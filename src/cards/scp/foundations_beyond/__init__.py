"""Foundations Beyond (FBN) expansion package.

Ten archetypes / 300 cards / 10 mechanics. Each archetype lives in its own
sub-module under this package; the per-file ``<ARCHETYPE>_CARDS`` list is
aggregated here into a single ``FBN_CARDS`` dict keyed by card name.

Architecture mirrors :mod:`src.cards.scp.mnestic_reset`. The cards register
through ``src.cards.scp.__init__`` via a single merge import.
"""
from __future__ import annotations

from typing import Callable

from src.engine.types import CardDefinition

from .helpers import (
    EXPANSION,
    EXPANSION_CODE,
    _with_fbn_metadata,
    _fbn_card,
    _compleation,
    _phylactery_audit,
    _spark_containment,
    _leyline_saturation,
    _planar_rift,
    _dragon_hoard,
    _annihilation_wave,
    _wurm_devourer,
    _brief,
    _mnestic_personnel,
)

from .phyrexian_strain import PHYREXIAN_STRAIN_CARDS
from .eldrazi_apex import ELDRAZI_APEX_CARDS
from .dragon_conclave import DRAGON_CONCLAVE_CARDS
from .planeswalker_detention import PLANESWALKER_DETENTION_CARDS
from .demonic_pact_bureau import DEMONIC_PACT_BUREAU_CARDS
from .leyline_anomaly import LEYLINE_ANOMALY_CARDS
from .multiverse_rift import MULTIVERSE_RIFT_CARDS
from .lich_phylactery import LICH_PHYLACTERY_CARDS
from .wurm_apex import WURM_APEX_CARDS
from .spirit_archive import SPIRIT_ARCHIVE_CARDS


_ALL_LISTS = [
    PHYREXIAN_STRAIN_CARDS,
    ELDRAZI_APEX_CARDS,
    DRAGON_CONCLAVE_CARDS,
    PLANESWALKER_DETENTION_CARDS,
    DEMONIC_PACT_BUREAU_CARDS,
    LEYLINE_ANOMALY_CARDS,
    MULTIVERSE_RIFT_CARDS,
    LICH_PHYLACTERY_CARDS,
    WURM_APEX_CARDS,
    SPIRIT_ARCHIVE_CARDS,
]


FBN_CARDS: dict[str, CardDefinition] = {
    card.name: card for sub in _ALL_LISTS for card in sub
}


from .decks import FBN_STARTER_DECK_FACTORIES  # noqa: E402  (populated by Stage 6)


__all__ = [
    "EXPANSION",
    "EXPANSION_CODE",
    "FBN_CARDS",
    "FBN_STARTER_DECK_FACTORIES",
    "PHYREXIAN_STRAIN_CARDS",
    "ELDRAZI_APEX_CARDS",
    "DRAGON_CONCLAVE_CARDS",
    "PLANESWALKER_DETENTION_CARDS",
    "DEMONIC_PACT_BUREAU_CARDS",
    "LEYLINE_ANOMALY_CARDS",
    "MULTIVERSE_RIFT_CARDS",
    "LICH_PHYLACTERY_CARDS",
    "WURM_APEX_CARDS",
    "SPIRIT_ARCHIVE_CARDS",
    "_with_fbn_metadata",
    "_fbn_card",
    "_compleation",
    "_phylactery_audit",
    "_spark_containment",
    "_leyline_saturation",
    "_planar_rift",
    "_dragon_hoard",
    "_annihilation_wave",
    "_wurm_devourer",
    "_brief",
    "_mnestic_personnel",
]
