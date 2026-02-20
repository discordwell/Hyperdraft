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
        self.human_action_handler = None  # async fn(player_id, game_state) -> action_dict

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

        # If fatigue killed a player during draw, stop the turn immediately
        if self._is_game_over():
            return events

        # Main Phase (actions handled by player/AI, not automatic)
        self.hs_turn_state.phase = HearthstonePhase.MAIN
        events.extend(await self._run_main_phase_start())

        # Main phase: dispatch to AI or human handler based on active player
        active_pid = self.hs_turn_state.active_player_id
        is_ai = self._is_ai_player(active_pid)

        if is_ai and hasattr(self, 'hearthstone_ai_handler') and self.hearthstone_ai_handler:
            # AI turn — execute automatically
            ai_events = await self._run_ai_turn()
            events.extend(ai_events)
            await self._check_state_based_actions()
        elif not is_ai and self.human_action_handler:
            # Human turn — block until client sends actions
            human_events = await self._run_human_turn()
            events.extend(human_events)

        # End Phase (auto-end for AI, manual end handled inside _run_human_turn)
        if not self._is_game_over() and is_ai:
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

        # Apply Overload: lock mana from previous turn's overloaded cards
        if active_player.overloaded_mana > 0:
            active_player.mana_crystals_available = max(
                0, active_player.mana_crystals_available - active_player.overloaded_mana
            )
            active_player.overloaded_mana = 0

        # Reset combo counter
        active_player.cards_played_this_turn = 0

        # Reset hero power
        active_player.hero_power_used = False

        # Clear summoning sickness for active player's minions at turn start
        # (Freeze is handled at end of turn — see _run_end_phase)
        from .types import CardType
        battlefield = self.state.zones.get('battlefield')
        if battlefield:
            for obj_id in list(battlefield.objects):
                obj = self.state.objects.get(obj_id)
                if obj and obj.controller == active_player_id:
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

    async def _run_human_turn(self) -> list[Event]:
        """
        Run a human player's main phase via the action handler callback.

        Loops, calling human_action_handler to get each action, until
        the player sends HS_END_TURN or the game ends.
        """
        events = []
        player_id = self.hs_turn_state.active_player_id

        for _ in range(200):  # Safety cap
            if self._is_game_over():
                break

            # Wait for human input
            action = await self.human_action_handler(player_id, self.state)
            if action is None:
                break

            action_type = action.get('action_type', '')

            if action_type == 'HS_END_TURN':
                # End the turn
                events.extend(await self.end_turn())
                break

            elif action_type == 'HS_PLAY_CARD':
                card_id = action.get('card_id')
                if card_id:
                    play_events = await self._execute_human_card_play(card_id, player_id)
                    events.extend(play_events)

            elif action_type == 'HS_ATTACK':
                attacker_id = action.get('attacker_id')
                target_id = action.get('target_id')
                if attacker_id and target_id and self.combat_manager:
                    await self.combat_manager.declare_attack(attacker_id, target_id)

            elif action_type == 'HS_HERO_POWER':
                target_id = action.get('target_id')
                # use_hero_power is on the Game object, get it via pipeline
                game = None
                if hasattr(self, 'pipeline') and hasattr(self.pipeline, 'game'):
                    game = self.pipeline.game
                elif hasattr(self.state, '_game'):
                    game = self.state._game
                if game:
                    await game.use_hero_power(player_id, target_id)

            # Check SBAs after each action
            await self._check_state_based_actions()

        return events

    async def _execute_human_card_play(self, card_id: str, player_id: str) -> list[Event]:
        """
        Execute a card play from hand for a human player.

        Reuses the same event emission pattern as stormrift_play.py.
        """
        import re as _re
        events = []

        obj = self.state.objects.get(card_id)
        if not obj:
            return events

        player = self.state.players.get(player_id)
        if not player:
            return events

        # Calculate mana cost
        cost = 0
        if obj.characteristics and obj.characteristics.mana_cost:
            numbers = _re.findall(r'\{(\d+)\}', obj.characteristics.mana_cost)
            cost = sum(int(n) for n in numbers)

        # Check dynamic cost
        if obj.card_def and hasattr(obj.card_def, 'dynamic_cost') and obj.card_def.dynamic_cost:
            cost = obj.card_def.dynamic_cost(obj, self.state)

        # Apply cost modifiers
        for mod in player.cost_modifiers:
            if mod.get('amount'):
                cost = max(0, cost + mod['amount'])

        if player.mana_crystals_available < cost:
            return events

        from .types import CardType

        if CardType.MINION in obj.characteristics.types:
            # Check board limit (7 minions max)
            battlefield = self.state.zones.get('battlefield')
            if battlefield:
                my_minions = sum(
                    1 for oid in battlefield.objects
                    if oid in self.state.objects
                    and self.state.objects[oid].controller == player_id
                    and CardType.MINION in self.state.objects[oid].characteristics.types
                )
                if my_minions >= 7:
                    return events

            player.mana_crystals_available -= cost
            zone_event = Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': card_id,
                    'from_zone': f'hand_{player_id}',
                    'from_zone_type': ZoneType.HAND,
                    'to_zone': 'battlefield',
                    'to_zone_type': ZoneType.BATTLEFIELD,
                },
                source=card_id,
            )
            if self.pipeline:
                self.pipeline.emit(zone_event)
            events.append(zone_event)
            player.cards_played_this_turn += 1

        elif CardType.SPELL in obj.characteristics.types:
            player.mana_crystals_available -= cost

            spell_event = Event(
                type=EventType.SPELL_CAST,
                payload={'spell_id': card_id, 'caster': player_id},
                source=card_id,
            )
            if self.pipeline:
                self.pipeline.emit(spell_event)
            events.append(spell_event)

            # Execute spell effect
            card_def = obj.card_def
            if card_def and card_def.spell_effect:
                try:
                    if self.pipeline:
                        self.pipeline.sba_deferred = True
                    effect_events = card_def.spell_effect(obj, self.state, [])
                    for ev in effect_events:
                        if self.pipeline:
                            self.pipeline.emit(ev)
                        events.append(ev)
                finally:
                    if self.pipeline:
                        self.pipeline.sba_deferred = False
                await self._check_state_based_actions()

            # Move to graveyard
            zone_event = Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': card_id,
                    'from_zone': f'hand_{player_id}',
                    'from_zone_type': ZoneType.HAND,
                    'to_zone': f'graveyard_{player_id}',
                    'to_zone_type': ZoneType.GRAVEYARD,
                },
                source=card_id,
            )
            if self.pipeline:
                self.pipeline.emit(zone_event)
            events.append(zone_event)
            player.cards_played_this_turn += 1

        elif CardType.WEAPON in obj.characteristics.types:
            player.mana_crystals_available -= cost
            zone_event = Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': card_id,
                    'from_zone': f'hand_{player_id}',
                    'from_zone_type': ZoneType.HAND,
                    'to_zone': 'battlefield',
                    'to_zone_type': ZoneType.BATTLEFIELD,
                },
                source=card_id,
            )
            if self.pipeline:
                self.pipeline.emit(zone_event)
            events.append(zone_event)
            player.cards_played_this_turn += 1

        # SBA check after play
        await self._check_state_based_actions()

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

        # Clear 'this_turn' cost modifiers for the active player
        active_player = self.state.players.get(self.hs_turn_state.active_player_id)
        if active_player:
            active_player.cost_modifiers = [
                m for m in active_player.cost_modifiers
                if m.get('duration') != 'this_turn'
            ]

        # Clean up temporary hero attack (Druid Shapeshift "+1 Attack this turn")
        if active_player and getattr(active_player, '_shapeshift_attack', False):
            active_player._shapeshift_attack = False
            pre_attack = getattr(active_player, '_pre_shapeshift_weapon_attack', None)
            if hasattr(active_player, '_pre_shapeshift_weapon_attack'):
                del active_player._pre_shapeshift_weapon_attack

            # Check if a real weapon card is on the battlefield for this player
            from .types import CardType
            real_weapon = None
            battlefield = self.state.zones.get('battlefield')
            if battlefield:
                for card_id in battlefield.objects:
                    card = self.state.objects.get(card_id)
                    if (card and card.controller == self.hs_turn_state.active_player_id and
                            CardType.WEAPON in card.characteristics.types):
                        real_weapon = card
                        break

            if real_weapon:
                # Only remove the +1 bonus if weapon_attack still includes it.
                # If a new weapon was equipped after Shapeshift, the bonus was
                # overwritten and we should not subtract from the new weapon.
                if pre_attack is not None and active_player.weapon_attack == pre_attack + 1:
                    active_player.weapon_attack = pre_attack
                # else: weapon was replaced after Shapeshift, don't touch it
                if active_player.hero_id:
                    hero = self.state.objects.get(active_player.hero_id)
                    if hero:
                        hero.state.weapon_attack = active_player.weapon_attack
                        hero.state.weapon_durability = active_player.weapon_durability
            else:
                # No real weapon - zero out the temporary attack
                active_player.weapon_attack = 0
                active_player.weapon_durability = 0
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

        # Unfreeze characters that didn't attack this turn.
        # In Hearthstone, freeze wears off at the END of the frozen character's
        # controller's turn — not at the start. This ensures a frozen minion
        # misses a full turn of attacks before unfreezing.
        battlefield = self.state.zones.get('battlefield')
        if battlefield:
            for obj_id in list(battlefield.objects):
                obj = self.state.objects.get(obj_id)
                if (obj and obj.controller == self.hs_turn_state.active_player_id
                        and obj.state.frozen):
                    # Only unfreeze if the character didn't attack this turn.
                    # If it attacked AND got frozen (e.g. Water Elemental), it
                    # stays frozen through the next turn.
                    if obj.state.attacks_this_turn == 0:
                        obj.state.frozen = False

        # Reset combat state for active player only (must be AFTER freeze check)
        if self.combat_manager:
            self.combat_manager.reset_combat(player_id=self.hs_turn_state.active_player_id)

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

        Loops until stable because deathrattles can deal hero damage
        (e.g. Abomination) or spawn new minions that die immediately.

        When pipeline.sba_deferred is True, returns immediately so that
        AOE damage can resolve simultaneously before deaths are checked.
        """
        if self.pipeline and self.pipeline.sba_deferred:
            return

        from .queries import get_toughness, is_creature

        for _ in range(20):  # Safety cap to prevent infinite loops
            changed = False

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
                    changed = True

            # Check minion health
            battlefield = self.state.zones.get('battlefield')
            if battlefield:
                for obj_id in list(battlefield.objects):
                    obj = self.state.objects.get(obj_id)
                    if not obj:
                        continue
                    # Guard: a deathrattle from a previously-processed death in this
                    # same SBA pass may have already destroyed this minion (e.g. via
                    # direct OBJECT_DESTROYED). Skip objects no longer on battlefield.
                    if obj.zone != ZoneType.BATTLEFIELD:
                        continue
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
                            changed = True

            if not changed:
                break

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

    def _is_game_over(self) -> bool:
        """Check if the game is over (any player has lost)."""
        alive = [p for p in self.state.players.values() if not p.has_lost]
        return len(alive) <= 1

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
    def phase(self) -> Phase:
        """Map Hearthstone phases to MTG Phase enum for client compatibility."""
        phase_to_mtg = {
            HearthstonePhase.DRAW: Phase.BEGINNING,
            HearthstonePhase.MAIN: Phase.PRECOMBAT_MAIN,
            HearthstonePhase.END: Phase.ENDING,
        }
        return phase_to_mtg.get(self.hs_turn_state.phase, Phase.PRECOMBAT_MAIN)

    @property
    def step(self) -> Step:
        """Map Hearthstone phases to Step enum for client compatibility."""
        phase_to_step = {
            HearthstonePhase.DRAW: Step.DRAW,
            HearthstonePhase.MAIN: Step.MAIN,
            HearthstonePhase.END: Step.END_STEP,
        }
        return phase_to_step.get(self.hs_turn_state.phase, Step.MAIN)
