"""Clankers card sets — see ``docs/games/clankers.md`` for the engine.

This package aggregates all Clankers card sets into a single ``CLANKERS_CARDS``
dict so external tooling (deckbuilder, art harness, registry) can find them.
Currently ships: CLAN (Workshop Genesis, 151 cards).
"""

from .CLAN import CLAN_CARDS


CLANKERS_CARDS: dict = {
    **CLAN_CARDS,
}


__all__ = ["CLANKERS_CARDS", "CLAN_CARDS"]
