"""
Hyperdraft Aggro Strategy

An aggressive AI strategy that prioritizes:
- Dealing damage to the opponent
- Playing creatures quickly
- Attacking whenever possible
- Trading creatures favorably to keep pressure
"""

from typing import TYPE_CHECKING

from .base import AIStrategy

if TYPE_CHECKING:
    from src.engine import GameState, LegalAction
    from src.engine import AttackDeclaration, BlockDeclaration
    from src.ai.evaluator import BoardEvaluator


class AggroStrategy(AIStrategy):
    """
    Aggressive strategy that prioritizes face damage and quick wins.

    Key principles:
    - Always attack when possible
    - Play creatures over removal
    - Trade only when it keeps pressure
    - Burn spells go to face when winning
    """

    @property
    def name(self) -> str:
        return "Aggro"

    def evaluate_action(
        self,
        action: 'LegalAction',
        state: 'GameState',
        evaluator: 'BoardEvaluator',
        player_id: str
    ) -> float:
        """
        Score actions with aggro priorities.

        Prefers:
        1. Playing creatures (board presence)
        2. Damage spells to face when opponent is low
        3. Efficient mana usage
        4. Removal only when necessary
        """
        from src.engine import ActionType, CardType

        score = 0.0

        if action.type == ActionType.PASS:
            return -0.1  # Aggro doesn't want to pass

        if action.type == ActionType.PLAY_LAND:
            return 0.8  # Lands are necessary for aggro curve

        if action.type == ActionType.CAST_SPELL:
            card = state.objects.get(action.card_id)
            if not card:
                return 0.0

            # Creatures are top priority for aggro
            if CardType.CREATURE in card.characteristics.types:
                power = card.characteristics.power or 0
                toughness = card.characteristics.toughness or 0
                mana_cost = self._get_mana_value(card)

                # Efficiency: power per mana
                if mana_cost > 0:
                    efficiency = power / mana_cost
                    score = 1.0 + efficiency
                else:
                    score = 1.5 + power  # Free creatures are great

                # Haste bonus
                if self._has_ability(card, 'haste', state):
                    score += 0.5

                # Evasion bonus
                if self._has_ability(card, 'flying', state):
                    score += 0.3
                if self._has_ability(card, 'trample', state):
                    score += 0.3

            # Instants/Sorceries
            elif CardType.INSTANT in card.characteristics.types or \
                 CardType.SORCERY in card.characteristics.types:
                # Damage spells
                if self._is_damage_spell(card):
                    opponent_id = self._get_opponent_id(player_id, state)
                    opponent = state.players.get(opponent_id)

                    # Burn to face when opponent is low
                    if opponent and opponent.life <= 10:
                        score = 1.5
                    else:
                        score = 0.8  # Still useful

                # Removal - lower priority for aggro
                elif self._is_removal(card):
                    score = 0.6  # Only use if necessary

                # Pump spells
                elif self._is_pump(card):
                    score = 0.9  # Good for pushing damage

            # Enchantments - generally lower priority
            elif CardType.ENCHANTMENT in card.characteristics.types:
                score = 0.4

        return score

    def plan_attacks(
        self,
        state: 'GameState',
        player_id: str,
        evaluator: 'BoardEvaluator',
        legal_attackers: list[str]
    ) -> list['AttackDeclaration']:
        """
        Aggro attacks with everything almost always.

        Only holds back if:
        - Blocking would save us from lethal
        - We need specific blockers to survive
        """
        from src.engine import AttackDeclaration, get_power, is_creature

        if not legal_attackers:
            return []

        opponent_id = self._get_opponent_id(player_id, state)
        if not opponent_id:
            return []

        opponent = state.players.get(opponent_id)
        player = state.players.get(player_id)

        # Calculate opponent's potential attack
        opp_damage = 0
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = state.objects.get(obj_id)
                if obj and is_creature(obj, state) and obj.controller == opponent_id:
                    if not obj.state.tapped:
                        opp_damage += get_power(obj, state)

        # Check if we need to hold back blockers
        need_blockers = player and opp_damage >= player.life

        attacks = []
        for attacker_id in legal_attackers:
            attacker = state.objects.get(attacker_id)
            if not attacker:
                continue

            # If we need blockers, hold back our biggest creatures
            if need_blockers:
                power = get_power(attacker, state)
                # Keep creatures that can kill attackers
                # Simple heuristic: hold back if power >= 2
                if power >= 2:
                    continue

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
        Aggro blocks defensively - only to prevent lethal or trade up.

        Blocking philosophy:
        - Block if we die otherwise
        - Trade only if we come out ahead
        - Never chump block unless lethal
        """
        from src.engine import BlockDeclaration, get_power, get_toughness

        if not attackers or not legal_blockers:
            return []

        player = state.players.get(player_id)
        if not player:
            return []

        blocks = []
        used_blockers = set()

        # Calculate total incoming damage
        total_damage = sum(
            get_power(state.objects.get(a.attacker_id), state)
            for a in attackers
            if state.objects.get(a.attacker_id)
        )

        # If damage is lethal, we must block
        lethal_incoming = total_damage >= player.life

        for attack in attackers:
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

                # Would we kill the attacker?
                kills_attacker = blocker_power >= attacker_toughness
                # Would we die?
                dies = attacker_power >= blocker_toughness

                value = 0

                # Favorable trade: we kill them, we survive
                if kills_attacker and not dies:
                    value = 100
                # Even trade: both die
                elif kills_attacker and dies:
                    # Only trade if attacker is worth more
                    attacker_value = attacker_power + attacker_toughness
                    blocker_value = blocker_power + blocker_toughness
                    if attacker_value >= blocker_value:
                        value = 50
                # Chump block: only if lethal
                elif lethal_incoming:
                    value = 10 + (attacker_power * 2)  # Prefer blocking big attackers

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
        Aggro keeps more hands - needs to curve out.
        """
        thresholds = {
            0: 0.5,   # Keep reasonable hands on 7
            1: 0.4,   # Keep mediocre on 6
            2: 0.2,   # Keep bad hands on 5
            3: 0.0,   # Keep almost anything on 4
        }
        return thresholds.get(mulligan_count, 0.0)

    # Helper methods

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

    def _is_damage_spell(self, card) -> bool:
        """Check if card deals damage."""
        if card.card_def and card.card_def.text:
            text = card.card_def.text.lower()
            return 'damage' in text
        return False

    def _is_removal(self, card) -> bool:
        """Check if card is removal."""
        if card.card_def and card.card_def.text:
            text = card.card_def.text.lower()
            return 'destroy' in text or 'exile' in text
        return False

    def _is_pump(self, card) -> bool:
        """Check if card pumps creatures."""
        if card.card_def and card.card_def.text:
            text = card.card_def.text.lower()
            return '+' in text and '/' in text  # e.g., +2/+2
        return False
