"""For each MTG set, find cards with activated abilities that are not yet
wired (or are wired-but-noop) and emit a per-set briefing JSON listing the
cards along with their cost/effect text.

Run from the repo root:
    python scripts/build_phase4_briefings.py
"""
from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS_DIR = ROOT / "src" / "cards"
OUT_DIR = ROOT / ".phase4_briefings"

SET_FILES = [
    "wilds_of_eldraine.py", "lost_caverns_ixalan.py", "murders_karlov_manor.py",
    "outlaws_thunder_junction.py", "bloomburrow.py", "duskmourn.py",
    "foundations.py", "edge_of_eternities.py", "lorwyn_eclipsed.py",
    "spider_man.py", "avatar_tla.py", "final_fantasy.py",
]

# Activated ability lines: cost-and-colon-and-effect on a single line.
# Cost = mana symbols and/or +-N (loyalty) and/or "Sacrifice ..." / "Discard ..." etc.
ACT_LINE_RE = re.compile(
    r"^\s*((?:[{][^}]+[}](?:\s*,\s*[^,:]+)*)|(?:[+\-−]\d+))\s*:\s*(.+?)\.\s*$",
    re.M,
)


def is_noop(fn: ast.FunctionDef) -> bool:
    body = [
        s for s in fn.body
        if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                and isinstance(s.value.value, str))
    ]
    return (
        len(body) == 1
        and isinstance(body[0], ast.Return)
        and isinstance(body[0].value, ast.List)
        and len(body[0].value.elts) == 0
    )


def is_trivial_mana_only(cost: str, effect: str) -> bool:
    """Filter out pure mana abilities like ``{T}: Add {R}`` (already supported)."""
    return cost.strip() == "{T}" and re.match(r"^add \{[^}]+\}", effect.strip().lower()) is not None


def is_loyalty(cost: str) -> bool:
    return bool(re.match(r"^[+\-−]\d+$", cost.strip()))


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    summary_rows = []

    for fname in SET_FILES:
        path = CARDS_DIR / fname
        src = path.read_text()
        tree = ast.parse(src)

        cards_by_var: dict[str, dict] = {}
        for n in tree.body:
            if not isinstance(n, ast.Assign) or not isinstance(n.value, ast.Call):
                continue
            if not isinstance(n.targets[0], ast.Name):
                continue
            var = n.targets[0].id
            setup_fn = None
            text = None
            factory = n.value.func.id if isinstance(n.value.func, ast.Name) else "?"
            for kw in n.value.keywords:
                if kw.arg == "setup_interceptors" and isinstance(kw.value, ast.Name):
                    setup_fn = kw.value.id
                if kw.arg == "text" and isinstance(kw.value, ast.Constant):
                    text = kw.value.value
            if text:
                cards_by_var[var] = {
                    "setup_fn": setup_fn,
                    "text": text,
                    "factory": factory,
                    "card_lineno": n.lineno,
                    "card_end_lineno": n.value.end_lineno,
                }

        noop_setups = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and is_noop(n):
                noop_setups.add(n.name)

        rows = []
        for var, info in cards_by_var.items():
            text = info["text"]
            matches = ACT_LINE_RE.findall(text)
            nontrivial = [
                (c, e) for c, e in matches
                if not is_trivial_mana_only(c, e) and not is_loyalty(c)
            ]
            if not nontrivial:
                continue

            setup_fn = info["setup_fn"]
            if setup_fn is None:
                state = "unwired"
            elif setup_fn in noop_setups:
                state = "noop"
            else:
                state = "wired"
                # Skip cards that already have something — agents should focus
                # on noop and unwired entries.
                continue

            rows.append({
                "card_var": var,
                "factory": info["factory"],
                "setup_fn": setup_fn,
                "card_text": text,
                "abilities": [{"cost": c, "effect": e} for c, e in nontrivial],
                "state": state,
                "card_lineno": info["card_lineno"],
                "card_end_lineno": info["card_end_lineno"],
            })

        out_path = OUT_DIR / fname.replace(".py", ".json")
        out_path.write_text(json.dumps({
            "set_file": fname,
            "rows": rows,
            "total": len(rows),
            "noop": sum(1 for r in rows if r["state"] == "noop"),
            "unwired": sum(1 for r in rows if r["state"] == "unwired"),
        }, indent=2))

        summary_rows.append((fname, len(rows), sum(1 for r in rows if r["state"] == "noop"),
                             sum(1 for r in rows if r["state"] == "unwired")))

    print(f"{'set':<32}{'total':>8}{'noop':>8}{'unwired':>8}")
    print("-" * 60)
    T = Counter()
    for fname, total, noop, unwired in summary_rows:
        print(f"{fname:<32}{total:>8}{noop:>8}{unwired:>8}")
        T['total'] += total
        T['noop'] += noop
        T['unwired'] += unwired
    print("-" * 60)
    print(f"{'TOTAL':<32}{T['total']:>8}{T['noop']:>8}{T['unwired']:>8}")


if __name__ == "__main__":
    main()
