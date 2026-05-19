"""
Attack on Titan Spice Pass Tests (Phase A1)

Validates the format-defining cards added in the AOT Phase A1 spice pass.
Phase A1 — within current engine, no new helpers.

Cards covered:
- Berserker Titan (REWIRE — was self_keywords cluster member, now attack-buffs Titans)
- Kenny Ackerman, The Ripper (REWIRE — was self_keywords, now another-death snowball)
- Gabi Braun, Warrior Candidate (REWIRE — was self_keywords, now opp-life-loss grows)
- Falco Grice, Jaw Inheritor (REWIRE — was self_keywords, now attack-reveal-may-exile)
- Levi Ackerman, Captain of the Special Ops Squad (NEW — Scout-tribal build-around)
- Battle of Trost (NEW — 3-chapter saga, WBR)
- Eren's Hardening (NEW — Equipment with granted indestructible activated)
- The Nine Titans Assembled (NEW — Titan-tribal gated mythic)
"""

import os
import sys
# Worktree-portable sys.path: compute repo root from this file's location so
# the test runs from any checkout (main or a `.claude/worktrees/agent-*/`).
# Hardcoding the main-checkout path bit prior parallel-agent worktrees —
# see spice-pass.md gotcha #18.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness,
)
from src.engine.queries import has_ability
from src.cards.custom.attack_on_titan import ATTACK_ON_TITAN_CARDS


def _put_on_battlefield(game, player, card_name):
    """Mirror the spice test harness shape.

    `create_object` runs `setup_interceptors` for BATTLEFIELD/COMMAND zones.
    Putting the card in HAND first with `card_def=None`, then ZONE_CHANGE
    to battlefield, runs setup exactly once via the pipeline."""
    card_def = ATTACK_ON_TITAN_CARDS[card_name]
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
# Berserker Titan (REWIRE)
# ============================================================================

def test_berserker_titan_loads():
    print("\n=== Berserker Titan: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    bt = _put_on_battlefield(game, p1, "Berserker Titan")
    assert bt.zone == ZoneType.BATTLEFIELD
    # self_keywords + attack trigger
    assert len(bt.interceptor_ids) >= 2, (
        f"Expected self_keywords + attack trigger; got {len(bt.interceptor_ids)}"
    )


def test_berserker_titan_attack_buffs_titans():
    """When Berserker attacks, each Titan you control gets +1/+0 + trample EOT."""
    print("\n=== Berserker Titan: attack buffs Titans ===")
    game = Game()
    p1 = game.add_player("Alice")
    bt = _put_on_battlefield(game, p1, "Berserker Titan")
    raging = _put_on_battlefield(game, p1, "Raging Titan")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': bt.id, 'attacker': bt.id, 'controller': p1.id},
        source=bt.id,
    ))
    after_events = game.state.event_log[before:]
    pt_mods = [
        e for e in after_events
        if e.type == EventType.PT_MODIFICATION
        and e.payload.get('object_id') == raging.id
        and e.payload.get('power_mod') == 1
    ]
    grants = [
        e for e in after_events
        if e.type == EventType.GRANT_KEYWORD
        and e.payload.get('object_id') == raging.id
        and e.payload.get('keyword') == 'trample'
    ]
    assert pt_mods, "Expected +1/+0 PT_MODIFICATION on Raging Titan"
    assert grants, "Expected trample GRANT_KEYWORD on Raging Titan"


def test_berserker_titan_non_titan_not_buffed():
    """Non-Titans your control are NOT buffed by Berserker's attack."""
    print("\n=== Berserker Titan: non-Titans skipped ===")
    game = Game()
    p1 = game.add_player("Alice")
    bt = _put_on_battlefield(game, p1, "Berserker Titan")
    scout = _put_on_battlefield(game, p1, "Survey Corps Recruit")  # Scout, NOT Titan

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': bt.id, 'attacker': bt.id, 'controller': p1.id},
        source=bt.id,
    ))
    after_events = game.state.event_log[before:]
    pt_mods = [
        e for e in after_events
        if e.type == EventType.PT_MODIFICATION
        and e.payload.get('object_id') == scout.id
    ]
    assert not pt_mods, f"Scout should NOT be buffed; got {len(pt_mods)}"


# ============================================================================
# Kenny Ackerman, The Ripper (REWIRE)
# ============================================================================

def test_kenny_ackerman_loads():
    print("\n=== Kenny Ackerman: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    kenny = _put_on_battlefield(game, p1, "Kenny Ackerman, The Ripper")
    assert kenny.zone == ZoneType.BATTLEFIELD
    assert len(kenny.interceptor_ids) >= 2


def test_kenny_ackerman_another_death_drains_and_scries():
    """When another creature dies, opps lose 1 life and you scry 1."""
    print("\n=== Kenny Ackerman: another death drains + scries ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Kenny Ackerman, The Ripper")
    victim = _put_on_battlefield(game, p2, "Marleyan Warrior")

    before = len(game.state.event_log)
    # Move victim to graveyard (simulates death).
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': victim.id,
            'from_zone': 'battlefield',
            'to_zone': f'graveyard_{p2.id}',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    after_events = game.state.event_log[before:]
    drains = [
        e for e in after_events
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
    ]
    scries = [
        e for e in after_events
        if e.type == EventType.ACTIVATE
        and e.payload.get('action') == 'scry'
    ]
    assert drains, f"Expected -1 life drain on Bob; got recent={_emitted_types(game)[-10:]}"
    assert scries, "Expected scry placeholder on Kenny's controller"


def test_kenny_ackerman_self_death_does_not_drain():
    """Kenny's OWN death does NOT fire his 'another creature dies' trigger."""
    print("\n=== Kenny Ackerman: own death does NOT fire ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    kenny = _put_on_battlefield(game, p1, "Kenny Ackerman, The Ripper")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': kenny.id,
            'from_zone': 'battlefield',
            'to_zone': f'graveyard_{p1.id}',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    after_events = game.state.event_log[before:]
    drains = [
        e for e in after_events
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
    ]
    assert not drains, "Kenny's own death should NOT fire his another-creature trigger"


# ============================================================================
# Gabi Braun, Warrior Candidate (REWIRE)
# ============================================================================

def test_gabi_braun_loads():
    print("\n=== Gabi Braun: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    gabi = _put_on_battlefield(game, p1, "Gabi Braun, Warrior Candidate")
    assert gabi.zone == ZoneType.BATTLEFIELD
    assert len(gabi.interceptor_ids) >= 2


def test_gabi_braun_grows_on_opp_life_loss():
    """When an opponent loses life, Gabi gets a +1/+1 counter."""
    print("\n=== Gabi Braun: opp life loss -> +1/+1 counter ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    gabi = _put_on_battlefield(game, p1, "Gabi Braun, Warrior Candidate")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p2.id, 'amount': -3, 'source': gabi.id},
    ))
    after_events = game.state.event_log[before:]
    counter_events = [
        e for e in after_events
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == gabi.id
        and e.payload.get('counter_type') == '+1/+1'
    ]
    assert counter_events, f"Expected +1/+1 counter on Gabi after opp life loss"


def test_gabi_braun_own_life_loss_does_not_grow():
    """When YOU lose life, Gabi does NOT grow."""
    print("\n=== Gabi Braun: own life loss -> no counter ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Gabi Braun, Warrior Candidate")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p1.id, 'amount': -3, 'source': None},
    ))
    after_events = game.state.event_log[before:]
    counter_events = [
        e for e in after_events
        if e.type == EventType.COUNTER_ADDED
    ]
    assert not counter_events, "Gabi should NOT grow on own life loss"


def test_gabi_braun_opp_life_gain_does_not_grow():
    """Opponent GAINING life does NOT grow Gabi (only losses)."""
    print("\n=== Gabi Braun: opp life gain -> no counter ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Gabi Braun, Warrior Candidate")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p2.id, 'amount': 2, 'source': None},
    ))
    after_events = game.state.event_log[before:]
    counter_events = [
        e for e in after_events
        if e.type == EventType.COUNTER_ADDED
    ]
    assert not counter_events, "Gabi should NOT grow on opp life gain"


# ============================================================================
# Falco Grice, Jaw Inheritor (REWIRE)
# ============================================================================

def test_falco_grice_loads():
    print("\n=== Falco Grice: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    falco = _put_on_battlefield(game, p1, "Falco Grice, Jaw Inheritor")
    assert falco.zone == ZoneType.BATTLEFIELD
    assert len(falco.interceptor_ids) >= 2


def test_falco_grice_attack_reveals_opp_top():
    """Attack emits a 'falco_dreams' ACTIVATE for each opponent."""
    print("\n=== Falco Grice: attack reveals opp top ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    falco = _put_on_battlefield(game, p1, "Falco Grice, Jaw Inheritor")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': falco.id, 'attacker': falco.id, 'controller': p1.id},
        source=falco.id,
    ))
    after_events = game.state.event_log[before:]
    dreams = [
        e for e in after_events
        if e.type == EventType.ACTIVATE
        and e.payload.get('action') == 'falco_dreams'
        and e.payload.get('opponent') == p2.id
    ]
    assert dreams, "Expected falco_dreams ACTIVATE event after attack"


# ============================================================================
# Levi Ackerman, Captain of the Special Ops Squad (NEW)
# ============================================================================

def test_levi_special_ops_loads():
    print("\n=== Levi Special Ops: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    levi = _put_on_battlefield(game, p1, "Levi Ackerman, Captain of the Special Ops Squad")
    assert levi.zone == ZoneType.BATTLEFIELD
    # self_keywords + attack trigger = >=2
    assert len(levi.interceptor_ids) >= 2
    # Check self-keywords
    assert has_ability(levi, "first_strike", game.state)
    assert has_ability(levi, "haste", game.state)
    assert has_ability(levi, "vigilance", game.state)


def test_levi_special_ops_attack_buffs_scouts():
    """Levi attack: each OTHER Scout gets +2/+0 and double_strike EOT."""
    print("\n=== Levi Special Ops: attack buffs Scouts ===")
    game = Game()
    p1 = game.add_player("Alice")
    levi = _put_on_battlefield(game, p1, "Levi Ackerman, Captain of the Special Ops Squad")
    scout = _put_on_battlefield(game, p1, "Survey Corps Recruit")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': levi.id, 'attacker': levi.id, 'controller': p1.id},
        source=levi.id,
    ))
    after_events = game.state.event_log[before:]
    pumps = [
        e for e in after_events
        if e.type == EventType.PT_MODIFICATION
        and e.payload.get('object_id') == scout.id
        and e.payload.get('power_mod') == 2
    ]
    ds_grants = [
        e for e in after_events
        if e.type == EventType.GRANT_KEYWORD
        and e.payload.get('object_id') == scout.id
        and e.payload.get('keyword') == 'double_strike'
    ]
    assert pumps, "Expected +2/+0 on Scout"
    assert ds_grants, "Expected double_strike on Scout"


def test_levi_special_ops_does_not_self_buff():
    """Levi's attack does NOT pump himself (other-Scout filter)."""
    print("\n=== Levi Special Ops: other-Scout filter ===")
    game = Game()
    p1 = game.add_player("Alice")
    levi = _put_on_battlefield(game, p1, "Levi Ackerman, Captain of the Special Ops Squad")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': levi.id, 'attacker': levi.id, 'controller': p1.id},
        source=levi.id,
    ))
    after_events = game.state.event_log[before:]
    self_pumps = [
        e for e in after_events
        if e.type == EventType.PT_MODIFICATION
        and e.payload.get('object_id') == levi.id
    ]
    assert not self_pumps, "Levi should NOT self-buff"


# ============================================================================
# Battle of Trost (NEW Saga)
# ============================================================================

def test_battle_of_trost_loads():
    """Battle of Trost is a Legendary Saga enchantment with saga interceptors."""
    print("\n=== Battle of Trost: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Battle of Trost")
    assert saga.zone == ZoneType.BATTLEFIELD
    assert "Saga" in saga.characteristics.subtypes
    assert "Legendary" in saga.characteristics.supertypes
    # make_saga_setup registers (>= 3) interceptors: entry trigger, draw trigger,
    # chapter dispatcher
    assert len(saga.interceptor_ids) >= 3, (
        f"Expected saga to register >=3 interceptors; got {len(saga.interceptor_ids)}"
    )


def test_battle_of_trost_chapter_i_debuffs_opp_creatures():
    """Chapter I debuffs each opp creature by -1/-1 EOT."""
    print("\n=== Battle of Trost: chapter I debuffs opp ===")
    from src.cards.custom.attack_on_titan import _trost_chapter_i
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    saga = _put_on_battlefield(game, p1, "Battle of Trost")
    opp_creature = _put_on_battlefield(game, p2, "Marleyan Warrior")

    events = _trost_chapter_i(saga, game.state)
    pt_mods = [
        e for e in events
        if e.type == EventType.PT_MODIFICATION
        and e.payload.get('object_id') == opp_creature.id
        and e.payload.get('power_mod') == -1
        and e.payload.get('toughness_mod') == -1
    ]
    assert pt_mods, "Expected -1/-1 on opp creature"


def test_battle_of_trost_chapter_ii_creates_two_scouts():
    """Chapter II creates two 2/2 Scout tokens with haste."""
    print("\n=== Battle of Trost: chapter II creates 2 Scout tokens ===")
    from src.cards.custom.attack_on_titan import _trost_chapter_ii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Battle of Trost")
    events = _trost_chapter_ii(saga, game.state)
    tokens = [e for e in events if e.type == EventType.CREATE_TOKEN]
    assert len(tokens) == 2, f"Expected 2 token events; got {len(tokens)}"
    spec = tokens[0].payload['token']
    assert spec['power'] == 2 and spec['toughness'] == 2
    assert 'Scout' in spec['subtypes']
    assert 'haste' in spec.get('keywords', [])


def test_battle_of_trost_chapter_iii_buffs_own_creatures():
    """Chapter III gives +1/+1 + trample to own creatures EOT (not the saga itself)."""
    print("\n=== Battle of Trost: chapter III buffs your creatures ===")
    from src.cards.custom.attack_on_titan import _trost_chapter_iii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Battle of Trost")
    ally = _put_on_battlefield(game, p1, "Survey Corps Recruit")
    events = _trost_chapter_iii(saga, game.state)
    pumps = [
        e for e in events
        if e.type == EventType.PT_MODIFICATION
        and e.payload.get('object_id') == ally.id
        and e.payload.get('power_mod') == 1
    ]
    grants = [
        e for e in events
        if e.type == EventType.GRANT_KEYWORD
        and e.payload.get('object_id') == ally.id
        and e.payload.get('keyword') == 'trample'
    ]
    self_pumps = [
        e for e in events
        if e.payload.get('object_id') == saga.id
    ]
    assert pumps, "Expected +1/+1 on ally"
    assert grants, "Expected trample grant on ally"
    assert not self_pumps, "Saga itself should not be in chapter III buff list"


# ============================================================================
# Eren's Hardening (NEW Equipment)
# ============================================================================

def test_erens_hardening_loads():
    print("\n=== Eren's Hardening: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    eh = _put_on_battlefield(game, p1, "Eren's Hardening")
    assert eh.zone == ZoneType.BATTLEFIELD
    assert "Equipment" in eh.characteristics.subtypes
    # Equipment registers PT mod + granted-ability listener
    assert len(eh.interceptor_ids) >= 2
    activated = getattr(eh.state, 'activated_abilities', None)
    assert activated, "Expected equip activated ability on Eren's Hardening"


def test_erens_hardening_pt_mod_on_attach():
    """ATTACH makes equipped creature read +1/+2 via QUERY interceptors."""
    print("\n=== Eren's Hardening: +1/+2 on attach ===")
    game = Game()
    p1 = game.add_player("Alice")
    eh = _put_on_battlefield(game, p1, "Eren's Hardening")
    creature = _put_on_battlefield(game, p1, "Survey Corps Recruit")
    base_p = get_power(creature, game.state)
    base_t = get_toughness(creature, game.state)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': eh.id, 'target_id': creature.id},
        source=eh.id,
    ))
    new_p = get_power(creature, game.state)
    new_t = get_toughness(creature, game.state)
    assert new_p == base_p + 1, f"Expected power +1: {base_p}->{new_p}"
    assert new_t == base_t + 2, f"Expected toughness +2: {base_t}->{new_t}"


def test_erens_hardening_granted_ability_indestructible():
    """The granted activated ability emits GRANT_KEYWORD indestructible
    when activated on the equipped target. We call the effect directly via
    the spec stored on the equipment, mimicking the activation pipeline."""
    print("\n=== Eren's Hardening: granted indestructible activation ===")
    from src.cards.custom.attack_on_titan import _erens_hardening_indestructible_effect
    game = Game()
    p1 = game.add_player("Alice")
    eh = _put_on_battlefield(game, p1, "Eren's Hardening")
    creature = _put_on_battlefield(game, p1, "Survey Corps Recruit")

    # ATTACH so the engine sets _granted_ability_targets.
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': eh.id, 'target_id': creature.id},
        source=eh.id,
    ))
    # The pipeline-emitted GRANT_ACTIVATED_ABILITY marker tells us the engine
    # wired the ability and stored the target pointer. We then invoke the
    # effect_fn directly to assert the GRANT_KEYWORD shape.
    target_id = getattr(eh.state, '_granted_ability_targets', None)
    assert target_id == creature.id, (
        f"Expected _granted_ability_targets={creature.id!r}; got {target_id!r}"
    )
    events = _erens_hardening_indestructible_effect(eh, game.state, [])
    grants = [
        e for e in events
        if e.type == EventType.GRANT_KEYWORD
        and e.payload.get('object_id') == creature.id
        and e.payload.get('keyword') == 'indestructible'
        and e.payload.get('duration') == 'end_of_turn'
    ]
    assert grants, f"Expected indestructible grant on equipped creature; got {events}"


# ============================================================================
# The Nine Titans Assembled (NEW Pattern-11 build-around)
# ============================================================================

def test_nine_titans_assembled_loads():
    print("\n=== Nine Titans Assembled: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    nta = _put_on_battlefield(game, p1, "The Nine Titans Assembled")
    assert nta.zone == ZoneType.BATTLEFIELD
    assert "Titan" in nta.characteristics.subtypes
    assert "Legendary" in nta.characteristics.supertypes
    assert has_ability(nta, "trample", game.state)
    assert has_ability(nta, "indestructible", game.state)


def test_nine_titans_assembled_etb_counters_each_titan():
    """ETB puts a +1/+1 counter on each other Titan you control."""
    print("\n=== Nine Titans Assembled: ETB counters Titans ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Three Titans BEFORE NTA enters
    raging = _put_on_battlefield(game, p1, "Raging Titan")
    bt = _put_on_battlefield(game, p1, "Berserker Titan")
    forest = _put_on_battlefield(game, p1, "Forest Titan")
    nta = _put_on_battlefield(game, p1, "The Nine Titans Assembled")

    # Counters added via NTA's ETB (filtered by source=nta.id)
    nta_counters = [
        e for e in game.state.event_log
        if e.type == EventType.COUNTER_ADDED
        and e.source == nta.id
        and e.payload.get('counter_type') == '+1/+1'
    ]
    counter_targets = {e.payload.get('object_id') for e in nta_counters}
    assert raging.id in counter_targets, "Expected +1/+1 on Raging Titan"
    assert bt.id in counter_targets, "Expected +1/+1 on Berserker Titan"
    assert forest.id in counter_targets, "Expected +1/+1 on Forest Titan"
    # NTA should not self-counter
    assert nta.id not in counter_targets, "NTA should not self-counter"


def test_nine_titans_assembled_threshold_exiles_non_titans():
    """With 5+ Titans (4 others + self), non-Titan opp creatures are exiled."""
    print("\n=== Nine Titans Assembled: 5+ Titans -> exile non-Titans ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Four Titans BEFORE NTA -> 5 total including self
    _put_on_battlefield(game, p1, "Raging Titan")
    _put_on_battlefield(game, p1, "Berserker Titan")
    _put_on_battlefield(game, p1, "Forest Titan")
    _put_on_battlefield(game, p1, "Wall Breaker")
    # Opp non-Titan creature
    enemy = _put_on_battlefield(game, p2, "Marleyan Warrior")
    nta = _put_on_battlefield(game, p1, "The Nine Titans Assembled")

    exile_events = [
        e for e in game.state.event_log
        if e.type == EventType.EXILE
        and e.source == nta.id
        and e.payload.get('target') == enemy.id
    ]
    assert exile_events, (
        f"Expected EXILE event for enemy non-Titan when 5+ Titans assembled"
    )


def test_nine_titans_assembled_below_threshold_no_exile():
    """With <5 Titans, threshold does NOT fire."""
    print("\n=== Nine Titans Assembled: <5 Titans -> no exile ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Three Titans BEFORE NTA -> 4 total including self (below threshold)
    _put_on_battlefield(game, p1, "Raging Titan")
    _put_on_battlefield(game, p1, "Berserker Titan")
    _put_on_battlefield(game, p1, "Forest Titan")
    enemy = _put_on_battlefield(game, p2, "Marleyan Warrior")
    nta = _put_on_battlefield(game, p1, "The Nine Titans Assembled")

    exile_events = [
        e for e in game.state.event_log
        if e.type == EventType.EXILE
        and e.source == nta.id
    ]
    assert not exile_events, f"Expected NO exile below threshold; got {len(exile_events)}"


def test_nine_titans_assembled_threshold_spares_titan_opp_creatures():
    """Threshold exiles non-Titans only; Titan opp creatures are spared."""
    print("\n=== Nine Titans Assembled: threshold spares Titan opp creatures ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # 4 own Titans + self = 5 -> threshold fires
    _put_on_battlefield(game, p1, "Raging Titan")
    _put_on_battlefield(game, p1, "Berserker Titan")
    _put_on_battlefield(game, p1, "Forest Titan")
    _put_on_battlefield(game, p1, "Wall Breaker")
    # Opp Titan and non-Titan
    opp_titan = _put_on_battlefield(game, p2, "Forest Titan")  # Titan subtype
    opp_human = _put_on_battlefield(game, p2, "Marleyan Warrior")
    nta = _put_on_battlefield(game, p1, "The Nine Titans Assembled")

    exile_events = [
        e for e in game.state.event_log
        if e.type == EventType.EXILE
        and e.source == nta.id
    ]
    targets = {e.payload.get('target') for e in exile_events}
    assert opp_human.id in targets, "Expected non-Titan to be exiled"
    assert opp_titan.id not in targets, (
        "Titan opp creature should NOT be exiled by threshold"
    )


# ============================================================================
# Garrison Cannon Battery (Phase A2 slice-1 — divided-damage flip)
# ============================================================================

def test_garrison_cannon_battery_loads():
    """Setup registers the divided-damage ETB-trigger interceptor."""
    print("\n=== Garrison Cannon Battery: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    gcb = _put_on_battlefield(game, p1, "Garrison Cannon Battery")
    assert gcb.zone == ZoneType.BATTLEFIELD
    assert gcb.interceptor_ids, "Expected at least 1 ETB interceptor"


def test_garrison_cannon_battery_etb_emits_divided_damage_target_required():
    """ETB emits TARGET_REQUIRED with divide_amount=4."""
    print("\n=== Garrison Cannon Battery: ETB divide-damage ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    gcb = _put_on_battlefield(game, p1, "Garrison Cannon Battery")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == gcb.id
        and e.payload.get('effect') == 'damage'
    ]
    assert target_reqs, (
        f"Expected damage TARGET_REQUIRED; new={[e.type.name for e in new[-10:]]}"
    )
    payload = target_reqs[0].payload
    assert payload.get('divide_amount') == 4, (
        f"Expected divide_amount=4; got {payload.get('divide_amount')}"
    )
    assert payload.get('max_targets') == 4


# ============================================================================
# Hange's Field Experiment (Phase A2 slice-1 — modal-ETB flip)
# ============================================================================

def test_hange_field_experiment_loads():
    """Setup registers the modal-ETB trigger."""
    print("\n=== Hange's Field Experiment: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    hfe = _put_on_battlefield(game, p1, "Hange's Field Experiment")
    assert hfe.zone == ZoneType.BATTLEFIELD
    assert hfe.interceptor_ids, "Expected modal-ETB trigger interceptor"


def test_hange_field_experiment_etb_sets_pending_modal_choice():
    """ETB sets state.pending_choice with a modal_with_targeting choice."""
    print("\n=== Hange's Field Experiment: ETB pending modal choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    hfe = _put_on_battlefield(game, p1, "Hange's Field Experiment")
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending_choice after ETB"
    assert pc.source_id == hfe.id, (
        f"Expected choice source={hfe.id}; got {pc.source_id}"
    )
    assert pc.choice_type == "modal_with_targeting"
    assert pc.player == p1.id
    assert len(pc.options) == 3, f"Expected 3 modes; got {len(pc.options)}"
    labels = {opt['label'] for opt in pc.options}
    assert 'Scry 3' in labels


# ============================================================================
# Slice-4 thin-bust tests (2026-05-19): twelve previously-vanilla AOT cards
# now carry minimum-viable depth-1 setups. Tests assert each setup wires up
# and fires under its on-flavor trigger.
# ============================================================================


def _put_extra_creature_on_battlefield(game, player, card_name):
    """Spawn a card directly onto the battlefield without the
    create_object → ZONE_CHANGE pipeline (so the trigger under test fires
    off the explicit emit below, not off the spawn)."""
    card_def = ATTACK_ON_TITAN_CARDS[card_name]
    obj = game.create_object(
        name=card_name, owner_id=player.id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=None,
    )
    obj.card_def = card_def
    bf = game.state.zones.get('battlefield')
    if bf and obj.id not in bf.objects:
        bf.objects.append(obj.id)
    return obj


def test_odm_gear_etb_on_creature_gains_life():
    print("\n=== ODM Gear: ETB heal on creature ===")
    game = Game()
    p1 = game.add_player("Alice")
    odm = _put_on_battlefield(game, p1, "ODM Gear")
    assert odm.interceptor_ids
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Survey Corps Recruit")
    new = game.state.event_log[before:]
    gains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p1.id
        and e.payload.get('amount') == 1
    ]
    assert gains, f"Expected +1 life; recent={[e.type.name for e in new[-10:]]}"


def test_advanced_odm_gear_taxes_opp_creature():
    print("\n=== Advanced ODM Gear: opp ETB tax ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Advanced ODM Gear")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p2, "Survey Corps Recruit")
    new = game.state.event_log[before:]
    losses = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
    ]
    assert losses, f"Expected -1 life to opp; recent={[e.type.name for e in new[-10:]]}"


def test_anti_personnel_odm_gear_death_damages_opps():
    print("\n=== Anti-Personnel ODM Gear: death dmg ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Anti-Personnel ODM Gear")
    extra = _put_extra_creature_on_battlefield(game, p1, "Survey Corps Recruit")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': extra.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    new = game.state.event_log[before:]
    dmgs = [
        e for e in new
        if e.type == EventType.DAMAGE
        and e.payload.get('target') == p2.id
        and e.payload.get('amount') == 1
    ]
    assert dmgs, f"Expected 1 dmg to opp on death; recent={[e.type.name for e in new[-10:]]}"


def test_survey_corps_cloak_etb_gains_life():
    print("\n=== Survey Corps Cloak: ETB heal ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Survey Corps Cloak")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Survey Corps Recruit")
    new = game.state.event_log[before:]
    gains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p1.id
        and e.payload.get('amount') == 1
    ]
    assert gains, f"Expected +1 life; recent={[e.type.name for e in new[-10:]]}"


def test_blade_set_death_damages_opps():
    print("\n=== Blade Set: death dmg ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Blade Set")
    extra = _put_extra_creature_on_battlefield(game, p1, "Survey Corps Recruit")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': extra.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    new = game.state.event_log[before:]
    dmgs = [
        e for e in new
        if e.type == EventType.DAMAGE
        and e.payload.get('target') == p2.id
        and e.payload.get('amount') == 1
    ]
    assert dmgs, f"Expected 1 dmg to opp; recent={[e.type.name for e in new[-10:]]}"


def test_gas_canister_damages_opp_creature():
    print("\n=== Gas Canister: damage opp creature ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Gas Canister")
    before = len(game.state.event_log)
    opp_creature = _put_on_battlefield(game, p2, "Survey Corps Recruit")
    new = game.state.event_log[before:]
    dmgs = [
        e for e in new
        if e.type == EventType.DAMAGE
        and e.payload.get('target') == opp_creature.id
        and e.payload.get('amount') == 1
    ]
    assert dmgs, f"Expected 1 dmg to opp creature; recent={[e.type.name for e in new[-10:]]}"


def test_garrison_cannon_taxes_opp():
    print("\n=== Garrison Cannon: opp ETB tax ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Garrison Cannon")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p2, "Survey Corps Recruit")
    new = game.state.event_log[before:]
    losses = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
    ]
    assert losses, f"Expected -1 life to opp; recent={[e.type.name for e in new[-10:]]}"


def test_flare_gun_drains_opps_on_friendly_etb():
    print("\n=== Flare Gun: friendly ETB drains opps ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Flare Gun")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Survey Corps Recruit")
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
    ]
    assert drains, f"Expected -1 life to opp; recent={[e.type.name for e in new[-10:]]}"


def test_founding_titan_serum_death_gains_life():
    print("\n=== Founding Titan Serum: death heal ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Founding Titan Serum")
    extra = _put_extra_creature_on_battlefield(game, p1, "Survey Corps Recruit")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': extra.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    new = game.state.event_log[before:]
    gains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p1.id
        and e.payload.get('amount') == 1
    ]
    assert gains, f"Expected +1 life; recent={[e.type.name for e in new[-10:]]}"


def test_titan_serum_death_drains_opps():
    print("\n=== Titan Serum: death drains opps ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Titan Serum")
    extra = _put_extra_creature_on_battlefield(game, p1, "Survey Corps Recruit")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': extra.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
    ]
    assert drains, f"Expected -1 life to opp; recent={[e.type.name for e in new[-10:]]}"


def test_armored_titan_serum_etb_gains_life():
    print("\n=== Armored Titan Serum: ETB heal ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Armored Titan Serum")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Survey Corps Recruit")
    new = game.state.event_log[before:]
    gains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p1.id
        and e.payload.get('amount') == 1
    ]
    assert gains, f"Expected +1 life; recent={[e.type.name for e in new[-10:]]}"


def test_eldian_woodcutter_grows_on_death():
    print("\n=== Eldian Woodcutter: grows on death ===")
    game = Game()
    p1 = game.add_player("Alice")
    cutter = _put_on_battlefield(game, p1, "Eldian Woodcutter")
    extra = _put_extra_creature_on_battlefield(game, p1, "Survey Corps Recruit")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': extra.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    new = game.state.event_log[before:]
    counters = [
        e for e in new
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == cutter.id
        and e.payload.get('counter_type') == '+1/+1'
    ]
    assert counters, f"Expected +1/+1 on Woodcutter; recent={[e.type.name for e in new[-10:]]}"


# ============================================================================
# Slice-19 median-lift tests: scry/drain/mill/discard pattern verification.
# Each test puts a buffed card on the battlefield and asserts the expected
# cross-controller event (LIFE_CHANGE / DAMAGE / MILL / DISCARD / REVEAL_HAND)
# plus the SCRY or SURVEIL info event fires.
# ============================================================================


def _emit_etb_and_collect(game, p1, p2, card_name):
    """Place card under p1, return new events after entry."""
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, card_name)
    return game.state.event_log[before:]


def _assert_scry_and_opp_loss(events, p2_id, expect_amount_min=1):
    scries = [e for e in events if e.type == EventType.SCRY]
    drains = [e for e in events if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2_id and e.payload.get('amount') < 0]
    assert scries, f"Expected SCRY; got {[e.type.name for e in events[-10:]]}"
    assert drains, f"Expected life-loss on opp; got {[e.type.name for e in events[-10:]]}"


def _assert_surveil_and_opp_mill(events, p2_id):
    surveils = [e for e in events if e.type == EventType.SURVEIL]
    mills = [e for e in events if e.type == EventType.MILL
             and e.payload.get('player') == p2_id]
    assert surveils, f"Expected SURVEIL; got {[e.type.name for e in events[-10:]]}"
    assert mills, f"Expected mill on opp; got {[e.type.name for e in events[-10:]]}"


# --- SHAPE 1: ETB scry + drain (Survey Corps, Garrison) -------------------


def test_aot_s19_sasha_blouse():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Sasha Blouse, Hunter")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_erwin_smith_commander():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Erwin Smith, Commander")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_connie_springer():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Connie Springer, Loyal Friend")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_petra_ral():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Petra Ral, Levi Squad")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_oluo_bozado():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Oluo Bozado, Levi Squad")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_survey_corps_veteran():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Survey Corps Veteran")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_military_police_officer():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Military Police Officer")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_squad_captain():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Squad Captain")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_horse_mounted_scout():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Horse Mounted Scout")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_wall_garrison_elite():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Wall Garrison Elite")
    _assert_scry_and_opp_loss(events, p2.id)


# --- SHAPE 2: Attack drain (Titan, Warrior combat) -------------------------


def _emit_attack_and_collect(game, p1, attacker):
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': attacker.id, 'attacker': attacker.id, 'controller': p1.id},
        source=attacker.id,
    ))
    return game.state.event_log[before:]


def test_aot_s19_jaw_titan_attack():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    jaw = _put_on_battlefield(game, p1, "Jaw Titan")
    events = _emit_attack_and_collect(game, p1, jaw)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_wall_breaker_attack():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    wb = _put_on_battlefield(game, p1, "Wall Breaker")
    events = _emit_attack_and_collect(game, p1, wb)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_attack_titan_acolyte_attack():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    aa = _put_on_battlefield(game, p1, "Attack Titan Acolyte")
    events = _emit_attack_and_collect(game, p1, aa)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_yeagerist_soldier_attack():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    ys = _put_on_battlefield(game, p1, "Yeagerist Soldier")
    events = _emit_attack_and_collect(game, p1, ys)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_louise_attack():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    lou = _put_on_battlefield(game, p1, "Louise, Yeagerist Devotee")
    events = _emit_attack_and_collect(game, p1, lou)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_porco_galliard_attack():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    porco = _put_on_battlefield(game, p1, "Porco Galliard, Jaw Titan")
    events = _emit_attack_and_collect(game, p1, porco)
    _assert_scry_and_opp_loss(events, p2.id)


# --- SHAPE 3: ETB surveil + mill (Marleyan spies, intel) ------------------


def test_aot_s19_marleyan_spy():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Marleyan Spy")
    _assert_surveil_and_opp_mill(events, p2.id)


def test_aot_s19_marleyan_warrior():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Marleyan Warrior")
    _assert_surveil_and_opp_mill(events, p2.id)


def test_aot_s19_marleyan_officer():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Marleyan Officer")
    _assert_surveil_and_opp_mill(events, p2.id)


def test_aot_s19_infiltrator():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Infiltrator")
    _assert_surveil_and_opp_mill(events, p2.id)


def test_aot_s19_intelligence_officer():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Intelligence Officer")
    _assert_surveil_and_opp_mill(events, p2.id)


def test_aot_s19_signal_corps_operator():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Signal Corps Operator")
    _assert_surveil_and_opp_mill(events, p2.id)


def test_aot_s19_survey_cartographer():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Survey Cartographer")
    _assert_surveil_and_opp_mill(events, p2.id)


def test_aot_s19_coastal_scout():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Coastal Scout")
    _assert_surveil_and_opp_mill(events, p2.id)


def test_aot_s19_formation_analyst():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Formation Analyst")
    _assert_surveil_and_opp_mill(events, p2.id)


def test_aot_s19_military_tactician():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Military Tactician")
    _assert_surveil_and_opp_mill(events, p2.id)


# --- SHAPE 4: ETB scry + heal (medics, lifegain) --------------------------


def test_aot_s19_eldian_refugee():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Eldian Refugee")
    scries = [e for e in events if e.type == EventType.SCRY]
    gains = [e for e in events if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount') > 0]
    assert scries
    assert gains


def test_aot_s19_paradis_farmer():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Paradis Farmer")
    scries = [e for e in events if e.type == EventType.SCRY]
    gains = [e for e in events if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount') > 0]
    assert scries
    assert gains


def test_aot_s19_kaya():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Kaya, Sasha's Friend")
    scries = [e for e in events if e.type == EventType.SCRY]
    gains = [e for e in events if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount') > 0]
    assert scries
    assert gains


def test_aot_s19_shiganshina_citizen():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Shiganshina Citizen")
    scries = [e for e in events if e.type == EventType.SCRY]
    gains = [e for e in events if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount') > 0]
    assert scries
    assert gains


# --- SHAPE 5: ETB surveil + discard (mind-games) --------------------------


def test_aot_s19_pieck_finger():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Pieck Finger, Cart Titan")
    surveils = [e for e in events if e.type == EventType.SURVEIL]
    discards = [e for e in events if e.type == EventType.DISCARD
                and e.payload.get('player') == p2.id]
    assert surveils
    assert discards


def test_aot_s19_eldian_internment_guard():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Eldian Internment Guard")
    surveils = [e for e in events if e.type == EventType.SURVEIL]
    discards = [e for e in events if e.type == EventType.DISCARD
                and e.payload.get('player') == p2.id]
    assert surveils
    assert discards


def test_aot_s19_yelena():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Yelena, True Believer")
    surveils = [e for e in events if e.type == EventType.SURVEIL]
    discards = [e for e in events if e.type == EventType.DISCARD
                and e.payload.get('player') == p2.id]
    assert surveils
    assert discards


def test_aot_s19_onyankopon():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Onyankopon, Anti-Marleyan")
    surveils = [e for e in events if e.type == EventType.SURVEIL]
    discards = [e for e in events if e.type == EventType.DISCARD
                and e.payload.get('player') == p2.id]
    assert surveils
    assert discards


def test_aot_s19_interior_police():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Interior Police")
    surveils = [e for e in events if e.type == EventType.SURVEIL]
    discards = [e for e in events if e.type == EventType.DISCARD
                and e.payload.get('player') == p2.id]
    assert surveils
    assert discards


# --- SHAPE 6: ETB scry + damage (thunder-spear, Titan strikes) ------------


def test_aot_s19_reiner_braun():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Reiner Braun, Armored Titan")
    scries = [e for e in events if e.type == EventType.SCRY]
    dmg = [e for e in events if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id]
    assert scries
    assert dmg


def test_aot_s19_pure_titan():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Pure Titan")
    scries = [e for e in events if e.type == EventType.SCRY]
    dmg = [e for e in events if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id]
    assert scries
    assert dmg


def test_aot_s19_abnormal_titan():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Abnormal Titan")
    scries = [e for e in events if e.type == EventType.SCRY]
    dmg = [e for e in events if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id]
    assert scries
    assert dmg


def test_aot_s19_mindless_titan():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Mindless Titan")
    scries = [e for e in events if e.type == EventType.SCRY]
    dmg = [e for e in events if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id]
    assert scries
    assert dmg


def test_aot_s19_small_titan():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Small Titan")
    scries = [e for e in events if e.type == EventType.SCRY]
    dmg = [e for e in events if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id]
    assert scries
    assert dmg


def test_aot_s19_titan_horde():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Titan Horde")
    scries = [e for e in events if e.type == EventType.SCRY]
    dmg = [e for e in events if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id]
    assert scries
    assert dmg


def test_aot_s19_crawling_titan_etb():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Crawling Titan")
    scries = [e for e in events if e.type == EventType.SCRY]
    dmg = [e for e in events if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id]
    assert scries
    assert dmg


def test_aot_s19_forest_titan_etb():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Forest Titan")
    scries = [e for e in events if e.type == EventType.SCRY]
    dmg = [e for e in events if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id]
    assert scries
    assert dmg


def test_aot_s19_towering_titan_etb():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Towering Titan")
    scries = [e for e in events if e.type == EventType.SCRY]
    dmg = [e for e in events if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id]
    assert scries
    assert dmg


def test_aot_s19_primordial_titan_etb():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Primordial Titan")
    scries = [e for e in events if e.type == EventType.SCRY]
    dmg = [e for e in events if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id]
    assert scries
    assert dmg


# --- SHAPE 7: Death drain (Titan deaths) ----------------------------------


def _emit_death_and_collect(game, p1, victim, victim_owner):
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': victim.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{victim_owner.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    return game.state.event_log[before:]


def test_aot_s19_titan_inheritor_death():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    ti = _put_on_battlefield(game, p1, "Titan Inheritor")
    events = _emit_death_and_collect(game, p1, ti, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_marcel_galliard_death():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    mg = _put_on_battlefield(game, p1, "Marcel Galliard, Fallen Warrior")
    events = _emit_death_and_collect(game, p1, mg, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_ymir_original_death():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    ymir = _put_on_battlefield(game, p1, "Ymir, Original Titan")
    events = _emit_death_and_collect(game, p1, ymir, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_eren_kruger_death():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    ek = _put_on_battlefield(game, p1, "Eren Kruger, The Owl")
    events = _emit_death_and_collect(game, p1, ek, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_willy_tybur_death():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    wt = _put_on_battlefield(game, p1, "Willy Tybur, Declaration of War")
    events = _emit_death_and_collect(game, p1, wt, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_ilse_langnar_death():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    il = _put_on_battlefield(game, p1, "Ilse Langnar, Titan Chronicler")
    events = _emit_death_and_collect(game, p1, il, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_training_corps_cadet_death():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    tcc = _put_on_battlefield(game, p1, "Training Corps Cadet")
    events = _emit_death_and_collect(game, p1, tcc, p1)
    _assert_scry_and_opp_loss(events, p2.id)


# --- SHAPE 8: ETB hand-reveal ---------------------------------------------


def test_aot_s19_erwin_smith_gambit():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Erwin Smith, The Gambit")
    scries = [e for e in events if e.type == EventType.SCRY]
    reveals = [e for e in events if e.type == EventType.REVEAL_HAND
               and e.payload.get('player') == p2.id]
    assert scries
    assert reveals


def test_aot_s19_supply_corps_quartermaster():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Supply Corps Quartermaster")
    scries = [e for e in events if e.type == EventType.SCRY]
    reveals = [e for e in events if e.type == EventType.REVEAL_HAND
               and e.payload.get('player') == p2.id]
    assert scries
    assert reveals


def test_aot_s19_wall_architect():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Wall Architect")
    scries = [e for e in events if e.type == EventType.SCRY]
    reveals = [e for e in events if e.type == EventType.REVEAL_HAND
               and e.payload.get('player') == p2.id]
    assert scries
    assert reveals


def test_aot_s19_colt_grice():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Colt Grice, Beast Candidate")
    scries = [e for e in events if e.type == EventType.SCRY]
    reveals = [e for e in events if e.type == EventType.REVEAL_HAND
               and e.payload.get('player') == p2.id]
    assert scries
    assert reveals


# --- SHAPE 9: ETB graveyard + draw ----------------------------------------


def test_aot_s19_armin_arlert_tactician():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Armin Arlert, Tactician")
    scries = [e for e in events if e.type == EventType.SCRY]
    draws = [e for e in events if e.type == EventType.DRAW
             and e.payload.get('player') == p1.id]
    assert scries
    assert draws


# --- SHAPE 10: ETB gain + ally scaling (Wall, Eldian) ---------------------


def test_aot_s19_wall_defender():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Wall Defender")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_wall_cultist():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Wall Cultist")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_forest_dweller():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Forest Dweller")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_titan_hunter():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Titan Hunter")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_forest_scout():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Forest Scout")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_wild_horse():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Wild Horse")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_darius_zackly():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Darius Zackly, Premier")
    _assert_scry_and_opp_loss(events, p2.id)


# --- Artifacts ETB ---


def test_aot_s19_supply_cache():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Supply Cache")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_signal_flare():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Signal Flare")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_war_hammer_construct():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "War Hammer Construct")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_the_coordinate():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "The Coordinate")
    scries = [e for e in events if e.type == EventType.SCRY]
    dmg = [e for e in events if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id]
    assert scries
    assert dmg


def test_aot_s19_basement_key():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Basement Key")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_grishas_journal():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Grisha's Journal")
    scries = [e for e in events if e.type == EventType.SCRY]
    mills = [e for e in events if e.type == EventType.MILL
             and e.payload.get('player') == p2.id]
    assert scries
    assert mills


def test_aot_s19_eldian_armband():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Eldian Armband")
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_attack_titans_memories():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _emit_etb_and_collect(game, p1, p2, "Attack Titan's Memories")
    scries = [e for e in events if e.type == EventType.SCRY]
    mills = [e for e in events if e.type == EventType.MILL
             and e.payload.get('player') == p2.id]
    assert scries
    assert mills


# --- SHAPE 11: Upkeep scry + drain (lands, enchantments) ------------------


def _trigger_upkeep_and_collect(game, p1):
    """Emit a PHASE_START event for p1's upkeep, return new events."""
    # active_player must be p1 for controller_only=True to fire.
    game.state.active_player = p1.id
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'player': p1.id},
    ))
    return game.state.event_log[before:]


def test_aot_s19_strategic_planning_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Strategic Planning")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_wall_maria_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Wall Maria")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_wall_rose_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Wall Rose")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_wall_sheena_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Wall Sheena")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_shiganshina_district_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Shiganshina District")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_trost_district_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Trost District")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_stohess_district_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Stohess District")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_surveil_and_opp_mill(events, p2.id)


def test_aot_s19_survey_corps_hq_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Survey Corps Headquarters")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_garrison_hq_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Garrison Headquarters")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_mp_hq_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Military Police Headquarters")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_surveil_and_opp_mill(events, p2.id)


def test_aot_s19_paradis_island_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Paradis Island")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_marley_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Marley")
    events = _trigger_upkeep_and_collect(game, p1)
    surveils = [e for e in events if e.type == EventType.SURVEIL]
    drains = [e for e in events if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.payload.get('amount') < 0]
    assert surveils
    assert drains


def test_aot_s19_liberio_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Liberio Internment Zone")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_surveil_and_opp_mill(events, p2.id)


def test_aot_s19_forest_of_giant_trees_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Forest of Giant Trees")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_utgard_castle_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Utgard Castle")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_reiss_chapel_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Reiss Chapel")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_paths_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "The Paths")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_the_ocean_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "The Ocean")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_orvud_district_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Orvud District")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_scry_and_opp_loss(events, p2.id)


def test_aot_s19_karanes_district_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Karanes District")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_surveil_and_opp_mill(events, p2.id)


def test_aot_s19_ragako_village_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Ragako Village")
    events = _trigger_upkeep_and_collect(game, p1)
    surveils = [e for e in events if e.type == EventType.SURVEIL]
    drains = [e for e in events if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.payload.get('amount') < 0]
    assert surveils
    assert drains


def test_aot_s19_underground_city_upkeep():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Underground City")
    events = _trigger_upkeep_and_collect(game, p1)
    _assert_surveil_and_opp_mill(events, p2.id)


# --- SHAPE 12: Resolve handlers (instants/sorceries) ----------------------


def _resolve_card(game, p1, card_name):
    """Call card.resolve directly (simulates cast resolution)."""
    card_def = ATTACK_ON_TITAN_CARDS[card_name]
    game.state.active_player = p1.id
    if card_def.resolve is None:
        return []
    events = card_def.resolve([], game.state)
    for e in events:
        game.emit(e)
    return events


def test_aot_s19_resolve_devoted_heart():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _resolve_card(game, p1, "Devoted Heart")
    scries = [e for e in events if e.type == EventType.SCRY]
    gains = [e for e in events if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount') > 0]
    assert scries
    assert gains


def test_aot_s19_resolve_survey_corps_charge():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _resolve_card(game, p1, "Survey Corps Charge")
    scries = [e for e in events if e.type == EventType.SCRY]
    dmg = [e for e in events if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id]
    assert scries
    assert dmg


def test_aot_s19_resolve_humanitys_hope():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _resolve_card(game, p1, "Humanity's Hope")
    scries = [e for e in events if e.type == EventType.SCRY]
    assert scries


def test_aot_s19_resolve_strategic_analysis():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _resolve_card(game, p1, "Strategic Analysis")
    scries = [e for e in events if e.type == EventType.SCRY]
    draws = [e for e in events if e.type == EventType.DRAW
             and e.payload.get('player') == p1.id]
    assert scries
    assert draws


def test_aot_s19_resolve_memory_wipe():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _resolve_card(game, p1, "Memory Wipe")
    surveils = [e for e in events if e.type == EventType.SURVEIL]
    mills = [e for e in events if e.type == EventType.MILL
             and e.payload.get('player') == p2.id]
    assert surveils
    assert mills


def test_aot_s19_resolve_betrayal():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _resolve_card(game, p1, "Betrayal")
    surveils = [e for e in events if e.type == EventType.SURVEIL]
    drains = [e for e in events if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.payload.get('amount') < 0]
    assert surveils
    assert drains


def test_aot_s19_resolve_titans_hunger():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _resolve_card(game, p1, "Titan's Hunger")
    surveils = [e for e in events if e.type == EventType.SURVEIL]
    drains = [e for e in events if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.payload.get('amount') < 0]
    assert surveils
    assert drains


def test_aot_s19_resolve_thunder_spear():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _resolve_card(game, p1, "Thunder Spear Strike")
    scries = [e for e in events if e.type == EventType.SCRY]
    dmg = [e for e in events if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id]
    assert scries
    assert dmg


def test_aot_s19_resolve_the_rumbling():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _resolve_card(game, p1, "The Rumbling")
    scries = [e for e in events if e.type == EventType.SCRY]
    dmg = [e for e in events if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id]
    assert scries
    assert dmg


def test_aot_s19_resolve_titans_growth():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _resolve_card(game, p1, "Titan's Growth")
    scries = [e for e in events if e.type == EventType.SCRY]
    gains = [e for e in events if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount') > 0]
    assert scries
    assert gains


def test_aot_s19_resolve_natural_regeneration():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _resolve_card(game, p1, "Natural Regeneration")
    scries = [e for e in events if e.type == EventType.SCRY]
    gains = [e for e in events if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount') > 0]
    assert scries
    assert gains


def test_aot_s19_resolve_survey_mission():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _resolve_card(game, p1, "Survey Mission")
    scries = [e for e in events if e.type == EventType.SCRY]
    draws = [e for e in events if e.type == EventType.DRAW
             and e.payload.get('player') == p1.id]
    assert scries
    assert draws


def test_aot_s19_resolve_titanization():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _resolve_card(game, p1, "Titanization")
    surveils = [e for e in events if e.type == EventType.SURVEIL]
    drains = [e for e in events if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.payload.get('amount') < 0]
    assert surveils
    assert drains


def test_aot_s19_resolve_eldian_purge():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _resolve_card(game, p1, "Eldian Purge")
    surveils = [e for e in events if e.type == EventType.SURVEIL]
    drains = [e for e in events if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.payload.get('amount') < 0]
    assert surveils
    assert drains


def test_aot_s19_resolve_information_gathering():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _resolve_card(game, p1, "Information Gathering")
    surveils = [e for e in events if e.type == EventType.SURVEIL]
    reveals = [e for e in events if e.type == EventType.REVEAL_HAND
               and e.payload.get('player') == p2.id]
    assert surveils
    assert reveals


def test_aot_s19_resolve_declaration_of_war():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _resolve_card(game, p1, "Declaration of War")
    scries = [e for e in events if e.type == EventType.SCRY]
    dmg = [e for e in events if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id]
    assert scries
    assert dmg


def test_aot_s19_resolve_wall_titan_army():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _resolve_card(game, p1, "Wall Titan Army")
    scries = [e for e in events if e.type == EventType.SCRY]
    drains = [e for e in events if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.payload.get('amount') < 0]
    assert scries
    assert drains


# ============================================================================
# Runner — module-direct so tests work without pytest config
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
