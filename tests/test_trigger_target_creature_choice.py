"""
Tests for ``create_target_creature_choice`` — Gap 2 (trigger-time creature
targeting via PendingChoice).

Background
----------
Triggered abilities historically had to deterministically pick a target via
filter (e.g. "first eligible") because no helper existed to open a
PendingChoice mid-trigger. The Helper 5 sweep (Clima-Tact, Shock Gauntlets,
Temporal Blade, Chitauri Scepter) all worked around this by picking the
first eligible creature.

``create_target_creature_choice`` mirrors ``create_library_search_choice``
for battlefield creatures: an effect_fn opens the choice, returns ``[]``,
and the chosen-creature callback emits the actual effect events.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, ZoneType, CardType, Color,
    Event, EventType,
    make_creature, make_land,
)
from src.cards.interceptor_helpers import create_target_creature_choice


def _make_bear(name: str, p: int = 2, t: int = 2):
    return make_creature(
        name=name, power=p, toughness=t,
        mana_cost="{1}{G}", colors={Color.GREEN},
        subtypes={"Bear"},
        text="",
    )


def _setup_game_two_players():
    from src.engine.turn import Phase
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    if game.turn_manager is not None:
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN
    return game, p1, p2


def test_target_creature_choice_returns_none_with_no_valid_targets():
    """An empty battlefield should give no choice and silently no-op."""
    game, p1, _ = _setup_game_two_players()
    source_def = _make_bear("Source")
    source = game.create_object(
        name=source_def.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=source_def.characteristics, card_def=source_def,
    )
    # No other creatures — filter_fn excludes self.
    def exclude_self(o, st):
        return o.id != source.id

    choice = create_target_creature_choice(
        game.state, p1.id, source.id, filter_fn=exclude_self,
    )
    assert choice is None
    assert game.state.pending_choice is None


def test_target_creature_choice_opens_pending_choice():
    """Two valid creatures => a choice opens with those candidates."""
    game, p1, p2 = _setup_game_two_players()
    source_def = _make_bear("Source")
    source = game.create_object(
        name=source_def.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=source_def.characteristics, card_def=source_def,
    )
    target_a = game.create_object(
        name="Target A", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=_make_bear("Target A").characteristics,
        card_def=_make_bear("Target A"),
    )
    target_b = game.create_object(
        name="Target B", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=_make_bear("Target B").characteristics,
        card_def=_make_bear("Target B"),
    )

    def opponents_creatures(o, st):
        return o.controller != p1.id

    choice = create_target_creature_choice(
        game.state, p1.id, source.id, filter_fn=opponents_creatures,
        prompt="Choose an opponent creature",
    )
    assert choice is not None
    assert game.state.pending_choice is choice
    assert choice.choice_type == "target"
    assert choice.player == p1.id
    assert set(choice.options) == {target_a.id, target_b.id}


def test_target_creature_choice_callback_emits_effect():
    """Submitting the choice runs the effect_fn and the engine emits its events."""
    game, p1, p2 = _setup_game_two_players()
    source_def = _make_bear("Source")
    source = game.create_object(
        name=source_def.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=source_def.characteristics, card_def=source_def,
    )
    target = game.create_object(
        name="Target", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=_make_bear("Target").characteristics,
        card_def=_make_bear("Target"),
    )

    # The effect_fn taps the chosen creature.
    def tap_effect(target_obj, state):
        return [Event(
            type=EventType.TAP,
            payload={'object_id': target_obj.id},
            source=source.id,
        )]

    choice = create_target_creature_choice(
        game.state, p1.id, source.id,
        filter_fn=lambda o, st: o.controller != p1.id,
        effect_fn=tap_effect,
        prompt="Choose a creature to tap",
    )
    assert choice is not None

    # Resolve the choice — picks target.
    events = game.submit_choice(choice.id, p1.id, [target.id])
    # The handler is dispatched and emits TAP — the target should now be tapped.
    assert target.state.tapped is True, (
        f"Expected target to be tapped after choice; events were: {events}"
    )
    # Choice should be cleared after submission.
    assert game.state.pending_choice is None


def test_target_creature_choice_handler_skips_invalid_after_choice():
    """If the target leaves the battlefield between choice and resolve, the
    handler should silently skip it rather than throwing."""
    game, p1, p2 = _setup_game_two_players()
    source_def = _make_bear("Source")
    source = game.create_object(
        name=source_def.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=source_def.characteristics, card_def=source_def,
    )
    target = game.create_object(
        name="Target", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=_make_bear("Target").characteristics,
        card_def=_make_bear("Target"),
    )

    effect_invocations = []

    def tap_effect(target_obj, state):
        effect_invocations.append(target_obj.id)
        return [Event(
            type=EventType.TAP,
            payload={'object_id': target_obj.id},
            source=source.id,
        )]

    choice2 = create_target_creature_choice(
        game.state, p1.id, source.id,
        filter_fn=lambda o, st: o.controller != p1.id,
        effect_fn=tap_effect,
    )

    # Target leaves the battlefield before the choice resolves.
    target.zone = ZoneType.GRAVEYARD
    bf = game.state.zones['battlefield']
    if target.id in bf.objects:
        bf.objects.remove(target.id)
    game.state.zones[f"graveyard_{p2.id}"].objects.append(target.id)

    # Resolving the choice should silently drop the now-invalid target.
    game.submit_choice(choice2.id, p1.id, [target.id])
    assert effect_invocations == [], (
        "effect_fn was called for a target that left the battlefield"
    )
    assert game.state.pending_choice is None


if __name__ == "__main__":
    test_target_creature_choice_returns_none_with_no_valid_targets()
    test_target_creature_choice_opens_pending_choice()
    test_target_creature_choice_callback_emits_effect()
    test_target_creature_choice_handler_skips_invalid_after_choice()
    print("All trigger-target-creature-choice tests passed.")
