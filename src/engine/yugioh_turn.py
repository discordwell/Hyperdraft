"""
Yu-Gi-Oh! Turn Manager

Turn structure:
1. Draw Phase (draw 1 card, deck-out = lose)
2. Standby Phase (resolve mandatory effects)
3. Main Phase 1 (summon, set, activate spells/traps)
4. Battle Phase (declare attacks — skipped on first turn)
   - Battle Start Step
   - Battle Step (declare attack)
   - Damage Step (damage calculation)
   - Battle End Step
5. Main Phase 2 (same as Main Phase 1)
6. End Phase (discard to hand limit, resolve end-of-turn effects)

Per-turn limits: 1 Normal Summon/Set, position changes tracked per monster.
"""

import random
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
from enum import Enum, auto

from .types import (
    GameState, Event, EventType, ZoneType, CardType, new_id
)
from .turn import TurnManager, Phase, Step, TurnState
from .yugioh_types import YGOPhase, STARTING_HAND_SIZE, STARTING_LP, MAX_HAND_SIZE

if TYPE_CHECKING:
    from .priority import PrioritySystem
    from .combat import CombatManager
    from .pipeline import EventPipeline


@dataclass
class YugiohTurnState:
    """Turn state for Yu-Gi-Oh! mode."""
    turn_number: int = 0
    active_player_id: Optional[str] = None
    phase: YGOPhase = YGOPhase.DRAW
    game_turn_count: int = 0  # Total turns played (for first-turn restriction)
    first_player_id: Optional[str] = None  # Who went first

    # Per-turn tracking
    normal_summon_used: bool = False
    battle_phase_entered: bool = False
    position_changes: dict = field(default_factory=dict)  # monster_id -> bool
    attacks_declared: dict = field(default_factory=dict)  # monster_id -> int


class YugiohTurnManager(TurnManager):
    """
    Yu-Gi-Oh! turn manager.

    Key differences from MTG/HS:
    - Draw 1 card (deck-out = instant loss)
    - No mana system
    - Normal Summon limited to 1 per turn
    - Battle Phase skipped on first turn
    - Chain system for responses (handled by chain manager)
    """

    def __init__(self, state: GameState):
        super().__init__(state)
        self.ygo_turn_state = YugiohTurnState()
        self.ygo_ai_handler = None
        self.ai_players: set[str] = set()
        self.human_action_handler = None  # async fn(player_id, game_state) -> action_dict
        self._chain_manager = None  # Set by Game._connect_subsystems
        self.action_log_callback = None  # fn(text, event_type, player_id) — set by session for AI logging

    def set_ai_handler(self, handler):
        """Set the AI handler for YGO turns."""
        self.ygo_ai_handler = handler

    async def setup_game(self) -> list[Event]:
        """
        Yu-Gi-Oh! game setup:
        1. Both players shuffle decks
        2. Both draw 5 cards
        3. Coin flip for first player (winner chooses, we default to winner goes first)
        4. First player skips their Draw Phase on turn 1
        """
        events = []
        player_ids = list(self.state.players.keys())
        if len(player_ids) < 2:
            return events

        # Shuffle decks
        for pid in player_ids:
            library_key = f"library_{pid}"
            if library_key in self.state.zones:
                zone = self.state.zones[library_key]
                random.shuffle(zone.objects)

        # Draw starting hands (5 cards each)
        for pid in player_ids:
            self._draw_cards(pid, STARTING_HAND_SIZE)

        # Coin flip — random first player
        first_player = random.choice(player_ids)
        second_player = next(pid for pid in player_ids if pid != first_player)

        self.ygo_turn_state.first_player_id = first_player
        self.ygo_turn_state.active_player_id = first_player
        self.state.active_player = first_player
        self.turn_state.active_player_id = first_player

        # Set turn order
        self._turn_order = [first_player, second_player]

        events.append(Event(
            type=EventType.GAME_START,
            payload={'first_player': first_player}
        ))

        return events

    def _draw_cards(self, player_id: str, count: int):
        """Draw cards from library to hand."""
        library_key = f"library_{player_id}"
        hand_key = f"hand_{player_id}"
        library = self.state.zones.get(library_key)
        hand = self.state.zones.get(hand_key)
        if not library or not hand:
            return

        for _ in range(count):
            if not library.objects:
                # Deck-out
                player = self.state.players.get(player_id)
                if player:
                    player.has_lost = True
                return
            obj_id = library.objects.pop(0)
            hand.objects.append(obj_id)
            obj = self.state.objects.get(obj_id)
            if obj:
                obj.zone = ZoneType.HAND

    async def run_turn(self) -> list[Event]:
        """Run a single turn for the active player."""
        events = []
        pid = self.ygo_turn_state.active_player_id
        if not pid:
            return events

        self.ygo_turn_state.turn_number += 1
        self.ygo_turn_state.game_turn_count += 1
        self.state.turn_number = self.ygo_turn_state.turn_number
        self.turn_state.turn_number = self.ygo_turn_state.turn_number
        self.state.active_player = pid
        self.turn_state.active_player_id = pid
        self._end_turn_requested = False

        # Reset per-turn state
        self.ygo_turn_state.normal_summon_used = False
        self.ygo_turn_state.battle_phase_entered = False
        self.ygo_turn_state.position_changes.clear()
        self.ygo_turn_state.attacks_declared.clear()

        # Reset per-turn player state
        player = self.state.players.get(pid)
        if player:
            player.normal_summon_used = False

        # Increment turns_set for all set spell/trap cards
        self._increment_set_turns()

        events.append(Event(
            type=EventType.TURN_START,
            payload={'player': pid, 'turn': self.ygo_turn_state.turn_number}
        ))

        # Log turn start for AI turns
        if pid in self.ai_players and self.action_log_callback:
            player_name = player.name if player else "AI"
            self.action_log_callback(
                f"Turn {self.ygo_turn_state.turn_number} - {player_name}'s turn.",
                "turn_start", pid
            )

        # === Draw Phase ===
        # First player skips draw on their first turn
        is_very_first_turn = (self.ygo_turn_state.game_turn_count == 1)
        if not is_very_first_turn:
            self.ygo_turn_state.phase = YGOPhase.DRAW
            self._draw_cards(pid, 1)

            # Check deck-out
            if player and player.has_lost:
                return events

            events.append(Event(
                type=EventType.YGO_DRAW,
                payload={'player': pid}
            ))

        # === Standby Phase ===
        self.ygo_turn_state.phase = YGOPhase.STANDBY
        events.append(Event(
            type=EventType.PHASE_START,
            payload={'phase': 'standby', 'player': pid}
        ))

        # === Main Phase 1 ===
        self.ygo_turn_state.phase = YGOPhase.MAIN1
        events.extend(await self._run_main_phase(pid))

        if self._check_game_over():
            return events

        # === Battle Phase (skipped on very first turn and if end_turn requested) ===
        if not is_very_first_turn and not self._end_turn_requested:
            if self._should_enter_battle_phase(pid):
                self.ygo_turn_state.battle_phase_entered = True
                events.extend(await self._run_battle_phase(pid))

            if self._check_game_over():
                return events

        # === Main Phase 2 (skipped if end_turn requested) ===
        if not self._end_turn_requested:
            self.ygo_turn_state.phase = YGOPhase.MAIN2
            events.extend(await self._run_main_phase(pid))

            if self._check_game_over():
                return events

        # === End Phase ===
        self.ygo_turn_state.phase = YGOPhase.END
        events.extend(self._run_end_phase(pid))

        events.append(Event(
            type=EventType.TURN_END,
            payload={'player': pid}
        ))

        # Switch to next player
        self._advance_turn()

        return events

    async def _run_main_phase(self, player_id: str) -> list[Event]:
        """Run a main phase — player can take actions until they choose to move on."""
        events = []
        is_ai = player_id in self.ai_players

        while True:
            if self._check_game_over():
                break

            if is_ai and self.ygo_ai_handler:
                action = self.ygo_ai_handler.get_main_phase_action(
                    player_id, self.state, self.ygo_turn_state
                )
            elif self.human_action_handler:
                action = await self.human_action_handler(player_id, self.state)
            else:
                action = {'action_type': 'end_phase'}

            if not action or action.get('action_type') in ('end_phase', 'end_turn'):
                if action and action.get('action_type') == 'end_turn':
                    self._end_turn_requested = True
                break

            result = self._execute_action(player_id, action)
            events.extend(result)

        return events

    async def _run_battle_phase(self, player_id: str) -> list[Event]:
        """Run the Battle Phase with sub-steps."""
        events = []
        opponent_id = self._get_opponent(player_id)
        is_ai = player_id in self.ai_players

        # Battle Start Step
        self.ygo_turn_state.phase = YGOPhase.BATTLE_START
        events.append(Event(
            type=EventType.PHASE_START,
            payload={'phase': 'battle_start', 'player': player_id}
        ))

        # Battle Step loop — declare attacks one at a time
        while True:
            if self._check_game_over():
                break

            self.ygo_turn_state.phase = YGOPhase.BATTLE_STEP

            if is_ai and self.ygo_ai_handler:
                action = self.ygo_ai_handler.get_battle_action(
                    player_id, self.state, self.ygo_turn_state
                )
            elif self.human_action_handler:
                action = await self.human_action_handler(player_id, self.state)
            else:
                action = {'action_type': 'end_phase'}

            if not action or action.get('action_type') in ('end_phase', 'end_turn'):
                if action and action.get('action_type') == 'end_turn':
                    self._end_turn_requested = True
                break

            if action.get('action_type') == 'declare_attack':
                attack_events = self._resolve_attack(
                    player_id,
                    action.get('attacker_id'),
                    action.get('target_id'),
                    opponent_id
                )
                events.extend(attack_events)

                # Log AI attacks
                if attack_events and self.action_log_callback and player_id in self.ai_players:
                    attacker_obj = self.state.objects.get(action.get('attacker_id'))
                    attacker_name = attacker_obj.name if attacker_obj else "a monster"
                    target_id = action.get('target_id')
                    if target_id is None:
                        self.action_log_callback(f"{attacker_name} attacks directly!", "attack", player_id)
                    else:
                        target_obj = self.state.objects.get(target_id)
                        target_name = target_obj.name if target_obj else "a monster"
                        self.action_log_callback(f"{attacker_name} attacks {target_name}!", "attack", player_id)
                    # Log battle damage
                    for evt in attack_events:
                        if evt.type == EventType.YGO_BATTLE_DAMAGE:
                            amount = evt.payload.get('amount', 0)
                            dmg_player = evt.payload.get('player')
                            if amount > 0:
                                self.action_log_callback(f"{amount} battle damage!", "damage", dmg_player)

        # Battle End Step
        self.ygo_turn_state.phase = YGOPhase.BATTLE_END
        events.append(Event(
            type=EventType.PHASE_START,
            payload={'phase': 'battle_end', 'player': player_id}
        ))

        return events

    def _run_end_phase(self, player_id: str) -> list[Event]:
        """Run End Phase — discard to hand limit, clean up."""
        events = []
        hand_key = f"hand_{player_id}"
        hand = self.state.zones.get(hand_key)
        if hand and len(hand.objects) > MAX_HAND_SIZE:
            # Discard excess cards (AI: discard worst; for now: discard from end)
            while len(hand.objects) > MAX_HAND_SIZE:
                obj_id = hand.objects.pop()
                gy_key = f"graveyard_{player_id}"
                gy = self.state.zones.get(gy_key)
                if gy:
                    gy.objects.append(obj_id)
                obj = self.state.objects.get(obj_id)
                if obj:
                    obj.zone = ZoneType.GRAVEYARD
                events.append(Event(
                    type=EventType.DISCARD,
                    payload={'player': player_id, 'card_id': obj_id}
                ))

        # Clean up end-of-turn effects
        self._cleanup_end_of_turn()

        return events

    def _execute_action(self, player_id: str, action: dict) -> list[Event]:
        """Execute a player action during a main phase."""
        events = []
        action_type = action.get('action_type')

        if action_type == 'normal_summon':
            events.extend(self._do_normal_summon(player_id, action))
        elif action_type == 'set_monster':
            events.extend(self._do_set_monster(player_id, action))
        elif action_type == 'flip_summon':
            events.extend(self._do_flip_summon(player_id, action))
        elif action_type == 'change_position':
            events.extend(self._do_change_position(player_id, action))
        elif action_type == 'activate_spell':
            events.extend(self._do_activate_spell(player_id, action))
        elif action_type == 'set_spell_trap':
            events.extend(self._do_set_spell_trap(player_id, action))
        elif action_type == 'special_summon':
            events.extend(self._do_special_summon(player_id, action))

        # Log AI actions via callback
        if events and self.action_log_callback and player_id in self.ai_players:
            self._log_ai_action(player_id, action, events)

        return events

    def _log_ai_action(self, player_id: str, action: dict, events: list[Event]):
        """Log an AI action via the session callback."""
        cb = self.action_log_callback
        if not cb:
            return
        action_type = action.get('action_type')
        card_id = action.get('card_id')
        card_name = None
        if card_id:
            obj = self.state.objects.get(card_id)
            if obj:
                card_name = obj.name

        player = self.state.players.get(player_id)
        name = player.name if player else "AI"

        if action_type == 'normal_summon':
            cb(f"{name} Normal Summoned {card_name or 'a monster'}!", "summon", player_id)
        elif action_type == 'set_monster':
            cb(f"{name} set a monster.", "set", player_id)
        elif action_type == 'flip_summon':
            cb(f"{name} Flip Summoned {card_name or 'a monster'}!", "summon", player_id)
        elif action_type == 'activate_spell':
            cb(f"{name} activated {card_name or 'a card'}!", "activate", player_id)
        elif action_type == 'set_spell_trap':
            cb(f"{name} set a card.", "set", player_id)
        elif action_type == 'change_position':
            cb(f"{name} changed {card_name or 'a monster'}'s position.", "position", player_id)
        elif action_type == 'special_summon':
            cb(f"{name} Special Summoned {card_name or 'a monster'}!", "summon", player_id)

    # === Normal Summon / Tribute Summon ===

    def _do_normal_summon(self, player_id: str, action: dict) -> list[Event]:
        """Normal Summon (or Tribute Summon for level 5+)."""
        events = []
        card_id = action.get('card_id')

        if self.ygo_turn_state.normal_summon_used:
            return events  # Already used normal summon

        obj = self.state.objects.get(card_id)
        if not obj or obj.zone != ZoneType.HAND or obj.controller != player_id:
            return events

        card_def = obj.card_def
        if not card_def:
            return events

        level = getattr(card_def, 'level', 0) or 0

        # Check tributes needed
        tributes_needed = 0
        if level >= 5:
            tributes_needed = 1
        if level >= 7:
            tributes_needed = 2

        # Perform tributes
        tribute_ids = action.get('tribute_ids', [])
        if len(tribute_ids) < tributes_needed:
            return events  # Not enough tributes

        for tid in tribute_ids:
            self._send_to_graveyard(tid, player_id)

        # Move from hand to monster zone
        slot = self._find_empty_monster_slot(player_id)
        if slot is None:
            return events  # No space

        self._move_to_monster_zone(card_id, player_id, slot)
        obj.state.ygo_position = 'face_up_atk'
        obj.state.face_down = False

        self.ygo_turn_state.normal_summon_used = True
        player = self.state.players.get(player_id)
        if player:
            player.normal_summon_used = True

        event_type = EventType.YGO_TRIBUTE_SUMMON if tributes_needed > 0 else EventType.YGO_NORMAL_SUMMON
        events.append(Event(
            type=event_type,
            payload={
                'player': player_id,
                'card_id': card_id,
                'card_name': obj.name,
                'tributes': tribute_ids,
            },
            source=card_id,
            controller=player_id,
        ))

        return events

    # === Set Monster ===

    def _do_set_monster(self, player_id: str, action: dict) -> list[Event]:
        """Set a monster face-down in Defense Position."""
        events = []
        card_id = action.get('card_id')

        if self.ygo_turn_state.normal_summon_used:
            return events

        obj = self.state.objects.get(card_id)
        if not obj or obj.zone != ZoneType.HAND or obj.controller != player_id:
            return events

        card_def = obj.card_def
        if not card_def:
            return events

        level = getattr(card_def, 'level', 0) or 0

        # Tribute for level 5+
        tributes_needed = 0
        if level >= 5:
            tributes_needed = 1
        if level >= 7:
            tributes_needed = 2

        tribute_ids = action.get('tribute_ids', [])
        if len(tribute_ids) < tributes_needed:
            return events

        for tid in tribute_ids:
            self._send_to_graveyard(tid, player_id)

        slot = self._find_empty_monster_slot(player_id)
        if slot is None:
            return events

        self._move_to_monster_zone(card_id, player_id, slot)
        obj.state.ygo_position = 'face_down_def'
        obj.state.face_down = True
        obj.state.turns_set = 0

        self.ygo_turn_state.normal_summon_used = True
        player = self.state.players.get(player_id)
        if player:
            player.normal_summon_used = True

        events.append(Event(
            type=EventType.YGO_SET_MONSTER,
            payload={
                'player': player_id,
                'card_id': card_id,
            },
            source=card_id,
            controller=player_id,
        ))

        return events

    # === Flip Summon ===

    def _do_flip_summon(self, player_id: str, action: dict) -> list[Event]:
        """Flip Summon a face-down Defense Position monster."""
        events = []
        card_id = action.get('card_id')

        obj = self.state.objects.get(card_id)
        if not obj or obj.controller != player_id:
            return events

        if obj.state.ygo_position != 'face_down_def':
            return events

        # Cannot flip summon the turn it was set
        if obj.state.turns_set < 1:
            return events

        obj.state.ygo_position = 'face_up_atk'
        obj.state.face_down = False
        obj.state.flip_summoned = True

        events.append(Event(
            type=EventType.YGO_FLIP_SUMMON,
            payload={
                'player': player_id,
                'card_id': card_id,
                'card_name': obj.name,
            },
            source=card_id,
            controller=player_id,
        ))

        # Trigger flip effect
        if obj.card_def and getattr(obj.card_def, 'flip_effect', None):
            events.append(Event(
                type=EventType.YGO_FLIP,
                payload={
                    'card_id': card_id,
                    'card_name': obj.name,
                },
                source=card_id,
                controller=player_id,
            ))

        return events

    # === Change Position ===

    def _do_change_position(self, player_id: str, action: dict) -> list[Event]:
        """Change a monster's battle position."""
        events = []
        card_id = action.get('card_id')

        obj = self.state.objects.get(card_id)
        if not obj or obj.controller != player_id:
            return events

        if self.ygo_turn_state.position_changes.get(card_id):
            return events  # Already changed this turn

        old_position = obj.state.ygo_position
        if old_position == 'face_up_atk':
            obj.state.ygo_position = 'face_up_def'
        elif old_position == 'face_up_def':
            obj.state.ygo_position = 'face_up_atk'
        else:
            return events  # Can't manually change face-down

        self.ygo_turn_state.position_changes[card_id] = True

        events.append(Event(
            type=EventType.YGO_POSITION_CHANGE,
            payload={
                'card_id': card_id,
                'old_position': old_position,
                'new_position': obj.state.ygo_position,
            },
            source=card_id,
            controller=player_id,
        ))

        return events

    # === Activate Spell ===

    def _do_activate_spell(self, player_id: str, action: dict) -> list[Event]:
        """Activate a Spell card from hand or field."""
        events = []
        card_id = action.get('card_id')

        obj = self.state.objects.get(card_id)
        if not obj or obj.controller != player_id:
            return events

        card_def = obj.card_def
        if not card_def:
            return events

        # Resolve spell effect
        if card_def.resolve:
            result_events = card_def.resolve(
                Event(type=EventType.YGO_ACTIVATE_SPELL,
                      payload={'card_id': card_id, 'player': player_id},
                      source=card_id, controller=player_id),
                self.state
            )
            events.extend(result_events or [])

        # Normal spells go to GY after resolution
        spell_type = getattr(card_def, 'ygo_spell_type', None)
        if spell_type in (None, 'Normal'):
            if obj.zone == ZoneType.HAND:
                self._remove_from_current_zone(card_id)
            self._send_to_graveyard(card_id, player_id)

        events.append(Event(
            type=EventType.YGO_ACTIVATE_SPELL,
            payload={
                'player': player_id,
                'card_id': card_id,
                'card_name': obj.name,
            },
            source=card_id,
            controller=player_id,
        ))

        return events

    # === Set Spell/Trap ===

    def _do_set_spell_trap(self, player_id: str, action: dict) -> list[Event]:
        """Set a Spell or Trap card face-down in the Spell/Trap Zone."""
        events = []
        card_id = action.get('card_id')

        obj = self.state.objects.get(card_id)
        if not obj or obj.zone != ZoneType.HAND or obj.controller != player_id:
            return events

        slot = self._find_empty_spell_trap_slot(player_id)
        if slot is None:
            return events

        self._move_to_spell_trap_zone(card_id, player_id, slot)
        obj.state.face_down = True
        obj.state.turns_set = 0

        events.append(Event(
            type=EventType.YGO_SET_SPELL_TRAP,
            payload={
                'player': player_id,
                'card_id': card_id,
            },
            source=card_id,
            controller=player_id,
        ))

        return events

    # === Special Summon (generic) ===

    def _do_special_summon(self, player_id: str, action: dict) -> list[Event]:
        """Generic special summon — used by effects and extra deck mechanics."""
        events = []
        card_id = action.get('card_id')
        position = action.get('position', 'face_up_atk')

        obj = self.state.objects.get(card_id)
        if not obj:
            return events

        slot = self._find_empty_monster_slot(player_id)
        if slot is None:
            return events

        self._remove_from_current_zone(card_id)
        self._move_to_monster_zone(card_id, player_id, slot)
        obj.state.ygo_position = position
        obj.state.face_down = (position == 'face_down_def')
        obj.controller = player_id

        events.append(Event(
            type=EventType.YGO_SPECIAL_SUMMON,
            payload={
                'player': player_id,
                'card_id': card_id,
                'card_name': obj.name,
                'position': position,
            },
            source=card_id,
            controller=player_id,
        ))

        return events

    # === Attack Resolution ===

    def _resolve_attack(self, attacker_pid: str, attacker_id: str,
                        target_id: Optional[str], opponent_id: str) -> list[Event]:
        """Resolve a single attack declaration and damage."""
        events = []
        combat = getattr(self, 'combat_manager', None)
        if not combat:
            # Fallback to inline combat if no combat manager wired
            return self._inline_resolve_attack(attacker_pid, attacker_id, target_id, opponent_id)

        return combat.resolve_attack(attacker_pid, attacker_id, target_id, opponent_id)

    def _inline_resolve_attack(self, attacker_pid: str, attacker_id: str,
                                target_id: Optional[str], opponent_id: str) -> list[Event]:
        """Inline attack resolution (used when combat manager not yet wired)."""
        events = []
        attacker = self.state.objects.get(attacker_id)
        if not attacker:
            return events

        # Must be face-up ATK to attack
        if getattr(attacker.state, 'ygo_position', None) != 'face_up_atk':
            return events

        # Track attack
        self.ygo_turn_state.attacks_declared[attacker_id] = \
            self.ygo_turn_state.attacks_declared.get(attacker_id, 0) + 1

        atk_val = getattr(attacker.card_def, 'atk', 0) or 0

        if target_id is None:
            # Direct attack
            opponent = self.state.players.get(opponent_id)
            if opponent:
                opponent.lp = max(0, opponent.lp - atk_val)
                events.append(Event(
                    type=EventType.YGO_BATTLE_DAMAGE,
                    payload={
                        'player': opponent_id,
                        'amount': atk_val,
                        'source': attacker_id,
                        'direct': True,
                    }
                ))
                if opponent.lp <= 0:
                    opponent.has_lost = True
        else:
            # Attack a monster
            defender = self.state.objects.get(target_id)
            if not defender:
                return events

            # Flip face-down defenders
            if defender.state.face_down:
                defender.state.face_down = False
                if defender.state.ygo_position == 'face_down_def':
                    defender.state.ygo_position = 'face_up_def'
                events.append(Event(
                    type=EventType.YGO_FLIP,
                    payload={'card_id': target_id, 'card_name': defender.name}
                ))

            def_atk = getattr(defender.card_def, 'atk', 0) or 0
            def_def = getattr(defender.card_def, 'def_val', 0) or 0

            if defender.state.ygo_position == 'face_up_atk':
                # ATK vs ATK
                if atk_val > def_atk:
                    damage = atk_val - def_atk
                    self._destroy_monster(target_id, opponent_id)
                    opp = self.state.players.get(opponent_id)
                    if opp:
                        opp.lp = max(0, opp.lp - damage)
                    events.append(Event(
                        type=EventType.YGO_BATTLE_DAMAGE,
                        payload={'player': opponent_id, 'amount': damage, 'source': attacker_id}
                    ))
                elif atk_val == def_atk:
                    self._destroy_monster(attacker_id, attacker_pid)
                    self._destroy_monster(target_id, opponent_id)
                else:
                    damage = def_atk - atk_val
                    self._destroy_monster(attacker_id, attacker_pid)
                    p = self.state.players.get(attacker_pid)
                    if p:
                        p.lp = max(0, p.lp - damage)
                    events.append(Event(
                        type=EventType.YGO_BATTLE_DAMAGE,
                        payload={'player': attacker_pid, 'amount': damage, 'source': target_id}
                    ))
            else:
                # ATK vs DEF
                if atk_val > def_def:
                    self._destroy_monster(target_id, opponent_id)
                    # No battle damage
                elif atk_val == def_def:
                    pass  # No destruction, no damage
                else:
                    damage = def_def - atk_val
                    p = self.state.players.get(attacker_pid)
                    if p:
                        p.lp = max(0, p.lp - damage)
                    events.append(Event(
                        type=EventType.YGO_BATTLE_DAMAGE,
                        payload={'player': attacker_pid, 'amount': damage, 'source': target_id}
                    ))

            # Check for LP loss
            for pid in [attacker_pid, opponent_id]:
                p = self.state.players.get(pid)
                if p and p.lp <= 0:
                    p.has_lost = True

        events.append(Event(
            type=EventType.YGO_BATTLE_DECLARE,
            payload={
                'attacker_id': attacker_id,
                'target_id': target_id,
                'attacker_player': attacker_pid,
            }
        ))

        return events

    # === Zone Helpers ===

    def _find_empty_monster_slot(self, player_id: str) -> Optional[int]:
        """Find an empty monster zone slot (0-4)."""
        zone_key = f"monster_zone_{player_id}"
        zone = self.state.zones.get(zone_key)
        if not zone:
            return None
        # Zone stores obj IDs; empty slots are None
        for i in range(5):
            if i >= len(zone.objects) or zone.objects[i] is None:
                return i
        if len(zone.objects) < 5:
            return len(zone.objects)
        return None

    def _find_empty_spell_trap_slot(self, player_id: str) -> Optional[int]:
        """Find an empty spell/trap zone slot (0-4)."""
        zone_key = f"spell_trap_zone_{player_id}"
        zone = self.state.zones.get(zone_key)
        if not zone:
            return None
        for i in range(5):
            if i >= len(zone.objects) or zone.objects[i] is None:
                return i
        if len(zone.objects) < 5:
            return len(zone.objects)
        return None

    def _move_to_monster_zone(self, card_id: str, player_id: str, slot: int):
        """Move a card into a monster zone slot."""
        self._remove_from_current_zone(card_id)
        zone_key = f"monster_zone_{player_id}"
        zone = self.state.zones.get(zone_key)
        if zone:
            # Extend zone if needed
            while len(zone.objects) <= slot:
                zone.objects.append(None)
            zone.objects[slot] = card_id
        obj = self.state.objects.get(card_id)
        if obj:
            obj.zone = ZoneType.MONSTER_ZONE

    def _move_to_spell_trap_zone(self, card_id: str, player_id: str, slot: int):
        """Move a card into a spell/trap zone slot."""
        self._remove_from_current_zone(card_id)
        zone_key = f"spell_trap_zone_{player_id}"
        zone = self.state.zones.get(zone_key)
        if zone:
            while len(zone.objects) <= slot:
                zone.objects.append(None)
            zone.objects[slot] = card_id
        obj = self.state.objects.get(card_id)
        if obj:
            obj.zone = ZoneType.SPELL_TRAP_ZONE

    def _remove_from_current_zone(self, card_id: str):
        """Remove a card from whatever zone it's currently in."""
        for zone_key, zone in self.state.zones.items():
            if card_id in zone.objects:
                # Slotted zones (monster/spell-trap): replace with None to preserve slots
                if 'monster_zone_' in zone_key or 'spell_trap_zone_' in zone_key:
                    for i, oid in enumerate(zone.objects):
                        if oid == card_id:
                            zone.objects[i] = None
                            break
                else:
                    # List-style zones (hand, graveyard, library, etc.): remove entirely
                    while card_id in zone.objects:
                        zone.objects.remove(card_id)
                break

    def _send_to_graveyard(self, card_id: str, player_id: str):
        """Send a card to its owner's graveyard."""
        self._remove_from_current_zone(card_id)
        gy_key = f"graveyard_{player_id}"
        gy = self.state.zones.get(gy_key)
        if gy:
            gy.objects.append(card_id)
        obj = self.state.objects.get(card_id)
        if obj:
            obj.zone = ZoneType.GRAVEYARD
            obj.state.face_down = False
            obj.state.ygo_position = None

    def _destroy_monster(self, card_id: str, owner_id: str):
        """Destroy a monster — send to GY."""
        obj = self.state.objects.get(card_id)
        if not obj:
            return
        self._send_to_graveyard(card_id, obj.owner)

    def _increment_set_turns(self):
        """Increment turns_set on all face-down cards controlled by active player."""
        pid = self.ygo_turn_state.active_player_id
        for zone_key in [f"monster_zone_{pid}", f"spell_trap_zone_{pid}"]:
            zone = self.state.zones.get(zone_key)
            if not zone:
                continue
            for obj_id in zone.objects:
                if obj_id is None:
                    continue
                obj = self.state.objects.get(obj_id)
                if obj and obj.state.face_down:
                    obj.state.turns_set = getattr(obj.state, 'turns_set', 0) + 1

    def _cleanup_end_of_turn(self):
        """Clean up end-of-turn temporary effects."""
        pass  # Will be expanded in Stage 2

    def _should_enter_battle_phase(self, player_id: str) -> bool:
        """Check if player wants to enter battle phase."""
        is_ai = player_id in self.ai_players
        if is_ai and self.ygo_ai_handler:
            return self.ygo_ai_handler.should_enter_battle(player_id, self.state)
        # For humans, battle phase entry is handled by the action system
        return True

    def _get_opponent(self, player_id: str) -> str:
        """Get the opponent's player ID."""
        for pid in self.state.players:
            if pid != player_id:
                return pid
        return ""

    def _advance_turn(self):
        """Switch to the next player's turn."""
        player_ids = list(self.state.players.keys())
        current_idx = player_ids.index(self.ygo_turn_state.active_player_id) if self.ygo_turn_state.active_player_id in player_ids else 0
        next_idx = (current_idx + 1) % len(player_ids)
        self.ygo_turn_state.active_player_id = player_ids[next_idx]
        self.state.active_player = player_ids[next_idx]
        self.turn_state.active_player_id = player_ids[next_idx]

    def _check_game_over(self) -> bool:
        """Check if any player has lost."""
        for player in self.state.players.values():
            if player.has_lost:
                return True
        return False

    def get_monsters_on_field(self, player_id: str) -> list:
        """Get all monster objects on a player's field."""
        zone_key = f"monster_zone_{player_id}"
        zone = self.state.zones.get(zone_key)
        if not zone:
            return []
        monsters = []
        for obj_id in zone.objects:
            if obj_id is None:
                continue
            obj = self.state.objects.get(obj_id)
            if obj:
                monsters.append(obj)
        return monsters

    def get_spell_traps_on_field(self, player_id: str) -> list:
        """Get all spell/trap objects on a player's field."""
        zone_key = f"spell_trap_zone_{player_id}"
        zone = self.state.zones.get(zone_key)
        if not zone:
            return []
        cards = []
        for obj_id in zone.objects:
            if obj_id is None:
                continue
            obj = self.state.objects.get(obj_id)
            if obj:
                cards.append(obj)
        return cards
