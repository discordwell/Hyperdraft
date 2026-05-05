"""
Type-grant handlers.

Handles ``GRANT_CREATURE_TYPE`` — install a TRANSFORM-priority interceptor on
``EventType.QUERY_TYPES`` for the target object that adds ``CardType.CREATURE``
to the live type set. Used by vehicle animation (Crew, Exhaust-vehicle), and
any "X becomes a creature" effect that needs to grant the CREATURE type
independently of the full ``becomes_creature`` sweep.

The installed interceptor is tagged with ``_grant_creature_type_tag`` so the
end-of-turn cleanup or a leaves-zone sweep can identify and remove it.
"""

from ...types import (
    Event,
    EventType,
    GameState,
    Interceptor,
    InterceptorPriority,
    InterceptorAction,
    InterceptorResult,
    CardType,
    new_id,
)


def _normalize_duration(value) -> str:
    if not isinstance(value, str):
        return "end_of_turn"
    d = value.strip().lower().replace(" ", "_")
    if d in {"until_end_of_turn", "until_eot", "eot"}:
        return "end_of_turn"
    return d


def _handle_grant_creature_type(event: Event, state: GameState):
    """Install a TRANSFORM interceptor on QUERY_TYPES for the target.

    Payload:
      object_id (str, required) — the target permanent.
      duration (str, optional)  — 'end_of_turn' (default), 'until_leaves',
                                  or 'forever'.
    """
    object_id = event.payload.get("object_id")
    if not object_id or object_id not in state.objects:
        return

    target = state.objects[object_id]
    target_id = target.id
    duration = _normalize_duration(event.payload.get("duration", "end_of_turn"))
    tag_id = new_id()

    def _filter(ev: Event, st: GameState) -> bool:
        return (
            ev.type == EventType.QUERY_TYPES
            and ev.payload.get("object_id") == target_id
        )

    def _handler(ev: Event, st: GameState) -> InterceptorResult:
        new_event = ev.copy()
        existing = new_event.payload.get("value")
        if existing is None:
            live = st.objects.get(target_id)
            existing = set(live.characteristics.types) if live else set()
        new_types = set(existing)
        new_types.add(CardType.CREATURE)
        new_event.payload["value"] = new_types
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    interceptor = Interceptor(
        id=new_id(),
        source=target_id,
        controller=target.controller,
        priority=InterceptorPriority.QUERY,
        filter=_filter,
        handler=_handler,
        duration=duration,
    )
    setattr(interceptor, "_grant_creature_type_tag", tag_id)
    state.interceptors[interceptor.id] = interceptor
    interceptor.timestamp = state.next_timestamp()
