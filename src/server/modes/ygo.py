"""
Server-side Yu-Gi-Oh! mode adapter.

Encapsulates the YGO game loop, human-action handling, action dispatch,
action logging/validation, and YGO-specific card serialization.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, Optional

from src.engine import ZoneType
from src.server.models import GameLogEntry

from .base import ModeAdapter

if TYPE_CHECKING:
    from src.server.session import GameSession
    from src.server.models import CardData, PlayerActionRequest


class YugiohModeAdapter(ModeAdapter):
    """Yu-Gi-Oh! adapter."""

    async def setup_game(self, session: "GameSession") -> None:
        from src.ai.yugioh_adapter import YugiohAIAdapter

        if session.ai_profiles_by_player:
            first_profile = next(iter(session.ai_profiles_by_player.values()))
            difficulty = first_profile.get("difficulty", session.ai_difficulty or "medium")
        else:
            difficulty = session.ai_difficulty or "medium"
        if hasattr(difficulty, "value"):
            difficulty = difficulty.value
        difficulty = str(difficulty).strip().lower()

        ai_adapter = YugiohAIAdapter(difficulty=difficulty)
        if session.ygo_ai_strategy:
            ai_adapter.strategy = session.ygo_ai_strategy
        session.game.turn_manager.set_ai_handler(ai_adapter)

        # Wire human action handler and log callback for YGO mode
        if session.human_players:
            session.game.turn_manager.human_action_handler = (
                lambda pid, gs: self.get_human_action(session, pid, gs)
            )
        session.game.turn_manager.action_log_callback = (
            lambda text, event_type, player=None: self.add_log(session, text, event_type, player)
        )

        # Setup game (shuffle, draw 5, coin flip)
        await session.game.turn_manager.setup_game()

    async def run_game_loop(self, session: "GameSession") -> None:
        """
        Yu-Gi-Oh! game loop.

        run_turn() blocks during human turns (via future) and auto-executes
        AI turns, so we just keep calling it in a loop.
        """
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

            # Broadcast updated state after each turn
            if session.on_state_change:
                for pid in session.human_players:
                    state = session.get_client_state(pid)
                    await session.on_state_change(pid, state.model_dump())

    async def get_human_action(
        self, session: "GameSession", player_id: str, game_state: Any
    ) -> dict:
        """
        Callback for YugiohTurnManager.human_action_handler.

        Blocks (via asyncio.Future) until the client submits a YGO action.
        """
        turn = session.game.turn_manager.turn_number if hasattr(session.game.turn_manager, "turn_number") else 0
        player_name = session.player_names.get(player_id, "Player")
        if (
            not session._game_log
            or session._game_log[-1].turn != turn
            or session._game_log[-1].event_type != "turn_start"
        ):
            self.add_log(session, f"Turn {turn} - {player_name}'s turn.", "turn_start", player_id)

        if session._action_processed_event:
            session._action_processed_event.set()
            session._action_processed_event = None

        loop = asyncio.get_event_loop()
        session._pending_action_future = loop.create_future()
        session._pending_player_id = player_id
        session._action_processed_event = asyncio.Event()

        # Notify the client they need to act
        if session.on_state_change:
            for pid in session.human_players:
                state = session.get_client_state(pid)
                await session.on_state_change(pid, state.model_dump())

        try:
            action = await asyncio.wait_for(session._pending_action_future, timeout=300.0)
            return action
        except asyncio.TimeoutError:
            return {"action_type": "end_phase"}

    async def handle_action(
        self,
        session: "GameSession",
        request: "PlayerActionRequest",
    ) -> tuple[bool, str]:
        """Handle a Yu-Gi-Oh!-specific player action."""
        active_player = session.game.get_active_player()
        if request.player_id != active_player:
            return False, "Not your turn"

        # Pre-validate common failure cases so we can return clear errors
        error = self._validate_action(session, request)
        if error:
            return False, error

        target_id = request.targets[0][0] if request.targets and request.targets[0] else None

        # Build YGO action dict matching yugioh_turn.py expectations
        action_dict: dict = {"action_type": request.action_type}

        if request.action_type == "YGO_NORMAL_SUMMON":
            action_dict = {"action_type": "normal_summon", "card_id": request.card_id}
        elif request.action_type == "YGO_SET_MONSTER":
            action_dict = {"action_type": "set_monster", "card_id": request.card_id}
        elif request.action_type == "YGO_FLIP_SUMMON":
            action_dict = {"action_type": "flip_summon", "card_id": request.card_id}
        elif request.action_type == "YGO_CHANGE_POSITION":
            action_dict = {"action_type": "change_position", "card_id": request.card_id}
        elif request.action_type == "YGO_ACTIVATE":
            action_dict = {
                "action_type": "activate_spell",
                "card_id": request.card_id,
                "targets": [target_id] if target_id else [],
            }
        elif request.action_type == "YGO_SET_SPELL_TRAP":
            action_dict = {"action_type": "set_spell_trap", "card_id": request.card_id}
        elif request.action_type == "YGO_DECLARE_ATTACK":
            action_dict = {
                "action_type": "declare_attack",
                "attacker_id": request.source_id or request.card_id,
                "target_id": target_id,
            }
        elif request.action_type == "YGO_DIRECT_ATTACK":
            action_dict = {
                "action_type": "declare_attack",
                "attacker_id": request.source_id or request.card_id,
                "target_id": None,
            }
        elif request.action_type == "YGO_END_TURN":
            action_dict = {"action_type": "end_turn"}
        elif request.action_type == "YGO_END_PHASE":
            action_dict = {"action_type": "end_phase"}
        elif request.action_type == "YGO_SPECIAL_SUMMON":
            action_dict = {"action_type": "special_summon", "card_id": request.card_id}

        # Log the action
        self.log_action(session, request, action_dict)

        # Resolve the pending future
        if (
            session._pending_action_future
            and not session._pending_action_future.done()
            and session._pending_player_id == request.player_id
        ):

            is_end = request.action_type in ("YGO_END_TURN", "YGO_END_PHASE")
            pending_future = session._pending_action_future
            processed_event = session._action_processed_event

            session._pending_action_future.set_result(action_dict)
            session._record_frame(action=request.model_dump())

            timeout = 30.0 if is_end else 5.0

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

    # --- Action logging ---------------------------------------------------

    def log_action(
        self,
        session: "GameSession",
        request: "PlayerActionRequest",
        action_dict: dict,
    ) -> None:
        """Generate a log entry for a Yu-Gi-Oh! action."""
        player_name = session.player_names.get(request.player_id, "Player")
        action = request.action_type

        if action in ("YGO_END_TURN", "YGO_END_PHASE"):
            self.add_log(session, f"{player_name} ended their turn.", "turn_end", request.player_id)
        elif action == "YGO_NORMAL_SUMMON":
            card_obj = session.game.state.objects.get(request.card_id) if request.card_id else None
            card_name = card_obj.name if card_obj else "a monster"
            self.add_log(session, f"{player_name} Normal Summoned {card_name}!", "summon", request.player_id)
        elif action == "YGO_SET_MONSTER":
            self.add_log(session, f"{player_name} set a monster.", "set", request.player_id)
        elif action == "YGO_FLIP_SUMMON":
            card_obj = session.game.state.objects.get(request.card_id) if request.card_id else None
            card_name = card_obj.name if card_obj else "a monster"
            self.add_log(session, f"{player_name} Flip Summoned {card_name}!", "summon", request.player_id)
        elif action == "YGO_ACTIVATE":
            card_obj = session.game.state.objects.get(request.card_id) if request.card_id else None
            card_name = card_obj.name if card_obj else "a card"
            self.add_log(session, f"{player_name} activated {card_name}!", "activate", request.player_id)
        elif action == "YGO_SET_SPELL_TRAP":
            self.add_log(session, f"{player_name} set a card.", "set", request.player_id)
        elif action == "YGO_CHANGE_POSITION":
            card_obj = session.game.state.objects.get(request.card_id) if request.card_id else None
            card_name = card_obj.name if card_obj else "a monster"
            self.add_log(session, f"{player_name} changed {card_name}'s position.", "position", request.player_id)
        elif action == "YGO_SPECIAL_SUMMON":
            card_obj = session.game.state.objects.get(request.card_id) if request.card_id else None
            card_name = card_obj.name if card_obj else "a monster"
            self.add_log(session, f"{player_name} Special Summoned {card_name}!", "summon", request.player_id)
        elif action in ("YGO_DECLARE_ATTACK", "YGO_DIRECT_ATTACK"):
            attacker_id = request.source_id or request.card_id
            attacker_obj = session.game.state.objects.get(attacker_id) if attacker_id else None
            attacker_name = attacker_obj.name if attacker_obj else "a monster"
            if action == "YGO_DIRECT_ATTACK":
                self.add_log(session, f"{attacker_name} attacks directly!", "attack", request.player_id)
            else:
                target_id = request.targets[0][0] if request.targets and request.targets[0] else None
                target_obj = session.game.state.objects.get(target_id) if target_id else None
                target_name = target_obj.name if target_obj else "a monster"
                self.add_log(session, f"{attacker_name} attacks {target_name}!", "attack", request.player_id)

    def _validate_action(self, session: "GameSession", request: "PlayerActionRequest") -> Optional[str]:
        """Pre-validate a YGO action. Returns error string or None if valid."""
        turn_mgr = session.game.turn_manager
        if not hasattr(turn_mgr, "ygo_turn_state"):
            return None

        yts = turn_mgr.ygo_turn_state

        # Common card ownership/zone check for card-based actions
        if request.card_id and request.action_type not in ("YGO_END_TURN", "YGO_END_PHASE"):
            obj = session.game.state.objects.get(request.card_id)
            if not obj:
                return "Card not found."
            if request.action_type in ("YGO_NORMAL_SUMMON", "YGO_SET_MONSTER", "YGO_ACTIVATE", "YGO_SET_SPELL_TRAP"):
                if obj.zone != ZoneType.HAND or obj.controller != request.player_id:
                    return "That card is not in your hand."

        if request.action_type in ("YGO_NORMAL_SUMMON", "YGO_SET_MONSTER"):
            if yts.normal_summon_used:
                return "You already used your Normal Summon this turn."
            if request.card_id:
                obj = session.game.state.objects.get(request.card_id)
                if obj and obj.card_def:
                    level = getattr(obj.card_def, "level", 0) or 0
                    tributes_needed = 0
                    if level >= 5:
                        tributes_needed = 1
                    if level >= 7:
                        tributes_needed = 2
                    if tributes_needed > 0:
                        return (
                            f"Level {level} monsters require {tributes_needed} tribute(s). "
                            "Tribute Summon not yet supported in UI."
                        )
            slot = turn_mgr._find_empty_monster_slot(request.player_id)
            if slot is None:
                return "Monster Zone is full."

        elif request.action_type == "YGO_SET_SPELL_TRAP":
            slot = turn_mgr._find_empty_spell_trap_slot(request.player_id)
            if slot is None:
                return "Spell/Trap Zone is full."

        elif request.action_type == "YGO_FLIP_SUMMON":
            if request.card_id:
                obj = session.game.state.objects.get(request.card_id)
                if obj:
                    if getattr(obj.state, "ygo_position", None) != "face_down_def":
                        return "That monster is not face-down in Defense Position."
                    if getattr(obj.state, "turns_set", 0) < 1:
                        return "Cannot Flip Summon a monster the same turn it was Set."

        elif request.action_type == "YGO_CHANGE_POSITION":
            if request.card_id:
                obj = session.game.state.objects.get(request.card_id)
                if obj and yts.position_changes.get(request.card_id):
                    return "That monster already changed position this turn."

        elif request.action_type in ("YGO_DECLARE_ATTACK", "YGO_DIRECT_ATTACK"):
            attacker_id = request.source_id or request.card_id
            if attacker_id:
                obj = session.game.state.objects.get(attacker_id)
                if not obj:
                    return "Attacker not found."
                if obj.controller != request.player_id:
                    return "That monster is not yours."
                if obj.zone != ZoneType.MONSTER_ZONE:
                    return "That card is not on the field."
                if getattr(obj.state, "ygo_position", None) != "face_up_atk":
                    return "Only face-up ATK position monsters can attack."
                if yts.attacks_declared.get(attacker_id, 0) >= 1:
                    return "That monster already attacked this turn."

        return None

    def add_log(
        self,
        session: "GameSession",
        text: str,
        event_type: str,
        player: Optional[str] = None,
    ) -> None:
        """Add an entry to the Yu-Gi-Oh! game log."""
        turn = session.game.turn_manager.turn_number if hasattr(session.game.turn_manager, "turn_number") else 0
        session._game_log.append(
            GameLogEntry(
                turn=turn,
                text=text,
                event_type=event_type,
                player=player,
                timestamp=time.time(),
            )
        )

    # --- Serialization ----------------------------------------------------

    def serialize_card(
        self,
        session: "GameSession",
        obj: Any,
        reveal: bool = True,
        **kwargs: Any,
    ) -> "CardData":
        """Serialize a Yu-Gi-Oh! game object to CardData with YGO-specific fields."""
        card_data = session._serialize_card(obj)

        # Face-down cards: hide info from opponent
        is_face_down = getattr(obj.state, "face_down", False)
        if is_face_down and not reveal:
            card_data.name = "Set Card"
            card_data.text = ""
            card_data.face_down = True
            card_data.ygo_position = getattr(obj.state, "ygo_position", None)
            return card_data

        card_def = obj.card_def
        if card_def:
            card_data.level = getattr(card_def, "level", None)
            card_data.rank = getattr(card_def, "rank", None)
            card_data.link_rating = getattr(card_def, "link_rating", None)
            card_data.atk = getattr(card_def, "atk", None)
            card_data.def_val = getattr(card_def, "def_val", None)
            card_data.attribute = getattr(card_def, "attribute", None)
            card_data.ygo_monster_type = getattr(card_def, "ygo_monster_type", None)
            card_data.ygo_spell_type = getattr(card_def, "ygo_spell_type", None)
            card_data.ygo_trap_type = getattr(card_def, "ygo_trap_type", None)
            card_data.is_tuner = getattr(card_def, "is_tuner", False)
            card_data.image_url = getattr(card_def, "image_url", None)

        # Runtime state
        card_data.face_down = is_face_down
        card_data.ygo_position = getattr(obj.state, "ygo_position", None)
        overlay_units = getattr(obj.state, "overlay_units", None)
        if overlay_units:
            card_data.overlay_units = len(overlay_units)

        return card_data
