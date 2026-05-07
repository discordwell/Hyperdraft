"""
Server-side Finance TCG mode adapter.

Encapsulates the Finance game loop, human-action handling, and action dispatch
for the 5-phase Finance TCG engine (PRE_MARKET → RESEARCH → TRADING_SESSION →
SETTLEMENT → MARKET_CLOSE).
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from src.server.models import GameLogEntry

from .base import ModeAdapter

if TYPE_CHECKING:
    from src.server.session import GameSession
    from src.server.models import PlayerActionRequest


class FinanceModeAdapter(ModeAdapter):
    """Finance TCG server adapter."""

    async def setup_game(self, session: "GameSession") -> None:
        from src.ai.finance_adapter import FinanceAIAdapter

        # Resolve global difficulty from session.
        if session.ai_profiles_by_player:
            first_profile = next(iter(session.ai_profiles_by_player.values()))
            difficulty = first_profile.get("difficulty", session.ai_difficulty or "medium")
        else:
            difficulty = session.ai_difficulty or "medium"
        if hasattr(difficulty, "value"):
            difficulty = difficulty.value
        difficulty = str(difficulty).strip().lower()

        tm = session.game.turn_manager

        # Register AI handlers per AI player.
        ai_player_ids = [pid for pid in session.player_ids if pid not in session.human_players]
        for pid in ai_player_ids:
            profile = session.ai_profiles_by_player.get(pid) or {}
            player_diff = profile.get("difficulty", difficulty)
            adapter = FinanceAIAdapter(difficulty=str(player_diff).strip().lower())
            if hasattr(tm, "set_ai_handler"):
                tm.set_ai_handler(pid, adapter)

        # Wire the combat manager onto the turn manager (it's built separately by Game.__init__).
        if hasattr(tm, "finance_combat_manager") and tm.finance_combat_manager is None:
            combat_mgr = getattr(session.game, "combat_manager", None)
            if combat_mgr is not None:
                tm.finance_combat_manager = combat_mgr

        # Wire human action handler.
        if session.human_players and hasattr(tm, "human_action_handler"):
            tm.human_action_handler = (
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
                break

            if session.on_state_change:
                for pid in session.human_players:
                    state = session.get_client_state(pid)
                    await session.on_state_change(pid, state.model_dump())

    async def get_human_action(
        self, session: "GameSession", player_id: str, game_state: Any
    ) -> dict:
        """Block until the client submits a Finance action."""
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
            return {"action_type": "FIN_END_TURN"}

    async def handle_action(
        self,
        session: "GameSession",
        request: "PlayerActionRequest",
    ) -> tuple[bool, str]:
        """Dispatch a Finance player action to the pending turn-manager future."""
        active_player = session.game.get_active_player()

        # Blockers can come from the non-active player during the opponent's
        # TRADING_SESSION combat sub-phase.
        is_block_declaration = request.action_type == "FIN_DECLARE_BLOCKERS"
        if request.player_id != active_player and not is_block_declaration:
            return False, "Not your turn"

        target_id = request.targets[0][0] if request.targets and request.targets[0] else None
        action_dict: dict[str, Any] = {"action_type": request.action_type}

        if request.action_type == "FIN_PLAY_CARD":
            if not request.card_id:
                return False, "FIN_PLAY_CARD requires card_id"
            action_dict = {
                "action_type": "FIN_PLAY_CARD_ACTION",
                "card_id": request.card_id,
                "targets": [target_id] if target_id else [],
            }
        elif request.action_type == "FIN_ACTIVATE_ABILITY":
            action_dict = {
                "action_type": "FIN_ACTIVATE_ABILITY",
                "source_id": request.source_id,
                "ability_index": request.ability_index if hasattr(request, "ability_index") else 0,
                "targets": [target_id] if target_id else [],
            }
        elif request.action_type == "FIN_DECLARE_ATTACKERS":
            attackers = list(request.attackers or [])
            if not attackers and request.source_id:
                attackers = [request.source_id]
            action_dict = {
                "action_type": "FIN_DECLARE_ATTACKERS",
                "attackers": attackers,
            }
        elif request.action_type == "FIN_DECLARE_BLOCKERS":
            blocks = dict(request.blockers or {}) if hasattr(request, "blockers") and isinstance(request.blockers, dict) else {}
            if not blocks and request.source_id and target_id:
                # source_id = blocker, target_id = attacker it's blocking
                blocks = {target_id: request.source_id}
            action_dict = {
                "action_type": "FIN_DECLARE_BLOCKERS",
                "blocks": blocks,
            }
        elif request.action_type in ("FIN_END_PHASE", "FIN_END_TURN"):
            action_dict = {"action_type": request.action_type}
        else:
            return False, f"Unknown Finance action: {request.action_type}"

        self._add_log(session, request, action_dict)

        if (
            session._pending_action_future
            and not session._pending_action_future.done()
            and session._pending_player_id == request.player_id
        ):
            is_end_turn = request.action_type in ("FIN_END_TURN", "FIN_END_PHASE")
            pending_future = session._pending_action_future
            processed_event = session._action_processed_event

            session._pending_action_future.set_result(action_dict)
            session._record_frame(action=request.model_dump())

            timeout = 30.0 if is_end_turn else 5.0
            if processed_event:
                try:
                    await asyncio.wait_for(processed_event.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    pass

            if session._pending_action_future is pending_future:
                session._pending_action_future = None
                session._pending_player_id = None
            if session._action_processed_event is processed_event:
                session._action_processed_event = None

            await asyncio.sleep(0.05)
            return True, "Action accepted"

        return False, "No pending action expected"

    def _add_log(
        self,
        session: "GameSession",
        request: "PlayerActionRequest",
        action: dict,
    ) -> None:
        player_name = session.player_names.get(request.player_id, "Player")
        text = f"{player_name} acted."
        if request.action_type == "FIN_PLAY_CARD":
            card = session.game.state.objects.get(request.card_id or "")
            text = f"{player_name} played {card.name if card else 'a card'}."
        elif request.action_type == "FIN_DECLARE_ATTACKERS":
            text = f"{player_name} declared attackers."
        elif request.action_type == "FIN_DECLARE_BLOCKERS":
            text = f"{player_name} declared blockers."
        elif request.action_type == "FIN_ACTIVATE_ABILITY":
            text = f"{player_name} activated an ability."
        elif request.action_type == "FIN_END_PHASE":
            text = f"{player_name} ended the phase."
        tm = session.game.turn_manager
        if request.action_type == "FIN_END_TURN":
            phase = getattr(getattr(tm, "fin_turn_state", None), "phase", None)
            phase_name = phase.name if phase else ""
            if phase_name == "TRADING_SESSION":
                text = f"{player_name} closed the market."
            else:
                text = f"{player_name} ended the turn."
        turn = getattr(tm, "turn_number", 0)
        session._game_log.append(GameLogEntry(
            turn=turn,
            text=text,
            event_type=request.action_type.lower(),
            player=request.player_id,
            timestamp=time.time(),
        ))
