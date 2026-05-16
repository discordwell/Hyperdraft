"""Strict noop audit — purely structural detection of useless setup_interceptors.

This script is the authoritative cross-check on ``find_useless_stubs.py``.
Unlike that script, this one has NO helper-name allowlist. It only flags
setup functions whose body is *literally* a bare ``return []`` (optionally
preceded by a docstring).

A "strict noop" is a function whose effective behaviour is identical to
not passing ``setup_interceptors=`` at all. The trigger never fires, no
interceptor is registered, no replacement effect is installed. Side-effect
helper calls (e.g. ``make_activated_ability(obj, ...)`` without a return
value) are EXCLUDED — those genuinely register abilities.

Output: per-set count + grand total + the file/line/function-name of every
strict noop. Optionally writes JSON for downstream tooling.

Usage::

    python scripts/strict_noop_audit.py                # text report
    python scripts/strict_noop_audit.py --json out.json # also dump JSON
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS_DIR = ROOT / "src" / "cards"

SET_FILES = [
    "wilds_of_eldraine.py", "lost_caverns_ixalan.py", "murders_karlov_manor.py",
    "outlaws_thunder_junction.py", "bloomburrow.py", "duskmourn.py",
    "foundations.py", "edge_of_eternities.py", "lorwyn_eclipsed.py",
    "spider_man.py", "avatar_tla.py", "final_fantasy.py",
]


def is_strict_noop(fn: ast.FunctionDef) -> bool:
    """Return True iff the function body, ignoring an optional leading
    docstring and pure ``Pass`` / comment-only statements, is exactly
    ``return []``.

    Comments don't appear in the AST at all, so the only "filler"
    statements we need to strip are:
      - a leading string-constant Expr (the docstring)
      - bare ``pass`` statements
    """
    body = []
    for stmt in fn.body:
        # Skip docstring
        if (isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)):
            continue
        # Skip bare `pass`
        if isinstance(stmt, ast.Pass):
            continue
        body.append(stmt)

    if len(body) != 1:
        return False
    s = body[0]
    if not isinstance(s, ast.Return):
        return False
    v = s.value
    return isinstance(v, ast.List) and len(v.elts) == 0


def is_delegated_setup(fn: ast.FunctionDef) -> bool:
    """Return True iff the function body is a single ``return some_setup(obj, state)``
    (delegating to another setup function). This is a *real* implementation,
    just by reference.
    """
    body = [s for s in fn.body
            if not (isinstance(s, ast.Expr)
                    and isinstance(s.value, ast.Constant)
                    and isinstance(s.value.value, str))]
    if len(body) != 1:
        return False
    s = body[0]
    if not isinstance(s, ast.Return):
        return False
    v = s.value
    if not isinstance(v, ast.Call):
        return False
    if not isinstance(v.func, ast.Name):
        return False
    # Must end with _setup and not be one of our recognised "useless" patterns
    return v.func.id.endswith("_setup") or v.func.id.endswith("_handler")


def collect_wired_setup_names(tree: ast.AST) -> set[str]:
    """Return the names of all functions referenced via ``setup_interceptors=``
    keyword arguments anywhere in the file.

    Also includes those bound to ``setup_in_graveyard=``.
    """
    names: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.keyword) and n.arg in {"setup_interceptors",
                                                     "setup_in_graveyard"}:
            v = n.value
            if isinstance(v, ast.Name):
                names.add(v.id)
            elif isinstance(v, ast.Attribute):
                # e.g. some_module.foo_setup — ignore (not local)
                pass
    return names


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", metavar="PATH",
                    help="Also dump structured results to this JSON file")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="List every strict-noop function, not just per-set counts")
    args = ap.parse_args()

    results: dict[str, dict] = {}
    grand_strict_noops: list[tuple[str, str, int, str]] = []
    grand_delegated: list[tuple[str, str, int, str]] = []
    grand_wired = 0

    for fname in SET_FILES:
        path = CARDS_DIR / fname
        if not path.is_file():
            print(f"[skip] {fname} not found", file=sys.stderr)
            continue
        tree = ast.parse(path.read_text())
        wired = collect_wired_setup_names(tree)
        grand_wired += len(wired)

        strict: list[tuple[str, int, str]] = []  # (name, lineno, docstring_head)
        delegated: list[tuple[str, int, str]] = []
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and n.name in wired:
                doc = ast.get_docstring(n) or ""
                doc_head = doc.split("\n", 1)[0][:160]
                if is_strict_noop(n):
                    strict.append((n.name, n.lineno, doc_head))
                    grand_strict_noops.append((fname, n.name, n.lineno, doc_head))
                elif is_delegated_setup(n):
                    delegated.append((n.name, n.lineno, doc_head))
                    grand_delegated.append((fname, n.name, n.lineno, doc_head))
        results[fname] = {
            "wired": len(wired),
            "strict_noop": len(strict),
            "delegated": len(delegated),
            "strict_noop_entries": [{"name": n, "lineno": l, "doc": d}
                                     for n, l, d in strict],
            "delegated_entries": [{"name": n, "lineno": l, "doc": d}
                                    for n, l, d in delegated],
        }

    # Pretty print
    print(f"{'set':<32}{'wired':>8}{'noop':>8}{'delegated':>12}")
    print("-" * 60)
    total_noop = 0
    total_delegated = 0
    for fname, data in results.items():
        print(f"{fname:<32}{data['wired']:>8}{data['strict_noop']:>8}"
              f"{data['delegated']:>12}")
        total_noop += data["strict_noop"]
        total_delegated += data["delegated"]
    print("-" * 60)
    print(f"{'TOTAL':<32}{grand_wired:>8}{total_noop:>8}{total_delegated:>12}")
    print()
    if grand_wired:
        print(f"Strict noops = {total_noop} "
              f"({100*total_noop/grand_wired:.1f}% of {grand_wired} wired setups)")
    print(f"Delegated setups (real-by-reference) = {total_delegated}")
    print()

    if args.verbose:
        print("Per-set strict noops:")
        for fname, data in results.items():
            entries = data["strict_noop_entries"]
            if not entries:
                continue
            print(f"\n  {fname} ({len(entries)} strict noops):")
            for e in entries:
                tag = f"L{e['lineno']:5d}"
                doc = e["doc"]
                print(f"    {tag}  {e['name']:<48}  {doc}")

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2))
        print(f"\nWrote JSON to {args.json}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
