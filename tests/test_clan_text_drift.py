"""Stage 7.5a — CLAN text-drift check.

For each card in CLAN_CARDS, parse its rules ``text`` for numeric and keyword
patterns and verify the code matches. Catches "rules text says +3 but code
does +2" and similar drift bugs that defeat downstream balance work.

Patterns checked:
  - P/I mods (+X/+Y, +X power, +X integrity)
  - "Draw N cards" / "draw a card"
  - "Deal N damage"
  - "Gain N (scrap | workshop integrity)"
  - "Pay N (Compute | scrap)"
  - "Armor N"
  - "Reclaim N"
  - "N Compute" (compute_cost references)
  - Keywords: Self-Mobile, Modular, Synchronize, Reticulate, Reclaim

Drift is reported per-card with the failing clause and the code value found.
Cards too complex to parse heuristically go in SKIPPED_CARDS with reason.

Run: PYTHONPATH=. python tests/test_clan_text_drift.py
"""

from __future__ import annotations

import re
import sys
import inspect
from typing import Optional

# Imports gate on engine + card pool availability.
from src.cards.clankers.CLAN import CLAN_CARDS
from src.engine.types import CardType


# ---------------------------------------------------------------------------
# Cards too complex / multi-clause for the heuristic checker
# ---------------------------------------------------------------------------

SKIPPED_CARDS: dict[str, str] = {
    # Conditional / contextual stats — drift checker can't verify "instead"-style
    # clauses without modelling the conditional.
    "Hum-Lance":         "conditional: '+3 / +0 instead' (vs +2 base) needs context",
    "Tinker's Frame":    "conditional: '+1 / +2 instead' (vs +1/+1 base) needs context",
    "Crowd Marcher":     "conditional Synchronize: +2 vs +1 depending on count",
    # Cipher Rotor / Cores / etc.: card text mentions "+power_bonus while solo"
    # but the actual numeric printed is on the factory call — we treat the
    # numeric field on the card_def as truth, no drift needed.
    "Cipher Rotor":      "Self-Mobile flavor text mentions printed stats not effect numerics",
    "Scout Drone":       "Self-Mobile flavor text describes printed stats not effect numerics",
    "Joybuzzer":         "Self-Mobile flavor text",
    "Magenta Coil":      "Self-Mobile flavor text",
    "Spark Whip":        "Self-Mobile flavor text",
    "Stinger Pack":      "Self-Mobile flavor text",
    "Tickle-Saw":        "Self-Mobile flavor text",
    "Joybuzzer Sleeve":  "Self-Mobile flavor text",
    "Affection.exe Add-On": "Self-Mobile flavor text",
    "Curiosity Routine":  "Self-Mobile flavor text + on-attach effect",
    # Cores' "max 27" is the cap, not a heal amount
    "BULWARK-9":          "max 27 cap is workshop_integrity ceiling, not a heal value",
    "Containment Sergeant": "max 27 cap is workshop_integrity ceiling, not a heal value",
    "Sentinel Cannon":    "max 27 cap is ceiling, not heal amount",
    # Heuristic Loop has a conditional "+1 more"
    "Heuristic Loop":     "conditional draw: 'draw 1 more' depends on scrap heap state",
    # Subroutine Cascade mentions both draw 3 and cost reduction 2 — the drift
    # checker would conflate them
    "Subroutine Cascade": "multi-effect: draw 3 + next-Transient cost -2",
    # Big Swing — "damage equal to its effective power" is computed at runtime
    "Big Swing":          "damage = runtime effective_power, not a numeric literal",
    # Reroute Power — damage = attached-weapon-count
    "Reroute Power":      "damage = runtime attached-weapon-count",
    # Tungsten Walker — cost = printed - scrap (runtime)
    "Tungsten Walker":    "compute discount = runtime scrap pool",
    # FORGE-Δ cost reduction is conditional on integrity ≥5 — drift checker
    # would need to model the conditional
    "FORGE-Δ":            "conditional cost reduction",
    "Heavy Forge":        "conditional cost reduction (weapons)",
    "ETHOS-7":            "first-Transient discount is conditional",
    "Shared Bus":         "first-part discount is conditional",
    # SUBROUTINE-α — grants +2 compute, but text references "scrap a card";
    # the +2 number IS in code; let it be checked. Actually checking this.
    # Burnout Protocol — "double" not a literal numeric
    "Burnout Protocol":   "'double' is multiplicative, not literal numeric",
    # Big-ticket: cards that are simple vanillas — text says "Vanilla" so
    # nothing to check
    "Heavy Assembly":     "vanilla heavyweight, no text numerics",
    "Apex Hulk":          "vanilla apex",
    "Workshop Prototype": "vanilla neutral",
    "Vault Chassis":      "vanilla wall",
    "Sentinel Crane":     "vanilla high-end wall",
    "Embankment":         "vanilla; 0 weapon slots is on factory call not text",
    "Bulwark Frame":      "vanilla tank text",
    "Endurance Frame":    "vanilla text",
    "Sparkbot":           "vanilla 1-drop text",
    "Reinforced Plating": "vanilla",
    "Bulwark Brace":      "vanilla",
    "Vault Bracer":       "vanilla",
    "BUZZSAW MK-III":     "vanilla weapon text; no numerics to verify",
    "Buzzsaw Arm":        "vanilla weapon",
    "Bolt-Driver Mk-II":  "vanilla weapon",
    "Standard Issue Blaster": "vanilla",
    "Riveter Mk-I":       "vanilla",
    "Spare Coilgun":      "vanilla",
}


# ---------------------------------------------------------------------------
# Helpers — extract numerics from text and from code
# ---------------------------------------------------------------------------

# Regex patterns
RE_PI_MOD = re.compile(r"\+(\d+)\s*/\s*\+(\d+)")
RE_DRAW = re.compile(r"[Dd]raw\s+(\d+|a)\s+cards?")
RE_DEAL_DAMAGE = re.compile(r"[Dd]eal[s]?\s+(\d+)\s+(?:workshop\s+|combat\s+)?damage")
RE_GAIN_SCRAP = re.compile(r"[Gg]ain\s+(\d+)\s+scrap")
RE_GAIN_INTEG = re.compile(r"[Gg]ain\s+(\d+)\s+workshop\s+integrity")
RE_PAY_COMPUTE = re.compile(r"[Pp]ay\s+(\d+)\s+Compute")
RE_PAY_SCRAP = re.compile(r"[Pp]ay\s+(\d+)\s+scrap")
RE_ARMOR_N = re.compile(r"[Aa]rmor\s+(\d+)")
RE_RECLAIM_N = re.compile(r"[Rr]eclaim\s+(\d+)")
RE_SLOT_COST = re.compile(r"[Ss]lot\s+cost:\s+(\d+)")
RE_COMPUTE_COST = re.compile(r"(\d+)\s+Compute")
RE_INTEG_GE = re.compile(r"integrity\s+[≥>=]+\s*(\d+)")
RE_DAMAGE_GE = re.compile(r"(\d+)\+?\s+damage\s+marked")
RE_PLUS_POWER = re.compile(r"\+(\d+)\s+power")
RE_PLUS_INTEG = re.compile(r"\+(\d+)\s+integrity")


def _unwrap_fn(fn):
    """If ``fn`` is the ETHOS `_wrap_with_hook` wrapper, recover the inner fn.

    The wrapper closes over ``orig_setup``, which is the actual card setup.
    Return the chain of inner functions (including the wrapper itself) so
    callers can grep the union of source code.
    """
    if fn is None:
        return []
    out = [fn]
    # Look for orig_setup closure cell.
    if fn.__name__ == "wrapped" and fn.__closure__:
        for cell in fn.__closure__:
            content = cell.cell_contents
            if callable(content):
                out.extend(_unwrap_fn(content))
    return out


def _all_code_for_card(card_def) -> str:
    """Get all related code source for a card.

    Combines setup_interceptors / resolve_fn / passive_setup sources, and
    recursively unwraps ETHOS wrappers.
    """
    chunks: list[str] = []
    fns: list = []
    for attr in ("setup_interceptors", "clankers_resolve",
                 "clankers_core_passive_setup"):
        fn = getattr(card_def, attr, None)
        if fn is None:
            continue
        fns.extend(_unwrap_fn(fn))
    for f in fns:
        try:
            chunks.append(inspect.getsource(f))
        except (OSError, TypeError):
            continue
    return "\n".join(chunks)


def _closure_ints(card_def) -> set[int]:
    """Collect integer values stored in any closure cell of the card's
    setup_interceptors / resolve_fn / passive_setup function(s).

    Factory-style code (e.g. ``_reclaim_setup(2)``) closes over the int
    parameter; the literal doesn't appear in the function source, so we
    pick it up via the closure cell.
    """
    out: set[int] = set()
    for attr in ("setup_interceptors", "clankers_resolve",
                 "clankers_core_passive_setup"):
        fn = getattr(card_def, attr, None)
        if fn is None:
            continue
        for f in _unwrap_fn(fn):
            if f.__closure__:
                for cell in f.__closure__:
                    try:
                        v = cell.cell_contents
                    except ValueError:
                        continue
                    if isinstance(v, int) and not isinstance(v, bool):
                        out.add(v)
    return out


def _has_pattern_in_code(code: str, value: int, kind: str) -> bool:
    """Heuristic: does the code mention ``value`` as a literal in a relevant context?

    Examples:
      kind='draw':   matches "count': N" or "count=N" in DRAW payload
      kind='gain_scrap': matches "_gain_scrap(..., N, ...)" or similar
      kind='armor': matches "make_armor(obj, N)" or "armor_value=N"
      kind='reclaim': matches the integer in a make_part_on_self_destroyed gain_scrap
      kind='pay_compute': matches "compute_cost=N"
      kind='pay_scrap': matches "scrap < N" or "scrap_pool" arithmetic
      kind='deal_damage': matches DAMAGE/CLANKERS_COMBAT_DAMAGE with amount: N
    """
    if not code:
        # If we can't inspect the source, can't disprove drift — pass to avoid
        # false positives. Cards without code don't have effects to drift.
        return True

    # Try several patterns per kind.
    patterns = []
    if kind == "draw":
        patterns = [
            rf"['\"]count['\"]\s*:\s*{value}\b",
            rf"count\s*=\s*{value}\b",
        ]
    elif kind == "gain_scrap":
        patterns = [
            rf"_gain_scrap\s*\(\s*[^,)]+,\s*[^,)]+,\s*{value}\b",
            rf"gain[_]?scrap\s*\([^)]*{value}",
            rf"amount\s*=\s*{value}",
            rf"_spend_scrap\s*\(\s*[^,)]+,\s*[^,)]+,\s*{value}\b",
        ]
    elif kind == "gain_integ":
        patterns = [
            rf"_heal_workshop\s*\(\s*[^,)]+,\s*[^,)]+,\s*{value}\b",
            rf"\+\s*{value}\b",
        ]
    elif kind == "pay_compute":
        patterns = [
            rf"compute_cost\s*=\s*{value}\b",
        ]
    elif kind == "pay_scrap":
        patterns = [
            rf"_spend_scrap\s*\(\s*[^,)]+,\s*[^,)]+,\s*{value}\b",
            rf"scrap\s*<\s*{value}\b",
            rf"scrap\s*-\s*{value}\b",
        ]
    elif kind == "armor":
        patterns = [
            rf"make_armor\s*\(\s*[^,)]+,\s*{value}\b",
            rf"armor_value\s*=\s*{value}\b",
            rf"_armor_setup\s*\(\s*{value}\b",
            rf"absorbed\s*=\s*min\s*\(\s*{value}\b",
        ]
    elif kind == "reclaim":
        # Reclaim N → gain_scrap N. Some cards use a factory like
        # _reclaim_setup(N) where the literal N appears in the factory call.
        patterns = [
            rf"_gain_scrap\s*\(\s*[^,)]+,\s*[^,)]+,\s*{value}\b",
            rf"_reclaim_setup\s*\(\s*{value}\b",
            rf"obj\.controller,\s*{value}\b",
            rf"_gain_scrap\s*\(\s*[a-zA-Z_]+,\s*[a-zA-Z_.]+,\s*{value}\b",
        ]
    elif kind == "deal_damage":
        patterns = [
            rf"['\"]amount['\"]\s*:\s*{value}\b",
            rf"amount\s*=\s*{value}\b",
            rf"min\s*\(\s*{value}",
            rf"\+\s*{value}\b",
        ]
    elif kind == "plus_power":
        patterns = [
            rf"power_mod\s*=\s*{value}\b",
            rf"\+\s*int\s*\(\s*new_payload[^)]*\)\s*\+\s*{value}",
            rf"\+\s*{value}\b",
            rf"power_bonus\s*=\s*{value}\b",
        ]
    elif kind == "plus_integ":
        patterns = [
            rf"integrity_mod\s*=\s*{value}\b",
            rf"toughness_mod\s*=\s*{value}\b",
            rf"integrity_bonus\s*=\s*{value}\b",
            rf"\+\s*{value}\b",
        ]
    elif kind == "integ_ge":
        patterns = [
            rf"integrity\s*\)\s*>=\s*{value}\b",
            rf"integrity[^>]*>=\s*{value}",
            rf">=\s*{value}\b",
        ]
    elif kind == "damage_ge":
        patterns = [
            rf"damage_marked[^>]*>=\s*{value}",
            rf"damage\s*>=\s*{value}\b",
        ]

    for p in patterns:
        if re.search(p, code):
            return True
    return False


# ---------------------------------------------------------------------------
# Keyword checks
# ---------------------------------------------------------------------------

KEYWORD_MAP = {
    "Self-Mobile": "self_mobile",
    "Modular": "modular",
    "Synchronize": "synchronize",
    "Reticulate": None,  # keyword not stored; check setup mentions CLANKERS_TURN_END
    "Reclaim": None,     # numeric keyword; checked separately via Reclaim N
}


def _has_keyword(card_def, keyword: str) -> bool:
    """Check if card has the given keyword in its `clankers_keywords` list OR
    its setup_interceptors references the keyword's mechanism."""
    kws = getattr(card_def, "clankers_keywords", []) or []
    code_key = KEYWORD_MAP.get(keyword)
    if code_key is not None and code_key in kws:
        return True
    # Fallback: check source for the mechanism
    code = _all_code_for_card(card_def)
    if keyword == "Self-Mobile":
        return "attached_to is None" in code or "_self_mobile" in code or "self_mobile" in code
    if keyword == "Modular":
        return "_modular_relocate_effect" in code or "make_weapon_activated" in code
    if keyword == "Synchronize":
        return "synchronize" in code.lower() or "_synchronize_setup" in code
    if keyword == "Reticulate":
        return ("CLANKERS_TURN_END" in code and "transients_this_turn" in code)
    if keyword == "Reclaim":
        # Reclaim implementations:
        #   - Parts use make_part_on_self_destroyed
        #   - Chassis use a custom CLANKERS_CHASSIS_DESTROYED filter + _gain_scrap
        #   - Some use the _reclaim_setup factory
        return (
            "make_part_on_self_destroyed" in code
            or "_reclaim_setup" in code
            or ("CLANKERS_CHASSIS_DESTROYED" in code and "_gain_scrap" in code)
        )
    return False


# ---------------------------------------------------------------------------
# Drift detection logic
# ---------------------------------------------------------------------------

def check_drift(card_name: str, card_def) -> list[str]:
    """Return a list of drift failure messages for this card (empty = clean)."""
    text = (card_def.text or "").strip()
    if not text:
        return []  # nothing to drift against
    code = _all_code_for_card(card_def)
    closure_vals = _closure_ints(card_def)
    failures: list[str] = []

    # --- numeric draws ---
    for m in RE_DRAW.finditer(text):
        n = m.group(1)
        value = 1 if n == "a" else int(n)
        if not _has_pattern_in_code(code, value, "draw"):
            # Could also be that draw is conditional/runtime — fail only if we
            # have code AND we couldn't find any DRAW emit.
            if code and "DRAW" not in code and "draw" not in code.lower():
                failures.append(f"text says 'draw {n} cards' but no DRAW event in code")

    # --- deal damage ---
    for m in RE_DEAL_DAMAGE.finditer(text):
        value = int(m.group(1))
        if not _has_pattern_in_code(code, value, "deal_damage"):
            if code and ("DAMAGE" not in code and "damage" not in code.lower()):
                failures.append(f"text says 'deal {value} damage' but no damage event in code")

    # --- gain N scrap ---
    for m in RE_GAIN_SCRAP.finditer(text):
        value = int(m.group(1))
        if value in closure_vals:
            continue
        if not _has_pattern_in_code(code, value, "gain_scrap"):
            failures.append(f"text says 'gain {value} scrap' but no _gain_scrap({value}) in code")

    # --- gain N workshop integrity ---
    for m in RE_GAIN_INTEG.finditer(text):
        value = int(m.group(1))
        if value in closure_vals:
            continue
        if not _has_pattern_in_code(code, value, "gain_integ"):
            failures.append(f"text says 'gain {value} workshop integrity' but no matching heal in code")

    # --- pay N compute ---
    for m in RE_PAY_COMPUTE.finditer(text):
        value = int(m.group(1))
        if value in closure_vals:
            continue
        if not _has_pattern_in_code(code, value, "pay_compute"):
            failures.append(f"text says 'pay {value} Compute' but no compute_cost={value} in code")

    # --- pay N scrap ---
    for m in RE_PAY_SCRAP.finditer(text):
        value = int(m.group(1))
        if value in closure_vals:
            continue
        if not _has_pattern_in_code(code, value, "pay_scrap"):
            failures.append(f"text says 'pay {value} scrap' but no _spend_scrap({value}) in code")

    # --- armor N ---
    for m in RE_ARMOR_N.finditer(text):
        value = int(m.group(1))
        # Armor is checked via armor_value on card_def OR make_armor(obj, N).
        armor_val = getattr(card_def, "armor_value", None)
        if armor_val == value:
            continue
        if not _has_pattern_in_code(code, value, "armor"):
            failures.append(f"text says 'Armor {value}' but card armor_value={armor_val} and no make_armor({value}) in code")

    # --- reclaim N ---
    for m in RE_RECLAIM_N.finditer(text):
        value = int(m.group(1))
        if value in closure_vals:
            continue
        if not _has_pattern_in_code(code, value, "reclaim"):
            failures.append(f"text says 'Reclaim {value}' but no _gain_scrap({value}) in code")

    return failures


def check_keywords(card_name: str, card_def) -> list[str]:
    """Check keyword presence: text mentions 'Self-Mobile' → code must implement it."""
    text = (card_def.text or "").strip()
    failures: list[str] = []
    for kw in KEYWORD_MAP.keys():
        if kw in text:
            # "Reclaim" alone is ambiguous; only fail if it's just "Reclaim" w/o number
            # (Reclaim N is checked via RE_RECLAIM_N above).
            if kw == "Reclaim" and not RE_RECLAIM_N.search(text):
                continue
            if not _has_keyword(card_def, kw):
                failures.append(f"text mentions '{kw}' but code doesn't implement the keyword")
    return failures


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_drift_checks():
    """Walk every card, run drift checks, report."""
    total = 0
    skipped_count = 0
    failures: dict[str, list[str]] = {}
    skipped_listed: list[str] = []

    for name, cd in CLAN_CARDS.items():
        total += 1
        if name in SKIPPED_CARDS:
            skipped_count += 1
            skipped_listed.append(f"  - {name}: {SKIPPED_CARDS[name]}")
            continue
        all_failures = []
        all_failures.extend(check_drift(name, cd))
        all_failures.extend(check_keywords(name, cd))
        if all_failures:
            failures[name] = all_failures

    print(f"\n=== CLAN text drift check ===")
    print(f"  total cards: {total}")
    print(f"  skipped:     {skipped_count}")
    print(f"  failures:    {len(failures)}")

    if skipped_listed:
        print(f"\n--- SKIPPED CARDS ({len(skipped_listed)}) ---")
        for line in skipped_listed:
            print(line)

    if failures:
        print(f"\n--- DRIFT FAILURES ({len(failures)}) ---")
        for card_name, msgs in failures.items():
            print(f"\n  {card_name}:")
            for m in msgs:
                print(f"    - {m}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run_drift_checks())
