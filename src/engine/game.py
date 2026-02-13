"""
Hyperdraft Game Manager

High-level game operations and state-based action checking.
Integrates all game systems: turns, priority, stack, combat, mana.
"""

from typing import Optional, Callable, TYPE_CHECKING
import asyncio
import copy

from .types import (
    GameState, GameObject, Player, Zone, ZoneType,
    Event, EventType, EventStatus,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    Characteristics, ObjectState, CardType,
    PendingChoice,
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

    def __init__(self, mode: str = "mtg"):
        self.state = GameState()
        self.state.game_mode = mode

        # Set mode-specific defaults
        if mode == "hearthstone":
            self.state.max_hand_size = 10

        self.pipeline = EventPipeline(self.state)

        # Initialize subsystems using factory methods
        self.mana_system = self._create_mana_system()
        self.stack = StackManager(self.state)
        self.turn_manager = self._create_turn_manager()
        self.priority_system = PrioritySystem(self.state)
        self.combat_manager = self._create_combat_manager()
        self.targeting_system = TargetingSystem(self.state)

        # Wire up subsystem dependencies
        self._connect_subsystems()

        # Callbacks for UI/AI integration
        self.on_game_event: Optional[Callable[[Event], None]] = None
        self.on_state_change: Optional[Callable[[GameState], None]] = None

        # Mulligan handler: (player_id, hand, mulligan_count) -> bool (True = keep)
        self.get_mulligan_decision: Optional[Callable[[str, list[GameObject], int], bool]] = None

        self._setup_system_interceptors()

    def _create_mana_system(self):
        """Factory method for creating mode-specific mana system."""
        if self.state.game_mode == "hearthstone":
            from .hearthstone_mana import HearthstoneManaSystem
            return HearthstoneManaSystem(self.state)
        return ManaSystem(self.state)

    def _create_combat_manager(self):
        """Factory method for creating mode-specific combat manager."""
        if self.state.game_mode == "hearthstone":
            from .hearthstone_combat import HearthstoneCombatManager
            return HearthstoneCombatManager(self.state)
        return CombatManager(self.state)

    def _create_turn_manager(self):
        """Factory method for creating mode-specific turn manager."""
        if self.state.game_mode == "hearthstone":
            from .hearthstone_turn import HearthstoneTurnManager
            return HearthstoneTurnManager(self.state)
        return TurnManager(self.state)

    def _connect_subsystems(self):
        """Wire up dependencies between subsystems."""
        # Store game reference for subsystems to access
        self.state._game = self
        self.pipeline.game = self

        # Priority system needs other systems
        self.priority_system.stack = self.stack
        self.priority_system.turn_manager = self.turn_manager
        self.priority_system.mana_system = self.mana_system
        self.priority_system.pipeline = self.pipeline

        # Turn manager needs priority, combat, pipeline, and mana
        self.turn_manager.priority_system = self.priority_system
        self.turn_manager.combat_manager = self.combat_manager
        self.turn_manager.pipeline = self.pipeline
        self.turn_manager.mana_system = self.mana_system

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

    def setup_hearthstone_player(self, player: Player, hero_def, hero_power_def):
        """
        Set up a Hearthstone player with hero and hero power.

        Args:
            player: Player object
            hero_def: Hero CardDefinition
            hero_power_def: Hero Power CardDefinition
        """
        # Create hero on battlefield
        hero = self.create_object(
            name=hero_def.name,
            owner_id=player.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=copy.deepcopy(hero_def.characteristics),
            card_def=hero_def
        )
        player.hero_id = hero.id
        player.life = hero_def.characteristics.toughness or 30
        player.max_life = player.life

        # Note: create_object already runs card_def.setup_interceptors

        # Create hero power in command zone
        hero_power = self.create_object(
            name=hero_power_def.name,
            owner_id=player.id,
            zone=ZoneType.COMMAND,
            characteristics=copy.deepcopy(hero_power_def.characteristics),
            card_def=hero_power_def
        )
        player.hero_power_id = hero_power.id

        # Note: create_object already runs card_def.setup_interceptors

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
            # Characteristics are per-object mutable state (types can change, keyword
            # counters/grants can add abilities, etc.). Copy to avoid sharing the
            # CardDefinition template between different physical objects.
            characteristics=copy.deepcopy(characteristics or Characteristics()),
            state=ObjectState(
                summoning_sickness=(zone == ZoneType.BATTLEFIELD)
            ),
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
        # System interceptors (generic rules glue that card files rely on).

        # -----------------------------------------------------------------
        # FLICKER: exile an object, then return it at the beginning of the
        # next end step (under its owner's control).
        # -----------------------------------------------------------------
        def _flicker_filter(event: Event, state: GameState) -> bool:
            return event.type == EventType.FLICKER

        def _flicker_handler(event: Event, state: GameState) -> InterceptorResult:
            object_id = event.payload.get("object_id")
            if not object_id or object_id not in state.objects:
                return InterceptorResult(action=InterceptorAction.PASS)

            obj = state.objects[object_id]
            if obj.zone != ZoneType.BATTLEFIELD:
                return InterceptorResult(action=InterceptorAction.PASS)

            with_flying_counter = bool(event.payload.get("with_flying_counter"))

            # Register a one-shot delayed return at the beginning of the next end step.
            return_interceptor_id = new_id()

            def _return_filter(e: Event, s: GameState) -> bool:
                return e.type == EventType.PHASE_START and e.payload.get("phase") == "end_step"

            def _return_handler(e: Event, s: GameState) -> InterceptorResult:
                returning = s.objects.get(object_id)
                if not returning or returning.zone != ZoneType.EXILE:
                    return InterceptorResult(action=InterceptorAction.PASS)

                # MTG: returns under its owner's control.
                returning.controller = returning.owner

                payload = {
                    "object_id": object_id,
                    "from_zone_type": ZoneType.EXILE,
                    "to_zone_type": ZoneType.BATTLEFIELD,
                }
                if with_flying_counter:
                    payload["counters"] = {"flying": 1}

                return InterceptorResult(
                    action=InterceptorAction.REACT,
                    new_events=[Event(type=EventType.ZONE_CHANGE, payload=payload, source=event.source)],
                )

            self.register_interceptor(
                Interceptor(
                    id=return_interceptor_id,
                    source=event.source or object_id,
                    controller=obj.controller,
                    priority=InterceptorPriority.REACT,
                    filter=_return_filter,
                    handler=_return_handler,
                    duration="forever",
                    uses_remaining=1,
                )
            )

            # Exile now.
            exile_event = Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    "object_id": object_id,
                    "from_zone_type": ZoneType.BATTLEFIELD,
                    "to_zone_type": ZoneType.EXILE,
                },
                source=event.source,
            )
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[exile_event])

        self.register_interceptor(
            Interceptor(
                id=new_id(),
                source="SYSTEM",
                controller="SYSTEM",
                priority=InterceptorPriority.REACT,
                filter=_flicker_filter,
                handler=_flicker_handler,
                duration="forever",
            )
        )

        # -----------------------------------------------------------------
        # BOUNCE: return a permanent to its owner's hand.
        # Many card files express this as EventType.BOUNCE rather than a direct
        # ZONE_CHANGE, so normalize here.
        # -----------------------------------------------------------------
        def _bounce_filter(event: Event, state: GameState) -> bool:
            return event.type == EventType.BOUNCE

        def _bounce_handler(event: Event, state: GameState) -> InterceptorResult:
            object_id = event.payload.get("object_id")
            if not object_id or object_id not in state.objects:
                return InterceptorResult(action=InterceptorAction.PASS)

            obj = state.objects[object_id]
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=Event(
                    type=EventType.ZONE_CHANGE,
                    payload={
                        "object_id": object_id,
                        "from_zone_type": obj.zone,
                        "to_zone_type": ZoneType.HAND,
                        "to_zone": f"hand_{obj.owner}",
                    },
                    source=event.source,
                    controller=event.controller,
                ),
            )

        self.register_interceptor(
            Interceptor(
                id=new_id(),
                source="SYSTEM",
                controller="SYSTEM",
                priority=InterceptorPriority.TRANSFORM,
                filter=_bounce_filter,
                handler=_bounce_handler,
                duration="forever",
            )
        )

        # -----------------------------------------------------------------
        # Legacy event aliases used by some card scripts.
        # Normalize to core engine events so standard trigger helpers fire.
        # -----------------------------------------------------------------
        def _destroy_filter(event: Event, state: GameState) -> bool:
            return event.type == EventType.DESTROY

        def _destroy_handler(event: Event, state: GameState) -> InterceptorResult:
            object_id = (
                event.payload.get("object_id")
                or event.payload.get("target")
                or event.payload.get("target_id")
            )
            if not object_id:
                return InterceptorResult(action=InterceptorAction.PASS)
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={"object_id": object_id, "reason": event.payload.get("reason", "destroy")},
                    source=event.source,
                    controller=event.controller,
                ),
            )

        self.register_interceptor(
            Interceptor(
                id=new_id(),
                source="SYSTEM",
                controller="SYSTEM",
                priority=InterceptorPriority.TRANSFORM,
                filter=_destroy_filter,
                handler=_destroy_handler,
                duration="forever",
            )
        )

        def _sacrifice_filter(event: Event, state: GameState) -> bool:
            return event.type == EventType.SACRIFICE

        def _sacrifice_handler(event: Event, state: GameState) -> InterceptorResult:
            object_id = (
                event.payload.get("object_id")
                or event.payload.get("target")
                or event.payload.get("target_id")
            )
            if not object_id or object_id not in state.objects:
                return InterceptorResult(action=InterceptorAction.PASS)

            obj = state.objects[object_id]
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=Event(
                    type=EventType.ZONE_CHANGE,
                    payload={
                        "object_id": object_id,
                        "from_zone_type": obj.zone,
                        "to_zone_type": ZoneType.GRAVEYARD,
                        "to_zone": f"graveyard_{obj.owner}",
                        "reason": event.payload.get("reason", "sacrifice"),
                    },
                    source=event.source,
                    controller=event.controller,
                ),
            )

        self.register_interceptor(
            Interceptor(
                id=new_id(),
                source="SYSTEM",
                controller="SYSTEM",
                priority=InterceptorPriority.TRANSFORM,
                filter=_sacrifice_filter,
                handler=_sacrifice_handler,
                duration="forever",
            )
        )

        # "Can't block" is commonly expressed as a dedicated event in some sets.
        # Normalize into a temporary keyword grant so combat rules pick it up.
        def _cant_block_filter(event: Event, state: GameState) -> bool:
            return event.type == EventType.CANT_BLOCK

        def _cant_block_handler(event: Event, state: GameState) -> InterceptorResult:
            object_id = event.payload.get("object_id")
            duration = event.payload.get("duration", "end_of_turn")
            if not object_id:
                return InterceptorResult(action=InterceptorAction.PASS)
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=Event(
                    type=EventType.GRANT_KEYWORD,
                    payload={
                        "object_id": object_id,
                        "keyword": "cant_block",
                        "duration": duration,
                    },
                    source=event.source,
                    controller=event.controller,
                ),
            )

        self.register_interceptor(
            Interceptor(
                id=new_id(),
                source="SYSTEM",
                controller="SYSTEM",
                priority=InterceptorPriority.TRANSFORM,
                filter=_cant_block_filter,
                handler=_cant_block_handler,
                duration="forever",
            )
        )

        # Counterspell glue: some card scripts emit COUNTER_SPELL* events.
        def _counter_spell_filter(event: Event, state: GameState) -> bool:
            return event.type in {
                EventType.COUNTER,
                EventType.COUNTER_SPELL,
                EventType.COUNTER_SPELL_UNLESS_PAY,
            }

        def _counter_spell_handler(event: Event, state: GameState) -> InterceptorResult:
            spell_id = (
                event.payload.get("spell_id")
                or event.payload.get("object_id")
                or event.payload.get("target")
                or event.payload.get("target_id")
            )
            if not spell_id:
                return InterceptorResult(action=InterceptorAction.PASS)

            # Best-effort: find a stack item whose card/source id matches the targeted
            # stack-zone object id, then counter it.
            for stack_item in list(self.stack.items):
                if stack_item.card_id == spell_id or stack_item.source_id == spell_id:
                    counter_events = self.stack.counter(stack_item.id, reason=event.payload.get("reason", "countered"))
                    return InterceptorResult(
                        action=InterceptorAction.REACT,
                        new_events=counter_events,
                    )

            return InterceptorResult(action=InterceptorAction.PASS)

        self.register_interceptor(
            Interceptor(
                id=new_id(),
                source="SYSTEM",
                controller="SYSTEM",
                priority=InterceptorPriority.REACT,
                filter=_counter_spell_filter,
                handler=_counter_spell_handler,
                duration="forever",
            )
        )

        # Fight glue: two creatures deal damage equal to their power to each other.
        def _fight_filter(event: Event, state: GameState) -> bool:
            return event.type == EventType.FIGHT

        def _fight_handler(event: Event, state: GameState) -> InterceptorResult:
            c1 = event.payload.get("creature1") or event.payload.get("attacker")
            c2 = event.payload.get("creature2") or event.payload.get("defender")
            if not c1 or not c2:
                return InterceptorResult(action=InterceptorAction.PASS)

            o1 = state.objects.get(c1)
            o2 = state.objects.get(c2)
            if not o1 or not o2:
                return InterceptorResult(action=InterceptorAction.PASS)
            if o1.zone != ZoneType.BATTLEFIELD or o2.zone != ZoneType.BATTLEFIELD:
                return InterceptorResult(action=InterceptorAction.PASS)

            p1 = get_power(o1, state)
            p2 = get_power(o2, state)

            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[
                    Event(
                        type=EventType.DAMAGE,
                        payload={"target": c2, "amount": p1, "is_combat": False, "source": c1},
                        source=c1,
                        controller=o1.controller,
                    ),
                    Event(
                        type=EventType.DAMAGE,
                        payload={"target": c1, "amount": p2, "is_combat": False, "source": c2},
                        source=c2,
                        controller=o2.controller,
                    ),
                ],
            )

        self.register_interceptor(
            Interceptor(
                id=new_id(),
                source="SYSTEM",
                controller="SYSTEM",
                priority=InterceptorPriority.REACT,
                filter=_fight_filter,
                handler=_fight_handler,
                duration="forever",
            )
        )

        # Hearthstone Divine Shield interceptor
        if self.state.game_mode == "hearthstone":
            def _divine_shield_filter(event: Event, state: GameState) -> bool:
                if event.type != EventType.DAMAGE:
                    return False
                target_id = event.payload.get("target")
                if not target_id:
                    return False
                target = state.objects.get(target_id)
                return target is not None and target.state.divine_shield

            def _divine_shield_handler(event: Event, state: GameState) -> InterceptorResult:
                target_id = event.payload.get("target")
                target = state.objects[target_id]

                # Break the shield
                target.state.divine_shield = False

                # Emit shield break event
                shield_break = Event(
                    type=EventType.DIVINE_SHIELD_BREAK,
                    payload={'target': target_id},
                    source=event.source
                )

                # Prevent the damage
                return InterceptorResult(
                    action=InterceptorAction.PREVENT,
                    new_events=[shield_break]
                )

            self.register_interceptor(
                Interceptor(
                    id=new_id(),
                    source="SYSTEM",
                    controller="SYSTEM",
                    priority=InterceptorPriority.PREVENT,
                    filter=_divine_shield_filter,
                    handler=_divine_shield_handler,
                    duration="forever",
                )
            )

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
        if self.state.game_mode == "hearthstone":
            # Hearthstone: randomize who goes first
            import random
            random.shuffle(player_ids)
        self.turn_manager.set_turn_order(player_ids)

        # Draw starting hands
        if self.state.game_mode == "hearthstone":
            # Hearthstone: Player 1 draws 3, Player 2 draws 4
            for i, player_id in enumerate(player_ids):
                draw_count = 3 if i == 0 else 4
                self.draw_cards(player_id, draw_count)
        else:
            # MTG: London Mulligan
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
            # Move all cards from hand to library, updating per-object zone metadata.
            for oid in hand.objects:
                obj = self.state.objects.get(oid)
                if obj:
                    obj.zone = ZoneType.LIBRARY
                    obj.entered_zone_at = self.state.timestamp

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
                # Library top is index 0 (DRAW pops 0), so bottom is the end.
                library.objects.append(card.id)
                card.zone = ZoneType.LIBRARY
                card.entered_zone_at = self.state.timestamp

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
    # Hearthstone Actions
    # =========================================================================

    async def use_hero_power(self, player_id: str, target_id: str = None) -> bool:
        """
        Use a player's hero power.

        Returns True if successful, False if blocked (insufficient mana,
        already used this turn, etc.)
        """
        player = self.state.players.get(player_id)
        if not player or not player.hero_power_id:
            return False

        # Already used this turn
        if player.hero_power_used:
            return False

        # Determine hero power cost from the hero power object
        hero_power_cost = 2  # default
        hp_obj = self.state.objects.get(player.hero_power_id)
        if hp_obj and hp_obj.characteristics and hp_obj.characteristics.mana_cost:
            import re
            nums = re.findall(r'\{(\d+)\}', hp_obj.characteristics.mana_cost)
            if nums:
                hero_power_cost = max(0, sum(int(n) for n in nums))

        # Not enough mana
        if player.mana_crystals_available < hero_power_cost:
            return False

        # Emit hero power activation event
        payload = {'hero_power_id': player.hero_power_id, 'player': player_id}
        if target_id:
            payload['target'] = target_id

        power_event = Event(
            type=EventType.HERO_POWER_ACTIVATE,
            payload=payload,
            source=player.hero_power_id
        )
        processed = self.pipeline.emit(power_event)

        # Check if the hero power event itself was prevented (not follow-up events)
        if power_event.status == EventStatus.PREVENTED:
            return False

        # Deduct mana and mark as used only after successful activation
        player.mana_crystals_available -= hero_power_cost
        player.hero_power_used = True

        return True

    # =========================================================================
    # Player Setup
    # =========================================================================

    def set_ai_player(self, player_id: str) -> None:
        """Mark a player as AI-controlled."""
        self.priority_system.set_ai_player(player_id)

        # Also register with Hearthstone turn manager if in Hearthstone mode
        if self.state.game_mode == "hearthstone":
            if hasattr(self.turn_manager, 'set_ai_player'):
                self.turn_manager.set_ai_player(player_id)

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

    def set_hearthstone_ai_handler(self, handler) -> None:
        """Set the Hearthstone AI handler for turn execution."""
        if hasattr(self.turn_manager, 'set_ai_handler'):
            self.turn_manager.set_ai_handler(handler)

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
        # create_object appends to the end of the zone list.
        # The draw handler pops from index 0 (top of library).
        # So end-of-list = bottom, beginning-of-list = top.
        library_key = f"library_{player_id}"
        library = self.state.zones.get(library_key)
        if library and position == 'top':
            # Move to top (index 0); create_object placed it at the end (bottom)
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
    # Player Choice System
    # =========================================================================

    def create_choice(
        self,
        choice_type: str,
        player_id: str,
        prompt: str,
        options: list,
        source_id: str,
        min_choices: int = 1,
        max_choices: int = 1,
        callback_data: dict = None
    ) -> PendingChoice:
        """
        Create a pending choice that pauses the game for player input.

        Args:
            choice_type: Type of choice ("modal", "target", "scry", "surveil", "order", "discard")
            player_id: ID of the player who must make the choice
            prompt: Human-readable prompt for the UI
            options: List of valid choices (card IDs, mode indices, etc.)
            source_id: ID of the card/ability requesting the choice
            min_choices: Minimum number of choices required (default 1)
            max_choices: Maximum number of choices allowed (default 1)
            callback_data: Additional data needed to resume after choice

        Returns:
            The created PendingChoice object

        Example usage:
            # Modal spell
            choice = game.create_choice(
                choice_type="modal",
                player_id=controller_id,
                prompt="Choose one:",
                options=[
                    {"index": 0, "text": "Target creature gets +2/+2"},
                    {"index": 1, "text": "Target creature gets flying"}
                ],
                source_id=spell_id,
                min_choices=1,
                max_choices=1
            )

            # Scry 2
            choice = game.create_choice(
                choice_type="scry",
                player_id=controller_id,
                prompt="Scry 2 - choose cards to put on bottom",
                options=top_card_ids,  # IDs of cards being scryed
                source_id=source_id,
                min_choices=0,
                max_choices=2,
                callback_data={"scry_count": 2}
            )
        """
        if self.state.pending_choice is not None:
            raise ValueError("Cannot create choice while another choice is pending")

        choice = PendingChoice(
            choice_type=choice_type,
            player=player_id,
            prompt=prompt,
            options=options,
            source_id=source_id,
            min_choices=min_choices,
            max_choices=max_choices,
            callback_data=callback_data or {}
        )

        self.state.pending_choice = choice
        return choice

    def submit_choice(self, choice_id: str, player_id: str, selected: list) -> tuple[bool, str, list[Event]]:
        """
        Submit a player's choice and continue game resolution.

        Args:
            choice_id: ID of the pending choice being answered
            player_id: ID of the player submitting the choice
            selected: List of selected options

        Returns:
            (success, error_message, resulting_events)
        """
        choice = self.state.pending_choice
        if choice is None:
            return False, "No pending choice", []

        if choice.id != choice_id:
            return False, f"Choice ID mismatch: expected {choice.id}", []

        if choice.player != player_id:
            return False, f"Not your choice to make", []

        # Validate the selection
        is_valid, error = choice.validate_selection(selected)
        if not is_valid:
            return False, error, []

        # Clear the pending choice
        self.state.pending_choice = None

        # Process the choice based on type
        events = self._process_choice(choice, selected)

        # Emit all resulting events through the pipeline
        # This ensures effects like damage, destroy, etc. actually happen
        all_processed = []
        for event in events:
            processed = self.emit(event)
            all_processed.extend(processed)

        return True, "", all_processed

    def _process_choice(self, choice: PendingChoice, selected: list) -> list[Event]:
        """
        Process a completed choice and return resulting events.

        This is the core dispatch for different choice types.
        """
        events: list[Event] = []

        # Some choices include an explicit handler (closures from card scripts,
        # engine systems like TARGET_REQUIRED, etc.). Prefer it over the built-in
        # choice_type dispatch so custom behavior works even for standard types
        # like "target"/"discard"/"sacrifice".
        #
        # Exception: divide_allocation has a special input format that we normalize
        # before calling the handler.
        if choice.choice_type == "divide_allocation":
            return self._process_divide_allocation_choice(choice, selected)

        # modal_with_targeting also needs special handling.
        if choice.choice_type == "modal_with_targeting":
            return self._process_modal_with_targeting_choice(choice, selected)

        handler = choice.callback_data.get('handler')
        if handler:
            return handler(choice, selected, self.state)

        if choice.choice_type == "modal":
            # Modal spell - selected contains mode indices
            events = self._process_modal_choice(choice, selected)

        elif choice.choice_type == "target":
            # Target selection - selected contains target IDs
            events = self._process_target_choice(choice, selected)

        elif choice.choice_type == "scry":
            # Scry - selected contains card IDs to put on bottom
            events = self._process_scry_choice(choice, selected)

        elif choice.choice_type == "surveil":
            # Surveil - selected contains card IDs to put in graveyard
            events = self._process_surveil_choice(choice, selected)

        elif choice.choice_type == "order":
            # Order cards - selected is the ordered list
            events = self._process_order_choice(choice, selected)

        elif choice.choice_type == "discard":
            # Discard - selected contains card IDs to discard
            events = self._process_discard_choice(choice, selected)

        elif choice.choice_type == "sacrifice":
            # Sacrifice - selected contains permanent IDs to sacrifice
            events = self._process_sacrifice_choice(choice, selected)

        elif choice.choice_type == "may":
            # "You may" - selected is [True] or [False]
            events = self._process_may_choice(choice, selected)

        return events

    def _process_modal_choice(self, choice: PendingChoice, selected: list) -> list[Event]:
        """Process a modal spell choice."""
        # Store the selected modes in callback_data for the spell's resolve function
        # The actual effect happens when the spell resolves
        callback_data = choice.callback_data
        callback_data['selected_modes'] = selected
        return []  # Modal choice just stores selection, spell handles resolution

    def _process_target_choice(self, choice: PendingChoice, selected: list) -> list[Event]:
        """Process target selection."""
        # Store targets for the spell/ability to use
        callback_data = choice.callback_data
        callback_data['selected_targets'] = selected
        return []

    def _process_scry_choice(self, choice: PendingChoice, selected: list) -> list[Event]:
        """
        Process scry choice - put selected cards on bottom, rest stay on top.

        selected: card IDs to put on bottom
        """
        player_id = choice.player
        library_key = f"library_{player_id}"
        library = self.state.zones.get(library_key)

        if not library:
            return []

        scry_count = choice.callback_data.get('scry_count', len(choice.options))
        # Be robust: only reorder cards that are still in the library.
        cards_being_scryed = [
            cid for cid in choice.options[:scry_count]
            if cid in library.objects
        ]

        # Cards to put on bottom (in order selected)
        bottom_cards = [cid for cid in selected if cid in cards_being_scryed]

        # Cards to keep on top (original order)
        top_cards = [cid for cid in cards_being_scryed if cid not in bottom_cards]

        # Rebuild library: top cards at index 0 (top), then rest, then bottom cards at end
        # Library convention: index 0 = top (drawn first), last index = bottom (drawn last)
        new_library = []

        # Add top cards first (they'll be on top - drawn first)
        new_library.extend(top_cards)

        # Add remaining library cards (excluding scryed cards)
        for cid in library.objects:
            if cid not in cards_being_scryed:
                new_library.append(cid)

        # Add bottom cards last (they'll be at the bottom - drawn last)
        new_library.extend(bottom_cards)

        library.objects = new_library

        return [Event(
            type=EventType.SCRY,
            payload={
                'player': player_id,
                'count': scry_count,
                'to_bottom': len(bottom_cards),
                'to_top': len(top_cards)
            },
            source=choice.source_id
        )]

    def _process_surveil_choice(self, choice: PendingChoice, selected: list) -> list[Event]:
        """
        Process surveil choice - put selected cards in graveyard, rest on top.

        selected: card IDs to put in graveyard
        """
        player_id = choice.player
        library_key = f"library_{player_id}"
        graveyard_key = f"graveyard_{player_id}"

        library = self.state.zones.get(library_key)
        graveyard = self.state.zones.get(graveyard_key)

        if not library or not graveyard:
            return []

        surveil_count = choice.callback_data.get('surveil_count', len(choice.options))
        cards_being_surveiled = choice.options[:surveil_count]

        # Cards to put in graveyard
        graveyard_cards = [cid for cid in selected if cid in cards_being_surveiled]

        # Cards to keep on top
        top_cards = [cid for cid in cards_being_surveiled if cid not in graveyard_cards]

        # Move graveyard cards
        for cid in graveyard_cards:
            if cid in library.objects:
                library.objects.remove(cid)
                graveyard.objects.append(cid)
                # Update object zone
                obj = self.state.objects.get(cid)
                if obj:
                    obj.zone = ZoneType.GRAVEYARD

        # Ensure top cards are at the top of library (index 0 = top)
        # Insert in reverse order so they maintain their original relative order at the top
        for cid in reversed(top_cards):
            if cid in library.objects:
                library.objects.remove(cid)
                library.objects.insert(0, cid)

        return [Event(
            type=EventType.SURVEIL,
            payload={
                'player': player_id,
                'count': surveil_count,
                'to_graveyard': len(graveyard_cards),
                'to_top': len(top_cards)
            },
            source=choice.source_id
        )]

    def _process_order_choice(self, choice: PendingChoice, selected: list) -> list[Event]:
        """
        Process card ordering choice (e.g., for putting cards on top in specific order).

        selected: ordered list of card IDs
        """
        # The callback_data should specify where these cards go
        destination = choice.callback_data.get('destination', 'library_top')
        player_id = choice.player

        if destination == 'library_top':
            library_key = f"library_{player_id}"
            library = self.state.zones.get(library_key)
            if library:
                # Only operate on cards that are actually in the library to avoid
                # corrupting zone bookkeeping.
                ordered = [cid for cid in selected if cid in library.objects]
                # Remove cards from their current position
                for cid in ordered:
                    if cid in library.objects:
                        library.objects.remove(cid)
                # Add in order (first selected = deepest, last = top)
                library.objects.extend(ordered)

        return []

    def _process_discard_choice(self, choice: PendingChoice, selected: list) -> list[Event]:
        """Process discard choice."""
        events = []
        for card_id in selected:
            events.append(Event(
                type=EventType.DISCARD,
                payload={
                    'player': choice.player,
                    'object_id': card_id
                },
                source=choice.source_id
            ))
        return events

    def _process_sacrifice_choice(self, choice: PendingChoice, selected: list) -> list[Event]:
        """Process sacrifice choice."""
        events = []
        for permanent_id in selected:
            events.append(Event(
                type=EventType.SACRIFICE,
                payload={
                    'player': choice.player,
                    'object_id': permanent_id
                },
                source=choice.source_id
            ))
        return events

    def _process_may_choice(self, choice: PendingChoice, selected: list) -> list[Event]:
        """Process a 'you may' choice."""
        # selected should be [True] or [False]
        chose_yes = selected and selected[0] is True

        if chose_yes and 'yes_handler' in choice.callback_data:
            handler = choice.callback_data['yes_handler']
            return handler(choice, self.state)

        if not chose_yes and 'no_handler' in choice.callback_data:
            handler = choice.callback_data['no_handler']
            return handler(choice, self.state)

        return []

    def _process_divide_allocation_choice(self, choice: PendingChoice, selected: list) -> list[Event]:
        """
        Process a divide_allocation choice.

        Args:
            selected: For divide_allocation, this should be a dict mapping target_id -> amount,
                      or a list of (target_id, amount) tuples.
        """
        # Normalize input - could be dict or list of tuples
        if isinstance(selected, dict):
            allocations = selected
        elif isinstance(selected, list) and len(selected) > 0:
            if isinstance(selected[0], tuple):
                allocations = dict(selected)
            elif isinstance(selected[0], dict):
                # List of {target_id: ..., amount: ...} dicts
                allocations = {item.get('target_id') or item.get('id'): item.get('amount', 0)
                               for item in selected}
            else:
                # Fallback: assume it's already a dict
                allocations = selected[0] if isinstance(selected[0], dict) else {}
        else:
            return []

        # Use the handler from callback_data
        handler = choice.callback_data.get('handler')
        if handler:
            return handler(choice, allocations, self.state)

        return []

    def _process_modal_with_targeting_choice(self, choice: PendingChoice, selected: list) -> list[Event]:
        """
        Process a modal_with_targeting choice.

        After mode selection, creates TARGET_REQUIRED events for modes that need targeting,
        or executes non-targeting modes directly.

        Args:
            selected: List of selected mode indices
        """
        modes = choice.callback_data.get('modes', [])
        source_id = choice.source_id

        events = []

        for mode_idx in selected:
            # Convert string index to int (choices come as strings)
            mode_idx = int(mode_idx)
            if mode_idx < 0 or mode_idx >= len(modes):
                continue

            mode = modes[mode_idx]

            if mode.get('requires_targeting'):
                # Create TARGET_REQUIRED for this mode
                events.append(Event(
                    type=EventType.TARGET_REQUIRED,
                    payload={
                        'source': source_id,
                        'controller': choice.player,
                        'effect': mode.get('effect'),
                        'effect_params': mode.get('effect_params', {}),
                        'effects': mode.get('effects'),  # For multi-effect modes
                        'target_filter': mode.get('target_filter', 'any'),
                        'min_targets': mode.get('min_targets', 1),
                        'max_targets': mode.get('max_targets', 1),
                        'optional': mode.get('optional', False),
                        'prompt': mode.get('text')
                    },
                    source=source_id
                ))
            else:
                # Non-targeting mode - execute directly
                mode_events = self._execute_mode_effect(mode, source_id, choice.player)
                events.extend(mode_events)

        return events

    def _execute_mode_effect(self, mode: dict, source_id: str, controller: str = None) -> list[Event]:
        """Execute a non-targeting mode effect directly."""
        effect = mode.get('effect')
        params = mode.get('effect_params', {})
        player_id = mode.get('controller') or controller or self.state.active_player

        events = []

        if effect == 'draw':
            amount = params.get('amount', 1)
            events.append(Event(
                type=EventType.DRAW,
                payload={'player': player_id, 'amount': amount},
                source=source_id
            ))

        elif effect == 'life_gain':
            amount = params.get('amount', 0)
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': player_id, 'amount': amount},
                source=source_id
            ))

        elif effect == 'create_token':
            token = params.get('token', {})
            count = params.get('count', 1)
            events.append(Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': player_id,
                    'token': token,
                    'count': count
                },
                source=source_id
            ))

        elif effect == 'mill':
            amount = params.get('amount', 1)
            target_player = params.get('target_player', player_id)
            events.append(Event(
                type=EventType.MILL,
                payload={'player': target_player, 'amount': amount},
                source=source_id
            ))

        elif effect == 'scry':
            amount = params.get('amount', 1)
            events.append(Event(
                type=EventType.SCRY,
                payload={'player': player_id, 'amount': amount, 'source_id': source_id},
                source=source_id
            ))

        return events

    def has_pending_choice(self) -> bool:
        """Check if the game is waiting for a player choice."""
        return self.state.has_pending_choice()

    def get_pending_choice(self) -> Optional[PendingChoice]:
        """Get the current pending choice, if any."""
        return self.state.pending_choice

    def get_pending_choice_for_player(self, player_id: str) -> Optional[PendingChoice]:
        """Get the pending choice if it's for this player."""
        return self.state.get_pending_choice_for_player(player_id)

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
            'pending_choice': self._serialize_pending_choice(player_id),
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

    def _serialize_pending_choice(self, player_id: Optional[str]) -> Optional[dict]:
        """Serialize pending choice for the client."""
        choice = self.state.pending_choice
        if not choice:
            return None

        # Only show full choice details to the player who needs to make it
        if player_id != choice.player:
            return {
                'waiting_for': choice.player,
                'choice_type': choice.choice_type,
            }

        result = {
            'id': choice.id,
            'choice_type': choice.choice_type,
            'player': choice.player,
            'prompt': choice.prompt,
            'options': choice.options,
            'source_id': choice.source_id,
            'min_choices': choice.min_choices,
            'max_choices': choice.max_choices,
        }

        # Add divide_allocation-specific data
        if choice.choice_type == "divide_allocation":
            result['total_amount'] = choice.callback_data.get('total_amount', 0)
            result['effect_type'] = choice.callback_data.get('effect', 'damage')

        # Add modal_with_targeting-specific data
        if choice.choice_type == "modal_with_targeting":
            result['modes'] = choice.callback_data.get('modes', [])

        return result


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
    rarity: str = None,
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
        rarity=rarity,
        abilities=abilities or [],
        setup_interceptors=setup_interceptors
    )


def make_instant(
    name: str,
    mana_cost: str = "",
    colors: set = None,
    text: str = "",
    rarity: str = None,
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
        rarity=rarity,
        abilities=abilities or [],
        resolve=resolve
    )


def make_spell(
    name: str,
    mana_cost: str = "",
    colors: set = None,
    text: str = "",
    rarity: str = None,
    spell_effect = None,
    requires_target: bool = False
) -> 'CardDefinition':
    """
    Helper to create Hearthstone spell card definitions.

    Args:
        name: Card name
        mana_cost: Mana cost (e.g., "{3}")
        colors: Set of colors
        text: Card text
        rarity: Card rarity
        spell_effect: Function(obj, state, targets) -> list[Event]
        requires_target: Whether spell requires a target
    """
    from .types import CardDefinition, Characteristics

    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.SPELL},
            colors=colors or set(),
            mana_cost=mana_cost
        ),
        text=text,
        rarity=rarity,
        spell_effect=spell_effect,
        requires_target=requires_target,
        domain="HEARTHSTONE"
    )


def make_enchantment(
    name: str,
    mana_cost: str = "",
    colors: set = None,
    subtypes: set = None,
    supertypes: set = None,
    text: str = "",
    rarity: str = None,
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
        rarity=rarity,
        abilities=abilities or [],
        setup_interceptors=setup_interceptors
    )


def make_sorcery(
    name: str,
    mana_cost: str = "",
    colors: set = None,
    text: str = "",
    rarity: str = None,
    abilities: list = None,
    resolve = None
) -> 'CardDefinition':
    """Helper to create sorcery card definitions."""
    from .types import CardDefinition, Characteristics

    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.SORCERY},
            colors=colors or set(),
            mana_cost=mana_cost
        ),
        text=text,
        rarity=rarity,
        abilities=abilities or [],
        resolve=resolve
    )


def make_artifact(
    name: str,
    mana_cost: str = "",
    text: str = "",
    subtypes: set = None,
    supertypes: set = None,
    rarity: str = None,
    abilities: list = None,
    setup_interceptors = None,
    power: int = None,
    toughness: int = None,
    colors: set = None
) -> 'CardDefinition':
    """Helper to create artifact card definitions.

    For Vehicles, pass power/toughness which will be used when crewed.
    """
    from .types import CardDefinition, Characteristics

    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors or set(),
            mana_cost=mana_cost,
            power=power,
            toughness=toughness
        ),
        text=text,
        rarity=rarity,
        abilities=abilities or [],
        setup_interceptors=setup_interceptors
    )


def make_land(
    name: str,
    text: str = "",
    subtypes: set = None,
    supertypes: set = None,
    rarity: str = None,
    abilities: list = None,
    setup_interceptors = None
) -> 'CardDefinition':
    """Helper to create land card definitions."""
    from .types import CardDefinition, Characteristics

    return CardDefinition(
        name=name,
        mana_cost=None,
        characteristics=Characteristics(
            types={CardType.LAND},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=set(),
            mana_cost=None
        ),
        text=text,
        rarity=rarity,
        abilities=abilities or [],
        setup_interceptors=setup_interceptors
    )


def make_planeswalker(
    name: str,
    mana_cost: str,
    colors: set,
    loyalty: int,
    text: str = "",
    subtypes: set = None,
    rarity: str = None,
    abilities: list = None,
    setup_interceptors = None
) -> 'CardDefinition':
    """Helper to create planeswalker card definitions."""
    from .types import CardDefinition, Characteristics

    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.PLANESWALKER},
            subtypes=subtypes or set(),
            colors=colors or set(),
            mana_cost=mana_cost,
            abilities=[{'loyalty': loyalty}]  # Store starting loyalty
        ),
        text=text,
        rarity=rarity,
        abilities=abilities or [],
        setup_interceptors=setup_interceptors
    )


# =============================================================================
# Hearthstone Card Factories
# =============================================================================

def make_hero(
    name: str,
    hero_class: str,
    starting_life: int = 30,
    text: str = "",
    rarity: str = None,
    setup_interceptors = None
) -> 'CardDefinition':
    """
    Create a Hearthstone hero card.

    Args:
        name: Hero name
        hero_class: Hero class (e.g., "Mage", "Warrior", "Hunter")
        starting_life: Starting health (default 30)
        text: Hero card text
        rarity: Rarity string
        setup_interceptors: Optional setup function for hero effects
    """
    from .types import CardDefinition, Characteristics

    return CardDefinition(
        name=name,
        mana_cost=None,
        characteristics=Characteristics(
            types={CardType.HERO},
            subtypes={hero_class},
            toughness=starting_life  # Use toughness for hero health
        ),
        text=text,
        rarity=rarity,
        abilities=[],
        setup_interceptors=setup_interceptors,
        domain="HEARTHSTONE"
    )


def make_hero_power(
    name: str,
    cost: int = 2,
    text: str = "",
    effect = None,
    setup_interceptors = None
) -> 'CardDefinition':
    """
    Create a Hearthstone hero power card.

    Args:
        name: Hero power name
        cost: Mana cost (default 2)
        text: Hero power description
        effect: Function called when activated: (obj: GameObject, state: GameState) -> list[Event]
        setup_interceptors: Optional setup function for complex hero powers
    """
    from .types import CardDefinition, Characteristics

    # Create setup function that handles hero power activation
    def hero_power_setup(obj: 'GameObject', state: 'GameState') -> list['Interceptor']:
        from .types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, Event, EventType

        if not effect and not setup_interceptors:
            return []

        # If custom setup provided, use it
        if setup_interceptors:
            return setup_interceptors(obj, state)

        # Standard hero power interceptor
        def filter_fn(event: Event, s: 'GameState') -> bool:
            return (
                event.type == EventType.HERO_POWER_ACTIVATE and
                event.payload.get('hero_power_id') == obj.id
            )

        def handler_fn(event: Event, s: 'GameState') -> 'InterceptorResult':
            # Check if already used this turn
            player = s.players.get(obj.controller)
            if player and player.hero_power_used:
                return InterceptorResult(action=InterceptorAction.PREVENT)

            # Check mana cost
            # (Mana check should be done before emitting this event)

            # Note: hero_power_used is marked by use_hero_power() after emit()
            # to avoid double-marking when both interceptor and caller set it.

            # Execute effect
            new_events = effect(obj, s) if effect else []

            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=new_events
            )

        return [Interceptor(
            id=f"hero_power_{obj.id}",
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=filter_fn,
            handler=handler_fn,
            duration='permanent'  # Hero powers are in command zone, not battlefield
        )]

    return CardDefinition(
        name=name,
        mana_cost=f"{{{cost}}}",  # Store as mana cost string
        characteristics=Characteristics(
            types={CardType.HERO_POWER},
            mana_cost=f"{{{cost}}}"
        ),
        text=text,
        abilities=[],
        setup_interceptors=hero_power_setup,
        domain="HEARTHSTONE"
    )


def make_weapon(
    name: str,
    attack: int,
    durability: int,
    mana_cost: str = "",
    text: str = "",
    rarity: str = None,
    abilities: list = None,
    setup_interceptors = None
) -> 'CardDefinition':
    """
    Create a Hearthstone weapon card.

    Args:
        name: Weapon name
        attack: Weapon attack value
        durability: Weapon durability
        mana_cost: Mana cost string
        text: Weapon card text
        rarity: Rarity string
        abilities: List of keyword abilities
        setup_interceptors: Optional setup function
    """
    from .types import CardDefinition, Characteristics

    # Auto-equip weapon on ETB
    def weapon_setup(obj: 'GameObject', state: 'GameState') -> list['Interceptor']:
        from .types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, Event, EventType, ZoneType

        interceptors = []

        # Add custom interceptors if provided
        if setup_interceptors:
            interceptors.extend(setup_interceptors(obj, state))

        # Equip on ETB
        def equip_filter(event: Event, s: 'GameState') -> bool:
            return (
                event.type == EventType.ZONE_CHANGE and
                event.payload.get('object_id') == obj.id and
                event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD
            )

        def equip_handler(event: Event, s: 'GameState') -> 'InterceptorResult':
            # Find hero and player
            player = s.players.get(obj.controller)
            if player and player.hero_id:
                # Collect old weapon cards to destroy via pipeline
                destroy_events = []
                battlefield = s.zones.get('battlefield')
                if battlefield:
                    for card_id in list(battlefield.objects):
                        if card_id == obj.id:
                            continue  # Don't destroy self
                        card = s.objects.get(card_id)
                        if (card and card.controller == obj.controller and
                                CardType.WEAPON in card.characteristics.types):
                            destroy_events.append(Event(
                                type=EventType.OBJECT_DESTROYED,
                                payload={'object_id': card_id, 'reason': 'weapon_replaced'},
                                source=obj.id
                            ))

                # Set weapon stats on PLAYER (where combat manager checks)
                player.weapon_attack = attack
                player.weapon_durability = durability

                # Also set on hero object state for consistency
                hero = s.objects.get(player.hero_id)
                if hero:
                    hero.state.weapon_attack = attack
                    hero.state.weapon_durability = durability

                if destroy_events:
                    return InterceptorResult(
                        action=InterceptorAction.REACT,
                        new_events=destroy_events
                    )

            return InterceptorResult(action=InterceptorAction.PASS)

        interceptors.append(Interceptor(
            id=f"weapon_equip_{obj.id}",
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=equip_filter,
            handler=equip_handler,
            duration='while_on_battlefield',
            uses_remaining=1
        ))

        return interceptors

    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.WEAPON},
            power=attack,
            toughness=durability,
            mana_cost=mana_cost
        ),
        text=text,
        rarity=rarity,
        abilities=abilities or [],
        setup_interceptors=weapon_setup,
        domain="HEARTHSTONE"
    )


def make_minion(
    name: str,
    attack: int,
    health: int,
    mana_cost: str = "",
    subtypes: set[str] = None,
    text: str = "",
    rarity: str = None,
    abilities: list = None,
    keywords: set[str] = None,
    battlecry = None,
    deathrattle = None,
    setup_interceptors = None
) -> 'CardDefinition':
    """
    Create a Hearthstone minion card.

    Args:
        name: Minion name
        attack: Attack value
        health: Health value
        mana_cost: Mana cost string
        subtypes: Minion types (e.g., {"Beast", "Murloc"})
        text: Card text
        rarity: Rarity string
        abilities: List of keyword abilities (charge, taunt, etc.)
        keywords: Set of keywords (charge, taunt, divine_shield, etc.)
        battlecry: Function called on ETB: (obj: GameObject, state: GameState) -> list[Event]
        deathrattle: Function called on death: (obj: GameObject, state: GameState) -> list[Event]
        setup_interceptors: Optional custom setup function
    """
    from .types import CardDefinition, Characteristics

    # Combine battlecry/deathrattle with custom setup
    def minion_setup(obj: 'GameObject', state: 'GameState') -> list['Interceptor']:
        from src.cards.interceptor_helpers import make_etb_trigger, make_death_trigger

        interceptors = []

        # Apply keyword states (Hearthstone keywords)
        if keywords:
            if 'divine_shield' in keywords:
                obj.state.divine_shield = True
            if 'stealth' in keywords:
                obj.state.stealth = True
            if 'windfury' in keywords:
                obj.state.windfury = True
            if 'frozen' in keywords:
                obj.state.frozen = True

        # Add battlecry (ETB trigger - only when played from hand)
        if battlecry:
            # Wrap battlecry to convert (obj, state) -> (event, state)
            def battlecry_wrapper(event: Event, state: 'GameState') -> list[Event]:
                return battlecry(obj, state)

            # Battlecries only trigger when played from hand, not when summoned by effects
            def battlecry_filter(event: Event, state: 'GameState', obj: GameObject) -> bool:
                return (event.type == EventType.ZONE_CHANGE and
                        event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD and
                        event.payload.get('from_zone_type') == ZoneType.HAND and
                        event.payload.get('object_id') == obj.id)

            interceptors.append(make_etb_trigger(obj, battlecry_wrapper, filter_fn=battlecry_filter))

        # Add deathrattle (death trigger)
        if deathrattle:
            # Wrap deathrattle to convert (obj, state) -> (event, state)
            def deathrattle_wrapper(event: Event, state: 'GameState') -> list[Event]:
                return deathrattle(obj, state)
            interceptors.append(make_death_trigger(obj, deathrattle_wrapper))

        # Add custom interceptors
        if setup_interceptors:
            interceptors.extend(setup_interceptors(obj, state))

        return interceptors

    # Convert keywords to abilities format
    char_abilities = abilities or []
    if keywords:
        for keyword in keywords:
            char_abilities.append({'keyword': keyword})

    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.MINION},
            subtypes=subtypes or set(),
            power=attack,
            toughness=health,
            mana_cost=mana_cost,
            abilities=char_abilities
        ),
        text=text,
        rarity=rarity,
        abilities=char_abilities,
        battlecry=battlecry,
        deathrattle=deathrattle,
        setup_interceptors=minion_setup if (battlecry or deathrattle or setup_interceptors or keywords) else None,
        domain="HEARTHSTONE"
    )


def make_secret(
    name: str,
    mana_cost: str = "",
    text: str = "",
    trigger_filter = None,
    trigger_effect = None,
    setup_interceptors = None
) -> 'CardDefinition':
    """
    Create a Hearthstone secret card.

    Args:
        name: Secret name
        mana_cost: Mana cost string
        text: Secret description
        trigger_filter: Function determining when secret triggers: (event: Event, state: GameState) -> bool
        trigger_effect: Function called when triggered: (obj: GameObject, state: GameState) -> list[Event]
        setup_interceptors: Optional custom setup function
    """
    from .types import CardDefinition, Characteristics

    def secret_setup(obj: 'GameObject', state: 'GameState') -> list['Interceptor']:
        from .types import Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult, Event, EventType

        if not trigger_filter or not trigger_effect:
            if setup_interceptors:
                return setup_interceptors(obj, state)
            return []

        # Secret interceptor - triggers on opponent's actions
        def filter_fn(event: Event, s: 'GameState') -> bool:
            # Only trigger during opponent's turn
            if s.active_player == obj.controller:
                return False
            return trigger_filter(event, s)

        def handler_fn(event: Event, s: 'GameState') -> 'InterceptorResult':
            # Execute secret effect
            new_events = trigger_effect(obj, s)

            # Destroy the secret after triggering
            from .types import ZoneType
            destroy_event = Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': obj.id,
                    'from_zone_type': obj.zone,
                    'to_zone_type': ZoneType.GRAVEYARD
                },
                source=obj.id
            )
            new_events.append(destroy_event)

            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=new_events
            )

        return [Interceptor(
            id=f"secret_{obj.id}",
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=filter_fn,
            handler=handler_fn,
            duration='while_on_battlefield',
            uses_remaining=1
        )]

    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.SECRET},
            mana_cost=mana_cost
        ),
        text=text,
        abilities=[],
        setup_interceptors=secret_setup,
        domain="HEARTHSTONE"
    )
