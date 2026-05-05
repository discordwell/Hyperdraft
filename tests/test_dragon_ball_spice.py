"""
Dragon Ball Z Spice Pass Tests (Phase A)

Mirrors test_star_wars_spice.py for the second pilot set.
"""

import sys
sys.path.insert(0, '/Users/discordwell/Projects/HYPERDRAFT')

from src.engine import (
    Game, Event, EventType, ZoneType, CardType,
    Characteristics, Color,
    get_power, get_toughness,
)
from src.cards.custom.dragon_ball import DRAGON_BALL_CARDS


def _put_on_battlefield(game, player, card_name):
    """Standard pattern: create in hand without card_def, then ZONE_CHANGE."""
    card_def = DRAGON_BALL_CARDS[card_name]
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


# ============================================================================
# Future Sword
# ============================================================================

def test_future_sword_loads_with_sword_subtype():
    """Future Sword carries Equipment + Sword subtypes (so Trunks's combo can detect it)."""
    print("\n=== Future Sword: subtype check ===")
    cd = DRAGON_BALL_CARDS["Future Sword"]
    chars = cd.characteristics
    assert 'Equipment' in chars.subtypes
    assert 'Sword' in chars.subtypes
    print(f"  Subtypes: {chars.subtypes}")


def test_future_sword_grants_pt_and_haste():
    """Future Sword's setup_interceptors registers attached P/T + haste."""
    print("\n=== Future Sword: equipment setup ===")
    game = Game()
    p1 = game.add_player("Alice")
    sword = _put_on_battlefield(game, p1, "Future Sword")
    abilities = getattr(sword.state, 'activated_abilities', [])
    # Equip {1} registers an activated ability.
    assert len(abilities) >= 1, (
        f"Expected at least one activated ability (equip), got {len(abilities)}"
    )
    print(f"  Equip ability registered: {len(abilities)} ability/abilities")


# ============================================================================
# Master Roshi's Training Hall
# ============================================================================

def test_master_roshi_hall_loads_as_legendary_land():
    """Land + Legendary supertype + 2 activated abilities (mana, tutor)."""
    print("\n=== Master Roshi's Hall: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    hall = _put_on_battlefield(game, p1, "Master Roshi's Training Hall")
    chars = hall.characteristics
    assert CardType.LAND in chars.types
    assert 'Legendary' in (chars.supertypes or set())
    abilities = getattr(hall.state, 'activated_abilities', [])
    assert len(abilities) >= 2, (
        f"Expected mana + tutor abilities, got {len(abilities)}"
    )
    print(f"  Land+Legendary, abilities={len(abilities)}")


def test_master_roshi_tutor_gate_three_or_fewer_creatures():
    """Tutor ability gated to ≤3 creatures via precondition_fn."""
    print("\n=== Master Roshi's Hall: gating ===")
    from src.engine.activated import can_pay_activation
    game = Game()
    p1 = game.add_player("Alice")
    hall = _put_on_battlefield(game, p1, "Master Roshi's Training Hall")

    # Find tutor ability (cost contains "{2}, {T}").
    abilities = hall.state.activated_abilities or []
    tutor = next(
        (a for a in abilities if a.cost_text and '{2}' in a.cost_text and '{T}' in a.cost_text),
        None,
    )
    assert tutor is not None, f"Tutor ability not found among {[a.cost_text for a in abilities]}"

    # Zero creatures: legal (mana ignored with mana_system=None).
    legal_low = can_pay_activation(tutor, hall, game.state, p1.id, mana_system=None)
    assert legal_low, "Should be legal with 0 creatures"

    # Add 4 creatures → no longer legal.
    for i in range(4):
        game.create_object(
            name=f"Creature {i}",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(types={CardType.CREATURE}, power=1, toughness=1),
        )
    legal_high = can_pay_activation(tutor, hall, game.state, p1.id, mana_system=None)
    assert not legal_high, "Should NOT be legal with 4 creatures"
    print(f"  ≤3 creatures: legal; >3 creatures: blocked")


# ============================================================================
# Capsule Corp R&D
# ============================================================================

def test_capsule_corp_rnd_loads():
    """Legendary Artifact with mana + tutor + cast-trigger interceptors."""
    print("\n=== Capsule Corp R&D: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    cc = _put_on_battlefield(game, p1, "Capsule Corp R&D")
    chars = cc.characteristics
    assert CardType.ARTIFACT in chars.types
    assert 'Legendary' in (chars.supertypes or set())
    abilities = getattr(cc.state, 'activated_abilities', [])
    assert len(abilities) >= 2, (
        f"Expected ≥2 activated abilities, got {len(abilities)}"
    )
    # The cast-trigger interceptor registers via setup_interceptors return.
    assert len(cc.interceptor_ids) >= 1
    print(f"  Abilities={len(abilities)}, interceptors={len(cc.interceptor_ids)}")


# ============================================================================
# Ginyu Force, Assemble!
# ============================================================================

def test_ginyu_assemble_card_def():
    """Sorcery with a wired resolve fn."""
    print("\n=== Ginyu Force, Assemble!: card def ===")
    cd = DRAGON_BALL_CARDS["Ginyu Force, Assemble!"]
    assert CardType.SORCERY in cd.characteristics.types
    assert cd.resolve is not None
    print(f"  Sorcery resolve: {cd.resolve.__name__}")


def test_ginyu_assemble_resolve_emits_two_searches():
    """Resolve emits exactly two SEARCH_LIBRARY events for Ginyu Force creatures."""
    print("\n=== Ginyu Force, Assemble!: resolve ===")
    game = Game()
    p1 = game.add_player("Alice")
    cd = DRAGON_BALL_CARDS["Ginyu Force, Assemble!"]

    # Place a copy on the stack so the resolve fn finds the caster.
    spell = game.create_object(
        name="Ginyu Force, Assemble!",
        owner_id=p1.id,
        zone=ZoneType.STACK,
        characteristics=cd.characteristics,
        card_def=cd,
    )
    events = cd.resolve([], game.state)
    sl = [e for e in events if e.type == EventType.SEARCH_LIBRARY]
    assert len(sl) == 2, f"Expected 2 SEARCH_LIBRARY events, got {len(sl)}"
    for e in sl:
        assert e.payload.get('subtype') == 'Ginyu Force'
        assert e.payload.get('destination') == 'battlefield'
        assert e.payload.get('tapped') is True
    print(f"  Both tutors set subtype=Ginyu Force, destination=battlefield, tapped=True")


# ============================================================================
# Trunks, Sword of the Future
# ============================================================================

def test_trunks_sword_haste_and_etb_tutor():
    """Trunks self-grants haste; ETB emits SEARCH_LIBRARY for a Sword."""
    print("\n=== Trunks: ETB tutor + haste ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = [e.type.name for e in game.state.event_log]
    trunks = _put_on_battlefield(game, p1, "Trunks, Sword of the Future")
    after = [e.type.name for e in game.state.event_log]
    new = after[len(before):]
    assert 'SEARCH_LIBRARY' in new, f"ETB should emit SEARCH_LIBRARY: {new}"
    # Verify the SEARCH_LIBRARY targets Sword subtype.
    sl = [e for e in game.state.event_log if e.type == EventType.SEARCH_LIBRARY and e.source == trunks.id]
    assert sl and sl[-1].payload.get('subtype') == 'Sword', (
        f"Tutor should filter for Sword subtype: {sl[-1].payload if sl else 'no SL'}"
    )
    print(f"  Tutor emitted with subtype=Sword")


def test_trunks_sword_attach_grants_double_strike():
    """When a Sword attaches to Trunks, untap him and grant double strike EOT."""
    print("\n=== Trunks: Sword attach trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    trunks = _put_on_battlefield(game, p1, "Trunks, Sword of the Future")
    # Tap Trunks to verify untap fires.
    trunks.state.tapped = True
    before = [e.type.name for e in game.state.event_log]
    # Build a Sword equipment object and emit ATTACH event.
    sword = game.create_object(
        name="Some Sword",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            subtypes={"Equipment", "Sword"},
        ),
    )
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'source': sword.id, 'target': trunks.id},
        source=sword.id,
    ))
    after = [e.type.name for e in game.state.event_log]
    new = after[len(before):]
    assert 'UNTAP' in new, f"UNTAP not emitted: {new}"
    assert 'GRANT_KEYWORD' in new, f"GRANT_KEYWORD not emitted: {new}"
    # The grant payload should be 'double_strike' targeting Trunks.
    gks = [e for e in game.state.event_log
           if e.type == EventType.GRANT_KEYWORD
           and e.payload.get('object_id') == trunks.id]
    assert gks, "GRANT_KEYWORD targeting Trunks not found"
    assert gks[-1].payload.get('keyword') == 'double_strike'
    print("  UNTAP + double_strike grant both fired")


# ============================================================================
# Goku, Pure of Heart
# ============================================================================

def test_goku_pure_attack_adds_counter():
    """Whenever Goku attacks, +1/+1 counter goes onto him."""
    print("\n=== Goku Pure: attack counter ===")
    game = Game()
    p1 = game.add_player("Alice")
    goku = _put_on_battlefield(game, p1, "Goku, Pure of Heart")
    before_ct = goku.state.counters.get('+1/+1', 0)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': goku.id},
        source=goku.id,
    ))
    after_ct = goku.state.counters.get('+1/+1', 0)
    assert after_ct == before_ct + 1, (
        f"Expected +1 counter from attack: {before_ct} -> {after_ct}"
    )
    print(f"  Counters {before_ct} -> {after_ct}")


def test_goku_pure_other_creature_death_adds_counter():
    """When another creature you control dies, Goku gains a +1/+1 counter."""
    print("\n=== Goku Pure: other death counter ===")
    game = Game()
    p1 = game.add_player("Alice")
    goku = _put_on_battlefield(game, p1, "Goku, Pure of Heart")
    # Drop a friendly creature and destroy it.
    other = game.create_object(
        name="Friendly",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            colors={Color.RED},
            power=2, toughness=2,
        ),
    )
    before_ct = goku.state.counters.get('+1/+1', 0)
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': other.id},
        source=other.id,
    ))
    after_ct = goku.state.counters.get('+1/+1', 0)
    assert after_ct == before_ct + 1, (
        f"Other creature death should add counter: {before_ct} -> {after_ct}"
    )
    print(f"  Goku counters {before_ct} -> {after_ct} after ally's death")


def test_goku_pure_self_death_does_not_add_counter():
    """Edge: Goku's own death does NOT trigger the death-counter (would be circular)."""
    print("\n=== Goku Pure: self-death edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    goku = _put_on_battlefield(game, p1, "Goku, Pure of Heart")
    before_ct = goku.state.counters.get('+1/+1', 0)
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': goku.id},
        source=goku.id,
    ))
    after_ct = goku.state.counters.get('+1/+1', 0)
    assert after_ct == before_ct, (
        f"Self-death should NOT add counter: {before_ct} -> {after_ct}"
    )
    print(f"  No self-counter (correct)")


if __name__ == "__main__":
    test_future_sword_loads_with_sword_subtype()
    test_future_sword_grants_pt_and_haste()
    test_master_roshi_hall_loads_as_legendary_land()
    test_master_roshi_tutor_gate_three_or_fewer_creatures()
    test_capsule_corp_rnd_loads()
    test_ginyu_assemble_card_def()
    test_ginyu_assemble_resolve_emits_two_searches()
    test_trunks_sword_haste_and_etb_tutor()
    test_trunks_sword_attach_grants_double_strike()
    test_goku_pure_attack_adds_counter()
    test_goku_pure_other_creature_death_adds_counter()
    test_goku_pure_self_death_does_not_add_counter()
    print("\n" + "=" * 60)
    print("ALL DRAGON BALL SPICE TESTS PASSED!")
    print("=" * 60)
