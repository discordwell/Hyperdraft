"""
Lord of the Rings Spice Pass Tests (Phase A)

Mirrors test_star_wars_spice.py / test_dragon_ball_spice.py for the LotR set.
Validates the format-defining cards added in the LotR Phase A spice pass:

- Aragorn, King Returned (compression)
- Gandalf, Mithrandir (compression)
- Galadriel, Lady of Lothlorien (snowball / Fellowship)
- Witch-king, Black Captain (hard-to-interact + asymmetric prison)
- The One Ring (mythic compression — replaced)
- Anduril, Flame of the West (equipment compression — replaced)
- Mithril Coat (hard-to-interact equipment — replaced)
- Lothlorien (Fellowship-anchored utility land — replaced)
"""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Characteristics,
    get_power, get_toughness,
)

# Direct import: avoid __init__.py import-graph issues; mirror
# tests/test_lord_of_the_rings.py.
import importlib.util
spec = importlib.util.spec_from_file_location(
    "lord_of_the_rings",
    str(PROJECT_ROOT / "src/cards/custom/lord_of_the_rings.py"),
)
lotr_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lotr_module)
LORD_OF_THE_RINGS_CARDS = lotr_module.LORD_OF_THE_RINGS_CARDS


def _put_on_battlefield(game, player, card_name):
    """Standard pattern: create in hand without card_def, then ZONE_CHANGE.

    See spice-pass.md gotcha #10: the library/cast filters insist on a real
    card_def, so for tests that invoke filters/handlers we must attach the
    real def AFTER object creation (so setup_interceptors runs once via the
    ZONE_CHANGE pipeline, not twice via create_object).
    """
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
    """Snapshot of EventType names that have been logged."""
    return [e.type.name for e in game.state.event_log]


def _drop_legendary(game, player_id, name="Helper Hero"):
    """Helper: drop a generic Legendary creature for Fellowship gating tests."""
    return game.create_object(
        name=name,
        owner_id=player_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            supertypes={"Legendary"},
            subtypes={"Human"},
            power=2, toughness=2,
        ),
    )


# ============================================================================
# Aragorn, King Returned
# ============================================================================

def test_aragorn_returned_loads_with_keywords():
    """Aragorn registers self vigilance+haste, attack trigger, dynamic P/T."""
    print("\n=== Aragorn Returned: load + interceptors ===")
    game = Game()
    p1 = game.add_player("Alice")
    aragorn = _put_on_battlefield(game, p1, "Aragorn, King Returned")
    assert aragorn.zone == ZoneType.BATTLEFIELD
    # Expect at least 4 interceptors: keyword grant, attack trigger,
    # 2 dynamic P/T (QUERY_POWER + QUERY_TOUGHNESS).
    assert len(aragorn.interceptor_ids) >= 4, (
        f"Expected ≥4 interceptors, got {len(aragorn.interceptor_ids)}"
    )
    assert 'Legendary' in aragorn.characteristics.supertypes
    assert 'Human' in aragorn.characteristics.subtypes
    print(f"  Interceptors: {len(aragorn.interceptor_ids)}")


def test_aragorn_fellowship_pt_scaling():
    """Aragorn is 4/4 alone, +X/+X with X = legendary creatures controlled."""
    print("\n=== Aragorn Returned: Fellowship dynamic P/T ===")
    game = Game()
    p1 = game.add_player("Alice")
    aragorn = _put_on_battlefield(game, p1, "Aragorn, King Returned")

    # Alone: count legendary creatures = 1 (himself), so +1/+1 → 5/5.
    pwr_alone = get_power(aragorn, game.state)
    tgh_alone = get_toughness(aragorn, game.state)
    assert pwr_alone == 4 + 1, f"Alone: expected 5 power, got {pwr_alone}"
    assert tgh_alone == 4 + 1, f"Alone: expected 5 toughness, got {tgh_alone}"

    # Add 2 more legendaries → count = 3, +3/+3 → 7/7.
    _drop_legendary(game, p1.id, "L1")
    _drop_legendary(game, p1.id, "L2")
    pwr_three = get_power(aragorn, game.state)
    tgh_three = get_toughness(aragorn, game.state)
    assert pwr_three == 4 + 3, f"Fellowship 3: expected 7 power, got {pwr_three}"
    assert tgh_three == 4 + 3, f"Fellowship 3: expected 7 toughness, got {tgh_three}"
    print(f"  Alone: {pwr_alone}/{tgh_alone}; with 3 legendaries: {pwr_three}/{tgh_three}")


def test_aragorn_attack_trigger_pumps_humans():
    """Aragorn attacks → other Humans get +1/+1 EOT and first strike."""
    print("\n=== Aragorn Returned: attack pumps Humans ===")
    game = Game()
    p1 = game.add_player("Alice")
    aragorn = _put_on_battlefield(game, p1, "Aragorn, King Returned")

    # Drop a non-legendary Human Soldier — Aragorn pumps OTHER humans.
    other_human = game.create_object(
        name="Foot Soldier",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Human", "Soldier"},
            colors={Color.WHITE},
            power=2, toughness=2,
        ),
    )
    # Drop a non-Human (Elf) — should NOT receive the buff.
    elf = game.create_object(
        name="Foot Elf",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Elf"},
            colors={Color.GREEN},
            power=2, toughness=2,
        ),
    )

    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': aragorn.id, 'attacker': aragorn.id, 'defender': 'opponent'},
        source=aragorn.id,
    ))
    after = _emitted_types(game)
    new = after[len(before):]
    # Verify PT_MODIFICATION was emitted targeting the Human, NOT the Elf.
    pt_mods = [e for e in game.state.event_log
               if e.type == EventType.PT_MODIFICATION
               and e.source == aragorn.id]
    targeted = {e.payload.get('object_id') for e in pt_mods}
    assert other_human.id in targeted, (
        f"Other Human should receive +1/+1; targeted={targeted}"
    )
    assert elf.id not in targeted, (
        f"Non-Human should NOT receive Aragorn's pump; targeted={targeted}"
    )
    assert 'GRANT_KEYWORD' in new, f"first strike grant not emitted: {new}"
    print(f"  Human pumped, Elf skipped, first_strike granted")


def test_aragorn_does_not_self_pump_on_attack():
    """Edge: Aragorn's attack trigger pumps OTHER humans, not himself."""
    print("\n=== Aragorn Returned: doesn't self-pump on attack ===")
    game = Game()
    p1 = game.add_player("Alice")
    aragorn = _put_on_battlefield(game, p1, "Aragorn, King Returned")

    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': aragorn.id, 'attacker': aragorn.id, 'defender': 'opponent'},
        source=aragorn.id,
    ))
    pt_mods = [e for e in game.state.event_log
               if e.type == EventType.PT_MODIFICATION
               and e.source == aragorn.id]
    aragorn_targets = [e for e in pt_mods if e.payload.get('object_id') == aragorn.id]
    assert not aragorn_targets, (
        f"Aragorn's attack trigger should not target himself; got {aragorn_targets}"
    )
    print("  Aragorn correctly excluded from his own attack pump")


# ============================================================================
# Gandalf, Mithrandir
# ============================================================================

def test_gandalf_mithrandir_loads_with_flash_hexproof():
    """Gandalf, Mithrandir registers flash+hexproof + ETB + spell trigger."""
    print("\n=== Gandalf Mithrandir: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    gandalf = _put_on_battlefield(game, p1, "Gandalf, Mithrandir")
    assert 'Wizard' in gandalf.characteristics.subtypes
    # 3 interceptors: keyword grant, ETB trigger, spell-cast trigger.
    assert len(gandalf.interceptor_ids) >= 3, (
        f"Expected ≥3 interceptors, got {len(gandalf.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(gandalf.interceptor_ids)}")


def test_gandalf_mithrandir_etb_draws_two_and_creates_token():
    """ETB emits DRAW (amount=2) and at least one CREATE_TOKEN (Spirit)."""
    print("\n=== Gandalf Mithrandir: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = _emitted_types(game)
    gandalf = _put_on_battlefield(game, p1, "Gandalf, Mithrandir")
    after = _emitted_types(game)
    new = after[len(before):]
    assert 'DRAW' in new, f"DRAW not emitted: {new}"
    # At least one Spirit (Gandalf himself is a Wizard).
    create_tokens = [e for e in game.state.event_log
                     if e.type == EventType.CREATE_TOKEN
                     and e.source == gandalf.id]
    assert create_tokens, f"No CREATE_TOKEN emitted: {new}"
    spirit = create_tokens[-1].payload.get('token', {})
    assert spirit.get('name') == 'Spirit'
    assert 'Spirit' in spirit.get('subtypes', set())
    # Verify draw amount.
    draws = [e for e in game.state.event_log
             if e.type == EventType.DRAW
             and e.source == gandalf.id]
    assert draws and draws[-1].payload.get('amount') == 2, (
        f"Should draw 2; got {draws[-1].payload if draws else 'none'}"
    )
    print(f"  Drew 2, created Spirit token {spirit.get('subtypes')}")


def test_gandalf_mithrandir_etb_scales_with_wizards():
    """If you control multiple wizards, Gandalf creates more tokens."""
    print("\n=== Gandalf Mithrandir: ETB scales with Wizards ===")
    game = Game()
    p1 = game.add_player("Alice")

    # Drop two non-legendary Wizards first.
    for i in range(2):
        game.create_object(
            name=f"Apprentice {i}",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(
                types={CardType.CREATURE},
                subtypes={"Human", "Wizard"},
                colors={Color.BLUE},
                power=1, toughness=1,
            ),
        )
    before = _emitted_types(game)
    gandalf = _put_on_battlefield(game, p1, "Gandalf, Mithrandir")
    create_tokens = [e for e in game.state.event_log
                     if e.type == EventType.CREATE_TOKEN
                     and e.source == gandalf.id]
    # Gandalf himself is a Wizard, so 2 apprentices + Gandalf = 3 spirits.
    assert len(create_tokens) >= 3, (
        f"Expected ≥3 Spirit tokens (1 per Wizard incl. self); got {len(create_tokens)}"
    )
    print(f"  Created {len(create_tokens)} Spirit tokens with 3 Wizards")


def test_gandalf_spell_cast_trigger_pumps():
    """Casting an instant/sorcery → Gandalf gets +1/+0 EOT."""
    print("\n=== Gandalf Mithrandir: spell-cast pump ===")
    game = Game()
    p1 = game.add_player("Alice")
    gandalf = _put_on_battlefield(game, p1, "Gandalf, Mithrandir")
    base_p = get_power(gandalf, game.state)

    # Synth a SPELL_CAST event for an instant. The default filter on
    # make_spell_cast_trigger reads payload['types'] (set of CardType) and
    # payload['caster'] (the controller). Mirror that shape.
    inst = game.create_object(
        name="Lightning Bolt",
        owner_id=p1.id,
        zone=ZoneType.STACK,
        characteristics=Characteristics(types={CardType.INSTANT}),
    )
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={
            'object_id': inst.id,
            'caster': p1.id,
            'controller': p1.id,
            'types': {CardType.INSTANT},
        },
        source=inst.id,
        controller=p1.id,
    ))
    new_p = get_power(gandalf, game.state)
    assert new_p == base_p + 1, (
        f"Gandalf should be +1/+0 after instant cast: {base_p}→{new_p}"
    )
    print(f"  Gandalf {base_p}→{new_p} after instant cast")


# ============================================================================
# Galadriel, Lady of Lothlorien
# ============================================================================

def test_galadriel_lothlorien_loads():
    """Galadriel registers anthem + hexproof + upkeep trigger."""
    print("\n=== Galadriel Lothlorien: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    g = _put_on_battlefield(game, p1, "Galadriel, Lady of Lothlorien")
    # 2 P/T boost (QUERY_POWER + QUERY_TOUGHNESS) + keyword grant + upkeep trigger = 4.
    assert len(g.interceptor_ids) >= 4, (
        f"Expected ≥4 interceptors, got {len(g.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(g.interceptor_ids)}")


def test_galadriel_lothlorien_buffs_elves_and_humans():
    """Lord effect: other Elves and Humans get +1/+1."""
    print("\n=== Galadriel Lothlorien: tribal lord ===")
    game = Game()
    p1 = game.add_player("Alice")

    elf = game.create_object(
        name="Wood Elf",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Elf"},
            colors={Color.GREEN},
            power=2, toughness=2,
        ),
    )
    human = game.create_object(
        name="Town Guard",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Human"},
            colors={Color.WHITE},
            power=2, toughness=2,
        ),
    )
    dwarf = game.create_object(
        name="Hill Dwarf",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Dwarf"},
            colors={Color.RED},
            power=2, toughness=2,
        ),
    )

    _put_on_battlefield(game, p1, "Galadriel, Lady of Lothlorien")
    assert get_power(elf, game.state) == 3, "Elf should be +1/+1"
    assert get_power(human, game.state) == 3, "Human should be +1/+1"
    assert get_power(dwarf, game.state) == 2, "Dwarf should NOT be buffed"
    print(f"  Elf {get_power(elf, game.state)}, Human {get_power(human, game.state)}, Dwarf {get_power(dwarf, game.state)}")


def test_galadriel_upkeep_scry_no_fellowship():
    """Edge: with <3 legendary creatures, upkeep emits SCRY but no DRAW."""
    print("\n=== Galadriel Lothlorien: upkeep no-Fellowship ===")
    game = Game()
    p1 = game.add_player("Alice")
    g = _put_on_battlefield(game, p1, "Galadriel, Lady of Lothlorien")

    # Force upkeep trigger.
    game.state.active_player = p1.id
    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'step': 'upkeep',
                 'active_player': p1.id, 'turn_number': 1},
    ))
    new_events = [e for e in game.state.event_log
                  if e.source == g.id
                  and e.type in (EventType.SCRY, EventType.DRAW)]
    scry = [e for e in new_events if e.type == EventType.SCRY]
    draws = [e for e in new_events if e.type == EventType.DRAW]
    assert scry, f"Upkeep should emit SCRY; got {[e.type.name for e in new_events]}"
    assert not draws, f"<3 legendaries: should NOT draw; got {draws}"
    print(f"  SCRY only (no Fellowship): {len(scry)} scry, {len(draws)} draw")


def test_galadriel_upkeep_with_fellowship_draws():
    """With 3+ legendary creatures (incl. self), upkeep draws a card."""
    print("\n=== Galadriel Lothlorien: upkeep w/ Fellowship ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Drop 2 other legendaries (Galadriel will be the 3rd).
    _drop_legendary(game, p1.id, "L1")
    _drop_legendary(game, p1.id, "L2")
    g = _put_on_battlefield(game, p1, "Galadriel, Lady of Lothlorien")

    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'step': 'upkeep',
                 'active_player': p1.id, 'turn_number': 1},
    ))
    g_events = [e for e in game.state.event_log
                if e.source == g.id
                and e.type in (EventType.SCRY, EventType.DRAW)]
    draws = [e for e in g_events if e.type == EventType.DRAW]
    assert draws, f"≥3 legendaries: should DRAW; got {[e.type.name for e in g_events]}"
    print(f"  SCRY + DRAW (Fellowship met)")


# ============================================================================
# Witch-king, Black Captain
# ============================================================================

def test_witch_king_black_captain_loads():
    """Witch-king registers flying, ward {3}, lord, menace grant, damage trigger."""
    print("\n=== Witch-king Black Captain: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    wk = _put_on_battlefield(game, p1, "Witch-king, Black Captain")
    # ≥5 interceptors: flying, ward, P/T boost (2 query), menace, damage trigger.
    assert len(wk.interceptor_ids) >= 5, (
        f"Expected ≥5 interceptors, got {len(wk.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(wk.interceptor_ids)}")


def test_witch_king_buffs_other_wraiths():
    """Witch-king buffs other Wraiths (e.g. Nazgul)."""
    print("\n=== Witch-king: lord effect on Wraiths ===")
    game = Game()
    p1 = game.add_player("Alice")
    wraith = game.create_object(
        name="Black Rider",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wraith"},
            colors={Color.BLACK},
            power=3, toughness=3,
        ),
    )
    _put_on_battlefield(game, p1, "Witch-king, Black Captain")
    pwr = get_power(wraith, game.state)
    assert pwr == 3 + 1, f"Wraith should be +1/+1: 3 → {pwr}"
    print(f"  Wraith pumped to {pwr}/{get_toughness(wraith, game.state)}")


def test_witch_king_combat_damage_discard_and_corrupt():
    """Combat damage to player → discard + corruption counter on a creature."""
    print("\n=== Witch-king: combat damage trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    wk = _put_on_battlefield(game, p1, "Witch-king, Black Captain")

    # Drop an opposing creature so the corruption-counter half has a target.
    enemy = game.create_object(
        name="Foe",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Soldier"},
            power=2, toughness=2,
        ),
    )
    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'source': wk.id, 'target': p2.id, 'amount': 4, 'is_combat': True},
        source=wk.id,
    ))
    after = _emitted_types(game)
    new = after[len(before):]
    assert 'DISCARD' in new, f"DISCARD not emitted: {new}"
    counter_added = [e for e in game.state.event_log
                     if e.type == EventType.COUNTER_ADDED
                     and e.payload.get('counter_type') == 'corruption'
                     and e.source == wk.id]
    assert counter_added, f"Corruption counter not added: {[e.type.name for e in game.state.event_log]}"
    assert counter_added[-1].payload.get('object_id') == enemy.id, (
        f"Corruption should target enemy creature; got {counter_added[-1].payload}"
    )
    print(f"  DISCARD + corruption on {enemy.name}")


def test_witch_king_noncombat_damage_does_not_trigger():
    """Edge: noncombat damage shouldn't trigger Witch-king's discard."""
    print("\n=== Witch-king: noncombat damage edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    wk = _put_on_battlefield(game, p1, "Witch-king, Black Captain")

    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'source': wk.id, 'target': p2.id, 'amount': 4, 'is_combat': False},
        source=wk.id,
    ))
    after = _emitted_types(game)
    new = after[len(before):]
    assert 'DISCARD' not in new, f"DISCARD should not fire on noncombat: {new}"
    print("  Noncombat damage suppressed")


# ============================================================================
# The One Ring (replaced)
# ============================================================================

def test_one_ring_loads_as_legendary_artifact():
    """The One Ring is a Legendary Artifact (Ring/Equipment)."""
    print("\n=== The One Ring: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    ring = _put_on_battlefield(game, p1, "The One Ring")
    chars = ring.characteristics
    assert CardType.ARTIFACT in chars.types
    assert 'Ring' in chars.subtypes
    assert 'Equipment' in chars.subtypes
    assert 'Legendary' in chars.supertypes
    # ≥2 interceptors: ward + upkeep trigger.
    assert len(ring.interceptor_ids) >= 2, (
        f"Expected ≥2 interceptors, got {len(ring.interceptor_ids)}"
    )
    print(f"  Loaded with {len(ring.interceptor_ids)} interceptors")


def test_one_ring_upkeep_escalates():
    """Upkeep: corruption counter + draw (n+1) + lose (n+1) life."""
    print("\n=== The One Ring: escalating upkeep ===")
    game = Game()
    p1 = game.add_player("Alice")
    ring = _put_on_battlefield(game, p1, "The One Ring")

    game.state.active_player = p1.id
    p1_life_before = p1.life
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'step': 'upkeep',
                 'active_player': p1.id, 'turn_number': 1},
    ))
    # First upkeep: 1 counter, draw 1, -1 life.
    counters = ring.state.counters.get('corruption', 0)
    assert counters == 1, f"Expected 1 corruption counter, got {counters}"
    draws = [e for e in game.state.event_log
             if e.type == EventType.DRAW and e.source == ring.id]
    assert draws, "Should draw on first upkeep"
    first_amount = draws[-1].payload.get('amount')
    assert first_amount == 1, f"First draw amount should be 1; got {first_amount}"
    # Life goes down by 1.
    assert p1.life == p1_life_before - 1, (
        f"Should lose 1 life on first upkeep: {p1_life_before} -> {p1.life}"
    )

    # Second upkeep: 2 counters, draw 2, -2 life.
    p1_life_mid = p1.life
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'step': 'upkeep',
                 'active_player': p1.id, 'turn_number': 2},
    ))
    counters2 = ring.state.counters.get('corruption', 0)
    assert counters2 == 2, f"Expected 2 corruption counters, got {counters2}"
    draws2 = [e for e in game.state.event_log
              if e.type == EventType.DRAW and e.source == ring.id]
    last_amount = draws2[-1].payload.get('amount')
    assert last_amount == 2, f"Second draw amount should be 2; got {last_amount}"
    assert p1.life == p1_life_mid - 2, (
        f"Should lose 2 life on second upkeep: {p1_life_mid} -> {p1.life}"
    )
    print(f"  Upkeep 1: -1 life, draw 1; Upkeep 2: -2 life, draw 2 (escalating)")


def test_one_ring_does_not_fire_on_opponent_upkeep():
    """Edge: opponent's upkeep should NOT trigger The One Ring's effect."""
    print("\n=== The One Ring: opponent upkeep edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    ring = _put_on_battlefield(game, p1, "The One Ring")

    # Bob's upkeep.
    game.state.active_player = p2.id
    before = ring.state.counters.get('corruption', 0)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'step': 'upkeep',
                 'active_player': p2.id, 'turn_number': 1},
    ))
    after = ring.state.counters.get('corruption', 0)
    assert after == before, (
        f"Opp upkeep should not trigger: {before} → {after}"
    )
    print(f"  Counter unchanged on opp upkeep: {before} → {after}")


# ============================================================================
# Anduril, Flame of the West (replaced)
# ============================================================================

def test_anduril_loads_with_equipment_subtype():
    """Anduril is an Artifact-Equipment with equip activated ability."""
    print("\n=== Anduril: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    anduril = _put_on_battlefield(game, p1, "Anduril, Flame of the West")
    chars = anduril.characteristics
    assert CardType.ARTIFACT in chars.types
    assert 'Equipment' in chars.subtypes
    assert 'Legendary' in chars.supertypes
    abilities = getattr(anduril.state, 'activated_abilities', [])
    # Equip activated ability.
    assert len(abilities) >= 1, (
        f"Expected equip ability; got {len(abilities)}"
    )
    print(f"  Loaded; equip ability count={len(abilities)}")


def test_anduril_grants_pt_and_keywords_when_attached():
    """When Anduril is attached, equipped creature gains +3/+3 + first strike + vigilance."""
    print("\n=== Anduril: attach grants P/T + keywords ===")
    from src.engine import has_ability
    game = Game()
    p1 = game.add_player("Alice")
    anduril = _put_on_battlefield(game, p1, "Anduril, Flame of the West")
    # Drop a creature, then emit ATTACH.
    creature = game.create_object(
        name="Aragorn Test",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Human"},
            power=2, toughness=2,
        ),
    )
    base_p = get_power(creature, game.state)
    base_t = get_toughness(creature, game.state)
    # ATTACH handler reads payload['object_id'] (the equipment) and
    # payload['target_id'] (the wearer). See src/engine/attach.py.
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': anduril.id, 'target_id': creature.id},
        source=anduril.id,
    ))
    new_p = get_power(creature, game.state)
    new_t = get_toughness(creature, game.state)
    assert new_p == base_p + 3, f"Power: {base_p} → {new_p} (expected +3)"
    assert new_t == base_t + 3, f"Toughness: {base_t} → {new_t} (expected +3)"
    # Granted keywords.
    fs = has_ability(creature, 'first_strike', game.state)
    vg = has_ability(creature, 'vigilance', game.state)
    assert fs, "Equipped creature should have first strike"
    assert vg, "Equipped creature should have vigilance"
    print(f"  P/T {base_p}/{base_t} → {new_p}/{new_t}; first_strike={fs}, vigilance={vg}")


# ============================================================================
# Mithril Coat (replaced)
# ============================================================================

def test_mithril_coat_grants_indestructible_and_toughness():
    """Mithril Coat: equipped creature has indestructible + +0/+2."""
    print("\n=== Mithril Coat: attach grants protection ===")
    from src.engine import has_ability
    game = Game()
    p1 = game.add_player("Alice")
    coat = _put_on_battlefield(game, p1, "Mithril Coat")
    creature = game.create_object(
        name="Frodo Test",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Hobbit"},
            power=1, toughness=1,
        ),
    )
    base_t = get_toughness(creature, game.state)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': coat.id, 'target_id': creature.id},
        source=coat.id,
    ))
    new_t = get_toughness(creature, game.state)
    assert new_t == base_t + 2, f"Toughness should be +2: {base_t} → {new_t}"
    indest = has_ability(creature, 'indestructible', game.state)
    assert indest, "Equipped creature should be indestructible"
    print(f"  Toughness {base_t} → {new_t}; indestructible={indest}")


# ============================================================================
# Lothlorien (replaced)
# ============================================================================

def test_lothlorien_loads_as_legendary_land():
    """Lothlorien is a Legendary Land with two activated abilities."""
    print("\n=== Lothlorien: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    loth = _put_on_battlefield(game, p1, "Lothlorien")
    chars = loth.characteristics
    assert CardType.LAND in chars.types
    assert 'Legendary' in chars.supertypes
    abilities = getattr(loth.state, 'activated_abilities', [])
    assert len(abilities) >= 2, (
        f"Expected ≥2 activated abilities, got {len(abilities)}"
    )
    print(f"  Land+Legendary with {len(abilities)} activated abilities")


def test_lothlorien_scry_ability_does_not_draw_without_fellowship():
    """Lothlorien's scry-or-draw ability emits SCRY only with <3 legendaries."""
    print("\n=== Lothlorien: scry-only no Fellowship ===")
    game = Game()
    p1 = game.add_player("Alice")
    loth = _put_on_battlefield(game, p1, "Lothlorien")

    abilities = loth.state.activated_abilities or []
    scry_ability = next(
        (a for a in abilities if a.cost_text and '{2}' in a.cost_text and '{T}' in a.cost_text),
        None,
    )
    assert scry_ability is not None, f"Scry ability not found: {[a.cost_text for a in abilities]}"
    events = scry_ability.effect_fn(loth, game.state, [])
    scry = [e for e in events if e.type == EventType.SCRY]
    draws = [e for e in events if e.type == EventType.DRAW]
    assert scry, f"Should emit SCRY; got {[e.type.name for e in events]}"
    assert not draws, f"<3 legendaries: should not draw; got {draws}"
    print(f"  SCRY only (count={len(scry)})")


def test_lothlorien_scry_ability_draws_with_fellowship():
    """With 3+ legendary creatures controlled, scry+draw both fire."""
    print("\n=== Lothlorien: scry+draw with Fellowship ===")
    game = Game()
    p1 = game.add_player("Alice")
    loth = _put_on_battlefield(game, p1, "Lothlorien")
    # 3 legendary creatures (Lothlorien is a Legendary land, NOT a creature, so it
    # doesn't count toward the legendary-creature count).
    for i in range(3):
        _drop_legendary(game, p1.id, f"L{i}")

    abilities = loth.state.activated_abilities or []
    scry_ability = next(
        (a for a in abilities if a.cost_text and '{2}' in a.cost_text and '{T}' in a.cost_text),
        None,
    )
    assert scry_ability is not None
    events = scry_ability.effect_fn(loth, game.state, [])
    draws = [e for e in events if e.type == EventType.DRAW]
    assert draws, f"≥3 legendaries: should DRAW; got {[e.type.name for e in events]}"
    print(f"  SCRY + DRAW (Fellowship met)")


def test_lothlorien_mana_ability_emits_green():
    """Lothlorien's {T}: Add {G} ability emits MANA_PRODUCED with green mana."""
    print("\n=== Lothlorien: mana ability ===")
    game = Game()
    p1 = game.add_player("Alice")
    loth = _put_on_battlefield(game, p1, "Lothlorien")

    abilities = loth.state.activated_abilities or []
    mana_ability = next(
        (a for a in abilities if a.cost_text == '{T}'),
        None,
    )
    assert mana_ability is not None, f"Mana ability not found: {[a.cost_text for a in abilities]}"
    events = mana_ability.effect_fn(loth, game.state, [])
    mana = [e for e in events if e.type == EventType.MANA_PRODUCED]
    assert mana, f"Should emit MANA_PRODUCED; got {[e.type.name for e in events]}"
    payload = mana[0].payload
    assert payload.get('mana', {}).get('G') == 1, (
        f"Should produce 1 green mana; got {payload}"
    )
    print(f"  {{T}}: Add {{G}} → {payload.get('mana')}")


# ============================================================================
# Cross-card sanity: registry + CARDS list integrity
# ============================================================================

def test_spice_cards_in_registry():
    """All Phase A spice cards are exported in LORD_OF_THE_RINGS_CARDS."""
    print("\n=== Spice registry ===")
    expected = [
        "Aragorn, King Returned",
        "Gandalf, Mithrandir",
        "Galadriel, Lady of Lothlorien",
        "Witch-king, Black Captain",
        "The One Ring",
        "Anduril, Flame of the West",
        "Mithril Coat",
        "Lothlorien",
    ]
    for name in expected:
        assert name in LORD_OF_THE_RINGS_CARDS, f"{name} missing from registry"
        cd = LORD_OF_THE_RINGS_CARDS[name]
        assert cd is not None, f"{name} maps to None"
    print(f"  All {len(expected)} spice cards present in registry")


def test_spice_cards_no_name_collisions_with_existing_legends():
    """Phase A spice variants do not collide with existing legend names."""
    print("\n=== Spice registry: no collisions ===")
    # The vanilla legends keep their names; the spice picks have differentiated names.
    assert "Aragorn, King of Gondor" in LORD_OF_THE_RINGS_CARDS
    assert "Aragorn, King Returned" in LORD_OF_THE_RINGS_CARDS
    assert "Galadriel, Lady of Light" in LORD_OF_THE_RINGS_CARDS
    assert "Galadriel, Lady of Lothlorien" in LORD_OF_THE_RINGS_CARDS
    assert "Gandalf the Grey" in LORD_OF_THE_RINGS_CARDS
    assert "Gandalf, Mithrandir" in LORD_OF_THE_RINGS_CARDS
    assert "Witch-king of Angmar" in LORD_OF_THE_RINGS_CARDS
    assert "Witch-king, Black Captain" in LORD_OF_THE_RINGS_CARDS
    print("  All four spice legends coexist with their vanilla counterparts")


if __name__ == '__main__':
    # Allow direct execution for quick iteration.
    import inspect
    fns = [
        v for k, v in globals().items()
        if k.startswith('test_') and inspect.isfunction(v)
    ]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS: {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL: {fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR: {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed} / {len(fns)} tests passed")
    sys.exit(0 if failed == 0 else 1)
