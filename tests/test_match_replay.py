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


# === Pokemon ultra-AI frame-capture regression tests ====================
# Bug history: four spectator-demo Pokemon ultra matches each ran 92-96
# turns but archived only the single turn-0 start_game frame (e.g. replay
# 4f9142e0 — 94 turns, 1 frame). Root cause: when the LLM subprocess
# died early (auth failure, watchdog idle-kill) the engine's
# human_action_handler kept timing out and returning PKM_END_TURN
# directly, bypassing pkm.handle_action — the only path that called
# session._record_frame for Pokemon /match/ ultra matches. The fix is in
# PokemonModeAdapter.run_game_loop: emit a per-turn replay frame even
# when nobody acts. Bug B fix: track consecutive timeouts on the session
# and mark it finished after a small threshold so the game-loop exits
# cleanly instead of churning for hours after the LLM is dead.

from src.cards.pokemon.sv_starter import make_fire_deck, make_water_deck
from src.server.modes.pkm import PokemonModeAdapter


@pytest.fixture
def pokemon_bot_vs_bot_session():
    """Build a real Pokemon bot_vs_bot session with two LLM/ultra-style seats.

    Uses the engine's setup_pokemon_player (matches what bot_game / match
    do in production) so the run_game_loop and turn manager paths are
    exercised end-to-end. The session is *not* started; tests drive it
    manually so they can stub out human_action_handler without waiting on
    the 300 s production timeout.
    """
    match_id = "test-pkm-replay-loop"
    session_manager.sessions.pop(match_id, None)

    game = Game(mode="pokemon")
    p1 = game.add_player("Claude Ultra A")
    p2 = game.add_player("Claude Ultra B")
    game.set_ai_player(p1.id)
    game.set_ai_player(p2.id)
    game.setup_pokemon_player(p1, [])
    game.setup_pokemon_player(p2, [])

    session = GameSession(id=match_id, game=game, mode="bot_vs_bot")
    session.player_ids = [p1.id, p2.id]
    session.player_names = {p1.id: "Claude Ultra A", p2.id: "Claude Ultra B"}
    session.record_actions_for_replay = True
    session.max_replay_frames = 8000
    # Mirror production: both seats are externally-driven LLM ultras.
    session.ai_profiles_by_player = {
        p1.id: {"brain": "external", "difficulty": "ultra", "agent_runner": "claude"},
        p2.id: {"brain": "external", "difficulty": "ultra", "agent_runner": "claude"},
    }

    # Seed each library with a real starter deck so setup_game doesn't
    # immediately stall on mulligan.
    for pid, deck_fn in ((p1.id, make_fire_deck), (p2.id, make_water_deck)):
        for card_def in deck_fn():
            game.create_object(
                name=card_def.name,
                owner_id=pid,
                zone=getattr(__import__("src.engine.types", fromlist=["ZoneType"]), "ZoneType").LIBRARY,
                characteristics=__import__("copy").deepcopy(card_def.characteristics),
                card_def=card_def,
            )

    session_manager.sessions[match_id] = session
    yield session
    session_manager.sessions.pop(match_id, None)


def test_pokemon_run_game_loop_records_frame_per_turn_when_no_actions_submitted(
    pokemon_bot_vs_bot_session,
):
    """Regression: 4 broken replays archived ``total_turns=94`` but only the
    single ``action=None`` start_game frame. Each completed Pokemon turn
    must record at least one replay frame so the archived match can be
    scrubbed.

    This drives the real ``PokemonModeAdapter.run_game_loop`` (not a hand-
    rolled copy of its body) so deleting the per-turn ``_record_frame``
    call in pkm.py would fail the assertion.
    """
    session = pokemon_bot_vs_bot_session
    adapter = PokemonModeAdapter()

    async def _run():
        # Set up the game (shuffle/draw/place basics/coin flip) and record
        # the initial frame the same way ``GameSession.start_game`` does.
        await adapter.setup_game(session)
        session.is_started = True
        session._record_frame(action=None)
        frames_after_setup = len(session.replay_frames)

        # Stub asyncio.wait_for so the production 300 s timeout in
        # get_human_action fires immediately. The dead-LLM short-circuit
        # (Bug B fix) will flip session.is_finished after a small number
        # of consecutive timeouts, which lets run_game_loop exit cleanly
        # — without that, this test would hang forever.
        import asyncio as aio
        real_wait_for = aio.wait_for

        async def _instant_timeout(_aw, timeout):
            if hasattr(_aw, "cancel"):
                _aw.cancel()
            raise aio.TimeoutError()

        aio.wait_for = _instant_timeout
        try:
            await adapter.run_game_loop(session)
        finally:
            aio.wait_for = real_wait_for

        # Each completed run_turn must produce at least one replay frame
        # via the safety-net branch in run_game_loop. Without the fix this
        # was zero. The exact frame count depends on how many turns ran
        # before the dead-LLM threshold flipped is_finished, but it MUST
        # exceed the initial setup frame.
        frames_after_loop = len(session.replay_frames)
        new_frames = frames_after_loop - frames_after_setup
        assert new_frames >= 1, (
            f"Expected >= 1 turn-complete frame from run_game_loop with a "
            f"silent LLM, got {new_frames}. Per-turn frame capture in "
            "pkm.run_game_loop is the safety net for matches where the "
            "LLM subprocess has died and handle_action is never invoked."
        )
        # And the new frames must carry the turn-complete marker so the
        # frontend scrubber + archive viewer can identify them.
        marker_frames = [
            f for f in session.replay_frames[frames_after_setup:]
            if (f.action or {}).get("kind") == "turn_complete"
        ]
        assert marker_frames, (
            "Per-turn safety-net frames must carry "
            "action.kind == 'turn_complete' so they're distinguishable "
            "from action-driven frames in the replay viewer."
        )

    asyncio.run(_run())


def test_pokemon_get_human_action_marks_match_finished_after_consecutive_timeouts(
    pokemon_bot_vs_bot_session,
):
    """Regression for Bug B: when the ultra subprocess is dead the match
    used to churn for ~7 h (300 s × 90 turns) before a deckout finally
    finished it. Trigger three consecutive timeouts and assert the
    session flips ``is_finished`` so run_game_loop exits promptly.
    """
    session = pokemon_bot_vs_bot_session
    adapter = PokemonModeAdapter()

    async def _run():
        # Provide minimal infra so get_human_action's body runs without
        # waiting on the real 300 s deadline. We patch wait_for to raise
        # immediately so the timeout branch fires per call.
        import asyncio as aio
        real_wait_for = aio.wait_for

        async def _instant_timeout(_aw, timeout):
            # Cancel the underlying future so it doesn't leak.
            if hasattr(_aw, "cancel"):
                _aw.cancel()
            raise aio.TimeoutError()

        aio.wait_for = _instant_timeout
        try:
            p1 = session.player_ids[0]
            # First two timeouts should NOT flip is_finished — leaves
            # headroom for a one-off slow LLM call without ending the
            # whole match prematurely.
            for _ in range(2):
                action = await adapter.get_human_action(session, p1, session.game.state)
                assert action == {"action_type": "PKM_END_TURN"}
            assert not session.is_finished

            # Third timeout (configurable threshold = 3) trips the
            # dead-LLM short-circuit so run_game_loop can exit.
            await adapter.get_human_action(session, p1, session.game.state)
            assert session.is_finished, (
                "After 3 consecutive human_action_handler timeouts the "
                "session must be marked finished so the match doesn't "
                "churn for hours past the operator wall-time cap."
            )
        finally:
            aio.wait_for = real_wait_for

    asyncio.run(_run())


def test_pokemon_get_human_action_resets_streak_when_action_arrives(
    pokemon_bot_vs_bot_session,
):
    """The dead-LLM short-circuit must NOT trigger when the LLM is alive
    and acting between timeouts — only when the seat goes silent for a
    sustained streak.
    """
    session = pokemon_bot_vs_bot_session
    adapter = PokemonModeAdapter()

    async def _run():
        import asyncio as aio
        real_wait_for = aio.wait_for

        # Flip-flop: timeout, then a real action, then timeout, then a real
        # action. Counter should reset after each successful action so we
        # never reach the threshold.
        calls = {"n": 0}

        async def _alternating_wait_for(_aw, timeout):
            calls["n"] += 1
            if hasattr(_aw, "cancel"):
                _aw.cancel()
            if calls["n"] % 2 == 1:
                raise aio.TimeoutError()
            return {"action_type": "PKM_ATTACK", "attack_index": 0}

        aio.wait_for = _alternating_wait_for
        try:
            p1 = session.player_ids[0]
            # Run 6 alternating cycles (3 timeouts, 3 acts). Without the
            # reset on success, this would trip the threshold; with the
            # reset, is_finished stays False.
            for _ in range(6):
                await adapter.get_human_action(session, p1, session.game.state)
            assert not session.is_finished, (
                "Action-arrival branch must reset _pkm_consecutive_timeouts "
                "so a few intermittent LLM hiccups don't kill an otherwise "
                "active match."
            )
        finally:
            aio.wait_for = real_wait_for

    asyncio.run(_run())
