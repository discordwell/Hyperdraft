"""Print Stormrift custom-set balance metrics as JSON."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--faction",
        choices=("Pyromancer", "Cryomancer"),
        help="Only print metrics for one Stormrift faction.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print compact JSON instead of indented JSON.",
    )
    args = parser.parse_args()

    with contextlib.redirect_stdout(sys.stderr):
        from src.cards.hearthstone.stormrift import stormrift_balance_summary

        report = stormrift_balance_summary()
    if args.faction:
        report = {args.faction: report[args.faction]}

    indent = None if args.compact else 2
    print(json.dumps(report, indent=indent, sort_keys=True))


if __name__ == "__main__":
    main()
