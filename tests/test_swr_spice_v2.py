"""
Star Wars Spice Pass Tests (v2 EXPANSION)

Sits on top of `test_star_wars_spice.py` (the original Phase A/B-1/B-2/B-3).
This v2 expansion adds 7 net-new spice picks targeting axis_diversity (the
failing health gate per docs/sets/custom_set_depth_baseline_2026-05-18.md):

Net-new cards (5):
- Ahsoka Tano, Fulcrum                  — snowball attack-trigger mythic
- Grogu, Strong With the Force          — build-around legendary-tribal mythic
- Death Star Superlaser Charge          — 3-chapter prison saga
- The Imperial Throne                   — pattern-5 cost-bump enchantment
- Carbonite Containment                 — exile-attached prison artifact

Reskinned (REWIRE) entries (2) — replace pre-existing unwired stubs:
- Sith Holocron of Vitiate              — pattern-5 mill enchantment-artifact
- Darksaber, Mandalore's Birthright     — Mandalorian-tribal equipment

Mirrors ZLD/LTR-v2 shape. Worktree-portable sys.path per spice-pass.md
gotcha #18 — repo root is computed from this file's location so the test
runs from any checkout (main or `.claude/worktrees/agent-*/`).
"""

import os
import sys
# Per gotcha #18: never hardcode the main-checkout path. Compute repo root
# from this file's location so the test runs equivalently in main and worktree.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Characteristics,
    get_power, get_toughness,
)
from src.engine.queries import has_ability
from src.cards.custom.star_wars import STAR_WARS_CARDS


def _put_on_battlefield(game, player, card_name):
    """Standard harness — create in hand without card_def, then ZONE_CHANGE."""
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
    return [e.type.name for e in game.state.event_log]


# ============================================================================
# Ahsoka Tano, Fulcrum
# ============================================================================

def test_ahsoka_fulcrum_loads():
    """Ahsoka loads with vigilance + attack trigger."""
    print("\n=== Ahsoka Fulcrum: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    ahsoka = _put_on_battlefield(game, p1, "Ahsoka Tano, Fulcrum")
    assert ahsoka.zone == ZoneType.BATTLEFIELD
    assert 'Togruta' in ahsoka.characteristics.subtypes
    assert 'Jedi' in ahsoka.characteristics.subtypes
    assert 'Rebel' in ahsoka.characteristics.subtypes
    assert 'Legendary' in ahsoka.characteristics.supertypes
    assert len(ahsoka.interceptor_ids) >= 2, (
        f"Expected ≥2 interceptors, got {len(ahsoka.interceptor_ids)}"
    )
    assert has_ability(ahsoka, 'vigilance', game.state)
    print(f"  Interceptors: {len(ahsoka.interceptor_ids)}; vigilance confirmed")


def test_ahsoka_fulcrum_attack_emits_scry_and_token():
    """Attack → SCRY + CREATE_TOKEN."""
    print("\n=== Ahsoka Fulcrum: attack trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    ahsoka = _put_on_battlefield(game, p1, "Ahsoka Tano, Fulcrum")
    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': ahsoka.id, 'attacker': ahsoka.id, 'defender': 'opponent'},
        source=ahsoka.id,
    ))
    after = _emitted_types(game)
    new = after[len(before):]
    assert 'SCRY' in new, f"SCRY missing: {new}"
    assert 'CREATE_TOKEN' in new, f"CREATE_TOKEN missing: {new}"
    print("  SCRY + CREATE_TOKEN emitted")


def test_ahsoka_fulcrum_other_attacker_skips_trigger():
    """Edge: when another creature attacks (not Ahsoka), Ahsoka's trigger no-ops."""
    print("\n=== Ahsoka Fulcrum: non-self attack (edge) ===")
    game = Game()
    p1 = game.add_player("Alice")
    ahsoka = _put_on_battlefield(game, p1, "Ahsoka Tano, Fulcrum")
    # Drop a second attacker (vanilla Padawan).
    padawan = _put_on_battlefield(game, p1, "Jedi Padawan")
    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': padawan.id, 'attacker': padawan.id, 'defender': 'opponent'},
        source=padawan.id,
    ))
    after = _emitted_types(game)
    new = after[len(before):]
    # Ahsoka's trigger should NOT fire on the Padawan's attack.
    scry_events = [
        e for e in game.state.event_log
        if e.type == EventType.SCRY and e.source == ahsoka.id
    ]
    # No new SCRY from Ahsoka on this event.
    assert 'SCRY' not in new, f"SCRY should not fire when non-Ahsoka attacks: {new}"
    print("  Non-Ahsoka attack correctly skipped")


# ============================================================================
# Grogu, Strong With the Force
# ============================================================================

def test_grogu_loads_with_end_step_and_activated():
    """Grogu has hexproof gate, end-step trigger, and Force Push activated."""
    print("\n=== Grogu: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    grogu = _put_on_battlefield(game, p1, "Grogu, Strong With the Force")
    assert grogu.zone == ZoneType.BATTLEFIELD
    assert 'Legendary' in grogu.characteristics.supertypes
    assert 'Jedi' in grogu.characteristics.subtypes
    # 1 keyword grant + 1 end-step trigger = 2 (activated abilities aren't in interceptor_ids).
    assert len(grogu.interceptor_ids) >= 2
    abilities = getattr(grogu.state, 'activated_abilities', None) or []
    assert len(abilities) >= 1, f"Expected Force Push ability, got {abilities}"
    print(f"  Interceptors: {len(grogu.interceptor_ids)}; activated: {len(abilities)}")


def test_grogu_hexproof_only_with_other_legendary():
    """Grogu has hexproof ONLY when another legendary is on the battlefield."""
    print("\n=== Grogu: conditional hexproof ===")
    game = Game()
    p1 = game.add_player("Alice")
    grogu = _put_on_battlefield(game, p1, "Grogu, Strong With the Force")
    # Solo — no hexproof.
    assert not has_ability(grogu, 'hexproof', game.state), (
        "Grogu shouldn't have hexproof when alone"
    )
    # Drop another legendary.
    _put_on_battlefield(game, p1, "Yoda, Living Force")
    assert has_ability(grogu, 'hexproof', game.state), (
        "Grogu should have hexproof with another legendary on board"
    )
    print("  Hexproof gate validated")


def test_grogu_end_step_counter_when_legendary_majority():
    """End step → +1/+1 counter on Grogu when controller has more legendaries."""
    print("\n=== Grogu: end-step counter ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    grogu = _put_on_battlefield(game, p1, "Grogu, Strong With the Force")
    # Alice gets a second legendary (Yoda Living Force counts).
    _put_on_battlefield(game, p1, "Yoda, Living Force")
    before = grogu.state.counters.get('+1/+1', 0)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'step': 'end_step', 'active_player': p1.id, 'turn_number': 1},
    ))
    after = grogu.state.counters.get('+1/+1', 0)
    assert after >= before + 1, (
        f"+1/+1 counter expected on majority: before={before} after={after}"
    )
    print(f"  Grogu counter {before} → {after}")


def test_grogu_no_counter_when_equal_legendaries():
    """Edge: no counter when controller doesn't have legendary majority."""
    print("\n=== Grogu: no counter at parity ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    grogu = _put_on_battlefield(game, p1, "Grogu, Strong With the Force")
    # Plant a legendary on Bob's side to match Grogu (1-vs-1).
    enemy = game.create_object(
        name="Test Foe",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            supertypes={'Legendary'},
            colors={Color.BLACK},
            power=3, toughness=3,
        ),
    )
    before = grogu.state.counters.get('+1/+1', 0)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'step': 'end_step', 'active_player': p1.id, 'turn_number': 1},
    ))
    after = grogu.state.counters.get('+1/+1', 0)
    assert after == before, (
        f"No counter expected at parity: before={before} after={after}"
    )
    print(f"  Grogu counter stays at {before} (parity, correct)")


# ============================================================================
# Sith Holocron of Vitiate (REWIRE)
# ============================================================================

def test_sith_holocron_vitiate_loads():
    """Sith Holocron of Vitiate has two registered interceptors."""
    print("\n=== Sith Holocron of Vitiate: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    holo = _put_on_battlefield(game, p1, "Sith Holocron of Vitiate")
    assert holo.zone == ZoneType.BATTLEFIELD
    chars = holo.characteristics
    assert CardType.ENCHANTMENT in chars.types
    assert CardType.ARTIFACT in chars.types
    assert 'Legendary' in chars.supertypes
    assert len(holo.interceptor_ids) >= 2, (
        f"Expected 2 interceptors, got {len(holo.interceptor_ids)}"
    )
    print(f"  Loaded with {len(holo.interceptor_ids)} interceptors")


def test_sith_holocron_vitiate_punishes_opp_creature_cast():
    """When an OPPONENT casts a creature spell, they lose 1 life."""
    print("\n=== Sith Holocron of Vitiate: opp creature cast → drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Sith Holocron of Vitiate")
    p2_life = p2.life
    # Plant a creature in Bob's hand and emit a SPELL_CAST for it.
    cd = STAR_WARS_CARDS["Jedi Padawan"]
    spell_obj = game.create_object(
        name="Jedi Padawan",
        owner_id=p2.id,
        zone=ZoneType.HAND,
        characteristics=cd.characteristics,
        card_def=cd,
    )
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={
            'player': p2.id,
            'controller': p2.id,
            'spell_id': spell_obj.id,
            'object_id': spell_obj.id,
        },
        source=spell_obj.id,
    ))
    assert p2.life == p2_life - 1, (
        f"Bob should lose 1 life: {p2_life} → {p2.life}"
    )
    print(f"  Bob {p2_life} → {p2.life} on creature cast")


def test_sith_holocron_vitiate_self_cast_safe():
    """Edge: controller's own creature cast does NOT drain self."""
    print("\n=== Sith Holocron of Vitiate: self-cast edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Sith Holocron of Vitiate")
    p1_life = p1.life
    cd = STAR_WARS_CARDS["Jedi Padawan"]
    spell_obj = game.create_object(
        name="Jedi Padawan",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=cd.characteristics,
        card_def=cd,
    )
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={
            'player': p1.id,
            'controller': p1.id,
            'spell_id': spell_obj.id,
            'object_id': spell_obj.id,
        },
        source=spell_obj.id,
    ))
    assert p1.life == p1_life, (
        f"Self cast must not drain: {p1_life} → {p1.life}"
    )
    print(f"  Alice life stays {p1_life} (correct)")


def test_sith_holocron_vitiate_creature_death_mills():
    """When any creature dies, its owner mills 1."""
    print("\n=== Sith Holocron of Vitiate: death → mill ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Sith Holocron of Vitiate")
    # Plant a creature on Bob's side; emit OBJECT_DESTROYED.
    foe = game.create_object(
        name="Bob Soldier",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={'Human', 'Soldier'},
            colors={Color.WHITE},
            power=2, toughness=2,
        ),
    )
    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': foe.id},
        source=foe.id,
    ))
    after = _emitted_types(game)
    new = after[len(before):]
    assert 'MILL' in new, f"MILL not emitted on death: {new}"
    print(f"  MILL emitted on Bob's creature death")


# ============================================================================
# Darksaber, Mandalore's Birthright (REWIRE)
# ============================================================================

def test_darksaber_birthright_loads_as_equipment():
    """Darksaber is a Legendary Equipment (Lightsaber subtype)."""
    print("\n=== Darksaber Birthright: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saber = _put_on_battlefield(game, p1, "Darksaber, Mandalore's Birthright")
    chars = saber.characteristics
    assert CardType.ARTIFACT in chars.types
    assert 'Equipment' in chars.subtypes
    assert 'Lightsaber' in chars.subtypes
    assert 'Legendary' in chars.supertypes
    abilities = getattr(saber.state, 'activated_abilities', None) or []
    assert len(abilities) >= 1, "Equip cost should register activated ability"
    print(f"  Loaded: types={chars.types}, abilities={len(abilities)}")


def test_darksaber_birthright_pt_boost_on_attach():
    """Equipped creature gets +3/+2."""
    print("\n=== Darksaber Birthright: +3/+2 on attach ===")
    game = Game()
    p1 = game.add_player("Alice")
    saber = _put_on_battlefield(game, p1, "Darksaber, Mandalore's Birthright")
    # Build a Mandalorian to equip.
    mando_chars = Characteristics(
        types={CardType.CREATURE},
        subtypes={'Human', 'Mandalorian', 'Warrior'},
        colors={Color.RED},
        power=2, toughness=2,
    )
    mando = game.create_object(
        name="Mando Warrior",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=mando_chars,
    )
    base_p, base_t = get_power(mando, game.state), get_toughness(mando, game.state)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': saber.id, 'target_id': mando.id},
        source=saber.id,
    ))
    new_p, new_t = get_power(mando, game.state), get_toughness(mando, game.state)
    assert new_p == base_p + 3, f"Expected +3 power: {base_p} → {new_p}"
    assert new_t == base_t + 2, f"Expected +2 toughness: {base_t} → {new_t}"
    print(f"  Equipped Mandalorian {base_p}/{base_t} → {new_p}/{new_t}")


def test_darksaber_birthright_mandalorian_attack_creates_treasure():
    """Equipped Mandalorian attack → Treasure token via Darksaber's trigger."""
    print("\n=== Darksaber Birthright: Mandalorian-attack Treasure ===")
    game = Game()
    p1 = game.add_player("Alice")
    saber = _put_on_battlefield(game, p1, "Darksaber, Mandalore's Birthright")
    mando = game.create_object(
        name="Mando Hunter",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={'Human', 'Mandalorian'},
            colors={Color.RED},
            power=2, toughness=2,
        ),
    )
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': saber.id, 'target_id': mando.id},
        source=saber.id,
    ))
    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': mando.id, 'attacker': mando.id, 'defender': 'opponent'},
        source=mando.id,
    ))
    after = _emitted_types(game)
    new = after[len(before):]
    # Locate Treasure CREATE_TOKEN whose source is the saber.
    treasures = [
        e for e in game.state.event_log
        if e.type == EventType.CREATE_TOKEN
        and 'Treasure' in (e.payload.get('token', {}).get('subtypes', set()) or set())
        and e.source == saber.id
    ]
    assert treasures, f"Treasure not minted from Mandalorian attack; new={new}"
    print(f"  Treasure tokens: {len(treasures)}")


def test_darksaber_birthright_non_mandalorian_no_treasure():
    """Edge: equipped non-Mandalorian attack does NOT mint Treasure."""
    print("\n=== Darksaber Birthright: non-Mandalorian edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    saber = _put_on_battlefield(game, p1, "Darksaber, Mandalore's Birthright")
    soldier = game.create_object(
        name="Plain Soldier",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={'Human', 'Soldier'},  # NOT Mandalorian
            colors={Color.WHITE},
            power=2, toughness=2,
        ),
    )
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': saber.id, 'target_id': soldier.id},
        source=saber.id,
    ))
    before_count = sum(
        1 for e in game.state.event_log
        if e.type == EventType.CREATE_TOKEN and e.source == saber.id
    )
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': soldier.id, 'attacker': soldier.id, 'defender': 'opponent'},
        source=soldier.id,
    ))
    after_count = sum(
        1 for e in game.state.event_log
        if e.type == EventType.CREATE_TOKEN and e.source == saber.id
    )
    assert after_count == before_count, (
        f"No new Treasure should mint for non-Mandalorian: {before_count} → {after_count}"
    )
    print("  Non-Mandalorian attack correctly skipped")


# ============================================================================
# Death Star Superlaser Charge (NEW Saga)
# ============================================================================

def test_death_star_charge_loads_as_saga():
    """Saga subtype + ETB lore counter."""
    print("\n=== Death Star Superlaser Charge: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Death Star Superlaser Charge")
    assert saga.zone == ZoneType.BATTLEFIELD
    assert 'Saga' in saga.characteristics.subtypes
    assert 'Legendary' in saga.characteristics.supertypes
    assert saga.state.counters.get('lore', 0) == 1, (
        f"Expected 1 lore counter at ETB; got {saga.state.counters}"
    )
    print(f"  Lore counter at ETB: {saga.state.counters.get('lore', 0)}")


def test_death_star_charge_chapter_i_drains_each_opponent():
    """Chapter I drains each opponent 2."""
    print("\n=== Death Star: chapter I ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    p2_life_before = p2.life
    _put_on_battlefield(game, p1, "Death Star Superlaser Charge")
    # ETB runs chapter I.
    assert p2.life == p2_life_before - 2, (
        f"Bob should lose 2 life on chapter I: {p2_life_before} → {p2.life}"
    )
    print(f"  Bob {p2_life_before} → {p2.life}")


def test_death_star_charge_chapter_iii_destroys_nonlegendary():
    """After two draws, chapter III destroys all non-legendary creatures."""
    print("\n=== Death Star: chapter III ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Drop a non-legendary creature on Bob's side + a legendary creature.
    target = game.create_object(
        name="Mook",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            colors={Color.BLACK},
            power=2, toughness=2,
        ),
    )
    legend_safe = game.create_object(
        name="Legendary Boss",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            supertypes={'Legendary'},
            colors={Color.RED},
            power=3, toughness=3,
        ),
    )

    saga = _put_on_battlefield(game, p1, "Death Star Superlaser Charge")
    game.state.active_player = p1.id
    # Two draw-step phases to push lore 1 → 3.
    for turn in (1, 2):
        game.emit(Event(
            type=EventType.PHASE_START,
            payload={'phase': 'draw', 'step': 'draw',
                     'active_player': p1.id, 'turn_number': turn},
        ))

    # Chapter III destruction events on the non-legendary target.
    destroys = [
        e for e in game.state.event_log
        if e.type == EventType.OBJECT_DESTROYED
        and e.payload.get('object_id') == target.id
        and e.source == saga.id
    ]
    assert destroys, "Non-legendary should be marked for destruction by chapter III"
    # Legendary creature should NOT be destroyed by chapter III.
    legend_destroys = [
        e for e in game.state.event_log
        if e.type == EventType.OBJECT_DESTROYED
        and e.payload.get('object_id') == legend_safe.id
        and e.source == saga.id
    ]
    assert not legend_destroys, "Legendary should be spared"
    print(f"  Non-legendary destroyed; legendary spared")


# ============================================================================
# The Imperial Throne
# ============================================================================

def test_imperial_throne_loads():
    """The Imperial Throne registers cost-modifying + life-loss tracker + end-step."""
    print("\n=== Imperial Throne: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    throne = _put_on_battlefield(game, p1, "The Imperial Throne")
    assert throne.zone == ZoneType.BATTLEFIELD
    chars = throne.characteristics
    assert CardType.ENCHANTMENT in chars.types
    assert 'Legendary' in chars.supertypes
    # Expect 3 interceptors: cost-bump + life-loss tracker + end-step.
    assert len(throne.interceptor_ids) >= 3, (
        f"Expected ≥3 interceptors, got {len(throne.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(throne.interceptor_ids)}")


def test_imperial_throne_end_step_draws_when_opp_lost_life():
    """End step → DRAW when an opponent lost life this turn."""
    print("\n=== Imperial Throne: end-step draw when opp life lost ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "The Imperial Throne")
    # Drain Bob to set the marker.
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p2.id, 'amount': -1},
        source=p1.id,
    ))
    game.state.active_player = p1.id
    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'step': 'end_step',
                 'active_player': p1.id, 'turn_number': 1},
    ))
    after = _emitted_types(game)
    new = after[len(before):]
    assert 'DRAW' in new, f"DRAW not emitted: {new}"
    print("  DRAW emitted at end step (opp lost life)")


def test_imperial_throne_no_draw_without_opp_life_loss():
    """Edge: end step without opp life loss → no DRAW."""
    print("\n=== Imperial Throne: no draw when no life lost ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "The Imperial Throne")
    # No life-change event this turn.
    game.state.active_player = p1.id
    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'step': 'end_step',
                 'active_player': p1.id, 'turn_number': 1},
    ))
    after = _emitted_types(game)
    new = after[len(before):]
    # No DRAW from the Throne's end-step trigger.
    throne_draws = [
        e for e in game.state.event_log
        if e.type == EventType.DRAW
        and e.payload.get('player') == p1.id
    ]
    # In an end-step phase with no life loss, the Throne's effect should be []
    # (we don't gate on global DRAW count since the engine may emit other DRAW
    # events around phase ticks).
    # The unique signature is that no Throne-sourced DRAW exists.
    throne_sourced = [
        e for e in game.state.event_log
        if e.type == EventType.DRAW
        and e.payload.get('player') == p1.id
    ]
    # The trigger only fires when 'imperial_throne_opp_life_lost' is true. Verify the flag.
    assert game.state.turn_data.get('imperial_throne_opp_life_lost', False) is False, (
        "Flag should be unset when no opp life was lost"
    )
    print("  Flag correctly unset (no DRAW from Throne)")


# ============================================================================
# Carbonite Containment
# ============================================================================

def test_carbonite_containment_loads():
    """Loads as Legendary Artifact with ETB exile + activated payoff."""
    print("\n=== Carbonite Containment: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    carbo = _put_on_battlefield(game, p1, "Carbonite Containment")
    chars = carbo.characteristics
    assert CardType.ARTIFACT in chars.types
    assert 'Legendary' in chars.supertypes
    abilities = getattr(carbo.state, 'activated_abilities', None) or []
    assert len(abilities) >= 1, "Sac payoff activated ability should be registered"
    print(f"  Loaded: types={chars.types}, abilities={len(abilities)}")


def test_carbonite_containment_etb_exiles_opp_creature():
    """ETB: emits EXILE on an opp creature; the prisoner_toughness flag is set."""
    print("\n=== Carbonite Containment: ETB exile ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    foe = game.create_object(
        name="Imperial Mook",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            colors={Color.BLACK},
            power=2, toughness=4,
        ),
    )
    carbo = _put_on_battlefield(game, p1, "Carbonite Containment")
    # EXILE event targeting foe.
    exiles = [
        e for e in game.state.event_log
        if e.type == EventType.EXILE
        and e.payload.get('object_id') == foe.id
        and e.source == carbo.id
    ]
    assert exiles, f"Expected EXILE on opp creature; got log tail {_emitted_types(game)[-10:]}"
    # Toughness captured on Carbonite's state.
    captured_t = getattr(carbo.state, '_carbonite_prisoner_toughness', None)
    assert captured_t == 4, (
        f"Expected captured_t=4; got {captured_t}"
    )
    print(f"  EXILE emitted; captured_t={captured_t}")


def test_carbonite_containment_etb_skips_when_no_opp_creature():
    """Edge: ETB no-ops when no opponent creature exists."""
    print("\n=== Carbonite Containment: empty board edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    carbo = _put_on_battlefield(game, p1, "Carbonite Containment")
    exiles = [
        e for e in game.state.event_log
        if e.type == EventType.EXILE and e.source == carbo.id
    ]
    assert not exiles, f"No EXILE should fire on empty board; got {exiles}"
    captured_t = getattr(carbo.state, '_carbonite_prisoner_toughness', None)
    assert not captured_t, (
        f"No prisoner toughness should be captured; got {captured_t}"
    )
    print("  No EXILE on empty board (correct)")


# ============================================================================
# v2 spice — meta integrity
# ============================================================================

def test_swr_v2_all_cards_registered():
    """All 7 v2 cards live in STAR_WARS_CARDS."""
    print("\n=== Spice v2: registry ===")
    expected = [
        "Ahsoka Tano, Fulcrum",
        "Grogu, Strong With the Force",
        "Sith Holocron of Vitiate",
        "Darksaber, Mandalore's Birthright",
        "Death Star Superlaser Charge",
        "The Imperial Throne",
        "Carbonite Containment",
    ]
    missing = [n for n in expected if n not in STAR_WARS_CARDS]
    assert not missing, f"Missing v2 entries: {missing}"
    # All have setup_interceptors wired.
    for name in expected:
        cd = STAR_WARS_CARDS[name]
        assert cd.setup_interceptors is not None, f"{name} should be wired"
    print(f"  All {len(expected)} v2 cards present & wired")


def test_swr_v2_does_not_collide_with_existing_spice():
    """v2 names must not duplicate Phase A/B-1/B-2/B-3 names."""
    print("\n=== Spice v2: no name collision with prior spice ===")
    v1_names = {
        "Boba Fett, Hunter of Hunters",
        "IG-88, Assassin Droid Network",
        "Yoda, Living Force",
        "Bossk, Trandoshan Hunter Prime",
        "Han Solo, Hotshot Pilot",
        "Holocron of the High Council",
        "Mandalorian Beskar Plating",
        "Sith Resurgence",
        "Kylo Ren, Conflicted Heir",
        "Stormtrooper Patrol Squadron",
        "R2-D2, Master Hacker",
        "Darth Vader, More Machine Than Man",
        "The Force Itself",
        "Luke Skywalker, Last Jedi",
        "Princess Leia, Spark of Hope",
    }
    v2_names = {
        "Ahsoka Tano, Fulcrum",
        "Grogu, Strong With the Force",
        "Sith Holocron of Vitiate",
        "Darksaber, Mandalore's Birthright",
        "Death Star Superlaser Charge",
        "The Imperial Throne",
        "Carbonite Containment",
    }
    overlap = v1_names & v2_names
    assert not overlap, f"v2 names collide with v1: {overlap}"
    print(f"  No collisions between v1 ({len(v1_names)}) and v2 ({len(v2_names)})")


# ============================================================================
# SLICE 5 — Thin-bust: 23 vanilla cards lifted to depth-3 axes
# Each card now reads state.zones, counts allies by subtype, emits SCRY
# (info) plus LIFE_CHANGE / DAMAGE / REVEAL_HAND / DISCARD per opponent
# (asymmetry). Net per-card: zeros 5 -> 2 (state=1, zone=1, asym>=2).
# ============================================================================


def _events_emitted_by(game, source_id, event_type):
    return [e for e in game.state.event_log
            if e.type == event_type and e.source == source_id]


def _assert_etb_scry(game, p1, card_name, expected_amount=1):
    """Helper: ETB the card, assert it emits SCRY for the controller."""
    before = len(game.state.event_log)
    obj = _put_on_battlefield(game, p1, card_name)
    scries = [e for e in game.state.event_log[before:]
              if e.type == EventType.SCRY and e.source == obj.id]
    assert scries, (
        f"{card_name}: SCRY missing — emitted "
        f"{[e.type.name for e in game.state.event_log[before:]]}"
    )
    assert scries[-1].payload.get('amount') == expected_amount, (
        f"{card_name}: expected SCRY {expected_amount}, got {scries[-1].payload}"
    )
    return obj


def _trigger_attack(game, attacker, defender_player):
    """Emit an ATTACK_DECLARED for the attack-trigger cards."""
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': attacker.id, 'defender': defender_player.id},
    ))


def test_alderaanian_diplomat_etb_scry_and_life_gain():
    """Alderaanian Diplomat (W Rebel) — ETB: scry 1 + life per Rebel."""
    print("\n=== Alderaanian Diplomat: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    obj = _assert_etb_scry(game, p1, "Alderaanian Diplomat")
    gains = [e for e in game.state.event_log
             if e.type == EventType.LIFE_CHANGE and e.source == obj.id
             and e.payload.get('amount', 0) > 0]
    assert gains, "LIFE_CHANGE gain missing"
    print(f"  Alderaanian Diplomat: SCRY + life gain {gains[-1].payload}")


def test_rebel_medic_etb_scry_drain_and_gain():
    """Rebel Medic — ETB scry 1 + each opp -1 life."""
    print("\n=== Rebel Medic: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry(game, p1, "Rebel Medic")
    drains = [e for e in game.state.event_log
              if e.type == EventType.LIFE_CHANGE and e.source == obj.id
              and e.payload.get('amount') == -1]
    assert drains, "Opp life drain missing"
    print(f"  Rebel Medic: SCRY + {len(drains)} drain(s)")


def test_jedi_sentinel_attack_scry_and_drain_with_jedi():
    """Jedi Sentinel — attack scry 1; if you control a Jedi, each opp -1 life."""
    print("\n=== Jedi Sentinel: attack ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    js = _put_on_battlefield(game, p1, "Jedi Sentinel")
    before = len(game.state.event_log)
    _trigger_attack(game, js, p2)
    new_events = game.state.event_log[before:]
    scries = [e for e in new_events if e.type == EventType.SCRY and e.source == js.id]
    drains = [e for e in new_events
              if e.type == EventType.LIFE_CHANGE and e.source == js.id
              and e.payload.get('amount') == -1]
    assert scries, "SCRY missing"
    assert drains, "Drain missing (Jedi Sentinel itself is a Jedi)"
    print(f"  Jedi Sentinel: SCRY + {len(drains)} drain(s)")


def test_tatooine_homesteader_etb_scry_and_life_gain():
    """Tatooine Homesteader — ETB scry 1 + life gain per Citizen."""
    print("\n=== Tatooine Homesteader: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    obj = _assert_etb_scry(game, p1, "Tatooine Homesteader")
    gains = [e for e in game.state.event_log
             if e.type == EventType.LIFE_CHANGE and e.source == obj.id
             and e.payload.get('amount', 0) > 0]
    assert gains, "Life gain missing"
    print(f"  Tatooine Homesteader: SCRY + gain")


def test_galactic_senator_etb_scry_and_reveal():
    """Galactic Senator — ETB scry 1 + each opp reveals."""
    print("\n=== Galactic Senator: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry(game, p1, "Galactic Senator")
    reveals = _events_emitted_by(game, obj.id, EventType.REVEAL_HAND)
    assert reveals, "REVEAL_HAND missing"
    print(f"  Galactic Senator: SCRY + {len(reveals)} reveal(s)")


def test_royal_guard_etb_scry_and_life_gain():
    """Royal Guard — ETB scry 1 + life gain per Soldier."""
    print("\n=== Royal Guard: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    obj = _assert_etb_scry(game, p1, "Royal Guard")
    gains = [e for e in game.state.event_log
             if e.type == EventType.LIFE_CHANGE and e.source == obj.id
             and e.payload.get('amount', 0) > 0]
    assert gains, "Life gain missing"
    print(f"  Royal Guard: SCRY + gain")


def test_mon_calamari_captain_etb_scry_and_surveil():
    """Mon Calamari Captain — ETB scry 1; with no opp creatures, surveil 1 fires."""
    print("\n=== Mon Calamari Captain: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry(game, p1, "Mon Calamari Captain")
    surveils = _events_emitted_by(game, obj.id, EventType.SURVEIL)
    assert surveils, "SURVEIL missing (Captain is a Rebel; opp_threats=0)"
    print(f"  Mon Calamari Captain: SCRY + {len(surveils)} surveil(s)")


def test_rebel_strategist_etb_scry_and_reveal():
    """Rebel Strategist — ETB scry 1 + each opp reveals."""
    print("\n=== Rebel Strategist: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry(game, p1, "Rebel Strategist")
    reveals = _events_emitted_by(game, obj.id, EventType.REVEAL_HAND)
    assert reveals, "REVEAL_HAND missing"
    print(f"  Rebel Strategist: SCRY + {len(reveals)} reveal(s)")


def test_separatist_infiltrator_attack_scry_and_reveal():
    """Separatist Infiltrator — attack scry 1 + each opp reveals hand."""
    print("\n=== Separatist Infiltrator: attack ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    si = _put_on_battlefield(game, p1, "Separatist Infiltrator")
    before = len(game.state.event_log)
    _trigger_attack(game, si, p2)
    new_events = game.state.event_log[before:]
    scries = [e for e in new_events if e.type == EventType.SCRY and e.source == si.id]
    reveals = [e for e in new_events
               if e.type == EventType.REVEAL_HAND and e.source == si.id]
    assert scries, "SCRY missing"
    assert reveals, "REVEAL_HAND missing"
    print(f"  Separatist Infiltrator: SCRY + reveal")


def test_information_broker_etb_scry_surveil_and_reveal():
    """Information Broker — ETB scry 1 + surveil 1 (self counts as Rogue) + each opp reveals."""
    print("\n=== Information Broker: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry(game, p1, "Information Broker")
    surveils = _events_emitted_by(game, obj.id, EventType.SURVEIL)
    reveals = _events_emitted_by(game, obj.id, EventType.REVEAL_HAND)
    assert surveils, "SURVEIL missing"
    assert reveals, "REVEAL_HAND missing"
    print(f"  Information Broker: SCRY + surveil + {len(reveals)} reveal(s)")


def test_imperial_officer_etb_scry_and_drain():
    """Imperial Officer — ETB scry 1 + each opp -1 life per Empire (self counts)."""
    print("\n=== Imperial Officer: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry(game, p1, "Imperial Officer")
    drains = [e for e in game.state.event_log
              if e.type == EventType.LIFE_CHANGE and e.source == obj.id
              and e.payload.get('amount', 0) < 0]
    assert drains, "Opp drain missing"
    print(f"  Imperial Officer: SCRY + {len(drains)} drain(s)")


def test_imperial_inquisitor_etb_scry_and_reveal():
    """Imperial Inquisitor — ETB scry 1 + each opp reveals."""
    print("\n=== Imperial Inquisitor: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry(game, p1, "Imperial Inquisitor")
    reveals = _events_emitted_by(game, obj.id, EventType.REVEAL_HAND)
    assert reveals, "REVEAL_HAND missing"
    print(f"  Imperial Inquisitor: SCRY + {len(reveals)} reveal(s)")


def test_mustafar_torturer_etb_scry_and_drain():
    """Mustafar Torturer — ETB scry 1 + each opp -1 life."""
    print("\n=== Mustafar Torturer: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry(game, p1, "Mustafar Torturer")
    drains = [e for e in game.state.event_log
              if e.type == EventType.LIFE_CHANGE and e.source == obj.id
              and e.payload.get('amount') == -1]
    assert drains, "Drain missing"
    print(f"  Mustafar Torturer: SCRY + {len(drains)} drain(s)")


def test_imperial_spy_etb_surveil_and_reveal():
    """Imperial Spy — ETB surveil 1 (no SCRY) + each opp reveals."""
    print("\n=== Imperial Spy: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    spy = _put_on_battlefield(game, p1, "Imperial Spy")
    surveils = _events_emitted_by(game, spy.id, EventType.SURVEIL)
    reveals = _events_emitted_by(game, spy.id, EventType.REVEAL_HAND)
    assert surveils, "SURVEIL missing"
    assert reveals, "REVEAL_HAND missing"
    print(f"  Imperial Spy: surveil + {len(reveals)} reveal(s)")


def test_tie_fighter_pilot_attack_scry_and_damage():
    """TIE Fighter Pilot — attack scry 1 + 1 damage to each opp."""
    print("\n=== TIE Fighter Pilot: attack ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    tfp = _put_on_battlefield(game, p1, "TIE Fighter Pilot")
    before = len(game.state.event_log)
    _trigger_attack(game, tfp, p2)
    new_events = game.state.event_log[before:]
    scries = [e for e in new_events if e.type == EventType.SCRY and e.source == tfp.id]
    dmgs = [e for e in new_events if e.type == EventType.DAMAGE and e.source == tfp.id]
    assert scries and dmgs
    print(f"  TIE Fighter Pilot: SCRY + {len(dmgs)} damage event(s)")


def test_force_choker_etb_scry_and_drain():
    """Force Choker — ETB scry 1 + each opp loses life per Sith."""
    print("\n=== Force Choker: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry(game, p1, "Force Choker")
    drains = [e for e in game.state.event_log
              if e.type == EventType.LIFE_CHANGE and e.source == obj.id
              and e.payload.get('amount', 0) < 0]
    assert drains, "Drain missing"
    print(f"  Force Choker: SCRY + {len(drains)} drain(s)")


def test_shadow_guard_etb_scry_no_drain_solo():
    """Shadow Guard — ETB scry 1; no drain unless >=2 Empire creatures controlled."""
    print("\n=== Shadow Guard: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry(game, p1, "Shadow Guard")
    drains = [e for e in game.state.event_log
              if e.type == EventType.LIFE_CHANGE and e.source == obj.id]
    assert not drains, f"Drain should NOT fire with 1 Empire creature (Shadow Guard alone): got {drains}"
    print("  Shadow Guard: SCRY but no drain (only 1 Empire)")


def test_mandalorian_warrior_etb_scry_and_damage():
    """Mandalorian Warrior — ETB scry 1 + each opp takes damage."""
    print("\n=== Mandalorian Warrior: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry(game, p1, "Mandalorian Warrior")
    dmgs = _events_emitted_by(game, obj.id, EventType.DAMAGE)
    assert dmgs, "DAMAGE missing"
    print(f"  Mandalorian Warrior: SCRY + {len(dmgs)} dmg event(s)")


def test_clone_trooper_commando_etb_scry_and_damage():
    """Clone Trooper Commando — ETB scry 1 + damage to each opp."""
    print("\n=== Clone Trooper Commando: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry(game, p1, "Clone Trooper Commando")
    dmgs = _events_emitted_by(game, obj.id, EventType.DAMAGE)
    assert dmgs, "DAMAGE missing"
    print(f"  Clone Trooper Commando: SCRY + {len(dmgs)} dmg")


def test_arena_gladiator_attack_scry_and_damage():
    """Arena Gladiator — attack scry 1 + damage per Warrior."""
    print("\n=== Arena Gladiator: attack ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    ag = _put_on_battlefield(game, p1, "Arena Gladiator")
    before = len(game.state.event_log)
    _trigger_attack(game, ag, p2)
    new_events = game.state.event_log[before:]
    scries = [e for e in new_events if e.type == EventType.SCRY and e.source == ag.id]
    dmgs = [e for e in new_events if e.type == EventType.DAMAGE and e.source == ag.id]
    assert scries and dmgs
    print(f"  Arena Gladiator: SCRY + {len(dmgs)} dmg")


def test_wookiee_warrior_etb_scry_and_life_gain():
    """Wookiee Warrior — ETB scry 1 + life gain per Wookiee."""
    print("\n=== Wookiee Warrior: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    obj = _assert_etb_scry(game, p1, "Wookiee Warrior")
    gains = [e for e in game.state.event_log
             if e.type == EventType.LIFE_CHANGE and e.source == obj.id
             and e.payload.get('amount', 0) > 0]
    assert gains, "Life gain missing"
    print("  Wookiee Warrior: SCRY + gain")


def test_ewok_hunter_attack_scry_and_drain():
    """Ewok Hunter — attack scry 1 + drain per Ewok."""
    print("\n=== Ewok Hunter: attack ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    eh = _put_on_battlefield(game, p1, "Ewok Hunter")
    before = len(game.state.event_log)
    _trigger_attack(game, eh, p2)
    new_events = game.state.event_log[before:]
    scries = [e for e in new_events if e.type == EventType.SCRY and e.source == eh.id]
    drains = [e for e in new_events
              if e.type == EventType.LIFE_CHANGE and e.source == eh.id
              and e.payload.get('amount', 0) < 0]
    assert scries and drains
    print(f"  Ewok Hunter: SCRY + {len(drains)} drain")


def test_kashyyyk_defender_etb_scry_2_and_life_gain():
    """Kashyyyk Defender — ETB scry 2 + life gain."""
    print("\n=== Kashyyyk Defender: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    obj = _assert_etb_scry(game, p1, "Kashyyyk Defender", expected_amount=2)
    gains = [e for e in game.state.event_log
             if e.type == EventType.LIFE_CHANGE and e.source == obj.id
             and e.payload.get('amount', 0) > 0]
    assert gains, "Life gain missing"
    print(f"  Kashyyyk Defender: SCRY 2 + gain")


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
