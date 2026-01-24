"""
Hyperdraft AI Heuristics

Quick decision-making rules that don't require deep calculation.
These are fast evaluations used for common situations.
"""

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import GameState, GameObject


class Heuristics:
    """
    Quick heuristics for common MTG decisions.

    These provide fast answers for situations where deep calculation
    isn't necessary or would be overkill.
    """

    # Card type weights for generic evaluations
    CREATURE_VALUE = 1.0
    REMOVAL_VALUE = 1.5
    DRAW_VALUE = 1.2
    RAMP_VALUE = 1.1
    COUNTER_VALUE = 1.3

    # Life threshold constants
    CRITICAL_LIFE_THRESHOLD = 5
    LOW_LIFE_THRESHOLD = 10
    COMFORTABLE_LIFE = 15

    # Hand size constants
    IDEAL_HAND_SIZE = 4
    FLOOD_THRESHOLD = 6
    SCREW_THRESHOLD = 2

    @staticmethod
    def is_good_opening_hand(
        hand: list['GameObject'],
        mulligan_count: int
    ) -> bool:
        """
        Determine if an opening hand is keepable.

        Basic criteria:
        - 2-5 lands for a 7-card hand
        - Adjust down for mulligans
        - At least one playable spell
        """
        lands = [card for card in hand if Heuristics._is_land(card)]
        spells = [card for card in hand if not Heuristics._is_land(card)]

        land_count = len(lands)
        spell_count = len(spells)
        hand_size = len(hand)

        # Adjust land requirements based on mulligan count
        if mulligan_count == 0:  # 7 cards
            min_lands = 2
            max_lands = 5
        elif mulligan_count == 1:  # 6 cards
            min_lands = 2
            max_lands = 4
        elif mulligan_count == 2:  # 5 cards
            min_lands = 1
            max_lands = 4
        else:  # 4 or fewer cards - keep almost anything
            return land_count >= 1 and spell_count >= 1

        # Check land count
        if land_count < min_lands or land_count > max_lands:
            return False

        # Need at least one playable spell (CMC <= land_count + 1)
        playable_spells = [
            s for s in spells
            if Heuristics._get_mana_value(s) <= land_count + 1
        ]

        return len(playable_spells) >= 1

    @staticmethod
    def should_attack_with_all(
        my_creatures: list['GameObject'],
        opponent_creatures: list['GameObject'],
        my_life: int,
        opponent_life: int,
        state: 'GameState'
    ) -> bool:
        """
        Quick check if swinging with everything is a good idea.

        Generally good when:
        - Opponent is at low life and can't block lethal
        - We have overwhelming board advantage
        - Opponent has no blockers
        """
        if not my_creatures:
            return False

        total_power = sum(Heuristics._get_creature_power(c, state) for c in my_creatures)

        # Lethal on board and opponent can't block all
        if total_power >= opponent_life and len(my_creatures) > len(opponent_creatures):
            return True

        # No blockers = free damage
        if not opponent_creatures:
            return True

        # Overwhelming board (2x or more creatures)
        if len(my_creatures) >= len(opponent_creatures) * 2:
            return True

        return False

    @staticmethod
    def should_block(
        blocker: 'GameObject',
        attacker: 'GameObject',
        my_life: int,
        state: 'GameState'
    ) -> bool:
        """
        Quick evaluation of whether to block.

        Generally block when:
        - We would trade favorably
        - We're at low life and need to block
        - Blocker is worth less than the damage prevented
        """
        blocker_power = Heuristics._get_creature_power(blocker, state)
        blocker_toughness = Heuristics._get_creature_toughness(blocker, state)
        attacker_power = Heuristics._get_creature_power(attacker, state)
        attacker_toughness = Heuristics._get_creature_toughness(attacker, state)

        blocker_dies = attacker_power >= blocker_toughness
        attacker_dies = blocker_power >= attacker_toughness

        # Always block if we kill the attacker and survive
        if attacker_dies and not blocker_dies:
            return True

        # Trade is usually good
        if attacker_dies and blocker_dies:
            # Trade up or equal
            attacker_value = Heuristics._creature_combat_value(attacker, state)
            blocker_value = Heuristics._creature_combat_value(blocker, state)
            if attacker_value >= blocker_value:
                return True

        # Chump block if at low life
        if my_life <= Heuristics.CRITICAL_LIFE_THRESHOLD:
            if attacker_power >= my_life:
                return True

        # Block if damage is significant relative to our life
        if my_life <= Heuristics.LOW_LIFE_THRESHOLD:
            if attacker_power >= 3:
                return True

        return False

    @staticmethod
    def get_best_target(
        targets: list[str],
        state: 'GameState',
        prefer_creatures: bool = True
    ) -> Optional[str]:
        """
        Get the best target from a list of legal targets.

        Prefers:
        - Higher value creatures
        - Threats over utility creatures
        - Players if no good creature targets
        """
        if not targets:
            return None

        best_target = None
        best_value = -1

        for target_id in targets:
            # Check if it's a player
            player = state.players.get(target_id)
            if player:
                if not prefer_creatures:
                    return target_id  # Player is best target for damage
                continue

            # Check if it's an object
            obj = state.objects.get(target_id)
            if obj:
                value = Heuristics._target_value(obj, state)
                if value > best_value:
                    best_value = value
                    best_target = target_id

        # Return best creature target, or first player if no creatures
        if best_target:
            return best_target

        # Fallback to first target
        return targets[0]

    @staticmethod
    def cast_priority_score(
        card: 'GameObject',
        state: 'GameState',
        available_mana: int
    ) -> float:
        """
        Score a card for casting priority.

        Higher scores = cast first.
        Considers:
        - Mana efficiency
        - Card type priority
        - Current board state
        """
        mana_value = Heuristics._get_mana_value(card)

        # Can't cast if not enough mana
        if mana_value > available_mana:
            return -1.0

        score = 0.0

        # Mana efficiency bonus (using mana efficiently is good)
        if mana_value == available_mana:
            score += 0.3
        elif mana_value == available_mana - 1:
            score += 0.2

        # Card type bonuses
        if Heuristics._is_creature(card):
            score += Heuristics.CREATURE_VALUE
            # Bonus for stats
            power = card.characteristics.power or 0
            toughness = card.characteristics.toughness or 0
            score += (power + toughness) * 0.1

        if Heuristics._is_removal(card):
            score += Heuristics.REMOVAL_VALUE

        if Heuristics._is_draw(card):
            score += Heuristics.DRAW_VALUE

        # Normalize by mana value
        if mana_value > 0:
            score = score / mana_value

        return score

    # Helper methods

    @staticmethod
    def _is_land(card: 'GameObject') -> bool:
        """Check if card is a land."""
        from src.engine import CardType
        return CardType.LAND in card.characteristics.types

    @staticmethod
    def _is_creature(card: 'GameObject') -> bool:
        """Check if card is a creature."""
        from src.engine import CardType
        return CardType.CREATURE in card.characteristics.types

    @staticmethod
    def _is_removal(card: 'GameObject') -> bool:
        """Check if card is likely removal based on common patterns."""
        # Simple heuristic: instant/sorcery with 'destroy' or 'damage' in text
        from src.engine import CardType
        if CardType.INSTANT not in card.characteristics.types and \
           CardType.SORCERY not in card.characteristics.types:
            return False

        if card.card_def and card.card_def.text:
            text = card.card_def.text.lower()
            return 'destroy' in text or 'damage' in text or 'exile' in text
        return False

    @staticmethod
    def _is_draw(card: 'GameObject') -> bool:
        """Check if card draws cards."""
        if card.card_def and card.card_def.text:
            text = card.card_def.text.lower()
            return 'draw' in text
        return False

    @staticmethod
    def _get_mana_value(card: 'GameObject') -> int:
        """Get converted mana cost of a card."""
        from src.engine import ManaCost
        if card.characteristics.mana_cost:
            cost = ManaCost.parse(card.characteristics.mana_cost)
            return cost.mana_value
        return 0

    @staticmethod
    def _get_creature_power(creature: 'GameObject', state: 'GameState') -> int:
        """Get a creature's current power."""
        from src.engine import get_power
        return get_power(creature, state)

    @staticmethod
    def _get_creature_toughness(creature: 'GameObject', state: 'GameState') -> int:
        """Get a creature's current toughness."""
        from src.engine import get_toughness
        return get_toughness(creature, state)

    @staticmethod
    def _creature_combat_value(creature: 'GameObject', state: 'GameState') -> float:
        """Evaluate a creature's combat value (power + toughness + abilities)."""
        from src.engine import get_power, get_toughness, has_ability

        power = get_power(creature, state)
        toughness = get_toughness(creature, state)

        value = power + toughness

        # Ability bonuses
        if has_ability(creature, 'flying', state):
            value += 1.5
        if has_ability(creature, 'trample', state):
            value += 0.5
        if has_ability(creature, 'deathtouch', state):
            value += 2.0
        if has_ability(creature, 'lifelink', state):
            value += 1.0
        if has_ability(creature, 'vigilance', state):
            value += 0.5
        if has_ability(creature, 'first_strike', state):
            value += 1.0
        if has_ability(creature, 'double_strike', state):
            value += power  # Double power effectively
        if has_ability(creature, 'hexproof', state):
            value += 1.5
        if has_ability(creature, 'indestructible', state):
            value += 3.0

        return value

    @staticmethod
    def _target_value(obj: 'GameObject', state: 'GameState') -> float:
        """Evaluate how valuable a target is (higher = better to target)."""
        from src.engine import CardType

        value = 0.0

        if CardType.CREATURE in obj.characteristics.types:
            value = Heuristics._creature_combat_value(obj, state)
        elif CardType.ENCHANTMENT in obj.characteristics.types:
            value = 2.0  # Enchantments are often high value
        elif CardType.ARTIFACT in obj.characteristics.types:
            value = 1.5
        elif CardType.PLANESWALKER in obj.characteristics.types:
            value = 4.0  # Planeswalkers are high priority

        # Bonus for cards that are tapped (easier to kill)
        if obj.state.tapped:
            value += 0.5

        return value
