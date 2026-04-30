"""
EOE Void mechanic — per-turn condition tracking.

Void is active for a player when, this turn:
  - A nonland permanent left the battlefield (controlled by anyone), OR
  - That player cast a spell with mana value 5 or greater
    (this stands in for the printed "or a spell was warped this turn" condition;
    Hyperdraft has no full warp implementation, so the design constraint
    documented in this task uses MV >= 5 as the equivalent trigger).

State storage (per turn, cleared in TurnManager._emit_turn_end):
  state.turn_data['void_<player_id>']        -> bool     (per-player Void active)
  state.turn_data['void_global']             -> bool     (any nonland LTB this turn)

The two contributors are tracked separately so a future warp implementation can
fold in by writing 'void_<player_id>' = True when a player warps a spell.
"""

from typing import TYPE_CHECKING

from .types import (
    Event, EventType, GameState, ZoneType, CardType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    new_id,
)

if TYPE_CHECKING:
    from .game import Game


# =============================================================================
# Public query helpers
# =============================================================================

def is_void_active(player_id: str, state: GameState) -> bool:
    """Return True if Void is active for ``player_id`` this turn.

    Void becomes active when EITHER of the following occurred during the
    current turn:
      * A nonland permanent left the battlefield (any controller), OR
      * ``player_id`` cast a spell with mana value 5 or greater.
    """
    td = getattr(state, "turn_data", None) or {}
    if td.get("void_global"):
        return True
    if td.get(f"void_{player_id}"):
        return True
    return False


def mark_warp_cast(player_id: str, state: GameState) -> None:
    """Mark that ``player_id`` warped a spell this turn (for future use).

    Hyperdraft does not yet implement warp casting end-to-end. When that lands,
    the warp casting site should call this so cards that read "or a spell was
    warped this turn" remain correct.
    """
    td = getattr(state, "turn_data", None)
    if td is None:
        return
    td[f"void_{player_id}"] = True


def reset_void_state(state: GameState) -> None:
    """Clear void flags. Called at end of turn (TurnManager already clears
    state.turn_data globally; this is a defensive helper for tests)."""
    td = getattr(state, "turn_data", None)
    if td is None:
        return
    keys = [k for k in list(td.keys()) if k == "void_global" or k.startswith("void_")]
    for k in keys:
        td.pop(k, None)


# =============================================================================
# System interceptor registration
# =============================================================================

def _ltb_filter(event: Event, state: GameState) -> bool:
    """Match ZONE_CHANGE events that take a nonland permanent off the battlefield."""
    if event.type != EventType.ZONE_CHANGE:
        return False
    if event.payload.get("from_zone_type") != ZoneType.BATTLEFIELD:
        return False
    to_zone_type = event.payload.get("to_zone_type")
    # Leaving the battlefield to anywhere counts (graveyard, exile, hand, library).
    if to_zone_type == ZoneType.BATTLEFIELD:
        return False
    object_id = event.payload.get("object_id")
    obj = state.objects.get(object_id)
    if obj is None:
        return False
    # Lands don't count.
    if CardType.LAND in obj.characteristics.types:
        return False
    return True


def _ltb_handler(event: Event, state: GameState) -> InterceptorResult:
    td = getattr(state, "turn_data", None)
    new_events: list[Event] = []
    if td is not None:
        was_active_global = bool(td.get("void_global"))
        td["void_global"] = True
        # Fire a marker the first time void activates this turn (so UI/triggers
        # can observe the transition). All players are now globally void-active.
        if not was_active_global:
            for pid in list(state.players.keys()):
                new_events.append(Event(
                    type=EventType.VOID_ACTIVATED,
                    payload={"player": pid, "via": "leaves_battlefield"},
                    source=event.source,
                ))
        obj_id = event.payload.get("object_id")
        obj = state.objects.get(obj_id)
        if obj is not None and obj.controller:
            td[f"void_{obj.controller}"] = True
    # Observer: react with marker events only (no game-state changes here).
    return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)


def _destroy_filter(event: Event, state: GameState) -> bool:
    """Match OBJECT_DESTROYED for a nonland permanent.

    We also subscribe to OBJECT_DESTROYED because some legacy paths emit it
    instead of ZONE_CHANGE. Sacrifice/exile of permanents go through
    ZONE_CHANGE in our pipeline, so they're already covered above.
    """
    if event.type != EventType.OBJECT_DESTROYED:
        return False
    obj_id = event.payload.get("object_id")
    obj = state.objects.get(obj_id)
    if obj is None:
        return False
    if CardType.LAND in obj.characteristics.types:
        return False
    # Only count things that were actually on the battlefield.
    # By the time the handler runs, the object's zone has already moved to
    # graveyard, so we can't easily check "was on battlefield". Treat any
    # nonland destruction as void-activating; spells/abilities don't get
    # OBJECT_DESTROYED, only permanents do.
    return True


def _destroy_handler(event: Event, state: GameState) -> InterceptorResult:
    td = getattr(state, "turn_data", None)
    new_events: list[Event] = []
    if td is not None:
        was_active_global = bool(td.get("void_global"))
        td["void_global"] = True
        if not was_active_global:
            for pid in list(state.players.keys()):
                new_events.append(Event(
                    type=EventType.VOID_ACTIVATED,
                    payload={"player": pid, "via": "destroyed"},
                    source=event.source,
                ))
        obj_id = event.payload.get("object_id")
        obj = state.objects.get(obj_id)
        if obj is not None and obj.controller:
            td[f"void_{obj.controller}"] = True
    return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)


def _cast_filter(event: Event, state: GameState) -> bool:
    """Match CAST/SPELL_CAST events for big spells (MV >= 5)."""
    if event.type not in (EventType.CAST, EventType.SPELL_CAST):
        return False
    mv = event.payload.get("mana_value")
    if mv is None:
        return False
    try:
        return int(mv) >= 5
    except (TypeError, ValueError):
        return False


def _cast_handler(event: Event, state: GameState) -> InterceptorResult:
    td = getattr(state, "turn_data", None)
    if td is None:
        return InterceptorResult(action=InterceptorAction.PASS)
    caster = (
        event.payload.get("caster")
        or event.payload.get("controller")
        or event.controller
    )
    new_events: list[Event] = []
    if caster:
        was_active = bool(td.get(f"void_{caster}") or td.get("void_global"))
        td[f"void_{caster}"] = True
        if not was_active:
            new_events.append(Event(
                type=EventType.VOID_ACTIVATED,
                payload={"player": caster, "via": "big_spell_cast"},
                source=event.source,
            ))
    return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)


def register_void_tracker(game: "Game") -> None:
    """Register the three system interceptors that maintain Void state.

    Called from ``Game._setup_system_interceptors``.
    """
    register = game.register_interceptor

    register(Interceptor(
        id=new_id(),
        source="SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_ltb_filter,
        handler=_ltb_handler,
        duration="forever",
    ))

    register(Interceptor(
        id=new_id(),
        source="SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_destroy_filter,
        handler=_destroy_handler,
        duration="forever",
    ))

    register(Interceptor(
        id=new_id(),
        source="SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=_cast_filter,
        handler=_cast_handler,
        duration="forever",
    ))
