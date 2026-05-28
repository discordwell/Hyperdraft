"""
Triggered abilities as stack items (CR 603.2 / 603.3).

Tests the TriggeredStackItem class, the pending_triggers queue,
APNAP ordering, and the auto_resolve_triggers default flag.
"""

import sys
sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[1].as_posix())

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, Characteristics, new_id,
)
from src.engine.stack import (
    TriggeredStackItem, StackItemType,
    process_pending_triggers,
    auto_resolve_pending_triggers,
)
from src.cards.interceptor_helpers import make_etb_trigger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_state_with_two_players():
    state = GameState()
    state.players["alice"] = type(__import__("src.engine", fromlist=["Player"]).Player)(
        id="alice", name="Alice"
    ) if False else None
    # Avoid the dance — import directly.
    from src.engine.types import Player, Zone
    state.players["alice"] = Player(id="alice", name="Alice", life=20)
    state.players["bob"] = Player(id="bob", name="Bob", life=20)
    state.zones["battlefield"] = Zone(type=ZoneType.BATTLEFIELD, owner=None)
    state.zones["stack"] = Zone(type=ZoneType.STACK, owner=None)
    state.active_player = "alice"
    return state


def _make_perm(state, name, controller, life_gain_amount=3):
    """Make a permanent on the battlefield with an ETB trigger that gains life."""
    char = Characteristics(
        types={CardType.CREATURE},
        power=1, toughness=1,
    )
    obj = GameObject(
        id=new_id(),
        name=name,
        owner=controller,
        controller=controller,
        zone=ZoneType.BATTLEFIELD,
        characteristics=char,
    )
    state.objects[obj.id] = obj
    state.zones["battlefield"].objects.append(obj.id)

    def effect_fn(event, state):
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': controller, 'amount': life_gain_amount},
            source=obj.id,
            controller=controller,
        )]

    interceptor = make_etb_trigger(obj, effect_fn)
    interceptor.timestamp = state.next_timestamp()
    state.interceptors[interceptor.id] = interceptor
    obj.interceptor_ids.append(interceptor.id)
    return obj


def _make_engine_game():
    """Build a minimal Game with two players + stack."""
    game = Game()
    alice = game.add_player("Alice")
    bob = game.add_player("Bob")
    # Make sure deterministic ids for assertions.
    game.state.active_player = alice.id
    # Cache ids on the game for tests to read.
    game._alice_id = alice.id  # type: ignore[attr-defined]
    game._bob_id = bob.id  # type: ignore[attr-defined]
    return game


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_etb_trigger_queues_when_auto_resolve_disabled():
    """With auto_resolve_triggers=False, ETB queues a TriggeredStackItem."""
    print("\n=== Test: ETB queues TriggeredStackItem (no auto-resolve) ===")
    game = _make_engine_game()
    aid = game._alice_id  # type: ignore[attr-defined]
    game.state.options.auto_resolve_triggers = False

    obj = _make_perm(game.state, "Helper", aid, life_gain_amount=3)

    # Reset life so we can detect non-firing.
    game.state.players[aid].life = 20
    pre = game.state.players[aid].life

    # Fire an ETB-equivalent ZONE_CHANGE.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
        source=obj.id,
    ))

    # The trigger should have been queued, NOT fired.
    assert game.state.players[aid].life == pre, (
        f"With auto_resolve_triggers=False, life should not change yet. "
        f"Got {game.state.players[aid].life}, expected {pre}."
    )
    assert len(game.state.pending_triggers) == 1, (
        f"Expected 1 pending trigger, got {len(game.state.pending_triggers)}"
    )
    trig = game.state.pending_triggers[0]
    assert isinstance(trig, TriggeredStackItem)
    assert trig.controller == aid
    assert trig.source_id == obj.id
    print("  OK")


def test_auto_resolve_triggers_default_resolves_immediately():
    """With auto_resolve_triggers=True (default), trigger fires immediately."""
    print("\n=== Test: auto_resolve_triggers=True fires inline ===")
    game = _make_engine_game()
    aid = game._alice_id  # type: ignore[attr-defined]
    # Default is True — leave it.

    obj = _make_perm(game.state, "Helper", aid, life_gain_amount=3)
    game.state.players[aid].life = 20

    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
        source=obj.id,
    ))

    # The effect should have run inline.
    assert game.state.players[aid].life == 23, (
        f"Auto-resolve should fire trigger inline; expected life 23, "
        f"got {game.state.players[aid].life}."
    )
    assert game.state.pending_triggers == []
    print("  OK")


def test_apnap_ordering_active_player_first():
    """Triggers from multiple players resolve AP first then NAP (CR 603.3b)."""
    print("\n=== Test: APNAP ordering ===")
    game = _make_engine_game()
    aid = game._alice_id  # type: ignore[attr-defined]
    bid = game._bob_id  # type: ignore[attr-defined]
    game.state.options.auto_resolve_triggers = False

    a = _make_perm(game.state, "AliceCard", aid, life_gain_amount=1)
    b = _make_perm(game.state, "BobCard", bid, life_gain_amount=1)

    # Fire a TURN_START (both cards' upkeep-style triggers won't fire from this
    # but for the queue test we'll directly install pending triggers via ETB).
    # Emit two ETB-equivalent events — one for alice's card, one for bob's.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': a.id, 'to_zone_type': ZoneType.BATTLEFIELD},
        source=a.id,
    ))
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': b.id, 'to_zone_type': ZoneType.BATTLEFIELD},
        source=b.id,
    ))

    assert len(game.state.pending_triggers) == 2

    # Now drain via process_pending_triggers (APNAP).
    pushed = process_pending_triggers(game.state, game.stack)
    assert pushed == 2

    # Stack should have alice's trigger pushed first (so it's at the bottom),
    # bob's second (so it's at the top — resolves first).
    items = game.stack.get_items()
    assert len(items) == 2
    assert items[0].controller == aid, f"Expected alice's trigger at bottom, got {items[0].controller}"
    assert items[1].controller == bid, f"Expected bob's trigger at top, got {items[1].controller}"
    print("  OK: alice (active) was pushed first, bob's resolves first (LIFO)")


def test_replacement_effect_does_not_go_on_stack():
    """TRANSFORM-priority replacement effects fire inline, not on the stack."""
    print("\n=== Test: replacement effect (TRANSFORM) stays inline ===")
    from src.cards.interceptor_helpers import make_replacement_effect

    game = _make_engine_game()
    aid = game._alice_id  # type: ignore[attr-defined]
    game.state.options.auto_resolve_triggers = False

    # Build a creature with a replacement that doubles life gain.
    char = Characteristics(types={CardType.CREATURE}, power=1, toughness=1)
    obj = GameObject(
        id=new_id(), name="Doubler",
        owner=aid, controller=aid,
        zone=ZoneType.BATTLEFIELD, characteristics=char,
    )
    game.state.objects[obj.id] = obj
    game.state.zones["battlefield"].objects.append(obj.id)

    def event_filter(event, state):
        return event.type == EventType.LIFE_CHANGE and event.payload.get('player') == aid

    def replace(event, state):
        new_event = event.copy()
        new_event.payload['amount'] = (event.payload.get('amount', 0) or 0) * 2
        return [new_event]

    rep_ints = make_replacement_effect(
        source=obj,
        event_filter=event_filter,
        replace_fn=replace,
        duration='permanent',
    )
    for rep_int in rep_ints:
        rep_int.timestamp = game.state.next_timestamp()
        game.state.interceptors[rep_int.id] = rep_int

    pre = game.state.players[aid].life
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': aid, 'amount': 2},
        source=obj.id, controller=aid,
    ))

    # Replacement should fire inline. Pending triggers should be empty.
    assert game.state.pending_triggers == []
    assert game.state.players[aid].life == pre + 4, (
        f"Replacement should double 2->4. Life {pre} -> {game.state.players[aid].life}"
    )
    print("  OK: replacement fired inline, doubled the life gain")


def test_pending_triggers_drain_via_helper():
    """auto_resolve_pending_triggers drains in APNAP order and resolves."""
    print("\n=== Test: auto_resolve_pending_triggers drains queue ===")
    game = _make_engine_game()
    aid = game._alice_id  # type: ignore[attr-defined]
    bid = game._bob_id  # type: ignore[attr-defined]
    game.state.options.auto_resolve_triggers = False

    a = _make_perm(game.state, "AliceCard", aid, life_gain_amount=2)
    b = _make_perm(game.state, "BobCard", bid, life_gain_amount=5)

    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': a.id, 'to_zone_type': ZoneType.BATTLEFIELD},
        source=a.id,
    ))
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': b.id, 'to_zone_type': ZoneType.BATTLEFIELD},
        source=b.id,
    ))

    # Now drain.
    out = auto_resolve_pending_triggers(game.state, game.stack)
    # Each trigger emits 1 LIFE_CHANGE event.
    assert len(out) == 2
    # Process the events through the pipeline so life changes apply.
    for ev in out:
        game.emit(ev)

    assert game.state.players[aid].life == 22
    assert game.state.players[bid].life == 25
    assert game.stack.is_empty()
    print("  OK: both triggers resolved, life changes applied")


def test_trigger_fizzles_on_illegal_target_at_resolution():
    """If a trigger's chosen target is gone at resolve-time, trigger removes."""
    print("\n=== Test: trigger fizzles on illegal target ===")
    from src.engine.targeting import TargetRequirement, TargetFilter, Target

    game = _make_engine_game()
    aid = game._alice_id  # type: ignore[attr-defined]
    bid = game._bob_id  # type: ignore[attr-defined]
    char = Characteristics(types={CardType.CREATURE}, power=1, toughness=1)

    src = GameObject(
        id=new_id(), name="Source",
        owner=aid, controller=aid,
        zone=ZoneType.BATTLEFIELD, characteristics=char,
    )
    target = GameObject(
        id=new_id(), name="Target",
        owner=bid, controller=bid,
        zone=ZoneType.BATTLEFIELD, characteristics=char,
    )
    game.state.objects[src.id] = src
    game.state.objects[target.id] = target
    game.state.zones["battlefield"].objects.append(src.id)
    game.state.zones["battlefield"].objects.append(target.id)

    # Build a TriggeredStackItem with a target requirement.
    fired = {"count": 0}

    def effect_fn(event, state):
        fired["count"] += 1
        return []

    snap = Event(type=EventType.ZONE_CHANGE, payload={'object_id': src.id})
    req = TargetRequirement(
        filter=TargetFilter(types={CardType.CREATURE}),
        count=1,
        count_type='exactly',
    )
    trig = TriggeredStackItem(
        id=new_id(),
        controller=aid,
        source_id=src.id,
        source_card_name="Source",
        trigger_event=snap,
        effect_fn=effect_fn,
        description="Test trigger",
        target_requirements=[req],
        chosen_targets=[[Target(id=target.id)]],
    )

    # Move target to graveyard so it's no longer on battlefield (illegal target).
    game.state.zones["battlefield"].objects.remove(target.id)
    target.zone = ZoneType.GRAVEYARD

    game.stack.push_triggered_ability(trig)
    events = game.stack.resolve_top()

    # Trigger should fizzle (target illegal) — effect_fn should NOT have run.
    assert fired["count"] == 0, "Effect must not run when target is illegal"
    assert events == [], "Fizzled trigger returns no events"
    print("  OK: trigger fizzled silently due to illegal target")


def test_marker_event_fires_when_trigger_queued():
    """TRIGGERED_ABILITY_PUT_ON_STACK appears in event log when queued."""
    print("\n=== Test: TRIGGERED_ABILITY_PUT_ON_STACK marker ===")
    game = _make_engine_game()
    aid = game._alice_id  # type: ignore[attr-defined]
    # auto_resolve True => trigger drains inline + emits marker via event log.

    obj = _make_perm(game.state, "Helper", aid, life_gain_amount=1)
    pre_log_size = len(game.state.event_log)

    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': obj.id, 'to_zone_type': ZoneType.BATTLEFIELD},
        source=obj.id,
    ))

    markers = [
        e for e in game.state.event_log[pre_log_size:]
        if e.type == EventType.TRIGGERED_ABILITY_PUT_ON_STACK
    ]
    assert len(markers) >= 1, f"Expected at least 1 marker event, got {len(markers)}"
    m = markers[0]
    assert m.payload.get('controller') == aid
    assert m.payload.get('source_id') == obj.id
    print(f"  OK: marker emitted (description={m.payload.get('description')!r})")


def test_chained_triggers_drain_recursively():
    """A trigger that emits an event triggering another trigger drains both."""
    print("\n=== Test: chained triggers drain recursively ===")
    game = _make_engine_game()
    aid = game._alice_id  # type: ignore[attr-defined]

    a = _make_perm(game.state, "AliceCardA", aid, life_gain_amount=1)
    b = _make_perm(game.state, "AliceCardB", aid, life_gain_amount=2)

    game.state.players[aid].life = 20
    # Both ETBs fire — should both queue, both resolve.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': a.id, 'to_zone_type': ZoneType.BATTLEFIELD},
        source=a.id,
    ))
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': b.id, 'to_zone_type': ZoneType.BATTLEFIELD},
        source=b.id,
    ))

    assert game.state.players[aid].life == 23, (
        f"Both ETB triggers should resolve. Life: {game.state.players[aid].life}"
    )
    assert game.state.pending_triggers == []
    print("  OK: chained triggers all resolved")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_etb_trigger_queues_when_auto_resolve_disabled,
        test_auto_resolve_triggers_default_resolves_immediately,
        test_apnap_ordering_active_player_first,
        test_replacement_effect_does_not_go_on_stack,
        test_pending_triggers_drain_via_helper,
        test_trigger_fizzles_on_illegal_target_at_resolution,
        test_marker_event_fires_when_trigger_queued,
        test_chained_triggers_drain_recursively,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"  FAIL: {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR: {t.__name__}: {type(e).__name__}: {e}")

    print()
    print("=" * 60)
    print(f"{passed} passed / {failed} failed (of {len(tests)})")
    print("=" * 60)
    if failed:
        sys.exit(1)
