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
    PT_MODIFICATION = auto()  # Temporary P/T changes (until end of turn, etc.)

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

    # Targeting
    TARGET_REQUIRED = auto()  # Card requires a target to be chosen

    # Library manipulation
    SCRY = auto()              # Look at top N cards, put any on bottom
    SURVEIL = auto()           # Look at top N cards, put any in graveyard
    MILL = auto()              # Put top N cards into graveyard
    EXPLORE = auto()           # Reveal top card, +1/+1 or keep on top
    DISCOVER = auto()          # Exile until CMC <= N, cast free or put in hand
    SEARCH_LIBRARY = auto()    # Search library for card
    LIBRARY_SEARCH = auto()    # Alias for SEARCH_LIBRARY
    LOOK_AT_TOP = auto()       # Look at top N cards
    REVEAL_TOP = auto()        # Reveal top card(s)
    REVEAL_UNTIL_LAND = auto() # Reveal until land found
    EXILE_FROM_TOP = auto()    # Exile top card(s) of library
    IMPULSE_DRAW = auto()      # Exile top, may play until end of turn

    # Token creation
    CREATE_TOKEN = auto()      # Create a token

    # Sacrifice
    SACRIFICE = auto()         # Sacrifice a permanent
    SACRIFICE_REQUIRED = auto()        # Player must sacrifice
    SACRIFICE_ALL = auto()             # Sacrifice all of type
    OPTIONAL_SACRIFICE_FOR_EFFECT = auto()  # May sacrifice for effect

    # Temporary effects
    PUMP = auto()              # +X/+Y until end of turn
    TEMPORARY_EFFECT = auto()  # Generic temporary effect
    GRANT_KEYWORD = auto()     # Grant keyword until end of turn

    # Conditional effects
    CONDITIONAL_COUNTERS = auto()      # Add counters if condition met
    CONDITIONAL_DISCARD = auto()       # Discard if condition met
    OPTIONAL_COST_FOR_EFFECT = auto()  # Pay optional cost for effect
    OPTIONAL_DISCARD_FOR_EFFECT = auto()  # Discard for effect

    # Misc
    EXILE = auto()             # Exile a card/permanent
    MANIFEST_DREAD = auto()    # Duskmourn manifest dread mechanic
    MANA_ADDED = auto()        # Mana was added to pool
    ADD_MANA = auto()          # Alias for mana production
    TAP_FOR_EFFECT = auto()    # Tap as part of an effect
    CONDITIONAL_EFFECT = auto() # Effect with condition

    # Additional card-used events
    DESTROY = auto()                       # Destroy a permanent
    COUNTER = auto()                       # Counter a spell/ability
    COPY_SPELL = auto()                    # Copy a spell on the stack
    RETURN_TO_HAND = auto()                # Return permanent to hand
    RETURN_FROM_GRAVEYARD = auto()         # Return card from graveyard
    RETURN_TO_HAND_FROM_GRAVEYARD = auto() # Bounce from graveyard to hand
    TAP_TARGET = auto()                    # Tap target permanent
    UNTAP_TARGET = auto()                  # Untap target permanent
    UNTAP_ALL = auto()                     # Untap all of type
    REVEAL_HAND = auto()                   # Reveal player's hand
    LIFE_GAIN = auto()                     # Alias - use LIFE_CHANGE with amount > 0
    LIFE_LOSS = auto()                     # Alias - use LIFE_CHANGE with amount < 0
    EXTRA_TURN = auto()                    # Take an extra turn
    EXTRA_COMBAT = auto()                  # Extra combat phase
    PHASE_OUT = auto()                     # Phase out a permanent
    PHASE_IN = auto()                      # Phase in a permanent
    FREEZE = auto()                        # Freeze a permanent (doesn't untap)
    TRANSFORM = auto()                     # Transform a DFC
    GRANT_ABILITY = auto()                 # Grant an ability temporarily
    GRANT_UNBLOCKABLE = auto()             # Grant can't be blocked
    GRANT_PT_MODIFIER = auto()             # Grant P/T modifier
    TEMPORARY_BOOST = auto()               # Temporary stat boost (alias for PUMP)
    REMOVE_ABILITIES = auto()              # Remove all abilities from permanent
    CONTINUOUS_EFFECT = auto()             # Register continuous effect
    DELAYED_TRIGGER = auto()               # Create delayed trigger
    DELAYED_SACRIFICE = auto()             # Sacrifice at end of turn
    MODAL_CHOICE = auto()                  # Player makes modal choice
    MAY_PAY_LIFE = auto()                  # May pay life for effect
    MAY_PAY_DRAW = auto()                  # May pay to draw
    MAY_SACRIFICE = auto()                 # May sacrifice for effect
    OPTIONAL_COST = auto()                 # Pay optional additional cost
    DISCARD_CHOICE = auto()                # Choose cards to discard
    LOOK_TOP_CARDS = auto()                # Look at top N cards of library
    EXILE_TOP_CARD = auto()                # Exile top card of library
    EXILE_TOP_PLAY = auto()                # Exile top, may play
    IMPULSE_TO_GRAVEYARD = auto()          # Put impulse-drawn cards to graveyard
    PUT_TIME_COUNTER = auto()              # Put time counters on permanent
    DECLARE_ATTACKERS = auto()             # Declare attackers step
    AUTO_EQUIP = auto()                    # Auto-equip to creature


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

    @property
    def keywords(self) -> set[str]:
        """Get set of keyword abilities for easy checking."""
        return {a.get('keyword', '').lower() for a in self.abilities if a.get('keyword')}


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
    is_token: bool = False           # True if this is a token (not a card)
    damage_marked: int = 0           # Damage marked this turn (before cleanup)
    crewed_until_eot: bool = False   # True if Vehicle was crewed this turn


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
# Card Face (for split/adventure cards)
# =============================================================================

@dataclass
class CardFace:
    """
    Represents one face of a multi-face card (adventure, split, MDFC).

    For adventure cards: the adventure spell portion
    For split cards: left or right half
    For MDFCs: front or back face
    """
    name: str
    mana_cost: str
    types: set['CardType'] = field(default_factory=set)
    text: str = ""
    power: Optional[int] = None
    toughness: Optional[int] = None
    resolve: Optional[Callable[['Event', 'GameState'], list['Event']]] = None


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
    rarity: Optional[str] = None  # 'common', 'uncommon', 'rare', 'mythic'

    # NEW: Declarative abilities - single source of truth for text and behavior
    abilities: list = field(default_factory=list)

    # Function to set up interceptors when this card enters play
    setup_interceptors: Optional[Callable[['GameObject', 'GameState'], list[Interceptor]]] = None

    # Function for spell/ability resolution
    resolve: Optional[Callable[['Event', 'GameState'], list[Event]]] = None

    # Multi-face card support
    adventure: Optional[CardFace] = None      # Adventure spell portion
    split_left: Optional[CardFace] = None     # Left half of split card
    split_right: Optional[CardFace] = None    # Right half of split card
    back_face: Optional[CardFace] = None      # Back face of MDFC

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

# =============================================================================
# Player Choice System
# =============================================================================

@dataclass
class PendingChoice:
    """
    Tracks when the game needs player input.

    Used for modal spells, targeted ETB abilities, scry/surveil decisions, etc.
    When pending_choice is set on GameState, the game pauses and waits for
    the player to submit their choice through the API.
    """
    choice_type: str  # "modal", "target", "scry", "surveil", "order", "discard", etc.
    player: str  # player_id who must make the choice
    prompt: str  # Human-readable prompt ("Choose a mode", "Choose a target", etc.)
    options: list[Any]  # Available choices (card IDs, mode indices, etc.)
    source_id: str  # Card/ability ID that needs the choice
    min_choices: int = 1  # Minimum number of choices required
    max_choices: int = 1  # Maximum number of choices allowed
    callback_data: dict = field(default_factory=dict)  # Data needed to continue after choice
    id: str = field(default_factory=new_id)  # Unique identifier for this choice

    def validate_selection(self, selected: list[Any]) -> tuple[bool, str]:
        """
        Validate that a selection is legal for this choice.

        Returns (is_valid, error_message).
        """
        if len(selected) < self.min_choices:
            return False, f"Must choose at least {self.min_choices} option(s)"
        if len(selected) > self.max_choices:
            return False, f"Cannot choose more than {self.max_choices} option(s)"

        # Check all selected options are valid
        for choice in selected:
            if choice not in self.options:
                return False, f"Invalid choice: {choice}"

        return True, ""


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

    # Land play tracking (for "one land per turn" rule)
    lands_played_this_turn: int = 0
    lands_allowed_this_turn: int = 1  # Can be increased by effects like Exploration

    # Pending events (the "stack")
    pending_events: list[Event] = field(default_factory=list)

    # Event history
    event_log: list[Event] = field(default_factory=list)

    # Player choice system - when set, game is paused waiting for input
    pending_choice: Optional['PendingChoice'] = None

    def next_timestamp(self) -> int:
        self.timestamp += 1
        return self.timestamp

    def has_pending_choice(self) -> bool:
        """Check if the game is waiting for a player choice."""
        return self.pending_choice is not None

    def get_pending_choice_for_player(self, player_id: str) -> Optional['PendingChoice']:
        """Get the pending choice if it's for this player, else None."""
        if self.pending_choice and self.pending_choice.player == player_id:
            return self.pending_choice
        return None
