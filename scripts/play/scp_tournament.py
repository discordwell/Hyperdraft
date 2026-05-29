"""SCP Containment TCG starter-deck balance harness.

This is intentionally small: it gives the prototype a repeatable baseline
before larger set/AI/art passes. The output shape mirrors the other Hyperdraft
tournament scripts enough to compare archetype win rates and game length.

Usage:
    python -m scripts.play.scp_tournament --games 12 --max-turns 40 \
      --out logs/scp_tournament.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

from src.ai.scp_adapter import SCPAIAdapter, SUPPORTED_SCP_PILOTS, validate_scp_pilot
from src.cards.scp import SCP_STARTER_DECKS
from src.engine.game import Game
from src.engine import scp


@dataclass
class SCPGameOutcome:
    p1_deck: str
    p2_deck: str
    p1_pilot: str
    p2_pilot: str
    winner_deck: Optional[str]
    loser_deck: Optional[str]
    winner_reason: str
    turns: int
    duration_s: float
    p1_site: dict[str, Any]
    p2_site: dict[str, Any]
    error: Optional[str] = None


class _DispatchSCPAIAdapter:
    def __init__(self, adapters: dict[str, SCPAIAdapter]):
        self.adapters = adapters

    async def take_turn(self, player_id: str, state, game) -> list:
        return await self.adapters[player_id].take_turn(player_id, state, game)


def _winner_reason(game: Game, winner_id: Optional[str]) -> str:
    if winner_id is None:
        return "draw_or_timeout"
    opponent = next((p for p in game.state.players.values() if p.id != winner_id), None)
    if not opponent:
        return "unknown"
    site = game.state.scp_sites.get(opponent.id, {})
    if site.get("breach", 0) >= 10:
        return "opponent_breach"
    if site.get("secrecy", 0) <= 0:
        return "opponent_exposure"
    if site.get("ethics_debt", 0) >= 8:
        return "opponent_ethics"
    winner_site = game.state.scp_sites.get(winner_id, {})
    if winner_site.get("archives", 0) >= 7:
        return "archives"
    for mandate_id in list(game.state.scp_mandates.get(winner_id, [])):
        mandate = game.state.objects.get(mandate_id)
        if not mandate or mandate.state.scp_status != "active" or not mandate.card_def:
            continue
        alt_win = getattr(mandate.card_def, "scp_alt_win", None)
        if alt_win == "redaction" and scp.redaction_alt_win_met(mandate.card_def, winner_site):
            return "total_redaction"
        if alt_win == "thaumiel" and len(game.state.scp_contained.get(winner_id, [])) >= 4 and winner_site.get("breach", 0) == 0:
            return "thaumiel_containment"
        if alt_win == "veil_lockdown" and winner_site.get("archives", 0) >= 3 and winner_site.get("breach", 0) == 0:
            return "veil_lockdown"
        if (
            alt_win == "ethics_audit"
            and winner_site.get("archives", 0) >= 4
            and winner_site.get("secrecy", 0) >= 8
            and winner_site.get("ethics_debt", 0) <= 2
        ):
            return "ethics_audit"
        if alt_win == "public_panic" and winner_site.get("archives", 0) >= 4:
            for opponent_id, opponent_site in game.state.scp_sites.items():
                if opponent_id != winner_id and opponent_site.get("secrecy", 0) <= 6:
                    return "public_panic"
        # MNR alt-wins. memory_hole sums forgotten anomalies across all
        # players (own-side forgets count under the relaxed rule); both
        # mirror the thresholds in src/engine/scp.py::check_scp_victory.
        if alt_win == "memory_hole":
            total_forgotten = sum(
                len(game.state.scp_forgotten.get(pid, []))
                for pid in game.state.players
            )
            if total_forgotten >= 3 and winner_site.get("secrecy", 0) >= 10:
                return "memory_hole"
        if alt_win == "mnestic_saturation":
            mnestic_count = 0
            for pid in game.state.scp_personnel.get(winner_id, []):
                person = game.state.objects.get(pid)
                if not person or person.state.scp_status != "active":
                    continue
                if (getattr(person.card_def, "scp_mnestic", False)
                        or person.state.scp_mnestic_gained):
                    mnestic_count += 1
            if mnestic_count >= 4 and winner_site.get("archives", 0) >= 4:
                return "mnestic_saturation"
    return "alternate_or_state_based"


async def run_one_game(
    p1_deck_name: str,
    p2_deck_name: str,
    *,
    seed: int,
    max_turns: int,
    difficulty: str,
    p1_pilot: str,
    p2_pilot: str,
) -> SCPGameOutcome:
    p1_pilot = validate_scp_pilot(p1_pilot)
    p2_pilot = validate_scp_pilot(p2_pilot)
    started = time.perf_counter()
    random.seed(seed)
    game = Game(mode="scp")
    p1 = game.add_player(f"{p1_deck_name}-pilot")
    p2 = game.add_player(f"{p2_deck_name}-pilot")
    game.setup_scp_player(p1, SCP_STARTER_DECKS[p1_deck_name]())
    game.setup_scp_player(p2, SCP_STARTER_DECKS[p2_deck_name]())
    game.shuffle_library(p1.id)
    game.shuffle_library(p2.id)
    game.turn_manager.set_ai_player(p1.id)
    game.turn_manager.set_ai_player(p2.id)
    game.turn_manager.set_ai_handler(_DispatchSCPAIAdapter({
        p1.id: SCPAIAdapter(difficulty=difficulty, pilot=p1_pilot),
        p2.id: SCPAIAdapter(difficulty=difficulty, pilot=p2_pilot),
    }))
    await game.start_game()

    for _ in range(max_turns * 2):
        if game.is_game_over():
            break
        await game.run_turn()

    winner_id = game.get_winner()
    winner_deck = None
    loser_deck = None
    if winner_id == p1.id:
        winner_deck = p1_deck_name
        loser_deck = p2_deck_name
    elif winner_id == p2.id:
        winner_deck = p2_deck_name
        loser_deck = p1_deck_name

    return SCPGameOutcome(
        p1_deck=p1_deck_name,
        p2_deck=p2_deck_name,
        p1_pilot=p1_pilot,
        p2_pilot=p2_pilot,
        winner_deck=winner_deck,
        loser_deck=loser_deck,
        winner_reason=_winner_reason(game, winner_id),
        turns=int(game.turn_manager.turn_number),
        duration_s=round(time.perf_counter() - started, 4),
        p1_site=dict(game.state.scp_sites[p1.id]),
        p2_site=dict(game.state.scp_sites[p2.id]),
    )


async def run_tournament(
    *,
    games_per_pair: int,
    max_turns: int,
    difficulty: str,
    pilots: list[str],
    cross_pilots: bool,
    seed: int,
    decks: list[str] | None = None,
) -> list[SCPGameOutcome]:
    pilots = [validate_scp_pilot(pilot) for pilot in pilots]
    decks = decks or list(SCP_STARTER_DECKS.keys())
    outcomes: list[SCPGameOutcome] = []
    index = 0
    for i, deck_a in enumerate(decks):
        for deck_b in decks[i + 1:]:
            pilot_pairs = [(pilot, pilot) for pilot in pilots]
            if cross_pilots:
                pilot_pairs = [(left, right) for left in pilots for right in pilots]
            for p1_pilot, p2_pilot in pilot_pairs:
                for game_index in range(games_per_pair):
                    p1, p2 = (deck_a, deck_b) if index % 2 == 0 else (deck_b, deck_a)
                    try:
                        outcome = await run_one_game(
                            p1,
                            p2,
                            seed=seed + index,
                            max_turns=max_turns,
                            difficulty=difficulty,
                            p1_pilot=p1_pilot,
                            p2_pilot=p2_pilot,
                        )
                    except Exception as exc:  # pylint: disable=broad-except
                        outcome = SCPGameOutcome(
                            p1_deck=p1,
                            p2_deck=p2,
                            p1_pilot=p1_pilot,
                            p2_pilot=p2_pilot,
                            winner_deck=None,
                            loser_deck=None,
                            winner_reason="error",
                            turns=0,
                            duration_s=0.0,
                            p1_site={},
                            p2_site={},
                            error=f"{type(exc).__name__}: {exc}",
                        )
                    outcomes.append(outcome)
                    index += 1
    return outcomes


def aggregate(outcomes: list[SCPGameOutcome], *, decks: list[str] | None = None) -> dict[str, Any]:
    decks = decks or list(SCP_STARTER_DECKS.keys())
    wins = defaultdict(int)
    games = defaultdict(int)
    pair_games = defaultdict(lambda: defaultdict(int))
    pair_wins = defaultdict(lambda: defaultdict(int))
    reasons = defaultdict(int)
    pilot_games = defaultdict(int)
    pilot_wins = defaultdict(int)
    total_turns = 0
    finished = 0
    errors = 0

    for outcome in outcomes:
        games[outcome.p1_deck] += 1
        games[outcome.p2_deck] += 1
        pair_games[outcome.p1_deck][outcome.p2_deck] += 1
        pair_games[outcome.p2_deck][outcome.p1_deck] += 1
        reasons[outcome.winner_reason] += 1
        pilot_games[outcome.p1_pilot] += 1
        pilot_games[outcome.p2_pilot] += 1
        total_turns += outcome.turns
        if outcome.error:
            errors += 1
        if outcome.winner_deck:
            finished += 1
            wins[outcome.winner_deck] += 1
            loser = outcome.loser_deck or (outcome.p2_deck if outcome.winner_deck == outcome.p1_deck else outcome.p1_deck)
            pair_wins[outcome.winner_deck][loser] += 1
            if outcome.winner_deck == outcome.p1_deck:
                pilot_wins[outcome.p1_pilot] += 1
            elif outcome.winner_deck == outcome.p2_deck:
                pilot_wins[outcome.p2_pilot] += 1

    matrix: dict[str, dict[str, Optional[float]]] = {}
    for a in decks:
        matrix[a] = {}
        for b in decks:
            if a == b:
                matrix[a][b] = None
                continue
            n = pair_games[a][b]
            matrix[a][b] = round(pair_wins[a][b] / n, 3) if n else 0.0

    summary = {
        deck: {
            "games": games[deck],
            "wins": wins[deck],
            "winrate": round(wins[deck] / games[deck], 3) if games[deck] else 0.0,
        }
        for deck in decks
    }
    balance_flags = {
        deck: {
            "winrate": data["winrate"],
            "status": "too_high" if data["winrate"] > 0.65 else ("too_low" if data["winrate"] < 0.35 else "in_band"),
        }
        for deck, data in summary.items()
    }
    return {
        "schema_version": "hyperdraft.scp_tournament.v1",
        "total_games": len(outcomes),
        "finished_games": finished,
        "draws_or_timeouts": len(outcomes) - finished - errors,
        "errors": errors,
        "average_turns": round(total_turns / len(outcomes), 2) if outcomes else 0.0,
        "winner_reasons": dict(sorted(reasons.items())),
        "set_summary": summary,
        "pilot_summary": {
            pilot: {
                "games": pilot_games[pilot],
                "wins": pilot_wins[pilot],
                "winrate": round(pilot_wins[pilot] / pilot_games[pilot], 3) if pilot_games[pilot] else 0.0,
            }
            for pilot in sorted(pilot_games)
        },
        "target_winrate_band": [0.35, 0.65],
        "balance_flags": balance_flags,
        "matchup_matrix": matrix,
        "outcomes": [asdict(outcome) for outcome in outcomes],
    }


def _json_default(o):
    """Coerce non-JSON values for ``--out`` (e.g. a set nested in a site dict in
    some late-game states — a pre-existing serialization gap, not specific to any
    deck). Sets become sorted lists; anything else falls back to its string."""
    if isinstance(o, (set, frozenset)):
        return sorted(o, key=str)
    return str(o)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=12, help="Games per unordered pair")
    parser.add_argument("--max-turns", type=int, default=40, help="Full turns per game before timeout")
    parser.add_argument("--difficulty", default="medium")
    parser.add_argument("--pilots", default="balanced", help="Comma-separated SCP heuristic pilots")
    parser.add_argument("--cross-pilots", action="store_true", help="Run every pilot pairing instead of same-pilot mirrors")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--decks", default="", help="Comma-separated deck ids; defaults to every SCP starter deck")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    pilots = [pilot.strip() for pilot in args.pilots.split(",") if pilot.strip()]
    if not pilots:
        pilots = ["balanced"]
    try:
        pilots = [validate_scp_pilot(pilot) for pilot in pilots]
    except ValueError:
        supported = ", ".join(sorted(SUPPORTED_SCP_PILOTS))
        unknown_pilots = [pilot for pilot in pilots if pilot.strip().lower() not in SUPPORTED_SCP_PILOTS]
        raise SystemExit(
            f"Unknown SCP pilot name(s): {', '.join(unknown_pilots)}. "
            f"Supported pilots: {supported}"
        ) from None
    decks = [deck.strip() for deck in args.decks.split(",") if deck.strip()]
    unknown = [deck for deck in decks if deck not in SCP_STARTER_DECKS]
    if unknown:
        raise SystemExit(f"Unknown SCP deck id(s): {', '.join(unknown)}")
    selected_decks = list(dict.fromkeys(decks)) if decks else None
    tournament_decks = selected_decks or list(SCP_STARTER_DECKS)
    if len(tournament_decks) < 2:
        selected = ", ".join(tournament_decks) if tournament_decks else "none"
        raise SystemExit(
            "At least two SCP deck ids are required after filtering; "
            f"got {len(tournament_decks)} ({selected})."
        )
    outcomes = asyncio.run(run_tournament(
        games_per_pair=args.games,
        max_turns=args.max_turns,
        difficulty=args.difficulty,
        pilots=pilots,
        cross_pilots=args.cross_pilots,
        seed=args.seed,
        decks=selected_decks,
    ))
    report = aggregate(outcomes, decks=selected_decks)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, default=_json_default), encoding="utf-8")

    print(json.dumps({
        "total_games": report["total_games"],
        "finished_games": report["finished_games"],
        "draws_or_timeouts": report["draws_or_timeouts"],
        "errors": report["errors"],
        "average_turns": report["average_turns"],
        "winner_reasons": report["winner_reasons"],
        "set_summary": report["set_summary"],
        "pilot_summary": report["pilot_summary"],
        "target_winrate_band": report["target_winrate_band"],
        "balance_flags": report["balance_flags"],
        "matchup_matrix": report["matchup_matrix"],
    }, indent=2))


if __name__ == "__main__":
    main()
