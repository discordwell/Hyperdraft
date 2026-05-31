"""SCP: SECURE / CONTAIN / SUBVERT — card pool (asymmetric Foundation vs Chaos Insurgency).

Engine lives in ``src/engine/scp2.py`` + ``scp2_turn.py``; design in
``docs/design/scp2_rules.md``. This package holds the card definitions and starter decks.

    from src.cards.scp2 import FOUNDATION_CARDS, INSURGENCY_CARDS, ALL_CARDS
    from src.cards.scp2 import SCP2_DECKS, SCP2_FOUNDATION_DECKS, SCP2_INSURGENCY_DECKS
"""

from __future__ import annotations

from .foundation import (
    FOUNDATION_CARDS, FOUNDATION_ANOMALIES, FOUNDATION_LAYERS,
    FOUNDATION_ASSETS, FOUNDATION_OPERATIONS, FOUNDATION_IDENTITIES,
    SITE_19_COMMAND,
)
from .insurgency import (
    INSURGENCY_CARDS, INSURGENCY_OPERATIVES, INSURGENCY_TOOLS,
    INSURGENCY_EVENTS, INSURGENCY_IDENTITIES, BLACK_QUEEN_CELL,
)
from .decks import (
    SCP2_DECKS, SCP2_FOUNDATION_DECKS, SCP2_INSURGENCY_DECKS,
    site19_containment, blackfile_bait, black_queen_cell, containment_breach,
    anomaly_density, DECK_SIZE, MIN_ANOMALY_DENSITY,
)

ALL_CARDS = FOUNDATION_CARDS + INSURGENCY_CARDS

__all__ = [
    "FOUNDATION_CARDS", "FOUNDATION_ANOMALIES", "FOUNDATION_LAYERS",
    "FOUNDATION_ASSETS", "FOUNDATION_OPERATIONS", "FOUNDATION_IDENTITIES",
    "INSURGENCY_CARDS", "INSURGENCY_OPERATIVES", "INSURGENCY_TOOLS",
    "INSURGENCY_EVENTS", "INSURGENCY_IDENTITIES",
    "SITE_19_COMMAND", "BLACK_QUEEN_CELL",
    "ALL_CARDS",
    "SCP2_DECKS", "SCP2_FOUNDATION_DECKS", "SCP2_INSURGENCY_DECKS",
    "site19_containment", "blackfile_bait", "black_queen_cell", "containment_breach",
    "anomaly_density", "DECK_SIZE", "MIN_ANOMALY_DENSITY",
]
