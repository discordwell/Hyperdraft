"""
Yu-Gi-Oh! Stage 4 Tests — Card Effects

Tests for individual card effects: Dark Hole board wipe, Mirror Force,
Swords of Revealing Light, Blue-Eyes Ultimate Fusion, Monster Reborn,
Kuriboh hand trap, Ring of Destruction, Magic Cylinder.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.game import Game, make_ygo_monster, make_ygo_spell, make_ygo_trap
from src.engine.types import ZoneType, CardType, EventType, Event, Characteristics
from src.engine.yugioh_spells import YugiohSpellTrapManager
from src.engine.yugioh_summon import YugiohSummonManager
from src.cards.yugioh.ygo_classic import (
    DARK_MAGICIAN, BLUE_EYES_WHITE_DRAGON, BLUE_EYES_ULTIMATE_DRAGON,
    KURIBOH, DARK_HOLE, MONSTER_REBORN, MIRROR_FORCE, MAGIC_CYLINDER,
    RING_OF_DESTRUCTION, SWORDS_OF_REVEALING_LIGHT, MYSTICAL_SPACE_TYPHOON,
    CELTIC_GUARDIAN, LA_JINN, POLYMERIZATION,
)
from src.cards.yugioh.ygo_starter import (
    SOLEMN_JUDGMENT, MAN_EATER_BUG, SAKURETSU_ARMOR,
    WARRIOR_DECK, WARRIOR_EXTRA_DECK, SPELLCASTER_DECK, SPELLCASTER_EXTRA_DECK,
)
from src.cards.yugioh.ygo_classic import YUGI_DECK, KAIBA_DECK


def make_test_game():
    game = Game(mode="yugioh")
    p1 = game.add_player("Player 1")
    p2 = game.add_player("Player 2")
    return game, p1, p2


def place_on_field(game, player, card_def, position='face_up_atk'):
    turn_mgr = game.turn_manager
    obj = game.create_object(
        name=card_def.name, owner_id=player.id, zone=ZoneType.HAND,
        characteristics=Characteristics(types=set(card_def.characteristics.types)),
        card_def=card_def,
    )
    turn_mgr.ygo_turn_state.active_player_id = player.id
    turn_mgr.ygo_turn_state.normal_summon_used = False
    turn_mgr._do_normal_summon(player.id, {'card_id': obj.id})
    obj.state.ygo_position = position
    return obj


def add_to_hand(game, player, card_def):
    return game.create_object(
        name=card_def.name, owner_id=player.id, zone=ZoneType.HAND,
        characteristics=Characteristics(types=set(card_def.characteristics.types)),
        card_def=card_def,
    )


def set_trap(game, player, card_def, turns_set=1):
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = player.id
    obj = add_to_hand(game, player, card_def)
    turn_mgr._do_set_spell_trap(player.id, {'card_id': obj.id})
    obj.state.turns_set = turns_set
    return obj


def count_monsters(game, player_id):
    zone = game.state.zones.get(f"monster_zone_{player_id}")
    if not zone:
        return 0
    return sum(1 for oid in zone.objects if oid is not None)


# =============================================================================
# Card Effect Tests
# =============================================================================

def test_dark_hole_destroys_all():
    """Test Dark Hole destroys all monsters on the field."""
    game, p1, p2 = make_test_game()
    spell_mgr = YugiohSpellTrapManager(game.state)

    # Place monsters for both players
    place_on_field(game, p1, CELTIC_GUARDIAN)
    place_on_field(game, p2, LA_JINN)

    assert count_monsters(game, p1.id) == 1
    assert count_monsters(game, p2.id) == 1

    dh = add_to_hand(game, p1, DARK_HOLE)
    events = spell_mgr.activate_spell(dh.id, p1.id)

    assert count_monsters(game, p1.id) == 0
    assert count_monsters(game, p2.id) == 0
    assert dh.zone == ZoneType.GRAVEYARD
    print("  PASS: test_dark_hole_destroys_all")


def test_mirror_force_destroys_atk_opponents():
    """Test Mirror Force destroys all ATK-position opponent monsters."""
    game, p1, p2 = make_test_game()
    spell_mgr = YugiohSpellTrapManager(game.state)

    # P2 has 2 ATK monsters, 1 DEF
    m1 = place_on_field(game, p2, LA_JINN, 'face_up_atk')
    m2 = place_on_field(game, p2, CELTIC_GUARDIAN, 'face_up_atk')
    m3 = place_on_field(game, p2, make_ygo_monster("Wall", 500, 2000, 4), 'face_up_def')

    # P1 has Mirror Force set
    mf = set_trap(game, p1, MIRROR_FORCE)

    events = spell_mgr.activate_trap(mf.id, p1.id)

    # ATK position monsters destroyed
    assert m1.zone == ZoneType.GRAVEYARD
    assert m2.zone == ZoneType.GRAVEYARD
    # DEF position monster survives
    assert m3.zone == ZoneType.MONSTER_ZONE
    print("  PASS: test_mirror_force_destroys_atk_opponents")


def test_monster_reborn_revives():
    """Test Monster Reborn revives a monster from GY."""
    game, p1, p2 = make_test_game()
    spell_mgr = YugiohSpellTrapManager(game.state)

    # Place and destroy a monster to put it in GY
    dm = place_on_field(game, p1, DARK_MAGICIAN)
    game.turn_manager._send_to_graveyard(dm.id, p1.id)
    assert dm.zone == ZoneType.GRAVEYARD

    # Create Monster Reborn
    mr_def = MONSTER_REBORN
    mr = game.create_object(
        name=mr_def.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=Characteristics(types=set(mr_def.characteristics.types)),
        card_def=mr_def,
    )

    # Activate with target
    resolve_event = Event(
        type=EventType.YGO_ACTIVATE_SPELL,
        payload={'card_id': mr.id, 'player': p1.id, 'targets': [dm.id]},
        source=mr.id, controller=p1.id,
    )
    events = mr_def.resolve(resolve_event, game.state)

    assert dm.zone == ZoneType.MONSTER_ZONE
    assert dm.state.ygo_position == 'face_up_atk'
    print("  PASS: test_monster_reborn_revives")


def test_swords_flips_face_down():
    """Test Swords of Revealing Light flips opponent's face-down monsters."""
    game, p1, p2 = make_test_game()

    # P2 has face-down monster
    fd = place_on_field(game, p2, LA_JINN)
    fd.state.face_down = True
    fd.state.ygo_position = 'face_down_def'

    sol = add_to_hand(game, p1, SWORDS_OF_REVEALING_LIGHT)
    resolve_event = Event(
        type=EventType.YGO_ACTIVATE_SPELL,
        payload={'card_id': sol.id, 'player': p1.id},
        source=sol.id, controller=p1.id,
    )
    events = SWORDS_OF_REVEALING_LIGHT.resolve(resolve_event, game.state)

    assert not fd.state.face_down
    assert fd.state.ygo_position == 'face_up_def'
    print("  PASS: test_swords_flips_face_down")


def test_magic_cylinder_damage():
    """Test Magic Cylinder inflicts ATK as damage."""
    game, p1, p2 = make_test_game()

    # P2 has a 3000 ATK monster
    bewd = place_on_field(game, p2, BLUE_EYES_WHITE_DRAGON)

    # P1 activates Magic Cylinder targeting BEWD
    resolve_event = Event(
        type=EventType.YGO_ACTIVATE_TRAP,
        payload={'card_id': 'mc', 'player': p1.id, 'targets': [bewd.id]},
        source='mc', controller=p1.id,
    )
    events = MAGIC_CYLINDER.resolve(resolve_event, game.state)

    # P2 should take 3000 damage
    assert p2.lp == 5000  # 8000 - 3000
    print("  PASS: test_magic_cylinder_damage")


def test_ring_of_destruction():
    """Test Ring of Destruction: destroy + both players take damage."""
    game, p1, p2 = make_test_game()

    mon = place_on_field(game, p2, DARK_MAGICIAN)

    resolve_event = Event(
        type=EventType.YGO_ACTIVATE_TRAP,
        payload={'card_id': 'rod', 'player': p1.id, 'targets': [mon.id]},
        source='rod', controller=p1.id,
    )
    events = RING_OF_DESTRUCTION.resolve(resolve_event, game.state)

    assert mon.zone == ZoneType.GRAVEYARD
    assert p1.lp == 5500  # 8000 - 2500
    assert p2.lp == 5500  # 8000 - 2500
    print("  PASS: test_ring_of_destruction")


def test_solemn_judgment_lp():
    """Test Solemn Judgment pays half LP."""
    game, p1, p2 = make_test_game()

    resolve_event = Event(
        type=EventType.YGO_ACTIVATE_TRAP,
        payload={'card_id': 'sj', 'player': p1.id},
        source='sj', controller=p1.id,
    )
    events = SOLEMN_JUDGMENT.resolve(resolve_event, game.state)
    assert p1.lp == 4000  # Half of 8000
    print("  PASS: test_solemn_judgment_lp")


def test_man_eater_bug_flip():
    """Test Man-Eater Bug FLIP effect destroys a monster."""
    game, p1, p2 = make_test_game()

    # P2 has a monster
    target = place_on_field(game, p2, LA_JINN)

    # Man-Eater Bug triggers its flip effect
    bug_def = MAN_EATER_BUG
    bug = place_on_field(game, p1, bug_def)

    events = bug_def.flip_effect(bug, game.state)

    assert target.zone == ZoneType.GRAVEYARD
    print("  PASS: test_man_eater_bug_flip")


def test_mst_destroys_spell_trap():
    """Test Mystical Space Typhoon destroys a set spell/trap."""
    game, p1, p2 = make_test_game()

    # P2 has a set trap
    trap = set_trap(game, p2, MIRROR_FORCE)
    assert trap.zone == ZoneType.SPELL_TRAP_ZONE

    resolve_event = Event(
        type=EventType.YGO_ACTIVATE_SPELL,
        payload={'card_id': 'mst', 'player': p1.id, 'targets': [trap.id]},
        source='mst', controller=p1.id,
    )
    events = MYSTICAL_SPACE_TYPHOON.resolve(resolve_event, game.state)

    assert trap.zone == ZoneType.GRAVEYARD
    print("  PASS: test_mst_destroys_spell_trap")


def test_deck_sizes():
    """Verify deck sizes are correct (40 cards each)."""
    assert len(WARRIOR_DECK) == 40, f"Warrior deck: {len(WARRIOR_DECK)}"
    assert len(SPELLCASTER_DECK) == 40, f"Spellcaster deck: {len(SPELLCASTER_DECK)}"
    assert len(YUGI_DECK) == 40, f"Yugi deck: {len(YUGI_DECK)}"
    assert len(KAIBA_DECK) == 40, f"Kaiba deck: {len(KAIBA_DECK)}"
    print("  PASS: test_deck_sizes")


def test_card_registry():
    """Test that all cards are in the registry."""
    from src.cards.yugioh import ALL_YGO_CARDS
    assert len(ALL_YGO_CARDS) > 50, f"Only {len(ALL_YGO_CARDS)} cards"
    assert "Dark Magician" in ALL_YGO_CARDS
    assert "Blue-Eyes White Dragon" in ALL_YGO_CARDS
    assert "Mirror Force" in ALL_YGO_CARDS
    assert "Dark Hole" in ALL_YGO_CARDS
    print("  PASS: test_card_registry")


def test_fusion_blue_eyes_ultimate():
    """Test Blue-Eyes Ultimate Dragon Fusion from Extra Deck."""
    game, p1, p2 = make_test_game()
    summon_mgr = YugiohSummonManager(game.state)

    # Put 3 BEWD on field/hand
    bewd1 = place_on_field(game, p1, BLUE_EYES_WHITE_DRAGON)
    bewd2 = place_on_field(game, p1, BLUE_EYES_WHITE_DRAGON)
    bewd3 = add_to_hand(game, p1, BLUE_EYES_WHITE_DRAGON)

    # Put Ultimate in Extra Deck
    ultimate = game.create_object(
        name=BLUE_EYES_ULTIMATE_DRAGON.name, owner_id=p1.id, zone=ZoneType.EXTRA_DECK,
        characteristics=Characteristics(types={CardType.YGO_MONSTER}),
        card_def=BLUE_EYES_ULTIMATE_DRAGON,
    )

    events = summon_mgr.fusion_summon(
        p1.id, ultimate.id, [bewd1.id, bewd2.id, bewd3.id]
    )

    assert ultimate.zone == ZoneType.MONSTER_ZONE
    assert ultimate.card_def.atk == 4500
    assert bewd1.zone == ZoneType.GRAVEYARD
    assert bewd2.zone == ZoneType.GRAVEYARD
    assert bewd3.zone == ZoneType.GRAVEYARD
    print("  PASS: test_fusion_blue_eyes_ultimate")


# =============================================================================
# Run all tests
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Yu-Gi-Oh! Stage 4 Tests — Card Effects")
    print("=" * 60)

    tests = [
        test_dark_hole_destroys_all,
        test_mirror_force_destroys_atk_opponents,
        test_monster_reborn_revives,
        test_swords_flips_face_down,
        test_magic_cylinder_damage,
        test_ring_of_destruction,
        test_solemn_judgment_lp,
        test_man_eater_bug_flip,
        test_mst_destroys_spell_trap,
        test_deck_sizes,
        test_card_registry,
        test_fusion_blue_eyes_ultimate,
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
