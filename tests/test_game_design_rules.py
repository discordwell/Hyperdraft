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
