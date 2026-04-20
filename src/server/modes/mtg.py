"""
Server-side MTG mode adapter + helpers.

Handles the MTG priority-based game loop. The MTG flow is unusual vs. the
other modes because it pushes actions through the engine's priority_system
rather than a dedicated turn manager. As a result:

- Action/human-input routing for MTG lives on `GameSession` itself (it's
  registered via `game.set_human_action_handler`).
- The LLM-bot helpers (decision-mode gating, prompt building, state
  summarizers) are MTG-specific but are invoked from `GameSession._get_ai_action`
  (the callback engine calls when an AI has priority). Rather than move them
  here and thread `session` through every call, we keep them on the session
  but this module owns the loop + adapter-level setup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import ModeAdapter

if TYPE_CHECKING:
    from src.server.session import GameSession
    from src.server.models import PlayerActionRequest


class MTGModeAdapter(ModeAdapter):
    """MTG adapter: priority-based loop with PendingChoice support."""

    async def setup_game(self, session: "GameSession") -> None:
        # MTG mode needs AI strategy layers precomputed before the first
        # priority decision so Hard/Ultra bots can use their deck+matchup plans.
        await session._prepare_ai_layers()

    async def run_game_loop(self, session: "GameSession") -> None:
        """MTG game loop - runs until human input needed or game ends."""
        while not session.is_finished:
            await session._process_ai_pending_choices()
            await session.game.turn_manager.run_turn()
            await session._process_ai_pending_choices()

            if session.game.is_game_over():
                session.is_finished = True
                session.winner_id = session.game.get_winner()
                break

    async def handle_action(
        self,
        session: "GameSession",
        request: "PlayerActionRequest",
    ) -> tuple[bool, str]:
        # MTG's action flow is handled directly in `GameSession.handle_action`
        # (priority_system-based). This adapter method is not wired for MTG;
        # it is defined for protocol symmetry only.
        return False, "MTG actions are dispatched via GameSession directly"

    async def get_human_action(self, session, player_id, game_state):
        # MTG uses `session._get_human_action` registered on
        # `game.set_human_action_handler`, not a turn_manager callback.
        return await session._get_human_action(player_id, [])
