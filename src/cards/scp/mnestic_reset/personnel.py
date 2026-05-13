"""MNR personnel sub-set.

Card-design agents: populate ``PERSONNEL`` with ~24 personnel. Most should
use ``_mnestic_personnel`` (the keystone verb of the set). For non-Mnestic
personnel that gain Mnestic mid-game, add a Mnestic Wake activated ability
via ``_mnestic_wake_ability`` inside a ``setup_interceptors`` callback.
"""

from __future__ import annotations

from src.engine.types import CardDefinition

from .helpers import _mnestic_personnel


# Sample card: a baseline Mnestic personnel — research-leaning, lightweight.
# Card-design agents replace / extend this list.
_MARION_WHEELER = _mnestic_personnel(
    "MNR Marion Wheeler",
    skills={"research": 2, "suppress": 1},
    red_tape=2,
    subtypes={"Antimemetics", "Hero"},
    text=(
        "Mnestic. While Marion Wheeler is active, antimemetic anomalies you "
        "control do not gain forget counters and your hand is shielded from "
        "Cognitive Hazard."
    ),
    rarity="rare",
    archetype="mnestic_core",
)


PERSONNEL: list[CardDefinition] = [
    _MARION_WHEELER,
]
