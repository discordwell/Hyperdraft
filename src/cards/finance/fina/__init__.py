"""FINA — Finance TCG Set 1 (Quant & IB). Aggregating module."""

from .high_frequency import HIGH_FREQUENCY_CARDS
from .derivatives import DERIVATIVES_CARDS
from .quant import QUANT_CARDS
from .dark_arbitrage import DARK_ARBITRAGE_CARDS
from .decks import (
    build_high_frequency_deck,
    build_derivatives_deck,
    build_quant_deck,
    build_dark_arbitrage_deck,
    FINA_STARTER_DECKS,
)

FINA_CARDS: dict = {
    **HIGH_FREQUENCY_CARDS,
    **DERIVATIVES_CARDS,
    **QUANT_CARDS,
    **DARK_ARBITRAGE_CARDS,
}

assert len(FINA_CARDS) == 151, (  # rebalance: +1 — added Forced Liquidation (DA)
    f"FINA set should have 151 cards, got {len(FINA_CARDS)}. "
    f"HF={len(HIGH_FREQUENCY_CARDS)} DV={len(DERIVATIVES_CARDS)} "
    f"QT={len(QUANT_CARDS)} DA={len(DARK_ARBITRAGE_CARDS)}"
)

__all__ = [
    "FINA_CARDS",
    "HIGH_FREQUENCY_CARDS",
    "DERIVATIVES_CARDS",
    "QUANT_CARDS",
    "DARK_ARBITRAGE_CARDS",
]
