"""
Depths Combat Manager

Combat phase manager for the submarine-fleet card game ``depths``.
See ``docs/games/depths.md`` section 5 for the design.

Pipeline:
    declare_attackers -> resolve_detection -> declare_interceptors -> assign_damage

Key submarine-warfare twist:
    * ``detected`` flag on each Vessel gates targeting by interceptors. Undetected
      attackers still deal damage but cannot be intercepted.
    * Damage between firer and target is reduced by the depth-band difference
      (min 1). The ``homing`` keyword skips the modifier. The reduction is
      implemented as a TRANSFORM-priority interceptor on ``DAMAGE`` events so
      card scripts can hook the same point.

Ownership:
    Owns ONLY this file. The DepthBand enum, ``depth_difference``, ``is_vessel``,
    and ``vessels_at_depth`` come from ``src.engine.depths`` (Agent 1). If those
    symbols aren't present at import time we fall back to module-local
    definitions so this file can be loaded standalone for tests.

Imports expected from ``src.engine.depths``:
    * ``DepthBand`` enum with members SURFACE, PERISCOPE, MID, DEEP, CRUSH
      (in shallow-to-deep order, typically with ``.value`` 0..4).
    * ``depth_difference(a: DepthBand, b: DepthBand) -> int`` — absolute band
      separation.
    * ``is_vessel(obj: GameObject) -> bool`` — whether ``obj`` is a Depths Vessel
      (covers Submarine, Destroyer, Carrier, Drone, Flagship subtypes).
    * ``vessels_at_depth(player_id: str, band: DepthBand, state: GameState)
      -> list[GameObject]`` — query.

If Agent 1 ships those names verbatim everything just works. If the names
differ, the import block has a single try/except and concrete fallbacks so the
reconciliation step is mechanical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING

from .types import (
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    ZoneType,
    new_id,
)
from .queries import get_power, has_ability

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Imports from Agent 1's depths.py — wrapped in try/except so this module can
# be loaded before depths.py exists. The fallbacks are minimal stand-ins that
# match the design doc's contract; they will be replaced at runtime by the
# real symbols once depths.py is on the import path.
# ---------------------------------------------------------------------------

try:
    from .depths import (  # type: ignore
        DepthBand,
        depth_difference,
        is_vessel,
        vessels_at_depth,
    )
    _USING_DEPTHS_FALLBACK = False
except Exception:  # pragma: no cover - fallback only used pre-Agent-1
    _USING_DEPTHS_FALLBACK = True

    class DepthBand(Enum):  # type: ignore[no-redef]
        SURFACE = 0
        PERISCOPE = 1
        MID = 2
        DEEP = 3
        CRUSH = 4

    def depth_difference(a: "DepthBand", b: "DepthBand") -> int:  # type: ignore[no-redef]
        return abs(int(a.value) - int(b.value))

    def is_vessel(obj: GameObject) -> bool:  # type: ignore[no-redef]
        # Best-effort fallback: anything tagged with a Vessel subtype or a
        # depth_band on its state. Agent 1's real implementation should
        # check ``CardType.DEPTHS_VESSEL`` properly.
        if obj is None:
            return False
        if getattr(obj.state, "depth_band", None) is not None:
            return True
        subtypes = getattr(obj.characteristics, "subtypes", set()) or set()
        vessel_subs = {"Submarine", "Destroyer", "Carrier", "Drone", "Flagship"}
        return bool(set(subtypes) & vessel_subs)

    def vessels_at_depth(  # type: ignore[no-redef]
        player_id: str,
        band: "DepthBand",
        state: GameState,
    ) -> list[GameObject]:
        battlefield = state.zones.get("battlefield")
        if not battlefield:
            return []
        out: list[GameObject] = []
        for oid in battlefield.objects:
            obj = state.objects.get(oid)
            if not obj or obj.controller != player_id:
                continue
            if not is_vessel(obj):
                continue
            if getattr(obj.state, "depth_band", None) != band:
                continue
            out.append(obj)
        return out


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AttackerSpec:
    """A single attacker declaration.

    ``firing_depth_band`` is the band the vessel is firing from (usually its
    own current depth, but a card could shift firing depth temporarily). Used
    for the depth-modifier math. ``target_id`` is either an opposing Vessel
    object id or the opponent's Flagship id.
    """

    vessel_id: str
    target_id: str
    firing_depth_band: "DepthBand"


@dataclass
class BlockerSpec:
    """A 1:1 interceptor declaration."""

    interceptor_id: str
    attacker_id: str


@dataclass
class _DepthsCombatState:
    """Internal book-keeping for one combat phase."""

    attackers: list[AttackerSpec] = field(default_factory=list)
    interceptors: list[BlockerSpec] = field(default_factory=list)
    intercepted_by: dict[str, str] = field(default_factory=dict)  # attacker_id -> interceptor_id
    detection_attempts: dict[str, bool] = field(default_factory=dict)  # attacker_id -> detected_now


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# How much it costs in Sonar Charges to detect at each depth, BEFORE keyword
# adjustments. Linear with depth.
DETECTION_DIFFICULTY: dict["DepthBand", int] = {
    DepthBand.SURFACE: 0,
    DepthBand.PERISCOPE: 1,
    DepthBand.MID: 1,
    DepthBand.DEEP: 2,
    DepthBand.CRUSH: 3,
}


# Maximum interceptor reach (in bands of separation between attacker's TARGET
# depth and the interceptor's depth). The ``reach`` keyword bumps this to 2.
DEFAULT_INTERCEPT_RANGE = 1
REACH_INTERCEPT_RANGE = 2


# Minimum damage after depth modifier reduction.
MIN_DAMAGE_AFTER_MODIFIER = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_detected(vessel: GameObject) -> bool:
    """Return True if ``vessel`` is currently detected.

    Default-safe: missing ``detected`` flag is treated as False (undetected).
    """

    if vessel is None:
        return False
    return bool(getattr(vessel.state, "detected", False))


def _vessel_depth(vessel: GameObject) -> Optional["DepthBand"]:
    """Return the vessel's current depth band, or None if not set."""

    if vessel is None:
        return None
    return getattr(vessel.state, "depth_band", None)


def _vessel_charges(state: GameState, player_id: str, kind: str) -> int:
    """Return the player's current charge pool for ``kind`` ('tc' or 'sc').

    Reads from the standard locations Agent 1's ``DepthsChargeSystem`` is
    expected to use. Falls back to 0 when the value isn't present so this
    helper is safe before the resource system is wired.
    """

    player = state.players.get(player_id)
    if player is None:
        return 0
    # Try direct attribute first
    val = getattr(player, kind, None)
    if isinstance(val, int):
        return val
    # Try a ``depths_charges`` dict (alternative shape Agent 1 might use)
    pool = getattr(player, "depths_charges", None)
    if isinstance(pool, dict):
        return int(pool.get(kind, 0))
    return 0


def _spend_charges(state: GameState, player_id: str, kind: str, amount: int) -> bool:
    """Best-effort charge spend. Returns True on success, False if player can't pay.

    Mirrors ``_vessel_charges`` shape expectations.
    """

    if amount <= 0:
        return True
    player = state.players.get(player_id)
    if player is None:
        return False
    val = getattr(player, kind, None)
    if isinstance(val, int):
        if val < amount:
            return False
        setattr(player, kind, val - amount)
        return True
    pool = getattr(player, "depths_charges", None)
    if isinstance(pool, dict):
        cur = int(pool.get(kind, 0))
        if cur < amount:
            return False
        pool[kind] = cur - amount
        return True
    # No resource system wired yet. Treat the spend as free in dev-mode so
    # combat logic can still be exercised by tests; flag via a turn_data
    # marker so tests can detect when the fallback was used.
    state.turn_data["depths_charge_spend_unwired"] = True
    return True


def detection_cost(vessel: GameObject, state: GameState) -> int:
    """Sonar Charges needed to detect ``vessel`` right now.

    ``1 + depth_difficulty(depth_band) + (1 if silent_running else 0)``.
    Already-detected vessels return 0 (no point detecting twice).
    """

    if vessel is None:
        return 0
    if is_detected(vessel):
        return 0
    band = _vessel_depth(vessel)
    if band is None:
        difficulty = 0
    else:
        difficulty = DETECTION_DIFFICULTY.get(band, 0)
    cost = 1 + int(difficulty)
    if has_ability(vessel, "silent_running", state):
        cost += 1
    return cost


def mark_detected(
    vessel: GameObject,
    state: GameState,
    *,
    duration: str = "until_end_of_turn",
) -> None:
    """Flag a vessel as detected.

    The duration string is read by Agent 1's Sonar Decay step (run at SURFACE
    phase end) to clean up. ``"until_end_of_turn"`` is the default — it expires
    at the end of the turn the detection was made.
    """

    if vessel is None:
        return
    vessel.state.detected = True
    # Stash duration on the object's state so the cleanup pass can read it.
    # Stored as a dict so multiple detections (e.g. permanent + EOT) can
    # coexist; Agent 1 just needs to inspect ``detected_durations``.
    durations = getattr(vessel.state, "detected_durations", None)
    if durations is None:
        durations = []
        vessel.state.detected_durations = durations
    if duration not in durations:
        durations.append(duration)


def legal_targets_for(vessel: GameObject, state: GameState) -> list[str]:
    """Return target ids ``vessel`` can legally fire at right now.

    Includes:
        * opposing Vessels at any depth (depth-modifier handles reach falloff)
        * the opponent's Flagship id

    Excludes:
        * own permanents
        * non-Vessels (Mines etc. — Mines auto-trigger, not targeted)
        * Vessels in non-battlefield zones

    Agent 4 (the AI) calls this to enumerate candidate attacks.
    """

    if vessel is None:
        return []
    own_pid = vessel.controller
    targets: list[str] = []
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return targets
    for oid in battlefield.objects:
        obj = state.objects.get(oid)
        if not obj:
            continue
        if obj.controller == own_pid:
            continue
        if not is_vessel(obj):
            continue
        targets.append(oid)
    return targets


def can_intercept(
    interceptor: GameObject,
    attacker_spec: AttackerSpec,
    state: GameState,
) -> bool:
    """Validation predicate for an interceptor declaration.

    Rules:
        * attacker must be currently detected
        * interceptor must be untapped, not summoning sick (haste exempt)
        * interceptor depth must be within max-range of the attacker's TARGET
          depth (not firing depth — interceptors guard the target's location).
          Range is 1 by default, 2 with the ``reach`` keyword.
    """

    if interceptor is None:
        return False
    if interceptor.zone != ZoneType.BATTLEFIELD:
        return False
    if interceptor.state.tapped:
        return False
    if interceptor.state.summoning_sickness and not has_ability(
        interceptor, "haste", state
    ):
        return False

    attacker = state.objects.get(attacker_spec.vessel_id)
    if attacker is None or not is_detected(attacker):
        return False

    target = state.objects.get(attacker_spec.target_id)
    target_band = _vessel_depth(target) if target else None
    interceptor_band = _vessel_depth(interceptor)
    if target_band is None or interceptor_band is None:
        return False

    diff = depth_difference(target_band, interceptor_band)
    max_range = (
        REACH_INTERCEPT_RANGE
        if has_ability(interceptor, "reach", state)
        else DEFAULT_INTERCEPT_RANGE
    )
    return diff <= max_range


# ---------------------------------------------------------------------------
# Damage modifier interceptor (TRANSFORM priority)
# ---------------------------------------------------------------------------

DEPTHS_DAMAGE_MODIFIER_TAG = "_depths_depth_modifier_applied"


def _damage_modifier_filter(event: Event, state: GameState) -> bool:
    if event.type != EventType.DAMAGE:
        return False
    if event.payload.get(DEPTHS_DAMAGE_MODIFIER_TAG):
        return False
    # Only modify combat damage; non-combat (mine triggers, ability damage)
    # carries their own depth flag if the card wants the modifier applied.
    if not event.payload.get("is_combat") and not event.payload.get(
        "depths_combat", False
    ):
        return False
    src_id = event.source or event.payload.get("source")
    target_id = event.payload.get("target")
    if not src_id or not target_id:
        return False
    src = state.objects.get(src_id)
    tgt = state.objects.get(target_id)
    if src is None or tgt is None:
        return False
    if not is_vessel(src) or not is_vessel(tgt):
        return False
    return True


def _damage_modifier_handler(event: Event, state: GameState) -> InterceptorResult:
    """Reduce DAMAGE.amount by depth-band difference between source and target.

    Skipped when the source has the ``homing`` keyword OR when the payload
    explicitly opts out via ``payload['source_keyword_homing'] == True``.
    """

    src_id = event.source or event.payload.get("source")
    target_id = event.payload.get("target")
    src = state.objects.get(src_id) if src_id else None
    tgt = state.objects.get(target_id) if target_id else None
    if src is None or tgt is None:
        return InterceptorResult(action=InterceptorAction.PASS)

    # Homing skip — either explicit payload flag or actual keyword.
    # NOTE: We check the source object's printed keywords directly rather than
    # calling has_ability() here. has_ability() consults QUERY interceptors from
    # state.interceptors without zone-gating, so a keyword-grant card sitting in
    # the LIBRARY (e.g. Fleet Admiral Yamamoto's homing grant to all Drones) can
    # cause unrelated combat attackers to be treated as homing. The depth modifier
    # should only honour keywords that are currently active on the battlefield —
    # i.e., either printed on the attacker or granted by a *battlefield* permanent.
    # Battlefield-based grants DO update characteristics.keywords via static
    # interceptors that run through the gated pipeline, so reading printed keywords
    # is the correct zone-safe check. (iter-9 bug fix)
    src_has_homing = (
        event.payload.get("source_keyword_homing")
        or "homing" in (src.characteristics.keywords or set())
    )
    if src_has_homing:
        # Mark as processed so we don't re-enter on the modified copy.
        new_payload = dict(event.payload)
        new_payload[DEPTHS_DAMAGE_MODIFIER_TAG] = True
        new_event = Event(
            type=event.type,
            payload=new_payload,
            source=event.source,
            controller=event.controller,
            status=event.status,
            timestamp=event.timestamp,
        )
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    # Use firing_depth_band from payload if provided (declared during combat),
    # else fall back to the source vessel's current depth.
    firing_band = event.payload.get("firing_depth_band") or _vessel_depth(src)
    target_band = _vessel_depth(tgt)
    if firing_band is None or target_band is None:
        return InterceptorResult(action=InterceptorAction.PASS)

    diff = depth_difference(firing_band, target_band)
    if diff <= 0:
        # Mark and pass through unchanged.
        new_payload = dict(event.payload)
        new_payload[DEPTHS_DAMAGE_MODIFIER_TAG] = True
        new_event = Event(
            type=event.type,
            payload=new_payload,
            source=event.source,
            controller=event.controller,
            status=event.status,
            timestamp=event.timestamp,
        )
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    original_amount = int(event.payload.get("amount", 0) or 0)
    if original_amount <= 0:
        return InterceptorResult(action=InterceptorAction.PASS)

    reduced = max(MIN_DAMAGE_AFTER_MODIFIER, original_amount - diff)
    if reduced == original_amount:
        new_payload = dict(event.payload)
        new_payload[DEPTHS_DAMAGE_MODIFIER_TAG] = True
        new_event = Event(
            type=event.type,
            payload=new_payload,
            source=event.source,
            controller=event.controller,
            status=event.status,
            timestamp=event.timestamp,
        )
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    new_payload = dict(event.payload)
    new_payload["amount"] = reduced
    new_payload["original_amount"] = original_amount
    new_payload["depth_modifier_diff"] = diff
    new_payload[DEPTHS_DAMAGE_MODIFIER_TAG] = True
    new_event = Event(
        type=event.type,
        payload=new_payload,
        source=event.source,
        controller=event.controller,
        status=event.status,
        timestamp=event.timestamp,
    )
    return InterceptorResult(
        action=InterceptorAction.TRANSFORM,
        transformed_event=new_event,
    )


def install_depth_damage_modifier(state: GameState) -> Interceptor:
    """Register the system-level depth damage modifier on ``state``.

    Idempotent: returns the existing interceptor if one is already installed.
    Called once at game start by the turn manager (Agent 3) or whoever sets up
    a Depths game.
    """

    for existing in state.interceptors.values():
        if existing.source == "_depths_system_damage_modifier":
            return existing

    interceptor = Interceptor(
        id=new_id(),
        source="_depths_system_damage_modifier",
        controller="_system",
        priority=InterceptorPriority.TRANSFORM,
        filter=_damage_modifier_filter,
        handler=_damage_modifier_handler,
        timestamp=state.next_timestamp(),
        duration="forever",
    )
    state.interceptors[interceptor.id] = interceptor
    return interceptor


# ---------------------------------------------------------------------------
# DepthsCombatManager
# ---------------------------------------------------------------------------

class DepthsCombatManager:
    """Combat manager for the Depths game.

    Created once per game by Agent 3's turn manager. Call ``resolve_combat``
    once per ENGAGEMENT phase. The manager is stateful WITHIN a single combat;
    state is reset at the top of every ``resolve_combat`` call.

    All operations route through ``state._game.emit`` (the standard pipeline)
    when a Game reference is available so card interceptors can hook combat.
    """

    def __init__(self) -> None:
        self.combat: _DepthsCombatState = _DepthsCombatState()

    # ------------------------------------------------------------------ utils
    def _emit(self, state: GameState, event: Event) -> None:
        """Emit through the pipeline if available, else append to event_log."""

        game = getattr(state, "_game", None)
        if game is not None and hasattr(game, "emit"):
            game.emit(event)
        else:
            # Fallback for unit tests that don't construct a Game.
            state.event_log.append(event)

    def _ensure_modifier_installed(self, state: GameState) -> None:
        install_depth_damage_modifier(state)

    def reset(self) -> None:
        """Clear combat state. Idempotent."""

        self.combat = _DepthsCombatState()

    # ------------------------------------------------------------ declaration
    def declare_attackers(
        self,
        state: GameState,
        attacker_specs: list[AttackerSpec],
    ) -> tuple[bool, str, list[AttackerSpec]]:
        """Register attacks. Returns (ok, message, accepted_specs).

        Validates each spec; rejects illegal ones. Taps each accepted attacker
        and emits ``ATTACK_DECLARED``. The caller (turn manager) is responsible
        for choosing which player is attacking; we trust ``state.active_player``.
        """

        self._ensure_modifier_installed(state)
        accepted: list[AttackerSpec] = []
        for spec in attacker_specs or []:
            ok, _reason = self._validate_attacker(state, spec)
            if not ok:
                continue
            attacker = state.objects.get(spec.vessel_id)
            if attacker is None:
                continue
            attacker.state.tapped = True
            attacker.state.attacking = True
            accepted.append(spec)

            ev = Event(
                type=EventType.ATTACK_DECLARED,
                payload={
                    "attacker_id": spec.vessel_id,
                    "target_id": spec.target_id,
                    "firing_depth_band": spec.firing_depth_band,
                    "attacking_player": attacker.controller,
                    "is_depths": True,
                },
                source=spec.vessel_id,
                controller=attacker.controller,
            )
            self._emit(state, ev)

        self.combat.attackers = accepted
        if not accepted:
            return False, "No legal attackers", []
        return True, "Attackers declared", accepted

    def _validate_attacker(
        self,
        state: GameState,
        spec: AttackerSpec,
    ) -> tuple[bool, str]:
        attacker = state.objects.get(spec.vessel_id)
        if attacker is None:
            return False, "no such vessel"
        if attacker.zone != ZoneType.BATTLEFIELD:
            return False, "vessel not on battlefield"
        if not is_vessel(attacker):
            return False, "not a vessel"
        if attacker.state.tapped:
            return False, "vessel is tapped"
        if attacker.state.summoning_sickness and not has_ability(
            attacker, "haste", state
        ):
            return False, "summoning sick"
        if has_ability(attacker, "defender", state):
            return False, "defender keyword"

        # Firing depth must be ≤ vessel's actual depth (a vessel can fire from
        # shallower than where it sits, but cannot fire from deeper than it is).
        own_band = _vessel_depth(attacker)
        if own_band is None:
            return False, "no depth band"
        try:
            if int(spec.firing_depth_band.value) > int(own_band.value):
                return False, "firing depth deeper than vessel depth"
        except AttributeError:
            return False, "invalid depth band"

        # Target must exist & be legal.
        target = state.objects.get(spec.target_id)
        if target is None:
            return False, "no such target"
        if target.controller == attacker.controller:
            return False, "cannot target own permanent"
        if not is_vessel(target):
            return False, "target not a vessel"
        target_band = _vessel_depth(target)
        if target_band is None:
            return False, "target has no depth"

        return True, "ok"

    # ---------------------------------------------------------- detection
    def resolve_detection(
        self,
        state: GameState,
        defender_id: str,
        sonar_spends: dict[str, int],
    ) -> dict[str, bool]:
        """Spend Sonar Charges to detect attackers.

        ``sonar_spends`` maps attacker_id -> Sonar Charges committed. If the
        commitment >= ``detection_cost(attacker)`` the attacker is flipped to
        detected. Otherwise the spend is wasted (the design doc doesn't refund
        partial pings — that mirrors real ASW where a failed sweep still uses
        battery).

        Returns a map of attacker_id -> bool (whether it was detected this step).
        """

        results: dict[str, bool] = {}
        for spec in self.combat.attackers:
            attacker = state.objects.get(spec.vessel_id)
            if attacker is None:
                results[spec.vessel_id] = False
                continue
            if is_detected(attacker):
                results[spec.vessel_id] = True
                continue
            committed = int(sonar_spends.get(spec.vessel_id, 0) or 0)
            if committed <= 0:
                results[spec.vessel_id] = False
                continue
            cost = detection_cost(attacker, state)
            if committed < cost:
                # Failed ping — spend the sonar anyway, emit a fail marker.
                if not _spend_charges(state, defender_id, "sc", committed):
                    results[spec.vessel_id] = False
                    continue
                fail = Event(
                    type=self._optional_event_type(
                        "DEPTHS_DETECTION_FAIL", EventType.PRIORITY_PASS
                    ),
                    payload={
                        "defender": defender_id,
                        "attacker_id": spec.vessel_id,
                        "spent": committed,
                        "needed": cost,
                    },
                    source=spec.vessel_id,
                    controller=defender_id,
                )
                self._emit(state, fail)
                results[spec.vessel_id] = False
                continue
            # Successful detect: spend the charges, flip the flag, emit event.
            if not _spend_charges(state, defender_id, "sc", cost):
                results[spec.vessel_id] = False
                continue
            mark_detected(attacker, state, duration="until_end_of_turn")
            ev = Event(
                type=self._optional_event_type(
                    "DEPTHS_DETECT", EventType.PRIORITY_PASS
                ),
                payload={
                    "defender": defender_id,
                    "attacker_id": spec.vessel_id,
                    "cost_paid": cost,
                },
                source=spec.vessel_id,
                controller=defender_id,
            )
            self._emit(state, ev)
            results[spec.vessel_id] = True

        self.combat.detection_attempts = dict(results)
        return results

    @staticmethod
    def _optional_event_type(name: str, fallback: EventType) -> EventType:
        """Look up a Depths-specific EventType, fall back if missing.

        Agent 1 should add ``DEPTHS_DETECT`` etc. to the EventType enum. Until
        then we use ``PRIORITY_PASS`` as a benign sentinel (it's emitted often
        and ignored by most observers) so combat keeps flowing.
        """

        return getattr(EventType, name, fallback)

    # ---------------------------------------------------------- interceptors
    def declare_interceptors(
        self,
        state: GameState,
        blocker_specs: list[BlockerSpec],
    ) -> tuple[bool, str, list[BlockerSpec]]:
        """Register defender interceptions (1:1).

        Validates against ``can_intercept``. Each interceptor can only block
        one attacker; each attacker can only be intercepted once.
        """

        accepted: list[BlockerSpec] = []
        seen_interceptors: set[str] = set()
        seen_attackers: set[str] = set()
        attacker_lookup = {a.vessel_id: a for a in self.combat.attackers}

        for spec in blocker_specs or []:
            if spec.interceptor_id in seen_interceptors:
                continue
            if spec.attacker_id in seen_attackers:
                continue
            attacker_spec = attacker_lookup.get(spec.attacker_id)
            if attacker_spec is None:
                continue
            interceptor = state.objects.get(spec.interceptor_id)
            if not can_intercept(interceptor, attacker_spec, state):
                continue
            seen_interceptors.add(spec.interceptor_id)
            seen_attackers.add(spec.attacker_id)
            accepted.append(spec)
            interceptor.state.blocking = True
            ev = Event(
                type=EventType.BLOCK_DECLARED,
                payload={
                    "blocker_id": spec.interceptor_id,
                    "attacker_id": spec.attacker_id,
                    "is_depths": True,
                },
                source=spec.interceptor_id,
                controller=interceptor.controller,
            )
            self._emit(state, ev)

        self.combat.interceptors = accepted
        self.combat.intercepted_by = {
            spec.attacker_id: spec.interceptor_id for spec in accepted
        }
        return True, "Interceptors declared", accepted

    # ---------------------------------------------------------- damage
    def assign_damage(self, state: GameState) -> list[Event]:
        """Emit DAMAGE events for the current combat. Simultaneous resolution.

        Returns the (pre-pipeline) events emitted, in order, primarily for
        tests. The pipeline mutates payloads via the depth-modifier interceptor
        as they are emitted.
        """

        emitted: list[Event] = []
        for atk_spec in self.combat.attackers:
            attacker = state.objects.get(atk_spec.vessel_id)
            if attacker is None or attacker.zone != ZoneType.BATTLEFIELD:
                continue
            atk_power = int(get_power(attacker, state) or 0)
            if atk_power <= 0:
                continue

            interceptor_id = self.combat.intercepted_by.get(atk_spec.vessel_id)
            if interceptor_id is not None:
                interceptor = state.objects.get(interceptor_id)
                if interceptor is None or interceptor.zone != ZoneType.BATTLEFIELD:
                    interceptor = None

                if interceptor is not None:
                    int_power = int(get_power(interceptor, state) or 0)
                    # Attacker -> interceptor
                    if atk_power > 0:
                        ev = self._build_damage_event(
                            source=attacker,
                            target_id=interceptor.id,
                            amount=atk_power,
                            firing_band=atk_spec.firing_depth_band,
                        )
                        self._emit(state, ev)
                        emitted.append(ev)
                    # Interceptor -> attacker (interceptor fires from its own
                    # depth at the attacker's CURRENT depth)
                    if int_power > 0:
                        ev = self._build_damage_event(
                            source=interceptor,
                            target_id=attacker.id,
                            amount=int_power,
                            firing_band=_vessel_depth(interceptor),
                        )
                        self._emit(state, ev)
                        emitted.append(ev)
                    continue

            # Unintercepted (or interceptor vanished mid-combat) — hit declared
            # target.
            target_obj = state.objects.get(atk_spec.target_id)
            if target_obj is None:
                continue
            ev = self._build_damage_event(
                source=attacker,
                target_id=atk_spec.target_id,
                amount=atk_power,
                firing_band=atk_spec.firing_depth_band,
            )
            self._emit(state, ev)
            emitted.append(ev)

        # State-based: sink any vessels with damage >= hull. Damage persists.
        self._check_sink_state(state)
        return emitted

    def _build_damage_event(
        self,
        *,
        source: GameObject,
        target_id: str,
        amount: int,
        firing_band: Optional["DepthBand"],
    ) -> Event:
        payload: dict[str, Any] = {
            "target": target_id,
            "amount": int(amount),
            "source": source.id,
            "is_combat": True,
            "depths_combat": True,
        }
        if firing_band is not None:
            payload["firing_depth_band"] = firing_band
        # Note: homing is handled by the depth-modifier interceptor at
        # apply-time by reading the keyword from the source object. We do not
        # eagerly tag ``source_keyword_homing`` here because the keyword may
        # be granted/removed between event emission and pipeline transform;
        # callers that want to force-skip the modifier (e.g. a card that
        # grants "this damage ignores depth modifier just once") can set the
        # flag in the payload directly before emitting.

        return Event(
            type=EventType.DAMAGE,
            payload=payload,
            source=source.id,
            controller=source.controller,
        )

    def _check_sink_state(self, state: GameState) -> None:
        """Sink any Vessel whose damage >= hull. Damage persists across turns.

        Emits ``OBJECT_DESTROYED`` and ``ZONE_CHANGE`` events through the
        pipeline so existing handlers move the object to the graveyard. We
        intentionally do NOT clear ``state.damage`` — that's the headline
        difference vs MTG (sub damage doesn't heal at end of turn).
        """

        battlefield = state.zones.get("battlefield")
        if not battlefield:
            return

        sinking: list[str] = []
        for oid in list(battlefield.objects):
            obj = state.objects.get(oid)
            if obj is None or not is_vessel(obj):
                continue
            hull = obj.characteristics.toughness
            if hull is None:
                continue
            if int(obj.state.damage or 0) >= int(hull):
                sinking.append(oid)

        for oid in sinking:
            obj = state.objects.get(oid)
            if obj is None:
                continue
            destroyed = Event(
                type=EventType.OBJECT_DESTROYED,
                payload={
                    "object_id": oid,
                    "reason": "depths_sunk",
                    "last_damage_source": obj.state.last_damage_source,
                },
                source=obj.state.last_damage_source,
                controller=obj.controller,
            )
            self._emit(state, destroyed)
            zone_change = Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    "object_id": oid,
                    "from": "battlefield",
                    "to": "graveyard",
                    "reason": "depths_sunk",
                },
                source=obj.state.last_damage_source,
                controller=obj.controller,
            )
            self._emit(state, zone_change)

    # ---------------------------------------------------------- orchestration
    def resolve_combat(
        self,
        state: GameState,
        *,
        attacker_specs: Optional[list[AttackerSpec]] = None,
        sonar_spends: Optional[dict[str, int]] = None,
        blocker_specs: Optional[list[BlockerSpec]] = None,
    ) -> dict[str, Any]:
        """Run the full combat pipeline.

        Single-call interface used by Agent 3's turn manager when it has all
        decisions in hand (e.g. AI-vs-AI). For interactive UIs the manager
        also exposes the individual steps so callers can pause for player
        input between detection and interception.

        Returns a summary dict with the accepted specs and emitted damage events.
        """

        self.reset()
        self._ensure_modifier_installed(state)

        defender_id = self._derive_defender(state)

        ok, msg, accepted_attackers = self.declare_attackers(
            state, attacker_specs or []
        )
        if not ok:
            return {
                "ok": False,
                "message": msg,
                "attackers": [],
                "interceptors": [],
                "damage_events": [],
                "detected": {},
            }

        detected = self.resolve_detection(
            state, defender_id, sonar_spends or {}
        )
        _, _, accepted_blockers = self.declare_interceptors(
            state, blocker_specs or []
        )
        damage_events = self.assign_damage(state)

        # Clear per-combat flags on accepted attackers.
        for spec in accepted_attackers:
            obj = state.objects.get(spec.vessel_id)
            if obj is not None:
                obj.state.attacking = False
        for spec in accepted_blockers:
            obj = state.objects.get(spec.interceptor_id)
            if obj is not None:
                obj.state.blocking = False

        return {
            "ok": True,
            "message": "Combat resolved",
            "attackers": accepted_attackers,
            "interceptors": accepted_blockers,
            "damage_events": damage_events,
            "detected": detected,
        }

    def _derive_defender(self, state: GameState) -> str:
        active = state.active_player
        for pid, player in state.players.items():
            if pid == active:
                continue
            if not getattr(player, "has_lost", False):
                return pid
        # Singleton fallback (should never hit in normal play).
        for pid in state.players:
            if pid != active:
                return pid
        return active or ""


# ---------------------------------------------------------------------------
# __all__ — public surface
# ---------------------------------------------------------------------------

__all__ = [
    "AttackerSpec",
    "BlockerSpec",
    "DepthsCombatManager",
    "DETECTION_DIFFICULTY",
    "DEFAULT_INTERCEPT_RANGE",
    "REACH_INTERCEPT_RANGE",
    "MIN_DAMAGE_AFTER_MODIFIER",
    "DEPTHS_DAMAGE_MODIFIER_TAG",
    "is_detected",
    "mark_detected",
    "detection_cost",
    "legal_targets_for",
    "can_intercept",
    "install_depth_damage_modifier",
]
