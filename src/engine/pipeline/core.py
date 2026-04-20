"""
Event pipeline dispatcher.

Wraps the phase pipeline (TRANSFORM → PREVENT → RESOLVE → REACT → CLEANUP)
and dispatches resolution to the per-family handlers registered in
``EVENT_HANDLERS`` (see ``handlers/__init__.py``).
"""

from ..types import (
    Event, EventType, EventStatus,
    Interceptor, InterceptorPriority, InterceptorAction,
    GameState, ZoneType,
)


class EventPipeline:
    """Processes events through the interceptor chain."""

    def __init__(self, state: GameState, max_iterations: int = 1000):
        self.state = state
        self.max_iterations = max_iterations
        self._iteration_count = 0
        self.sba_deferred = False  # When True, SBA checks skip death processing

    def emit(self, event: Event) -> list[Event]:
        """
        Emit an event through the pipeline.
        Returns all events that were processed (including triggered ones).
        """
        # Reset per-emit iteration counter. This is a guard against infinite
        # event chains within a single emit call, not a global lifetime cap.
        self._iteration_count = 0
        event.timestamp = self.state.next_timestamp()
        processed = []
        queue = [event]

        while queue and self._iteration_count < self.max_iterations:
            self._iteration_count += 1
            current = queue.pop(0)

            result = self._process_single(current)
            processed.append(current)

            # Add any triggered events to the queue
            queue.extend(result)

        if self._iteration_count >= self.max_iterations:
            raise RuntimeError(f"Event loop exceeded {self.max_iterations} iterations - possible infinite loop")

        return processed

    def _process_single(self, event: Event) -> list[Event]:
        """Process a single event through all phases. Returns triggered events."""

        # 1. TRANSFORM PHASE
        event = self._run_transform_phase(event)

        # 2. PREVENT PHASE
        prevented, prevent_side_effects = self._run_prevent_phase(event)
        if prevented:
            event.status = EventStatus.PREVENTED
            self.state.event_log.append(event)
            return prevent_side_effects

        # 3. RESOLVE PHASE
        event.status = EventStatus.RESOLVING
        produced = self._resolve_event(event) or []
        for e in produced:
            e.timestamp = self.state.next_timestamp()
        event.status = EventStatus.RESOLVED
        self.state.event_log.append(event)

        # 4. REACT PHASE
        # Death triggers and other reactions fire here, BEFORE cleanup
        triggered = self._run_react_phase(event)

        # 5. CLEANUP PHASE
        # Clean up interceptors for objects that left the battlefield
        # This happens AFTER REACT so death triggers can fire
        self._cleanup_departed_interceptors(event)

        # Events produced by resolution are treated like triggered events and
        # will be processed by this emit() call's queue.
        return list(produced) + list(triggered)

    def _cleanup_departed_interceptors(self, event: Event):
        """
        Clean up interceptors for objects that left the battlefield.

        Called after REACT phase so death triggers can fire first.
        Only cleans up interceptors with duration='while_on_battlefield'.
        """
        # Only clean up after zone changes or destruction
        if event.type not in (EventType.OBJECT_DESTROYED, EventType.ZONE_CHANGE, EventType.SACRIFICE, EventType.EXILE):
            return

        # Some events (EXILE) can operate on multiple objects.
        object_ids: list[str] = []
        if 'object_id' in event.payload:
            object_ids.append(event.payload.get('object_id'))
        if event.type == EventType.EXILE and 'object_ids' in event.payload:
            object_ids.extend(list(event.payload.get('object_ids') or []))

        for object_id in [oid for oid in object_ids if oid]:
            if object_id not in self.state.objects:
                continue

            obj = self.state.objects[object_id]

            # Only clean up if object left the battlefield
            if obj.zone == ZoneType.BATTLEFIELD:
                continue

            # Remove interceptors marked for cleanup when leaving battlefield
            to_remove = []
            for int_id in list(obj.interceptor_ids):
                interceptor = self.state.interceptors.get(int_id)
                if interceptor:
                    # Clean up interceptors that only work while on battlefield
                    # Keep interceptors marked 'until_leaves' for one more event cycle
                    # (they needed to fire their death trigger)
                    duration = getattr(interceptor, 'duration', None) or 'while_on_battlefield'
                    if duration == 'while_on_battlefield':
                        to_remove.append(int_id)
                    elif duration == 'until_leaves':
                        # Mark for removal next time (already fired)
                        to_remove.append(int_id)

            for int_id in to_remove:
                if int_id in self.state.interceptors:
                    del self.state.interceptors[int_id]
                if int_id in obj.interceptor_ids:
                    obj.interceptor_ids.remove(int_id)

    def _get_interceptors(self, priority: InterceptorPriority) -> list[Interceptor]:
        """
        Get interceptors of a given priority, sorted by timestamp.

        Important: Most interceptors are intended to apply only while their source
        object is on the battlefield. However, we register interceptors when a card
        object is created (e.g. when building libraries), so we must gate those
        interceptors here rather than relying on every card file's filter_fn to
        check zones.
        """

        def is_active(interceptor: Interceptor) -> bool:
            duration = getattr(interceptor, 'duration', None) or 'while_on_battlefield'
            if duration != 'while_on_battlefield':
                return True

            source_obj = self.state.objects.get(interceptor.source)
            return bool(source_obj and source_obj.zone == ZoneType.BATTLEFIELD)

        return sorted(
            [
                i
                for i in self.state.interceptors.values()
                if i.priority == priority and is_active(i)
            ],
            key=lambda i: i.timestamp,
        )

    def _run_transform_phase(self, event: Event) -> Event:
        """Run all TRANSFORM interceptors. Returns the (possibly modified) event."""
        for interceptor in self._get_interceptors(InterceptorPriority.TRANSFORM):
            if not interceptor.filter(event, self.state):
                continue

            result = interceptor.handler(event, self.state)

            if result.action == InterceptorAction.TRANSFORM:
                event = result.transformed_event or event
            elif result.action == InterceptorAction.REPLACE:
                # Replace returns multiple events - we emit the first, queue the rest
                # This is a simplification; could be more sophisticated
                if result.new_events:
                    event = result.new_events[0]

            self._consume_use(interceptor)

        return event

    def _run_prevent_phase(self, event: Event) -> tuple[bool, list[Event]]:
        """Run all PREVENT interceptors. Returns (prevented, side_effect_events)."""
        for interceptor in self._get_interceptors(InterceptorPriority.PREVENT):
            if not interceptor.filter(event, self.state):
                continue

            result = interceptor.handler(event, self.state)

            if result.action == InterceptorAction.PREVENT:
                self._consume_use(interceptor)
                # Collect side-effect events (e.g. DIVINE_SHIELD_BREAK)
                side_effects = []
                for new_event in (result.new_events or []):
                    new_event.timestamp = self.state.next_timestamp()
                    side_effects.append(new_event)
                return True, side_effects

            self._consume_use(interceptor)

        return False, []

    def _run_react_phase(self, event: Event) -> list[Event]:
        """Run all REACT interceptors. Returns triggered events."""
        triggered = []

        for interceptor in self._get_interceptors(InterceptorPriority.REACT):
            if not interceptor.filter(event, self.state):
                continue

            result = interceptor.handler(event, self.state)

            if result.action == InterceptorAction.REACT:
                for new_event in result.new_events:
                    new_event.timestamp = self.state.next_timestamp()
                    triggered.append(new_event)

            self._consume_use(interceptor)

        return triggered

    def _consume_use(self, interceptor: Interceptor):
        """Decrement uses_remaining if applicable, remove if exhausted."""
        if interceptor.uses_remaining is not None:
            interceptor.uses_remaining -= 1
            if interceptor.uses_remaining <= 0:
                del self.state.interceptors[interceptor.id]

    def _resolve_event(self, event: Event) -> list[Event]:
        """
        Actually apply the event to game state.

        Some resolution handlers return follow-up events (e.g. RETURN_* helpers
        that normalize into ZONE_CHANGE events). The pipeline will enqueue and
        process those events as part of this emit() call.
        """
        # Imported locally to avoid a circular import at module load time
        # (handlers/__init__.py imports from this module indirectly).
        from .handlers import EVENT_HANDLERS

        handler = EVENT_HANDLERS.get(event.type)
        if handler:
            out = handler(event, self.state)
            if out is None:
                return []
            if isinstance(out, Event):
                return [out]
            if isinstance(out, list):
                return [e for e in out if isinstance(e, Event)]
            # Unknown handler return type; ignore for safety.
            return []
        return []
