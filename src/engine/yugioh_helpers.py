"""
Yu-Gi-Oh! Effect Helper Factories

Reusable helpers for creating card effects, following the interceptor_helpers.py pattern.
"""

from .types import (
    GameState, GameObject, Event, EventType, ZoneType, CardType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    new_id
)


# =============================================================================
# Trigger Helpers
# =============================================================================

def make_ygo_summon_trigger(obj: GameObject, effect_fn):
    """Create a trigger that fires when this monster is summoned."""
    def _filter(event: Event, state: GameState) -> bool:
        return (event.type in (EventType.YGO_NORMAL_SUMMON, EventType.YGO_SPECIAL_SUMMON,
                               EventType.YGO_FLIP_SUMMON, EventType.YGO_TRIBUTE_SUMMON) and
                event.payload.get('card_id') == obj.id)

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        events = effect_fn(obj, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events or [])

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=_filter, handler=_handler,
        duration='until_leaves',
    )


def make_ygo_destroy_trigger(obj: GameObject, effect_fn):
    """Create a trigger that fires when this card is destroyed."""
    def _filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.YGO_DESTROY and
                event.payload.get('card_id') == obj.id)

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        events = effect_fn(obj, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events or [])

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=_filter, handler=_handler,
        duration='forever', uses_remaining=1,
    )


def make_ygo_flip_trigger(obj: GameObject, effect_fn):
    """Create a FLIP: effect trigger."""
    def _filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.YGO_FLIP and
                event.payload.get('card_id') == obj.id)

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        events = effect_fn(obj, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events or [])

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=_filter, handler=_handler,
        duration='until_leaves',
    )


def make_ygo_ignition_effect(obj: GameObject, effect_fn):
    """Create an Ignition Effect (SS1, activated during Main Phase)."""
    def _filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.ACTIVATE and
                event.payload.get('card_id') == obj.id)

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        events = effect_fn(obj, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events or [])

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=_filter, handler=_handler,
        duration='until_leaves',
    )


def make_ygo_quick_effect(obj: GameObject, effect_fn):
    """Create a Quick Effect (SS2, can be activated during either turn)."""
    return make_ygo_ignition_effect(obj, effect_fn)  # Same structure, SS differs in chain


def make_ygo_continuous_effect(obj: GameObject, modifier_fn):
    """Create a continuous effect that modifies game state while on the field."""
    def _filter(event: Event, state: GameState) -> bool:
        # Apply to relevant query events
        return event.type in (EventType.QUERY_POWER, EventType.QUERY_TOUGHNESS,
                              EventType.QUERY_ABILITIES)

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        # Check if this monster is still on the field
        source = state.objects.get(obj.id)
        if not source or source.zone != ZoneType.MONSTER_ZONE:
            return InterceptorResult(action=InterceptorAction.PASS)
        return modifier_fn(event, state)

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.QUERY, filter=_filter, handler=_handler,
        duration='until_leaves',
    )


def make_ygo_equip_boost(obj: GameObject, atk_boost: int = 0, def_boost: int = 0):
    """Create an equip effect that boosts ATK/DEF of the equipped monster."""
    def _filter(event: Event, state: GameState) -> bool:
        target_id = getattr(obj.state, 'equipped_to', None)
        if not target_id:
            return False
        return (event.type in (EventType.QUERY_POWER, EventType.QUERY_TOUGHNESS) and
                event.payload.get('object_id') == target_id)

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        if event.type == EventType.QUERY_POWER and atk_boost:
            event.payload['value'] = event.payload.get('value', 0) + atk_boost
        elif event.type == EventType.QUERY_TOUGHNESS and def_boost:
            event.payload['value'] = event.payload.get('value', 0) + def_boost
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.QUERY, filter=_filter, handler=_handler,
        duration='until_leaves',
    )


# =============================================================================
# Common Effect Implementations
# =============================================================================

def destroy_all_monsters(state: GameState) -> list[Event]:
    """Destroy all monsters on the field (Dark Hole effect)."""
    events = []
    for pid in state.players:
        zone_key = f"monster_zone_{pid}"
        zone = state.zones.get(zone_key)
        if not zone:
            continue
        for i, obj_id in enumerate(zone.objects):
            if obj_id is None:
                continue
            obj = state.objects.get(obj_id)
            if obj:
                # Send to GY
                zone.objects[i] = None
                gy = state.zones.get(f"graveyard_{obj.owner}")
                if gy:
                    gy.objects.append(obj_id)
                obj.zone = ZoneType.GRAVEYARD
                obj.state.face_down = False
                obj.state.ygo_position = None
                events.append(Event(
                    type=EventType.YGO_DESTROY,
                    payload={'card_id': obj_id, 'card_name': obj.name}
                ))
        # Clean up None entries
        while None in zone.objects:
            zone.objects.remove(None)
    return events


def destroy_attacking_monsters(state: GameState, controller_id: str) -> list[Event]:
    """Destroy all attack-position monsters the opponent controls (Mirror Force)."""
    events = []
    for pid in state.players:
        if pid == controller_id:
            continue
        zone_key = f"monster_zone_{pid}"
        zone = state.zones.get(zone_key)
        if not zone:
            continue
        for i, obj_id in enumerate(zone.objects):
            if obj_id is None:
                continue
            obj = state.objects.get(obj_id)
            if obj and getattr(obj.state, 'ygo_position', None) == 'face_up_atk':
                zone.objects[i] = None
                gy = state.zones.get(f"graveyard_{obj.owner}")
                if gy:
                    gy.objects.append(obj_id)
                obj.zone = ZoneType.GRAVEYARD
                obj.state.face_down = False
                obj.state.ygo_position = None
                events.append(Event(
                    type=EventType.YGO_DESTROY,
                    payload={'card_id': obj_id, 'card_name': obj.name}
                ))
        while None in zone.objects:
            zone.objects.remove(None)
    return events


def revive_from_graveyard(state: GameState, player_id: str, card_id: str) -> list[Event]:
    """Special Summon a monster from the GY (Monster Reborn effect)."""
    events = []
    obj = state.objects.get(card_id)
    if not obj:
        return events

    # Remove from GY
    gy_key = f"graveyard_{obj.owner}"
    gy = state.zones.get(gy_key)
    if gy and card_id in gy.objects:
        gy.objects.remove(card_id)

    # Find empty monster slot
    zone_key = f"monster_zone_{player_id}"
    zone = state.zones.get(zone_key)
    if not zone:
        return events
    slot = None
    for i in range(5):
        if i >= len(zone.objects) or zone.objects[i] is None:
            slot = i
            break
    if slot is None and len(zone.objects) < 5:
        slot = len(zone.objects)
    if slot is None:
        return events

    while len(zone.objects) <= slot:
        zone.objects.append(None)
    zone.objects[slot] = card_id
    obj.zone = ZoneType.MONSTER_ZONE
    obj.controller = player_id
    obj.state.ygo_position = 'face_up_atk'
    obj.state.face_down = False

    events.append(Event(
        type=EventType.YGO_SPECIAL_SUMMON,
        payload={'player': player_id, 'card_id': card_id, 'card_name': obj.name,
                 'summon_type': 'revive'}
    ))
    return events


def destroy_spell_trap(state: GameState, card_id: str) -> list[Event]:
    """Destroy a Spell/Trap card (MST effect)."""
    events = []
    obj = state.objects.get(card_id)
    if not obj:
        return events

    for zone in state.zones.values():
        if card_id in zone.objects:
            for i, oid in enumerate(zone.objects):
                if oid == card_id:
                    zone.objects[i] = None
                    break
            while card_id in zone.objects:
                zone.objects.remove(card_id)
            break

    gy = state.zones.get(f"graveyard_{obj.owner}")
    if gy:
        gy.objects.append(card_id)
    obj.zone = ZoneType.GRAVEYARD
    obj.state.face_down = False

    events.append(Event(
        type=EventType.YGO_DESTROY,
        payload={'card_id': card_id, 'card_name': obj.name}
    ))
    return events
