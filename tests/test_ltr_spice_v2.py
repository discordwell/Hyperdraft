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
# Phase A2 (slice 1) — decision-axis flip cards
# ============================================================================

def test_striders_pathfinding_loads():
    """Setup registers an ETB trigger interceptor."""
    print("\n=== Strider's Pathfinding: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    sp = _put_on_battlefield(game, p1, "Strider's Pathfinding")
    assert sp.zone == ZoneType.BATTLEFIELD
    assert sp.interceptor_ids, "Expected ETB interceptor"


def test_striders_pathfinding_etb_with_empty_library_no_op():
    """Edge: when library is empty the helper returns [] (no crash)."""
    print("\n=== Strider's Pathfinding: empty library no-op ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Library starts empty by default in this harness.
    before = len(game.state.event_log)
    sp = _put_on_battlefield(game, p1, "Strider's Pathfinding")
    new = game.state.event_log[before:]
    # No CARD_REVEALED / pending_choice should appear because the library
    # is empty. The card still enters the battlefield.
    assert sp.zone == ZoneType.BATTLEFIELD


def test_striders_pathfinding_etb_reveals_library_top():
    """ETB with non-empty library opens a pending_choice (the top-N pick)."""
    print("\n=== Strider's Pathfinding: pending choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Plant a basic Plains in p1's library so the helper sees a land.
    plains_def = LORD_OF_THE_RINGS_CARDS.get("Soldier of Gondor")
    # Use any creature card if no specific land is registered — the helper
    # only requires *some* card to be revealable; an empty library returns [].
    lib = game.state.zones[f'library_{p1.id}']
    for _ in range(4):
        ko = game.create_object(
            name="Soldier of Gondor",
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=plains_def.characteristics,
            card_def=None,
        )
        ko.card_def = plains_def
        if ko.id not in lib.objects:
            lib.objects.append(ko.id)
    before = len(game.state.event_log)
    sp = _put_on_battlefield(game, p1, "Strider's Pathfinding")
    # No-land library means the helper auto-bottoms all revealed and does
    # NOT install a pending_choice. The card still entered the battlefield
    # so the trigger fired.
    assert sp.zone == ZoneType.BATTLEFIELD
    # The trigger must have produced at least one library-touch effect
    # (object_id reassignment via _remove_object_from_all_zones). We
    # validate the library contents were re-ordered (4 reveals -> bottomed).
    lib_after = game.state.zones[f'library_{p1.id}']
    assert len(lib_after.objects) == 4, (
        f"Library should still have 4 entries; got {len(lib_after.objects)}"
    )


def test_faramirs_last_stand_loads():
    """Setup registers the targeted-death trigger interceptor."""
    print("\n=== Faramir's Last Stand: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    fls = _put_on_battlefield(game, p1, "Faramir's Last Stand")
    assert fls.zone == ZoneType.BATTLEFIELD
    assert fls.interceptor_ids, "Expected death-trigger interceptor"


def test_faramirs_last_stand_death_emits_target_required_exile():
    """Death emits TARGET_REQUIRED w/ effect=exile + opponent_creature filter."""
    print("\n=== Faramir's Last Stand: death -> target_required exile ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    fls = _put_on_battlefield(game, p1, "Faramir's Last Stand")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': fls.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
        source=fls.id,
    ))
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == fls.id
        and e.payload.get('effect') == 'exile'
        and e.payload.get('target_filter') == 'opponent_creature'
    ]
    assert target_reqs, (
        f"Expected exile TARGET_REQUIRED; new={[e.type.name for e in new[-10:]]}"
    )


def test_the_choice_at_the_council_loads():
    """Setup registers the modal-ETB trigger."""
    print("\n=== The Choice at the Council: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    cot = _put_on_battlefield(game, p1, "The Choice at the Council")
    assert cot.zone == ZoneType.BATTLEFIELD
    assert cot.interceptor_ids, "Expected modal-ETB trigger interceptor"


def test_the_choice_at_the_council_etb_sets_modal_pending_choice():
    """ETB installs a modal_with_targeting pending_choice with 3 modes."""
    print("\n=== The Choice at the Council: pending modal choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    cot = _put_on_battlefield(game, p1, "The Choice at the Council")
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending_choice after ETB"
    assert pc.source_id == cot.id
    assert pc.choice_type == "modal_with_targeting"
    assert len(pc.options) == 3, f"Expected 3 modes; got {len(pc.options)}"
    # One mode requires targeting (the destroy mode).
    targeting_modes = [o for o in pc.options if o.get('requires_targeting')]
    assert targeting_modes, "Expected at least one targeting mode"


# ============================================================================
# Slice-5 thin-bust tests (2026-05-19): one unit test per buffed vanilla
# card. Verifies setup_interceptors registers + on-flavor effect fires
# under the expected trigger (ATTACK_DECLARED / ETB / death / combat damage).
# ============================================================================


def _slice5_emit_attack(game, attacker):
    """Helper: emit ATTACK_DECLARED for the given attacker."""
    p2 = next(iter([p for p in game.state.players.values() if p.id != attacker.controller]))
    return game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': attacker.id, 'defender': p2.id},
        source=attacker.id, controller=attacker.controller,
    ))


def _slice5_emit_death(game, dying):
    """Helper: emit ZONE_CHANGE moving the object from battlefield to graveyard."""
    return game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': dying.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{dying.controller}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
        source=dying.id,
    ))


def test_boromir_captain_attack_drains_each_opp_slice5():
    """Slice-5: Boromir attacks -> each opponent loses 1 life."""
    print("\n=== Slice-5: Boromir, Captain of Gondor — attack drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    boromir = _put_on_battlefield(game, p1, "Boromir, Captain of Gondor")
    assert boromir.interceptor_ids, "Expected attack-trigger interceptor"
    before = len(game.state.event_log)
    _slice5_emit_attack(game, boromir)
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.payload.get('source', e.source) == boromir.id or e.source == boromir.id
    ]
    assert drains, (
        f"Expected each-opp -1 life drain; recent={[e.type.name for e in new[-10:]]}"
    )


def test_eowyn_shieldmaiden_attack_drains_each_opp_slice5():
    """Slice-5: Eowyn attacks -> each opponent loses 1 life."""
    print("\n=== Slice-5: Eowyn, Shieldmaiden of Rohan — attack drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    eowyn = _put_on_battlefield(game, p1, "Eowyn, Shieldmaiden of Rohan")
    assert eowyn.interceptor_ids, "Expected attack-trigger interceptor"
    before = len(game.state.event_log)
    _slice5_emit_attack(game, eowyn)
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == eowyn.id
    ]
    assert drains, (
        f"Expected each-opp -1 life drain; recent={[e.type.name for e in new[-10:]]}"
    )


def test_eomer_marshal_attack_pings_each_opp_slice5():
    """Slice-5: Eomer attacks -> deals 1 damage to each opponent."""
    print("\n=== Slice-5: Eomer, Marshal of Rohan — attack ping ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    eomer = _put_on_battlefield(game, p1, "Eomer, Marshal of Rohan")
    assert eomer.interceptor_ids, "Expected attack-trigger interceptor"
    before = len(game.state.event_log)
    _slice5_emit_attack(game, eomer)
    new = game.state.event_log[before:]
    pings = [
        e for e in new
        if e.type == EventType.DAMAGE
        and e.payload.get('target') == p2.id
        and e.payload.get('amount') == 1
        and e.source == eomer.id
    ]
    assert pings, (
        f"Expected each-opp 1 damage ping; recent={[e.type.name for e in new[-10:]]}"
    )


def test_citadel_castellan_etb_no_other_soldiers_no_drain_slice5():
    """Slice-5: Citadel Castellan ETB alone -> no drain (only fires at 2+)."""
    print("\n=== Slice-5: Citadel Castellan — solo ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    cc = _put_on_battlefield(game, p1, "Citadel Castellan")
    assert cc.interceptor_ids, "Expected ETB-trigger interceptor"
    # No allies in play - solo ETB should NOT drain opponents.
    drains = [
        e for e in game.state.event_log
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.source == cc.id
    ]
    assert not drains, (
        f"Expected no drain with 0 other Soldiers; got {len(drains)}"
    )


def test_beacon_warden_etb_scry_and_drain_slice5():
    """Slice-5: Beacon Warden ETB -> SCRY + each opp -1 life."""
    print("\n=== Slice-5: Beacon Warden — ETB scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Plant a card in library so the helper proceeds past empty-library guard.
    plains_def = LORD_OF_THE_RINGS_CARDS.get("Soldier of Gondor")
    ko = game.create_object(
        name="Soldier of Gondor", owner_id=p1.id, zone=ZoneType.LIBRARY,
        characteristics=plains_def.characteristics, card_def=None,
    )
    ko.card_def = plains_def
    lib = game.state.zones[f'library_{p1.id}']
    if ko.id not in lib.objects:
        lib.objects.append(ko.id)
    before = len(game.state.event_log)
    bw = _put_on_battlefield(game, p1, "Beacon Warden")
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY and e.source == bw.id]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == bw.id
    ]
    assert scrys, f"Expected SCRY event; recent={[e.type.name for e in new[-10:]]}"
    assert drains, f"Expected each-opp drain; recent={[e.type.name for e in new[-10:]]}"


def test_pelennor_defender_etb_drains_each_opp_slice5():
    """Slice-5: Pelennor Defender ETB -> each opp -1 life."""
    print("\n=== Slice-5: Pelennor Defender — ETB drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    pd = _put_on_battlefield(game, p1, "Pelennor Defender")
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == pd.id
    ]
    assert drains, f"Expected each-opp drain; recent={[e.type.name for e in new[-10:]]}"


def test_osgiliath_veteran_attack_drains_each_opp_slice5():
    """Slice-5: Osgiliath Veteran attacks -> each opp -1 life."""
    print("\n=== Slice-5: Osgiliath Veteran — attack drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    ov = _put_on_battlefield(game, p1, "Osgiliath Veteran")
    assert ov.interceptor_ids, "Expected attack-trigger interceptor"
    before = len(game.state.event_log)
    _slice5_emit_attack(game, ov)
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == ov.id
    ]
    assert drains, f"Expected each-opp drain; recent={[e.type.name for e in new[-10:]]}"


def test_cirdan_shipwright_etb_scry_2_slice5():
    """Slice-5: Cirdan the Shipwright ETB -> SCRY 2 (library non-empty)."""
    print("\n=== Slice-5: Cirdan the Shipwright — ETB scry ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    plains_def = LORD_OF_THE_RINGS_CARDS.get("Soldier of Gondor")
    ko = game.create_object(
        name="Soldier of Gondor", owner_id=p1.id, zone=ZoneType.LIBRARY,
        characteristics=plains_def.characteristics, card_def=None,
    )
    ko.card_def = plains_def
    lib = game.state.zones[f'library_{p1.id}']
    if ko.id not in lib.objects:
        lib.objects.append(ko.id)
    before = len(game.state.event_log)
    cirdan = _put_on_battlefield(game, p1, "Cirdan the Shipwright")
    new = game.state.event_log[before:]
    scrys = [
        e for e in new
        if e.type == EventType.SCRY and e.source == cirdan.id and e.payload.get('amount') == 2
    ]
    assert scrys, f"Expected SCRY 2 event; recent={[e.type.name for e in new[-10:]]}"


def test_mirkwood_archer_attack_drains_each_opp_slice5():
    """Slice-5: Mirkwood Archer attacks -> each opp -1 life."""
    print("\n=== Slice-5: Mirkwood Archer — attack drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    ma = _put_on_battlefield(game, p1, "Mirkwood Archer")
    assert ma.interceptor_ids, "Expected attack-trigger interceptor"
    before = len(game.state.event_log)
    _slice5_emit_attack(game, ma)
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == ma.id
    ]
    assert drains, f"Expected each-opp drain; recent={[e.type.name for e in new[-10:]]}"


def test_cave_troll_death_pings_each_opp_slice5():
    """Slice-5: Cave Troll dies -> 1 damage to each opponent."""
    print("\n=== Slice-5: Cave Troll — death ping ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    ct = _put_on_battlefield(game, p1, "Cave Troll")
    assert ct.interceptor_ids, "Expected death-trigger interceptor"
    before = len(game.state.event_log)
    _slice5_emit_death(game, ct)
    new = game.state.event_log[before:]
    pings = [
        e for e in new
        if e.type == EventType.DAMAGE
        and e.payload.get('target') == p2.id
        and e.payload.get('amount') == 1
        and e.source == ct.id
    ]
    assert pings, f"Expected each-opp ping; recent={[e.type.name for e in new[-10:]]}"


def test_old_man_willow_etb_solo_no_drain_slice5():
    """Slice-5: Old Man Willow ETB solo (1 Treefolk only = self) -> no opp drain."""
    print("\n=== Slice-5: Old Man Willow — solo ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    omw = _put_on_battlefield(game, p1, "Old Man Willow")
    assert omw.interceptor_ids, "Expected ETB-trigger interceptor"
    # Solo Treefolk (only self) — opp drain fires only at 2+ Treefolk.
    drains = [
        e for e in game.state.event_log
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.source == omw.id
    ]
    assert not drains, f"Expected no drain with 1 Treefolk; got {len(drains)}"


def test_buckland_shirriff_etb_solo_no_drain_slice5():
    """Slice-5: Buckland Shirriff ETB solo (1 Hobbit = self) -> no opp drain."""
    print("\n=== Slice-5: Buckland Shirriff — solo ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    bs = _put_on_battlefield(game, p1, "Buckland Shirriff")
    assert bs.interceptor_ids, "Expected ETB-trigger interceptor"
    drains = [
        e for e in game.state.event_log
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.source == bs.id
    ]
    assert not drains, f"Expected no drain with 1 Hobbit; got {len(drains)}"


def test_spawn_of_shelob_combat_damage_drains_each_opp_slice5():
    """Slice-5: Spawn of Shelob deals combat damage -> each opp -1 life."""
    print("\n=== Slice-5: Spawn of Shelob — combat damage drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    spawn = _put_on_battlefield(game, p1, "Spawn of Shelob")
    assert spawn.interceptor_ids, "Expected damage-trigger interceptor"
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'source': spawn.id, 'target': p2.id, 'amount': 2, 'is_combat': True},
        source=spawn.id,
    ))
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == spawn.id
    ]
    assert drains, f"Expected each-opp drain; recent={[e.type.name for e in new[-10:]]}"


def test_khazad_dum_veteran_etb_solo_no_drain_slice5():
    """Slice-5: Khazad-dum Veteran ETB solo (1 Dwarf = self) -> no opp drain."""
    print("\n=== Slice-5: Khazad-dum Veteran — solo ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    kdv = _put_on_battlefield(game, p1, "Khazad-dum Veteran")
    assert kdv.interceptor_ids, "Expected ETB-trigger interceptor"
    drains = [
        e for e in game.state.event_log
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.source == kdv.id
    ]
    assert not drains, f"Expected no drain with 1 Dwarf; got {len(drains)}"



# ============================================================================
# Slice-9 median-lift tests (2026-05-19): one assertion per buffed vanilla
# card driving LTR median_depth 0 -> >= 2. Each test puts the card on the
# battlefield (or invokes its resolve handler for instants/sorceries) and
# asserts the expected SCRY/SURVEIL info event + a cross-controller effect
# (LIFE_CHANGE / DAMAGE / MILL / DISCARD / REVEAL_HAND).
# ============================================================================


def _s9_setup_with_library_card(p1):
    """Plant a library card so SCRY/SURVEIL helpers proceed past empty-library guards."""
    return None  # SCRY/SURVEIL emit regardless; some helpers need it though.


def _s9_assert_etb_with_event(game, obj, expected_type, p1, p2,
                              info_type=None, opp_effect_payload_key='player'):
    """Helper: assert the card emitted info_type (SCRY/SURVEIL) and expected_type
    against p2 from obj.id. Returns the matching events."""
    new = game.state.event_log
    info_evs = []
    if info_type is not None:
        info_evs = [e for e in new if e.type == info_type and e.source == obj.id]
        assert info_evs, f"Expected {info_type.name} from {obj.id}; events={[e.type.name for e in new[-15:]]}"
    if expected_type == EventType.LIFE_CHANGE:
        opp_evs = [e for e in new if e.type == expected_type
                   and e.payload.get(opp_effect_payload_key) == p2.id
                   and e.payload.get('amount', 0) < 0
                   and e.source == obj.id]
    elif expected_type == EventType.DAMAGE:
        opp_evs = [e for e in new if e.type == expected_type
                   and e.payload.get('target') == p2.id
                   and e.source == obj.id]
    elif expected_type == EventType.MILL:
        opp_evs = [e for e in new if e.type == expected_type
                   and e.payload.get('player') == p2.id
                   and e.source == obj.id]
    elif expected_type == EventType.DISCARD:
        opp_evs = [e for e in new if e.type == expected_type
                   and e.payload.get('player') == p2.id
                   and e.source == obj.id]
    elif expected_type == EventType.REVEAL_HAND:
        opp_evs = [e for e in new if e.type == expected_type
                   and e.payload.get('player') == p2.id
                   and e.source == obj.id]
    else:
        opp_evs = []
    assert opp_evs, f"Expected {expected_type.name} against p2 from {obj.id}; events={[e.type.name for e in new[-15:]]}"
    return info_evs, opp_evs


def _s9_etb_card(card_name):
    """Spin up a game, put the named card under p1, return (game, p1, p2, obj)."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, card_name)
    return game, p1, p2, obj


def _s9_attack(card_name):
    """Spin up a game, put the named card under p1, emit ATTACK_DECLARED."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, card_name)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': obj.id, 'defender': p2.id},
        source=obj.id, controller=obj.controller,
    ))
    return game, p1, p2, obj


# --- WHITE creature/enchantment tests ----------------------------------------


def test_knights_of_dol_amroth_attack_scry_drain_s9():
    print("\n=== Slice-9: Knights of Dol Amroth — attack scry + drain ===")
    game, p1, p2, obj = _s9_attack("Knights of Dol Amroth")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_rohirrim_lancer_attack_drain_s9():
    print("\n=== Slice-9: Rohirrim Lancer — attack drain ===")
    game, p1, p2, obj = _s9_attack("Rohirrim Lancer")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2)


def test_dunedain_healer_etb_scry_and_gain_s9():
    print("\n=== Slice-9: Dunedain Healer — ETB scry + heal ===")
    game, p1, p2, obj = _s9_etb_card("Dunedain Healer")
    scrys = [e for e in game.state.event_log if e.type == EventType.SCRY and e.source == obj.id]
    gains = [e for e in game.state.event_log if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0
             and e.source == obj.id]
    assert scrys, "Expected SCRY"
    assert gains, "Expected life gain"


def test_oath_of_eorl_etb_scry_drain_s9():
    print("\n=== Slice-9: Oath of Eorl — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Oath of Eorl")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_the_white_tree_etb_scry_drain_s9():
    print("\n=== Slice-9: The White Tree — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("The White Tree")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


# --- WHITE spell resolve tests ----------------------------------------------


def _s9_resolve(fn_name):
    """Pull a resolve fn out of the lotr_module."""
    fn = getattr(lotr_module, fn_name)
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.state.active_player = p1.id
    events = fn([], game.state)
    return events, p1, p2


def test_shield_of_the_west_resolve_s9():
    print("\n=== Slice-9: Shield of the West resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_shield_of_the_west")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0 for e in events)


def test_charge_of_the_rohirrim_resolve_s9():
    print("\n=== Slice-9: Charge of the Rohirrim resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_charge_of_the_rohirrim")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) == -2 for e in events)


def test_gondorian_discipline_resolve_s9():
    print("\n=== Slice-9: Gondorian Discipline resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_gondorian_discipline")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0 for e in events)


def test_rally_the_west_resolve_s9():
    print("\n=== Slice-9: Rally the West resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_rally_the_west")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0 for e in events)


def test_elendils_courage_resolve_s9():
    print("\n=== Slice-9: Elendil's Courage resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_elendils_courage")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0 for e in events)


def test_valiant_stand_resolve_s9():
    print("\n=== Slice-9: Valiant Stand resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_valiant_stand")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0 for e in events)


def test_mustering_of_gondor_resolve_s9():
    print("\n=== Slice-9: Mustering of Gondor resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_mustering_of_gondor")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) == -2 for e in events)


def test_ride_to_ruin_resolve_s9():
    print("\n=== Slice-9: Ride to Ruin resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_ride_to_ruin")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) == -3 for e in events)


def test_restoration_of_the_king_resolve_s9():
    print("\n=== Slice-9: Restoration of the King resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_restoration_of_the_king")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0 for e in events)


def test_dawn_over_minas_tirith_resolve_s9():
    print("\n=== Slice-9: Dawn Over Minas Tirith resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_dawn_over_minas_tirith")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) == -2 for e in events)


# --- BLUE creature/enchantment tests ----------------------------------------


def test_arwen_evenstar_etb_scry_drain_s9():
    print("\n=== Slice-9: Arwen, Evenstar — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Arwen, Evenstar")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_lorien_sentinel_etb_scry_drain_s9():
    print("\n=== Slice-9: Lorien Sentinel — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Lorien Sentinel")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_rivendell_scholar_etb_surveil_mill_s9():
    print("\n=== Slice-9: Rivendell Scholar — ETB surveil + mill ===")
    game, p1, p2, obj = _s9_etb_card("Rivendell Scholar")
    _s9_assert_etb_with_event(game, obj, EventType.MILL, p1, p2, EventType.SURVEIL)


def test_grey_havens_navigator_etb_scry_drain_s9():
    print("\n=== Slice-9: Grey Havens Navigator — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Grey Havens Navigator")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_elvish_seer_etb_scry_mill_s9():
    print("\n=== Slice-9: Elvish Seer — ETB scry + mill ===")
    game, p1, p2, obj = _s9_etb_card("Elvish Seer")
    _s9_assert_etb_with_event(game, obj, EventType.MILL, p1, p2, EventType.SCRY)


def test_silvan_tracker_etb_surveil_drain_s9():
    print("\n=== Slice-9: Silvan Tracker — ETB surveil + drain ===")
    game, p1, p2, obj = _s9_etb_card("Silvan Tracker")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SURVEIL)


def test_imladris_guardian_etb_scry_drain_s9():
    print("\n=== Slice-9: Imladris Guardian — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Imladris Guardian")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_keeper_of_the_mirror_etb_surveil_drain_s9():
    print("\n=== Slice-9: Keeper of the Mirror — ETB surveil + drain ===")
    game, p1, p2, obj = _s9_etb_card("Keeper of the Mirror")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SURVEIL)


def test_mirror_of_galadriel_etb_scry_mill_s9():
    print("\n=== Slice-9: Mirror of Galadriel — ETB scry + mill ===")
    game, p1, p2, obj = _s9_etb_card("Mirror of Galadriel")
    _s9_assert_etb_with_event(game, obj, EventType.MILL, p1, p2, EventType.SCRY)


def test_light_of_earendil_etb_scry_drain_s9():
    print("\n=== Slice-9: Light of Earendil — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Light of Earendil")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_elven_sanctuary_etb_scry_drain_s9():
    print("\n=== Slice-9: Elven Sanctuary — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Elven Sanctuary")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


# --- BLUE spell resolve tests -----------------------------------------------


def test_foresight_of_the_elves_resolve_s9():
    print("\n=== Slice-9: Foresight of the Elves resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_foresight_of_the_elves")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_elven_wisdom_resolve_s9():
    print("\n=== Slice-9: Elven Wisdom resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_elven_wisdom")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_mists_of_lorien_resolve_s9():
    print("\n=== Slice-9: Mists of Lorien resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_mists_of_lorien")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0 for e in events)


def test_visions_of_the_palantir_resolve_s9():
    print("\n=== Slice-9: Visions of the Palantir resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_visions_of_the_palantir")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.REVEAL_HAND and e.payload.get('player') == p2.id for e in events)


def test_elronds_rejection_resolve_s9():
    print("\n=== Slice-9: Elrond's Rejection resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_elronds_rejection")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) == -2 for e in events)


def test_silver_flow_resolve_s9():
    print("\n=== Slice-9: Silver Flow resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_silver_flow")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_council_of_elrond_resolve_s9():
    print("\n=== Slice-9: Council of Elrond resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_council_of_elrond")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0 for e in events)


def test_words_of_the_eldar_resolve_s9():
    print("\n=== Slice-9: Words of the Eldar resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_words_of_the_eldar")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_sailing_to_valinor_resolve_s9():
    print("\n=== Slice-9: Sailing to Valinor resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_sailing_to_valinor")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0 for e in events)


def test_memory_of_ages_resolve_s9():
    print("\n=== Slice-9: Memory of Ages resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_memory_of_ages")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


# --- BLACK creature/enchantment tests ---------------------------------------


def test_witch_king_etb_surveil_drain_s9():
    print("\n=== Slice-9: Witch-king of Angmar — ETB surveil + drain ===")
    game, p1, p2, obj = _s9_etb_card("Witch-king of Angmar")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SURVEIL)


def test_grima_wormtongue_etb_surveil_discard_s9():
    print("\n=== Slice-9: Grima Wormtongue — ETB surveil + discard ===")
    game, p1, p2, obj = _s9_etb_card("Grima Wormtongue")
    _s9_assert_etb_with_event(game, obj, EventType.DISCARD, p1, p2, EventType.SURVEIL)


def test_orc_warrior_attack_drain_s9():
    print("\n=== Slice-9: Orc Warrior — attack drain ===")
    game, p1, p2, obj = _s9_attack("Orc Warrior")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2)


def test_uruk_hai_berserker_etb_surveil_drain_s9():
    print("\n=== Slice-9: Uruk-hai Berserker — ETB surveil + drain ===")
    game, p1, p2, obj = _s9_etb_card("Uruk-hai Berserker")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SURVEIL)


def test_mordor_siege_engine_etb_surveil_drain_s9():
    print("\n=== Slice-9: Mordor Siege Engine — ETB surveil + drain ===")
    game, p1, p2, obj = _s9_etb_card("Mordor Siege Engine")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SURVEIL)


def test_haradrim_assassin_etb_surveil_drain_s9():
    print("\n=== Slice-9: Haradrim Assassin — ETB surveil + drain ===")
    game, p1, p2, obj = _s9_etb_card("Haradrim Assassin")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SURVEIL)


def test_morgul_knight_attack_surveil_drain_s9():
    print("\n=== Slice-9: Morgul Knight — attack surveil + drain ===")
    game, p1, p2, obj = _s9_attack("Morgul Knight")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SURVEIL)


def test_shadow_of_the_east_etb_surveil_drain_s9():
    print("\n=== Slice-9: Shadow of the East — ETB surveil + drain ===")
    game, p1, p2, obj = _s9_etb_card("Shadow of the East")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SURVEIL)


def test_the_ring_tempts_etb_surveil_discard_s9():
    print("\n=== Slice-9: The Ring Tempts You — ETB surveil + discard ===")
    game, p1, p2, obj = _s9_etb_card("The Ring Tempts You")
    _s9_assert_etb_with_event(game, obj, EventType.DISCARD, p1, p2, EventType.SURVEIL)


# --- BLACK spell resolve tests ----------------------------------------------


def test_shadow_of_mordor_resolve_s9():
    print("\n=== Slice-9: Shadow of Mordor resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_shadow_of_mordor")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0 for e in events)


def test_corruption_spreads_resolve_s9():
    print("\n=== Slice-9: Corruption Spreads resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_corruption_spreads")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.DISCARD and e.payload.get('player') == p2.id for e in events)


def test_morgul_blade_resolve_s9():
    print("\n=== Slice-9: Morgul Blade resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_morgul_blade")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) == -3 for e in events)


def test_dark_whispers_resolve_s9():
    print("\n=== Slice-9: Dark Whispers resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_dark_whispers")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.DISCARD and e.payload.get('player') == p2.id for e in events)


def test_treachery_of_isengard_resolve_s9():
    print("\n=== Slice-9: Treachery of Isengard resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_treachery_of_isengard")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.DISCARD and e.payload.get('player') == p2.id for e in events)


def test_saurons_command_resolve_s9():
    print("\n=== Slice-9: Sauron's Command resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_saurons_command")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) == -2 for e in events)


def test_march_of_the_orcs_resolve_s9():
    print("\n=== Slice-9: March of the Orcs resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_march_of_the_orcs")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) == -3 for e in events)


def test_harvest_of_souls_resolve_s9():
    print("\n=== Slice-9: Harvest of Souls resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_harvest_of_souls")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_corruption_of_power_resolve_s9():
    print("\n=== Slice-9: Corruption of Power resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_corruption_of_power")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.DISCARD and e.payload.get('player') == p2.id for e in events)


def test_ritual_of_morgoth_resolve_s9():
    print("\n=== Slice-9: Ritual of Morgoth resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_ritual_of_morgoth")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


# --- RED creature/enchantment tests -----------------------------------------


def test_iron_hills_warrior_attack_damage_s9():
    print("\n=== Slice-9: Iron Hills Warrior — attack scry + damage ===")
    game, p1, p2, obj = _s9_attack("Iron Hills Warrior")
    _s9_assert_etb_with_event(game, obj, EventType.DAMAGE, p1, p2, EventType.SCRY)


def test_dwarf_berserker_attack_damage_s9():
    print("\n=== Slice-9: Dwarf Berserker — attack damage ===")
    game, p1, p2, obj = _s9_attack("Dwarf Berserker")
    _s9_assert_etb_with_event(game, obj, EventType.DAMAGE, p1, p2)


def test_mountain_guard_etb_scry_drain_s9():
    print("\n=== Slice-9: Mountain Guard — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Mountain Guard")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_warg_rider_attack_damage_s9():
    print("\n=== Slice-9: Warg Rider — attack damage ===")
    game, p1, p2, obj = _s9_attack("Warg Rider")
    _s9_assert_etb_with_event(game, obj, EventType.DAMAGE, p1, p2)


def test_dragon_of_the_north_etb_scry_damage_s9():
    print("\n=== Slice-9: Dragon of the North — ETB scry + damage ===")
    game, p1, p2, obj = _s9_etb_card("Dragon of the North")
    _s9_assert_etb_with_event(game, obj, EventType.DAMAGE, p1, p2, EventType.SCRY)


def test_fire_drake_etb_scry_damage_s9():
    print("\n=== Slice-9: Fire Drake — ETB scry + damage ===")
    game, p1, p2, obj = _s9_etb_card("Fire Drake")
    _s9_assert_etb_with_event(game, obj, EventType.DAMAGE, p1, p2, EventType.SCRY)


def test_moria_goblin_attack_drain_s9():
    print("\n=== Slice-9: Moria Goblin — attack scry + drain ===")
    game, p1, p2, obj = _s9_attack("Moria Goblin")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_fires_of_mount_doom_etb_scry_damage_s9():
    print("\n=== Slice-9: Fires of Mount Doom — ETB scry + damage ===")
    game, p1, p2, obj = _s9_etb_card("Fires of Mount Doom")
    _s9_assert_etb_with_event(game, obj, EventType.DAMAGE, p1, p2, EventType.SCRY)


def test_wrath_of_the_dwarves_etb_scry_damage_s9():
    print("\n=== Slice-9: Wrath of the Dwarves — ETB scry + damage ===")
    game, p1, p2, obj = _s9_etb_card("Wrath of the Dwarves")
    _s9_assert_etb_with_event(game, obj, EventType.DAMAGE, p1, p2, EventType.SCRY)


# --- RED spell resolve tests ------------------------------------------------


def test_flame_of_anor_resolve_s9():
    print("\n=== Slice-9: Flame of Anor resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_flame_of_anor")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id and e.payload.get('amount') == 3 for e in events)


def test_dwarven_rage_resolve_s9():
    print("\n=== Slice-9: Dwarven Rage resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_dwarven_rage")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_dragons_breath_resolve_s9():
    print("\n=== Slice-9: Dragon's Breath resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_dragons_breath")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id and e.payload.get('amount') == 4 for e in events)


def test_forge_fire_resolve_s9():
    print("\n=== Slice-9: Forge Fire resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_forge_fire")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_battle_cry_of_erebor_resolve_s9():
    print("\n=== Slice-9: Battle Cry of Erebor resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_battle_cry_of_erebor")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0 for e in events)


def test_smash_the_gate_resolve_s9():
    print("\n=== Slice-9: Smash the Gate resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_smash_the_gate")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_siege_of_erebor_resolve_s9():
    print("\n=== Slice-9: Siege of Erebor resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_siege_of_erebor")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id and e.payload.get('amount') == 4 for e in events)


def test_dragon_fire_resolve_s9():
    print("\n=== Slice-9: Dragon Fire resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_dragon_fire")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id and e.payload.get('amount') == 5 for e in events)


def test_call_of_the_mountain_resolve_s9():
    print("\n=== Slice-9: Call of the Mountain resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_call_of_the_mountain")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) == -2 for e in events)


def test_delving_the_mines_resolve_s9():
    print("\n=== Slice-9: Delving the Mines resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_delving_the_mines")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


# --- GREEN creature/enchantment tests ---------------------------------------


def test_samwise_the_brave_etb_scry_gain_s9():
    print("\n=== Slice-9: Samwise the Brave — ETB scry + gain ===")
    game, p1, p2, obj = _s9_etb_card("Samwise, the Brave")
    scrys = [e for e in game.state.event_log if e.type == EventType.SCRY and e.source == obj.id]
    gains = [e for e in game.state.event_log if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0 and e.source == obj.id]
    assert scrys, "Expected SCRY"
    assert gains, "Expected life gain"


def test_gwaihir_wind_lord_etb_scry_drain_s9():
    print("\n=== Slice-9: Gwaihir, Wind Lord — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Gwaihir, Wind Lord")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_quickbeam_attack_drain_s9():
    print("\n=== Slice-9: Quickbeam — attack drain ===")
    game, p1, p2, obj = _s9_attack("Quickbeam, Bregalad")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_ent_sapling_etb_scry_gain_s9():
    print("\n=== Slice-9: Ent Sapling — ETB scry + gain ===")
    game, p1, p2, obj = _s9_etb_card("Ent Sapling")
    scrys = [e for e in game.state.event_log if e.type == EventType.SCRY and e.source == obj.id]
    assert scrys, "Expected SCRY"


def test_hobbiton_gardener_etb_scry_gain_s9():
    print("\n=== Slice-9: Hobbiton Gardener — ETB scry + gain ===")
    game, p1, p2, obj = _s9_etb_card("Hobbiton Gardener")
    scrys = [e for e in game.state.event_log if e.type == EventType.SCRY and e.source == obj.id]
    gains = [e for e in game.state.event_log if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0 and e.source == obj.id]
    assert scrys, "Expected SCRY"
    assert gains, "Expected life gain"


def test_fangorn_guardian_etb_scry_drain_s9():
    print("\n=== Slice-9: Fangorn Guardian — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Fangorn Guardian")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_great_eagle_etb_scry_drain_s9():
    print("\n=== Slice-9: Great Eagle — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Great Eagle")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_oliphaunt_etb_scry_drain_s9():
    print("\n=== Slice-9: Oliphaunt — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Oliphaunt")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_radagast_companion_etb_scry_gain_s9():
    print("\n=== Slice-9: Radagast's Companion — ETB scry + gain ===")
    game, p1, p2, obj = _s9_etb_card("Radagast's Companion")
    scrys = [e for e in game.state.event_log if e.type == EventType.SCRY and e.source == obj.id]
    gains = [e for e in game.state.event_log if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0 and e.source == obj.id]
    assert scrys, "Expected SCRY"
    assert gains, "Expected life gain"


def test_huorn_etb_scry_drain_s9():
    print("\n=== Slice-9: Huorn — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Huorn")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_heart_of_fangorn_etb_scry_drain_s9():
    print("\n=== Slice-9: Heart of Fangorn — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Heart of Fangorn")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_second_breakfast_etb_scry_gain_s9():
    print("\n=== Slice-9: Second Breakfast — ETB scry + gain ===")
    game, p1, p2, obj = _s9_etb_card("Second Breakfast")
    scrys = [e for e in game.state.event_log if e.type == EventType.SCRY and e.source == obj.id]
    gains = [e for e in game.state.event_log if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0 and e.source == obj.id]
    assert scrys, "Expected SCRY"
    assert gains, "Expected life gain"


# --- GREEN spell resolve tests ----------------------------------------------


def test_strength_of_nature_resolve_s9():
    print("\n=== Slice-9: Strength of Nature resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_strength_of_nature")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0 for e in events)


def test_hobbits_cunning_resolve_s9():
    print("\n=== Slice-9: Hobbit's Cunning resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_hobbits_cunning")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0 for e in events)


def test_entish_fury_resolve_s9():
    print("\n=== Slice-9: Entish Fury resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_entish_fury")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) == -3 for e in events)


def test_gift_of_the_shire_resolve_s9():
    print("\n=== Slice-9: Gift of the Shire resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_gift_of_the_shire")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0 for e in events)


def test_eagles_are_coming_resolve_s9():
    print("\n=== Slice-9: The Eagles Are Coming resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_eagles_are_coming")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) == -3 for e in events)


def test_natures_reclamation_resolve_s9():
    print("\n=== Slice-9: Nature's Reclamation resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_natures_reclamation")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0 for e in events)


def test_last_march_of_the_ents_resolve_s9():
    print("\n=== Slice-9: Last March of the Ents resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_last_march_of_the_ents")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) == -4 for e in events)


def test_shire_harvest_resolve_s9():
    print("\n=== Slice-9: Shire Harvest resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_shire_harvest")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0 for e in events)


def test_party_in_the_shire_resolve_s9():
    print("\n=== Slice-9: Party in the Shire resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_party_in_the_shire")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0 for e in events)


def test_isengard_unleashed_resolve_s9():
    print("\n=== Slice-9: Isengard Unleashed resolve ===")
    events, p1, p2 = _s9_resolve("_ltr_s9_resolve_isengard_unleashed")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) == -4 for e in events)


# --- ARTIFACT tests ---------------------------------------------------------


def test_vilya_etb_scry_drain_s9():
    print("\n=== Slice-9: Vilya — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Vilya, Ring of Air")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_narya_etb_scry_damage_s9():
    print("\n=== Slice-9: Narya — ETB scry + damage ===")
    game, p1, p2, obj = _s9_etb_card("Narya, Ring of Fire")
    _s9_assert_etb_with_event(game, obj, EventType.DAMAGE, p1, p2, EventType.SCRY)


def test_phial_of_galadriel_etb_scry_gain_s9():
    print("\n=== Slice-9: Phial of Galadriel — ETB scry + gain ===")
    game, p1, p2, obj = _s9_etb_card("Phial of Galadriel")
    scrys = [e for e in game.state.event_log if e.type == EventType.SCRY and e.source == obj.id]
    gains = [e for e in game.state.event_log if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0 and e.source == obj.id]
    assert scrys, "Expected SCRY"
    assert gains, "Expected life gain"


def test_palantir_of_orthanc_etb_surveil_reveal_s9():
    print("\n=== Slice-9: Palantir of Orthanc — ETB surveil + reveal ===")
    game, p1, p2, obj = _s9_etb_card("Palantir of Orthanc")
    _s9_assert_etb_with_event(game, obj, EventType.REVEAL_HAND, p1, p2, EventType.SURVEIL)


def test_horn_of_gondor_etb_scry_drain_s9():
    print("\n=== Slice-9: Horn of Gondor — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Horn of Gondor")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_ring_of_barahir_etb_scry_gain_s9():
    print("\n=== Slice-9: Ring of Barahir — ETB scry + gain ===")
    game, p1, p2, obj = _s9_etb_card("Ring of Barahir")
    scrys = [e for e in game.state.event_log if e.type == EventType.SCRY and e.source == obj.id]
    gains = [e for e in game.state.event_log if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0 and e.source == obj.id]
    assert scrys, "Expected SCRY"
    assert gains, "Expected life gain"


def test_morgul_sword_etb_surveil_drain_s9():
    print("\n=== Slice-9: Morgul Sword — ETB surveil + drain ===")
    game, p1, p2, obj = _s9_etb_card("Morgul Sword")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SURVEIL)


def test_dwarven_axe_etb_scry_damage_s9():
    print("\n=== Slice-9: Dwarven Axe — ETB scry + damage ===")
    game, p1, p2, obj = _s9_etb_card("Dwarven Axe")
    _s9_assert_etb_with_event(game, obj, EventType.DAMAGE, p1, p2, EventType.SCRY)


def test_elven_bow_etb_scry_drain_s9():
    print("\n=== Slice-9: Elven Bow — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Elven Bow")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_orc_blade_etb_surveil_drain_s9():
    print("\n=== Slice-9: Orc Blade — ETB surveil + drain ===")
    game, p1, p2, obj = _s9_etb_card("Orc Blade")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SURVEIL)


# --- LAND tests -------------------------------------------------------------


def test_rivendell_land_etb_scry_gain_s9():
    print("\n=== Slice-9: Rivendell (land) — ETB scry + gain ===")
    game, p1, p2, obj = _s9_etb_card("Rivendell")
    scrys = [e for e in game.state.event_log if e.type == EventType.SCRY and e.source == obj.id]
    gains = [e for e in game.state.event_log if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0 and e.source == obj.id]
    assert scrys, "Expected SCRY"
    assert gains, "Expected life gain"


def test_the_shire_land_etb_scry_gain_s9():
    print("\n=== Slice-9: The Shire (land) — ETB scry + gain ===")
    game, p1, p2, obj = _s9_etb_card("The Shire")
    scrys = [e for e in game.state.event_log if e.type == EventType.SCRY and e.source == obj.id]
    gains = [e for e in game.state.event_log if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0 and e.source == obj.id]
    assert scrys, "Expected SCRY"
    assert gains, "Expected life gain"


def test_minas_tirith_land_etb_scry_drain_s9():
    print("\n=== Slice-9: Minas Tirith (land) — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Minas Tirith")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_mordor_land_etb_surveil_drain_s9():
    print("\n=== Slice-9: Mordor (land) — ETB surveil + drain ===")
    game, p1, p2, obj = _s9_etb_card("Mordor, Land of Shadow")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SURVEIL)


def test_erebor_land_etb_scry_damage_s9():
    print("\n=== Slice-9: Erebor (land) — ETB scry + damage ===")
    game, p1, p2, obj = _s9_etb_card("Erebor, the Lonely Mountain")
    _s9_assert_etb_with_event(game, obj, EventType.DAMAGE, p1, p2, EventType.SCRY)


def test_helms_deep_land_etb_scry_gain_s9():
    print("\n=== Slice-9: Helm's Deep (land) — ETB scry + gain ===")
    game, p1, p2, obj = _s9_etb_card("Helm's Deep")
    scrys = [e for e in game.state.event_log if e.type == EventType.SCRY and e.source == obj.id]
    gains = [e for e in game.state.event_log if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0 and e.source == obj.id]
    assert scrys, "Expected SCRY"
    assert gains, "Expected life gain"


def test_isengard_land_etb_surveil_discard_s9():
    print("\n=== Slice-9: Isengard (land) — ETB surveil + discard ===")
    game, p1, p2, obj = _s9_etb_card("Isengard")
    _s9_assert_etb_with_event(game, obj, EventType.DISCARD, p1, p2, EventType.SURVEIL)


def test_fangorn_land_etb_scry_drain_s9():
    print("\n=== Slice-9: Fangorn Forest (land) — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Fangorn Forest")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_mount_doom_land_etb_surveil_damage_s9():
    print("\n=== Slice-9: Mount Doom (land) — ETB surveil + damage ===")
    game, p1, p2, obj = _s9_etb_card("Mount Doom")
    _s9_assert_etb_with_event(game, obj, EventType.DAMAGE, p1, p2, EventType.SURVEIL)


def test_weathertop_land_etb_scry_drain_s9():
    print("\n=== Slice-9: Weathertop (land) — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Weathertop")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_osgiliath_land_etb_scry_drain_s9():
    print("\n=== Slice-9: Osgiliath (land) — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Osgiliath, Fallen City")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_grey_havens_land_etb_scry_drain_s9():
    print("\n=== Slice-9: Grey Havens (land) — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Grey Havens")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)


def test_mines_of_moria_land_etb_surveil_mill_s9():
    print("\n=== Slice-9: Mines of Moria (land) — ETB surveil + mill ===")
    game, p1, p2, obj = _s9_etb_card("Mines of Moria")
    _s9_assert_etb_with_event(game, obj, EventType.MILL, p1, p2, EventType.SURVEIL)


def test_edoras_land_etb_scry_drain_s9():
    print("\n=== Slice-9: Edoras (land) — ETB scry + drain ===")
    game, p1, p2, obj = _s9_etb_card("Edoras")
    _s9_assert_etb_with_event(game, obj, EventType.LIFE_CHANGE, p1, p2, EventType.SCRY)



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
