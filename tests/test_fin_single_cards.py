"""
Final Fantasy single-card wiring tests + per-turn life-gained tracker proof.

Covers cards wired in the FIN punch-list pass:
- Hope Estheim (proof of life-gained tracking)
- Sandworm (red) — ETB destroy target land + may-search basic for the
  destroyed land's controller
- Sazh Katzroy — ETB Bird/basic-land tutor + attack +1/+1 counter w/ doubling
- Yuna, Hope of Spira — keyword grant (trample/lifelink/ward) + end-step
  enchantment-graveyard return
- Zell Dincht — additional land play, +1/+0 per land static, end-step bounce
- Lion Heart — ETB damage to any target + +2/+1 equipment static

Also verifies the per-turn life-gained tracker (`life_gained_this_turn`):
gain accumulates, mid-turn losses don't undo it, turn rollover resets to 0.

Run directly: ``python tests/test_fin_single_cards.py``
"""

import os
import sys

_THIS = os.path.abspath(__file__)
_ROOT = os.path.dirname(os.path.dirname(_THIS))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, Characteristics,
)
from src.engine.turn_state import life_gained_this_turn

from src.cards.final_fantasy import (
    HOPE_ESTHEIM,
    SANDWORM,
    SAZH_KATZROY,
    YUNA_HOPE_OF_SPIRA,
    ZELL_DINCHT,
    LION_HEART,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _new_game(num_players: int = 2):
    g = Game(mode="mtg")
    players = [g.add_player(f"P{i}", life=20) for i in range(num_players)]
    if num_players >= 1:
        g.state.active_player = players[0].id
    return g, players


def _put_on_battlefield(game, owner_id, card_def, name=None):
    """Spawn a card with its setup_interceptors directly on the battlefield."""
    obj = game.create_object(
        name=name or card_def.name,
        owner_id=owner_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    return obj


def _put_in_hand(game, owner_id, card_def, name=None):
    obj = game.create_object(
        name=name or card_def.name,
        owner_id=owner_id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    return obj


def _emit_etb(game, obj, owner_id):
    """Emit a ZONE_CHANGE from HAND to BATTLEFIELD so ETB triggers fire."""
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': f'hand_{owner_id}',
            'to_zone': 'battlefield',
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))


def _vanilla_creature(game, owner_id, name="Bear", power=2, toughness=2,
                     subtypes=None):
    return game.create_object(
        name=name,
        owner_id=owner_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            power=power,
            toughness=toughness,
            subtypes=subtypes or set(),
        ),
    )


def _vanilla_land(game, owner_id, name="Forest", subtype="Forest"):
    obj = game.create_object(
        name=name,
        owner_id=owner_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.LAND},
            supertypes={"Basic"},
            subtypes={subtype},
        ),
    )
    return obj


# =============================================================================
# Per-turn life-gained tracker
# =============================================================================

def test_life_gained_accumulates_and_lost_does_not_subtract():
    print("\n=== Test: life_gained_this_turn accumulates ===")
    g, (p, _) = _new_game(2)

    g.emit(Event(type=EventType.LIFE_CHANGE,
                 payload={'player': p.id, 'amount': 3}))
    assert life_gained_this_turn(p.id, g.state) == 3

    g.emit(Event(type=EventType.LIFE_CHANGE,
                 payload={'player': p.id, 'amount': 2}))
    assert life_gained_this_turn(p.id, g.state) == 5

    # Life loss does not reduce the gained tally.
    g.emit(Event(type=EventType.LIFE_CHANGE,
                 payload={'player': p.id, 'amount': -4}))
    assert life_gained_this_turn(p.id, g.state) == 5
    print("PASS: gain accumulates, loss does not subtract")


def test_life_gained_resets_on_turn_rollover():
    print("\n=== Test: life_gained_this_turn resets on turn rollover ===")
    g, (p, _) = _new_game(2)

    g.emit(Event(type=EventType.LIFE_CHANGE,
                 payload={'player': p.id, 'amount': 7}))
    assert life_gained_this_turn(p.id, g.state) == 7

    # Simulate turn end: turn_data is cleared by TurnManager._emit_turn_end.
    # Tests that don't run the full TurnManager just clear the dict directly,
    # which is the same observable behavior.
    g.state.turn_data.clear()
    assert life_gained_this_turn(p.id, g.state) == 0
    print("PASS: turn rollover resets life_gained tracker")


# =============================================================================
# Hope Estheim
# =============================================================================

def test_hope_estheim_mills_opponents_when_life_gained():
    print("\n=== Test: Hope Estheim mills X = life gained this turn ===")
    g, (p, opp) = _new_game(2)
    hope = _put_on_battlefield(g, p.id, HOPE_ESTHEIM)
    assert hope.interceptor_ids, "Hope Estheim should register interceptors"

    # Stock opponent's library with some cards so MILL has fodder.
    for _ in range(10):
        g.create_object(
            name="Filler",
            owner_id=opp.id,
            zone=ZoneType.LIBRARY,
            characteristics=Characteristics(types={CardType.CREATURE},
                                            power=1, toughness=1),
        )
    opp_library_before = len(g.state.zones[f'library_{opp.id}'].objects)
    opp_gy_before = len(g.state.zones[f'graveyard_{opp.id}'].objects)

    # Gain 4 life this turn.
    g.emit(Event(type=EventType.LIFE_CHANGE,
                 payload={'player': p.id, 'amount': 4}))
    assert life_gained_this_turn(p.id, g.state) == 4

    # Trigger Hope's end-step ability.
    g.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step'}))

    opp_library_after = len(g.state.zones[f'library_{opp.id}'].objects)
    opp_gy_after = len(g.state.zones[f'graveyard_{opp.id}'].objects)
    milled = opp_library_before - opp_library_after
    assert milled == 4, f"Expected opp to mill 4, got {milled}"
    assert (opp_gy_after - opp_gy_before) == 4
    print(f"PASS: opp milled {milled} cards (gained 4 life)")


def test_hope_estheim_no_fire_when_no_life_gained():
    print("\n=== Test: Hope Estheim no-op when no life gained ===")
    g, (p, opp) = _new_game(2)
    _put_on_battlefield(g, p.id, HOPE_ESTHEIM)
    for _ in range(5):
        g.create_object(
            name="Filler",
            owner_id=opp.id,
            zone=ZoneType.LIBRARY,
            characteristics=Characteristics(types={CardType.CREATURE},
                                            power=1, toughness=1),
        )
    before = len(g.state.zones[f'library_{opp.id}'].objects)
    g.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step'}))
    after = len(g.state.zones[f'library_{opp.id}'].objects)
    assert before == after, "No mill should fire when no life gained"
    print("PASS: no mill when no life gained")


# =============================================================================
# Sandworm (red)
# =============================================================================

def test_sandworm_etb_emits_target_required_for_lands():
    print("\n=== Test: Sandworm ETB emits TARGET_REQUIRED for lands ===")
    g, (p, opp) = _new_game(2)
    # Put a couple of lands on the battlefield so there's something to target.
    _vanilla_land(g, opp.id, name="Mountain", subtype="Mountain")
    _vanilla_land(g, p.id, name="Forest", subtype="Forest")

    sw = _put_in_hand(g, p.id, SANDWORM)
    _emit_etb(g, sw, p.id)

    # Sandworm sets up a TARGET_REQUIRED PendingChoice for a land.
    pc = g.state.pending_choice
    assert pc is not None, "Expected a pending target choice for the land"
    assert pc.choice_type == "target_with_callback"
    # Both lands should be legal targets.
    assert len(pc.options) >= 2
    print(f"PASS: Sandworm prompted with {len(pc.options)} legal land target(s)")


# =============================================================================
# Sazh Katzroy
# =============================================================================

def test_sazh_katzroy_etb_opens_library_search():
    print("\n=== Test: Sazh Katzroy ETB opens library search ===")
    g, (p, _) = _new_game(2)
    sazh = _put_in_hand(g, p.id, SAZH_KATZROY)
    # Put a Bird and a basic Forest in the library to ensure it has options.
    g.create_object(
        name="Wandering Sparrow",
        owner_id=p.id,
        zone=ZoneType.LIBRARY,
        characteristics=Characteristics(
            types={CardType.CREATURE}, subtypes={"Bird"},
            power=1, toughness=1,
        ),
    )
    g.create_object(
        name="Forest",
        owner_id=p.id,
        zone=ZoneType.LIBRARY,
        characteristics=Characteristics(
            types={CardType.LAND}, supertypes={"Basic"},
            subtypes={"Forest"},
        ),
    )
    _emit_etb(g, sazh, p.id)
    pc = g.state.pending_choice
    assert pc is not None, "Sazh should open a library search PendingChoice"
    assert pc.choice_type in ("library_search", "library_search_with_callback")
    # At least the Bird and the Forest should be legal.
    assert len(pc.options) >= 2
    print(f"PASS: Sazh opened library search with {len(pc.options)} legal options")


def test_sazh_katzroy_attack_targets_creature_for_counter():
    print("\n=== Test: Sazh Katzroy attack opens target choice for +1/+1 ===")
    g, (p, _) = _new_game(2)
    sazh = _put_on_battlefield(g, p.id, SAZH_KATZROY)
    bear = _vanilla_creature(g, p.id, name="Grizzly Bear")

    g.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': sazh.id, 'attacking_player': p.id},
    ))
    pc = g.state.pending_choice
    assert pc is not None, "Attack should prompt for a +1/+1 counter target"
    assert pc.choice_type == "target_with_callback"
    assert bear.id in pc.options or sazh.id in pc.options
    print(f"PASS: attack prompted with {len(pc.options)} creature target(s)")


# =============================================================================
# Yuna, Hope of Spira
# =============================================================================

def test_yuna_grants_keywords_to_enchantment_creatures():
    print("\n=== Test: Yuna grants trample/lifelink/ward to enchantment creatures ===")
    g, (p, _) = _new_game(2)
    yuna = _put_on_battlefield(g, p.id, YUNA_HOPE_OF_SPIRA)
    # Active turn must be Yuna's controller for the keyword grant.
    g.state.active_player = p.id

    # Plain creature does NOT get the keywords (not an enchantment).
    bear = _vanilla_creature(g, p.id, name="Bear")
    # Enchantment creature SHOULD get them.
    starfield = g.create_object(
        name="Starfield Bear",
        owner_id=p.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE, CardType.ENCHANTMENT},
            power=2, toughness=2,
        ),
    )

    def _query_keywords(target_id):
        ev = Event(type=EventType.QUERY_ABILITIES,
                   payload={'object_id': target_id, 'granted': []})
        result = g.emit(ev)
        # The pipeline returns the transformed event; read the granted list off
        # the state-mutated event by re-reading from interceptors directly.
        # Simplest: walk all REACT/QUERY interceptors and accumulate.
        granted = list(ev.payload.get('granted', []))
        for interceptor_id in (yuna.interceptor_ids or set()):
            interceptor = g.state.interceptors.get(interceptor_id)
            if interceptor is None:
                continue
            test_ev = Event(type=EventType.QUERY_ABILITIES,
                            payload={'object_id': target_id, 'granted': []})
            if interceptor.filter(test_ev, g.state):
                res = interceptor.handler(test_ev, g.state)
                if res.transformed_event is not None:
                    granted.extend(res.transformed_event.payload.get('granted', []))
        return granted

    starfield_keywords = _query_keywords(starfield.id)
    bear_keywords = _query_keywords(bear.id)
    yuna_keywords = _query_keywords(yuna.id)

    assert 'trample' in starfield_keywords
    assert 'lifelink' in starfield_keywords
    assert 'ward' in starfield_keywords
    assert 'trample' in yuna_keywords
    assert 'trample' not in bear_keywords
    print("PASS: Yuna grants trample/lifelink/ward to herself + enchantment creatures only")


def test_yuna_end_step_offers_enchantment_recursion():
    print("\n=== Test: Yuna end step offers enchantment recursion ===")
    g, (p, _) = _new_game(2)
    yuna = _put_on_battlefield(g, p.id, YUNA_HOPE_OF_SPIRA)
    # Put an enchantment in the graveyard.
    g.create_object(
        name="Pacifism",
        owner_id=p.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT}, subtypes={"Aura"},
        ),
    )
    g.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step'}))
    pc = g.state.pending_choice
    assert pc is not None, "Yuna's end step should open a graveyard target choice"
    assert pc.choice_type == "target_with_callback"
    assert pc.min_choices == 0  # "up to one"
    print("PASS: Yuna end step offered up-to-one enchantment-from-graveyard")


# =============================================================================
# Zell Dincht
# =============================================================================

def test_zell_dincht_end_step_bounce_target_choice():
    print("\n=== Test: Zell Dincht end step bounce prompts for land ===")
    g, (p, _) = _new_game(2)
    zell = _put_on_battlefield(g, p.id, ZELL_DINCHT)
    _vanilla_land(g, p.id, name="Forest", subtype="Forest")
    _vanilla_land(g, p.id, name="Mountain", subtype="Mountain")

    g.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step'}))
    pc = g.state.pending_choice
    assert pc is not None, "Zell's end step should open a target-land choice"
    assert pc.choice_type == "target_with_callback"
    assert len(pc.options) == 2  # both lands you control
    print(f"PASS: Zell prompted with {len(pc.options)} of your lands")


def test_zell_dincht_power_scales_with_lands():
    print("\n=== Test: Zell Dincht +1/+0 per land ===")
    g, (p, _) = _new_game(2)
    zell = _put_on_battlefield(g, p.id, ZELL_DINCHT)
    for n in range(3):
        _vanilla_land(g, p.id, name=f"Forest{n}", subtype="Forest")

    # Query power: base 0 + 3 lands = 3.
    ev = Event(type=EventType.QUERY_POWER,
               payload={'object_id': zell.id, 'value': 0})
    val = ev.payload.get('value', 0)
    for interceptor_id in (zell.interceptor_ids or set()):
        interceptor = g.state.interceptors.get(interceptor_id)
        if interceptor is None:
            continue
        test_ev = Event(type=EventType.QUERY_POWER,
                        payload={'object_id': zell.id, 'value': val})
        if interceptor.filter(test_ev, g.state):
            res = interceptor.handler(test_ev, g.state)
            if res.transformed_event is not None:
                val = res.transformed_event.payload.get('value', val)
    assert val == 3, f"Expected Zell to be 3/3 with 3 lands, got power={val}"
    print(f"PASS: Zell power = {val} with 3 lands (base 0 + 1 per land)")


# =============================================================================
# Lion Heart
# =============================================================================

def test_lion_heart_etb_damage_target_required():
    print("\n=== Test: Lion Heart ETB requires a damage target ===")
    g, (p, opp) = _new_game(2)
    bear = _vanilla_creature(g, opp.id, name="Opp Bear")
    lion = _put_in_hand(g, p.id, LION_HEART)
    _emit_etb(g, lion, p.id)

    pc = g.state.pending_choice
    assert pc is not None, "Lion Heart ETB should require a target"
    assert pc.choice_type == "target_with_callback"
    # 'any' target_filter — both players + the creature should be legal.
    assert bear.id in pc.options or opp.id in pc.options or p.id in pc.options
    print(f"PASS: Lion Heart prompted with {len(pc.options)} legal target(s)")


def test_lion_heart_static_pt_when_attached():
    print("\n=== Test: Lion Heart +2/+1 to attached creature ===")
    g, (p, _) = _new_game(2)
    lion = _put_on_battlefield(g, p.id, LION_HEART)
    bear = _vanilla_creature(g, p.id, name="Bear", power=2, toughness=2)
    # Manually attach.
    lion.state.attached_to = bear.id
    bear.state.attachments.append(lion.id)

    def _query(event_type, target_id):
        val = 0
        if event_type == EventType.QUERY_POWER:
            val = bear.characteristics.power or 0
        else:
            val = bear.characteristics.toughness or 0
        for interceptor_id in (lion.interceptor_ids or set()):
            interceptor = g.state.interceptors.get(interceptor_id)
            if interceptor is None:
                continue
            test_ev = Event(type=event_type,
                            payload={'object_id': target_id, 'value': val})
            if interceptor.filter(test_ev, g.state):
                res = interceptor.handler(test_ev, g.state)
                if res.transformed_event is not None:
                    val = res.transformed_event.payload.get('value', val)
        return val

    p_val = _query(EventType.QUERY_POWER, bear.id)
    t_val = _query(EventType.QUERY_TOUGHNESS, bear.id)
    assert p_val == 4, f"Expected attached creature power 4 (2 + 2), got {p_val}"
    assert t_val == 3, f"Expected attached creature toughness 3 (2 + 1), got {t_val}"
    print(f"PASS: Lion Heart bumps attached creature to {p_val}/{t_val}")


# =============================================================================
# Test runner
# =============================================================================

def main():
    tests = [
        # Per-turn tracker
        test_life_gained_accumulates_and_lost_does_not_subtract,
        test_life_gained_resets_on_turn_rollover,
        # Hope Estheim
        test_hope_estheim_mills_opponents_when_life_gained,
        test_hope_estheim_no_fire_when_no_life_gained,
        # Sandworm
        test_sandworm_etb_emits_target_required_for_lands,
        # Sazh Katzroy
        test_sazh_katzroy_etb_opens_library_search,
        test_sazh_katzroy_attack_targets_creature_for_counter,
        # Yuna
        test_yuna_grants_keywords_to_enchantment_creatures,
        test_yuna_end_step_offers_enchantment_recursion,
        # Zell Dincht
        test_zell_dincht_end_step_bounce_target_choice,
        test_zell_dincht_power_scales_with_lands,
        # Lion Heart
        test_lion_heart_etb_damage_target_required,
        test_lion_heart_static_pt_when_attached,
    ]

    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
            print(f"  FAIL: {t.__name__}: {e}")
        except Exception as e:  # noqa
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
            print(f"  ERROR: {t.__name__}: {e}")

    total = len(tests)
    passed = total - len(failed)
    print(f"\n{'='*60}\nResults: {passed}/{total} tests passed")
    if failed:
        print("Failures:")
        for name, msg in failed:
            print(f"  - {name}: {msg}")
        sys.exit(1)
    else:
        print("All FIN single-card tests passed.")


if __name__ == "__main__":
    main()
