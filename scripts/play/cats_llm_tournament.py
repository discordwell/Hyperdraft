"""Cats — LLM vs LLM round-robin tournament.

Both seats are Claude (via `claude -p` shellout through CatsLLMAdapter).
Each pairing plays N seat-balanced games (alternating who's p1 vs p2).

Time budget: each game makes ~30+ `claude -p` calls. At ~5s per call on
haiku, a 9-round game is 3-5 minutes. Default 12-game tournament =
~45-90 minutes wall time.

Usage:
    python scripts/play/cats_llm_tournament.py
    python scripts/play/cats_llm_tournament.py --model sonnet --games-per-pairing 1
    python scripts/play/cats_llm_tournament.py --output cats_llm_results.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

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


@dataclass
class GameRecord:
    deck_a: str
    deck_b: str
    p1_seat: str  # "a" or "b"
    seed: int
    winner: str  # "p1" / "p2" / "tie"
    final_scores: dict
    rounds_played: int
    wall_time_s: float
    llm_decisions: int
    notes: list[dict] = field(default_factory=list)  # captured reasoning summaries


def _run_one_round(state: GameState, ai_p1: CatsLLMAdapter, ai_p2: CatsLLMAdapter) -> bool:
    """Drive one round; returns False if a hand emptied mid-round."""
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

    resolve_trick(state)

    winner_id = state.cats_current_trick.get("winner")
    if winner_id is None:
        end_round(state)
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
    claim_pile(state, winner_id, pile_choice)
    end_round(state)
    return True


def play_one_game(
    deck_a_name: str,
    deck_b_name: str,
    p1_is_a: bool,
    seed: int,
    model: str,
    verbose: bool = False,
) -> GameRecord:
    """Play a single LLM-vs-LLM game. p1_is_a controls seat assignment."""
    a_cmd, a_deck = CATS_DECKS[deck_a_name]
    b_cmd, b_deck = CATS_DECKS[deck_b_name]

    if p1_is_a:
        p1_name, p1_cmd, p1_deck = deck_a_name, a_cmd, a_deck
        p2_name, p2_cmd, p2_deck = deck_b_name, b_cmd, b_deck
    else:
        p1_name, p1_cmd, p1_deck = deck_b_name, b_cmd, b_deck
        p2_name, p2_cmd, p2_deck = deck_a_name, a_cmd, a_deck

    state = GameState()
    state.game_mode = "cats"
    state.rng_seed = seed
    state.players["p1"] = Player(id="p1", name=f"LLM-p1-{p1_name}")
    state.players["p2"] = Player(id="p2", name=f"LLM-p2-{p2_name}")
    setup_cats_player(state, "p1", list(p1_deck), commander=p1_cmd)
    setup_cats_player(state, "p2", list(p2_deck), commander=p2_cmd)

    ai_p1 = CatsLLMAdapter(model=model, verbose=verbose)
    ai_p1.player_id = "p1"
    ai_p2 = CatsLLMAdapter(model=model, verbose=verbose)
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

    winners = state.cats_winners or []
    if len(winners) == 1:
        winner = winners[0]
    else:
        winner = "tie"

    return GameRecord(
        deck_a=deck_a_name,
        deck_b=deck_b_name,
        p1_seat="a" if p1_is_a else "b",
        seed=seed,
        winner=winner,
        final_scores=state.cats_final_scores,
        rounds_played=rounds_played,
        wall_time_s=elapsed,
        llm_decisions=len(ai_p1.decisions) + len(ai_p2.decisions),
        notes=[
            *[{"seat": "p1", **d} for d in ai_p1.decisions[:8]],  # first 8 decisions
            *[{"seat": "p2", **d} for d in ai_p2.decisions[:8]],
        ],
    )


def run_tournament(games_per_pairing: int, model: str, seed_base: int, verbose: bool, output: Path | None):
    """Round-robin LLM-vs-LLM. Each pairing plays N games seat-balanced."""
    deck_names = list(CATS_DECKS.keys())
    pairings = []
    for i, a in enumerate(deck_names):
        for b in deck_names[i + 1:]:
            pairings.append((a, b))

    total_games = len(pairings) * games_per_pairing
    print(f"\n{'='*72}")
    print(f"CATS — LLM vs LLM tournament")
    print(f"  Model: {model}")
    print(f"  Decks: {deck_names}")
    print(f"  Pairings: {len(pairings)} × {games_per_pairing} games = {total_games} total")
    print(f"  Estimated wall time: {total_games * 5:.0f}-{total_games * 8:.0f} minutes")
    print(f"{'='*72}\n")

    all_games: list[GameRecord] = []
    wins: dict[str, int] = {n: 0 for n in deck_names}
    losses: dict[str, int] = {n: 0 for n in deck_names}
    ties: dict[str, int] = {n: 0 for n in deck_names}

    game_idx = 0
    t_start = time.time()
    for (a, b) in pairings:
        print(f"\n--- {a} vs {b} ---")
        for g in range(games_per_pairing):
            game_idx += 1
            p1_is_a = (g % 2 == 0)
            seed = seed_base + game_idx * 1000
            t0 = time.time()
            print(f"  [{game_idx}/{total_games}] seed={seed}, p1={'A:'+a if p1_is_a else 'B:'+b} ... ", end="", flush=True)
            rec = play_one_game(a, b, p1_is_a, seed, model, verbose=False)
            elapsed = time.time() - t0
            # Decode winner
            if rec.winner == "tie":
                ties[a] += 1
                ties[b] += 1
                result_label = "tie"
            else:
                winner_deck = (a if (rec.winner == "p1") == p1_is_a else b)
                loser_deck = b if winner_deck == a else a
                wins[winner_deck] += 1
                losses[loser_deck] += 1
                result_label = f"{winner_deck} wins"
            scores = rec.final_scores
            p1_total = scores.get("p1", {}).get("total", 0)
            p2_total = scores.get("p2", {}).get("total", 0)
            print(f"{result_label}  ({p1_total}-{p2_total}, {rec.rounds_played}r, {elapsed:.0f}s)")
            all_games.append(rec)

    total_elapsed = time.time() - t_start
    print(f"\n{'='*72}")
    print(f"Tournament complete in {total_elapsed/60:.1f} minutes")
    print(f"{'='*72}")
    print(f"{'Deck':<22} | {'W':>3} {'L':>3} {'T':>3} | {'Win%':>6}")
    print("-" * 72)
    for n in deck_names:
        total_games_for_deck = wins[n] + losses[n] + ties[n]
        wr = (wins[n] + 0.5 * ties[n]) / max(total_games_for_deck, 1) * 100
        print(f"{n:<22} | {wins[n]:>3} {losses[n]:>3} {ties[n]:>3} | {wr:>5.1f}%")

    if output:
        payload = {
            "model": model,
            "games_per_pairing": games_per_pairing,
            "total_games": total_games,
            "wall_time_s": total_elapsed,
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "games": [
                {
                    "deck_a": g.deck_a,
                    "deck_b": g.deck_b,
                    "p1_seat": g.p1_seat,
                    "seed": g.seed,
                    "winner": g.winner,
                    "rounds": g.rounds_played,
                    "wall_time_s": g.wall_time_s,
                    "scores": g.final_scores,
                    "llm_decisions": g.llm_decisions,
                    "notes": g.notes,
                }
                for g in all_games
            ],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, default=str))
        print(f"\nResults saved to {output}")


def main():
    parser = argparse.ArgumentParser(description="Cats LLM-vs-LLM tournament")
    parser.add_argument("--model", default="haiku", help="Claude model alias (haiku/sonnet/opus)")
    parser.add_argument("--games-per-pairing", "-n", type=int, default=2, help="Games per matchup (default 2 — seat-balanced)")
    parser.add_argument("--seed-base", type=int, default=12345, help="Base seed (each game += game_idx * 1000)")
    parser.add_argument("--output", "-o", type=Path, default=Path("artifacts/cats_llm_tournament.json"), help="JSON results path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print every LLM decision")
    args = parser.parse_args()
    run_tournament(args.games_per_pairing, args.model, args.seed_base, args.verbose, args.output)


if __name__ == "__main__":
    main()
