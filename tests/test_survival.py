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
# W3: Per-card Survival helper tests (Reluctant Role Model, Veteran Survivor,
# Cynical Loner, Kona Rescue Beastie, Rip Spawn Hunter).
#
# These exercise the four new helpers added in src/cards/interceptor_helpers.py:
#   - make_counter_transfer_on_death
#   - track_exile_with / count_exiled_with
#   - make_hand_to_battlefield_choice
#   - reveal_top_n_with_distinct_filter
# -----------------------------------------------------------------------------


def test_reluctant_role_model_counter_transfer_on_death():
    print("\n=== Test: Reluctant Role Model — counter transfer on death ===")
    from src.cards.duskmourn import RELUCTANT_ROLE_MODEL
    game, p1, p2 = _new_game()
    obj = _create_with_setup(game, RELUCTANT_ROLE_MODEL, p1, tapped=False)
    # Pre-load a +1/+1 counter on the source — simulates a previous Survival fire.
    obj.state.counters['+1/+1'] = 2

    # Add a recipient creature on the battlefield.
    cd = make_creature(name="Recipient", power=2, toughness=2, mana_cost="{2}",
                       colors={Color.GREEN}, subtypes={"Beast"})
    recipient = game.create_object("Recipient", p1, ZoneType.BATTLEFIELD,
                                   cd.characteristics, card_def=cd)

    # Kill Reluctant Role Model.
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': obj.id},
        source='test',
    ))

    # The death-transfer trigger should have opened a target choice on p1.
    choice = game.state.pending_choice
    assert choice is not None, "Expected a target PendingChoice from death-transfer"
    assert choice.choice_type == 'target', f"Expected target choice, got {choice.choice_type}"
    assert recipient.id in choice.options, "Recipient must be a legal target"

    # Pick the recipient.
    ok, msg, _ = game.submit_choice(choice.id, p1, [recipient.id])
    assert ok, f"submit_choice failed: {msg}"

    # Verify the counters moved.
    rec_counters = recipient.state.counters.get('+1/+1', 0)
    print(f"  Recipient +1/+1 counters after transfer: {rec_counters}")
    assert rec_counters == 2, f"Expected 2 +1/+1 on recipient, got {rec_counters}"
    src_counters = obj.state.counters.get('+1/+1', 0)
    print(f"  Source +1/+1 counters after transfer: {src_counters}")
    assert src_counters == 0, "Counters must be removed from the dying creature"
    print("  PASS: Reluctant Role Model transfers counters on death.")


def test_reluctant_role_model_no_trigger_without_counters():
    print("\n=== Test: Reluctant Role Model — no choice when no counters ===")
    from src.cards.duskmourn import RELUCTANT_ROLE_MODEL
    game, p1, p2 = _new_game()
    obj = _create_with_setup(game, RELUCTANT_ROLE_MODEL, p1, tapped=False)
    # No counters on the source.

    # Add a recipient creature.
    cd = make_creature(name="Recipient", power=2, toughness=2, mana_cost="{2}",
                       colors={Color.GREEN}, subtypes={"Beast"})
    game.create_object("Recipient", p1, ZoneType.BATTLEFIELD,
                       cd.characteristics, card_def=cd)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': obj.id},
        source='test',
    ))
    assert game.state.pending_choice is None, (
        "No choice should be opened when the dying creature had no counters."
    )
    print("  PASS: Death without counters opens no choice.")


def test_veteran_survivor_exile_tracking_and_buff():
    print("\n=== Test: Veteran Survivor — exile tracking + +3/+3 hexproof ===")
    from src.cards.duskmourn import VETERAN_SURVIVOR
    game, p1, p2 = _new_game()
    obj = _create_with_setup(game, VETERAN_SURVIVOR, p1, tapped=True)

    # Seed the controller's graveyard with three cards we'll exile one at a time.
    gy_key = f"graveyard_{p1}"
    gy_cards = []
    for i in range(3):
        cd = make_creature(name=f"GY Card {i}", power=1, toughness=1,
                           mana_cost="{1}", colors={Color.WHITE}, subtypes=set())
        c = game.create_object(f"GY Card {i}", p1, ZoneType.GRAVEYARD,
                               cd.characteristics, card_def=cd)
        gy_cards.append(c)

    # Repeat 3 times: tap, fire Survival, choose a graveyard card to exile.
    for i in range(3):
        obj.state.tapped = True
        _emit_postcombat_main(game, p1)
        choice = game.state.pending_choice
        assert choice is not None, f"Expected target choice on iteration {i}"
        # Pick the first remaining graveyard card.
        target = gy_cards[i].id
        assert target in choice.options
        ok, msg, _ = game.submit_choice(choice.id, p1, [target])
        assert ok, f"iteration {i}: {msg}"

    # Now there should be three cards exiled with this creature.
    from src.cards.interceptor_helpers import count_exiled_with
    assert count_exiled_with(game.state, obj.id) == 3, (
        f"count_exiled_with should be 3, got {count_exiled_with(game.state, obj.id)}"
    )

    # Power/toughness queries should reflect +3/+3.
    from src.engine.queries import get_power, get_toughness, has_ability
    final_power = get_power(obj, game.state)
    print(f"  Power query: base={obj.characteristics.power} -> {final_power}")
    assert final_power == obj.characteristics.power + 3, (
        f"Expected +3 power, got {final_power - obj.characteristics.power}"
    )

    final_toughness = get_toughness(obj, game.state)
    print(f"  Toughness query: base={obj.characteristics.toughness} -> {final_toughness}")
    assert final_toughness == obj.characteristics.toughness + 3, (
        f"Expected +3 toughness, got {final_toughness - obj.characteristics.toughness}"
    )

    # Hexproof query.
    has_hex = has_ability(obj, 'hexproof', game.state)
    assert has_hex, "Expected hexproof to be granted"
    print("  PASS: Veteran Survivor +3/+3 + hexproof from 3 exiled cards.")


def test_cynical_loner_search_to_graveyard():
    print("\n=== Test: Cynical Loner — search library, send card to graveyard ===")
    from src.cards.duskmourn import CYNICAL_LONER
    game, p1, p2 = _new_game()
    obj = _create_with_setup(game, CYNICAL_LONER, p1, tapped=True)

    # Seed library with a couple of cards.
    lib_key = f"library_{p1}"
    lib_cards = []
    for i in range(2):
        cd = make_creature(name=f"Lib Card {i}", power=2, toughness=2,
                           mana_cost="{1}", colors={Color.GREEN}, subtypes=set())
        c = game.create_object(f"Lib Card {i}", p1, ZoneType.LIBRARY,
                               cd.characteristics, card_def=cd)
        lib_cards.append(c)

    _emit_postcombat_main(game, p1)
    choice = game.state.pending_choice
    assert choice is not None, "Expected a library_search PendingChoice"
    assert choice.choice_type == 'library_search'
    # All seeded cards should be eligible.
    for c in lib_cards:
        assert c.id in choice.options, f"Card {c.id} should be eligible"

    # Pick the first library card.
    pick = lib_cards[0].id
    ok, msg, _ = game.submit_choice(choice.id, p1, [pick])
    assert ok, f"submit_choice failed: {msg}"

    # Verify it's in graveyard.
    gy = game.state.zones.get(f"graveyard_{p1}")
    assert pick in gy.objects, "Picked card should be in graveyard"
    print(f"  Library search routed card to graveyard: {pick}")
    print("  PASS: Cynical Loner sends searched card to graveyard.")


def test_kona_hand_to_battlefield_permanent_choice():
    print("\n=== Test: Kona, Rescue Beastie — hand-to-battlefield permanent choice ===")
    from src.cards.duskmourn import KONA_RESCUE_BEASTIE
    game, p1, p2 = _new_game()
    obj = _create_with_setup(game, KONA_RESCUE_BEASTIE, p1, tapped=True)

    # Seed hand with: one creature (permanent), one instant (not permanent).
    perm_cd = make_creature(name="Hand Creature", power=2, toughness=2,
                            mana_cost="{2}", colors={Color.GREEN}, subtypes={"Beast"})
    perm = game.create_object("Hand Creature", p1, ZoneType.HAND,
                              perm_cd.characteristics, card_def=perm_cd)

    # Build an instant manually since make_instant is in card_factories.
    from src.cards.card_factories import make_instant
    instant_cd = make_instant(name="Hand Instant", mana_cost="{1}",
                              colors={Color.RED}, text="Deal 3 damage.")
    inst = game.create_object("Hand Instant", p1, ZoneType.HAND,
                              instant_cd.characteristics, card_def=instant_cd)

    _emit_postcombat_main(game, p1)
    choice = game.state.pending_choice
    assert choice is not None, "Expected a hand_to_battlefield PendingChoice"
    assert choice.choice_type == 'hand_to_battlefield'
    # Permanent should be in options; instant should NOT.
    assert perm.id in choice.options, "Creature must be eligible"
    assert inst.id not in choice.options, "Instant must NOT be eligible"
    print(f"  Eligible options: {len(choice.options)} (creature only)")

    # Pick the creature.
    ok, msg, _ = game.submit_choice(choice.id, p1, [perm.id])
    assert ok, f"submit_choice failed: {msg}"

    # Verify the creature moved to battlefield.
    moved = game.state.objects.get(perm.id)
    assert moved.zone == ZoneType.BATTLEFIELD, (
        f"Hand creature should be on the battlefield, got {moved.zone}"
    )
    print("  PASS: Kona moves a permanent card from hand to battlefield.")


def test_kona_optional_no_permanent_in_hand():
    print("\n=== Test: Kona — no permanent cards in hand opens no choice ===")
    from src.cards.duskmourn import KONA_RESCUE_BEASTIE
    game, p1, p2 = _new_game()
    obj = _create_with_setup(game, KONA_RESCUE_BEASTIE, p1, tapped=True)

    # Hand contains only an instant (no permanents).
    from src.cards.card_factories import make_instant
    instant_cd = make_instant(name="Hand Instant", mana_cost="{1}",
                              colors={Color.RED}, text="Deal 3 damage.")
    game.create_object("Hand Instant", p1, ZoneType.HAND,
                       instant_cd.characteristics, card_def=instant_cd)

    _emit_postcombat_main(game, p1)
    assert game.state.pending_choice is None, (
        "Optional choice over an empty filter should not open a PendingChoice."
    )
    print("  PASS: Kona declines silently when no permanent is available.")


def test_rip_spawn_hunter_distinct_power_reveal():
    print("\n=== Test: Rip, Spawn Hunter — distinct-power reveal-to-hand ===")
    from src.cards.duskmourn import RIP_SPAWN_HUNTER
    game, p1, p2 = _new_game()
    obj = _create_with_setup(game, RIP_SPAWN_HUNTER, p1, tapped=True)

    # Seed library top with 4 cards (in this order — top of library = index 0):
    #   bear/2 (creature, power 2)
    #   elf/1  (creature, power 1)
    #   dragon/4 (creature, power 4)
    #   goblin/1 (creature, power 1) — dup power
    # Rip's power is 4, so all 4 are revealed.
    lib_seed = [
        ("Bear", 2, {"Bear"}),
        ("Elf", 1, {"Elf"}),
        ("Dragon", 4, {"Dragon"}),
        ("Goblin", 1, {"Goblin"}),
    ]
    seeded = []
    for name, pwr, subs in lib_seed:
        cd = make_creature(name=name, power=pwr, toughness=pwr,
                           mana_cost="{1}", colors={Color.GREEN}, subtypes=subs)
        c = game.create_object(name, p1, ZoneType.LIBRARY,
                               cd.characteristics, card_def=cd)
        seeded.append(c)
    # Ensure they are at the very top (push to front).
    lib = game.state.zones.get(f"library_{p1}")
    # Remove from wherever they got appended and put on top in order.
    for c in seeded:
        if c.id in lib.objects:
            lib.objects.remove(c.id)
    # Push front so order: Bear, Elf, Dragon, Goblin (top -> down).
    for c in reversed(seeded):
        lib.objects.insert(0, c.id)

    _emit_postcombat_main(game, p1)
    choice = game.state.pending_choice
    assert choice is not None, "Expected a reveal_distinct PendingChoice"
    assert choice.choice_type == 'reveal_distinct'
    # All 4 are creatures so all eligible.
    assert len(choice.options) == 4, f"Expected 4 eligible, got {len(choice.options)}"

    # Pick a valid distinct-power set: Bear (2), Dragon (4), Elf (1).
    bear_id = seeded[0].id
    elf_id = seeded[1].id
    dragon_id = seeded[2].id
    goblin_id = seeded[3].id
    ok, msg, _ = game.submit_choice(choice.id, p1, [bear_id, dragon_id, elf_id])
    assert ok, f"submit_choice failed: {msg}"

    hand = game.state.zones.get(f"hand_{p1}")
    for cid, cname in [(bear_id, "Bear"), (dragon_id, "Dragon"), (elf_id, "Elf")]:
        assert cid in hand.objects, f"{cname} should be in hand"
    # Goblin was not selected; should be on the bottom of the library.
    assert goblin_id in lib.objects, "Goblin should be back in library"
    # Re-fetch lib.objects since the bottom_random put it somewhere.
    print(f"  Hand size after reveal: {len(hand.objects)}")
    print("  PASS: Rip puts distinct-power creatures into hand.")


def test_rip_distinct_constraint_filters_duplicates():
    print("\n=== Test: Rip — duplicate-power picks are silently dropped ===")
    from src.cards.duskmourn import RIP_SPAWN_HUNTER
    game, p1, p2 = _new_game()
    obj = _create_with_setup(game, RIP_SPAWN_HUNTER, p1, tapped=True)

    # Seed 2 cards with the same power.
    same_seed = []
    for i in range(2):
        cd = make_creature(name=f"Twin {i}", power=2, toughness=2,
                           mana_cost="{1}", colors={Color.GREEN}, subtypes={"Beast"})
        c = game.create_object(f"Twin {i}", p1, ZoneType.LIBRARY,
                               cd.characteristics, card_def=cd)
        same_seed.append(c)
    lib = game.state.zones.get(f"library_{p1}")
    for c in same_seed:
        if c.id in lib.objects:
            lib.objects.remove(c.id)
    for c in reversed(same_seed):
        lib.objects.insert(0, c.id)

    _emit_postcombat_main(game, p1)
    choice = game.state.pending_choice
    assert choice is not None
    assert len(choice.options) >= 1

    # Try to pick BOTH twins — only the first should land in hand (distinct-power).
    twin_a = same_seed[0].id
    twin_b = same_seed[1].id
    ok, msg, _ = game.submit_choice(choice.id, p1, [twin_a, twin_b])
    assert ok, f"submit_choice failed: {msg}"

    hand = game.state.zones.get(f"hand_{p1}")
    twins_in_hand = [c for c in [twin_a, twin_b] if c in hand.objects]
    print(f"  Twins in hand: {len(twins_in_hand)} (expected 1)")
    assert len(twins_in_hand) == 1, (
        "Distinct-power constraint should accept only one of the twins"
    )
    print("  PASS: Rip enforces distinct-power constraint.")


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
    # W3 — per-card helper integration tests
    test_reluctant_role_model_counter_transfer_on_death()
    test_reluctant_role_model_no_trigger_without_counters()
    test_veteran_survivor_exile_tracking_and_buff()
    test_cynical_loner_search_to_graveyard()
    test_kona_hand_to_battlefield_permanent_choice()
    test_kona_optional_no_permanent_in_hand()
    test_rip_spawn_hunter_distinct_power_reveal()
    test_rip_distinct_constraint_filters_duplicates()
    print("\n" + "=" * 60)
    print("ALL SURVIVAL TESTS PASSED!")
    print("=" * 60)
