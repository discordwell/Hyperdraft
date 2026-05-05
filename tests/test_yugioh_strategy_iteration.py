"""Focused Yu-Gi-Oh! strategy iteration tests."""

from src.ai.yugioh_adapter import YugiohAIAdapter
from src.cards.yugioh.ygo_classic import BLUE_EYES_WHITE_DRAGON
from src.cards.yugioh.beyond.kamigawa.staples import LIGHTNING_BOLT
from src.cards.yugioh.ygo_optimized import (
    CHAIN_BURN_STRATEGY,
    DRAGON_BEATDOWN_STRATEGY,
    HEAVY_STORM,
    MESSENGER_OF_PEACE,
    MIRROR_FORCE,
    MONSTER_REBORN,
    MOUNTAIN,
    MYSTICAL_SPACE_TYPHOON,
    OOKAZI,
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


def test_hard_ai_battle_assignment_preserves_matchups_for_other_attackers():
    game, p1, p2 = _new_ygo_game()
    ai = YugiohAIAdapter(difficulty="hard")
    strong = _field_monster(game, p1, "Strong Attacker", 2500, 2000)
    weak = _field_monster(game, p1, "Weak Attacker", 1600, 1200)
    small = _field_monster(game, p2, "Small Target", 1500, 1000)
    big = _field_monster(game, p2, "Big Target", 2400, 1800)
    turn_state = game.turn_manager.ygo_turn_state

    action = ai.get_battle_action(p1.id, game.state, turn_state)

    assert action["action_type"] == "declare_attack"
    assert (action["attacker_id"], action["target_id"]) in {
        (strong.id, big.id),
        (weak.id, small.id),
    }
    assert (action["attacker_id"], action["target_id"]) != (strong.id, small.id)


def test_hard_ai_casts_lethal_burn_before_summoning():
    game, p1, p2 = _new_ygo_game()
    ai = YugiohAIAdapter(difficulty="hard")
    p2.lp = 800
    burn = _card(game, OOKAZI, p1, ZoneType.HAND)
    _card(game, BLUE_EYES_WHITE_DRAGON, p1, ZoneType.HAND)
    turn_state = game.turn_manager.ygo_turn_state
    turn_state.active_player_id = p1.id
    turn_state.normal_summon_used = False

    action = ai.get_main_phase_action(p1.id, game.state, turn_state)

    assert action == {
        "action_type": "activate_spell",
        "card_id": burn.id,
    }


def test_hard_ai_casts_custom_lethal_burn_before_summoning():
    game, p1, p2 = _new_ygo_game()
    ai = YugiohAIAdapter(difficulty="hard")
    p2.lp = 1500
    bolt = _card(game, LIGHTNING_BOLT, p1, ZoneType.HAND)
    _card(game, BLUE_EYES_WHITE_DRAGON, p1, ZoneType.HAND)
    turn_state = game.turn_manager.ygo_turn_state
    turn_state.active_player_id = p1.id
    turn_state.normal_summon_used = False

    action = ai.get_main_phase_action(p1.id, game.state, turn_state)

    assert action == {
        "action_type": "activate_spell",
        "card_id": bolt.id,
    }


def test_hard_ai_does_not_reborn_when_monster_zones_are_full():
    game, p1, p2 = _new_ygo_game()
    ai = YugiohAIAdapter(difficulty="hard")
    reborn = _card(game, MONSTER_REBORN, p1, ZoneType.HAND)
    target = _card(game, BLUE_EYES_WHITE_DRAGON, p1, ZoneType.GRAVEYARD)
    for idx in range(5):
        _field_monster(game, p1, f"Filled Slot {idx}", 1000, 1000)

    choice = ai._pick_spell_activation(
        [reborn], p1.id, game.state, p2.id, [], []
    )

    assert choice is None

    game.state.zones[f"monster_zone_{p1.id}"].objects[0] = None
    choice = ai._pick_spell_activation(
        [reborn], p1.id, game.state, p2.id, [], []
    )

    assert choice == {
        "action_type": "activate_spell",
        "card_id": reborn.id,
        "targets": [target.id],
    }


def test_hard_ai_uses_stall_spells_by_role_and_board_posture():
    game, p1, p2 = _new_ygo_game()
    ai = YugiohAIAdapter(difficulty="hard")
    ai.strategy = DRAGON_BEATDOWN_STRATEGY
    messenger = _card(game, MESSENGER_OF_PEACE, p1, ZoneType.HAND)
    my_monster = _field_monster(game, p1, "My Beater", 1900, 1200)
    opp_monster = _field_monster(game, p2, "Small Fodder", 1000, 1000)

    choice = ai._pick_spell_activation(
        [messenger], p1.id, game.state, p2.id, [opp_monster], [my_monster]
    )

    assert choice is None

    ai.strategy = CHAIN_BURN_STRATEGY
    choice = ai._pick_spell_activation(
        [messenger], p1.id, game.state, p2.id, [opp_monster], [my_monster]
    )

    assert choice == {
        "action_type": "activate_spell",
        "card_id": messenger.id,
    }


def test_hard_ai_targets_field_spells_with_mst_effects():
    game, p1, p2 = _new_ygo_game()
    ai = YugiohAIAdapter(difficulty="hard")
    mst = _card(game, MYSTICAL_SPACE_TYPHOON, p1, ZoneType.HAND)
    field_spell = _card(game, MOUNTAIN, p2, ZoneType.FIELD_SPELL_ZONE)

    choice = ai._pick_spell_activation(
        [mst], p1.id, game.state, p2.id, [], []
    )

    assert choice == {
        "action_type": "activate_spell",
        "card_id": mst.id,
        "targets": [field_spell.id],
    }
