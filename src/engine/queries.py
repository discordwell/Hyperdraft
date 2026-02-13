"""
Hyperdraft Query System

Continuous effects don't modify state directly.
Instead, they register QUERY interceptors that modify how state is READ.

When you ask "what's this creature's power?", the query runs through
all relevant interceptors to compute the final value.
"""

from .types import (
    GameState, GameObject, Interceptor, InterceptorPriority,
    CardType, Color
)


def get_power(obj: GameObject, state: GameState) -> int:
    """Get computed power of a creature, applying all continuous effects."""
    if obj.characteristics.power is None:
        return 0

    power = obj.characteristics.power

    # Get all QUERY interceptors that affect power, sorted by timestamp
    interceptors = sorted(
        [i for i in state.interceptors.values()
         if i.priority == InterceptorPriority.QUERY
         and _is_power_query(i, obj, state)],
        key=lambda i: i.timestamp
    )

    # Apply each interceptor in order
    for interceptor in interceptors:
        result = interceptor.handler(
            _make_query_event('power', obj, power),
            state
        )
        if result.transformed_event:
            power = result.transformed_event.payload.get('value', power)

    # Apply temporary PT modifiers (from PT_MODIFICATION events)
    if hasattr(obj.state, 'pt_modifiers'):
        for mod in obj.state.pt_modifiers:
            power += mod.get('power', 0)

    # Apply counters last (always after other modifications)
    power += obj.state.counters.get('+1/+1', 0)
    power -= obj.state.counters.get('-1/-1', 0)

    return power


def get_toughness(obj: GameObject, state: GameState) -> int:
    """Get computed toughness of a creature, applying all continuous effects."""
    if obj.characteristics.toughness is None:
        return 0

    toughness = obj.characteristics.toughness

    # Get all QUERY interceptors that affect toughness
    interceptors = sorted(
        [i for i in state.interceptors.values()
         if i.priority == InterceptorPriority.QUERY
         and _is_toughness_query(i, obj, state)],
        key=lambda i: i.timestamp
    )

    for interceptor in interceptors:
        result = interceptor.handler(
            _make_query_event('toughness', obj, toughness),
            state
        )
        if result.transformed_event:
            toughness = result.transformed_event.payload.get('value', toughness)

    # Apply temporary PT modifiers (from PT_MODIFICATION events)
    if hasattr(obj.state, 'pt_modifiers'):
        for mod in obj.state.pt_modifiers:
            toughness += mod.get('toughness', 0)

    # Apply counters
    toughness += obj.state.counters.get('+1/+1', 0)
    toughness -= obj.state.counters.get('-1/-1', 0)

    return toughness


def get_types(obj: GameObject, state: GameState) -> set[CardType]:
    """Get computed types of an object."""
    types = set(obj.characteristics.types)

    interceptors = sorted(
        [i for i in state.interceptors.values()
         if i.priority == InterceptorPriority.QUERY
         and _is_types_query(i, obj, state)],
        key=lambda i: i.timestamp
    )

    for interceptor in interceptors:
        result = interceptor.handler(
            _make_query_event('types', obj, types),
            state
        )
        if result.transformed_event:
            types = result.transformed_event.payload.get('value', types)

    return types


def get_colors(obj: GameObject, state: GameState) -> set[Color]:
    """Get computed colors of an object."""
    colors = set(obj.characteristics.colors)

    interceptors = sorted(
        [i for i in state.interceptors.values()
         if i.priority == InterceptorPriority.QUERY
         and _is_colors_query(i, obj, state)],
        key=lambda i: i.timestamp
    )

    for interceptor in interceptors:
        result = interceptor.handler(
            _make_query_event('colors', obj, colors),
            state
        )
        if result.transformed_event:
            colors = result.transformed_event.payload.get('value', colors)

    return colors


def has_ability(obj: GameObject, ability_name: str, state: GameState) -> bool:
    """Check if object has a specific ability (keyword or other)."""
    # Check base abilities
    for ability in obj.characteristics.abilities:
        if ability.get('name') == ability_name or ability.get('keyword') == ability_name:
            return True

    # Check Hearthstone state flags (keywords can be set directly on state)
    hs_state_keywords = {
        'divine_shield': obj.state.divine_shield,
        'stealth': obj.state.stealth,
        'windfury': obj.state.windfury,
    }
    if hs_state_keywords.get(ability_name, False):
        return True

    # Check granted abilities via QUERY interceptors
    interceptors = [
        i for i in state.interceptors.values()
        if i.priority == InterceptorPriority.QUERY
        and _is_abilities_query(i, obj, state)
    ]

    for interceptor in interceptors:
        result = interceptor.handler(
            _make_query_event('abilities', obj, []),
            state
        )
        if result.transformed_event:
            granted = result.transformed_event.payload.get('granted', [])
            if ability_name in granted:
                return True

    return False


def is_creature(obj: GameObject, state: GameState) -> bool:
    """Check if object is currently a creature (or minion in Hearthstone)."""
    types = get_types(obj, state)
    return CardType.CREATURE in types or CardType.MINION in types


# =============================================================================
# Helper functions
# =============================================================================

def _make_query_event(query_type: str, obj: GameObject, current_value) -> 'Event':
    """Create a pseudo-event for query interceptors."""
    from .types import Event, EventType

    type_map = {
        'power': EventType.QUERY_POWER,
        'toughness': EventType.QUERY_TOUGHNESS,
        'types': EventType.QUERY_TYPES,
        'colors': EventType.QUERY_COLORS,
        'abilities': EventType.QUERY_ABILITIES,
    }

    return Event(
        type=type_map.get(query_type, EventType.QUERY_POWER),
        payload={
            'object_id': obj.id,
            'value': current_value,
        }
    )


def _is_power_query(interceptor: Interceptor, obj: GameObject, state: GameState) -> bool:
    """Check if interceptor is a power query for this object."""
    from .types import Event, EventType
    test_event = Event(type=EventType.QUERY_POWER, payload={'object_id': obj.id})
    try:
        return interceptor.filter(test_event, state)
    except:
        return False


def _is_toughness_query(interceptor: Interceptor, obj: GameObject, state: GameState) -> bool:
    """Check if interceptor is a toughness query for this object."""
    from .types import Event, EventType
    test_event = Event(type=EventType.QUERY_TOUGHNESS, payload={'object_id': obj.id})
    try:
        return interceptor.filter(test_event, state)
    except:
        return False


def _is_types_query(interceptor: Interceptor, obj: GameObject, state: GameState) -> bool:
    """Check if interceptor is a types query for this object."""
    from .types import Event, EventType
    test_event = Event(type=EventType.QUERY_TYPES, payload={'object_id': obj.id})
    try:
        return interceptor.filter(test_event, state)
    except:
        return False


def _is_colors_query(interceptor: Interceptor, obj: GameObject, state: GameState) -> bool:
    """Check if interceptor is a colors query for this object."""
    from .types import Event, EventType
    test_event = Event(type=EventType.QUERY_COLORS, payload={'object_id': obj.id})
    try:
        return interceptor.filter(test_event, state)
    except:
        return False


def _is_abilities_query(interceptor: Interceptor, obj: GameObject, state: GameState) -> bool:
    """Check if interceptor is an abilities query for this object."""
    from .types import Event, EventType
    test_event = Event(type=EventType.QUERY_ABILITIES, payload={'object_id': obj.id})
    try:
        return interceptor.filter(test_event, state)
    except:
        return False
