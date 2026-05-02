"""Insidious Fungus (DSK) — modal activated ability tests.

Tests for the W6 wiring:
  {2}, Sacrifice this creature: Choose one —
    • Destroy target artifact.
    • Destroy target enchantment.
    • Draw a card. (then "may put a land from hand tapped" rider — engine gap, skipped)

Verifies:
  - Mode 0 chains a target_with_callback for an artifact, only artifacts are legal,
    and submitting destroys the chosen artifact.
  - Mode 1 chains the same flow for an enchantment.
  - Mode 2 still draws a card with no target prompt.
"""
import os
import sys
import asyncio

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, Characteristics,
    make_enchantment,
)
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase
from src.engine.mana import ManaType
from src.cards.duskmourn import INSIDIOUS_FUNGUS
from src.cards.card_factories import make_artifact


def _spawn_fungus(game, player):
    fungus = game.create_object(
        name=INSIDIOUS_FUNGUS.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=INSIDIOUS_FUNGUS.characteristics,
        card_def=None,
    )
    fungus.card_def = INSIDIOUS_FUNGUS
    # Drop on the battlefield via ZONE_CHANGE so setup_interceptors fires
    # through the pipeline path (this registers the activated ability).
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': fungus.id,
            'from_zone': f'hand_{player.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    fungus.state.summoning_sickness = False
    return fungus


def _spawn_permanent(game, player, card_def):
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    return obj


def _activate_fungus(game, fungus, player):
    """Activate the modal ability and resolve its stack item.

    Returns the resolved events list (which is empty because the ability
    installs a pending modal choice rather than emitting events directly).
    """
    # Provide {2}.
    game.mana_system.produce_mana(player.id, ManaType.COLORLESS, 2)
    game.turn_manager.turn_state.active_player_id = player.id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

    action = PlayerAction(
        type=ActionType.ACTIVATE_ABILITY,
        player_id=player.id,
        source_id=fungus.id,
        ability_id="activated:0",
    )

    async def _run():
        return await game.priority_system._handle_activate_ability(action)

    cost_events = asyncio.get_event_loop().run_until_complete(_run())
    # Emit cost events (SACRIFICE → graveyard, ACTIVATE).
    for ev in cost_events:
        game.emit(ev)

    # Resolve the activated-ability stack item.
    assert game.stack.items, "activated ability should have pushed a stack item"
    item = game.stack.items[-1]
    resolved = item.resolve_fn(item.chosen_targets, game.state) if item.resolve_fn else []
    # Pop the item now that it has resolved (mirrors stack.resolve_top behavior).
    game.stack.items.pop()
    for ev in resolved:
        game.emit(ev)
    return resolved


# A standalone artifact and enchantment that don't touch the engine.
TEST_ARTIFACT = make_artifact(name="Test Artifact", mana_cost="{1}", text="")
TEST_ENCHANTMENT = make_enchantment(name="Test Enchantment", mana_cost="{1}",
                                    colors={Color.WHITE}, text="")


def test_insidious_fungus_mode_0_destroys_artifact():
    """Mode 0: pick artifact target → OBJECT_DESTROYED moves it off the battlefield."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    fungus = _spawn_fungus(game, p1)
    artifact = _spawn_permanent(game, p1, TEST_ARTIFACT)
    enchantment = _spawn_permanent(game, p1, TEST_ENCHANTMENT)

    _activate_fungus(game, fungus, p1)

    # First pending choice is the modal pick.
    pc = game.state.pending_choice
    assert pc is not None, "modal choice should be pending after resolve"
    assert pc.choice_type == "modal_with_callback", f"expected modal_with_callback, got {pc.choice_type}"

    # Pick mode 0 (destroy target artifact).
    ok, err, _ = game.submit_choice(pc.id, p1.id, [0])
    assert ok, f"submit_choice (mode pick) failed: {err}"

    # Now we should have a target_with_callback choice prompting for an artifact.
    pc2 = game.state.pending_choice
    assert pc2 is not None, "target choice should be pending after picking mode 0"
    assert pc2.choice_type == "target_with_callback", (
        f"expected target_with_callback, got {pc2.choice_type}"
    )
    assert artifact.id in pc2.options, (
        f"artifact {artifact.id} should be a legal target; options={pc2.options}"
    )
    assert enchantment.id not in pc2.options, (
        f"enchantment should NOT be a legal target for mode 0; options={pc2.options}"
    )

    # Pick the artifact.
    ok, err, _ = game.submit_choice(pc2.id, p1.id, [artifact.id])
    assert ok, f"submit_choice (target pick) failed: {err}"

    # Artifact is destroyed → moved to graveyard (or removed from battlefield).
    after = game.state.objects.get(artifact.id)
    assert after is None or after.zone != ZoneType.BATTLEFIELD, (
        f"artifact should leave the battlefield after destroy; "
        f"zone={getattr(after, 'zone', 'gone')}"
    )

    # Enchantment is untouched.
    ench_after = game.state.objects.get(enchantment.id)
    assert ench_after is not None and ench_after.zone == ZoneType.BATTLEFIELD, (
        f"enchantment should be unaffected; zone={getattr(ench_after, 'zone', None)}"
    )

    print("PASS: Insidious Fungus mode 0 destroys target artifact")


def test_insidious_fungus_mode_1_destroys_enchantment():
    """Mode 1: pick enchantment target → OBJECT_DESTROYED moves it off the battlefield."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    fungus = _spawn_fungus(game, p1)
    artifact = _spawn_permanent(game, p1, TEST_ARTIFACT)
    enchantment = _spawn_permanent(game, p1, TEST_ENCHANTMENT)

    _activate_fungus(game, fungus, p1)

    pc = game.state.pending_choice
    assert pc is not None and pc.choice_type == "modal_with_callback"

    # Pick mode 1.
    ok, err, _ = game.submit_choice(pc.id, p1.id, [1])
    assert ok, f"submit_choice (mode pick) failed: {err}"

    pc2 = game.state.pending_choice
    assert pc2 is not None and pc2.choice_type == "target_with_callback"
    assert enchantment.id in pc2.options
    assert artifact.id not in pc2.options, (
        f"artifact should NOT be a legal target for mode 1; options={pc2.options}"
    )

    ok, err, _ = game.submit_choice(pc2.id, p1.id, [enchantment.id])
    assert ok, f"submit_choice (target pick) failed: {err}"

    after = game.state.objects.get(enchantment.id)
    assert after is None or after.zone != ZoneType.BATTLEFIELD, (
        f"enchantment should leave the battlefield; zone={getattr(after, 'zone', 'gone')}"
    )

    art_after = game.state.objects.get(artifact.id)
    assert art_after is not None and art_after.zone == ZoneType.BATTLEFIELD, (
        f"artifact should be unaffected; zone={getattr(art_after, 'zone', None)}"
    )

    print("PASS: Insidious Fungus mode 1 destroys target enchantment")


def test_insidious_fungus_mode_2_draws_card():
    """Mode 2: draws a card and prompts no follow-up target choice."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Stock the library with at least one card so DRAW has something to fetch.
    library_key = f"library_{p1.id}"
    if library_key in game.state.zones:
        from src.cards.card_factories import make_artifact as _ma
        seed_def = _ma(name="Library Seed", mana_cost="{0}", text="")
        seed = game.create_object(
            name=seed_def.name,
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=seed_def.characteristics,
            card_def=seed_def,
        )
        game.state.zones[library_key].objects.append(seed.id)

    fungus = _spawn_fungus(game, p1)
    hand_key = f"hand_{p1.id}"
    hand_before = len(game.state.zones[hand_key].objects) if hand_key in game.state.zones else 0

    _activate_fungus(game, fungus, p1)

    pc = game.state.pending_choice
    assert pc is not None and pc.choice_type == "modal_with_callback"

    ok, err, evs = game.submit_choice(pc.id, p1.id, [2])
    assert ok, f"submit_choice (mode 2) failed: {err}"

    # No follow-up choice should be pending (mode 2 does not chain a target).
    assert game.state.pending_choice is None, (
        f"mode 2 should not chain another choice; pending={game.state.pending_choice}"
    )

    # A DRAW event must have been emitted.
    types = [e.type for e in evs]
    assert EventType.DRAW in types, f"expected DRAW event in {types}"

    # Player drew at least one card (when the library had a card).
    if hand_key in game.state.zones:
        hand_after = len(game.state.zones[hand_key].objects)
        assert hand_after == hand_before + 1, (
            f"player should have drawn 1 card; before={hand_before}, after={hand_after}"
        )

    print("PASS: Insidious Fungus mode 2 draws a card")


if __name__ == "__main__":
    test_insidious_fungus_mode_0_destroys_artifact()
    test_insidious_fungus_mode_1_destroys_enchantment()
    test_insidious_fungus_mode_2_draws_card()
    print("\nAll Insidious Fungus tests passed!")
