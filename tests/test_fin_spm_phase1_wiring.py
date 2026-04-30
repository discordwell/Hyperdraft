"""
Phase 1 wiring sweep tests for Final Fantasy (FIN) and Marvels Spider-Man (SPM).

Validates the noop-cleanup wirings from:
- .phase1_briefings/final_fantasy.json
- .phase1_briefings/spider_man.json

FIN crystals (life-gain doubler / counter doubler / mill-plus-4 / dies-to-exile)
and SPM equipment statics (Web-Shooters, Spider-Suit) are exercised here. Other
briefing rows are activated abilities that remain engine gaps.
"""

import os
import sys

_THIS = os.path.abspath(__file__)
_ROOT = os.path.dirname(os.path.dirname(_THIS))
sys.path.insert(0, _ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, Characteristics,
)
from src.cards.final_fantasy import (
    THE_WIND_CRYSTAL, THE_WATER_CRYSTAL,
    THE_DARKNESS_CRYSTAL, THE_EARTH_CRYSTAL,
)
from src.cards.spider_man import WEBSHOOTERS, SPIDERSUIT


def _make_game(num_players: int = 1):
    game = Game()
    players = [game.add_player(f"P{i}") for i in range(num_players)]
    return game, players


def test_wind_crystal_doubles_life_gain():
    """The Wind Crystal doubles its controller's life gain."""
    print("\n=== Test: The Wind Crystal doubles life gain ===")
    game, (p,) = _make_game(1)
    p.life = 20

    crystal = game.create_object(
        name="The Wind Crystal",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=THE_WIND_CRYSTAL.characteristics,
        card_def=THE_WIND_CRYSTAL,
    )
    assert crystal.interceptor_ids, "Wind Crystal should register interceptors"

    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p.id, 'amount': 3},
    ))
    assert p.life == 26, f"Expected 26 (20+3*2), got {p.life}"

    # Life loss should be untouched.
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p.id, 'amount': -2},
    ))
    assert p.life == 24, f"Expected 24, got {p.life}"
    print("PASS: Wind Crystal doubles life gain only")


def test_water_crystal_adds_four_to_opponent_mill():
    """The Water Crystal makes opponents mill that many cards plus 4."""
    print("\n=== Test: The Water Crystal adds 4 to opponent mill ===")
    game, (p, opp) = _make_game(2)

    crystal = game.create_object(
        name="The Water Crystal",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=THE_WATER_CRYSTAL.characteristics,
        card_def=THE_WATER_CRYSTAL,
    )
    assert crystal.interceptor_ids, "Water Crystal should register interceptors"

    interceptor_id = next(iter(crystal.interceptor_ids))
    interceptor = game.state.interceptors.get(interceptor_id)
    assert interceptor is not None, "Replacement interceptor should be in registry"

    # Opponent mill 1 -> opponent mill 5.
    opp_mill = Event(
        type=EventType.MILL,
        payload={'player': opp.id, 'amount': 1},
    )
    assert interceptor.filter(opp_mill, game.state)
    res = interceptor.handler(opp_mill, game.state)
    assert res.transformed_event is not None
    assert res.transformed_event.payload['amount'] == 5, (
        f"Expected 5 (1+4), got {res.transformed_event.payload['amount']}"
    )

    # Self mill is untouched.
    self_mill = Event(
        type=EventType.MILL,
        payload={'player': p.id, 'amount': 1},
    )
    assert not interceptor.filter(self_mill, game.state), (
        "Replacement should not fire on controller's mill"
    )
    print("PASS: Water Crystal adds 4 to opponent mill, leaves controller alone")


def test_darkness_crystal_redirects_opponent_creature_death():
    """The Darkness Crystal exiles opponent's nontoken creatures instead of destroy."""
    print("\n=== Test: The Darkness Crystal redirects opp creature death to exile ===")
    game, (p, opp) = _make_game(2)

    crystal = game.create_object(
        name="The Darkness Crystal",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=THE_DARKNESS_CRYSTAL.characteristics,
        card_def=THE_DARKNESS_CRYSTAL,
    )
    assert crystal.interceptor_ids, "Darkness Crystal should register interceptors"

    # Place an opponent creature that should be redirected on destroy.
    victim = game.create_object(
        name="OppGoblin",
        owner_id=opp.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, power=1, toughness=1,
        ),
    )

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': victim.id},
    ))
    assert victim.zone == ZoneType.EXILE, (
        f"Opp creature should be exiled, ended up in {victim.zone}"
    )
    print("PASS: Darkness Crystal exiles opponent creatures on death")


def test_earth_crystal_doubles_plus1_counters_on_your_creatures():
    """The Earth Crystal doubles +1/+1 counters placed on creatures you control."""
    print("\n=== Test: The Earth Crystal doubles your +1/+1 counters ===")
    game, (p, opp) = _make_game(2)

    crystal = game.create_object(
        name="The Earth Crystal",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=THE_EARTH_CRYSTAL.characteristics,
        card_def=THE_EARTH_CRYSTAL,
    )
    assert crystal.interceptor_ids, "Earth Crystal should register interceptors"

    # Friendly creature
    friendly = game.create_object(
        name="Friend",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, power=2, toughness=2,
        ),
    )
    interceptor_id = next(iter(crystal.interceptor_ids))
    interceptor = game.state.interceptors.get(interceptor_id)
    assert interceptor is not None

    your_counter = Event(
        type=EventType.COUNTER_ADDED,
        payload={'object_id': friendly.id, 'counter_type': '+1/+1', 'amount': 1},
    )
    assert interceptor.filter(your_counter, game.state)
    res = interceptor.handler(your_counter, game.state)
    assert res.transformed_event.payload['amount'] == 2, (
        f"Expected doubled 2, got {res.transformed_event.payload['amount']}"
    )

    # Opponent's creature should not benefit
    enemy = game.create_object(
        name="Enemy",
        owner_id=opp.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, power=2, toughness=2,
        ),
    )
    enemy_counter = Event(
        type=EventType.COUNTER_ADDED,
        payload={'object_id': enemy.id, 'counter_type': '+1/+1', 'amount': 1},
    )
    assert not interceptor.filter(enemy_counter, game.state), (
        "Earth Crystal should not double counters on opponent creatures"
    )
    print("PASS: Earth Crystal doubles your +1/+1 counters only")


def test_webshooters_grants_static_pt_and_reach():
    """Web-Shooters static grants flow only to the attached creature."""
    print("\n=== Test: Web-Shooters grants +1/+1 + reach to equipped creature ===")
    game, (p,) = _make_game(1)

    equipment = game.create_object(
        name="Web-Shooters",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=WEBSHOOTERS.characteristics,
        card_def=WEBSHOOTERS,
    )
    assert equipment.interceptor_ids, "Web-Shooters should register interceptors"

    creature = game.create_object(
        name="Hero",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, power=2, toughness=2,
        ),
    )
    creature.state.attached_to = equipment.id

    # Power query with attached relationship -> bumped by +1.
    qp = Event(
        type=EventType.QUERY_POWER,
        payload={'object_id': creature.id, 'value': 2},
    )
    matching = []
    for iid in equipment.interceptor_ids:
        i = game.state.interceptors.get(iid)
        if i and i.filter(qp, game.state):
            matching.append(i)
    assert len(matching) == 1, f"Expected 1 power-grant interceptor, got {len(matching)}"
    res = matching[0].handler(qp, game.state)
    assert res.transformed_event.payload['value'] == 3, (
        f"Expected +1/+1 -> 3, got {res.transformed_event.payload['value']}"
    )

    # Abilities query should grant 'reach'.
    qa = Event(
        type=EventType.QUERY_ABILITIES,
        payload={'object_id': creature.id, 'granted': []},
    )
    matched_kw = []
    for iid in equipment.interceptor_ids:
        i = game.state.interceptors.get(iid)
        if i and i.filter(qa, game.state):
            matched_kw.append(i)
    assert matched_kw, "Web-Shooters should grant reach via QUERY_ABILITIES"
    res2 = matched_kw[0].handler(qa, game.state)
    assert 'reach' in res2.transformed_event.payload['granted']
    print("PASS: Web-Shooters grants +1/+1 and reach to equipped creature")


def test_webshooters_does_not_grant_to_unattached_creature():
    """Web-Shooters' static does not affect a creature it isn't equipped to."""
    print("\n=== Test: Web-Shooters does not grant to unequipped creature ===")
    game, (p,) = _make_game(1)
    equipment = game.create_object(
        name="Web-Shooters",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=WEBSHOOTERS.characteristics,
        card_def=WEBSHOOTERS,
    )
    creature = game.create_object(
        name="Stranger",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, power=2, toughness=2,
        ),
    )
    # Not attached.
    qp = Event(
        type=EventType.QUERY_POWER,
        payload={'object_id': creature.id, 'value': 2},
    )
    for iid in equipment.interceptor_ids:
        i = game.state.interceptors.get(iid)
        if i:
            assert not i.filter(qp, game.state), (
                "Should not grant +1 to unattached creature"
            )
    print("PASS: Web-Shooters static is gated by attachment")


def test_spidersuit_grants_plus_two_plus_two():
    """Spider-Suit grants +2/+2 to its equipped creature."""
    print("\n=== Test: Spider-Suit grants +2/+2 to equipped creature ===")
    game, (p,) = _make_game(1)
    equipment = game.create_object(
        name="Spider-Suit",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SPIDERSUIT.characteristics,
        card_def=SPIDERSUIT,
    )
    creature = game.create_object(
        name="Spider",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, power=1, toughness=1,
        ),
    )
    creature.state.attached_to = equipment.id

    qp = Event(
        type=EventType.QUERY_POWER,
        payload={'object_id': creature.id, 'value': 1},
    )
    found_p = False
    for iid in equipment.interceptor_ids:
        i = game.state.interceptors.get(iid)
        if i and i.filter(qp, game.state):
            res = i.handler(qp, game.state)
            assert res.transformed_event.payload['value'] == 3
            found_p = True
            break
    assert found_p, "Spider-Suit power grant should fire"

    qt = Event(
        type=EventType.QUERY_TOUGHNESS,
        payload={'object_id': creature.id, 'value': 1},
    )
    found_t = False
    for iid in equipment.interceptor_ids:
        i = game.state.interceptors.get(iid)
        if i and i.filter(qt, game.state):
            res = i.handler(qt, game.state)
            assert res.transformed_event.payload['value'] == 3
            found_t = True
            break
    assert found_t, "Spider-Suit toughness grant should fire"
    print("PASS: Spider-Suit grants +2/+2 to equipped creature")


def run_all():
    print("=" * 60)
    print("FIN + SPM PHASE 1 WIRING TESTS")
    print("=" * 60)

    test_wind_crystal_doubles_life_gain()
    test_water_crystal_adds_four_to_opponent_mill()
    test_darkness_crystal_redirects_opponent_creature_death()
    test_earth_crystal_doubles_plus1_counters_on_your_creatures()
    test_webshooters_grants_static_pt_and_reach()
    test_webshooters_does_not_grant_to_unattached_creature()
    test_spidersuit_grants_plus_two_plus_two()

    print("\n" + "=" * 60)
    print("ALL FIN + SPM PHASE 1 WIRING TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    run_all()
