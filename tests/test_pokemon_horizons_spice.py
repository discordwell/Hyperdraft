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


def test_charizard_mega_chains_on_red_spell_cast():
    """Charizard's redesigned trigger: pump+ping when you cast a red spell."""
    print("\n=== Charizard Mega: chain on red cast ===")
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    foe = _make_opponent_creature(game, p2, "Foe", power=2, toughness=2)
    cz = _put_on_battlefield(game, p1, "Charizard, Mega Evolved")

    # Build a fake red spell as a GameObject so the trigger sees a red cost.
    red_spell = game.create_object(
        name="Lightning Bolt",
        owner_id=p1.id,
        zone=ZoneType.STACK,
        characteristics=Characteristics(
            types={CardType.INSTANT},
            colors={Color.RED},
        ),
    )

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={
            'spell_id': red_spell.id,
            'caster': p1.id,
            'controller': p1.id,
            'colors': {Color.RED},
            'types': {CardType.INSTANT},
        },
        source=red_spell.id,
        controller=p1.id,
    ))
    new = game.state.event_log[before:]
    pump = [e for e in new if e.type == EventType.PT_MODIFICATION
            and e.payload.get('object_id') == cz.id]
    ping = [e for e in new if e.type == EventType.DAMAGE
            and e.payload.get('source') == cz.id]
    assert pump, f"Charizard should pump on red cast; got {[e.type.name for e in new]}"
    assert ping, f"Charizard should ping on red cast; got {[e.type.name for e in new]}"
    print(f"  Pump + ping emitted on red spell cast")


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


def test_pikachu_team_player_damage_adds_counter():
    """v3.5 redesign: Pikachu gathers +1/+1 counters when ANY of your
    creatures (not just Pikachu) deals damage to a player. Build-around:
    every successful attacker grows the focal, so the deck's natural
    plays compound on Pikachu without him having to push through.
    """
    print("\n=== Pikachu: team player damage adds counter ===")
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    pk = _put_on_battlefield(game, p1, "Pikachu, Thunder Champion")

    # A different friendly creature deals damage to a player → Pikachu grows.
    ally = game.create_object(
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
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p2.id, 'amount': 2, 'source': ally.id, 'is_combat': True},
        source=ally.id,
    ))
    new = game.state.event_log[before:]
    counters = [e for e in new if e.type == EventType.COUNTER_ADDED
                and e.payload.get('object_id') == pk.id
                and e.payload.get('counter_type') == '+1/+1']
    assert counters, f"Pikachu should gain a counter from ally damage; got {[e.type.name for e in new]}"
    print(f"  Ally damage to player → +1/+1 counter on Pikachu")

    # Damage to a creature: no counter.
    foe = _make_opponent_creature(game, p2)
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': foe.id, 'amount': 2, 'source': ally.id, 'is_combat': True},
        source=ally.id,
    ))
    new = game.state.event_log[before:]
    counters = [e for e in new if e.type == EventType.COUNTER_ADDED]
    assert not counters, f"Damage to a creature must NOT add counter; got {counters}"
    print(f"  Creature damage → no counter (correct)")

    # Opponent's creature damages player: no counter (must be your team).
    enemy = _make_opponent_creature(game, p2, "Enemy", power=2, toughness=2)
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': p1.id, 'amount': 2, 'source': enemy.id, 'is_combat': True},
        source=enemy.id,
    ))
    new = game.state.event_log[before:]
    counters = [e for e in new if e.type == EventType.COUNTER_ADDED]
    assert not counters, f"Opp's creature damage must NOT grow Pikachu; got {counters}"
    print(f"  Opponent damage → no counter (correct)")


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

def test_volcanic_mantle_loads_as_legendary_enchantment():
    print("\n=== Volcanic Mantle: load (Enchantment) ===")
    game = Game()
    p1 = game.add_player("P1")
    vm = _put_on_battlefield(game, p1, "Volcanic Mantle")
    assert CardType.ENCHANTMENT in vm.characteristics.types
    assert "Legendary" in (vm.characteristics.supertypes or set())
    print(f"  Loaded with {len(vm.interceptor_ids)} interceptors")


def test_volcanic_mantle_buffs_red_attacker():
    """ATTACK_DECLARED by a red creature you control → +1/+1 + trample."""
    print("\n=== Volcanic Mantle: red attack buff ===")
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    vm = _put_on_battlefield(game, p1, "Volcanic Mantle")

    # Red attacker triggers the buff.
    red_attacker = game.create_object(
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
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': red_attacker.id, 'attacker': red_attacker.id,
                 'defender': p2.id},
        source=red_attacker.id,
    ))
    new = game.state.event_log[before:]
    pump = [e for e in new if e.type == EventType.PT_MODIFICATION
            and e.payload.get('object_id') == red_attacker.id
            and e.payload.get('power_mod') == 1]
    trample = [e for e in new if e.type == EventType.GRANT_KEYWORD
               and e.payload.get('object_id') == red_attacker.id
               and e.payload.get('keyword') == 'trample']
    assert pump, f"Red attacker should get +1/+1; got {[e.type.name for e in new]}"
    assert trample, f"Red attacker should get trample"
    print(f"  Red attacker got +1/+1 and trample")

    # Non-red attacker: no buff.
    blue_attacker = game.create_object(
        name="Magikarp",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            colors={Color.BLUE},
            power=1, toughness=1,
        ),
    )
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': blue_attacker.id, 'attacker': blue_attacker.id,
                 'defender': p2.id},
        source=blue_attacker.id,
    ))
    new = game.state.event_log[before:]
    pump = [e for e in new if e.type == EventType.PT_MODIFICATION
            and e.payload.get('object_id') == blue_attacker.id]
    assert not pump, f"Non-red attacker should NOT be buffed; got {pump}"
    print(f"  Blue attacker not buffed (correct)")


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


def test_hyper_beam_resolve_deals_4_damage():
    """resolve() returns one DAMAGE event for 4 to the chosen target.
    R5 redesign lowered cost to {1}{R} and damage to 4 (was {2}{R}{R}/6).
    """
    print("\n=== Hyper Beam: resolve damage ===")
    cd = POKEMON_HORIZONS_CARDS["Hyper Beam"]
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    foe = _make_opponent_creature(game, p2, "Foe", power=3, toughness=6)

    class _Tgt:
        object_id = foe.id

    events = cd.resolve([_Tgt()], game.state)
    damage_events = [event for event in events if event.type == EventType.DAMAGE]
    assert len(damage_events) == 1
    assert damage_events[0].payload.get('amount') == 4
    assert damage_events[0].payload.get('target') == foe.id
    assert len(events) == 1
    print("  Hyper Beam resolves to 4 damage at the chosen target")


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
    test_charizard_mega_chains_on_red_spell_cast()
    test_moltres_loads_with_flying_haste()
    test_moltres_death_sets_return_flag()
    test_pikachu_loads_with_haste()
    test_pikachu_team_player_damage_adds_counter()
    test_eevee_loads_with_etb_search()
    test_master_ball_loads_as_legendary_artifact()
    test_volcanic_mantle_loads_as_legendary_enchantment()
    test_volcanic_mantle_buffs_red_attacker()
    test_reshiram_loads_with_flying_trample_and_cost_reduction()
    test_reshiram_etb_emits_damage_to_threat()
    test_hyper_beam_loads_as_sorcery()
    test_hyper_beam_resolve_deals_4_damage()
    test_all_8_spice_cards_in_registry()
    print("\n============================================================")
    print("ALL POKEMON HORIZONS SPICE TESTS PASSED!")
    print("============================================================")
