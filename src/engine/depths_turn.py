"""
Depths Turn Manager
====================

Submarine-fleet card game turn structure. The five phases per turn are, in
order:

    DIVE        — Untap exhausted Vessels, Resupply (gain charges, capped),
                  Recon (draw 1)
    MANEUVER    — Player-action loop (deploy Vessels, attach Crew/Weapons,
                  change depth band, lay Mines, play Doctrine cards,
                  activate abilities). No Resupply.
    ENGAGEMENT  — Combat sub-phases:
                    1. Declare Attackers
                    2. Detection Resolution (defender spends Sonar)
                    3. Declare Interceptors (only on detected attackers)
                    4. Damage (simultaneous, depth-modifier reduction)
    REGROUP     — Same action loop as Maneuver (post-engagement main).
    SURFACE     — Cleanup: discard down to hand limit (default 8),
                  Sonar Decay (detected flags reset per Agent 1's rules),
                  Oxygen tick on submerged Vessels.

Every phase emits ``PHASE_START`` / ``PHASE_END`` events with payload
``{"phase": "<name>", "player": <id>}`` so card triggers can hook them.

This file lives behind the same TurnManager protocol as
``minecraft_turn.py`` and ``hearthstone_turn.py``. It assumes Agent 1
will land ``src/engine/depths.py`` exporting ``setup_depths_player``,
``DepthsModeAdapter``, ``cap_for_turn``, and the ``DEPTHS_*`` event-type
additions to ``EventType``. It assumes Agent 2 will land
``src/engine/depths_combat.py`` exporting ``DepthsCombatManager``. Imports
from those modules are deferred (function-local) so this file can be
imported in parallel with ongoing work on its peers.

AI handler contract (Agent 4 implements these on
``game.depths_ai_handler``):

    async choose_maneuver_action(state, player_id)
        Returns ``None`` (or ``{"action_type": "DEPTHS_END_MANEUVER"}``)
        to end the maneuver phase, otherwise a dict describing one
        action. See ``execute_action`` for the action-type dispatch table.

    async choose_regroup_action(state, player_id)
        Same shape as ``choose_maneuver_action`` but for the post-combat
        regroup loop.

    choose_attackers(state, player_id)
        Returns the list passed to ``DepthsCombatManager.declare_attackers``.

    choose_detections(state, defender_id, attackers)
        Returns the list passed to ``DepthsCombatManager.resolve_detection``.

    choose_interceptors(state, defender_id, attackers)
        Returns the list passed to ``DepthsCombatManager.declare_interceptors``.

    choose_discards(state, player_id, count)
        Returns ``count`` card ids to discard during the SURFACE cleanup
        step. May return fewer if the hand is below the limit.
"""

from __future__ import annotations

import inspect
import random
from typing import Any, Optional, TYPE_CHECKING

from .turn import TurnManager, Phase, Step
from .types import (
    Event,
    EventType,
    GameState,
    Player,
    ZoneType,
)

if TYPE_CHECKING:  # pragma: no cover - type-only imports
    from .combat import CombatManager
    from .pipeline import EventPipeline


# Maneuver/Regroup action loops are bounded so a misbehaving AI handler
# can never spin the turn forever.
_ACTION_LOOP_CAP = 200

# Default hand limit if Agent 1 has not yet landed ``DepthsModeAdapter``.
_DEFAULT_HAND_LIMIT = 8

# Default opening hand if neither the GameState nor Agent 1 supplies one.
_DEFAULT_OPENING_HAND = 7


# =============================================================================
# Action-type sentinels
# =============================================================================
#
# These mirror the convention used in ``minecraft_turn.py`` (``MC_*``) and
# ``hearthstone_turn.py`` (``HS_*``). Action dicts returned by the AI handler
# (or by a future human-action callback) carry one of these in
# ``action["action_type"]``. The set is intentionally open: unknown action
# types fall through to ``(False, "Unknown Depths action", [])``.
#
ACTION_END_MANEUVER       = "DEPTHS_END_MANEUVER"
ACTION_END_REGROUP        = "DEPTHS_END_REGROUP"
ACTION_CAST_SPELL         = "DEPTHS_CAST_SPELL"        # Action / Doctrine card
ACTION_DEPLOY_VESSEL      = "DEPTHS_DEPLOY_VESSEL"
ACTION_ATTACH             = "DEPTHS_ATTACH"            # Crew/Weapon -> Vessel
ACTION_DIVE               = "DEPTHS_DIVE"              # depth band -1
ACTION_SURFACE_VESSEL     = "DEPTHS_SURFACE_VESSEL"    # depth band +1
ACTION_LAY_MINE           = "DEPTHS_LAY_MINE"
ACTION_ACTIVATE_ABILITY   = "DEPTHS_ACTIVATE_ABILITY"


# =============================================================================
# Helpers — guarded imports from peer modules (Agent 1 / Agent 2)
# =============================================================================

def _import_depths_module():
    """Return the ``src.engine.depths`` module if Agent 1 has shipped it."""
    try:
        from . import depths as _depths  # type: ignore
        return _depths
    except Exception:
        return None


def _import_combat_module():
    """Return the ``src.engine.depths_combat`` module if Agent 2 has shipped it."""
    try:
        from . import depths_combat as _depths_combat  # type: ignore
        return _depths_combat
    except Exception:
        return None


def _resolve_event_type(name: str):
    """Look up a ``DEPTHS_*`` EventType member by name, with a typed fallback.

    Agent 1 owns the ``EventType`` additions. Until they land, we fall back
    to a stable string sentinel so the turn manager can be exercised in
    isolation by smoke tests. Once Agent 1's enum members are in place the
    real enum value is used.
    """
    member = getattr(EventType, name, None)
    if member is not None:
        return member
    # String fallback: Event payload-only consumers will still see the right
    # ``payload['phase']`` and ``payload['player']`` data.
    return name


# =============================================================================
# DepthsTurnManager
# =============================================================================

class DepthsTurnManager(TurnManager):
    """Drives the five-phase Depths turn loop.

    Mirrors the public surface of ``MinecraftTurnManager`` /
    ``HearthstoneTurnManager``: ``setup_game`` initialises both players and
    decides the starting player, then ``run_turn`` advances one full turn
    for ``player_id`` (defaulting to the player whose ``current_player_index``
    slot is up).
    """

    # ---------------------------------------------------------------------
    # Construction & accessors
    # ---------------------------------------------------------------------
    def __init__(self, state: GameState):
        super().__init__(state)
        self.ai_players: set[str] = set()
        self.depths_ai_handler = None
        # Per-player AI handler overrides — keyed by player_id. When a key
        # is present we dispatch decision calls for that player to the
        # mapped handler instead of ``self.depths_ai_handler``. This lets
        # AI-vs-AI tests give each player its own decision-tracking shim
        # while keeping single-handler usage backwards compatible.
        self.depths_ai_handlers: dict[str, Any] = {}
        self.human_action_handler = None  # async fn(player_id, state) -> action_dict
        # One DepthsCombatManager per game keeps any across-combat bookkeeping
        # (detection-flag decay, interceptor pairings) attached to a single
        # object rather than being rebuilt every engagement.
        self._combat_mgr = None

    @property
    def _emit_pipeline(self):
        """Return ``self.pipeline`` or fall back to the state-attached one.

        Tests that construct the turn manager after the Game (e.g. swap
        ``game.turn_manager`` post-init) won't have ``self.pipeline``
        wired by ``Game._connect_subsystems``. The Game still publishes
        its pipeline on ``state._pipeline`` so we can recover it lazily —
        otherwise system interceptors never fire and DEPTHS_RESUPPLY +
        SBA loss checks silently no-op.
        """
        if self.pipeline is not None:
            return self.pipeline
        return getattr(self.state, "_pipeline", None)

    def set_ai_handler(self, handler, player_id: Optional[str] = None) -> None:
        """Install an AI handler.

        With ``player_id=None`` (default) the handler becomes the shared
        fallback used for any AI player without a per-player override
        — the original single-handler shape. With ``player_id`` the
        handler is installed for that player only and overrides the
        fallback for that player's turns.
        """
        if player_id is None:
            self.depths_ai_handler = handler
            game = getattr(self.state, "_game", None)
            if game is not None:
                try:
                    game.depths_ai_handler = handler
                except Exception:
                    pass
        else:
            if handler is None:
                self.depths_ai_handlers.pop(player_id, None)
            else:
                self.depths_ai_handlers[player_id] = handler

    def set_ai_player(self, player_id: str) -> None:
        self.ai_players.add(player_id)

    def _is_ai_player(self, player_id: Optional[str]) -> bool:
        return bool(player_id and player_id in self.ai_players)

    def _ai_handler(self, game, player_id: Optional[str] = None) -> Any:
        """Resolve the AI handler for ``player_id`` (or the shared fallback).

        Preference order:
          1. Per-player override registered via ``set_ai_handler(h, pid)``.
          2. Per-player override stored on the ``Game`` instance under
             ``depths_ai_handlers``.
          3. Shared handler on ``self.depths_ai_handler``.
          4. Shared handler on ``game.depths_ai_handler``.
        """
        if player_id is not None:
            handler = self.depths_ai_handlers.get(player_id)
            if handler is not None:
                return handler
            if game is not None:
                game_map = getattr(game, "depths_ai_handlers", None)
                if isinstance(game_map, dict):
                    handler = game_map.get(player_id)
                    if handler is not None:
                        return handler
        if self.depths_ai_handler is not None:
            return self.depths_ai_handler
        if game is not None:
            return getattr(game, "depths_ai_handler", None)
        return None

    # ---------------------------------------------------------------------
    # Setup
    # ---------------------------------------------------------------------
    async def setup_game(
        self,
        game,
        p1_deck: list,
        p2_deck: list,
        p1_flagship,
        p2_flagship,
    ) -> list[Event]:
        """Initialise both players and prepare turn 1.

        ``p*_deck`` is a list of ``CardDefinition`` (the pattern used by
        every other engine in this repo). ``p*_flagship`` is the Flagship
        Vessel ``CardDefinition``. The actual Flagship object construction,
        library zone setup, and charge-pool initialisation live in
        Agent 1's ``setup_depths_player``.

        Returns the list of bookkeeping events emitted during setup
        (``GAME_START``, opening-hand ``DRAW`` events, etc.).
        """
        events: list[Event] = []
        depths = _import_depths_module()
        if depths is None or not hasattr(depths, "setup_depths_player"):
            raise RuntimeError(
                "depths_turn.setup_game requires src.engine.depths.setup_depths_player. "
                "Agent 1 must land src/engine/depths.py before setup_game can run."
            )

        player_ids = list(self.state.players.keys())
        if len(player_ids) < 2:
            raise RuntimeError(
                f"DepthsTurnManager.setup_game requires 2 players, got {len(player_ids)}."
            )
        p1_id, p2_id = player_ids[0], player_ids[1]
        p1 = self.state.players[p1_id]
        p2 = self.state.players[p2_id]

        # Delegate Flagship construction, deck → library placement, and
        # charge-pool initialisation to Agent 1.
        depths.setup_depths_player(game, p1, p1_deck, p1_flagship)
        depths.setup_depths_player(game, p2, p2_deck, p2_flagship)

        # Shuffle libraries (best-effort — Agent 1 may already do this).
        for pid in player_ids:
            lib = self.state.zones.get(f"library_{pid}")
            if lib is not None:
                random.shuffle(lib.objects)

        # Decide starting player. Coin flip; tests can pre-seed
        # ``state.rng_seed`` for determinism.
        rng = getattr(self.state, "_rng", None) or random.Random(
            getattr(self.state, "rng_seed", None)
        )
        first_idx = rng.randint(0, 1)
        first_id = player_ids[first_idx]
        second_id = player_ids[1 - first_idx]
        self.set_turn_order([first_id, second_id])

        # Reset turn counter — turn 1 will be incremented at the top of
        # ``run_turn`` to land at 1.
        self.turn_state.turn_number = 0
        self.state.turn_number = 0

        # Note: ``setup_depths_player`` (Agent 1) already deals each player
        # their opening hand of OPENING_HAND_SIZE cards. We do NOT re-draw
        # here. If a future Agent-1 revision drops the in-setup draw, swap
        # back to an explicit DRAW emission gated by ``_opening_hand_size``.

        # Game start event (parity with Pokemon / HS).
        game_start = Event(
            type=EventType.GAME_START,
            payload={
                "players": list(self.turn_order),
                "first_player": first_id,
            },
        )
        if (pipeline := self._emit_pipeline):
            pipeline.emit(game_start)
        events.append(game_start)

        return events

    # ---------------------------------------------------------------------
    # Turn driver
    # ---------------------------------------------------------------------
    async def run_turn(self, player_id: Optional[str] = None) -> list[Event]:
        """Run one full Depths turn for ``player_id`` (or the next in order)."""
        events: list[Event] = []

        # Determine active player.
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

        turn_start = Event(
            type=EventType.TURN_START,
            payload={"player": active, "turn_number": self.turn_state.turn_number},
        )
        if (pipeline := self._emit_pipeline):
            pipeline.emit(turn_start)
        events.append(turn_start)

        # 1. DIVE
        events.extend(await self.phase_dive(game, active))
        if self._game_over(game):
            return events

        # 2. MANEUVER
        self.turn_state.phase = Phase.PRECOMBAT_MAIN
        self.turn_state.step = Step.MAIN
        events.extend(await self.phase_maneuver(game, active))
        if self._game_over(game):
            return events

        # 3. ENGAGEMENT
        self.turn_state.phase = Phase.COMBAT
        self.turn_state.step = Step.BEGINNING_OF_COMBAT
        events.extend(await self.phase_engagement(game, active))
        if self._game_over(game):
            return events

        # 4. REGROUP
        self.turn_state.phase = Phase.POSTCOMBAT_MAIN
        self.turn_state.step = Step.MAIN
        events.extend(await self.phase_regroup(game, active))
        if self._game_over(game):
            return events

        # 5. SURFACE (end)
        self.turn_state.phase = Phase.ENDING
        self.turn_state.step = Step.END_STEP
        events.extend(await self.phase_surface(game, active))

        turn_end = Event(
            type=EventType.TURN_END,
            payload={"player": active, "turn_number": self.turn_state.turn_number},
        )
        if (pipeline := self._emit_pipeline):
            pipeline.emit(turn_end)
        events.append(turn_end)

        # Bump turn pointer + pass priority. ``state.turn_number`` already
        # reflects the turn we just finished; the *next* player's TURN_START
        # will increment it again.
        self.state.priority_player = None
        self.current_player_index = (self.current_player_index + 1) % len(self.turn_order)

        return events

    # ---------------------------------------------------------------------
    # Phase 1: DIVE
    # ---------------------------------------------------------------------
    async def phase_dive(self, game, player_id: str) -> list[Event]:
        """Untap → Resupply → Recon (draw 1)."""
        events: list[Event] = []
        events.extend(self._emit_phase("dive", "start", player_id))

        # --- Untap step: untap each tapped Vessel of the active player.
        battlefield = self.state.zones.get("battlefield")
        if battlefield:
            for obj_id in list(battlefield.objects):
                obj = self.state.objects.get(obj_id)
                if not obj or obj.controller != player_id:
                    continue
                # Vessels only — Agent 1 owns the Vessel-card-type check.
                if not self._is_vessel(obj):
                    continue
                if not getattr(obj.state, "tapped", False):
                    continue
                untap = Event(type=EventType.UNTAP, payload={"object_id": obj_id})
                if (pipeline := self._emit_pipeline):
                    pipeline.emit(untap)
                events.append(untap)

        # Clear "summoning sickness" so freshly-deployed Vessels can act
        # this turn for cards that hook on a per-turn basis. Agent 1 may
        # also do this in the resupply interceptor; running it here is a
        # belt-and-braces measure that is cheap and idempotent.
        if battlefield:
            for obj_id in list(battlefield.objects):
                obj = self.state.objects.get(obj_id)
                if obj and obj.controller == player_id and self._is_vessel(obj):
                    if hasattr(obj.state, "summoning_sickness"):
                        obj.state.summoning_sickness = False
                # Reset per-turn attack count if the engine tracks one.
                if obj and hasattr(obj.state, "attacks_this_turn"):
                    if obj.controller == player_id:
                        obj.state.attacks_this_turn = 0

        # --- Resupply step: emit DEPTHS_RESUPPLY.
        cap = self._cap_for_turn(self.turn_state.turn_number)
        resupply = Event(
            type=_resolve_event_type("DEPTHS_RESUPPLY"),
            payload={
                "player": player_id,
                "tc_gain": 1,
                "sc_gain": 1,
                "cap": cap,
            },
        )
        if (pipeline := self._emit_pipeline):
            pipeline.emit(resupply)
        events.append(resupply)

        # --- Recon step: draw 1.
        # Skip the very first draw if the GameState says so (parity with
        # MTG ``first_player_draws``); Depths' default in the design doc
        # is "draw every turn including the first", but we honour the
        # GameState toggle for symmetry with other engines.
        skip_first_draw = (
            self.turn_state.turn_number == 1
            and player_id == self.turn_order[0]
            and not getattr(self.state, "first_player_draws", True)
        )
        if not skip_first_draw:
            draw = Event(
                type=EventType.DRAW,
                payload={"player": player_id, "count": 1},
            )
            if (pipeline := self._emit_pipeline):
                pipeline.emit(draw)
            events.append(draw)

        self._check_sba(game)
        events.extend(self._emit_phase("dive", "end", player_id))
        return events

    # ---------------------------------------------------------------------
    # Phase 2: MANEUVER
    # ---------------------------------------------------------------------
    async def phase_maneuver(self, game, player_id: str) -> list[Event]:
        """Pre-combat main: AI/human action loop until 'done with maneuver'."""
        events: list[Event] = []
        events.extend(self._emit_phase("maneuver", "start", player_id))
        events.extend(await self._run_action_loop(
            game, player_id, end_action=ACTION_END_MANEUVER, phase_label="maneuver"
        ))
        events.extend(self._emit_phase("maneuver", "end", player_id))
        return events

    # ---------------------------------------------------------------------
    # Phase 3: ENGAGEMENT
    # ---------------------------------------------------------------------
    async def phase_engagement(self, game, player_id: str) -> list[Event]:
        """Combat: Declare → Detect → Intercept → Damage."""
        events: list[Event] = []
        events.extend(self._emit_phase("engagement", "start", player_id))

        defender_id = self._other_player(player_id)
        if defender_id is None:
            events.extend(self._emit_phase("engagement", "end", player_id))
            return events

        combat_mgr = self._get_combat_mgr(game)
        if combat_mgr is None:
            # Agent 2 hasn't shipped DepthsCombatManager yet. Skip combat
            # rather than crash — useful during parallel-agent stage.
            events.extend(self._emit_phase("engagement", "end", player_id))
            return events

        attacker_ai = self._ai_handler(game, player_id)
        defender_ai = self._ai_handler(game, defender_id)

        # Mirror the active player onto state so the combat manager can
        # derive defender / attacker correctly via state.active_player.
        self.state.active_player = player_id

        # 1. Declare attackers (active player). Combat signature is
        # ``(state, attacker_specs)`` — see DepthsCombatManager.
        attackers = await self._maybe_await(
            self._call_ai(attacker_ai, "choose_attackers", self.state, player_id)
        ) or []
        decl_events = self._invoke_combat(
            combat_mgr, "declare_attackers", self.state, attackers
        )
        events.extend(decl_events)
        self._check_sba(game)
        if self._game_over(game):
            events.extend(self._emit_phase("engagement", "end", player_id))
            return events

        # 2. Detection resolution (defender). Signature ``(state, defender_id, sonar_spends)``.
        # Use an explicit None check so an empty {} from the AI is preserved
        # (combat's resolve_detection expects a dict, not a list).
        detect_choices = await self._maybe_await(
            self._call_ai(defender_ai, "choose_detections", self.state, defender_id, attackers)
        )
        if detect_choices is None:
            detect_choices = {}
        det_events = self._invoke_combat(
            combat_mgr, "resolve_detection", self.state, defender_id, detect_choices
        )
        events.extend(det_events)
        self._check_sba(game)
        if self._game_over(game):
            events.extend(self._emit_phase("engagement", "end", player_id))
            return events

        # 3. Declare interceptors (defender). Signature ``(state, blocker_specs)``.
        interceptors = await self._maybe_await(
            self._call_ai(defender_ai, "choose_interceptors", self.state, defender_id, attackers)
        ) or []
        intc_events = self._invoke_combat(
            combat_mgr, "declare_interceptors", self.state, interceptors
        )
        events.extend(intc_events)
        self._check_sba(game)
        if self._game_over(game):
            events.extend(self._emit_phase("engagement", "end", player_id))
            return events

        # 4. Damage.
        dmg_events = self._invoke_combat(combat_mgr, "assign_damage", self.state)
        events.extend(dmg_events)

        # Reset combat manager per-engagement state if it supports it.
        for reset_name in ("reset_combat", "end_combat", "reset"):
            if hasattr(combat_mgr, reset_name):
                try:
                    getattr(combat_mgr, reset_name)()
                except TypeError:
                    # Some combat managers want player_id; try once with it.
                    try:
                        getattr(combat_mgr, reset_name)(player_id=player_id)
                    except Exception:
                        pass
                break

        self._check_sba(game)
        events.extend(self._emit_phase("engagement", "end", player_id))
        return events

    # ---------------------------------------------------------------------
    # Phase 4: REGROUP
    # ---------------------------------------------------------------------
    async def phase_regroup(self, game, player_id: str) -> list[Event]:
        """Post-combat main: same loop as maneuver, no resupply."""
        events: list[Event] = []
        events.extend(self._emit_phase("regroup", "start", player_id))
        events.extend(await self._run_action_loop(
            game, player_id, end_action=ACTION_END_REGROUP, phase_label="regroup"
        ))
        events.extend(self._emit_phase("regroup", "end", player_id))
        return events

    # ---------------------------------------------------------------------
    # Phase 5: SURFACE
    # ---------------------------------------------------------------------
    async def phase_surface(self, game, player_id: str) -> list[Event]:
        """End of turn: discard, sonar decay, oxygen tick, EOT modifier sweep."""
        events: list[Event] = []
        events.extend(self._emit_phase("surface", "start", player_id))

        # --- Cleanup: discard down to hand limit.
        events.extend(await self._discard_to_hand_limit(game, player_id))

        # --- Sonar Decay: emit DEPTHS_PING_DECAY.
        decay = Event(
            type=_resolve_event_type("DEPTHS_PING_DECAY"),
            payload={"player": player_id, "turn_number": self.turn_state.turn_number},
        )
        if (pipeline := self._emit_pipeline):
            pipeline.emit(decay)
        events.append(decay)

        # --- Oxygen tick on submerged Vessels.
        events.extend(self._oxygen_tick(player_id))

        # --- End-of-turn modifier sweep. Mirrors the base TurnManager cleanup
        # in src/engine/turn.py:440-480 but skips MTG-specific bits (we don't
        # heal damage; hull damage persists in Depths).
        self._sweep_eot_modifiers()

        self._check_sba(game)
        events.extend(self._emit_phase("surface", "end", player_id))
        return events

    def _sweep_eot_modifiers(self) -> None:
        """Drop pt_modifiers / temporary abilities / interceptors whose
        duration is end-of-turn. Without this, cards like Snorkel Stalker's
        '+1 power EOT' trigger pump accumulate across turns indefinitely.
        """
        eot_aliases = {"end_of_turn", "until_end_of_turn", "until_eot", "eot",
                       "next_end_step", "end_of_this_turn", "this_turn"}

        battlefield = self.state.zones.get("battlefield")
        if battlefield:
            for obj_id in list(battlefield.objects):
                obj = self.state.objects.get(obj_id)
                if obj is None:
                    continue
                # Clear PT modifiers tagged with EOT durations.
                if hasattr(obj.state, "pt_modifiers") and obj.state.pt_modifiers:
                    obj.state.pt_modifiers = [
                        mod for mod in obj.state.pt_modifiers
                        if str(mod.get("duration", "")).strip().lower().replace(" ", "_")
                        not in eot_aliases
                    ]
                # Clear temporary ability grants.
                if obj.characteristics and obj.characteristics.abilities:
                    obj.characteristics.abilities = [
                        a for a in obj.characteristics.abilities
                        if not (
                            isinstance(a, dict)
                            and a.get("_temporary") is True
                            and a.get("_duration") == "end_of_turn"
                        )
                    ]

        # Sweep duration='end_of_turn' interceptors out of state.interceptors.
        to_remove = [
            iid for iid, ic in self.state.interceptors.items()
            if isinstance(getattr(ic, "duration", None), str)
            and ic.duration.strip().lower().replace(" ", "_") in eot_aliases
        ]
        for iid in to_remove:
            ic = self.state.interceptors.pop(iid, None)
            if ic is not None:
                src = self.state.objects.get(getattr(ic, "source", None))
                if src is not None and iid in src.interceptor_ids:
                    src.interceptor_ids.remove(iid)

    # =====================================================================
    # Action-loop dispatch
    # =====================================================================

    async def _run_action_loop(
        self,
        game,
        player_id: str,
        *,
        end_action: str,
        phase_label: str,
    ) -> list[Event]:
        """Drive AI / human action selection until the player ends the phase."""
        events: list[Event] = []
        if game is None:
            return events

        is_ai = self._is_ai_player(player_id)
        ai = self._ai_handler(game, player_id)
        method_name = (
            "choose_maneuver_action" if phase_label == "maneuver"
            else "choose_regroup_action"
        )

        for _ in range(_ACTION_LOOP_CAP):
            if self._game_over(game):
                break

            if is_ai and ai is not None:
                action = await self._maybe_await(
                    self._call_ai(ai, method_name, self.state, player_id)
                )
            elif self.human_action_handler is not None:
                action = await self.human_action_handler(player_id, self.state)
            else:
                # No handler available — silently end the phase.
                break

            if action is None:
                break

            action_type = action.get("action_type")
            if action_type == end_action or action_type in ("DEPTHS_END_TURN", "END_PHASE"):
                break

            ok, _msg, action_events = await self.execute_action(player_id, action)
            if action_events:
                events.extend(action_events)
            self._check_sba(game)
            if self._game_over(game):
                break

        return events

    async def execute_action(self, player_id: str, action: dict) -> tuple[bool, str, list[Event]]:
        """Dispatch a single Depths action.

        Action handlers live in ``src.engine.depths`` (Agent 1). This method
        looks up the handler by name and forwards positional/keyword args
        from the action dict. Unknown action types return
        ``(False, "Unknown Depths action", [])``.
        """
        game = getattr(self.state, "_game", None)
        if game is None:
            return False, "Game not attached", []

        depths = _import_depths_module()
        if depths is None:
            return False, "src.engine.depths is not yet available", []

        action_type = action.get("action_type")

        # Dispatch table maps action type → (function name on depths module,
        # kwargs builder). The kwargs builder pulls the right keys off the
        # action dict so each handler can have a stable signature.
        # Action-dict keys come from one of two producers: the canonical
        # turn-manager schema or the AI-adapter dataclass-to-dict converter
        # in tests. We accept either shape via fallback lookups.
        def _target_list(a: dict) -> list:
            if a.get("targets"):
                return list(a.get("targets") or [])
            tgt = a.get("target")
            return [tgt] if tgt is not None else []

        dispatch = {
            ACTION_CAST_SPELL: ("cast_spell", lambda a: {
                "card_id": a.get("card_id"),
                "targets": _target_list(a),
                "modes": a.get("modes") or [],
            }),
            ACTION_DEPLOY_VESSEL: ("deploy_vessel", lambda a: {
                "card_id": a.get("card_id"),
                "depth_band": a.get("depth_band"),
            }),
            ACTION_ATTACH: ("attach", lambda a: {
                "attachment_id": (a.get("attachment_id") or a.get("source_id")
                                  or a.get("card_id")),
                "target_id": a.get("target_id"),
            }),
            ACTION_DIVE: ("dive_vessel", lambda a: {
                "vessel_id": a.get("vessel_id") or a.get("source_id"),
            }),
            ACTION_SURFACE_VESSEL: ("surface_vessel", lambda a: {
                "vessel_id": a.get("vessel_id") or a.get("source_id"),
            }),
            ACTION_LAY_MINE: ("lay_mine", lambda a: {
                "card_id": a.get("card_id"),
                "depth_band": a.get("depth_band"),
            }),
            ACTION_ACTIVATE_ABILITY: ("activate_ability", lambda a: {
                "source_id": a.get("source_id") or a.get("vessel_id"),
                "ability_index": a.get("ability_index", a.get("ability_idx", 0)),
                "targets": _target_list(a),
            }),
        }

        if action_type not in dispatch:
            return False, "Unknown Depths action", []

        fn_name, kwarg_builder = dispatch[action_type]
        fn = getattr(depths, fn_name, None)
        if fn is None:
            return False, f"src.engine.depths.{fn_name} not implemented yet", []

        try:
            result = fn(game, player_id, **kwarg_builder(action))
        except TypeError as exc:
            return False, f"{fn_name}: {exc}", []

        # Allow handlers to be either ``(ok, message, events)`` triplets
        # (preferred — matches Minecraft) or just a list of events.
        if isinstance(result, tuple) and len(result) == 3:
            return result
        if isinstance(result, list):
            return True, "", result
        return True, "", []

    # =====================================================================
    # State-based actions & loss checks
    # =====================================================================

    def _check_sba(self, game) -> None:
        """Sink Vessels with ``damage >= hull``, then check loss conditions."""
        if game is None:
            return

        # 1. Sink any Vessel where damage exceeds hull.
        battlefield = self.state.zones.get("battlefield")
        if battlefield:
            for obj_id in list(battlefield.objects):
                obj = self.state.objects.get(obj_id)
                if not obj or obj.zone != ZoneType.BATTLEFIELD:
                    continue
                if not self._is_vessel(obj):
                    continue
                hull = self._vessel_hull(obj)
                damage = getattr(obj.state, "damage", 0) or 0
                if hull is not None and damage >= hull:
                    death = Event(
                        type=EventType.OBJECT_DESTROYED,
                        payload={"object_id": obj_id, "reason": "sunk"},
                    )
                    if (pipeline := self._emit_pipeline):
                        pipeline.emit(death)

        # 2. Loss conditions via Agent 1's adapter (per-player bool check).
        adapter_cls = self._adapter_class()
        adapter_instance = None
        if adapter_cls is not None:
            try:
                adapter_instance = adapter_cls()
            except Exception:
                adapter_instance = None

        for player in list(self.state.players.values()):
            if player.has_lost:
                continue

            lost = False
            reason = "depths_loss"

            # Try the adapter's ``check_loss(player, state)`` first.
            if adapter_instance is not None:
                check = getattr(adapter_instance, "check_loss", None)
                if callable(check):
                    try:
                        lost = bool(check(player, self.state))
                    except Exception:
                        lost = False

            # Inline fallback: Flagship sunk OR scuttle-loss.
            if not lost:
                if self._flagship_sunk(player):
                    lost = True
                    reason = "flagship_sunk"
                elif self._scuttle_loss(player):
                    lost = True
                    reason = "scuttle_loss"

            if lost:
                player.has_lost = True
                ev = Event(
                    type=EventType.PLAYER_LOSES,
                    payload={"player": player.id, "reason": reason},
                )
                if (pipeline := self._emit_pipeline):
                    pipeline.emit(ev)

    def _flagship_sunk(self, player: Player) -> bool:
        """True if the player's Flagship has been destroyed (battlefield-absent)."""
        flagship_id = (
            getattr(player, "depths_flagship_id", None)
            or getattr(player, "flagship_id", None)
        )
        if not flagship_id:
            return False
        obj = self.state.objects.get(flagship_id)
        if obj is None:
            return True
        if obj.zone != ZoneType.BATTLEFIELD:
            return True
        # If the Flagship's hull is exhausted but it hasn't been moved yet
        # (e.g. mid-event), call it sunk.
        hull = self._vessel_hull(obj)
        damage = getattr(obj.state, "damage", 0) or 0
        return hull is not None and damage >= hull

    def _scuttle_loss(self, player: Player) -> bool:
        """True if the player has no Vessels on board AND no Vessels in hand+library."""
        # Battlefield Vessels (excluding sunk).
        battlefield = self.state.zones.get("battlefield")
        if battlefield:
            for obj_id in battlefield.objects:
                obj = self.state.objects.get(obj_id)
                if (
                    obj
                    and obj.controller == player.id
                    and obj.zone == ZoneType.BATTLEFIELD
                    and self._is_vessel(obj)
                ):
                    return False
        # Hand Vessels.
        hand = self.state.zones.get(f"hand_{player.id}")
        if hand:
            for obj_id in hand.objects:
                obj = self.state.objects.get(obj_id)
                if obj and self._is_vessel(obj):
                    return False
        # Library Vessels.
        lib = self.state.zones.get(f"library_{player.id}")
        if lib:
            for obj_id in lib.objects:
                obj = self.state.objects.get(obj_id)
                if obj and self._is_vessel(obj):
                    return False
        return True

    # =====================================================================
    # SURFACE-phase helpers
    # =====================================================================

    async def _discard_to_hand_limit(self, game, player_id: str) -> list[Event]:
        events: list[Event] = []
        hand = self.state.zones.get(f"hand_{player_id}")
        if hand is None:
            return events
        limit = self._hand_limit()
        excess = len(hand.objects) - limit
        if excess <= 0:
            return events

        # Ask the AI / human which cards to discard.
        ai = self._ai_handler(game, player_id)
        chosen: list[str] = []
        if self._is_ai_player(player_id) and ai is not None:
            chosen = await self._maybe_await(
                self._call_ai(ai, "choose_discards", self.state, player_id, excess)
            ) or []
        elif self.human_action_handler is not None:
            # Simple convention: human handler returns a discard action when
            # asked. Implementations may instead block on user input.
            action = await self.human_action_handler(player_id, self.state)
            if action and action.get("action_type") == "DEPTHS_DISCARD":
                chosen = list(action.get("card_ids") or [])

        # If the AI under-supplied, top up by discarding the rightmost cards.
        if len(chosen) < excess:
            for oid in reversed(hand.objects):
                if oid not in chosen:
                    chosen.append(oid)
                if len(chosen) >= excess:
                    break

        for card_id in chosen[:excess]:
            zc = Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    "object_id": card_id,
                    "from_zone": f"hand_{player_id}",
                    "from_zone_type": ZoneType.HAND,
                    "to_zone": f"graveyard_{player_id}",
                    "to_zone_type": ZoneType.GRAVEYARD,
                    "reason": "depths_hand_limit_discard",
                },
                source=card_id,
            )
            if (pipeline := self._emit_pipeline):
                pipeline.emit(zc)
            events.append(zc)

        return events

    def _oxygen_tick(self, player_id: str) -> list[Event]:
        """Emit DEPTHS_OXYGEN_TICK; tick down counters on submerged Vessels.

        Per the design doc, "submerged" = depth band DEEP or CRUSH. Vessels
        with an oxygen counter lose 1 per tick; if they hit 0 they sink. For
        Vessels with no oxygen counter this is a no-op so future cards can
        hook the event without disturbing today's deck.
        """
        events: list[Event] = []
        battlefield = self.state.zones.get("battlefield")
        if not battlefield:
            return events

        submerged_bands = {"DEEP", "CRUSH"}
        ticked: list[str] = []
        sunk: list[str] = []

        for obj_id in list(battlefield.objects):
            obj = self.state.objects.get(obj_id)
            if not obj or obj.controller != player_id or not self._is_vessel(obj):
                continue
            depth = getattr(obj.state, "depth_band", None)
            if depth is None:
                continue
            depth_name = getattr(depth, "name", str(depth)).upper()
            if depth_name not in submerged_bands:
                continue

            ticked.append(obj_id)
            oxygen = getattr(obj.state, "oxygen", None)
            if oxygen is None:
                continue
            try:
                oxygen_int = int(oxygen)
            except (TypeError, ValueError):
                continue
            if oxygen_int <= 0:
                continue
            new_oxygen = oxygen_int - 1
            obj.state.oxygen = new_oxygen
            if new_oxygen <= 0:
                sunk.append(obj_id)

        # Emit a single batch event so triggers can hook it once.
        tick = Event(
            type=_resolve_event_type("DEPTHS_OXYGEN_TICK"),
            payload={
                "player": player_id,
                "vessel_ids": ticked,
            },
        )
        if (pipeline := self._emit_pipeline):
            pipeline.emit(tick)
        events.append(tick)

        # Sink Vessels that hit 0 oxygen.
        for obj_id in sunk:
            death = Event(
                type=EventType.OBJECT_DESTROYED,
                payload={"object_id": obj_id, "reason": "oxygen"},
            )
            if (pipeline := self._emit_pipeline):
                pipeline.emit(death)
            events.append(death)

        return events

    # =====================================================================
    # Adapter-bridge helpers
    # =====================================================================

    def _opening_hand_size(self) -> int:
        depths = _import_depths_module()
        if depths is not None:
            # Agent 1 publishes a module constant.
            const = getattr(depths, "OPENING_HAND_SIZE", None)
            if isinstance(const, int) and const > 0:
                return const
        gs_val = getattr(self.state, "opening_hand_size", None)
        if isinstance(gs_val, int) and gs_val > 0:
            return gs_val
        return _DEFAULT_OPENING_HAND

    def _hand_limit(self) -> int:
        """Return the hand-size limit for SURFACE-phase discard.

        Prefers Agent 1's ``DepthsModeAdapter.hand_size_limit(player, state)``,
        then ``HAND_SIZE_LIMIT`` constant, then GameState, then default 8.
        """
        depths = _import_depths_module()
        if depths is not None:
            # Try the module-level constant first (cheap & sufficient).
            const = getattr(depths, "HAND_SIZE_LIMIT", None)
            if isinstance(const, int) and const > 0:
                return const
            # Fall back to the adapter class's instance method.
            adapter_cls = self._adapter_class()
            if adapter_cls is not None:
                try:
                    inst = adapter_cls()
                    fn = getattr(inst, "hand_size_limit", None)
                    if callable(fn):
                        # The adapter signature is ``(player, state)`` but
                        # the answer is per-game, not per-player. Pass any
                        # player as a placeholder.
                        any_player = next(iter(self.state.players.values()), None)
                        if any_player is not None:
                            return int(fn(any_player, self.state))
                except Exception:
                    pass
        gs_val = getattr(self.state, "max_hand_size", None)
        if isinstance(gs_val, int) and gs_val > 0:
            return gs_val
        return _DEFAULT_HAND_LIMIT

    def _cap_for_turn(self, turn_number: int) -> int:
        """Per-pool charge cap for the given turn number."""
        depths = _import_depths_module()
        if depths is not None:
            # Agent 1 puts cap_for_turn on DepthsChargeSystem.
            charge_cls = getattr(depths, "DepthsChargeSystem", None)
            cap_fn = getattr(charge_cls, "cap_for_turn", None) if charge_cls else None
            if callable(cap_fn):
                try:
                    return int(cap_fn(turn_number))
                except Exception:
                    pass
            # Module-level fallback.
            module_fn = getattr(depths, "cap_for_turn", None)
            if callable(module_fn):
                try:
                    return int(module_fn(turn_number))
                except Exception:
                    pass
            max_cap = getattr(depths, "MAX_CHARGE_CAP", 10)
            return max(0, min(int(turn_number or 0), int(max_cap)))
        # Fallback: design-doc formula min(turn, 10).
        return max(0, min(int(turn_number or 0), 10))

    def _adapter_class(self):
        """Return the ``DepthsModeAdapter`` class (built lazily by Agent 1)."""
        depths = _import_depths_module()
        if depths is None:
            return None
        # Agent 1 currently exposes the class via a builder (the registration
        # path goes through mode_adapter). Try both shapes.
        cls = getattr(depths, "DepthsModeAdapter", None)
        if cls is not None:
            return cls
        builder = getattr(depths, "_depths_mode_adapter_class", None)
        if callable(builder):
            try:
                return builder()
            except Exception:
                return None
        return None

    def _is_vessel(self, obj) -> bool:
        """Vessel check; defers to Agent 1's ``depths.is_vessel`` if present."""
        if obj is None:
            return False
        depths = _import_depths_module()
        if depths is not None and hasattr(depths, "is_vessel"):
            try:
                return bool(depths.is_vessel(obj))
            except Exception:
                pass
        # Direct flag (cheapest).
        if getattr(obj.state, "is_vessel", False):
            return True
        # Card-type enum check.
        try:
            from .types import CardType
            depths_vessel = getattr(CardType, "DEPTHS_VESSEL", None)
            if depths_vessel is not None and obj.characteristics:
                if depths_vessel in obj.characteristics.types:
                    return True
        except Exception:
            pass
        # Subtype fallback.
        if obj.characteristics and obj.characteristics.subtypes:
            for sub in obj.characteristics.subtypes:
                if sub in {"Submarine", "Destroyer", "Carrier", "Drone", "Flagship"}:
                    return True
        return False

    def _vessel_hull(self, obj) -> Optional[int]:
        """Return the Vessel's current hull (toughness) if known."""
        if obj is None or obj.characteristics is None:
            return None
        # ``hull`` is the Depths name; mirror MTG ``toughness`` if the engine
        # reuses that field (Agent 1 may overlay).
        for attr in ("hull", "toughness"):
            val = getattr(obj.characteristics, attr, None)
            if val is not None:
                try:
                    return int(val)
                except (TypeError, ValueError):
                    return None
        return None

    def _other_player(self, player_id: str) -> Optional[str]:
        for pid in self.turn_order:
            if pid != player_id:
                return pid
        for pid in self.state.players:
            if pid != player_id:
                return pid
        return None

    def _get_combat_mgr(self, game):
        """Lazily build (and cache) a ``DepthsCombatManager`` for this game."""
        if self._combat_mgr is not None:
            return self._combat_mgr
        combat_mod = _import_combat_module()
        if combat_mod is None:
            return None
        mgr_cls = getattr(combat_mod, "DepthsCombatManager", None)
        if mgr_cls is None:
            return None
        # Try (state, game) → (state) → () in that order; we don't know
        # Agent 2's chosen signature until they land the file.
        for args in ((self.state, game), (self.state,), ()):
            try:
                self._combat_mgr = mgr_cls(*args)
                break
            except TypeError:
                continue
            except Exception:
                continue
        return self._combat_mgr

    def _invoke_combat(self, mgr, method_name: str, *args) -> list[Event]:
        """Call a method on the combat manager; tolerate sync/async returns."""
        method = getattr(mgr, method_name, None)
        if method is None:
            return []
        try:
            result = method(*args)
        except TypeError as exc:
            # Try without trailing args in case Agent 2's signature is shorter.
            try:
                result = method(args[0]) if args else method()
            except Exception:
                return []
        if inspect.isawaitable(result):
            # We're already inside an async function but want to keep
            # this helper sync for symmetry; callers that need the
            # awaited value can wrap with `await self._maybe_await(...)`.
            # Returning the awaitable is fine because _invoke_combat is
            # only called inline below; we await its result via
            # ``events.extend(...)`` when sync, and explicitly await when
            # used elsewhere. But to keep the call sites simple, resolve
            # sync results here and synchronously await async ones via
            # asyncio.run-equivalent isn't safe — so treat awaitables
            # as opaque and return [] for now.
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, tuple) and len(result) == 3:
            # (ok, msg, events) triple style.
            return result[2] if isinstance(result[2], list) else []
        return []

    def _call_ai(self, handler, method_name: str, *args):
        """Look up a handler method and invoke it with ``args``.

        Returns the call result (which may be a coroutine — caller awaits
        via ``_maybe_await``). Returns ``None`` if the handler or method
        is missing.
        """
        if handler is None:
            return None
        method = getattr(handler, method_name, None)
        if method is None:
            return None
        try:
            return method(*args)
        except TypeError:
            # Try a (state, player_id) two-arg signature as a fallback.
            try:
                return method(args[0], args[1]) if len(args) >= 2 else method(*args)
            except Exception:
                return None

    @staticmethod
    async def _maybe_await(value):
        if inspect.isawaitable(value):
            return await value
        return value

    # =====================================================================
    # Phase-event helper
    # =====================================================================
    def _emit_phase(self, phase: str, kind: str, player_id: str) -> list[Event]:
        """Emit ``PHASE_START`` or ``PHASE_END`` and return ``[event]``."""
        ev_type = EventType.PHASE_START if kind == "start" else EventType.PHASE_END
        ev = Event(
            type=ev_type,
            payload={"phase": phase, "player": player_id},
        )
        if (pipeline := self._emit_pipeline):
            pipeline.emit(ev)
        return [ev]

    # =====================================================================
    # Game-over helper
    # =====================================================================
    def _game_over(self, game) -> bool:
        if game is not None and hasattr(game, "is_game_over"):
            try:
                return bool(game.is_game_over())
            except Exception:
                pass
        alive = [p for p in self.state.players.values() if not p.has_lost]
        return len(alive) <= 1

    # =====================================================================
    # MTG-compat overrides (no-ops for Depths)
    # =====================================================================
    async def _run_beginning_phase(self) -> list[Event]:
        return []

    async def _run_main_phase(self, *_, **__) -> list[Event]:
        return []

    async def _run_combat_phase(self) -> list[Event]:
        return []

    async def _run_ending_phase(self) -> list[Event]:
        return []
