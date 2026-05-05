"""Focused Hearthstone strategy iteration tests."""

from src.ai.hearthstone_adapter import HearthstoneAIAdapter
from src.cards.hearthstone.basic import BLOODFEN_RAPTOR, CHILLWIND_YETI, THE_COIN
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.heroes import HEROES
from src.engine.game import Game
from src.engine.types import ZoneType


def _new_hs_game(hero1: str = "Mage", hero2: str = "Warrior"):
    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    game.setup_hearthstone_player(p1, HEROES[hero1], HERO_POWERS[hero1])
    game.setup_hearthstone_player(p2, HEROES[hero2], HERO_POWERS[hero2])
    return game, p1, p2


def _hand_card(game: Game, card_def, owner):
    return game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def test_hard_ai_uses_coin_to_unlock_much_better_curve_play():
    game, p1, _p2 = _new_hs_game()
    ai = HearthstoneAIAdapter(difficulty="hard")
    p1.mana_crystals_available = 3

    coin = _hand_card(game, THE_COIN, p1)
    _hand_card(game, BLOODFEN_RAPTOR, p1)
    _hand_card(game, CHILLWIND_YETI, p1)

    choice = ai._choose_card_to_play(game.state, p1.id, game)

    assert choice is not None
    assert choice["card_id"] == coin.id
