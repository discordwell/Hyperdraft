"""
Star Wars Spice Pass Tests (Wave 22+)

Validates the format-defining cards added in plans/proud-singing-sonnet.md.
Phase A: cards built with existing engine helpers only.
"""

import sys
sys.path.insert(0, '/Users/discordwell/Projects/HYPERDRAFT')

from src.engine import (
    Game, Event, EventType, ZoneType, CardType,
    get_power, get_toughness,
)
from src.cards.custom.star_wars import STAR_WARS_CARDS


def _put_on_battlefield(game, player, card_name):
    """Standard pattern: create in hand without card_def, then ZONE_CHANGE."""
    card_def = STAR_WARS_CARDS[card_name]
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
# Boba Fett, Hunter of Hunters
# ============================================================================

def test_boba_fett_loads_and_grants_keywords():
    """Self-keyword grants register on ETB."""
    print("\n=== Boba Fett: keywords + ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    boba = _put_on_battlefield(game, p1, "Boba Fett, Hunter of Hunters")
    assert boba.zone == ZoneType.BATTLEFIELD
    # Spice card should have at least the damage trigger and 2 keyword grants
    assert len(boba.interceptor_ids) >= 2, (
        f"Expected setup_interceptors to register helpers; got "
        f"{len(boba.interceptor_ids)}"
    )
    print(f"  Interceptors registered: {len(boba.interceptor_ids)}")


def test_boba_fett_combat_damage_triggers_exile_and_treasure():
    """Combat damage to a player → EXILE_TOP_PLAY + CREATE_TOKEN events."""
    print("\n=== Boba Fett: combat damage trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    boba = _put_on_battlefield(game, p1, "Boba Fett, Hunter of Hunters")

    # Emit a combat damage event from Boba targeting p2.
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'source': boba.id,
            'target': p2.id,
            'amount': 2,
            'is_combat': True,
        },
        source=boba.id,
    ))
    types = _emitted_types(game)
    assert 'EXILE_TOP_PLAY' in types, f"EXILE_TOP_PLAY not emitted: {types[-10:]}"
    assert 'CREATE_TOKEN' in types, f"CREATE_TOKEN not emitted: {types[-10:]}"
    print("  EXILE_TOP_PLAY + CREATE_TOKEN both emitted")


def test_boba_fett_noncombat_damage_does_not_trigger():
    """Edge: noncombat damage must NOT trigger the exile-and-play."""
    print("\n=== Boba Fett: noncombat damage edge case ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    boba = _put_on_battlefield(game, p1, "Boba Fett, Hunter of Hunters")

    before_types = _emitted_types(game)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'source': boba.id,
            'target': p2.id,
            'amount': 2,
            'is_combat': False,
        },
        source=boba.id,
    ))
    after_types = _emitted_types(game)
    new_types = after_types[len(before_types):]
    assert 'EXILE_TOP_PLAY' not in new_types, (
        f"Should not exile-and-play on noncombat damage: {new_types}"
    )
    print("  Noncombat damage correctly suppressed")


# ============================================================================
# IG-88, Assassin Droid Network
# ============================================================================

def test_ig88_loads_with_artifact_creature_types():
    """IG-88 carries both CREATURE and ARTIFACT types."""
    print("\n=== IG-88: dual types ===")
    game = Game()
    p1 = game.add_player("Alice")
    ig88 = _put_on_battlefield(game, p1, "IG-88, Assassin Droid Network")
    types = ig88.characteristics.types
    assert CardType.CREATURE in types
    assert CardType.ARTIFACT in types
    assert 'Droid' in ig88.characteristics.subtypes
    print(f"  Types: {types}, Subtypes: {ig88.characteristics.subtypes}")


def test_ig88_droid_etb_grants_counter_and_token():
    """When another Droid you control ETBs, IG-88 gets +1/+1 + Droid token."""
    print("\n=== IG-88: another Droid ETB trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    ig88 = _put_on_battlefield(game, p1, "IG-88, Assassin Droid Network")

    before_counters = ig88.state.counters.get('+1/+1', 0)
    before_types = _emitted_types(game)

    # Drop another Droid
    _put_on_battlefield(game, p1, "Battle Droid")

    after_counters = ig88.state.counters.get('+1/+1', 0)
    after_types = _emitted_types(game)
    new_types = after_types[len(before_types):]

    # +1/+1 counter applied via COUNTER_ADDED event
    assert 'COUNTER_ADDED' in new_types, (
        f"COUNTER_ADDED not emitted: {new_types}"
    )
    assert 'CREATE_TOKEN' in new_types, (
        f"CREATE_TOKEN not emitted: {new_types}"
    )
    assert after_counters >= before_counters + 1, (
        f"+1/+1 counter not applied. before={before_counters} after={after_counters}"
    )
    print(f"  IG-88 counters {before_counters} -> {after_counters}, tokens emitted")


def test_ig88_self_etb_does_not_self_trigger():
    """Edge: IG-88 entering should not trigger its own ETB-counter ability."""
    print("\n=== IG-88: self-ETB does not self-trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    ig88 = _put_on_battlefield(game, p1, "IG-88, Assassin Droid Network")
    counters = ig88.state.counters.get('+1/+1', 0)
    assert counters == 0, (
        f"IG-88 should not apply +1/+1 to itself on ETB; got {counters}"
    )
    print(f"  Self ETB counters: {counters} (correct)")


# ============================================================================
# Yoda, Living Force
# ============================================================================

def test_yoda_living_force_etb_emits_scry():
    """ETB emits a SCRY event."""
    print("\n=== Yoda Living Force: ETB scry ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = _emitted_types(game)
    _put_on_battlefield(game, p1, "Yoda, Living Force")
    after = _emitted_types(game)
    new = after[len(before):]
    assert 'SCRY' in new, f"SCRY not emitted: {new}"
    print(f"  SCRY emitted on ETB")


def test_yoda_living_force_lords_other_jedi():
    """Other Jedi creatures get +1/+1 statically."""
    print("\n=== Yoda Living Force: lord effect ===")
    game = Game()
    p1 = game.add_player("Alice")

    # Drop a Jedi first (Jedi Padawan: 2/2)
    padawan = _put_on_battlefield(game, p1, "Jedi Padawan")
    base_p, base_t = get_power(padawan, game.state), get_toughness(padawan, game.state)

    # Drop Yoda
    _put_on_battlefield(game, p1, "Yoda, Living Force")

    new_p, new_t = get_power(padawan, game.state), get_toughness(padawan, game.state)
    assert new_p == base_p + 1, f"Expected Padawan power +1: {base_p}→{new_p}"
    assert new_t == base_t + 1, f"Expected Padawan toughness +1: {base_t}→{new_t}"
    print(f"  Jedi Padawan {base_p}/{base_t} -> {new_p}/{new_t}")


# ============================================================================
# Bossk, Trandoshan Hunter Prime
# ============================================================================

def test_bossk_attack_emits_search_library():
    """Bossk attacks → SEARCH_LIBRARY event for a Bounty Hunter."""
    print("\n=== Bossk Prime: attack → tutor ===")
    game = Game()
    p1 = game.add_player("Alice")
    bossk = _put_on_battlefield(game, p1, "Bossk, Trandoshan Hunter Prime")

    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': bossk.id, 'attacker': bossk.id, 'defender': 'opponent'},
        source=bossk.id,
    ))
    after = _emitted_types(game)
    new = after[len(before):]
    assert 'SEARCH_LIBRARY' in new, f"SEARCH_LIBRARY not emitted: {new}"
    print("  SEARCH_LIBRARY emitted on attack")


# ============================================================================
# Han Solo, Hotshot Pilot
# ============================================================================

def test_han_solo_hotshot_etb_creates_treasure():
    """ETB emits CREATE_TOKEN for Treasure."""
    print("\n=== Han Solo: ETB Treasure ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = _emitted_types(game)
    _put_on_battlefield(game, p1, "Han Solo, Hotshot Pilot")
    after = _emitted_types(game)
    new = after[len(before):]
    assert 'CREATE_TOKEN' in new, f"CREATE_TOKEN not emitted: {new}"
    print("  Treasure token emitted on ETB")


# ============================================================================
# Holocron of the High Council
# ============================================================================

def test_holocron_registers_activated_abilities():
    """Holocron registers two activated abilities (mana + tutor)."""
    print("\n=== Holocron: activated abilities ===")
    game = Game()
    p1 = game.add_player("Alice")
    holocron = _put_on_battlefield(game, p1, "Holocron of the High Council")
    abilities = getattr(holocron.state, 'activated_abilities', [])
    assert len(abilities) >= 2, (
        f"Expected ≥2 activated abilities, got {len(abilities)}"
    )
    print(f"  Activated abilities registered: {len(abilities)}")


# ============================================================================
# Mandalorian Beskar Plating
# ============================================================================

def test_mandalorian_beskar_loads_as_equipment():
    """Beskar is an Artifact-Equipment; setup runs without error."""
    print("\n=== Mandalorian Beskar: loads ===")
    game = Game()
    p1 = game.add_player("Alice")
    beskar = _put_on_battlefield(game, p1, "Mandalorian Beskar Plating")
    chars = beskar.characteristics
    assert CardType.ARTIFACT in chars.types
    assert 'Equipment' in chars.subtypes
    abilities = getattr(beskar.state, 'activated_abilities', [])
    # Equip cost registers an activated ability
    assert len(abilities) >= 1, (
        f"Expected equip activated ability, got {len(abilities)}"
    )
    print(f"  Beskar loaded: types={chars.types}, abilities={len(abilities)}")


# ============================================================================
# Sith Resurgence
# ============================================================================

def test_sith_resurgence_card_definition():
    """Sith Resurgence is a sorcery with a wired resolve fn."""
    print("\n=== Sith Resurgence: card def ===")
    cd = STAR_WARS_CARDS["Sith Resurgence"]
    assert CardType.SORCERY in cd.characteristics.types
    assert cd.resolve is not None, "resolve fn must be wired"
    print(f"  Sorcery with resolve fn: {cd.resolve.__name__}")


def test_sith_resurgence_resolve_returns_sith_to_battlefield():
    """resolve(targets=[sith_id], state) emits RETURN_FROM_GRAVEYARD."""
    print("\n=== Sith Resurgence: resolve ===")
    game = Game()
    p1 = game.add_player("Alice")

    # Create a Sith creature in graveyard
    from src.engine import Characteristics, Color
    sith_chars = Characteristics(
        types={CardType.CREATURE},
        subtypes={"Human", "Sith"},
        colors={Color.BLACK},
        power=2, toughness=2,
    )
    sith = game.create_object(
        name="Test Sith",
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=sith_chars,
    )

    cd = STAR_WARS_CARDS["Sith Resurgence"]

    # The resolve fn takes a list of "target" entries; emulate the format used
    # by stack.py — bare ids work since the fn handles both shapes.
    events = cd.resolve([sith.id], game.state)
    assert events, "resolve should return at least one event"
    rfg = [e for e in events if e.type == EventType.RETURN_FROM_GRAVEYARD]
    assert rfg, f"Expected RETURN_FROM_GRAVEYARD, got {[e.type.name for e in events]}"
    payload = rfg[0].payload
    assert payload.get('object_id') == sith.id
    assert payload.get('destination') == 'battlefield'
    print(f"  RETURN_FROM_GRAVEYARD emitted for {payload.get('object_id')}")


def test_sith_resurgence_rejects_non_sith():
    """Edge: target a non-Sith → resolve returns []."""
    print("\n=== Sith Resurgence: edge non-Sith target ===")
    game = Game()
    p1 = game.add_player("Alice")
    from src.engine import Characteristics, Color
    rebel_chars = Characteristics(
        types={CardType.CREATURE},
        subtypes={"Human", "Rebel"},
        colors={Color.WHITE},
        power=2, toughness=2,
    )
    rebel = game.create_object(
        name="Test Rebel",
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=rebel_chars,
    )
    cd = STAR_WARS_CARDS["Sith Resurgence"]
    events = cd.resolve([rebel.id], game.state)
    rfg = [e for e in events if e.type == EventType.RETURN_FROM_GRAVEYARD]
    assert not rfg, f"Non-Sith target should be rejected; got {events}"
    print("  Non-Sith target correctly rejected")


# ============================================================================
# Regression tests for reviewer-flagged bugs (round 1)
# ============================================================================

def test_boba_fett_exile_top_play_caster_is_bobas_controller():
    """Bug fix: EXILE_TOP_PLAY payload uses 'caster' (not 'controller') so the
    play permission lands on Boba's controller, not the defending player."""
    print("\n=== Boba Fett: caster key ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    boba = _put_on_battlefield(game, p1, "Boba Fett, Hunter of Hunters")

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'source': boba.id, 'target': p2.id, 'amount': 2, 'is_combat': True},
        source=boba.id,
    ))
    etps = [e for e in game.state.event_log if e.type == EventType.EXILE_TOP_PLAY]
    assert etps, "EXILE_TOP_PLAY not emitted"
    payload = etps[-1].payload
    assert payload.get('caster') == p1.id, (
        f"Caster must be Boba's controller (p1={p1.id}); got "
        f"caster={payload.get('caster')} controller={payload.get('controller')}"
    )
    assert payload.get('player') == p2.id, "Library to exile is the target's"
    print(f"  caster={payload.get('caster')} (Boba's controller), player={payload.get('player')} (defender)")


def test_boba_fett_empty_library_no_crash():
    """Edge: Boba's combat damage when target has no library left must not crash."""
    print("\n=== Boba Fett: empty library edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    boba = _put_on_battlefield(game, p1, "Boba Fett, Hunter of Hunters")

    # Empty Bob's library
    lib = game.state.zones.get(f"library_{p2.id}")
    if lib:
        lib.objects.clear()

    # Should not raise
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'source': boba.id, 'target': p2.id, 'amount': 2, 'is_combat': True},
        source=boba.id,
    ))
    print("  No crash on empty library")


def test_ig88_triggers_on_token_droid():
    """Bug fix: IG-88 must fire on OBJECT_CREATED events (token Droids), not
    only on ZONE_CHANGE."""
    print("\n=== IG-88: token Droid trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    ig88 = _put_on_battlefield(game, p1, "IG-88, Assassin Droid Network")
    before = ig88.state.counters.get('+1/+1', 0)

    # Mint a token Droid via CREATE_TOKEN — the standard token-minting path.
    game.emit(Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': p1.id,
            'token': {
                'name': 'Battle Droid Token',
                'power': 1, 'toughness': 1,
                'types': {CardType.ARTIFACT, CardType.CREATURE},
                'subtypes': {'Droid'},
            },
        },
    ))
    after = ig88.state.counters.get('+1/+1', 0)
    assert after >= before + 1, (
        f"IG-88 didn't trigger on token Droid: counters {before} -> {after}"
    )
    print(f"  IG-88 +1/+1 counters {before} -> {after} on token Droid")


def test_holocron_tutor_filter_only_jedi_or_sith():
    """Bug fix: tutor must filter to Jedi/Sith subtypes only, not return any card."""
    print("\n=== Holocron: tutor subtype filter ===")
    from src.cards.custom.star_wars import HOLOCRON_OF_THE_HIGH_COUNCIL

    # Tap into the activated ability's effect_fn directly to inspect the event payload.
    game = Game()
    p1 = game.add_player("Alice")
    holo = _put_on_battlefield(game, p1, "Holocron of the High Council")

    abilities = getattr(holo.state, 'activated_abilities', [])
    # Pick the tutor ability (the one with a sacrifice cost).
    tutor_abil = None
    for a in abilities:
        # Cost dict / object likely surfaces sac_self or similar.
        cost_text = getattr(a, 'cost_text', None) or getattr(a, 'description', '') or ''
        if 'Sacrifice' in cost_text or 'sacrifice' in cost_text:
            tutor_abil = a
            break
    assert tutor_abil is not None, f"Tutor ability not found among {abilities}"

    # Invoke the effect fn to inspect emitted SEARCH_LIBRARY payload.
    effect_fn = getattr(tutor_abil, 'effect_fn', None)
    assert effect_fn, "Tutor ability missing effect_fn"
    events = effect_fn(holo, game.state, [])
    sl = [e for e in events if e.type == EventType.SEARCH_LIBRARY]
    assert sl, f"SEARCH_LIBRARY not emitted; got {[e.type.name for e in events]}"
    payload = sl[0].payload
    subtypes_any = payload.get('subtypes_any')
    assert subtypes_any, f"subtypes_any missing: {payload}"
    assert set(subtypes_any) == {'Jedi', 'Sith'}, (
        f"Expected subtypes_any = {{Jedi, Sith}}; got {subtypes_any}"
    )
    print(f"  Tutor filters subtypes_any={subtypes_any}")


def test_holocron_tutor_cost_parses():
    """Bug fix: Holocron's tutor cost '{4}, {T}, Sacrifice this artifact' must
    parse as: 4 generic mana + tap + sacrifice-self."""
    print("\n=== Holocron: cost parses correctly ===")
    from src.engine.activated import parse_activation_cost
    mana, has_tap, sac_self, _, _, _, _ = parse_activation_cost(
        "{4}, {T}, Sacrifice this artifact",
        source_name="Holocron of the High Council",
    )
    assert has_tap, "Tap symbol must be recognised"
    assert sac_self, "Sacrifice-self must be recognised"
    assert mana is not None, "Mana cost must parse"
    print(f"  has_tap={has_tap} sac_self={sac_self} mana={mana}")


def test_search_library_handler_subtypes_any():
    """Engine extension: SEARCH_LIBRARY supports subtypes_any (list)."""
    print("\n=== Engine: SEARCH_LIBRARY subtypes_any ===")
    game = Game()
    p1 = game.add_player("Alice")
    library = game.state.zones.get(f"library_{p1.id}")
    assert library is not None

    # Use real card defs so the filter (which requires card_def) accepts them.
    def _add_to_lib(card_name):
        cd = STAR_WARS_CARDS[card_name]
        obj = game.create_object(
            name=card_name,
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=cd.characteristics,
            card_def=cd,
        )
        return obj

    jedi_card = _add_to_lib("Jedi Padawan")          # subtypes contain "Jedi"
    sith_card = _add_to_lib("Sith Apprentice")       # subtypes contain "Sith"
    rebel_card = _add_to_lib("Rebel Trooper")        # subtypes contain "Rebel"

    # Build a filter via the handler's pattern.
    from src.engine.library_search import _handle_search_library_event
    event = Event(
        type=EventType.SEARCH_LIBRARY,
        payload={
            'player': p1.id,
            'subtypes_any': ['Jedi', 'Sith'],
            'destination': 'hand',
            'min_count': 0,
            'max_count': 1,
        },
        source=p1.id,
    )
    _handle_search_library_event(event, game.state)

    # Verify the pending choice has the right options.
    choice = game.state.pending_choice
    assert choice is not None, "No pending choice created"
    option_ids = set(getattr(choice, 'options', []) or [])
    assert jedi_card.id in option_ids, "Jedi card must be a valid target"
    assert sith_card.id in option_ids, "Sith card must be a valid target"
    assert rebel_card.id not in option_ids, "Rebel card must NOT be a valid target"
    print(f"  Filter accepted Jedi+Sith ({len(option_ids)} options), excluded Rebel")


def test_bossk_cost_reduction_applies_to_bounty_hunters():
    """Bossk's static effect: Bounty Hunter spells cost {1} less."""
    print("\n=== Bossk: cost reduction ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Bossk, Trandoshan Hunter Prime")

    # Pick a Bounty Hunter card and ask the cost-query helper for its effective cost.
    bh_def = STAR_WARS_CARDS["Bounty Hunter"]
    bh = game.create_object(
        name="Bounty Hunter",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=bh_def.characteristics,
        card_def=bh_def,
    )
    from src.engine.cost_query import get_effective_mana_cost
    from src.engine import ManaCost
    base_cost = ManaCost.parse(bh_def.characteristics.mana_cost or bh_def.mana_cost)
    effective = get_effective_mana_cost(bh, p1.id, game.state, base_cost=base_cost)
    base_total = base_cost.mana_value
    eff_total = effective.mana_value
    assert eff_total == base_total - 1, (
        f"Bounty Hunter cost should be reduced by 1: base={base_total} effective={eff_total}"
    )
    print(f"  Bounty Hunter base CMC {base_total} -> effective {eff_total}")


def test_han_solo_sacrifice_treasure_pump():
    """Han Solo: when a Treasure is sacrificed by you, Han gets +2/+0 EOT."""
    print("\n=== Han Solo: sac-Treasure pump ===")
    from src.engine import Characteristics, Color
    game = Game()
    p1 = game.add_player("Alice")
    han = _put_on_battlefield(game, p1, "Han Solo, Hotshot Pilot")
    base_p = get_power(han, game.state)

    # Mint a Treasure under p1 and sacrifice it.
    treasure = game.create_object(
        name="Treasure",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            subtypes={"Treasure"},
            colors=set(),
        ),
    )
    game.emit(Event(
        type=EventType.SACRIFICE,
        payload={'object_id': treasure.id},
    ))
    # Han should have a temporary +2/+0
    new_p = get_power(han, game.state)
    assert new_p == base_p + 2, (
        f"Han should be +2/+0 after sacrificing a Treasure: {base_p} -> {new_p}"
    )
    print(f"  Han power {base_p} -> {new_p}")


# ============================================================================
# Phase B-1: 5 cards (Kylo, Stormtrooper Patrol, R2-D2, Vader, Sith Resurgence)
# ============================================================================

def test_kylo_ren_loads_with_haste():
    """Kylo Ren has haste granted via setup."""
    print("\n=== Kylo Ren: loads + haste ===")
    game = Game()
    p1 = game.add_player("Alice")
    kylo = _put_on_battlefield(game, p1, "Kylo Ren, Conflicted Heir")
    # Two interceptors expected: keyword grant + damage trigger.
    assert len(kylo.interceptor_ids) >= 2
    print(f"  Kylo registered {len(kylo.interceptor_ids)} interceptors")


def test_kylo_ren_combat_damage_steals_and_extra_combat_with_legendary():
    """Combat damage to a player → threaten target + EXTRA_COMBAT (when other legendary present)."""
    print("\n=== Kylo Ren: combat damage triggers steal + extra combat ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Drop another legendary creature alongside Kylo (Yoda Living Force).
    _put_on_battlefield(game, p1, "Yoda, Living Force")
    kylo = _put_on_battlefield(game, p1, "Kylo Ren, Conflicted Heir")
    # Drop an opposing creature to be stolen.
    from src.engine import Characteristics, Color
    enemy = game.create_object(
        name="Foe",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Soldier"},
            colors={Color.RED},
            power=2, toughness=2,
        ),
    )
    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'source': kylo.id, 'target': p2.id, 'amount': 4, 'is_combat': True},
        source=kylo.id,
    ))
    after = _emitted_types(game)
    new = after[len(before):]
    assert 'CONTROL_CHANGE' in new, f"CONTROL_CHANGE not emitted: {new}"
    assert 'EXTRA_COMBAT' in new, f"EXTRA_COMBAT not emitted: {new}"
    print(f"  Steal + extra combat both fired (events: {[e for e in new if e in ('CONTROL_CHANGE', 'EXTRA_COMBAT')]})")


def test_kylo_ren_no_extra_combat_alone():
    """No EXTRA_COMBAT when Kylo is the only legendary."""
    print("\n=== Kylo Ren: no extra combat without other legendary ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    kylo = _put_on_battlefield(game, p1, "Kylo Ren, Conflicted Heir")
    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'source': kylo.id, 'target': p2.id, 'amount': 4, 'is_combat': True},
        source=kylo.id,
    ))
    after = _emitted_types(game)
    new = after[len(before):]
    assert 'EXTRA_COMBAT' not in new, f"Should not get extra combat alone: {new}"
    print("  No EXTRA_COMBAT (correct)")


def test_stormtrooper_patrol_forces_opp_nonbasic_land_tapped():
    """Opponent's nonbasic land entering battlefield is forced to enter tapped."""
    print("\n=== Stormtrooper Patrol: opponent nonbasic enters tapped ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Stormtrooper Patrol Squadron")

    # Build a nonbasic land and emit ZONE_CHANGE to battlefield untapped.
    from src.engine import Characteristics
    land = game.create_object(
        name="Hidden Cove",
        owner_id=p2.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(
            types={CardType.LAND},
            subtypes={"Cove"},   # not Basic
        ),
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': land.id,
            'from_zone': f'hand_{p2.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
            'tapped': False,
        },
    ))
    # Find the resolved ZONE_CHANGE and confirm tapped flipped to True.
    matching = [e for e in game.state.event_log
                if e.type == EventType.ZONE_CHANGE
                and e.payload.get('object_id') == land.id]
    assert matching, "ZONE_CHANGE not logged"
    assert matching[-1].payload.get('tapped') is True, (
        f"Land should enter tapped; payload={matching[-1].payload}"
    )
    print("  Opponent's nonbasic land forced tapped (correct)")


def test_stormtrooper_patrol_does_not_tap_own_lands():
    """Squadron controller's nonbasic lands enter untapped."""
    print("\n=== Stormtrooper Patrol: own land untapped (edge) ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Stormtrooper Patrol Squadron")
    from src.engine import Characteristics
    land = game.create_object(
        name="Friendly Cove",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(
            types={CardType.LAND},
            subtypes={"Cove"},
        ),
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': land.id,
            'from_zone': f'hand_{p1.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
            'tapped': False,
        },
    ))
    matching = [e for e in game.state.event_log
                if e.type == EventType.ZONE_CHANGE
                and e.payload.get('object_id') == land.id]
    assert matching, "ZONE_CHANGE not logged"
    assert matching[-1].payload.get('tapped') is not True, (
        f"Squadron's own land should stay untapped: {matching[-1].payload}"
    )
    print("  Own nonbasic land untapped (correct)")


def test_r2d2_etb_castable_when_match():
    """R2-D2 ETB on artifact ≤MV3 → exiles + grants free cast permission."""
    print("\n=== R2-D2: ETB cast permission for matching card ===")
    from src.engine.cast_permission import is_castable_from_zone
    game = Game()
    p1 = game.add_player("Alice")

    # Stack the library: top is a low-cost artifact (any of the basic Star Wars artifacts).
    cd = STAR_WARS_CARDS["Astromech Droid"]
    library = game.state.zones.get(f"library_{p1.id}")
    obj = game.create_object(
        name="Astromech Droid",
        owner_id=p1.id,
        zone=ZoneType.LIBRARY,
        characteristics=cd.characteristics,
        card_def=cd,
    )
    # Move it to library top.
    library.objects.remove(obj.id)
    library.objects.insert(0, obj.id)

    _put_on_battlefield(game, p1, "R2-D2, Master Hacker")
    # The card should now be in exile and castable for free.
    assert obj.zone == ZoneType.EXILE, f"Top card should be exiled, got {obj.zone}"
    permitted = is_castable_from_zone(obj.id, "exile", game.state)
    assert permitted, "Top card must be castable from exile after R2-D2 ETB"
    print(f"  Astromech exiled and castable from exile (permitted={permitted})")


def test_r2d2_etb_draws_when_filter_misses():
    """R2-D2 ETB with non-matching top card draws instead."""
    print("\n=== R2-D2: ETB draws when filter doesn't match ===")
    game = Game()
    p1 = game.add_player("Alice")

    # Top of library: a creature (not artifact/instant/sorcery).
    cd = STAR_WARS_CARDS["Jedi Padawan"]
    library = game.state.zones.get(f"library_{p1.id}")
    obj = game.create_object(
        name="Jedi Padawan",
        owner_id=p1.id,
        zone=ZoneType.LIBRARY,
        characteristics=cd.characteristics,
        card_def=cd,
    )
    library.objects.remove(obj.id)
    library.objects.insert(0, obj.id)

    before = _emitted_types(game)
    _put_on_battlefield(game, p1, "R2-D2, Master Hacker")
    after = _emitted_types(game)
    new = after[len(before):]
    assert 'DRAW' in new, f"DRAW not emitted: {new}"
    assert 'EXILE' not in new, f"EXILE should NOT be emitted on miss: {new}"
    print("  Filter miss → DRAW (correct)")


def test_vader_etb_drains_two():
    """Vader ETB drains opponent and gains 2 life."""
    print("\n=== Vader: ETB drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    p1_life = p1.life
    p2_life = p2.life
    _put_on_battlefield(game, p1, "Darth Vader, More Machine Than Man")
    assert p1.life == p1_life + 2, f"P1 should gain 2: {p1_life} -> {p1.life}"
    assert p2.life == p2_life - 2, f"P2 should lose 2: {p2_life} -> {p2.life}"
    print(f"  P1 {p1_life}→{p1.life}, P2 {p2_life}→{p2.life}")


def test_vader_dark_side_pt_bonus():
    """Vader gets +3/+1 when controller has < 10 life."""
    print("\n=== Vader: Dark Side P/T bonus ===")
    game = Game()
    p1 = game.add_player("Alice")
    vader = _put_on_battlefield(game, p1, "Darth Vader, More Machine Than Man")
    # ETB drained Bob, then gave Alice +2 life. Make Alice low.
    p1.life = 5
    pwr = get_power(vader, game.state)
    tgh = get_toughness(vader, game.state)
    assert pwr == 4 + 3, f"Vader power should be +3 (7), got {pwr}"
    assert tgh == 4 + 1, f"Vader toughness should be +1 (5), got {tgh}"
    p1.life = 20
    pwr = get_power(vader, game.state)
    assert pwr == 4, f"Vader at high life should be 4 power; got {pwr}"
    print(f"  Vader P/T at life=5: 7/5; at life=20: {pwr}/{get_toughness(vader, game.state)}")


def test_vader_reassemble_precondition_only_if_destroyed_this_turn():
    """Vader's reassemble ability is only legal if Vader was destroyed this turn."""
    print("\n=== Vader: reassemble precondition ===")
    from src.cards.interceptor_helpers import was_destroyed_this_turn
    from src.engine.activated import can_pay_activation

    game = Game()
    p1 = game.add_player("Alice")
    vader = _put_on_battlefield(game, p1, "Darth Vader, More Machine Than Man")

    # Move Vader to graveyard manually (simulating death).
    bf = game.state.zones.get("battlefield")
    if bf and vader.id in bf.objects:
        bf.objects.remove(vader.id)
    gy = game.state.zones.get(f"graveyard_{p1.id}")
    gy.objects.append(vader.id)
    vader.zone = ZoneType.GRAVEYARD

    # Re-run setup_in_graveyard manually since we didn't go through ZONE_CHANGE.
    from src.cards.custom.star_wars import vader_machine_man_setup
    vader_machine_man_setup(vader, game.state)

    # Find the reassemble ability.
    abilities = vader.state.activated_abilities or []
    reassemble = [a for a in abilities if 'Reassemble' in (a.description or '')]
    assert reassemble, f"Reassemble ability not registered: {[a.description for a in abilities]}"
    rea = reassemble[0]

    # NOT destroyed-this-turn → ability not legal.
    assert not was_destroyed_this_turn(vader.id, game.state)
    legal = can_pay_activation(rea, vader, game.state, p1.id, mana_system=None)
    # mana_system=None means mana check skipped, but precondition still gates.
    assert not legal, "Reassemble must NOT be legal before destruction is recorded"

    # Record destruction → ability legal.
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': vader.id},
        source=vader.id,
    ))
    assert was_destroyed_this_turn(vader.id, game.state)
    legal2 = can_pay_activation(rea, vader, game.state, p1.id, mana_system=None)
    assert legal2, "Reassemble must be legal after destruction this turn"
    print("  Precondition gates ability legality correctly")


def test_sith_resurgence_dark_side_discount():
    """Sith Resurgence with caster < 10 life costs 2 less."""
    print("\n=== Sith Resurgence: Dark Side discount ===")
    from src.engine.cost_query import get_effective_mana_cost
    from src.engine import ManaCost

    game = Game()
    p1 = game.add_player("Alice")
    sr_def = STAR_WARS_CARDS["Sith Resurgence"]
    sr = game.create_object(
        name="Sith Resurgence",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=sr_def.characteristics,
        card_def=sr_def,
    )
    # Run setup_in_hand to register the cost-reduction interceptor.
    if sr_def.setup_in_hand:
        for itc in sr_def.setup_in_hand(sr, game.state):
            game.state.interceptors[itc.id] = itc
            sr.interceptor_ids.append(itc.id)

    base = ManaCost.parse(sr_def.characteristics.mana_cost or sr_def.mana_cost)

    # High life: no discount.
    p1.life = 20
    eff_high = get_effective_mana_cost(sr, p1.id, game.state, base_cost=base)
    assert eff_high.mana_value == base.mana_value, (
        f"No discount at life≥10; base={base.mana_value} eff={eff_high.mana_value}"
    )

    # Low life: discount of 2.
    p1.life = 5
    eff_low = get_effective_mana_cost(sr, p1.id, game.state, base_cost=base)
    assert eff_low.mana_value == base.mana_value - 2, (
        f"Should discount by 2 at life<10; base={base.mana_value} eff={eff_low.mana_value}"
    )
    print(f"  life=20: cost {eff_high.mana_value}; life=5: cost {eff_low.mana_value}")


# ============================================================================
# Engine extension tests
# ============================================================================

def test_was_destroyed_this_turn_lifecycle():
    """Helper records destructions and resets on TURN_START."""
    print("\n=== Engine: was_destroyed_this_turn lifecycle ===")
    from src.cards.interceptor_helpers import was_destroyed_this_turn
    from src.engine import Characteristics
    game = Game()
    p1 = game.add_player("Alice")
    creature = game.create_object(
        name="Test Creature",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            power=1, toughness=1,
        ),
    )
    assert not was_destroyed_this_turn(creature.id, game.state)
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': creature.id},
    ))
    assert was_destroyed_this_turn(creature.id, game.state)
    game.emit(Event(
        type=EventType.TURN_START,
        payload={'turn_number': 2, 'active_player': p1.id},
    ))
    assert not was_destroyed_this_turn(creature.id, game.state), (
        "Helper must reset on TURN_START"
    )
    print("  False → True after destroy → False after TURN_START (correct)")


def test_cost_reduction_condition_fn_skipped_when_false():
    """make_cost_reduction with condition_fn=False → no reduction."""
    print("\n=== Engine: cost_reduction condition_fn ===")
    from src.cards.interceptor_helpers import make_cost_reduction
    from src.engine.cost_query import get_effective_mana_cost
    from src.engine import ManaCost, Characteristics

    game = Game()
    p1 = game.add_player("Alice")
    src = game.create_object(
        name="Source",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.ENCHANTMENT}),
    )
    target_card = game.create_object(
        name="Target",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(
            types={CardType.CREATURE}, mana_cost="{3}{R}",
            power=2, toughness=2,
        ),
    )
    target_card.card_def = type("X", (), {"mana_cost": "{3}{R}", "characteristics": target_card.characteristics})()

    flag = {'enabled': False}

    interceptor = make_cost_reduction(
        src,
        applies_to=lambda c, pid, st: True,
        amount=2,
        condition_fn=lambda st: flag['enabled'],
    )
    game.state.interceptors[interceptor.id] = interceptor
    src.interceptor_ids.append(interceptor.id)

    base = ManaCost.parse("{3}{R}")
    eff_disabled = get_effective_mana_cost(target_card, p1.id, game.state, base_cost=base)
    assert eff_disabled.mana_value == base.mana_value, (
        f"Disabled condition should not reduce; got {eff_disabled.mana_value}"
    )

    flag['enabled'] = True
    eff_enabled = get_effective_mana_cost(target_card, p1.id, game.state, base_cost=base)
    assert eff_enabled.mana_value == base.mana_value - 2, (
        f"Enabled condition should reduce by 2; got {eff_enabled.mana_value}"
    )
    print(f"  disabled: {eff_disabled.mana_value}; enabled: {eff_enabled.mana_value}")


# ============================================================================
# Phase B-2: The Force Itself (Saga)
# ============================================================================

def test_force_itself_loads_as_saga():
    """The Force Itself loads with the Saga subtype + chapter dispatcher."""
    print("\n=== Force Itself: loads ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Force Itself")
    assert saga.zone == ZoneType.BATTLEFIELD
    assert "Saga" in saga.characteristics.subtypes
    # ETB sets first lore counter.
    assert saga.state.counters.get('lore', 0) == 1, (
        f"ETB should set 1 lore counter; got {saga.state.counters}"
    )
    print(f"  Lore counter at ETB: {saga.state.counters.get('lore', 0)}")


def test_force_itself_chapter_i_exiles_top_creature():
    """Chapter I exiles top of each opponent's library if it's a creature."""
    print("\n=== Force Itself: chapter I ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Plant a creature on top of Bob's library.
    cd = STAR_WARS_CARDS["Jedi Padawan"]
    library = game.state.zones.get(f"library_{p2.id}")
    target = game.create_object(
        name="Jedi Padawan",
        owner_id=p2.id,
        zone=ZoneType.LIBRARY,
        characteristics=cd.characteristics,
        card_def=cd,
    )
    library.objects.remove(target.id)
    library.objects.insert(0, target.id)

    _put_on_battlefield(game, p1, "The Force Itself")
    # Chapter I should have run on ETB.
    assert target.zone == ZoneType.EXILE, (
        f"Top creature should be exiled; got {target.zone}"
    )
    print(f"  Bob's top library card exiled to {target.zone.name}")


def test_force_itself_chapter_i_skips_noncreature():
    """Chapter I leaves non-creatures alone."""
    print("\n=== Force Itself: chapter I noncreature edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Plant an instant on top of Bob's library.
    cd = STAR_WARS_CARDS["Force Push"]  # instant
    library = game.state.zones.get(f"library_{p2.id}")
    target = game.create_object(
        name="Force Push",
        owner_id=p2.id,
        zone=ZoneType.LIBRARY,
        characteristics=cd.characteristics,
        card_def=cd,
    )
    library.objects.remove(target.id)
    library.objects.insert(0, target.id)

    _put_on_battlefield(game, p1, "The Force Itself")
    assert target.zone == ZoneType.LIBRARY, (
        f"Non-creature should not be exiled; got {target.zone}"
    )
    print(f"  Non-creature stays in library (correct)")


def test_force_itself_chapter_ii_pumps_negatively_only_opponent():
    """Chapter II gives -3/-3 to opponent creatures, not own."""
    print("\n=== Force Itself: chapter II ===")
    from src.engine import Characteristics, Color
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Drop creatures for both.
    own = game.create_object(
        name="Mine",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            colors={Color.WHITE},
            power=4, toughness=4,
        ),
    )
    enemy = game.create_object(
        name="Theirs",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            colors={Color.RED},
            power=4, toughness=4,
        ),
    )
    saga = _put_on_battlefield(game, p1, "The Force Itself")
    # Advance to chapter II via a draw step trigger.
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'draw', 'step': 'draw',
                 'active_player': p1.id, 'turn_number': 1},
    ))
    assert saga.state.counters.get('lore', 0) == 2, (
        f"After draw step, saga should be at lore 2; got {saga.state.counters}"
    )
    own_p, own_t = get_power(own, game.state), get_toughness(own, game.state)
    en_p, en_t = get_power(enemy, game.state), get_toughness(enemy, game.state)
    assert own_p == 4 and own_t == 4, (
        f"Own creature should be untouched: {own_p}/{own_t}"
    )
    assert en_p == 1 and en_t == 1, (
        f"Enemy should be -3/-3: {en_p}/{en_t}"
    )
    print(f"  Own {own_p}/{own_t}, enemy {en_p}/{en_t}")


def test_force_itself_chapter_iii_emits_two_searches_and_sacrifices():
    """Chapter III emits two SEARCH_LIBRARY events; saga sacrificed after III."""
    print("\n=== Force Itself: chapter III ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Force Itself")

    game.state.active_player = p1.id
    # Two draw steps to get to chapter III.
    for turn in (1, 2):
        game.emit(Event(
            type=EventType.PHASE_START,
            payload={'phase': 'draw', 'step': 'draw',
                     'active_player': p1.id, 'turn_number': turn},
        ))

    # SEARCH_LIBRARY emitted twice (creature tutor + equipment tutor).
    sl_events = [e for e in game.state.event_log
                 if e.type == EventType.SEARCH_LIBRARY
                 and e.source == saga.id]
    assert len(sl_events) >= 2, (
        f"Expected ≥2 SEARCH_LIBRARY from saga, got {len(sl_events)}"
    )
    payloads = [e.payload for e in sl_events]
    has_jedi_or_sith = any(p.get('subtypes_any') == ['Jedi', 'Sith'] for p in payloads)
    has_equipment = any(p.get('subtype') == 'Equipment' for p in payloads)
    assert has_jedi_or_sith, f"Missing Jedi/Sith tutor: {payloads}"
    assert has_equipment, f"Missing Equipment tutor: {payloads}"
    # Final-chapter sacrifice.
    assert saga.zone == ZoneType.GRAVEYARD, (
        f"Saga should be sacrificed after III; got {saga.zone}"
    )
    print(f"  Two tutors emitted, saga sacrificed to graveyard")


if __name__ == "__main__":
    test_boba_fett_loads_and_grants_keywords()
    test_boba_fett_combat_damage_triggers_exile_and_treasure()
    test_boba_fett_noncombat_damage_does_not_trigger()
    test_ig88_loads_with_artifact_creature_types()
    test_ig88_droid_etb_grants_counter_and_token()
    test_ig88_self_etb_does_not_self_trigger()
    test_yoda_living_force_etb_emits_scry()
    test_yoda_living_force_lords_other_jedi()
    test_bossk_attack_emits_search_library()
    test_han_solo_hotshot_etb_creates_treasure()
    test_holocron_registers_activated_abilities()
    test_mandalorian_beskar_loads_as_equipment()
    test_sith_resurgence_card_definition()
    test_sith_resurgence_resolve_returns_sith_to_battlefield()
    test_sith_resurgence_rejects_non_sith()
    test_boba_fett_exile_top_play_caster_is_bobas_controller()
    test_boba_fett_empty_library_no_crash()
    test_ig88_triggers_on_token_droid()
    test_holocron_tutor_filter_only_jedi_or_sith()
    test_holocron_tutor_cost_parses()
    test_search_library_handler_subtypes_any()
    test_bossk_cost_reduction_applies_to_bounty_hunters()
    test_han_solo_sacrifice_treasure_pump()
    print("\n" + "=" * 60)
    print("ALL STAR WARS SPICE TESTS PASSED!")
    print("=" * 60)
