"""
Spell resolve helpers — composable callable factories.

Card definitions traditionally implement their resolve effect as a closure
captured by their setup. For instants/sorceries with simple effects, this
module provides ``resolve_*`` factories that return ``(targets, state) ->
list[Event]`` callables matching the existing ``StackItem.resolve_fn``
contract used by ``src/engine/stack.py``.

Use ``resolve_chain(...)`` to compose multiple effects in order, and
``resolve_modal(...)`` to support "choose one" modal spells.

Example
-------

.. code-block:: python

    # "Lightning Bolt deals 2 damage to any target. Draw a card."
    CARD = make_instant(
        name="Lightning Bolt",
        ...,
        resolve=resolve_chain(
            resolve_damage(2),
            resolve_draw(1),
        ),
    )

Callable signature
------------------

Every helper returns a function with the canonical resolve signature::

    resolve_fn(targets: list[list[Target]], state: GameState) -> list[Event]

``targets`` is the list of target groups (one list per ``TargetRequirement``).
For text-parsed spells without formal targeting, ``targets`` may be ``[]``
or ``[[]]``; the helpers handle both shapes defensively.

The factories accept ``source_id`` lazily — when a card definition wires a
resolve helper as ``resolve=`` on the card def, the stack manager passes the
card_id as the spell's source via the StackItem and the engine fills it in
at call time. Helpers therefore take the source from the *first* target's
controller-of-resolving-spell when available; in practice the engine keeps
this metadata via the surrounding ``StackItem`` and passes through the
relevant Event ``source`` field.
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from .types import (
    Color,
    CardType,
    Event,
    EventType,
    GameState,
)
from .targeting import Target


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

ResolveFn = Callable[[list[list[Target]], GameState], list[Event]]


def _flatten_targets(targets: Optional[list[list[Target]]]) -> list[Target]:
    """Return all chosen targets as a single flat list."""
    if not targets:
        return []
    out: list[Target] = []
    for group in targets:
        if not group:
            continue
        for t in group:
            if t is not None:
                out.append(t)
    return out


def _first_target(targets: Optional[list[list[Target]]]) -> Optional[Target]:
    flat = _flatten_targets(targets)
    return flat[0] if flat else None


def _caster_id_from_state_and_targets(
    state: GameState,
    targets: Optional[list[list[Target]]],
) -> Optional[str]:
    """Best-effort extraction of the resolving spell's controller.

    Strategy (in order):
    1. Walk ``state.zones['stack'].objects`` for the most recently pushed
       spell card; return its controller.
    2. Fall back to ``state.priority_player`` (during normal resolution this
       is the spell's controller).
    3. Fall back to ``state.active_player``.
    4. As a final resort, walk targets and return the first target's
       controller (or itself if it's a player target).
    """
    # 1. Topmost spell on the stack zone.
    stack_zone = state.zones.get('stack') if state and state.zones else None
    if stack_zone is not None:
        for obj_id in reversed(list(stack_zone.objects or [])):
            obj = state.objects.get(obj_id)
            if obj is not None and obj.controller:
                return obj.controller

    # 2/3. Priority player, then active player.
    pp = getattr(state, 'priority_player', None)
    if pp:
        return pp
    ap = getattr(state, 'active_player', None)
    if ap:
        return ap

    # 4. Walk targets.
    for t in _flatten_targets(targets):
        if t.is_player:
            return t.id
        obj = state.objects.get(t.id)
        if obj is not None and obj.controller:
            return obj.controller
    return None


# ---------------------------------------------------------------------------
# Public factories
# ---------------------------------------------------------------------------

def resolve_damage(amount: int, to_each_opponent: bool = False) -> ResolveFn:
    """Deal ``amount`` damage.

    By default deals damage to each chosen target. With
    ``to_each_opponent=True``, the spell ignores chosen targets and deals
    damage to each opponent of the spell's controller (e.g. "Pyroclasm to
    each opponent").
    """
    def _resolve(targets: list[list[Target]], state: GameState) -> list[Event]:
        events: list[Event] = []
        if to_each_opponent:
            caster = _caster_id_from_state_and_targets(state, targets)
            if caster is None:
                return []
            for pid in state.players:
                if pid == caster:
                    continue
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={
                        'target': pid,
                        'amount': amount,
                        'is_combat': False,
                        'is_player': True,
                    },
                ))
            return events
        for t in _flatten_targets(targets):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={
                    'target': t.id,
                    'amount': amount,
                    'is_combat': False,
                    'is_player': t.is_player,
                },
            ))
        return events

    return _resolve


def resolve_destroy() -> ResolveFn:
    """Destroy each chosen target permanent."""
    def _resolve(targets: list[list[Target]], state: GameState) -> list[Event]:
        events: list[Event] = []
        for t in _flatten_targets(targets):
            if t.is_player:
                continue
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': t.id},
            ))
        return events

    return _resolve


def resolve_exile() -> ResolveFn:
    """Exile each chosen target permanent."""
    from .types import ZoneType

    def _resolve(targets: list[list[Target]], state: GameState) -> list[Event]:
        events: list[Event] = []
        for t in _flatten_targets(targets):
            if t.is_player:
                continue
            events.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': t.id,
                    'to_zone_type': ZoneType.EXILE,
                    'to_zone': 'exile',
                },
            ))
        return events

    return _resolve


def resolve_draw(amount: int = 1, to_caster: bool = True) -> ResolveFn:
    """Draw ``amount`` cards.

    If ``to_caster=True`` (default) the spell's controller draws. Otherwise,
    the first targeted player draws.
    """
    def _resolve(targets: list[list[Target]], state: GameState) -> list[Event]:
        if to_caster:
            player = _caster_id_from_state_and_targets(state, targets)
        else:
            t = _first_target(targets)
            player = t.id if (t and t.is_player) else None
        if not player:
            return []
        return [Event(
            type=EventType.DRAW,
            payload={'player': player, 'amount': amount},
        )]

    return _resolve


def resolve_life_change(amount: int, to_caster: bool = True) -> ResolveFn:
    """Change life total by ``amount`` (positive = gain, negative = lose).

    If ``to_caster=True`` (default), the controller of the spell is the
    target. Otherwise, every chosen player target receives the change.
    """
    def _resolve(targets: list[list[Target]], state: GameState) -> list[Event]:
        events: list[Event] = []
        if to_caster:
            player = _caster_id_from_state_and_targets(state, targets)
            if not player:
                return []
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': player, 'amount': amount},
            ))
            return events

        for t in _flatten_targets(targets):
            if not t.is_player:
                continue
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': t.id, 'amount': amount},
            ))
        return events

    return _resolve


def resolve_create_token(
    name: str,
    power: Optional[int],
    toughness: Optional[int],
    types: Sequence,
    subtypes: Sequence[str],
    colors: Optional[Sequence] = None,
    count: int = 1,
) -> ResolveFn:
    """Create ``count`` tokens with the given characteristics.

    ``types`` is a sequence of ``CardType`` (or strings the OBJECT_CREATED
    handler can coerce). ``subtypes`` is a sequence of strings.
    """
    types_list = list(types)
    subtypes_list = list(subtypes)
    colors_list = list(colors) if colors else []

    def _resolve(targets: list[list[Target]], state: GameState) -> list[Event]:
        caster = _caster_id_from_state_and_targets(state, targets)
        if caster is None:
            return []

        events: list[Event] = []
        for _ in range(max(count, 0)):
            payload: dict = {
                'name': name,
                'controller': caster,
                'types': list(types_list),
                'subtypes': list(subtypes_list),
                'colors': list(colors_list),
                'is_token': True,
            }
            if power is not None:
                payload['power'] = power
            if toughness is not None:
                payload['toughness'] = toughness
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload=payload,
                controller=caster,
            ))
        return events

    return _resolve


def resolve_pump(
    power_mod: int,
    toughness_mod: int,
    duration: str = 'end_of_turn',
) -> ResolveFn:
    """Apply a temporary +N/+M (or -N/-M) to each chosen target."""
    def _resolve(targets: list[list[Target]], state: GameState) -> list[Event]:
        events: list[Event] = []
        for t in _flatten_targets(targets):
            if t.is_player:
                continue
            events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': t.id,
                    'power_mod': power_mod,
                    'toughness_mod': toughness_mod,
                    'duration': duration,
                },
            ))
        return events

    return _resolve


def resolve_counter(
    amount: int = 1,
    counter_type: str = '+1/+1',
) -> ResolveFn:
    """Put ``amount`` counters of ``counter_type`` on each chosen target."""
    def _resolve(targets: list[list[Target]], state: GameState) -> list[Event]:
        events: list[Event] = []
        for t in _flatten_targets(targets):
            if t.is_player:
                continue
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    'object_id': t.id,
                    'counter_type': counter_type,
                    'amount': amount,
                },
            ))
        return events

    return _resolve


def resolve_modal(options: list[ResolveFn]) -> ResolveFn:
    """Compose a "choose one" modal spell.

    The chosen mode is read from the resolving spell's
    ``card_def.chosen_mode`` attribute (set by the caller before
    resolution) or from ``state.pending_choice.callback_data['mode']`` if
    a pending modal choice is being resolved. If no mode is set, the first
    option runs as a sensible default (e.g. AI didn't pick a mode yet).
    Out-of-range indices fall back to the first option.
    """
    options_list = list(options)

    def _resolve(targets: list[list[Target]], state: GameState) -> list[Event]:
        if not options_list:
            return []
        index = 0
        # Prefer an explicit mode set on the topmost stack object's GameObject.
        stack_zone = state.zones.get('stack') if state and state.zones else None
        if stack_zone is not None:
            for obj_id in reversed(list(stack_zone.objects or [])):
                obj = state.objects.get(obj_id)
                if obj is None:
                    continue
                # Card scripts may attach `chosen_mode` directly on the
                # GameObject before pushing the spell to the stack.
                mode = getattr(obj, 'chosen_mode', None)
                if mode is None and obj.card_def is not None:
                    mode = getattr(obj.card_def, 'chosen_mode', None)
                if mode is not None:
                    try:
                        index = int(mode)
                    except (TypeError, ValueError):
                        index = 0
                    break
        # Pending modal choice: callback_data may contain 'mode'.
        if index == 0:
            choice = getattr(state, 'pending_choice', None)
            if choice is not None and getattr(choice, 'callback_data', None):
                mode = choice.callback_data.get('mode')
                if mode is not None:
                    try:
                        index = int(mode)
                    except (TypeError, ValueError):
                        index = 0
        if index < 0 or index >= len(options_list):
            index = 0
        return options_list[index](targets, state) or []

    return _resolve


def resolve_chain(*resolvers: ResolveFn) -> ResolveFn:
    """Compose multiple resolve callables into a single one.

    The composed function calls each resolver in order with the same
    ``targets`` and ``state`` and concatenates their event lists. Use this
    for "do A and do B" / "do A. Then do B." spell texts.
    """
    fns = list(resolvers)

    def _resolve(targets: list[list[Target]], state: GameState) -> list[Event]:
        events: list[Event] = []
        for fn in fns:
            try:
                more = fn(targets, state) or []
            except Exception:
                more = []
            events.extend(more)
        return events

    return _resolve


__all__ = [
    'ResolveFn',
    'resolve_damage',
    'resolve_destroy',
    'resolve_exile',
    'resolve_draw',
    'resolve_life_change',
    'resolve_create_token',
    'resolve_pump',
    'resolve_counter',
    'resolve_modal',
    'resolve_chain',
]
