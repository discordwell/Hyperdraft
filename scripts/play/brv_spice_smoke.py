"""Smoke test: run heuristic AI vs heuristic AI Pokemon games on every BRV
guild matchup, catch crashes / exceptions / deadlocks introduced by the
spice pack v1 cards.

Not a balance benchmark — just a "does the game finish without throwing?"
gate. Real balance/decision-quality validation is /ultra-loop.

Usage:
    python -m scripts.play.brv_spice_smoke --games-per-matchup 1 --max-turns 16

Output: one line per matchup, summary at the end. Exits 1 if any matchup crashes.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys
import time
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


async def _run_matchup(g1: str, b1, g2: str, b2, max_turns: int) -> tuple[str, int, str]:
    """Run one game, return (verdict, turns, error_text)."""
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.engine.game import Game
        from src.ai.pokemon_adapter import PokemonAIAdapter
    try:
        deck1 = b1()
        deck2 = b2()
    except Exception as e:
        return f"deck-build-fail", 0, f"{g1}/{g2}: {type(e).__name__}: {e}\n{traceback.format_exc()}"

    try:
        game = Game(mode="pokemon")
        p1 = game.add_player(f"P1-{g1}")
        p2 = game.add_player(f"P2-{g2}")
        game.setup_pokemon_player(p1, deck1)
        game.setup_pokemon_player(p2, deck2)
        ai = PokemonAIAdapter(difficulty="medium")
        ai.player_difficulties[p1.id] = "medium"
        ai.player_difficulties[p2.id] = "medium"
        game.turn_manager.set_ai_handler(ai)
        game.turn_manager.set_ai_player(p1.id)
        game.turn_manager.set_ai_player(p2.id)
        await game.turn_manager.setup_game()
        turns = 0
        for _ in range(max_turns):
            if game.is_game_over():
                break
            await game.turn_manager.run_turn()
            turns += 1
        if game.is_game_over():
            verdict = "completed"
        else:
            verdict = "max-turns"
        return verdict, turns, ""
    except Exception as e:
        tb = traceback.format_exc()
        return "CRASH", 0, f"{g1}/{g2}: {type(e).__name__}: {e}\n{tb}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games-per-matchup", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=16)
    parser.add_argument("--matchups", nargs="*", default=None,
                        help="Restrict to specific guild pairs like izzet:dimir")
    parser.add_argument("--out", default=None,
                        help="Optional path to write the verdict log")
    args = parser.parse_args()

    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.cards.pokemon.beyond.ravnica import GUILD_DECK_BUILDERS

    guilds = sorted(GUILD_DECK_BUILDERS.keys())
    if args.matchups:
        pairs = [tuple(m.split(":")) for m in args.matchups]
    else:
        # Each guild plays the next one in alphabetical order — 10 matchups,
        # good coverage without quadratic blowup.
        pairs = list(zip(guilds, guilds[1:] + [guilds[0]]))

    results: list[tuple[str, str, str, int, str]] = []
    crashes: list[tuple[str, str, str]] = []
    start = time.perf_counter()
    for g1, g2 in pairs:
        for _ in range(args.games_per_matchup):
            verdict, turns, err = asyncio.run(_run_matchup(
                g1, GUILD_DECK_BUILDERS[g1], g2, GUILD_DECK_BUILDERS[g2],
                max_turns=args.max_turns,
            ))
            results.append((g1, g2, verdict, turns, err))
            tag = "OK" if verdict in ("completed", "max-turns") else "FAIL"
            print(f"[{tag:4s}] {g1:10s} vs {g2:10s}  →  {verdict:12s} in {turns:2d} turns")
            if verdict == "CRASH":
                crashes.append((g1, g2, err))

    elapsed = time.perf_counter() - start
    print(f"\n=== Summary ===")
    print(f"Total: {len(results)}  Crashed: {len(crashes)}  Elapsed: {elapsed:.1f}s")
    if crashes:
        print(f"\n=== Crash details (first 3) ===")
        for g1, g2, err in crashes[:3]:
            print(f"\n--- {g1} vs {g2} ---")
            print(err[:1500])

    if args.out:
        Path(args.out).write_text("\n".join(
            f"[{v}] {a} vs {b}  {t} turns  {e[:200]}" for (a, b, v, t, e) in results
        ))
        print(f"\nWrote {args.out}")

    return 1 if crashes else 0


if __name__ == "__main__":
    raise SystemExit(main())
