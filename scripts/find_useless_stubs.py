"""Find setup_interceptors functions whose body is functionally a no-op.

A useless stub is one of:
  1. Body is literally `return []` with no triggers registered.
  2. Body returns a single helper-call but that helper's effect_fn returns
     []. (This DOES register a trigger though, so it's less useless — the
     engine fires the trigger but the effect is empty.)

We classify into:
  - 'noop'   : returns []  immediately. Trigger never fires. Equivalent to
               no setup_interceptors=.
  - 'trigger_empty' : registers a trigger (ETB / death / attack / etc.)
               whose inner effect_fn returns []. Useful as a hook for
               future engine work, but currently does nothing.
  - 'real'   : has at least one helper call AND emits at least one Event
               somewhere in the body.
"""
from __future__ import annotations

import ast
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS_DIR = ROOT / "src" / "cards"

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
    """True if any sub-node creates an Event(...) call."""
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Event":
            return True
    return False


def has_interceptor_constructor(node: ast.AST) -> bool:
    """True if any sub-node creates an Interceptor(...) directly."""
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Interceptor":
            return True
    return False


def is_top_level_empty_return(fn: ast.FunctionDef) -> bool:
    """True if the function's only top-level statement is `return []`
    (possibly preceded by a docstring).
    """
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))]
    if len(body) != 1:
        return False
    s = body[0]
    if not isinstance(s, ast.Return):
        return False
    v = s.value
    return isinstance(v, ast.List) and len(v.elts) == 0


def classify_setup(fn: ast.FunctionDef) -> str:
    """Return 'noop', 'trigger_empty', or 'real'.

    - noop: body is literally `return []` (no triggers, no interceptors).
    - trigger_empty: registers a trigger/interceptor but the effect_fn or
      handler returns []; firing the trigger does nothing.
    - real: registers something AND emits at least one Event somewhere.
    """
    helper_calls = sum(
        1 for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id in HELPER_NAMES
    )
    direct_interceptor = has_interceptor_constructor(fn)
    emits_event = has_event_emitted(fn)

    if is_top_level_empty_return(fn):
        return "noop"
    if helper_calls == 0 and not direct_interceptor:
        # Function body has logic but never registers anything. Useless.
        return "noop"
    if emits_event or direct_interceptor:
        # If it constructs Interceptor directly, the handler does whatever
        # the body says — assume real unless we can prove otherwise.
        # Likewise emits_event => real.
        return "real" if emits_event else "trigger_empty_or_static"
    return "trigger_empty"


def main() -> None:
    by_set: dict[str, Counter] = {}
    examples: dict[str, list[tuple[str, str]]] = defaultdict(list)
    grand = Counter()

    for fname in SET_FILES:
        path = CARDS_DIR / fname
        tree = ast.parse(path.read_text())

        # Build set of wired setup function names
        wired = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.keyword) and n.arg == "setup_interceptors":
                if isinstance(n.value, ast.Name):
                    wired.add(n.value.id)

        counts = Counter()
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and n.name in wired and n.name.endswith("_setup"):
                cls = classify_setup(n)
                counts[cls] += 1
                grand[cls] += 1
                if cls == "noop":
                    examples[fname].append((n.name, n.lineno))
        by_set[fname] = counts

    cats = ["real", "trigger_empty_or_static", "trigger_empty", "noop"]
    print(f"{'set':<32}" + "".join(f"{c[:10]:>11}" for c in cats) + f"{'total':>8}")
    print("-" * 80)
    for fname, counts in by_set.items():
        total = sum(counts.values())
        row = "".join(f"{counts.get(c, 0):>11}" for c in cats)
        print(f"{fname:<32}{row}{total:>8}")
    print("-" * 80)
    grand_total = sum(grand.values())
    print(f"{'TOTAL':<32}" + "".join(f"{grand[c]:>11}" for c in cats) + f"{grand_total:>8}")
    print()
    print(f"Bare-return-[] 'noop' setups: {grand['noop']} ({100*grand['noop']/grand_total:.1f}% of wired)")
    print(f"  These are functionally identical to NOT having setup_interceptors=.")
    print()
    print("First 5 noops per set with >5:")
    for fname, exs in examples.items():
        if len(exs) > 5:
            print(f"  {fname}: {len(exs)} noops, e.g.")
            for name, lineno in exs[:5]:
                print(f"    L{lineno:5d}  {name}")


if __name__ == "__main__":
    main()
