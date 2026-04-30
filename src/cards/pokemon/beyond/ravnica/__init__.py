"""
Beyond Ravnica — Pokemon-style cards based on MTG's Ravnica plane.

Each guild lives in its own module. The aggregate card registry and
deck-builders are exposed at the package level for convenience.
"""

from .azorius import BEYOND_RAVNICA_AZORIUS, make_azorius_deck
from .boros import BEYOND_RAVNICA_BOROS, make_boros_deck
from .dimir import BEYOND_RAVNICA_DIMIR, make_dimir_deck
from .golgari import BEYOND_RAVNICA_GOLGARI, make_golgari_deck
from .gruul import BEYOND_RAVNICA_GRUUL, make_gruul_deck
from .izzet import (
    BEYOND_RAVNICA_IZZET,
    NIVLET, MIZZLING, NIV_MIZZET_PARUN_EX,
    GOBLIN_ELECTROMANCER, MERCURIAL_MAGELING,
    NIV_MIZZETS_TOWER, RAL_STORM_CONDUIT, IZZET_SIGNET,
    make_izzet_deck,
)
from .orzhov import BEYOND_RAVNICA_ORZHOV, make_orzhov_deck
from .rakdos import BEYOND_RAVNICA_RAKDOS, make_rakdos_deck
from .selesnya import BEYOND_RAVNICA_SELESNYA, make_selesnya_deck
from .simic import BEYOND_RAVNICA_SIMIC, make_simic_deck


GUILD_REGISTRIES = {
    "azorius": BEYOND_RAVNICA_AZORIUS,
    "boros": BEYOND_RAVNICA_BOROS,
    "dimir": BEYOND_RAVNICA_DIMIR,
    "golgari": BEYOND_RAVNICA_GOLGARI,
    "gruul": BEYOND_RAVNICA_GRUUL,
    "izzet": BEYOND_RAVNICA_IZZET,
    "orzhov": BEYOND_RAVNICA_ORZHOV,
    "rakdos": BEYOND_RAVNICA_RAKDOS,
    "selesnya": BEYOND_RAVNICA_SELESNYA,
    "simic": BEYOND_RAVNICA_SIMIC,
}

GUILD_DECK_BUILDERS = {
    "azorius": make_azorius_deck,
    "boros": make_boros_deck,
    "dimir": make_dimir_deck,
    "golgari": make_golgari_deck,
    "gruul": make_gruul_deck,
    "izzet": make_izzet_deck,
    "orzhov": make_orzhov_deck,
    "rakdos": make_rakdos_deck,
    "selesnya": make_selesnya_deck,
    "simic": make_simic_deck,
}

# Aggregate registry — every card across all 10 guilds.
BEYOND_RAVNICA_CARDS = {}
for _registry in GUILD_REGISTRIES.values():
    BEYOND_RAVNICA_CARDS.update(_registry)


__all__ = [
    "BEYOND_RAVNICA_CARDS",
    "GUILD_REGISTRIES",
    "GUILD_DECK_BUILDERS",
    # Per-guild registries
    "BEYOND_RAVNICA_AZORIUS",
    "BEYOND_RAVNICA_BOROS",
    "BEYOND_RAVNICA_DIMIR",
    "BEYOND_RAVNICA_GOLGARI",
    "BEYOND_RAVNICA_GRUUL",
    "BEYOND_RAVNICA_IZZET",
    "BEYOND_RAVNICA_ORZHOV",
    "BEYOND_RAVNICA_RAKDOS",
    "BEYOND_RAVNICA_SELESNYA",
    "BEYOND_RAVNICA_SIMIC",
    # Per-guild deck builders
    "make_azorius_deck",
    "make_boros_deck",
    "make_dimir_deck",
    "make_golgari_deck",
    "make_gruul_deck",
    "make_izzet_deck",
    "make_orzhov_deck",
    "make_rakdos_deck",
    "make_selesnya_deck",
    "make_simic_deck",
]
