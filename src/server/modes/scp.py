"""Server-side SCP Containment TCG mode adapter."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from .base import ModeAdapter

if TYPE_CHECKING:
    from src.server.session import GameSession
    from src.server.models import PlayerActionRequest


class SCPModeAdapter(ModeAdapter):
    async def setup_game(self, session: "GameSession") -> None:
        from src.ai.scp_adapter import SCPAIAdapter

        difficulty = session.ai_difficulty or "medium"
        if hasattr(difficulty, "value"):
            difficulty = difficulty.value
        ai_adapter = SCPAIAdapter(difficulty=str(difficulty).strip().lower())
        if hasattr(session.game.turn_manager, "set_ai_handler"):
            session.game.turn_manager.set_ai_handler(ai_adapter)

        if session.human_players or session.has_ultra_ai:
            session.detach_ultra_from_engine_ai_sets()
            session.game.turn_manager.human_action_handler = (
                lambda pid, gs: self.get_human_action(session, pid, gs)
            )

    async def run_game_loop(self, session: "GameSession") -> None:
        while not session.is_finished:
            await session.game.turn_manager.run_turn()
            if session.game.is_game_over():
                session.is_finished = True
                session.winner_id = session.game.get_winner()
            if session.on_state_change:
                for pid in session.human_players:
                    state = session.get_client_state(pid)
                    await session.on_state_change(pid, state.model_dump())
            if session.is_finished:
                break

    async def get_human_action(self, session: "GameSession", player_id: str, game_state: Any) -> dict:
        if session._action_processed_event:
            session._action_processed_event.set()
            session._action_processed_event = None
        loop = asyncio.get_event_loop()
        session._pending_action_future = loop.create_future()
        session._pending_player_id = player_id
        session._action_processed_event = asyncio.Event()
        if session.on_state_change:
            for pid in session.human_players:
                state = session.get_client_state(pid)
                await session.on_state_change(pid, state.model_dump())
        try:
            return await asyncio.wait_for(session._pending_action_future, timeout=300.0)
        except asyncio.TimeoutError:
            return {"action_type": "SCP_END_TURN"}

    async def handle_action(self, session: "GameSession", request: "PlayerActionRequest") -> tuple[bool, str]:
        active_player = session.game.get_active_player()
        if request.player_id != active_player:
            return False, "Not your turn"

        action_dict: dict[str, Any] = {"action_type": request.action_type}
        if request.action_type == "SCP_OPEN_DOSSIER":
            if not request.card_id:
                return False, "SCP_OPEN_DOSSIER requires card_id"
            action_dict = {
                "action_type": "SCP_OPEN_DOSSIER",
                "card_id": request.card_id,
                "fast_track": request.fast_track,
                "sealed": request.sealed,
            }
        elif request.action_type == "SCP_REVEAL_DOSSIER":
            action_dict = {"action_type": "SCP_REVEAL_DOSSIER", "object_id": request.source_id or request.anomaly_id}
        elif request.action_type in {"SCP_RESEARCH", "SCP_CONTAIN", "SCP_SUPPRESS"}:
            action_dict = {
                "action_type": request.action_type,
                "anomaly_id": request.anomaly_id or request.source_id,
                "staff_ids": list(request.staff_ids or []),
            }
        elif request.action_type == "SCP_SPEND_ETHICS":
            action_dict = {
                "action_type": "SCP_SPEND_ETHICS",
                "amount": request.amount or request.x_value,
                "mode": request.action_kind or "",
            }
        elif request.action_type == "SCP_SHIFT_MOOD":
            action_dict = {
                "action_type": "SCP_SHIFT_MOOD",
                "anomaly_id": request.anomaly_id or request.source_id,
                "mood": request.mood or request.action_kind or "",
            }
        elif request.action_type == "SCP_CROSS_CONTAIN":
            action_dict = {
                "action_type": "SCP_CROSS_CONTAIN",
                "contained_id": request.contained_id,
                "active_id": request.active_id or request.anomaly_id,
            }
        elif request.action_type == "SCP_MEMORY_HOLE":
            action_dict = {"action_type": "SCP_MEMORY_HOLE", "object_id": request.source_id}
        elif request.action_type == "SCP_APPLY_PROTOCOL":
            action_dict = {
                "action_type": "SCP_APPLY_PROTOCOL",
                "anomaly_id": request.anomaly_id or request.source_id,
                "protocol": request.protocol or request.action_kind or "",
            }
        elif request.action_type == "SCP_RESOLVE_INCIDENT":
            action_dict = {
                "action_type": "SCP_RESOLVE_INCIDENT",
                "index": request.index or 0,
            }
        elif request.action_type == "SCP_END_TURN":
            action_dict = {"action_type": "SCP_END_TURN"}
        else:
            return False, "Unknown SCP action"

        if not (
            session._pending_action_future
            and not session._pending_action_future.done()
            and session._pending_player_id == request.player_id
        ):
            return False, "No SCP action is currently pending for this player"

        is_end_turn = request.action_type == "SCP_END_TURN"
        pending_future = session._pending_action_future
        processed_event = session._action_processed_event
        session._pending_action_future.set_result(action_dict)
        session._record_frame(action=request.model_dump())
        if is_end_turn:
            if processed_event:
                processed_event.set()
            if session._pending_action_future is pending_future:
                session._pending_action_future = None
                session._pending_player_id = None
            if session._action_processed_event is processed_event:
                session._action_processed_event = None
            return True, "Action submitted"
        if processed_event:
            try:
                await asyncio.wait_for(processed_event.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
        if session._pending_action_future is pending_future:
            session._pending_action_future = None
            session._pending_player_id = None
        if session._action_processed_event is processed_event:
            session._action_processed_event = None
        await asyncio.sleep(0.05)
        return True, "Action submitted"
