#!/usr/bin/env python3
"""Emit Beyond Ravnica Pokemon balance metrics as JSON."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def build_report() -> dict:
    with contextlib.redirect_stdout(io.StringIO()):
        from src.cards.pokemon.beyond.ravnica.balance import ravnica_balance_summary

        guilds = ravnica_balance_summary()
    failing = {
        guild: profile["balance_flags"]
        for guild, profile in guilds.items()
        if profile["balance_flags"]
    }
    return {
        "schema_version": 1,
        "format": "pokemon_beyond_ravnica_balance",
        "guilds": guilds,
        "quality_gate": {
            "passed": not failing,
            "failing_guilds": failing,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="Optional JSON output path.")
    parser.add_argument(
        "--fail-on-flags",
        action="store_true",
        help="Return a non-zero status when any guild has balance flags.",
    )
    args = parser.parse_args(argv)

    report = build_report()
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(payload + "\n")
    print(payload)
    if args.fail_on_flags and not report["quality_gate"]["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
