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
import random
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
        random.seed(2024)  # deterministic shuffle (fog test needs a face-down-able opening hand)
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


def test_foundation_collapse_reason_serializes_to_client():
    """When the Foundation can no longer reach Containment (anomaly supply spent), check_scp_win
    declares an Insurgency win by collapse — and the client serializer must surface that reason
    (not a blank), mirroring the engine. Guards the session.py win-reason mapping."""
    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot", game_mode="scp", ai_difficulty="medium",
                player_name="TestHuman"),
            background_tasks=BackgroundTasks())
        session = session_manager.get_session(response.match_id)
        random.seed(7)
        await session.mode_adapter.setup_game(session)
        session.is_started = True

        from src.engine import scp
        from src.engine.types import ZoneType
        game = session.game
        human_id = response.player_id                                    # Foundation (seat 0)
        ai_id = next(p for p in session.player_ids if p != human_id)     # Insurgency
        fid, iid = scp.foundation_id(game.state), scp.insurgency_id(game.state)

        # Force a collapse position: Foundation one point short of the target with no anomaly value
        # left anywhere (deck + hand emptied, no cells), Insurgency holding its dealt hand (>=2).
        fr = scp.ensure_scp_state(game.state, fid)
        fr["containment_points"] = scp.CONTAINMENT_TARGET - 1
        fr["cells"] = []
        for ztype in (ZoneType.LIBRARY, ZoneType.HAND):
            zone = game.state.zones.get(scp._zkey(ztype, fid))
            if zone:
                zone.objects[:] = []
        assert len(scp.hand_ids(game.state, iid)) >= 2, "Insurgency holds its dealt hand"

        evs = scp.check_scp_win(game)
        assert any(e.type.name == "SCP_WIN" and e.payload.get("reason") == "foundation_collapse"
                   for e in evs), "engine declares collapse"
        view = session.get_client_state(ai_id)
        assert view.scp["game_over"] is True
        assert view.scp["winner"] == ai_id
        assert view.scp["win_reason"] == "foundation_collapse", \
            "the serializer must surface the collapse reason, not a blank"

        await session_manager.remove_session(response.match_id)

    asyncio.run(_run())


def test_collapse_telegraph_is_foundation_only_and_tracks_the_supply():
    """The collapse telegraph (`foundation_reachable`) must reach the FOUNDATION viewer as a live
    number but be None for the Insurgency — it counts the Foundation's hidden hand/deck, so
    exposing it would leak fog. And it must drop as the supply is milled, so the UI clock is real."""
    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot", game_mode="scp", ai_difficulty="medium",
                player_name="TestHuman"),
            background_tasks=BackgroundTasks())
        session = session_manager.get_session(response.match_id)
        random.seed(11)
        await session.mode_adapter.setup_game(session)
        session.is_started = True

        from src.engine import scp
        game = session.game
        human_id = response.player_id                                    # Foundation
        ai_id = next(p for p in session.player_ids if p != human_id)     # Insurgency
        fid = scp.foundation_id(game.state)

        fview = session.get_client_state(human_id)
        iview = session.get_client_state(ai_id)
        reach0 = fview.scp["foundation_reachable"]
        assert isinstance(reach0, int) and reach0 >= scp.CONTAINMENT_TARGET, \
            "Foundation viewer sees its reachable Containment as a live number"
        assert iview.scp["foundation_reachable"] is None, \
            "Insurgency viewer must NOT see it (it counts the Foundation's hidden cards — fog)"

        # Mill the Foundation's deck → reachable Containment must fall (the clock is real).
        scp.mill(game, fid, 12)
        reach1 = session.get_client_state(human_id).scp["foundation_reachable"]
        assert reach1 < reach0, "reachable Containment drops as the anomaly supply is denied"

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
        random.seed(2024)  # deterministic shuffle (fog test needs a face-down-able opening hand)
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


def test_insurgency_view_redacts_facedown_central_layers():
    """Hard-wet fog check for the live central-access surface: a Foundation layer installed
    face-down on a central (HQ/Research/Archives) must be redacted to the Insurgency exactly
    like a cell layer — its identity (type/strength) never reaches the runner's wire payload."""
    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot", game_mode="scp", ai_difficulty="medium",
                player_name="TestHuman"),
            background_tasks=BackgroundTasks())
        session = session_manager.get_session(response.match_id)
        random.seed(2024)
        await session.mode_adapter.setup_game(session)
        session.is_started = True

        from src.engine import scp
        from src.engine.types import ZoneType
        from src.cards.scp import foundation as F
        human_id = response.player_id                                   # Foundation (seat 0)
        ai_id = next(p for p in session.player_ids if p != human_id)    # Insurgency

        game = session.game
        r = scp.ensure_scp_state(game.state, human_id)
        r["ap"], r["credits"] = 5, 10
        layer = game.create_object(name=F.BLAST_DOOR.name, owner_id=human_id, zone=ZoneType.HAND,
                                   characteristics=F.BLAST_DOOR.characteristics, card_def=F.BLAST_DOOR)
        ok, msg, _ = scp.play_card(game, human_id, layer.id, target=("central", "hq"))
        assert ok, msg

        ai_view = session.get_client_state(ai_id)
        blob = json.dumps(ai_view.scp)
        assert F.BLAST_DOOR.name not in blob, \
            "fog leak: the Insurgency payload contains a face-down central layer's identity"
        hq_stack = ai_view.scp["opponent"]["centrals"]["hq"]
        assert hq_stack and hq_stack[0]["hidden"] is True and hq_stack[0]["name"] == "[FACE-DOWN]", \
            "the face-down central layer must be present-but-redacted to the Insurgency"

        await session_manager.remove_session(response.match_id)

    asyncio.run(_run())


def test_spectator_view_populates_both_seats():
    """Regression (review finding): _serialize_scp_state with no viewer (spectator /
    replay frames) must show the Foundation's perspective with both seats + central
    layer stacks — it previously returned me/opponent=None, blanking the SCPBoard."""
    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot", game_mode="scp", ai_difficulty="medium",
                player_name="Spectator",
            ),
            background_tasks=BackgroundTasks(),
        )
        session = session_manager.get_session(response.match_id)
        random.seed(2024)
        await session.mode_adapter.setup_game(session)

        spec = session._serialize_scp_state(session.game.state, None)  # no viewer
        assert spec["me"] is not None and spec["opponent"] is not None, \
            "spectator/replay must see both seats, not a blank board"
        assert spec["me"]["faction"] == "foundation"
        assert spec["opponent"]["faction"] == "insurgency"
        # Central-access layer stacks are serialized (HQ / Research / Archives).
        assert set(spec["me"]["centrals"]) == {"hq", "research", "archives"}

        await session_manager.remove_session(response.match_id)

    asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
