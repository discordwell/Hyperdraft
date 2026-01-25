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
        """Score an action with reactive awareness."""
        from src.engine import ActionType, CardType
        from src.ai.reactive import ReactiveEvaluator

        # Get base score from strategy
        base_score = self.strategy.evaluate_action(action, state, evaluator, player_id)

        # Build reactive context
        reactive_eval = ReactiveEvaluator(state)
        stack_items = []
        if hasattr(state, 'stack') and state.stack:
            stack_items = state.stack.get_items() if hasattr(state.stack, 'get_items') else list(state.stack.items)

        context = reactive_eval.build_context(player_id, stack_items)

        # Apply reactive modifiers for instant-speed plays
        if action.type == ActionType.CAST_SPELL and action.card_id:
            card = state.objects.get(action.card_id)
            if card:
                # Check for X spells and adjust score based on potential X value
                x_bonus = self._get_x_spell_bonus(card, context.available_mana, state, player_id)
                if x_bonus > 0:
                    base_score += x_bonus

                if CardType.INSTANT in card.characteristics.types:
                    # Classify and score the instant
                    if self._is_counterspell(card):
                        base_score += reactive_eval.get_counterspell_bonus(
                            context, self.strategy.reactivity
                        )
                    elif self._is_instant_removal(card):
                        base_score += reactive_eval.get_removal_bonus(
                            context, self.strategy.reactivity
                        )
                    elif self._is_combat_trick(card):
                        # Pass the card so we can evaluate if the trick changes outcomes
                        base_score += reactive_eval.get_combat_trick_bonus(
                            context, self.strategy.reactivity, trick_card=card
                        )
                else:
                    # Sorcery-speed: consider hold-mana penalty
                    penalty = reactive_eval.get_hold_mana_penalty(
                        card, context, self.strategy.reactivity
                    )
                    base_score -= penalty

        # Pass gets bonus if holding for reaction
        if action.type == ActionType.PASS:
            if context.instants_in_hand and context.available_mana >= 2:
                if context.stack_threats or not context.is_our_turn:
                    base_score += 0.3 * self.strategy.reactivity

        # Adventure casting - evaluate the adventure spell portion
        if action.type == ActionType.CAST_ADVENTURE and action.card_id:
            card = state.objects.get(action.card_id)
            if card:
                base_score += self._get_adventure_bonus(card, context, state, player_id)

        # Split card casting - evaluate the chosen half
        if action.type == ActionType.CAST_SPLIT_LEFT and action.card_id:
            card = state.objects.get(action.card_id)
            if card:
                base_score += self._get_split_bonus(card, 'left', context, state, player_id)

        if action.type == ActionType.CAST_SPLIT_RIGHT and action.card_id:
            card = state.objects.get(action.card_id)
            if card:
                base_score += self._get_split_bonus(card, 'right', context, state, player_id)

        return base_score

    def _is_counterspell(self, card) -> bool:
        """Check if card is a counterspell."""
        text = (card.card_def.text or '').lower() if card.card_def else ''
        return 'counter target' in text and 'spell' in text

    def _is_instant_removal(self, card) -> bool:
        """Check if card is instant-speed removal."""
        from src.engine import CardType
        if CardType.INSTANT not in card.characteristics.types:
            return False
        text = (card.card_def.text or '').lower() if card.card_def else ''
        return 'destroy' in text or 'exile' in text or 'damage' in text

    def _is_combat_trick(self, card) -> bool:
        """Check if card is a combat trick."""
        from src.engine import CardType
        if CardType.INSTANT not in card.characteristics.types:
            return False
        text = (card.card_def.text or '').lower() if card.card_def else ''
        return '+' in text and '/' in text

    def _get_x_spell_bonus(self, card, available_mana: int, state: 'GameState', player_id: str) -> float:
        """
        Calculate bonus for X spells based on how much mana we can spend.

        X spells are more valuable when we have more mana to spend on X.
        Returns 0 if not an X spell.
        """
        from src.engine import ManaCost

        if not card.characteristics.mana_cost:
            return 0.0

        cost = ManaCost.parse(card.characteristics.mana_cost)
        if cost.x_count == 0:
            return 0.0  # Not an X spell

        # Calculate the base cost (non-X part)
        base_cost = cost.mana_value  # This includes colored and generic

        # Calculate max X we can afford
        max_x = max(0, available_mana - base_cost)

        if max_x <= 0:
            return -1.0  # Can't cast meaningfully, penalize

        # Score based on X value and spell type
        text = (card.card_def.text or '').lower() if card.card_def else ''

        bonus = 0.0

        # Damage spells: X damage is very valuable
        if 'damage' in text:
            # Check if opponent is low enough for lethal
            opponent_id = self._get_opponent_id(player_id, state)
            opponent = state.players.get(opponent_id) if opponent_id else None
            if opponent and max_x >= opponent.life:
                bonus += 3.0  # Lethal X spell!
            else:
                bonus += max_x * 0.3  # Scale with X

        # Card draw: X cards is good
        elif 'draw' in text:
            bonus += max_x * 0.4

        # Generic X spell
        else:
            bonus += max_x * 0.2

        return bonus

    def _get_opponent_id(self, player_id: str, state: 'GameState') -> str:
        """Get the opponent's player ID."""
        for pid in state.players:
            if pid != player_id:
                return pid
        return None

    def _has_adventure(self, card) -> bool:
        """Check if card has an adventure face."""
        if not card or not card.card_def:
            return False
        # Check for explicit adventure face
        if hasattr(card.card_def, 'adventure') and card.card_def.adventure:
            return True
        # Check for adventure pattern in text (// Adventure)
        if card.card_def.text and '// adventure' in card.card_def.text.lower():
            return True
        return False

    def _has_split(self, card) -> bool:
        """Check if card is a split card."""
        if not card or not card.card_def:
            return False
        # Check for explicit split faces
        if hasattr(card.card_def, 'split_left') and card.card_def.split_left:
            return True
        if hasattr(card.card_def, 'split_right') and card.card_def.split_right:
            return True
        # Check for split pattern in mana cost
        if card.characteristics.mana_cost and '//' in card.characteristics.mana_cost:
            return True
        return False

    def _get_adventure_bonus(self, card, context, state: 'GameState', player_id: str) -> float:
        """
        Calculate bonus for casting adventure side of a card.

        Adventure spells are valuable because:
        1. They give you a 2-for-1 (spell now, creature later)
        2. The adventure often has useful instant/sorcery effects
        """
        if not self._has_adventure(card):
            return 0.0

        bonus = 0.5  # Base bonus for flexibility

        # Parse adventure text if available
        adventure_text = ""
        if hasattr(card.card_def, 'adventure') and card.card_def.adventure:
            adventure_text = card.card_def.adventure.text.lower()
        elif card.card_def.text:
            # Try to extract adventure portion after "// Adventure"
            parts = card.card_def.text.lower().split('// adventure')
            if len(parts) > 1:
                adventure_text = parts[1]

        # Evaluate adventure effect
        if 'damage' in adventure_text:
            bonus += 0.8  # Removal is good
        elif 'destroy' in adventure_text or 'exile' in adventure_text:
            bonus += 1.0  # Hard removal is great
        elif 'draw' in adventure_text:
            bonus += 0.7  # Card advantage
        elif 'counter' in adventure_text:
            bonus += 0.9 * self.strategy.reactivity  # Counterspells
        elif 'create' in adventure_text and 'token' in adventure_text:
            bonus += 0.6  # Token generation

        return bonus

    def _get_split_bonus(self, card, mode: str, context, state: 'GameState', player_id: str) -> float:
        """
        Calculate bonus for casting a specific side of a split card.

        Args:
            mode: 'left' or 'right'
        """
        if not self._has_split(card):
            return 0.0

        bonus = 0.3  # Base bonus for flexibility

        # Get the appropriate face text
        face_text = ""
        if mode == 'left' and hasattr(card.card_def, 'split_left') and card.card_def.split_left:
            face_text = card.card_def.split_left.text.lower()
        elif mode == 'right' and hasattr(card.card_def, 'split_right') and card.card_def.split_right:
            face_text = card.card_def.split_right.text.lower()
        elif card.card_def.text:
            # Try to parse from combined text
            parts = card.card_def.text.split('//')
            if len(parts) >= 2:
                face_text = parts[0 if mode == 'left' else 1].lower()

        # Evaluate effect
        if 'damage' in face_text:
            bonus += 0.6
        elif 'destroy' in face_text or 'exile' in face_text:
            bonus += 0.8
        elif 'draw' in face_text:
            bonus += 0.5
        elif 'counter' in face_text:
            bonus += 0.7 * self.strategy.reactivity

        return bonus

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

        # If action is a spell cast, try to select targets
        if legal_action.type == ActionType.CAST_SPELL and legal_action.card_id:
            card = state.objects.get(legal_action.card_id)
            if card:
                targets = self._select_targets_for_spell(card, player_id, state)
                if targets:
                    action.targets = targets

        return action

    def _select_targets_for_spell(
        self,
        card,
        player_id: str,
        state: 'GameState'
    ) -> list[list]:
        """
        Select appropriate targets for a spell based on its text.

        Returns a list of target lists (one per target requirement).
        """
        from src.engine import CardType, ZoneType
        from src.engine.targeting import (
            TargetingSystem, Target, TargetRequirement,
            creature_filter, any_target_filter, spell_filter
        )

        text = ""
        if card.card_def and card.card_def.text:
            text = card.card_def.text.lower()

        # No targeting text means no targets needed
        if 'target' not in text:
            return []

        targeting = TargetingSystem(state)
        targets = []

        # Determine target type from text
        opponent_id = self._get_opponent_id(player_id, state)

        if 'target creature' in text:
            # Find legal creature targets
            filter_obj = creature_filter()
            source_obj = card

            legal_ids = targeting.get_legal_targets(
                TargetRequirement(filter=filter_obj),
                source_obj,
                player_id
            )

            if legal_ids:
                # Prefer opponent creatures for removal/damage, own creatures for buffs
                is_buff = '+' in text or 'gain' in text or 'gets' in text
                if is_buff:
                    # Target own creatures
                    own_creatures = [tid for tid in legal_ids
                                     if state.objects.get(tid) and
                                     state.objects[tid].controller == player_id]
                    if own_creatures:
                        best = Heuristics.get_best_target(own_creatures, state, prefer_creatures=True)
                        if best:
                            targets.append([Target(id=best)])
                else:
                    # Target opponent creatures
                    opp_creatures = [tid for tid in legal_ids
                                     if state.objects.get(tid) and
                                     state.objects[tid].controller != player_id]
                    if opp_creatures:
                        best = Heuristics.get_best_target(opp_creatures, state, prefer_creatures=True)
                        if best:
                            targets.append([Target(id=best)])

        elif 'target player' in text or 'target opponent' in text:
            # Target opponent
            if opponent_id:
                targets.append([Target(id=opponent_id, is_player=True)])

        elif 'any target' in text or 'target creature or player' in text:
            # Damage spells - prefer opponent if going face is good
            opponent = state.players.get(opponent_id)

            # Check if there are threatening creatures to remove
            opp_creatures = []
            battlefield = state.zones.get('battlefield')
            if battlefield:
                for obj_id in battlefield.objects:
                    obj = state.objects.get(obj_id)
                    if obj and obj.controller == opponent_id and CardType.CREATURE in obj.characteristics.types:
                        opp_creatures.append(obj_id)

            # If opponent is low on life, go face
            if opponent and opponent.life <= 5:
                targets.append([Target(id=opponent_id, is_player=True)])
            # If there are threatening creatures, kill them
            elif opp_creatures:
                best = Heuristics.get_best_target(opp_creatures, state, prefer_creatures=True)
                if best:
                    targets.append([Target(id=best)])
            # Default: go face
            elif opponent_id:
                targets.append([Target(id=opponent_id, is_player=True)])

        elif 'target spell' in text:
            # Counterspell - target top spell on stack that we don't control
            stack_zone = state.zones.get('stack')
            if stack_zone:
                for obj_id in reversed(stack_zone.objects):
                    obj = state.objects.get(obj_id)
                    if obj and obj.controller != player_id:
                        targets.append([Target(id=obj_id)])
                        break

        return targets

    def _get_opponent_id(self, player_id: str, state: 'GameState') -> str:
        """Get the opponent's player ID."""
        for pid in state.players:
            if pid != player_id:
                return pid
        return None

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
