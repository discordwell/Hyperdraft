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

        # 0. Take immediate lethal before spending summon/position resources.
        if self.difficulty in ("hard", "ultra"):
            lethal_spell = self._pick_lethal_spell_activation(hand, player_id, state, opp_id)
            if lethal_spell:
                return lethal_spell

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

        # 3.5 Activate face-up monster ignition / quick effects (once per turn).
        # Run this before spells so the AI uses monster-effect engines while
        # they're available — disruption monsters like Eight-and-a-Half-Tails
        # and Boseiju Mechanical Bridgekeeper depend on it.
        ignition = self._pick_monster_ignition(monsters, player_id, state, turn_state, opp_monsters)
        if ignition:
            return ignition

        # 4. Activate spells from hand
        spell = self._pick_spell_activation(hand, player_id, state, opp_id, opp_monsters, monsters)
        if spell:
            return spell

        # 5. Activate already-set proactive traps
        trap_activation = self._pick_trap_activation(
            self._get_spell_traps(player_id, state), player_id, state, opp_monsters
        )
        if trap_activation:
            return trap_activation

        # 6. Set traps from hand
        trap = self._pick_set_trap(hand, player_id, state)
        if trap:
            return trap

        # 7. Change position if beneficial
        pos_change = self._pick_position_change(monsters, player_id, state, turn_state, opp_monsters)
        if pos_change:
            return pos_change

        self._actions_taken = 0
        return {'action_type': 'end_phase'}

    def _pick_normal_summon(self, hand: list, monsters: list, player_id: str,
                            state: GameState) -> Optional[dict]:
        """Pick the best monster to Normal Summon."""
        summonable = []
        set_priority = set((self.strategy or {}).get('set_priority', []))
        summon_priority = set((self.strategy or {}).get('summon_priority', []))
        for obj in hand:
            if CardType.YGO_MONSTER not in obj.characteristics.types:
                continue
            if (self.difficulty in ("hard", "ultra")
                    and obj.name in set_priority
                    and obj.name not in summon_priority):
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
        tributes_needed = 0
        if level >= 5:
            tributes_needed = 1
        if level >= 7:
            tributes_needed = 2

        # Check for empty slot
        zone = state.zones.get(f"monster_zone_{player_id}")
        has_slot = zone and any(
            i >= len(zone.objects) or zone.objects[i] is None
            for i in range(5)
        )
        if not has_slot and level < 5:
            return None  # No room and can't tribute

        action = {
            'action_type': 'normal_summon',
            'card_id': obj.id,
        }
        if tributes_needed:
            tribute_ids = self._pick_tribute_ids(monsters, tributes_needed)
            if len(tribute_ids) < tributes_needed:
                return None
            action['tribute_ids'] = tribute_ids
        return action

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

    # Spells the AI knows how to evaluate — skip the generic fallback for these
    _KNOWN_SPELLS = frozenset({
        "Pot of Greed", "Graceful Charity", "Raigeki", "Heavy Storm", "Dark Hole",
        "Monster Reborn", "Premature Burial", "Mystical Space Typhoon",
        "Stamping Destruction", "Nobleman of Crossout", "Book of Moon", "Ookazi",
        "Swords of Revealing Light", "Messenger of Peace", "Level Limit - Area B",
        "Mountain", "Lightning Bolt", "Ponder", "Preordain", "Demonic Tutor",
        "Fact or Fiction", "Wheel of Fortune", "Wrath of God", "Day of Judgment",
        "Path to Exile", "Swords to Plowshares", "Doom Blade",
    })

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

            if name in ("Ponder", "Preordain", "Demonic Tutor", "Fact or Fiction"):
                return {'action_type': 'activate_spell', 'card_id': obj.id}

            if name == "Wheel of Fortune":
                own_hand = len(self._get_hand(player_id, state))
                opp_hand = len(self._get_hand(opp_id, state))
                if own_hand <= 2 or opp_hand <= own_hand:
                    return {'action_type': 'activate_spell', 'card_id': obj.id}
                continue

            # === Board wipes ===
            if name == "Raigeki":
                if opp_monsters:
                    return {'action_type': 'activate_spell', 'card_id': obj.id}
                continue

            if name == "Heavy Storm":
                opp_st = self._get_spell_traps(opp_id, state)
                own_st = self._get_spell_traps(player_id, state)
                if self.difficulty in ("hard", "ultra"):
                    if len(opp_st) >= 2 and len(opp_st) > len(own_st):
                        return {'action_type': 'activate_spell', 'card_id': obj.id}
                elif len(opp_st) >= 1:
                    return {'action_type': 'activate_spell', 'card_id': obj.id}
                continue

            if name == "Dark Hole":
                if len(opp_monsters) > len(my_monsters) or (
                    len(opp_monsters) > 0 and len(my_monsters) == 0
                ):
                    return {'action_type': 'activate_spell', 'card_id': obj.id}
                if self.difficulty in ("easy", "medium") and opp_monsters:
                    return {'action_type': 'activate_spell', 'card_id': obj.id}
                continue

            if name in ("Wrath of God", "Day of Judgment"):
                if len(opp_monsters) > len(my_monsters) or (
                    len(opp_monsters) >= 2 and len(my_monsters) <= 1
                ):
                    return {'action_type': 'activate_spell', 'card_id': obj.id}
                continue

            # === Targeted removal / utility ===
            if name == "Monster Reborn":
                if not self._has_empty_monster_slot(player_id, state):
                    continue
                target = self._find_reborn_target(player_id, opp_id, state)
                if target:
                    return {'action_type': 'activate_spell', 'card_id': obj.id, 'targets': [target]}
                continue

            if name == "Premature Burial":
                player = state.players.get(player_id)
                if player and getattr(player, 'lp', 0) <= 800:
                    continue
                if not self._has_empty_monster_slot(player_id, state):
                    continue
                target = self._find_own_gy_target(player_id, state)
                if target:
                    return {'action_type': 'activate_spell', 'card_id': obj.id, 'targets': [target]}
                continue

            if name in ("Mystical Space Typhoon", "Stamping Destruction"):
                target = self._find_mst_target(opp_id, state)
                if target:
                    return {'action_type': 'activate_spell', 'card_id': obj.id, 'targets': [target]}
                continue

            if name == "Nobleman of Crossout":
                for m in opp_monsters:
                    if m.state.face_down:
                        return {'action_type': 'activate_spell', 'card_id': obj.id, 'targets': [m.id]}
                continue

            if name == "Book of Moon":
                atk_monsters = [m for m in opp_monsters if not m.state.face_down
                                and m.state.ygo_position == 'face_up_atk']
                if atk_monsters:
                    atk_monsters.sort(key=lambda m: getattr(m.card_def, 'atk', 0) or 0, reverse=True)
                    return {'action_type': 'activate_spell', 'card_id': obj.id, 'targets': [atk_monsters[0].id]}
                continue

            if name in ("Path to Exile", "Swords to Plowshares", "Doom Blade"):
                target = self._find_best_visible_monster(opp_monsters)
                if target:
                    return {'action_type': 'activate_spell', 'card_id': obj.id, 'targets': [target.id]}
                continue

            # === Burn spells ===
            if name == "Ookazi":
                return {'action_type': 'activate_spell', 'card_id': obj.id}

            if name == "Lightning Bolt":
                opponent = state.players.get(opp_id)
                if opponent and getattr(opponent, 'lp', 0) <= 1500:
                    return {'action_type': 'activate_spell', 'card_id': obj.id}
                small_target = self._find_best_visible_monster(
                    [m for m in opp_monsters if (getattr(m.card_def, 'atk', 0) or 0) <= 1500]
                )
                if small_target:
                    return {
                        'action_type': 'activate_spell',
                        'card_id': obj.id,
                        'targets': [small_target.id],
                    }
                role = ((self.strategy or {}).get('archetype') or '').lower()
                if opponent and ("burn" in role or "aggro" in role or not opp_monsters):
                    return {'action_type': 'activate_spell', 'card_id': obj.id}
                continue

            # === Stall / continuous ===
            if name == "Swords of Revealing Light":
                if opp_monsters:
                    return {'action_type': 'activate_spell', 'card_id': obj.id}
                continue

            if name in ("Messenger of Peace", "Level Limit - Area B"):
                if opp_monsters:
                    if self.difficulty in ("hard", "ultra"):
                        role = ((self.strategy or {}).get('archetype') or '').lower()
                        if "burn" in role or "stall" in role:
                            return {'action_type': 'activate_spell', 'card_id': obj.id}
                        my_big = sum(
                            1 for m in my_monsters
                            if not m.state.face_down and (getattr(m.card_def, 'atk', 0) or 0) >= 1500
                        )
                        opp_big = sum(
                            1 for m in opp_monsters
                            if not m.state.face_down and (getattr(m.card_def, 'atk', 0) or 0) >= 1500
                        )
                        if opp_big > my_big:
                            return {'action_type': 'activate_spell', 'card_id': obj.id}
                    else:
                        return {'action_type': 'activate_spell', 'card_id': obj.id}
                continue

            # === Field spells ===
            if name == "Mountain":
                if my_monsters:
                    return {'action_type': 'activate_spell', 'card_id': obj.id}
                continue

            if spell_type == "Equip":
                target = self._find_best_visible_monster(my_monsters)
                if target:
                    return {'action_type': 'activate_spell', 'card_id': obj.id, 'targets': [target.id]}
                continue

            # === Generic fallback for unknown spells ===
            if name not in self._KNOWN_SPELLS:
                generic = self._pick_generic_spell_activation(
                    obj, player_id, state, opp_monsters, my_monsters
                )
                if generic:
                    return generic

        return None

    def _pick_lethal_spell_activation(self, hand: list, player_id: str,
                                      state: GameState, opp_id: str) -> Optional[dict]:
        """Pick a known direct-damage spell if it wins immediately."""
        opponent = state.players.get(opp_id)
        if not opponent:
            return None
        opp_lp = getattr(opponent, 'lp', 0)
        for obj in hand:
            if CardType.YGO_SPELL not in obj.characteristics.types:
                continue
            if obj.name == "Ookazi" and opp_lp <= 800:
                return {'action_type': 'activate_spell', 'card_id': obj.id}
            if obj.name == "Lightning Bolt" and opp_lp <= 1500:
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

    def _pick_trap_activation(self, spell_traps: list, player_id: str,
                              state: GameState, opp_monsters: list) -> Optional[dict]:
        """Activate proactive set traps with effects the local engine models."""
        for obj in spell_traps:
            if CardType.YGO_TRAP not in obj.characteristics.types:
                continue
            if obj.state.face_down and getattr(obj.state, 'turns_set', 0) < 1:
                continue
            card_def = obj.card_def
            if not card_def or not card_def.resolve:
                continue

            blob = f"{obj.name} {card_def.text or ''}".lower()
            if "negate" in blob and not any(
                term in blob for term in ("destroy", "return", "draw", "damage", "inflict")
            ):
                continue

            target = self._find_best_visible_monster(opp_monsters)
            if any(term in blob for term in ("destroy", "banish", "return", "bounce")):
                if not opp_monsters:
                    continue
                action = {'action_type': 'activate_trap', 'card_id': obj.id}
                if target:
                    action['targets'] = [target.id]
                return action

            if any(term in blob for term in ("draw", "damage", "inflict")):
                return {'action_type': 'activate_trap', 'card_id': obj.id}

        return None

    def _pick_position_change(self, monsters: list, player_id: str,
                              state: GameState, turn_state: 'YugiohTurnState',
                              opp_monsters: list) -> Optional[dict]:
        """Change a monster's battle position if beneficial."""
        if self.difficulty == "easy":
            return None

        opp_max_atk = max(
            (getattr(m.card_def, 'atk', 0) or 0
             for m in opp_monsters
             if not m.state.face_down and m.state.ygo_position == 'face_up_atk'),
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

            # Switch to DEF only if: ATK can't survive AND DEF actually blocks their attack
            if (pos == 'face_up_atk' and atk < opp_max_atk
                    and def_val >= opp_max_atk and def_val > atk):
                return {
                    'action_type': 'change_position',
                    'card_id': obj.id,
                }

            # Switch to ATK if we can overpower or opponent has nothing threatening
            if pos == 'face_up_def' and atk >= 1200:
                # Switch if we outclass opponent's ATK, or if no ATK monsters threaten us
                if atk > opp_max_atk or opp_max_atk == 0:
                    return {
                        'action_type': 'change_position',
                        'card_id': obj.id,
                    }

        return None

    # === Monster Ignition / Quick Effects ===

    # Text markers identifying once-per-turn player-activated effects.
    _IGNITION_TEXT_MARKERS = (
        "once per turn",
        "(ignition)",
        "ignition:",
        "ignition effect",
        "quick effect",
        "(quick)",
    )

    def _has_ignition_effect(self, obj: 'GameObject') -> bool:
        """Heuristic check — does this monster expose a once-per-turn surface?"""
        if not obj or not obj.card_def:
            return False
        text = (getattr(obj.card_def, 'text', '') or '').lower()
        return any(marker in text for marker in self._IGNITION_TEXT_MARKERS)

    def _score_ignition_effect(self, obj: 'GameObject',
                               opp_monsters: list, my_monsters: list,
                               player_id: str, state: GameState) -> int:
        """Score the value of activating a monster's ignition effect.

        Bonuses:
        - +200 per opponent monster the effect can plausibly hit (removal)
        - +150 per "draw"/"search"/"add to hand" marker (card advantage)
        - +100 per "damage"/"inflict" marker (burn)
        - +80 per own-monster pump marker (combat support)
        - small flat bonus so any ignition fires over passing the phase
        """
        if not obj.card_def:
            return -1
        text = (getattr(obj.card_def, 'text', '') or '').lower()
        score = 30  # Baseline — firing any once-per-turn engine beats passing.

        removal_terms = ("destroy", "banish", "send 1", "to gy", "return ",
                         "bounce", "shuffle")
        if any(term in text for term in removal_terms):
            # Each opposing target multiplies the value.
            visible_opp = [m for m in opp_monsters
                           if not getattr(m.state, "face_down", False)]
            score += 200 * (1 + len(visible_opp))

        if any(term in text for term in ("draw", "search", "add 1", "add to hand")):
            score += 150

        if any(term in text for term in ("damage", "inflict", "burn")):
            score += 100

        if any(term in text for term in ("gain ", "atk", "pump")):
            score += 80 * max(1, len(my_monsters))

        if "discard" in text and "opponent" in text:
            score += 250  # Hand disruption is high-leverage in YGO.

        # Defensive ignitions (e.g. "this card cannot be destroyed")
        # are still worth playing on tempo.
        if "cannot" in text or "negate" in text:
            score += 60

        return score

    def _pick_monster_ignition(self, monsters: list, player_id: str,
                               state: GameState,
                               turn_state: 'YugiohTurnState',
                               opp_monsters: list) -> Optional[dict]:
        """Pick the highest-scoring face-up monster ignition effect to fire.

        Skips monsters that already fired this turn (gated by
        ``obj.state.ignition_used_turn``). Returns an action dict the
        YGO turn manager can dispatch through ``_execute_action``.
        """
        cur_turn = getattr(turn_state, 'turn_number', 0)
        my_monsters = monsters
        candidates: list[tuple[int, 'GameObject']] = []
        for obj in monsters:
            if getattr(obj.state, 'face_down', False):
                continue
            pos = getattr(obj.state, 'ygo_position', None)
            if pos not in ('face_up_atk', 'face_up_def'):
                continue
            if getattr(obj.state, 'ignition_used_turn', None) == cur_turn:
                continue
            if not self._has_ignition_effect(obj):
                continue
            score = self._score_ignition_effect(
                obj, opp_monsters, my_monsters, player_id, state
            )
            if score <= 0:
                continue
            candidates.append((score, obj))

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        _, chosen = candidates[0]
        return {
            'action_type': 'activate_monster_effect',
            'card_id': chosen.id,
            'monster_id': chosen.id,
            'effect_index': 0,
        }

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
                if self.difficulty == "easy":
                    return True
                opp_id = self._get_opponent(player_id, state)
                target = self._pick_attack_target(
                    obj, self._get_monsters(opp_id, state), opp_id, state
                )
                if target != "__SKIP__":
                    return True
        return False

    def get_battle_action(self, player_id: str, state: GameState,
                          turn_state: 'YugiohTurnState') -> dict:
        """Decide what to do during the Battle Phase."""
        monsters = self._get_monsters(player_id, state)
        opp_id = self._get_opponent(player_id, state)
        opp_monsters = self._get_monsters(opp_id, state)

        # Find attackers that haven't attacked yet
        attackers = []
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
            attackers.append(obj)

        if self.difficulty in ("hard", "ultra"):
            best_attack = self._pick_best_battle_attack(attackers, opp_monsters, opp_id, state)
            if best_attack:
                attacker, target = best_attack
                return {
                    'action_type': 'declare_attack',
                    'attacker_id': attacker.id,
                    'target_id': target,
                }

        for obj in attackers:
            target = self._pick_attack_target(obj, opp_monsters, opp_id, state)
            if target == "__SKIP__":
                continue  # Can't safely attack with this monster
            return {
                'action_type': 'declare_attack',
                'attacker_id': obj.id,
                'target_id': target,
            }

        return {'action_type': 'end_phase'}

    def _pick_best_battle_attack(self, attackers: list, opp_monsters: list,
                                 opp_id: str, state: GameState) -> Optional[tuple]:
        """Pick the best next attack with shallow lookahead over remaining attackers."""
        if not attackers:
            return None
        if not opp_monsters:
            best_direct = max(
                attackers,
                key=lambda obj: getattr(obj.card_def, 'atk', 0) or 0,
            )
            return (best_direct, None)

        best = None
        best_score = -1
        for attacker in attackers:
            for option in self._attack_options(attacker, opp_monsters):
                score = self._score_attack_option(
                    attacker, option, attackers, opp_monsters, opp_id, state
                )
                if score > best_score:
                    best_score = score
                    best = (attacker, option["target"].id)
        return best

    def _score_attack_option(self, attacker: 'GameObject', option: dict,
                             attackers: list, opp_monsters: list,
                             opp_id: str, state: GameState) -> int:
        """Score an attack plus the best immediate follow-up by another attacker."""
        target = option["target"]
        damage = option["damage"]
        target_value = option["target_value"]
        opponent = state.players.get(opp_id)
        if opponent and damage >= getattr(opponent, 'lp', 0):
            return 1_000_000 + damage

        remaining_targets = [m for m in opp_monsters if m.id != target.id]
        followup = 0
        for other in attackers:
            if other.id == attacker.id:
                continue
            options = self._attack_options(other, remaining_targets)
            if not options:
                continue
            followup = max(
                followup,
                max(opt["damage"] + opt["target_value"] for opt in options),
            )
        return damage + target_value + followup

    def _attack_options(self, attacker: 'GameObject', opp_monsters: list) -> list[dict]:
        """Return safe attack options against visible/acceptable targets."""
        atk = getattr(attacker.card_def, 'atk', 0) or 0
        options = []
        for m in opp_monsters:
            m_atk = getattr(m.card_def, 'atk', 0) or 0
            m_def = getattr(m.card_def, 'def_val', 0) or 0

            if m.state.ygo_position == 'face_up_atk':
                if atk > m_atk:
                    options.append({"target": m, "damage": atk - m_atk, "target_value": m_atk})
                elif atk == m_atk and self.difficulty in ("easy", "medium"):
                    options.append({"target": m, "damage": 0, "target_value": m_atk})
            elif m.state.ygo_position in ('face_up_def', 'face_down_def'):
                if m.state.face_down:
                    if self.difficulty in ("easy", "medium") or atk >= 1500:
                        options.append({"target": m, "damage": 0, "target_value": 0})
                elif atk > m_def:
                    options.append({"target": m, "damage": 0, "target_value": m_def})
        return options

    def _pick_attack_target(self, attacker: 'GameObject', opp_monsters: list,
                            opp_id: str, state: GameState) -> Optional[str]:
        """Pick the best target for an attack."""
        atk = getattr(attacker.card_def, 'atk', 0) or 0

        if not opp_monsters:
            return None  # Direct attack

        # Filter to monsters we can beat
        beatable = self._attack_options(attacker, opp_monsters)

        if not beatable:
            # No safe target — medium+ skip, easy attacks anyway
            if self.difficulty == "easy" and opp_monsters:
                return opp_monsters[0].id
            # Return sentinel to indicate "skip this attacker"
            return "__SKIP__"

        if self.difficulty in ("hard", "ultra"):
            # Prioritize: ATK monsters that deal LP damage first, then clear DEF
            beatable.sort(key=lambda x: (x["damage"], x["target_value"]), reverse=True)
        else:
            random.shuffle(beatable)

        return beatable[0]["target"].id

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

    def _has_empty_monster_slot(self, player_id: str, state: GameState) -> bool:
        """Return True if the player has an open monster zone slot."""
        zone = state.zones.get(f"monster_zone_{player_id}")
        return bool(zone and any(
            i >= len(zone.objects) or zone.objects[i] is None
            for i in range(5)
        ))

    def _get_opponent(self, player_id: str, state: GameState) -> str:
        """Get opponent's player ID."""
        for pid in state.players:
            if pid != player_id:
                return pid
        return ""

    def _find_own_gy_target(self, player_id: str, state: GameState) -> Optional[str]:
        """Find the best monster in own graveyard to revive."""
        best = None
        best_atk = 0
        gy = state.zones.get(f"graveyard_{player_id}")
        if not gy:
            return None
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

    def _find_best_visible_monster(self, monsters: list) -> Optional['GameObject']:
        """Return the highest-ATK visible monster from a list."""
        visible = [m for m in monsters if m and not m.state.face_down]
        if not visible:
            return None
        visible.sort(key=lambda m: getattr(m.card_def, 'atk', 0) or 0, reverse=True)
        return visible[0]

    def _pick_generic_spell_activation(self, obj: 'GameObject', player_id: str,
                                       state: GameState, opp_monsters: list,
                                       my_monsters: list) -> Optional[dict]:
        """Use text heuristics for custom-set YGO spells not in the named table."""
        card_def = obj.card_def
        if not card_def:
            return None
        spell_type = getattr(card_def, 'ygo_spell_type', 'Normal')
        blob = f"{obj.name} {card_def.text or ''}".lower()

        if "you control" in blob and not my_monsters:
            return None

        if spell_type == "Equip":
            target = self._find_best_visible_monster(my_monsters)
            if target:
                return {'action_type': 'activate_spell', 'card_id': obj.id, 'targets': [target.id]}
            return None

        if spell_type in ("Continuous", "Field"):
            setup_terms = (
                "draw", "add 1", "search", "gain", "cannot attack",
                "piercing", "special summon",
            )
            if any(term in blob for term in setup_terms):
                return {'action_type': 'activate_spell', 'card_id': obj.id}
            return None

        if spell_type not in ("Normal", "Quick-Play"):
            return None

        removal_terms = (
            "destroy", "banish", "return 1 monster", "return the first",
            "return 1 face-up", "bounce", "to its owner's hand",
        )
        if any(term in blob for term in removal_terms) and opp_monsters:
            target = self._find_best_visible_monster(opp_monsters)
            if target:
                return {'action_type': 'activate_spell', 'card_id': obj.id, 'targets': [target.id]}
            return {'action_type': 'activate_spell', 'card_id': obj.id}

        value_terms = ("draw", "add 1", "search", "from your deck", "reveal top")
        if any(term in blob for term in value_terms):
            return {'action_type': 'activate_spell', 'card_id': obj.id}

        if "special summon" in blob and self._has_empty_monster_slot(player_id, state):
            return {'action_type': 'activate_spell', 'card_id': obj.id}

        burn_terms = ("inflict", "damage to your opponent", "deal")
        if any(term in blob for term in burn_terms):
            return {'action_type': 'activate_spell', 'card_id': obj.id}

        if spell_type == "Normal" and self.difficulty in ("easy", "medium"):
            return {'action_type': 'activate_spell', 'card_id': obj.id}
        return None

    def _pick_tribute_ids(self, monsters: list, count: int) -> list[str]:
        """Pick low-value monsters to tribute for a high-level summon."""
        candidates = []
        for monster in monsters:
            if not monster or not monster.card_def:
                continue
            atk = getattr(monster.card_def, 'atk', 0) or 0
            defense = getattr(monster.card_def, 'def_val', 0) or 0
            candidates.append((max(atk, defense), monster.id))
        candidates.sort(key=lambda item: item[0])
        return [mid for _score, mid in candidates[:count]]

    def _find_mst_target(self, opp_id: str, state: GameState) -> Optional[str]:
        """Find an opponent's set spell/trap to destroy."""
        zone = state.zones.get(f"spell_trap_zone_{opp_id}")
        if zone:
            for oid in zone.objects:
                if oid is None:
                    continue
                obj = state.objects.get(oid)
                if obj:
                    return oid
        field_zone = state.zones.get(f"field_spell_zone_{opp_id}")
        if field_zone:
            for oid in field_zone.objects:
                if oid is None:
                    continue
                obj = state.objects.get(oid)
                if obj:
                    return oid
        return None
