"""Tests for the Phase 4 spectator + admin routes.

  - /api/spectate/live returns 404 when no demo is live
  - /api/spectate/status reports the supervisor's enabled state
  - /api/admin/train refuses requests when HYPERDRAFT_ADMIN_SECRET is unset
  - /api/admin/train refuses requests with the wrong secret
  - /api/admin/train validates the ``game`` parameter
"""

import asyncio
import os
from types import SimpleNamespace

import pytest

from src.server import spectator
from src.server.routes import admin as admin_routes
from src.server.routes import spectate as spectate_routes


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


def test_spectate_status_reports_enabled(monkeypatch):
    monkeypatch.setenv("HYPERDRAFT_SPECTATOR_ENABLED", "true")
    monkeypatch.setattr(spectator, "_current_match_id", None)

    async def _run():
        result = await spectate_routes.get_spectator_status()
        assert result["enabled"] is True
        assert result["current_match_id"] is None

    asyncio.run(_run())


def test_spectate_status_reports_disabled(monkeypatch):
    monkeypatch.delenv("HYPERDRAFT_SPECTATOR_ENABLED", raising=False)

    async def _run():
        result = await spectate_routes.get_spectator_status()
        assert result["enabled"] is False

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
