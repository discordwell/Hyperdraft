"""
Face-down permanents (Manifest / Manifest Dread / Cloak / Disguise / Morph).

Concept
-------
While a permanent is face-down, observers (combat, opponents, query helpers)
must see it as a vanilla 2/2 colourless creature with no name and no abilities.
The card's real characteristics are still stored on the GameObject — they are
*hidden* by interceptors, not erased — so flipping it face-up is just a matter
of toggling ``obj.state.face_down`` and re-running the card's
``setup_interceptors``.

What this module exposes
------------------------
* ``register_face_down_handler`` — wires :data:`EventType.TURN_FACE_UP` into the
  pipeline's ``EVENT_HANDLERS`` dict on first import. Idempotent.
* ``turn_face_up(obj, state)`` — flip a permanent face-up, drop the masking
  interceptors, and re-register its real ``setup_interceptors``.
* ``make_face_down_object(...)`` — low-level factory used by ``OBJECT_CREATED``
  payloads built from :func:`make_manifest_etb_event` (interceptor_helpers).

This module imports lazily from :mod:`.pipeline.handlers` to avoid the circular
import that would otherwise occur during ``src.engine`` package initialization.
"""

from __future__ import annotations

from typing import Optional

from .types import (
    Event,
    EventType,
    GameObject,
    GameState,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    ZoneType,
)


# =============================================================================
# Public API
# =============================================================================

# Tag stored on each face-down masking interceptor so we can identify and remove
# them on flip without disturbing other QUERY effects on the object.
FACE_DOWN_TAG = "face_down_mask"

# Default vanilla face-down profile (CR 711.2). Mechanics that override these
# values (notably Disguise / Morph -> "face-down 2/2 with ward {2}") can do so
# by passing ``face_down_keywords=[...]`` to the helper that builds the mask.
DEFAULT_FACE_DOWN_POWER = 2
DEFAULT_FACE_DOWN_TOUGHNESS = 2


def is_face_down(obj: GameObject) -> bool:
    """Return True if obj is currently face-down."""
    state = getattr(obj, "state", None)
    return bool(getattr(state, "face_down", False)) if state else False


def turn_face_up(obj: GameObject, state: GameState) -> None:
    """
    Flip ``obj`` face-up: clear the face-down flag, restore characteristics
    from the underlying card_def, remove masking interceptors, and re-run
    ``card_def.setup_interceptors`` so the card's real abilities come online.

    Safe to call on an already-face-up object (no-ops).
    """
    import copy
    if not is_face_down(obj):
        return

    obj.state.face_down = False

    # Restore real characteristics from the underlying card definition.
    # When the object was minted face-down (via OBJECT_CREATED with face_down=True),
    # its `characteristics` were intentionally blank — the underlying card's
    # real values are stored on `obj.card_def`. We deep-copy so per-object
    # mutations (counters, type changes, etc.) don't bleed between objects.
    card_def = getattr(obj, "card_def", None)
    if card_def is not None and getattr(card_def, "characteristics", None) is not None:
        obj.characteristics = copy.deepcopy(card_def.characteristics)
        # Also restore the public name, which face-down hides.
        if not obj.name and getattr(card_def, "name", None):
            obj.name = card_def.name

    # Strip the masking interceptors we registered when the object went face-down.
    to_remove: list[str] = []
    for int_id in list(obj.interceptor_ids):
        interceptor = state.interceptors.get(int_id)
        if interceptor is None:
            continue
        if getattr(interceptor, "_face_down_tag", None) == FACE_DOWN_TAG:
            to_remove.append(int_id)
    for int_id in to_remove:
        if int_id in state.interceptors:
            del state.interceptors[int_id]
        if int_id in obj.interceptor_ids:
            obj.interceptor_ids.remove(int_id)

    # Re-run the card's setup_interceptors now that the card is "really" itself.
    # Mirrors the path taken by _handle_zone_change when a permanent enters the
    # battlefield from a hidden zone. We also fire a synthetic ZONE_CHANGE
    # marker so generic ETB triggers (make_etb_trigger) — which filter on
    # ZONE_CHANGE -> BATTLEFIELD — see this card "entering" face-up. CR 707.4.
    if card_def is not None and getattr(card_def, "setup_interceptors", None):
        new_interceptors = card_def.setup_interceptors(obj, state) or []
        for interceptor in new_interceptors:
            interceptor.timestamp = state.next_timestamp()
            state.interceptors[interceptor.id] = interceptor
            obj.interceptor_ids.append(interceptor.id)

    # Fire ETB triggers as if the card were entering the battlefield now.
    # (Per CR 707.4, turning face-up is treated as "becoming a new permanent"
    # for the purposes of triggers like "when this enters".)
    flip_zone_change = Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.BATTLEFIELD,
            'face_up_flip': True,
        },
        source=obj.id,
        controller=obj.controller,
    )
    # Direct emit through the pipeline so REACT triggers fire and downstream
    # events resolve.
    pipeline = getattr(state, '_pipeline', None)
    if pipeline is None:
        # State may not have a pipeline reference — but most flows route through
        # Game.emit which does. We append to pending_events as a fallback.
        state.pending_events.append(flip_zone_change)
    else:
        pipeline.emit(flip_zone_change)


# =============================================================================
# Pipeline handler — TURN_FACE_UP
# =============================================================================

def _handle_turn_face_up(event: Event, state: GameState):
    """
    Resolve a TURN_FACE_UP event.

    Payload:
        object_id: str — the permanent being turned face-up.
        mana_paid_cost: str (optional) — the morph/disguise cost that was paid.
            Recorded on the event for downstream triggers; not consumed here.
    """
    object_id = event.payload.get("object_id")
    if not object_id or object_id not in state.objects:
        return
    obj = state.objects[object_id]
    if obj.zone != ZoneType.BATTLEFIELD:
        return
    turn_face_up(obj, state)
    # Surface a marker event so triggers ("when CARD is turned face-up") can fire.
    event.payload["object_id"] = object_id


def register_face_down_handler() -> None:
    """
    Idempotently register the TURN_FACE_UP handler in the global EVENT_HANDLERS
    dict.

    Called from :mod:`src.engine.pipeline.handlers` package init via the
    auto-registration hook below; safe to call directly from tests too.
    """
    # Lazy import to avoid circular imports during pipeline.handlers init.
    from .pipeline.handlers import EVENT_HANDLERS

    EVENT_HANDLERS.setdefault(EventType.TURN_FACE_UP, _handle_turn_face_up)


# =============================================================================
# Object factory — used by make_manifest_etb_event in interceptor_helpers
# =============================================================================

def make_face_down_object(
    state: GameState,
    *,
    controller: str,
    owner: Optional[str] = None,
    card_def=None,
    power: int = DEFAULT_FACE_DOWN_POWER,
    toughness: int = DEFAULT_FACE_DOWN_TOUGHNESS,
    name: str = "",
) -> GameObject:
    """
    Create a face-down permanent on the battlefield.

    Caller is responsible for emitting any subsequent triggers
    (FACE_DOWN_ENTER, ZONE_CHANGE markers, etc.). This builder handles only
    construction; the standard pipeline path is to fire an OBJECT_CREATED event
    whose payload is built by :func:`make_manifest_etb_event`.
    """
    from .types import (
        Characteristics,
        GameObject as _GameObject,
        ObjectState,
        new_id,
    )

    owner = owner or controller
    obj_id = new_id()
    obj = _GameObject(
        id=obj_id,
        name=name or "",
        owner=owner,
        controller=controller,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types=set(),                      # masked by QUERY interceptors
            colors=set(),                     # masked
            mana_cost=None,
            power=power,
            toughness=toughness,
            abilities=[],
        ),
        state=ObjectState(face_down=True, summoning_sickness=True),
        card_def=card_def,
        created_at=state.next_timestamp(),
        entered_zone_at=state.timestamp,
        _state_ref=state,
    )
    state.objects[obj_id] = obj
    if "battlefield" in state.zones:
        state.zones["battlefield"].objects.append(obj_id)
    return obj
