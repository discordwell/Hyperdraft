"""
Layer Generator

Generates strategy layers using LLM or falls back to heuristics.
"""

import hashlib
import json
from typing import Optional, TYPE_CHECKING

from .types import (
    CardStrategy,
    DeckRole,
    MatchupGuide,
    CardLayers,
    DeckAnalysis,
    MatchupAnalysis
)
from .defaults import (
    infer_card_strategy,
    infer_deck_role,
    default_card_strategy,
    default_deck_role,
    default_matchup_guide,
    default_deck_analysis,
    default_matchup_analysis
)

if TYPE_CHECKING:
    from src.ai.llm import LLMProvider, LLMCache
    from src.engine import CardDefinition


class LayerGenerator:
    """
    Generates strategy layers for cards.

    Uses LLM when available, falls back to heuristic inference.
    All results are cached for efficiency.
    """

    def __init__(
        self,
        provider: Optional['LLMProvider'] = None,
        cache: Optional['LLMCache'] = None
    ):
        """
        Initialize the generator.

        Args:
            provider: LLM provider (None = use heuristics only)
            cache: Cache for LLM responses
        """
        self.provider = provider
        self.cache = cache

        # Track if provider is actually available
        self._provider_available = provider is not None and provider.is_available

    def _hash_deck(self, deck_cards: list[str]) -> str:
        """Create a hash for a deck."""
        sorted_cards = sorted(deck_cards)
        data = json.dumps(sorted_cards)
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _hash_matchup(self, our_deck: list[str], opp_deck: list[str]) -> str:
        """Create a hash for a matchup."""
        our_hash = self._hash_deck(our_deck)
        opp_hash = self._hash_deck(opp_deck)
        return hashlib.sha256(f"{our_hash}:{opp_hash}".encode()).hexdigest()[:16]

    # === Card Strategy (Layer 1) ===

    async def generate_card_strategy(
        self,
        card_def: 'CardDefinition'
    ) -> CardStrategy:
        """
        Generate Layer 1 for a card.

        Checks cache first, then uses LLM or heuristics.
        """
        # Check cache
        if self.cache:
            cached = self.cache.get_card_strategy(card_def.name)
            if cached:
                return CardStrategy.from_dict(cached)

        # Try LLM
        if self._provider_available:
            try:
                strategy = await self._llm_card_strategy(card_def)
                if self.cache:
                    self.cache.set_card_strategy(
                        card_def.name,
                        strategy.to_dict(),
                        self.provider.model_name
                    )
                return strategy
            except Exception as e:
                print(f"LLM card strategy failed: {e}")

        # Fall back to heuristics
        strategy = infer_card_strategy(card_def)

        # Cache heuristic result too
        if self.cache:
            self.cache.set_card_strategy(
                card_def.name,
                strategy.to_dict(),
                "heuristic"
            )

        return strategy

    async def _llm_card_strategy(self, card_def: 'CardDefinition') -> CardStrategy:
        """Generate card strategy using LLM."""
        from src.ai.llm.prompts import (
            CARD_STRATEGY_SYSTEM,
            CARD_STRATEGY_PROMPT,
            CARD_STRATEGY_SCHEMA
        )

        # Build prompt
        prompt = CARD_STRATEGY_PROMPT.format(
            name=card_def.name,
            cost=card_def.characteristics.mana_cost or "N/A",
            type=str(list(card_def.characteristics.types)),
            text=card_def.text or "No text",
            pt=f"{card_def.characteristics.power or '-'}/{card_def.characteristics.toughness or '-'}"
        )

        # Get LLM response
        result = await self.provider.complete_json(
            prompt=prompt,
            schema=CARD_STRATEGY_SCHEMA,
            system=CARD_STRATEGY_SYSTEM
        )

        return CardStrategy(
            card_name=card_def.name,
            timing=result.get("timing", "any"),
            base_priority=float(result.get("base_priority", 0.5)),
            role=result.get("role", "utility"),
            target_priority=result.get("target_priority", ["creature"]),
            when_to_play=result.get("when_to_play", ""),
            when_not_to_play=result.get("when_not_to_play", ""),
            targeting_advice=result.get("targeting_advice", "")
        )

    # === Deck Role (Layer 2) ===

    async def generate_deck_role(
        self,
        card_def: 'CardDefinition',
        deck_cards: list[str],
        archetype: str = "midrange"
    ) -> DeckRole:
        """
        Generate Layer 2 for a card in a deck.

        Args:
            card_def: The card to analyze
            deck_cards: List of all card names in deck
            archetype: Deck archetype
        """
        deck_hash = self._hash_deck(deck_cards)

        # Check cache
        if self.cache:
            cached = self.cache.get_deck_role(card_def.name, deck_cards)
            if cached:
                return DeckRole.from_dict(cached)

        # Try LLM
        if self._provider_available:
            try:
                role = await self._llm_deck_role(card_def, deck_cards, deck_hash, archetype)
                if self.cache:
                    self.cache.set_deck_role(
                        card_def.name,
                        deck_cards,
                        role.to_dict(),
                        self.provider.model_name
                    )
                return role
            except Exception as e:
                print(f"LLM deck role failed: {e}")

        # Fall back to heuristics
        role = infer_deck_role(card_def, deck_cards, deck_hash, archetype)

        if self.cache:
            self.cache.set_deck_role(
                card_def.name,
                deck_cards,
                role.to_dict(),
                "heuristic"
            )

        return role

    async def _llm_deck_role(
        self,
        card_def: 'CardDefinition',
        deck_cards: list[str],
        deck_hash: str,
        archetype: str
    ) -> DeckRole:
        """Generate deck role using LLM."""
        from src.ai.llm.prompts import (
            DECK_ROLE_SYSTEM,
            DECK_ROLE_PROMPT,
            DECK_ROLE_SCHEMA
        )

        # Summarize deck
        unique_cards = sorted(set(deck_cards))
        deck_list = "\n".join(f"- {deck_cards.count(c)}x {c}" for c in unique_cards[:20])

        # Calculate curve
        curve = {}
        # Would need card database to calculate properly

        # Key cards (most copies)
        from collections import Counter
        card_counts = Counter(deck_cards)
        key_cards = [card for card, count in card_counts.most_common(5)]

        prompt = DECK_ROLE_PROMPT.format(
            card_name=card_def.name,
            card_cost=card_def.characteristics.mana_cost or "N/A",
            card_type=str(list(card_def.characteristics.types)),
            card_text=card_def.text or "No text",
            archetype=archetype,
            colors="Unknown",
            key_cards=", ".join(key_cards),
            curve=str(curve),
            deck_list=deck_list
        )

        result = await self.provider.complete_json(
            prompt=prompt,
            schema=DECK_ROLE_SCHEMA,
            system=DECK_ROLE_SYSTEM
        )

        return DeckRole(
            card_name=card_def.name,
            deck_hash=deck_hash,
            role_weight=float(result.get("role_weight", 1.0)),
            curve_slot=int(result.get("curve_slot", 3)),
            synergy_cards=result.get("synergy_cards", []),
            enables=[],
            is_key_card=bool(result.get("is_key_card", False)),
            deck_role=result.get("deck_role", ""),
            play_pattern=result.get("play_pattern", ""),
            synergy_notes=result.get("synergy_notes", "")
        )

    # === Matchup Guide (Layer 3) ===

    async def generate_matchup_guide(
        self,
        card_def: 'CardDefinition',
        our_deck: list[str],
        opp_deck: list[str],
        our_analysis: Optional[DeckAnalysis] = None,
        opp_analysis: Optional[DeckAnalysis] = None
    ) -> MatchupGuide:
        """
        Generate Layer 3 for a card vs opponent.

        Args:
            card_def: The card to analyze
            our_deck: Our deck card names
            opp_deck: Opponent's deck card names
            our_analysis: Pre-computed deck analysis
            opp_analysis: Pre-computed opponent analysis
        """
        matchup_hash = self._hash_matchup(our_deck, opp_deck)

        # Check cache
        if self.cache:
            cached = self.cache.get_matchup_guide(card_def.name, our_deck, opp_deck)
            if cached:
                return MatchupGuide.from_dict(cached)

        # Try LLM
        if self._provider_available:
            try:
                guide = await self._llm_matchup_guide(
                    card_def, our_deck, opp_deck, matchup_hash,
                    our_analysis, opp_analysis
                )
                if self.cache:
                    self.cache.set_matchup_guide(
                        card_def.name,
                        our_deck,
                        opp_deck,
                        guide.to_dict(),
                        self.provider.model_name
                    )
                return guide
            except Exception as e:
                print(f"LLM matchup guide failed: {e}")

        # Fall back to default
        return default_matchup_guide(card_def.name, matchup_hash)

    async def _llm_matchup_guide(
        self,
        card_def: 'CardDefinition',
        our_deck: list[str],
        opp_deck: list[str],
        matchup_hash: str,
        our_analysis: Optional[DeckAnalysis],
        opp_analysis: Optional[DeckAnalysis]
    ) -> MatchupGuide:
        """Generate matchup guide using LLM."""
        from src.ai.llm.prompts import (
            MATCHUP_GUIDE_SYSTEM,
            MATCHUP_GUIDE_PROMPT,
            MATCHUP_GUIDE_SCHEMA
        )

        from collections import Counter

        our_key = [c for c, _ in Counter(our_deck).most_common(5)]
        opp_key = [c for c, _ in Counter(opp_deck).most_common(5)]

        prompt = MATCHUP_GUIDE_PROMPT.format(
            card_name=card_def.name,
            card_type=str(list(card_def.characteristics.types)),
            card_text=card_def.text or "No text",
            our_archetype=our_analysis.archetype if our_analysis else "Unknown",
            our_key_cards=", ".join(our_key),
            opp_archetype=opp_analysis.archetype if opp_analysis else "Unknown",
            opp_key_cards=", ".join(opp_key),
            opp_threats=", ".join(opp_analysis.their_threats if opp_analysis else opp_key[:3]),
            opp_answers=""
        )

        result = await self.provider.complete_json(
            prompt=prompt,
            schema=MATCHUP_GUIDE_SCHEMA,
            system=MATCHUP_GUIDE_SYSTEM
        )

        return MatchupGuide(
            card_name=card_def.name,
            matchup_hash=matchup_hash,
            priority_modifier=float(result.get("priority_modifier", 1.0)),
            save_for=result.get("save_for", []),
            dont_use_on=result.get("dont_use_on", []),
            threat_level=0.5,
            matchup_role=result.get("matchup_role", ""),
            key_targets=result.get("key_targets", ""),
            timing_advice=result.get("timing_advice", "")
        )

    # === Deck Analysis ===

    async def generate_deck_analysis(self, deck_cards: list[str]) -> DeckAnalysis:
        """Generate overall deck analysis."""
        deck_hash = self._hash_deck(deck_cards)

        # Check cache
        if self.cache:
            cached = self.cache.get_deck_analysis(deck_cards)
            if cached:
                return DeckAnalysis.from_dict(cached)

        # Try LLM
        if self._provider_available:
            try:
                analysis = await self._llm_deck_analysis(deck_cards, deck_hash)
                if self.cache:
                    self.cache.set_deck_analysis(
                        deck_cards,
                        analysis.to_dict(),
                        self.provider.model_name
                    )
                return analysis
            except Exception as e:
                print(f"LLM deck analysis failed: {e}")

        # Fall back to default
        return default_deck_analysis(deck_hash)

    async def _llm_deck_analysis(
        self,
        deck_cards: list[str],
        deck_hash: str
    ) -> DeckAnalysis:
        """Generate deck analysis using LLM."""
        from src.ai.llm.prompts import (
            DECK_ANALYSIS_SYSTEM,
            DECK_ANALYSIS_PROMPT,
            DECK_ANALYSIS_SCHEMA
        )

        from collections import Counter

        unique_cards = sorted(set(deck_cards))
        deck_list = "\n".join(f"- {deck_cards.count(c)}x {c}" for c in unique_cards)

        prompt = DECK_ANALYSIS_PROMPT.format(
            deck_list=deck_list,
            colors="Unknown",
            curve="{}"
        )

        result = await self.provider.complete_json(
            prompt=prompt,
            schema=DECK_ANALYSIS_SCHEMA,
            system=DECK_ANALYSIS_SYSTEM
        )

        return DeckAnalysis(
            deck_hash=deck_hash,
            archetype=result.get("archetype", "midrange"),
            win_conditions=result.get("win_conditions", []),
            key_cards=result.get("key_cards", []),
            curve={},
            game_plan=result.get("game_plan", "")
        )

    # === Matchup Analysis ===

    async def generate_matchup_analysis(
        self,
        our_deck: list[str],
        opp_deck: list[str],
        our_analysis: Optional[DeckAnalysis] = None,
        opp_analysis: Optional[DeckAnalysis] = None
    ) -> MatchupAnalysis:
        """Generate matchup analysis."""
        matchup_hash = self._hash_matchup(our_deck, opp_deck)

        # Check cache
        if self.cache:
            cached = self.cache.get_matchup_analysis(our_deck, opp_deck)
            if cached:
                return MatchupAnalysis.from_dict(cached)

        # Try LLM
        if self._provider_available:
            try:
                analysis = await self._llm_matchup_analysis(
                    our_deck, opp_deck, matchup_hash,
                    our_analysis, opp_analysis
                )
                if self.cache:
                    self.cache.set_matchup_analysis(
                        our_deck,
                        opp_deck,
                        analysis.to_dict(),
                        self.provider.model_name
                    )
                return analysis
            except Exception as e:
                print(f"LLM matchup analysis failed: {e}")

        # Fall back to default
        return default_matchup_analysis(matchup_hash)

    async def _llm_matchup_analysis(
        self,
        our_deck: list[str],
        opp_deck: list[str],
        matchup_hash: str,
        our_analysis: Optional[DeckAnalysis],
        opp_analysis: Optional[DeckAnalysis]
    ) -> MatchupAnalysis:
        """Generate matchup analysis using LLM."""
        from src.ai.llm.prompts import (
            MATCHUP_ANALYSIS_SYSTEM,
            MATCHUP_ANALYSIS_PROMPT,
            MATCHUP_ANALYSIS_SCHEMA
        )

        from collections import Counter

        our_key = [c for c, _ in Counter(our_deck).most_common(5)]
        opp_key = [c for c, _ in Counter(opp_deck).most_common(5)]

        prompt = MATCHUP_ANALYSIS_PROMPT.format(
            our_archetype=our_analysis.archetype if our_analysis else "Unknown",
            our_win_cons=", ".join(our_analysis.win_conditions if our_analysis else ["creature damage"]),
            our_key_cards=", ".join(our_key),
            opp_archetype=opp_analysis.archetype if opp_analysis else "Unknown",
            opp_win_cons=", ".join(opp_analysis.win_conditions if opp_analysis else ["creature damage"]),
            opp_key_cards=", ".join(opp_key)
        )

        result = await self.provider.complete_json(
            prompt=prompt,
            schema=MATCHUP_ANALYSIS_SCHEMA,
            system=MATCHUP_ANALYSIS_SYSTEM
        )

        return MatchupAnalysis(
            matchup_hash=matchup_hash,
            our_role=result.get("our_role", "midrange"),
            their_threats=result.get("their_threats", []),
            their_answers=result.get("their_answers", []),
            game_plan=result.get("game_plan", ""),
            key_turns=result.get("key_turns", {})
        )

    # === Batch Generation ===

    async def generate_all_layers(
        self,
        card_defs: dict[str, 'CardDefinition'],
        our_deck: list[str],
        opp_deck: Optional[list[str]] = None
    ) -> dict[str, CardLayers]:
        """
        Generate all layers for all cards in a deck.

        This is the main entry point for match preparation.

        Args:
            card_defs: Map of card name -> CardDefinition
            our_deck: Our deck card names
            opp_deck: Opponent's deck card names (optional)

        Returns:
            Map of card name -> CardLayers
        """
        result = {}

        # Generate deck analysis
        our_analysis = await self.generate_deck_analysis(our_deck)
        opp_analysis = None
        matchup_analysis = None

        if opp_deck:
            opp_analysis = await self.generate_deck_analysis(opp_deck)
            matchup_analysis = await self.generate_matchup_analysis(
                our_deck, opp_deck, our_analysis, opp_analysis
            )

        # Generate layers for each card
        unique_cards = set(our_deck)
        for card_name in unique_cards:
            card_def = card_defs.get(card_name)
            if not card_def:
                continue

            # Layer 1: Card strategy
            strategy = await self.generate_card_strategy(card_def)

            # Layer 2: Deck role
            deck_role = await self.generate_deck_role(
                card_def, our_deck, our_analysis.archetype
            )

            # Layer 3: Matchup guide (if opponent known)
            matchup_guide = None
            if opp_deck:
                matchup_guide = await self.generate_matchup_guide(
                    card_def, our_deck, opp_deck,
                    our_analysis, opp_analysis
                )

            result[card_name] = CardLayers(
                card_strategy=strategy,
                deck_role=deck_role,
                matchup_guide=matchup_guide,
                deck_analysis=our_analysis,
                matchup_analysis=matchup_analysis
            )

        return result
