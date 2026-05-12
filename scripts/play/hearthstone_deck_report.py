"""Print Hearthstone deckbuilding quality metrics as JSON."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


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
    parser.add_argument(
        "--include-custom",
        action="store_true",
        help="Include Stormrift, Frierenrift, and Riftclash deck metrics.",
    )
    parser.add_argument(
        "--custom-only",
        action="store_true",
        help="Only print Stormrift, Frierenrift, and Riftclash deck metrics.",
    )
    parser.add_argument(
        "--fail-on-flags",
        action="store_true",
        help="Exit with status 1 if any deck reports quality or role flags.",
    )
    args = parser.parse_args()

    with contextlib.redirect_stdout(sys.stderr):
        from src.cards.hearthstone.decks import analyze_all_decks, analyze_custom_set_decks

        if args.custom_only:
            report = analyze_custom_set_decks()
        else:
            report = analyze_all_decks()
            if args.include_custom:
                report = {**report, **analyze_custom_set_decks()}
    if args.hero_class:
        if args.hero_class not in report:
            available = ", ".join(sorted(report))
            raise SystemExit(f"Unknown class {args.hero_class!r}. Available: {available}")
        report = {args.hero_class: report[args.hero_class]}

    indent = None if args.compact else 2
    print(json.dumps(report, indent=indent, sort_keys=True))

    if args.fail_on_flags:
        flagged = {
            hero_class: {
                "quality_flags": summary.get("quality_flags", []),
                "role_quality_flags": summary.get("role_quality_flags", []),
            }
            for hero_class, summary in report.items()
            if summary.get("quality_flags") or summary.get("role_quality_flags")
        }
        if flagged:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
