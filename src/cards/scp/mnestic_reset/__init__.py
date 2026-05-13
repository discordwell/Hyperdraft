"""Mnestic Reset (MNR) expansion package.

Five interlocking verbs based on qntm's *There Is No Antimemetics Division*:

- **Mnestic** — personnel tag that shields a Site from antimemes.
- **Antimeme N** — anomalies decay each end-of-turn unless a Mnestic
  personnel is in play; at N forget counters, they are removed from history
  (``state.scp_forgotten``).
- **Redact N** — opponent discard + retroactive event tag.
- **Cognitive Hazard X** — opposing-turn hand drain (suppressed by Mnestic).
- **Mnestic Wake** — activated ability that grants Mnestic mid-game.

Sub-modules each own one card category; ``MNR_CARDS`` is the union exported
into ``src/cards/scp/__init__.py`` and stitched onto ``SCP_CARDS``.
"""

from __future__ import annotations

from src.engine.types import CardDefinition

from .anomalies import ANOMALIES
from .facilities import FACILITIES
from .helpers import (
    EXPANSION,
    EXPANSION_CODE,
    _antimeme,
    _cog_hazard,
    _mnestic_personnel,
    _mnestic_wake_ability,
    _mnr_card,
    _redact,
    _with_mnr_metadata,
)
from .mandates import MANDATES
from .personnel import PERSONNEL
from .procedures import PROCEDURES
from .szb_callbacks import CALLBACKS


_ALL_LISTS = [ANOMALIES, PERSONNEL, FACILITIES, PROCEDURES, MANDATES, CALLBACKS]


MNR_CARDS: dict[str, CardDefinition] = {
    card.name: card for sub in _ALL_LISTS for card in sub
}


__all__ = [
    "EXPANSION",
    "EXPANSION_CODE",
    "MNR_CARDS",
    "ANOMALIES",
    "PERSONNEL",
    "FACILITIES",
    "PROCEDURES",
    "MANDATES",
    "CALLBACKS",
    "_with_mnr_metadata",
    "_antimeme",
    "_mnestic_personnel",
    "_redact",
    "_cog_hazard",
    "_mnestic_wake_ability",
    "_mnr_card",
]
