"""
Saga Subsystem
==============

Implements MTG's Saga enchantment mechanic.

CR 714 (Sagas):
- 714.2  As a Saga enters the battlefield, its controller puts a lore counter
         on it.
- 714.3  After the controller's draw step, that player's Saga gains a lore
         counter.
- 714.4  When one or more lore counters are placed on a Saga, the chapter
         ability for the chapter corresponding to the counter's number triggers.
- 714.5  If a Saga has the number of lore counters equal to or greater than its
         final chapter number, it is sacrificed by its controller after the
         chapter ability resolves.

Design
------

Two new EventTypes (in :class:`src.engine.types.EventType`):

* ``SAGA_LORE_ADDED`` -- Emitted when a lore counter should be added to a Saga.
  Payload: ``{'object_id': saga_id, 'amount': int = 1}``.
  The pipeline handler (registered below) increments
  ``saga.state.counters['lore']`` and produces one ``SAGA_CHAPTER`` event for
  each counter placed.

* ``SAGA_CHAPTER`` -- Emitted once per chapter that just triggered.
  Payload: ``{'object_id': saga_id, 'chapter': int, 'final_chapter': int}``.
  Card-supplied chapter handlers (built by ``make_saga_setup`` in
  ``interceptor_helpers.py``) react to this event and produce the chapter's
  effect events. After the final chapter resolves, the handler also queues a
  ``SACRIFICE`` event for the Saga.

Two interceptors are auto-installed when a Saga setup runs (see
``make_saga_setup``):

1. **ETB lore-counter trigger**: when the Saga enters the battlefield, react
   with a ``SAGA_LORE_ADDED`` event so chapter I fires.
2. **Post-draw-step lore-counter trigger**: after the controller's draw step
   (i.e. ``PHASE_START`` with phase ``'draw'`` for the Saga's controller), react
   with a ``SAGA_LORE_ADDED`` event for the next chapter.

Pipeline registration is performed by importing this module before the engine
processes any event. ``src.engine.pipeline.handlers.__init__`` imports it at
module load time and merges its handlers into ``EVENT_HANDLERS``.
"""

from typing import Optional

from .types import (
    Event,
    EventType,
    EventStatus,
    GameState,
    GameObject,
    ZoneType,
)


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

def _handle_saga_lore_added(event: Event, state: GameState) -> Optional[list[Event]]:
    """
    Handle a ``SAGA_LORE_ADDED`` event.

    Adds the lore counters to ``saga.state.counters['lore']`` and produces a
    ``SAGA_CHAPTER`` event for each counter placed. Multiple counters in one
    event (rare) trigger their chapters in increasing order.

    Returns the list of follow-up events that the pipeline should process
    next (which is where chapter triggers live).
    """
    object_id = event.payload.get('object_id')
    amount = int(event.payload.get('amount', 1) or 0)
    if not object_id or amount <= 0:
        return []
    saga = state.objects.get(object_id)
    if saga is None or saga.zone != ZoneType.BATTLEFIELD:
        # Saga left the battlefield; ignore.
        return []
    if not _is_saga(saga):
        return []

    final_chapter = _saga_final_chapter(saga)
    current = int(saga.state.counters.get('lore', 0))

    chapter_events: list[Event] = []
    for i in range(amount):
        current += 1
        saga.state.counters['lore'] = current
        chapter_events.append(Event(
            type=EventType.SAGA_CHAPTER,
            payload={
                'object_id': object_id,
                'chapter': current,
                'final_chapter': final_chapter,
            },
            source=object_id,
            controller=saga.controller,
        ))

    return chapter_events


def _handle_saga_chapter(event: Event, state: GameState) -> Optional[list[Event]]:
    """
    Default ``SAGA_CHAPTER`` resolver.

    The actual chapter effects are produced by REACT-priority interceptors that
    cards register through ``make_saga_setup``. The resolver itself is a no-op
    that simply confirms the event resolved; sacrifice on final chapter is also
    queued by the ``make_saga_setup`` interceptor (so the chapter effect and
    sacrifice live in one place per card).
    """
    return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_saga(obj: GameObject) -> bool:
    """Return True if ``obj`` has the ``Saga`` subtype."""
    if obj is None or obj.characteristics is None:
        return False
    return 'Saga' in (obj.characteristics.subtypes or set())


def _saga_final_chapter(obj: GameObject) -> int:
    """
    Best-effort detection of a Saga's final chapter from its rules text.

    Looks for ``"Sacrifice after <ROMAN>."`` and converts the roman numeral.
    Falls back to ``3`` (the most common Saga shape) if parsing fails. The
    final chapter can also be supplied explicitly via
    ``card_def._saga_final_chapter`` -- ``make_saga_setup`` sets that override
    when the caller passes the final-chapter argument explicitly.
    """
    card_def = getattr(obj, 'card_def', None)
    explicit = getattr(card_def, '_saga_final_chapter', None) if card_def else None
    if isinstance(explicit, int) and explicit > 0:
        return explicit

    text = getattr(card_def, 'text', '') if card_def else ''
    if not text:
        return 3

    # Find "Sacrifice after <numeral>."
    import re
    m = re.search(r'[Ss]acrifice after\s+([IVXLCDM]+)', text)
    if not m:
        return 3
    try:
        return _roman_to_int(m.group(1))
    except Exception:
        return 3


def _roman_to_int(s: str) -> int:
    """Convert a Roman numeral string to int. Supports up to ``XXXIX``."""
    table = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    total = 0
    prev = 0
    for ch in reversed(s.upper()):
        v = table.get(ch, 0)
        if v < prev:
            total -= v
        else:
            total += v
        prev = v
    return total


# ---------------------------------------------------------------------------
# Public registry used by ``handlers/__init__``
# ---------------------------------------------------------------------------

SAGA_EVENT_HANDLERS = {
    EventType.SAGA_LORE_ADDED: _handle_saga_lore_added,
    EventType.SAGA_CHAPTER: _handle_saga_chapter,
}


__all__ = [
    'SAGA_EVENT_HANDLERS',
    '_handle_saga_lore_added',
    '_handle_saga_chapter',
    '_is_saga',
    '_saga_final_chapter',
]
