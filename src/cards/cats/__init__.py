"""Cats — trick-taking + pile-building card game card definitions.

This package holds card definitions, decks, and Commander Cat catalogues
for the Cats engine. Engine code lives in ``src/engine/cats.py``. See
``docs/games/cats.md`` for the design.

Re-exports the CATS set (the first 60-card set):

    from src.cards.cats import ALL_CARDS, COMMANDERS, CATS_LIST,
        MOODS, SNACKS, TRINKETS
"""

from __future__ import annotations

from .CATS import (
    ALL_CARDS,
    COMMANDERS,
    CATS_LIST,
    SLEEK_CATS,
    FLUFFY_CATS,
    SCRAPPY_CATS,
    SNEAKY_CATS,
    MOODS,
    SNACKS,
    TRINKETS,
)

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
