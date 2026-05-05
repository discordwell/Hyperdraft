#!/usr/bin/env python3
"""Emit Pokemon deck quality metrics as JSON."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _quality_gate(summaries: dict[str, dict]) -> dict:
    failing = {
        name: {
            "quality_flags": summary["quality_flags"],
            "role_quality_flags": summary["role_quality_flags"],
        }
        for name, summary in summaries.items()
        if summary["quality_flags"] or summary["role_quality_flags"]
    }
    return {
        "passed": not failing,
        "failing_decks": failing,
    }


def build_report(deck_name: str | None = None) -> dict:
    with contextlib.redirect_stdout(io.StringIO()):
        from src.cards.pokemon.deck_quality import analyze_sv_starter_decks

        summaries = analyze_sv_starter_decks()
    if deck_name:
        if deck_name not in summaries:
            available = ", ".join(sorted(summaries))
            raise ValueError(f"Unknown Pokemon starter deck '{deck_name}'. Available: {available}")
        summaries = {deck_name: summaries[deck_name]}
    return {
        "schema_version": 1,
        "format": "pokemon_deck_quality",
        "decks": summaries,
        "quality_gate": _quality_gate(summaries),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deck", help="Optional starter deck name to report.")
    parser.add_argument("--out", help="Optional JSON output path.")
    parser.add_argument(
        "--fail-on-flags",
        action="store_true",
        help="Return a non-zero status when any deck has quality flags.",
    )
    args = parser.parse_args(argv)

    try:
        report = build_report(args.deck)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(payload + "\n")
    print(payload)
    if args.fail_on_flags and not report["quality_gate"]["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
