"""MNR facility sub-set.

16 facilities themed on memory infrastructure: Mnestic Wards, Memory
Archives, Cognitive Anchors. Mostly stat-line infrastructure that buffs
specific tasks; the verbs (Antimeme, Redact, Cognitive Hazard, Mnestic
Wake) live on anomalies/personnel/procedures.

Composition (16 total):
- 1 sample (kept from scaffold) — Bystander Briefing Room (research +1)
- 6 Mnestic Wards (contain-flavored, telegraph Mnestic theme)
- 4 Memory Archives (research engines, often CL 1)
- 3 Cognitive Anchors (suppression counters to Cognitive Hazard)
- 2 utility facilities (mixed-skill, cheap curve fillers)
"""

from __future__ import annotations

from src.engine.types import CardDefinition, CardType

from .helpers import _mnr_card


# Sample card (KEEP): a baseline research facility flavored as briefing infra.
_BYSTANDER_BRIEFING_ROOM = _mnr_card(
    "MNR Bystander Briefing Room",
    CardType.SCP_FACILITY,
    bonus={"research": 1},
    red_tape=1,
    subtypes={"Briefing"},
    text="Research +1.",
    rarity="uncommon",
    archetype="mnestic_reset",
)


# ---------------------------------------------------------------------------
# Mnestic Wards (6): contain-leaning, telegraph the Mnestic theme.
# ---------------------------------------------------------------------------

_MNESTIC_WARD = _mnr_card(
    "MNR Mnestic Ward",
    CardType.SCP_FACILITY,
    bonus={"contain": 1},
    red_tape=1,
    subtypes={"Site", "Mnestic"},
    text="Mnemonics dosing station. Containment attempts get +1.",
    rarity="common",
    archetype="antimemetic",
)

_ANTIMEMETIC_QUARANTINE_LAB = _mnr_card(
    "MNR Antimemetic Quarantine Lab",
    CardType.SCP_FACILITY,
    bonus={"contain": 1, "research": 1},
    red_tape=2,
    subtypes={"Lab", "Mnestic"},
    text="Quarantine cells lined with mnestic foil. Containment and research +1.",
    rarity="uncommon",
    archetype="antimemetic",
)

_INOCULATION_BAY = _mnr_card(
    "MNR Inoculation Bay",
    CardType.SCP_FACILITY,
    bonus={"contain": 1},
    red_tape=1,
    subtypes={"Medical", "Mnestic"},
    text="Staff receive their daily mnestic dose here. Containment +1.",
    rarity="common",
    archetype="antimemetic",
)

_MNEMONIC_IMPRINT_STATION = _mnr_card(
    "MNR Mnemonic Imprint Station",
    CardType.SCP_FACILITY,
    bonus={"contain": 2},
    red_tape=2,
    subtypes={"Lab", "Mnestic"},
    text="Forced-recall harness. Mnestic protocols. Containment +2.",
    rarity="uncommon",
    archetype="antimemetic",
)

_SEALED_CONFERENCE_ROOM = _mnr_card(
    "MNR Sealed Conference Room",
    CardType.SCP_FACILITY,
    bonus={"contain": 1, "suppress": 1},
    red_tape=2,
    subtypes={"Briefing", "Mnestic"},
    text="Faraday-and-foam meeting space. Mnestic briefings only. Containment and suppression +1.",
    rarity="uncommon",
    archetype="antimemetic",
)

_DIRECTOR_AD_OFFICE = _mnr_card(
    "MNR Director's Office, AD",
    CardType.SCP_FACILITY,
    bonus={"contain": 2},
    red_tape=3,
    clearance=1,
    subtypes={"Office", "Mnestic"},
    text="The Antimemetics Director keeps the lights on. Containment +2.",
    rarity="rare",
    archetype="antimemetic",
)


# ---------------------------------------------------------------------------
# Memory Archives (4): research engines, often CL 1.
# ---------------------------------------------------------------------------

_DEEP_MEMORY_VAULT = _mnr_card(
    "MNR Deep Memory Vault",
    CardType.SCP_FACILITY,
    bonus={"research": 2},
    red_tape=3,
    clearance=1,
    subtypes={"Archive"},
    text="Sealed archive of pre-amnestic case files. Research +2.",
    rarity="rare",
    archetype="antimemetic",
)

_PRE_AMNESTIC_RECORDS = _mnr_card(
    "MNR Pre-Amnestic Records",
    CardType.SCP_FACILITY,
    bonus={"research": 2},
    red_tape=3,
    clearance=1,
    subtypes={"Archive"},
    text="Yellowing dossiers from before the wipe. Research +2.",
    rarity="rare",
    archetype="antimemetic",
)

_BLACK_BOX_LIBRARY = _mnr_card(
    "MNR Black-Box Library",
    CardType.SCP_FACILITY,
    bonus={"research": 2},
    red_tape=2,
    subtypes={"Archive"},
    text="What survives a redaction wave, in one room. Research +2.",
    rarity="uncommon",
    archetype="antimemetic",
)

_ANTIMEMETIC_ATLAS = _mnr_card(
    "MNR Antimemetic Atlas",
    CardType.SCP_FACILITY,
    bonus={"research": 1, "suppress": 1},
    red_tape=2,
    subtypes={"Archive", "Mnestic"},
    text="Charts of what we no longer remember. Research and suppression +1.",
    rarity="uncommon",
    archetype="antimemetic",
)


# ---------------------------------------------------------------------------
# Cognitive Anchors (3): suppression-focused, counter Cognitive Hazard.
# ---------------------------------------------------------------------------

_COGNITIVE_ANCHOR_ARRAY = _mnr_card(
    "MNR Cognitive Anchor Array",
    CardType.SCP_FACILITY,
    bonus={"suppress": 2},
    red_tape=2,
    subtypes={"Array"},
    text="Reality-tethered beacons. Suppression +2.",
    rarity="uncommon",
    archetype="antimemetic",
)

_REALITY_STABILIZATION_SUITE = _mnr_card(
    "MNR Reality Stabilization Suite",
    CardType.SCP_FACILITY,
    bonus={"suppress": 2},
    red_tape=3,
    clearance=1,
    subtypes={"Array"},
    text="Scranton-class anchors humming behind the walls. Suppression +2.",
    rarity="rare",
    archetype="antimemetic",
)

_BYSTANDER_BRIEFING_HALL = _mnr_card(
    "MNR Bystander Briefing Hall",
    CardType.SCP_FACILITY,
    bonus={"suppress": 1},
    red_tape=1,
    subtypes={"Briefing"},
    text="Mass briefings keep civilians cognitively anchored. Suppression +1.",
    rarity="common",
    archetype="antimemetic",
)


# ---------------------------------------------------------------------------
# Utility (2): mixed-skill, cheap curve fillers.
# ---------------------------------------------------------------------------

_JUNIOR_COORDINATION_OFFICE = _mnr_card(
    "MNR Junior Coordination Office",
    CardType.SCP_FACILITY,
    bonus={"contain": 1, "research": 1},
    red_tape=1,
    subtypes={"Office"},
    text="Junior researchers triage the day's anomalies. Containment and research +1.",
    rarity="common",
    archetype="mnestic_reset",
)

_BYSTANDER_LOUNGE = _mnr_card(
    "MNR Bystander Lounge",
    CardType.SCP_FACILITY,
    bonus={"contain": 1, "suppress": 1},
    red_tape=0,
    subtypes={"Staff"},
    text="Where staff forget what they've seen. Containment and suppression +1.",
    rarity="common",
    archetype="mnestic_reset",
)


FACILITIES: list[CardDefinition] = [
    # Sample (kept)
    _BYSTANDER_BRIEFING_ROOM,
    # Mnestic Wards (6)
    _MNESTIC_WARD,
    _ANTIMEMETIC_QUARANTINE_LAB,
    _INOCULATION_BAY,
    _MNEMONIC_IMPRINT_STATION,
    _SEALED_CONFERENCE_ROOM,
    _DIRECTOR_AD_OFFICE,
    # Memory Archives (4)
    _DEEP_MEMORY_VAULT,
    _PRE_AMNESTIC_RECORDS,
    _BLACK_BOX_LIBRARY,
    _ANTIMEMETIC_ATLAS,
    # Cognitive Anchors (3)
    _COGNITIVE_ANCHOR_ARRAY,
    _REALITY_STABILIZATION_SUITE,
    _BYSTANDER_BRIEFING_HALL,
    # Utility (2)
    _JUNIOR_COORDINATION_OFFICE,
    _BYSTANDER_LOUNGE,
]
