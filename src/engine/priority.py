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

from .types import GameState, Event, EventType, CardType
from .stack import StackManager, StackItem, StackItemType
from .mana import ManaSystem, ManaCost

if TYPE_CHECKING:
    from .turn import TurnManager


class ActionType(Enum):
    """Types of actions a player can take."""
    PASS = auto()              # Pass priority
    CAST_SPELL = auto()        # Cast a spell from hand
    ACTIVATE_ABILITY = auto()  # Activate an ability
    PLAY_LAND = auto()         # Play a land
    SPECIAL_ACTION = auto()    # Special actions (morph, suspend, etc.)


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

        # Priority state
        self.priority_player: Optional[str] = None
        self.passed_players: set[str] = set()

        # For human players - callback to get their action
        self.get_human_action: Optional[Callable[[str, list[LegalAction]], asyncio.Future]] = None

        # For AI players - callback to get their action
        self.get_ai_action: Optional[Callable[[str, GameState, list[LegalAction]], PlayerAction]] = None

        # Player type tracking
        self.ai_players: set[str] = set()

        # Action handlers
        self._action_handlers: dict[ActionType, Callable] = {
            ActionType.PASS: self._handle_pass,
            ActionType.CAST_SPELL: self._handle_cast_spell,
            ActionType.ACTIVATE_ABILITY: self._handle_activate_ability,
            ActionType.PLAY_LAND: self._handle_play_land,
            ActionType.SPECIAL_ACTION: self._handle_special_action,
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

        return actions

    def _can_cast(self, card, player_id: str) -> bool:
        """Check if a player can cast a card."""
        # Check if it's a spell (not a land)
        if CardType.LAND in card.characteristics.types:
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
        cost = ManaCost.parse(card.characteristics.mana_cost or "")
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
        """Get activatable abilities on a permanent."""
        # Would iterate through abilities on the card
        # For now, return empty list
        return []

    async def _execute_action(self, action: PlayerAction) -> list[Event]:
        """Execute a player action."""
        handler = self._action_handlers.get(action.type)
        if handler:
            return await handler(action)
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
                'card_id': action.card_id,
                'controller': action.player_id
            }
        ))

        return events

    async def _handle_activate_ability(self, action: PlayerAction) -> list[Event]:
        """Handle activating an ability."""
        events = []

        # Would create ability stack item
        if self.stack:
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
                'to_zone_type': 'BATTLEFIELD'
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
        # This would call the game's SBA checker
        pass

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
        # This would be connected to the main event pipeline
        pass


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
