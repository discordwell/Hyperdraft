"""Mixed Depths deck registries.

This module keeps cross-set optimized decks separate from the individual
set starter lists. Starter labels stay set-prefixed (`SUBS_`, `ABYS_`);
constructed mixed lists use the `DEPTHS_` prefix.
"""

from __future__ import annotations

from typing import Callable

from src.engine.types import CardDefinition

from . import DEPTHS_CARDS
from .abyssal_expanse.decks import ABYS_STARTER_DECKS
from .submarine_fleet.decks import SUBS_STARTER_DECKS


def _build_mixed(spec: list[tuple[int, str]]) -> list[CardDefinition]:
    out: list[CardDefinition] = []
    for count, name in spec:
        cd = DEPTHS_CARDS.get(name)
        if cd is None:
            raise KeyError(f"deck refers to unknown Depths card: {name!r}")
        out.extend([cd] * count)
    return out


# Best SUBS+ABYS list from the second-stage Depths optimization pass.
# See docs/sets/DEPTHS_RESEARCH_MIDRANGE.md for tournament notes.
DEPTHS_RESEARCH_MIDRANGE_SPEC: list[tuple[int, str]] = [
    (4, "Sample Drone"),
    (4, "Probe Scribe"),
    (4, "Archive Submersible"),
    (4, "Bathymetry Intern"),
    (4, "Echo Graduate"),
    (4, "Black Smoker"),
    (3, "U-Boat Wolf-cub"),
    (3, "Surface Skirmisher"),
]


def make_depths_research_midrange_deck() -> list[CardDefinition]:
    """DEPTHS_research_midrange — ABYS Research core plus SUBS pressure."""
    return _build_mixed(DEPTHS_RESEARCH_MIDRANGE_SPEC)


DEPTHS_OPTIMIZED_DECKS: dict[str, Callable[[], list[CardDefinition]]] = {
    "DEPTHS_research_midrange": make_depths_research_midrange_deck,
}

DEPTHS_STARTER_DECKS: dict[str, Callable[[], list[CardDefinition]]] = {
    **SUBS_STARTER_DECKS,
    **ABYS_STARTER_DECKS,
    **DEPTHS_OPTIMIZED_DECKS,
}

DEPTHS_DECK_PREFIXES = ("DEPTHS_", "ABYS_", "SUBS_")


def normalize_depths_deck_label(label: str) -> str:
    """Return the registered deck key for a full key or short archetype label."""
    if label in DEPTHS_STARTER_DECKS:
        return label
    for prefix in DEPTHS_DECK_PREFIXES:
        key = f"{prefix}{label}"
        if key in DEPTHS_STARTER_DECKS:
            return key
    return f"SUBS_{label}"


def format_depths_deck_labels() -> str:
    """Return a stable, display-friendly list of all registered Depths decks."""
    return ", ".join(sorted(DEPTHS_STARTER_DECKS))


__all__ = [
    "DEPTHS_DECK_PREFIXES",
    "DEPTHS_OPTIMIZED_DECKS",
    "DEPTHS_RESEARCH_MIDRANGE_SPEC",
    "DEPTHS_STARTER_DECKS",
    "format_depths_deck_labels",
    "make_depths_research_midrange_deck",
    "normalize_depths_deck_label",
]
