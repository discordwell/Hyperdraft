"""
Yu-Gi-Oh! Card Sets

Exports both card sets and their pre-built decks.
"""

from .ygo_starter import (
    YGO_STARTER_CARDS,
    WARRIOR_DECK, WARRIOR_EXTRA_DECK,
    SPELLCASTER_DECK, SPELLCASTER_EXTRA_DECK,
)
from .ygo_classic import (
    YGO_CLASSIC_CARDS,
    YUGI_DECK, YUGI_EXTRA_DECK,
    KAIBA_DECK, KAIBA_EXTRA_DECK,
)
from .deck_quality import (
    analyze_all_ygo_optimized_decks,
    analyze_ygo_deck_quality,
)
from .deck_builder import (
    build_ygo_optimized_deck,
    list_ygo_optimized_decks,
)

ALL_YGO_CARDS = {**YGO_STARTER_CARDS, **YGO_CLASSIC_CARDS}
