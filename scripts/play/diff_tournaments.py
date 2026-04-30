#!/usr/bin/env python3
"""
Diff two tournament JSONs (e.g., pre-rebalance vs post-rebalance).

Reports per-set:
  - winrate delta
  - dead-card count delta
  - broken-card count delta
  - cards that moved from dead → ok or strong
  - cards that newly became broken

Usage:
    python scripts/play/diff_tournaments.py \\
        logs/tournament_v1.json logs/tournament_v2.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


BASIC_LAND_NAMES = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}


def bucket(score: dict) -> str:
    cpc = score.get("cast_per_copy", 0.0)
    if cpc < 0.05 and score.get("deck_copies", 0) >= 2:
        return "dead"
    if cpc < 0.30:
        return "weak"
    if cpc < 0.70:
        return "ok"
    return "strong"


def is_broken(score: dict) -> bool:
    return (
        score.get("cast_per_copy", 0) >= 0.7
        and score.get("win_rate_in_play", 0) > 0.70
        and score.get("in_play_at_end", 0) >= 4
    )


def summarize(agg: dict) -> dict[str, dict]:
    """Per-set summary: winrate, bucket counts, broken count, card -> bucket."""
    out: dict[str, dict] = {}
    for domain, rec in agg["set_summary"].items():
        out[domain] = {
            "winrate": rec.get("winrate", 0.0),
            "wins": rec.get("wins", 0),
            "losses": rec.get("losses", 0),
            "draws": rec.get("draws", 0),
            "cards": {},
            "buckets": {"dead": 0, "weak": 0, "ok": 0, "strong": 0},
            "broken": 0,
        }

    for ref, score in agg["card_scores"].items():
        domain, name = ref.split("::", 1)
        if name in BASIC_LAND_NAMES:
            continue
        if domain not in out:
            continue
        b = bucket(score)
        out[domain]["cards"][name] = b
        out[domain]["buckets"][b] += 1
        if is_broken(score):
            out[domain]["broken"] += 1

    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("before_json")
    parser.add_argument("after_json")
    args = parser.parse_args()

    with open(args.before_json) as f:
        before = json.load(f)
    with open(args.after_json) as f:
        after = json.load(f)

    if "aggregate" not in before or "aggregate" not in after:
        print("ERROR: one or both tournament JSONs are missing 'aggregate'.")
        sys.exit(1)

    a = summarize(before["aggregate"])
    b = summarize(after["aggregate"])
    domains = sorted(set(a.keys()) | set(b.keys()))

    print("=" * 70)
    print(f"TOURNAMENT DIFF — {Path(args.before_json).name} → {Path(args.after_json).name}")
    print("=" * 70)

    print(f"\n{'Set':6s}  {'WR Δ':>8s}  {'Wins Δ':>7s}  {'Dead Δ':>7s}  {'Broken Δ':>8s}")
    for d in domains:
        ra, rb = a.get(d, {}), b.get(d, {})
        wr_a, wr_b = ra.get("winrate", 0) * 100, rb.get("winrate", 0) * 100
        wins_a, wins_b = ra.get("wins", 0), rb.get("wins", 0)
        dead_a = ra.get("buckets", {}).get("dead", 0)
        dead_b = rb.get("buckets", {}).get("dead", 0)
        brk_a, brk_b = ra.get("broken", 0), rb.get("broken", 0)
        sign_wr = "+" if wr_b - wr_a >= 0 else ""
        sign_w = "+" if wins_b - wins_a >= 0 else ""
        sign_dead = "+" if dead_b - dead_a >= 0 else ""
        sign_brk = "+" if brk_b - brk_a >= 0 else ""
        print(
            f"{d:6s}  {sign_wr}{wr_b - wr_a:6.1f}%  "
            f"{sign_w}{wins_b - wins_a:6d}  "
            f"{sign_dead}{dead_b - dead_a:6d}  "
            f"{sign_brk}{brk_b - brk_a:7d}"
        )

    # Per-set: cards that moved buckets
    print("\n## Card movement (dead → ok/strong, broken → ok/weak)")
    for d in domains:
        ca = a.get(d, {}).get("cards", {})
        cb = b.get(d, {}).get("cards", {})
        rescued = []
        regressed = []
        nerfed = []
        new_dead = []
        for name, ba in ca.items():
            bb = cb.get(name)
            if bb is None:
                continue  # card not in v2 (shouldn't happen)
            if ba == "dead" and bb in ("ok", "strong"):
                rescued.append((name, ba, bb))
            if ba == "strong" and bb in ("weak", "dead"):
                nerfed.append((name, ba, bb))
            if ba in ("ok", "strong") and bb == "dead":
                new_dead.append((name, ba, bb))
        if rescued or regressed or nerfed or new_dead:
            print(f"\n### {d}")
            for n, ba, bb in rescued:
                print(f"  rescued: {n}  ({ba} → {bb})")
            for n, ba, bb in nerfed:
                print(f"  nerfed: {n}  ({ba} → {bb})")
            for n, ba, bb in new_dead:
                print(f"  newly dead: {n}  ({ba} → {bb})")


if __name__ == "__main__":
    main()
