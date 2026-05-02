# STUB-W2: replaced at integration by W1
"""
Archetype templates for the heuristic deckbuilder.

These are pure data — no I/O, no scoring. The W1 scorer in ``scorer.py`` and
the W2 slot-filling builder consume these to drive curve, role, and
land-count targets.

The archetype name strings match the values used elsewhere in the codebase
(``standard_decks.py`` and ``netdecks.py``): "Aggro", "Control",
"Midrange", "Tempo", "Ramp". These are also the keys of
``ARCHETYPE_TEMPLATES``.

Tunable: every number in this file is an educated baseline. The W4
tournament harness and the W5 netdeck calibration are the real ground truth
— treat each value here as a knob to revisit, not a setting in stone.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ArchetypeTemplate:
    """
    Static description of an archetype's deck shape.

    Attributes:
        name: Human-readable archetype name (matches existing deck.archetype).
        curve_targets: Mapping of CMC bucket -> target nonland count.
            Bucket 6 represents "6 or more".
        role_targets: Mapping of role tag -> target count of cards with that role.
        land_count: Target number of lands in a 60-card mainboard.
        mainboard_size: Total mainboard target (60 in standard).
        sideboard_size: Sideboard target (15 in standard).
        cmc_sweet: Preferred CMC for non-land spells. Used by the scorer's curve term.
    """

    name: str
    curve_targets: dict[int, int] = field(default_factory=dict)
    role_targets: dict[str, int] = field(default_factory=dict)
    land_count: int = 24
    mainboard_size: int = 60
    sideboard_size: int = 15
    cmc_sweet: int = 3


# =============================================================================
# Templates — curve totals = mainboard_size - land_count
# =============================================================================

AGGRO = ArchetypeTemplate(
    name="Aggro",
    curve_targets={1: 10, 2: 14, 3: 8, 4: 4, 5: 2, 6: 2},
    role_targets={"removal": 4, "wincon": 8, "card_draw": 2, "utility": 4},
    land_count=20,
    cmc_sweet=2,
)

MIDRANGE = ArchetypeTemplate(
    name="Midrange",
    curve_targets={1: 4, 2: 8, 3: 10, 4: 8, 5: 4, 6: 2},
    role_targets={"removal": 6, "card_draw": 4, "wincon": 6, "utility": 4},
    land_count=24,
    cmc_sweet=3,
)

CONTROL = ArchetypeTemplate(
    name="Control",
    curve_targets={1: 2, 2: 6, 3: 8, 4: 8, 5: 6, 6: 4},
    role_targets={
        "removal": 8,
        "counterspell": 6,
        "card_draw": 8,
        "wincon": 6,
        "utility": 2,
    },
    land_count=26,
    cmc_sweet=4,
)

COMBO = ArchetypeTemplate(
    name="Combo",
    curve_targets={1: 8, 2: 12, 3: 8, 4: 4, 5: 2, 6: 2},
    role_targets={
        "card_draw": 10,
        "wincon": 4,
        "counterspell": 4,
        "ramp": 2,
        "removal": 2,
        "utility": 2,
    },
    land_count=22,
    cmc_sweet=2,
)

TEMPO = ArchetypeTemplate(
    name="Tempo",
    curve_targets={1: 8, 2: 12, 3: 8, 4: 6, 5: 2, 6: 2},
    role_targets={
        "counterspell": 4,
        "removal": 4,
        "card_draw": 4,
        "wincon": 6,
        "utility": 4,
    },
    land_count=22,
    cmc_sweet=2,
)

RAMP = ArchetypeTemplate(
    name="Ramp",
    curve_targets={1: 2, 2: 8, 3: 6, 4: 6, 5: 6, 6: 6},
    role_targets={
        "ramp": 8,
        "removal": 4,
        "card_draw": 4,
        "wincon": 6,
        "utility": 2,
    },
    land_count=26,
    cmc_sweet=5,
)


ARCHETYPE_TEMPLATES: dict[str, ArchetypeTemplate] = {
    "Aggro": AGGRO,
    "Midrange": MIDRANGE,
    "Control": CONTROL,
    "Tempo": TEMPO,
    "Ramp": RAMP,
    "Combo": COMBO,
}


def get_template(archetype: str) -> ArchetypeTemplate:
    """Look up a template by archetype name. Case-insensitive."""
    if archetype in ARCHETYPE_TEMPLATES:
        return ARCHETYPE_TEMPLATES[archetype]
    canonical = archetype.strip().capitalize()
    if canonical in ARCHETYPE_TEMPLATES:
        return ARCHETYPE_TEMPLATES[canonical]
    raise KeyError(
        f"Unknown archetype {archetype!r}. "
        f"Known: {sorted(ARCHETYPE_TEMPLATES.keys())}"
    )


__all__ = [
    "ArchetypeTemplate",
    "ARCHETYPE_TEMPLATES",
    "AGGRO",
    "MIDRANGE",
    "CONTROL",
    "TEMPO",
    "RAMP",
    "COMBO",
    "get_template",
]
