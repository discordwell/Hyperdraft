"""
Server-side Pokemon mode adapter.

Encapsulates the Pokemon game loop, human-action handling, action dispatch,
action logging, and Pokemon-specific card serialization.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, Optional

from src.server.models import GameLogEntry

from .base import ModeAdapter

if TYPE_CHECKING:
    from src.server.session import GameSession
    from src.server.models import CardData, PlayerActionRequest


class PokemonModeAdapter(ModeAdapter):
    """Pokemon adapter."""

    async def setup_game(self, session: "GameSession") -> None:
        from src.ai.pokemon_adapter import PokemonAIAdapter

        if session.ai_profiles_by_player:
            first_profile = next(iter(session.ai_profiles_by_player.values()))
            difficulty = first_profile.get("difficulty", session.ai_difficulty or "medium")
        else:
            difficulty = session.ai_difficulty or "medium"
        if hasattr(difficulty, "value"):
            difficulty = difficulty.value
        difficulty = str(difficulty).strip().lower()

        ai_adapter = PokemonAIAdapter(difficulty=difficulty)
        session.game.turn_manager.set_ai_handler(ai_adapter)

        # Wire human action handler for Pokemon mode with human players
        if session.human_players:
            session.game.turn_manager.human_action_handler = (
                lambda pid, gs: self.get_human_action(session, pid, gs)
            )

        # Setup game (shuffle, draw 7, mulligans, prizes, coin flip)
        await session.game.turn_manager.setup_game()

    async def run_game_loop(self, session: "GameSession") -> None:
        """
        Pokemon game loop.

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
        Callback for PokemonTurnManager.human_action_handler.

        Blocks (via asyncio.Future) until the client submits a Pokemon action.
        """
        # Log turn start when human is prompted for action
        turn = session.game.turn_manager.turn_number if hasattr(session.game.turn_manager, "turn_number") else 0
        player_name = session.player_names.get(player_id, "Player")
        # Only log if this is a new turn (avoid double-logging)
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
            return {"action_type": "PKM_END_TURN"}

    async def handle_action(
        self,
        session: "GameSession",
        request: "PlayerActionRequest",
    ) -> tuple[bool, str]:
        """Handle a Pokemon-specific player action."""
        active_player = session.game.get_active_player()
        if request.player_id != active_player:
            return False, "Not your turn"

        target_id = request.targets[0][0] if request.targets and request.targets[0] else None

        # Build Pokemon action dict matching pokemon_turn.py expectations
        action_dict: dict = {"action_type": request.action_type}

        if request.action_type == "PKM_PLAY_CARD":
            card_id = request.card_id
            if not card_id:
                return False, "PKM_PLAY_CARD requires card_id"

            card_obj = session.game.state.objects.get(card_id)
            if not card_obj:
                return False, "Card not found"

            from src.engine.types import CardType

            types = card_obj.characteristics.types
            if CardType.POKEMON in types:
                stage = card_obj.card_def.evolution_stage if card_obj.card_def else "Basic"
                if stage == "Basic":
                    action_dict = {"action_type": "PKM_PLAY_BASIC", "card_id": card_id}
                else:
                    action_dict = {"action_type": "PKM_EVOLVE", "card_id": card_id, "target_id": target_id}
            elif CardType.ITEM in types:
                action_dict = {"action_type": "PKM_PLAY_ITEM", "card_id": card_id}
            elif CardType.SUPPORTER in types:
                action_dict = {"action_type": "PKM_PLAY_SUPPORTER", "card_id": card_id}
            elif CardType.STADIUM in types:
                action_dict = {"action_type": "PKM_PLAY_STADIUM", "card_id": card_id}
            elif CardType.ENERGY in types:
                action_dict = {"action_type": "PKM_ATTACH_ENERGY", "energy_id": card_id, "target_id": target_id}
            else:
                return False, "Unknown card type for PKM_PLAY_CARD"

        elif request.action_type == "PKM_ATTACH_ENERGY":
            action_dict = {
                "action_type": "PKM_ATTACH_ENERGY",
                "energy_id": request.card_id,
                "target_id": target_id,
            }

        elif request.action_type == "PKM_ATTACK":
            attack_index = int(target_id) if target_id else 0
            action_dict = {
                "action_type": "PKM_ATTACK",
                "attack_index": attack_index,
            }

        elif request.action_type == "PKM_RETREAT":
            action_dict = {
                "action_type": "PKM_RETREAT",
                "bench_pokemon_id": target_id,
            }

        elif request.action_type == "PKM_EVOLVE":
            action_dict = {
                "action_type": "PKM_EVOLVE",
                "card_id": request.card_id,
                "target_id": request.source_id or target_id,
            }

        elif request.action_type == "PKM_USE_ABILITY":
            action_dict = {
                "action_type": "PKM_USE_ABILITY",
                "pokemon_id": request.source_id,
            }

        elif request.action_type == "PKM_END_TURN":
            action_dict = {"action_type": "PKM_END_TURN"}

        # Log the action for the game log
        self.log_action(session, request, action_dict)

        # Resolve the pending future
        if (
            session._pending_action_future
            and not session._pending_action_future.done()
            and session._pending_player_id == request.player_id
        ):

            is_end_turn = request.action_type == "PKM_END_TURN"
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

            # Check for KOs after attack resolves
            if request.action_type == "PKM_ATTACK":
                self._check_and_log_kos(session)

            await asyncio.sleep(0.05)
            return True, "Action accepted"

        return False, "No pending action expected"

    # --- Logging helpers --------------------------------------------------

    def log_action(
        self,
        session: "GameSession",
        request: "PlayerActionRequest",
        action_dict: dict,
    ) -> None:
        """Generate a log entry for a Pokemon action."""
        player_name = session.player_names.get(request.player_id, "Player")
        action = request.action_type

        if action == "PKM_END_TURN":
            self.add_log(session, f"{player_name} ended their turn.", "turn_end", request.player_id)
        elif action == "PKM_ATTACK":
            attack_idx = action_dict.get("attack_index", 0)
            active_key = f"active_spot_{request.player_id}"
            active_zone = session.game.state.zones.get(active_key)
            atk_name = "?"
            atk_dmg = ""
            if active_zone and active_zone.objects:
                active_obj = session.game.state.objects.get(active_zone.objects[0])
                if active_obj and active_obj.card_def:
                    attacks = getattr(active_obj.card_def, "attacks", []) or []
                    if attack_idx < len(attacks):
                        atk_name = attacks[attack_idx].get("name", "?")
                        dmg = attacks[attack_idx].get("damage", 0)
                        if dmg:
                            atk_dmg = f" for {dmg}"
                    pokemon_name = active_obj.name
                    self.add_log(
                        session,
                        f"{pokemon_name} attacked with {atk_name}{atk_dmg}!",
                        "attack",
                        request.player_id,
                    )
                    return
            self.add_log(session, f"{player_name} attacked with {atk_name}!", "attack", request.player_id)
        elif action == "PKM_PLAY_CARD":
            card_obj = session.game.state.objects.get(request.card_id or "")
            card_name = card_obj.name if card_obj else "?"
            sub = action_dict.get("action_type", "")
            if sub == "PKM_PLAY_BASIC":
                self.add_log(session, f"{player_name} played {card_name} to bench.", "play_basic", request.player_id)
            elif sub in ("PKM_PLAY_ITEM", "PKM_PLAY_SUPPORTER", "PKM_PLAY_STADIUM"):
                self.add_log(session, f"{player_name} played {card_name}.", "trainer", request.player_id)
            elif sub == "PKM_EVOLVE":
                self.add_log(session, f"{player_name} evolved into {card_name}.", "evolution", request.player_id)
            elif sub == "PKM_ATTACH_ENERGY":
                self.add_log(session, f"{player_name} attached {card_name}.", "energy", request.player_id)
            else:
                self.add_log(session, f"{player_name} played {card_name}.", "play", request.player_id)
        elif action == "PKM_ATTACH_ENERGY":
            card_obj = session.game.state.objects.get(request.card_id or "")
            target_id = request.targets[0][0] if request.targets and request.targets[0] else None
            target_obj = session.game.state.objects.get(target_id or "") if target_id else None
            card_name = card_obj.name if card_obj else "Energy"
            target_name = target_obj.name if target_obj else "?"
            self.add_log(session, f"{player_name} attached {card_name} to {target_name}.", "energy", request.player_id)
        elif action == "PKM_RETREAT":
            target_id = request.targets[0][0] if request.targets and request.targets[0] else None
            target_obj = session.game.state.objects.get(target_id or "") if target_id else None
            target_name = target_obj.name if target_obj else "?"
            self.add_log(session, f"{player_name} retreated, promoting {target_name}.", "retreat", request.player_id)
        elif action == "PKM_EVOLVE":
            card_obj = session.game.state.objects.get(request.card_id or "")
            card_name = card_obj.name if card_obj else "?"
            self.add_log(session, f"{player_name} evolved into {card_name}!", "evolution", request.player_id)
        elif action == "PKM_USE_ABILITY":
            source_obj = session.game.state.objects.get(request.source_id or "")
            ability_name = "?"
            if source_obj and source_obj.card_def:
                ability = getattr(source_obj.card_def, "ability", None)
                if ability:
                    ability_name = ability.get("name", "?")
            self.add_log(session, f"{player_name} used {ability_name}.", "ability", request.player_id)

    def _check_and_log_kos(self, session: "GameSession") -> None:
        """Check for Pokemon with lethal damage and log KO entries."""
        for pid in session.game.state.players:
            active_zone = session.game.state.zones.get(f"active_spot_{pid}")
            if active_zone:
                for obj_id in active_zone.objects:
                    obj = session.game.state.objects.get(obj_id)
                    if obj and obj.state:
                        hp = getattr(obj.card_def, "hp", 0) if obj.card_def else 0
                        dmg = getattr(obj.state, "damage_counters", 0) * 10
                        if hp > 0 and dmg >= hp:
                            self.add_log(session, f"{obj.name} was knocked out!", "ko", pid)

    def add_log(
        self,
        session: "GameSession",
        text: str,
        event_type: str,
        player: Optional[str] = None,
    ) -> None:
        """Add an entry to the Pokemon game log."""
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

    def serialize_card(self, session: "GameSession", obj: Any, **kwargs: Any) -> "CardData":
        """Serialize a Pokemon game object to CardData with Pokemon-specific fields."""
        card_data = session._serialize_card(obj)

        # Add Pokemon-specific fields from card definition
        card_def = obj.card_def
        if card_def:
            card_data.hp = getattr(card_def, "hp", None)
            card_data.pokemon_type = getattr(card_def, "pokemon_type", None)
            card_data.evolution_stage = getattr(card_def, "evolution_stage", None)
            card_data.weakness_type = getattr(card_def, "weakness_type", None)
            card_data.resistance_type = getattr(card_def, "resistance_type", None)
            card_data.retreat_cost = getattr(card_def, "retreat_cost", 0)
            card_data.is_ex = getattr(card_def, "is_ex", False)
            card_data.prize_count = getattr(card_def, "prize_count", 1)
            card_data.image_url = getattr(card_def, "image_url", None)

            # Serialize attacks
            raw_attacks = getattr(card_def, "attacks", []) or []
            card_data.attacks = []
            for atk in raw_attacks:
                attack_data = {
                    "name": atk.get("name", "?"),
                    "damage": atk.get("damage", 0),
                    "text": atk.get("text", ""),
                    "cost": atk.get("cost", []),
                }
                card_data.attacks.append(attack_data)

            # Serialize ability
            ability = getattr(card_def, "ability", None)
            if ability:
                card_data.ability_name = ability.get("name")
                card_data.ability_text = ability.get("text")

        # Add runtime state from ObjectState
        state = obj.state if obj.state else None
        if state:
            card_data.damage_counters = getattr(state, "damage_counters", 0)
            card_data.status_conditions = list(getattr(state, "status_conditions", set()))

            # Attached energy: resolve energy type codes
            attached_ids = getattr(state, "attached_energy", []) or []
            energy_types = []
            for eid in attached_ids:
                energy_obj = session.game.state.objects.get(eid)
                if energy_obj and energy_obj.card_def:
                    energy_types.append(getattr(energy_obj.card_def, "pokemon_type", "C") or "C")
                else:
                    energy_types.append("C")
            card_data.attached_energy = energy_types

            # Attached tool
            tool_id = getattr(state, "attached_tool", None)
            if tool_id:
                tool_obj = session.game.state.objects.get(tool_id)
                if tool_obj:
                    card_data.attached_tool_name = tool_obj.name

        return card_data
