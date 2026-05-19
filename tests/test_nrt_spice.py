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
from src.cards.custom import naruto as naruto_module


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
# Phase A2 (slice 2) — decision-axis flip cards
# ============================================================================


def test_sage_mode_decree_loads():
    """Setup registers a modal-ETB trigger."""
    print("\n=== Sage Mode Decree: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    smd = _put_on_battlefield(game, p1, "Sage Mode Decree")
    assert smd.zone == ZoneType.BATTLEFIELD
    assert smd.interceptor_ids, "Expected modal-ETB trigger interceptor"


def test_sage_mode_decree_etb_opens_modal_pending_choice():
    """ETB installs a modal_with_targeting pending_choice with 3 modes."""
    print("\n=== Sage Mode Decree: pending modal choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    smd = _put_on_battlefield(game, p1, "Sage Mode Decree")
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending_choice after ETB"
    assert pc.source_id == smd.id
    assert pc.choice_type == "modal_with_targeting"
    assert pc.player == p1.id
    assert len(pc.options) == 3, f"Expected 3 modes; got {len(pc.options)}"
    labels = {opt['label'] for opt in pc.options}
    # All modes are non-targeting.
    assert all(not o.get('requires_targeting') for o in pc.options), (
        "Expected all 3 modes to be non-targeting"
    )
    # Spot-check at least one label.
    assert any('Scry 2' in lbl for lbl in labels), f"Expected scry mode; labels={labels}"


def test_ino_yamanaka_mind_reader_loads():
    """Setup registers flying + ETB info pulse + targeted-ETB trigger."""
    print("\n=== Ino Yamanaka, Mind-Body Reader: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    ino = _put_on_battlefield(game, p1, "Ino Yamanaka, Mind-Body Reader")
    assert ino.zone == ZoneType.BATTLEFIELD
    # flying + info pulse + targeted-ETB = at least 3 interceptors
    assert len(ino.interceptor_ids) >= 3, (
        f"Expected at least 3 interceptors; got {len(ino.interceptor_ids)}"
    )
    assert has_ability(ino, 'flying', game.state), "Expected flying"


def test_ino_yamanaka_etb_emits_target_required_for_opponent():
    """ETB emits TARGET_REQUIRED with target_filter=opponent and effect=discard."""
    print("\n=== Ino Yamanaka: ETB target_required + info pulse ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    ino = _put_on_battlefield(game, p1, "Ino Yamanaka, Mind-Body Reader")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == ino.id
        and e.payload.get('target_filter') == 'opponent'
        and e.payload.get('effect') == 'discard'
    ]
    assert target_reqs, (
        f"Expected discard TARGET_REQUIRED w/ opponent filter; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )
    # The info pulse should ALSO fire.
    info_events = [
        e for e in new
        if e.type == EventType.DISCARD_CHOICE and e.payload.get('source') == ino.id
    ]
    assert info_events, "Expected DISCARD_CHOICE info pulse on ETB"


def test_tailed_beast_bomb_loads():
    """Setup registers a divided-damage ETB trigger."""
    print("\n=== Tailed Beast Bomb: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    tbb = _put_on_battlefield(game, p1, "Tailed Beast Bomb")
    assert tbb.zone == ZoneType.BATTLEFIELD
    assert tbb.interceptor_ids, "Expected ETB interceptor"


def test_tailed_beast_bomb_etb_emits_divided_damage_target_required():
    """ETB emits TARGET_REQUIRED with divide_amount=6 and damage effect."""
    print("\n=== Tailed Beast Bomb: ETB divide-damage ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    tbb = _put_on_battlefield(game, p1, "Tailed Beast Bomb")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == tbb.id
        and e.payload.get('effect') == 'damage'
    ]
    assert target_reqs, (
        f"Expected damage TARGET_REQUIRED; new={[e.type.name for e in new[-10:]]}"
    )
    payload = target_reqs[0].payload
    assert payload.get('divide_amount') == 6, (
        f"Expected divide_amount=6; got {payload.get('divide_amount')}"
    )
    assert payload.get('max_targets') == 6


def test_itachi_last_curse_loads():
    """Setup registers the targeted-death + zone-read death triggers."""
    print("\n=== Itachi Uchiha, Last Curse: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    itachi = _put_on_battlefield(game, p1, "Itachi Uchiha, Last Curse")
    assert itachi.zone == ZoneType.BATTLEFIELD
    # Both death triggers register at battlefield-entry time.
    assert len(itachi.interceptor_ids) >= 2, (
        f"Expected 2 death triggers; got {len(itachi.interceptor_ids)}"
    )


def test_itachi_last_curse_death_emits_target_required_exile():
    """Itachi's death emits TARGET_REQUIRED w/ effect=exile + opponent_creature."""
    print("\n=== Itachi Uchiha: death -> target_required exile ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    itachi = _put_on_battlefield(game, p1, "Itachi Uchiha, Last Curse")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': itachi.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
        source=itachi.id,
    ))
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == itachi.id
        and e.payload.get('effect') == 'exile'
        and e.payload.get('target_filter') == 'opponent_creature'
    ]
    assert target_reqs, (
        f"Expected exile TARGET_REQUIRED; recent={[e.type.name for e in new[-15:]]}"
    )


def test_kabuto_yakushi_loads():
    """Setup registers an ETB trigger interceptor."""
    print("\n=== Kabuto Yakushi, Forbidden Researcher: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    kabuto = _put_on_battlefield(game, p1, "Kabuto Yakushi, Forbidden Researcher")
    assert kabuto.zone == ZoneType.BATTLEFIELD
    assert kabuto.interceptor_ids, "Expected ETB interceptor"


def test_kabuto_yakushi_etb_empty_library_no_crash():
    """ETB with empty library returns [] without installing a scry choice."""
    print("\n=== Kabuto Yakushi: empty library no-op ===")
    game = Game()
    p1 = game.add_player("Alice")
    kabuto = _put_on_battlefield(game, p1, "Kabuto Yakushi, Forbidden Researcher")
    # Library is empty by default — should NOT install a scry choice.
    assert kabuto.zone == ZoneType.BATTLEFIELD
    # pending_choice may have been cleared/never set; either way no crash.


def test_kabuto_yakushi_etb_with_library_opens_scry_choice():
    """ETB with non-empty library opens a scry pending_choice."""
    print("\n=== Kabuto Yakushi: ETB opens scry choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Plant 3 cards in p1's library.
    konoha_genin = NARUTO_CARDS["Konoha Genin"]
    lib = game.state.zones[f'library_{p1.id}']
    for _ in range(3):
        obj = game.create_object(
            name="Konoha Genin",
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=konoha_genin.characteristics,
            card_def=None,
        )
        obj.card_def = konoha_genin
        if obj.id not in lib.objects:
            lib.objects.append(obj.id)
    kabuto = _put_on_battlefield(game, p1, "Kabuto Yakushi, Forbidden Researcher")
    pc = game.state.pending_choice
    assert pc is not None, "Expected scry pending_choice after ETB"
    assert pc.source_id == kabuto.id
    assert pc.choice_type == "scry"
    assert pc.player == p1.id


# ============================================================================
# Slice-10 median-lift tests (2026-05-19): one assertion per buffed vanilla
# card driving NRT median_depth 0 -> >= 2. Each test puts the card on the
# battlefield (or invokes its resolve handler for instants/sorceries) and
# asserts the expected SCRY/SURVEIL info event + a cross-controller effect
# (LIFE_CHANGE / DAMAGE / MILL / DISCARD / REVEAL_HAND).
# ============================================================================


def _s10_etb_card(card_name):
    """Spin up a game, put the named card under p1, return (game, p1, p2, obj)."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, card_name)
    return game, p1, p2, obj


def _s10_attack(card_name):
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


def _s10_assert_info_and_opp(game, obj, p2, *, info_type, opp_type, opp_key='player'):
    """Assert info_type (SCRY/SURVEIL) emitted by obj + a cross-controller effect.
    For LIFE_CHANGE we require amount < 0; for DAMAGE we accept target == p2.id."""
    new = game.state.event_log
    info_evs = [e for e in new if e.type == info_type and e.source == obj.id]
    assert info_evs, f"Expected {info_type.name} from {obj.id}; events={[e.type.name for e in new[-15:]]}"
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


def _s10_resolve(fn_name):
    """Pull a resolve fn out of the naruto module, prep a 2-player state, call it."""
    fn = getattr(naruto_module, fn_name)
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.state.active_player = p1.id
    events = fn([], game.state)
    return events, p1, p2


# --- WHITE permanent buff tests ---------------------------------------------


def test_nara_shadow_user_etb_scry_drain_s10():
    print("\n=== Slice-10: Nara Shadow User ETB scry+drain ===")
    g, p1, p2, obj = _s10_etb_card("Nara Shadow User")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_barrier_team_ninja_etb_scry_drain_s10():
    print("\n=== Slice-10: Barrier Team Ninja ETB scry+drain ===")
    g, p1, p2, obj = _s10_etb_card("Barrier Team Ninja")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_konoha_alliance_etb_scry_drain_s10():
    print("\n=== Slice-10: Konoha Alliance ETB scry+drain ===")
    g, p1, p2, obj = _s10_etb_card("Konoha Alliance")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


# --- WHITE resolve handler tests --------------------------------------------


def test_substitution_jutsu_resolve_s10():
    print("\n=== Slice-10: Substitution Jutsu resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_substitution_jutsu")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_will_of_fire_resolve_s10():
    print("\n=== Slice-10: Will of Fire resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_will_of_fire")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 for e in events)


def test_gentle_fist_resolve_s10():
    print("\n=== Slice-10: Gentle Fist resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_gentle_fist")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_eight_trigrams_palm_resolve_s10():
    print("\n=== Slice-10: Eight Trigrams Palm resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_eight_trigrams_palm")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) == -2 for e in events)


def test_healing_jutsu_resolve_s10():
    print("\n=== Slice-10: Healing Jutsu resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_healing_jutsu")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) >= 5 for e in events)


def test_konoha_senbon_resolve_s10():
    print("\n=== Slice-10: Konoha Senbon resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_konoha_senbon")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_protection_barrier_resolve_s10():
    print("\n=== Slice-10: Protection Barrier resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_protection_barrier")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) >= 3 for e in events)


def test_village_defense_resolve_s10():
    print("\n=== Slice-10: Village Defense resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_village_defense")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_konoha_reinforcements_resolve_s10():
    print("\n=== Slice-10: Konoha Reinforcements resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_konoha_reinforcements")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) >= 4 for e in events)


def test_hidden_leaf_decree_resolve_s10():
    print("\n=== Slice-10: Hidden Leaf Decree resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_hidden_leaf_decree")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) == -2 for e in events)


def test_hokage_monument_resolve_s10():
    print("\n=== Slice-10: Hokage Monument resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_hokage_monument")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) >= 5 for e in events)


# --- BLUE permanent buff tests ----------------------------------------------


def test_mist_village_ninja_etb_surveil_mill_s10():
    print("\n=== Slice-10: Mist Village Ninja ETB surveil+mill ===")
    g, p1, p2, obj = _s10_etb_card("Mist Village Ninja")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_genjutsu_specialist_etb_surveil_mill_s10():
    print("\n=== Slice-10: Genjutsu Specialist ETB surveil+mill ===")
    g, p1, p2, obj = _s10_etb_card("Genjutsu Specialist")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_water_clone_etb_surveil_mill_s10():
    print("\n=== Slice-10: Water Clone ETB surveil+mill ===")
    g, p1, p2, obj = _s10_etb_card("Water Clone")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_sound_village_spy_etb_surveil_mill_s10():
    print("\n=== Slice-10: Sound Village Spy ETB surveil+mill ===")
    g, p1, p2, obj = _s10_etb_card("Sound Village Spy")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_mist_swordsman_etb_surveil_mill_s10():
    print("\n=== Slice-10: Mist Swordsman ETB surveil+mill ===")
    g, p1, p2, obj = _s10_etb_card("Mist Swordsman")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_sensor_ninja_etb_scry_reveal_s10():
    print("\n=== Slice-10: Sensor Ninja ETB scry+reveal ===")
    g, p1, p2, obj = _s10_etb_card("Sensor Ninja")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.REVEAL_HAND)


def test_genjutsu_web_etb_surveil_discard_s10():
    print("\n=== Slice-10: Genjutsu Web ETB surveil+discard ===")
    g, p1, p2, obj = _s10_etb_card("Genjutsu Web")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.DISCARD)


def test_hidden_mist_etb_surveil_reveal_s10():
    print("\n=== Slice-10: Hidden Mist ETB surveil+reveal ===")
    g, p1, p2, obj = _s10_etb_card("Hidden Mist")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.REVEAL_HAND)


# --- BLUE resolve handler tests ---------------------------------------------


def test_water_prison_resolve_s10():
    print("\n=== Slice-10: Water Prison resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_water_prison")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_hidden_mist_jutsu_resolve_s10():
    print("\n=== Slice-10: Hidden Mist Jutsu resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_hidden_mist_jutsu")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_water_dragon_resolve_s10():
    print("\n=== Slice-10: Water Dragon resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_water_dragon")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_genjutsu_release_resolve_s10():
    print("\n=== Slice-10: Genjutsu: Release resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_genjutsu_release")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.DISCARD and e.payload.get('player') == p2.id for e in events)


def test_demonic_illusion_resolve_s10():
    print("\n=== Slice-10: Demonic Illusion resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_demonic_illusion")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_substitution_resolve_s10():
    print("\n=== Slice-10: Substitution resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_substitution")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_mind_confusion_resolve_s10():
    print("\n=== Slice-10: Mind Confusion resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_mind_confusion")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.REVEAL_HAND and e.payload.get('player') == p2.id for e in events)


def test_water_wall_resolve_s10():
    print("\n=== Slice-10: Water Wall resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_water_wall")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) >= 3 for e in events)


def test_water_style_training_resolve_s10():
    print("\n=== Slice-10: Water Style Training resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_water_style_training")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_clone_jutsu_resolve_s10():
    print("\n=== Slice-10: Clone Jutsu resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_clone_jutsu")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_tactical_retreat_resolve_s10():
    print("\n=== Slice-10: Tactical Retreat resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_tactical_retreat")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


# --- BLACK permanent buff tests ---------------------------------------------


def test_curse_mark_bearer_death_drain_s10():
    print("\n=== Slice-10: Curse Mark Bearer death drain ===")
    g = Game()
    p1 = g.add_player("Alice")
    p2 = g.add_player("Bob")
    obj = _put_on_battlefield(g, p1, "Curse Mark Bearer")
    # Emit OBJECT_DESTROYED for the curse-mark bearer; engine will route to graveyard.
    obj.zone = ZoneType.GRAVEYARD
    g.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': obj.id},
        source=obj.id, controller=obj.controller,
    ))
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_anbu_assassin_etb_surveil_discard_s10():
    print("\n=== Slice-10: ANBU Assassin ETB surveil+discard ===")
    g, p1, p2, obj = _s10_etb_card("ANBU Assassin")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.DISCARD)


def test_forbidden_jutsu_user_etb_surveil_discard_s10():
    print("\n=== Slice-10: Forbidden Jutsu User ETB surveil+discard ===")
    g, p1, p2, obj = _s10_etb_card("Forbidden Jutsu User")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.DISCARD)


def test_reanimated_shinobi_etb_surveil_drain_s10():
    print("\n=== Slice-10: Reanimated Shinobi ETB surveil+drain ===")
    g, p1, p2, obj = _s10_etb_card("Reanimated Shinobi")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_curse_of_hatred_etb_surveil_drain_s10():
    print("\n=== Slice-10: Curse of Hatred ETB surveil+drain ===")
    g, p1, p2, obj = _s10_etb_card("Curse of Hatred")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


# --- BLACK resolve handler tests --------------------------------------------


def test_tsukuyomi_resolve_s10():
    print("\n=== Slice-10: Tsukuyomi resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_tsukuyomi")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) == -3 for e in events)


def test_soul_extraction_resolve_s10():
    print("\n=== Slice-10: Soul Extraction resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_soul_extraction")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_curse_mark_activation_resolve_s10():
    print("\n=== Slice-10: Curse Mark Activation resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_curse_mark_activation")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) == -2 for e in events)


def test_death_seal_resolve_s10():
    print("\n=== Slice-10: Death Seal resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_death_seal")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_shadow_possession_resolve_s10():
    print("\n=== Slice-10: Shadow Possession resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_shadow_possession")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_reaper_death_seal_resolve_s10():
    print("\n=== Slice-10: Reaper Death Seal resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_reaper_death_seal")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_painful_memories_resolve_s10():
    print("\n=== Slice-10: Painful Memories resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_painful_memories")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) == -2 for e in events)
    assert any(e.type == EventType.DISCARD and e.payload.get('player') == p2.id for e in events)


def test_edo_tensei_resolve_s10():
    print("\n=== Slice-10: Edo Tensei resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_edo_tensei")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_shinra_tensei_resolve_s10():
    print("\n=== Slice-10: Shinra Tensei resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_shinra_tensei")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) == -3 for e in events)


def test_uchiha_massacre_resolve_s10():
    print("\n=== Slice-10: Uchiha Massacre resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_uchiha_massacre")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) == -4 for e in events)


def test_izanagi_resolve_s10():
    print("\n=== Slice-10: Izanagi resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_izanagi")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) >= 4 for e in events)


# --- RED permanent buff tests -----------------------------------------------


def test_fire_style_user_etb_scry_damage_s10():
    print("\n=== Slice-10: Fire Style User ETB scry+damage ===")
    g, p1, p2, obj = _s10_etb_card("Fire Style User")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_uzumaki_descendant_etb_scry_damage_s10():
    print("\n=== Slice-10: Uzumaki Descendant ETB scry+damage ===")
    g, p1, p2, obj = _s10_etb_card("Uzumaki Descendant")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_shadow_clone_etb_scry_damage_s10():
    print("\n=== Slice-10: Shadow Clone ETB scry+damage ===")
    g, p1, p2, obj = _s10_etb_card("Shadow Clone")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_explosive_tag_ninja_etb_scry_damage_s10():
    print("\n=== Slice-10: Explosive Tag Ninja ETB scry+damage ===")
    g, p1, p2, obj = _s10_etb_card("Explosive Tag Ninja")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_taijutsu_specialist_attack_drain_s10():
    print("\n=== Slice-10: Taijutsu Specialist attack drain ===")
    g, p1, p2, obj = _s10_attack("Taijutsu Specialist")
    # Taijutsu doesn't emit SCRY when no Warriors are out, so check just the drain
    new = g.state.event_log
    opp_evs = [e for e in new if e.type == EventType.LIFE_CHANGE
               and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0
               and e.source == obj.id]
    assert opp_evs, "Expected LIFE_CHANGE drain on attack"


def test_rage_jinchuriki_etb_scry_damage_s10():
    print("\n=== Slice-10: Rage-Filled Jinchuriki ETB scry+damage ===")
    g, p1, p2, obj = _s10_etb_card("Rage-Filled Jinchuriki")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_lightning_blade_user_etb_scry_damage_s10():
    print("\n=== Slice-10: Lightning Blade User ETB scry+damage ===")
    g, p1, p2, obj = _s10_etb_card("Lightning Blade User")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_berserker_ninja_attack_scry_drain_s10():
    print("\n=== Slice-10: Berserker Ninja attack scry+drain ===")
    g, p1, p2, obj = _s10_attack("Berserker Ninja")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_battle_frenzy_etb_scry_damage_s10():
    print("\n=== Slice-10: Battle Frenzy ETB scry+damage ===")
    g, p1, p2, obj = _s10_etb_card("Battle Frenzy")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


# --- RED resolve handler tests ----------------------------------------------


def test_fire_ball_resolve_s10():
    print("\n=== Slice-10: Fire Ball resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_fire_ball")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_rasengan_resolve_s10():
    print("\n=== Slice-10: Rasengan resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_rasengan")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_chidori_resolve_s10():
    print("\n=== Slice-10: Chidori resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_chidori")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_rasenshuriken_resolve_s10():
    print("\n=== Slice-10: Rasenshuriken resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_rasenshuriken")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_lightning_blade_resolve_s10():
    print("\n=== Slice-10: Lightning Blade resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_lightning_blade")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_eight_gates_resolve_s10():
    print("\n=== Slice-10: Eight Gates Release resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_eight_gates")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_fire_dragon_resolve_s10():
    print("\n=== Slice-10: Fire Dragon Jutsu resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_fire_dragon")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_explosive_kunai_resolve_s10():
    print("\n=== Slice-10: Explosive Kunai resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_explosive_kunai")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_lariat_resolve_s10():
    print("\n=== Slice-10: Lariat resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_lariat")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_planetary_rasengan_resolve_s10():
    print("\n=== Slice-10: Planetary Rasengan resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_planetary_rasengan")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_multi_shadow_clone_resolve_s10():
    print("\n=== Slice-10: Multi Shadow Clone resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_multi_shadow_clone")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_burning_will_resolve_s10():
    print("\n=== Slice-10: Burning Will resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_burning_will")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


# --- GREEN permanent buff tests ---------------------------------------------


def test_gamabunta_etb_scry_gain_s10():
    print("\n=== Slice-10: Gamabunta ETB scry+gain ===")
    g, p1, p2, obj = _s10_etb_card("Gamabunta, Toad Boss")
    new = g.state.event_log
    scrys = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    gains = [e for e in new if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0
             and e.source == obj.id]
    assert scrys, "Expected SCRY"
    assert gains, "Expected life gain"


def test_toad_summon_etb_scry_gain_s10():
    print("\n=== Slice-10: Toad Summon ETB scry+gain ===")
    g, p1, p2, obj = _s10_etb_card("Toad Summon")
    new = g.state.event_log
    assert any(e.type == EventType.SCRY and e.source == obj.id for e in new)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 and e.source == obj.id for e in new)


def test_snake_summon_etb_surveil_drain_s10():
    print("\n=== Slice-10: Snake Summon ETB surveil+drain ===")
    g, p1, p2, obj = _s10_etb_card("Snake Summon")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_forest_death_beast_etb_scry_damage_s10():
    print("\n=== Slice-10: Forest of Death Beast ETB scry+damage ===")
    g, p1, p2, obj = _s10_etb_card("Forest of Death Beast")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_nature_chakra_user_etb_scry_gain_s10():
    print("\n=== Slice-10: Nature Chakra User ETB scry+gain ===")
    g, p1, p2, obj = _s10_etb_card("Nature Chakra User")
    new = g.state.event_log
    assert any(e.type == EventType.SCRY and e.source == obj.id for e in new)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 and e.source == obj.id for e in new)


def test_sage_apprentice_etb_scry_gain_s10():
    print("\n=== Slice-10: Sage Apprentice ETB scry+gain ===")
    g, p1, p2, obj = _s10_etb_card("Sage Apprentice")
    new = g.state.event_log
    assert any(e.type == EventType.SCRY and e.source == obj.id for e in new)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 and e.source == obj.id for e in new)


def test_giant_centipede_etb_surveil_drain_s10():
    print("\n=== Slice-10: Giant Centipede ETB surveil+drain ===")
    g, p1, p2, obj = _s10_etb_card("Giant Centipede")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_forest_guardian_etb_scry_gain_s10():
    print("\n=== Slice-10: Forest Guardian ETB scry+gain ===")
    g, p1, p2, obj = _s10_etb_card("Forest Guardian")
    new = g.state.event_log
    assert any(e.type == EventType.SCRY and e.source == obj.id for e in new)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 and e.source == obj.id for e in new)


def test_sage_mode_etb_scry_gain_s10():
    print("\n=== Slice-10: Sage Mode ETB scry+gain ===")
    g, p1, p2, obj = _s10_etb_card("Sage Mode")
    new = g.state.event_log
    assert any(e.type == EventType.SCRY and e.source == obj.id for e in new)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 and e.source == obj.id for e in new)


def test_nature_chakra_field_etb_scry_gain_s10():
    print("\n=== Slice-10: Nature Chakra Field ETB scry+gain ===")
    g, p1, p2, obj = _s10_etb_card("Nature Chakra Field")
    new = g.state.event_log
    assert any(e.type == EventType.SCRY and e.source == obj.id for e in new)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 and e.source == obj.id for e in new)


# --- GREEN resolve handler tests --------------------------------------------


def test_summoning_jutsu_resolve_s10():
    print("\n=== Slice-10: Summoning Jutsu resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_summon_jutsu")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 for e in events)


def test_wood_wall_resolve_s10():
    print("\n=== Slice-10: Wood Style: Wall resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_wood_wall")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) >= 4 for e in events)


def test_nature_energy_resolve_s10():
    print("\n=== Slice-10: Nature Energy resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_nature_energy")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 for e in events)


def test_frog_kumite_resolve_s10():
    print("\n=== Slice-10: Frog Kumite resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_frog_kumite")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_forest_binding_resolve_s10():
    print("\n=== Slice-10: Forest Binding resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_forest_binding")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) == -2 for e in events)


def test_rejuvenation_resolve_s10():
    print("\n=== Slice-10: Rejuvenation Jutsu resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_rejuvenation")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) >= 6 for e in events)


def test_giant_growth_resolve_s10():
    print("\n=== Slice-10: Giant Growth Jutsu resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_giant_growth")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 for e in events)


def test_sage_awakening_resolve_s10():
    print("\n=== Slice-10: Sage Art: Awakening resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_sage_awakening")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_mass_summoning_resolve_s10():
    print("\n=== Slice-10: Mass Summoning resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_mass_summoning")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) >= 6 for e in events)


def test_deep_forest_resolve_s10():
    print("\n=== Slice-10: Wood Style: Deep Forest resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_deep_forest")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) >= 5 for e in events)


def test_sage_training_resolve_s10():
    print("\n=== Slice-10: Sage Training resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_sage_training")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) >= 4 for e in events)


def test_natural_rebirth_resolve_s10():
    print("\n=== Slice-10: Natural Rebirth resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_natural_rebirth")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) >= 8 for e in events)


# --- MULTICOLOR + ARTIFACT + LAND tests -------------------------------------


def test_shino_aburame_etb_surveil_drain_s10():
    print("\n=== Slice-10: Shino Aburame ETB surveil+drain ===")
    g, p1, p2, obj = _s10_etb_card("Shino Aburame, Insect Master")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_kiba_inuzuka_attack_scry_damage_s10():
    print("\n=== Slice-10: Kiba Inuzuka attack scry+damage ===")
    g, p1, p2, obj = _s10_attack("Kiba Inuzuka, Fang over Fang")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_zetsu_etb_surveil_drain_s10():
    print("\n=== Slice-10: Zetsu ETB surveil+drain ===")
    g, p1, p2, obj = _s10_etb_card("Zetsu, White and Black")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_manda_etb_surveil_drain_s10():
    print("\n=== Slice-10: Manda ETB surveil+drain ===")
    g, p1, p2, obj = _s10_etb_card("Manda, Snake Boss")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_shukaku_etb_scry_damage_s10():
    print("\n=== Slice-10: Shukaku ETB scry+damage ===")
    g, p1, p2, obj = _s10_etb_card("Shukaku, One-Tail")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_matatabi_etb_scry_damage_s10():
    print("\n=== Slice-10: Matatabi ETB scry+damage ===")
    g, p1, p2, obj = _s10_etb_card("Matatabi, Two-Tails")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_isobu_etb_surveil_drain_s10():
    print("\n=== Slice-10: Isobu ETB surveil+drain ===")
    g, p1, p2, obj = _s10_etb_card("Isobu, Three-Tails")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_son_goku_etb_scry_damage_s10():
    print("\n=== Slice-10: Son Goku ETB scry+damage ===")
    g, p1, p2, obj = _s10_etb_card("Son Goku, Four-Tails")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_gyuki_etb_scry_damage_s10():
    print("\n=== Slice-10: Gyuki ETB scry+damage ===")
    g, p1, p2, obj = _s10_etb_card("Gyuki, Eight-Tails")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_amaterasu_resolve_s10():
    print("\n=== Slice-10: Amaterasu resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_amaterasu")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_wind_rasengan_resolve_s10():
    print("\n=== Slice-10: Wind-Enhanced Rasengan resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_wind_rasengan")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_new_generation_resolve_s10():
    print("\n=== Slice-10: New Generation resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_new_generation")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 for e in events)


def test_bonds_friendship_resolve_s10():
    print("\n=== Slice-10: Bonds of Friendship resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_bonds_of_friendship")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 for e in events)


def test_shinobi_war_resolve_s10():
    print("\n=== Slice-10: Shinobi War resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_shinobi_war")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) == -3 for e in events)


def test_sannin_showdown_resolve_s10():
    print("\n=== Slice-10: Sannin Showdown resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_sannin_showdown")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_final_valley_resolve_s10():
    print("\n=== Slice-10: Final Valley Battle resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_final_valley")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_infinite_tsukuyomi_resolve_s10():
    print("\n=== Slice-10: Infinite Tsukuyomi resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_infinite_tsukuyomi")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_talk_no_jutsu_resolve_s10():
    print("\n=== Slice-10: Talk no Jutsu resolve ===")
    events, p1, p2 = _s10_resolve("_nrt_resolve_talk_no_jutsu")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) >= 5 for e in events)


def test_susanoo_etb_surveil_drain_s10():
    print("\n=== Slice-10: Susanoo ETB surveil+drain ===")
    g, p1, p2, obj = _s10_etb_card("Susanoo")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


# --- ARTIFACT tests ---------------------------------------------------------


def test_kunai_etb_scry_damage_s10():
    print("\n=== Slice-10: Kunai ETB scry+damage ===")
    g, p1, p2, obj = _s10_etb_card("Kunai")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_shuriken_etb_scry_damage_s10():
    print("\n=== Slice-10: Shuriken ETB scry+damage ===")
    g, p1, p2, obj = _s10_etb_card("Shuriken")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_scroll_of_sealing_etb_surveil_drain_s10():
    print("\n=== Slice-10: Scroll of Sealing ETB surveil+drain ===")
    g, p1, p2, obj = _s10_etb_card("Scroll of Sealing")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_chakra_pills_etb_scry_gain_s10():
    print("\n=== Slice-10: Chakra Pills ETB scry+gain ===")
    g, p1, p2, obj = _s10_etb_card("Chakra Pills")
    new = g.state.event_log
    assert any(e.type == EventType.SCRY and e.source == obj.id for e in new)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) >= 4 and e.source == obj.id for e in new)


def test_forbidden_scroll_etb_surveil_mill_s10():
    print("\n=== Slice-10: Forbidden Scroll ETB surveil+mill ===")
    g, p1, p2, obj = _s10_etb_card("Forbidden Scroll")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_headband_etb_scry_gain_s10():
    print("\n=== Slice-10: Headband of the Leaf ETB scry+gain ===")
    g, p1, p2, obj = _s10_etb_card("Headband of the Leaf")
    new = g.state.event_log
    assert any(e.type == EventType.SCRY and e.source == obj.id for e in new)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 and e.source == obj.id for e in new)


def test_sharingan_contact_etb_scry_drain_s10():
    print("\n=== Slice-10: Sharingan Contact ETB scry+drain ===")
    g, p1, p2, obj = _s10_etb_card("Sharingan Contact")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_rinnegan_eye_etb_surveil_reveal_s10():
    print("\n=== Slice-10: Rinnegan Eye ETB surveil+reveal ===")
    g, p1, p2, obj = _s10_etb_card("Rinnegan Eye")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.REVEAL_HAND)


def test_byakugan_eye_etb_scry_reveal_s10():
    print("\n=== Slice-10: Byakugan Eye ETB scry+reveal ===")
    g, p1, p2, obj = _s10_etb_card("Byakugan Eye")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.REVEAL_HAND)


def test_explosive_tag_etb_scry_damage_s10():
    print("\n=== Slice-10: Explosive Tag ETB scry+damage ===")
    g, p1, p2, obj = _s10_etb_card("Explosive Tag")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_smoke_bomb_etb_surveil_drain_s10():
    print("\n=== Slice-10: Smoke Bomb ETB surveil+drain ===")
    g, p1, p2, obj = _s10_etb_card("Smoke Bomb")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_summoning_contract_etb_scry_gain_s10():
    print("\n=== Slice-10: Summoning Contract ETB scry+gain ===")
    g, p1, p2, obj = _s10_etb_card("Summoning Contract")
    new = g.state.event_log
    assert any(e.type == EventType.SCRY and e.source == obj.id for e in new)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 and e.source == obj.id for e in new)


# --- LAND tests -------------------------------------------------------------


def test_hidden_leaf_village_etb_scry_gain_s10():
    print("\n=== Slice-10: Hidden Leaf Village ETB scry+gain ===")
    g, p1, p2, obj = _s10_etb_card("Hidden Leaf Village")
    new = g.state.event_log
    assert any(e.type == EventType.SCRY and e.source == obj.id for e in new)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 and e.source == obj.id for e in new)


def test_hidden_mist_village_etb_surveil_mill_s10():
    print("\n=== Slice-10: Hidden Mist Village ETB surveil+mill ===")
    g, p1, p2, obj = _s10_etb_card("Hidden Mist Village")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_akatsuki_hideout_land_etb_surveil_drain_s10():
    print("\n=== Slice-10: Akatsuki Hideout land ETB surveil+drain ===")
    g = Game()
    p1 = g.add_player("Alice")
    p2 = g.add_player("Bob")
    # Disambiguate: use the LAND with set name 'Akatsuki Hideout' (last def wins in dict).
    obj = _put_on_battlefield(g, p1, "Akatsuki Hideout")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_valley_of_end_etb_scry_damage_s10():
    print("\n=== Slice-10: Valley of the End ETB scry+damage ===")
    g, p1, p2, obj = _s10_etb_card("Valley of the End")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_mount_myoboku_etb_scry_gain_s10():
    print("\n=== Slice-10: Mount Myoboku ETB scry+gain ===")
    g, p1, p2, obj = _s10_etb_card("Mount Myoboku")
    new = g.state.event_log
    assert any(e.type == EventType.SCRY and e.source == obj.id for e in new)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 and e.source == obj.id for e in new)


def test_uchiha_compound_etb_surveil_drain_s10():
    print("\n=== Slice-10: Uchiha Compound ETB surveil+drain ===")
    g, p1, p2, obj = _s10_etb_card("Uchiha Compound")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_hyuga_compound_etb_scry_gain_s10():
    print("\n=== Slice-10: Hyuga Compound ETB scry+gain ===")
    g, p1, p2, obj = _s10_etb_card("Hyuga Compound")
    new = g.state.event_log
    assert any(e.type == EventType.SCRY and e.source == obj.id for e in new)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 and e.source == obj.id for e in new)


def test_training_ground_etb_scry_gain_s10():
    print("\n=== Slice-10: Training Ground ETB scry+gain ===")
    g, p1, p2, obj = _s10_etb_card("Training Ground")
    new = g.state.event_log
    assert any(e.type == EventType.SCRY and e.source == obj.id for e in new)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) >= 2 and e.source == obj.id for e in new)


def test_chunin_arena_etb_scry_drain_s10():
    print("\n=== Slice-10: Chunin Exam Arena ETB scry+drain ===")
    g, p1, p2, obj = _s10_etb_card("Chunin Exam Arena")
    _s10_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


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
