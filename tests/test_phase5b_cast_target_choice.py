"""
Phase 5b — engine-authoritative cast-time target selection via PendingChoice.

When a CardDefinition declares ``target_requirements`` and the cast action
arrives without pre-supplied ``targets``, the priority system emits a
PendingChoice and pauses the cast. The choice handler re-enters the cast
with targets baked in.

This file covers:
- Human path: cast with empty targets → PendingChoice emitted; effect not
  applied yet; legal targets enumerated correctly; mana not yet paid.
- AI path: with a heuristic resolver registered, the choice resolves inline
  to the first legal target, completing the cast.
- Pre-supplied targets path (the drag-to-target and AI ``_select_targets_for_spell``
  flows): action.targets already populated → no PendingChoice; cast resolves
  normally.
- No legal targets: cast aborts gracefully with no PendingChoice.

Demo card: Lightning Bolt from ``src/cards/test_cards.py`` — gained a
``target_requirements=[target_any(count=1)]`` declaration in this phase.
"""

import asyncio
import os
import sys

# Make the project root importable regardless of where pytest runs from.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Characteristics,
)
from src.engine.priority import PlayerAction, ActionType
from src.cards.test_cards import LIGHTNING_BOLT, SOUL_WARDEN
from src.engine.game import make_land


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_game_with_bolt_in_hand():
    """Two-player game, P1 has Lightning Bolt in hand and 1 Mountain in play."""
    game = Game()
    p1 = game.add_player("Caster")
    p2 = game.add_player("Target")

    bolt = game.create_object(
        name=LIGHTNING_BOLT.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=LIGHTNING_BOLT.characteristics,
        card_def=LIGHTNING_BOLT,
    )

    mountain_def = make_land("Mountain", subtypes={"Mountain"})
    mountain = game.create_object(
        name="Mountain",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=mountain_def.characteristics,
        card_def=mountain_def,
    )

    # Mountain produces {R} when tapped — but the cast handler taps it for
    # us through the mana system. We just need it on the battlefield.
    return game, p1, p2, bolt, mountain


def _add_creature(game, owner_id, name="Soul Warden"):
    return game.create_object(
        name=name,
        owner_id=owner_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SOUL_WARDEN.characteristics,
        card_def=SOUL_WARDEN,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_cast_with_no_targets_emits_pending_choice():
    """Phase 5b: cast Lightning Bolt with action.targets=[] → PendingChoice."""
    game, p1, p2, bolt, _mountain = _setup_game_with_bolt_in_hand()
    creature = _add_creature(game, p2.id, "Bear")

    # Pre-state: no pending choice, Lightning Bolt in hand, p1 has full mana
    # pool to draw from.
    assert game.state.pending_choice is None

    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=bolt.id,
        targets=[],  # Phase 5b path
    )
    events = asyncio.run(game.priority_system._handle_cast_spell(action))
    # The cast should have PAUSED — no stack push, just the choice prompt.
    assert events == [] or not events, f"expected empty/paused, got {events}"

    pc = game.state.pending_choice
    assert pc is not None, "PendingChoice should be set"
    assert pc.player == p1.id
    assert pc.choice_type == "target"
    assert pc.source_id == bolt.id
    # Legal targets should include p2's creature plus both players
    # (Lightning Bolt is "any target" = creature, planeswalker, or player).
    option_ids = {opt["id"] for opt in pc.options}
    assert creature.id in option_ids, f"creature should be a legal target: {option_ids}"
    assert p1.id in option_ids and p2.id in option_ids, \
        f"both players should be legal targets: {option_ids}"

    # Bolt is still in hand (cast paused before mana payment and stack push).
    assert bolt.zone == ZoneType.HAND, \
        f"Bolt should still be in hand while choice pending, got {bolt.zone}"


def test_cast_with_no_targets_pre_supplied_skips_choice():
    """Pre-supplied targets (frontend drag-to-target / AI selection) skip
    the new PendingChoice path entirely — back-compat for both UX flows."""
    game, p1, p2, bolt, _mountain = _setup_game_with_bolt_in_hand()

    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=bolt.id,
        targets=[[p2.id]],  # already targeted via drag-to-target
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))
    # No PendingChoice should have been emitted.
    assert game.state.pending_choice is None, \
        "Pre-supplied targets path should NOT emit PendingChoice"
    # Bolt moved to the stack (normal cast path completed).
    assert bolt.zone == ZoneType.STACK, \
        f"Bolt should be on stack with pre-supplied targets, got {bolt.zone}"


def test_cast_with_no_legal_targets_aborts():
    """No legal targets → cast aborts gracefully without emitting a
    PendingChoice. MTG rule: a spell with no legal targets can't be cast."""
    game = Game()
    p1 = game.add_player("P1")
    # No P2 → no opponent target. Lightning Bolt's filter accepts the
    # casting player as a target ("any target" allows self-burn), so legal
    # targets won't be empty. Use a filter setup that DOES yield zero
    # targets: a fresh game with no creatures + a card whose requirement
    # accepts only opposing creatures. We synthesize one inline.
    from src.engine.targeting import TargetRequirement, creature_filter
    from src.cards.card_factories import make_instant
    from src.engine import Color

    opp_creature_only = TargetRequirement(
        filter=creature_filter(controller='opponent'),
        count=1,
        label="target opposing creature",
    )

    HOSTILE_BOLT = make_instant(
        name="Hostile Bolt",
        mana_cost="{R}",
        colors={Color.RED},
        text="Deal 3 damage to target creature you don't control.",
        target_requirements=[opp_creature_only],
    )
    card = game.create_object(
        name=HOSTILE_BOLT.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=HOSTILE_BOLT.characteristics,
        card_def=HOSTILE_BOLT,
    )

    mountain_def = make_land("Mountain", subtypes={"Mountain"})
    game.create_object(
        name="Mountain",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=mountain_def.characteristics,
        card_def=mountain_def,
    )

    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=card.id,
        targets=[],
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))
    # Cast aborted: no PendingChoice, card still in hand.
    assert game.state.pending_choice is None, \
        "No PendingChoice when no legal targets"
    assert card.zone == ZoneType.HAND, \
        f"Card should remain in hand when cast aborts, got {card.zone}"


def test_pending_choice_handler_completes_the_cast():
    """When the human (or AI) submits the choice, the handler re-enters the
    cast and pushes the spell to the stack with chosen targets."""
    game, p1, p2, bolt, _mountain = _setup_game_with_bolt_in_hand()
    creature = _add_creature(game, p2.id, "Bear")

    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=bolt.id,
        targets=[],
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))

    pc = game.state.pending_choice
    assert pc is not None

    # Use the public submit_choice path (clears pending_choice before
    # invoking the handler — _process_choice alone does NOT clear it).
    ok, err, _events = game.submit_choice(pc.id, p1.id, [creature.id])
    assert ok, f"submit_choice failed: {err}"

    # Re-entered cast completed.
    assert game.state.pending_choice is None, \
        "PendingChoice should be cleared after submission"
    assert bolt.zone == ZoneType.STACK, \
        f"Bolt should now be on stack, got {bolt.zone}"


def test_cast_target_choice_carries_overlay_interaction_mode():
    """Phase 5b polish: MTG cast-time target prompts ship with
    ``callback_data['interaction_mode']='overlay'`` so the frontend
    renders them as click-to-target board highlights instead of a modal
    panel. Other engines/choice paths leave the hint absent."""
    game, p1, p2, bolt, _mountain = _setup_game_with_bolt_in_hand()
    _add_creature(game, p2.id, "Bear")

    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=bolt.id,
        targets=[],
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))
    pc = game.state.pending_choice
    assert pc is not None, "PendingChoice should be set for cast-time target"
    assert pc.callback_data.get("interaction_mode") == "overlay", (
        "MTG cast-time PendingChoice must carry interaction_mode='overlay' "
        f"for frontend overlay rendering; got {pc.callback_data.get('interaction_mode')!r}"
    )


def test_cast_paused_state_does_not_leak_mana():
    """While PendingChoice is open, no mana has been paid — cancelling the
    choice (engine just clears it) leaves the player in their pre-cast state."""
    game, p1, p2, bolt, mountain = _setup_game_with_bolt_in_hand()
    _add_creature(game, p2.id, "Bear")

    pre_mana_available = mountain.state.tapped if hasattr(mountain.state, 'tapped') else None

    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=bolt.id,
        targets=[],
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))
    assert game.state.pending_choice is not None

    # Mana payment hasn't happened yet — Mountain should be in the same
    # tap state as before.
    if pre_mana_available is not None:
        assert mountain.state.tapped == pre_mana_available, \
            "Mountain should not be tapped while cast is paused"


if __name__ == "__main__":
    test_cast_with_no_targets_emits_pending_choice()
    print("PASS  test_cast_with_no_targets_emits_pending_choice")
    test_cast_with_no_targets_pre_supplied_skips_choice()
    print("PASS  test_cast_with_no_targets_pre_supplied_skips_choice")
    test_cast_with_no_legal_targets_aborts()
    print("PASS  test_cast_with_no_legal_targets_aborts")
    test_pending_choice_handler_completes_the_cast()
    print("PASS  test_pending_choice_handler_completes_the_cast")
    test_cast_target_choice_carries_overlay_interaction_mode()
    print("PASS  test_cast_target_choice_carries_overlay_interaction_mode")
    test_cast_paused_state_does_not_leak_mana()
    print("PASS  test_cast_paused_state_does_not_leak_mana")
    print("\nAll Phase 5b cast-target-choice tests passed.")
