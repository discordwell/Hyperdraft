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
# Wolfpack lean — variant that cuts Saturation Strike (0/4 cast across
# /ultra-loop iters) and replaces with cheap bodies. Tests whether the
# top-end is worth slot-cost or whether pure cheap-aggro is better.
# ---------------------------------------------------------------------------

WOLFPACK_LEAN_DECK_SPEC: list[tuple[int, str]] = [
    # 1-drops (8) — same as base
    (4, "U-Boat Wolf-cub"),
    (4, "Sea Wolf Scout"),
    # 2-drops (12) — +2 Pack Runner replacing the cut Saturation Strike
    (6, "Pack Runner"),         # base 4 → 6 (replaces 2x Sat Strike)
    (3, "Coastal Raider"),
    (3, "Surface Skirmisher"),
    # 3-drops (6) — same as base
    (3, "Pack Leader U-99"),
    (3, "Type-VII Veteran"),
    # finishers (4) — Saturation Strike CUT
    (1, "Admiral Dönitz"),
    (2, "Wolfpack Doctrine"),
    (1, "Hammerhead U-505"),
]


def make_subs_wolfpack_lean_deck() -> list[CardDefinition]:
    """SUBS_wolfpack_lean — Wolfpack minus Saturation Strike (0/4 cast in
    /ultra-loop iters), +2 cheap chip-bodies. Tests the cheap-only race line."""
    return _build(WOLFPACK_LEAN_DECK_SPEC)


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
    # ---------------------------------------------------------------
    # Cycle 1 redesign — see docs/sets/SUBS.md "Archetype changelog"
    #
    # Two Stage-1 engine gaps were quietly killing the original
    # 30-card spec:
    #   (a) make_end_step_trigger / make_upkeep_trigger watch for
    #       phase=='end_step' / 'upkeep' but the depths turn manager
    #       emits 'surface' / 'dive', so every Carrier's drone-spawn
    #       trigger was a no-op (carrier.py uses depths-aware variants
    #       now);
    #   (b) the AI doesn't deploy Doctrines, so Carrier Air Wing
    #       Doctrine + Hangar Bay Doctrine never resolved (anthem
    #       effects baked onto Carriers / Crew now);
    #   (c) Action cards' cast_effect_fn is never invoked by the
    #       engine — so Drone Swarm / Kamikaze Run / Dive Bomber
    #       Squadron etc. were no-ops on cast.
    #
    # New deck leans on Vessels (ETB + on-attack triggers fire
    # reliably) and Crew (anthem stat boosts fire on attach), with
    # zero Doctrines and only one Action.
    # ---------------------------------------------------------------

    # Cheap Drone bodies (12) — 1-cost 2/1 swarmers that can attack
    # the Flagship even without a Carrier on board.
    (4, "Pilot Cadet"),
    (4, "Patrol Bomber"),       # 2/1 with homing — clean Flagship hits
    (2, "Recon Drone"),         # 1/1 with cycle-on-death (ETB-only effect)
    (2, "Skipjack Drone"),      # 2/1 with sink-spawn-Drone death trigger

    # Carriers (7) — each ETB-creates a Drone, end-phase-creates more,
    # and statically buffs Drones +0/+1 (anthem baked in).
    (4, "Escort Carrier"),         # {3T} 1/5, 1 ETB Drone + 1/turn
    (2, "Fleet Carrier \"Hiryu\""), # {4T,1S} 2/6, 2 ETB + 2/turn
    (1, "Light Carrier \"Shoho\""), # {3T} 2/4, ETB + on-attack Drone

    # Crew (5) — equipment that also serves as cheap Drone-buff anchors.
    (2, "Veteran Squadron Lead"),   # +1/+1 to your Drones (lord)
    (2, "Drone Pen Mate"),          # +1/+0 EOT to drones the host deploys
    (1, "Air-Sea Coordinator"),     # +1/+0 to all Drones at end phase

    # Mid bodies (4) — defensive Destroyers with reach to intercept aggro.
    (3, "Escort Frigate"),          # {2T} 2/2 reach
    (1, "Heavy Cruiser Escort"),    # {3T,1S} 4/4 reach

    # Finisher + sacrifice payoff (2)
    (1, "Fleet Admiral Yamamoto"),  # legendary 3/8 — three Drones/turn
    (1, "Crash-Boat Pilot"),        # attack-Flagship sac for 4 dmg
]


def make_subs_carrier_deck() -> list[CardDefinition]:
    """SUBS_carrier — wide Drone swarm + carriers (cycle 1 redesign).

    Now leans on ETB + attack triggers (which fire) instead of end-step
    triggers (broken phase name) or Doctrines (AI doesn't deploy). Drone
    bodies bumped to 2/1 base + Carrier static anthem so the AI's
    expected-damage attack threshold is met.
    """
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
    "SUBS_wolfpack_lean": make_subs_wolfpack_lean_deck,  # variant: -2 Sat Strike, +2 Pack Runner
    "SUBS_silent_hunter": make_subs_silent_hunter_deck,
    "SUBS_carrier":       make_subs_carrier_deck,
    "SUBS_deep_strike":   make_subs_deep_strike_deck,
}


__all__ = [
    "SUBS_STARTER_DECKS",
    "make_subs_wolfpack_deck",
    "make_subs_wolfpack_lean_deck",
    "make_subs_silent_hunter_deck",
    "make_subs_carrier_deck",
    "make_subs_deep_strike_deck",
    "make_subs_flagship",
]
