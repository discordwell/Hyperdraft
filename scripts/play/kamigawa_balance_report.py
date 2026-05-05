"""Print Beyond Kamigawa Yu-Gi-Oh! balance metrics as JSON."""

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
        help="Exit with status 1 if any archetype reports balance flags.",
    )
    parser.add_argument("--archetype", default=None,
                        help="optional Beyond Kamigawa archetype to report")
    args = parser.parse_args()

    with contextlib.redirect_stdout(sys.stderr):
        from src.cards.yugioh.beyond.kamigawa import kamigawa_balance_summary

    report = kamigawa_balance_summary()
    if args.archetype:
        if args.archetype not in report:
            print(f"Unknown Beyond Kamigawa archetype: {args.archetype}", file=sys.stderr)
            return 2
        report = {args.archetype: report[args.archetype]}
    print(json.dumps(report, indent=2, sort_keys=True))

    if args.fail_on_flags:
        flagged = {
            archetype: profile["balance_flags"]
            for archetype, profile in report.items()
            if profile["balance_flags"]
        }
        if flagged:
            print(json.dumps({"flagged_archetypes": flagged}, indent=2, sort_keys=True), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
