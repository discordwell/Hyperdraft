"""CATS — Archetype tournament runner.

Round-robin tournament between the four archetype decks in
`src.cards.cats.CATS.decks`. Each pairing plays `GAMES_PER_PAIRING` games
(seat-balanced — half with deck A as p1, half as p2). Two `CatsAIAdapter("hard")`
agents drive both players via the same manual-round helper used by
`tests/test_cats_first_set.py`.

Usage
-----
    python scripts/play/cats_tournament.py
        # → prints win-rate matrix & per-deck record over GAMES_PER_PAIRING games.

    from scripts.play.cats_tournament import run_tournament
    results = run_tournament(games_per_pairing=10)

Output format:
    {(deck_a, deck_b): {deck_a: wins, deck_b: wins, "ties": int}}
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Make repo root importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ai.cats_adapter import CatsAIAdapter
from src.cards.cats.CATS.decks import CATS_DECKS
from src.engine.cats import (
    CATS_TOTAL_ROUNDS,
    begin_round,
    check_game_over,
    claim_pile,
    end_round,
    finalize_game,
    play_card_to_trick,
    resolve_trick,
    setup_cats_player,
)
from src.engine.types import EventType, GameState, Player


# ---------------------------------------------------------------------------
# Verbose-mode event tracer
# ---------------------------------------------------------------------------

@dataclass
class TrickTrace:
    """Per-game accumulator for interceptor-activity counts.

    Counts the structured events emitted by the engine each round:
      - ``on_win`` phase of ``CATS_TRICK_RESOLVE`` — one per winning card
      - ``on_enter_pile`` phase of ``CATS_CLAIM_PILE`` — one per card entering
      - distinct REACT follow-up events emitted *because* a card's
        ``setup_interceptors`` filtered+handled an ``on_enter_pile`` event
        (these signal that wired interceptors actually fired, not just that
        the engine emitted the phase event).

    A REACT follow-up is anything emitted by ``claim_pile`` after the
    per-card on_enter_pile event for the same card-id. We tag each by the
    source card_id so we can count *distinct* on_enter triggers fired.
    """

    rounds: int = 0
    trick_wins: int = 0          # count of phase=on_win CATS_TRICK_RESOLVE
    pile_entries: int = 0        # count of phase=on_enter_pile CATS_CLAIM_PILE
    distinct_on_enter_sources: set[str] = field(default_factory=set)
    # Per-card wins, keyed by card name (resolved at observation time).
    win_per_card: dict[str, int] = field(default_factory=dict)

    def observe_resolve(self, state: GameState, events: list) -> None:
        """Walk events from ``resolve_trick`` and count on-win triggers."""
        for ev in events or []:
            if ev.type != EventType.CATS_TRICK_RESOLVE:
                continue
            phase = ev.payload.get("phase") if hasattr(ev, "payload") and ev.payload else None
            if phase != "on_win":
                continue
            self.trick_wins += 1
            cid = ev.payload.get("card_id")
            name = None
            if cid:
                obj = state.objects.get(cid)
                if obj is not None:
                    name = obj.name
            key = name or (cid or "<unknown>")
            self.win_per_card[key] = self.win_per_card.get(key, 0) + 1

    def observe_claim(self, state: GameState, events: list) -> None:
        """Walk events from ``claim_pile`` and count pile-entry triggers.

        Distinct-trigger count: claim_pile emits two CATS_CLAIM_PILE events
        per card (the base + the on_enter_pile phase). The REACT dispatcher
        then appends *additional* events emitted by card interceptors. A
        card whose setup_interceptors handler returned ``new_events`` will
        therefore push one or more non-CATS_CLAIM_PILE follow-up events with
        ``source = card_id``. We treat those follow-ups as evidence the
        on_enter trigger fired.
        """
        on_enter_card_ids: set[str] = set()
        for ev in events or []:
            payload = getattr(ev, "payload", None) or {}
            if ev.type == EventType.CATS_CLAIM_PILE and payload.get("phase") == "on_enter_pile":
                self.pile_entries += 1
                cid = payload.get("card_id")
                if cid:
                    on_enter_card_ids.add(cid)
                continue
            # Follow-up REACT event whose source is one of the cards that
            # just entered a pile → an on_enter trigger fired.
            src = getattr(ev, "source", None)
            if src and src in on_enter_card_ids:
                self.distinct_on_enter_sources.add(src)

    def distinct_on_enter_count(self) -> int:
        return len(self.distinct_on_enter_sources)


# ---------------------------------------------------------------------------
# Round driver — extracted/duplicated from tests/test_cats_first_set.py
# (deliberately self-contained so this script doesn't import a test file).
# ---------------------------------------------------------------------------

def _run_one_round_manual(
    state: GameState,
    ai_p1: CatsAIAdapter,
    ai_p2: CatsAIAdapter,
    trace: Optional["TrickTrace"] = None,
) -> bool:
    """Drive one round: begin → pounce → counter → resolve → claim → end.

    Returns True if the round completed normally, False if a hand was empty
    at a point the round needed it (which we treat as a no-op exit).

    If ``trace`` is provided, accumulates per-game counts of on_win
    CATS_TRICK_RESOLVE events and on_enter_pile CATS_CLAIM_PILE events.
    """
    begin_round(state)
    lead = getattr(state, "cats_lead_player", None) or "p1"
    follower = "p2" if lead == "p1" else "p1"

    hand_zone = state.zones.get(f"HAND_{follower}")
    if hand_zone is None or not hand_zone.objects:
        return False
    ai_follower = ai_p1 if follower == "p1" else ai_p2
    pounce_card = ai_follower.choose_card(state, list(hand_zone.objects))
    play_card_to_trick(state, follower, pounce_card, role="pounce")

    hand_zone2 = state.zones.get(f"HAND_{lead}")
    if hand_zone2 is None or not hand_zone2.objects:
        return False
    ai_lead = ai_p1 if lead == "p1" else ai_p2
    counter_card = ai_lead.choose_card(state, list(hand_zone2.objects))
    play_card_to_trick(state, lead, counter_card, role="counter")

    resolve_events = resolve_trick(state)
    if trace is not None:
        trace.observe_resolve(state, resolve_events)

    winner_id = state.cats_current_trick.get("winner")
    if winner_id is None:
        # Edge case: no winner declared. End the round anyway so we don't loop.
        end_round(state)
        if trace is not None:
            trace.rounds += 1
        return True

    ai_winner = ai_p1 if winner_id == "p1" else ai_p2
    available_piles = ["pile_territory", "pile_nap", "pile_snack"]
    won_cards = [
        c for c in (
            state.cats_current_trick.get("pounce_card"),
            state.cats_current_trick.get("counter_card"),
        ) if c
    ]
    pile_choice = ai_winner.choose_pile(state, won_cards, available_piles)
    claim_events = claim_pile(state, winner_id, pile_choice)
    if trace is not None:
        trace.observe_claim(state, claim_events)

    end_round(state)
    if trace is not None:
        trace.rounds += 1
    return True


# ---------------------------------------------------------------------------
# Game runner
# ---------------------------------------------------------------------------

def _build_state(
    seed: int,
    p1_commander, p1_deck,
    p2_commander, p2_deck,
) -> GameState:
    """Build a fresh 2-player Cats state with given commanders + decks."""
    state = GameState()
    state.game_mode = "cats"
    state.rng_seed = seed
    state.players["p1"] = Player(id="p1", name="P1")
    state.players["p2"] = Player(id="p2", name="P2")
    # Pass a fresh list copy — setup_cats_player shuffles in place.
    setup_cats_player(state, "p1", list(p1_deck), commander=p1_commander)
    setup_cats_player(state, "p2", list(p2_deck), commander=p2_commander)
    return state


def _play_one_game(
    seed: int,
    p1_commander, p1_deck,
    p2_commander, p2_deck,
    difficulty: str = "hard",
    trace: Optional[TrickTrace] = None,
    p2_difficulty: Optional[str] = None,
) -> tuple[str, dict]:
    """Play a full game; return (winner_seat, scores).

    winner_seat ∈ {"p1", "p2", "tie"}.

    If ``trace`` is supplied, it is populated with per-game event counts.
    ``p2_difficulty`` defaults to ``difficulty`` — set differently to run
    asymmetric matchups (e.g. hard vs medium).
    """
    state = _build_state(seed, p1_commander, p1_deck, p2_commander, p2_deck)
    ai_p1 = CatsAIAdapter(difficulty); ai_p1.player_id = "p1"
    ai_p2 = CatsAIAdapter(p2_difficulty or difficulty); ai_p2.player_id = "p2"

    rounds_played = 0
    max_rounds = CATS_TOTAL_ROUNDS * 3   # safety budget
    while not check_game_over(state) and rounds_played < max_rounds:
        ok = _run_one_round_manual(state, ai_p1, ai_p2, trace=trace)
        rounds_played += 1
        if not ok:
            break

    finalize_game(state)
    scores = state.cats_final_scores
    winners = state.cats_winners or []
    if len(winners) == 1:
        return winners[0], scores
    return "tie", scores


# ---------------------------------------------------------------------------
# Match / tournament API
# ---------------------------------------------------------------------------

def run_match(
    deck_a_name: str,
    deck_b_name: str,
    n_games: int = 10,
    seed_offset: int = 0,
    difficulty: str = "hard",
    verbose: bool = False,
    p2_difficulty: Optional[str] = None,
) -> dict:
    """Play n_games between two decks; half with A as p1, half as p2.

    Returns {deck_a_name: wins, deck_b_name: wins, "ties": int}.
    If verbose=True, additionally prints one ``Game N: …`` line per game
    summarising trick / pile-entry / distinct-trigger counts.
    """
    cmd_a, deck_a = CATS_DECKS[deck_a_name]
    cmd_b, deck_b = CATS_DECKS[deck_b_name]
    result = {deck_a_name: 0, deck_b_name: 0, "ties": 0}

    for i in range(n_games):
        seed = seed_offset + 1000 * i + 7
        # Alternate seats so neither deck always leads first.
        trace = TrickTrace() if verbose else None
        if i % 2 == 0:
            winner_seat, _ = _play_one_game(
                seed, cmd_a, deck_a, cmd_b, deck_b, difficulty,
                trace=trace, p2_difficulty=p2_difficulty,
            )
            p1_name, p2_name = deck_a_name, deck_b_name
            if winner_seat == "p1":
                result[deck_a_name] += 1
            elif winner_seat == "p2":
                result[deck_b_name] += 1
            else:
                result["ties"] += 1
        else:
            winner_seat, _ = _play_one_game(
                seed, cmd_b, deck_b, cmd_a, deck_a, difficulty,
                trace=trace, p2_difficulty=p2_difficulty,
            )
            p1_name, p2_name = deck_b_name, deck_a_name
            if winner_seat == "p1":
                result[deck_b_name] += 1
            elif winner_seat == "p2":
                result[deck_a_name] += 1
            else:
                result["ties"] += 1
        if verbose and trace is not None:
            print(
                f"Game {i + 1} ({p1_name} vs {p2_name}): "
                f"{trace.rounds} rounds, "
                f"{trace.trick_wins} trick wins, "
                f"{trace.pile_entries} pile-entries, "
                f"{trace.distinct_on_enter_count()} distinct on_enter triggers fired"
            )

    return result


def run_tournament(
    decks: dict | None = None,
    games_per_pairing: int = 10,
    difficulty: str = "hard",
    verbose: bool = False,
    p2_difficulty: Optional[str] = None,
) -> dict:
    """Round-robin tournament.

    Returns {(deck_a, deck_b): match_result_dict}.
    """
    decks = decks or CATS_DECKS
    deck_names = list(decks.keys())
    results: dict = {}
    for i, a in enumerate(deck_names):
        for b in deck_names[i + 1:]:
            if verbose:
                print(f"--- {a} vs {b} ---")
            results[(a, b)] = run_match(
                a, b,
                n_games=games_per_pairing,
                difficulty=difficulty,
                verbose=verbose,
                p2_difficulty=p2_difficulty,
            )
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _format_results(results: dict, decks: dict) -> str:
    """Format tournament results into a readable text table."""
    deck_names = list(decks.keys())
    lines: list[str] = []
    # Per-deck aggregate
    totals = {n: {"wins": 0, "losses": 0, "ties": 0, "games": 0} for n in deck_names}
    for (a, b), r in results.items():
        a_w = r[a]; b_w = r[b]; t = r["ties"]
        games = a_w + b_w + t
        totals[a]["wins"]   += a_w
        totals[a]["losses"] += b_w
        totals[a]["ties"]   += t
        totals[a]["games"]  += games
        totals[b]["wins"]   += b_w
        totals[b]["losses"] += a_w
        totals[b]["ties"]   += t
        totals[b]["games"]  += games

    # Pairing detail
    lines.append("=" * 72)
    lines.append("Pairing results")
    lines.append("=" * 72)
    lines.append(f"{'Match':<46} | {'A':>3} {'B':>3} {'Tie':>3}")
    lines.append("-" * 72)
    for (a, b), r in results.items():
        lines.append(
            f"{a + ' vs ' + b:<46} | {r[a]:>3} {r[b]:>3} {r['ties']:>3}"
        )

    # Summary
    lines.append("")
    lines.append("=" * 72)
    lines.append("Per-deck record")
    lines.append("=" * 72)
    lines.append(f"{'Deck':<22} | {'W':>3} {'L':>3} {'T':>3} {'Games':>5} | {'Win%':>6}")
    lines.append("-" * 72)
    summary: list[tuple[str, float]] = []
    for name in deck_names:
        t = totals[name]
        wr = (t["wins"] + 0.5 * t["ties"]) / max(t["games"], 1) * 100
        summary.append((name, wr))
        lines.append(
            f"{name:<22} | {t['wins']:>3} {t['losses']:>3} {t['ties']:>3} "
            f"{t['games']:>5} | {wr:>5.1f}%"
        )

    # Balance verdict
    lines.append("")
    lines.append("=" * 72)
    lines.append("Balance verdict")
    lines.append("=" * 72)
    out_of_range = [(n, wr) for n, wr in summary if wr < 35.0 or wr > 60.0]
    if out_of_range:
        lines.append("OUT OF TARGET 35-60% range:")
        for n, wr in out_of_range:
            lines.append(f"  - {n}: {wr:.1f}%")
    else:
        lines.append("All decks within 35-60% target range.")
    return "\n".join(lines)


def _build_argparser() -> argparse.ArgumentParser:
    """CLI flags. Verbose mode prints one Game-N summary per game played."""
    parser = argparse.ArgumentParser(description="CATS — round-robin tournament runner")
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print per-game trick / pile-entry / distinct-trigger counts.",
    )
    parser.add_argument(
        "--games-per-pairing", "-n",
        type=int,
        default=10,
        help="Games per archetype pairing (default 10).",
    )
    parser.add_argument(
        "--difficulty", "-d",
        choices=("easy", "medium", "hard"),
        default="hard",
        help="AI difficulty (applies to both seats).",
    )
    parser.add_argument(
        "--p2-difficulty",
        choices=("easy", "medium", "hard"),
        default=None,
        help="Optional override for p2 only (asymmetric matchup, e.g. hard vs medium).",
    )
    return parser


if __name__ == "__main__":
    args = _build_argparser().parse_args()
    print(
        f"Running CATS round-robin tournament "
        f"({args.games_per_pairing} games per pairing, difficulty={args.difficulty}"
        + (f", p2={args.p2_difficulty}" if args.p2_difficulty else "")
        + ")..."
    )
    print(f"  Decks: {list(CATS_DECKS.keys())}")
    print()
    results = run_tournament(
        games_per_pairing=args.games_per_pairing,
        difficulty=args.difficulty,
        verbose=args.verbose,
        p2_difficulty=args.p2_difficulty,
    )
    if args.verbose:
        print()
    print(_format_results(results, CATS_DECKS))
