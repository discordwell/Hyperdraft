"""Constructed Finance decks that span multiple Finance sets."""

from __future__ import annotations

from src.engine.types import CardDefinition


def _cards(names: list[tuple[str, int]]) -> list[CardDefinition]:
    from src.cards.finance import FINANCE_CARDS

    deck: list[CardDefinition] = []
    for name, count in names:
        deck.extend([FINANCE_CARDS[name]] * count)
    assert len(deck) == 40, f"Finance constructed deck has {len(deck)} cards"
    return deck


def build_voltron_premium_deck() -> list[CardDefinition]:
    """Best-of-FINA+FINM HFPM voltron deck from the FINM optimization pass."""
    return _cards([
        ("Hedge Fund PM", 4),
        ("Structured Product Builder", 4),
        ("Underlying Asset Runner", 4),
        ("Protective Put", 3),
        ("Theta Decay Trader", 2),
        ("Synthetic Collar", 2),
        ("Theta Decay Collar", 2),
        ("Gamma Amplifier", 2),
        ("Iron Condor", 2),
        ("All-In Control Premium", 2),
        ("Position Audit", 2),
        ("Forced Liquidation", 2),
        ("The Black-Scholes Model", 2),
        ("Liquidity Provision", 2),
        ("Delta Hedger", 1),
        ("Delta Neutral Wrap", 1),
        ("Cover Short", 1),
        ("Derivatives Desk Console", 1),
        ("Short Squeeze", 1),
    ])


FINANCE_CONSTRUCTED_DECKS = {
    "FINX_voltron_premium": build_voltron_premium_deck,
}


__all__ = [
    "FINANCE_CONSTRUCTED_DECKS",
    "build_voltron_premium_deck",
]
