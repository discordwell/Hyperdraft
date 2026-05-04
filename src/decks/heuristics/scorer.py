# STUB-W2: replaced at integration by W1
"""
Heuristic card scorer for the W1 deckbuilder.

Single entry point: ``score_card(card_def, archetype, colors) -> float``.

Lower is better, mirroring the ``quality()`` pattern in
``scripts/play/custom_set_tournament.py:135``. ``+inf`` means the card is
uncastable in the given color identity (or otherwise unusable).

Design notes:

* Pure-Python, deterministic, no LLM. Same inputs always return the same
  float.
* Reads only ``CardDefinition.characteristics`` (set/list types are read,
  never mutated), ``card_def.text`` (regex), ``card_def.mana_cost``,
  ``card_def.rarity``, and the optional ``setup_interceptors`` /
  ``resolve`` callables.
* The scorer is intentionally side-effect-free so it can also become the
  brain of a future AI drafter (deferred).

Score formula:

    score = curve_term
          + body_term       (creatures only; lower for efficient bodies)
          - keyword_bonus
          + role_weight     (archetype-dependent; negative = favored)
          + rarity_prior    (small tiebreaker — mythic best)
          + wired_bonus     (-0.5 if has setup_interceptors,
                             -5.5 if has resolve — same as
                             custom_set_tournament:148-158)

Castability: any colored pip in the mana cost that isn't in ``colors``
returns ``+inf``. This is a hard drop, not a penalty.
"""

from __future__ import annotations

import math
import re
from typing import Iterable

from src.engine.mana import ManaCost
from src.engine.types import CardType


# =============================================================================
# Constants — tunable weights
# =============================================================================
# These weights are educated baselines. The W4 tournament harness and the W5
# netdeck calibration are the real ground truth — every knob here is a knob,
# not a setting in stone.

_CMC_SWEET: dict[str, int] = {
    "Aggro": 2,
    "Tempo": 2,
    "Midrange": 3,
    "Control": 4,
    "Ramp": 5,
    "Combo": 2,
}

# Body baseline: a vanilla 2/3 for {2} ≈ 0 contribution
# (P+T)/max(cmc,1) = 5/2 = 2.5; we subtract this from BODY_BASE so a vanilla
# 2/3 nets to ~0 and only above-rate bodies get a discount.
_BODY_BASE = 2.5
_BODY_WEIGHT = 1.5  # how much body efficiency dominates other terms

_KEYWORDS_BY_ARCHETYPE: dict[str, set[str]] = {
    "Aggro": {"haste", "flying", "trample", "menace", "first strike", "double strike"},
    "Tempo": {"flying", "flash", "haste", "prowess"},
    "Midrange": {"lifelink", "ward", "deathtouch", "vigilance"},
    "Control": {"flash", "defender", "vigilance", "ward"},
    "Ramp": {"reach", "trample", "ward", "vigilance"},
    "Combo": {"flash", "ward", "hexproof"},
}
_KEYWORD_BONUS_PER_HIT = 0.4

_RARITY_PRIOR: dict[str, float] = {
    "mythic": -1.0,
    "rare": -0.5,
    "uncommon": -0.2,
    "common": 0.0,
}

# Role detection. Compiled module-level for speed.
# Each role: a list of substrings/patterns. We match case-insensitively.
_ROLE_PATTERNS: dict[str, list[str]] = {
    "removal": [
        r"\bdestroy target\b",
        r"\bexile target\b",
        r"\b(deals?|dealt)\b.*\bdamage to (any target|target creature|target player|target opponent)\b",
        r"\btarget creature you control fights target creature\b",
        r"\btarget creature you control deals damage equal to its power to target creature\b",
        r"\btarget creature gets -",
        r"\bsacrifices? (a|target) creature\b",
        r"\breturn target creature to its owner's hand\b",
    ],
    "counterspell": [
        r"\bcounter target\b",
        r"\bcounter that spell\b",
    ],
    "card_draw": [
        r"\bdraw (a|two|three|four|five|that many|x) cards?\b",
        r"\bdraws? a card\b",
        r"\blook at the top \w+ cards? of your library\b",
        r"\bscry \d+\b",
        r"\bsurveil \d+\b",
        r"\bconnives?\b",
        r"\bdiscover \d+\b",
        r"\bexile the top \w+ cards? of your library\b.*\bmay play\b",
        r"\bcreate(s)? (a|one|two|three|x) clue\b",
        r"\bcreate(s)? (a|one|two|three|x) blood\b",
    ],
    "ramp": [
        r"\bsearch your library for (a|up to) (basic )?land\b",
        r"\badd (\{[wubrgc]\}|one mana|\{x\}|two mana|three mana)\b",
        r"\byou may put a land card from your hand\b",
        r"\buntap target land\b",
        r"\bcreate(s)? (a|one|two|three|x) treasure\b",
    ],
    "wincon": [
        r"\bcan't be blocked\b",
        r"\bdoubles? (your )?life total\b",
        r"\b(opponent|target opponent) loses the game\b",
        r"\bdeals? (\d+|x) damage to (each|any|target) (opponent|player)\b",
        r"\bcreate(s)? (two|three|four|five|x) .*creature tokens?\b",
    ],
    # "utility" is the residual catch-all when no other role matches.
}

_COMPILED_ROLE_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    role: [re.compile(p, re.IGNORECASE) for p in patterns]
    for role, patterns in _ROLE_PATTERNS.items()
}

# How much each role is favored by each archetype. Negative = bonus (lowers
# score). Roles with weight 0 are neither rewarded nor penalized.
_ROLE_WEIGHTS: dict[str, dict[str, float]] = {
    "Aggro": {
        "removal": -0.5,
        "wincon": -1.0,
        "card_draw": -0.2,
        "counterspell": +1.0,   # discourage in aggro
        "ramp": +0.5,
        "utility": 0.0,
    },
    "Tempo": {
        "removal": -0.6,
        "counterspell": -0.8,
        "card_draw": -0.4,
        "wincon": -0.5,
        "ramp": +0.3,
        "utility": 0.0,
    },
    "Midrange": {
        "removal": -0.8,
        "card_draw": -0.5,
        "wincon": -0.5,
        "ramp": -0.2,
        "counterspell": -0.1,
        "utility": 0.0,
    },
    "Control": {
        "removal": -1.0,
        "counterspell": -1.0,
        "card_draw": -0.8,
        "wincon": -0.7,
        "ramp": -0.1,
        "utility": 0.0,
    },
    "Ramp": {
        "ramp": -1.0,
        "card_draw": -0.5,
        "wincon": -0.8,
        "removal": -0.3,
        "counterspell": -0.1,
        "utility": 0.0,
    },
    "Combo": {
        "card_draw": -1.0,
        "wincon": -1.0,
        "counterspell": -0.5,
        "ramp": -0.5,
        "removal": -0.2,
        "utility": 0.0,
    },
}

# Standard MTG keywords used for the keyword fallback when chars.keywords is
# empty (most printed-set CardDefinitions in this codebase don't populate
# the abilities list, so we look for the keyword as a word in card_def.text).
_KEYWORD_FALLBACK_LIST = [
    "flying", "trample", "haste", "menace", "first strike", "double strike",
    "vigilance", "lifelink", "deathtouch", "ward", "defender", "flash",
    "reach", "prowess", "hexproof", "indestructible",
]

_COLOR_INTENSITY_BASE_PENALTY = 0.45


# =============================================================================
# Color helpers
# =============================================================================

# Map ManaCost colored-pip-counts to the MTG color letters.
_COST_COLOR_LETTERS: list[tuple[str, str]] = [
    ("white", "W"),
    ("blue", "U"),
    ("black", "B"),
    ("red", "R"),
    ("green", "G"),
]


def _required_color_letters(cost: ManaCost) -> set[str]:
    """Letters of colors that *must* be paid in this mana cost.

    Hybrid pips like {W/U} are not required individually — they're "either".
    Phyrexian pips can be paid with life, but we still treat them as
    requiring a color letter for deckbuilding purposes (they're colored
    cards in practice).
    """
    required: set[str] = set()
    for attr, letter in _COST_COLOR_LETTERS:
        if getattr(cost, attr, 0) > 0:
            required.add(letter)
    for p in cost.phyrexian:
        if p in {"W", "U", "B", "R", "G"}:
            required.add(p)
    return required


def _is_castable(card_def, colors: Iterable[str]) -> bool:
    """True if every required color pip is in ``colors``.

    Lands and 0-mana cards are always castable. We never reject on generic
    mana. Hybrid pips ({W/U}) are accepted if at least one named color is in
    the deck identity.
    """
    cost_str = card_def.mana_cost or ""
    if not cost_str:
        return True
    try:
        cost = ManaCost.parse(cost_str)
    except Exception:
        return True  # be permissive — bad costs aren't the scorer's problem

    deck_colors = {c.upper() for c in colors}
    required = _required_color_letters(cost)
    if required - deck_colors:
        return False

    # Hybrid pips: accept if at least one named option is in deck colors,
    # OR if neither named option is a colored pip (numeric hybrid like {2/W}).
    for opt1, opt2 in cost.hybrid:
        named = {o for o in (opt1, opt2) if o in {"W", "U", "B", "R", "G"}}
        if not named:
            continue  # purely numeric hybrid, harmless
        if not (named & deck_colors):
            return False
    return True


# =============================================================================
# Card-feature helpers
# =============================================================================


def _get_cmc(card_def) -> int:
    cost_str = card_def.mana_cost or ""
    if not cost_str:
        return 0
    try:
        return ManaCost.parse(cost_str).mana_value
    except Exception:
        return 0


def _colored_pip_counts(card_def) -> dict[str, int]:
    """Count exact colored pips in the printed mana cost."""
    counts = {letter: 0 for letter in {"W", "U", "B", "R", "G"}}
    cost_str = card_def.mana_cost or ""
    for raw in re.findall(r"\{([^}]+)\}", cost_str):
        symbol = raw.upper().strip()
        if symbol in counts:
            counts[symbol] += 1
    return counts


def _color_intensity_penalty(card_def, colors: Iterable[str], cmc: int) -> float:
    """Penalize early double-pip cards in multi-color decks."""
    deck_colors = {c.upper() for c in colors if c}
    if len(deck_colors) <= 1:
        return 0.0
    pip_counts = _colored_pip_counts(card_def)
    intense_pips = sum(max(0, pip_counts[color] - 1) for color in deck_colors)
    if intense_pips <= 0:
        return 0.0

    if cmc <= 2:
        curve_multiplier = 1.5
    elif cmc <= 4:
        curve_multiplier = 1.0
    else:
        curve_multiplier = 0.5
    return intense_pips * _COLOR_INTENSITY_BASE_PENALTY * curve_multiplier


def _is_creature(card_def) -> bool:
    types = card_def.characteristics.types or set()
    return CardType.CREATURE in types


def _is_land(card_def) -> bool:
    types = card_def.characteristics.types or set()
    return CardType.LAND in types


def _keywords_of(card_def) -> set[str]:
    """Return the canonical lowercase set of keywords on this card.

    Falls back to scanning ``card_def.text`` for the standard keyword names
    when ``chars.keywords`` is empty (most printed-MTG cards in this
    codebase don't populate the abilities list).
    """
    chars = card_def.characteristics
    explicit = set(chars.keywords) if chars and chars.abilities else set()
    if explicit:
        return explicit
    text = (card_def.text or "").lower()
    if not text:
        return set()
    found: set[str] = set()
    for kw in _KEYWORD_FALLBACK_LIST:
        # Use word-boundary match. Multi-word keywords (e.g. "first strike")
        # are matched as a literal phrase.
        pat = r"\b" + re.escape(kw) + r"\b"
        if re.search(pat, text):
            found.add(kw)
    return found


def _detect_role(card_def) -> str:
    """Return one of: removal, counterspell, card_draw, ramp, wincon, utility.

    First match wins (order of iteration on _COMPILED_ROLE_PATTERNS), and
    "utility" is the fallback when no pattern hits. Land cards are always
    "utility" — the role tagger is for spell selection, not lands.
    """
    if _is_land(card_def):
        return "utility"
    text = card_def.text or ""
    if text:
        for role, patterns in _COMPILED_ROLE_PATTERNS.items():
            for pat in patterns:
                if pat.search(text):
                    return role

    chars = card_def.characteristics
    types = chars.types or set()
    if CardType.PLANESWALKER in types:
        return "wincon"
    if _is_creature(card_def):
        power = chars.power if chars.power is not None else 0
        if power >= 4:
            return "wincon"

    return "utility"


def _rarity_prior(card_def) -> float:
    rarity = (card_def.rarity or "common").lower()
    return _RARITY_PRIOR.get(rarity, 0.0)


def _wired_bonus(card_def) -> float:
    """Mirror custom_set_tournament:148-158 — favor wired/functional cards.

    setup_interceptors → -0.5 (static/triggered/etc).
    resolve            → -5.5 (functional spell with dispatch).
    Both can stack (some hybrid cards register both).
    """
    bonus = 0.0
    if getattr(card_def, "setup_interceptors", None):
        bonus -= 0.5
    if getattr(card_def, "resolve", None):
        bonus -= 5.5
    return bonus


# =============================================================================
# Public API
# =============================================================================


def score_card(card_def, archetype: str, colors: list[str]) -> float:
    """
    Score a card for the given archetype + color identity.

    Lower is better. Returns ``+inf`` for uncastable cards (off-color pip
    outside ``colors``).

    Args:
        card_def: A ``CardDefinition`` from any set in
            ``src.cards.set_registry.SET_TO_CARDS``.
        archetype: One of the keys in ``ARCHETYPE_TEMPLATES`` —
            "Aggro", "Midrange", "Control", "Tempo", "Ramp". Trimmed and
            capitalized for forgiving lookup; unknown archetypes fall back
            to Midrange weights.
        colors: List of MTG color letters (e.g. ``["W", "U"]``).

    Returns:
        A float. Lower scores are picked first by the slot-filler.
    """
    if card_def is None:
        return math.inf

    # --- Castability gate ---------------------------------------------------
    if not _is_castable(card_def, colors):
        return math.inf

    # Resolve archetype (forgiving)
    arch = archetype if archetype in _CMC_SWEET else archetype.strip().capitalize()
    if arch not in _CMC_SWEET:
        # Unknown archetype: fall back to Midrange weights.
        arch = "Midrange"

    cmc = _get_cmc(card_def)
    score = 0.0

    # --- Curve fit ----------------------------------------------------------
    sweet = _CMC_SWEET[arch]
    score += abs(cmc - sweet) * 1.0

    # --- Mana stability -----------------------------------------------------
    score += _color_intensity_penalty(card_def, colors, cmc)

    # --- Body efficiency (creatures) ---------------------------------------
    chars = card_def.characteristics
    if _is_creature(card_def):
        power = chars.power if chars.power is not None else 0
        toughness = chars.toughness if chars.toughness is not None else 0
        denom = max(cmc, 1)
        body_eff = (power + toughness) / denom
        # Higher body efficiency lowers the score. We center on _BODY_BASE so
        # a vanilla 2/3 for {2} (eff = 2.5) contributes ~0.
        score += -_BODY_WEIGHT * (body_eff - _BODY_BASE)

    # --- Keyword bonuses ---------------------------------------------------
    keywords = _keywords_of(card_def)
    favored = _KEYWORDS_BY_ARCHETYPE.get(arch, set())
    hits = keywords & favored
    score -= _KEYWORD_BONUS_PER_HIT * len(hits)

    # --- Role tag ----------------------------------------------------------
    role = _detect_role(card_def)
    role_weights = _ROLE_WEIGHTS.get(arch, {})
    score += role_weights.get(role, 0.0)

    # --- Rarity prior ------------------------------------------------------
    score += _rarity_prior(card_def)

    # --- Wired bonus -------------------------------------------------------
    score += _wired_bonus(card_def)

    # Lands have a special role: they're added by the manabase pass, not the
    # spell scorer. Push them well above all spells so the slot-filler never
    # picks them as a spell.
    if _is_land(card_def):
        score += 100.0

    return score


def role_of(card_def) -> str:
    """Public re-export of the role detector for the slot-filler in W2."""
    return _detect_role(card_def)


def cmc_of(card_def) -> int:
    """Public re-export of the CMC helper for the slot-filler in W2."""
    return _get_cmc(card_def)


def is_castable(card_def, colors: Iterable[str]) -> bool:
    """Public re-export of the castability check."""
    return _is_castable(card_def, colors)


__all__ = [
    "score_card",
    "role_of",
    "cmc_of",
    "is_castable",
]
