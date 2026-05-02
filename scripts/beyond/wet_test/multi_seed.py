"""
Multi-seed round-robin: run the 45-pair tournament 5 times with different
seeds to confirm the Boros↑/Orzhov↓ trend is real and not single-seed noise.
"""

from __future__ import annotations

import asyncio
import random
import sys
import time
from collections import defaultdict
from itertools import combinations
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from src.engine.game import Game  # noqa: E402
from src.cards.pokemon.beyond.ravnica import GUILD_DECK_BUILDERS  # noqa: E402

MAX_TURNS = 80
SEEDS = [42, 100, 2026, 7777, 31415]


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def play_match(guild_a, guild_b):
    from src.ai.pokemon_adapter import PokemonAIAdapter
    g = Game(mode="pokemon")
    p1 = g.add_player(guild_a)
    p2 = g.add_player(guild_b)
    g.setup_pokemon_player(p1, GUILD_DECK_BUILDERS[guild_a]())
    g.setup_pokemon_player(p2, GUILD_DECK_BUILDERS[guild_b]())
    ai = PokemonAIAdapter(difficulty="medium")
    g.turn_manager.set_ai_handler(ai)
    g.turn_manager.set_ai_player(p1.id)
    g.turn_manager.set_ai_player(p2.id)
    g.turn_manager.turn_order = [p1.id, p2.id]
    await g.turn_manager.setup_game()
    for _ in range(MAX_TURNS):
        if g.is_game_over():
            break
        await g.turn_manager.run_turn()
    if not g.is_game_over():
        return None  # timeout
    if getattr(p1, "has_lost", False) and not getattr(p2, "has_lost", False):
        return guild_b
    if getattr(p2, "has_lost", False) and not getattr(p1, "has_lost", False):
        return guild_a
    return None  # draw


def main():
    guilds = sorted(GUILD_DECK_BUILDERS.keys())
    pairs = list(combinations(guilds, 2))
    print(f"Multi-seed: {len(pairs)} pairs × {len(SEEDS)} seeds = {len(pairs)*len(SEEDS)} matches")
    print("=" * 70)

    wins = defaultdict(int)
    matches = defaultdict(int)
    matchup = defaultdict(lambda: defaultdict(int))  # matchup[a][b] = wins for a in a-vs-b
    t0 = time.time()

    for seed in SEEDS:
        random.seed(seed)
        for a, b in pairs:
            try:
                winner = run(play_match(a, b))
                matches[a] += 1
                matches[b] += 1
                if winner == a:
                    wins[a] += 1
                    matchup[a][b] += 1
                elif winner == b:
                    wins[b] += 1
                    matchup[b][a] += 1
            except Exception as ex:
                print(f"  CRASH {a} vs {b} seed={seed}: {type(ex).__name__}: {ex}")

    dt = time.time() - t0
    print(f"\nDone in {dt:.1f}s")
    print()
    print(f"{'Guild':>10s} {'W':>4s} {'P':>4s} {'WR':>5s}")
    print("-" * 30)
    for g in sorted(guilds, key=lambda x: -wins[x]/max(1, matches[x])):
        wr = wins[g] / max(1, matches[g]) * 100
        print(f"{g:>10s} {wins[g]:>4d} {matches[g]:>4d} {wr:>4.0f}%")

    print()
    print("=== Matchup grid (W/P from row's perspective) ===")
    print(f"{'':>10s}", end="")
    for b in guilds:
        print(f" {b[:5]:>6s}", end="")
    print()
    for a in guilds:
        print(f"{a:>10s}", end="")
        for b in guilds:
            if a == b:
                print(f" {'  -':>6s}", end="")
            else:
                w = matchup[a][b]
                p = w + matchup[b][a]
                print(f" {w:>2d}/{p:<2d} ", end="")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
