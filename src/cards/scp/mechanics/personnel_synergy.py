"""Subtype-lord auras for SCP personnel.

Each personnel card here gains a ``scp_aura`` dict consumed by
``src.engine.scp._staff_total``. The aura applies to FRIENDLY personnel on the
same battlefield that match the selector. The aura source counts itself when
its own subtypes match the selector (e.g. the Memetics Analyst is itself a
Memetics personnel, so a ``"subtype:Memetics"`` aura buffs the analyst as well
as other Memetics teammates).

Two selector forms are supported by the engine:

  - ``"subtype:X"`` — applies when the buffed personnel's subtypes include X.
  - ``"any"`` — applies to every friendly personnel on the battlefield.

Each value is a per-task delta dict::

    {"research": 1, "suppress": 1}

This module also rewrites the assigned cards' ``text`` so the printed rules
describe the lord effect instead of pure flavor.

NOTES on flavor-implied quirks not wired here:

  - ``Janitor Who Knows Too Much`` and ``Sleep-Deprived Intern`` both imply
    "stops alarms before anyone notices" / "somehow always available" effects
    that ideally fire on incident-tick or staff-reset. The current engine
    exposes only ``scp_on_reveal`` / ``scp_on_test`` / ``scp_on_test_fail`` on
    anomalies, and ``scp_aura`` on personnel. There is no ``scp_on_assign`` or
    personnel-side incident hook. Wiring those quirks beyond the aura would
    require a new hook owned by the engine, which is out of W4's scope. Leave
    them to a future personnel-trigger pass.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine.types import CardDefinition


# ---------------------------------------------------------------------------
# CORE personnel auras (11 named CORE cards from src/cards/scp/__init__.py:304).
# ---------------------------------------------------------------------------

_CORE_AURAS: dict[str, tuple[dict[str, dict[str, int]], str]] = {
    "Junior Researcher": (
        {"subtype:Scientist": {"research": 1}},
        "Research 1. Other Scientist personnel get +1 research.",
    ),
    "Containment Specialist": (
        {"subtype:Security": {"contain": 1}},
        "Contain 2, suppress 1. Other Security personnel get +1 contain.",
    ),
    "MTF Doorbreaker": (
        {"subtype:Security": {"contain": 1, "suppress": 1}},
        "Contain 3, suppress 1. Other Security personnel get +1 contain and +1 suppress.",
    ),
    "Memetics Analyst": (
        {
            "subtype:Memetics": {"research": 1},
            "subtype:Scientist": {"research": 1},
        },
        "Research 2, suppress 1. Memetics and Scientist personnel each get +1 research (stacks on Memetics Scientists).",
    ),
    "Ethics Liaison": (
        {"subtype:Ethics": {"suppress": 1}},
        "Research 1, suppress 2. Other Ethics personnel get +1 suppress.",
    ),
    "O5 Auditor": (
        {"any": {"research": 1}},
        "Research 3, contain 1. Every friendly personnel gets +1 research.",
    ),
    "Field Agent": (
        {"subtype:Agent": {"suppress": 1}},
        "Contain 1, research 1, suppress 2. Other Agent personnel get +1 suppress.",
    ),
    "Thaumic Consultant": (
        {"subtype:Occult": {"research": 1}},
        "Research 2, contain 2. Other Occult personnel get +1 research.",
    ),
    "Night Shift Archivist": (
        {"subtype:Archivist": {"research": 1}},
        "Research 3. Other Archivist personnel get +1 research.",
    ),
    "Janitor Who Knows Too Much": (
        {"subtype:Staff": {"suppress": 1}},
        "Contain 1, suppress 3. Other Staff personnel get +1 suppress.",
    ),
    "D-Class Volunteer": (
        {"subtype:D-Class": {"contain": 1, "research": 1, "suppress": 1}},
        "Contain 1, research 1, suppress 1. Other D-Class personnel get +1 to every task.",
    ),
}


# ---------------------------------------------------------------------------
# Expansion hero auras. Heroes are named "{CODE} Hero - {Name}" and built in
# src/cards/scp/__init__.py:665 via expansion["heroes"]. All 6 heroes per
# expansion share an aura template tied to that expansion's primary subtype.
# ---------------------------------------------------------------------------

_EXPANSION_HERO_AURAS: dict[str, tuple[dict[str, dict[str, int]], str]] = {
    "ACW": (
        {"subtype:Antimemetic": {"research": 1}},
        "Other Antimemetic personnel get +1 research.",
    ),
    "KBO": (
        {"subtype:Keter": {"contain": 1}},
        "Other Keter personnel get +1 contain.",
    ),
    "GOI": (
        {"subtype:GOI": {"suppress": 1}},
        "Other GOI personnel get +1 suppress.",
    ),
    "ETH": (
        {"subtype:Ethics": {"research": 1}},
        "Other Ethics personnel get +1 research.",
    ),
    "OAR": (
        {"subtype:Dream": {"research": 1}},
        "Other Dream personnel get +1 research.",
    ),
}


# Hero name lists per expansion, matching SCP_EXPANSIONS in src/cards/scp/__init__.py.
_EXPANSION_HEROES: dict[str, list[str]] = {
    "ACW": [
        "Director Ana Vale", "Dr. Kovacs of the Blank Wing", "Agent No-Name", "Archivist Lumen Rye",
        "Professor Hester Quill", "O5-Null", "Mara Voss, Mnestic Surgeon", "Captain Erasure Bell",
    ],
    "KBO": [
        "Commander Slate Rook", "Dr. Mira Lock", "O5-Blackout", "Captain Ferro Kane",
        "Warden Vela Cross", "Chief Sato Lastdoor", "Ada Pike, Breach Marshal", "Rook Team Helix",
    ],
    "GOI": [
        "Agent Felicity Graves", "Marshal Rane Cross", "Serpent Speaker Ilya", "The Defector in Blue",
        "Quartermaster Hex", "Dr. Sel Orison", "O5-Interdiction", "Captain Crowbar Venn",
    ],
    "ETH": [
        "Chairwoman Inez Salt", "Dr. Gideon Vale", "O5-Conscience", "Nurse Patel of Ward Zero",
        "Mediator June Frost", "D-0001, Volunteer King", "Auditor Sol Mercer", "Sister Redline",
    ],
    "OAR": [
        "Dr. Somna Reed", "Agent Lucid Marr", "O5-Dreaming", "The Sleepless Child",
        "Archivist Yarrow Night", "Captain Nora REM", "Professor Glass Pillow", "Warden Hypnos Vale",
    ],
}


def apply_personnel_synergy(cards: "dict[str, CardDefinition]") -> None:
    """Wire ``scp_aura`` (and rules-text) on CORE personnel + expansion heroes.

    Mutates the card pool in place. Safe to call once after the SCP card pool
    is constructed (see ``src/cards/scp/mechanics/__init__.py``). Idempotent —
    re-running just re-sets the same dict, so re-imports are harmless.
    """

    # 1. CORE personnel: 11 named lords.
    for name, (aura, text) in _CORE_AURAS.items():
        card = cards.get(name)
        if card is None:
            continue
        card.scp_aura = dict(aura)
        card.text = text

    # 2. Expansion heroes: 6 per expansion (the first 6 of the 8 hero names
    #    in SCP_EXPANSIONS get hero cards via the index-range(6) loop in
    #    _build_expansion_cards at __init__.py:665 — but in the current
    #    generator that loop ranges over the FULL hero list, so all 8 heroes
    #    per expansion exist. The task spec says "6 per expansion" but the
    #    generator emits all 8; we apply auras to ALL heroes we find since
    #    the aura is by design uniform within an expansion).
    for code, (aura, aura_text) in _EXPANSION_HERO_AURAS.items():
        for hero_name in _EXPANSION_HEROES[code]:
            card_name = f"{code} Hero - {hero_name}"
            card = cards.get(card_name)
            if card is None:
                continue
            card.scp_aura = dict(aura)
            # Hero text: keep the combo-piece framing but add the aura clause.
            base_skills = getattr(card, "scp_skills", {}) or {}
            skill_summary = ", ".join(
                f"{task} {value}" for task, value in sorted(base_skills.items()) if value
            )
            if skill_summary:
                card.text = f"Hero ({skill_summary}). {aura_text}"
            else:
                card.text = aura_text
