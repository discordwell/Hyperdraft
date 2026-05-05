"""Print Hearthstone deckbuilding quality metrics as JSON."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--class",
        dest="hero_class",
        help="Only print metrics for one Hearthstone class.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print compact JSON instead of indented JSON.",
    )
    args = parser.parse_args()

    with contextlib.redirect_stdout(sys.stderr):
        from src.cards.hearthstone.decks import analyze_all_decks

        report = analyze_all_decks()
    if args.hero_class:
        if args.hero_class not in report:
            available = ", ".join(sorted(report))
            raise SystemExit(f"Unknown class {args.hero_class!r}. Available: {available}")
        report = {args.hero_class: report[args.hero_class]}

    indent = None if args.compact else 2
    print(json.dumps(report, indent=indent, sort_keys=True))


if __name__ == "__main__":
    main()
