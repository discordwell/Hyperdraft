"""
Bloomburrow Mechanic Helpers Tests

Verifies the four BLB set mechanics implemented in src/engine/blb_mechanics.py:
- Offspring (ETB token copy)
- Forage (cost helper: exile 3 GY OR sacrifice a Food)
- Expend N (mana-spent threshold trigger)
- Valiant (target-of-ally trigger, once per turn)
"""

import sys
sys.path.insert(0, '/Users/discordwell/Projects/HYPERDRAFT')

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, Characteristics, ObjectState, CardDefinition, PendingChoice,
    new_id, make_creature, make_artifact,
)
from src.engine.blb_mechanics import (
    make_offspring_setup,
    pay_forage_cost,
    make_forage_trigger,
    make_expend_trigger,
    record_mana_spent_for_expend,
    reset_expend_for_turn,
    make_valiant_trigger,
    emit_valiant_target_events,
)


def _new_game(p1_name="Alice", p2_name="Bob"):
    """Returns (game, p1_id, p2_id)."""
    from src.engine.game import Game
    game = Game()
    p1 = game.add_player(p1_name)
    p2 = game.add_player(p2_name)
    game.state.active_player = p1.id
    return game, p1.id, p2.id


# -----------------------------------------------------------------------------
# OFFSPRING
# -----------------------------------------------------------------------------
def test_offspring_creates_token_copy_on_etb():
    print("\n=== Test: Offspring helper creates 1/1 token copy on ETB ===")
    game, p1, p2 = _new_game()
    setup_fn = make_offspring_setup(offspring_cost="{2}")
    cd = make_creature(
        name="Test Mouse",
        power=2, toughness=2,
        mana_cost="{1}{W}",
        colors={Color.WHITE},
        subtypes={"Mouse"},
        text="Offspring {2}",
        setup_interceptors=setup_fn,
    )
    obj = game.create_object("Test Mouse", p1, ZoneType.BATTLEFIELD,
                             cd.characteristics, card_def=cd)

    bf_before = len(game.state.zones['battlefield'].objects)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'to_zone_type': ZoneType.BATTLEFIELD,
            'from_zone_type': ZoneType.HAND,
        },
        source=obj.id,
    ))
    bf_after = len(game.state.zones['battlefield'].objects)
    print(f"  Battlefield count: {bf_before} -> {bf_after}")
    assert bf_after == bf_before + 1, "Token copy should have been created"

    tokens = [o for o in game.state.objects.values()
              if o.name == "Test Mouse" and o.id != obj.id and o.state.is_token]
    assert len(tokens) == 1, f"Expected 1 token, got {len(tokens)}"
    tok = tokens[0]
    assert tok.characteristics.power == 1 and tok.characteristics.toughness == 1
    print(f"  Token: {tok.name} {tok.characteristics.power}/{tok.characteristics.toughness}")
    print("  Offspring works.")


# -----------------------------------------------------------------------------
# FORAGE
# -----------------------------------------------------------------------------
def test_forage_sacrifices_food_when_available():
    print("\n=== Test: Forage prefers Food sacrifice ===")
    game, p1, p2 = _new_game()
    food_cd = make_artifact(name="Food",
                            mana_cost="",
                            text="Food token",
                            subtypes={"Food"})
    food = game.create_object("Food", p1, ZoneType.BATTLEFIELD,
                              food_cd.characteristics, card_def=food_cd)
    food.characteristics.subtypes = {"Food"}

    for _ in range(3):
        game.create_object("Filler", p1, ZoneType.GRAVEYARD)

    gy_before = len(game.state.zones[f'graveyard_{p1}'].objects)
    paid = pay_forage_cost(p1, game.state, source_id="src")
    gy_after = len(game.state.zones[f'graveyard_{p1}'].objects)
    print(f"  Pay result: {paid}; food zone: {food.zone}; GY {gy_before}->{gy_after}")
    assert paid is True
    assert food.zone == ZoneType.GRAVEYARD
    print("  Forage prefers Food.")


def test_forage_falls_back_to_exiling_three_gy_cards():
    print("\n=== Test: Forage exiles 3 GY cards when no Food ===")
    game, p1, p2 = _new_game()
    for i in range(4):
        game.create_object(f"Filler{i}", p1, ZoneType.GRAVEYARD)
    gy_before = len(game.state.zones[f'graveyard_{p1}'].objects)
    ex_before = len(game.state.zones['exile'].objects)
    paid = pay_forage_cost(p1, game.state, source_id="src")
    gy_after = len(game.state.zones[f'graveyard_{p1}'].objects)
    ex_after = len(game.state.zones['exile'].objects)
    print(f"  GY {gy_before}->{gy_after}; Exile {ex_before}->{ex_after}")
    assert paid is True
    assert gy_before - gy_after == 3
    assert ex_after - ex_before == 3
    print("  Forage exiles 3 GY cards.")


def test_forage_fails_when_no_resources():
    print("\n=== Test: Forage fails with no Food and < 3 GY ===")
    game, p1, p2 = _new_game()
    game.create_object("Filler", p1, ZoneType.GRAVEYARD)
    paid = pay_forage_cost(p1, game.state, source_id="src")
    assert paid is False
    print("  Returns False as expected.")


# -----------------------------------------------------------------------------
# EXPEND N
# -----------------------------------------------------------------------------
def test_expend_4_fires_when_threshold_crossed():
    print("\n=== Test: Expend 4 fires on first crossing ===")
    game, p1, p2 = _new_game()
    fired = record_mana_spent_for_expend(game.state, p1, 2)
    assert len(fired) == 0
    fired = record_mana_spent_for_expend(game.state, p1, 3)  # 2+3=5
    assert len(fired) == 1
    assert fired[0].type == EventType.EXPEND_4_REACHED
    print(f"  Total: {game.state.turn_data[f'mana_spent_{p1}']}; fired {fired[0].type.name}")
    fired2 = record_mana_spent_for_expend(game.state, p1, 5)
    assert all(e.type != EventType.EXPEND_4_REACHED for e in fired2)
    print("  Once-per-turn enforced.")


def test_expend_8_fires_independently_of_4():
    print("\n=== Test: Expend 8 fires on its own ===")
    game, p1, p2 = _new_game()
    fired = record_mana_spent_for_expend(game.state, p1, 9)
    types_fired = {e.type for e in fired}
    assert EventType.EXPEND_4_REACHED in types_fired
    assert EventType.EXPEND_8_REACHED in types_fired
    print(f"  Both thresholds fired in single 9-mana payment.")


def test_expend_resets_each_turn():
    print("\n=== Test: Expend resets between turns ===")
    game, p1, p2 = _new_game()
    record_mana_spent_for_expend(game.state, p1, 5)
    reset_expend_for_turn(game.state, p1)
    fired = record_mana_spent_for_expend(game.state, p1, 5)
    assert any(e.type == EventType.EXPEND_4_REACHED for e in fired)
    print("  Reset works.")


def test_expend_trigger_interceptor_routes_to_handler():
    print("\n=== Test: Expend interceptor routes to handler ===")
    game, p1, p2 = _new_game()
    cd = make_creature(name="Test Tom", power=2, toughness=2,
                       mana_cost="{2}", colors=set(), subtypes={"Cat"})
    obj = game.create_object("Test Tom", p1, ZoneType.BATTLEFIELD,
                             cd.characteristics, card_def=cd)

    handler_calls = []

    def effect_fn(event, state):
        handler_calls.append(event)
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': p1, 'amount': 1},
                      source=obj.id)]

    interceptor = make_expend_trigger(obj, 4, effect_fn)
    game.register_interceptor(interceptor, obj)

    life_before = game.state.players[p1].life
    game.emit(Event(
        type=EventType.EXPEND_4_REACHED,
        payload={'controller': p1, 'threshold': 4, 'total': 5},
        source=obj.id,
        controller=p1,
    ))
    life_after = game.state.players[p1].life
    print(f"  Handler called {len(handler_calls)} times; life {life_before}->{life_after}")
    assert len(handler_calls) == 1
    assert life_after == life_before + 1
    print("  Expend handler runs.")


# -----------------------------------------------------------------------------
# VALIANT
# -----------------------------------------------------------------------------
def test_valiant_trigger_fires_once_per_turn():
    print("\n=== Test: Valiant fires only once per turn ===")
    game, p1, p2 = _new_game()
    cd = make_creature(name="Hero", power=1, toughness=1,
                       mana_cost="{W}", colors={Color.WHITE}, subtypes={"Mouse"})
    hero = game.create_object("Hero", p1, ZoneType.BATTLEFIELD,
                              cd.characteristics, card_def=cd)

    fire_count = [0]

    def effect_fn(event, state):
        fire_count[0] += 1
        return []

    inter = make_valiant_trigger(hero, effect_fn)
    game.register_interceptor(inter, hero)

    game.emit(Event(
        type=EventType.VALIANT_TARGETED,
        payload={'target_id': hero.id, 'controller': p1, 'source_id': 'spell1'},
        source='spell1',
        controller=p1,
    ))
    game.emit(Event(
        type=EventType.VALIANT_TARGETED,
        payload={'target_id': hero.id, 'controller': p1, 'source_id': 'spell2'},
        source='spell2',
        controller=p1,
    ))
    print(f"  Fire count: {fire_count[0]}")
    assert fire_count[0] == 1
    print("  Once-per-turn ok.")


def test_valiant_does_not_fire_for_opponent_spells():
    print("\n=== Test: Valiant ignores opponent spells ===")
    game, p1, p2 = _new_game()
    cd = make_creature(name="Hero", power=1, toughness=1,
                       mana_cost="{W}", colors={Color.WHITE}, subtypes={"Mouse"})
    hero = game.create_object("Hero", p1, ZoneType.BATTLEFIELD,
                              cd.characteristics, card_def=cd)

    fire_count = [0]
    def effect_fn(event, state):
        fire_count[0] += 1
        return []

    inter = make_valiant_trigger(hero, effect_fn)
    game.register_interceptor(inter, hero)

    game.emit(Event(
        type=EventType.VALIANT_TARGETED,
        payload={'target_id': hero.id, 'controller': p2, 'source_id': 'opp_spell'},
        source='opp_spell',
        controller=p2,
    ))
    print(f"  Fire count after opponent target: {fire_count[0]}")
    assert fire_count[0] == 0
    print("  Filter works.")


def test_emit_valiant_target_events_filters_to_controller_permanents():
    print("\n=== Test: emit_valiant_target_events filters correctly ===")
    game, p1, p2 = _new_game()
    cd = make_creature(name="Hero", power=1, toughness=1,
                       mana_cost="{W}", colors={Color.WHITE})
    your = game.create_object("YourMouse", p1, ZoneType.BATTLEFIELD,
                              cd.characteristics, card_def=cd)
    opp = game.create_object("OppMouse", p2, ZoneType.BATTLEFIELD,
                             cd.characteristics, card_def=cd)
    events = emit_valiant_target_events([your.id, opp.id, p2], "spell", p1, game.state)
    target_ids = {e.payload['target_id'] for e in events}
    print(f"  Selected: 3 (your, opp, player); emitted for: {target_ids}")
    assert your.id in target_ids
    assert opp.id not in target_ids
    assert p2 not in target_ids
    print("  Filter correct.")


# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    test_offspring_creates_token_copy_on_etb()
    test_forage_sacrifices_food_when_available()
    test_forage_falls_back_to_exiling_three_gy_cards()
    test_forage_fails_when_no_resources()
    test_expend_4_fires_when_threshold_crossed()
    test_expend_8_fires_independently_of_4()
    test_expend_resets_each_turn()
    test_expend_trigger_interceptor_routes_to_handler()
    test_valiant_trigger_fires_once_per_turn()
    test_valiant_does_not_fire_for_opponent_spells()
    test_emit_valiant_target_events_filters_to_controller_permanents()
    print("\n" + "=" * 60)
    print("ALL BLB MECHANICS TESTS PASSED!")
    print("=" * 60)
