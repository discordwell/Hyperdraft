"""
Hyperdraft Turn Manager

Handles the turn structure with phases and steps.
MTG turn structure:
1. Beginning Phase (Untap, Upkeep, Draw)
2. Pre-combat Main Phase
3. Combat Phase (Beginning, Declare Attackers, Declare Blockers, Damage, End)
4. Post-combat Main Phase
5. Ending Phase (End Step, Cleanup)
"""

from dataclasses import dataclass, field
from typing import Callable, Optional, TYPE_CHECKING
from enum import Enum, auto

from .types import (
    GameState, Event, EventType, ZoneType, CardType, new_id
)

if TYPE_CHECKING:
    from .priority import PrioritySystem
    from .combat import CombatManager
    from .pipeline import EventPipeline


class Phase(Enum):
    """Main phases of a turn."""
    BEGINNING = auto()
    PRECOMBAT_MAIN = auto()
    COMBAT = auto()
    POSTCOMBAT_MAIN = auto()
    ENDING = auto()


class Step(Enum):
    """Steps within phases."""
    # Beginning Phase
    UNTAP = auto()
    UPKEEP = auto()
    DRAW = auto()

    # Main Phase (no steps, just the phase)
    MAIN = auto()

    # Combat Phase
    BEGINNING_OF_COMBAT = auto()
    DECLARE_ATTACKERS = auto()
    DECLARE_BLOCKERS = auto()
    COMBAT_DAMAGE = auto()
    FIRST_STRIKE_DAMAGE = auto()  # Only exists if first strike creatures
    END_OF_COMBAT = auto()

    # Ending Phase
    END_STEP = auto()
    CLEANUP = auto()


@dataclass
class TurnState:
    """Current state of the turn."""
    turn_number: int = 0
    active_player_id: Optional[str] = None
    phase: Phase = Phase.BEGINNING
    step: Step = Step.UNTAP

    # Track what's happened this turn
    land_played: bool = False
    lands_played_count: int = 0
    lands_allowed: int = 1  # Can be increased by effects

    # Extra turns/phases queue
    extra_turns: list[str] = field(default_factory=list)  # Player IDs
    extra_combats: int = 0

    # Skip tracking
    skip_untap: bool = False
    skip_draw: bool = False
    skip_combat: bool = False


class TurnManager:
    """
    Manages turn structure and phase/step transitions.
    """

    def __init__(self, state: GameState):
        self.state = state
        self.turn_state = TurnState()

        # These will be set by the Game class
        self.priority_system: Optional['PrioritySystem'] = None
        self.combat_manager: Optional['CombatManager'] = None
        self.pipeline: Optional['EventPipeline'] = None

        # Callbacks for game integration
        self.on_phase_change: Optional[Callable[[Phase, Phase], None]] = None
        self.on_step_change: Optional[Callable[[Step, Step], None]] = None

        # Player turn order
        self.turn_order: list[str] = []
        self.current_player_index: int = 0

    @property
    def turn_number(self) -> int:
        return self.turn_state.turn_number

    @property
    def active_player(self) -> Optional[str]:
        return self.turn_state.active_player_id

    @property
    def phase(self) -> Phase:
        return self.turn_state.phase

    @property
    def step(self) -> Step:
        return self.turn_state.step

    def set_turn_order(self, player_ids: list[str]) -> None:
        """Set the turn order (usually determined by who goes first)."""
        self.turn_order = list(player_ids)
        self.current_player_index = 0

    def get_next_player(self) -> Optional[str]:
        """Get the next player in turn order."""
        if not self.turn_order:
            return None
        next_index = (self.current_player_index + 1) % len(self.turn_order)
        return self.turn_order[next_index]

    async def start_game(self) -> None:
        """Initialize and start the first turn."""
        if not self.turn_order:
            self.turn_order = list(self.state.players.keys())

        self.turn_state.turn_number = 0
        await self._emit_game_start()

    async def run_turn(self, player_id: str = None) -> list[Event]:
        """
        Run a complete turn for a player.

        Returns all events generated during the turn.
        """
        events = []

        # Determine active player
        if player_id:
            self.turn_state.active_player_id = player_id
            self.current_player_index = self.turn_order.index(player_id)
        else:
            self.turn_state.active_player_id = self.turn_order[self.current_player_index]

        # Keep centralized GameState tracking in sync for card logic/interceptors.
        self.state.active_player = self.turn_state.active_player_id

        self.turn_state.turn_number += 1
        self.state.turn_number = self.turn_state.turn_number
        self._reset_turn_state()

        events.extend(await self._emit_turn_start())

        # Beginning Phase
        events.extend(await self._run_beginning_phase())

        # Pre-combat Main Phase
        events.extend(await self._run_main_phase(is_postcombat=False))

        # Combat Phase (can be skipped)
        if not self.turn_state.skip_combat:
            events.extend(await self._run_combat_phase())

            # Extra combat phases
            while self.turn_state.extra_combats > 0:
                self.turn_state.extra_combats -= 1
                events.extend(await self._run_main_phase(is_postcombat=False))
                events.extend(await self._run_combat_phase())

        # Post-combat Main Phase
        events.extend(await self._run_main_phase(is_postcombat=True))

        # Ending Phase
        events.extend(await self._run_ending_phase())

        events.extend(await self._emit_turn_end())

        # Move to next player
        self.current_player_index = (self.current_player_index + 1) % len(self.turn_order)

        return events

    def _reset_turn_state(self) -> None:
        """Reset per-turn tracking."""
        self.turn_state.land_played = False
        self.turn_state.lands_played_count = 0
        self.turn_state.lands_allowed = 1
        self.turn_state.skip_untap = False
        self.turn_state.skip_draw = False
        self.turn_state.skip_combat = False
        self.turn_state.extra_combats = 0

        # Also reset the centralized GameState land tracking
        # (this is the authoritative source for interceptors)
        self.state.lands_played_this_turn = 0
        self.state.lands_allowed_this_turn = 1

    async def _run_beginning_phase(self) -> list[Event]:
        """Run the Beginning Phase (Untap, Upkeep, Draw)."""
        events = []
        self._set_phase(Phase.BEGINNING)

        # Untap Step
        if not self.turn_state.skip_untap:
            self._set_step(Step.UNTAP)
            events.extend(await self._do_untap_step())
            # No priority during untap step

        # Upkeep Step
        self._set_step(Step.UPKEEP)
        events.extend(await self._emit_step_start())
        if self.priority_system:
            await self.priority_system.run_priority_loop()

        # Draw Step
        self._set_step(Step.DRAW)
        if not self.turn_state.skip_draw:
            # First player doesn't draw on turn 1
            if not (self.turn_state.turn_number == 1 and
                    self.current_player_index == 0):
                events.extend(await self._do_draw_step())

        events.extend(await self._emit_step_start())
        if self.priority_system:
            await self.priority_system.run_priority_loop()

        return events

    async def _run_main_phase(self, is_postcombat: bool) -> list[Event]:
        """Run a Main Phase."""
        events = []

        if is_postcombat:
            self._set_phase(Phase.POSTCOMBAT_MAIN)
        else:
            self._set_phase(Phase.PRECOMBAT_MAIN)

        self._set_step(Step.MAIN)
        events.extend(await self._emit_step_start())

        if self.priority_system:
            await self.priority_system.run_priority_loop()

        return events

    async def _run_combat_phase(self) -> list[Event]:
        """Run the Combat Phase."""
        events = []
        self._set_phase(Phase.COMBAT)

        # Beginning of Combat
        self._set_step(Step.BEGINNING_OF_COMBAT)
        events.extend(await self._emit_step_start())
        if self.priority_system:
            await self.priority_system.run_priority_loop()

        # Delegate to combat manager if available
        if self.combat_manager:
            combat_events = await self.combat_manager.run_combat()
            events.extend(combat_events)
        else:
            # Basic combat without combat manager
            events.extend(await self._basic_combat())

        # End of Combat
        self._set_step(Step.END_OF_COMBAT)
        events.extend(await self._emit_step_start())
        if self.priority_system:
            await self.priority_system.run_priority_loop()

        # Combat has ended; creatures are no longer attacking or blocking.
        battlefield = self.state.zones.get('battlefield')
        if battlefield:
            for obj_id in list(battlefield.objects):
                obj = self.state.objects.get(obj_id)
                if obj:
                    obj.state.attacking = False
                    obj.state.blocking = False

        return events

    async def _basic_combat(self) -> list[Event]:
        """Basic combat flow when no combat manager is available."""
        events = []

        # Declare Attackers
        self._set_step(Step.DECLARE_ATTACKERS)
        events.extend(await self._emit_step_start())
        if self.priority_system:
            await self.priority_system.run_priority_loop()

        # Declare Blockers
        self._set_step(Step.DECLARE_BLOCKERS)
        events.extend(await self._emit_step_start())
        if self.priority_system:
            await self.priority_system.run_priority_loop()

        # Combat Damage
        self._set_step(Step.COMBAT_DAMAGE)
        events.extend(await self._emit_step_start())
        if self.priority_system:
            await self.priority_system.run_priority_loop()

        return events

    async def _run_ending_phase(self) -> list[Event]:
        """Run the Ending Phase (End Step, Cleanup)."""
        events = []
        self._set_phase(Phase.ENDING)

        # End Step
        self._set_step(Step.END_STEP)
        events.extend(await self._emit_step_start())
        if self.priority_system:
            await self.priority_system.run_priority_loop()

        # Cleanup Step
        self._set_step(Step.CLEANUP)
        events.extend(await self._do_cleanup_step())

        # Normally no priority in cleanup, but if triggers happen,
        # there's another cleanup step with priority
        # (simplified: we don't handle recursive cleanup)

        return events

    async def _do_untap_step(self) -> list[Event]:
        """Perform untap step actions."""
        events = []
        active_player = self.turn_state.active_player_id

        # Untap all permanents controlled by active player
        battlefield = self.state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = self.state.objects.get(obj_id)
                if obj and obj.controller == active_player and obj.state.tapped:
                    # Check for "doesn't untap" effects (would be an interceptor)
                    event = Event(
                        type=EventType.UNTAP,
                        payload={'object_id': obj_id}
                    )
                    # Emit the event through the pipeline to actually untap
                    if self.pipeline:
                        self.pipeline.emit(event)
                    events.append(event)

        return events

    async def _do_draw_step(self) -> list[Event]:
        """Perform draw step action."""
        event = Event(
            type=EventType.DRAW,
            payload={
                'player': self.turn_state.active_player_id,
                'count': 1
            }
        )
        # Emit the event through the pipeline to actually draw
        if self.pipeline:
            self.pipeline.emit(event)
        return [event]

    async def _do_cleanup_step(self) -> list[Event]:
        """Perform cleanup step actions."""
        events = []
        active_player = self.turn_state.active_player_id

        # Discard to hand size (7 by default)
        hand_key = f"hand_{active_player}"
        hand = self.state.zones.get(hand_key)
        max_hand_size = 7  # Could be modified by effects

        if hand and len(hand.objects) > max_hand_size:
            excess = len(hand.objects) - max_hand_size
            # Player would choose which cards to discard
            # For now, just note the requirement
            events.append(Event(
                type=EventType.DISCARD,
                payload={
                    'player': active_player,
                    'count': excess,
                    'reason': 'cleanup'
                }
            ))

        # Remove damage from creatures
        battlefield = self.state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = self.state.objects.get(obj_id)
                if obj:
                    # Clear damage
                    if obj.state.damage > 0:
                        obj.state.damage = 0

                    # End "crewed until end of turn" - remove CREATURE type from Vehicles
                    if obj.state.crewed_until_eot:
                        obj.state.crewed_until_eot = False
                        # Only remove CREATURE if it's a Vehicle (artifact with Vehicle subtype)
                        # that wasn't originally a creature
                        if ('Vehicle' in obj.characteristics.subtypes and
                            CardType.ARTIFACT in obj.characteristics.types):
                            obj.characteristics.types.discard(CardType.CREATURE)

                    # Clear end-of-turn PT modifiers
                    if hasattr(obj.state, 'pt_modifiers'):
                        obj.state.pt_modifiers = [
                            mod for mod in obj.state.pt_modifiers
                            if mod.get('duration') != 'end_of_turn'
                        ]

                    # Clear end-of-turn temporary keyword/ability grants.
                    if obj.characteristics and obj.characteristics.abilities:
                        obj.characteristics.abilities = [
                            a for a in obj.characteristics.abilities
                            if not (
                                isinstance(a, dict)
                                and a.get("_temporary") is True
                                and a.get("_duration") == "end_of_turn"
                            )
                        ]

                    # Revert end-of-turn control changes.
                    if hasattr(obj.state, "_restore_controller_eot"):
                        obj.controller = getattr(obj.state, "_restore_controller_eot")
                        delattr(obj.state, "_restore_controller_eot")

        # End "until end of turn" effects
        # (Would be handled by interceptor duration system)

        # Empty mana pools
        # (Would be handled by mana system)

        return events

    async def _emit_game_start(self) -> list[Event]:
        """Emit game start event."""
        event = Event(
            type=EventType.GAME_START,
            payload={'players': list(self.state.players.keys())}
        )
        if self.pipeline:
            self.pipeline.emit(event)
        return [event]

    async def _emit_turn_start(self) -> list[Event]:
        """Emit turn start event."""
        event = Event(
            type=EventType.TURN_START,
            payload={
                'player': self.turn_state.active_player_id,
                'turn_number': self.turn_state.turn_number
            }
        )
        if self.pipeline:
            self.pipeline.emit(event)
        return [event]

    async def _emit_turn_end(self) -> list[Event]:
        """Emit turn end event."""
        event = Event(
            type=EventType.TURN_END,
            payload={
                'player': self.turn_state.active_player_id,
                'turn_number': self.turn_state.turn_number
            }
        )
        if self.pipeline:
            self.pipeline.emit(event)
        return [event]

    async def _emit_step_start(self) -> list[Event]:
        """Emit step/phase start event."""
        step = self.turn_state.step.name.lower()
        # Many card files treat "phase" as a semantic step marker.
        if self.turn_state.step == Step.BEGINNING_OF_COMBAT:
            phase = 'combat'
        else:
            phase = step

        event = Event(
            type=EventType.PHASE_START,
            payload={
                'phase': phase,
                'step': step,
                'active_player': self.turn_state.active_player_id,
                'turn_number': self.turn_state.turn_number,
            }
        )
        if self.pipeline:
            self.pipeline.emit(event)
        return [event]

    def _set_phase(self, phase: Phase) -> None:
        """Set the current phase."""
        old_phase = self.turn_state.phase
        self.turn_state.phase = phase
        if self.on_phase_change:
            self.on_phase_change(old_phase, phase)

    def _set_step(self, step: Step) -> None:
        """Set the current step."""
        old_step = self.turn_state.step
        self.turn_state.step = step
        if self.on_step_change:
            self.on_step_change(old_step, step)

    # Action helpers

    def can_play_land(self, player_id: str) -> bool:
        """Check if a player can play a land."""
        if player_id != self.turn_state.active_player_id:
            return False

        if self.turn_state.phase not in [Phase.PRECOMBAT_MAIN, Phase.POSTCOMBAT_MAIN]:
            return False

        # Use centralized GameState tracking (authoritative for interceptors)
        if self.state.lands_played_this_turn >= self.state.lands_allowed_this_turn:
            return False

        return True

    def play_land(self) -> None:
        """Record that a land was played."""
        self.turn_state.land_played = True
        self.turn_state.lands_played_count += 1

        # Also update centralized GameState tracking
        self.state.lands_played_this_turn += 1

    def can_cast_sorcery(self, player_id: str) -> bool:
        """Check if a player can cast a sorcery-speed spell."""
        if player_id != self.turn_state.active_player_id:
            return False

        if self.turn_state.phase not in [Phase.PRECOMBAT_MAIN, Phase.POSTCOMBAT_MAIN]:
            return False

        # Stack must be empty for sorcery speed
        # (Would check stack manager)
        return True

    def add_extra_turn(self, player_id: str) -> None:
        """Add an extra turn for a player."""
        self.turn_state.extra_turns.append(player_id)

    def add_extra_combat(self) -> None:
        """Add an extra combat phase."""
        self.turn_state.extra_combats += 1

    def skip_next_untap(self) -> None:
        """Skip the next untap step."""
        self.turn_state.skip_untap = True

    def skip_next_draw(self) -> None:
        """Skip the next draw step."""
        self.turn_state.skip_draw = True

    def skip_combat(self) -> None:
        """Skip the combat phase this turn."""
        self.turn_state.skip_combat = True

    def grant_additional_land_play(self, count: int = 1) -> None:
        """
        Grant additional land plays for this turn.

        Used by cards like Exploration ("You may play an additional land on each of your turns").

        Args:
            count: Number of additional lands allowed (default 1)
        """
        self.turn_state.lands_allowed += count
        self.state.lands_allowed_this_turn += count
