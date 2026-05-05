"""Print optimized Yu-Gi-Oh! deck quality metrics as JSON."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fail-on-flags",
        action="store_true",
        help="Exit with status 1 if any optimized deck reports quality flags.",
    )
    parser.add_argument("--deck", default=None,
                        help="optional optimized deck name to report")
    args = parser.parse_args()

    with contextlib.redirect_stdout(sys.stderr):
        from src.cards.yugioh.deck_quality import analyze_all_ygo_optimized_decks

    report = analyze_all_ygo_optimized_decks()
    if args.deck:
        if args.deck not in report:
            print(f"Unknown optimized Yu-Gi-Oh! deck: {args.deck}", file=sys.stderr)
            return 2
        report = {args.deck: report[args.deck]}
    print(json.dumps(report, indent=2, sort_keys=True))

    if args.fail_on_flags:
        flagged = {
            deck: {
                "quality_flags": summary["quality_flags"],
                "role_quality_flags": summary["role_quality_flags"],
            }
            for deck, summary in report.items()
            if summary["quality_flags"] or summary["role_quality_flags"]
        }
        if flagged:
            print(json.dumps({"flagged_decks": flagged}, indent=2, sort_keys=True), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
