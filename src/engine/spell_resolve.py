"""
Spell Resolve Factories
=======================

Reusable factory functions for the `resolve=` parameter on
`make_instant` / `make_sorcery` calls. These cover the common
"vanilla spell" patterns the auto-pattern matcher in stack.py
doesn't handle yet (multi-effect chains, modal one-of, +N/+N pumps,
-N/-N counters, opponent draws/loses life, etc.).

A resolve callback has the signature:

    def resolve(targets: list[list[Target]] | list, state: GameState) -> list[Event]:
        ...

Targets are passed as `chosen_targets` from the stack item. Most factories
in this module don't actually use `targets` (they post a PendingChoice via
the helpers in `interceptor_helpers`). The factories return events directly
when the effect is non-targeted, or open a PendingChoice and return [] when
they need a choice.

Usage example:

    from src.engine.spell_resolve import resolve_chain, resolve_pump_target

    SOME_PUMP_AND_DRAW = make_instant(
        name="Some Pump and Draw",
        ...,
        resolve=resolve_chain(
            resolve_pump_target(power=2, toughness=2),
            resolve_draw(count=1),
        ),
    )
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from .types import (
    Event,
    EventType,
    GameObject,
    GameState,
    ZoneType,
)

ResolveFn = Callable[[list, GameState], list[Event]]


# =============================================================================
# Internal helpers
# =============================================================================

def _find_spell_on_stack(state: GameState, spell_name: str) -> tuple[Optional[str], Optional[str]]:
    """Locate (spell_id, caster_id) for a spell of the given name on the stack.

    Falls back to a synthetic spell_id and the active player when the spell
    can't be located (e.g. tests that bypass the stack).
    """
    stack_zone = state.zones.get('stack')
    spell_id: Optional[str] = None
    caster_id: Optional[str] = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == spell_name:
                spell_id = obj.id
                caster_id = obj.controller
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = f"{spell_name.lower().replace(' ', '_')}_spell"
    return spell_id, caster_id


def _all_creatures(state: GameState) -> list[str]:
    from .types import CardType
    return [
        oid for oid, obj in state.objects.items()
        if obj.zone == ZoneType.BATTLEFIELD
        and CardType.CREATURE in obj.characteristics.types
    ]


def _all_creatures_controlled_by(state: GameState, controller_id: str) -> list[str]:
    from .types import CardType
    return [
        oid for oid, obj in state.objects.items()
        if obj.zone == ZoneType.BATTLEFIELD
        and CardType.CREATURE in obj.characteristics.types
        and obj.controller == controller_id
    ]


def _opponents_of(state: GameState, player_id: str) -> list[str]:
    return [pid for pid in state.players if pid != player_id]


# =============================================================================
# Composition: chain multiple resolves together
# =============================================================================

def resolve_chain(*resolves: ResolveFn) -> ResolveFn:
    """Compose multiple resolve callbacks. Events are concatenated in order.

    Note: each resolve in the chain is called independently and their event
    lists merged. If an earlier resolve opens a PendingChoice, later
    resolves still run — author intent is "these all happen at resolution
    time", not "these are sequenced asynchronously". For most vanilla
    spells with a small chain (e.g. pump + draw, gain life + investigate),
    that's the correct behaviour.
    """
    def fn(targets, state: GameState) -> list[Event]:
        out: list[Event] = []
        for r in resolves:
            try:
                evts = r(targets, state) or []
            except Exception:
                evts = []
            if evts:
                out.extend(evts)
        return out
    return fn


# =============================================================================
# Modal: "Choose one" / "Choose one or both" / "Choose two —"
# =============================================================================

def resolve_modal(
    spell_name: str,
    modes: list[tuple[str, ResolveFn]],
    *,
    min_modes: int = 1,
    max_modes: int = 1,
    prompt: Optional[str] = None,
) -> ResolveFn:
    """Open a modal choice; on selection, run the chosen mode(s).

    `modes` is a list of (mode_text, resolve_fn) pairs.
    """
    from src.cards.interceptor_helpers import create_modal_choice

    def fn(targets, state: GameState) -> list[Event]:
        spell_id, caster_id = _find_spell_on_stack(state, spell_name)
        mode_dicts = [{"index": i, "text": text} for i, (text, _r) in enumerate(modes)]

        choice = create_modal_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            modes=mode_dicts,
            min_modes=min_modes,
            max_modes=max_modes,
            prompt=prompt or f"{spell_name} — Choose:",
        )
        choice.choice_type = "modal_with_callback"

        def handle(choice, selected, gs: GameState) -> list[Event]:
            events: list[Event] = []
            for sel in (selected or []):
                idx = sel["index"] if isinstance(sel, dict) else sel
                if not (0 <= idx < len(modes)):
                    continue
                _text, mode_resolve = modes[idx]
                try:
                    evts = mode_resolve(targets, gs) or []
                except Exception:
                    evts = []
                events.extend(evts)
            return events

        choice.callback_data['handler'] = handle
        return []

    return fn


# =============================================================================
# Targeted-creature effects (post a target choice)
# =============================================================================

def resolve_pump_target(
    power: int,
    toughness: int,
    *,
    until: str = "end_of_turn",
    legal_filter: Optional[Callable[[GameObject, GameState, str], bool]] = None,
    spell_name: Optional[str] = None,
    prompt: Optional[str] = None,
) -> ResolveFn:
    """+power/+toughness to a single target creature until end of turn.

    `legal_filter(obj, state, controller_id) -> bool` narrows targets
    (e.g. "creature you control"). When None, any creature is legal.
    """
    from src.cards.interceptor_helpers import create_target_choice
    from .types import CardType

    def fn(targets, state: GameState) -> list[Event]:
        spell_id, caster_id = _find_spell_on_stack(state, spell_name or "Spell")
        legal: list[str] = []
        for oid, obj in state.objects.items():
            if obj.zone != ZoneType.BATTLEFIELD:
                continue
            if CardType.CREATURE not in obj.characteristics.types:
                continue
            if legal_filter is not None and not legal_filter(obj, state, caster_id):
                continue
            legal.append(oid)
        if not legal:
            return []

        choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            legal_targets=legal,
            prompt=prompt or f"Choose a creature to get +{power}/+{toughness}",
        )
        choice.choice_type = "target_with_callback"

        def handler(choice, selected, gs: GameState) -> list[Event]:
            if not selected:
                return []
            tid = selected[0]
            t = gs.objects.get(tid)
            if not t or t.zone != ZoneType.BATTLEFIELD:
                return []
            return [Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': tid,
                    'power_mod': power,
                    'toughness_mod': toughness,
                    'duration': until,
                },
                source=choice.source_id,
            )]

        choice.callback_data['handler'] = handler
        return []

    return fn


def resolve_minus_counters_target(
    amount: int,
    *,
    spell_name: Optional[str] = None,
    prompt: Optional[str] = None,
) -> ResolveFn:
    """Put N -1/-1 counters on a target creature."""
    from src.cards.interceptor_helpers import create_target_choice
    from .types import CardType

    def fn(targets, state: GameState) -> list[Event]:
        spell_id, caster_id = _find_spell_on_stack(state, spell_name or "Spell")
        legal = _all_creatures(state)
        if not legal:
            return []

        choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            legal_targets=legal,
            prompt=prompt or f"Choose a creature to put {amount} -1/-1 counters on",
        )
        choice.choice_type = "target_with_callback"

        def handler(choice, selected, gs: GameState) -> list[Event]:
            if not selected:
                return []
            tid = selected[0]
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': tid, 'counter_type': '-1/-1', 'amount': amount},
                source=choice.source_id,
            )]

        choice.callback_data['handler'] = handler
        return []

    return fn


def resolve_destroy_filtered(
    *,
    creature_ok: bool = True,
    artifact_ok: bool = False,
    enchantment_ok: bool = False,
    creature_predicate: Optional[Callable[[GameObject, GameState], bool]] = None,
    spell_name: Optional[str] = None,
    prompt: Optional[str] = None,
) -> ResolveFn:
    """Destroy a single target permanent matching a filter."""
    from src.cards.interceptor_helpers import create_target_choice
    from .types import CardType

    def fn(targets, state: GameState) -> list[Event]:
        spell_id, caster_id = _find_spell_on_stack(state, spell_name or "Spell")
        legal: list[str] = []
        for oid, obj in state.objects.items():
            if obj.zone != ZoneType.BATTLEFIELD:
                continue
            t = obj.characteristics.types
            if creature_ok and CardType.CREATURE in t:
                if creature_predicate is None or creature_predicate(obj, state):
                    legal.append(oid)
                    continue
            if artifact_ok and CardType.ARTIFACT in t:
                legal.append(oid)
                continue
            if enchantment_ok and CardType.ENCHANTMENT in t:
                legal.append(oid)
                continue
        if not legal:
            return []

        choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            legal_targets=legal,
            prompt=prompt or "Choose a permanent to destroy",
        )
        choice.choice_type = "target_with_callback"

        def handler(choice, selected, gs: GameState) -> list[Event]:
            if not selected:
                return []
            tid = selected[0]
            obj = gs.objects.get(tid)
            if not obj or obj.zone != ZoneType.BATTLEFIELD:
                return []
            return [Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': tid},
                source=choice.source_id,
            )]

        choice.callback_data['handler'] = handler
        return []

    return fn


def resolve_bounce_target(
    *,
    nonland: bool = False,
    spell_name: Optional[str] = None,
    prompt: Optional[str] = None,
    min_targets: int = 1,
    max_targets: int = 1,
) -> ResolveFn:
    """Return target nonland permanent (or up to N) to its owner's hand."""
    from src.cards.interceptor_helpers import create_target_choice
    from .types import CardType

    def fn(targets, state: GameState) -> list[Event]:
        spell_id, caster_id = _find_spell_on_stack(state, spell_name or "Spell")
        legal: list[str] = []
        for oid, obj in state.objects.items():
            if obj.zone != ZoneType.BATTLEFIELD:
                continue
            if nonland and CardType.LAND in obj.characteristics.types:
                continue
            legal.append(oid)
        if not legal:
            return []

        choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            legal_targets=legal,
            prompt=prompt or "Choose target permanent to return to hand",
            min_targets=min(min_targets, len(legal)),
            max_targets=min(max_targets, len(legal)),
        )
        choice.choice_type = "target_with_callback"

        def handler(choice, selected, gs: GameState) -> list[Event]:
            evts: list[Event] = []
            for tid in (selected or []):
                obj = gs.objects.get(tid)
                if not obj or obj.zone != ZoneType.BATTLEFIELD:
                    continue
                evts.append(Event(
                    type=EventType.ZONE_CHANGE,
                    payload={
                        'object_id': tid,
                        'from_zone_type': ZoneType.BATTLEFIELD,
                        'to_zone_type': ZoneType.HAND,
                        'to_zone': f'hand_{obj.owner}',
                        'reason': 'bounced',
                    },
                    source=choice.source_id,
                ))
            return evts

        choice.callback_data['handler'] = handler
        return []

    return fn


# =============================================================================
# Untargeted effects on caster
# =============================================================================

def resolve_draw(count: int = 1) -> ResolveFn:
    """Caster draws N cards."""
    def fn(targets, state: GameState) -> list[Event]:
        # Determine controller. Prefer the spell on the stack; fallback to
        # active player.
        controller = state.active_player
        stack_zone = state.zones.get('stack')
        if stack_zone:
            for oid in stack_zone.objects:
                obj = state.objects.get(oid)
                if obj is not None:
                    controller = obj.controller
                    break
        return [Event(
            type=EventType.DRAW,
            payload={'count': count, 'player': controller},
            source=None,
            controller=controller,
        )]
    return fn


def resolve_gain_life(amount: int) -> ResolveFn:
    """Caster gains N life."""
    def fn(targets, state: GameState) -> list[Event]:
        controller = state.active_player
        stack_zone = state.zones.get('stack')
        if stack_zone:
            for oid in stack_zone.objects:
                obj = state.objects.get(oid)
                if obj is not None:
                    controller = obj.controller
                    break
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': controller, 'amount': amount},
            source=None,
            controller=controller,
        )]
    return fn


def resolve_each_opponent_loses_life(amount: int) -> ResolveFn:
    """Each opponent loses N life."""
    def fn(targets, state: GameState) -> list[Event]:
        controller = state.active_player
        stack_zone = state.zones.get('stack')
        if stack_zone:
            for oid in stack_zone.objects:
                obj = state.objects.get(oid)
                if obj is not None:
                    controller = obj.controller
                    break
        events = []
        for opp in _opponents_of(state, controller):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp, 'amount': -amount},
                source=None,
                controller=controller,
            ))
        return events
    return fn


def resolve_create_token(
    *,
    name: str,
    power: Optional[int] = None,
    toughness: Optional[int] = None,
    types: Iterable = (),
    subtypes: Iterable = (),
    colors: Iterable = (),
    keywords: Iterable = (),
    count: int = 1,
) -> ResolveFn:
    """Create N tokens with the given characteristics."""
    types_l = list(types)
    subtypes_l = list(subtypes)
    colors_l = list(colors)
    keywords_l = list(keywords)

    def fn(targets, state: GameState) -> list[Event]:
        controller = state.active_player
        stack_zone = state.zones.get('stack')
        if stack_zone:
            for oid in stack_zone.objects:
                obj = state.objects.get(oid)
                if obj is not None:
                    controller = obj.controller
                    break
        events = []
        for _ in range(count):
            payload = {
                'name': name,
                'controller': controller,
                'types': types_l,
                'subtypes': subtypes_l,
                'colors': colors_l,
                'keywords': keywords_l,
            }
            if power is not None:
                payload['power'] = power
            if toughness is not None:
                payload['toughness'] = toughness
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload=payload,
                source=None,
                controller=controller,
            ))
        return events
    return fn


def resolve_minus_counters_each_creature(amount: int) -> ResolveFn:
    """Put N -1/-1 counters on each creature on the battlefield."""
    def fn(targets, state: GameState) -> list[Event]:
        events = []
        for cid in _all_creatures(state):
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': cid, 'counter_type': '-1/-1', 'amount': amount},
                source=None,
            ))
        return events
    return fn


# =============================================================================
# Library / mill / search
# =============================================================================

def resolve_mill_self(count: int) -> ResolveFn:
    """Caster mills N cards."""
    def fn(targets, state: GameState) -> list[Event]:
        controller = state.active_player
        stack_zone = state.zones.get('stack')
        if stack_zone:
            for oid in stack_zone.objects:
                obj = state.objects.get(oid)
                if obj is not None:
                    controller = obj.controller
                    break
        return [Event(
            type=EventType.MILL,
            payload={'player': controller, 'amount': count},
            source=None,
            controller=controller,
        )]
    return fn


def resolve_search_basic_land_to_battlefield_tapped(
    *,
    spell_name: Optional[str] = None,
    prompt: Optional[str] = None,
) -> ResolveFn:
    """Search library for a basic land, put it onto the battlefield tapped, then shuffle."""
    from .library_search import (
        create_library_search_choice,
        is_basic_land,
    )

    def fn(targets, state: GameState) -> list[Event]:
        spell_id, caster_id = _find_spell_on_stack(state, spell_name or "Spell")
        create_library_search_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            filter_fn=is_basic_land(),
            min_count=0,
            max_count=1,
            destination='battlefield_tapped',
            shuffle_after=True,
            prompt=prompt or "Search for a basic land",
            optional=True,
        )
        return []

    return fn


# =============================================================================
# Bounce / hand manipulation
# =============================================================================

def resolve_destroy_each_creature_modify(amount: int) -> ResolveFn:
    """All creatures get -X/-X — alias to put -X/-X counters on each creature.

    Naming is intentional: when this is paired with a -X/-X counter delta,
    common phrasing is "put N -1/-1 counters on each creature" which we
    handle via `resolve_minus_counters_each_creature`. This helper exists
    for the symmetrical case of a stat-line shrink everywhere.
    """
    return resolve_minus_counters_each_creature(amount)


__all__ = [
    "ResolveFn",
    "resolve_chain",
    "resolve_modal",
    "resolve_pump_target",
    "resolve_minus_counters_target",
    "resolve_minus_counters_each_creature",
    "resolve_destroy_filtered",
    "resolve_bounce_target",
    "resolve_draw",
    "resolve_gain_life",
    "resolve_each_opponent_loses_life",
    "resolve_create_token",
    "resolve_mill_self",
    "resolve_search_basic_land_to_battlefield_tapped",
]
