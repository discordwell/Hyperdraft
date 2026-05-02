#!/usr/bin/env python3
"""
Regression baseline check for the deckbuilder pipeline.

Runs a deterministic mini-tournament across a fixed set of standard
decks, then diffs the resulting per-deck winrates against a committed
baseline. The goal is "did some engine/scoring change perturb the
deckbuilder in a noticeable way?", not statistical significance.

Workflow:
    # First time (no baseline yet) — script exits 2 with a hint:
    python scripts/play/regression_check.py --games 3
    # Inspect /tmp/regression_current.json, then commit it:
    cp /tmp/regression_current.json tests/baselines/hybrid_v1_matrix.json
    git add tests/baselines/hybrid_v1_matrix.json && git commit ...

    # Subsequent runs (CI on engine PRs):
    python scripts/play/regression_check.py --games 3

Exit codes:
    0 — no regression detected (or baseline & current within thresholds).
    1 — regression detected (matchup or total winrate moved beyond threshold).
    2 — baseline missing; current.json was still written for human review.

The runner uses LAZY imports so this script can live alongside W4's
in-flight tournament harness without coupling at import time. If
`scripts.play.custom_set_tournament.run_deck_tournament` is missing
when this script is invoked, an actionable error is raised pointing
at the W4 dependency.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Fixed seed for deterministic ordering. Don't change this without also
# regenerating the baseline.
DEFAULT_SEED = 42

# The deterministic deck panel. Four representative archetypes from
# STANDARD_DECKS, picked to span aggro / control / midrange-ish and a
# tempo flavor. Keys must exist in src/decks/standard_decks.py:STANDARD_DECKS.
DEFAULT_DECK_KEYS: tuple[str, ...] = (
    "mono_red_aggro",
    "dimir_control",
    "boros_aggro",
    "simic_tempo",
)


def _load_standard_pool(deck_keys: tuple[str, ...]) -> dict[str, Any]:
    """Lazy-load the STANDARD_DECKS map and return the requested subset.

    Returns a dict[label, Deck] suitable for passing to
    ``run_deck_tournament``. The label IS the deck key — the harness
    uses it as the matchup-matrix index.
    """
    from src.decks.standard_decks import STANDARD_DECKS  # noqa: WPS433

    pool: dict[str, Any] = {}
    missing: list[str] = []
    for key in deck_keys:
        deck = STANDARD_DECKS.get(key)
        if deck is None:
            missing.append(key)
            continue
        pool[key] = deck
    if missing:
        available = ", ".join(sorted(STANDARD_DECKS.keys()))
        raise SystemExit(
            f"regression_check: deck keys not found in STANDARD_DECKS: "
            f"{missing}. Available: {available}"
        )
    return pool


def _resolve_run_deck_tournament():
    """Lazy import of W4's deck-object tournament runner.

    Kept inside a function so importing this module (e.g. from the
    smoke test) does not require W4 to be merged.
    """
    try:
        from scripts.play.custom_set_tournament import (  # noqa: WPS433
            run_deck_tournament,
        )
    except ImportError as exc:  # pragma: no cover - exercised by integrators
        raise SystemExit(
            "regression_check: run_deck_tournament not yet available in "
            "scripts.play.custom_set_tournament. Round-10 W4 must land "
            "before this regression check can run.\n"
            f"Import error: {exc}"
        ) from exc
    return run_deck_tournament


def _resolve_summarize():
    """Lazy import of summarize() from diff_tournaments.

    Mirrors W6 spec: reuse the per-set winrate aggregation, do not
    duplicate it.
    """
    try:
        from scripts.play.diff_tournaments import summarize  # noqa: WPS433
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "regression_check: could not import summarize() from "
            "scripts.play.diff_tournaments. Repo may be in a broken state.\n"
            f"Import error: {exc}"
        ) from exc
    return summarize


def _run_mini_tournament(
    deck_keys: tuple[str, ...],
    games_per_pair: int,
    seed: int,
) -> dict[str, Any]:
    """Build a deck pool and run W4's deck-object tournament.

    Returns the full tournament JSON (results + aggregate). The output
    schema is intentionally identical to ``custom_set_tournament``'s
    so it can flow into ``diff_tournaments.summarize``.
    """
    # Seed the global RNG. The W4 harness does not accept an explicit
    # seed; this seeds Python's `random` module so any reachable
    # tiebreakers, shuffles, or AI fallbacks behave deterministically
    # across runs of this script. Note: any subprocess/child process
    # the harness spawns would not inherit this seed, but the current
    # sequential SIGALRM-bounded harness runs in-process.
    random.seed(seed)

    pool = _load_standard_pool(deck_keys)
    run_deck_tournament = _resolve_run_deck_tournament()

    # The W4 harness signature parallels run_tournament_sequential —
    # see crispy-riding-orbit.md §W4. The first positional is a deck
    # pool keyed by label. We pass only kwargs the harness actually
    # exposes so this script stays compatible if W4 evolves the
    # signature in compatible ways.
    results = run_deck_tournament(
        pool,
        games_per_pair=games_per_pair,
        verbose=False,
    )

    # If the harness returns the tournament dict without aggregate
    # already attached, run aggregate() ourselves to match the schema
    # consumed by summarize().
    if "aggregate" not in results:
        from scripts.play.custom_set_tournament import aggregate  # noqa: WPS433

        results = {**results, "aggregate": aggregate(results)}
    return results


def _compute_diff(
    current_summary: dict[str, dict],
    baseline_summary: dict[str, dict],
    *,
    matchup_threshold: float,
    total_threshold: float,
) -> tuple[list[str], list[str]]:
    """Return (per-deck flags, missing-deck warnings).

    Each flag is a human-readable string explaining the regression.
    """
    flags: list[str] = []
    warnings: list[str] = []

    all_keys = sorted(set(current_summary.keys()) | set(baseline_summary.keys()))
    for key in all_keys:
        cur = current_summary.get(key)
        base = baseline_summary.get(key)
        if cur is None:
            warnings.append(f"  - deck '{key}' present in baseline but absent from current run")
            continue
        if base is None:
            warnings.append(f"  - deck '{key}' present in current run but absent from baseline")
            continue

        cur_wr = float(cur.get("winrate", 0.0))
        base_wr = float(base.get("winrate", 0.0))
        delta = cur_wr - base_wr
        if abs(delta) > total_threshold:
            sign = "+" if delta >= 0 else ""
            flags.append(
                f"  ! {key}: total winrate moved {sign}{delta * 100:.1f}% "
                f"({base_wr * 100:.1f}% -> {cur_wr * 100:.1f}%) "
                f"[total_threshold={total_threshold * 100:.1f}%]"
            )

    # Per-matchup deltas. Deck pairs aren't surfaced by summarize(); we
    # compute them directly off the aggregate.matchup map of each json
    # if available.
    return flags, warnings


def _matchup_diff(
    current: dict[str, Any],
    baseline: dict[str, Any],
    matchup_threshold: float,
) -> list[str]:
    """Compute per-matchup winrate deltas off aggregate['matchup'].

    Each entry is "{a} vs {b}" -> {wins_a, wins_b, draws}. We compute
    a side-A winrate (wins_a / total_decided) for both runs and flag
    if abs(delta) exceeds matchup_threshold.
    """
    flags: list[str] = []
    cur_m = current.get("aggregate", {}).get("matchup", {}) or {}
    base_m = baseline.get("aggregate", {}).get("matchup", {}) or {}
    keys = sorted(set(cur_m.keys()) | set(base_m.keys()))
    for k in keys:
        cur_rec = cur_m.get(k)
        base_rec = base_m.get(k)
        if cur_rec is None or base_rec is None:
            continue
        cur_wr = _matchup_winrate(cur_rec)
        base_wr = _matchup_winrate(base_rec)
        if cur_wr is None or base_wr is None:
            continue
        delta = cur_wr - base_wr
        if abs(delta) > matchup_threshold:
            sign = "+" if delta >= 0 else ""
            flags.append(
                f"  ! matchup [{k}]: side-A winrate moved {sign}{delta * 100:.1f}% "
                f"({base_wr * 100:.1f}% -> {cur_wr * 100:.1f}%) "
                f"[matchup_threshold={matchup_threshold * 100:.1f}%]"
            )
    return flags


def _matchup_winrate(rec: dict[str, Any]) -> Optional[float]:
    wa = int(rec.get("wins_a", 0))
    wb = int(rec.get("wins_b", 0))
    draws = int(rec.get("draws", 0))
    decided = wa + wb
    if decided == 0:
        return None
    return wa / decided


def _print_summary(
    *,
    current_summary: dict[str, dict],
    baseline_summary: Optional[dict[str, dict]],
    flags: list[str],
    matchup_flags: list[str],
    warnings: list[str],
) -> None:
    print("=" * 70)
    print("REGRESSION CHECK — deckbuilder mini-tournament")
    print("=" * 70)

    print("\n## Current per-deck winrates")
    for key, rec in sorted(current_summary.items()):
        wins = int(rec.get("wins", 0))
        losses = int(rec.get("losses", 0))
        draws = int(rec.get("draws", 0))
        wr = float(rec.get("winrate", 0.0))
        print(f"  {key:24s}  {wr * 100:5.1f}%  ({wins}W-{losses}L-{draws}D)")

    if baseline_summary is None:
        print("\n(no baseline loaded — diff skipped)")
        return

    print("\n## Diff vs baseline")
    if not flags and not matchup_flags and not warnings:
        print("  clean — no deck moved beyond thresholds")
    else:
        for line in flags:
            print(line)
        for line in matchup_flags:
            print(line)
        for line in warnings:
            print(line)


def _emit_baseline_hint(baseline_path: Path, current_path: Path) -> None:
    print("=" * 70)
    print("REGRESSION CHECK — BASELINE MISSING")
    print("=" * 70)
    print(
        f"\nNo baseline found at {baseline_path}.\n"
        f"Current tournament JSON written to: {current_path}\n\n"
        "To create the baseline, review the current JSON for sanity then run:\n"
        f"  cp {current_path} {baseline_path}\n"
        "  git add {b} && git commit -m \"chore: commit deckbuilder regression baseline\"\n"
        "Subsequent invocations of this script will diff against that baseline."
        .format(b=baseline_path)
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic regression check for the deckbuilder.",
    )
    parser.add_argument(
        "--games",
        type=int,
        default=3,
        help="games per pair (default 3)",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("tests/baselines/hybrid_v1_matrix.json"),
        help="path to committed baseline JSON",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("/tmp/regression_current.json"),
        help="path to write current tournament JSON",
    )
    parser.add_argument(
        "--matchup-threshold",
        type=float,
        default=0.25,
        help="abs winrate delta per matchup that triggers a regression flag",
    )
    parser.add_argument(
        "--total-threshold",
        type=float,
        default=0.15,
        help="abs winrate delta per deck that triggers a regression flag",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"deterministic seed (default {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--decks",
        type=str,
        default=",".join(DEFAULT_DECK_KEYS),
        help="comma-separated STANDARD_DECKS keys",
    )
    args = parser.parse_args(argv)

    deck_keys = tuple(s.strip() for s in args.decks.split(",") if s.strip())
    if len(deck_keys) < 2:
        raise SystemExit("regression_check: need at least 2 decks for a tournament")

    # Resolve the baseline path relative to the repo root if it's
    # given as a relative path.
    baseline_path = args.baseline
    if not baseline_path.is_absolute():
        baseline_path = REPO_ROOT / baseline_path

    out_path = args.out
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path

    # 1) Run the mini-tournament.
    print(f"Running mini-tournament: {deck_keys} x {args.games} games/pair (seed={args.seed})", flush=True)
    current = _run_mini_tournament(deck_keys, args.games, args.seed)

    # 2) Always write current.json so the integrator can inspect it.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as fh:
        json.dump(current, fh, indent=2, default=str)
    print(f"Wrote current tournament JSON: {out_path}", flush=True)

    # 3) Reuse summarize() to compute per-deck winrates.
    summarize = _resolve_summarize()
    current_summary = summarize(current["aggregate"])

    # 4) Load baseline if present.
    if not baseline_path.exists():
        _emit_baseline_hint(baseline_path, out_path)
        _print_summary(
            current_summary=current_summary,
            baseline_summary=None,
            flags=[],
            matchup_flags=[],
            warnings=[],
        )
        return 2

    with baseline_path.open() as fh:
        baseline = json.load(fh)

    if "aggregate" not in baseline:
        raise SystemExit(
            f"regression_check: baseline at {baseline_path} is missing "
            "'aggregate' key — was it produced by an older harness?"
        )
    baseline_summary = summarize(baseline["aggregate"])

    # 5) Compute diff.
    flags, warnings = _compute_diff(
        current_summary,
        baseline_summary,
        matchup_threshold=args.matchup_threshold,
        total_threshold=args.total_threshold,
    )
    matchup_flags = _matchup_diff(current, baseline, args.matchup_threshold)

    _print_summary(
        current_summary=current_summary,
        baseline_summary=baseline_summary,
        flags=flags,
        matchup_flags=matchup_flags,
        warnings=warnings,
    )

    if flags or matchup_flags:
        print("\nResult: REGRESSION DETECTED (exit 1)")
        return 1
    print("\nResult: clean (exit 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
