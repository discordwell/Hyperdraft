"""Pipeline-the-Game v0.2 REST routes.

Single-process, in-memory match registry. Client posts a card, the server
runs the engine for both halves of the trick (AI opponent picks randomly,
RESOLVE-biased), and returns the new snapshot.

When v0.3 adds real socket updates, swap the GET-poll loop for a
Socket.IO room and emit `pipeline_state_update` on each play.
"""

from __future__ import annotations

import random
import string
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.engine.pipeline_deck import (
    DECK_REGISTRY,
    default_event_deck,
    load_deck,
)
from src.engine.pipeline_game import PipelineGameManager

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

# In-memory match registry. v0.2 is single-process; production-grade
# persistence + cross-process sharing is deferred to v0.3.
_pipeline_matches: dict[str, PipelineGameManager] = {}


# ───────────────────────── request / response models ──────────────────


class StartRequest(BaseModel):
    deck_a_id: str = "starter_a_lightning"
    deck_b_id: str = "starter_b_control"
    rng_seed: Optional[int] = None


class StartResponse(BaseModel):
    match_id: str
    player_id: str
    snapshot: dict


class PlayRequest(BaseModel):
    player_id: str
    card_id: str


class PlayResponse(BaseModel):
    snapshot: dict
    trick_resolved: bool
    resolution: Optional[dict] = None  # set when both played + trick ran


# ───────────────────────── helpers ────────────────────────────────────


def _make_match_id() -> str:
    """Generate an HD-XXXX short code unique within the current registry."""
    while True:
        suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        candidate = f"HD-{suffix}"
        if candidate not in _pipeline_matches:
            return candidate


def _pick_ai_card(manager: PipelineGameManager, ai_pid: str):
    """Heuristic AI: bias toward RESOLVE (mandatory column), then pick the
    highest-cost card available in that stage. If no RESOLVE in hand, fall
    back to any stage."""
    hand = manager.state.hands[ai_pid]
    resolves = [c for c in hand if c.stage == "RESOLVE"]
    pool = resolves if (resolves and random.random() < 0.7) else hand
    # Filter out stages already filled
    slots = manager.state.slots[ai_pid]
    pool = [c for c in pool if slots.get(c.stage) is None]
    if not pool:
        return None
    # Highest cost wins (slightly smart, not optimal).
    return max(pool, key=lambda c: c.cost)


# ───────────────────────── routes ─────────────────────────────────────


@router.post("/start", response_model=StartResponse)
async def start_match(req: StartRequest) -> StartResponse:
    """Start a new Pipeline-the-Game match. Player A is the human; player
    B is the AI in v0.2."""
    if req.deck_a_id not in DECK_REGISTRY:
        raise HTTPException(404, f"unknown deck {req.deck_a_id!r}")
    if req.deck_b_id not in DECK_REGISTRY:
        raise HTTPException(404, f"unknown deck {req.deck_b_id!r}")

    match_id = _make_match_id()
    player_id = "player_a"
    opponent_id = "player_b"

    manager = PipelineGameManager(
        match_id=match_id,
        player_a_id=player_id,
        player_b_id=opponent_id,
        deck_a=load_deck(req.deck_a_id),
        deck_b=load_deck(req.deck_b_id),
        event_deck=default_event_deck(),
        rng_seed=req.rng_seed
        if req.rng_seed is not None
        else random.randint(0, 2**31 - 1),
    )
    _pipeline_matches[match_id] = manager

    return StartResponse(
        match_id=match_id,
        player_id=player_id,
        snapshot=manager.snapshot(),
    )


@router.get("/{match_id}", response_model=dict)
async def get_state(match_id: str) -> dict:
    manager = _pipeline_matches.get(match_id)
    if manager is None:
        raise HTTPException(404, f"match {match_id!r} not found")
    return manager.snapshot()


@router.post("/{match_id}/play", response_model=PlayResponse)
async def play_card(match_id: str, req: PlayRequest) -> PlayResponse:
    manager = _pipeline_matches.get(match_id)
    if manager is None:
        raise HTTPException(404, f"match {match_id!r} not found")

    # Player plays the card.
    try:
        manager.play_card(req.player_id, req.card_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # AI opponent auto-plays a card if it hasn't yet this trick.
    ai_pid = (
        manager.state.player_b_id
        if req.player_id == manager.state.player_a_id
        else manager.state.player_a_id
    )
    ai_card = _pick_ai_card(manager, ai_pid)
    if ai_card is not None:
        manager.play_card(ai_pid, ai_card.id)

    # If both players have at least one card slotted, resolve the trick.
    a_slots = manager.state.slots[manager.state.player_a_id]
    b_slots = manager.state.slots[manager.state.player_b_id]
    resolution = None
    trick_resolved = False
    if any(a_slots.values()) and any(b_slots.values()):
        result = manager.resolve_trick()
        trick_resolved = True
        resolution = {
            "winner": result.winner,
            "a_impact": {
                "damage_dealt": result.a_impact.damage_dealt,
                "life_gained": result.a_impact.life_gained,
                "cards_drawn": result.a_impact.cards_drawn,
                "cards_destroyed": result.a_impact.cards_destroyed,
                "prevented": result.a_impact.prevented,
                "total": result.a_impact.total,
            },
            "b_impact": {
                "damage_dealt": result.b_impact.damage_dealt,
                "life_gained": result.b_impact.life_gained,
                "cards_drawn": result.b_impact.cards_drawn,
                "cards_destroyed": result.b_impact.cards_destroyed,
                "prevented": result.b_impact.prevented,
                "total": result.b_impact.total,
            },
            "log": list(result.log),
        }

    return PlayResponse(
        snapshot=manager.snapshot(),
        trick_resolved=trick_resolved,
        resolution=resolution,
    )


@router.post("/{match_id}/reshuffle", response_model=StartResponse)
async def reshuffle(match_id: str) -> StartResponse:
    """Reset and reshuffle a finished or in-progress match. Keeps the
    same match_id so the frontend's URL doesn't change."""
    manager = _pipeline_matches.get(match_id)
    if manager is None:
        raise HTTPException(404, f"match {match_id!r} not found")

    fresh = PipelineGameManager(
        match_id=match_id,
        player_a_id=manager.state.player_a_id,
        player_b_id=manager.state.player_b_id,
        deck_a=load_deck("starter_a_lightning"),
        deck_b=load_deck("starter_b_control"),
        event_deck=default_event_deck(),
        rng_seed=random.randint(0, 2**31 - 1),
    )
    _pipeline_matches[match_id] = fresh
    return StartResponse(
        match_id=match_id,
        player_id=manager.state.player_a_id,
        snapshot=fresh.snapshot(),
    )


@router.get("/_meta/decks", response_model=list[str])
async def list_decks() -> list[str]:
    """For the frontend deck-picker, eventually."""
    return list(DECK_REGISTRY.keys())
