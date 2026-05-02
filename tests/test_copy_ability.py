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
    Characteristics,
)
from src.engine.stack import StackManager, StackItem, StackItemType
from src.engine.targeting import (
    Target, TargetRequirement, TargetFilter, target_creature, target_any,
)
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


# =============================================================================
# Virtue of Knowledge — collect new targets after picking the stack item
# =============================================================================

class TestVirtueOfKnowledgeRetarget:
    """The Adventure half of Virtue of Knowledge ("Vantress Visions"):
    Copy target activated/triggered ability you control. You may choose
    new targets for the copy.
    """

    @staticmethod
    def _setup_virtue_game():
        """Build a two-player game and place Virtue of Knowledge on the
        battlefield as the source. Returns (game, p1, p2, virtue)."""
        game, p1, p2 = make_game_two_players()
        # Create a permanent to act as the Adventure source. Real Virtue of
        # Knowledge is an enchantment; the source object's controller and id
        # are the only things the resolve callback uses.
        virtue = game.create_object(
            name="Virtue of Knowledge",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(
                types={CardType.ENCHANTMENT},
                colors=set(),
            ),
        )
        return game, p1, p2, virtue

    @staticmethod
    def _make_creature(game, owner_id, name, *, power=2, toughness=2):
        return game.create_object(
            name=name,
            owner_id=owner_id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(
                types={CardType.CREATURE},
                power=power,
                toughness=toughness,
            ),
        )

    def test_virtue_of_knowledge_retarget_single_target(self):
        """Lightning-Strike-like spell (1 target creature, 3 damage); cast
        Virtue of Knowledge Adventure, pick the strike, choose a NEW creature.
        Resolve and assert damage went to the NEW target, not the original."""
        from src.cards.wilds_of_eldraine import _virtue_of_knowledge_adventure

        game, p1, p2, virtue = self._setup_virtue_game()

        # Two creatures controlled by p2 — original target and a new target.
        original_creature = self._make_creature(game, p2.id, "Bear A", power=2, toughness=4)
        new_creature = self._make_creature(game, p2.id, "Bear B", power=2, toughness=4)

        # Build a "Lightning Strike"-like stack item: deal 3 damage to target.
        damage_log = []  # Capture each resolution so we can check both copies.

        def strike_resolve(targets, state):
            # targets is list[list[Target]]; one inner list per requirement.
            tids = []
            for group in (targets or []):
                for t in group:
                    tids.append(t.id)
            damage_log.append(tuple(tids))
            return []

        # The source needs to be a real GameObject because stack.resolve_top
        # passes it to TargetingSystem.validate_targets (which reads .characteristics).
        strike_source = game.create_object(
            name="Lightning Strike",
            owner_id=p1.id,
            zone=ZoneType.STACK,
            characteristics=Characteristics(
                types={CardType.INSTANT},
                colors=set(),
            ),
        )

        strike_item = StackItem(
            id="",
            type=StackItemType.SPELL,
            source_id=strike_source.id,
            controller_id=p1.id,
            target_requirements=[target_creature(count=1)],
            chosen_targets=[[_make_target(original_creature.id)]],
            resolve_fn=strike_resolve,
        )
        game.stack.push(strike_item)
        original_id = strike_item.id

        # Now invoke Virtue of Knowledge's adventure resolve — it should set up
        # a target_with_callback PendingChoice over stack items p1 controls.
        events = _virtue_of_knowledge_adventure(virtue, game.state, [])
        assert events == [], "Adventure resolve only sets pending_choice; no events yet"
        choice1 = game.state.pending_choice
        assert choice1 is not None, "Should have created a pending choice"
        assert choice1.choice_type == "target_with_callback"
        assert original_id in choice1.options

        # Player picks the strike. The handler should walk the strike's
        # target_requirements and chain a second target_with_callback choice
        # for picking a NEW target creature.
        ok, msg, _evs = game.submit_choice(choice1.id, p1.id, [original_id])
        assert ok, f"Submit should succeed: {msg}"

        choice2 = game.state.pending_choice
        assert choice2 is not None, "Should have chained a second choice for new targets"
        assert choice2.choice_type == "target_with_callback"
        # Both creatures should be legal targets (creature filter, no controller restriction).
        assert original_creature.id in choice2.options
        assert new_creature.id in choice2.options

        # Player picks the NEW creature. The handler should emit a
        # COPY_STACK_ITEM event with new_targets pointing at new_creature.
        ok2, msg2, _evs2 = game.submit_choice(choice2.id, p1.id, [new_creature.id])
        assert ok2, f"Second submit should succeed: {msg2}"

        # Stack should now have the original strike and one copy.
        assert game.stack.size() == 2, f"Expected 2 items on stack, got {game.stack.size()}"
        copy_item = game.stack.top()
        assert copy_item.is_copy is True

        # The copy's chosen_targets should be the new creature, NOT the original.
        assert len(copy_item.chosen_targets) == 1
        copy_target_ids = [t.id for t in copy_item.chosen_targets[0]]
        assert copy_target_ids == [new_creature.id], (
            f"Copy should target new creature {new_creature.id}, got {copy_target_ids}"
        )

        # And the original strike still targets the ORIGINAL creature.
        assert [t.id for t in strike_item.chosen_targets[0]] == [original_creature.id]

        # Resolve top first (the copy) -> resolve_fn sees the new target.
        game.stack.resolve_top()
        # Then resolve the original.
        game.stack.resolve_top()

        # Order: copy resolves first (it was pushed last), then the original.
        assert len(damage_log) == 2
        assert damage_log[0] == (new_creature.id,), (
            f"Copy resolved against new target; got {damage_log[0]}"
        )
        assert damage_log[1] == (original_creature.id,), (
            f"Original strike resolved against original target; got {damage_log[1]}"
        )

    def test_virtue_of_knowledge_retarget_two_targets(self):
        """Spell with 2 target requirements (e.g. one damage source picks two
        different creatures). Both retargeted to fresh choices in order."""
        from src.cards.wilds_of_eldraine import _virtue_of_knowledge_adventure

        game, p1, p2, virtue = self._setup_virtue_game()

        # Four creatures: 2 originals, 2 new — the player will retarget both.
        orig_a = self._make_creature(game, p2.id, "Bear Alpha")
        orig_b = self._make_creature(game, p2.id, "Bear Beta")
        new_a = self._make_creature(game, p2.id, "Bear Gamma")
        new_b = self._make_creature(game, p2.id, "Bear Delta")

        captured = []

        def two_target_resolve(targets, state):
            ids = []
            for group in (targets or []):
                ids.append(tuple(t.id for t in group))
            captured.append(tuple(ids))
            return []

        # Use two `target_creature` requirements — distinct labels would be
        # useful in real cards, but the engine handles both the same way here.
        # Real source object — see explanation in single-target test.
        multi_source = game.create_object(
            name="Two-Target Spell",
            owner_id=p1.id,
            zone=ZoneType.STACK,
            characteristics=Characteristics(
                types={CardType.SORCERY},
                colors=set(),
            ),
        )

        item = StackItem(
            id="",
            type=StackItemType.SPELL,
            source_id=multi_source.id,
            controller_id=p1.id,
            target_requirements=[
                target_creature(count=1),
                target_creature(count=1),
            ],
            chosen_targets=[
                [_make_target(orig_a.id)],
                [_make_target(orig_b.id)],
            ],
            resolve_fn=two_target_resolve,
        )
        game.stack.push(item)
        original_id = item.id

        # Step 1: invoke Virtue's adventure resolve.
        _virtue_of_knowledge_adventure(virtue, game.state, [])
        choice0 = game.state.pending_choice
        assert choice0 is not None and original_id in choice0.options
        ok, msg, _ = game.submit_choice(choice0.id, p1.id, [original_id])
        assert ok, msg

        # Step 2: choose new target for the FIRST requirement.
        choice_req1 = game.state.pending_choice
        assert choice_req1 is not None, "Should chain first requirement choice"
        assert new_a.id in choice_req1.options
        ok1, msg1, _ = game.submit_choice(choice_req1.id, p1.id, [new_a.id])
        assert ok1, msg1

        # Step 3: choose new target for the SECOND requirement.
        choice_req2 = game.state.pending_choice
        assert choice_req2 is not None, "Should chain second requirement choice"
        assert new_b.id in choice_req2.options
        ok2, msg2, _ = game.submit_choice(choice_req2.id, p1.id, [new_b.id])
        assert ok2, msg2

        # No further choices needed; the copy is on the stack.
        assert game.state.pending_choice is None
        assert game.stack.size() == 2
        copy_item = game.stack.top()
        assert copy_item.is_copy is True

        # Verify the copy's targets match the new selections, in order.
        assert len(copy_item.chosen_targets) == 2
        assert [t.id for t in copy_item.chosen_targets[0]] == [new_a.id]
        assert [t.id for t in copy_item.chosen_targets[1]] == [new_b.id]

        # Original is unchanged.
        assert [t.id for t in item.chosen_targets[0]] == [orig_a.id]
        assert [t.id for t in item.chosen_targets[1]] == [orig_b.id]

        # Resolve and check the resolve_fn saw the new targets first, then originals.
        game.stack.resolve_top()
        game.stack.resolve_top()
        assert len(captured) == 2
        assert captured[0] == ((new_a.id,), (new_b.id,))
        assert captured[1] == ((orig_a.id,), (orig_b.id,))

    def test_virtue_of_knowledge_no_targets_just_copies(self):
        """Spell with no targets (e.g. 'each player draws a card') — should
        copy without prompting, and the copy's chosen_targets is empty."""
        from src.cards.wilds_of_eldraine import _virtue_of_knowledge_adventure

        game, p1, p2, virtue = self._setup_virtue_game()

        resolve_count = {'n': 0}

        def draw_resolve(targets, state):
            # No targets — just count resolutions.
            resolve_count['n'] += 1
            return []

        item = StackItem(
            id="",
            type=StackItemType.SPELL,
            source_id="howling-mine-src",
            controller_id=p1.id,
            target_requirements=[],   # No targets!
            chosen_targets=[],
            resolve_fn=draw_resolve,
        )
        game.stack.push(item)
        original_id = item.id

        # Invoke virtue's adventure resolve.
        _virtue_of_knowledge_adventure(virtue, game.state, [])
        choice = game.state.pending_choice
        assert choice is not None
        ok, msg, _ = game.submit_choice(choice.id, p1.id, [original_id])
        assert ok, msg

        # No second choice should appear — the copy was pushed directly.
        assert game.state.pending_choice is None, (
            "No-target spell should not prompt for new targets"
        )
        assert game.stack.size() == 2, "Original + copy should both be on the stack"
        copy_item = game.stack.top()
        assert copy_item.is_copy is True
        assert copy_item.chosen_targets == []

        # Resolve both — both should call the resolve_fn.
        game.stack.resolve_top()
        game.stack.resolve_top()
        assert resolve_count['n'] == 2


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
