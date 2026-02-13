"""
Bot Game Routes

Endpoints for bot vs bot games and replays.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional
import os

from ..session import session_manager, GameSession, generate_id
from ..models import (
    StartBotGameRequest, BotGameResponse,
    ReplayResponse, GameStateResponse
)

# Card/deck imports
from src.cards import ALL_CARDS
from src.cards.test_cards import TEST_CARDS
from src.cards.set_registry import get_cards_in_set, get_sets_for_card
from src.decks import ALL_DECKS, get_random_deck, load_deck

router = APIRouter(prefix="/bot-game", tags=["bot-game"])

# Store for active bot games and completed replays
active_bot_games: dict[str, GameSession] = {}
completed_replays: dict[str, ReplayResponse] = {}


def get_default_deck() -> list:
    """Get a default deck of test cards."""
    deck = []
    for card_name, card_def in TEST_CARDS.items():
        for _ in range(4):
            deck.append(card_def)
    return deck


def get_deck_cards(deck_id: Optional[str] = None) -> list:
    """
    Get cards for a deck by ID or random if no ID provided.

    Returns list of CardDefinition objects ready for gameplay.
    """
    if deck_id and deck_id in ALL_DECKS:
        deck = ALL_DECKS[deck_id]
    else:
        deck = get_random_deck()

    return load_deck(ALL_CARDS, deck)


def _parse_card_ref(ref: str) -> tuple[Optional[str], str]:
    """Parse card refs like 'TMH::Chrono-Berserker' or plain 'Card Name'."""
    raw = (ref or "").strip()
    if "::" in raw:
        domain, name = raw.split("::", 1)
        return (domain.strip() or None), name.strip()
    return None, raw


def get_cards_by_names(card_names: list[str]) -> list:
    """Resolve explicit card-name refs into CardDefinitions."""
    cards = []
    for ref in card_names:
        domain, name = _parse_card_ref(ref)
        if not name:
            continue

        card_def = None
        if domain and domain.upper() != "MTG":
            domain_cards = get_cards_in_set(domain)
            card_def = domain_cards.get(name) if domain_cards else None
        else:
            card_def = ALL_CARDS.get(name)

        if card_def is None and not domain:
            set_codes = get_sets_for_card(name)
            if len(set_codes) == 1:
                domain_cards = get_cards_in_set(set_codes[0])
                card_def = domain_cards.get(name) if domain_cards else None

        if card_def:
            cards.append(card_def)

    return cards


@router.post("/start", response_model=BotGameResponse)
async def start_bot_game(
    request: StartBotGameRequest,
    background_tasks: BackgroundTasks
) -> BotGameResponse:
    """
    Start a new bot vs bot game.

    The game runs in the background and can be spectated in real-time.
    """
    # Create session
    session = await session_manager.create_session(
        mode="bot_vs_bot",
        game_mode=request.mode
    )

    # Add bot players
    bot1_display = request.bot1_name or (request.bot1_model if request.bot1_model else "Bot 1")
    bot2_display = request.bot2_name or (request.bot2_model if request.bot2_model else "Bot 2")

    bot1_id = session.add_player(bot1_display, is_ai=True)
    bot2_id = session.add_player(bot2_display, is_ai=True)

    # Configure replay + pacing for spectating/replay.
    session.record_actions_for_replay = True
    session.spectator_delay_ms = request.delay_ms
    session.max_replay_frames = request.max_replay_frames

    # Configure bot brains.
    session.ai_profiles_by_player[bot1_id] = {
        "brain": request.bot1_brain.value,
        "difficulty": request.bot1_difficulty.value,
        "model": request.bot1_model,
        "temperature": request.bot1_temperature,
        "record_prompts": request.record_prompts,
    }
    session.ai_profiles_by_player[bot2_id] = {
        "brain": request.bot2_brain.value,
        "difficulty": request.bot2_difficulty.value,
        "model": request.bot2_model,
        "temperature": request.bot2_temperature,
        "record_prompts": request.record_prompts,
    }

    # Fast preflight for API-based bots (avoid starting a match that will wedge).
    if request.bot1_brain.value == "openai" or request.bot2_brain.value == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            raise HTTPException(status_code=400, detail="OPENAI_API_KEY not set")
    if request.bot1_brain.value == "anthropic" or request.bot2_brain.value == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise HTTPException(status_code=400, detail="ANTHROPIC_API_KEY not set")

    # Build decks
    if request.bot1_deck_id:
        bot1_deck = get_deck_cards(request.bot1_deck_id)
    elif request.bot1_deck:
        bot1_deck = get_cards_by_names(request.bot1_deck)
    else:
        bot1_deck = get_default_deck()

    if request.bot2_deck_id:
        bot2_deck = get_deck_cards(request.bot2_deck_id)
    elif request.bot2_deck:
        bot2_deck = get_cards_by_names(request.bot2_deck)
    else:
        bot2_deck = get_default_deck()

    if not bot1_deck:
        raise HTTPException(status_code=400, detail="bot1 deck is empty (invalid deck_id or card list)")
    if not bot2_deck:
        raise HTTPException(status_code=400, detail="bot2 deck is empty (invalid deck_id or card list)")

    # Setup Hearthstone heroes if in Hearthstone mode
    if request.mode == "hearthstone":
        from src.cards.hearthstone.heroes import HEROES
        from src.cards.hearthstone.hero_powers import HERO_POWERS
        from src.cards.hearthstone.decks import get_deck_for_hero
        import random

        # Get players from game
        player_ids = list(session.game.state.players.keys())
        if len(player_ids) >= 2:
            # Randomly select two different hero classes
            available_heroes = ["Mage", "Warrior", "Hunter", "Paladin", "Priest", "Rogue", "Shaman", "Warlock", "Druid"]
            hero1_class = random.choice(available_heroes)
            available_heroes.remove(hero1_class)
            hero2_class = random.choice(available_heroes)

            # Setup heroes for both players
            p1 = session.game.state.players[player_ids[0]]
            p2 = session.game.state.players[player_ids[1]]

            session.game.setup_hearthstone_player(p1, HEROES[hero1_class], HERO_POWERS[hero1_class])
            session.game.setup_hearthstone_player(p2, HEROES[hero2_class], HERO_POWERS[hero2_class])

            # Use class-appropriate decks
            bot1_deck = get_deck_for_hero(hero1_class)
            bot2_deck = get_deck_for_hero(hero2_class)

    # Add cards to libraries
    session.add_cards_to_deck(bot1_id, bot1_deck)
    session.add_cards_to_deck(bot2_id, bot2_deck)

    # Store in active games
    active_bot_games[session.id] = session

    # Start game in background with delay
    background_tasks.add_task(
        run_bot_game,
        session
    )

    return BotGameResponse(
        game_id=session.id,
        status="running"
    )


async def run_bot_game(session: GameSession):
    """Background task to run a bot vs bot game."""
    try:
        await session.start_game()

        while not session.is_finished:
            # Run one turn (priority actions inside are paced via session.spectator_delay_ms)
            await session.game.turn_manager.run_turn()

            # In Hearthstone mode, the priority system loop is bypassed so
            # _on_action_processed never fires.  Record a frame per turn
            # so that replays capture the game progression.
            if session.game.state.game_mode == "hearthstone" and session.record_actions_for_replay:
                active = session.game.get_active_player()
                session._record_frame(action={
                    "kind": "action_processed",
                    "player_id": active,
                    "player_name": session.player_names.get(active, active or ""),
                    "action_type": "END_TURN",
                })

            # Check game over
            if session.game.is_game_over():
                session.is_finished = True
                session.winner_id = session.game.get_winner()
                break

            # Safety limit
            if session.game.turn_manager.turn_number > 100:
                session.is_finished = True
                break

        # Store completed replay
        completed_replays[session.id] = ReplayResponse(
            game_id=session.id,
            winner=session.winner_id,
            total_turns=session.game.turn_manager.turn_number,
            frames=session.replay_frames
        )

    except Exception as e:
        print(f"Bot game error: {e}")
        session.is_finished = True


@router.get("/{game_id}/state", response_model=GameStateResponse)
async def get_bot_game_state(game_id: str) -> GameStateResponse:
    """
    Get current state of a bot game for spectating.
    """
    session = active_bot_games.get(game_id)
    if not session:
        # Check if it's a completed game
        if game_id in completed_replays:
            replay = completed_replays[game_id]
            if replay.frames:
                return GameStateResponse(**replay.frames[-1].state)

        raise HTTPException(status_code=404, detail="Game not found")

    return session.get_client_state()


@router.get("/{game_id}/replay", response_model=ReplayResponse)
async def get_replay(game_id: str, since: int = 0, limit: int = 5000) -> ReplayResponse:
    """
    Get replay data for a bot game.

    - For running games, returns frames recorded so far.
    - For finished games, returns frames from the completed replay.

    Query params:
        since: Frame index to start from (0-based)
        limit: Max frames to return (paging)
    """
    since = max(0, since)
    limit = max(1, min(5000, limit))

    # Completed replay
    if game_id in completed_replays:
        replay = completed_replays[game_id]
        return ReplayResponse(
            game_id=replay.game_id,
            winner=replay.winner,
            total_turns=replay.total_turns,
            frames=replay.frames[since:since + limit],
        )

    # Check active games
    session = active_bot_games.get(game_id)
    if session:
        # If the game finished but wasn't persisted yet, persist it now.
        if session.is_finished and game_id not in completed_replays:
            completed_replays[game_id] = ReplayResponse(
                game_id=session.id,
                winner=session.winner_id,
                total_turns=session.game.turn_manager.turn_number,
                frames=session.replay_frames,
            )

        return ReplayResponse(
            game_id=session.id,
            winner=session.winner_id,
            total_turns=session.game.turn_manager.turn_number if session.is_started else 0,
            frames=session.replay_frames[since:since + limit],
        )

    raise HTTPException(status_code=404, detail="Game not found")


@router.get("/{game_id}/status")
async def get_bot_game_status(game_id: str) -> dict:
    """
    Get the status of a bot game.
    """
    session = active_bot_games.get(game_id)

    if session:
        return {
            "game_id": game_id,
            "status": "finished" if session.is_finished else "running",
            "turn": session.game.turn_manager.turn_number if session.is_started else 0,
            "winner": session.winner_id
        }

    if game_id in completed_replays:
        replay = completed_replays[game_id]
        return {
            "game_id": game_id,
            "status": "finished",
            "turn": replay.total_turns,
            "winner": replay.winner
        }

    raise HTTPException(status_code=404, detail="Game not found")


@router.get("/list")
async def list_bot_games(
    status: Optional[str] = None
) -> dict:
    """
    List all bot games.

    Filter by status: 'running', 'finished', or None for all.
    """
    games = []

    # Active games
    for game_id, session in active_bot_games.items():
        if status == "finished" and not session.is_finished:
            continue
        if status == "running" and session.is_finished:
            continue

        games.append({
            "game_id": game_id,
            "status": "finished" if session.is_finished else "running",
            "turn": session.game.turn_manager.turn_number if session.is_started else 0,
            "winner": session.winner_id
        })

    # Completed replays not in active games
    for game_id, replay in completed_replays.items():
        if game_id not in active_bot_games:
            if status == "running":
                continue

            games.append({
                "game_id": game_id,
                "status": "finished",
                "turn": replay.total_turns,
                "winner": replay.winner
            })

    return {"games": games, "total": len(games)}


@router.delete("/{game_id}")
async def delete_bot_game(game_id: str) -> dict:
    """
    Delete a bot game and its replay.
    """
    deleted = False

    if game_id in active_bot_games:
        session = active_bot_games[game_id]
        session.is_finished = True
        del active_bot_games[game_id]
        await session_manager.remove_session(game_id)
        deleted = True

    if game_id in completed_replays:
        del completed_replays[game_id]
        deleted = True

    if not deleted:
        raise HTTPException(status_code=404, detail="Game not found")

    return {"status": "deleted", "game_id": game_id}
