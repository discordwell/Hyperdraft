"""
Reactive Evaluator for instant-speed decision making.

This module provides AI capabilities for evaluating and responding to
stack threats, enabling proper use of counterspells, instant removal,
and combat tricks.
"""

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
import re

if TYPE_CHECKING:
    from src.engine import GameState, GameObject
    from src.engine.stack import StackItem


@dataclass
class StackThreatAssessment:
    """Assessment of a spell/ability on the stack."""
    item_id: str
    threat_level: float          # 0.0-1.0
    is_counterable: bool
    is_board_wipe: bool
    targets_our_creatures: bool
    targets_us: bool
    mana_value: int


@dataclass
class CombatCreatureInfo:
    """Information about a creature in combat."""
    creature_id: str
    power: int
    toughness: int
    is_attacking: bool
    is_blocking: bool
    controller: str
    blocking_ids: list[str] = field(default_factory=list)  # What this creature is blocking
    blocked_by_ids: list[str] = field(default_factory=list)  # What is blocking this creature


@dataclass
class ReactiveContext:
    """Context for evaluating reactive plays."""
    stack_threats: list[StackThreatAssessment] = field(default_factory=list)
    highest_threat: Optional[StackThreatAssessment] = None
    in_combat: bool = False
    is_our_turn: bool = True
    our_creatures_at_risk: list[str] = field(default_factory=list)
    available_mana: int = 0
    instants_in_hand: list[str] = field(default_factory=list)
    # Combat-specific info
    our_attackers: list[CombatCreatureInfo] = field(default_factory=list)
    our_blockers: list[CombatCreatureInfo] = field(default_factory=list)
    enemy_attackers: list[CombatCreatureInfo] = field(default_factory=list)
    enemy_blockers: list[CombatCreatureInfo] = field(default_factory=list)


class ReactiveEvaluator:
    """Evaluates reactive opportunities for instant-speed plays."""

    CRITICAL_THREAT = 0.8
    HIGH_THREAT = 0.6

    def __init__(self, state: 'GameState'):
        self.state = state

    def build_context(self, player_id: str, stack_items: list = None) -> ReactiveContext:
        """Build reactive context for current game state."""
        threats = []
        if stack_items:
            for item in stack_items:
                controller_id = getattr(item, 'controller_id', None) or getattr(item, 'controller', None)
                if controller_id != player_id:
                    assessment = self._assess_stack_item(item, player_id)
                    threats.append(assessment)

        threats.sort(key=lambda t: t.threat_level, reverse=True)

        in_combat = self._is_in_combat()

        # Build combat info if in combat
        our_attackers = []
        our_blockers = []
        enemy_attackers = []
        enemy_blockers = []

        if in_combat:
            combat_info = self._get_combat_info(player_id)
            our_attackers = combat_info.get('our_attackers', [])
            our_blockers = combat_info.get('our_blockers', [])
            enemy_attackers = combat_info.get('enemy_attackers', [])
            enemy_blockers = combat_info.get('enemy_blockers', [])

        return ReactiveContext(
            stack_threats=threats,
            highest_threat=threats[0] if threats else None,
            in_combat=in_combat,
            is_our_turn=self._is_our_turn(player_id),
            available_mana=self._count_available_mana(player_id),
            instants_in_hand=self._get_instants_in_hand(player_id),
            our_attackers=our_attackers,
            our_blockers=our_blockers,
            enemy_attackers=enemy_attackers,
            enemy_blockers=enemy_blockers
        )

    def _assess_stack_item(self, item, player_id: str) -> StackThreatAssessment:
        """Assess threat level of a stack item."""
        threat_level = 0.3  # Base threat
        is_board_wipe = False
        targets_creatures = False
        targets_us = False
        mana_value = 0

        # Get the card from the stack item
        card_id = getattr(item, 'card_id', None) or getattr(item, 'source_id', None)
        card = self.state.objects.get(card_id) if card_id else None

        if card and card.card_def:
            text = (card.card_def.text or '').lower()
            mana_value = self._get_mana_value(card)

            # Board wipes are critical
            if 'destroy all' in text or 'exile all' in text:
                is_board_wipe = True
                threat_level = 0.9
            # Targeted removal
            elif 'destroy target' in text or 'exile target' in text:
                targets_creatures = True
                threat_level = 0.6
            # Damage spells
            elif 'damage' in text:
                threat_level = 0.5
                if self._targets_us(item, player_id):
                    targets_us = True
                    damage = self._estimate_damage(text)
                    player = self.state.players.get(player_id)
                    if player and damage >= player.life:
                        threat_level = 1.0  # Lethal!

        item_id = getattr(item, 'id', str(id(item)))
        return StackThreatAssessment(
            item_id=item_id,
            threat_level=min(1.0, threat_level),
            is_counterable=getattr(item, 'can_be_countered', True),
            is_board_wipe=is_board_wipe,
            targets_our_creatures=targets_creatures,
            targets_us=targets_us,
            mana_value=mana_value
        )

    def get_counterspell_bonus(self, context: ReactiveContext, reactivity: float) -> float:
        """Calculate bonus for casting a counterspell."""
        if not context.highest_threat:
            return 0.0

        threat = context.highest_threat
        if not threat.is_counterable:
            return -10.0  # Can't counter, don't try

        if threat.threat_level >= self.CRITICAL_THREAT:
            bonus = 2.0
        elif threat.threat_level >= self.HIGH_THREAT:
            bonus = 1.5
        else:
            bonus = threat.threat_level * 1.2

        if threat.is_board_wipe:
            bonus += 0.5

        return bonus * reactivity

    def get_removal_bonus(self, context: ReactiveContext, reactivity: float) -> float:
        """Calculate bonus for using instant removal reactively."""
        bonus = 0.0

        # Response to buff/threat spell
        if context.stack_threats:
            bonus += 1.5 * reactivity

        # Combat situation
        if context.in_combat:
            bonus += 0.5 * reactivity

        # End of opponent's turn
        if not context.is_our_turn:
            bonus += 0.3

        return bonus

    def get_combat_trick_bonus(
        self,
        context: ReactiveContext,
        reactivity: float,
        trick_card=None,
        target_creature_id: str = None
    ) -> float:
        """
        Calculate bonus for combat tricks.

        Only returns a bonus if the trick would change the combat outcome:
        - Save a creature that would die
        - Kill an enemy creature that would survive
        - Enable a profitable attack/block that wasn't possible

        Args:
            context: The reactive context with combat info
            reactivity: Strategy's reactivity level
            trick_card: The combat trick card being evaluated
            target_creature_id: The creature we'd target with the trick
        """
        if not context.in_combat:
            return 0.0

        # No creatures in combat means no value
        all_our_combat = context.our_attackers + context.our_blockers
        all_enemy_combat = context.enemy_attackers + context.enemy_blockers
        if not all_our_combat and not all_enemy_combat:
            return 0.0

        # Parse the trick's effect
        power_boost, toughness_boost = self._parse_pump_effect(trick_card)
        if power_boost == 0 and toughness_boost == 0:
            return 0.0  # Not a pump spell, no combat trick value

        # Find scenarios where the trick changes the outcome
        bonus = 0.0

        # Check our attackers - would the trick let us kill a blocker we couldn't?
        for attacker in context.our_attackers:
            if target_creature_id and attacker.creature_id != target_creature_id:
                continue

            for blocker_id in attacker.blocked_by_ids:
                blocker = self._find_creature_info(blocker_id, all_enemy_combat)
                if not blocker:
                    continue

                # Without trick: do we kill the blocker?
                kills_without = attacker.power >= blocker.toughness
                # With trick: do we kill the blocker?
                kills_with = (attacker.power + power_boost) >= blocker.toughness

                # Without trick: do we die?
                dies_without = blocker.power >= attacker.toughness
                # With trick: do we die?
                dies_with = blocker.power >= (attacker.toughness + toughness_boost)

                # Trick enables a kill we couldn't get
                if kills_with and not kills_without:
                    bonus += 1.5

                # Trick saves our creature from dying
                if dies_without and not dies_with:
                    bonus += 1.2

        # Check our blockers - would the trick save us or let us kill?
        for blocker in context.our_blockers:
            if target_creature_id and blocker.creature_id != target_creature_id:
                continue

            for attacker_id in blocker.blocking_ids:
                attacker = self._find_creature_info(attacker_id, all_enemy_combat)
                if not attacker:
                    continue

                # Without trick: do we kill the attacker?
                kills_without = blocker.power >= attacker.toughness
                # With trick: do we kill the attacker?
                kills_with = (blocker.power + power_boost) >= attacker.toughness

                # Without trick: do we die?
                dies_without = attacker.power >= blocker.toughness
                # With trick: do we die?
                dies_with = attacker.power >= (blocker.toughness + toughness_boost)

                # Trick enables a kill
                if kills_with and not kills_without:
                    bonus += 1.5

                # Trick saves our blocker
                if dies_without and not dies_with:
                    bonus += 1.2

        # If no outcome changes, don't waste the trick
        if bonus == 0.0:
            return -0.5  # Slight penalty for wasting a combat trick

        return bonus * reactivity

    def _find_creature_info(
        self,
        creature_id: str,
        creature_list: list[CombatCreatureInfo]
    ) -> Optional[CombatCreatureInfo]:
        """Find a creature in a list by ID."""
        for c in creature_list:
            if c.creature_id == creature_id:
                return c
        return None

    def _parse_pump_effect(self, card) -> tuple[int, int]:
        """Parse a pump spell to get power/toughness boost."""
        if not card or not card.card_def or not card.card_def.text:
            return (0, 0)

        text = card.card_def.text.lower()

        # Match patterns like "+2/+2", "+3/+0", "+0/+4", etc.
        match = re.search(r'\+(\d+)/\+(\d+)', text)
        if match:
            return (int(match.group(1)), int(match.group(2)))

        # Match "gets +X/+Y"
        match = re.search(r'gets \+(\d+)/\+(\d+)', text)
        if match:
            return (int(match.group(1)), int(match.group(2)))

        return (0, 0)

    def get_hold_mana_penalty(self, card, context: ReactiveContext, reactivity: float) -> float:
        """Calculate penalty for tapping out when we have instants."""
        if reactivity < 0.3 or not context.instants_in_hand:
            return 0.0

        card_cost = self._get_mana_value(card)
        remaining = context.available_mana - card_cost

        if remaining < 2:  # Can't cast most instants
            return 0.4 * reactivity
        return 0.0

    # Helper methods

    def _get_combat_info(self, player_id: str) -> dict:
        """Gather information about creatures currently in combat."""
        from src.engine import get_power, get_toughness, is_creature

        result = {
            'our_attackers': [],
            'our_blockers': [],
            'enemy_attackers': [],
            'enemy_blockers': []
        }

        # Get combat manager if available
        combat_manager = getattr(self.state, 'combat_manager', None)
        if not combat_manager:
            return result

        # Get declared attackers and blockers
        attackers = getattr(combat_manager, 'attackers', []) or []
        blocks = getattr(combat_manager, 'blocks', []) or []

        # Build a map of attacker -> blockers and blocker -> attackers
        attacker_to_blockers: dict[str, list[str]] = {}
        blocker_to_attackers: dict[str, list[str]] = {}

        for block in blocks:
            blocker_id = getattr(block, 'blocker_id', None)
            attacker_id = getattr(block, 'blocking_attacker_id', None) or getattr(block, 'attacker_id', None)

            if blocker_id and attacker_id:
                if attacker_id not in attacker_to_blockers:
                    attacker_to_blockers[attacker_id] = []
                attacker_to_blockers[attacker_id].append(blocker_id)

                if blocker_id not in blocker_to_attackers:
                    blocker_to_attackers[blocker_id] = []
                blocker_to_attackers[blocker_id].append(attacker_id)

        # Process attackers
        for attack in attackers:
            attacker_id = getattr(attack, 'attacker_id', None)
            if not attacker_id:
                continue

            attacker = self.state.objects.get(attacker_id)
            if not attacker or not is_creature(attacker, self.state):
                continue

            info = CombatCreatureInfo(
                creature_id=attacker_id,
                power=get_power(attacker, self.state),
                toughness=get_toughness(attacker, self.state),
                is_attacking=True,
                is_blocking=False,
                controller=attacker.controller,
                blocked_by_ids=attacker_to_blockers.get(attacker_id, [])
            )

            if attacker.controller == player_id:
                result['our_attackers'].append(info)
            else:
                result['enemy_attackers'].append(info)

        # Process blockers
        for blocker_id, attacking_ids in blocker_to_attackers.items():
            blocker = self.state.objects.get(blocker_id)
            if not blocker or not is_creature(blocker, self.state):
                continue

            info = CombatCreatureInfo(
                creature_id=blocker_id,
                power=get_power(blocker, self.state),
                toughness=get_toughness(blocker, self.state),
                is_attacking=False,
                is_blocking=True,
                controller=blocker.controller,
                blocking_ids=attacking_ids
            )

            if blocker.controller == player_id:
                result['our_blockers'].append(info)
            else:
                result['enemy_blockers'].append(info)

        return result

    def _is_in_combat(self) -> bool:
        """Check if we're in a combat phase."""
        # Check turn manager phase if available
        if hasattr(self.state, 'turn_manager') and self.state.turn_manager:
            phase = getattr(self.state.turn_manager, 'current_phase', None)
            if phase:
                phase_name = str(phase).lower()
                return 'combat' in phase_name
        return False

    def _is_our_turn(self, player_id: str) -> bool:
        """Check if it's our turn."""
        active_player = getattr(self.state, 'active_player', None)
        if active_player:
            return active_player == player_id
        if hasattr(self.state, 'turn_manager') and self.state.turn_manager:
            return getattr(self.state.turn_manager, 'active_player', None) == player_id
        return True

    def _count_available_mana(self, player_id: str) -> int:
        """Count untapped lands for available mana."""
        from src.engine import CardType
        count = 0
        battlefield = self.state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = self.state.objects.get(obj_id)
                if obj and obj.controller == player_id:
                    if CardType.LAND in obj.characteristics.types:
                        if not getattr(obj.state, 'tapped', False):
                            count += 1
        return count

    def _get_instants_in_hand(self, player_id: str) -> list[str]:
        """Get list of instant card IDs in hand."""
        from src.engine import CardType
        instants = []
        hand = self.state.zones.get(f"hand_{player_id}")
        if hand:
            for card_id in hand.objects:
                card = self.state.objects.get(card_id)
                if card and CardType.INSTANT in card.characteristics.types:
                    instants.append(card_id)
        return instants

    def _get_mana_value(self, card) -> int:
        """Get the mana value of a card."""
        if not card or not card.characteristics.mana_cost:
            return 0
        try:
            from src.engine import ManaCost
            cost = ManaCost.parse(card.characteristics.mana_cost)
            return cost.mana_value
        except:
            # Fallback: count symbols
            cost = card.characteristics.mana_cost
            return cost.count('{')

    def _targets_us(self, item, player_id: str) -> bool:
        """Check if a stack item targets us."""
        chosen_targets = getattr(item, 'chosen_targets', None) or getattr(item, 'targets', None)
        if not chosen_targets:
            return False

        for target_list in chosen_targets:
            if isinstance(target_list, (list, tuple)):
                for target in target_list:
                    target_id = getattr(target, 'id', target) if hasattr(target, 'id') else target
                    if target_id == player_id:
                        return True
            else:
                target_id = getattr(target_list, 'id', target_list) if hasattr(target_list, 'id') else target_list
                if target_id == player_id:
                    return True
        return False

    def _estimate_damage(self, text: str) -> int:
        """Estimate damage from spell text."""
        match = re.search(r'deals (\d+) damage', text)
        return int(match.group(1)) if match else 0
