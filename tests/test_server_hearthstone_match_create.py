import asyncio

from fastapi import BackgroundTasks

from src.server.models import CreateMatchRequest
from src.server.routes.match import create_match
from src.server.session import session_manager
from src.engine.types import CardType


def test_create_match_hearthstone_sets_up_heroes_and_decks():
    """Creating a Hearthstone match should configure heroes/hero powers and 30-card decks."""

    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot",
                game_mode="hearthstone",
                player_name="Tester",
            ),
            background_tasks=BackgroundTasks(),
        )

        session = session_manager.get_session(response.match_id)
        assert session is not None
        assert session.game.state.game_mode == "hearthstone"
        assert len(session.player_ids) == 2

        for pid in session.player_ids:
            player = session.game.state.players[pid]

            assert player.hero_id is not None
            assert player.hero_power_id is not None

            hero = session.game.state.objects[player.hero_id]
            hero_power = session.game.state.objects[player.hero_power_id]

            assert CardType.HERO in hero.characteristics.types
            assert CardType.HERO_POWER in hero_power.characteristics.types

            library = session.game.state.zones[f"library_{pid}"]
            assert len(library.objects) == 30

        await session_manager.remove_session(response.match_id)

    asyncio.run(_run())


def test_create_match_riftclash_sets_up_variant_decks_and_modifiers():
    """Creating a Riftclash match should install variant heroes, decks, and global modifiers."""

    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot",
                game_mode="hearthstone",
                variant="riftclash",
                hero_class="Pyromancer",
                player_name="Tester",
            ),
            background_tasks=BackgroundTasks(),
        )

        session = session_manager.get_session(response.match_id)
        assert session is not None
        assert session.display_variant == "riftclash"

        # Variant interceptors are registered with a stable prefix.
        assert any(iid.startswith("mod_riftclash_") for iid in session.game.state.interceptors.keys())

        hero_names = []
        for pid in session.player_ids:
            player = session.game.state.players[pid]
            assert player.hero_id is not None
            library = session.game.state.zones[f"library_{pid}"]
            assert len(library.objects) == 30
            hero_names.append(session.game.state.objects[player.hero_id].name)

        assert "Ignis, Rift Vanguard" in hero_names
        assert "Glaciel, Icebound Regent" in hero_names

        await session_manager.remove_session(response.match_id)

    asyncio.run(_run())


def test_hearthstone_match_uses_requested_ai_difficulty_for_adapter():
    """HS human-vs-bot should pass requested difficulty into HearthstoneAIAdapter."""

    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot",
                game_mode="hearthstone",
                variant="riftclash",
                ai_difficulty="ultra",
                player_name="Tester",
            ),
            background_tasks=BackgroundTasks(),
        )

        session = session_manager.get_session(response.match_id)
        assert session is not None

        await session.start_game()

        adapter = getattr(session.game.turn_manager, "hearthstone_ai_handler", None)
        assert adapter is not None
        assert getattr(adapter, "difficulty", None) == "ultra"

        await session_manager.remove_session(response.match_id)

    asyncio.run(_run())
