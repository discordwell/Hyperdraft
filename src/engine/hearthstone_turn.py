"""
Hearthstone Turn Manager

Simplified turn structure for Hearthstone mode:
1. Draw step (with fatigue if empty deck)
2. Main phase (all actions happen here - casting, attacking, hero powers)
3. End step (cleanup)

No separate combat phase - attacks happen during main phase.
No priority system - active player has control until end of turn.
"""

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
from enum import Enum, auto

from .types import (
    GameState, Event, EventType, ZoneType, new_id
)
from .turn import TurnManager, Phase, Step, TurnState

if TYPE_CHECKING:
    from .priority import PrioritySystem
    from .combat import CombatManager
    from .pipeline import EventPipeline


class HearthstonePhase(Enum):
    """Hearthstone turn phases (simplified)."""
    DRAW = auto()
    MAIN = auto()
    END = auto()


@dataclass
class HearthstoneTurnState:
    """Turn state for Hearthstone mode."""
    turn_number: int = 0
    active_player_id: Optional[str] = None
    phase: HearthstonePhase = HearthstonePhase.DRAW

    # Extra turns
    extra_turns: list[str] = field(default_factory=list)


class HearthstoneTurnManager(TurnManager):
    """
    Hearthstone-specific turn manager.

    Key differences from MTG:
    - No untap/upkeep steps
    - No priority loops (active player acts until passing turn)
    - No combat phase (attacks happen in main phase)
    - Mana crystals auto-gain and refill at turn start
    - Fatigue damage when drawing from empty deck
    """

    def __init__(self, state: GameState):
        super().__init__(state)
        self.hs_turn_state = HearthstoneTurnState()
        self.hearthstone_ai_handler = None
        self.ai_players = set()  # Set of AI player IDs

    async def run_turn(self, player_id: str = None) -> list[Event]:
        """
        Run a complete Hearthstone turn.

        Turn structure:
        1. Draw step (gain mana crystal, draw card, check fatigue)
        2. Main phase (player performs actions until ending turn)
        3. End step (cleanup)
        """
        events = []

        # Determine active player
        if player_id:
            self.hs_turn_state.active_player_id = player_id
            if player_id in self.turn_order:
                self.current_player_index = self.turn_order.index(player_id)
        else:
            self.hs_turn_state.active_player_id = self.turn_order[self.current_player_index]

        # Keep GameState in sync
        self.state.active_player = self.hs_turn_state.active_player_id

        self.hs_turn_state.turn_number += 1
        self.state.turn_number = self.hs_turn_state.turn_number
        self.turn_state.turn_number = self.hs_turn_state.turn_number

        events.extend(await self._emit_turn_start())

        # Draw Phase
        self.hs_turn_state.phase = HearthstonePhase.DRAW
        events.extend(await self._run_draw_phase())

        # Main Phase (actions handled by player/AI, not automatic)
        self.hs_turn_state.phase = HearthstonePhase.MAIN
        events.extend(await self._run_main_phase_start())

        # For AI players, execute their turn automatically
        if hasattr(self, 'hearthstone_ai_handler') and self.hearthstone_ai_handler:
            if self._is_ai_player(self.hs_turn_state.active_player_id):
                ai_events = await self._run_ai_turn()
                events.extend(ai_events)

                # Check SBAs after AI actions (minions may have died in combat)
                await self._check_state_based_actions()

        # End Phase (auto-end for AI, manual for humans)
        if hasattr(self, 'hearthstone_ai_handler') and self._is_ai_player(self.hs_turn_state.active_player_id):
            events.extend(await self.end_turn())

        return events

    async def end_turn(self) -> list[Event]:
        """
        End the current turn and perform cleanup.
        Called when active player explicitly ends their turn.
        """
        events = []

        self.hs_turn_state.phase = HearthstonePhase.END
        events.extend(await self._run_end_phase())

        # Final SBA check before ending turn
        await self._check_state_based_actions()

        events.extend(await self._emit_turn_end())

        # Move to next player
        self.current_player_index = (self.current_player_index + 1) % len(self.turn_order)

        return events

    async def _run_draw_phase(self) -> list[Event]:
        """
        Hearthstone draw phase:
        1. Gain mana crystal (max 10)
        2. Refill mana crystals
        3. Reset hero power usage
        4. Unfreeze minions
        5. Draw a card (or take fatigue damage)
        6. Check state-based actions (player loss)
        """
        events = []
        active_player_id = self.hs_turn_state.active_player_id
        active_player = self.state.players.get(active_player_id)

        if not active_player:
            return events

        # Gain mana crystal and refill
        if hasattr(self, 'mana_system') and self.mana_system:
            self.mana_system.on_turn_start(active_player_id)
        else:
            # Direct manipulation if mana system not available
            if active_player.mana_crystals < 10:
                active_player.mana_crystals += 1
            active_player.mana_crystals_available = active_player.mana_crystals

        # Reset hero power
        active_player.hero_power_used = False

        # Unfreeze minions and clear summoning sickness for active player
        from .types import CardType
        battlefield = self.state.zones.get('battlefield')
        if battlefield:
            for obj_id in list(battlefield.objects):
                obj = self.state.objects.get(obj_id)
                if obj and obj.controller == active_player_id:
                    if obj.state.frozen:
                        obj.state.frozen = False
                    # Clear summoning sickness at start of controller's turn
                    if CardType.MINION in obj.characteristics.types:
                        obj.state.summoning_sickness = False

        # Draw a card
        library_zone_id = f"library_{active_player_id}"
        library = self.state.zones.get(library_zone_id)

        if library and library.objects:
            # Draw card
            draw_event = Event(
                type=EventType.DRAW,
                payload={
                    'player': active_player_id,
                    'count': 1
                }
            )
            if self.pipeline:
                self.pipeline.emit(draw_event)
            events.append(draw_event)
        else:
            # Fatigue damage
            active_player.fatigue_damage += 1
            fatigue_event = Event(
                type=EventType.FATIGUE_DAMAGE,
                payload={
                    'player': active_player_id,
                    'amount': active_player.fatigue_damage
                }
            )
            if self.pipeline:
                self.pipeline.emit(fatigue_event)
            events.append(fatigue_event)

            # Apply damage to hero (uses DAMAGE so armor absorbs it)
            if active_player.hero_id:
                damage_event = Event(
                    type=EventType.DAMAGE,
                    payload={
                        'target': active_player.hero_id,
                        'amount': active_player.fatigue_damage,
                        'source': 'fatigue'
                    }
                )
                if self.pipeline:
                    self.pipeline.emit(damage_event)
                events.append(damage_event)

        # Check state-based actions (player death from fatigue, minion death, etc.)
        await self._check_state_based_actions()

        return events

    async def _run_main_phase_start(self) -> list[Event]:
        """
        Start of main phase.
        Emit phase start event.
        """
        events = []

        phase_event = Event(
            type=EventType.PHASE_START,
            payload={
                'phase': 'main',
                'player': self.hs_turn_state.active_player_id
            }
        )
        if self.pipeline:
            self.pipeline.emit(phase_event)
        events.append(phase_event)

        return events

    async def _run_end_phase(self) -> list[Event]:
        """
        End phase cleanup:
        1. Clear "this turn" effects
        2. Reset attacks_this_turn counters
        """
        events = []

        phase_event = Event(
            type=EventType.PHASE_END,
            payload={
                'phase': 'end',
                'player': self.hs_turn_state.active_player_id
            }
        )
        if self.pipeline:
            self.pipeline.emit(phase_event)
        events.append(phase_event)

        # Clean up temporary hero attack (Druid Shapeshift "+1 Attack this turn")
        active_player = self.state.players.get(self.hs_turn_state.active_player_id)
        if active_player and getattr(active_player, '_shapeshift_attack', False):
            # Only clear if no real weapon card is equipped
            active_player.weapon_attack = 0
            active_player.weapon_durability = 0
            active_player._shapeshift_attack = False
            # Clear hero object weapon state too
            if active_player.hero_id:
                hero = self.state.objects.get(active_player.hero_id)
                if hero:
                    hero.state.weapon_attack = 0
                    hero.state.weapon_durability = 0

        # Clear end-of-turn PT modifiers on all battlefield objects
        battlefield = self.state.zones.get('battlefield')
        if battlefield:
            for obj_id in list(battlefield.objects):
                obj = self.state.objects.get(obj_id)
                if obj and hasattr(obj.state, 'pt_modifiers'):
                    obj.state.pt_modifiers = [
                        mod for mod in obj.state.pt_modifiers
                        if mod.get('duration') != 'end_of_turn'
                    ]

        # Reset combat state
        if self.combat_manager:
            self.combat_manager.reset_combat()

        return events

    async def _emit_turn_start(self) -> list[Event]:
        """Emit turn start event."""
        events = []
        turn_start = Event(
            type=EventType.TURN_START,
            payload={
                'player': self.hs_turn_state.active_player_id,
                'turn_number': self.hs_turn_state.turn_number
            }
        )
        if self.pipeline:
            self.pipeline.emit(turn_start)
        events.append(turn_start)
        return events

    async def _emit_turn_end(self) -> list[Event]:
        """Emit turn end event."""
        events = []
        turn_end = Event(
            type=EventType.TURN_END,
            payload={
                'player': self.hs_turn_state.active_player_id,
                'turn_number': self.hs_turn_state.turn_number
            }
        )
        if self.pipeline:
            self.pipeline.emit(turn_end)
        events.append(turn_end)
        return events

    async def _emit_game_start(self) -> None:
        """Emit game start event."""
        game_start = Event(
            type=EventType.GAME_START,
            payload={'players': list(self.state.players.keys())}
        )
        if self.pipeline:
            self.pipeline.emit(game_start)

    async def _check_state_based_actions(self) -> None:
        """
        Check and process state-based actions in Hearthstone:
        - Players with life <= 0 lose the game
        - Minions with health <= 0 die
        """
        # Check player life totals
        for player in self.state.players.values():
            if player.life <= 0 and not player.has_lost:
                event = Event(
                    type=EventType.PLAYER_LOSES,
                    payload={'player': player.id, 'reason': 'life'}
                )
                if self.pipeline:
                    self.pipeline.emit(event)
                player.has_lost = True

        # Check minion health
        from .queries import get_toughness, is_creature
        battlefield = self.state.zones.get('battlefield')
        if battlefield:
            for obj_id in list(battlefield.objects):
                obj = self.state.objects.get(obj_id)
                if obj:
                    # Check if minion (use is_creature which works for both MTG creatures and HS minions)
                    if is_creature(obj, self.state):
                        toughness = get_toughness(obj, self.state)
                        # Minion dies if damage >= toughness OR if toughness <= 0
                        if obj.state.damage >= toughness or toughness <= 0:
                            # Minion dies
                            death_event = Event(
                                type=EventType.OBJECT_DESTROYED,
                                payload={'object_id': obj.id, 'reason': 'lethal_damage'}
                            )
                            if self.pipeline:
                                self.pipeline.emit(death_event)

    # Override MTG-specific methods to no-op

    async def _run_beginning_phase(self) -> list[Event]:
        """MTG compatibility - no-op in Hearthstone."""
        return []

    async def _run_combat_phase(self) -> list[Event]:
        """MTG compatibility - no-op in Hearthstone (combat in main phase)."""
        return []

    async def _run_ending_phase(self) -> list[Event]:
        """MTG compatibility - handled by _run_end_phase."""
        return []

    # AI Integration

    def set_ai_handler(self, handler):
        """Set the Hearthstone AI handler."""
        self.hearthstone_ai_handler = handler

    def set_ai_player(self, player_id: str):
        """Mark a player as AI-controlled."""
        self.ai_players.add(player_id)

    def _is_ai_player(self, player_id: str) -> bool:
        """Check if player is AI-controlled."""
        return player_id in self.ai_players

    async def _run_ai_turn(self) -> list[Event]:
        """Execute AI turn using the configured handler."""
        if not self.hearthstone_ai_handler:
            return []

        from .game import Game
        game = None

        # Try to get game instance from pipeline
        if hasattr(self, 'pipeline') and hasattr(self.pipeline, 'game'):
            game = self.pipeline.game
        # Or from state if stored there
        elif hasattr(self.state, '_game'):
            game = self.state._game

        if not game:
            # Fallback: create minimal game reference
            # This is a workaround - ideally we'd pass game in constructor
            return []

        return await self.hearthstone_ai_handler.take_turn(
            self.hs_turn_state.active_player_id,
            self.state,
            game
        )

    # Properties for compatibility

    @property
    def turn_number(self) -> int:
        return self.hs_turn_state.turn_number

    @property
    def active_player(self) -> Optional[str]:
        return self.hs_turn_state.active_player_id

    @property
    def phase(self) -> HearthstonePhase:
        return self.hs_turn_state.phase
