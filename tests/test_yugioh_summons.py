"""
Yu-Gi-Oh! Stage 3 Tests — Extra Deck Summoning Mechanics

Tests for Fusion, Synchro, Xyz, Pendulum, Link, and Ritual summon
validation and execution, overlay unit tracking, etc.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.game import Game, make_ygo_monster
from src.engine.types import ZoneType, CardType, EventType, Characteristics, CardDefinition
from src.engine.yugioh_summon import YugiohSummonManager


def make_test_game():
    game = Game(mode="yugioh")
    p1 = game.add_player("Player 1")
    p2 = game.add_player("Player 2")
    return game, p1, p2


def place_on_field(game, player, card_def, position='face_up_atk'):
    """Put a monster directly on the field."""
    turn_mgr = game.turn_manager
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(types={CardType.YGO_MONSTER}),
        card_def=card_def,
    )
    turn_mgr.ygo_turn_state.active_player_id = player.id
    turn_mgr.ygo_turn_state.normal_summon_used = False
    turn_mgr._do_normal_summon(player.id, {'card_id': obj.id})
    obj.state.ygo_position = position
    return obj


def add_to_extra_deck(game, player, card_def):
    """Add a card to the Extra Deck."""
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.EXTRA_DECK,
        characteristics=Characteristics(types={CardType.YGO_MONSTER}),
        card_def=card_def,
    )
    return obj


def add_to_hand(game, player, card_def):
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(types={CardType.YGO_MONSTER}),
        card_def=card_def,
    )
    return obj


# =============================================================================
# Fusion Tests
# =============================================================================

def test_fusion_summon_basic():
    """Test basic Fusion Summon with materials from field."""
    game, p1, p2 = make_test_game()
    summon_mgr = YugiohSummonManager(game.state)

    mat1 = place_on_field(game, p1, make_ygo_monster("Material A", 1200, 1000, 4))
    mat2 = add_to_hand(game, p1, make_ygo_monster("Material B", 1300, 900, 3))
    fusion = add_to_extra_deck(game, p1, make_ygo_monster(
        "Fusion Monster", 2500, 2100, 7, ygo_monster_type="Fusion"
    ))

    can, reason = summon_mgr.can_fusion_summon(p1.id, fusion.id, [mat1.id, mat2.id])
    assert can, reason

    events = summon_mgr.fusion_summon(p1.id, fusion.id, [mat1.id, mat2.id])
    assert len(events) > 0
    assert fusion.zone == ZoneType.MONSTER_ZONE
    assert mat1.zone == ZoneType.GRAVEYARD
    assert mat2.zone == ZoneType.GRAVEYARD
    print("  PASS: test_fusion_summon_basic")


def test_fusion_wrong_type():
    """Test that non-Fusion monsters can't be Fusion Summoned."""
    game, p1, p2 = make_test_game()
    summon_mgr = YugiohSummonManager(game.state)

    mat1 = place_on_field(game, p1, make_ygo_monster("Mat", 1000, 1000, 4))
    mat2 = add_to_hand(game, p1, make_ygo_monster("Mat2", 1000, 1000, 4))
    not_fusion = add_to_extra_deck(game, p1, make_ygo_monster(
        "Not Fusion", 2500, 2100, 7, ygo_monster_type="Effect"
    ))

    can, reason = summon_mgr.can_fusion_summon(p1.id, not_fusion.id, [mat1.id, mat2.id])
    assert not can
    print("  PASS: test_fusion_wrong_type")


# =============================================================================
# Synchro Tests
# =============================================================================

def test_synchro_summon_basic():
    """Test basic Synchro Summon: Tuner + non-Tuner, levels match."""
    game, p1, p2 = make_test_game()
    summon_mgr = YugiohSummonManager(game.state)

    tuner = place_on_field(game, p1, make_ygo_monster(
        "Tuner", 900, 200, level=3, is_tuner=True
    ))
    non_tuner = place_on_field(game, p1, make_ygo_monster(
        "Non-Tuner", 1500, 1200, level=4
    ))
    synchro = add_to_extra_deck(game, p1, make_ygo_monster(
        "Synchro Dragon", 2800, 2300, level=7, ygo_monster_type="Synchro"
    ))

    can, reason = summon_mgr.can_synchro_summon(p1.id, synchro.id, [tuner.id, non_tuner.id])
    assert can, reason

    events = summon_mgr.synchro_summon(p1.id, synchro.id, [tuner.id, non_tuner.id])
    assert len(events) > 0
    assert synchro.zone == ZoneType.MONSTER_ZONE
    assert tuner.zone == ZoneType.GRAVEYARD
    assert non_tuner.zone == ZoneType.GRAVEYARD
    print("  PASS: test_synchro_summon_basic")


def test_synchro_wrong_levels():
    """Test Synchro fails when levels don't sum correctly."""
    game, p1, p2 = make_test_game()
    summon_mgr = YugiohSummonManager(game.state)

    tuner = place_on_field(game, p1, make_ygo_monster("Tuner", 900, 200, level=3, is_tuner=True))
    non_tuner = place_on_field(game, p1, make_ygo_monster("NT", 1500, 1200, level=3))
    synchro = add_to_extra_deck(game, p1, make_ygo_monster(
        "Synchro", 2800, 2300, level=8, ygo_monster_type="Synchro"
    ))

    can, reason = summon_mgr.can_synchro_summon(p1.id, synchro.id, [tuner.id, non_tuner.id])
    assert not can
    assert "level" in reason.lower()
    print("  PASS: test_synchro_wrong_levels")


def test_synchro_no_tuner():
    """Test Synchro fails without a Tuner."""
    game, p1, p2 = make_test_game()
    summon_mgr = YugiohSummonManager(game.state)

    nt1 = place_on_field(game, p1, make_ygo_monster("NT1", 1500, 1200, level=4))
    nt2 = place_on_field(game, p1, make_ygo_monster("NT2", 1500, 1200, level=4))
    synchro = add_to_extra_deck(game, p1, make_ygo_monster(
        "Synchro", 2800, 2300, level=8, ygo_monster_type="Synchro"
    ))

    can, reason = summon_mgr.can_synchro_summon(p1.id, synchro.id, [nt1.id, nt2.id])
    assert not can
    assert "Tuner" in reason
    print("  PASS: test_synchro_no_tuner")


# =============================================================================
# Xyz Tests
# =============================================================================

def test_xyz_summon_basic():
    """Test basic Xyz Summon: 2 same-level monsters."""
    game, p1, p2 = make_test_game()
    summon_mgr = YugiohSummonManager(game.state)

    mat1 = place_on_field(game, p1, make_ygo_monster("Lv4 A", 1500, 1200, level=4))
    mat2 = place_on_field(game, p1, make_ygo_monster("Lv4 B", 1600, 1000, level=4))
    xyz = add_to_extra_deck(game, p1, CardDefinition(
        name="Xyz Beast", mana_cost=None,
        characteristics=Characteristics(types={CardType.YGO_MONSTER}),
        domain="YGO", rank=4, atk=2500, def_val=1800,
        ygo_monster_type="Xyz",
    ))

    can, reason = summon_mgr.can_xyz_summon(p1.id, xyz.id, [mat1.id, mat2.id])
    assert can, reason

    events = summon_mgr.xyz_summon(p1.id, xyz.id, [mat1.id, mat2.id])
    assert len(events) > 0
    assert xyz.zone == ZoneType.MONSTER_ZONE
    assert len(xyz.state.overlay_units) == 2
    assert mat1.id in xyz.state.overlay_units
    assert mat2.id in xyz.state.overlay_units
    print("  PASS: test_xyz_summon_basic")


def test_xyz_different_levels():
    """Test Xyz fails with different-level materials."""
    game, p1, p2 = make_test_game()
    summon_mgr = YugiohSummonManager(game.state)

    mat1 = place_on_field(game, p1, make_ygo_monster("Lv3", 1200, 1000, level=3))
    mat2 = place_on_field(game, p1, make_ygo_monster("Lv4", 1500, 1200, level=4))
    xyz = add_to_extra_deck(game, p1, CardDefinition(
        name="Xyz", mana_cost=None,
        characteristics=Characteristics(types={CardType.YGO_MONSTER}),
        domain="YGO", rank=4, atk=2500, def_val=1800, ygo_monster_type="Xyz",
    ))

    can, reason = summon_mgr.can_xyz_summon(p1.id, xyz.id, [mat1.id, mat2.id])
    assert not can
    assert "same level" in reason.lower()
    print("  PASS: test_xyz_different_levels")


def test_xyz_detach_material():
    """Test detaching overlay materials from an Xyz monster."""
    game, p1, p2 = make_test_game()
    summon_mgr = YugiohSummonManager(game.state)

    mat1 = place_on_field(game, p1, make_ygo_monster("Lv4 A", 1500, 1200, level=4))
    mat2 = place_on_field(game, p1, make_ygo_monster("Lv4 B", 1600, 1000, level=4))
    xyz = add_to_extra_deck(game, p1, CardDefinition(
        name="Xyz", mana_cost=None,
        characteristics=Characteristics(types={CardType.YGO_MONSTER}),
        domain="YGO", rank=4, atk=2500, def_val=1800, ygo_monster_type="Xyz",
    ))

    summon_mgr.xyz_summon(p1.id, xyz.id, [mat1.id, mat2.id])
    assert len(xyz.state.overlay_units) == 2

    detached = summon_mgr.detach_material(xyz.id, 1)
    assert len(detached) == 1
    assert len(xyz.state.overlay_units) == 1
    # Detached material goes to GY
    assert game.state.objects[detached[0]].zone == ZoneType.GRAVEYARD
    print("  PASS: test_xyz_detach_material")


# =============================================================================
# Link Tests
# =============================================================================

def test_link_summon_basic():
    """Test basic Link Summon with correct number of materials."""
    game, p1, p2 = make_test_game()
    summon_mgr = YugiohSummonManager(game.state)

    mat1 = place_on_field(game, p1, make_ygo_monster("A", 1000, 1000, 4))
    mat2 = place_on_field(game, p1, make_ygo_monster("B", 1200, 800, 3))
    link = add_to_extra_deck(game, p1, CardDefinition(
        name="Link Spider", mana_cost=None,
        characteristics=Characteristics(types={CardType.YGO_MONSTER}),
        domain="YGO", link_rating=2, atk=1400, def_val=None,
        ygo_monster_type="Link", link_arrows=["Bottom-Left", "Bottom-Right"],
    ))

    can, reason = summon_mgr.can_link_summon(p1.id, link.id, [mat1.id, mat2.id])
    assert can, reason

    events = summon_mgr.link_summon(p1.id, link.id, [mat1.id, mat2.id])
    assert len(events) > 0
    assert link.zone == ZoneType.MONSTER_ZONE
    assert mat1.zone == ZoneType.GRAVEYARD
    assert mat2.zone == ZoneType.GRAVEYARD
    print("  PASS: test_link_summon_basic")


def test_link_wrong_material_count():
    """Test Link Summon fails with wrong number of materials."""
    game, p1, p2 = make_test_game()
    summon_mgr = YugiohSummonManager(game.state)

    mat1 = place_on_field(game, p1, make_ygo_monster("A", 1000, 1000, 4))
    link = add_to_extra_deck(game, p1, CardDefinition(
        name="Link-3", mana_cost=None,
        characteristics=Characteristics(types={CardType.YGO_MONSTER}),
        domain="YGO", link_rating=3, atk=2400,
        ygo_monster_type="Link",
    ))

    can, reason = summon_mgr.can_link_summon(p1.id, link.id, [mat1.id])
    assert not can
    assert "Link Rating" in reason
    print("  PASS: test_link_wrong_material_count")


# =============================================================================
# Ritual Tests
# =============================================================================

def test_ritual_summon_basic():
    """Test basic Ritual Summon with tributes from field."""
    game, p1, p2 = make_test_game()
    summon_mgr = YugiohSummonManager(game.state)

    tribute = place_on_field(game, p1, make_ygo_monster("Tribute", 1500, 1200, level=4))
    ritual = add_to_hand(game, p1, make_ygo_monster(
        "Ritual Beast", 2500, 2000, level=4, ygo_monster_type="Ritual"
    ))

    can, reason = summon_mgr.can_ritual_summon(p1.id, ritual.id, [tribute.id])
    assert can, reason

    events = summon_mgr.ritual_summon(p1.id, ritual.id, [tribute.id])
    assert len(events) > 0
    assert ritual.zone == ZoneType.MONSTER_ZONE
    assert tribute.zone == ZoneType.GRAVEYARD
    print("  PASS: test_ritual_summon_basic")


def test_ritual_insufficient_levels():
    """Test Ritual Summon fails when tribute levels are too low."""
    game, p1, p2 = make_test_game()
    summon_mgr = YugiohSummonManager(game.state)

    tribute = place_on_field(game, p1, make_ygo_monster("Small", 500, 500, level=2))
    ritual = add_to_hand(game, p1, make_ygo_monster(
        "Big Ritual", 3000, 2500, level=8, ygo_monster_type="Ritual"
    ))

    can, reason = summon_mgr.can_ritual_summon(p1.id, ritual.id, [tribute.id])
    assert not can
    assert "level" in reason.lower()
    print("  PASS: test_ritual_insufficient_levels")


def test_ritual_from_hand_only():
    """Test that Ritual monsters must be summoned from hand."""
    game, p1, p2 = make_test_game()
    summon_mgr = YugiohSummonManager(game.state)

    tribute = place_on_field(game, p1, make_ygo_monster("T", 1500, 1200, level=4))
    # Put ritual in GY instead of hand
    ritual_def = make_ygo_monster("Ritual", 2500, 2000, level=4, ygo_monster_type="Ritual")
    ritual = game.create_object(
        name=ritual_def.name, owner_id=p1.id, zone=ZoneType.GRAVEYARD,
        characteristics=Characteristics(types={CardType.YGO_MONSTER}),
        card_def=ritual_def,
    )
    gy = game.state.zones[f"graveyard_{p1.id}"]
    gy.objects.append(ritual.id)

    can, reason = summon_mgr.can_ritual_summon(p1.id, ritual.id, [tribute.id])
    assert not can
    assert "hand" in reason.lower()
    print("  PASS: test_ritual_from_hand_only")


# =============================================================================
# Pendulum Tests
# =============================================================================

def test_pendulum_summon_basic():
    """Test Pendulum Summon with correct scales and levels."""
    game, p1, p2 = make_test_game()
    summon_mgr = YugiohSummonManager(game.state)

    # Set up Pendulum Zones
    pz_key = f"pendulum_zone_{p1.id}"
    scale_low_def = CardDefinition(
        name="Scale 1", mana_cost=None,
        characteristics=Characteristics(types={CardType.YGO_MONSTER}),
        domain="YGO", pendulum_scale=1, level=4, atk=1500, def_val=1000,
        ygo_monster_type="Pendulum",
    )
    scale_high_def = CardDefinition(
        name="Scale 8", mana_cost=None,
        characteristics=Characteristics(types={CardType.YGO_MONSTER}),
        domain="YGO", pendulum_scale=8, level=4, atk=1500, def_val=1000,
        ygo_monster_type="Pendulum",
    )
    s1 = game.create_object("Scale 1", p1.id, ZoneType.PENDULUM_ZONE,
                            Characteristics(types={CardType.YGO_MONSTER}), scale_low_def)
    s2 = game.create_object("Scale 8", p1.id, ZoneType.PENDULUM_ZONE,
                            Characteristics(types={CardType.YGO_MONSTER}), scale_high_def)

    # Monster to summon (level between 1 and 8 exclusive)
    summon_def = make_ygo_monster("Pendulum Target", 2000, 1500, level=5)
    target = add_to_hand(game, p1, summon_def)

    can, reason = summon_mgr.can_pendulum_summon(p1.id, [target.id])
    assert can, reason

    events = summon_mgr.pendulum_summon(p1.id, [target.id])
    assert len(events) > 0
    assert target.zone == ZoneType.MONSTER_ZONE
    print("  PASS: test_pendulum_summon_basic")


def test_pendulum_level_out_of_range():
    """Test Pendulum Summon fails when level is outside scale range."""
    game, p1, p2 = make_test_game()
    summon_mgr = YugiohSummonManager(game.state)

    # Scales 3 and 5
    pz_key = f"pendulum_zone_{p1.id}"
    s1_def = CardDefinition(
        name="Scale 3", mana_cost=None,
        characteristics=Characteristics(types={CardType.YGO_MONSTER}),
        domain="YGO", pendulum_scale=3, level=4, atk=1000, def_val=1000,
        ygo_monster_type="Pendulum",
    )
    s2_def = CardDefinition(
        name="Scale 5", mana_cost=None,
        characteristics=Characteristics(types={CardType.YGO_MONSTER}),
        domain="YGO", pendulum_scale=5, level=4, atk=1000, def_val=1000,
        ygo_monster_type="Pendulum",
    )
    game.create_object("Scale 3", p1.id, ZoneType.PENDULUM_ZONE,
                        Characteristics(types={CardType.YGO_MONSTER}), s1_def)
    game.create_object("Scale 5", p1.id, ZoneType.PENDULUM_ZONE,
                        Characteristics(types={CardType.YGO_MONSTER}), s2_def)

    # Level 4 is the only valid one (between 3 and 5 exclusive)
    # Level 5 is NOT between them
    bad = add_to_hand(game, p1, make_ygo_monster("Lv5", 2000, 1500, level=5))
    can, reason = summon_mgr.can_pendulum_summon(p1.id, [bad.id])
    assert not can
    assert "scale" in reason.lower()

    # Level 4 should work
    good = add_to_hand(game, p1, make_ygo_monster("Lv4", 1800, 1400, level=4))
    can, reason = summon_mgr.can_pendulum_summon(p1.id, [good.id])
    assert can, reason
    print("  PASS: test_pendulum_level_out_of_range")


# =============================================================================
# Run all tests
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Yu-Gi-Oh! Stage 3 Tests — Summoning Mechanics")
    print("=" * 60)

    tests = [
        test_fusion_summon_basic,
        test_fusion_wrong_type,
        test_synchro_summon_basic,
        test_synchro_wrong_levels,
        test_synchro_no_tuner,
        test_xyz_summon_basic,
        test_xyz_different_levels,
        test_xyz_detach_material,
        test_link_summon_basic,
        test_link_wrong_material_count,
        test_ritual_summon_basic,
        test_ritual_insufficient_levels,
        test_ritual_from_hand_only,
        test_pendulum_summon_basic,
        test_pendulum_level_out_of_range,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    print(f"{'=' * 60}")
    if failed > 0:
        sys.exit(1)
