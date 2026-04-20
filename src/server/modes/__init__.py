"""
Server-side mode adapters.

Each adapter encapsulates per-mode server concerns: game loop, human action
handling, action dispatch, and card serialization. The GameSession orchestrator
delegates to one of these adapters based on `game.state.game_mode`.
"""

from .base import ModeAdapter
from .mtg import MTGModeAdapter
from .hs import HearthstoneModeAdapter
from .pkm import PokemonModeAdapter
from .ygo import YugiohModeAdapter


_ADAPTERS: dict[str, ModeAdapter] = {
    "mtg": MTGModeAdapter(),
    "hearthstone": HearthstoneModeAdapter(),
    "pokemon": PokemonModeAdapter(),
    "yugioh": YugiohModeAdapter(),
}


def get_server_mode_adapter(game_mode: str) -> ModeAdapter:
    """Return the server-side adapter for a given game mode."""
    if game_mode in _ADAPTERS:
        return _ADAPTERS[game_mode]
    # Default to MTG for unknown/legacy modes.
    return _ADAPTERS["mtg"]


__all__ = [
    "ModeAdapter",
    "MTGModeAdapter",
    "HearthstoneModeAdapter",
    "PokemonModeAdapter",
    "YugiohModeAdapter",
    "get_server_mode_adapter",
]
