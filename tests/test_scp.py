"""Phase-1 unit tests for the scp engine (SCP: SECURE / CONTAIN / SUBVERT).

Covers every mechanic in docs/design/scp_rules.md §4-7: resources/AP, install (face-down),
advance/contain, the infiltration run (rez/break/subroutine/access), free/steal, traps,
all four win conditions, fog-of-war redaction, and a turn-manager smoke test.

Run: HYPERDRAFT_STRICT=1 PYTHONPATH=. python3 -m pytest tests/test_scp.py -q
"""

import asyncio

import pytest

from src.engine.game import Game
from src.engine import scp
from src.engine.types import ZoneType


# --------------------------------------------------------------------------- helpers
def _setup():
    g = Game(mode="scp")
    f = g.add_player("Foundation")
    i = g.add_player("Insurgency")
    scp.setup_scp_player(g, f, scp.FOUNDATION)
    scp.setup_scp_player(g, i, scp.INSURGENCY)
    return g, f, i


def _hand(g, pid, cd):
    return g.create_object(name=cd.name, owner_id=pid, zone=ZoneType.HAND,
                           characteristics=cd.characteristics, card_def=cd)


def _ready(g, pid, ap=10, credits=20):
    r = scp.ensure_scp_state(g.state, pid)
    r["ap"] = ap
    r["credits"] = credits
    return r


def _install_anomaly(g, fid, *, threshold=4, value=2, trap=False, breach_on_free=None):
    _ready(g, fid)
    cd = scp.make_anomaly("SCP-TEST", threshold, value, trap=trap, breach_on_free=breach_on_free)
    obj = _hand(g, fid, cd)
    ok, msg, _ = scp.play_card(g, fid, obj.id)
    assert ok, msg
    cell = scp.ensure_scp_state(g.state, fid)["cells"][-1]
    return obj, cell


def _add_layer(g, fid, cell, *, ltype="barrier", strength=4, rez=4, sub=None):
    _ready(g, fid)
    cd = scp.make_layer("LAYER", ltype, strength, rez, sub=sub)
    obj = _hand(g, fid, cd)
    ok, msg, _ = scp.play_card(g, fid, obj.id, target=("cell", cell["id"]))
    assert ok, msg
    return obj


# --------------------------------------------------------------------------- resources
def test_gain_credits_spends_ap():
    g, f, i = _setup()
    r = _ready(g, f.id, ap=1, credits=5)
    ok, _m, _e = scp.gain_credits(g, f.id)
    assert ok and r["credits"] == 5 + scp.GAIN_AMOUNT and r["ap"] == 0
    ok2, _m2, _e2 = scp.gain_credits(g, f.id)
    assert not ok2, "should fail with no AP"


def test_play_card_costs_ap_and_credits():
    g, f, i = _setup()
    r = _ready(g, f.id, ap=1, credits=3)
    cd = scp.make_anomaly("Pricey", 3, 1, cost=2)
    obj = _hand(g, f.id, cd)
    ok, msg, _ = scp.play_card(g, f.id, obj.id)
    assert ok, msg
    assert r["ap"] == 0 and r["credits"] == 1


# --------------------------------------------------------------------------- install / advance / contain
def test_install_anomaly_is_facedown_in_a_cell():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id)
    assert cell["anomaly"] == obj.id
    assert getattr(obj.state, "scp_facedown") is True
    assert getattr(obj.state, "scp_advancement") == 0
    assert obj.zone == ZoneType.BATTLEFIELD


def test_advance_then_contain_scores_value():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, threshold=3, value=2)
    for _ in range(3):
        ok, msg, _ = scp.advance(g, f.id, obj.id)
        assert ok, msg
    assert getattr(obj.state, "scp_advancement") == 3
    ok, msg, _ = scp.contain(g, f.id, obj.id)
    assert ok, msg
    fr = scp.ensure_scp_state(g.state, f.id)
    assert fr["containment_points"] == 2
    assert getattr(obj.state, "scp_status") == "contained"
    assert getattr(obj.state, "scp_facedown") is False


def test_contain_below_threshold_fails():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, threshold=4, value=2)
    scp.advance(g, f.id, obj.id)  # only 1 of 4
    ok, msg, _ = scp.contain(g, f.id, obj.id)
    assert not ok and "advancement" in msg.lower()


# --------------------------------------------------------------------------- contain is one-shot
# Regression: contain() only checked threshold (which stays met once an anomaly locks) and the
# anomaly's role — it did NOT check that the anomaly is still a live agenda on a cell. advance() has
# always rejected a non-live anomaly, but contain() didn't, so the REST/human SCP_CONTAIN path could
# re-submit it to DOUBLE-SCORE a Value (and re-fire on_contain), or score a freed anomaly straight out
# of the discard. The cell binding (not the sticky scp_status) is the source of truth for "advanceable".
def test_cannot_recontain_an_already_contained_anomaly():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, threshold=1, value=2)
    scp.advance(g, f.id, obj.id)
    fr = scp.ensure_scp_state(g.state, f.id)
    ok, _m, _ = scp.contain(g, f.id, obj.id)
    assert ok and fr["containment_points"] == 2, "first contain scores the Value"
    ok2, msg2, _ = scp.contain(g, f.id, obj.id)
    assert not ok2 and "advanceable" in msg2.lower(), "re-containing is rejected — no double-score"
    assert fr["containment_points"] == 2, "the Value is banked exactly once"
    oka, _ma, _ = scp.advance(g, f.id, obj.id)
    assert not oka, "a contained anomaly is off its cell → not advanceable"


def test_cannot_contain_or_advance_a_freed_anomaly_from_the_discard():
    # Sibling hole: _free_anomaly leaves a freed anomaly's status as "advancing", so a threshold-only
    # check would let the Foundation contain an anomaly the Insurgency already stole. Free one that had
    # met its threshold (containable but not yet contained), then prove neither verb touches it.
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, threshold=2, value=2)
    scp.advance(g, f.id, obj.id); scp.advance(g, f.id, obj.id)  # met threshold, not yet contained
    _ready(g, i.id, ap=3, credits=10)
    scp.infiltrate(g, i.id, ("cell", cell["id"]))  # undefended → the Insurgency frees it
    assert obj.zone == ZoneType.GRAVEYARD and cell["anomaly"] is None, "the anomaly was stolen"
    fr = scp.ensure_scp_state(g.state, f.id)
    ok, msg, _ = scp.contain(g, f.id, obj.id)
    assert not ok and "advanceable" in msg.lower(), "cannot contain a stolen anomaly out of the discard"
    assert fr["containment_points"] == 0, "the freed anomaly scores the Foundation nothing"
    oka, _ma, _ = scp.advance(g, f.id, obj.id)
    assert not oka, "nor can it be advanced in the discard"


# --------------------------------------------------------------------------- infiltration
def test_infiltrate_undefended_cell_frees_anomaly():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2)
    ir = _ready(g, i.id, ap=3, credits=10)
    fr = scp.ensure_scp_state(g.state, f.id)
    ok, msg, _ = scp.infiltrate(g, i.id, ("cell", cell["id"]))
    assert ok, msg
    assert ir["liberation_points"] == 2
    assert fr["total_breach"] == 2
    assert cell["anomaly"] is None


def test_rezzed_barrier_with_no_breaker_ends_run():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2)
    _add_layer(g, f.id, cell, ltype="barrier", strength=4, rez=4)
    fr = scp.ensure_scp_state(g.state, f.id)
    fr["credits"] = 10  # enough to rez
    ir = _ready(g, i.id, ap=3, credits=10)  # but no breaker
    ok, msg, _ = scp.infiltrate(g, i.id, ("cell", cell["id"]))
    assert ok, msg
    assert ir["liberation_points"] == 0, "barrier should have stopped the run"
    assert cell["anomaly"] == obj.id, "anomaly must still be contained-in-progress"


def test_breaker_cracks_barrier_and_frees():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2)
    _add_layer(g, f.id, cell, ltype="barrier", strength=4, rez=4)
    fr = scp.ensure_scp_state(g.state, f.id)
    fr["credits"] = 10
    # Insurgency installs an Infiltrator (power 2, boost 1) → needs +2 power = 2 credits
    op = scp.make_operative("Infiltrator", "barrier", 2, boost=1)
    oh = _hand(g, i.id, op)
    _ready(g, i.id, ap=3, credits=5)
    okp, _m, _e = scp.play_card(g, i.id, oh.id)
    assert okp
    ir = scp.ensure_scp_state(g.state, i.id)
    ir["ap"] = 3
    ir["credits"] = 5
    ok, msg, _ = scp.infiltrate(g, i.id, ("cell", cell["id"]))
    assert ok, msg
    assert ir["liberation_points"] == 2, "breaker should have cracked the barrier"
    assert ir["credits"] == 3, "should have paid 2 to boost through strength 4"


def test_sentry_neutralize_deals_damage_when_no_operative():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2)
    _add_layer(g, f.id, cell, ltype="sentry", strength=3, rez=3)
    fr = scp.ensure_scp_state(g.state, f.id)
    fr["credits"] = 10
    junk = _hand(g, i.id, scp.make_event("Junk"))
    ir = _ready(g, i.id, ap=3, credits=10)
    assert len(scp.hand_ids(g.state, i.id)) == 1
    scp.infiltrate(g, i.id, ("cell", cell["id"]))
    assert len(scp.hand_ids(g.state, i.id)) == 0, "sentry should have dealt 1 damage (discard)"


def test_sensor_exposes():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2)
    _add_layer(g, f.id, cell, ltype="sensor", strength=2, rez=2)
    fr = scp.ensure_scp_state(g.state, f.id)
    fr["credits"] = 10
    ir = _ready(g, i.id, ap=3, credits=10)
    scp.infiltrate(g, i.id, ("cell", cell["id"]))
    assert ir["exposed"] == 1


def test_trap_punishes_and_yields_no_liberation():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2, trap=True)
    # two cards to absorb the default 2 trap damage
    _hand(g, i.id, scp.make_event("J1"))
    _hand(g, i.id, scp.make_event("J2"))
    ir = _ready(g, i.id, ap=3, credits=10)
    scp.infiltrate(g, i.id, ("cell", cell["id"]))
    assert ir["liberation_points"] == 0, "a trap must not grant liberation"
    assert len(scp.hand_ids(g.state, i.id)) == 0, "trap should have dealt 2 damage"
    assert cell["anomaly"] is None, "the trap is consumed"


# --------------------------------------------------------------------------- central access (live HQ/Research/Archives)
def test_central_hq_trashes_a_foundation_hand_card():
    g, f, i = _setup()
    _hand(g, f.id, scp.make_anomaly("F-card", 3, 1))  # the Foundation card HQ will strip
    assert len(scp.hand_ids(g.state, f.id)) == 1
    _ready(g, i.id, ap=3, credits=10)
    ok, msg, evs = scp.infiltrate(g, i.id, ("central", "hq"))
    assert ok, msg
    assert len(scp.hand_ids(g.state, f.id)) == 0, "HQ run trashes a Foundation hand card"
    assert any(e.type.name == "SCP_SABOTAGE" and e.payload.get("effect") == "hand_trash" for e in evs)


def test_central_research_mills_top_two():
    g, f, i = _setup()
    for n in range(4):
        cd = scp.make_anomaly(f"D{n}", 3, 1)
        g.create_object(name=cd.name, owner_id=f.id, zone=ZoneType.LIBRARY,
                        characteristics=cd.characteristics, card_def=cd)
    before = len(scp.deck_ids(g.state, f.id))
    _ready(g, i.id, ap=3, credits=10)
    ok, msg, evs = scp.infiltrate(g, i.id, ("central", "research"))
    assert ok, msg
    assert len(scp.deck_ids(g.state, f.id)) == before - 2, "Research run mills the top 2"
    assert any(e.type.name == "SCP_SABOTAGE" and e.payload.get("effect") == "mill" for e in evs)


def test_central_archives_draws_for_the_insurgency():
    g, f, i = _setup()
    for n in range(3):
        cd = scp.make_event(f"I{n}")
        g.create_object(name=cd.name, owner_id=i.id, zone=ZoneType.LIBRARY,
                        characteristics=cd.characteristics, card_def=cd)
    h0, d0 = len(scp.hand_ids(g.state, i.id)), len(scp.deck_ids(g.state, i.id))
    _ready(g, i.id, ap=3, credits=10)
    ok, msg, evs = scp.infiltrate(g, i.id, ("central", "archives"))
    assert ok, msg
    assert len(scp.hand_ids(g.state, i.id)) == h0 + 1, "Archives run draws 1 for the Insurgency"
    assert len(scp.deck_ids(g.state, i.id)) == d0 - 1
    assert any(e.type.name == "SCP_SABOTAGE" and e.payload.get("effect") == "draw" for e in evs)


def test_defended_central_stops_the_run_before_sabotage():
    g, f, i = _setup()
    _ready(g, f.id)
    gate = _hand(g, f.id, scp.make_layer("Gate", "barrier", 4, 4))
    ok, msg, _ = scp.play_card(g, f.id, gate.id, target=("central", "hq"))
    assert ok, msg
    _hand(g, f.id, scp.make_anomaly("F-card", 3, 1))  # would be trashed if the run completed
    fr = scp.ensure_scp_state(g.state, f.id); fr["credits"] = 10  # enough to rez
    _ready(g, i.id, ap=3, credits=10)  # but no breaker
    hand_before = len(scp.hand_ids(g.state, f.id))
    ok, msg, evs = scp.infiltrate(g, i.id, ("central", "hq"))
    assert ok, msg
    assert len(scp.hand_ids(g.state, f.id)) == hand_before, "a rezzed barrier ends the HQ run"
    assert not any(e.type.name == "SCP_SABOTAGE" for e in evs), "no sabotage when the run is stopped"


# --------------------------------------------------------------------------- rez/break mini-game (smart AI policies)
def test_smart_rez_declines_a_breakable_barrier():
    """Rez to stop, not decorate: a barrier the runner can crack is wasted Funding — pass it."""
    from src.ai.scp_adapter import foundation_rez_policy
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2)
    _add_layer(g, f.id, cell, ltype="barrier", strength=3, rez=2)
    fr = scp.ensure_scp_state(g.state, f.id); fr["credits"] = 10  # could afford to rez
    op = scp.make_operative("Infiltrator", "barrier", 2, boost=1)
    oh = _hand(g, i.id, op); _ready(g, i.id, ap=3, credits=5)
    scp.play_card(g, i.id, oh.id)
    ir = scp.ensure_scp_state(g.state, i.id); ir["ap"], ir["credits"] = 3, 5
    ok, msg, _ = scp.infiltrate(g, i.id, ("cell", cell["id"]),
                                rez_policy=foundation_rez_policy(g, i.id))
    assert ok, msg
    assert ir["liberation_points"] == 2, "the run accesses and frees"
    assert ir["credits"] == 5, "barrier passed unrezzed → no boost paid"
    assert fr["credits"] == 10, "Foundation spent no Funding on a futile rez"


def test_smart_rez_stops_an_unbreakable_barrier():
    from src.ai.scp_adapter import foundation_rez_policy
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2)
    _add_layer(g, f.id, cell, ltype="barrier", strength=5, rez=3)
    fr = scp.ensure_scp_state(g.state, f.id); fr["credits"] = 10
    op = scp.make_operative("Infiltrator", "barrier", 2, boost=1)
    oh = _hand(g, i.id, op); _ready(g, i.id, ap=3, credits=2)
    scp.play_card(g, i.id, oh.id)
    ir = scp.ensure_scp_state(g.state, i.id); ir["ap"], ir["credits"] = 3, 2  # 2 + 2 = 4 < 5
    ok, msg, _ = scp.infiltrate(g, i.id, ("cell", cell["id"]),
                                rez_policy=foundation_rez_policy(g, i.id))
    assert ok, msg
    assert ir["liberation_points"] == 0, "an unbreakable barrier ends the run"
    assert fr["credits"] == 7, "Foundation paid 3 to rez the stopping barrier"


def test_smart_break_eats_a_sensor_to_conserve_cells():
    """Greedy rez (default) fires the sensor; the smart break policy eats the expose to save Cells."""
    from src.ai.scp_adapter import insurgency_break_policy
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2)
    _add_layer(g, f.id, cell, ltype="sensor", strength=2, rez=2)
    fr = scp.ensure_scp_state(g.state, f.id); fr["credits"] = 10
    op = scp.make_operative("Ghost", "sensor", 1, boost=1)
    oh = _hand(g, i.id, op); _ready(g, i.id, ap=3, credits=5)
    scp.play_card(g, i.id, oh.id)
    ir = scp.ensure_scp_state(g.state, i.id); ir["ap"], ir["credits"] = 3, 5
    ok, msg, _ = scp.infiltrate(g, i.id, ("cell", cell["id"]),
                                break_policy=insurgency_break_policy(g))
    assert ok, msg
    assert ir["exposed"] == 1, "ate the sensor's expose instead of breaking it"
    assert ir["credits"] == 5, "no Cells spent on the sensor"
    assert ir["liberation_points"] == 2, "run still reached and freed the anomaly"


def test_smart_break_breaks_sensor_once_exposure_is_in_softkill_range():
    from src.ai.scp_adapter import insurgency_break_policy
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2)
    _add_layer(g, f.id, cell, ltype="sensor", strength=2, rez=2)
    fr = scp.ensure_scp_state(g.state, f.id); fr["credits"] = 10
    op = scp.make_operative("Ghost", "sensor", 1, boost=1)
    oh = _hand(g, i.id, op); _ready(g, i.id, ap=3, credits=5)
    scp.play_card(g, i.id, oh.id)
    ir = scp.ensure_scp_state(g.state, i.id)
    ir["ap"], ir["credits"], ir["exposed"] = 3, 5, 2  # already tagged twice → don't climb further
    ok, msg, _ = scp.infiltrate(g, i.id, ("cell", cell["id"]),
                                break_policy=insurgency_break_policy(g))
    assert ok, msg
    assert ir["exposed"] == 2, "broke the sensor rather than eat another tag"
    assert ir["credits"] == 4, "paid 1 Cell to boost Ghost through strength 2"


def test_smart_rez_walls_a_barrier_stack_the_runner_cant_fully_break():
    """Stack-aware rez (review Finding 1): two barriers each breakable *in isolation* must both be
    rezzed so the runner's Cells drain across the whole wall. Judging each alone (the old bug) would
    decline both and hand the runner a free pass through a wall that cumulatively stops them."""
    from src.ai.scp_adapter import foundation_rez_policy
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2)
    _add_layer(g, f.id, cell, ltype="barrier", strength=4, rez=4)
    _add_layer(g, f.id, cell, ltype="barrier", strength=4, rez=4)
    fr = scp.ensure_scp_state(g.state, f.id); fr["credits"] = 20  # can afford both rezzes
    op = scp.make_operative("Infiltrator", "barrier", 2, boost=1)
    oh = _hand(g, i.id, op); _ready(g, i.id, ap=3, credits=3)
    scp.play_card(g, i.id, oh.id)
    ir = scp.ensure_scp_state(g.state, i.id)
    ir["ap"], ir["credits"] = 3, 3  # breaks ONE barrier (cost 2), leaving 1 — can't break the second
    ok, msg, _ = scp.infiltrate(g, i.id, ("cell", cell["id"]),
                                rez_policy=foundation_rez_policy(g, i.id))
    assert ok, msg
    assert ir["liberation_points"] == 0, "the 2-barrier wall stops a runner who can only break one"
    assert cell["anomaly"] == obj.id, "anomaly stays safe behind the wall"


def test_saboteur_boost2_break_cost_boundary():
    """Saboteur breaks Sentries at boost 2 (+1 power per 2 Cells) — the previously-untested branch.
    A Sentry doesn't end the run, so we read the *break cost* + the neutralize, not access denial."""
    # Enough Cells: power 2 + (4 // boost 2 = +2) ≥ str 4 → breaks, pays (4-2)×2 = 4, operative lives.
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2)
    _add_layer(g, f.id, cell, ltype="sentry", strength=4, rez=3)
    scp.ensure_scp_state(g.state, f.id)["credits"] = 20
    oh = _hand(g, i.id, scp.make_operative("Saboteur", "sentry", 2, boost=2))
    _ready(g, i.id, ap=3, credits=4); scp.play_card(g, i.id, oh.id)
    ir = scp.ensure_scp_state(g.state, i.id); ir["ap"], ir["credits"] = 3, 4
    scp.infiltrate(g, i.id, ("cell", cell["id"]))
    assert oh.id in ir["rig"], "broke the Sentry → the operative survives"
    assert ir["credits"] == 0, "paid 4 Cells (deficit 2 × boost 2)"
    assert ir["liberation_points"] == 2

    # Too few Cells: power 2 + (3 // 2 = +1) = 3 < str 4 → can't break → the Saboteur is neutralised.
    g2, f2, i2 = _setup()
    obj2, cell2 = _install_anomaly(g2, f2.id, value=2)
    _add_layer(g2, f2.id, cell2, ltype="sentry", strength=4, rez=3)
    scp.ensure_scp_state(g2.state, f2.id)["credits"] = 20
    oh2 = _hand(g2, i2.id, scp.make_operative("Saboteur", "sentry", 2, boost=2))
    _ready(g2, i2.id, ap=3, credits=3); scp.play_card(g2, i2.id, oh2.id)
    ir2 = scp.ensure_scp_state(g2.state, i2.id); ir2["ap"], ir2["credits"] = 3, 3
    scp.infiltrate(g2, i2.id, ("cell", cell2["id"]))
    assert oh2.id not in ir2["rig"], "couldn't break → the Saboteur is neutralised"
    assert ir2["credits"] == 3, "no Cells spent when it can't break"


# --------------------------------------------------------------------------- win conditions
def test_foundation_wins_at_containment_target():
    g, f, i = _setup()
    fr = scp.ensure_scp_state(g.state, f.id)
    fr["containment_points"] = scp.CONTAINMENT_TARGET - 1
    obj, cell = _install_anomaly(g, f.id, threshold=1, value=2)
    scp.advance(g, f.id, obj.id)
    scp.contain(g, f.id, obj.id)
    assert fr["containment_points"] >= scp.CONTAINMENT_TARGET
    assert g.state.players[i.id].has_lost
    assert not g.state.players[f.id].has_lost


def test_insurgency_wins_at_liberation_target():
    g, f, i = _setup()
    ir = scp.ensure_scp_state(g.state, i.id)
    ir["liberation_points"] = scp.LIBERATION_TARGET - 2
    obj, cell = _install_anomaly(g, f.id, value=2)
    _ready(g, i.id, ap=3, credits=10)
    scp.infiltrate(g, i.id, ("cell", cell["id"]))
    assert ir["liberation_points"] >= scp.LIBERATION_TARGET
    assert g.state.players[f.id].has_lost


def test_total_breach_catastrophe_is_insurgency_win():
    g, f, i = _setup()
    fr = scp.ensure_scp_state(g.state, f.id)
    fr["total_breach"] = scp.BREACH_CATASTROPHE
    scp.check_scp_win(g)
    assert g.state.players[f.id].has_lost
    assert not g.state.players[i.id].has_lost


def test_burnout_is_foundation_soft_kill():
    g, f, i = _setup()
    # empty insurgency hand → any damage burns them out
    scp.deal_damage(g, i.id, 1)
    scp.check_scp_win(g)
    assert g.state.players[i.id].has_lost
    assert not g.state.players[f.id].has_lost


# --------------------------------------------------------------------------- foundation collapse
# When the Foundation can no longer reach Containment (its anomaly supply spent by the Insurgency's
# frees), it has failed its mandate → the Insurgency wins by default. Decisive resolution of the
# old mutual-exhaustion stall (no draw, no turn-cap spin) and the matching human-play hang.
def test_foundation_collapse_when_it_can_no_longer_reach_containment():
    g, f, i = _setup()
    scp.ensure_scp_state(g.state, f.id)["containment_points"] = scp.CONTAINMENT_TARGET - 1
    # no anomalies anywhere in F's hand/deck/board → reachable Containment is stuck below target
    _hand(g, i.id, scp.make_event("Cell-A")); _hand(g, i.id, scp.make_event("Cell-B"))  # hand >= 2
    evs = scp.check_scp_win(g)
    assert g.state.players[f.id].has_lost and not g.state.players[i.id].has_lost
    assert any(e.type.name == "SCP_WIN" and e.payload.get("reason") == "foundation_collapse"
               for e in evs), "the Insurgency wins by Foundation collapse"


def test_no_collapse_while_containment_is_still_reachable():
    # One value-1 anomaly still in the deck keeps reachable == target → the Foundation can still win,
    # so collapse must NOT fire (the rule never robs a winnable game).
    g, f, i = _setup()
    scp.ensure_scp_state(g.state, f.id)["containment_points"] = scp.CONTAINMENT_TARGET - 1
    cd = scp.make_anomaly("Last-Anomaly", threshold=1, value=1)
    g.create_object(name=cd.name, owner_id=f.id, zone=ZoneType.LIBRARY,
                    characteristics=cd.characteristics, card_def=cd)
    _hand(g, i.id, scp.make_event("X")); _hand(g, i.id, scp.make_event("Y"))
    scp.check_scp_win(g)
    assert not g.state.players[f.id].has_lost, "one anomaly short of the target ≠ collapsed"


def test_collapse_defers_to_a_live_burnout_window():
    # Containment is dead, but the Insurgency hand is nearly empty (<2) — a genuine soft-kill window.
    # Collapse must defer so the Foundation isn't robbed of a burnout win; it re-resolves once the
    # Insurgency draws back up to >=2.
    g, f, i = _setup()
    scp.ensure_scp_state(g.state, f.id)["containment_points"] = scp.CONTAINMENT_TARGET - 1
    _hand(g, i.id, scp.make_event("only-card"))  # exactly 1 card in hand
    scp.check_scp_win(g)
    assert not g.state.players[f.id].has_lost, "don't preempt a burnout window (Insurgency hand < 2)"


def test_no_collapse_at_game_start_with_a_stocked_deck():
    # A fully-stocked anomaly deck keeps reachable Containment far above the target, so the arbiter
    # never fires early. (Production games are dealt a real 40-card deck — this guards the rule.)
    g, f, i = _setup()
    for n in range(4):
        cd = scp.make_anomaly(f"A{n}", threshold=3, value=2)  # 4 × value 2 = 8 ≥ target
        g.create_object(name=cd.name, owner_id=f.id, zone=ZoneType.LIBRARY,
                        characteristics=cd.characteristics, card_def=cd)
    _hand(g, i.id, scp.make_event("X")); _hand(g, i.id, scp.make_event("Y"))
    scp.check_scp_win(g)
    assert not g.state.players[f.id].has_lost, "a stocked deck is not a collapse"


# --- collapse vs the recontainment reserve: discard anomalies a Recovery can reclaim are reachable ---
# The reachable-Containment metric excluded the discard entirely, so a recontainment deck whose
# anomalies were all milled/freed to the discard was declared 'mathematically dead' and lost by
# collapse the instant its last board anomaly left — even while it held a Containment Recovery that
# could re-secure one and win. These pin the fix (scp_recovers marks the recovery vector) and, just as
# importantly, that the bound stays a true UPPER bound so a genuine mill-out is still a collapse.
def _gy(g, pid, cd):
    return g.create_object(name=cd.name, owner_id=pid, zone=ZoneType.GRAVEYARD,
                           characteristics=cd.characteristics, card_def=cd)


def test_no_premature_collapse_while_a_recovery_can_reclaim_the_discard():
    g, f, i = _setup()
    scp.ensure_scp_state(g.state, f.id)["containment_points"] = 0
    _gy(g, f.id, scp.make_anomaly("Lost-A", threshold=5, value=3))  # 3 + 3 = target, all in discard
    _gy(g, f.id, scp.make_anomaly("Lost-B", threshold=5, value=3))
    rec = scp.make_operation("Recontain", recovers=True)
    _hand(g, f.id, rec); _hand(g, f.id, rec)  # two recoveries → reclaim both (one anomaly each)
    _hand(g, i.id, scp.make_event("c1")); _hand(g, i.id, scp.make_event("c2"))  # Insurgency hand >= 2
    assert scp._foundation_reachable_containment(g.state, f.id) == 6, "both value-3 anomalies are reclaimable"
    scp.check_scp_win(g)
    assert not g.state.players[f.id].has_lost, "a live recontainment reserve is not a collapse"
    assert scp.evaluate_scp_win(g.state) is None


def test_collapse_still_fires_when_recovery_cannot_cover_the_gap():
    # One Recovery reclaims exactly ONE anomaly (highest-Value first), so two value-3 in the discard
    # with a single Recovery reach only 3 < target → still a collapse. The bound never over-credits.
    g, f, i = _setup()
    scp.ensure_scp_state(g.state, f.id)["containment_points"] = 0
    _gy(g, f.id, scp.make_anomaly("Lost-A", threshold=5, value=3))
    _gy(g, f.id, scp.make_anomaly("Lost-B", threshold=5, value=3))
    _hand(g, f.id, scp.make_operation("Recontain", recovers=True))  # only ONE recovery
    _hand(g, i.id, scp.make_event("c1")); _hand(g, i.id, scp.make_event("c2"))
    assert scp._foundation_reachable_containment(g.state, f.id) == 3, "one Recovery → top-1 Value only"
    assert scp.evaluate_scp_win(g.state) == (i.id, f.id, "foundation_collapse")


def test_a_spent_recovery_in_the_discard_does_not_keep_anomalies_reachable():
    # A one-shot Recovery already spent (sitting in the discard) can't be replayed, so it does NOT
    # count — only hand/deck copies do. Guards the bound against crediting a dead card.
    g, f, i = _setup()
    scp.ensure_scp_state(g.state, f.id)["containment_points"] = 0
    _gy(g, f.id, scp.make_anomaly("Lost", threshold=5, value=3))
    _gy(g, f.id, scp.make_operation("Spent-Recontain", recovers=True))  # in DISCARD, not hand/deck
    _hand(g, i.id, scp.make_event("c1")); _hand(g, i.id, scp.make_event("c2"))
    assert scp._foundation_reachable_containment(g.state, f.id) == 0, "a discarded Recovery is dead"
    assert scp.evaluate_scp_win(g.state) == (i.id, f.id, "foundation_collapse")


def test_an_installed_repeatable_recovery_asset_makes_all_discard_reachable():
    # A repeatable recovery *asset* (scp_recovers on an installed asset) lifts the top-K cap — it can
    # re-secure turn after turn, so every discard anomaly is reachable and no collapse fires.
    g, f, i = _setup()
    fr = scp.ensure_scp_state(g.state, f.id)
    fr["containment_points"] = 0
    for n in range(3):  # 9 pts — only reachable if recovery is repeatable, not one-shot-capped
        _gy(g, f.id, scp.make_anomaly(f"Lost-{n}", threshold=5, value=3))
    asset = scp.make_asset("Recovery Bay", recovers=True)
    ao = g.create_object(name=asset.name, owner_id=f.id, zone=ZoneType.BATTLEFIELD,
                         characteristics=asset.characteristics, card_def=asset)
    fr["assets"].append(ao.id)
    _hand(g, i.id, scp.make_event("c1")); _hand(g, i.id, scp.make_event("c2"))
    assert scp._foundation_reachable_containment(g.state, f.id) == 9, "repeatable recovery → all discard counts"
    assert scp.evaluate_scp_win(g.state) is None


# --------------------------------------------------------------------------- direct point-grant vocabulary
# add_liberation / add_containment / add_breach are the flat-grant vocabulary: a card that moves a win
# counter without freeing/containing an anomaly. All three MUST emit their event (so the client
# animates) and run the win check (so a crossed threshold resolves at once) — never a silent counter
# bump. These guard exactly that invariant; the silent-bump versions they replaced would fail the
# win-check pins. add_breach was the odd one out (win-checked only transitively via play_card's
# trailing check) until it was made self-sufficient like its siblings — its pin is below.
def test_add_liberation_credits_insurgency_and_emits_free():
    g, f, i = _setup()
    events = scp.add_liberation(g, 3)
    assert scp.ensure_scp_state(g.state, i.id)["liberation_points"] == 3
    assert scp.ensure_scp_state(g.state, f.id)["liberation_points"] == 0, "liberation is the Insurgency counter only"
    free = [e for e in events if e.type.name == "SCP_FREE"]
    assert len(free) == 1 and free[0].payload["liberation_points"] == 3 and free[0].payload["value"] == 3


def test_add_containment_credits_foundation_and_emits_contain():
    g, f, i = _setup()
    events = scp.add_containment(g, 2)
    assert scp.ensure_scp_state(g.state, f.id)["containment_points"] == 2
    assert scp.ensure_scp_state(g.state, i.id)["containment_points"] == 0, "containment is the Foundation counter only"
    contain = [e for e in events if e.type.name == "SCP_CONTAIN"]
    assert len(contain) == 1 and contain[0].payload["containment_points"] == 2 and contain[0].payload["value"] == 2


def test_add_liberation_runs_win_check_when_it_crosses_the_target():
    # The load-bearing guard: a direct grant that reaches LIBERATION_TARGET must win NOW, not on the
    # next natural check. The old silent-bump add_liberation would leave both sides alive here.
    g, f, i = _setup()
    scp.ensure_scp_state(g.state, i.id)["liberation_points"] = scp.LIBERATION_TARGET - 1
    events = scp.add_liberation(g, 1)
    assert g.state.players[f.id].has_lost and not g.state.players[i.id].has_lost
    assert any(e.type.name == "SCP_WIN" and e.payload.get("reason") == "liberation" for e in events)


def test_add_containment_runs_win_check_when_it_crosses_the_target():
    g, f, i = _setup()
    scp.ensure_scp_state(g.state, f.id)["containment_points"] = scp.CONTAINMENT_TARGET - 1
    events = scp.add_containment(g, 1)
    assert g.state.players[i.id].has_lost and not g.state.players[f.id].has_lost
    assert any(e.type.name == "SCP_WIN" and e.payload.get("reason") == "containment" for e in events)


def test_add_breach_runs_win_check_when_it_crosses_catastrophe():
    # The missing third pin: a breach bump that reaches BREACH_CATASTROPHE must win NOW, self-
    # sufficiently — not lazily wait for play_card's trailing check (the only reason the pre-fix
    # silent bump wasn't a live bug). A future non-play_card caller (an on-contain closure, a tool
    # ability) would otherwise leave the Insurgency's "unleash" win un-declared with the counter
    # sitting over the line. This asserts add_breach itself declares the win, no wrapper needed.
    g, f, i = _setup()
    scp.ensure_scp_state(g.state, f.id)["total_breach"] = scp.BREACH_CATASTROPHE - 1
    events = scp.add_breach(g, 1)
    assert g.state.players[f.id].has_lost and not g.state.players[i.id].has_lost
    assert any(e.type.name == "SCP_WIN" and e.payload.get("reason") == "total_breach" for e in events)


def test_direct_grant_below_target_does_not_win():
    # No false positive: a grant that stays under the target leaves the game live and emits no SCP_WIN.
    g, f, i = _setup()
    lib_events = scp.add_liberation(g, scp.LIBERATION_TARGET - 1)
    con_events = scp.add_containment(g, scp.CONTAINMENT_TARGET - 1)
    brk_events = scp.add_breach(g, scp.BREACH_CATASTROPHE - 1)
    assert not g.state.players[f.id].has_lost and not g.state.players[i.id].has_lost
    assert not any(e.type.name == "SCP_WIN" for e in lib_events + con_events + brk_events)


# --------------------------------------------------------------------------- evaluate_scp_win (the single win evaluator)
# evaluate_scp_win is the pure §7 ladder that BOTH the engine arbiter (check_scp_win) and the client
# serializer read, so neither can drift from the spec table. These pin every rung, the live-game
# None, and the load-bearing priority order.
def test_evaluate_scp_win_is_none_for_a_live_game():
    g, f, i = _setup()
    assert scp.evaluate_scp_win(g.state) is None


def test_evaluate_scp_win_returns_winner_loser_reason_for_each_axis():
    g, f, i = _setup()
    fr = scp.ensure_scp_state(g.state, f.id)
    ir = scp.ensure_scp_state(g.state, i.id)

    def _reset():
        fr["containment_points"] = 0; fr["total_breach"] = 0
        ir["liberation_points"] = 0; ir["burned_out"] = False

    _reset(); fr["containment_points"] = scp.CONTAINMENT_TARGET
    assert scp.evaluate_scp_win(g.state) == (f.id, i.id, "containment")

    _reset(); ir["burned_out"] = True
    assert scp.evaluate_scp_win(g.state) == (f.id, i.id, "burnout")

    _reset(); ir["liberation_points"] = scp.LIBERATION_TARGET
    assert scp.evaluate_scp_win(g.state) == (i.id, f.id, "liberation")

    _reset(); fr["total_breach"] = scp.BREACH_CATASTROPHE
    assert scp.evaluate_scp_win(g.state) == (i.id, f.id, "total_breach")

    # collapse: one point short, no anomaly supply anywhere, Insurgency still holding cards (>= 2)
    _reset(); fr["containment_points"] = scp.CONTAINMENT_TARGET - 1
    _hand(g, i.id, scp.make_event("c1")); _hand(g, i.id, scp.make_event("c2"))
    assert scp.evaluate_scp_win(g.state) == (i.id, f.id, "foundation_collapse")


def test_evaluate_scp_win_priority_order_is_stable():
    # When two conditions are simultaneously true the ladder order decides — and the order is
    # load-bearing, so pin both a same-faction tie (reason) and a cross-faction tie (the winner).
    g, f, i = _setup()
    fr = scp.ensure_scp_state(g.state, f.id)
    ir = scp.ensure_scp_state(g.state, i.id)

    # Same faction: liberation (rung 3) outranks total_breach (rung 4) — reason is "liberation".
    ir["liberation_points"] = scp.LIBERATION_TARGET
    fr["total_breach"] = scp.BREACH_CATASTROPHE
    assert scp.evaluate_scp_win(g.state) == (i.id, f.id, "liberation")

    # Cross faction (the winner-flipping case): containment (rung 1) outranks liberation (rung 3),
    # so a board where BOTH sides have met their primary win goes to the Foundation.
    fr["containment_points"] = scp.CONTAINMENT_TARGET
    assert scp.evaluate_scp_win(g.state) == (f.id, i.id, "containment")


def test_check_scp_win_declares_the_evaluators_verdict():
    # check_scp_win is just evaluate_scp_win behind the has-lost gate — the SCP_WIN event it emits
    # must carry exactly the winner/loser/reason the evaluator returns from the same state.
    g, f, i = _setup()
    scp.ensure_scp_state(g.state, i.id)["liberation_points"] = scp.LIBERATION_TARGET
    verdict = scp.evaluate_scp_win(g.state)
    evs = scp.check_scp_win(g)
    win = next((e.payload for e in evs if e.type.name == "SCP_WIN"), None)
    assert verdict == (i.id, f.id, "liberation")
    assert win and (win["winner"], win["loser"], win["reason"]) == verdict


# --------------------------------------------------------------------------- AI difficulty (onboarding)
def test_easy_insurgency_leaves_defended_anomalies_for_the_player():
    # Difficulty was cosmetic on the Insurgency seat (easy == medium == hard), so a human Foundation
    # got no onboarding ramp. Easy must now only take UNDEFENDED anomalies — it won't crack a
    # defended cell, giving a new player who learns to defend a beatable bot. Medium still cracks it.
    import asyncio
    from src.ai.scp_adapter import SCPAIAdapter

    def board():
        g, f, i = _setup()
        _obj, cell = _install_anomaly(g, f.id, threshold=5, value=2)
        g.state.objects[cell["anomaly"]].state.scp_advancement = 3     # "hot" → would attract a strike
        _add_layer(g, f.id, cell, ltype="sensor", strength=1, rez=1)   # a token defense (1 layer)
        scp.ensure_scp_state(g.state, f.id)["credits"] = 10
        oh = _hand(g, i.id, scp.make_operative("Breaker", "sensor", 2, boost=1))
        _ready(g, i.id, ap=4, credits=20)
        scp.play_card(g, i.id, oh.id)                                  # Insurgency has a rig
        return g, f, cell

    g, f, cell = board()
    asyncio.run(SCPAIAdapter("easy").take_turn(scp.insurgency_id(g.state), g.state, g))
    assert cell["anomaly"] is not None, "easy Insurgency must leave a DEFENDED anomaly for the player"

    g, f, cell = board()
    asyncio.run(SCPAIAdapter("medium").take_turn(scp.insurgency_id(g.state), g.state, g))
    assert cell["anomaly"] is None, "medium Insurgency cracks the defended cell"


def test_easy_insurgency_still_takes_undefended_anomalies():
    # Positive control for the easy gate: easy is weaker, but it still PLAYS the game — it freely
    # takes UNDEFENDED anomalies (it only declines to crack walls). Guards against easy going inert.
    import asyncio
    from src.ai.scp_adapter import SCPAIAdapter
    g, f, i = _setup()
    _obj, cell = _install_anomaly(g, f.id, threshold=5, value=2)   # NO layer → undefended
    _ready(g, i.id, ap=4, credits=10)
    asyncio.run(SCPAIAdapter("easy").take_turn(scp.insurgency_id(g.state), g.state, g))
    assert cell["anomaly"] is None, "easy still freely frees an UNDEFENDED anomaly"


def test_hard_insurgency_strikes_cells_earlier_than_medium():
    # Hard strikes at advancement >= 2; medium waits for >= 3. (Hard branch was untested — the
    # multi-reviewer panel flagged it, and a hard-Foundation regression had slipped through.)
    import asyncio
    from src.ai.scp_adapter import SCPAIAdapter

    def board():
        g, f, i = _setup()
        _obj, cell = _install_anomaly(g, f.id, threshold=5, value=2)
        g.state.objects[cell["anomaly"]].state.scp_advancement = 2   # hot for HARD (>=2), not medium (>=3)
        _add_layer(g, f.id, cell, ltype="sensor", strength=1, rez=1)
        scp.ensure_scp_state(g.state, f.id)["credits"] = 0           # can't rez → the run passes the sensor
        oh = _hand(g, i.id, scp.make_operative("Breaker", "sensor", 2, boost=1))
        _ready(g, i.id, ap=4, credits=20)
        scp.play_card(g, i.id, oh.id)                               # Insurgency has a rig
        return g, cell

    g, cell = board()
    asyncio.run(SCPAIAdapter("medium").take_turn(scp.insurgency_id(g.state), g.state, g))
    assert cell["anomaly"] is not None, "medium does NOT strike a cell only at advancement 2"

    g, cell = board()
    asyncio.run(SCPAIAdapter("hard").take_turn(scp.insurgency_id(g.state), g.state, g))
    assert cell["anomaly"] is None, "hard strikes the adv-2 cell early and frees it"


def test_sarkic_breach_bonus_hits_events_not_freeing():
    # Load-bearing balance invariant: Sarkic's +1 applies to breach EVENTS (add_breach) only, NOT to
    # freeing (_free_anomaly writes Total Breach directly). Freeing a breach-on-free anomaly under
    # Sarkic must add the un-bonused amount. (Untested before — multi-reviewer finding.)
    g, f, i = _setup()
    scp.ensure_scp_state(g.state, i.id)["breach_event_bonus"] = 1
    _obj, cell = _install_anomaly(g, f.id, value=3, breach_on_free=5)   # Wurm-like
    fr = scp.ensure_scp_state(g.state, f.id); before = fr["total_breach"]
    _ready(g, i.id, ap=3, credits=10)
    scp.infiltrate(g, i.id, ("cell", cell["id"]))                      # free it (undefended)
    assert fr["total_breach"] == before + 5, "freeing adds breach_on_free=5 un-bonused (Sarkic is events-only)"


# --------------------------------------------------------------------------- fog of war
def test_fog_of_war_hides_foundation_facedown_from_insurgency():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, threshold=3, value=2)
    scp.advance(g, f.id, obj.id)  # 1 advancement (public)
    _add_layer(g, f.id, cell, ltype="barrier", strength=4, rez=4)

    iview = scp.public_board(g.state, i.id)
    icell = iview["players"][f.id]["cells"][0]
    assert icell["anomaly"]["hidden"] is True
    assert icell["anomaly"]["name"] == "[FACE-DOWN]"
    assert icell["anomaly"]["advancement"] == 1, "advancement heat is public"
    assert icell["layers"][0]["hidden"] is True
    assert icell["layers"][0]["name"] == "[FACE-DOWN]"

    fview = scp.public_board(g.state, f.id)
    fcell = fview["players"][f.id]["cells"][0]
    assert fcell["anomaly"]["hidden"] is False
    assert fcell["anomaly"]["name"] == "SCP-TEST", "owner sees their own card"


def test_no_facedown_identity_leaks_in_insurgency_payload():
    g, f, i = _setup()
    _install_anomaly(g, f.id)
    iview = scp.public_board(g.state, i.id)
    # The literal Foundation anomaly name must never appear in the Insurgency's payload.
    import json
    blob = json.dumps(iview)
    assert "SCP-TEST" not in blob


# --------------------------------------------------------------------------- turn manager smoke
def test_turn_manager_runs_a_turn():
    g = Game(mode="scp")
    f = g.add_player("F")
    i = g.add_player("I")
    fdeck = [scp.make_anomaly(f"A{n}", 3, 1) for n in range(12)]
    ideck = [scp.make_operative(f"Op{n}", "barrier", 2) for n in range(12)]
    scp.setup_scp_game(g, f, i, foundation_deck=fdeck, insurgency_deck=ideck)

    class _Stub:
        async def take_turn(self, pid, state, game):
            return []

    g.turn_manager.set_ai_handler(_Stub())
    g.turn_manager.set_ai_player(f.id)
    g.turn_manager.set_ai_player(i.id)

    assert len(scp.hand_ids(g.state, f.id)) == 5
    assert len(scp.deck_ids(g.state, f.id)) == 7  # 12 deck - 5 opening hand
    asyncio.run(g.turn_manager.run_turn(f.id))
    fr = scp.ensure_scp_state(g.state, f.id)
    assert fr["ap"] == scp.AP_PER_TURN, "AP refreshed at turn start"
    assert len(scp.deck_ids(g.state, f.id)) == 6, "drew 1 for the turn"
    # drew to 6, took no actions, then end-of-turn discard trims back to MAX_HAND.
    assert len(scp.hand_ids(g.state, f.id)) == scp.MAX_HAND


# --------------------------------------------------------------------------- Phase-2 engine: activated abilities
def test_activate_ability_fires_and_costs():
    g, f, i = _setup()
    fired = {"n": 0}

    def _abil(game, pid, obj, target):
        fired["n"] += 1
        return scp.add_credits(game.state, pid, 3)

    cd = scp.make_asset("Generator", ability=_abil, ability_cost=1, ability_ap=1)
    obj = _hand(g, f.id, cd)
    r = _ready(g, f.id, ap=2, credits=2)
    okp, _m, _e = scp.play_card(g, f.id, obj.id)
    assert okp and r["ap"] == 1, "play spent 1 AP"
    ok, msg, _ = scp.activate_ability(g, f.id, obj.id)
    assert ok, msg
    assert fired["n"] == 1, "the formerly-dead ability callback actually fired"
    assert r["ap"] == 0, "ability spent its 1 AP"
    assert r["credits"] == 4, "paid 1, gained 3 (2-1+3)"


def test_activate_ability_blocked_without_ap():
    g, f, i = _setup()
    cd = scp.make_asset("Generator", ability=lambda *a: [], ability_ap=1)
    obj = _hand(g, f.id, cd)
    _ready(g, f.id, ap=1, credits=5)
    scp.play_card(g, f.id, obj.id)  # consumes the only AP
    ok, msg, _ = scp.activate_ability(g, f.id, obj.id)
    assert not ok and "action" in msg.lower()


# --------------------------------------------------------------------------- Phase-2 engine: identity passives
def test_identity_passive_applies_at_setup():
    g = Game(mode="scp")
    f = g.add_player("F")
    i = g.add_player("I")

    def _f_passive(game, pid, obj):
        scp.ensure_scp_state(game.state, pid)["max_hand"] = 6
        return []

    def _i_passive(game, pid, obj):
        return scp.add_credits(game.state, pid, 2)

    fid_card = scp.make_identity("Site-19", scp.FOUNDATION, passive=_f_passive)
    iid_card = scp.make_identity("Black Queen", scp.INSURGENCY, passive=_i_passive)
    fdeck = [scp.make_anomaly(f"A{n}", 3, 1) for n in range(12)]
    ideck = [scp.make_operative(f"Op{n}", "barrier", 2) for n in range(12)]
    scp.setup_scp_game(g, f, i, foundation_deck=fdeck, insurgency_deck=ideck,
                         foundation_identity=fid_card, insurgency_identity=iid_card)
    assert scp.ensure_scp_state(g.state, f.id)["max_hand"] == 6
    assert scp.ensure_scp_state(g.state, i.id)["credits"] == scp.STARTING_CREDITS + 2


def test_max_hand_modifier_honored_by_discard():
    g, f, i = _setup()
    scp.ensure_scp_state(g.state, f.id)["max_hand"] = 6
    for n in range(7):
        _hand(g, f.id, scp.make_anomaly(f"A{n}", 3, 1))
    scp.discard_to_max(g, f.id)
    assert len(scp.hand_ids(g.state, f.id)) == 6


# --------------------------------------------------------------------------- Phase-2 engine: reinforcement
def test_reinforce_raises_effective_strength_and_break_cost():
    g, f, i = _setup()
    obj, cell = _install_anomaly(g, f.id, value=2)
    layer = _add_layer(g, f.id, cell, ltype="barrier", strength=4, rez=4)
    scp.reinforce(g.state, layer, 2)  # effective strength now 6
    fr = scp.ensure_scp_state(g.state, f.id)
    fr["credits"] = 10
    op = scp.make_operative("Infiltrator", "barrier", 2, boost=1)
    oh = _hand(g, i.id, op)
    _ready(g, i.id, ap=3, credits=3)
    scp.play_card(g, i.id, oh.id)
    ir = scp.ensure_scp_state(g.state, i.id)
    ir["ap"], ir["credits"] = 3, 3        # power2 + 3 cells = 5 < 6 → cannot break
    scp.infiltrate(g, i.id, ("cell", cell["id"]))
    assert ir["liberation_points"] == 0, "reinforced str-6 barrier resists 3 cells"
    ir["ap"], ir["credits"] = 3, 4        # power2 + 4 cells = 6 ≥ 6 → breaks
    scp.infiltrate(g, i.id, ("cell", cell["id"]))
    assert ir["liberation_points"] == 2, "4 cells boosts through str-6"


# --------------------------------------------------------------------------- Phase-2 engine: effect helpers
def test_effect_helpers_breach_expose_mill_trashtool():
    g, f, i = _setup()
    fr = scp.ensure_scp_state(g.state, f.id)
    ir = scp.ensure_scp_state(g.state, i.id)
    scp.add_breach(g, 3)
    assert fr["total_breach"] == 3
    scp.expose(g, 2)
    assert ir["exposed"] == 2
    for n in range(3):
        cd = scp.make_anomaly("x", 3, 1)
        g.create_object(name=cd.name, owner_id=f.id, zone=ZoneType.LIBRARY,
                        characteristics=cd.characteristics, card_def=cd)
    before = len(scp.deck_ids(g.state, f.id))
    scp.mill(g, f.id, 2)
    assert len(scp.deck_ids(g.state, f.id)) == before - 2
    tool = _hand(g, i.id, scp.make_tool("Gizmo"))
    _ready(g, i.id)
    scp.play_card(g, i.id, tool.id)
    assert tool.id in ir["rig"]
    scp.trash_a_tool(g)
    assert tool.id not in ir["rig"], "soft-kill trashed the tool"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
