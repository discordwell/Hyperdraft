"""Public "Watch Claude play" spectator demo.

A background task spawns ``bot_vs_bot`` ultra LLM-pilot demo matches on
demand. The currently-live match's ID is exposed via
``GET /api/spectate/live`` so the spectator landing page can redirect to
``/watch/<match_id>``.

This reuses the existing create_match + start_match plumbing, including
``_spawn_ultra_subprocess`` which fires two subprocesses (one per seat)
when ``mode=="bot_vs_bot"`` and ``ai_difficulty=="ultra"``.

Toggle model: enabled state lives in ``storage/spectator_state.json``.
Single-shot mode (the default) spawns one match per Start click and
auto-disables when that match ends. Cleared on container restart unless
the state file survives (it lives on the persistent volume).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks

from . import ultra_telemetry
from .models import CreateMatchRequest

log = logging.getLogger(__name__)

# Game modes that have an ultra brief in prompts/ultra_ai/. SCP / Finance
# / Depths / Minecraft excluded because they don't have ultra briefs yet.
SUPPORTED_GAME_MODES = ("pokemon", "hearthstone", "yugioh", "mtg")
DEFAULT_GAME_MODE = "mtg"

# Cooldown between toggle requests (start/stop), to deter thrash. Applies
# regardless of caller — the supervisor itself bypasses the cooldown when
# auto-disabling after a single-shot match ends (that's not a user
# toggle).
TOGGLE_COOLDOWN_SECONDS = 30.0

_STATE_PATH = Path(os.environ.get("HYPERDRAFT_SPECTATOR_STATE_FILE", "storage/spectator_state.json"))

_current_match_id: Optional[str] = None
_supervisor_task: Optional[asyncio.Task] = None
_stop_event: asyncio.Event | None = None
_state_lock = asyncio.Lock()


def _default_state() -> dict:
    return {
        "enabled": False,
        "single_shot": True,
        "requested_game_mode": None,
        "last_toggle_at": 0.0,
        "started_at": None,
    }


def _read_state() -> dict:
    """Read the persisted toggle state. Default OFF when the file is absent.

    The legacy ``HYPERDRAFT_SPECTATOR_ENABLED`` env var is intentionally
    ignored — the on-demand toggle is the only enable path. Set it via
    ``POST /api/spectate/start`` (or persist `storage/spectator_state.json`
    out-of-band) to enable.
    """
    try:
        if _STATE_PATH.exists():
            with _STATE_PATH.open("r") as f:
                data = json.load(f)
            merged = _default_state()
            merged.update({k: v for k, v in data.items() if k in merged})
            return merged
    except (OSError, json.JSONDecodeError) as e:
        log.warning("spectator: failed to read state file %s: %s", _STATE_PATH, e)
    return _default_state()


def _write_state(state: dict) -> None:
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STATE_PATH.with_suffix(".tmp")
        with tmp.open("w") as f:
            json.dump(state, f)
        tmp.replace(_STATE_PATH)
    except OSError as e:
        log.warning("spectator: failed to write state file %s: %s", _STATE_PATH, e)


def is_enabled() -> bool:
    return bool(_read_state().get("enabled"))


def current_match_id() -> Optional[str]:
    """Read-only: which match ID is the live demo right now?"""
    return _current_match_id


def current_game_mode() -> Optional[str]:
    """Read-only: which game mode is the live demo running?"""
    return _read_state().get("requested_game_mode")


def get_status() -> dict:
    """Full public status for the operator UI."""
    state = _read_state()
    now = time.time()
    elapsed = now - float(state.get("last_toggle_at") or 0.0)
    cooldown_remaining = max(0.0, TOGGLE_COOLDOWN_SECONDS - elapsed)
    return {
        "enabled": bool(state.get("enabled")),
        "single_shot": bool(state.get("single_shot")),
        "current_match_id": _current_match_id,
        "game_mode": state.get("requested_game_mode"),
        "started_at": state.get("started_at"),
        "cooldown_seconds_remaining": round(cooldown_remaining, 1),
        "supported_game_modes": list(SUPPORTED_GAME_MODES),
    }


class ToggleRejected(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


async def request_start(game_mode: Optional[str] = None, *, single_shot: bool = True) -> dict:
    """User-facing Start: queue exactly one demo match (single-shot default).

    Raises ToggleRejected with HTTP-style status codes:
      * 409 if a match is already running or another start is pending
      * 429 if the cooldown hasn't elapsed since the last toggle
      * 400 if game_mode isn't in SUPPORTED_GAME_MODES
    """
    async with _state_lock:
        state = _read_state()
        now = time.time()

        if state.get("enabled") or _current_match_id:
            raise ToggleRejected(
                409,
                "Spectator demo is already running; press Stop first or wait for it to finish.",
            )

        elapsed = now - float(state.get("last_toggle_at") or 0.0)
        if elapsed < TOGGLE_COOLDOWN_SECONDS:
            wait = round(TOGGLE_COOLDOWN_SECONDS - elapsed, 1)
            raise ToggleRejected(
                429,
                f"Cooldown active. Try again in {wait}s.",
            )

        mode = (game_mode or DEFAULT_GAME_MODE).lower()
        if mode not in SUPPORTED_GAME_MODES:
            raise ToggleRejected(
                400,
                f"Unsupported game_mode {mode!r}. Pick one of {SUPPORTED_GAME_MODES}.",
            )

        state.update(
            enabled=True,
            single_shot=bool(single_shot),
            requested_game_mode=mode,
            last_toggle_at=now,
            started_at=now,
        )
        _write_state(state)
        log.info("spectator: start requested game_mode=%s single_shot=%s", mode, single_shot)
        return get_status()


async def request_stop() -> dict:
    """User-facing Stop with two-step escalation.

    * First call (toggle is ON): flip the toggle off so no new match
      spawns. The currently-running match continues to its natural end.
    * Second call (toggle is OFF but a match is still running): kill the
      in-flight match — SIGTERM the ultra subprocesses + remove the
      session so the supervisor's watcher returns immediately.

    The kill path bypasses the user-toggle cooldown because it's a
    different operation (terminate, not toggle).
    """
    global _current_match_id
    async with _state_lock:
        state = _read_state()
        now = time.time()
        match_id = _current_match_id

        # Escalation: toggle already off, but the supervisor is still
        # watching a running match. Kill it.
        if not state.get("enabled") and match_id:
            log.info("spectator: stop escalation — killing match=%s", match_id)
            killed = _kill_in_flight_match(match_id)
            # Don't clear _current_match_id here; the supervisor watcher
            # observes session removal and clears it on its next poll.
            status = get_status()
            status["killed_subprocesses"] = killed
            return status

        elapsed = now - float(state.get("last_toggle_at") or 0.0)
        if elapsed < TOGGLE_COOLDOWN_SECONDS and not state.get("enabled"):
            wait = round(TOGGLE_COOLDOWN_SECONDS - elapsed, 1)
            raise ToggleRejected(429, f"Cooldown active. Try again in {wait}s.")

        state.update(enabled=False, last_toggle_at=now)
        _write_state(state)
        log.info("spectator: stop requested (no kill — match runs to natural end)")
        return get_status()


def _kill_in_flight_match(match_id: str) -> int:
    """Tear down the live demo match: signal subprocesses + drop the session.

    Import is local because routes.match imports from this module
    transitively via the supervisor's _spawn_one_demo_match.
    """
    from .routes.match import kill_match_subprocesses
    from .session import session_manager

    killed = kill_match_subprocesses(match_id)
    # Schedule session removal — remove_session is async but we're in a
    # sync callback path here (called inside _state_lock). Fire-and-forget
    # is fine; the supervisor will observe session=None within 5s anyway.
    try:
        asyncio.create_task(session_manager.remove_session(match_id))
    except RuntimeError:
        # No running loop (e.g. tests calling synchronously). The supervisor
        # watcher would also see is_finished, so this isn't load-bearing.
        pass
    return killed


def _auto_disable_after_single_shot() -> None:
    """Called by the supervisor when a single-shot match ends.

    Stamps ``last_toggle_at`` so the cooldown applies post-match too —
    otherwise a quick-ending match (concession, spawn failure) would let
    a fresh Start fire immediately and bypass abuse-mitigation.
    """
    state = _read_state()
    if state.get("single_shot"):
        state.update(enabled=False, started_at=None, last_toggle_at=time.time())
        _write_state(state)


async def _spawn_one_demo_match(game_mode: str) -> Optional[str]:
    """Create + start a single bot_vs_bot ultra demo match. Returns its ID."""
    from .routes.match import create_match, run_game_session
    from .session import session_manager

    request = CreateMatchRequest(
        mode="bot_vs_bot",
        game_mode=game_mode,
        ai_difficulty="ultra",
        ultra_agent="claude",
        player_name=f"Demo Spectator ({game_mode})",
    )
    try:
        resp = await create_match(request=request, background_tasks=BackgroundTasks())
    except Exception as e:  # noqa: BLE001
        log.warning("spectator: create_match for game_mode=%s failed: %s", game_mode, e)
        return None

    match_id = resp.match_id
    session = session_manager.get_session(match_id)
    if session is None:
        log.warning("spectator: session %s not found after create", match_id)
        return None

    # start_match's route handler attaches run_game_session via FastAPI's
    # BackgroundTasks queue, which only fires after an HTTP response.
    # Calling it programmatically with a fresh BackgroundTasks() silently
    # drops the task. Schedule it directly as an asyncio task so both
    # Claude subprocesses actually have a game state to poll against.
    try:
        asyncio.create_task(run_game_session(session))
    except Exception as e:  # noqa: BLE001
        log.warning("spectator: scheduling run_game_session for %s failed: %s", match_id, e)
        await session_manager.remove_session(match_id)
        return None

    log.info("spectator: started demo match=%s game_mode=%s", match_id, game_mode)
    return match_id


def _write_post_match_takeaway(match_id: str, game_mode: str) -> None:
    """Synthesize a Session takeaway from the decision log + match state and
    append it to ``storage/strategy/<game_mode>.md``.

    The pilot's prompt brief tells claude to append a takeaway at game end,
    but in practice the subprocess exits at SIGTERM (watchdog) without
    flushing — 38 matches archived to date, zero takeaways written. This
    supervisor-side fallback guarantees one entry per match.

    Best-effort: all failures log + continue (a missing strategy doc must
    not block the next demo match from spawning).
    """
    from .session import session_manager  # local import: avoids cycle

    try:
        session = session_manager.get_session(match_id)

        winner_id: Optional[str] = None
        total_turns: Optional[int] = None
        seat_labels: dict[str, str] = {}

        if session is not None:
            winner_id = session.winner_id
            tm = getattr(session.game, "turn_manager", None)
            if tm is not None:
                total_turns = int(getattr(tm, "turn_number", 0) or 0)
            for pid in session.player_ids:
                profile = session.ai_profiles_by_player.get(pid) or {}
                brain = (profile.get("brain") or "").lower()
                diff = profile.get("difficulty") or ""
                if hasattr(diff, "value"):
                    diff = diff.value
                if brain or diff:
                    seat_labels[pid] = f"{session.player_names.get(pid, pid[:6])} ({brain or '?'} · {diff or '?'})"
                else:
                    seat_labels[pid] = session.player_names.get(pid, pid[:6])

        body = ultra_telemetry.synthesize_takeaway(
            match_id=match_id,
            game_mode=game_mode,
            winner_id=winner_id,
            seat_labels=seat_labels,
            total_turns=total_turns,
        )
        written = ultra_telemetry.append_takeaway_to_strategy_doc(
            game_mode=game_mode,
            body=body,
        )
        if written:
            log.info("spectator: wrote takeaway match=%s → %s", match_id, written)
    except Exception as e:  # noqa: BLE001
        log.warning("spectator: takeaway synth failed for match=%s: %s", match_id, e)


async def _wait_for_match_end(match_id: str, poll_seconds: float = 5.0) -> None:
    """Block until the match's session reports is_finished, is gone, or hits
    the per-match wall-time cap.

    Without the wall-time cap, a stuck demo match (e.g. the ultra agents
    couldn't authenticate and their subprocesses died with no game progress)
    would keep the spectator soft-slot held forever and no new demo would
    start until container restart.
    """
    from .session import session_manager

    max_wall = float(os.environ.get("HYPERDRAFT_SPECTATOR_MAX_WALL_SECONDS", "5400"))  # 90 min
    started_at = time.time()
    while True:
        if _stop_event is not None and _stop_event.is_set():
            return
        session = session_manager.get_session(match_id)
        if session is None:
            return
        if session.is_finished:
            return
        try:
            if session.game.is_game_over():
                return
        except Exception:  # noqa: BLE001
            pass
        if time.time() - started_at > max_wall:
            log.warning(
                "spectator: demo match=%s exceeded %.0fs wall time; dropping",
                match_id, max_wall,
            )
            try:
                await session_manager.remove_session(match_id)
            except Exception:  # noqa: BLE001
                pass
            return
        await asyncio.sleep(poll_seconds)


async def supervisor_loop() -> None:
    """Long-running task: spawn one demo match each time the toggle goes on.

    Single-shot (default): runs one match, auto-disables, idles until the
    next Start click.

    Continuous (set via legacy HYPERDRAFT_SPECTATOR_ENABLED env var):
    cycles through SUPPORTED_GAME_MODES indefinitely until something
    flips the toggle off.
    """
    global _current_match_id
    cycle_idx = 0
    cooldown_seconds = float(os.environ.get("HYPERDRAFT_SPECTATOR_COOLDOWN", "30"))

    log.info("spectator supervisor starting (cooldown=%ss)", cooldown_seconds)

    while True:
        if _stop_event is not None and _stop_event.is_set():
            return

        state = _read_state()
        if not state.get("enabled"):
            await asyncio.sleep(5)
            continue

        if state.get("single_shot"):
            game_mode = (state.get("requested_game_mode") or DEFAULT_GAME_MODE).lower()
        else:
            game_mode = SUPPORTED_GAME_MODES[cycle_idx % len(SUPPORTED_GAME_MODES)]
            cycle_idx += 1

        match_id = await _spawn_one_demo_match(game_mode)
        if match_id is None:
            # Backoff and try again. In single-shot mode also flip off to
            # avoid hot-looping on a persistent spawn failure.
            if state.get("single_shot"):
                _auto_disable_after_single_shot()
            await asyncio.sleep(cooldown_seconds)
            continue

        _current_match_id = match_id
        try:
            await _wait_for_match_end(match_id)
        except asyncio.CancelledError:
            return
        except Exception as e:  # noqa: BLE001
            log.warning("spectator: wait_for_match_end raised: %s", e)
        finally:
            _current_match_id = None

        # Synthesize a Session-takeaway from the per-match decision log and
        # append it to storage/strategy/<game_mode>.md. The pilot brief tells
        # claude to do this at game end, but in practice the subprocess gets
        # SIGTERM'd by the watchdog without flushing the doc, so the
        # supervisor enforces it.
        _write_post_match_takeaway(match_id, game_mode)

        log.info("spectator: demo match=%s ended", match_id)

        # Single-shot: one and done. Continuous: cool down and advance.
        if _read_state().get("single_shot"):
            _auto_disable_after_single_shot()
        else:
            await asyncio.sleep(cooldown_seconds)


async def start() -> None:
    """Start the supervisor task from FastAPI lifespan."""
    global _supervisor_task, _stop_event
    if _supervisor_task is not None and not _supervisor_task.done():
        return
    _stop_event = asyncio.Event()
    _supervisor_task = asyncio.create_task(supervisor_loop())


async def stop() -> None:
    """Cancel the supervisor task on lifespan teardown."""
    global _supervisor_task, _stop_event
    if _stop_event is not None:
        _stop_event.set()
    if _supervisor_task is not None:
        _supervisor_task.cancel()
        try:
            await _supervisor_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
    _supervisor_task = None
    _stop_event = None
