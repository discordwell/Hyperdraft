"""
Cats Turn Manager
=================

Drives the six-phase Cats *round* loop. Cats is symmetric per round — both
players act every round — so this manager bends the TurnManager protocol
the same way the other "no-priority" engines do: ``run_turn`` advances one
full round, both seats commit cards, the trick resolves, the winner claims
into a pile, and end-of-round bookkeeping fires.

Phase order (mirrors ``docs/games/cats.md`` § 3):

    1. STRETCH         — Round-open. Round-start triggers fire; commanders /
                         trinkets recompute. (Cards untap, etc.)
    2. POUNCE          — The *non-lead* player commits the first card.
                         The card's Category installs the round's trick rule.
    3. COUNTER-POUNCE  — The *lead* player commits the second card. They
                         see what was pounced and react.
    4. RESOLVE         — Compare the two cards under the installed rule.
                         Determine winner.
    5. CLAIM           — Winner picks one of their scoring piles. Snack rules
                         may force the choice.
    6. CURL UP         — End-of-round. Round-end triggers fire. Hands refill
                         if both empty. ``round_number`` increments. Lead
                         rotates for next round.

Every phase emits ``PHASE_START`` / ``PHASE_END`` events with payload
``{"phase": "cats_<name>", "player": <id>}`` so card triggers can hook them.

After CURL UP the manager checks ``cats.check_game_over(state)``; on True
it calls ``cats.finalize_game(state)`` (which scores piles and emits
PLAYER_WINS / PLAYER_LOSES / a tie marker) and exits.

This file lives behind the same TurnManager protocol as
``minecraft_turn.py``, ``hearthstone_turn.py``, and ``depths_turn.py``.
Peer-module imports (``src.engine.cats``, ``src.engine.cats_combat``) are
guarded and deferred so this file can be imported while Agents 1 and 2 are
still in flight.

AI handler contract (Agent 4 implements these on ``CatsAIAdapter``):

    handler.choose_card(state, available_card_ids: list[str]) -> str
        Return one card object id from ``available_card_ids`` (the hand
        cards the player can legally pounce / counter-pounce).

    handler.choose_pile(
        state,
        won_card_ids: list[str],
        available_pile_names: list[str],
    ) -> str
        Return one pile name from ``available_pile_names``. Names are the
        zone-key suffixes: ``"pile_territory"``, ``"pile_nap"``,
        ``"pile_snack"``, or ``"pile_attention"`` if overflow forces it.

    handler.choose_activations(state) -> list[tuple[str, int]]
        Return a list of ``(card_obj_id, ability_index)`` pairs to activate
        at the start of the round (called during STRETCH).  Empty list =
        no activations.  Easy AIs always return ``[]``.

All three calls return *plain* shapes — strings or list-of-tuples. The
``_ask_ai`` dispatcher is defensive: if a future AI returns a dataclass
wrapper (e.g. ``Choice(card_id=...)``), it unwraps via the conventional
attribute names (``card_id`` / ``pile`` / ``activations``).

# TODO: reconciliation — register CatsTurnManager in
# src/engine/mode_adapter.py:_REGISTRY under "cats" via a new
# CatsModeAdapter, and add the matching ``game_mode == "cats"`` branches
# wherever ``Game`` dispatches per-mode (e.g. setup_starting_hands).
# Agent 1 may have already done part of this in src/engine/cats.py.
"""

from __future__ import annotations

import inspect
import random
from typing import Any, Optional, TYPE_CHECKING

from .turn import TurnManager, Phase, Step
from .types import (
    Event,
    EventType,
    GameObject,
    GameState,
    Player,
)

if TYPE_CHECKING:  # pragma: no cover — type-only imports
    from .pipeline import EventPipeline


# =============================================================================
# Defaults — used until Agent 1's cats.py lands
# =============================================================================

# Doc § 2: 9 rounds = "a day in the life of a cat".
_DEFAULT_TOTAL_ROUNDS = 9
# Doc § 11 Q2: 5-card hand recommended for v1.
_DEFAULT_HAND_SIZE = 5
# Safety cap on the inner phase dispatch loop (defensive — never hit in normal play).
_PHASE_LOOP_CAP = 32

# Canonical pile zone-key suffixes. Same strings the AI adapter sees in
# ``available_pile_names`` and the same strings ``cats.claim_pile`` expects.
PILE_TERRITORY = "pile_territory"
PILE_NAP = "pile_nap"
PILE_SNACK = "pile_snack"
PILE_ATTENTION = "pile_attention"

# Pile caps from doc § 5. Used as a fallback when Agent 1's cats module is
# not yet importable; cats.claim_pile is the source of truth at runtime.
_DEFAULT_PILE_CAPS = {
    PILE_TERRITORY: 8,
    PILE_NAP: 6,
    PILE_SNACK: 5,
    PILE_ATTENTION: 10_000,  # effectively unlimited
}


# =============================================================================
# Guarded peer-module imports (Agents 1 and 2)
# =============================================================================

def _import_cats_module():
    """Return the ``src.engine.cats`` module if Agent 1 has shipped it."""
    try:
        from . import cats as _cats  # type: ignore
        return _cats
    except Exception:
        return None


def _import_combat_module():
    """Return the ``src.engine.cats_combat`` module if Agent 2 has shipped it."""
    try:
        from . import cats_combat as _cats_combat  # type: ignore
        return _cats_combat
    except Exception:
        return None


def _get_constant(name: str, default: Any) -> Any:
    """Look up a constant in Agent 1's cats module, with a typed fallback.

    Used for ``CATS_TOTAL_ROUNDS`` / ``CATS_HAND_SIZE`` etc. so the turn
    manager works in isolation while Agent 1 is still landing the module.
    """
    cats = _import_cats_module()
    if cats is None:
        return default
    return getattr(cats, name, default)


# =============================================================================
# CatsTurnManager
# =============================================================================

class CatsTurnManager(TurnManager):
    """Turn manager for the Cats engine.

    Drives the six-phase round loop:

        STRETCH -> POUNCE -> COUNTER-POUNCE -> RESOLVE -> CLAIM -> CURL UP

    Calls into ``CatsTrickManager`` for trick resolution and the registered
    ``CatsAIAdapter`` instances for in-round decisions.

    Public surface mirrors the other engine turn managers
    (``HearthstoneTurnManager``, ``MinecraftTurnManager``,
    ``DepthsTurnManager``):

      * ``__init__(state)``       — built by ``Game`` via mode adapter.
      * ``setup_game()``          — one-shot post-construction wiring.
      * ``set_ai_handler(pid, h)``— register an AI adapter for a player.
      * ``set_ai_player(pid)``    — mark a player as AI-controlled.
      * ``run_turn(player_id=None)`` — run one full ROUND.
    """

    PHASES: list[str] = [
        "stretch",
        "pounce",
        "counter_pounce",
        "resolve",
        "claim",
        "curl_up",
    ]

    # ---------------------------------------------------------------------
    # Construction & accessors
    # ---------------------------------------------------------------------
    def __init__(self, state: Optional[GameState] = None):
        # Defensive: ``CatsTurnManager(None)`` must not crash. We only call
        # ``super().__init__`` when a real state is provided.
        if state is not None:
            super().__init__(state)
        else:
            # Mirror the bits of TurnManager.__init__ that callers use so
            # an unparented instance is still inspectable. This branch only
            # exists for self-validation / harness construction.
            self.state = None  # type: ignore[assignment]
            self.turn_state = None  # type: ignore[assignment]
            self.priority_system = None
            self.combat_manager = None
            self.pipeline = None
            self.on_phase_change = None
            self.on_step_change = None
            self.turn_order = []
            self.current_player_index = 0

        # Cats-specific scaffolding ---------------------------------------
        # Lazy-init in ``setup_game``: the trick manager closes over the
        # GameState and lives for the whole game.
        self.trick_manager: Optional[Any] = None  # CatsTrickManager when typed.

        # Per-player AI adapter. ``set_ai_handler(player_id, handler)``
        # populates this. Mirror what depths_turn does with per-player
        # handlers — but Cats *requires* per-player adapters because both
        # seats decide every round.
        self.cats_ai_handlers: dict[str, Any] = {}

        # Tracks which players are AI-controlled (used by ``_is_ai_player``).
        self.ai_players: set[str] = set()

        # The "lead" player for the *current* round. Round 1 = players[0]
        # by convention; alternates each round (see ``_rotate_lead``).
        self.lead_player_id: Optional[str] = None

        # Defensive: if Agent 1 attaches their own state container to
        # GameState (e.g. ``state.cats`` or scattered ``state.cats_*``
        # attributes), we read through these helpers rather than hard-
        # coding either layout.
        self._cats_state_cache: dict[str, Any] = {}

    # ---------------------------------------------------------------------
    # GameState <-> cats-engine-state bridging
    # ---------------------------------------------------------------------
    #
    # Agent 1 may model their engine state either as:
    #   (A) attribute-attached on GameState: ``state.cats_round_number``,
    #       ``state.cats_lead_player``, ``state.cats_current_rule``,
    #       ``state.cats_current_trick``, ``state.cats_commanders``.
    #   (B) a sub-namespace: ``state.cats`` holding everything.
    #
    # The docs/cats.md § 8 "Required GameState fields" list suggests (A),
    # but the brief explicitly notes the reconciliation agent will paper
    # over drift. These helpers tolerate either layout.
    # ---------------------------------------------------------------------

    def _get_cats_state(self) -> Any:
        """Return the cats sub-namespace, or a dict-like shim over the
        ``state.cats_*`` attributes if Agent 1 used the flat layout.
        """
        if self.state is None:
            return None
        sub = getattr(self.state, "cats", None)
        if sub is not None:
            return sub
        return self._cats_state_cache  # may be empty until setup_game runs.

    def _set_cats_field(self, name: str, value: Any) -> None:
        """Set a cats-engine field on whichever layout Agent 1 picked."""
        if self.state is None:
            return
        sub = getattr(self.state, "cats", None)
        if sub is not None:
            try:
                setattr(sub, name, value)
                return
            except Exception:
                pass
        # Flat layout: ``state.cats_round_number`` etc.
        try:
            setattr(self.state, f"cats_{name}", value)
        except Exception:
            self._cats_state_cache[name] = value

    def _get_cats_field(self, name: str, default: Any = None) -> Any:
        """Read a cats-engine field across either layout."""
        if self.state is None:
            return default
        sub = getattr(self.state, "cats", None)
        if sub is not None:
            val = getattr(sub, name, None)
            if val is not None:
                return val
        flat = getattr(self.state, f"cats_{name}", None)
        if flat is not None:
            return flat
        return self._cats_state_cache.get(name, default)

    # ---------------------------------------------------------------------
    # AI handler registration
    # ---------------------------------------------------------------------
    def set_ai_handler(self, player_id_or_handler: Any, handler: Any = None) -> None:
        """Register an AI adapter for a player.

        Two call shapes supported for parity with the other engines:
          * ``set_ai_handler(handler)`` — install ``handler`` for every
            currently-known player. Used by single-handler tests.
          * ``set_ai_handler(player_id, handler)`` — per-player install.
        """
        if handler is None and not isinstance(player_id_or_handler, str):
            # Single-arg form: handler positional, no player_id.
            shared = player_id_or_handler
            if self.state is not None:
                for pid in self.state.players:
                    self.cats_ai_handlers[pid] = shared
            return
        pid = player_id_or_handler
        if handler is None:
            self.cats_ai_handlers.pop(pid, None)
        else:
            self.cats_ai_handlers[pid] = handler

    def set_ai_player(self, player_id: str) -> None:
        """Mark a player as AI-controlled."""
        self.ai_players.add(player_id)

    def _is_ai_player(self, player_id: Optional[str]) -> bool:
        return bool(player_id and player_id in self.ai_players)

    # ---------------------------------------------------------------------
    # Setup
    # ---------------------------------------------------------------------
    def setup_game(self) -> None:
        """One-shot setup called after the GameState is built.

        Wires up:
          * the ``CatsTrickManager`` (Agent 2's module);
          * the initial ``round_number`` (1);
          * the initial ``lead_player_id`` (players[0] — alternates each
            round per doc § 3);
          * the empty current_trick scratchpad.
        """
        if self.state is None:
            return

        # Lazy-import the combat module — Agent 2 may still be in flight.
        combat = _import_combat_module()
        if combat is not None and hasattr(combat, "CatsTrickManager"):
            try:
                self.trick_manager = combat.CatsTrickManager(self.state)
            except Exception:
                # If Agent 2's constructor signature drifted, fall back
                # to leaving ``trick_manager`` None; ``_phase_resolve``
                # tolerates this.
                self.trick_manager = None

        # Initialise round number and lead. Doc § 3: round 1 = player 1.
        player_ids = list(self.state.players.keys())
        first_lead = player_ids[0] if player_ids else None

        self._set_cats_field("round_number", 1)
        self._set_cats_field("lead_player", first_lead)
        self._set_cats_field("current_rule", None)
        self._set_cats_field("current_trick", {})
        self._set_cats_field("game_over", False)
        self.lead_player_id = first_lead

        # Standard turn manager bookkeeping. ``turn_number`` mirrors the
        # round number for compatibility with downstream tools that key
        # off ``state.turn_number``.
        if self.turn_state is not None:
            self.turn_state.turn_number = 0
            self.turn_state.active_player_id = first_lead
            self.turn_state.phase = Phase.BEGINNING
            self.turn_state.step = Step.UNTAP

        if not self.turn_order and player_ids:
            self.set_turn_order(player_ids)

        # Mirror ``state.active_player`` to the lead so legacy interceptors
        # can read ``state.active_player`` without needing the cats sub-
        # namespace. Cats doesn't really have an "active player" in the
        # MTG sense — but the lead is the closest analog.
        if first_lead is not None:
            self.state.active_player = first_lead

    # ---------------------------------------------------------------------
    # Turn driver — one full ROUND.
    # ---------------------------------------------------------------------
    async def run_turn(self, player_id: Optional[str] = None) -> list[Event]:
        """Run one complete *round* (the Cats analog of a turn).

        ``player_id`` is accepted for protocol parity with the base class
        but is ignored — both players act every round.  The "active
        player" pointer is set to whichever seat is currently the lead
        (doc § 3: lead alternates each round).
        """
        events: list[Event] = []

        if self.state is None:
            return events

        # If setup hasn't been called yet, do it now. (Safety net for
        # callers that go straight from ``Game(mode="cats")`` to
        # ``await game.run_turn()``.)
        if self._get_cats_field("round_number", None) is None:
            self.setup_game()

        # Sync the active-player pointer to the lead and bump round +
        # turn_number trackers.
        active = self.lead_player_id or (
            self.turn_order[self.current_player_index]
            if self.turn_order else None
        )
        self.lead_player_id = active
        self._set_cats_field("lead_player", active)

        if self.turn_state is not None:
            self.turn_state.active_player_id = active
            self.turn_state.turn_number = int(
                self._get_cats_field("round_number", 1) or 1
            )
        self.state.active_player = active
        self.state.turn_number = int(self._get_cats_field("round_number", 1) or 1)

        # Emit TURN_START so downstream tooling (replays, the server-side
        # game-log) sees a turn boundary. Cats rounds map 1:1 to "turns"
        # for serialization purposes.
        turn_start = Event(
            type=EventType.TURN_START,
            payload={
                "player": active,
                "turn_number": self.turn_state.turn_number if self.turn_state else 1,
                "cats_round": self._get_cats_field("round_number", 1),
                "cats_lead": active,
            },
        )
        if self.pipeline is not None:
            self.pipeline.emit(turn_start)
        events.append(turn_start)

        # Run the six phases. Each helper emits its own PHASE_START /
        # PHASE_END and returns the events it generated.
        for phase_name in self.PHASES:
            events.extend(await self._run_phase(phase_name))
            if self._is_game_over():
                # ``cats.check_game_over`` already returned True (or a
                # player called game-over mid-phase). Bail before the
                # remaining phases run.
                break

        # End-of-round game-over check. Doc § 2 says this fires after
        # CURL UP. The per-phase break above handles the rare case where
        # a card or sweep flips game_over mid-round.
        if self._game_over_check():
            cats = _import_cats_module()
            if cats is not None and hasattr(cats, "finalize_game"):
                try:
                    finalize_events = cats.finalize_game(self.state) or []
                    for ev in finalize_events:
                        if self.pipeline is not None:
                            self.pipeline.emit(ev)
                        events.append(ev)
                except Exception:
                    # Don't let a buggy finalize_game crash the turn loop.
                    pass
            self._set_cats_field("game_over", True)

            game_end = Event(
                type=EventType.GAME_END,
                payload={"reason": "day_complete"},
            )
            if self.pipeline is not None:
                self.pipeline.emit(game_end)
            events.append(game_end)

        # Emit TURN_END for symmetry with TURN_START.
        turn_end = Event(
            type=EventType.TURN_END,
            payload={
                "player": active,
                "turn_number": self.turn_state.turn_number if self.turn_state else 1,
                "cats_round": self._get_cats_field("round_number", 1),
            },
        )
        if self.pipeline is not None:
            self.pipeline.emit(turn_end)
        events.append(turn_end)

        # Per-turn scratchpad cleanup (mirrors base ``TurnManager``).
        if hasattr(self.state, "turn_data") and self.state.turn_data:
            self.state.turn_data.clear()

        # Advance ``current_player_index`` so the base-class turn-order
        # bookkeeping stays consistent with whoever leads next. (Lead is
        # rotated in ``_phase_curl_up`` via ``cats.end_round``; we mirror
        # the choice here for tools that read ``current_player_index``
        # directly.)
        if self.turn_order:
            next_lead = self._get_cats_field("lead_player", None)
            if isinstance(next_lead, str) and next_lead in self.turn_order:
                self.current_player_index = self.turn_order.index(next_lead)
            else:
                self.current_player_index = (
                    self.current_player_index + 1
                ) % len(self.turn_order)

        return events

    # ---------------------------------------------------------------------
    # Phase dispatcher
    # ---------------------------------------------------------------------
    async def _run_phase(self, phase_name: str) -> list[Event]:
        """Emit PHASE_START / PHASE_END around the per-phase handler.

        The handler is ``self._phase_<name>``. Unknown phases fall through
        to a no-op so misconfigured PHASES lists don't crash.
        """
        events: list[Event] = []
        events.extend(self._emit_phase(phase_name, "start"))

        handler = getattr(self, f"_phase_{phase_name}", None)
        if callable(handler):
            result = handler()
            # Phase methods are sync (no awaitable I/O in the six round
            # phases), but if a future override returns a coroutine we
            # transparently await it.
            if inspect.isawaitable(result):
                result = await result
            if result:
                events.extend(result)

        events.extend(self._emit_phase(phase_name, "end"))
        return events

    def _emit_phase(self, phase_name: str, kind: str) -> list[Event]:
        """Build & emit a PHASE_START or PHASE_END event for a cats phase.

        Payload phase string is prefixed with ``cats_`` (doc § 8: round-
        triggers distinguish on ``"cats_stretch"`` / ``"cats_curl_up"``).
        """
        ev_type = EventType.PHASE_START if kind == "start" else EventType.PHASE_END
        payload = {
            "phase": f"cats_{phase_name}",
            "player": self.lead_player_id,
            "cats_round": self._get_cats_field("round_number", 1),
        }
        ev = Event(type=ev_type, payload=payload)
        if self.pipeline is not None:
            self.pipeline.emit(ev)
        return [ev]

    # ---------------------------------------------------------------------
    # Phase 1: STRETCH (round-start)
    # ---------------------------------------------------------------------
    def _phase_stretch(self) -> list[Event]:
        """Round-start phase.

        Calls into Agent 1's ``begin_round`` to run round-start triggers
        (commander/trinket passive recomputation, untap-pile cards, etc.)
        and gives each player a chance to activate pile abilities at the
        top of the round.
        """
        events: list[Event] = []
        cats = _import_cats_module()
        if cats is not None and hasattr(cats, "begin_round"):
            try:
                round_events = cats.begin_round(self.state) or []
                for ev in round_events:
                    if self.pipeline is not None:
                        self.pipeline.emit(ev)
                    events.append(ev)
            except Exception:
                # If Agent 1's helper raises, swallow rather than break
                # the round loop. Reconciliation will surface the bug.
                pass

        # Doc § 4: cards untap at the start of each round. If Agent 1
        # didn't do it inside ``begin_round`` we do a defensive sweep
        # over the four pile zones.
        self._untap_pile_cards()

        # Top-of-round activation window. Each player gets a chance to
        # knock-over pile cards (doc § 4: "exhausted" cards activate
        # printed abilities). Easy/Medium AIs typically return [].
        player_ids = list(self.state.players.keys()) if self.state else []
        for pid in player_ids:
            events.extend(self._run_activation_window(pid))

        return events

    def _untap_pile_cards(self) -> None:
        """Untap every card sitting in any of the four scoring piles.

        Cats has no "tapped permanent" notion in the MTG sense, but cards
        in a pile can be "knocked over" (exhausted) to pay for activations
        (doc § 4). Knocked-over flag lives on ``obj.state.tapped`` by
        convention so existing interceptors work.
        """
        if self.state is None:
            return
        player_ids = list(self.state.players.keys())
        for pid in player_ids:
            for pile in (PILE_TERRITORY, PILE_NAP, PILE_SNACK, PILE_ATTENTION):
                zone = self.state.zones.get(f"{pile}_{pid}")
                if zone is None:
                    continue
                for obj_id in list(zone.objects):
                    obj = self.state.objects.get(obj_id)
                    if obj is not None and getattr(obj.state, "tapped", False):
                        obj.state.tapped = False

    def _run_activation_window(self, player_id: str) -> list[Event]:
        """Give ``player_id`` a chance to activate pile abilities.

        Asks the player's AI handler for a list of ``(card_id, ability_ix)``
        pairs and routes each through Agent 1's activation primitives if
        they exist, otherwise falls back to ``state.activated_ability``
        helpers if present.
        """
        events: list[Event] = []
        if self.state is None:
            return events

        choices = self._ask_ai(player_id, "activate_ability", {})
        if not choices:
            return events

        cats = _import_cats_module()
        for entry in choices:
            try:
                card_id, ability_ix = entry[0], entry[1]
            except (TypeError, IndexError):
                continue
            obj = self.state.objects.get(card_id) if isinstance(card_id, str) else None
            if obj is None:
                continue

            # Prefer Agent 1's pile-activation primitive if it exists.
            activated = False
            if cats is not None and hasattr(cats, "activate_pile_ability"):
                try:
                    out = cats.activate_pile_ability(
                        self.state, player_id, card_id, ability_ix
                    )
                    if out:
                        for ev in out:
                            if self.pipeline is not None:
                                self.pipeline.emit(ev)
                            events.append(ev)
                    activated = True
                except Exception:
                    activated = False

            if not activated:
                # Generic fallback: emit a CATS_PILE_ACTIVATE marker so
                # any registered interceptor that filters on it fires.
                ev_type = getattr(EventType, "CATS_PILE_ACTIVATE", None)
                if ev_type is not None:
                    ev = Event(
                        type=ev_type,
                        payload={
                            "player": player_id,
                            "card_id": card_id,
                            "ability_index": ability_ix,
                        },
                        source=card_id if isinstance(card_id, str) else None,
                    )
                    if self.pipeline is not None:
                        self.pipeline.emit(ev)
                    events.append(ev)

        return events

    # ---------------------------------------------------------------------
    # Phase 2: POUNCE  (non-lead plays first)
    # ---------------------------------------------------------------------
    def _phase_pounce(self) -> list[Event]:
        """Doc § 3: the *follower* (non-lead) commits first.

        Asks their AI for a card choice from hand and routes it through
        the trick manager.  Also installs the round's Category Rule based
        on the card's category (Sleek/Fluffy/Scrappy/Sneaky).
        """
        events: list[Event] = []
        if self.state is None:
            return events

        follower = self._other_player(self.lead_player_id)
        if follower is None:
            return events

        hand_ids = self._hand_card_ids(follower)
        if not hand_ids:
            # Empty hand — happens between deck-cycle refills. Skip the
            # pounce gracefully; resolve will see only one card and the
            # other side wins by walkover.
            return events

        chosen = self._ask_ai(follower, "choose_card", {"hand": hand_ids})
        chosen = self._unwrap_card_id(chosen, hand_ids)
        if chosen is None:
            return events

        # Hand off to Agent 1's play primitive if it exists. Otherwise
        # we route through the trick manager directly.
        cats = _import_cats_module()
        if cats is not None and hasattr(cats, "play_card_to_trick"):
            try:
                play_events = cats.play_card_to_trick(
                    self.state, follower, chosen, phase="pounce"
                ) or []
                for ev in play_events:
                    if self.pipeline is not None:
                        self.pipeline.emit(ev)
                    events.append(ev)
            except Exception:
                pass

        if self.trick_manager is not None:
            handler = getattr(self.trick_manager, "receive_pounce", None)
            if callable(handler):
                try:
                    extra = handler(follower, chosen) or []
                    if isinstance(extra, list):
                        for ev in extra:
                            if self.pipeline is not None:
                                self.pipeline.emit(ev)
                            events.append(ev)
                except Exception:
                    pass

        # Belt-and-braces category-rule install. ``play_card_to_trick``
        # and ``CatsTrickManager.receive_pounce`` both *may* install the
        # rule; calling here is idempotent if they did.
        if cats is not None and hasattr(cats, "install_category_rule"):
            try:
                played_obj = self.state.objects.get(chosen)
                if played_obj is not None:
                    cats.install_category_rule(self.state, played_obj)
            except Exception:
                pass

        # Emit a generic CATS_CARD_PLAYED marker if the EventType exists.
        ev_type = getattr(EventType, "CATS_CARD_PLAYED", None)
        if ev_type is not None:
            ev = Event(
                type=ev_type,
                payload={"player": follower, "card_id": chosen, "phase": "pounce"},
                source=chosen,
            )
            if self.pipeline is not None:
                self.pipeline.emit(ev)
            events.append(ev)

        return events

    # ---------------------------------------------------------------------
    # Phase 3: COUNTER-POUNCE  (lead plays second)
    # ---------------------------------------------------------------------
    def _phase_counter_pounce(self) -> list[Event]:
        """Doc § 3: the *lead* commits second, seeing the pounce."""
        events: list[Event] = []
        if self.state is None or self.lead_player_id is None:
            return events

        lead = self.lead_player_id
        hand_ids = self._hand_card_ids(lead)
        if not hand_ids:
            return events

        chosen = self._ask_ai(lead, "choose_card", {"hand": hand_ids})
        chosen = self._unwrap_card_id(chosen, hand_ids)
        if chosen is None:
            return events

        cats = _import_cats_module()
        if cats is not None and hasattr(cats, "play_card_to_trick"):
            try:
                play_events = cats.play_card_to_trick(
                    self.state, lead, chosen, phase="counter_pounce"
                ) or []
                for ev in play_events:
                    if self.pipeline is not None:
                        self.pipeline.emit(ev)
                    events.append(ev)
            except Exception:
                pass

        if self.trick_manager is not None:
            handler = getattr(self.trick_manager, "receive_counter_pounce", None)
            if callable(handler):
                try:
                    extra = handler(lead, chosen) or []
                    if isinstance(extra, list):
                        for ev in extra:
                            if self.pipeline is not None:
                                self.pipeline.emit(ev)
                            events.append(ev)
                except Exception:
                    pass

        # Doc § 7: a Mood played as Counter-pounce installs its rule
        # *before* the comparison. The trick manager may do this already;
        # we don't second-guess by re-installing here.

        ev_type = getattr(EventType, "CATS_CARD_PLAYED", None)
        if ev_type is not None:
            ev = Event(
                type=ev_type,
                payload={"player": lead, "card_id": chosen, "phase": "counter_pounce"},
                source=chosen,
            )
            if self.pipeline is not None:
                self.pipeline.emit(ev)
            events.append(ev)

        return events

    # ---------------------------------------------------------------------
    # Phase 4: RESOLVE
    # ---------------------------------------------------------------------
    def _phase_resolve(self) -> list[Event]:
        """Compare the two played cards under the installed rule.

        Delegates to ``CatsTrickManager.resolve()``. The trick manager
        owns the rule lookup (it queries ``CATS_TRICK_RULE_QUERY``) and
        sets the winner. We just relay its events and stash the winner
        on the cats state for the CLAIM phase to read.
        """
        events: list[Event] = []
        winner_id: Optional[str] = None

        if self.trick_manager is not None:
            handler = getattr(self.trick_manager, "resolve", None)
            if callable(handler):
                try:
                    out = handler()
                    # CatsTrickManager.resolve may return:
                    #   (a) winner_id: str
                    #   (b) (winner_id, [events])
                    #   (c) {"winner": ..., "events": [...]}
                    #   (d) [events] (winner stashed on state)
                    if isinstance(out, str):
                        winner_id = out
                    elif isinstance(out, tuple) and len(out) >= 1:
                        winner_id = out[0]
                        if len(out) >= 2 and isinstance(out[1], list):
                            for ev in out[1]:
                                if self.pipeline is not None:
                                    self.pipeline.emit(ev)
                                events.append(ev)
                    elif isinstance(out, dict):
                        winner_id = out.get("winner")
                        for ev in out.get("events", []) or []:
                            if self.pipeline is not None:
                                self.pipeline.emit(ev)
                            events.append(ev)
                    elif isinstance(out, list):
                        for ev in out:
                            if self.pipeline is not None:
                                self.pipeline.emit(ev)
                            events.append(ev)
                except Exception:
                    winner_id = None

        # Stash the winner on the cats state so CLAIM can read it. The
        # trick manager *may* already do this — that's fine, this is
        # idempotent.
        if winner_id is None:
            # Fallback: read winner from whatever the trick manager
            # stashed. ``state.cats.trick.winner`` (sub-namespace) or
            # ``state.cats_trick_winner`` (flat).
            current_trick = self._get_cats_field("current_trick", {}) or {}
            if isinstance(current_trick, dict):
                winner_id = current_trick.get("winner")
            if winner_id is None:
                winner_id = self._get_cats_field("trick_winner", None)

        if winner_id is not None:
            ct = self._get_cats_field("current_trick", {}) or {}
            if isinstance(ct, dict):
                ct = dict(ct)
                ct["winner"] = winner_id
                self._set_cats_field("current_trick", ct)
            self._set_cats_field("trick_winner", winner_id)

            # Emit CATS_TRICK_RESOLVE if Agent 1 added the EventType.
            ev_type = getattr(EventType, "CATS_TRICK_RESOLVE", None)
            if ev_type is not None:
                ev = Event(
                    type=ev_type,
                    payload={
                        "winner": winner_id,
                        "round": self._get_cats_field("round_number", 1),
                    },
                )
                if self.pipeline is not None:
                    self.pipeline.emit(ev)
                events.append(ev)

        return events

    # ---------------------------------------------------------------------
    # Phase 5: CLAIM  (winner picks a pile)
    # ---------------------------------------------------------------------
    def _phase_claim(self) -> list[Event]:
        """Doc § 3 phase 5: the trick winner picks a pile.

        The winning player's AI is asked which of their scoring piles
        should receive the trick's cards. ``cats.claim_pile`` is the
        authoritative dispatcher — it enforces Snack-force rules, pile
        caps, and overflow-to-attention.
        """
        events: list[Event] = []
        if self.state is None:
            return events

        winner = self._get_cats_field("trick_winner", None)
        if not winner:
            # Tie / no-card-played edge case. Reset and exit.
            if self.trick_manager is not None:
                reset = getattr(self.trick_manager, "reset", None)
                if callable(reset):
                    try:
                        reset()
                    except Exception:
                        pass
            self._set_cats_field("current_trick", {})
            return events

        # Collect the played cards so we can hand them to the AI prompt.
        current_trick = self._get_cats_field("current_trick", {}) or {}
        won_card_ids: list[str] = []
        if isinstance(current_trick, dict):
            for key in ("pounce", "counter_pounce", "cards", "played"):
                val = current_trick.get(key)
                if isinstance(val, list):
                    won_card_ids.extend(c for c in val if isinstance(c, str))
                elif isinstance(val, dict):
                    cid = val.get("card_id") or val.get("id")
                    if isinstance(cid, str):
                        won_card_ids.append(cid)
                elif isinstance(val, str):
                    won_card_ids.append(val)

        # Determine which piles are legal targets. Snack-force overrides
        # (handled inside cats.claim_pile) may collapse this to a single
        # option — we still pass the full menu so the AI sees the choice.
        available_piles = self._available_pile_names(winner, won_card_ids)

        chosen_pile = self._ask_ai(
            winner,
            "choose_pile",
            {"won_cards": won_card_ids, "piles": available_piles},
        )
        chosen_pile = self._unwrap_pile_name(chosen_pile, available_piles)
        if chosen_pile is None:
            chosen_pile = PILE_TERRITORY  # safest legal default per doc § 5.

        # Hand off to Agent 1's claim_pile primitive.
        cats = _import_cats_module()
        if cats is not None and hasattr(cats, "claim_pile"):
            try:
                claim_events = cats.claim_pile(
                    self.state, winner, chosen_pile
                ) or []
                for ev in claim_events:
                    if self.pipeline is not None:
                        self.pipeline.emit(ev)
                    events.append(ev)
            except Exception:
                # If claim_pile blows up, emit a generic marker so the
                # cards aren't silently lost. Reconciliation will fix.
                ev_type = getattr(EventType, "CATS_CLAIM_PILE", None)
                if ev_type is not None:
                    ev = Event(
                        type=ev_type,
                        payload={
                            "player": winner,
                            "pile": chosen_pile,
                            "cards": won_card_ids,
                        },
                    )
                    if self.pipeline is not None:
                        self.pipeline.emit(ev)
                    events.append(ev)

        # Reset the trick manager so the next round starts clean.
        if self.trick_manager is not None:
            reset = getattr(self.trick_manager, "reset", None)
            if callable(reset):
                try:
                    reset()
                except Exception:
                    pass

        # Clear the cats current_trick scratchpad. Round number is bumped
        # by end_round() in curl_up, not here.
        self._set_cats_field("current_trick", {})
        self._set_cats_field("trick_winner", None)
        self._set_cats_field("current_rule", None)

        return events

    # ---------------------------------------------------------------------
    # Phase 6: CURL UP  (round-end)
    # ---------------------------------------------------------------------
    def _phase_curl_up(self) -> list[Event]:
        """End-of-round phase.

        Delegates to ``cats.end_round`` which handles:
          * end-of-round triggers (doc § 8 round-time hooks);
          * hand refills when both hands are empty (doc § 11 Q2);
          * round_number increment;
          * lead rotation.

        If Agent 1 hasn't shipped ``end_round`` yet we do the minimum
        viable bookkeeping inline (increment + rotate) so the harness
        can still loop.
        """
        events: list[Event] = []
        if self.state is None:
            return events

        cats = _import_cats_module()
        handled = False
        if cats is not None and hasattr(cats, "end_round"):
            try:
                end_events = cats.end_round(self.state) or []
                for ev in end_events:
                    if self.pipeline is not None:
                        self.pipeline.emit(ev)
                    events.append(ev)
                handled = True
            except Exception:
                handled = False

        if not handled:
            # Fallback bookkeeping ----------------------------------------
            # Refill hands if both empty (doc § 2: "hands refresh from
            # the deck when both hands are empty").
            self._refill_hands_if_both_empty()
            # Bump round number.
            current = int(self._get_cats_field("round_number", 1) or 1)
            self._set_cats_field("round_number", current + 1)

        # Rotate the lead — *always* runs, since Agent 1's end_round may
        # only do the bookkeeping above. Doc § 3: lead alternates each
        # round so over 9 rounds each player leads 4 or 5 times.
        self._rotate_lead()

        return events

    def _rotate_lead(self) -> None:
        """Pick the next round's lead — the *other* player."""
        if self.state is None:
            return
        player_ids = list(self.state.players.keys())
        if len(player_ids) < 2:
            return
        current = self.lead_player_id or player_ids[0]
        if current not in player_ids:
            current = player_ids[0]
        idx = player_ids.index(current)
        next_lead = player_ids[(idx + 1) % len(player_ids)]
        self.lead_player_id = next_lead
        self._set_cats_field("lead_player", next_lead)

    def _refill_hands_if_both_empty(self) -> None:
        """If both players' hands are empty, draw a fresh hand for each.

        Fallback used when Agent 1's ``end_round`` hasn't landed. Reads
        ``CATS_HAND_SIZE`` from the cats module (default 5).
        """
        if self.state is None:
            return
        hand_size = int(_get_constant("CATS_HAND_SIZE", _DEFAULT_HAND_SIZE))
        player_ids = list(self.state.players.keys())
        empty = []
        for pid in player_ids:
            zone = self.state.zones.get(f"hand_{pid}")
            if zone is None or not zone.objects:
                empty.append(pid)
        if len(empty) != len(player_ids):
            return  # not all empty.

        # Both hands empty — refill from each player's deck. We emit DRAW
        # events through the pipeline so any interceptor on draw (e.g. a
        # commander that draws an extra card when refilling) fires.
        for pid in player_ids:
            ev = Event(
                type=EventType.DRAW,
                payload={"player": pid, "count": hand_size},
            )
            if self.pipeline is not None:
                self.pipeline.emit(ev)

    # ---------------------------------------------------------------------
    # AI handler dispatch
    # ---------------------------------------------------------------------
    def _ask_ai(
        self,
        player_id: str,
        decision_type: str,
        payload: dict,
    ) -> Any:
        """Route a decision request to the player's registered AI adapter.

        Three decision types supported (matching the contract documented
        at the top of this file):

          * ``"choose_card"``     -> handler.choose_card(state, hand_ids) -> str
          * ``"choose_pile"``     -> handler.choose_pile(state, won_ids, pile_names) -> str
          * ``"activate_ability"``-> handler.choose_activations(state) -> list[tuple[str,int]]

        If no handler is registered (shouldn't happen in normal play),
        falls back to a random legal pick so the round still progresses.
        Defensive against AI returns that wrap the result in a dataclass —
        ``_unwrap_*`` helpers downstream peel off common attribute names.
        """
        handler = self.cats_ai_handlers.get(player_id)

        if decision_type == "choose_card":
            hand_ids = payload.get("hand", []) or []
            if handler is not None:
                method = getattr(handler, "choose_card", None)
                if callable(method):
                    try:
                        result = method(self.state, hand_ids)
                        return result
                    except Exception:
                        pass
            # Fallback: random.
            if hand_ids:
                rng = self._get_rng()
                return rng.choice(hand_ids)
            return None

        if decision_type == "choose_pile":
            won_cards = payload.get("won_cards", []) or []
            piles = payload.get("piles", []) or []
            if handler is not None:
                method = getattr(handler, "choose_pile", None)
                if callable(method):
                    try:
                        result = method(self.state, won_cards, piles)
                        return result
                    except Exception:
                        pass
            # Fallback: pick the first available pile (deterministic).
            return piles[0] if piles else None

        if decision_type == "activate_ability":
            if handler is not None:
                method = getattr(handler, "choose_activations", None)
                if callable(method):
                    try:
                        result = method(self.state)
                        if isinstance(result, list):
                            return result
                        # Unwrap from a dataclass-like wrapper.
                        if hasattr(result, "activations"):
                            return list(result.activations)  # type: ignore[arg-type]
                        return []
                    except Exception:
                        return []
            return []

        return None

    # ---------------------------------------------------------------------
    # Defensive unwrap helpers — AI may return a dataclass instead of str.
    # ---------------------------------------------------------------------
    @staticmethod
    def _unwrap_card_id(result: Any, hand_ids: list[str]) -> Optional[str]:
        if isinstance(result, str):
            return result if result in hand_ids else (
                # Some AIs return a card by *name*; if so, refuse and
                # fall back to the first legal hand id.
                hand_ids[0] if hand_ids else None
            )
        if result is None:
            return hand_ids[0] if hand_ids else None
        # Dataclass-like wrappers — drift point flagged by the brief.
        for attr in ("card_id", "card", "id", "obj_id", "object_id"):
            val = getattr(result, attr, None)
            if isinstance(val, str):
                if val in hand_ids:
                    return val
                return hand_ids[0] if hand_ids else None
        # Tuple form ("CHOOSE_CARD", card_id, ...).
        if isinstance(result, (list, tuple)) and result:
            for elt in result:
                if isinstance(elt, str) and elt in hand_ids:
                    return elt
        return hand_ids[0] if hand_ids else None

    @staticmethod
    def _unwrap_pile_name(result: Any, available: list[str]) -> Optional[str]:
        if isinstance(result, str):
            if result in available:
                return result
            # Allow "territory" / "nap" / "snack" / "attention" shorthand.
            short_map = {
                "territory": PILE_TERRITORY,
                "nap": PILE_NAP,
                "snack": PILE_SNACK,
                "attention": PILE_ATTENTION,
            }
            mapped = short_map.get(result.lower())
            if mapped in available:
                return mapped
            return available[0] if available else None
        if result is None:
            return available[0] if available else None
        # Dataclass-like wrappers.
        for attr in ("pile", "pile_name", "name", "target"):
            val = getattr(result, attr, None)
            if isinstance(val, str):
                if val in available:
                    return val
                short_map = {
                    "territory": PILE_TERRITORY,
                    "nap": PILE_NAP,
                    "snack": PILE_SNACK,
                    "attention": PILE_ATTENTION,
                }
                mapped = short_map.get(val.lower())
                if mapped in available:
                    return mapped
        return available[0] if available else None

    # ---------------------------------------------------------------------
    # Misc helpers
    # ---------------------------------------------------------------------
    def _hand_card_ids(self, player_id: str) -> list[str]:
        """Return the list of object ids in ``player_id``'s hand zone."""
        if self.state is None:
            return []
        zone = self.state.zones.get(f"hand_{player_id}")
        if zone is None:
            return []
        return list(zone.objects)

    def _available_pile_names(
        self,
        player_id: str,
        won_card_ids: list[str],
    ) -> list[str]:
        """Return the scoring-pile names ``player_id`` may legally choose.

        Reads pile caps from Agent 1's cats module if it exposes them,
        otherwise from the per-engine defaults. Snack-force overrides
        (which collapse the choice) live inside ``cats.claim_pile`` —
        we still surface the full menu to the AI; ``claim_pile`` is the
        gatekeeper.
        """
        if self.state is None:
            return [PILE_TERRITORY, PILE_NAP, PILE_SNACK]

        caps = _get_constant("CATS_PILE_CAPS", _DEFAULT_PILE_CAPS) or _DEFAULT_PILE_CAPS

        available: list[str] = []
        for pile_name in (PILE_TERRITORY, PILE_NAP, PILE_SNACK):
            zone = self.state.zones.get(f"{pile_name}_{player_id}")
            current = len(zone.objects) if zone is not None else 0
            cap = int(caps.get(pile_name, _DEFAULT_PILE_CAPS[pile_name]))
            # The trick contributes len(won_card_ids) more cards; if the
            # pile can't hold them, omit from the menu (doc § 5: overflow
            # goes to attention).
            if current + len(won_card_ids) <= cap:
                available.append(pile_name)

        # Attention is always available as a fallback (doc § 5: pile_attention has unlimited cap).
        if not available:
            available.append(PILE_ATTENTION)

        return available

    def _other_player(self, player_id: Optional[str]) -> Optional[str]:
        """Return the *other* player's id (binary opponent lookup)."""
        if self.state is None or player_id is None:
            return None
        for pid in self.state.players:
            if pid != player_id:
                return pid
        return None

    def _get_rng(self) -> random.Random:
        """Reuse the state's deterministic RNG if seeded, else fresh."""
        if self.state is None:
            return random.Random()
        rng = getattr(self.state, "_rng", None)
        if isinstance(rng, random.Random):
            return rng
        seed = getattr(self.state, "rng_seed", None)
        if seed is not None:
            rng = random.Random(seed)
            try:
                self.state._rng = rng  # type: ignore[attr-defined]
            except Exception:
                pass
            return rng
        return random.Random()

    # ---------------------------------------------------------------------
    # Game-over plumbing
    # ---------------------------------------------------------------------
    def _is_game_over(self) -> bool:
        """Fast check used during ``run_turn`` to break out of the phase
        loop. Mirrors the helper used by the other engines.
        """
        if self.state is None:
            return True
        if self._get_cats_field("game_over", False):
            return True
        # Player-has-lost SBA parity.
        alive = [p for p in self.state.players.values() if not p.has_lost]
        return len(alive) <= 1

    def _game_over_check(self) -> bool:
        """Authoritative end-of-round game-over check.

        Prefers ``cats.check_game_over(state)`` if Agent 1 shipped it;
        otherwise applies the doc § 2 condition: round_number > total AND
        all hands empty.
        """
        if self.state is None:
            return False
        if self._get_cats_field("game_over", False):
            return True

        cats = _import_cats_module()
        if cats is not None and hasattr(cats, "check_game_over"):
            try:
                return bool(cats.check_game_over(self.state))
            except Exception:
                pass

        # Fallback: doc-spec condition.
        total_rounds = int(_get_constant("CATS_TOTAL_ROUNDS", _DEFAULT_TOTAL_ROUNDS))
        current_round = int(self._get_cats_field("round_number", 1) or 1)
        if current_round <= total_rounds:
            return False
        # All hands empty?
        for pid in self.state.players:
            zone = self.state.zones.get(f"hand_{pid}")
            if zone is not None and zone.objects:
                return False
        return True

    # ---------------------------------------------------------------------
    # MTG-compat no-op overrides
    # ---------------------------------------------------------------------
    # The base ``TurnManager`` exposes MTG-flavoured phase helpers. Cats
    # never calls them but ``Game._connect_subsystems`` (and some replay
    # tools) may invoke them by reflection. Override to no-op for safety.
    # ---------------------------------------------------------------------
    async def _run_beginning_phase(self) -> list[Event]:
        return []

    async def _run_main_phase(self, *_args, **_kwargs) -> list[Event]:
        return []

    async def _run_combat_phase(self) -> list[Event]:
        return []

    async def _run_ending_phase(self) -> list[Event]:
        return []
