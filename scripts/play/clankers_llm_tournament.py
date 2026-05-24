"""Clankers LLM round-robin tournament.

Pairs 2 ClankersLLMAdapter seats against each other across the 4 CLAN starter
decks. Mirrors the cats_llm_tournament.py shape.

Usage
-----
    PYTHONPATH=. python scripts/play/clankers_llm_tournament.py \\
        --games-per-pair 2 --model haiku \\
        --json-out logs/clan_balance_wave5_llm.json

Outputs winrate-per-deck + full per-game decision logs to JSON.

Note: each LLM call is ~3-10 seconds and a Clankers game is ~50-150 calls. A
24-game tournament takes ~1-2 hours wall time. Scope conservatively.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ai.clankers_llm_adapter import ClankersLLMAdapter
from src.ai.clankers_adapter import ClankersAIAdapter
from src.cards.clankers.CLAN.decks import CLAN_STARTER_DECKS
from src.engine.clankers_turn import ClankersTurnManager
from src.engine.types import GameState, Player


def _run_one_game(
    deck_a_label: str,
    deck_b_label: str,
    seed: int,
    model: str,
    timeout: float,
    verbose: bool = False,
) -> dict:
    """Play one game, return {winner, loser, turns, decisions_a, decisions_b}."""
    state = GameState()
    state.rng_seed = seed
    p_a, p_b = "p1", "p2"
    state.players[p_a] = Player(id=p_a, name="P1")
    state.players[p_b] = Player(id=p_b, name="P2")

    # Build decks via the registry.
    builder_a = CLAN_STARTER_DECKS[deck_a_label]
    builder_b = CLAN_STARTER_DECKS[deck_b_label]
    core_a, deck_a = builder_a()
    core_b, deck_b = builder_b()

    state._game = None  # heuristic tournament does this; harness tolerates

    tm = ClankersTurnManager(state)

    # LLM seats — both players get an LLM adapter.
    ai_a = ClankersLLMAdapter(player_id=p_a, model=model, timeout=timeout, verbose=verbose)
    ai_b = ClankersLLMAdapter(player_id=p_b, model=model, timeout=timeout, verbose=verbose)

    # Per the heuristic tournament: set_ai_handler is the canonical API.
    tm.set_ai_handler(ai_a, p_a)
    tm.set_ai_handler(ai_b, p_b)

    tm.setup_game(deck_a, core_a, deck_b, core_b)

    # Run up to 40 turns.
    max_turns = 40
    turn = 0
    while turn < max_turns:
        active = state.active_player
        if active is None:
            break
        tm.run_turn(active)
        turn += 1
        if getattr(state, "game_over", False):
            break

    loser = getattr(state, "clankers_loser", None)
    if loser is None:
        # Tournament timeout / mutual breach — call it a draw.
        winner = None
    else:
        winner = p_a if loser == p_b else p_b

    return {
        "winner": winner,
        "loser": loser,
        "turns": turn,
        "deck_a": deck_a_label,
        "deck_b": deck_b_label,
        "seed": seed,
        "decisions_a": len(ai_a.decisions),
        "decisions_b": len(ai_b.decisions),
    }


def run_tournament(
    decks: list[str],
    games_per_pair: int = 2,
    seed_base: int = 42,
    model: str = "haiku",
    timeout: float = 60.0,
    verbose: bool = False,
) -> dict:
    """Round-robin among `decks`. games_per_pair per unordered pair, half each seat."""
    deck_list = [d for d in decks if d in CLAN_STARTER_DECKS]
    if not deck_list:
        raise ValueError(f"No valid decks from {decks}. Available: {list(CLAN_STARTER_DECKS)}")

    pairs: list[tuple[str, str]] = []
    for i in range(len(deck_list)):
        for j in range(i + 1, len(deck_list)):
            pairs.append((deck_list[i], deck_list[j]))

    results: list[dict] = []
    wins: dict[str, int] = {d: 0 for d in deck_list}
    games_played: dict[str, int] = {d: 0 for d in deck_list}

    total_games = len(pairs) * games_per_pair
    print(f"=== Clankers LLM tournament ===")
    print(f"Decks: {deck_list}")
    print(f"Pairs: {len(pairs)}, games per pair: {games_per_pair}")
    print(f"Total games: {total_games}, model: {model}")
    t0 = time.time()
    g = 0
    for pair_idx, (a, b) in enumerate(pairs):
        for k in range(games_per_pair):
            # Half as a-then-b seat, half reversed.
            if k % 2 == 0:
                deck_p1, deck_p2 = a, b
            else:
                deck_p1, deck_p2 = b, a
            seed = seed_base + pair_idx * 100 + k
            print(f"  [{g+1}/{total_games}] {deck_p1} vs {deck_p2} (seed {seed})", flush=True)
            try:
                game_result = _run_one_game(deck_p1, deck_p2, seed, model, timeout, verbose)
                results.append(game_result)
                games_played[a] += 1
                games_played[b] += 1
                winner = game_result["winner"]
                if winner == "p1":
                    wins[deck_p1] += 1
                elif winner == "p2":
                    wins[deck_p2] += 1
                print(f"    → {winner or 'draw'} after {game_result['turns']} turns", flush=True)
            except Exception as e:
                print(f"    EXCEPTION: {type(e).__name__}: {e}", flush=True)
                results.append({
                    "deck_a": deck_p1, "deck_b": deck_p2, "seed": seed,
                    "winner": None, "loser": None, "turns": 0, "error": str(e),
                })
            g += 1
    elapsed = time.time() - t0
    print(f"\nTotal wall time: {elapsed/60:.1f} min")

    winrates = {d: (wins[d] / games_played[d] if games_played[d] else 0.0)
                for d in deck_list}
    return {
        "winrates": winrates,
        "wins": wins,
        "games_played": games_played,
        "results": results,
        "config": {
            "decks": deck_list,
            "games_per_pair": games_per_pair,
            "model": model,
            "timeout": timeout,
            "seed_base": seed_base,
            "total_games": total_games,
            "elapsed_sec": elapsed,
        },
    }


def main():
    p = argparse.ArgumentParser(description="Clankers LLM tournament")
    p.add_argument("--decks", type=str, default="CLAN_forge,CLAN_ethos,CLAN_mirth,CLAN_bulwark")
    p.add_argument("--games-per-pair", "-n", type=int, default=2)
    p.add_argument("--model", "-m", type=str, default="haiku")
    p.add_argument("--timeout", "-t", type=float, default=60.0)
    p.add_argument("--seed-base", type=int, default=42)
    p.add_argument("--json-out", type=str, default=None)
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()

    decks = [s.strip() for s in args.decks.split(",") if s.strip()]
    result = run_tournament(
        decks=decks,
        games_per_pair=args.games_per_pair,
        seed_base=args.seed_base,
        model=args.model,
        timeout=args.timeout,
        verbose=args.verbose,
    )

    print("\n=== Winrates ===")
    for d, wr in sorted(result["winrates"].items(), key=lambda x: -x[1]):
        n = result["games_played"][d]
        w = result["wins"][d]
        print(f"  {d}: {wr:.1%} ({w}/{n})")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2, sort_keys=False))
        print(f"\nSaved to {args.json_out}")


if __name__ == "__main__":
    main()
