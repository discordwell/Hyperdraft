"""Turn driver for the SCP Containment TCG."""

from __future__ import annotations

from typing import Optional

from .turn import TurnManager, Phase, Step
from .types import Event, EventType, GameState
from . import scp


class SCPTurnManager(TurnManager):
    """Compact turn loop: briefing, paperwork, assignments, breach audit."""

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

        scp.ensure_scp_state(self.state, active)
        scp.reset_staff(getattr(self.state, "_game", None), active) if getattr(self.state, "_game", None) else None
        start = Event(type=EventType.TURN_START, payload={"player": active, "turn_number": self.turn_state.turn_number})
        if self.pipeline:
            self.pipeline.emit(start)
        events.append(start)

        game = getattr(self.state, "_game", None)
        if game:
            scp.reset_assignment_slots(self.state, active)
            events.extend(scp.process_paperwork(game, active))
            # MNR: Cognitive Hazard fires at the start of the affected
            # player's turn — opposing anomalies project discard pressure
            # onto the active player unless they have a Mnestic personnel.
            events.extend(scp.apply_cognitive_hazard_start(game, active))

        self.turn_state.step = Step.DRAW
        draw = Event(type=EventType.DRAW, payload={"player": active, "count": 1})
        if self.pipeline:
            self.pipeline.emit(draw)
        events.append(draw)

        self.turn_state.phase = Phase.PRECOMBAT_MAIN
        self.turn_state.step = Step.MAIN
        phase_start = Event(type=EventType.PHASE_START, payload={"phase": "scp_assignment", "player": active})
        if self.pipeline:
            self.pipeline.emit(phase_start)
        events.append(phase_start)

        if self._is_ai_player(active) and self.scp_ai_handler:
            ai_events = await self.scp_ai_handler.take_turn(active, self.state, game)
            events.extend(ai_events or [])
        elif self.human_action_handler:
            events.extend(await self._run_human_turn(active))

        if game:
            events.extend(scp.breach_tick(game, active))
            # MNR: end-of-turn antimeme decay. Anomalies controlled by
            # ``active`` advance their forget counters when no Mnestic
            # personnel is covering them — and forget out of history at
            # threshold. Runs AFTER breach_tick so the breach numbers are
            # the snapshot players see, then the antimeme audit happens.
            events.extend(scp.tick_antimeme_counters(game, active))

        end = Event(type=EventType.TURN_END, payload={"player": active, "turn_number": self.turn_state.turn_number})
        if self.pipeline:
            self.pipeline.emit(end)
        events.append(end)

        self.state.priority_player = None
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
            ok, _message, action_events = await self.execute_action(player_id, action)
            if ok:
                events.extend(action_events)
            if game.is_game_over():
                break
        return events

    async def execute_action(self, player_id: str, action: dict) -> tuple[bool, str, list[Event]]:
        game = getattr(self.state, "_game", None)
        if not game:
            return False, "Game not attached", []
        action_type = action.get("action_type")
        if action_type == "SCP_OPEN_DOSSIER":
            return scp.open_dossier(
                game,
                player_id,
                action.get("card_id"),
                fast_track=bool(action.get("fast_track")),
                sealed=bool(action.get("sealed")),
            )
        if action_type == "SCP_REVEAL_DOSSIER":
            return scp.reveal_dossier(game, player_id, action.get("object_id"))
        if action_type == "SCP_RESEARCH":
            return scp.run_test(game, player_id, action.get("anomaly_id"), action.get("staff_ids") or [])
        if action_type == "SCP_CONTAIN":
            return scp.contain_anomaly(game, player_id, action.get("anomaly_id"), action.get("staff_ids") or [])
        if action_type == "SCP_SUPPRESS":
            return scp.suppress_anomaly(game, player_id, action.get("anomaly_id"), action.get("staff_ids") or [])
        if action_type == "SCP_SPEND_ETHICS":
            return scp.spend_ethics(
                game,
                player_id,
                int(action.get("amount", 0) or 0),
                mode=action.get("mode") or "",
            )
        if action_type == "SCP_SHIFT_MOOD":
            return scp.shift_mood(game, player_id, action.get("anomaly_id"), action.get("mood") or "")
        if action_type == "SCP_CROSS_CONTAIN":
            return scp.cross_contain(game, player_id, action.get("contained_id"), action.get("active_id"))
        if action_type == "SCP_MEMORY_HOLE":
            return scp.memory_hole(game, player_id, action.get("object_id"))
        if action_type == "SCP_APPLY_PROTOCOL":
            return scp.apply_protocol(game, player_id, action.get("anomaly_id"), action.get("protocol") or "")
        if action_type == "SCP_RESOLVE_INCIDENT":
            return scp.resolve_incident(game, player_id, int(action.get("index", 0) or 0))
        return False, "Unknown SCP action", []
