"""ABYS starter decks for Depths balance loops."""

from __future__ import annotations

from typing import Callable

from src.engine.depths import DepthBand, FLAGSHIP_HULL
from src.engine.types import CardDefinition

from . import ABYS_CARDS
from ._mechanics import abys_vessel


def make_abys_flagship(name: str = "Abyssal Survey Flagship") -> CardDefinition:
    return abys_vessel(
        name,
        power=0,
        hull=FLAGSHIP_HULL,
        cost=None,
        subtypes={"Flagship"},
        default_depth=DepthBand.PERISCOPE,
        is_flagship=True,
        text="Flagship. Cannot dive. If sunk, you lose.",
    )


def _build(spec: list[tuple[int, str]]) -> list[CardDefinition]:
    out: list[CardDefinition] = []
    for count, name in spec:
        cd = ABYS_CARDS.get(name)
        if cd is None:
            raise KeyError(f"deck refers to unknown ABYS card: {name!r}")
        out.extend([cd] * count)
    return out


THERMALS_DECK_SPEC = [
    (4, "Vent Minnow"),
    (4, "Sulfur Skiff"),
    (3, "Warm Current Scout"),
    (3, "Black Smoker"),
    (3, "Geyser Runner"),
    (2, "Ridge Foundry"),
    (2, "Thermal Plume"),
    (2, "Rift Valve"),
    (2, "Ventfield Doctrine"),
    (2, "Superheated Lance"),
    (2, "Abyssal Turbine"),
    (1, "Admiral of the Vents"),
]

SALVAGE_DECK_SPEC = [
    (4, "Scrap Skimmer"),
    (3, "Wreck Lantern"),
    (4, "Hull Picker"),
    (3, "Patchplate Rover"),
    (3, "Bonefield Tug"),
    (2, "Prize Barge"),
    (2, "Scrapyard Drone Wave"),
    (2, "Salvage Code"),
    (2, "Tow Cable"),
    (2, "Chainhook Veteran"),
    (2, "Debris Field Scavenger"),
    (1, "Recovery Admiral Nia"),
]

LEVIATHANS_DECK_SPEC = [
    (4, "Abyss Larva"),
    (4, "Pressure Calf"),
    (3, "Blackwater Eel"),
    (3, "Trench Maw"),
    (2, "Cathedral Ray"),
    (2, "Moonless Angler"),
    (2, "Abyssal Feeding"),
    (2, "Crushfield Roar"),
    (2, "Pressure Crown"),
    (2, "Grave Current Serpent"),
    (2, "Lantern-Back Colossus"),
    (1, "Old Hundred Fathoms"),
    (1, "World-Shell Sleeper"),
]

CONVOY_DECK_SPEC = [
    (4, "Convoy Tender"),
    (4, "Wake Boat"),
    (3, "Depth-Flag Runner"),
    (3, "Masthead Sloop"),
    (3, "Twin-Line Frigate"),
    (2, "Harbor Shepherd"),
    (2, "Line Ahead Doctrine"),
    (2, "Escort Screen"),
    (2, "Hold the Route"),
    (2, "Quartermaster Sato"),
    (2, "Screen Cutter"),
    (1, "Admiral Chain-Grid"),
]

MINEFIELD_DECK_SPEC = [
    (4, "Tripwire Drone"),
    (2, "Shelf Mine"),
    (3, "Cold Pressure Mine"),
    (3, "Buoy Spotter"),
    (3, "Acoustic Sweeper"),
    (2, "Tripline Skiff"),
    (2, "Listening Net"),
    (2, "Marked for Depth Charges"),
    (2, "Mine Tender"),
    (2, "Dead Zone Cartographer"),
    (2, "Ping Cascade"),
    (2, "Mine-Layer Manta"),
    (1, "Net Captain Orlov"),
]

RESEARCH_DECK_SPEC = [
    (4, "Probe Scribe"),
    (4, "Sample Drone"),
    (3, "Bathymetry Intern"),
    (3, "Echo Graduate"),
    (3, "Wet Lab Cutter"),
    (1, "Charts and Coffee"),
    (3, "Pressure Archivist"),
    (1, "Deep Thesis"),
    (4, "Archive Submersible"),
    (2, "Final Expedition"),
    (2, "Professor Vela"),
]


def make_abys_thermals_deck() -> list[CardDefinition]:
    return _build(THERMALS_DECK_SPEC)


def make_abys_salvage_deck() -> list[CardDefinition]:
    return _build(SALVAGE_DECK_SPEC)


def make_abys_leviathans_deck() -> list[CardDefinition]:
    return _build(LEVIATHANS_DECK_SPEC)


def make_abys_convoy_deck() -> list[CardDefinition]:
    return _build(CONVOY_DECK_SPEC)


def make_abys_minefield_deck() -> list[CardDefinition]:
    return _build(MINEFIELD_DECK_SPEC)


def make_abys_research_deck() -> list[CardDefinition]:
    return _build(RESEARCH_DECK_SPEC)


ABYS_STARTER_DECKS: dict[str, Callable[[], list[CardDefinition]]] = {
    "ABYS_thermals": make_abys_thermals_deck,
    "ABYS_salvage": make_abys_salvage_deck,
    "ABYS_leviathans": make_abys_leviathans_deck,
    "ABYS_convoy": make_abys_convoy_deck,
    "ABYS_minefield": make_abys_minefield_deck,
    "ABYS_research": make_abys_research_deck,
}

__all__ = ["ABYS_STARTER_DECKS", "make_abys_flagship"]
