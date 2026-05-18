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
