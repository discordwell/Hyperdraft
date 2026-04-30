"""
OTJ Crime mechanic regression tests.

Covers a previously-broken `make_crime_committed_trigger` in
`src/cards/interceptor_helpers.py`: the function fell through to dead code
referencing undefined names (``saga_id``/``controller_id``/etc.) instead of
returning an Interceptor. Every crime-trigger card on the battlefield raised
a NameError at setup time. This file pins the fix and verifies that crime
triggers emit their reaction events end-to-end.
"""

import sys
import os

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Characteristics, ObjectState,
    Interceptor,
    make_creature,
)
from src.engine.crime import detect_crime, is_crime_committed
from src.cards.interceptor_helpers import make_crime_committed_trigger
from src.cards.outlaws_thunder_junction import (
    OUTLAWS_THUNDER_JUNCTION_CARDS,
    blood_hustler_setup,
    lazav_familiar_stranger_setup,
    bandits_haul_setup,
    kaervek_the_punisher_setup,
)


def _setup_game():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.state.active_player = p1.id
    game.state.turn_number = 1
    return game, p1, p2


def _put_on_battlefield(game, player, card_def):
    """Create the card in HAND, then emit a HAND -> BATTLEFIELD ZONE_CHANGE
    so setup_interceptors fires through the normal pipeline."""
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None,
    )
    obj.card_def = card_def
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    return obj


# =============================================================================
# Direct API: make_crime_committed_trigger returns an Interceptor
# =============================================================================

def test_make_crime_committed_trigger_returns_interceptor():
    print("\n=== Test: make_crime_committed_trigger returns an Interceptor ===")
    game, p1, _ = _setup_game()
    card_def = make_creature(
        name="Crime Sentinel", power=1, toughness=1,
        mana_cost="{B}", colors={Color.BLACK},
    )
    obj = _put_on_battlefield(game, p1, card_def)

    interceptor = make_crime_committed_trigger(
        obj,
        effect_fn=lambda e, s: [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': p1.id, 'amount': 1},
            source=obj.id,
        )],
    )
    assert isinstance(interceptor, Interceptor), (
        f"Expected Interceptor, got {type(interceptor).__name__}"
    )
    assert interceptor.source == obj.id
    assert interceptor.controller == p1.id
    print("OK")


# =============================================================================
# Existing OTJ setup functions no longer raise NameError
# =============================================================================

def test_blood_hustler_setup_runs_without_error():
    print("\n=== Test: blood_hustler_setup runs without error ===")
    game, p1, _ = _setup_game()
    card_def = OUTLAWS_THUNDER_JUNCTION_CARDS["Blood Hustler"]
    obj = _put_on_battlefield(game, p1, card_def)
    interceptors = blood_hustler_setup(obj, game.state)
    assert len(interceptors) == 1, f"Expected 1 interceptor, got {len(interceptors)}"
    assert isinstance(interceptors[0], Interceptor)
    print("OK")


def test_lazav_setup_runs_without_error():
    print("\n=== Test: lazav_familiar_stranger_setup runs without error ===")
    game, p1, _ = _setup_game()
    card_def = OUTLAWS_THUNDER_JUNCTION_CARDS["Lazav, Familiar Stranger"]
    obj = _put_on_battlefield(game, p1, card_def)
    interceptors = lazav_familiar_stranger_setup(obj, game.state)
    assert len(interceptors) == 1
    assert isinstance(interceptors[0], Interceptor)
    print("OK")


def test_bandits_haul_setup_runs_without_error():
    print("\n=== Test: bandits_haul_setup runs without error ===")
    game, p1, _ = _setup_game()
    card_def = OUTLAWS_THUNDER_JUNCTION_CARDS["Bandit's Haul"]
    obj = _put_on_battlefield(game, p1, card_def)
    interceptors = bandits_haul_setup(obj, game.state)
    assert len(interceptors) == 1
    assert isinstance(interceptors[0], Interceptor)
    print("OK")


def test_kaervek_setup_runs_without_error():
    print("\n=== Test: kaervek_the_punisher_setup runs without error ===")
    game, p1, _ = _setup_game()
    card_def = OUTLAWS_THUNDER_JUNCTION_CARDS["Kaervek, the Punisher"]
    obj = _put_on_battlefield(game, p1, card_def)
    interceptors = kaervek_the_punisher_setup(obj, game.state)
    assert len(interceptors) == 1
    assert isinstance(interceptors[0], Interceptor)
    print("OK")


# =============================================================================
# End-to-end: crime trigger fires its effect on CRIME_COMMITTED
# =============================================================================

def test_blood_hustler_crime_trigger_emits_counter():
    print("\n=== Test: Blood Hustler emits +1/+1 counter when controller commits a crime ===")
    game, p1, p2 = _setup_game()
    card_def = OUTLAWS_THUNDER_JUNCTION_CARDS["Blood Hustler"]
    hustler = _put_on_battlefield(game, p1, card_def)

    counters_before = (hustler.state.counters or {}).get('+1/+1', 0)

    # Simulate p1 committing a crime by targeting p2.
    crime_events = detect_crime(p1.id, [p2.id], game.state, source_id=hustler.id)
    assert crime_events, "Expected a CRIME_COMMITTED event"
    for ev in crime_events:
        game.emit(ev)

    counters_after = (hustler.state.counters or {}).get('+1/+1', 0)
    assert counters_after > counters_before, (
        f"Expected +1/+1 counter on Blood Hustler after crime; before={counters_before} after={counters_after}"
    )
    print(f"+1/+1 counters before: {counters_before}, after: {counters_after}")
    print("OK")


def test_lazav_crime_trigger_emits_counter_once_per_turn():
    print("\n=== Test: Lazav crime trigger fires only once per turn ===")
    game, p1, p2 = _setup_game()
    card_def = OUTLAWS_THUNDER_JUNCTION_CARDS["Lazav, Familiar Stranger"]
    lazav = _put_on_battlefield(game, p1, card_def)

    # First crime
    for ev in detect_crime(p1.id, [p2.id], game.state, source_id=lazav.id):
        game.emit(ev)
    after_first = (lazav.state.counters or {}).get('+1/+1', 0)

    # Second crime same turn — once_per_turn gate must suppress the trigger.
    for ev in detect_crime(p1.id, [p2.id], game.state, source_id=lazav.id):
        game.emit(ev)
    after_second = (lazav.state.counters or {}).get('+1/+1', 0)

    assert after_first >= 1, f"First crime should add 1 +1/+1 counter; got {after_first}"
    assert after_second == after_first, (
        f"Second crime same turn must NOT add another counter; first={after_first} second={after_second}"
    )
    print(f"After first crime: {after_first}, after second crime: {after_second}")
    print("OK")


def test_crime_state_updates():
    print("\n=== Test: detect_crime increments turn_data crime counter ===")
    game, p1, p2 = _setup_game()
    assert not is_crime_committed(p1.id, game.state)
    detect_crime(p1.id, [p2.id], game.state, source_id="src")
    assert is_crime_committed(p1.id, game.state), "Expected crime flag to flip after detect_crime"
    print("OK")


# =============================================================================
# Run
# =============================================================================

if __name__ == "__main__":
    test_make_crime_committed_trigger_returns_interceptor()
    test_blood_hustler_setup_runs_without_error()
    test_lazav_setup_runs_without_error()
    test_bandits_haul_setup_runs_without_error()
    test_kaervek_setup_runs_without_error()
    test_blood_hustler_crime_trigger_emits_counter()
    test_lazav_crime_trigger_emits_counter_once_per_turn()
    test_crime_state_updates()
    print("\nAll OTJ crime trigger tests passed!")
