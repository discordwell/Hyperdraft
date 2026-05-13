"""MNR facility sub-set.

Card-design agents: populate ``FACILITIES`` with ~16 facilities. Most are
``scp_bonus``-bearing wings that buff a specific task — feel free to also
flavor them as Mnestic/antimemetic infrastructure.
"""

from __future__ import annotations

from src.engine.types import CardDefinition, CardType

from .helpers import _mnr_card


# Sample card: a baseline research facility flavored as briefing infra.
# Card-design agents replace / extend this list.
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


FACILITIES: list[CardDefinition] = [
    _BYSTANDER_BRIEFING_ROOM,
]
