"""Unit tests for src/server/auto_repair.py and the session.py trigger hooks.

The orchestrator's network of asyncio tasks + claude subprocess + git diff
is hard to test end-to-end without a real container; these tests cover:

  - is_enabled() reading REPAIR_ENABLED correctly
  - capture_and_kick respecting the kill switch
  - capture_and_kick writing context.json + state_snapshot.json
  - per-match dedup in _kick
  - _verify_fix returning failure when repro test is missing
  - session.handle_action timeout trigger (no real claude subprocess)
  - session.handle_action exception trigger (no real claude subprocess)
  - cleanup_old_artifacts honoring active sessions and TTL

End-to-end verification (real claude subprocess, real git diff, real pytest
verifier) requires the production container and GitHub PAT, and is
exercised in Phase 4.5 deploy verification.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import pytest

from src.server import auto_repair


@pytest.fixture(autouse=True)
def _isolate_repair_state(tmp_path, monkeypatch):
    """Reset module globals + redirect REPAIR_ROOT to a per-test tmp dir."""
    monkeypatch.setattr(auto_repair, "REPAIR_ROOT", tmp_path / "repair")
    auto_repair._active.clear()
    yield
    auto_repair._active.clear()


def test_is_enabled_default_off(monkeypatch):
    monkeypatch.delenv("REPAIR_ENABLED", raising=False)
    assert auto_repair.is_enabled() is False


def test_is_enabled_truthy(monkeypatch):
    for val in ("true", "TRUE", "1", "yes"):
        monkeypatch.setenv("REPAIR_ENABLED", val)
        assert auto_repair.is_enabled() is True


def test_is_enabled_falsy(monkeypatch):
    for val in ("false", "0", "no", ""):
        monkeypatch.setenv("REPAIR_ENABLED", val)
        assert auto_repair.is_enabled() is False


def test_capture_and_kick_skipped_when_disabled(monkeypatch):
    monkeypatch.setenv("REPAIR_ENABLED", "false")

    async def _run():
        result = await auto_repair.capture_and_kick(
            "match-disabled",
            game_mode="mtg",
            traceback_text="RuntimeError: test",
        )
        assert result is False
        # No context written
        assert not (auto_repair.REPAIR_ROOT / "match-disabled").exists()

    asyncio.run(_run())


def test_capture_and_kick_writes_context_and_snapshot(monkeypatch):
    """When enabled, writes context.json and state_snapshot.json. We monkey-patch
    _kick so we don't actually try to spawn claude (no CLI in this test env)."""
    monkeypatch.setenv("REPAIR_ENABLED", "true")
    monkeypatch.setattr(auto_repair, "_kick", _fake_kick_true)

    async def _run():
        result = await auto_repair.capture_and_kick(
            "match-abc",
            game_mode="pokemon",
            traceback_text="ValueError: bad card",
            game_state_snapshot={"turn_number": 3, "active_player": "p1"},
            trigger="exception",
            extra_context={"action_type": "POKEMON_ATTACK"},
        )
        assert result is True

        out = auto_repair.REPAIR_ROOT / "match-abc"
        ctx = json.loads((out / "context.json").read_text())
        assert ctx["match_id"] == "match-abc"
        assert ctx["game_mode"] == "pokemon"
        assert ctx["trigger"] == "exception"
        assert ctx["action_type"] == "POKEMON_ATTACK"
        assert "ValueError" in ctx["traceback"]

        snap = json.loads((out / "state_snapshot.json").read_text())
        assert snap["turn_number"] == 3
        assert snap["active_player"] == "p1"

    asyncio.run(_run())


async def _fake_kick_true(*_a, **_kw) -> bool:
    return True


async def _fake_kick_false(*_a, **_kw) -> bool:
    return False


def test_kick_dedup_per_match(monkeypatch):
    """A second kick for the same match should fold in and return False."""
    monkeypatch.setenv("REPAIR_ENABLED", "true")

    # Block _run_first_turn from actually spawning claude.
    async def _fake_first_turn(_match, _mode):
        return

    monkeypatch.setattr(auto_repair, "_run_first_turn", _fake_first_turn)

    async def _run():
        first = await auto_repair._kick("match-dup", "mtg")
        second = await auto_repair._kick("match-dup", "mtg")
        assert first is True
        assert second is False
        # Let any spawned tasks finish so the test doesn't leak warnings.
        await asyncio.sleep(0)

    asyncio.run(_run())


def test_verify_fix_missing_repro_test(monkeypatch, tmp_path):
    """_verify_fix should return (False, ...) when tests/auto_repair/<match>.py is missing."""
    monkeypatch.chdir(tmp_path)  # repro_test path is relative

    async def _run():
        passed, reason = await auto_repair._verify_fix("nonexistent-match-id")
        assert passed is False
        assert reason is not None
        assert "no repro test" in reason

    asyncio.run(_run())


def test_verify_fix_runs_pytest_when_test_exists(monkeypatch, tmp_path):
    """_verify_fix should run pytest and propagate its return code."""
    monkeypatch.chdir(tmp_path)
    test_dir = tmp_path / "tests" / "auto_repair"
    test_dir.mkdir(parents=True)
    test_file = test_dir / "match-verify.py"

    # Always-passing test
    test_file.write_text("def test_ok():\n    assert True\n")

    async def _run():
        passed, reason = await auto_repair._verify_fix("match-verify")
        assert passed is True
        assert reason is None

        # Now overwrite with a failing test
        test_file.write_text("def test_fail():\n    assert False\n")
        passed, reason = await auto_repair._verify_fix("match-verify")
        assert passed is False
        assert reason is not None
        assert "pytest exited" in reason

    asyncio.run(_run())


def test_cleanup_old_artifacts_keeps_active_and_prunes_old(monkeypatch):
    """Active sessions are kept; old (mtime < cutoff) ones are pruned."""
    monkeypatch.setattr(auto_repair, "ARTIFACT_TTL_SECONDS", 60)
    repair_root = auto_repair.REPAIR_ROOT
    repair_root.mkdir(parents=True, exist_ok=True)

    old_dir = repair_root / "old-match"
    old_dir.mkdir()
    (old_dir / "context.json").write_text("{}")
    # Make it 2 hours old
    old_mtime = time.time() - 7200
    os.utime(old_dir, (old_mtime, old_mtime))

    active_dir = repair_root / "active-match"
    active_dir.mkdir()
    auto_repair._active["active-match"] = {"started_at": time.time()}

    fresh_dir = repair_root / "fresh-match"
    fresh_dir.mkdir()

    auto_repair.cleanup_old_artifacts()

    assert not old_dir.exists(), "old artifact should have been pruned"
    assert active_dir.exists(), "active session must not be pruned"
    assert fresh_dir.exists(), "within-TTL artifact must not be pruned"


# === session.py trigger hooks ===============================================
#
# We construct a tiny GameSession-shaped object (not the real one — building a
# full game is overkill for testing the wrappers) and exercise the try/except
# logic. The real handle_action body is monkey-patched to raise / sleep.


class _StubGame:
    class _State:
        game_mode = "mtg"
        players = {"p1": object()}
    state = _State()

    class _TurnManager:
        turn_number = 5
    turn_manager = _TurnManager()

    def get_active_player(self):
        return "p1"

    def is_game_over(self):
        return False


class _StubSession:
    """Mirror the minimum surface of GameSession that the wrappers touch."""
    id = "stub-match"
    is_finished = False
    game = _StubGame()

    def __init__(self):
        self._kicks: list[dict] = []

    @staticmethod
    def _action_timeout_seconds() -> int:
        from src.server.session import GameSession
        return GameSession._action_timeout_seconds()

    async def _maybe_kick_auto_repair(self, *, trigger, traceback_text, extra_context=None):
        self._kicks.append({
            "trigger": trigger,
            "traceback_text": traceback_text,
            "extra_context": extra_context,
        })

    def _auto_repair_state_snapshot(self):
        from src.server.session import GameSession
        return GameSession._auto_repair_state_snapshot(self)


def _bind(method):
    """Bind a real GameSession method to a stub instance for testing."""
    from src.server.session import GameSession
    real = getattr(GameSession, method)
    return real


def _call_handle_action(sess, request):
    """Invoke the real GameSession.handle_action wrapper with a stub `self`."""
    from src.server.session import GameSession
    return GameSession.handle_action(sess, request)


def _call_get_ai_action(sess, player_id, state, legal_actions):
    """Invoke the real GameSession._get_ai_action wrapper with a stub `self`."""
    from src.server.session import GameSession
    return GameSession._get_ai_action(sess, player_id, state, legal_actions)


def test_handle_action_timeout_kicks(monkeypatch):
    """A body that sleeps past the timeout should fire a turn_timeout kick."""
    from src.server.models import PlayerActionRequest

    monkeypatch.setenv("ACTION_TIMEOUT_SECONDS", "1")

    sess = _StubSession()
    sess.is_finished = False

    async def _slow_body(_request):
        await asyncio.sleep(5)
        return True, "should never reach"

    sess._handle_action_body = _slow_body  # attach as instance attribute

    async def _run():
        ok, msg = await _call_handle_action(
            sess,
            PlayerActionRequest(action_type="PASS", player_id="p1"),
        )
        assert ok is False
        assert "timed out" in msg
        assert len(sess._kicks) == 1
        assert sess._kicks[0]["trigger"] == "turn_timeout"

    asyncio.run(_run())


def test_handle_action_exception_kicks_and_reraises(monkeypatch):
    """An uncaught exception in the body should fire an exception kick and re-raise."""
    from src.server.models import PlayerActionRequest

    sess = _StubSession()

    async def _raise_body(_request):
        raise RuntimeError("synthetic crash for test")

    sess._handle_action_body = _raise_body

    async def _run():
        with pytest.raises(RuntimeError, match="synthetic crash"):
            await _call_handle_action(
                sess,
                PlayerActionRequest(action_type="PASS", player_id="p1"),
            )
        assert len(sess._kicks) == 1
        assert sess._kicks[0]["trigger"] == "exception"
        assert "synthetic crash" in sess._kicks[0]["traceback_text"]

    asyncio.run(_run())


def test_get_ai_action_none_return_kicks_without_raising(monkeypatch):
    """If the inner returns None, fire ai_none_returned but DON'T raise."""
    sess = _StubSession()

    async def _none_body(_player_id, _state, _legal_actions):
        return None

    sess._get_ai_action_body = _none_body

    async def _run():
        result = await _call_get_ai_action(sess, "p1", None, [])
        assert result is None
        assert len(sess._kicks) == 1
        assert sess._kicks[0]["trigger"] == "ai_none_returned"

    asyncio.run(_run())


def test_get_ai_action_exception_kicks_and_reraises(monkeypatch):
    """An uncaught exception in the AI inner should kick and re-raise."""
    sess = _StubSession()

    async def _raise_body(_player_id, _state, _legal_actions):
        raise ValueError("ai blew up")

    sess._get_ai_action_body = _raise_body

    async def _run():
        with pytest.raises(ValueError, match="ai blew up"):
            await _call_get_ai_action(sess, "p1", None, [])
        assert len(sess._kicks) == 1
        assert sess._kicks[0]["trigger"] == "exception"

    asyncio.run(_run())


def test_state_snapshot_is_defensive():
    """The snapshot must never raise — even if game state is weird."""
    from src.server.session import GameSession

    class _BrokenGame:
        @property
        def state(self):
            raise RuntimeError("nope")

    class _Sess:
        id = "broken"
        game = _BrokenGame()

    snap = GameSession._auto_repair_state_snapshot(_Sess())
    assert isinstance(snap, dict)


def test_action_timeout_seconds_env_override(monkeypatch):
    from src.server.session import GameSession

    monkeypatch.setenv("ACTION_TIMEOUT_SECONDS", "5")
    assert GameSession._action_timeout_seconds() == 5

    monkeypatch.setenv("ACTION_TIMEOUT_SECONDS", "garbage")
    assert GameSession._action_timeout_seconds() == 30  # falls back

    monkeypatch.delenv("ACTION_TIMEOUT_SECONDS", raising=False)
    assert GameSession._action_timeout_seconds() == 30
