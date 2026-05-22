"""
Server-side Depths: Submarine Fleet mode adapter.

Encapsulates the Depths game loop, human-action handling, and action dispatch
for the 5-phase Depths engine (DIVE → MANEUVER → ENGAGEMENT → REGROUP → SURFACE).

Mirrors finance.py structure exactly.
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


class DepthsModeAdapter(ModeAdapter):
    """Depths: Submarine Fleet server adapter."""

    async def setup_game(self, session: "GameSession") -> None:
        from src.ai.depths_adapter import DepthsAIAdapter

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

        # Register AI handlers per AI player. Skip ultra-AI players — those
        # are driven externally via /action (an external Claude Code agent).
        ai_player_ids = [pid for pid in session.player_ids if pid not in session.human_players]
        for pid in ai_player_ids:
            if session.is_ultra_ai_player(pid):
                continue
            profile = session.ai_profiles_by_player.get(pid) or {}
            player_diff = profile.get("difficulty", difficulty)
            adapter = DepthsAIAdapter(difficulty=str(player_diff).strip().lower())
            if hasattr(tm, "set_ai_handler"):
                tm.set_ai_handler(adapter, pid)
            if hasattr(tm, "set_ai_player"):
                tm.set_ai_player(pid)

        # Detach ultra-AI seats so the depths turn manager routes them via
        # human_action_handler (resolved by /action).
        session.detach_ultra_from_engine_ai_sets()

        # Wire human action handler (humans OR ultra AIs).
        if (session.human_players or session.has_ultra_ai) and hasattr(tm, "human_action_handler"):
            tm.human_action_handler = (
                lambda pid, gs: self.get_human_action(session, pid, gs)
            )

    async def run_game_loop(self, session: "GameSession") -> None:
        tm = session.game.turn_manager
        while not session.is_finished:
            await tm.run_turn()

            # Per-turn replay frame: Depths bypasses the MTG priority
            # pipeline — see pkm.py for the longer rationale.
            if session.record_actions_for_replay:
                active = session.game.get_active_player()
                turn_number = getattr(tm, "turn_number", 0)
                session._record_frame(action={
                    "kind": "turn_complete",
                    "player_id": active,
                    "player_name": session.player_names.get(active, active or ""),
                    "action_type": "DEPTHS_TURN_COMPLETE",
                    "turn": turn_number,
                })

            if session.game.is_game_over():
                session.is_finished = True
                session.winner_id = session.game.get_winner()
                if session.on_state_change:
                    for pid in session.player_ids:
                        state = session.get_client_state(pid)
                        await session.on_state_change(pid, state.model_dump())
                break

            if session.on_state_change:
                for pid in session.player_ids:
                    state = session.get_client_state(pid)
                    await session.on_state_change(pid, state.model_dump())

    async def get_human_action(
        self, session: "GameSession", player_id: str, game_state: Any
    ) -> dict:
        """Block until the client submits a Depths action.

        If the session has _depths_ending_turn set, auto-resolve with
        DEPTHS_END_TURN so a single button click skips through all
        remaining human-action phases (MANEUVER → REGROUP) in one shot.
        """
        if session._action_processed_event:
            session._action_processed_event.set()
            session._action_processed_event = None

        # Auto-forward through remaining phases when the human clicked end-turn.
        if getattr(session, "_depths_ending_turn", False):
            # Clear on the last phase (regroup) so the AI's turn resets it.
            # We can't know which phase this is easily, so we trust the turn
            # manager to call us only twice (maneuver + regroup). Use a counter.
            count = getattr(session, "_depths_end_turn_count", 0)
            session._depths_end_turn_count = count + 1
            if count >= 1:
                # Second call = regroup. After this the human's turn ends.
                session._depths_ending_turn = False
                session._depths_end_turn_count = 0
            return {"action_type": "DEPTHS_END_TURN"}

        loop = asyncio.get_event_loop()
        session._pending_action_future = loop.create_future()
        session._pending_player_id = player_id
        session._action_processed_event = asyncio.Event()

        if session.on_state_change:
            for pid in session.player_ids:
                state = session.get_client_state(pid)
                await session.on_state_change(pid, state.model_dump())

        try:
            action = await asyncio.wait_for(session._pending_action_future, timeout=300.0)
            session._depths_consecutive_timeouts = 0
            return action
        except asyncio.TimeoutError:
            # Dead-LLM short-circuit — see pkm.py.
            session._depths_consecutive_timeouts = (
                getattr(session, "_depths_consecutive_timeouts", 0) + 1
            )
            if session._depths_consecutive_timeouts >= 3:
                session.is_finished = True
            return {"action_type": "DEPTHS_END_TURN"}

    async def handle_action(
        self,
        session: "GameSession",
        request: "PlayerActionRequest",
    ) -> tuple[bool, str]:
        """Dispatch a Depths player action to the pending turn-manager future."""
        active_player = session.game.get_active_player()

        # Detection and interceptor responses can come from the non-active player.
        non_active_actions = {"DEPTHS_DETECT", "DEPTHS_DECLARE_INTERCEPTORS"}
        if request.player_id != active_player and request.action_type not in non_active_actions:
            return False, "Not your turn"

        action_dict: dict[str, Any] = {"action_type": request.action_type}

        atype = request.action_type

        if atype in ("DEPTHS_DEPLOY_VESSEL", "DEPTHS_PLAY_CARD"):
            if not request.card_id:
                return False, "DEPTHS_DEPLOY_VESSEL requires card_id"
            action_dict = {
                "action_type": "DEPTHS_DEPLOY_VESSEL",
                "card_id": request.card_id,
                "depth_band": getattr(request, "depth_band", None),
            }
        elif atype == "DEPTHS_DIVE":
            vessel_id = getattr(request, "vessel_id", None) or request.source_id
            action_dict = {
                "action_type": "DEPTHS_DIVE",
                "vessel_id": vessel_id,
            }
        elif atype in ("DEPTHS_SURFACE_VESSEL", "DEPTHS_SURFACE"):
            vessel_id = getattr(request, "vessel_id", None) or request.source_id
            action_dict = {
                "action_type": "DEPTHS_SURFACE_VESSEL",
                "vessel_id": vessel_id,
            }
        elif atype == "DEPTHS_ATTACH":
            action_dict = {
                "action_type": "DEPTHS_ATTACH",
                "card_id": request.card_id,
                "target_id": request.targets[0][0] if request.targets and request.targets[0] else None,
            }
        elif atype == "DEPTHS_CAST_SPELL":
            action_dict = {
                "action_type": "DEPTHS_CAST_SPELL",
                "card_id": request.card_id,
                "targets": [row[0] for row in request.targets if row] if request.targets else [],
            }
        elif atype == "DEPTHS_LAY_MINE":
            action_dict = {
                "action_type": "DEPTHS_LAY_MINE",
                "card_id": request.card_id,
                "depth_band": getattr(request, "depth_band", None),
            }
        elif atype == "DEPTHS_ACTIVATE_ABILITY":
            action_dict = {
                "action_type": "DEPTHS_ACTIVATE_ABILITY",
                "source_id": request.source_id,
                "ability_index": getattr(request, "ability_index", 0),
                "targets": [row[0] for row in request.targets if row] if request.targets else [],
            }
        elif atype == "DEPTHS_DECLARE_ATTACKERS":
            attackers = list(request.attackers or [])
            action_dict = {
                "action_type": "DEPTHS_DECLARE_ATTACKERS",
                "attackers": attackers,
            }
        elif atype == "DEPTHS_DETECT":
            # detect_targets comes from the hook as a flat list in attackers field
            detect_targets = []
            if request.attackers:
                detect_targets = [a.get("attacker_id") for a in request.attackers if a.get("attacker_id")]
            if not detect_targets and request.targets:
                detect_targets = [row[0] for row in request.targets if row]
            action_dict = {
                "action_type": "DEPTHS_DETECT",
                "detect_targets": detect_targets,
            }
        elif atype == "DEPTHS_DECLARE_INTERCEPTORS":
            interceptors = list(request.attackers or [])
            action_dict = {
                "action_type": "DEPTHS_DECLARE_INTERCEPTORS",
                "interceptors": interceptors,
            }
        elif atype == "DEPTHS_END_TURN":
            action_dict = {"action_type": "DEPTHS_END_TURN"}
            # Signal get_human_action to auto-forward through remaining phases.
            # Only set this flag for actual human players — an ultra-AI agent
            # submits explicit per-phase actions and shouldn't poison the next
            # player's turn with the auto-skip flag.
            if request.player_id in session.human_players:
                session._depths_ending_turn = True
                session._depths_end_turn_count = 0
        else:
            return False, f"Unknown Depths action: {atype}"

        self._add_log(session, request, action_dict)

        if (
            session._pending_action_future
            and not session._pending_action_future.done()
            and session._pending_player_id == request.player_id
        ):
            is_end_turn = atype in ("DEPTHS_END_TURN",)
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
        atype = request.action_type
        if atype == "DEPTHS_DEPLOY_VESSEL":
            card = session.game.state.objects.get(request.card_id or "")
            text = f"{player_name} deployed {card.name if card else 'a vessel'}."
        elif atype == "DEPTHS_DECLARE_ATTACKERS":
            text = f"{player_name} declared attackers."
        elif atype == "DEPTHS_DETECT":
            text = f"{player_name} resolved detection."
        elif atype == "DEPTHS_DECLARE_INTERCEPTORS":
            text = f"{player_name} declared interceptors."
        elif atype == "DEPTHS_DIVE":
            text = f"{player_name} dived a vessel."
        elif atype == "DEPTHS_SURFACE_VESSEL":
            text = f"{player_name} surfaced a vessel."
        elif atype == "DEPTHS_LAY_MINE":
            text = f"{player_name} laid a mine."
        elif atype == "DEPTHS_CAST_SPELL":
            text = f"{player_name} cast a spell."
        elif atype == "DEPTHS_ACTIVATE_ABILITY":
            text = f"{player_name} activated an ability."
        elif atype == "DEPTHS_END_TURN":
            text = f"{player_name} ended the turn."
        else:
            text = f"{player_name} acted."
        tm = session.game.turn_manager
        turn = getattr(tm, "turn_number", 0)
        session._game_log.append(GameLogEntry(
            turn=turn,
            text=text,
            event_type=atype.lower(),
            player=request.player_id,
            timestamp=time.time(),
        ))
