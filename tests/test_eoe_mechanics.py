"""
Test EOE Station + Void mechanics and the 6 wired cards.

Covers:
  * Station — tap a creature, charge counters land on the Station.
  * Station — sorcery speed gating (active player + main phase + empty stack).
  * Station — tapping a tapped creature is rejected.
  * Threshold — once charge >= threshold, threshold_effect_fn fires once and
    a STATION_ACTIVATED marker event is emitted.
  * Void — exiling a card sets card_was_exiled_this_turn; the void trigger
    fires at the start of the controller's end step.
  * Void — turn rollover clears the marker.
  * Per-card tests for each of the 6 cards (4 stations + 2 voids).
"""

import os
import sys
# Tests live in tests/; push the project root onto sys.path so 'src' resolves.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, GameObject,
)
from src.engine.eoe_mechanics import (
    make_station_ability, make_charge_threshold_ability, make_void_trigger,
    is_stationed, get_station_charge,
)
from src.engine.types import (
    Characteristics, ObjectState, CardDefinition,
)
from src.engine.turn_state import (
    cards_exiled_this_turn, card_was_exiled_this_turn,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_basic_creature(game, owner_id, name="Test Creature", power=3, toughness=3,
                         tapped=False) -> GameObject:
    """Drop a vanilla creature on the battlefield with the given stats."""
    char = Characteristics(
        types={CardType.CREATURE},
        subtypes={"Test"},
        colors={Color.WHITE},
        power=power,
        toughness=toughness,
    )
    obj = game.create_object(
        name=name,
        owner_id=owner_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=char,
    )
    obj.state.tapped = tapped
    # Skip summoning sickness so tap costs work.
    obj.state.summoning_sickness = False
    return obj


def _put_card_on_battlefield(game, owner_id, card_def):
    """Put a CardDefinition onto the battlefield via ZONE_CHANGE so setup_interceptors fires."""
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner_id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None,
    )
    obj.card_def = card_def
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': f'hand_{owner_id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    return obj


def _make_station_target(game, owner_id, name="TestStation"):
    """Create a Station-style permanent on the battlefield (artifact, no creature)."""
    char = Characteristics(
        types={CardType.ARTIFACT},
        subtypes={"Spacecraft"},
        colors=set(),
        power=0,
        toughness=0,
    )
    obj = game.create_object(
        name=name,
        owner_id=owner_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=char,
    )
    return obj


# ---------------------------------------------------------------------------
# Mechanic tests
# ---------------------------------------------------------------------------

def test_station_tap_adds_charge_counters():
    """STATION_ACTIVATE -> donor tapped, charge counters added equal to donor power."""
    print("\n=== Test: Station tap adds charge counters ===")
    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    station = _make_station_target(game, p1.id)
    donor = _make_basic_creature(game, p1.id, name="Donor", power=3)
    assert not donor.state.tapped

    # Emit STATION_ACTIVATE directly.
    game.emit(Event(
        type=EventType.STATION_ACTIVATE,
        payload={'spacecraft_id': station.id, 'donor_id': donor.id},
        source=station.id, controller=p1.id,
    ))
    assert donor.state.tapped, "Donor should be tapped"
    charge = get_station_charge(station)
    assert charge == 3, f"Expected 3 charge, got {charge}"
    print(f"  Donor tapped={donor.state.tapped}, charge={charge}")
    print("PASS")


def test_station_threshold_fires_effect_once():
    """When charge crosses threshold, threshold_effect_fn fires and emits STATION_ACTIVATED."""
    print("\n=== Test: Station threshold fires once ===")
    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    station = _make_station_target(game, p1.id)
    fired = {"count": 0}

    def threshold_effect(event, state):
        fired["count"] += 1
        # Sentinel: emit a LIFE_CHANGE so we can test pipeline propagation too.
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': p1.id, 'amount': 5},
                      source=station.id)]

    interceptors = make_station_ability(
        station, threshold=6,
        threshold_effect_fn=threshold_effect,
        threshold_effect_once=True,
    )
    for it in interceptors:
        game.register_interceptor(it, station)

    # Add charge in two steps: 3 then 4 (should cross 6 on the second step).
    game.emit(Event(type=EventType.STATION_CHARGE,
                    payload={'object_id': station.id, 'amount': 3},
                    source=station.id, controller=p1.id))
    assert fired["count"] == 0, f"Should not fire below threshold; got {fired['count']}"
    game.emit(Event(type=EventType.STATION_CHARGE,
                    payload={'object_id': station.id, 'amount': 4},
                    source=station.id, controller=p1.id))
    assert fired["count"] == 1, f"Threshold should fire once; got {fired['count']}"
    assert p1.life == 25, f"Life should reflect threshold effect; got {p1.life}"

    # Re-cross (e.g. counter removed and re-added) should NOT refire when once=True.
    station.state.counters['charge'] = 0
    game.emit(Event(type=EventType.STATION_CHARGE,
                    payload={'object_id': station.id, 'amount': 7},
                    source=station.id, controller=p1.id))
    assert fired["count"] == 1, f"Once-only should not refire; got {fired['count']}"
    print(f"  Fired {fired['count']} time(s); life={p1.life}")
    print("PASS")


def test_station_rejects_tapped_donor():
    """STATION_ACTIVATE with a tapped donor short-circuits — no charge added."""
    print("\n=== Test: Station rejects tapped donor ===")
    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    station = _make_station_target(game, p1.id)
    donor = _make_basic_creature(game, p1.id, name="Donor", power=3, tapped=True)

    game.emit(Event(
        type=EventType.STATION_ACTIVATE,
        payload={'spacecraft_id': station.id, 'donor_id': donor.id},
        source=station.id, controller=p1.id,
    ))
    charge = get_station_charge(station)
    assert charge == 0, f"Expected 0 charge for tapped donor; got {charge}"
    print(f"  Charge after tapped-donor activation: {charge}")
    print("PASS")


def test_station_sorcery_speed_via_activated_ability():
    """make_station_ability registers a sorcery-speed ActivatedAbility."""
    print("\n=== Test: Station ability is sorcery-speed ===")
    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    station = _make_station_target(game, p1.id)
    interceptors = make_station_ability(station, threshold=6)
    for it in interceptors:
        game.register_interceptor(it, station)

    # Inspect the registered ActivatedAbility.
    abs_ = station.state.activated_abilities or []
    assert len(abs_) >= 1, "Station should register an activated ability"
    sa = abs_[0]
    assert sa.sorcery_speed, "Station ability must be sorcery-speed"
    assert sa.targets_required == 1, "Station ability needs a donor target"
    assert sa.target_kind == "creature_you_control_untapped"
    print(f"  Registered: sorcery_speed={sa.sorcery_speed}, targets={sa.targets_required}")
    print("PASS")


def test_charge_threshold_ability_gated():
    """make_charge_threshold_ability runs the effect only when charge >= threshold."""
    print("\n=== Test: Charge-threshold ability gates by counter count ===")
    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    station = _make_station_target(game, p1.id)
    fired = {"count": 0}

    def effect(o, st, targets):
        fired["count"] += 1
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': p1.id, 'amount': 1}, source=o.id)]

    interceptors = make_charge_threshold_ability(
        station, threshold=12, cost="{1}",
        effect_fn=effect, description="test",
    )
    for it in interceptors:
        game.register_interceptor(it, station)

    abs_ = station.state.activated_abilities
    assert abs_ and len(abs_) >= 1
    sa = abs_[0]

    # Below threshold: effect short-circuits.
    station.state.counters['charge'] = 5
    out = sa.effect_fn(station, game.state, [])
    assert out == [], "Below threshold should produce no events"
    assert fired["count"] == 0

    # At threshold: effect runs.
    station.state.counters['charge'] = 12
    out = sa.effect_fn(station, game.state, [])
    assert len(out) == 1
    assert fired["count"] == 1
    print(f"  Below=skipped ({0} events), at-threshold={len(out)} event(s)")
    print("PASS")


def test_void_trigger_fires_when_card_exiled():
    """Exiling a card sets card_was_exiled_this_turn and fires Void at end step."""
    print("\n=== Test: Void trigger fires after exile ===")
    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    holder = _make_station_target(game, p1.id, name="Void Holder")
    fired = {"count": 0}

    def void_effect(event, state):
        fired["count"] += 1
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': p1.id, 'amount': 1}, source=holder.id)]

    interceptor = make_void_trigger(holder, void_effect)
    game.register_interceptor(interceptor, holder)

    # No exile yet — void should not fire.
    assert not card_was_exiled_this_turn(game.state)
    game.emit(Event(type=EventType.PHASE_START,
                    payload={'phase': 'end'}, controller=p1.id))
    assert fired["count"] == 0, f"No void condition active; should not fire (got {fired['count']})"

    # Exile a dummy object to set the marker.
    dummy = _make_basic_creature(game, p1.id, name="Bait")
    game.emit(Event(type=EventType.EXILE,
                    payload={'object_id': dummy.id, 'controller': p1.id},
                    source=holder.id, controller=p1.id))
    assert card_was_exiled_this_turn(game.state), "exile_this_turn marker should be set"

    # Now end-step trigger should fire.
    game.emit(Event(type=EventType.PHASE_START,
                    payload={'phase': 'end'}, controller=p1.id))
    assert fired["count"] == 1, f"Void should fire once; got {fired['count']}"
    print(f"  exile_marker={card_was_exiled_this_turn(game.state)}, fired={fired['count']}")
    print("PASS")


def test_void_marker_clears_on_turn_rollover():
    """Clearing turn_data resets cards_exiled_this_turn (simulated turn rollover)."""
    print("\n=== Test: Void marker clears on turn rollover ===")
    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    dummy = _make_basic_creature(game, p1.id, name="Bait")
    game.emit(Event(type=EventType.EXILE,
                    payload={'object_id': dummy.id, 'controller': p1.id},
                    source=None, controller=p1.id))
    assert card_was_exiled_this_turn(game.state)

    # TurnManager._emit_turn_end clears turn_data; we simulate by clearing it.
    game.state.turn_data = {}
    assert not card_was_exiled_this_turn(game.state)
    print("PASS")


# ---------------------------------------------------------------------------
# Per-card tests
# ---------------------------------------------------------------------------

def test_evendo_waking_haven_card_setup():
    """Evendo Waking Haven registers a station ability + threshold mana ability."""
    print("\n=== Test: Evendo Waking Haven (Planet) ===")
    from src.cards.edge_of_eternities import EVENDO_WAKING_HAVEN
    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    obj = _put_card_on_battlefield(game, p1.id, EVENDO_WAKING_HAVEN)
    abs_ = obj.state.activated_abilities or []
    assert len(abs_) >= 2, f"Expected at least 2 activated abilities (station + 12+); got {len(abs_)}"
    descs = [a.description for a in abs_]
    print(f"  abilities: {descs}")
    # Station ability is sorcery-speed.
    assert any(a.sorcery_speed and a.targets_required == 1 for a in abs_), \
        "Station ability missing sorcery-speed donor activation"
    # 12+ mana ability description should embed the threshold marker.
    assert any("12+" in (a.description or "") for a in abs_), \
        "12+ threshold ability description missing"
    print("PASS")


def test_kavaron_memorial_world_card_setup():
    """Kavaron Memorial World registers station + 12+ Robot/pump ability."""
    print("\n=== Test: Kavaron Memorial World (Planet) ===")
    from src.cards.edge_of_eternities import KAVARON_MEMORIAL_WORLD
    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    obj = _put_card_on_battlefield(game, p1.id, KAVARON_MEMORIAL_WORLD)
    abs_ = obj.state.activated_abilities or []
    assert len(abs_) >= 2
    assert any("12+" in (a.description or "") and "Robot" in (a.description or "") for a in abs_), \
        "12+ Robot-deploy ability not registered"
    print(f"  abilities: {[a.description for a in abs_]}")
    print("PASS")


def test_susur_secundi_void_altar_card_setup():
    """Susur Secundi registers station + 12+ draw-cards-equal-to-power ability."""
    print("\n=== Test: Susur Secundi, Void Altar (Planet) ===")
    from src.cards.edge_of_eternities import SUSUR_SECUNDI_VOID_ALTAR
    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    obj = _put_card_on_battlefield(game, p1.id, SUSUR_SECUNDI_VOID_ALTAR)
    abs_ = obj.state.activated_abilities or []
    assert len(abs_) >= 2
    assert any("12+" in (a.description or "") and "Draw" in (a.description or "") for a in abs_), \
        "12+ draw ability not registered"
    print(f"  abilities: {[a.description for a in abs_]}")
    print("PASS")


def test_uthros_titanic_godcore_card_setup():
    """Uthros registers station + 12+ U-per-artifact mana ability."""
    print("\n=== Test: Uthros, Titanic Godcore (Planet) ===")
    from src.cards.edge_of_eternities import UTHROS_TITANIC_GODCORE
    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    obj = _put_card_on_battlefield(game, p1.id, UTHROS_TITANIC_GODCORE)
    abs_ = obj.state.activated_abilities or []
    assert len(abs_) >= 2
    assert any("12+" in (a.description or "") and "artifact" in (a.description or "").lower() for a in abs_), \
        "12+ artifact mana ability not registered"
    print(f"  abilities: {[a.description for a in abs_]}")
    print("PASS")


def test_voidforged_titan_void_trigger():
    """Voidforged Titan: end step + exile-this-turn -> draw + lose 1 life."""
    print("\n=== Test: Voidforged Titan (Void) ===")
    from src.cards.edge_of_eternities import VOIDFORGED_TITAN
    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    obj = _put_card_on_battlefield(game, p1.id, VOIDFORGED_TITAN)
    # Pre-condition: trigger interceptor registered.
    assert obj.interceptor_ids, "Voidforged Titan should register interceptors"

    # Exile a dummy to enable Void.
    dummy = _make_basic_creature(game, p1.id, name="Bait")
    game.emit(Event(type=EventType.EXILE,
                    payload={'object_id': dummy.id, 'controller': p1.id},
                    source=obj.id, controller=p1.id))
    assert card_was_exiled_this_turn(game.state)
    life_before = p1.life
    # End step trigger.
    game.emit(Event(type=EventType.PHASE_START,
                    payload={'phase': 'end'}, controller=p1.id))
    # Net delta: +1 draw (no life change) and -1 life.
    assert p1.life == life_before - 1, \
        f"Voidforged Titan should cost 1 life; before={life_before}, after={p1.life}"
    print(f"  life {life_before} -> {p1.life}")
    print("PASS")


def test_kavaron_skywarden_void_trigger():
    """Kavaron Skywarden: end step + exile-this-turn -> +1/+1 counter."""
    print("\n=== Test: Kavaron Skywarden (Void) ===")
    from src.cards.edge_of_eternities import KAVARON_SKYWARDEN
    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id

    obj = _put_card_on_battlefield(game, p1.id, KAVARON_SKYWARDEN)
    counters_before = obj.state.counters.get('+1/+1', 0)

    # Exile a dummy to enable Void.
    dummy = _make_basic_creature(game, p1.id, name="Bait")
    game.emit(Event(type=EventType.EXILE,
                    payload={'object_id': dummy.id, 'controller': p1.id},
                    source=obj.id, controller=p1.id))

    game.emit(Event(type=EventType.PHASE_START,
                    payload={'phase': 'end'}, controller=p1.id))
    counters_after = obj.state.counters.get('+1/+1', 0)
    assert counters_after == counters_before + 1, \
        f"Skywarden should add a +1/+1 counter; got {counters_after} (was {counters_before})"
    print(f"  +1/+1 counters: {counters_before} -> {counters_after}")
    print("PASS")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all_tests():
    print("=" * 60)
    print("EOE STATION + VOID MECHANIC TESTS")
    print("=" * 60)
    # Mechanic-level
    test_station_tap_adds_charge_counters()
    test_station_threshold_fires_effect_once()
    test_station_rejects_tapped_donor()
    test_station_sorcery_speed_via_activated_ability()
    test_charge_threshold_ability_gated()
    test_void_trigger_fires_when_card_exiled()
    test_void_marker_clears_on_turn_rollover()
    # Per-card
    test_evendo_waking_haven_card_setup()
    test_kavaron_memorial_world_card_setup()
    test_susur_secundi_void_altar_card_setup()
    test_uthros_titanic_godcore_card_setup()
    test_voidforged_titan_void_trigger()
    test_kavaron_skywarden_void_trigger()
    print("\n" + "=" * 60)
    print("ALL EOE MECHANIC TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
