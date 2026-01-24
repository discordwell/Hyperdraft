"""
Hyperdraft Engine

Everything is an Event. Everything else is an Interceptor.
"""

from .types import (
    # IDs
    new_id,

    # Events
    Event, EventType, EventStatus,

    # Interceptors
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    InterceptorHandler, EventFilter,

    # Game objects
    GameObject, Characteristics, ObjectState,
    CardType, Color, ZoneType,

    # Other
    Player, Zone, GameState, CardDefinition,
)

from .pipeline import EventPipeline

from .queries import (
    get_power, get_toughness, get_types, get_colors,
    has_ability, is_creature
)

from .game import (
    Game,
    make_creature, make_instant, make_enchantment
)

__all__ = [
    # IDs
    'new_id',

    # Events
    'Event', 'EventType', 'EventStatus',

    # Interceptors
    'Interceptor', 'InterceptorPriority', 'InterceptorAction', 'InterceptorResult',
    'InterceptorHandler', 'EventFilter',

    # Game objects
    'GameObject', 'Characteristics', 'ObjectState',
    'CardType', 'Color', 'ZoneType',

    # Other
    'Player', 'Zone', 'GameState', 'CardDefinition',

    # Pipeline
    'EventPipeline',

    # Queries
    'get_power', 'get_toughness', 'get_types', 'get_colors',
    'has_ability', 'is_creature',

    # Game
    'Game', 'make_creature', 'make_instant', 'make_enchantment',
]
