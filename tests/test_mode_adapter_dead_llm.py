"""Regression tests for the dead-LLM short-circuit + per-turn replay frame
across every non-MTG mode adapter.

The Pokemon fix (commit 9995e472) added two guards to ``pkm.py``:
  1. After each ``run_turn()`` the adapter records a replay frame so the
     archive captures progression even when no action POST comes in.
  2. After 3 consecutive ``get_human_action`` timeouts the session is
     flagged ``is_finished=True`` so the engine doesn't churn for hours
     past the spectator wall-time cap.

Every non-MTG mode adapter (YGO, HS, MC, Finance, SCP, Depths) has the
same shape and the same latent bug. These tests confirm the guards are
wired uniformly. MTG uses the priority pipeline and is exempt; Cats had
the per-turn frame from day one and uses a non-future action path.

The tests use a minimal ``StubSession`` instead of constructing full
real engines per adapter — each adapter touches the same surface
(``session.record_actions_for_replay``, ``_record_frame``, the streak
attribute, ``is_finished``, ``_pending_action_future``).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import pytest

from src.server.modes.hs import HearthstoneModeAdapter
from src.server.modes.ygo import YugiohModeAdapter
from src.server.modes.mc import MinecraftModeAdapter
from src.server.modes.finance import FinanceModeAdapter
from src.server.modes.scp import SCPModeAdapter
from src.server.modes.depths_mode import DepthsModeAdapter


@dataclass
class _StubTurnManager:
    turn_number: int = 1
    run_turn: Optional[Callable] = None


@dataclass
class _StubGame:
    turn_manager: _StubTurnManager = field(default_factory=_StubTurnManager)
    _game_over: bool = False
    _active: str = "p1"
    _winner: Optional[str] = None
    _state: Any = None

    def is_game_over(self) -> bool:
        return self._game_over

    def get_active_player(self) -> str:
        return self._active

    def get_winner(self) -> Optional[str]:
        return self._winner

    @property
    def state(self) -> Any:
        return self._state


@dataclass
class _StubSession:
    """Minimal session shape that every adapter's get_human_action +
    run_game_loop body touches. We don't model the full GameSession —
    just what the dead-LLM short-circuit and per-turn frame paths need.
    """
    id: str = "test-match"
    game: _StubGame = field(default_factory=_StubGame)
    is_finished: bool = False
    winner_id: Optional[str] = None
    player_ids: list = field(default_factory=lambda: ["p1", "p2"])
    player_names: dict = field(default_factory=lambda: {"p1": "P1", "p2": "P2"})
    human_players: list = field(default_factory=list)  # bot_vs_bot has none
    record_actions_for_replay: bool = True
    replay_frames: list = field(default_factory=list)
    _pending_action_future: Optional[asyncio.Future] = None
    _pending_player_id: Optional[str] = None
    _action_processed_event: Optional[asyncio.Event] = None
    _game_log: list = field(default_factory=list)
    on_state_change: Optional[Callable] = None
    mode: str = "bot_vs_bot"

    def _record_frame(self, action: Optional[dict] = None) -> None:
        self.replay_frames.append({"action": action})

    def get_client_state(self, pid: str) -> Any:
        class _S:
            def model_dump(self):
                return {}
        return _S()


# Each entry: (label, AdapterClass, streak_attr, fallback_action_type, frame_prefix)
ADAPTERS = [
    ("ygo", YugiohModeAdapter, "_ygo_consecutive_timeouts", "end_phase", "YGO"),
    ("hs", HearthstoneModeAdapter, "_hs_consecutive_timeouts", "HS_END_TURN", "HS"),
    ("mc", MinecraftModeAdapter, "_mc_consecutive_timeouts", "MC_END_TURN", "MC"),
    ("finance", FinanceModeAdapter, "_fin_consecutive_timeouts", "FIN_END_TURN", "FIN"),
    ("scp", SCPModeAdapter, "_scp_consecutive_timeouts", "SCP_END_TURN", "SCP"),
    ("depths", DepthsModeAdapter, "_depths_consecutive_timeouts", "DEPTHS_END_TURN", "DEPTHS"),
]


@pytest.fixture
def patch_instant_timeout(monkeypatch):
    """Make every adapter's ``asyncio.wait_for`` raise TimeoutError
    immediately so we don't actually wait 300 s per call."""
    import asyncio as aio
    real = aio.wait_for

    async def _instant_timeout(awaitable, timeout):
        if hasattr(awaitable, "cancel"):
            awaitable.cancel()
        raise aio.TimeoutError()

    monkeypatch.setattr(aio, "wait_for", _instant_timeout)
    return real


@pytest.mark.parametrize("label,adapter_cls,streak_attr,fallback_action,frame_prefix", ADAPTERS)
def test_consecutive_timeouts_finish_match(
    label, adapter_cls, streak_attr, fallback_action, frame_prefix, patch_instant_timeout
):
    """3 consecutive get_human_action timeouts must flip is_finished."""
    session = _StubSession()
    adapter = adapter_cls()

    async def _run():
        # First two timeouts: streak rises but match keeps running.
        for i in range(2):
            action = await adapter.get_human_action(session, "p1", session.game.state)
            assert action.get("action_type") == fallback_action
            assert getattr(session, streak_attr) == i + 1
        assert not session.is_finished, (
            f"[{label}] After 2 timeouts the match must still be running — "
            "a one-off slow LLM call shouldn't kill a live game."
        )

        # Third timeout: streak hits threshold, is_finished flips.
        await adapter.get_human_action(session, "p1", session.game.state)
        assert getattr(session, streak_attr) == 3
        assert session.is_finished, (
            f"[{label}] After 3 consecutive timeouts the match must be "
            "marked finished so run_game_loop exits cleanly."
        )

    asyncio.run(_run())


@pytest.mark.parametrize("label,adapter_cls,streak_attr,fallback_action,frame_prefix", ADAPTERS)
def test_streak_resets_when_action_arrives(
    label, adapter_cls, streak_attr, fallback_action, frame_prefix, monkeypatch
):
    """A real action between timeouts must reset the streak to 0 so the
    short-circuit doesn't fire on a healthy seat with intermittent slow
    calls."""
    import asyncio as aio
    real_wait_for = aio.wait_for

    # Two-state wait_for: first call raises (timeout), second returns a
    # real action, third raises again. Sequence: T → A → T. Streak should
    # be: 1 → 0 → 1. Match must NOT be finished at the end.
    call_index = {"n": 0}

    async def _scripted(awaitable, timeout):
        call_index["n"] += 1
        if call_index["n"] in (1, 3):
            if hasattr(awaitable, "cancel"):
                awaitable.cancel()
            raise aio.TimeoutError()
        # Mid call: pretend a real action arrived.
        if hasattr(awaitable, "cancel"):
            awaitable.cancel()
        return {"action_type": "FAKE_REAL_ACTION"}

    monkeypatch.setattr(aio, "wait_for", _scripted)

    session = _StubSession()
    adapter = adapter_cls()

    async def _run():
        # T (timeout)
        await adapter.get_human_action(session, "p1", session.game.state)
        assert getattr(session, streak_attr) == 1

        # A (real action) — streak resets
        action = await adapter.get_human_action(session, "p1", session.game.state)
        assert action.get("action_type") == "FAKE_REAL_ACTION"
        assert getattr(session, streak_attr) == 0

        # T (timeout again)
        await adapter.get_human_action(session, "p1", session.game.state)
        assert getattr(session, streak_attr) == 1
        assert not session.is_finished, (
            f"[{label}] Alternating timeout/action sequence must never "
            "trip the dead-LLM short-circuit."
        )

    asyncio.run(_run())


@pytest.mark.parametrize("label,adapter_cls,streak_attr,fallback_action,frame_prefix", ADAPTERS)
def test_run_game_loop_records_per_turn_frame(
    label, adapter_cls, streak_attr, fallback_action, frame_prefix, monkeypatch
):
    """The per-turn safety-net frame must fire on every completed
    run_turn() so the replay archive captures progression even when no
    action POST arrives. Mirrors test_pokemon_run_game_loop_records_*."""
    session = _StubSession()
    # Auto-end the game after 3 turns so the loop terminates.
    turn_counter = {"n": 0}

    async def _stub_run_turn():
        turn_counter["n"] += 1
        session.game.turn_manager.turn_number = turn_counter["n"]
        if turn_counter["n"] >= 3:
            session.game._game_over = True

    session.game.turn_manager.run_turn = _stub_run_turn  # type: ignore[assignment]

    adapter = adapter_cls()

    async def _run():
        await adapter.run_game_loop(session)
        # 3 turns × 1 turn-complete frame each.
        turn_complete_frames = [
            f for f in session.replay_frames
            if (f.get("action") or {}).get("kind") == "turn_complete"
        ]
        assert len(turn_complete_frames) >= 3, (
            f"[{label}] Expected at least 3 turn-complete frames, "
            f"got {len(turn_complete_frames)}. The per-turn safety net "
            "in run_game_loop is what catches dead-LLM matches."
        )
        # Frames must carry the engine-specific action_type marker.
        markers = {
            (f.get("action") or {}).get("action_type")
            for f in turn_complete_frames
        }
        assert any(frame_prefix in (m or "") for m in markers), (
            f"[{label}] turn-complete frames must tag the engine via "
            f"action_type (saw: {markers}, expected prefix: {frame_prefix})."
        )

    asyncio.run(_run())
