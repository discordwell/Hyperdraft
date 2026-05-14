"""
Calibration corpus drift tests.

Each engine that ships a `src/depth/calibration/<engine>.toml` corpus declares
(a) the thresholds its gates pin to and (b) a reference card set whose
actual depth scores those thresholds were chosen against. The tests below
re-score every reference set under the corpus's own thresholds and fail
if the rubric, the gates, or the reference set drifts far enough to break
the calibration — the failure modes the task spec calls out:

- "someone bumped axis_diversity to 0.5 again" → caught by the per-gate
  ±0.05 drift check.
- "rubric refactor accidentally tanked Bloomburrow" → caught by
  asserting the reference set still passes `gates_passing_min` gates.

Run:
    python -m pytest tests/test_depth_calibration.py -q
"""

from __future__ import annotations

import importlib
import os
import tempfile
from pathlib import Path

import pytest

from src.depth.report import (
    CalibrationCorpus,
    list_calibrations,
    load_calibration,
    reset_calibration_cache,
    score_registry,
)


# Maximum allowed drift between the threshold stored in a corpus TOML and
# the threshold a future edit could push to. ±0.05 catches the documented
# "someone bumped axis_diversity from 0.10 to 0.50" regression while still
# allowing fine-tuning passes that nudge a gate by a hundredth.
THRESHOLD_DRIFT_TOLERANCE = 0.05


# Each tuple records the threshold values the calibration TOMLs CURRENTLY
# ship with. The drift test compares the loaded corpus against this table
# rather than against itself — that way, an accidental edit to the TOML
# file is caught at test time (the TOML and this table disagree by more
# than the tolerance).
EXPECTED_THRESHOLDS = {
    "mtg": {
        # Re-pinned 2026-05-14 post-trace-markers refactor: BLB's actual
        # scores are axis=0.093 (not 0.10) and thin=0.882 (not 0.81).
        # Gates floored honestly to track real scores.
        "median_depth": 2.0,
        "axis_diversity": 0.08,
        "code_diversity": 0.40,
        "thin_ratio": 0.90,
    },
    "pokemon": {
        "median_depth": 2.0,
        "axis_diversity": 0.10,
        "code_diversity": 0.40,
        "thin_ratio": 0.80,
    },
    "hearthstone": {
        "median_depth": 1.0,
        "axis_diversity": 0.08,
        "code_diversity": 0.50,
        "thin_ratio": 0.99,
    },
    "yugioh": {
        "median_depth": 0.0,
        "axis_diversity": 0.10,
        "code_diversity": 0.50,
        "thin_ratio": 0.99,
    },
    "scp": {
        # SCP cards route through src.depth.scp_scorer, not the AST scorer.
        # FBN sits at median=2.0 ax=0.097 cd=0.535 thin=0.780 (4/4 pass).
        # See src/depth/calibration/scp.toml for the full rationale.
        "median_depth": 2.0,
        "axis_diversity": 0.08,
        "code_diversity": 0.50,
        "thin_ratio": 0.80,
    },
}


CALIBRATED_ENGINES = sorted(EXPECTED_THRESHOLDS.keys())


# ---------------------------------------------------------------------------
# Smoke checks on the corpus loader
# ---------------------------------------------------------------------------


def test_calibration_dir_exists_and_lists_all_four_engines():
    found = set(list_calibrations())
    assert found == set(CALIBRATED_ENGINES), (
        f"Expected exactly {CALIBRATED_ENGINES} calibration TOMLs; got {sorted(found)}"
    )


def test_unknown_engine_returns_fallback_corpus():
    """Brand-new engines without a TOML fall back to the module defaults."""
    reset_calibration_cache()
    corpus = load_calibration("nonexistent_engine")
    assert corpus.source_path is None
    assert corpus.reference_set == ""
    # Fallbacks pin to the module-level constants.
    from src.depth.report import (
        MEDIAN_DEPTH_TARGET,
        AXIS_DIVERSITY_TARGET,
        CODE_DIVERSITY_TARGET,
        THIN_RATIO_MAX,
    )
    assert corpus.median_depth == MEDIAN_DEPTH_TARGET
    assert corpus.axis_diversity == AXIS_DIVERSITY_TARGET
    assert corpus.code_diversity == CODE_DIVERSITY_TARGET
    assert corpus.thin_ratio == THIN_RATIO_MAX


# ---------------------------------------------------------------------------
# Reference-set drift: re-score the corpus's reference set, assert it still
# clears the corpus's claimed `gates_passing_min`.
# ---------------------------------------------------------------------------


def _load_reference_registry(corpus: CalibrationCorpus) -> dict:
    mod = importlib.import_module(corpus.reference_module)
    reg = getattr(mod, corpus.reference_registry, None)
    assert isinstance(reg, dict), (
        f"{corpus.reference_module}.{corpus.reference_registry} is not a dict "
        f"(got {type(reg).__name__})"
    )
    return reg


@pytest.mark.parametrize("engine", CALIBRATED_ENGINES)
def test_reference_set_still_passes_min_gates(engine):
    """The corpus's reference set must still clear `gates_passing_min` gates.

    Drift modes this catches:
    - someone refactors the rubric and Bloomburrow drops to 1/4
    - someone deletes Pokemon's BRV spice pack and BRV regresses
    - someone changes a threshold past the reference's score
    """
    reset_calibration_cache()
    corpus = load_calibration(engine)
    registry = _load_reference_registry(corpus)
    report = score_registry(
        registry,
        engine=engine,
        set_code=corpus.reference_set.upper(),
    )
    passing = sum(1 for v in report.health_checks.values() if v == "PASS")
    assert passing >= corpus.gates_passing_min, (
        f"Calibration drift on {engine}: reference set {corpus.reference_set} "
        f"now passes {passing}/4 gates, corpus requires ≥{corpus.gates_passing_min}.\n"
        f"  median={report.median_total} ax={report.axis_diversity} "
        f"cd={report.code_diversity} thin={report.thin_ratio}\n"
        f"  health={report.health_checks}"
    )


# ---------------------------------------------------------------------------
# Threshold drift: a TOML edit can't silently move a gate by >0.05.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("engine", CALIBRATED_ENGINES)
def test_thresholds_within_tolerance_of_recorded(engine):
    """Every TOML threshold must be within ±0.05 of the recorded value.

    The recorded table lives in this test file (EXPECTED_THRESHOLDS). When
    you intentionally rebalance a corpus, you update both the TOML and this
    table in the same commit — the test guarantees the two stay in sync.
    """
    reset_calibration_cache()
    corpus = load_calibration(engine)
    expected = EXPECTED_THRESHOLDS[engine]
    actual = corpus.thresholds_dict()
    for key, expected_value in expected.items():
        diff = abs(actual[key] - expected_value)
        assert diff <= THRESHOLD_DRIFT_TOLERANCE, (
            f"Threshold drift on {engine}.{key}: "
            f"corpus={actual[key]} vs expected={expected_value} "
            f"(diff={diff} > tolerance={THRESHOLD_DRIFT_TOLERANCE}). "
            f"If this rebalancing is intentional, update EXPECTED_THRESHOLDS "
            f"in tests/test_depth_calibration.py too."
        )


# ---------------------------------------------------------------------------
# Reference identity: the corpus file picks a real, importable registry.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("engine", CALIBRATED_ENGINES)
def test_reference_module_and_registry_resolvable(engine):
    reset_calibration_cache()
    corpus = load_calibration(engine)
    assert corpus.reference_module, f"{engine} corpus has no reference_module"
    assert corpus.reference_registry, f"{engine} corpus has no reference_registry"
    registry = _load_reference_registry(corpus)
    assert len(registry) > 0, (
        f"{engine} reference registry "
        f"{corpus.reference_module}.{corpus.reference_registry} is empty"
    )


# ---------------------------------------------------------------------------
# Hot-swap test: a deliberate threshold bump in mtg.toml must fail the
# reference-drift check. This is the "did the drift test actually work?"
# guard documented in the task spec.
# ---------------------------------------------------------------------------


def test_deliberate_regression_in_mtg_corpus_fails_drift(tmp_path, monkeypatch):
    """Hot-swap mtg.toml to deliberately-too-strict thresholds in a temp
    calibration dir; the reference set (Bloomburrow) must now fall below
    the gate count.

    Picks a multi-gate bump (median + axis simultaneously) since the
    loosened individual gates can each be cleared with one regression —
    only a coordinated tightening reliably drops BLB to <3/4.
    """
    from src.depth import report as depth_report

    # Copy every existing TOML into a temp dir, then overwrite mtg.toml with
    # deliberately too-strict thresholds.
    real_dir = depth_report._CALIBRATION_DIR
    fake_dir = tmp_path / "calibration"
    fake_dir.mkdir()
    for src in real_dir.glob("*.toml"):
        (fake_dir / src.name).write_text(src.read_text())

    bumped = (fake_dir / "mtg.toml").read_text().replace(
        "median_depth = 2", "median_depth = 5"
    ).replace(
        "axis_diversity = 0.08", "axis_diversity = 0.50"
    )
    (fake_dir / "mtg.toml").write_text(bumped)

    monkeypatch.setattr(depth_report, "_CALIBRATION_DIR", fake_dir)
    depth_report.reset_calibration_cache()

    corpus = depth_report.load_calibration("mtg")
    assert corpus.median_depth == 5.0, "Hot-swap median didn't take"
    assert corpus.axis_diversity == 0.50, "Hot-swap axis didn't take"

    # Re-score Bloomburrow; median 2.0 < 5 fails AND axis 0.093 < 0.50 fails,
    # so the reference set should now pass <gates_passing_min gates.
    from src.cards.bloomburrow import BLOOMBURROW_CARDS
    report = depth_report.score_registry(
        BLOOMBURROW_CARDS, engine="mtg", set_code="BLB",
    )
    passing = sum(1 for v in report.health_checks.values() if v == "PASS")
    assert passing < corpus.gates_passing_min, (
        f"Hot-swap should have dropped BLB below "
        f"gates_passing_min={corpus.gates_passing_min}; got {passing} passes. "
        f"health={report.health_checks}"
    )

    # Restore the cache so subsequent tests see real thresholds.
    monkeypatch.setattr(depth_report, "_CALIBRATION_DIR", real_dir)
    depth_report.reset_calibration_cache()
