"""Server-side SCP mode adapter (asymmetric Foundation vs Chaos Insurgency).

scp is a strict-alternation two-player game: each seat gets AP per turn and spends it on
verbs (gain / draw / play / advance / contain / infiltrate / activate). Like cats and
clankers, the human seat is driven *transactionally* — each ``SCP_*`` action mutates state
via the turn manager's ``execute_action`` — while the bot seat's full turn is driven by
``turn_manager.run_turn`` when the human ends their turn.

Faction by seat: ``player_ids[0]`` is the Foundation (goes first), ``player_ids[1]`` the
Insurgency. Decks/identities are resolved from the scp deck registry (deterministic
fallback). Fog of war is enforced by the per-viewer serializer (``_serialize_scp_state``).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Optional

from src.server.models import GameLogEntry

from .base import ModeAdapter

if TYPE_CHECKING:
    from src.server.session import GameSession
    from src.server.models import PlayerActionRequest


def _coerce_target(t) -> Optional[tuple]:
    """['cell','3'] -> ('cell', 3); ['central','research'] -> ('central','research')."""
    if not t:
        return None
    parts = list(t)
    if len(parts) >= 2 and parts[0] == "cell":
        try:
            return ("cell", int(parts[1]))
        except (TypeError, ValueError):
            return tuple(parts)
    return tuple(parts)


class SCPModeAdapter(ModeAdapter):
    """SCP server adapter — per-action transactional, strict alternation, AI opponent."""

    # ─── Setup ──────────────────────────────────────────────────────────
    async def setup_game(self, session: "GameSession") -> None:
        from src.engine import scp
        from src.ai.scp_adapter import SCPAIAdapter
        from src.cards.scp.decks import SCP_FOUNDATION_DECKS, SCP_INSURGENCY_DECKS

        game = session.game
        pids = list(session.player_ids)
        if len(pids) < 2:
            return
        foundation_seat, insurgency_seat = pids[0], pids[1]

        fkeys, ikeys = list(SCP_FOUNDATION_DECKS), list(SCP_INSURGENCY_DECKS)
        fkey = session.deck_id_by_player.get(foundation_seat)
        fkey = fkey if fkey in SCP_FOUNDATION_DECKS else fkeys[0]
        ikey = session.deck_id_by_player.get(insurgency_seat)
        ikey = ikey if ikey in SCP_INSURGENCY_DECKS else ikeys[0]
        session.deck_id_by_player[foundation_seat] = fkey
        session.deck_id_by_player[insurgency_seat] = ikey
        fident, fbuild = SCP_FOUNDATION_DECKS[fkey]
        iident, ibuild = SCP_INSURGENCY_DECKS[ikey]

        scp.setup_scp_game(
            game, game.state.players[foundation_seat], game.state.players[insurgency_seat],
            foundation_deck=fbuild(), insurgency_deck=ibuild(),
            foundation_identity=fident, insurgency_identity=iident,
        )
        game.state.game_mode = "scp"

        # Resolve difficulty (ultra → hard for the in-process heuristic).
        difficulty = session.ai_difficulty or "medium"
        if hasattr(difficulty, "value"):
            difficulty = difficulty.value
        difficulty = str(difficulty).strip().lower()
        if difficulty not in ("easy", "medium", "hard"):
            difficulty = "hard" if difficulty == "ultra" else "medium"

        tm = game.turn_manager
        if hasattr(tm, "set_ai_handler"):
            tm.set_ai_handler(SCPAIAdapter(difficulty))
        for pid in pids:
            if pid not in session.human_players and hasattr(tm, "set_ai_player"):
                tm.set_ai_player(pid)

        # Open the opening turn for human_vs_bot so the human sees a ready board.
        if session.mode == "human_vs_bot" and session.human_players:
            if foundation_seat in session.human_players:
                self._open_turn(session, foundation_seat)
            else:
                # Human is the Insurgency (seat 1): let the Foundation bot take turn 1 first.
                await self._run_ai_turn(session, foundation_seat)
                if not self._finish_if_over(session):
                    self._open_turn(session, insurgency_seat)

    # ─── Game loop ──────────────────────────────────────────────────────
    async def run_game_loop(self, session: "GameSession") -> None:
        tm = session.game.turn_manager
        if session.mode == "bot_vs_bot":
            cap = 200
            turns = 0
            while not session.is_finished and turns < cap:
                try:
                    await tm.run_turn()
                except Exception as e:  # noqa: BLE001
                    print(f"[scp] run_turn failed: {e}")
                    break
                turns += 1
                if self._finish_if_over(session):
                    await self._broadcast(session)
                    break
                await self._broadcast(session)
            return
        # human_vs_bot / human_vs_human: broadcast the opening board and wait for actions.
        await self._broadcast(session)

    async def get_human_action(self, session: "GameSession", player_id, game_state) -> dict:
        """Unused — scp uses the transactional per-action path."""
        return {"action_type": "SCP_END_TURN"}

    # ─── Action dispatch ────────────────────────────────────────────────
    async def handle_action(
        self, session: "GameSession", request: "PlayerActionRequest",
    ) -> tuple[bool, str]:
        from src.engine import scp

        game = session.game
        tm = game.turn_manager
        state = game.state
        atype = request.action_type
        pid = request.player_id
        active = getattr(state, "active_player", None)

        if pid != active:
            return False, "Not your turn to act"
        if game.is_game_over():
            return False, "Game is over"

        if atype == "SCP_END_TURN":
            scp.discard_to_max(game, pid)
            scp.check_scp_win(game)
            if self._finish_if_over(session):
                self._log(session, pid, "ended turn")
                await self._broadcast(session)
                return True, "Game over"
            opp = self._other_player(session, pid)
            if opp is None:
                await self._broadcast(session)
                return True, "Turn ended"
            if opp in session.human_players:
                self._open_turn(session, opp)
            else:
                await self._run_ai_turn(session, opp)
                if self._finish_if_over(session):
                    await self._broadcast(session)
                    return True, "Game over"
                self._open_turn(session, pid)
            self._log(session, pid, "ended turn")
            session._record_frame(action=request.model_dump())
            await self._broadcast(session)
            return True, "Turn ended"

        # State-mutating verbs → turn manager's execute_action.
        action: dict[str, Any] = {"action_type": atype}
        if atype == "SCP_PLAY":
            if not request.card_id:
                return False, "SCP_PLAY requires card_id"
            action["card_id"] = request.card_id
            action["cell_id"] = request.cell_id
            tgt = _coerce_target(request.scp_target)
            if tgt:
                action["target"] = tgt
        elif atype in ("SCP_ADVANCE", "SCP_CONTAIN"):
            action["anomaly_id"] = request.anomaly_id or request.card_id
        elif atype == "SCP_INFILTRATE":
            tgt = _coerce_target(request.scp_target)
            if tgt:
                action["target"] = tgt
        elif atype == "SCP_ACTIVATE":
            if not request.card_id:
                return False, "SCP_ACTIVATE requires card_id"
            action["card_id"] = request.card_id
            tgt = _coerce_target(request.scp_target)
            if tgt:
                action["target"] = tgt

        try:
            ok, msg, _events = tm.execute_action(pid, action)
        except Exception as e:  # noqa: BLE001
            return False, f"scp action failed: {e}"
        if ok:
            self._log(session, pid, self._describe(state, atype, request))
            if self._finish_if_over(session):
                await self._broadcast(session)
                return True, "Game over"
            session._record_frame(action=request.model_dump())
            await self._broadcast(session)
        return ok, msg or ("Action accepted" if ok else "Rejected")

    # ─── Turn helpers ───────────────────────────────────────────────────
    def _open_turn(self, session: "GameSession", pid: str) -> None:
        """Start ``pid``'s turn: refresh AP, fire start-of-turn assets, draw 1. Mirrors the
        opening of SCPTurnManager.run_turn without the AI/human dispatch + end-of-turn."""
        from src.engine import scp

        game = session.game
        tm = game.turn_manager
        state = game.state
        state.active_player = pid
        if getattr(tm, "turn_state", None) is not None:
            tm.turn_state.active_player_id = pid
            tm.turn_state.turn_number = int(tm.turn_state.turn_number or 0) + 1
            state.turn_number = tm.turn_state.turn_number
        if tm.turn_order and pid in tm.turn_order:
            tm.current_player_index = tm.turn_order.index(pid)
        scp.ensure_scp_state(state, pid)
        scp.reset_turn_resources(state, pid)
        scp.fire_turn_start_assets(game, pid)
        scp.draw_cards(game, pid, scp.DRAW_PER_TURN)

    async def _run_ai_turn(self, session: "GameSession", pid: str) -> None:
        tm = session.game.turn_manager
        try:
            await tm.run_turn(pid)
        except Exception as e:  # noqa: BLE001
            print(f"[scp] AI run_turn failed: {e}")

    def _finish_if_over(self, session: "GameSession") -> bool:
        state = session.game.state
        losers = [pid for pid, p in state.players.items() if getattr(p, "has_lost", False)]
        if losers or session.game.is_game_over():
            session.is_finished = True
            for pid in session.player_ids:
                if pid not in losers:
                    session.winner_id = pid
                    break
            return True
        return False

    # ─── Misc helpers ───────────────────────────────────────────────────
    def _other_player(self, session: "GameSession", pid: Optional[str]) -> Optional[str]:
        for other in session.player_ids:
            if other != pid:
                return other
        return None

    def _describe(self, state, atype: str, request) -> str:
        verb = atype.replace("SCP_", "").lower()
        if request.card_id and request.card_id in state.objects:
            return f"{verb} {state.objects[request.card_id].name}"
        if atype == "SCP_INFILTRATE" and request.scp_target:
            return f"infiltrate {'/'.join(str(x) for x in request.scp_target)}"
        return verb

    def _log(self, session: "GameSession", player: Optional[str], text: str) -> None:
        tm = session.game.turn_manager
        turn = int(getattr(tm, "turn_number", 0) or getattr(getattr(tm, "turn_state", None), "turn_number", 0) or 0)
        name = session.player_names.get(player, "AI") if player else ""
        session._game_log.append(GameLogEntry(
            turn=turn, text=(f"{name}: {text}" if name else text),
            event_type="scp_action", player=player, timestamp=time.time(),
        ))

    async def _broadcast(self, session: "GameSession") -> None:
        if not session.on_state_change:
            return
        for pid in session.player_ids:
            socket = session.player_sockets.get(pid)
            if socket:
                state = session.get_client_state(pid)
                await session.on_state_change(pid, state.model_dump())
