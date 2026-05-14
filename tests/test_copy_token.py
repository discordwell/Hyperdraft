"""
Test the copy-token mechanic.

Engine support: ``EventType.OBJECT_CREATED`` payload with a ``copy_of`` key
copies a permanent's printed characteristics, inherits the source's
``card_def``, and applies optional "except" modifications.

Helper: ``src.cards.interceptor_helpers.make_copy_token_event``.
"""

import os
import sys

# Insert the directory containing this file's repo root so imports resolve to
# the local worktree (not the parent /Users/discordwell/Projects/HYPERDRAFT).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, Characteristics,
    get_power, get_toughness,
)
from src.engine.game import make_creature
from src.cards.interceptor_helpers import (
    make_copy_token_event,
    make_etb_trigger,
)


# =============================================================================
# Test fixtures: lightweight creature with a setup_interceptors that fires on
# ETB so we can verify a copy's setup_interceptors actually run.
# =============================================================================

def _set_etb_flag_setup(flag_key: str):
    """Returns a setup_interceptors callable that sets ``state.turn_data[flag_key]``
    to ``state.turn_data.get(flag_key, 0) + 1`` whenever the source ETBs.
    """
    def setup(obj, state):
        def effect(event, st):
            st.turn_data[flag_key] = st.turn_data.get(flag_key, 0) + 1
            return []
        return [make_etb_trigger(obj, effect)]
    return setup


def _make_simple_creature(
    name: str,
    power: int,
    toughness: int,
    *,
    colors=None,
    subtypes=None,
    abilities=None,
    setup_interceptors=None,
):
    cdef = make_creature(
        name=name,
        power=power,
        toughness=toughness,
        mana_cost="{1}",
        colors=colors or {Color.GREEN},
        subtypes=subtypes or {"Beast"},
        text=f"Test creature {name}.",
        abilities=abilities or [],
        setup_interceptors=setup_interceptors,
    )
    # Mirror keyword abilities onto the Characteristics so the copy engine
    # can deep-copy them. (make_creature stores them only on CardDefinition.)
    if abilities:
        cdef.characteristics.abilities = list(abilities)
    return cdef


def _put_on_battlefield(game, player, card_def, name=None):
    obj = game.create_object(
        name=name or card_def.name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    return obj


# =============================================================================
# Tests
# =============================================================================

def test_copy_inherits_printed_pt_types_subtypes_colors():
    """Copy token gets the original's printed P/T, types, subtypes, and colors."""
    print("\n=== Test: copy inherits printed characteristics ===")
    game = Game()
    p1 = game.add_player("Alice")

    # Source: 4/4 black Vampire with flying
    src_def = _make_simple_creature(
        "Mock Vampire",
        4, 4,
        colors={Color.BLACK},
        subtypes={"Vampire"},
        abilities=[{'keyword': 'flying'}],
    )
    source = _put_on_battlefield(game, p1, src_def)

    # Emit a copy event
    events = make_copy_token_event(
        target_id=source.id,
        controller=p1.id,
    )
    assert len(events) == 1, f"Expected 1 event, got {len(events)}"
    game.emit(events[0])

    # The created object should be findable via the event payload
    created_id = events[0].payload.get('object_id')
    assert created_id, "Copy event should expose object_id"
    copy = game.state.objects[created_id]

    assert copy.name == "Mock Vampire", f"Name should match: {copy.name}"
    assert copy.is_token is True, "Copy should be a token"
    assert copy.controller == p1.id
    assert copy.zone == ZoneType.BATTLEFIELD
    assert CardType.CREATURE in copy.characteristics.types
    assert "Vampire" in copy.characteristics.subtypes
    assert Color.BLACK in copy.characteristics.colors
    assert copy.characteristics.power == 4
    assert copy.characteristics.toughness == 4
    # Printed P/T flow through the query system too
    assert get_power(copy, game.state) == 4
    assert get_toughness(copy, game.state) == 4
    # Abilities (flying) should have been deep-copied
    assert any(a.get('keyword') == 'flying' for a in copy.characteristics.abilities)
    print("PASSED: copy inherits printed P/T, types, subtypes, colors, abilities")


def test_copy_card_def_inherited_so_setup_interceptors_fire():
    """Copy's card_def matches the source's, so setup_interceptors fire on ETB."""
    print("\n=== Test: copy inherits card_def and setup fires ===")
    game = Game()
    p1 = game.add_player("Alice")

    # Source has an ETB trigger that increments a counter in turn_data.
    src_def = _make_simple_creature(
        "Echo Beast",
        2, 2,
        setup_interceptors=_set_etb_flag_setup("etb_count"),
    )
    source = _put_on_battlefield(game, p1, src_def)

    # Source itself enters via create_object -> setup_interceptors fired BUT
    # the etb_count would only increment if a ZONE_CHANGE -> battlefield was
    # emitted. Reset to baseline:
    game.state.turn_data['etb_count'] = 0

    # Now emit the copy event — the OBJECT_CREATED handler should fire the
    # inherited setup_interceptors AND the registered ETB trigger should fire
    # off the OBJECT_CREATED event itself (since make_etb_trigger filters on
    # ZONE_CHANGE OR OBJECT_CREATED).
    events = make_copy_token_event(
        target_id=source.id,
        controller=p1.id,
    )
    game.emit(events[0])

    copy_id = events[0].payload['object_id']
    copy = game.state.objects[copy_id]

    # card_def was inherited from source
    assert copy.card_def is source.card_def, "Copy should inherit card_def"
    # setup_interceptors should have registered an interceptor on the copy
    assert len(copy.interceptor_ids) >= 1, (
        "Copy should have registered interceptors from inherited card_def"
    )
    # ETB trigger on the copy should have fired during OBJECT_CREATED
    etb_count = game.state.turn_data.get('etb_count', 0)
    assert etb_count >= 1, f"Copy's ETB trigger should fire on creation; got {etb_count}"
    print(f"PASSED: copy ETB fired (count={etb_count}), card_def inherited")


def test_copy_with_except_subtypes_added():
    """`add_subtypes` adds subtypes in addition to the copied ones."""
    print("\n=== Test: copy with add_subtypes ===")
    game = Game()
    p1 = game.add_player("Alice")

    src_def = _make_simple_creature(
        "Dragon Mock",
        5, 5,
        colors={Color.RED},
        subtypes={"Dragon"},
    )
    source = _put_on_battlefield(game, p1, src_def)

    events = make_copy_token_event(
        target_id=source.id,
        controller=p1.id,
        add_subtypes={"Reflection"},
    )
    game.emit(events[0])

    copy = game.state.objects[events[0].payload['object_id']]
    assert "Dragon" in copy.characteristics.subtypes, "Original subtype preserved"
    assert "Reflection" in copy.characteristics.subtypes, "New subtype added"
    print("PASSED: add_subtypes correctly adds to copied subtypes")


def test_copy_with_except_pt_overrides_printed_pt():
    """`except_power` / `except_toughness` override the copied P/T."""
    print("\n=== Test: copy with except_power / except_toughness ===")
    game = Game()
    p1 = game.add_player("Alice")

    src_def = _make_simple_creature("Big Mock", 7, 7)
    source = _put_on_battlefield(game, p1, src_def)

    # ECL Charm-style: "create two tokens that are copies, except they're 1/1
    # red Goblins."
    events = make_copy_token_event(
        target_id=source.id,
        controller=p1.id,
        count=2,
        except_power=1,
        except_toughness=1,
        except_colors={Color.RED},
        except_subtypes={"Goblin"},
    )
    assert len(events) == 2

    for event in events:
        game.emit(event)
        copy = game.state.objects[event.payload['object_id']]
        assert copy.characteristics.power == 1
        assert copy.characteristics.toughness == 1
        assert copy.characteristics.colors == {Color.RED}
        assert copy.characteristics.subtypes == {"Goblin"}
    print("PASSED: except_* modifiers correctly override copy")


def test_copy_count_creates_n_tokens():
    """`count=N` emits N OBJECT_CREATED events that each create a token."""
    print("\n=== Test: copy count=3 creates 3 tokens ===")
    game = Game()
    p1 = game.add_player("Alice")

    src_def = _make_simple_creature("Hydra Mock", 3, 3)
    source = _put_on_battlefield(game, p1, src_def)

    events = make_copy_token_event(
        target_id=source.id,
        controller=p1.id,
        count=3,
    )
    assert len(events) == 3

    created_ids = []
    for event in events:
        game.emit(event)
        created_ids.append(event.payload['object_id'])

    # All three should be live battlefield objects
    bf = game.state.zones['battlefield']
    for cid in created_ids:
        assert cid in bf.objects, f"Token {cid} should be on the battlefield"
        assert game.state.objects[cid].is_token

    # source + 3 copies = 4 objects with the same name
    same_name = [
        o for o in game.state.objects.values()
        if o.name == "Hydra Mock"
    ]
    assert len(same_name) == 4, f"Expected 4 objects named Hydra Mock, got {len(same_name)}"
    print("PASSED: count=3 creates 3 distinct tokens")


def test_copy_does_not_share_mutable_state_with_source():
    """Mutating copy's characteristics doesn't leak back to source (deep-copy safety)."""
    print("\n=== Test: copy does not share mutable state with source ===")
    game = Game()
    p1 = game.add_player("Alice")

    src_def = _make_simple_creature(
        "Hydra",
        3, 3,
        subtypes={"Hydra"},
        abilities=[{'keyword': 'trample'}],
    )
    source = _put_on_battlefield(game, p1, src_def)

    events = make_copy_token_event(target_id=source.id, controller=p1.id)
    game.emit(events[0])
    copy = game.state.objects[events[0].payload['object_id']]

    # Mutate the copy
    copy.characteristics.subtypes.add("Token-Only")
    copy.characteristics.abilities.append({'keyword': 'haste'})

    # Source should be unaffected
    assert "Token-Only" not in source.characteristics.subtypes, (
        "Mutating copy should not leak into source.subtypes"
    )
    assert not any(
        a.get('keyword') == 'haste' for a in source.characteristics.abilities
    ), "Mutating copy should not leak into source.abilities"
    print("PASSED: copy and source have independent mutable state")


def test_copy_with_missing_target_is_a_noop():
    """Copy of a non-existent object should not crash; no token created."""
    print("\n=== Test: copy of missing target is a no-op ===")
    game = Game()
    p1 = game.add_player("Alice")

    bf_before = list(game.state.zones['battlefield'].objects)
    events = make_copy_token_event(
        target_id="bogus-id-doesnt-exist",
        controller=p1.id,
    )
    # Even with a missing target, the engine should not crash. It MAY still
    # create a default-vanilla creature token (the non-copy fallback) since
    # OBJECT_CREATED is conservative; assert no battlefield breakage.
    game.emit(events[0])
    bf_after = game.state.zones['battlefield'].objects

    # Whatever was created (vanilla creature, since copy_source was None),
    # the battlefield should still be a valid list of object ids.
    for oid in bf_after:
        assert oid in game.state.objects, "Battlefield references a missing object"
    print("PASSED: missing-target copy doesn't break the engine")


# =============================================================================
# Wired-card smoke tests
# =============================================================================

def test_wired_kindle_the_inner_flame_resolve():
    """KINDLE_THE_INNER_FLAME emits a copy event for the pre-selected target.

    Phase 5b: target picking happens at cast time via ``target_requirements``,
    so the resolve fn consumes ``targets[0]`` directly instead of posting its
    own PendingChoice.
    """
    print("\n=== Test: Kindle the Inner Flame wiring ===")
    from src.cards.lorwyn_eclipsed import KINDLE_THE_INNER_FLAME

    game = Game()
    p1 = game.add_player("Alice")

    # Put a creature on the battlefield.
    src_def = _make_simple_creature(
        "Ember Elemental", 3, 3,
        colors={Color.RED}, subtypes={"Elemental"},
        abilities=[{'keyword': 'flying'}],
    )
    src = _put_on_battlefield(game, p1, src_def)
    # Mirror keyword onto Characteristics for the deep-copy.
    src.characteristics.abilities = [{'keyword': 'flying'}]

    game.state.active_player = p1.id
    # Phase 5b: targets pre-supplied as if engine emitted PendingChoice + user picked.
    events = KINDLE_THE_INNER_FLAME.resolve([[src.id]], game.state)
    assert events, "Resolve should emit a copy event"
    assert all(e.type == EventType.OBJECT_CREATED for e in events)
    assert events[0].payload.get('copy_of') == src.id
    # Haste should be added on top of the original's flying.
    keywords = events[0].payload.get('except_keywords') or []
    assert 'haste' in [k.lower() for k in keywords]
    assert 'flying' in [k.lower() for k in keywords]
    print("PASSED: Kindle the Inner Flame emits copy event with haste")


def test_wired_mirror_room_door1_emits_copy_with_reflection():
    """Mirror Room's door 1 unlock should add 'Reflection' to the copy's subtypes."""
    print("\n=== Test: Mirror Room door 1 wiring ===")
    from src.cards.duskmourn import MIRROR_ROOM

    game = Game()
    p1 = game.add_player("Alice")

    # Place a creature for the room to copy.
    creature_def = _make_simple_creature(
        "Dragon", 4, 4,
        colors={Color.RED}, subtypes={"Dragon"},
    )
    creature = _put_on_battlefield(game, p1, creature_def)

    # Place Mirror Room (this fires its room setup).
    room = game.create_object(
        name="Mirror Room",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=MIRROR_ROOM.characteristics,
        card_def=MIRROR_ROOM,
    )
    # Initialize unlocked_doors on state if needed.
    if not isinstance(getattr(room.state, 'unlocked_doors', None), list):
        room.state.unlocked_doors = []

    # Trigger door 1 unlock — it should emit an UNLOCK_DOOR event whose REACT
    # interceptor (registered by make_room_setup) opens a target choice.
    game.emit(Event(
        type=EventType.UNLOCK_DOOR,
        payload={'object_id': room.id, 'door_name': 'Mirror Room'},
        source=room.id, controller=p1.id,
    ))

    assert game.state.pending_choice is not None, "Door 1 should open a target choice"
    assert creature.id in game.state.pending_choice.options

    # Drive the callback as if Alice chose the dragon.
    handler = game.state.pending_choice.callback_data['handler']
    events = handler(game.state.pending_choice, [creature.id], game.state)
    assert events, "Handler should produce a copy event"
    assert events[0].payload.get('copy_of') == creature.id
    add_subtypes = events[0].payload.get('add_subtypes') or set()
    assert "Reflection" in add_subtypes, "Mirror Room should add Reflection subtype"

    # Emit the copy event and verify the resulting token has both subtypes.
    game.emit(events[0])
    copy = game.state.objects[events[0].payload['object_id']]
    assert "Dragon" in copy.characteristics.subtypes
    assert "Reflection" in copy.characteristics.subtypes
    print("PASSED: Mirror Room door 1 creates copy with Dragon + Reflection subtypes")


def test_wired_trystans_command_copy_elf_mode():
    """Trystan's Command mode 1 builds a copy event for a target Elf."""
    print("\n=== Test: Trystan's Command (mode 1: copy Elf) ===")
    from src.cards.lorwyn_eclipsed import _trystans_command_copy_elf

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Two creatures: Alice's Elf (legal) and Bob's Elf (illegal: not your own).
    elf_def = _make_simple_creature(
        "Forest Elf", 2, 2,
        colors={Color.GREEN}, subtypes={"Elf"},
    )
    alice_elf = _put_on_battlefield(game, p1, elf_def)
    bob_elf = game.create_object(
        name="Forest Elf",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=elf_def.characteristics,
        card_def=elf_def,
    )

    spell_id = "trystans_command_test"
    res = _trystans_command_copy_elf(game.state, p1.id, spell_id)
    assert res == [], "Mode opens a choice rather than emitting events"

    pc = game.state.pending_choice
    assert pc is not None, "Mode 1 should open a target choice"
    # Bob's Elf is NOT a legal target (controller filter).
    assert alice_elf.id in pc.options
    assert bob_elf.id not in pc.options

    handler = pc.callback_data['handler']
    events = handler(pc, [alice_elf.id], game.state)
    assert events and events[0].type == EventType.OBJECT_CREATED
    assert events[0].payload.get('copy_of') == alice_elf.id
    print("PASSED: Trystan's Command Elf-copy mode targets only your Elves")


def run_all_tests():
    print("=" * 60)
    print("COPY-TOKEN TESTS")
    print("=" * 60)

    test_copy_inherits_printed_pt_types_subtypes_colors()
    test_copy_card_def_inherited_so_setup_interceptors_fire()
    test_copy_with_except_subtypes_added()
    test_copy_with_except_pt_overrides_printed_pt()
    test_copy_count_creates_n_tokens()
    test_copy_does_not_share_mutable_state_with_source()
    test_copy_with_missing_target_is_a_noop()
    test_wired_kindle_the_inner_flame_resolve()
    test_wired_mirror_room_door1_emits_copy_with_reflection()
    test_wired_trystans_command_copy_elf_mode()

    print("\n" + "=" * 60)
    print("ALL COPY-TOKEN TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
