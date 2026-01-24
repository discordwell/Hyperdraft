"""
Hyperdraft AI Strategy Base

Abstract base class defining the strategy interface.
All AI strategies inherit from this and implement the required methods.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine import GameState, PlayerAction, LegalAction
    from src.engine import AttackDeclaration, BlockDeclaration
    from src.ai.evaluator import BoardEvaluator


class AIStrategy(ABC):
    """
    Abstract base class for AI strategies.

    Each strategy implements different playstyles:
    - Aggro: Aggressive, prioritizes damage and fast wins
    - Control: Defensive, prioritizes card advantage and answers
    - Midrange: Balanced, adapts to the game state
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the strategy name."""
        pass

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
