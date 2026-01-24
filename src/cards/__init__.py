# Card definitions
"""
Card Registry Module

Exports all card registries from the different sets.
"""

from .edge_of_eternities import EDGE_OF_ETERNITIES_CARDS
from .avatar_tla import AVATAR_TLA_CARDS
from .lorwyn_eclipsed import LORWYN_ECLIPSED_CARDS
from .spider_man import SPIDER_MAN_CARDS
from .test_cards import TEST_CARDS


def build_combined_registry() -> dict:
    """
    Build a combined card registry from all sets.

    Returns a dictionary mapping card names to their CardDefinition objects.
    Later sets override earlier ones if there are name conflicts.
    """
    registry = {}

    # Add all sets to the registry
    registry.update(TEST_CARDS)
    registry.update(EDGE_OF_ETERNITIES_CARDS)
    registry.update(AVATAR_TLA_CARDS)
    registry.update(LORWYN_ECLIPSED_CARDS)
    registry.update(SPIDER_MAN_CARDS)

    return registry


# Pre-built combined registry for convenience
ALL_CARDS = build_combined_registry()

__all__ = [
    'EDGE_OF_ETERNITIES_CARDS',
    'AVATAR_TLA_CARDS',
    'LORWYN_ECLIPSED_CARDS',
    'SPIDER_MAN_CARDS',
    'TEST_CARDS',
    'ALL_CARDS',
    'build_combined_registry',
]
