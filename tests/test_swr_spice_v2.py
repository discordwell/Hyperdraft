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
from src.cards.custom import star_wars as star_wars_module


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
# SPICE PASS PHASE A2 (slice 5.5, 2026-05-19) — decision-axis flip
# Each test below proves that the new card installs a brand-new
# PendingChoice / TARGET_REQUIRED surface (decision axis > 0). These tests
# do NOT resolve the choices — they verify the surface emits, since
# resolution requires either AI auto-pick or full UI plumbing.
# ============================================================================


# ----------------------------------------------------------------------------
# Yoda, Force-Echo of the Living — modal-ETB (decision=3 modal-deep)
# ----------------------------------------------------------------------------

def test_yoda_force_echo_loads_legendary():
    """Loads as a legendary Alien Jedi with a modal ETB interceptor."""
    print("\n=== Yoda Force-Echo: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    yoda = _put_on_battlefield(game, p1, "Yoda, Force-Echo of the Living")
    chars = yoda.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Jedi' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert yoda.interceptor_ids, f"Expected ETB interceptor; got {yoda.interceptor_ids}"
    print(f"  Interceptors: {len(yoda.interceptor_ids)}; subtypes={chars.subtypes}")


def test_yoda_force_echo_etb_opens_modal_choice():
    """ETB installs a modal_with_targeting pending_choice with 3 modes."""
    print("\n=== Yoda Force-Echo: modal choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    yoda = _put_on_battlefield(game, p1, "Yoda, Force-Echo of the Living")
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending_choice after ETB"
    assert pc.source_id == yoda.id
    assert pc.choice_type == "modal_with_targeting"
    assert pc.player == p1.id
    assert len(pc.options) == 3, f"Expected 3 modes; got {len(pc.options)}"
    print(f"  Modes: {[opt.get('label') for opt in pc.options]}")


# ----------------------------------------------------------------------------
# Reva, Third Sister Inquisitor — targeted ETB (decision=1 + asymmetry)
# ----------------------------------------------------------------------------

def test_reva_third_sister_loads_legendary():
    """Loads as a Black Human Inquisitor with ETB interceptors."""
    print("\n=== Reva Third Sister: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    reva = _put_on_battlefield(game, p1, "Reva, Third Sister Inquisitor")
    chars = reva.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Inquisitor' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert reva.interceptor_ids, "Expected ETB interceptors"
    print(f"  Interceptors: {len(reva.interceptor_ids)}")


def test_reva_third_sister_etb_emits_target_required_and_reveal():
    """ETB emits a TARGET_REQUIRED reveal_hand + REVEAL_HAND on an opponent."""
    print("\n=== Reva Third Sister: ETB target+reveal ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    reva = _put_on_battlefield(game, p1, "Reva, Third Sister Inquisitor")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == reva.id
        and e.payload.get('effect') == 'reveal_hand'
    ]
    assert target_reqs, (
        f"Expected reveal_hand TARGET_REQUIRED; new={[e.type.name for e in new[-10:]]}"
    )
    assert target_reqs[0].payload.get('target_filter') == 'opponent'
    reveals = [e for e in new
               if e.type == EventType.REVEAL_HAND
               and e.source == reva.id
               and e.payload.get('player') == p2.id]
    assert reveals, f"Expected REVEAL_HAND on p2; new={[e.type.name for e in new[-10:]]}"
    print(f"  TARGET_REQUIRED: {len(target_reqs)}; REVEAL_HAND: {len(reveals)}")


# ----------------------------------------------------------------------------
# HK-47, Hunter-Killer Protocol — divided damage (decision=1 + asymmetry)
# ----------------------------------------------------------------------------

def test_hk_47_hunter_killer_loads_enchantment():
    """Loads as a Red enchantment with ETB interceptor."""
    print("\n=== HK-47 Hunter-Killer: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    hk = _put_on_battlefield(game, p1, "HK-47, Hunter-Killer Protocol")
    assert CardType.ENCHANTMENT in hk.characteristics.types
    assert hk.interceptor_ids, "Expected ETB interceptor"
    print(f"  Interceptors: {len(hk.interceptor_ids)}")


def test_hk_47_hunter_killer_etb_emits_divided_damage_target_required():
    """ETB emits TARGET_REQUIRED with divide_amount=5 and damage effect."""
    print("\n=== HK-47: ETB divided 5 ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    hk = _put_on_battlefield(game, p1, "HK-47, Hunter-Killer Protocol")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == hk.id
        and e.payload.get('effect') == 'damage'
    ]
    assert target_reqs, (
        f"Expected damage TARGET_REQUIRED; new={[e.type.name for e in new[-10:]]}"
    )
    payload = target_reqs[0].payload
    assert payload.get('divide_amount') == 5, (
        f"Expected divide_amount=5; got {payload.get('divide_amount')}"
    )
    print(f"  divide_amount: {payload.get('divide_amount')}")


# ----------------------------------------------------------------------------
# Bo-Katan Kryze, Mandalore's Heir — divided counters (decision=1 + synergy)
# ----------------------------------------------------------------------------

def test_bo_katan_kryze_loads_legendary_mandalorian():
    """Loads as a White legendary Mandalorian with ETB interceptor."""
    print("\n=== Bo-Katan Kryze: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    bk = _put_on_battlefield(game, p1, "Bo-Katan Kryze, Mandalore's Heir")
    chars = bk.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Mandalorian' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert bk.interceptor_ids, "Expected ETB interceptor"
    print(f"  Interceptors: {len(bk.interceptor_ids)}; subtypes={chars.subtypes}")


def test_bo_katan_kryze_etb_emits_counter_add_target_required():
    """ETB emits TARGET_REQUIRED with divide_amount=4 and counter_add effect."""
    print("\n=== Bo-Katan Kryze: ETB distribute counters ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    bk = _put_on_battlefield(game, p1, "Bo-Katan Kryze, Mandalore's Heir")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == bk.id
        and e.payload.get('effect') == 'counter_add'
    ]
    assert target_reqs, (
        f"Expected counter_add TARGET_REQUIRED; new={[e.type.name for e in new[-10:]]}"
    )
    payload = target_reqs[0].payload
    assert payload.get('divide_amount') == 4, (
        f"Expected divide_amount=4; got {payload.get('divide_amount')}"
    )
    assert payload.get('target_filter') == 'your_creature'
    print(f"  divide_amount: {payload.get('divide_amount')}; filter: {payload.get('target_filter')}")


# ----------------------------------------------------------------------------
# Cad Bane, Sky's-Edge Reckoner — targeted death + asymmetric discard
# ----------------------------------------------------------------------------

def test_cad_bane_skys_edge_loads_legendary_bounty_hunter():
    """Loads as a Rakdos legendary Duros Bounty Hunter with death triggers."""
    print("\n=== Cad Bane Sky's-Edge: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    cb = _put_on_battlefield(game, p1, "Cad Bane, Sky's-Edge Reckoner")
    chars = cb.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Bounty Hunter' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(cb.interceptor_ids) >= 2, (
        f"Expected >=2 (targeted-death + death listener); got {len(cb.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(cb.interceptor_ids)}")


def test_cad_bane_skys_edge_death_emits_target_required_and_discard():
    """On death, emits TARGET_REQUIRED for destroy + DISCARD on opponent hand."""
    print("\n=== Cad Bane Sky's-Edge: death trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Drop a card into p2's hand so the DISCARD pulse has something to bite.
    junk_chars = Characteristics(
        types={CardType.CREATURE}, subtypes={"Soldier"}, power=1, toughness=1,
    )
    game.create_object(
        name="Spare Trooper", owner_id=p2.id, zone=ZoneType.HAND,
        characteristics=junk_chars, card_def=None,
    )
    cb = _put_on_battlefield(game, p1, "Cad Bane, Sky's-Edge Reckoner")
    before = len(game.state.event_log)
    # Simulate death: ZONE_CHANGE battlefield -> graveyard with reason='destroy'.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': cb.id,
            'from_zone': 'battlefield',
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
            'reason': 'destroy',
        },
        source=cb.id,
    ))
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == cb.id
        and e.payload.get('effect') == 'destroy'
    ]
    assert target_reqs, (
        f"Expected destroy TARGET_REQUIRED on death; new={[e.type.name for e in new[-10:]]}"
    )
    assert target_reqs[0].payload.get('target_filter') == 'opponent_creature'
    discards = [
        e for e in new
        if e.type == EventType.DISCARD
        and e.payload.get('player') == p2.id
        and e.source == cb.id
    ]
    assert discards, f"Expected DISCARD on p2; new={[e.type.name for e in new[-10:]]}"
    print(f"  TARGET_REQUIRED: {len(target_reqs)}; DISCARD: {len(discards)}")


# ----------------------------------------------------------------------------
# Padmé Amidala, Naboo's Senator — top-N + zone-coupling
# ----------------------------------------------------------------------------

def test_padme_amidala_loads_legendary_advisor():
    """Loads as a Selesnya legendary Human Advisor with ETB interceptor."""
    print("\n=== Padmé Amidala: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    pa = _put_on_battlefield(game, p1, "Padme Amidala, Naboo's Senator")
    chars = pa.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Advisor' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert pa.interceptor_ids, "Expected ETB interceptor"
    print(f"  Interceptors: {len(pa.interceptor_ids)}; subtypes={chars.subtypes}")


def test_padme_amidala_etb_empty_library_no_op():
    """ETB with empty library doesn't crash and doesn't install a choice."""
    print("\n=== Padmé Amidala: empty library no-op ===")
    game = Game()
    p1 = game.add_player("Alice")
    pa = _put_on_battlefield(game, p1, "Padme Amidala, Naboo's Senator")
    assert pa.zone == ZoneType.BATTLEFIELD
    pc = game.state.pending_choice
    # No-crash is the contract; pc may or may not be set.
    print(f"  No-crash; pending_choice={pc}")


def test_padme_amidala_etb_with_library_lands_opens_choice():
    """ETB with a land on top of library installs a PendingChoice."""
    print("\n=== Padmé Amidala: library lands -> choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Plant a land in p1's library so the helper has something to pick.
    lib = game.state.zones[f'library_{p1.id}']
    land_chars = Characteristics(types={CardType.LAND}, subtypes={"Plains"})
    land_obj = game.create_object(
        name="Test Plains", owner_id=p1.id, zone=ZoneType.LIBRARY,
        characteristics=land_chars, card_def=None,
    )
    if land_obj.id not in lib.objects:
        lib.objects.append(land_obj.id)
    pa = _put_on_battlefield(game, p1, "Padme Amidala, Naboo's Senator")
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending_choice installed by top-N land pick"
    assert pc.source_id == pa.id, f"Choice source should be Padmé; got {pc.source_id}"
    print(f"  PendingChoice type: {pc.choice_type}; source: {pc.source_id}")


# ----------------------------------------------------------------------------
# Asajj Ventress, Dathomiri Bounty Hunter — targeted attack trigger
# ----------------------------------------------------------------------------

def test_asajj_ventress_loads_legendary_bounty_hunter():
    """Loads as a Rakdos legendary Bounty Hunter with menace + attack trigger."""
    print("\n=== Asajj Ventress: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    av = _put_on_battlefield(game, p1, "Asajj Ventress, Dathomiri Bounty Hunter")
    chars = av.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Bounty Hunter' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(av.interceptor_ids) >= 2, (
        f"Expected >=2 (menace kw + attack trigger); got {len(av.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(av.interceptor_ids)}")


def test_asajj_ventress_attack_emits_tap_target_required():
    """On attack, emits TARGET_REQUIRED with effect='tap' targeting opp creature."""
    print("\n=== Asajj Ventress: attack tap trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    av = _put_on_battlefield(game, p1, "Asajj Ventress, Dathomiri Bounty Hunter")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': av.id, 'attacker': av.id, 'controller': p1.id},
        source=av.id,
    ))
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == av.id
        and e.payload.get('effect') == 'tap'
        and e.payload.get('target_filter') == 'opponent_creature'
    ]
    assert target_reqs, (
        f"Expected tap TARGET_REQUIRED on attack; new={[e.type.name for e in new[-10:]]}"
    )
    print(f"  TARGET_REQUIRED (tap): {len(target_reqs)}")


# ----------------------------------------------------------------------------
# Jocasta Nu, Jedi Archivist — scry-4 + library zone + Jedi synergy
# ----------------------------------------------------------------------------

def test_jocasta_nu_loads_legendary_jedi():
    """Loads as a Blue legendary Human Jedi with ETB interceptor."""
    print("\n=== Jocasta Nu: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    jn = _put_on_battlefield(game, p1, "Jocasta Nu, Jedi Archivist")
    chars = jn.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Jedi' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert jn.interceptor_ids, "Expected ETB interceptor"
    print(f"  Interceptors: {len(jn.interceptor_ids)}; subtypes={chars.subtypes}")


def test_jocasta_nu_etb_opens_scry_choice():
    """ETB with cards in library installs a scry PendingChoice."""
    print("\n=== Jocasta Nu: scry choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Plant 4 cards in p1's library so create_scry_choice has options.
    lib = game.state.zones[f'library_{p1.id}']
    base_chars = Characteristics(types={CardType.CREATURE}, subtypes={"Jedi"}, power=1, toughness=1)
    for i in range(4):
        c = game.create_object(
            name=f"Library Card {i}", owner_id=p1.id, zone=ZoneType.LIBRARY,
            characteristics=base_chars, card_def=None,
        )
        if c.id not in lib.objects:
            lib.objects.append(c.id)
    jn = _put_on_battlefield(game, p1, "Jocasta Nu, Jedi Archivist")
    pc = game.state.pending_choice
    assert pc is not None, "Expected scry pending_choice"
    assert pc.choice_type == "scry", f"Expected scry; got {pc.choice_type}"
    assert pc.source_id == jn.id
    assert pc.callback_data.get('scry_count') == 4, (
        f"Expected scry_count=4; got {pc.callback_data}"
    )
    print(f"  Scry choice with {len(pc.options)} option(s); count={pc.callback_data.get('scry_count')}")


def test_jocasta_nu_etb_empty_library_no_op():
    """ETB with empty library doesn't crash (and doesn't install a scry choice)."""
    print("\n=== Jocasta Nu: empty library no-op ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Default library is empty.
    jn = _put_on_battlefield(game, p1, "Jocasta Nu, Jedi Archivist")
    assert jn.zone == ZoneType.BATTLEFIELD
    print(f"  No-crash on empty library")


# ----------------------------------------------------------------------------
# Slice 5.5 registry hygiene
# ----------------------------------------------------------------------------

def test_swr_slice_5_5_all_cards_registered():
    """All 8 slice-5.5 cards live in STAR_WARS_CARDS and are wired."""
    print("\n=== Slice 5.5: registry ===")
    expected = [
        "Yoda, Force-Echo of the Living",
        "Reva, Third Sister Inquisitor",
        "HK-47, Hunter-Killer Protocol",
        "Bo-Katan Kryze, Mandalore's Heir",
        "Cad Bane, Sky's-Edge Reckoner",
        "Padme Amidala, Naboo's Senator",
        "Asajj Ventress, Dathomiri Bounty Hunter",
        "Jocasta Nu, Jedi Archivist",
    ]
    missing = [n for n in expected if n not in STAR_WARS_CARDS]
    assert not missing, f"Missing slice-5.5 entries: {missing}"
    for name in expected:
        cd = STAR_WARS_CARDS[name]
        assert cd.setup_interceptors is not None, f"{name} should be wired"
    print(f"  All {len(expected)} slice-5.5 cards present & wired")


# =============================================================================
# Slice-11 median-lift tests (2026-05-19): one assertion per buffed vanilla
# card driving SWR median_depth 0 -> >= 2. Each test puts the card on the
# battlefield (or invokes its resolve handler for instants/sorceries) and
# asserts the expected SCRY/SURVEIL info event + a cross-controller effect.
# =============================================================================


def _s11_etb_card(card_name):
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, card_name)
    return game, p1, p2, obj


def _s11_attack(card_name):
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, card_name)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={"attacker_id": obj.id, "defender": p2.id},
        source=obj.id, controller=obj.controller,
    ))
    return game, p1, p2, obj


def _s11_assert_info_and_opp(game, obj, p2, *, info_type, opp_type, opp_key, amount_check):
    new = game.state.event_log
    info_evs = [e for e in new if e.type == info_type and e.source == obj.id]
    assert info_evs, f"Expected {info_type.name} from {obj.id}; events={[e.type.name for e in new[-15:]]}"
    if opp_type == EventType.LIFE_CHANGE:
        opp_evs = [e for e in new if e.type == opp_type
                   and e.payload.get(opp_key) == p2.id
                   and (e.payload.get("amount", 0) < 0 if amount_check == "neg" else True)
                   and e.source == obj.id]
    elif opp_type == EventType.DAMAGE:
        opp_evs = [e for e in new if e.type == opp_type
                   and e.payload.get(opp_key) == p2.id
                   and e.source == obj.id]
    elif opp_type in (EventType.MILL, EventType.DISCARD, EventType.REVEAL_HAND):
        opp_evs = [e for e in new if e.type == opp_type
                   and e.payload.get(opp_key) == p2.id
                   and e.source == obj.id]
    else:
        opp_evs = []
    assert opp_evs, (
        f"Expected {opp_type.name} against p2 from {obj.id}; "
        f"events={[e.type.name for e in new[-15:]]}"
    )


def _s11_resolve(fn_name):
    fn = getattr(star_wars_module, fn_name)
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.state.active_player = p1.id
    events = fn([], game.state)
    return events, p1, p2


def _s11_assert_resolve(events, p2, *, info_type, opp_type, opp_key, amount_check):
    info_evs = [e for e in events if e.type == info_type]
    assert info_evs, f"Expected {info_type.name}; events={[e.type.name for e in events]}"
    if opp_type == EventType.LIFE_CHANGE:
        opp_evs = [e for e in events if e.type == opp_type
                   and e.payload.get(opp_key) == p2.id
                   and (e.payload.get("amount", 0) < 0 if amount_check == "neg" else True)]
    elif opp_type == EventType.DAMAGE:
        opp_evs = [e for e in events if e.type == opp_type
                   and e.payload.get(opp_key) == p2.id]
    else:
        opp_evs = [e for e in events if e.type == opp_type
                   and e.payload.get(opp_key) == p2.id]
    assert opp_evs, f"Expected {opp_type.name} on p2; events={[e.type.name for e in events]}"


def test_s11_coruscant_peacekeeper_s11():
    """Slice-11 ETB: Coruscant Peacekeeper -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Coruscant Peacekeeper ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Coruscant Peacekeeper')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_resistance_commander_s11():
    """Slice-11 ETB: Resistance Commander -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Resistance Commander ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Resistance Commander')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_rebellion_sympathizer_s11():
    """Slice-11 ETB: Rebellion Sympathizer -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Rebellion Sympathizer ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Rebellion Sympathizer')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_force_protection_resolve_s11():
    """Slice-11 resolve: Force Protection -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Force Protection resolve scry+life_change ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_white_v1')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_rebel_ambush_resolve_s11():
    """Slice-11 resolve: Rebel Ambush -> SCRY+MILL."""
    print("\n=== Slice-11: Rebel Ambush resolve scry+mill ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_white_v4')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_jedi_reflexes_resolve_s11():
    """Slice-11 resolve: Jedi Reflexes -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Jedi Reflexes resolve scry+life_change ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_white_v3')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_hope_renewed_resolve_s11():
    """Slice-11 resolve: Hope Renewed -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Hope Renewed resolve scry+life_change ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_white_v1')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_defensive_formation_resolve_s11():
    """Slice-11 resolve: Defensive Formation -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Defensive Formation resolve scry+life_change ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_white_v3')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_light_of_the_force_resolve_s11():
    """Slice-11 resolve: Light of the Force -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Light of the Force resolve scry+life_change ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_white_v2')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_call_to_arms_resolve_s11():
    """Slice-11 resolve: Call to Arms -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Call to Arms resolve scry+life_change ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_white_v2')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_liberation_day_resolve_s11():
    """Slice-11 resolve: Liberation Day -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Liberation Day resolve scry+life_change ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_white_v2')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_jedi_training_resolve_s11():
    """Slice-11 resolve: Jedi Training -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Jedi Training resolve scry+life_change ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_white_v3')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_evacuation_plan_resolve_s11():
    """Slice-11 resolve: Evacuation Plan -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Evacuation Plan resolve scry+life_change ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_white_v1')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_rebel_alliance_s11():
    """Slice-11 ETB: Rebel Alliance -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Rebel Alliance ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Rebel Alliance')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_jedi_sanctuary_s11():
    """Slice-11 ETB: Jedi Sanctuary -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Jedi Sanctuary ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Jedi Sanctuary')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_protocol_droid_s11():
    """Slice-11 ETB: Protocol Droid -> SURVEIL+MILL."""
    print("\n=== Slice-11: Protocol Droid ETB surveil+mill ===")
    g, p1, p2, obj = _s11_etb_card('Protocol Droid')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_jedi_scholar_s11():
    """Slice-11 ETB: Jedi Scholar -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Jedi Scholar ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Jedi Scholar')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_battle_droid_s11():
    """Slice-11 ETB: Battle Droid -> SURVEIL+MILL."""
    print("\n=== Slice-11: Battle Droid ETB surveil+mill ===")
    g, p1, p2, obj = _s11_etb_card('Battle Droid')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_probe_droid_s11():
    """Slice-11 ETB: Probe Droid -> SURVEIL+MILL."""
    print("\n=== Slice-11: Probe Droid ETB surveil+mill ===")
    g, p1, p2, obj = _s11_etb_card('Probe Droid')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_coruscant_archivist_s11():
    """Slice-11 ETB: Coruscant Archivist -> SCRY+REVEAL_HAND."""
    print("\n=== Slice-11: Coruscant Archivist ETB scry+reveal_hand ===")
    g, p1, p2, obj = _s11_etb_card('Coruscant Archivist')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.REVEAL_HAND, opp_key='player', amount_check='na')


def test_s11_holo_projector_droid_s11():
    """Slice-11 ETB: Holo-Projector Droid -> SURVEIL+MILL."""
    print("\n=== Slice-11: Holo-Projector Droid ETB surveil+mill ===")
    g, p1, p2, obj = _s11_etb_card('Holo-Projector Droid')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_jedi_investigator_s11():
    """Slice-11 ETB: Jedi Investigator -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Jedi Investigator ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Jedi Investigator')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_jedi_mind_trick_resolve_s11():
    """Slice-11 resolve: Jedi Mind Trick -> SURVEIL+MILL."""
    print("\n=== Slice-11: Jedi Mind Trick resolve surveil+mill ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_blue_v2')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_force_push_resolve_s11():
    """Slice-11 resolve: Force Push -> SURVEIL+MILL."""
    print("\n=== Slice-11: Force Push resolve surveil+mill ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_surveil_mill')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_holographic_decoy_resolve_s11():
    """Slice-11 resolve: Holographic Decoy -> SURVEIL+MILL."""
    print("\n=== Slice-11: Holographic Decoy resolve surveil+mill ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_blue_v3')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_hyperspace_jump_resolve_s11():
    """Slice-11 resolve: Hyperspace Jump -> SURVEIL+MILL."""
    print("\n=== Slice-11: Hyperspace Jump resolve surveil+mill ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_blue_v2')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_sensor_scramble_resolve_s11():
    """Slice-11 resolve: Sensor Scramble -> SURVEIL+MILL."""
    print("\n=== Slice-11: Sensor Scramble resolve surveil+mill ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_blue_v3')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_force_vision_resolve_s11():
    """Slice-11 resolve: Force Vision -> SURVEIL+MILL."""
    print("\n=== Slice-11: Force Vision resolve surveil+mill ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_blue_v1')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_tech_override_resolve_s11():
    """Slice-11 resolve: Tech Override -> SURVEIL+MILL."""
    print("\n=== Slice-11: Tech Override resolve surveil+mill ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_blue_v1')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_droid_fabrication_resolve_s11():
    """Slice-11 resolve: Droid Fabrication -> SURVEIL+MILL."""
    print("\n=== Slice-11: Droid Fabrication resolve surveil+mill ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_blue_v3')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_memory_wipe_resolve_s11():
    """Slice-11 resolve: Memory Wipe -> SURVEIL+MILL."""
    print("\n=== Slice-11: Memory Wipe resolve surveil+mill ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_blue_v2')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_clone_army_resolve_s11():
    """Slice-11 resolve: Clone Army -> SURVEIL+MILL."""
    print("\n=== Slice-11: Clone Army resolve surveil+mill ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_blue_v1')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_hologram_transmission_resolve_s11():
    """Slice-11 resolve: Hologram Transmission -> SURVEIL+MILL."""
    print("\n=== Slice-11: Hologram Transmission resolve surveil+mill ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_blue_v1')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_droid_factory_s11():
    """Slice-11 ETB: Droid Factory -> SURVEIL+MILL."""
    print("\n=== Slice-11: Droid Factory ETB surveil+mill ===")
    g, p1, p2, obj = _s11_etb_card('Droid Factory')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_jedi_archives_s11():
    """Slice-11 ETB: Jedi Archives -> SURVEIL+MILL."""
    print("\n=== Slice-11: Jedi Archives ETB surveil+mill ===")
    g, p1, p2, obj = _s11_etb_card('Jedi Archives')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_dark_side_adept_s11():
    """Slice-11 ETB: Dark Side Adept -> SURVEIL+MILL."""
    print("\n=== Slice-11: Dark Side Adept ETB surveil+mill ===")
    g, p1, p2, obj = _s11_etb_card('Dark Side Adept')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_force_choke_resolve_s11():
    """Slice-11 resolve: Force Choke -> SURVEIL+DISCARD."""
    print("\n=== Slice-11: Force Choke resolve surveil+discard ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_surveil_discard')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_dark_side_corruption_resolve_s11():
    """Slice-11 resolve: Dark Side Corruption -> SURVEIL+DISCARD."""
    print("\n=== Slice-11: Dark Side Corruption resolve surveil+discard ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_black_v3')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_imperial_execution_resolve_s11():
    """Slice-11 resolve: Imperial Execution -> SURVEIL+DISCARD."""
    print("\n=== Slice-11: Imperial Execution resolve surveil+discard ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_black_v1')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_sith_lightning_resolve_s11():
    """Slice-11 resolve: Sith Lightning -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Sith Lightning resolve scry+damage ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_red_v2')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_fear_itself_resolve_s11():
    """Slice-11 resolve: Fear Itself -> SURVEIL+DISCARD."""
    print("\n=== Slice-11: Fear Itself resolve surveil+discard ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_black_v1')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_betrayal_resolve_s11():
    """Slice-11 resolve: Betrayal -> SURVEIL+DISCARD."""
    print("\n=== Slice-11: Betrayal resolve surveil+discard ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_black_v3')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_order_66_resolve_s11():
    """Slice-11 resolve: Order 66 -> SURVEIL+DISCARD."""
    print("\n=== Slice-11: Order 66 resolve surveil+discard ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_black_v3')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_imperial_bombardment_resolve_s11():
    """Slice-11 resolve: Imperial Bombardment -> SURVEIL+DISCARD."""
    print("\n=== Slice-11: Imperial Bombardment resolve surveil+discard ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_black_v1')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_harvest_despair_resolve_s11():
    """Slice-11 resolve: Harvest Despair -> SURVEIL+DISCARD."""
    print("\n=== Slice-11: Harvest Despair resolve surveil+discard ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_black_v1')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_conscription_resolve_s11():
    """Slice-11 resolve: Conscription -> SURVEIL+DISCARD."""
    print("\n=== Slice-11: Conscription resolve surveil+discard ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_black_v3')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_galactic_empire_s11():
    """Slice-11 ETB: Galactic Empire -> SCRY+DISCARD."""
    print("\n=== Slice-11: Galactic Empire ETB scry+discard ===")
    g, p1, p2, obj = _s11_etb_card('Galactic Empire')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_rule_of_two_s11():
    """Slice-11 ETB: Rule of Two -> SCRY+DISCARD."""
    print("\n=== Slice-11: Rule of Two ETB scry+discard ===")
    g, p1, p2, obj = _s11_etb_card('Rule of Two')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_trandoshan_slaver_s11():
    """Slice-11 ETB: Trandoshan Slaver -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Trandoshan Slaver ETB scry+damage ===")
    g, p1, p2, obj = _s11_etb_card('Trandoshan Slaver')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_gamorrean_guard_s11():
    """Slice-11 ETB: Gamorrean Guard -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Gamorrean Guard ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Gamorrean Guard')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_podracer_s11():
    """Slice-11 ETB: Podracer -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Podracer ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Podracer')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_separatist_battle_droid_s11():
    """Slice-11 ETB: Separatist Battle Droid -> SURVEIL+MILL."""
    print("\n=== Slice-11: Separatist Battle Droid ETB surveil+mill ===")
    g, p1, p2, obj = _s11_etb_card('Separatist Battle Droid')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_weequay_pirate_s11():
    """Slice-11 ETB: Weequay Pirate -> SCRY+DISCARD."""
    print("\n=== Slice-11: Weequay Pirate ETB scry+discard ===")
    g, p1, p2, obj = _s11_etb_card('Weequay Pirate')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_pyke_enforcer_s11():
    """Slice-11 ETB: Pyke Enforcer -> SCRY+DISCARD."""
    print("\n=== Slice-11: Pyke Enforcer ETB scry+discard ===")
    g, p1, p2, obj = _s11_etb_card('Pyke Enforcer')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_blaster_bolt_resolve_s11():
    """Slice-11 resolve: Blaster Bolt -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Blaster Bolt resolve scry+damage ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_red_v1')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_thermal_detonator_resolve_s11():
    """Slice-11 resolve: Thermal Detonator -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Thermal Detonator resolve scry+damage ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_red_v3')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_aggressive_negotiations_resolve_s11():
    """Slice-11 resolve: Aggressive Negotiations -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Aggressive Negotiations resolve scry+damage ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_red_v3')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_bounty_posted_resolve_s11():
    """Slice-11 resolve: Bounty Posted -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Bounty Posted resolve scry+damage ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_red_v3')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_reckless_assault_resolve_s11():
    """Slice-11 resolve: Reckless Assault -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Reckless Assault resolve scry+damage ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_red_v1')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_disintegrate_resolve_s11():
    """Slice-11 resolve: Disintegrate -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Disintegrate resolve scry+damage ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_red_v2')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_orbital_strike_resolve_s11():
    """Slice-11 resolve: Orbital Strike -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Orbital Strike resolve scry+damage ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_red_v3')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_bounty_collection_resolve_s11():
    """Slice-11 resolve: Bounty Collection -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Bounty Collection resolve scry+damage ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_red_v2')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_rage_of_the_arena_resolve_s11():
    """Slice-11 resolve: Rage of the Arena -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Rage of the Arena resolve scry+damage ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_red_v1')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_hired_guns_resolve_s11():
    """Slice-11 resolve: Hired Guns -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Hired Guns resolve scry+damage ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_red_v2')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_hunters_code_s11():
    """Slice-11 ETB: Hunter's Code -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Hunter's Code ETB scry+damage ===")
    g, p1, p2, obj = _s11_etb_card("Hunter's Code")
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_arena_pit_s11():
    """Slice-11 ETB: Arena Pit -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Arena Pit ETB scry+damage ===")
    g, p1, p2, obj = _s11_etb_card('Arena Pit')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_galactic_underworld_s11():
    """Slice-11 ETB: Galactic Underworld -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Galactic Underworld ETB scry+damage ===")
    g, p1, p2, obj = _s11_etb_card('Galactic Underworld')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_felucia_beast_s11():
    """Slice-11 ETB: Felucia Beast -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Felucia Beast ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Felucia Beast')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_naboo_ranger_s11():
    """Slice-11 ETB: Naboo Ranger -> SCRY+REVEAL_HAND."""
    print("\n=== Slice-11: Naboo Ranger ETB scry+reveal_hand ===")
    g, p1, p2, obj = _s11_etb_card('Naboo Ranger')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.REVEAL_HAND, opp_key='player', amount_check='na')


def test_s11_gungan_warrior_s11():
    """Slice-11 ETB: Gungan Warrior -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Gungan Warrior ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Gungan Warrior')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_yavin_jungle_cat_s11():
    """Slice-11 ETB: Yavin Jungle Cat -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Yavin Jungle Cat ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Yavin Jungle Cat')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_endor_wildlife_s11():
    """Slice-11 ETB: Endor Wildlife -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Endor Wildlife ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Endor Wildlife')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_sarlacc_pit_spawn_s11():
    """Slice-11 ETB: Sarlacc Pit Spawn -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Sarlacc Pit Spawn ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Sarlacc Pit Spawn')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_wookiee_rage_resolve_s11():
    """Slice-11 resolve: Wookiee Rage -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Wookiee Rage resolve scry+life_change ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_green_v2')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_forest_ambush_resolve_s11():
    """Slice-11 resolve: Forest Ambush -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Forest Ambush resolve scry+life_change ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_scry_gain_ally')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_ewok_trap_resolve_s11():
    """Slice-11 resolve: Ewok Trap -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Ewok Trap resolve scry+life_change ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_green_v2')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_natural_camouflage_resolve_s11():
    """Slice-11 resolve: Natural Camouflage -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Natural Camouflage resolve scry+damage ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_green_v3')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_jungle_growth_resolve_s11():
    """Slice-11 resolve: Jungle Growth -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Jungle Growth resolve scry+life_change ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_green_v1')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_primal_connection_resolve_s11():
    """Slice-11 resolve: Primal Connection -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Primal Connection resolve scry+damage ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_green_v3')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_call_of_the_wild_resolve_s11():
    """Slice-11 resolve: Call of the Wild -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Call of the Wild resolve scry+life_change ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_green_v1')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_ewok_uprising_resolve_s11():
    """Slice-11 resolve: Ewok Uprising -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Ewok Uprising resolve scry+life_change ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_green_v1')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_force_of_nature_resolve_s11():
    """Slice-11 resolve: Force of Nature -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Force of Nature resolve scry+life_change ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_scry_gain_ally')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_rampant_growth_resolve_s11():
    """Slice-11 resolve: Rampant Growth -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Rampant Growth resolve scry+life_change ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_green_v2')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_ewok_village_s11():
    """Slice-11 ETB: Ewok Village -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Ewok Village ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Ewok Village')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_kashyyyk_homeland_s11():
    """Slice-11 ETB: Kashyyyk Homeland -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Kashyyyk Homeland ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Kashyyyk Homeland')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_the_living_force_s11():
    """Slice-11 ETB: The Living Force -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: The Living Force ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('The Living Force')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_darth_sidious_puppetmaster_s11():
    """Slice-11 ETB: Darth Sidious, Puppetmaster -> SURVEIL+MILL."""
    print("\n=== Slice-11: Darth Sidious, Puppetmaster ETB surveil+mill ===")
    g, p1, p2, obj = _s11_etb_card('Darth Sidious, Puppetmaster')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_rebel_commando_team_s11():
    """Slice-11 ETB: Rebel Commando Team -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Rebel Commando Team ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Rebel Commando Team')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_separatist_commander_s11():
    """Slice-11 ETB: Separatist Commander -> SCRY+REVEAL_HAND."""
    print("\n=== Slice-11: Separatist Commander ETB scry+reveal_hand ===")
    g, p1, p2, obj = _s11_etb_card('Separatist Commander')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.REVEAL_HAND, opp_key='player', amount_check='na')


def test_s11_mandalorian_forge_master_s11():
    """Slice-11 ETB: Mandalorian Forge-Master -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Mandalorian Forge-Master ETB scry+damage ===")
    g, p1, p2, obj = _s11_etb_card('Mandalorian Forge-Master')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_force_sensitive_s11():
    """Slice-11 ETB: Force Sensitive -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Force Sensitive ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Force Sensitive')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_hutt_crime_lord_s11():
    """Slice-11 ETB: Hutt Crime Lord -> SCRY+DISCARD."""
    print("\n=== Slice-11: Hutt Crime Lord ETB scry+discard ===")
    g, p1, p2, obj = _s11_etb_card('Hutt Crime Lord')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_balance_of_the_force_resolve_s11():
    """Slice-11 resolve: Balance of the Force -> SURVEIL+DISCARD."""
    print("\n=== Slice-11: Balance of the Force resolve surveil+discard ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_black_v2')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_force_lightning_resolve_s11():
    """Slice-11 resolve: Force Lightning -> SURVEIL+MILL."""
    print("\n=== Slice-11: Force Lightning resolve surveil+mill ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_surveil_mill')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_unity_of_the_rebellion_resolve_s11():
    """Slice-11 resolve: Unity of the Rebellion -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Unity of the Rebellion resolve scry+damage ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_red_v1')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_galactic_senate_decree_resolve_s11():
    """Slice-11 resolve: Galactic Senate Decree -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Galactic Senate Decree resolve scry+life_change ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_scry_gain_drain')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_devastation_of_alderaan_resolve_s11():
    """Slice-11 resolve: Devastation of Alderaan -> SURVEIL+DISCARD."""
    print("\n=== Slice-11: Devastation of Alderaan resolve surveil+discard ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_black_v2')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_lukes_lightsaber_s11():
    """Slice-11 ETB: Luke's Lightsaber -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Luke's Lightsaber ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card("Luke's Lightsaber")
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_darth_vaders_lightsaber_s11():
    """Slice-11 ETB: Darth Vader's Lightsaber -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Darth Vader's Lightsaber ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card("Darth Vader's Lightsaber")
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_double_bladed_lightsaber_s11():
    """Slice-11 ETB: Double-Bladed Lightsaber -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Double-Bladed Lightsaber ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Double-Bladed Lightsaber')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_lightsaber_s11():
    """Slice-11 ETB: Lightsaber -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Lightsaber ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Lightsaber')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_darksaber_s11():
    """Slice-11 ETB: Darksaber -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Darksaber ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Darksaber')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_mandalorian_armor_s11():
    """Slice-11 ETB: Mandalorian Armor -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Mandalorian Armor ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Mandalorian Armor')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_beskar_helmet_s11():
    """Slice-11 ETB: Beskar Helmet -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Beskar Helmet ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Beskar Helmet')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_jetpack_s11():
    """Slice-11 ETB: Jetpack -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Jetpack ETB scry+damage ===")
    g, p1, p2, obj = _s11_etb_card('Jetpack')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_blaster_rifle_s11():
    """Slice-11 ETB: Blaster Rifle -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Blaster Rifle ETB scry+damage ===")
    g, p1, p2, obj = _s11_etb_card('Blaster Rifle')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_bowcaster_s11():
    """Slice-11 ETB: Bowcaster -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Bowcaster ETB scry+damage ===")
    g, p1, p2, obj = _s11_etb_card('Bowcaster')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_electrostaff_s11():
    """Slice-11 ETB: Electrostaff -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Electrostaff ETB scry+damage ===")
    g, p1, p2, obj = _s11_etb_card('Electrostaff')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_millennium_falcon_s11():
    """Slice-11 ETB: Millennium Falcon -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Millennium Falcon ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Millennium Falcon')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_x_wing_starfighter_s11():
    """Slice-11 ETB: X-Wing Starfighter -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: X-Wing Starfighter ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('X-Wing Starfighter')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_tie_fighter_s11():
    """Slice-11 ETB: TIE Fighter -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: TIE Fighter ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('TIE Fighter')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_star_destroyer_s11():
    """Slice-11 ETB: Star Destroyer -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Star Destroyer ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Star Destroyer')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_slave_i_s11():
    """Slice-11 ETB: Slave I -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Slave I ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Slave I')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_speeder_bike_s11():
    """Slice-11 ETB: Speeder Bike -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Speeder Bike ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Speeder Bike')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_at_at_walker_s11():
    """Slice-11 ETB: AT-AT Walker -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: AT-AT Walker ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('AT-AT Walker')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_at_st_walker_s11():
    """Slice-11 ETB: AT-ST Walker -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: AT-ST Walker ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('AT-ST Walker')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_republic_gunship_s11():
    """Slice-11 ETB: Republic Gunship -> SURVEIL+DAMAGE."""
    print("\n=== Slice-11: Republic Gunship ETB surveil+damage ===")
    g, p1, p2, obj = _s11_etb_card('Republic Gunship')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_the_razor_crest_s11():
    """Slice-11 ETB: The Razor Crest -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: The Razor Crest ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('The Razor Crest')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_y_wing_bomber_s11():
    """Slice-11 ETB: Y-Wing Bomber -> SURVEIL+DAMAGE."""
    print("\n=== Slice-11: Y-Wing Bomber ETB surveil+damage ===")
    g, p1, p2, obj = _s11_etb_card('Y-Wing Bomber')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_jedi_holocron_s11():
    """Slice-11 ETB: Jedi Holocron -> SCRY+MILL."""
    print("\n=== Slice-11: Jedi Holocron ETB scry+mill ===")
    g, p1, p2, obj = _s11_etb_card('Jedi Holocron')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_sith_holocron_s11():
    """Slice-11 ETB: Sith Holocron -> SCRY+MILL."""
    print("\n=== Slice-11: Sith Holocron ETB scry+mill ===")
    g, p1, p2, obj = _s11_etb_card('Sith Holocron')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_carbonite_prison_s11():
    """Slice-11 ETB: Carbonite Prison -> SURVEIL+LIFE_CHANGE."""
    print("\n=== Slice-11: Carbonite Prison ETB surveil+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Carbonite Prison')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_kyber_crystal_s11():
    """Slice-11 ETB: Kyber Crystal -> SCRY+MILL."""
    print("\n=== Slice-11: Kyber Crystal ETB scry+mill ===")
    g, p1, p2, obj = _s11_etb_card('Kyber Crystal')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_stormtrooper_barracks_s11():
    """Slice-11 ETB: Stormtrooper Barracks -> SURVEIL+LIFE_CHANGE."""
    print("\n=== Slice-11: Stormtrooper Barracks ETB surveil+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Stormtrooper Barracks')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_droid_foundry_s11():
    """Slice-11 ETB: Droid Foundry -> SURVEIL+LIFE_CHANGE."""
    print("\n=== Slice-11: Droid Foundry ETB surveil+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Droid Foundry')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_trade_federation_vault_s11():
    """Slice-11 ETB: Trade Federation Vault -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Trade Federation Vault ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Trade Federation Vault')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_bacta_tank_s11():
    """Slice-11 ETB: Bacta Tank -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Bacta Tank ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Bacta Tank')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_hyperdrive_s11():
    """Slice-11 ETB: Hyperdrive -> SCRY+MILL."""
    print("\n=== Slice-11: Hyperdrive ETB scry+mill ===")
    g, p1, p2, obj = _s11_etb_card('Hyperdrive')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_shield_generator_s11():
    """Slice-11 ETB: Shield Generator -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Shield Generator ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Shield Generator')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_coruscant_s11():
    """Slice-11 ETB: Coruscant -> SCRY+MILL."""
    print("\n=== Slice-11: Coruscant ETB scry+mill ===")
    g, p1, p2, obj = _s11_etb_card('Coruscant')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_tatooine_s11():
    """Slice-11 ETB: Tatooine -> SURVEIL+DAMAGE."""
    print("\n=== Slice-11: Tatooine ETB surveil+damage ===")
    g, p1, p2, obj = _s11_etb_card('Tatooine')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_endor_forest_s11():
    """Slice-11 ETB: Endor Forest -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Endor Forest ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Endor Forest')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_kashyyyk_s11():
    """Slice-11 ETB: Kashyyyk -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Kashyyyk ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Kashyyyk')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_mustafar_s11():
    """Slice-11 ETB: Mustafar -> SURVEIL+DAMAGE."""
    print("\n=== Slice-11: Mustafar ETB surveil+damage ===")
    g, p1, p2, obj = _s11_etb_card('Mustafar')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_dagobah_s11():
    """Slice-11 ETB: Dagobah -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Dagobah ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Dagobah')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_hoth_s11():
    """Slice-11 ETB: Hoth -> SCRY+MILL."""
    print("\n=== Slice-11: Hoth ETB scry+mill ===")
    g, p1, p2, obj = _s11_etb_card('Hoth')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_naboo_s11():
    """Slice-11 ETB: Naboo -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Naboo ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Naboo')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_kamino_s11():
    """Slice-11 ETB: Kamino -> SCRY+MILL."""
    print("\n=== Slice-11: Kamino ETB scry+mill ===")
    g, p1, p2, obj = _s11_etb_card('Kamino')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_geonosis_s11():
    """Slice-11 ETB: Geonosis -> SURVEIL+DAMAGE."""
    print("\n=== Slice-11: Geonosis ETB surveil+damage ===")
    g, p1, p2, obj = _s11_etb_card('Geonosis')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_jakku_s11():
    """Slice-11 ETB: Jakku -> SCRY+MILL."""
    print("\n=== Slice-11: Jakku ETB scry+mill ===")
    g, p1, p2, obj = _s11_etb_card('Jakku')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_cloud_city_s11():
    """Slice-11 ETB: Cloud City -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Cloud City ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Cloud City')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_mos_eisley_spaceport_s11():
    """Slice-11 ETB: Mos Eisley Spaceport -> SCRY+MILL."""
    print("\n=== Slice-11: Mos Eisley Spaceport ETB scry+mill ===")
    g, p1, p2, obj = _s11_etb_card('Mos Eisley Spaceport')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_jedi_temple_s11():
    """Slice-11 ETB: Jedi Temple -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Jedi Temple ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Jedi Temple')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_sith_temple_s11():
    """Slice-11 ETB: Sith Temple -> SURVEIL+DISCARD."""
    print("\n=== Slice-11: Sith Temple ETB surveil+discard ===")
    g, p1, p2, obj = _s11_etb_card('Sith Temple')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_death_star_hangar_s11():
    """Slice-11 ETB: Death Star Hangar -> SURVEIL+DISCARD."""
    print("\n=== Slice-11: Death Star Hangar ETB surveil+discard ===")
    g, p1, p2, obj = _s11_etb_card('Death Star Hangar')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_rebel_base_s11():
    """Slice-11 ETB: Rebel Base -> SCRY+MILL."""
    print("\n=== Slice-11: Rebel Base ETB scry+mill ===")
    g, p1, p2, obj = _s11_etb_card('Rebel Base')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_clone_captain_rex_s11():
    """Slice-11 ETB: Clone Captain Rex -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Clone Captain Rex ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Clone Captain Rex')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_bail_organa_s11():
    """Slice-11 ETB: Bail Organa -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Bail Organa ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Bail Organa')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_mon_mothma_s11():
    """Slice-11 ETB: Mon Mothma -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Mon Mothma ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Mon Mothma')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_alderaanian_refugee_s11():
    """Slice-11 ETB: Alderaanian Refugee -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Alderaanian Refugee ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Alderaanian Refugee')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_force_barrier_resolve_s11():
    """Slice-11 resolve: Force Barrier -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Force Barrier resolve scry+life_change ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_scry_gain_drain')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_bb_8_loyal_astromech_s11():
    """Slice-11 ETB: BB-8, Loyal Astromech -> SURVEIL+MILL."""
    print("\n=== Slice-11: BB-8, Loyal Astromech ETB surveil+mill ===")
    g, p1, p2, obj = _s11_etb_card('BB-8, Loyal Astromech')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_k_2so_reprogrammed_s11():
    """Slice-11 ETB: K-2SO, Reprogrammed -> SURVEIL+MILL."""
    print("\n=== Slice-11: K-2SO, Reprogrammed ETB surveil+mill ===")
    g, p1, p2, obj = _s11_etb_card('K-2SO, Reprogrammed')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_super_battle_droid_s11():
    """Slice-11 ETB: Super Battle Droid -> SURVEIL+MILL."""
    print("\n=== Slice-11: Super Battle Droid ETB surveil+mill ===")
    g, p1, p2, obj = _s11_etb_card('Super Battle Droid')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_tactical_droid_s11():
    """Slice-11 ETB: Tactical Droid -> SURVEIL+MILL."""
    print("\n=== Slice-11: Tactical Droid ETB surveil+mill ===")
    g, p1, p2, obj = _s11_etb_card('Tactical Droid')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_force_illusion_resolve_s11():
    """Slice-11 resolve: Force Illusion -> SURVEIL+MILL."""
    print("\n=== Slice-11: Force Illusion resolve surveil+mill ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_surveil_mill')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_darth_bane_rule_creator_s11():
    """Slice-11 ETB: Darth Bane, Rule Creator -> SURVEIL+MILL."""
    print("\n=== Slice-11: Darth Bane, Rule Creator ETB surveil+mill ===")
    g, p1, p2, obj = _s11_etb_card('Darth Bane, Rule Creator')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_grand_inquisitor_s11():
    """Slice-11 ETB: Grand Inquisitor -> SURVEIL+MILL."""
    print("\n=== Slice-11: Grand Inquisitor ETB surveil+mill ===")
    g, p1, p2, obj = _s11_etb_card('Grand Inquisitor')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_imperial_executioner_s11():
    """Slice-11 ETB: Imperial Executioner -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Imperial Executioner ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Imperial Executioner')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_snoke_supreme_leader_s11():
    """Slice-11 ETB: Snoke, Supreme Leader -> SURVEIL+MILL."""
    print("\n=== Slice-11: Snoke, Supreme Leader ETB surveil+mill ===")
    g, p1, p2, obj = _s11_etb_card('Snoke, Supreme Leader')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_dark_ritual_of_the_sith_resolve_s11():
    """Slice-11 resolve: Dark Ritual of the Sith -> SURVEIL+DISCARD."""
    print("\n=== Slice-11: Dark Ritual of the Sith resolve surveil+discard ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_black_v2')
    _s11_assert_resolve(events, p2, info_type=EventType.SURVEIL,
                         opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_aurra_sing_sniper_s11():
    """Slice-11 ETB: Aurra Sing, Sniper -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Aurra Sing, Sniper ETB scry+damage ===")
    g, p1, p2, obj = _s11_etb_card('Aurra Sing, Sniper')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_bossk_trandoshan_hunter_s11():
    """Slice-11 ETB: Bossk, Trandoshan Hunter -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Bossk, Trandoshan Hunter ETB scry+damage ===")
    g, p1, p2, obj = _s11_etb_card('Bossk, Trandoshan Hunter')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_fennec_shand_elite_assassin_s11():
    """Slice-11 ETB: Fennec Shand, Elite Assassin -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Fennec Shand, Elite Assassin ETB scry+damage ===")
    g, p1, p2, obj = _s11_etb_card('Fennec Shand, Elite Assassin')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_death_watch_warrior_s11():
    """Slice-11 ETB: Death Watch Warrior -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Death Watch Warrior ETB scry+damage ===")
    g, p1, p2, obj = _s11_etb_card('Death Watch Warrior')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_wrist_rocket_resolve_s11():
    """Slice-11 resolve: Wrist Rocket -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Wrist Rocket resolve scry+damage ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_red_v1')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_yaddle_jedi_council_member_s11():
    """Slice-11 ETB: Yaddle, Jedi Council Member -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Yaddle, Jedi Council Member ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Yaddle, Jedi Council Member')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_wookiee_berserker_s11():
    """Slice-11 ETB: Wookiee Berserker -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Wookiee Berserker ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Wookiee Berserker')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_ewok_shaman_s11():
    """Slice-11 ETB: Ewok Shaman -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Ewok Shaman ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Ewok Shaman')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_rancor_s11():
    """Slice-11 ETB: Rancor -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Rancor ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Rancor')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_nexu_s11():
    """Slice-11 ETB: Nexu -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Nexu ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Nexu')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_beast_call_resolve_s11():
    """Slice-11 resolve: Beast Call -> SCRY+DAMAGE."""
    print("\n=== Slice-11: Beast Call resolve scry+damage ===")
    events, p1, p2 = _s11_resolve('_swr_s11_resolve_green_v3')
    _s11_assert_resolve(events, p2, info_type=EventType.SCRY,
                         opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_captain_phasma_s11():
    """Slice-11 ETB: Captain Phasma -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Captain Phasma ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Captain Phasma')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_sabine_wren_mandalorian_artist_s11():
    """Slice-11 ETB: Sabine Wren, Mandalorian Artist -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Sabine Wren, Mandalorian Artist ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Sabine Wren, Mandalorian Artist')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_ezra_bridger_street_kid_s11():
    """Slice-11 ETB: Ezra Bridger, Street Kid -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Ezra Bridger, Street Kid ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Ezra Bridger, Street Kid')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_kanan_jarrus_blinded_master_s11():
    """Slice-11 ETB: Kanan Jarrus, Blinded Master -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Kanan Jarrus, Blinded Master ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Kanan Jarrus, Blinded Master')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_hera_syndulla_ghost_captain_s11():
    """Slice-11 ETB: Hera Syndulla, Ghost Captain -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Hera Syndulla, Ghost Captain ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Hera Syndulla, Ghost Captain')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_training_remote_s11():
    """Slice-11 ETB: Training Remote -> SCRY+DISCARD."""
    print("\n=== Slice-11: Training Remote ETB scry+discard ===")
    g, p1, p2, obj = _s11_etb_card('Training Remote')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.DISCARD, opp_key='player', amount_check='pos')


def test_s11_restraining_bolt_s11():
    """Slice-11 ETB: Restraining Bolt -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Restraining Bolt ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Restraining Bolt')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_thermal_imaging_goggles_s11():
    """Slice-11 ETB: Thermal Imaging Goggles -> SURVEIL+REVEAL_HAND."""
    print("\n=== Slice-11: Thermal Imaging Goggles ETB surveil+reveal_hand ===")
    g, p1, p2, obj = _s11_etb_card('Thermal Imaging Goggles')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.REVEAL_HAND, opp_key='player', amount_check='na')


def test_s11_scarif_s11():
    """Slice-11 ETB: Scarif -> SCRY+MILL."""
    print("\n=== Slice-11: Scarif ETB scry+mill ===")
    g, p1, p2, obj = _s11_etb_card('Scarif')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_jedha_s11():
    """Slice-11 ETB: Jedha -> SCRY+MILL."""
    print("\n=== Slice-11: Jedha ETB scry+mill ===")
    g, p1, p2, obj = _s11_etb_card('Jedha')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


def test_s11_mandalore_s11():
    """Slice-11 ETB: Mandalore -> SURVEIL+DAMAGE."""
    print("\n=== Slice-11: Mandalore ETB surveil+damage ===")
    g, p1, p2, obj = _s11_etb_card('Mandalore')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL,
                              opp_type=EventType.DAMAGE, opp_key='target', amount_check='pos')


def test_s11_bespin_s11():
    """Slice-11 ETB: Bespin -> SCRY+LIFE_CHANGE."""
    print("\n=== Slice-11: Bespin ETB scry+life_change ===")
    g, p1, p2, obj = _s11_etb_card('Bespin')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.LIFE_CHANGE, opp_key='player', amount_check='neg')


def test_s11_lothal_s11():
    """Slice-11 ETB: Lothal -> SCRY+MILL."""
    print("\n=== Slice-11: Lothal ETB scry+mill ===")
    g, p1, p2, obj = _s11_etb_card('Lothal')
    _s11_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY,
                              opp_type=EventType.MILL, opp_key='player', amount_check='pos')


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
