"""
Studio Ghibli Spice Pass Tests (Phase A)

Mirrors test_star_wars_spice.py / test_dragon_ball_spice.py for the third
pilot set. Validates the format-defining-but-atmospheric Ghibli cards.

The Ghibli pilot is the deliberately peaceful one — replacement effects and
soft-lock prisons get the most validation here.
"""

import sys
sys.path.insert(0, '/Users/discordwell/Projects/HYPERDRAFT')

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, Characteristics,
    get_power, get_toughness,
)
from src.cards.custom.studio_ghibli import STUDIO_GHIBLI_CARDS


def _put_on_battlefield(game, player, card_name):
    """Standard pattern: create in hand without card_def, then ZONE_CHANGE."""
    card_def = STUDIO_GHIBLI_CARDS[card_name]
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


def _emitted_types(game):
    return [e.type.name for e in game.state.event_log]


# ============================================================================
# The Forest Watches — replacement effect: opp creatures enter tapped
# ============================================================================

def test_forest_watches_loads_as_legendary_enchantment():
    """Loads as Legendary Enchantment with replacement + upkeep interceptors."""
    print("\n=== Forest Watches: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    fw = _put_on_battlefield(game, p1, "The Forest Watches")
    chars = fw.characteristics
    assert CardType.ENCHANTMENT in chars.types
    assert 'Legendary' in (chars.supertypes or set())
    # Two interceptors: replacement + upkeep trigger.
    assert len(fw.interceptor_ids) >= 2, (
        f"Expected ≥2 interceptors, got {len(fw.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(fw.interceptor_ids)}")


def test_forest_watches_forces_opp_creature_tapped():
    """An opponent's creature entering battlefield is forced tapped."""
    print("\n=== Forest Watches: opp creature enters tapped ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "The Forest Watches")

    # Build an opponent creature and emit ZONE_CHANGE to battlefield untapped.
    opp_creature = game.create_object(
        name="Enemy Wolf",
        owner_id=p2.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            colors={Color.GREEN},
            power=2, toughness=2,
        ),
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': opp_creature.id,
            'from_zone': f'hand_{p2.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
            'tapped': False,
        },
    ))
    # Find the resolved ZONE_CHANGE; tapped should now be True.
    matching = [e for e in game.state.event_log
                if e.type == EventType.ZONE_CHANGE
                and e.payload.get('object_id') == opp_creature.id]
    assert matching, "ZONE_CHANGE not logged"
    assert matching[-1].payload.get('tapped') is True, (
        f"Opp creature should enter tapped; payload={matching[-1].payload}"
    )
    print("  Opp creature forced tapped (correct)")


def test_forest_watches_does_not_tap_own_creatures():
    """Edge: Watches' controller's creatures enter untapped."""
    print("\n=== Forest Watches: own creature untapped (edge) ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "The Forest Watches")
    own = game.create_object(
        name="Friendly Wolf",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            colors={Color.GREEN},
            power=2, toughness=2,
        ),
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': own.id,
            'from_zone': f'hand_{p1.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
            'tapped': False,
        },
    ))
    matching = [e for e in game.state.event_log
                if e.type == EventType.ZONE_CHANGE
                and e.payload.get('object_id') == own.id]
    assert matching, "ZONE_CHANGE not logged"
    assert matching[-1].payload.get('tapped') is not True, (
        f"Own creature should stay untapped: {matching[-1].payload}"
    )
    print("  Own creature untapped (correct)")


def test_forest_watches_upkeep_scry():
    """At controller's upkeep, emits SCRY."""
    print("\n=== Forest Watches: upkeep scry ===")
    game = Game()
    p1 = game.add_player("Alice")
    fw = _put_on_battlefield(game, p1, "The Forest Watches")
    game.state.active_player = p1.id
    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'step': 'upkeep',
                 'active_player': p1.id, 'turn_number': 1},
    ))
    after = _emitted_types(game)
    new = after[len(before):]
    scrys = [e for e in game.state.event_log
             if e.type == EventType.SCRY and e.source == fw.id]
    assert scrys, f"Expected SCRY from Forest Watches; new types: {new}"
    print(f"  SCRY emitted on upkeep")


def test_forest_watches_skips_opp_upkeep():
    """Edge: opponent's upkeep does not fire the scry."""
    print("\n=== Forest Watches: opp upkeep skip ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    fw = _put_on_battlefield(game, p1, "The Forest Watches")
    game.state.active_player = p2.id
    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'step': 'upkeep',
                 'active_player': p2.id, 'turn_number': 1},
    ))
    new_scrys = [e for e in game.state.event_log[len(before_log):]
                 if e.type == EventType.SCRY and e.source == fw.id]
    assert not new_scrys, f"Should not scry on opp upkeep, got: {new_scrys}"
    print("  No scry on opp upkeep (correct)")


# ============================================================================
# Mei's Forest Friend — replacement: dies → spirit token + exile
# ============================================================================

def test_mei_forest_friend_loads():
    """Loads as Legendary Spirit creature."""
    print("\n=== Mei's Forest Friend: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    mei = _put_on_battlefield(game, p1, "Mei's Forest Friend")
    chars = mei.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Spirit' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(mei.interceptor_ids) >= 1
    print(f"  Loaded with {len(mei.interceptor_ids)} interceptors")


def test_mei_forest_friend_replaces_death_with_exile_and_token():
    """When another of your creatures would die, instead exile + create Spirit."""
    print("\n=== Mei's Forest Friend: replacement ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Mei's Forest Friend")

    # Build a soldier creature on battlefield.
    soldier = game.create_object(
        name="Brave Soldier",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Human", "Soldier"},
            colors={Color.WHITE},
            power=2, toughness=2,
        ),
    )
    # Simulate dying via ZONE_CHANGE BF -> GY.
    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': soldier.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    new_events = game.state.event_log[len(before_log):]
    # CREATE_TOKEN should have fired.
    create_tokens = [e for e in new_events if e.type == EventType.CREATE_TOKEN]
    assert create_tokens, f"Expected CREATE_TOKEN replacement, got: {[e.type.name for e in new_events]}"
    # The replacement should redirect to exile.
    soldier_zcs = [e for e in new_events
                   if e.type == EventType.ZONE_CHANGE
                   and e.payload.get('object_id') == soldier.id]
    assert soldier_zcs, "ZONE_CHANGE for soldier missing"
    last = soldier_zcs[-1]
    assert last.payload.get('to_zone_type') == ZoneType.EXILE, (
        f"Replacement should redirect to exile; got {last.payload.get('to_zone_type')}"
    )
    print(f"  Death replaced: exile + Spirit token created")


def test_mei_forest_friend_only_fires_once_per_turn():
    """Edge: second creature death in same turn is NOT replaced."""
    print("\n=== Mei's Forest Friend: once-per-turn ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Mei's Forest Friend")

    def _death(name):
        c = game.create_object(
            name=name,
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(
                types={CardType.CREATURE},
                subtypes={"Human"},
                power=1, toughness=1,
            ),
        )
        before_log = list(game.state.event_log)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': c.id,
                'from_zone': 'battlefield',
                'from_zone_type': ZoneType.BATTLEFIELD,
                'to_zone': f'graveyard_{p1.id}',
                'to_zone_type': ZoneType.GRAVEYARD,
            },
        ))
        return c, game.state.event_log[len(before_log):]

    # First death: should be replaced.
    c1, new1 = _death("First Soldier")
    tokens1 = [e for e in new1 if e.type == EventType.CREATE_TOKEN]
    assert tokens1, "First death should fire replacement"

    # Second death: should NOT be replaced (no second token).
    c2, new2 = _death("Second Soldier")
    tokens2 = [e for e in new2 if e.type == EventType.CREATE_TOKEN]
    assert not tokens2, (
        f"Second death same turn should not fire replacement, got {tokens2}"
    )
    print(f"  Once-per-turn gate works: first death replaced, second not")


def test_mei_forest_friend_does_not_replace_opp_death():
    """Edge: opponent's creature dying does NOT trigger Mei's replacement."""
    print("\n=== Mei's Forest Friend: opp death edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Mei's Forest Friend")
    enemy = game.create_object(
        name="Enemy Wolf",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            power=2, toughness=2,
        ),
    )
    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': enemy.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p2.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    new = game.state.event_log[len(before_log):]
    tokens = [e for e in new if e.type == EventType.CREATE_TOKEN]
    assert not tokens, (
        f"Opp creature death should not fire Mei's replacement; got {tokens}"
    )
    print("  Opp death not replaced (correct)")


# ============================================================================
# Howl's Moving Castle, Wandering Heart
# ============================================================================

def test_howls_castle_loads_as_artifact_creature():
    """Castle is an Artifact + Creature with Castle subtype."""
    print("\n=== Howl's Castle: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    castle = _put_on_battlefield(game, p1, "Howl's Moving Castle, Wandering Heart")
    chars = castle.characteristics
    assert CardType.ARTIFACT in chars.types
    assert CardType.CREATURE in chars.types
    assert 'Castle' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    abilities = getattr(castle.state, 'activated_abilities', [])
    assert len(abilities) >= 1, (
        f"Expected at least 1 activated ability, got {len(abilities)}"
    )
    print(f"  Loaded with {len(abilities)} activated abilities")


def test_howls_castle_carry_effect_pumps_target():
    """Activated effect: target friendly creature gets +3/+3 + flying EOT."""
    print("\n=== Howl's Castle: carry effect ===")
    game = Game()
    p1 = game.add_player("Alice")
    castle = _put_on_battlefield(game, p1, "Howl's Moving Castle, Wandering Heart")

    target = game.create_object(
        name="Mei",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Human"},
            colors={Color.GREEN},
            power=1, toughness=1,
        ),
    )

    abilities = castle.state.activated_abilities or []
    carry = next(
        (a for a in abilities if a.cost_text and '{2}' in a.cost_text and '{T}' in a.cost_text),
        None,
    )
    assert carry is not None, f"Carry ability not found among {[a.cost_text for a in abilities]}"
    # Make a fake target wrapper.
    class FakeTarget:
        def __init__(self, oid): self.object_id = oid
    events = carry.effect_fn(castle, game.state, [FakeTarget(target.id)])
    pt_mods = [e for e in events if e.type == EventType.PT_MODIFICATION]
    keyword_grants = [e for e in events if e.type == EventType.GRANT_KEYWORD]
    assert pt_mods, "Carry should emit PT_MODIFICATION"
    assert pt_mods[0].payload.get('power_mod') == 3
    assert pt_mods[0].payload.get('toughness_mod') == 3
    assert keyword_grants, "Carry should emit GRANT_KEYWORD"
    assert keyword_grants[0].payload.get('keyword') == 'flying'
    print(f"  +3/+3 + flying granted to target")


def test_howls_castle_carry_rejects_opp_creature():
    """Edge: cannot carry an opponent's creature."""
    print("\n=== Howl's Castle: opp creature edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    castle = _put_on_battlefield(game, p1, "Howl's Moving Castle, Wandering Heart")
    enemy = game.create_object(
        name="Enemy",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            power=2, toughness=2,
        ),
    )
    abilities = castle.state.activated_abilities or []
    carry = next(
        (a for a in abilities if a.cost_text and '{2}' in a.cost_text and '{T}' in a.cost_text),
        None,
    )
    class FakeTarget:
        def __init__(self, oid): self.object_id = oid
    events = carry.effect_fn(castle, game.state, [FakeTarget(enemy.id)])
    assert not events, f"Carry should reject opp creature; got {events}"
    print("  Carry correctly rejected opp creature")


# ============================================================================
# Catbus, Wind-Carrier of the Forest
# ============================================================================

def test_catbus_wind_carrier_loads_with_haste():
    """Catbus loads with haste self-grant + attack trigger."""
    print("\n=== Catbus Wind-Carrier: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    cat = _put_on_battlefield(game, p1, "Catbus, Wind-Carrier of the Forest")
    chars = cat.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Spirit' in chars.subtypes
    # Two interceptors: keyword grant + attack trigger.
    assert len(cat.interceptor_ids) >= 2
    print(f"  Loaded with {len(cat.interceptor_ids)} interceptors")


def test_catbus_attack_grants_passenger_haste_and_unblockable():
    """Attack trigger picks a friendly creature and gives haste + unblockable."""
    print("\n=== Catbus: attack passenger ===")
    game = Game()
    p1 = game.add_player("Alice")
    cat = _put_on_battlefield(game, p1, "Catbus, Wind-Carrier of the Forest")
    passenger = game.create_object(
        name="Tiny Friend",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Spirit"},
            colors={Color.GREEN},
            power=1, toughness=1,
        ),
    )
    # Tap the passenger so we can verify the untap.
    passenger.state.tapped = True

    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': cat.id, 'attacker': cat.id, 'defender': 'opponent'},
        source=cat.id,
    ))
    new = game.state.event_log[len(before_log):]
    untaps = [e for e in new if e.type == EventType.UNTAP
              and e.payload.get('object_id') == passenger.id]
    haste_grants = [e for e in new if e.type == EventType.GRANT_KEYWORD
                    and e.payload.get('object_id') == passenger.id
                    and e.payload.get('keyword') == 'haste']
    unblockable_grants = [e for e in new if e.type == EventType.GRANT_KEYWORD
                          and e.payload.get('object_id') == passenger.id
                          and e.payload.get('keyword') == 'unblockable']
    assert untaps, f"UNTAP for passenger missing: {[e.type.name for e in new]}"
    assert haste_grants, f"GRANT_KEYWORD haste missing"
    assert unblockable_grants, f"GRANT_KEYWORD unblockable missing"
    print(f"  Passenger got untap + haste + unblockable")


def test_catbus_attack_no_passenger_no_events():
    """Edge: if no other friendly creature, no untap/grant events."""
    print("\n=== Catbus: alone-attack edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    cat = _put_on_battlefield(game, p1, "Catbus, Wind-Carrier of the Forest")
    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': cat.id, 'attacker': cat.id, 'defender': 'opponent'},
        source=cat.id,
    ))
    new = game.state.event_log[len(before_log):]
    # Can't be any UNTAP / GRANT_KEYWORD attributable to passenger movement.
    relevant = [e for e in new
                if e.source == cat.id
                and e.type in (EventType.UNTAP, EventType.GRANT_KEYWORD)]
    assert not relevant, f"Should be no passenger events with no friendlies; got {relevant}"
    print("  No passenger events when alone (correct)")


# ============================================================================
# The World Tree's Gift — modal-by-state
# ============================================================================

def test_world_tree_gift_loads():
    """Loads as Legendary Enchantment with upkeep trigger."""
    print("\n=== World Tree's Gift: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    wt = _put_on_battlefield(game, p1, "The World Tree's Gift")
    chars = wt.characteristics
    assert CardType.ENCHANTMENT in chars.types
    assert 'Legendary' in (chars.supertypes or set())
    assert len(wt.interceptor_ids) >= 1
    print(f"  Loaded with {len(wt.interceptor_ids)} interceptors")


def test_world_tree_gift_low_life_gain_2():
    """Low life (≤10) → gain 2 life (LIFE_CHANGE)."""
    print("\n=== World Tree's Gift: low-life mode ===")
    game = Game()
    p1 = game.add_player("Alice")
    wt = _put_on_battlefield(game, p1, "The World Tree's Gift")
    p1.life = 8
    game.state.active_player = p1.id
    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'step': 'upkeep',
                 'active_player': p1.id, 'turn_number': 1},
    ))
    new = game.state.event_log[len(before_log):]
    life_events = [e for e in new if e.type == EventType.LIFE_CHANGE
                   and e.source == wt.id
                   and e.payload.get('amount') == 2]
    assert life_events, f"Expected gain-2-life event: {[e.type.name for e in new]}"
    print(f"  Gain 2 life triggered at low life")


def test_world_tree_gift_high_life_untap_forest():
    """High life (≥16) + tapped Forest → untap forest."""
    print("\n=== World Tree's Gift: high-life untap mode ===")
    game = Game()
    p1 = game.add_player("Alice")
    wt = _put_on_battlefield(game, p1, "The World Tree's Gift")
    forest = game.create_object(
        name="Forest",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.LAND},
            subtypes={"Forest"},
            supertypes={"Basic"},
        ),
    )
    forest.state.tapped = True
    p1.life = 20
    game.state.active_player = p1.id
    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'step': 'upkeep',
                 'active_player': p1.id, 'turn_number': 1},
    ))
    new = game.state.event_log[len(before_log):]
    untaps = [e for e in new if e.type == EventType.UNTAP
              and e.payload.get('object_id') == forest.id]
    assert untaps, f"Expected forest UNTAP at high life: {[e.type.name for e in new]}"
    print("  Forest untapped at high life")


def test_world_tree_gift_default_scry():
    """Mid life and no tapped Forest → scry 2 (default)."""
    print("\n=== World Tree's Gift: default scry mode ===")
    game = Game()
    p1 = game.add_player("Alice")
    wt = _put_on_battlefield(game, p1, "The World Tree's Gift")
    p1.life = 13  # mid-range
    game.state.active_player = p1.id
    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'step': 'upkeep',
                 'active_player': p1.id, 'turn_number': 1},
    ))
    new = game.state.event_log[len(before_log):]
    scrys = [e for e in new if e.type == EventType.SCRY
             and e.source == wt.id
             and e.payload.get('amount') == 2]
    assert scrys, f"Expected scry 2 default: {[e.type.name for e in new]}"
    print("  Scry 2 default mode triggered")


# ============================================================================
# Ascension of the Spirits — lord with threshold flying
# ============================================================================

def test_ascension_of_spirits_loads():
    """Loads as Enchantment, registers lord interceptors."""
    print("\n=== Ascension of the Spirits: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    asc = _put_on_battlefield(game, p1, "Ascension of the Spirits")
    chars = asc.characteristics
    assert CardType.ENCHANTMENT in chars.types
    # Three interceptors: power lord, toughness lord, threshold flying grant.
    assert len(asc.interceptor_ids) >= 3, (
        f"Expected ≥3 interceptors, got {len(asc.interceptor_ids)}"
    )
    print(f"  Loaded with {len(asc.interceptor_ids)} interceptors")


def test_ascension_pumps_spirits():
    """Spirits get +1/+1 from Ascension."""
    print("\n=== Ascension: spirits pumped ===")
    game = Game()
    p1 = game.add_player("Alice")
    spirit = game.create_object(
        name="Tiny Spirit",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Spirit"},
            power=1, toughness=1,
        ),
    )
    base_p = get_power(spirit, game.state)
    base_t = get_toughness(spirit, game.state)
    _put_on_battlefield(game, p1, "Ascension of the Spirits")
    new_p = get_power(spirit, game.state)
    new_t = get_toughness(spirit, game.state)
    assert new_p == base_p + 1, f"Expected +1 power: {base_p}→{new_p}"
    assert new_t == base_t + 1, f"Expected +1 toughness: {base_t}→{new_t}"
    print(f"  Spirit P/T: {base_p}/{base_t} → {new_p}/{new_t}")


def test_ascension_threshold_grants_flying_at_5_spirits():
    """When 5+ spirits are out, all spirits get flying."""
    print("\n=== Ascension: threshold flying ===")
    game = Game()
    p1 = game.add_player("Alice")
    asc = _put_on_battlefield(game, p1, "Ascension of the Spirits")

    spirits = []
    for i in range(5):
        s = game.create_object(
            name=f"Spirit {i}",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(
                types={CardType.CREATURE},
                subtypes={"Spirit"},
                power=1, toughness=1,
            ),
        )
        spirits.append(s)

    # Now query keywords on the first spirit. Should include 'flying'.
    from src.engine.queries import has_ability
    assert has_ability(spirits[0], 'flying', game.state), (
        f"Expected flying at 5 spirits"
    )
    print(f"  Flying granted at 5 spirits")


def test_ascension_no_flying_below_threshold():
    """Edge: with only 3 spirits, NO flying grant."""
    print("\n=== Ascension: below-threshold edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    asc = _put_on_battlefield(game, p1, "Ascension of the Spirits")

    spirits = []
    for i in range(3):
        s = game.create_object(
            name=f"Spirit {i}",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(
                types={CardType.CREATURE},
                subtypes={"Spirit"},
                power=1, toughness=1,
            ),
        )
        spirits.append(s)

    from src.engine.queries import has_ability
    assert not has_ability(spirits[0], 'flying', game.state), (
        f"Should NOT have flying below 5 spirits"
    )
    print(f"  No flying below threshold (correct)")


# ============================================================================
# Calcifer's Hearth-Pact — value engine
# ============================================================================

def test_calcifer_hearth_pact_loads():
    """Calcifer loads as Legendary Enchantment with two triggers."""
    print("\n=== Calcifer's Hearth-Pact: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    calc = _put_on_battlefield(game, p1, "Calcifer's Hearth-Pact")
    chars = calc.characteristics
    assert CardType.ENCHANTMENT in chars.types
    assert 'Legendary' in (chars.supertypes or set())
    assert len(calc.interceptor_ids) >= 2
    print(f"  Loaded with {len(calc.interceptor_ids)} interceptors")


def test_calcifer_hearth_pact_lifegain_on_cast():
    """Casting a spell triggers +1 life."""
    print("\n=== Calcifer: lifegain on cast ===")
    game = Game()
    p1 = game.add_player("Alice")
    calc = _put_on_battlefield(game, p1, "Calcifer's Hearth-Pact")
    p1_before = p1.life
    # Emit a fake CAST event.
    game.emit(Event(
        type=EventType.CAST,
        payload={
            'caster': p1.id,
            'controller': p1.id,
            'spell_id': 'fake_spell',
            'mana_value': 2,
        },
        controller=p1.id,
    ))
    assert p1.life == p1_before + 1, (
        f"Expected +1 life on cast: {p1_before}→{p1.life}"
    )
    print(f"  Life {p1_before} → {p1.life} on cast")


def test_calcifer_hearth_pact_no_lifegain_on_opp_cast():
    """Edge: opponent casting does NOT trigger Calcifer's lifegain."""
    print("\n=== Calcifer: no lifegain on opp cast ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    calc = _put_on_battlefield(game, p1, "Calcifer's Hearth-Pact")
    p1_before = p1.life
    game.emit(Event(
        type=EventType.CAST,
        payload={
            'caster': p2.id,
            'controller': p2.id,
            'spell_id': 'fake_spell_opp',
            'mana_value': 2,
        },
        controller=p2.id,
    ))
    assert p1.life == p1_before, (
        f"Should not gain life on opp cast: {p1_before}→{p1.life}"
    )
    print(f"  Life unchanged on opp cast (correct)")


def test_calcifer_hearth_pact_end_step_damage():
    """At end step, deals 1 damage to an opponent."""
    print("\n=== Calcifer: end-step damage ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    calc = _put_on_battlefield(game, p1, "Calcifer's Hearth-Pact")
    game.state.active_player = p1.id
    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'step': 'end_step',
                 'active_player': p1.id, 'turn_number': 1},
    ))
    new = game.state.event_log[len(before_log):]
    dmgs = [e for e in new if e.type == EventType.DAMAGE
            and e.source == calc.id
            and e.payload.get('target') == p2.id
            and e.payload.get('amount') == 1]
    assert dmgs, f"Expected 1 damage to opp at end step: {[e.type.name for e in new]}"
    print(f"  Calcifer pinged opp for 1 at end step")


# ============================================================================
# Granmamare's Hospitality — replacement on opp draw
# ============================================================================

def test_granmamare_loads_as_legendary_enchantment():
    """Granmamare loads as Legendary Enchantment."""
    print("\n=== Granmamare's Hospitality: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    gran = _put_on_battlefield(game, p1, "Granmamare's Hospitality")
    chars = gran.characteristics
    assert CardType.ENCHANTMENT in chars.types
    assert 'Legendary' in (chars.supertypes or set())
    assert len(gran.interceptor_ids) >= 1
    print(f"  Loaded with {len(gran.interceptor_ids)} interceptors")


def test_granmamare_replaces_opp_draw_when_top_is_creature():
    """Opp draw → top is creature → exile + Spirit token for you."""
    print("\n=== Granmamare: opp draw creature ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    gran = _put_on_battlefield(game, p1, "Granmamare's Hospitality")

    # Build a creature card on top of Bob's library.
    creature = game.create_object(
        name="Bob's Creature",
        owner_id=p2.id,
        zone=ZoneType.LIBRARY,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            colors={Color.GREEN},
            power=2, toughness=2,
        ),
    )
    library = game.state.zones.get(f'library_{p2.id}')
    if creature.id in library.objects:
        library.objects.remove(creature.id)
    library.objects.insert(0, creature.id)

    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p2.id, 'count': 1},
    ))
    new = game.state.event_log[len(before_log):]
    exiles = [e for e in new if e.type == EventType.EXILE
              and e.payload.get('object_id') == creature.id]
    tokens = [e for e in new if e.type == EventType.CREATE_TOKEN
              and e.source == gran.id]
    assert exiles, f"Expected EXILE of opp's top creature: {[e.type.name for e in new]}"
    assert tokens, f"Expected Spirit CREATE_TOKEN: {[e.type.name for e in new]}"
    print(f"  Opp's top creature exiled, Spirit token created")


def test_granmamare_lets_noncreature_through():
    """Edge: opp draw, top is non-creature → no replacement (let it draw)."""
    print("\n=== Granmamare: non-creature pass-through ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    gran = _put_on_battlefield(game, p1, "Granmamare's Hospitality")

    instant = game.create_object(
        name="Bob's Instant",
        owner_id=p2.id,
        zone=ZoneType.LIBRARY,
        characteristics=Characteristics(
            types={CardType.INSTANT},
            colors={Color.RED},
        ),
    )
    library = game.state.zones.get(f'library_{p2.id}')
    if instant.id in library.objects:
        library.objects.remove(instant.id)
    library.objects.insert(0, instant.id)

    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p2.id, 'count': 1},
    ))
    new = game.state.event_log[len(before_log):]
    # No exile of the instant, no Granmamare token.
    exiles = [e for e in new if e.type == EventType.EXILE
              and e.payload.get('object_id') == instant.id]
    tokens = [e for e in new if e.type == EventType.CREATE_TOKEN
              and e.source == gran.id]
    assert not exiles, f"Non-creature should not be exiled; got {exiles}"
    assert not tokens, f"No Spirit token for non-creature; got {tokens}"
    print(f"  Non-creature draw passes through (correct)")


def test_granmamare_only_first_draw_per_turn():
    """Edge: only the first draw each turn per opponent is replaced."""
    print("\n=== Granmamare: once-per-turn ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    gran = _put_on_battlefield(game, p1, "Granmamare's Hospitality")

    def _stack_creature(name):
        c = game.create_object(
            name=name,
            owner_id=p2.id,
            zone=ZoneType.LIBRARY,
            characteristics=Characteristics(
                types={CardType.CREATURE},
                subtypes={"Spirit"},
                power=1, toughness=1,
            ),
        )
        library = game.state.zones.get(f'library_{p2.id}')
        if c.id in library.objects:
            library.objects.remove(c.id)
        library.objects.insert(0, c.id)
        return c

    # First draw: replace.
    c1 = _stack_creature("First Creature")
    before1 = list(game.state.event_log)
    game.emit(Event(type=EventType.DRAW, payload={'player': p2.id, 'count': 1}))
    new1 = game.state.event_log[len(before1):]
    tokens1 = [e for e in new1 if e.type == EventType.CREATE_TOKEN
               and e.source == gran.id]
    assert tokens1, f"First draw should fire replacement"

    # Second draw: NO replace (same turn).
    c2 = _stack_creature("Second Creature")
    before2 = list(game.state.event_log)
    game.emit(Event(type=EventType.DRAW, payload={'player': p2.id, 'count': 1}))
    new2 = game.state.event_log[len(before2):]
    tokens2 = [e for e in new2 if e.type == EventType.CREATE_TOKEN
               and e.source == gran.id]
    assert not tokens2, f"Second draw same turn should NOT fire: {tokens2}"
    print("  Once-per-turn-per-opponent works")


def test_granmamare_does_not_replace_own_draw():
    """Edge: Granmamare's controller's own draw is not replaced."""
    print("\n=== Granmamare: own draw edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    gran = _put_on_battlefield(game, p1, "Granmamare's Hospitality")

    # Stack a creature on Alice's library.
    creature = game.create_object(
        name="Alice's Creature",
        owner_id=p1.id,
        zone=ZoneType.LIBRARY,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            power=2, toughness=2,
        ),
    )
    library = game.state.zones.get(f'library_{p1.id}')
    if creature.id in library.objects:
        library.objects.remove(creature.id)
    library.objects.insert(0, creature.id)

    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'count': 1},
    ))
    new = game.state.event_log[len(before_log):]
    exiles = [e for e in new if e.type == EventType.EXILE
              and e.payload.get('object_id') == creature.id]
    tokens = [e for e in new if e.type == EventType.CREATE_TOKEN
              and e.source == gran.id]
    assert not exiles, f"Own draw should not be exiled; got {exiles}"
    assert not tokens, f"No Spirit on own draw; got {tokens}"
    print(f"  Own draw passes through (correct)")


# ============================================================================
# Smoke test that all cards register correctly
# ============================================================================

def test_all_spice_cards_register():
    """All eight spice cards are in STUDIO_GHIBLI_CARDS."""
    print("\n=== Registry smoke ===")
    expected = [
        "The Forest Watches",
        "Mei's Forest Friend",
        "Howl's Moving Castle, Wandering Heart",
        "Catbus, Wind-Carrier of the Forest",
        "The World Tree's Gift",
        "Ascension of the Spirits",
        "Calcifer's Hearth-Pact",
        "Granmamare's Hospitality",
    ]
    for name in expected:
        assert name in STUDIO_GHIBLI_CARDS, f"Missing in registry: {name}"
    print(f"  All {len(expected)} spice cards present")


if __name__ == "__main__":
    test_forest_watches_loads_as_legendary_enchantment()
    test_forest_watches_forces_opp_creature_tapped()
    test_forest_watches_does_not_tap_own_creatures()
    test_forest_watches_upkeep_scry()
    test_forest_watches_skips_opp_upkeep()
    test_mei_forest_friend_loads()
    test_mei_forest_friend_replaces_death_with_exile_and_token()
    test_mei_forest_friend_only_fires_once_per_turn()
    test_mei_forest_friend_does_not_replace_opp_death()
    test_howls_castle_loads_as_artifact_creature()
    test_howls_castle_carry_effect_pumps_target()
    test_howls_castle_carry_rejects_opp_creature()
    test_catbus_wind_carrier_loads_with_haste()
    test_catbus_attack_grants_passenger_haste_and_unblockable()
    test_catbus_attack_no_passenger_no_events()
    test_world_tree_gift_loads()
    test_world_tree_gift_low_life_gain_2()
    test_world_tree_gift_high_life_untap_forest()
    test_world_tree_gift_default_scry()
    test_ascension_of_spirits_loads()
    test_ascension_pumps_spirits()
    test_ascension_threshold_grants_flying_at_5_spirits()
    test_ascension_no_flying_below_threshold()
    test_calcifer_hearth_pact_loads()
    test_calcifer_hearth_pact_lifegain_on_cast()
    test_calcifer_hearth_pact_no_lifegain_on_opp_cast()
    test_calcifer_hearth_pact_end_step_damage()
    test_granmamare_loads_as_legendary_enchantment()
    test_granmamare_replaces_opp_draw_when_top_is_creature()
    test_granmamare_lets_noncreature_through()
    test_granmamare_only_first_draw_per_turn()
    test_granmamare_does_not_replace_own_draw()
    test_all_spice_cards_register()
    print("\n" + "=" * 60)
    print("ALL STUDIO GHIBLI SPICE TESTS PASSED!")
    print("=" * 60)
