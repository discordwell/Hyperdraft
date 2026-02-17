from src.ai.hearthstone_adapter import HearthstoneAIAdapter
from src.engine.game import Game
from src.engine.types import ZoneType
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.basic import CHILLWIND_YETI, BLOODFEN_RAPTOR, BOULDERFIST_OGRE
from src.cards.hearthstone.classic import FIREBALL


def _new_game():
    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])
    return game, p1, p2


def _summon(game: Game, card_def, owner):
    return game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _hand_card(game: Game, card_def, owner):
    return game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def test_ultra_prefers_favorable_trade_when_behind_and_is_deterministic():
    game, p1, p2 = _new_game()
    ai = HearthstoneAIAdapter(difficulty="ultra")

    attacker = _summon(game, CHILLWIND_YETI, p1)  # 4/5
    killable_trade = _summon(game, BLOODFEN_RAPTOR, p2)  # 3/2
    _summon(game, BOULDERFIST_OGRE, p2)  # 6/7, not favorable for 4/5

    # Push board/life context toward "behind" so Ultra should trade.
    p1.life = 12
    p2.life = 30

    chosen = {ai._choose_attack_target(attacker.id, game.state, p1.id) for _ in range(20)}
    assert chosen == {killable_trade.id}


def test_ultra_burn_targets_killable_threat_over_unkillable_threat():
    game, p1, p2 = _new_game()
    ai = HearthstoneAIAdapter(difficulty="ultra")

    fireball = _hand_card(game, FIREBALL, p1)  # 6 damage
    killable = _summon(game, CHILLWIND_YETI, p2)  # 5 health
    _summon(game, BOULDERFIST_OGRE, p2)  # 7 health (unkillable by Fireball)
    p2.life = 30

    targets = ai._choose_spell_targets(fireball, game.state, p1.id)
    assert targets == [[killable.id]]


def test_ultra_burn_goes_face_when_ahead_and_no_killable_minion():
    game, p1, p2 = _new_game()
    ai = HearthstoneAIAdapter(difficulty="ultra")

    fireball = _hand_card(game, FIREBALL, p1)  # 6 damage
    _summon(game, BOULDERFIST_OGRE, p2)  # unkillable by Fireball
    _summon(game, BOULDERFIST_OGRE, p1)
    _summon(game, CHILLWIND_YETI, p1)
    p1.life = 30
    p2.life = 12

    targets = ai._choose_spell_targets(fireball, game.state, p1.id)
    assert targets == [[p2.hero_id]]
