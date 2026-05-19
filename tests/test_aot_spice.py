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
