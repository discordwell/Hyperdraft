"""Throwaway runtime probe (Phase D): attribute the breach-rush edge BEFORE committing card changes.

Sweeps BREACH_FREE_MULTIPLIER (the free→breach double-dip) and BREACH_CATASTROPHE (the breach
win threshold) by monkeypatching the engine constants, replays the full deck matrix per config,
and reports the overall faction split + the breach-rush deck's winrate + per-pairing. Disprove-
before-commit: if a single systemic lever tames breach-rush to a healthy band without flattening
its identity, prefer it over a 140-card deck rebalance.

Run: HYPERDRAFT_STRICT=1 PYTHONPATH=. python3 scripts/play/scp_breach_probe.py
"""

from __future__ import annotations

from src.engine import scp
from scripts.play.scp_tournament import run_tournament, summarize

GAMES = 50  # per pairing → 200 games/config; enough to read ≥15pt moves over the ~15% variance


def _probe(mult: float, catastrophe: int) -> dict:
    old_mult, old_cat = scp.BREACH_FREE_MULTIPLIER, scp.BREACH_CATASTROPHE
    scp.BREACH_FREE_MULTIPLIER, scp.BREACH_CATASTROPHE = mult, catastrophe
    try:
        s = summarize(run_tournament(games=GAMES))
    finally:
        scp.BREACH_FREE_MULTIPLIER, scp.BREACH_CATASTROPHE = old_mult, old_cat
    breach_deck = "SCP_containment_breach"
    breach_wins = breach_games = 0
    for k, v in s["per_pairing"].items():
        if breach_deck in k:
            breach_wins += v.get("Insurgency", 0)
            breach_games += sum(v.values())
    s["breach_rush_winrate"] = round(100 * breach_wins / max(1, breach_games), 1)
    return s


def main():
    configs = [(1.0, 14), (0.75, 14), (0.5, 14), (0.5, 16), (1.0, 16)]
    print(f"{'mult':>5} {'catas':>6} | {'Found%':>7} {'Insur%':>7} | {'breach-rush%':>12} | reasons")
    for mult, cat in configs:
        s = _probe(mult, cat)
        print(f"{mult:>5} {cat:>6} | {s['foundation_winrate']:>7} {s['insurgency_winrate']:>7} | "
              f"{s['breach_rush_winrate']:>12} | {s['reasons']}")


if __name__ == "__main__":
    main()
