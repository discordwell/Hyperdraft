"""
SUBS starter decks — one per archetype.

Deck labels (LOAD-BEARING for balance loop): `SUBS_<archetype>` so
`scripts/new_set/balance_loop.py` and `coverage.py` can filter the
tournament JSON via `domain_matches_set("SUBS", ...)`.

Each builder returns a list[CardDefinition] of 30 cards. The Flagship
is provided separately by the test/tournament harness via
`setup_depths_player(game, player, deck, flagship_def)`.
"""

from __future__ import annotations

from typing import Callable

from src.engine.types import CardDefinition, Characteristics, CardType

from . import (
    SUBS_CARDS,
    WOLFPACK_CARDS,
    SILENT_HUNTER_CARDS,
    CARRIER_CARDS,
    DEEP_STRIKE_CARDS,
    NEUTRAL_CARDS,
)
from ._factories import make_vessel
from src.engine.depths import DepthBand, FLAGSHIP_HULL


# ---------------------------------------------------------------------------
# Generic Flagship CardDefinition — shared across all four decks.
# ---------------------------------------------------------------------------

def make_subs_flagship(name: str = "Battleship Flagship") -> CardDefinition:
    """Default Flagship Vessel passed to setup_depths_player.

    Power 0 (Flagships don't attack), hull = FLAGSHIP_HULL (25), locked
    at PERISCOPE.
    """
    return make_vessel(
        name=name,
        power=0,
        hull=FLAGSHIP_HULL,
        cost=None,                              # not cast from hand
        subtypes={"Flagship"},
        default_depth=DepthBand.PERISCOPE,
        is_flagship=True,
        text="Flagship. Cannot dive. If sunk, you lose.",
    )


# ---------------------------------------------------------------------------
# Internal helper: turn a list of (count, name) into a list of CardDefinitions
# ---------------------------------------------------------------------------

def _build(spec: list[tuple[int, str]]) -> list[CardDefinition]:
    """`spec = [(count, name), ...]` → flat list, validating each name."""
    out: list[CardDefinition] = []
    for count, name in spec:
        cd = SUBS_CARDS.get(name)
        if cd is None:
            raise KeyError(f"deck refers to unknown SUBS card: {name!r}")
        out.extend([cd] * count)
    return out


# ---------------------------------------------------------------------------
# Wolfpack — fast aggro
# ---------------------------------------------------------------------------

WOLFPACK_DECK_SPEC: list[tuple[int, str]] = [
    # 1-drops (8)
    (4, "U-Boat Wolf-cub"),
    (4, "Sea Wolf Scout"),
    # 2-drops (10)
    (4, "Pack Runner"),
    (3, "Coastal Raider"),
    (3, "Surface Skirmisher"),
    # 3-drops (6)
    (3, "Pack Leader U-99"),
    (3, "Type-VII Veteran"),
    # finishers + actions (6)
    (1, "Admiral Dönitz"),
    (2, "Saturation Strike"),
    (2, "Wolfpack Doctrine"),
    (1, "Hammerhead U-505"),
]


def make_subs_wolfpack_deck() -> list[CardDefinition]:
    """SUBS_wolfpack — go-wide submarine aggro."""
    return _build(WOLFPACK_DECK_SPEC)


# ---------------------------------------------------------------------------
# Silent Hunter — stealth/control
# ---------------------------------------------------------------------------

SILENT_HUNTER_DECK_SPEC: list[tuple[int, str]] = [
    # 1-drops (6)
    (4, "Periscope Recon"),
    (2, "Listening Post"),
    # 2-drops (10)
    (4, "Stalker Sub"),
    (3, "Bottom-Crawler Probe"),
    (3, "U-Class Stalker"),
    # 3-drops (6)
    (3, "Diesel Whisper"),
    (3, "Snorkel Stalker"),
    # mid+actions (8)
    (2, "Wolf at the Door"),
    (2, "Type-XXI Phantom"),
    (2, "Iron Discipline"),
    (2, "Sonar Jammer"),
]


def make_subs_silent_hunter_deck() -> list[CardDefinition]:
    """SUBS_silent_hunter — DEEP-band stealth attrition."""
    return _build(SILENT_HUNTER_DECK_SPEC)


# ---------------------------------------------------------------------------
# Carrier — Drone swarm
# ---------------------------------------------------------------------------

CARRIER_DECK_SPEC: list[tuple[int, str]] = [
    # cheap drones / destroyers (10)
    (4, "Pilot Cadet"),
    (3, "Recon Drone"),
    (3, "Patrol Bomber"),
    # carriers (8)
    (4, "Escort Carrier"),
    (2, "Fleet Carrier \"Hiryu\""),
    (2, "Light Carrier \"Shoho\""),
    # support (6)
    (2, "Drone Swarm"),
    (2, "Carrier Air Wing Doctrine"),
    (2, "Kamikaze Run"),
    # finishers + escort (6)
    (1, "Fleet Admiral Yamamoto"),
    (3, "Escort Frigate"),
    (2, "Anti-Sub Drone"),
]


def make_subs_carrier_deck() -> list[CardDefinition]:
    """SUBS_carrier — wide Drone swarm + carriers."""
    return _build(CARRIER_DECK_SPEC)


# ---------------------------------------------------------------------------
# Deep-Strike — combo finisher
# ---------------------------------------------------------------------------

DEEP_STRIKE_DECK_SPEC: list[tuple[int, str]] = [
    # cheap defense / sonar early (8)
    (4, "Bathyscaphe Mite"),
    (4, "Pressure Probe"),
    # mid-curve deep vessels (8)
    (3, "Salvage Diver"),
    (3, "Deep-Lurker"),
    (2, "Pressure Hull Veteran"),
    # finishers (4)
    (2, "Black Demon X-7"),
    (2, "Triton-Class"),
    # support / payoffs (10)
    (3, "Crush-Depth Doctrine"),
    (2, "Battery Reroute"),
    (3, "Crush-Depth Charges"),
    (2, "Coelacanth Class"),
]


def make_subs_deep_strike_deck() -> list[CardDefinition]:
    """SUBS_deep_strike — stall, hoard SC, dive a finisher."""
    return _build(DEEP_STRIKE_DECK_SPEC)


# ---------------------------------------------------------------------------
# Public registry
# ---------------------------------------------------------------------------

SUBS_STARTER_DECKS: dict[str, Callable[[], list[CardDefinition]]] = {
    "SUBS_wolfpack":      make_subs_wolfpack_deck,
    "SUBS_silent_hunter": make_subs_silent_hunter_deck,
    "SUBS_carrier":       make_subs_carrier_deck,
    "SUBS_deep_strike":   make_subs_deep_strike_deck,
}


__all__ = [
    "SUBS_STARTER_DECKS",
    "make_subs_wolfpack_deck",
    "make_subs_silent_hunter_deck",
    "make_subs_carrier_deck",
    "make_subs_deep_strike_deck",
    "make_subs_flagship",
]
