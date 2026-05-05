"""
"Until your next turn" duration tests.

Covers:
- Animation with duration='until_your_next_turn' persists through opponent
  turn and clears at the start of the original controller's NEXT turn.
- TURN_END / EOT cleanup does NOT remove until-next-turn interceptors.
- Multi-player: animation owned by Alice survives Bob's *and* Carol's turns
  and only clears when Alice's next turn begins.
- Rootwise Survivor: Survival trigger fires correctly; targeted land becomes
  a 0/0 Elemental creature with haste and three +1/+1 counters; reverts at
  Rootwise's controller's TURN_START.
- Edge: animated land destroyed before next turn — cleanup is idempotent.
- Edge: multiple until-next-turn animations from different controllers are
  cleaned up independently (each on its respective owner's turn).

Implementation under test:
- Engine: ``src/engine/turn.py`` ``TurnManager._do_until_your_next_turn_cleanup``
  invoked from ``run_turn`` before TURN_START.
- Helper: ``src/cards/interceptor_helpers.make_until_next_turn_animation``.
- Card (DSK): Rootwise Survivor (``rootwise_survivor_setup``).
"""

import os
import sys
import asyncio

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    make_creature, make_land,
    get_power, get_toughness, get_types, has_ability,
)
from src.cards.interceptor_helpers import (
    becomes_creature,
    make_until_next_turn_animation,
)


# -----------------------------------------------------------------------------
# Test harness
# -----------------------------------------------------------------------------

def _new_game(*names):
    """Create a Game with the given player names (in turn order)."""
    game = Game()
    pids = []
    for n in names:
        p = game.add_player(n)
        pids.append(p.id)
    game.turn_manager.set_turn_order(pids)
    game.state.active_player = pids[0]
    return (game, *pids)


def _spawn_land(game, controller, name="Forest", subtypes=None):
    """Drop a Land on the battlefield directly."""
    if subtypes is None:
        subtypes = {"Forest"}
    land_def = make_land(name=name, text="", subtypes=subtypes)
    obj = game.create_object(
        name=land_def.name,
        owner_id=controller,
        zone=ZoneType.BATTLEFIELD,
        characteristics=land_def.characteristics,
        card_def=land_def,
    )
    obj.controller = controller
    return obj


def _spawn_creature(game, controller, name, *, power=2, toughness=2, tapped=False):
    cd = make_creature(
        name=name,
        power=power, toughness=toughness,
        mana_cost="{1}{G}",
        colors={Color.GREEN},
        subtypes={"Survivor"},
    )
    obj = game.create_object(
        name=cd.name,
        owner_id=controller,
        zone=ZoneType.BATTLEFIELD,
        characteristics=cd.characteristics,
        card_def=cd,
    )
    obj.controller = controller
    obj.state.tapped = tapped
    return obj


def _run_turn(game, player_id):
    """Run one full turn for the given player."""
    return asyncio.run(game.turn_manager.run_turn(player_id))


# -----------------------------------------------------------------------------
# Core duration tests
# -----------------------------------------------------------------------------

def test_until_next_turn_persists_through_opponent_turn():
    print("\n=== Test: 'until your next turn' persists through opponent turn ===")
    game, alice, bob = _new_game("Alice", "Bob")
    land = _spawn_land(game, alice, "Forest", subtypes={"Forest"})

    # Apply animation on Alice's turn (active_player = alice).
    make_until_next_turn_animation(
        land, game.state,
        controller=alice,
        power=3, toughness=3,
        subtypes={"Elemental"},
        keywords=["haste"],
    )
    assert CardType.CREATURE in get_types(land, game.state)
    assert get_power(land, game.state) == 3
    assert "Elemental" in land.characteristics.subtypes

    # Run Bob's turn — animation should still be live at all phases of Bob's turn.
    _run_turn(game, bob)
    types_after_bob = get_types(land, game.state)
    print(f"  After Bob's turn: types={types_after_bob}, P={get_power(land, game.state)}/T={get_toughness(land, game.state)}")
    assert CardType.CREATURE in types_after_bob, (
        "Animation should still be active during/after opponent's turn"
    )
    assert get_power(land, game.state) == 3
    assert "Elemental" in land.characteristics.subtypes

    # Now run Alice's NEXT turn — at TURN_START the cleanup sweeps the
    # interceptors. Check state after run_turn finished.
    _run_turn(game, alice)
    types_after_alice = get_types(land, game.state)
    print(f"  After Alice's next turn start: types={types_after_alice}, P={get_power(land, game.state)}/T={get_toughness(land, game.state)}")
    assert CardType.CREATURE not in types_after_alice, (
        "Animation should have been cleared at Alice's next TURN_START"
    )
    assert "Elemental" not in land.characteristics.subtypes, (
        "Subtype dual-write should be reverted"
    )
    print("  PASS: until_your_next_turn persists across opponent turn, expires on owner's next turn.")


def test_eot_cleanup_does_not_remove_until_next_turn():
    print("\n=== Test: EOT cleanup leaves 'until your next turn' interceptors alone ===")
    game, alice, bob = _new_game("Alice", "Bob")
    land = _spawn_land(game, alice, "Forest")

    make_until_next_turn_animation(
        land, game.state,
        controller=alice,
        power=4, toughness=4,
        subtypes={"Elemental"},
        keywords=["haste"],
    )
    pre_count = sum(
        1 for ic in game.state.interceptors.values()
        if getattr(ic, 'duration', None) == 'until_your_next_turn'
    )
    assert pre_count >= 4, f"Expected becomes_creature to install >=4 interceptors, got {pre_count}"

    # Run the EOT cleanup of Alice's turn directly (no TURN_START between).
    asyncio.run(game.turn_manager._do_cleanup_step())

    post_count = sum(
        1 for ic in game.state.interceptors.values()
        if getattr(ic, 'duration', None) == 'until_your_next_turn'
    )
    print(f"  Until-next-turn interceptors before/after cleanup: {pre_count} -> {post_count}")
    assert post_count == pre_count, (
        f"EOT cleanup should NOT remove until_your_next_turn interceptors "
        f"({pre_count} before, {post_count} after)"
    )
    # And the land is still a creature.
    assert CardType.CREATURE in get_types(land, game.state)
    print("  PASS: EOT cleanup does not eat until-next-turn effects.")


def test_multi_player_until_next_turn_only_clears_on_owner_turn():
    print("\n=== Test: 3-player game — animation clears only on owner's turn ===")
    game, alice, bob, carol = _new_game("Alice", "Bob", "Carol")
    land = _spawn_land(game, alice, "Forest")

    make_until_next_turn_animation(
        land, game.state,
        controller=alice,
        power=2, toughness=2,
        subtypes={"Elemental"},
        keywords=["haste"],
    )

    # Bob's turn — still active.
    _run_turn(game, bob)
    assert CardType.CREATURE in get_types(land, game.state), "Should survive Bob's turn"
    print("  After Bob's turn: still a creature.")

    # Carol's turn — still active (not Alice yet!).
    _run_turn(game, carol)
    assert CardType.CREATURE in get_types(land, game.state), (
        "Should survive Carol's turn (not Alice's!)"
    )
    print("  After Carol's turn: still a creature.")

    # Alice's next turn — clears.
    _run_turn(game, alice)
    assert CardType.CREATURE not in get_types(land, game.state), (
        "Should be cleared at Alice's TURN_START"
    )
    assert "Elemental" not in land.characteristics.subtypes
    print("  PASS: 3-player — animation only clears on owner's next turn.")


def test_multiple_until_next_turn_independent_owners():
    print("\n=== Test: Two animations with different controllers clean up independently ===")
    game, alice, bob = _new_game("Alice", "Bob")
    alice_land = _spawn_land(game, alice, "Forest")
    bob_land = _spawn_land(game, bob, "Mountain", subtypes={"Mountain"})

    # Alice animates her land on her turn.
    make_until_next_turn_animation(
        alice_land, game.state,
        controller=alice,
        power=3, toughness=3,
        subtypes={"Elemental"},
        keywords=["haste"],
    )
    # Pretend Bob also has animated his land "until *his* next turn" — install
    # the same way but with controller=bob (mid-turn timing trickery is fine
    # for a unit test of the cleanup mechanism).
    make_until_next_turn_animation(
        bob_land, game.state,
        controller=bob,
        power=4, toughness=4,
        subtypes={"Elemental"},
        keywords=["haste"],
    )
    assert CardType.CREATURE in get_types(alice_land, game.state)
    assert CardType.CREATURE in get_types(bob_land, game.state)

    # Run Bob's turn — at Bob's TURN_START, only Bob's animation should clear.
    _run_turn(game, bob)
    print(f"  After Bob's turn: Alice's land creature? {CardType.CREATURE in get_types(alice_land, game.state)}")
    print(f"  After Bob's turn: Bob's land creature? {CardType.CREATURE in get_types(bob_land, game.state)}")
    assert CardType.CREATURE in get_types(alice_land, game.state), (
        "Alice's animation should still be active (Bob's turn doesn't clear it)"
    )
    assert CardType.CREATURE not in get_types(bob_land, game.state), (
        "Bob's animation should have cleared at Bob's TURN_START"
    )
    assert "Elemental" not in bob_land.characteristics.subtypes, (
        "Bob's land subtype should revert"
    )

    # Now run Alice's next turn — Alice's animation clears.
    _run_turn(game, alice)
    assert CardType.CREATURE not in get_types(alice_land, game.state), (
        "Alice's animation should have cleared at her TURN_START"
    )
    print("  PASS: Multiple owners — each cleans up on their own turn.")


def test_animated_land_destroyed_before_next_turn_idempotent():
    print("\n=== Test: Animated land destroyed before next turn — cleanup is idempotent ===")
    game, alice, bob = _new_game("Alice", "Bob")
    land = _spawn_land(game, alice, "Forest")

    make_until_next_turn_animation(
        land, game.state,
        controller=alice,
        power=3, toughness=3,
        subtypes={"Elemental"},
        keywords=["haste"],
    )

    # Simulate the land being destroyed: move it to graveyard and pop the
    # interceptors that happened to be tied to it. The cleanup should not
    # crash.
    land.zone = ZoneType.GRAVEYARD
    bf = game.state.zones.get('battlefield')
    if bf and land.id in bf.objects:
        bf.objects.remove(land.id)
    gy_key = f"graveyard_{alice}"
    gy = game.state.zones.get(gy_key)
    if gy is not None and land.id not in gy.objects:
        gy.objects.append(land.id)

    # Run Alice's next turn — cleanup should run without errors.
    try:
        _run_turn(game, alice)
        ran_clean = True
    except Exception as ex:
        print(f"  Exception during run_turn: {ex}")
        ran_clean = False
    assert ran_clean, "Cleanup must not crash even if target object left battlefield"

    # Double-check the until-next-turn interceptors were removed.
    remaining = sum(
        1 for ic in game.state.interceptors.values()
        if getattr(ic, 'duration', None) == 'until_your_next_turn'
        and getattr(ic, 'controller', None) == alice
    )
    assert remaining == 0, (
        f"Expected 0 remaining alice-owned until_your_next_turn interceptors, got {remaining}"
    )
    print("  PASS: cleanup is robust to early destruction of the animated land.")


# -----------------------------------------------------------------------------
# Rootwise Survivor integration
# -----------------------------------------------------------------------------

def test_rootwise_survivor_animates_land_until_next_turn():
    print("\n=== Test: Rootwise Survivor — Survival animates land until next turn ===")
    from src.cards.duskmourn import ROOTWISE_SURVIVOR

    game, alice, bob = _new_game("Alice", "Bob")
    # Need a land for Rootwise to target.
    land = _spawn_land(game, alice, "Forest")

    # Spawn Rootwise (setup_interceptors runs in create_object on BATTLEFIELD).
    rs = game.create_object(
        name=ROOTWISE_SURVIVOR.name,
        owner_id=alice,
        zone=ZoneType.BATTLEFIELD,
        characteristics=ROOTWISE_SURVIVOR.characteristics,
        card_def=ROOTWISE_SURVIVOR,
    )
    rs.controller = alice
    rs.state.tapped = True  # Survival requires tapped at second main.
    game.state.active_player = alice

    # Pre-trigger sanity.
    assert CardType.CREATURE not in get_types(land, game.state)

    # Emit second main start — this fires Survival.
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={
            'phase': 'postcombat_main',
            'step': 'main',
            'active_player': alice,
            'turn_number': game.state.turn_number,
        },
    ))

    # Land should now be a creature with Elemental subtype + haste.
    types_after = get_types(land, game.state)
    print(f"  After Survival: types={types_after}, P={get_power(land, game.state)}/T={get_toughness(land, game.state)}")
    print(f"  Land subtypes: {land.characteristics.subtypes}")
    print(f"  Has haste: {has_ability(land, 'haste', game.state)}")

    assert CardType.CREATURE in types_after, "Land should have become a creature"
    assert CardType.LAND in types_after, "Land should still be a land"
    assert "Elemental" in land.characteristics.subtypes, "Should have Elemental subtype"
    assert has_ability(land, "haste", game.state), "Should gain haste"

    # Three +1/+1 counters were added (event in log).
    plus_one_counters = [
        e for e in game.state.event_log
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == land.id
        and e.payload.get('counter_type') == '+1/+1'
        and e.payload.get('amount') == 3
    ]
    assert plus_one_counters, "Expected COUNTER_ADDED amount=3 event"
    print("  +1/+1 counters event present.")

    # Animation is until_your_next_turn — survives Bob's turn.
    _run_turn(game, bob)
    print(f"  After Bob's turn: types={get_types(land, game.state)}")
    assert CardType.CREATURE in get_types(land, game.state), (
        "Animation should survive Bob's turn"
    )

    # On Alice's next turn-start, animation reverts.
    _run_turn(game, alice)
    print(f"  After Alice's next turn: types={get_types(land, game.state)}")
    assert CardType.CREATURE not in get_types(land, game.state), (
        "Animation should clear at Alice's TURN_START"
    )
    assert "Elemental" not in land.characteristics.subtypes, "Subtype dual-write reverted"
    print("  PASS: Rootwise Survivor animates land until controller's next turn.")


def test_rootwise_survivor_does_not_fire_when_untapped():
    print("\n=== Test: Rootwise Survivor — does NOT fire when untapped ===")
    from src.cards.duskmourn import ROOTWISE_SURVIVOR
    game, alice, bob = _new_game("Alice", "Bob")
    land = _spawn_land(game, alice, "Forest")

    rs = game.create_object(
        name=ROOTWISE_SURVIVOR.name,
        owner_id=alice,
        zone=ZoneType.BATTLEFIELD,
        characteristics=ROOTWISE_SURVIVOR.characteristics,
        card_def=ROOTWISE_SURVIVOR,
    )
    rs.controller = alice
    rs.state.tapped = False  # untapped — Survival shouldn't fire.
    game.state.active_player = alice

    game.emit(Event(
        type=EventType.PHASE_START,
        payload={
            'phase': 'postcombat_main',
            'step': 'main',
            'active_player': alice,
            'turn_number': game.state.turn_number,
        },
    ))

    types_after = get_types(land, game.state)
    print(f"  Land types (untapped Rootwise): {types_after}")
    assert CardType.CREATURE not in types_after, (
        "Land should NOT become a creature when Rootwise is untapped"
    )
    print("  PASS: Rootwise's Survival is gated on tapped state.")


# -----------------------------------------------------------------------------
# Runner
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_until_next_turn_persists_through_opponent_turn,
        test_eot_cleanup_does_not_remove_until_next_turn,
        test_multi_player_until_next_turn_only_clears_on_owner_turn,
        test_multiple_until_next_turn_independent_owners,
        test_animated_land_destroyed_before_next_turn_idempotent,
        test_rootwise_survivor_animates_land_until_next_turn,
        test_rootwise_survivor_does_not_fire_when_untapped,
    ]
    failures = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failures.append((t.__name__, str(e)))
            print(f"  FAIL: {t.__name__}: {e}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            failures.append((t.__name__, repr(e)))
            print(f"  ERROR: {t.__name__}: {e!r}")
    print()
    if failures:
        print(f"FAILURES: {len(failures)}/{len(tests)}")
        for n, m in failures:
            print(f"  - {n}: {m}")
        sys.exit(1)
    else:
        print(f"All {len(tests)} tests passed.")
