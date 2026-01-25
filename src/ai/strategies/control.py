"""
Hyperdraft Control Strategy

A defensive AI strategy that prioritizes:
- Card advantage
- Answering threats with removal
- Holding up mana for responses
- Playing threats only when safe
"""

from typing import TYPE_CHECKING

from .base import AIStrategy

if TYPE_CHECKING:
    from src.engine import GameState, LegalAction
    from src.engine import AttackDeclaration, BlockDeclaration
    from src.ai.evaluator import BoardEvaluator


class ControlStrategy(AIStrategy):
    """
    Control strategy that prioritizes defense and card advantage.

    Key principles:
    - Remove threats before playing our own
    - Hold up mana for instant-speed answers
    - Draw cards whenever possible
    - Only attack when safe to do so
    """

    @property
    def name(self) -> str:
        return "Control"

    @property
    def reactivity(self) -> float:
        """Control is highly reactive - holds mana and counters threats."""
        return 0.9

    def evaluate_action(
        self,
        action: 'LegalAction',
        state: 'GameState',
        evaluator: 'BoardEvaluator',
        player_id: str
    ) -> float:
        """
        Score actions with control priorities.

        Prefers:
        1. Removal spells (answering threats)
        2. Card draw
        3. Holding mana (passing)
        4. Playing threats when board is clear
        """
        from src.engine import ActionType, CardType

        score = 0.0

        if action.type == ActionType.PASS:
            # Control often wants to pass and hold up mana
            # But only if we have instant-speed options
            if self._has_instant_in_hand(state, player_id):
                return 0.5
            return 0.1

        if action.type == ActionType.PLAY_LAND:
            return 0.9  # Lands are important for control

        if action.type == ActionType.CAST_SPELL:
            card = state.objects.get(action.card_id)
            if not card:
                return 0.0

            # Removal is top priority for control
            if self._is_removal(card):
                # Higher priority if there are threats on board
                if self._count_opponent_creatures(state, player_id) > 0:
                    score = 1.8
                else:
                    score = 0.5  # Save removal for later

            # Card draw is very valuable
            elif self._is_card_draw(card):
                score = 1.5

            # Counter spells
            elif self._is_counterspell(card):
                # Only valuable if something to counter
                score = 0.3  # Hold for later

            # Creatures - lower priority
            elif CardType.CREATURE in card.characteristics.types:
                power = card.characteristics.power or 0
                toughness = card.characteristics.toughness or 0

                # Only play creatures when board is safe
                opp_creatures = self._count_opponent_creatures(state, player_id)
                my_removal = self._count_removal_in_hand(state, player_id)

                if opp_creatures == 0:
                    # Safe to play threats
                    score = 1.0 + (power + toughness) * 0.1
                elif my_removal > 0:
                    # We have answers, can play threats
                    score = 0.7
                else:
                    # Risky to tap out
                    score = 0.3

                # Defensive creatures are more valuable for control
                if toughness > power:
                    score += 0.2
                if self._has_ability(card, 'flying', state):
                    score += 0.1  # Good blocker
                if self._has_ability(card, 'vigilance', state):
                    score += 0.2  # Can attack and block

            # Board wipes - very valuable
            elif self._is_board_wipe(card):
                opp_creatures = self._count_opponent_creatures(state, player_id)
                my_creatures = self._count_my_creatures(state, player_id)

                # Only wipe if opponent has more
                if opp_creatures > my_creatures and opp_creatures >= 2:
                    score = 2.0
                else:
                    score = 0.2  # Hold for better moment

            # Enchantments
            elif CardType.ENCHANTMENT in card.characteristics.types:
                score = 0.6

        return score

    def plan_attacks(
        self,
        state: 'GameState',
        player_id: str,
        evaluator: 'BoardEvaluator',
        legal_attackers: list[str]
    ) -> list['AttackDeclaration']:
        """
        Control attacks conservatively - only when safe.

        Attack when:
        - We have blockers to spare
        - Opponent can't crack back for lethal
        - We have answers in hand
        """
        from src.engine import AttackDeclaration, get_power, get_toughness, is_creature

        if not legal_attackers:
            return []

        opponent_id = self._get_opponent_id(player_id, state)
        if not opponent_id:
            return []

        opponent = state.players.get(opponent_id)
        player = state.players.get(player_id)

        # Count opponent's potential attackers
        opp_potential_damage = 0
        opp_blockers = []
        battlefield = state.zones.get('battlefield')

        if battlefield:
            for obj_id in battlefield.objects:
                obj = state.objects.get(obj_id)
                if not obj or not is_creature(obj, state):
                    continue

                if obj.controller == opponent_id:
                    power = get_power(obj, state)
                    if not obj.state.tapped:
                        opp_potential_damage += power
                        opp_blockers.append(obj_id)

        # Don't attack if opponent can crack back for lethal
        if player and opp_potential_damage >= player.life:
            # Keep all creatures back for blocking
            return []

        # Select safe attackers (those we don't need for blocking)
        attacks = []
        my_blockers_needed = self._blockers_needed(state, player_id, opponent_id)
        blockers_held = 0

        # Sort attackers by power (attack with biggest first)
        attacker_powers = []
        for attacker_id in legal_attackers:
            attacker = state.objects.get(attacker_id)
            if attacker:
                power = get_power(attacker, state)
                attacker_powers.append((attacker_id, power))

        attacker_powers.sort(key=lambda x: x[1], reverse=True)

        for attacker_id, power in attacker_powers:
            attacker = state.objects.get(attacker_id)
            if not attacker:
                continue

            toughness = get_toughness(attacker, state)

            # Hold back enough blockers
            if blockers_held < my_blockers_needed:
                blockers_held += 1
                continue

            # Vigilance creatures can attack and block
            if self._has_ability(attacker, 'vigilance', state):
                attacks.append(AttackDeclaration(
                    attacker_id=attacker_id,
                    defending_player_id=opponent_id,
                    is_attacking_planeswalker=False
                ))
                continue

            # Only attack if it wouldn't die to a single blocker
            # or if no blockers exist
            if not opp_blockers:
                attacks.append(AttackDeclaration(
                    attacker_id=attacker_id,
                    defending_player_id=opponent_id,
                    is_attacking_planeswalker=False
                ))
            else:
                # Check if any blocker can kill our attacker without dying
                safe_to_attack = True
                for blocker_id in opp_blockers:
                    blocker = state.objects.get(blocker_id)
                    if blocker:
                        blocker_power = get_power(blocker, state)
                        blocker_toughness = get_toughness(blocker, state)

                        would_kill_attacker = blocker_power >= toughness
                        would_kill_blocker = power >= blocker_toughness

                        if would_kill_attacker and not would_kill_blocker:
                            safe_to_attack = False
                            break

                if safe_to_attack:
                    attacks.append(AttackDeclaration(
                        attacker_id=attacker_id,
                        defending_player_id=opponent_id,
                        is_attacking_planeswalker=False
                    ))

        return attacks

    def plan_blocks(
        self,
        state: 'GameState',
        player_id: str,
        evaluator: 'BoardEvaluator',
        attackers: list['AttackDeclaration'],
        legal_blockers: list[str]
    ) -> list['BlockDeclaration']:
        """
        Control blocks aggressively - trade whenever possible.

        Blocking philosophy:
        - Always block if we can kill the attacker
        - Trade 1-for-1 gladly
        - Chump block large threats to preserve life
        """
        from src.engine import BlockDeclaration, get_power, get_toughness

        if not attackers or not legal_blockers:
            return []

        player = state.players.get(player_id)
        if not player:
            return []

        blocks = []
        used_blockers = set()

        # Sort attackers by power (block biggest first)
        sorted_attackers = []
        for attack in attackers:
            attacker = state.objects.get(attack.attacker_id)
            if attacker:
                power = get_power(attacker, state)
                sorted_attackers.append((attack, power))

        sorted_attackers.sort(key=lambda x: x[1], reverse=True)

        for attack, attacker_power in sorted_attackers:
            attacker = state.objects.get(attack.attacker_id)
            if not attacker:
                continue

            attacker_toughness = get_toughness(attacker, state)

            best_blocker = None
            best_value = -999

            for blocker_id in legal_blockers:
                if blocker_id in used_blockers:
                    continue

                blocker = state.objects.get(blocker_id)
                if not blocker:
                    continue

                blocker_power = get_power(blocker, state)
                blocker_toughness = get_toughness(blocker, state)

                kills_attacker = blocker_power >= attacker_toughness
                dies = attacker_power >= blocker_toughness

                value = 0

                # Perfect block: kill attacker, survive
                if kills_attacker and not dies:
                    value = 200

                # Good trade: both die
                elif kills_attacker and dies:
                    value = 100

                # Chump block: we die, they live
                elif not kills_attacker:
                    # Control is willing to chump to preserve life
                    if attacker_power >= 3:  # Worth chumping big attackers
                        value = 30 + attacker_power
                    elif attacker_power >= player.life:  # Must chump
                        value = 50

                # First strike consideration
                if self._has_ability(attacker, 'first_strike', state):
                    if dies and not self._has_ability(blocker, 'first_strike', state):
                        value -= 30  # We die before dealing damage

                if value > best_value:
                    best_value = value
                    best_blocker = blocker_id

            if best_blocker and best_value > 0:
                blocks.append(BlockDeclaration(
                    blocker_id=best_blocker,
                    blocking_attacker_id=attack.attacker_id
                ))
                used_blockers.add(best_blocker)

        return blocks

    def mulligan_threshold(self, mulligan_count: int) -> float:
        """
        Control is pickier about hands - needs interaction.
        """
        thresholds = {
            0: 0.65,  # Need a good hand on 7
            1: 0.55,  # Still want quality on 6
            2: 0.35,  # Okay with mediocre on 5
            3: 0.1,   # Keep almost anything on 4
        }
        return thresholds.get(mulligan_count, 0.0)

    def should_counter(
        self,
        spell_on_stack,
        state: 'GameState',
        evaluator: 'BoardEvaluator',
        player_id: str
    ) -> bool:
        """
        Control counters important spells.
        """
        # Counter creatures with 3+ power
        # Counter planeswalkers
        # Counter board wipes when ahead
        return True  # Default to counter (can refine later)

    # Helper methods

    def _has_instant_in_hand(self, state: 'GameState', player_id: str) -> bool:
        """Check if player has instant-speed spells in hand."""
        from src.engine import CardType

        hand_key = f"hand_{player_id}"
        hand = state.zones.get(hand_key)
        if not hand:
            return False

        for card_id in hand.objects:
            card = state.objects.get(card_id)
            if card and CardType.INSTANT in card.characteristics.types:
                return True
        return False

    def _count_opponent_creatures(self, state: 'GameState', player_id: str) -> int:
        """Count opponent's creatures on battlefield."""
        from src.engine import is_creature

        opponent_id = self._get_opponent_id(player_id, state)
        count = 0

        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = state.objects.get(obj_id)
                if obj and is_creature(obj, state) and obj.controller == opponent_id:
                    count += 1
        return count

    def _count_my_creatures(self, state: 'GameState', player_id: str) -> int:
        """Count our creatures on battlefield."""
        from src.engine import is_creature

        count = 0
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = state.objects.get(obj_id)
                if obj and is_creature(obj, state) and obj.controller == player_id:
                    count += 1
        return count

    def _count_removal_in_hand(self, state: 'GameState', player_id: str) -> int:
        """Count removal spells in hand."""
        count = 0
        hand_key = f"hand_{player_id}"
        hand = state.zones.get(hand_key)
        if hand:
            for card_id in hand.objects:
                card = state.objects.get(card_id)
                if card and self._is_removal(card):
                    count += 1
        return count

    def _blockers_needed(
        self,
        state: 'GameState',
        player_id: str,
        opponent_id: str
    ) -> int:
        """Calculate how many blockers we need to hold back."""
        from src.engine import get_power, is_creature

        player = state.players.get(player_id)
        if not player:
            return 0

        # Count opponent's potential attackers
        opp_damage = 0
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = state.objects.get(obj_id)
                if obj and is_creature(obj, state) and obj.controller == opponent_id:
                    if not obj.state.tapped:
                        opp_damage += get_power(obj, state)

        # Need enough blockers to not die
        if opp_damage >= player.life:
            return 3  # Hold back several blockers
        elif opp_damage >= player.life * 0.5:
            return 2
        elif opp_damage > 0:
            return 1
        return 0

    def _is_removal(self, card) -> bool:
        """Check if card is removal."""
        if card.card_def and card.card_def.text:
            text = card.card_def.text.lower()
            return 'destroy' in text or 'exile' in text or 'damage' in text
        return False

    def _is_card_draw(self, card) -> bool:
        """Check if card draws cards."""
        if card.card_def and card.card_def.text:
            text = card.card_def.text.lower()
            return 'draw' in text
        return False

    def _is_counterspell(self, card) -> bool:
        """Check if card counters spells."""
        if card.card_def and card.card_def.text:
            text = card.card_def.text.lower()
            return 'counter' in text and 'spell' in text
        return False

    def _is_board_wipe(self, card) -> bool:
        """Check if card is a board wipe."""
        if card.card_def and card.card_def.text:
            text = card.card_def.text.lower()
            return ('destroy all' in text or 'exile all' in text or
                    'each creature' in text and 'damage' in text)
        return False

    def _has_ability(self, card, ability_name: str, state) -> bool:
        """Check if card has an ability."""
        from src.engine import has_ability
        return has_ability(card, ability_name, state)
