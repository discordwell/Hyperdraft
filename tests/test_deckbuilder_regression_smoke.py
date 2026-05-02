#!/usr/bin/env python3
"""
Pipeline-runs smoke test for ``scripts/play/regression_check.py``.

This is intentionally NOT a correctness gate — the regression check
itself emits exit-code 1 on real regressions, which is the human's
review surface. Here we only assert that the pipeline plumbing is
intact: the script imports cleanly, the deck pool resolves, and the
runner returns without an unhandled exception in ~30s.

Exit-code contract (must match scripts/play/regression_check.py):
    0 — clean (no regression)
    1 — regression detected (still a successful pipeline run)
    2 — baseline missing (still a successful pipeline run; first-run
        bootstrap mode)

The test passes if the script exits with any of {0, 1, 2}.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "play" / "regression_check.py"

# Allowed exit codes for "the pipeline ran". Anything else (e.g. 3+ from
# argparse, signals, or unhandled exceptions translated to non-zero)
# fails the smoke test.
ALLOWED_EXIT_CODES = {0, 1, 2}

# 30-second smoke budget; the runner uses 1 game per pair to fit within
# it. The W4 harness has its own per-game SIGALRM so individual hangs
# can't blow this out.
SMOKE_TIMEOUT_S = 90  # generous to avoid flake on cold start


@pytest.mark.skipif(
    not SCRIPT.exists(),
    reason="regression_check.py not present (W6 not yet integrated)",
)
def test_regression_check_pipeline_runs(tmp_path: Path) -> None:
    """Run the regression check with --games 1 and verify exit ∈ {0,1,2}."""
    out_path = tmp_path / "regression_current.json"
    # Use a baseline path inside tmp_path so the test never accidentally
    # exercises a freshly-committed baseline. First-run-style behavior
    # (exit 2) is the expected smoke outcome here.
    baseline_path = tmp_path / "nonexistent_baseline.json"

    env = os.environ.copy()
    # Ensure the repo is importable when run from any cwd.
    env["PYTHONPATH"] = f"{REPO_ROOT}{os.pathsep}{env.get('PYTHONPATH', '')}"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--games",
            "1",
            "--baseline",
            str(baseline_path),
            "--out",
            str(out_path),
        ],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=SMOKE_TIMEOUT_S,
    )

    # Echo subprocess output so failures are debuggable in CI logs.
    if proc.returncode not in ALLOWED_EXIT_CODES:
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)

    assert proc.returncode in ALLOWED_EXIT_CODES, (
        f"regression_check.py exited with {proc.returncode}; "
        f"expected one of {sorted(ALLOWED_EXIT_CODES)}.\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )

    # If the script reached the baseline-missing branch (exit 2), it
    # should still have written current.json for inspection.
    if proc.returncode == 2:
        assert out_path.exists(), (
            "regression_check.py exited 2 (baseline missing) but did "
            f"not write current.json at {out_path}"
        )


def test_regression_check_module_imports() -> None:
    """The regression_check module imports without invoking the runner.

    Lazy imports of run_deck_tournament and summarize should NOT fire
    at import time. This guards against accidental coupling that would
    break CI before W4 lands.
    """
    if not SCRIPT.exists():
        pytest.skip("regression_check.py not present (W6 not yet integrated)")

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "regression_check_smoke_module", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # If lazy imports leaked, this load would raise on a missing W4 export.
    spec.loader.exec_module(mod)

    assert hasattr(mod, "main"), "regression_check should expose main()"
    assert callable(mod.main)
