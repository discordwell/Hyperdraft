"""Ultra-agent telemetry: per-decision JSONL capture + post-match takeaway synth.

The LLM-pilot ("ultra") sub-system invokes `claude -p` subprocesses that read
match state and submit actions back via REST. The reasoning lives in the
subprocess and is hard to extract, but the **resulting action** is observable
at the action POST endpoint. This module captures one JSONL line per ultra
decision, and after the match ends synthesises a 4-6 line "Session takeaway"
that the supervisor appends to `storage/strategy/<game_mode>.md`.

Layout::

    storage/ultra-agent/decisions/<match_id>.jsonl
        ↳ first line: {"_meta": {<match_id, game_mode, model_id, git_sha, ...>}}
        ↳ subsequent lines: one per ultra decision (see DECISION_FIELDS)

The decision JSONL is what `/api/match/ultra-summary` aggregates over, and is
the seed for the per-match "decisions logged" counters.

Schema notes
------------
- ``reasoning``: the LLM's free-form rationale, if the pilot sends it on the
  action POST. The launcher script doesn't currently surface it server-side
  (it lives in subprocess stdout), but the schema reserves the field so a
  future ``PlayerActionRequest.reasoning`` extension lights up automatically.
- ``actor_is_ultra``: True only for the externally-driven Ultra seats. Human
  actions and heuristic AI actions are skipped at the call site.

All file writes are best-effort: telemetry must never break the game-loop.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import statistics
import subprocess
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Optional

log = logging.getLogger(__name__)

DECISIONS_DIR = Path("storage/ultra-agent/decisions")
TAKEAWAY_HEADING = "## Session takeaway"
SESSION_TAKEAWAYS_ANCHOR = "## Session takeaways"
MAX_TAKEAWAYS_PER_DOC = 50  # rotate older ones to <mode>.archive.md


# =============================================================================
# Module-level metadata (resolved once at boot, cached on the module).
# =============================================================================

_git_sha_cache: Optional[str] = None


def get_git_sha() -> str:
    """Return ``git rev-parse --short HEAD`` for the worktree, cached.

    Falls back to ``"unknown"`` outside a git checkout (e.g. inside a build
    container that didn't ship the .git dir). The result is cached at module
    level so we don't fork on every match — the SHA can't change without a
    container restart anyway.
    """
    global _git_sha_cache
    if _git_sha_cache is not None:
        return _git_sha_cache
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(Path(__file__).resolve().parents[2]),
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        sha = out.stdout.strip()
        if sha:
            _git_sha_cache = sha
            return sha
    except (OSError, subprocess.SubprocessError) as e:  # noqa: BLE001
        log.debug("git_sha lookup failed: %s", e)
    _git_sha_cache = "unknown"
    return _git_sha_cache


def reset_git_sha_cache_for_test() -> None:
    """Test helper — clear the cache so tests can monkeypatch the result."""
    global _git_sha_cache
    _git_sha_cache = None


# =============================================================================
# Per-match metadata: written once at file creation.
# =============================================================================


def _decisions_path(match_id: str) -> Path:
    return DECISIONS_DIR / f"{match_id}.jsonl"


def init_match_metadata(
    *,
    match_id: str,
    game_mode: Optional[str],
    ultra_model_id: Optional[str],
    agent_runner: Optional[str] = None,
    extra: Optional[dict] = None,
) -> Optional[Path]:
    """Create the decisions JSONL with a single ``_meta`` header line.

    Idempotent: if the file already exists, it's left alone (the header line
    survives across restarts). Returns the file path on success, or None if
    the write failed.
    """
    if not match_id:
        return None
    path = _decisions_path(match_id)
    try:
        DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 0:
            return path
        meta = {
            "_meta": {
                "match_id": match_id,
                "game_mode": game_mode,
                "model_id": ultra_model_id or os.environ.get("ULTRA_MODEL_ID") or os.environ.get("ULTRA_MODEL"),
                "git_sha": get_git_sha(),
                "agent_runner": (agent_runner or "claude").strip().lower(),
                "created_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "schema_version": 1,
                **(extra or {}),
            }
        }
        with path.open("a") as fh:
            fh.write(json.dumps(meta, default=str) + "\n")
    except OSError as e:
        log.warning("ultra_telemetry: init_match_metadata failed for %s: %s", match_id, e)
        return None
    return path


def append_decision(
    *,
    match_id: str,
    player_id: str,
    turn: Optional[int],
    phase: Optional[str],
    action_type: str,
    action_payload: Optional[dict],
    actor_is_ultra: bool,
    ai_difficulty: Optional[str] = None,
    reasoning: Optional[str] = None,
) -> bool:
    """Append a single decision JSONL line. Returns True on success.

    Only logs when ``actor_is_ultra`` is True — heuristic AI and human
    decisions are skipped at the call site (cheap, but the guard keeps the
    public API symmetric so callers can pass everything).

    See module docstring for schema.

    TODO(reasoning capture): once the launcher / pilot sends a structured
    ``reasoning`` field on the action POST, that string will be carried
    here transparently — schema is already prepared.
    """
    if not actor_is_ultra or not match_id:
        return False
    path = _decisions_path(match_id)
    record = {
        "ts": round(time.time(), 3),
        "match_id": match_id,
        "player_id": player_id,
        "turn": int(turn) if turn is not None else None,
        "phase": str(phase) if phase is not None else None,
        "action_type": str(action_type),
        "action_payload": _scrub_payload(action_payload or {}),
        "actor_is_ultra": True,
        "ai_difficulty": ai_difficulty or "ultra",
    }
    if reasoning:
        record["reasoning"] = str(reasoning)
    try:
        DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
        return True
    except OSError as e:
        log.warning("ultra_telemetry: append_decision failed for %s: %s", match_id, e)
        return False


def _scrub_payload(payload: dict) -> dict:
    """Strip noisy fields and clamp the payload to a primitive-only dict.

    The action POST can carry attack/block declarations with deep nested
    structure; we keep the top-level scalars and shallow lists, and drop
    anything else. This keeps each JSONL line short and parseable.
    """
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, (list, tuple)):
            # Keep one level of nesting only.
            out[k] = [
                vv if isinstance(vv, (str, int, float, bool, type(None))) else str(vv)
                for vv in v[:32]  # cap len
            ]
        elif isinstance(v, dict):
            out[k] = {
                kk: vv for kk, vv in v.items()
                if isinstance(vv, (str, int, float, bool)) or vv is None
            }
        else:
            out[k] = str(v)
    return out


# =============================================================================
# Reader helpers — used by /api/match/ultra-summary and the supervisor.
# =============================================================================


def read_decisions(match_id: str) -> tuple[Optional[dict], list[dict]]:
    """Return ``(meta, decisions)`` for a match.

    ``meta`` is None if the file is missing or has no ``_meta`` header.
    ``decisions`` may include zero lines (just a header).
    """
    path = _decisions_path(match_id)
    if not path.exists():
        return None, []
    meta: Optional[dict] = None
    decisions: list[dict] = []
    try:
        with path.open("r") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and "_meta" in obj:
                    meta = obj["_meta"]
                else:
                    decisions.append(obj)
    except OSError as e:
        log.warning("ultra_telemetry: read_decisions failed for %s: %s", match_id, e)
    return meta, decisions


def count_decisions_by_seat(match_id: str) -> dict[str, int]:
    """Per-seat decision count for a match. Skips the _meta header."""
    _, decisions = read_decisions(match_id)
    counts: Counter[str] = Counter()
    for d in decisions:
        pid = d.get("player_id")
        if pid:
            counts[str(pid)] += 1
    return dict(counts)


# =============================================================================
# Session-takeaway synthesis (Feature 2).
# =============================================================================


def _format_takeaway_lines(
    *,
    match_id: str,
    game_mode: str,
    winner_id: Optional[str],
    winner_label: Optional[str],
    total_turns: Optional[int],
    decisions_by_seat: dict[str, int],
    seat_labels: dict[str, str],
    most_played: Optional[str],
    notes_extra: Optional[str],
) -> str:
    """Format the multi-line markdown block written to the strategy doc."""
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header = f"{TAKEAWAY_HEADING} — {now} · match {match_id[:8]}"
    winner_str = "draw / unfinished"
    if winner_id:
        label = winner_label or seat_labels.get(winner_id) or winner_id
        winner_str = label
    # Decisions logged line: "A: 47 / B: 51" (seat ordering best-effort, sorted)
    if decisions_by_seat:
        sorted_seats = sorted(decisions_by_seat.items())
        dec_pieces = [
            f"{seat_labels.get(pid, pid[:8])}: {n}"
            for pid, n in sorted_seats
        ]
        decisions_str = " / ".join(dec_pieces)
    else:
        decisions_str = "0"
    parts = [
        header,
        f"- **Winner**: {winner_str}",
        f"- **Result**: {('win on turn ' + str(total_turns)) if total_turns and winner_id else 'inconclusive'}",
        f"- **Engine**: {game_mode}",
        f"- **Decisions logged**: {decisions_str}",
    ]
    if most_played:
        parts.append(f"- **Most-played action**: {most_played}")
    if notes_extra:
        parts.append(f"- **Notes**: {notes_extra}")
    return "\n".join(parts) + "\n"


def synthesize_takeaway(
    *,
    match_id: str,
    game_mode: str,
    winner_id: Optional[str],
    seat_labels: Optional[dict[str, str]] = None,
    total_turns: Optional[int] = None,
    notes_extra: Optional[str] = None,
) -> str:
    """Build a multi-line markdown takeaway for ``match_id``.

    Reads the decision JSONL to compute per-seat counts + most-played action.
    Falls back gracefully when the file is missing (e.g. metadata never
    initialised — happens for matches that started before this feature
    shipped).
    """
    _, decisions = read_decisions(match_id)
    counts_by_seat = count_decisions_by_seat(match_id)

    action_counter: Counter[str] = Counter()
    for d in decisions:
        at = d.get("action_type")
        if at and at != "PASS":
            action_counter[str(at)] += 1
    most_played: Optional[str] = None
    if action_counter:
        top_action, top_n = action_counter.most_common(1)[0]
        most_played = f"{top_action} ({top_n}x)"

    return _format_takeaway_lines(
        match_id=match_id,
        game_mode=game_mode,
        winner_id=winner_id,
        winner_label=(seat_labels or {}).get(winner_id) if winner_id else None,
        total_turns=total_turns,
        decisions_by_seat=counts_by_seat,
        seat_labels=seat_labels or {},
        most_played=most_played,
        notes_extra=notes_extra,
    )


def append_takeaway_to_strategy_doc(
    *,
    game_mode: str,
    body: str,
    strategy_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Append ``body`` under the ``## Session takeaways`` heading in the doc.

    Most-recent first: the new block is inserted directly after the heading,
    not at the bottom of the file. After insertion the function caps the
    number of entries at ``MAX_TAKEAWAYS_PER_DOC``, moving older ones into
    ``<mode>.archive.md``.

    Returns the path written on success, None on failure (logged, never
    raised — the supervisor must keep running).
    """
    strategy_dir = strategy_dir or Path("storage/strategy")
    doc_path = strategy_dir / f"{game_mode}.md"
    if not doc_path.exists():
        # Bootstrap a minimal doc so the takeaway has somewhere to live.
        try:
            strategy_dir.mkdir(parents=True, exist_ok=True)
            doc_path.write_text(
                f"# {game_mode.capitalize()} — Strategy Doc\n\n"
                f"{SESSION_TAKEAWAYS_ANCHOR}\n\n"
                f"<!-- Most-recent entry first; appended by the supervisor. -->\n"
            )
        except OSError as e:
            log.warning("ultra_telemetry: failed to bootstrap %s: %s", doc_path, e)
            return None

    try:
        text = doc_path.read_text()
    except OSError as e:
        log.warning("ultra_telemetry: failed to read %s: %s", doc_path, e)
        return None

    block = body if body.endswith("\n") else body + "\n"
    block = block + "\n"  # blank line between entries

    if SESSION_TAKEAWAYS_ANCHOR in text:
        # Insert right after the heading line (most-recent first).
        idx = text.index(SESSION_TAKEAWAYS_ANCHOR)
        # Find end of the heading line.
        line_end = text.find("\n", idx)
        if line_end == -1:
            line_end = len(text)
        # Skip any HTML comment immediately after the heading.
        insertion_point = line_end + 1
        # Insert with a blank line between heading and entry for readability.
        new_text = (
            text[:insertion_point]
            + "\n"
            + block
            + text[insertion_point:]
        )
    else:
        # No anchor — append at the end with the section header.
        new_text = (
            text.rstrip()
            + f"\n\n{SESSION_TAKEAWAYS_ANCHOR}\n\n"
            + block
        )

    new_text = _rotate_old_takeaways(new_text, game_mode, strategy_dir)

    try:
        doc_path.write_text(new_text)
        return doc_path
    except OSError as e:
        log.warning("ultra_telemetry: failed to write %s: %s", doc_path, e)
        return None


def _rotate_old_takeaways(doc_text: str, game_mode: str, strategy_dir: Path) -> str:
    """Move excess takeaway entries past ``MAX_TAKEAWAYS_PER_DOC`` to the archive.

    Splits on ``\\n## Session takeaway — `` (preserving the heading), keeps the
    newest N, and appends the rest to ``<mode>.archive.md``. Returns the
    trimmed doc text.
    """
    # Split into preface + blocks. Blocks are demarcated by the entry heading.
    marker = f"\n{TAKEAWAY_HEADING} —"
    if marker not in doc_text:
        return doc_text
    head, rest = doc_text.split(marker, 1)
    # Re-prefix the rest so the first block also has the marker.
    rest = marker + rest
    blocks = [b for b in rest.split(marker) if b.strip()]
    # Each ``b`` is the body after the marker — re-prepend it.
    blocks = [marker.lstrip("\n") + b for b in blocks]
    if len(blocks) <= MAX_TAKEAWAYS_PER_DOC:
        return doc_text  # no rotation needed
    keep = blocks[:MAX_TAKEAWAYS_PER_DOC]
    rotate = blocks[MAX_TAKEAWAYS_PER_DOC:]
    archive_path = strategy_dir / f"{game_mode}.archive.md"
    try:
        existing = archive_path.read_text() if archive_path.exists() else (
            f"# {game_mode.capitalize()} — Archived takeaways\n\n"
        )
        archive_path.write_text(existing + "\n" + "\n".join(rotate) + "\n")
    except OSError as e:
        log.warning("ultra_telemetry: failed to rotate to %s: %s", archive_path, e)
        return doc_text

    return head + "\n".join(keep)


# =============================================================================
# Ultra-summary aggregate (Feature 3).
# =============================================================================


def build_ultra_summary(
    *,
    replays_index_path: Optional[Path] = None,
    decisions_dir: Optional[Path] = None,
) -> dict:
    """Aggregate every archived match + decision log into a single summary.

    Walks ``storage/replays/index.json`` (the canonical match list) and
    ``storage/ultra-agent/decisions/*.jsonl`` to compute per-engine totals.
    Both sources are tolerant of missing files — a brand-new install with
    no archived matches returns ``total_matches: 0`` with an empty
    ``by_engine`` mapping.

    Returns the shape documented in the route handler.
    """
    # Resolve at call time (NOT default-arg) so monkeypatched test paths
    # take effect. Default-arg expressions are bound at module-import.
    if replays_index_path is None:
        from . import replay_archive as _ra
        replays_index_path = _ra.INDEX_PATH
    if decisions_dir is None:
        decisions_dir = DECISIONS_DIR

    index: list[dict] = []
    if replays_index_path.exists():
        try:
            with replays_index_path.open("r") as fh:
                data = json.load(fh)
                if isinstance(data, list):
                    index = data
        except (OSError, json.JSONDecodeError) as e:
            log.warning("ultra_telemetry: failed to read replays index: %s", e)

    # Counts of decisions logged per match (cheap line-count).
    decisions_per_match: dict[str, int] = {}
    decisions_by_engine: dict[str, int] = defaultdict(int)
    if decisions_dir.exists():
        for path in decisions_dir.iterdir():
            if not path.is_file() or not path.name.endswith(".jsonl"):
                continue
            match_id = path.stem
            try:
                count = 0
                with path.open("r") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        # Skip the meta header
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(obj, dict) and "_meta" not in obj:
                            count += 1
                decisions_per_match[match_id] = count
            except OSError as e:  # noqa: BLE001
                log.debug("ultra_telemetry: skipping unreadable %s: %s", path, e)

    by_engine: dict[str, dict] = {}
    earliest_ts: Optional[float] = None
    latest_ts: Optional[float] = None

    # Aggregate engine stats from the replay index (the canonical match list).
    engine_groups: dict[str, list[dict]] = defaultdict(list)
    for entry in index:
        mode = entry.get("game_mode") or "unknown"
        engine_groups[mode].append(entry)

    # Also include matches that have a decision log but no replay (rare, but
    # we want them visible — a match that crashed before any frames archived).
    indexed_match_ids = {e.get("match_id") for e in index}
    for match_id in decisions_per_match:
        if match_id not in indexed_match_ids:
            # We don't know the engine of un-archived matches; bucket as 'unknown'.
            engine_groups.setdefault("unknown", []).append({
                "match_id": match_id,
                "game_mode": "unknown",
                "total_turns": None,
                "total_frames": 0,
                "archived_at": None,
            })

    for engine, rows in engine_groups.items():
        turns = [r.get("total_turns") for r in rows if isinstance(r.get("total_turns"), int)]
        archived_with_frames = sum(1 for r in rows if (r.get("total_frames") or 0) > 1)
        total = len(rows)
        dec_count = 0
        for r in rows:
            mid = r.get("match_id")
            if mid and mid in decisions_per_match:
                dec_count += decisions_per_match[mid]
                decisions_by_engine[engine] += decisions_per_match[mid]

        by_engine[engine] = {
            "matches": total,
            "avg_turns": round(statistics.fmean(turns), 1) if turns else None,
            "median_turns": int(statistics.median(turns)) if turns else None,
            "decisions_logged": dec_count,
            "archive_completeness_pct": (
                round(100.0 * archived_with_frames / total, 1) if total else 0.0
            ),
        }

        for r in rows:
            ts = r.get("archived_at")
            if isinstance(ts, (int, float)):
                if earliest_ts is None or ts < earliest_ts:
                    earliest_ts = ts
                if latest_ts is None or ts > latest_ts:
                    latest_ts = ts

    return {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_matches": sum(stat["matches"] for stat in by_engine.values()),
        "by_engine": by_engine,
        "earliest": (
            _dt.datetime.fromtimestamp(earliest_ts, _dt.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ")
            if earliest_ts else None
        ),
        "latest": (
            _dt.datetime.fromtimestamp(latest_ts, _dt.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ")
            if latest_ts else None
        ),
    }


# =============================================================================
# Utilities exported for other modules.
# =============================================================================


def is_ultra_seat(session: Any, player_id: str) -> bool:
    """Best-effort check used by routes/match.py to gate decision logging.

    Tries ``session.is_ultra_ai_player`` (the canonical predicate); falls
    back to the AI profile dict if that's not available.
    """
    if session is None or not player_id:
        return False
    try:
        if hasattr(session, "is_ultra_ai_player"):
            return bool(session.is_ultra_ai_player(player_id))
    except Exception:  # noqa: BLE001
        pass
    profile = getattr(session, "ai_profiles_by_player", {}) or {}
    p = profile.get(player_id) or {}
    diff = p.get("difficulty") or ""
    if hasattr(diff, "value"):
        diff = diff.value
    return str(diff).strip().lower() == "ultra"
