"""MNR mandate sub-set.

Card-design agents: populate ``MANDATES`` with ~8 mandates. The flagship
sample below wires the new ``memory_hole`` alt-win.
"""

from __future__ import annotations

from src.engine import scp
from src.engine.types import CardDefinition, CardType

from .helpers import _with_mnr_metadata


# Sample card: validates the memory_hole alt-win end-to-end.
# Card-design agents replace / extend this list.
def _build_memory_hole_mandate() -> CardDefinition:
    card = scp.make_scp_card(
        "MNR Mandate 1: Memory Hole",
        CardType.SCP_MANDATE,
        red_tape=1,
        subtypes={"Directive", "Antimemetic"},
        text=(
            "Mandate. If 3 or more opposing anomalies are forgotten and your "
            "secrecy is 10 or greater, you win the game."
        ),
        rarity="mythic",
    )
    card.scp_alt_win = "memory_hole"
    return _with_mnr_metadata(card, archetype="mnestic_reset")


_MEMORY_HOLE_MANDATE = _build_memory_hole_mandate()


MANDATES: list[CardDefinition] = [
    _MEMORY_HOLE_MANDATE,
]
