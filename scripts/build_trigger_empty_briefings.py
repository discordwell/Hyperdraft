"""For each setup_interceptors function that registers a trigger but
whose effect_fn body returns [], write a per-set briefing.

The agent reading the briefing decides whether to fill in the effect with
a real Event-emitting body, or leave it (engine gap remains).
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS_DIR = ROOT / "src" / "cards"
OUT_DIR = ROOT / ".trigger_empty_briefings"

SET_FILES = [
    "wilds_of_eldraine.py", "lost_caverns_ixalan.py", "murders_karlov_manor.py",
    "outlaws_thunder_junction.py", "bloomburrow.py", "duskmourn.py",
    "foundations.py", "edge_of_eternities.py", "lorwyn_eclipsed.py",
    "spider_man.py", "avatar_tla.py", "final_fantasy.py",
]

HELPER_NAMES = {
    "make_etb_trigger", "make_death_trigger", "make_attack_trigger",
    "make_damage_trigger", "make_static_pt_boost", "make_keyword_grant",
    "make_upkeep_trigger", "make_spell_cast_trigger", "make_end_step_trigger",
    "make_tap_trigger", "make_life_gain_trigger", "make_draw_trigger",
}


def has_event_emitted(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Event":
            return True
    return False


def is_top_level_empty_return(fn: ast.FunctionDef) -> bool:
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))]
    return (len(body) == 1
            and isinstance(body[0], ast.Return)
            and isinstance(body[0].value, ast.List)
            and len(body[0].value.elts) == 0)


def is_trigger_empty(fn: ast.FunctionDef) -> bool:
    """Registers a trigger via helper or constructs Interceptor, but emits no Events."""
    if is_top_level_empty_return(fn):
        return False
    if has_event_emitted(fn):
        return False
    helper_calls = sum(
        1 for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in HELPER_NAMES
    )
    has_interceptor = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Interceptor"
        for n in ast.walk(fn)
    )
    return helper_calls > 0 or has_interceptor


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    summary = {}

    for fname in SET_FILES:
        path = CARDS_DIR / fname
        src = path.read_text()
        tree = ast.parse(src)
        lines = src.splitlines()

        # Map setup_fn -> card data
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
                cards_by_setup[setup_fn] = {"var": var, "text": text, "factory": factory}

        rows = []
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and n.name in cards_by_setup and is_trigger_empty(n):
                card = cards_by_setup[n.name]
                fn_body = "\n".join(lines[n.lineno - 1: n.end_lineno])
                rows.append({
                    "fn": n.name,
                    "card_var": card["var"],
                    "factory": card["factory"],
                    "card_text": card["text"],
                    "fn_lineno": n.lineno,
                    "fn_end_lineno": n.end_lineno,
                    "fn_body": fn_body,
                })

        out = OUT_DIR / fname.replace(".py", ".json")
        out.write_text(json.dumps({
            "set_file": fname,
            "trigger_empty_count": len(rows),
            "cards": rows,
        }, indent=2))
        summary[fname] = len(rows)

    total = sum(summary.values())
    print(f"{'set':<32}{'trigger_empty':>15}")
    print("-" * 47)
    for s, n in summary.items():
        print(f"{s:<32}{n:>15}")
    print("-" * 47)
    print(f"{'TOTAL':<32}{total:>15}")


if __name__ == "__main__":
    main()
