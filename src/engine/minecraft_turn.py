"""
Minecraft TCG turn manager.

The alpha turn is intentionally direct: start/readiness, draw, main actions,
optional combat actions, end. There is no MTG priority loop.
"""

from __future__ import annotations

from typing import Optional

from .turn import TurnManager, Phase, Step
from .types import Event, EventType, GameState
from . import minecraft as mc


class MinecraftTurnManager(TurnManager):
    def __init__(self, state: GameState):
        super().__init__(state)
        self.ai_players: set[str] = set()
        self.minecraft_ai_handler = None
        self.human_action_handler = None

    def set_ai_handler(self, handler) -> None:
        self.minecraft_ai_handler = handler

    def set_ai_player(self, player_id: str) -> None:
        self.ai_players.add(player_id)

    def _is_ai_player(self, player_id: Optional[str]) -> bool:
        return bool(player_id and player_id in self.ai_players)

    async def run_turn(self, player_id: str = None) -> list[Event]:
        events: list[Event] = []

        if player_id:
            self.turn_state.active_player_id = player_id
            if player_id in self.turn_order:
                self.current_player_index = self.turn_order.index(player_id)
        else:
            self.turn_state.active_player_id = self.turn_order[self.current_player_index]

        active = self.turn_state.active_player_id
        self.state.active_player = active
        self.state.priority_player = active
        self.turn_state.turn_number += 1
        self.state.turn_number = self.turn_state.turn_number
        self.turn_state.phase = Phase.BEGINNING
        self.turn_state.step = Step.UNTAP

        mc.reset_for_turn(self.state, active)
        game = getattr(self.state, "_game", None)
        if game:
            events.extend(mc.apply_start_turn_bonuses(game, active))
        flip_event = mc.maybe_flip_day_night(self.state, active)
        if flip_event and self.pipeline:
            self.pipeline.emit(flip_event)
            events.append(flip_event)

        turn_start = Event(type=EventType.TURN_START, payload={"player": active, "turn_number": self.turn_state.turn_number})
        if self.pipeline:
            self.pipeline.emit(turn_start)
        events.append(turn_start)

        self.turn_state.step = Step.DRAW
        draw = Event(type=EventType.DRAW, payload={"player": active, "count": 1})
        if self.pipeline:
            self.pipeline.emit(draw)
        events.append(draw)

        self.turn_state.phase = Phase.PRECOMBAT_MAIN
        self.turn_state.step = Step.MAIN
        phase_start = Event(type=EventType.PHASE_START, payload={"phase": "minecraft_main", "player": active})
        if self.pipeline:
            self.pipeline.emit(phase_start)
        events.append(phase_start)

        if self._is_ai_player(active) and self.minecraft_ai_handler:
            ai_events = await self.minecraft_ai_handler.take_turn(active, self.state, game)
            events.extend(ai_events or [])
            events.extend(await self._run_pending_block_prompt())
        elif self.human_action_handler:
            events.extend(await self._run_human_turn(active))

        end = Event(type=EventType.PHASE_END, payload={"phase": "minecraft_main", "player": active})
        if self.pipeline:
            self.pipeline.emit(end)
        events.append(end)

        turn_end = Event(type=EventType.TURN_END, payload={"player": active, "turn_number": self.turn_state.turn_number})
        if self.pipeline:
            self.pipeline.emit(turn_end)
        events.append(turn_end)

        self.state.priority_player = None
        self.current_player_index = (self.current_player_index + 1) % len(self.turn_order)
        return events

    async def _run_human_turn(self, player_id: str) -> list[Event]:
        events: list[Event] = []
        game = getattr(self.state, "_game", None)
        if not game:
            return events

        for _ in range(200):
            if game.is_game_over():
                break
            action = await self.human_action_handler(player_id, self.state)
            if not action:
                break
            if action.get("action_type") == "MC_END_TURN":
                marker = Event(type=EventType.MC_END_TURN, payload={"player": player_id})
                if self.pipeline:
                    self.pipeline.emit(marker)
                events.append(marker)
                break
            ok, _message, action_events = await self.execute_action(player_id, action)
            if ok:
                events.extend(action_events)
            game.check_state_based_actions()
            events.extend(mc.handle_avatar_deaths(game))
            events.extend(await self._run_pending_block_prompt())
            if game.is_game_over():
                break
        return events

    async def _run_pending_block_prompt(self) -> list[Event]:
        events: list[Event] = []
        combat = self.state.minecraft_combat or {}
        if combat.get("phase") != "declare_blockers":
            return events
        defender_id = combat.get("defending_player")
        game = getattr(self.state, "_game", None)
        if not defender_id or not game:
            return events

        if not self._is_ai_player(defender_id) and self.human_action_handler:
            action = await self.human_action_handler(defender_id, self.state)
            if action and action.get("action_type") == "MC_DECLARE_BLOCKERS":
                ok, _message, action_events = await self.execute_action(defender_id, action)
                if ok:
                    events.extend(action_events)
            else:
                ok, _message, action_events = mc.declare_blockers(game, defender_id, [])
                if ok:
                    events.extend(action_events)
        elif self._is_ai_player(defender_id):
            block_map = mc.auto_blockers(self.state, defender_id, combat.get("attackers") or [])
            ok, _message, action_events = mc.resolve_combat(
                game,
                combat.get("attacking_player"),
                defender_id,
                combat.get("attackers") or [],
                block_map,
            )
            if ok:
                events.extend(action_events)
        return events

    async def execute_action(self, player_id: str, action: dict) -> tuple[bool, str, list[Event]]:
        game = getattr(self.state, "_game", None)
        if not game:
            return False, "Game not attached", []
        action_type = action.get("action_type")
        if action_type == "MC_PLAY_CARD":
            return mc.play_card(
                game,
                player_id,
                action.get("card_id"),
                cell=action.get("cell"),
                target_id=action.get("target_id"),
                target_column=action.get("target_column"),
            )
        if action_type == "MC_ASSIGN_WORKER":
            return mc.mine_biome(
                game,
                player_id,
                int(action.get("biome_index", 0) or 0),
                actor_id=action.get("worker_id") or action.get("source_id"),
            )
        if action_type == "MC_AVATAR_ACTION":
            kind = action.get("kind") or "mine"
            if kind == "mine":
                return mc.mine_biome(game, player_id, int(action.get("biome_index", 0) or 0), avatar=True)
            if kind == "explore":
                return mc.explore_biome(game, player_id, int(action.get("biome_index", 0) or 0))
            if kind == "attack":
                return mc.avatar_attack(
                    game, player_id,
                    target_id=action.get("target_id"),
                    target_column=action.get("target_column"),
                )
            return False, "Unknown avatar action", []
        if action_type == "MC_EXPLORE_BIOME":
            return mc.explore_biome(game, player_id, int(action.get("biome_index", 0) or 0))
        if action_type == "MC_DECLARE_ATTACKERS":
            return mc.declare_attackers(game, player_id, action.get("attackers") or [])
        if action_type == "MC_DECLARE_BLOCKERS":
            return mc.declare_blockers(game, player_id, action.get("blockers") or [])
        return False, "Unknown Minecraft action", []
