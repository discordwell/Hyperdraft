"""
Yu-Gi-Oh!-specific zone-movement handlers.

YGO_DESTROY and YGO_SEND_TO_GY are *effect families*: a card's resolver/trigger
emits one of these events with the targets, and the pipeline performs the
zone manipulation and emits per-card notification events (YGO_DESTROYED /
YGO_SENT_TO_GY) so downstream triggers can react.

Distinction (YGO rules):
- *Destroyed*: card was destroyed by battle or by an effect (counts for cards
  like "If this card is destroyed: ...").
- *Sent to GY*: card was sent to GY for any reason (tribute, discard, cost,
  destruction). Destruction implies "sent to GY", but "sent to GY" does NOT
  imply destruction.

This handler emits *both* a YGO_DESTROYED and a YGO_SENT_TO_GY notification
when a card is destroyed, so triggers keyed on either path fire correctly.

Pre-existing legacy code in src/cards/yugioh/** still emits YGO_DESTROY with a
single ``card_id`` payload after manually moving the card itself. To stay
backwards compatible the handler treats that shape as a *post-move
notification* (no zone manipulation) and only fans out YGO_DESTROYED.
"""

from typing import Optional

from ...types import (
    Event, EventType, GameState, ZoneType,
)


def _zone_key_for_card(state: GameState, card_id: str) -> Optional[str]:
    """Find the zone-key currently holding ``card_id`` (slot None entries count as absent)."""
    for key, zone in state.zones.items():
        if card_id in zone.objects:
            return key
    return None


def _remove_from_any_zone(state: GameState, card_id: str) -> Optional[str]:
    """Remove ``card_id`` from whatever zone holds it. Returns the zone-key it left, if any.

    Slotted zones (monster_zone_*, spell_trap_zone_*) preserve slot order by
    setting the slot to ``None`` instead of removing it. All other zones drop
    the entry entirely.
    """
    departed_key: Optional[str] = None
    for zone_key, zone in state.zones.items():
        if card_id not in zone.objects:
            continue
        departed_key = zone_key
        if "monster_zone_" in zone_key or "spell_trap_zone_" in zone_key:
            for i, oid in enumerate(zone.objects):
                if oid == card_id:
                    zone.objects[i] = None
                    break
        else:
            while card_id in zone.objects:
                zone.objects.remove(card_id)
        # A card lives in exactly one zone — stop after we found it.
        break
    return departed_key


def _move_to_graveyard(state: GameState, card_id: str) -> tuple[Optional[str], Optional[object]]:
    """Move ``card_id`` to its owner's graveyard. Returns (from_zone_key, obj)."""
    obj = state.objects.get(card_id)
    if obj is None:
        return (None, None)
    from_zone = _remove_from_any_zone(state, card_id)
    gy = state.zones.get(f"graveyard_{obj.owner}")
    if gy is not None and card_id not in gy.objects:
        gy.objects.append(card_id)
    obj.zone = ZoneType.GRAVEYARD
    # YGO cleanup: cards in GY are face-up, position cleared.
    if hasattr(obj, "state") and obj.state is not None:
        obj.state.face_down = False
        obj.state.ygo_position = None
    return (from_zone, obj)


def _handle_ygo_destroy(event: Event, state: GameState):
    """Handle ``YGO_DESTROY`` as an effect family.

    Payload (preferred):
        target_ids: list[str]   — cards to destroy
        source_id:  str         — the card causing the destruction
        reason:     str         — optional sub-reason ('battle', 'effect', ...)

    Backwards-compatible legacy shape (cards that already moved the card and
    emit YGO_DESTROY as a *notification*):
        card_id: str            — already moved; we only fan out YGO_DESTROYED

    Returns the list of follow-up YGO_DESTROYED + YGO_SENT_TO_GY events.
    """
    follow_ups: list[Event] = []
    source_id = event.payload.get("source_id") or event.source
    reason = event.payload.get("reason", "effect")

    target_ids = event.payload.get("target_ids")
    if target_ids:
        # New API path — actually destroy each target.
        for tid in list(target_ids):
            obj_before = state.objects.get(tid)
            if obj_before is None:
                continue
            controller_before = obj_before.controller
            name_before = obj_before.name
            from_zone, obj_after = _move_to_graveyard(state, tid)
            if obj_after is None:
                continue
            follow_ups.append(Event(
                type=EventType.YGO_DESTROYED,
                payload={
                    "card_id": tid,
                    "card_name": name_before,
                    "owner": obj_after.owner,
                    "controller": controller_before,
                    "from_zone": from_zone or "",
                    "reason": reason,
                    "source_id": source_id,
                },
                source=source_id,
            ))
            follow_ups.append(Event(
                type=EventType.YGO_SENT_TO_GY,
                payload={
                    "card_id": tid,
                    "card_name": name_before,
                    "owner": obj_after.owner,
                    "controller": controller_before,
                    "from_zone": from_zone or "",
                    "reason": reason,
                },
                source=source_id,
            ))
        return follow_ups

    # Legacy single-card notification path: card was already moved by the
    # emitting code. We still fan out the destroyed/sent-to-GY notification
    # events so triggers keyed on YGO_DESTROYED/YGO_SENT_TO_GY can react.
    card_id = event.payload.get("card_id")
    if not card_id:
        return follow_ups
    obj = state.objects.get(card_id)
    if obj is None:
        return follow_ups
    follow_ups.append(Event(
        type=EventType.YGO_DESTROYED,
        payload={
            "card_id": card_id,
            "card_name": event.payload.get("card_name", obj.name),
            "owner": obj.owner,
            "controller": obj.controller,
            "from_zone": event.payload.get("from_zone", ""),
            "reason": reason,
            "source_id": source_id,
        },
        source=source_id,
    ))
    follow_ups.append(Event(
        type=EventType.YGO_SENT_TO_GY,
        payload={
            "card_id": card_id,
            "card_name": event.payload.get("card_name", obj.name),
            "owner": obj.owner,
            "controller": obj.controller,
            "from_zone": event.payload.get("from_zone", ""),
            "reason": reason,
        },
        source=source_id,
    ))
    return follow_ups


def _handle_ygo_send_to_gy(event: Event, state: GameState):
    """Handle ``YGO_SEND_TO_GY`` as an effect family.

    Payload:
        card_id:   str          — card to send to GY (from any zone)
        from_zone: str          — optional hint; we compute it ourselves anyway
        reason:    str          — e.g. 'tribute', 'discard', 'cost', 'effect'

    Returns ``[YGO_SENT_TO_GY]`` so downstream triggers can react. Does *not*
    emit YGO_DESTROYED — being sent to GY is a strictly weaker event than
    being destroyed.
    """
    card_id = event.payload.get("card_id")
    if not card_id:
        return []
    obj_before = state.objects.get(card_id)
    if obj_before is None:
        return []
    controller_before = obj_before.controller
    name_before = obj_before.name
    reason = event.payload.get("reason", "effect")
    from_zone, obj_after = _move_to_graveyard(state, card_id)
    if obj_after is None:
        return []
    return [Event(
        type=EventType.YGO_SENT_TO_GY,
        payload={
            "card_id": card_id,
            "card_name": name_before,
            "owner": obj_after.owner,
            "controller": controller_before,
            "from_zone": from_zone or event.payload.get("from_zone", ""),
            "reason": reason,
        },
        source=event.source,
    )]
