"""
Counter add/remove handlers.

The keyword-counter bookkeeping lives in _shared.py so that zone handlers
(which also need to sync keyword counters on battlefield entry) can use it
without cross-importing handler modules.
"""

from ...types import Event, GameState
from .._shared import _KEYWORD_COUNTER_TYPES, _sync_keyword_counter_abilities


def _handle_counter_added(event: Event, state: GameState):
    """Handle COUNTER_ADDED event."""
    object_id = event.payload.get('object_id')
    counter_type = event.payload.get('counter_type', '+1/+1')
    amount = event.payload.get('amount', 1)

    if object_id in state.objects:
        obj = state.objects[object_id]
        if isinstance(counter_type, str):
            normalized = counter_type.strip().lower()
            if normalized in _KEYWORD_COUNTER_TYPES:
                counter_type = normalized
        current = obj.state.counters.get(counter_type, 0)
        obj.state.counters[counter_type] = current + amount
        if counter_type in _KEYWORD_COUNTER_TYPES:
            _sync_keyword_counter_abilities(obj)


def _handle_counter_removed(event: Event, state: GameState):
    """Handle COUNTER_REMOVED event."""
    object_id = event.payload.get('object_id')
    counter_type = event.payload.get('counter_type', '+1/+1')
    amount = event.payload.get('amount', 1)

    if object_id in state.objects:
        obj = state.objects[object_id]
        if isinstance(counter_type, str):
            normalized = counter_type.strip().lower()
            if normalized in _KEYWORD_COUNTER_TYPES:
                counter_type = normalized
        current = obj.state.counters.get(counter_type, 0)
        obj.state.counters[counter_type] = max(0, current - amount)
        if counter_type in _KEYWORD_COUNTER_TYPES:
            _sync_keyword_counter_abilities(obj)
