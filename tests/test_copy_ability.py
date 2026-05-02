"""
Test Copy-Ability Mechanic

Tests for "Copy target activated or triggered ability you control":
- StackItem.copy() preserves resolve_fn / source / controller / additional_data.
- StackManager.push_copy() pushes a copy and assigns a fresh id + timestamp.
- The COPY_STACK_ITEM event handler dispatches push_copy via state._game.stack.
- The copy resolves with the same effect as the original.
- Copy with new_targets resolves against the new targets, not the original.
- can_be_copied=False refuses the copy.
"""

import os
import sys

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, GameState, Event, EventType, ZoneType, CardType,
)
from src.engine.stack import StackManager, StackItem, StackItemType
from src.engine.targeting import Target
from src.cards.interceptor_helpers import make_copy_ability_event


# =============================================================================
# Test fixtures / helpers
# =============================================================================

def _make_target(target_id: str) -> Target:
    """Build a non-player Target with id only."""
    return Target(id=target_id, is_player=False)


def _make_player_target(player_id: str) -> Target:
    return Target(id=player_id, is_player=True)


def make_game_two_players():
    game = Game()
    p1 = game.add_player("Alice", life=20)
    p2 = game.add_player("Bob", life=20)
    return game, p1, p2


# =============================================================================
# StackItem.copy()
# =============================================================================

class TestStackItemCopy:
    """Direct tests on StackItem.copy() — the dataclass clone helper."""

    def test_copy_preserves_resolve_fn_and_metadata(self):
        marker = []

        def resolve_fn(targets, state):
            marker.append(("called", targets))
            return []

        original = StackItem(
            id="orig",
            type=StackItemType.TRIGGERED_ABILITY,
            source_id="source-1",
            controller_id="p1",
            chosen_targets=[[_make_target("t1")]],
            resolve_fn=resolve_fn,
            additional_data={"foo": "bar"},
        )
        copy = original.copy()

        assert copy.id != original.id
        assert copy.is_copy is True
        assert copy.type == original.type
        assert copy.source_id == original.source_id
        assert copy.controller_id == original.controller_id
        assert copy.resolve_fn is resolve_fn
        assert copy.additional_data == {"foo": "bar"}
        # additional_data must be a separate dict (mutating one shouldn't affect the other).
        assert copy.additional_data is not original.additional_data

    def test_copy_keeps_targets_when_new_targets_omitted(self):
        original = StackItem(
            id="orig",
            type=StackItemType.TRIGGERED_ABILITY,
            source_id="src",
            controller_id="p1",
            chosen_targets=[[_make_target("alpha"), _make_target("beta")]],
        )
        copy = original.copy()
        assert len(copy.chosen_targets) == 1
        assert [t.id for t in copy.chosen_targets[0]] == ["alpha", "beta"]
        # And the lists are independent.
        assert copy.chosen_targets is not original.chosen_targets

    def test_copy_uses_new_targets_when_supplied(self):
        original = StackItem(
            id="orig",
            type=StackItemType.TRIGGERED_ABILITY,
            source_id="src",
            controller_id="p1",
            chosen_targets=[[_make_target("alpha")]],
        )
        new_targets = [[_make_target("zulu")]]
        copy = original.copy(new_targets=new_targets)
        assert [t.id for t in copy.chosen_targets[0]] == ["zulu"]


# =============================================================================
# StackManager.push_copy()
# =============================================================================

class TestStackManagerPushCopy:

    def test_push_copy_by_item(self):
        state = GameState()
        stack = StackManager(state)
        original = StackItem(
            id="",
            type=StackItemType.TRIGGERED_ABILITY,
            source_id="src",
            controller_id="p1",
            resolve_fn=lambda t, s: [],
        )
        stack.push(original)
        copy = stack.push_copy(original)
        assert copy is not None
        assert copy.id != original.id
        assert stack.size() == 2
        # Top of stack is the copy (most recent).
        assert stack.top().id == copy.id
        assert stack.top().is_copy is True

    def test_push_copy_by_id(self):
        state = GameState()
        stack = StackManager(state)
        original = StackItem(
            id="",
            type=StackItemType.TRIGGERED_ABILITY,
            source_id="src",
            controller_id="p1",
            resolve_fn=lambda t, s: [],
        )
        stack.push(original)
        copy = stack.push_copy(original.id)
        assert copy is not None
        assert stack.size() == 2

    def test_push_copy_with_new_targets(self):
        state = GameState()
        stack = StackManager(state)
        original = StackItem(
            id="",
            type=StackItemType.TRIGGERED_ABILITY,
            source_id="src",
            controller_id="p1",
            chosen_targets=[[_make_target("orig-target")]],
            resolve_fn=lambda t, s: [],
        )
        stack.push(original)
        copy = stack.push_copy(
            original.id,
            new_targets=[[_make_target("new-target")]],
        )
        assert copy is not None
        assert [t.id for t in copy.chosen_targets[0]] == ["new-target"]
        # Original is unchanged.
        assert [t.id for t in original.chosen_targets[0]] == ["orig-target"]

    def test_push_copy_refuses_when_can_be_copied_false(self):
        state = GameState()
        stack = StackManager(state)
        original = StackItem(
            id="",
            type=StackItemType.TRIGGERED_ABILITY,
            source_id="src",
            controller_id="p1",
            resolve_fn=lambda t, s: [],
            can_be_copied=False,
        )
        stack.push(original)
        result = stack.push_copy(original.id)
        assert result is None
        assert stack.size() == 1

    def test_push_copy_returns_none_for_unknown_id(self):
        state = GameState()
        stack = StackManager(state)
        result = stack.push_copy("does-not-exist")
        assert result is None


# =============================================================================
# Copy resolves with the same effect (full-game integration)
# =============================================================================

class TestCopyResolvesSameEffect:
    """End-to-end: push a stack item, copy it via the event handler, resolve both."""

    def test_copied_triggered_ability_resolves_same_effect(self):
        """Copying a triggered ability stack item — the copy resolves with the same effect."""
        game, p1, p2 = make_game_two_players()

        # Build a triggered ability stack item that draws a card for the controller.
        def resolve_fn(targets, state):
            return [Event(
                type=EventType.DRAW,
                payload={'count': 1, 'player': p1.id},
                source="src",
                controller=p1.id,
            )]

        original = StackItem(
            id="",
            type=StackItemType.TRIGGERED_ABILITY,
            source_id="src",
            controller_id=p1.id,
            resolve_fn=resolve_fn,
        )
        game.stack.push(original)

        # Emit a COPY_STACK_ITEM event — handler should push a copy.
        game.emit(make_copy_ability_event(
            stack_item_id=original.id,
            controller=p1.id,
            source_id="src",
        ))
        assert game.stack.size() == 2

        # Resolve top (copy) and then original — both should produce a DRAW event.
        copy_events = game.stack.resolve_top()
        # The resolve_fn returns Events; they're not auto-emitted by resolve_top
        # (the priority system normally emits these). So check the returned list.
        assert any(e.type == EventType.DRAW for e in copy_events)
        original_events = game.stack.resolve_top()
        assert any(e.type == EventType.DRAW for e in original_events)
        assert game.stack.is_empty()

    def test_copy_with_new_targets_uses_new_targets_at_resolve(self):
        """Copy with new_targets — the copy resolves against the new targets, not the original."""
        game, p1, p2 = make_game_two_players()

        captured = []

        def resolve_fn(targets, state):
            # targets is list[list[Target]]; capture target ids for inspection.
            ids = []
            for group in (targets or []):
                for t in group:
                    ids.append(t.id)
            captured.append(tuple(ids))
            return []

        original = StackItem(
            id="",
            type=StackItemType.TRIGGERED_ABILITY,
            source_id="src",
            controller_id=p1.id,
            chosen_targets=[[_make_target("orig-target")]],
            resolve_fn=resolve_fn,
        )
        game.stack.push(original)

        # Copy with new targets via the helper.
        game.emit(make_copy_ability_event(
            stack_item_id=original.id,
            controller=p1.id,
            source_id="src",
            new_targets=[[_make_target("new-target")]],
        ))
        assert game.stack.size() == 2

        # Resolve top first: that's the copy, with new targets.
        game.stack.resolve_top()
        # Then resolve the original.
        game.stack.resolve_top()

        assert len(captured) == 2
        # Order: copy resolves first (it was pushed last), then original.
        assert captured[0] == ("new-target",)
        assert captured[1] == ("orig-target",)

    def test_copy_preserves_resolve_fn_semantics(self):
        """Copying preserves resolve_fn semantics — closures over local state still work."""
        game, p1, p2 = make_game_two_players()

        # A resolve_fn that closes over a counter; copying should share the same fn
        # so both resolutions increment the same counter.
        counter = {"count": 0}

        def resolve_fn(targets, state):
            counter["count"] += 1
            return []

        original = StackItem(
            id="",
            type=StackItemType.TRIGGERED_ABILITY,
            source_id="src",
            controller_id=p1.id,
            resolve_fn=resolve_fn,
        )
        game.stack.push(original)
        game.emit(make_copy_ability_event(
            stack_item_id=original.id,
            controller=p1.id,
            source_id="src",
        ))

        # Resolve both.
        game.stack.resolve_top()
        game.stack.resolve_top()

        assert counter["count"] == 2  # Both the original and the copy resolved the same fn


# =============================================================================
# COPY_STACK_ITEM event integration
# =============================================================================

class TestCopyStackItemEvent:

    def test_copy_stack_item_event_pushes_copy(self):
        """The COPY_STACK_ITEM event handler pushes a copy onto the stack."""
        game, p1, p2 = make_game_two_players()

        original = StackItem(
            id="",
            type=StackItemType.TRIGGERED_ABILITY,
            source_id="src",
            controller_id=p1.id,
            resolve_fn=lambda t, s: [],
        )
        game.stack.push(original)
        assert game.stack.size() == 1

        game.emit(make_copy_ability_event(
            stack_item_id=original.id,
            controller=p1.id,
            source_id="src",
        ))
        assert game.stack.size() == 2
        assert game.stack.top().is_copy is True
        assert game.stack.top().id != original.id

    def test_copy_stack_item_event_with_unknown_id_is_noop(self):
        """The handler safely ignores unknown stack_item_ids."""
        game, p1, _ = make_game_two_players()
        before_size = game.stack.size()
        game.emit(make_copy_ability_event(
            stack_item_id="nonexistent",
            controller=p1.id,
            source_id="src",
        ))
        assert game.stack.size() == before_size


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
