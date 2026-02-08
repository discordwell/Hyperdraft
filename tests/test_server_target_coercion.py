from src.engine import Game
from src.engine.targeting import Target as EngineTarget
from src.server.models import PlayerActionRequest, ActionType as ApiActionType
from src.server.session import GameSession


def test_action_targets_are_coerced_to_engine_targets_for_player_ids():
    session = GameSession(id="test", game=Game(), mode="human_vs_bot")
    p1_id = session.add_player("P1", is_ai=False)
    p2_id = session.add_player("P2", is_ai=True)

    req = PlayerActionRequest(
        action_type=ApiActionType.CAST_SPELL,
        player_id=p1_id,
        card_id=None,
        targets=[[p2_id]],
    )
    action = session._build_action(req)

    assert action.targets and action.targets[0]
    assert isinstance(action.targets[0][0], EngineTarget)
    assert action.targets[0][0].id == p2_id
    assert action.targets[0][0].is_player is True

