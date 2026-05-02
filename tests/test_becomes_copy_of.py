"""Tests for becomes_copy_of continuous-effect copy helper.

`becomes_copy_of` is the sibling of `becomes_creature` for "X becomes a copy
of Y until end of turn." Distinct from token-copy (zone.py copy_of branch),
this OVERRIDES an existing permanent's queryable characteristics via QUERY
interceptors.

Reference cards: Oko, the Ringleader; Fleeting Reflection; Likeness Looter.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    make_creature,
    get_power, get_toughness, get_types, get_subtypes, get_colors,
    has_ability,
)
from src.engine.queries import get_supertypes
from src.cards.interceptor_helpers import becomes_copy_of


# =============================================================================
# Helpers
# =============================================================================

def _make_creature_def(name, power, toughness, *, colors=None, subtypes=None,
                      abilities=None):
    cdef = make_creature(
        name=name,
        power=power, toughness=toughness,
        mana_cost="{2}",
        colors=colors or {Color.GREEN},
        subtypes=subtypes or {"Beast"},
        text=f"Test creature {name}.",
        abilities=abilities or [],
    )
    if abilities:
        cdef.characteristics.abilities = list(abilities)
    return cdef


def _put_on_battlefield(game, player, card_def):
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    return obj


# =============================================================================
# Tests
# =============================================================================

def test_basic_copy_mirrors_source():
    """target becomes_copy_of source -> matches power/toughness/subtypes."""
    print("\n=== Test: basic copy mirrors source ===")
    game = Game()
    p1 = game.add_player("Alice")

    src_def = _make_creature_def(
        "Mock Dragon", 5, 5,
        colors={Color.RED}, subtypes={"Dragon"},
        abilities=[{'keyword': 'flying'}],
    )
    target_def = _make_creature_def(
        "Plain Goblin", 1, 1,
        colors={Color.RED}, subtypes={"Goblin"},
    )

    source = _put_on_battlefield(game, p1, src_def)
    target = _put_on_battlefield(game, p1, target_def)

    # Sanity: target is a 1/1 Goblin before copy.
    assert get_power(target, game.state) == 1
    assert get_toughness(target, game.state) == 1
    assert "Goblin" in get_subtypes(target, game.state)

    becomes_copy_of(target, source, game.state)

    # After: target now reads as a 5/5 Dragon with flying.
    assert get_power(target, game.state) == 5, (
        f"expected 5 power, got {get_power(target, game.state)}"
    )
    assert get_toughness(target, game.state) == 5
    subs = get_subtypes(target, game.state)
    assert "Dragon" in subs, f"expected Dragon in subtypes, got {subs}"
    assert "Goblin" not in subs, "original Goblin subtype must not survive copy"
    types = get_types(target, game.state)
    assert CardType.CREATURE in types
    colors = get_colors(target, game.state)
    assert Color.RED in colors
    assert has_ability(target, "flying", game.state), "should inherit flying"

    # Direct subtypes read (dual-write) is also correct.
    assert "Dragon" in target.characteristics.subtypes
    assert "Goblin" not in target.characteristics.subtypes
    print("PASS: basic copy mirrors source")


def test_live_source_pump_propagates():
    """+1/+1 counter on source -> target's power tracks (live read)."""
    print("\n=== Test: live source pump propagates ===")
    game = Game()
    p1 = game.add_player("Alice")

    src_def = _make_creature_def("Hydra", 3, 3)
    target_def = _make_creature_def("Squire", 1, 1)
    source = _put_on_battlefield(game, p1, src_def)
    target = _put_on_battlefield(game, p1, target_def)

    becomes_copy_of(target, source, game.state)

    assert get_power(target, game.state) == 3
    assert get_toughness(target, game.state) == 3

    # Apply a +1/+1 counter on the source.
    source.state.counters['+1/+1'] = 2

    # Now target should read 5/5 because the QUERY chain re-evaluates.
    assert get_power(target, game.state) == 5, (
        f"expected 5 power after +2/+2 on source, got {get_power(target, game.state)}"
    )
    assert get_toughness(target, game.state) == 5
    print("PASS: live source pump propagates to target")


def test_except_keywords_overrides():
    """except_keywords replaces the source's keywords, even if absent."""
    print("\n=== Test: except_keywords overrides ===")
    game = Game()
    p1 = game.add_player("Alice")

    # Source has trample but NO hexproof.
    src_def = _make_creature_def(
        "Trampler", 3, 3,
        abilities=[{'keyword': 'trample'}],
    )
    target_def = _make_creature_def("Plain", 1, 1)
    source = _put_on_battlefield(game, p1, src_def)
    target = _put_on_battlefield(game, p1, target_def)

    becomes_copy_of(target, source, game.state, except_keywords=['hexproof'])

    # Target should have hexproof (override) but NOT trample (replaced).
    assert has_ability(target, "hexproof", game.state), (
        "except_keywords=['hexproof'] should grant hexproof"
    )
    assert not has_ability(target, "trample", game.state), (
        "except_keywords replaces source keywords; trample shouldn't pass through"
    )
    print("PASS: except_keywords overrides source keywords")


def test_end_of_turn_cleanup():
    """After cleanup step, target reverts to printed characteristics."""
    print("\n=== Test: end of turn cleanup ===")
    import asyncio

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.state.active_player = p1.id

    src_def = _make_creature_def(
        "Mock Dragon", 5, 5,
        colors={Color.RED}, subtypes={"Dragon"},
        abilities=[{'keyword': 'flying'}],
    )
    target_def = _make_creature_def(
        "Plain Goblin", 1, 1,
        colors={Color.RED}, subtypes={"Goblin"},
    )
    source = _put_on_battlefield(game, p1, src_def)
    target = _put_on_battlefield(game, p1, target_def)

    becomes_copy_of(target, source, game.state)

    assert get_power(target, game.state) == 5
    assert "Dragon" in get_subtypes(target, game.state)
    assert "Goblin" not in target.characteristics.subtypes

    # Run a cleanup step via the game's existing turn manager.
    tm = game.turn_manager
    tm.turn_state.active_player_id = p1.id
    asyncio.run(tm._do_cleanup_step())

    # After cleanup: target reverts.
    assert get_power(target, game.state) == 1, (
        f"expected revert to printed 1 power, got {get_power(target, game.state)}"
    )
    assert get_toughness(target, game.state) == 1
    subs_after = get_subtypes(target, game.state)
    assert "Goblin" in subs_after, f"expected Goblin restored, got {subs_after}"
    assert "Dragon" not in subs_after, "Dragon should be gone after cleanup"
    # Direct dual-write is also restored.
    assert "Goblin" in target.characteristics.subtypes
    assert "Dragon" not in target.characteristics.subtypes
    print("PASS: cleanup step reverts target to printed characteristics")


def test_source_leaves_zone_falls_back_to_snapshot():
    """Source is removed from battlefield; target keeps snapshot characteristics."""
    print("\n=== Test: source leaves zone -> snapshot fallback ===")
    game = Game()
    p1 = game.add_player("Alice")

    src_def = _make_creature_def(
        "Mock Dragon", 5, 5,
        colors={Color.RED}, subtypes={"Dragon"},
        abilities=[{'keyword': 'flying'}],
    )
    target_def = _make_creature_def(
        "Plain Goblin", 1, 1,
        colors={Color.RED}, subtypes={"Goblin"},
    )
    source = _put_on_battlefield(game, p1, src_def)
    target = _put_on_battlefield(game, p1, target_def)

    becomes_copy_of(target, source, game.state)

    # Move source off the battlefield (simulate destroy).
    bf = game.state.zones['battlefield']
    if source.id in bf.objects:
        bf.objects.remove(source.id)
    source.zone = ZoneType.GRAVEYARD
    gy = game.state.zones.get(f'graveyard_{p1.id}')
    if gy is not None:
        gy.objects.append(source.id)

    # Target should still read as a Dragon (snapshot fallback).
    assert get_power(target, game.state) == 5, (
        f"expected snapshot 5 power after source left zone, got {get_power(target, game.state)}"
    )
    assert "Dragon" in get_subtypes(target, game.state)
    assert has_ability(target, "flying", game.state)
    print("PASS: snapshot fallback when source leaves zone")


def test_copy_of_copy_chain_propagates():
    """A copies B copies C -> A reads C's stats via the recursive query chain."""
    print("\n=== Test: copy-of-copy chain propagates ===")
    game = Game()
    p1 = game.add_player("Alice")

    base_def = _make_creature_def(
        "Eldrazi", 7, 7,
        colors={Color.GREEN}, subtypes={"Eldrazi"},
        abilities=[{'keyword': 'trample'}],
    )
    middle_def = _make_creature_def("Mid", 2, 2)
    far_def = _make_creature_def("Far", 1, 1)

    base = _put_on_battlefield(game, p1, base_def)
    middle = _put_on_battlefield(game, p1, middle_def)
    far = _put_on_battlefield(game, p1, far_def)

    # B copies C(=base).
    becomes_copy_of(middle, base, game.state)
    # A copies B.
    becomes_copy_of(far, middle, game.state)

    assert get_power(far, game.state) == 7, (
        f"chain copy should read 7, got {get_power(far, game.state)}"
    )
    assert get_toughness(far, game.state) == 7
    assert "Eldrazi" in get_subtypes(far, game.state)
    assert has_ability(far, "trample", game.state)
    print("PASS: copy-of-copy chain propagates the base's characteristics")


def test_oko_becomes_copy_with_hexproof():
    """Oko, the Ringleader: becomes_copy_of(target, except_keywords=['hexproof'])."""
    print("\n=== Test: Oko-style copy with hexproof rider ===")
    from src.cards.outlaws_thunder_junction import OKO_THE_RINGLEADER

    game = Game()
    p1 = game.add_player("Alice")

    # An Oko-controlled creature to copy.
    elk_def = _make_creature_def(
        "Generous Elk", 4, 4,
        colors={Color.GREEN}, subtypes={"Elk"},
    )
    elk = _put_on_battlefield(game, p1, elk_def)

    # Place Oko (planeswalker) on the battlefield. Run setup.
    oko = game.create_object(
        name=OKO_THE_RINGLEADER.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=OKO_THE_RINGLEADER.characteristics,
        card_def=OKO_THE_RINGLEADER,
    )

    # Oko's setup_interceptors registers a beginning-of-combat trigger;
    # we don't drive the full pipeline, just call the helper directly.
    becomes_copy_of(
        oko, elk, game.state,
        duration='end_of_turn',
        except_keywords=['hexproof'],
    )

    # Oko should now be a 4/4 Elk with hexproof.
    assert get_power(oko, game.state) == 4, (
        f"expected Oko's bot to have power 4, got {get_power(oko, game.state)}"
    )
    assert get_toughness(oko, game.state) == 4
    assert "Elk" in get_subtypes(oko, game.state)
    assert has_ability(oko, "hexproof", game.state), "should have hexproof"
    print("PASS: Oko bot becomes 4/4 Elk with hexproof rider")


def test_oko_setup_combat_trigger_registers():
    """Oko's setup_interceptors registers a combat-start REACT interceptor."""
    print("\n=== Test: Oko setup registers a beginning-of-combat trigger ===")
    from src.cards.outlaws_thunder_junction import OKO_THE_RINGLEADER

    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    oko = game.create_object(
        name=OKO_THE_RINGLEADER.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=OKO_THE_RINGLEADER.characteristics,
        card_def=OKO_THE_RINGLEADER,
    )
    # The setup function should have installed at least one interceptor on Oko.
    assert oko.interceptor_ids, "Oko setup should install at least one interceptor"
    print("PASS: Oko's setup registers a combat-start trigger")


def test_likeness_looter_setup_doesnt_crash():
    """Likeness Looter's setup wires the activated ability without crashing."""
    print("\n=== Test: Likeness Looter setup wires ability ===")
    from src.cards.wilds_of_eldraine import LIKENESS_LOOTER

    game = Game()
    p1 = game.add_player("Alice")
    looter = game.create_object(
        name=LIKENESS_LOOTER.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=LIKENESS_LOOTER.characteristics,
        card_def=LIKENESS_LOOTER,
    )
    # Should have at least the loot activated ability registered.
    assert looter.state.activated_abilities, (
        "Likeness Looter setup should register at least one activated ability"
    )
    print("PASS: Likeness Looter setup registers ability")


def test_fleeting_reflection_resolve_opens_choice():
    """Fleeting Reflection's resolve opens a target_with_callback choice."""
    print("\n=== Test: Fleeting Reflection resolve opens target choice ===")
    from src.cards.outlaws_thunder_junction import FLEETING_REFLECTION

    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    elk_def = _make_creature_def(
        "Plain Elk", 2, 2,
        colors={Color.GREEN}, subtypes={"Elk"},
    )
    other_def = _make_creature_def(
        "Hydra", 5, 5,
        colors={Color.GREEN}, subtypes={"Hydra"},
    )
    elk = _put_on_battlefield(game, p1, elk_def)
    hydra = _put_on_battlefield(game, p1, other_def)

    FLEETING_REFLECTION.resolve([], game.state)

    # The resolve fn opens a target choice for the controller's creature.
    assert game.state.pending_choice is not None, (
        "Fleeting Reflection.resolve should open a target choice"
    )
    pc = game.state.pending_choice
    assert pc.choice_type == "target_with_callback"
    assert elk.id in pc.options
    assert hydra.id in pc.options
    print("PASS: Fleeting Reflection opens target_with_callback choice")


# =============================================================================
# Round 9 follow-ups
# =============================================================================

def test_supertypes_copy_and_cleanup():
    """Copy a Legendary creature -> target gains Legendary; EOT restores."""
    print("\n=== Test: supertypes copy + cleanup ===")
    import asyncio

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.state.active_player = p1.id

    src_def = _make_creature_def(
        "Legendary Wurm", 6, 6,
        colors={Color.GREEN}, subtypes={"Wurm"},
    )
    src_def.characteristics.supertypes = {"Legendary"}

    target_def = _make_creature_def(
        "Vanilla Bear", 2, 2,
        colors={Color.GREEN}, subtypes={"Bear"},
    )
    # target is a basic, mundane bear with no supertypes.

    source = _put_on_battlefield(game, p1, src_def)
    target = _put_on_battlefield(game, p1, target_def)

    assert "Legendary" not in target.characteristics.supertypes

    becomes_copy_of(target, source, game.state)

    supers = get_supertypes(target, game.state)
    assert "Legendary" in supers, f"copy should grant Legendary, got {supers}"
    # Dual-write check.
    assert "Legendary" in target.characteristics.supertypes

    tm = game.turn_manager
    tm.turn_state.active_player_id = p1.id
    asyncio.run(tm._do_cleanup_step())

    supers_after = get_supertypes(target, game.state)
    assert "Legendary" not in supers_after, (
        f"cleanup should drop Legendary, got {supers_after}"
    )
    assert "Legendary" not in target.characteristics.supertypes
    print("PASS: supertypes copy + cleanup")


def test_source_leaves_then_eot_cleanup_still_works():
    """Source leaves the battlefield mid-turn -> EOT cleanup still reverts target.

    Edge case: the cleanup hook indexes by target_id, so the source going
    away shouldn't disturb it. This protects against AttributeError or
    leftover dual-write fields if the source object is garbage-collected
    or its zone changes.
    """
    print("\n=== Test: source leaves zone -> EOT cleanup still reverts ===")
    import asyncio

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.state.active_player = p1.id

    src_def = _make_creature_def(
        "Mock Dragon", 5, 5,
        colors={Color.RED}, subtypes={"Dragon"},
        abilities=[{'keyword': 'flying'}],
    )
    src_def.characteristics.supertypes = {"Legendary"}

    target_def = _make_creature_def(
        "Plain Goblin", 1, 1,
        colors={Color.RED}, subtypes={"Goblin"},
    )
    source = _put_on_battlefield(game, p1, src_def)
    target = _put_on_battlefield(game, p1, target_def)

    becomes_copy_of(target, source, game.state)
    # Mid-turn: while still copying, snapshot fields are dual-written.
    assert "Dragon" in target.characteristics.subtypes
    assert "Legendary" in target.characteristics.supertypes

    # Now the source leaves the battlefield mid-turn.
    bf = game.state.zones['battlefield']
    if source.id in bf.objects:
        bf.objects.remove(source.id)
    source.zone = ZoneType.GRAVEYARD
    gy = game.state.zones.get(f'graveyard_{p1.id}')
    if gy is not None:
        gy.objects.append(source.id)

    # While copy is active and source is in the GY, target still reads as
    # the snapshot.
    assert get_power(target, game.state) == 5
    assert "Dragon" in get_subtypes(target, game.state)
    assert "Legendary" in get_supertypes(target, game.state)

    # Now EOT cleanup runs. Even though source is gone, target should
    # cleanly revert.
    tm = game.turn_manager
    tm.turn_state.active_player_id = p1.id
    asyncio.run(tm._do_cleanup_step())

    assert get_power(target, game.state) == 1
    assert "Goblin" in get_subtypes(target, game.state)
    assert "Dragon" not in get_subtypes(target, game.state)
    assert "Legendary" not in get_supertypes(target, game.state)
    assert "Dragon" not in target.characteristics.subtypes
    assert "Legendary" not in target.characteristics.supertypes
    print("PASS: EOT cleanup reverts target even after source left zone")


# =============================================================================
# Driver
# =============================================================================

def run_all_tests():
    print("=" * 60)
    print("becomes_copy_of TESTS")
    print("=" * 60)

    test_basic_copy_mirrors_source()
    test_live_source_pump_propagates()
    test_except_keywords_overrides()
    test_end_of_turn_cleanup()
    test_source_leaves_zone_falls_back_to_snapshot()
    test_copy_of_copy_chain_propagates()
    test_oko_becomes_copy_with_hexproof()
    test_oko_setup_combat_trigger_registers()
    test_likeness_looter_setup_doesnt_crash()
    test_fleeting_reflection_resolve_opens_choice()
    test_supertypes_copy_and_cleanup()
    test_source_leaves_then_eot_cleanup_still_works()

    print("\n" + "=" * 60)
    print("ALL becomes_copy_of TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
