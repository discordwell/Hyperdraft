"""
Beyond Kamigawa — Yu-Gi-Oh! cards based on MTG's Kamigawa plane.

Each archetype lives in its own module. The aggregate card registry and
deck-builders are exposed at the package level for convenience, mirroring
the layout of ``src/cards/pokemon/beyond/ravnica/``.
"""

from .samurai import BEYOND_KAMIGAWA_SAMURAI, make_samurai_deck
from .ninja import BEYOND_KAMIGAWA_NINJA, make_ninja_deck
from .spirit_dragons import BEYOND_KAMIGAWA_SPIRIT_DRAGONS, make_spirit_dragon_deck
from .moonfolk import BEYOND_KAMIGAWA_MOONFOLK, make_moonfolk_deck
from .modified import BEYOND_KAMIGAWA_MODIFIED, make_modified_deck
from .staples import BEYOND_KAMIGAWA_STAPLES


ARCHETYPE_REGISTRIES = {
    "samurai": BEYOND_KAMIGAWA_SAMURAI,
    "ninja": BEYOND_KAMIGAWA_NINJA,
    "spirit_dragons": BEYOND_KAMIGAWA_SPIRIT_DRAGONS,
    "moonfolk": BEYOND_KAMIGAWA_MOONFOLK,
    "modified": BEYOND_KAMIGAWA_MODIFIED,
}

ARCHETYPE_DECK_BUILDERS = {
    "samurai": make_samurai_deck,
    "ninja": make_ninja_deck,
    "spirit_dragons": make_spirit_dragon_deck,
    "moonfolk": make_moonfolk_deck,
    "modified": make_modified_deck,
}

# Aggregate registry — every card across all 5 archetypes plus staples.
BEYOND_KAMIGAWA_CARDS: dict = {}
for _registry in ARCHETYPE_REGISTRIES.values():
    BEYOND_KAMIGAWA_CARDS.update(_registry)
BEYOND_KAMIGAWA_CARDS.update(BEYOND_KAMIGAWA_STAPLES)


__all__ = [
    "BEYOND_KAMIGAWA_CARDS",
    "ARCHETYPE_REGISTRIES",
    "ARCHETYPE_DECK_BUILDERS",
    "BEYOND_KAMIGAWA_SAMURAI",
    "BEYOND_KAMIGAWA_NINJA",
    "BEYOND_KAMIGAWA_SPIRIT_DRAGONS",
    "BEYOND_KAMIGAWA_MOONFOLK",
    "BEYOND_KAMIGAWA_MODIFIED",
    "BEYOND_KAMIGAWA_STAPLES",
    "make_samurai_deck",
    "make_ninja_deck",
    "make_spirit_dragon_deck",
    "make_moonfolk_deck",
    "make_modified_deck",
]
