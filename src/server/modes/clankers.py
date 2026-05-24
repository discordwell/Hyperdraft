"""
Server-side Clankers mode adapter.

Clankers is a multi-part robot assembly battler with a six-phase per-player
turn (BOOT → ALLOCATE → ASSEMBLE → COMBAT → REASSEMBLE → CLEANUP). The
engine primitives in ``src.engine.clankers`` are synchronous, and the
``ClankersTurnManager`` is also synchronous (``run_turn`` is plain ``def``,
not ``async``) — mirroring the cats engine.

This adapter therefore uses the same transactional pattern as
``cats.py``: rather than going through the MTG-style priority-future loop,
each human ``CLANKERS_*`` action mutates state via the engine module
directly, and bot turns drive ``turn_manager.run_turn`` once per call.

Phase progression for the human seat is tracked via
``state.clankers_current_phase`` (one of "boot" / "allocate" / "assemble" /
"combat" / "reassemble" / "cleanup" / None pre-game). When the human submits
``END_TURN`` (or ``CLANKERS_END_PHASE`` past Reassemble), we run the
remaining phases of their turn, then let the turn manager drive the AI's
full turn, and finally run BOOT + ALLOCATE for the human's next turn so the
client sees a populated hand / refreshed compute pool on the next prompt.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, Optional

from src.server.models import GameLogEntry

from .base import ModeAdapter

if TYPE_CHECKING:
    from src.server.session import GameSession
    from src.server.models import PlayerActionRequest


_HUMAN_PHASES = ("assemble", "combat", "reassemble")


class ClankersModeAdapter(ModeAdapter):
    """Clankers server adapter — per-action transactional, six-phase turn."""

    # ─── Setup ──────────────────────────────────────────────────────────

    async def setup_game(self, session: "GameSession") -> None:
        from src.ai.clankers_adapter import ClankersAIAdapter
        from src.engine import clankers as clankers_engine
        from src.cards.clankers.CLAN.decks import CLAN_STARTER_DECKS

        # Resolve global difficulty fallback.
        if session.ai_profiles_by_player:
            first_profile = next(iter(session.ai_profiles_by_player.values()))
            difficulty = first_profile.get("difficulty", session.ai_difficulty or "medium")
        else:
            difficulty = session.ai_difficulty or "medium"
        if hasattr(difficulty, "value"):
            difficulty = difficulty.value
        difficulty = str(difficulty).strip().lower()
        # Ultra difficulty isn't a heuristic the engine knows; fall back to
        # hard for the in-process adapter (the external runner still drives
        # the seat via /action under "ultra" difficulty).
        engine_difficulty = "hard" if difficulty == "ultra" else difficulty

        tm = session.game.turn_manager

        # Resolve and apply per-seat decks. Decks were NOT loaded in match.py
        # for the clankers branch — we do it here so setup_clankers_player
        # gets the full (deck, core) tuple for each seat.
        deck_ids_by_seat: dict[str, str] = dict(session.deck_id_by_player)
        deck_keys = list(CLAN_STARTER_DECKS.keys())
        for idx, pid in enumerate(session.player_ids):
            key = deck_ids_by_seat.get(pid)
            if key not in CLAN_STARTER_DECKS:
                # Fall back to a deterministic deck per seat. Seat 0 → first
                # registered deck, seat 1 → second, etc.
                key = deck_keys[idx % len(deck_keys)]
                session.deck_id_by_player[pid] = key
            core_def, deck_cards = CLAN_STARTER_DECKS[key]()
            # Stash for any downstream consumer (Ultra agent layer prep).
            session.deck_card_defs_by_player.setdefault(pid, []).extend(deck_cards)
            clankers_engine.setup_clankers_player(
                session.game.state, pid, deck_cards, core_def
            )

        # Set turn order on the turn manager so its turn-state tracker is
        # consistent. We pick seat 0 as the first player.
        if session.player_ids:
            first_id = session.player_ids[0]
            second_id = session.player_ids[1] if len(session.player_ids) > 1 else None
            order = [first_id] + ([second_id] if second_id else [])
            tm.set_turn_order(order)
            tm.state.active_player = first_id
            if tm.turn_state is not None:
                tm.turn_state.active_player_id = first_id
                tm.turn_state.turn_number = 0
            tm.state.turn_number = 0
            tm.state.game_mode = "clankers"
            # P1 skips combat on turn 1 (see clankers_turn.py:_phase_combat).
            tm.state.clankers_first_turn = True  # type: ignore[attr-defined]
            tm.state.clankers_first_player = first_id  # type: ignore[attr-defined]

        # Instantiate the combat manager if the turn manager hasn't already.
        if getattr(tm, "combat_manager", None) is None:
            from src.engine.clankers_combat import ClankersCombatManager
            game_or_tm = getattr(tm.state, "_game", None) or tm
            tm.combat_manager = ClankersCombatManager(game_or_tm)

        # Build per-player AI adapters and register on the turn manager.
        # Ultra seats are detached (external CLI drives them via /action).
        clankers_ai_adapters: dict[str, Any] = {}
        for pid in session.player_ids:
            if pid in session.human_players:
                continue
            if session.is_ultra_ai_player(pid):
                continue
            profile = session.ai_profiles_by_player.get(pid) or {}
            seat_diff = profile.get("difficulty", difficulty)
            if hasattr(seat_diff, "value"):
                seat_diff = seat_diff.value
            seat_diff_str = str(seat_diff).strip().lower()
            if seat_diff_str == "ultra":
                seat_diff_str = "hard"
            adapter = ClankersAIAdapter(difficulty=seat_diff_str)
            adapter.player_id = pid
            clankers_ai_adapters[pid] = adapter
            if hasattr(tm, "set_ai_handler"):
                tm.set_ai_handler(adapter, pid)
            if hasattr(tm, "set_ai_player"):
                tm.set_ai_player(pid)
        session._clankers_ai_adapters = clankers_ai_adapters  # type: ignore[attr-defined]

        # Detach ultra seats so engine-level AI sets don't try to heuristically
        # drive them (the external agent posts moves via /action).
        session.detach_ultra_from_engine_ai_sets()

        # Phase tracker — the human-driven path advances this manually; the
        # bot path doesn't read it.
        session.game.state.clankers_current_phase = None  # type: ignore[attr-defined]
        session.game.state.clankers_pending_attackers = []  # type: ignore[attr-defined]

        # For human_vs_bot: prime the human's first turn so they see a
        # populated hand + refreshed compute pool on the initial state load.
        if session.mode == "human_vs_bot" and session.human_players:
            human_id = next(iter(session.human_players))
            self._open_player_turn(session, human_id)

    # ─── Game loop ──────────────────────────────────────────────────────

    async def run_game_loop(self, session: "GameSession") -> None:
        """Drive the game.

        - bot_vs_bot: drive ``turn_manager.run_turn(active)`` per turn until
          one workshop is breached or we hit a turn cap.
        - human_vs_bot: emit initial state and return; the per-action path
          drives the rest.
        """
        tm = session.game.turn_manager

        if session.mode == "bot_vs_bot":
            from src.engine.clankers import check_workshop_breached
            max_turns = 100  # safety cap so a stuck match doesn't run forever
            turns = 0
            while not session.is_finished and turns < max_turns:
                active = session.game.get_active_player()
                if active is None:
                    break
                try:
                    tm.run_turn(active)
                except Exception as e:
                    print(f"[clankers] run_turn failed: {e}")
                    break
                turns += 1

                if session.record_actions_for_replay:
                    turn_number = int(getattr(tm, "turn_number", 0) or 0)
                    session._record_frame(action={
                        "kind": "turn_complete",
                        "player_id": active,
                        "player_name": session.player_names.get(active, active or ""),
                        "action_type": "CLANKERS_TURN_END",
                        "turn": turn_number,
                    })

                # Workshop breach / engine-flagged game over.
                loser = check_workshop_breached(session.game.state)
                if loser is not None or getattr(session.game.state, "game_over", False):
                    session.is_finished = True
                    # Pick a winner: whichever player isn't the loser. The
                    # turn manager has also already set has_lost on the loser.
                    if loser is not None:
                        for pid in session.player_ids:
                            if pid != loser:
                                session.winner_id = pid
                                break
                    else:
                        session.winner_id = session.game.get_winner()
                    if session.on_state_change:
                        for pid in session.player_ids:
                            socket = session.player_sockets.get(pid)
                            if socket:
                                state = session.get_client_state(pid)
                                await session.on_state_change(pid, state.model_dump())
                    break

                if session.on_state_change:
                    for pid in session.player_ids:
                        socket = session.player_sockets.get(pid)
                        if socket:
                            state = session.get_client_state(pid)
                            await session.on_state_change(pid, state.model_dump())

                if session.spectator_delay_ms > 0:
                    await asyncio.sleep(session.spectator_delay_ms / 1000.0)
            return

        # human_vs_bot: broadcast initial state and return.
        if session.on_state_change:
            for pid in session.human_players:
                socket = session.player_sockets.get(pid)
                if socket:
                    state = session.get_client_state(pid)
                    await session.on_state_change(pid, state.model_dump())

    # ─── Human action callback (not used; transactional path is below) ──

    async def get_human_action(
        self, session: "GameSession", player_id: str, game_state: Any
    ) -> dict:
        """Not used — clankers uses a transactional per-action path."""
        return {"action_type": "CLANKERS_END_PHASE"}

    # ─── Turn predicates ────────────────────────────────────────────────

    def is_ai_turn(self, session: "GameSession") -> bool:
        active = session.game.get_active_player()
        if active is None:
            return False
        if active in session.human_players:
            return False
        if session.is_ultra_ai_player(active):
            # Ultra seats are externally driven; not "AI" in the sense of
            # "run an in-process turn".
            return False
        return True

    async def run_ai_actions(self, session: "GameSession") -> None:
        """Drive one AI turn through the turn manager. Mostly used as a
        passive hook by callers that need to nudge progress after a human
        move. The handle_action path already calls this itself."""
        if not self.is_ai_turn(session):
            return
        active = session.game.get_active_player()
        if active is None:
            return
        tm = session.game.turn_manager
        try:
            tm.run_turn(active)
        except Exception as e:
            print(f"[clankers] AI run_turn failed: {e}")
        if session.record_actions_for_replay:
            session._record_frame(action={
                "kind": "turn_complete",
                "player_id": active,
                "player_name": session.player_names.get(active, active or ""),
                "action_type": "CLANKERS_TURN_END",
                "turn": int(getattr(tm, "turn_number", 0) or 0),
            })

    # ─── Action dispatch ────────────────────────────────────────────────

    async def handle_action(
        self,
        session: "GameSession",
        request: "PlayerActionRequest",
    ) -> tuple[bool, str]:
        """Dispatch a clankers player action.

        The active player must match the requester for state-mutating actions.
        Each branch returns immediately after applying the mutation; the
        END_TURN / END_PHASE branches additionally drive the AI's full turn
        if the turn rolls over.
        """
        from src.engine import clankers as clankers_engine

        atype = request.action_type
        state = session.game.state
        active = session.game.get_active_player()

        # Guard: only the active player may submit play-card / activate /
        # combat-decl actions. END_TURN is similarly active-player-only.
        if request.player_id != active:
            return False, "Not your turn to act"

        if atype == "CLANKERS_PLAY_CARD":
            if not request.card_id:
                return False, "CLANKERS_PLAY_CARD requires card_id"
            hand_zone = state.zones.get(f"hand_{request.player_id}")
            if hand_zone is None or request.card_id not in hand_zone.objects:
                return False, "Card not in your hand"
            kwargs: dict[str, Any] = {}
            if request.target_chassis_id:
                kwargs["target_chassis_id"] = request.target_chassis_id
            if request.targets:
                # Transients accept a list of target ids; flatten the first
                # group of the targets matrix.
                target_ids = [t for t in (request.targets[0] or []) if t]
                if target_ids:
                    kwargs["targets"] = target_ids
            try:
                clankers_engine.play_card_from_hand(
                    state, request.player_id, request.card_id, **kwargs,
                )
            except Exception as e:
                return False, f"play_card_from_hand failed: {e}"
            self._log(session, request.player_id,
                      f"played {self._card_name(state, request.card_id)}")
            session._record_frame(action=request.model_dump())
            await self._broadcast(session)
            return True, "Action accepted"

        if atype == "CLANKERS_ATTACH_PART":
            if not request.part_obj_id or not request.target_chassis_id:
                return False, "CLANKERS_ATTACH_PART requires part_obj_id and target_chassis_id"
            events = clankers_engine.attach_part(
                state, request.part_obj_id, request.target_chassis_id,
            )
            if not events:
                return False, "attach failed (slot full, wrong controller, etc.)"
            self._log(session, request.player_id,
                      f"attached {self._card_name(state, request.part_obj_id)} "
                      f"to {self._card_name(state, request.target_chassis_id)}")
            session._record_frame(action=request.model_dump())
            await self._broadcast(session)
            return True, "Action accepted"

        if atype == "CLANKERS_ACTIVATE_ABILITY":
            if not request.source_obj_id:
                return False, "CLANKERS_ACTIVATE_ABILITY requires source_obj_id"
            targets = []
            if request.targets:
                targets = [t for t in (request.targets[0] or []) if t]
            events = clankers_engine.activate_ability(
                state, request.player_id, request.source_obj_id,
                ability_index=int(request.ability_index or 0),
                targets=targets,
            )
            if not events:
                return False, "activation rejected (cost / target / ownership)"
            self._log(session, request.player_id,
                      f"activated {self._card_name(state, request.source_obj_id)}")
            session._record_frame(action=request.model_dump())
            await self._broadcast(session)
            return True, "Action accepted"

        if atype == "CLANKERS_DECLARE_ATTACKERS":
            # Record attackers and resolve combat phase immediately. The
            # combat manager pulls attackers/blockers from the per-seat
            # AI handler by default; for the human seat we register a
            # transient handler that returns these chosen attackers + then
            # delegates blocker choice to the defender's AI.
            attackers = list(request.attacker_ids or [])
            self._set_phase(session, "combat")
            self._resolve_combat_with_attackers(session, request.player_id, attackers)
            self._log(session, request.player_id,
                      f"declared {len(attackers)} attacker(s)")
            session._record_frame(action=request.model_dump())
            # Auto-advance into Reassemble so the client doesn't need a
            # separate phase-end click to continue playing cards.
            self._set_phase(session, "reassemble")
            await self._broadcast(session)
            return True, "Action accepted"

        if atype == "CLANKERS_DECLARE_BLOCKERS":
            # Record blocker pairing for the human (defender). In the human-
            # vs-bot setup the AI always declares attackers and the human
            # declares blockers in response. This stashes the choice on
            # state so the combat manager can pick it up via the human's
            # ai_handler shim. Real flow: combat runs synchronously inside
            # the AI's run_turn, blocking on a human-action callback we
            # haven't wired here — for the v1 surface we'll store the
            # blocker map and let the next AI turn pick it up. This isn't
            # used in the current human-vs-bot v1 flow (AI auto-blocks via
            # its own adapter); leave a hook for the upcoming UI work.
            session.game.state.clankers_pending_blockers = dict(  # type: ignore[attr-defined]
                request.blocker_pairs or {}
            )
            session._record_frame(action=request.model_dump())
            await self._broadcast(session)
            return True, "Action accepted"

        if atype == "CLANKERS_REFILL_DECISION":
            # Allocate-phase may-refill choice. Apply it via the engine's
            # emit_refill_query and advance to assemble.
            take = True if request.refill_decision is None else bool(request.refill_decision)
            try:
                clankers_engine.emit_refill_query(
                    state, request.player_id, take=take,
                )
            except Exception:
                pass
            self._set_phase(session, "assemble")
            self._log(session, request.player_id,
                      f"{'took' if take else 'declined'} hand refill")
            session._record_frame(action=request.model_dump())
            await self._broadcast(session)
            return True, "Action accepted"

        if atype == "CLANKERS_END_PHASE":
            # Advance through the per-phase state machine. The phase param
            # (if provided) sets the requested next phase; otherwise we
            # advance to the next phase in canonical order.
            next_phase = (request.phase or "").strip().lower() or None
            current = getattr(state, "clankers_current_phase", None) or "assemble"
            if next_phase is None:
                # default progression: assemble → combat → reassemble → end_turn
                ordering = {"assemble": "combat",
                            "combat": "reassemble",
                            "reassemble": "_end_turn"}
                next_phase = ordering.get(current, "_end_turn")
            if next_phase == "_end_turn":
                # Drive Cleanup + roll the turn over.
                await self._advance_through_end_of_turn(session, request.player_id)
                return True, "Turn ended"
            self._set_phase(session, next_phase)
            session._record_frame(action=request.model_dump())
            await self._broadcast(session)
            return True, "Phase advanced"

        return False, f"Unknown Clankers action: {atype}"

    # ─── Phase / turn helpers ──────────────────────────────────────────

    def _set_phase(self, session: "GameSession", phase: str) -> None:
        session.game.state.clankers_current_phase = phase  # type: ignore[attr-defined]

    def _open_player_turn(self, session: "GameSession", player_id: str) -> None:
        """Run BOOT + ALLOCATE for the human's turn, then leave them in
        Assemble.

        We re-implement the BOOT phase inline because the turn manager's
        ``_phase_boot`` advances ``turn_state.turn_number`` and would also
        try to consult the AI handler for the human seat. Mirroring just
        the bookkeeping (untap, compute refresh, refill draw) keeps the
        human's first turn coherent without invoking the full AI-aware
        phase pipeline.
        """
        from src.engine.clankers import (
            CLANKERS_COMPUTE_POOL_BASE, CLANKERS_COMPUTE_CAP,
            emit_refill_query,
        )
        from src.engine.types import ZoneType

        state = session.game.state
        tm = session.game.turn_manager
        if tm.turn_state is not None:
            tm.turn_state.turn_number = int(tm.turn_state.turn_number or 0) + 1
            tm.turn_state.active_player_id = player_id
            state.turn_number = tm.turn_state.turn_number
        state.active_player = player_id

        # Untap own assembly-floor objects.
        floor_key = f"clankers_assembly_floor_{player_id}"
        floor = state.zones.get(floor_key)
        if floor is not None:
            for obj_id in list(floor.objects):
                obj = state.objects.get(obj_id)
                if obj is None or obj.controller != player_id:
                    continue
                if getattr(obj.state, "tapped", False):
                    obj.state.tapped = False

        # Refresh compute pool.
        pool_dict = getattr(state, "clankers_compute_pool", None)
        cap_dict = getattr(state, "clankers_compute_cap", None)
        if pool_dict is not None and cap_dict is not None:
            turn_num = tm.turn_state.turn_number if tm.turn_state else 1
            cap = cap_dict.get(player_id, CLANKERS_COMPUTE_CAP)
            pool_dict[player_id] = min(cap, CLANKERS_COMPUTE_POOL_BASE + turn_num)

        # Mark allocate-phase refill as not-yet-used so emit_refill_query fires.
        refill_used = getattr(state, "clankers_refill_used", None)
        if isinstance(refill_used, dict):
            refill_used[player_id] = False

        # Auto-take the refill draw. Humans rarely want to decline (cards in
        # hand are strictly more options). If a UI wants the may-decline
        # affordance, expose CLANKERS_REFILL_DECISION before this branch
        # runs — currently we just default to take=True so the human sees
        # a 7-card hand at turn start.
        try:
            emit_refill_query(state, player_id, take=True)
        except Exception:
            pass

        self._set_phase(session, "assemble")

    async def _advance_through_end_of_turn(
        self, session: "GameSession", player_id: str,
    ) -> None:
        """Drive Cleanup for the human, then run the opponent's full turn.

        After the opponent's turn ends, open the human's next turn so they
        see a refreshed board on the next state poll.
        """
        # 1. Run Cleanup for the human side. We re-implement just the parts
        #    that matter (refill_used reset, EOT interceptor sweep,
        #    first-turn flag clear) so we don't fight the turn manager.
        state = session.game.state
        tm = session.game.turn_manager
        refill_used = getattr(state, "clankers_refill_used", None)
        if isinstance(refill_used, dict):
            refill_used[player_id] = False

        # Clear duration='end_of_turn' interceptors.
        ic_map = getattr(state, "interceptors", None)
        if isinstance(ic_map, dict):
            eot_ids = [
                ic_id for ic_id, ic in ic_map.items()
                if getattr(ic, "duration", None) == "end_of_turn"
            ]
            for ic_id in eot_ids:
                ic_map.pop(ic_id, None)
                for obj in state.objects.values():
                    if ic_id in obj.interceptor_ids:
                        obj.interceptor_ids.remove(ic_id)

        # First-turn flag clear (per-player, only for the first player).
        first_player_id = getattr(state, "clankers_first_player", None)
        if (
            getattr(state, "clankers_first_turn", False)
            and player_id == first_player_id
        ):
            state.clankers_first_turn = False  # type: ignore[attr-defined]

        self._set_phase(session, None)

        # 2. Swap active player.
        next_player = self._other_player(session, player_id)
        if next_player is None:
            await self._broadcast(session)
            return
        state.active_player = next_player
        if tm.turn_state is not None:
            tm.turn_state.active_player_id = next_player
        if tm.turn_order and next_player in tm.turn_order:
            tm.current_player_index = tm.turn_order.index(next_player)

        # 3. Run the opponent's turn. If they're an in-process AI, run the
        #    full turn manager loop synchronously. If they're an Ultra seat,
        #    leave the turn open for the external CLI to drive via /action.
        if next_player in session.human_players:
            self._open_player_turn(session, next_player)
        elif session.is_ultra_ai_player(next_player):
            # Open the turn (BOOT + ALLOCATE) so the Ultra agent sees a
            # ready board; the agent will then call /action repeatedly.
            self._open_player_turn(session, next_player)
        else:
            try:
                tm.run_turn(next_player)
            except Exception as e:
                print(f"[clankers] AI run_turn failed during end-of-turn: {e}")
            if session.record_actions_for_replay:
                session._record_frame(action={
                    "kind": "turn_complete",
                    "player_id": next_player,
                    "player_name": session.player_names.get(next_player, next_player or ""),
                    "action_type": "CLANKERS_TURN_END",
                    "turn": int(getattr(tm, "turn_number", 0) or 0),
                })

            # 4. Check workshop breach after AI turn.
            from src.engine.clankers import check_workshop_breached
            loser = check_workshop_breached(state)
            if loser is not None or getattr(state, "game_over", False):
                session.is_finished = True
                if loser is not None:
                    for pid in session.player_ids:
                        if pid != loser:
                            session.winner_id = pid
                            break
                else:
                    session.winner_id = session.game.get_winner()
                await self._broadcast(session)
                return

            # 5. Open the human's next turn.
            self._open_player_turn(session, player_id)

        await self._broadcast(session)

    def _resolve_combat_with_attackers(
        self,
        session: "GameSession",
        player_id: str,
        attackers: list[str],
    ) -> None:
        """Wrap the player's AI adapter slot so combat picks human-chosen
        attackers, then call ``combat_manager.resolve_combat_phase``.

        The defender's blocker choice still flows through whatever adapter
        is registered on the turn manager (in human_vs_bot that's the
        opponent's heuristic AI).
        """
        tm = session.game.turn_manager
        original = tm.clankers_ai_handlers.get(player_id)

        class _HumanCombatShim:
            def __init__(self, atk_list):
                self._atk = list(atk_list)

            def choose_attackers(self, state, pid):
                return list(self._atk)

            def choose_blockers(self, state, pid, attackers):
                # Honour any stashed blocker mapping; otherwise no blocks.
                stashed = getattr(state, "clankers_pending_blockers", None) or {}
                if isinstance(stashed, dict) and stashed:
                    return dict(stashed)
                return {}

            def choose_target(self, *args, **kwargs):
                return None

        shim = _HumanCombatShim(attackers)
        if hasattr(tm, "set_ai_handler"):
            tm.set_ai_handler(shim, player_id)
        try:
            if getattr(tm, "combat_manager", None) is not None:
                resolve = getattr(tm.combat_manager, "resolve_combat_phase", None)
                if callable(resolve):
                    try:
                        resolve(player_id)
                    except Exception as e:
                        print(f"[clankers] combat resolve failed: {e}")
        finally:
            # Restore the original adapter so subsequent turns aren't
            # poisoned by the one-shot shim.
            if hasattr(tm, "set_ai_handler"):
                if original is not None:
                    tm.set_ai_handler(original, player_id)
                else:
                    tm.set_ai_handler(None, player_id)

    # ─── Helpers ────────────────────────────────────────────────────────

    def _other_player(self, session: "GameSession", pid: Optional[str]) -> Optional[str]:
        if pid is None:
            return None
        for other in session.player_ids:
            if other != pid:
                return other
        return None

    def _card_name(self, state, card_id: str) -> str:
        obj = state.objects.get(card_id) if card_id else None
        if obj is None:
            return "?"
        return obj.name or "?"

    def _log(self, session: "GameSession", player: Optional[str], text: str) -> None:
        tm = session.game.turn_manager
        turn = int(getattr(tm, "turn_number", 0) or 0)
        name = session.player_names.get(player, "AI") if player else ""
        full = f"{name}: {text}" if name else text
        session._game_log.append(GameLogEntry(
            turn=turn,
            text=full,
            event_type="clankers_action",
            player=player,
            timestamp=time.time(),
        ))

    async def _broadcast(self, session: "GameSession") -> None:
        if not session.on_state_change:
            return
        for pid in session.player_ids:
            socket = session.player_sockets.get(pid)
            if socket:
                state = session.get_client_state(pid)
                await session.on_state_change(pid, state.model_dump())
