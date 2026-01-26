"""
Ultra AI Strategy

LLM-guided strategy that uses all three layers for decisions.
Falls back to MidrangeStrategy when LLM is unavailable.
"""

import asyncio
import hashlib
from typing import TYPE_CHECKING, Optional

from .base import AIStrategy
from .midrange import MidrangeStrategy

if TYPE_CHECKING:
    from src.engine import GameState, LegalAction, AttackDeclaration, BlockDeclaration
    from src.ai.evaluator import BoardEvaluator
    from src.ai.llm import LLMProvider, LLMConfig
    from src.ai.layers import CardLayers


class UltraStrategy(AIStrategy):
    """
    LLM-powered strategy using full layer context.

    For each decision, builds a rich context from the three layers
    and queries the LLM. Falls back to MidrangeStrategy when needed.

    Note: This strategy supports both sync and async evaluation.
    The sync evaluate_action() method wraps the async version
    for compatibility with the existing AIEngine.
    """

    def __init__(
        self,
        provider: Optional['LLMProvider'] = None,
        config: Optional['LLMConfig'] = None
    ):
        """
        Initialize Ultra strategy.

        Args:
            provider: LLM provider for decisions
            config: LLM configuration
        """
        super().__init__()
        self.provider = provider
        self.config = config
        self._fallback = MidrangeStrategy()
        self._decision_cache: dict[str, dict] = {}

    @property
    def name(self) -> str:
        return "Ultra"

    @property
    def reactivity(self) -> float:
        # Ultra adapts its reactivity based on context
        return 0.7

    def evaluate_action(
        self,
        action: 'LegalAction',
        state: 'GameState',
        evaluator: 'BoardEvaluator',
        player_id: str
    ) -> float:
        """
        Evaluate an action (sync wrapper).

        Uses cached decisions when available, otherwise
        falls back to MidrangeStrategy for sync evaluation.
        """
        # Check if we have layers for this card
        if action.card_id:
            card = state.objects.get(action.card_id)
            if card:
                layers = self.get_layers(card.name)
                if layers:
                    # Use programmatic layer scoring (like Hard AI)
                    return self._score_with_layers(action, state, evaluator, player_id, card, layers)

        # Fallback to midrange
        return self._fallback.evaluate_action(action, state, evaluator, player_id)

    def _score_with_layers(
        self,
        action: 'LegalAction',
        state: 'GameState',
        evaluator: 'BoardEvaluator',
        player_id: str,
        card,
        layers: 'CardLayers'
    ) -> float:
        """
        Score an action using layer data.

        This is a more sophisticated version of Hard AI's scoring
        that uses all three layers.
        """
        base_score = 1.0

        # Layer 1: Card strategy
        strategy = layers.card_strategy
        turn = state.turn_number if hasattr(state, 'turn_number') else 1

        # Timing adjustments
        if strategy.timing == "early" and turn <= 3:
            base_score *= 1.3
        elif strategy.timing == "late" and turn >= 5:
            base_score *= 1.3
        elif strategy.timing == "reactive":
            # Check if we're responding to something
            if hasattr(state, 'stack') and state.stack:
                base_score *= 1.4

        # Priority
        base_score *= (0.5 + strategy.base_priority)

        # Role adjustments
        opponent_id = self._get_opponent_id(player_id, state)
        opp_creatures = self._count_opponent_creatures(state, opponent_id)

        if strategy.role == "removal" and opp_creatures > 0:
            base_score *= 1.3
        elif strategy.role == "threat" and opp_creatures == 0:
            base_score *= 1.2

        # Layer 2: Deck role
        if layers.deck_role:
            deck_role = layers.deck_role
            base_score *= deck_role.role_weight

            # Key card bonus
            if deck_role.is_key_card:
                base_score *= 1.2

            # Curve consideration
            if turn == deck_role.curve_slot:
                base_score *= 1.15

        # Layer 3: Matchup guide
        if layers.matchup_guide:
            matchup = layers.matchup_guide
            base_score *= matchup.priority_modifier

            # Check if opponent has cards we should save for
            if matchup.save_for:
                opp_board = self._get_opponent_board_names(state, opponent_id)
                for target in matchup.save_for:
                    if target in opp_board:
                        base_score *= 1.4
                        break

        return base_score

    async def evaluate_action_async(
        self,
        action: 'LegalAction',
        state: 'GameState',
        player_id: str
    ) -> dict:
        """
        Evaluate an action asynchronously using LLM.

        Returns:
            Dict with 'should_play', 'score', 'reasoning', 'target'
        """
        if not action.card_id:
            return {"should_play": True, "score": 0.0, "reasoning": "Pass action"}

        card = state.objects.get(action.card_id)
        if not card:
            return {"should_play": False, "score": 0.0, "reasoning": "Card not found"}

        # Check cache
        cache_key = self._hash_decision(card.name, state, player_id)
        if cache_key in self._decision_cache:
            return self._decision_cache[cache_key]

        # Get layers
        layers = self.get_layers(card.name)
        if not layers or not self.provider or not self.provider.is_available:
            # Fall back to programmatic score
            from src.ai.evaluator import BoardEvaluator
            evaluator = BoardEvaluator(state)
            score = self._score_with_layers(action, state, evaluator, player_id, card, layers) if layers else 0.5
            result = {
                "should_play": score > 0.5,
                "score": score,
                "reasoning": "Scored by heuristics",
                "target": None
            }
            self._decision_cache[cache_key] = result
            return result

        # Build LLM context
        context = self._build_llm_context(card, state, layers, player_id)

        try:
            from src.ai.llm.prompts import DECISION_SYSTEM, DECISION_SCHEMA
            response = await self.provider.complete_json(
                prompt=context,
                schema=DECISION_SCHEMA,
                system=DECISION_SYSTEM
            )

            result = {
                "should_play": response.get("should_play", True),
                "score": float(response.get("score", 0.5)),
                "reasoning": response.get("reasoning", ""),
                "target": response.get("target")
            }

        except Exception as e:
            print(f"Ultra AI LLM decision failed: {e}")
            from src.ai.evaluator import BoardEvaluator
            evaluator = BoardEvaluator(state)
            score = self._score_with_layers(action, state, evaluator, player_id, card, layers)
            result = {
                "should_play": score > 0.5,
                "score": score,
                "reasoning": f"Fallback: {e}",
                "target": None
            }

        self._decision_cache[cache_key] = result
        return result

    def _build_llm_context(
        self,
        card,
        state: 'GameState',
        layers: 'CardLayers',
        player_id: str
    ) -> str:
        """Build rich context for LLM decision."""
        from src.ai.llm.prompts import DECISION_PROMPT

        opponent_id = self._get_opponent_id(player_id, state)
        player = state.players.get(player_id)
        opponent = state.players.get(opponent_id)

        return DECISION_PROMPT.format(
            card_name=card.name,
            when_to_play=layers.card_strategy.when_to_play,
            when_not_to_play=layers.card_strategy.when_not_to_play,
            targeting_advice=layers.card_strategy.targeting_advice,
            archetype=layers.deck_analysis.archetype if layers.deck_analysis else "Unknown",
            deck_role=layers.deck_role.deck_role if layers.deck_role else "",
            play_pattern=layers.deck_role.play_pattern if layers.deck_role else "",
            synergy_notes=layers.deck_role.synergy_notes if layers.deck_role else "",
            our_role=layers.matchup_analysis.our_role if layers.matchup_analysis else "Unknown",
            matchup_role=layers.matchup_guide.matchup_role if layers.matchup_guide else "",
            key_targets=layers.matchup_guide.key_targets if layers.matchup_guide else "",
            timing_advice=layers.matchup_guide.timing_advice if layers.matchup_guide else "",
            turn=state.turn_number if hasattr(state, 'turn_number') else 1,
            our_life=player.life if player else 20,
            opp_life=opponent.life if opponent else 20,
            our_board=self._describe_board(state, player_id),
            opp_board=self._describe_board(state, opponent_id),
            hand_count=self._count_hand(state, player_id),
            mana_available=self._count_mana(state, player_id)
        )

    def _hash_decision(self, card_name: str, state: 'GameState', player_id: str) -> str:
        """Create a hash key for decision caching."""
        # Include relevant board state in hash
        turn = state.turn_number if hasattr(state, 'turn_number') else 0
        life = state.players.get(player_id).life if state.players.get(player_id) else 20

        key = f"{card_name}:{turn}:{life}"
        return hashlib.sha256(key.encode()).hexdigest()[:12]

    def plan_attacks(
        self,
        state: 'GameState',
        player_id: str,
        evaluator: 'BoardEvaluator',
        legal_attackers: list[str]
    ) -> list['AttackDeclaration']:
        """Plan attacks using layer knowledge."""
        # For now, delegate to fallback
        # Future: Use matchup analysis for attack planning
        return self._fallback.plan_attacks(state, player_id, evaluator, legal_attackers)

    def plan_blocks(
        self,
        state: 'GameState',
        player_id: str,
        evaluator: 'BoardEvaluator',
        attackers: list['AttackDeclaration'],
        legal_blockers: list[str]
    ) -> list['BlockDeclaration']:
        """Plan blocks using layer knowledge."""
        # For now, delegate to fallback
        # Future: Use matchup analysis for block planning
        return self._fallback.plan_blocks(state, player_id, evaluator, attackers, legal_blockers)

    def should_counter(
        self,
        spell_on_stack,
        state: 'GameState',
        evaluator: 'BoardEvaluator',
        player_id: str
    ) -> bool:
        """Decide whether to counter using matchup knowledge."""
        # Check if spell is on our threat list
        spell_name = spell_on_stack.name if hasattr(spell_on_stack, 'name') else ""

        # Look through our layers for matchup data
        for layers in self._layers.values():
            if layers.matchup_guide and spell_name in layers.matchup_guide.save_for:
                return True

        # Fall back
        return self._fallback.should_counter(spell_on_stack, state, evaluator, player_id)

    def clear_decision_cache(self):
        """Clear the decision cache."""
        self._decision_cache.clear()

    # === Helper Methods ===

    def _get_opponent_id(self, player_id: str, state: 'GameState') -> str:
        """Get the opponent's player ID."""
        for pid in state.players:
            if pid != player_id:
                return pid
        return None

    def _count_opponent_creatures(self, state: 'GameState', opponent_id: str) -> int:
        """Count opponent's creatures on battlefield."""
        from src.engine import CardType, ZoneType

        count = 0
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = state.objects.get(obj_id)
                if obj and obj.controller == opponent_id:
                    if CardType.CREATURE in obj.characteristics.types:
                        count += 1
        return count

    def _get_opponent_board_names(self, state: 'GameState', opponent_id: str) -> set:
        """Get names of all opponent permanents."""
        names = set()
        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = state.objects.get(obj_id)
                if obj and obj.controller == opponent_id:
                    names.add(obj.name)
        return names

    def _describe_board(self, state: 'GameState', player_id: str) -> str:
        """Describe a player's board state."""
        from src.engine import CardType

        creatures = []
        other = []

        battlefield = state.zones.get('battlefield')
        if battlefield:
            for obj_id in battlefield.objects:
                obj = state.objects.get(obj_id)
                if obj and obj.controller == player_id:
                    if CardType.CREATURE in obj.characteristics.types:
                        power = obj.characteristics.power or 0
                        toughness = obj.characteristics.toughness or 0
                        creatures.append(f"{obj.name} ({power}/{toughness})")
                    else:
                        other.append(obj.name)

        parts = []
        if creatures:
            parts.append(f"Creatures: {', '.join(creatures)}")
        if other:
            parts.append(f"Other: {', '.join(other)}")

        return "; ".join(parts) if parts else "Empty"

    def _count_hand(self, state: 'GameState', player_id: str) -> int:
        """Count cards in hand."""
        hand_zone = state.zones.get(f'hand_{player_id}')
        if hand_zone:
            return len(hand_zone.objects)
        return 0

    def _count_mana(self, state: 'GameState', player_id: str) -> int:
        """Count available mana."""
        # This is a rough estimate - untapped lands
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
