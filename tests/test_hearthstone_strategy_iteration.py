"""Focused Hearthstone strategy iteration tests."""

from src.ai.hearthstone_adapter import HearthstoneAIAdapter
from src.cards.hearthstone.basic import BLOODFEN_RAPTOR, CHILLWIND_YETI, THE_COIN
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.heroes import HEROES
from src.engine.game import Game
from src.engine.types import CardType, Event, EventType, ZoneType


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


def _summon_minion(game: Game, owner, name: str, attack: int, health: int):
    minion = game.create_object(name=name, owner_id=owner.id, zone=ZoneType.BATTLEFIELD)
    minion.characteristics.types = {CardType.MINION}
    minion.characteristics.power = attack
    minion.characteristics.toughness = health
    return minion


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


def test_fireblast_kills_one_health_threat_before_defaulting_face():
    game, p1, p2 = _new_hs_game("Mage", "Warrior")
    p1.mana_crystals_available = 2
    p2.life = 30
    _summon_minion(game, p2, "Low Threat", 1, 1)
    threat = _summon_minion(game, p2, "Knife Juggler", 3, 1)

    events = game.pipeline.emit(Event(
        type=EventType.HERO_POWER_ACTIVATE,
        payload={"hero_power_id": p1.hero_power_id, "player": p1.id},
        source=p1.hero_power_id,
    ))

    damage_events = [event for event in events if event.type == EventType.DAMAGE]
    assert damage_events
    assert damage_events[-1].payload["target"] == threat.id
