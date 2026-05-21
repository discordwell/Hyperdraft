"""
Unit tests for the Finance card-art URL builder.

`_finance_image_url` in `src/server/session.py` is what plumbs Finance card
PNGs through CardData.image_url to the frontend renderer. These tests pin
the slug + subset behaviour so the renderer's URL pattern stays stable.

Files live at assets/card_art/finance/<subset>/<slug>.png and are served
under /api/card-art/finance/<subset>/<slug>.png — those are the exact
strings the frontend's <img> tag will hit.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.server.session import _finance_image_url  # noqa: E402
from src.engine.types import (  # noqa: E402
    CardDefinition,
    Characteristics,
    CardType,
)


def _stub_card(name: str, domain: str = "FINA") -> CardDefinition:
    chars = Characteristics(
        types={CardType.FIN_TRADER},
        subtypes={"Trader"},
        power=1,
        toughness=1,
        mana_cost="{1}",
    )
    return CardDefinition(
        name=name,
        mana_cost="{1}",
        characteristics=chars,
        domain=domain,
        text="",
    )


def test_finance_image_url_basic_slug() -> None:
    card = _stub_card("Flash Crash Bot")
    assert (
        _finance_image_url(card, card.name)
        == "/api/card-art/finance/fina/flash_crash_bot.png"
    )


def test_finance_image_url_strips_punctuation() -> None:
    """Apostrophes and commas should collapse to underscores."""
    card = _stub_card("Trader's Edge, Inc.")
    url = _finance_image_url(card, card.name)
    # The slug regex collapses all non-alphanumeric runs into single '_',
    # then strips leading/trailing — so the trailing period becomes nothing.
    assert url == "/api/card-art/finance/fina/trader_s_edge_inc.png"


def test_finance_image_url_finm_domain() -> None:
    card = _stub_card("Acme Holdings", domain="FINM")
    assert (
        _finance_image_url(card, card.name)
        == "/api/card-art/finance/finm/acme_holdings.png"
    )


def test_finance_image_url_unknown_domain_falls_back_to_fina() -> None:
    """Unknown / TOKEN domains default to fina/ — currently the only folder
    with art on disk."""
    card = _stub_card("Mystery Token", domain="TOKEN")
    assert (
        _finance_image_url(card, card.name)
        == "/api/card-art/finance/fina/mystery_token.png"
    )


def test_finance_image_url_handles_missing_card_def() -> None:
    """Token / synthesized cards may have no card_def — must not crash."""
    assert (
        _finance_image_url(None, "Spawned Trader Token")
        == "/api/card-art/finance/fina/spawned_trader_token.png"
    )


def test_finance_image_url_returns_none_for_empty_name() -> None:
    assert _finance_image_url(None, "") is None
    # An all-punctuation name slugifies to empty after stripping underscores.
    assert _finance_image_url(None, "...") is None


if __name__ == "__main__":
    # Run directly: python tests/test_finance_image_url.py
    test_finance_image_url_basic_slug()
    test_finance_image_url_strips_punctuation()
    test_finance_image_url_finm_domain()
    test_finance_image_url_unknown_domain_falls_back_to_fina()
    test_finance_image_url_handles_missing_card_def()
    test_finance_image_url_returns_none_for_empty_name()
    print("ok")
