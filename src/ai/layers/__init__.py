"""
Hyperdraft Strategy Layers

Three-layer strategic knowledge system for cards:
1. CardStrategy - General card play patterns
2. DeckRole - Card's role in specific deck context
3. MatchupGuide - Card guidance vs specific opponent

Used by both Hard AI (programmatic scoring) and Ultra AI (LLM guidance).
"""

from .types import (
    CardStrategy,
    DeckRole,
    MatchupGuide,
    CardLayers,
    DeckAnalysis,
    MatchupAnalysis
)
from .generator import LayerGenerator
from .defaults import (
    default_card_strategy,
    default_deck_role,
    default_matchup_guide,
    default_deck_analysis,
    default_matchup_analysis,
    infer_card_strategy,
    infer_deck_role
)

__all__ = [
    # Types
    'CardStrategy',
    'DeckRole',
    'MatchupGuide',
    'CardLayers',
    'DeckAnalysis',
    'MatchupAnalysis',
    # Generator
    'LayerGenerator',
    # Defaults
    'default_card_strategy',
    'default_deck_role',
    'default_matchup_guide',
    'default_deck_analysis',
    'default_matchup_analysis',
    'infer_card_strategy',
    'infer_deck_role',
]
