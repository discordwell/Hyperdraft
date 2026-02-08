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
    GameState, GameObject, ZoneType, Player, Color, CardType,
    PendingChoice
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
        # Death triggers and other reactions fire here, BEFORE cleanup
        triggered = self._run_react_phase(event)

        # 5. CLEANUP PHASE
        # Clean up interceptors for objects that left the battlefield
        # This happens AFTER REACT so death triggers can fire
        self._cleanup_departed_interceptors(event)

        return triggered

    def _cleanup_departed_interceptors(self, event: Event):
        """
        Clean up interceptors for objects that left the battlefield.

        Called after REACT phase so death triggers can fire first.
        Only cleans up interceptors with duration='while_on_battlefield'.
        """
        # Only clean up after zone changes or destruction
        if event.type not in (EventType.OBJECT_DESTROYED, EventType.ZONE_CHANGE):
            return

        object_id = event.payload.get('object_id')
        if not object_id or object_id not in self.state.objects:
            return

        obj = self.state.objects[object_id]

        # Only clean up if object left the battlefield
        if obj.zone == ZoneType.BATTLEFIELD:
            return

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
    # Support both 'amount' (used by most cards) and 'count' (legacy)
    count = event.payload.get('amount') or event.payload.get('count', 1)

    # Find player's library and hand
    library_key = f"library_{player_id}"
    hand_key = f"hand_{player_id}"

    if library_key not in state.zones or hand_key not in state.zones:
        return

    library = state.zones[library_key]
    hand = state.zones[hand_key]

    for _ in range(count):
        if not library.objects:
            # MTG rule: a player loses the game if they attempt to draw from an empty library.
            player = state.players.get(player_id)
            if player:
                player.has_lost = True
            break
        card_id = library.objects.pop(0)  # Top of library
        # Be robust against zone corruption: ensure the card isn't referenced in
        # any other zone list before we put it into the hand.
        _remove_object_from_all_zones(card_id, state)
        hand.objects.append(card_id)

        if card_id in state.objects:
            state.objects[card_id].zone = ZoneType.HAND
            state.objects[card_id].entered_zone_at = state.timestamp


def _handle_object_created(event: Event, state: GameState):
    """
    Handle OBJECT_CREATED event.

    This is primarily used by card implementations to create tokens.

    Common payload keys:
        - name: str
        - controller: player_id
        - owner: player_id (optional, defaults to controller)
        - zone_type / to_zone_type: ZoneType (optional, defaults to BATTLEFIELD)
        - types: list[CardType] | set[CardType] (optional, defaults to {CREATURE})
        - subtypes: list[str] | set[str] (optional)
        - supertypes: list[str] | set[str] (optional)
        - colors: list[Color] | set[Color] (optional)
        - power: int (optional)
        - toughness: int (optional)
        - abilities: list[dict] (optional, keyword dicts etc.)
        - keywords: list[str] (optional, converted into abilities=[{'keyword': ...}])
        - token / is_token: bool (optional)
        - tapped: bool (optional)
        - attach_to / attached_to: object_id (optional)

    Side effects:
        - event.payload['object_id'] is set to the created object's id.
        - event.payload['to_zone_type'] is set to the final ZoneType.
    """
    from .types import new_id, GameObject, Characteristics, ObjectState

    controller_id = event.payload.get('controller') or event.controller
    if not controller_id or controller_id not in state.players:
        return

    owner_id = event.payload.get('owner') or controller_id

    zone_type = (
        event.payload.get('zone_type')
        or event.payload.get('to_zone_type')
        or event.payload.get('zone')
        or ZoneType.BATTLEFIELD
    )
    if isinstance(zone_type, str):
        # Accept ZoneType names like "BATTLEFIELD"/"battlefield".
        try:
            zone_type = ZoneType[zone_type.upper()]
        except Exception:
            zone_type = ZoneType.BATTLEFIELD

    types = event.payload.get('types')
    if types is None:
        types = {CardType.CREATURE}
    if isinstance(types, list):
        types = set(types)

    subtypes = event.payload.get('subtypes', set())
    if isinstance(subtypes, list):
        subtypes = set(subtypes)

    supertypes = event.payload.get('supertypes', set())
    if isinstance(supertypes, list):
        supertypes = set(supertypes)

    colors = event.payload.get('colors', set())
    if isinstance(colors, list):
        colors = set(colors)

    # Abilities/keywords (best-effort). Many callers use `keywords=[...]`.
    abilities = event.payload.get('abilities', [])
    if isinstance(abilities, list) and abilities and not isinstance(abilities[0], dict):
        abilities = []

    keywords = event.payload.get('keywords', [])
    if keywords and not abilities:
        abilities = [{'keyword': str(kw).lower()} for kw in keywords]

    characteristics = Characteristics(
        types=types,
        subtypes=subtypes,
        supertypes=supertypes,
        colors=colors,
        power=event.payload.get('power'),
        toughness=event.payload.get('toughness'),
        abilities=abilities or []
    )

    is_token = bool(event.payload.get('is_token') or event.payload.get('token'))
    enters_tapped = bool(event.payload.get('tapped', False))

    obj_id = new_id()
    created = GameObject(
        id=obj_id,
        name=event.payload.get('name', 'Token'),
        owner=owner_id,
        controller=controller_id,
        zone=zone_type,
        characteristics=characteristics,
        state=ObjectState(
            is_token=is_token,
            tapped=enters_tapped
        ),
        created_at=state.next_timestamp(),
        entered_zone_at=state.timestamp
    )

    state.objects[obj_id] = created

    # Add to zone list if we can resolve a key.
    zone_key = None
    if zone_type in {ZoneType.LIBRARY, ZoneType.HAND, ZoneType.GRAVEYARD}:
        zone_key = f"{zone_type.name.lower()}_{owner_id}"
    else:
        zone_key = zone_type.name.lower()

    if zone_key in state.zones:
        state.zones[zone_key].objects.append(obj_id)

    # Optional attachment support (Auras/Equipment tokens, etc.)
    attach_to = event.payload.get('attach_to') or event.payload.get('attached_to')
    if attach_to and attach_to in state.objects:
        created.state.attached_to = attach_to
        host = state.objects[attach_to]
        if obj_id not in host.state.attachments:
            host.state.attachments.append(obj_id)

    # Surface created id/zone for downstream triggers/tests.
    event.payload['object_id'] = obj_id
    event.payload['to_zone_type'] = zone_type


def _remove_object_from_all_zones(object_id: str, state: GameState) -> None:
    """Remove an object id from every zone list (robust against zone corruption)."""
    for zone in state.zones.values():
        while object_id in zone.objects:
            zone.objects.remove(object_id)


def _handle_zone_change(event: Event, state: GameState):
    """Handle ZONE_CHANGE event."""
    object_id = event.payload.get('object_id')
    from_zone = event.payload.get('from_zone')
    to_zone = event.payload.get('to_zone')
    from_zone_type = event.payload.get('from_zone_type')
    to_zone_type = event.payload.get('to_zone_type')

    if object_id not in state.objects:
        return

    obj = state.objects[object_id]

    def _zone_key(zone_type: ZoneType, owner_id: Optional[str]) -> Optional[str]:
        if zone_type in {ZoneType.LIBRARY, ZoneType.HAND, ZoneType.GRAVEYARD}:
            return f"{zone_type.name.lower()}_{owner_id}" if owner_id else None
        return zone_type.name.lower()

    from_owner = event.payload.get('from_zone_owner')
    to_owner = event.payload.get('to_zone_owner')
    if from_owner is None and from_zone_type in {ZoneType.LIBRARY, ZoneType.HAND, ZoneType.GRAVEYARD}:
        from_owner = obj.owner
    if to_owner is None and to_zone_type in {ZoneType.LIBRARY, ZoneType.HAND, ZoneType.GRAVEYARD}:
        to_owner = obj.owner

    # Support a more semantic payload format used by some card files:
    #   {from_zone_type, to_zone_type, to_zone_owner, ...}
    # Normalize into {from_zone, to_zone} so zone list operations stay consistent.
    if from_zone is None and from_zone_type:
        from_zone = _zone_key(from_zone_type, from_owner)

    if to_zone is None and to_zone_type:
        to_zone = _zone_key(to_zone_type, to_owner)

    # Infer zone types from keys when omitted (helps older callers).
    if from_zone_type is None and from_zone in state.zones:
        from_zone_type = state.zones[from_zone].type
    if to_zone_type is None and to_zone in state.zones:
        to_zone_type = state.zones[to_zone].type

    # If both are provided but inconsistent (e.g. a replacement effect transforms
    # to_zone_type without updating to_zone), treat the zone type as canonical
    # and recompute the zone key.
    if from_zone_type and from_zone in state.zones and state.zones[from_zone].type != from_zone_type:
        from_zone = _zone_key(from_zone_type, from_owner)
    if to_zone_type and to_zone in state.zones and state.zones[to_zone].type != to_zone_type:
        to_zone = _zone_key(to_zone_type, to_owner)

    # Normalize payload for downstream triggers/filters.
    if from_zone is not None:
        event.payload['from_zone'] = from_zone
    if to_zone is not None:
        event.payload['to_zone'] = to_zone
    if from_zone_type is not None:
        event.payload['from_zone_type'] = from_zone_type
    if to_zone_type is not None:
        event.payload['to_zone_type'] = to_zone_type

    # Important: many call sites provide imperfect `from_zone` keys. Be robust
    # and remove the object from *any* zone that currently references it.
    _remove_object_from_all_zones(object_id, state)

    # Add to new zone
    if to_zone and to_zone in state.zones:
        zone = state.zones[to_zone]
        zone.objects.append(object_id)

    # Update object's zone
    if to_zone_type is not None:
        obj.zone = to_zone_type
    obj.entered_zone_at = state.timestamp

    # When entering the battlefield, reset object state (MTG rule: new object)
    # This happens BEFORE applying special enter-the-battlefield modifications
    if to_zone_type == ZoneType.BATTLEFIELD:
        # Clear counters (will be re-added if specified in payload)
        obj.state.counters = {}
        _sync_keyword_counter_abilities(obj)
        # Clear damage
        obj.state.damage = 0
        # Reset tapped state (will be set if entering tapped)
        obj.state.tapped = False

    # Handle "as enchantment only" - for cards like Enduring Curiosity
    # that return from graveyard without their creature type
    if event.payload.get('as_enchantment_only'):
        if CardType.CREATURE in obj.characteristics.types:
            obj.characteristics.types.discard(CardType.CREATURE)
        # Clear P/T since it's no longer a creature
        obj.characteristics.power = None
        obj.characteristics.toughness = None

    # Handle entering tapped (e.g., Unstoppable Slasher)
    if event.payload.get('tapped'):
        obj.state.tapped = True

    # Handle entering with counters (e.g., Unstoppable Slasher with stun counters)
    counters = event.payload.get('counters')
    if counters and isinstance(counters, dict):
        for counter_type, amount in counters.items():
            if isinstance(counter_type, str):
                normalized = counter_type.strip().lower()
                if normalized in _KEYWORD_COUNTER_TYPES:
                    counter_type = normalized
            obj.state.counters[counter_type] = amount  # Set directly since we cleared above
        _sync_keyword_counter_abilities(obj)

    # Re-setup interceptors when entering the battlefield
    # This handles cards like Enduring Curiosity that return from graveyard
    # Only register if object doesn't already have interceptors (avoids double-registration)
    if to_zone_type == ZoneType.BATTLEFIELD and obj.card_def:
        if obj.card_def.setup_interceptors and not obj.interceptor_ids:
            # Run setup with the current object state (post-type-changes)
            new_interceptors = obj.card_def.setup_interceptors(obj, state) or []
            for interceptor in new_interceptors:
                interceptor.timestamp = state.next_timestamp()
                state.interceptors[interceptor.id] = interceptor
                obj.interceptor_ids.append(interceptor.id)


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


def _handle_gain_control(event: Event, state: GameState):
    """Handle GAIN_CONTROL event (controller change, usually temporary)."""
    object_id = event.payload.get("object_id")
    new_controller = event.payload.get("new_controller")
    duration = event.payload.get("duration", "end_of_turn")
    if isinstance(duration, str):
        d = duration.strip().lower().replace(" ", "_")
        if d in {"until_end_of_turn", "until_eot", "eot"}:
            duration = "end_of_turn"

    if not object_id or object_id not in state.objects or not new_controller:
        return

    obj = state.objects[object_id]
    if duration == "end_of_turn" and not hasattr(obj.state, "_restore_controller_eot"):
        obj.state._restore_controller_eot = obj.controller

    obj.controller = new_controller


_KEYWORD_COUNTER_TYPES: set[str] = {
    # MTG keyword counters (702.* / 122.*). We model these as real keyword
    # abilities for compatibility with older card logic that checks
    # `obj.characteristics.keywords` directly.
    "deathtouch",
    "double strike",
    "first strike",
    "flying",
    "haste",
    "hexproof",
    "indestructible",
    "lifelink",
    "menace",
    "reach",
    "trample",
    "vigilance",
}


def _sync_keyword_counter_abilities(obj: GameObject) -> None:
    """Mirror keyword counters into `obj.characteristics.abilities`."""
    abilities = obj.characteristics.abilities or []

    # Remove previously injected keyword-counter abilities.
    abilities = [
        a for a in abilities
        if not (isinstance(a, dict) and a.get("_from_counter") is True)
    ]

    # Add abilities for any active keyword counters.
    for kw in sorted(_KEYWORD_COUNTER_TYPES):
        if obj.state.counters.get(kw, 0) > 0:
            abilities.append({"keyword": kw, "_from_counter": True})

    obj.characteristics.abilities = abilities


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


def _handle_pt_modification(event: Event, state: GameState):
    """
    Handle PT_MODIFICATION event - temporary P/T changes.

    Stores the modification on the object's state for QUERY handlers to use.
    Modifications with duration='end_of_turn' are cleared at cleanup step.
    """
    object_id = event.payload.get('object_id')
    power_mod = event.payload.get('power_mod', 0)
    toughness_mod = event.payload.get('toughness_mod', 0)
    duration = event.payload.get('duration', 'end_of_turn')
    if isinstance(duration, str):
        d = duration.strip().lower().replace(" ", "_")
        if d in {"until_end_of_turn", "until_eot", "eot"}:
            duration = "end_of_turn"

    if object_id not in state.objects:
        return

    obj = state.objects[object_id]

    # Initialize temporary modifiers list if not present
    if not hasattr(obj.state, 'pt_modifiers'):
        obj.state.pt_modifiers = []

    # Add the modifier
    obj.state.pt_modifiers.append({
        'power': power_mod,
        'toughness': toughness_mod,
        'duration': duration,
        'timestamp': state.timestamp
    })


def _handle_pt_change(event: Event, state: GameState):
    """
    Handle PT_CHANGE event - legacy alias for temporary P/T deltas.

    Expected payload keys (common in older card files):
        object_id: str
        power: int (delta)
        toughness: int (delta)
        duration: str (e.g. 'until_end_of_turn')
    """
    object_id = event.payload.get('object_id')
    power_mod = event.payload.get('power', 0)
    toughness_mod = event.payload.get('toughness', 0)
    duration = event.payload.get('duration', 'end_of_turn')
    if isinstance(duration, str):
        d = duration.strip().lower().replace(" ", "_")
        if d in {"until_end_of_turn", "until_eot", "eot"}:
            duration = "end_of_turn"

    if object_id not in state.objects:
        return

    obj = state.objects[object_id]
    if not hasattr(obj.state, 'pt_modifiers'):
        obj.state.pt_modifiers = []

    obj.state.pt_modifiers.append({
        'power': power_mod,
        'toughness': toughness_mod,
        'duration': duration,
        'timestamp': state.timestamp
    })


def _handle_grant_keyword(event: Event, state: GameState):
    """
    Handle keyword/ability grants that older card files express as events.

    Supported event types:
      - GRANT_KEYWORD / KEYWORD_GRANT: payload {object_id, keyword, duration}
      - GRANT_ABILITY: payload {object_id, abilities=[...], duration}
    """
    object_id = event.payload.get("object_id")
    if not object_id or object_id not in state.objects:
        return

    obj = state.objects[object_id]

    duration = event.payload.get("duration", "end_of_turn")
    if isinstance(duration, str):
        d = duration.strip().lower().replace(" ", "_")
        if d in {"until_end_of_turn", "until_eot", "eot"}:
            duration = "end_of_turn"

    keywords: list[str] = []
    if event.type == EventType.GRANT_ABILITY:
        abilities = event.payload.get("abilities") or []
        if isinstance(abilities, str):
            abilities = [abilities]
        if isinstance(abilities, (list, tuple, set)):
            keywords = [str(a).strip().lower() for a in abilities if str(a).strip()]
    else:
        kw = event.payload.get("keyword")
        if kw:
            keywords = [str(kw).strip().lower()]

    if not keywords:
        return

    for kw in keywords:
        obj.characteristics.abilities.append({
            "keyword": kw,
            "_temporary": True,
            "_duration": duration,
        })


def _handle_object_destroyed(event: Event, state: GameState):
    """
    Handle OBJECT_DESTROYED - move to graveyard.

    Note: Interceptor cleanup is handled AFTER the REACT phase
    by _cleanup_departed_interceptors() so death triggers can fire.
    """
    object_id = event.payload.get('object_id')

    if object_id not in state.objects:
        return

    obj = state.objects[object_id]
    owner_id = obj.owner

    # Remove from any zone that currently references it (robust).
    _remove_object_from_all_zones(object_id, state)

    # Add to owner's graveyard
    gy_key = f"graveyard_{owner_id}"
    if gy_key in state.zones:
        state.zones[gy_key].objects.append(object_id)

    obj.zone = ZoneType.GRAVEYARD
    obj.entered_zone_at = state.timestamp

    # NOTE: Interceptor cleanup moved to _cleanup_departed_interceptors()
    # which runs AFTER the REACT phase, allowing death triggers to fire


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


def _handle_create_token(event: Event, state: GameState):
    """
    Handle CREATE_TOKEN event.

    Creates a new GameObject representing a token and adds it to the battlefield.

    Payload:
        controller: Player ID who controls the token
        token: dict with token characteristics:
            - name: str
            - power: int
            - toughness: int
            - types: set[CardType] (optional, defaults to {CREATURE})
            - subtypes: set[str] (optional)
            - colors: set[Color] (optional)
            - text: str (optional)
            - abilities: list[dict] (optional, for keywords like flying, haste)
        count: int (optional, defaults to 1)
        tapped: bool (optional, whether token enters tapped)
    """
    from .types import new_id, GameObject, Characteristics, ObjectState

    controller_id = event.payload.get('controller')
    token_data = event.payload.get('token', {})
    count = event.payload.get('count', 1)
    enters_tapped = event.payload.get('tapped', False)

    if not controller_id or controller_id not in state.players:
        return

    for _ in range(count):
        # Build characteristics from token data
        types = token_data.get('types', {CardType.CREATURE})
        if isinstance(types, list):
            types = set(types)

        subtypes = token_data.get('subtypes', set())
        if isinstance(subtypes, list):
            subtypes = set(subtypes)

        colors = token_data.get('colors', set())
        if isinstance(colors, list):
            colors = set(colors)

        characteristics = Characteristics(
            types=types,
            subtypes=subtypes,
            colors=colors,
            power=token_data.get('power'),
            toughness=token_data.get('toughness'),
            abilities=token_data.get('abilities', [])
        )

        # Create the token object
        obj_id = new_id()
        token = GameObject(
            id=obj_id,
            name=token_data.get('name', 'Token'),
            owner=controller_id,
            controller=controller_id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=characteristics,
            state=ObjectState(
                is_token=True,
                tapped=enters_tapped
            ),
            created_at=state.next_timestamp(),
            entered_zone_at=state.timestamp
        )

        # Add to state
        state.objects[obj_id] = token

        # Add to battlefield zone
        battlefield_key = 'battlefield'
        if battlefield_key in state.zones:
            state.zones[battlefield_key].objects.append(obj_id)


def _handle_exile(event: Event, state: GameState):
    """
    Handle EXILE event.

    Moves object(s) from their current zone to exile.

    Payload:
        object_id: str - single object to exile
        OR
        object_ids: list[str] - multiple objects to exile
    """
    # Gather all object IDs to exile
    object_ids = []
    if 'object_id' in event.payload:
        object_ids.append(event.payload['object_id'])
    if 'object_ids' in event.payload:
        object_ids.extend(event.payload['object_ids'])

    exile_key = 'exile'
    if exile_key not in state.zones:
        return

    for object_id in object_ids:
        if object_id not in state.objects:
            continue

        obj = state.objects[object_id]

        # Remove from any zone that currently references it (robust).
        _remove_object_from_all_zones(object_id, state)

        # Add to exile zone
        state.zones[exile_key].objects.append(object_id)

        # Update object's zone
        obj.zone = ZoneType.EXILE
        obj.entered_zone_at = state.timestamp


def _parse_duration_turns(duration: object, state: GameState) -> Optional[int]:
    """
    Convert common duration strings into an inclusive turn number.

    Returns:
        int: last turn number the permission is valid for (inclusive)
        None: if unknown/unbounded
    """
    if not isinstance(duration, str):
        return None

    d = duration.strip().lower().replace(" ", "_")
    if d in {"", "forever"}:
        return None

    # "next_end_step" is still this turn.
    if d in {"next_end_step", "end_of_turn", "end_of_this_turn", "this_turn", "until_end_of_turn", "until_eot", "eot"}:
        return state.turn_number

    if d in {"end_of_next_turn", "until_end_of_next_turn", "next_turn"}:
        return state.turn_number + 1

    return None


def _handle_exile_from_top(event: Event, state: GameState):
    """
    Handle EXILE_FROM_TOP and related impulse-exile events.

    Supported event types (various card scripts):
      - EXILE_FROM_TOP / EXILE_TOP
      - EXILE_TOP_CARD
      - EXILE_TOP_PLAY
      - IMPULSE_DRAW

    Payload (best-effort, keys vary by set):
      - player: player_id whose library to exile from
      - count / amount: number of cards to exile (default 1)
      - may_play: bool (EXILE_TOP_CARD) - whether some player may play the card(s)
      - caster: player_id who may play the exiled card(s) (if may_play)
      - until / duration / playable_until: duration string (optional)
    """
    player_id = event.payload.get("player") or event.controller or state.active_player
    if not player_id or player_id not in state.players:
        return

    amount = event.payload.get("amount")
    count = event.payload.get("count", amount)
    if count is None:
        count = 1
    try:
        count = int(count)
    except Exception:
        count = 1
    if count <= 0:
        return

    library_key = f"library_{player_id}"
    exile_key = "exile"
    library = state.zones.get(library_key)
    exile_zone = state.zones.get(exile_key)
    if not library or not exile_zone:
        return

    # Determine whether the exiled cards are playable from exile.
    may_play = bool(event.payload.get("may_play"))
    if event.type in {EventType.IMPULSE_DRAW, EventType.EXILE_TOP_PLAY}:
        may_play = True

    playable_by = event.payload.get("caster") or event.controller or player_id
    duration = (
        event.payload.get("until")
        or event.payload.get("duration")
        or event.payload.get("playable_until")
    )
    expires_turn = _parse_duration_turns(duration, state)

    to_exile = list(library.objects[:count])
    if not to_exile:
        return

    for obj_id in to_exile:
        if obj_id not in state.objects:
            continue

        # Remove from any zone that currently references it (robust).
        _remove_object_from_all_zones(obj_id, state)

        exile_zone.objects.append(obj_id)
        obj = state.objects[obj_id]
        obj.zone = ZoneType.EXILE
        obj.entered_zone_at = state.timestamp

        if may_play and playable_by:
            obj.state._playable_from_exile_by = playable_by
            if expires_turn is not None:
                obj.state._playable_from_exile_through_turn = expires_turn


def _handle_impulse_to_graveyard(event: Event, state: GameState):
    """
    Handle IMPULSE_TO_GRAVEYARD (look at top N, take some, rest to graveyard).

    Payload (best-effort):
      - player: player_id
      - look: N (default 1)
      - take: M (default 1)
    """
    player_id = event.payload.get("player") or event.controller or state.active_player
    if not player_id or player_id not in state.players:
        return

    look = event.payload.get("look", 1)
    take = event.payload.get("take", 1)
    try:
        look = int(look)
        take = int(take)
    except Exception:
        look = 1
        take = 1

    if look <= 0:
        return
    take = max(0, min(take, look))

    library_key = f"library_{player_id}"
    hand_key = f"hand_{player_id}"
    graveyard_key = f"graveyard_{player_id}"
    library = state.zones.get(library_key)
    hand = state.zones.get(hand_key)
    graveyard = state.zones.get(graveyard_key)
    if not library or not hand or not graveyard:
        return

    seen = list(library.objects[:look])
    if not seen:
        return

    to_hand = seen[:take]
    to_graveyard = seen[take:]

    for obj_id in to_hand:
        if obj_id not in state.objects:
            continue
        _remove_object_from_all_zones(obj_id, state)
        hand.objects.append(obj_id)
        obj = state.objects[obj_id]
        obj.zone = ZoneType.HAND
        obj.entered_zone_at = state.timestamp

    for obj_id in to_graveyard:
        if obj_id not in state.objects:
            continue
        _remove_object_from_all_zones(obj_id, state)
        graveyard.objects.append(obj_id)
        obj = state.objects[obj_id]
        obj.zone = ZoneType.GRAVEYARD
        obj.entered_zone_at = state.timestamp


def _handle_surveil(event: Event, state: GameState):
    """
    Handle SURVEIL event.

    Look at top N cards of library, put any number in graveyard (rest stay on top).

    Payload:
        player: player_id
        amount: N (number of cards to surveil)
        to_graveyard: list of indices (0-indexed) to put in graveyard
                      If not provided, creates a PendingChoice for the player
        source_id: Optional source card ID for the choice
    """
    from .types import PendingChoice

    player_id = event.payload.get('player')
    # Support both 'amount' and legacy 'count' keys.
    amount = event.payload.get('amount') or event.payload.get('count', 1)

    library_key = f"library_{player_id}"
    graveyard_key = f"graveyard_{player_id}"

    if library_key not in state.zones or graveyard_key not in state.zones:
        return

    library = state.zones[library_key]
    graveyard = state.zones[graveyard_key]

    # Get top N cards (without removing yet)
    cards_to_look = library.objects[:amount]

    if not cards_to_look:
        return

    # Check if player selection is provided
    to_graveyard_indices = event.payload.get('to_graveyard')

    if to_graveyard_indices is None:
        # No selection provided - create a choice for the player
        source_id = event.payload.get('source_id', event.source or '')
        choice = PendingChoice(
            choice_type="surveil",
            player=player_id,
            prompt=f"Surveil {amount}: Choose cards to put into your graveyard",
            options=cards_to_look,  # Card IDs being surveiled
            source_id=source_id,
            min_choices=0,
            max_choices=len(cards_to_look),
            callback_data={"surveil_count": amount}
        )
        state.pending_choice = choice
        return  # Don't process yet - wait for player choice

    # Some call sites emit post-resolution SURVEIL summary payloads where
    # to_graveyard is a count, not an index/card-id list. In that case, skip
    # re-processing library order here.
    if isinstance(to_graveyard_indices, int):
        return

    if not isinstance(to_graveyard_indices, (list, tuple, set)):
        return

    # Convert to set for O(1) lookup
    graveyard_set = set(to_graveyard_indices)

    # Process cards - those in graveyard_set go to graveyard, others stay on top
    cards_to_gy = []
    cards_to_keep = []

    for i, card_id in enumerate(cards_to_look):
        # Accept either indices (int) or direct card IDs (str).
        if i in graveyard_set or card_id in graveyard_set:
            cards_to_gy.append(card_id)
        else:
            cards_to_keep.append(card_id)

    # Remove all surveiled cards from library
    for card_id in cards_to_look:
        library.objects.remove(card_id)

    # Put cards back on top (cards_to_keep) - in original order
    library.objects = cards_to_keep + library.objects

    # Put cards in graveyard
    for card_id in cards_to_gy:
        graveyard.objects.append(card_id)
        if card_id in state.objects:
            state.objects[card_id].zone = ZoneType.GRAVEYARD
            state.objects[card_id].entered_zone_at = state.timestamp


def _handle_scry(event: Event, state: GameState):
    """
    Handle SCRY event.

    Look at top N cards of library, put any number on bottom (rest stay on top).

    Payload:
        player: player_id
        count/amount: N (number of cards to scry) - accepts both keys
        to_bottom: list of indices (0-indexed) to put on bottom
                   If not provided, creates a PendingChoice for the player
        source_id: Optional source card ID for the choice
    """
    from .types import PendingChoice

    player_id = event.payload.get('player')
    # Support both 'count' and 'amount' (many cards use 'amount')
    count = event.payload.get('count') or event.payload.get('amount', 1)

    library_key = f"library_{player_id}"

    if library_key not in state.zones:
        return

    library = state.zones[library_key]

    # Get top N cards (without removing yet)
    cards_to_look = library.objects[:count]

    if not cards_to_look:
        return

    # Check if player selection is provided
    to_bottom_indices = event.payload.get('to_bottom')

    if to_bottom_indices is None:
        # No selection provided - create a choice for the player
        source_id = event.payload.get('source_id', event.source or '')
        choice = PendingChoice(
            choice_type="scry",
            player=player_id,
            prompt=f"Scry {count}: Choose cards to put on the bottom of your library",
            options=cards_to_look,  # Card IDs being scried
            source_id=source_id,
            min_choices=0,
            max_choices=len(cards_to_look),
            callback_data={"scry_count": count}
        )
        state.pending_choice = choice
        return  # Don't process yet - wait for player choice

    # Some call sites emit post-resolution SCRY summary payloads where
    # to_bottom is a count, not an index list. In that case, skip
    # re-processing library order here.
    if isinstance(to_bottom_indices, int):
        return

    if not isinstance(to_bottom_indices, (list, tuple, set)):
        return

    # Convert to set for O(1) lookup
    bottom_set = set(to_bottom_indices)

    # Process cards - those in bottom_set go to bottom, others stay on top
    cards_to_bottom = []
    cards_to_keep = []

    for i, card_id in enumerate(cards_to_look):
        if i in bottom_set:
            cards_to_bottom.append(card_id)
        else:
            cards_to_keep.append(card_id)

    # Remove all scried cards from library
    for card_id in cards_to_look:
        library.objects.remove(card_id)

    # Put cards back on top (cards_to_keep) - in original order
    library.objects = cards_to_keep + library.objects

    # Put cards on bottom
    library.objects.extend(cards_to_bottom)


def _handle_mill(event: Event, state: GameState):
    """
    Handle MILL event.

    Move top N cards from library directly to graveyard.

    Payload:
        player: player_id
        count/amount: N (number of cards to mill) - accepts both keys
    """
    player_id = event.payload.get('player')
    # Support both 'count' and 'amount' (many cards use 'amount')
    count = event.payload.get('count') or event.payload.get('amount', 1)

    library_key = f"library_{player_id}"
    graveyard_key = f"graveyard_{player_id}"

    if library_key not in state.zones or graveyard_key not in state.zones:
        return

    library = state.zones[library_key]
    graveyard = state.zones[graveyard_key]

    for _ in range(count):
        if not library.objects:
            break

        card_id = library.objects.pop(0)  # Top of library
        _remove_object_from_all_zones(card_id, state)
        graveyard.objects.append(card_id)

        if card_id in state.objects:
            state.objects[card_id].zone = ZoneType.GRAVEYARD
            state.objects[card_id].entered_zone_at = state.timestamp


def _handle_discard(event: Event, state: GameState):
    """
    Handle DISCARD event.

    Moves card(s) from hand to graveyard.

    Payload:
        object_id: str - specific card to discard
        OR
        player: str + amount: int - player discards N cards (requires choice)
    """
    player_id = event.payload.get('player')
    object_id = event.payload.get('object_id')

    if object_id:
        # Discard a specific card
        if object_id not in state.objects:
            return

        obj = state.objects[object_id]
        # Only discard from a hand zone. (Some effects can discard cards a player
        # doesn't own, so don't assume `hand_{obj.owner}`.)
        in_hand = any(
            z.type == ZoneType.HAND and object_id in z.objects
            for z in state.zones.values()
        )
        if not in_hand:
            return

        # Discarded cards always go to their owner's graveyard.
        graveyard_key = f"graveyard_{obj.owner}"

        if graveyard_key not in state.zones:
            return

        graveyard = state.zones[graveyard_key]

        _remove_object_from_all_zones(object_id, state)
        graveyard.objects.append(object_id)
        obj.zone = ZoneType.GRAVEYARD
        obj.entered_zone_at = state.timestamp


def _handle_target_required(event: Event, state: GameState):
    """
    Handle TARGET_REQUIRED event.

    Creates a PendingChoice for target selection and pauses game execution.
    When the player submits their choice, _execute_targeted_effect is called.

    Payload:
        source: str           - Object ID causing this targeting requirement
        controller: str       - Player who chooses targets (defaults to source controller)
        effect: str           - Effect type: 'damage', 'destroy', 'exile', 'bounce', etc.
        effect_params: dict   - Parameters for the effect (e.g., {'amount': 3} for damage)
        effects: list[dict]   - Multiple effects to apply (overrides effect/effect_params)
                                Each dict has: {'effect': str, 'params': dict}
        target_filter: str    - Filter type: 'any', 'creature', 'opponent_creature',
                                'your_creature', 'opponent', 'player', 'nonland_permanent'
        min_targets: int      - Minimum targets (default 1)
        max_targets: int      - Maximum targets (default 1)
        optional: bool        - If True, may choose 0 targets
        prompt: str           - UI text (auto-generated if not provided)
        divide_amount: int    - If set, creates a two-step choice: select targets, then allocate
                                the amount among them (e.g., "deal 5 damage divided as you choose")
    """
    from .targeting import (
        TargetingSystem, TargetRequirement, TargetFilter,
        creature_filter, any_target_filter, permanent_filter, player_filter
    )

    source_id = event.payload.get('source')
    effect = event.payload.get('effect', 'damage')
    effect_params = event.payload.get('effect_params', {})
    effects = event.payload.get('effects')  # Multi-effect support
    target_filter_type = event.payload.get('target_filter', 'any')
    min_targets = event.payload.get('min_targets', 1)
    max_targets = event.payload.get('max_targets', 1)
    optional = event.payload.get('optional', False)
    prompt = event.payload.get('prompt')
    divide_amount = event.payload.get('divide_amount')  # For damage division

    # Get source object and controller
    source_obj = state.objects.get(source_id)
    if not source_obj:
        return

    controller_id = event.payload.get('controller', source_obj.controller)

    # Build target filter based on filter type
    target_requirement = _build_target_requirement(
        target_filter_type, source_obj, min_targets, max_targets, optional
    )

    # Check for pre-computed legal targets override (for complex targeting like
    # "destroy target creature that player controls")
    legal_targets_override = event.payload.get('legal_targets_override')

    if legal_targets_override is not None:
        # Use the override directly
        legal_targets = list(legal_targets_override)
    else:
        # Get legal targets using the targeting system
        targeting_system = TargetingSystem(state)
        legal_targets = targeting_system.get_legal_targets(
            target_requirement, source_obj, controller_id
        )

        # For 'any' and 'player'/'opponent' filters, add players to targets
        if target_filter_type in ('any', 'player'):
            for player_id in state.players:
                if player_id not in legal_targets:
                    legal_targets.append(player_id)
        elif target_filter_type == 'opponent':
            for player_id in state.players:
                if player_id != controller_id and player_id not in legal_targets:
                    legal_targets.append(player_id)

    # If no legal targets and not optional, ability fizzles
    if not legal_targets and not optional:
        return

    # If no legal targets but optional, skip silently
    if not legal_targets and optional:
        return

    # Adjust min_targets if optional
    actual_min = 0 if optional else min_targets

    # Generate prompt if not provided
    if not prompt:
        prompt = _generate_target_prompt(effect, effect_params, target_filter_type)

    # Build callback data
    callback_data = {
        'handler': _execute_targeted_effect,
        'effect': effect,
        'effect_params': effect_params,
        'source_id': source_id,
        'controller_id': controller_id,
    }

    # Multi-effect support: if effects list is provided, use it instead
    if effects:
        callback_data['effects'] = effects

    # Damage division support: pass divide_amount for two-step allocation
    if divide_amount:
        callback_data['divide_amount'] = divide_amount

    # Create PendingChoice
    choice = PendingChoice(
        choice_type="target_with_callback",
        player=controller_id,
        prompt=prompt,
        options=legal_targets,
        source_id=source_id,
        min_choices=actual_min,
        max_choices=min(max_targets, len(legal_targets)),
        callback_data=callback_data
    )
    state.pending_choice = choice


def _build_target_requirement(
    filter_type: str,
    source_obj,
    min_targets: int,
    max_targets: int,
    optional: bool
):
    """Build a TargetRequirement based on filter type string."""
    from .targeting import (
        TargetRequirement, TargetFilter,
        creature_filter, any_target_filter, permanent_filter, player_filter
    )

    # Map filter types to TargetFilter constructors
    if filter_type == 'any':
        tf = any_target_filter()
    elif filter_type == 'creature':
        tf = creature_filter()
    elif filter_type == 'opponent_creature':
        tf = creature_filter(controller='opponent')
    elif filter_type == 'your_creature':
        tf = creature_filter(controller='you')
    elif filter_type == 'other_creature_you_control':
        tf = creature_filter(controller='you', exclude_self=True)
    elif filter_type == 'opponent':
        tf = player_filter(controller='opponent')
    elif filter_type == 'player':
        tf = player_filter()
    elif filter_type == 'nonland_permanent':
        tf = permanent_filter()
        # Exclude lands
        tf.types = {CardType.CREATURE, CardType.ARTIFACT, CardType.ENCHANTMENT, CardType.PLANESWALKER}
    elif filter_type == 'permanent':
        tf = permanent_filter()
    elif filter_type == 'creature_in_your_graveyard':
        tf = creature_filter(controller='you')
        tf.zones = {ZoneType.GRAVEYARD}
    elif filter_type == 'creature_in_graveyard':
        tf = creature_filter()
        tf.zones = {ZoneType.GRAVEYARD}
    else:
        # Default to any target
        tf = any_target_filter()

    count_type = 'up_to' if optional else 'exactly'

    return TargetRequirement(
        filter=tf,
        count=max_targets,
        count_type=count_type,
        optional=optional
    )


def _generate_target_prompt(effect: str, effect_params: dict, filter_type: str) -> str:
    """Generate a user-friendly prompt for target selection."""
    # Build target description
    target_desc = {
        'any': 'any target',
        'creature': 'target creature',
        'opponent_creature': "target creature you don't control",
        'your_creature': 'target creature you control',
        'other_creature_you_control': 'another target creature you control',
        'opponent': 'target opponent',
        'player': 'target player',
        'nonland_permanent': 'target nonland permanent',
        'permanent': 'target permanent',
        'creature_in_your_graveyard': 'target creature card in your graveyard',
        'creature_in_graveyard': 'target creature card in a graveyard',
    }.get(filter_type, 'a target')

    # Build effect description
    if effect == 'damage':
        amount = effect_params.get('amount', 0)
        return f"Deal {amount} damage to {target_desc}"
    elif effect == 'destroy':
        return f"Destroy {target_desc}"
    elif effect == 'exile':
        return f"Exile {target_desc}"
    elif effect == 'bounce':
        return f"Return {target_desc} to its owner's hand"
    elif effect == 'tap':
        return f"Tap {target_desc}"
    elif effect == 'untap':
        return f"Untap {target_desc}"
    elif effect == 'pump':
        power = effect_params.get('power_mod', 0)
        toughness = effect_params.get('toughness_mod', 0)
        sign_p = '+' if power >= 0 else ''
        sign_t = '+' if toughness >= 0 else ''
        return f"{target_desc} gets {sign_p}{power}/{sign_t}{toughness} until end of turn"
    elif effect == 'counter_add':
        counter_type = effect_params.get('counter_type', '+1/+1')
        amount = effect_params.get('amount', 1)
        return f"Put {amount} {counter_type} counter(s) on {target_desc}"
    elif effect == 'grant_keyword':
        keyword = effect_params.get('keyword', 'an ability')
        return f"{target_desc} gains {keyword} until end of turn"
    elif effect == 'life_change':
        amount = effect_params.get('amount', 0)
        if amount >= 0:
            return f"{target_desc} gains {amount} life"
        else:
            return f"{target_desc} loses {abs(amount)} life"
    elif effect == 'graveyard_to_hand':
        return f"Return {target_desc} to its owner's hand"
    else:
        return f"Choose {target_desc}"


def _execute_targeted_effect(choice: PendingChoice, selected: list, state: GameState) -> list[Event]:
    """
    Execute the targeted effect after player selects targets.

    Called as the callback handler when a target_with_callback choice resolves.

    If divide_amount is present in callback_data, this doesn't execute effects directly.
    Instead, it returns a special marker event that triggers the allocation phase.
    """
    if not selected:
        return []  # No targets selected (optional effect)

    source_id = choice.callback_data.get('source_id')
    divide_amount = choice.callback_data.get('divide_amount')

    # Check for damage division - need to create allocation choice instead of executing
    if divide_amount:
        return _create_divide_allocation_choice(choice, selected, state)

    # Check for multi-effect support
    effects = choice.callback_data.get('effects')
    if effects:
        return _execute_multi_effects(effects, selected, source_id, state)

    # Standard single effect execution
    effect = choice.callback_data.get('effect', 'damage')
    effect_params = choice.callback_data.get('effect_params', {})

    events = []

    for target_id in selected:
        if effect == 'damage':
            amount = effect_params.get('amount', 0)
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': target_id, 'amount': amount, 'source': source_id, 'is_combat': False},
                source=source_id
            ))

        elif effect == 'destroy':
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': target_id},
                source=source_id
            ))

        elif effect == 'exile':
            events.append(Event(
                type=EventType.EXILE,
                payload={'object_id': target_id},
                source=source_id
            ))

        elif effect == 'bounce':
            # Return to hand
            obj = state.objects.get(target_id)
            if obj:
                owner_hand = f"hand_{obj.owner}"
                events.append(Event(
                    type=EventType.ZONE_CHANGE,
                    payload={
                        'object_id': target_id,
                        'from_zone': 'battlefield',
                        'to_zone': owner_hand,
                        'from_zone_type': ZoneType.BATTLEFIELD,
                        'to_zone_type': ZoneType.HAND
                    },
                    source=source_id
                ))

        elif effect == 'tap':
            events.append(Event(
                type=EventType.TAP,
                payload={'object_id': target_id},
                source=source_id
            ))

        elif effect == 'untap':
            events.append(Event(
                type=EventType.UNTAP,
                payload={'object_id': target_id},
                source=source_id
            ))

        elif effect == 'pump':
            power_mod = effect_params.get('power_mod', 0)
            toughness_mod = effect_params.get('toughness_mod', 0)
            events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': target_id,
                    'power_mod': power_mod,
                    'toughness_mod': toughness_mod,
                    'duration': 'end_of_turn'
                },
                source=source_id
            ))

        elif effect == 'counter_add':
            counter_type = effect_params.get('counter_type', '+1/+1')
            amount = effect_params.get('amount', 1)
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    'object_id': target_id,
                    'counter_type': counter_type,
                    'amount': amount
                },
                source=source_id
            ))

        elif effect == 'counter_remove':
            counter_type = effect_params.get('counter_type', '+1/+1')
            amount = effect_params.get('amount', 1)
            events.append(Event(
                type=EventType.COUNTER_REMOVED,
                payload={
                    'object_id': target_id,
                    'counter_type': counter_type,
                    'amount': amount
                },
                source=source_id
            ))

        elif effect == 'grant_keyword':
            keyword = effect_params.get('keyword', '')
            events.append(Event(
                type=EventType.GRANT_KEYWORD,
                payload={
                    'object_id': target_id,
                    'keyword': keyword,
                    'duration': effect_params.get('duration', 'end_of_turn')
                },
                source=source_id
            ))

        elif effect == 'life_change':
            # For effects targeting players
            amount = effect_params.get('amount', 0)
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': target_id, 'amount': amount},
                source=source_id
            ))

        elif effect == 'graveyard_to_hand':
            # Return target card from graveyard to owner's hand
            target_obj = state.objects.get(target_id)
            if target_obj and target_obj.zone == ZoneType.GRAVEYARD:
                events.append(Event(
                    type=EventType.ZONE_CHANGE,
                    payload={
                        'object_id': target_id,
                        'from_zone': f'graveyard_{target_obj.owner}',
                        'to_zone': f'hand_{target_obj.owner}',
                        'to_zone_type': ZoneType.HAND
                    },
                    source=source_id
                ))

    return events


def _create_divide_allocation_choice(
    original_choice: PendingChoice,
    selected_targets: list,
    state: GameState
) -> list[Event]:
    """
    Create a divide_allocation PendingChoice after targets are selected.

    This is the second step in damage division: allocate the amount among targets.
    """
    divide_amount = original_choice.callback_data.get('divide_amount')
    source_id = original_choice.callback_data.get('source_id')
    controller_id = original_choice.callback_data.get('controller_id')
    effect = original_choice.callback_data.get('effect', 'damage')
    effect_params = original_choice.callback_data.get('effect_params', {})

    # Build options with target info for the UI
    options = []
    for target_id in selected_targets:
        obj = state.objects.get(target_id)
        if obj:
            options.append({
                'id': target_id,
                'name': obj.name,
                'type': 'creature' if hasattr(obj, 'characteristics') else 'permanent'
            })
        elif target_id in state.players:
            player = state.players[target_id]
            options.append({
                'id': target_id,
                'name': player.name,
                'type': 'player',
                'life': player.life
            })
        else:
            options.append({'id': target_id, 'name': target_id, 'type': 'unknown'})

    choice = PendingChoice(
        choice_type="divide_allocation",
        player=controller_id,
        prompt=f"Allocate {divide_amount} {effect} among {len(selected_targets)} target(s)",
        options=options,
        source_id=source_id,
        min_choices=1,  # Must allocate to at least 1 target
        max_choices=len(selected_targets),
        callback_data={
            'handler': _execute_divided_effect,
            'total_amount': divide_amount,
            'effect': effect,
            'effect_params': effect_params,
            'source_id': source_id,
            'selected_targets': selected_targets,
            'counter_type': effect_params.get('counter_type', '+1/+1'),
        }
    )
    state.pending_choice = choice

    return []  # Don't execute effects yet - wait for allocation


def _execute_divided_effect(
    choice: PendingChoice,
    allocations: dict,
    state: GameState
) -> list[Event]:
    """
    Execute the divided effect based on player's allocation.

    Args:
        allocations: Dict mapping target_id -> amount allocated
    """
    source_id = choice.callback_data.get('source_id')
    effect = choice.callback_data.get('effect', 'damage')
    total_amount = choice.callback_data.get('total_amount', 0)

    # Validate total allocation equals required amount
    total_allocated = sum(allocations.values())
    if total_allocated != total_amount:
        # Invalid allocation - this shouldn't happen if UI validates
        return []

    events = []

    for target_id, amount in allocations.items():
        if amount <= 0:
            continue

        if effect == 'damage':
            events.append(Event(
                type=EventType.DAMAGE,
                payload={
                    'target': target_id,
                    'amount': amount,
                    'source': source_id,
                    'is_combat': False
                },
                source=source_id
            ))
        elif effect == 'counter_add':
            counter_type = choice.callback_data.get('counter_type', '+1/+1')
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    'object_id': target_id,
                    'counter_type': counter_type,
                    'amount': amount
                },
                source=source_id
            ))
        elif effect == 'life_change':
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': target_id, 'amount': amount},
                source=source_id
            ))

    return events


def _execute_multi_effects(
    effects: list[dict],
    selected_targets: list,
    source_id: str,
    state: GameState
) -> list[Event]:
    """
    Execute multiple effects on selected targets.

    Used for cards like "Tap target creature. It doesn't untap during next untap step."

    Args:
        effects: List of effect specs [{'effect': 'tap'}, {'effect': 'stun'}]
    """
    events = []

    for target_id in selected_targets:
        for effect_spec in effects:
            effect = effect_spec.get('effect')
            params = effect_spec.get('params', {})

            effect_events = _create_effect_event(effect, params, target_id, source_id, state)
            events.extend(effect_events)

    return events


def _create_effect_event(
    effect: str,
    params: dict,
    target_id: str,
    source_id: str,
    state: GameState
) -> list[Event]:
    """Create event(s) for a single effect application."""
    events = []

    if effect == 'damage':
        amount = params.get('amount', 0)
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': amount, 'source': source_id, 'is_combat': False},
            source=source_id
        ))

    elif effect == 'destroy':
        events.append(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': target_id},
            source=source_id
        ))

    elif effect == 'exile':
        events.append(Event(
            type=EventType.EXILE,
            payload={'object_id': target_id},
            source=source_id
        ))

    elif effect == 'bounce':
        obj = state.objects.get(target_id)
        if obj:
            owner_hand = f"hand_{obj.owner}"
            events.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': target_id,
                    'from_zone': 'battlefield',
                    'to_zone': owner_hand,
                    'from_zone_type': ZoneType.BATTLEFIELD,
                    'to_zone_type': ZoneType.HAND
                },
                source=source_id
            ))

    elif effect == 'tap':
        events.append(Event(
            type=EventType.TAP,
            payload={'object_id': target_id},
            source=source_id
        ))

    elif effect == 'untap':
        events.append(Event(
            type=EventType.UNTAP,
            payload={'object_id': target_id},
            source=source_id
        ))

    elif effect == 'stun':
        # "Doesn't untap during next untap step" - add stun counter
        events.append(Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': target_id, 'counter_type': 'stun', 'amount': 1},
            source=source_id
        ))

    elif effect == 'freeze':
        # Tap + stun combo (tap and doesn't untap)
        events.append(Event(
            type=EventType.TAP,
            payload={'object_id': target_id},
            source=source_id
        ))
        events.append(Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': target_id, 'counter_type': 'stun', 'amount': 1},
            source=source_id
        ))

    elif effect == 'pump':
        power_mod = params.get('power_mod', 0)
        toughness_mod = params.get('toughness_mod', 0)
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': target_id,
                'power_mod': power_mod,
                'toughness_mod': toughness_mod,
                'duration': 'end_of_turn'
            },
            source=source_id
        ))

    elif effect == 'counter_add':
        counter_type = params.get('counter_type', '+1/+1')
        amount = params.get('amount', 1)
        events.append(Event(
            type=EventType.COUNTER_ADDED,
            payload={
                'object_id': target_id,
                'counter_type': counter_type,
                'amount': amount
            },
            source=source_id
        ))

    elif effect == 'grant_keyword':
        keyword = params.get('keyword', '')
        events.append(Event(
            type=EventType.GRANT_KEYWORD,
            payload={
                'object_id': target_id,
                'keyword': keyword,
                'duration': params.get('duration', 'end_of_turn')
            },
            source=source_id
        ))

    elif effect == 'life_change':
        amount = params.get('amount', 0)
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': target_id, 'amount': amount},
            source=source_id
        ))

    return events


# =============================================================================
# Event Handler Registry
# =============================================================================

EVENT_HANDLERS = {
    EventType.DAMAGE: _handle_damage,
    EventType.LIFE_CHANGE: _handle_life_change,
    EventType.DRAW: _handle_draw,
    EventType.OBJECT_CREATED: _handle_object_created,
    EventType.ZONE_CHANGE: _handle_zone_change,
    EventType.TAP: _handle_tap,
    EventType.UNTAP: _handle_untap,
    EventType.GAIN_CONTROL: _handle_gain_control,
    EventType.COUNTER_ADDED: _handle_counter_added,
    EventType.COUNTER_REMOVED: _handle_counter_removed,
    EventType.PT_MODIFICATION: _handle_pt_modification,
    EventType.PT_MODIFIER: _handle_pt_modification,
    EventType.PT_CHANGE: _handle_pt_change,
    EventType.PT_MODIFY: _handle_pt_change,
    EventType.TEMPORARY_PT_CHANGE: _handle_pt_change,
    EventType.PUMP: _handle_pt_change,
    EventType.TEMPORARY_BOOST: _handle_pt_change,
    EventType.GRANT_KEYWORD: _handle_grant_keyword,
    EventType.KEYWORD_GRANT: _handle_grant_keyword,
    EventType.GRANT_ABILITY: _handle_grant_keyword,
    EventType.OBJECT_DESTROYED: _handle_object_destroyed,
    EventType.MANA_PRODUCED: _handle_mana_produced,
    EventType.PLAYER_LOSES: _handle_player_loses,
    EventType.CREATE_TOKEN: _handle_create_token,
    EventType.EXILE: _handle_exile,
    EventType.EXILE_FROM_TOP: _handle_exile_from_top,
    EventType.EXILE_TOP: _handle_exile_from_top,
    EventType.EXILE_TOP_CARD: _handle_exile_from_top,
    EventType.EXILE_TOP_PLAY: _handle_exile_from_top,
    EventType.IMPULSE_DRAW: _handle_exile_from_top,
    EventType.IMPULSE_TO_GRAVEYARD: _handle_impulse_to_graveyard,
    EventType.SURVEIL: _handle_surveil,
    EventType.SCRY: _handle_scry,
    EventType.MILL: _handle_mill,
    EventType.DISCARD: _handle_discard,
    EventType.TARGET_REQUIRED: _handle_target_required,
}
