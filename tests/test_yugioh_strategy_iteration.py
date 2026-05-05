"""Focused Yu-Gi-Oh! strategy iteration tests."""

from src.ai.yugioh_adapter import YugiohAIAdapter
from src.cards.yugioh.ygo_classic import BLUE_EYES_WHITE_DRAGON
from src.cards.yugioh.ygo_optimized import PREMATURE_BURIAL
from src.engine.game import Game
from src.engine.types import ZoneType


def _new_ygo_game():
    game = Game(mode="yugioh")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    game.setup_yugioh_player(p1, [], [])
    game.setup_yugioh_player(p2, [], [])
    return game, p1, p2


def _card(game: Game, card_def, owner, zone: ZoneType):
    return game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def test_hard_ai_does_not_activate_premature_burial_at_lethal_cost():
    game, p1, p2 = _new_ygo_game()
    ai = YugiohAIAdapter(difficulty="hard")
    spell = _card(game, PREMATURE_BURIAL, p1, ZoneType.HAND)
    target = _card(game, BLUE_EYES_WHITE_DRAGON, p1, ZoneType.GRAVEYARD)
    p1.lp = 800

    choice = ai._pick_spell_activation(
        [spell], p1.id, game.state, p2.id, [], []
    )

    assert choice is None

    p1.lp = 801
    choice = ai._pick_spell_activation(
        [spell], p1.id, game.state, p2.id, [], []
    )

    assert choice == {
        "action_type": "activate_spell",
        "card_id": spell.id,
        "targets": [target.id],
    }
