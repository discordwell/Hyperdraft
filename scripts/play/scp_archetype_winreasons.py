"""Run tournament-style games and surface ``winner_reason`` per game for the
rebalanced archetypes. Confirms whether the alt-wins actually trigger.
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path
from collections import Counter

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.play.scp_tournament import run_one_game


async def main():
    pairs = [
        ("antimemetic_cold_war", "secure_contain_research"),
        ("ethics_reckoning", "secure_contain_research"),
        ("mnestic_reset_division", "secure_contain_research"),
        ("mnestic_reset_division", "antimemetic_cold_war"),
    ]
    for p1, p2 in pairs:
        print(f"\n=== {p1} vs {p2} (10 games) ===")
        reasons = Counter()
        wins_p1 = 0
        for i in range(10):
            outcome = await run_one_game(
                p1, p2, seed=100 + i, max_turns=40, difficulty="medium",
                p1_pilot="balanced", p2_pilot="balanced",
            )
            reasons[outcome.winner_reason] += 1
            if outcome.winner_deck == p1:
                wins_p1 += 1
            print(f"  game {i+1:2d}: winner={outcome.winner_deck} reason={outcome.winner_reason} turns={outcome.turns}")
        print(f"  -> {p1} wins {wins_p1}/10. Reason breakdown: {dict(reasons)}")


if __name__ == "__main__":
    asyncio.run(main())
