"""
Casting Cost System

This module implements a minimal-but-extensible framework for additional
casting costs that require player choice (discard, sacrifice, tap, etc.).

The engine previously only handled mana costs; many printed cards include
"As an additional cost..." or "You may cast this card from your graveyard by..."
clauses that require choices and other payments.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Callable, Any
import re

from .types import (
    GameState, GameObject, PendingChoice,
    Event, EventType, ZoneType, CardType,
)
from .mana import ManaCost, ManaSystem


_NUMBER_WORDS: dict[str, int] = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def _parse_int(token: str) -> Optional[int]:
    t = (token or "").strip().lower()
    if not t:
        return None
    if t.isdigit():
        return int(t)
    return _NUMBER_WORDS.get(t)


def add_mana_costs(a: ManaCost, b: ManaCost) -> ManaCost:
    """Add two parsed ManaCost objects (best-effort; concatenates hybrid/phyrexian)."""
    out = ManaCost()
    out.white = a.white + b.white
    out.blue = a.blue + b.blue
    out.black = a.black + b.black
    out.red = a.red + b.red
    out.green = a.green + b.green
    out.colorless = a.colorless + b.colorless
    out.generic = a.generic + b.generic
    out.snow = a.snow + b.snow
    out.x_count = a.x_count + b.x_count
    out.hybrid = list(a.hybrid) + list(b.hybrid)
    out.phyrexian = list(a.phyrexian) + list(b.phyrexian)
    return out


def describe_mana_cost(cost: ManaCost) -> str:
    return cost.to_string()


@dataclass(frozen=True)
class CastCostContext:
    state: GameState
    mana_system: Optional[ManaSystem]
    player_id: str
    casting_card_id: str
    casting_card_name: str
    casting_zone: ZoneType
    base_mana_cost: ManaCost
    x_value: int = 0


@dataclass(frozen=True)
class ChoiceSpec:
    choice_type: str
    prompt: str
    options: list[Any]
    min_choices: int = 1
    max_choices: int = 1
    # Optional extra validation hook (PendingChoice.validate_selection will call it).
    validator: Optional[Callable[[PendingChoice, list[Any]], tuple[bool, str]]] = None


# =============================================================================
# Cost Plan Representation
# =============================================================================


@dataclass(frozen=True)
class CostStep:
    kind: str
    amount: int = 0
    mana_cost: Optional[ManaCost] = None
    allowed_types: Optional[set[CardType]] = None
    # For OR steps: each option is a full sub-plan.
    options: Optional[tuple["CostPlan", ...]] = None


CostPlan = tuple[CostStep, ...]


def describe_plan(plan: CostPlan) -> str:
    parts: list[str] = []
    for step in plan:
        if step.kind == "pay_life":
            parts.append(f"pay {step.amount} life")
        elif step.kind == "add_mana":
            parts.append(f"pay {describe_mana_cost(step.mana_cost or ManaCost())}")
        elif step.kind == "discard":
            parts.append("discard a card" if step.amount == 1 else f"discard {step.amount} cards")
        elif step.kind == "sacrifice":
            if step.allowed_types:
                names = []
                if CardType.ARTIFACT in step.allowed_types:
                    names.append("artifact")
                if CardType.CREATURE in step.allowed_types:
                    names.append("creature")
                if CardType.ENCHANTMENT in step.allowed_types:
                    names.append("enchantment")
                if CardType.LAND in step.allowed_types:
                    names.append("land")
                if CardType.PLANESWALKER in step.allowed_types:
                    names.append("planeswalker")
                noun = " or ".join(names) if names else "permanent"
            else:
                noun = "permanent"
            parts.append(f"sacrifice {step.amount} {noun}" if step.amount != 1 else f"sacrifice a {noun}")
        elif step.kind == "tap":
            parts.append(f"tap {step.amount} permanent(s)")
        elif step.kind == "exile_from_graveyard":
            parts.append(f"exile {step.amount} card(s) from your graveyard")
        elif step.kind == "return_to_hand":
            parts.append(f"return {step.amount} permanent(s) you control to its owner's hand")
        elif step.kind == "exile_you_control":
            parts.append(f"exile {step.amount} permanent(s) you control")
        elif step.kind == "remove_counters":
            parts.append(f"remove {step.amount} counter(s) from among creatures you control")
        elif step.kind == "or":
            # For OR, describe each option plan.
            opt_desc = " / ".join(describe_plan(p) for p in (step.options or ()))
            parts.append(f"choose one ({opt_desc})")
        else:
            parts.append(step.kind)
    return ", ".join(parts)


# =============================================================================
# Parsing
# =============================================================================


_AS_ADDITIONAL_COST_RE = re.compile(
    r"^\s*as an additional cost to cast this spell,\s*(?P<rest>.+?)\s*$",
    re.IGNORECASE,
)

_GY_BY_RE = re.compile(
    r"^\s*you may cast this card from your graveyard by\s*(?P<rest>.+?)\s*$",
    re.IGNORECASE,
)

_IN_ADDITION_TO_OTHER_COSTS_RE = re.compile(
    r"\s*in addition to paying (?:its|their) other costs\.?\s*$",
    re.IGNORECASE,
)


def extract_additional_cost_plan(text: str) -> Optional[CostPlan]:
    """
    Extract a CostPlan from the first line that starts with:
      "As an additional cost to cast this spell, ..."
    """
    if not text:
        return None
    for line in text.splitlines():
        m = _AS_ADDITIONAL_COST_RE.match(line.strip())
        if not m:
            continue
        rest = m.group("rest").strip()
        # Only consider the first sentence.
        rest = rest.split(".")[0].strip()
        plan = parse_cost_expression(rest)
        return plan
    return None


def extract_graveyard_permission_cost_plan(text: str) -> Optional[CostPlan]:
    """
    Extract a CostPlan from the first line that starts with:
      "You may cast this card from your graveyard by ..."

    This describes extra costs required specifically to cast the card from the graveyard.
    """
    if not text:
        return None
    for line in text.splitlines():
        m = _GY_BY_RE.match(line.strip())
        if not m:
            continue
        rest = m.group("rest").strip()
        rest = _IN_ADDITION_TO_OTHER_COSTS_RE.sub("", rest).strip()
        rest = rest.split(".")[0].strip()
        plan = parse_cost_expression(rest)
        return plan
    return None


def _normalize_expr(expr: str) -> str:
    e = (expr or "").strip()
    # normalize unicode minus/dash variants commonly found in card text
    e = e.replace("−", "-").replace("—", "-")
    # remove trailing punctuation
    e = e.rstrip(" .;")
    # collapse whitespace
    e = re.sub(r"\s+", " ", e)
    return e


_PAY_MANA_RE = re.compile(r"^pay\s+((?:\{[^}]+\})+)$", re.IGNORECASE)
_PAY_LIFE_RE = re.compile(r"^pay\s+(\d+)\s+life$", re.IGNORECASE)
_DISCARD_RE = re.compile(r"^discard\s+(?:a|an|one)\s+card$", re.IGNORECASE)
_DISCARD_N_RE = re.compile(r"^discard\s+(\d+)\s+cards?$", re.IGNORECASE)
_DISCARD_TYPED_RE = re.compile(r"^discard\s+(?:a|an|one)\s+(\w+)\s+card$", re.IGNORECASE)
_SACRIFICE_RE = re.compile(r"^(?:sacrifice|sacrificing)\s+(?:a|an|one)\s+(.+)$", re.IGNORECASE)
_TAP_RE = re.compile(r"^(?:tap|tapping)\s+(\w+)\s+untapped\s+(.+?)\s+you control$", re.IGNORECASE)
_EXILE_FROM_GY_RE = re.compile(r"^(?:exile|exiling)\s+(\w+)\s+cards?\s+from your graveyard$", re.IGNORECASE)
_RETURN_TO_HAND_RE = re.compile(r"^(?:return|returning)\s+(?:a|an|one)\s+permanent you control to its owner's hand$", re.IGNORECASE)
_EXILE_YOU_CONTROL_RE = re.compile(r"^(?:exile|exiling)\s+(?:a|an|one)\s+creature you control$", re.IGNORECASE)
_REMOVE_COUNTERS_RE = re.compile(r"^(?:remove|removing)\s+(\w+)\s+counters?\s+from among creatures you control$", re.IGNORECASE)


def parse_cost_expression(expr: str) -> Optional[CostPlan]:
    """
    Parse a cost expression into a CostPlan.

    Supported (initial) patterns include:
      - discard a card
      - sacrifice an artifact or creature
      - pay N life
      - pay {2}{B}
      - tap two untapped creatures and/or lands you control
      - exile six cards from your graveyard
      - return a permanent you control to its owner's hand
      - remove six counters from among creatures you control
      - X or Y (where X/Y are supported expressions)
      - X and Y (where X/Y are supported expressions)
    """
    expr = _normalize_expr(expr)
    if not expr:
        return None

    # Special-case: "<sacrifice ...> or pay <...>" where the sacrifice side can
    # contain internal "or" type lists (e.g., "sacrifice a creature or enchantment or pay {2}").
    m = re.match(r"^(sacrific(?:e|ing)\s+.+?)\s+or\s+(pay\s+.+)$", expr, re.IGNORECASE)
    if m:
        left = parse_cost_expression(m.group(1))
        right = parse_cost_expression(m.group(2))
        if left and right:
            return (CostStep(kind="or", options=(left, right)),)

    # Try parsing as a single phrase first (avoids splitting "artifact or creature" type lists).
    single = _parse_single_phrase(expr)
    if single:
        return (single,)

    # OR: split into parts; only accept if every part parses.
    or_parts = _split_top_level(expr, " or ")
    if len(or_parts) > 1:
        parsed: list[CostPlan] = []
        for part in or_parts:
            p = parse_cost_expression(part)
            if not p:
                parsed = []
                break
            parsed.append(p)
        if parsed:
            return (CostStep(kind="or", options=tuple(parsed)),)

    # AND: split into parts; only accept if every part parses.
    and_parts = _split_top_level(expr, " and ")
    if len(and_parts) > 1:
        steps: list[CostStep] = []
        for part in and_parts:
            p = parse_cost_expression(part)
            if not p:
                return None
            steps.extend(p)
        return tuple(steps)

    return None


def _split_top_level(expr: str, sep: str) -> list[str]:
    # For now we don't attempt to parse parentheses nesting; card text patterns we
    # support are simple. Keep this as a helper in case we add nesting later.
    return [p.strip() for p in expr.split(sep) if p.strip()]


def _parse_single_phrase(expr: str) -> Optional[CostStep]:
    # pay {..}
    m = _PAY_MANA_RE.match(expr)
    if m:
        cost = ManaCost.parse(m.group(1))
        return CostStep(kind="add_mana", mana_cost=cost)

    # pay N life
    m = _PAY_LIFE_RE.match(expr)
    if m:
        return CostStep(kind="pay_life", amount=int(m.group(1)))

    # discard a <type> card (e.g. "discard a land card")
    m = _DISCARD_TYPED_RE.match(expr)
    if m:
        type_word = (m.group(1) or "").strip().lower()
        type_map = {
            "land": CardType.LAND,
            "creature": CardType.CREATURE,
            "artifact": CardType.ARTIFACT,
            "enchantment": CardType.ENCHANTMENT,
            "planeswalker": CardType.PLANESWALKER,
            "instant": CardType.INSTANT,
            "sorcery": CardType.SORCERY,
        }
        ct = type_map.get(type_word)
        if ct is not None:
            return CostStep(kind="discard", amount=1, allowed_types={ct})

    # discard a card / discard N cards
    if _DISCARD_RE.match(expr):
        return CostStep(kind="discard", amount=1)
    m = _DISCARD_N_RE.match(expr)
    if m:
        return CostStep(kind="discard", amount=int(m.group(1)))

    # sacrifice ...
    m = _SACRIFICE_RE.match(expr)
    if m:
        types_text = m.group(1).strip().lower()
        allowed = _parse_permanent_type_list(types_text)
        return CostStep(kind="sacrifice", amount=1, allowed_types=allowed)

    # tap N untapped X you control
    m = _TAP_RE.match(expr)
    if m:
        n = _parse_int(m.group(1))
        if n is None:
            return None
        types_text = m.group(2).strip().lower()
        allowed = _parse_permanent_type_list(types_text)
        return CostStep(kind="tap", amount=n, allowed_types=allowed)

    # exile N cards from your graveyard
    m = _EXILE_FROM_GY_RE.match(expr)
    if m:
        n = _parse_int(m.group(1))
        if n is None:
            return None
        return CostStep(kind="exile_from_graveyard", amount=n)

    # return a permanent you control to its owner's hand
    if _RETURN_TO_HAND_RE.match(expr):
        return CostStep(kind="return_to_hand", amount=1)

    # exile a creature you control
    if _EXILE_YOU_CONTROL_RE.match(expr):
        return CostStep(kind="exile_you_control", amount=1, allowed_types={CardType.CREATURE})

    # remove N counters from among creatures you control
    m = _REMOVE_COUNTERS_RE.match(expr)
    if m:
        n = _parse_int(m.group(1))
        if n is None:
            return None
        return CostStep(kind="remove_counters", amount=n)

    return None


def _parse_permanent_type_list(text: str) -> set[CardType]:
    """
    Parse a light-weight permanent type list from a clause like:
      "artifact or creature"
      "artifacts, creatures, and/or lands"
      "creatures and/or lands"
      "permanent"
    """
    t = (text or "").strip().lower()
    # Strip common suffixes.
    t = t.replace("untapped ", "")
    t = t.replace("nonland ", "")  # we don't model nonland here yet

    # Normalize punctuation.
    t = t.replace(",", " ")
    t = t.replace("and/or", "or")
    t = re.sub(r"\s+", " ", t)

    # Tokenize on "or".
    parts = [p.strip() for p in t.split(" or ") if p.strip()]
    allowed: set[CardType] = set()

    def add_word(word: str) -> None:
        w = word.strip().lower()
        if w in {"artifact", "artifacts"}:
            allowed.add(CardType.ARTIFACT)
        elif w in {"creature", "creatures"}:
            allowed.add(CardType.CREATURE)
        elif w in {"enchantment", "enchantments"}:
            allowed.add(CardType.ENCHANTMENT)
        elif w in {"land", "lands"}:
            allowed.add(CardType.LAND)
        elif w in {"planeswalker", "planeswalkers"}:
            allowed.add(CardType.PLANESWALKER)
        elif w in {"permanent", "permanents"}:
            allowed.update({CardType.ARTIFACT, CardType.CREATURE, CardType.ENCHANTMENT, CardType.LAND, CardType.PLANESWALKER})

    for part in parts:
        # Handle "artifacts creatures lands" after punctuation stripping.
        for word in part.split(" "):
            add_word(word)

    # Default to any permanent if we couldn't parse.
    if not allowed:
        allowed.update({CardType.ARTIFACT, CardType.CREATURE, CardType.ENCHANTMENT, CardType.LAND, CardType.PLANESWALKER})
    return allowed


# =============================================================================
# Eligibility Helpers
# =============================================================================


def eligible_hand_cards(ctx: CastCostContext, allowed_types: Optional[set[CardType]] = None) -> list[str]:
    hand = ctx.state.zones.get(f"hand_{ctx.player_id}")
    if not hand:
        return []
    # Can't discard the spell being cast if it's currently in the hand.
    out: list[str] = []
    for cid in hand.objects:
        if cid == ctx.casting_card_id:
            continue
        if allowed_types:
            obj = ctx.state.objects.get(cid)
            if not obj:
                continue
            if not (obj.characteristics.types & allowed_types):
                continue
        out.append(cid)
    return out


def eligible_battlefield_permanents(ctx: CastCostContext, allowed_types: Optional[set[CardType]] = None, *, must_be_untapped: bool = False) -> list[str]:
    battlefield = ctx.state.zones.get("battlefield")
    if not battlefield:
        return []

    eligible: list[str] = []
    for oid in battlefield.objects:
        obj = ctx.state.objects.get(oid)
        if not obj:
            continue
        if obj.controller != ctx.player_id:
            continue
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        if must_be_untapped and obj.state.tapped:
            continue
        if allowed_types and not (obj.characteristics.types & allowed_types):
            continue
        eligible.append(oid)
    return eligible


def eligible_graveyard_cards(ctx: CastCostContext) -> list[str]:
    gy = ctx.state.zones.get(f"graveyard_{ctx.player_id}")
    if not gy:
        return []
    return [cid for cid in gy.objects if cid != ctx.casting_card_id]


def total_counters_on_creatures_you_control(ctx: CastCostContext) -> dict[str, int]:
    eligible_ids = eligible_battlefield_permanents(ctx, {CardType.CREATURE})
    totals: dict[str, int] = {}
    for oid in eligible_ids:
        obj = ctx.state.objects.get(oid)
        if not obj:
            continue
        totals[oid] = sum(int(v) for v in (obj.state.counters or {}).values() if isinstance(v, int) and v > 0)
    return {k: v for k, v in totals.items() if v > 0}
