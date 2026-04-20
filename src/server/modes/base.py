"""
Server-side ModeAdapter base class.

Each game mode (MTG, Hearthstone, Pokemon, Yu-Gi-Oh!) implements these hooks
so `GameSession` can stay mode-agnostic. The set of methods is the MINIMUM
needed for the orchestrator to delegate cleanly.

Note: the upstream `GameModeAdapter` in `src/engine/mode_adapter.py` handles
engine-level concerns. This class is a separate *server*-side adapter that
deals with socket-facing orchestration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.server.session import GameSession
    from src.server.models import (
        CardData,
        PlayerActionRequest,
    )


class ModeAdapter:
    """
    Base mode adapter. Concrete modes override as needed.

    All methods receive the `GameSession` explicitly rather than being bound
    to it — adapters are stateless singletons; per-session state lives on the
    session itself.
    """

    # --- Setup / teardown -------------------------------------------------
    async def setup_game(self, session: "GameSession") -> None:  # noqa: D401
        """
        Per-mode setup invoked from `GameSession.start_game`, after session
        flags are set but before `game.start_game()`.

        Default: no-op.
        """
        return None

    # --- Game loop --------------------------------------------------------
    async def run_game_loop(self, session: "GameSession") -> None:
        """Run the main game loop until human input needed or game ends."""
        raise NotImplementedError

    # --- Action handling --------------------------------------------------
    async def handle_action(
        self,
        session: "GameSession",
        request: "PlayerActionRequest",
    ) -> tuple[bool, str]:
        """
        Handle a mode-specific player action. Return (success, message).

        Only called when `session.handle_action` has already confirmed this
        action belongs to the current mode.
        """
        raise NotImplementedError

    # --- Human input callback (registered on turn_manager) ---------------
    async def get_human_action(
        self,
        session: "GameSession",
        player_id: str,
        game_state: Any,
    ) -> Any:
        """Block until the client submits an action. Return action dict."""
        raise NotImplementedError

    # --- Card serialization ----------------------------------------------
    def serialize_card(self, session: "GameSession", obj: Any, **kwargs: Any) -> "CardData":
        """Serialize a card/permanent for the client."""
        return session._serialize_card(obj)

    # --- Hero power (HS-specific, no-op elsewhere) -----------------------
    def get_hero_power_name(self, session: "GameSession", player: Any) -> Optional[str]:
        return None

    def get_hero_power_cost(self, session: "GameSession", player: Any) -> int:
        return 0

    def get_hero_power_text(self, session: "GameSession", player: Any) -> Optional[str]:
        return None
