"""Planeswalker loyalty framework.

Implements the rules-engine plumbing for planeswalker permanents (CR 113.5g,
606, 716):

- ETB with starting loyalty counters.
- Loyalty-cost activated abilities (``+N: ...``, ``-N: ...``, ``0: ...``).
- Once-per-turn activation per planeswalker (across ALL its loyalty abilities).
- Sorcery-speed restriction (own turn, main phase, empty stack).
- Damage redirection: damage to a planeswalker removes that many loyalty
  counters via a TRANSFORM-priority interceptor on EventType.DAMAGE.
- 0-loyalty SBA: a state-based check destroys planeswalkers with 0 or fewer
  loyalty counters (added to the SBA loop in turn.py).

This module exports two helpers:

- ``make_loyalty_ability(obj, *, cost, effect_fn, ability_id, ...)`` —
  registers a loyalty-cost activated ability.
- ``make_planeswalker_setup(obj, starting_loyalty)`` — returns the standard
  interceptor bundle (ETB loyalty, damage redirection, turn-start reset of
  the once-per-turn lock, and a sibling-lockout REACT trigger).

Both are re-exported from ``src.cards.interceptor_helpers`` for convenience.

Implementation notes:

- For the **negative-cost** case (``-N: ...``) we register the ability with
  ``counter_removal=("loyalty", N)``; this lets the standard activated-ability
  cost-validator (``can_pay_activation``) reject the activation when the
  planeswalker has fewer than N loyalty counters and lets the standard cost
  payer (``pay_activation_cost``) emit the COUNTER_REMOVED event and update
  ``obj.state.counters`` directly. We do not duplicate this in the effect_fn.
- For the **positive-cost** case (``+N: ...``), we emit a COUNTER_ADDED event
  from the effect_fn at resolution time.
- For **zero-cost** (``0: ...``), we emit no counter event.

- Once-per-turn-across-all-loyalty-abilities is enforced by a REACT
  interceptor on ``EventType.LOYALTY_ABILITY_ACTIVATED`` that, when fired,
  bumps ``last_activation_turn`` on every loyalty ability registered on the
  same planeswalker. The standard ``can_pay_activation`` then refuses any
  further activation this turn (each ability's ``once_per_turn`` flag is
  True). At TURN_START we explicitly reset the bookkeeping for the
  planeswalker's loyalty abilities.
"""

from __future__ import annotations

from typing import Callable, Optional

from .types import (
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    ZoneType,
    new_id,
)

EffectFn = Callable[[GameObject, GameState, list], list[Event]]


# ---------------------------------------------------------------------------
# Bookkeeping helpers
# ---------------------------------------------------------------------------


def get_loyalty(obj: GameObject) -> int:
    """Return the planeswalker's current loyalty (loyalty counter count)."""
    return int(obj.state.counters.get("loyalty", 0))


def _iter_loyalty_abilities(obj: GameObject):
    abilities = getattr(obj.state, "activated_abilities", None) or []
    for ab in abilities:
        if getattr(ab, "is_loyalty", False):
            yield ab


# ---------------------------------------------------------------------------
# make_loyalty_ability
# ---------------------------------------------------------------------------


def make_loyalty_ability(
    obj: GameObject,
    *,
    cost: int,
    effect_fn: EffectFn,
    ability_id: str,
    targets_required: int = 0,
    target_kind: str = "any",
    sorcery_speed: bool = True,
    once_per_turn: bool = True,
    description: str = "",
):
    """Register a loyalty-cost activated ability on a planeswalker.

    Args:
        obj: the planeswalker GameObject.
        cost: signed loyalty cost. Positive adds loyalty counters; negative
            removes loyalty counters as a cost (only legal when the
            planeswalker has at least ``abs(cost)`` loyalty); zero is allowed
            and changes nothing.
        effect_fn: ``(obj, state, targets) -> list[Event]``. Called as the
            ability resolves; should NOT emit the COUNTER_ADDED/COUNTER_REMOVED
            for paying loyalty — those are emitted by this helper / by the
            standard activated-ability cost payer.
        ability_id: a logical identifier ("+1", "-3", etc.) used for logging
            and to populate the LOYALTY_ABILITY_ACTIVATED marker payload.
        targets_required: number of targets the ability requires.
        target_kind: target kind hint used by the targeting subsystem.
        sorcery_speed: when True (default), the ability is restricted to the
            controller's own turn at sorcery speed (main phase, empty stack).
        once_per_turn: when True (default), at most one loyalty ability per
            planeswalker may be activated per turn (CR 606.5).
        description: human-readable description (defaults to a synthesised
            description from cost + ability_id).

    Returns the registered ``ActivatedAbility`` descriptor.
    """
    # Local import to avoid cycles.
    from .activated import register_activated_ability

    cost_int = int(cost)
    obj_id = obj.id

    if not description:
        sign = "+" if cost_int > 0 else ("" if cost_int == 0 else "")
        description = f"Loyalty {sign}{cost_int}: {ability_id}"

    def _wrapped_effect(o: GameObject, state: GameState, targets: list) -> list[Event]:
        # On resolution: emit the loyalty change event (positive cost only —
        # negative cost is paid up-front via counter_removal handled by
        # pay_activation_cost; we suppress the handler-side decrement via
        # a TRANSFORM interceptor installed in make_planeswalker_setup so
        # the cost is only paid once).
        events: list[Event] = []
        if cost_int > 0:
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    "object_id": o.id,
                    "counter_type": "loyalty",
                    "amount": cost_int,
                },
                source=o.id,
                controller=o.controller,
            ))

        events.append(Event(
            type=EventType.LOYALTY_ABILITY_ACTIVATED,
            payload={
                "source": o.id,
                "controller": o.controller,
                "ability_id": ability_id,
                "cost": cost_int,
            },
            source=o.id,
            controller=o.controller,
        ))

        try:
            extra = effect_fn(o, state, list(targets) if targets else []) or []
        except Exception:
            extra = []
        events.extend(extra)
        return events

    # Cost text:
    # - Positive cost: pay nothing upfront; effect emits COUNTER_ADDED on resolve.
    # - Negative cost: register counter_removal so can_pay_activation gates
    #   on current loyalty, and pay_activation_cost emits COUNTER_REMOVED.
    # - Zero cost: nothing.
    #
    # The cost-text string must parse via parse_activation_cost. We append a
    # unique tag (``[loyalty:<id>]``) so the dedupe logic in
    # ``register_activated_ability`` does not collapse multiple loyalty
    # abilities with empty / identical cost text together. The tag is parsed
    # as an "additional phrase" and discarded by ``parse_cost_expression``.
    if cost_int < 0:
        cost_text = f"Remove {abs(cost_int)} loyalty counters from this"
    elif cost_int > 0:
        cost_text = f"[loyalty:+{cost_int}:{ability_id}]"
    else:
        cost_text = f"[loyalty:0:{ability_id}]"

    ability = register_activated_ability(
        obj,
        cost=cost_text,
        effect_fn=_wrapped_effect,
        description=description,
        sorcery_speed=sorcery_speed,
        own_turn_only=sorcery_speed,
        once_per_turn=bool(once_per_turn),
        targets_required=targets_required,
        target_kind=target_kind,
    )
    # Tag the descriptor with our loyalty metadata so the sibling-lockout
    # REACT interceptor and tests can identify loyalty abilities.
    ability.is_loyalty = True
    ability.loyalty_cost = cost_int
    ability.loyalty_ability_id = ability_id
    ability.loyalty_owner_id = obj_id
    return ability


# ---------------------------------------------------------------------------
# make_planeswalker_setup
# ---------------------------------------------------------------------------


def make_planeswalker_setup(
    obj: GameObject,
    starting_loyalty: int,
) -> list[Interceptor]:
    """Return interceptors for the standard planeswalker rules:

    - ETB: place ``starting_loyalty`` loyalty counters on this planeswalker.
    - Damage redirection: install a TRANSFORM interceptor on EventType.DAMAGE
      so that damage to this planeswalker becomes loyalty-counter removal.
    - Once-per-turn lockout: REACT to LOYALTY_ABILITY_ACTIVATED and bump
      ``last_activation_turn`` on every loyalty ability registered on this
      planeswalker.
    - Turn-start reset: clear the once-per-turn bookkeeping at TURN_START.

    The 0-loyalty state-based action lives in the SBA loop (see
    ``src.engine.turn`` — ``check_planeswalker_zero_loyalty_sbas``).
    """

    starting_loyalty = max(0, int(starting_loyalty))
    obj_id = obj.id
    obj_controller = obj.controller

    # ------------------------------------------------------------------
    # ETB: add starting loyalty counters.
    # ------------------------------------------------------------------
    def _etb_filter(event: Event, state: GameState) -> bool:
        if event.type == EventType.ZONE_CHANGE:
            return (
                event.payload.get("to_zone_type") == ZoneType.BATTLEFIELD
                and event.payload.get("object_id") == obj_id
            )
        if event.type == EventType.OBJECT_CREATED:
            return (
                event.payload.get("object_id") == obj_id
                and event.payload.get("to_zone_type") == ZoneType.BATTLEFIELD
            )
        return False

    def _etb_handler(event: Event, state: GameState) -> InterceptorResult:
        # Defensive: only fire once. If counters are already present,
        # treat as already-initialised (e.g. tests creating the PW directly
        # on the battlefield with counters).
        current = state.objects.get(obj_id)
        if current is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        if current.state.counters.get("loyalty", 0) > 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        if starting_loyalty <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    "object_id": obj_id,
                    "counter_type": "loyalty",
                    "amount": starting_loyalty,
                },
                source=obj_id,
                controller=obj_controller,
            )],
        )

    etb_interceptor = Interceptor(
        id=new_id(),
        source=obj_id,
        controller=obj_controller,
        priority=InterceptorPriority.REACT,
        filter=_etb_filter,
        handler=_etb_handler,
        duration="while_on_battlefield",
    )

    # ------------------------------------------------------------------
    # Loyalty-cost double-decrement workaround: pay_activation_cost
    # eagerly decrements obj.state.counters[ctype] AND emits a
    # COUNTER_REMOVED event whose handler decrements again. For loyalty
    # costs (source = this PW), we TRANSFORM amount -> 0 so the handler
    # is a no-op while preserving the event for REACT triggers (including
    # our zero-loyalty SBA check). The damage-redirection path emits
    # COUNTER_REMOVED with source = damager (not this PW), so it is left
    # untouched.
    # ------------------------------------------------------------------
    def _suppress_double_decrement_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.COUNTER_REMOVED:
            return False
        if event.payload.get("object_id") != obj_id:
            return False
        if event.payload.get("counter_type") != "loyalty":
            return False
        # Only suppress for self-sourced COUNTER_REMOVED (loyalty-cost payment).
        return getattr(event, "source", None) == obj_id

    def _suppress_double_decrement_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload["amount"] = 0
        # Mark the event so REACT interceptors know the eager decrement
        # has already paid the cost and don't repeat work.
        new_event.payload["_loyalty_eager_paid"] = True
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    suppress_interceptor = Interceptor(
        id=new_id(),
        source=obj_id,
        controller=obj_controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=_suppress_double_decrement_filter,
        handler=_suppress_double_decrement_handler,
        duration="while_on_battlefield",
    )

    # ------------------------------------------------------------------
    # Damage redirection: TRANSFORM DAMAGE → COUNTER_REMOVED for this PW.
    # ------------------------------------------------------------------
    def _damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get("target") != obj_id:
            return False
        # Only intercept while we're on the battlefield.
        current = state.objects.get(obj_id)
        return bool(current and current.zone == ZoneType.BATTLEFIELD)

    def _damage_handler(event: Event, state: GameState) -> InterceptorResult:
        amount = int(event.payload.get("amount", 0) or 0)
        if amount <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        damager = getattr(event, "source", None) or event.payload.get("source")
        # Track damager so the SBA-driven destruction can credit the source.
        current = state.objects.get(obj_id)
        if current is not None and damager:
            current.state.last_damage_source = damager
        # Replace DAMAGE with a COUNTER_REMOVED so the standard handler
        # decrements obj.state.counters['loyalty']. Note we do NOT mark
        # ``_loyalty_eager_paid`` here — this is a damage hit, not an
        # activated-ability cost, so the suppress_interceptor (which only
        # filters on source == obj_id) won't fire and the handler will run
        # normally. The PLANESWALKER_DAMAGED marker fires from the REACT
        # interceptor below.
        replacement = Event(
            type=EventType.COUNTER_REMOVED,
            payload={
                "object_id": obj_id,
                "counter_type": "loyalty",
                "amount": amount,
            },
            source=damager,
            controller=event.controller,
        )
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=replacement,
        )

    damage_interceptor = Interceptor(
        id=new_id(),
        source=obj_id,
        controller=obj_controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=_damage_filter,
        handler=_damage_handler,
        duration="while_on_battlefield",
    )

    # ------------------------------------------------------------------
    # PLANESWALKER_DAMAGED marker. We fire this in REACT-after-DAMAGE
    # using a separate trigger that *also* matches the original DAMAGE
    # event (before the TRANSFORM rewrites it). Since TRANSFORM phase
    # mutates the event in place, REACT actually sees the post-TRANSFORM
    # COUNTER_REMOVED. We instead piggyback on the COUNTER_REMOVED event:
    # any damage-sourced (source != obj_id) COUNTER_REMOVED targeting
    # this PW signifies a damage hit. The marker is informational; it
    # does not drive the SBA (the SBA hook listens on COUNTER_REMOVED
    # directly).
    # ------------------------------------------------------------------
    def _damage_marker_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.COUNTER_REMOVED:
            return False
        if event.payload.get("object_id") != obj_id:
            return False
        if event.payload.get("counter_type") != "loyalty":
            return False
        # Skip activated-ability cost paths.
        return getattr(event, "source", None) != obj_id

    def _damage_marker_handler(event: Event, state: GameState) -> InterceptorResult:
        damager = getattr(event, "source", None)
        amount = int(event.payload.get("amount", 0) or 0)
        if amount <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.PLANESWALKER_DAMAGED,
                payload={
                    "target": obj_id,
                    "amount": amount,
                    "source": damager,
                },
                source=damager,
                controller=event.controller,
            )],
        )

    damage_marker_interceptor = Interceptor(
        id=new_id(),
        source=obj_id,
        controller=obj_controller,
        priority=InterceptorPriority.REACT,
        filter=_damage_marker_filter,
        handler=_damage_marker_handler,
        duration="while_on_battlefield",
    )

    # ------------------------------------------------------------------
    # Once-per-turn-across-all-loyalty-abilities lockout.
    # When ANY loyalty ability on this PW resolves, bump every sibling
    # loyalty ability's last_activation_turn to the current turn.
    # ------------------------------------------------------------------
    def _lockout_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.LOYALTY_ABILITY_ACTIVATED
            and event.payload.get("source") == obj_id
        )

    def _lockout_handler(event: Event, state: GameState) -> InterceptorResult:
        current = state.objects.get(obj_id)
        if current is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        for sibling in _iter_loyalty_abilities(current):
            sibling.last_activation_turn = state.turn_number
            sibling.activations_this_turn = max(1, getattr(sibling, "activations_this_turn", 0))
        return InterceptorResult(action=InterceptorAction.PASS)

    lockout_interceptor = Interceptor(
        id=new_id(),
        source=obj_id,
        controller=obj_controller,
        priority=InterceptorPriority.REACT,
        filter=_lockout_filter,
        handler=_lockout_handler,
        duration="while_on_battlefield",
    )

    # ------------------------------------------------------------------
    # Turn-start: reset the once-per-turn lockout for this planeswalker.
    # ------------------------------------------------------------------
    def _turn_start_filter(event: Event, state: GameState) -> bool:
        return event.type == EventType.TURN_START

    def _turn_start_handler(event: Event, state: GameState) -> InterceptorResult:
        current = state.objects.get(obj_id)
        if current is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        for ability in _iter_loyalty_abilities(current):
            # Force the ability to be re-activatable this turn.
            ability.last_activation_turn = -1
            ability.activations_this_turn = 0
        return InterceptorResult(action=InterceptorAction.PASS)

    turn_start_interceptor = Interceptor(
        id=new_id(),
        source=obj_id,
        controller=obj_controller,
        priority=InterceptorPriority.REACT,
        filter=_turn_start_filter,
        handler=_turn_start_handler,
        duration="while_on_battlefield",
    )

    # ------------------------------------------------------------------
    # Zero-loyalty SBA: when this planeswalker's loyalty hits 0 (or below),
    # schedule destruction. We piggyback on the COUNTER_REMOVED event that
    # follows every loyalty-cost activation and every redirected damage hit.
    # The SBA helper in src/engine/turn.py lets tests invoke this without
    # going through the priority loop; this interceptor closes the loop in
    # normal play.
    # ------------------------------------------------------------------
    def _sba_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.COUNTER_REMOVED, EventType.PLANESWALKER_DAMAGED):
            return False
        target_id = event.payload.get("object_id") or event.payload.get("target")
        return target_id == obj_id

    def _sba_handler(event: Event, state: GameState) -> InterceptorResult:
        current = state.objects.get(obj_id)
        if current is None or current.zone != ZoneType.BATTLEFIELD:
            return InterceptorResult(action=InterceptorAction.PASS)
        if get_loyalty(current) > 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.OBJECT_DESTROYED,
                payload={"object_id": obj_id, "reason": "zero_loyalty"},
                source=current.state.last_damage_source,
                controller=obj_controller,
            )],
        )

    sba_interceptor = Interceptor(
        id=new_id(),
        source=obj_id,
        controller=obj_controller,
        priority=InterceptorPriority.REACT,
        filter=_sba_filter,
        handler=_sba_handler,
        duration="while_on_battlefield",
    )

    return [etb_interceptor, suppress_interceptor, damage_interceptor,
            damage_marker_interceptor, lockout_interceptor,
            turn_start_interceptor, sba_interceptor]


# ---------------------------------------------------------------------------
# Zero-loyalty SBA helper (consumed by turn.py SBA hook)
# ---------------------------------------------------------------------------


def planeswalkers_with_zero_loyalty(state: GameState) -> list:
    """Return a list of planeswalker GameObjects on the battlefield whose
    loyalty is 0 or less. Used by the SBA loop to schedule destruction.
    """
    from .types import CardType
    out = []
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return out
    for obj_id in list(battlefield.objects):
        obj = state.objects.get(obj_id)
        if obj is None:
            continue
        if CardType.PLANESWALKER not in obj.characteristics.types:
            continue
        if get_loyalty(obj) <= 0:
            out.append(obj)
    return out


__all__ = [
    "make_loyalty_ability",
    "make_planeswalker_setup",
    "planeswalkers_with_zero_loyalty",
    "get_loyalty",
]
