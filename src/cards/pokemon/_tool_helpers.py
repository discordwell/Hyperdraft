"""
Pokemon Tool attachment helpers.

A *Tool* is a Trainer subtype that, when played, attaches to one of the
player's Pokemon and stays in play (rather than going to the discard pile
like an Item). Its effect — an interceptor registered via
``setup_interceptors`` — only fires while the Tool is attached to a holder.

The Pokemon engine already has the bookkeeping fields:
- ``GameObject.state.attached_tool``: holder → tool back-pointer
- ``GameObject.state.attached_to``: tool → holder pointer

This module wires the missing pieces:
- ``attach_tool`` / ``detach_tool`` — move a Tool between attached state
  and the holder's discard pile, emitting the matching events.
- ``make_tool_setup`` — return a ``setup_interceptors`` callable that
  filters by ``tool.state.attached_to`` so the effect only fires while
  the Tool is actually attached to a Pokemon in play.

Pithing Drone (`src/cards/pokemon/beyond/ravnica/azorius.py`) is the first
card to use this pattern; future Tools should follow the same shape.
"""

from __future__ import annotations

from typing import Callable, Optional

from src.engine.types import (
    Event, EventType, GameObject, GameState, Interceptor,
    InterceptorAction, InterceptorPriority, InterceptorResult,
    ZoneType, new_id,
)


def attach_tool(
    tool_id: str,
    holder_id: str,
    state: GameState,
    *,
    source: Optional[str] = None,
) -> list[Event]:
    """Attach ``tool_id`` to ``holder_id``.

    - If the holder already has a Tool, the existing Tool is detached and
      sent to its owner's discard pile (per real Pokemon TCG rules — only
      one Tool per Pokemon).
    - The tool is removed from whatever zone container it was in (usually
      the hand) but does NOT enter any new zone container — its presence
      in play is tracked only via ``holder.state.attached_tool``.
    - Tool's ``zone`` field is set to match the holder's, so queries that
      check ``tool.zone`` see a consistent location.

    Returns the list of events emitted (1× ``PKM_ATTACH_TOOL`` for the
    new attachment, plus any ``PKM_DETACH_TOOL`` for a displaced Tool).
    """
    tool = state.objects.get(tool_id)
    holder = state.objects.get(holder_id)
    if tool is None or holder is None:
        return []

    events: list[Event] = []

    # Displace any existing tool on the holder.
    existing_tool_id = getattr(holder.state, 'attached_tool', None)
    if existing_tool_id and existing_tool_id != tool_id:
        events.extend(detach_tool(existing_tool_id, state, source=source))

    # Remove the new tool from its current zone container, if any.
    for zone in state.zones.values():
        if tool_id in zone.objects:
            zone.objects.remove(tool_id)

    tool.state.attached_to = holder_id
    holder.state.attached_tool = tool_id
    # Pokemon doesn't have a per-spot zone container for Tools; the engine's
    # interceptor-active gate (`pipeline/core.py:_get_interceptors`) checks
    # `source.zone == ZoneType.BATTLEFIELD`, so we mark the Tool as "on
    # battlefield" while attached. detach_tool / KO bookkeeping flips it
    # back to GRAVEYARD when the attachment ends.
    tool.zone = ZoneType.BATTLEFIELD
    tool.entered_zone_at = state.timestamp

    events.append(Event(
        type=EventType.PKM_ATTACH_TOOL,
        payload={
            'tool_id': tool_id,
            'holder_id': holder_id,
            'holder_controller': holder.controller,
            'source': source,
        },
        source=source or tool_id,
    ))
    return events


def detach_tool(
    tool_id: str,
    state: GameState,
    *,
    source: Optional[str] = None,
    send_to_graveyard: bool = True,
) -> list[Event]:
    """Detach ``tool_id`` from its current holder.

    Default sends the Tool to the discard pile of its owner. Pass
    ``send_to_graveyard=False`` to leave the Tool in limbo (e.g., when the
    holder is going to the Lost Zone and the Tool should follow).
    """
    tool = state.objects.get(tool_id)
    if tool is None:
        return []

    holder_id = getattr(tool.state, 'attached_to', None)
    if holder_id:
        holder = state.objects.get(holder_id)
        if holder is not None and getattr(holder.state, 'attached_tool', None) == tool_id:
            holder.state.attached_tool = None

    tool.state.attached_to = None

    if send_to_graveyard:
        grave_key = f"graveyard_{tool.owner}"
        grave = state.zones.get(grave_key)
        if grave is not None and tool_id not in grave.objects:
            grave.objects.append(tool_id)
        tool.zone = ZoneType.GRAVEYARD
        tool.entered_zone_at = state.timestamp

    return [Event(
        type=EventType.PKM_DETACH_TOOL,
        payload={
            'tool_id': tool_id,
            'former_holder_id': holder_id,
            'source': source,
        },
        source=source or tool_id,
    )]


def make_tool_setup(
    *,
    event_type: EventType,
    trigger_filter: Callable[[Event, GameState, GameObject, str], bool],
    trigger_handler: Callable[[Event, GameState, GameObject, str], list[Event]],
    priority: InterceptorPriority = InterceptorPriority.REACT,
) -> Callable[[GameObject, GameState], list[Interceptor]]:
    """Return a ``setup_interceptors`` callable for a Pokemon Tool.

    The returned setup callback registers one interceptor that:

    1. Auto-gates on the tool being currently attached: if
       ``tool.state.attached_to`` is None, the filter returns False and
       the interceptor does nothing. This means the interceptor is
       harmless before play (when the tool sits in the deck/hand) and
       harmless after KO (after ``detach_tool`` clears the pointer).

    2. Calls the caller-supplied ``trigger_filter(event, state, tool,
       holder_id)`` only after the auto-gate passes — letting the card
       script focus on the actual trigger condition (KO event matches
       holder, attack-by-holder matches, etc.).

    3. Calls ``trigger_handler(event, state, tool, holder_id)`` on a
       match, packaging the returned events as a REACT result.

    The interceptor lives ``'while_on_battlefield'``; the
    ``_cleanup_departed_interceptors`` path removes it when the Tool
    leaves play (per existing engine semantics for tracked interceptors).
    """

    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def filter_fn(event: Event, st: GameState) -> bool:
            holder_id = getattr(obj.state, 'attached_to', None)
            if not holder_id:
                return False
            if event.type != event_type:
                return False
            try:
                return bool(trigger_filter(event, st, obj, holder_id))
            except Exception:
                return False

        def handler_fn(event: Event, st: GameState) -> InterceptorResult:
            holder_id = getattr(obj.state, 'attached_to', None)
            if not holder_id:
                return InterceptorResult(action=InterceptorAction.PASS)
            try:
                extras = trigger_handler(event, st, obj, holder_id) or []
            except Exception:
                extras = []
            return InterceptorResult(action=InterceptorAction.REACT, new_events=extras)

        return [Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=priority,
            filter=filter_fn,
            handler=handler_fn,
            duration='while_on_battlefield',
        )]

    return setup


def choose_tool_holder(
    player_id: str,
    state: GameState,
    *,
    prefer_active: bool = True,
    filter_fn: Optional[Callable[[GameObject, GameState], bool]] = None,
) -> Optional[str]:
    """Pick a Pokemon owned by ``player_id`` that can receive a Tool.

    Heuristic v1: prefer the Active Pokemon (highest investment, the one
    most likely to benefit from a defensive Tool); fall back to the first
    Bench Pokemon. Skips Pokemon that already have a Tool attached unless
    explicitly allowed by ``filter_fn``. AI-overridable in Phase 1a via
    ``PokemonAIAdapter.choose_tool_target``.
    """
    candidates: list[str] = []

    def is_eligible(obj: GameObject) -> bool:
        if filter_fn is not None and not filter_fn(obj, state):
            return False
        # Default: skip Pokemon that already have a Tool (Pokemon TCG
        # rule). filter_fn can override.
        if filter_fn is None and getattr(obj.state, 'attached_tool', None):
            return False
        return True

    active_zone = state.zones.get(f"active_spot_{player_id}")
    if active_zone and active_zone.objects:
        active_id = active_zone.objects[0]
        active = state.objects.get(active_id)
        if active and is_eligible(active):
            if prefer_active:
                return active_id
            candidates.append(active_id)

    bench_zone = state.zones.get(f"bench_{player_id}")
    if bench_zone:
        for bid in bench_zone.objects:
            if not bid:
                continue
            obj = state.objects.get(bid)
            if obj and is_eligible(obj):
                candidates.append(bid)

    return candidates[0] if candidates else None
