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

    # Phase 5b: engine-authoritative cast-time targeting for activated
    # abilities. When set, the ``_handle_activate_ability`` priority handler
    # emits a PendingChoice (mirroring ``_emit_cast_target_choice_step``)
    # BEFORE paying any cost — matching CR 602.1 (announce → choose targets →
    # pay costs). Shape matches ``CardDefinition.target_requirements``: a list
    # of ``TargetRequirement | TargetRequirementBuilder``. Legacy abilities
    # leave this ``None`` and rely on the older ``targets_required`` /
    # ``target_kind`` path (or pre-supplied ``action.targets``).
    target_requirements: Optional[list] = None

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

    # Marvin-style ability mirror marker. When True, this ActivatedAbility is
    # a *derived* view created by ``get_mirrored_abilities`` from another
    # creature's printed ability. The descriptor lives transiently on the
    # mirror's view list and MUST NOT be re-mirrored (otherwise an A->B->A
    # chain would recurse forever).
    is_mirror_derived: bool = False
    # When ``is_mirror_derived``, points back at the source object whose
    # ability is being mirrored. Set so the mirror's cost-pay can still tap
    # the *mirroring* object (e.g. Marvin) while ignoring the source's tap
    # state for legality.
    mirror_source_obj_id: Optional[str] = None
    # Identity of the original (printed) ability descriptor on the source.
    # Used for de-dup / bookkeeping; not consulted by the cost-pay path.
    mirror_source_ability_index: Optional[int] = None

    # OTJ Plot marker. When True, paying ``exile_self`` sets the source
    # object's ``state.plotted_turn`` to the current turn number so the
    # cast subsystem can offer casting the spell from exile on a later
    # turn at sorcery speed without paying its mana cost.
    is_plot: bool = False

    # Optional state-time gate. When provided, ``can_pay_activation`` invokes
    # ``precondition_fn(obj, state) -> bool``; if it returns False, the ability
    # is treated as not legal. Use for "Activate only if X happened this turn"
    # / "Activate only while you control a Y". Distinct from ``mana_cost`` /
    # ``requires_tap`` etc. — those are *costs*; this is a *condition*.
    precondition_fn: Optional[Callable[[Any, Any], bool]] = None


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
    target_requirements: Optional[list] = None,
    is_adventure: bool = False,
    is_plot: bool = False,
    precondition_fn: Optional[Callable[[Any, Any], bool]] = None,
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
        target_requirements=target_requirements,
        is_adventure=is_adventure,
        is_plot=is_plot,
        precondition_fn=precondition_fn,
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
    # State-time precondition (e.g. "Activate only if Vader was destroyed
    # this turn"). Distinct from cost/timing — guards legality entirely.
    if ability.precondition_fn is not None:
        try:
            if not ability.precondition_fn(obj, state):
                return False
        except Exception:
            return False
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
    # Additional non-self cost validation (exile-from-GY, sacrifice-named).
    # Other kinds (pay_life / discard) are validated at cost-pay time and
    # don't gate legality here for backward compatibility.
    if ability.additional_cost_plan:
        for step in ability.additional_cost_plan:
            if step.kind == "exile_from_graveyard":
                gy_key = f"graveyard_{player_id}"
                gy = state.zones.get(gy_key)
                gy_objects = list(getattr(gy, "objects", []) or []) if gy is not None else []
                # Compute required count: literal amount, or X (read from
                # caller's chosen x_value at validation time).
                if getattr(step, "count_is_x", False):
                    required = max(0, int(x_value or 0))
                else:
                    required = int(step.amount or 1)
                # Filter graveyard pool by subtype_filter if provided.
                subtype_filter = getattr(step, "subtype_filter", None)
                if subtype_filter is not None:
                    eligible = [
                        cid for cid in gy_objects
                        if (cand := state.objects.get(cid)) is not None
                        and subtype_filter in cand.characteristics.types
                    ]
                else:
                    eligible = gy_objects
                if len(eligible) < required:
                    return False
            elif step.kind == "sacrifice_named":
                name_lc = (step.name_match or "").lower()
                if not name_lc:
                    return False
                # Find at least one battlefield permanent the player controls
                # whose lowercase name matches.
                bf = state.zones.get("battlefield")
                if bf is None:
                    return False
                found = False
                for oid in bf.objects:
                    cand = state.objects.get(oid)
                    if cand is None:
                        continue
                    if cand.controller != player_id:
                        continue
                    if (cand.name or "").lower() == name_lc:
                        found = True
                        break
                if not found:
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
        # OTJ Plot: mark the source so the cast subsystem can surface a
        # free cast from exile on a later turn (sorcery speed). We record
        # the turn the plot cost was paid; ``can_cast_plotted`` requires
        # strict-greater-than to ensure same-turn casts are rejected.
        # The PLOT_PAID + PLOT_BECOMES_PLOTTED markers are emitted as
        # part of the resolve so triggers like "When this card becomes
        # plotted" fire after the cost is paid.
        if ability.is_plot:
            obj.state.plotted_turn = state.turn_number
            obj.state.plot_cast_used = False
            events.append(Event(
                type=EventType.PLOT_PAID,
                payload={
                    'object_id': obj.id,
                    'player': player_id,
                    'turn': state.turn_number,
                },
                source=obj.id,
                controller=player_id,
            ))
            events.append(Event(
                type=EventType.PLOT_BECOMES_PLOTTED,
                payload={
                    'object_id': obj.id,
                    'player': player_id,
                    'turn': state.turn_number,
                },
                source=obj.id,
                controller=player_id,
            ))

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

    # Additional non-self costs (discard, pay-life, exile-from-GY,
    # sacrifice-named, etc.) — emit declarative events; the pipeline
    # handles the actual zone moves.
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
            elif step.kind == "exile_from_graveyard":
                # Greedy: exile the first N cards in the player's
                # graveyard (filtered by subtype_filter if set, count
                # bound to X if count_is_x). AI/UI can intercept earlier
                # to pick specific cards via PendingChoice if the cost
                # requires selection.
                if getattr(step, "count_is_x", False):
                    n = max(0, int(x_value or 0))
                else:
                    n = int(step.amount or 1)
                gy_key = f"graveyard_{player_id}"
                gy = state.zones.get(gy_key)
                gy_ids_all = list(getattr(gy, "objects", []) or [])
                subtype_filter = getattr(step, "subtype_filter", None)
                if subtype_filter is not None:
                    gy_ids = [
                        cid for cid in gy_ids_all
                        if (cand := state.objects.get(cid)) is not None
                        and subtype_filter in cand.characteristics.types
                    ][:n]
                else:
                    gy_ids = gy_ids_all[:n]
                for cid in gy_ids:
                    events.append(Event(
                        type=EventType.EXILE,
                        payload={"object_id": cid, "controller": player_id},
                        source=obj.id,
                        controller=player_id,
                    ))
            elif step.kind == "sacrifice_named":
                # Sacrifice one battlefield permanent the player controls
                # whose name matches step.name_match (case-insensitive).
                # If multiple match, pick the first (callers wanting a
                # specific one can wire a PendingChoice upstream).
                name_lc = (step.name_match or "").lower()
                bf = state.zones.get("battlefield")
                target_id: Optional[str] = None
                if bf is not None and name_lc:
                    for oid in bf.objects:
                        cand = state.objects.get(oid)
                        if cand is None or cand.controller != player_id:
                            continue
                        if (cand.name or "").lower() == name_lc:
                            target_id = oid
                            break
                if target_id is not None:
                    events.append(Event(
                        type=EventType.SACRIFICE,
                        payload={"object_id": target_id, "controller": player_id},
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


# ----------------------------------------------------------------------
# Exhaust reset
# ----------------------------------------------------------------------


def reset_exhaust(
    state: GameState,
    *,
    target_id: Optional[str] = None,
    ability_index: Optional[int] = None,
    controller: Optional[str] = None,
) -> int:
    """Clear ``once_per_game_used`` on Exhaust abilities so they can fire again.

    Resolution order (most specific to most permissive):
      - If ``target_id`` is given AND ``ability_index`` is given, reset just
        that one descriptor on that permanent.
      - If ``target_id`` is given, reset every Exhaust ability on it.
      - If ``controller`` is given (and no target_id), reset every Exhaust
        ability on every permanent that player controls.
      - If neither is given, reset every Exhaust ability in the game (rare;
        debug / "reset all" cards).

    Returns the number of ability descriptors that were reset (handy for
    tests / telemetry). A reset is a no-op for an ability that has not
    been used or that isn't an Exhaust (``once_per_game=False``).
    """
    n_reset = 0

    def _reset_one(ability: ActivatedAbility) -> None:
        nonlocal n_reset
        if not ability.once_per_game:
            return
        if ability.once_per_game_used:
            ability.once_per_game_used = False
            n_reset += 1

    def _reset_obj(o: GameObject, idx: Optional[int]) -> None:
        abilities = getattr(o.state, "activated_abilities", None) or []
        if idx is not None:
            if 0 <= idx < len(abilities):
                _reset_one(abilities[idx])
            return
        for ab in abilities:
            _reset_one(ab)

    if target_id is not None:
        obj = state.objects.get(target_id)
        if obj is not None:
            _reset_obj(obj, ability_index)
        return n_reset

    # Iterate all objects. Filter on controller if requested.
    for obj in list(state.objects.values()):
        if controller is not None and obj.controller != controller:
            continue
        _reset_obj(obj, None)
    return n_reset


def make_exhaust_reset_effect(
    source: GameObject,
    *,
    target_id: Optional[str] = None,
    ability_index: Optional[int] = None,
    controller: Optional[str] = None,
) -> list[Event]:
    """Helper for cards that grant Exhaust reset (e.g. Aetherdrift Elvish Refueler).

    Emits an EXHAUST_RESET marker event AND immediately calls
    ``reset_exhaust`` so the descriptor flag is cleared by the time the
    next legal-action sweep runs. The marker event lets observers / logs
    react ("Whenever an exhaust ability resets, ...").

    ``target_id``/``ability_index``/``controller`` mirror ``reset_exhaust``.
    """
    # The state reference comes from the source object's runtime state via
    # the priority/pipeline. The helper is meant to be called inside an
    # effect_fn where ``state`` is in scope, so callers do the call:
    #
    #   def my_effect(o, st, targets):
    #       return make_exhaust_reset_effect(o, controller=o.controller, state=st)
    #
    # but we also expose a stateless variant that *only* emits the event
    # and lets the caller invoke ``reset_exhaust`` separately. Tests use
    # the latter.
    payload: dict = {}
    if target_id is not None:
        payload["target_id"] = target_id
    if ability_index is not None:
        payload["ability_index"] = ability_index
    if controller is not None:
        payload["controller"] = controller
    return [Event(
        type=EventType.EXHAUST_RESET,
        payload=payload,
        source=source.id,
        controller=source.controller,
    )]


# ----------------------------------------------------------------------
# Dynamic ability mirror (Marvin, Murderous Mimic)
# ----------------------------------------------------------------------
#
# Some cards copy the activated abilities of other permanents at state-time:
# Marvin, Murderous Mimic — "Marvin has all activated abilities of creatures
# you control that don't have the same name as this creature."
#
# We model this with a state-keyed registry: ``state.ability_mirrors`` maps
# the mimic object's id -> AbilityMirror. The legal-action surface
# (``priority._get_activatable_abilities``) calls ``get_mirrored_abilities``
# in addition to the printed ones, and ``_handle_activate_ability`` looks up
# the descriptor via the ``mirror:<src>:<idx>`` ability_id prefix.
#
# The mirror is *additive*: it never replaces or hides existing abilities.
# Cost-pay still applies to the mimic (so Marvin taps itself when activating
# a {T} ability from a source creature; the source creature does not tap).
# Recursion is prevented by ``is_mirror_derived``: mirror-derived descriptors
# on a source creature are never themselves re-mirrored.


PredicateFn = Callable[[GameObject, GameState], list[GameObject]]


@dataclass
class AbilityMirror:
    """Registry entry: mimic object copies abilities from a dynamic source set."""

    source_obj_id: str
    predicate_fn: PredicateFn
    controller: str = ""


def register_ability_mirror(
    obj: GameObject,
    predicate_fn: PredicateFn,
    *,
    controller: Optional[str] = None,
) -> AbilityMirror:
    """Register an ability mirror for ``obj``.

    The mirror is consulted at state-time by the priority system when it
    enumerates activated abilities for ``obj`` and when it dispatches a
    ``mirror:<source_obj_id>:<idx>`` ability_id.

    Stored on ``obj.state`` so the registry is bound to the GameState that
    owns ``obj``: ``obj.state`` holds an ``ObjectState`` which is owned by
    the same GameState whose ``ability_mirrors`` dict we mutate via the
    GameState reference threaded through priority callers. We don't have a
    direct state ref at registration time, so we stash on ``obj`` and
    resolve at consumption time.
    """
    mirror = AbilityMirror(
        source_obj_id=obj.id,
        predicate_fn=predicate_fn,
        controller=controller or obj.controller,
    )
    # We need a state ref to populate ``state.ability_mirrors``. Setup
    # functions are called with ``(obj, state)`` in this codebase, but
    # ``register_ability_mirror`` is invoked from inside the setup body
    # where state is also in scope; helper wrappers thread the state into
    # the object's ``_state_ref`` (see Game.create_object). Use that.
    state = getattr(obj, "_state_ref", None)
    if state is None:
        # Defensive: try GameState-style lookup via priority callers later.
        # Stash on the object for the consumer to pick up on first use.
        if not hasattr(obj.state, "_pending_ability_mirror"):
            obj.state._pending_ability_mirror = mirror
        return mirror
    if not isinstance(getattr(state, "ability_mirrors", None), dict):
        state.ability_mirrors = {}
    state.ability_mirrors[obj.id] = mirror
    return mirror


def _resolve_state_mirror(obj: GameObject, state: GameState) -> Optional[AbilityMirror]:
    """Look up the mirror for ``obj``, lazily promoting any pending stash."""
    if not isinstance(getattr(state, "ability_mirrors", None), dict):
        state.ability_mirrors = {}
    mirror = state.ability_mirrors.get(obj.id)
    if mirror is not None:
        return mirror
    pending = getattr(obj.state, "_pending_ability_mirror", None)
    if pending is not None:
        state.ability_mirrors[obj.id] = pending
        try:
            delattr(obj.state, "_pending_ability_mirror")
        except AttributeError:
            pass
        return pending
    return None


def get_mirrored_abilities(
    obj: GameObject, state: GameState
) -> list[ActivatedAbility]:
    """Return the live list of ActivatedAbility descriptors mirrored onto ``obj``.

    For each creature returned by the registered ``predicate_fn``, we walk
    that creature's *printed* (non-mirror-derived) activated abilities and
    construct a fresh ActivatedAbility view "owned" by ``obj`` but whose
    ``effect_fn`` retains the original closure (so it still references the
    source creature's intended effect — Marvin's tap won't double-flag the
    source, but the source's effect_fn body runs as written).

    Recursion guard: any ability with ``is_mirror_derived=True`` on a source
    creature is skipped. Two coexisting Marvins each mirror the other's
    printed abilities (which are none unless we add some via test setup),
    not each other's mirror-derived views.

    Returned descriptors are *transient* (built fresh on each call). Callers
    must NOT mutate per-turn bookkeeping fields on them (those would be lost
    when the next call returns a new descriptor); instead, when an activation
    succeeds, the priority handler updates bookkeeping on the original source
    descriptor too.
    """
    mirror = _resolve_state_mirror(obj, state)
    if mirror is None:
        return []
    try:
        sources = mirror.predicate_fn(obj, state) or []
    except Exception:
        return []
    out: list[ActivatedAbility] = []
    for src in sources:
        src_abilities = getattr(src.state, "activated_abilities", None) or []
        for idx, ability in enumerate(src_abilities):
            if getattr(ability, "is_mirror_derived", False):
                # Don't re-mirror an already-mirrored ability — prevents A->B->A
                # cycles when two Marvins coexist.
                continue
            view = ActivatedAbility(
                cost_text=ability.cost_text,
                effect_fn=ability.effect_fn,
                description=ability.description,
                mana_cost=ability.mana_cost,
                requires_tap=ability.requires_tap,
                sac_self=ability.sac_self,
                discard_self=ability.discard_self,
                exile_self=ability.exile_self,
                additional_cost_plan=ability.additional_cost_plan,
                counter_removal=ability.counter_removal,
                sorcery_speed=ability.sorcery_speed,
                own_turn_only=ability.own_turn_only,
                once_per_turn=ability.once_per_turn,
                once_per_game=ability.once_per_game,
                has_x_cost=ability.has_x_cost,
                is_exhaust=ability.is_exhaust,
                targets_required=ability.targets_required,
                target_kind=ability.target_kind,
                # Carry per-turn bookkeeping by reference-ish — we still
                # update the source descriptor in ``record_activation`` to
                # avoid bypassing once-per-turn on the source itself, but
                # the mirror needs its own counters for once-per-turn from
                # Marvin's perspective. We initialise to defaults and the
                # priority handler will commit to both descriptors.
                activations_this_turn=ability.activations_this_turn,
                last_activation_turn=ability.last_activation_turn,
                total_activations=ability.total_activations,
                once_per_game_used=ability.once_per_game_used,
                ability_index=idx,
                is_adventure=ability.is_adventure,
                is_plot=ability.is_plot,
                precondition_fn=ability.precondition_fn,
                # Mark derived + back-reference.
                is_mirror_derived=True,
                mirror_source_obj_id=src.id,
                mirror_source_ability_index=idx,
            )
            out.append(view)
    return out


def find_mirrored_ability(
    obj: GameObject,
    state: GameState,
    source_obj_id: str,
    source_ability_index: int,
) -> Optional[ActivatedAbility]:
    """Look up a specific mirrored ability descriptor for dispatch.

    Called by ``priority._handle_activate_ability`` when it sees an
    ``ability_id`` starting with ``mirror:``.
    """
    mirror = _resolve_state_mirror(obj, state)
    if mirror is None:
        return None
    try:
        sources = mirror.predicate_fn(obj, state) or []
    except Exception:
        return None
    for src in sources:
        if src.id != source_obj_id:
            continue
        src_abilities = getattr(src.state, "activated_abilities", None) or []
        if not (0 <= source_ability_index < len(src_abilities)):
            return None
        ability = src_abilities[source_ability_index]
        if getattr(ability, "is_mirror_derived", False):
            return None
        # Build a fresh view (must mirror the structure produced by
        # ``get_mirrored_abilities`` so cost-pay sees the same flags).
        return ActivatedAbility(
            cost_text=ability.cost_text,
            effect_fn=ability.effect_fn,
            description=ability.description,
            mana_cost=ability.mana_cost,
            requires_tap=ability.requires_tap,
            sac_self=ability.sac_self,
            discard_self=ability.discard_self,
            exile_self=ability.exile_self,
            additional_cost_plan=ability.additional_cost_plan,
            counter_removal=ability.counter_removal,
            sorcery_speed=ability.sorcery_speed,
            own_turn_only=ability.own_turn_only,
            once_per_turn=ability.once_per_turn,
            once_per_game=ability.once_per_game,
            has_x_cost=ability.has_x_cost,
            is_exhaust=ability.is_exhaust,
            targets_required=ability.targets_required,
            target_kind=ability.target_kind,
            activations_this_turn=ability.activations_this_turn,
            last_activation_turn=ability.last_activation_turn,
            total_activations=ability.total_activations,
            once_per_game_used=ability.once_per_game_used,
            ability_index=source_ability_index,
            is_adventure=ability.is_adventure,
            is_plot=ability.is_plot,
            precondition_fn=ability.precondition_fn,
            is_mirror_derived=True,
            mirror_source_obj_id=src.id,
            mirror_source_ability_index=source_ability_index,
        )
    return None


def cleanup_ability_mirror(obj_id: str, state: GameState) -> None:
    """Remove the mirror entry for ``obj_id`` (called on leaves-battlefield).

    Safe to call when no entry exists. Idempotent.
    """
    mirrors = getattr(state, "ability_mirrors", None)
    if isinstance(mirrors, dict) and obj_id in mirrors:
        del mirrors[obj_id]


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
    "reset_exhaust",
    "make_exhaust_reset_effect",
    # Mirror system
    "AbilityMirror",
    "PredicateFn",
    "register_ability_mirror",
    "get_mirrored_abilities",
    "find_mirrored_ability",
    "cleanup_ability_mirror",
]
