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
from src.cards.set_registry import get_cards_in_set, get_sets_for_card

# Deck imports
from src.decks import STANDARD_DECKS, ALL_DECKS, get_deck, get_random_deck, load_deck

router = APIRouter(prefix="/match", tags=["match"])

_CARD_REF_SEP = "::"


def _parse_card_ref(ref: str) -> tuple[Optional[str], str]:
    """
    Parse a card reference.

    Accepted:
    - "Card Name" -> (None, "Card Name")  (defaults to MTG domain)
    - "TMH::Chrono-Berserker" -> ("TMH", "Chrono-Berserker")
    """
    raw = (ref or "").strip()
    if _CARD_REF_SEP in raw:
        domain, name = raw.split(_CARD_REF_SEP, 1)
        domain = domain.strip() or None
        name = name.strip()
        return domain, name
    return None, raw


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

    # `load_deck` can resolve custom-card domains via set_registry when deck entries
    # specify `DeckEntry.domain`. For MTG cards, use the canonical ALL_CARDS registry.
    return load_deck(ALL_CARDS, deck)


def get_cards_by_names(card_names: list[str]) -> list:
    """
    Get cards by a list of card names.

    Returns list of CardDefinition objects.
    """
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

        # Unqualified fallback: if the card isn't in MTG, allow an unambiguous
        # lookup by set code (covers many custom-only names without requiring a domain).
        if card_def is None and not domain:
            set_codes = get_sets_for_card(name)
            if len(set_codes) == 1:
                domain_cards = get_cards_in_set(set_codes[0])
                card_def = domain_cards.get(name) if domain_cards else None

        if card_def:
            cards.append(card_def)
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
        ai_difficulty=request.ai_difficulty,
        game_mode=request.game_mode,
    )

    # Store variant for client display
    if request.variant:
        session.display_variant = request.variant

    # Add human player
    human_id = session.add_player(request.player_name, is_ai=False)

    # Add AI player for human vs bot mode
    if request.mode == "human_vs_bot":
        ai_name = "Codex Ultra" if request.ai_difficulty.value == "ultra" else "AI Opponent"
        ai_id = session.add_player(ai_name, is_ai=True)
    elif request.mode == "bot_vs_bot":
        ai_id = session.add_player("AI 1", is_ai=True)
        ai2_id = session.add_player("AI 2", is_ai=True)
    else:
        ai_id = None

    # === Variant setup (installs heroes, decks, global modifiers) ===
    if request.variant in {"stormrift", "riftclash", "frierenrift"}:
        if request.variant == "riftclash":
            from src.cards.hearthstone.riftclash import (
                RIFTCLASH_HEROES as variant_heroes,
                RIFTCLASH_HERO_POWERS as variant_hero_powers,
                RIFTCLASH_DECKS as variant_decks,
                install_riftclash_modifiers as install_variant_modifiers,
            )
        elif request.variant == "frierenrift":
            from src.cards.hearthstone.frierenrift import (
                FRIERENRIFT_HEROES as variant_heroes,
                FRIERENRIFT_HERO_POWERS as variant_hero_powers,
                FRIERENRIFT_DECKS as variant_decks,
                install_frierenrift_modifiers as install_variant_modifiers,
            )
        else:
            from src.cards.hearthstone.stormrift import (
                STORMRIFT_HEROES as variant_heroes,
                STORMRIFT_HERO_POWERS as variant_hero_powers,
                STORMRIFT_DECKS as variant_decks,
                install_stormrift_modifiers as install_variant_modifiers,
            )

        default_class = (
            "Pyromancer" if "Pyromancer" in variant_heroes
            else ("Frieren" if "Frieren" in variant_heroes else next(iter(variant_heroes.keys())))
        )
        human_class = request.hero_class if request.hero_class in variant_heroes else default_class
        ai_class = next((klass for klass in variant_heroes.keys() if klass != human_class), human_class)

        for pid in session.player_ids:
            player = session.game.state.players.get(pid)
            if not player:
                continue
            hero_class = human_class if pid == human_id else ai_class
            session.game.setup_hearthstone_player(
                player,
                variant_heroes[hero_class],
                variant_hero_powers[hero_class],
            )

        # Add variant decks
        human_deck = list(variant_decks[human_class])
        ai_deck_cards = list(variant_decks[ai_class])

        session.add_cards_to_deck(human_id, human_deck)
        if request.mode == "human_vs_bot" and ai_id:
            session.add_cards_to_deck(ai_id, ai_deck_cards)

        # Install variant global modifiers
        install_variant_modifiers(session.game)

    elif request.game_mode == "hearthstone":
        # Hearthstone matches need heroes + hero powers + 30-card class decks.
        from src.cards.hearthstone.heroes import HEROES
        from src.cards.hearthstone.hero_powers import HERO_POWERS
        from src.cards.hearthstone.decks import get_deck_for_hero
        import random

        hero_classes = [
            "Mage", "Warrior", "Hunter", "Paladin",
            "Priest", "Rogue", "Shaman", "Warlock", "Druid",
        ]
        random.shuffle(hero_classes)

        hero_class_by_player: dict[str, str] = {}
        for idx, pid in enumerate(session.player_ids):
            hero_class_by_player[pid] = hero_classes[idx % len(hero_classes)]

        # Ensure human and primary AI differ in human-vs-bot for better variety.
        if request.mode == "human_vs_bot" and ai_id:
            hero_class_by_player[human_id] = hero_classes[0]
            hero_class_by_player[ai_id] = hero_classes[1]

        for pid in session.player_ids:
            player = session.game.state.players.get(pid)
            hero_class = hero_class_by_player[pid]
            if not player:
                continue
            session.game.setup_hearthstone_player(
                player,
                HEROES[hero_class],
                HERO_POWERS[hero_class],
            )

        # We intentionally ignore MTG deck IDs in Hearthstone mode.
        player_deck = (
            get_cards_by_names(request.player_deck)
            if request.player_deck
            else get_deck_for_hero(hero_class_by_player[human_id])
        )
        if not player_deck:
            player_deck = get_deck_for_hero(hero_class_by_player[human_id])

        ai_deck = (
            get_cards_by_names(request.ai_deck)
            if request.ai_deck
            else get_deck_for_hero(hero_class_by_player.get(ai_id, hero_class_by_player[human_id]))
        )
        if not ai_deck:
            ai_deck = get_deck_for_hero(hero_class_by_player.get(ai_id, hero_class_by_player[human_id]))

        session.add_cards_to_deck(human_id, player_deck)

        if request.mode == "human_vs_bot" and ai_id:
            session.add_cards_to_deck(ai_id, ai_deck)
        elif request.mode == "bot_vs_bot":
            session.add_cards_to_deck(ai_id, ai_deck)
            ai2_deck = (
                get_deck_for_hero(hero_class_by_player.get(ai2_id, hero_class_by_player[human_id]))
                if ai2_id
                else ai_deck
            )
            if ai2_id:
                session.add_cards_to_deck(ai2_id, ai2_deck)
    else:
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

    if session.game.is_game_over():
        session.is_finished = True
        session.winner_id = session.game.get_winner()
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

    if session.game.is_game_over():
        session.is_finished = True
        session.winner_id = session.game.get_winner()
        raise HTTPException(status_code=400, detail="Game is finished")

    # Check there's actually a pending choice
    pending_choice = session.game.get_pending_choice()
    if not pending_choice:
        raise HTTPException(status_code=400, detail="No pending choice")

    # Submit the choice via the session so any waiting human action handler can unblock.
    success, message, events = await session.handle_choice(
        choice_id=request.choice_id,
        player_id=request.player_id,
        selected=request.selected,
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
