"""
Match Routes

Endpoints for creating and managing game matches.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from typing import Optional
import asyncio
import os

from ..session import session_manager, GameSession
from ..models import (
    CreateMatchRequest, CreateMatchResponse,
    PlayerActionRequest, ActionResultResponse,
    GameStateResponse,
    SubmitChoiceRequest, ChoiceResultResponse,
    ReplayResponse,
)
from .. import replay_archive

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


@router.get("/ygo-decks")
async def list_ygo_decks() -> dict:
    """List available Yu-Gi-Oh! decks."""
    from src.cards.yugioh.ygo_optimized import YGO_OPTIMIZED_DECKS
    decks = []
    for deck_id, info in YGO_OPTIMIZED_DECKS.items():
        strat = info.get('strategy', {})
        decks.append({
            "id": deck_id,
            "name": strat.get('name', deck_id),
            "archetype": strat.get('archetype', ''),
            "description": strat.get('description', ''),
            "is_optimized": True,
        })
    # Add legacy decks
    for deck_id, name in [('yugi', 'Yugi Starter'), ('kaiba', 'Kaiba Starter'),
                          ('warrior', 'Warrior Starter'), ('spellcaster', 'Spellcaster Starter')]:
        decks.append({
            "id": deck_id,
            "name": name,
            "archetype": "Starter",
            "description": f"Classic {name} deck",
            "is_optimized": False,
        })
    return {"decks": decks}


def _is_internal_request(request: Request) -> bool:
    """Return True if the request originated inside the container/host.

    Container-internal Ultra agents poll over 127.0.0.1, so localhost
    matches the production path. A shared-secret backdoor via
    ``X-Internal-Auth`` lets external orchestrators opt in if
    HYPERDRAFT_INTERNAL_SECRET is configured.
    """
    import hmac as _hmac

    client = request.client
    if client is not None and client.host in ("127.0.0.1", "::1", "localhost"):
        return True
    expected = os.environ.get("HYPERDRAFT_INTERNAL_SECRET", "").strip()
    if expected:
        provided = request.headers.get("x-internal-auth", "").strip()
        if provided and _hmac.compare_digest(provided, expected):
            return True
    return False


@router.get("/ultra-pending")
async def list_ultra_pending(request: Request) -> dict:
    """List matches awaiting an ultra-AI move from an external agent.

    Returns matches where:
      - the AI seat's difficulty is "ultra"
      - the AI is the current active player (i.e. it's the AI's turn)
      - the match is still active (not finished)
      - the session is registered with the active session manager

    Auth: localhost-only by default (container-internal agents poll over
    127.0.0.1). Set HYPERDRAFT_INTERNAL_SECRET to also accept calls bearing
    a matching ``X-Internal-Auth`` header.
    """
    if not _is_internal_request(request):
        raise HTTPException(status_code=404, detail="Not found")
    return _list_external_ultra_pending()


@router.get("/codex-pending")
async def list_codex_pending(request: Request) -> dict:
    """List pending Ultra matches whose configured external runner is Codex."""
    if not _is_internal_request(request):
        raise HTTPException(status_code=404, detail="Not found")
    return _list_external_ultra_pending(agent_runner="codex")


def _list_external_ultra_pending(agent_runner: Optional[str] = None) -> dict:
    pending: list[dict] = []
    for match_id, session in session_manager.sessions.items():
        try:
            if session.is_finished:
                continue
            if not session.has_ultra_ai:
                continue

            game = session.game
            if game.is_game_over():
                continue

            try:
                active_player = game.get_active_player()
            except Exception:
                active_player = None
            if not active_player:
                continue

            ultra_ids = session.ultra_ai_player_ids
            if active_player not in ultra_ids:
                continue
            ai_player_id = active_player
            resolved_runner = session.external_agent_runner(ai_player_id)
            if agent_runner and resolved_runner != agent_runner:
                continue

            human_player_id = next(
                (pid for pid in session.player_ids if pid in session.human_players),
                None,
            )

            tm = getattr(game, "turn_manager", None)
            turn_number = int(getattr(tm, "turn_number", 0) or 0)

            phase_name: Optional[str] = None
            phase_obj = getattr(tm, "phase", None)
            if phase_obj is not None:
                phase_name = getattr(phase_obj, "name", None) or str(phase_obj)
            if phase_name is None:
                # Mode-specific phase fallbacks (finance/depths/ygo)
                for attr in ("fin_turn_state", "depths_turn_state", "ygo_turn_state"):
                    sub = getattr(tm, attr, None)
                    sub_phase = getattr(sub, "phase", None) if sub is not None else None
                    if sub_phase is not None:
                        phase_name = getattr(sub_phase, "name", None) or str(sub_phase)
                        break

            game_mode = getattr(game.state, "game_mode", None) or "mtg"

            pending.append({
                "match_id": match_id,
                "game_mode": game_mode,
                "ai_player_id": ai_player_id,
                "human_player_id": human_player_id or "",
                "agent_runner": resolved_runner,
                "turn_number": turn_number,
                "phase": phase_name or "",
            })
        except Exception:
            # Defensive: never let one broken session break the listing.
            continue

    return {"pending": pending}


def _resolve_ultra_agent(request: CreateMatchRequest) -> tuple[str, Optional[str]]:
    configured = request.ultra_agent or os.environ.get("HYPERDRAFT_ULTRA_AGENT") or "claude"
    runner = str(configured).strip().lower()
    if runner not in {"claude", "codex"}:
        runner = "claude"
    model = request.ultra_model or os.environ.get("HYPERDRAFT_ULTRA_MODEL")
    return runner, model


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
        ai_difficulty=request.ai_difficulty.value,
        game_mode=request.game_mode,
    )

    # Always record replay frames on match sessions — needed for the
    # /api/match/:matchId/replay endpoint + post-game archive. Cost is
    # ~2-5 MB per long match in memory, capped at 8000 frames; cleanup
    # happens when session_manager evicts the session or on container
    # restart. The archive (storage/replays/...) is the durable copy.
    session.record_actions_for_replay = True
    session.max_replay_frames = 8000

    # Store variant for client display
    if request.variant:
        session.display_variant = request.variant

    # Add players. bot_vs_bot does NOT seat a human — both seats are AI;
    # the supervisor passes a player_name like "Demo Spectator (pokemon)"
    # for display labeling but it shouldn't actually be in the game.
    # Pre-Phase-4 this branch always seated a human first, which made
    # Pokémon / Yu-Gi-Oh / etc. turn managers set up human-vs-AI even
    # for the "watch live" demo. Fix: only seat a human when the mode
    # actually has one.
    if request.mode != "bot_vs_bot":
        human_id = session.add_player(request.player_name, is_ai=False)
    else:
        human_id = ""  # no human seat in bot_vs_bot

    # Add AI player for human vs bot mode
    if request.mode == "human_vs_bot":
        ai_difficulty = request.ai_difficulty.value
        ultra_agent, ultra_model = _resolve_ultra_agent(request)
        if ai_difficulty == "ultra":
            ai_name = "Codex Ultra" if ultra_agent == "codex" else "Claude Ultra"
        else:
            ai_name = "AI Opponent"
        ai_id = session.add_player(ai_name, is_ai=True)
        session.ai_profiles_by_player[ai_id] = {
            "brain": "external" if ai_difficulty == "ultra" else "heuristic",
            "difficulty": ai_difficulty,
            "agent_runner": ultra_agent,
            "model": ultra_model,
        }
    elif request.mode == "bot_vs_bot":
        ai_difficulty = request.ai_difficulty.value
        ultra_agent, ultra_model = _resolve_ultra_agent(request)
        if ai_difficulty == "ultra":
            label_a = "Codex Ultra A" if ultra_agent == "codex" else "Claude Ultra A"
            label_b = "Codex Ultra B" if ultra_agent == "codex" else "Claude Ultra B"
        else:
            label_a, label_b = "AI 1", "AI 2"
        ai_id = session.add_player(label_a, is_ai=True)
        ai2_id = session.add_player(label_b, is_ai=True)
        for seat in (ai_id, ai2_id):
            session.ai_profiles_by_player[seat] = {
                "brain": "external" if ai_difficulty == "ultra" else "heuristic",
                "difficulty": ai_difficulty,
                "agent_runner": ultra_agent,
                "model": ultra_model,
            }
    else:
        ai_id = None
        ai2_id = None

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

    elif request.game_mode == "minecraft":
        from src.cards.minecraft import MINECRAFT_STARTER_DECKS
        import random

        deck_keys = list(MINECRAFT_STARTER_DECKS.keys())
        human_deck_id = request.player_deck_id if request.player_deck_id in MINECRAFT_STARTER_DECKS else "builder"
        ai_deck_id = request.ai_deck_id if request.ai_deck_id in MINECRAFT_STARTER_DECKS else "raider"
        if request.mode == "bot_vs_bot":
            random.shuffle(deck_keys)
            human_deck_id, ai_deck_id = deck_keys[0], deck_keys[1]

        for pid in session.player_ids:
            player = session.game.state.players.get(pid)
            if player:
                session.game.setup_minecraft_player(player, [])

        session.add_cards_to_deck(human_id, MINECRAFT_STARTER_DECKS[human_deck_id]())
        if request.mode == "human_vs_bot" and ai_id:
            session.add_cards_to_deck(ai_id, MINECRAFT_STARTER_DECKS[ai_deck_id]())
        elif request.mode == "bot_vs_bot":
            session.add_cards_to_deck(ai_id, MINECRAFT_STARTER_DECKS[human_deck_id]())
            if ai2_id:
                session.add_cards_to_deck(ai2_id, MINECRAFT_STARTER_DECKS[ai_deck_id]())

    elif request.game_mode == "scp":
        from src.cards.scp import SCP_STARTER_DECKS
        import random

        deck_keys = ["secure_contain_research", "keter_risk", "veil_control"]
        human_deck_id = request.player_deck_id if request.player_deck_id in SCP_STARTER_DECKS else "secure_contain_research"
        ai_deck_id = request.ai_deck_id if request.ai_deck_id in SCP_STARTER_DECKS else "keter_risk"
        if request.mode == "bot_vs_bot":
            random.shuffle(deck_keys)
            human_deck_id, ai_deck_id = deck_keys[0], deck_keys[1]

        for pid in session.player_ids:
            player = session.game.state.players.get(pid)
            if player:
                session.game.setup_scp_player(player, [])

        session.add_cards_to_deck(human_id, SCP_STARTER_DECKS[human_deck_id]())
        if request.mode == "human_vs_bot" and ai_id:
            session.add_cards_to_deck(ai_id, SCP_STARTER_DECKS[ai_deck_id]())
        elif request.mode == "bot_vs_bot":
            session.add_cards_to_deck(ai_id, SCP_STARTER_DECKS[human_deck_id]())
            if ai2_id:
                session.add_cards_to_deck(ai2_id, SCP_STARTER_DECKS[ai_deck_id]())

    elif request.game_mode == "yugioh":
        # Yu-Gi-Oh! mode - support deck selection via deck IDs
        from src.cards.yugioh.ygo_classic import (
            YUGI_DECK, YUGI_EXTRA_DECK, KAIBA_DECK, KAIBA_EXTRA_DECK,
        )
        from src.cards.yugioh.ygo_starter import (
            WARRIOR_DECK, WARRIOR_EXTRA_DECK, SPELLCASTER_DECK, SPELLCASTER_EXTRA_DECK,
        )
        from src.cards.yugioh.ygo_optimized import YGO_OPTIMIZED_DECKS
        import random

        # All available decks: optimized + classic + starter
        all_decks = {
            'goat_control': (YGO_OPTIMIZED_DECKS['goat_control']['deck'],
                             YGO_OPTIMIZED_DECKS['goat_control']['extra'],
                             YGO_OPTIMIZED_DECKS['goat_control']['strategy']),
            'monarch_control': (YGO_OPTIMIZED_DECKS['monarch_control']['deck'],
                                YGO_OPTIMIZED_DECKS['monarch_control']['extra'],
                                YGO_OPTIMIZED_DECKS['monarch_control']['strategy']),
            'chain_burn': (YGO_OPTIMIZED_DECKS['chain_burn']['deck'],
                           YGO_OPTIMIZED_DECKS['chain_burn']['extra'],
                           YGO_OPTIMIZED_DECKS['chain_burn']['strategy']),
            'dragon_beatdown': (YGO_OPTIMIZED_DECKS['dragon_beatdown']['deck'],
                                YGO_OPTIMIZED_DECKS['dragon_beatdown']['extra'],
                                YGO_OPTIMIZED_DECKS['dragon_beatdown']['strategy']),
            'yugi': (YUGI_DECK, YUGI_EXTRA_DECK, None),
            'kaiba': (KAIBA_DECK, KAIBA_EXTRA_DECK, None),
            'warrior': (WARRIOR_DECK, WARRIOR_EXTRA_DECK, None),
            'spellcaster': (SPELLCASTER_DECK, SPELLCASTER_EXTRA_DECK, None),
        }

        deck_keys = list(all_decks.keys())

        def resolve_ygo_deck(deck_id):
            if deck_id and deck_id in all_decks:
                return all_decks[deck_id]
            # Random from all
            return all_decks[random.choice(deck_keys)]

        p1_main, p1_extra, p1_strategy = resolve_ygo_deck(request.player_deck_id)
        p2_main, p2_extra, p2_strategy = resolve_ygo_deck(request.ai_deck_id)

        if request.mode == "human_vs_bot":
            # Human gets p1 deck, AI gets p2 deck + strategy
            for pid in session.player_ids:
                player = session.game.state.players.get(pid)
                if not player:
                    continue
                if pid == human_id:
                    session.game.setup_yugioh_player(player, p1_main, p1_extra)
                elif ai_id and pid == ai_id:
                    session.game.setup_yugioh_player(player, p2_main, p2_extra)
            if p2_strategy:
                session.ygo_ai_strategy = p2_strategy

        elif request.mode == "bot_vs_bot":
            # Bot 1 gets p1 deck, Bot 2 gets p2 deck
            bot_decks = [(p1_main, p1_extra, p1_strategy), (p2_main, p2_extra, p2_strategy)]
            for idx, pid in enumerate(session.player_ids):
                player = session.game.state.players.get(pid)
                if player and idx < len(bot_decks):
                    dm, de, _ = bot_decks[idx]
                    session.game.setup_yugioh_player(player, dm, de)
            # Use p1 strategy for the shared AI adapter (bot_vs_bot shares one adapter)
            strategy = p1_strategy or p2_strategy
            if strategy:
                session.ygo_ai_strategy = strategy

        else:
            # Fallback: set up all players with p1 deck
            for pid in session.player_ids:
                player = session.game.state.players.get(pid)
                if player:
                    session.game.setup_yugioh_player(player, p1_main, p1_extra)

    elif request.game_mode == "pokemon":
        # Pokemon TCG mode - use built-in starter decks
        from src.cards.pokemon.sv_starter import make_fire_deck, make_water_deck
        import random

        deck_options = [make_fire_deck, make_water_deck]
        random.shuffle(deck_options)

        human_deck = deck_options[0]()
        ai_deck_cards = deck_options[1]()

        # Setup Pokemon players (sets life=0, prizes_remaining=6)
        for pid in session.player_ids:
            player = session.game.state.players.get(pid)
            if player:
                session.game.setup_pokemon_player(player, [])

        session.add_cards_to_deck(human_id, human_deck)
        if request.mode == "human_vs_bot" and ai_id:
            session.add_cards_to_deck(ai_id, ai_deck_cards)
        elif request.mode == "bot_vs_bot":
            session.add_cards_to_deck(ai_id, ai_deck_cards)
            if ai2_id:
                session.add_cards_to_deck(ai2_id, deck_options[0]())

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
        # In bot_vs_bot mode human_id == "" (no human seat), so we resolve the
        # "primary" hero class from whichever seat is actually populated.
        # Indexing hero_class_by_player[""] used to raise KeyError and prevent
        # the HS demo match from ever being created (zero HS replays in prod).
        primary_pid = human_id or ai_id or (ai2_id if ai2_id else next(iter(session.player_ids), ""))
        primary_hero_class = hero_class_by_player.get(primary_pid)
        primary_default_deck = get_deck_for_hero(primary_hero_class) if primary_hero_class else []

        player_deck = (
            get_cards_by_names(request.player_deck)
            if request.player_deck
            else primary_default_deck
        )
        if not player_deck:
            player_deck = primary_default_deck

        ai_hero_class = hero_class_by_player.get(ai_id, primary_hero_class)
        ai_default_deck = get_deck_for_hero(ai_hero_class) if ai_hero_class else primary_default_deck
        ai_deck = (
            get_cards_by_names(request.ai_deck)
            if request.ai_deck
            else ai_default_deck
        )
        if not ai_deck:
            ai_deck = ai_default_deck

        if human_id:
            session.add_cards_to_deck(human_id, player_deck)

        if request.mode == "human_vs_bot" and ai_id:
            session.add_cards_to_deck(ai_id, ai_deck)
        elif request.mode == "bot_vs_bot":
            if ai_id:
                session.add_cards_to_deck(ai_id, ai_deck)
            if ai2_id:
                ai2_hero_class = hero_class_by_player.get(ai2_id, primary_hero_class)
                ai2_deck = (
                    get_deck_for_hero(ai2_hero_class) if ai2_hero_class else ai_deck
                )
                session.add_cards_to_deck(ai2_id, ai2_deck)
    elif request.game_mode == "finance":
        from src.cards.finance import FINANCE_DECKS
        import random

        deck_keys = list(FINANCE_DECKS.keys())
        human_deck_key = (
            request.player_deck_id if request.player_deck_id in FINANCE_DECKS
            else "FINA_high_frequency"
        )
        ai_deck_key = (
            request.ai_deck_id if request.ai_deck_id in FINANCE_DECKS
            else "FINA_quant"
        )
        if request.mode == "bot_vs_bot":
            random.shuffle(deck_keys)
            human_deck_key, ai_deck_key = deck_keys[0], deck_keys[1]

        for pid in session.player_ids:
            player = session.game.state.players.get(pid)
            if player:
                session.game.setup_finance_player(player)

        session.add_cards_to_deck(human_id, FINANCE_DECKS[human_deck_key]())
        if request.mode == "human_vs_bot" and ai_id:
            session.add_cards_to_deck(ai_id, FINANCE_DECKS[ai_deck_key]())
        elif request.mode == "bot_vs_bot":
            session.add_cards_to_deck(ai_id, FINANCE_DECKS[human_deck_key]())
            if ai2_id:
                session.add_cards_to_deck(ai2_id, FINANCE_DECKS[ai_deck_key]())

    elif request.game_mode == "cats":
        # Cats: trick-taking + pile-building. Decks are 30-card commander+main
        # tuples in CATS_DECKS. The cats engine uses its own setup_cats_player
        # primitive (shuffles deck, draws CATS_HAND_SIZE, installs commander).
        from src.cards.cats.CATS.decks import CATS_DECKS
        from src.engine.cats import setup_cats_player
        import random

        deck_keys = list(CATS_DECKS.keys())
        default_human = "Couch Empire"
        default_ai = "Naptime Tyrants"

        human_deck_key = (
            request.player_deck_id if request.player_deck_id in CATS_DECKS
            else default_human
        )
        ai_deck_key = (
            request.ai_deck_id if request.ai_deck_id in CATS_DECKS
            else default_ai
        )
        if request.mode == "bot_vs_bot":
            shuffled = list(deck_keys)
            random.shuffle(shuffled)
            human_deck_key, ai_deck_key = shuffled[0], shuffled[1]

        # Build seat assignments. In human_vs_bot mode the human is seat 0
        # so they're the round-1 lead-rotation anchor (player_ids[0]).
        seat_keys: dict[str, str] = {}
        for idx, pid in enumerate(session.player_ids):
            if pid == human_id:
                seat_keys[pid] = human_deck_key
            elif ai_id and pid == ai_id:
                seat_keys[pid] = ai_deck_key
            elif ai2_id and pid == ai2_id:
                # bot-vs-bot second seat
                seat_keys[pid] = ai_deck_key
            else:
                # Fallback for any unmapped seats — alternate decks.
                seat_keys[pid] = deck_keys[idx % len(deck_keys)]

        for pid, deck_key in seat_keys.items():
            commander, deck_cards = CATS_DECKS[deck_key]
            setup_cats_player(session.game.state, pid, deck_cards, commander=commander)
            session.deck_card_defs_by_player.setdefault(pid, []).extend(deck_cards)

    elif request.game_mode == "depths":
        from src.cards.depths.submarine_fleet.decks import SUBS_STARTER_DECKS, make_subs_flagship
        import random

        DEPTHS_DECK_KEYS = ["SUBS_wolfpack", "SUBS_silent_hunter", "SUBS_carrier", "SUBS_deep_strike"]
        human_deck_key = (
            request.player_deck_id if request.player_deck_id in SUBS_STARTER_DECKS
            else "SUBS_wolfpack"
        )
        ai_deck_key = (
            request.ai_deck_id if request.ai_deck_id in SUBS_STARTER_DECKS
            else "SUBS_silent_hunter"
        )
        if request.mode == "bot_vs_bot":
            keys = list(DEPTHS_DECK_KEYS)
            random.shuffle(keys)
            human_deck_key, ai_deck_key = keys[0], keys[1]

        # Build flagships and decks, then call setup_depths_player via turn manager
        from src.engine.depths import setup_depths_player

        for pid in session.player_ids:
            player = session.game.state.players.get(pid)
            if player is None:
                continue
            flagship_def = make_subs_flagship(f"{session.player_names.get(pid, 'Player')} Flagship")
            if pid == human_id:
                deck = SUBS_STARTER_DECKS[human_deck_key]()
            else:
                deck = SUBS_STARTER_DECKS[ai_deck_key]()
            setup_depths_player(session.game, player, deck, flagship_def)

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

    # Ultra mode: spawn the external-agent CLI as a background subprocess.
    # In production the container hosts this; the launcher script's stdout
    # is captured to ``storage/ultra-agent/<MATCH_ID>.log`` for operators
    # to tail. Both human_vs_bot AND bot_vs_bot (spectator demo, Phase 4)
    # fire this path when ai_difficulty==ultra; bot_vs_bot spawns one
    # subprocess per AI seat.
    if request.ai_difficulty.value == "ultra":
        ultra_agent, ultra_model = _resolve_ultra_agent(request)
        if request.mode == "human_vs_bot" and ai_id:
            await _spawn_ultra_subprocess(
                match_id=session.id,
                ai_player_id=ai_id,
                human_player_id=human_id,
                game_mode=request.game_mode,
                agent_runner=ultra_agent,
                agent_model=ultra_model,
            )
        elif request.mode == "bot_vs_bot" and ai_id and ai2_id:
            await _spawn_ultra_subprocess(
                match_id=session.id,
                ai_player_id=ai_id,
                human_player_id=ai2_id,  # opponent label for the prompt; both are bots
                game_mode=request.game_mode,
                agent_runner=ultra_agent,
                agent_model=ultra_model,
            )
            await _spawn_ultra_subprocess(
                match_id=session.id,
                ai_player_id=ai2_id,
                human_player_id=ai_id,
                game_mode=request.game_mode,
                agent_runner=ultra_agent,
                agent_model=ultra_model,
            )

    return CreateMatchResponse(
        match_id=session.id,
        player_id=human_id,
        opponent_id=ai_id or "",
        status="created"
    )


# Registry of live ultra-agent subprocesses, keyed by (match_id, ai_player_id).
# Used by Phase 3 cleanup to reap zombies when a match ends mid-session. No
# concurrency cap is enforced — Claude Code seats spawn freely.
_active_ultra_subprocesses: dict[tuple[str, str], "object"] = {}
_ultra_spawn_lock = asyncio.Lock()


async def _spawn_ultra_subprocess(
    *,
    match_id: str,
    ai_player_id: str,
    human_player_id: str,
    game_mode: str,
    agent_runner: str = "claude",
    agent_model: Optional[str] = None,
) -> bool:
    """Spawn an external Ultra-agent CLI as a background subprocess.

    No terminal window is opened; stdout/stderr are redirected to
    ``storage/ultra-agent/<MATCH_ID>__<AI_PLAYER_ID>.log`` for operators
    to tail. The process inherits ``start_new_session=True`` so it's not
    killed when the FastAPI worker recycles.

    Returns True if spawned, False if the launcher is missing. Failure must
    NOT break match creation — the user can still play (the AI seat just
    sits idle until manually relaunched).
    """
    import subprocess
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[3]
    runner = str(agent_runner or "claude").strip().lower()
    if runner not in {"claude", "codex"}:
        runner = "claude"
    launcher_name = "launch_codex_agent.sh" if runner == "codex" else "launch_ultra_agent.sh"
    launcher = project_root / "scripts" / launcher_name
    if not launcher.exists():
        print(f"[ultra:{runner}] launcher not found: {launcher}", flush=True)
        return False

    log_dir = project_root / "storage" / "ultra-agent"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{match_id}__{ai_player_id}.log"

    env = os.environ.copy()
    env.update({
        "MATCH_ID": match_id,
        "AI_PLAYER_ID": ai_player_id,
        "HUMAN_PLAYER_ID": human_player_id,
        "GAME_MODE": game_mode,
        "ULTRA_AGENT": runner,
    })
    if agent_model:
        env["ULTRA_MODEL"] = agent_model

    # Serialize Popen + registry-insert so concurrent create_match calls
    # don't race on the registry. No cap is enforced.
    async with _ultra_spawn_lock:
        try:
            log_fh = open(log_path, "ab")
            proc = subprocess.Popen(
                ["bash", str(launcher)],
                cwd=str(project_root),
                env=env,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[ultra:{runner}] spawn failed: {exc}", flush=True)
            return False

        key = (match_id, ai_player_id)
        _active_ultra_subprocesses[key] = proc
    print(
        f"[ultra:{runner}] spawned subprocess pid={proc.pid} for match {match_id} "
        f"seat {ai_player_id} ({game_mode}); log={log_path}",
        flush=True,
    )

    # Reap on exit in a background task so the registry doesn't grow unbounded.
    async def _reap_when_done():
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, proc.wait)
        finally:
            _active_ultra_subprocesses.pop(key, None)

    asyncio.create_task(_reap_when_done())
    return True


def kill_match_subprocesses(match_id: str) -> int:
    """SIGTERM all ultra subprocesses spawned for ``match_id``.

    The Popen used ``start_new_session=True``, so each subprocess heads its
    own process group; killing the group reaps the bash launcher + claude
    CLI together. Returns the number of subprocesses signalled.
    """
    import os
    import signal

    count = 0
    for (m_id, _seat), proc in list(_active_ultra_subprocesses.items()):
        if m_id != match_id:
            continue
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
            count += 1
        except (ProcessLookupError, PermissionError):
            # Process already exited or no permission — the reap task will
            # clean up the registry entry. Don't crash the caller.
            pass
    return count


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
    finally:
        # Archive the replay on game-end so it survives container restarts.
        # No-op if the game crashed before any frames were recorded.
        try:
            if session.is_finished and session.replay_frames:
                payload = {
                    "game_id": session.id,
                    "match_id": session.id,
                    "game_mode": getattr(session.game.state, "game_mode", None),
                    "winner": session.winner_id,
                    "total_turns": (
                        session.game.turn_manager.turn_number
                        if hasattr(session.game, "turn_manager") and session.game.turn_manager
                        else 0
                    ),
                    "frames": [f.model_dump() for f in session.replay_frames],
                }
                replay_archive.archive_match(session.id, payload)
        except Exception as arch_err:  # noqa: BLE001
            print(f"replay archive on game-end failed for {session.id}: {arch_err}")


@router.get("/replays/list")
async def list_replays(limit: int = 30) -> dict:
    """List recently archived match replays.

    Backed by replay_archive's index.json. Used by the /replays page on
    the frontend to render a roster of past Claude-vs-Claude matches.
    """
    entries = replay_archive.list_archives(limit=max(1, min(200, limit)))
    return {"replays": entries, "total": len(entries)}


@router.get("/{match_id}/replay", response_model=ReplayResponse)
async def get_match_replay(
    match_id: str,
    since: int = 0,
    limit: int = 8000,
) -> ReplayResponse:
    """Return the replay frames for a match.

    Resolution order:
      1. Live session in session_manager (running OR just-finished)
      2. Persisted archive at storage/replays/match-<id>.json.gz

    ``since`` / ``limit`` paginate the frames so the frontend can
    progressively fetch as the player scrubs.
    """
    since = max(0, since)
    limit = max(1, min(8000, limit))

    session = session_manager.get_session(match_id)
    if session is not None:
        total = len(session.replay_frames)
        return ReplayResponse(
            game_id=session.id,
            winner=session.winner_id,
            total_turns=(
                session.game.turn_manager.turn_number
                if session.is_started and hasattr(session.game, "turn_manager") and session.game.turn_manager
                else 0
            ),
            frames=session.replay_frames[since : since + limit],
        )

    archived = replay_archive.load_archive(match_id)
    if archived is not None:
        frames = archived.get("frames") or []
        return ReplayResponse(
            game_id=archived.get("game_id") or match_id,
            winner=archived.get("winner"),
            total_turns=archived.get("total_turns") or 0,
            frames=frames[since : since + limit],
        )

    raise HTTPException(status_code=404, detail="Match not found")


@router.get("/{match_id}/replay/manifest")
async def get_match_replay_manifest(match_id: str) -> dict:
    """Compact index of frame -> (turn, phase) for scrubber labelling."""
    session = session_manager.get_session(match_id)
    frames_iter: list = []
    if session is not None:
        frames_iter = list(session.replay_frames)
        total_frames = len(frames_iter)
        is_complete = session.is_finished
        game_mode = getattr(session.game.state, "game_mode", None)
    else:
        archived = replay_archive.load_archive(match_id)
        if archived is None:
            raise HTTPException(status_code=404, detail="Match not found")
        frames_iter = archived.get("frames") or []
        total_frames = len(frames_iter)
        is_complete = True
        game_mode = archived.get("game_mode")

    manifest: list[dict] = []
    last_turn: Optional[int] = None
    last_phase: Optional[str] = None
    for idx, frame in enumerate(frames_iter):
        if hasattr(frame, "model_dump"):
            f = frame.model_dump()
        else:
            f = frame
        turn = f.get("turn")
        phase = f.get("phase")
        if turn != last_turn or phase != last_phase:
            manifest.append({"frame": idx, "turn": turn, "phase": phase})
            last_turn = turn
            last_phase = phase

    return {
        "match_id": match_id,
        "game_mode": game_mode,
        "total_frames": total_frames,
        "is_complete": is_complete,
        "marks": manifest,
    }


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
