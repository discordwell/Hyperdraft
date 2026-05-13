"""
Calibration and regression tests for the depth heuristic.

These tests pin down:
1. AST fingerprint walks nested closures (MTG-style setup_interceptors).
2. Reskin detection: Pokemon BRV Izzet cards calling only `_draw_cards`
   collapse to a single code fingerprint.
3. Per-axis scoring rules behave as documented (vanilla → 0, modal → D=2, etc).
4. Engine profile registry exposes the expected engines.
5. Set-level diversity ratios are computed from the registry correctly.

Run:
    python -m pytest tests/test_depth_rubric.py -q
"""

from __future__ import annotations

import pytest

from src.depth import (
    AxisScores,
    EngineProfile,
    extract_features_from_callable,
    get_profile,
    list_profiles,
    score_card,
)
from src.depth.report import score_registry


# ---------------------------------------------------------------------------
# Engine profile registry
# ---------------------------------------------------------------------------


def test_profile_registry_exposes_six_engines():
    names = set(list_profiles())
    assert {"mtg", "pokemon", "hearthstone", "yugioh", "finance", "minecraft"} <= names


def test_get_profile_unknown_engine_raises():
    with pytest.raises(KeyError):
        get_profile("magic-the-gathering")


def test_pokemon_profile_includes_active_and_bench_zones():
    prof = get_profile("pokemon")
    assert "active_spot" in prof.zone_names
    assert "bench" in prof.zone_names
    assert "PKM_PLACE_DAMAGE_COUNTERS" in prof.asymmetric_event_types


def test_mtg_profile_includes_modal_helpers():
    prof = get_profile("mtg")
    assert "create_modal_choice" in prof.modal_helpers
    assert "make_spree_setup" in prof.modal_helpers
    assert "make_targeted_etb_trigger" in prof.modal_helpers
    assert "other_creatures_with_subtype" in prof.filter_factories
    assert "make_room_setup" in prof.novel_helpers


# ---------------------------------------------------------------------------
# AST fingerprint — flat module-level callable (Pokemon style)
# ---------------------------------------------------------------------------


def test_pokemon_draw_only_cards_collapse_to_one_fingerprint():
    """Five Izzet cards with effect_fn = `_draw_cards(...)` only must produce
    the same code fingerprint. This is the user's "mid — same keyword
    ability" critique made falsifiable."""
    from src.cards.pokemon.beyond.ravnica.izzet import BEYOND_RAVNICA_IZZET
    pure_draw_cards = [
        "Nivlet", "Goblin Electromancer", "Mercurial Mageling",
        "Steamcore Weird", "Pteramander",
    ]
    pokemon = get_profile("pokemon")
    fingerprints = set()
    for name in pure_draw_cards:
        cs = score_card(BEYOND_RAVNICA_IZZET[name], pokemon)
        fingerprints.add(cs.code_fingerprint)
    assert len(fingerprints) == 1, (
        f"Expected all {len(pure_draw_cards)} draw-only Izzet cards to share "
        f"one fingerprint; got {len(fingerprints)}: {fingerprints}"
    )


def test_pokemon_bench_scaling_cards_collapse_to_one_fingerprint():
    """Boros bench-scaling damage cluster — Aurelin, Razia, Wojek use the same
    bench-count → opp-active-damage pattern. Aurelia ex was rewritten in
    spice pack v1 and no longer shares this fingerprint; the remaining 3
    cards still cluster, which is the rewrite target for spice pack v2."""
    from src.cards.pokemon.beyond.ravnica.boros import BEYOND_RAVNICA_BOROS
    bench_scaling = ["Aurelin", "Razia, Boros Archangel", "Wojek Halberdiers"]
    pokemon = get_profile("pokemon")
    fingerprints = set()
    for name in bench_scaling:
        cs = score_card(BEYOND_RAVNICA_BOROS[name], pokemon)
        fingerprints.add(cs.code_fingerprint)
    assert len(fingerprints) == 1, (
        f"Bench-scaling cluster should be 1 fingerprint; got {fingerprints}"
    )


def test_draw_only_vs_bench_scaling_have_different_fingerprints():
    """Different mechanical patterns must produce different fingerprints —
    otherwise the scorer is too coarse."""
    from src.cards.pokemon.beyond.ravnica.izzet import BEYOND_RAVNICA_IZZET
    from src.cards.pokemon.beyond.ravnica.boros import BEYOND_RAVNICA_BOROS
    pokemon = get_profile("pokemon")
    nivlet_fp = score_card(BEYOND_RAVNICA_IZZET["Nivlet"], pokemon).code_fingerprint
    aurelin_fp = score_card(BEYOND_RAVNICA_BOROS["Aurelin"], pokemon).code_fingerprint
    assert nivlet_fp != aurelin_fp


# ---------------------------------------------------------------------------
# AST fingerprint — MTG nested closures
# ---------------------------------------------------------------------------


def test_ast_walker_descends_into_mtg_setup_closures():
    """MTG setup_interceptors patterns have the real effect logic in nested
    closures. The walker MUST descend into them or it'll under-score every
    MTG card."""
    from src.cards.bloomburrow import BLOOMBURROW_CARDS
    mtg = get_profile("mtg")
    cs = score_card(BLOOMBURROW_CARDS["Banishing Light"], mtg)
    # Banishing Light's etb closure calls create_target_choice → D >= 1.
    assert cs.scores.decision >= 1, (
        f"Banishing Light should detect create_target_choice; got D={cs.scores.decision}, "
        f"helpers={sorted(cs.features.helpers_called)}"
    )


# ---------------------------------------------------------------------------
# Axis scoring rules
# ---------------------------------------------------------------------------


def test_vanilla_creature_scores_zero():
    """A card with no callable slots (pure stat-line) scores 0 on all axes."""
    from src.engine.types import CardDefinition, Characteristics
    vanilla = CardDefinition(
        name="Test Vanilla",
        mana_cost="{1}{W}",
        characteristics=Characteristics(),
    )
    mtg = get_profile("mtg")
    cs = score_card(vanilla, mtg)
    assert cs.scores.total == 0
    assert cs.scores.tier == "vanilla"
    assert cs.is_unwired


def test_axis_score_tiers():
    """Sanity-check tier mapping."""
    assert AxisScores(0, 0, 0, 0, 0).tier == "vanilla"
    assert AxisScores(1, 1, 1, 0, 0).tier == "vanilla"
    assert AxisScores(2, 1, 1, 0, 0).tier == "functional"
    assert AxisScores(3, 1, 2, 2, 0).tier == "spicy"
    assert AxisScores(3, 3, 3, 3, 0).tier == "build-around"


def test_axes_zero_count():
    s = AxisScores(0, 0, 2, 0, 1)
    assert s.axes_zero_count() == 3


# ---------------------------------------------------------------------------
# Set-level diversity
# ---------------------------------------------------------------------------


def test_brv_set_health_partial_pass_post_spice_v1():
    """Spice pack v1 lifted BRV from 0/4 → 1/4 health gates. Code diversity
    now PASSES (the new cards each have a unique AST fingerprint). Axis
    diversity, median depth, and thin ratio still FAIL — those need spice
    pack v2 to lift further. This test pins the current post-v1 baseline."""
    from src.cards.pokemon.beyond.ravnica import BEYOND_RAVNICA_CARDS
    report = score_registry(BEYOND_RAVNICA_CARDS, engine="pokemon", set_code="BRV")
    # code_diversity must now PASS (≥0.5).
    assert report.code_diversity >= 0.5, (
        f"Spice pack v1 should keep code_diversity ≥0.5; got {report.code_diversity}"
    )
    # axis_diversity still FAILS (improved but below 0.5 — v2 territory).
    assert report.axis_diversity < 0.5
    # At least 8 spicy + at least 4 build-around (user's success criterion).
    spicy = report.tier_counts.get("spicy", 0)
    build_around = report.tier_counts.get("build-around", 0)
    assert spicy >= 8, f"Expected ≥8 spicy cards; got {spicy}"
    assert build_around >= 4, f"Expected ≥4 build-around cards; got {build_around}"


def test_set_report_per_axis_distribution_sums_to_total():
    from src.cards.pokemon.beyond.ravnica import BEYOND_RAVNICA_CARDS
    report = score_registry(BEYOND_RAVNICA_CARDS, engine="pokemon", set_code="BRV")
    for ax in (report.state_dist, report.decision_dist, report.zone_dist,
               report.asymmetry_dist, report.synergy_dist):
        assert sum(ax.counts.values()) == report.total_cards


def test_brv_decision_pressure_axis_lit_post_spice_v1():
    """Spice pack v1 added modal Trainers (Tezzy's Test), forced-opp-decision
    cards (Niv-Mizzet's Quandary), and hand-targeted disruption (Jace, Dimir
    Interrogation). At least 5 cards should score >0 on Decision Pressure."""
    from src.cards.pokemon.beyond.ravnica import BEYOND_RAVNICA_CARDS
    report = score_registry(BEYOND_RAVNICA_CARDS, engine="pokemon", set_code="BRV")
    decision_lit = (
        report.decision_dist.counts.get(1, 0)
        + report.decision_dist.counts.get(2, 0)
        + report.decision_dist.counts.get(3, 0)
    )
    assert decision_lit >= 5, (
        f"Expected ≥5 cards with Decision Pressure >0; got {decision_lit}"
    )


def test_brv_synergy_hook_axis_lit_post_spice_v1():
    """Spice pack v1 added 14 cards calling novel helpers (LZ feeders, prize
    tax, status-condition payoffs, etc). At least 10 cards should score >0
    on Synergy Hook."""
    from src.cards.pokemon.beyond.ravnica import BEYOND_RAVNICA_CARDS
    report = score_registry(BEYOND_RAVNICA_CARDS, engine="pokemon", set_code="BRV")
    synergy_lit = (
        report.synergy_dist.counts.get(1, 0)
        + report.synergy_dist.counts.get(2, 0)
        + report.synergy_dist.counts.get(3, 0)
    )
    assert synergy_lit >= 10, (
        f"Expected ≥10 cards with Synergy Hook >0; got {synergy_lit}"
    )
