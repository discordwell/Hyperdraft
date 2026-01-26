"""
Match Routes

Endpoints for creating and managing game matches.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional
import asyncio

from ..session import session_manager, GameSession
from ..models import (
    CreateMatchRequest, CreateMatchResponse,
    PlayerActionRequest, ActionResultResponse,
    GameStateResponse,
    SubmitChoiceRequest, ChoiceResultResponse
)

# Card imports
from src.cards import ALL_CARDS

# Deck imports
from src.decks import STANDARD_DECKS, ALL_DECKS, get_deck, get_random_deck, load_deck

router = APIRouter(prefix="/match", tags=["match"])


@router.get("/decks")
async def list_decks() -> dict:
    """
    List all available decks (standard + netdecks).

    Returns deck IDs, names, archetypes, and colors.
    """
    decks = []
    for deck_id, deck in ALL_DECKS.items():
        decks.append({
            "id": deck_id,
            "name": deck.name,
            "archetype": deck.archetype,
            "colors": deck.colors,
            "description": deck.description,
            "mainboard_count": deck.mainboard_count,
            "sideboard_count": deck.sideboard_count,
            "source": deck.source,
            "is_netdeck": deck_id.endswith("_netdeck"),
        })
    return {"decks": decks, "total": len(decks)}


def get_deck_cards(deck_id: str = None) -> list:
    """
    Get cards for a deck by ID or random if no ID provided.

    Returns list of CardDefinition objects ready for gameplay.
    """
    if deck_id and deck_id in ALL_DECKS:
        deck = ALL_DECKS[deck_id]
    else:
        deck = get_random_deck()

    return load_deck(ALL_CARDS, deck)


def get_cards_by_names(card_names: list[str]) -> list:
    """
    Get cards by a list of card names.

    Returns list of CardDefinition objects.
    """
    cards = []
    for name in card_names:
        if name in ALL_CARDS:
            cards.append(ALL_CARDS[name])
    return cards


@router.post("/create", response_model=CreateMatchResponse)
async def create_match(
    request: CreateMatchRequest,
    background_tasks: BackgroundTasks
) -> CreateMatchResponse:
    """
    Create a new match.

    Returns match_id and player_id for the human player.
    """
    # Create session
    session = await session_manager.create_session(
        mode=request.mode,
        player_name=request.player_name,
        ai_difficulty=request.ai_difficulty
    )

    # Add human player
    human_id = session.add_player(request.player_name, is_ai=False)

    # Add AI player for human vs bot mode
    if request.mode == "human_vs_bot":
        ai_id = session.add_player("AI Opponent", is_ai=True)
    elif request.mode == "bot_vs_bot":
        ai_id = session.add_player("AI 1", is_ai=True)
        ai2_id = session.add_player("AI 2", is_ai=True)
    else:
        ai_id = None

    # Build decks - prefer deck_id, fallback to card names, else random
    if request.player_deck_id:
        player_deck = get_deck_cards(request.player_deck_id)
    elif request.player_deck:
        player_deck = get_cards_by_names(request.player_deck)
    else:
        player_deck = get_deck_cards()  # Random deck

    if request.ai_deck_id:
        ai_deck = get_deck_cards(request.ai_deck_id)
    elif request.ai_deck:
        ai_deck = get_cards_by_names(request.ai_deck)
    else:
        ai_deck = get_deck_cards()  # Random deck

    # Add cards to libraries
    session.add_cards_to_deck(human_id, player_deck)

    if request.mode == "human_vs_bot" and ai_id:
        session.add_cards_to_deck(ai_id, ai_deck)
    elif request.mode == "bot_vs_bot":
        session.add_cards_to_deck(ai_id, ai_deck)
        session.add_cards_to_deck(ai2_id, ai_deck)

    return CreateMatchResponse(
        match_id=session.id,
        player_id=human_id,
        opponent_id=ai_id or "",
        status="created"
    )


@router.post("/{match_id}/start")
async def start_match(
    match_id: str,
    background_tasks: BackgroundTasks
) -> dict:
    """
    Start a match that has been created.

    This begins the game loop.
    """
    session = session_manager.get_session(match_id)
    if not session:
        raise HTTPException(status_code=404, detail="Match not found")

    if session.is_started:
        raise HTTPException(status_code=400, detail="Match already started")

    # Start the game in background
    background_tasks.add_task(run_game_session, session)

    return {"status": "started", "match_id": match_id}


async def run_game_session(session: GameSession):
    """Background task to run a game session."""
    try:
        await session.start_game()
        await session.run_until_human_input()
    except Exception as e:
        import traceback
        print(f"Game session error: {e}")
        traceback.print_exc()
        session.is_finished = True


@router.get("/{match_id}/state", response_model=GameStateResponse)
async def get_match_state(
    match_id: str,
    player_id: Optional[str] = None
) -> GameStateResponse:
    """
    Get the current state of a match.

    If player_id is provided, returns state from that player's perspective
    (including their hand and legal actions).
    """
    session = session_manager.get_session(match_id)
    if not session:
        raise HTTPException(status_code=404, detail="Match not found")

    return session.get_client_state(player_id)


@router.post("/{match_id}/action", response_model=ActionResultResponse)
async def submit_action(
    match_id: str,
    action: PlayerActionRequest
) -> ActionResultResponse:
    """
    Submit a player action.

    The action must be legal for the current game state.
    """
    session = session_manager.get_session(match_id)
    if not session:
        raise HTTPException(status_code=404, detail="Match not found")

    if session.is_finished:
        raise HTTPException(status_code=400, detail="Game is finished")

    success, message = await session.handle_action(action)

    if not success:
        return ActionResultResponse(
            success=False,
            message=message
        )

    # Get updated state
    new_state = session.get_client_state(action.player_id)

    return ActionResultResponse(
        success=True,
        message="Action processed",
        new_state=new_state
    )


@router.post("/{match_id}/choice", response_model=ChoiceResultResponse)
async def submit_choice(
    match_id: str,
    request: SubmitChoiceRequest
) -> ChoiceResultResponse:
    """
    Submit a player choice (modal spell, scry, target, etc.).

    Used when the game is paused waiting for player input.
    """
    session = session_manager.get_session(match_id)
    if not session:
        raise HTTPException(status_code=404, detail="Match not found")

    if session.is_finished:
        raise HTTPException(status_code=400, detail="Game is finished")

    # Check there's actually a pending choice
    pending_choice = session.game.get_pending_choice()
    if not pending_choice:
        raise HTTPException(status_code=400, detail="No pending choice")

    # Submit the choice
    success, message, events = session.game.submit_choice(
        choice_id=request.choice_id,
        player_id=request.player_id,
        selected=request.selected
    )

    if not success:
        return ChoiceResultResponse(
            success=False,
            message=message
        )

    # Get updated state
    new_state = session.get_client_state(request.player_id)

    return ChoiceResultResponse(
        success=True,
        message="Choice submitted",
        new_state=new_state,
        events=[{'type': e.type.name, 'payload': e.payload} for e in events]
    )


@router.get("/{match_id}/choice")
async def get_pending_choice(
    match_id: str,
    player_id: Optional[str] = None
) -> dict:
    """
    Get the current pending choice, if any.

    Returns choice details if it's for the requesting player.
    """
    session = session_manager.get_session(match_id)
    if not session:
        raise HTTPException(status_code=404, detail="Match not found")

    pending_choice = session.game.get_pending_choice()
    if not pending_choice:
        return {"pending_choice": None}

    # Full details for the player who needs to make the choice
    if player_id == pending_choice.player:
        return {
            "pending_choice": {
                "id": pending_choice.id,
                "choice_type": pending_choice.choice_type,
                "player": pending_choice.player,
                "prompt": pending_choice.prompt,
                "options": pending_choice.options,
                "source_id": pending_choice.source_id,
                "min_choices": pending_choice.min_choices,
                "max_choices": pending_choice.max_choices,
            }
        }

    # Limited info for other players
    return {
        "pending_choice": {
            "waiting_for": pending_choice.player,
            "choice_type": pending_choice.choice_type,
        }
    }


@router.post("/{match_id}/concede")
async def concede_match(
    match_id: str,
    player_id: str
) -> dict:
    """
    Concede a match.

    The conceding player loses immediately.
    """
    session = session_manager.get_session(match_id)
    if not session:
        raise HTTPException(status_code=404, detail="Match not found")

    if session.is_finished:
        raise HTTPException(status_code=400, detail="Game is already finished")

    # Find the opponent
    opponent_id = None
    for pid in session.player_ids:
        if pid != player_id:
            opponent_id = pid
            break

    session.is_finished = True
    session.winner_id = opponent_id

    return {
        "status": "conceded",
        "winner": opponent_id
    }


@router.delete("/{match_id}")
async def delete_match(match_id: str) -> dict:
    """
    Delete a match and clean up resources.
    """
    session = session_manager.get_session(match_id)
    if not session:
        raise HTTPException(status_code=404, detail="Match not found")

    await session_manager.remove_session(match_id)

    return {"status": "deleted", "match_id": match_id}
