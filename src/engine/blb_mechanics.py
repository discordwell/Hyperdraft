"""
Bloomburrow (BLB) Mechanic Helpers
==================================

This module owns the engine glue for the four set-defining BLB mechanics:

1. **Offspring {cost}** — when a creature with offspring enters the battlefield,
   create a 1/1 token copy of it. The "may pay an additional cost" portion is
   modeled as an unconditional ETB trigger (an "engine gap" simplification, in
   the same spirit as many other BLB cards in `src/cards/bloomburrow.py`).

2. **Forage** — "Exile three cards from your graveyard or sacrifice a Food."
   It is a *cost*, not a trigger. ``pay_forage_cost`` consumes the resource
   deterministically (prefers Food when available; falls back to exiling 3
   graveyard cards) and emits a ``FORAGE_PAID`` marker event so other cards
   can react to "whenever you forage".

3. **Expend N** — track the *total* mana spent across spells in a turn. When a
   player crosses threshold N (4 or 8), an ``EXPEND_N_REACHED`` event fires.
   This is hooked into ``priority.py`` which calls
   ``record_mana_spent_for_expend`` after each successful ``mana_system.pay_cost``.

4. **Valiant** — "Whenever this creature becomes the target of a spell or
   ability you control for the first time each turn, [effect]." We hook the
   ``_execute_targeted_effect`` callback in ``handlers/targeting.py`` to emit a
   ``VALIANT_TARGETED`` event for each chosen target whose source is controlled
   by the targeted permanent's controller. The helper enforces "first time
   each turn" via ``state.turn_data``.

All BLB-specific helpers and event types are appended to existing modules
rather than replacing or wrapping core types — see ``EventType`` additions in
``src/engine/types.py`` and the targeting/priority hooks below.
"""

from __future__ import annotations

from typing import Callable, Optional

from .types import (
    Event, EventType, ZoneType, CardType, Color,
    GameObject, GameState,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    new_id,
)


# === BLB MECHANICS HELPERS ===

# -----------------------------------------------------------------------------
# OFFSPRING — ETB trigger that creates a 1/1 token copy of the creature.
# -----------------------------------------------------------------------------
def make_offspring_setup(
    offspring_cost: Optional[str] = None,
    base_setup: Optional[Callable[[GameObject, GameState], list[Interceptor]]] = None,
) -> Callable[[GameObject, GameState], list[Interceptor]]:
    """
    Build a ``setup_interceptors`` function for a creature with Offspring.

    Args:
        offspring_cost: The printed offspring cost string (e.g. ``"{2}"``,
            ``"{1}{U}"``). Currently informational — stored on the resulting
            interceptor so card text/UI layers can surface it. The actual
            "may pay" gating is an engine gap; we always create the token copy
            on ETB, matching how other BLB simplifications are handled.
        base_setup: Optional underlying setup function to compose with. Its
            interceptors are returned alongside the offspring ETB trigger.

    Returns:
        A setup_interceptors callable.
    """

    def offspring_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        interceptors: list[Interceptor] = []

        if base_setup is not None:
            try:
                base_ints = base_setup(obj, state) or []
            except Exception:
                base_ints = []
            interceptors.extend(base_ints)

        def etb_filter(event: Event, state: GameState) -> bool:
            if event.type != EventType.ZONE_CHANGE:
                return False
            if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
                return False
            return event.payload.get('object_id') == obj.id

        def etb_handler(event: Event, state: GameState) -> InterceptorResult:
            # Build a shallow-copy 1/1 token of the source creature.
            chars = obj.characteristics
            token_payload = {
                'controller': obj.controller,
                'owner': obj.controller,
                'name': obj.name,
                'to_zone_type': ZoneType.BATTLEFIELD,
                'types': set(chars.types),
                'subtypes': set(chars.subtypes),
                'colors': set(chars.colors),
                'power': 1,
                'toughness': 1,
                'abilities': list(chars.abilities or []),
                'is_token': True,
            }
            new_events = [
                Event(
                    type=EventType.OBJECT_CREATED,
                    payload=token_payload,
                    source=obj.id,
                    controller=obj.controller,
                ),
                Event(
                    type=EventType.OFFSPRING_TRIGGERED,
                    payload={'controller': obj.controller, 'parent_id': obj.id,
                             'offspring_cost': offspring_cost},
                    source=obj.id,
                    controller=obj.controller,
                ),
            ]
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=new_events,
            )

        offspring_int = Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=etb_filter,
            handler=etb_handler,
            duration='while_on_battlefield',
        )
        interceptors.append(offspring_int)
        return interceptors

    return offspring_setup


# -----------------------------------------------------------------------------
# FORAGE — pay-cost helper. Returns True if the cost was paid.
# -----------------------------------------------------------------------------
def pay_forage_cost(
    player_id: str,
    state: GameState,
    source_id: Optional[str] = None,
    pipeline=None,
) -> bool:
    """
    Pay a forage cost: exile three cards from the player's graveyard OR
    sacrifice a Food.

    Strategy: prefer sacrificing a Food (cheapest in graveyard terms) if any
    is available; otherwise fall back to exiling the three most-recently-added
    graveyard cards. Returns False (without consuming anything) if neither
    option is available.

    Emits a ``FORAGE_PAID`` marker event so other cards can react to
    "whenever you forage". If a ``pipeline`` is supplied, the consumption
    events are routed through it; otherwise they are returned implicitly via
    direct mutation (acceptable for simple call sites and tests).
    """
    player = state.players.get(player_id)
    if player is None:
        return False

    # 1) Try to sacrifice a Food permanent we control.
    food_id: Optional[str] = None
    for obj in state.objects.values():
        if obj.controller != player_id:
            continue
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        if 'Food' in obj.characteristics.subtypes:
            food_id = obj.id
            break

    if food_id is not None:
        sac_event = Event(
            type=EventType.SACRIFICE,
            payload={'object_id': food_id, 'player': player_id},
            source=source_id,
            controller=player_id,
        )
        forage_event = Event(
            type=EventType.FORAGE_PAID,
            payload={'controller': player_id, 'method': 'food',
                     'food_id': food_id},
            source=source_id,
            controller=player_id,
        )
        if pipeline is not None:
            pipeline.emit(sac_event)
            pipeline.emit(forage_event)
        else:
            # Best-effort direct sacrifice for callers without a pipeline.
            from .pipeline.handlers.zone import _handle_sacrifice
            _handle_sacrifice(sac_event, state)
        return True

    # 2) Otherwise exile three cards from our graveyard.
    gy_key = f"graveyard_{player_id}"
    gy = state.zones.get(gy_key)
    if gy is None or len(gy.objects) < 3:
        return False

    # Take the top three (most recently put there).
    to_exile = list(gy.objects[-3:])
    if pipeline is not None:
        pipeline.emit(Event(
            type=EventType.EXILE,
            payload={'object_ids': to_exile},
            source=source_id,
            controller=player_id,
        ))
        pipeline.emit(Event(
            type=EventType.FORAGE_PAID,
            payload={'controller': player_id, 'method': 'exile_three',
                     'exiled_ids': to_exile},
            source=source_id,
            controller=player_id,
        ))
    else:
        # Fallback direct mutation (sufficient for unit tests).
        from .pipeline.handlers.zone import _handle_exile
        ev = Event(
            type=EventType.EXILE,
            payload={'object_ids': to_exile},
            source=source_id,
            controller=player_id,
        )
        _handle_exile(ev, state)
    return True


def make_forage_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
) -> Interceptor:
    """
    React to ``FORAGE_PAID`` events by ``source_obj.controller``.

    This implements "whenever you forage, ..." abilities (e.g. Scurry of
    Squirrels: "Whenever you forage, put a +1/+1 counter on this creature").
    """

    def forage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.FORAGE_PAID:
            return False
        return event.payload.get('controller') == source_obj.controller

    def forage_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=effect_fn(event, state),
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=forage_filter,
        handler=forage_handler,
        duration='while_on_battlefield',
    )


# -----------------------------------------------------------------------------
# EXPEND N — track total mana spent per turn; fire EXPEND_N_REACHED on cross.
# -----------------------------------------------------------------------------
_EXPEND_TURN_KEY_FMT = "mana_spent_{player}"
_EXPEND_FIRED_KEY_FMT = "expend_{n}_fired_{player}"


def record_mana_spent_for_expend(
    state: GameState,
    player_id: str,
    amount: int,
    source_id: Optional[str] = None,
) -> list[Event]:
    """
    Update the running mana-spent counter for ``player_id`` and return any
    EXPEND threshold events that fire as a result of this payment.

    Called from ``priority.py`` after a successful ``mana_system.pay_cost``.
    Each EXPEND threshold (4, 8) fires at most once per player per turn,
    governed by ``state.turn_data['expend_<n>_fired_<player>']``.
    """
    if amount <= 0:
        return []

    key = _EXPEND_TURN_KEY_FMT.format(player=player_id)
    prior = int(state.turn_data.get(key, 0) or 0)
    new_total = prior + int(amount)
    state.turn_data[key] = new_total

    fired: list[Event] = []
    for threshold, evt_type in (
        (4, EventType.EXPEND_4_REACHED),
        (8, EventType.EXPEND_8_REACHED),
    ):
        fired_key = _EXPEND_FIRED_KEY_FMT.format(n=threshold, player=player_id)
        if state.turn_data.get(fired_key):
            continue
        if prior < threshold <= new_total:
            state.turn_data[fired_key] = True
            fired.append(Event(
                type=evt_type,
                payload={'controller': player_id, 'threshold': threshold,
                         'total': new_total},
                source=source_id,
                controller=player_id,
            ))
    return fired


def reset_expend_for_turn(state: GameState, player_id: str) -> None:
    """Reset per-turn mana-spent tracking. Call at TURN_START / cleanup."""
    for key in (
        _EXPEND_TURN_KEY_FMT.format(player=player_id),
        _EXPEND_FIRED_KEY_FMT.format(n=4, player=player_id),
        _EXPEND_FIRED_KEY_FMT.format(n=8, player=player_id),
    ):
        state.turn_data.pop(key, None)


def make_expend_trigger(
    source_obj: GameObject,
    threshold: int,
    effect_fn: Callable[[Event, GameState], list[Event]],
) -> Interceptor:
    """
    Fire ``effect_fn`` when ``source_obj.controller`` crosses the EXPEND
    threshold this turn. ``threshold`` must be 4 or 8.
    """
    if threshold == 4:
        wanted_type = EventType.EXPEND_4_REACHED
    elif threshold == 8:
        wanted_type = EventType.EXPEND_8_REACHED
    else:
        raise ValueError(f"Expend threshold must be 4 or 8, got {threshold}")

    def expend_filter(event: Event, state: GameState) -> bool:
        if event.type != wanted_type:
            return False
        return event.payload.get('controller') == source_obj.controller

    def expend_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=effect_fn(event, state),
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=expend_filter,
        handler=expend_handler,
        duration='while_on_battlefield',
    )


# -----------------------------------------------------------------------------
# VALIANT — "When this creature becomes the target of a spell or ability you
# control for the first time each turn, [effect]."
# -----------------------------------------------------------------------------
_VALIANT_FIRED_KEY_FMT = "valiant_fired_{obj}_{turn}"


def emit_valiant_target_events(
    target_ids: list,
    source_id: Optional[str],
    controller_id: Optional[str],
    state: GameState,
) -> list[Event]:
    """
    Build ``VALIANT_TARGETED`` events for each chosen target. Called from
    ``handlers/targeting._execute_targeted_effect`` after the player commits
    target selection. Skips player IDs (Valiant only triggers for permanents)
    and skips targets whose controller does not match the caster
    (Valiant only fires for *your* spells/abilities).
    """
    events: list[Event] = []
    if not controller_id or not target_ids:
        return events
    for tid in target_ids:
        target = state.objects.get(tid) if isinstance(tid, str) else None
        if target is None:
            # Player target or non-object — Valiant only triggers on permanents.
            continue
        if target.controller != controller_id:
            continue
        events.append(Event(
            type=EventType.VALIANT_TARGETED,
            payload={
                'target_id': target.id,
                'source_id': source_id,
                'controller': controller_id,
            },
            source=source_id,
            controller=controller_id,
        ))
    return events


def make_valiant_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    once_per_turn: bool = True,
) -> Interceptor:
    """
    Build a Valiant trigger interceptor.

    Fires when ``source_obj`` is the target of a spell or ability whose
    controller equals ``source_obj.controller``. By default the trigger fires
    only once per turn (printed Valiant ability text), tracked in
    ``state.turn_data``.
    """

    def valiant_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.VALIANT_TARGETED:
            return False
        if event.payload.get('target_id') != source_obj.id:
            return False
        if event.payload.get('controller') != source_obj.controller:
            return False
        if once_per_turn:
            key = _VALIANT_FIRED_KEY_FMT.format(
                obj=source_obj.id, turn=state.turn_number
            )
            if state.turn_data.get(key):
                return False
        return True

    def valiant_handler(event: Event, state: GameState) -> InterceptorResult:
        if once_per_turn:
            key = _VALIANT_FIRED_KEY_FMT.format(
                obj=source_obj.id, turn=state.turn_number
            )
            state.turn_data[key] = True
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=effect_fn(event, state),
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=valiant_filter,
        handler=valiant_handler,
        duration='while_on_battlefield',
    )


__all__ = [
    'make_offspring_setup',
    'pay_forage_cost',
    'make_forage_trigger',
    'record_mana_spent_for_expend',
    'reset_expend_for_turn',
    'make_expend_trigger',
    'emit_valiant_target_events',
    'make_valiant_trigger',
]
