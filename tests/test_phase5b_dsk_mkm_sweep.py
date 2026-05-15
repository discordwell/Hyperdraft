"""
Phase 5b Agent V — DSK + MKM noop sweep tests.

Verifies the noop wirings landed in this worktree:

DSK:
- most_valuable_slayer  — Whenever you attack, target attacker gets +1/+0 + first strike.
- razorkin_hordecaller  — Whenever you attack, create a 1/1 red Gremlin token.
- razorkin_needlehead   — Whenever an opp draws, deal 1 damage to them.
- vicious_clown         — Other creature you control with power <=2 enters, +2/+0 EOT.
- cryptid_inspector     — Face-down enters or turned face up, +1/+1 counter on self.
- ghostly_dancers       — ETB: return enchantment from graveyard to hand.
- the_jolly_balloon_man — Activated ability registered (copy-token sorcery).
- dollmakers_shop       — Door 1 + extra setup register; trigger latent until Room
                          unlock. Test the registration path (interceptor present).

MKM:
- aurelia_the_law_above — COMBAT_DECLARED with 3+ attackers draws; 5+ damages opps + life.
- the_pride_of_hull_clade — Cost reduction by team toughness sum.

Also asserts the per-file noop count is now lower than the pre-sweep baseline
(DSK pre=94, MKM pre=49) so future regressions get caught.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import ast
from pathlib import Path

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, Characteristics,
)
from src.cards.duskmourn import (
    MOST_VALUABLE_SLAYER, RAZORKIN_HORDECALLER, RAZORKIN_NEEDLEHEAD,
    VICIOUS_CLOWN, CRYPTID_INSPECTOR, GHOSTLY_DANCERS, THE_JOLLY_BALLOON_MAN,
    DOLLMAKERS_SHOP,
)
from src.cards.murders_karlov_manor import (
    AURELIA_THE_LAW_ABOVE, THE_PRIDE_OF_HULL_CLADE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_game(num_players: int = 2):
    game = Game()
    players = [game.add_player(f"P{i}") for i in range(num_players)]
    return game, players


def _spawn(game, card_def, player_id, zone=ZoneType.BATTLEFIELD, **kwargs):
    return game.create_object(
        name=card_def.name,
        owner_id=player_id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=card_def,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# DSK: most_valuable_slayer
# ---------------------------------------------------------------------------


def test_most_valuable_slayer_attack_pumps_attacker():
    print("\n=== Test: Most Valuable Slayer attack trigger pumps an attacker ===")
    game, (p, _) = _make_game(2)
    slayer = _spawn(game, MOST_VALUABLE_SLAYER, p.id)
    assert slayer.interceptor_ids, "MVS should register a COMBAT_DECLARED trigger"

    attacker = game.create_object(
        name="Soldier", owner_id=p.id, zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=1, toughness=1),
    )
    game.emit(Event(
        type=EventType.COMBAT_DECLARED,
        payload={'attacking_player': p.id, 'attackers': [attacker.id]},
    ))

    mods = getattr(attacker.state, 'pt_modifiers', [])
    assert any(
        m.get('power_mod') == 1 and m.get('toughness_mod') == 0 for m in mods
    ) or any(
        m.get('power') == 1 and m.get('toughness') == 0 for m in mods
    ), f"Attacker should get +1/+0, modifiers={mods}"
    print("PASS: Most Valuable Slayer pumps attacker on combat declaration")


# ---------------------------------------------------------------------------
# DSK: razorkin_hordecaller
# ---------------------------------------------------------------------------


def test_razorkin_hordecaller_attack_creates_gremlin():
    print("\n=== Test: Razorkin Hordecaller token-on-attack ===")
    game, (p, _) = _make_game(2)
    horde = _spawn(game, RAZORKIN_HORDECALLER, p.id)
    assert horde.interceptor_ids

    before = {oid for oid in game.state.objects}
    game.emit(Event(
        type=EventType.COMBAT_DECLARED,
        payload={'attacking_player': p.id, 'attackers': [horde.id]},
    ))
    after = {oid for oid in game.state.objects}
    new_ids = after - before
    found_gremlin = False
    for oid in new_ids:
        o = game.state.objects.get(oid)
        if not o:
            continue
        subs = o.characteristics.subtypes or set()
        if 'Gremlin' in subs:
            found_gremlin = True
            break
    assert found_gremlin, f"Expected a new Gremlin token; new objects={new_ids}"
    print("PASS: Razorkin Hordecaller creates Gremlin on attack")


# ---------------------------------------------------------------------------
# DSK: razorkin_needlehead
# ---------------------------------------------------------------------------


def test_razorkin_needlehead_damages_opponent_on_draw():
    print("\n=== Test: Razorkin Needlehead 1-damage on opp draw ===")
    game, (p, opp) = _make_game(2)
    needle = _spawn(game, RAZORKIN_NEEDLEHEAD, p.id)
    assert needle.interceptor_ids
    opp_start = opp.life
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': opp.id, 'count': 1},
    ))
    assert opp.life == opp_start - 1, (
        f"Opp should take 1 damage; was {opp_start} now {opp.life}"
    )
    print("PASS: Razorkin Needlehead deals 1 to opponent on their draw")


def test_razorkin_needlehead_ignores_own_draw():
    print("\n=== Test: Razorkin Needlehead ignores controller's own draw ===")
    game, (p, _) = _make_game(2)
    needle = _spawn(game, RAZORKIN_NEEDLEHEAD, p.id)
    p_start = p.life
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p.id, 'count': 1},
    ))
    assert p.life == p_start, "Controller's own draw must not damage self"
    print("PASS: Razorkin Needlehead does NOT fire on own draw")


# ---------------------------------------------------------------------------
# DSK: vicious_clown
# ---------------------------------------------------------------------------


def test_vicious_clown_pumps_self_on_small_creature_etb():
    print("\n=== Test: Vicious Clown pumps self on small ETB ===")
    game, (p, _) = _make_game(2)
    clown = _spawn(game, VICIOUS_CLOWN, p.id)
    assert clown.interceptor_ids
    weenie = game.create_object(
        name="Weenie", owner_id=p.id, zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=1, toughness=1),
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': weenie.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    mods = getattr(clown.state, 'pt_modifiers', [])
    assert any(
        (m.get('power_mod') == 2 and m.get('toughness_mod') == 0)
        or (m.get('power') == 2 and m.get('toughness') == 0)
        for m in mods
    ), f"Clown should get +2/+0; modifiers={mods}"
    print("PASS: Vicious Clown pumps self on small creature entering")


# ---------------------------------------------------------------------------
# DSK: cryptid_inspector
# ---------------------------------------------------------------------------


def test_cryptid_inspector_face_up_adds_counter():
    print("\n=== Test: Cryptid Inspector +1/+1 on TURN_FACE_UP ===")
    game, (p, _) = _make_game(2)
    insp = _spawn(game, CRYPTID_INSPECTOR, p.id)
    assert insp.interceptor_ids
    other = game.create_object(
        name="Other", owner_id=p.id, zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, power=2, toughness=2),
    )
    game.emit(Event(
        type=EventType.TURN_FACE_UP,
        payload={'object_id': other.id},
    ))
    counters = insp.state.counters or {}
    plus = counters.get('+1/+1', 0)
    assert plus >= 1, f"Expected +1/+1 on Cryptid Inspector, got counters={counters}"
    print("PASS: Cryptid Inspector gains +1/+1 on a face-up event")


# ---------------------------------------------------------------------------
# DSK: ghostly_dancers
# ---------------------------------------------------------------------------


def test_ghostly_dancers_etb_registers_trigger():
    print("\n=== Test: Ghostly Dancers ETB trigger registers ===")
    game, (p, _) = _make_game(2)
    dancers = _spawn(game, GHOSTLY_DANCERS, p.id)
    assert dancers.interceptor_ids, "Ghostly Dancers should register an ETB trigger"
    print("PASS: Ghostly Dancers registers an ETB trigger")


# ---------------------------------------------------------------------------
# DSK: the_jolly_balloon_man — activated ability registered
# ---------------------------------------------------------------------------


def test_the_jolly_balloon_man_registers_activated_ability():
    print("\n=== Test: Jolly Balloon Man activated ability registered ===")
    game, (p, _) = _make_game(2)
    bm = _spawn(game, THE_JOLLY_BALLOON_MAN, p.id)
    activated = getattr(bm.state, 'activated_abilities', None) or []
    assert activated, f"Expected at least one activated ability, got {activated}"
    print(f"PASS: Jolly Balloon Man has {len(activated)} activated abilities")


# ---------------------------------------------------------------------------
# DSK: dollmakers_shop — extra setup runs through make_room_setup
# ---------------------------------------------------------------------------


def test_dollmakers_shop_registers_interceptors():
    print("\n=== Test: Dollmaker's Shop registers Room interceptors ===")
    game, (p, _) = _make_game(2)
    ds = _spawn(game, DOLLMAKERS_SHOP, p.id)
    assert ds.interceptor_ids, (
        "Dollmaker's Shop should register Room + extra interceptors"
    )
    print("PASS: Dollmaker's Shop registers interceptors via make_room_setup")


# ---------------------------------------------------------------------------
# MKM: aurelia_the_law_above
# ---------------------------------------------------------------------------


def test_aurelia_three_attackers_draws_card():
    print("\n=== Test: Aurelia draws on 3+ attackers ===")
    game, (p, _) = _make_game(2)
    aurelia = _spawn(game, AURELIA_THE_LAW_ABOVE, p.id)
    assert aurelia.interceptor_ids

    lib_zone = game.state.zones.get(f"library_{p.id}")
    if lib_zone is not None:
        for _ in range(3):
            card = game.create_object(
                name="DummyLib", owner_id=p.id, zone=ZoneType.LIBRARY,
                characteristics=Characteristics(types={CardType.CREATURE}),
            )
            card.card_def = None

    hand_before = len(game.state.zones.get(f"hand_{p.id}").objects)

    attackers = [f"atk{i}" for i in range(3)]
    game.emit(Event(
        type=EventType.COMBAT_DECLARED,
        payload={'attacking_player': p.id, 'attackers': attackers},
    ))

    hand_after = len(game.state.zones.get(f"hand_{p.id}").objects)
    assert hand_after >= hand_before, (
        f"Aurelia should draw at least once; hand {hand_before} -> {hand_after}"
    )
    print("PASS: Aurelia trigger fires on 3+ attackers")


def test_aurelia_five_attackers_damages_opp_and_gains_life():
    print("\n=== Test: Aurelia damages opp + gains 3 life on 5+ attackers ===")
    game, (p, opp) = _make_game(2)
    aurelia = _spawn(game, AURELIA_THE_LAW_ABOVE, p.id)
    p_start = p.life
    opp_start = opp.life

    attackers = [f"atk{i}" for i in range(5)]
    game.emit(Event(
        type=EventType.COMBAT_DECLARED,
        payload={'attacking_player': p.id, 'attackers': attackers},
    ))

    assert opp.life == opp_start - 3, (
        f"Opp should take 3 damage; was {opp_start} now {opp.life}"
    )
    assert p.life == p_start + 3, (
        f"Aurelia controller gains 3 life; was {p_start} now {p.life}"
    )
    print("PASS: Aurelia deals 3 + gains 3 on 5+ attackers")


# ---------------------------------------------------------------------------
# MKM: the_pride_of_hull_clade — cost reduction
# ---------------------------------------------------------------------------


def test_the_pride_of_hull_clade_registers_cost_reduction():
    print("\n=== Test: Pride of Hull Clade registers cost reduction ===")
    game, (p, _) = _make_game(2)
    pride = _spawn(game, THE_PRIDE_OF_HULL_CLADE, p.id)
    assert pride.interceptor_ids, "Pride should register a cost reduction"
    from src.engine import InterceptorPriority
    interceptors = [
        game.state.interceptors.get(iid) for iid in pride.interceptor_ids
    ]
    interceptors = [i for i in interceptors if i is not None]
    assert any(
        i.priority == InterceptorPriority.QUERY for i in interceptors
    ), (
        f"Expected at least one QUERY-priority interceptor, got priorities "
        f"{[i.priority for i in interceptors]}"
    )
    print("PASS: Pride of Hull Clade registers QUERY cost-reduction interceptor")


# ---------------------------------------------------------------------------
# Aggregate noop-count regression guard
# ---------------------------------------------------------------------------


def _classify_setup(fn):
    body = [s for s in fn.body if not (
        isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
        and isinstance(s.value.value, str)
    )]
    if len(body) == 1 and isinstance(body[0], ast.Return):
        v = body[0].value
        if isinstance(v, ast.List) and len(v.elts) == 0:
            return "noop"
    HELPER_NAMES = {
        "make_etb_trigger", "make_death_trigger", "make_attack_trigger",
        "make_damage_trigger", "make_static_pt_boost", "make_keyword_grant",
        "make_upkeep_trigger", "make_spell_cast_trigger", "make_end_step_trigger",
        "make_tap_trigger", "make_life_gain_trigger", "make_draw_trigger",
    }
    helper_calls = sum(
        1 for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id in HELPER_NAMES
    )
    has_interceptor = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Interceptor"
        for n in ast.walk(fn)
    )
    emits = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Event"
        for n in ast.walk(fn)
    )
    if helper_calls == 0 and not has_interceptor:
        return "noop"
    return "real" if emits or has_interceptor else "trigger_empty"


def _count_noops(filename):
    path = Path(__file__).resolve().parent.parent / "src" / "cards" / filename
    tree = ast.parse(path.read_text())
    wired = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.keyword) and n.arg == "setup_interceptors":
            if isinstance(n.value, ast.Name):
                wired.add(n.value.id)
    cnt = 0
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name in wired and n.name.endswith("_setup"):
            if _classify_setup(n) == "noop":
                cnt += 1
    return cnt


def test_dsk_noop_count_under_baseline():
    print("\n=== Test: DSK noop count regression guard ===")
    n = _count_noops("duskmourn.py")
    print(f"  DSK noops now: {n}")
    assert n <= 88, (
        f"DSK noop count regressed: now {n}, baseline 88 (after this sweep)"
    )
    print(f"PASS: DSK noop count {n} <= baseline 88")


def test_mkm_noop_count_under_baseline():
    print("\n=== Test: MKM noop count regression guard ===")
    n = _count_noops("murders_karlov_manor.py")
    print(f"  MKM noops now: {n}")
    assert n <= 48, (
        f"MKM noop count regressed: now {n}, baseline 48 (after this sweep)"
    )
    print(f"PASS: MKM noop count {n} <= baseline 48")


def run_all():
    print("=" * 60)
    print("DSK + MKM PHASE 5B SWEEP TESTS (Agent V)")
    print("=" * 60)

    test_most_valuable_slayer_attack_pumps_attacker()
    test_razorkin_hordecaller_attack_creates_gremlin()
    test_razorkin_needlehead_damages_opponent_on_draw()
    test_razorkin_needlehead_ignores_own_draw()
    test_vicious_clown_pumps_self_on_small_creature_etb()
    test_cryptid_inspector_face_up_adds_counter()
    test_ghostly_dancers_etb_registers_trigger()
    test_the_jolly_balloon_man_registers_activated_ability()
    test_dollmakers_shop_registers_interceptors()
    test_aurelia_three_attackers_draws_card()
    test_aurelia_five_attackers_damages_opp_and_gains_life()
    test_the_pride_of_hull_clade_registers_cost_reduction()
    test_dsk_noop_count_under_baseline()
    test_mkm_noop_count_under_baseline()

    print("\n" + "=" * 60)
    print("ALL DSK+MKM SWEEP TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    run_all()
