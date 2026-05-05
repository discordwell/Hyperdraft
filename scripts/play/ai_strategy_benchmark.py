#!/usr/bin/env python3
"""Run fixed-seed MTG AI decision benchmarks and write trace artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.ai.benchmark_scenarios import run_fixed_decision_benchmark  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True, help="Directory for decisions.jsonl and summary.json.")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--difficulty", default="hard")
    args = parser.parse_args(argv)

    summary = run_fixed_decision_benchmark(
        args.out_dir,
        seed=args.seed,
        difficulty=args.difficulty,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("scenario_pass_rate") == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
