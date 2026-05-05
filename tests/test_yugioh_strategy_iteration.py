"""Focused Yu-Gi-Oh! strategy iteration tests."""

from src.ai.yugioh_adapter import YugiohAIAdapter
from src.cards.yugioh.ygo_classic import BLUE_EYES_WHITE_DRAGON
from src.cards.yugioh.ygo_optimized import (
    CHAIN_BURN_STRATEGY,
    HEAVY_STORM,
    MIRROR_FORCE,
    PREMATURE_BURIAL,
    SAKURETSU_ARMOR,
    STEALTH_BIRD,
)
from src.engine.game import Game, make_ygo_monster
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


def _field_monster(game: Game, owner, name: str, atk: int, def_val: int,
                   position: str = "face_up_atk"):
    card_def = make_ygo_monster(name, atk=atk, def_val=def_val, level=4)
    obj = _card(game, card_def, owner, ZoneType.MONSTER_ZONE)
    obj.state.ygo_position = position
    obj.state.face_down = position == "face_down_def"
    return obj


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


def test_hard_ai_skips_battle_phase_when_no_safe_attack_exists():
    game, p1, p2 = _new_ygo_game()
    ai = YugiohAIAdapter(difficulty="hard")
    _field_monster(game, p1, "Outclassed Attacker", 1200, 1000)
    blocker = _field_monster(game, p2, "Visible Beater", 2000, 1600)

    assert ai.should_enter_battle(p1.id, game.state) is False

    blocker.state.ygo_position = "face_up_def"
    blocker.card_def.def_val = 1000

    assert ai.should_enter_battle(p1.id, game.state) is True


def test_hard_ai_sets_strategy_set_priority_monster_before_summoning():
    game, p1, _p2 = _new_ygo_game()
    ai = YugiohAIAdapter(difficulty="hard")
    ai.strategy = CHAIN_BURN_STRATEGY
    bird = _card(game, STEALTH_BIRD, p1, ZoneType.HAND)
    turn_state = game.turn_manager.ygo_turn_state
    turn_state.active_player_id = p1.id
    turn_state.normal_summon_used = False

    action = ai.get_main_phase_action(p1.id, game.state, turn_state)

    assert action == {
        "action_type": "set_monster",
        "card_id": bird.id,
    }


def test_hard_ai_does_not_heavy_storm_equal_backrow():
    game, p1, p2 = _new_ygo_game()
    ai = YugiohAIAdapter(difficulty="hard")
    storm = _card(game, HEAVY_STORM, p1, ZoneType.HAND)
    _card(game, MIRROR_FORCE, p1, ZoneType.SPELL_TRAP_ZONE)
    _card(game, SAKURETSU_ARMOR, p1, ZoneType.SPELL_TRAP_ZONE)
    _card(game, MIRROR_FORCE, p2, ZoneType.SPELL_TRAP_ZONE)
    _card(game, SAKURETSU_ARMOR, p2, ZoneType.SPELL_TRAP_ZONE)

    choice = ai._pick_spell_activation(
        [storm], p1.id, game.state, p2.id, [], []
    )

    assert choice is None

    game.state.zones[f"spell_trap_zone_{p1.id}"].objects.pop()
    choice = ai._pick_spell_activation(
        [storm], p1.id, game.state, p2.id, [], []
    )

    assert choice == {"action_type": "activate_spell", "card_id": storm.id}
