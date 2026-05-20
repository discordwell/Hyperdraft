"""CATS — first card set for the Cats engine (60 cards).

Set composition:
- 6 Commander Cats
- 30 Cat cards (8 Sleek, 8 Fluffy, 7 Scrappy, 7 Sneaky)
- 10 Mood cards
- 8 Snack cards
- 6 Trinket cards

The 60-card pool is designed for tournament starter deck construction:
draft any 30 cards (with replacement allowed for the smoke harness) plus
one Commander to build a deck.

See ``docs/games/cats.md`` for the engine design. See the individual
archetype files for card definitions and interceptor patterns.
"""

from __future__ import annotations

from .commanders import COMMANDERS
from .sleek_cats import SLEEK_CATS
from .fluffy_cats import FLUFFY_CATS
from .scrappy_cats import SCRAPPY_CATS
from .sneaky_cats import SNEAKY_CATS
from .moods import MOODS
from .snacks import SNACKS
from .trinkets import TRINKETS

CATS_LIST = SLEEK_CATS + FLUFFY_CATS + SCRAPPY_CATS + SNEAKY_CATS
ALL_CARDS = COMMANDERS + CATS_LIST + MOODS + SNACKS + TRINKETS

__all__ = [
    "ALL_CARDS",
    "COMMANDERS",
    "CATS_LIST",
    "SLEEK_CATS",
    "FLUFFY_CATS",
    "SCRAPPY_CATS",
    "SNEAKY_CATS",
    "MOODS",
    "SNACKS",
    "TRINKETS",
]
