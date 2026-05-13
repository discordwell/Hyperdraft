"""MNR anomaly sub-set.

Card-design agents: populate ``ANOMALIES`` with ~24 anomaly cards. Use the
``_mnr_card``, ``_antimeme``, and ``_cog_hazard`` factories from
``helpers.py``. The single sample below demonstrates the full wiring loop.
"""

from __future__ import annotations

from src.engine.types import CardDefinition, CardType

from .helpers import _antimeme, _cog_hazard, _mnr_card


# Sample card: validates the antimeme + cog hazard verbs end-to-end.
# Card-design agents replace / extend this list.
_FIVE_AND_THREE_EIGHTHS = _antimeme(
    _cog_hazard(
        _mnr_card(
            "MNR Five and Three-Eighths",
            CardType.SCP_ANOMALY,
            containment=5,
            curiosity=4,
            hazard=2,
            red_tape=1,
            subtypes={"Antimemetic", "Recursive"},
            text=(
                "Antimeme 3: at end of your turn without a Mnestic personnel, "
                "gain a forget counter. At 3, this anomaly is forgotten. "
                "Cognitive Hazard 1: at the start of an opponent's turn without "
                "a Mnestic personnel, they discard a card."
            ),
            rarity="rare",
            archetype="antimeme_decay",
        ),
        x=1,
    ),
    n=3,
)


ANOMALIES: list[CardDefinition] = [
    _FIVE_AND_THREE_EIGHTHS,
]
