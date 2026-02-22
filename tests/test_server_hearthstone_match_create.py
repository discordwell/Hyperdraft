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


def test_create_match_frierenrift_sets_up_variant_decks_and_resources():
    """Creating a Frierenrift match should install variant heroes/decks/resource rules."""

    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot",
                game_mode="hearthstone",
                variant="frierenrift",
                hero_class="Frieren",
                player_name="Tester",
            ),
            background_tasks=BackgroundTasks(),
        )

        session = session_manager.get_session(response.match_id)
        assert session is not None
        assert session.display_variant == "frierenrift"
        assert any(iid.startswith("mod_frierenrift_") for iid in session.game.state.interceptors.keys())

        hero_names = []
        for pid in session.player_ids:
            player = session.game.state.players[pid]
            assert player.hero_id is not None
            assert getattr(player, "manual_mana_growth", False) is True
            assert int(getattr(player, "attunements_per_turn", 0)) == 1
            resources = getattr(player, "variant_resources", {})
            assert isinstance(resources, dict)
            assert {"azure", "ember", "verdant"}.issubset(set(resources.keys()))
            library = session.game.state.zones[f"library_{pid}"]
            assert len(library.objects) == 30
            hero_names.append(session.game.state.objects[player.hero_id].name)

        assert "Frieren, Last Great Mage" in hero_names
        assert "Macht of El Dorado" in hero_names

        await session_manager.remove_session(response.match_id)

    asyncio.run(_run())


def test_frierenrift_attune_card_moves_hand_card_and_grants_resources():
    """Attuning in Frierenrift should exile a hand card, add mana, and add a shard."""

    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot",
                game_mode="hearthstone",
                variant="frierenrift",
                hero_class="Frieren",
                player_name="Tester",
            ),
            background_tasks=BackgroundTasks(),
        )

        session = session_manager.get_session(response.match_id)
        assert session is not None

        await session.start_game()

        active_pid = session.game.get_active_player()
        if active_pid is None:
            tm = session.game.turn_manager
            assert tm.turn_order
            active_pid = tm.turn_order[tm.current_player_index]
        player = session.game.state.players[active_pid]
        hand = session.game.state.zones[f"hand_{active_pid}"]
        assert hand.objects, "expected at least one card in opening hand"

        card_id = hand.objects[0]
        before_mana = player.mana_crystals
        before_attunes = int(getattr(player, "attunements_this_turn", 0))
        before_resources = dict(getattr(player, "variant_resources", {}))

        ok = await session.game.attune_card(active_pid, card_id)
        assert ok is True

        card = session.game.state.objects[card_id]
        assert card.zone == session.game.state.zones["exile"].type
        assert card_id in session.game.state.zones["exile"].objects
        assert card_id not in session.game.state.zones[f"hand_{active_pid}"].objects
        assert player.mana_crystals == min(10, before_mana + 1)
        assert int(getattr(player, "attunements_this_turn", 0)) == before_attunes + 1
        resources = getattr(player, "variant_resources", {})
        assert isinstance(resources, dict)
        assert sum(int(resources.get(k, 0)) for k in ("azure", "ember", "verdant")) >= (
            sum(int(before_resources.get(k, 0)) for k in ("azure", "ember", "verdant")) + 1
        )

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
