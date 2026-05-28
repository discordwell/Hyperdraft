"""
Yu-Gi-Oh! Effect Helper Factories

Reusable helpers for creating card effects, following the interceptor_helpers.py pattern.
"""

from .types import (
    GameState, GameObject, Event, EventType, ZoneType, CardType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    new_id
)


# =============================================================================
# YGO ATK / DEF effective-value queries
# =============================================================================
#
# YGO monsters store printed ATK/DEF on ``card_def.atk`` and ``card_def.def_val``,
# not on ``characteristics.power``/``characteristics.toughness`` (which the MTG
# pipeline uses). Lord effects (Six Samurai, Konda's Banner-Bearer, Bushido,
# etc.) register ``QUERY_POWER`` / ``QUERY_TOUGHNESS`` TRANSFORM interceptors,
# so we need a YGO-aware getter that:
#
# 1. Starts from the printed ``atk`` / ``def_val`` (not ``characteristics.power``,
#    which is ``None`` for YGO monsters).
# 2. Applies any per-target ``atk_bonus_eot`` / ``def_bonus_eot`` /
#    ``path_bravery_bonus`` markers cards write directly on ``obj.state``.
# 3. Runs all priority=QUERY interceptors that pass the filter for this object,
#    in timestamp order, so lord static effects (which mutate
#    ``event.payload['value']``) compose.
#
# Combat and the turn manager both call these helpers so lord ATK swings,
# Bushido pumps, equip bonuses, and trap drains all stack the same way.

def get_ygo_atk(obj: GameObject, state: GameState,
                *, battle_opponent_id: str | None = None) -> int:
    """Effective ATK for a YGO monster, with all continuous effects applied.

    ``battle_opponent_id`` (optional): if supplied, threaded into the
    QUERY_POWER event payload so battle-conditional pumps (e.g. Mothrider
    Samurai: "+1500 ATK during damage step if opponent is Lv 5+") can fire.
    """
    if obj is None or obj.card_def is None:
        return 0
    value = getattr(obj.card_def, 'atk', 0) or 0
    return _resolve_ygo_query(obj, state, EventType.QUERY_POWER, value,
                              direct_keys=('atk_bonus_eot',
                                           'path_bravery_bonus'),
                              extra_payload={'battle_opponent_id':
                                             battle_opponent_id}
                              if battle_opponent_id else None)


def get_ygo_def(obj: GameObject, state: GameState) -> int:
    """Effective DEF for a YGO monster, with all continuous effects applied."""
    if obj is None or obj.card_def is None:
        return 0
    value = getattr(obj.card_def, 'def_val', 0) or 0
    return _resolve_ygo_query(obj, state, EventType.QUERY_TOUGHNESS, value,
                              direct_keys=('def_bonus_eot',))


def _resolve_ygo_query(obj: GameObject, state: GameState,
                       event_type: EventType, base_value: int,
                       *, direct_keys: tuple = (),
                       extra_payload: dict | None = None) -> int:
    """Walk all QUERY-priority interceptors for ``obj`` and apply them in
    timestamp order to ``base_value``.

    ``direct_keys`` are state-stored boost markers (e.g. ``atk_bonus_eot``)
    that some card scripts write to ``obj.state`` directly; we add them on top
    of the interceptor-applied value so cards that don't bother registering
    a transform still take effect.

    ``extra_payload`` is merged into the QUERY event payload so callers can
    expose battle context (battle_opponent_id, etc.) to TRANSFORM handlers.
    """
    # Sort registered interceptors by timestamp so QUERY layer composes
    # deterministically.
    interceptors = sorted(
        [i for i in state.interceptors.values()
         if i.priority == InterceptorPriority.QUERY],
        key=lambda i: i.timestamp,
    )
    value = base_value
    for inter in interceptors:
        payload = {'object_id': obj.id, 'value': value}
        if extra_payload:
            payload.update(extra_payload)
        ev = Event(type=event_type, payload=payload)
        try:
            if not inter.filter(ev, state):
                continue
        except Exception:
            continue
        try:
            result = inter.handler(ev, state)
        except Exception:
            continue
        if result and result.transformed_event:
            value = result.transformed_event.payload.get('value', value)
    # State-stored markers (atk_bonus_eot etc.) — these are written by cards
    # whose effect resolves with a direct mutation rather than an interceptor.
    for key in direct_keys:
        value += int(getattr(obj.state, key, 0) or 0)
    return value


# =============================================================================
# Trigger Helpers
# =============================================================================

def make_ygo_summon_trigger(obj: GameObject, effect_fn):
    """Create a trigger that fires when this monster is summoned."""
    def _filter(event: Event, state: GameState) -> bool:
        return (event.type in (EventType.YGO_NORMAL_SUMMON, EventType.YGO_SPECIAL_SUMMON,
                               EventType.YGO_FLIP_SUMMON, EventType.YGO_TRIBUTE_SUMMON) and
                event.payload.get('card_id') == obj.id)

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        events = effect_fn(obj, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events or [])

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=_filter, handler=_handler,
        duration='until_leaves',
    )


def make_ygo_destroy_trigger(obj: GameObject, effect_fn):
    """Create a trigger that fires when this card is destroyed.

    Listens for both the legacy ``YGO_DESTROY`` notification (single ``card_id``
    payload, emitted by cards that perform their own zone manipulation) and the
    new ``YGO_DESTROYED`` notification fanned out by the pipeline handler.
    """
    def _filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.YGO_DESTROY, EventType.YGO_DESTROYED):
            return False
        # YGO_DESTROY effect-family with target_ids — match if this obj is a target.
        target_ids = event.payload.get('target_ids')
        if target_ids:
            return obj.id in target_ids
        return event.payload.get('card_id') == obj.id

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        events = effect_fn(obj, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events or [])

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=_filter, handler=_handler,
        duration='forever', uses_remaining=1,
    )


def make_ygo_send_to_gy_trigger(obj: GameObject, effect_fn):
    """Create a trigger that fires when this card is sent to the Graveyard
    for any reason (tribute, discard, destruction, cost).

    Listens for ``YGO_SENT_TO_GY`` (new pipeline notification). Also fires on
    ``YGO_SEND_TO_GY`` for backward compatibility with any test or card that
    pre-empts the pipeline by emitting the action event directly.
    """
    def _filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.YGO_SEND_TO_GY, EventType.YGO_SENT_TO_GY):
            return False
        return event.payload.get('card_id') == obj.id

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        events = effect_fn(obj, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events or [])

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=_filter, handler=_handler,
        duration='forever', uses_remaining=1,
    )


def make_ygo_flip_trigger(obj: GameObject, effect_fn):
    """Create a FLIP: effect trigger."""
    def _filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.YGO_FLIP and
                event.payload.get('card_id') == obj.id)

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        events = effect_fn(obj, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events or [])

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=_filter, handler=_handler,
        duration='until_leaves',
    )


def make_ygo_ignition_effect(obj: GameObject, effect_fn):
    """Create an Ignition Effect (SS1, activated during Main Phase).

    Listens for ``EventType.YGO_ACTIVATE_MONSTER_EFFECT`` — the dedicated
    YGO activation surface emitted by ``YugiohTurnManager._do_activate_monster_effect``.
    The legacy ``EventType.ACTIVATE`` filter (an MTG-only emission) is also
    accepted for backwards compatibility, but the YGO turn manager no longer
    emits it.
    """
    def _filter(event: Event, state: GameState) -> bool:
        if event.type == EventType.YGO_ACTIVATE_MONSTER_EFFECT:
            return event.payload.get('monster_id') == obj.id
        # Legacy path — kept for any callers still emitting ACTIVATE.
        if event.type == EventType.ACTIVATE:
            return event.payload.get('card_id') == obj.id
        return False

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        events = effect_fn(obj, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events or [])

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=_filter, handler=_handler,
        duration='until_leaves',
    )


def make_ygo_quick_effect(obj: GameObject, effect_fn):
    """Create a Quick Effect (SS2, can be activated during either turn).

    Wraps ``make_ygo_ignition_effect`` — the activation surface is the same;
    spell-speed differs only in chain resolution rules.
    """
    return make_ygo_ignition_effect(obj, effect_fn)


def make_ygo_continuous_effect(obj: GameObject, modifier_fn):
    """Create a continuous effect that modifies game state while on the field."""
    def _filter(event: Event, state: GameState) -> bool:
        # Apply to relevant query events
        return event.type in (EventType.QUERY_POWER, EventType.QUERY_TOUGHNESS,
                              EventType.QUERY_ABILITIES)

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        # Check if this monster is still on the field
        source = state.objects.get(obj.id)
        if not source or source.zone != ZoneType.MONSTER_ZONE:
            return InterceptorResult(action=InterceptorAction.PASS)
        return modifier_fn(event, state)

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.QUERY, filter=_filter, handler=_handler,
        duration='until_leaves',
    )


def make_ygo_equip_boost(obj: GameObject, atk_boost: int = 0, def_boost: int = 0):
    """Create an equip effect that boosts ATK/DEF of the equipped monster."""
    def _filter(event: Event, state: GameState) -> bool:
        target_id = getattr(obj.state, 'equipped_to', None)
        if not target_id:
            return False
        return (event.type in (EventType.QUERY_POWER, EventType.QUERY_TOUGHNESS) and
                event.payload.get('object_id') == target_id)

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        if event.type == EventType.QUERY_POWER and atk_boost:
            event.payload['value'] = event.payload.get('value', 0) + atk_boost
        elif event.type == EventType.QUERY_TOUGHNESS and def_boost:
            event.payload['value'] = event.payload.get('value', 0) + def_boost
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=event)

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.QUERY, filter=_filter, handler=_handler,
        duration='until_leaves',
    )


# =============================================================================
# Common Effect Implementations
# =============================================================================

def destroy_all_monsters(state: GameState) -> list[Event]:
    """Destroy all monsters on the field (Dark Hole effect)."""
    events = []
    for pid in state.players:
        zone_key = f"monster_zone_{pid}"
        zone = state.zones.get(zone_key)
        if not zone:
            continue
        for i, obj_id in enumerate(zone.objects):
            if obj_id is None:
                continue
            obj = state.objects.get(obj_id)
            if obj:
                # Send to GY
                zone.objects[i] = None
                gy = state.zones.get(f"graveyard_{obj.owner}")
                if gy:
                    gy.objects.append(obj_id)
                obj.zone = ZoneType.GRAVEYARD
                obj.state.face_down = False
                obj.state.ygo_position = None
                events.append(Event(
                    type=EventType.YGO_DESTROY,
                    payload={'card_id': obj_id, 'card_name': obj.name}
                ))
        # Clean up None entries
        while None in zone.objects:
            zone.objects.remove(None)
    return events


def destroy_attacking_monsters(state: GameState, controller_id: str) -> list[Event]:
    """Destroy all attack-position monsters the opponent controls (Mirror Force)."""
    events = []
    for pid in state.players:
        if pid == controller_id:
            continue
        zone_key = f"monster_zone_{pid}"
        zone = state.zones.get(zone_key)
        if not zone:
            continue
        for i, obj_id in enumerate(zone.objects):
            if obj_id is None:
                continue
            obj = state.objects.get(obj_id)
            if obj and getattr(obj.state, 'ygo_position', None) == 'face_up_atk':
                zone.objects[i] = None
                gy = state.zones.get(f"graveyard_{obj.owner}")
                if gy:
                    gy.objects.append(obj_id)
                obj.zone = ZoneType.GRAVEYARD
                obj.state.face_down = False
                obj.state.ygo_position = None
                events.append(Event(
                    type=EventType.YGO_DESTROY,
                    payload={'card_id': obj_id, 'card_name': obj.name}
                ))
        while None in zone.objects:
            zone.objects.remove(None)
    return events


def _reregister_setup_interceptors(state: GameState, obj: GameObject) -> None:
    """Re-run setup_interceptors for a revived/special-summoned monster.

    On-field triggers like ``make_ygo_summon_trigger`` register with
    ``duration='until_leaves'`` and get cleaned up by the pipeline when the
    object leaves the field. Re-running setup_interceptors at SS time re-arms
    them so revived monsters can fire their on-summon effects.

    Idempotent: clears any stale interceptor_ids still bound to ``obj`` before
    re-registering (rare, but safe).
    """
    if not obj.card_def or not obj.card_def.setup_interceptors:
        return

    # Purge stale interceptor ids — anything still bound to this obj from a
    # previous on-field stint must be cleared so we don't double-register.
    for int_id in list(obj.interceptor_ids):
        if int_id in state.interceptors:
            del state.interceptors[int_id]
    obj.interceptor_ids = []

    interceptors = obj.card_def.setup_interceptors(obj, state) or []
    for interceptor in interceptors:
        ts = getattr(state, 'next_timestamp', None)
        if callable(ts):
            interceptor.timestamp = state.next_timestamp()
        state.interceptors[interceptor.id] = interceptor
        obj.interceptor_ids.append(interceptor.id)


def revive_from_graveyard(state: GameState, player_id: str, card_id: str) -> list[Event]:
    """Special Summon a monster from the GY (Monster Reborn effect).

    Re-arms ``setup_interceptors`` on the revived object so on-summon
    triggers (``make_ygo_summon_trigger``) registered via the helper fire
    against the emitted ``YGO_SPECIAL_SUMMON`` event. Previously this helper
    only mutated zones — revived monsters never re-registered their triggers
    because ``until_leaves`` interceptors had been cleaned up when the card
    first hit the GY.
    """
    events = []
    obj = state.objects.get(card_id)
    if not obj:
        return events

    # Remove from GY
    gy_key = f"graveyard_{obj.owner}"
    gy = state.zones.get(gy_key)
    if gy and card_id in gy.objects:
        gy.objects.remove(card_id)

    # Find empty monster slot
    zone_key = f"monster_zone_{player_id}"
    zone = state.zones.get(zone_key)
    if not zone:
        return events
    slot = None
    for i in range(5):
        if i >= len(zone.objects) or zone.objects[i] is None:
            slot = i
            break
    if slot is None and len(zone.objects) < 5:
        slot = len(zone.objects)
    if slot is None:
        return events

    while len(zone.objects) <= slot:
        zone.objects.append(None)
    zone.objects[slot] = card_id
    obj.zone = ZoneType.MONSTER_ZONE
    obj.controller = player_id
    obj.state.ygo_position = 'face_up_atk'
    obj.state.face_down = False

    # Re-arm interceptors so the revived monster's on-summon trigger fires
    # against the YGO_SPECIAL_SUMMON event below.
    _reregister_setup_interceptors(state, obj)

    events.append(Event(
        type=EventType.YGO_SPECIAL_SUMMON,
        payload={'player': player_id, 'card_id': card_id, 'card_name': obj.name,
                 'summon_type': 'revive'}
    ))
    return events


def make_ygo_standby_trigger(obj: GameObject, effect_fn, *, controllers_only: bool = True):
    """Trigger that fires once per (player) Standby Phase while ``obj`` is on
    the field. Used by Continuous Spells like Wave-Motion Cannon and persistent
    effects like Lava Golem, Snatch Steal, Messenger of Peace.

    ``effect_fn(obj, state) -> list[Event]`` is called every time the
    controller's Standby Phase is entered. If ``controllers_only=False`` it
    fires on EITHER player's standby (used for Wave-Motion accumulator).
    """
    from .types import ZoneType

    def _filter(event: Event, state: GameState) -> bool:
        if obj.zone not in (ZoneType.MONSTER_ZONE, ZoneType.SPELL_TRAP_ZONE,
                            ZoneType.FIELD_SPELL_ZONE):
            return False
        if event.type != EventType.PHASE_CHANGE:
            return False
        if event.payload.get('phase') != 'standby':
            return False
        if controllers_only and event.payload.get('player') != obj.controller:
            return False
        last_turn = getattr(obj.state, '_standby_trigger_turn', None)
        return last_turn != state.turn_number

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        obj.state._standby_trigger_turn = state.turn_number
        events = effect_fn(obj, state) or []
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=_filter, handler=_handler,
        duration='until_leaves',
    )


def make_ygo_battle_damage_trigger(obj: GameObject, effect_fn):
    """Trigger that fires when this monster inflicts battle damage.

    Filters on ``EventType.YGO_BATTLE_DAMAGE`` where the payload's ``source``
    (the attacker) equals this object's id. Used by cards like Airknight
    Parshath (draw on battle damage) and Spirit Reaper (force discard).
    """
    def _filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.YGO_BATTLE_DAMAGE:
            return False
        # The attacker may be in payload['attacker_id'] or payload['source'].
        attacker = (event.payload.get('attacker_id')
                    or event.payload.get('source')
                    or event.source)
        return attacker == obj.id

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        events = effect_fn(obj, event, state) or []
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=_filter, handler=_handler,
        duration='until_leaves',
    )


def emit_lp_change(player_id: str, amount: int, source: str = "") -> list[Event]:
    """Build a declarative YGO_LP_CHANGE event for the pipeline to apply.

    Use this for cards that want the engine to handle the LP mutation +
    loss-condition check (rather than mutating ``player.lp`` inline). The
    handler (``pipeline.handlers.damage._handle_ygo_lp_change``) does:

    1. Clamps the new LP at 0 (cannot go negative).
    2. Emits ``YGO_LP_CHANGED`` (so downstream interceptors can trigger on
       the change — e.g. cards that say "when you gain LP" / "when you take
       damage").
    3. Sets ``has_lost = True`` and emits ``YGO_GAME_OVER`` if LP hit 0.

    Positive ``amount`` = lifegain; negative ``amount`` = burn / payment.

    NOTE: this is the modern, declarative path. The older pattern (mutate
    ``player.lp`` inline, then emit YGO_LP_CHANGE as a notification) is still
    supported by the same handler (omit ``_engine_apply``) — but new code
    should prefer this helper.
    """
    return [Event(
        type=EventType.YGO_LP_CHANGE,
        payload={'player': player_id, 'amount': amount,
                 'source': source, '_engine_apply': True},
    )]


def destroy_spell_trap(state: GameState, card_id: str) -> list[Event]:
    """Destroy a Spell/Trap card (MST effect)."""
    events = []
    obj = state.objects.get(card_id)
    if not obj:
        return events

    for zone in state.zones.values():
        if card_id in zone.objects:
            for i, oid in enumerate(zone.objects):
                if oid == card_id:
                    zone.objects[i] = None
                    break
            while card_id in zone.objects:
                zone.objects.remove(card_id)
            break

    gy = state.zones.get(f"graveyard_{obj.owner}")
    if gy:
        gy.objects.append(card_id)
    obj.zone = ZoneType.GRAVEYARD
    obj.state.face_down = False

    events.append(Event(
        type=EventType.YGO_DESTROY,
        payload={'card_id': card_id, 'card_name': obj.name}
    ))
    return events


# =============================================================================
# Draw / Search / Hand Recovery — centralized helpers
# =============================================================================
#
# Yu-Gi-Oh "draw N", "search for a card with X subtype/name", and "add from GY
# to hand" are the most common card effects. Each of these helpers does the
# zone-move atomically and emits a ``YGO_DRAW`` event so generic draw-reactive
# triggers (e.g. Howling Mine reactions, archetype lord effects) still fire.
#
# Search effects ALSO emit a ``YGO_SEARCH_DECK`` event before the ``YGO_DRAW``
# so cards that specifically react to deck-search (e.g. "Maxx C", anti-search
# tech) can fire.

def draw_cards(state: GameState, player_id: str, count: int = 1) -> list[Event]:
    """Move N cards from the top of ``player_id``'s deck to their hand.

    Emits one ``YGO_DRAW`` event per card with ``source='draw'``. Caps at deck
    size; emits nothing for empty deck (deck-out handled by turn manager).

    Returns the list of emitted events.
    """
    library = state.zones.get(f"library_{player_id}")
    hand = state.zones.get(f"hand_{player_id}")
    if not library or not hand:
        return []
    events: list[Event] = []
    for _ in range(count):
        if not library.objects:
            break
        card_id = library.objects.pop(0)
        hand.objects.append(card_id)
        obj = state.objects.get(card_id)
        if obj is not None:
            obj.zone = ZoneType.HAND
        events.append(Event(
            type=EventType.YGO_DRAW,
            payload={'player': player_id, 'card_id': card_id,
                     'count': 1, 'source': 'draw'},
        ))
    return events


def search_deck(state: GameState, player_id: str, predicate,
                *, filter_desc: str | None = None,
                destination: str = 'hand') -> list[Event]:
    """Search ``player_id``'s deck for the first card matching ``predicate``.

    ``predicate(GameObject) -> bool`` is evaluated on each card in the library
    until one matches; that card is moved to the destination zone (default:
    hand). Library order is preserved (we remove the matched card in place).

    Emits two events on success:
      1. ``YGO_SEARCH_DECK`` — for anti-search tech.
      2. ``YGO_DRAW`` with ``source='search'`` — for generic draw-reactive
         triggers.

    Emits nothing on miss. Caller is responsible for shuffling the deck
    afterwards (per YGO rules, but most modern decks don't shuffle on a
    failed search — we don't auto-shuffle to keep state deterministic).
    """
    library = state.zones.get(f"library_{player_id}")
    hand = state.zones.get(f"hand_{player_id}")
    if not library or not hand:
        return []

    matched_id: str | None = None
    for cid in list(library.objects):
        obj = state.objects.get(cid)
        if obj is None or obj.card_def is None:
            continue
        try:
            if predicate(obj):
                matched_id = cid
                break
        except Exception:
            continue

    if matched_id is None:
        return []

    library.objects.remove(matched_id)
    obj = state.objects.get(matched_id)
    if destination == 'hand':
        hand.objects.append(matched_id)
        if obj is not None:
            obj.zone = ZoneType.HAND
    elif destination == 'field':
        # Caller must position the card; we still emit the search event so
        # the caller can chain it. (Modern engines special-summon directly,
        # so leave that to the calling card.)
        pass

    events: list[Event] = [Event(
        type=EventType.YGO_SEARCH_DECK,
        payload={'player': player_id, 'card_id': matched_id,
                 'card_name': obj.name if obj else '',
                 'filter_desc': filter_desc or '',
                 'destination': destination},
    )]
    events.append(Event(
        type=EventType.YGO_DRAW,
        payload={'player': player_id, 'card_id': matched_id,
                 'card_name': obj.name if obj else '',
                 'count': 1, 'source': 'search'},
    ))
    return events


def add_from_gy_to_hand(state: GameState, player_id: str,
                        card_id: str) -> list[Event]:
    """Move a specific card from ``player_id``'s GY (or anywhere else) to hand.

    Emits a single ``YGO_DRAW`` event with ``source='recovery'``. Returns
    empty list if the card isn't found.
    """
    obj = state.objects.get(card_id)
    if obj is None:
        return []
    moved = False
    for z in state.zones.values():
        if card_id in z.objects:
            for i, oid in enumerate(z.objects):
                if oid == card_id:
                    z.objects[i] = None
                    moved = True
                    break
            while card_id in z.objects:
                z.objects.remove(card_id)
    hand = state.zones.get(f"hand_{player_id}")
    if hand is None:
        return []
    hand.objects.append(card_id)
    obj.zone = ZoneType.HAND
    obj.state.face_down = False
    obj.state.ygo_position = None
    if not moved:
        return []
    return [Event(
        type=EventType.YGO_DRAW,
        payload={'player': player_id, 'card_id': card_id,
                 'card_name': obj.name, 'count': 1, 'source': 'recovery'},
    )]


def search_deck_by_subtype(state: GameState, player_id: str,
                           subtype: str,
                           *, max_level: int | None = None,
                           exclude_id: str | None = None) -> list[Event]:
    """Convenience: search deck for a monster with the given subtype.

    Optional level cap (e.g. "Level 4 or lower Moonfolk"). Excludes a given
    card_id from matches (so a searcher doesn't find a copy of itself if the
    deck contains one).
    """
    def _pred(card_obj: GameObject) -> bool:
        if exclude_id is not None and card_obj.id == exclude_id:
            return False
        cd = card_obj.card_def
        if cd is None:
            return False
        subtypes = cd.characteristics.subtypes or set()
        if subtype not in subtypes:
            return False
        if max_level is not None:
            level = getattr(cd, 'level', None) or 99
            if level > max_level:
                return False
        return True

    desc = f"{subtype}" + (f" (Level <={max_level})" if max_level else "")
    return search_deck(state, player_id, _pred, filter_desc=desc)


def search_deck_by_name(state: GameState, player_id: str,
                        card_name: str) -> list[Event]:
    """Convenience: search deck for a card with exact name match."""
    def _pred(card_obj: GameObject) -> bool:
        return (card_obj.card_def is not None and
                card_obj.card_def.name == card_name)
    return search_deck(state, player_id, _pred, filter_desc=f"name='{card_name}'")
