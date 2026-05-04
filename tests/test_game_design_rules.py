"""Tests for configurable Hyperdraft rules knobs."""

import asyncio

from src.engine import EventType, Game, ZoneType


async def _run_first_draw_step(first_player_draws: bool):
    game = Game(first_player_draws=first_player_draws)
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    game.create_object(name="Top Card", owner_id=p1.id, zone=ZoneType.LIBRARY)

    game.turn_manager.priority_system = None
    game.turn_manager.set_turn_order([p1.id, p2.id])
    game.turn_manager.current_player_index = 0
    game.turn_manager.turn_state.active_player_id = p1.id
    game.turn_manager.turn_state.turn_number = 1
    game.state.active_player = p1.id
    game.state.turn_number = 1

    events = await game.turn_manager._run_beginning_phase()
    return game, p1, events


def test_default_mtg_first_player_skips_first_draw():
    game, p1, events = asyncio.run(_run_first_draw_step(first_player_draws=False))

    draw_events = [event for event in events if event.type == EventType.DRAW]

    assert draw_events == []
    assert game.state.zones[f"hand_{p1.id}"].objects == []
    assert len(game.state.zones[f"library_{p1.id}"].objects) == 1


def test_hyperdraft_variant_can_let_first_player_draw():
    game, p1, events = asyncio.run(_run_first_draw_step(first_player_draws=True))

    draw_events = [event for event in events if event.type == EventType.DRAW]

    assert len(draw_events) == 1
    assert draw_events[0].payload["player"] == p1.id
    assert game.state.zones[f"hand_{p1.id}"].objects
    assert game.state.zones[f"library_{p1.id}"].objects == []


def test_variant_starting_life_sets_default_for_new_players():
    game = Game(starting_life=25)

    default_player = game.add_player("Default")
    explicit_player = game.add_player("Explicit", life=12)

    assert game.state.starting_life == 25
    assert default_player.life == 25
    assert explicit_player.life == 12


def test_variant_opening_hand_size_controls_mtg_mulligan_draw():
    game = Game(opening_hand_size=5)
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    for player in (p1, p2):
        for idx in range(5):
            game.create_object(name=f"Card {player.name} {idx}", owner_id=player.id, zone=ZoneType.LIBRARY)
    game.set_mulligan_handler(lambda _player_id, _hand, _mulligan_count: True)

    asyncio.run(game.start_game())

    assert game.state.opening_hand_size == 5
    assert len(game.state.zones[f"hand_{p1.id}"].objects) == 5
    assert len(game.state.zones[f"hand_{p2.id}"].objects) == 5


def test_variant_max_hand_size_controls_cleanup_discard_count():
    game = Game(max_hand_size=5)
    player = game.add_player("P1")
    for idx in range(6):
        game.create_object(name=f"Hand Card {idx}", owner_id=player.id, zone=ZoneType.HAND)
    game.turn_manager.turn_state.active_player_id = player.id

    events = asyncio.run(game.turn_manager._do_cleanup_step())

    discards = [event for event in events if event.type == EventType.DISCARD]
    assert game.state.max_hand_size == 5
    assert len(discards) == 1
    assert discards[0].payload["count"] == 1


def test_variant_lands_allowed_per_turn_controls_turn_reset():
    game = Game(lands_allowed_per_turn=2)

    game.state.lands_played_this_turn = 1
    game.turn_manager.turn_state.lands_played_count = 1
    game.turn_manager._reset_turn_state()

    assert game.state.base_lands_allowed_per_turn == 2
    assert game.state.lands_allowed_this_turn == 2
    assert game.turn_manager.turn_state.lands_allowed == 2
    assert game.state.lands_played_this_turn == 0


def test_variant_max_mulligans_limits_mtg_mulligan_loop():
    game = Game(max_mulligans=2)
    player = game.add_player("P1")
    for idx in range(7):
        game.create_object(name=f"Library Card {idx}", owner_id=player.id, zone=ZoneType.LIBRARY)
    game.set_mulligan_handler(lambda _player_id, _hand, _mulligan_count: False)

    asyncio.run(game._resolve_mulligans(player.id))

    assert game.state.max_mulligans == 2
    assert len(game.state.zones[f"hand_{player.id}"].objects) == 0
    assert len(game.state.zones[f"library_{player.id}"].objects) == 7
