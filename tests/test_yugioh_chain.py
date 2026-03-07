"""
Yu-Gi-Oh! Stage 2 Tests — Chain System & Spell/Trap Lifecycle

Tests for chain mechanics, Spell Speed validation, Counter Trap exclusivity,
LIFO resolution, Quick-Play hand vs set, Continuous staying on field,
Equip, Field replacement, trap set timing.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.game import Game, make_ygo_monster, make_ygo_spell, make_ygo_trap
from src.engine.types import ZoneType, CardType, EventType
from src.engine.yugioh_chain import YugiohChainManager, ChainLink
from src.engine.yugioh_spells import YugiohSpellTrapManager


def make_test_game():
    game = Game(mode="yugioh")
    p1 = game.add_player("Player 1")
    p2 = game.add_player("Player 2")
    return game, p1, p2


def add_card_to_hand(game, player, card_def):
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics.__class__(types=set(card_def.characteristics.types)),
        card_def=card_def,
    )
    return obj


def set_card_on_field(game, player, card_def, turns_set=1):
    """Set a card face-down in the spell/trap zone."""
    turn_mgr = game.turn_manager
    turn_mgr.ygo_turn_state.active_player_id = player.id
    obj = add_card_to_hand(game, player, card_def)
    turn_mgr._do_set_spell_trap(player.id, {'card_id': obj.id})
    obj.state.turns_set = turns_set
    return obj


# =============================================================================
# Chain System Tests
# =============================================================================

def test_chain_start():
    """Test starting a chain."""
    game, p1, p2 = make_test_game()
    chain = YugiohChainManager(game.state)

    result = chain.start_chain(
        card_id="card1", controller=p1.id, spell_speed=1,
        card_name="Dark Hole"
    )
    assert result
    assert chain.is_chain_active
    assert len(chain.chain_links) == 1
    assert chain.current_spell_speed == 1
    print("  PASS: test_chain_start")


def test_chain_add_link_valid():
    """Test adding a valid link (SS2 responding to SS1)."""
    game, p1, p2 = make_test_game()
    chain = YugiohChainManager(game.state)

    chain.start_chain("card1", p1.id, 1, card_name="Spell")
    success, msg = chain.add_link("card2", p2.id, 2, card_name="Quick-Play")
    assert success
    assert len(chain.chain_links) == 2
    assert chain.current_spell_speed == 2
    print("  PASS: test_chain_add_link_valid")


def test_chain_ss_too_low():
    """Test that SS1 cannot respond to SS2."""
    game, p1, p2 = make_test_game()
    chain = YugiohChainManager(game.state)

    chain.start_chain("card1", p1.id, 2, card_name="Quick-Play")
    success, msg = chain.add_link("card2", p2.id, 1, card_name="Normal Spell")
    assert not success
    assert "lower" in msg.lower()
    print("  PASS: test_chain_ss_too_low")


def test_counter_trap_exclusivity():
    """Test that only SS3 can respond to SS3."""
    game, p1, p2 = make_test_game()
    chain = YugiohChainManager(game.state)

    chain.start_chain("card1", p1.id, 3, card_name="Counter Trap")

    # SS2 should fail
    success, msg = chain.add_link("card2", p2.id, 2, card_name="Normal Trap")
    assert not success
    assert "Counter Trap" in msg

    # SS3 should succeed
    success, msg = chain.add_link("card3", p2.id, 3, card_name="Another Counter")
    assert success
    print("  PASS: test_counter_trap_exclusivity")


def test_chain_lifo_resolution():
    """Test that chain resolves in LIFO order."""
    game, p1, p2 = make_test_game()
    chain = YugiohChainManager(game.state)

    resolve_order = []

    def make_resolve(name):
        def fn(state, targets):
            resolve_order.append(name)
            return []
        return fn

    chain.start_chain("c1", p1.id, 1, resolve_fn=make_resolve("CL1"), card_name="CL1")
    chain.add_link("c2", p2.id, 2, resolve_fn=make_resolve("CL2"), card_name="CL2")
    chain.add_link("c3", p1.id, 2, resolve_fn=make_resolve("CL3"), card_name="CL3")

    events = chain.resolve_chain()

    # Should resolve CL3 -> CL2 -> CL1 (LIFO)
    assert resolve_order == ["CL3", "CL2", "CL1"]
    assert not chain.is_chain_active  # Chain cleared after resolution
    print("  PASS: test_chain_lifo_resolution")


def test_chain_resolve_events():
    """Test that chain resolution emits proper events."""
    game, p1, p2 = make_test_game()
    chain = YugiohChainManager(game.state)

    chain.start_chain("c1", p1.id, 1, card_name="Dark Hole")
    events = chain.resolve_chain()

    assert len(events) >= 1
    assert events[0].type == EventType.YGO_CHAIN_RESOLVE
    assert events[0].payload['card_name'] == "Dark Hole"
    print("  PASS: test_chain_resolve_events")


# =============================================================================
# Spell/Trap Lifecycle Tests
# =============================================================================

def test_normal_spell_activation():
    """Test Normal Spell: activate from hand, goes to GY."""
    game, p1, p2 = make_test_game()
    spell_mgr = YugiohSpellTrapManager(game.state)

    spell_def = make_ygo_spell("Dark Hole", ygo_spell_type="Normal", text="Destroy all monsters")
    spell = add_card_to_hand(game, p1, spell_def)

    can, reason = spell_mgr.can_activate_spell(spell.id, p1.id, is_main_phase=True)
    assert can, reason

    events = spell_mgr.activate_spell(spell.id, p1.id)
    assert len(events) > 0
    assert spell.zone == ZoneType.GRAVEYARD  # Normal spell goes to GY
    print("  PASS: test_normal_spell_activation")


def test_quick_play_from_hand_your_turn():
    """Test Quick-Play Spell from hand on your turn."""
    game, p1, p2 = make_test_game()
    spell_mgr = YugiohSpellTrapManager(game.state)

    qp_def = make_ygo_spell("MST", ygo_spell_type="Quick-Play", text="Destroy 1 S/T")
    qp = add_card_to_hand(game, p1, qp_def)

    can, reason = spell_mgr.can_activate_spell(qp.id, p1.id, is_your_turn=True)
    assert can, reason
    print("  PASS: test_quick_play_from_hand_your_turn")


def test_quick_play_from_hand_opp_turn():
    """Test Quick-Play Spell from hand on opponent's turn (not allowed)."""
    game, p1, p2 = make_test_game()
    spell_mgr = YugiohSpellTrapManager(game.state)

    qp_def = make_ygo_spell("MST", ygo_spell_type="Quick-Play", text="Destroy 1 S/T")
    qp = add_card_to_hand(game, p1, qp_def)

    can, reason = spell_mgr.can_activate_spell(qp.id, p1.id, is_your_turn=False)
    assert not can
    assert "your turn" in reason.lower()
    print("  PASS: test_quick_play_from_hand_opp_turn")


def test_quick_play_set_activation():
    """Test Quick-Play set for 1+ turns can be activated on either turn."""
    game, p1, p2 = make_test_game()
    spell_mgr = YugiohSpellTrapManager(game.state)

    qp_def = make_ygo_spell("MST", ygo_spell_type="Quick-Play")
    qp = set_card_on_field(game, p1, qp_def, turns_set=1)

    # Should work even on opponent's turn
    can, reason = spell_mgr.can_activate_spell(qp.id, p1.id, is_your_turn=False)
    assert can, reason
    print("  PASS: test_quick_play_set_activation")


def test_continuous_spell_stays():
    """Test Continuous Spell stays on field after activation."""
    game, p1, p2 = make_test_game()
    spell_mgr = YugiohSpellTrapManager(game.state)

    cont_def = make_ygo_spell("Swords of Revealing Light", ygo_spell_type="Continuous")
    cont = add_card_to_hand(game, p1, cont_def)

    events = spell_mgr.activate_spell(cont.id, p1.id)
    # Continuous spells should move to S/T zone, not GY
    assert cont.zone == ZoneType.SPELL_TRAP_ZONE
    print("  PASS: test_continuous_spell_stays")


def test_field_spell_replaces():
    """Test Field Spell replaces existing one."""
    game, p1, p2 = make_test_game()
    spell_mgr = YugiohSpellTrapManager(game.state)

    field1_def = make_ygo_spell("Mountain", ygo_spell_type="Field")
    field1 = add_card_to_hand(game, p1, field1_def)
    spell_mgr.activate_spell(field1.id, p1.id)
    assert field1.zone == ZoneType.FIELD_SPELL_ZONE

    field2_def = make_ygo_spell("Forest", ygo_spell_type="Field")
    field2 = add_card_to_hand(game, p1, field2_def)
    spell_mgr.activate_spell(field2.id, p1.id)

    assert field2.zone == ZoneType.FIELD_SPELL_ZONE
    assert field1.zone == ZoneType.GRAVEYARD  # Old one destroyed
    print("  PASS: test_field_spell_replaces")


def test_trap_must_be_set():
    """Test that traps cannot be activated from hand."""
    game, p1, p2 = make_test_game()
    spell_mgr = YugiohSpellTrapManager(game.state)

    trap_def = make_ygo_trap("Mirror Force", ygo_trap_type="Normal")
    trap = add_card_to_hand(game, p1, trap_def)

    can, reason = spell_mgr.can_activate_trap(trap.id, p1.id)
    assert not can
    assert "set" in reason.lower()
    print("  PASS: test_trap_must_be_set")


def test_trap_set_timing():
    """Test that traps must be set for 1+ turns before activation."""
    game, p1, p2 = make_test_game()
    spell_mgr = YugiohSpellTrapManager(game.state)

    trap_def = make_ygo_trap("Mirror Force", ygo_trap_type="Normal")
    trap = set_card_on_field(game, p1, trap_def, turns_set=0)

    # Just set — cannot activate
    can, reason = spell_mgr.can_activate_trap(trap.id, p1.id)
    assert not can

    # After 1 turn
    trap.state.turns_set = 1
    can, reason = spell_mgr.can_activate_trap(trap.id, p1.id)
    assert can, reason
    print("  PASS: test_trap_set_timing")


def test_normal_trap_goes_to_gy():
    """Test Normal Trap goes to GY after resolution."""
    game, p1, p2 = make_test_game()
    spell_mgr = YugiohSpellTrapManager(game.state)

    trap_def = make_ygo_trap("Sakuretsu Armor", ygo_trap_type="Normal")
    trap = set_card_on_field(game, p1, trap_def, turns_set=1)

    events = spell_mgr.activate_trap(trap.id, p1.id)
    assert trap.zone == ZoneType.GRAVEYARD
    print("  PASS: test_normal_trap_goes_to_gy")


def test_continuous_trap_stays():
    """Test Continuous Trap stays on field after activation."""
    game, p1, p2 = make_test_game()
    spell_mgr = YugiohSpellTrapManager(game.state)

    cont_trap_def = make_ygo_trap("Call of the Haunted", ygo_trap_type="Continuous")
    cont_trap = set_card_on_field(game, p1, cont_trap_def, turns_set=1)

    events = spell_mgr.activate_trap(cont_trap.id, p1.id)
    # Continuous traps stay on field (in S/T zone)
    assert cont_trap.zone == ZoneType.SPELL_TRAP_ZONE
    print("  PASS: test_continuous_trap_stays")


def test_counter_trap_goes_to_gy():
    """Test Counter Trap goes to GY and has SS3."""
    game, p1, p2 = make_test_game()
    spell_mgr = YugiohSpellTrapManager(game.state)

    counter_def = make_ygo_trap("Solemn Judgment", ygo_trap_type="Counter")
    assert counter_def.spell_speed == 3  # Auto-set by make_ygo_trap

    counter = set_card_on_field(game, p1, counter_def, turns_set=1)
    events = spell_mgr.activate_trap(counter.id, p1.id)
    assert counter.zone == ZoneType.GRAVEYARD
    print("  PASS: test_counter_trap_goes_to_gy")


def test_chain_can_respond_check():
    """Test can_respond detects set traps that can chain."""
    game, p1, p2 = make_test_game()
    chain = YugiohChainManager(game.state)

    # Set a trap for P2
    trap_def = make_ygo_trap("Mirror Force", ygo_trap_type="Normal", spell_speed=2)
    trap = set_card_on_field(game, p2, trap_def, turns_set=1)

    # Start a chain at SS1
    chain.start_chain("c1", p1.id, 1, card_name="Spell")

    # P2 should be able to respond with their set trap
    assert chain.can_respond(p2.id)
    print("  PASS: test_chain_can_respond_check")


# =============================================================================
# Run all tests
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Yu-Gi-Oh! Stage 2 Tests — Chain & Spell/Trap")
    print("=" * 60)

    tests = [
        test_chain_start,
        test_chain_add_link_valid,
        test_chain_ss_too_low,
        test_counter_trap_exclusivity,
        test_chain_lifo_resolution,
        test_chain_resolve_events,
        test_normal_spell_activation,
        test_quick_play_from_hand_your_turn,
        test_quick_play_from_hand_opp_turn,
        test_quick_play_set_activation,
        test_continuous_spell_stays,
        test_field_spell_replaces,
        test_trap_must_be_set,
        test_trap_set_timing,
        test_normal_trap_goes_to_gy,
        test_continuous_trap_stays,
        test_counter_trap_goes_to_gy,
        test_chain_can_respond_check,
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
