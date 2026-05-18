"""
Naruto Spice Pass Tests (Phase A1) — 2026-05-18

Validates the format-defining cards added in the spice-pass-W23 NRT pass.
Mirrors the test_zelda_spice.py shape (gotcha #18 — worktree-portable
sys.path).

Cards covered (Phase A1):
- Sharingan Eye (NEW equipment — +2/+2, lifelink, ward {1})
- Naruto, Sage of Six Paths (NEW build-around mythic — TB synergy)
- Kurama Sealed, Nine-Tail Avatar (NEW assembly mythic — gated on TB count)
- Sasuke Uchiha, Eternal Mangekyo (NEW compression mythic — removal + ping)
- Chunin Exams Tournament (NEW Saga — Ninja tribal package)
- Tenten, Weapons Master (REWIRE — Equipment cost reduction)
- A, Fourth Raikage (REWIRE — Lightning Armor hexproof on your turn)
- Mei Terumi, Fifth Mizukage (REWIRE — Boil Style attack trigger)
"""

import os
import sys

# Compute repo root from this file's location so the test runs from any
# checkout (main or a `.claude/worktrees/agent-*/` worktree). See
# spice-pass.md gotcha #18.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness,
)
from src.engine.queries import has_ability
from src.cards.custom.naruto import NARUTO_CARDS


def _put_on_battlefield(game, player, card_name):
    """Mirror the Star Wars / Zelda spice test harness."""
    card_def = NARUTO_CARDS[card_name]
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
# Sharingan Eye (NEW equipment)
# ============================================================================

def test_sharingan_eye_loads():
    """make_equipment_setup registers PT-mod + lifelink keyword + ward."""
    print("\n=== Sharingan Eye: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    eye = _put_on_battlefield(game, p1, "Sharingan Eye")
    assert eye.zone == ZoneType.BATTLEFIELD
    activated = getattr(eye.state, 'activated_abilities', None)
    assert activated, "Expected equip activated ability on Sharingan Eye"
    # Expect PT + keyword + ward listeners
    assert len(eye.interceptor_ids) >= 2, (
        f"Expected at least PT + ward interceptors; got {len(eye.interceptor_ids)}"
    )


def test_sharingan_eye_attach_pt_and_lifelink():
    """After ATTACH, equipped creature reads +2/+2 and has lifelink."""
    print("\n=== Sharingan Eye: +2/+2 + lifelink on attach ===")
    game = Game()
    p1 = game.add_player("Alice")
    eye = _put_on_battlefield(game, p1, "Sharingan Eye")
    sasuke_avenger = _put_on_battlefield(game, p1, "Sasuke Uchiha, Avenger")
    base_p = get_power(sasuke_avenger, game.state)
    base_t = get_toughness(sasuke_avenger, game.state)
    assert not has_ability(sasuke_avenger, "lifelink", game.state)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': eye.id, 'target_id': sasuke_avenger.id},
        source=eye.id,
    ))

    new_p = get_power(sasuke_avenger, game.state)
    new_t = get_toughness(sasuke_avenger, game.state)
    assert new_p == base_p + 2, f"Expected +2 power: {base_p}->{new_p}"
    assert new_t == base_t + 2, f"Expected +2 toughness: {base_t}->{new_t}"
    assert has_ability(sasuke_avenger, "lifelink", game.state), (
        "Expected lifelink after attach"
    )
    print(f"  Sasuke: {base_p}/{base_t} -> {new_p}/{new_t}, lifelink granted")


# ============================================================================
# Naruto, Sage of Six Paths (NEW build-around)
# ============================================================================

def test_naruto_six_paths_loads():
    print("\n=== Naruto, Sage of Six Paths: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    n = _put_on_battlefield(game, p1, "Naruto, Sage of Six Paths")
    assert n.zone == ZoneType.BATTLEFIELD
    assert has_ability(n, "trample", game.state)
    assert has_ability(n, "haste", game.state)
    # Expect: self-kw + 3 triggers (etb-untap, tb-etb-trig, tb-attack-trig).
    assert len(n.interceptor_ids) >= 3, (
        f"Expected keyword + 3 triggers; got {len(n.interceptor_ids)}"
    )


def test_naruto_six_paths_etb_untaps_tailed_beasts():
    """ETB emits UNTAP events for each Tailed Beast you control."""
    print("\n=== Naruto Six Paths: ETB untaps TBs ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Pre-stage two Tailed Beasts on the battlefield.
    kokuo = _put_on_battlefield(game, p1, "Kokuo, Five-Tails")
    saiken = _put_on_battlefield(game, p1, "Saiken, Six-Tails")

    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Naruto, Sage of Six Paths")
    new = game.state.event_log[before:]
    untaps = [
        e for e in new
        if e.type == EventType.UNTAP
        and e.payload.get('object_id') in {kokuo.id, saiken.id}
    ]
    # Should hit BOTH Tailed Beasts (not Naruto himself).
    untap_targets = {e.payload['object_id'] for e in untaps}
    assert kokuo.id in untap_targets, "Expected UNTAP for Kokuo"
    assert saiken.id in untap_targets, "Expected UNTAP for Saiken"


def test_naruto_six_paths_no_self_untap():
    """ETB does NOT emit UNTAP for self even though Naruto isn't a TB."""
    print("\n=== Naruto Six Paths: no self-untap ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    n = _put_on_battlefield(game, p1, "Naruto, Sage of Six Paths")
    new = game.state.event_log[before:]
    self_untaps = [e for e in new
                   if e.type == EventType.UNTAP
                   and e.payload.get('object_id') == n.id]
    assert not self_untaps, "Naruto shouldn't untap himself (he's not TB)"


def test_naruto_six_paths_tb_etb_triggers_draw():
    """When another Tailed Beast enters under your control, draw a card."""
    print("\n=== Naruto Six Paths: TB-ETB -> draw ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Naruto, Sage of Six Paths")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Kokuo, Five-Tails")
    new = game.state.event_log[before:]
    draws = [e for e in new
             if e.type == EventType.DRAW
             and e.payload.get('player') == p1.id]
    assert draws, (
        f"Expected a DRAW after Tailed Beast ETB; recent={_emitted_types(game)[-12:]}"
    )


def test_naruto_six_paths_opp_tb_no_draw():
    """Opponent ETB'ing a Tailed Beast does NOT trigger our draw."""
    print("\n=== Naruto Six Paths: opp TB -> no draw ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Naruto, Sage of Six Paths")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p2, "Kokuo, Five-Tails")
    new = game.state.event_log[before:]
    p1_draws = [e for e in new
                if e.type == EventType.DRAW
                and e.payload.get('player') == p1.id]
    assert not p1_draws, "Naruto shouldn't draw off opp's TB ETB"


# ============================================================================
# Kurama Sealed, Nine-Tail Avatar (NEW assembly mythic)
# ============================================================================

def test_kurama_sealed_loads():
    print("\n=== Kurama Sealed: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    k = _put_on_battlefield(game, p1, "Kurama Sealed, Nine-Tail Avatar")
    assert k.zone == ZoneType.BATTLEFIELD
    assert has_ability(k, "trample", game.state)
    assert has_ability(k, "haste", game.state)


def test_kurama_sealed_etb_scales_with_tb_count():
    """ETB emits 2*N COUNTER_ADDED for N other Tailed Beasts."""
    print("\n=== Kurama Sealed: ETB counters scale ===")
    game = Game()
    p1 = game.add_player("Alice")
    # 2 TBs already present.
    _put_on_battlefield(game, p1, "Kokuo, Five-Tails")
    _put_on_battlefield(game, p1, "Saiken, Six-Tails")
    before = len(game.state.event_log)
    k = _put_on_battlefield(game, p1, "Kurama Sealed, Nine-Tail Avatar")
    new = game.state.event_log[before:]
    counters = [e for e in new
                if e.type == EventType.COUNTER_ADDED
                and e.payload.get('object_id') == k.id
                and e.payload.get('counter_type') == '+1/+1']
    # 2 TBs × 2 counters each = 4 counter events.
    assert len(counters) == 4, (
        f"Expected 4 +1/+1 counter events with 2 other TBs; got {len(counters)}"
    )


def test_kurama_sealed_no_etb_counters_solo():
    """ETB with no other TBs emits 0 counters (Kurama enters as 0/0)."""
    print("\n=== Kurama Sealed: solo ETB no counters ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    k = _put_on_battlefield(game, p1, "Kurama Sealed, Nine-Tail Avatar")
    new = game.state.event_log[before:]
    counters = [e for e in new
                if e.type == EventType.COUNTER_ADDED
                and e.payload.get('object_id') == k.id
                and e.payload.get('counter_type') == '+1/+1']
    assert not counters, (
        f"Expected NO counters with 0 other TBs; got {len(counters)}"
    )


def test_kurama_sealed_attack_dmg_gated_on_3_tbs():
    """Attack with 3+ TBs deals damage = power to each opponent."""
    print("\n=== Kurama Sealed: gated attack damage ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # 2 TBs already on the field — Kurama Sealed (self) makes 3.
    _put_on_battlefield(game, p1, "Kokuo, Five-Tails")
    _put_on_battlefield(game, p1, "Saiken, Six-Tails")
    k = _put_on_battlefield(game, p1, "Kurama Sealed, Nine-Tail Avatar")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': k.id, 'attacker': k.id, 'controller': p1.id},
        source=k.id,
    ))
    after_events = game.state.event_log[before:]
    dmg = [e for e in after_events
           if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id
           and e.payload.get('source') == k.id]
    assert dmg, (
        f"Expected DAMAGE to p2 on attack; recent={[e.type.name for e in after_events[-10:]]}"
    )
    # Power should be 4 (2 TBs × 2 counters = 4 counters → 0/0 + 4/4 = 4/4).
    assert dmg[-1].payload.get('amount', 0) >= 1


def test_kurama_sealed_attack_no_damage_solo():
    """Attack with only 1 TB (self) does NOT trigger beast storm."""
    print("\n=== Kurama Sealed: solo attack -> no storm ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    k = _put_on_battlefield(game, p1, "Kurama Sealed, Nine-Tail Avatar")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': k.id, 'attacker': k.id, 'controller': p1.id},
        source=k.id,
    ))
    after_events = game.state.event_log[before:]
    dmg = [e for e in after_events
           if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id
           and e.payload.get('source') == k.id]
    assert not dmg, (
        f"Beast storm fired with only 1 TB (self); got {len(dmg)} dmg events"
    )


# ============================================================================
# Sasuke Uchiha, Eternal Mangekyo (NEW compression)
# ============================================================================

def test_sasuke_mangekyo_loads():
    print("\n=== Sasuke Mangekyo: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    s = _put_on_battlefield(game, p1, "Sasuke Uchiha, Eternal Mangekyo")
    assert s.zone == ZoneType.BATTLEFIELD
    assert s.interceptor_ids, "Should register ETB + spell-cast triggers"


def test_sasuke_mangekyo_etb_damages_biggest_opp():
    """ETB emits DAMAGE 3 to the largest opposing creature."""
    print("\n=== Sasuke Mangekyo: ETB removal ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    big = _put_on_battlefield(game, p2, "Gamabunta, Toad Boss")
    small = _put_on_battlefield(game, p2, "Konoha Genin")

    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Sasuke Uchiha, Eternal Mangekyo")
    new = game.state.event_log[before:]
    dmg = [e for e in new
           if e.type == EventType.DAMAGE
           and e.payload.get('target') in {big.id, small.id}
           and e.payload.get('amount') == 3]
    assert dmg, "Expected ETB damage to opposing creature"
    # Should target the biggest (Gamabunta 7/7, not Konoha Genin 2/2).
    assert dmg[0].payload['target'] == big.id, (
        f"Expected target Gamabunta (biggest); got {dmg[0].payload['target']}"
    )


def test_sasuke_mangekyo_noncreature_pings_opps():
    """Casting a noncreature spell pings each opponent for 1."""
    print("\n=== Sasuke Mangekyo: noncreature -> ping ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Sasuke Uchiha, Eternal Mangekyo")
    before = len(game.state.event_log)
    # Simulate casting an instant we control.
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={
            'caster': p1.id,
            'spell_id': 'noncreature_spell',
            'types': [CardType.INSTANT],
        },
    ))
    new = game.state.event_log[before:]
    pings = [e for e in new
             if e.type == EventType.DAMAGE
             and e.payload.get('target') == p2.id
             and e.payload.get('amount') == 1
             and e.payload.get('source') is not None]
    assert pings, (
        f"Expected ping to p2; recent={[e.type.name for e in new[-10:]]}"
    )


def test_sasuke_mangekyo_creature_spell_no_ping():
    """Casting a creature spell does NOT trigger the ping."""
    print("\n=== Sasuke Mangekyo: creature -> no ping ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    sas = _put_on_battlefield(game, p1, "Sasuke Uchiha, Eternal Mangekyo")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={
            'caster': p1.id,
            'spell_id': 'creature_spell',
            'types': [CardType.CREATURE],
        },
    ))
    new = game.state.event_log[before:]
    pings_from_sasuke = [
        e for e in new
        if e.type == EventType.DAMAGE
        and e.payload.get('target') == p2.id
        and e.payload.get('amount') == 1
        and e.payload.get('source') == sas.id
    ]
    assert not pings_from_sasuke, "Creature spell should NOT trigger Sasuke ping"


# ============================================================================
# Chunin Exams Tournament (NEW saga)
# ============================================================================

def test_chunin_exams_loads_saga():
    print("\n=== Chunin Exams Tournament: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Chunin Exams Tournament")
    assert saga.interceptor_ids, "Expected saga chapter interceptors"


def test_chunin_exams_chapter_i_creates_two_ninjas():
    """Direct chapter-I dispatch emits CREATE_TOKEN x2 with subtype Ninja."""
    print("\n=== Chunin Exams: chapter I ===")
    from src.cards.custom.naruto import _chunin_exams_chapter_i
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Chunin Exams Tournament")
    events = _chunin_exams_chapter_i(saga, game.state)
    tokens = [
        e for e in events
        if e.type == EventType.CREATE_TOKEN
        and 'Ninja' in (e.payload.get('token', {}).get('subtypes', set()))
    ]
    assert len(tokens) == 2, f"Expected 2 Ninja tokens; got {len(tokens)}"


def test_chunin_exams_chapter_ii_anthems_only_ninjas():
    """Chapter II buffs only Ninja creatures you control, not the saga itself."""
    print("\n=== Chunin Exams: chapter II ===")
    from src.cards.custom.naruto import _chunin_exams_chapter_ii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Chunin Exams Tournament")
    ninja = _put_on_battlefield(game, p1, "Konoha Genin")
    non_ninja = _put_on_battlefield(game, p1, "Gamabunta, Toad Boss")

    events = _chunin_exams_chapter_ii(saga, game.state)
    targets = [e.payload['object_id'] for e in events
               if e.type == EventType.PT_MODIFICATION]
    assert ninja.id in targets, (
        f"Konoha Genin (Ninja) not buffed: targets={targets}"
    )
    assert non_ninja.id not in targets, (
        f"Gamabunta (non-Ninja) wrongly buffed: targets={targets}"
    )
    assert saga.id not in targets, (
        f"Saga should not buff itself: targets={targets}"
    )


def test_chunin_exams_chapter_iii_tutors_low_mv_ninja():
    """Chapter III emits SEARCH_LIBRARY for Ninja creature MV<=3."""
    print("\n=== Chunin Exams: chapter III ===")
    from src.cards.custom.naruto import _chunin_exams_chapter_iii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Chunin Exams Tournament")
    events = _chunin_exams_chapter_iii(saga, game.state)
    assert events and events[0].type == EventType.SEARCH_LIBRARY
    p = events[0].payload
    assert p.get('subtype') == 'Ninja'
    assert p.get('card_type') == 'creature'
    assert p.get('mana_value_max') == 3
    assert p.get('enters_tapped') is True
    assert p.get('destination') == 'battlefield'


# ============================================================================
# Tenten, Weapons Master (REWIRE)
# ============================================================================

def test_tenten_loads_with_first_strike():
    print("\n=== Tenten: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    t = _put_on_battlefield(game, p1, "Tenten, Weapons Master")
    assert t.zone == ZoneType.BATTLEFIELD
    assert has_ability(t, "first strike", game.state), (
        "Tenten should have first strike from self-grant"
    )


def test_tenten_reduces_equipment_spell_cost():
    """Tenten's interceptor reduces effective cost of an Equipment card by 1.

    Uses the canonical cost_query API rather than reading raw QUERY_COST
    events from emit() — the cost system uses get_effective_mana_cost as
    its public surface; raw QUERY_COST events bypass the reduction pipeline.
    """
    print("\n=== Tenten: cost reduction for Equipment ===")
    from src.engine.cost_query import get_effective_mana_cost
    from src.engine.mana import ManaCost
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Tenten, Weapons Master")
    # Kunai is an Equipment with printed cost {1}.
    kunai_def = NARUTO_CARDS["Kunai"]
    kunai = game.create_object(
        name="Kunai",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=kunai_def.characteristics,
        card_def=None,
    )
    kunai.card_def = kunai_def

    base = ManaCost.parse(kunai_def.characteristics.mana_cost or "")
    # Effective cost should be reduced by 1 (clamped at 0).
    eff = get_effective_mana_cost(kunai, p1.id, game.state, base_cost=base)
    assert eff.generic == max(0, base.generic - 1), (
        f"Expected Kunai cost reduced from {base.to_string()} by 1; "
        f"got {eff.to_string()}"
    )
    # And total mana value should drop by exactly 1.
    assert eff.mana_value == max(0, base.mana_value - 1), (
        f"Expected MV reduction by 1; base={base.mana_value} eff={eff.mana_value}"
    )


def test_tenten_no_reduction_on_non_equipment():
    """Tenten does NOT reduce cost for a non-Equipment spell."""
    print("\n=== Tenten: no reduction on non-Equipment ===")
    from src.engine.cost_query import get_effective_mana_cost
    from src.engine.mana import ManaCost
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Tenten, Weapons Master")
    # Konoha Genin = creature, not equipment, printed cost {1}{W}.
    genin_def = NARUTO_CARDS["Konoha Genin"]
    genin = game.create_object(
        name="Konoha Genin",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=genin_def.characteristics,
        card_def=None,
    )
    genin.card_def = genin_def

    base = ManaCost.parse(genin_def.characteristics.mana_cost or "")
    eff = get_effective_mana_cost(genin, p1.id, game.state, base_cost=base)
    # No reduction: generic and total MV should match printed.
    assert eff.generic == base.generic, (
        f"Tenten should not reduce non-Equipment; "
        f"printed={base.to_string()} effective={eff.to_string()}"
    )
    assert eff.mana_value == base.mana_value


# ============================================================================
# A, Fourth Raikage (REWIRE)
# ============================================================================

def test_a_fourth_raikage_loads_with_haste_first_strike():
    print("\n=== A, Fourth Raikage: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    a = _put_on_battlefield(game, p1, "A, Fourth Raikage")
    assert a.zone == ZoneType.BATTLEFIELD
    assert has_ability(a, "haste", game.state), "Expected haste"
    assert has_ability(a, "first strike", game.state), "Expected first strike"


def test_a_fourth_raikage_hexproof_on_your_turn():
    """Lightning Armor: hexproof when active_player == controller."""
    print("\n=== A, Fourth Raikage: hexproof on your turn ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    a = _put_on_battlefield(game, p1, "A, Fourth Raikage")
    # During your turn.
    game.state.active_player = p1.id
    assert has_ability(a, "hexproof", game.state), (
        "Expected hexproof while active_player == controller"
    )


def test_a_fourth_raikage_no_hexproof_on_opp_turn():
    """Lightning Armor off during opponent's turn."""
    print("\n=== A, Fourth Raikage: no hexproof on opp turn ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    a = _put_on_battlefield(game, p1, "A, Fourth Raikage")
    game.state.active_player = p2.id
    assert not has_ability(a, "hexproof", game.state), (
        "Should NOT have hexproof during opp turn"
    )


# ============================================================================
# Mei Terumi, Fifth Mizukage (REWIRE)
# ============================================================================

def test_mei_terumi_loads():
    print("\n=== Mei Terumi: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    m = _put_on_battlefield(game, p1, "Mei Terumi, Fifth Mizukage")
    assert m.interceptor_ids, "Should register an attack trigger"


def test_mei_terumi_attack_damages_opp_creatures():
    """Attack trigger emits DAMAGE 2 to each opp's creature."""
    print("\n=== Mei Terumi: Boil Style ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    opp_creature_1 = _put_on_battlefield(game, p2, "Konoha Genin")
    opp_creature_2 = _put_on_battlefield(game, p2, "Medical Ninja")
    own_creature = _put_on_battlefield(game, p1, "Konoha Genin")

    m = _put_on_battlefield(game, p1, "Mei Terumi, Fifth Mizukage")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': m.id, 'attacker': m.id, 'controller': p1.id},
        source=m.id,
    ))
    after_events = game.state.event_log[before:]
    dmg = [e for e in after_events
           if e.type == EventType.DAMAGE
           and e.payload.get('source') == m.id
           and e.payload.get('amount') == 2]
    targeted = {e.payload['target'] for e in dmg}
    assert opp_creature_1.id in targeted
    assert opp_creature_2.id in targeted
    assert own_creature.id not in targeted, (
        "Mei should NOT damage own creatures"
    )
    print(f"  Mei attacked. Damaged: {len(targeted)} opp creatures")


# ============================================================================
# Runner — module-direct so tests work without pytest config
# ============================================================================

def _run_all():
    import traceback
    tests = [v for k, v in globals().items()
             if k.startswith("test_") and callable(v)]
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
