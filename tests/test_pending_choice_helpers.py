"""Tests for the engine-agnostic PendingChoice helpers in
``src/engine/pending_choice_helpers.py``.

These tests pin down the contract that distinguishes AI players (resolve
inline, clear the choice) from human players (leave the choice pending so
the session.py blocks on it).
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import Game
from src.engine.pending_choice_helpers import (
    create_choice_and_resolve,
    resolve_pending_choice_inline,
)
from src.engine.types import Event, EventType, PendingChoice


def _make_game_with_ai(ai_player_ids: set[str]) -> Game:
    """Build a Game with a turn_manager-shaped namespace carrying
    ``ai_players`` so the resolver can identify AI vs human.

    No specific engine — just enough wiring for the helper's lookup.
    """
    game = Game()
    game.turn_manager = SimpleNamespace(ai_players=set(ai_player_ids))
    return game


def _stash_choice(game: Game, player_id: str, handler) -> PendingChoice:
    pc = PendingChoice(
        choice_type="modal_with_callback",
        player=player_id,
        prompt="Pick a mode",
        options=[{"index": 0, "text": "A"}, {"index": 1, "text": "B"}],
        source_id="test_source",
        min_choices=1,
        max_choices=1,
        callback_data={"handler": handler},
    )
    game.state.pending_choice = pc
    return pc


def test_human_player_leaves_choice_pending():
    """A choice belonging to a human (non-AI) player must NOT be resolved
    inline — the resolver returns empty and leaves state.pending_choice set
    so the session's _get_human_action blocks on it.
    """
    game = _make_game_with_ai(ai_player_ids=set())  # no AI players
    p1 = game.add_player("Alice")

    handler_called = {"value": False}

    def handler(choice, selected, state):
        handler_called["value"] = True
        return []

    _stash_choice(game, p1.id, handler)
    assert game.state.pending_choice is not None

    events, selected = resolve_pending_choice_inline(game.state)

    assert events == []
    assert selected == []
    assert game.state.pending_choice is not None, (
        "Human choice must remain pending so the session blocks on it. "
        "The old Pokemon helper silently auto-resolved to [0] — regression check."
    )
    assert handler_called["value"] is False, "Handler must not fire for humans"
    print("PASS: human choice stays pending; no handler fired")


def test_ai_player_resolves_inline_via_handler():
    """A choice belonging to an AI player should fire its callback_data
    handler with a fallback selection (no AI handler registered), clear
    pending_choice, and return events.
    """
    game = _make_game_with_ai(ai_player_ids={"bot_player"})

    captured = {"selected": None}

    def handler(choice, selected, state):
        captured["selected"] = list(selected)
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={"player": choice.player, "amount": 3},
            source=choice.source_id,
        )]

    _stash_choice(game, "bot_player", handler)
    events, selected = resolve_pending_choice_inline(game.state)

    assert game.state.pending_choice is None, "AI path must clear pending_choice"
    assert captured["selected"] is not None, "Handler should have fired"
    assert len(events) == 1 and events[0].type == EventType.LIFE_CHANGE
    print("PASS: AI choice resolves inline, clears pending_choice")


def test_ai_handler_heuristic_pick_overrides_default():
    """When no engine AI handler is registered, the resolver should fall
    back to ``callback_data['heuristic_pick']`` rather than always picking
    ``[0]``.
    """
    game = _make_game_with_ai(ai_player_ids={"bot_player"})

    captured = {"selected": None}

    def handler(choice, selected, state):
        captured["selected"] = list(selected)
        return []

    pc = PendingChoice(
        choice_type="modal_with_callback",
        player="bot_player",
        prompt="Pick one",
        options=[{"index": 0}, {"index": 1}, {"index": 2}],
        source_id="src",
        min_choices=1,
        max_choices=1,
        callback_data={"handler": handler, "heuristic_pick": 2},
    )
    game.state.pending_choice = pc
    resolve_pending_choice_inline(game.state)

    assert captured["selected"] == [2], (
        f"heuristic_pick should drive AI fallback, got {captured['selected']}"
    )
    print("PASS: heuristic_pick overrides default first-option")


def test_no_pending_choice_is_a_noop():
    """If state has no pending choice, the helper returns empty tuples."""
    game = _make_game_with_ai(ai_player_ids={"bot_player"})
    assert game.state.pending_choice is None
    events, selected = resolve_pending_choice_inline(game.state)
    assert events == [] and selected == []
    print("PASS: no choice => no-op")


def test_ai_handler_error_clears_choice_no_deadlock():
    """If the callback_data handler raises, the resolver still clears
    pending_choice so the engine doesn't deadlock waiting forever."""
    game = _make_game_with_ai(ai_player_ids={"bot_player"})

    def bad_handler(choice, selected, state):
        raise RuntimeError("simulated handler crash")

    _stash_choice(game, "bot_player", bad_handler)
    events, selected = resolve_pending_choice_inline(game.state)

    assert game.state.pending_choice is None, (
        "pending_choice must be cleared even on handler error"
    )
    assert events == [], "errored handler emits no events"
    print("PASS: handler error clears choice (no deadlock)")


def test_create_choice_and_resolve_for_ai():
    """The one-stop ``create_choice_and_resolve`` builds + resolves for AI."""
    game = _make_game_with_ai(ai_player_ids={"bot_player"})

    fired = {"value": False}

    def handler(choice, selected, state):
        fired["value"] = True
        return [Event(type=EventType.DRAW, payload={"player": "bot_player", "count": 1}, source="src")]

    events = create_choice_and_resolve(
        game.state,
        choice_type="modal_with_callback",
        player_id="bot_player",
        prompt="Pick one",
        options=[{"index": 0}, {"index": 1}],
        source_id="src",
        handler=handler,
    )

    assert fired["value"], "handler should fire on AI path"
    assert len(events) == 1 and events[0].type == EventType.DRAW
    assert game.state.pending_choice is None
    print("PASS: create_choice_and_resolve fires for AI")


def test_create_choice_and_resolve_for_human_leaves_pending():
    """``create_choice_and_resolve`` for a human leaves the choice
    pending and returns empty events.
    """
    game = _make_game_with_ai(ai_player_ids=set())

    handler_calls = {"count": 0}

    def handler(choice, selected, state):
        handler_calls["count"] += 1
        return []

    events = create_choice_and_resolve(
        game.state,
        choice_type="target",
        player_id="alice_human",
        prompt="Choose a target",
        options=[{"id": "obj_1"}, {"id": "obj_2"}],
        source_id="src",
        handler=handler,
    )

    assert events == [], "human path returns no events"
    assert game.state.pending_choice is not None
    assert game.state.pending_choice.player == "alice_human"
    assert handler_calls["count"] == 0, "handler must not fire for human"
    print("PASS: create_choice_and_resolve leaves pending for human")


if __name__ == "__main__":
    test_human_player_leaves_choice_pending()
    test_ai_player_resolves_inline_via_handler()
    test_ai_handler_heuristic_pick_overrides_default()
    test_no_pending_choice_is_a_noop()
    test_ai_handler_error_clears_choice_no_deadlock()
    test_create_choice_and_resolve_for_ai()
    test_create_choice_and_resolve_for_human_leaves_pending()
    print("ALL PASSED")
