import asyncio

from src.engine import Game, ZoneType, ActionType as EngineActionType
from src.server.models import PlayerActionRequest, ActionType as ApiActionType
from src.server.session import GameSession


def test_session_human_pending_choice_unblocks_human_action_handler():
    """
    When the engine raises a PendingChoice for a human player, the session should
    block in _get_human_action until /choice is submitted, then continue the loop.
    """
    session = GameSession(id="test", game=Game(), mode="human_vs_bot")
    p1_id = session.add_player("P1", is_ai=False)
    session.add_player("P2", is_ai=True)

    game = session.game
    card_a = game.create_object(name="Card A", owner_id=p1_id, zone=ZoneType.LIBRARY)
    card_b = game.create_object(name="Card B", owner_id=p1_id, zone=ZoneType.LIBRARY)

    choice = game.create_choice(
        choice_type="scry",
        player_id=p1_id,
        prompt="Scry 2",
        options=[card_a.id, card_b.id],
        source_id="source",
        min_choices=0,
        max_choices=2,
        callback_data={"scry_count": 2},
    )

    async def _run():
        waiter = asyncio.create_task(session._get_human_action(p1_id, []))
        await asyncio.sleep(0)  # Let _get_human_action register its future.

        success, message, _events = await session.handle_choice(choice.id, p1_id, [card_a.id])
        assert success, message

        action = await asyncio.wait_for(waiter, timeout=1.0)
        assert action.type == EngineActionType.SPECIAL_ACTION

    asyncio.run(_run())


def test_session_rejects_action_requests_while_waiting_for_choice():
    """
    Clients should not be able to submit /action while a PendingChoice is waiting
    for their input; they must submit /choice instead.
    """
    session = GameSession(id="test", game=Game(), mode="human_vs_bot")
    p1_id = session.add_player("P1", is_ai=False)
    session.add_player("P2", is_ai=True)

    game = session.game
    card_a = game.create_object(name="Card A", owner_id=p1_id, zone=ZoneType.LIBRARY)
    card_b = game.create_object(name="Card B", owner_id=p1_id, zone=ZoneType.LIBRARY)

    game.create_choice(
        choice_type="scry",
        player_id=p1_id,
        prompt="Scry 2",
        options=[card_a.id, card_b.id],
        source_id="source",
        min_choices=0,
        max_choices=2,
        callback_data={"scry_count": 2},
    )

    # Make this player the priority player so handle_action reaches the pending-choice guard.
    session.game.priority_system.priority_player = p1_id

    req = PlayerActionRequest(action_type=ApiActionType.PASS, player_id=p1_id)
    success, message = asyncio.run(session.handle_action(req))

    assert success is False
    assert "pending choice" in message.lower()

