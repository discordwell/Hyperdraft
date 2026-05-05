"""
Cast-from-zone permission system (W7).

Today the priority system only lets a player cast a card from HAND, with a
small number of bespoke exceptions wired directly into ``_handle_cast_spell``
(WOE Adventure, EOE Warp, the graveyard-cast options for Flashback /
Harmonize / Mayhem). This module provides a generalised mechanism so a card
or effect can grant *permission* for a specific card to be cast from another
zone (graveyard, exile, library top, etc.) without each card having to patch
``priority.py`` directly.

Design
------
Permissions are registered as QUERY-priority interceptors filtered on
``EventType.QUERY_CAST_LEGALITY``. The priority handler builds a synthetic
event for the casting card and fires it before its zone check. Any
interceptor that recognises the card-id + zone combination flips
``payload['allowed'] = True``. Optionally an interceptor may set
``payload['cost_override']`` to a ``ManaCost`` (or callable returning one)
so the card is cast for that alternative cost.

This module exposes:

  - ``make_castable_from_zone(source, *, target_card_id, zone, ...)`` —
    returns a list of interceptors to register (typically one).
  - ``is_castable_from_zone(card_id, current_zone, state)`` — utility used
    by the priority handler (and ``get_legal_actions``) to ask "can this
    card be cast from this zone right now?".
  - ``query_cast_permission(card_id, zone, player_id, state)`` — internal
    helper that returns the full payload (allowed + optional cost_override).

The system is intentionally narrow: it does not (yet) replace the bespoke
flashback/adventure handling, because those mechanics carry additional
side-effects (cost-plan integration, exile-on-leave-stack, ...). It is the
right tool for one-off effects like "you may cast the exiled card this
turn" or "you may cast an instant or sorcery from the top of your library".
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Union

from .types import (
    Event, EventType, GameState, GameObject,
    Interceptor, InterceptorAction, InterceptorPriority, InterceptorResult,
    ZoneType, new_id,
)
from .mana import ManaCost


# Payload keys for the synthetic QUERY_CAST_LEGALITY event.
ALLOWED_KEY = "allowed"
COST_OVERRIDE_KEY = "cost_override"

CostModifier = Union[ManaCost, Callable[[GameObject, GameState], ManaCost], None]


def _normalize_zone(zone: Union[ZoneType, str]) -> ZoneType:
    """Accept either a ZoneType enum or a friendly string ('graveyard', etc.)."""
    if isinstance(zone, ZoneType):
        return zone
    if isinstance(zone, str):
        key = zone.strip().lower()
        aliases = {
            "hand": ZoneType.HAND,
            "graveyard": ZoneType.GRAVEYARD,
            "gy": ZoneType.GRAVEYARD,
            "exile": ZoneType.EXILE,
            "library": ZoneType.LIBRARY,
            "library_top": ZoneType.LIBRARY,
            "top": ZoneType.LIBRARY,
            "battlefield": ZoneType.BATTLEFIELD,
            "command": ZoneType.COMMAND,
        }
        if key in aliases:
            return aliases[key]
    raise ValueError(f"Unrecognised zone: {zone!r}")


def make_castable_from_zone(
    source_obj: GameObject,
    *,
    target_card_id: str,
    zone: Union[ZoneType, str],
    duration: str = "permanent",
    cost_modifier: CostModifier = None,
    library_top_only: bool = False,
) -> list[Interceptor]:
    """
    Grant permission to cast ``target_card_id`` from ``zone``.

    Args:
        source_obj: the object granting the permission (used for ownership
            and lifetime tracking).
        target_card_id: the card the permission applies to. Use the special
            sentinel value ``"*"`` to allow any card the source owns.
        zone: the zone the card may be cast from (ZoneType enum or friendly
            string like ``"graveyard"`` / ``"exile"`` / ``"library_top"``).
        duration: lifetime of the permission. Standard values:
            * ``"permanent"`` — until the source leaves the battlefield
              (default; aliased internally to ``"while_on_battlefield"`` so
              the pipeline auto-sweeps it).
            * ``"end_of_turn"`` — cleared by TurnManager EOT sweep.
            * ``"forever"`` — never auto-cleared (use sparingly).
        cost_modifier: either a ``ManaCost`` to use instead of the printed
            cost, or a callable ``(card, state) -> ManaCost``. ``None`` means
            "still pay the normal cost."
        library_top_only: when ``zone == LIBRARY``, only allow casting if the
            target card is the *top* card of its owner's library.

    Returns:
        A list of interceptors. Caller is responsible for registering them
        on ``state.interceptors`` (typical pattern: append to the return
        value of a ``setup_interceptors`` function).
    """
    target_zone = _normalize_zone(zone)

    # Map the "permanent" alias to the engine's pipeline-aware duration so
    # the standard cleanup-on-leave-battlefield sweep collects this for us.
    effective_duration = duration
    if duration == "permanent":
        effective_duration = "while_on_battlefield"

    source_id = source_obj.id

    def cast_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_CAST_LEGALITY:
            return False
        # The source must still exist; for non-self_only durations we also
        # require it to be on the battlefield (the pipeline normally enforces
        # this for ``while_on_battlefield`` interceptors, but cast-legality
        # queries don't go through the pipeline so we re-check here).
        src = state.objects.get(source_id)
        if src is None:
            return False
        if effective_duration == "while_on_battlefield" and src.zone != ZoneType.BATTLEFIELD:
            return False

        card_id = event.payload.get("card_id")
        if not card_id:
            return False
        if target_card_id != "*" and card_id != target_card_id:
            return False

        candidate = state.objects.get(card_id)
        if candidate is None:
            return False
        # The card must currently live in the granted zone for the permission
        # to fire. If it has already moved, the permission silently no-ops.
        if candidate.zone != target_zone:
            return False

        if library_top_only and target_zone == ZoneType.LIBRARY:
            owner_id = candidate.owner
            lib_zone = state.zones.get(f"library_{owner_id}")
            if lib_zone is None or not lib_zone.objects:
                return False
            # Convention: the "top" of the library is the LAST element of the
            # zone's objects list (mirrors how src/engine/library_search.py
            # treats library top).
            if lib_zone.objects[-1] != card_id:
                return False

        return True

    def cast_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload[ALLOWED_KEY] = True

        if cost_modifier is not None:
            try:
                if callable(cost_modifier):
                    candidate = state.objects.get(event.payload.get("card_id"))
                    override = cost_modifier(candidate, state)
                else:
                    override = cost_modifier
                if isinstance(override, ManaCost):
                    new_event.payload[COST_OVERRIDE_KEY] = override
            except Exception:
                # A bad cost_modifier shouldn't take down the cast-legality
                # query - we just skip the override and leave the printed
                # cost in place.
                pass

        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=cast_filter,
        handler=cast_handler,
        duration=effective_duration,
    )
    return [interceptor]


def query_cast_permission(
    card_id: str,
    current_zone: ZoneType,
    player_id: str,
    state: GameState,
) -> dict:
    """
    Run the QUERY_CAST_LEGALITY query for ``card_id``. Returns a dict with
    keys ``allowed`` (bool) and optionally ``cost_override`` (ManaCost).

    HAND is always allowed; this is a fast path so callers don't have to
    special-case it themselves.
    """
    if current_zone == ZoneType.HAND:
        return {ALLOWED_KEY: True}

    event = Event(
        type=EventType.QUERY_CAST_LEGALITY,
        payload={
            "card_id": card_id,
            "current_zone": current_zone,
            "player_id": player_id,
            ALLOWED_KEY: False,
        },
        controller=player_id,
    )

    # Sort by timestamp for deterministic ordering (matches cost_query.py).
    interceptors = sorted(
        [
            i for i in state.interceptors.values()
            if i.priority == InterceptorPriority.QUERY
        ],
        key=lambda i: i.timestamp,
    )

    allowed = False
    cost_override: Optional[ManaCost] = None

    for interceptor in interceptors:
        try:
            if not interceptor.filter(event, state):
                continue
        except Exception:
            continue
        try:
            result = interceptor.handler(event, state)
        except Exception:
            continue
        if not result or not result.transformed_event:
            continue
        payload = result.transformed_event.payload
        if payload.get(ALLOWED_KEY):
            allowed = True
            override = payload.get(COST_OVERRIDE_KEY)
            if isinstance(override, ManaCost):
                cost_override = override

    out: dict[str, Any] = {ALLOWED_KEY: allowed}
    if cost_override is not None:
        out[COST_OVERRIDE_KEY] = cost_override
    return out


def is_castable_from_zone(card_id: str, current_zone: ZoneType, state: GameState) -> bool:
    """Convenience boolean for "can this card be cast from this zone?".

    HAND always returns True. For other zones the QUERY_CAST_LEGALITY event
    is fired and any granting interceptor will flip the allowed flag.
    """
    obj = state.objects.get(card_id)
    if obj is None:
        return False
    payload = query_cast_permission(card_id, current_zone, obj.owner, state)
    return bool(payload.get(ALLOWED_KEY))


def cost_override_for(card_id: str, current_zone: ZoneType, state: GameState) -> Optional[ManaCost]:
    """Return the cost override published by the granting interceptor, or None."""
    obj = state.objects.get(card_id)
    if obj is None:
        return None
    payload = query_cast_permission(card_id, current_zone, obj.owner, state)
    override = payload.get(COST_OVERRIDE_KEY)
    return override if isinstance(override, ManaCost) else None
