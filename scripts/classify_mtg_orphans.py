"""Triage orphan setup_interceptors functions across real MTG set files.

For each *_setup function defined but never referenced via setup_interceptors=,
attempt to match it to a card by name and classify by complexity so we can
decide which orphans are safe to auto-wire vs. which need agent review.
"""
from __future__ import annotations

import ast
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS_DIR = ROOT / "src" / "cards"

SET_FILES = [
    "wilds_of_eldraine.py",
    "lost_caverns_ixalan.py",
    "murders_karlov_manor.py",
    "outlaws_thunder_junction.py",
    "bloomburrow.py",
    "duskmourn.py",
    "foundations.py",
    "edge_of_eternities.py",
    "lorwyn_eclipsed.py",
    "spider_man.py",
    "avatar_tla.py",
    "final_fantasy.py",
]

KNOWN_HELPERS = {
    "make_etb_trigger",
    "make_death_trigger",
    "make_attack_trigger",
    "make_damage_trigger",
    "make_static_pt_boost",
    "make_keyword_grant",
    "make_upkeep_trigger",
    "make_spell_cast_trigger",
}


def fn_name_to_card_name(fn: str) -> str:
    """honored_knightcaptain_setup -> 'Honored Knightcaptain' (rough display only)."""
    base = fn[: -len("_setup")] if fn.endswith("_setup") else fn
    return " ".join(w.capitalize() for w in base.split("_"))


def slugify(name: str) -> str:
    """Card name -> underscore slug for fuzzy matching with function base names."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def fuzzy_match_card(fn_base: str, slug_to_card: dict[str, dict]) -> dict | None:
    """Match an orphan setup function to a card by slug. Try exact, then prefix."""
    if fn_base in slug_to_card:
        return slug_to_card[fn_base]
    # The function name is often a truncated card slug. Find the longest card
    # slug that the function name extends, or vice-versa.
    best: tuple[int, dict] | None = None
    for slug, card in slug_to_card.items():
        if fn_base.startswith(slug + "_") or slug.startswith(fn_base + "_") or fn_base == slug:
            score = min(len(slug), len(fn_base))
            if best is None or score > best[0]:
                best = (score, card)
    return best[1] if best else None


def load(path: Path) -> tuple[ast.Module, list[str]]:
    src = path.read_text()
    return ast.parse(src), src.splitlines()


def find_setup_functions(tree: ast.Module) -> list[tuple[str, int, int]]:
    return [
        (n.name, n.lineno, n.end_lineno or n.lineno)
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name.endswith("_setup")
    ]


def find_wired_setup_names(tree: ast.Module) -> set[str]:
    wired: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.keyword) and n.arg == "setup_interceptors":
            v = n.value
            if isinstance(v, ast.Name):
                wired.add(v.id)
    return wired


def find_card_definitions(tree: ast.Module) -> list[dict]:
    """Find module-level UPPER_VAR = make_*(...) assignments, capture name/text/setup_ref."""
    cards: list[dict] = []
    for n in tree.body:
        if not isinstance(n, ast.Assign) or len(n.targets) != 1:
            continue
        tgt = n.targets[0]
        if not isinstance(tgt, ast.Name):
            continue
        if not isinstance(n.value, ast.Call):
            continue
        call = n.value
        if not (isinstance(call.func, ast.Name) and call.func.id.startswith("make_")):
            continue
        info = {
            "var": tgt.id,
            "factory": call.func.id,
            "lineno": n.lineno,
            "end_lineno": n.end_lineno or n.lineno,
            "name": None,
            "text": None,
            "setup_ref": None,
        }
        for kw in call.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                info["name"] = kw.value.value
            elif kw.arg == "text" and isinstance(kw.value, ast.Constant):
                info["text"] = kw.value.value
            elif kw.arg == "setup_interceptors" and isinstance(kw.value, ast.Name):
                info["setup_ref"] = kw.value.id
        cards.append(info)
    return cards


STUB_PATTERNS = [
    re.compile(r"return\s+\[\]\s*#"),
    re.compile(r"#\s*Target selection required", re.I),
    re.compile(r"#\s*TODO", re.I),
    re.compile(r"#\s*FIXME", re.I),
    re.compile(r"#\s*requires"),
    re.compile(r"pass\s*$", re.M),
]

HELPER_CALL_RE = re.compile(r"\bmake_[a-z_]+\b")


def classify(body: str, matched: dict | None) -> tuple[str, dict]:
    helpers = HELPER_CALL_RE.findall(body)
    helpers = [h for h in helpers if h in KNOWN_HELPERS or h.startswith("make_")]
    unknown_helpers = [h for h in set(helpers) if h not in KNOWN_HELPERS]
    has_stub = any(p.search(body) for p in STUB_PATTERNS)
    has_targeting = "target" in body.lower() and "Target selection" in body

    facts = {
        "helpers": sorted(set(helpers)),
        "helper_count": len(set(helpers)),
        "unknown_helpers": unknown_helpers,
        "has_stub_marker": has_stub,
        "lines": body.count("\n") + 1,
    }

    if matched is None:
        return "name_mismatch", facts
    if unknown_helpers:
        return "unknown_helper", facts
    if has_stub:
        return "stub", facts
    if facts["helper_count"] >= 2 or facts["lines"] > 25:
        return "multi_ability", facts
    return "trivial", facts


def main() -> None:
    rows: list[dict] = []
    per_set_summary: dict[str, dict] = {}

    for fname in SET_FILES:
        path = CARDS_DIR / fname
        tree, source_lines = load(path)
        setup_fns = find_setup_functions(tree)
        wired = find_wired_setup_names(tree)
        cards = find_card_definitions(tree)
        slug_to_card: dict[str, dict] = {}
        for c in cards:
            if c["name"]:
                slug = slugify(c["name"])
                # Keep the first card definition for each slug (avoid silent overwrite
                # when a set defines duplicates — flag in stderr if encountered).
                if slug not in slug_to_card:
                    slug_to_card[slug] = c

        orphans = [(n, s, e) for n, s, e in setup_fns if n not in wired]

        per_set_summary[fname] = {
            "total_cards": len(cards),
            "setup_fns": len(setup_fns),
            "wired_fns": len(wired),
            "orphan_fns": len(orphans),
        }

        for fn, start, end in orphans:
            body = "\n".join(source_lines[start - 1 : end])
            fn_base = fn[: -len("_setup")] if fn.endswith("_setup") else fn
            expected = fn_name_to_card_name(fn)
            matched = fuzzy_match_card(fn_base, slug_to_card)
            # Don't auto-wire if the matched card already references a *different*
            # setup function — the orphan would be duplicate logic for the same card.
            duplicate_of = matched["setup_ref"] if matched and matched.get("setup_ref") else None
            category, facts = classify(body, matched)
            if duplicate_of:
                category = "duplicate"
            text_excerpt = (matched["text"][:120] if matched and matched["text"] else None)
            rows.append({
                "set": fname,
                "fn": fn,
                "expected_card_name": expected,
                "matched_card_var": matched["var"] if matched else None,
                "matched_card_factory": matched["factory"] if matched else None,
                "matched_card_name": matched["name"] if matched else None,
                "card_text_excerpt": text_excerpt,
                "duplicate_of": duplicate_of,
                "category": category,
                "lineno": start,
                "end_lineno": end,
                **facts,
            })

    out = ROOT / "orphan_triage.json"
    out.write_text(json.dumps({
        "rows": rows,
        "per_set_summary": per_set_summary,
    }, indent=2))

    print(f"Wrote {out} with {len(rows)} orphan rows.\n")
    print("Per-set summary:")
    print(f"{'set':<32}{'cards':>7}{'setup':>7}{'wired':>7}{'orphan':>8}")
    for s, info in per_set_summary.items():
        print(f"{s:<32}{info['total_cards']:>7}{info['setup_fns']:>7}"
              f"{info['wired_fns']:>7}{info['orphan_fns']:>8}")

    cat_counts = Counter(r["category"] for r in rows)
    print("\nBy category:")
    for cat, count in cat_counts.most_common():
        print(f"  {cat:<20}{count}")

    print("\nBy set x category:")
    cats = sorted(cat_counts)
    header = f"{'set':<32}" + "".join(f"{c[:14]:>15}" for c in cats)
    print(header)
    by_sc: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        by_sc[(r["set"], r["category"])] += 1
    for s in SET_FILES:
        line = f"{s:<32}" + "".join(f"{by_sc.get((s, c), 0):>15}" for c in cats)
        print(line)


if __name__ == "__main__":
    main()
