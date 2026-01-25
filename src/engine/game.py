"""
Hyperdraft Game Manager

High-level game operations and state-based action checking.
Integrates all game systems: turns, priority, stack, combat, mana.
"""

from typing import Optional, Callable, TYPE_CHECKING
import asyncio

from .types import (
    GameState, GameObject, Player, Zone, ZoneType,
    Event, EventType, EventStatus,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    Characteristics, ObjectState, CardType,
    new_id
)
from .pipeline import EventPipeline
from .queries import get_power, get_toughness, is_creature
from .mana import ManaSystem, ManaCost, ManaType
from .stack import StackManager, StackItem, SpellBuilder
from .turn import TurnManager, Phase, Step
from .priority import PrioritySystem, PlayerAction, ActionType, LegalAction
from .combat import CombatManager, AttackDeclaration, BlockDeclaration
from .targeting import TargetingSystem, Target, TargetRequirement


class Game:
    """
    Main game controller.

    Integrates all subsystems:
    - Event Pipeline (existing)
    - Turn Manager
    - Priority System
    - Stack Manager
    - Combat Manager
    - Mana System
    - Targeting System
    """

    def __init__(self):
        self.state = GameState()
        self.pipeline = EventPipeline(self.state)

        # Initialize subsystems
        self.mana_system = ManaSystem(self.state)
        self.stack = StackManager(self.state)
        self.turn_manager = TurnManager(self.state)
        self.priority_system = PrioritySystem(self.state)
        self.combat_manager = CombatManager(self.state)
        self.targeting_system = TargetingSystem(self.state)

        # Wire up subsystem dependencies
        self._connect_subsystems()

        # Callbacks for UI/AI integration
        self.on_game_event: Optional[Callable[[Event], None]] = None
        self.on_state_change: Optional[Callable[[GameState], None]] = None

        # Mulligan handler: (player_id, hand, mulligan_count) -> bool (True = keep)
        self.get_mulligan_decision: Optional[Callable[[str, list[GameObject], int], bool]] = None

        self._setup_system_interceptors()

    def _connect_subsystems(self):
        """Wire up dependencies between subsystems."""
        # Priority system needs other systems
        self.priority_system.stack = self.stack
        self.priority_system.turn_manager = self.turn_manager
        self.priority_system.mana_system = self.mana_system
        self.priority_system.pipeline = self.pipeline

        # Turn manager needs priority, combat, and pipeline
        self.turn_manager.priority_system = self.priority_system
        self.turn_manager.combat_manager = self.combat_manager
        self.turn_manager.pipeline = self.pipeline

        # Combat manager needs turn, priority, and pipeline
        self.combat_manager.turn_manager = self.turn_manager
        self.combat_manager.priority_system = self.priority_system
        self.combat_manager.pipeline = self.pipeline

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
            for interceptor in (interceptors or []):
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

    # =========================================================================
    # Game Flow Methods
    # =========================================================================

    async def start_game(self) -> None:
        """
        Initialize and start the game.

        Call this after adding players and setting up decks.
        """
        # Set up turn order
        player_ids = list(self.state.players.keys())
        self.turn_manager.set_turn_order(player_ids)

        # Draw starting hands and handle mulligans (London Mulligan)
        for player_id in player_ids:
            await self._resolve_mulligans(player_id)

        await self.turn_manager.start_game()

    async def _resolve_mulligans(self, player_id: str) -> None:
        """
        Handle mulligan decisions for a player using London Mulligan rules.

        London Mulligan:
        1. Draw 7 cards
        2. Decide to keep or mulligan
        3. If mulligan: shuffle hand back, draw 7, repeat
        4. After keeping: put X cards on bottom (X = number of mulligans taken)
        """
        mulligan_count = 0
        max_mulligans = 7  # Can't mulligan more than 7 times

        while mulligan_count < max_mulligans:
            # Draw 7 cards
            self.draw_cards(player_id, 7)

            # Get the hand
            hand = self.get_hand(player_id)

            # Check if player wants to mulligan
            keep = True
            if self.get_mulligan_decision:
                keep = self.get_mulligan_decision(player_id, hand, mulligan_count)
            else:
                # Default: keep any hand with at least 2 lands and 1 spell
                keep = self._default_mulligan_decision(hand, mulligan_count)

            if keep:
                # Put X cards on bottom of library (X = mulligan count)
                if mulligan_count > 0:
                    self._put_cards_on_bottom(player_id, mulligan_count)
                break
            else:
                # Shuffle hand back into library
                self._shuffle_hand_into_library(player_id)
                mulligan_count += 1

    def _default_mulligan_decision(self, hand: list[GameObject], mulligan_count: int) -> bool:
        """Default mulligan logic: keep hands with 2-5 lands."""
        if mulligan_count >= 4:
            # Keep anything at 3 cards or fewer
            return True

        land_count = sum(1 for card in hand if CardType.LAND in card.characteristics.types)

        # Keep hands with 2-5 lands
        if 2 <= land_count <= 5:
            return True

        return False

    def _shuffle_hand_into_library(self, player_id: str) -> None:
        """Shuffle a player's hand back into their library."""
        import random
        hand_key = f"hand_{player_id}"
        library_key = f"library_{player_id}"

        hand = self.state.zones.get(hand_key)
        library = self.state.zones.get(library_key)

        if hand and library:
            # Move all cards from hand to library
            library.objects.extend(hand.objects)
            hand.objects.clear()
            # Shuffle library
            random.shuffle(library.objects)

    def _put_cards_on_bottom(self, player_id: str, count: int) -> None:
        """
        Let player put cards from hand on bottom of library.

        For AI/auto: puts the worst cards (lands if too many, expensive spells otherwise).
        """
        hand_key = f"hand_{player_id}"
        library_key = f"library_{player_id}"

        hand = self.state.zones.get(hand_key)
        library = self.state.zones.get(library_key)

        if not hand or not library or count <= 0:
            return

        hand_cards = [self.state.objects[oid] for oid in hand.objects if oid in self.state.objects]

        # Score cards (lower = bottom first)
        # Lands are medium, cheap spells are good, expensive spells go to bottom
        def card_score(card: GameObject) -> float:
            if CardType.LAND in card.characteristics.types:
                # Count lands in hand
                land_count = sum(1 for c in hand_cards if CardType.LAND in c.characteristics.types)
                if land_count > 3:
                    return -10  # Too many lands, bottom them
                return 5  # Keep lands

            # Non-land: score by CMC (lower CMC = higher score)
            cmc = card.characteristics.mana_cost.count('{')
            return 10 - cmc

        # Sort by score, take the worst ones
        hand_cards.sort(key=card_score)
        cards_to_bottom = hand_cards[:count]

        for card in cards_to_bottom:
            if card.id in hand.objects:
                hand.objects.remove(card.id)
                library.objects.insert(0, card.id)  # Insert at bottom

    async def run_game(self) -> str:
        """
        Run the game until completion.

        Returns the winning player's ID, or None for a draw.
        """
        while not self.is_game_over():
            await self.turn_manager.run_turn()

        return self.get_winner()

    async def run_turn(self, player_id: str = None) -> list[Event]:
        """Run a single turn."""
        return await self.turn_manager.run_turn(player_id)

    def is_game_over(self) -> bool:
        """Check if the game is over."""
        alive_players = [p for p in self.state.players.values() if not p.has_lost]
        return len(alive_players) <= 1

    def get_winner(self) -> Optional[str]:
        """Get the winning player's ID."""
        alive = [p for p in self.state.players.values() if not p.has_lost]
        if len(alive) == 1:
            return alive[0].id
        return None

    # =========================================================================
    # Player Setup
    # =========================================================================

    def set_ai_player(self, player_id: str) -> None:
        """Mark a player as AI-controlled."""
        self.priority_system.set_ai_player(player_id)

    def set_human_action_handler(
        self,
        handler: Callable[[str, list[LegalAction]], asyncio.Future]
    ) -> None:
        """Set the handler for getting human player actions."""
        self.priority_system.get_human_action = handler

    def set_ai_action_handler(
        self,
        handler: Callable[[str, GameState, list[LegalAction]], PlayerAction]
    ) -> None:
        """Set the handler for AI player decisions."""
        self.priority_system.get_ai_action = handler

    def set_attack_handler(
        self,
        handler: Callable[[str, list[str]], list[AttackDeclaration]]
    ) -> None:
        """Set the handler for getting attack declarations."""
        self.combat_manager.get_attack_declarations = handler

    def set_block_handler(
        self,
        handler: Callable[[str, list[AttackDeclaration], list[str]], list[BlockDeclaration]]
    ) -> None:
        """Set the handler for getting block declarations."""
        self.combat_manager.get_block_declarations = handler

    def set_mulligan_handler(
        self,
        handler: Callable[[str, list[GameObject], int], bool]
    ) -> None:
        """
        Set the handler for mulligan decisions.

        Handler receives: (player_id, hand_cards, mulligan_count)
        Returns: True to keep, False to mulligan
        """
        self.get_mulligan_decision = handler

    # =========================================================================
    # Deck Building
    # =========================================================================

    def add_card_to_library(
        self,
        player_id: str,
        card_def: 'CardDefinition',
        position: str = 'top'
    ) -> GameObject:
        """Add a card to a player's library."""
        obj = self.create_object(
            name=card_def.name,
            owner_id=player_id,
            zone=ZoneType.LIBRARY,
            characteristics=card_def.characteristics,
            card_def=card_def
        )

        # Position in library
        library_key = f"library_{player_id}"
        library = self.state.zones.get(library_key)
        if library and position == 'bottom':
            # Move to bottom (it was added to top by create_object)
            library.objects.remove(obj.id)
            library.objects.insert(0, obj.id)

        return obj

    def shuffle_library(self, player_id: str) -> None:
        """Shuffle a player's library."""
        import random
        library_key = f"library_{player_id}"
        library = self.state.zones.get(library_key)
        if library:
            random.shuffle(library.objects)

    # =========================================================================
    # Mana Operations
    # =========================================================================

    def add_mana(
        self,
        player_id: str,
        color: ManaType,
        amount: int = 1
    ) -> None:
        """Add mana to a player's pool."""
        self.mana_system.produce_mana(player_id, color, amount)

    def can_pay_cost(self, player_id: str, cost_string: str) -> bool:
        """Check if a player can pay a mana cost."""
        cost = ManaCost.parse(cost_string)
        return self.mana_system.can_cast(player_id, cost)

    def pay_cost(self, player_id: str, cost_string: str) -> bool:
        """Pay a mana cost from a player's pool."""
        cost = ManaCost.parse(cost_string)
        return self.mana_system.pay_cost(player_id, cost)

    def empty_mana_pools(self) -> None:
        """Empty all players' mana pools."""
        self.mana_system.empty_pools()

    # =========================================================================
    # Spell Casting
    # =========================================================================

    def cast_spell(
        self,
        card_id: str,
        controller_id: str,
        targets: list[list[Target]] = None,
        x_value: int = 0
    ) -> StackItem:
        """Cast a spell and put it on the stack."""
        builder = SpellBuilder(self.state, self.stack)
        item = builder.cast_spell(
            card_id=card_id,
            controller_id=controller_id,
            targets=targets or [],
            x_value=x_value
        )
        self.stack.push(item)
        return item

    def resolve_stack(self) -> list[Event]:
        """Resolve the top item of the stack."""
        return self.stack.resolve_top()

    # =========================================================================
    # Targeting
    # =========================================================================

    def get_legal_targets(
        self,
        requirement: TargetRequirement,
        source: GameObject,
        controller_id: str
    ) -> list[str]:
        """Get all legal targets for a targeting requirement."""
        return self.targeting_system.get_legal_targets(
            requirement, source, controller_id
        )

    # =========================================================================
    # Game State Queries
    # =========================================================================

    def get_battlefield(self) -> list[GameObject]:
        """Get all permanents on the battlefield."""
        battlefield = self.state.zones.get('battlefield')
        if not battlefield:
            return []
        return [self.state.objects[oid] for oid in battlefield.objects
                if oid in self.state.objects]

    def get_hand(self, player_id: str) -> list[GameObject]:
        """Get cards in a player's hand."""
        hand_key = f"hand_{player_id}"
        hand = self.state.zones.get(hand_key)
        if not hand:
            return []
        return [self.state.objects[oid] for oid in hand.objects
                if oid in self.state.objects]

    def get_graveyard(self, player_id: str) -> list[GameObject]:
        """Get cards in a player's graveyard."""
        gy_key = f"graveyard_{player_id}"
        graveyard = self.state.zones.get(gy_key)
        if not graveyard:
            return []
        return [self.state.objects[oid] for oid in graveyard.objects
                if oid in self.state.objects]

    def get_library_size(self, player_id: str) -> int:
        """Get number of cards in a player's library."""
        library_key = f"library_{player_id}"
        library = self.state.zones.get(library_key)
        return len(library.objects) if library else 0

    def get_player(self, player_id: str) -> Optional[Player]:
        """Get a player by ID."""
        return self.state.players.get(player_id)

    def get_current_phase(self) -> Phase:
        """Get the current phase."""
        return self.turn_manager.phase

    def get_current_step(self) -> Step:
        """Get the current step."""
        return self.turn_manager.step

    def get_active_player(self) -> Optional[str]:
        """Get the active player's ID."""
        return self.turn_manager.active_player

    def get_priority_player(self) -> Optional[str]:
        """Get the player with priority."""
        return self.priority_system.priority_player

    # =========================================================================
    # Serialization for Network/UI
    # =========================================================================

    def get_game_state_for_player(self, player_id: str) -> dict:
        """
        Get the game state from a player's perspective.

        Hides hidden information (opponent's hand, library contents).
        """
        return {
            'turn_number': self.turn_manager.turn_number,
            'phase': self.turn_manager.phase.name,
            'step': self.turn_manager.step.name,
            'active_player': self.turn_manager.active_player,
            'priority_player': self.priority_system.priority_player,
            'players': {
                pid: {
                    'id': p.id,
                    'name': p.name,
                    'life': p.life,
                    'has_lost': p.has_lost,
                    'hand_size': len(self.get_hand(pid)),
                    'library_size': self.get_library_size(pid),
                }
                for pid, p in self.state.players.items()
            },
            'battlefield': [
                self._serialize_permanent(obj)
                for obj in self.get_battlefield()
            ],
            'stack': [
                self._serialize_stack_item(item)
                for item in self.stack.get_items()
            ],
            'hand': [
                self._serialize_card(obj)
                for obj in self.get_hand(player_id)
            ] if player_id else [],
            'graveyard': {
                pid: [
                    self._serialize_card(obj)
                    for obj in self.get_graveyard(pid)
                ]
                for pid in self.state.players
            },
            'legal_actions': [
                self._serialize_action(a)
                for a in self.priority_system.get_legal_actions(player_id)
            ] if player_id == self.priority_system.priority_player else [],
        }

    def _serialize_permanent(self, obj: GameObject) -> dict:
        """Serialize a permanent for the client."""
        return {
            'id': obj.id,
            'name': obj.name,
            'controller': obj.controller,
            'owner': obj.owner,
            'types': [t.name for t in obj.characteristics.types],
            'subtypes': list(obj.characteristics.subtypes),
            'power': get_power(obj, self.state) if is_creature(obj, self.state) else None,
            'toughness': get_toughness(obj, self.state) if is_creature(obj, self.state) else None,
            'tapped': obj.state.tapped,
            'counters': dict(obj.state.counters),
            'damage': obj.state.damage,
        }

    def _serialize_card(self, obj: GameObject) -> dict:
        """Serialize a card for the client."""
        return {
            'id': obj.id,
            'name': obj.name,
            'mana_cost': obj.characteristics.mana_cost,
            'types': [t.name for t in obj.characteristics.types],
            'subtypes': list(obj.characteristics.subtypes),
            'power': obj.characteristics.power,
            'toughness': obj.characteristics.toughness,
            'text': obj.card_def.text if obj.card_def else '',
        }

    def _serialize_stack_item(self, item: StackItem) -> dict:
        """Serialize a stack item for the client."""
        source = self.state.objects.get(item.source_id)
        return {
            'id': item.id,
            'type': item.type.name,
            'source_id': item.source_id,
            'source_name': source.name if source else 'Unknown',
            'controller': item.controller_id,
        }

    def _serialize_action(self, action: LegalAction) -> dict:
        """Serialize a legal action for the client."""
        return {
            'type': action.type.name,
            'card_id': action.card_id,
            'ability_id': action.ability_id,
            'description': action.description,
            'requires_mana': action.requires_mana,
        }


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
    abilities: list = None,
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
        abilities=abilities or [],
        setup_interceptors=setup_interceptors
    )


def make_instant(
    name: str,
    mana_cost: str = "",
    colors: set = None,
    text: str = "",
    abilities: list = None,
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
        abilities=abilities or [],
        resolve=resolve
    )


def make_enchantment(
    name: str,
    mana_cost: str = "",
    colors: set = None,
    subtypes: set = None,
    supertypes: set = None,
    text: str = "",
    abilities: list = None,
    setup_interceptors = None
) -> 'CardDefinition':
    """Helper to create enchantment card definitions."""
    from .types import CardDefinition, Characteristics

    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors or set(),
            mana_cost=mana_cost
        ),
        text=text,
        abilities=abilities or [],
        setup_interceptors=setup_interceptors
    )
