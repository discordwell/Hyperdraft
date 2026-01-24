"""
Hyperdraft Game Manager

High-level game operations and state-based action checking.
"""

from typing import Optional
from .types import (
    GameState, GameObject, Player, Zone, ZoneType,
    Event, EventType, EventStatus,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    Characteristics, ObjectState, CardType,
    new_id
)
from .pipeline import EventPipeline
from .queries import get_power, get_toughness, is_creature


class Game:
    """Main game controller."""

    def __init__(self):
        self.state = GameState()
        self.pipeline = EventPipeline(self.state)
        self._setup_system_interceptors()

    def add_player(self, name: str, life: int = 20) -> Player:
        """Add a player to the game."""
        player_id = new_id()
        player = Player(id=player_id, name=name, life=life)
        self.state.players[player_id] = player

        # Create zones for this player
        self._create_player_zones(player_id)

        return player

    def _create_player_zones(self, player_id: str):
        """Create library, hand, graveyard for a player."""
        for zone_type in [ZoneType.LIBRARY, ZoneType.HAND, ZoneType.GRAVEYARD]:
            key = f"{zone_type.name.lower()}_{player_id}"
            self.state.zones[key] = Zone(
                type=zone_type,
                owner=player_id
            )

    def _setup_shared_zones(self):
        """Create battlefield, stack, exile, command zones."""
        for zone_type in [ZoneType.BATTLEFIELD, ZoneType.STACK, ZoneType.EXILE, ZoneType.COMMAND]:
            key = zone_type.name.lower()
            if key not in self.state.zones:
                self.state.zones[key] = Zone(type=zone_type, owner=None)

    def create_object(
        self,
        name: str,
        owner_id: str,
        zone: ZoneType,
        characteristics: Optional[Characteristics] = None,
        card_def = None
    ) -> GameObject:
        """Create a game object (card/token)."""
        obj_id = new_id()
        obj = GameObject(
            id=obj_id,
            name=name,
            owner=owner_id,
            controller=owner_id,
            zone=zone,
            characteristics=characteristics or Characteristics(),
            state=ObjectState(),
            card_def=card_def,
            created_at=self.state.next_timestamp(),
            entered_zone_at=self.state.timestamp
        )

        self.state.objects[obj_id] = obj

        # Add to appropriate zone
        zone_key = self._get_zone_key(zone, owner_id)
        if zone_key and zone_key in self.state.zones:
            self.state.zones[zone_key].objects.append(obj_id)

        # If card_def has setup_interceptors, run it
        if card_def and card_def.setup_interceptors:
            interceptors = card_def.setup_interceptors(obj, self.state)
            for interceptor in interceptors:
                self.register_interceptor(interceptor, obj)

        return obj

    def _get_zone_key(self, zone_type: ZoneType, owner_id: str) -> Optional[str]:
        """Get the zone key for a zone type and owner."""
        if zone_type in {ZoneType.LIBRARY, ZoneType.HAND, ZoneType.GRAVEYARD}:
            return f"{zone_type.name.lower()}_{owner_id}"
        elif zone_type in {ZoneType.BATTLEFIELD, ZoneType.STACK, ZoneType.EXILE, ZoneType.COMMAND}:
            return zone_type.name.lower()
        return None

    def register_interceptor(self, interceptor: Interceptor, source_obj: Optional[GameObject] = None):
        """Register an interceptor."""
        interceptor.timestamp = self.state.next_timestamp()
        self.state.interceptors[interceptor.id] = interceptor

        if source_obj:
            source_obj.interceptor_ids.append(interceptor.id)

    def emit(self, event: Event) -> list[Event]:
        """Emit an event through the pipeline."""
        return self.pipeline.emit(event)

    def deal_damage(self, source_id: str, target_id: str, amount: int) -> list[Event]:
        """Convenience method to deal damage."""
        source = self.state.objects.get(source_id)
        return self.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': amount},
            source=source_id,
            controller=source.controller if source else None
        ))

    def draw_cards(self, player_id: str, count: int = 1) -> list[Event]:
        """Convenience method to draw cards."""
        return self.emit(Event(
            type=EventType.DRAW,
            payload={'player': player_id, 'count': count}
        ))

    def destroy(self, object_id: str) -> list[Event]:
        """Convenience method to destroy an object."""
        return self.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': object_id}
        ))

    def check_state_based_actions(self) -> list[Event]:
        """Check and process state-based actions. Returns events generated."""
        all_events = []

        # Loop until no more SBAs trigger
        while True:
            events = self._check_sbas_once()
            if not events:
                break
            all_events.extend(events)

        return all_events

    def _check_sbas_once(self) -> list[Event]:
        """Single pass of SBA checking."""
        events = []

        # Check player life totals
        for player in self.state.players.values():
            if player.life <= 0 and not player.has_lost:
                events.extend(self.emit(Event(
                    type=EventType.PLAYER_LOSES,
                    payload={'player': player.id, 'reason': 'life'}
                )))

        # Check creature toughness
        battlefield_key = 'battlefield'
        if battlefield_key in self.state.zones:
            for obj_id in list(self.state.zones[battlefield_key].objects):
                if obj_id not in self.state.objects:
                    continue

                obj = self.state.objects[obj_id]

                if not is_creature(obj, self.state):
                    continue

                toughness = get_toughness(obj, self.state)

                # Zero or less toughness
                if toughness <= 0:
                    events.extend(self.emit(Event(
                        type=EventType.OBJECT_DESTROYED,
                        payload={'object_id': obj_id, 'reason': 'zero_toughness'}
                    )))
                    continue

                # Lethal damage
                if obj.state.damage >= toughness:
                    events.extend(self.emit(Event(
                        type=EventType.OBJECT_DESTROYED,
                        payload={'object_id': obj_id, 'reason': 'lethal_damage'}
                    )))

        return events

    def _setup_system_interceptors(self):
        """Set up built-in system interceptors."""
        self._setup_shared_zones()
        # System interceptors could go here, but we're handling SBAs
        # explicitly in check_state_based_actions() for clarity


# =============================================================================
# Card Builder Helpers
# =============================================================================

def make_creature(
    name: str,
    power: int,
    toughness: int,
    mana_cost: str = "",
    types: set[CardType] = None,
    subtypes: set[str] = None,
    supertypes: set[str] = None,
    colors: set = None,
    text: str = "",
    setup_interceptors = None
) -> 'CardDefinition':
    """Helper to create creature card definitions."""
    from .types import CardDefinition, Characteristics

    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types=(types or set()) | {CardType.CREATURE},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors or set(),
            mana_cost=mana_cost,
            power=power,
            toughness=toughness
        ),
        text=text,
        setup_interceptors=setup_interceptors
    )


def make_instant(
    name: str,
    mana_cost: str = "",
    colors: set = None,
    text: str = "",
    resolve = None
) -> 'CardDefinition':
    """Helper to create instant card definitions."""
    from .types import CardDefinition, Characteristics

    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.INSTANT},
            colors=colors or set(),
            mana_cost=mana_cost
        ),
        text=text,
        resolve=resolve
    )


def make_enchantment(
    name: str,
    mana_cost: str = "",
    colors: set = None,
    text: str = "",
    setup_interceptors = None
) -> 'CardDefinition':
    """Helper to create enchantment card definitions."""
    from .types import CardDefinition, Characteristics

    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT},
            colors=colors or set(),
            mana_cost=mana_cost
        ),
        text=text,
        setup_interceptors=setup_interceptors
    )
