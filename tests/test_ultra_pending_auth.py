"""Tests for the localhost / shared-secret gate on /api/match/ultra-pending.

Added in Phase 2.4 of the Hosted Claude Code rollout. The endpoint used to
leak active match + player IDs publicly; container-internal callers reach
it via 127.0.0.1, so we localhost-gate by default and accept the
X-Internal-Auth header as a backdoor when HYPERDRAFT_INTERNAL_SECRET is set.
"""

import asyncio
from types import SimpleNamespace

import pytest

from src.server.routes import match as match_routes


def _make_request(client_host: str, headers: dict[str, str] | None = None):
    """Build a minimal stand-in for fastapi.Request — only client.host and headers are read."""
    return SimpleNamespace(
        client=SimpleNamespace(host=client_host),
        headers=headers or {},
    )


def test_localhost_request_is_internal():
    assert match_routes._is_internal_request(_make_request("127.0.0.1")) is True
    assert match_routes._is_internal_request(_make_request("::1")) is True
    assert match_routes._is_internal_request(_make_request("localhost")) is True


def test_non_localhost_without_secret_is_external(monkeypatch):
    monkeypatch.delenv("HYPERDRAFT_INTERNAL_SECRET", raising=False)
    assert match_routes._is_internal_request(_make_request("10.0.0.5")) is False
    assert match_routes._is_internal_request(_make_request("172.18.0.3")) is False


def test_non_localhost_with_matching_secret_is_internal(monkeypatch):
    monkeypatch.setenv("HYPERDRAFT_INTERNAL_SECRET", "shared-secret-abc")
    req = _make_request("10.0.0.5", {"x-internal-auth": "shared-secret-abc"})
    assert match_routes._is_internal_request(req) is True


def test_non_localhost_with_wrong_secret_is_external(monkeypatch):
    monkeypatch.setenv("HYPERDRAFT_INTERNAL_SECRET", "shared-secret-abc")
    req = _make_request("10.0.0.5", {"x-internal-auth": "wrong"})
    assert match_routes._is_internal_request(req) is False


def test_non_localhost_without_header_when_secret_set_is_external(monkeypatch):
    monkeypatch.setenv("HYPERDRAFT_INTERNAL_SECRET", "shared-secret-abc")
    req = _make_request("10.0.0.5")
    assert match_routes._is_internal_request(req) is False


def test_endpoint_returns_404_for_external_request(monkeypatch):
    """list_ultra_pending should raise HTTPException(404) instead of leaking data."""
    monkeypatch.delenv("HYPERDRAFT_INTERNAL_SECRET", raising=False)
    from fastapi import HTTPException

    async def _run():
        req = _make_request("203.0.113.10")  # documentation IP, never localhost
        try:
            await match_routes.list_ultra_pending(req)
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            pytest.fail("expected HTTPException(404)")

    asyncio.run(_run())


def test_endpoint_serves_localhost_request(monkeypatch):
    """list_ultra_pending should return the pending dict when called from localhost."""
    monkeypatch.delenv("HYPERDRAFT_INTERNAL_SECRET", raising=False)

    async def _run():
        req = _make_request("127.0.0.1")
        result = await match_routes.list_ultra_pending(req)
        assert isinstance(result, dict)
        assert "pending" in result

    asyncio.run(_run())
