"""
Server-side integration tests for the priority-window UI plumbing.

These tests exercise the path the React UI relies on:
  * Live MTG matches default to ``auto_resolve_triggers=False`` so
    triggered abilities go on the stack.
  * ``GameSession.get_client_state`` surfaces ``pending_triggers`` and
    ``stack`` (with descriptions for triggered abilities) so the frontend
    can render the queue and the priority prompt.
  * The serializer tolerates both ``StackItem`` (controller_id) and
    ``TriggeredStackItem`` (controller).

Run directly: ``python tests/test_server_priority_window.py``.
"""

import asyncio
import os
import sys

# Insert this worktree's repo root (parent of ``tests/``) at the FRONT of
# sys.path so we always import the local ``src/server/...`` next to this
# file, even when other test files in the same suite have already
# inserted a different root (e.g. the main repo).
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT in sys.path:
    sys.path.remove(_REPO_ROOT)
sys.path.insert(0, _REPO_ROOT)

from fastapi import BackgroundTasks

from src.engine import (
    Game, Event, EventType, ZoneType, CardType,
    GameObject, Characteristics, new_id,
)
from src.engine.stack import TriggeredStackItem, process_pending_triggers
from src.cards.interceptor_helpers import make_etb_trigger
from src.server.models import CreateMatchRequest
from src.server.routes.match import create_match
from src.server.session import GameSession, session_manager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_perm_with_etb(state, *, name, controller, life_amount=3, description=""):
    """Create a battlefield permanent with an ETB life-gain trigger."""
    char = Characteristics(types={CardType.CREATURE}, power=1, toughness=1)
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
            payload={'player': controller, 'amount': life_amount},
            source=obj.id,
            controller=controller,
        )]

    interceptor = make_etb_trigger(obj, effect_fn)
    interceptor.timestamp = state.next_timestamp()
    state.interceptors[interceptor.id] = interceptor
    obj.interceptor_ids.append(interceptor.id)

    # Stash the description so _serialize_pending_trigger surfaces it.
    # The trigger queue item built by the pipeline copies the
    # interceptor's description; for direct queue-injection paths we
    # set it explicitly later.
    return obj, description


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_live_mtg_match_disables_auto_resolve_triggers():
    """Creating a human-vs-bot MTG match should flip auto_resolve_triggers off."""

    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot",
                game_mode="mtg",
                player_name="Tester",
            ),
            background_tasks=BackgroundTasks(),
        )

        session = session_manager.get_session(response.match_id)
        assert session is not None

        opts = session.game.state.options
        assert opts.auto_resolve_triggers is False, (
            "Live MTG matches should disable auto_resolve_triggers so "
            "triggered abilities surface a priority window in the UI."
        )

        await session_manager.remove_session(response.match_id)

    asyncio.run(_run())


def test_hearthstone_match_keeps_auto_resolve_triggers_on():
    """Hearthstone matches don't use the MTG stack; flag should stay True."""

    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot",
                game_mode="hearthstone",
                player_name="Tester",
            ),
            background_tasks=BackgroundTasks(),
        )

        session = session_manager.get_session(response.match_id)
        assert session is not None

        # HS doesn't use auto_resolve_triggers — defaults to True.
        opts = session.game.state.options
        assert opts.auto_resolve_triggers is True

        await session_manager.remove_session(response.match_id)

    asyncio.run(_run())


def test_get_client_state_surfaces_pending_triggers():
    """A trigger queued in state.pending_triggers must appear in client state."""
    session = GameSession(id="t1", game=Game(mode="mtg"), mode="human_vs_bot")
    p1 = session.add_player("Alice", is_ai=False)
    session.add_player("Bob", is_ai=True)
    state = session.game.state

    # Disable auto-resolve so ETB queues a trigger.
    state.options.auto_resolve_triggers = False
    state.active_player = p1

    obj, _ = _make_perm_with_etb(state, name="Soul Warden", controller=p1, life_amount=1)

    # Fire the ETB-equivalent zone change.
    session.game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
        source=obj.id,
    ))

    # The trigger should sit in pending_triggers, not have fired yet.
    assert len(state.pending_triggers) == 1
    assert state.pending_triggers[0].source_card_name == "Soul Warden"

    # Patch a description in so we can verify it surfaces (in the live
    # game, descriptions come from the interceptor's metadata; for
    # direct ETB-trigger helpers it's fine to leave blank — the UI
    # renders source_name with no body).
    state.pending_triggers[0].description = "When Soul Warden enters, you gain 1 life."

    client = session.get_client_state(p1)
    payload = client.model_dump()

    # The pending_triggers key must be present and populated.
    assert 'pending_triggers' in payload
    assert len(payload['pending_triggers']) == 1

    item = payload['pending_triggers'][0]
    assert item['source_name'] == "Soul Warden"
    assert item['controller'] == p1
    assert "you gain 1 life" in item['description'].lower()


def test_get_client_state_serializes_triggered_stack_item():
    """Once a trigger is on the stack, it serializes with description + controller."""
    session = GameSession(id="t2", game=Game(mode="mtg"), mode="human_vs_bot")
    p1 = session.add_player("Alice", is_ai=False)
    session.add_player("Bob", is_ai=True)
    state = session.game.state

    state.options.auto_resolve_triggers = False
    state.active_player = p1

    obj, _ = _make_perm_with_etb(state, name="Soul Warden", controller=p1, life_amount=1)

    # Manually craft a TriggeredStackItem onto the stack so we can
    # verify the serializer handles it (rather than depending on an
    # ETB to fire at exactly the right pipeline time).
    trig = TriggeredStackItem(
        id=new_id(),
        controller=p1,
        source_id=obj.id,
        source_card_name="Soul Warden",
        trigger_event=Event(type=EventType.ZONE_CHANGE, payload={}, source=obj.id),
        effect_fn=lambda e, s: [],
        description="Whenever a creature enters, you gain 1 life.",
    )
    session.game.stack.push_triggered_ability(trig)

    client = session.get_client_state(p1)
    payload = client.model_dump()
    stack_payload = payload['stack']

    assert len(stack_payload) == 1
    item = stack_payload[0]
    assert item['type'] == "TRIGGERED_ABILITY"
    assert item['source_name'] == "Soul Warden"
    assert item['controller'] == p1
    assert "gain 1 life" in item['description'].lower()


def test_priority_window_pass_resolves_trigger():
    """End-to-end shape: trigger queued -> pushed on stack -> resolves on drain."""

    session = GameSession(id="t3", game=Game(mode="mtg"), mode="human_vs_bot")
    p1 = session.add_player("Alice", is_ai=False)
    session.add_player("Bob", is_ai=True)
    state = session.game.state
    state.options.auto_resolve_triggers = False
    state.active_player = p1

    starting_life = state.players[p1].life

    obj, _ = _make_perm_with_etb(state, name="Soul Warden", controller=p1, life_amount=2)

    # Step 1: Fire ETB; trigger queues.
    session.game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
        source=obj.id,
    ))

    assert len(state.pending_triggers) == 1
    # Life unchanged — auto-resolve is off, so the effect hasn't run.
    assert state.players[p1].life == starting_life

    # Client snapshot should show the queued trigger.
    snapshot1 = session.get_client_state(p1).model_dump()
    assert len(snapshot1['pending_triggers']) == 1
    assert snapshot1['stack'] == []

    # Step 2: priority pass equivalent — drain queue onto stack
    # (which is what the engine's _put_triggers_on_stack does).
    pushed = process_pending_triggers(state, session.game.stack)
    assert pushed == 1
    assert state.pending_triggers == []

    # Snapshot should now show the trigger on the stack, queue empty.
    snapshot2 = session.get_client_state(p1).model_dump()
    assert snapshot2['pending_triggers'] == []
    assert len(snapshot2['stack']) == 1
    assert snapshot2['stack'][0]['type'] == "TRIGGERED_ABILITY"
    assert snapshot2['stack'][0]['source_name'] == "Soul Warden"

    # Step 3: resolve the stack — both players passed, top resolves.
    resolution_events = session.game.stack.resolve_top()
    # The effect_fn returns a LIFE_CHANGE event; emit it through the
    # pipeline to apply the life gain.
    for event in resolution_events:
        session.game.emit(event)

    assert state.players[p1].life == starting_life + 2
    assert session.game.stack.is_empty()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    tests = [
        test_live_mtg_match_disables_auto_resolve_triggers,
        test_hearthstone_match_keeps_auto_resolve_triggers_on,
        test_get_client_state_surfaces_pending_triggers,
        test_get_client_state_serializes_triggered_stack_item,
        test_priority_window_pass_resolves_trigger,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{'OK' if failures == 0 else 'FAILED'}: {len(tests) - failures}/{len(tests)} passed")
    return failures


if __name__ == "__main__":
    sys.exit(main())
