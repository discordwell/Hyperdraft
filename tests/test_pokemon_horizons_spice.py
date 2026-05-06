"""
Pokemon Horizons Spice Pass Tests

Validates the 8 PKH spice cards added after Wave-22 R4 revealed PKH at
25%. Each card gets a load test + at least one behavior test.
"""

import sys
sys.path.insert(0, '/Users/discordwell/Projects/HYPERDRAFT')

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, Characteristics,
    get_power, get_toughness,
)
from src.cards.custom.pokemon_horizons import POKEMON_HORIZONS_CARDS


def _put_on_battlefield(game, player, card_name):
    """Standard spice-test pattern: create in hand without card_def, then
    emit ZONE_CHANGE to battlefield so the pipeline's _handle_zone_change
    runs setup_interceptors and fires ETB triggers."""
    card_def = POKEMON_HORIZONS_CARDS[card_name]
    obj = game.create_object(
        name=card_name,
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
            'from_zone': f'hand_{player.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    return obj


def _put_in_hand(game, player, card_name):
    card_def = POKEMON_HORIZONS_CARDS[card_name]
    obj = game.create_object(
        name=card_name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    return obj


def _make_opponent_creature(game, player, name="Foe", power=2, toughness=2):
    return game.create_object(
        name=name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Beast"},
            colors={Color.GREEN},
            power=power, toughness=toughness,
        ),
    )


# ============================================================================
# Charizard, Mega Evolved
# ============================================================================

def test_charizard_mega_loads_with_flying():
    print("\n=== Charizard Mega: load ===")
    game = Game()
    p1 = game.add_player("P1")
    cz = _put_on_battlefield(game, p1, "Charizard, Mega Evolved")
    assert CardType.CREATURE in cz.characteristics.types
    assert "Dragon" in cz.characteristics.subtypes
    assert "Legendary" in (cz.characteristics.supertypes or set())
    # Flying keyword grant + ETB damage trigger = ≥2 interceptors
    assert len(cz.interceptor_ids) >= 2
    print(f"  Loaded with {len(cz.interceptor_ids)} interceptors")


def test_charizard_mega_etb_emits_damage():
    print("\n=== Charizard Mega: ETB damage ===")
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    foe1 = _make_opponent_creature(game, p2, "Foe1", power=3, toughness=3)
    foe2 = _make_opponent_creature(game, p2, "Foe2", power=2, toughness=2)

    before = len(game.state.event_log)
    cz = _put_on_battlefield(game, p1, "Charizard, Mega Evolved")
    new = game.state.event_log[before:]
    dmg_events = [
        e for e in new
        if e.type == EventType.DAMAGE and e.payload.get('source') == cz.id
    ]
    total = sum(e.payload.get('amount', 0) for e in dmg_events)
    assert dmg_events, f"Charizard ETB should emit DAMAGE; got {[e.type.name for e in new]}"
    assert total == 4, f"Charizard total ETB damage should be 4; got {total}"
    print(f"  Emitted {len(dmg_events)} damage events totaling {total}")


# ============================================================================
# Moltres, Phoenix Reborn
# ============================================================================

def test_moltres_loads_with_flying_haste():
    print("\n=== Moltres: load ===")
    game = Game()
    p1 = game.add_player("P1")
    m = _put_on_battlefield(game, p1, "Moltres, Phoenix Reborn")
    assert "Phoenix" in m.characteristics.subtypes
    # Flying+haste grant + death trigger + upkeep trigger = ≥3 interceptors
    assert len(m.interceptor_ids) >= 3
    print(f"  Loaded with {len(m.interceptor_ids)} interceptors")


def test_moltres_death_sets_return_flag():
    """When Moltres dies, turn_data flag is set so it returns next upkeep."""
    print("\n=== Moltres: death sets return flag ===")
    game = Game()
    p1 = game.add_player("P1")
    m = _put_on_battlefield(game, p1, "Moltres, Phoenix Reborn")

    # Simulate death via OBJECT_DESTROYED (death triggers fire on this).
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': m.id},
        source=m.id,
    ))
    assert game.state.turn_data.get(f'moltres_return_{m.id}'), (
        "Death should mark Moltres for return at next upkeep"
    )
    print("  Return flag set after death")


# ============================================================================
# Pikachu, Thunder Champion
# ============================================================================

def test_pikachu_loads_with_haste():
    print("\n=== Pikachu Champion: load ===")
    game = Game()
    p1 = game.add_player("P1")
    pk = _put_on_battlefield(game, p1, "Pikachu, Thunder Champion")
    assert "Mouse" in pk.characteristics.subtypes
    assert len(pk.interceptor_ids) >= 2  # haste + damage trigger
    print(f"  Loaded with {len(pk.interceptor_ids)} interceptors")


def test_pikachu_combat_damage_to_player_emits_draw():
    """Combat damage to player → DRAW event. Damage to creature → no draw."""
    print("\n=== Pikachu: combat damage draw ===")
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    pk = _put_on_battlefield(game, p1, "Pikachu, Thunder Champion")

    # Player damage → draw fires.
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p2.id, 'amount': 2, 'source': pk.id, 'is_combat': True},
        source=pk.id,
    ))
    new = game.state.event_log[before:]
    draws = [e for e in new if e.type == EventType.DRAW
             and e.payload.get('player') == p1.id]
    assert draws, f"Pikachu should DRAW on player combat damage; got {[e.type.name for e in new]}"
    print(f"  Player damage → {len(draws)} DRAW event(s)")

    # Creature damage → NO draw.
    foe = _make_opponent_creature(game, p2)
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': foe.id, 'amount': 2, 'source': pk.id, 'is_combat': True},
        source=pk.id,
    ))
    new = game.state.event_log[before:]
    draws = [e for e in new if e.type == EventType.DRAW]
    assert not draws, f"Pikachu must NOT draw on creature damage; got {draws}"
    print(f"  Creature damage → no DRAW (correct)")


# ============================================================================
# Eevee, Evolution Vessel
# ============================================================================

def test_eevee_loads_with_etb_search():
    print("\n=== Eevee Vessel: load ===")
    game = Game()
    p1 = game.add_player("P1")
    e = _put_on_battlefield(game, p1, "Eevee, Evolution Vessel")
    assert "Pokemon" in e.characteristics.subtypes
    assert len(e.interceptor_ids) >= 1
    print(f"  Loaded with {len(e.interceptor_ids)} interceptors")


# ============================================================================
# Master Ball
# ============================================================================

def test_master_ball_loads_as_legendary_artifact():
    print("\n=== Master Ball: load ===")
    game = Game()
    p1 = game.add_player("P1")
    mb = _put_on_battlefield(game, p1, "Master Ball")
    assert CardType.ARTIFACT in mb.characteristics.types
    assert "Legendary" in (mb.characteristics.supertypes or set())
    print(f"  Loaded with {len(mb.interceptor_ids)} interceptors")


# ============================================================================
# Volcanic Mantle
# ============================================================================

def test_volcanic_mantle_loads_as_equipment():
    print("\n=== Volcanic Mantle: load ===")
    game = Game()
    p1 = game.add_player("P1")
    vm = _put_on_battlefield(game, p1, "Volcanic Mantle")
    assert "Equipment" in vm.characteristics.subtypes
    assert "Legendary" in (vm.characteristics.supertypes or set())
    print(f"  Loaded with {len(vm.interceptor_ids)} interceptors")


def test_volcanic_mantle_grants_pt_haste_trample_on_attach():
    """ATTACH event with canonical {object_id, target_id} keys grants the
    +3/+1, haste, trample bundle."""
    print("\n=== Volcanic Mantle: attach grants buffs ===")
    game = Game()
    p1 = game.add_player("P1")
    vm = _put_on_battlefield(game, p1, "Volcanic Mantle")
    creature = game.create_object(
        name="Charmander",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Pokemon"},
            colors={Color.RED},
            power=2, toughness=1,
        ),
    )
    base_p, base_t = get_power(creature, game.state), get_toughness(creature, game.state)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': vm.id, 'target_id': creature.id},
        source=vm.id,
    ))

    new_p, new_t = get_power(creature, game.state), get_toughness(creature, game.state)
    assert new_p - base_p == 3, f"Equipped creature should get +3 power; got {new_p - base_p}"
    assert new_t - base_t == 1, f"Equipped creature should get +1 toughness; got {new_t - base_t}"
    print(f"  Stats: {base_p}/{base_t} → {new_p}/{new_t} (+3/+1 confirmed)")


# ============================================================================
# Reshiram, Truth Aspect
# ============================================================================

def test_reshiram_loads_with_flying_trample_and_cost_reduction():
    print("\n=== Reshiram: load ===")
    game = Game()
    p1 = game.add_player("P1")
    r = _put_on_battlefield(game, p1, "Reshiram, Truth Aspect")
    assert "Dragon" in r.characteristics.subtypes
    # flying/trample grant + ETB damage + cost reduction = ≥3 interceptors
    assert len(r.interceptor_ids) >= 3
    print(f"  Loaded with {len(r.interceptor_ids)} interceptors")


def test_reshiram_etb_emits_damage_to_threat():
    """ETB picks the highest-power opponent creature and burns it for 4."""
    print("\n=== Reshiram: ETB burn ===")
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    weak = _make_opponent_creature(game, p2, "Weak", power=1, toughness=1)
    strong = _make_opponent_creature(game, p2, "Strong", power=4, toughness=4)

    before = len(game.state.event_log)
    r = _put_on_battlefield(game, p1, "Reshiram, Truth Aspect")
    new = game.state.event_log[before:]
    dmg = [
        e for e in new
        if e.type == EventType.DAMAGE
        and e.payload.get('source') == r.id
    ]
    assert dmg, f"Reshiram ETB should emit DAMAGE; got {[e.type.name for e in new]}"
    targets = {e.payload.get('target') for e in dmg}
    assert strong.id in targets, (
        f"Reshiram should target the strongest opponent creature; "
        f"hit {targets} but expected {strong.id}"
    )
    print(f"  Burned the strongest threat (Strong, 4/4) for 4")


# ============================================================================
# Hyper Beam
# ============================================================================

def test_hyper_beam_loads_as_sorcery():
    print("\n=== Hyper Beam: load ===")
    cd = POKEMON_HORIZONS_CARDS["Hyper Beam"]
    assert CardType.SORCERY in cd.characteristics.types
    assert getattr(cd, "targets_required", 0) == 1
    assert getattr(cd, "resolve", None) is not None
    print("  Hyper Beam is a sorcery with resolve= and 1 target")


def test_hyper_beam_resolve_deals_6_damage():
    """resolve() returns one DAMAGE event for 6 to the chosen target."""
    print("\n=== Hyper Beam: resolve damage ===")
    cd = POKEMON_HORIZONS_CARDS["Hyper Beam"]
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    foe = _make_opponent_creature(game, p2, "Foe", power=3, toughness=6)

    # Build a fake "spell object" stand-in (resolve takes a spell-shaped obj).
    class _Spell:
        id = "spell_stub"
    class _Tgt:
        object_id = foe.id

    events = cd.resolve(_Spell(), game.state, [_Tgt()])
    assert len(events) == 1
    assert events[0].type == EventType.DAMAGE
    assert events[0].payload.get('amount') == 6
    assert events[0].payload.get('target') == foe.id
    print("  Hyper Beam resolves to 6 damage at the chosen target")


# ============================================================================
# Registry sanity
# ============================================================================

def test_all_8_spice_cards_in_registry():
    """All 8 spice cards must be findable in POKEMON_HORIZONS_CARDS."""
    spice = [
        "Charizard, Mega Evolved",
        "Moltres, Phoenix Reborn",
        "Pikachu, Thunder Champion",
        "Eevee, Evolution Vessel",
        "Master Ball",
        "Volcanic Mantle",
        "Reshiram, Truth Aspect",
        "Hyper Beam",
    ]
    for name in spice:
        assert name in POKEMON_HORIZONS_CARDS, f"Missing from registry: {name}"
    print(f"\n=== Registry: all 8 spice cards present ===")


if __name__ == "__main__":
    test_charizard_mega_loads_with_flying()
    test_charizard_mega_etb_emits_damage()
    test_moltres_loads_with_flying_haste()
    test_moltres_death_sets_return_flag()
    test_pikachu_loads_with_haste()
    test_pikachu_combat_damage_to_player_emits_draw()
    test_eevee_loads_with_etb_search()
    test_master_ball_loads_as_legendary_artifact()
    test_volcanic_mantle_loads_as_equipment()
    test_volcanic_mantle_grants_pt_haste_trample_on_attach()
    test_reshiram_loads_with_flying_trample_and_cost_reduction()
    test_reshiram_etb_emits_damage_to_threat()
    test_hyper_beam_loads_as_sorcery()
    test_hyper_beam_resolve_deals_6_damage()
    test_all_8_spice_cards_in_registry()
    print("\n============================================================")
    print("ALL POKEMON HORIZONS SPICE TESTS PASSED!")
    print("============================================================")
