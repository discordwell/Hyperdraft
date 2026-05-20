"""Cats — LLM vs heuristic demo.

Plays one 9-round game with:
  - p1: CatsLLMAdapter (Claude via `claude -p`)
  - p2: CatsAIAdapter("medium")  (the existing heuristic)

Both AIs' decisions are printed in plain English with their reasoning. At the
end the final scores and winner are reported.

This script will make ~30+ subprocess calls to `claude -p` (one per LLM
decision). Expect 3-8s per call → a single demo run takes 3-8 minutes. It
consumes your Claude Code session quota.

Usage
-----
    python scripts/play/cats_llm_demo.py
    python scripts/play/cats_llm_demo.py --model sonnet
    python scripts/play/cats_llm_demo.py --p1-deck "Snack Rush" --p2-deck "Couch Empire"

The driver is a copy of ``_run_one_round_manual`` from
``scripts/play/cats_tournament.py`` adapted to accept pre-built adapter
instances (rather than constructing them by difficulty string).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Make repo root importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ai.cats_adapter import CatsAIAdapter
from src.ai.cats_llm_adapter import CatsLLMAdapter
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
from src.engine.types import GameState, Player


# ---------------------------------------------------------------------------
# Round driver — copy of cats_tournament._run_one_round_manual but takes
# pre-built adapters (so we can mix an LLM with a heuristic).
# ---------------------------------------------------------------------------

def _run_one_round(state: GameState, ai_p1, ai_p2) -> bool:
    """Drive one round; returns True if it ran, False if a hand emptied."""
    begin_round(state)
    lead = getattr(state, "cats_lead_player", None) or "p1"
    follower = "p2" if lead == "p1" else "p1"

    hand_zone = state.zones.get(f"HAND_{follower}")
    if hand_zone is None or not hand_zone.objects:
        return False
    ai_follower = ai_p1 if follower == "p1" else ai_p2
    print(f"\n--- Round {state.cats_round_number}: lead={lead}, follower={follower} ---")
    print(f"  [Pounce phase: {follower} plays first]")
    pounce_card = ai_follower.choose_card(state, list(hand_zone.objects))
    play_card_to_trick(state, follower, pounce_card, role="pounce")

    hand_zone2 = state.zones.get(f"HAND_{lead}")
    if hand_zone2 is None or not hand_zone2.objects:
        return False
    ai_lead = ai_p1 if lead == "p1" else ai_p2
    print(f"  [Counter-pounce phase: {lead} reacts]")
    counter_card = ai_lead.choose_card(state, list(hand_zone2.objects))
    play_card_to_trick(state, lead, counter_card, role="counter")

    resolve_trick(state)

    winner_id = state.cats_current_trick.get("winner")
    if winner_id is None:
        end_round(state)
        return True

    winner_name = "LLM" if winner_id == "p1" else "heuristic"
    print(f"  Trick winner: {winner_id} ({winner_name})")

    ai_winner = ai_p1 if winner_id == "p1" else ai_p2
    available_piles = ["pile_territory", "pile_nap", "pile_snack"]
    won_cards = [
        c for c in (
            state.cats_current_trick.get("pounce_card"),
            state.cats_current_trick.get("counter_card"),
        ) if c
    ]
    pile_choice = ai_winner.choose_pile(state, won_cards, available_piles)
    claim_pile(state, winner_id, pile_choice)

    end_round(state)
    return True


# ---------------------------------------------------------------------------
# Game runner
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Cats LLM-vs-heuristic demo")
    parser.add_argument(
        "--p1-deck",
        default="Couch Empire",
        choices=list(CATS_DECKS.keys()),
        help="Deck for the LLM seat (p1).",
    )
    parser.add_argument(
        "--p2-deck",
        default="Naptime Tyrants",
        choices=list(CATS_DECKS.keys()),
        help="Deck for the heuristic seat (p2).",
    )
    parser.add_argument(
        "--model",
        default="haiku",
        help="Claude model alias passed to `claude --model` (e.g. haiku, sonnet, opus).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deck-shuffle seed.",
    )
    parser.add_argument(
        "--p2-difficulty",
        default="medium",
        choices=("easy", "medium", "hard"),
        help="Heuristic difficulty for p2.",
    )
    args = parser.parse_args()

    p1_cmd, p1_deck = CATS_DECKS[args.p1_deck]
    p2_cmd, p2_deck = CATS_DECKS[args.p2_deck]

    print("=" * 72)
    print(f"CATS LLM demo")
    print(f"  p1 (LLM, model={args.model}): {args.p1_deck} (commander: {p1_cmd.name})")
    print(f"  p2 (heuristic {args.p2_difficulty}): {args.p2_deck} (commander: {p2_cmd.name})")
    print(f"  seed: {args.seed}")
    print("=" * 72)

    state = GameState()
    state.game_mode = "cats"
    state.rng_seed = args.seed
    state.players["p1"] = Player(id="p1", name="LLM")
    state.players["p2"] = Player(id="p2", name="Heuristic")
    setup_cats_player(state, "p1", list(p1_deck), commander=p1_cmd)
    setup_cats_player(state, "p2", list(p2_deck), commander=p2_cmd)

    ai_p1 = CatsLLMAdapter(model=args.model, verbose=True)
    ai_p1.player_id = "p1"
    ai_p2 = CatsAIAdapter(args.p2_difficulty)
    ai_p2.player_id = "p2"

    rounds_played = 0
    max_rounds = CATS_TOTAL_ROUNDS * 3
    start = time.time()
    while not check_game_over(state) and rounds_played < max_rounds:
        ok = _run_one_round(state, ai_p1, ai_p2)
        rounds_played += 1
        if not ok:
            break
    elapsed = time.time() - start

    finalize_game(state)

    print()
    print("=" * 72)
    print("Game over")
    print("=" * 72)
    print(f"  Rounds played: {rounds_played}")
    print(f"  Wall time: {elapsed:.1f}s")
    print(f"  LLM decisions made: {len(ai_p1.decisions)}")
    print()
    print("Final scores:")
    for pid, score in state.cats_final_scores.items():
        label = "LLM (p1)" if pid == "p1" else "Heuristic (p2)"
        print(f"  {label}: {score}")
    print()
    winners = state.cats_winners or []
    if len(winners) == 1:
        winner_label = "LLM (p1)" if winners[0] == "p1" else "Heuristic (p2)"
        print(f"Winner: {winner_label}")
    else:
        print(f"Result: tie ({winners})")
    print()
    print("Pile contents (final):")
    for pid in ("p1", "p2"):
        label = "LLM (p1)" if pid == "p1" else "Heuristic (p2)"
        piles = state.cats_piles.get(pid, {})
        print(f"  {label}:")
        for pile_name in ("pile_territory", "pile_nap", "pile_snack", "pile_attention"):
            cards = piles.get(pile_name, [])
            names = [state.objects[c].card_def.name if c in state.objects else "?" for c in cards]
            print(f"    {pile_name}: {names}")


if __name__ == "__main__":
    main()
