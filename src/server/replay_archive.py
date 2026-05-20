"""Persistent replay archive for completed matches.

Match-based games (and bot_game spectator runs) carry their `replay_frames`
on the in-memory `GameSession`. Without persistence those replays disappear
the moment the container is rebuilt — so the spectator demo's matches
become unreplayable after the next deploy.

This module gzips the frames to disk on game-end and serves them back via
:func:`load_archive`. The match replay endpoint falls through to the archive
when the in-memory session is gone or already evicted.

Layout:

    storage/replays/match-<match_id>.json.gz   (compressed ReplayResponse)
    storage/replays/index.json                  (lightweight directory)

The index is the cheap source for the ``/replays`` list page; the per-match
files are read only when a viewer opens a specific replay.

Garbage collection runs from ``cleanup_old_replays`` on the same cadence as
the auto-repair artifact GC (every CLEANUP_INTERVAL_SECONDS). Default TTL
is 30 days; tunable via REPLAY_ARTIFACT_TTL_SECONDS.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

ARCHIVE_DIR = Path("storage/replays")
INDEX_PATH = ARCHIVE_DIR / "index.json"

ARTIFACT_TTL_SECONDS = int(
    os.environ.get("REPLAY_ARTIFACT_TTL_SECONDS", str(30 * 86400))
)


def archive_match(match_id: str, payload: dict[str, Any]) -> Optional[Path]:
    """Write a gzipped replay JSON to disk; update the index.

    ``payload`` should match the shape of ReplayResponse:
    ``{game_id, winner, total_turns, frames, ...}``. Returns the file path
    on success, or None on failure (logged, not raised — archiving must
    never break the game-loop).
    """
    if not match_id:
        return None
    try:
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        out_path = ARCHIVE_DIR / f"match-{match_id}.json.gz"
        body = json.dumps(payload, default=str).encode("utf-8")
        with gzip.open(out_path, "wb", compresslevel=6) as fh:
            fh.write(body)
    except Exception as e:  # noqa: BLE001
        log.warning("replay archive write failed for match=%s: %s", match_id, e)
        return None

    _update_index_entry(
        match_id=match_id,
        game_mode=payload.get("game_mode"),
        winner=payload.get("winner"),
        total_turns=payload.get("total_turns"),
        total_frames=len(payload.get("frames") or []),
        archived_at=time.time(),
    )
    log.info(
        "replay archived match=%s frames=%d bytes=%d path=%s",
        match_id, len(payload.get("frames") or []), out_path.stat().st_size, out_path,
    )
    return out_path


def load_archive(match_id: str) -> Optional[dict[str, Any]]:
    """Read a gzipped replay JSON back, returning the parsed payload."""
    if not match_id:
        return None
    path = ARCHIVE_DIR / f"match-{match_id}.json.gz"
    if not path.exists():
        return None
    try:
        with gzip.open(path, "rb") as fh:
            return json.loads(fh.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("replay archive read failed for match=%s: %s", match_id, e)
        return None


def list_archives(limit: int = 30) -> list[dict[str, Any]]:
    """Return a sorted (newest first) slice of the index for the /replays page."""
    if not INDEX_PATH.exists():
        return []
    try:
        with INDEX_PATH.open("r") as fh:
            entries = json.load(fh)
    except Exception as e:  # noqa: BLE001
        log.warning("replay index read failed: %s", e)
        return []
    if not isinstance(entries, list):
        return []
    entries.sort(key=lambda e: e.get("archived_at", 0), reverse=True)
    return entries[: max(1, min(200, limit))]


def cleanup_old_replays() -> None:
    """Prune gzipped replays + index entries past the TTL."""
    if not ARCHIVE_DIR.exists():
        return
    cutoff = time.time() - ARTIFACT_TTL_SECONDS
    pruned = 0
    for entry in ARCHIVE_DIR.iterdir():
        if not entry.is_file() or not entry.name.startswith("match-"):
            continue
        try:
            if entry.stat().st_mtime < cutoff:
                entry.unlink(missing_ok=True)
                pruned += 1
        except Exception as e:  # noqa: BLE001
            log.warning("replay GC: failed to prune %s: %s", entry, e)

    if pruned and INDEX_PATH.exists():
        try:
            with INDEX_PATH.open("r") as fh:
                entries = json.load(fh)
            if isinstance(entries, list):
                entries = [
                    e for e in entries
                    if (ARCHIVE_DIR / f"match-{e.get('match_id')}.json.gz").exists()
                ]
                with INDEX_PATH.open("w") as fh:
                    json.dump(entries, fh)
        except Exception as e:  # noqa: BLE001
            log.warning("replay index GC rewrite failed: %s", e)

    if pruned:
        log.info("replay GC: pruned %d archive(s) past TTL=%ds", pruned, ARTIFACT_TTL_SECONDS)


def _update_index_entry(
    *,
    match_id: str,
    game_mode: Optional[str],
    winner: Optional[str],
    total_turns: Optional[int],
    total_frames: int,
    archived_at: float,
) -> None:
    """Idempotent append (or replace) of a match's index row."""
    try:
        existing: list[dict[str, Any]] = []
        if INDEX_PATH.exists():
            with INDEX_PATH.open("r") as fh:
                try:
                    existing = json.load(fh) or []
                except Exception:  # noqa: BLE001
                    existing = []
                if not isinstance(existing, list):
                    existing = []
        existing = [e for e in existing if e.get("match_id") != match_id]
        existing.append({
            "match_id": match_id,
            "game_mode": game_mode,
            "winner": winner,
            "total_turns": total_turns,
            "total_frames": total_frames,
            "archived_at": archived_at,
        })
        with INDEX_PATH.open("w") as fh:
            json.dump(existing, fh)
    except Exception as e:  # noqa: BLE001
        log.warning("replay index update failed for match=%s: %s", match_id, e)
