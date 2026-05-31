"""Phase-1 unit tests for the scp2 engine (SCP: SECURE / CONTAIN / SUBVERT).

Covers every mechanic in docs/design/scp2_rules.md §4-7: resources/AP, install (face-down),
advance/contain, the infiltration run (rez/break/subroutine/access), free/steal, traps,
all four win conditions, fog-of-war redaction, and a turn-manager smoke test.

Run: HYPERDRAFT_STRICT=1 PYTHONPATH=. python3 -m pytest tests/test_scp2.py -q
"""

import asyncio

import pytest

from src.engine.game import Game
from src.engine import scp2
from src.engine.types import ZoneType


# --------------------------------------------------------------------------- helpers
def _setup():
    g = Game(mode="scp2")
    f = g.add_player("Foundation")
    i = g.add_player("Insurgency")
    scp2.setup_scp2_player(g, f, scp2.FOUNDATION)
    scp2.setup_scp2_player(g, i, scp2.INSURGENCY)
    return g, f, i


def _hand(g, pid, cd):
    return g.create_object(name=cd.name, owner_id=pid, zone=ZoneType.HAND,
                           characteristics=cd.characteristics, card_def=cd)


def _ready(g, pid, ap=10, credits=20):
    r = scp2.ensure_scp2_state(g.state, pid)
    r["ap"] = ap
    r["credits"] = credits
    return r


def _install_anomaly(g, fid, *, threshold=4, value=2, trap=False, breach_on_free=None):
    _ready(g, fid)
    cd = scp2.make_anomaly("SCP-TEST", threshold, value, trap=trap, breach_on_free=breach_on_free)
    obj = _hand(g, fid, cd)
    ok, msg, _ = scp2.play_card(g, fid, obj.id)
    assert ok, msg
    cell = scp2.ensure_scp2_state(g.state, fid)["cells"][-1]
    return obj, cell


def _add_layer(g, fid, cell, *, ltype="barrier", strength=4, rez=4, sub=None):
    _ready(g, fid)
    cd = scp2.make_layer("LAYER", ltype, strength, rez, sub=sub)
    obj = _hand(g, fid, cd)
    ok, msg, _ = scp2.play_card(g, fid, obj.id, target=("cell", cell["id"]))
    assert ok, msg
    return obj


# --------------------------------------------------------------------------- resources
def test_gain_credits_spends_ap():
    g, f, i = _setup()
    r = _ready(g, f.id, ap=1, credits=5)
    ok, _m, _e = scp2.gain_credits(g, f.id)
    assert ok and r["credits"] == 5 + scp2.GAIN_AMOUNT and r["ap"] == 0
    ok2, _m2, _e2 = scp2.gain_credits(g, f.id)
    assert not ok2, "should fail with no AP"


def test_play_card_costs_ap_and_credits():
    g, f, i = _setup()
    r = _ready(g, f.id, ap=1, credits=3)
    cd = scp2.make_anomaly("Pricey", 3, 1, cost=2)
    obj = _hand(g, f.id, cd)
    ok, msg, _ = scp2.play_card(g, f.id, obj.id)
    assert ok, msg
    assert r["ap"] == 0 and r["credits"] == 1


# --------------------------------------------------------------------------- install / advance / contain
def test_install_anomaly_is_facedown_in_a_cell():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id)
    assert cell["anomaly"] == obj.id
    assert getattr(obj.state, "scp2_facedown") is True
    assert getattr(obj.state, "scp2_advancement") == 0
    assert obj.zone == ZoneType.BATTLEFIELD


def test_advance_then_contain_scores_value():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, threshold=3, value=2)
    for _ in range(3):
        ok, msg, _ = scp2.advance(g, f.id, obj.id)
        assert ok, msg
    assert getattr(obj.state, "scp2_advancement") == 3
    ok, msg, _ = scp2.contain(g, f.id, obj.id)
    assert ok, msg
    fr = scp2.ensure_scp2_state(g.state, f.id)
    assert fr["containment_points"] == 2
    assert getattr(obj.state, "scp2_status") == "contained"
    assert getattr(obj.state, "scp2_facedown") is False


def test_contain_below_threshold_fails():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, threshold=4, value=2)
    scp2.advance(g, f.id, obj.id)  # only 1 of 4
    ok, msg, _ = scp2.contain(g, f.id, obj.id)
    assert not ok and "advancement" in msg.lower()


# --------------------------------------------------------------------------- infiltration
def test_infiltrate_undefended_cell_frees_anomaly():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2)
    ir = _ready(g, i.id, ap=3, credits=10)
    fr = scp2.ensure_scp2_state(g.state, f.id)
    ok, msg, _ = scp2.infiltrate(g, i.id, ("cell", cell["id"]))
    assert ok, msg
    assert ir["liberation_points"] == 2
    assert fr["total_breach"] == 2
    assert cell["anomaly"] is None


def test_rezzed_barrier_with_no_breaker_ends_run():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2)
    _add_layer(g, f.id, cell, ltype="barrier", strength=4, rez=4)
    fr = scp2.ensure_scp2_state(g.state, f.id)
    fr["credits"] = 10  # enough to rez
    ir = _ready(g, i.id, ap=3, credits=10)  # but no breaker
    ok, msg, _ = scp2.infiltrate(g, i.id, ("cell", cell["id"]))
    assert ok, msg
    assert ir["liberation_points"] == 0, "barrier should have stopped the run"
    assert cell["anomaly"] == obj.id, "anomaly must still be contained-in-progress"


def test_breaker_cracks_barrier_and_frees():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2)
    _add_layer(g, f.id, cell, ltype="barrier", strength=4, rez=4)
    fr = scp2.ensure_scp2_state(g.state, f.id)
    fr["credits"] = 10
    # Insurgency installs an Infiltrator (power 2, boost 1) → needs +2 power = 2 credits
    op = scp2.make_operative("Infiltrator", "barrier", 2, boost=1)
    oh = _hand(g, i.id, op)
    _ready(g, i.id, ap=3, credits=5)
    okp, _m, _e = scp2.play_card(g, i.id, oh.id)
    assert okp
    ir = scp2.ensure_scp2_state(g.state, i.id)
    ir["ap"] = 3
    ir["credits"] = 5
    ok, msg, _ = scp2.infiltrate(g, i.id, ("cell", cell["id"]))
    assert ok, msg
    assert ir["liberation_points"] == 2, "breaker should have cracked the barrier"
    assert ir["credits"] == 3, "should have paid 2 to boost through strength 4"


def test_sentry_neutralize_deals_damage_when_no_operative():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2)
    _add_layer(g, f.id, cell, ltype="sentry", strength=3, rez=3)
    fr = scp2.ensure_scp2_state(g.state, f.id)
    fr["credits"] = 10
    junk = _hand(g, i.id, scp2.make_event("Junk"))
    ir = _ready(g, i.id, ap=3, credits=10)
    assert len(scp2.hand_ids(g.state, i.id)) == 1
    scp2.infiltrate(g, i.id, ("cell", cell["id"]))
    assert len(scp2.hand_ids(g.state, i.id)) == 0, "sentry should have dealt 1 damage (discard)"


def test_sensor_exposes():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2)
    _add_layer(g, f.id, cell, ltype="sensor", strength=2, rez=2)
    fr = scp2.ensure_scp2_state(g.state, f.id)
    fr["credits"] = 10
    ir = _ready(g, i.id, ap=3, credits=10)
    scp2.infiltrate(g, i.id, ("cell", cell["id"]))
    assert ir["exposed"] == 1


def test_trap_punishes_and_yields_no_liberation():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2, trap=True)
    # two cards to absorb the default 2 trap damage
    _hand(g, i.id, scp2.make_event("J1"))
    _hand(g, i.id, scp2.make_event("J2"))
    ir = _ready(g, i.id, ap=3, credits=10)
    scp2.infiltrate(g, i.id, ("cell", cell["id"]))
    assert ir["liberation_points"] == 0, "a trap must not grant liberation"
    assert len(scp2.hand_ids(g.state, i.id)) == 0, "trap should have dealt 2 damage"
    assert cell["anomaly"] is None, "the trap is consumed"


# --------------------------------------------------------------------------- win conditions
def test_foundation_wins_at_containment_target():
    g, f, i = _setup()
    fr = scp2.ensure_scp2_state(g.state, f.id)
    fr["containment_points"] = scp2.CONTAINMENT_TARGET - 1
    obj, cell = _install_anomaly(g, f.id, threshold=1, value=2)
    scp2.advance(g, f.id, obj.id)
    scp2.contain(g, f.id, obj.id)
    assert fr["containment_points"] >= scp2.CONTAINMENT_TARGET
    assert g.state.players[i.id].has_lost
    assert not g.state.players[f.id].has_lost


def test_insurgency_wins_at_liberation_target():
    g, f, i = _setup()
    ir = scp2.ensure_scp2_state(g.state, i.id)
    ir["liberation_points"] = scp2.LIBERATION_TARGET - 2
    obj, cell = _install_anomaly(g, f.id, value=2)
    _ready(g, i.id, ap=3, credits=10)
    scp2.infiltrate(g, i.id, ("cell", cell["id"]))
    assert ir["liberation_points"] >= scp2.LIBERATION_TARGET
    assert g.state.players[f.id].has_lost


def test_total_breach_catastrophe_is_insurgency_win():
    g, f, i = _setup()
    fr = scp2.ensure_scp2_state(g.state, f.id)
    fr["total_breach"] = scp2.BREACH_CATASTROPHE
    scp2.check_scp2_win(g)
    assert g.state.players[f.id].has_lost
    assert not g.state.players[i.id].has_lost


def test_burnout_is_foundation_soft_kill():
    g, f, i = _setup()
    # empty insurgency hand → any damage burns them out
    scp2.deal_damage(g, i.id, 1)
    scp2.check_scp2_win(g)
    assert g.state.players[i.id].has_lost
    assert not g.state.players[f.id].has_lost


# --------------------------------------------------------------------------- fog of war
def test_fog_of_war_hides_foundation_facedown_from_insurgency():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, threshold=3, value=2)
    scp2.advance(g, f.id, obj.id)  # 1 advancement (public)
    _add_layer(g, f.id, cell, ltype="barrier", strength=4, rez=4)

    iview = scp2.public_board(g.state, i.id)
    icell = iview["players"][f.id]["cells"][0]
    assert icell["anomaly"]["hidden"] is True
    assert icell["anomaly"]["name"] == "[FACE-DOWN]"
    assert icell["anomaly"]["advancement"] == 1, "advancement heat is public"
    assert icell["layers"][0]["hidden"] is True
    assert icell["layers"][0]["name"] == "[FACE-DOWN]"

    fview = scp2.public_board(g.state, f.id)
    fcell = fview["players"][f.id]["cells"][0]
    assert fcell["anomaly"]["hidden"] is False
    assert fcell["anomaly"]["name"] == "SCP-TEST", "owner sees their own card"


def test_no_facedown_identity_leaks_in_insurgency_payload():
    g, f, i = _setup()
    _install_anomaly(g, f.id)
    iview = scp2.public_board(g.state, i.id)
    # The literal Foundation anomaly name must never appear in the Insurgency's payload.
    import json
    blob = json.dumps(iview)
    assert "SCP-TEST" not in blob


# --------------------------------------------------------------------------- turn manager smoke
def test_turn_manager_runs_a_turn():
    g = Game(mode="scp2")
    f = g.add_player("F")
    i = g.add_player("I")
    fdeck = [scp2.make_anomaly(f"A{n}", 3, 1) for n in range(12)]
    ideck = [scp2.make_operative(f"Op{n}", "barrier", 2) for n in range(12)]
    scp2.setup_scp2_game(g, f, i, foundation_deck=fdeck, insurgency_deck=ideck)

    class _Stub:
        async def take_turn(self, pid, state, game):
            return []

    g.turn_manager.set_ai_handler(_Stub())
    g.turn_manager.set_ai_player(f.id)
    g.turn_manager.set_ai_player(i.id)

    assert len(scp2.hand_ids(g.state, f.id)) == 5
    assert len(scp2.deck_ids(g.state, f.id)) == 7  # 12 deck - 5 opening hand
    asyncio.run(g.turn_manager.run_turn(f.id))
    fr = scp2.ensure_scp2_state(g.state, f.id)
    assert fr["ap"] == scp2.AP_PER_TURN, "AP refreshed at turn start"
    assert len(scp2.deck_ids(g.state, f.id)) == 6, "drew 1 for the turn"
    # drew to 6, took no actions, then end-of-turn discard trims back to MAX_HAND.
    assert len(scp2.hand_ids(g.state, f.id)) == scp2.MAX_HAND


# --------------------------------------------------------------------------- Phase-2 engine: activated abilities
def test_activate_ability_fires_and_costs():
    g, f, i = _setup()
    fired = {"n": 0}

    def _abil(game, pid, obj, target):
        fired["n"] += 1
        return scp2.add_credits(game.state, pid, 3)

    cd = scp2.make_asset("Generator", ability=_abil, ability_cost=1, ability_ap=1)
    obj = _hand(g, f.id, cd)
    r = _ready(g, f.id, ap=2, credits=2)
    okp, _m, _e = scp2.play_card(g, f.id, obj.id)
    assert okp and r["ap"] == 1, "play spent 1 AP"
    ok, msg, _ = scp2.activate_ability(g, f.id, obj.id)
    assert ok, msg
    assert fired["n"] == 1, "the formerly-dead ability callback actually fired"
    assert r["ap"] == 0, "ability spent its 1 AP"
    assert r["credits"] == 4, "paid 1, gained 3 (2-1+3)"


def test_activate_ability_blocked_without_ap():
    g, f, i = _setup()
    cd = scp2.make_asset("Generator", ability=lambda *a: [], ability_ap=1)
    obj = _hand(g, f.id, cd)
    _ready(g, f.id, ap=1, credits=5)
    scp2.play_card(g, f.id, obj.id)  # consumes the only AP
    ok, msg, _ = scp2.activate_ability(g, f.id, obj.id)
    assert not ok and "action" in msg.lower()


# --------------------------------------------------------------------------- Phase-2 engine: identity passives
def test_identity_passive_applies_at_setup():
    g = Game(mode="scp2")
    f = g.add_player("F")
    i = g.add_player("I")

    def _f_passive(game, pid, obj):
        scp2.ensure_scp2_state(game.state, pid)["max_hand"] = 6
        return []

    def _i_passive(game, pid, obj):
        return scp2.add_credits(game.state, pid, 2)

    fid_card = scp2.make_identity("Site-19", scp2.FOUNDATION, passive=_f_passive)
    iid_card = scp2.make_identity("Black Queen", scp2.INSURGENCY, passive=_i_passive)
    fdeck = [scp2.make_anomaly(f"A{n}", 3, 1) for n in range(12)]
    ideck = [scp2.make_operative(f"Op{n}", "barrier", 2) for n in range(12)]
    scp2.setup_scp2_game(g, f, i, foundation_deck=fdeck, insurgency_deck=ideck,
                         foundation_identity=fid_card, insurgency_identity=iid_card)
    assert scp2.ensure_scp2_state(g.state, f.id)["max_hand"] == 6
    assert scp2.ensure_scp2_state(g.state, i.id)["credits"] == scp2.STARTING_CREDITS + 2


def test_max_hand_modifier_honored_by_discard():
    g, f, i = _setup()
    scp2.ensure_scp2_state(g.state, f.id)["max_hand"] = 6
    for n in range(7):
        _hand(g, f.id, scp2.make_anomaly(f"A{n}", 3, 1))
    scp2.discard_to_max(g, f.id)
    assert len(scp2.hand_ids(g.state, f.id)) == 6


# --------------------------------------------------------------------------- Phase-2 engine: reinforcement
def test_reinforce_raises_effective_strength_and_break_cost():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2)
    layer = _add_layer(g, f.id, cell, ltype="barrier", strength=4, rez=4)
    scp2.reinforce(g.state, layer, 2)  # effective strength now 6
    fr = scp2.ensure_scp2_state(g.state, f.id)
    fr["credits"] = 10
    op = scp2.make_operative("Infiltrator", "barrier", 2, boost=1)
    oh = _hand(g, i.id, op)
    _ready(g, i.id, ap=3, credits=3)
    scp2.play_card(g, i.id, oh.id)
    ir = scp2.ensure_scp2_state(g.state, i.id)
    ir["ap"], ir["credits"] = 3, 3        # power2 + 3 cells = 5 < 6 → cannot break
    scp2.infiltrate(g, i.id, ("cell", cell["id"]))
    assert ir["liberation_points"] == 0, "reinforced str-6 barrier resists 3 cells"
    ir["ap"], ir["credits"] = 3, 4        # power2 + 4 cells = 6 ≥ 6 → breaks
    scp2.infiltrate(g, i.id, ("cell", cell["id"]))
    assert ir["liberation_points"] == 2, "4 cells boosts through str-6"


# --------------------------------------------------------------------------- Phase-2 engine: effect helpers
def test_effect_helpers_breach_expose_mill_trashtool():
    g, f, i = _setup()
    fr = scp2.ensure_scp2_state(g.state, f.id)
    ir = scp2.ensure_scp2_state(g.state, i.id)
    scp2.add_breach(g, 3)
    assert fr["total_breach"] == 3
    scp2.expose(g, 2)
    assert ir["exposed"] == 2
    for n in range(3):
        cd = scp2.make_anomaly("x", 3, 1)
        g.create_object(name=cd.name, owner_id=f.id, zone=ZoneType.LIBRARY,
                        characteristics=cd.characteristics, card_def=cd)
    before = len(scp2.deck_ids(g.state, f.id))
    scp2.mill(g, f.id, 2)
    assert len(scp2.deck_ids(g.state, f.id)) == before - 2
    tool = _hand(g, i.id, scp2.make_tool("Gizmo"))
    _ready(g, i.id)
    scp2.play_card(g, i.id, tool.id)
    assert tool.id in ir["rig"]
    scp2.trash_a_tool(g)
    assert tool.id not in ir["rig"], "soft-kill trashed the tool"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
