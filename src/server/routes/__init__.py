"""
API Routes
"""

from .match import router as match_router
from .cards import router as cards_router
from .bot_game import router as bot_game_router

__all__ = ['match_router', 'cards_router', 'bot_game_router']
