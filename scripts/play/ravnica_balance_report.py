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


def _aggregate_summary(guilds: dict[str, dict]) -> dict:
    consistency_scores = [profile["consistency_score"] for profile in guilds.values()]
    pressure_scores = [profile["pressure_score"] for profile in guilds.values()]
    alignment_scores = [profile["energy_alignment_score"] for profile in guilds.values()]
    return {
        "guild_count": len(guilds),
        "min_consistency_score": min(consistency_scores, default=0),
        "max_consistency_score": max(consistency_scores, default=0),
        "consistency_score_spread": max(consistency_scores, default=0) - min(consistency_scores, default=0),
        "min_pressure_score": min(pressure_scores, default=0),
        "max_pressure_score": max(pressure_scores, default=0),
        "pressure_score_spread": max(pressure_scores, default=0) - min(pressure_scores, default=0),
        "min_energy_alignment_score": min(alignment_scores, default=0),
        "max_energy_alignment_score": max(alignment_scores, default=0),
        "energy_alignment_spread": max(alignment_scores, default=0) - min(alignment_scores, default=0),
        "flagged_guild_count": sum(
            1 for profile in guilds.values() if profile["balance_flags"]
        ),
    }


def build_report(guild_name: str | None = None) -> dict:
    with contextlib.redirect_stdout(io.StringIO()):
        from src.cards.pokemon.beyond.ravnica.balance import ravnica_balance_summary

        guilds = ravnica_balance_summary()
    if guild_name:
        if guild_name not in guilds:
            available = ", ".join(sorted(guilds))
            raise ValueError(f"Unknown Beyond Ravnica guild '{guild_name}'. Available: {available}")
        guilds = {guild_name: guilds[guild_name]}
    failing = {
        guild: profile["balance_flags"]
        for guild, profile in guilds.items()
        if profile["balance_flags"]
    }
    return {
        "schema_version": 1,
        "format": "pokemon_beyond_ravnica_balance",
        "summary": _aggregate_summary(guilds),
        "guilds": guilds,
        "quality_gate": {
            "passed": not failing,
            "failing_guilds": failing,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guild", help="Optional guild name to report.")
    parser.add_argument("--out", help="Optional JSON output path.")
    parser.add_argument(
        "--fail-on-flags",
        action="store_true",
        help="Return a non-zero status when any guild has balance flags.",
    )
    args = parser.parse_args(argv)

    try:
        report = build_report(args.guild)
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
