"""Unit tests for Foundations Beyond (FBN) engine extensions.

Covers all eight new mechanics (Cluster 1-7) plus the three alt-wins,
exercising each through the public engine surface using synthetic cards
built via the FBN helpers. Mirrors the fixture pattern from
``tests/test_scp_interceptors.py``.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cards.scp.foundations_beyond.helpers import (
    _annihilation_wave,
    _compleation,
    _dragon_hoard,
    _fbn_card,
    _leyline_saturation,
    _mnestic_personnel,
    _phylactery_audit,
    _planar_rift,
    _spark_containment,
    _wurm_devourer,
)
from src.engine import scp
from src.engine.game import Game
from src.engine.types import CardType, EventType, ZoneType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _setup():
    """Return (game, p1, p2) with two initialized SCP Sites."""
    game = Game(mode="scp")
    p1 = game.add_player("Site-A")
    p2 = game.add_player("Site-B")
    game.setup_scp_player(p1, [])
    game.setup_scp_player(p2, [])
    return game, p1, p2


def _make_anomaly(name, **kwargs):
    """Cheap FBN anomaly factory for tests. Default 1/1/1 with 0 red_tape."""
    defaults = dict(text="test", subtypes=set(), red_tape=0, containment=1, curiosity=1, hazard=1)
    defaults.update(kwargs)
    return _fbn_card(name, CardType.SCP_ANOMALY, **defaults)


def _make_personnel(name, *, skills=None, subtypes=None, **kwargs):
    """Cheap FBN personnel factory for tests."""
    return _fbn_card(
        name, CardType.SCP_PERSONNEL,
        text="test", red_tape=0, skills=skills or {"research": 1, "contain": 1},
        subtypes=set(subtypes or set()),
        **kwargs,
    )


def _put_in_play(game, player, card_def, *, status="active", subtype_index=None):
    """Materialize ``card_def`` as a battlefield object controlled by ``player``."""
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    obj.state.scp_status = status
    types = set(card_def.characteristics.types)
    if CardType.SCP_ANOMALY in types and status == "active":
        scp.ensure_scp_state(game.state, player.id)
        game.state.scp_anomalies.setdefault(player.id, []).append(obj.id)
    elif CardType.SCP_PERSONNEL in types and status == "active":
        scp.ensure_scp_state(game.state, player.id)
        game.state.scp_personnel.setdefault(player.id, []).append(obj.id)
    elif CardType.SCP_FACILITY in types and status == "active":
        scp.ensure_scp_state(game.state, player.id)
        game.state.scp_facilities.setdefault(player.id, []).append(obj.id)
    elif CardType.SCP_MANDATE in types and status == "active":
        scp.ensure_scp_state(game.state, player.id)
        game.state.scp_mandates.setdefault(player.id, []).append(obj.id)
    return obj


def _snap_site(game, pid):
    return dict(scp.site(game.state, pid))


def _site_delta(before, after):
    out = {}
    for k in set(before) | set(after):
        b = before.get(k, 0)
        a = after.get(k, 0)
        if isinstance(b, (int, float)) and isinstance(a, (int, float)):
            out[k] = a - b
    return out


# ---------------------------------------------------------------------------
# Cluster 1: Compleation Vector
# ---------------------------------------------------------------------------


def test_compleation_vector_places_counters_on_highest_skill_target():
    """End-of-turn tick should drop N counters on the strongest opposing personnel."""
    game, p1, p2 = _setup()
    # Opponent runs a Compleation Vector 2 anomaly.
    anomaly_def = _compleation(_make_anomaly("Vector Bloom"), 2)
    _put_in_play(game, p2, anomaly_def)
    # Active player has two personnel, only one of which is high-skill.
    weak = _make_personnel("Intern", skills={"research": 1})
    strong = _make_personnel("Senior", skills={"research": 3, "contain": 3})
    _put_in_play(game, p1, weak)
    strong_obj = _put_in_play(game, p1, strong)
    scp.apply_compleation_vector(game, p1.id)
    assert strong_obj.state.scp_compleation == 2
    assert any(
        e.type == EventType.SCP_CONTROL_SWAP for e in game.state.event_log
    ) is False  # Only 2 counters; no swap yet.


def test_compleation_skips_mnestic_personnel():
    """Mnestic-tagged personnel should never receive compleation counters."""
    game, p1, p2 = _setup()
    anomaly_def = _compleation(_make_anomaly("Vector Bloom"), 1)
    _put_in_play(game, p2, anomaly_def)
    mnestic = _mnestic_personnel(_make_personnel("Memory Keeper", skills={"research": 5}))
    backup = _make_personnel("Junior", skills={"research": 1})
    mnestic_obj = _put_in_play(game, p1, mnestic)
    backup_obj = _put_in_play(game, p1, backup)
    scp.apply_compleation_vector(game, p1.id)
    assert mnestic_obj.state.scp_compleation == 0, "Mnestic should be skipped"
    assert backup_obj.state.scp_compleation == 1, "Backup should be the target"


def test_compleation_control_swap_at_threshold():
    """At >=3 counters the personnel's controller flips and SCP_CONTROL_SWAP fires."""
    game, p1, p2 = _setup()
    anomaly_def = _compleation(_make_anomaly("Vector Bloom"), 3)
    _put_in_play(game, p2, anomaly_def)
    target = _make_personnel("Volunteer", skills={"research": 2})
    target_obj = _put_in_play(game, p1, target)
    scp.apply_compleation_vector(game, p1.id)
    assert target_obj.controller == p2.id, "Controller should have swapped to p2"
    assert target_obj.id in game.state.scp_personnel[p2.id]
    assert target_obj.id not in game.state.scp_personnel[p1.id]
    assert any(e.type == EventType.SCP_CONTROL_SWAP for e in game.state.event_log)
    assert scp.site(game.state, p2.id)["compleation_swaps"] == 1


# ---------------------------------------------------------------------------
# Cluster 2: Phylactery Audit
# ---------------------------------------------------------------------------


def test_phylactery_audit_returns_card_to_hand_under_threshold():
    """memory_hole -> auto-accept when ethics_debt + X <= 8 -> card moves back to HAND."""
    game, p1, _p2 = _setup()
    audit_card = _phylactery_audit(
        _fbn_card("Phylactery", CardType.SCP_FACILITY, text="t", subtypes=set(), red_tape=0),
        2,
    )
    obj = _put_in_play(game, p1, audit_card, status="sealed")
    scp.site(game.state, p1.id)["ethics_debt"] = 4  # 4+2=6 <= 8 — auto-accept.
    ok, _msg, _events = scp.memory_hole(game, p1.id, obj.id)
    assert ok
    assert obj.zone == ZoneType.HAND, "Audit-accepted card should be back in hand"
    assert scp.site(game.state, p1.id)["phylactery_audits"] == 1
    assert scp.site(game.state, p1.id)["ethics_debt"] == 6
    # Offer event should have fired.
    assert any(
        e.type == EventType.SCP_PHYLACTERY_AUDIT_OFFER and e.payload.get("accepted")
        for e in game.state.event_log
    )


def test_phylactery_audit_rejects_above_threshold():
    """Above ethics+X<=8: card stays forgotten, hand is unchanged."""
    game, p1, _p2 = _setup()
    audit_card = _phylactery_audit(
        _fbn_card("Phylactery", CardType.SCP_FACILITY, text="t", subtypes=set(), red_tape=0),
        5,
    )
    obj = _put_in_play(game, p1, audit_card, status="sealed")
    scp.site(game.state, p1.id)["ethics_debt"] = 6  # 6+5=11 > 8 — reject.
    scp.memory_hole(game, p1.id, obj.id)
    assert obj.zone == ZoneType.EXILE
    assert scp.site(game.state, p1.id)["phylactery_audits"] == 0
    assert obj.id in game.state.scp_forgotten[p1.id], "Should be in forgotten zone"


# ---------------------------------------------------------------------------
# Cluster 3: Spark Containment
# ---------------------------------------------------------------------------


def test_spark_containment_bumps_clearance_and_fires_paperwork_at_six():
    """A Spark Containment N personnel adds N to clearance on every contain;
    at clearance >= 6 the first crossing fires an extra paperwork tick.
    """
    game, p1, p2 = _setup()
    # Spark personnel.
    spark = _spark_containment(_make_personnel("Reactor Tech"), 2)
    _put_in_play(game, p1, spark)
    # Pending dossier on p1 that the spark tick should advance.
    pending_def = _make_anomaly("Pending Anomaly", red_tape=2)
    pending_obj = _put_in_play(game, p1, pending_def, status="pending")
    pending_obj.state.scp_paperwork = 2
    # Seed clearance to 5 so the first spark contain crosses the threshold.
    scp.site(game.state, p1.id)["clearance"] = 5
    before = _snap_site(game, p1.id)
    scp.apply_spark_containment(game, p1.id)
    after = _snap_site(game, p1.id)
    delta = _site_delta(before, after)
    assert delta["clearance"] == 2
    assert after["spark_drawn_this_turn"] is True
    assert pending_obj.state.scp_paperwork == 1, "Extra paperwork tick should have fired"


def test_spark_containment_one_shot_only_per_turn():
    """Second crossing in the same turn should NOT fire another paperwork tick."""
    game, p1, _p2 = _setup()
    spark = _spark_containment(_make_personnel("Reactor Tech"), 2)
    _put_in_play(game, p1, spark)
    pending_def = _make_anomaly("Pending", red_tape=0)
    pending_obj = _put_in_play(game, p1, pending_def, status="pending")
    pending_obj.state.scp_paperwork = 3
    scp.site(game.state, p1.id)["clearance"] = 5
    scp.apply_spark_containment(game, p1.id)
    pw_after_first = pending_obj.state.scp_paperwork
    scp.apply_spark_containment(game, p1.id)
    assert pending_obj.state.scp_paperwork == pw_after_first, (
        "Second call same turn must not re-tick paperwork"
    )


# ---------------------------------------------------------------------------
# Cluster 4: Leyline Saturation
# ---------------------------------------------------------------------------


def test_leyline_saturation_negative_suppression_applied_and_cleared():
    """Opening an opposing facility should drop scp_suppressed by N on the
    saturator's active anomalies. End-of-turn clears the negative half.
    """
    game, p1, p2 = _setup()
    # p1 (saturator) has a Leyline 2 anomaly active.
    saturating = _leyline_saturation(_make_anomaly("Leyline"), 2)
    saturating_obj = _put_in_play(game, p1, saturating)
    # p2 opens a procedure -- synthetic since we just instantiate + call hook.
    procedure_def = _fbn_card(
        "Test Procedure", CardType.SCP_PROCEDURE, text="t", subtypes=set(), red_tape=0,
    )
    opened = _put_in_play(game, p2, procedure_def)
    scp.apply_leyline_saturation(game, p2.id, opened)
    assert saturating_obj.state.scp_suppressed == -2, "Negative suppression applied"
    # Clear at end of saturator's turn.
    scp.clear_leyline_saturation(game.state, p1.id)
    assert saturating_obj.state.scp_suppressed == 0


def test_leyline_saturation_ignores_anomaly_opens():
    """Opening an anomaly (not procedure/facility/mandate) should NOT trigger leyline."""
    game, p1, p2 = _setup()
    saturating = _leyline_saturation(_make_anomaly("Leyline"), 3)
    saturating_obj = _put_in_play(game, p1, saturating)
    opener = _make_anomaly("Other Anomaly")
    other = _put_in_play(game, p2, opener)
    scp.apply_leyline_saturation(game, p2.id, other)
    assert saturating_obj.state.scp_suppressed == 0


# ---------------------------------------------------------------------------
# Cluster 5: Planar Rift
# ---------------------------------------------------------------------------


def test_planar_rift_exiles_library_top_and_allows_play():
    """SCP_CONTAINED for Planar Rift X should exile top X of library into the
    rift window; ``play_from_rift_window`` plays an anomaly into BATTLEFIELD.
    """
    game, p1, _p2 = _setup()
    # Seed library with 3 anomaly card_defs.
    lib_card_defs = [_make_anomaly(f"Rift Card {i}") for i in range(3)]
    for cd in lib_card_defs:
        game.create_object(
            name=cd.name, owner_id=p1.id, zone=ZoneType.LIBRARY,
            characteristics=cd.characteristics, card_def=cd,
        )
    rift_anomaly = _planar_rift(_make_anomaly("Rift Source"), 2)
    rift_obj = _put_in_play(game, p1, rift_anomaly, status="contained")
    events = scp.apply_planar_rift(game, p1.id, rift_obj)
    window = scp.site(game.state, p1.id)["rift_window"]
    assert len(window) == 2, "Exactly 2 cards should be exiled to the window"
    # Play one of them.
    target_id = window[0]
    ok, _msg, _events = scp.play_from_rift_window(game, p1.id, target_id)
    assert ok
    target = game.state.objects[target_id]
    assert target.zone == ZoneType.BATTLEFIELD
    assert target.state.scp_status == "active"


def test_planar_rift_cleanup_returns_to_library():
    """End-of-turn cleanup should move unspent rift cards back to top of library."""
    game, p1, _p2 = _setup()
    for i in range(2):
        cd = _make_anomaly(f"Rift {i}")
        game.create_object(
            name=cd.name, owner_id=p1.id, zone=ZoneType.LIBRARY,
            characteristics=cd.characteristics, card_def=cd,
        )
    rift_anomaly = _planar_rift(_make_anomaly("Rift Source"), 2)
    rift_obj = _put_in_play(game, p1, rift_anomaly, status="contained")
    scp.apply_planar_rift(game, p1.id, rift_obj)
    assert len(scp.site(game.state, p1.id)["rift_window"]) == 2
    scp.cleanup_rift_window(game, p1.id)
    assert scp.site(game.state, p1.id)["rift_window"] == []
    library = game.state.zones[f"library_{p1.id}"]
    assert len(library.objects) == 2, "Both cards should be back in library"


# ---------------------------------------------------------------------------
# Cluster 6: Dragon Hoard
# ---------------------------------------------------------------------------


def test_dragon_hoard_adds_to_active_bonus_capped_at_six():
    """Each archived Dragon with scp_dragon_hoard = X grants X to every test,
    capped at +6 in total (engine guardrail).
    """
    game, p1, _p2 = _setup()
    # Seed archives_list with 4 Dragon defs at +2 each = +8 raw, cap to +6.
    dragons = [
        _dragon_hoard(
            _fbn_card(f"Dragon {i}", CardType.SCP_ANOMALY,
                      text="t", subtypes={"Dragon"}, red_tape=0,
                      containment=1, hazard=1, curiosity=1),
            2,
        )
        for i in range(4)
    ]
    scp.site(game.state, p1.id)["archives_list"] = dragons
    bonus_research = scp._active_bonus(game.state, p1.id, "research")
    bonus_contain = scp._active_bonus(game.state, p1.id, "contain")
    assert bonus_research == 6, f"Expected cap of +6, got +{bonus_research}"
    assert bonus_contain == 6
    # Non-dragon archives don't contribute.
    junk = _fbn_card("Junk", CardType.SCP_PROCEDURE, text="t", subtypes=set(), red_tape=0)
    junk.scp_dragon_hoard = 99  # ignored because no Dragon subtype.
    scp.site(game.state, p1.id)["archives_list"] = [junk]
    assert scp._active_bonus(game.state, p1.id, "research") == 0


# ---------------------------------------------------------------------------
# Cluster 7: Annihilation Wave + Wurm Devourer
# ---------------------------------------------------------------------------


def test_annihilation_wave_redacts_and_bumps_breach():
    """Each breach_tick should fire Annihilation Wave N: redact + breach += N."""
    game, p1, p2 = _setup()
    annihil = _annihilation_wave(_make_anomaly("Wave"), 2)
    _put_in_play(game, p1, annihil)
    # Seed p2 hand with 3 cards so redact has targets.
    for i in range(3):
        junk = _fbn_card(f"Junk{i}", CardType.SCP_PROCEDURE, text="t", subtypes=set(), red_tape=1)
        game.create_object(
            name=junk.name, owner_id=p2.id, zone=ZoneType.HAND,
            characteristics=junk.characteristics, card_def=junk,
        )
    before_breach = scp.site(game.state, p2.id)["breach"]
    before_hand = len(game.state.zones[f"hand_{p2.id}"].objects)
    scp.apply_annihilation_wave(game, p1.id, breach_amount=1)
    after_breach = scp.site(game.state, p2.id)["breach"]
    after_hand = len(game.state.zones[f"hand_{p2.id}"].objects)
    assert after_breach - before_breach == 2, "Opposing breach should bump by N"
    assert before_hand - after_hand == 2, "Opposing hand should lose N cards"


def test_wurm_devourer_swaps_curiosity_for_containment():
    """A successful test against a Wurm Devourer anomaly swaps the normal
    curiosity tick for ``scp_suppressed += 2`` and bumps wurms_tamed.
    """
    game, p1, _p2 = _setup()
    wurm_def = _wurm_devourer(_make_anomaly("Tame Wurm", curiosity=1, hazard=3))
    wurm = _put_in_play(game, p1, wurm_def)
    wurm.state.scp_researched = 1  # Simulate ``run_test`` already incremented.
    events = scp.apply_wurm_devourer(game, wurm)
    assert wurm.state.scp_suppressed == 2
    assert wurm.state.scp_researched == 0, "Curiosity tick should be cancelled"
    assert scp.site(game.state, p1.id)["wurms_tamed"] == 1
    assert any(
        e.type == EventType.SCP_INCIDENT_RESOLVED and e.payload.get("reason") == "wurm_taming"
        for e in events
    )


# ---------------------------------------------------------------------------
# Alt-wins (Cluster 1, 2, 7)
# ---------------------------------------------------------------------------


def _make_mandate(name, alt_win):
    return _fbn_card(name, CardType.SCP_MANDATE, text="t", subtypes=set(), red_tape=0)


def test_alt_win_compleation_overrun_triggers_at_three_swaps():
    """compleation_overrun: 3+ compleation swaps with an active mandate = win."""
    game, p1, _p2 = _setup()
    mandate_def = _make_mandate("Phyrexian Strain Mandate", "compleation_overrun")
    mandate_def.scp_alt_win = "compleation_overrun"
    _put_in_play(game, p1, mandate_def)
    scp.site(game.state, p1.id)["compleation_swaps"] = 3
    scp.check_scp_victory(game)
    assert game.state.players[_p2.id].has_lost, "Opponent should have lost on alt-win"


def test_alt_win_phylactery_chain_triggers_at_four_audits():
    """phylactery_chain: 4+ phylactery audits with an active mandate = win."""
    game, p1, _p2 = _setup()
    mandate_def = _make_mandate("Lich Phylactery Mandate", "phylactery_chain")
    mandate_def.scp_alt_win = "phylactery_chain"
    _put_in_play(game, p1, mandate_def)
    scp.site(game.state, p1.id)["phylactery_audits"] = 4
    scp.check_scp_victory(game)
    assert game.state.players[_p2.id].has_lost


def test_alt_win_wurm_apex_tamed_triggers_at_three_tames():
    """wurm_apex_tamed: 3+ wurms tamed with an active mandate = win."""
    game, p1, _p2 = _setup()
    mandate_def = _make_mandate("Wurm Apex Mandate", "wurm_apex_tamed")
    mandate_def.scp_alt_win = "wurm_apex_tamed"
    _put_in_play(game, p1, mandate_def)
    scp.site(game.state, p1.id)["wurms_tamed"] = 3
    scp.check_scp_victory(game)
    assert game.state.players[_p2.id].has_lost


# ---------------------------------------------------------------------------
# Helper composability sanity check
# ---------------------------------------------------------------------------


def test_helpers_compose_keywords_and_attributes():
    """_phylactery_audit(_compleation(card, 2), 1) keeps both fields and keywords."""
    card = _make_anomaly("Composed")
    card = _compleation(card, 2)
    card = _phylactery_audit(card, 1)
    assert card.scp_compleation_vector == 2
    assert card.scp_phylactery_audit == 1
    kws = set(card.scp_keywords)
    assert "Compleation Vector 2" in kws
    assert "Phylactery Audit 1" in kws


if __name__ == "__main__":
    import traceback
    passed = 0
    failed = 0
    errors = 0
    failures: list[tuple[str, str]] = []
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            failed += 1
            failures.append((name, f"AssertionError: {exc}"))
        except Exception:
            errors += 1
            failures.append((name, traceback.format_exc()))
    print("=" * 60)
    print(f"  FBN Engine Extensions: {passed} passed, {failed} failed, {errors} errors")
    print("=" * 60)
    for name, msg in failures:
        print(f"FAIL {name}")
        print(msg)
        print("-" * 60)
    sys.exit(0 if failed == 0 and errors == 0 else 1)
