"""
Hyperdraft Priority System

Handles the priority system - who can act and when.
Priority determines which player can take actions at any given moment.

Rules:
- Active player gets priority at the start of most steps/phases
- After casting/activating, that player retains priority (rule 116.3c)
- Players can pass priority
- When all players pass with empty stack, phase/step ends
- When all players pass with stack items, top item resolves
"""

from dataclasses import dataclass, field
from typing import Callable, Optional, TYPE_CHECKING, Any
from enum import Enum, auto
import asyncio
import re

from .types import GameState, Event, EventType, CardType, ZoneType
from .stack import StackManager, StackItem, StackItemType
from .mana import ManaSystem, ManaCost, ManaType
from .pipeline import EventPipeline

if TYPE_CHECKING:
    from .turn import TurnManager


class ActionType(Enum):
    """Types of actions a player can take."""
    PASS = auto()              # Pass priority
    CAST_SPELL = auto()        # Cast a spell from hand
    ACTIVATE_ABILITY = auto()  # Activate an ability
    PLAY_LAND = auto()         # Play a land
    SPECIAL_ACTION = auto()    # Special actions (morph, suspend, etc.)
    CAST_ADVENTURE = auto()    # Cast adventure side of a card
    CAST_SPLIT_LEFT = auto()   # Cast left half of split card
    CAST_SPLIT_RIGHT = auto()  # Cast right half of split card
    CREW = auto()              # Crew a Vehicle


@dataclass
class PlayerAction:
    """An action a player wants to take."""
    type: ActionType
    player_id: str

    # For casting spells
    card_id: Optional[str] = None
    targets: list[list] = field(default_factory=list)  # List of target lists per requirement
    x_value: int = 0
    modes: list[int] = field(default_factory=list)

    # For activating abilities
    ability_id: Optional[str] = None
    source_id: Optional[str] = None  # Permanent with the ability

    # Additional data
    data: dict = field(default_factory=dict)


@dataclass
class LegalAction:
    """A legal action available to a player."""
    type: ActionType
    card_id: Optional[str] = None
    ability_id: Optional[str] = None
    source_id: Optional[str] = None
    description: str = ""
    requires_targets: bool = False
    requires_mana: bool = False
    mana_cost: Optional[ManaCost] = None
    crew_cost: int = 0  # Power required to crew (for CREW actions)
    crew_with: list[str] = None  # Creature IDs to use for crewing


class PrioritySystem:
    """
    Manages priority and the main game loop.
    """

    def __init__(self, state: GameState):
        self.state = state

        # Other systems (set by Game class)
        self.stack: Optional[StackManager] = None
        self.turn_manager: Optional['TurnManager'] = None
        self.mana_system: Optional[ManaSystem] = None
        self.pipeline: Optional[EventPipeline] = None

        # Priority state
        self.priority_player: Optional[str] = None
        self.passed_players: set[str] = set()

        # For human players - callback to get their action
        self.get_human_action: Optional[Callable[[str, list[LegalAction]], asyncio.Future]] = None

        # For AI players - callback to get their action
        self.get_ai_action: Optional[Callable[[str, GameState, list[LegalAction]], PlayerAction]] = None

        # Callback invoked after action is processed (for synchronization)
        self.on_action_processed: Optional[Callable[[], None]] = None

        # Player type tracking
        self.ai_players: set[str] = set()
        # Track loyalty activations by permanent per turn.
        self._loyalty_activation_turn: dict[str, int] = {}

        # Action handlers
        self._action_handlers: dict[ActionType, Callable] = {
            ActionType.PASS: self._handle_pass,
            ActionType.CAST_SPELL: self._handle_cast_spell,
            ActionType.ACTIVATE_ABILITY: self._handle_activate_ability,
            ActionType.PLAY_LAND: self._handle_play_land,
            ActionType.SPECIAL_ACTION: self._handle_special_action,
            ActionType.CREW: self._handle_crew,
        }

    def set_ai_player(self, player_id: str) -> None:
        """Mark a player as AI-controlled."""
        self.ai_players.add(player_id)

    def is_ai_player(self, player_id: str) -> bool:
        """Check if a player is AI-controlled."""
        return player_id in self.ai_players

    async def run_priority_loop(self) -> None:
        """
        Main priority loop.

        1. Active player gets priority
        2. Players can act or pass
        3. When all pass with empty stack, proceed
        4. When all pass with stack items, resolve top
        """
        # Check state-based actions before starting
        await self._check_state_based_actions()
        await self._put_triggers_on_stack()

        self.passed_players.clear()
        self.priority_player = self.turn_manager.active_player if self.turn_manager else None

        if not self.priority_player:
            return

        while True:
            # Check SBAs before granting priority
            await self._check_state_based_actions()
            await self._put_triggers_on_stack()

            # Check if game is over
            if self._is_game_over():
                return

            # Get legal actions for current player
            legal_actions = self.get_legal_actions(self.priority_player)

            # Get player action
            action = await self._get_player_action(self.priority_player, legal_actions)

            if action.type == ActionType.PASS:
                self.passed_players.add(self.priority_player)
                # Signal action was processed (for API synchronization)
                if self.on_action_processed:
                    self.on_action_processed()

                if self._all_players_passed():
                    if self.stack and self.stack.is_empty():
                        return  # Phase/step ends
                    else:
                        # Resolve top of stack
                        if self.stack:
                            events = self.stack.resolve_top()
                            for event in events:
                                self._emit_event(event)

                        self.passed_players.clear()
                        self.priority_player = self.turn_manager.active_player if self.turn_manager else None
                        continue
                else:
                    # Next player gets priority
                    self.priority_player = self._get_next_player()
                    continue
            else:
                # Player took an action - reset passes
                self.passed_players.clear()
                await self._execute_action(action)
                # Signal action was processed (for API synchronization)
                if self.on_action_processed:
                    self.on_action_processed()
                # Player retains priority after acting (rule 116.3c)
                continue

    async def _get_player_action(
        self,
        player_id: str,
        legal_actions: list[LegalAction]
    ) -> PlayerAction:
        """Get action from a player (human or AI)."""
        if self.is_ai_player(player_id):
            # AI player
            if self.get_ai_action:
                return self.get_ai_action(player_id, self.state, legal_actions)
            else:
                # Default: pass priority
                return PlayerAction(type=ActionType.PASS, player_id=player_id)
        else:
            # Human player
            if self.get_human_action:
                return await self.get_human_action(player_id, legal_actions)
            else:
                # No handler - auto-pass
                return PlayerAction(type=ActionType.PASS, player_id=player_id)

    def get_legal_actions(self, player_id: str) -> list[LegalAction]:
        """
        Get all legal actions for a player.
        """
        actions = []

        # Can always pass
        actions.append(LegalAction(
            type=ActionType.PASS,
            description="Pass priority"
        ))

        # Check if player can cast spells
        hand_key = f"hand_{player_id}"
        hand = self.state.zones.get(hand_key)

        if hand:
            for card_id in hand.objects:
                card = self.state.objects.get(card_id)
                if card and self._can_cast(card, player_id):
                    cost = ManaCost.parse(card.characteristics.mana_cost or "")
                    actions.append(LegalAction(
                        type=ActionType.CAST_SPELL,
                        card_id=card_id,
                        description=f"Cast {card.name}",
                        requires_mana=not cost.is_free(),
                        mana_cost=cost
                    ))

        # Check if player can play lands
        if self._can_play_land(player_id):
            if hand:
                for card_id in hand.objects:
                    card = self.state.objects.get(card_id)
                    if card and CardType.LAND in card.characteristics.types:
                        actions.append(LegalAction(
                            type=ActionType.PLAY_LAND,
                            card_id=card_id,
                            description=f"Play {card.name}"
                        ))

        # Check for activatable abilities on permanents
        battlefield = self.state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = self.state.objects.get(obj_id)
                if obj and obj.controller == player_id:
                    abilities = self._get_activatable_abilities(obj, player_id)
                    actions.extend(abilities)

            # Check for Vehicles that can be crewed
            crew_actions = self._get_crew_actions(player_id, battlefield)
            actions.extend(crew_actions)

        return actions

    def _can_cast(self, card, player_id: str) -> bool:
        """Check if a player can cast a card."""
        # Check if it's a spell (not a land)
        if CardType.LAND in card.characteristics.types:
            return False

        # Cards without a mana cost cannot be cast (back faces of transform cards, etc.)
        # Note: {0} is a valid free cost, but "" or None means no mana cost defined
        mana_cost_str = card.characteristics.mana_cost
        if not mana_cost_str or mana_cost_str.strip() == "":
            return False

        # Check timing restrictions
        is_instant = CardType.INSTANT in card.characteristics.types
        has_flash = False  # Would check for flash ability

        if not is_instant and not has_flash:
            # Sorcery speed - can only cast during main phase with empty stack
            if self.turn_manager:
                from .turn import Phase
                if self.turn_manager.phase not in [Phase.PRECOMBAT_MAIN, Phase.POSTCOMBAT_MAIN]:
                    return False

            # Check stack is empty
            if self.stack and not self.stack.is_empty():
                return False

            # Must be active player
            if self.turn_manager and self.turn_manager.active_player != player_id:
                return False

        # Check mana cost
        cost = ManaCost.parse(mana_cost_str)
        if self.mana_system and not cost.is_free():
            if not self.mana_system.can_cast(player_id, cost):
                return False

        return True

    def _can_play_land(self, player_id: str) -> bool:
        """Check if a player can play a land."""
        if self.turn_manager:
            return self.turn_manager.can_play_land(player_id)
        return False

    def _get_activatable_abilities(
        self,
        obj,
        player_id: str
    ) -> list[LegalAction]:
        """
        Get activatable abilities on a permanent.

        Current implementation supports:
        - Planeswalker loyalty abilities without explicit targets
        - Tap-for-mana abilities from rules text
        """
        actions: list[LegalAction] = []
        ability_lines = self._get_activated_ability_lines(obj)

        for idx, line in enumerate(ability_lines):
            normalized = line.replace('−', '-').strip()
            lower = normalized.lower()

            # Planeswalker loyalty abilities: +N: ... / -N: ...
            loyalty_match = re.match(r'^([+-]\d+)\s*:\s*(.+)$', normalized)
            if loyalty_match and CardType.PLANESWALKER in obj.characteristics.types:
                current_turn = self.state.turn_number
                if self._loyalty_activation_turn.get(obj.id) == current_turn:
                    # Planeswalkers can activate loyalty abilities only once each turn.
                    continue

                loyalty_cost = int(loyalty_match.group(1))
                effect_text = loyalty_match.group(2).strip()

                # Only surface non-targeted loyalty abilities for now.
                if 'target' in effect_text.lower():
                    continue

                current_loyalty = self._get_current_loyalty(obj)
                if loyalty_cost < 0 and current_loyalty < abs(loyalty_cost):
                    continue

                actions.append(LegalAction(
                    type=ActionType.ACTIVATE_ABILITY,
                    ability_id=f"loyalty:{idx}:{loyalty_cost}",
                    source_id=obj.id,
                    description=f"Activate {obj.name}: {line}"
                ))
                continue

            # Basic mana abilities from text: "{T}: Add {R}" etc.
            if '{t}' in lower and 'add' in lower:
                if obj.state.tapped:
                    continue
                if (CardType.CREATURE in obj.characteristics.types and
                    getattr(obj, 'summoning_sickness', False)):
                    # Creatures with summoning sickness can't use tap abilities.
                    continue

                actions.append(LegalAction(
                    type=ActionType.ACTIVATE_ABILITY,
                    ability_id=f"mana:{idx}",
                    source_id=obj.id,
                    description=f"Activate {obj.name}: {line}"
                ))

        return actions

    def _get_activated_ability_lines(self, obj) -> list[str]:
        """Extract likely activated-ability lines from card rules text."""
        if not obj or not obj.card_def or not obj.card_def.text:
            return []

        lines = []
        for raw_line in obj.card_def.text.splitlines():
            line = raw_line.strip()
            if not line or ':' not in line:
                continue
            if (
                line.startswith('{') or
                line.startswith('+') or
                line.startswith('-') or
                line.startswith('−') or
                '{T}:' in line
            ):
                lines.append(line)
        return lines

    def _get_current_loyalty(self, obj) -> int:
        """Get current loyalty for a planeswalker, with a text fallback."""
        if 'loyalty' in obj.state.counters:
            return obj.state.counters['loyalty']

        text = obj.card_def.text if obj.card_def and obj.card_def.text else ""
        match = re.search(r'\[loyalty:\s*(\d+)\]', text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return 0

    def _parse_mana_symbols(self, ability_text: str) -> list[str]:
        """Parse explicit mana symbols from an activated ability line."""
        if ':' not in ability_text:
            return []
        add_text = ability_text.split(':', 1)[1]
        return re.findall(r'\{([WUBRGC])\}', add_text)

    def _resolve_simple_non_target_ability(
        self,
        ability_text: str,
        source_id: str,
        player_id: str
    ) -> list[Event]:
        """
        Resolve simple non-targeted activated effects from text.

        This intentionally handles only a small safe subset.
        """
        text = ability_text.lower()
        events: list[Event] = []

        # Surveil N
        surveil_match = re.search(r'surveil (\d+)', text)
        if surveil_match:
            events.append(Event(
                type=EventType.SURVEIL,
                payload={'player': player_id, 'amount': int(surveil_match.group(1))},
                source=source_id
            ))

        # Scry N
        scry_match = re.search(r'scry (\d+)', text)
        if scry_match:
            events.append(Event(
                type=EventType.SCRY,
                payload={'player': player_id, 'amount': int(scry_match.group(1))},
                source=source_id
            ))

        # Draw cards
        draw_match = re.search(r'draw (\d+|a|an) cards?', text)
        if draw_match:
            amount_str = draw_match.group(1)
            amount = 1 if amount_str in ('a', 'an') else int(amount_str)
            events.append(Event(
                type=EventType.DRAW,
                payload={'player': player_id, 'count': amount},
                source=source_id
            ))

        return events

    def _get_crew_actions(self, player_id: str, battlefield) -> list[LegalAction]:
        """Get all valid crew actions for Vehicles."""
        from .queries import get_power

        actions = []

        # Find all Vehicles controlled by player
        vehicles = []
        for obj_id in battlefield.objects:
            obj = self.state.objects.get(obj_id)
            if (obj and obj.controller == player_id and
                'Vehicle' in obj.characteristics.subtypes and
                CardType.CREATURE not in obj.characteristics.types):  # Not already a creature
                # Parse crew cost from text or abilities
                crew_cost = self._get_crew_cost(obj)
                if crew_cost is not None:
                    vehicles.append((obj, crew_cost))

        if not vehicles:
            return actions

        # Find all untapped creatures that can crew
        available_crew = []
        for obj_id in battlefield.objects:
            obj = self.state.objects.get(obj_id)
            if (obj and obj.controller == player_id and
                CardType.CREATURE in obj.characteristics.types and
                not obj.state.tapped):
                power = get_power(obj, self.state)
                available_crew.append((obj, power))

        if not available_crew:
            return actions

        # For each vehicle, check if we have enough power to crew it
        for vehicle, crew_cost in vehicles:
            total_power = sum(p for _, p in available_crew)
            if total_power >= crew_cost:
                # Generate a simple crew option using minimum creatures needed
                crew_with = []
                power_used = 0
                for creature, power in sorted(available_crew, key=lambda x: -x[1]):  # Highest power first
                    if power_used >= crew_cost:
                        break
                    crew_with.append(creature.id)
                    power_used += power

                if power_used >= crew_cost:
                    actions.append(LegalAction(
                        type=ActionType.CREW,
                        card_id=vehicle.id,
                        description=f"Crew {vehicle.name} (power {crew_cost})",
                        crew_cost=crew_cost,
                        crew_with=crew_with
                    ))

        return actions

    def _get_crew_cost(self, vehicle) -> int:
        """Extract crew cost from a Vehicle's text or abilities."""
        # Check text for "Crew N" pattern
        text = getattr(vehicle, 'card_def', None)
        if text and hasattr(text, 'text'):
            text = text.text
        else:
            text = ""

        import re
        match = re.search(r'Crew (\d+)', text, re.IGNORECASE)
        if match:
            return int(match.group(1))

        # Check abilities
        for ability in vehicle.characteristics.abilities:
            if isinstance(ability, dict):
                keyword = ability.get('keyword', '')
                if keyword.lower().startswith('crew'):
                    # Try to extract number from "Crew 2" format
                    match = re.search(r'crew\s*(\d+)', keyword, re.IGNORECASE)
                    if match:
                        return int(match.group(1))

        # Default crew cost if Vehicle but no explicit cost found
        return 2

    async def _execute_action(self, action: PlayerAction) -> list[Event]:
        """Execute a player action."""
        handler = self._action_handlers.get(action.type)
        if handler:
            events = await handler(action)
            # Emit each event through the pipeline to actually apply changes
            if self.pipeline:
                for event in events:
                    self.pipeline.emit(event)
            return events
        return []

    async def _handle_pass(self, action: PlayerAction) -> list[Event]:
        """Handle passing priority."""
        return []

    async def _handle_cast_spell(self, action: PlayerAction) -> list[Event]:
        """Handle casting a spell."""
        events = []

        card = self.state.objects.get(action.card_id)
        if not card:
            return events

        # Pay mana cost
        cost = ManaCost.parse(card.characteristics.mana_cost or "")
        if self.mana_system and not cost.is_free():
            self.mana_system.pay_cost(action.player_id, cost, action.x_value)

        # Create stack item
        if self.stack:
            from .stack import SpellBuilder
            builder = SpellBuilder(self.state, self.stack)
            item = builder.cast_spell(
                card_id=action.card_id,
                controller_id=action.player_id,
                targets=action.targets,
                x_value=action.x_value,
                modes=action.modes
            )
            self.stack.push(item)

        events.append(Event(
            type=EventType.CAST,
            payload={
                # Canonical spell-cast payload (used by spell-cast triggers).
                'spell_id': action.card_id,
                'card_id': action.card_id,
                'caster': action.player_id,
                'controller': action.player_id,
                'types': list(card.characteristics.types),
                'colors': list(card.characteristics.colors),
                'mana_value': cost.mana_value,
            }
        ))

        return events

    async def _handle_activate_ability(self, action: PlayerAction) -> list[Event]:
        """Handle activating an ability."""
        events = []
        source = self.state.objects.get(action.source_id) if action.source_id else None

        if source and action.ability_id:
            # Loyalty ability path.
            if action.ability_id.startswith("loyalty:"):
                parts = action.ability_id.split(":")
                if len(parts) >= 3:
                    try:
                        current_turn = self.state.turn_number
                        if self._loyalty_activation_turn.get(source.id) == current_turn:
                            # Enforce one loyalty activation per permanent per turn.
                            return []

                        line_idx = int(parts[1])
                        loyalty_delta = int(parts[2])
                        lines = self._get_activated_ability_lines(source)
                        ability_line = lines[line_idx] if 0 <= line_idx < len(lines) else ""
                        effect_text = ability_line.split(":", 1)[1].strip() if ":" in ability_line else ""

                        current = self._get_current_loyalty(source)
                        source.state.counters['loyalty'] = current + loyalty_delta

                        if loyalty_delta >= 0:
                            events.append(Event(
                                type=EventType.COUNTER_ADDED,
                                payload={
                                    'object_id': source.id,
                                    'counter_type': 'loyalty',
                                    'amount': loyalty_delta
                                },
                                source=source.id
                            ))
                        else:
                            events.append(Event(
                                type=EventType.COUNTER_REMOVED,
                                payload={
                                    'object_id': source.id,
                                    'counter_type': 'loyalty',
                                    'amount': abs(loyalty_delta)
                                },
                                source=source.id
                            ))

                        # Resolve a safe subset of non-targeted loyalty effects.
                        if effect_text and "target" not in effect_text.lower():
                            events.extend(self._resolve_simple_non_target_ability(
                                ability_text=effect_text,
                                source_id=source.id,
                                player_id=action.player_id
                            ))

                        # Record turn after successful loyalty activation.
                        self._loyalty_activation_turn[source.id] = current_turn
                    except ValueError:
                        pass

            # Basic mana ability path.
            elif action.ability_id.startswith("mana:"):
                parts = action.ability_id.split(":")
                if len(parts) >= 2:
                    try:
                        line_idx = int(parts[1])
                        lines = self._get_activated_ability_lines(source)
                        ability_line = lines[line_idx] if 0 <= line_idx < len(lines) else ""

                        if '{T}' in ability_line and not source.state.tapped:
                            events.append(Event(
                                type=EventType.TAP,
                                payload={'object_id': source.id},
                                source=source.id,
                                controller=action.player_id
                            ))

                        mana_symbols = self._parse_mana_symbols(ability_line)
                        symbol_to_type = {
                            'W': ManaType.WHITE,
                            'U': ManaType.BLUE,
                            'B': ManaType.BLACK,
                            'R': ManaType.RED,
                            'G': ManaType.GREEN,
                            'C': ManaType.COLORLESS,
                        }
                        for symbol in mana_symbols:
                            mana_type = symbol_to_type.get(symbol)
                            if mana_type and self.mana_system:
                                self.mana_system.produce_mana(action.player_id, mana_type, 1)
                                events.append(Event(
                                    type=EventType.MANA_PRODUCED,
                                    payload={
                                        'player': action.player_id,
                                        'color': mana_type.value,
                                        'amount': 1
                                    },
                                    source=source.id,
                                    controller=action.player_id
                                ))
                    except ValueError:
                        pass

        # Generic fallback for unknown activated abilities - still put on stack.
        if not events and self.stack:
            item = StackItem(
                id="",
                type=StackItemType.ACTIVATED_ABILITY,
                source_id=action.source_id,
                controller_id=action.player_id,
                chosen_targets=action.targets
            )
            self.stack.push(item)

        events.append(Event(
            type=EventType.ACTIVATE,
            payload={
                'source_id': action.source_id,
                'ability_id': action.ability_id,
                'controller': action.player_id
            }
        ))

        return events

    async def _handle_play_land(self, action: PlayerAction) -> list[Event]:
        """Handle playing a land."""
        events = []

        card = self.state.objects.get(action.card_id)
        if not card:
            return events

        # Move land from hand to battlefield
        events.append(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': action.card_id,
                'from_zone': f'hand_{action.player_id}',
                'to_zone': 'battlefield',
                'to_zone_type': ZoneType.BATTLEFIELD
            }
        ))

        # Record land play
        if self.turn_manager:
            self.turn_manager.play_land()

        return events

    async def _handle_special_action(self, action: PlayerAction) -> list[Event]:
        """Handle special actions (morph, suspend, etc.)."""
        # Special actions don't use the stack
        return []

    async def _handle_crew(self, action: PlayerAction) -> list[Event]:
        """Handle crewing a Vehicle."""
        events = []

        vehicle = self.state.objects.get(action.card_id)
        if not vehicle:
            return events

        # Get crew data from action
        crew_with = action.data.get('crew_with', [])

        # Tap the creatures used to crew
        for creature_id in crew_with:
            creature = self.state.objects.get(creature_id)
            if creature and not creature.state.tapped:
                events.append(Event(
                    type=EventType.TAP,
                    payload={'object_id': creature_id},
                    source=vehicle.id,
                    controller=action.player_id
                ))

        # Mark vehicle as crewed (becomes a creature until end of turn)
        if CardType.CREATURE not in vehicle.characteristics.types:
            vehicle.characteristics.types.add(CardType.CREATURE)

        # Mark for cleanup at end of turn
        vehicle.state.crewed_until_eot = True

        return events

    def _all_players_passed(self) -> bool:
        """Check if all players have passed priority."""
        return len(self.passed_players) >= len(self.state.players)

    def _get_next_player(self) -> Optional[str]:
        """Get the next player in turn order."""
        if not self.turn_manager or not self.turn_manager.turn_order:
            players = list(self.state.players.keys())
            if not players:
                return None
            current_idx = players.index(self.priority_player) if self.priority_player in players else 0
            return players[(current_idx + 1) % len(players)]

        turn_order = self.turn_manager.turn_order
        current_idx = turn_order.index(self.priority_player) if self.priority_player in turn_order else 0
        return turn_order[(current_idx + 1) % len(turn_order)]

    async def _check_state_based_actions(self) -> None:
        """Check and process state-based actions."""
        from .queries import get_toughness, is_creature

        # Loop until no more SBAs
        while True:
            found_sba = False

            # Check player life totals
            for player in self.state.players.values():
                if player.life <= 0 and not player.has_lost:
                    event = Event(
                        type=EventType.PLAYER_LOSES,
                        payload={'player': player.id, 'reason': 'life'}
                    )
                    self._emit_event(event)
                    found_sba = True

            # Check creature toughness
            battlefield = self.state.zones.get('battlefield')
            if battlefield:
                for obj_id in list(battlefield.objects):
                    obj = self.state.objects.get(obj_id)
                    if not obj:
                        continue

                    if not is_creature(obj, self.state):
                        continue

                    toughness = get_toughness(obj, self.state)

                    # Zero or less toughness
                    if toughness <= 0:
                        event = Event(
                            type=EventType.OBJECT_DESTROYED,
                            payload={'object_id': obj_id, 'reason': 'zero_toughness'}
                        )
                        self._emit_event(event)
                        found_sba = True
                        continue

                    # Lethal damage
                    if obj.state.damage >= toughness:
                        event = Event(
                            type=EventType.OBJECT_DESTROYED,
                            payload={'object_id': obj_id, 'reason': 'lethal_damage'}
                        )
                        self._emit_event(event)
                        found_sba = True

            if not found_sba:
                break

    async def _put_triggers_on_stack(self) -> None:
        """Put any waiting triggered abilities on the stack."""
        # This would process triggered abilities waiting to go on stack
        pass

    def _is_game_over(self) -> bool:
        """Check if the game is over."""
        alive_players = [p for p in self.state.players.values() if not p.has_lost]
        return len(alive_players) <= 1

    def _emit_event(self, event: Event) -> None:
        """Emit an event through the game's event pipeline."""
        if self.pipeline:
            self.pipeline.emit(event)


class ActionValidator:
    """
    Validates that actions are legal before execution.
    """

    def __init__(self, state: GameState, priority_system: PrioritySystem):
        self.state = state
        self.priority_system = priority_system

    def validate(self, action: PlayerAction) -> tuple[bool, str]:
        """
        Validate an action.

        Returns (is_valid, error_message).
        """
        # Check player has priority
        if action.player_id != self.priority_system.priority_player:
            return (False, "You don't have priority")

        # Validate specific action types
        if action.type == ActionType.CAST_SPELL:
            return self._validate_cast(action)
        elif action.type == ActionType.PLAY_LAND:
            return self._validate_land(action)
        elif action.type == ActionType.ACTIVATE_ABILITY:
            return self._validate_ability(action)

        return (True, "")

    def _validate_cast(self, action: PlayerAction) -> tuple[bool, str]:
        """Validate spell casting."""
        card = self.state.objects.get(action.card_id)
        if not card:
            return (False, "Card not found")

        # Check card is in hand
        hand_key = f"hand_{action.player_id}"
        hand = self.state.zones.get(hand_key)
        if not hand or action.card_id not in hand.objects:
            return (False, "Card not in hand")

        # Check can cast
        if not self.priority_system._can_cast(card, action.player_id):
            return (False, "Cannot cast this spell now")

        return (True, "")

    def _validate_land(self, action: PlayerAction) -> tuple[bool, str]:
        """Validate land play."""
        if not self.priority_system._can_play_land(action.player_id):
            return (False, "Cannot play a land now")

        card = self.state.objects.get(action.card_id)
        if not card:
            return (False, "Card not found")

        if CardType.LAND not in card.characteristics.types:
            return (False, "Not a land card")

        return (True, "")

    def _validate_ability(self, action: PlayerAction) -> tuple[bool, str]:
        """Validate ability activation."""
        # Would check ability can be activated
        return (True, "")
