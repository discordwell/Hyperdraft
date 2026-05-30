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

        # Sweep "until your next turn" effects whose owner is the player
        # whose turn is about to begin. This must happen *before* TURN_START
        # so the new active player starts the turn with their previously
        # registered until-next-turn animations / grants peeled off.
        self._do_until_your_next_turn_cleanup(self.turn_state.active_player_id)

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
        base_lands_allowed = getattr(self.state, "base_lands_allowed_per_turn", 1) or 1
        self.turn_state.lands_allowed = base_lands_allowed
        self.turn_state.skip_untap = False
        self.turn_state.skip_draw = False
        self.turn_state.skip_combat = False
        self.turn_state.extra_combats = 0

        # Also reset the centralized GameState land tracking
        # (this is the authoritative source for interceptors)
        self.state.lands_played_this_turn = 0
        self.state.lands_allowed_this_turn = base_lands_allowed

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
            skip_first_player_draw = (
                not getattr(self.state, "first_player_draws", False)
                and self.turn_state.turn_number == 1
                and self.current_player_index == 0
            )
            if not skip_first_player_draw:
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
        draw_count = max(0, int(getattr(self.state, "draw_step_cards", 1) or 0))
        if draw_count == 0:
            return []

        event = Event(
            type=EventType.DRAW,
            payload={
                'player': self.turn_state.active_player_id,
                'count': draw_count
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
        max_hand_size = getattr(self.state, "max_hand_size", 7)

        if hand and max_hand_size and max_hand_size > 0 and len(hand.objects) > max_hand_size:
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
                    if self.state.clear_damage_on_cleanup and obj.state.damage > 0:
                        obj.state.damage = 0

                    # End "crewed until end of turn" - remove CREATURE type from Vehicles
                    if obj.state.crewed_until_eot:
                        obj.state.crewed_until_eot = False
                        # Only remove CREATURE if it's a Vehicle (artifact with Vehicle subtype)
                        # that wasn't originally a creature
                        if ('Vehicle' in obj.characteristics.subtypes and
                            CardType.ARTIFACT in obj.characteristics.types):
                            obj.characteristics.types.discard(CardType.CREATURE)

                    # End "saddled until end of turn" (OTJ Mount mechanic)
                    if obj.state.saddled_until_eot:
                        obj.state.saddled_until_eot = False
                    # Clear "creatures that saddled this Mount this turn" tracking.
                    if obj.state.saddled_by_this_turn:
                        obj.state.saddled_by_this_turn = []
                    if obj.state.saddled_count_this_turn:
                        obj.state.saddled_count_this_turn = 0

                    # End "can attack this turn as though it didn't have
                    # defender" (Timid Shieldbearer and similar).
                    if getattr(obj.state, 'can_attack_despite_defender', False):
                        obj.state.can_attack_despite_defender = False

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

        # End "until end of turn" effects — sweep duration='end_of_turn'
        # interceptors out of state.interceptors. Granted triggered abilities
        # (grant_triggered_ability), make_pump_self_ability EOT registrations
        # going through the QUERY layer, etc. all rely on this.
        eot_aliases = {"end_of_turn", "until_end_of_turn", "until_eot", "eot",
                       "next_end_step", "end_of_this_turn", "this_turn"}
        to_remove = [
            iid for iid, ic in self.state.interceptors.items()
            if isinstance(getattr(ic, "duration", None), str)
            and ic.duration.strip().lower().replace(" ", "_") in eot_aliases
        ]
        for iid in to_remove:
            ic = self.state.interceptors.pop(iid, None)
            # Also detach from owning object's interceptor_ids list, if any.
            if ic is not None:
                src = self.state.objects.get(getattr(ic, "source", None))
                if src is not None and iid in src.interceptor_ids:
                    src.interceptor_ids.remove(iid)

        # Restore dual-write fields for becomes_copy_of effects whose EOT
        # interceptors were just swept above. The helper stashes the
        # target's original subtypes keyed by a copy-tag.
        becomes_copy_cleanups = getattr(self.state, '_becomes_copy_cleanups', None)
        if becomes_copy_cleanups:
            for tag_id, payload in list(becomes_copy_cleanups.items()):
                target_id = payload.get('target_id')
                target_obj = self.state.objects.get(target_id) if target_id else None
                if target_obj is not None:
                    original = payload.get('original_subtypes')
                    if isinstance(original, set):
                        target_obj.characteristics.subtypes = set(original)
                    original_super = payload.get('original_supertypes')
                    if isinstance(original_super, set):
                        target_obj.characteristics.supertypes = set(original_super)
                becomes_copy_cleanups.pop(tag_id, None)

        # Symmetrical sweep for becomes_creature subtype dual-writes: vehicles
        # and other "becomes a creature with subtype X" effects need their
        # added subtypes peeled off when the duration expires, otherwise the
        # subtypes leak indefinitely.
        becomes_creature_cleanups = getattr(self.state, '_becomes_creature_cleanups', None)
        if becomes_creature_cleanups:
            for tag_id, payload in list(becomes_creature_cleanups.items()):
                target_id = payload.get('target_id')
                target_obj = self.state.objects.get(target_id) if target_id else None
                if target_obj is not None:
                    original = payload.get('original_subtypes')
                    if isinstance(original, set):
                        target_obj.characteristics.subtypes = set(original)
                becomes_creature_cleanups.pop(tag_id, None)

        # Empty mana pools
        # (Would be handled by mana system)

        return events

    # =====================================================================
    # "Until your next turn" duration cleanup
    # =====================================================================
    # A handful of cards (Rootwise Survivor, etc.) install effects that
    # last "until your next turn" — the same player's next turn, *across*
    # the opponent's turn. Standard EOT cleanup runs at the end of each
    # turn, which is too eager. Instead, sweep these at the *start* of the
    # owner's next turn (i.e., when ``active_player == ic.controller``).
    #
    # Implementation parallels the EOT sweep in ``_do_cleanup_step``:
    #   1. Drop interceptors whose ``duration`` matches the recognized
    #      until-next-turn alias and whose ``controller`` is the player
    #      whose turn is starting.
    #   2. Restore stashed subtype dual-writes for ``becomes_creature``-style
    #      effects (mirrors the EOT subtype-restoration hook), keyed off
    #      ``state._until_your_next_turn_cleanups``.
    # =====================================================================
    def _do_until_your_next_turn_cleanup(self, active_player: Optional[str]) -> None:
        """Remove interceptors with duration='until_your_next_turn' whose
        controller is ``active_player`` (it's now their turn again).

        Also peel off any subtype dual-writes those interceptors had stashed
        in ``state._until_your_next_turn_cleanups`` so subtypes added by
        ``becomes_creature``-style helpers don't leak.
        """
        if not active_player:
            return

        unt_aliases = {
            "until_your_next_turn",
            "until_my_next_turn",
            "untilyournext_turn",
            "until_next_turn",
        }

        # 1. Sweep matching interceptors.
        to_remove = []
        for iid, ic in self.state.interceptors.items():
            dur = getattr(ic, "duration", None)
            if not isinstance(dur, str):
                continue
            normalized = dur.strip().lower().replace(" ", "_")
            if normalized not in unt_aliases:
                continue
            if getattr(ic, "controller", None) != active_player:
                continue
            to_remove.append(iid)

        removed_tags: set = set()
        for iid in to_remove:
            ic = self.state.interceptors.pop(iid, None)
            if ic is None:
                continue
            # Detach from owning object's interceptor_ids list, if any.
            src = self.state.objects.get(getattr(ic, "source", None))
            if src is not None and iid in src.interceptor_ids:
                src.interceptor_ids.remove(iid)
            # Track the becomes_creature tag so we can restore subtypes.
            tag = getattr(ic, "_becomes_creature_tag", None)
            if tag is not None:
                removed_tags.add(tag)

        # 2. Restore subtype dual-writes that were stashed for these
        #    until-next-turn animations. The dict is keyed by tag id and
        #    populated by the helper that installed the animation.
        unt_cleanups = getattr(self.state, "_until_your_next_turn_cleanups", None)
        if unt_cleanups:
            for tag_id in list(unt_cleanups.keys()):
                payload = unt_cleanups.get(tag_id, {}) or {}
                # Only act on cleanups owned by this player; if the helper
                # recorded the controller, gate on it. Otherwise fall back
                # to "tag was just removed".
                cleanup_owner = payload.get("controller")
                if cleanup_owner is not None and cleanup_owner != active_player:
                    continue
                if cleanup_owner is None and tag_id not in removed_tags:
                    continue
                target_id = payload.get("target_id")
                target_obj = self.state.objects.get(target_id) if target_id else None
                if target_obj is not None:
                    original = payload.get("original_subtypes")
                    if isinstance(original, set):
                        target_obj.characteristics.subtypes = set(original)
                unt_cleanups.pop(tag_id, None)

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
        # Clear per-turn scratchpad. Card setups use `state.turn_data` to
        # remember "did X happen this turn" (e.g. life gained, attacked).
        if hasattr(self.state, "turn_data"):
            self.state.turn_data.clear()
        return [event]

    async def _emit_step_start(self) -> list[Event]:
        """Emit step/phase start event."""
        step = self.turn_state.step.name.lower()
        # Many card files treat "phase" as a semantic step marker.
        if self.turn_state.step == Step.BEGINNING_OF_COMBAT:
            phase = 'combat'
        elif self.turn_state.step == Step.MAIN:
            # Distinguish first/second main so phase-keyed triggers (e.g. Survival,
            # "at the beginning of your second main phase") can filter on it.
            if self.turn_state.phase == Phase.POSTCOMBAT_MAIN:
                phase = 'postcombat_main'
            else:
                phase = 'precombat_main'
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


# =============================================================================
# State-based actions: planeswalker zero-loyalty destruction
# =============================================================================
#
# CR 704.5i: a planeswalker with 0 or less loyalty is destroyed and put into
# its owner's graveyard. The framework lives in src/engine/planeswalker.py
# (see make_planeswalker_setup); this hook fires the OBJECT_DESTROYED event
# for any battlefield planeswalker whose loyalty has dropped to or below 0.
#
# Two callers:
# 1. Priority's SBA loop / Game.check_state_based_actions: invokes
#    ``check_planeswalker_zero_loyalty_sbas(state, pipeline)`` to fire
#    pending destructions before granting priority.
# 2. Tests can call the helper directly with a Game instance to validate
#    the SBA without running a full turn.
# -----------------------------------------------------------------------------

def check_planeswalker_zero_loyalty_sbas(state: GameState, pipeline=None) -> list[Event]:
    """Destroy battlefield planeswalkers with loyalty <= 0.

    Returns the list of OBJECT_DESTROYED events emitted (or just constructed
    when ``pipeline`` is None). Idempotent: re-running after destruction is
    a no-op (destroyed PWs are no longer on the battlefield).
    """
    from .planeswalker import planeswalkers_with_zero_loyalty
    events: list[Event] = []
    for pw in planeswalkers_with_zero_loyalty(state):
        evt = Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': pw.id, 'reason': 'zero_loyalty'},
            source=pw.state.last_damage_source,
        )
        events.append(evt)
        if pipeline is not None:
            pipeline.emit(evt)
    return events


# =============================================================================
# State-based actions: legend rule (CR 704.5j) — W15
# =============================================================================
#
# CR 704.5j: "If a player controls two or more legendary permanents with the
# same name, that player chooses one of them, and the rest are put into their
# owners' graveyards. This is called the 'legend rule'."
#
# Implementation notes:
#  - Tokens with the Legendary supertype participate (W16+ pendant cards).
#  - Choice rule: for the simple SBA helper we keep the highest-loyalty
#    planeswalker (so PWs whose ult just fired aren't penalized) or the
#    most-recent ETB (highest entered_zone_at) for non-PW legends. Tests
#    can override by setting ``state._legend_rule_keep_picker`` to a
#    callable ``(controller, name, candidates_list) -> chosen``.
# -----------------------------------------------------------------------------

def check_legend_rule_sbas(state: GameState, pipeline=None) -> list[Event]:
    """Apply the legend rule: for each player, group legendary permanents on
    the battlefield by name; if a player controls 2+ in a group, keep one and
    destroy the rest.

    Returns OBJECT_DESTROYED events emitted (or constructed when no pipeline).
    Idempotent.
    """
    from collections import defaultdict
    events: list[Event] = []
    battlefield = state.zones.get('battlefield')
    if not battlefield:
        return events

    # Group: (controller, name) -> list[GameObject]
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for obj_id in list(battlefield.objects):
        obj = state.objects.get(obj_id)
        if obj is None:
            continue
        # Tokens with no name still participate via Characteristics; but most
        # legend tokens have a name set on the GameObject.
        supertypes = obj.characteristics.supertypes if obj.characteristics else set()
        if "Legendary" not in supertypes:
            continue
        name = obj.name or (obj.card_def.name if getattr(obj, "card_def", None) else "")
        if not name:
            continue
        groups[(obj.controller, name)].append(obj)

    picker = getattr(state, "_legend_rule_keep_picker", None)
    for (controller, name), objs in groups.items():
        if len(objs) < 2:
            continue
        if callable(picker):
            try:
                kept = picker(controller, name, list(objs))
            except Exception:
                kept = None
            if kept not in objs:
                kept = None
        else:
            kept = None

        if kept is None:
            # Default: keep most-recent ETB (highest entered_zone_at). For PWs,
            # break ties by highest current loyalty so a freshly-resolved
            # ultimate doesn't lose to its sibling.
            from .types import CardType
            def _rank(o):
                ts = getattr(o, "entered_zone_at", 0) or 0
                loyalty = 0
                if CardType.PLANESWALKER in o.characteristics.types:
                    loyalty = int(o.state.counters.get("loyalty", 0))
                return (ts, loyalty)
            kept = max(objs, key=_rank)

        for obj in objs:
            if obj is kept:
                continue
            evt = Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': obj.id, 'reason': 'legend_rule',
                         'kept_id': kept.id, 'name': name},
                source=obj.id,
                controller=controller,
            )
            events.append(evt)
            marker = Event(
                type=EventType.LEGEND_RULE_TRIGGERED,
                payload={'object_id': obj.id, 'kept_id': kept.id, 'name': name},
                source=obj.id,
                controller=controller,
            )
            events.append(marker)
            if pipeline is not None:
                pipeline.emit(evt)
                pipeline.emit(marker)
    return events
