"""Contamination detection + quarantine workflow for /ultra-loop.

Background
----------
The /ultra-loop training loop spawns LLM pilots, a coach, and a heuristic
encoder. The encoder converts the pilot's observations into adapter code
changes. If the pilot's game was *contaminated* — harness errors, mode
collapse (single-mode where one pilot played both seats), partial play,
state-file race conditions — the encoder can still produce plausible-looking
"bug fixes" that silently land in real code.

That happened in the BRV v2-iter3c session: a state-file race truncated
the pickle, the pilot read stale packets, mis-attributed the resulting
"card consumed but no effect" to engine bugs in Switch and Potion, and
the encoder applied ``-100`` hard-block scorers in
``src/ai/pokemon/trainers.py`` that silenced two working cards until
they were retracted in commit 7a982116.

This module gives the loop a small, testable surface for:

* Reading the iteration's pilot reports + run metadata.
* Scoring them against an explicit list of contamination signals.
* If contaminated, copying the coach/encoder outputs into a
  ``quarantine/`` sub-directory of the loop's log dir rather than letting
  them be applied.
* Producing a manifest of quarantined claims a reviewer can walk through
  with ``/quarantine-review``.

The module has no dependency on any specific engine — it operates on the
loop's own artefacts. That keeps it engine-agnostic, matching /ultra-loop
itself.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


# ──────────────────────────────────────────────────────────────────────
#  Signal definitions
# ──────────────────────────────────────────────────────────────────────

# Pilot-report markers that explicitly flag contamination. Pilots are
# instructed to write these strings when they detect trouble.
CONTAMINATION_REPORT_MARKERS: tuple[str, ...] = (
    "CONTAMINATED",
    "STATE FILE CORRUPTED",
    "STATE FILE CORRUPTION",
    "PICKLE TRUNCATED",
    "STALE PACKET",
    "PARALLEL WRITE RACE",
    "AI EXECUTED ON OFF-TURN",
    "PILOT CRASHED",
    "PLAYED BOTH SEATS",
    "MODE COLLAPSE",
    "FALLBACK TO HEURISTIC",
    "ABORT",
)

# Free-text harness error patterns that mean "the iteration's data
# is not trustworthy regardless of what the pilot wrote."
HARNESS_ERROR_PATTERNS: tuple[str, ...] = (
    r"EOFError",
    r"UnpicklingError",
    r"ran out of input",
    r"pickle data was truncated",
    r"BrokenPipeError",
    r"state file .*not found",
    r"refused.*active.player",
    r"two[- ]pilot mode disabled",
)

DEFAULT_MIN_TURNS = 5  # Below this we treat the game as a stub run.


# ──────────────────────────────────────────────────────────────────────
#  Data classes
# ──────────────────────────────────────────────────────────────────────

@dataclass
class IterationArtifacts:
    """Inputs collected for one iteration of /ultra-loop.

    Optional fields default to None/empty so callers can provide whatever
    subset they have. The loop typically populates all of them; tests can
    populate just the relevant fields.
    """

    iteration: int
    mode: str  # "single" or "double"
    pilot_reports: dict[str, str] = field(default_factory=dict)  # seat -> report text
    coach_output: str | None = None
    encoder_output: str | None = None
    harness_log: str | None = None
    turns_played: int | None = None
    expected_min_turns: int = DEFAULT_MIN_TURNS
    requested_mode: str | None = None  # what the user asked for; differs if we fell back
    pilot_self_reported_contaminated: bool = False
    extra_signals: list[str] = field(default_factory=list)


@dataclass
class ContaminationReport:
    """Result of grading an iteration."""

    iteration: int
    contaminated: bool
    signals: list[str]
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────
#  Signal detection
# ──────────────────────────────────────────────────────────────────────

def _scan_text_for_markers(text: str | None, markers: Iterable[str]) -> list[str]:
    if not text:
        return []
    upper = text.upper()
    return [m for m in markers if m.upper() in upper]


def _scan_text_for_patterns(text: str | None, patterns: Iterable[str]) -> list[str]:
    if not text:
        return []
    hits: list[str] = []
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            hits.append(pat)
    return hits


def detect_contamination(artifacts: IterationArtifacts) -> ContaminationReport:
    """Grade an iteration. Returns (signals, reasons) and a top-level flag.

    Signals are short identifiers (good for filter/group). Reasons are
    short human-readable strings the reviewer sees in the manifest.
    Detection is intentionally cheap and deterministic so the same
    artefacts always grade the same way.
    """

    signals: list[str] = []
    reasons: list[str] = []

    # 1. Pilot self-report markers (the strongest signal — pilots are
    #    trained to call this out explicitly).
    for seat, report in artifacts.pilot_reports.items():
        hits = _scan_text_for_markers(report, CONTAMINATION_REPORT_MARKERS)
        if hits:
            signals.append("pilot_self_report")
            reasons.append(
                f"pilot {seat} flagged: {', '.join(sorted(set(hits)))}"
            )

    if artifacts.pilot_self_reported_contaminated:
        signals.append("pilot_self_report")
        reasons.append("pilot_self_reported_contaminated flag set")

    # 2. Harness errors in the run log or in pilot reports.
    for source_name, source_text in [
        ("harness_log", artifacts.harness_log),
        *((f"pilot_{seat}_report", txt) for seat, txt in artifacts.pilot_reports.items()),
        ("coach_output", artifacts.coach_output),
    ]:
        hits = _scan_text_for_patterns(source_text, HARNESS_ERROR_PATTERNS)
        if hits:
            signals.append("harness_error")
            reasons.append(
                f"{source_name}: harness error pattern(s) {', '.join(hits)}"
            )

    # 3. Truncated play — game ended without enough turns to be representative.
    if artifacts.turns_played is not None:
        if artifacts.turns_played < artifacts.expected_min_turns:
            signals.append("partial_completion")
            reasons.append(
                f"game ended at turn {artifacts.turns_played} "
                f"(expected ≥ {artifacts.expected_min_turns})"
            )

    # 4. Mode collapse — user asked for double-mode but the loop fell
    #    back to single, so the pilot effectively played both seats and
    #    can't be cross-checked.
    if (
        artifacts.requested_mode
        and artifacts.mode
        and artifacts.requested_mode.lower() != artifacts.mode.lower()
    ):
        signals.append("mode_collapse")
        reasons.append(
            f"requested mode={artifacts.requested_mode!r} but ran as "
            f"{artifacts.mode!r}"
        )

    # 5. In double mode, missing one of the two pilot reports means a
    #    pilot crashed and the surviving pilot played both perspectives
    #    or filled the gap with a heuristic. Either way, contaminated.
    if artifacts.mode == "double" and len(artifacts.pilot_reports) < 2:
        signals.append("missing_pilot_report")
        reasons.append(
            f"double mode but only {len(artifacts.pilot_reports)} pilot report(s)"
        )

    # 6. Extra signals passed in by the caller (e.g. orchestrator
    #    notices a SIGTERM, watchdog kills the agent, etc.).
    for raw in artifacts.extra_signals:
        signals.append("orchestrator")
        reasons.append(raw)

    # De-dup signals while preserving order.
    seen: set[str] = set()
    dedup_signals: list[str] = []
    for s in signals:
        if s not in seen:
            dedup_signals.append(s)
            seen.add(s)

    return ContaminationReport(
        iteration=artifacts.iteration,
        contaminated=bool(dedup_signals),
        signals=dedup_signals,
        reasons=reasons,
    )


# ──────────────────────────────────────────────────────────────────────
#  Quarantine I/O
# ──────────────────────────────────────────────────────────────────────

def quarantine_dir(log_dir: Path) -> Path:
    """Return the quarantine directory for a given loop log root.

    Creates it if absent — quarantine output should never silently fail.
    """

    qdir = Path(log_dir) / "quarantine"
    qdir.mkdir(parents=True, exist_ok=True)
    return qdir


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def quarantine_iteration(
    log_dir: Path,
    artifacts: IterationArtifacts,
    report: ContaminationReport,
) -> Path:
    """Write the iteration's coach/encoder outputs into the quarantine dir.

    Returns the path to the manifest JSON. Coach/encoder outputs are
    copied (so they don't get applied), and a sidecar manifest records
    why and what to do next.
    """

    if not report.contaminated:
        raise ValueError(
            "quarantine_iteration called on an iteration that wasn't "
            "flagged contaminated; the loop should call apply_iteration instead"
        )

    qdir = quarantine_dir(log_dir)
    iter_slug = f"iter{artifacts.iteration:02d}"
    iter_dir = qdir / iter_slug
    iter_dir.mkdir(parents=True, exist_ok=True)

    payloads: dict[str, str | None] = {
        "coach": artifacts.coach_output,
        "encoder": artifacts.encoder_output,
    }
    for seat, txt in artifacts.pilot_reports.items():
        payloads[f"pilot_{seat}"] = txt
    if artifacts.harness_log:
        payloads["harness_log"] = artifacts.harness_log

    written: list[str] = []
    for name, body in payloads.items():
        if body is None:
            continue
        target = iter_dir / f"{name}.txt"
        target.write_text(body, encoding="utf-8")
        written.append(target.name)

    manifest = {
        "schema_version": "ultra_loop.quarantine.v1",
        "iteration": artifacts.iteration,
        "mode": artifacts.mode,
        "requested_mode": artifacts.requested_mode,
        "turns_played": artifacts.turns_played,
        "quarantined_at": _now_iso(),
        "signals": report.signals,
        "reasons": report.reasons,
        "files": sorted(written),
        "status": "quarantined",  # → "verified" once a reproducer passes
        "review_notes": "",
        "reproducer_test": None,  # filled in by /quarantine-review
    }
    manifest_path = iter_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return manifest_path


def list_quarantined(log_dir: Path) -> list[dict[str, Any]]:
    """Return manifests for every quarantined iteration in log_dir.

    Used by /quarantine-review to show the user what needs triage.
    """

    qdir = Path(log_dir) / "quarantine"
    if not qdir.exists():
        return []
    manifests: list[dict[str, Any]] = []
    for sub in sorted(qdir.iterdir()):
        if not sub.is_dir():
            continue
        m = sub / "manifest.json"
        if not m.exists():
            continue
        try:
            manifests.append(json.loads(m.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return manifests


def discover_quarantined_across_logs(root: Path) -> list[dict[str, Any]]:
    """Walk `root/` (typically the project's `logs/` dir) and return
    every quarantine manifest found, decorated with its log_dir.
    """

    out: list[dict[str, Any]] = []
    root = Path(root)
    if not root.exists():
        return out
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        for m in list_quarantined(child):
            m = dict(m)
            m["log_dir"] = str(child)
            out.append(m)
    return out


# ──────────────────────────────────────────────────────────────────────
#  Apply / dismiss
# ──────────────────────────────────────────────────────────────────────

def mark_verified(
    log_dir: Path,
    iteration: int,
    reproducer_test: str,
    notes: str = "",
) -> Path:
    """Mark a quarantined iteration as verified after a reproducer test exists.

    The encoder's outputs in the manifest can now be re-applied with
    confidence. The manifest's status field flips to ``"verified"``.
    """

    iter_dir = Path(log_dir) / "quarantine" / f"iter{iteration:02d}"
    manifest_path = iter_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "verified"
    manifest["reproducer_test"] = reproducer_test
    manifest["review_notes"] = notes
    manifest["verified_at"] = _now_iso()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def mark_dismissed(log_dir: Path, iteration: int, notes: str = "") -> Path:
    """Mark a quarantined iteration as a false alarm — encoder claims
    are dropped, not applied.
    """

    iter_dir = Path(log_dir) / "quarantine" / f"iter{iteration:02d}"
    manifest_path = iter_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "dismissed"
    manifest["review_notes"] = notes
    manifest["dismissed_at"] = _now_iso()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


# ──────────────────────────────────────────────────────────────────────
#  Clean apply path (for non-quarantined iterations)
# ──────────────────────────────────────────────────────────────────────

def apply_iteration(
    log_dir: Path,
    artifacts: IterationArtifacts,
    report: ContaminationReport,
) -> Path | None:
    """Write the iteration's coach/encoder outputs into the main loop log.

    This is the normal, non-quarantined path. The orchestrator should
    call this when ``report.contaminated`` is False — it copies the
    outputs into ``logs/<run>/iterN_*.txt`` where downstream consumers
    (the coach apply step, the encoder apply step) pick them up.

    Returns the path to the iter manifest, or None if nothing was written.
    """

    if report.contaminated:
        raise ValueError(
            "apply_iteration called on a contaminated iteration; "
            "the loop should call quarantine_iteration instead"
        )

    out = Path(log_dir)
    out.mkdir(parents=True, exist_ok=True)
    iter_slug = f"iter{artifacts.iteration:02d}"
    written: list[str] = []
    for name, body in [
        ("coach", artifacts.coach_output),
        ("encoder", artifacts.encoder_output),
    ]:
        if body is None:
            continue
        target = out / f"{iter_slug}_{name}.txt"
        target.write_text(body, encoding="utf-8")
        written.append(target.name)

    if not written:
        return None

    manifest_path = out / f"{iter_slug}_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "ultra_loop.iter.v1",
                "iteration": artifacts.iteration,
                "mode": artifacts.mode,
                "turns_played": artifacts.turns_played,
                "status": "applied",
                "files": sorted(written),
                "applied_at": _now_iso(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


# ──────────────────────────────────────────────────────────────────────
#  Retroactive quarantine
# ──────────────────────────────────────────────────────────────────────

def retroactive_quarantine(
    log_dir: Path,
    iteration: int,
    reasons: list[str],
    coach_output: str | None = None,
    encoder_output: str | None = None,
) -> Path:
    """Move an already-applied iteration into quarantine after the fact.

    Used when contamination is discovered after the loop finished (the
    canonical example: BRV v2-iter3c, where the contamination was named
    in the progression report but the encoder's changes had already
    landed in code). The caller is responsible for reverting any code
    changes that came from the now-quarantined iteration; this function
    only moves the artefacts.
    """

    artifacts = IterationArtifacts(
        iteration=iteration,
        mode="unknown",
        coach_output=coach_output,
        encoder_output=encoder_output,
    )
    report = ContaminationReport(
        iteration=iteration,
        contaminated=True,
        signals=["retroactive"],
        reasons=reasons,
    )
    return quarantine_iteration(log_dir, artifacts, report)


# ──────────────────────────────────────────────────────────────────────
#  Summary builder
# ──────────────────────────────────────────────────────────────────────

def summarize_run(log_dir: Path) -> dict[str, Any]:
    """Build the end-of-loop summary the orchestrator surfaces to the user.

    Returns the counts and the list of quarantined iteration manifests.
    """

    log_dir = Path(log_dir)
    quarantined = list_quarantined(log_dir)
    # Count clean iterations by looking for non-quarantined manifests.
    clean = 0
    for entry in log_dir.glob("iter*_manifest.json"):
        try:
            data = json.loads(entry.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("status") == "applied":
            clean += 1
    return {
        "log_dir": str(log_dir),
        "clean_iterations": clean,
        "quarantined_iterations": len(quarantined),
        "quarantined": quarantined,
    }


def format_summary(summary: dict[str, Any]) -> str:
    """Render the summary as a short multiline string for the loop's
    final report.
    """

    out = [
        f"=== /ultra-loop summary for {summary['log_dir']} ===",
        f"clean iterations:      {summary['clean_iterations']}",
        f"quarantined iterations:{summary['quarantined_iterations']}",
    ]
    if summary["quarantined_iterations"]:
        out.append("")
        out.append("Quarantined (run /quarantine-review to triage):")
        for q in summary["quarantined"]:
            sigs = ", ".join(q.get("signals", []))
            out.append(f"  - iter {q['iteration']}: {sigs}")
    return "\n".join(out)


__all__ = [
    "CONTAMINATION_REPORT_MARKERS",
    "HARNESS_ERROR_PATTERNS",
    "ContaminationReport",
    "IterationArtifacts",
    "apply_iteration",
    "detect_contamination",
    "discover_quarantined_across_logs",
    "format_summary",
    "list_quarantined",
    "mark_dismissed",
    "mark_verified",
    "quarantine_dir",
    "quarantine_iteration",
    "retroactive_quarantine",
    "summarize_run",
]
