"""Public "Watch Claude play" spectator demo (Phase 4.1).

A background task cycles through the four canonical game modes, creating a
``bot_vs_bot`` ultra match each time the previous one ends. The currently-live
match's ID is exposed via ``GET /api/spectate/live`` so a spectator landing
page can redirect to ``/watch/<match_id>``.

This reuses the existing create_match + start_match plumbing, including the
Phase 2 ``_spawn_ultra_subprocess`` extension that fires two subprocesses
(one per seat) when ``mode=="bot_vs_bot"`` and ``ai_difficulty=="ultra"``.
The supervisor owns one of the ULTRA_AGENT_SEMAPHORE slots when active.

Disabled by default — set ``HYPERDRAFT_SPECTATOR_ENABLED=true`` in the
container env to opt in.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

from fastapi import BackgroundTasks

from .models import CreateMatchRequest

log = logging.getLogger(__name__)

# Cycle order — matches the four engines with ultra-AI briefs in
# prompts/ultra_ai/. SCP / Finance / Depths / Minecraft are excluded
# because they don't have ultra briefs yet. Pokémon is intentionally
# FIRST so the spectator's first impression is a fast-ish prize-race
# game rather than a 30-min MTG control mirror.
GAME_MODE_CYCLE = ("pokemon", "hearthstone", "yugioh", "mtg")

_current_match_id: Optional[str] = None
_supervisor_task: Optional[asyncio.Task] = None
_stop_event: asyncio.Event | None = None


def is_enabled() -> bool:
    """Default OFF. Opt in via HYPERDRAFT_SPECTATOR_ENABLED=true."""
    return os.environ.get("HYPERDRAFT_SPECTATOR_ENABLED", "").lower() in ("true", "1", "yes")


def current_match_id() -> Optional[str]:
    """Read-only: which match ID is the live demo right now?"""
    return _current_match_id


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

    # start_match's route handler attaches run_game_session via
    # FastAPI's BackgroundTasks queue, which only fires after an HTTP
    # response. Calling it programmatically with a fresh BackgroundTasks()
    # silently drops the task — the session is created but the game
    # engine never runs. We schedule run_game_session directly as an
    # asyncio task so both Claude subprocesses actually have a game
    # state to poll against.
    try:
        asyncio.create_task(run_game_session(session))
    except Exception as e:  # noqa: BLE001
        log.warning("spectator: scheduling run_game_session for %s failed: %s", match_id, e)
        await session_manager.remove_session(match_id)
        return None

    log.info("spectator: started demo match=%s game_mode=%s", match_id, game_mode)
    return match_id


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
    """Long-running task: keep one demo match alive at all times."""
    global _current_match_id
    cycle_idx = 0
    cooldown_seconds = float(os.environ.get("HYPERDRAFT_SPECTATOR_COOLDOWN", "30"))

    log.info("spectator supervisor starting (cycle=%s cooldown=%ss)",
             list(GAME_MODE_CYCLE), cooldown_seconds)

    while True:
        if _stop_event is not None and _stop_event.is_set():
            return
        if not is_enabled():
            await asyncio.sleep(30)
            continue

        game_mode = GAME_MODE_CYCLE[cycle_idx % len(GAME_MODE_CYCLE)]
        cycle_idx += 1

        match_id = await _spawn_one_demo_match(game_mode)
        if match_id is None:
            # Backoff and try the next mode.
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

        log.info("spectator: demo match=%s ended; cooling down %ss then advancing",
                 match_id, cooldown_seconds)
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
