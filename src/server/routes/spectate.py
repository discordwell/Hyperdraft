"""Public spectator demo endpoints.

* ``GET /api/spectate/live`` — currently-live demo match ID (404 if none).
* ``GET /api/spectate/status`` — full toggle + cooldown state.
* ``POST /api/spectate/start`` — queue one demo match (single-shot).
* ``POST /api/spectate/stop`` — prevent any further matches from spawning.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import spectator

log = logging.getLogger(__name__)

router = APIRouter(prefix="/spectate", tags=["spectate"])


class StartRequest(BaseModel):
    game_mode: Optional[str] = None


@router.get("/live")
async def get_live_demo() -> dict:
    """Return the currently-live demo match's ID, or 404 if none."""
    match_id = spectator.current_match_id()
    if not match_id:
        raise HTTPException(status_code=404, detail="No live spectator demo right now")
    return {
        "match_id": match_id,
        "spectator_enabled": spectator.is_enabled(),
        "game_mode": spectator.current_game_mode(),
    }


@router.get("/status")
async def get_spectator_status() -> dict:
    """Full operator-facing status: enabled, current match, cooldown, supported modes."""
    return spectator.get_status()


@router.post("/start")
async def post_spectate_start(request: Request, body: Optional[StartRequest] = None) -> dict:
    """Queue exactly one spectator demo match.

    Body is optional; ``{"game_mode": "pokemon"}`` picks a specific engine,
    otherwise the server default is used.

    Returns the updated status. Raises 409 / 429 / 400 on rejection.
    """
    game_mode = body.game_mode if body else None
    client = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")[:120]
    try:
        status = await spectator.request_start(game_mode=game_mode, single_shot=True)
        log.info("spectator: /start accepted client=%s game_mode=%s ua=%r",
                 client, status.get("game_mode"), ua)
        return status
    except spectator.ToggleRejected as e:
        log.info("spectator: /start rejected client=%s status=%d reason=%s",
                 client, e.status_code, e.detail)
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/stop")
async def post_spectate_stop(request: Request) -> dict:
    """Stop the spectator demo with two-step escalation.

    * First call (toggle is on): flips it off so no new matches spawn.
      The running game continues until it ends naturally.
    * Second call (toggle is already off but a match is still running):
      kills the in-flight match — SIGTERM the ultra subprocesses and
      remove the session.
    """
    client = request.client.host if request.client else "unknown"
    try:
        status = await spectator.request_stop()
        killed = status.get("killed_subprocesses")
        if killed is not None:
            log.info("spectator: /stop escalation accepted client=%s killed=%d", client, killed)
        else:
            log.info("spectator: /stop accepted client=%s", client)
        return status
    except spectator.ToggleRejected as e:
        log.info("spectator: /stop rejected client=%s status=%d", client, e.status_code)
        raise HTTPException(status_code=e.status_code, detail=e.detail)
