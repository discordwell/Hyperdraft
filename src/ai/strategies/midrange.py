"""
Hyperdraft Midrange Strategy

A balanced AI strategy that adapts to the game state:
- Plays aggressively when ahead
- Plays defensively when behind
- Focuses on value and efficient trades
"""

from typing import TYPE_CHECKING

from .base import AIStrategy

if TYPE_CHECKING:
    from src.engine import GameState, LegalAction
    from src.engine import AttackDeclaration, BlockDeclaration
    from src.ai.evaluator import BoardEvaluator


class MidrangeStrategy(AIStrategy):
    """
    Midrange strategy that adapts based on board state.

    Key principles:
    - Evaluate board position and play accordingly
    - When ahead: press advantage (like aggro)
    - When behind: stabilize (like control)
    - Focus on value creatures and efficient answers
    """

    @property
    def name(self) -> str:
        return "Midrange"

    @property
    def reactivity(self) -> float:
        """Midrange adapts - moderate reactivity."""
        return 0.6

    def evaluate_action(
        self,
        action: 'LegalAction',
        state: 'GameState',
        evaluator: 'BoardEvaluator',
        player_id: str
    ) -> float:
        """
        Score actions with midrange priorities.

        Adapts scoring based on whether we're ahead or behind.
        """
        from src.engine import ActionType, CardType

        # Get our current position
        board_score = evaluator.evaluate(player_id)
        ahead = board_score > 0.2
        behind = board_score < -0.2
        role = self._clock_role(state, player_id)
        is_beatdown = role == 'beatdown'

        score = 0.0

        if action.type == ActionType.PASS:
            # Passing only beats playing if we have a real reason: an instant
            # we want to hold up AND opponent can plausibly act. In our own
            # main phase with the stack empty, just play things.
            if self._has_instant_in_hand(state, player_id) and behind and not is_beatdown:
                return 0.15
            return 0.0

        if action.type == ActionType.PLAY_LAND:
            return 0.85  # Lands are always important

        if action.type == ActionType.CAST_SPELL:
            card = state.objects.get(action.card_id)
            if not card:
                return 0.0

            mana_value = self._get_mana_value(card)

            # Creatures
            if CardType.CREATURE in card.characteristics.types:
                power = card.characteristics.power or 0
                toughness = card.characteristics.toughness or 0
                stats_total = power + toughness

                # Midrange loves efficient creatures
                if mana_value > 0:
                    efficiency = stats_total / mana_value
                    score = 1.0 + (efficiency * 0.3)
                else:
                    score = 1.0 + stats_total * 0.2

                # When behind, prefer defensive creatures
                if behind:
                    if toughness > power:
                        score += 0.3
                    if self._has_ability(card, 'lifelink', state):
                        score += 0.4

                # When ahead, prefer aggressive creatures
                if ahead:
                    if power > toughness:
                        score += 0.2
                    if self._has_ability(card, 'haste', state):
                        score += 0.4
                    if self._has_ability(card, 'trample', state):
                        score += 0.3

                # Beatdown role: clock favours us, so creatures matter more
                # than answers. Push aggressive plays harder.
                if is_beatdown:
                    score += 0.4
                    if power >= 2:
                        score += 0.2

                # Value abilities
                if self._has_ability(card, 'flying', state):
                    score += 0.3
                if self._has_ability(card, 'vigilance', state):
                    score += 0.25
                if self._has_ability(card, 'deathtouch', state):
                    score += 0.35

            # Burn / damage spells — direct damage to face is reach. Score
            # higher when the opponent is closer to lethal.
            elif self._is_damage_spell(card):
                opponent_id = self._get_opponent_id(player_id, state)
                opponent = state.players.get(opponent_id) if opponent_id else None
                if opponent and opponent.life <= 8:
                    score = 1.7  # Closing damage — top priority
                elif opponent and opponent.life <= 14:
                    score = 1.2
                else:
                    score = 0.9  # Always playable, less urgent
                # Beatdown role: burn is critical reach
                if is_beatdown:
                    score += 0.3

            # Removal — score by the most dangerous threat on board, not
            # a generic creature count. A removal spell against a 1/1 token
            # is very different from one against a 5/5 with deathtouch.
            elif self._is_removal(card):
                worst_threat = self._max_opponent_threat_value(state, player_id)
                if worst_threat >= 8:
                    score = 1.8  # Mandatory answer
                elif worst_threat >= 5:
                    score = 1.4
                elif worst_threat >= 3:
                    score = 1.0
                elif worst_threat > 0:
                    score = 0.5  # There's something but it's small
                else:
                    score = 0.2  # No targets — hold removal
                # Behind makes removal more urgent at every threat level.
                if behind and worst_threat > 0:
                    score += 0.3
                # Beatdown role wants tempo, not removal — discount unless
                # the threat is genuinely scary.
                if is_beatdown and worst_threat < 5:
                    score -= 0.3

            # Card draw
            elif self._is_card_draw(card):
                # Card draw is better when at parity
                if not ahead and not behind:
                    score = 1.4
                elif behind:
                    score = 1.0  # Need to find answers
                else:
                    score = 0.8  # Can afford to draw

            # Pump spells
            elif self._is_pump(card):
                if ahead:
                    score = 0.9  # Press advantage
                else:
                    score = 0.4  # Less useful when behind

            # Enchantments/Artifacts
            elif CardType.ENCHANTMENT in card.characteristics.types or \
                 CardType.ARTIFACT in card.characteristics.types:
                score = 0.6

        # Mana efficiency bonus
        if action.type == ActionType.CAST_SPELL:
            card = state.objects.get(action.card_id)
            if card:
                mana_value = self._get_mana_value(card)
                available_mana = self._count_available_mana(state, player_id)

                # Using mana efficiently is good
                if mana_value == available_mana:
                    score += 0.2
                elif mana_value == available_mana - 1:
                    score += 0.1

        return score

    def plan_attacks(
        self,
        state: 'GameState',
        player_id: str,
        evaluator: 'BoardEvaluator',
        legal_attackers: list[str]
    ) -> list['AttackDeclaration']:
        """
        Midrange attacks based on board position.

        When ahead: attack with most creatures
        When behind: attack only with evasive/protected creatures
        At parity: attack with creatures that trade favorably
        """
        from src.engine import AttackDeclaration, get_power, get_toughness, is_creature

        if not legal_attackers:
            return []

        opponent_id = self._get_opponent_id(player_id, state)
        if not opponent_id:
            return []

        # Analyze board position
        board_score = evaluator.evaluate(player_id)
        ahead = board_score > 0.2
        behind = board_score < -0.2

        opponent = state.players.get(opponent_id)
        player = state.players.get(player_id)

        # Get opponent's blockers
        opp_blockers = []
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = state.objects.get(obj_id)
                if obj and is_creature(obj, state) and obj.controller == opponent_id:
                    if not obj.state.tapped:
                        opp_blockers.append(obj)

        # Lethal-swing detection. If all attackers together can deal lethal AND
        # opponent has no realistic block coverage, swing with everything. Two
        # cheap scenarios that catch the common case:
        #   (a) opponent has zero untapped blockers and our total power >= life,
        #   (b) total evasive (flying/unblockable) power >= life regardless of blockers.
        # Without this short-circuit, midrange logic at parity often under-attacks.
        if opponent and opponent.life is not None:
            total_power = 0
            evasive_power = 0
            for aid in legal_attackers:
                a = state.objects.get(aid)
                if not a:
                    continue
                p = get_power(a, state)
                total_power += p
                if (self._has_ability(a, 'flying', state)
                    or self._has_ability(a, 'unblockable', state)
                    or self._has_ability(a, 'menace', state) and len(opp_blockers) < 2):
                    evasive_power += p
            if (not opp_blockers and total_power >= opponent.life) or evasive_power >= opponent.life:
                return [AttackDeclaration(
                    attacker_id=aid,
                    defending_player_id=opponent_id,
                    is_attacking_planeswalker=False,
                ) for aid in legal_attackers if state.objects.get(aid)]

        attacks = []

        for attacker_id in legal_attackers:
            attacker = state.objects.get(attacker_id)
            if not attacker:
                continue

            power = get_power(attacker, state)
            toughness = get_toughness(attacker, state)

            should_attack = False

            # When ahead: attack with most creatures
            if ahead:
                should_attack = True
                # Hold back small creatures if opponent has big blockers
                if power <= 1:
                    for blocker in opp_blockers:
                        blocker_power = get_power(blocker, state)
                        if blocker_power >= toughness and power < get_toughness(blocker, state):
                            should_attack = False
                            break

            # When behind: only attack with safe creatures
            elif behind:
                # Attack with evasive creatures
                if self._has_ability(attacker, 'flying', state):
                    has_flying_blocker = any(
                        self._has_ability(b, 'flying', state) or
                        self._has_ability(b, 'reach', state)
                        for b in opp_blockers
                    )
                    if not has_flying_blocker:
                        should_attack = True

                # Attack with unblockable
                if self._has_ability(attacker, 'unblockable', state):
                    should_attack = True

                # Menace is effectively unblockable when the opponent has fewer than two blockers.
                if self._has_ability(attacker, 'menace', state) and len(opp_blockers) < 2:
                    should_attack = True

                # Attack if we can't lose the creature
                if self._has_ability(attacker, 'indestructible', state):
                    should_attack = True

            # At parity: attack if we trade favorably
            else:
                should_attack = True
                # Check if we'd trade poorly
                for blocker in opp_blockers:
                    blocker_power = get_power(blocker, state)
                    blocker_toughness = get_toughness(blocker, state)

                    # Would we die?
                    we_die = blocker_power >= toughness
                    # Would they die?
                    they_die = power >= blocker_toughness

                    # Don't attack into bad trades
                    if we_die and not they_die:
                        # Unless we have evasion
                        if not (self._has_ability(attacker, 'flying', state) or
                                self._has_ability(attacker, 'trample', state) or
                                self._has_ability(attacker, 'unblockable', state) or
                                (self._has_ability(attacker, 'menace', state) and len(opp_blockers) < 2)):
                            should_attack = False
                            break

            if should_attack:
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
        Midrange blocks to protect life and trade favorably.

        Block when:
        - We can trade up or even
        - We need to protect our life total
        - We can kill a threat
        """
        from src.engine import BlockDeclaration, get_power, get_toughness

        if not attackers or not legal_blockers:
            return []

        player = state.players.get(player_id)
        if not player:
            return []

        # Analyze board
        board_score = evaluator.evaluate(player_id)
        behind = board_score < -0.2

        blocks = []
        used_blockers = set()

        # Calculate incoming damage
        total_damage = sum(
            get_power(state.objects.get(a.attacker_id), state)
            for a in attackers
            if state.objects.get(a.attacker_id)
        )
        lethal_incoming = total_damage >= player.life

        # Sort attackers by threat level (power + abilities)
        threat_levels = []
        for attack in attackers:
            attacker = state.objects.get(attack.attacker_id)
            if attacker:
                power = get_power(attacker, state)
                threat = power
                if self._has_ability(attacker, 'trample', state):
                    threat += 1
                if self._has_ability(attacker, 'lifelink', state):
                    threat += 2
                if self._has_ability(attacker, 'deathtouch', state):
                    threat += 1
                threat_levels.append((attack, threat))

        threat_levels.sort(key=lambda x: x[1], reverse=True)

        for attack, _ in threat_levels:
            attacker = state.objects.get(attack.attacker_id)
            if not attacker:
                continue

            attacker_power = get_power(attacker, state)
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

                # Deathtouch always kills
                if self._has_ability(blocker, 'deathtouch', state):
                    kills_attacker = True
                if self._has_ability(attacker, 'deathtouch', state):
                    dies = True

                value = 0

                # Perfect block: kill them, survive
                if kills_attacker and not dies:
                    value = 150

                # Even trade
                elif kills_attacker and dies:
                    # Trade if attacker is worth more
                    attacker_val = attacker_power + attacker_toughness
                    blocker_val = blocker_power + blocker_toughness

                    if attacker_val >= blocker_val:
                        value = 80
                    else:
                        value = 30  # Slight downgrade but still okay

                # Chump block
                elif not kills_attacker:
                    avoid_nonlethal_trample_chump = (
                        self._has_ability(attacker, 'trample', state)
                        and dies
                        and attacker_power - blocker_toughness < player.life
                        and blocker_toughness <= 1
                    )
                    if lethal_incoming:
                        value = 50 + attacker_power  # Must block
                    elif avoid_nonlethal_trample_chump:
                        value = 0
                    elif behind and attacker_power >= 3:
                        value = 20  # Protect life when behind

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
        Midrange is moderately picky about hands.
        """
        thresholds = {
            0: 0.55,  # Need a reasonable hand
            1: 0.45,  # Okay with decent
            2: 0.25,  # Keep most on 5
            3: 0.05,  # Keep almost anything
        }
        return thresholds.get(mulligan_count, 0.0)

    # Helper methods

    def _has_instant_in_hand(self, state: 'GameState', player_id: str) -> bool:
        """Check if player has instant-speed spells."""
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

    def _count_opponent_threats(self, state: 'GameState', player_id: str) -> int:
        """Count threatening opponent creatures."""
        from src.engine import get_power, is_creature

        opponent_id = self._get_opponent_id(player_id, state)
        count = 0

        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = state.objects.get(obj_id)
                if obj and is_creature(obj, state) and obj.controller == opponent_id:
                    power = get_power(obj, state)
                    if power >= 2:  # Count as threat if 2+ power
                        count += 1
        return count

    def _count_available_mana(self, state: 'GameState', player_id: str) -> int:
        """Count untapped lands."""
        from src.engine import CardType

        count = 0
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = state.objects.get(obj_id)
                if obj and obj.controller == player_id:
                    if CardType.LAND in obj.characteristics.types:
                        if not obj.state.tapped:
                            count += 1
        return count

    def _get_mana_value(self, card) -> int:
        """Get converted mana cost."""
        from src.engine import ManaCost
        if card.characteristics.mana_cost:
            cost = ManaCost.parse(card.characteristics.mana_cost)
            return cost.mana_value
        return 0

    def _has_ability(self, card, ability_name: str, state) -> bool:
        """Check if card has an ability."""
        from src.engine import has_ability
        return has_ability(card, ability_name, state)

    def _is_removal(self, card) -> bool:
        """Check if card is removal."""
        if card.card_def and card.card_def.text:
            text = card.card_def.text.lower()
            return 'destroy' in text or 'exile' in text
        return False

    def _is_damage_spell(self, card) -> bool:
        """Check if card deals direct damage (burn). Excludes creature
        triggers — those are scored as creatures."""
        if card.card_def and card.card_def.text:
            text = card.card_def.text.lower()
            return 'deal' in text and 'damage' in text
        return False

    def _is_card_draw(self, card) -> bool:
        """Check if card draws cards."""
        if card.card_def and card.card_def.text:
            text = card.card_def.text.lower()
            return 'draw' in text
        return False

    def _is_pump(self, card) -> bool:
        """Check if card pumps creatures."""
        if card.card_def and card.card_def.text:
            text = card.card_def.text.lower()
            return '+' in text and '/' in text
        return False
