"""Categorize bare-`return []` setup functions by what kind of card they're for.

For every noop setup, find the matched card and inspect its `text=` field.
Bucket by: activated-only, replacement, static-pt, lord, modal/targeting,
saga, equipment-static, mechanic-specific, or unclassified.
"""
from __future__ import annotations

import ast
import re
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


def is_top_level_empty_return(fn: ast.FunctionDef) -> bool:
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))]
    return len(body) == 1 and isinstance(body[0], ast.Return) and isinstance(body[0].value, ast.List) and len(body[0].value.elts) == 0


def categorize(text: str | None) -> str:
    if not text:
        return "no_text"
    t = text.lower()
    # Activated ability — pattern "{cost}: effect" or "{cost}, {T}: effect"
    if re.search(r"\{[^}]+\}\s*:|\{[^}]+\}\s*,.*:\s", text):
        # But also has triggered? E.g. some cards have both
        if any(kw in t for kw in ["whenever", "when ~ enters", "when this"]):
            return "activated+triggered"
        return "activated_only"
    # Replacement effects
    if "instead" in t or "if you would" in t or "as ~" in t or "as this creature" in t:
        return "replacement"
    # Static P/T (lord)
    if re.search(r"other.*creatures.*you control.*get \+\d", t) or re.search(r"creatures you control get \+\d", t):
        return "lord_pt"
    # Static keyword grant
    if re.search(r"creatures you control have", t):
        return "lord_keyword"
    # Self pump / static
    if re.search(r"this creature gets \+", t) or re.search(r"~ gets \+", t):
        return "self_static_pt"
    # Saga
    if "lore counter" in t or "(this saga" in t or re.search(r"\bi+\s*[—-]", text):
        return "saga"
    # Equipment / aura attached effects
    if "equipped creature" in t or "enchanted creature" in t or "equip {" in t:
        return "equipment_aura_static"
    # Modal / targeting
    if "choose one" in t or "choose two" in t or "target" in t:
        return "modal_or_target"
    # Specific mechanics
    for mech in ["disguise", "suspect", "collect evidence", "crime", "warp", "void", "station",
                 "lander", "manifest dread", "unlock", "saddle", "plot", "offspring",
                 "expend", "valiant", "training", "explore", "discover", "descend",
                 "craft", "bargain", "celebration", "spree", "freerunning", "impending",
                 "max speed", "harmonize", "exhaust", "bending", "web-slinging",
                 "mayhem", "evoke", "champion", "clash", "hideaway", "conspire",
                 "convoke", "delve", "affinity", "dredge", "morph", "kicker"]:
        if mech in t:
            return f"mechanic:{mech}"
    return "unclassified"


def main() -> None:
    bucket = Counter()
    samples: dict[str, list[str]] = defaultdict(list)
    total_noops = 0

    for fname in SET_FILES:
        path = CARDS_DIR / fname
        tree = ast.parse(path.read_text())

        # Build var -> card data
        cards_by_setup_fn: dict[str, dict] = {}
        for n in tree.body:
            if not isinstance(n, ast.Assign) or not isinstance(n.value, ast.Call):
                continue
            setup_fn = None
            text = None
            for kw in n.value.keywords:
                if kw.arg == "setup_interceptors" and isinstance(kw.value, ast.Name):
                    setup_fn = kw.value.id
                if kw.arg == "text" and isinstance(kw.value, ast.Constant):
                    text = kw.value.value
            if setup_fn:
                tgt = n.targets[0].id if isinstance(n.targets[0], ast.Name) else "?"
                cards_by_setup_fn[setup_fn] = {"var": tgt, "text": text}

        # For each noop function, classify
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and n.name in cards_by_setup_fn and n.name.endswith("_setup"):
                if is_top_level_empty_return(n):
                    card = cards_by_setup_fn[n.name]
                    cat = categorize(card["text"])
                    bucket[cat] += 1
                    total_noops += 1
                    if len(samples[cat]) < 3:
                        samples[cat].append(f"  {fname[:8]} :: {card['var']} — {(card['text'] or '')[:90]!r}")

    print(f"Total bare-return-[] noops: {total_noops}")
    print()
    print(f"{'category':<30}{'count':>8}")
    print("-" * 38)
    for cat, count in bucket.most_common():
        print(f"{cat:<30}{count:>8}")
    print()
    print("Samples per category (top 8):")
    for cat, count in bucket.most_common(8):
        print(f"\n[{cat}] ({count} cards)")
        for s in samples[cat]:
            print(s)


if __name__ == "__main__":
    main()
