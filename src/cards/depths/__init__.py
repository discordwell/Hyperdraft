"""Depths engine card pools."""

from .submarine_fleet import SUBS_CARDS
from .abyssal_expanse import ABYS_CARDS

# Aggregate of all depths-engine cards.
DEPTHS_CARDS: dict = {**SUBS_CARDS, **ABYS_CARDS}

from .decks import DEPTHS_OPTIMIZED_DECKS, DEPTHS_STARTER_DECKS  # noqa: E402

__all__ = [
    "DEPTHS_CARDS",
    "SUBS_CARDS",
    "ABYS_CARDS",
    "DEPTHS_OPTIMIZED_DECKS",
    "DEPTHS_STARTER_DECKS",
]
