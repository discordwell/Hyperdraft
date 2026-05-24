"""CLAN — Wave 2 adversarial candidate tournament runner.

Plays each of the 6 candidate decks (`CLAN_CANDIDATE_DECKS`) against each of
the 4 starter decks (`CLAN_STARTER_DECKS`) for `games_per_pairing` games per
ordered (candidate, starter) pair, with seat-balanced p1/p2 splits, repeated
across `trials` independent rng seeds and averaged.

Default config: 20 games/pair × 3 trials × 6 candidates × 4 starters = 1440
games. Output JSON matches the schema of wave-1's tournament JSON so analysis
tooling can re-use the same shape.

Usage
-----
    python scripts/play/clankers_candidate_tournament.py \\
        --trials 3 --games-per-pairing 20 --difficulty hard \\
        --json-out logs/clan_balance_wave2_matrix.json

Output schema (matches scripts/play/clankers_tournament.py):
    {
      "result": {
        "winrates": {candidate_label: avg WR% across all starter matchups},
        "stddev":   {candidate_label: stdev across trials},
        "per_trial": [...],
        "matchup":  {"<cand>|<starter>": {"<cand>": wins, "<starter>": wins,
                     "ties": ties, "turns_total": turns_total}},
        "coverage": {card_name: total cast count across all games},
        "deck_lengths": {label: 60},
        "config": {...}
      },
      "analysis": {
        "candidate_winrates": [(label, avg_winrate)],
        "top_played": [(card, archetype, casts)],
      }
    }
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Optional

# Make repo root importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ai.clankers_adapter import ClankersAIAdapter
from src.cards.clankers.CLAN.candidate_decks import CLAN_CANDIDATE_DECKS
from src.cards.clankers.CLAN.decks import CLAN_STARTER_DECKS
from src.engine.clankers_turn import ClankersTurnManager
from src.engine.types import (
    CardDefinition,
    Event,
    EventType,
    GameState,
    Player,
    ZoneType,
)


# Safety cap on the per-game turn loop; matches scripts/play/clankers_tournament.
GAME_TURN_SAFETY_CAP = 80


class CastTracker:
    """Accumulates per-card play counts (mirrors clankers_tournament.CastTracker)."""

    PLAY_DEST_ZONES = {ZoneType.CLANKERS_ASSEMBLY_FLOOR.name}

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def observe(self, state: GameState, events: list[Event]) -> None:
        if not events:
            return
        for ev in events:
            if ev.type is not EventType.ZONE_CHANGE:
                continue
            payload = getattr(ev, "payload", None) or {}
            to_zone = payload.get("to_zone")
            if to_zone not in self.PLAY_DEST_ZONES:
                continue
            obj_id = payload.get("object_id")
            if not isinstance(obj_id, str):
                continue
            obj = state.objects.get(obj_id)
            if obj is None:
                continue
            from_zone = payload.get("from_zone")
            if from_zone and from_zone != ZoneType.HAND.name:
                continue
            name = obj.name or "<unnamed>"
            self.counts[name] = self.counts.get(name, 0) + 1

    def install_on_turn_manager(self, tm: "ClankersTurnManager") -> None:
        original = tm._dispatch_play_card

        def wrapped(clankers, player_id, action, *args, **kwargs):
            if action.get("action") == "play_transient":
                cid = action.get("card_obj_id")
                obj = tm.state.objects.get(cid) if cid else None
                if obj is not None:
                    self.counts[obj.name] = self.counts.get(obj.name, 0) + 1
            return original(clankers, player_id, action, *args, **kwargs)

        tm._dispatch_play_card = wrapped  # type: ignore[assignment]


def _build_state(seed: int) -> GameState:
    state = GameState()
    state.game_mode = "clankers"
    state.rng_seed = seed
    state.players["p1"] = Player(id="p1", name="P1")
    state.players["p2"] = Player(id="p2", name="P2")
    return state


def _play_one_game(
    seed: int,
    deck_a: tuple[CardDefinition, list[CardDefinition]],
    deck_b: tuple[CardDefinition, list[CardDefinition]],
    *,
    difficulty: str,
    tracker: CastTracker,
    a_seat: str = "p1",
) -> tuple[Optional[str], int]:
    """Run one Clankers game between two prebuilt decks."""
    core_a, cards_a = deck_a
    core_b, cards_b = deck_b
    if a_seat == "p1":
        p1_core, p1_cards = core_a, cards_a
        p2_core, p2_cards = core_b, cards_b
    else:
        p1_core, p1_cards = core_b, cards_b
        p2_core, p2_cards = core_a, cards_a

    state = _build_state(seed)
    tm = ClankersTurnManager(state)
    state._pipeline = None  # type: ignore[attr-defined]
    state._game = None  # type: ignore[attr-defined]

    ai_p1 = ClankersAIAdapter(difficulty=difficulty)
    ai_p1.player_id = "p1"
    ai_p2 = ClankersAIAdapter(difficulty=difficulty)
    ai_p2.player_id = "p2"
    tm.set_ai_handler(ai_p1, "p1")
    tm.set_ai_handler(ai_p2, "p2")
    tm.set_ai_player("p1")
    tm.set_ai_player("p2")

    tracker.install_on_turn_manager(tm)

    setup_events = tm.setup_game(p1_cards, p1_core, p2_cards, p2_core)
    tracker.observe(state, setup_events)

    active = getattr(state, "active_player", None) or "p1"
    turns_played = 0
    for _ in range(GAME_TURN_SAFETY_CAP):
        try:
            events = tm.run_turn(active)
        except Exception:
            traceback.print_exc()
            state.clankers_loser = active  # type: ignore[attr-defined]
            state.game_over = True  # type: ignore[attr-defined]
            break
        turns_played += 1
        tracker.observe(state, events)
        if getattr(state, "game_over", False):
            break
        active = "p2" if active == "p1" else "p1"

    loser = getattr(state, "clankers_loser", None)
    losers_flagged = [
        pid for pid, p in state.players.items() if getattr(p, "has_lost", False)
    ]
    if loser is None and len(losers_flagged) == 1:
        loser = losers_flagged[0]
    if loser is None or len(losers_flagged) == 2:
        return None, turns_played
    winner_seat = "p2" if loser == "p1" else "p1"
    return winner_seat, turns_played


def _run_pairing(
    cand_label: str,
    cand_built: tuple[CardDefinition, list[CardDefinition]],
    starter_label: str,
    starter_built: tuple[CardDefinition, list[CardDefinition]],
    *,
    n_games: int,
    seed_base: int,
    difficulty: str,
    tracker: CastTracker,
) -> dict[str, int]:
    """Play ``n_games`` between a candidate and a starter, half with each as p1."""
    result = {cand_label: 0, starter_label: 0, "ties": 0, "turns_total": 0}
    half = n_games // 2
    for i in range(n_games):
        seed = seed_base + 17 * i + 1
        a_seat = "p1" if i < half else "p2"
        winner_seat, turns = _play_one_game(
            seed, cand_built, starter_built,
            difficulty=difficulty, tracker=tracker, a_seat=a_seat,
        )
        result["turns_total"] += turns
        if winner_seat is None:
            result["ties"] += 1
            continue
        if (a_seat == "p1" and winner_seat == "p1") or (a_seat == "p2" and winner_seat == "p2"):
            result[cand_label] += 1
        else:
            result[starter_label] += 1
    return result


def _build_all_candidates() -> dict[str, tuple[CardDefinition, list[CardDefinition]]]:
    return {label: builder() for label, builder in CLAN_CANDIDATE_DECKS.items()}


def _build_all_starters() -> dict[str, tuple[CardDefinition, list[CardDefinition]]]:
    return {label: builder() for label, builder in CLAN_STARTER_DECKS.items()}


def run_single_round(
    *,
    games_per_pairing: int,
    difficulty: str,
    seed_base: int,
    verbose: bool = False,
) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    """Run one round of candidate-vs-starter matchups.

    Returns ``(matchup_results, coverage)`` where matchup is keyed by
    "<candidate>|<starter>".
    """
    candidates = _build_all_candidates()
    starters = _build_all_starters()
    tracker = CastTracker()

    matchup: dict[str, dict[str, int]] = {}
    for cand_label, cand_built in candidates.items():
        for starter_label, starter_built in starters.items():
            if verbose:
                print(f"  {cand_label} vs {starter_label} … ", end="", flush=True)
            pair_seed = seed_base + (hash((cand_label, starter_label)) & 0xFFFF)
            pair_result = _run_pairing(
                cand_label, cand_built, starter_label, starter_built,
                n_games=games_per_pairing,
                seed_base=pair_seed,
                difficulty=difficulty,
                tracker=tracker,
            )
            matchup[f"{cand_label}|{starter_label}"] = pair_result
            if verbose:
                tot = pair_result.get("turns_total", 0)
                print(
                    f"{pair_result[cand_label]:>2} - {pair_result[starter_label]:>2}  "
                    f"(ties {pair_result['ties']}, avg turns "
                    f"{tot / max(1, games_per_pairing):.1f})"
                )

    return matchup, dict(tracker.counts)


def _aggregate_candidate_winrates(
    matchup: dict[str, dict[str, int]],
    candidate_names: list[str],
) -> dict[str, float]:
    """Per-candidate winrate (%) averaged across the 4 starter matchups."""
    totals: dict[str, dict[str, int]] = {n: {"wins": 0, "games": 0} for n in candidate_names}
    for key, r in matchup.items():
        cand, _ = key.split("|", 1)
        if cand not in totals:
            continue
        wins = int(r.get(cand, 0))
        ties = int(r.get("ties", 0))
        # losses are everything else in the pair result
        total_games = sum(v for k, v in r.items() if k not in ("ties", "turns_total")) + ties
        totals[cand]["wins"] += wins
        totals[cand]["games"] += total_games
    out: dict[str, float] = {}
    for n in candidate_names:
        g = totals[n]["games"]
        out[n] = totals[n]["wins"] / g * 100.0 if g > 0 else 0.0
    return out


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(var)


def run_tournament(
    games_per_pairing: int = 20,
    trials: int = 3,
    ai_difficulty: str = "hard",
    seed_base: int = 42,
    verbose: bool = False,
) -> dict[str, Any]:
    """Multi-trial 6×4 candidate-vs-starter matrix."""
    candidates = _build_all_candidates()
    starters = _build_all_starters()
    cand_names = list(candidates.keys())

    per_trial: list[dict[str, float]] = []
    averaged_matchup: dict[str, dict[str, float]] = {}
    aggregated_coverage: dict[str, int] = {}

    for trial_idx in range(trials):
        trial_seed = seed_base + trial_idx * 100_003
        if verbose:
            print(f"\n=== Trial {trial_idx + 1}/{trials} (seed_base={trial_seed}) ===")
        t0 = time.time()
        matchup, coverage = run_single_round(
            games_per_pairing=games_per_pairing,
            difficulty=ai_difficulty,
            seed_base=trial_seed,
            verbose=verbose,
        )
        elapsed = time.time() - t0
        if verbose:
            print(f"  Trial finished in {elapsed:.1f}s")

        trial_wr = _aggregate_candidate_winrates(matchup, cand_names)
        per_trial.append(trial_wr)

        for name, count in coverage.items():
            aggregated_coverage[name] = aggregated_coverage.get(name, 0) + count

        for key, r in matchup.items():
            slot = averaged_matchup.setdefault(key, {})
            for k, v in r.items():
                slot[k] = slot.get(k, 0.0) + float(v)

    if trials > 0:
        for key, slot in averaged_matchup.items():
            for k in list(slot.keys()):
                slot[k] = slot[k] / trials

    winrates: dict[str, float] = {}
    stddev: dict[str, float] = {}
    for n in cand_names:
        rates = [trial.get(n, 0.0) for trial in per_trial]
        winrates[n] = sum(rates) / max(1, len(rates))
        stddev[n] = _stdev(rates)

    deck_lengths = {label: len(cards) for label, (_, cards) in candidates.items()}
    starter_lengths = {label: len(cards) for label, (_, cards) in starters.items()}

    return {
        "winrates": winrates,
        "stddev": stddev,
        "per_trial": per_trial,
        "matchup": averaged_matchup,
        "coverage": aggregated_coverage,
        "deck_lengths": deck_lengths,
        "starter_lengths": starter_lengths,
        "config": {
            "games_per_pairing": games_per_pairing,
            "trials": trials,
            "ai_difficulty": ai_difficulty,
            "seed_base": seed_base,
            "games_total": games_per_pairing * trials * len(cand_names) * len(starters),
            "candidate_names": cand_names,
            "starter_names": list(starters.keys()),
        },
    }


def _card_archetype_lookup() -> dict[str, str]:
    """Map card name -> clankers_archetype tag (using both starters + candidates)."""
    lookup: dict[str, str] = {}
    for builder in CLAN_STARTER_DECKS.values():
        _core, deck = builder()
        for cd in deck:
            arch = getattr(cd, "clankers_archetype", None) or "?"
            lookup.setdefault(cd.name, arch)
    for builder in CLAN_CANDIDATE_DECKS.values():
        _core, deck = builder()
        for cd in deck:
            arch = getattr(cd, "clankers_archetype", None) or "?"
            lookup.setdefault(cd.name, arch)
    return lookup


def analyze_results(result: dict[str, Any]) -> dict[str, Any]:
    """Pull high-leverage signals for Wave 2 analysis.

    Returns:
      - 'candidate_winrates': sorted list of (label, mean WR%)
      - 'top_played': top 10 by cast count
      - 'dominant_candidates': candidates above 65% (Wave 4 trigger)
    """
    winrates: dict[str, float] = result["winrates"]
    coverage: dict[str, int] = result["coverage"]
    arch = _card_archetype_lookup()

    candidate_winrates = sorted(winrates.items(), key=lambda kv: kv[1], reverse=True)
    dominant_candidates = [(n, wr) for n, wr in candidate_winrates if wr > 65.0]

    top_played = sorted(coverage.items(), key=lambda kv: kv[1], reverse=True)[:10]

    return {
        "candidate_winrates": candidate_winrates,
        "top_played": [(n, arch.get(n, "?"), c) for n, c in top_played],
        "dominant_candidates": dominant_candidates,
    }


def _format_block(title: str, lines: list[str]) -> str:
    sep = "=" * 72
    return "\n".join([sep, title, sep, *lines, ""])


def print_report(result: dict[str, Any], analysis: dict[str, Any]) -> None:
    cfg = result["config"]
    print("")
    print(_format_block(
        f"CLAN Candidate Tournament — {cfg['trials']} trials × "
        f"{cfg['games_per_pairing']} games/pairing × "
        f"{len(cfg['candidate_names'])} candidates × "
        f"{len(cfg['starter_names'])} starters = {cfg['games_total']} games "
        f"(difficulty={cfg['ai_difficulty']})",
        [],
    ).rstrip())

    # Per-candidate winrate.
    lines = [f"{'Candidate':<30} | {'Mean WR%':>8} | {'StdDev':>7} | per-trial"]
    lines.append("-" * 72)
    for name, wr in result["winrates"].items():
        per_trial_str = " ".join(f"{t.get(name, 0.0):.1f}" for t in result["per_trial"])
        lines.append(
            f"{name:<30} | {wr:>7.2f}% | {result['stddev'][name]:>6.2f}% | {per_trial_str}"
        )
    print(_format_block("Per-candidate winrates (vs all starters)", lines).rstrip())

    # Matchup table — broken out as candidate rows × starter columns.
    starter_names = cfg["starter_names"]
    lines = [f"{'Candidate':<30} | " + " ".join(f"{s[5:]:>10}" for s in starter_names) + "  | avg"]
    lines.append("-" * (30 + 3 + 11 * len(starter_names) + 7))
    for cand in cfg["candidate_names"]:
        row_parts = []
        wr_sum = 0.0
        wr_count = 0
        for starter in starter_names:
            key = f"{cand}|{starter}"
            slot = result["matchup"].get(key, {})
            cand_wins = slot.get(cand, 0.0)
            starter_wins = slot.get(starter, 0.0)
            ties = slot.get("ties", 0.0)
            total = cand_wins + starter_wins + ties
            wr = (cand_wins / total * 100.0) if total > 0 else 0.0
            wr_sum += wr
            wr_count += 1
            row_parts.append(f"{wr:>9.1f}%")
        avg = wr_sum / max(1, wr_count)
        lines.append(f"{cand:<30} | " + " ".join(row_parts) + f"  | {avg:>5.1f}%")
    print(_format_block("Candidate × Starter matchup grid (candidate winrate %)", lines).rstrip())

    # Dominant candidates.
    if analysis["dominant_candidates"]:
        lines = [f"DOMINANT (>65%) — Wave 4 (engine-level) trigger:"]
        for n, wr in analysis["dominant_candidates"]:
            lines.append(f"  - {n}: {wr:.1f}%")
        print(_format_block("Dominance verdict", lines).rstrip())
    else:
        print(_format_block("Dominance verdict", ["No candidate above 65%. Proceed to Wave 3."]).rstrip())

    # Top played.
    lines = [f"{'Card':<32} | {'Archetype':<12} | {'Casts':>6}"]
    lines.append("-" * 72)
    for n, a, c in analysis["top_played"]:
        lines.append(f"{n:<32} | {a:<12} | {c:>6}")
    print(_format_block("Top 10 most-cast cards", lines).rstrip())


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CLAN — Wave 2 candidate tournament")
    p.add_argument("--trials", "-t", type=int, default=3,
                   help="Number of independent trials (default 3).")
    p.add_argument("--games-per-pairing", "-n", type=int, default=20,
                   help="Games per ordered (candidate, starter) pairing per trial (default 20).")
    p.add_argument("--difficulty", "-d",
                   choices=("easy", "medium", "hard"), default="hard",
                   help="AI difficulty (applies to both seats).")
    p.add_argument("--seed-base", type=int, default=42,
                   help="Base RNG seed (default 42).")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Print per-pairing progress.")
    p.add_argument("--json-out", type=str, default=None,
                   help="Optional path to write the full result + analysis JSON.")
    return p


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v) for v in obj]
    return obj


def main() -> None:
    args = _build_argparser().parse_args()
    n_cands = len(CLAN_CANDIDATE_DECKS)
    n_starters = len(CLAN_STARTER_DECKS)
    total_games = args.trials * args.games_per_pairing * n_cands * n_starters
    print(
        f"Running CLAN candidate tournament — {args.trials} trials × "
        f"{args.games_per_pairing} games/pairing × "
        f"{n_cands} candidates × {n_starters} starters = {total_games} games "
        f"(difficulty={args.difficulty})"
    )
    print(f"  Candidates: {list(CLAN_CANDIDATE_DECKS.keys())}")
    print(f"  Starters:   {list(CLAN_STARTER_DECKS.keys())}")
    t0 = time.time()
    result = run_tournament(
        games_per_pairing=args.games_per_pairing,
        trials=args.trials,
        ai_difficulty=args.difficulty,
        seed_base=args.seed_base,
        verbose=args.verbose,
    )
    elapsed = time.time() - t0
    print(f"\nFinished in {elapsed:.1f}s ({elapsed / 60.0:.1f}m)")

    analysis = analyze_results(result)
    print_report(result, analysis)

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "result": _json_safe(result),
            "analysis": _json_safe(analysis),
        }
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=False))
        print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
