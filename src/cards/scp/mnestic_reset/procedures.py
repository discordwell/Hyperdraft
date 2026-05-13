"""MNR procedure sub-set.

Card-design agents: populate ``PROCEDURES`` with ~32 procedures. Most MNR
procedures use ``_redact(N)`` as the ``effect=`` arg to ``_mnr_card`` — see
the sample below.
"""

from __future__ import annotations

from src.engine.types import CardDefinition, CardType

from .helpers import _mnr_card, _redact


# Sample card: validates the Redact verb end-to-end.
# Card-design agents replace / extend this list.
_MEMORY_TRIAGE = _mnr_card(
    "MNR Memory Triage",
    CardType.SCP_PROCEDURE,
    red_tape=1,
    subtypes={"Redaction", "Mnemonic"},
    text="Redact 1: each opponent discards a card.",
    effect=_redact(1),
    rarity="common",
    archetype="redaction_press",
)


PROCEDURES: list[CardDefinition] = [
    _MEMORY_TRIAGE,
]
