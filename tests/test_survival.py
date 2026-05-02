"""
Survival Mechanic Tests (Duskmourn / DSK)

Survival is a triggered ability:
  "At the beginning of your second main phase, if this creature is tapped, X."

Implementation under test:
- Engine: ``src/engine/turn.py`` ``_emit_step_start`` distinguishes the
  precombat / postcombat main-phase entries via ``payload['phase']``.
- Helper: ``src/cards/interceptor_helpers.make_survival_trigger``.
- Cards (DSK): Cautious Survivor, Acrobatic Cheerleader, Defiant Survivor,
  Glimmer Seeker, Shrewd Storyteller, Savior of the Small, House Cartographer.

Test surface:
1. Trigger fires when its source is tapped at the start of second main.
2. Does NOT fire when the source is untapped.
3. Does NOT fire on the opponent's second main.
4. Fires once per second-main per turn (does not double-fire on the same event).
5. Specific cards emit the expected event payload.
"""

import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    make_creature,
)
from src.cards.interceptor_helpers import make_survival_trigger


def _new_game(p1_name="Alice", p2_name="Bob"):
    """Returns (game, p1_id, p2_id) with p1 as the active player."""
    game = Game()
    p1 = game.add_player(p1_name)
    p2 = game.add_player(p2_name)
    game.state.active_player = p1.id
    return game, p1.id, p2.id


def _emit_postcombat_main(game, active_player):
    """Emit the engine's PHASE_START event for the second (postcombat) main."""
    game.state.active_player = active_player
    return game.emit(Event(
        type=EventType.PHASE_START,
        payload={
            'phase': 'postcombat_main',
            'step': 'main',
            'active_player': active_player,
            'turn_number': game.state.turn_number,
        },
    ))


def _emit_precombat_main(game, active_player):
    """Emit the engine's PHASE_START event for the first (precombat) main."""
    game.state.active_player = active_player
    return game.emit(Event(
        type=EventType.PHASE_START,
        payload={
            'phase': 'precombat_main',
            'step': 'main',
            'active_player': active_player,
            'turn_number': game.state.turn_number,
        },
    ))


# -----------------------------------------------------------------------------
# Helper-level tests
# -----------------------------------------------------------------------------

def test_survival_fires_when_tapped_at_second_main():
    print("\n=== Test: Survival fires on second main when tapped ===")
    game, p1, p2 = _new_game()
    cd = make_creature(name="Survivor",
                       power=2, toughness=2,
                       mana_cost="{1}{G}",
                       colors={Color.GREEN}, subtypes={"Survivor"})
    obj = game.create_object("Survivor", p1, ZoneType.BATTLEFIELD,
                             cd.characteristics, card_def=cd)
    obj.state.tapped = True

    fire_count = [0]
    def effect_fn(event, state):
        fire_count[0] += 1
        return []

    game.register_interceptor(make_survival_trigger(obj, effect_fn), obj)

    _emit_postcombat_main(game, p1)
    print(f"  Fire count: {fire_count[0]}")
    assert fire_count[0] == 1, f"Expected 1 fire, got {fire_count[0]}"
    print("  PASS: Survival fires when tapped at second main.")


def test_survival_does_not_fire_when_untapped():
    print("\n=== Test: Survival does NOT fire when untapped ===")
    game, p1, p2 = _new_game()
    cd = make_creature(name="Survivor",
                       power=2, toughness=2,
                       mana_cost="{1}{G}",
                       colors={Color.GREEN}, subtypes={"Survivor"})
    obj = game.create_object("Survivor", p1, ZoneType.BATTLEFIELD,
                             cd.characteristics, card_def=cd)
    obj.state.tapped = False  # explicitly untapped

    fire_count = [0]
    def effect_fn(event, state):
        fire_count[0] += 1
        return []

    game.register_interceptor(make_survival_trigger(obj, effect_fn), obj)

    _emit_postcombat_main(game, p1)
    print(f"  Fire count (untapped): {fire_count[0]}")
    assert fire_count[0] == 0, "Should not fire when untapped"
    print("  PASS: Survival skipped when untapped.")


def test_survival_does_not_fire_on_opponent_second_main():
    print("\n=== Test: Survival does NOT fire on opponent's second main ===")
    game, p1, p2 = _new_game()
    cd = make_creature(name="Survivor",
                       power=2, toughness=2,
                       mana_cost="{1}{G}",
                       colors={Color.GREEN}, subtypes={"Survivor"})
    obj = game.create_object("Survivor", p1, ZoneType.BATTLEFIELD,
                             cd.characteristics, card_def=cd)
    obj.state.tapped = True  # tapped, but it's not p1's turn

    fire_count = [0]
    def effect_fn(event, state):
        fire_count[0] += 1
        return []

    game.register_interceptor(make_survival_trigger(obj, effect_fn), obj)

    # p2 is the active player at second main
    _emit_postcombat_main(game, p2)
    print(f"  Fire count (opponent's main): {fire_count[0]}")
    assert fire_count[0] == 0, "Should not fire on opponent's second main"
    print("  PASS: Survival ignores opponent's second main.")


def test_survival_does_not_fire_on_first_main():
    print("\n=== Test: Survival does NOT fire on first main phase ===")
    game, p1, p2 = _new_game()
    cd = make_creature(name="Survivor",
                       power=2, toughness=2,
                       mana_cost="{1}{G}",
                       colors={Color.GREEN}, subtypes={"Survivor"})
    obj = game.create_object("Survivor", p1, ZoneType.BATTLEFIELD,
                             cd.characteristics, card_def=cd)
    obj.state.tapped = True

    fire_count = [0]
    def effect_fn(event, state):
        fire_count[0] += 1
        return []

    game.register_interceptor(make_survival_trigger(obj, effect_fn), obj)

    _emit_precombat_main(game, p1)
    print(f"  Fire count (first main): {fire_count[0]}")
    assert fire_count[0] == 0, "Should not fire on first main"
    print("  PASS: Survival skipped on first main.")


def test_survival_fires_exactly_once_per_second_main():
    print("\n=== Test: Survival fires once per second-main event ===")
    game, p1, p2 = _new_game()
    cd = make_creature(name="Survivor",
                       power=2, toughness=2,
                       mana_cost="{1}{G}",
                       colors={Color.GREEN}, subtypes={"Survivor"})
    obj = game.create_object("Survivor", p1, ZoneType.BATTLEFIELD,
                             cd.characteristics, card_def=cd)
    obj.state.tapped = True

    fire_count = [0]
    def effect_fn(event, state):
        fire_count[0] += 1
        return []

    game.register_interceptor(make_survival_trigger(obj, effect_fn), obj)

    # Each second-main entry is one trigger. Survival re-triggers each turn,
    # but a single PHASE_START only fires the trigger once.
    _emit_postcombat_main(game, p1)
    assert fire_count[0] == 1, f"Expected 1 fire after first second-main, got {fire_count[0]}"

    # Simulate a second turn cycle: p2's turn comes and goes (no fire),
    # then p1's second main again fires once.
    _emit_postcombat_main(game, p2)  # opp turn
    _emit_postcombat_main(game, p1)  # p1's next second main
    print(f"  Fire count after 2 own-second-mains + 1 opp: {fire_count[0]}")
    assert fire_count[0] == 2, f"Expected 2 fires, got {fire_count[0]}"
    print("  PASS: Survival fires once per own second main, not on opponent's.")


def test_survival_does_not_fire_off_battlefield():
    print("\n=== Test: Survival does NOT fire when source left battlefield ===")
    game, p1, p2 = _new_game()
    cd = make_creature(name="Survivor",
                       power=2, toughness=2,
                       mana_cost="{1}{G}",
                       colors={Color.GREEN}, subtypes={"Survivor"})
    obj = game.create_object("Survivor", p1, ZoneType.BATTLEFIELD,
                             cd.characteristics, card_def=cd)
    obj.state.tapped = True

    fire_count = [0]
    def effect_fn(event, state):
        fire_count[0] += 1
        return []

    game.register_interceptor(make_survival_trigger(obj, effect_fn), obj)

    # Move the creature to graveyard before phase fires.
    obj.zone = ZoneType.GRAVEYARD
    _emit_postcombat_main(game, p1)
    print(f"  Fire count (off battlefield): {fire_count[0]}")
    assert fire_count[0] == 0
    print("  PASS: Survival is zone-gated.")


# -----------------------------------------------------------------------------
# Card-level integration tests
# -----------------------------------------------------------------------------

def _create_with_setup(game, card_def, controller, tapped=False):
    """Create a battlefield object. ``Game.create_object`` already runs
    ``setup_interceptors`` for the BATTLEFIELD zone, so we don't re-run it
    here (running twice would double-register the trigger)."""
    obj = game.create_object(card_def.name, controller, ZoneType.BATTLEFIELD,
                             card_def.characteristics, card_def=card_def)
    obj.state.tapped = tapped
    return obj


def test_cautious_survivor_gains_2_life_when_tapped_at_second_main():
    print("\n=== Test: Cautious Survivor gains 2 life ===")
    from src.cards.duskmourn import CAUTIOUS_SURVIVOR
    game, p1, p2 = _new_game()
    obj = _create_with_setup(game, CAUTIOUS_SURVIVOR, p1, tapped=True)

    life_before = game.state.players[p1].life
    _emit_postcombat_main(game, p1)
    life_after = game.state.players[p1].life
    print(f"  Life: {life_before} -> {life_after}")
    assert life_after == life_before + 2, (
        f"Expected +2 life, got {life_after - life_before}"
    )
    print("  PASS: Cautious Survivor gains 2 life on second main when tapped.")


def test_cautious_survivor_no_life_when_untapped():
    print("\n=== Test: Cautious Survivor untapped -> no effect ===")
    from src.cards.duskmourn import CAUTIOUS_SURVIVOR
    game, p1, p2 = _new_game()
    _create_with_setup(game, CAUTIOUS_SURVIVOR, p1, tapped=False)

    life_before = game.state.players[p1].life
    _emit_postcombat_main(game, p1)
    life_after = game.state.players[p1].life
    print(f"  Life: {life_before} -> {life_after}")
    assert life_after == life_before
    print("  PASS: Cautious Survivor stays silent when untapped.")


def test_acrobatic_cheerleader_only_fires_once():
    print("\n=== Test: Acrobatic Cheerleader once-only Survival ===")
    from src.cards.duskmourn import ACROBATIC_CHEERLEADER
    game, p1, p2 = _new_game()
    obj = _create_with_setup(game, ACROBATIC_CHEERLEADER, p1, tapped=True)

    counter_count = [0]

    def counter_listener_filter(event, state):
        return (event.type == EventType.COUNTER_ADDED
                and event.payload.get('object_id') == obj.id
                and event.payload.get('counter_type') == 'flying')

    # Hook into game events by listening on all emits via a sentinel intercept.
    # Simpler: emit phase, then count flying counter events in the event_log.
    _emit_postcombat_main(game, p1)
    counter_count[0] = sum(
        1 for e in game.state.event_log
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == obj.id
        and e.payload.get('counter_type') == 'flying'
    )
    print(f"  Flying counters added on first second-main: {counter_count[0]}")
    assert counter_count[0] >= 1, "Should have added at least one flying counter"

    # Reset the source to tapped (counter was added but flag still set) and
    # fire the second main again — should NOT add another counter.
    first_count = counter_count[0]
    obj.state.tapped = True
    _emit_postcombat_main(game, p1)
    counter_count[0] = sum(
        1 for e in game.state.event_log
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == obj.id
        and e.payload.get('counter_type') == 'flying'
    )
    print(f"  Flying counters after second second-main: {counter_count[0]}")
    assert counter_count[0] == first_count, (
        f"Should not double-fire (got {counter_count[0]}, expected {first_count})"
    )
    print("  PASS: Acrobatic Cheerleader is one-shot.")


def test_defiant_survivor_emits_manifest_dread():
    print("\n=== Test: Defiant Survivor emits MANIFEST_DREAD ===")
    from src.cards.duskmourn import DEFIANT_SURVIVOR
    game, p1, p2 = _new_game()
    obj = _create_with_setup(game, DEFIANT_SURVIVOR, p1, tapped=True)

    pre = len([e for e in game.state.event_log
               if e.type == EventType.MANIFEST_DREAD])
    _emit_postcombat_main(game, p1)
    post = len([e for e in game.state.event_log
                if e.type == EventType.MANIFEST_DREAD])
    print(f"  MANIFEST_DREAD events: {pre} -> {post}")
    assert post > pre, "Should have emitted MANIFEST_DREAD on second main"
    print("  PASS: Defiant Survivor manifests dread on tapped second main.")


def test_glimmer_seeker_creates_token_when_no_glimmer():
    print("\n=== Test: Glimmer Seeker token branch ===")
    from src.cards.duskmourn import GLIMMER_SEEKER
    game, p1, p2 = _new_game()
    obj = _create_with_setup(game, GLIMMER_SEEKER, p1, tapped=True)

    pre_tokens = len([e for e in game.state.event_log
                      if e.type == EventType.OBJECT_CREATED
                      and e.payload.get('name') == 'Glimmer'])
    _emit_postcombat_main(game, p1)
    post_tokens = len([e for e in game.state.event_log
                       if e.type == EventType.OBJECT_CREATED
                       and e.payload.get('name') == 'Glimmer'])
    print(f"  Glimmer OBJECT_CREATED events: {pre_tokens} -> {post_tokens}")
    assert post_tokens > pre_tokens, (
        "With no Glimmer creature in play, should create a Glimmer token"
    )
    print("  PASS: Glimmer Seeker creates token when no Glimmer is in play.")


def test_shrewd_storyteller_adds_plus1_counter_to_self():
    print("\n=== Test: Shrewd Storyteller +1/+1 self-counter ===")
    from src.cards.duskmourn import SHREWD_STORYTELLER
    game, p1, p2 = _new_game()
    obj = _create_with_setup(game, SHREWD_STORYTELLER, p1, tapped=True)

    _emit_postcombat_main(game, p1)
    counter_events = [
        e for e in game.state.event_log
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == obj.id
        and e.payload.get('counter_type') == '+1/+1'
    ]
    print(f"  +1/+1 counter events on Shrewd Storyteller: {len(counter_events)}")
    assert counter_events, "Expected at least one +1/+1 counter event"
    print("  PASS: Shrewd Storyteller emits +1/+1 self-counter.")


def test_savior_of_the_small_returns_creature_from_graveyard():
    print("\n=== Test: Savior of the Small RETURN_TO_HAND_FROM_GRAVEYARD ===")
    from src.cards.duskmourn import SAVIOR_OF_THE_SMALL
    game, p1, p2 = _new_game()
    obj = _create_with_setup(game, SAVIOR_OF_THE_SMALL, p1, tapped=True)

    _emit_postcombat_main(game, p1)
    return_events = [
        e for e in game.state.event_log
        if e.type == EventType.RETURN_TO_HAND_FROM_GRAVEYARD
        and e.payload.get('player') == p1
        and e.payload.get('max_mv') == 3
    ]
    print(f"  RETURN_TO_HAND_FROM_GRAVEYARD events: {len(return_events)}")
    assert return_events, "Expected a return-from-GY event"
    print("  PASS: Savior of the Small queues GY return.")


def test_house_cartographer_emits_reveal_until_land():
    print("\n=== Test: House Cartographer emits REVEAL_UNTIL_LAND ===")
    from src.cards.duskmourn import HOUSE_CARTOGRAPHER
    game, p1, p2 = _new_game()
    obj = _create_with_setup(game, HOUSE_CARTOGRAPHER, p1, tapped=True)

    _emit_postcombat_main(game, p1)
    reveal_events = [
        e for e in game.state.event_log
        if e.type == EventType.REVEAL_UNTIL_LAND
        and e.payload.get('player') == p1
    ]
    print(f"  REVEAL_UNTIL_LAND events: {len(reveal_events)}")
    assert reveal_events, "Expected REVEAL_UNTIL_LAND event"
    print("  PASS: House Cartographer reveals until land.")


def test_cautious_survivor_no_fire_on_opponent_second_main():
    print("\n=== Test: Cautious Survivor ignores opponent's second main ===")
    from src.cards.duskmourn import CAUTIOUS_SURVIVOR
    game, p1, p2 = _new_game()
    _create_with_setup(game, CAUTIOUS_SURVIVOR, p1, tapped=True)

    life_before = game.state.players[p1].life
    _emit_postcombat_main(game, p2)  # opponent's second main
    life_after = game.state.players[p1].life
    print(f"  p1 life on p2's second main: {life_before} -> {life_after}")
    assert life_after == life_before, (
        "Should NOT gain life on opponent's second main"
    )
    print("  PASS: Cautious Survivor controller-gated.")


# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    test_survival_fires_when_tapped_at_second_main()
    test_survival_does_not_fire_when_untapped()
    test_survival_does_not_fire_on_opponent_second_main()
    test_survival_does_not_fire_on_first_main()
    test_survival_fires_exactly_once_per_second_main()
    test_survival_does_not_fire_off_battlefield()
    test_cautious_survivor_gains_2_life_when_tapped_at_second_main()
    test_cautious_survivor_no_life_when_untapped()
    test_acrobatic_cheerleader_only_fires_once()
    test_defiant_survivor_emits_manifest_dread()
    test_glimmer_seeker_creates_token_when_no_glimmer()
    test_shrewd_storyteller_adds_plus1_counter_to_self()
    test_savior_of_the_small_returns_creature_from_graveyard()
    test_house_cartographer_emits_reveal_until_land()
    test_cautious_survivor_no_fire_on_opponent_second_main()
    print("\n" + "=" * 60)
    print("ALL SURVIVAL TESTS PASSED!")
    print("=" * 60)
