"""Tests for the Phase 4 spectator + admin routes.

  - /api/spectate/live returns 404 when no demo is live
  - /api/spectate/status reports the supervisor's enabled state
  - /api/spectate/start + /stop honor the persisted toggle + cooldown
  - /api/admin/train refuses requests when HYPERDRAFT_ADMIN_SECRET is unset
  - /api/admin/train refuses requests with the wrong secret
  - /api/admin/train validates the ``game`` parameter
"""

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.server import spectator
from src.server.routes import admin as admin_routes
from src.server.routes import spectate as spectate_routes


@pytest.fixture(autouse=True)
def _isolate_spectator_state(tmp_path, monkeypatch):
    """Each test gets a fresh state file path so file-backed toggle state
    doesn't bleed between tests (or pollute the dev box's storage/ dir)."""
    monkeypatch.setattr(spectator, "_STATE_PATH", tmp_path / "spectator_state.json")
    spectator._current_match_id = None
    yield


# ===== /api/spectate ===========================================================

def test_spectate_live_404_when_no_match():
    """When no current_match_id is set, /api/spectate/live should raise 404."""
    spectator._current_match_id = None

    async def _run():
        from fastapi import HTTPException
        try:
            await spectate_routes.get_live_demo()
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            pytest.fail("expected 404 when no live demo")

    asyncio.run(_run())


def test_spectate_live_returns_match_id_when_set(monkeypatch):
    """When current_match_id is set, /api/spectate/live should return it."""
    monkeypatch.setattr(spectator, "_current_match_id", "demo-12345")

    async def _run():
        result = await spectate_routes.get_live_demo()
        assert result["match_id"] == "demo-12345"
        assert "spectator_enabled" in result

    asyncio.run(_run())


def test_spectate_status_reports_enabled():
    """File-backed enable: writing the state file flips status to enabled."""
    spectator._write_state({
        "enabled": True,
        "single_shot": True,
        "requested_game_mode": "mtg",
        "last_toggle_at": 0.0,
        "started_at": None,
    })
    spectator._current_match_id = None

    async def _run():
        result = await spectate_routes.get_spectator_status()
        assert result["enabled"] is True
        assert result["current_match_id"] is None

    asyncio.run(_run())


def test_spectate_status_reports_disabled():
    """No file present → off by default. Legacy env var is no longer respected."""
    async def _run():
        result = await spectate_routes.get_spectator_status()
        assert result["enabled"] is False

    asyncio.run(_run())


def test_legacy_env_var_does_not_enable(monkeypatch):
    """Regression: HYPERDRAFT_SPECTATOR_ENABLED=true must NOT auto-enable.
    The deploy that flipped this feature off must stay off after a restart."""
    monkeypatch.setenv("HYPERDRAFT_SPECTATOR_ENABLED", "true")
    assert spectator.is_enabled() is False


# ===== /api/spectate/start + /stop =============================================

def test_spectate_default_off(monkeypatch):
    """Fresh install with no env var, no state file → off by default."""
    monkeypatch.delenv("HYPERDRAFT_SPECTATOR_ENABLED", raising=False)
    assert spectator.is_enabled() is False


def test_spectate_start_persists_and_enables(monkeypatch):
    monkeypatch.delenv("HYPERDRAFT_SPECTATOR_ENABLED", raising=False)

    async def _run():
        status = await spectator.request_start(game_mode="mtg", single_shot=True)
        assert status["enabled"] is True
        assert status["game_mode"] == "mtg"
        assert status["single_shot"] is True
        # State persists across reads
        assert spectator.is_enabled() is True
        assert spectator._STATE_PATH.exists()

    asyncio.run(_run())


def test_spectate_start_rejects_unsupported_mode(monkeypatch):
    monkeypatch.delenv("HYPERDRAFT_SPECTATOR_ENABLED", raising=False)

    async def _run():
        with pytest.raises(spectator.ToggleRejected) as ei:
            await spectator.request_start(game_mode="scp")
        assert ei.value.status_code == 400

    asyncio.run(_run())


def test_spectate_start_rejects_when_already_running(monkeypatch):
    monkeypatch.delenv("HYPERDRAFT_SPECTATOR_ENABLED", raising=False)

    async def _run():
        await spectator.request_start(game_mode="mtg")
        # Even with cooldown bypassed, second Start is 409 not 429
        state = spectator._read_state()
        state["last_toggle_at"] = 0.0
        spectator._write_state(state)
        with pytest.raises(spectator.ToggleRejected) as ei:
            await spectator.request_start(game_mode="mtg")
        assert ei.value.status_code == 409

    asyncio.run(_run())


def test_spectate_start_enforces_cooldown(monkeypatch):
    monkeypatch.delenv("HYPERDRAFT_SPECTATOR_ENABLED", raising=False)

    async def _run():
        await spectator.request_start(game_mode="mtg")
        await spectator.request_stop()  # bypasses cooldown when stopping a live one
        # Now the toggle is freshly off, but last_toggle_at is recent
        with pytest.raises(spectator.ToggleRejected) as ei:
            await spectator.request_start(game_mode="mtg")
        assert ei.value.status_code == 429

    asyncio.run(_run())


def test_spectate_stop_flips_enabled(monkeypatch):
    monkeypatch.delenv("HYPERDRAFT_SPECTATOR_ENABLED", raising=False)

    async def _run():
        await spectator.request_start(game_mode="pokemon")
        assert spectator.is_enabled() is True
        await spectator.request_stop()
        assert spectator.is_enabled() is False

    asyncio.run(_run())


def test_spectate_auto_disable_after_single_shot(monkeypatch):
    """Internal helper the supervisor calls when a single-shot match ends.
    Must flip enabled OFF and skip the user-toggle cooldown."""
    monkeypatch.delenv("HYPERDRAFT_SPECTATOR_ENABLED", raising=False)

    async def _run():
        await spectator.request_start(game_mode="mtg", single_shot=True)
        spectator._auto_disable_after_single_shot()
        assert spectator.is_enabled() is False

    asyncio.run(_run())


def test_spectate_auto_disable_skips_continuous():
    """When state file sets single_shot=False, auto-disable must NOT flip
    the toggle — that's the continuous-mode escape hatch."""
    spectator._write_state({
        "enabled": True,
        "single_shot": False,
        "requested_game_mode": None,
        "last_toggle_at": 0.0,
        "started_at": None,
    })
    spectator._auto_disable_after_single_shot()
    assert spectator.is_enabled() is True


def test_auto_disable_stamps_cooldown(monkeypatch):
    """Regression: a fast-ending match used to bypass the cooldown because
    _auto_disable_after_single_shot didn't update last_toggle_at. Now it
    must — back-to-back Start spams should be rate-limited."""
    async def _run():
        await spectator.request_start(game_mode="mtg", single_shot=True)
        # Simulate the match ending instantly (e.g. spawn failure)
        spectator._auto_disable_after_single_shot()
        # Cooldown must still apply for the next Start
        with pytest.raises(spectator.ToggleRejected) as ei:
            await spectator.request_start(game_mode="mtg")
        assert ei.value.status_code == 429

    asyncio.run(_run())


# ===== /api/admin/train ========================================================

def _admin_request(headers: dict[str, str] | None = None):
    return SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers=headers or {},
    )


def test_admin_refuses_when_secret_unset(monkeypatch):
    """No HYPERDRAFT_ADMIN_SECRET → refuse ALL requests (including correct ones)."""
    monkeypatch.delenv("HYPERDRAFT_ADMIN_SECRET", raising=False)
    from fastapi import HTTPException

    async def _run():
        try:
            await admin_routes.start_training(_admin_request({"x-admin-auth": "anything"}), game="mtg", iterations=1)
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            pytest.fail("expected 404 when secret unset")

    asyncio.run(_run())


def test_admin_refuses_wrong_secret(monkeypatch):
    monkeypatch.setenv("HYPERDRAFT_ADMIN_SECRET", "the-real-secret")
    from fastapi import HTTPException

    async def _run():
        try:
            await admin_routes.start_training(_admin_request({"x-admin-auth": "wrong"}), game="mtg", iterations=1)
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            pytest.fail("expected 404 with wrong secret")

    asyncio.run(_run())


def test_admin_refuses_invalid_game(monkeypatch):
    monkeypatch.setenv("HYPERDRAFT_ADMIN_SECRET", "the-real-secret")
    from fastapi import HTTPException

    async def _run():
        try:
            await admin_routes.start_training(
                _admin_request({"x-admin-auth": "the-real-secret"}),
                game="not-a-game",
                iterations=1,
            )
        except HTTPException as exc:
            assert exc.status_code == 400
            assert "Unknown game" in exc.detail
        else:
            pytest.fail("expected 400 for invalid game")

    asyncio.run(_run())


def test_admin_refuses_invalid_iterations(monkeypatch):
    monkeypatch.setenv("HYPERDRAFT_ADMIN_SECRET", "the-real-secret")
    from fastapi import HTTPException

    async def _run():
        for bad in (0, 51, -1, 100):
            try:
                await admin_routes.start_training(
                    _admin_request({"x-admin-auth": "the-real-secret"}),
                    game="mtg",
                    iterations=bad,
                )
            except HTTPException as exc:
                assert exc.status_code == 400
            else:
                pytest.fail(f"expected 400 for iterations={bad}")

    asyncio.run(_run())


def test_admin_status_404_for_unknown_run(monkeypatch):
    monkeypatch.setenv("HYPERDRAFT_ADMIN_SECRET", "the-real-secret")
    from fastapi import HTTPException

    async def _run():
        try:
            await admin_routes.get_training_status(
                "no-such-run-id-12345",
                _admin_request({"x-admin-auth": "the-real-secret"}),
            )
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            pytest.fail("expected 404 for unknown run")

    asyncio.run(_run())
