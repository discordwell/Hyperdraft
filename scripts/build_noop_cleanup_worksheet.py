"""Build a per-card cleanup disposition for every bare-`return []` noop setup.

Dispositions:
  - 'strip_vanilla':  card text is purely keywords + reminder text. The
                      setup function adds nothing — remove the wiring.
  - 'strip_activated': card text is only activated abilities ({cost}: effect)
                       with no triggered or static abilities. The engine
                       handles activation through the cast pipeline, not via
                       setup_interceptors. Remove the wiring.
  - 'convert_static':  card has a self-static "gets +N/+M for each X" or
                       "gets +N/+M as long as Y" effect. Quick-win rewrite
                       to QUERY_POWER/QUERY_TOUGHNESS interceptor.
  - 'leave':           genuine engine gap — saga, replacement, modal,
                       equipment/aura static, mechanic-specific. Leave the
                       noop alone as a placeholder.
"""
from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS_DIR = ROOT / "src" / "cards"
OUT_PATH = ROOT / "noop_cleanup_worksheet.json"

SET_FILES = [
    "wilds_of_eldraine.py", "lost_caverns_ixalan.py", "murders_karlov_manor.py",
    "outlaws_thunder_junction.py", "bloomburrow.py", "duskmourn.py",
    "foundations.py", "edge_of_eternities.py", "lorwyn_eclipsed.py",
    "spider_man.py", "avatar_tla.py", "final_fantasy.py",
]

KEYWORD_RE = re.compile(
    r"^(?:flying|trample|first strike|double strike|deathtouch|haste|hexproof"
    r"|indestructible|lifelink|menace|reach|vigilance|defender|flash"
    r"|prowess|ward(?:\s+\{[^}]+\})?(?:\s+\d+)?|protection from \w+"
    r"|shroud|fear|intimidate|infect|wither|skulk)$",
    re.IGNORECASE,
)


def is_top_level_empty_return(fn: ast.FunctionDef) -> bool:
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))]
    return (len(body) == 1
            and isinstance(body[0], ast.Return)
            and isinstance(body[0].value, ast.List)
            and len(body[0].value.elts) == 0)


def strip_reminder(text: str) -> str:
    """Remove parenthetical reminder text."""
    return re.sub(r"\([^)]*\)", "", text).strip()


def split_clauses(text: str) -> list[str]:
    """Split text into clauses (lines / sentences)."""
    clauses = []
    for line in text.split("\n"):
        line = strip_reminder(line).strip()
        if not line:
            continue
        # Split on `.` but keep activated-ability `{cost}: effect` patterns intact.
        parts = re.split(r"(?<![{}])\.\s+", line)
        for p in parts:
            p = p.strip().rstrip(".")
            if p:
                clauses.append(p)
    return clauses


# A trigger pattern means the card has a real triggered ability.
TRIGGER_PATTERN = re.compile(
    r"\b(?:when(?:ever)?\s|at the beginning of)",
    re.IGNORECASE,
)
# A static pattern means a continuous +P/+T effect — must be conditional
# ("for each X" / "as long as Y"), NOT activated ("{cost}: gets +X/+Y") or
# until-end-of-turn ("gets +X/+Y until end of turn").
SELF_STATIC_PT = re.compile(
    r"(?:this creature\s+)?gets?\s*\+\d+/[+-]?\d+\s*(?:for each|as long as)\b",
    re.IGNORECASE,
)
# Lord pattern — passive +N/+N for other creatures of a type. Excludes
# activated "{cost}: ... get +1/+1 until end of turn" patterns.
LORD_PATTERN = re.compile(
    r"\bother\b[^.\n]*\bcreatures?\b[^.\n]*\byou control\b[^.\n]*\bget\s*\+\d+/[+-]?\d+(?!\s*until)",
    re.IGNORECASE,
)
# An until-end-of-turn pump is NOT a static effect — it's an activated
# ability or one-shot trigger. Used to disqualify false-positive matches.
UNTIL_EOT_RE = re.compile(r"until end of turn", re.IGNORECASE)
ACTIVATED_RE = re.compile(
    r"^\s*(?:\{[^}]+\}|[0-9]+)(?:\s*,\s*(?:\{[^}]+\}|sacrifice [^:]+|discard [^:]+|tap[^:]*|exile [^:]+|pay [^:]+))*\s*:",
    re.IGNORECASE,
)
REPLACEMENT_RE = re.compile(r"\binstead\b|\bif you would\b|\bas this (?:creature|artifact|enchantment) enters\b", re.IGNORECASE)
SAGA_RE = re.compile(r"lore counter|\bI(?:I|II)?\s*[—-]\s", re.IGNORECASE)
MODAL_RE = re.compile(r"choose (?:one|two|three)|target ", re.IGNORECASE)
EQUIP_AURA_RE = re.compile(r"equipped creature|enchanted creature|equip \{", re.IGNORECASE)

ENGINE_GAP_MECHANICS = [
    "disguise", "suspect", "collect evidence", "crime", "warp", "void",
    "station", "lander", "manifest dread", "unlock", "saddle", "plot",
    "offspring", "expend", "valiant", "training", "explore", "discover",
    "descend", "craft", "bargain", "celebration", "spree", "freerunning",
    "impending", "max speed", "harmonize", "exhaust", "bending", "web-slinging",
    "mayhem", "evoke", "champion", "clash", "hideaway", "conspire",
    "convoke", "delve", "affinity", "dredge", "morph", "kicker",
]


def categorize(text: str | None) -> tuple[str, str]:
    """Returns (disposition, reason)."""
    if not text:
        return "strip_vanilla", "no text"
    cleaned = strip_reminder(text)
    clauses = split_clauses(text)
    if not clauses:
        return "strip_vanilla", "empty after stripping reminders"

    # Check if every clause is just a keyword.
    all_keywords = all(KEYWORD_RE.match(c) for c in clauses)
    if all_keywords:
        return "strip_vanilla", "keyword-only"

    has_trigger = bool(TRIGGER_PATTERN.search(cleaned))
    # Only count static if there's no until-end-of-turn variant on the same line.
    static_match = SELF_STATIC_PT.search(cleaned)
    lord_match = LORD_PATTERN.search(cleaned)
    has_self_static = bool(static_match)
    has_lord = bool(lord_match)
    has_replacement = bool(REPLACEMENT_RE.search(cleaned))
    has_saga = bool(SAGA_RE.search(cleaned)) or "Saga" in (text or "")
    has_modal = bool(MODAL_RE.search(cleaned))
    has_equip_aura = bool(EQUIP_AURA_RE.search(cleaned))

    has_activated = any(ACTIVATED_RE.search(c) for c in clauses)

    cleaned_low = cleaned.lower()
    for mech in ENGINE_GAP_MECHANICS:
        if mech in cleaned_low:
            return "leave", f"mechanic:{mech}"

    if has_replacement:
        return "leave", "replacement effect"
    if has_saga:
        return "leave", "saga"
    if has_equip_aura:
        return "leave", "equipment/aura static"
    if has_trigger:
        return "leave", "has triggered ability (should be implemented)"
    if has_self_static or has_lord:
        return "convert_static", ("lord" if has_lord else "self_static")
    if has_modal:
        return "leave", "modal/target"
    if has_activated and not has_trigger and not has_self_static and not has_lord:
        # Only activated abilities — engine handles via cast pipeline.
        return "strip_activated", "activated-ability-only"

    return "leave", "unclassified — needs human review"


def main() -> None:
    rows: list[dict] = []
    for fname in SET_FILES:
        path = CARDS_DIR / fname
        tree = ast.parse(path.read_text())

        cards_by_setup: dict[str, dict] = {}
        for n in tree.body:
            if not isinstance(n, ast.Assign) or not isinstance(n.value, ast.Call):
                continue
            if not isinstance(n.targets[0], ast.Name):
                continue
            var = n.targets[0].id
            setup_fn = None
            text = None
            for kw in n.value.keywords:
                if kw.arg == "setup_interceptors" and isinstance(kw.value, ast.Name):
                    setup_fn = kw.value.id
                if kw.arg == "text" and isinstance(kw.value, ast.Constant):
                    text = kw.value.value
            if setup_fn:
                cards_by_setup[setup_fn] = {
                    "var": var, "text": text, "card_lineno": n.lineno, "card_end_lineno": n.value.end_lineno
                }

        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and n.name in cards_by_setup and is_top_level_empty_return(n):
                card = cards_by_setup[n.name]
                disposition, reason = categorize(card["text"])
                rows.append({
                    "set": fname,
                    "fn": n.name,
                    "card_var": card["var"],
                    "card_lineno": card["card_lineno"],
                    "card_end_lineno": card["card_end_lineno"],
                    "fn_lineno": n.lineno,
                    "fn_end_lineno": n.end_lineno,
                    "card_text": card["text"],
                    "disposition": disposition,
                    "reason": reason,
                })

    OUT_PATH.write_text(json.dumps(rows, indent=2))
    counts = Counter(r["disposition"] for r in rows)
    print(f"Wrote {OUT_PATH} with {len(rows)} noop rows.")
    print()
    for disp, count in counts.most_common():
        print(f"  {disp:<20} {count}")
    print()
    print("Per-set:")
    by_set_disp: dict[tuple, int] = {}
    for r in rows:
        key = (r["set"], r["disposition"])
        by_set_disp[key] = by_set_disp.get(key, 0) + 1
    sets = sorted({r["set"] for r in rows})
    disps = sorted(counts.keys())
    print(f"{'set':<32}" + "".join(f"{d[:14]:>16}" for d in disps))
    for s in sets:
        print(f"{s:<32}" + "".join(f"{by_set_disp.get((s,d), 0):>16}" for d in disps))


if __name__ == "__main__":
    main()
