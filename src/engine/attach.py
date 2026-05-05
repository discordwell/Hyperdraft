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

from typing import Any, Callable, Optional

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
from .types import new_id as _new_id


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
    unattach the permanent itself if it was attached to something.

    Also revokes any granted activated abilities synchronously: by the time
    the queued UNATTACH events reach REACT, the granted-abilities listener
    has been filtered out (its source is no longer on the battlefield), so
    we revoke here while we still have the source/target binding.
    """
    obj_id = event.payload.get("object_id")
    if not obj_id:
        return InterceptorResult(action=InterceptorAction.PASS)
    obj = state.objects.get(obj_id)
    if obj is None:
        return InterceptorResult(action=InterceptorAction.PASS)

    new_events: list[Event] = []

    # Revoke granted abilities for everything currently attached to obj,
    # then for obj itself if it's attached to something. We do this BEFORE
    # queuing the UNATTACH events so the bookkeeping is consistent even if
    # the listener-driven path doesn't fire.
    for attached_id in list(obj.state.attachments):
        attached = state.objects.get(attached_id)
        if attached is not None:
            target_for_grant = getattr(
                attached.state, "_granted_ability_targets", None
            ) or obj_id
            revoke_granted_abilities(attached_id, target_for_grant, state)
            try:
                delattr(attached.state, "_granted_ability_targets")
            except AttributeError:
                pass
        new_events.append(Event(
            type=EventType.UNATTACH,
            payload={"object_id": attached_id},
            source=obj_id,
            controller=obj.controller,
        ))

    if obj.state.attached_to:
        target_for_grant = getattr(
            obj.state, "_granted_ability_targets", None
        ) or obj.state.attached_to
        revoke_granted_abilities(obj_id, target_for_grant, state)
        try:
            delattr(obj.state, "_granted_ability_targets")
        except AttributeError:
            pass
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
    """Install the leaves-battlefield cleanup interceptor on ``state``.

    Also installs the vehicle-animation auto-falloff system interceptor
    (see ``register_animation_falloff``) so a single call from game.py
    bootstraps all attach-related system interceptors.
    """
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
    register_animation_falloff(state)


# =====================================================================
# BEGIN: vehicle-animation auto-falloff hook (CR 311.7 / 704.5n / 704.5p)
# =====================================================================
#
# When a Vehicle (or any artifact temporarily granted CREATURE) reverts
# to non-creature, CR says:
#   * 704.5p — Equipment attached to an illegal permanent becomes
#     unattached (Equipment stays on the battlefield).
#   * 704.5n — Aura attached to an illegal object is put into its
#     owner's graveyard.
#
# ``falloff_attachments_on_creature_loss`` returns the events to queue;
# the system end_step interceptor (registered alongside attach_cleanup)
# scans the battlefield and fires this for each Vehicle whose
# end-of-turn animation is about to expire.

def falloff_attachments_on_creature_loss(
    host_id: str,
    state: GameState,
) -> list[Event]:
    """Detach Equipment and graveyard Auras from ``host_id``.

    Returns a list of UNATTACH (and ZONE_CHANGE for Auras) events to
    queue. Multiple Equipment / Auras are handled in one pass.
    """
    host = state.objects.get(host_id)
    if host is None:
        return []
    events: list[Event] = []
    for attached_id in list(host.state.attachments):
        attached = state.objects.get(attached_id)
        if attached is None:
            continue
        subs = set(attached.characteristics.subtypes)
        events.append(Event(
            type=EventType.UNATTACH,
            payload={"object_id": attached_id},
            source=host_id, controller=attached.controller,
        ))
        # CR 704.5n: an Aura that becomes unattached goes to its owner's
        # graveyard. Equipment (704.5p) stays on the battlefield.
        if "Aura" in subs:
            events.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    "object_id": attached_id,
                    "from_zone_type": ZoneType.BATTLEFIELD,
                    "to_zone_type": ZoneType.GRAVEYARD,
                    "to_zone_owner": attached.owner,
                    "reason": "aura_falloff",
                },
                source=attached_id, controller=attached.controller,
            ))
    return events


def _animation_falloff_filter(event: Event, state: GameState) -> bool:
    """Fire on PHASE_START step='end_step' (before EOT interceptor sweep)."""
    if event.type != EventType.PHASE_START:
        return False
    return event.payload.get("step") == "end_step"


def _animation_falloff_handler(event: Event, state: GameState) -> InterceptorResult:
    """Scan battlefield for hosts whose ``_grant_creature_type_tag`` interceptor
    is about to expire (duration='end_of_turn'). For each such host, queue
    UNATTACH (Equipment) / Aura→graveyard events so the auto-falloff happens
    BEFORE the EOT interceptor sweep clears the type-grant.
    """
    eot = {"end_of_turn", "until_end_of_turn", "until_eot", "eot",
           "next_end_step", "end_of_this_turn", "this_turn"}
    expiring_hosts: set[str] = set()
    for ic in state.interceptors.values():
        if not hasattr(ic, "_grant_creature_type_tag"):
            continue
        d = getattr(ic, "duration", None)
        if not isinstance(d, str):
            continue
        if d.strip().lower().replace(" ", "_") in eot:
            src = ic.source
            if src and src in state.objects:
                expiring_hosts.add(src)
    new_events: list[Event] = []
    for host_id in expiring_hosts:
        new_events.extend(falloff_attachments_on_creature_loss(host_id, state))
    if not new_events:
        return InterceptorResult(action=InterceptorAction.PASS)
    return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)


def register_animation_falloff(state: GameState) -> None:
    """Install the system-level end_step interceptor that handles auto-falloff."""
    cid = "system:animation_falloff"
    if cid not in state.interceptors:
        state.interceptors[cid] = Interceptor(
            id=cid,
            source="system",
            controller=None,
            priority=InterceptorPriority.REACT,
            filter=_animation_falloff_filter,
            handler=_animation_falloff_handler,
            duration="forever",
        )

# =====================================================================
# END: vehicle-animation auto-falloff hook
# =====================================================================


# ----------------------------------------------------------------------
# Granted activated abilities: "Equipped creature has '<cost>: <effect>'"
# ----------------------------------------------------------------------
#
# Equipment / Aura grants an activated ability to the creature it's attached
# to. The ability lives on the equipped creature's ``state.activated_abilities``
# (so the priority system discovers it like any other activated ability),
# but is tagged with ``_granted_by = <equipment_id>`` so that:
#   - On UNATTACH, the equipment can find and remove the ability it granted.
#   - When the equipment leaves the battlefield, the
#     ``register_attach_cleanup`` interceptor emits UNATTACH which feeds the
#     same removal path.
#
# The activated-ability descriptor's ``effect_fn`` is invoked with the
# equipped creature as ``obj`` (because that's where the descriptor lives),
# which is the correct semantics for "Equipped creature has '<cost>: <effect>'".


GrantedAbilitySpec = dict  # {'cost': str, 'effect_fn': Callable, 'description': str, ...}


def _normalise_granted_specs(
    granted: Optional[Any],
) -> list[GrantedAbilitySpec]:
    """Accept None / single dict / list of dicts; return a list."""
    if granted is None:
        return []
    if isinstance(granted, dict):
        return [granted]
    return list(granted)


def grant_activated_ability_on_attach(
    target: GameObject,
    source_id: str,
    spec: GrantedAbilitySpec,
    state: Optional[GameState] = None,
) -> None:
    """Register an activated ability on ``target`` tagged with ``_granted_by=source_id``.

    The descriptor is appended to ``target.state.activated_abilities`` so the
    priority system discovers it. Defensive against double-registration: if a
    descriptor with the same source and effect_fn already exists on the target,
    no-op.
    """
    # Defensive import: avoid an import cycle since ``activated`` itself uses
    # types from this module's package.
    from .activated import register_activated_ability

    cost = spec.get("cost", "")
    effect_fn = spec.get("effect_fn")
    description = spec.get("description", "")
    sorcery_speed = spec.get("sorcery_speed", False)
    own_turn_only = spec.get("own_turn_only", False)
    once_per_turn = spec.get("once_per_turn", False)
    once_per_game = spec.get("once_per_game", False)
    targets_required = spec.get("targets_required", 0)
    target_kind = spec.get("target_kind", "any")

    if effect_fn is None:
        return

    abilities = getattr(target.state, "activated_abilities", None) or []
    for existing in abilities:
        if getattr(existing, "_granted_by", None) == source_id:
            existing_code = getattr(getattr(existing, "effect_fn", None), "__code__", None)
            new_code = getattr(effect_fn, "__code__", None)
            if existing_code is not None and new_code is not None and existing_code is new_code:
                return  # already granted

    ability = register_activated_ability(
        target,
        cost=cost,
        effect_fn=effect_fn,
        description=description,
        sorcery_speed=sorcery_speed,
        own_turn_only=own_turn_only,
        once_per_turn=once_per_turn,
        once_per_game=once_per_game,
        targets_required=targets_required,
        target_kind=target_kind,
    )
    setattr(ability, "_granted_by", source_id)


def revoke_granted_abilities(
    source_id: str,
    target_id: Optional[str],
    state: GameState,
) -> None:
    """Strip every activated ability tagged ``_granted_by == source_id`` from
    ``target_id``'s descriptor list.

    When ``target_id`` is None we sweep every battlefield object — used by
    the leaves-bf path where the equipment's ``attached_to`` may already be
    cleared.
    """
    candidates: list[GameObject] = []
    if target_id and target_id in state.objects:
        candidates.append(state.objects[target_id])
    else:
        # Fallback: scan all objects (rare; only when caller has lost track).
        candidates.extend(state.objects.values())

    for target in candidates:
        abilities = getattr(target.state, "activated_abilities", None)
        if not abilities:
            continue
        kept = [
            a for a in abilities
            if getattr(a, "_granted_by", None) != source_id
        ]
        if len(kept) != len(abilities):
            target.state.activated_abilities = kept
            # Re-index ability_index so the priority system's "activated:N"
            # action ids stay 0-based and contiguous.
            for i, a in enumerate(kept):
                a.ability_index = i


def make_granted_abilities_listener(
    source_obj: GameObject,
    granted: Optional[Any],
) -> Optional[Interceptor]:
    """Build an ATTACH/UNATTACH REACT interceptor that grants/revokes the
    activated abilities described in ``granted`` on the creature
    ``source_obj`` is currently attached to.

    ``granted`` is a single ``{cost, effect_fn, description, ...}`` dict, or
    a list of such dicts. The interceptor stashes the most recent target id
    on ``source_obj.state._granted_ability_targets`` so UNATTACH can find
    the target even after ``attached_to`` has been cleared.
    """
    specs = _normalise_granted_specs(granted)
    if not specs:
        return None

    source_id = source_obj.id
    controller_id = source_obj.controller

    def _filter(event: Event, state: GameState) -> bool:
        if event.type in (EventType.ATTACH, EventType.UNATTACH):
            return event.payload.get("object_id") == source_id
        # Also revoke synchronously when the equipment leaves the battlefield.
        # The async UNATTACH path emitted by system:attach_cleanup runs AFTER
        # _cleanup_departed_interceptors strips this listener, so we have to
        # catch the ZONE_CHANGE in the same REACT phase before cleanup runs.
        if event.type == EventType.ZONE_CHANGE:
            if event.payload.get("object_id") != source_id:
                return False
            from_t = event.payload.get("from_zone_type")
            to_t = event.payload.get("to_zone_type")
            return from_t == ZoneType.BATTLEFIELD and to_t != ZoneType.BATTLEFIELD
        return False

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        source = state.objects.get(source_id)
        if source is None:
            return InterceptorResult(action=InterceptorAction.PASS)

        if event.type == EventType.ATTACH:
            target_id = event.payload.get("target_id") or event.payload.get("target")
            if not target_id:
                return InterceptorResult(action=InterceptorAction.PASS)
            target = state.objects.get(target_id)
            if target is None:
                return InterceptorResult(action=InterceptorAction.PASS)
            # If we were already granting to a different creature, revoke first.
            prior = getattr(source.state, "_granted_ability_targets", None)
            if prior and prior != target_id:
                revoke_granted_abilities(source_id, prior, state)
            new_events: list[Event] = []
            for spec in specs:
                grant_activated_ability_on_attach(target, source_id, spec, state)
                # Emit a marker event for observers (tests, AI). The pipeline
                # has no built-in handler for this type — it's purely a
                # broadcast that "ability X was granted to target Y".
                new_events.append(Event(
                    type=EventType.GRANT_ACTIVATED_ABILITY,
                    payload={
                        "target_id": target_id,
                        "source_id": source_id,
                        "cost": spec.get("cost", ""),
                        "effect_fn": spec.get("effect_fn"),
                        "description": spec.get("description", ""),
                    },
                    source=source_id,
                    controller=controller_id,
                ))
            setattr(source.state, "_granted_ability_targets", target_id)
            if new_events:
                return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)
            return InterceptorResult(action=InterceptorAction.PASS)

        # UNATTACH or ZONE_CHANGE leaving battlefield: revoke.
        prior = getattr(source.state, "_granted_ability_targets", None)
        revoke_granted_abilities(source_id, prior, state)
        try:
            delattr(source.state, "_granted_ability_targets")
        except AttributeError:
            pass
        return InterceptorResult(action=InterceptorAction.PASS)

    return Interceptor(
        id=_new_id(),
        source=source_id,
        controller=controller_id,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="while_on_battlefield",
    )


__all__ = [
    "ATTACH_EVENT_HANDLERS",
    "register_attach_cleanup",
    "grant_activated_ability_on_attach",
    "revoke_granted_abilities",
    "make_granted_abilities_listener",
    "falloff_attachments_on_creature_loss",
    "register_animation_falloff",
]
