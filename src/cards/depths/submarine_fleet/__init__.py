"""SUBS — Submarine Fleet (depths engine, set 1).

Aggregates the 5 archetype card files into a single SUBS_CARDS dict and
auto-wires image_url for cards whose PNG exists on disk.
"""

from pathlib import Path

from .wolfpack import WOLFPACK_CARDS
from .silent_hunter import SILENT_HUNTER_CARDS
from .carrier import CARRIER_CARDS
from .deep_strike import DEEP_STRIKE_CARDS
from .neutral import NEUTRAL_CARDS

SUBS_CARDS: dict = {
    **WOLFPACK_CARDS,
    **SILENT_HUNTER_CARDS,
    **CARRIER_CARDS,
    **DEEP_STRIKE_CARDS,
    **NEUTRAL_CARDS,
}


_CARD_ART_DIR = Path(__file__).resolve().parents[4] / "assets" / "card_art" / "depths" / "submarine_fleet"


def _slug(name: str) -> str:
    return (
        name.lower()
        .replace("'", "")
        .replace(",", "")
        .replace(":", "")
        .replace("(", "")
        .replace(")", "")
        .replace(".", "")
        .replace("!", "")
        .replace('"', "")
        .replace(" ", "_")
        .replace("-", "_")
        .replace("__", "_")
        .strip("_")
    )


def _wire_image_urls() -> None:
    if not _CARD_ART_DIR.exists():
        return
    for name, card in SUBS_CARDS.items():
        png = _CARD_ART_DIR / f"{_slug(name)}.png"
        if png.exists() and not getattr(card, "image_url", None):
            card.image_url = f"/api/card-art/depths/submarine_fleet/{_slug(name)}.png"


_wire_image_urls()


__all__ = [
    "SUBS_CARDS",
    "WOLFPACK_CARDS",
    "SILENT_HUNTER_CARDS",
    "CARRIER_CARDS",
    "DEEP_STRIKE_CARDS",
    "NEUTRAL_CARDS",
]
