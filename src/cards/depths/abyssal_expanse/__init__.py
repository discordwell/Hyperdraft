"""ABYS — Abyssal Expanse (Depths expansion set 2)."""

from pathlib import Path

from .convoy import CONVOY_CARDS
from .leviathans import LEVIATHAN_CARDS
from .minefield import MINEFIELD_CARDS
from .research import RESEARCH_CARDS
from .salvage import SALVAGE_CARDS
from .thermals import THERMAL_CARDS

ABYS_CARDS: dict = {
    **THERMAL_CARDS,
    **SALVAGE_CARDS,
    **LEVIATHAN_CARDS,
    **CONVOY_CARDS,
    **MINEFIELD_CARDS,
    **RESEARCH_CARDS,
}

_CARD_ART_DIR = Path(__file__).resolve().parents[4] / "assets" / "card_art" / "depths" / "abyssal_expanse"


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
    for name, card in ABYS_CARDS.items():
        png = _CARD_ART_DIR / f"{_slug(name)}.png"
        if png.exists() and not getattr(card, "image_url", None):
            card.image_url = f"/api/card-art/depths/abyssal_expanse/{_slug(name)}.png"


_wire_image_urls()

__all__ = [
    "ABYS_CARDS",
    "THERMAL_CARDS",
    "SALVAGE_CARDS",
    "LEVIATHAN_CARDS",
    "CONVOY_CARDS",
    "MINEFIELD_CARDS",
    "RESEARCH_CARDS",
]
