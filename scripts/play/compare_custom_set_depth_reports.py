"""Compare two custom-set depth reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def compare_reports(before: dict, after: dict) -> dict:
    rows = {}
    before_sets = before.get("sets", {})
    after_sets = after.get("sets", {})
    for key in sorted(set(before_sets) & set(after_sets)):
        b = before_sets[key]
        a = after_sets[key]
        rows[key] = {
            "label": a.get("label", b.get("label", key)),
            "avg_score": {
                "before": b.get("avg_score", 0),
                "after": a.get("avg_score", 0),
                "delta": round(a.get("avg_score", 0) - b.get("avg_score", 0), 2),
            },
            "benchmark_ratio": {
                "before": b.get("benchmark_ratio", 0),
                "after": a.get("benchmark_ratio", 0),
                "delta": round(a.get("benchmark_ratio", 0) - b.get("benchmark_ratio", 0), 3),
            },
            "thin_pct": {
                "before": b.get("thin_pct", 0),
                "after": a.get("thin_pct", 0),
                "delta": round(a.get("thin_pct", 0) - b.get("thin_pct", 0), 1),
            },
            "wired_pct": {
                "before": b.get("wired_pct", 0),
                "after": a.get("wired_pct", 0),
                "delta": round(a.get("wired_pct", 0) - b.get("wired_pct", 0), 1),
            },
        }
    return {
        "schema_version": "hyperdraft.custom_set_depth_compare.v1",
        "sets": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    comparison = compare_reports(_load(args.before), _load(args.after))
    payload = json.dumps(comparison, indent=None if args.compact else 2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
