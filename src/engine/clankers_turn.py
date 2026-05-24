"""
Clankers Turn Manager
=====================

Drives the six-phase Clankers turn loop. Clankers is asymmetric per turn
(only the active player executes most phases; the opponent gets interrupt
windows via REACT-priority interceptors on combat / attach events).

Phase order (mirrors ``docs/games/clankers.md`` § 2):

    1. BOOT        — Untap active player's exhausted parts. Refresh compute:
                     ``compute = min(compute_cap, COMPUTE_POOL_BASE +
                     turn_number)``. Emit CLANKERS_TURN_START. Upkeep
                     triggers fire (via interceptor flow).
    2. ALLOCATE    — Once-per-turn hand refill. Emit CLANKERS_HAND_REFILL_QUERY.
                     The AI's ``choose_refill`` returns True/False (refusing
                     the refill is sometimes correct to slow deck-out). Then
                     check if the death-clock should activate (both libraries
                     empty).
    3. ASSEMBLE    — Active player loops: ask AI for an action, dispatch via
                     ``clankers.play_card_from_hand`` (or ``attach_part`` for
                     a floor-to-chassis attach). Capped at 100 actions/phase.
    4. COMBAT      — Delegate to ``ClankersCombatManager.resolve_combat_phase``.
                     SKIPPED on player 1's turn 1 (one-sided combat opening
                     is too lopsided under always-7 economy).
    5. REASSEMBLE  — A second Assemble window (post-combat main).
    6. CLEANUP     — End-of-turn triggers. ``clankers_refill_used`` cleared.
                     **Damage on chassis persists** (Clankers rule — override
                     the base TurnManager's MTG cleanup). Emit
                     CLANKERS_TURN_END. Swap active player.

After each phase the turn manager calls ``clankers.check_workshop_breached``
as a catch-all for non-combat sources of damage (Transients, structures,
death-clock ticks). The combat manager owns the inline check during combat.

This file lives behind the same TurnManager protocol as
``minecraft_turn.py``, ``hearthstone_turn.py``, ``depths_turn.py``, and
``cats_turn.py``. Peer-module imports (``src.engine.clankers``,
``src.engine.clankers_combat``) are deferred so this file can be imported
while Agents 1 and 2 are still in flight.

CONTRACT (see ``docs/games/clankers_contract.md``):
- Class name ``ClankersTurnManager`` extends ``TurnManager``.
- ``run_turn(player_id)`` returns ``list[Event]``.
- Phase helpers are private (``_phase_*``) and each returns ``list[Event]``.
- Constructor takes ``state`` — matches the mode-adapter factory convention
  used by every peer engine (cats / depths / minecraft / hearthstone).
  The Game reference is reachable via ``state._game`` after
  ``Game._connect_subsystems`` runs.

AI handler contract (Agent 4 implements ``ClankersAIAdapter``):

    handler.choose_refill(state, player_id) -> bool
    handler.choose_assemble_action(state, player_id) -> Optional[dict]
    handler.choose_attackers(state, player_id) -> list[str]
    handler.choose_blockers(state, player_id, attackers) -> dict[str, str]
    handler.choose_target(state, source_id, candidates, requirement) -> Optional[str]
    handler.mulligan_decision(state, player_id, num_kept) -> bool
"""

from __future__ import annotations

import random
from typing import Any, Optional, TYPE_CHECKING

from .turn import TurnManager
from .types import (
    CardDefinition,
    Event,
    EventType,
    GameObject,
    GameState,
    Zone,
    ZoneType,
)

if TYPE_CHECKING:  # pragma: no cover - type-only imports
    from .pipeline import EventPipeline
    from .game import Game


# =============================================================================
# Defaults — used until Agent 1's clankers module lands
# =============================================================================

# Fallback constants in case Agent 1's clankers module isn't importable yet.
# At runtime we re-read these from ``src.engine.clankers`` so any tuning
# changes there take precedence.
_DEFAULT_HAND_FLOOR = 7
_DEFAULT_COMPUTE_POOL_BASE = 3
_DEFAULT_COMPUTE_CAP = 10
_DEFAULT_SCRAP_CAP = 10
_DEFAULT_WORKSHOP_INTEGRITY = 25
_DEFAULT_MAX_STRUCTURES = 3
_DEFAULT_DEATHCLOCK_BASE = 2

# Safety cap on the inner Assemble / Reassemble action loop. Far above any
# legitimate turn (a typical turn plays 3-5 actions), but guards against a
# misbehaving AI that never returns ``pass``.
_ASSEMBLE_ACTION_CAP = 100


# =============================================================================
# Peer-module imports
# =============================================================================

from . import clankers as _clankers_module  # noqa: E402  (after top-of-file types)


def _import_clankers_module():
    """Return the clankers engine module — unconditional now that all
    Stage-1 modules exist."""
    return _clankers_module


def _get_constant(name: str, default: Any) -> Any:
    """Look up a constant on the clankers engine module with a typed fallback."""
    return getattr(_clankers_module, name, default)


# =============================================================================
# ClankersTurnManager
# =============================================================================

class ClankersTurnManager(TurnManager):
    """Turn manager for the Clankers engine.

    Drives the six-phase turn loop:

        BOOT -> ALLOCATE -> ASSEMBLE -> COMBAT -> REASSEMBLE -> CLEANUP

    Calls into ``ClankersCombatManager`` for combat resolution and the
    per-player ``ClankersAIAdapter`` instances for in-turn decisions.

    Public surface mirrors the other engine turn managers
    (``HearthstoneTurnManager``, ``MinecraftTurnManager``,
    ``DepthsTurnManager``, ``CatsTurnManager``).
    """

    PHASES: list[str] = [
        "boot",
        "allocate",
        "assemble",
        "combat",
        "reassemble",
        "cleanup",
    ]

    # ---------------------------------------------------------------------
    # Construction & accessors
    # ---------------------------------------------------------------------
    def __init__(self, state: GameState):
        """Construct from a ``GameState`` — matches the mode-adapter factory
        convention used by every peer engine.

        The Game back-reference is reachable via ``state._game`` once
        ``Game._connect_subsystems`` has wired it. Tests that build the turn
        manager without a Game may set ``state._game`` themselves before
        invoking any phase that needs an AI handler.
        """
        super().__init__(state)

        # Combat manager — instantiated lazily in setup_game so we can read
        # ``state._game`` after Game.__init__ finishes wiring subsystems.
        self.combat_manager = None

        # AI handler registry (per-player). The shared fallback exists for
        # single-handler test wiring; production setups should populate the
        # per-player dict.
        self.clankers_ai_handlers: dict[str, Any] = {}
        self.clankers_ai_handler: Any = None
        self.ai_players: set[str] = set()
        self.human_action_handler = None  # async (player_id, state) -> action dict

    @property
    def _emit_pipeline(self):
        """Return ``self.pipeline`` or the lazily-attached one on state.

        ``Game._connect_subsystems`` wires ``self.pipeline`` after the
        turn manager is constructed. Tests that build the turn manager
        outside ``Game`` still have the pipeline reachable via
        ``state._pipeline``.
        """
        if self.pipeline is not None:
            return self.pipeline
        return getattr(self.state, "_pipeline", None)

    # ---------------------------------------------------------------------
    # AI handler registration
    # ---------------------------------------------------------------------
    def set_ai_handler(self, handler, player_id: Optional[str] = None) -> None:
        """Install an AI handler.

        With ``player_id=None`` the handler becomes the shared fallback
        for any AI player without a per-player override. With ``player_id``
        it's installed for that player only.
        """
        if player_id is None:
            self.clankers_ai_handler = handler
            return
        if handler is None:
            self.clankers_ai_handlers.pop(player_id, None)
        else:
            self.clankers_ai_handlers[player_id] = handler

    def set_ai_player(self, player_id: str) -> None:
        """Mark a player as AI-controlled."""
        self.ai_players.add(player_id)

    def _is_ai_player(self, player_id: Optional[str]) -> bool:
        return bool(player_id and player_id in self.ai_players)

    def _ai_handler_for(self, player_id: str) -> Any:
        """Resolve the AI handler for ``player_id``.

        Preference order (matches contract §6):
          1. Per-player override registered via
             ``set_ai_handler(h, player_id)`` on this turn manager.
          2. Per-player entry on ``game.clankers_ai_handlers[player_id]``.
          3. Shared handler on ``self.clankers_ai_handler``.
          4. Shared handler on ``game.clankers_ai_handler``.
        """
        handler = self.clankers_ai_handlers.get(player_id)
        if handler is not None:
            return handler

        game = getattr(self.state, "_game", None)
        if game is not None:
            game_map = getattr(game, "clankers_ai_handlers", None)
            if isinstance(game_map, dict):
                handler = game_map.get(player_id)
                if handler is not None:
                    return handler

        if self.clankers_ai_handler is not None:
            return self.clankers_ai_handler
        if game is not None:
            return getattr(game, "clankers_ai_handler", None)
        return None

    # ---------------------------------------------------------------------
    # Setup
    # ---------------------------------------------------------------------
    def setup_game(
        self,
        deck_a: list[CardDefinition],
        core_a: CardDefinition,
        deck_b: list[CardDefinition],
        core_b: CardDefinition,
    ) -> list[Event]:
        """Initialise both players, libraries, opening hands, Cores, and
        the death-clock / containment-failure scaffolding.

        Returns the list of bookkeeping events emitted during setup
        (``GAME_START`` + opening-hand ``DRAW`` events for tooling).
        """
        events: list[Event] = []
        if self.state is None:
            return events

        player_ids = list(self.state.players.keys())
        if len(player_ids) < 2:
            raise RuntimeError(
                f"ClankersTurnManager.setup_game requires 2 players, "
                f"got {len(player_ids)}."
            )
        p1_id, p2_id = player_ids[0], player_ids[1]
        decks = {p1_id: list(deck_a), p2_id: list(deck_b)}
        cores = {p1_id: core_a, p2_id: core_b}

        # Instantiate the combat manager. Per contract §2, ClankersCombatManager
        # takes a ``game``; if no Game is wired we pass ``self`` (the turn
        # manager) — it exposes ``.state`` and the AI-handler dicts the
        # combat manager needs.
        if self.combat_manager is None:
            from .clankers_combat import ClankersCombatManager
            game_or_tm = getattr(self.state, "_game", None) or self
            self.combat_manager = ClankersCombatManager(game_or_tm)

        # Initialise state.clankers_* fields. Done before per-player setup
        # so card setup_interceptors can read live dicts.
        hand_floor = int(_get_constant("CLANKERS_HAND_FLOOR", _DEFAULT_HAND_FLOOR))
        compute_pool_base = int(_get_constant(
            "CLANKERS_COMPUTE_POOL_BASE", _DEFAULT_COMPUTE_POOL_BASE
        ))
        compute_cap = int(_get_constant(
            "CLANKERS_COMPUTE_CAP", _DEFAULT_COMPUTE_CAP
        ))
        workshop_integrity = int(_get_constant(
            "CLANKERS_STARTING_WORKSHOP_INTEGRITY", _DEFAULT_WORKSHOP_INTEGRITY
        ))

        self._init_clankers_state(
            player_ids,
            compute_pool_base=compute_pool_base,
            compute_cap=compute_cap,
            workshop_integrity=workshop_integrity,
        )

        # Per-player setup via the engine module.
        for pid in player_ids:
            try:
                out = _clankers_module.setup_clankers_player(
                    self.state, pid, decks[pid], cores[pid]
                )
                if isinstance(out, list):
                    for ev in out:
                        self._emit(ev)
                        events.append(ev)
            except Exception:
                # If the engine helper crashes, fall back inline so we still
                # have a runnable state for the smoke test.
                events.extend(self._inline_setup_player(
                    pid, decks[pid], cores[pid], hand_floor=hand_floor,
                ))

        # Decide first player. Deterministic when ``state.rng_seed`` is set.
        rng = self._get_rng()
        if getattr(self.state, "rng_seed", None) is not None:
            # Deterministic — use the first-listed player for reproducibility.
            first_id = p1_id
        else:
            first_id = p1_id if rng.random() < 0.5 else p2_id
        second_id = p2_id if first_id == p1_id else p1_id

        # Per contract §4: combat is skipped on the first player's first turn
        # only. clankers_first_turn alone isn't enough — after the active
        # player swaps mid-turn we'd need to know whether THIS player is the
        # one whose combat is being skipped. clankers_first_player tracks
        # that explicitly.
        self.state.clankers_first_turn = True  # type: ignore[attr-defined]
        self.state.clankers_first_player = first_id  # type: ignore[attr-defined]

        self.set_turn_order([first_id, second_id])
        self.state.active_player = first_id
        if self.turn_state is not None:
            self.turn_state.active_player_id = first_id
            self.turn_state.turn_number = 0
        self.state.turn_number = 0
        self.state.game_mode = "clankers"

        # Emit GAME_START so downstream tooling sees a game boundary.
        game_start = Event(
            type=EventType.GAME_START,
            payload={
                "players": list(self.turn_order),
                "first_player": first_id,
                "mode": "clankers",
            },
        )
        self._emit(game_start)
        events.append(game_start)

        return events

    def _init_clankers_state(
        self,
        player_ids: list[str],
        *,
        compute_pool_base: int,
        compute_cap: int,
        workshop_integrity: int,
    ) -> None:
        """Initialise every ``state.clankers_*`` field declared in contract §4.

        Uses ``setattr`` so the GameState dataclass stays unchanged (cats
        / scp / depths pattern).
        """
        s = self.state
        s.clankers_workshop_integrity = {pid: workshop_integrity for pid in player_ids}  # type: ignore[attr-defined]
        s.clankers_compute_pool = {pid: 0 for pid in player_ids}  # type: ignore[attr-defined]
        s.clankers_compute_cap = {pid: compute_cap for pid in player_ids}  # type: ignore[attr-defined]
        s.clankers_scrap_pool = {pid: 0 for pid in player_ids}  # type: ignore[attr-defined]
        s.clankers_refill_used = {pid: False for pid in player_ids}  # type: ignore[attr-defined]
        s.clankers_cores = {}  # type: ignore[attr-defined]  # populated by _inline_setup_player / Agent 1
        s.clankers_containment_failure = False  # type: ignore[attr-defined]
        s.clankers_containment_turn = 0  # type: ignore[attr-defined]
        s.clankers_structures = {pid: [] for pid in player_ids}  # type: ignore[attr-defined]
        s.clankers_assemblies = {pid: [] for pid in player_ids}  # type: ignore[attr-defined]
        s.clankers_loser: Optional[str] = None  # type: ignore[attr-defined]
        # _first_player is set by setup_game itself.

    def _inline_setup_player(
        self,
        player_id: str,
        deck: list[CardDefinition],
        core_card_def: CardDefinition,
        *,
        hand_floor: int,
    ) -> list[Event]:
        """Inline fallback for ``clankers.setup_clankers_player``.

        Used when Agent 1's module hasn't shipped yet (or its helper crashed).
        Creates GameObjects for every deck card in LIBRARY, shuffles, deals
        the opening hand, creates the Core in COMMAND, and registers the
        Core passive if defined.
        """
        events: list[Event] = []
        s = self.state
        if s is None:
            return events
        game = getattr(s, "_game", None)

        # Ensure per-player zones exist. All Clankers zones are per-player
        # (per setup_clankers_player in clankers.py); none use the
        # MTG-style shared layout.
        self._ensure_zone(f"library_{player_id}", ZoneType.LIBRARY, owner=player_id)
        self._ensure_zone(f"hand_{player_id}", ZoneType.HAND, owner=player_id)
        self._ensure_zone(
            f"clankers_scrap_heap_{player_id}",
            ZoneType.CLANKERS_SCRAP_HEAP,
            owner=player_id,
        )
        self._ensure_zone(
            f"clankers_assembly_floor_{player_id}",
            ZoneType.CLANKERS_ASSEMBLY_FLOOR,
            owner=player_id,
        )
        self._ensure_zone(f"command_{player_id}", ZoneType.COMMAND, owner=player_id)

        # Build deck GameObjects in LIBRARY.
        for card_def in deck:
            self._create_card_object(card_def, player_id, ZoneType.LIBRARY)

        # Shuffle.
        rng = self._get_rng()
        lib = self.state.zones.get(f"library_{player_id}")
        if lib is not None and lib.objects:
            rng.shuffle(lib.objects)

        # Draw opening hand.
        draws = self._move_top_n_to_hand(player_id, hand_floor)
        if draws > 0:
            draw_event = Event(
                type=EventType.DRAW,
                payload={"player": player_id, "count": draws, "reason": "opening_hand"},
            )
            self._emit(draw_event)
            events.append(draw_event)

        # Create the Core in COMMAND zone.
        core_obj = self._create_card_object(core_card_def, player_id, ZoneType.COMMAND)
        if core_obj is not None:
            self.state.clankers_cores[player_id] = core_obj.id  # type: ignore[attr-defined]
            # Register the Core's passive if defined.
            passive_setup = getattr(core_card_def, "clankers_core_passive_setup", None)
            if callable(passive_setup):
                try:
                    interceptors = passive_setup(core_obj, self.state) or []
                    for interceptor in interceptors:
                        self._register_interceptor(interceptor, core_obj)
                except Exception:
                    # If a Core passive crashes setup, leave it un-registered.
                    pass

        return events

    def _ensure_zone(self, key: str, zone_type: ZoneType, owner: Optional[str]) -> None:
        """Create a zone if it doesn't exist."""
        if key not in self.state.zones:
            self.state.zones[key] = Zone(type=zone_type, owner=owner)

    def _create_card_object(
        self,
        card_def: CardDefinition,
        owner_id: str,
        zone_type: ZoneType,
    ) -> Optional[GameObject]:
        """Create a GameObject from a CardDefinition.

        Prefers ``game.create_object`` (which handles setup_interceptors,
        timestamps, and the zone-key lookup table). Falls back to a
        manual GameObject build if Game isn't available.
        """
        game = getattr(self.state, "_game", None)
        if game is not None and hasattr(game, "create_object"):
            import copy
            return game.create_object(
                name=card_def.name,
                owner_id=owner_id,
                zone=zone_type,
                characteristics=copy.deepcopy(card_def.characteristics),
                card_def=card_def,
            )

        # Fallback: build the GameObject inline. This won't run
        # setup_interceptors but at least the smoke harness can construct
        # state.
        import copy
        from .types import new_id, ObjectState, Characteristics
        obj_id = new_id()
        obj = GameObject(
            id=obj_id,
            name=card_def.name,
            owner=owner_id,
            controller=owner_id,
            zone=zone_type,
            characteristics=copy.deepcopy(card_def.characteristics or Characteristics()),
            state=ObjectState(),
            card_def=card_def,
            created_at=self.state.next_timestamp(),
            entered_zone_at=self.state.timestamp,
            _state_ref=self.state,
        )
        self.state.objects[obj_id] = obj

        zone_key = self._resolve_zone_key(zone_type, owner_id)
        if zone_key and zone_key in self.state.zones:
            self.state.zones[zone_key].objects.append(obj_id)
        return obj

    @staticmethod
    def _resolve_zone_key(zone_type: ZoneType, owner_id: str) -> Optional[str]:
        """Build the zone-key for a (zone_type, owner) pair.

        Clankers uses per-player zones for everything (LIBRARY, HAND, COMMAND,
        CLANKERS_SCRAP_HEAP, CLANKERS_ASSEMBLY_FLOOR) — see
        ``setup_clankers_player`` in clankers.py. The legacy MTG-shared zones
        (BATTLEFIELD/STACK/EXILE) are not used.
        """
        per_player = {
            ZoneType.LIBRARY,
            ZoneType.HAND,
            ZoneType.GRAVEYARD,
            ZoneType.COMMAND,
        }
        scrap = getattr(ZoneType, "CLANKERS_SCRAP_HEAP", None)
        if scrap is not None:
            per_player.add(scrap)
        floor = getattr(ZoneType, "CLANKERS_ASSEMBLY_FLOOR", None)
        if floor is not None:
            per_player.add(floor)
        if zone_type in per_player:
            return f"{zone_type.name.lower()}_{owner_id}"
        # MTG-shared zones (rarely used by clankers) keep the canonical key.
        return zone_type.name.lower()

    def _register_interceptor(self, interceptor, source_obj: GameObject) -> None:
        """Register an interceptor — prefers game.register_interceptor."""
        game = getattr(self.state, "_game", None)
        if game is not None and hasattr(game, "register_interceptor"):
            game.register_interceptor(interceptor, source_obj)
            return
        # Fallback: stash on state.interceptors directly.
        interceptor.timestamp = self.state.next_timestamp()
        self.state.interceptors[interceptor.id] = interceptor
        source_obj.interceptor_ids.append(interceptor.id)

    def _move_top_n_to_hand(self, player_id: str, n: int) -> int:
        """Move up to ``n`` cards from library top to hand. Returns the
        actual count moved (clamped by library size).

        Convention: ``library.objects[0]`` is the top of the deck (popped
        first), matching ``clankers._draw_one``.
        """
        library = self._zone_lookup(ZoneType.LIBRARY, player_id)
        hand = self._zone_lookup(ZoneType.HAND, player_id)
        if library is None or hand is None:
            return 0
        moved = 0
        for _ in range(n):
            if not library.objects:
                break
            obj_id = library.objects.pop(0)
            hand.objects.append(obj_id)
            obj = self.state.objects.get(obj_id)
            if obj is not None:
                obj.zone = ZoneType.HAND
                obj.entered_zone_at = self.state.timestamp
            moved += 1
        return moved

    # ---------------------------------------------------------------------
    # Turn driver — one full TURN.
    # ---------------------------------------------------------------------
    def run_turn(self, player_id: str) -> list[Event]:
        """Run one complete Clankers turn for ``player_id``.

        Phase order: BOOT → ALLOCATE → ASSEMBLE → COMBAT → REASSEMBLE → CLEANUP.
        Returns all events emitted.

        Aborts early (returning whatever events have accumulated) if the
        workshop is breached or the game otherwise ends mid-turn.
        """
        events: list[Event] = []
        if self.state is None:
            return events

        # Sync active player + bump turn counter.
        if player_id and player_id in self.turn_order:
            self.current_player_index = self.turn_order.index(player_id)
        active = player_id or (
            self.turn_order[self.current_player_index] if self.turn_order else None
        )
        if active is None:
            return events
        self.state.active_player = active
        if self.turn_state is not None:
            self.turn_state.active_player_id = active

        # Run the six phases. Each helper emits its own PHASE_START /
        # PHASE_END plus its phase-specific events.
        events.extend(self._phase_boot(active))
        if self._is_game_over():
            return events

        events.extend(self._phase_allocate(active))
        if self._is_game_over():
            return events

        events.extend(self._phase_assemble(active))
        if self._is_game_over():
            return events

        # Combat-skip rule: player 1 skips combat on the very first turn
        # of the game (doc § 2: "Player 1 skips Combat on their first turn").
        first_player_id = getattr(self.state, "clankers_first_player", None)
        first_turn_flag = bool(getattr(self.state, "clankers_first_turn", False))
        is_p1_first_turn = (
            first_turn_flag
            and active == first_player_id
            and self.turn_state is not None
            and self.turn_state.turn_number == 1
        )
        if not is_p1_first_turn:
            events.extend(self._phase_combat(active))
            if self._is_game_over():
                return events

        events.extend(self._phase_reassemble(active))
        if self._is_game_over():
            return events

        events.extend(self._phase_cleanup(active))
        return events

    # ---------------------------------------------------------------------
    # Helpers — common to all phases
    # ---------------------------------------------------------------------
    def _emit(self, event: Event) -> None:
        """Emit an event through whichever pipeline is currently wired."""
        pipeline = self._emit_pipeline
        if pipeline is not None:
            try:
                pipeline.emit(event)
            except Exception:
                # Don't let a buggy interceptor crash the turn loop.
                # The event is still recorded on the returned events list
                # by the caller for reproducibility.
                pass

    def _emit_phase_event(self, phase_name: str, kind: str, player_id: str) -> Event:
        """Build & emit a PHASE_START or PHASE_END event."""
        ev_type = EventType.PHASE_START if kind == "start" else EventType.PHASE_END
        ev = Event(
            type=ev_type,
            payload={
                "phase": phase_name,
                "player": player_id,
                "turn_number": self.turn_state.turn_number if self.turn_state else 0,
            },
        )
        self._emit(ev)
        return ev

    def _check_workshop_breached(self) -> list[Event]:
        """Run the after-phase workshop-integrity check.

        Returns the events emitted if a player has lost. The combat manager
        emits these inline during combat damage; this helper is the
        catch-all for Transients, Structures, deathclock ticks, and other
        non-combat sources.
        """
        events: list[Event] = []
        clankers = _import_clankers_module()
        loser: Optional[str] = None

        if clankers is not None and hasattr(clankers, "check_workshop_breached"):
            try:
                loser = clankers.check_workshop_breached(self.state)
            except Exception:
                loser = None
        if loser is None:
            # Fallback: read the workshop_integrity dict ourselves.
            integrity = getattr(self.state, "clankers_workshop_integrity", {}) or {}
            for pid, hp in integrity.items():
                if hp <= 0:
                    loser = pid
                    break

        if loser is None:
            return events

        # Mark loser and emit canonical death markers. Also flips
        # ``state.game_over = True`` (cats pattern).
        self.state.clankers_loser = loser  # type: ignore[attr-defined]
        self.state.game_over = True  # type: ignore[attr-defined]

        loser_player = self.state.players.get(loser) if self.state.players else None
        if loser_player is not None:
            loser_player.has_lost = True

        breach = Event(
            type=EventType.CLANKERS_WORKSHOP_BREACHED,
            payload={"player_id": loser, "reason": "workshop_integrity_zero"},
        )
        self._emit(breach)
        events.append(breach)

        lose_event = Event(
            type=EventType.PLAYER_LOSES,
            payload={"player": loser, "reason": "workshop_integrity_zero"},
        )
        self._emit(lose_event)
        events.append(lose_event)

        # Emit a corresponding PLAYER_WINS for the survivor(s).
        for pid in self.state.players:
            if pid == loser:
                continue
            survivor = self.state.players[pid]
            if not survivor.has_lost:
                survivor.has_won = True
                win_event = Event(
                    type=EventType.PLAYER_WINS,
                    payload={"player": pid, "reason": "opponent_workshop_breached"},
                )
                self._emit(win_event)
                events.append(win_event)

        return events

    def _is_game_over(self) -> bool:
        """Fast end-of-game check used between phases."""
        if self.state is None:
            return True
        if getattr(self.state, "game_over", False):
            return True
        if getattr(self.state, "clankers_loser", None) is not None:
            return True
        alive = [p for p in self.state.players.values() if not p.has_lost]
        return len(alive) <= 1

    def _other_player(self, player_id: str) -> Optional[str]:
        for pid in self.state.players:
            if pid != player_id:
                return pid
        return None

    def _zone_lookup(self, zone_type: ZoneType, owner: Optional[str]) -> Optional[Zone]:
        """Find a zone via the canonical lowercase key convention.

        Matches ``Game._create_player_zones`` and every peer engine: per-player
        zones are keyed ``f"{zone_type.name.lower()}_{owner}"``, shared zones
        with no owner are keyed ``zone_type.name.lower()``.
        """
        s = self.state
        if s is None:
            return None
        if owner is None:
            return s.zones.get(zone_type.name.lower())
        return s.zones.get(f"{zone_type.name.lower()}_{owner}")

    def _all_assembly_floor_objs(self, player_id: str) -> list[str]:
        """Return every obj_id on the Assembly Floor controlled by ``player_id``.

        Reads ``state.zones[f"clankers_assembly_floor_{player_id}"]`` (the
        canonical per-player lowercase key). Agent 1's
        ``setup_clankers_player`` is responsible for pre-creating the zone.
        """
        s = self.state
        if s is None:
            return []
        z = self._zone_lookup(ZoneType.CLANKERS_ASSEMBLY_FLOOR, player_id)
        if z is None:
            return []
        return list(z.objects)

    def _get_rng(self) -> random.Random:
        """Reuse the state's deterministic RNG if seeded, else a fresh one."""
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
    # Phase 1: BOOT
    # ---------------------------------------------------------------------
    def _phase_boot(self, player_id: str) -> list[Event]:
        """Boot phase: untap, refresh compute, bump turn number, fire upkeep
        triggers, emit CLANKERS_TURN_START.
        """
        events: list[Event] = []

        # Bump turn_number FIRST so compute math sees the new value.
        # Following minecraft_turn's per-half-turn convention: each call
        # to run_turn increments the counter once. (Cleaner than per-pair
        # for state inspection.)
        if self.turn_state is not None:
            self.turn_state.turn_number += 1
            self.state.turn_number = self.turn_state.turn_number

        events.append(self._emit_phase_event("boot", "start", player_id))

        # Untap all of the active player's tapped objects on the Assembly Floor.
        # Works under both Agent 1's per-player uppercase zone convention and
        # the legacy shared-battlefield convention.
        #
        # Containment Lance (ETHOS) and any other "skip ready next Boot" effect
        # sets ``state.clankers_clan_ethos_skip_ready_next_boot[player_id]`` to
        # True before this Boot. If set, we skip the untap pass and clear the
        # flag so the lockout only lasts a single Boot.
        skip_map = getattr(self.state, "clankers_clan_ethos_skip_ready_next_boot", None)
        skip_ready = bool(skip_map.get(player_id, False)) if isinstance(skip_map, dict) else False
        if skip_ready:
            # Consume the one-shot lockout flag.
            skip_map[player_id] = False
        else:
            for obj_id in self._all_assembly_floor_objs(player_id):
                obj = self.state.objects.get(obj_id)
                if obj is None or obj.controller != player_id:
                    continue
                if getattr(obj.state, "tapped", False):
                    obj.state.tapped = False
                    untap_event = Event(
                        type=EventType.UNTAP,
                        payload={"object_id": obj_id, "reason": "clankers_boot"},
                    )
                    self._emit(untap_event)
                    events.append(untap_event)

        # Refresh compute pool.
        compute_pool_base = int(_get_constant(
            "CLANKERS_COMPUTE_POOL_BASE", _DEFAULT_COMPUTE_POOL_BASE
        ))
        pool_dict = getattr(self.state, "clankers_compute_pool", None)
        cap_dict = getattr(self.state, "clankers_compute_cap", None)
        if pool_dict is not None and cap_dict is not None:
            turn_num = self.turn_state.turn_number if self.turn_state else 1
            cap = cap_dict.get(player_id, _DEFAULT_COMPUTE_CAP)
            pool_dict[player_id] = min(cap, compute_pool_base + turn_num)
            gain_event = Event(
                type=EventType.CLANKERS_COMPUTE_GAIN,
                payload={
                    "player_id": player_id,
                    "amount": pool_dict[player_id],
                    "reason": "boot_refresh",
                },
            )
            self._emit(gain_event)
            events.append(gain_event)

        # Emit CLANKERS_TURN_START so per-card upkeep triggers can hook it.
        turn_start = Event(
            type=EventType.CLANKERS_TURN_START,
            payload={
                "player": player_id,
                "turn_number": self.turn_state.turn_number if self.turn_state else 1,
            },
        )
        self._emit(turn_start)
        events.append(turn_start)

        # Generic TURN_START for downstream tooling (replay, server log).
        generic_start = Event(
            type=EventType.TURN_START,
            payload={
                "player": player_id,
                "turn_number": self.turn_state.turn_number if self.turn_state else 1,
                "mode": "clankers",
            },
        )
        self._emit(generic_start)
        events.append(generic_start)

        # Catch-all SBA / workshop check (e.g. a setup_interceptor that
        # deals damage on turn-start).
        events.extend(self._check_workshop_breached())
        events.append(self._emit_phase_event("boot", "end", player_id))
        return events

    # ---------------------------------------------------------------------
    # Phase 2: ALLOCATE
    # ---------------------------------------------------------------------
    def _phase_allocate(self, player_id: str) -> list[Event]:
        """Allocate phase: once-per-turn hand refill, then deathclock check."""
        events: list[Event] = []
        events.append(self._emit_phase_event("allocate", "start", player_id))

        # Consult AI for the may-refill decision.
        take = True  # default: take the refill
        handler = self._ai_handler_for(player_id)
        if handler is not None:
            method = getattr(handler, "choose_refill", None)
            if callable(method):
                try:
                    result = method(self.state, player_id)
                    if isinstance(result, bool):
                        take = result
                except Exception:
                    take = True

        # Emit the refill query — Agent 1 handles the actual draw resolution
        # through ``emit_refill_query`` interceptors (REPLACE / REACT priority).
        clankers = _import_clankers_module()
        if clankers is not None and hasattr(clankers, "emit_refill_query"):
            try:
                # Some implementations accept ``take``; older ones do not.
                # Try the keyword form first, fall back to positional / no-arg.
                try:
                    refill_events = clankers.emit_refill_query(
                        self.state, player_id, take=take
                    ) or []
                except TypeError:
                    refill_events = clankers.emit_refill_query(
                        self.state, player_id
                    ) or []
                for ev in refill_events:
                    self._emit(ev)
                    events.append(ev)
            except Exception:
                # Fall back to inline refill.
                events.extend(self._inline_refill(player_id, take=take))
        else:
            events.extend(self._inline_refill(player_id, take=take))

        # Mark refill_used regardless of take/decline so the gate enforces
        # once-per-turn semantics. Agent 1's helper may already do this,
        # but setting again is idempotent.
        refill_used = getattr(self.state, "clankers_refill_used", None)
        if isinstance(refill_used, dict):
            refill_used[player_id] = True

        # Activate the death-clock if both libraries are empty.
        if clankers is not None and hasattr(clankers, "activate_deathclock_if_needed"):
            try:
                deathclock_events = clankers.activate_deathclock_if_needed(self.state) or []
                for ev in deathclock_events:
                    self._emit(ev)
                    events.append(ev)
            except Exception:
                # Fallback inline deathclock tick.
                events.extend(self._inline_deathclock())
        else:
            events.extend(self._inline_deathclock())

        events.extend(self._check_workshop_breached())
        events.append(self._emit_phase_event("allocate", "end", player_id))
        return events

    def _inline_refill(self, player_id: str, *, take: bool) -> list[Event]:
        """Fallback hand refill when Agent 1's helper isn't available.

        Emits CLANKERS_HAND_REFILL_QUERY then either CLANKERS_REFILL_TAKEN
        + a DRAW for the missing cards, or CLANKERS_REFILL_DECLINED.
        """
        events: list[Event] = []
        hand_floor = int(_get_constant("CLANKERS_HAND_FLOOR", _DEFAULT_HAND_FLOOR))
        hand = self._zone_lookup(ZoneType.HAND, player_id)
        current = len(hand.objects) if hand is not None else 0
        target = hand_floor

        query = Event(
            type=EventType.CLANKERS_HAND_REFILL_QUERY,
            payload={
                "player_id": player_id,
                "current_hand_size": current,
                "target_hand_size": target,
                "may": True,
            },
        )
        self._emit(query)
        events.append(query)

        if not take:
            decline = Event(
                type=EventType.CLANKERS_REFILL_DECLINED,
                payload={"player_id": player_id, "current_hand_size": current},
            )
            self._emit(decline)
            events.append(decline)
            return events

        # Take the refill — pull from library top to hand.
        needed = max(0, target - current)
        drawn = self._move_top_n_to_hand(player_id, needed) if needed else 0
        if drawn > 0:
            draw = Event(
                type=EventType.DRAW,
                payload={
                    "player": player_id,
                    "count": drawn,
                    "reason": "clankers_refill",
                },
            )
            self._emit(draw)
            events.append(draw)
        taken = Event(
            type=EventType.CLANKERS_REFILL_TAKEN,
            payload={
                "player_id": player_id,
                "drawn": drawn,
                "current_hand_size": current + drawn,
            },
        )
        self._emit(taken)
        events.append(taken)
        return events

    def _inline_deathclock(self) -> list[Event]:
        """Fallback deathclock tick when Agent 1's helper isn't available."""
        events: list[Event] = []

        # Are both libraries empty?
        empty = True
        for pid in self.state.players:
            lib = self._zone_lookup(ZoneType.LIBRARY, pid)
            if lib is not None and lib.objects:
                empty = False
                break
        if not empty:
            return events

        # Either start or tick the deathclock.
        if not getattr(self.state, "clankers_containment_failure", False):
            self.state.clankers_containment_failure = True  # type: ignore[attr-defined]
            self.state.clankers_containment_turn = 0  # type: ignore[attr-defined]
        else:
            self.state.clankers_containment_turn = int(  # type: ignore[attr-defined]
                getattr(self.state, "clankers_containment_turn", 0)
            ) + 1

        base = int(_get_constant("CLANKERS_DEATHCLOCK_BASE", _DEFAULT_DEATHCLOCK_BASE))
        turn = int(getattr(self.state, "clankers_containment_turn", 0))
        damage = base * (2 ** turn)

        tick = Event(
            type=EventType.CLANKERS_CONTAINMENT_FAILURE_TICK,
            payload={"turn": turn, "damage": damage},
        )
        self._emit(tick)
        events.append(tick)

        # Apply self-damage to each player's workshop integrity.
        integrity = getattr(self.state, "clankers_workshop_integrity", None)
        if isinstance(integrity, dict):
            for pid in self.state.players:
                integrity[pid] = integrity.get(pid, 0) - damage
                wd = Event(
                    type=EventType.CLANKERS_WORKSHOP_DAMAGE,
                    payload={
                        "player_id": pid,
                        "amount": damage,
                        "reason": "containment_failure",
                    },
                )
                self._emit(wd)
                events.append(wd)
        return events

    # ---------------------------------------------------------------------
    # Phase 3: ASSEMBLE
    # ---------------------------------------------------------------------
    def _phase_assemble(self, player_id: str) -> list[Event]:
        return self._run_action_loop(player_id, phase_label="assemble")

    # ---------------------------------------------------------------------
    # Phase 5: REASSEMBLE
    # ---------------------------------------------------------------------
    def _phase_reassemble(self, player_id: str) -> list[Event]:
        return self._run_action_loop(player_id, phase_label="reassemble")

    def _run_action_loop(self, player_id: str, *, phase_label: str) -> list[Event]:
        """Shared body for Assemble and Reassemble — the AI's main-phase loop.

        Loops up to ``_ASSEMBLE_ACTION_CAP`` times asking the AI for an
        action and dispatching it. A ``None``, ``{"action": "pass"}``, or
        unknown action ends the loop.
        """
        events: list[Event] = []
        events.append(self._emit_phase_event(phase_label, "start", player_id))

        handler = self._ai_handler_for(player_id)
        clankers = _import_clankers_module()

        for action_count in range(_ASSEMBLE_ACTION_CAP):
            action = None
            if handler is not None:
                method = getattr(handler, "choose_assemble_action", None)
                if callable(method):
                    try:
                        action = method(self.state, player_id)
                    except Exception:
                        action = None

            if action is None:
                break
            if isinstance(action, dict) and action.get("action") == "pass":
                break
            if not isinstance(action, dict):
                # Skip non-dict shapes defensively.
                break

            kind = action.get("action")
            try:
                if kind in {
                    "play_chassis", "play_weapon", "play_add_on",
                    "play_transient", "play_structure",
                }:
                    new_events = self._dispatch_play_card(
                        clankers, player_id, action,
                    )
                elif kind == "attach_floor_part":
                    new_events = self._dispatch_attach(
                        clankers, action,
                    )
                elif kind == "activate_ability":
                    new_events = self._dispatch_activate(
                        clankers, player_id, action,
                    )
                else:
                    # Unknown action — bail to avoid infinite loop.
                    break
            except Exception:
                # If a dispatch crashes, surface it as a warning event
                # and break out so the harness can keep going.
                warn = Event(
                    type=EventType.PHASE_END,  # reuse for visibility
                    payload={
                        "phase": phase_label,
                        "warning": "dispatch_exception",
                        "action": kind,
                    },
                )
                self._emit(warn)
                events.append(warn)
                break

            for ev in new_events or []:
                events.append(ev)
            events.extend(self._check_workshop_breached())
            if self._is_game_over():
                break
        else:
            # Loop ran the full 100 iterations without breaking → cap hit.
            warn = Event(
                type=EventType.PHASE_END,  # reuse for observability
                payload={
                    "phase": phase_label,
                    "warning": "assemble_action_cap_hit",
                    "cap": _ASSEMBLE_ACTION_CAP,
                },
            )
            self._emit(warn)
            events.append(warn)

        events.append(self._emit_phase_event(phase_label, "end", player_id))
        return events

    def _dispatch_play_card(
        self,
        clankers,
        player_id: str,
        action: dict,
    ) -> list[Event]:
        """Route a play_<cardtype> action to clankers.play_card_from_hand."""
        if clankers is None or not hasattr(clankers, "play_card_from_hand"):
            return []
        # Pass action through as kwargs. play_card_from_hand routes by
        # CardType internally per contract §4.
        card_obj_id = action.get("card_obj_id")
        if not isinstance(card_obj_id, str):
            return []
        # Build a kwargs dict, dropping the action key.
        kwargs = {k: v for k, v in action.items() if k not in {"action", "card_obj_id"}}
        try:
            out = clankers.play_card_from_hand(
                self.state, player_id, card_obj_id, **kwargs,
            )
            return list(out) if out else []
        except TypeError:
            # If the signature differs (no **kwargs), fall back to a basic call.
            try:
                out = clankers.play_card_from_hand(self.state, player_id, card_obj_id)
                return list(out) if out else []
            except Exception:
                return []
        except Exception:
            return []

    def _dispatch_attach(
        self,
        clankers,
        action: dict,
    ) -> list[Event]:
        """Route an attach_floor_part action to clankers.attach_part."""
        if clankers is None or not hasattr(clankers, "attach_part"):
            return []
        part_id = action.get("part_obj_id")
        chassis_id = action.get("target_chassis_id")
        if not isinstance(part_id, str) or not isinstance(chassis_id, str):
            return []
        try:
            out = clankers.attach_part(self.state, part_id, chassis_id)
            return list(out) if out else []
        except Exception:
            return []

    def _dispatch_activate(
        self,
        clankers,
        player_id: str,
        action: dict,
    ) -> list[Event]:
        """Route an activate_ability action to ``clankers.activate_ability``.

        Contract §1 shape:
            {"action": "activate_ability", "source_obj_id": str,
             "ability_index": int, "targets": list[str]}

        The engine module's ``activate_ability`` validates ownership, cost
        payability (compute pool and/or self-exhaust), pays the cost, then
        invokes the descriptor's ``effect_fn`` and returns
        ``[CLANKERS_ACTIVATE marker, *cost_events, *effect_events]``.
        Returns ``[]`` if the action can't legally resolve (caller doesn't
        crash).
        """
        source_id = action.get("source_obj_id")
        ability_index = action.get("ability_index", 0)
        targets = action.get("targets", []) or []
        if not isinstance(source_id, str):
            return []
        if clankers is None:
            return []
        try:
            out = clankers.activate_ability(
                self.state, player_id, source_id,
                ability_index=ability_index, targets=targets,
            )
            return list(out) if out else []
        except Exception:
            return []

    # ---------------------------------------------------------------------
    # Phase 4: COMBAT
    # ---------------------------------------------------------------------
    def _phase_combat(self, player_id: str) -> list[Event]:
        """Delegate combat resolution to the ClankersCombatManager."""
        events: list[Event] = []
        events.append(self._emit_phase_event("combat", "start", player_id))

        if self.combat_manager is not None:
            resolve = getattr(self.combat_manager, "resolve_combat_phase", None)
            if callable(resolve):
                try:
                    combat_events = resolve(player_id) or []
                    for ev in combat_events:
                        events.append(ev)
                except Exception as exc:
                    warn = Event(
                        type=EventType.PHASE_END,  # reuse for observability
                        payload={
                            "phase": "combat",
                            "warning": "combat_manager_exception",
                            "exception": repr(exc),
                        },
                    )
                    self._emit(warn)
                    events.append(warn)
        # No combat manager → silently skip; the smoke test tolerates this.

        events.extend(self._check_workshop_breached())
        events.append(self._emit_phase_event("combat", "end", player_id))
        return events

    # ---------------------------------------------------------------------
    # Phase 6: CLEANUP
    # ---------------------------------------------------------------------
    def _phase_cleanup(self, player_id: str) -> list[Event]:
        """End-of-turn cleanup.

        - End-of-turn triggers fire via the interceptor flow.
        - clankers_refill_used cleared for next turn.
        - **Damage on chassis persists across turns** (Clankers rule).
        - First-turn flag cleared once player 1's first turn ends.
        - CLANKERS_TURN_END + TURN_END emitted.
        - Active player swapped + current_player_index advanced.
        """
        events: list[Event] = []
        events.append(self._emit_phase_event("cleanup", "start", player_id))

        # Reset refill flag for the player whose turn just ended.
        refill_used = getattr(self.state, "clankers_refill_used", None)
        if isinstance(refill_used, dict):
            refill_used[player_id] = False

        # CONTRACT NOTE: We intentionally DO NOT clear damage_marked here.
        # The Clankers rule (doc § 2 phase 6, doc § 5 combat math) is that
        # damage on chassis persists across turns. Base TurnManager.cleanup
        # would clear it; this engine never invokes that path because we
        # don't go through _run_ending_phase.

        # Sweep ``duration='end_of_turn'`` interceptors out of
        # ``state.interceptors`` so per-turn buffs (e.g. MIRTH temp P/T
        # buffs) don't accumulate across long games. Cards that defensively
        # snapshot ``state.turn_number`` in their filter still work — the
        # sweep here is the canonical eviction.
        ic_map = getattr(self.state, "interceptors", None)
        if isinstance(ic_map, dict):
            eot_ids = [
                ic_id for ic_id, ic in ic_map.items()
                if getattr(ic, "duration", None) == "end_of_turn"
            ]
            for ic_id in eot_ids:
                ic_map.pop(ic_id, None)
                # Also detach from any source object's interceptor_ids so
                # the per-object cleanup path doesn't try to double-remove.
                for obj in self.state.objects.values():
                    if ic_id in obj.interceptor_ids:
                        obj.interceptor_ids.remove(ic_id)

        # Clear the first-turn flag once player 1's first turn has ended.
        # The flag exists to suppress combat exactly once.
        first_player_id = getattr(self.state, "clankers_first_player", None)
        if (
            getattr(self.state, "clankers_first_turn", False)
            and player_id == first_player_id
        ):
            self.state.clankers_first_turn = False  # type: ignore[attr-defined]

        # Per-turn scratchpad clear (parity with base TurnManager).
        if hasattr(self.state, "turn_data") and self.state.turn_data:
            self.state.turn_data.clear()

        # Emit CLANKERS_TURN_END so per-card EOT triggers can hook it.
        clankers_end = Event(
            type=EventType.CLANKERS_TURN_END,
            payload={
                "player": player_id,
                "turn_number": self.turn_state.turn_number if self.turn_state else 1,
            },
        )
        self._emit(clankers_end)
        events.append(clankers_end)

        # Generic TURN_END for downstream tooling.
        generic_end = Event(
            type=EventType.TURN_END,
            payload={
                "player": player_id,
                "turn_number": self.turn_state.turn_number if self.turn_state else 1,
                "mode": "clankers",
            },
        )
        self._emit(generic_end)
        events.append(generic_end)

        # Catch-all workshop check (a CLANKERS_TURN_END interceptor may
        # have dealt damage).
        events.extend(self._check_workshop_breached())

        events.append(self._emit_phase_event("cleanup", "end", player_id))

        # Swap active player. Advance the turn-order index so the next
        # ``run_turn(other_player_id)`` (or ``run_turn(None)``) picks up
        # the right seat.
        next_player = self._other_player(player_id)
        if next_player is not None:
            self.state.active_player = next_player
            if self.turn_state is not None:
                self.turn_state.active_player_id = next_player
            if self.turn_order and next_player in self.turn_order:
                self.current_player_index = self.turn_order.index(next_player)

        return events

    # ---------------------------------------------------------------------
    # MTG-compat no-op overrides
    # ---------------------------------------------------------------------
    # The base ``TurnManager`` exposes async MTG phase helpers. Clankers
    # never calls them but some replay tools may invoke them by reflection.
    # Override to no-op for safety, matching cats_turn / hearthstone_turn.
    # ---------------------------------------------------------------------
    async def _run_beginning_phase(self) -> list[Event]:
        return []

    async def _run_main_phase(self, *_args, **_kwargs) -> list[Event]:
        return []

    async def _run_combat_phase(self) -> list[Event]:
        return []

    async def _run_ending_phase(self) -> list[Event]:
        return []
