"""
Tests for the SCP-engine depth scorer.

SCP-engine sets carry their mechanics in metadata fields (``scp_archetype``,
``scp_compleation_vector``, ``scp_on_reveal``, ``scp_alt_win``…) rather
than callable interceptor slots. ``src/depth/scp_scorer.py`` reads those
fields and produces a five-axis depth report whose shape matches the
MTG-style scorer in ``axis_scorer.py``. These tests cover:

1. Per-axis scoring rules — each axis should be 0 on a bare card and
   non-zero only when the SCP signal that axis maps to is present.
2. The "wired" predicate — vanilla stat-line cards are unwired, anything
   that touches a mechanic slot is wired.
3. The code fingerprint — two cards with the same archetype/trigger
   surface/keyword set must fingerprint identically (reskin cluster).
4. Dispatch — ``score_registry(engine='scp', …)`` routes to the SCP
   scorer, not the AST scorer.
5. Drift — FBN as the reference still passes ``gates_passing_min``.
6. Hot-swap — deliberately tightening scp.toml drops FBN below the gate
   count, proving the calibration test actually works.

Run::

    python -m pytest tests/test_scp_depth_scorer.py -q
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pytest


# ---------------------------------------------------------------------------
# Minimal stand-in for CardDefinition so the per-axis rules can be exercised
# without booting the full set registry.
# ---------------------------------------------------------------------------


@dataclass
class FakeScpCard:
    name: str = "TEST"
    scp_archetype: Optional[str] = None
    scp_alt_win: Optional[str] = None
    scp_compleation_vector: int = 0
    scp_aura: dict = field(default_factory=dict)
    scp_bonus: dict = field(default_factory=dict)
    scp_keywords: list = field(default_factory=list)
    scp_containment: int = 0
    scp_curiosity: int = 0
    scp_hazard: int = 0
    # Decision-axis trigger callables.
    scp_effect: Optional[object] = None
    scp_on_test: Optional[object] = None
    scp_on_test_fail: Optional[object] = None
    scp_on_assign: Optional[object] = None
    scp_on_open_dossier: Optional[object] = None
    scp_on_activate: Optional[object] = None
    scp_on_audit_return: Optional[object] = None
    # Zone-axis trigger callables.
    scp_on_reveal: Optional[object] = None
    scp_on_contain: Optional[object] = None
    scp_on_dragon_contain: Optional[object] = None
    scp_on_archive: Optional[object] = None
    scp_on_archive_stub: Optional[object] = None
    scp_on_breach: Optional[object] = None
    scp_on_play: Optional[object] = None
    scp_on_sacrifice: Optional[object] = None
    scp_on_anomaly_enter: Optional[object] = None
    scp_on_memory_hole: Optional[object] = None
    scp_on_rift_play: Optional[object] = None
    # Asymmetry-axis trigger callables.
    scp_on_any_compleated: Optional[object] = None
    scp_on_opponent_compleated: Optional[object] = None
    scp_on_you_compleated: Optional[object] = None
    scp_on_annihilation_wave_fire: Optional[object] = None
    # State-axis trigger callable (end-of-turn read).
    scp_on_turn_end: Optional[object] = None


def _no_op(*args, **kwargs):
    """Placeholder callable used as a trigger stand-in."""
    return []


# ---------------------------------------------------------------------------
# 1. Per-axis rule tests
# ---------------------------------------------------------------------------


def test_unwired_card_scores_zero_on_every_axis():
    """A pure-vanilla stat-line card (no mechanic fields) is unwired and 0/15."""
    from src.depth.scp_scorer import score_scp_card

    card = FakeScpCard(name="Vanilla Anomaly", scp_containment=2)
    cs = score_scp_card(card)
    assert cs.is_unwired is True
    assert cs.scores.total == 0
    assert cs.scores.fingerprint == (0, 0, 0, 0, 0)
    # Unwired cards must emit empty fingerprints so they cannot accidentally
    # join a reskin cluster downstream — fingerprint clustering ignores
    # cards whose code_fingerprint is "".
    assert cs.code_fingerprint == ""


def test_state_axis_picks_up_end_of_turn_trigger():
    """End-of-turn slots are state reads, not zone moves."""
    from src.depth.scp_scorer import score_scp_card

    card = FakeScpCard(
        name="End-of-Turn Watcher",
        scp_archetype="leyline_anomaly",
        scp_on_turn_end=_no_op,
    )
    cs = score_scp_card(card)
    assert cs.scores.state == 1


def test_state_axis_picks_up_alt_win_compleation_and_keyword():
    from src.depth.scp_scorer import score_scp_card

    card = FakeScpCard(
        name="State-Reading Praetor",
        scp_archetype="phyrexian_strain",
        scp_alt_win="compleation_overrun",
        scp_compleation_vector=2,
        scp_keywords=["Mnestic Ward", "Antimemetic Hush"],
    )
    cs = score_scp_card(card)
    assert cs.scores.state == 3, f"Expected S=3, got {cs.scores.state}"


def test_decision_axis_counts_branching_triggers():
    from src.depth.scp_scorer import score_scp_card

    card = FakeScpCard(
        name="Branching Procedure",
        scp_archetype="redaction",
        scp_effect=_no_op,
        scp_on_test=_no_op,
        scp_on_test_fail=_no_op,
    )
    cs = score_scp_card(card)
    assert cs.scores.decision == 3, f"Expected D=3, got {cs.scores.decision}"


def test_decision_axis_credits_full_trigger_surface():
    """Non-test branches (assign / activate / audit_return / open_dossier)
    are also decision-axis signals. Without this, a card whose only
    callable is scp_on_play+scp_on_activate would score D=0."""
    from src.depth.scp_scorer import score_scp_card

    card = FakeScpCard(
        name="Activated Operative",
        scp_archetype="phyrexian_strain",
        scp_on_assign=_no_op,
        scp_on_activate=_no_op,
        scp_on_open_dossier=_no_op,
    )
    cs = score_scp_card(card)
    assert cs.scores.decision == 3


def test_zone_axis_counts_movement_triggers_and_keywords():
    from src.depth.scp_scorer import score_scp_card

    card = FakeScpCard(
        name="Zone-Mover",
        scp_archetype="phyrexian_strain",
        scp_on_reveal=_no_op,
        scp_on_contain=_no_op,
        scp_keywords=["Containment Vector"],
    )
    cs = score_scp_card(card)
    assert cs.scores.zone == 3


def test_zone_axis_credits_play_and_sacrifice_slots():
    """Z must credit the full zone-change slot family (play/sacrifice/breach
    /archive/anomaly_enter). Common-but-uncovered slots were the reason
    FBN's old code_diversity sat at 0.535 — they all hit the same '----' bits."""
    from src.depth.scp_scorer import score_scp_card

    card = FakeScpCard(
        name="Played-and-Sacrificed",
        scp_archetype="lich_phylactery",
        scp_on_play=_no_op,
        scp_on_sacrifice=_no_op,
        scp_on_breach=_no_op,
    )
    cs = score_scp_card(card)
    assert cs.scores.zone == 3


def test_asymmetry_axis_credits_cross_player_triggers():
    """Cross-player triggers (opponent_compleated etc.) signal info imbalance
    and should add to asymmetry."""
    from src.depth.scp_scorer import score_scp_card

    card = FakeScpCard(
        name="Cross-Player Praetor",
        scp_archetype="phyrexian_strain",
        scp_on_opponent_compleated=_no_op,
    )
    cs = score_scp_card(card)
    assert cs.scores.asymmetry == 1


def test_asymmetry_axis_counts_aura_alt_win_and_threat():
    from src.depth.scp_scorer import score_scp_card

    card = FakeScpCard(
        name="Pressuring Anomaly",
        scp_archetype="dragon_conclave",
        scp_aura={"any": {"contain": 1}},
        scp_alt_win="dragon_hoard_sealed",
        scp_hazard=4,
    )
    cs = score_scp_card(card)
    assert cs.scores.asymmetry == 3


def test_asymmetry_high_threat_only_contributes_when_card_is_wired():
    """High containment/hazard is stat-line — not a mechanic field. It
    contributes +1 to asymmetry only when the card is *already* wired by
    some mechanic field (effect/trigger/alt_win/aura/bonus/keyword/vector).

    Without that, the card is a pure stat-line and scores 0 across all axes
    even with containment=5 — which is correct: a vanilla 5/5/5 anomaly
    is still vanilla.
    """
    from src.depth.scp_scorer import score_scp_card

    bare = FakeScpCard(
        name="Stat-line Only",
        scp_archetype="dragon_conclave",
        scp_containment=5,
    )
    assert score_scp_card(bare).scores.asymmetry == 0
    assert score_scp_card(bare).is_unwired is True

    wired_with_threat = FakeScpCard(
        name="Wired + High Threat",
        scp_archetype="dragon_conclave",
        scp_bonus={"contain": 1},  # wires the card
        scp_containment=5,
    )
    cs = score_scp_card(wired_with_threat)
    assert cs.is_unwired is False
    # asymmetry +1 from threat tier; aura/alt_win not set so axis = 1.
    assert cs.scores.asymmetry == 1


def test_synergy_axis_counts_archetype_bonus_and_keyword():
    from src.depth.scp_scorer import score_scp_card

    card = FakeScpCard(
        name="Synergy Hook",
        scp_archetype="leyline_anomaly",
        scp_bonus={"contain": 1},
        scp_keywords=["Leyline Saturation 1"],
    )
    cs = score_scp_card(card)
    assert cs.scores.synergy == 3


def test_axis_scores_cap_at_three():
    """Even with redundant signals, no axis exceeds 3."""
    from src.depth.scp_scorer import score_scp_card

    card = FakeScpCard(
        name="Maxed Card",
        scp_archetype="phyrexian_strain",
        scp_alt_win="compleation_overrun",
        scp_compleation_vector=3,
        scp_aura={"any": {"contain": 1}},
        scp_bonus={"contain": 1},
        scp_keywords=[
            "Mnestic", "Antimemetic", "Compleation",
            "Phyrexian", "Containment",
        ],
        scp_containment=5,
        scp_hazard=5,
        scp_effect=_no_op,
        scp_on_reveal=_no_op,
        scp_on_test=_no_op,
        scp_on_test_fail=_no_op,
        scp_on_contain=_no_op,
    )
    cs = score_scp_card(card)
    for axis in ("state", "decision", "zone", "asymmetry", "synergy"):
        assert getattr(cs.scores, axis) == 3, f"{axis} did not cap at 3"


# ---------------------------------------------------------------------------
# 2. Wired predicate
# ---------------------------------------------------------------------------


def test_card_is_wired_if_any_mechanic_field_is_populated():
    """Archetype / expansion / red_tape alone don't count — they're identity."""
    from src.depth.scp_scorer import score_scp_card, _is_wired

    identity_only = FakeScpCard(name="ID only", scp_archetype="redaction")
    assert _is_wired(identity_only) is False
    assert score_scp_card(identity_only).is_unwired is True

    keyword_only = FakeScpCard(
        name="Keyword card",
        scp_archetype="redaction",
        scp_keywords=["Mnestic"],
    )
    assert _is_wired(keyword_only) is True


# ---------------------------------------------------------------------------
# 3. Code fingerprint clusters
# ---------------------------------------------------------------------------


def test_two_cards_with_identical_trigger_surface_share_fingerprint():
    """Two reskins of the same archetype+trigger+keywords are one cluster."""
    from src.depth.scp_scorer import score_scp_card

    card_a = FakeScpCard(
        name="Reskin A",
        scp_archetype="leyline_anomaly",
        scp_keywords=["Leyline Saturation 1"],
        scp_bonus={"contain": 1},
    )
    card_b = FakeScpCard(
        name="Reskin B",
        scp_archetype="leyline_anomaly",
        scp_keywords=["Leyline Saturation 1"],
        scp_bonus={"research": 2},  # different value, same trigger surface
    )
    assert score_scp_card(card_a).code_fingerprint == score_scp_card(card_b).code_fingerprint


def test_different_archetypes_get_different_fingerprints():
    from src.depth.scp_scorer import score_scp_card

    a = FakeScpCard(name="A", scp_archetype="phyrexian_strain", scp_bonus={"x": 1})
    b = FakeScpCard(name="B", scp_archetype="dragon_conclave", scp_bonus={"x": 1})
    assert score_scp_card(a).code_fingerprint != score_scp_card(b).code_fingerprint


def test_alt_win_key_is_bucketed_not_embedded_in_fingerprint():
    """Each Mandate ships a unique alt-win identifier. Embedding the raw key
    would explode every Mandate into its own cluster and defeat reskin
    detection. Two Mandates from the same archetype with different alt-win
    keys but the same trigger surface should fingerprint identically."""
    from src.depth.scp_scorer import score_scp_card

    a = FakeScpCard(
        name="Mandate Compleation",
        scp_archetype="phyrexian_strain",
        scp_alt_win="compleation_overrun",
        scp_bonus={"contain": 1},
    )
    b = FakeScpCard(
        name="Mandate Phyresis",
        scp_archetype="phyrexian_strain",
        scp_alt_win="phyresis_complete",
        scp_bonus={"contain": 1},
    )
    assert score_scp_card(a).code_fingerprint == score_scp_card(b).code_fingerprint


def test_state_axis_does_not_credit_vector_zero():
    """scp_compleation_vector defaults to 0 and the _is_set check must NOT
    treat 0 as 'set'. A card with only Mnestic keyword should score S=1,
    not S=2 from a phantom vector signal."""
    from src.depth.scp_scorer import score_scp_card

    card = FakeScpCard(
        name="Mnestic Only",
        scp_archetype="redaction",
        scp_keywords=["Mnestic"],
    )
    cs = score_scp_card(card)
    assert cs.scores.state == 1


# ---------------------------------------------------------------------------
# 4. Dispatch — score_registry must route SCP engine to the SCP scorer.
# ---------------------------------------------------------------------------


def test_score_registry_routes_scp_engine_to_metadata_scorer():
    """If dispatch is wired, FBN scores >0 on multiple axes. If it falls
    back to the AST scorer it scores 0/4 on every gate."""
    from src.depth.report import score_registry, reset_calibration_cache
    from src.cards.scp.foundations_beyond import FBN_CARDS

    reset_calibration_cache()
    report = score_registry(FBN_CARDS, engine="scp", set_code="FBN")
    # Sanity: dispatch went somewhere productive.
    assert report.median_total >= 2.0
    assert report.axis_diversity > 0.05
    assert report.wired_cards > 100, (
        "FBN expected to have >100 mechanic-bearing cards under the SCP "
        f"rubric; got {report.wired_cards}. Dispatch may be falling "
        "through to the AST scorer."
    )


# ---------------------------------------------------------------------------
# 5. Reference set still clears gates_passing_min.
# ---------------------------------------------------------------------------


def test_fbn_reference_passes_scp_corpus_gates():
    """FBN is the SCP corpus reference; it must clear gates_passing_min."""
    from src.depth.report import (
        score_registry, reset_calibration_cache, load_calibration,
    )
    from src.cards.scp.foundations_beyond import FBN_CARDS

    reset_calibration_cache()
    corpus = load_calibration("scp")
    assert corpus.reference_set == "foundations_beyond"
    report = score_registry(FBN_CARDS, engine="scp", set_code="FBN")
    passing = sum(1 for v in report.health_checks.values() if v == "PASS")
    assert passing >= corpus.gates_passing_min, (
        f"FBN passes {passing}/4 gates, corpus requires >= {corpus.gates_passing_min}\n"
        f"  health: {report.health_checks}"
    )


def test_mnr_secondary_reference_passes_minimum_gates():
    """MNR is the secondary reference. It is allowed to fail code_div (its
    tighter archetypes pack more reskin clusters) but must still clear
    median + axis + thin = 3 gates."""
    from src.depth.report import score_registry, reset_calibration_cache
    from src.cards.scp.mnestic_reset import MNR_CARDS

    reset_calibration_cache()
    report = score_registry(MNR_CARDS, engine="scp", set_code="MNR")
    passing = sum(1 for v in report.health_checks.values() if v == "PASS")
    assert passing >= 3, (
        f"MNR passes {passing}/4 gates; should be >=3\n"
        f"  health: {report.health_checks}"
    )


# ---------------------------------------------------------------------------
# 6. Hot-swap regression test — deliberately tightening the corpus must
#    drop FBN below the gate count.
# ---------------------------------------------------------------------------


def test_deliberate_regression_in_scp_corpus_fails_drift(tmp_path, monkeypatch):
    """Hot-swap scp.toml to deliberately-too-strict thresholds; FBN must
    drop below gates_passing_min so the calibration test catches drift."""
    from src.depth import report as depth_report

    real_dir = depth_report._CALIBRATION_DIR
    fake_dir = tmp_path / "calibration"
    fake_dir.mkdir()
    for src in real_dir.glob("*.toml"):
        (fake_dir / src.name).write_text(src.read_text())

    bumped = (fake_dir / "scp.toml").read_text().replace(
        "median_depth = 2", "median_depth = 5"
    ).replace(
        "code_diversity = 0.50", "code_diversity = 0.95"
    )
    (fake_dir / "scp.toml").write_text(bumped)

    monkeypatch.setattr(depth_report, "_CALIBRATION_DIR", fake_dir)
    depth_report.reset_calibration_cache()

    corpus = depth_report.load_calibration("scp")
    assert corpus.median_depth == 5.0
    assert corpus.code_diversity == 0.95

    from src.cards.scp.foundations_beyond import FBN_CARDS
    report = depth_report.score_registry(
        FBN_CARDS, engine="scp", set_code="FBN",
    )
    passing = sum(1 for v in report.health_checks.values() if v == "PASS")
    assert passing < corpus.gates_passing_min, (
        f"Hot-swap should have dropped FBN below "
        f"gates_passing_min={corpus.gates_passing_min}; got {passing} passes. "
        f"health={report.health_checks}"
    )

    monkeypatch.setattr(depth_report, "_CALIBRATION_DIR", real_dir)
    depth_report.reset_calibration_cache()


# ---------------------------------------------------------------------------
# 7. The SCP scorer must not be reached by non-SCP engines.
# ---------------------------------------------------------------------------


def test_mtg_engine_does_not_route_to_scp_scorer():
    """An MTG-engine call must still produce AST-driven results."""
    from src.depth.report import score_registry, reset_calibration_cache
    from src.cards.bloomburrow import BLOOMBURROW_CARDS

    reset_calibration_cache()
    report = score_registry(BLOOMBURROW_CARDS, engine="mtg", set_code="BLB")
    # BLB ships with high code_diversity under the AST scorer (~0.78).
    # The SCP scorer would emit ~0.0 since BLB has no scp_* fields.
    assert report.code_diversity > 0.5, (
        f"BLB code_diversity collapsed to {report.code_diversity:.3f} — "
        "the MTG path may have been replaced by SCP routing."
    )


# ---------------------------------------------------------------------------
# 8. CLI registry coverage — all SCP sets resolvable; list-shape works.
# ---------------------------------------------------------------------------


def test_all_three_scp_sets_registered_in_known_sets():
    """MNR + FBN + SZB are the three SCP-engine sets that ship; each must
    be invocable via the CLI registry. The historic gap was SZB being
    declared in src/cards/ but absent from _KNOWN_SETS — caught on first
    pass."""
    from src.depth.report import _KNOWN_SETS

    for code in ("MNR", "FBN", "SZB"):
        assert code in _KNOWN_SETS, (
            f"SCP set code {code!r} missing from _KNOWN_SETS. "
            f"Known: {sorted(_KNOWN_SETS)}"
        )
        engine, module, name = _KNOWN_SETS[code]
        assert engine == "scp", f"{code} routed to wrong engine: {engine}"


def test_list_shape_registry_scores_through_scp_path():
    """SZB exports as a list[CardDefinition] (not a dict). The SCP scorer
    must accept both shapes — otherwise an entire shipping set is
    unscorable. Regression: the first version of the scorer .items()'d
    the registry unconditionally and crashed on SZB."""
    from src.depth.report import score_registry, reset_calibration_cache
    from src.cards.scp.site_zero_broken_masquerade import (
        SITE_ZERO_BROKEN_MASQUERADE_CARDS as SZB,
    )

    assert isinstance(SZB, list), (
        "SZB used to be a list; rewrite this test if the shape changed."
    )
    reset_calibration_cache()
    report = score_registry(SZB, engine="scp", set_code="SZB")
    assert report.total_cards == len(SZB)
    assert report.wired_cards > 0


def test_scp_scorer_rejects_unsupported_registry_shape():
    """A scalar/None/string slipping through is a programmer error and
    should fail loudly, not silently empty-score."""
    from src.depth.scp_scorer import score_scp_registry
    import pytest

    for bad in (None, "string", 42, 3.14):
        with pytest.raises(TypeError):
            score_scp_registry(bad, set_code="OOPS")
