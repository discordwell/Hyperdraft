"""
Hyperdraft Event Pipeline

The heart of the engine. Events flow through interceptors:
1. TRANSFORM - modify the event
2. PREVENT - cancel the event
3. RESOLVE - actually do it
4. REACT - trigger responses
"""

from typing import Optional
from .types import (
    Event, EventType, EventStatus,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameState, GameObject, ZoneType, Player, Color
)


class EventPipeline:
    """Processes events through the interceptor chain."""

    def __init__(self, state: GameState, max_iterations: int = 1000):
        self.state = state
        self.max_iterations = max_iterations
        self._iteration_count = 0

    def emit(self, event: Event) -> list[Event]:
        """
        Emit an event through the pipeline.
        Returns all events that were processed (including triggered ones).
        """
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
        if self._run_prevent_phase(event):
            event.status = EventStatus.PREVENTED
            self.state.event_log.append(event)
            return []

        # 3. RESOLVE PHASE
        event.status = EventStatus.RESOLVING
        self._resolve_event(event)
        event.status = EventStatus.RESOLVED
        self.state.event_log.append(event)

        # 4. REACT PHASE
        triggered = self._run_react_phase(event)

        return triggered

    def _get_interceptors(self, priority: InterceptorPriority) -> list[Interceptor]:
        """Get interceptors of a given priority, sorted by timestamp."""
        return sorted(
            [i for i in self.state.interceptors.values() if i.priority == priority],
            key=lambda i: i.timestamp
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

    def _run_prevent_phase(self, event: Event) -> bool:
        """Run all PREVENT interceptors. Returns True if event was prevented."""
        for interceptor in self._get_interceptors(InterceptorPriority.PREVENT):
            if not interceptor.filter(event, self.state):
                continue

            result = interceptor.handler(event, self.state)

            if result.action == InterceptorAction.PREVENT:
                self._consume_use(interceptor)
                return True

            self._consume_use(interceptor)

        return False

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

    def _resolve_event(self, event: Event):
        """Actually apply the event to game state."""
        handler = EVENT_HANDLERS.get(event.type)
        if handler:
            handler(event, self.state)


# =============================================================================
# Event Resolution Handlers
# =============================================================================

def _handle_damage(event: Event, state: GameState):
    """Handle DAMAGE event."""
    target_id = event.payload.get('target')
    amount = event.payload.get('amount', 0)

    if amount <= 0:
        return

    # Damage to player
    if target_id in state.players:
        player = state.players[target_id]
        player.life -= amount
        return

    # Damage to creature
    if target_id in state.objects:
        obj = state.objects[target_id]
        obj.state.damage += amount


def _handle_life_change(event: Event, state: GameState):
    """Handle LIFE_CHANGE event."""
    player_id = event.payload.get('player')
    amount = event.payload.get('amount', 0)

    if player_id in state.players:
        state.players[player_id].life += amount


def _handle_draw(event: Event, state: GameState):
    """Handle DRAW event."""
    player_id = event.payload.get('player')
    count = event.payload.get('count', 1)

    # Find player's library and hand
    library_key = f"library_{player_id}"
    hand_key = f"hand_{player_id}"

    if library_key not in state.zones or hand_key not in state.zones:
        return

    library = state.zones[library_key]
    hand = state.zones[hand_key]

    for _ in range(count):
        if not library.objects:
            # TODO: Player loses for drawing from empty library
            break
        card_id = library.objects.pop(0)  # Top of library
        hand.objects.append(card_id)

        if card_id in state.objects:
            state.objects[card_id].zone = ZoneType.HAND


def _handle_zone_change(event: Event, state: GameState):
    """Handle ZONE_CHANGE event."""
    object_id = event.payload.get('object_id')
    from_zone = event.payload.get('from_zone')
    to_zone = event.payload.get('to_zone')

    if object_id not in state.objects:
        return

    obj = state.objects[object_id]

    # Remove from old zone
    if from_zone in state.zones:
        zone = state.zones[from_zone]
        if object_id in zone.objects:
            zone.objects.remove(object_id)

    # Add to new zone
    if to_zone in state.zones:
        zone = state.zones[to_zone]
        zone.objects.append(object_id)

    # Update object's zone
    obj.zone = event.payload.get('to_zone_type', obj.zone)
    obj.entered_zone_at = state.timestamp


def _handle_tap(event: Event, state: GameState):
    """Handle TAP event."""
    object_id = event.payload.get('object_id')
    if object_id in state.objects:
        state.objects[object_id].state.tapped = True


def _handle_untap(event: Event, state: GameState):
    """Handle UNTAP event."""
    object_id = event.payload.get('object_id')
    if object_id in state.objects:
        state.objects[object_id].state.tapped = False


def _handle_counter_added(event: Event, state: GameState):
    """Handle COUNTER_ADDED event."""
    object_id = event.payload.get('object_id')
    counter_type = event.payload.get('counter_type', '+1/+1')
    amount = event.payload.get('amount', 1)

    if object_id in state.objects:
        obj = state.objects[object_id]
        current = obj.state.counters.get(counter_type, 0)
        obj.state.counters[counter_type] = current + amount


def _handle_counter_removed(event: Event, state: GameState):
    """Handle COUNTER_REMOVED event."""
    object_id = event.payload.get('object_id')
    counter_type = event.payload.get('counter_type', '+1/+1')
    amount = event.payload.get('amount', 1)

    if object_id in state.objects:
        obj = state.objects[object_id]
        current = obj.state.counters.get(counter_type, 0)
        obj.state.counters[counter_type] = max(0, current - amount)


def _handle_object_destroyed(event: Event, state: GameState):
    """Handle OBJECT_DESTROYED - move to graveyard."""
    object_id = event.payload.get('object_id')

    if object_id not in state.objects:
        return

    obj = state.objects[object_id]
    owner_id = obj.owner

    # Remove from current zone
    for zone in state.zones.values():
        if object_id in zone.objects:
            zone.objects.remove(object_id)
            break

    # Add to owner's graveyard
    gy_key = f"graveyard_{owner_id}"
    if gy_key in state.zones:
        state.zones[gy_key].objects.append(object_id)

    obj.zone = ZoneType.GRAVEYARD
    obj.entered_zone_at = state.timestamp

    # Remove interceptors this object created
    to_remove = list(obj.interceptor_ids)
    for int_id in to_remove:
        if int_id in state.interceptors:
            del state.interceptors[int_id]
    obj.interceptor_ids.clear()


def _handle_mana_produced(event: Event, state: GameState):
    """Handle MANA_PRODUCED event."""
    player_id = event.payload.get('player')
    color = event.payload.get('color', Color.COLORLESS)
    amount = event.payload.get('amount', 1)

    if player_id in state.players:
        player = state.players[player_id]
        current = player.mana_pool.get(color, 0)
        player.mana_pool[color] = current + amount


def _handle_player_loses(event: Event, state: GameState):
    """Handle PLAYER_LOSES event."""
    player_id = event.payload.get('player')
    if player_id in state.players:
        state.players[player_id].has_lost = True


# =============================================================================
# Event Handler Registry
# =============================================================================

EVENT_HANDLERS = {
    EventType.DAMAGE: _handle_damage,
    EventType.LIFE_CHANGE: _handle_life_change,
    EventType.DRAW: _handle_draw,
    EventType.ZONE_CHANGE: _handle_zone_change,
    EventType.TAP: _handle_tap,
    EventType.UNTAP: _handle_untap,
    EventType.COUNTER_ADDED: _handle_counter_added,
    EventType.COUNTER_REMOVED: _handle_counter_removed,
    EventType.OBJECT_DESTROYED: _handle_object_destroyed,
    EventType.MANA_PRODUCED: _handle_mana_produced,
    EventType.PLAYER_LOSES: _handle_player_loses,
}
