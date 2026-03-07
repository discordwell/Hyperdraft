"""
Yu-Gi-Oh! AI Adapter

Adapts the AI system to play Yu-Gi-Oh! using the engine's turn structure.
Translates board state into decisions for summoning, spell/trap activation,
attack declarations, and chain responses.

Supports difficulty levels (easy, medium, hard, ultra) with progressively
smarter resource management, combat math, and chain evaluation.
"""
import random
from typing import Optional, TYPE_CHECKING

from src.engine.types import (
    GameState, ZoneType, CardType,
)

if TYPE_CHECKING:
    from src.engine.types import GameObject
    from src.engine.yugioh_turn import YugiohTurnState


class YugiohAIAdapter:
    """
    Adapter that lets the AI play Yu-Gi-Oh!

    Called by YugiohTurnManager during AI turns. Provides:
    - get_main_phase_action(player_id, state, turn_state) -> action dict
    - get_battle_action(player_id, state, turn_state) -> action dict
    - should_enter_battle(player_id, state) -> bool
    """

    def __init__(self, difficulty: str = "medium"):
        self.difficulty = difficulty.lower()
        self.strategy: Optional[dict] = None  # AI strategy hints from deck
        # Track what we've done this main phase call to avoid loops
        self._actions_taken: int = 0
        self._max_actions: int = 20  # safety valve

    # === Main Phase Logic ===

    def get_main_phase_action(self, player_id: str, state: GameState,
                              turn_state: 'YugiohTurnState') -> dict:
        """Decide what to do during Main Phase 1 or 2."""
        self._actions_taken += 1
        if self._actions_taken > self._max_actions:
            self._actions_taken = 0
            return {'action_type': 'end_phase'}

        hand = self._get_hand(player_id, state)
        monsters = self._get_monsters(player_id, state)
        opp_id = self._get_opponent(player_id, state)
        opp_monsters = self._get_monsters(opp_id, state)

        # 1. Normal Summon the best monster from hand (if not used this turn)
        if not turn_state.normal_summon_used:
            summon = self._pick_normal_summon(hand, monsters, player_id, state)
            if summon:
                return summon

        # 2. Set a monster face-down if hand is weak and no normal summon used
        if not turn_state.normal_summon_used:
            set_action = self._pick_set_monster(hand, monsters, player_id, state)
            if set_action:
                return set_action

        # 3. Flip Summon face-down monsters
        flip = self._pick_flip_summon(monsters, player_id, state, turn_state)
        if flip:
            return flip

        # 4. Activate spells from hand
        spell = self._pick_spell_activation(hand, player_id, state, opp_id, opp_monsters, monsters)
        if spell:
            return spell

        # 5. Set traps from hand
        trap = self._pick_set_trap(hand, player_id, state)
        if trap:
            return trap

        # 6. Change position if beneficial
        pos_change = self._pick_position_change(monsters, player_id, state, turn_state, opp_monsters)
        if pos_change:
            return pos_change

        self._actions_taken = 0
        return {'action_type': 'end_phase'}

    def _pick_normal_summon(self, hand: list, monsters: list, player_id: str,
                            state: GameState) -> Optional[dict]:
        """Pick the best monster to Normal Summon."""
        summonable = []
        for obj in hand:
            if CardType.YGO_MONSTER not in obj.characteristics.types:
                continue
            level = getattr(obj.card_def, 'level', 1) or 1
            atk = getattr(obj.card_def, 'atk', 0) or 0

            # Can we tribute summon?
            if level >= 7:
                if len(monsters) >= 2:
                    summonable.append((obj, atk + 1000, level))  # Bonus for big monsters
            elif level >= 5:
                if len(monsters) >= 1:
                    summonable.append((obj, atk + 500, level))
            else:
                summonable.append((obj, atk, level))

        if not summonable:
            return None

        # Sort by strategy priority, then ATK value
        if self.difficulty in ("hard", "ultra") and self.strategy and self.strategy.get('summon_priority'):
            priority_list = self.strategy['summon_priority']
            def _summon_sort_key(entry):
                obj, score, _ = entry
                name = obj.name
                try:
                    idx = priority_list.index(name)
                    return (0, idx)  # In priority list: sort by position
                except ValueError:
                    return (1, -score)  # Not in list: sort by ATK score
            summonable.sort(key=_summon_sort_key)
        elif self.difficulty in ("hard", "ultra"):
            summonable.sort(key=lambda x: x[1], reverse=True)
        else:
            random.shuffle(summonable)

        best = summonable[0]
        obj, _, level = best

        # Check for empty slot
        zone = state.zones.get(f"monster_zone_{player_id}")
        has_slot = zone and any(
            i >= len(zone.objects) or zone.objects[i] is None
            for i in range(5)
        )
        if not has_slot and level < 5:
            return None  # No room and can't tribute

        return {
            'action_type': 'normal_summon',
            'card_id': obj.id,
        }

    def _pick_set_monster(self, hand: list, monsters: list, player_id: str,
                          state: GameState) -> Optional[dict]:
        """Set a weak monster face-down if we have nothing strong to summon."""
        if self.difficulty == "easy":
            return None  # Easy AI doesn't set strategically

        settable = []
        for obj in hand:
            if CardType.YGO_MONSTER not in obj.characteristics.types:
                continue
            level = getattr(obj.card_def, 'level', 1) or 1
            if level > 4:
                continue  # Only set level 4 or below
            atk = getattr(obj.card_def, 'atk', 0) or 0
            def_val = getattr(obj.card_def, 'def_val', 0) or 0
            flip_effect = getattr(obj.card_def, 'flip_effect', None)

            # Prefer setting monsters with flip effects or high DEF
            score = def_val
            if flip_effect:
                score += 2000  # Bonus for flip effect
            if atk < 1000:
                score += 500  # More reason to set weak monsters

            settable.append((obj, score))

        if not settable:
            return None

        # Check for empty slot
        zone = state.zones.get(f"monster_zone_{player_id}")
        has_slot = zone and any(
            i >= len(zone.objects) or zone.objects[i] is None
            for i in range(5)
        )
        if not has_slot:
            return None

        # Boost score for monsters in strategy's set_priority
        if self.strategy and self.strategy.get('set_priority'):
            set_prio = self.strategy['set_priority']
            for i, (obj, score) in enumerate(settable):
                if obj.name in set_prio:
                    settable[i] = (obj, score + 3000)  # Strongly prefer strategy targets

        settable.sort(key=lambda x: x[1], reverse=True)
        best = settable[0]

        # Only set if we have a reason (flip effect or defensive) — unless strategy says to
        if best[1] < 1000 and self.difficulty != "easy":
            return None

        return {
            'action_type': 'set_monster',
            'card_id': best[0].id,
        }

    def _pick_flip_summon(self, monsters: list, player_id: str, state: GameState,
                          turn_state: 'YugiohTurnState') -> Optional[dict]:
        """Flip summon a face-down monster if beneficial."""
        for obj in monsters:
            if not obj.state.face_down:
                continue
            if turn_state.position_changes.get(obj.id):
                continue
            # Don't flip summon on the turn it was set (needs at least 1 turn)
            turns_set = getattr(obj.state, 'turns_set', 0)
            if turns_set < 1:
                continue

            atk = getattr(obj.card_def, 'atk', 0) or 0
            flip_effect = getattr(obj.card_def, 'flip_effect', None)

            # Flip if monster has flip effect or decent ATK
            if flip_effect or atk >= 1500 or self.difficulty == "easy":
                return {
                    'action_type': 'flip_summon',
                    'card_id': obj.id,
                }
        return None

    def _pick_spell_activation(self, hand: list, player_id: str, state: GameState,
                               opp_id: str, opp_monsters: list,
                               my_monsters: list) -> Optional[dict]:
        """Activate a spell from hand if beneficial."""
        for obj in hand:
            if CardType.YGO_SPELL not in obj.characteristics.types:
                continue

            spell_type = getattr(obj.card_def, 'ygo_spell_type', 'Normal')
            name = obj.name

            # === Draw / advantage spells — always activate ===
            if name == "Pot of Greed":
                return {'action_type': 'activate_spell', 'card_id': obj.id}

            if name == "Graceful Charity":
                return {'action_type': 'activate_spell', 'card_id': obj.id}

            # === Board wipes ===
            if name == "Raigeki":
                if opp_monsters:
                    return {'action_type': 'activate_spell', 'card_id': obj.id}

            if name == "Heavy Storm":
                opp_st = self._get_spell_traps(opp_id, state)
                if len(opp_st) >= 2 or (len(opp_st) >= 1 and self.difficulty in ("easy", "medium")):
                    return {'action_type': 'activate_spell', 'card_id': obj.id}

            if name == "Dark Hole":
                if len(opp_monsters) > len(my_monsters) or (
                    len(opp_monsters) > 0 and len(my_monsters) == 0
                ):
                    return {'action_type': 'activate_spell', 'card_id': obj.id}
                if self.difficulty in ("easy", "medium") and opp_monsters:
                    return {'action_type': 'activate_spell', 'card_id': obj.id}

            # === Targeted removal / utility ===
            if name == "Monster Reborn":
                target = self._find_reborn_target(player_id, opp_id, state)
                if target:
                    return {'action_type': 'activate_spell', 'card_id': obj.id, 'targets': [target]}

            if name == "Premature Burial":
                target = self._find_reborn_target(player_id, player_id, state)
                if target:
                    return {'action_type': 'activate_spell', 'card_id': obj.id, 'targets': [target]}

            if name in ("Mystical Space Typhoon", "Stamping Destruction"):
                target = self._find_mst_target(opp_id, state)
                if target:
                    return {'action_type': 'activate_spell', 'card_id': obj.id, 'targets': [target]}

            if name == "Nobleman of Crossout":
                # Target opponent's face-down monsters
                for m in opp_monsters:
                    if m.state.face_down:
                        return {'action_type': 'activate_spell', 'card_id': obj.id, 'targets': [m.id]}

            if name == "Book of Moon":
                # Defensively flip down opponent's strongest attacker
                atk_monsters = [m for m in opp_monsters if not m.state.face_down
                                and m.state.ygo_position == 'face_up_atk']
                if atk_monsters:
                    atk_monsters.sort(key=lambda m: getattr(m.card_def, 'atk', 0) or 0, reverse=True)
                    return {'action_type': 'activate_spell', 'card_id': obj.id, 'targets': [atk_monsters[0].id]}

            # === Burn spells ===
            if name == "Ookazi":
                return {'action_type': 'activate_spell', 'card_id': obj.id}

            # === Stall / continuous ===
            if name == "Swords of Revealing Light":
                if opp_monsters:
                    return {'action_type': 'activate_spell', 'card_id': obj.id}

            if name in ("Messenger of Peace", "Level Limit - Area B"):
                if opp_monsters:
                    return {'action_type': 'activate_spell', 'card_id': obj.id}

            # === Field spells ===
            if name == "Mountain":
                if my_monsters:
                    return {'action_type': 'activate_spell', 'card_id': obj.id}

            # === Generic fallback ===
            if spell_type == "Normal" and self.difficulty in ("easy", "medium"):
                return {'action_type': 'activate_spell', 'card_id': obj.id}

        return None

    def _pick_set_trap(self, hand: list, player_id: str,
                       state: GameState) -> Optional[dict]:
        """Set a trap card from hand."""
        # Check for empty spell/trap slot
        zone = state.zones.get(f"spell_trap_zone_{player_id}")
        has_slot = zone and any(
            i >= len(zone.objects) or zone.objects[i] is None
            for i in range(5)
        )
        if not has_slot:
            return None

        for obj in hand:
            if CardType.YGO_TRAP not in obj.characteristics.types:
                continue
            return {
                'action_type': 'set_spell_trap',
                'card_id': obj.id,
            }
        return None

    def _pick_position_change(self, monsters: list, player_id: str,
                              state: GameState, turn_state: 'YugiohTurnState',
                              opp_monsters: list) -> Optional[dict]:
        """Change a monster's battle position if beneficial."""
        if self.difficulty == "easy":
            return None

        opp_max_atk = max(
            (getattr(m.card_def, 'atk', 0) or 0 for m in opp_monsters),
            default=0
        )

        for obj in monsters:
            if obj.state.face_down:
                continue
            if turn_state.position_changes.get(obj.id):
                continue

            atk = getattr(obj.card_def, 'atk', 0) or 0
            def_val = getattr(obj.card_def, 'def_val', 0) or 0
            pos = obj.state.ygo_position

            # Switch to DEF if our ATK is lower than opponent's strongest
            if pos == 'face_up_atk' and atk < opp_max_atk and def_val > atk:
                return {
                    'action_type': 'change_position',
                    'card_id': obj.id,
                }

            # Switch to ATK if we can overpower and we're in DEF
            if pos == 'face_up_def' and atk > opp_max_atk and atk >= 1500:
                return {
                    'action_type': 'change_position',
                    'card_id': obj.id,
                }

        return None

    # === Battle Phase Logic ===

    def should_enter_battle(self, player_id: str, state: GameState) -> bool:
        """Decide whether to enter the Battle Phase."""
        self._actions_taken = 0  # Reset for battle phase
        monsters = self._get_monsters(player_id, state)
        if not monsters:
            return False

        # Check if we have any monster that can attack
        for obj in monsters:
            if obj.state.face_down:
                continue
            if obj.state.ygo_position != 'face_up_atk':
                continue
            atk = getattr(obj.card_def, 'atk', 0) or 0
            if atk > 0:
                return True
        return False

    def get_battle_action(self, player_id: str, state: GameState,
                          turn_state: 'YugiohTurnState') -> dict:
        """Decide what to do during the Battle Phase."""
        monsters = self._get_monsters(player_id, state)
        opp_id = self._get_opponent(player_id, state)
        opp_monsters = self._get_monsters(opp_id, state)

        # Find attackers that haven't attacked yet
        for obj in monsters:
            if obj.state.face_down:
                continue
            if obj.state.ygo_position != 'face_up_atk':
                continue
            if turn_state.attacks_declared.get(obj.id, 0) > 0:
                continue

            atk = getattr(obj.card_def, 'atk', 0) or 0
            if atk <= 0:
                continue

            target = self._pick_attack_target(obj, opp_monsters, opp_id, state)
            if target == "__SKIP__":
                continue  # Can't safely attack with this monster
            return {
                'action_type': 'declare_attack',
                'attacker_id': obj.id,
                'target_id': target,
            }

        return {'action_type': 'end_phase'}

    def _pick_attack_target(self, attacker: 'GameObject', opp_monsters: list,
                            opp_id: str, state: GameState) -> Optional[str]:
        """Pick the best target for an attack."""
        atk = getattr(attacker.card_def, 'atk', 0) or 0

        if not opp_monsters:
            return None  # Direct attack

        # Filter to face-up ATK monsters we can beat
        beatable = []
        for m in opp_monsters:
            m_atk = getattr(m.card_def, 'atk', 0) or 0
            m_def = getattr(m.card_def, 'def_val', 0) or 0

            if m.state.ygo_position == 'face_up_atk':
                if atk > m_atk:
                    # We win and deal damage
                    beatable.append((m, m_atk - atk, m_atk))  # damage is positive
                elif self.difficulty == "easy" and atk >= m_atk:
                    beatable.append((m, 0, m_atk))
            elif m.state.ygo_position in ('face_up_def', 'face_down_def'):
                if m.state.face_down:
                    # Unknown DEF — risk it on easy, avoid on hard
                    if self.difficulty in ("easy", "medium"):
                        beatable.append((m, 0, 0))
                elif atk > m_def:
                    beatable.append((m, 0, m_def))

        if not beatable:
            # No safe target and opponent has monsters — can't direct attack
            if self.difficulty == "easy" and opp_monsters:
                return opp_monsters[0].id
            # Return sentinel to indicate "skip this attacker" (not None, which means direct)
            return "__SKIP__"

        if self.difficulty in ("hard", "ultra"):
            # Prioritize: kill ATK monsters that deal the most damage
            beatable.sort(key=lambda x: x[2], reverse=True)
        else:
            random.shuffle(beatable)

        return beatable[0][0].id

    # === Helper Methods ===

    def _get_hand(self, player_id: str, state: GameState) -> list:
        """Get player's hand as list of GameObjects."""
        hand_zone = state.zones.get(f"hand_{player_id}")
        if not hand_zone:
            return []
        return [
            state.objects[oid] for oid in hand_zone.objects
            if oid and oid in state.objects
        ]

    def _get_monsters(self, player_id: str, state: GameState) -> list:
        """Get player's monsters on field."""
        zone = state.zones.get(f"monster_zone_{player_id}")
        if not zone:
            return []
        return [
            state.objects[oid] for oid in zone.objects
            if oid and oid in state.objects
        ]

    def _get_spell_traps(self, player_id: str, state: GameState) -> list:
        """Get player's spell/trap cards on field."""
        zone = state.zones.get(f"spell_trap_zone_{player_id}")
        if not zone:
            return []
        return [
            state.objects[oid] for oid in zone.objects
            if oid and oid in state.objects
        ]

    def _get_opponent(self, player_id: str, state: GameState) -> str:
        """Get opponent's player ID."""
        for pid in state.players:
            if pid != player_id:
                return pid
        return ""

    def _find_reborn_target(self, player_id: str, opp_id: str,
                            state: GameState) -> Optional[str]:
        """Find the best monster to revive from either graveyard."""
        best = None
        best_atk = 0

        for pid in [player_id, opp_id]:
            gy = state.zones.get(f"graveyard_{pid}")
            if not gy:
                continue
            for oid in gy.objects:
                obj = state.objects.get(oid)
                if not obj:
                    continue
                if CardType.YGO_MONSTER not in obj.characteristics.types:
                    continue
                atk = getattr(obj.card_def, 'atk', 0) or 0
                if atk > best_atk:
                    best_atk = atk
                    best = oid

        return best

    def _find_mst_target(self, opp_id: str, state: GameState) -> Optional[str]:
        """Find an opponent's set spell/trap to destroy."""
        zone = state.zones.get(f"spell_trap_zone_{opp_id}")
        if not zone:
            return None
        for oid in zone.objects:
            if oid is None:
                continue
            obj = state.objects.get(oid)
            if obj:
                return oid
        return None
