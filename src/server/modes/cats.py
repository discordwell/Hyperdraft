"""
Server-side Cats mode adapter.

Cats is round-based: both players act every round. This adapter implements a
transactional per-action model rather than the priority/turn future pattern
used by MTG-style engines:

- ``CATS_PLAY_CARD``  : human plays a card into the current trick. If both
                       sides have committed, the round auto-resolves
                       (resolve_trick + claim by AI if AI won + end_round).
- ``CATS_CHOOSE_PILE``: trick winner (human side) picks a pile. After the
                       pile is claimed we run end_round and begin the next.

Because the cats engine's ``run_turn`` advances by one full round (and the
human's two decisions span pounce/counter + claim phases), we drive the
round manually here rather than relying on the CatsTurnManager's future
infrastructure. Bot-vs-bot still uses ``turn_manager.run_turn`` for the
spectator demo.
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


_PILE_NAMES = ("pile_territory", "pile_nap", "pile_snack", "pile_attention")


class CatsModeAdapter(ModeAdapter):
    """Cats server adapter — round-based, transactional."""

    async def setup_game(self, session: "GameSession") -> None:
        from src.ai.cats_adapter import CatsAIAdapter
        from src.engine.cats import begin_round

        # Resolve difficulty
        if session.ai_profiles_by_player:
            first_profile = next(iter(session.ai_profiles_by_player.values()))
            difficulty = first_profile.get("difficulty", session.ai_difficulty or "medium")
        else:
            difficulty = session.ai_difficulty or "medium"
        if hasattr(difficulty, "value"):
            difficulty = difficulty.value
        difficulty = str(difficulty).strip().lower()

        tm = session.game.turn_manager

        # Register cats AI adapters on the turn manager — primarily for the
        # bot_vs_bot path that calls run_turn(). The per-action human path
        # below uses the same adapters via session._cats_ai_adapters.
        cats_ai_adapters: dict[str, Any] = {}
        for pid in session.player_ids:
            if pid in session.human_players:
                continue
            profile = session.ai_profiles_by_player.get(pid) or {}
            player_diff = profile.get("difficulty", difficulty)
            if hasattr(player_diff, "value"):
                player_diff = player_diff.value
            adapter = CatsAIAdapter(difficulty=str(player_diff).strip().lower())
            adapter.player_id = pid
            cats_ai_adapters[pid] = adapter
            if hasattr(tm, "set_ai_handler"):
                tm.set_ai_handler(pid, adapter)
            if hasattr(tm, "set_ai_player"):
                tm.set_ai_player(pid)
        # Stash adapters on the session for the transactional human-action path.
        session._cats_ai_adapters = cats_ai_adapters  # type: ignore[attr-defined]

        # Set the initial lead player. Cats begins round 1 with players[0] as
        # lead (per design §3). In human_vs_bot the human is seat 0.
        player_ids = list(session.game.state.players.keys())
        if player_ids:
            session.game.state.cats_lead_player = player_ids[0]
            session.game.state.cats_round_number = 1
            session.game.state.active_player = player_ids[0]

        # Open round 1: untaps pile cards (none yet) and fires CATS_ROUND_START.
        try:
            begin_round(session.game.state)
        except Exception as e:
            print(f"[cats] begin_round failed during setup: {e}")

        # Pre-play the AI's Pounce if AI is the round-1 follower (i.e. human leads).
        # Cats §3: the *follower* (non-lead) plays first in the Pounce phase.
        if session.mode == "human_vs_bot":
            self._maybe_play_ai_pounce(session)

    async def run_game_loop(self, session: "GameSession") -> None:
        """Run the cats game loop.

        - bot_vs_bot: drives full rounds via turn_manager.run_turn() until done.
        - human_vs_bot: emits state and returns; the per-action path
          (handle_action) advances rounds when the human submits decisions.
        """
        if session.mode == "bot_vs_bot":
            tm = session.game.turn_manager
            while not session.is_finished:
                try:
                    await tm.run_turn()
                except Exception as e:
                    print(f"[cats] run_turn failed: {e}")
                    break

                # Record a replay frame per round so ReplayView's scrubber has
                # something to anchor on. The cats engine doesn't route through
                # the MTG priority pipeline, so _on_action_processed never
                # fires — this is the cats equivalent of the per-turn record
                # block in src/server/routes/bot_game.py:run_bot_game.
                if session.record_actions_for_replay:
                    round_num = int(getattr(session.game.state, "cats_round_number", 0) or 0)
                    session._record_frame(action={
                        "kind": "action_processed",
                        "player_id": session.game.get_active_player(),
                        "player_name": session.player_names.get(
                            session.game.get_active_player(), ""
                        ) if hasattr(session.game, "get_active_player") else "",
                        "action_type": "CATS_ROUND_END",
                        "data": {"round_number": round_num},
                    })

                if session.game.is_game_over():
                    session.is_finished = True
                    session.winner_id = session.game.get_winner()
                    if session.on_state_change:
                        for pid in session.player_ids:
                            socket = session.player_sockets.get(pid)
                            if socket:
                                state = session.get_client_state(pid)
                                await session.on_state_change(pid, state.model_dump())
                    break

                # Broadcast updated state after each round.
                if session.on_state_change:
                    for pid in session.player_ids:
                        socket = session.player_sockets.get(pid)
                        if socket:
                            state = session.get_client_state(pid)
                            await session.on_state_change(pid, state.model_dump())

                # Pacing delay for spectators.
                if session.spectator_delay_ms > 0:
                    await asyncio.sleep(session.spectator_delay_ms / 1000.0)
            return

        # human_vs_bot — broadcast initial state and return. The handle_action
        # path drives subsequent rounds in response to player actions.
        if session.on_state_change:
            for pid in session.human_players:
                socket = session.player_sockets.get(pid)
                if socket:
                    state = session.get_client_state(pid)
                    await session.on_state_change(pid, state.model_dump())

    async def get_human_action(
        self, session: "GameSession", player_id: str, game_state: Any
    ) -> dict:
        """Not used — cats uses a transactional per-action path, not futures."""
        return {"action_type": "CATS_PLAY_CARD"}

    async def handle_action(
        self,
        session: "GameSession",
        request: "PlayerActionRequest",
    ) -> tuple[bool, str]:
        """Dispatch a cats player action.

        Two action types:
          - CATS_PLAY_CARD {card_id}    : commit a card to the current trick
          - CATS_CHOOSE_PILE {pile_name}: winner picks a pile

        After each human action we drive the AI's matching decision so the
        round either fully resolves (both cards played → resolve + claim by
        winner if AI won → end_round → begin_round + AI pounce if AI follows
        next round) or pauses waiting for the human's next decision.
        """
        from src.engine.cats import (
            play_card_to_trick, resolve_trick, claim_pile, end_round,
            begin_round, check_game_over, finalize_game,
        )

        atype = request.action_type
        state = session.game.state

        if atype == "CATS_PLAY_CARD":
            if not request.card_id:
                return False, "CATS_PLAY_CARD requires card_id"
            # Validate card is in the player's hand.
            hand_zone = state.zones.get(f"HAND_{request.player_id}")
            if hand_zone is None or request.card_id not in hand_zone.objects:
                return False, "Card not in your hand"

            # Determine whether this is pounce or counter for the player.
            trick = state.cats_current_trick or {}
            lead = getattr(state, "cats_lead_player", None)
            follower = self._other_player(session, lead)
            # If no pounce yet, only the follower may play; if counter,
            # only the lead.
            if trick.get("pounce_card") is None:
                expected = follower
                role = "pounce"
            elif trick.get("counter_card") is None:
                expected = lead
                role = "counter"
            else:
                return False, "Both players have already played; resolve in progress"

            if request.player_id != expected:
                return False, f"Not your turn to play ({role})"

            play_card_to_trick(state, request.player_id, request.card_id, role=role)
            self._log(session, request.player_id, f"played {self._card_name(state, request.card_id)} ({role})")

            # If the human just played pounce, the AI plays counter; if the
            # human just played counter, both cards are committed, run the
            # full resolution. Either way we keep driving until we either
            # hit a phase that needs the human (their pounce next round, or
            # the human-winner's pile pick) or the game ends.
            await self._drive_until_human(session, role_just_played=role)

            session._record_frame(action=request.model_dump())
            await self._broadcast(session)
            return True, "Action accepted"

        if atype == "CATS_CHOOSE_PILE":
            pile_name = request.pile_name
            if pile_name not in _PILE_NAMES:
                return False, f"Unknown pile: {pile_name}"
            # Validate this player is the trick winner.
            trick = state.cats_current_trick or {}
            winner = trick.get("winner")
            if winner != request.player_id:
                return False, "You did not win the current trick"

            claim_pile(state, winner, pile_name)
            self._log(session, request.player_id, f"claimed trick into {pile_name}")

            # Continue the round: end_round → begin_round → AI pounce if AI follows.
            await self._advance_to_next_decision(session)

            session._record_frame(action=request.model_dump())
            await self._broadcast(session)
            return True, "Action accepted"

        if atype == "CATS_KNOCK_OVER":
            # Pile-tap activated ability. Validation rules (per design §8.7):
            #   1. card_id required
            #   2. card must be in one of the player's piles
            #   3. card must be untapped
            #   4. card must have a registered CATS_KNOCK_OVER interceptor
            # `activate_pile_card` enforces (2) and (3) internally; we surface
            # rejections by inspecting state before/after so the client sees a
            # clear error. (4) is verified by scanning state.interceptors.
            from src.engine.cats import activate_pile_card
            from src.engine.types import EventType

            if not request.card_id:
                return False, "CATS_KNOCK_OVER requires card_id"
            card_id = request.card_id
            piles = state.cats_piles.get(request.player_id, {}) if hasattr(state, "cats_piles") else {}
            pile_name = None
            for name in ("pile_territory", "pile_nap", "pile_snack", "pile_attention"):
                if card_id in piles.get(name, []):
                    pile_name = name
                    break
            if pile_name is None:
                return False, "Card is not in one of your piles"
            obj = state.objects.get(card_id)
            if obj is None:
                return False, "Card not found"
            if obj.state.tapped:
                return False, "Card is already knocked over (tapped)"
            # Confirm a CATS_KNOCK_OVER interceptor exists for this card.
            has_handler = False
            for ic in state.interceptors.values():
                if ic.source != card_id:
                    continue
                # A pile-activated handler is REACT-priority and filters on
                # CATS_KNOCK_OVER events. Build a synthetic probe event with
                # the right card_id so the interceptor's filter accepts it.
                from src.engine.types import Event as _Event
                probe = _Event(
                    type=EventType.CATS_KNOCK_OVER,
                    payload={"player": request.player_id, "card_id": card_id, "pile": pile_name},
                    source=card_id,
                )
                try:
                    if ic.filter(probe, state):
                        has_handler = True
                        break
                except Exception:
                    continue
            if not has_handler:
                return False, "Card has no activated ability"

            events = activate_pile_card(state, request.player_id, card_id)
            self._log(
                session,
                request.player_id,
                f"knocked over {self._card_name(state, card_id)} ({pile_name})",
            )
            session._record_frame(action=request.model_dump())
            await self._broadcast(session)
            if not events:
                # activate_pile_card silently failed (eg owner mismatch). Surface as success=False.
                return False, "Pile activation failed"
            return True, "Action accepted"

        return False, f"Unknown Cats action: {atype}"

    # ─── Round-driving helpers ──────────────────────────────────────────

    async def _drive_until_human(
        self,
        session: "GameSession",
        *,
        role_just_played: str,
    ) -> None:
        """Advance the round state machine until the human is needed (or game ends).

        After the human plays pounce: AI plays counter, trick resolves, if AI
        won the trick AI claims a pile + end_round + begin next round + AI
        pounces if AI is the new follower; if human won, we stop at the claim
        phase awaiting the human's CATS_CHOOSE_PILE.

        After the human plays counter (i.e. trick has both cards): resolve,
        same branching for winner.
        """
        from src.engine.cats import (
            play_card_to_trick, resolve_trick, claim_pile,
        )

        state = session.game.state
        trick = state.cats_current_trick or {}
        lead = getattr(state, "cats_lead_player", None)
        follower = self._other_player(session, lead)

        # Step 1: if only pounce is set, the lead (whoever they are) must play counter.
        if trick.get("pounce_card") is not None and trick.get("counter_card") is None:
            counter_player = lead
            if counter_player and counter_player not in session.human_players:
                ai = self._ai_for(session, counter_player)
                hand_zone = state.zones.get(f"HAND_{counter_player}")
                hand_ids = list(hand_zone.objects) if hand_zone else []
                if not hand_ids:
                    # Empty hand edge case — skip
                    return
                if ai is not None:
                    chosen = ai.choose_card(state, hand_ids)
                else:
                    chosen = hand_ids[0]
                play_card_to_trick(state, counter_player, chosen, role="counter")
                self._log(session, counter_player, f"played {self._card_name(state, chosen)} (counter)")
                trick = state.cats_current_trick or {}
            # If lead is human, we stop here and wait for their counter via /action.
            elif counter_player in session.human_players:
                return

        # Step 2: if both cards committed, resolve.
        if trick.get("pounce_card") and trick.get("counter_card") and not trick.get("winner"):
            resolve_trick(state)
            trick = state.cats_current_trick or {}
            winner = trick.get("winner")
            self._log(session, winner, "won the trick")

        # Step 3: claim phase — winner picks a pile.
        winner = trick.get("winner")
        if winner is not None:
            if winner in session.human_players:
                # Stop and wait for the human's CATS_CHOOSE_PILE.
                return
            # AI claims via choose_pile.
            ai = self._ai_for(session, winner)
            available = self._available_piles(state, winner)
            cards = [c for c in (trick.get("pounce_card"), trick.get("counter_card")) if c]
            if ai is not None:
                pile_choice = ai.choose_pile(state, cards, available)
            else:
                pile_choice = available[0] if available else "pile_attention"
            claim_pile(state, winner, pile_choice)
            self._log(session, winner, f"claimed trick into {pile_choice}")

        # Step 4: advance to the next decision (end_round + begin next + AI pounce if needed).
        await self._advance_to_next_decision(session)

    async def _advance_to_next_decision(self, session: "GameSession") -> None:
        """Run end_round + begin_round + AI pounce (if AI is follower next round).

        If the game ends mid-advance, set session flags accordingly.
        """
        from src.engine.cats import (
            end_round, begin_round, check_game_over, finalize_game,
        )

        state = session.game.state
        end_events = end_round(state)
        for ev in end_events:
            pass  # events are processed in-engine

        if check_game_over(state):
            finalize_events = finalize_game(state)
            session.is_finished = True
            # Pick the winner — pull from cats_winners list.
            winners = getattr(state, "cats_winners", []) or []
            if len(winners) == 1:
                session.winner_id = winners[0]
            self._log(session, None, "Game over!")
            return

        # Begin the next round.
        begin_events = begin_round(state)
        for ev in begin_events:
            pass

        # If AI is the new follower, pre-play their pounce so the human's
        # next decision sees the trick already opened.
        self._maybe_play_ai_pounce(session)

    def _maybe_play_ai_pounce(self, session: "GameSession") -> None:
        """If the round's *follower* is an AI seat, have them play the Pounce now.

        The follower is the *non-lead* player. Per cats §3 the follower commits
        first ("intentionally backwards from intuition"). We pre-play here so
        the human (the lead) sees a populated trick when they're prompted for
        their Counter-pounce.
        """
        from src.engine.cats import play_card_to_trick

        state = session.game.state
        trick = state.cats_current_trick or {}
        if trick.get("pounce_card") is not None:
            return  # already played
        lead = getattr(state, "cats_lead_player", None)
        follower = self._other_player(session, lead)
        if follower is None or follower in session.human_players:
            return  # human will play, or no opponent

        ai = self._ai_for(session, follower)
        hand_zone = state.zones.get(f"HAND_{follower}")
        hand_ids = list(hand_zone.objects) if hand_zone else []
        if not hand_ids:
            return
        if ai is not None:
            chosen = ai.choose_card(state, hand_ids)
        else:
            chosen = hand_ids[0]
        play_card_to_trick(state, follower, chosen, role="pounce")
        self._log(session, follower, f"played {self._card_name(state, chosen)} (pounce)")

    # ─── Helpers ────────────────────────────────────────────────────────

    def _other_player(self, session: "GameSession", pid: Optional[str]) -> Optional[str]:
        if pid is None:
            return None
        for other in session.player_ids:
            if other != pid:
                return other
        return None

    def _ai_for(self, session: "GameSession", player_id: str):
        adapters = getattr(session, "_cats_ai_adapters", None) or {}
        return adapters.get(player_id)

    def _available_piles(self, state, player_id: str) -> list[str]:
        """Return non-full pile names for the given player. Always includes attention."""
        from src.engine.cats import CATS_PILE_CAPS

        piles = getattr(state, "cats_piles", {}).get(player_id, {})
        available = []
        for name in ("pile_territory", "pile_nap", "pile_snack"):
            cap = CATS_PILE_CAPS.get(name, 999)
            # We add 2 cards per claim; only include if there's room.
            if len(piles.get(name, [])) + 2 <= cap:
                available.append(name)
        if not available:
            available.append("pile_attention")
        return available

    def _card_name(self, state, card_id: str) -> str:
        obj = state.objects.get(card_id)
        if obj is None:
            return "?"
        return obj.name or "?"

    def _log(self, session: "GameSession", player: Optional[str], text: str) -> None:
        turn = int(getattr(session.game.state, "cats_round_number", 0) or 0)
        name = session.player_names.get(player, "AI") if player else ""
        full = f"{name}: {text}" if name else text
        session._game_log.append(GameLogEntry(
            turn=turn,
            text=full,
            event_type="cats_action",
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
