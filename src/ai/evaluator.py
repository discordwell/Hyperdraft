"""
Hyperdraft Board Evaluator

Evaluates game state and returns scores indicating who is winning.
Score range: -1.0 (AI losing badly) to 1.0 (AI winning badly)
"""

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import GameState, GameObject, Player


@dataclass
class BoardAnalysis:
    """Detailed breakdown of board state analysis."""
    life_score: float = 0.0          # Life total comparison
    board_score: float = 0.0         # Creature/permanent presence
    card_advantage: float = 0.0      # Hand size comparison
    mana_advantage: float = 0.0      # Available mana comparison
    threat_score: float = 0.0        # Assessment of immediate threats
    blocker_score: float = 0.0       # How well each side can absorb attacks
    evasion_pressure: float = 0.0    # Evasive pressure that blockers cannot cover
    crack_back_risk: float = 0.0     # Risk after committing attackers
    permanent_score: float = 0.0     # Noncreature permanent value
    role: str = "even"               # Beatdown/control/even role estimate

    total_score: float = 0.0         # Combined weighted score


class BoardEvaluator:
    """
    Evaluates board states for AI decision making.

    Returns scores from -1.0 (losing) to 1.0 (winning) from the
    perspective of the evaluated player.
    """

    # Weight factors for different aspects of the game
    LIFE_WEIGHT = 0.25
    BOARD_WEIGHT = 0.35
    CARD_ADVANTAGE_WEIGHT = 0.20
    MANA_WEIGHT = 0.10
    THREAT_WEIGHT = 0.10
    BLOCKER_WEIGHT = 0.08
    EVASION_WEIGHT = 0.08
    CRACK_BACK_WEIGHT = 0.08
    PERMANENT_WEIGHT = 0.06

    def __init__(self, state: 'GameState'):
        self.state = state

    def evaluate(self, player_id: str) -> float:
        """
        Evaluate the board state from a player's perspective.

        Args:
            player_id: The player to evaluate for

        Returns:
            Score from -1.0 (losing) to 1.0 (winning)
        """
        analysis = self.analyze(player_id)
        return analysis.total_score

    def analyze(self, player_id: str) -> BoardAnalysis:
        """
        Perform detailed board analysis.

        Args:
            player_id: The player to analyze for

        Returns:
            BoardAnalysis with breakdown of all factors
        """
        opponent_id = self._get_opponent_id(player_id)
        if not opponent_id:
            return BoardAnalysis(total_score=0.0)

        player = self.state.players.get(player_id)
        opponent = self.state.players.get(opponent_id)

        if not player or not opponent:
            return BoardAnalysis(total_score=0.0)

        analysis = BoardAnalysis()

        # Calculate each component
        analysis.life_score = self._evaluate_life(player, opponent)
        analysis.board_score = self._evaluate_board(player_id, opponent_id)
        analysis.card_advantage = self._evaluate_cards(player_id, opponent_id)
        analysis.mana_advantage = self._evaluate_mana(player_id, opponent_id)
        analysis.threat_score = self._evaluate_threats(player_id, opponent_id)
        analysis.blocker_score = self._evaluate_blockers(player_id, opponent_id)
        analysis.evasion_pressure = self._evaluate_evasion_pressure(player_id, opponent_id)
        analysis.crack_back_risk = self._evaluate_crack_back_risk(player_id, opponent_id)
        analysis.permanent_score = self._evaluate_noncreature_permanents(player_id, opponent_id)
        analysis.role = self.detect_role(player_id)

        # Calculate weighted total
        analysis.total_score = (
            analysis.life_score * self.LIFE_WEIGHT +
            analysis.board_score * self.BOARD_WEIGHT +
            analysis.card_advantage * self.CARD_ADVANTAGE_WEIGHT +
            analysis.mana_advantage * self.MANA_WEIGHT +
            analysis.threat_score * self.THREAT_WEIGHT +
            analysis.blocker_score * self.BLOCKER_WEIGHT +
            analysis.evasion_pressure * self.EVASION_WEIGHT -
            analysis.crack_back_risk * self.CRACK_BACK_WEIGHT +
            analysis.permanent_score * self.PERMANENT_WEIGHT
        )

        # Clamp to [-1, 1]
        analysis.total_score = max(-1.0, min(1.0, analysis.total_score))

        return analysis

    def _evaluate_life(self, player: 'Player', opponent: 'Player') -> float:
        """
        Evaluate life totals.

        Returns score from -1 to 1 based on relative life totals.
        """
        my_life = player.life
        opp_life = opponent.life

        # Handle edge cases
        if my_life <= 0:
            return -1.0
        if opp_life <= 0:
            return 1.0

        # Compare life totals
        total_life = my_life + opp_life
        if total_life == 0:
            return 0.0

        # Normalize to [-1, 1]
        life_diff = my_life - opp_life
        max_diff = max(my_life, opp_life)

        if max_diff == 0:
            return 0.0

        score = life_diff / (max_diff * 2)

        # Add urgency bonus/penalty for low life
        if my_life <= 5:
            score -= 0.3
        elif my_life <= 10:
            score -= 0.1

        if opp_life <= 5:
            score += 0.3
        elif opp_life <= 10:
            score += 0.1

        return max(-1.0, min(1.0, score))

    def _evaluate_board(self, player_id: str, opponent_id: str) -> float:
        """
        Evaluate board presence (creatures, permanents).

        Considers:
        - Total power/toughness on board
        - Number of creatures
        - Quality of creatures (abilities)
        """
        from src.engine import get_power, get_toughness, is_creature, has_ability, ZoneType

        my_creatures = []
        opp_creatures = []

        battlefield = self.state.zones.get('battlefield')
        if not battlefield:
            return 0.0

        for obj_id in battlefield.objects:
            obj = self.state.objects.get(obj_id)
            if not obj or not is_creature(obj, self.state):
                continue

            if obj.controller == player_id:
                my_creatures.append(obj)
            elif obj.controller == opponent_id:
                opp_creatures.append(obj)

        # Calculate total board value
        my_value = sum(self._creature_value(c) for c in my_creatures)
        opp_value = sum(self._creature_value(c) for c in opp_creatures)

        # Normalize
        total_value = my_value + opp_value
        if total_value == 0:
            return 0.0

        diff = my_value - opp_value
        score = diff / (total_value + 1)

        # Creature count matters too
        count_diff = len(my_creatures) - len(opp_creatures)
        score += count_diff * 0.1

        return max(-1.0, min(1.0, score))

    def _battlefield_objects(self):
        battlefield = self.state.zones.get('battlefield')
        if not battlefield:
            return []
        return [self.state.objects[obj_id] for obj_id in battlefield.objects if obj_id in self.state.objects]

    def _creatures_for(self, player_id: str) -> list['GameObject']:
        from src.engine import is_creature
        return [
            obj for obj in self._battlefield_objects()
            if obj.controller == player_id and is_creature(obj, self.state)
        ]

    def _noncreatures_for(self, player_id: str) -> list['GameObject']:
        from src.engine import CardType, is_creature
        return [
            obj for obj in self._battlefield_objects()
            if obj.controller == player_id
            and not is_creature(obj, self.state)
            and CardType.LAND not in obj.characteristics.types
        ]

    def _has_ability(self, obj: 'GameObject', *names: str) -> bool:
        from src.engine import has_ability
        normalized = {name.lower().replace("_", " ") for name in names}
        for name in normalized:
            if has_ability(obj, name, self.state):
                return True
            if has_ability(obj, name.replace(" ", "_"), self.state):
                return True
        return False

    def _can_attack_now(self, obj: 'GameObject') -> bool:
        if obj.state.tapped:
            return False
        if self._has_ability(obj, "defender"):
            return False
        if getattr(obj.state, "summoning_sickness", False) and not self._has_ability(obj, "haste"):
            return False
        return True

    def _can_block(self, obj: 'GameObject') -> bool:
        if obj.state.tapped:
            return False
        if getattr(obj.state, "suspected", False):
            return False
        return True

    def _can_block_attacker(self, blocker: 'GameObject', attacker: 'GameObject') -> bool:
        if not self._can_block(blocker):
            return False
        if self._has_ability(attacker, "unblockable"):
            return False
        if self._has_ability(attacker, "flying"):
            return self._has_ability(blocker, "flying", "reach")
        if self._has_ability(attacker, "menace"):
            # Pairing is handled elsewhere; a single blocker cannot block menace.
            return False
        return True

    def _attacker_damage_through(self, attacker: 'GameObject', blockers: list['GameObject']) -> int:
        from src.engine import get_power
        power = max(0, get_power(attacker, self.state))
        possible_blockers = [b for b in blockers if self._can_block_attacker(b, attacker)]
        if not possible_blockers:
            return power
        if self._has_ability(attacker, "trample"):
            from src.engine import get_toughness
            best_absorb = max(max(0, get_toughness(b, self.state)) for b in possible_blockers)
            return max(0, power - best_absorb)
        return 0

    def expected_unblocked_damage(self, attacker_ids: list[str], defender_id: str) -> int:
        """Estimate damage that gets through after available blockers."""
        attackers = [self.state.objects[aid] for aid in attacker_ids if aid in self.state.objects]
        blockers = self._creatures_for(defender_id)
        return sum(self._attacker_damage_through(a, blockers) for a in attackers if self._can_attack_now(a))

    def attack_pressure(self, player_id: str) -> int:
        """Attack-ready power after summoning sickness/defender filters."""
        from src.engine import get_power
        return sum(
            max(0, get_power(c, self.state))
            for c in self._creatures_for(player_id)
            if self._can_attack_now(c)
        )

    def evasive_pressure(self, player_id: str, opponent_id: Optional[str] = None) -> int:
        """Attack-ready damage that is hard or impossible to block."""
        opponent_id = opponent_id or self._get_opponent_id(player_id)
        if not opponent_id:
            return 0
        attackers = [c.id for c in self._creatures_for(player_id)]
        return self.expected_unblocked_damage(attackers, opponent_id)

    def _evaluate_blockers(self, player_id: str, opponent_id: str) -> float:
        from src.engine import get_power, get_toughness

        def coverage(defender_id: str, attacker_id: str) -> float:
            blockers = self._creatures_for(defender_id)
            attackers = [c for c in self._creatures_for(attacker_id) if self._can_attack_now(c)]
            if not attackers:
                return 0.0
            covered = 0
            for attacker in attackers:
                for blocker in blockers:
                    if not self._can_block_attacker(blocker, attacker):
                        continue
                    b_power = get_power(blocker, self.state)
                    a_toughness = get_toughness(attacker, self.state)
                    if self._has_ability(blocker, "deathtouch") or b_power >= a_toughness:
                        covered += 1
                        break
            return covered / max(1, len(attackers))

        score = coverage(player_id, opponent_id) - coverage(opponent_id, player_id)
        return max(-1.0, min(1.0, score))

    def _evaluate_evasion_pressure(self, player_id: str, opponent_id: str) -> float:
        player = self.state.players.get(player_id)
        opponent = self.state.players.get(opponent_id)
        if not player or not opponent:
            return 0.0

        my_evasive = self.evasive_pressure(player_id, opponent_id)
        opp_evasive = self.evasive_pressure(opponent_id, player_id)
        my_ratio = my_evasive / max(1, opponent.life)
        opp_ratio = opp_evasive / max(1, player.life)
        return max(-1.0, min(1.0, my_ratio - opp_ratio))

    def _evaluate_crack_back_risk(self, player_id: str, opponent_id: str) -> float:
        player = self.state.players.get(player_id)
        opponent = self.state.players.get(opponent_id)
        if not player or not opponent:
            return 0.0

        opp_pressure = self.attack_pressure(opponent_id)
        my_pressure = self.attack_pressure(player_id)
        if opp_pressure >= player.life:
            return 1.0
        if my_pressure >= opponent.life:
            return -0.5
        return max(-1.0, min(1.0, (opp_pressure / max(1, player.life)) - 0.35))

    def _evaluate_noncreature_permanents(self, player_id: str, opponent_id: str) -> float:
        my_value = sum(self._permanent_value(p) for p in self._noncreatures_for(player_id))
        opp_value = sum(self._permanent_value(p) for p in self._noncreatures_for(opponent_id))
        total = my_value + opp_value
        if total == 0:
            return 0.0
        return max(-1.0, min(1.0, (my_value - opp_value) / (total + 1)))

    def _permanent_value(self, obj: 'GameObject') -> float:
        from src.engine import CardType

        value = 0.5
        types = obj.characteristics.types or set()
        if CardType.PLANESWALKER in types:
            value += 4.0
        elif CardType.ARTIFACT in types or CardType.ENCHANTMENT in types:
            value += 1.0

        text = (obj.card_def.text or "").lower() if obj.card_def else ""
        if "draw" in text:
            value += 1.0
        if "create" in text and "token" in text:
            value += 0.8
        if "destroy" in text or "exile" in text:
            value += 0.8
        if "whenever" in text or "at the beginning" in text:
            value += 0.6
        return value

    def detect_role(self, player_id: str) -> str:
        opponent_id = self._get_opponent_id(player_id)
        if not opponent_id:
            return "even"
        player = self.state.players.get(player_id)
        opponent = self.state.players.get(opponent_id)
        if not player or not opponent:
            return "even"
        my_pressure = self.attack_pressure(player_id)
        opp_pressure = self.attack_pressure(opponent_id)
        my_clock = (opponent.life + my_pressure - 1) // my_pressure if my_pressure > 0 else 99
        opp_clock = (player.life + opp_pressure - 1) // opp_pressure if opp_pressure > 0 else 99
        if my_clock < opp_clock:
            return "beatdown"
        if my_clock > opp_clock:
            return "control"
        return "even"

    def _evaluate_cards(self, player_id: str, opponent_id: str) -> float:
        """
        Evaluate card advantage (hand size).
        """
        my_hand = self._get_hand_size(player_id)
        opp_hand = self._get_hand_size(opponent_id)

        # Card advantage is important but not overwhelming
        diff = my_hand - opp_hand
        score = diff * 0.15  # Each card is worth about 0.15

        # Having cards is better than not having cards
        if my_hand == 0 and opp_hand > 0:
            score -= 0.3
        elif opp_hand == 0 and my_hand > 0:
            score += 0.3

        return max(-1.0, min(1.0, score))

    def _evaluate_mana(self, player_id: str, opponent_id: str) -> float:
        """
        Evaluate mana advantage (lands/mana sources).
        """
        from src.engine import CardType

        my_lands = 0
        opp_lands = 0

        battlefield = self.state.zones.get('battlefield')
        if not battlefield:
            return 0.0

        for obj_id in battlefield.objects:
            obj = self.state.objects.get(obj_id)
            if not obj:
                continue

            if CardType.LAND in obj.characteristics.types:
                if obj.controller == player_id:
                    my_lands += 1
                elif obj.controller == opponent_id:
                    opp_lands += 1

        # Mana difference matters less as game goes on
        diff = my_lands - opp_lands
        total_lands = my_lands + opp_lands

        if total_lands == 0:
            return 0.0

        # Early game: mana matters more
        # Late game: less so
        multiplier = 1.0 if total_lands < 8 else 0.5

        score = (diff / (total_lands + 1)) * multiplier

        return max(-1.0, min(1.0, score))

    def _evaluate_threats(self, player_id: str, opponent_id: str) -> float:
        """
        Evaluate immediate threats on the board.

        Looks for:
        - Creatures that can attack for lethal
        - Dangerous abilities about to trigger
        - Board wipes in hand (if known)
        """
        from src.engine import get_power, is_creature

        player = self.state.players.get(player_id)
        opponent = self.state.players.get(opponent_id)

        if not player or not opponent:
            return 0.0

        # Calculate potential damage from untapped attackers
        my_damage_potential = 0
        opp_damage_potential = 0

        battlefield = self.state.zones.get('battlefield')
        if not battlefield:
            return 0.0

        for obj_id in battlefield.objects:
            obj = self.state.objects.get(obj_id)
            if not obj or not is_creature(obj, self.state):
                continue

            # Only creatures that can attack now count as immediate damage.
            if not self._can_attack_now(obj):
                continue

            power = get_power(obj, self.state)

            if obj.controller == player_id:
                my_damage_potential += power
            elif obj.controller == opponent_id:
                opp_damage_potential += power

        score = 0.0

        # Threatening lethal is very valuable
        if my_damage_potential >= opponent.life:
            score += 0.5
        elif my_damage_potential >= opponent.life * 0.5:
            score += 0.2

        # Being threatened is very bad
        if opp_damage_potential >= player.life:
            score -= 0.5
        elif opp_damage_potential >= player.life * 0.5:
            score -= 0.2

        return max(-1.0, min(1.0, score))

    def _creature_value(self, creature: 'GameObject') -> float:
        """Calculate the value of a creature on the board."""
        from src.engine import get_power, get_toughness, has_ability

        power = get_power(creature, self.state)
        toughness = get_toughness(creature, self.state)

        # Base value is power + toughness
        value = power + toughness

        # Ability bonuses
        ability_bonus = 0
        if has_ability(creature, 'flying', self.state):
            ability_bonus += 1.5
        if has_ability(creature, 'trample', self.state):
            ability_bonus += 0.5
        if has_ability(creature, 'deathtouch', self.state):
            ability_bonus += 2.0
        if has_ability(creature, 'lifelink', self.state):
            ability_bonus += 1.0
        if has_ability(creature, 'vigilance', self.state):
            ability_bonus += 0.5
        if has_ability(creature, 'first_strike', self.state):
            ability_bonus += 1.0
        if has_ability(creature, 'double_strike', self.state):
            ability_bonus += power
        if has_ability(creature, 'hexproof', self.state):
            ability_bonus += 1.5
        if has_ability(creature, 'indestructible', self.state):
            ability_bonus += 3.0
        if has_ability(creature, 'haste', self.state):
            ability_bonus += 0.5

        # Tapped creatures are worth less
        if creature.state.tapped:
            value *= 0.8

        return value + ability_bonus

    def target_threat_value(
        self,
        target_id: str,
        player_id: str,
        source_card=None,
        layers=None,
        is_removal: bool = True
    ) -> float:
        """Score a target with board value plus optional layer preferences."""
        from src.engine import CardType

        obj = self.state.objects.get(target_id)
        if not obj:
            if target_id in self.state.players:
                target_player = self.state.players[target_id]
                if target_id == player_id:
                    return -100.0
                return 100.0 - float(target_player.life)
            return 0.0

        score = 0.0
        if CardType.CREATURE in obj.characteristics.types:
            score += self._creature_value(obj)
            if self._can_attack_now(obj):
                score += 0.5
            if self._has_ability(obj, "flying", "unblockable", "menace"):
                score += 1.0
        elif CardType.PLANESWALKER in obj.characteristics.types:
            score += 10.0
        else:
            score += self._permanent_value(obj)

        text = (obj.card_def.text or "").lower() if obj.card_def else ""
        if "draw" in text:
            score += 2.0
        if "whenever" in text or "at the beginning" in text:
            score += 1.0

        if layers:
            strategy = layers.card_strategy
            matchup = layers.matchup_guide
            target_types = []
            if CardType.CREATURE in obj.characteristics.types:
                target_types.append("creature")
            if CardType.PLANESWALKER in obj.characteristics.types:
                target_types.append("planeswalker")
            if not target_types:
                target_types.append("permanent")

            for idx, target_type in enumerate(strategy.target_priority or []):
                if target_type in target_types:
                    score += max(0.0, 2.0 - idx * 0.5)
                    break

            if matchup:
                if obj.name in (matchup.save_for or []):
                    score += 5.0
                if obj.name in (matchup.dont_use_on or []):
                    score -= 8.0
                score *= max(0.1, matchup.priority_modifier)

        if not is_removal and obj.controller != player_id:
            score *= -1
        return score

    def _get_hand_size(self, player_id: str) -> int:
        """Get the number of cards in a player's hand."""
        hand_key = f"hand_{player_id}"
        hand = self.state.zones.get(hand_key)
        return len(hand.objects) if hand else 0

    def _get_opponent_id(self, player_id: str) -> Optional[str]:
        """Get the opponent's player ID."""
        for pid in self.state.players:
            if pid != player_id:
                return pid
        return None

    # Utility methods for external use

    def get_lethal_attackers(self, player_id: str) -> Optional[list[str]]:
        """
        Find a set of attackers that would be lethal.

        Returns list of creature IDs if lethal exists, None otherwise.
        """
        from src.engine import get_power, is_creature

        opponent_id = self._get_opponent_id(player_id)
        if not opponent_id:
            return None

        opponent = self.state.players.get(opponent_id)
        if not opponent:
            return None

        # Get all untapped creatures we control
        attackers = []
        battlefield = self.state.zones.get('battlefield')
        if not battlefield:
            return None

        total_power = 0
        for obj_id in battlefield.objects:
            obj = self.state.objects.get(obj_id)
            if not obj or not is_creature(obj, self.state):
                continue
            if obj.controller != player_id:
                continue
            if not self._can_attack_now(obj):
                continue

            power = get_power(obj, self.state)
            attackers.append((obj_id, power))
            total_power += power

        if total_power >= opponent.life:
            return [a[0] for a in attackers]

        return None

    def count_blockers(self, player_id: str) -> int:
        """Count untapped creatures that can block."""
        from src.engine import is_creature

        count = 0
        battlefield = self.state.zones.get('battlefield')
        if not battlefield:
            return 0

        for obj_id in battlefield.objects:
            obj = self.state.objects.get(obj_id)
            if not obj or not is_creature(obj, self.state):
                continue
            if obj.controller != player_id:
                continue
            if not self._can_block(obj):
                continue

            count += 1

        return count
