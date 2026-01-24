"""
Hyperdraft AI Engine

Main AI controller that integrates strategies, evaluation, and heuristics
to make decisions during gameplay.
"""

import random
from typing import Literal, Optional, TYPE_CHECKING

from .evaluator import BoardEvaluator
from .heuristics import Heuristics
from .strategies import AIStrategy, AggroStrategy, ControlStrategy, MidrangeStrategy

if TYPE_CHECKING:
    from src.engine import GameState, PlayerAction, LegalAction, GameObject
    from src.engine import AttackDeclaration, BlockDeclaration


class AIEngine:
    """
    Main AI engine for making game decisions.

    Supports multiple difficulty levels:
    - easy: Makes suboptimal plays, doesn't evaluate well
    - medium: Reasonable plays, uses strategy
    - hard: Optimal plays, considers future turns
    """

    # Difficulty modifiers
    DIFFICULTY_SETTINGS = {
        'easy': {
            'random_factor': 0.4,      # Add randomness to decisions
            'mistake_chance': 0.25,    # Chance to make a suboptimal play
            'block_skill': 0.5,        # How well it blocks
            'mulligan_strictness': 0.3 # How picky about hands
        },
        'medium': {
            'random_factor': 0.15,
            'mistake_chance': 0.1,
            'block_skill': 0.8,
            'mulligan_strictness': 0.6
        },
        'hard': {
            'random_factor': 0.05,
            'mistake_chance': 0.02,
            'block_skill': 1.0,
            'mulligan_strictness': 0.9
        }
    }

    def __init__(
        self,
        strategy: Optional[AIStrategy] = None,
        difficulty: str = 'medium'
    ):
        """
        Initialize the AI engine.

        Args:
            strategy: The AI strategy to use (default: MidrangeStrategy)
            difficulty: Difficulty level ('easy', 'medium', 'hard')
        """
        self.strategy = strategy or MidrangeStrategy()
        self.difficulty = difficulty

        if difficulty not in self.DIFFICULTY_SETTINGS:
            raise ValueError(f"Unknown difficulty: {difficulty}")

        self.settings = self.DIFFICULTY_SETTINGS[difficulty]

    def get_action(
        self,
        player_id: str,
        state: 'GameState',
        legal_actions: list['LegalAction']
    ) -> 'PlayerAction':
        """
        Choose an action when AI has priority.

        Args:
            player_id: The AI player's ID
            state: Current game state
            legal_actions: List of legal actions available

        Returns:
            The chosen PlayerAction
        """
        from src.engine import PlayerAction, ActionType

        if not legal_actions:
            return PlayerAction(type=ActionType.PASS, player_id=player_id)

        # Create evaluator for this state
        evaluator = BoardEvaluator(state)

        # Score all actions
        scored_actions = []
        for action in legal_actions:
            score = self._score_action(action, state, evaluator, player_id)

            # Add randomness based on difficulty
            score += random.uniform(0, self.settings['random_factor'])

            scored_actions.append((action, score))

        # Sort by score (highest first)
        scored_actions.sort(key=lambda x: x[1], reverse=True)

        # Chance to make a mistake (pick second-best option)
        if len(scored_actions) >= 2 and random.random() < self.settings['mistake_chance']:
            chosen_action = scored_actions[1][0]
        else:
            chosen_action = scored_actions[0][0]

        # Convert LegalAction to PlayerAction
        return self._legal_to_player_action(chosen_action, player_id, state)

    def get_attack_declarations(
        self,
        player_id: str,
        state: 'GameState',
        legal_attackers: list[str]
    ) -> list['AttackDeclaration']:
        """
        Choose which creatures to attack with.

        Args:
            player_id: The AI player's ID
            state: Current game state
            legal_attackers: List of creature IDs that can attack

        Returns:
            List of AttackDeclaration objects
        """
        if not legal_attackers:
            return []

        evaluator = BoardEvaluator(state)

        # Get strategy's attack plan
        attacks = self.strategy.plan_attacks(
            state, player_id, evaluator, legal_attackers
        )

        # Easy difficulty might not attack with everything
        if self.difficulty == 'easy':
            if random.random() < 0.3:
                # Randomly remove some attackers
                if len(attacks) > 1:
                    keep_count = random.randint(1, len(attacks) - 1)
                    attacks = random.sample(attacks, keep_count)

        return attacks

    def get_block_declarations(
        self,
        player_id: str,
        state: 'GameState',
        attackers: list['AttackDeclaration'],
        legal_blockers: list[str]
    ) -> list['BlockDeclaration']:
        """
        Choose how to block.

        Args:
            player_id: The AI player's ID
            state: Current game state
            attackers: List of attacking creature declarations
            legal_blockers: List of creature IDs that can block

        Returns:
            List of BlockDeclaration objects
        """
        if not attackers or not legal_blockers:
            return []

        evaluator = BoardEvaluator(state)

        # Get strategy's block plan
        blocks = self.strategy.plan_blocks(
            state, player_id, evaluator, attackers, legal_blockers
        )

        # Apply blocking skill based on difficulty
        if self.difficulty == 'easy':
            # Easy might miss blocks or make suboptimal choices
            final_blocks = []
            for block in blocks:
                if random.random() < self.settings['block_skill']:
                    final_blocks.append(block)
            return final_blocks

        return blocks

    def get_mulligan_decision(
        self,
        hand: list['GameObject'],
        mulligan_count: int
    ) -> Literal['keep', 'mulligan']:
        """
        Decide whether to mulligan.

        Args:
            hand: The current hand
            mulligan_count: How many times already mulliganed

        Returns:
            'keep' or 'mulligan'
        """
        # Always keep at 4 cards or fewer
        if len(hand) <= 4:
            return 'keep'

        # Use heuristics to evaluate hand
        is_good = Heuristics.is_good_opening_hand(hand, mulligan_count)

        # Adjust based on difficulty
        strictness = self.settings['mulligan_strictness']
        threshold = self.strategy.mulligan_threshold(mulligan_count)

        # Easy AI keeps more hands
        adjusted_threshold = threshold * strictness

        if is_good:
            return 'keep'
        elif random.random() > adjusted_threshold:
            return 'keep'
        else:
            return 'mulligan'

    def choose_targets(
        self,
        ability,
        legal_targets: list[str],
        state: 'GameState'
    ) -> list[str]:
        """
        Choose targets for a spell or ability.

        Args:
            ability: The ability requiring targets
            legal_targets: List of legal target IDs
            state: Current game state

        Returns:
            List of chosen target IDs
        """
        if not legal_targets:
            return []

        # Determine how many targets needed
        # Default to 1 if not specified
        num_targets = 1
        if hasattr(ability, 'num_targets'):
            num_targets = ability.num_targets

        # Use heuristics to choose best targets
        chosen = []
        remaining_targets = list(legal_targets)

        for _ in range(min(num_targets, len(remaining_targets))):
            # Determine if we prefer creatures or players
            prefer_creatures = self._should_target_creature(ability, state)

            best_target = Heuristics.get_best_target(
                remaining_targets,
                state,
                prefer_creatures=prefer_creatures
            )

            if best_target:
                chosen.append(best_target)
                remaining_targets.remove(best_target)

        # Easy difficulty might choose suboptimally
        if self.difficulty == 'easy' and len(legal_targets) > 1:
            if random.random() < 0.3:
                return [random.choice(legal_targets)]

        return chosen

    def _score_action(
        self,
        action: 'LegalAction',
        state: 'GameState',
        evaluator: BoardEvaluator,
        player_id: str
    ) -> float:
        """Score an action using the current strategy."""
        return self.strategy.evaluate_action(action, state, evaluator, player_id)

    def _legal_to_player_action(
        self,
        legal_action: 'LegalAction',
        player_id: str,
        state: 'GameState'
    ) -> 'PlayerAction':
        """Convert a LegalAction to a PlayerAction."""
        from src.engine import PlayerAction, ActionType

        action = PlayerAction(
            type=legal_action.type,
            player_id=player_id,
            card_id=legal_action.card_id,
            ability_id=legal_action.ability_id,
            source_id=legal_action.source_id
        )

        # If action requires targets, choose them
        if legal_action.requires_targets and legal_action.card_id:
            card = state.objects.get(legal_action.card_id)
            if card and card.card_def:
                # Get legal targets for this card
                # This would need targeting system integration
                pass

        return action

    def _should_target_creature(self, ability, state: 'GameState') -> bool:
        """Determine if we should prefer targeting creatures over players."""
        # Check if ability text suggests creature targeting
        if hasattr(ability, 'text'):
            text = ability.text.lower()
            if 'creature' in text:
                return True
            if 'player' in text and 'creature' not in text:
                return False

        # Default: prefer creatures for removal, players for damage
        if hasattr(ability, 'effect_type'):
            if ability.effect_type in ['destroy', 'exile', 'bounce']:
                return True
            if ability.effect_type == 'damage':
                return False

        return True

    # Convenience factory methods

    @classmethod
    def create_aggro_bot(cls, difficulty: str = 'medium') -> 'AIEngine':
        """Create an AI with aggro strategy."""
        return cls(strategy=AggroStrategy(), difficulty=difficulty)

    @classmethod
    def create_control_bot(cls, difficulty: str = 'medium') -> 'AIEngine':
        """Create an AI with control strategy."""
        return cls(strategy=ControlStrategy(), difficulty=difficulty)

    @classmethod
    def create_midrange_bot(cls, difficulty: str = 'medium') -> 'AIEngine':
        """Create an AI with midrange strategy."""
        return cls(strategy=MidrangeStrategy(), difficulty=difficulty)

    @classmethod
    def create_random_strategy_bot(cls, difficulty: str = 'medium') -> 'AIEngine':
        """Create an AI with a randomly chosen strategy."""
        strategies = [AggroStrategy(), ControlStrategy(), MidrangeStrategy()]
        return cls(strategy=random.choice(strategies), difficulty=difficulty)


def create_ai_action_handler(ai_engine: AIEngine):
    """
    Create an action handler function compatible with the priority system.

    Usage:
        ai = AIEngine(difficulty='hard')
        game.set_ai_action_handler(create_ai_action_handler(ai))
    """
    def handler(player_id: str, state: 'GameState', legal_actions: list) -> 'PlayerAction':
        return ai_engine.get_action(player_id, state, legal_actions)
    return handler


def create_ai_attack_handler(ai_engine: AIEngine):
    """
    Create an attack handler function compatible with the combat manager.

    Usage:
        ai = AIEngine(difficulty='hard')
        game.set_attack_handler(create_ai_attack_handler(ai))
    """
    def handler(player_id: str, legal_attackers: list[str]):
        # We need the game state, but the handler signature doesn't include it
        # This is a limitation - in practice, you'd need to get state from game
        # For now, return all attackers (basic behavior)
        from src.engine import AttackDeclaration
        return [
            AttackDeclaration(
                attacker_id=attacker_id,
                defending_player_id='',  # Would need opponent ID
                is_attacking_planeswalker=False
            )
            for attacker_id in legal_attackers
        ]
    return handler


def create_ai_block_handler(ai_engine: AIEngine):
    """
    Create a block handler function compatible with the combat manager.

    Usage:
        ai = AIEngine(difficulty='hard')
        game.set_block_handler(create_ai_block_handler(ai))
    """
    def handler(
        player_id: str,
        attackers: list['AttackDeclaration'],
        legal_blockers: list[str]
    ):
        # Similar limitation as attack handler
        return []
    return handler
