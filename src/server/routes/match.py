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


@router.get("/ultra-pending")
async def list_ultra_pending() -> dict:
    """List matches awaiting an ultra-AI move from an external agent.

    Returns matches where:
      - the AI seat's difficulty is "ultra"
      - the AI is the current active player (i.e. it's the AI's turn)
      - the match is still active (not finished)
      - the session is registered with the active session manager

    No auth — this is a local-only signal consumed by the orchestrator that
    spawns Claude Code agents to play the AI seat.
    """
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
                "turn_number": turn_number,
                "phase": phase_name or "",
            })
        except Exception:
            # Defensive: never let one broken session break the listing.
            continue

    return {"pending": pending}


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

    # Store variant for client display
    if request.variant:
        session.display_variant = request.variant

    # Add human player
    human_id = session.add_player(request.player_name, is_ai=False)

    # Add AI player for human vs bot mode
    if request.mode == "human_vs_bot":
        ai_difficulty = request.ai_difficulty.value
        if ai_difficulty == "ultra":
            ai_name = "Codex Ultra"
        else:
            ai_name = "AI Opponent"
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

    elif request.game_mode == "minecraft":
        from src.cards.minecraft import MINECRAFT_STARTER_DECKS
        import random

        deck_keys = ["builder", "miner", "raider"]
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
    elif request.game_mode == "finance":
        from src.cards.finance.fina import FINA_STARTER_DECKS
        import random

        deck_keys = list(FINA_STARTER_DECKS.keys())
        human_deck_key = (
            request.player_deck_id if request.player_deck_id in FINA_STARTER_DECKS
            else "FINA_high_frequency"
        )
        ai_deck_key = (
            request.ai_deck_id if request.ai_deck_id in FINA_STARTER_DECKS
            else "FINA_quant"
        )
        if request.mode == "bot_vs_bot":
            random.shuffle(deck_keys)
            human_deck_key, ai_deck_key = deck_keys[0], deck_keys[1]

        for pid in session.player_ids:
            player = session.game.state.players.get(pid)
            if player:
                session.game.setup_finance_player(player)

        session.add_cards_to_deck(human_id, FINA_STARTER_DECKS[human_deck_key]())
        if request.mode == "human_vs_bot" and ai_id:
            session.add_cards_to_deck(ai_id, FINA_STARTER_DECKS[ai_deck_key]())
        elif request.mode == "bot_vs_bot":
            session.add_cards_to_deck(ai_id, FINA_STARTER_DECKS[human_deck_key]())
            if ai2_id:
                session.add_cards_to_deck(ai2_id, FINA_STARTER_DECKS[ai_deck_key]())

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

    # Ultra mode: spawn a Claude Code instance in a new Terminal window to
    # play the AI seat. The watcher script polls /state and takes turns.
    if (
        request.mode == "human_vs_bot"
        and ai_id
        and request.ai_difficulty.value == "ultra"
    ):
        _spawn_ultra_terminal(
            match_id=session.id,
            ai_player_id=ai_id,
            human_player_id=human_id,
            game_mode=request.game_mode,
        )

    return CreateMatchResponse(
        match_id=session.id,
        player_id=human_id,
        opponent_id=ai_id or "",
        status="created"
    )


def _spawn_ultra_terminal(
    *, match_id: str, ai_player_id: str, human_player_id: str, game_mode: str
) -> None:
    """Open a terminal window running ``scripts/launch_ultra_agent.sh``.

    Cross-platform: tries macOS (Terminal.app / iTerm2), Linux (respects
    ``$TERMINAL`` env var, falls through common terminal emulators), and
    Windows (Windows Terminal preferred). Falls back to printing a copyable
    command if no terminal can be spawned automatically.

    Best-effort. Failure must NOT break match creation — the user can still
    play (the AI seat just sits idle until they launch the agent manually).
    """
    import os
    import shlex
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[3]
    launcher = project_root / "scripts" / "launch_ultra_agent.sh"
    if not launcher.exists():
        print(f"[ultra] launcher not found: {launcher}", flush=True)
        return

    env_assignments = (
        f"MATCH_ID={shlex.quote(match_id)} "
        f"AI_PLAYER_ID={shlex.quote(ai_player_id)} "
        f"HUMAN_PLAYER_ID={shlex.quote(human_player_id)} "
        f"GAME_MODE={shlex.quote(game_mode)}"
    )
    inner = f"cd {shlex.quote(str(project_root))} && {env_assignments} {shlex.quote(str(launcher))}"

    def _print_manual(reason: str) -> None:
        print(
            f"[ultra] {reason}; run this manually in a terminal:\n  {inner}",
            flush=True,
        )

    spawned = False
    try:
        if sys.platform == "darwin":
            spawned = _spawn_macos(inner, match_id)
        elif sys.platform.startswith("linux"):
            spawned = _spawn_linux(inner)
        elif sys.platform.startswith("win"):
            spawned = _spawn_windows(inner)
        else:
            _print_manual(f"unsupported platform {sys.platform}")
            return
    except Exception as exc:  # pylint: disable=broad-except
        _print_manual(f"spawn failed: {exc}")
        return

    if spawned:
        print(f"[ultra] spawned terminal for match {match_id} ({game_mode})", flush=True)
    else:
        _print_manual("no usable terminal found")


def _spawn_macos(inner: str, match_id: str) -> bool:
    """macOS: pick Terminal.app or iTerm2 based on $TERM_PROGRAM."""
    import os
    import subprocess

    term = os.environ.get("TERM_PROGRAM", "")
    apple_inner = inner.replace("\\", "\\\\").replace('"', '\\"')

    if term == "iTerm.app":
        # iTerm2 — open a new window with the command.
        osa = (
            'tell application "iTerm"\n'
            '  create window with default profile\n'
            f'  tell current session of current window to write text "{apple_inner}"\n'
            'end tell'
        )
    else:
        # Terminal.app (default). Works for unknown $TERM_PROGRAM too.
        osa = f'tell application "Terminal" to do script "{apple_inner}"'

    subprocess.Popen(
        ["osascript", "-e", osa],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return True


def _spawn_linux(inner: str) -> bool:
    """Linux: respect $TERMINAL, then try common terminal emulators."""
    import os
    import shutil
    import subprocess

    # Tuples of (binary, args-template). Args use {cmd} as placeholder.
    candidates: list[tuple[str, list[str]]] = []
    user_term = os.environ.get("TERMINAL")
    if user_term:
        # Generic fallback args; if user's terminal needs different syntax
        # they can override via wrapping their own script.
        candidates.append((user_term, ["-e", "bash", "-c", inner]))
    candidates.extend([
        ("x-terminal-emulator", ["-e", "bash", "-c", inner]),  # Debian alternatives
        ("gnome-terminal", ["--", "bash", "-c", inner]),
        ("konsole", ["-e", "bash", "-c", inner]),
        ("alacritty", ["-e", "bash", "-c", inner]),
        ("kitty", ["bash", "-c", inner]),
        ("wezterm", ["start", "--", "bash", "-c", inner]),
        ("tilix", ["-e", "bash", "-c", inner]),
        ("xfce4-terminal", ["-e", f"bash -c {shlex_quote(inner)}"]),
        ("xterm", ["-e", "bash", "-c", inner]),
    ])

    for prog, args in candidates:
        if shutil.which(prog):
            subprocess.Popen(
                [prog] + args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
    return False


def _spawn_windows(inner: str) -> bool:
    """Windows: prefer Windows Terminal, fall back to cmd. Requires bash on PATH."""
    import shutil
    import subprocess

    # The launcher script is bash — user must have Git Bash, WSL, or similar.
    if shutil.which("bash") is None:
        return False

    if shutil.which("wt.exe"):
        subprocess.Popen(["wt.exe", "bash", "-c", inner])
        return True

    # Plain cmd fallback.
    subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", f"bash -c \"{inner}\""])
    return True


def shlex_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)


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
