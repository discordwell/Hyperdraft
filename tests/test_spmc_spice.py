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
