"""
Bot Game Routes

Endpoints for bot vs bot games and replays.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional
import os

from ..session import session_manager, GameSession, generate_id
from ..models import (
    StartBotGameRequest, BotGameResponse, BotGameStatus, BotGameListResponse,
    ReplayResponse, GameStateResponse
)


# --- WatchLive enrichment helpers ---------------------------------------
# These keep /list (and /status) lobby-ready without bloating the route
# bodies. Each is pure — no engine state mutation — so they're safe to
# call from a request handler.

# Pretty labels for the BotBrain values. Maps the enum value (stored on
# ai_profiles_by_player["brain"]) onto the chip text in WatchLive.
_BRAIN_LABELS = {
    "heuristic": "Heuristic",
    "openai": "GPT",
    "ollama": "Ollama",
    "claude_code": "Claude",
    "anthropic": "Claude",
}


def _format_player_label(session: GameSession, player_id: str) -> Optional[str]:
    """Compose '<brain_or_name> · <difficulty>' for a single seat.

    Brain takes priority over the bot's display name (so "Heuristic" beats
    "Bot 1"); falls back to player_names if no brain hint exists. The
    difficulty suffix uses the per-seat profile difficulty when available,
    else the session default. Returns None if we have nothing useful to
    show.
    """
    profile = session.ai_profiles_by_player.get(player_id) or {}
    brain = profile.get("brain")
    model = profile.get("model")
    difficulty = profile.get("difficulty") or session.ai_difficulty

    # Normalise enum-ish values to strings.
    if hasattr(brain, "value"):
        brain = brain.value
    if hasattr(difficulty, "value"):
        difficulty = difficulty.value

    head: Optional[str] = None
    if brain:
        b = str(brain).strip().lower()
        # OpenAI/Ollama with explicit model — surface the model id so
        # "GPT-5.3 · ultra" reads correctly. We only show the model tail
        # so absurdly long ids stay readable.
        if b in {"openai", "ollama"} and model:
            head = str(model).strip()
        else:
            head = _BRAIN_LABELS.get(b, b.title())
    if not head:
        head = session.player_names.get(player_id)
    if not head:
        return None

    diff = str(difficulty or "").strip().lower()
    if not diff:
        return head
    return f"{head} · {diff}"


def _format_deck_blurb(session: GameSession) -> Optional[str]:
    """Title-case the deck id used for either seat.

    The lobby surfaces one blurb per match (both seats in bot-vs-bot
    typically pick from the same engine pool — the column is "archetype",
    not "p1 archetype"). We pick the first non-empty deck id we see, in
    seat order, and de-slug it.

    For MTG decks resolved through ALL_DECKS, the registered Deck.name
    is preferred (so "mono_red_netdeck" displays as the deck's real
    "Mono-Red Netdeck", not a literal de-slug).
    """
    if not session.deck_id_by_player:
        return None

    # Stable order: walk the session's known player_ids so seat 1 wins
    # ties with seat 2.
    for pid in session.player_ids:
        deck_id = session.deck_id_by_player.get(pid)
        if not deck_id:
            continue
        return _pretty_deck_name(deck_id)
    return None


def _pretty_deck_name(deck_id: str) -> str:
    """Resolve deck_id -> display name; fall back to title-cased slug."""
    deck = ALL_DECKS.get(deck_id)
    if deck is not None and getattr(deck, "name", None):
        return str(deck.name)
    # De-slug: "mono_red_netdeck" -> "Mono-Red Netdeck",
    # "SUBS_wolfpack" -> "Subs Wolfpack".
    return deck_id.replace("_", " ").strip().title()


def _bot_game_status_from_session(session: GameSession) -> BotGameStatus:
    """Build the enriched BotGameStatus row for an active bot-game session."""
    pids = list(session.player_ids)
    p1_id = pids[0] if pids else None
    p2_id = pids[1] if len(pids) > 1 else None
    return BotGameStatus(
        game_id=session.id,
        status="finished" if session.is_finished else "running",
        turn=session.game.turn_manager.turn_number if session.is_started else 0,
        winner=session.winner_id,
        game_mode=getattr(session.game.state, "game_mode", None),
        player1_label=_format_player_label(session, p1_id) if p1_id else None,
        player2_label=_format_player_label(session, p2_id) if p2_id else None,
        deck_blurb=_format_deck_blurb(session),
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

    # Configure bot brains. A `claude_code` brain is sugar for "this seat is
    # externally driven by a `claude -p` subprocess at ultra difficulty" —
    # normalize it so the engine routes its actions through the human-action
    # handler (poll-based) rather than calling an in-process LLM provider.
    def _profile_for(brain_value: str, difficulty_value: str, model: Optional[str], temperature: float) -> dict:
        if brain_value == "claude_code":
            return {
                "brain": "external",
                "difficulty": "ultra",
                "agent_runner": "claude",
                "model": model,
                "temperature": temperature,
                "record_prompts": request.record_prompts,
            }
        return {
            "brain": brain_value,
            "difficulty": difficulty_value,
            "model": model,
            "temperature": temperature,
            "record_prompts": request.record_prompts,
        }

    session.ai_profiles_by_player[bot1_id] = _profile_for(
        request.bot1_brain.value, request.bot1_difficulty.value,
        request.bot1_model, request.bot1_temperature,
    )
    session.ai_profiles_by_player[bot2_id] = _profile_for(
        request.bot2_brain.value, request.bot2_difficulty.value,
        request.bot2_model, request.bot2_temperature,
    )

    # Fast preflight for API-based bots (avoid starting a match that will wedge).
    if request.bot1_brain.value == "openai" or request.bot2_brain.value == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            raise HTTPException(status_code=400, detail="OPENAI_API_KEY not set")

    # === Game-mode-specific setup ===

    if request.mode == "minecraft":
        from src.cards.minecraft import MINECRAFT_STARTER_DECKS

        b1_key = request.bot1_deck_id if request.bot1_deck_id in MINECRAFT_STARTER_DECKS else "builder"
        b2_key = request.bot2_deck_id if request.bot2_deck_id in MINECRAFT_STARTER_DECKS else "raider"

        player_ids = list(session.game.state.players.keys())
        for pid in player_ids[:2]:
            player = session.game.state.players[pid]
            session.game.setup_minecraft_player(player, [])
        session.add_cards_to_deck(bot1_id, MINECRAFT_STARTER_DECKS[b1_key]())
        session.add_cards_to_deck(bot2_id, MINECRAFT_STARTER_DECKS[b2_key]())
        # WatchLive lobby: stash the resolved keys so the table can render
        # a deck blurb instead of mock padding.
        session.deck_id_by_player[bot1_id] = b1_key
        session.deck_id_by_player[bot2_id] = b2_key

    elif request.mode == "yugioh":
        # Yu-Gi-Oh! bot-vs-bot: resolve decks by ID, setup players
        from src.cards.yugioh.ygo_classic import (
            YUGI_DECK, YUGI_EXTRA_DECK, KAIBA_DECK, KAIBA_EXTRA_DECK,
        )
        from src.cards.yugioh.ygo_starter import (
            WARRIOR_DECK, WARRIOR_EXTRA_DECK, SPELLCASTER_DECK, SPELLCASTER_EXTRA_DECK,
        )
        from src.cards.yugioh.ygo_optimized import YGO_OPTIMIZED_DECKS
        import random

        ygo_all_decks = {
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
        ygo_keys = list(ygo_all_decks.keys())

        def resolve_ygo(deck_id):
            if deck_id and deck_id in ygo_all_decks:
                return ygo_all_decks[deck_id]
            return ygo_all_decks[random.choice(ygo_keys)]

        b1_main, b1_extra, b1_strat = resolve_ygo(request.bot1_deck_id)
        b2_main, b2_extra, b2_strat = resolve_ygo(request.bot2_deck_id)

        # WatchLive: capture the resolved deck IDs (even when the request
        # left them blank and we rolled random) so the lobby can blurb
        # the archetype.
        b1_yk = request.bot1_deck_id if request.bot1_deck_id in ygo_all_decks else next(
            (k for k, v in ygo_all_decks.items() if v == (b1_main, b1_extra, b1_strat)), None
        )
        b2_yk = request.bot2_deck_id if request.bot2_deck_id in ygo_all_decks else next(
            (k for k, v in ygo_all_decks.items() if v == (b2_main, b2_extra, b2_strat)), None
        )
        if b1_yk:
            session.deck_id_by_player[bot1_id] = b1_yk
        if b2_yk:
            session.deck_id_by_player[bot2_id] = b2_yk

        player_ids = list(session.game.state.players.keys())
        for idx, pid in enumerate(player_ids[:2]):
            player = session.game.state.players[pid]
            main, extra = (b1_main, b1_extra) if idx == 0 else (b2_main, b2_extra)
            session.game.setup_yugioh_player(player, main, extra)

        # Apply strategy to AI adapter (shared — use bot1's strategy)
        strategy = b1_strat or b2_strat
        if strategy:
            session.ygo_ai_strategy = strategy

    elif request.mode == "pokemon":
        # Pokemon bot-vs-bot: random starter decks
        from src.cards.pokemon.sv_starter import make_fire_deck, make_water_deck
        import random

        deck_fns = [make_fire_deck, make_water_deck]
        random.shuffle(deck_fns)
        # Mirror lookup: fn -> blurb-id, for WatchLive enrichment.
        _pkm_fn_ids = {make_fire_deck: "fire_starter", make_water_deck: "water_starter"}

        player_ids = list(session.game.state.players.keys())
        for idx, pid in enumerate(player_ids[:2]):
            player = session.game.state.players[pid]
            session.game.setup_pokemon_player(player, [])
            chosen_fn = deck_fns[idx % len(deck_fns)]
            session.add_cards_to_deck(pid, chosen_fn())
            deck_blurb_id = _pkm_fn_ids.get(chosen_fn)
            if deck_blurb_id:
                # Map back to bot1_id / bot2_id (player_ids[idx] is the
                # same seat the engine assigned).
                session.deck_id_by_player[pid] = deck_blurb_id

    elif request.mode == "scp":
        # SCP bot-vs-bot: asymmetric Foundation (seat 0) vs Chaos Insurgency
        # (seat 1). Record a faction-appropriate deck id per seat; the actual
        # scp.setup_scp_game call is deferred to SCPModeAdapter.setup_game(),
        # which reads session.deck_id_by_player.
        from src.cards.scp.decks import SCP_FOUNDATION_DECKS, SCP_INSURGENCY_DECKS
        import random

        fkeys = list(SCP_FOUNDATION_DECKS)
        ikeys = list(SCP_INSURGENCY_DECKS)
        b1_key = request.bot1_deck_id if request.bot1_deck_id in SCP_FOUNDATION_DECKS else random.choice(fkeys)
        b2_key = request.bot2_deck_id if request.bot2_deck_id in SCP_INSURGENCY_DECKS else random.choice(ikeys)

        player_ids = list(session.game.state.players.keys())
        if len(player_ids) >= 1:
            session.deck_id_by_player[player_ids[0]] = b1_key
        if len(player_ids) >= 2:
            session.deck_id_by_player[player_ids[1]] = b2_key

    elif request.mode == "clankers":
        # Clankers bot-vs-bot: pick (Core, 60-card deck) for each seat from
        # CLAN_STARTER_DECKS. The actual setup_clankers_player call is
        # deferred to ClankersModeAdapter.setup_game() which reads the
        # per-seat deck ID from session.deck_id_by_player.
        from src.cards.clankers.CLAN.decks import CLAN_STARTER_DECKS
        import random

        deck_keys = list(CLAN_STARTER_DECKS.keys())
        b1_key = (
            request.bot1_deck_id if request.bot1_deck_id in CLAN_STARTER_DECKS
            else random.choice(deck_keys)
        )
        b2_key = (
            request.bot2_deck_id if request.bot2_deck_id in CLAN_STARTER_DECKS
            else random.choice([k for k in deck_keys if k != b1_key] or deck_keys)
        )

        player_ids = list(session.game.state.players.keys())
        if len(player_ids) >= 1:
            session.deck_id_by_player[player_ids[0]] = b1_key
        if len(player_ids) >= 2:
            session.deck_id_by_player[player_ids[1]] = b2_key

    elif request.mode == "cats":
        # Cats bot-vs-bot: mirror match.py's cats branch. Each seat gets a
        # commander + 30-card deck from CATS_DECKS, then setup_cats_player
        # shuffles + draws CATS_HAND_SIZE + installs commander.
        from src.cards.cats.CATS.decks import CATS_DECKS
        from src.engine.cats import setup_cats_player
        import random

        deck_keys = list(CATS_DECKS.keys())
        b1_key = (
            request.bot1_deck_id if request.bot1_deck_id in CATS_DECKS
            else random.choice(deck_keys)
        )
        b2_key = (
            request.bot2_deck_id if request.bot2_deck_id in CATS_DECKS
            else random.choice([k for k in deck_keys if k != b1_key] or deck_keys)
        )

        player_ids = list(session.game.state.players.keys())
        deck_keys_by_seat = {player_ids[0]: b1_key}
        if len(player_ids) >= 2:
            deck_keys_by_seat[player_ids[1]] = b2_key

        for pid in player_ids[:2]:
            commander, deck_cards = CATS_DECKS[deck_keys_by_seat[pid]]
            setup_cats_player(session.game.state, pid, deck_cards, commander=commander)
            session.deck_card_defs_by_player.setdefault(pid, []).extend(deck_cards)

    elif request.mode == "finance":
        # Finance bot-vs-bot: setup both players with Capital Reserve=30
        # (setup_finance_player) and seed each library with a Finance deck.
        # Without this branch the route fell through to the MTG/HS else
        # block, which assigned TEST_CARDS (Forest/Plains/Lightning Bolt)
        # to each seat. None of those carry FIN_TRADER/FIN_ORDER/etc.
        # types, so FinanceTurnManager._play_card_action recognised them
        # as neither permanents nor one-shots and silently dropped every
        # play. End result: 89 turns of END_TURN spam with 0 battlefield
        # objects — exactly the symptom in the wet-test report.
        from src.cards.finance import FINANCE_DECKS
        import random

        finance_deck_keys = list(FINANCE_DECKS.keys())
        b1_key = (
            request.bot1_deck_id if request.bot1_deck_id in FINANCE_DECKS
            else random.choice(finance_deck_keys)
        )
        b2_key = (
            request.bot2_deck_id if request.bot2_deck_id in FINANCE_DECKS
            else random.choice(
                [k for k in finance_deck_keys if k != b1_key] or finance_deck_keys
            )
        )

        player_ids = list(session.game.state.players.keys())
        deck_keys_by_seat = {player_ids[0]: b1_key}
        if len(player_ids) >= 2:
            deck_keys_by_seat[player_ids[1]] = b2_key

        for pid in player_ids[:2]:
            player = session.game.state.players.get(pid)
            if player is None:
                continue
            session.game.setup_finance_player(player)
            deck = FINANCE_DECKS[deck_keys_by_seat[pid]]()
            session.add_cards_to_deck(pid, deck)
            # WatchLive lobby: stash the deck key so the table can blurb
            # the archetype.
            session.deck_id_by_player[pid] = deck_keys_by_seat[pid]

    elif request.mode == "depths":
        # Depths bot-vs-bot: setup both players with a Flagship + 30-card deck.
        # Without setup_depths_player, neither player has a Flagship, so the
        # turn manager's SBA loss check ('flagship is None') triggers
        # immediately and both players lose on turn 1 → Draw.
        from src.cards.depths.submarine_fleet.decks import (
            SUBS_STARTER_DECKS, make_subs_flagship,
        )
        from src.engine.depths import setup_depths_player
        import random

        depths_deck_keys = list(SUBS_STARTER_DECKS.keys())
        b1_key = (
            request.bot1_deck_id if request.bot1_deck_id in SUBS_STARTER_DECKS
            else random.choice(depths_deck_keys)
        )
        b2_key = (
            request.bot2_deck_id if request.bot2_deck_id in SUBS_STARTER_DECKS
            else random.choice([k for k in depths_deck_keys if k != b1_key] or depths_deck_keys)
        )

        player_ids = list(session.game.state.players.keys())
        deck_keys_by_seat = {player_ids[0]: b1_key}
        if len(player_ids) >= 2:
            deck_keys_by_seat[player_ids[1]] = b2_key

        for pid in player_ids[:2]:
            player = session.game.state.players.get(pid)
            if player is None:
                continue
            seat_name = session.player_names.get(pid, "Bot")
            flagship_def = make_subs_flagship(f"{seat_name} Flagship")
            deck = SUBS_STARTER_DECKS[deck_keys_by_seat[pid]]()
            setup_depths_player(session.game, player, deck, flagship_def)
            # Mirror match.py: keep the decklist around so the AI layer prep
            # can read it if Ultra brains are wired in later.
            session.deck_card_defs_by_player.setdefault(pid, []).extend(deck)
            # WatchLive lobby: stash the deck key so the table can blurb
            # the archetype.
            session.deck_id_by_player[pid] = deck_keys_by_seat[pid]

    else:
        # MTG / Hearthstone: build decks from IDs or card names
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

            player_ids = list(session.game.state.players.keys())
            if len(player_ids) >= 2:
                available_heroes = ["Mage", "Warrior", "Hunter", "Paladin", "Priest", "Rogue", "Shaman", "Warlock", "Druid"]
                hero1_class = random.choice(available_heroes)
                available_heroes.remove(hero1_class)
                hero2_class = random.choice(available_heroes)

                p1 = session.game.state.players[player_ids[0]]
                p2 = session.game.state.players[player_ids[1]]

                session.game.setup_hearthstone_player(p1, HEROES[hero1_class], HERO_POWERS[hero1_class])
                session.game.setup_hearthstone_player(p2, HEROES[hero2_class], HERO_POWERS[hero2_class])

                if not request.bot1_deck and not request.bot1_deck_id:
                    bot1_deck = get_deck_for_hero(hero1_class)
                if not request.bot2_deck and not request.bot2_deck_id:
                    bot2_deck = get_deck_for_hero(hero2_class)

                # WatchLive lobby: stash the hero class as the deck blurb
                # when no explicit deck_id was given (HS default-deck path).
                if not request.bot1_deck and not request.bot1_deck_id:
                    session.deck_id_by_player[bot1_id] = hero1_class
                if not request.bot2_deck and not request.bot2_deck_id:
                    session.deck_id_by_player[bot2_id] = hero2_class

        # WatchLive lobby: capture explicit deck IDs (MTG netdecks like
        # 'mono_red_netdeck'). Explicit card-list decks have no canonical
        # name so we leave the blurb empty for those.
        if request.bot1_deck_id:
            session.deck_id_by_player[bot1_id] = request.bot1_deck_id
        if request.bot2_deck_id:
            session.deck_id_by_player[bot2_id] = request.bot2_deck_id

        # Add cards to libraries
        session.add_cards_to_deck(bot1_id, bot1_deck)
        session.add_cards_to_deck(bot2_id, bot2_deck)

    # Store in active games
    active_bot_games[session.id] = session

    # Spawn one `claude -p` subprocess per seat with brain=claude_code.
    # The subprocess polls the REST API and posts actions for its seat;
    # the engine reaches it through the human-action-handler path because
    # the profile normalization above set difficulty=ultra.
    from .match import _spawn_ultra_subprocess
    claude_seats: list[tuple[str, str, Optional[str]]] = []
    if request.bot1_brain.value == "claude_code":
        claude_seats.append((bot1_id, bot2_id, request.bot1_model))
    if request.bot2_brain.value == "claude_code":
        claude_seats.append((bot2_id, bot1_id, request.bot2_model))
    for seat_id, opponent_id, model in claude_seats:
        await _spawn_ultra_subprocess(
            match_id=session.id,
            ai_player_id=seat_id,
            human_player_id=opponent_id,
            game_mode=request.mode,
            agent_runner="claude",
            agent_model=model,
        )

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

        # Clankers' run_turn is synchronous (and the mode adapter drives the
        # full bot_vs_bot loop with workshop-breach detection + replay frames
        # internally). Delegate to the mode adapter rather than the generic
        # ``await turn_manager.run_turn()`` driver below.
        if session.game.state.game_mode == "clankers":
            await session.mode_adapter.run_game_loop(session)
            completed_replays[session.id] = ReplayResponse(
                game_id=session.id,
                winner=session.winner_id,
                total_turns=session.game.turn_manager.turn_number,
                frames=session.replay_frames
            )
            return

        while not session.is_finished:
            # Run one turn (priority actions inside are paced via session.spectator_delay_ms)
            await session.game.turn_manager.run_turn()

            # For non-MTG modes, the priority system loop is bypassed so
            # _on_action_processed never fires.  Record a frame per turn
            # so that replays capture the game progression.
            if session.game.state.game_mode in ("hearthstone", "yugioh", "pokemon", "minecraft", "depths", "finance", "scp", "cats", "clankers") and session.record_actions_for_replay:
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

            # Safety limit (HS games are faster; 50 turns ~25 rounds)
            turn_limit = 50 if session.game.state.game_mode in ("hearthstone", "minecraft") else 100
            if session.game.turn_manager.turn_number > turn_limit:
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


@router.get("/{game_id}/status", response_model=BotGameStatus)
async def get_bot_game_status(game_id: str) -> BotGameStatus:
    """
    Get the status of a bot game.
    """
    session = active_bot_games.get(game_id)

    if session:
        return _bot_game_status_from_session(session)

    if game_id in completed_replays:
        replay = completed_replays[game_id]
        # Completed replays are post-session — we don't carry per-seat
        # brain/difficulty metadata across the boundary, so enrichment
        # is intentionally None for these rows.
        return BotGameStatus(
            game_id=game_id,
            status="finished",
            turn=replay.total_turns,
            winner=replay.winner,
        )

    raise HTTPException(status_code=404, detail="Game not found")


@router.get("/list", response_model=BotGameListResponse)
async def list_bot_games(
    status: Optional[str] = None
) -> BotGameListResponse:
    """
    List all bot games.

    Filter by status: 'running', 'finished', or None for all.
    """
    games: list[BotGameStatus] = []

    # Active games — emit the enriched row so WatchLive can render real
    # engine + player + deck data instead of mock fallbacks.
    for game_id, session in active_bot_games.items():
        if status == "finished" and not session.is_finished:
            continue
        if status == "running" and session.is_finished:
            continue

        games.append(_bot_game_status_from_session(session))

    # Completed replays not in active games — minimal shape (no live
    # session to read brain/deck off of).
    for game_id, replay in completed_replays.items():
        if game_id not in active_bot_games:
            if status == "running":
                continue

            games.append(BotGameStatus(
                game_id=game_id,
                status="finished",
                turn=replay.total_turns,
                winner=replay.winner,
            ))

    return BotGameListResponse(games=games, total=len(games))


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
