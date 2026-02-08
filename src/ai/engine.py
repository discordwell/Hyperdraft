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
    from src.engine.types import PendingChoice
    from .llm import LLMConfig


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
            'mulligan_strictness': 0.3, # How picky about hands
            'use_layers': False,       # Don't use strategy layers
            'use_llm': False           # Don't use LLM
        },
        'medium': {
            'random_factor': 0.15,
            'mistake_chance': 0.1,
            'block_skill': 0.8,
            'mulligan_strictness': 0.6,
            'use_layers': False,
            'use_llm': False
        },
        'hard': {
            'random_factor': 0.05,
            'mistake_chance': 0.02,
            'block_skill': 1.0,
            'mulligan_strictness': 0.9,
            'use_layers': True,        # Use programmatic layers
            'use_llm': False           # No LLM, just layer scoring
        },
        'ultra': {
            'random_factor': 0.0,
            'mistake_chance': 0.0,
            'block_skill': 1.0,
            'mulligan_strictness': 1.0,
            'use_layers': True,        # Use strategy layers
            'use_llm': True            # Use LLM for guidance
        }
    }

    def __init__(
        self,
        strategy: Optional[AIStrategy] = None,
        difficulty: str = 'medium',
        llm_config: Optional['LLMConfig'] = None
    ):
        """
        Initialize the AI engine.

        Args:
            strategy: The AI strategy to use (default: MidrangeStrategy)
            difficulty: Difficulty level ('easy', 'medium', 'hard', 'ultra')
            llm_config: LLM configuration for ultra difficulty
        """
        self.strategy = strategy or MidrangeStrategy()
        self.difficulty = difficulty
        self.llm_config = llm_config
        self._layers_prepared = False

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

    def make_choice(
        self,
        player_id: str,
        choice: 'PendingChoice',
        state: 'GameState'
    ) -> list:
        """
        Make a choice for the AI player based on the pending choice type.

        Args:
            player_id: The AI player's ID
            choice: The pending choice to respond to
            state: Current game state

        Returns:
            List of selected options appropriate for the choice type
        """
        from src.engine import CardType

        choice_type = choice.choice_type
        options = choice.options
        min_choices = choice.min_choices
        max_choices = choice.max_choices

        # Handle different choice types
        if choice_type in ("target", "target_with_callback"):
            return self._make_target_choice(player_id, choice, state)

        elif choice_type == "divide_allocation":
            return self._make_divide_allocation_choice(player_id, choice, state)

        elif choice_type == "modal_with_targeting":
            return self._make_modal_with_targeting_choice(player_id, choice, state)

        elif choice_type in ("modal", "modal_with_callback"):
            return self._make_modal_choice(player_id, choice, state)

        elif choice_type == "scry":
            return self._make_scry_choice(player_id, choice, state)

        elif choice_type == "surveil":
            return self._make_surveil_choice(player_id, choice, state)

        elif choice_type == "discard":
            return self._make_discard_choice(player_id, choice, state)

        elif choice_type == "sacrifice":
            return self._make_sacrifice_choice(player_id, choice, state)

        elif choice_type == "may":
            return self._make_may_choice(player_id, choice, state)

        elif choice_type == "order":
            # Just return options as-is (keep original order)
            return list(options)

        # Default: pick the first options up to min_choices
        if options:
            return list(options[:max(1, min_choices)])
        return []

    def _make_target_choice(
        self,
        player_id: str,
        choice: 'PendingChoice',
        state: 'GameState'
    ) -> list:
        """Choose targets from the available options."""
        from src.engine import CardType

        options = choice.options
        min_targets = choice.min_choices
        max_targets = choice.max_choices

        if not options:
            return []

        # First check callback_data for effect type (most reliable)
        callback_data = choice.callback_data or {}
        effect = callback_data.get('effect', '')

        # Classify effect by type
        removal_effects = {'damage', 'destroy', 'exile', 'bounce', 'tap', 'counter_remove'}
        buff_effects = {'pump', 'counter_add', 'untap', 'grant_keyword', 'life_change'}

        is_removal = effect in removal_effects
        is_buff = effect in buff_effects

        # Fall back to analyzing source card text if no effect specified
        if not effect:
            source = state.objects.get(choice.source_id)
            text = ""
            if source and source.card_def:
                text = (source.card_def.text or "").lower()
                is_removal = any(w in text for w in ["destroy", "exile", "damage", "-", "sacrifice", "return"])
                is_buff = any(w in text for w in ["+", "gain", "gets", "protection", "indestructible"])

        # Categorize options by ownership
        opponent_id = self._get_opponent_id(player_id, state)
        our_options = []
        opp_options = []

        for opt in options:
            # Option could be an ID string or a dict with 'id'
            opt_id = opt.get('id') if isinstance(opt, dict) else opt
            obj = state.objects.get(opt_id)

            if obj:
                if obj.controller == player_id:
                    our_options.append(opt)
                else:
                    opp_options.append(opt)
            elif opt_id in state.players:
                # It's a player target
                if opt_id == player_id:
                    our_options.append(opt)
                else:
                    opp_options.append(opt)

        # Select based on intent
        selected = []
        pool = opp_options if is_removal else our_options if is_buff else options

        # Fall back to all options if preferred pool is empty
        if not pool:
            pool = list(options)

        # Score and select targets
        scored = []
        for opt in pool:
            opt_id = opt.get('id') if isinstance(opt, dict) else opt
            score = self._score_target(opt_id, state, player_id, is_removal)
            scored.append((opt, score))

        # Sort by score (highest first for removal, varies for buffs)
        scored.sort(key=lambda x: x[1], reverse=True)

        # Select up to max_targets
        for opt, score in scored[:max_targets]:
            selected.append(opt)

        # Easy AI might pick randomly
        if self.difficulty == 'easy' and random.random() < 0.3 and options:
            return [random.choice(options)]

        return selected if len(selected) >= min_targets else list(options[:min_targets])

    def _score_target(
        self,
        target_id: str,
        state: 'GameState',
        player_id: str,
        is_removal: bool
    ) -> float:
        """Score a target for selection priority."""
        from src.engine import CardType

        obj = state.objects.get(target_id)
        if not obj:
            # Player target
            if target_id in state.players:
                player = state.players[target_id]
                # For damage, lower life = better target
                return 100 - player.life if target_id != player_id else -100
            return 0

        score = 0.0

        # Creatures score based on P/T and abilities
        if CardType.CREATURE in obj.characteristics.types:
            power = obj.characteristics.power or 0
            toughness = obj.characteristics.toughness or 0
            score += power * 2 + toughness

            # Keywords make it more threatening
            keywords = obj.characteristics.keywords or set()
            if "flying" in keywords:
                score += 2
            if "lifelink" in keywords:
                score += 2
            if "deathtouch" in keywords:
                score += 3
            if "trample" in keywords:
                score += 1

        # Planeswalkers are high priority
        if CardType.PLANESWALKER in obj.characteristics.types:
            score += 10

        # Card text value
        if obj.card_def and obj.card_def.text:
            text = obj.card_def.text.lower()
            if "draw" in text:
                score += 3
            if "destroy" in text or "exile" in text:
                score += 2

        return score

    def _make_modal_choice(
        self,
        player_id: str,
        choice: 'PendingChoice',
        state: 'GameState'
    ) -> list:
        """Choose modes for a modal spell."""
        options = choice.options
        min_modes = choice.min_choices
        max_modes = choice.max_choices

        if not options:
            return []

        # Score each mode based on game state relevance
        scored = []
        opponent_id = self._get_opponent_id(player_id, state)

        for i, mode in enumerate(options):
            mode_text = str(mode).lower() if mode else ""
            score = 0.0

            # Removal modes are high priority if opponent has creatures
            if any(w in mode_text for w in ["destroy", "exile", "damage"]):
                opp_creatures = self._count_creatures(opponent_id, state)
                score += 5 if opp_creatures > 0 else 1

            # Draw modes are generally good
            if "draw" in mode_text:
                score += 4

            # Counter modes if something on stack
            if "counter" in mode_text:
                if state.zones.get('stack') and state.zones['stack'].objects:
                    score += 6
                else:
                    score += 0

            # Buff modes if we have creatures
            if any(w in mode_text for w in ["+", "gain", "gets"]):
                our_creatures = self._count_creatures(player_id, state)
                score += 3 if our_creatures > 0 else 0

            # Life gain is decent
            if "life" in mode_text and "gain" in mode_text:
                score += 2

            scored.append((i, score))

        # Sort by score
        scored.sort(key=lambda x: x[1], reverse=True)

        # Select top modes
        selected = [idx for idx, _ in scored[:max_modes]]
        return selected[:max(min_modes, 1)]

    def _make_scry_choice(
        self,
        player_id: str,
        choice: 'PendingChoice',
        state: 'GameState'
    ) -> list:
        """Choose which cards to put on bottom for scry."""
        options = choice.options  # Card IDs on top of library

        if not options:
            return []

        # Evaluate each card - put bad cards on bottom
        to_bottom = []
        current_lands = self._count_lands(player_id, state)

        for card_id in options:
            card = state.objects.get(card_id)
            if not card:
                continue

            should_bottom = False

            # Check mana cost vs current mana
            if card.characteristics.mana_cost:
                from src.engine.mana import ManaCost
                cost = ManaCost.parse(card.characteristics.mana_cost)
                cmc = cost.mana_value

                # Late-game high drops are fine, early game bottom them
                if cmc > current_lands + 2:
                    should_bottom = True

            # Duplicate lands when we have many
            from src.engine import CardType
            if CardType.LAND in card.characteristics.types:
                if current_lands >= 5:
                    should_bottom = True

            if should_bottom:
                to_bottom.append(card_id)

        return to_bottom

    def _make_surveil_choice(
        self,
        player_id: str,
        choice: 'PendingChoice',
        state: 'GameState'
    ) -> list:
        """Choose which cards to put in graveyard for surveil."""
        options = choice.options

        if not options:
            return []

        # Similar to scry, but graveyard can be beneficial
        to_graveyard = []

        for card_id in options:
            card = state.objects.get(card_id)
            if not card:
                continue

            should_yard = False

            # Check for graveyard synergies in card text
            if card.card_def and card.card_def.text:
                text = card.card_def.text.lower()
                # Cards that want to be in graveyard
                if any(w in text for w in ["flashback", "escape", "from your graveyard"]):
                    should_yard = True

            # High cost cards we can't cast soon
            if card.characteristics.mana_cost:
                from src.engine.mana import ManaCost
                cost = ManaCost.parse(card.characteristics.mana_cost)
                current_lands = self._count_lands(player_id, state)
                if cost.mana_value > current_lands + 3:
                    should_yard = True

            if should_yard:
                to_graveyard.append(card_id)

        return to_graveyard

    def _make_discard_choice(
        self,
        player_id: str,
        choice: 'PendingChoice',
        state: 'GameState'
    ) -> list:
        """Choose which cards to discard."""
        options = choice.options
        min_discard = choice.min_choices

        if not options or min_discard == 0:
            return []

        # Score cards - discard lowest value cards
        scored = []
        current_lands = self._count_lands(player_id, state)

        for card_id in options:
            card = state.objects.get(card_id)
            if not card:
                continue

            score = 5.0  # Base value

            # High cost cards we can't cast are less valuable
            if card.characteristics.mana_cost:
                from src.engine.mana import ManaCost
                cost = ManaCost.parse(card.characteristics.mana_cost)
                if cost.mana_value > current_lands + 2:
                    score -= 2

            # Lands have reduced value if we have many
            from src.engine import CardType
            if CardType.LAND in card.characteristics.types:
                if current_lands >= 5:
                    score -= 3
                else:
                    score += 2  # Keep lands early

            # Card draw effects are valuable
            if card.card_def and card.card_def.text:
                text = card.card_def.text.lower()
                if "draw" in text:
                    score += 2
                if "destroy" in text or "exile" in text:
                    score += 1

            scored.append((card_id, score))

        # Sort by score (lowest first - discard worst cards)
        scored.sort(key=lambda x: x[1])

        return [cid for cid, _ in scored[:min_discard]]

    def _make_sacrifice_choice(
        self,
        player_id: str,
        choice: 'PendingChoice',
        state: 'GameState'
    ) -> list:
        """Choose which permanents to sacrifice."""
        options = choice.options
        min_sac = choice.min_choices

        if not options or min_sac == 0:
            return []

        # Score permanents - sacrifice lowest value
        scored = []

        for perm_id in options:
            perm = state.objects.get(perm_id)
            if not perm:
                continue

            score = self._score_target(perm_id, state, player_id, is_removal=False)
            scored.append((perm_id, score))

        # Sort by score (lowest first)
        scored.sort(key=lambda x: x[1])

        return [pid for pid, _ in scored[:min_sac]]

    def _make_may_choice(
        self,
        player_id: str,
        choice: 'PendingChoice',
        state: 'GameState'
    ) -> list:
        """Make a 'you may' decision."""
        # Analyze the prompt to understand the choice
        prompt = (choice.prompt or "").lower()

        # Generally say yes to beneficial effects
        if any(w in prompt for w in ["draw", "gain life", "create", "search", "+", "untap"]):
            return [True]

        # Say no to costs/downsides unless necessary
        if any(w in prompt for w in ["pay", "sacrifice", "discard", "lose life"]):
            # Still might want to do it for big effects
            if "draw" in prompt or "destroy" in prompt:
                return [True]
            return [False]

        # Default: yes (most "may" abilities are beneficial)
        return [True]

    def _make_divide_allocation_choice(
        self,
        player_id: str,
        choice: 'PendingChoice',
        state: 'GameState'
    ) -> list:
        """
        Make a damage/counter division allocation choice.

        Strategy:
        - For damage: allocate lethal damage to highest-threat creatures first
        - For counters: spread evenly or focus on best targets
        - Dump remainder on players if creatures are dealt with
        """
        from src.engine import CardType
        from src.engine.queries import get_toughness

        options = choice.options
        callback_data = choice.callback_data or {}
        total_amount = callback_data.get('total_amount', 0)
        effect = callback_data.get('effect', 'damage')

        if not options or total_amount <= 0:
            return []

        allocations = {}

        if effect == 'damage':
            # Score targets by threat level
            scored_targets = []
            for opt in options:
                opt_id = opt.get('id') if isinstance(opt, dict) else opt
                score = self._score_damage_target(opt_id, state, player_id)
                toughness = self._get_target_toughness(opt_id, state)
                scored_targets.append((opt_id, score, toughness))

            # Sort by score (highest threat first)
            scored_targets.sort(key=lambda x: x[1], reverse=True)

            remaining = total_amount

            # First pass: allocate lethal damage to creatures
            for target_id, score, toughness in scored_targets:
                if remaining <= 0:
                    break
                if toughness is not None and toughness > 0:
                    # Allocate lethal damage (minimum 1, up to toughness)
                    allocation = min(toughness, remaining)
                    allocations[target_id] = allocation
                    remaining -= allocation

            # Second pass: if we have remaining and there are players, dump on them
            if remaining > 0:
                opponent_id = self._get_opponent_id(player_id, state)
                for target_id, score, toughness in scored_targets:
                    if target_id in state.players and target_id == opponent_id:
                        # Dump on opponent
                        existing = allocations.get(target_id, 0)
                        allocations[target_id] = existing + remaining
                        remaining = 0
                        break

            # If still remaining and we have any targets with allocation, add to highest threat
            if remaining > 0 and allocations:
                top_target = scored_targets[0][0]
                allocations[top_target] = allocations.get(top_target, 0) + remaining
            elif remaining > 0 and scored_targets:
                # No allocations yet, put everything on best target
                allocations[scored_targets[0][0]] = total_amount

        elif effect == 'counter_add':
            # For counters: focus on best creatures we control
            scored_targets = []
            for opt in options:
                opt_id = opt.get('id') if isinstance(opt, dict) else opt
                obj = state.objects.get(opt_id)
                if obj and obj.controller == player_id:
                    score = self._score_target(opt_id, state, player_id, is_removal=False)
                    scored_targets.append((opt_id, score))

            if scored_targets:
                scored_targets.sort(key=lambda x: x[1], reverse=True)
                # Focus counters on best creature
                allocations[scored_targets[0][0]] = total_amount
            elif options:
                # Fallback: put on first option
                first_id = options[0].get('id') if isinstance(options[0], dict) else options[0]
                allocations[first_id] = total_amount

        else:
            # Default: spread evenly
            if options:
                per_target = max(1, total_amount // len(options))
                remaining = total_amount
                for opt in options:
                    opt_id = opt.get('id') if isinstance(opt, dict) else opt
                    allocation = min(per_target, remaining)
                    if allocation > 0:
                        allocations[opt_id] = allocation
                        remaining -= allocation
                    if remaining <= 0:
                        break

        # Return as list of dicts for the game to process
        return [{'target_id': tid, 'amount': amt} for tid, amt in allocations.items()]

    def _score_damage_target(
        self,
        target_id: str,
        state: 'GameState',
        player_id: str
    ) -> float:
        """Score a target for damage allocation priority."""
        from src.engine import CardType

        obj = state.objects.get(target_id)
        if not obj:
            # Player target
            if target_id in state.players:
                player = state.players[target_id]
                # Prefer opponent, especially at low life
                if target_id != player_id:
                    return 50 + (20 - player.life)  # Higher score for lower life
                return -10  # Don't damage self
            return 0

        score = 0.0

        # Prefer opponent creatures
        if obj.controller != player_id:
            score += 20

        # Creatures score based on threat
        if CardType.CREATURE in obj.characteristics.types:
            power = obj.characteristics.power or 0
            toughness = obj.characteristics.toughness or 0
            score += power * 3 + toughness

            # Keywords make it more threatening
            keywords = obj.characteristics.keywords or set()
            if "flying" in keywords:
                score += 5
            if "lifelink" in keywords:
                score += 5
            if "deathtouch" in keywords:
                score += 8
            if "trample" in keywords:
                score += 3

        return score

    def _get_target_toughness(self, target_id: str, state: 'GameState') -> int | None:
        """Get toughness of a target (None for players)."""
        from src.engine.queries import get_toughness

        obj = state.objects.get(target_id)
        if obj:
            try:
                return get_toughness(obj, state)
            except:
                return obj.characteristics.toughness
        return None  # Players don't have toughness

    def _make_modal_with_targeting_choice(
        self,
        player_id: str,
        choice: 'PendingChoice',
        state: 'GameState'
    ) -> list:
        """
        Make a modal choice where some modes may require targeting.

        Strategy:
        - Prefer modes that have valid targets (if targeting required)
        - Score based on effect type and current game state
        """
        from src.engine import CardType

        options = choice.options
        modes = choice.callback_data.get('modes', [])
        min_modes = choice.min_choices
        max_modes = choice.max_choices

        if not options or not modes:
            return []

        opponent_id = self._get_opponent_id(player_id, state)
        scored = []

        for i, opt in enumerate(options):
            mode_idx = opt.get('index', i) if isinstance(opt, dict) else i
            if mode_idx >= len(modes):
                continue

            mode = modes[mode_idx]
            score = 0.0

            # Check if targeting mode has valid targets
            if mode.get('requires_targeting'):
                target_filter = mode.get('target_filter', 'any')
                has_targets = self._has_valid_targets(target_filter, player_id, state)
                if not has_targets:
                    score -= 100  # Heavily penalize modes without valid targets

            # Score based on effect
            mode_text = mode.get('text', '').lower()
            effect = mode.get('effect', '')

            # Removal modes are high priority if opponent has creatures
            if effect in ('destroy', 'exile') or any(w in mode_text for w in ['destroy', 'exile']):
                opp_creatures = self._count_creatures(opponent_id, state) if opponent_id else 0
                score += 10 if opp_creatures > 0 else 1

            # Damage modes
            if effect == 'damage' or 'damage' in mode_text:
                score += 6

            # Draw modes
            if effect == 'draw' or 'draw' in mode_text:
                score += 5

            # Buff modes if we have creatures
            if effect in ('pump', 'counter_add') or '+' in mode_text:
                our_creatures = self._count_creatures(player_id, state)
                score += 4 if our_creatures > 0 else 0

            # Life gain
            if 'life' in mode_text and 'gain' in mode_text:
                score += 2

            # Token creation
            if 'create' in mode_text and 'token' in mode_text:
                score += 4

            # Tap/untap effects
            if effect == 'tap' or 'tap' in mode_text:
                opp_creatures = self._count_creatures(opponent_id, state) if opponent_id else 0
                score += 3 if opp_creatures > 0 else 1

            scored.append((mode_idx, score))

        # Sort by score
        scored.sort(key=lambda x: x[1], reverse=True)

        # Select top modes
        selected = [idx for idx, _ in scored[:max_modes] if scored[0][1] > -100]
        return selected[:max(min_modes, 1)] if selected else [scored[0][0]] if scored else []

    def _has_valid_targets(self, target_filter: str, player_id: str, state: 'GameState') -> bool:
        """Check if there are valid targets for a target filter."""
        from src.engine import CardType

        battlefield = state.zones.get('battlefield')
        if not battlefield:
            return target_filter in ('player', 'opponent', 'any')

        if target_filter == 'any':
            return True  # Always have players

        if target_filter == 'player':
            return len(state.players) > 0

        if target_filter == 'opponent':
            return len(state.players) > 1

        # Check for creatures
        for obj_id in battlefield.objects:
            obj = state.objects.get(obj_id)
            if not obj:
                continue

            is_creature = CardType.CREATURE in obj.characteristics.types

            if target_filter == 'creature' and is_creature:
                return True
            if target_filter == 'opponent_creature' and is_creature and obj.controller != player_id:
                return True
            if target_filter == 'your_creature' and is_creature and obj.controller == player_id:
                return True

        return False

    def _count_creatures(self, player_id: str, state: 'GameState') -> int:
        """Count creatures controlled by a player."""
        from src.engine import CardType

        count = 0
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = state.objects.get(obj_id)
                if obj and obj.controller == player_id:
                    if CardType.CREATURE in obj.characteristics.types:
                        count += 1
        return count

    def _count_lands(self, player_id: str, state: 'GameState') -> int:
        """Count lands controlled by a player."""
        from src.engine import CardType

        count = 0
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = state.objects.get(obj_id)
                if obj and obj.controller == player_id:
                    if CardType.LAND in obj.characteristics.types:
                        count += 1
        return count

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

    # === Layer Preparation ===

    async def prepare_for_match(
        self,
        our_deck_cards: list[str],
        card_defs: dict,
        opponent_deck_cards: Optional[list[str]] = None
    ):
        """
        Pre-compute strategy layers for a match.

        Call this before the game starts to generate all strategic
        knowledge. For Hard difficulty, uses heuristic layers.
        For Ultra difficulty, uses LLM-generated layers.

        Args:
            our_deck_cards: List of card names in our deck
            card_defs: Map of card name -> CardDefinition
            opponent_deck_cards: Opponent's deck card names (optional)
        """
        if not self.settings.get('use_layers'):
            return  # Easy/Medium don't use layers

        from .layers import LayerGenerator
        from .llm import LLMCache

        # Set up cache
        cache = LLMCache()

        # Set up provider if using LLM
        provider = None
        if self.settings.get('use_llm'):
            provider = self._get_llm_provider()

        # Create generator
        generator = LayerGenerator(provider=provider, cache=cache)

        # Generate all layers
        layers_map = await generator.generate_all_layers(
            card_defs=card_defs,
            our_deck=our_deck_cards,
            opp_deck=opponent_deck_cards
        )

        # Store layers in strategy
        for card_name, layers in layers_map.items():
            self.strategy.set_card_layers(card_name, layers)

        self._layers_prepared = True

    def _get_llm_provider(self):
        """Get the appropriate LLM provider based on config."""
        from .llm import OllamaProvider, LLMConfig
        from .llm.api_provider import get_provider

        config = self.llm_config or LLMConfig()

        try:
            return get_provider(config)
        except RuntimeError as e:
            print(f"Warning: {e}")
            print("Using heuristic layers instead of LLM.")
            return None

    def prepare_for_match_sync(
        self,
        our_deck_cards: list[str],
        card_defs: dict,
        opponent_deck_cards: Optional[list[str]] = None
    ):
        """
        Synchronous wrapper for prepare_for_match.

        Use this if you're not in an async context.
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Can't use run_until_complete in running loop
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.prepare_for_match(our_deck_cards, card_defs, opponent_deck_cards)
                    )
                    future.result()
            else:
                loop.run_until_complete(
                    self.prepare_for_match(our_deck_cards, card_defs, opponent_deck_cards)
                )
        except RuntimeError:
            asyncio.run(
                self.prepare_for_match(our_deck_cards, card_defs, opponent_deck_cards)
            )

    # === Convenience Factory Methods ===

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

    @classmethod
    def create_hard_bot(cls, strategy: Optional[AIStrategy] = None) -> 'AIEngine':
        """
        Create a Hard AI with programmatic layer scoring.

        Uses strategy layers for improved decision-making but
        doesn't require LLM - uses heuristic layer generation.
        """
        return cls(strategy=strategy or MidrangeStrategy(), difficulty='hard')

    @classmethod
    def create_ultra_bot(cls, llm_config: Optional['LLMConfig'] = None) -> 'AIEngine':
        """
        Create an Ultra AI with LLM-guided decisions.

        Uses all three strategy layers with LLM-generated guidance.
        Falls back to heuristics if LLM is unavailable.

        Args:
            llm_config: LLM configuration (defaults to Ollama with qwen2.5:3b)
        """
        from .strategies import UltraStrategy
        from .llm import LLMConfig, OllamaProvider

        config = llm_config or LLMConfig()

        # Try to get provider
        provider = None
        try:
            from .llm.api_provider import get_provider
            provider = get_provider(config)
        except RuntimeError:
            print("Warning: No LLM provider available. Ultra AI will use heuristics.")

        strategy = UltraStrategy(provider=provider, config=config)
        return cls(strategy=strategy, difficulty='ultra', llm_config=config)


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
