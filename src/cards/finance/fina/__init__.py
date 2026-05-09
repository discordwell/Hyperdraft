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

assert len(FINA_CARDS) == 161, (
    # rebalance v2 (2026-05-09): +5 voltron-meta answers + burn seed:
    #   - DERIVATIVES (+2): Position Audit, Liquidation Cascade
    #   - DARK_ARBITRAGE (+2): Forced Unwinding, Margin Squeeze
    #   - HIGH_FREQUENCY (+1): Capital Skimmer
    # rebalance v3a (2026-05-09): +1 Wrath-of-God-tier Trader sweeper
    #   - QUANT (+1): Black Monday {4} destroy all Traders
    # rebalance v3b (2026-05-09): +4 HF-aggro / Burn pinnacle pieces
    #   - HIGH_FREQUENCY (+4): Tick Sniper {1} 2/1 Alpha Strike,
    #     Capital Skim {1} 1-dmg burn, Volatility Bomb {2} 3-dmg Bolt analog,
    #     Cascading Liquidations {3} graveyard-Trader-count finisher (max 6)
    f"FINA set should have 161 cards, got {len(FINA_CARDS)}. "
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
