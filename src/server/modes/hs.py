"""
Server-side Hearthstone mode adapter.

Encapsulates the HS game loop, human-action handling, action dispatch, and
hero-power query helpers that used to live on GameSession.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any, Optional

from .base import ModeAdapter

if TYPE_CHECKING:
    from src.server.session import GameSession
    from src.server.models import PlayerActionRequest


class HearthstoneModeAdapter(ModeAdapter):
    """Hearthstone adapter."""

    async def setup_game(self, session: "GameSession") -> None:
        from src.ai.hearthstone_adapter import HearthstoneAIAdapter

        if session.ai_profiles_by_player:
            first_profile = next(iter(session.ai_profiles_by_player.values()))
            difficulty = first_profile.get("difficulty", session.ai_difficulty or "medium")
        else:
            difficulty = session.ai_difficulty or "medium"
        if hasattr(difficulty, "value"):
            difficulty = difficulty.value
        difficulty = str(difficulty).strip().lower()

        ai_adapter = HearthstoneAIAdapter(difficulty=difficulty)

        # Per-player difficulty overrides for bot-vs-bot
        for pid, profile in session.ai_profiles_by_player.items():
            player_diff = profile.get("difficulty", difficulty)
            ai_adapter.player_difficulties[pid] = player_diff

        session.game.set_hearthstone_ai_handler(ai_adapter)

        # Wire human action handler for HS mode with human players
        if session.human_players:
            session.game.turn_manager.human_action_handler = (
                lambda pid, gs: self.get_human_action(session, pid, gs)
            )

    async def run_game_loop(self, session: "GameSession") -> None:
        """
        Hearthstone game loop.

        run_turn() blocks during human turns (via future) and auto-executes
        AI turns, so we just keep calling it in a loop.
        """
        while not session.is_finished:
            await session.game.turn_manager.run_turn()

            if session.game.is_game_over():
                session.is_finished = True
                session.winner_id = session.game.get_winner()
                # Notify clients of game over
                if session.on_state_change:
                    for pid in session.human_players:
                        state = session.get_client_state(pid)
                        await session.on_state_change(pid, state.model_dump())
                break

            # After each turn completes, broadcast updated state
            if session.on_state_change:
                for pid in session.human_players:
                    state = session.get_client_state(pid)
                    await session.on_state_change(pid, state.model_dump())

    async def get_human_action(
        self, session: "GameSession", player_id: str, game_state: Any
    ) -> dict:
        """
        Callback for HearthstoneTurnManager.human_action_handler.

        Blocks (via asyncio.Future) until the client submits an HS action.
        Returns an action dict with 'action_type' and relevant fields.
        """
        # Signal that the *previous* action has been fully processed
        if session._action_processed_event:
            session._action_processed_event.set()
            session._action_processed_event = None

        loop = asyncio.get_event_loop()
        session._pending_action_future = loop.create_future()
        session._pending_player_id = player_id
        session._action_processed_event = asyncio.Event()

        # Notify the client they need to act (send updated state)
        if session.on_state_change:
            for pid in session.human_players:
                state = session.get_client_state(pid)
                await session.on_state_change(pid, state.model_dump())

        # Wait for the action
        try:
            action = await asyncio.wait_for(session._pending_action_future, timeout=300.0)
            return action
        except asyncio.TimeoutError:
            return {"action_type": "HS_END_TURN"}

    async def handle_action(
        self,
        session: "GameSession",
        request: "PlayerActionRequest",
    ) -> tuple[bool, str]:
        """
        Handle a Hearthstone-specific player action.

        Validates the player is active and resolves the pending future.
        """
        # Validate it's this player's turn
        active_player = session.game.get_active_player()
        if request.player_id != active_player:
            return False, "Not your turn"

        # Build HS action dict from the request
        target_id = request.targets[0][0] if request.targets and request.targets[0] else None

        # Validate attack has required fields
        if request.action_type == "HS_ATTACK":
            if not request.source_id:
                return False, "Attack requires an attacker (source_id)"
            if not target_id:
                return False, "Attack requires a target"
        elif request.action_type == "HS_ATTUNE_CARD":
            if not request.card_id:
                return False, "Attune requires a card_id from hand"

        action_dict = {
            "action_type": request.action_type,
            "card_id": request.card_id,
            "attacker_id": request.source_id,  # source_id used for attacker
            "target_id": target_id,
        }

        # If we're waiting for this player's input, resolve the future
        if (
            session._pending_action_future
            and not session._pending_action_future.done()
            and session._pending_player_id == request.player_id
        ):

            is_end_turn = request.action_type == "HS_END_TURN"
            pending_future = session._pending_action_future
            processed_event = session._action_processed_event

            session._pending_action_future.set_result(action_dict)

            # Record the action
            session._record_frame(action=request.model_dump())

            # For end turn, the human loop breaks and won't call get_human_action
            # again, so we wait longer for the AI turn + next human draw to complete.
            timeout = 30.0 if is_end_turn else 5.0

            if processed_event:
                try:
                    await asyncio.wait_for(processed_event.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    pass

            # Clear only the action context we resolved. The game loop may have
            # already created the next turn's pending future by now.
            if session._pending_action_future is pending_future:
                session._pending_action_future = None
                session._pending_player_id = None
            if session._action_processed_event is processed_event:
                session._action_processed_event = None

            # Yield briefly so the turn manager loop can advance
            await asyncio.sleep(0.05)

            return True, "Action accepted"

        return False, "No pending action expected"

    # --- Hero power queries ----------------------------------------------
    def get_hero_power_name(self, session: "GameSession", player: Any) -> Optional[str]:
        if not player.hero_power_id:
            return None
        hp = session.game.state.objects.get(player.hero_power_id)
        return hp.name if hp else None

    def get_hero_power_cost(self, session: "GameSession", player: Any) -> int:
        if not player.hero_power_id:
            return 2
        hp = session.game.state.objects.get(player.hero_power_id)
        if hp and hp.characteristics.mana_cost:
            nums = re.findall(r"\{(\d+)\}", hp.characteristics.mana_cost)
            return sum(int(n) for n in nums) if nums else 2
        return 2

    def get_hero_power_text(self, session: "GameSession", player: Any) -> Optional[str]:
        if not player.hero_power_id:
            return None
        hp = session.game.state.objects.get(player.hero_power_id)
        return hp.card_def.text if hp and hp.card_def else None
