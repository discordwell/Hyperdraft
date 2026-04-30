"""
Zone-movement handlers: ZONE_CHANGE, OBJECT_CREATED, OBJECT_DESTROYED,
SACRIFICE, EXILE, CREATE_TOKEN, TAP/UNTAP, RETURN_TO_HAND/BOUNCE.
"""

from typing import Optional

from ...types import (
    Event, EventType, GameState, ZoneType, CardType, Color,
)
from .._shared import (
    _remove_object_from_all_zones,
    _exile_instead_of_graveyard_active,
    _KEYWORD_COUNTER_TYPES,
    _sync_keyword_counter_abilities,
)


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
    from ...types import new_id, GameObject, Characteristics, ObjectState

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
    enters_face_down = bool(event.payload.get('face_down', False))

    obj_id = new_id()
    obj_state = ObjectState(
        is_token=is_token,
        tapped=enters_tapped,
        face_down=enters_face_down,
        summoning_sickness=(zone_type == ZoneType.BATTLEFIELD)
    )

    # Apply keyword states from abilities (mirror make_minion behavior)
    obj_keywords = {
        a.get('keyword', '').lower()
        for a in characteristics.abilities
        if isinstance(a, dict) and a.get('keyword')
    }
    if 'divine_shield' in obj_keywords:
        obj_state.divine_shield = True
    if 'stealth' in obj_keywords:
        obj_state.stealth = True
    if 'windfury' in obj_keywords:
        obj_state.windfury = True
    if 'frozen' in obj_keywords:
        obj_state.frozen = True
    if 'charge' in obj_keywords:
        obj_state.summoning_sickness = False

    created = GameObject(
        id=obj_id,
        name=event.payload.get('name', 'Token'),
        owner=owner_id,
        controller=controller_id,
        zone=zone_type,
        characteristics=characteristics,
        state=obj_state,
        card_def=event.payload.get('card_def'),
        created_at=state.next_timestamp(),
        entered_zone_at=state.timestamp,
        _state_ref=state,
    )

    state.objects[obj_id] = created

    # If the object enters face-down (Manifest / Manifest Dread / Cloak /
    # Disguise / Morph), wire the masking QUERY interceptors *now* so observers
    # see a vanilla 2/2 even on the same tick. We import lazily to avoid the
    # interceptor-helpers -> pipeline.zone circular import.
    if enters_face_down and zone_type == ZoneType.BATTLEFIELD:
        try:
            from src.cards.interceptor_helpers import _face_down_query_interceptors
            face_down_interceptors = _face_down_query_interceptors(created)
            for interceptor in face_down_interceptors:
                interceptor.timestamp = state.next_timestamp()
                state.interceptors[interceptor.id] = interceptor
                created.interceptor_ids.append(interceptor.id)
        except Exception:
            # Don't break OBJECT_CREATED if helpers aren't loadable in this
            # context (e.g. early bootstrapping). Card-side scripts can still
            # call make_face_down_setup() directly.
            pass

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
        if zone_type in {ZoneType.LIBRARY, ZoneType.HAND, ZoneType.GRAVEYARD,
                         ZoneType.ACTIVE_SPOT, ZoneType.BENCH, ZoneType.PRIZE_CARDS}:
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

    # If a caller provided a zone key that doesn't exist (common in older/hand-written
    # card scripts), fall back to the canonical key derived from the zone type.
    if from_zone_type and (from_zone is None or from_zone not in state.zones):
        from_zone = _zone_key(from_zone_type, from_owner)
    if to_zone_type and (to_zone is None or to_zone not in state.zones):
        to_zone = _zone_key(to_zone_type, to_owner)

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

    # Replacement: per-object "exile if it would leave the battlefield" (Unearth, etc.).
    # This is distinct from the global "exile instead of graveyard" replacement.
    if from_zone_type == ZoneType.BATTLEFIELD:
        exile_on_leave = bool(getattr(getattr(obj, "state", None), "_exile_on_leave_battlefield", False))
        if exile_on_leave and to_zone_type is not None and to_zone_type != ZoneType.EXILE:
            to_zone_type = ZoneType.EXILE
            to_zone = "exile"
            event.payload["to_zone_type"] = ZoneType.EXILE
            event.payload["to_zone"] = "exile"
            event.payload["replacement"] = "exile_on_leave_battlefield"

    # Replacement: "exile instead of graveyard" (Rest in Peace, etc.).
    # We apply this as a last-mile destination rewrite for ZONE_CHANGE events
    # targeting a graveyard zone.
    if to_zone_type == ZoneType.GRAVEYARD:
        dest_owner = to_owner or obj.owner
        if dest_owner and _exile_instead_of_graveyard_active(dest_owner, state):
            to_zone_type = ZoneType.EXILE
            to_zone = "exile"
            event.payload["to_zone_type"] = ZoneType.EXILE
            event.payload["to_zone"] = "exile"
            event.payload["replacement"] = "exile_instead_of_graveyard"

    # Important: many call sites provide imperfect `from_zone` keys. Be robust
    # and remove the object from *any* zone that currently references it.
    _remove_object_from_all_zones(object_id, state)

    # Enforce mode's minion board cap (HS: 7). Adapter returns None = uncapped.
    from ...mode_adapter import get_mode_adapter
    _mode_adapter = get_mode_adapter(state.game_mode)
    if (to_zone_type == ZoneType.BATTLEFIELD and
            CardType.MINION in obj.characteristics.types):
        minion_cap = _mode_adapter.max_minions_on_board(obj.controller, state)
        if minion_cap is not None:
            battlefield = state.zones.get('battlefield')
            if battlefield:
                minion_count = sum(
                    1 for oid in battlefield.objects
                    if oid in state.objects
                    and state.objects[oid].controller == obj.controller
                    and CardType.MINION in state.objects[oid].characteristics.types
                )
                if minion_count >= minion_cap:
                    # Board full - send to graveyard instead
                    dest_key = f"graveyard_{obj.owner}"
                    if dest_key in state.zones:
                        state.zones[dest_key].objects.append(object_id)
                    obj.zone = ZoneType.GRAVEYARD
                    obj.entered_zone_at = state.timestamp
                    return

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
        # Reset summoning sickness (new objects can't attack the turn they enter)
        obj.state.summoning_sickness = True

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

    # Reset minion state when leaving battlefield (HS bounce/return to hand).
    # MTG: no-op — returning cards become new instances anyway.
    _mode_adapter.on_leave_battlefield_to_hidden(obj, from_zone_type, to_zone_type, state)

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
    exile_on_leave = bool(getattr(getattr(obj, "state", None), "_exile_on_leave_battlefield", False))

    # Remove from any zone that currently references it (robust).
    _remove_object_from_all_zones(object_id, state)

    # Add to owner's graveyard (or exile, if a replacement effect applies).
    if exile_on_leave or _exile_instead_of_graveyard_active(owner_id, state):
        dest_key = "exile"
        dest_type = ZoneType.EXILE
    else:
        dest_key = f"graveyard_{owner_id}"
        dest_type = ZoneType.GRAVEYARD

    if dest_key in state.zones:
        state.zones[dest_key].objects.append(object_id)

    obj.zone = dest_type
    obj.entered_zone_at = state.timestamp

    # Mode-specific weapon cleanup (HS clears player.weapon_*). Default no-op.
    from ...mode_adapter import get_mode_adapter
    get_mode_adapter(state.game_mode).on_weapon_destroyed(obj, event, state)

    # NOTE: Interceptor cleanup moved to _cleanup_departed_interceptors()
    # which runs AFTER the REACT phase, allowing death triggers to fire


def _handle_sacrifice(event: Event, state: GameState):
    """
    Handle SACRIFICE.

    Moves the sacrificed permanent from the battlefield to its owner's graveyard.

    Payload:
        object_id: str - permanent being sacrificed
        player: str (optional) - who is sacrificing (defaults to controller)
    """
    object_id = event.payload.get('object_id')
    if not object_id or object_id not in state.objects:
        return

    obj = state.objects[object_id]
    exile_on_leave = bool(getattr(getattr(obj, "state", None), "_exile_on_leave_battlefield", False))

    # Sacrifices only apply to permanents on the battlefield.
    if obj.zone != ZoneType.BATTLEFIELD:
        return

    player_id = event.payload.get('player') or event.controller
    if player_id and obj.controller != player_id:
        # Can't sacrifice a permanent you don't control.
        return

    owner_id = obj.owner

    # Remove from any zone that currently references it (robust).
    _remove_object_from_all_zones(object_id, state)

    # Add to owner's graveyard (or exile, if a replacement effect applies).
    if exile_on_leave or _exile_instead_of_graveyard_active(owner_id, state):
        dest_key = "exile"
        dest_type = ZoneType.EXILE
    else:
        dest_key = f"graveyard_{owner_id}"
        dest_type = ZoneType.GRAVEYARD

    if dest_key in state.zones:
        state.zones[dest_key].objects.append(object_id)

    obj.zone = dest_type
    obj.entered_zone_at = state.timestamp


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
    from ...types import new_id, GameObject, Characteristics, ObjectState

    controller_id = event.payload.get('controller')
    token_data = event.payload.get('token', {})
    count = event.payload.get('count', 1)
    enters_tapped = event.payload.get('tapped', False)

    if not controller_id or controller_id not in state.players:
        return

    created_ids: list[str] = []

    from ...mode_adapter import get_mode_adapter
    _mode_adapter = get_mode_adapter(state.game_mode)

    for _ in range(count):
        # Enforce mode's minion board cap (HS: 7; MTG: uncapped).
        minion_cap = _mode_adapter.max_minions_on_board(controller_id, state)
        if minion_cap is not None:
            battlefield = state.zones.get('battlefield')
            if battlefield:
                minion_count = sum(
                    1 for oid in battlefield.objects
                    if oid in state.objects
                    and state.objects[oid].controller == controller_id
                    and CardType.MINION in state.objects[oid].characteristics.types
                )
                if minion_count >= minion_cap:
                    break  # Board full, can't create more tokens

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
        token_state = ObjectState(
            is_token=True,
            tapped=enters_tapped,
            summoning_sickness=True  # Tokens can't attack the turn they're created
        )

        # Apply keyword states from abilities (mirror make_minion behavior)
        token_keywords = {
            a.get('keyword', '').lower()
            for a in characteristics.abilities
            if isinstance(a, dict) and a.get('keyword')
        }
        if 'divine_shield' in token_keywords:
            token_state.divine_shield = True
        if 'stealth' in token_keywords:
            token_state.stealth = True
        if 'windfury' in token_keywords:
            token_state.windfury = True
        if 'frozen' in token_keywords:
            token_state.frozen = True
        if 'charge' in token_keywords:
            token_state.summoning_sickness = False

        token = GameObject(
            id=obj_id,
            name=token_data.get('name', 'Token'),
            owner=controller_id,
            controller=controller_id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=characteristics,
            state=token_state,
            created_at=state.next_timestamp(),
            entered_zone_at=state.timestamp,
            _state_ref=state,
        )

        # Add to state
        state.objects[obj_id] = token
        created_ids.append(obj_id)

        # Add to battlefield zone
        battlefield_key = 'battlefield'
        if battlefield_key in state.zones:
            state.zones[battlefield_key].objects.append(obj_id)

        # Run setup_interceptors if provided in token payload
        setup_fn = token_data.get('setup_interceptors')
        if setup_fn:
            interceptors = setup_fn(token, state)
            for interceptor in (interceptors or []):
                interceptor.timestamp = state.next_timestamp()
                state.interceptors[interceptor.id] = interceptor
                token.interceptor_ids.append(interceptor.id)

    # Make created token IDs available to REACT interceptors on this event.
    if created_ids:
        event.payload['object_ids'] = created_ids
        if len(created_ids) == 1:
            event.payload['object_id'] = created_ids[0]


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


def _handle_return_to_hand(event: Event, state: GameState):
    """
    Handle RETURN_TO_HAND / BOUNCE event.

    Moves an object from its current zone (usually battlefield) to its owner's hand.
    Payload:
        object_id: The ID of the object to return
    """
    obj_id = event.payload.get('object_id')
    if not obj_id or obj_id not in state.objects:
        return

    obj = state.objects[obj_id]
    from_zone_type = obj.zone or ZoneType.BATTLEFIELD

    # Delegate to the zone change handler
    zone_event = Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj_id,
            'from_zone_type': from_zone_type,
            'to_zone_type': ZoneType.HAND,
        },
        source=event.source
    )
    _handle_zone_change(zone_event, state)
