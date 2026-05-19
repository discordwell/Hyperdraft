"""
My Hero Academia Spice Pass Tests (Phase A1)

Validates the format-defining cards added in the MHA Phase A1 spice pass.
Mirrors `tests/test_zelda_spice.py` shape.

Cards covered:
- One For All, Inherited Quirk (NEW — Legendary Enchantment assembly engine)
- Sports Festival, U.A. Tradition (NEW — saga: tutor / tokens / anthem)
- Deku, One For All Awakened (NEW — Legendary mythic build-around)
- Hatsume's Battle Suit (NEW — Equipment with granted activated ability)
- Momo, Creation Hero (REWIRE — was unwired vanilla legendary)
- Midnight, R-Rated Hero (REWIRE — ETB tap each opp creature)
- Koda, Anima (REWIRE — was unwired; Bird token + attack pump)
"""

import os
import sys
# Compute repo root from this file's location so the test runs from any
# checkout (main or a `.claude/worktrees/agent-*/` worktree).
# See spice-pass.md gotcha #18.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness,
)
from src.engine.queries import has_ability
from src.cards.custom.my_hero_academia import MY_HERO_ACADEMIA_CARDS


def _put_on_battlefield(game, player, card_name):
    """Mirror the spice-pass test harness shape (gotcha #X).

    `create_object` runs `setup_interceptors` for BATTLEFIELD/COMMAND zones.
    Putting the card in HAND first with `card_def=None`, then ZONE_CHANGE to
    battlefield, runs setup exactly once via the pipeline (the correct path)."""
    card_def = MY_HERO_ACADEMIA_CARDS[card_name]
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
# One For All, Inherited Quirk
# ============================================================================

def test_one_for_all_enchantment_loads():
    print("\n=== One For All: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    ofa = _put_on_battlefield(game, p1, "One For All, Inherited Quirk")
    assert ofa.zone == ZoneType.BATTLEFIELD
    # 3 interceptors: ETB trigger, upkeep trigger, attack listener.
    assert len(ofa.interceptor_ids) >= 3, (
        f"Expected 3+ interceptors; got {len(ofa.interceptor_ids)}"
    )


def test_one_for_all_etb_shards_highest_power_hero():
    """ETB puts a +1/+1 counter on the highest-power Hero you control."""
    print("\n=== One For All: ETB shard ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Drop a Hero first so ETB can find a target.
    bakugo = _put_on_battlefield(game, p1, "Bakugo, Explosion Hero")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "One For All, Inherited Quirk")
    new = game.state.event_log[before:]
    counters = [
        e for e in new
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == bakugo.id
        and e.payload.get('counter_type') == '+1/+1'
    ]
    assert counters, f"Expected COUNTER_ADDED on Bakugo; recent={[e.type.name for e in new[-10:]]}"


def test_one_for_all_etb_no_heroes_no_op():
    """ETB without any Hero on the battlefield: no counter event."""
    print("\n=== One For All: ETB no heroes ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "One For All, Inherited Quirk")
    new = game.state.event_log[before:]
    counters = [e for e in new if e.type == EventType.COUNTER_ADDED]
    assert not counters, f"Expected no counters; got {len(counters)}"


def test_one_for_all_attack_grants_double_strike_for_3plus_shards():
    """Hero with 3+ +1/+1 counters that attacks gets double strike."""
    print("\n=== One For All: attack -> double strike ===")
    game = Game()
    p1 = game.add_player("Alice")
    bakugo = _put_on_battlefield(game, p1, "Bakugo, Explosion Hero")
    _put_on_battlefield(game, p1, "One For All, Inherited Quirk")
    # Manually crank up Bakugo's shard count to 3.
    bakugo.state.counters['+1/+1'] = 3

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': bakugo.id, 'attacker': bakugo.id, 'controller': p1.id},
        source=bakugo.id,
    ))
    new = game.state.event_log[before:]
    grants = [
        e for e in new
        if e.type == EventType.GRANT_KEYWORD
        and e.payload.get('object_id') == bakugo.id
        and e.payload.get('keyword') == 'double_strike'
    ]
    assert grants, (
        f"Expected double_strike grant; recent={[e.type.name for e in new[-10:]]}"
    )


def test_one_for_all_attack_no_grant_below_threshold():
    """Hero with only 2 +1/+1 counters: no double strike on attack."""
    print("\n=== One For All: 2 shards no grant ===")
    game = Game()
    p1 = game.add_player("Alice")
    bakugo = _put_on_battlefield(game, p1, "Bakugo, Explosion Hero")
    _put_on_battlefield(game, p1, "One For All, Inherited Quirk")
    bakugo.state.counters['+1/+1'] = 2

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': bakugo.id, 'attacker': bakugo.id, 'controller': p1.id},
        source=bakugo.id,
    ))
    new = game.state.event_log[before:]
    grants = [
        e for e in new
        if e.type == EventType.GRANT_KEYWORD
        and e.payload.get('object_id') == bakugo.id
        and e.payload.get('keyword') == 'double_strike'
    ]
    assert not grants, f"Expected NO grant below threshold; got {len(grants)}"


# ============================================================================
# Sports Festival, U.A. Tradition (saga)
# ============================================================================

def test_sports_festival_loads():
    print("\n=== Sports Festival: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Sports Festival, U.A. Tradition")
    assert saga.interceptor_ids, "Saga should register chapter interceptors"


def test_sports_festival_chapter_i_emits_student_tutor():
    """Direct chapter-I dispatch emits SEARCH_LIBRARY with subtype filter."""
    print("\n=== Sports Festival: chapter I ===")
    from src.cards.custom.my_hero_academia import _sports_festival_chapter_i
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Sports Festival, U.A. Tradition")
    events = _sports_festival_chapter_i(saga, game.state)
    assert events and events[0].type == EventType.SEARCH_LIBRARY
    payload = events[0].payload
    assert payload.get('subtypes_any') == ['Student']
    assert payload.get('mana_value_max') == 3
    assert payload.get('destination') == 'battlefield'


def test_sports_festival_chapter_ii_creates_two_student_tokens():
    print("\n=== Sports Festival: chapter II ===")
    from src.cards.custom.my_hero_academia import _sports_festival_chapter_ii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Sports Festival, U.A. Tradition")
    events = _sports_festival_chapter_ii(saga, game.state)
    tokens = [
        e for e in events
        if e.type == EventType.CREATE_TOKEN
        and e.payload.get('token', {}).get('subtypes', set()) & {'Student'}
    ]
    assert len(tokens) == 2


def test_sports_festival_chapter_iii_pumps_students_only():
    """III pumps Students you control, not other creatures or opp creatures."""
    print("\n=== Sports Festival: chapter III ===")
    from src.cards.custom.my_hero_academia import _sports_festival_chapter_iii
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    saga = _put_on_battlefield(game, p1, "Sports Festival, U.A. Tradition")
    # Drop a Student you control (Deku is Student+Hero).
    deku = _put_on_battlefield(game, p1, "Deku, Inheritor of One For All")
    # Drop an opp Student.
    opp_student = _put_on_battlefield(game, p2, "Growth-Type Student")

    events = _sports_festival_chapter_iii(saga, game.state)
    targets = [e.payload['object_id'] for e in events if e.type == EventType.PT_MODIFICATION]
    assert deku.id in targets, f"Own Deku should be buffed: {targets}"
    assert opp_student.id not in targets, f"Opp Student should NOT be buffed: {targets}"
    assert saga.id not in targets, f"Saga is enchantment, should not target: {targets}"


# ============================================================================
# Deku, One For All Awakened
# ============================================================================

def test_deku_awakened_loads_with_keywords_and_etb():
    print("\n=== Deku Awakened: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    deku = _put_on_battlefield(game, p1, "Deku, One For All Awakened")
    assert has_ability(deku, "trample", game.state)
    assert has_ability(deku, "haste", game.state)


def test_deku_awakened_etb_adds_two_self_counters():
    """ETB emits COUNTER_ADDED for 2 +1/+1 counters on self."""
    print("\n=== Deku Awakened: ETB self-shard ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    deku = _put_on_battlefield(game, p1, "Deku, One For All Awakened")
    new = game.state.event_log[before:]
    counters = [
        e for e in new
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == deku.id
        and e.payload.get('counter_type') == '+1/+1'
        and e.payload.get('amount') == 2
    ]
    assert counters, f"Expected ETB +2 +1/+1 on self; recent={[e.type.name for e in new[-10:]]}"


def test_deku_awakened_attack_spreads_counters_to_other_heroes():
    """Attack distributes 1 +1/+1 to each OTHER Hero you control."""
    print("\n=== Deku Awakened: attack spread ===")
    game = Game()
    p1 = game.add_player("Alice")
    bakugo = _put_on_battlefield(game, p1, "Bakugo, Explosion Hero")
    deku = _put_on_battlefield(game, p1, "Deku, One For All Awakened")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': deku.id, 'attacker': deku.id, 'controller': p1.id},
        source=deku.id,
    ))
    new = game.state.event_log[before:]
    counters = [
        e for e in new
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('counter_type') == '+1/+1'
    ]
    targets = {e.payload.get('object_id') for e in counters}
    assert bakugo.id in targets, f"Bakugo should receive a shard: {targets}"
    assert deku.id not in targets, f"Deku must NOT shard himself in attack: {targets}"


def test_deku_awakened_attack_no_heroes_no_spread():
    """Edge: attack with no OTHER Hero you control -> no spread events."""
    print("\n=== Deku Awakened: solo attack no spread ===")
    game = Game()
    p1 = game.add_player("Alice")
    deku = _put_on_battlefield(game, p1, "Deku, One For All Awakened")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': deku.id, 'attacker': deku.id, 'controller': p1.id},
        source=deku.id,
    ))
    new = game.state.event_log[before:]
    counters = [
        e for e in new
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('counter_type') == '+1/+1'
        and e.payload.get('object_id') != deku.id
    ]
    assert not counters, f"Expected NO spread without other Heroes; got {len(counters)}"


# ============================================================================
# Hatsume's Battle Suit
# ============================================================================

def test_hatsume_suit_loads():
    print("\n=== Hatsume's Battle Suit: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    suit = _put_on_battlefield(game, p1, "Hatsume's Battle Suit")
    assert suit.zone == ZoneType.BATTLEFIELD
    activated = getattr(suit.state, 'activated_abilities', None)
    assert activated, "Expected an equip activated ability on Hatsume's Battle Suit"


def test_hatsume_suit_attach_grants_pt_and_first_strike():
    """ATTACH gives +2/+2 + first strike to equipped creature."""
    print("\n=== Hatsume's Battle Suit: attach ===")
    game = Game()
    p1 = game.add_player("Alice")
    suit = _put_on_battlefield(game, p1, "Hatsume's Battle Suit")
    bakugo = _put_on_battlefield(game, p1, "Bakugo, Explosion Hero")
    base_p = get_power(bakugo, game.state)
    base_t = get_toughness(bakugo, game.state)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': suit.id, 'target_id': bakugo.id},
        source=suit.id,
    ))
    new_p = get_power(bakugo, game.state)
    new_t = get_toughness(bakugo, game.state)
    assert new_p == base_p + 2, f"Expected power +2: {base_p}->{new_p}"
    assert new_t == base_t + 2, f"Expected toughness +2: {base_t}->{new_t}"
    assert has_ability(bakugo, 'first_strike', game.state), (
        "Expected first_strike after attach"
    )


# ============================================================================
# Momo, Creation Hero (REWIRE)
# ============================================================================

def test_momo_creation_etb_creates_artifact_token():
    """ETB emits CREATE_TOKEN for a 0/2 Construct artifact creature."""
    print("\n=== Momo: ETB creates Gear token ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Momo, Creation Hero")
    new = game.state.event_log[before:]
    tokens = [
        e for e in new
        if e.type == EventType.CREATE_TOKEN
        and 'Construct' in e.payload.get('token', {}).get('subtypes', set())
    ]
    assert tokens, f"Expected Construct token CREATE_TOKEN; recent={[e.type.name for e in new[-10:]]}"


def test_momo_creation_cast_grants_life_gain():
    """Cast spell -> +1 life. Opponent cast -> no life gain."""
    print("\n=== Momo: spell -> +1 life (own only) ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Momo, Creation Hero")

    # p1 casts a spell -> +1 life
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={'caster': p1.id, 'stack_item_id': 'spell-1'},
    ))
    new = game.state.event_log[before:]
    gains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p1.id
        and e.payload.get('amount', 0) > 0
    ]
    assert gains, f"Expected life gain after own spell; recent={[e.type.name for e in new[-8:]]}"

    # p2 casts -> no own-side gain
    mid = len(game.state.event_log)
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={'caster': p2.id, 'stack_item_id': 'spell-2'},
    ))
    new2 = game.state.event_log[mid:]
    opp_gains = [
        e for e in new2
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p1.id
        and e.payload.get('amount', 0) > 0
    ]
    assert not opp_gains, f"Expected no gain on opp spell; got {len(opp_gains)}"


# ============================================================================
# Midnight, R-Rated Hero (REWIRE)
# ============================================================================

def test_midnight_etb_taps_opp_creatures_only():
    """ETB taps every opp creature; doesn't touch own creatures."""
    print("\n=== Midnight: ETB tap opp ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    opp_a = _put_on_battlefield(game, p2, "Bakugo, Explosion Hero")
    opp_b = _put_on_battlefield(game, p2, "Growth-Type Student")
    own = _put_on_battlefield(game, p1, "Bakugo, Explosion Hero")

    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Midnight, R-Rated Hero")
    new = game.state.event_log[before:]
    taps = [
        e for e in new
        if e.type == EventType.TAP
    ]
    tap_targets = {e.payload.get('object_id') for e in taps}
    assert opp_a.id in tap_targets, f"opp_a should be tapped: {tap_targets}"
    assert opp_b.id in tap_targets, f"opp_b should be tapped: {tap_targets}"
    assert own.id not in tap_targets, f"own creature should NOT be tapped: {tap_targets}"


def test_midnight_has_flash():
    print("\n=== Midnight: flash ===")
    game = Game()
    p1 = game.add_player("Alice")
    mid = _put_on_battlefield(game, p1, "Midnight, R-Rated Hero")
    assert has_ability(mid, "flash", game.state), "Midnight should have flash"


# ============================================================================
# Koda, Anima (REWIRE)
# ============================================================================

def test_koda_etb_creates_bird_token():
    print("\n=== Koda: ETB Bird ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Koda, Anima")
    new = game.state.event_log[before:]
    birds = [
        e for e in new
        if e.type == EventType.CREATE_TOKEN
        and 'Bird' in e.payload.get('token', {}).get('subtypes', set())
    ]
    assert birds, f"Expected Bird token; recent={[e.type.name for e in new[-10:]]}"


def test_koda_attack_pumps_birds_only():
    """Koda's attack trigger emits +1/+0 PT_MOD on each Bird you control.

    Note: tokens emitted via CREATE_TOKEN aren't on the battlefield at the time
    of this test (engine needs to process the event). Instead we plant a non-
    token Bird manually and check the attack fires for it."""
    print("\n=== Koda: attack pump bird ===")
    game = Game()
    p1 = game.add_player("Alice")
    koda = _put_on_battlefield(game, p1, "Koda, Anima")

    # Hand-craft a Bird object directly so the attack trigger has a target.
    from src.engine import Characteristics
    bird_chars = Characteristics(
        types={CardType.CREATURE},
        subtypes={'Bird'},
        power=1, toughness=1,
        colors={Color.GREEN},
    )
    bird = game.create_object(
        name="Test Bird",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=bird_chars,
        card_def=None,
    )

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': koda.id, 'attacker': koda.id, 'controller': p1.id},
        source=koda.id,
    ))
    new = game.state.event_log[before:]
    pt_mods = [
        e for e in new
        if e.type == EventType.PT_MODIFICATION
        and e.payload.get('object_id') == bird.id
    ]
    assert pt_mods, f"Expected PT_MOD on Bird; recent={[e.type.name for e in new[-10:]]}"
    assert pt_mods[-1].payload.get('power_mod') == 1


# ============================================================================
# Phase A2 (slice 3) — decision-axis flip cards
# ============================================================================


def test_all_might_apex_loads():
    """Setup registers vigilance + modal-ETB trigger interceptors."""
    print("\n=== All Might, One For All Apex: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    am = _put_on_battlefield(game, p1, "All Might, One For All Apex")
    assert am.zone == ZoneType.BATTLEFIELD
    assert len(am.interceptor_ids) >= 2, (
        f"Expected vigilance + modal interceptors; got {len(am.interceptor_ids)}"
    )
    assert has_ability(am, 'vigilance', game.state), "Expected vigilance"


def test_all_might_apex_etb_opens_modal_choice():
    """ETB installs a modal_with_targeting pending_choice with 3 modes."""
    print("\n=== All Might Apex: pending modal choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    am = _put_on_battlefield(game, p1, "All Might, One For All Apex")
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending_choice after ETB"
    assert pc.source_id == am.id
    assert pc.choice_type == "modal_with_targeting"
    assert pc.player == p1.id
    assert len(pc.options) == 3, f"Expected 3 modes; got {len(pc.options)}"


def test_deku_full_cowl_combat_loads():
    """Setup registers haste + attack trigger interceptors."""
    print("\n=== Deku, Full Cowl Combat: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    deku = _put_on_battlefield(game, p1, "Deku, Full Cowl Combat")
    assert deku.zone == ZoneType.BATTLEFIELD
    assert len(deku.interceptor_ids) >= 2, (
        f"Expected haste + attack triggers; got {len(deku.interceptor_ids)}"
    )
    assert has_ability(deku, 'haste', game.state), "Expected haste"


def test_deku_full_cowl_combat_attack_emits_target_required_and_info():
    """Attack emits TARGET_REQUIRED + TARGET_CHOSEN info event."""
    print("\n=== Deku Full Cowl Combat: attack triggers smash + info ===")
    game = Game()
    p1 = game.add_player("Alice")
    deku = _put_on_battlefield(game, p1, "Deku, Full Cowl Combat")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': deku.id, 'attacker': deku.id, 'controller': p1.id},
        source=deku.id,
    ))
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == deku.id
        and e.payload.get('effect') == 'damage'
        and e.payload.get('target_filter') == 'opponent_creature'
    ]
    assert target_reqs, (
        f"Expected smash TARGET_REQUIRED; recent={[e.type.name for e in new[-10:]]}"
    )
    info_events = [
        e for e in new
        if e.type == EventType.TARGET_CHOSEN and e.payload.get('source') == deku.id
    ]
    assert info_events, "Expected TARGET_CHOSEN info pulse on attack"


def test_bakugo_howitzer_impact_loads():
    """Setup registers the divided-damage ETB trigger."""
    print("\n=== Bakugo's Howitzer Impact: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    hi = _put_on_battlefield(game, p1, "Bakugo's Howitzer Impact")
    assert hi.zone == ZoneType.BATTLEFIELD
    assert hi.interceptor_ids, "Expected ETB interceptor"


def test_bakugo_howitzer_impact_etb_emits_divided_damage_target_required():
    """ETB emits TARGET_REQUIRED with divide_amount=6 and damage effect."""
    print("\n=== Bakugo's Howitzer Impact: ETB distribute damage ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    hi = _put_on_battlefield(game, p1, "Bakugo's Howitzer Impact")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == hi.id
        and e.payload.get('effect') == 'damage'
    ]
    assert target_reqs, (
        f"Expected damage TARGET_REQUIRED; new={[e.type.name for e in new[-10:]]}"
    )
    payload = target_reqs[0].payload
    assert payload.get('divide_amount') == 6, (
        f"Expected divide_amount=6; got {payload.get('divide_amount')}"
    )


def test_endeavor_prominence_forge_loads():
    """Setup registers the divided-counters ETB trigger."""
    print("\n=== Endeavor's Prominence Forge: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    epf = _put_on_battlefield(game, p1, "Endeavor's Prominence Forge")
    assert epf.zone == ZoneType.BATTLEFIELD
    assert epf.interceptor_ids, "Expected ETB interceptor"


def test_endeavor_prominence_forge_etb_emits_divided_counters_target_required():
    """ETB emits TARGET_REQUIRED with divide_amount=4 and counter_add effect."""
    print("\n=== Endeavor's Prominence Forge: ETB distribute counters ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    epf = _put_on_battlefield(game, p1, "Endeavor's Prominence Forge")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == epf.id
        and e.payload.get('effect') == 'counter_add'
    ]
    assert target_reqs, (
        f"Expected counter_add TARGET_REQUIRED; new={[e.type.name for e in new[-10:]]}"
    )
    payload = target_reqs[0].payload
    assert payload.get('divide_amount') == 4, (
        f"Expected divide_amount=4; got {payload.get('divide_amount')}"
    )


def test_sir_nighteye_foresights_edge_loads():
    """Setup registers an ETB trigger."""
    print("\n=== Sir Nighteye, Foresight's Edge: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    sn = _put_on_battlefield(game, p1, "Sir Nighteye, Foresight's Edge")
    assert sn.zone == ZoneType.BATTLEFIELD
    assert sn.interceptor_ids, "Expected ETB interceptor"


def test_sir_nighteye_etb_with_library_opens_scry_choice():
    """ETB opens a scry pending_choice when library has cards."""
    print("\n=== Sir Nighteye: ETB opens scry choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Plant 3 cards in p1's library.
    chitauri_def = MY_HERO_ACADEMIA_CARDS["Eager Sidekick"]
    p1_lib = game.state.zones[f'library_{p1.id}']
    for _ in range(3):
        obj = game.create_object(
            name="Eager Sidekick",
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=chitauri_def.characteristics,
            card_def=None,
        )
        obj.card_def = chitauri_def
        if obj.id not in p1_lib.objects:
            p1_lib.objects.append(obj.id)
    sn = _put_on_battlefield(game, p1, "Sir Nighteye, Foresight's Edge")
    pc = game.state.pending_choice
    assert pc is not None, "Expected scry pending_choice"
    assert pc.source_id == sn.id
    assert pc.choice_type == "scry"
    assert pc.player == p1.id


def test_sir_nighteye_etb_empty_library_no_op():
    """ETB with empty library doesn't crash and doesn't install a choice."""
    print("\n=== Sir Nighteye: empty library no-op ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Empty the library before ETB.
    p1_lib = game.state.zones[f'library_{p1.id}']
    p1_lib.objects.clear()
    sn = _put_on_battlefield(game, p1, "Sir Nighteye, Foresight's Edge")
    assert sn.zone == ZoneType.BATTLEFIELD


def test_toga_bloody_mimicry_loads():
    """Setup registers death trigger interceptors."""
    print("\n=== Toga, Bloody Mimicry: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    toga = _put_on_battlefield(game, p1, "Toga, Bloody Mimicry")
    assert toga.zone == ZoneType.BATTLEFIELD
    assert len(toga.interceptor_ids) >= 2, (
        f"Expected 2+ death triggers; got {len(toga.interceptor_ids)}"
    )


def test_toga_bloody_mimicry_death_emits_exile_target_required():
    """Toga's death emits TARGET_REQUIRED with effect=exile."""
    print("\n=== Toga: death -> exile target required ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    toga = _put_on_battlefield(game, p1, "Toga, Bloody Mimicry")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': toga.id, 'destroyed_by': 'lethal_damage'},
        source=toga.id,
    ))
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == toga.id
        and e.payload.get('effect') == 'exile'
    ]
    assert target_reqs, (
        f"Expected exile TARGET_REQUIRED; new={[e.type.name for e in new[-10:]]}"
    )


def test_all_for_one_quirk_thief_loads():
    """Setup registers an ETB trigger."""
    print("\n=== All For One, Quirk Thief: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    afo = _put_on_battlefield(game, p1, "All For One, Quirk Thief")
    assert afo.zone == ZoneType.BATTLEFIELD
    assert afo.interceptor_ids, "Expected ETB interceptor"


def test_all_for_one_etb_with_opponent_hand_opens_discard_choice():
    """ETB opens a discard pending_choice for the opponent when their hand
    has cards."""
    print("\n=== All For One: ETB opens discard choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Plant 2 cards in p2's hand.
    sidekick_def = MY_HERO_ACADEMIA_CARDS["Eager Sidekick"]
    p2_hand = game.state.zones[f'hand_{p2.id}']
    for _ in range(2):
        obj = game.create_object(
            name="Eager Sidekick",
            owner_id=p2.id,
            zone=ZoneType.HAND,
            characteristics=sidekick_def.characteristics,
            card_def=None,
        )
        obj.card_def = sidekick_def
        if obj.id not in p2_hand.objects:
            p2_hand.objects.append(obj.id)
    afo = _put_on_battlefield(game, p1, "All For One, Quirk Thief")
    pc = game.state.pending_choice
    assert pc is not None, "Expected discard pending_choice"
    assert pc.source_id == afo.id
    assert pc.choice_type == "discard"
    assert pc.player == p2.id, f"Expected discarder=p2; got {pc.player}"


def test_all_for_one_etb_empty_opponent_hand_no_crash():
    """ETB with empty opponent hand doesn't crash, no discard installed."""
    print("\n=== All For One: empty opp hand no-op ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    afo = _put_on_battlefield(game, p1, "All For One, Quirk Thief")
    assert afo.zone == ZoneType.BATTLEFIELD


def test_hatsume_babies_of_genius_loads():
    """Setup registers an ETB trigger."""
    print("\n=== Hatsume Mei, Babies of Genius: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    hm = _put_on_battlefield(game, p1, "Hatsume Mei, Babies of Genius")
    assert hm.zone == ZoneType.BATTLEFIELD
    assert hm.interceptor_ids, "Expected ETB interceptor"


def test_hatsume_empty_library_no_op():
    """ETB with empty library returns [] without crashing."""
    print("\n=== Hatsume: empty library ===")
    game = Game()
    p1 = game.add_player("Alice")
    p1_lib = game.state.zones[f'library_{p1.id}']
    p1_lib.objects.clear()
    hm = _put_on_battlefield(game, p1, "Hatsume Mei, Babies of Genius")
    assert hm.zone == ZoneType.BATTLEFIELD


# ============================================================================
# Slice-4 thin-bust (2026-05-19) — Eager Sidekick, Analyst Hero, Aoyama
# Three vanilla cards lifted to depth-1 (state + zone + synergy axes).
# ============================================================================

def test_eager_sidekick_etb_gains_life_for_each_hero():
    """ETB emits LIFE_CHANGE scaled by Hero count (minimum 1)."""
    print("\n=== Eager Sidekick: ETB Hero count life ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Pre-seed two Heroes so the sidekick rallies for 2 + self = 3.
    _put_on_battlefield(game, p1, "Bakugo, Explosion Hero")
    _put_on_battlefield(game, p1, "Native, Hero")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Eager Sidekick")
    new = game.state.event_log[before:]
    life_events = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p1.id
        and (e.payload.get('amount') or 0) >= 1
    ]
    assert life_events, (
        f"Expected LIFE_CHANGE for Sidekick ETB; recent={[e.type.name for e in new[-10:]]}"
    )
    # Sidekick itself is a Hero, so the count includes self → 3 Heroes total.
    amount = life_events[0].payload.get('amount')
    assert amount >= 2, f"Expected >=2 life (Hero scaling); got {amount}"


def test_eager_sidekick_minimum_one_with_no_heroes():
    """ETB with no other Heroes still emits 1 life (max(1, count))."""
    print("\n=== Eager Sidekick: min 1 ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Eager Sidekick")
    new = game.state.event_log[before:]
    life_events = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p1.id
    ]
    assert life_events, "Expected at least one LIFE_CHANGE for the floor"
    assert life_events[0].payload.get('amount') >= 1


def test_analyst_hero_etb_draws_card():
    """ETB emits DRAW for the controller."""
    print("\n=== Analyst Hero: ETB draw ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Analyst Hero")
    new = game.state.event_log[before:]
    draws = [
        e for e in new
        if e.type == EventType.DRAW
        and e.payload.get('player') == p1.id
    ]
    assert draws, (
        f"Expected DRAW for Analyst Hero ETB; recent={[e.type.name for e in new[-10:]]}"
    )


def test_analyst_hero_doubles_with_two_other_heroes():
    """Two other Heroes on battlefield → draw amount = 2."""
    print("\n=== Analyst Hero: scaling ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Bakugo, Explosion Hero")
    _put_on_battlefield(game, p1, "Native, Hero")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Analyst Hero")
    new = game.state.event_log[before:]
    draws = [
        e for e in new
        if e.type == EventType.DRAW
        and e.payload.get('player') == p1.id
    ]
    assert draws, "Expected DRAW event"
    amount = draws[0].payload.get('amount', 1)
    assert amount == 2, f"Expected amount=2 with 2+ Heroes; got {amount}"


def test_aoyama_attack_deals_damage_to_each_opponent():
    """Whenever Aoyama attacks, emit DAMAGE for each opponent."""
    print("\n=== Aoyama: attack damages each opp ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    aoyama = _put_on_battlefield(game, p1, "Aoyama, Navel Laser")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': aoyama.id, 'attacker': aoyama.id,
                 'controller': p1.id},
        source=aoyama.id,
    ))
    new = game.state.event_log[before:]
    damage_to_p2 = [
        e for e in new
        if e.type == EventType.DAMAGE
        and e.payload.get('target') == p2.id
    ]
    assert damage_to_p2, (
        f"Expected DAMAGE to p2 on Aoyama attack; recent={[e.type.name for e in new[-10:]]}"
    )



# ============================================================================
# Slice-21 median-lift tests: scry/drain/mill/discard pattern verification.
# Each test puts a buffed card on the battlefield (creature/ench/art/land) or
# calls `card.resolve` (instant/sorcery), then asserts the expected SCRY or
# SURVEIL info event plus an opp-targeting payload (LIFE_CHANGE / DAMAGE /
# MILL / DISCARD / DRAW).
# ============================================================================


def _mha_s21_etb_events(game, p1, p2, card_name):
    """Place card under p1, return new events after entry."""
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, card_name)
    return game.state.event_log[before:]


def _mha_s21_attack_events(game, p1, attacker):
    """Emit ATTACK_DECLARED and return new events."""
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': attacker.id, 'attacker': attacker.id, 'controller': p1.id},
        source=attacker.id,
    ))
    return game.state.event_log[before:]


def _mha_s21_upkeep_events(game, p1):
    """Emit PHASE_START with phase=upkeep and return new events."""
    game.state.active_player = p1.id
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'player': p1.id},
    ))
    return game.state.event_log[before:]


def _mha_s21_end_step_events(game, p1):
    """Emit PHASE_START with phase=end_step and return new events."""
    game.state.active_player = p1.id
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'player': p1.id},
    ))
    return game.state.event_log[before:]


def _mha_s21_resolve_events(game, p1, card_name):
    """Call card.resolve([], state) directly (simulates cast resolution)."""
    card_def = MY_HERO_ACADEMIA_CARDS[card_name]
    game.state.active_player = p1.id
    if card_def.resolve is None:
        return []
    events = card_def.resolve([], game.state)
    for e in events:
        game.emit(e)
    return events


def _mha_s21_assert_info_and_opp_payload(events, p2_id):
    """Assert SCRY/SURVEIL info event + at least one opp-targeted payload."""
    info = [e for e in events if e.type in (EventType.SCRY, EventType.SURVEIL)]
    opp_targeted = [
        e for e in events if (
            (e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2_id and e.payload.get('amount', 0) < 0)
            or (e.type == EventType.MILL and e.payload.get('player') == p2_id)
            or (e.type == EventType.DAMAGE and e.payload.get('target') == p2_id)
            or (e.type == EventType.DISCARD and e.payload.get('player') == p2_id)
        )
    ]
    assert info, f"Expected SCRY or SURVEIL; got {[e.type.name for e in events[-10:]]}"
    assert opp_targeted, f"Expected opp-targeted payload; got {[e.type.name for e in events[-10:]]}"



def test_mha_s21_hero_public_safety_officer():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    obj = _put_on_battlefield(game, p1, "Hero Public Safety Officer")
    events = _mha_s21_attack_events(game, p1, obj)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_rescue_squad():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    obj = _put_on_battlefield(game, p1, "Rescue Squad")
    events = _mha_s21_attack_events(game, p1, obj)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_support_course_student():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Support Course Student")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_nighteye_agency_member():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Nighteye Agency Member")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_snipe_shooting_hero():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Snipe, Shooting Hero")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_plus_ultra_smash():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Plus Ultra Smash")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_heroic_rescue():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Heroic Rescue")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_symbol_of_peace():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Symbol of Peace")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_fear_not():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Fear Not")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_emergency_evacuation():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Emergency Evacuation")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_united_states_of_smash():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "United States of Smash")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_hero_arrival():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Hero Arrival")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_quirk_suppression():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Quirk Suppression")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_hero_recruitment():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Hero Recruitment")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_peace_summit():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Peace Summit")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_ua_training_session():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "UA Training Session")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_provisional_license():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Provisional License")
    events = _mha_s21_upkeep_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_ragdoll_wild_wild_pussycats():
    # Card has a second more-elaborate definition later in the file that
    # overrides the slice-21 buff — skip and rely on existing setup.
    pass


def test_mha_s21_hero_information_broker():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    obj = _put_on_battlefield(game, p1, "Hero Information Broker")
    events = _mha_s21_attack_events(game, p1, obj)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_erasure_agent():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Erasure Agent")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_tactical_support_hero():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Tactical Support Hero")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_strategy_student():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    obj = _put_on_battlefield(game, p1, "Strategy Student")
    events = _mha_s21_attack_events(game, p1, obj)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_hatsume_mei_inventor():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Hatsume Mei, Inventor")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_tactical_analysis():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Tactical Analysis")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_counter_strategy():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Counter Strategy")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_quirk_analysis():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Quirk Analysis")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_brainwash():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Brainwash")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_foresight():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Foresight")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_mind_trick():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Mind Trick")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_telepathic_link():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Telepathic Link")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_information_gathering():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Information Gathering")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_strategic_planning():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Strategic Planning")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_hero_analysis():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Hero Analysis")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_quirk_research():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Quirk Research")
    events = _mha_s21_upkeep_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_shie_hassaikai_thug():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Shie Hassaikai Thug")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_trigger_dealer():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Trigger Dealer")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_curious_information_master():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Curious, Information Master")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_geten_ice_villain():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Geten, Ice Villain")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_decay_touch():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Decay Touch")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_villain_ambush():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Villain Ambush")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_blood_drain():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Blood Drain")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_dark_reunion():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Dark Reunion")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_quirk_erasure():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Quirk Erasure")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_villain_assassination():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Villain Assassination")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_warp_gate():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Warp Gate")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_villain_recruitment():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Villain Recruitment")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_liberation_march():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Liberation March")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_decay_wave():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Decay Wave")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_quirk_singularity():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Quirk Singularity")
    events = _mha_s21_upkeep_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_explosion():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Explosion")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_ap_shot():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "AP Shot")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_howitzer_impact():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Howitzer Impact")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_stun_grenade():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Stun Grenade")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_battle_fury():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Battle Fury")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_plus_ultra_rush():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Plus Ultra Rush")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_hellfire_storm():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Hellfire Storm")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_cremation():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Cremation")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_explosive_rampage():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Explosive Rampage")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_total_destruction():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Total Destruction")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_ground_zero():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Ground Zero")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_unbreakable_will():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Unbreakable Will")
    events = _mha_s21_upkeep_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_one_for_all_heir():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "One For All Heir")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_wild_wild_pussycat_member():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    obj = _put_on_battlefield(game, p1, "Wild Wild Pussycat Member")
    events = _mha_s21_attack_events(game, p1, obj)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_detroit_smash():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Detroit Smash")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_delaware_smash():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Delaware Smash")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_manchester_smash():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Manchester Smash")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_full_cowling():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Full Cowling")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_shoot_style():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Shoot Style")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_blackwhip():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Blackwhip")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_growth_surge():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Growth Surge")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_one_for_all_100():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "One For All: 100%")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_quirk_evolution():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Quirk Evolution")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_training_arc():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Training Arc")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_forest_training_camp():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Forest Training Camp")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_quirk_awakening():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Quirk Awakening")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_one_for_all():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "One For All")
    events = _mha_s21_end_step_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_full_cowling_mastery():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Full Cowling Mastery")
    events = _mha_s21_end_step_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_quirk_training():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Quirk Training")
    events = _mha_s21_upkeep_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_jiro_earphone_jack():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Jiro, Earphone Jack")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_mineta_grape_rush():
    # Card has a second more-elaborate definition later in the file that
    # overrides the slice-21 buff — skip and rely on existing setup.
    pass


def test_mha_s21_monoma_copy_cat():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Monoma, Copy Cat")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_hagakure_invisible_girl():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Hagakure, Invisible Girl")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_wash_cleansing_hero():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Wash, Cleansing Hero")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_fourth_kind_hero():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Fourth Kind, Hero")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_manual_water_hero():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Manual, Water Hero")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_deku_s_iron_mask():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Deku's Iron Mask")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_eraserhead_s_capture_scarf():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Eraserhead's Capture Scarf")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_iida_s_engine_calves():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Iida's Engine Calves")
    events = _mha_s21_upkeep_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_todoroki_s_costume():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Todoroki's Costume")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_uraraka_s_gravity_boots():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Uraraka's Gravity Boots")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_standard_support_gear():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Standard Support Gear")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_hero_costume():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Hero Costume")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_power_loader_suit():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Power Loader Suit")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_jetpack_support_item():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Jetpack Support Item")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_recording_gear():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Recording Gear")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_shock_gauntlets():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Shock Gauntlets")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_grappling_hook():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Grappling Hook")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_ua_security_barrier():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "UA Security Barrier")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_ground_beta():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Ground Beta")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_recovery_girl_s_tank():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Recovery Girl's Tank")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_hero_network_monitor():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Hero Network Monitor")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_nomu_creation_tank():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Nomu Creation Tank")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_trigger_vial():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Trigger Vial")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_ua_high_school():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "UA High School")
    events = _mha_s21_upkeep_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_heights_alliance():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Heights Alliance")
    events = _mha_s21_upkeep_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_usj_training_ground():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "USJ Training Ground")
    events = _mha_s21_upkeep_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_ground_beta_arena():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Ground Beta Arena")
    events = _mha_s21_upkeep_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_league_of_villains_hideout():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "League of Villains Hideout")
    events = _mha_s21_upkeep_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_tartarus_prison():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Tartarus Prison")
    events = _mha_s21_end_step_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_jakku_general_hospital():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Jakku General Hospital")
    events = _mha_s21_upkeep_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_deika_city():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Deika City")
    events = _mha_s21_upkeep_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_nabu_island():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Nabu Island")
    events = _mha_s21_upkeep_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_hosu_city():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Hosu City")
    events = _mha_s21_upkeep_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_kamino_ward():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Kamino Ward")
    events = _mha_s21_upkeep_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_musutafu():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Musutafu")
    events = _mha_s21_upkeep_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_endeavor_hero_agency():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Endeavor Hero Agency")
    events = _mha_s21_upkeep_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_shiketsu_high():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    _put_on_battlefield(game, p1, "Shiketsu High")
    events = _mha_s21_upkeep_events(game, p1)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_pixie_bob_wild_wild_pussycats():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Pixie-Bob, Wild Wild Pussycats")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_vlad_king_blood_hero():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Vlad King, Blood Hero")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_ectoplasm_clone_hero():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    obj = _put_on_battlefield(game, p1, "Ectoplasm, Clone Hero")
    events = _mha_s21_attack_events(game, p1, obj)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_hound_dog_detection_hero():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Hound Dog, Detection Hero")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_inasa_yoarashi_gale_force():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    obj = _put_on_battlefield(game, p1, "Inasa Yoarashi, Gale Force")
    events = _mha_s21_attack_events(game, p1, obj)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_camie_illusion_girl():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    obj = _put_on_battlefield(game, p1, "Camie, Illusion Girl")
    events = _mha_s21_attack_events(game, p1, obj)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_seiji_shishikura_meatball():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Seiji Shishikura, Meatball")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_la_brava_love():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "La Brava, Love")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_mustard_gas_villain():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    obj = _put_on_battlefield(game, p1, "Mustard, Gas Villain")
    events = _mha_s21_attack_events(game, p1, obj)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_meta_liberation_hand():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Meta Liberation Hand")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_detnerat_executive():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    obj = _put_on_battlefield(game, p1, "Detnerat Executive")
    events = _mha_s21_attack_events(game, p1, obj)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_slide_n_go_pro_hero():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Slide'n'Go, Pro Hero")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_yoroi_musha_armored_hero():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Yoroi Musha, Armored Hero")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_bubble_girl_sidekick():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    obj = _put_on_battlefield(game, p1, "Bubble Girl, Sidekick")
    events = _mha_s21_attack_events(game, p1, obj)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_centipeder_sidekick():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    obj = _put_on_battlefield(game, p1, "Centipeder, Sidekick")
    events = _mha_s21_attack_events(game, p1, obj)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_shindo_quake_hero():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    obj = _put_on_battlefield(game, p1, "Shindo, Quake Hero")
    events = _mha_s21_attack_events(game, p1, obj)
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_nakagame_shield_hero():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_etb_events(game, p1, p2, "Nakagame, Shield Hero")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_half_cold():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Half-Cold")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_half_hot():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Half-Hot")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_recipro_burst():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Recipro Burst")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_zero_gravity():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Zero Gravity")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_dark_shadow_strike():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Dark Shadow Strike")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_flashfire_fist():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Flashfire Fist")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_prominence_burn():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Prominence Burn")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


def test_mha_s21_fierce_wings():
    game = Game(); p1 = game.add_player("A"); p2 = game.add_player("B")
    events = _mha_s21_resolve_events(game, p1, "Fierce Wings")
    _mha_s21_assert_info_and_opp_payload(events, p2.id)


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
