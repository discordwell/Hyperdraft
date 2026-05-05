#!/usr/bin/env python3
"""Generate a compact measurement report for the strategy iteration pass."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.ai.strategy_pass import run_strategy_pass_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--sets", default="FDN", help="Comma-separated set codes for deck metrics.")
    args = parser.parse_args(argv)

    set_codes = [item.strip() for item in args.sets.split(",") if item.strip()]
    report = run_strategy_pass_report(args.out_dir, seed=args.seed, set_codes=set_codes)
    print(json.dumps({
        "schema_version": report["schema_version"],
        "seed": report["seed"],
        "set_codes": report["set_codes"],
        "ai_scenario_pass_rate": report["ai"]["scenario_pass_rate"],
        "deck_labels": sorted(report["decks"]),
        "variant_labels": sorted(report["variants"]),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
