"""Server-side Minecraft TCG mode adapter."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from src.server.models import GameLogEntry

from .base import ModeAdapter

if TYPE_CHECKING:
    from src.server.session import GameSession
    from src.server.models import PlayerActionRequest


class MinecraftModeAdapter(ModeAdapter):
    async def setup_game(self, session: "GameSession") -> None:
        from src.ai.minecraft_adapter import MinecraftAIAdapter

        difficulty = session.ai_difficulty or "medium"
        if hasattr(difficulty, "value"):
            difficulty = difficulty.value
        ai_adapter = MinecraftAIAdapter(difficulty=str(difficulty).strip().lower())
        if hasattr(session.game.turn_manager, "set_ai_handler"):
            session.game.turn_manager.set_ai_handler(ai_adapter)
        # Treat ultra AIs as humans for mc_human_players (used by mulligan
        # routing) so the engine asks them for keep/mulligan via the human path.
        ultra_ai = set(session.ultra_ai_player_ids)
        session.game.state.turn_data["mc_human_players"] = list(session.human_players | ultra_ai)

        # Detach ultra-AI seats from the engine so its turn dispatch routes
        # them through human_action_handler (resolved by /action).
        session.detach_ultra_from_engine_ai_sets()

        if session.human_players or session.has_ultra_ai:
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
                break

            if session.on_state_change:
                for pid in session.human_players:
                    state = session.get_client_state(pid)
                    await session.on_state_change(pid, state.model_dump())

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
            return {"action_type": "MC_END_TURN"}

    async def handle_action(self, session: "GameSession", request: "PlayerActionRequest") -> tuple[bool, str]:
        # Mulligan decisions arrive during game setup, before any "active player"
        # exists — short-circuit before the turn-order check.
        if request.action_type == "MC_MULLIGAN_DECISION":
            if request.keep is None:
                return False, "MC_MULLIGAN_DECISION requires `keep` (true=keep, false=mulligan)"
            ok = session.resolve_mulligan_decision(request.player_id, bool(request.keep))
            if not ok:
                return False, "No mulligan prompt is currently pending for this player"
            # Push fresh state so the client clears the prompt UI immediately.
            if session.on_state_change:
                state = session.get_client_state(request.player_id)
                await session.on_state_change(request.player_id, state.model_dump())
            return True, "Mulligan decision accepted"

        active_player = session.game.get_active_player()
        combat = session.game.state.minecraft_combat or {}
        is_block_declaration = (
            request.action_type == "MC_DECLARE_BLOCKERS"
            and combat.get("phase") == "declare_blockers"
            and combat.get("defending_player") == request.player_id
        )
        if request.player_id != active_player and not is_block_declaration:
            return False, "Not your turn"

        target_id = request.targets[0][0] if request.targets and request.targets[0] else None
        action_dict: dict[str, Any] = {"action_type": request.action_type}

        if request.action_type == "MC_PLAY_CARD":
            if not request.card_id:
                return False, "MC_PLAY_CARD requires card_id"
            action_dict = {
                "action_type": "MC_PLAY_CARD",
                "card_id": request.card_id,
                "cell": request.cell,
                "target_id": target_id,
                "target_column": request.target_column,
            }
        elif request.action_type == "MC_ASSIGN_WORKER":
            action_dict = {
                "action_type": "MC_ASSIGN_WORKER",
                "worker_id": request.source_id,
                "biome_index": request.biome_index or 0,
            }
        elif request.action_type == "MC_AVATAR_ACTION":
            action_dict = {
                "action_type": "MC_AVATAR_ACTION",
                "kind": request.action_kind or "mine",
                "biome_index": request.biome_index or 0,
                "target_id": target_id,
                "target_column": request.target_column,
            }
        elif request.action_type == "MC_EXPLORE_BIOME":
            action_dict = {
                "action_type": "MC_EXPLORE_BIOME",
                "biome_index": request.biome_index or 0,
            }
        elif request.action_type == "MC_DECLARE_ATTACKERS":
            attacks = list(request.attackers or [])
            if not attacks and request.source_id:
                attacks = [{
                    "attacker_id": request.source_id,
                    "target_id": target_id,
                    "target_column": request.target_column,
                }]
            action_dict = {"action_type": "MC_DECLARE_ATTACKERS", "attackers": attacks}
        elif request.action_type == "MC_DECLARE_BLOCKERS":
            action_dict = {"action_type": "MC_DECLARE_BLOCKERS", "blockers": list(request.blockers or [])}
        elif request.action_type == "MC_END_TURN":
            action_dict = {"action_type": "MC_END_TURN"}
        else:
            return False, "Unknown Minecraft action"

        self.add_log(session, request, action_dict)

        if (
            session._pending_action_future
            and not session._pending_action_future.done()
            and session._pending_player_id == request.player_id
        ):
            is_end_turn = request.action_type == "MC_END_TURN"
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

    def add_log(self, session: "GameSession", request: "PlayerActionRequest", action: dict) -> None:
        player_name = session.player_names.get(request.player_id, "Player")
        text = f"{player_name} acted."
        if request.action_type == "MC_PLAY_CARD":
            card = session.game.state.objects.get(request.card_id or "")
            text = f"{player_name} crafted {card.name if card else 'a card'}."
        elif request.action_type == "MC_ASSIGN_WORKER":
            text = f"{player_name} assigned a worker to mine."
        elif request.action_type == "MC_AVATAR_ACTION":
            text = f"{player_name} used an avatar action."
        elif request.action_type == "MC_DECLARE_ATTACKERS":
            text = f"{player_name} attacked."
        elif request.action_type == "MC_END_TURN":
            text = f"{player_name} ended the turn."
        session._game_log.append(GameLogEntry(
            turn=session.game.turn_manager.turn_number,
            text=text,
            event_type=request.action_type.lower(),
            player=request.player_id,
            timestamp=time.time(),
        ))
