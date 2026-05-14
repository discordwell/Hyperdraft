"""Tests for the /ultra-loop quarantine flow.

The quarantine module is intentionally small and engine-agnostic — it
operates on the loop's own log artefacts (pilot reports, coach output,
encoder output, harness logs) and decides whether a given iteration is
trustworthy enough to apply. The tests below cover the canonical BRV
v2-iter3c regression: a state-file race contaminated the iteration, the
pilot's "engine bug" claim was bogus, and the encoder applied a
``-100`` hard-block on Switch / Potion that had to be retracted.

A passing quarantine flow would have caught it: contamination signals
would trip, the encoder output would land in ``quarantine/`` instead of
the main log, and ``apply_iteration`` would refuse to write the changes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.play import ultra_loop_quarantine as q


# ──────────────────────────────────────────────────────────────────────
#  Signal detection
# ──────────────────────────────────────────────────────────────────────

def test_clean_iteration_is_not_flagged():
    artifacts = q.IterationArtifacts(
        iteration=1,
        mode="double",
        pilot_reports={
            "A": "I played a clean game, ended at turn 31 with a Boros win.",
            "B": "I played a clean game, ended at turn 31 with a Boros loss.",
        },
        coach_output="Coach: bumped Gideon weight 1.8 -> 2.0",
        encoder_output="Encoder: added Aurelia opening-active check",
        turns_played=31,
        requested_mode="double",
    )
    report = q.detect_contamination(artifacts)
    assert not report.contaminated, report.reasons
    assert report.signals == []
    assert report.reasons == []


def test_pilot_self_report_marker_is_flagged():
    artifacts = q.IterationArtifacts(
        iteration=3,
        mode="single",
        pilot_reports={
            "A": (
                "I noticed something strange: CONTAMINATED — the state "
                "file got corrupted on T4 and my packet showed Switch "
                "with no effect. Probably not actually an engine bug."
            ),
        },
        coach_output="Coach: flag Switch as broken",
        encoder_output="Encoder: -100 score for Switch",
        turns_played=11,
        requested_mode="double",  # mode collapse too
    )
    report = q.detect_contamination(artifacts)
    assert report.contaminated
    assert "pilot_self_report" in report.signals
    # The mode collapse should ALSO be detected — single mode used in a
    # requested double-mode iteration.
    assert "mode_collapse" in report.signals


def test_harness_error_in_log_is_flagged():
    artifacts = q.IterationArtifacts(
        iteration=2,
        mode="double",
        pilot_reports={"A": "ok", "B": "ok"},
        harness_log="Traceback ... EOFError: Ran out of input",
        turns_played=20,
        requested_mode="double",
    )
    report = q.detect_contamination(artifacts)
    assert report.contaminated
    assert "harness_error" in report.signals


def test_partial_completion_is_flagged():
    artifacts = q.IterationArtifacts(
        iteration=1,
        mode="single",
        pilot_reports={"A": "game ended early after T2"},
        coach_output="...",
        encoder_output="...",
        turns_played=2,
        expected_min_turns=5,
    )
    report = q.detect_contamination(artifacts)
    assert report.contaminated
    assert "partial_completion" in report.signals


def test_mode_collapse_is_flagged():
    artifacts = q.IterationArtifacts(
        iteration=1,
        mode="single",
        requested_mode="double",
        pilot_reports={"A": "fine"},
        turns_played=15,
    )
    report = q.detect_contamination(artifacts)
    assert report.contaminated
    assert "mode_collapse" in report.signals


def test_missing_double_mode_pilot_report_is_flagged():
    artifacts = q.IterationArtifacts(
        iteration=1,
        mode="double",
        requested_mode="double",
        pilot_reports={"A": "I played and won, but B never reported back"},
        turns_played=15,
    )
    report = q.detect_contamination(artifacts)
    assert report.contaminated
    assert "missing_pilot_report" in report.signals


def test_orchestrator_extra_signals_are_propagated():
    artifacts = q.IterationArtifacts(
        iteration=1,
        mode="double",
        requested_mode="double",
        pilot_reports={"A": "ok", "B": "ok"},
        turns_played=20,
        extra_signals=["watchdog killed pilot B after 5 min idle"],
    )
    report = q.detect_contamination(artifacts)
    assert report.contaminated
    assert "orchestrator" in report.signals
    assert any("watchdog" in r for r in report.reasons)


# ──────────────────────────────────────────────────────────────────────
#  Quarantine I/O
# ──────────────────────────────────────────────────────────────────────

def test_quarantine_iteration_writes_to_quarantine_subdir(tmp_path: Path):
    log_dir = tmp_path / "ultra_loop_brv_v2"
    artifacts = q.IterationArtifacts(
        iteration=3,
        mode="single",
        requested_mode="double",
        pilot_reports={"A": "CONTAMINATED stale-packet read on T4"},
        coach_output="Coach: Switch -100 score (engine bug)",
        encoder_output="Encoder: applied -100 score to Switch + Potion",
        turns_played=11,
    )
    report = q.detect_contamination(artifacts)
    assert report.contaminated

    manifest_path = q.quarantine_iteration(log_dir, artifacts, report)
    assert manifest_path.exists()
    assert manifest_path.parent == log_dir / "quarantine" / "iter03"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "quarantined"
    assert "encoder.txt" in manifest["files"]
    assert "coach.txt" in manifest["files"]
    assert "pilot_A.txt" in manifest["files"]

    # Most importantly: the encoder output must NOT be in the main log
    # dir (the apply path). Only in quarantine/.
    main_log_files = {p.name for p in log_dir.iterdir() if p.is_file()}
    assert all("encoder" not in f for f in main_log_files)


def test_apply_iteration_refuses_contaminated(tmp_path: Path):
    log_dir = tmp_path / "ultra_loop_brv_v2"
    artifacts = q.IterationArtifacts(
        iteration=3,
        mode="single",
        requested_mode="double",
        pilot_reports={"A": "CONTAMINATED"},
        coach_output="C",
        encoder_output="E",
        turns_played=11,
    )
    report = q.detect_contamination(artifacts)
    with pytest.raises(ValueError):
        q.apply_iteration(log_dir, artifacts, report)


def test_quarantine_refuses_clean_iteration(tmp_path: Path):
    log_dir = tmp_path / "ultra_loop_brv_v2"
    artifacts = q.IterationArtifacts(
        iteration=1,
        mode="double",
        requested_mode="double",
        pilot_reports={"A": "ok", "B": "ok"},
        coach_output="C",
        encoder_output="E",
        turns_played=20,
    )
    report = q.detect_contamination(artifacts)
    assert not report.contaminated
    with pytest.raises(ValueError):
        q.quarantine_iteration(log_dir, artifacts, report)


def test_apply_iteration_writes_to_main_log_when_clean(tmp_path: Path):
    log_dir = tmp_path / "ultra_loop_brv_v2"
    artifacts = q.IterationArtifacts(
        iteration=1,
        mode="double",
        requested_mode="double",
        pilot_reports={"A": "ok", "B": "ok"},
        coach_output="Coach: bumped Gideon",
        encoder_output="Encoder: opening-active check",
        turns_played=31,
    )
    report = q.detect_contamination(artifacts)
    manifest_path = q.apply_iteration(log_dir, artifacts, report)
    assert manifest_path is not None
    assert manifest_path.parent == log_dir
    assert (log_dir / "iter01_coach.txt").exists()
    assert (log_dir / "iter01_encoder.txt").exists()
    # The quarantine dir should NOT have been touched.
    assert not (log_dir / "quarantine" / "iter01").exists()


# ──────────────────────────────────────────────────────────────────────
#  Listing + review
# ──────────────────────────────────────────────────────────────────────

def test_list_quarantined_returns_all_manifests(tmp_path: Path):
    log_dir = tmp_path / "loop"
    for n, sig in [(2, "harness_error"), (3, "mode_collapse")]:
        artifacts = q.IterationArtifacts(
            iteration=n,
            mode="single",
            requested_mode="double",
            pilot_reports={"A": "ABORT"},
            coach_output="C",
            encoder_output="E",
            turns_played=3,
        )
        report = q.detect_contamination(artifacts)
        q.quarantine_iteration(log_dir, artifacts, report)

    listed = q.list_quarantined(log_dir)
    assert len(listed) == 2
    iters = sorted(m["iteration"] for m in listed)
    assert iters == [2, 3]


def test_mark_verified_flips_status(tmp_path: Path):
    log_dir = tmp_path / "loop"
    artifacts = q.IterationArtifacts(
        iteration=3,
        mode="single",
        requested_mode="double",
        pilot_reports={"A": "CONTAMINATED"},
        coach_output="C",
        encoder_output="E",
        turns_played=11,
    )
    report = q.detect_contamination(artifacts)
    q.quarantine_iteration(log_dir, artifacts, report)

    q.mark_verified(
        log_dir,
        iteration=3,
        reproducer_test="tests/test_brv_gap_v3.py::test_switch_swaps_active_and_bench",
        notes="reproducer confirms Switch actually works",
    )
    manifest = json.loads(
        (log_dir / "quarantine" / "iter03" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "verified"
    assert manifest["reproducer_test"].endswith("test_switch_swaps_active_and_bench")
    assert "verified_at" in manifest


def test_mark_dismissed_flips_status(tmp_path: Path):
    log_dir = tmp_path / "loop"
    artifacts = q.IterationArtifacts(
        iteration=3,
        mode="single",
        requested_mode="double",
        pilot_reports={"A": "CONTAMINATED"},
        coach_output="C",
        encoder_output="E",
        turns_played=11,
    )
    report = q.detect_contamination(artifacts)
    q.quarantine_iteration(log_dir, artifacts, report)

    q.mark_dismissed(log_dir, iteration=3, notes="false alarm, retracted")
    manifest = json.loads(
        (log_dir / "quarantine" / "iter03" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "dismissed"
    assert "dismissed_at" in manifest


def test_retroactive_quarantine_handles_post_hoc_discovery(tmp_path: Path):
    """The canonical BRV v2-iter3c case: contamination was named in the
    progression report but the encoder's changes had already landed.
    The reviewer reaches for ``retroactive_quarantine`` to record what
    happened so /quarantine-review can prompt for reproducers.
    """
    log_dir = tmp_path / "ultra_loop_brv_v2"
    log_dir.mkdir(parents=True)
    manifest_path = q.retroactive_quarantine(
        log_dir,
        iteration=3,
        reasons=[
            "single-mode used in a double-mode loop (mode collapse)",
            "state-file race truncated pickle (stale packet on T4)",
        ],
        coach_output="Coach: Switch -100",
        encoder_output="Encoder: -100 score to Switch / Potion in trainers.py",
    )
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "quarantined"
    assert "retroactive" in manifest["signals"]


def test_summarize_run_returns_clean_plus_quarantined_counts(tmp_path: Path):
    log_dir = tmp_path / "loop"
    # 2 clean iters
    for n in (1, 2):
        clean = q.IterationArtifacts(
            iteration=n,
            mode="double",
            requested_mode="double",
            pilot_reports={"A": "ok", "B": "ok"},
            coach_output="C",
            encoder_output="E",
            turns_played=20,
        )
        clean_report = q.detect_contamination(clean)
        q.apply_iteration(log_dir, clean, clean_report)
    # 1 contaminated iter
    bad = q.IterationArtifacts(
        iteration=3,
        mode="single",
        requested_mode="double",
        pilot_reports={"A": "CONTAMINATED"},
        coach_output="C",
        encoder_output="E",
        turns_played=11,
    )
    bad_report = q.detect_contamination(bad)
    q.quarantine_iteration(log_dir, bad, bad_report)

    summary = q.summarize_run(log_dir)
    assert summary["clean_iterations"] == 2
    assert summary["quarantined_iterations"] == 1

    formatted = q.format_summary(summary)
    assert "clean iterations:      2" in formatted
    assert "quarantined iterations:1" in formatted
    assert "/quarantine-review" in formatted


# ──────────────────────────────────────────────────────────────────────
#  Cross-log discovery
# ──────────────────────────────────────────────────────────────────────

def test_discover_quarantined_across_logs(tmp_path: Path):
    root = tmp_path / "logs"
    for name in ("ultra_loop_brv_v1", "ultra_loop_brv_v2"):
        log_dir = root / name
        artifacts = q.IterationArtifacts(
            iteration=1,
            mode="single",
            requested_mode="double",
            pilot_reports={"A": "CONTAMINATED"},
            coach_output="C",
            encoder_output="E",
            turns_played=2,
        )
        report = q.detect_contamination(artifacts)
        q.quarantine_iteration(log_dir, artifacts, report)

    found = q.discover_quarantined_across_logs(root)
    assert len(found) == 2
    log_dirs = {m["log_dir"] for m in found}
    assert any(d.endswith("ultra_loop_brv_v1") for d in log_dirs)
    assert any(d.endswith("ultra_loop_brv_v2") for d in log_dirs)


# ──────────────────────────────────────────────────────────────────────
#  Regression: the BRV v2-iter3c scenario
# ──────────────────────────────────────────────────────────────────────

def test_brv_v2_iter3c_would_have_been_quarantined(tmp_path: Path):
    """End-to-end: replay the BRV v2-iter3c artefacts and confirm the
    quarantine flow would have caught them.

    Signals expected:
    * mode_collapse — requested double, ran as single
    * harness_error — state-file race / stale packet evidence
    * partial_completion — game terminated at T11 with only one pilot
      effectively engaged
    The Switch / Potion ``-100`` bug claims would have landed in
    ``quarantine/iter03/encoder.txt`` instead of ``trainers.py``.
    """

    log_dir = tmp_path / "ultra_loop_brv_v2"
    pilot_report = (
        "# BRV Pilot Report — iteration 3c\n"
        "## Outcome\n"
        "Dimir won in 11 turns. Pilot played both seats sub-optimally.\n"
        "## Mode\n"
        "Single mode used in a double-mode loop — pilot effectively played both seats.\n"
        "## Anomalies\n"
        "- T4: state file appears stale; my packet shows Switch played\n"
        "  with no Active↔Bench swap. PARALLEL WRITE RACE suspected.\n"
        "- T6: same with Potion — card consumed, no heal.\n"
        "## Suggested updates\n"
        "Add hard-blocks on Switch and Potion until engine is fixed.\n"
    )
    harness_log = (
        "Traceback (most recent call last):\n"
        '  File "scripts/play/pokemon_codex_match.py", line 412, in _load_state\n'
        "    state = pickle.load(f)\n"
        "EOFError: Ran out of input\n"
    )
    coach = (
        "Coach: applying pilot suggestion — hard-block Switch and Potion "
        "in src/ai/pokemon/trainers.py."
    )
    encoder = (
        "Encoder change list:\n"
        "* trainers.py Switch scorer: return -100.0 (engine bug)\n"
        "* trainers.py Potion scorer: return -100.0 (engine bug)\n"
    )

    artifacts = q.IterationArtifacts(
        iteration=3,
        mode="single",
        requested_mode="double",
        pilot_reports={"A": pilot_report},
        coach_output=coach,
        encoder_output=encoder,
        harness_log=harness_log,
        turns_played=11,
        expected_min_turns=15,
    )
    report = q.detect_contamination(artifacts)

    assert report.contaminated
    # All four diagnostic signals fire on this iteration.
    for signal in ("pilot_self_report", "harness_error", "partial_completion", "mode_collapse"):
        assert signal in report.signals, (signal, report.signals, report.reasons)

    manifest_path = q.quarantine_iteration(log_dir, artifacts, report)

    # The encoder's ``-100`` claim is now in quarantine, NOT in trainers.py.
    encoder_payload = (log_dir / "quarantine" / "iter03" / "encoder.txt").read_text(
        encoding="utf-8"
    )
    assert "-100" in encoder_payload
    # And the main log dir has no encoder file for iter03.
    assert not (log_dir / "iter03_encoder.txt").exists()
    # The manifest is ready for /quarantine-review.
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "quarantined"
    assert manifest["reproducer_test"] is None  # reviewer fills in
