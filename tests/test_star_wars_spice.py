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
