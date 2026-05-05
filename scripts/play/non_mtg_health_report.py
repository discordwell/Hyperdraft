#!/usr/bin/env python3
"""Generate a compact health report for non-MTG game modes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.engine.mode_metrics import NON_MTG_MODES, non_mtg_health_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--modes",
        default=",".join(NON_MTG_MODES),
        help="Comma-separated mode names to validate.",
    )
    parser.add_argument("--out", help="Optional path for the full JSON report.")
    args = parser.parse_args(argv)

    modes = [item.strip() for item in args.modes.split(",") if item.strip()]
    report = non_mtg_health_report(modes)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    compact = {
        "schema_version": report["schema_version"],
        "passed": report["passed"],
        "mode_count": report["mode_count"],
        "failed_modes": report["failed_modes"],
        "modes": {
            mode: {
                "passed": summary["passed"],
                "failures": summary["failures"],
                "subsystems": summary.get("subsystems", {}),
                "rules": summary.get("rules", {}),
            }
            for mode, summary in report["modes"].items()
        },
    }
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
