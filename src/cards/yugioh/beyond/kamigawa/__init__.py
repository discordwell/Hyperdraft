"""
Beyond Kamigawa — Yu-Gi-Oh! cards based on MTG's Kamigawa plane.

Each archetype lives in its own module. The aggregate card registry and
deck-builders are exposed at the package level for convenience, mirroring
the layout of ``src/cards/pokemon/beyond/ravnica/``.
"""

from .samurai import BEYOND_KAMIGAWA_SAMURAI, make_samurai_deck
from .ninja import BEYOND_KAMIGAWA_NINJA, make_ninja_deck
from .spirit_dragons import BEYOND_KAMIGAWA_SPIRIT_DRAGONS, make_spirit_dragon_deck
from .moonfolk import BEYOND_KAMIGAWA_MOONFOLK, make_moonfolk_deck
from .modified import BEYOND_KAMIGAWA_MODIFIED, make_modified_deck
from .staples import BEYOND_KAMIGAWA_STAPLES
from .balance import kamigawa_balance_flags, kamigawa_balance_summary


ARCHETYPE_REGISTRIES = {
    "samurai": BEYOND_KAMIGAWA_SAMURAI,
    "ninja": BEYOND_KAMIGAWA_NINJA,
    "spirit_dragons": BEYOND_KAMIGAWA_SPIRIT_DRAGONS,
    "moonfolk": BEYOND_KAMIGAWA_MOONFOLK,
    "modified": BEYOND_KAMIGAWA_MODIFIED,
}

ARCHETYPE_DECK_BUILDERS = {
    "samurai": make_samurai_deck,
    "ninja": make_ninja_deck,
    "spirit_dragons": make_spirit_dragon_deck,
    "moonfolk": make_moonfolk_deck,
    "modified": make_modified_deck,
}

# Aggregate registry — every card across all 5 archetypes plus staples.
BEYOND_KAMIGAWA_CARDS: dict = {}
for _registry in ARCHETYPE_REGISTRIES.values():
    BEYOND_KAMIGAWA_CARDS.update(_registry)
BEYOND_KAMIGAWA_CARDS.update(BEYOND_KAMIGAWA_STAPLES)


# =============================================================================
# Image-URL auto-wiring
# =============================================================================
# Patches each card's ``image_url`` to point at its rendered PNG under
# ``assets/card_art/beyond/kamigawa/<slug>.png`` (served by the FastAPI
# server at ``/api/card-art/beyond/kamigawa/<slug>.png``). Only sets the
# field when the PNG actually exists, so cards without art yet keep
# ``image_url=None`` and the frontend falls through to its other lookups.
#
# Slug rule MUST match scripts/beyond_kamigawa/generate_card_art.py:to_filename.

import pathlib as _pathlib

_BK_ART_DIR = (_pathlib.Path(__file__).resolve().parents[5]
               / "assets" / "card_art" / "beyond" / "kamigawa")
_BK_ART_URL_BASE = "/api/card-art/beyond/kamigawa"


def _bk_slug(name: str) -> str:
    return (
        name.lower()
        .replace("'", "")
        .replace(",", "")
        .replace(":", "")
        .replace("(", "")
        .replace(")", "")
        .replace(" ", "_")
        .replace("-", "_")
        .replace("__", "_")
        .strip("_")
    )


def _wire_image_urls() -> int:
    """Set ``image_url`` on each BK card whose PNG exists on disk.

    Idempotent — already-set ``image_url`` values are preserved. Returns
    the number of cards wired (useful for tests / verification scripts).
    """
    if not _BK_ART_DIR.exists():
        return 0
    wired = 0
    for name, card_def in BEYOND_KAMIGAWA_CARDS.items():
        if getattr(card_def, "image_url", None):
            continue
        slug = _bk_slug(name)
        if (_BK_ART_DIR / f"{slug}.png").exists():
            card_def.image_url = f"{_BK_ART_URL_BASE}/{slug}.png"
            wired += 1
    return wired


_WIRED_IMAGE_URLS = _wire_image_urls()


__all__ = [
    "BEYOND_KAMIGAWA_CARDS",
    "ARCHETYPE_REGISTRIES",
    "ARCHETYPE_DECK_BUILDERS",
    "BEYOND_KAMIGAWA_SAMURAI",
    "BEYOND_KAMIGAWA_NINJA",
    "BEYOND_KAMIGAWA_SPIRIT_DRAGONS",
    "BEYOND_KAMIGAWA_MOONFOLK",
    "BEYOND_KAMIGAWA_MODIFIED",
    "BEYOND_KAMIGAWA_STAPLES",
    "kamigawa_balance_flags",
    "kamigawa_balance_summary",
    "make_samurai_deck",
    "make_ninja_deck",
    "make_spirit_dragon_deck",
    "make_moonfolk_deck",
    "make_modified_deck",
]
