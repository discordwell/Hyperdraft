"""Phase 4: Activated-ability framework.

Cards register activated abilities by appending an ``ActivatedAbility`` to
``obj.state.activated_abilities`` (typically via
``cards.interceptor_helpers.make_activated_ability``). The priority system
discovers them in ``_get_activatable_abilities`` and dispatches them in
``_handle_activate_ability``.

Costs supported:
- mana cost (any prefix of ``{N}``, ``{W}``, ``{X}``, hybrid)
- ``{T}`` tap-self
- ``Sacrifice this`` / ``Sacrifice this <type>``
- ``Discard a card``
- ``Pay N life``
- ``Remove an X counter from this``

Restrictions supported:
- ``Activate only as a sorcery`` (main phase, empty stack, own turn)
- ``Activate only during your turn``
- ``Activate only any time you could cast a sorcery`` (alias for sorcery-speed)
- ``Activate only once each turn``
- ``Activate only once`` ("Exhaust" — once per game per permanent)

Effect signature: ``(obj: GameObject, state: GameState, targets: list[Target]) -> list[Event]``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .casting_costs import CostPlan, CostStep, parse_cost_expression
from .mana import ManaCost
from .types import (
    CardType,
    Event,
    EventType,
    GameObject,
    GameState,
    ZoneType,
)

EffectFn = Callable[[GameObject, GameState, list], list[Event]]


@dataclass
class ActivatedAbility:
    """Descriptor for an activated ability registered on a GameObject."""

    cost_text: str
    effect_fn: EffectFn
    description: str = ""

    # Parsed cost components.
    mana_cost: Optional[ManaCost] = None
    requires_tap: bool = False
    sac_self: bool = False
    discard_self: bool = False
    exile_self: bool = False
    additional_cost_plan: Optional[CostPlan] = None
    counter_removal: Optional[tuple[str, int]] = None  # (counter_name, amount) on self

    # Restrictions.
    sorcery_speed: bool = False
    own_turn_only: bool = False
    once_per_turn: bool = False
    once_per_game: bool = False  # Exhaust — single activation per permanent, ever.

    # X-cost / Exhaust flags (Phase: W2 engine extensions).
    has_x_cost: bool = False  # True iff mana_cost.x_count > 0 at registration time.
    is_exhaust: bool = False  # Mirror of once_per_game for now; broadcast on ACTIVATE event.

    # Targeting hints.
    targets_required: int = 0
    target_kind: str = "any"

    # State (mutable across activations).
    activations_this_turn: int = 0
    last_activation_turn: int = -1
    total_activations: int = 0
    once_per_game_used: bool = False  # Set on the first activation of an Exhaust ability.

    # Identity.
    ability_index: int = 0

    # WOE Adventure marker. When True, paying ``exile_self`` flags the source
    # object's ``state.adventure_exile`` so the cast subsystem can offer
    # casting the main half from exile.
    is_adventure: bool = False


# ----------------------------------------------------------------------
# Cost parsing
# ----------------------------------------------------------------------

_MANA_SYMBOL_RE = re.compile(r"^\{(?:[WUBRGCSXY0-9/]+|[0-9]+|[WUBRG]/[WUBRG]|[WUBRG]/P|2/[WUBRG])\}$", re.IGNORECASE)
# Matches a sequence of one or more contiguous mana symbols (e.g. "{X}{X}",
# "{2}{R}{R}", "{W/U}{B}"). Used by the cost parser to recognise compound
# mana costs that aren't comma-separated.
_MANA_SEQUENCE_RE = re.compile(
    r"^(?:\{(?:[WUBRGCSXY0-9/]+|[WUBRG]/P|2/[WUBRG])\})+$",
    re.IGNORECASE,
)
_COUNTER_REMOVE_RE = re.compile(
    r"remove (?:an?|(\d+))\s+([\w\-]+)\s+counters?\s+from\s+(?:this|\w[\w\s]*)",
    re.IGNORECASE,
)


def _is_mana_symbol(part: str) -> bool:
    s = part.strip()
    if not (s.startswith("{") and s.endswith("}")):
        return False
    return bool(_MANA_SYMBOL_RE.match(s))


def _is_mana_sequence(part: str) -> bool:
    """True if ``part`` is a contiguous run of mana symbols (e.g. {X}{X}, {2}{R}).

    A single mana symbol also satisfies this (it's the trivial 1-symbol run).
    """
    s = part.strip()
    if not (s.startswith("{") and s.endswith("}")):
        return False
    return bool(_MANA_SEQUENCE_RE.match(s))


def parse_activation_cost(cost_text: str, source_name: str = "") -> tuple[
    Optional[ManaCost], bool, bool, bool, bool, Optional[CostPlan], Optional[tuple[str, int]]
]:
    """Parse a cost expression like ``{2}, {T}, Sacrifice this``.

    Returns ``(mana_cost, requires_tap, sac_self, discard_self, exile_self,
    additional_cost_plan, counter_removal)``.
    """
    parts = [p.strip() for p in cost_text.split(",") if p.strip()]
    mana_parts: list[str] = []
    has_tap = False
    sac_self = False
    discard_self = False
    exile_self = False
    additional_phrases: list[str] = []
    counter_removal: Optional[tuple[str, int]] = None

    sname_lower = (source_name or "").lower()

    for part in parts:
        upper = part.upper()
        lower = part.lower()
        if upper == "{T}":
            has_tap = True
            continue
        if upper == "{Q}":  # Untap symbol — rare; treat as tap-untap.
            continue
        if _is_mana_symbol(part):
            mana_parts.append(part)
            continue
        # Compound mana sequences such as "{X}{X}" or "{2}{R}". We try to
        # split off a leading run of mana symbols and treat it as one mana
        # chunk. The remainder (rare — usually empty) gets re-processed.
        if _is_mana_sequence(part):
            mana_parts.append(part)
            continue
        # Self-exile (Adventure-style "Exile this card").
        if re.match(r"^exile\s+this\s+card\b", lower):
            exile_self = True
            continue
        # Self-discard (cycling-style "Discard this card").
        if re.match(r"^discard\s+(?:this|" + re.escape(sname_lower) + r")(?:\s+card)?\b", lower):
            discard_self = True
            continue
        if re.match(r"^discard\s+this\s+card\b", lower):
            discard_self = True
            continue
        # Self-sacrifice patterns
        if re.match(r"^sacrifice\s+(?:this|" + re.escape(sname_lower) + r")\b", lower) and sname_lower:
            sac_self = True
            continue
        if re.match(r"^sacrifice\s+(?:this|it)\b", lower):
            sac_self = True
            continue
        if re.match(r"^sacrifice\s+(?:this\s+\w+)\b", lower):  # "sacrifice this creature/artifact"
            sac_self = True
            continue
        # Counter removal from self
        m = _COUNTER_REMOVE_RE.search(part)
        if m:
            n = int(m.group(1)) if m.group(1) else 1
            ctype = m.group(2).lower()
            counter_removal = (ctype, n)
            continue
        additional_phrases.append(part)

    mana_cost = None
    if mana_parts:
        mana_cost = ManaCost.parse("".join(mana_parts))

    add_plan: Optional[CostPlan] = None
    if additional_phrases:
        joined = " and ".join(additional_phrases)
        add_plan = parse_cost_expression(joined)

    return mana_cost, has_tap, sac_self, discard_self, exile_self, add_plan, counter_removal


# ----------------------------------------------------------------------
# Restriction detection from card text
# ----------------------------------------------------------------------


def detect_restrictions(card_text: Optional[str]) -> tuple[bool, bool, bool]:
    """Inspect card text for sorcery-speed / own-turn / once-per-turn flags."""
    if not card_text:
        return False, False, False
    t = card_text.lower()
    sorcery_speed = (
        "activate only as a sorcery" in t
        or "activate only any time you could cast a sorcery" in t
    )
    own_turn = "activate only during your turn" in t
    once_per_turn = (
        "activate only once each turn" in t
        or "activate this ability only once each turn" in t
    )
    return sorcery_speed, own_turn, once_per_turn


def detect_exhaust(card_text: Optional[str]) -> bool:
    """Return True if the card text contains an Exhaust ability marker.

    Exhaust abilities use the reminder text "Activate each exhaust ability
    only once." (sometimes "Activate this ability only once.") and are written
    with the prefix ``Exhaust — <cost>: <effect>``.
    """
    if not card_text:
        return False
    t = card_text.lower()
    if "exhaust" in t and "—" in t:
        return True
    if "activate each exhaust ability only once" in t:
        return True
    if "activate this ability only once" in t and "exhaust" in t:
        return True
    return False


# ----------------------------------------------------------------------
# Registration
# ----------------------------------------------------------------------


def register_activated_ability(
    obj: GameObject,
    cost: str,
    effect_fn: EffectFn,
    *,
    description: str = "",
    sorcery_speed: bool = False,
    own_turn_only: bool = False,
    once_per_turn: bool = False,
    once_per_game: bool = False,
    targets_required: int = 0,
    target_kind: str = "any",
    is_adventure: bool = False,
) -> ActivatedAbility:
    """Register an activated ability descriptor on ``obj.state.activated_abilities``.

    The setup function calling this typically returns ``[]`` (no interceptors)
    since the ability is consulted via the registry rather than the event pipeline.
    """
    mana_cost, requires_tap, sac_self, discard_self, exile_self, add_plan, counter_removal = parse_activation_cost(
        cost, source_name=obj.name
    )

    text_speed, text_turn, text_once = detect_restrictions(
        obj.card_def.text if obj.card_def else None
    )
    sorcery_speed = sorcery_speed or text_speed
    own_turn_only = own_turn_only or text_turn or sorcery_speed
    once_per_turn = once_per_turn or text_once

    has_x_cost = bool(mana_cost is not None and mana_cost.x_count > 0)
    # is_exhaust currently mirrors once_per_game; tracked separately for forward
    # compatibility with potential future "Exhaust without once-per-game" cards.
    is_exhaust = bool(once_per_game)

    ability = ActivatedAbility(
        cost_text=cost,
        effect_fn=effect_fn,
        description=description or f"{cost}: ...",
        mana_cost=mana_cost,
        requires_tap=requires_tap,
        sac_self=sac_self,
        discard_self=discard_self,
        exile_self=exile_self,
        additional_cost_plan=add_plan,
        counter_removal=counter_removal,
        sorcery_speed=sorcery_speed,
        own_turn_only=own_turn_only,
        once_per_turn=once_per_turn,
        once_per_game=once_per_game,
        has_x_cost=has_x_cost,
        is_exhaust=is_exhaust,
        targets_required=targets_required,
        target_kind=target_kind,
        is_adventure=is_adventure,
    )

    if not isinstance(obj.state.activated_abilities, list):
        obj.state.activated_abilities = []
    # Guard against double-registration: setup_interceptors runs both during
    # Game.create_object (HAND-side initialization) and during the ZONE_CHANGE
    # to BATTLEFIELD. The reliable identity for a single ability is
    # (cost_text, effect_fn.__code__) compared by **identity**: two runs of
    # the same setup produce different function objects but share the same
    # compiled ``code`` object (def statements compile once at module load).
    # Two genuinely distinct abilities — even with identical cost text and
    # auto-generated descriptions — were defined by separate ``def``
    # statements, so their code objects are not ``is``-equal.
    #
    # NB: comparing ``co_code`` bytes is *not* sufficient — two distinct
    # closures can have identical instruction sequences when only their
    # constants/names differ (those live in ``co_consts`` / ``co_names``,
    # not in the bytecode body).
    new_code = getattr(effect_fn, '__code__', None)
    expected_desc = description or f"{cost}: ..."
    for existing in obj.state.activated_abilities:
        if existing.cost_text != cost:
            continue
        existing_code = getattr(existing.effect_fn, '__code__', None)
        if new_code is not None and existing_code is not None:
            if new_code is existing_code:
                return existing
            # Distinct code objects -> genuinely different abilities. Continue
            # scanning the list rather than collapsing.
            continue
        # Fallback for non-Python callables (rare): legacy description match.
        if existing.description == expected_desc:
            return existing
    ability.ability_index = len(obj.state.activated_abilities)
    obj.state.activated_abilities.append(ability)
    return ability


# ----------------------------------------------------------------------
# Cost-payment helpers (called from priority.py)
# ----------------------------------------------------------------------


def can_pay_activation(
    ability: ActivatedAbility,
    obj: GameObject,
    state: GameState,
    player_id: str,
    mana_system=None,
    *,
    is_active_player: bool = True,
    is_main_phase: bool = True,
    stack_empty: bool = True,
    x_value: int = 0,
    effective_mana_cost: Optional[ManaCost] = None,
) -> bool:
    """Check whether all activation costs/timing constraints are satisfied.

    Timing booleans are passed in by the caller (priority.py) which has the
    authoritative turn_manager / stack references. ``is_active_player`` should
    be True iff ``player_id`` is the player whose turn it currently is.

    ``x_value`` is the chosen value for {X} symbols in the mana cost; defaults
    to 0 (so existing callers that only have an X=0 ability behave unchanged).
    ``effective_mana_cost`` overrides the printed mana_cost when supplied
    (used by callers that have already applied activated-cost reductions via
    ``cost_query.get_effective_activation_cost``); the printed cost is used
    otherwise.
    """
    # Tap requirement
    if ability.requires_tap and obj.state.tapped:
        return False
    # Summoning sickness blocks tap on creatures (unless they have haste)
    if ability.requires_tap and CardType.CREATURE in obj.characteristics.types:
        if obj.state.summoning_sickness:
            try:
                from .queries import has_keyword
                if not has_keyword(obj, "haste", state):
                    return False
            except Exception:
                # If has_keyword unavailable, be conservative and block.
                return False
    # Mana
    if ability.mana_cost and mana_system is not None:
        cost_to_pay = effective_mana_cost if effective_mana_cost is not None else ability.mana_cost
        if not mana_system.can_cast(player_id, cost_to_pay, x_value):
            return False
    # Counter removal
    if ability.counter_removal:
        ctype, n = ability.counter_removal
        if obj.state.counters.get(ctype, 0) < n:
            return False
    # Once-per-turn
    if ability.once_per_turn and ability.last_activation_turn == state.turn_number:
        return False
    # Once-per-game (Exhaust): if it has ever been activated, it's spent forever
    # on this permanent. New permanents (different obj.id) get a fresh copy.
    if ability.once_per_game and ability.once_per_game_used:
        return False
    # Sorcery-speed: own turn, main phase, empty stack
    if ability.sorcery_speed:
        if not is_active_player:
            return False
        if not is_main_phase:
            return False
        if not stack_empty:
            return False
    elif ability.own_turn_only:
        if not is_active_player:
            return False
    return True


def pay_activation_cost(
    ability: ActivatedAbility,
    obj: GameObject,
    state: GameState,
    player_id: str,
    mana_system=None,
    *,
    x_value: int = 0,
    effective_mana_cost: Optional[ManaCost] = None,
) -> list[Event]:
    """Pay all activation costs, returning the resulting Events to enqueue.

    Mana is paid via ``mana_system`` directly (no event emitted; the existing
    cast path uses the same convention). Returns events for tap, sacrifice,
    counter removal, etc.

    ``x_value`` is the chosen value for any {X} mana symbols in the cost.
    ``effective_mana_cost`` lets callers substitute a cost-reduction-applied
    cost; the printed cost is used otherwise.
    """
    events: list[Event] = []

    # Mana
    if ability.mana_cost and mana_system is not None and not ability.mana_cost.is_free():
        cost_to_pay = effective_mana_cost if effective_mana_cost is not None else ability.mana_cost
        mana_system.pay_cost(player_id, cost_to_pay, x_value)

    # Tap
    if ability.requires_tap:
        events.append(Event(
            type=EventType.TAP,
            payload={"object_id": obj.id},
            source=obj.id,
            controller=player_id,
        ))
        # Eagerly mark tapped so simultaneous abilities can't double-tap.
        obj.state.tapped = True

    # Self-sacrifice
    if ability.sac_self:
        events.append(Event(
            type=EventType.SACRIFICE,
            payload={"object_id": obj.id, "controller": player_id},
            source=obj.id,
            controller=player_id,
        ))

    # Self-discard (cycling cost: "Discard this card").
    if ability.discard_self:
        events.append(Event(
            type=EventType.DISCARD,
            payload={"player": player_id, "object_id": obj.id},
            source=obj.id,
            controller=player_id,
        ))

    # Self-exile (Adventure cost: "Exile this card").
    if ability.exile_self:
        events.append(Event(
            type=EventType.EXILE,
            payload={"object_id": obj.id, "controller": player_id},
            source=obj.id,
            controller=player_id,
        ))
        # WOE Adventure: mark the source so the cast subsystem can surface
        # casting the main (creature/enchantment) half from exile after the
        # Adventure spell resolves. We set the flag here at cost-pay time
        # because the EXILE handler runs later in the pipeline; setting it
        # on obj.state persists through the zone change.
        if ability.is_adventure:
            obj.state.adventure_exile = True

    # Counter removal from self
    if ability.counter_removal:
        ctype, n = ability.counter_removal
        events.append(Event(
            type=EventType.COUNTER_REMOVED,
            payload={
                "object_id": obj.id,
                "counter_type": ctype,
                "amount": n,
            },
            source=obj.id,
            controller=player_id,
        ))
        obj.state.counters[ctype] = max(0, obj.state.counters.get(ctype, 0) - n)

    # Additional non-self costs (discard, pay-life, etc.) — best-effort:
    # emit declarative events; the pipeline handles them.
    if ability.additional_cost_plan:
        for step in ability.additional_cost_plan:
            if step.kind == "pay_life":
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={"player": player_id, "amount": -step.amount},
                    source=obj.id,
                    controller=player_id,
                ))
            elif step.kind == "discard":
                events.append(Event(
                    type=EventType.DISCARD_CHOICE,
                    payload={"player": player_id, "count": step.amount or 1},
                    source=obj.id,
                    controller=player_id,
                ))

    return events


# ----------------------------------------------------------------------
# Bookkeeping
# ----------------------------------------------------------------------


def record_activation(ability: ActivatedAbility, state: GameState) -> None:
    """Update per-turn bookkeeping after a successful activation."""
    if ability.last_activation_turn != state.turn_number:
        ability.activations_this_turn = 0
    ability.last_activation_turn = state.turn_number
    ability.activations_this_turn += 1
    ability.total_activations += 1
    if ability.once_per_game:
        ability.once_per_game_used = True


__all__ = [
    "ActivatedAbility",
    "EffectFn",
    "parse_activation_cost",
    "detect_restrictions",
    "detect_exhaust",
    "register_activated_ability",
    "can_pay_activation",
    "pay_activation_cost",
    "record_activation",
]
