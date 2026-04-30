"""Find MTG cards that have rules text but no setup_interceptors wired.

For every `UPPER_VAR = make_*(...)` card, check:
- Is there a setup_interceptors= keyword? If yes, skip.
- Does the `text=` field contain anything beyond bare keyword keywords
  (flying / trample / etc.) and reminder text? If no, skip — vanilla.
- Otherwise, this card needs a setup function. Record it.

Outputs `.missing_briefings/<set>.json` per set with the missing cards.
"""
from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS_DIR = ROOT / "src" / "cards"
OUT_DIR = ROOT / ".missing_briefings"

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

# Single-word keywords that need NO setup function — handled by make_creature
# factories or the engine's keyword system. A card whose entire rules text is
# a comma-separated list of these is "vanilla-ish" and skipped.
KEYWORD_ABILITIES = {
    "flying", "trample", "first strike", "double strike", "deathtouch",
    "haste", "hexproof", "indestructible", "lifelink", "menace", "reach",
    "vigilance", "ward", "defender", "flash", "protection", "shroud",
    "intimidate", "infect", "wither", "fear", "horsemanship", "skulk",
    "prowess", "convoke", "delve", "flashback", "scry", "exalted",
    "cycling", "morph", "kicker", "rebound", "buyback", "echo",
    "regenerate", "shadow", "evolve", "extort", "annihilator", "soulbond",
    "miracle", "overload", "evoke", "champion", "amplify", "absorb",
    "battle cry", "living weapon", "undying", "persist", "bushido",
    "ninjutsu", "dredge", "transmute", "haunt", "dash", "renown",
    "myriad", "emerge", "escalate", "melee", "crew", "fabricate",
    "improvise", "aftermath", "embalm", "eternalize", "afflict", "ascend",
    "jump-start", "mentor", "afterlife", "spectacle", "riot", "adapt",
    "amass", "addendum", "proliferate", "escape", "mutate", "companion",
    "boast", "foretell", "disturb", "daybound", "nightbound", "decayed",
    "training", "blitz", "casualty", "compleated", "hideaway", "alliance",
    "domain", "read ahead", "ravenous", "channel", "ninjutsu", "reconfigure",
    "soulshift", "splice", "graft", "modular", "outlast", "renown",
    "sunburst", "delirium", "investigate", "madness", "skulk",
    "surveil", "undergrowth", "spectacle", "akashik record", "convoke",
    "encore", "magecraft", "learn", "ward", "double team", "myriad",
    "manifest", "manifold", "bestow", "tribute", "outlaw",
    "celebration", "plot", "spree", "saddle", "bargain", "disguise",
    "discover", "disguise", "expend", "freerunning", "harmonize",
    "impending", "max speed", "offspring", "offspring", "eerie",
    "enrage", "boast", "nightbound", "daybound", "exploit", "support",
}

# Common "reminder text" / parenthetical patterns we strip when checking.
REMINDER_RE = re.compile(r"\([^)]+\)")


def looks_vanilla(text: str | None) -> bool:
    """True if the text field is empty or pure keyword abilities only."""
    if not text:
        return True
    cleaned = REMINDER_RE.sub("", text).strip()
    if not cleaned:
        return True
    # Split on commas, semicolons, newlines — examine each clause.
    clauses = [c.strip().lower() for c in re.split(r"[,;\n]+", cleaned) if c.strip()]
    for c in clauses:
        # Keyword with N (e.g. "ward 2", "ninjutsu {1}{B}", "scry 1")
        # Strip trailing tokens after the first word/phrase to test.
        c_norm = re.sub(r"[^a-z\s]+", "", c).strip()
        # Walk down possible keyword phrases
        words = c_norm.split()
        if not words:
            continue
        # Try the longest match first (e.g. "first strike", "double strike").
        matched = False
        for take in (3, 2, 1):
            phrase = " ".join(words[:take])
            if phrase in KEYWORD_ABILITIES:
                matched = True
                break
        if not matched:
            return False
    return True


def find_card_definitions(tree: ast.Module) -> list[dict]:
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
            "end_lineno": call.end_lineno or n.end_lineno or n.lineno,
            "name": None,
            "text": None,
            "has_setup": False,
        }
        for kw in call.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                info["name"] = kw.value.value
            elif kw.arg == "text" and isinstance(kw.value, ast.Constant):
                info["text"] = kw.value.value
            elif kw.arg == "setup_interceptors":
                info["has_setup"] = True
        cards.append(info)
    return cards


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    summary: dict[str, dict] = {}

    for fname in SET_FILES:
        path = CARDS_DIR / fname
        tree = ast.parse(path.read_text())
        cards = find_card_definitions(tree)

        # Instants and sorceries don't use setup_interceptors — their effects
        # are handled via cast effects elsewhere in the engine. Skip them.
        SPELL_FACTORIES = {"make_instant", "make_sorcery"}

        wired = [c for c in cards if c["has_setup"]]
        spells = [c for c in cards if c["factory"] in SPELL_FACTORIES]
        permanents = [c for c in cards if c["factory"] not in SPELL_FACTORIES]
        vanilla = [c for c in permanents if not c["has_setup"] and looks_vanilla(c["text"])]
        missing = [c for c in permanents if not c["has_setup"] and not looks_vanilla(c["text"])]

        summary[fname] = {
            "total": len(cards),
            "wired": len(wired),
            "spells": len(spells),
            "vanilla": len(vanilla),
            "missing": len(missing),
        }

        out = OUT_DIR / fname.replace(".py", ".json")
        out.write_text(json.dumps({
            "set_file": fname,
            "missing_count": len(missing),
            "cards": missing,
        }, indent=2))

    print(f"{'set':<32}{'total':>7}{'wired':>7}{'spells':>8}{'vanilla':>9}{'missing':>9}")
    print("-" * 73)
    grand = Counter()
    for fname, info in summary.items():
        print(f"{fname:<32}{info['total']:>7}{info['wired']:>7}{info['spells']:>8}"
              f"{info['vanilla']:>9}{info['missing']:>9}")
        for k in ("total", "wired", "spells", "vanilla", "missing"):
            grand[k] += info[k]
    print("-" * 73)
    print(f"{'TOTAL':<32}{grand['total']:>7}{grand['wired']:>7}{grand['spells']:>8}"
          f"{grand['vanilla']:>9}{grand['missing']:>9}")


if __name__ == "__main__":
    main()
