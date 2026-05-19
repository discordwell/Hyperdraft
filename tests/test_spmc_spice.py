"""
Spider-Man Custom Spice Pass Tests (Phase A1)

Validates the format-defining cards added in the W22+ SPMC spice pass.
Phase A1 — within current engine, no new helpers.

Cards covered:
- Hydro-Man (REWIRE — was unwired vanilla Sinister legendary)
- Chameleon (REWIRE — was unwired vanilla Sinister legendary)
- Doc Ock, Supreme Master (NEW mythic, per-opp upkeep drain/discard)
- Venom, Symbiote King (NEW mythic, ETB discard 2 + sacrifice)
- Carnage, Unleashed (NEW mythic, opp-life-loss snowball + drain)
- The Sinister Six Gathers (NEW saga, Villain assembly)
- Iron Spider Armor (NEW equipment)
- Miles Morales, Ultimate Spider-Man (NEW mythic, attack trigger)
"""

import os
import sys
# Compute repo root from this file's location so the test runs from any
# checkout (main or a `.claude/worktrees/agent-*/` worktree). Per
# spice-pass.md gotcha #18, never hardcode the main-checkout path.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness,
)
from src.engine.queries import has_ability
from src.cards.custom.man_of_pider import SPIDER_MAN_CUSTOM_CARDS
from src.cards.custom import man_of_pider as spmc_module


def _put_on_battlefield(game, player, card_name):
    """Mirror the ZLD/SW spice test harness shape.

    `create_object` runs `setup_interceptors` for BATTLEFIELD/COMMAND zones.
    Putting the card in HAND first with `card_def=None`, then ZONE_CHANGE to
    battlefield, runs setup exactly once via the pipeline (the correct path).
    """
    card_def = SPIDER_MAN_CUSTOM_CARDS[card_name]
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
# Hydro-Man (REWIRE)
# ============================================================================

def test_hydro_man_loads():
    print("\n=== Hydro-Man: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    h = _put_on_battlefield(game, p1, "Hydro-Man")
    assert h.zone == ZoneType.BATTLEFIELD
    assert h.interceptor_ids, "Hydro-Man should register an attack trigger"


def test_hydro_man_attack_mills_each_opponent():
    """Attack trigger emits MILL for each opponent."""
    print("\n=== Hydro-Man: attack mills ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    hydro = _put_on_battlefield(game, p1, "Hydro-Man")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': hydro.id, 'attacker': hydro.id, 'controller': p1.id},
        source=hydro.id,
    ))
    new = game.state.event_log[before:]
    mills = [
        e for e in new
        if e.type == EventType.MILL
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == 2
    ]
    assert mills, f"Expected MILL on opponent; got {_emitted_types(game)[-10:]}"


def test_hydro_man_attack_drains_per_creature_in_gy():
    """Drain to opponent scales with creatures in their graveyard."""
    print("\n=== Hydro-Man: graveyard drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    hydro = _put_on_battlefield(game, p1, "Hydro-Man")

    # Plant a creature card in p2's graveyard.
    sinner_def = SPIDER_MAN_CUSTOM_CARDS["Hammerhead"]
    gy = game.state.zones[f'graveyard_{p2.id}']
    for _ in range(3):
        obj = game.create_object(
            name="Hammerhead",
            owner_id=p2.id,
            zone=ZoneType.GRAVEYARD,
            characteristics=sinner_def.characteristics,
            card_def=None,
        )
        obj.card_def = sinner_def
        if obj.id not in gy.objects:
            gy.objects.append(obj.id)

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': hydro.id, 'attacker': hydro.id, 'controller': p1.id},
        source=hydro.id,
    ))
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount', 0) < 0
    ]
    # Expect -3 (3 creature cards in gy).
    assert drains, f"Expected drain; got {_emitted_types(game)[-10:]}"
    assert drains[-1].payload.get('amount') == -3, (
        f"Expected -3 drain (3 creatures in opp gy), got {drains[-1].payload.get('amount')}"
    )


def test_hydro_man_attack_no_drain_with_empty_gy():
    """Edge: empty opp graveyard => no LIFE_CHANGE event for that opp."""
    print("\n=== Hydro-Man: empty gy edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    hydro = _put_on_battlefield(game, p1, "Hydro-Man")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': hydro.id, 'attacker': hydro.id, 'controller': p1.id},
        source=hydro.id,
    ))
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount', 0) < 0
        and e.source == hydro.id
    ]
    assert not drains, f"Expected no drain with empty gy; got {drains}"


# ============================================================================
# Chameleon (REWIRE)
# ============================================================================

def test_chameleon_loads():
    print("\n=== Chameleon: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    cham = _put_on_battlefield(game, p1, "Chameleon")
    assert cham.zone == ZoneType.BATTLEFIELD
    assert cham.interceptor_ids, "Chameleon should register an upkeep trigger"


def test_chameleon_upkeep_emits_reveal_top():
    """Own upkeep emits REVEAL_TOP for each opponent."""
    print("\n=== Chameleon: upkeep reveal ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Chameleon")

    # gotcha #8: upkeep filter checks state.active_player.
    game.state.active_player = p1.id
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    reveals = [
        e for e in new
        if e.type == EventType.REVEAL_TOP
        and e.payload.get('player') == p2.id
    ]
    assert reveals, f"Expected REVEAL_TOP for opponent; got {_emitted_types(game)[-10:]}"


def test_chameleon_creature_on_top_triggers_draw_and_discard():
    """If a creature is on top of opp library, you draw and they discard."""
    print("\n=== Chameleon: creature-on-top draw/discard ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Chameleon")

    # Stack a creature on top of p2's library.
    sinner_def = SPIDER_MAN_CUSTOM_CARDS["Hammerhead"]
    lib = game.state.zones[f'library_{p2.id}']
    obj = game.create_object(
        name="Hammerhead",
        owner_id=p2.id,
        zone=ZoneType.LIBRARY,
        characteristics=sinner_def.characteristics,
        card_def=None,
    )
    obj.card_def = sinner_def
    if obj.id not in lib.objects:
        lib.objects.append(obj.id)  # top is end of list (per ZLD test convention)

    game.state.active_player = p1.id
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    draws = [e for e in new
             if e.type == EventType.DRAW and e.payload.get('player') == p1.id]
    discards = [e for e in new
                if e.type == EventType.DISCARD and e.payload.get('player') == p2.id]
    assert draws, f"Expected DRAW on creature-on-top; got {_emitted_types(game)[-10:]}"
    assert discards, f"Expected opp DISCARD; got {_emitted_types(game)[-10:]}"


def test_chameleon_opp_upkeep_does_not_fire():
    """Edge: opponent upkeep does not trigger Chameleon."""
    print("\n=== Chameleon: opp upkeep no fire ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Chameleon")

    game.state.active_player = p2.id
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p2.id},
    ))
    new = game.state.event_log[before:]
    reveals = [
        e for e in new
        if e.type == EventType.REVEAL_TOP
        and e.payload.get('player') == p2.id
    ]
    assert not reveals, "Chameleon should not fire on opp upkeep"


# ============================================================================
# Doc Ock, Supreme Master
# ============================================================================

def test_doc_ock_supreme_loads():
    print("\n=== Doc Ock, Supreme Master: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    doc = _put_on_battlefield(game, p1, "Doc Ock, Supreme Master")
    assert doc.zone == ZoneType.BATTLEFIELD
    assert doc.interceptor_ids


def test_doc_ock_supreme_opp_upkeep_with_hand_discards():
    """Opp's upkeep with cards in hand emits DISCARD."""
    print("\n=== Doc Ock: opp upkeep discards ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Doc Ock, Supreme Master")

    # Give p2 a card in hand.
    sinner_def = SPIDER_MAN_CUSTOM_CARDS["Hammerhead"]
    hand = game.state.zones[f'hand_{p2.id}']
    obj = game.create_object(
        name="Hammerhead", owner_id=p2.id, zone=ZoneType.HAND,
        characteristics=sinner_def.characteristics, card_def=None,
    )
    obj.card_def = sinner_def
    if obj.id not in hand.objects:
        hand.objects.append(obj.id)

    game.state.active_player = p2.id
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p2.id},
    ))
    new = game.state.event_log[before:]
    discards = [
        e for e in new
        if e.type == EventType.DISCARD
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == 1
    ]
    assert discards, f"Expected DISCARD for opp; got {_emitted_types(game)[-10:]}"


def test_doc_ock_supreme_opp_upkeep_empty_hand_drains():
    """Opp's upkeep with empty hand emits -2 LIFE_CHANGE (not DISCARD)."""
    print("\n=== Doc Ock: opp upkeep empty hand drains ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Doc Ock, Supreme Master")
    # p2's hand is empty by default.
    game.state.active_player = p2.id
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p2.id},
    ))
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -2
    ]
    assert drains, f"Expected -2 drain on empty-hand opp; got {_emitted_types(game)[-10:]}"


def test_doc_ock_supreme_own_upkeep_no_fire():
    """Edge: controller's own upkeep does not punish self."""
    print("\n=== Doc Ock: own upkeep no fire ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Doc Ock, Supreme Master")

    game.state.active_player = p1.id
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    # Should not target p1 with DISCARD/LIFE_CHANGE
    bad = [
        e for e in new
        if e.payload.get('player') == p1.id
        and e.type in (EventType.DISCARD, EventType.LIFE_CHANGE)
        and e.payload.get('amount', 0) < 0
    ]
    assert not bad, f"Doc Ock punished its own controller: {[e.type.name for e in bad]}"


# ============================================================================
# Venom, Symbiote King
# ============================================================================

def test_venom_symbiote_king_loads():
    print("\n=== Venom, Symbiote King: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    v = _put_on_battlefield(game, p1, "Venom, Symbiote King")
    assert v.zone == ZoneType.BATTLEFIELD
    assert v.interceptor_ids


def test_venom_symbiote_king_etb_discards_two_and_demands_sac():
    """ETB emits DISCARD 2 + SACRIFICE_REQUIRED to each opponent."""
    print("\n=== Venom King: ETB pain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Venom, Symbiote King")
    new = game.state.event_log[before:]
    discards = [
        e for e in new
        if e.type == EventType.DISCARD
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == 2
    ]
    sacs = [
        e for e in new
        if e.type == EventType.SACRIFICE_REQUIRED
        and e.payload.get('player') == p2.id
        and e.payload.get('card_type') == 'creature'
    ]
    assert discards, f"Expected DISCARD 2 to opp; got {_emitted_types(game)[-15:]}"
    assert sacs, f"Expected SACRIFICE_REQUIRED to opp; got {_emitted_types(game)[-15:]}"


def test_venom_symbiote_king_etb_skips_self_controller():
    """Edge: Venom's own controller is not affected."""
    print("\n=== Venom King: self-skip ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Venom, Symbiote King")
    new = game.state.event_log[before:]
    self_discards = [
        e for e in new
        if e.type == EventType.DISCARD and e.payload.get('player') == p1.id
    ]
    assert not self_discards, "Venom King discarded its own controller"


# ============================================================================
# Carnage, Unleashed
# ============================================================================

def test_carnage_unleashed_loads():
    print("\n=== Carnage, Unleashed: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    c = _put_on_battlefield(game, p1, "Carnage, Unleashed")
    assert c.zone == ZoneType.BATTLEFIELD
    assert has_ability(c, "haste", game.state)


def test_carnage_unleashed_opp_life_loss_grows_and_pings():
    """When opponent loses life, Carnage gets a +1/+1 counter and pings opps."""
    print("\n=== Carnage: snowball + ping ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    carnage = _put_on_battlefield(game, p1, "Carnage, Unleashed")

    before = len(game.state.event_log)
    # Trigger a fake opp life-loss from any source other than Carnage itself.
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p2.id, 'amount': -1},
    ))
    new = game.state.event_log[before:]
    counters = [
        e for e in new
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == carnage.id
        and e.payload.get('counter_type') == '+1/+1'
    ]
    pings = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == carnage.id
    ]
    assert counters, f"Expected +1/+1 counter on Carnage; got {_emitted_types(game)[-10:]}"
    assert pings, f"Expected ping back to opp; got {_emitted_types(game)[-10:]}"


def test_carnage_unleashed_own_life_loss_no_fire():
    """Edge: controller's own life loss does NOT trigger."""
    print("\n=== Carnage: own life loss no fire ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    carnage = _put_on_battlefield(game, p1, "Carnage, Unleashed")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p1.id, 'amount': -2},
    ))
    new = game.state.event_log[before:]
    counters = [
        e for e in new
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == carnage.id
    ]
    assert not counters, "Carnage grew from its own controller's life loss"


def test_carnage_unleashed_no_self_loop():
    """Edge: Carnage's own ping back at opps must not retrigger forever."""
    print("\n=== Carnage: no infinite loop ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    carnage = _put_on_battlefield(game, p1, "Carnage, Unleashed")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p2.id, 'amount': -1},
    ))
    # If the loop guard fails, we'd see an exploding count. With the
    # `event.source == obj.id` skip, expect a single counter add.
    new = game.state.event_log[before:]
    counters = [
        e for e in new
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == carnage.id
    ]
    assert len(counters) == 1, (
        f"Expected exactly 1 counter, got {len(counters)} (loop guard broken?)"
    )


# ============================================================================
# The Sinister Six Gathers (saga)
# ============================================================================

def test_sinister_six_gathers_loads():
    print("\n=== Sinister Six Gathers: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Sinister Six Gathers")
    assert saga.interceptor_ids


def test_sinister_six_gathers_chapter_i_discards_each_opp():
    """Chapter I emits DISCARD against each opponent."""
    print("\n=== Sinister Six Gathers: I ===")
    from src.cards.custom.man_of_pider import _sinister_six_chapter_i
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    saga = _put_on_battlefield(game, p1, "The Sinister Six Gathers")
    events = _sinister_six_chapter_i(saga, game.state)
    discards = [e for e in events
                if e.type == EventType.DISCARD and e.payload.get('player') == p2.id]
    assert discards, "Chapter I should target opp with DISCARD"


def test_sinister_six_gathers_chapter_ii_searches_villain():
    """Chapter II emits SEARCH_LIBRARY with Villain subtype + MV<=4."""
    print("\n=== Sinister Six Gathers: II ===")
    from src.cards.custom.man_of_pider import _sinister_six_chapter_ii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Sinister Six Gathers")
    events = _sinister_six_chapter_ii(saga, game.state)
    assert events and events[0].type == EventType.SEARCH_LIBRARY
    payload = events[0].payload
    assert payload.get('subtype') == 'Villain'
    assert payload.get('mana_value_max') == 4
    assert payload.get('destination') == 'battlefield'


def test_sinister_six_gathers_chapter_iii_buffs_only_villains():
    """Chapter III buffs Villains, not non-Villain creatures."""
    print("\n=== Sinister Six Gathers: III ===")
    from src.cards.custom.man_of_pider import _sinister_six_chapter_iii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Sinister Six Gathers")
    villain = _put_on_battlefield(game, p1, "Hammerhead")  # Has Villain subtype
    # NYC Police Officer is a non-Villain Soldier — confirm filter.
    hero = _put_on_battlefield(game, p1, "NYC Police Officer")

    events = _sinister_six_chapter_iii(saga, game.state)
    pt_mods = [e for e in events if e.type == EventType.PT_MODIFICATION]
    targets = {e.payload['object_id'] for e in pt_mods}
    assert villain.id in targets, f"Villain should be buffed: {targets}"
    assert hero.id not in targets, f"Non-Villain hero should NOT be buffed: {targets}"


# ============================================================================
# Iron Spider Armor
# ============================================================================

def test_iron_spider_armor_loads():
    print("\n=== Iron Spider Armor: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    armor = _put_on_battlefield(game, p1, "Iron Spider Armor")
    assert armor.zone == ZoneType.BATTLEFIELD
    activated = getattr(armor.state, 'activated_abilities', None)
    assert activated, "Expected equip activated ability"
    assert len(armor.interceptor_ids) >= 2, (
        f"Expected PT + keyword + ward; got {len(armor.interceptor_ids)}"
    )


def test_iron_spider_armor_attach_buffs_creature():
    """ATTACH grants +3/+3 and reach."""
    print("\n=== Iron Spider Armor: +3/+3 reach on attach ===")
    game = Game()
    p1 = game.add_player("Alice")
    armor = _put_on_battlefield(game, p1, "Iron Spider Armor")
    crab = _put_on_battlefield(game, p1, "NYC Police Officer")
    base_p = get_power(crab, game.state)
    base_t = get_toughness(crab, game.state)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': armor.id, 'target_id': crab.id},
        source=armor.id,
    ))

    new_p = get_power(crab, game.state)
    new_t = get_toughness(crab, game.state)
    assert new_p == base_p + 3
    assert new_t == base_t + 3
    assert has_ability(crab, "reach", game.state)


# ============================================================================
# Miles Morales, Ultimate Spider-Man
# ============================================================================

def test_miles_morales_ultimate_loads():
    print("\n=== Miles Morales Ultimate: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    miles = _put_on_battlefield(game, p1, "Miles Morales, Ultimate Spider-Man")
    assert has_ability(miles, "flying", game.state)
    assert has_ability(miles, "menace", game.state)


def test_miles_morales_ultimate_attack_emits_scry_and_constraint():
    """Attack trigger emits SCRY and a TEMPORARY_EFFECT (block restriction)."""
    print("\n=== Miles Morales Ultimate: attack pump + scry ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    miles = _put_on_battlefield(game, p1, "Miles Morales, Ultimate Spider-Man")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': miles.id, 'attacker': miles.id, 'controller': p1.id},
        source=miles.id,
    ))
    new = game.state.event_log[before:]
    scry = [e for e in new
            if e.type == EventType.SCRY and e.payload.get('player') == p1.id]
    constraints = [
        e for e in new
        if e.type == EventType.TEMPORARY_EFFECT
        and e.payload.get('player') == p2.id
        and e.payload.get('effect') == 'cant_block_higher_power_than'
    ]
    assert scry, f"Expected SCRY on Miles attack; got {_emitted_types(game)[-10:]}"
    assert constraints, f"Expected blocker constraint; got {_emitted_types(game)[-10:]}"


def test_miles_morales_ultimate_constraint_scales_with_hand():
    """Constraint value tracks hand size at attack time."""
    print("\n=== Miles Morales Ultimate: scales with hand ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    miles = _put_on_battlefield(game, p1, "Miles Morales, Ultimate Spider-Man")

    # Stack 3 cards in p1's hand.
    h = SPIDER_MAN_CUSTOM_CARDS["Hammerhead"]
    hand = game.state.zones[f'hand_{p1.id}']
    for _ in range(3):
        obj = game.create_object(
            name="Hammerhead", owner_id=p1.id, zone=ZoneType.HAND,
            characteristics=h.characteristics, card_def=None,
        )
        obj.card_def = h
        if obj.id not in hand.objects:
            hand.objects.append(obj.id)

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': miles.id, 'attacker': miles.id, 'controller': p1.id},
        source=miles.id,
    ))
    new = game.state.event_log[before:]
    constraints = [
        e for e in new
        if e.type == EventType.TEMPORARY_EFFECT
        and e.payload.get('effect') == 'cant_block_higher_power_than'
    ]
    assert constraints, "Expected blocker constraint"
    val = constraints[-1].payload.get('value')
    assert val == 3, f"Expected constraint value=3 (hand size), got {val}"


def test_miles_morales_ultimate_other_attacker_no_fire():
    """Edge: another creature attacking does NOT trigger Miles's ability."""
    print("\n=== Miles Morales Ultimate: other attacker no fire ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Miles Morales, Ultimate Spider-Man")
    other = _put_on_battlefield(game, p1, "NYC Police Officer")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': other.id, 'attacker': other.id, 'controller': p1.id},
        source=other.id,
    ))
    new = game.state.event_log[before:]
    constraints = [
        e for e in new
        if e.type == EventType.TEMPORARY_EFFECT
        and e.payload.get('effect') == 'cant_block_higher_power_than'
    ]
    assert not constraints, "Constraint fired on wrong attacker"


# ============================================================================
# Slice-4 thin-bust (2026-05-19): 11 vanilla cards lifted to depth-1.
# Each test fires the buffed trigger and asserts the expected event hits the
# opponent (or self). These keep the depth-v2 axes wired in the engine, not
# just on paper.
# ============================================================================

def test_neighborhood_vigilante_attack_pings_opp():
    print("\n=== Neighborhood Vigilante: attack pings opp ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    v = _put_on_battlefield(game, p1, "Neighborhood Vigilante")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': v.id, 'attacker': v.id, 'controller': p1.id},
        source=v.id,
    ))
    new = game.state.event_log[before:]
    pings = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == v.id
    ]
    assert pings, f"Expected attack ping on opp; got {_emitted_types(game)[-10:]}"


def test_rooftop_sidekick_etb_scrys():
    print("\n=== Rooftop Sidekick: ETB scry ===")
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    before = len(game.state.event_log)
    s = _put_on_battlefield(game, p1, "Rooftop Sidekick")
    new = game.state.event_log[before:]
    scrys = [
        e for e in new
        if e.type == EventType.SCRY
        and e.payload.get('reason') == 'rooftop_sidekick'
        and e.source == s.id
    ]
    assert scrys, f"Expected SCRY on ETB; got {_emitted_types(game)[-10:]}"


def test_alley_wall_crawler_etb_drains_opp():
    print("\n=== Alley Wall-Crawler: ETB drains opp ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    a = _put_on_battlefield(game, p1, "Alley Wall-Crawler")
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == a.id
    ]
    assert drains, f"Expected ETB drain on opp; got {_emitted_types(game)[-10:]}"


def test_petty_mugger_attack_makes_opp_discard():
    print("\n=== Petty Mugger: attack opp discard ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    m = _put_on_battlefield(game, p1, "Petty Mugger")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': m.id, 'attacker': m.id, 'controller': p1.id},
        source=m.id,
    ))
    new = game.state.event_log[before:]
    discards = [
        e for e in new
        if e.type == EventType.DISCARD
        and e.payload.get('player') == p2.id
        and e.source == m.id
    ]
    assert discards, f"Expected DISCARD on attack; got {_emitted_types(game)[-10:]}"


def test_symbiote_larva_death_drains_opp():
    print("\n=== Symbiote Larva: death drain ===")
    from src.engine import CardType
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    larva = _put_on_battlefield(game, p1, "Symbiote Larva")
    before = len(game.state.event_log)
    # Send it to graveyard so death trigger fires.
    gy_id = f'graveyard_{p1.id}'
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': larva.id},
        source=larva.id,
    ))
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == larva.id
    ]
    assert drains, f"Expected death drain; got {_emitted_types(game)[-10:]}"


def test_klyntar_scout_etb_surveils():
    print("\n=== Klyntar Scout: ETB surveil ===")
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    before = len(game.state.event_log)
    k = _put_on_battlefield(game, p1, "Klyntar Scout")
    new = game.state.event_log[before:]
    surveils = [
        e for e in new
        if e.type == EventType.SURVEIL
        and e.payload.get('reason') == 'klyntar_scout'
        and e.source == k.id
    ]
    assert surveils, f"Expected SURVEIL on ETB; got {_emitted_types(game)[-10:]}"


def test_hand_ninja_attack_mills_opp():
    print("\n=== Hand Ninja: attack mill ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    n = _put_on_battlefield(game, p1, "Hand Ninja")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': n.id, 'attacker': n.id, 'controller': p1.id},
        source=n.id,
    ))
    new = game.state.event_log[before:]
    mills = [
        e for e in new
        if e.type == EventType.MILL
        and e.payload.get('player') == p2.id
        and e.source == n.id
    ]
    assert mills, f"Expected MILL on attack; got {_emitted_types(game)[-10:]}"


def test_vulture_initiate_etb_drains_opp():
    print("\n=== Vulture Initiate: ETB drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    v = _put_on_battlefield(game, p1, "Vulture Initiate")
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == v.id
    ]
    assert drains, f"Expected ETB drain; got {_emitted_types(game)[-10:]}"


def test_oscorp_enforcer_etb_makes_opp_discard():
    print("\n=== Oscorp Enforcer: ETB opp discard ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    e = _put_on_battlefield(game, p1, "Oscorp Enforcer")
    new = game.state.event_log[before:]
    discards = [
        ev for ev in new
        if ev.type == EventType.DISCARD
        and ev.payload.get('player') == p2.id
        and ev.source == e.id
    ]
    assert discards, f"Expected DISCARD on ETB; got {_emitted_types(game)[-10:]}"


def test_shocker_goon_etb_drains_opp():
    print("\n=== Shocker Goon: ETB drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    s = _put_on_battlefield(game, p1, "Shocker Goon")
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == s.id
    ]
    assert drains, f"Expected ETB drain; got {_emitted_types(game)[-10:]}"


def test_symbiote_brood_attack_mills_opp():
    print("\n=== Symbiote Brood: attack mill ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    b = _put_on_battlefield(game, p1, "Symbiote Brood")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': b.id, 'attacker': b.id, 'controller': p1.id},
        source=b.id,
    ))
    new = game.state.event_log[before:]
    mills = [
        e for e in new
        if e.type == EventType.MILL
        and e.payload.get('player') == p2.id
        and e.source == b.id
    ]
    assert mills, f"Expected MILL on attack; got {_emitted_types(game)[-10:]}"


# ============================================================================
# Slice-13 median-lift tests (2026-05-19): one assertion per buffed vanilla
# card driving SPMC median_depth 0 -> >= 2. Each test puts the card on the
# battlefield (or invokes its resolve handler for instants/sorceries) and
# asserts the expected SCRY/SURVEIL info event + a cross-controller effect
# (LIFE_CHANGE / DAMAGE / MILL / DISCARD / REVEAL_HAND).
# ============================================================================


def _s13_etb_card(card_name):
    """Spin up a game, put the named card under p1, return (game, p1, p2, obj)."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, card_name)
    return game, p1, p2, obj


def _s13_attack(card_name):
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


def _s13_assert_info_and_opp(game, obj, p2, *, info_type, opp_type):
    """Assert info_type (SCRY/SURVEIL) emitted by obj + a cross-controller effect."""
    new = game.state.event_log
    info_evs = [e for e in new if e.type == info_type and e.source == obj.id]
    assert info_evs, (
        f"Expected {info_type.name} from {obj.id}; "
        f"events={[e.type.name for e in new[-15:]]}"
    )
    if opp_type == EventType.LIFE_CHANGE:
        opp_evs = [e for e in new if e.type == opp_type
                   and e.payload.get('player') == p2.id
                   and e.payload.get('amount', 0) < 0
                   and e.source == obj.id]
    elif opp_type == EventType.DAMAGE:
        opp_evs = [e for e in new if e.type == opp_type
                   and e.payload.get('target') == p2.id
                   and e.source == obj.id]
    elif opp_type in (EventType.MILL, EventType.DISCARD, EventType.REVEAL_HAND):
        opp_evs = [e for e in new if e.type == opp_type
                   and e.payload.get('player') == p2.id
                   and e.source == obj.id]
    else:
        opp_evs = []
    assert opp_evs, (
        f"Expected {opp_type.name} against p2 from {obj.id}; "
        f"events={[e.type.name for e in new[-15:]]}"
    )


def _s13_resolve(fn_name):
    """Pull a resolve fn out of the spmc module, prep a 2-player state, call it."""
    fn = getattr(spmc_module, fn_name)
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.state.active_player = p1.id
    events = fn([], game.state)
    return events, p1, p2


# --- ETB tests (creatures, enchantments, artifacts, lands) ------------------


def test_daily_bugle_photographer_etb_scry_drain_s13():
    print("\n=== Slice-13: Daily Bugle Photographer ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("Daily Bugle Photographer")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_dr_octopus_etb_surveil_mill_s13():
    print("\n=== Slice-13: Dr. Octopus ETB surveil+mill ===")
    g, p1, p2, obj = _s13_etb_card("Dr. Octopus, Otto Octavius")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_mysterio_etb_surveil_mill_s13():
    print("\n=== Slice-13: Mysterio ETB surveil+mill ===")
    g, p1, p2, obj = _s13_etb_card("Mysterio, Master of Illusion")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_the_lizard_etb_scry_drain_s13():
    print("\n=== Slice-13: The Lizard ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("The Lizard")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_oscorp_scientist_etb_surveil_mill_s13():
    print("\n=== Slice-13: Oscorp Scientist ETB surveil+mill ===")
    g, p1, p2, obj = _s13_etb_card("Oscorp Scientist")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_mind_control_device_etb_surveil_mill_s13():
    print("\n=== Slice-13: Mind Control Device ETB surveil+mill ===")
    g, p1, p2, obj = _s13_etb_card("Mind Control Device")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_venom_lethal_protector_etb_surveil_drain_s13():
    print("\n=== Slice-13: Venom, Lethal Protector ETB surveil+drain ===")
    g, p1, p2, obj = _s13_etb_card("Venom, Lethal Protector")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_green_goblin_etb_surveil_discard_s13():
    print("\n=== Slice-13: Green Goblin ETB surveil+discard ===")
    g, p1, p2, obj = _s13_etb_card("Green Goblin, Norman Osborn")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.DISCARD)


def test_hobgoblin_etb_surveil_discard_s13():
    print("\n=== Slice-13: Hobgoblin ETB surveil+discard ===")
    g, p1, p2, obj = _s13_etb_card("Hobgoblin")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.DISCARD)


def test_morbius_etb_surveil_drain_s13():
    print("\n=== Slice-13: Morbius ETB surveil+drain ===")
    g, p1, p2, obj = _s13_etb_card("Morbius, the Living Vampire")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_symbiote_tendril_death_drain_s13():
    print("\n=== Slice-13: Symbiote Tendril death drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    t = _put_on_battlefield(game, p1, "Symbiote Tendril")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': t.id},
        source=t.id,
    ))
    new = game.state.event_log[before:]
    drains = [e for e in new
              if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id
              and e.payload.get('amount', 0) < 0
              and e.source == t.id]
    assert drains, f"Expected death drain; got {[e.type.name for e in new[-10:]]}"


def test_crime_boss_etb_surveil_drain_s13():
    print("\n=== Slice-13: Crime Boss ETB surveil+drain ===")
    g, p1, p2, obj = _s13_etb_card("Crime Boss")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_shocker_etb_scry_damage_s13():
    print("\n=== Slice-13: Shocker ETB scry+damage ===")
    g, p1, p2, obj = _s13_etb_card("Shocker")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_sandman_etb_scry_damage_s13():
    print("\n=== Slice-13: Sandman ETB scry+damage ===")
    g, p1, p2, obj = _s13_etb_card("Sandman")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_rhino_etb_scry_damage_s13():
    print("\n=== Slice-13: Rhino ETB scry+damage ===")
    g, p1, p2, obj = _s13_etb_card("Rhino")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_spider_hulk_etb_scry_drain_s13():
    print("\n=== Slice-13: Spider-Hulk ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("Spider-Hulk")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_spider_colony_etb_scry_drain_s13():
    print("\n=== Slice-13: Spider Colony ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("Spider Colony")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_forest_spider_etb_scry_drain_s13():
    print("\n=== Slice-13: Forest Spider ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("Forest Spider")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_prowler_etb_surveil_drain_s13():
    print("\n=== Slice-13: Prowler ETB surveil+drain ===")
    g, p1, p2, obj = _s13_etb_card("Prowler")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_peni_parker_etb_surveil_mill_s13():
    print("\n=== Slice-13: Peni Parker ETB surveil+mill ===")
    g, p1, p2, obj = _s13_etb_card("Peni Parker")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_superior_spider_man_etb_surveil_mill_s13():
    print("\n=== Slice-13: Superior Spider-Man ETB surveil+mill ===")
    g, p1, p2, obj = _s13_etb_card("Superior Spider-Man")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_j_jonah_jameson_etb_scry_drain_s13():
    print("\n=== Slice-13: J. Jonah Jameson ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("J. Jonah Jameson")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_harry_osborn_etb_surveil_drain_s13():
    print("\n=== Slice-13: Harry Osborn ETB surveil+drain ===")
    g, p1, p2, obj = _s13_etb_card("Harry Osborn")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_felicia_hardy_etb_surveil_drain_s13():
    print("\n=== Slice-13: Felicia Hardy ETB surveil+drain ===")
    g, p1, p2, obj = _s13_etb_card("Felicia Hardy")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_vulture_etb_surveil_drain_s13():
    print("\n=== Slice-13: Vulture ETB surveil+drain ===")
    g, p1, p2, obj = _s13_etb_card("Vulture")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_beetle_etb_surveil_drain_s13():
    print("\n=== Slice-13: Beetle ETB surveil+drain ===")
    g, p1, p2, obj = _s13_etb_card("Beetle")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_hammerhead_etb_surveil_discard_s13():
    print("\n=== Slice-13: Hammerhead ETB surveil+discard ===")
    g, p1, p2, obj = _s13_etb_card("Hammerhead")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.DISCARD)


def test_silver_sable_etb_scry_drain_s13():
    print("\n=== Slice-13: Silver Sable ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("Silver Sable")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_neighborhood_watch_etb_scry_drain_s13():
    print("\n=== Slice-13: Neighborhood Watch ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("Neighborhood Watch")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_uncle_ben_etb_scry_drain_s13():
    print("\n=== Slice-13: Uncle Ben ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("Uncle Ben")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_hired_muscle_etb_surveil_drain_s13():
    print("\n=== Slice-13: Hired Muscle ETB surveil+drain ===")
    g, p1, p2, obj = _s13_etb_card("Hired Muscle")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


# --- Enchantment tests -----------------------------------------------------


def test_great_responsibility_etb_scry_drain_s13():
    print("\n=== Slice-13: Great Responsibility ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("Great Responsibility")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_advanced_web_formula_etb_surveil_mill_s13():
    print("\n=== Slice-13: Advanced Web Formula ETB surveil+mill ===")
    g, p1, p2, obj = _s13_etb_card("Advanced Web Formula")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_sinister_rage_etb_scry_damage_s13():
    print("\n=== Slice-13: Sinister Rage ETB scry+damage ===")
    g, p1, p2, obj = _s13_etb_card("Sinister Rage")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_web_trap_etb_scry_drain_s13():
    print("\n=== Slice-13: Web Trap ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("Web Trap")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_underworld_connections_etb_surveil_drain_s13():
    print("\n=== Slice-13: Underworld Connections ETB surveil+drain ===")
    g, p1, p2, obj = _s13_etb_card("Underworld Connections")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_hunters_trap_etb_scry_drain_s13():
    print("\n=== Slice-13: Hunter's Trap ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("Hunter's Trap")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


# --- Artifact tests --------------------------------------------------------


def test_web_shooters_etb_scry_drain_s13():
    print("\n=== Slice-13: Web Shooters ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("Web Shooters")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_oscorp_tech_etb_surveil_mill_s13():
    print("\n=== Slice-13: Oscorp Tech ETB surveil+mill ===")
    g, p1, p2, obj = _s13_etb_card("Oscorp Tech")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_goblin_glider_etb_scry_damage_s13():
    print("\n=== Slice-13: Goblin Glider ETB scry+damage ===")
    g, p1, p2, obj = _s13_etb_card("Goblin Glider")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_iron_spider_suit_etb_scry_drain_s13():
    print("\n=== Slice-13: Iron Spider Suit ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("Iron Spider Suit")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_symbiote_sample_etb_surveil_drain_s13():
    print("\n=== Slice-13: Symbiote Sample ETB surveil+drain ===")
    g, p1, p2, obj = _s13_etb_card("Symbiote Sample")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_daily_bugle_press_etb_scry_drain_s13():
    print("\n=== Slice-13: Daily Bugle Press ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("Daily Bugle Press")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_stark_tech_upgrade_etb_scry_drain_s13():
    print("\n=== Slice-13: Stark Tech Upgrade ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("Stark Tech Upgrade")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


# --- Land tests ------------------------------------------------------------


def test_new_york_city_etb_scry_drain_s13():
    print("\n=== Slice-13: New York City ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("New York City")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_daily_bugle_building_etb_scry_drain_s13():
    print("\n=== Slice-13: Daily Bugle Building ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("Daily Bugle Building")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_oscorp_tower_etb_surveil_mill_s13():
    print("\n=== Slice-13: Oscorp Tower ETB surveil+mill ===")
    g, p1, p2, obj = _s13_etb_card("Oscorp Tower")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_fisk_tower_etb_surveil_drain_s13():
    print("\n=== Slice-13: Fisk Tower ETB surveil+drain ===")
    g, p1, p2, obj = _s13_etb_card("Fisk Tower")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_hells_kitchen_etb_surveil_drain_s13():
    print("\n=== Slice-13: Hell's Kitchen ETB surveil+drain ===")
    g, p1, p2, obj = _s13_etb_card("Hell's Kitchen")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_brooklyn_bridge_etb_scry_drain_s13():
    print("\n=== Slice-13: Brooklyn Bridge ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("Brooklyn Bridge")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_queens_neighborhood_etb_scry_drain_s13():
    print("\n=== Slice-13: Queens Neighborhood ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("Queens Neighborhood")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_stark_tower_etb_scry_drain_s13():
    print("\n=== Slice-13: Stark Tower ETB scry+drain ===")
    g, p1, p2, obj = _s13_etb_card("Stark Tower")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_symbiote_planet_etb_surveil_drain_s13():
    print("\n=== Slice-13: Symbiote Planet ETB surveil+drain ===")
    g, p1, p2, obj = _s13_etb_card("Symbiote Planet")
    _s13_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


# --- Instant/Sorcery resolve tests -----------------------------------------


def test_web_shield_resolve_s13():
    print("\n=== Slice-13: Web Shield resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_web_shield")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_with_great_power_resolve_s13():
    print("\n=== Slice-13: With Great Power resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_with_great_power")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) >= 3 for e in events)


def test_save_the_day_resolve_s13():
    print("\n=== Slice-13: Save the Day resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_save_the_day")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) >= 3 for e in events)


def test_spider_sense_alert_resolve_s13():
    print("\n=== Slice-13: Spider-Sense Alert resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_spider_sense_alert")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_web_sling_resolve_s13():
    print("\n=== Slice-13: Web Sling resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_web_sling")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_illusion_duplicate_resolve_s13():
    print("\n=== Slice-13: Illusion Duplicate resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_illusion_duplicate")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_technological_breakthrough_resolve_s13():
    print("\n=== Slice-13: Technological Breakthrough resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_technological_breakthrough")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_sinister_plot_resolve_s13():
    print("\n=== Slice-13: Sinister Plot resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_sinister_plot")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.DISCARD and e.payload.get('player') == p2.id for e in events)


def test_web_of_shadows_resolve_s13():
    print("\n=== Slice-13: Web of Shadows resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_web_of_shadows")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.DISCARD and e.payload.get('player') == p2.id for e in events)


def test_web_strike_resolve_s13():
    print("\n=== Slice-13: Web Strike resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_web_strike")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_pumpkin_bomb_resolve_s13():
    print("\n=== Slice-13: Pumpkin Bomb resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_pumpkin_bomb")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_goblin_glider_assault_resolve_s13():
    print("\n=== Slice-13: Goblin Glider Assault resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_goblin_glider_assault")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_electric_discharge_resolve_s13():
    print("\n=== Slice-13: Electric Discharge resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_electric_discharge")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_building_collapse_resolve_s13():
    print("\n=== Slice-13: Building Collapse resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_building_collapse")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_venomous_bite_resolve_s13():
    print("\n=== Slice-13: Venomous Bite resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_venomous_bite")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_spider_swarm_resolve_s13():
    print("\n=== Slice-13: Spider Swarm resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_spider_swarm")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_primal_instinct_resolve_s13():
    print("\n=== Slice-13: Primal Instinct resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_primal_instinct")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_jungle_ambush_resolve_s13():
    print("\n=== Slice-13: Jungle Ambush resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_jungle_ambush")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_natures_wrath_resolve_s13():
    print("\n=== Slice-13: Nature's Wrath resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_natures_wrath")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_spider_ham_attack_resolve_s13():
    print("\n=== Slice-13: Spider-Ham Attack resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_spider_ham_attack")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_multiverse_portal_resolve_s13():
    print("\n=== Slice-13: Multiverse Portal resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_multiverse_portal")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_dimension_hopping_resolve_s13():
    print("\n=== Slice-13: Dimension Hopping resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_dimension_hopping")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_symbiote_invasion_resolve_s13():
    print("\n=== Slice-13: Symbiote Invasion resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_symbiote_invasion")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.DISCARD and e.payload.get('player') == p2.id for e in events)


def test_electro_shock_resolve_s13():
    print("\n=== Slice-13: Electro Shock resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_electro_shock")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_spider_army_resolve_s13():
    print("\n=== Slice-13: Spider Army resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_spider_army")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_spectacular_swing_resolve_s13():
    print("\n=== Slice-13: Spectacular Swing resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_spectacular_swing")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_spider_sense_resolve_s13():
    print("\n=== Slice-13: Spider-Sense resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_spider_sense")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_experiment_gone_wrong_resolve_s13():
    print("\n=== Slice-13: Experiment Gone Wrong resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_experiment_gone_wrong")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_hologram_decoy_resolve_s13():
    print("\n=== Slice-13: Hologram Decoy resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_hologram_decoy")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_symbiote_surge_resolve_s13():
    print("\n=== Slice-13: Symbiote Surge resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_symbiote_surge")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.DISCARD and e.payload.get('player') == p2.id for e in events)


def test_shock_therapy_resolve_s13():
    print("\n=== Slice-13: Shock Therapy resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_shock_therapy")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_explosive_rampage_resolve_s13():
    print("\n=== Slice-13: Explosive Rampage resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_explosive_rampage")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_goblin_army_resolve_s13():
    print("\n=== Slice-13: Goblin Army resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_goblin_army")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_fire_punch_resolve_s13():
    print("\n=== Slice-13: Fire Punch resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_fire_punch")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_radioactive_bite_resolve_s13():
    print("\n=== Slice-13: Radioactive Bite resolve ===")
    events, p1, p2 = _s13_resolve("_spmc_resolve_radioactive_bite")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


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
