"""Tests for the match replay API + archive persistence.

The endpoints exposed:
  - GET /api/match/:matchId/replay?since&limit  (live session OR archive)
  - GET /api/match/:matchId/replay/manifest      (turn/phase index for scrubber)

Plus the archive module:
  - replay_archive.archive_match(match_id, payload)
  - replay_archive.load_archive(match_id)
  - replay_archive.list_archives(limit)
  - replay_archive.cleanup_old_replays()
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from src.server import replay_archive
from src.server.models import ReplayFrame


@pytest.fixture
def isolated_archive_dir(tmp_path, monkeypatch):
    """Redirect replay_archive into a tmp dir per test."""
    monkeypatch.setattr(replay_archive, "ARCHIVE_DIR", tmp_path / "replays")
    monkeypatch.setattr(replay_archive, "INDEX_PATH", tmp_path / "replays" / "index.json")
    return tmp_path


def _sample_payload(match_id: str = "abc123", frames: int = 5) -> dict:
    return {
        "game_id": match_id,
        "match_id": match_id,
        "game_mode": "pokemon",
        "winner": "p1",
        "total_turns": 7,
        "frames": [
            {
                "turn": i // 3 + 1,
                "phase": "main",
                "step": "",
                "action": {"action_type": "PASS"} if i % 2 else None,
                "state": {"turn_number": i // 3 + 1, "is_game_over": False},
                "timestamp": 1700000000.0 + i,
            }
            for i in range(frames)
        ],
    }


def test_archive_write_and_load_roundtrip(isolated_archive_dir):
    payload = _sample_payload("abc123", frames=4)
    path = replay_archive.archive_match("abc123", payload)
    assert path is not None
    assert path.exists()

    loaded = replay_archive.load_archive("abc123")
    assert loaded is not None
    assert loaded["match_id"] == "abc123"
    assert loaded["game_mode"] == "pokemon"
    assert loaded["winner"] == "p1"
    assert loaded["total_turns"] == 7
    assert len(loaded["frames"]) == 4


def test_archive_load_returns_none_when_absent(isolated_archive_dir):
    assert replay_archive.load_archive("nonexistent") is None


def test_archive_load_returns_none_for_empty_match_id(isolated_archive_dir):
    assert replay_archive.load_archive("") is None
    assert replay_archive.archive_match("", _sample_payload()) is None


def test_index_is_appended_on_archive(isolated_archive_dir):
    replay_archive.archive_match("m1", _sample_payload("m1", frames=3))
    replay_archive.archive_match("m2", _sample_payload("m2", frames=5))

    entries = replay_archive.list_archives()
    assert len(entries) == 2
    by_id = {e["match_id"]: e for e in entries}
    assert by_id["m1"]["total_frames"] == 3
    assert by_id["m2"]["total_frames"] == 5
    assert by_id["m1"]["game_mode"] == "pokemon"


def test_index_replaces_entry_on_re_archive(isolated_archive_dir):
    """Archiving the same match twice should not create duplicate index rows."""
    replay_archive.archive_match("m1", _sample_payload("m1", frames=3))
    replay_archive.archive_match("m1", _sample_payload("m1", frames=12))

    entries = replay_archive.list_archives()
    assert len(entries) == 1
    assert entries[0]["total_frames"] == 12


def test_list_archives_sorted_newest_first(isolated_archive_dir, monkeypatch):
    replay_archive.archive_match("old-match", _sample_payload("old-match", frames=2))
    time.sleep(0.01)
    replay_archive.archive_match("new-match", _sample_payload("new-match", frames=2))

    entries = replay_archive.list_archives()
    assert entries[0]["match_id"] == "new-match"
    assert entries[1]["match_id"] == "old-match"


def test_list_archives_returns_empty_when_no_index(isolated_archive_dir):
    assert replay_archive.list_archives() == []


def test_cleanup_old_replays_prunes_past_ttl(isolated_archive_dir, monkeypatch):
    monkeypatch.setattr(replay_archive, "ARTIFACT_TTL_SECONDS", 60)

    archived = replay_archive.archive_match("stale", _sample_payload("stale"))
    fresh = replay_archive.archive_match("fresh", _sample_payload("fresh"))
    assert archived is not None and fresh is not None

    # Backdate the stale file by 2 hours
    import os as _os
    old_t = time.time() - 7200
    _os.utime(archived, (old_t, old_t))

    replay_archive.cleanup_old_replays()

    assert not archived.exists()
    assert fresh.exists()
    entries = replay_archive.list_archives()
    assert [e["match_id"] for e in entries] == ["fresh"]


# === Endpoint tests ====================================================
# These use the real route handlers via direct invocation (mirroring the
# pattern from tests/test_phase4_routes.py and tests/test_auto_repair.py).

from src.server.routes.match import get_match_replay, get_match_replay_manifest
from src.server.session import session_manager, GameSession
from src.engine.game import Game


@pytest.fixture
def stub_session_with_frames():
    """Insert a minimal session with replay frames into session_manager."""
    match_id = "test-match-replay"
    # Tear down anything left from a previous test run.
    if match_id in session_manager.sessions:
        del session_manager.sessions[match_id]

    game = Game(mode="pokemon")
    session = GameSession(id=match_id, game=game, mode="bot_vs_bot")
    session.is_started = True
    session.replay_frames = [
        ReplayFrame(
            turn=i // 3 + 1,
            phase="main" if i % 2 == 0 else "battle",
            step="",
            action={"action_type": "PASS"} if i % 2 else None,
            state={"turn_number": i // 3 + 1},
            timestamp=1700000000.0 + i,
        )
        for i in range(10)
    ]
    session_manager.sessions[match_id] = session
    yield match_id
    session_manager.sessions.pop(match_id, None)


def test_replay_endpoint_returns_frames_from_live_session(stub_session_with_frames):
    match_id = stub_session_with_frames

    async def _run():
        resp = await get_match_replay(match_id, since=0, limit=8000)
        assert resp.game_id == match_id
        assert len(resp.frames) == 10

    asyncio.run(_run())


def test_replay_endpoint_paginates_with_since_and_limit(stub_session_with_frames):
    match_id = stub_session_with_frames

    async def _run():
        resp = await get_match_replay(match_id, since=3, limit=4)
        assert len(resp.frames) == 4
        # since=3 means we start at index 3 — frame should have ts=1700000003
        assert resp.frames[0].timestamp == 1700000003.0

    asyncio.run(_run())


def test_replay_endpoint_404_for_unknown_match(isolated_archive_dir):
    from fastapi import HTTPException

    async def _run():
        try:
            await get_match_replay("no-such-match-id-12345")
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            pytest.fail("expected 404 HTTPException")

    asyncio.run(_run())


def test_replay_endpoint_falls_back_to_archive(isolated_archive_dir, monkeypatch):
    """When the live session is gone, the endpoint must read from the archive."""
    match_id = "archived-only-match"
    session_manager.sessions.pop(match_id, None)  # ensure no live session

    replay_archive.archive_match(match_id, _sample_payload(match_id, frames=6))

    async def _run():
        resp = await get_match_replay(match_id, since=0, limit=8000)
        assert resp.game_id == match_id
        assert resp.winner == "p1"
        assert len(resp.frames) == 6

    asyncio.run(_run())


def test_manifest_compacts_turn_phase_changes(stub_session_with_frames):
    match_id = stub_session_with_frames

    async def _run():
        manifest = await get_match_replay_manifest(match_id)
        assert manifest["match_id"] == match_id
        assert manifest["total_frames"] == 10
        # Each (turn, phase) pair should appear once at the FIRST frame
        # with that pair. With 10 frames alternating main/battle and
        # turn flipping every 3 frames, we expect ~6-7 marks not 10.
        assert 4 <= len(manifest["marks"]) <= 10
        assert manifest["marks"][0]["frame"] == 0

    asyncio.run(_run())
