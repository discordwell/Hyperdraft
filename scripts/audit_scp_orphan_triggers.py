#!/usr/bin/env python3
"""Audit ``scp_on_*`` trigger slots declared on cards vs. read by the engine.

A *wired* slot is one the engine actually fires (the card_def value is read
and executed somewhere under ``src/engine/scp*.py``). An *orphan* slot is
declared on at least one card but never fired — those cards' triggers are
dead-letter code: the engine ignores them.

This script scans:

* ``src/cards/scp/**/*.py`` for ``scp_on_<name>`` declarations.
* ``src/engine/scp*.py`` for ``scp_on_<name>`` reads.

It prints two tables (wired + orphan, sorted by declaration frequency) plus
a JSON-shaped summary at the end. Exit code is always 0 — this is a
reporting tool, not a CI gate. The CI gate lives in
``tests/test_scp_orphan_triggers.py`` and grandfathers the orphan list so
the gap can't widen silently.

Run::

    python scripts/audit_scp_orphan_triggers.py
    python scripts/audit_scp_orphan_triggers.py --json   # machine-readable
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


SLOT_PATTERN = re.compile(r"scp_on_[a-z_]+")
REPO_ROOT = Path(__file__).resolve().parent.parent


def scan_card_declarations() -> tuple[Counter, dict[str, set[str]]]:
    card_dir = REPO_ROOT / "src" / "cards" / "scp"
    declarations: Counter = Counter()
    file_map: dict[str, set[str]] = defaultdict(set)
    for path in card_dir.rglob("*.py"):
        text = path.read_text()
        for match in SLOT_PATTERN.finditer(text):
            slot = match.group(0)
            declarations[slot] += 1
            file_map[slot].add(str(path.relative_to(REPO_ROOT)))
    return declarations, file_map


def scan_engine_reads() -> set[str]:
    engine_dir = REPO_ROOT / "src" / "engine"
    reads: set[str] = set()
    for path in engine_dir.glob("scp*.py"):
        text = path.read_text()
        for match in SLOT_PATTERN.finditer(text):
            reads.add(match.group(0))
    return reads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON instead of a table")
    args = parser.parse_args(argv)

    declarations, file_map = scan_card_declarations()
    engine_reads = scan_engine_reads()

    wired = sorted(set(declarations) & engine_reads)
    orphans = sorted(set(declarations) - engine_reads)

    if args.json:
        payload = {
            "wired": [
                {"slot": s, "declarations": declarations[s],
                 "files": sorted(file_map[s])}
                for s in sorted(wired, key=lambda s: -declarations[s])
            ],
            "orphans": [
                {"slot": s, "declarations": declarations[s],
                 "files": sorted(file_map[s])}
                for s in sorted(orphans, key=lambda s: -declarations[s])
            ],
            "engine_reads_only": sorted(engine_reads - set(declarations)),
            "summary": {
                "wired_slot_count": len(wired),
                "orphan_slot_count": len(orphans),
                "total_declarations": sum(declarations.values()),
                "orphan_declarations": sum(declarations[s] for s in orphans),
            },
        }
        print(json.dumps(payload, indent=2))
        return 0

    print("=== Wired slots (card declarations the engine reads) ===")
    for s in sorted(wired, key=lambda s: -declarations[s]):
        print(f"  {s:35s} {declarations[s]:4d}  ({len(file_map[s])} files)")

    print("\n=== Orphan slots (declared on cards, never read by engine) ===")
    for s in sorted(orphans, key=lambda s: -declarations[s]):
        print(f"  {s:35s} {declarations[s]:4d}  ({len(file_map[s])} files)")

    only_in_engine = engine_reads - set(declarations)
    if only_in_engine:
        print("\n=== Engine-only references (no card declares these) ===")
        for s in sorted(only_in_engine):
            print(f"  {s}")

    total = sum(declarations.values())
    orphan_total = sum(declarations[s] for s in orphans)
    print(f"\nSummary: {len(wired)} wired slot types, {len(orphans)} orphan slot types")
    print(f"         {total} total declarations, {orphan_total} orphan declarations "
          f"({orphan_total/total*100:.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
