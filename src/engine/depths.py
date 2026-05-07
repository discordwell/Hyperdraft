"""
Depths — Submarine Fleet Card Game core engine module.

This module mirrors the structure of ``src/engine/minecraft.py`` for the
Depths game mode: a small set of mode-specific helpers, a charge-pool
resource system, player setup, mine/sonar system interceptors, and a
``DepthsModeAdapter`` to register with ``mode_adapter.py``.

Public symbols (used by depths_combat.py / depths_turn.py /
depths_adapter.py):
  - DepthBand              — enum SURFACE/PERISCOPE/MID/DEEP/CRUSH
  - DepthsChargeSystem     — two-pool charge system (tc, sc)
  - setup_depths_player    — player init (deck, opening hand, flagship)
  - DepthsModeAdapter      — ``mode_adapter.GameModeAdapter`` subclass
  - get_flagship           — find a player's Flagship Vessel
  - vessels_at_depth       — list a player's Vessels at a given depth
  - is_vessel              — CardType.DEPTHS_VESSEL membership check
  - depth_difference       — abs(a.value - b.value)
  - parse_charge_cost      — parse '{2T, 1S}' / '{X(T/S)}' to a ChargeCost
  - count_vessels          — board+hand+library Vessel count for scuttle-loss

Spelling notes / deviations from the design doc:
  - The "surface a vessel" event is named ``DEPTHS_SURFACE_VESSEL`` (not
    ``DEPTHS_SURFACE``) so it doesn't collide with the SURFACE turn phase.
  - Detection persistence is implemented as a duration string on
    ``ObjectState.detected_until`` (one of ``end_of_turn`` |
    ``until_leaves`` | ``forever``) plus the ``ObjectState.detected``
    boolean. Ping decay clears the flag for ``end_of_turn`` durations
    only. Cards that want permanent detection set ``detected_until``
    to ``forever``.
  - Mines are kept on the battlefield until they fire; the system
    interceptor that emits ``DEPTHS_MINE_TRIGGER`` follows it with a
    ``DAMAGE`` event and an ``OBJECT_DESTROYED`` for the mine
    (one-shot semantics).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .types import (
    CardDefinition,
    CardType,
    Characteristics,
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    Player,
    ZoneType,
    new_id,
)


# =============================================================================
# Depth Ladder
# =============================================================================

class DepthBand(Enum):
    """
    The five vertical bands a Vessel can occupy.

    Numeric values are deliberately ordered (SURFACE=0 ... CRUSH=4) so
    ``abs(a.value - b.value)`` gives the depth-band separation used for
    damage modifier math (each band of separation reduces damage by 1).
    """
    SURFACE = 0
    PERISCOPE = 1
    MID = 2
    DEEP = 3
    CRUSH = 4


# Default depth a Flagship spawns at and is locked to.
FLAGSHIP_DEPTH = DepthBand.PERISCOPE
# Default Flagship hull (acts as the player's life total).
FLAGSHIP_HULL = 25
# Detection difficulty by band — used by combat to compute Sonar cost
# (1 + difficulty) for detection attempts.
DETECTION_DIFFICULTY: dict[DepthBand, int] = {
    DepthBand.SURFACE: 0,
    DepthBand.PERISCOPE: 0,
    DepthBand.MID: 1,
    DepthBand.DEEP: 2,
    DepthBand.CRUSH: 3,
}
# Per-turn Resupply gain (1 of each pool). Cap is computed dynamically.
RESUPPLY_TC = 1
RESUPPLY_SC = 1
# Hard ceiling on per-turn cap — analogous to Hearthstone's max-mana rule.
MAX_CHARGE_CAP = 10
# Opening hand size — the design doc specifies 5.
OPENING_HAND_SIZE = 5
# Hand size limit (Surface phase discard-to).
HAND_SIZE_LIMIT = 8


# =============================================================================
# Charge Cost Parser
# =============================================================================

@dataclass
class ChargeCost:
    """
    Parsed cost for a Depths card or activation.

    A cost string looks like ``{2T, 1S}`` (2 Torpedo + 1 Sonar) or
    ``{X(T/S)}`` (X charges from either pool). Tokens are
    case-insensitive.

    Fields:
      - torpedo:    fixed Torpedo Charge cost
      - sonar:      fixed Sonar Charge cost
      - hybrid:     "either" cost — payable from either pool
                    (Doctrine flexible costs)
      - x_pool:     None | 'T' | 'S' | 'either' — denotes that this cost
                    accepts an X value from the listed pool. The X value
                    itself is supplied at cast time and not stored here.
    """
    torpedo: int = 0
    sonar: int = 0
    hybrid: int = 0
    x_pool: Optional[str] = None

    @property
    def total_fixed(self) -> int:
        return self.torpedo + self.sonar + self.hybrid

    @property
    def is_free(self) -> bool:
        return self.total_fixed == 0 and self.x_pool is None


def parse_charge_cost(cost_str: Optional[str]) -> ChargeCost:
    """
    Parse a Depths cost string to a ChargeCost.

    Accepted token forms (whitespace and case insensitive, separated by
    commas inside the outer braces):
      ``{n}``       — n hybrid charges (from either pool); equivalent to ``{nH}``
      ``{nT}``      — n Torpedo Charges
      ``{nS}``      — n Sonar Charges
      ``{nH}``      — n hybrid charges
      ``{X(T/S)}``  — X charges from either pool
      ``{XT}``      — X Torpedo Charges
      ``{XS}``      — X Sonar Charges

    A cost string may include multiple tokens, e.g. ``{2T, 1S}``.

    Returns an empty ChargeCost on falsy input so vanilla cards (no
    cost / pseudo-tokens) parse cleanly.
    """
    cost = ChargeCost()
    if not cost_str:
        return cost

    raw = cost_str.strip()
    # Strip outer braces if present so '{2T, 1S}' and '2T, 1S' both parse.
    if raw.startswith("{") and raw.endswith("}"):
        raw = raw[1:-1]

    for chunk in raw.split(","):
        token = chunk.strip()
        if not token:
            continue
        # Inner braces (one cost expressed as multiple bracketed tokens):
        if token.startswith("{") and token.endswith("}"):
            token = token[1:-1].strip()
        # Hybrid X form: X(T/S) — case-insensitive
        upper = token.upper().replace(" ", "")
        if upper in {"X(T/S)", "X(S/T)"}:
            cost.x_pool = "either"
            continue
        if upper in {"XT", "X(T)"}:
            cost.x_pool = "T"
            continue
        if upper in {"XS", "X(S)"}:
            cost.x_pool = "S"
            continue
        # Numeric forms: digits followed optionally by a pool letter.
        digits = ""
        i = 0
        while i < len(upper) and upper[i].isdigit():
            digits += upper[i]
            i += 1
        if not digits:
            # Nothing to do for unrecognised tokens (defensive).
            continue
        amount = int(digits)
        suffix = upper[i:].strip()
        if suffix == "T":
            cost.torpedo += amount
        elif suffix == "S":
            cost.sonar += amount
        elif suffix in {"", "H"}:
            cost.hybrid += amount
        # Any other suffix is ignored — keep the parser permissive so
        # placeholder costs in tests don't blow up.
    return cost


# =============================================================================
# Charge System
# =============================================================================

class DepthsChargeSystem:
    """
    Two-pool resource system for Depths.

    Pools live on ``Player.tc`` and ``Player.sc`` (parallel to MTG's
    ManaPool but simpler — no colour, no land/source bookkeeping). The
    Beginning (Dive) phase calls ``resupply()`` to grant +1 to each
    pool, capped by ``cap_for_turn``.

    API mirrors the relevant slice of ``ManaSystem``:
      - ``can_pay(player_id, cost_str, x=0)``
      - ``pay_cost(player_id, cost_str, x=0)``
      - ``add_charges(player_id, *, tc=0, sc=0, cap=None)``
      - ``cap_for_turn(turn_number)``
      - ``resupply(player_id, turn_number)``
    """

    def __init__(self, state: GameState):
        self.state = state

    # ------------------------------------------------------------------
    # Cap math
    # ------------------------------------------------------------------

    @staticmethod
    def cap_for_turn(turn_number: int) -> int:
        """Per-pool cap for the given turn number — min(turn, MAX_CHARGE_CAP)."""
        return max(0, min(int(turn_number or 0), MAX_CHARGE_CAP))

    # ------------------------------------------------------------------
    # Payment
    # ------------------------------------------------------------------

    def can_pay(self, player_id: str, cost_str: str, x: int = 0) -> bool:
        cost = parse_charge_cost(cost_str)
        return self._can_pay_parsed(player_id, cost, x=x)

    def _can_pay_parsed(self, player_id: str, cost: ChargeCost, x: int = 0) -> bool:
        player = self.state.players.get(player_id)
        if not player:
            return False
        x_t = 0
        x_s = 0
        x_either = 0
        if cost.x_pool == "T":
            x_t = max(0, int(x or 0))
        elif cost.x_pool == "S":
            x_s = max(0, int(x or 0))
        elif cost.x_pool == "either":
            x_either = max(0, int(x or 0))

        if player.tc < cost.torpedo + x_t:
            return False
        if player.sc < cost.sonar + x_s:
            return False
        # Hybrid + X(either) draws from the combined pool minus the
        # earmarked T/S amounts already accounted for.
        remaining_t = player.tc - cost.torpedo - x_t
        remaining_s = player.sc - cost.sonar - x_s
        flexible_needed = cost.hybrid + x_either
        if remaining_t + remaining_s < flexible_needed:
            return False
        return True

    def pay_cost(self, player_id: str, cost_str: str, x: int = 0) -> bool:
        """
        Pay a parsed cost from the player's pools.

        Returns True on success, False if the player can't afford it
        (no partial payment).
        """
        cost = parse_charge_cost(cost_str)
        if not self._can_pay_parsed(player_id, cost, x=x):
            return False
        player = self.state.players[player_id]

        x_t = 0
        x_s = 0
        x_either = 0
        if cost.x_pool == "T":
            x_t = max(0, int(x or 0))
        elif cost.x_pool == "S":
            x_s = max(0, int(x or 0))
        elif cost.x_pool == "either":
            x_either = max(0, int(x or 0))

        # Earmarked pools first.
        player.tc -= (cost.torpedo + x_t)
        player.sc -= (cost.sonar + x_s)

        # Hybrid / X(either): greedy from whichever pool has more so we
        # leave the player a balanced reserve. Ties prefer Sonar (sensors
        # tend to be the constrained pool in most archetypes).
        flexible_needed = cost.hybrid + x_either
        while flexible_needed > 0:
            if player.tc >= player.sc:
                player.tc -= 1
            else:
                player.sc -= 1
            flexible_needed -= 1
        return True

    # ------------------------------------------------------------------
    # Granting charges (Resupply step + card effects)
    # ------------------------------------------------------------------

    def add_charges(
        self,
        player_id: str,
        *,
        tc: int = 0,
        sc: int = 0,
        cap: Optional[int] = None,
    ) -> tuple[int, int]:
        """
        Grant charges to a player, capped at ``cap`` (or MAX_CHARGE_CAP
        if cap is None).

        Returns the actual ``(tc_gained, sc_gained)`` tuple — useful for
        emitting truthful DEPTHS_RESUPPLY payloads.
        """
        player = self.state.players.get(player_id)
        if not player:
            return (0, 0)
        ceiling = MAX_CHARGE_CAP if cap is None else max(0, int(cap))
        old_tc, old_sc = player.tc, player.sc
        player.tc = min(ceiling, player.tc + max(0, int(tc or 0)))
        player.sc = min(ceiling, player.sc + max(0, int(sc or 0)))
        return (player.tc - old_tc, player.sc - old_sc)

    def resupply(self, player_id: str, turn_number: int) -> tuple[int, int]:
        """
        Apply the per-turn Resupply: +1 of each pool, capped by
        ``cap_for_turn(turn_number)``.
        """
        cap = self.cap_for_turn(turn_number)
        return self.add_charges(player_id, tc=RESUPPLY_TC, sc=RESUPPLY_SC, cap=cap)

    # ------------------------------------------------------------------
    # MTG / mode_adapter compatibility shims
    # ------------------------------------------------------------------

    def get_pool(self, player_id: str):
        """Compatibility shim — Depths has two pools, return None."""
        return None

    def get_untapped_lands(self, player_id: str) -> list:
        """Compatibility shim — Depths has no lands."""
        return []


# =============================================================================
# Helpers (queries used by combat / turn / AI)
# =============================================================================

def is_vessel(obj: Optional[GameObject]) -> bool:
    """True if ``obj`` is a Depths Vessel."""
    if obj is None:
        return False
    return CardType.DEPTHS_VESSEL in obj.characteristics.types


def is_mine(obj: Optional[GameObject]) -> bool:
    """True if ``obj`` is a Depths Mine."""
    if obj is None:
        return False
    return CardType.DEPTHS_MINE in obj.characteristics.types


def depth_difference(a: DepthBand, b: DepthBand) -> int:
    """Number of bands separating a and b (0 = same band)."""
    if a is None or b is None:
        return 0
    return abs(int(a.value) - int(b.value))


def get_flagship(player_id: str, state: GameState) -> Optional[GameObject]:
    """
    Return the player's Flagship Vessel object, or None if they have no
    Flagship on the battlefield.

    Looks up ``player.flagship_id`` first; falls back to scanning the
    battlefield for a vessel of subtype ``Flagship`` controlled by the
    player (handles the case where a card moved the flagship reference).
    """
    player = state.players.get(player_id)
    if player and player.flagship_id and player.flagship_id in state.objects:
        obj = state.objects[player.flagship_id]
        if obj.zone == ZoneType.BATTLEFIELD and is_vessel(obj):
            return obj
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return None
    for oid in battlefield.objects:
        obj = state.objects.get(oid)
        if not obj or obj.controller != player_id or not is_vessel(obj):
            continue
        if "Flagship" in obj.characteristics.subtypes:
            return obj
    return None


def vessels_at_depth(
    player_id: str,
    depth_band: DepthBand,
    state: GameState,
) -> list[GameObject]:
    """All on-battlefield Vessels controlled by player at the given band."""
    out: list[GameObject] = []
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return out
    for oid in battlefield.objects:
        obj = state.objects.get(oid)
        if not obj or obj.controller != player_id or not is_vessel(obj):
            continue
        if obj.state.depth_band == depth_band:
            out.append(obj)
    return out


def all_vessels(player_id: str, state: GameState, *, zones: Optional[set[ZoneType]] = None) -> list[GameObject]:
    """All Vessels owned (default zones: battlefield + hand + library)."""
    if zones is None:
        zones = {ZoneType.BATTLEFIELD, ZoneType.HAND, ZoneType.LIBRARY}
    out: list[GameObject] = []
    for obj in state.objects.values():
        if obj.zone not in zones:
            continue
        if obj.owner != player_id and obj.controller != player_id:
            continue
        if not is_vessel(obj):
            continue
        out.append(obj)
    return out


def count_vessels(player_id: str, state: GameState) -> int:
    """
    Count Vessels in board + hand + library — used by the scuttle-loss
    win-condition check.
    """
    return len(all_vessels(player_id, state))


def opposing_mines_at(
    state: GameState,
    band: DepthBand,
    triggering_controller: str,
) -> list[GameObject]:
    """
    Return all Mines controlled by an opponent of ``triggering_controller``
    that are sitting at ``band`` on the battlefield. Used by the system
    interceptor that fires DEPTHS_MINE_TRIGGER on DIVE / SURFACE_VESSEL.
    """
    out: list[GameObject] = []
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return out
    for oid in battlefield.objects:
        obj = state.objects.get(oid)
        if not obj or not is_mine(obj):
            continue
        if obj.controller == triggering_controller:
            continue
        if obj.state.depth_band == band:
            out.append(obj)
    return out


def detection_cost(band: DepthBand) -> int:
    """1 + depth_difficulty(band) — minimum Sonar to detect a Vessel here."""
    return 1 + DETECTION_DIFFICULTY.get(band, 0)


# =============================================================================
# Action Handlers (consumed by DepthsTurnManager.execute_action)
# =============================================================================
#
# Each handler returns a ``(ok, message, events)`` triple. ``ok=False`` is
# expected for illegal actions (insufficient charges, wrong card type, target
# missing, etc.) — the turn manager surfaces the message but does NOT abort
# the action loop on failure. ``ok=True`` callers also receive the list of
# events emitted through the pipeline so triggers can chain.
#
# All handlers route via ``game.emit(...)`` so card interceptors (ETB, ATTACH,
# DEPTHS_*, etc.) get a chance to react.


def _coerce_depth_band(value) -> Optional[DepthBand]:
    """Accept a DepthBand enum, an int 0..4, or its name string."""
    if value is None:
        return None
    if isinstance(value, DepthBand):
        return value
    if isinstance(value, int):
        try:
            return DepthBand(value)
        except ValueError:
            return None
    if isinstance(value, str):
        try:
            return DepthBand[value.upper()]
        except KeyError:
            return None
    return None


def _hand_zone_key(player_id: str) -> str:
    return f"hand_{player_id}"


def _move_object_zone(game, obj: GameObject, to_zone: ZoneType, *, source: Optional[str] = None) -> list[Event]:
    """Emit a ZONE_CHANGE moving ``obj`` to ``to_zone``."""
    from_zone = obj.zone
    payload: dict[str, object] = {
        "object_id": obj.id,
        "from_zone_type": from_zone,
        "to_zone_type": to_zone,
    }
    if from_zone in {ZoneType.HAND, ZoneType.LIBRARY, ZoneType.GRAVEYARD}:
        payload["from_zone"] = f"{from_zone.name.lower()}_{obj.owner}"
    elif from_zone in {ZoneType.BATTLEFIELD, ZoneType.STACK,
                       ZoneType.EXILE, ZoneType.COMMAND}:
        payload["from_zone"] = from_zone.name.lower()
    if to_zone in {ZoneType.HAND, ZoneType.LIBRARY, ZoneType.GRAVEYARD}:
        payload["to_zone"] = f"{to_zone.name.lower()}_{obj.owner}"
    elif to_zone in {ZoneType.BATTLEFIELD, ZoneType.STACK,
                     ZoneType.EXILE, ZoneType.COMMAND}:
        payload["to_zone"] = to_zone.name.lower()
    event = Event(
        type=EventType.ZONE_CHANGE,
        payload=payload,
        source=source or obj.id,
        controller=obj.controller,
    )
    return list(game.emit(event) or [])


def _hand_obj(state: GameState, player_id: str, card_id: Optional[str]) -> Optional[GameObject]:
    """Return the GameObject in player's hand matching card_id, or None."""
    if not card_id:
        return None
    hand = state.zones.get(_hand_zone_key(player_id))
    if hand is None or card_id not in hand.objects:
        return None
    return state.objects.get(card_id)


def _charge_system(game) -> "DepthsChargeSystem":
    cs = getattr(game, "mana_system", None)
    if isinstance(cs, DepthsChargeSystem):
        return cs
    return DepthsChargeSystem(game.state)


def _card_cost_str(obj: GameObject) -> Optional[str]:
    """Return the printed cost string from the object's characteristics."""
    if obj is None or obj.characteristics is None:
        return None
    return obj.characteristics.mana_cost


def deploy_vessel(
    game,
    player_id: str,
    *,
    card_id: Optional[str] = None,
    depth_band=None,
) -> tuple[bool, str, list[Event]]:
    """Pay the cost, move a Vessel from HAND to BATTLEFIELD.

    Vessels default to SURFACE depth unless ``depth_band`` is supplied. The
    new permanent enters with summoning sickness so it can't attack the same
    turn.
    """
    state = game.state
    obj = _hand_obj(state, player_id, card_id)
    if obj is None:
        return False, "Vessel card not in hand", []
    if not is_vessel(obj):
        return False, "Card is not a Vessel", []

    cost_str = _card_cost_str(obj)
    cs = _charge_system(game)
    if cost_str and not cs.pay_cost(player_id, cost_str):
        return False, "Cannot pay deploy cost", []

    # Honour the caller's explicit choice → card_def.depths_default_depth →
    # SURFACE fallback. Without the middle hop, every Vessel spawns at SURFACE
    # regardless of design (Snorkel Stalker -> PERISCOPE, Type-XXI Phantom ->
    # DEEP, etc.) — Pilot B confirmed in /ultra-loop iter-3.
    explicit = _coerce_depth_band(depth_band)
    default_attr = getattr(obj.card_def, "depths_default_depth", None) if obj.card_def else None
    band = explicit or _coerce_depth_band(default_attr) or DepthBand.SURFACE

    events = _move_object_zone(game, obj, ZoneType.BATTLEFIELD, source=obj.id)

    # Battlefield-entry bookkeeping. The system interceptor that defaults
    # depth_band on entry runs first; we overwrite to honour the caller's
    # choice if any. Summoning sickness is set by create_object's defaults
    # for fresh objects, but ZONE_CHANGE preserves the existing GameObject,
    # so set it here.
    obj.state.depth_band = band
    obj.state.summoning_sickness = True
    obj.state.tapped = False
    return True, "Vessel deployed", events


def dive_vessel(
    game,
    player_id: str,
    *,
    vessel_id: Optional[str] = None,
) -> tuple[bool, str, list[Event]]:
    """Pay 1 Sonar, move a Vessel one band toward CRUSH.

    Refuses if the Vessel is already at CRUSH or is the Flagship.
    """
    state = game.state
    if not vessel_id:
        return False, "No vessel_id supplied", []
    obj = state.objects.get(vessel_id)
    if obj is None or obj.zone != ZoneType.BATTLEFIELD:
        return False, "Vessel not on battlefield", []
    if obj.controller != player_id:
        return False, "Not your vessel", []
    if not is_vessel(obj):
        return False, "Not a vessel", []
    if "Flagship" in obj.characteristics.subtypes:
        return False, "Flagship cannot dive", []

    current = obj.state.depth_band or DepthBand.SURFACE
    if current is DepthBand.CRUSH:
        return False, "Already at CRUSH depth", []

    cs = _charge_system(game)
    if not cs.pay_cost(player_id, "{1S}"):
        return False, "Cannot pay dive cost", []

    new_band = DepthBand(int(current.value) + 1)
    obj.state.depth_band = new_band

    events = list(game.emit(Event(
        type=EventType.DEPTHS_DIVE,
        payload={
            "object_id": obj.id,
            "from_band": current,
            "to_band": new_band,
            "controller": player_id,
        },
        source=obj.id,
        controller=player_id,
    )) or [])
    return True, "Vessel dove", events


def surface_vessel(
    game,
    player_id: str,
    *,
    vessel_id: Optional[str] = None,
) -> tuple[bool, str, list[Event]]:
    """Free: move a Vessel one band toward SURFACE.

    Refuses if the Vessel is already at SURFACE or is the Flagship.
    """
    state = game.state
    if not vessel_id:
        return False, "No vessel_id supplied", []
    obj = state.objects.get(vessel_id)
    if obj is None or obj.zone != ZoneType.BATTLEFIELD:
        return False, "Vessel not on battlefield", []
    if obj.controller != player_id:
        return False, "Not your vessel", []
    if not is_vessel(obj):
        return False, "Not a vessel", []
    if "Flagship" in obj.characteristics.subtypes:
        return False, "Flagship cannot surface", []

    current = obj.state.depth_band or DepthBand.SURFACE
    if current is DepthBand.SURFACE:
        return False, "Already at SURFACE", []

    new_band = DepthBand(int(current.value) - 1)
    obj.state.depth_band = new_band

    events = list(game.emit(Event(
        type=EventType.DEPTHS_SURFACE_VESSEL,
        payload={
            "object_id": obj.id,
            "from_band": current,
            "to_band": new_band,
            "controller": player_id,
        },
        source=obj.id,
        controller=player_id,
    )) or [])
    return True, "Vessel surfaced", events


def lay_mine(
    game,
    player_id: str,
    *,
    card_id: Optional[str] = None,
    depth_band=None,
) -> tuple[bool, str, list[Event]]:
    """Move a Mine from HAND to BATTLEFIELD at ``depth_band``."""
    state = game.state
    obj = _hand_obj(state, player_id, card_id)
    if obj is None:
        return False, "Mine card not in hand", []
    if not is_mine(obj):
        return False, "Card is not a Mine", []

    band = _coerce_depth_band(depth_band) or DepthBand.PERISCOPE
    cost_str = _card_cost_str(obj)
    cs = _charge_system(game)
    if cost_str and not cs.pay_cost(player_id, cost_str):
        return False, "Cannot pay mine cost", []

    events = _move_object_zone(game, obj, ZoneType.BATTLEFIELD, source=obj.id)
    obj.state.depth_band = band

    events.extend(list(game.emit(Event(
        type=EventType.DEPTHS_LAY_MINE,
        payload={
            "object_id": obj.id,
            "controller": player_id,
            "depth_band": band,
        },
        source=obj.id,
        controller=player_id,
    )) or []))
    return True, "Mine laid", events


def attach(
    game,
    player_id: str,
    *,
    attachment_id: Optional[str] = None,
    target_id: Optional[str] = None,
) -> tuple[bool, str, list[Event]]:
    """Pay cost, move attachment to BATTLEFIELD, emit ATTACH event."""
    state = game.state
    if not attachment_id or not target_id:
        return False, "attach requires attachment_id and target_id", []
    attachment = _hand_obj(state, player_id, attachment_id)
    if attachment is None:
        return False, "Attachment card not in hand", []
    target = state.objects.get(target_id)
    if target is None or target.zone != ZoneType.BATTLEFIELD:
        return False, "Attach target not on battlefield", []
    if target.controller != player_id:
        return False, "Cannot attach to opposing permanent", []

    cost_str = _card_cost_str(attachment)
    cs = _charge_system(game)
    if cost_str and not cs.pay_cost(player_id, cost_str):
        return False, "Cannot pay attach cost", []

    events = _move_object_zone(game, attachment, ZoneType.BATTLEFIELD, source=attachment.id)
    events.extend(list(game.emit(Event(
        type=EventType.ATTACH,
        payload={
            "object_id": attachment.id,
            "target_id": target.id,
        },
        source=attachment.id,
        controller=player_id,
    )) or []))
    return True, "Attached", events


def cast_spell(
    game,
    player_id: str,
    *,
    card_id: Optional[str] = None,
    targets: Optional[list] = None,
    modes: Optional[list] = None,
) -> tuple[bool, str, list[Event]]:
    """Pay cost, resolve a Doctrine / Action card from hand into the GRAVEYARD.

    The current scaffold doesn't run cards through the MTG stack — Depths
    Doctrine cards are sorcery-speed effects that resolve immediately. We
    emit a marker SPELL_CAST event for triggers, then route the card to
    the graveyard via ZONE_CHANGE so the engine's existing handlers fire.
    A future revision can route Action cards through the stack if Depths
    grows instant-speed responses.
    """
    state = game.state
    obj = _hand_obj(state, player_id, card_id)
    if obj is None:
        return False, "Spell card not in hand", []
    types = obj.characteristics.types
    if not (CardType.INSTANT in types or CardType.SORCERY in types
            or CardType.ENCHANTMENT in types):
        return False, "Card is not a castable spell", []

    cost_str = _card_cost_str(obj)
    cs = _charge_system(game)
    if cost_str and not cs.pay_cost(player_id, cost_str):
        return False, "Cannot pay spell cost", []

    cast_event = Event(
        type=EventType.SPELL_CAST,
        payload={
            "object_id": obj.id,
            "controller": player_id,
            "targets": list(targets or []),
            "modes": list(modes or []),
        },
        source=obj.id,
        controller=player_id,
    )
    events = list(game.emit(cast_event) or [])

    # Bugfix 2026-05-07: invoke the card's cast_effect_fn body. Previously
    # SPELL_CAST emitted but the card's actual effect was a silent no-op for
    # all ~25 SUBS Action cards (Saturation Strike, Drone Swarm, Volley...).
    # Surfaced by ultra-loop iter-1 Pilot A confirming Saturation Strike's
    # +2 power buff never reached the DAMAGE event.
    cast_effect_fn = getattr(obj.card_def, "cast_effect_fn", None) if obj.card_def else None
    if callable(cast_effect_fn):
        try:
            produced = cast_effect_fn(obj, state)
        except TypeError:
            # Some effect_fns expect (game, player_id, source, targets) — try that.
            try:
                produced = cast_effect_fn(game, player_id, obj, list(targets or []))
            except Exception:
                produced = []
        for ev in produced or []:
            events.extend(list(game.emit(ev) or []) or [ev])

    if CardType.ENCHANTMENT in types:
        events.extend(_move_object_zone(game, obj, ZoneType.BATTLEFIELD, source=obj.id))
    else:
        events.extend(_move_object_zone(game, obj, ZoneType.GRAVEYARD, source=obj.id))
    return True, "Spell cast", events


def activate_ability(
    game,
    player_id: str,
    *,
    source_id: Optional[str] = None,
    ability_index: int = 0,
    targets: Optional[list] = None,
) -> tuple[bool, str, list[Event]]:
    """Activate an indexed ability registered on a permanent.

    Activated abilities are stored on ``obj.state.activated_abilities``
    as a list of descriptors with shape::

        {"cost": str, "effect": callable(game, player_id, source, targets) -> list[Event]}

    Cards that haven't shipped activated abilities yet will report
    "no such ability" — the AI's legal-action enumerator only emits
    ActivateAbility for permanents whose state actually exposes one,
    so this is a defensive guard rather than a hot path.
    """
    state = game.state
    if not source_id:
        return False, "No source_id supplied", []
    src = state.objects.get(source_id)
    if src is None or src.zone != ZoneType.BATTLEFIELD:
        return False, "Source not on battlefield", []
    if src.controller != player_id:
        return False, "Not your permanent", []

    abilities = list(getattr(src.state, "activated_abilities", []) or [])
    try:
        ability = abilities[int(ability_index)]
    except (IndexError, TypeError, ValueError):
        return False, "No such ability", []

    cost_str = ability.get("cost") if isinstance(ability, dict) else getattr(ability, "cost", None)
    cs = _charge_system(game)
    if cost_str and not cs.pay_cost(player_id, cost_str):
        return False, "Cannot pay activation cost", []

    effect_fn = (ability.get("effect") if isinstance(ability, dict)
                 else getattr(ability, "effect", None))
    events: list[Event] = []
    if callable(effect_fn):
        try:
            produced = effect_fn(game, player_id, src, list(targets or []))
        except TypeError:
            try:
                produced = effect_fn(game, src, list(targets or []))
            except Exception:
                produced = []
        for ev in produced or []:
            game.emit(ev)
            events.append(ev)
    return True, "Ability activated", events


# =============================================================================
# Player Setup
# =============================================================================

def setup_depths_player(
    game,
    player: Player,
    deck: list[CardDefinition],
    flagship_def: CardDefinition,
) -> GameObject:
    """
    Initialise a Depths player.

    Steps:
      1. Reset the player's pools / flagship pointer.
      2. Build deck objects in the LIBRARY zone, then shuffle.
      3. Draw OPENING_HAND_SIZE cards into HAND.
      4. Create the Flagship Vessel on the BATTLEFIELD at PERISCOPE
         depth with hull = FLAGSHIP_HULL. Stamp ``player.flagship_id``.

    Returns the Flagship GameObject.
    """
    import copy

    # (1) Reset pools / fields
    player.tc = 0
    player.sc = 0
    player.has_lost = False
    player.flagship_id = None
    # Use life as a mirror of flagship hull for downstream UI / SBA
    # consumers that read player.life. We'll keep it in sync by setting
    # life = FLAGSHIP_HULL here; the actual hull lives on the Vessel
    # GameObject's ``state.damage`` and is reduced via DAMAGE events.
    player.life = FLAGSHIP_HULL
    player.max_life = FLAGSHIP_HULL

    # (2) Deck → library
    for card_def in deck or []:
        game.create_object(
            name=card_def.name,
            owner_id=player.id,
            zone=ZoneType.LIBRARY,
            characteristics=copy.deepcopy(card_def.characteristics),
            card_def=card_def,
        )
    if hasattr(game, "shuffle_library"):
        game.shuffle_library(player.id)

    # (3) Opening hand. draw_cards goes through the pipeline and respects
    # adapter hand-size limits, but during setup we want the full hand
    # regardless of any per-game cap.
    if hasattr(game, "draw_cards"):
        game.draw_cards(player.id, OPENING_HAND_SIZE)

    # (4) Flagship on the battlefield at PERISCOPE.
    flagship_chars = copy.deepcopy(flagship_def.characteristics)
    # Make absolutely sure the Flagship has the Vessel type and the
    # Flagship subtype so helpers find it.
    flagship_chars.types.add(CardType.DEPTHS_VESSEL)
    flagship_chars.subtypes.add("Flagship")
    if flagship_chars.toughness is None:
        flagship_chars.toughness = FLAGSHIP_HULL
    flagship = game.create_object(
        name=flagship_def.name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=flagship_chars,
        card_def=flagship_def,
    )
    flagship.state.depth_band = FLAGSHIP_DEPTH
    flagship.state.detected = True
    flagship.state.detected_until = "forever"
    flagship.state.summoning_sickness = False
    player.flagship_id = flagship.id

    return flagship


# =============================================================================
# System Interceptors
# =============================================================================

def _install_depths_system_interceptors(game) -> None:
    """
    Register Depths-specific system interceptors:

      1. Mine triggers — on DEPTHS_DIVE / DEPTHS_SURFACE_VESSEL, check
         for opposing mines at the destination band and fire
         DEPTHS_MINE_TRIGGER + DAMAGE.
      2. Sonar Decay — on PHASE_END for the SURFACE phase, clear
         ``state.detected`` for any vessel whose detection persistence
         is ``end_of_turn`` and emit DEPTHS_PING_DECAY markers.
      3. Resupply — on DEPTHS_RESUPPLY, grant +1/+1 charges capped by
         the per-turn ceiling.
      4. depth_band tracking — when a Vessel enters the battlefield via
         ZONE_CHANGE without a depth_band, default it to PERISCOPE.

    Filters/handlers all gate on ``state.game_mode == 'depths'`` so a
    misconfigured registry can't fire mine triggers in MTG / HS games.
    """
    state = game.state

    # ------------------------------------------------------------------
    # (1) Mine triggers on DIVE / SURFACE_VESSEL
    # ------------------------------------------------------------------
    def _mine_filter(event: Event, st: GameState) -> bool:
        if st.game_mode != "depths":
            return False
        return event.type in {EventType.DEPTHS_DIVE, EventType.DEPTHS_SURFACE_VESSEL}

    def _mine_handler(event: Event, st: GameState) -> InterceptorResult:
        vessel_id = event.payload.get("object_id")
        vessel = st.objects.get(vessel_id) if vessel_id else None
        if not vessel or not is_vessel(vessel):
            return InterceptorResult(action=InterceptorAction.PASS)
        to_band = event.payload.get("to_band")
        if to_band is None:
            to_band = vessel.state.depth_band
        if to_band is None:
            return InterceptorResult(action=InterceptorAction.PASS)

        new_events: list[Event] = []
        for mine in opposing_mines_at(st, to_band, vessel.controller):
            damage_amount = 0
            if mine.card_def is not None:
                damage_amount = int(getattr(mine.card_def, "depths_mine_damage", 0) or 0)
            # Fallback: power of the mine, then a sensible default.
            if damage_amount <= 0:
                damage_amount = int(mine.characteristics.power or 0)
            if damage_amount <= 0:
                damage_amount = 3  # design-doc default
            new_events.append(Event(
                type=EventType.DEPTHS_MINE_TRIGGER,
                payload={
                    "mine_id": mine.id,
                    "target_id": vessel.id,
                    "amount": damage_amount,
                    "depth_band": to_band,
                    "controller": mine.controller,
                },
                source=mine.id,
                controller=mine.controller,
            ))
            new_events.append(Event(
                type=EventType.DAMAGE,
                payload={
                    "target": vessel.id,
                    "amount": damage_amount,
                    "source": mine.id,
                    "is_combat": False,
                    "reason": "mine_trigger",
                },
                source=mine.id,
                controller=mine.controller,
            ))
            # Mines are one-shot — destroy after firing.
            new_events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={"object_id": mine.id, "reason": "mine_consumed"},
                source=mine.id,
                controller=mine.controller,
            ))
        if not new_events:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    game.register_interceptor(Interceptor(
        id=new_id(),
        source="DEPTHS_SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_mine_filter,
        handler=_mine_handler,
        duration="forever",
    ))

    # ------------------------------------------------------------------
    # (2) Sonar Decay on PHASE_END for the Surface (end) phase
    # ------------------------------------------------------------------
    def _decay_filter(event: Event, st: GameState) -> bool:
        if st.game_mode != "depths":
            return False
        if event.type != EventType.PHASE_END:
            return False
        phase = event.payload.get("phase")
        # Accept either canonical 'surface' or compat 'depths_surface'.
        return phase in {"surface", "depths_surface", "end", "ending"}

    def _decay_handler(event: Event, st: GameState) -> InterceptorResult:
        new_events: list[Event] = []
        battlefield = st.zones.get("battlefield")
        if not battlefield:
            return InterceptorResult(action=InterceptorAction.PASS)
        for oid in battlefield.objects:
            obj = st.objects.get(oid)
            if not obj or not is_vessel(obj):
                continue
            if not obj.state.detected:
                continue
            if obj.state.detected_until in (None, "end_of_turn"):
                obj.state.detected = False
                obj.state.detected_until = None
                new_events.append(Event(
                    type=EventType.DEPTHS_PING_DECAY,
                    payload={"object_id": obj.id, "controller": obj.controller},
                    source="DEPTHS_SYSTEM",
                ))
        if not new_events:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    game.register_interceptor(Interceptor(
        id=new_id(),
        source="DEPTHS_SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_decay_filter,
        handler=_decay_handler,
        duration="forever",
    ))

    # ------------------------------------------------------------------
    # (3) Resupply: grant capped charges on DEPTHS_RESUPPLY
    # ------------------------------------------------------------------
    def _resupply_filter(event: Event, st: GameState) -> bool:
        return st.game_mode == "depths" and event.type == EventType.DEPTHS_RESUPPLY

    def _resupply_handler(event: Event, st: GameState) -> InterceptorResult:
        player_id = event.payload.get("player")
        if not player_id or player_id not in st.players:
            return InterceptorResult(action=InterceptorAction.PASS)
        # If the payload already declares actual gains (because the turn
        # manager pre-computed them), skip — we just observe.
        if "tc_gained" in event.payload or "sc_gained" in event.payload:
            return InterceptorResult(action=InterceptorAction.PASS)
        charge_system = getattr(getattr(st, "_game", None), "mana_system", None)
        if not isinstance(charge_system, DepthsChargeSystem):
            charge_system = DepthsChargeSystem(st)
        cap = DepthsChargeSystem.cap_for_turn(st.turn_number)
        gained_tc, gained_sc = charge_system.resupply(player_id, st.turn_number)
        # Mutate the payload in-place so the marker carries truthful counts.
        event.payload["tc_gained"] = gained_tc
        event.payload["sc_gained"] = gained_sc
        event.payload["cap"] = cap
        return InterceptorResult(action=InterceptorAction.PASS)

    game.register_interceptor(Interceptor(
        id=new_id(),
        source="DEPTHS_SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.TRANSFORM,
        filter=_resupply_filter,
        handler=_resupply_handler,
        duration="forever",
    ))

    # ------------------------------------------------------------------
    # (4) Default depth_band on Vessel battlefield entry
    # ------------------------------------------------------------------
    def _entry_filter(event: Event, st: GameState) -> bool:
        if st.game_mode != "depths":
            return False
        if event.type != EventType.ZONE_CHANGE:
            return False
        return event.payload.get("to_zone_type") == ZoneType.BATTLEFIELD

    def _entry_handler(event: Event, st: GameState) -> InterceptorResult:
        oid = event.payload.get("object_id")
        obj = st.objects.get(oid) if oid else None
        if not obj or not is_vessel(obj):
            return InterceptorResult(action=InterceptorAction.PASS)
        if obj.state.depth_band is None:
            # Flagships always land at PERISCOPE; everything else also
            # defaults there until a card / activation moves it.
            obj.state.depth_band = FLAGSHIP_DEPTH
        return InterceptorResult(action=InterceptorAction.PASS)

    game.register_interceptor(Interceptor(
        id=new_id(),
        source="DEPTHS_SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_entry_filter,
        handler=_entry_handler,
        duration="forever",
    ))


# =============================================================================
# Mode Adapter
# =============================================================================

def _import_mode_adapter():
    """Lazy import to break the mode_adapter <-> depths circular dependency."""
    from .mode_adapter import GameModeAdapter
    return GameModeAdapter


def _depths_mode_adapter_class():
    """Build the DepthsModeAdapter class lazily so mode_adapter can register it."""
    Base = _import_mode_adapter()

    class DepthsModeAdapter(Base):
        """
        Game-mode adapter for the Depths submarine card game.

        Hooks overridden:
          - hand_size_limit -> 8 (Surface phase discard-to)
          - life_cap        -> FLAGSHIP_HULL (the Flagship is the life total)
          - default_max_hand_size -> HAND_SIZE_LIMIT
          - create_mana_system    -> DepthsChargeSystem
          - register_system_interceptors -> install mine + decay + resupply
          - post_creature_damage_destroy_check -> sink Vessels at hull == 0
          - apply_player_damage   -> route into Flagship hull damage
          - check_loss            -> custom (flagship sunk OR scuttle-loss)

        Hooks intentionally NOT overridden:
          - clear_damage_on_cleanup defaults — but Depths damage *persists*,
            so the turn manager must not clear damage. We install no
            cleanup-step heal hook. (The game-wide
            ``state.clear_damage_on_cleanup`` flag is the canonical
            switch; Game(`mode='depths'`) callers should pass
            ``clear_damage_on_cleanup=False``. We also flip it here in
            ``register_system_interceptors`` for safety.)
        """
        mode: str = "depths"

        # --- Caps / hand size -----------------------------------------

        def hand_size_limit(self, player, state):
            return HAND_SIZE_LIMIT

        def default_max_hand_size(self):
            return HAND_SIZE_LIMIT

        def life_cap(self, player, state):
            return FLAGSHIP_HULL

        # --- Mana / charge system ------------------------------------

        def create_mana_system(self, state):
            return DepthsChargeSystem(state)

        # --- Combat / turn / AI factories ----------------------------
        # Subclasses defined by Agent 2 / Agent 3 / Agent 4 are imported
        # lazily; if they don't exist yet we fall back to the MTG default
        # so the engine can still boot for smoke tests.

        def create_combat_manager(self, state):
            try:
                from .depths_combat import DepthsCombatManager
                return DepthsCombatManager(state)
            except Exception:
                return super().create_combat_manager(state)

        def create_turn_manager(self, state):
            try:
                from .depths_turn import DepthsTurnManager
                return DepthsTurnManager(state)
            except Exception:
                return super().create_turn_manager(state)

        # --- Setup hooks ----------------------------------------------

        async def setup_starting_hands(self, game, player_ids):
            # setup_depths_player has already drawn the opening hand;
            # bypass MTG's London Mulligan loop.
            return True

        # --- Damage routing -------------------------------------------

        def apply_player_damage(self, player, amount, state):
            """
            Route player-targeted damage onto the Flagship's hull.

            Depths has no separate player life pool — the Flagship IS the
            life total. So damage targeting the player_id is redirected
            onto the Flagship object's ``state.damage`` while also
            decrementing ``player.life`` for downstream UI/SBA reads.
            """
            damage = max(0, int(amount or 0))
            flagship = get_flagship(player.id, state)
            if flagship is not None:
                flagship.state.damage += damage
                flagship.state.last_damage_source = None
            player.life = max(0, player.life - damage)
            return 0

        def post_creature_damage_destroy_check(self, obj, event, state):
            """
            Sink Vessels at hull == 0. Hull is stored on
            ``characteristics.toughness`` and damage on
            ``state.damage`` — same shape as MTG creature SBA.
            """
            if not is_vessel(obj):
                return []
            toughness = obj.characteristics.toughness
            if toughness is None:
                return []
            if obj.state.damage >= int(toughness):
                return [Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={"object_id": obj.id, "reason": "vessel_sunk"},
                    source=event.source,
                    controller=event.controller,
                )]
            return []

        # --- Win / loss check -----------------------------------------

        def check_loss(self, player, state):
            """
            A Depths player loses when:
              - Their Flagship's hull is 0 (Flagship sunk), OR
              - They have no Vessels in board + hand + library
                (scuttle-loss).
            """
            flagship = get_flagship(player.id, state)
            if flagship is None:
                # Flagship has been destroyed (or never existed).
                return True
            toughness = flagship.characteristics.toughness or FLAGSHIP_HULL
            if flagship.state.damage >= int(toughness):
                return True
            if count_vessels(player.id, state) == 0:
                return True
            return False

        # --- System interceptors -------------------------------------

        def register_system_interceptors(self, game):
            # Install Depths-specific interceptors AND flip the global
            # cleanup-damage flag off — sub damage persists across turns.
            game.state.clear_damage_on_cleanup = False
            _install_depths_system_interceptors(game)

        def includes_game_log_in_state(self):
            return True

        # --- Server / AI registration --------------------------------

        def register_ai_player(self, game, player_id):
            if hasattr(game.turn_manager, "set_ai_player"):
                game.turn_manager.set_ai_player(player_id)

    return DepthsModeAdapter
