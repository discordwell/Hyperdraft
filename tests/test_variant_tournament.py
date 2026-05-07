"""Unit tests for the variant_tournament aggregation."""

from scripts.play.variant_tournament import (
    GameOutcome,
    aggregate,
    render_report,
    ENGINES,
)


def _outcome(p1, p2, winner, deck="d1", err=None):
    return GameOutcome(
        p1_variant=p1, p2_variant=p2,
        p1_deck_label=deck, p2_deck_label=deck,
        winner_variant=winner, turns=10, duration_s=1.0, error=err,
    )


def test_aggregate_basic_winrate():
    variants = ["aggro", "control"]
    outcomes = [
        _outcome("aggro", "control", "aggro"),
        _outcome("aggro", "control", "aggro"),
        _outcome("aggro", "control", "control"),
    ]
    agg = aggregate(outcomes, variants)
    # aggro won 2 of 3, control won 1 of 3 (matrix is rounded to 3 decimals)
    assert abs(agg["win_matrix"]["aggro"]["control"] - 2 / 3) < 1e-2
    assert abs(agg["win_matrix"]["control"]["aggro"] - 1 / 3) < 1e-2
    # ranking sorted by overall winrate
    assert agg["ranking"][0]["variant"] == "aggro"
    assert agg["ranking"][1]["variant"] == "control"


def test_aggregate_handles_draws_and_errors():
    variants = ["a", "b"]
    outcomes = [
        _outcome("a", "b", "a"),
        _outcome("a", "b", None),               # draw
        _outcome("a", "b", None, err="timeout"),  # error
    ]
    agg = aggregate(outcomes, variants)
    assert agg["totals"]["draws"] == 2
    assert agg["totals"]["errors"] == 1
    # a still has higher winrate than b (1 win out of 3 vs 0)
    assert agg["ranking"][0]["variant"] == "a"


def test_aggregate_three_variants_pairwise():
    variants = ["x", "y", "z"]
    # x beats y; y beats z; z beats x — rock-paper-scissors
    outcomes = [
        _outcome("x", "y", "x"),
        _outcome("y", "z", "y"),
        _outcome("z", "x", "z"),
    ]
    agg = aggregate(outcomes, variants)
    assert agg["win_matrix"]["x"]["y"] == 1.0
    assert agg["win_matrix"]["y"]["z"] == 1.0
    assert agg["win_matrix"]["z"]["x"] == 1.0
    # all 1-1 overall
    rates = [r["winrate"] for r in agg["ranking"]]
    assert all(abs(r - 0.5) < 1e-9 for r in rates)


def test_render_report_does_not_crash():
    variants = ["a", "b"]
    outcomes = [_outcome("a", "b", "a"), _outcome("a", "b", "b")]
    agg = aggregate(outcomes, variants)
    text = render_report(agg)
    assert "WIN MATRIX" in text
    assert "OVERALL RANKING" in text
    assert "DISCOVERED META" in text


def test_engines_registry_has_mc_and_mtg():
    """Smoke check that the engine dispatch table is populated."""
    assert "minecraft" in ENGINES
    assert "mtg" in ENGINES
    for name in ("minecraft", "mtg"):
        cfg = ENGINES[name]
        assert callable(cfg["deck_resolver"])
        assert callable(cfg["run_one"])
        assert isinstance(cfg["default_variants"], list)
        assert len(cfg["default_variants"]) >= 2
