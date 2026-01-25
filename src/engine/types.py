"""
Hyperdraft Core Types

Everything is an Event. Everything else is an Interceptor.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional
from uuid import uuid4


# =============================================================================
# IDs
# =============================================================================

def new_id() -> str:
    return str(uuid4())[:8]


# =============================================================================
# Event Types
# =============================================================================

class EventType(Enum):
    # Object lifecycle
    OBJECT_CREATED = auto()
    OBJECT_DESTROYED = auto()
    ZONE_CHANGE = auto()

    # State changes
    TAP = auto()
    UNTAP = auto()
    COUNTER_ADDED = auto()
    COUNTER_REMOVED = auto()

    # Combat
    ATTACK_DECLARED = auto()
    BLOCK_DECLARED = auto()
    DAMAGE = auto()

    # Resources
    MANA_PRODUCED = auto()
    MANA_SPENT = auto()
    LIFE_CHANGE = auto()

    # Card actions
    DRAW = auto()
    DISCARD = auto()
    CAST = auto()
    SPELL_CAST = auto()  # Alias for card files using this name
    ACTIVATE = auto()

    # Turn structure
    PHASE_START = auto()
    PHASE_END = auto()
    TURN_START = auto()
    TURN_END = auto()
    PRIORITY_PASS = auto()

    # Meta
    GAME_START = auto()
    GAME_END = auto()
    PLAYER_LOSES = auto()
    PLAYER_WINS = auto()

    # Query events (for continuous effects)
    QUERY_POWER = auto()
    QUERY_TOUGHNESS = auto()
    QUERY_TYPES = auto()
    QUERY_COLORS = auto()
    QUERY_ABILITIES = auto()


class EventStatus(Enum):
    PENDING = auto()      # On the stack, can be responded to
    RESOLVING = auto()    # Currently resolving
    RESOLVED = auto()     # Done
    PREVENTED = auto()    # Cancelled


@dataclass
class Event:
    type: EventType
    payload: dict = field(default_factory=dict)
    source: Optional[str] = None      # Object ID that caused this
    controller: Optional[str] = None  # Player ID who controls source
    status: EventStatus = EventStatus.RESOLVING
    id: str = field(default_factory=new_id)
    timestamp: int = 0

    def copy(self) -> 'Event':
        return Event(
            type=self.type,
            payload=dict(self.payload),
            source=self.source,
            controller=self.controller,
            status=self.status,
            id=new_id(),
            timestamp=self.timestamp
        )


# =============================================================================
# Interceptor Types
# =============================================================================

class InterceptorPriority(Enum):
    TRANSFORM = 1   # Runs first - can change the event
    PREVENT = 2     # Can stop the event
    REACT = 3       # Runs after - creates new events
    QUERY = 4       # Modifies state reads


class InterceptorAction(Enum):
    PASS = auto()       # Do nothing
    TRANSFORM = auto()  # Modify the event
    PREVENT = auto()    # Cancel the event
    REACT = auto()      # Queue new events
    REPLACE = auto()    # Replace event with others


@dataclass
class InterceptorResult:
    action: InterceptorAction
    transformed_event: Optional[Event] = None
    new_events: list[Event] = field(default_factory=list)


# Type alias for interceptor handler functions
InterceptorHandler = Callable[['Event', 'GameState'], InterceptorResult]
EventFilter = Callable[['Event', 'GameState'], bool]


@dataclass
class Interceptor:
    id: str
    source: str                     # Object ID that created this
    controller: str                 # Player ID
    priority: InterceptorPriority
    filter: EventFilter             # What events to intercept
    handler: InterceptorHandler     # What to do
    timestamp: int = 0              # For ordering

    # Lifecycle
    duration: Optional[str] = None  # 'forever', 'end_of_turn', 'until_leaves'
    uses_remaining: Optional[int] = None


# =============================================================================
# Card Types
# =============================================================================

class CardType(Enum):
    CREATURE = auto()
    INSTANT = auto()
    SORCERY = auto()
    ENCHANTMENT = auto()
    ARTIFACT = auto()
    LAND = auto()
    PLANESWALKER = auto()


class Color(Enum):
    WHITE = 'W'
    BLUE = 'U'
    BLACK = 'B'
    RED = 'R'
    GREEN = 'G'
    COLORLESS = 'C'


class ZoneType(Enum):
    LIBRARY = auto()
    HAND = auto()
    BATTLEFIELD = auto()
    GRAVEYARD = auto()
    STACK = auto()
    EXILE = auto()
    COMMAND = auto()


# =============================================================================
# Game Objects
# =============================================================================

@dataclass
class Characteristics:
    """Base characteristics of a card/object."""
    types: set[CardType] = field(default_factory=set)
    subtypes: set[str] = field(default_factory=set)
    supertypes: set[str] = field(default_factory=set)
    colors: set[Color] = field(default_factory=set)
    mana_cost: Optional[str] = None
    power: Optional[int] = None
    toughness: Optional[int] = None
    abilities: list[dict] = field(default_factory=list)  # Keyword abilities and other static abilities


@dataclass
class ObjectState:
    """Mutable state of an object."""
    tapped: bool = False
    flipped: bool = False
    face_down: bool = False
    damage: int = 0
    counters: dict[str, int] = field(default_factory=dict)
    attached_to: Optional[str] = None
    attachments: list[str] = field(default_factory=list)


@dataclass
class GameObject:
    """A card, token, or other game object."""
    id: str
    name: str
    owner: str                          # Player ID
    controller: str                     # Player ID
    zone: ZoneType
    characteristics: Characteristics
    state: ObjectState = field(default_factory=ObjectState)

    # Interceptors this object has registered
    interceptor_ids: list[str] = field(default_factory=list)

    # Card definition reference (for tokens, this is None)
    card_def: Optional['CardDefinition'] = None

    # Timestamps
    entered_zone_at: int = 0
    created_at: int = 0


# =============================================================================
# Zone
# =============================================================================

@dataclass
class Zone:
    type: ZoneType
    owner: Optional[str]  # Player ID, or None for shared zones
    objects: list[str] = field(default_factory=list)  # Object IDs, ordered

    @property
    def is_ordered(self) -> bool:
        return self.type in {ZoneType.LIBRARY, ZoneType.GRAVEYARD, ZoneType.STACK}

    @property
    def is_hidden(self) -> bool:
        return self.type in {ZoneType.LIBRARY, ZoneType.HAND}


# =============================================================================
# Player
# =============================================================================

@dataclass
class Player:
    id: str
    name: str
    life: int = 20
    mana_pool: dict[Color, int] = field(default_factory=dict)
    has_lost: bool = False
    has_won: bool = False


# =============================================================================
# Card Definition (template for creating objects)
# =============================================================================

@dataclass
class CardDefinition:
    """Template for a card - used to create GameObjects."""
    name: str
    mana_cost: Optional[str]
    characteristics: Characteristics
    text: str = ""

    # NEW: Declarative abilities - single source of truth for text and behavior
    abilities: list = field(default_factory=list)

    # Function to set up interceptors when this card enters play
    setup_interceptors: Optional[Callable[['GameObject', 'GameState'], list[Interceptor]]] = None

    # Function for spell/ability resolution
    resolve: Optional[Callable[['Event', 'GameState'], list[Event]]] = None

    def __post_init__(self):
        """Auto-generate text and setup_interceptors from abilities if provided."""
        if self.abilities:
            # Generate text if not provided
            if not self.text:
                self.text = self._generate_text()
            # Generate setup_interceptors if not provided
            if not self.setup_interceptors:
                self.setup_interceptors = self._generate_setup()

    def _generate_text(self) -> str:
        """Generate rules text from abilities."""
        texts = []
        for ability in self.abilities:
            if hasattr(ability, 'render_text'):
                texts.append(ability.render_text(self.name))
        return " ".join(texts)

    def _generate_setup(self) -> Callable[['GameObject', 'GameState'], list[Interceptor]]:
        """Generate setup_interceptors function from abilities."""
        abilities = self.abilities

        def setup(obj: 'GameObject', state: 'GameState') -> list[Interceptor]:
            interceptors = []
            for ability in abilities:
                if hasattr(ability, 'generate_interceptors'):
                    interceptors.extend(ability.generate_interceptors(obj, state))
            return interceptors

        return setup


# =============================================================================
# Game State (forward declaration - full impl in game_state.py)
# =============================================================================

@dataclass
class GameState:
    """Complete game state."""
    players: dict[str, Player] = field(default_factory=dict)
    objects: dict[str, GameObject] = field(default_factory=dict)
    zones: dict[str, Zone] = field(default_factory=dict)
    interceptors: dict[str, Interceptor] = field(default_factory=dict)

    # Turn tracking
    active_player: Optional[str] = None
    priority_player: Optional[str] = None
    turn_number: int = 0
    timestamp: int = 0  # Global timestamp counter

    # Pending events (the "stack")
    pending_events: list[Event] = field(default_factory=list)

    # Event history
    event_log: list[Event] = field(default_factory=list)

    def next_timestamp(self) -> int:
        self.timestamp += 1
        return self.timestamp
