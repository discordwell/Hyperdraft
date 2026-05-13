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
    """Boros bench-scaling damage cluster — Aurelin, Aurelia ex, Razia, Wojek
    all use the same bench-count → opp-active-damage pattern."""
    from src.cards.pokemon.beyond.ravnica.boros import BEYOND_RAVNICA_BOROS
    bench_scaling = [
        "Aurelin", "Aurelia, the Warleader ex", "Razia, Boros Archangel",
        "Wojek Halberdiers",
    ]
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


def test_brv_set_health_fails_all_checks():
    """The whole point of the audit: BRV must fail the depth health checks.
    If this test ever passes, either the rubric was loosened or BRV got a
    genuine depth pass."""
    from src.cards.pokemon.beyond.ravnica import BEYOND_RAVNICA_CARDS
    report = score_registry(BEYOND_RAVNICA_CARDS, engine="pokemon", set_code="BRV")
    # Diversity must be below targets.
    assert report.axis_diversity < 0.50
    assert report.code_diversity < 0.50
    # There must be at least one large reskin cluster.
    assert report.top_reskin_clusters
    assert report.top_reskin_clusters[0].size >= 5, (
        f"Expected the top BRV reskin cluster to have >=5 members; "
        f"got {report.top_reskin_clusters[0].size}"
    )


def test_set_report_per_axis_distribution_sums_to_total():
    from src.cards.pokemon.beyond.ravnica import BEYOND_RAVNICA_CARDS
    report = score_registry(BEYOND_RAVNICA_CARDS, engine="pokemon", set_code="BRV")
    for ax in (report.state_dist, report.decision_dist, report.zone_dist,
               report.asymmetry_dist, report.synergy_dist):
        assert sum(ax.counts.values()) == report.total_cards


def test_brv_has_zero_decision_pressure_cards():
    """The Pokemon engine has no modal helpers in current cards. Every BRV
    card should score 0 on Decision Pressure — this is a fact about the
    current card pool, and a future spice pass should break this assertion."""
    from src.cards.pokemon.beyond.ravnica import BEYOND_RAVNICA_CARDS
    report = score_registry(BEYOND_RAVNICA_CARDS, engine="pokemon", set_code="BRV")
    assert report.decision_dist.counts.get(0, 0) == report.total_cards
    assert report.decision_dist.counts.get(1, 0) == 0
    assert report.decision_dist.counts.get(2, 0) == 0
    assert report.decision_dist.counts.get(3, 0) == 0


def test_brv_has_zero_synergy_hook_cards():
    """No card in BRV uses a recognized filter factory or novel-helper
    mechanic. This is the second half of the user's "mid" diagnosis: the
    cards don't pull other cards into the deck."""
    from src.cards.pokemon.beyond.ravnica import BEYOND_RAVNICA_CARDS
    report = score_registry(BEYOND_RAVNICA_CARDS, engine="pokemon", set_code="BRV")
    assert report.synergy_dist.counts.get(0, 0) == report.total_cards
