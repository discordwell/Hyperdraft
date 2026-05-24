"""CLAN — Workshop Genesis tournament runner.

Round-robin between the four CLAN starter decks (FORGE / ETHOS / MIRTH /
BULWARK), running ``games_per_pairing`` games per ordered pair with
seat-balanced splits, repeated across ``trials`` independent rng seeds and
averaged. Mirrors ``scripts/play/cats_tournament.py`` in shape so the
balance loop has a familiar surface.

Usage
-----
    python scripts/play/clankers_tournament.py \
        --trials 5 --games-per-pairing 10 --difficulty hard

    from scripts.play.clankers_tournament import run_tournament
    result = run_tournament(trials=5, games_per_pairing=10)

Tournament loop, per spec:
  1. Discover the 4 starter decks in ``CLAN_STARTER_DECKS``.
  2. For every ordered pair (A, B) of distinct decks, play
     ``games_per_pairing`` games — half with A as p1, half with B.
  3. Each game: ``ClankersTurnManager.setup_game(deck_a, core_a, deck_b,
     core_b)``, then alternate ``run_turn(active)`` until ``state.game_over``
     or the 80-turn safety cap.
  4. Winner = ``state.clankers_loser``'s opponent. Mutual breaches count as
     a tie (no win credit to either).
  5. Per-card cast count = number of HAND → CLANKERS_ASSEMBLY_FLOOR /
     CLANKERS_SCRAP_HEAP zone changes whose ``object_id`` resolves to a
     named card.
  6. Across ``trials`` independent rng seeds, results are averaged.

Returns (from ``run_tournament``):
    {
      "winrates": {deck_label: float mean across trials},
      "per_trial": [{deck: winrate, ...} for each trial],
      "matchup": {(a, b): {a: wins, b: wins, "ties": ties} averaged},
      "coverage": {card_name: cast_count across all games and trials},
      "deck_lengths": {deck: 60, ...},
      "stddev": {deck_label: stdev of trial winrates},
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


# Safety cap on the per-game turn loop. A typical CLAN game finishes in
# 15-30 turns; deathclock games can run to ~45. We pick 80 as the hard
# bound — anything past that is a runaway.
GAME_TURN_SAFETY_CAP = 80


# ---------------------------------------------------------------------------
# Per-game cast tracker
# ---------------------------------------------------------------------------

class CastTracker:
    """Accumulates per-card play counts.

    Two collection paths cover the full play space:
      1. ZONE_CHANGE → CLANKERS_ASSEMBLY_FLOOR events catch chassis,
         weapons, add-ons, and structures (these emit explicit
         ZONE_CHANGE events in ``_play_chassis`` / ``_play_part`` /
         ``_play_structure``).
      2. Transients don't emit ZONE_CHANGE (their ``_play_transient``
         path mutates zones directly), so we also instrument the turn
         manager's ``_dispatch_play_card`` and ``_dispatch_attach``
         methods via ``install_on_turn_manager`` — those see every
         ``play_<cardtype>`` action the AI decides on.

    To avoid double-counting (a chassis play is observed both by the
    turn-manager hook AND by the ZONE_CHANGE event), the turn-manager
    hook only records ``play_transient`` actions. The event-stream
    path handles every other card type.
    """

    PLAY_DEST_ZONES = {
        ZoneType.CLANKERS_ASSEMBLY_FLOOR.name,
    }

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
                # Bookkeeping move (floor -> floor, scrap -> floor, ...);
                # only count hand -> floor (the canonical cast).
                continue
            name = obj.name or "<unnamed>"
            self.counts[name] = self.counts.get(name, 0) + 1

    def install_on_turn_manager(self, tm: "ClankersTurnManager") -> None:
        """Wrap ``tm._dispatch_play_card`` so Transient plays are tracked.

        Chassis / Weapon / Add-On / Structure plays already fire
        ZONE_CHANGE events that ``observe`` will catch, so we deliberately
        only record Transients here to avoid double-counting.
        """
        original = tm._dispatch_play_card

        def wrapped(clankers, player_id, action, *args, **kwargs):
            if action.get("action") == "play_transient":
                cid = action.get("card_obj_id")
                obj = tm.state.objects.get(cid) if cid else None
                if obj is not None:
                    self.counts[obj.name] = self.counts.get(obj.name, 0) + 1
            return original(clankers, player_id, action, *args, **kwargs)

        tm._dispatch_play_card = wrapped  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Game runner
# ---------------------------------------------------------------------------

def _build_state(
    seed: int,
    p1_deck: list[CardDefinition],
    p2_deck: list[CardDefinition],
) -> GameState:
    """Build a fresh 2-player Clankers state with the canonical p1/p2 ids."""
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
    """Run one Clankers game between two prebuilt decks.

    Returns (winner_seat or None for tie, turns_played). The deck whose
    label was assigned to ``a_seat`` is p1; the other is p2. Winner is the
    seat whose opponent matches ``state.clankers_loser``; ``None`` when
    both players are flagged as losers (mutual breach) or the safety cap
    triggers.
    """
    core_a, cards_a = deck_a
    core_b, cards_b = deck_b
    if a_seat == "p1":
        p1_core, p1_cards = core_a, cards_a
        p2_core, p2_cards = core_b, cards_b
    else:
        p1_core, p1_cards = core_b, cards_b
        p2_core, p2_cards = core_a, cards_a

    state = _build_state(seed, p1_cards, p2_cards)
    # Fresh turn manager + AI handlers per game (state, RNG, scratchpads
    # all reset). No Game wrapper needed — setup_game is the documented
    # entry point and tolerates state._game = None via _inline_setup_player.
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

    # Track Transient plays via the dispatcher (they don't emit
    # ZONE_CHANGE events).
    tracker.install_on_turn_manager(tm)

    setup_events = tm.setup_game(p1_cards, p1_core, p2_cards, p2_core)
    tracker.observe(state, setup_events)

    active = getattr(state, "active_player", None) or "p1"
    turns_played = 0
    for _ in range(GAME_TURN_SAFETY_CAP):
        try:
            events = tm.run_turn(active)
        except Exception:
            # If a turn raises, treat the active player as the loser so the
            # game doesn't loop. The tournament harness logs but doesn't
            # propagate.
            traceback.print_exc()
            state.clankers_loser = active  # type: ignore[attr-defined]
            state.game_over = True  # type: ignore[attr-defined]
            break

        turns_played += 1
        tracker.observe(state, events)

        if getattr(state, "game_over", False):
            break
        active = "p2" if active == "p1" else "p1"

    # Decide winner: the deck whose owner is NOT the loser.
    loser = getattr(state, "clankers_loser", None)
    # Mutual breach: both players flagged as has_lost.
    losers_flagged = [
        pid for pid, p in state.players.items() if getattr(p, "has_lost", False)
    ]
    if loser is None and len(losers_flagged) == 1:
        loser = losers_flagged[0]
    if loser is None or len(losers_flagged) == 2:
        return None, turns_played
    winner_seat = "p2" if loser == "p1" else "p1"
    return winner_seat, turns_played


# ---------------------------------------------------------------------------
# Round-robin core
# ---------------------------------------------------------------------------

def _ordered_pairs(deck_names: list[str]) -> list[tuple[str, str]]:
    """Return all distinct ordered pairs (a, b) with a != b.

    For a 4-deck round-robin this yields 12 ordered pairs, but we'll iterate
    only the 6 unordered pairs at the top level and seat-balance within each
    pairing — see ``_run_pairing``.
    """
    pairs = []
    for i, a in enumerate(deck_names):
        for b in deck_names[i + 1:]:
            pairs.append((a, b))
    return pairs


def _run_pairing(
    deck_a_label: str,
    deck_a_built: tuple[CardDefinition, list[CardDefinition]],
    deck_b_label: str,
    deck_b_built: tuple[CardDefinition, list[CardDefinition]],
    *,
    n_games: int,
    seed_base: int,
    difficulty: str,
    tracker: CastTracker,
) -> dict[str, int]:
    """Play ``n_games`` between two decks, half with each as p1.

    Returns ``{deck_a_label: wins, deck_b_label: wins, "ties": ties,
    "turns_total": total_turns_played}``.
    """
    result = {deck_a_label: 0, deck_b_label: 0, "ties": 0, "turns_total": 0}
    half = n_games // 2
    for i in range(n_games):
        seed = seed_base + 17 * i + 1
        # First half: deck A as p1. Second half: deck B as p1.
        if i < half:
            a_seat = "p1"
        else:
            a_seat = "p2"
        winner_seat, turns = _play_one_game(
            seed, deck_a_built, deck_b_built,
            difficulty=difficulty, tracker=tracker, a_seat=a_seat,
        )
        result["turns_total"] += turns
        if winner_seat is None:
            result["ties"] += 1
            continue
        # Translate winner_seat back to deck label.
        if (a_seat == "p1" and winner_seat == "p1") or (
            a_seat == "p2" and winner_seat == "p2"
        ):
            result[deck_a_label] += 1
        else:
            result[deck_b_label] += 1
    return result


def _build_all_decks() -> dict[str, tuple[CardDefinition, list[CardDefinition]]]:
    """Call each CLAN deck builder once and cache the (core, deck) tuple."""
    built: dict[str, tuple[CardDefinition, list[CardDefinition]]] = {}
    for label, builder in CLAN_STARTER_DECKS.items():
        built[label] = builder()
    return built


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_single_round(
    *,
    games_per_pairing: int,
    difficulty: str,
    seed_base: int,
    verbose: bool = False,
) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    """Run one full round-robin tournament.

    Returns ``(matchup_results, coverage)`` where matchup_results is keyed
    by (deck_a, deck_b) tuple-as-string-pair and coverage is a flat dict
    of {card_name: cast_count}.
    """
    decks = _build_all_decks()
    deck_names = list(decks.keys())
    tracker = CastTracker()

    matchup: dict[str, dict[str, int]] = {}
    for a, b in _ordered_pairs(deck_names):
        if verbose:
            print(f"  {a} vs {b} … ", end="", flush=True)
        pair_seed = seed_base + (hash((a, b)) & 0xFFFF)
        pair_result = _run_pairing(
            a, decks[a], b, decks[b],
            n_games=games_per_pairing,
            seed_base=pair_seed,
            difficulty=difficulty,
            tracker=tracker,
        )
        matchup[f"{a}|{b}"] = pair_result
        if verbose:
            tot = pair_result.get("turns_total", 0)
            print(
                f"{pair_result[a]:>2} - {pair_result[b]:>2}  "
                f"(ties {pair_result['ties']}, avg turns "
                f"{tot / max(1, games_per_pairing):.1f})"
            )

    return matchup, dict(tracker.counts)


def _aggregate_winrates(
    matchup: dict[str, dict[str, int]],
    deck_names: list[str],
) -> dict[str, float]:
    """Compute per-deck winrate (in percent) across the matchup table.

    Ties count for neither deck but still count as games played.
    """
    totals: dict[str, dict[str, int]] = {
        n: {"wins": 0, "ties": 0, "games": 0} for n in deck_names
    }
    for key, r in matchup.items():
        a, b = key.split("|", 1)
        a_w = int(r.get(a, 0))
        b_w = int(r.get(b, 0))
        t = int(r.get("ties", 0))
        games = a_w + b_w + t
        totals[a]["wins"] += a_w
        totals[a]["ties"] += t
        totals[a]["games"] += games
        totals[b]["wins"] += b_w
        totals[b]["ties"] += t
        totals[b]["games"] += games
    out: dict[str, float] = {}
    for n in deck_names:
        g = totals[n]["games"]
        if g == 0:
            out[n] = 0.0
            continue
        # Ties contribute 0 wins; report pure win% to mirror the design doc's
        # 40-60% band. (CATS uses 0.5*ties; CLAN's target band reads cleaner
        # without including ties.)
        out[n] = totals[n]["wins"] / g * 100.0
    return out


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(var)


def run_tournament(
    games_per_pairing: int = 10,
    trials: int = 5,
    ai_difficulty: str = "hard",
    seed_base: int = 42,
    verbose: bool = False,
) -> dict[str, Any]:
    """Multi-trial round-robin between the 4 CLAN starter decks.

    See module docstring for the full result shape.
    """
    decks = _build_all_decks()
    deck_names = list(decks.keys())

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

        # Aggregate winrates for this trial.
        trial_wr = _aggregate_winrates(matchup, deck_names)
        per_trial.append(trial_wr)

        # Sum coverage across trials.
        for name, count in coverage.items():
            aggregated_coverage[name] = aggregated_coverage.get(name, 0) + count

        # Fold matchup wins into an averaged matchup table.
        for key, r in matchup.items():
            slot = averaged_matchup.setdefault(key, {})
            for k, v in r.items():
                slot[k] = slot.get(k, 0.0) + float(v)

    # Average matchup across trials.
    if trials > 0:
        for key, slot in averaged_matchup.items():
            for k in list(slot.keys()):
                slot[k] = slot[k] / trials

    # Compute mean + stddev winrate per deck across trials.
    winrates: dict[str, float] = {}
    stddev: dict[str, float] = {}
    for n in deck_names:
        rates = [trial.get(n, 0.0) for trial in per_trial]
        winrates[n] = sum(rates) / max(1, len(rates))
        stddev[n] = _stdev(rates)

    deck_lengths = {label: len(cards) for label, (_, cards) in decks.items()}

    return {
        "winrates": winrates,
        "stddev": stddev,
        "per_trial": per_trial,
        "matchup": averaged_matchup,
        "coverage": aggregated_coverage,
        "deck_lengths": deck_lengths,
        "config": {
            "games_per_pairing": games_per_pairing,
            "trials": trials,
            "ai_difficulty": ai_difficulty,
            "seed_base": seed_base,
            "games_total": games_per_pairing * trials * len(deck_names) * (len(deck_names) - 1) // 2,
        },
    }


# ---------------------------------------------------------------------------
# Coverage / analysis helpers
# ---------------------------------------------------------------------------

def _all_card_names_in_decks() -> dict[str, set[str]]:
    """Map deck_label -> set of card names that appear in that deck.

    Used by zero-play detection: a card is "zero play in a deck context"
    only if it's in the deck AND was never cast. Cores are excluded —
    they live in COMMAND zone and are never "cast" through the
    Assemble dispatcher.
    """
    out: dict[str, set[str]] = {}
    for label, builder in CLAN_STARTER_DECKS.items():
        _core, deck = builder()
        names = set()
        for card_def in deck:
            names.add(card_def.name)
        out[label] = names
    return out


def _card_archetype_lookup() -> dict[str, str]:
    """Map card name -> clankers_archetype tag for every card across all decks.

    Lets the zero-play report annotate each entry with its archetype.
    Cores are skipped (they never enter the cast stream).
    """
    lookup: dict[str, str] = {}
    for builder in CLAN_STARTER_DECKS.values():
        _core, deck = builder()
        for cd in deck:
            arch = getattr(cd, "clankers_archetype", None) or "?"
            lookup.setdefault(cd.name, arch)
    return lookup


def analyze_results(result: dict[str, Any]) -> dict[str, Any]:
    """Pull the high-leverage signals out of a multi-trial result.

    Returns a dict with:
      - 'out_of_band': decks whose mean winrate is outside [40, 60]
      - 'zero_play_by_deck': per-deck list of card names that were never cast
      - 'zero_play_overall': cards never cast in ANY game
      - 'top_played': top-5 by cast_count (potential over-tuned cards)
    """
    winrates: dict[str, float] = result["winrates"]
    coverage: dict[str, int] = result["coverage"]
    decks_to_cards = _all_card_names_in_decks()
    arch = _card_archetype_lookup()

    out_of_band = [
        (n, wr) for n, wr in winrates.items() if wr < 40.0 or wr > 60.0
    ]

    zero_play_by_deck: dict[str, list[str]] = {}
    all_in_any_deck: set[str] = set()
    for label, names in decks_to_cards.items():
        zp = sorted([n for n in names if coverage.get(n, 0) == 0])
        zero_play_by_deck[label] = zp
        all_in_any_deck |= names

    zero_play_overall = sorted([
        n for n in all_in_any_deck if coverage.get(n, 0) == 0
    ])

    top_played = sorted(
        coverage.items(), key=lambda kv: kv[1], reverse=True
    )[:5]

    return {
        "out_of_band": out_of_band,
        "zero_play_by_deck": zero_play_by_deck,
        "zero_play_overall": [(n, arch.get(n, "?")) for n in zero_play_overall],
        "top_played": [(n, arch.get(n, "?"), c) for n, c in top_played],
    }


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------

def _format_block(title: str, lines: list[str]) -> str:
    sep = "=" * 72
    return "\n".join([sep, title, sep, *lines, ""])


def print_report(result: dict[str, Any], analysis: dict[str, Any]) -> None:
    cfg = result["config"]
    print("")
    print(_format_block(
        f"CLAN Tournament — {cfg['trials']} trials x "
        f"{cfg['games_per_pairing']} games/pairing "
        f"(difficulty={cfg['ai_difficulty']}, total games={cfg['games_total']})",
        [],
    ).rstrip())

    # Per-deck winrate.
    lines = [f"{'Deck':<18} | {'Mean WR%':>8} | {'StdDev':>7} | per-trial"]
    lines.append("-" * 72)
    for name, wr in result["winrates"].items():
        per_trial_str = " ".join(f"{t.get(name, 0.0):.1f}" for t in result["per_trial"])
        lines.append(
            f"{name:<18} | {wr:>7.2f}% | {result['stddev'][name]:>6.2f}% | {per_trial_str}"
        )
    print(_format_block("Per-deck winrates", lines).rstrip())

    # Matchup table.
    deck_names = list(result["winrates"].keys())
    lines = [f"{'Pairing':<42} | {'A':>5} {'B':>5} {'T':>5}"]
    lines.append("-" * 72)
    for key, slot in result["matchup"].items():
        a, b = key.split("|", 1)
        lines.append(
            f"{a + ' vs ' + b:<42} | "
            f"{slot.get(a, 0.0):>5.1f} {slot.get(b, 0.0):>5.1f} {slot.get('ties', 0.0):>5.1f}"
        )
    print(_format_block("Pairing-level wins (averaged across trials)", lines).rstrip())

    # Out-of-band.
    if analysis["out_of_band"]:
        lines = ["OUT OF TARGET 40-60% range:"]
        for n, wr in analysis["out_of_band"]:
            lines.append(f"  - {n}: {wr:.1f}%")
        print(_format_block("Balance verdict", lines).rstrip())
    else:
        print(_format_block("Balance verdict", ["All decks within 40-60% band."]).rstrip())

    # Top played.
    lines = [f"{'Card':<32} | {'Archetype':<12} | {'Casts':>6}"]
    lines.append("-" * 72)
    for n, a, c in analysis["top_played"]:
        lines.append(f"{n:<32} | {a:<12} | {c:>6}")
    print(_format_block("Top 5 most-cast cards", lines).rstrip())

    # Zero play overall.
    zp = analysis["zero_play_overall"]
    if zp:
        lines = [f"{'Card':<32} | {'Archetype':<12}"]
        lines.append("-" * 48)
        for n, a in zp:
            lines.append(f"{n:<32} | {a:<12}")
        print(_format_block(
            f"Cards never cast across {cfg['games_total']} games "
            f"({len(zp)} cards)",
            lines,
        ).rstrip())
    else:
        print(_format_block("Zero-play coverage", ["Every card was cast at least once."]).rstrip())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CLAN — round-robin tournament runner")
    p.add_argument("--trials", "-t", type=int, default=5,
                   help="Number of independent multi-game rounds (default 5).")
    p.add_argument("--games-per-pairing", "-n", type=int, default=10,
                   help="Games per ordered deck pairing per trial (default 10).")
    p.add_argument("--difficulty", "-d",
                   choices=("easy", "medium", "hard"), default="hard",
                   help="AI difficulty (applies to both seats).")
    p.add_argument("--seed-base", type=int, default=42,
                   help="Base RNG seed (default 42).")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Print per-pairing progress and per-trial timing.")
    p.add_argument("--json-out", type=str, default=None,
                   help="Optional path to write the full result dict as JSON.")
    return p


def _json_safe(obj: Any) -> Any:
    """Recursively convert tuples / sets to JSON-friendly structures."""
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v) for v in obj]
    return obj


def main() -> None:
    args = _build_argparser().parse_args()
    print(
        f"Running CLAN tournament — {args.trials} trials × "
        f"{args.games_per_pairing} games/pairing × "
        f"4 decks × 3 ordered pairings = "
        f"{args.trials * args.games_per_pairing * 6} games "
        f"(difficulty={args.difficulty})"
    )
    print(f"  Decks: {list(CLAN_STARTER_DECKS.keys())}")
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
