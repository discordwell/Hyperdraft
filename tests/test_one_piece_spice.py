"""
One Piece: Grand Line Spice Pass Tests (Phase A)

Mirrors test_star_wars_spice.py / test_dragon_ball_spice.py for the third
pilot set. Validates the format-defining cards added in the Phase A spice
pass — Luffy/Zoro/Sanji captains, Crocodile asymmetric prison, Buggy
recursion, Wanted Poster crime escalator, Devil Fruit tutor, Fish-Man
tribal seat, Treasure-sac extra-turn payoff.
"""

import sys
sys.path.insert(0, '/Users/discordwell/Projects/HYPERDRAFT')

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Characteristics, get_power, get_toughness,
)
from src.cards.custom.one_piece import ONE_PIECE_CARDS


def _put_on_battlefield(game, player, card_name):
    """Standard pattern: create in hand without card_def, then ZONE_CHANGE.

    Why we don't pass card_def to create_object: ``create_object`` runs
    ``setup_interceptors`` for objects entering BATTLEFIELD/COMMAND. Putting
    the card in HAND first with no card_def skips that, then the ZONE_CHANGE
    to battlefield runs setup exactly once (the correct path).
    """
    card_def = ONE_PIECE_CARDS[card_name]
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
    """Snapshot of EventType names that have been logged."""
    return [e.type.name for e in game.state.event_log]


# ============================================================================
# Monkey D. Luffy, King of the Pirates
# ============================================================================

def test_luffy_king_loads_legendary_pirate():
    """Loads as a legendary creature with Pirate subtype + 4/5 stats."""
    print("\n=== Luffy KOTP: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    luffy = _put_on_battlefield(game, p1, "Monkey D. Luffy, King of the Pirates")
    chars = luffy.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Pirate' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    print(f"  Subtypes={chars.subtypes}, supertypes={chars.supertypes}")


def test_luffy_etb_taps_opp_creatures():
    """Conqueror's Haki ETB: each opp creature gets a TAP event."""
    print("\n=== Luffy KOTP: ETB Conqueror's Haki ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Drop two opp creatures.
    for _ in range(2):
        game.create_object(
            name="Foe",
            owner_id=p2.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(
                types={CardType.CREATURE},
                colors={Color.RED},
                power=2, toughness=2,
            ),
        )
    before = _emitted_types(game)
    _put_on_battlefield(game, p1, "Monkey D. Luffy, King of the Pirates")
    after = _emitted_types(game)
    new = after[len(before):]
    assert new.count('TAP') >= 2, f"Expected ≥2 TAP events: {new}"
    print(f"  TAP events emitted: {new.count('TAP')}")


def test_luffy_lord_buffs_other_pirates_not_self():
    """Other Pirates +1/+1 — Luffy himself doesn't self-buff."""
    print("\n=== Luffy KOTP: lord effect ===")
    game = Game()
    p1 = game.add_player("Alice")
    luffy = _put_on_battlefield(game, p1, "Monkey D. Luffy, King of the Pirates")
    pirate = _put_on_battlefield(game, p1, "East Blue Pirate")  # 2/1
    # Pirate should now read 3/2.
    p_power = get_power(pirate, game.state)
    p_tough = get_toughness(pirate, game.state)
    assert p_power == 3, f"Expected power 3, got {p_power}"
    assert p_tough == 2, f"Expected toughness 2, got {p_tough}"
    # Luffy should remain 4/5 — lord must not self-buff.
    l_power = get_power(luffy, game.state)
    l_tough = get_toughness(luffy, game.state)
    assert l_power == 4, f"Luffy self-buffed: power={l_power}"
    assert l_tough == 5, f"Luffy self-buffed: toughness={l_tough}"
    print(f"  Pirate {p_power}/{p_tough}; Luffy {l_power}/{l_tough}")


def test_luffy_threaten_requires_three_treasures():
    """The threaten activated ability returns no events when fewer than
    three Treasures are sacrificable. Edge case = scarce Treasure."""
    print("\n=== Luffy KOTP: threaten gating ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    luffy = _put_on_battlefield(game, p1, "Monkey D. Luffy, King of the Pirates")
    # Create a target opp creature.
    foe = game.create_object(
        name="Foe",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=2, toughness=2),
    )
    foe.controller = p2.id
    # Find the threaten ability.
    abilities = luffy.state.activated_abilities or []
    threaten = next((a for a in abilities if 'sacrifice three' in (a.description or '').lower()), None)
    assert threaten is not None, f"Threaten ability not found among {[a.description for a in abilities]}"

    class _T:
        def __init__(self, oid):
            self.object_id = oid

    # No treasures: no events.
    events = threaten.effect_fn(luffy, game.state, [_T(foe.id)])
    assert events == [], f"Should return [] without treasures: {events}"
    print("  No-treasure path correctly returns []")


# ============================================================================
# Roronoa Zoro, Demon of East Blue
# ============================================================================

def test_zoro_demon_loads_with_first_strike():
    """Loads with self-keyword interceptors registered (≥1 keyword grant + ETB
    + attach trigger)."""
    print("\n=== Zoro Demon: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    zoro = _put_on_battlefield(game, p1, "Roronoa Zoro, Demon of East Blue")
    assert len(zoro.interceptor_ids) >= 3, (
        f"Expected ≥3 interceptors (kw grant + ETB + attach); got {len(zoro.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(zoro.interceptor_ids)}")


def test_zoro_demon_etb_emits_search_for_sword():
    """ETB emits SEARCH_LIBRARY with subtypes_any covering Sword/Equipment."""
    print("\n=== Zoro Demon: ETB tutor ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = _emitted_types(game)
    zoro = _put_on_battlefield(game, p1, "Roronoa Zoro, Demon of East Blue")
    after = _emitted_types(game)
    new = after[len(before):]
    assert 'SEARCH_LIBRARY' in new, f"SEARCH_LIBRARY not emitted: {new}"
    sl = [e for e in game.state.event_log
          if e.type == EventType.SEARCH_LIBRARY and e.source == zoro.id]
    assert sl, "ETB SEARCH_LIBRARY missing"
    payload = sl[-1].payload
    subs = payload.get('subtypes_any') or [payload.get('subtype')]
    assert 'Sword' in subs or 'Equipment' in subs, f"Tutor not for Sword/Equipment: {payload}"
    print(f"  Tutor payload: {payload}")


def test_zoro_demon_attach_grants_double_strike():
    """When a Sword/Equipment becomes attached, Zoro untaps + double strike EOT."""
    print("\n=== Zoro Demon: Sword attach trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    zoro = _put_on_battlefield(game, p1, "Roronoa Zoro, Demon of East Blue")
    zoro.state.tapped = True
    sword = game.create_object(
        name="Wado Ichimonji",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.ARTIFACT}, subtypes={"Equipment", "Sword"},
        ),
    )
    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'source': sword.id, 'target': zoro.id},
        source=sword.id,
    ))
    after = _emitted_types(game)
    new = after[len(before):]
    assert 'UNTAP' in new, f"UNTAP not emitted: {new}"
    assert 'GRANT_KEYWORD' in new, f"GRANT_KEYWORD not emitted: {new}"
    gks = [e for e in game.state.event_log
           if e.type == EventType.GRANT_KEYWORD and e.payload.get('object_id') == zoro.id]
    assert gks and gks[-1].payload.get('keyword') == 'double_strike'
    print("  UNTAP + double_strike grant on attach")


# ============================================================================
# Sanji, Cook of the Sea
# ============================================================================

def test_sanji_etb_creates_food():
    """ETB emits a CREATE_TOKEN for Food."""
    print("\n=== Sanji COTS: ETB food ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = _emitted_types(game)
    sanji = _put_on_battlefield(game, p1, "Sanji, Cook of the Sea")
    after = _emitted_types(game)
    new = after[len(before):]
    assert 'CREATE_TOKEN' in new, f"CREATE_TOKEN missing: {new}"
    cts = [e for e in game.state.event_log
           if e.type == EventType.CREATE_TOKEN and e.source == sanji.id]
    assert cts and 'Food' in (cts[-1].payload.get('token') or {}).get('subtypes', set())
    print(f"  Food token created on ETB")


def test_sanji_attack_creates_food():
    """Attack trigger creates another Food token."""
    print("\n=== Sanji COTS: attack food ===")
    game = Game()
    p1 = game.add_player("Alice")
    sanji = _put_on_battlefield(game, p1, "Sanji, Cook of the Sea")
    before = len([e for e in game.state.event_log if e.type == EventType.CREATE_TOKEN])
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': sanji.id},
        source=sanji.id,
    ))
    after = len([e for e in game.state.event_log if e.type == EventType.CREATE_TOKEN])
    assert after >= before + 1, f"Attack didn't add a CREATE_TOKEN: {before}→{after}"
    print(f"  CREATE_TOKEN count {before}→{after}")


def test_sanji_attack_does_not_trigger_for_other_attacker():
    """Edge: another creature attacking does NOT mint Sanji's Food."""
    print("\n=== Sanji COTS: other attacker edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    sanji = _put_on_battlefield(game, p1, "Sanji, Cook of the Sea")
    other = _put_on_battlefield(game, p1, "East Blue Pirate")
    before = len([e for e in game.state.event_log
                  if e.type == EventType.CREATE_TOKEN and e.source == sanji.id])
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': other.id},
        source=other.id,
    ))
    after = len([e for e in game.state.event_log
                 if e.type == EventType.CREATE_TOKEN and e.source == sanji.id])
    assert after == before, f"Other attacker should not mint Sanji food: {before}→{after}"
    print("  Other-attacker correctly suppressed")


# ============================================================================
# Crocodile, Sandstorm of Alabasta
# ============================================================================

def test_crocodile_loads_with_replacement_and_crime_trigger():
    """Loads with at least 2 interceptors (replacement + crime trigger)."""
    print("\n=== Crocodile: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    croc = _put_on_battlefield(game, p1, "Crocodile, Sandstorm of Alabasta")
    assert len(croc.interceptor_ids) >= 2, (
        f"Expected ≥2 interceptors; got {len(croc.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(croc.interceptor_ids)}")


def test_crocodile_taps_opp_lands():
    """Replacement effect: opponents' lands ETB tapped."""
    print("\n=== Crocodile: opp-land replacement ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Crocodile, Sandstorm of Alabasta")
    # Drop an opponent land.
    land = game.create_object(
        name="Opp Forest",
        owner_id=p2.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(types={CardType.LAND}, subtypes={"Forest"}),
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': land.id,
            'from_zone': f'hand_{p2.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    # The replacement should rewrite the event to set tapped=True. The
    # land-place handler reads payload['tapped'] and sets state.tapped on
    # the object. We verify by inspecting the emitted ZONE_CHANGE in the log.
    zc = [e for e in game.state.event_log
          if e.type == EventType.ZONE_CHANGE
          and e.payload.get('object_id') == land.id
          and e.payload.get('to_zone_type') == ZoneType.BATTLEFIELD]
    assert zc, "ZONE_CHANGE for opp land not found"
    assert zc[-1].payload.get('tapped') is True, (
        f"Opp land should have tapped=True: {zc[-1].payload}"
    )
    print("  Opp land entered tapped (correct)")


def test_crocodile_self_lands_unaffected():
    """Edge: my own land is NOT forced tapped by Crocodile."""
    print("\n=== Crocodile: own-land edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Crocodile, Sandstorm of Alabasta")
    land = game.create_object(
        name="My Forest",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(types={CardType.LAND}, subtypes={"Forest"}),
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': land.id,
            'from_zone': f'hand_{p1.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    zc = [e for e in game.state.event_log
          if e.type == EventType.ZONE_CHANGE
          and e.payload.get('object_id') == land.id
          and e.payload.get('to_zone_type') == ZoneType.BATTLEFIELD]
    assert zc, "ZONE_CHANGE not found"
    assert not zc[-1].payload.get('tapped'), (
        f"Own land should not be forced tapped: {zc[-1].payload}"
    )
    print("  Own land entered untapped (correct)")


def test_crocodile_crime_creates_sand_soldier():
    """Crime trigger: a CRIME_COMMITTED for the controller creates a Sand Soldier."""
    print("\n=== Crocodile: crime trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    croc = _put_on_battlefield(game, p1, "Crocodile, Sandstorm of Alabasta")
    before = len([e for e in game.state.event_log
                  if e.type == EventType.CREATE_TOKEN and e.source == croc.id])
    game.emit(Event(
        type=EventType.CRIME_COMMITTED,
        payload={'player': p1.id, 'targets': [p2.id], 'source': croc.id},
        source=croc.id,
    ))
    after = len([e for e in game.state.event_log
                 if e.type == EventType.CREATE_TOKEN and e.source == croc.id])
    assert after >= before + 1, f"Crime should mint a token: {before}→{after}"
    cts = [e for e in game.state.event_log
           if e.type == EventType.CREATE_TOKEN and e.source == croc.id]
    last_token = cts[-1].payload.get('token') or {}
    assert 'Sand' in last_token.get('subtypes', set()), (
        f"Token subtypes should contain 'Sand': {last_token}"
    )
    print(f"  Sand Soldier minted on crime")


# ============================================================================
# Buggy, the Star Clown
# ============================================================================

def test_buggy_etb_creates_treasure():
    """ETB creates a Treasure token."""
    print("\n=== Buggy: ETB treasure ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = _emitted_types(game)
    buggy = _put_on_battlefield(game, p1, "Buggy, the Star Clown")
    after = _emitted_types(game)
    new = after[len(before):]
    assert 'CREATE_TOKEN' in new, f"CREATE_TOKEN missing: {new}"
    cts = [e for e in game.state.event_log
           if e.type == EventType.CREATE_TOKEN and e.source == buggy.id]
    assert cts and 'Treasure' in (cts[-1].payload.get('token') or {}).get('subtypes', set())
    print("  Treasure token on ETB")


def test_buggy_death_sets_revive_flag():
    """Buggy's death registers turn_data flags so the upkeep trigger fires."""
    print("\n=== Buggy: death flag ===")
    game = Game()
    p1 = game.add_player("Alice")
    buggy = _put_on_battlefield(game, p1, "Buggy, the Star Clown")
    # Kill Buggy.
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': buggy.id},
        source=buggy.id,
    ))
    # Death trigger fires during REACT — even if we don't move the object,
    # the effect_fn ran and set flags.
    assert game.state.turn_data.get('_buggy_revive_id') == buggy.id, (
        f"Revive flag not set: {game.state.turn_data}"
    )
    print(f"  Revive flag set: {game.state.turn_data.get('_buggy_revive_id') == buggy.id}")


# ============================================================================
# Wanted Poster: Three Billion Berries
# ============================================================================

def test_wanted_poster_loads_legendary_enchantment():
    """Loads as a legendary enchantment with crime trigger + activated ability."""
    print("\n=== Wanted Poster 3B: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    wp = _put_on_battlefield(game, p1, "Wanted Poster: Three Billion Berries")
    chars = wp.characteristics
    assert CardType.ENCHANTMENT in chars.types
    assert 'Legendary' in (chars.supertypes or set())
    assert len(wp.interceptor_ids) >= 1
    abilities = getattr(wp.state, 'activated_abilities', [])
    assert len(abilities) >= 1, f"Expected sac-detonate ability; got {len(abilities)}"
    print(f"  Interceptors={len(wp.interceptor_ids)}, abilities={len(abilities)}")


def test_wanted_poster_crime_adds_counter():
    """A CRIME_COMMITTED event adds a +1/+1 counter to Wanted Poster."""
    print("\n=== Wanted Poster 3B: crime counter ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    wp = _put_on_battlefield(game, p1, "Wanted Poster: Three Billion Berries")
    before_ct = wp.state.counters.get('+1/+1', 0)
    game.emit(Event(
        type=EventType.CRIME_COMMITTED,
        payload={'player': p1.id, 'targets': [p2.id], 'source': wp.id},
        source=wp.id,
    ))
    after_ct = wp.state.counters.get('+1/+1', 0)
    assert after_ct == before_ct + 1, f"Crime should add counter: {before_ct}→{after_ct}"
    print(f"  Counter {before_ct}→{after_ct}")


def test_wanted_poster_opp_crime_does_not_add_counter():
    """Edge: opponent committing a crime does NOT count for our Wanted Poster."""
    print("\n=== Wanted Poster 3B: opp-crime edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    wp = _put_on_battlefield(game, p1, "Wanted Poster: Three Billion Berries")
    before_ct = wp.state.counters.get('+1/+1', 0)
    game.emit(Event(
        type=EventType.CRIME_COMMITTED,
        payload={'player': p2.id, 'targets': [p1.id], 'source': 'opp_card'},
        source='opp_card',
    ))
    after_ct = wp.state.counters.get('+1/+1', 0)
    assert after_ct == before_ct, f"Opp crime should NOT add counter: {before_ct}→{after_ct}"
    print("  Opp crime correctly ignored")


def test_wanted_poster_detonate_emits_damage_and_treasure():
    """Detonate ability with N counters emits N damage to each opp + N Treasures."""
    print("\n=== Wanted Poster 3B: detonate ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    wp = _put_on_battlefield(game, p1, "Wanted Poster: Three Billion Berries")
    # Stack 3 counters.
    wp.state.counters['+1/+1'] = 3
    abilities = wp.state.activated_abilities or []
    detonate = next((a for a in abilities if 'sacrifice' in (a.cost_text or '').lower()
                     and 'wanted poster' in (a.cost_text or '').lower()), None)
    assert detonate is not None, f"Detonate ability not found: {[a.cost_text for a in abilities]}"
    events = detonate.effect_fn(wp, game.state, [])
    types_emitted = [e.type.name for e in events]
    dmg = [e for e in events if e.type == EventType.DAMAGE and e.payload.get('target') == p2.id]
    treasures = [e for e in events if e.type == EventType.CREATE_TOKEN]
    assert dmg and dmg[0].payload.get('amount') == 3, (
        f"Expected 3 damage to p2, got {[e.payload for e in dmg]}"
    )
    assert len(treasures) == 3, f"Expected 3 Treasure tokens, got {len(treasures)}"
    print(f"  3 damage to opp + 3 treasures emitted")


def test_wanted_poster_detonate_zero_counters_emits_nothing():
    """Edge: detonating with 0 counters returns []."""
    print("\n=== Wanted Poster 3B: zero-counter edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    wp = _put_on_battlefield(game, p1, "Wanted Poster: Three Billion Berries")
    abilities = wp.state.activated_abilities or []
    detonate = next((a for a in abilities if 'sacrifice' in (a.cost_text or '').lower()
                     and 'wanted poster' in (a.cost_text or '').lower()), None)
    assert detonate is not None
    events = detonate.effect_fn(wp, game.state, [])
    assert events == [], f"Zero counters should yield no events: {events}"
    print("  Zero counters correctly returns []")


# ============================================================================
# Devil Fruit Vault
# ============================================================================

def test_devil_fruit_vault_loads_legendary_artifact():
    """Loads as a legendary artifact with mana + tutor abilities."""
    print("\n=== Devil Fruit Vault: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    dfv = _put_on_battlefield(game, p1, "Devil Fruit Vault")
    chars = dfv.characteristics
    assert CardType.ARTIFACT in chars.types
    assert 'Legendary' in (chars.supertypes or set())
    abilities = getattr(dfv.state, 'activated_abilities', [])
    assert len(abilities) >= 2, f"Expected mana + tutor; got {len(abilities)}"
    print(f"  Abilities: {len(abilities)}")


def test_devil_fruit_vault_tutor_emits_search_for_devil_fruit():
    """The tutor ability emits a SEARCH_LIBRARY for Devil Fruit subtype."""
    print("\n=== Devil Fruit Vault: tutor ===")
    game = Game()
    p1 = game.add_player("Alice")
    dfv = _put_on_battlefield(game, p1, "Devil Fruit Vault")
    abilities = dfv.state.activated_abilities or []
    tutor = next((a for a in abilities if '{3}' in (a.cost_text or '')
                  and '{T}' in (a.cost_text or '')), None)
    assert tutor is not None, f"Tutor ability not found: {[a.cost_text for a in abilities]}"
    events = tutor.effect_fn(dfv, game.state, [])
    sl = [e for e in events if e.type == EventType.SEARCH_LIBRARY]
    assert sl, f"Tutor should emit SEARCH_LIBRARY: {[e.type.name for e in events]}"
    assert sl[0].payload.get('subtype') == 'Devil Fruit', (
        f"Tutor should target Devil Fruit subtype: {sl[0].payload}"
    )
    print(f"  SEARCH_LIBRARY for Devil Fruit emitted")


# ============================================================================
# Fishman Karate Trident
# ============================================================================

def test_fishman_trident_loads_with_equipment_subtype():
    """Carries Equipment subtype."""
    print("\n=== Fishman Trident: load ===")
    cd = ONE_PIECE_CARDS["Fishman Karate Trident"]
    chars = cd.characteristics
    assert CardType.ARTIFACT in chars.types
    assert 'Equipment' in (chars.subtypes or set())
    print(f"  Subtypes: {chars.subtypes}")


def test_fishman_trident_grants_pt_and_subtype_on_attach():
    """ATTACH grants the equipped creature the Fish-Man subtype + +2/+2."""
    print("\n=== Fishman Trident: attach grants ===")
    game = Game()
    p1 = game.add_player("Alice")
    trident = _put_on_battlefield(game, p1, "Fishman Karate Trident")
    # Drop a non-Fish-Man creature.
    crew = game.create_object(
        name="Crewmate",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            colors={Color.BLUE},
            subtypes={"Human", "Pirate"},
            power=2, toughness=2,
        ),
    )
    crew.controller = p1.id
    # Attach trident to crew. The canonical ATTACH payload uses object_id
    # for the source-of-attach (the equipment) and target_id for the
    # creature being attached to. The engine handler also accepts the
    # legacy source/target keys, but the subtypes-listener filter (which
    # gates on object_id) requires the canonical form.
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': trident.id, 'target_id': crew.id},
        source=trident.id,
    ))
    # Crew should now have Fish-Man subtype.
    assert 'Fish-Man' in (crew.characteristics.subtypes or set()), (
        f"Subtype not added: {crew.characteristics.subtypes}"
    )
    # Crew P/T should reflect +2/+2.
    p_power = get_power(crew, game.state)
    p_tough = get_toughness(crew, game.state)
    assert p_power >= 4 and p_tough >= 4, (
        f"Expected ≥4/≥4, got {p_power}/{p_tough}"
    )
    print(f"  Crew now {p_power}/{p_tough} with subtypes {crew.characteristics.subtypes}")


# ============================================================================
# Skypiea Gold Hoard
# ============================================================================

def test_skypiea_gold_hoard_loads():
    """Loads with two activated abilities (mana + extra-turn)."""
    print("\n=== Skypiea Gold Hoard: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    sgh = _put_on_battlefield(game, p1, "Skypiea Gold Hoard")
    chars = sgh.characteristics
    assert CardType.ARTIFACT in chars.types
    abilities = getattr(sgh.state, 'activated_abilities', [])
    assert len(abilities) >= 2, f"Expected mana + extra-turn; got {len(abilities)}"
    print(f"  Abilities: {len(abilities)}")


def test_skypiea_gold_hoard_extra_turn_requires_three_treasures():
    """The extra-turn ability returns no events when fewer than 3 Treasures
    are sacrificable."""
    print("\n=== Skypiea Gold Hoard: gating ===")
    game = Game()
    p1 = game.add_player("Alice")
    sgh = _put_on_battlefield(game, p1, "Skypiea Gold Hoard")
    abilities = sgh.state.activated_abilities or []
    extra = next((a for a in abilities if 'extra turn' in (a.description or '').lower()), None)
    assert extra is not None, f"Extra-turn ability missing: {[a.description for a in abilities]}"
    # No treasures: returns [].
    events = extra.effect_fn(sgh, game.state, [])
    assert events == [], f"No-treasure path should yield []: {events}"
    print("  Insufficient treasure correctly gates")


def test_skypiea_gold_hoard_extra_turn_with_three_treasures_emits():
    """With 3 Treasures controlled, the ability emits 3 SACRIFICE + EXTRA_TURN."""
    print("\n=== Skypiea Gold Hoard: extra-turn fires ===")
    game = Game()
    p1 = game.add_player("Alice")
    sgh = _put_on_battlefield(game, p1, "Skypiea Gold Hoard")
    # Drop 3 treasures.
    treasures = []
    for i in range(3):
        t = game.create_object(
            name=f"Treasure {i}",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(
                types={CardType.ARTIFACT}, subtypes={"Treasure"},
            ),
        )
        t.controller = p1.id
        treasures.append(t)
    abilities = sgh.state.activated_abilities or []
    extra = next((a for a in abilities if 'extra turn' in (a.description or '').lower()), None)
    events = extra.effect_fn(sgh, game.state, [])
    types_emitted = [e.type.name for e in events]
    assert types_emitted.count('SACRIFICE') == 3, f"Expected 3 SACRIFICE: {types_emitted}"
    assert 'EXTRA_TURN' in types_emitted, f"EXTRA_TURN missing: {types_emitted}"
    print("  3 SACRIFICE + EXTRA_TURN emitted")


if __name__ == "__main__":
    # Luffy
    test_luffy_king_loads_legendary_pirate()
    test_luffy_etb_taps_opp_creatures()
    test_luffy_lord_buffs_other_pirates_not_self()
    test_luffy_threaten_requires_three_treasures()
    # Zoro
    test_zoro_demon_loads_with_first_strike()
    test_zoro_demon_etb_emits_search_for_sword()
    test_zoro_demon_attach_grants_double_strike()
    # Sanji
    test_sanji_etb_creates_food()
    test_sanji_attack_creates_food()
    test_sanji_attack_does_not_trigger_for_other_attacker()
    # Crocodile
    test_crocodile_loads_with_replacement_and_crime_trigger()
    test_crocodile_taps_opp_lands()
    test_crocodile_self_lands_unaffected()
    test_crocodile_crime_creates_sand_soldier()
    # Buggy
    test_buggy_etb_creates_treasure()
    test_buggy_death_sets_revive_flag()
    # Wanted Poster
    test_wanted_poster_loads_legendary_enchantment()
    test_wanted_poster_crime_adds_counter()
    test_wanted_poster_opp_crime_does_not_add_counter()
    test_wanted_poster_detonate_emits_damage_and_treasure()
    test_wanted_poster_detonate_zero_counters_emits_nothing()
    # Devil Fruit Vault
    test_devil_fruit_vault_loads_legendary_artifact()
    test_devil_fruit_vault_tutor_emits_search_for_devil_fruit()
    # Fishman Trident
    test_fishman_trident_loads_with_equipment_subtype()
    test_fishman_trident_grants_pt_and_subtype_on_attach()
    # Skypiea Gold Hoard
    test_skypiea_gold_hoard_loads()
    test_skypiea_gold_hoard_extra_turn_requires_three_treasures()
    test_skypiea_gold_hoard_extra_turn_with_three_treasures_emits()
    print("\n" + "=" * 60)
    print("ALL ONE PIECE SPICE TESTS PASSED!")
    print("=" * 60)
