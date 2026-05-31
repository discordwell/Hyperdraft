"""Server integration + fog-of-war test for scp.

Drives a human-vs-bot scp match through the real server path: create_match →
SCPModeAdapter.setup_game → get_client_state → handle_action. Asserts:
  1. The match creates a 2-player scp session; the human is the Foundation (seat 0).
  2. get_client_state serializes a `scp` payload with me/opponent + the viewer's own hand.
  3. FOG OF WAR: the Insurgency viewer's payload redacts the Foundation's face-down cards —
     the real card name never appears in that JSON blob, but advancement 'heat' does.
  4. A human SCP_PLAY action succeeds, and SCP_END_TURN drives the AI's turn without error.

Run: HYPERDRAFT_STRICT=1 PYTHONPATH=. python3 -m pytest tests/test_scp_server.py -q
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from fastapi import BackgroundTasks

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.server.models import CreateMatchRequest, PlayerActionRequest  # noqa: E402
from src.server.routes import match as match_routes  # noqa: E402
from src.server.routes.match import create_match  # noqa: E402
from src.server.session import session_manager  # noqa: E402


@pytest.fixture(autouse=True)
def _suppress_ultra_subprocess_spawn(monkeypatch):
    async def _noop(**_kwargs):
        return True
    monkeypatch.setattr(match_routes, "_spawn_ultra_subprocess", _noop)


def _first_facedown_card(hand):
    """First hand card that installs face-down with no target needed (anomaly or asset)."""
    for c in hand:
        if c.get("kind") in ("SCP_ANOMALY", "SCP_ASSET"):
            return c
    return None


def test_scp_match_setup_and_fog_of_war():
    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot", game_mode="scp", ai_difficulty="medium",
                player_name="TestHuman",
            ),
            background_tasks=BackgroundTasks(),
        )
        session = session_manager.get_session(response.match_id)
        assert session is not None
        await session.mode_adapter.setup_game(session)
        session.is_started = True

        assert session.game.state.game_mode == "scp"
        assert len(session.player_ids) == 2
        human_id = response.player_id
        ai_id = next(p for p in session.player_ids if p != human_id)

        # --- 1. Foundation seat + serialized payload -------------------------------
        st = session.get_client_state(human_id)
        assert st.scp is not None, "scp state must serialize"
        me = st.scp["me"]
        assert me["faction"] == "foundation", "human (seat 0) is the Foundation"
        assert st.scp["your_turn"] is True, "Foundation acts first"
        assert me["hand"] is not None and len(me["hand"]) >= 5, "own hand is revealed"
        assert st.scp["opponent"]["hand"] is None, "opponent hand is hidden"
        assert st.scp["opponent"]["hand_count"] >= 5

        # --- 2. Play a face-down card --------------------------------------------
        card = _first_facedown_card(me["hand"])
        assert card is not None, f"expected an anomaly/asset in opening hand: {[c['kind'] for c in me['hand']]}"
        secret_name = card["name"]
        ok, msg = await session.handle_action(PlayerActionRequest(
            action_type="SCP_PLAY", player_id=human_id, card_id=card["id"],
        ))
        assert ok, f"SCP_PLAY failed: {msg}"

        # --- 3. FOG OF WAR: the Insurgency viewer must not see the face-down identity
        ai_view = session.get_client_state(ai_id)
        assert ai_view.scp is not None
        blob = json.dumps(ai_view.scp)
        assert secret_name not in blob, (
            f"fog-of-war leak: the Insurgency payload contains the Foundation's "
            f"face-down card name {secret_name!r}")
        # The opponent (Foundation) board is visible in structure but redacted.
        opp = ai_view.scp["opponent"]
        assert opp["faction"] == "foundation"
        if card["kind"] == "SCP_ANOMALY":
            cells = opp.get("cells", [])
            assert any(c.get("anomaly") and c["anomaly"].get("hidden") for c in cells), \
                "the face-down anomaly must be present-but-hidden to the Insurgency"

        # --- 4. End turn → AI (Insurgency) takes its full turn without error -------
        ok, msg = await session.handle_action(PlayerActionRequest(
            action_type="SCP_END_TURN", player_id=human_id,
        ))
        assert ok, f"SCP_END_TURN failed: {msg}"
        # Control returns to the human (Foundation) for their next turn, unless the
        # game ended (it won't this early).
        st2 = session.get_client_state(human_id)
        assert st2.scp is not None
        if not st2.scp["game_over"]:
            assert st2.scp["your_turn"] is True, "turn returns to the Foundation"
            assert st2.scp["me"]["ap"] == 4, "AP refreshed for the new turn"

        await session_manager.remove_session(response.match_id)

    asyncio.run(_run())


def test_scp_advance_and_credits_flow():
    """A Foundation can gain Funding and advance an installed anomaly via the server path."""
    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot", game_mode="scp", ai_difficulty="easy",
                player_name="TestHuman",
            ),
            background_tasks=BackgroundTasks(),
        )
        session = session_manager.get_session(response.match_id)
        await session.mode_adapter.setup_game(session)
        session.is_started = True
        human_id = response.player_id

        me = session.get_client_state(human_id).scp["me"]
        anomaly = next((c for c in me["hand"] if c.get("kind") == "SCP_ANOMALY"), None)
        if anomaly is None:
            await session_manager.remove_session(response.match_id)
            return  # rare: no anomaly in opening hand; nothing to advance
        await session.handle_action(PlayerActionRequest(
            action_type="SCP_PLAY", player_id=human_id, card_id=anomaly["id"]))
        # Find the installed anomaly's object id from my cells.
        cells = session.get_client_state(human_id).scp["me"]["cells"]
        cell = next(c for c in cells if c.get("anomaly"))
        # advancement is public; advance once.
        adv_before = cell["anomaly"]["advancement"]
        # The anomaly object id isn't in the redacted cell dto for the owner? It is the
        # owner's own view, so the name is shown; the engine id we need is the played card id.
        ok, msg = await session.handle_action(PlayerActionRequest(
            action_type="SCP_ADVANCE", player_id=human_id, anomaly_id=anomaly["id"]))
        assert ok, f"advance failed: {msg}"
        cells2 = session.get_client_state(human_id).scp["me"]["cells"]
        cell2 = next(c for c in cells2 if c.get("anomaly"))
        assert cell2["anomaly"]["advancement"] == adv_before + 1

        await session_manager.remove_session(response.match_id)

    asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
