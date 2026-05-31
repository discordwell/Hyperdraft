"""SCP: SECURE / CONTAIN / SUBVERT — asymmetric balance harness.

Pairs every Foundation deck against every Insurgency deck, plays N games per pairing
(seed-varied), and reports the per-faction win rate, the win-reason split, and average game
length. Unlike a symmetric mirror tournament, the unit of analysis is the *faction matchup*:
the Phase-4 goal (rules §10) is a healthy split where neither faction wins >~55% and games
are decided by play, not by which seat you were dealt.

Usage:
    python -m scripts.play.scp2_tournament --games 25
    python -m scripts.play.scp2_tournament --games 25 --out logs/scp2_tournament.json

The play_game / run_tournament functions are importable so balance *probes* can reuse them
after monkeypatching scp2 tuning constants — the cheap "disprove before you commit" loop.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter, defaultdict
from typing import Optional

from src.engine.game import Game
from src.engine import scp2
from src.cards.scp2 import decks as D
from src.ai.scp2_adapter import SCP2AIAdapter, DispatchSCP2AIAdapter

DEFAULT_TURN_CAP = 200


async def play_game(foundation_label: str, insurgency_label: str, seed: int,
                    difficulty: str = "medium", turn_cap: int = DEFAULT_TURN_CAP) -> dict:
    g = Game(mode="scp2")
    f = g.add_player("Foundation")
    i = g.add_player("Insurgency")
    fident, fbuild = D.SCP2_FOUNDATION_DECKS[foundation_label]
    iident, ibuild = D.SCP2_INSURGENCY_DECKS[insurgency_label]
    scp2.setup_scp2_game(g, f, i, foundation_deck=fbuild(), insurgency_deck=ibuild(),
                         foundation_identity=fident, insurgency_identity=iident,
                         rng=__import__("random").Random(seed))
    handler = DispatchSCP2AIAdapter({
        f.id: SCP2AIAdapter(difficulty),
        i.id: SCP2AIAdapter(difficulty),
    })
    g.turn_manager.set_ai_handler(handler)
    g.turn_manager.set_ai_player(f.id)
    g.turn_manager.set_ai_player(i.id)

    win = None
    turns = 0
    t0 = time.time()
    for _ in range(turn_cap):
        if g.is_game_over():
            break
        events = await g.turn_manager.run_turn()
        turns += 1
        for e in events:
            if e.type.name == "SCP2_WIN":
                win = e.payload
    fr = scp2.ensure_scp2_state(g.state, f.id)
    ir = scp2.ensure_scp2_state(g.state, i.id)
    winner_faction = None
    if win:
        winner_faction = "Foundation" if win.get("winner") == f.id else "Insurgency"
    return {
        "foundation": foundation_label, "insurgency": insurgency_label, "seed": seed,
        "winner_faction": winner_faction, "reason": (win or {}).get("reason"),
        "turns": turns, "over": g.is_game_over(), "duration_s": round(time.time() - t0, 4),
        "containment": fr["containment_points"], "liberation": ir["liberation_points"],
        "total_breach": fr["total_breach"],
    }


def run_tournament(games: int = 25, difficulty: str = "medium",
                   turn_cap: int = DEFAULT_TURN_CAP, base_seed: int = 1000) -> list[dict]:
    results = []
    for fl in D.SCP2_FOUNDATION_DECKS:
        for il in D.SCP2_INSURGENCY_DECKS:
            for k in range(games):
                seed = base_seed + k
                results.append(asyncio.run(play_game(fl, il, seed, difficulty, turn_cap)))
    return results


def summarize(results: list[dict]) -> dict:
    faction = Counter()
    reason = Counter()
    per_pairing = defaultdict(Counter)
    stalls = 0
    turns_total = 0
    for r in results:
        turns_total += r["turns"]
        if not r["over"]:
            stalls += 1
        wf = r["winner_faction"]
        faction[wf] += 1
        reason[r["reason"]] += 1
        per_pairing[(r["foundation"], r["insurgency"])][wf] += 1
    n = len(results)
    return {
        "games": n,
        "foundation_winrate": round(100 * faction.get("Foundation", 0) / max(1, n), 1),
        "insurgency_winrate": round(100 * faction.get("Insurgency", 0) / max(1, n), 1),
        "faction": dict(faction),
        "reasons": dict(reason),
        "stalls": stalls,
        "avg_turns": round(turns_total / max(1, n), 1),
        "per_pairing": {f"{k[0]} vs {k[1]}": dict(v) for k, v in per_pairing.items()},
    }


def print_report(results: list[dict]) -> dict:
    s = summarize(results)
    print(f"\n=== scp2 balance — {s['games']} games "
          f"({len(D.SCP2_FOUNDATION_DECKS)}×{len(D.SCP2_INSURGENCY_DECKS)} pairings) ===")
    print(f"Foundation win%: {s['foundation_winrate']}   Insurgency win%: {s['insurgency_winrate']}"
          f"   (goal: neither >~55)")
    print(f"avg turns/game: {s['avg_turns']}   stalls (hit cap): {s['stalls']}")
    print(f"win reasons: {s['reasons']}")
    print("per pairing:")
    for k, v in s["per_pairing"].items():
        print(f"   {k:45} {v}")
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=25, help="games per faction pairing")
    ap.add_argument("--difficulty", default="medium")
    ap.add_argument("--turn-cap", type=int, default=DEFAULT_TURN_CAP)
    ap.add_argument("--out", default=None, help="optional JSON dump of raw results")
    args = ap.parse_args()
    results = run_tournament(args.games, args.difficulty, args.turn_cap)
    s = print_report(results)
    if args.out:
        from pathlib import Path
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({"summary": s, "results": results}, indent=2))
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
