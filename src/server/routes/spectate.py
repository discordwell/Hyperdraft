"""Public spectator demo endpoint (Phase 4.1).

Exposes ``GET /api/spectate/live`` returning the current demo match's ID so
that ``/watch/live`` on the frontend can redirect to ``/watch/<match_id>``.
"""

from fastapi import APIRouter, HTTPException

from .. import spectator

router = APIRouter(prefix="/spectate", tags=["spectate"])


@router.get("/live")
async def get_live_demo() -> dict:
    """Return the currently-live demo match's ID, or 404 if none."""
    match_id = spectator.current_match_id()
    if not match_id:
        raise HTTPException(status_code=404, detail="No live spectator demo right now")
    return {
        "match_id": match_id,
        "spectator_enabled": spectator.is_enabled(),
    }


@router.get("/status")
async def get_spectator_status() -> dict:
    """Operator-facing: is the supervisor enabled? What's the current match?"""
    return {
        "enabled": spectator.is_enabled(),
        "current_match_id": spectator.current_match_id(),
    }
