"""Per-set briefings for Phase 3 (equipment + aura attach)."""
from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS_DIR = ROOT / "src" / "cards"
OUT_DIR = ROOT / ".phase3_briefings"

SET_FILES = [
    "wilds_of_eldraine.py", "lost_caverns_ixalan.py", "murders_karlov_manor.py",
    "outlaws_thunder_junction.py", "bloomburrow.py", "duskmourn.py",
    "foundations.py", "edge_of_eternities.py", "lorwyn_eclipsed.py",
    "spider_man.py", "avatar_tla.py", "final_fantasy.py",
]


def is_noop(fn):
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    return len(body) == 1 and isinstance(body[0], ast.Return) and isinstance(body[0].value, ast.List) and not body[0].value.elts


def main():
    OUT_DIR.mkdir(exist_ok=True)
    inline_dir = OUT_DIR / "inline"
    inline_dir.mkdir(exist_ok=True)

    for fname in SET_FILES:
        path = CARDS_DIR / fname
        src = path.read_text()
        tree = ast.parse(src)
        cards = {}
        for n in tree.body:
            if not isinstance(n, ast.Assign) or not isinstance(n.value, ast.Call):
                continue
            if not isinstance(n.targets[0], ast.Name):
                continue
            var = n.targets[0].id
            factory = n.value.func.id if isinstance(n.value.func, ast.Name) else "?"
            text = None
            setup = None
            for kw in n.value.keywords:
                if kw.arg == "text" and isinstance(kw.value, ast.Constant):
                    text = kw.value.value
                if kw.arg == "setup_interceptors" and isinstance(kw.value, ast.Name):
                    setup = kw.value.id
            if text:
                cards[var] = {
                    "factory": factory, "text": text, "setup": setup,
                    "lineno": n.lineno,
                }
        noops = {
            f.name for f in ast.walk(tree)
            if isinstance(f, ast.FunctionDef) and is_noop(f)
        }

        rows = []
        for var, info in cards.items():
            text_lower = info["text"].lower()
            is_equipment = info["factory"] == "make_equipment" or "equip {" in text_lower
            is_aura = re.match(r"^\s*enchant ", text_lower) is not None
            has_static = re.search(r"(equipped|enchanted) creature (gets|has)", text_lower) is not None

            if not (is_equipment or (is_aura and has_static)):
                continue

            state = "unwired" if info["setup"] is None else (
                "noop" if info["setup"] in noops else "wired"
            )
            if state == "wired":
                continue

            kind = "equipment" if is_equipment else "aura"
            rows.append({
                "card_var": var,
                "factory": info["factory"],
                "setup_fn": info["setup"],
                "card_text": info["text"],
                "state": state,
                "kind": kind,
                "card_lineno": info["lineno"],
            })

        out_path = OUT_DIR / fname.replace(".py", ".json")
        out_path.write_text(json.dumps({
            "set_file": fname,
            "rows": rows,
            "total": len(rows),
        }, indent=2))

        # Inline markdown
        lines = []
        for r in rows:
            lines.append(f"### {r['card_var']} ({r['kind']}, state={r['state']}, factory={r['factory']}, setup={r['setup_fn']}, line {r['card_lineno']})")
            lines.append(f"Text: {r['card_text']!r}")
            lines.append("")
        (inline_dir / fname.replace(".py", ".md")).write_text("\n".join(lines))

        print(f"{fname:<32}{len(rows):>4} cards")


if __name__ == "__main__":
    main()
