"""
Hyperdraft AI Strategy Base

Abstract base class defining the strategy interface.
All AI strategies inherit from this and implement the required methods.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.engine import GameState, PlayerAction, LegalAction
    from src.engine import AttackDeclaration, BlockDeclaration
    from src.ai.evaluator import BoardEvaluator
    from src.ai.layers import CardLayers


class AIStrategy(ABC):
    """
    Abstract base class for AI strategies.

    Each strategy implements different playstyles:
    - Aggro: Aggressive, prioritizes damage and fast wins
    - Control: Defensive, prioritizes card advantage and answers
    - Midrange: Balanced, adapts to the game state
    """

    def __init__(self):
        """Initialize the strategy with layer storage."""
        self._layers: dict[str, 'CardLayers'] = {}
        self._deck_analysis = None
        self._matchup_analysis = None

    def set_card_layers(self, card_name: str, layers: 'CardLayers'):
        """
        Set the strategy layers for a card.

        Called by AIEngine.prepare_for_match() to populate
        card-specific strategic knowledge.

        Args:
            card_name: The card name
            layers: All three layers for this card
        """
        self._layers[card_name] = layers
        if getattr(layers, "deck_analysis", None):
            self._deck_analysis = layers.deck_analysis
        if getattr(layers, "matchup_analysis", None):
            self._matchup_analysis = layers.matchup_analysis

    def get_layers(self, card_name: str) -> Optional['CardLayers']:
        """
        Get the strategy layers for a card.

        Args:
            card_name: The card name

        Returns:
            CardLayers if available, None otherwise
        """
        return self._layers.get(card_name)

    def clear_layers(self):
        """Clear all stored layers."""
        self._layers.clear()
        self._deck_analysis = None
        self._matchup_analysis = None

    def matchup_role(self) -> str:
        """Return the layer-derived matchup role when available."""
        role = getattr(self._matchup_analysis, "our_role", "") or ""
        return role.strip().lower()

    def deck_archetype(self) -> str:
        """Return the layer-derived deck archetype when available."""
        archetype = getattr(self._deck_analysis, "archetype", "") or ""
        return archetype.strip().lower()

    def layer_target_adjustment(self, card_name: str, target_name: str, target_kinds: list[str]) -> float:
        """Small target-score adjustment from existing layer fields."""
        layers = self.get_layers(card_name)
        if not layers:
            return 0.0

        score = 0.0
        strategy = layers.card_strategy
        for idx, preferred in enumerate(strategy.target_priority or []):
            if preferred in target_kinds:
                score += max(0.0, 2.0 - idx * 0.5)
                break

        matchup = layers.matchup_guide
        if matchup:
            if target_name in (matchup.save_for or []):
                score += 5.0
            if target_name in (matchup.dont_use_on or []):
                score -= 8.0
        return score

    def refine_attack_plan(
        self,
        state: 'GameState',
        player_id: str,
        evaluator: 'BoardEvaluator',
        legal_attackers: list[str],
        planned_attacks: list['AttackDeclaration']
    ) -> list['AttackDeclaration']:
        """Optional layer-aware attack adjustment. Default keeps strategy output."""
        return planned_attacks

    def refine_block_plan(
        self,
        state: 'GameState',
        player_id: str,
        evaluator: 'BoardEvaluator',
        attackers: list['AttackDeclaration'],
        legal_blockers: list[str],
        planned_blocks: list['BlockDeclaration']
    ) -> list['BlockDeclaration']:
        """Optional layer-aware block adjustment. Default keeps strategy output."""
        return planned_blocks

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the strategy name."""
        pass

    @property
    def reactivity(self) -> float:
        """
        How reactive this strategy is (0.0-1.0).

        Higher values mean the AI will:
        - Hold mana for instant-speed responses
        - Counter more spells
        - Use instant removal more aggressively
        - Value combat tricks higher

        Returns:
            Float from 0.0 (fully proactive) to 1.0 (fully reactive)
        """
        return 0.5  # Default: balanced

    @abstractmethod
    def evaluate_action(
        self,
        action: 'LegalAction',
        state: 'GameState',
        evaluator: 'BoardEvaluator',
        player_id: str
    ) -> float:
        """
        Score an action from this strategy's perspective.

        Args:
            action: The legal action to evaluate
            state: Current game state
            evaluator: Board evaluator for state analysis
            player_id: The AI player's ID

        Returns:
            Float score where higher = better action
        """
        pass

    @abstractmethod
    def plan_attacks(
        self,
        state: 'GameState',
        player_id: str,
        evaluator: 'BoardEvaluator',
        legal_attackers: list[str]
    ) -> list['AttackDeclaration']:
        """
        Plan which creatures to attack with.

        Args:
            state: Current game state
            player_id: The AI player's ID
            evaluator: Board evaluator for state analysis
            legal_attackers: List of creature IDs that can attack

        Returns:
            List of AttackDeclaration objects
        """
        pass

    @abstractmethod
    def plan_blocks(
        self,
        state: 'GameState',
        player_id: str,
        evaluator: 'BoardEvaluator',
        attackers: list['AttackDeclaration'],
        legal_blockers: list[str]
    ) -> list['BlockDeclaration']:
        """
        Plan how to block incoming attacks.

        Args:
            state: Current game state
            player_id: The AI player's ID
            evaluator: Board evaluator for state analysis
            attackers: List of attacking creatures
            legal_blockers: List of creature IDs that can block

        Returns:
            List of BlockDeclaration objects
        """
        pass

    def should_counter(
        self,
        spell_on_stack,
        state: 'GameState',
        evaluator: 'BoardEvaluator',
        player_id: str
    ) -> bool:
        """
        Decide whether to counter a spell on the stack.

        Default implementation: counter if it would hurt us significantly.

        Args:
            spell_on_stack: The spell being considered for countering
            state: Current game state
            evaluator: Board evaluator
            player_id: The AI player's ID

        Returns:
            True if the spell should be countered
        """
        # Default: counter threats and board wipes
        return False

    def mulligan_threshold(self, mulligan_count: int) -> float:
        """
        Return the minimum hand quality to keep.

        Lower values = more likely to keep.
        Strategy-specific implementations may vary.

        Args:
            mulligan_count: Number of times already mulliganed

        Returns:
            Float threshold (0.0 to 1.0)
        """
        # Default decreasing threshold
        thresholds = {
            0: 0.6,   # Need a good hand on 7
            1: 0.5,   # Okay hand on 6
            2: 0.3,   # Mediocre on 5
            3: 0.1,   # Keep almost anything on 4
        }
        return thresholds.get(mulligan_count, 0.0)

    def _get_opponent_id(self, player_id: str, state: 'GameState') -> str:
        """Get the opponent's player ID."""
        for pid in state.players:
            if pid != player_id:
                return pid
        return None

    def _clock_role(self, state: 'GameState', player_id: str) -> str:
        """
        Decide whether the AI is currently the beatdown or the control.

        Computes a coarse clock estimate for each side:
            clock = ceil(opp_life / max(my_total_attack_power, 1))
        and returns 'beatdown' if our clock is shorter than opponent's,
        'control' if longer, 'even' otherwise.

        Mike Flores's "Who's the Beatdown?" — the role is dictated by who
        finishes first, not by deck archetype label.
        """
        from src.engine import is_creature, get_power
        opp_id = self._get_opponent_id(player_id, state)
        if not opp_id:
            return 'even'
        me = state.players.get(player_id)
        opp = state.players.get(opp_id)
        if not me or not opp:
            return 'even'

        my_power = 0
        opp_power = 0
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = state.objects.get(obj_id)
                if not obj or not is_creature(obj, state):
                    continue
                p = max(0, get_power(obj, state))
                if obj.controller == player_id:
                    my_power += p
                elif obj.controller == opp_id:
                    opp_power += p

        # Avoid divide-by-zero. Treat zero power as "infinite clock" (huge int).
        my_clock = (opp.life + my_power - 1) // my_power if my_power > 0 else 99
        opp_clock = (me.life + opp_power - 1) // opp_power if opp_power > 0 else 99
        if my_clock < opp_clock:
            return 'beatdown'
        if my_clock > opp_clock:
            return 'control'
        return 'even'

    def _max_opponent_threat_value(self, state: 'GameState', player_id: str) -> int:
        """
        Return power+toughness+ability_premium of the opponent's most
        dangerous untapped creature on the battlefield. Used by removal
        evaluation: 'how bad is the worst threat I might want to answer?'
        """
        from src.engine import is_creature, get_power, get_toughness, has_ability
        opp_id = self._get_opponent_id(player_id, state)
        if not opp_id:
            return 0
        battlefield = state.zones.get('battlefield')
        if not battlefield:
            return 0
        best = 0
        for obj_id in battlefield.objects:
            obj = state.objects.get(obj_id)
            if not obj or obj.controller != opp_id:
                continue
            if not is_creature(obj, state):
                continue
            v = max(0, get_power(obj, state)) + max(0, get_toughness(obj, state))
            if has_ability(obj, 'deathtouch', state):
                v += 3
            if has_ability(obj, 'flying', state) or has_ability(obj, 'unblockable', state):
                v += 2
            if has_ability(obj, 'lifelink', state):
                v += 2
            if has_ability(obj, 'trample', state):
                v += 1
            if v > best:
                best = v
        return best
