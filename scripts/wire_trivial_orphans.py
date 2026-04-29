"""Auto-wire trivial orphan setup_interceptors functions to their cards.

Reads orphan_triage.json. For each row classified `trivial`, finds the
matched card's make_* assignment via AST, and inserts a
`setup_interceptors=foo_setup,` keyword line just before the closing ')'.
Skips defensively if anything looks unusual.
"""
from __future__ import annotations

import ast
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS_DIR = ROOT / "src" / "cards"
TRIAGE_PATH = ROOT / "orphan_triage.json"


def wire_file(filename: str, rows: list[dict]) -> tuple[int, list[str]]:
    path = CARDS_DIR / filename
    src = path.read_text()
    tree = ast.parse(src)
    lines = src.split("\n")

    var_to_assign: dict[str, ast.Assign] = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            var_to_assign[n.targets[0].id] = n

    # Sort by the *card's* line number descending so insertions don't shift
    # earlier (smaller-line-number) cards. The row's lineno is the function's,
    # not the card's, so look up the assignment's line number.
    def card_lineno(r: dict) -> int:
        node = var_to_assign.get(r.get("matched_card_var") or "")
        return node.lineno if node else 0

    rows_sorted = sorted(rows, key=card_lineno, reverse=True)

    skipped: list[str] = []
    inserted = 0
    for row in rows_sorted:
        var = row.get("matched_card_var")
        fn = row["fn"]
        if not var or var not in var_to_assign:
            skipped.append(f"{fn}: var {var!r} missing")
            continue
        node = var_to_assign[var]
        call = node.value
        if not isinstance(call, ast.Call) or not call.keywords:
            skipped.append(f"{fn}: {var} not a kwargs Call")
            continue

        if any(kw.arg == "setup_interceptors" for kw in call.keywords):
            skipped.append(f"{fn}: {var} already has setup_interceptors (defensive)")
            continue

        last_kw = call.keywords[-1]
        indent = " " * last_kw.col_offset
        new_line = f"{indent}setup_interceptors={fn},"

        end_lineno = call.end_lineno
        if end_lineno is None:
            skipped.append(f"{fn}: {var} no end_lineno")
            continue
        # Multi-line case: closing ')' on its own line.
        close_line_idx = end_lineno - 1
        close_line = lines[close_line_idx]
        if close_line.strip() != ")":
            skipped.append(f"{fn}: {var} closing line not bare ')' (got {close_line!r})")
            continue

        lines.insert(close_line_idx, new_line)
        inserted += 1

    if inserted:
        path.write_text("\n".join(lines))
    return inserted, skipped


def main() -> None:
    triage = json.loads(TRIAGE_PATH.read_text())
    trivial = [r for r in triage["rows"] if r["category"] == "trivial"]
    by_file: dict[str, list[dict]] = defaultdict(list)
    for r in trivial:
        by_file[r["set"]].append(r)

    total_inserted = 0
    total_skipped: list[str] = []
    for filename, rows in by_file.items():
        inserted, skipped = wire_file(filename, rows)
        total_inserted += inserted
        total_skipped.extend(f"{filename}::{s}" for s in skipped)
        print(f"{filename:32s} wired={inserted:3d} skipped={len(skipped):3d} (of {len(rows)} trivial)")

    print(f"\nTotal: wired {total_inserted}, skipped {len(total_skipped)}")
    if total_skipped:
        print("\nSkipped reasons:")
        for s in total_skipped:
            print(f"  {s}")


if __name__ == "__main__":
    main()
