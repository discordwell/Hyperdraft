# Card definitions
"""
Card Registry Module

Exports all card registries from the different sets.
All sets contain real card data fetched from Scryfall API.
Custom/themed sets (fan-made) available separately via .custom module.
"""

# Test sets
from .test_cards import TEST_CARDS

# MTG Standard rotation sets
from .wilds_of_eldraine import WILDS_OF_ELDRAINE_CARDS
from .lost_caverns_ixalan import LOST_CAVERNS_IXALAN_CARDS
from .murders_karlov_manor import MURDERS_KARLOV_MANOR_CARDS
from .outlaws_thunder_junction import OUTLAWS_THUNDER_JUNCTION_CARDS
from .bloomburrow import BLOOMBURROW_CARDS
from .duskmourn import DUSKMOURN_CARDS
from .foundations import FOUNDATIONS_CARDS

# Universes Beyond sets
from .edge_of_eternities import EDGE_OF_ETERNITIES_CARDS
from .lorwyn_eclipsed import LORWYN_ECLIPSED_CARDS
from .spider_man import SPIDER_MAN_CARDS
from .avatar_tla import AVATAR_TLA_CARDS
from .final_fantasy import FINAL_FANTASY_CARDS

# Custom sets available via: from src.cards.custom import CUSTOM_CARDS


def build_combined_registry() -> dict:
    """
    Build a combined card registry from all real MTG sets.

    Returns a dictionary mapping card names to their CardDefinition objects.
    Later sets override earlier ones if there are name conflicts.
    """
    registry = {}

    # Test sets
    registry.update(TEST_CARDS)

    # MTG Standard rotation
    registry.update(WILDS_OF_ELDRAINE_CARDS)
    registry.update(LOST_CAVERNS_IXALAN_CARDS)
    registry.update(MURDERS_KARLOV_MANOR_CARDS)
    registry.update(OUTLAWS_THUNDER_JUNCTION_CARDS)
    registry.update(BLOOMBURROW_CARDS)
    registry.update(DUSKMOURN_CARDS)
    registry.update(FOUNDATIONS_CARDS)

    # Universes Beyond
    registry.update(EDGE_OF_ETERNITIES_CARDS)
    registry.update(LORWYN_ECLIPSED_CARDS)
    registry.update(SPIDER_MAN_CARDS)
    registry.update(AVATAR_TLA_CARDS)
    registry.update(FINAL_FANTASY_CARDS)

    return registry


# Pre-built combined registry for convenience
ALL_CARDS = build_combined_registry()

__all__ = [
    # Test sets
    'TEST_CARDS',
    # MTG Standard
    'WILDS_OF_ELDRAINE_CARDS',
    'LOST_CAVERNS_IXALAN_CARDS',
    'MURDERS_KARLOV_MANOR_CARDS',
    'OUTLAWS_THUNDER_JUNCTION_CARDS',
    'BLOOMBURROW_CARDS',
    'DUSKMOURN_CARDS',
    'FOUNDATIONS_CARDS',
    # Universes Beyond
    'EDGE_OF_ETERNITIES_CARDS',
    'LORWYN_ECLIPSED_CARDS',
    'SPIDER_MAN_CARDS',
    'AVATAR_TLA_CARDS',
    'FINAL_FANTASY_CARDS',
    # Combined
    'ALL_CARDS',
    'build_combined_registry',
]
