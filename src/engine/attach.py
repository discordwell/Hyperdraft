"""Phase 3: Equipment / Aura attach mechanic.

This module wires the ATTACH and UNATTACH events through the pipeline and
exposes helpers to register the static effects an Equipment or Aura grants
to its attached permanent.

Flow:
- An Equipment registers an *equip* activated ability via the Phase 4
  framework (cards.interceptor_helpers.make_equip_ability). Activating it
  pays the equip cost and emits an ATTACH event from the equipment to the
  chosen creature you control. Sorcery-speed by default.
- An Aura, on resolution, ETBs already attached. The aura's setup function
  emits an ATTACH after its zone change to BATTLEFIELD.
- Static effects on the attached permanent are expressed via QUERY_POWER /
  QUERY_TOUGHNESS / QUERY_ABILITIES interceptors whose filter checks
  ``target.id == source.state.attached_to``.

Pipeline integration:
- ATTACH and UNATTACH are registered in EVENT_HANDLERS via
  ATTACH_EVENT_HANDLERS, mirroring the saga / face-down pattern.
- A leaves-battlefield cleanup interceptor is registered as a system
  interceptor so attached objects detach when the host leaves the
  battlefield (or vice-versa).
"""
from __future__ import annotations

from typing import Optional

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
)


# ----------------------------------------------------------------------
# EVENT_HANDLERS-style handlers
# ----------------------------------------------------------------------


def _handle_attach(event: Event, state: GameState) -> list[Event]:
    """Resolve an ATTACH event by mutating obj.state.attached_to.

    If the source was previously attached to a different permanent, that
    prior host's attachments list is cleaned up inline before the new
    binding is set.
    """
    source_id = event.payload.get("object_id") or event.payload.get("source_id")
    target_id = event.payload.get("target_id") or event.payload.get("target")
    if source_id is None or target_id is None:
        return []

    source = state.objects.get(source_id)
    target = state.objects.get(target_id)
    if source is None or target is None:
        return []

    # Detach from prior host, if any, before re-attaching.
    prior = source.state.attached_to
    if prior and prior != target_id:
        prior_obj = state.objects.get(prior)
        if prior_obj and source_id in prior_obj.state.attachments:
            prior_obj.state.attachments.remove(source_id)

    source.state.attached_to = target_id
    if source_id not in target.state.attachments:
        target.state.attachments.append(source_id)

    return []


def _handle_unattach(event: Event, state: GameState) -> list[Event]:
    """Resolve an UNATTACH event by clearing the back-pointer."""
    source_id = event.payload.get("object_id") or event.payload.get("source_id")
    if source_id is None:
        return []

    source = state.objects.get(source_id)
    if source is None:
        return []

    prior = source.state.attached_to
    source.state.attached_to = None

    if prior:
        prior_obj = state.objects.get(prior)
        if prior_obj and source_id in prior_obj.state.attachments:
            prior_obj.state.attachments.remove(source_id)

    return []


ATTACH_EVENT_HANDLERS = {
    EventType.ATTACH: _handle_attach,
    EventType.UNATTACH: _handle_unattach,
}


# ----------------------------------------------------------------------
# Cleanup on zone change (system interceptor)
# ----------------------------------------------------------------------


def _cleanup_filter(event: Event, state: GameState) -> bool:
    """Catch ZONE_CHANGE leaving battlefield."""
    if event.type != EventType.ZONE_CHANGE:
        return False
    payload = event.payload
    from_zone = payload.get("from_zone_type")
    to_zone = payload.get("to_zone_type")
    if from_zone is None:
        return False
    return from_zone == ZoneType.BATTLEFIELD and to_zone != ZoneType.BATTLEFIELD


def _cleanup_handler(event: Event, state: GameState) -> InterceptorResult:
    """When a permanent leaves the battlefield, unattach anything on it AND
    unattach the permanent itself if it was attached to something."""
    obj_id = event.payload.get("object_id")
    if not obj_id:
        return InterceptorResult(action=InterceptorAction.PASS)
    obj = state.objects.get(obj_id)
    if obj is None:
        return InterceptorResult(action=InterceptorAction.PASS)

    new_events: list[Event] = []

    for attached_id in list(obj.state.attachments):
        new_events.append(Event(
            type=EventType.UNATTACH,
            payload={"object_id": attached_id},
            source=obj_id,
            controller=obj.controller,
        ))

    if obj.state.attached_to:
        new_events.append(Event(
            type=EventType.UNATTACH,
            payload={"object_id": obj_id},
            source=obj_id,
            controller=obj.controller,
        ))

    if not new_events:
        return InterceptorResult(action=InterceptorAction.PASS)
    return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)


def register_attach_cleanup(state: GameState) -> None:
    """Install the leaves-battlefield cleanup interceptor on ``state``."""
    cid = "system:attach_cleanup"
    if cid not in state.interceptors:
        state.interceptors[cid] = Interceptor(
            id=cid,
            source="system",
            controller=None,
            priority=InterceptorPriority.REACT,
            filter=_cleanup_filter,
            handler=_cleanup_handler,
            duration="forever",
        )


__all__ = [
    "ATTACH_EVENT_HANDLERS",
    "register_attach_cleanup",
]
