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
