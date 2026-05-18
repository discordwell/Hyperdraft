"""
Lord of the Rings Spice Pass Tests (v2 EXPANSION)

Sits on top of `test_lord_of_the_rings_spice.py` (the original Phase A).
This v2 expansion adds 5 net-new cards + 3 rewired flagship Equipment.

Net-new cards:
- Frodo, Hobbit of the Shire — ring-bearer build-around mythic
- Bilbo, Brave Burglar — combat-damage impulse-draw mythic
- Eowyn, Slayer of the Witch-king — anti-Wraith hate mythic with death-trigger
- The Council of Elrond (saga) — legendary tutor → Hobbit Scout → anthem
- The Mount Doom Journey (saga) — opponent drain/discard → sac → graveyard burn

Reskinned (REWIRE) Equipment:
- Sting, Blade of Bilbo
- Glamdring, Foe-hammer
- Nenya, Ring of Adamant

Mirrors test_zelda_spice.py shape. Worktree-portable sys.path per
spice-pass.md gotcha #18 — repo root is computed from this file's location
so the test runs from any checkout (main or `.claude/worktrees/agent-*/`).
"""

import os
import sys
# Per gotcha #18: never hardcode the main-checkout path. The original
# test_lord_of_the_rings_spice.py uses Path-based parents[1], which is
# equivalent — we use os.path here to match the ZLD template exactly.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Characteristics,
    get_power, get_toughness,
)
from src.engine.queries import has_ability

# Direct import: avoid __init__.py import-graph issues; mirror
# tests/test_lord_of_the_rings_spice.py.
import importlib.util
spec = importlib.util.spec_from_file_location(
    "lord_of_the_rings",
    os.path.join(_REPO_ROOT, "src/cards/custom/lord_of_the_rings.py"),
)
lotr_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lotr_module)
LORD_OF_THE_RINGS_CARDS = lotr_module.LORD_OF_THE_RINGS_CARDS


def _put_on_battlefield(game, player, card_name):
    """Standard harness: create in hand without card_def, then ZONE_CHANGE."""
    card_def = LORD_OF_THE_RINGS_CARDS[card_name]
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
# Frodo, Hobbit of the Shire
# ============================================================================

def test_frodo_hobbit_loads():
    """Frodo registers hexproof + ETB Food + ring-bearer gating."""
    print("\n=== Frodo, Hobbit of the Shire: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    frodo = _put_on_battlefield(game, p1, "Frodo, Hobbit of the Shire")
    assert frodo.zone == ZoneType.BATTLEFIELD
    # 1 hexproof + 1 ETB + 2 PT (Q_POWER + Q_TOUGH) + 1 keyword gate = 5.
    assert len(frodo.interceptor_ids) >= 4, (
        f"Expected ≥4 interceptors, got {len(frodo.interceptor_ids)}"
    )
    assert 'Hobbit' in frodo.characteristics.subtypes
    assert 'Legendary' in frodo.characteristics.supertypes
    print(f"  Interceptors: {len(frodo.interceptor_ids)}")


def test_frodo_hobbit_has_hexproof():
    """Frodo grants hexproof to himself via QUERY_ABILITIES intercept."""
    print("\n=== Frodo, Hobbit of the Shire: hexproof ===")
    game = Game()
    p1 = game.add_player("Alice")
    frodo = _put_on_battlefield(game, p1, "Frodo, Hobbit of the Shire")
    assert has_ability(frodo, "hexproof", game.state), (
        "Frodo should have hexproof on entry"
    )
    print("  Hexproof confirmed")


def test_frodo_hobbit_etb_creates_food():
    """ETB emits CREATE_TOKEN for a Food token."""
    print("\n=== Frodo, Hobbit of the Shire: ETB food ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    frodo = _put_on_battlefield(game, p1, "Frodo, Hobbit of the Shire")
    new = game.state.event_log[before:]
    food_tokens = [
        e for e in new
        if e.type == EventType.CREATE_TOKEN
        and 'Food' in e.payload.get('token', {}).get('subtypes', set())
        and e.source == frodo.id
    ]
    assert food_tokens, f"Expected Food CREATE_TOKEN; got {[e.type.name for e in new[-10:]]}"
    print(f"  Food tokens created: {len(food_tokens)}")


def test_frodo_hobbit_ring_attached_grants_buffs():
    """When an Equipment is attached, Frodo gets +2/+2 + indestructible + lifelink."""
    print("\n=== Frodo, Hobbit of the Shire: ring-bearer payoff ===")
    game = Game()
    p1 = game.add_player("Alice")
    frodo = _put_on_battlefield(game, p1, "Frodo, Hobbit of the Shire")
    base_p = get_power(frodo, game.state)
    base_t = get_toughness(frodo, game.state)

    # Without equipment: no +2/+2 bonus, no lifelink/indestructible.
    assert not has_ability(frodo, "indestructible", game.state), (
        "Frodo should not be indestructible without a ring"
    )
    assert not has_ability(frodo, "lifelink", game.state), (
        "Frodo should not be lifelink without a ring"
    )

    # Attach The One Ring (which is an Equipment).
    ring = _put_on_battlefield(game, p1, "The One Ring")
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': ring.id, 'target_id': frodo.id},
        source=ring.id,
    ))

    new_p = get_power(frodo, game.state)
    new_t = get_toughness(frodo, game.state)
    assert new_p == base_p + 2, (
        f"Expected +2 power with ring: {base_p} → {new_p}"
    )
    assert new_t == base_t + 2, (
        f"Expected +2 toughness with ring: {base_t} → {new_t}"
    )
    assert has_ability(frodo, "indestructible", game.state), (
        "Frodo should be indestructible with ring attached"
    )
    assert has_ability(frodo, "lifelink", game.state), (
        "Frodo should have lifelink with ring attached"
    )
    print(f"  P/T {base_p}/{base_t} → {new_p}/{new_t}; indestructible + lifelink confirmed")


def test_frodo_hobbit_no_buffs_without_ring():
    """Edge: with no Equipment attached, Frodo stays at base P/T and no bonus keywords."""
    print("\n=== Frodo, Hobbit of the Shire: no-ring edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    frodo = _put_on_battlefield(game, p1, "Frodo, Hobbit of the Shire")
    # Add a non-Equipment artifact (Phial of Galadriel exists in set).
    _put_on_battlefield(game, p1, "Phial of Galadriel")
    p_after = get_power(frodo, game.state)
    assert p_after == frodo.characteristics.power, (
        f"Frodo with no Equipment should be base power; got {p_after}"
    )
    assert not has_ability(frodo, "indestructible", game.state)
    print("  No buffs without an attached Equipment")


# ============================================================================
# Bilbo, Brave Burglar
# ============================================================================

def test_bilbo_brave_burglar_loads():
    """Bilbo registers self menace + combat-damage trigger."""
    print("\n=== Bilbo, Brave Burglar: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    bilbo = _put_on_battlefield(game, p1, "Bilbo, Brave Burglar")
    assert bilbo.zone == ZoneType.BATTLEFIELD
    assert 'Hobbit' in bilbo.characteristics.subtypes
    assert 'Rogue' in bilbo.characteristics.subtypes
    assert len(bilbo.interceptor_ids) >= 2, (
        f"Expected ≥2 interceptors, got {len(bilbo.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(bilbo.interceptor_ids)}")


def test_bilbo_brave_burglar_has_menace():
    """Bilbo grants menace to himself via QUERY_ABILITIES intercept."""
    print("\n=== Bilbo, Brave Burglar: menace ===")
    game = Game()
    p1 = game.add_player("Alice")
    bilbo = _put_on_battlefield(game, p1, "Bilbo, Brave Burglar")
    assert has_ability(bilbo, "menace", game.state)
    print("  Menace confirmed")


def test_bilbo_brave_burglar_combat_damage_exiles_top():
    """Combat damage to player → EXILE_TOP_PLAY with caster=Bilbo's controller."""
    print("\n=== Bilbo, Brave Burglar: combat damage → impulse exile ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    bilbo = _put_on_battlefield(game, p1, "Bilbo, Brave Burglar")
    before = len(game.state.event_log)
    # Per gotcha #3 — EXILE_TOP_PLAY uses 'caster' key for play-permission.
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'source': bilbo.id, 'target': p2.id, 'amount': 2, 'is_combat': True},
        source=bilbo.id,
    ))
    new = game.state.event_log[before:]
    exile_events = [
        e for e in new
        if e.type == EventType.EXILE_TOP_PLAY
        and e.payload.get('caster') == p1.id
        and e.payload.get('player') == p2.id
    ]
    assert exile_events, (
        f"Expected EXILE_TOP_PLAY (caster=p1, player=p2); got {[e.type.name for e in new[-10:]]}"
    )
    print(f"  EXILE_TOP_PLAY events: {len(exile_events)}")


def test_bilbo_brave_burglar_noncombat_damage_does_not_fire():
    """Edge: noncombat damage should NOT trigger Bilbo's exile."""
    print("\n=== Bilbo, Brave Burglar: noncombat damage edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    bilbo = _put_on_battlefield(game, p1, "Bilbo, Brave Burglar")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'source': bilbo.id, 'target': p2.id, 'amount': 2, 'is_combat': False},
        source=bilbo.id,
    ))
    new = game.state.event_log[before:]
    exile_events = [
        e for e in new if e.type == EventType.EXILE_TOP_PLAY
    ]
    assert not exile_events, (
        f"Noncombat damage should not fire EXILE_TOP_PLAY; got {len(exile_events)}"
    )
    print("  Noncombat damage suppressed")


# ============================================================================
# Eowyn, Slayer of the Witch-king
# ============================================================================

def test_eowyn_slayer_loads():
    """Eowyn registers first_strike + ward {2} + damage trigger + death trigger."""
    print("\n=== Eowyn, Slayer of the Witch-king: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    eowyn = _put_on_battlefield(game, p1, "Eowyn, Slayer of the Witch-king")
    assert eowyn.zone == ZoneType.BATTLEFIELD
    # 1 first_strike kw + 1 ward + 1 damage_trig + 1 death_trig = 4.
    assert len(eowyn.interceptor_ids) >= 4, (
        f"Expected ≥4 interceptors, got {len(eowyn.interceptor_ids)}"
    )
    assert has_ability(eowyn, "first_strike", game.state)
    print(f"  Interceptors: {len(eowyn.interceptor_ids)}; first_strike confirmed")


def test_eowyn_slayer_kills_wraith_on_combat_damage():
    """Combat damage to a Wraith → DESTROY event + Eowyn +1/+1 EOT."""
    print("\n=== Eowyn, Slayer of the Witch-king: anti-Wraith trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    eowyn = _put_on_battlefield(game, p1, "Eowyn, Slayer of the Witch-king")

    # Drop an opposing Wraith.
    wraith = game.create_object(
        name="Black Rider",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wraith"},
            colors={Color.BLACK},
            power=3, toughness=3,
        ),
    )
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'source': eowyn.id, 'target': wraith.id, 'amount': 4, 'is_combat': True},
        source=eowyn.id,
    ))
    # Per gotcha #14: DESTROY is rewritten to OBJECT_DESTROYED in TRANSFORM.
    # Check the post-trigger zone — the wraith should be in the graveyard.
    assert wraith.zone == ZoneType.GRAVEYARD, (
        f"Expected Wraith in graveyard after Eowyn damage; got {wraith.zone}"
    )
    # And Eowyn should be pumped.
    new = game.state.event_log[before:]
    pt_mods = [
        e for e in new
        if e.type == EventType.PT_MODIFICATION
        and e.payload.get('object_id') == eowyn.id
        and e.payload.get('power_mod') == 1
    ]
    assert pt_mods, "Expected +1/+1 self-pump from Eowyn's damage trigger"
    print(f"  Wraith destroyed; Eowyn self-pumped +1/+1")


def test_eowyn_slayer_no_trigger_on_non_wraith():
    """Edge: damage to a non-Wraith creature should NOT destroy it."""
    print("\n=== Eowyn, Slayer of the Witch-king: non-Wraith edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    eowyn = _put_on_battlefield(game, p1, "Eowyn, Slayer of the Witch-king")

    soldier = game.create_object(
        name="Some Soldier",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Human", "Soldier"},
            colors={Color.WHITE},
            power=3, toughness=3,
        ),
    )
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'source': eowyn.id, 'target': soldier.id, 'amount': 4, 'is_combat': True},
        source=eowyn.id,
    ))
    # Soldier may still be in graveyard via normal damage rules — what we want
    # to verify is that the DESTROY event was NOT emitted by Eowyn's trigger.
    # Check that no DESTROY event sourced by Eowyn fired against the soldier.
    destroys_by_eowyn = [
        e for e in game.state.event_log
        if e.type == EventType.DESTROY
        and e.payload.get('object_id') == soldier.id
        and e.source == eowyn.id
    ]
    assert not destroys_by_eowyn, (
        f"Eowyn should not DESTROY non-Wraiths via trigger; got {len(destroys_by_eowyn)}"
    )
    print("  No Eowyn-sourced DESTROY against non-Wraith")


def test_eowyn_slayer_death_creates_two_soldiers():
    """When Eowyn dies, create two 2/2 white Human Soldier tokens."""
    print("\n=== Eowyn, Slayer of the Witch-king: death-trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    eowyn = _put_on_battlefield(game, p1, "Eowyn, Slayer of the Witch-king")
    # Force her to graveyard via direct ZONE_CHANGE (mirrors how engine
    # delivers the death event after destruction).
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': eowyn.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
        source=eowyn.id,
    ))
    new = game.state.event_log[before:]
    tokens = [
        e for e in new
        if e.type == EventType.CREATE_TOKEN
        and 'Soldier' in e.payload.get('token', {}).get('subtypes', set())
        and e.source == eowyn.id
    ]
    assert len(tokens) == 2, (
        f"Expected 2 Soldier CREATE_TOKEN events on death; got {len(tokens)}"
    )
    print(f"  Death-trigger created {len(tokens)} Soldier tokens")


# ============================================================================
# Sting, Blade of Bilbo (REWIRE)
# ============================================================================

def test_sting_rewired_loads_with_keywords():
    """Sting (rewired) is Legendary Equipment with PT/keyword + equip ability."""
    print("\n=== Sting (rewired): load ===")
    game = Game()
    p1 = game.add_player("Alice")
    sting = _put_on_battlefield(game, p1, "Sting, Blade of Bilbo")
    chars = sting.characteristics
    assert CardType.ARTIFACT in chars.types
    assert 'Equipment' in chars.subtypes
    assert 'Legendary' in chars.supertypes
    abilities = getattr(sting.state, 'activated_abilities', [])
    assert len(abilities) >= 1, f"Expected equip ability; got {len(abilities)}"
    # PT interceptors + keyword interceptor expected.
    assert len(sting.interceptor_ids) >= 2, (
        f"Expected ≥2 interceptors (PT + keyword); got {len(sting.interceptor_ids)}"
    )
    print(f"  Loaded; interceptors={len(sting.interceptor_ids)}, equip_abilities={len(abilities)}")


def test_sting_rewired_attach_grants_pt_and_keywords():
    """When Sting is attached, equipped creature gets +1/+2 + first_strike +
    hexproof + lifelink."""
    print("\n=== Sting (rewired): attach grants P/T + keywords ===")
    game = Game()
    p1 = game.add_player("Alice")
    sting = _put_on_battlefield(game, p1, "Sting, Blade of Bilbo")
    creature = game.create_object(
        name="Test Hobbit",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Hobbit"},
            power=1, toughness=1,
        ),
    )
    base_p = get_power(creature, game.state)
    base_t = get_toughness(creature, game.state)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': sting.id, 'target_id': creature.id},
        source=sting.id,
    ))
    new_p = get_power(creature, game.state)
    new_t = get_toughness(creature, game.state)
    assert new_p == base_p + 1, f"P: {base_p} → {new_p} (expected +1)"
    assert new_t == base_t + 2, f"T: {base_t} → {new_t} (expected +2)"
    assert has_ability(creature, "first_strike", game.state)
    assert has_ability(creature, "hexproof", game.state)
    assert has_ability(creature, "lifelink", game.state)
    print(f"  Hobbit {base_p}/{base_t} → {new_p}/{new_t}; first_strike+hexproof+lifelink")


# ============================================================================
# Glamdring, Foe-hammer (REWIRE)
# ============================================================================

def test_glamdring_rewired_attach_grants_pt_and_vigilance():
    """When Glamdring is attached, equipped creature gets +3/+2 + vigilance + ward {1}."""
    print("\n=== Glamdring (rewired): attach grants P/T + keywords ===")
    game = Game()
    p1 = game.add_player("Alice")
    glamdring = _put_on_battlefield(game, p1, "Glamdring, Foe-hammer")
    creature = game.create_object(
        name="Test Wizard",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wizard"},
            power=2, toughness=2,
        ),
    )
    base_p = get_power(creature, game.state)
    base_t = get_toughness(creature, game.state)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': glamdring.id, 'target_id': creature.id},
        source=glamdring.id,
    ))
    new_p = get_power(creature, game.state)
    new_t = get_toughness(creature, game.state)
    assert new_p == base_p + 3, f"P: {base_p} → {new_p} (expected +3)"
    assert new_t == base_t + 2, f"T: {base_t} → {new_t} (expected +2)"
    assert has_ability(creature, "vigilance", game.state)
    print(f"  Wizard {base_p}/{base_t} → {new_p}/{new_t}; vigilance confirmed")


# ============================================================================
# Nenya, Ring of Adamant (REWIRE)
# ============================================================================

def test_nenya_rewired_attach_grants_protection():
    """When Nenya is attached, equipped creature gets +1/+3 + hexproof + ward {2}."""
    print("\n=== Nenya (rewired): attach grants protection ===")
    game = Game()
    p1 = game.add_player("Alice")
    nenya = _put_on_battlefield(game, p1, "Nenya, Ring of Adamant")
    chars = nenya.characteristics
    assert 'Ring' in chars.subtypes
    assert 'Equipment' in chars.subtypes
    assert 'Legendary' in chars.supertypes

    creature = game.create_object(
        name="Test Elf",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Elf"},
            power=2, toughness=2,
        ),
    )
    base_p = get_power(creature, game.state)
    base_t = get_toughness(creature, game.state)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': nenya.id, 'target_id': creature.id},
        source=nenya.id,
    ))
    new_p = get_power(creature, game.state)
    new_t = get_toughness(creature, game.state)
    assert new_p == base_p + 1, f"P: {base_p} → {new_p} (expected +1)"
    assert new_t == base_t + 3, f"T: {base_t} → {new_t} (expected +3)"
    assert has_ability(creature, "hexproof", game.state)
    print(f"  Elf {base_p}/{base_t} → {new_p}/{new_t}; hexproof confirmed")


# ============================================================================
# The Council of Elrond (saga)
# ============================================================================

def test_the_council_of_elrond_loads_saga():
    """Saga registers chapter dispatcher interceptors."""
    print("\n=== The Council of Elrond: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Council of Elrond")
    chars = saga.characteristics
    assert CardType.ENCHANTMENT in chars.types
    assert 'Saga' in chars.subtypes
    assert 'Legendary' in chars.supertypes
    assert saga.interceptor_ids, "Expected saga chapter interceptors"
    print(f"  Saga loaded with {len(saga.interceptor_ids)} interceptors")


def test_the_council_of_elrond_chapter_i_tutors_legendary():
    """Direct chapter-I dispatch emits SEARCH_LIBRARY for legendary MV≤3."""
    print("\n=== The Council of Elrond: chapter I ===")
    fn = lotr_module._the_council_of_elrond_chapter_i
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Council of Elrond")
    events = fn(saga, game.state)
    assert events and events[0].type == EventType.SEARCH_LIBRARY
    payload = events[0].payload
    assert payload.get('supertype') == 'Legendary'
    assert payload.get('card_type') == 'creature'
    assert payload.get('mana_value_max') == 3
    assert payload.get('destination') == 'hand'
    print("  Chapter I emits SEARCH_LIBRARY (Legendary, MV≤3, → hand)")


def test_the_council_of_elrond_chapter_ii_creates_hobbit_scout():
    """Chapter II creates a 1/1 white Hobbit Scout token."""
    print("\n=== The Council of Elrond: chapter II ===")
    fn = lotr_module._the_council_of_elrond_chapter_ii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Council of Elrond")
    events = fn(saga, game.state)
    tokens = [
        e for e in events
        if e.type == EventType.CREATE_TOKEN
        and 'Hobbit' in e.payload.get('token', {}).get('subtypes', set())
    ]
    assert len(tokens) == 1, f"Expected 1 Hobbit Scout token; got {len(tokens)}"
    tok = tokens[0].payload['token']
    assert tok.get('power') == 1
    assert tok.get('toughness') == 1
    assert 'Scout' in tok.get('subtypes', set())
    print(f"  Chapter II creates {len(tokens)} Hobbit Scout token")


def test_the_council_of_elrond_chapter_iii_pumps_legendaries_only():
    """Chapter III pumps OTHER legendary creatures +2/+2 and grants flying."""
    print("\n=== The Council of Elrond: chapter III ===")
    fn = lotr_module._the_council_of_elrond_chapter_iii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Council of Elrond")

    # Drop a legendary and a non-legendary.
    legend = game.create_object(
        name="Some Legend",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Human"},
            supertypes={"Legendary"},
            power=3, toughness=3,
        ),
    )
    plain = game.create_object(
        name="Some Plain Creature",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Human"},
            power=2, toughness=2,
        ),
    )
    events = fn(saga, game.state)
    pt_targets = [e.payload['object_id'] for e in events
                  if e.type == EventType.PT_MODIFICATION]
    fly_targets = [e.payload['object_id'] for e in events
                   if e.type == EventType.GRANT_KEYWORD
                   and e.payload.get('keyword') == 'flying']
    assert legend.id in pt_targets, f"Legendary not buffed: {pt_targets}"
    assert plain.id not in pt_targets, f"Plain creature should NOT be buffed: {pt_targets}"
    assert legend.id in fly_targets, f"Legendary should gain flying: {fly_targets}"
    assert saga.id not in pt_targets, f"Saga should not buff itself: {pt_targets}"
    print(f"  Chapter III pumps only legendaries; saga excluded from buff")


# ============================================================================
# The Mount Doom Journey (saga)
# ============================================================================

def test_the_mount_doom_journey_loads_saga():
    """Saga registers chapter dispatcher interceptors."""
    print("\n=== The Mount Doom Journey: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Mount Doom Journey")
    chars = saga.characteristics
    assert CardType.ENCHANTMENT in chars.types
    assert 'Saga' in chars.subtypes
    assert 'Legendary' in chars.supertypes
    assert saga.interceptor_ids, "Expected saga chapter interceptors"
    print(f"  Saga loaded with {len(saga.interceptor_ids)} interceptors")


def test_the_mount_doom_journey_chapter_i_drains_each_opp():
    """Chapter I emits -2 LIFE_CHANGE + DISCARD for each opponent."""
    print("\n=== The Mount Doom Journey: chapter I ===")
    fn = lotr_module._mount_doom_journey_chapter_i
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    p3 = game.add_player("Carol")
    saga = _put_on_battlefield(game, p1, "The Mount Doom Journey")
    events = fn(saga, game.state)
    life_changes = [e for e in events if e.type == EventType.LIFE_CHANGE]
    discards = [e for e in events if e.type == EventType.DISCARD]
    # Two opponents → two life changes and two discards (controller untouched).
    drained_players = {e.payload['player'] for e in life_changes}
    discard_players = {e.payload['player'] for e in discards}
    assert drained_players == {p2.id, p3.id}, (
        f"Expected only opps drained; got {drained_players}"
    )
    assert discard_players == {p2.id, p3.id}, (
        f"Expected only opps discarding; got {discard_players}"
    )
    assert all(e.payload['amount'] == -2 for e in life_changes)
    print(f"  Chapter I drains 2 life + discard from {len(drained_players)} opp(s)")


def test_the_mount_doom_journey_chapter_ii_each_opp_sacs():
    """Chapter II emits SACRIFICE_REQUIRED for each opponent."""
    print("\n=== The Mount Doom Journey: chapter II ===")
    fn = lotr_module._mount_doom_journey_chapter_ii
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    saga = _put_on_battlefield(game, p1, "The Mount Doom Journey")
    events = fn(saga, game.state)
    sacs = [
        e for e in events
        if e.type == EventType.SACRIFICE_REQUIRED
        and e.payload.get('card_type') == 'creature'
    ]
    # Saga's controller should NOT sacrifice.
    sac_players = {e.payload['player'] for e in sacs}
    assert p1.id not in sac_players, "Controller should not be required to sacrifice"
    assert p2.id in sac_players, "Opponent should sacrifice"
    print(f"  Chapter II forces sacrifice on {len(sac_players)} opp(s)")


def test_the_mount_doom_journey_chapter_iii_burns_for_graveyard():
    """Chapter III drains opp = 2 × (creatures in their graveyard)."""
    print("\n=== The Mount Doom Journey: chapter III ===")
    fn = lotr_module._mount_doom_journey_chapter_iii
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    saga = _put_on_battlefield(game, p1, "The Mount Doom Journey")

    # Plant 3 creatures in p2's graveyard.
    gy = game.state.zones.get(f'graveyard_{p2.id}')
    assert gy is not None, "Expected graveyard zone for p2"
    for i in range(3):
        co = game.create_object(
            name=f"Dead Orc {i}",
            owner_id=p2.id,
            zone=ZoneType.GRAVEYARD,
            characteristics=Characteristics(
                types={CardType.CREATURE},
                subtypes={"Orc"},
                power=1, toughness=1,
            ),
        )
        if co.id not in gy.objects:
            gy.objects.append(co.id)
    # Plant 1 non-creature card (sorcery) — should NOT count.
    sorc = game.create_object(
        name="Some Spell",
        owner_id=p2.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=Characteristics(types={CardType.SORCERY}),
    )
    if sorc.id not in gy.objects:
        gy.objects.append(sorc.id)

    events = fn(saga, game.state)
    drains = [
        e for e in events
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
    ]
    assert drains, "Expected drain on opp"
    # 2 × 3 = -6.
    assert drains[0].payload.get('amount') == -6, (
        f"Expected -6 drain (2 × 3 creatures); got {drains[0].payload.get('amount')}"
    )
    print(f"  Chapter III drains 6 life from opp (3 creatures × 2)")


def test_the_mount_doom_journey_chapter_iii_no_drain_if_empty_gy():
    """Chapter III emits no drain when opponent's graveyard has no creatures."""
    print("\n=== The Mount Doom Journey: chapter III empty graveyard ===")
    fn = lotr_module._mount_doom_journey_chapter_iii
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    saga = _put_on_battlefield(game, p1, "The Mount Doom Journey")
    events = fn(saga, game.state)
    drains = [
        e for e in events
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
    ]
    assert not drains, "Empty graveyard should produce no drain"
    print("  No drain on empty graveyard")


# ============================================================================
# Cross-card integration: registry + no name collisions
# ============================================================================

def test_spice_v2_cards_in_registry():
    """All v2 expansion cards live in LORD_OF_THE_RINGS_CARDS."""
    print("\n=== Spice V2 registry ===")
    expected = [
        # Net-new
        "Frodo, Hobbit of the Shire",
        "Bilbo, Brave Burglar",
        "Eowyn, Slayer of the Witch-king",
        "The Council of Elrond",
        "The Mount Doom Journey",
        # Rewires keep their original names but point at new defs.
        "Sting, Blade of Bilbo",
        "Glamdring, Foe-hammer",
        "Nenya, Ring of Adamant",
    ]
    for name in expected:
        cd = LORD_OF_THE_RINGS_CARDS.get(name)
        assert cd is not None, f"{name} missing or None in registry"
        assert cd.setup_interceptors is not None, (
            f"{name} should have wired setup_interceptors (V2 rewire)"
        )
    print(f"  All {len(expected)} V2 cards present with setup_interceptors")


def test_spice_v2_no_name_collisions_with_existing_legends():
    """V2 variants coexist with their vanilla counterparts (no name collisions)."""
    print("\n=== Spice V2: no name collisions ===")
    # Both Frodo variants exist.
    assert "Frodo, the Ring-bearer" in LORD_OF_THE_RINGS_CARDS
    assert "Frodo, Hobbit of the Shire" in LORD_OF_THE_RINGS_CARDS
    # Both Eowyn variants exist.
    assert "Eowyn, Shieldmaiden of Rohan" in LORD_OF_THE_RINGS_CARDS
    assert "Eowyn, Slayer of the Witch-king" in LORD_OF_THE_RINGS_CARDS
    # The existing "Council of Elrond" (sorcery) coexists with the new
    # "The Council of Elrond" (saga).
    assert "Council of Elrond" in LORD_OF_THE_RINGS_CARDS
    assert "The Council of Elrond" in LORD_OF_THE_RINGS_CARDS
    cle = LORD_OF_THE_RINGS_CARDS["Council of Elrond"]
    tcle = LORD_OF_THE_RINGS_CARDS["The Council of Elrond"]
    assert CardType.SORCERY in cle.characteristics.types
    assert 'Saga' in tcle.characteristics.subtypes
    # The existing land "Mount Doom" coexists with the new saga.
    assert "Mount Doom" in LORD_OF_THE_RINGS_CARDS
    assert "The Mount Doom Journey" in LORD_OF_THE_RINGS_CARDS
    mt = LORD_OF_THE_RINGS_CARDS["Mount Doom"]
    tmdj = LORD_OF_THE_RINGS_CARDS["The Mount Doom Journey"]
    assert CardType.LAND in mt.characteristics.types
    assert 'Saga' in tmdj.characteristics.subtypes
    print("  All V2 cards differentiated from vanilla counterparts")


def test_spice_v2_rewires_are_wired():
    """Sting / Glamdring / Nenya now have setup_interceptors (were vanilla)."""
    print("\n=== Spice V2: rewired equipment has wiring ===")
    rewired = [
        "Sting, Blade of Bilbo",
        "Glamdring, Foe-hammer",
        "Nenya, Ring of Adamant",
    ]
    for name in rewired:
        cd = LORD_OF_THE_RINGS_CARDS[name]
        assert cd.setup_interceptors is not None, f"{name} should be wired"
        # Equipment characteristics preserved.
        assert CardType.ARTIFACT in cd.characteristics.types
        assert 'Equipment' in cd.characteristics.subtypes
        assert 'Legendary' in cd.characteristics.supertypes
    print(f"  All {len(rewired)} REWIRE cards confirmed wired")


# ============================================================================
# Runner — direct execution without pytest
# ============================================================================

def _run_all():
    import traceback
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = 0
    failed = []
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed.append((t.__name__, e))
            print(f"  FAILED: {t.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{'='*60}\nTotal: {passed}/{len(tests)} passed")
    if failed:
        print("Failures:")
        for name, e in failed:
            print(f"  {name}: {e}")
    return len(failed) == 0


if __name__ == "__main__":
    success = _run_all()
    sys.exit(0 if success else 1)
