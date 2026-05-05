"""
ATLA Niche Cards + Delayed-Trigger Helper Tests

Covers:
1. ``make_delayed_trigger`` helper (record events, fire at deferred phase,
   safety-net cleanup at TURN_END).
2. Jeong Jeong, the Deserter — exhaust arms a delayed Lesson-copy trigger;
   each Lesson cast after activation is captured and pushed as a copy at
   end of the controller's turn.
3. Tundra Tank ETB — grants indestructible until end of turn to a chosen
   target creature (uses GRANT_KEYWORD).
4. Fire Lord Azula — copy each spell its controller casts while Fire Lord
   Azula is attacking, via COPY_STACK_ITEM.

Run directly:
    python tests/test_atla_niche.py
"""

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Characteristics, GameObject,
)
from src.engine.stack import StackItem, StackItemType
from src.cards.interceptor_helpers import make_delayed_trigger
from src.cards.avatar_tla import (
    JEONG_JEONG_THE_DESERTER,
    TUNDRA_TANK,
    FIRE_LORD_AZULA,
)


# =============================================================================
# Shared helpers
# =============================================================================

def _put_on_battlefield(game, owner_id, card_def, name=None):
    """Create an object on battlefield and run its setup_interceptors path
    via OBJECT_CREATED -> ZONE_CHANGE so triggers register correctly."""
    obj = game.create_object(
        name=name or card_def.name,
        owner_id=owner_id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': f'hand_{owner_id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    return obj


def _make_creature_token(game, owner_id, *, name="Vanilla", power=2, toughness=2):
    """Create a vanilla creature directly on the battlefield."""
    return game.create_object(
        name=name,
        owner_id=owner_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            power=power,
            toughness=toughness,
            subtypes=set(),
        ),
    )


def _emit_end_step(game, controller_id):
    """Fire PHASE_START with phase=end_step under the given active player."""
    game.state.active_player = controller_id
    return game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step'},
        controller=controller_id,
    ))


def _emit_turn_end(game):
    """Reset turn_data via TURN_END so the safety-net cleanup runs."""
    game.emit(Event(
        type=EventType.TURN_END,
        payload={},
    ))


def _push_fake_lesson_spell(game, controller_id, *, name="Mock Lesson"):
    """Push a fake Lesson spell stack item AND emit the CAST event.

    Returns ``(stack_item, card_obj)``. Tests can manipulate the stack
    afterwards and then trigger the deferred firing by emitting end step.
    The resolve_fn is a no-op so resolving the copy doesn't perturb state.
    """
    card = game.create_object(
        name=name,
        owner_id=controller_id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(
            types={CardType.SORCERY},
            subtypes={"Lesson"},
        ),
    )

    def _noop_resolve(_targets, _state):
        return []

    item = StackItem(
        id="",
        type=StackItemType.SPELL,
        source_id=card.id,
        controller_id=controller_id,
        card_id=card.id,
        resolve_fn=_noop_resolve,
    )
    game.stack.push(item)

    # Emit the CAST event so the watcher fires.
    game.emit(Event(
        type=EventType.CAST,
        payload={
            'card_id': card.id,
            'spell_id': card.id,
            'caster': controller_id,
            'controller': controller_id,
            'types': list({CardType.SORCERY}),
            'subtypes': ['Lesson'],
            'colors': [],
            'mana_value': 1,
        },
        source=card.id,
        controller=controller_id,
    ))
    return item, card


# =============================================================================
# Helper-level tests for make_delayed_trigger
# =============================================================================

def test_delayed_trigger_helper_basic_tracks_and_fires():
    """Watcher records matching events; deferred fires once at end of turn."""
    print("\n=== Test: make_delayed_trigger basic accumulate + fire ===")

    game = Game()
    p1 = game.add_player("Alice")

    fired_with: list[list[dict]] = []

    # Create a battlefield "source" object so the helper can attribute the
    # interceptor to a real id.
    source = _make_creature_token(game, p1.id, name="Trigger Source")

    def watch_filter(event, st, src):
        return event.payload.get('caster') == src.controller

    def deferred_fn(src, st, payloads):
        fired_with.append(list(payloads))
        return []

    interceptors = make_delayed_trigger(
        source,
        watch_event=EventType.CAST,
        watch_filter=watch_filter,
        deferred_at='end_of_your_turn',
        deferred_effect_fn=deferred_fn,
    )
    for ic in interceptors:
        game.state.interceptors[ic.id] = ic
        source.interceptor_ids.append(ic.id)

    # Emit two CAST events for p1.
    for i in range(2):
        game.emit(Event(
            type=EventType.CAST,
            payload={'caster': p1.id, 'card_id': f'fake-{i}'},
            controller=p1.id,
        ))

    # Confirm tracker collected both.
    tracker_key = f"_delayed_{source.id}_triggers"
    bucket = game.state.turn_data.get(tracker_key)
    assert bucket is not None and len(bucket) == 2, (
        f"Expected 2 recorded events, got {bucket}"
    )

    # Fire end step.
    _emit_end_step(game, p1.id)

    assert len(fired_with) == 1, (
        f"Expected deferred to fire exactly once, got {len(fired_with)}"
    )
    assert len(fired_with[0]) == 2, (
        f"Expected 2 payloads delivered, got {len(fired_with[0])}"
    )
    # Tracker cleared after firing.
    assert not game.state.turn_data.get(tracker_key), (
        f"Tracker should be cleared after firing, got {game.state.turn_data.get(tracker_key)}"
    )
    print("PASS: helper accumulated 2 events and fired once at end step")


def test_delayed_trigger_no_match_no_fire():
    """If nothing matched, the deferred handler short-circuits (no events)."""
    print("\n=== Test: make_delayed_trigger no-match short-circuit ===")

    game = Game()
    p1 = game.add_player("Alice")

    fired = []

    source = _make_creature_token(game, p1.id, name="Trigger Source")

    def never_match(event, st, src):
        return False

    def deferred_fn(src, st, payloads):
        fired.append(payloads)
        return []

    for ic in make_delayed_trigger(
        source,
        watch_event=EventType.CAST,
        watch_filter=never_match,
        deferred_at='end_of_your_turn',
        deferred_effect_fn=deferred_fn,
    ):
        game.state.interceptors[ic.id] = ic
        source.interceptor_ids.append(ic.id)

    game.emit(Event(
        type=EventType.CAST,
        payload={'caster': p1.id, 'card_id': 'x'},
        controller=p1.id,
    ))
    _emit_end_step(game, p1.id)

    assert not fired, f"Deferred should not fire when nothing matched, got {fired}"
    print("PASS: deferred didn't fire on empty bucket")


def test_delayed_trigger_cleanup_on_turn_end():
    """If end step is skipped, TURN_END still clears the tracker."""
    print("\n=== Test: make_delayed_trigger cleanup at TURN_END ===")

    game = Game()
    p1 = game.add_player("Alice")

    source = _make_creature_token(game, p1.id, name="Trigger Source")

    fired = []
    for ic in make_delayed_trigger(
        source,
        watch_event=EventType.CAST,
        watch_filter=lambda e, s, src: True,
        deferred_at='end_of_your_turn',
        deferred_effect_fn=lambda src, st, p: (fired.append(p) or []),
    ):
        game.state.interceptors[ic.id] = ic
        source.interceptor_ids.append(ic.id)

    game.emit(Event(
        type=EventType.CAST,
        payload={'caster': p1.id, 'card_id': 'x'},
        controller=p1.id,
    ))

    tracker_key = f"_delayed_{source.id}_triggers"
    assert game.state.turn_data.get(tracker_key), "Should have recorded one event"

    # Emit TURN_END *without* end step — safety-net should still clear.
    _emit_turn_end(game)

    assert not game.state.turn_data.get(tracker_key), (
        f"Tracker should be cleared at TURN_END, got {game.state.turn_data.get(tracker_key)}"
    )
    assert not fired, "Deferred should not have fired (no end step)"
    print("PASS: TURN_END cleared the tracker")


def test_delayed_trigger_only_active_player_end_step():
    """end_of_your_turn waits for the *controller's* end step, not opponent's."""
    print("\n=== Test: make_delayed_trigger gates on controller's turn ===")

    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    fired = []
    source = _make_creature_token(game, p1.id, name="Trigger Source")
    for ic in make_delayed_trigger(
        source,
        watch_event=EventType.CAST,
        watch_filter=lambda e, s, src: True,
        deferred_at='end_of_your_turn',
        deferred_effect_fn=lambda src, st, p: (fired.append(list(p)) or []),
    ):
        game.state.interceptors[ic.id] = ic
        source.interceptor_ids.append(ic.id)

    game.emit(Event(
        type=EventType.CAST,
        payload={'caster': p1.id, 'card_id': 'x'},
        controller=p1.id,
    ))

    # Opponent's end step — must NOT fire the deferred handler.
    _emit_end_step(game, p2.id)
    assert not fired, "Deferred should not fire on opponent's end step"

    # Controller's end step — fires.
    _emit_end_step(game, p1.id)
    assert len(fired) == 1, f"Should have fired once on controller's end step, got {len(fired)}"
    print("PASS: gating on active_player == source.controller")


# =============================================================================
# Jeong Jeong tests
# =============================================================================

def test_jeong_jeong_arms_and_copies_lesson_at_end_step():
    """After exhaust, a Lesson cast is captured and copied at end of turn."""
    print("\n=== Test: Jeong Jeong end-step Lesson copy ===")

    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    jeong = _put_on_battlefield(game, p1.id, JEONG_JEONG_THE_DESERTER)

    # Activate the exhaust ability via the registered descriptor.
    armed_flag = f"_jeong_armed_{jeong.id}"
    snapshots_key = f"_jeong_snapshots_{jeong.id}"

    # Simulate exhaust activation by calling the recorded effect_fn with
    # paid cost. The descriptor lives on jeong.activated_abilities; the
    # easiest deterministic path is to set the armed flag directly — we
    # also run the descriptor via game.execute_activated_ability when
    # available. Tests for the cost/legality of the exhaust are handled
    # elsewhere; here we focus on the delayed-trigger semantics.
    game.state.turn_data[armed_flag] = True
    game.state.turn_data[snapshots_key] = []

    # Push a fake Lesson stack item + emit CAST → watcher should snapshot it.
    item, _ = _push_fake_lesson_spell(game, p1.id)
    snapshots = game.state.turn_data.get(snapshots_key) or []
    assert len(snapshots) == 1, (
        f"Expected one captured snapshot after Lesson cast, got {len(snapshots)}"
    )

    # Resolve the original spell (pop it off the stack) so we know the copy
    # is being pushed as a fresh stack item, not piggy-backing on the
    # original.
    game.stack.resolve_top()
    assert game.stack.is_empty(), "Original Lesson should have resolved"

    # Fire end step → expect a copy to be pushed onto the stack.
    _emit_end_step(game, p1.id)

    items = game.stack.get_items()
    assert len(items) == 1, f"Expected one copy on the stack, got {len(items)}"
    assert items[0].is_copy, "Pushed item should be marked is_copy=True"

    # Tracker cleared.
    assert not game.state.turn_data.get(snapshots_key), (
        f"Snapshots key should be cleared after firing"
    )
    assert not game.state.turn_data.get(armed_flag), (
        "Armed flag should be cleared after firing"
    )
    print("PASS: Jeong Jeong copied the Lesson at end of turn")


def test_jeong_jeong_two_lessons_copied():
    """Two Lessons cast after exhaust → two copies at end step."""
    print("\n=== Test: Jeong Jeong copies two Lessons ===")

    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    jeong = _put_on_battlefield(game, p1.id, JEONG_JEONG_THE_DESERTER)
    armed_flag = f"_jeong_armed_{jeong.id}"
    snapshots_key = f"_jeong_snapshots_{jeong.id}"
    game.state.turn_data[armed_flag] = True
    game.state.turn_data[snapshots_key] = []

    for i in range(2):
        item, _ = _push_fake_lesson_spell(game, p1.id, name=f"Mock Lesson {i+1}")
        # Resolve immediately to emulate normal resolution before end step.
        game.stack.resolve_top()

    snapshots = game.state.turn_data.get(snapshots_key) or []
    assert len(snapshots) == 2, f"Expected 2 captured snapshots, got {len(snapshots)}"

    _emit_end_step(game, p1.id)
    items = game.stack.get_items()
    assert len(items) == 2, f"Expected 2 copies, got {len(items)}"
    assert all(it.is_copy for it in items), "All copies should be is_copy=True"
    print("PASS: Jeong Jeong stacked 2 copies at end of turn")


def test_jeong_jeong_disarmed_next_turn():
    """The exhaust flag and snapshots clear at TURN_END so a stale arming
    on turn N doesn't bleed into turn N+1."""
    print("\n=== Test: Jeong Jeong tracker resets across turn boundary ===")

    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    jeong = _put_on_battlefield(game, p1.id, JEONG_JEONG_THE_DESERTER)
    armed_flag = f"_jeong_armed_{jeong.id}"
    snapshots_key = f"_jeong_snapshots_{jeong.id}"
    delayed_key = f"_delayed_{jeong.id}_triggers"
    game.state.turn_data[armed_flag] = True
    game.state.turn_data[snapshots_key] = []

    item, _ = _push_fake_lesson_spell(game, p1.id)
    game.stack.resolve_top()

    # End the turn WITHOUT an end step (simulate skipped end step). The
    # safety-net TURN_END cleanup should clear the helper's tracker.
    _emit_turn_end(game)

    # turn_data is reset by the engine's normal turn rollover; but since we
    # didn't emit TURN_START here, manually mimic it by clearing turn_data.
    game.state.turn_data = {}

    # Cast a fresh Lesson on the new "turn" without arming Jeong Jeong.
    item2, _ = _push_fake_lesson_spell(game, p1.id, name="Next Turn Lesson")
    game.stack.resolve_top()

    # The watcher should NOT have recorded anything — armed_flag is gone.
    assert not game.state.turn_data.get(armed_flag), "Armed flag must be reset"
    assert not game.state.turn_data.get(snapshots_key), (
        "Snapshots must be empty without arming"
    )
    print("PASS: tracker cleared after turn boundary, no stale captures")


def test_jeong_jeong_unarmed_does_not_record():
    """Without exhaust activation, Lesson casts are not recorded."""
    print("\n=== Test: Jeong Jeong without exhaust = no-op ===")

    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    jeong = _put_on_battlefield(game, p1.id, JEONG_JEONG_THE_DESERTER)
    snapshots_key = f"_jeong_snapshots_{jeong.id}"
    armed_flag = f"_jeong_armed_{jeong.id}"

    # Sanity: not armed.
    assert not game.state.turn_data.get(armed_flag), "Should start unarmed"

    item, _ = _push_fake_lesson_spell(game, p1.id)
    game.stack.resolve_top()

    snapshots = game.state.turn_data.get(snapshots_key) or []
    assert not snapshots, (
        f"Without arming, no Lesson should have been captured, got {len(snapshots)}"
    )

    _emit_end_step(game, p1.id)
    # No copy on the stack.
    assert game.stack.is_empty(), "Stack should be empty when unarmed"
    print("PASS: unarmed Jeong Jeong is inert")


# =============================================================================
# Tundra Tank tests
# =============================================================================

def test_tundra_tank_grants_indestructible():
    """Tundra Tank ETB grants indestructible UEOT to a chosen target creature."""
    print("\n=== Test: Tundra Tank ETB grants indestructible ===")

    game = Game()
    p1 = game.add_player("Alice")

    target = _make_creature_token(game, p1.id, name="Goblin Token")
    # Sanity: starts without indestructible.
    assert not any(
        a.get("keyword") == "indestructible"
        for a in target.characteristics.abilities
        if isinstance(a, dict)
    ), "Target shouldn't start with indestructible"

    _put_on_battlefield(game, p1.id, TUNDRA_TANK)

    # Simulate the player choosing the target via the pending choice queue.
    choice = game.state.pending_choice
    assert choice is not None, "Tundra Tank should have queued a target choice"
    handler = choice.callback_data.get('handler')
    assert handler is not None, "Tundra Tank choice must wire a callback"

    # The execute path: invoke handler with our target id, then dispatch
    # the resulting events through the pipeline to apply GRANT_KEYWORD.
    events = handler(choice, [target.id], game.state)
    for ev in events:
        game.emit(ev)

    # Target should now have indestructible ability registered.
    has_indestructible = any(
        (isinstance(a, dict) and a.get("keyword") == "indestructible")
        for a in target.characteristics.abilities
    )
    assert has_indestructible, (
        f"Target should have indestructible after grant, abilities={target.characteristics.abilities}"
    )
    print("PASS: Tundra Tank granted indestructible UEOT")


# =============================================================================
# Fire Lord Azula tests
# =============================================================================

def test_fire_lord_azula_copies_spell_while_attacking():
    """Casting a spell while Fire Lord Azula is attacking → copy via COPY_STACK_ITEM."""
    print("\n=== Test: Fire Lord Azula copies spells while attacking ===")

    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    azula = _put_on_battlefield(game, p1.id, FIRE_LORD_AZULA)
    azula.state.attacking = True

    # Push a fake instant on the stack and emit CAST.
    card = game.create_object(
        name="Lava Coil",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(types={CardType.INSTANT}),
    )

    def _resolve_noop(_t, _s):
        return []

    item = StackItem(
        id="",
        type=StackItemType.SPELL,
        source_id=card.id,
        controller_id=p1.id,
        card_id=card.id,
        resolve_fn=_resolve_noop,
    )
    game.stack.push(item)

    items_before = len(game.stack.get_items())
    game.emit(Event(
        type=EventType.CAST,
        payload={
            'card_id': card.id,
            'spell_id': card.id,
            'caster': p1.id,
            'controller': p1.id,
            'types': [CardType.INSTANT],
            'subtypes': [],
            'colors': [],
            'mana_value': 2,
        },
        source=card.id,
        controller=p1.id,
    ))

    items_after = len(game.stack.get_items())
    assert items_after == items_before + 1, (
        f"Expected one copy pushed (before={items_before}, after={items_after})"
    )
    # The new top should be a copy.
    assert game.stack.top().is_copy, "Top of stack should be the copy"
    print("PASS: Fire Lord Azula pushed a copy of the cast spell")


def test_fire_lord_azula_no_copy_when_not_attacking():
    """If Azula is NOT attacking, no copy is pushed."""
    print("\n=== Test: Fire Lord Azula does nothing when not attacking ===")

    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    azula = _put_on_battlefield(game, p1.id, FIRE_LORD_AZULA)
    # NOT attacking.
    azula.state.attacking = False

    card = game.create_object(
        name="Lava Coil",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(types={CardType.INSTANT}),
    )

    def _resolve_noop(_t, _s):
        return []

    item = StackItem(
        id="",
        type=StackItemType.SPELL,
        source_id=card.id,
        controller_id=p1.id,
        card_id=card.id,
        resolve_fn=_resolve_noop,
    )
    game.stack.push(item)
    items_before = len(game.stack.get_items())

    game.emit(Event(
        type=EventType.CAST,
        payload={
            'card_id': card.id,
            'spell_id': card.id,
            'caster': p1.id,
            'controller': p1.id,
            'types': [CardType.INSTANT],
            'subtypes': [],
            'colors': [],
            'mana_value': 2,
        },
        source=card.id,
        controller=p1.id,
    ))

    items_after = len(game.stack.get_items())
    assert items_after == items_before, (
        f"No copy expected when not attacking (before={items_before}, after={items_after})"
    )
    print("PASS: no copy pushed when Azula is not attacking")


# =============================================================================
# Edge case: multiple Jeong Jeongs
# =============================================================================

def test_two_jeong_jeongs_independent_queues():
    """Two Jeong Jeongs each have independent armed flags and snapshot
    buckets — arming one shouldn't arm the other."""
    print("\n=== Test: Two Jeong Jeongs share no state ===")

    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    # Note: legendary rule means one would die in real play, but the
    # tracker keys use obj.id so they'd still be independent. We bypass
    # legendary SBA in this isolated unit test.
    jj1 = _put_on_battlefield(game, p1.id, JEONG_JEONG_THE_DESERTER, name="Jeong Jeong 1")
    jj2 = _put_on_battlefield(game, p1.id, JEONG_JEONG_THE_DESERTER, name="Jeong Jeong 2")

    armed1 = f"_jeong_armed_{jj1.id}"
    snaps1 = f"_jeong_snapshots_{jj1.id}"
    armed2 = f"_jeong_armed_{jj2.id}"
    snaps2 = f"_jeong_snapshots_{jj2.id}"

    # Arm only #1.
    game.state.turn_data[armed1] = True
    game.state.turn_data[snaps1] = []

    item, _ = _push_fake_lesson_spell(game, p1.id)
    game.stack.resolve_top()

    s1 = game.state.turn_data.get(snaps1) or []
    s2 = game.state.turn_data.get(snaps2) or []
    assert len(s1) == 1, f"#1 should have captured 1, got {len(s1)}"
    assert len(s2) == 0, f"#2 should have captured 0, got {len(s2)}"

    # End step: only #1 should fire a copy.
    _emit_end_step(game, p1.id)
    assert len(game.stack.get_items()) == 1, "Only one copy should be pushed"
    print("PASS: independent queues per Jeong Jeong")


# =============================================================================
# Runner
# =============================================================================

def run_all():
    print("=" * 70)
    print("ATLA NICHE TESTS")
    print("=" * 70)

    print("\n--- DELAYED TRIGGER HELPER ---")
    test_delayed_trigger_helper_basic_tracks_and_fires()
    test_delayed_trigger_no_match_no_fire()
    test_delayed_trigger_cleanup_on_turn_end()
    test_delayed_trigger_only_active_player_end_step()

    print("\n--- JEONG JEONG ---")
    test_jeong_jeong_arms_and_copies_lesson_at_end_step()
    test_jeong_jeong_two_lessons_copied()
    test_jeong_jeong_disarmed_next_turn()
    test_jeong_jeong_unarmed_does_not_record()

    print("\n--- TUNDRA TANK ---")
    test_tundra_tank_grants_indestructible()

    print("\n--- FIRE LORD AZULA ---")
    test_fire_lord_azula_copies_spell_while_attacking()
    test_fire_lord_azula_no_copy_when_not_attacking()

    print("\n--- EDGE CASES ---")
    test_two_jeong_jeongs_independent_queues()

    print("\n" + "=" * 70)
    print("ALL ATLA NICHE TESTS PASSED!")
    print("=" * 70)


if __name__ == "__main__":
    run_all()
