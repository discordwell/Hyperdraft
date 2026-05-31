"""Turn driver for SCP: SECURE / CONTAIN / SUBVERT (asymmetric Foundation vs Insurgency).

Strict alternation, both draw 1 (spec §2/§11). The asymmetry lives in the cards and verbs,
not the turn shape. Notably there is NO end-of-turn breach tick — breach is not
self-inflicted in scp (unlike the original SCP engine); the only arbiter is check_scp_win.
"""

from __future__ import annotations

from typing import Optional

from .turn import TurnManager, Phase, Step
from .types import Event, EventType, GameState
from . import scp


class SCPTurnManager(TurnManager):
    def __init__(self, state: GameState):
        super().__init__(state)
        self.ai_players: set[str] = set()
        self.scp_ai_handler = None
        self.human_action_handler = None

    def set_ai_handler(self, handler) -> None:
        self.scp_ai_handler = handler

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

        game = getattr(self.state, "_game", None)
        scp.ensure_scp_state(self.state, active)
        scp.reset_turn_resources(self.state, active)
        if game:
            events.extend(scp.fire_turn_start_assets(game, active))

        start = Event(type=EventType.TURN_START,
                      payload={"player": active, "turn_number": self.turn_state.turn_number})
        if self.pipeline:
            self.pipeline.emit(start)
        events.append(start)

        # Draw step
        self.turn_state.step = Step.DRAW
        if game:
            events.extend(scp.draw_cards(game, active, scp.DRAW_PER_TURN))

        # Action phase
        self.turn_state.phase = Phase.PRECOMBAT_MAIN
        self.turn_state.step = Step.MAIN
        phase_start = Event(type=EventType.PHASE_START,
                            payload={"phase": "scp_actions", "player": active})
        if self.pipeline:
            self.pipeline.emit(phase_start)
        events.append(phase_start)

        if self._is_ai_player(active) and self.scp_ai_handler:
            ai_events = await self.scp_ai_handler.take_turn(active, self.state, game)
            events.extend(ai_events or [])
        elif self.human_action_handler:
            events.extend(await self._run_human_turn(active))

        # End of turn: enforce max hand, then the single win arbiter.
        if game:
            events.extend(scp.discard_to_max(game, active))
            events.extend(scp.check_scp_win(game))

        end = Event(type=EventType.TURN_END,
                    payload={"player": active, "turn_number": self.turn_state.turn_number})
        if self.pipeline:
            self.pipeline.emit(end)
        events.append(end)

        self.state.priority_player = None
        if self.turn_order:
            self.current_player_index = (self.current_player_index + 1) % len(self.turn_order)
        return events

    async def _run_human_turn(self, player_id: str) -> list[Event]:
        events: list[Event] = []
        game = getattr(self.state, "_game", None)
        if not game:
            return events
        for _ in range(100):
            action = await self.human_action_handler(player_id, self.state)
            if not action:
                break
            if action.get("action_type") == "SCP_END_TURN":
                break
            ok, _message, action_events = self.execute_action(player_id, action)
            if ok:
                events.extend(action_events)
            if game.is_game_over():
                break
        return events

    def execute_action(self, player_id: str, action: dict) -> tuple[bool, str, list[Event]]:
        game = getattr(self.state, "_game", None)
        if not game:
            return False, "Game not attached", []
        at = action.get("action_type")
        if at == "SCP_NOOP":
            return True, "", []
        if at == "SCP_GAIN":
            return scp.gain_credits(game, player_id)
        if at == "SCP_DRAW":
            return scp.draw_action(game, player_id)
        if at == "SCP_PLAY":
            return scp.play_card(game, player_id, action.get("card_id"),
                                  cell_id=action.get("cell_id"), target=action.get("target"))
        if at == "SCP_ADVANCE":
            return scp.advance(game, player_id, action.get("anomaly_id"))
        if at == "SCP_CONTAIN":
            return scp.contain(game, player_id, action.get("anomaly_id"))
        if at == "SCP_INFILTRATE":
            tgt = action.get("target")
            return scp.infiltrate(game, player_id, tuple(tgt) if tgt else ("central", "hq"))
        if at == "SCP_ACTIVATE":
            tgt = action.get("target")
            return scp.activate_ability(game, player_id, action.get("card_id"),
                                         target=tuple(tgt) if tgt else None)
        return False, "Unknown scp action", []
