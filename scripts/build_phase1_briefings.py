"""For every wired-but-noop setup function, classify by Phase 1 category
(modal/target/replacement/counter) and emit per-set JSON.
"""
from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS_DIR = ROOT / "src" / "cards"
OUT_DIR = ROOT / ".phase1_briefings"

SET_FILES = [
    "wilds_of_eldraine.py", "lost_caverns_ixalan.py", "murders_karlov_manor.py",
    "outlaws_thunder_junction.py", "bloomburrow.py", "duskmourn.py",
    "foundations.py", "edge_of_eternities.py", "lorwyn_eclipsed.py",
    "spider_man.py", "avatar_tla.py", "final_fantasy.py",
]

CATEGORIES = [
    # (label, pattern). First match wins.
    ("modal_or_target", re.compile(r"choose (?:one|two|three)|\btarget ", re.I)),
    ("replacement", re.compile(r"\binstead\b|\bif you would\b", re.I)),
    ("counter_manipulation", re.compile(r"counter on|remove a counter|put .* counter", re.I)),
]


def is_noop(fn: ast.FunctionDef) -> bool:
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))]
    return (len(body) == 1
            and isinstance(body[0], ast.Return)
            and isinstance(body[0].value, ast.List)
            and len(body[0].value.elts) == 0)


def categorize(text: str) -> str | None:
    for label, pattern in CATEGORIES:
        if pattern.search(text):
            return label
    return None


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    summary = {}
    for fname in SET_FILES:
        path = CARDS_DIR / fname
        src = path.read_text()
        tree = ast.parse(src)
        cards_by_setup: dict[str, dict] = {}
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
            if setup_fn:
                cards_by_setup[setup_fn] = {
                    "var": var, "text": text, "factory": factory,
                    "card_lineno": n.lineno, "card_end_lineno": n.value.end_lineno,
                }

        rows = []
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and n.name in cards_by_setup and is_noop(n):
                card = cards_by_setup[n.name]
                cat = categorize(card["text"] or "")
                if cat is None:
                    continue
                rows.append({
                    "fn": n.name,
                    "card_var": card["var"],
                    "factory": card["factory"],
                    "card_text": card["text"],
                    "fn_lineno": n.lineno,
                    "fn_end_lineno": n.end_lineno,
                    "card_lineno": card["card_lineno"],
                    "card_end_lineno": card["card_end_lineno"],
                    "category": cat,
                })

        cat_counts = Counter(r["category"] for r in rows)
        summary[fname] = (len(rows), cat_counts)
        out_path = OUT_DIR / fname.replace(".py", ".json")
        out_path.write_text(json.dumps({"set_file": fname, "rows": rows}, indent=2))

    print(f"{'set':<32}{'total':>7}  modal_or_target  replacement  counter")
    print("-" * 80)
    grand = Counter()
    for fname, (total, counts) in summary.items():
        print(f"{fname:<32}{total:>7}  "
              f"{counts.get('modal_or_target', 0):>15}  "
              f"{counts.get('replacement', 0):>11}  "
              f"{counts.get('counter_manipulation', 0):>7}")
        grand['total'] += total
        for k, v in counts.items():
            grand[k] += v
    print(f"\n{'TOTAL':<32}{grand['total']:>7}  "
          f"{grand['modal_or_target']:>15}  "
          f"{grand['replacement']:>11}  "
          f"{grand['counter_manipulation']:>7}")


if __name__ == "__main__":
    main()
