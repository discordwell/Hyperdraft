"""CLAN — Workshop Genesis (first Clankers set).

See ``docs/sets/clan.md`` for the design and ``docs/games/clankers.md`` for the
engine. 150 cards across 4 archetypes (FORGE-Δ / ETHOS-7 / MIRTHBOT-1 /
BULWARK-9) plus a handful of neutrals.
"""

from .clan_forge import FORGE_CARDS
from .clan_ethos import ETHOS_CARDS
from .clan_mirth import MIRTH_CARDS
from .clan_bulwark import BULWARK_CARDS
from .decks import (
    CLAN_STARTER_DECKS,
    build_clan_forge,
    build_clan_ethos,
    build_clan_mirth,
    build_clan_bulwark,
)


CLAN_CARDS: dict = {
    **FORGE_CARDS,
    **ETHOS_CARDS,
    **MIRTH_CARDS,
    **BULWARK_CARDS,
}


__all__ = [
    "CLAN_CARDS",
    "FORGE_CARDS",
    "ETHOS_CARDS",
    "MIRTH_CARDS",
    "BULWARK_CARDS",
    "CLAN_STARTER_DECKS",
    "build_clan_forge",
    "build_clan_ethos",
    "build_clan_mirth",
    "build_clan_bulwark",
]
