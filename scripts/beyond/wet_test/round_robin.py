"""
Round-robin tournament for Beyond Ravnica: all 45 guild pairs.
Reports per-guild win/loss/timeout/crash and any anomaly logs.
"""

from __future__ import annotations

import asyncio
import argparse
import json
import os
import random
import sys
import time
import traceback
from collections import defaultdict
from itertools import combinations
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from src.engine.game import Game  # noqa: E402
from src.cards.pokemon.beyond.ravnica import GUILD_DECK_BUILDERS  # noqa: E402

MAX_TURNS = 80
TIMEOUT_SECONDS = 60


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

    turns = 0
    for _ in range(MAX_TURNS):
        if g.is_game_over():
            break
        await g.turn_manager.run_turn()
        turns += 1

    if not g.is_game_over():
        return {"result": "timeout", "turns": turns}

    if getattr(p1, "has_lost", False) and getattr(p2, "has_lost", False):
        return {"result": "draw", "turns": turns}
    if getattr(p1, "has_lost", False):
        return {"result": "win", "winner": guild_b, "loser": guild_a, "turns": turns}
    if getattr(p2, "has_lost", False):
        return {"result": "win", "winner": guild_a, "loser": guild_b, "turns": turns}
    return {"result": "unknown", "turns": turns}


def build_round_robin_report(
    guilds,
    wins,
    losses,
    draws,
    timeouts,
    crashes,
    anomalies,
    turn_counts,
    elapsed_seconds,
    matches_run,
):
    standings = {}
    for guild in guilds:
        played = wins[guild] + losses[guild] + draws[guild] + timeouts[guild] + crashes[guild]
        standings[guild] = {
            "wins": wins[guild],
            "losses": losses[guild],
            "draws": draws[guild],
            "timeouts": timeouts[guild],
            "crashes": crashes[guild],
            "played": played,
            "win_rate": wins[guild] / played if played else 0.0,
        }
    return {
        "schema_version": 1,
        "format": "pokemon_beyond_ravnica_round_robin",
        "matches_run": matches_run,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "average_turns": sum(turn_counts) / max(1, len(turn_counts)),
        "standings": standings,
        "anomalies": list(anomalies),
        "quality_gate": {
            "passed": not anomalies,
            "anomaly_count": len(anomalies),
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", help="Optional JSON summary output path.")
    args = parser.parse_args(argv)

    guilds = sorted(GUILD_DECK_BUILDERS.keys())
    pairs = list(combinations(guilds, 2))
    print(f"Round-robin: {len(pairs)} guild pairs, max {MAX_TURNS} turns each")
    print("=" * 70)

    wins = defaultdict(int)
    losses = defaultdict(int)
    draws = defaultdict(int)
    timeouts = defaultdict(int)
    crashes = defaultdict(int)
    anomalies = []
    turn_counts = []
    t0 = time.time()

    random.seed(2026)

    for i, (a, b) in enumerate(pairs, 1):
        try:
            res = run(asyncio.wait_for(play_match(a, b), timeout=TIMEOUT_SECONDS))
            turn_counts.append(res.get("turns", 0))
            if res["result"] == "win":
                wins[res["winner"]] += 1
                losses[res["loser"]] += 1
                marker = f"{res['winner']:>10s} beat {res['loser']:<10s} ({res['turns']}t)"
            elif res["result"] == "draw":
                draws[a] += 1
                draws[b] += 1
                marker = f"{a:>10s} vs   {b:<10s} draw ({res['turns']}t)"
            elif res["result"] == "timeout":
                timeouts[a] += 1
                timeouts[b] += 1
                marker = f"{a:>10s} vs   {b:<10s} timeout"
                anomalies.append(f"{a} vs {b}: timeout @ turn {res['turns']}")
            else:
                anomalies.append(f"{a} vs {b}: unknown result")
                marker = f"{a:>10s} vs   {b:<10s} ???"
            print(f"  [{i:2d}/45] {marker}")
        except asyncio.TimeoutError:
            timeouts[a] += 1
            timeouts[b] += 1
            anomalies.append(f"{a} vs {b}: hard timeout >{TIMEOUT_SECONDS}s")
            print(f"  [{i:2d}/45] {a:>10s} vs {b:<10s} HARD TIMEOUT")
        except Exception as ex:
            crashes[a] += 1
            crashes[b] += 1
            tb = traceback.format_exc().splitlines()[-3:]
            anomalies.append(f"{a} vs {b}: {type(ex).__name__}: {ex}\n  " + "\n  ".join(tb))
            print(f"  [{i:2d}/45] {a:>10s} vs {b:<10s} CRASH: {type(ex).__name__}: {ex}")

    dt = time.time() - t0

    print()
    print("=" * 70)
    print(f"Total time: {dt:.1f}s  Avg turns: {sum(turn_counts)/max(1,len(turn_counts)):.1f}")
    print()
    print(f"{'Guild':>10s} {'W':>3s} {'L':>3s} {'D':>3s} {'TO':>3s} {'CR':>3s}  {'WR':>5s}")
    print("-" * 50)
    for g in guilds:
        played = wins[g] + losses[g] + draws[g] + timeouts[g] + crashes[g]
        wr = wins[g] / played * 100 if played else 0
        print(f"{g:>10s} {wins[g]:>3d} {losses[g]:>3d} {draws[g]:>3d} "
              f"{timeouts[g]:>3d} {crashes[g]:>3d}  {wr:>4.0f}%")

    if anomalies:
        print()
        print("=== ANOMALIES ===")
        for a in anomalies:
            print(f"  {a}")
        if args.json_out:
            report = build_round_robin_report(
                guilds, wins, losses, draws, timeouts, crashes, anomalies,
                turn_counts, dt, len(pairs),
            )
            Path(args.json_out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        return 1

    if args.json_out:
        report = build_round_robin_report(
            guilds, wins, losses, draws, timeouts, crashes, anomalies,
            turn_counts, dt, len(pairs),
        )
        Path(args.json_out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print()
    print("No crashes, no timeouts. All 45 matches resolved cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
