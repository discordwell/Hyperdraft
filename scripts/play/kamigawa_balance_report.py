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
    args = parser.parse_args()

    with contextlib.redirect_stdout(sys.stderr):
        from src.cards.yugioh.beyond.kamigawa import kamigawa_balance_summary

    report = kamigawa_balance_summary()
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
