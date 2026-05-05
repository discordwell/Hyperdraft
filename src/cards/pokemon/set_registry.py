"""
Pokemon Set Registry

Maps Pokemon "set codes" to their card registries. Mirrors the shape of
src/cards/set_registry.py but stays separate because Pokemon cards live
in their own domain (CardDefinition.domain == "PKM") and the MTG-side
SetInfo schema doesn't carry Pokemon-relevant attributes.
"""

from dataclasses import dataclass
from typing import Optional

from .sv_starter import SV_STARTER_CARDS
from .beyond.ravnica import BEYOND_RAVNICA_CARDS, GUILD_REGISTRIES


@dataclass(frozen=True)
class PokemonSetInfo:
    code: str
    name: str
    card_count: int
    release_date: str
    set_type: str  # "starter", "beyond"


POKEMON_SETS: dict[str, PokemonSetInfo] = {
    "SVS": PokemonSetInfo("SVS", "Scarlet & Violet Starter", len(SV_STARTER_CARDS), "2023-03-31", "starter"),
    "BRV": PokemonSetInfo("BRV", "Beyond Ravnica", len(BEYOND_RAVNICA_CARDS), "2026-01-01", "beyond"),
}


_SET_TO_REGISTRY = {
    "SVS": SV_STARTER_CARDS,
    "BRV": BEYOND_RAVNICA_CARDS,
}


# card_name -> guild (lowercase) for Beyond Ravnica cards.
_BRV_CARD_TO_GUILD: dict[str, str] = {}
for _guild, _registry in GUILD_REGISTRIES.items():
    for _name in _registry.keys():
        _BRV_CARD_TO_GUILD[_name] = _guild


def get_pokemon_set_info(set_code: str) -> Optional[PokemonSetInfo]:
    return POKEMON_SETS.get(set_code.upper())


def get_all_pokemon_sets(set_type: Optional[str] = None) -> list[PokemonSetInfo]:
    sets = list(POKEMON_SETS.values())
    if set_type:
        sets = [s for s in sets if s.set_type == set_type]
    return sorted(sets, key=lambda s: s.release_date, reverse=True)


def get_pokemon_cards_in_set(set_code: str) -> dict:
    return _SET_TO_REGISTRY.get(set_code.upper(), {})


def get_pokemon_guild(card_name: str) -> Optional[str]:
    """Return the Ravnica guild for a Beyond Ravnica card, else None."""
    return _BRV_CARD_TO_GUILD.get(card_name)


def get_pokemon_guilds() -> list[str]:
    """All guild names present in BRV (sorted)."""
    return sorted(GUILD_REGISTRIES.keys())


__all__ = [
    "PokemonSetInfo",
    "POKEMON_SETS",
    "get_pokemon_set_info",
    "get_all_pokemon_sets",
    "get_pokemon_cards_in_set",
    "get_pokemon_guild",
    "get_pokemon_guilds",
]
