# Card definitions
"""
Card Registry Module

Exports all card registries from the different sets.
"""

from .edge_of_eternities import EDGE_OF_ETERNITIES_CARDS
from .avatar_tla import AVATAR_TLA_CARDS
from .lorwyn_eclipsed import LORWYN_ECLIPSED_CARDS
from .spider_man import SPIDER_MAN_CARDS
from .star_wars import STAR_WARS_CARDS
from .demon_slayer import DEMON_SLAYER_CARDS
from .one_piece import ONE_PIECE_CARDS
from .pokemon_horizons import POKEMON_HORIZONS_CARDS
from .legend_of_zelda import LEGEND_OF_ZELDA_CARDS
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
    registry.update(STAR_WARS_CARDS)
    registry.update(DEMON_SLAYER_CARDS)
    registry.update(ONE_PIECE_CARDS)
    registry.update(POKEMON_HORIZONS_CARDS)
    registry.update(LEGEND_OF_ZELDA_CARDS)

    return registry


# Pre-built combined registry for convenience
ALL_CARDS = build_combined_registry()

__all__ = [
    'EDGE_OF_ETERNITIES_CARDS',
    'AVATAR_TLA_CARDS',
    'LORWYN_ECLIPSED_CARDS',
    'SPIDER_MAN_CARDS',
    'STAR_WARS_CARDS',
    'DEMON_SLAYER_CARDS',
    'ONE_PIECE_CARDS',
    'POKEMON_HORIZONS_CARDS',
    'LEGEND_OF_ZELDA_CARDS',
    'TEST_CARDS',
    'ALL_CARDS',
    'build_combined_registry',
]
