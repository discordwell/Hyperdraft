"""
Interceptor Helper Functions

Common patterns for creating interceptors across all card sets.
"""

from typing import Callable, Optional, Any
from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    PendingChoice,
    new_id
)


# =============================================================================
# Triggered-ability decoration (CR 603.2)
# =============================================================================

def _mark_triggered_ability(
    interceptor: Interceptor,
    effect_fn: Callable[[Event, GameState], list[Event]],
    description: str = "",
) -> Interceptor:
    """Tag a REACT-priority interceptor as a triggered ability.

    The pipeline reads ``is_triggered_ability`` and ``effect_fn`` directly
    when queueing the trigger onto ``state.pending_triggers``. The original
    ``handler`` is preserved for legacy/fallback paths (e.g. tests that
    flip is_triggered_ability=False to disable trigger queueing).
    """
    interceptor.is_triggered_ability = True
    interceptor.effect_fn = effect_fn
    if description and not interceptor.description:
        interceptor.description = description
    return interceptor


# =============================================================================
# FILTER FACTORY FUNCTIONS
# =============================================================================

def other_creatures_you_control(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter: Other creatures you control (excluding source)."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.id != source.id and
                target.controller == source.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def creatures_you_control(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter: All creatures you control (including source)."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.controller == source.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def creatures_with_subtype(source: GameObject, subtype: str) -> Callable[[GameObject, GameState], bool]:
    """Filter: Creatures you control with the given subtype."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.controller == source.controller and
                CardType.CREATURE in target.characteristics.types and
                subtype in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def other_creatures_with_subtype(source: GameObject, subtype: str) -> Callable[[GameObject, GameState], bool]:
    """Filter: Other creatures you control with the given subtype."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.id != source.id and
                target.controller == source.controller and
                CardType.CREATURE in target.characteristics.types and
                subtype in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def all_opponents(source: GameObject, state: GameState) -> list[str]:
    """Get list of opponent player IDs."""
    return [p_id for p_id in state.players.keys() if p_id != source.controller]


# =============================================================================
# ETB TRIGGER
# =============================================================================

def make_etb_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None
) -> Interceptor:
    """
    Create an ETB (enters-the-battlefield) trigger interceptor.

    Args:
        source_obj: The object with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        filter_fn: Optional custom filter (receives event, state, source_obj)

    Events matched (default filter):
        - ZONE_CHANGE with to_zone_type == BATTLEFIELD and object_id == source.id
        - OBJECT_CREATED with object_id == source.id and to_zone_type ==
          BATTLEFIELD. This covers copy-tokens, whose setup_interceptors are
          registered inside ``_handle_object_created`` before any ZONE_CHANGE
          is emitted, so we have to dispatch off OBJECT_CREATED itself.
    Priority: REACT
    """
    def default_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        if event.type == EventType.ZONE_CHANGE:
            return (event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD and
                    event.payload.get('object_id') == obj.id)
        if event.type == EventType.OBJECT_CREATED:
            return (event.payload.get('object_id') == obj.id and
                    event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD)
        return False

    actual_filter = filter_fn or default_filter

    def trigger_filter(event: Event, state: GameState) -> bool:
        return actual_filter(event, state, source_obj)

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="ETB trigger")


# =============================================================================
# DEATH TRIGGER
# =============================================================================

def make_death_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None
) -> Interceptor:
    """
    Create a death trigger interceptor (when this creature dies).

    Args:
        source_obj: The creature with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        filter_fn: Optional custom filter

    Event: OBJECT_DESTROYED with object_id == source_obj.id
    Priority: REACT

    Note: The trigger fires during the REACT phase, BEFORE interceptor cleanup.
    This allows the creature to "see" its own death and trigger effects.
    """
    def default_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        # Primary check: OBJECT_DESTROYED for this creature
        if event.type == EventType.OBJECT_DESTROYED:
            if event.payload.get('object_id') != obj.id:
                return False
            # "Dies" means the object actually went to a graveyard. Replacement
            # effects (Rest in Peace, Unearth, etc.) can change the destination.
            resolved = state.objects.get(obj.id)
            return bool(resolved and resolved.zone == ZoneType.GRAVEYARD)

        # Sacrifice is also a "dies" event when it moves from battlefield to graveyard.
        if event.type == EventType.SACRIFICE:
            if event.payload.get('object_id') != obj.id:
                return False
            resolved = state.objects.get(obj.id)
            return bool(resolved and resolved.zone == ZoneType.GRAVEYARD)

        # Fallback: ZONE_CHANGE from battlefield to graveyard (for exile->graveyard, etc.)
        if event.type == EventType.ZONE_CHANGE:
            return (event.payload.get('object_id') == obj.id and
                    event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD and
                    event.payload.get('to_zone_type') == ZoneType.GRAVEYARD)

        return False

    actual_filter = filter_fn or default_filter

    def trigger_filter(event: Event, state: GameState) -> bool:
        return actual_filter(event, state, source_obj)

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='until_leaves'  # Stays registered to fire after leaving
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Death trigger")


# =============================================================================
# COUNTER-TRANSFER-ON-DEATH (Reluctant Role Model template)
# =============================================================================

def make_counter_transfer_on_death(
    source_obj: GameObject,
    filter_fn: Optional[Callable[[GameObject, GameState], bool]] = None,
    *,
    prompt: str = "Choose a creature to receive the transferred counters",
    optional: bool = True,
) -> Interceptor:
    """
    Trigger that fires when a creature (matching ``filter_fn``) dies and had
    counters on it; emit a target choice for a recipient and transfer all
    counters that were on the dying creature to the chosen target.

    Default ``filter_fn`` is "this creature or another creature you control",
    matching cards like Reluctant Role Model whose own death also triggers.

    Args:
        source_obj: The card whose ability is doing the transfer.
        filter_fn: ``(dying_obj, state) -> bool``. Default: source itself OR
            any creature controlled by source.controller, on battlefield-leave.
        prompt: Choice prompt the player sees.
        optional: If True, recipient choice has min_choices=0 (player may decline).

    Behaviour:
        Listens on OBJECT_DESTROYED / ZONE_CHANGE (BF -> GY) / SACRIFICE
        for objects matching ``filter_fn`` that had at least one counter at
        time of death. On match, a PendingChoice of choice_type='target' is
        opened; when the player picks a recipient, COUNTER_ADDED events
        (and COUNTER_REMOVED events on the dying creature) are emitted to
        carry out the transfer.

    Returns:
        An Interceptor with duration='until_leaves' so a self-death also fires.
    """
    source_id = source_obj.id
    controller_id = source_obj.controller

    def default_filter(dying: GameObject, state: GameState) -> bool:
        # Self OR any creature controlled by source.controller. Source itself
        # may already be in graveyard at trigger time; resolve from state to
        # learn its (now-old) controller for the team check.
        if dying.id == source_id:
            return True
        if CardType.CREATURE not in dying.characteristics.types:
            return False
        return dying.controller == controller_id

    actual_filter = filter_fn or default_filter

    def _resolve_dying_id(event: Event) -> Optional[str]:
        if event.type == EventType.OBJECT_DESTROYED:
            return event.payload.get('object_id')
        if event.type == EventType.SACRIFICE:
            return event.payload.get('object_id')
        if event.type == EventType.ZONE_CHANGE:
            if (event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD and
                    event.payload.get('to_zone_type') == ZoneType.GRAVEYARD):
                return event.payload.get('object_id')
        return None

    def trigger_filter(event: Event, state: GameState) -> bool:
        # Source must still exist (and be on battlefield) for the trigger to
        # remain active. We allow self-death (source in graveyard) because the
        # interceptor is duration='until_leaves' — it gets one chance to fire
        # before the cleanup pass removes it.
        source = state.objects.get(source_id)
        if source is None:
            return False
        # If this is a non-self death, the source must still be on battlefield.
        dying_id = _resolve_dying_id(event)
        if dying_id is None:
            return False
        if dying_id != source_id and source.zone != ZoneType.BATTLEFIELD:
            return False
        dying = state.objects.get(dying_id)
        if dying is None:
            return False
        # Counters persist on obj.state.counters even after the move to GY.
        counters = getattr(dying.state, 'counters', None) or {}
        total = sum(int(v) for v in counters.values())
        if total <= 0:
            return False
        return actual_filter(dying, state)

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        dying_id = _resolve_dying_id(event)
        dying = state.objects.get(dying_id) if dying_id else None
        if dying is None:
            return InterceptorResult(action=InterceptorAction.PASS)

        # Snapshot counters BEFORE we open the choice (the chosen recipient
        # may not be picked until later, by which point a parallel effect
        # could have moved/removed the dying object). We freeze the data
        # into the choice's callback_data.
        counters_snapshot = dict(getattr(dying.state, 'counters', {}) or {})
        if not counters_snapshot:
            return InterceptorResult(action=InterceptorAction.PASS)

        # Legal targets: any creature on the battlefield that isn't the dying
        # one. (The card text says "up to one target creature" — opponent's
        # creatures are legal.)
        legal_targets = [
            oid for oid, ob in state.objects.items()
            if (ob.zone == ZoneType.BATTLEFIELD
                and CardType.CREATURE in ob.characteristics.types
                and oid != dying_id)
        ]

        def _on_chosen(choice: PendingChoice, selected: list, st: GameState) -> list[Event]:
            if not selected:
                return []
            target_id = selected[0]
            # Validate the target is still legal.
            target = st.objects.get(target_id)
            if (target is None or target.zone != ZoneType.BATTLEFIELD
                    or CardType.CREATURE not in target.characteristics.types):
                return []
            events: list[Event] = []
            for ctype, amount in counters_snapshot.items():
                if amount <= 0:
                    continue
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={
                        'object_id': target_id,
                        'counter_type': ctype,
                        'amount': int(amount),
                    },
                    source=source_id,
                    controller=controller_id,
                ))
                # Also clear the counters on the dying creature (it's now in GY,
                # but if it's returned to play later the counters shouldn't
                # double up). This mirrors actual MTG: counters move, they
                # don't duplicate.
                events.append(Event(
                    type=EventType.COUNTER_REMOVED,
                    payload={
                        'object_id': dying_id,
                        'counter_type': ctype,
                        'amount': int(amount),
                    },
                    source=source_id,
                    controller=controller_id,
                ))
            return events

        # If there are no legal targets, the trigger still fires (per MTG
        # rules a "may" target with no legal targets is a no-op), but we
        # don't open a choice.
        if not legal_targets:
            return InterceptorResult(action=InterceptorAction.PASS)

        choice = PendingChoice(
            choice_type="target",
            player=controller_id,
            prompt=prompt,
            options=legal_targets,
            source_id=source_id,
            min_choices=0 if optional else 1,
            max_choices=1,
            callback_data={
                'handler': _on_chosen,
                'counters_snapshot': counters_snapshot,
                'dying_id': dying_id,
            },
        )
        state.pending_choice = choice
        return InterceptorResult(action=InterceptorAction.PASS)

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='until_leaves',
    )


# =============================================================================
# ATTACK TRIGGER
# =============================================================================

def make_attack_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None
) -> Interceptor:
    """
    Create an attack trigger interceptor (whenever this creature attacks).

    Args:
        source_obj: The creature with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        filter_fn: Optional custom filter

    Event: ATTACK_DECLARED with attacker_id == source_obj.id
    Priority: REACT
    """
    def default_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        return (event.type == EventType.ATTACK_DECLARED and
                event.payload.get('attacker_id') == obj.id)

    actual_filter = filter_fn or default_filter

    def trigger_filter(event: Event, state: GameState) -> bool:
        return actual_filter(event, state, source_obj)

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Attack trigger")


# =============================================================================
# BLB KEYWORDS (Valiant, Expend) — re-exported from src/engine/blb_keywords.py
# =============================================================================
#
# These two helpers cover the Bloomburrow keyword frameworks for Valiant and
# Expend. They live in src/engine/blb_keywords.py (so the engine layer owns
# the event-filter logic and can be imported by tests/server code without
# pulling card definitions). We surface them here so card-side code keeps
# the same import sugar as the rest of the trigger helpers.
#
# Quick reference (full docs on the originals):
# * make_valiant_trigger(obj, effect_fn) — REACTs to EventType.TARGET_CHOSEN
#   when the targeted permanent is `obj` and the source spell/ability is
#   controlled by `obj.controller`. Fires at most once per `obj` per turn.
# * make_expend_trigger(obj, n, effect_fn) — REACTs to EventType.EXPEND_4_REACHED
#   or EXPEND_8_REACHED for `obj.controller`. `n` must be 4 or 8.
from src.engine.blb_keywords import (
    make_valiant_trigger,
    make_expend_trigger,
)


# =============================================================================
# BLOCK TRIGGER
# =============================================================================

def make_block_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None
) -> Interceptor:
    """
    Create a block trigger interceptor (whenever this creature blocks).

    Args:
        source_obj: The creature with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        filter_fn: Optional custom filter

    Event: BLOCK_DECLARED with blocker_id == source_obj.id
    Priority: REACT
    """
    def default_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        return (event.type == EventType.BLOCK_DECLARED and
                event.payload.get('blocker_id') == obj.id)

    actual_filter = filter_fn or default_filter

    def trigger_filter(event: Event, state: GameState) -> bool:
        return actual_filter(event, state, source_obj)

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Block trigger")


# =============================================================================
# DAMAGE TRIGGER
# =============================================================================

def make_damage_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    combat_only: bool = False,
    noncombat_only: bool = False,
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None
) -> Interceptor:
    """
    Create a damage trigger interceptor (whenever this creature deals damage).

    Args:
        source_obj: The creature with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        combat_only: If True, only trigger on combat damage
        noncombat_only: If True, only trigger on noncombat damage
        filter_fn: Optional custom filter for additional conditions

    Event: DAMAGE with source == source_obj.id
    Payload: {'target': str, 'amount': int, 'source': str, 'is_combat': bool}
    Priority: REACT
    """
    def default_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != obj.id:
            return False

        is_combat = event.payload.get('is_combat', False)
        if combat_only and not is_combat:
            return False
        if noncombat_only and is_combat:
            return False

        return True

    actual_filter = filter_fn or default_filter

    def trigger_filter(event: Event, state: GameState) -> bool:
        return actual_filter(event, state, source_obj)

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Damage trigger")


# =============================================================================
# STATIC P/T BOOST (LORD EFFECT)
# =============================================================================

def make_static_pt_boost(
    source_obj: GameObject,
    power_mod: int,
    toughness_mod: int,
    affects_filter: Callable[[GameObject, GameState], bool]
) -> list[Interceptor]:
    """
    Create +X/+Y static ability interceptors (lord effects).

    Args:
        source_obj: The object granting the bonus
        power_mod: Power modifier (+1, -1, etc.)
        toughness_mod: Toughness modifier
        affects_filter: Function(target, state) -> bool to determine which objects are affected

    Event: QUERY_POWER / QUERY_TOUGHNESS
    Priority: QUERY
    """
    interceptors = []
    source_id = source_obj.id  # Capture for closures

    if power_mod != 0:
        def power_filter(event: Event, state: GameState) -> bool:
            if event.type != EventType.QUERY_POWER:
                return False
            # Check that the source (lord) is on the battlefield
            source = state.objects.get(source_id)
            if not source or source.zone != ZoneType.BATTLEFIELD:
                return False
            target_id = event.payload.get('object_id')
            target = state.objects.get(target_id)
            if not target:
                return False
            return affects_filter(target, state)

        def power_handler(event: Event, state: GameState) -> InterceptorResult:
            current = event.payload.get('value', 0)
            new_event = event.copy()
            new_event.payload['value'] = current + power_mod
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event
            )

        interceptors.append(Interceptor(
            id=new_id(),
            source=source_obj.id,
            controller=source_obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=power_filter,
            handler=power_handler,
            duration='while_on_battlefield'
        ))

    if toughness_mod != 0:
        def toughness_filter(event: Event, state: GameState) -> bool:
            if event.type != EventType.QUERY_TOUGHNESS:
                return False
            # Check that the source (lord) is on the battlefield
            source = state.objects.get(source_id)
            if not source or source.zone != ZoneType.BATTLEFIELD:
                return False
            target_id = event.payload.get('object_id')
            target = state.objects.get(target_id)
            if not target:
                return False
            return affects_filter(target, state)

        def toughness_handler(event: Event, state: GameState) -> InterceptorResult:
            current = event.payload.get('value', 0)
            new_event = event.copy()
            new_event.payload['value'] = current + toughness_mod
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event
            )

        interceptors.append(Interceptor(
            id=new_id(),
            source=source_obj.id,
            controller=source_obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=toughness_filter,
            handler=toughness_handler,
            duration='while_on_battlefield'
        ))

    return interceptors


def make_dynamic_pt_boost(
    source_obj: GameObject,
    mod_fn: Callable[[GameObject, GameObject, GameState], tuple[int, int]],
    affects_filter: Callable[[GameObject, GameState], bool],
) -> list[Interceptor]:
    """+X/+Y boost where X and Y are computed at query time.

    Args:
        source_obj: the object granting the boost
        mod_fn: ``(source, target, state) -> (power_mod, toughness_mod)``
        affects_filter: ``(target, state) -> bool`` — which objects receive

    Returns QUERY_POWER + QUERY_TOUGHNESS interceptors that read the mod
    via ``mod_fn`` each time the query fires (so the value updates as the
    state changes — e.g. "+1/+1 for each Forest you control").
    """
    interceptors: list[Interceptor] = []
    source_id = source_obj.id

    def _query_filter(event_type: int):
        def _f(event: Event, state: GameState) -> bool:
            if event.type != event_type:
                return False
            source = state.objects.get(source_id)
            if not source or source.zone != ZoneType.BATTLEFIELD:
                return False
            target_id = event.payload.get('object_id')
            target = state.objects.get(target_id)
            if not target:
                return False
            return affects_filter(target, state)
        return _f

    def _make_handler(component_idx: int):
        def _h(event: Event, state: GameState) -> InterceptorResult:
            source = state.objects.get(source_id)
            target = state.objects.get(event.payload.get('object_id'))
            if not source or not target:
                return InterceptorResult(action=InterceptorAction.PASS)
            try:
                p_mod, t_mod = mod_fn(source, target, state)
            except Exception:
                return InterceptorResult(action=InterceptorAction.PASS)
            mod = p_mod if component_idx == 0 else t_mod
            if mod == 0:
                return InterceptorResult(action=InterceptorAction.PASS)
            new_event = event.copy()
            new_event.payload['value'] = new_event.payload.get('value', 0) + mod
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event,
            )
        return _h

    interceptors.append(Interceptor(
        id=new_id(),
        source=source_id,
        controller=source_obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=_query_filter(EventType.QUERY_POWER),
        handler=_make_handler(0),
        duration='while_on_battlefield',
    ))
    interceptors.append(Interceptor(
        id=new_id(),
        source=source_id,
        controller=source_obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=_query_filter(EventType.QUERY_TOUGHNESS),
        handler=_make_handler(1),
        duration='while_on_battlefield',
    ))
    return interceptors


# =============================================================================
# KEYWORD GRANT
# =============================================================================

def make_keyword_grant(
    source_obj: GameObject,
    keywords: list[str],
    affects_filter: Callable[[GameObject, GameState], bool]
) -> Interceptor:
    """
    Create a keyword-granting interceptor (static ability).

    Args:
        source_obj: The object granting the keywords
        keywords: List of keyword names to grant (e.g., ['flying', 'vigilance'])
        affects_filter: Function(target, state) -> bool to determine which objects receive keywords

    Event: QUERY_ABILITIES
    Payload: {'object_id': str, 'granted': list[str]}
    Priority: QUERY
    """
    def ability_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return affects_filter(target, state)

    def ability_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []))
        for kw in keywords:
            if kw not in granted:
                granted.append(kw)
        new_event.payload['granted'] = granted
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=ability_filter,
        handler=ability_handler,
        duration='while_on_battlefield'
    )


# =============================================================================
# COST REDUCTION (static / conditional)
# =============================================================================

def make_cost_reduction(
    source_obj: GameObject,
    *,
    applies_to: Callable[[GameObject, str, GameState], bool],
    amount,
    self_only: bool = False,
    condition_fn: Optional[Callable[[GameState], bool]] = None,
) -> Interceptor:
    """
    Register a cost-reduction interceptor.

    The reduction lowers the *generic* portion of the spell's mana cost only;
    coloured, colourless ({C}), snow ({S}), hybrid, and Phyrexian symbols are
    always preserved (so {2}{R}{R} reduced by {3} stays at {R}{R}, not {0}).
    Multiple reductions stack additively. Generic is clamped at 0.

    `condition_fn(state) -> bool`: optional state-time gate. If provided and
    returns False, the reduction is skipped for this query. Use for "Dark Side
    — costs less while life < 10" / "if it's your second spell this turn".
    """
    source_id = source_obj.id

    if self_only:
        original_applies = applies_to

        def _self_applies(card: GameObject, pid: str, state: GameState) -> bool:
            if card is None or card.id != source_id:
                return False
            if original_applies is None:
                return True
            return bool(original_applies(card, pid, state))

        applies_to = _self_applies
        duration = 'forever'
    else:
        duration = 'while_on_battlefield'

    def cost_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_COST:
            return False
        if not self_only:
            src = state.objects.get(source_id)
            if not src or src.zone != ZoneType.BATTLEFIELD:
                return False
        card = event.payload.get('card')
        pid = event.payload.get('player_id')
        if card is None or pid is None:
            return False
        if condition_fn is not None:
            try:
                if not condition_fn(state):
                    return False
            except Exception:
                return False
        try:
            return bool(applies_to(card, pid, state))
        except Exception:
            return False

    def cost_handler(event: Event, state: GameState) -> InterceptorResult:
        try:
            if callable(amount):
                card = event.payload.get('card')
                amt = int(amount(card, state) or 0)
            else:
                amt = int(amount or 0)
        except (TypeError, ValueError):
            amt = 0
        if amt <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)

        new_event = event.copy()
        from src.engine.cost_query import REDUCTION_KEY
        running = int(new_event.payload.get(REDUCTION_KEY, 0))
        new_event.payload[REDUCTION_KEY] = running + amt
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=cost_filter,
        handler=cost_handler,
        duration=duration,
    )
    if self_only:
        # Tag for the pipeline's _cleanup_departed_interceptors to sweep on
        # any ZONE_CHANGE of the source card. Without this, self_only
        # reductions with duration='forever' would accumulate forever once
        # the spell resolves and moves to graveyard / exile.
        setattr(interceptor, "_cleanup_on_zone_change", True)
    return interceptor


# =============================================================================
# WARD (CR 702.21 / CR 603)
# =============================================================================
#
# Ward {N} (or "ward—pay X life", "ward—sacrifice a creature", etc.) is a
# triggered ability that fires whenever an opponent's spell or ability targets
# the warded permanent. The triggered ability counters that spell unless the
# opponent pays the ward cost.
#
# Implementation:
#   * ``make_ward`` is a REACT-priority interceptor with
#     ``is_triggered_ability=True``. The pipeline queues a TriggeredStackItem
#     onto ``state.pending_triggers`` instead of firing the effect inline.
#   * Targets are committed to a stack item; priority emits one
#     ``EventType.TARGET_CHOSEN`` per chosen target. Ward triggers off those.
#   * On resolution the Ward trigger emits ``COUNTER_SPELL_UNLESS_PAY``;
#     the system counterspell glue counters the matching stack item.
#   * In auto-resolve mode (default for tests) the trigger drains inline
#     after the REACT phase, preserving the previous "ward fires
#     immediately" semantics.
#   * Under the priority loop, the Ward trigger goes on top of the stack
#     and resolves *before* the spell that targeted the warded creature
#     (LIFO), per CR 603.
#
# v1 simplifications still in effect:
#   * The existing system interceptor for COUNTER_SPELL_UNLESS_PAY treats
#     it as an unconditional counter — it does not yet prompt the
#     opponent to pay.
# =============================================================================

def make_ward(
    source_obj: GameObject,
    *,
    mana_cost: Optional[str] = None,
    life_cost: Optional[int] = None,
    custom_cost: Optional[str] = None,
) -> Interceptor:
    """Register a Ward triggered ability on ``source_obj`` (CR 702.21).

    Ward is a triggered ability: when a creature with Ward becomes the target
    of a spell or ability an opponent controls, that spell/ability is
    countered unless its controller pays the ward cost. Per CR 603 the
    trigger goes onto the stack (via ``TriggeredStackItem``) and resolves
    in the next priority window — *before* the spell that targeted the
    warded creature, since both sit on the stack in LIFO order.

    In auto-resolve mode (``state.options.auto_resolve_triggers=True``,
    default for tests) the trigger drains inline immediately after the
    REACT phase, preserving "ward fires immediately" semantics that
    existing tests rely on.
    """
    source_id = source_obj.id
    controller_id = source_obj.controller

    cost_payload: dict[str, Any] = {}
    if mana_cost:
        cost_payload['mana_cost'] = mana_cost
    if life_cost is not None:
        cost_payload['life_cost'] = int(life_cost)
    if custom_cost:
        cost_payload['custom_cost'] = custom_cost

    def ward_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.TARGET_CHOSEN:
            return False
        if event.payload.get('target_id') != source_id:
            return False
        source = state.objects.get(source_id)
        cur_controller = source.controller if source else controller_id
        spell_controller = event.payload.get('controller')
        if not spell_controller or spell_controller == cur_controller:
            return False
        return True

    def ward_effect(event: Event, state: GameState) -> list[Event]:
        """Resolve the Ward trigger by emitting COUNTER_SPELL_UNLESS_PAY.

        The synthetic event is consumed by the system counterspell glue,
        which counters the matching stack item unless the spell's
        controller pays the ward cost.
        """
        spell_id = event.payload.get('spell_id')
        if not spell_id:
            return []
        return [Event(
            type=EventType.COUNTER_SPELL_UNLESS_PAY,
            payload={
                'spell_id': spell_id,
                'target_id': source_id,
                'reason': 'ward',
                **cost_payload,
            },
            source=source_id,
            controller=controller_id,
        )]

    def ward_handler(event: Event, state: GameState) -> InterceptorResult:
        # Legacy/fallback handler — only used if a caller flips
        # ``is_triggered_ability=False`` (e.g. tests forcing inline mode).
        new_events = ward_effect(event, state)
        if not new_events:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events,
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_id,
        controller=controller_id,
        priority=InterceptorPriority.REACT,
        filter=ward_filter,
        handler=ward_handler,
        duration='while_on_battlefield',
    )
    return _mark_triggered_ability(
        interceptor, ward_effect, description="Ward trigger",
    )


# =============================================================================
# SHOCKLAND ("As this land enters, you may pay N life. Otherwise it enters tapped.")
# =============================================================================

def make_shockland_setup(*, life_cost: int = 2):
    """Build a ``setup_interceptors`` callable for a Ravnica-style shock land.

    Printed text:
        "As this land enters, you may pay 2 life. If you don't, it enters tapped."

    The returned callable wires a single ETB-trigger interceptor onto the land.
    When the land enters the battlefield, the trigger:

      1. Opens a ``PendingChoice`` (``choice_type='shockland'``) owned by the
         land's controller. Options are ``[True, False]`` — pay / decline.
      2. The choice's handler resolves the selection:
           * ``[True]``  -> emit ``LIFE_CHANGE`` for ``-life_cost`` to the
             controller. The land stays untapped.
           * ``[False]`` -> emit ``TAP`` on the land. No life change.
      3. For AI players, ``create_choice_and_resolve`` auto-resolves the choice
         inline via the ``heuristic_pick`` preset: pay when controller's life is
         comfortably above the threshold (default ``life_cost + 3``), otherwise
         decline so we don't dip to a lethal range.
      4. For human players, the choice is left pending on ``state.pending_choice``
         and the session-layer surfaces it via the standard PendingChoice UI.

    The mana ability itself is auto-derived from the land's basic-land subtypes
    (``Forest``, ``Island``, etc.) by ``ManaSystem._get_land_mana_production``,
    so this helper deliberately registers no mana interceptor.

    Args:
        life_cost: Life to pay to bypass the tap. Defaults to 2 (matches all
            printed Ravnica shocks).

    Returns:
        ``setup(obj, state) -> list[Interceptor]`` suitable for passing to
        ``make_land(setup_interceptors=...)``.

    Example:
        BREEDING_POOL = make_land(
            name="Breeding Pool",
            text="({T}: Add {G} or {U}.)\\nAs this land enters, you may pay 2 "
                 "life. If you don't, it enters tapped.",
            subtypes={"Forest", "Island"},
            setup_interceptors=make_shockland_setup(life_cost=2),
        )
    """
    cost = int(life_cost)

    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        source_id = obj.id
        controller_id = obj.controller

        def _shockland_handler(choice, selected, st):
            """Resolve the pay-or-tap selection.

            ``selected`` is a single-element list whose value is ``True`` (pay)
            or ``False`` (decline). Falsy/missing values are treated as decline
            (safer: the player kept their life total).
            """
            chose_pay = bool(selected and selected[0] is True)
            # Re-resolve the land in case the controller changed after ETB
            # but before the choice resolved.
            land = st.objects.get(source_id)
            target_player = (land.controller if land is not None else controller_id)
            if chose_pay:
                return [Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': target_player, 'amount': -cost},
                    source=source_id,
                )]
            # Decline: tap the land.
            return [Event(
                type=EventType.TAP,
                payload={'object_id': source_id},
                source=source_id,
            )]

        def _etb_effect(event: Event, st: GameState) -> list[Event]:
            # Pick up the current controller from state at fire-time so a
            # control-change between ETB queue-time and resolution still picks
            # the right player. Falls back to the captured controller_id.
            land = st.objects.get(source_id)
            pc_player = land.controller if land is not None else controller_id
            player = st.players.get(pc_player) if pc_player else None
            life = getattr(player, 'life', 20) if player is not None else 20

            # Heuristic: pay when comfortably above the tap-loss threshold.
            # We require life > cost + 3 so the AI doesn't drop itself into
            # a lethal range for a tempo-only tap. This matches the prior
            # inline _handle_play_land heuristic (life > 4 when cost=2)
            # while keeping the new threshold parametric on ``life_cost``.
            heuristic = [True] if life > cost + 3 else [False]

            from src.engine.pending_choice_helpers import create_choice_and_resolve

            return create_choice_and_resolve(
                st,
                choice_type="shockland",
                player_id=pc_player,
                prompt=f"Pay {cost} life to keep this land untapped?",
                options=[True, False],
                source_id=source_id,
                min_choices=1,
                max_choices=1,
                handler=_shockland_handler,
                heuristic_pick=heuristic,
            )

        return [make_etb_trigger(obj, _etb_effect)]

    return _setup


# =============================================================================
# SPELL CAST TRIGGER
# =============================================================================

def make_spell_cast_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    controller_only: bool = True,
    spell_type_filter: Optional[set[CardType]] = None,
    color_filter: Optional[set[Color]] = None,
    mana_value_min: Optional[int] = None,
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None
) -> Interceptor:
    """
    Create a spell cast trigger interceptor.

    Args:
        source_obj: The object with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        controller_only: If True, only trigger on spells cast by controller (default True)
        spell_type_filter: Only trigger on specific spell types (e.g., {CardType.INSTANT})
        color_filter: Only trigger on spells containing these colors
        mana_value_min: Only trigger on spells with MV >= this value
        filter_fn: Optional custom filter for additional conditions

    Event: CAST
    Payload: {'spell_id': str, 'caster': str, 'mana_value': int, 'colors': set, 'types': set}
    Priority: REACT
    """
    def default_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False

        # Check controller
        caster = event.payload.get('caster') or event.payload.get('controller') or event.controller
        if controller_only and caster != obj.controller:
            return False

        # Check spell type
        if spell_type_filter:
            spell_types = set(event.payload.get('types', []))
            if not spell_types and event.payload.get('spell_type') is not None:
                spell_types = {event.payload.get('spell_type')}
            if not spell_types.intersection(spell_type_filter):
                return False

        # Check colors
        if color_filter:
            spell_colors = set(event.payload.get('colors', []))
            if not spell_colors and event.payload.get('color') is not None:
                spell_colors = {event.payload.get('color')}
            if not spell_colors.intersection(color_filter):
                return False

        # Check mana value
        if mana_value_min is not None:
            mv = event.payload.get('mana_value', 0)
            if mv < mana_value_min:
                return False

        return True

    actual_filter = filter_fn or default_filter

    def trigger_filter(event: Event, state: GameState) -> bool:
        return actual_filter(event, state, source_obj)

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Spell cast trigger")


# =============================================================================
# TAP TRIGGER
# =============================================================================

def make_tap_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None
) -> Interceptor:
    """
    Create a tap trigger interceptor (whenever this permanent is tapped).

    Args:
        source_obj: The permanent with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        filter_fn: Optional custom filter

    Event: TAP with object_id == source_obj.id
    Priority: REACT
    """
    def default_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        return (event.type == EventType.TAP and
                event.payload.get('object_id') == obj.id)

    actual_filter = filter_fn or default_filter

    def trigger_filter(event: Event, state: GameState) -> bool:
        return actual_filter(event, state, source_obj)

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Tap trigger")


# =============================================================================
# UPKEEP TRIGGER
# =============================================================================

def make_upkeep_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    controller_only: bool = True
) -> Interceptor:
    """
    Create an upkeep trigger interceptor (at the beginning of upkeep).

    Args:
        source_obj: The permanent with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        controller_only: If True, only trigger on controller's upkeep

    Event: PHASE_START with phase == 'upkeep'
    Priority: REACT
    """
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'upkeep':
            return False
        if controller_only and state.active_player != source_obj.controller:
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Upkeep trigger")


# =============================================================================
# END STEP TRIGGER
# =============================================================================

def make_end_step_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    controller_only: bool = True
) -> Interceptor:
    """
    Create an end step trigger interceptor (at the beginning of end step).

    Args:
        source_obj: The permanent with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        controller_only: If True, only trigger on controller's end step

    Event: PHASE_START with phase == 'end_step'
    Priority: REACT
    """
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'end_step':
            return False
        if controller_only and state.active_player != source_obj.controller:
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="End step trigger")


# =============================================================================
# Delayed triggers
# =============================================================================
#
# Pattern: "Whenever X happens, accumulate a marker. At a later phase, fire an
# effect using the accumulated payloads, then clear the tracker."
#
# This is the canonical shape for cards like Jeong Jeong, the Deserter
# ("at end of next turn, copy each card exiled with this") or any
# "do X for each Y you did this turn" effect that needs deferred resolution.
#
# Storage: ``state.turn_data['_delayed_<source.id>_triggers']`` — a list of
# event payloads (dicts) accumulated by the watcher. The list is cleared
# both after the deferred effect fires AND on TURN_END (so a Jeong Jeong
# whose end step is skipped, or whose controller leaves the battlefield
# before end step, doesn't carry the markers across turns).
#
# Returns a list of interceptors: [watcher, deferred_firer, turn_end_cleanup].
# The caller concatenates this list into their setup return, e.g.:
#     return [make_etb_trigger(obj, fn), *make_delayed_trigger(obj, ...)]


def make_delayed_trigger(
    source_obj: GameObject,
    *,
    watch_event: EventType,
    watch_filter: Callable[[Event, GameState, GameObject], bool],
    deferred_at: str = 'end_of_your_turn',
    deferred_effect_fn: Callable[[GameObject, GameState, list[dict]], list[Event]],
    duration: str = 'while_on_battlefield',
) -> list[Interceptor]:
    """Build a watcher + deferred-firer pair for delayed-trigger effects.

    Args:
        source_obj: The permanent that owns the delayed trigger.
        watch_event: Event type to watch (e.g. ``EventType.SPELL_CAST``).
        watch_filter: ``(event, state, source) -> bool``. Return True to record
            the event payload onto the delayed-trigger queue. ``CAST`` and
            ``SPELL_CAST`` are commonly aliased; if you want both, accept either
            via your filter.
        deferred_at: When to fire the deferred effect. Supported values:
            ``'end_of_your_turn'`` (default — PHASE_START, phase=end_step,
            active player == source.controller),
            ``'end_of_turn'`` (any player's end step),
            ``'next_upkeep'`` (controller's upkeep on a later turn).
        deferred_effect_fn: ``(source, state, accumulated_payloads) -> list[Event]``.
            Runs once at the deferred phase. Receives the recorded payloads
            (a list of dicts — the original ``event.payload`` snapshots). The
            tracker is cleared before this returns.
        duration: Lifetime for the interceptors. Defaults to
            ``'while_on_battlefield'`` so the interceptors retire when the
            source leaves the battlefield (and cleanup handles them).

    Returns:
        A list ``[watcher, deferred_firer, turn_end_cleanup]``. Splat into your
        setup's return.

    Notes:
        * The tracker key uses ``source_obj.id``, so multiple copies of the
          same card (e.g. two Jeong Jeongs) get independent queues.
        * ``TURN_END`` always clears the queue as a safety net, regardless of
          whether the deferred firer ran. This protects against rules paths
          that skip the end step (e.g. a player loses mid-turn).
    """
    tracker_key = f"_delayed_{source_obj.id}_triggers"

    def watcher_filter(event: Event, state: GameState) -> bool:
        # Allow callers to listen for either CAST or SPELL_CAST by accepting
        # the event-type test in the user filter; we still gate on the
        # primary watch_event to keep the matrix small.
        if event.type != watch_event:
            return False
        return watch_filter(event, state, source_obj)

    def watcher_handler(event: Event, state: GameState) -> InterceptorResult:
        td = getattr(state, "turn_data", None)
        if td is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        bucket = td.setdefault(tracker_key, [])
        if not isinstance(bucket, list):
            bucket = []
            td[tracker_key] = bucket
        # Snapshot the payload so later mutation can't bite us.
        bucket.append(dict(event.payload or {}))
        return InterceptorResult(action=InterceptorAction.PASS)

    watcher = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=watcher_filter,
        handler=watcher_handler,
        duration=duration,
    )

    def deferred_filter(event: Event, state: GameState) -> bool:
        # Only fire if there's actually something accumulated. This prevents
        # an empty trigger from queueing on every PHASE_START.
        td = getattr(state, "turn_data", None)
        if td is None or not (td.get(tracker_key) or []):
            return False
        if deferred_at in ('end_of_your_turn', 'end_of_turn'):
            if event.type != EventType.PHASE_START:
                return False
            if event.payload.get('phase') != 'end_step':
                return False
            if deferred_at == 'end_of_your_turn':
                if state.active_player != source_obj.controller:
                    return False
            return True
        if deferred_at == 'next_upkeep':
            if event.type != EventType.PHASE_START:
                return False
            if event.payload.get('phase') != 'upkeep':
                return False
            if state.active_player != source_obj.controller:
                return False
            return True
        # Unknown deferred_at — fail safe.
        return False

    def deferred_handler(event: Event, state: GameState) -> InterceptorResult:
        td = getattr(state, "turn_data", None)
        if td is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        bucket = td.get(tracker_key) or []
        # Clear before firing so re-entrant emissions don't double-fire.
        td[tracker_key] = []
        if not bucket:
            return InterceptorResult(action=InterceptorAction.PASS)
        new_events = deferred_effect_fn(source_obj, state, bucket) or []
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events,
        )

    # Wrap the deferred handler effect so it can be queued as a TriggeredStackItem.
    def _deferred_effect_fn(event: Event, state: GameState) -> list[Event]:
        td = getattr(state, "turn_data", None)
        if td is None:
            return []
        bucket = td.get(tracker_key) or []
        td[tracker_key] = []
        if not bucket:
            return []
        return list(deferred_effect_fn(source_obj, state, bucket) or [])

    deferred = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=deferred_filter,
        handler=deferred_handler,
        duration=duration,
    )
    _mark_triggered_ability(deferred, _deferred_effect_fn, description="Delayed trigger")

    # Safety-net cleanup at TURN_END so a queue from a turn whose end step
    # was skipped doesn't leak into the next turn.
    def cleanup_filter(event: Event, state: GameState) -> bool:
        return event.type == EventType.TURN_END

    def cleanup_handler(event: Event, state: GameState) -> InterceptorResult:
        td = getattr(state, "turn_data", None)
        if td is not None and tracker_key in td:
            td[tracker_key] = []
        return InterceptorResult(action=InterceptorAction.PASS)

    cleanup = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=cleanup_filter,
        handler=cleanup_handler,
        duration=duration,
    )

    return [watcher, deferred, cleanup]


# =============================================================================
# EERIE TRIGGER (DSK)
# =============================================================================

def make_eerie_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
) -> Interceptor:
    """Create an Eerie trigger interceptor (Duskmourn / DSK).

    Printed wording: "Eerie — Whenever an enchantment you control enters and
    whenever you fully unlock a Room, <effect>."

    The interceptor fires for either of the following events, both gated to
    the source's controller:

      1. ``EventType.ZONE_CHANGE`` where the entering object is an
         enchantment controlled by ``source_obj.controller`` and the
         destination is the battlefield. (The source itself entering is
         excluded so a card with Eerie doesn't trigger its own ETB.)

      2. ``EventType.UNLOCK_DOOR`` where the Room's controller equals
         ``source_obj.controller`` AND, after the unlock has been resolved,
         the Room has both doors unlocked. Door 1 unlocks on ETB and Door 2
         unlocks via a sorcery-speed activated ability; in steady state the
         second UNLOCK_DOOR event for a given room is the "fully unlocks"
         moment.

    Args:
        source_obj: The object with the Eerie ability.
        effect_fn: ``Function(event, state) -> list[Event]`` to emit when
            either trigger condition fires.

    Returns:
        A REACT-priority interceptor scoped to
        ``duration='while_on_battlefield'`` (matches Survival's lifetime
        — when the source leaves play, the interceptor is cleaned up).

    Notes:
        Some Eerie cards (e.g. *Fear of Infinity*) have an Eerie ability
        that triggers from the graveyard. Those cards still use this helper
        but pass a custom ``effect_fn`` whose payload reflects the
        graveyard-based effect; the source-on-battlefield gate in this
        helper would *prevent* fire from graveyard, so those cards
        intentionally roll their own (see ``fear_of_infinity_setup``).
    """
    def trigger_filter(event: Event, state: GameState) -> bool:
        # The source must still be on the battlefield.
        current = state.objects.get(source_obj.id)
        if current is None:
            return False
        if current.zone != ZoneType.BATTLEFIELD:
            return False

        # Branch 1: enchantment ETB.
        if event.type == EventType.ZONE_CHANGE:
            if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
                return False
            entering_id = event.payload.get('object_id')
            if not entering_id or entering_id == source_obj.id:
                # Don't fire on the source's own ETB.
                return False
            entering = state.objects.get(entering_id)
            if entering is None:
                return False
            if CardType.ENCHANTMENT not in entering.characteristics.types:
                return False
            return entering.controller == current.controller

        # Branch 2: Room fully unlocked (UNLOCK_DOOR resolves the door first,
        # so by the time REACT runs, both doors are present in
        # ``unlocked_doors`` for a "fully unlock" trigger).
        if event.type == EventType.UNLOCK_DOOR:
            room_id = event.payload.get('object_id')
            if not room_id:
                return False
            room = state.objects.get(room_id)
            if room is None:
                return False
            if room.controller != current.controller:
                return False
            doors = getattr(room.state, 'unlocked_doors', None)
            # Treat "fully unlocked" as ≥ 2 doors unlocked. (DSK Rooms
            # always have exactly two doors; we don't assume the engine
            # tracks the door manifest.)
            return isinstance(doors, list) and len(doors) >= 2

        return False

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events,
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Eerie trigger")


# =============================================================================
# SURVIVAL TRIGGER (DSK)
# =============================================================================

def make_survival_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
) -> Interceptor:
    """
    Create a Survival trigger interceptor.

    Survival is a Duskmourn (DSK) keyword: "At the beginning of your second
    main phase, if this creature is tapped, X." This helper registers a
    PHASE_START interceptor that fires only when:
      1. The event is PHASE_START with phase == 'postcombat_main'
         (the engine emits this for the second main phase).
      2. The active player is the source's controller (it's their second main).
      3. The source is on the battlefield and tapped at trigger time.

    Args:
        source_obj: The creature with Survival.
        effect_fn: Function(event, state) -> list[Event] to execute when the
            trigger fires (the X in "if this creature is tapped, X").

    Returns:
        An Interceptor at REACT priority, scoped to ``while_on_battlefield``.
    """
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        # Accept the canonical "postcombat_main" plus a couple of legacy
        # spellings that other card files have used historically, so that
        # any future engine renaming doesn't silently turn Survival cards
        # into no-ops.
        if event.payload.get('phase') not in (
            'postcombat_main', 'main2', 'second_main',
        ):
            return False
        # Must be the controller's own second main phase.
        if state.active_player != source_obj.controller:
            return False
        # Re-resolve the source from state (handler may capture a stale
        # snapshot if the card moved zones, e.g. a token Survivor exiled).
        current = state.objects.get(source_obj.id)
        if current is None:
            return False
        if current.zone != ZoneType.BATTLEFIELD:
            return False
        if not current.state.tapped:
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events,
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Survival trigger")


# =============================================================================
# EXILE-WITH-SOURCE TRACKING (Veteran Survivor template)
# =============================================================================
#
# Cards like Veteran Survivor count "cards exiled with this creature" to
# scale a static effect ("As long as there are three or more cards exiled
# with this creature, ..."). The tracking lives on
# ``ObjectState.exiled_with_source`` (a list[str] of object ids).
#
# Use ``track_exile_with`` when emitting/resolving the EXILE event for a
# specific source, and ``count_exiled_with`` from a static interceptor
# (QUERY_POWER / QUERY_TOUGHNESS / QUERY_ABILITIES) to read the count.
# =============================================================================


def track_exile_with(state: GameState, source_id: str, exiled_id: str) -> None:
    """Record that ``exiled_id`` was exiled by ``source_id`` (additive).

    Safe to call repeatedly; duplicates are ignored. The card is *not*
    removed when the exiling source leaves play — Veteran Survivor's static
    ability is gated by source-on-battlefield, so the count effectively
    becomes inert (still readable for log/debug).
    """
    source = state.objects.get(source_id)
    if source is None:
        return
    tracker = getattr(source.state, 'exiled_with_source', None)
    if tracker is None:
        tracker = []
        source.state.exiled_with_source = tracker
    if exiled_id and exiled_id not in tracker:
        tracker.append(exiled_id)


def count_exiled_with(state: GameState, source_id: str) -> int:
    """Return the number of cards exiled with ``source_id``.

    Cards that have since left the exile zone (e.g. a saga that returned
    them, a flicker effect) are still counted — Veteran Survivor's reminder
    text is "exiled with this creature" without a "still in exile" rider.
    """
    source = state.objects.get(source_id)
    if source is None:
        return 0
    tracker = getattr(source.state, 'exiled_with_source', None) or []
    return len(tracker)


# =============================================================================
# LIFE CHANGE TRIGGER
# =============================================================================

def make_life_gain_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    controller_only: bool = True
) -> Interceptor:
    """
    Create a life gain trigger (whenever you gain life).

    Args:
        source_obj: The permanent with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        controller_only: If True, only trigger when controller gains life

    Event: LIFE_CHANGE with amount > 0
    Priority: REACT
    """
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        amount = event.payload.get('amount', 0)
        if amount <= 0:
            return False
        if controller_only and event.payload.get('player') != source_obj.controller:
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Life gain trigger")


def make_life_loss_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    opponent_only: bool = True
) -> Interceptor:
    """
    Create a life loss trigger (whenever an opponent loses life).

    Args:
        source_obj: The permanent with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        opponent_only: If True, only trigger when opponents lose life

    Event: LIFE_CHANGE with amount < 0
    Priority: REACT
    """
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        amount = event.payload.get('amount', 0)
        if amount >= 0:
            return False
        if opponent_only and event.payload.get('player') == source_obj.controller:
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Life loss trigger")


# =============================================================================
# DRAW TRIGGER
# =============================================================================

def make_draw_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    controller_only: bool = True
) -> Interceptor:
    """
    Create a draw trigger (whenever you draw a card).

    Args:
        source_obj: The permanent with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        controller_only: If True, only trigger when controller draws

    Event: DRAW
    Priority: REACT
    """
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DRAW:
            return False
        if controller_only and event.payload.get('player') != source_obj.controller:
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Draw trigger")


# =============================================================================
# COUNTER ADDED TRIGGER
# =============================================================================

def make_counter_added_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    counter_type: Optional[str] = None,
    self_only: bool = True
) -> Interceptor:
    """
    Create a counter added trigger.

    Args:
        source_obj: The permanent with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        counter_type: Specific counter type to trigger on (None = any)
        self_only: If True, only trigger when counters are added to this permanent

    Event: COUNTER_ADDED
    Priority: REACT
    """
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.COUNTER_ADDED:
            return False
        if self_only and event.payload.get('object_id') != source_obj.id:
            return False
        if counter_type and event.payload.get('counter_type') != counter_type:
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Counter added trigger")


# =============================================================================
# ADDITIONAL LAND PLAY (Static Ability)
# =============================================================================

def make_additional_land_play(
    source_obj: GameObject,
    count: int = 1
) -> Interceptor:
    """
    Create a static ability that grants additional land plays.

    Used for cards like Exploration ("You may play an additional land on each of your turns").

    This interceptor fires at the beginning of each of the controller's turns to
    increase their lands_allowed_this_turn count.

    Args:
        source_obj: The permanent granting additional land plays
        count: Number of additional lands allowed (default 1)

    Event: TURN_START for controller
    Priority: REACT

    Example usage:
        EXPLORATION = make_enchantment(
            name="Exploration",
            mana_cost="{G}",
            colors={Color.GREEN},
            text="You may play an additional land on each of your turns.",
            setup_interceptors=lambda obj, state: [make_additional_land_play(obj, 1)]
        )
    """
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.TURN_START:
            return False
        # Only on controller's turn
        return event.payload.get('player') == source_obj.controller

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        # Directly modify the GameState land allowance
        # This is safe because interceptors run during event processing
        state.lands_allowed_this_turn += count
        return InterceptorResult(
            action=InterceptorAction.PASS  # No new events, just modified state
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )


# =============================================================================
# PLAYER CHOICE HELPERS
# =============================================================================

def create_modal_choice(
    state: GameState,
    player_id: str,
    source_id: str,
    modes: list[dict],
    min_modes: int = 1,
    max_modes: int = 1,
    prompt: str = "Choose a mode:"
) -> PendingChoice:
    """
    Create a modal spell choice.

    Args:
        state: The game state
        player_id: Player who makes the choice
        source_id: Card/ability that needs the choice
        modes: List of mode options, each as {"index": int, "text": str}
        min_modes: Minimum modes to choose (default 1)
        max_modes: Maximum modes to choose (default 1, use 2+ for "choose two")
        prompt: UI prompt text

    Example:
        # Choose one:
        choice = create_modal_choice(
            state, controller_id, spell_id,
            modes=[
                {"index": 0, "text": "Target creature gets +2/+2 until end of turn"},
                {"index": 1, "text": "Target creature gains flying until end of turn"},
            ]
        )

        # Choose two:
        choice = create_modal_choice(
            state, controller_id, spell_id,
            modes=[...],
            min_modes=2,
            max_modes=2,
            prompt="Choose two:"
        )
    """
    choice = PendingChoice(
        choice_type="modal",
        player=player_id,
        prompt=prompt,
        options=modes,
        source_id=source_id,
        min_choices=min_modes,
        max_choices=max_modes
    )
    state.pending_choice = choice
    return choice


# =============================================================================
# Spree (cost-per-mode)
# =============================================================================
# OTJ Spree mechanic: "Choose one or more additional costs" — each chosen mode
# adds its mana cost to the spell AND its effect to the resolution. The
# implementation lives in src/engine/spree.py; this helper is a thin re-export
# so card files don't have to reach into the engine module directly.
#
# Pair ``make_spree_setup`` (returned from setup_interceptors=...) with
# ``make_spree_resolve`` (set as the card's resolve=...) so chosen modes'
# effects fire in declaration order at resolve time. The priority layer
# detects Spree spells via ``card_def._spree`` (set by make_spree_setup) and
# opens the mode prompt at cast time, charging each chosen mode's surcharge
# as part of the cast.


from src.engine.spree import (
    SpreeMode,
    make_spree_setup as _engine_make_spree_setup,
    make_spree_resolve,
    compute_affordable_spree_modes,
    get_chosen_spree_modes,
    is_spree_card,
    get_spree_modes,
    get_spree_minmax,
)


def make_spree_setup(obj: GameObject, *, base_modes, min_modes: int = 1, max_modes=None):
    """Card-side helper: register Spree metadata for ``obj``.

    Args:
        obj: GameObject for the Spree spell. Its ``card_def`` is tagged with
            the modes/min/max so the priority layer can find them.
        base_modes: ordered list of ``SpreeMode``. Each describes one
            ``+ <cost> — <effect>`` line on the card.
        min_modes: minimum number of modes that must be chosen. Defaults to 1
            (matches printed Spree text). Must be >= 1.
        max_modes: maximum modes. Defaults to ``len(base_modes)`` (Spree
            allows "one or more").

    Returns an empty interceptor list — Spree is driven from the priority
    layer rather than via per-event interceptors. The empty list is safe to
    return from ``setup_interceptors``.

    Example::

        from src.engine import SpreeMode, make_spree_resolve

        def _mode_a(spell, state, targets):
            return [Event(type=EventType.LIFE_CHANGE,
                          payload={'player': spell.controller, 'amount': 2},
                          source=spell.id)]

        def _mode_b(spell, state, targets):
            return [Event(type=EventType.DRAW,
                          payload={'player': spell.controller, 'amount': 1},
                          source=spell.id)]

        SPREE_MODES = [
            SpreeMode(name="Mode A", extra_cost="{1}", effect_fn=_mode_a),
            SpreeMode(name="Mode B", extra_cost="{2}", effect_fn=_mode_b),
        ]

        MY_CARD = make_instant(
            name="My Spree Spell",
            mana_cost="{R}",
            colors={Color.RED},
            text="Spree (Choose one or more additional costs.)\\n+ {1} - ...\\n+ {2} - ...",
            setup_interceptors=lambda obj, state: make_spree_setup(
                obj, base_modes=SPREE_MODES,
            ),
            resolve=make_spree_resolve(SPREE_MODES),
        )
    """
    return _engine_make_spree_setup(
        obj,
        base_modes=base_modes,
        min_modes=min_modes,
        max_modes=max_modes,
    )


# Re-export the engine helpers for direct import from card files.
__all_spree__ = [
    'SpreeMode',
    'make_spree_setup',
    'make_spree_resolve',
    'compute_affordable_spree_modes',
    'get_chosen_spree_modes',
    'is_spree_card',
    'get_spree_modes',
    'get_spree_minmax',
]


def create_scry_choice(
    state: GameState,
    player_id: str,
    source_id: str,
    card_ids: list[str],
    scry_count: int = None
) -> PendingChoice:
    """
    Create a scry choice.

    Args:
        state: The game state
        player_id: Player who is scrying
        source_id: Card/ability causing the scry
        card_ids: IDs of the top cards being scryed
        scry_count: Number being scryed (defaults to len(card_ids))

    Returns the PendingChoice. Player selects which cards go to bottom.
    Cards not selected stay on top in their original order.

    Example:
        # Scry 2
        top_cards = get_top_cards(library, 2)
        choice = create_scry_choice(state, player_id, source_id, top_cards)
    """
    count = scry_count or len(card_ids)
    choice = PendingChoice(
        choice_type="scry",
        player=player_id,
        prompt=f"Scry {count}: Choose cards to put on the bottom of your library",
        options=card_ids,
        source_id=source_id,
        min_choices=0,
        max_choices=len(card_ids),
        callback_data={"scry_count": count}
    )
    state.pending_choice = choice
    return choice


def create_surveil_choice(
    state: GameState,
    player_id: str,
    source_id: str,
    card_ids: list[str],
    surveil_count: int = None
) -> PendingChoice:
    """
    Create a surveil choice.

    Args:
        state: The game state
        player_id: Player who is surveilling
        source_id: Card/ability causing the surveil
        card_ids: IDs of the top cards being surveilled
        surveil_count: Number being surveilled (defaults to len(card_ids))

    Returns the PendingChoice. Player selects which cards go to graveyard.
    Cards not selected stay on top.

    Example:
        # Surveil 2
        top_cards = get_top_cards(library, 2)
        choice = create_surveil_choice(state, player_id, source_id, top_cards)
    """
    count = surveil_count or len(card_ids)
    choice = PendingChoice(
        choice_type="surveil",
        player=player_id,
        prompt=f"Surveil {count}: Choose cards to put into your graveyard",
        options=card_ids,
        source_id=source_id,
        min_choices=0,
        max_choices=len(card_ids),
        callback_data={"surveil_count": count}
    )
    state.pending_choice = choice
    return choice


def normalize_target(entry, state: GameState) -> tuple[str, bool]:
    """Normalize a target entry to (target_id, is_player).

    Phase 5b: cast-time target picking emits raw IDs via PendingChoice
    handlers, whereas AI ``_select_targets_for_spell`` and the server
    ``_coerce_action_targets`` path both pre-supply ``Target`` instances.
    Card resolve_fns that opt into ``target_requirements`` need to handle
    both shapes — this helper does the lookup in one place.

    Returns:
        ``(target_id, is_player)`` regardless of whether the input was a
        ``Target`` dataclass, a ``{"id": ...}`` dict, or a raw string ID.
    """
    target_id = getattr(entry, "id", None)
    if target_id is None and isinstance(entry, dict):
        target_id = entry.get("id") or entry.get("target_id")
    if target_id is None:
        target_id = entry  # assume a string ID
    target_id = str(target_id)

    is_player = getattr(entry, "is_player", None)
    if is_player is None:
        is_player = target_id in state.players
    return target_id, bool(is_player)


def create_target_choice(
    state: GameState,
    player_id: str,
    source_id: str,
    legal_targets: list[str],
    prompt: str = "Choose a target",
    min_targets: int = 1,
    max_targets: int = 1,
    callback_data: dict = None
) -> PendingChoice:
    """
    Create a target selection choice.

    Args:
        state: The game state
        player_id: Player choosing targets
        source_id: Card/ability that needs targets
        legal_targets: List of valid target IDs
        prompt: UI prompt text
        min_targets: Minimum targets required
        max_targets: Maximum targets allowed
        callback_data: Additional data for when choice resolves

    Example:
        # ETB ability: "Exile target creature"
        legal = get_legal_creature_targets(state, controller_id)
        choice = create_target_choice(
            state, controller_id, permanent_id,
            legal_targets=legal,
            prompt="Choose a creature to exile"
        )
    """
    choice = PendingChoice(
        choice_type="target",
        player=player_id,
        prompt=prompt,
        options=legal_targets,
        source_id=source_id,
        min_choices=min_targets,
        max_choices=max_targets,
        callback_data=callback_data or {}
    )
    state.pending_choice = choice
    return choice


def create_discard_choice(
    state: GameState,
    player_id: str,
    source_id: str,
    card_ids: list[str],
    discard_count: int,
    prompt: str = None
) -> PendingChoice:
    """
    Create a discard choice.

    Args:
        state: The game state
        player_id: Player who must discard
        source_id: Card/ability causing the discard
        card_ids: IDs of cards in player's hand
        discard_count: Number of cards to discard

    Example:
        # "Discard two cards"
        hand_ids = [c.id for c in get_hand(player_id)]
        choice = create_discard_choice(state, player_id, source_id, hand_ids, 2)
    """
    choice = PendingChoice(
        choice_type="discard",
        player=player_id,
        prompt=prompt or f"Choose {discard_count} card(s) to discard",
        options=card_ids,
        source_id=source_id,
        min_choices=min(discard_count, len(card_ids)),
        max_choices=min(discard_count, len(card_ids))
    )
    state.pending_choice = choice
    return choice


def create_sacrifice_choice(
    state: GameState,
    player_id: str,
    source_id: str,
    permanent_ids: list[str],
    sacrifice_count: int,
    prompt: str = None
) -> PendingChoice:
    """
    Create a sacrifice choice.

    Args:
        state: The game state
        player_id: Player who must sacrifice
        source_id: Card/ability causing the sacrifice
        permanent_ids: IDs of permanents that can be sacrificed
        sacrifice_count: Number of permanents to sacrifice

    Example:
        # "Sacrifice a creature"
        creature_ids = [c.id for c in get_creatures_you_control(state, player_id)]
        choice = create_sacrifice_choice(state, player_id, source_id, creature_ids, 1)
    """
    choice = PendingChoice(
        choice_type="sacrifice",
        player=player_id,
        prompt=prompt or f"Choose {sacrifice_count} permanent(s) to sacrifice",
        options=permanent_ids,
        source_id=source_id,
        min_choices=min(sacrifice_count, len(permanent_ids)),
        max_choices=min(sacrifice_count, len(permanent_ids))
    )
    state.pending_choice = choice
    return choice


def create_may_choice(
    state: GameState,
    player_id: str,
    source_id: str,
    prompt: str,
    yes_handler: Callable[['PendingChoice', GameState], list[Event]] = None,
    no_handler: Callable[['PendingChoice', GameState], list[Event]] = None
) -> PendingChoice:
    """
    Create a "you may" choice.

    Args:
        state: The game state
        player_id: Player making the choice
        source_id: Card/ability offering the choice
        prompt: Question text (e.g., "Pay {2} to draw a card?")
        yes_handler: Function to call if player chooses yes
        no_handler: Function to call if player chooses no

    Example:
        # "You may pay {2}. If you do, draw a card."
        choice = create_may_choice(
            state, player_id, source_id,
            prompt="Pay {2} to draw a card?",
            yes_handler=lambda c, s: pay_and_draw(c, s)
        )
    """
    choice = PendingChoice(
        choice_type="may",
        player=player_id,
        prompt=prompt,
        options=[True, False],  # Yes or No
        source_id=source_id,
        min_choices=1,
        max_choices=1,
        callback_data={
            'yes_handler': yes_handler,
            'no_handler': no_handler
        }
    )
    state.pending_choice = choice
    return choice


def create_order_choice(
    state: GameState,
    player_id: str,
    source_id: str,
    card_ids: list[str],
    destination: str = "library_top",
    prompt: str = None
) -> PendingChoice:
    """
    Create a card ordering choice.

    Args:
        state: The game state
        player_id: Player ordering the cards
        source_id: Card/ability causing the ordering
        card_ids: IDs of cards to order
        destination: Where cards go ("library_top", "library_bottom", etc.)
        prompt: UI prompt text

    Example:
        # "Put them back in any order"
        choice = create_order_choice(
            state, player_id, source_id,
            card_ids=revealed_cards,
            prompt="Put these cards on top of your library in any order"
        )
    """
    choice = PendingChoice(
        choice_type="order",
        player=player_id,
        prompt=prompt or f"Arrange these {len(card_ids)} cards in order",
        options=card_ids,
        source_id=source_id,
        min_choices=len(card_ids),
        max_choices=len(card_ids),
        callback_data={"destination": destination}
    )
    state.pending_choice = choice
    return choice


def create_hand_reveal_choice(
    state: GameState,
    choosing_player_id: str,
    source_id: str,
    target_player_id: str,
    card_filter: Callable[[GameObject], bool] = None,
    min_choices: int = 1,
    max_choices: int = 1,
    prompt: str = None,
    handler: Callable = None,
    callback_data: dict = None
) -> PendingChoice:
    """
    Create a choice for revealing a player's hand and selecting cards from it.

    Args:
        state: The game state
        choosing_player_id: Player who makes the choice (typically the caster)
        source_id: Card/ability that needs the choice
        target_player_id: Player whose hand is being revealed
        card_filter: Optional filter function(card) -> bool for valid choices
        min_choices: Minimum cards to choose (0 for "may" effects)
        max_choices: Maximum cards to choose
        prompt: UI prompt text
        handler: Callback function(choice, selected, state) -> list[Event]
        callback_data: Additional data for when choice resolves

    Example:
        # Duress: Choose a noncreature, nonland card
        def noncreature_nonland(card):
            types = card.characteristics.types
            return CardType.CREATURE not in types and CardType.LAND not in types

        choice = create_hand_reveal_choice(
            state, caster_id, spell_id, opponent_id,
            card_filter=noncreature_nonland,
            handler=lambda c, s, gs: [Event(type=EventType.DISCARD, ...)]
        )
    """
    hand_key = f"hand_{target_player_id}"
    if hand_key not in state.zones:
        return None

    hand = state.zones[hand_key]
    valid_choices = []

    for card_id in hand.objects:
        card = state.objects.get(card_id)
        if card:
            if card_filter is None or card_filter(card):
                valid_choices.append(card_id)

    if not valid_choices and min_choices > 0:
        # No valid targets and selection is required - cannot create choice
        return None

    # Build callback data
    cb_data = callback_data.copy() if callback_data else {}
    cb_data['target_player'] = target_player_id
    if handler:
        cb_data['handler'] = handler

    choice = PendingChoice(
        choice_type="hand_reveal",
        player=choosing_player_id,
        prompt=prompt or "Choose a card from opponent's hand",
        options=valid_choices,
        source_id=source_id,
        min_choices=min(min_choices, len(valid_choices)),
        max_choices=min(max_choices, len(valid_choices)),
        callback_data=cb_data
    )
    state.pending_choice = choice
    return choice


# =============================================================================
# LEAVES-THE-BATTLEFIELD TRIGGER
# =============================================================================

def make_leaves_battlefield_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None
) -> Interceptor:
    """
    Create a leaves-the-battlefield trigger interceptor.

    Args:
        source_obj: The object with the trigger
        effect_fn: Function(event, state) -> list[Event] to execute when trigger fires
        filter_fn: Optional custom filter

    Event: ZONE_CHANGE with from_zone_type == BATTLEFIELD and object_id == source_obj.id
    Priority: REACT
    """
    def default_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        return True

    actual_filter = filter_fn or default_filter

    def trigger_filter(event: Event, state: GameState) -> bool:
        return actual_filter(event, state, source_obj)

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='until_leaves'  # Fire once when leaving
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Leaves-battlefield trigger")


# =============================================================================
# TARGETED TRIGGER HELPERS
# =============================================================================
# These helpers emit TARGET_REQUIRED events, letting the pipeline handle
# target selection and effect execution automatically.

def make_targeted_etb_trigger(
    source_obj: GameObject,
    effect: str,
    effect_params: dict = None,
    target_filter: str = 'any',
    min_targets: int = 1,
    max_targets: int = 1,
    optional: bool = False,
    prompt: str = None
) -> Interceptor:
    """
    Create an ETB trigger that requires targeting.

    Args:
        source_obj: The object with the trigger
        effect: Effect type ('damage', 'destroy', 'exile', 'bounce', 'tap', 'pump', etc.)
        effect_params: Parameters for the effect (e.g., {'amount': 3} for damage)
        target_filter: Target filter type ('any', 'creature', 'opponent_creature',
                       'your_creature', 'opponent', 'player', 'nonland_permanent')
        min_targets: Minimum targets required (default 1)
        max_targets: Maximum targets allowed (default 1)
        optional: If True, may choose 0 targets (default False)
        prompt: Custom prompt text (auto-generated if not provided)

    Example:
        # "When ~ enters, deal 2 damage to any target"
        make_targeted_etb_trigger(obj, effect='damage', effect_params={'amount': 2})

        # "When ~ enters, exile target creature an opponent controls"
        make_targeted_etb_trigger(obj, effect='exile', target_filter='opponent_creature')
    """
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': source_obj.id,
                'controller': source_obj.controller,
                'effect': effect,
                'effect_params': effect_params or {},
                'target_filter': target_filter,
                'min_targets': min_targets,
                'max_targets': max_targets,
                'optional': optional,
                'prompt': prompt
            },
            source=source_obj.id
        )]

    return make_etb_trigger(source_obj, etb_effect)


def make_targeted_attack_trigger(
    source_obj: GameObject,
    effect: str,
    effect_params: dict = None,
    target_filter: str = 'any',
    min_targets: int = 1,
    max_targets: int = 1,
    optional: bool = False,
    prompt: str = None
) -> Interceptor:
    """
    Create an attack trigger that requires targeting.

    Args:
        source_obj: The creature with the trigger
        effect: Effect type ('damage', 'destroy', 'exile', 'bounce', 'tap', 'pump', etc.)
        effect_params: Parameters for the effect (e.g., {'amount': 2} for damage)
        target_filter: Target filter type
        min_targets: Minimum targets required (default 1)
        max_targets: Maximum targets allowed (default 1)
        optional: If True, may choose 0 targets (default False)
        prompt: Custom prompt text (auto-generated if not provided)

    Example:
        # "When ~ attacks, deal 2 damage to any target"
        make_targeted_attack_trigger(obj, effect='damage', effect_params={'amount': 2})

        # "When ~ attacks, tap target creature an opponent controls"
        make_targeted_attack_trigger(obj, effect='tap', target_filter='opponent_creature')
    """
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': source_obj.id,
                'controller': source_obj.controller,
                'effect': effect,
                'effect_params': effect_params or {},
                'target_filter': target_filter,
                'min_targets': min_targets,
                'max_targets': max_targets,
                'optional': optional,
                'prompt': prompt
            },
            source=source_obj.id
        )]

    return make_attack_trigger(source_obj, attack_effect)


def make_targeted_death_trigger(
    source_obj: GameObject,
    effect: str,
    effect_params: dict = None,
    target_filter: str = 'any',
    min_targets: int = 1,
    max_targets: int = 1,
    optional: bool = False,
    prompt: str = None
) -> Interceptor:
    """
    Create a death trigger that requires targeting.

    Args:
        source_obj: The creature with the trigger
        effect: Effect type ('damage', 'destroy', 'exile', 'bounce', 'tap', 'pump', etc.)
        effect_params: Parameters for the effect (e.g., {'amount': 4} for damage)
        target_filter: Target filter type
        min_targets: Minimum targets required (default 1)
        max_targets: Maximum targets allowed (default 1)
        optional: If True, may choose 0 targets (default False)
        prompt: Custom prompt text (auto-generated if not provided)

    Example:
        # "When ~ dies, deal 4 damage to any target"
        make_targeted_death_trigger(obj, effect='damage', effect_params={'amount': 4})
    """
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': source_obj.id,
                'controller': source_obj.controller,
                'effect': effect,
                'effect_params': effect_params or {},
                'target_filter': target_filter,
                'min_targets': min_targets,
                'max_targets': max_targets,
                'optional': optional,
                'prompt': prompt
            },
            source=source_obj.id
        )]

    return make_death_trigger(source_obj, death_effect)


def make_targeted_damage_trigger(
    source_obj: GameObject,
    effect: str,
    effect_params: dict = None,
    target_filter: str = 'any',
    min_targets: int = 1,
    max_targets: int = 1,
    optional: bool = False,
    prompt: str = None,
    combat_only: bool = False,
    noncombat_only: bool = False
) -> Interceptor:
    """
    Create a damage trigger that requires targeting.

    Args:
        source_obj: The creature with the trigger
        effect: Effect type ('damage', 'destroy', 'exile', 'bounce', etc.)
        effect_params: Parameters for the effect
        target_filter: Target filter type
        min_targets: Minimum targets required (default 1)
        max_targets: Maximum targets allowed (default 1)
        optional: If True, may choose 0 targets (default False)
        prompt: Custom prompt text (auto-generated if not provided)
        combat_only: If True, only trigger on combat damage
        noncombat_only: If True, only trigger on noncombat damage

    Example:
        # "When ~ deals combat damage, destroy target creature"
        make_targeted_damage_trigger(obj, effect='destroy', target_filter='creature',
                                     combat_only=True)
    """
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': source_obj.id,
                'controller': source_obj.controller,
                'effect': effect,
                'effect_params': effect_params or {},
                'target_filter': target_filter,
                'min_targets': min_targets,
                'max_targets': max_targets,
                'optional': optional,
                'prompt': prompt
            },
            source=source_obj.id
        )]

    return make_damage_trigger(source_obj, damage_effect, combat_only=combat_only,
                               noncombat_only=noncombat_only)


def make_targeted_spell_cast_trigger(
    source_obj: GameObject,
    effect: str,
    effect_params: dict = None,
    target_filter: str = 'any',
    min_targets: int = 1,
    max_targets: int = 1,
    optional: bool = False,
    prompt: str = None,
    controller_only: bool = True,
    spell_type_filter: set = None,
    color_filter: set = None
) -> Interceptor:
    """
    Create a spell cast trigger that requires targeting.

    Args:
        source_obj: The object with the trigger
        effect: Effect type ('damage', 'destroy', 'exile', etc.)
        effect_params: Parameters for the effect
        target_filter: Target filter type
        min_targets: Minimum targets required (default 1)
        max_targets: Maximum targets allowed (default 1)
        optional: If True, may choose 0 targets (default False)
        prompt: Custom prompt text (auto-generated if not provided)
        controller_only: If True, only trigger on spells cast by controller
        spell_type_filter: Only trigger on specific spell types (e.g., {CardType.INSTANT})
        color_filter: Only trigger on spells containing these colors

    Example:
        # "When you cast an instant or sorcery, deal 1 damage to any target"
        make_targeted_spell_cast_trigger(
            obj, effect='damage', effect_params={'amount': 1},
            spell_type_filter={CardType.INSTANT, CardType.SORCERY}
        )
    """
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': source_obj.id,
                'controller': source_obj.controller,
                'effect': effect,
                'effect_params': effect_params or {},
                'target_filter': target_filter,
                'min_targets': min_targets,
                'max_targets': max_targets,
                'optional': optional,
                'prompt': prompt
            },
            source=source_obj.id
        )]

    return make_spell_cast_trigger(
        source_obj, spell_effect,
        controller_only=controller_only,
        spell_type_filter=spell_type_filter,
        color_filter=color_filter
    )


# =============================================================================
# DIVIDED DAMAGE/COUNTERS HELPERS
# =============================================================================

def make_divided_damage_etb_trigger(
    source_obj: GameObject,
    damage_amount: int,
    target_filter: str = 'any',
    max_targets: int = None,
    prompt: str = None
) -> Interceptor:
    """
    Create an ETB trigger that deals damage divided as you choose among targets.

    Example: "When ~ enters, deal 5 damage divided as you choose among any number of targets."

    Args:
        source_obj: The object with the trigger
        damage_amount: Total damage to divide (e.g., 5)
        target_filter: Target filter type ('any', 'creature', 'opponent_creature', etc.)
        max_targets: Max targets to select (default: damage_amount, since you must deal at least 1 each)
        prompt: Custom prompt text

    Returns:
        An ETB trigger interceptor
    """
    actual_max = max_targets if max_targets is not None else damage_amount

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': source_obj.id,
                'controller': source_obj.controller,
                'effect': 'damage',
                'effect_params': {},  # Amount comes from divide_amount
                'target_filter': target_filter,
                'min_targets': 1,  # Must have at least 1 target
                'max_targets': actual_max,
                'optional': False,
                'divide_amount': damage_amount,
                'prompt': prompt or f"Deal {damage_amount} damage divided as you choose among any number of targets"
            },
            source=source_obj.id
        )]

    return make_etb_trigger(source_obj, etb_effect)


def make_divided_counters_etb_trigger(
    source_obj: GameObject,
    counter_amount: int,
    counter_type: str = '+1/+1',
    target_filter: str = 'creature',
    max_targets: int = None,
    prompt: str = None
) -> Interceptor:
    """
    Create an ETB trigger that puts counters divided as you choose among targets.

    Example: "When ~ enters, distribute 3 +1/+1 counters among any number of target creatures."

    Args:
        source_obj: The object with the trigger
        counter_amount: Total counters to distribute
        counter_type: Type of counter (default: '+1/+1')
        target_filter: Target filter type
        max_targets: Max targets to select
        prompt: Custom prompt text

    Returns:
        An ETB trigger interceptor
    """
    actual_max = max_targets if max_targets is not None else counter_amount

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': source_obj.id,
                'controller': source_obj.controller,
                'effect': 'counter_add',
                'effect_params': {'counter_type': counter_type},
                'target_filter': target_filter,
                'min_targets': 1,
                'max_targets': actual_max,
                'optional': False,
                'divide_amount': counter_amount,
                'prompt': prompt or f"Distribute {counter_amount} {counter_type} counters among any number of target creatures"
            },
            source=source_obj.id
        )]

    return make_etb_trigger(source_obj, etb_effect)


# =============================================================================
# MULTI-EFFECT TARGETING HELPERS
# =============================================================================

def make_targeted_multi_effect_etb_trigger(
    source_obj: GameObject,
    effects: list[dict],
    target_filter: str = 'creature',
    min_targets: int = 1,
    max_targets: int = 1,
    optional: bool = False,
    prompt: str = None
) -> Interceptor:
    """
    Create an ETB trigger that applies multiple effects to targeted creature(s).

    Example: "When ~ enters, tap target creature. It doesn't untap during its controller's next untap step."

    Args:
        source_obj: The object with the trigger
        effects: List of effect dicts [{'effect': 'tap'}, {'effect': 'stun'}]
        target_filter: Target filter type
        min_targets: Minimum targets
        max_targets: Maximum targets
        optional: If True, may choose 0 targets
        prompt: Custom prompt text

    Supported effects:
        - 'tap' - Tap target
        - 'untap' - Untap target
        - 'stun' - Add stun counter (doesn't untap next untap step)
        - 'freeze' - Tap + stun combo
        - 'damage' with params: {'amount': N}
        - 'pump' with params: {'power_mod': N, 'toughness_mod': M}
        - 'counter_add' with params: {'counter_type': str, 'amount': N}
        - 'grant_keyword' with params: {'keyword': str}

    Returns:
        An ETB trigger interceptor
    """
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': source_obj.id,
                'controller': source_obj.controller,
                'effects': effects,  # Multi-effect list
                'target_filter': target_filter,
                'min_targets': min_targets,
                'max_targets': max_targets,
                'optional': optional,
                'prompt': prompt
            },
            source=source_obj.id
        )]

    return make_etb_trigger(source_obj, etb_effect)


def make_targeted_multi_effect_attack_trigger(
    source_obj: GameObject,
    effects: list[dict],
    target_filter: str = 'creature',
    min_targets: int = 1,
    max_targets: int = 1,
    optional: bool = False,
    prompt: str = None
) -> Interceptor:
    """
    Create an attack trigger that applies multiple effects to targeted creature(s).

    Args:
        source_obj: The creature with the trigger
        effects: List of effect dicts
        target_filter: Target filter type
        min_targets: Minimum targets
        max_targets: Maximum targets
        optional: If True, may choose 0 targets
        prompt: Custom prompt text

    Returns:
        An attack trigger interceptor
    """
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': source_obj.id,
                'controller': source_obj.controller,
                'effects': effects,
                'target_filter': target_filter,
                'min_targets': min_targets,
                'max_targets': max_targets,
                'optional': optional,
                'prompt': prompt
            },
            source=source_obj.id
        )]

    return make_attack_trigger(source_obj, attack_effect)


# =============================================================================
# MODAL WITH TARGETING HELPERS
# =============================================================================

def make_modal_etb_trigger(
    source_obj: GameObject,
    modes: list[dict],
    min_modes: int = 1,
    max_modes: int = 1,
    prompt: str = None
) -> Interceptor:
    """
    Create an ETB trigger with modal choices, where some modes may require targeting.

    Example: "When ~ enters, choose one: Tap target creature; or Untap target creature."

    Args:
        source_obj: The object with the trigger
        modes: List of mode dicts, each with:
            - 'text': str - Description shown in UI
            - 'requires_targeting': bool - Whether this mode needs targets
            - 'effect': str - Effect type (for non-targeting or single-effect modes)
            - 'effects': list - Multi-effect list (overrides 'effect')
            - 'effect_params': dict - Parameters for the effect
            - 'target_filter': str - Target filter (only if requires_targeting)
            - 'min_targets': int - Min targets (default 1)
            - 'max_targets': int - Max targets (default 1)
            - 'optional': bool - If targets are optional
        min_modes: Minimum modes to choose (default 1)
        max_modes: Maximum modes to choose (default 1, use 2+ for "choose two")
        prompt: Custom prompt text

    Returns:
        An ETB trigger interceptor

    Example modes:
        modes=[
            {'text': 'Tap target creature', 'requires_targeting': True,
             'effect': 'tap', 'target_filter': 'creature'},
            {'text': 'Untap target creature', 'requires_targeting': True,
             'effect': 'untap', 'target_filter': 'creature'},
            {'text': 'Draw a card', 'requires_targeting': False,
             'effect': 'draw', 'effect_params': {'amount': 1}},
        ]
    """
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Build options for UI
        options = []
        for i, mode in enumerate(modes):
            options.append({
                'id': str(i),
                'index': i,
                'label': mode.get('text', f'Mode {i + 1}'),
                'description': mode.get('description', ''),
                'requires_targeting': mode.get('requires_targeting', False)
            })

        # Create modal choice
        choice = PendingChoice(
            choice_type="modal_with_targeting",
            player=source_obj.controller,
            prompt=prompt or "Choose a mode:",
            options=options,
            source_id=source_obj.id,
            min_choices=min_modes,
            max_choices=max_modes,
            callback_data={
                'modes': modes,
                'controller': source_obj.controller
            }
        )
        state.pending_choice = choice
        return []  # Choice processing is handled when player submits

    return make_etb_trigger(source_obj, etb_effect)


# =============================================================================
# HEARTHSTONE-SPECIFIC HELPERS
# =============================================================================

def other_friendly_minions(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter: Other minions you control (HS uses MINION, not CREATURE)."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.id != source.id and
                target.controller == source.controller and
                CardType.MINION in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def friendly_minions(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter: All minions you control including self."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.controller == source.controller and
                CardType.MINION in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def friendly_minions_with_subtype(source: GameObject, subtype: str) -> Callable[[GameObject, GameState], bool]:
    """Filter: Your minions with the given subtype."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.controller == source.controller and
                CardType.MINION in target.characteristics.types and
                subtype in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def other_friendly_minions_with_subtype(source: GameObject, subtype: str) -> Callable[[GameObject, GameState], bool]:
    """Filter: Other minions you control with the given subtype."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.id != source.id and
                target.controller == source.controller and
                CardType.MINION in target.characteristics.types and
                subtype in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def get_enemy_targets(obj: GameObject, state: GameState) -> list[str]:
    """Get all valid enemy targets (hero + minions) for targeting effects."""
    enemies = []
    for pid, player in state.players.items():
        if pid != obj.controller and player.hero_id:
            enemies.append(player.hero_id)
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if m and m.controller != obj.controller and CardType.MINION in m.characteristics.types:
                enemies.append(mid)
    return enemies


def get_all_targets(obj: GameObject, state: GameState) -> list[str]:
    """Get all valid targets (all heroes + all minions) for targeting effects."""
    targets = []
    for pid, player in state.players.items():
        if player.hero_id:
            targets.append(player.hero_id)
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if m and CardType.MINION in m.characteristics.types:
                targets.append(mid)
    return targets


def get_friendly_minions(obj: GameObject, state: GameState, exclude_self: bool = True) -> list[str]:
    """Get all friendly minion IDs on the battlefield."""
    minions = []
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if m and m.controller == obj.controller and CardType.MINION in m.characteristics.types:
                if not exclude_self or m.id != obj.id:
                    minions.append(mid)
    return minions


def get_enemy_minions(obj: GameObject, state: GameState) -> list[str]:
    """Get all enemy minion IDs on the battlefield."""
    minions = []
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if m and m.controller != obj.controller and CardType.MINION in m.characteristics.types:
                minions.append(mid)
    return minions


def get_all_minions(state: GameState) -> list[str]:
    """Get all minion IDs on the battlefield."""
    minions = []
    battlefield = state.zones.get('battlefield')
    if battlefield:
        for mid in battlefield.objects:
            m = state.objects.get(mid)
            if m and CardType.MINION in m.characteristics.types:
                minions.append(mid)
    return minions


def get_enemy_hero_id(obj: GameObject, state: GameState) -> str | None:
    """Get the opponent's hero object ID."""
    for pid, player in state.players.items():
        if pid != obj.controller and player.hero_id:
            return player.hero_id
    return None


def make_enrage_trigger(
    source_obj: GameObject,
    attack_bonus: int = 0,
    keywords: set[str] | None = None
) -> list[Interceptor]:
    """
    Create an Enrage effect: while damaged, gain +attack and/or keywords.

    Works via QUERY interceptors that check obj.state.damage > 0.
    """
    interceptors = []
    source_id = source_obj.id

    if attack_bonus > 0:
        def enrage_power_filter(event: Event, state: GameState) -> bool:
            if event.type != EventType.QUERY_POWER:
                return False
            if event.payload.get('object_id') != source_id:
                return False
            source = state.objects.get(source_id)
            return bool(source and source.zone == ZoneType.BATTLEFIELD and source.state.damage > 0)

        def enrage_power_handler(event: Event, state: GameState) -> InterceptorResult:
            current = event.payload.get('value', 0)
            new_event = event.copy()
            new_event.payload['value'] = current + attack_bonus
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event
            )

        interceptors.append(Interceptor(
            id=new_id(),
            source=source_obj.id,
            controller=source_obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=enrage_power_filter,
            handler=enrage_power_handler,
            duration='while_on_battlefield'
        ))

    if keywords:
        def enrage_ability_filter(event: Event, state: GameState) -> bool:
            if event.type != EventType.QUERY_ABILITIES:
                return False
            if event.payload.get('object_id') != source_id:
                return False
            source = state.objects.get(source_id)
            return bool(source and source.zone == ZoneType.BATTLEFIELD and source.state.damage > 0)

        def enrage_ability_handler(event: Event, state: GameState) -> InterceptorResult:
            new_event = event.copy()
            granted = list(new_event.payload.get('granted', []))
            for kw in keywords:
                if kw not in granted:
                    granted.append(kw)
            new_event.payload['granted'] = granted
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event
            )

        interceptors.append(Interceptor(
            id=new_id(),
            source=source_obj.id,
            controller=source_obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=enrage_ability_filter,
            handler=enrage_ability_handler,
            duration='while_on_battlefield'
        ))

    return interceptors


def make_spell_damage_boost(source_obj: GameObject, amount: int = 1) -> Interceptor:
    """
    Create a Spell Damage +N interceptor.

    Increases damage from spells controlled by the same player by +N.
    """
    source_id = source_obj.id

    def spell_dmg_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('from_spell'):
            return False
        # Only boost spells from same controller
        source = state.objects.get(event.source)
        if not source:
            return False
        # Check source minion is still on battlefield
        boost_source = state.objects.get(source_id)
        if not boost_source or boost_source.zone != ZoneType.BATTLEFIELD:
            return False
        return source.controller == boost_source.controller

    def spell_dmg_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['amount'] = event.payload.get('amount', 0) + amount
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=spell_dmg_filter,
        handler=spell_dmg_handler,
        duration='while_on_battlefield'
    )


def make_end_of_turn_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    controller_only: bool = True
) -> Interceptor:
    """Create an end-of-turn trigger (HS: fires at PHASE_END with phase='end')."""
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_END:
            return False
        if event.payload.get('phase') != 'end':
            return False
        if controller_only and event.payload.get('player') != source_obj.controller:
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="End-of-turn trigger")


def make_start_of_turn_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    controller_only: bool = True
) -> Interceptor:
    """Create a start-of-turn trigger (HS: fires at TURN_START)."""
    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.TURN_START:
            return False
        if controller_only and event.payload.get('player') != source_obj.controller:
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Start-of-turn trigger")


def make_whenever_healed_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    self_only: bool = True
) -> Interceptor:
    """Create a 'whenever this minion is healed' trigger."""
    source_id = source_obj.id

    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        amount = event.payload.get('amount', 0)
        if amount <= 0:
            return False
        if self_only:
            return event.payload.get('target') == source_id
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Healed trigger")


def make_whenever_takes_damage_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
) -> Interceptor:
    """Create a 'whenever this minion takes damage' trigger."""
    source_id = source_obj.id

    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        return event.payload.get('target') == source_id

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield'
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Takes-damage trigger")


def make_modal_spell_trigger(
    source_obj: GameObject,
    modes: list[dict],
    min_modes: int = 1,
    max_modes: int = 1,
    prompt: str = None,
    spell_type_filter: set = None,
    controller_only: bool = True
) -> Interceptor:
    """
    Create a spell cast trigger with modal choices.

    Similar to make_modal_etb_trigger but triggers on spell cast.

    Args:
        source_obj: The object with the trigger
        modes: List of mode dicts (same format as make_modal_etb_trigger)
        min_modes: Minimum modes to choose
        max_modes: Maximum modes to choose
        prompt: Custom prompt text
        spell_type_filter: Only trigger on specific spell types
        controller_only: Only trigger on controller's spells

    Returns:
        A spell cast trigger interceptor
    """
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        options = []
        for i, mode in enumerate(modes):
            options.append({
                'id': str(i),
                'index': i,
                'label': mode.get('text', f'Mode {i + 1}'),
                'description': mode.get('description', ''),
                'requires_targeting': mode.get('requires_targeting', False)
            })

        choice = PendingChoice(
            choice_type="modal_with_targeting",
            player=source_obj.controller,
            prompt=prompt or "Choose a mode:",
            options=options,
            source_id=source_obj.id,
            min_choices=min_modes,
            max_choices=max_modes,
            callback_data={
                'modes': modes,
                'controller': source_obj.controller
            }
        )
        state.pending_choice = choice
        return []

    return make_spell_cast_trigger(
        source_obj, spell_effect,
        controller_only=controller_only,
        spell_type_filter=spell_type_filter
    )


# =============================================================================
# Hearthstone Board Adjacency
# =============================================================================

def get_adjacent_minions(obj_id: str, state) -> tuple[str | None, str | None]:
    """
    Get the minion IDs adjacent (left and right) to obj_id on the battlefield.
    Returns (left_id, right_id) — either may be None if at the edge or no neighbor.
    Only considers minions controlled by the same player.
    """
    obj = state.objects.get(obj_id)
    if not obj:
        return (None, None)

    battlefield = state.zones.get('battlefield')
    if not battlefield:
        return (None, None)

    # Build ordered list of minions for this controller
    controller_minions = []
    for mid in battlefield.objects:
        m = state.objects.get(mid)
        if m and m.controller == obj.controller and CardType.MINION in m.characteristics.types:
            controller_minions.append(mid)

    if obj_id not in controller_minions:
        return (None, None)

    idx = controller_minions.index(obj_id)
    left = controller_minions[idx - 1] if idx > 0 else None
    right = controller_minions[idx + 1] if idx < len(controller_minions) - 1 else None
    return (left, right)


def get_adjacent_enemy_minions(target_id: str, state) -> list[str]:
    """
    Get the enemy minion IDs adjacent to target_id on the battlefield.
    Used for Cone of Cold, Betrayal, etc. where we target an enemy minion
    and need its neighbors (among the enemy's board).
    Returns list of adjacent IDs (0-2 elements).
    """
    target = state.objects.get(target_id)
    if not target:
        return []

    battlefield = state.zones.get('battlefield')
    if not battlefield:
        return []

    # Build ordered list of minions for the target's controller
    controller_minions = []
    for mid in battlefield.objects:
        m = state.objects.get(mid)
        if m and m.controller == target.controller and CardType.MINION in m.characteristics.types:
            controller_minions.append(mid)

    if target_id not in controller_minions:
        return []

    idx = controller_minions.index(target_id)
    adjacent = []
    if idx > 0:
        adjacent.append(controller_minions[idx - 1])
    if idx < len(controller_minions) - 1:
        adjacent.append(controller_minions[idx + 1])
    return adjacent


# =============================================================================
# Hearthstone Cost Reduction Helpers
# =============================================================================

def make_cost_reduction_aura(obj, card_type_filter, amount, floor=0, state=None):
    """
    Create interceptors that add/remove a cost modifier while obj is on the battlefield.

    Directly applies the modifier immediately (setup_interceptors is only called
    when the object enters the battlefield), and registers cleanup interceptors
    for when it leaves.

    Args:
        obj: The source minion (e.g. Sorcerer's Apprentice)
        card_type_filter: CardType to reduce cost for (e.g. CardType.SPELL)
        amount: How much to reduce (positive = reduce, negative = increase)
        floor: Minimum cost (0 for most, 1 for Summoning Portal)
        state: GameState — used to directly add the modifier

    Returns list of Interceptors.
    """
    modifier_id = f"aura_{obj.id}"

    # Directly add the cost modifier now — setup_interceptors is only called
    # when the object is on the battlefield, so no need for an ETB interceptor.
    if state:
        player = state.players.get(obj.controller)
        if player:
            player.cost_modifiers.append({
                'id': modifier_id,
                'card_type': card_type_filter,
                'amount': amount,
                'duration': 'while_on_battlefield',
                'source': obj.id,
                'floor': floor,
            })

    def leave_filter(event, state) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        return (event.payload.get('object_id') == obj.id and
                event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD and
                event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD)

    def remove_modifier(event, state):
        player = state.players.get(obj.controller)
        if player:
            player.cost_modifiers = [m for m in player.cost_modifiers if m.get('id') != modifier_id]
        return InterceptorResult(action=InterceptorAction.PASS)

    def death_filter(event, state) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        return event.payload.get('object_id') == obj.id

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=leave_filter,
            handler=remove_modifier,
            duration='permanent'
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=death_filter,
            handler=remove_modifier,
            duration='permanent'
        ),
    ]


def make_cant_attack(source_obj: GameObject) -> Interceptor:
    """
    Create a "Can't Attack" interceptor (HS: Ancient Watcher, Ragnaros).
    PREVENT interceptor on ATTACK_DECLARED when attacker is this object.
    Also marks the object with a 'cant_attack' keyword so has_ability() can find it.
    """
    # Mark with keyword so has_ability('cant_attack', ...) returns True
    if not any(a.get('keyword') == 'cant_attack' for a in source_obj.characteristics.abilities):
        source_obj.characteristics.abilities.append({'keyword': 'cant_attack'})

    source_id = source_obj.id

    def cant_attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        return event.payload.get('attacker_id') == source_id

    def cant_attack_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    return Interceptor(
        id=new_id(),
        source=source_id,
        controller=source_obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=cant_attack_filter,
        handler=cant_attack_handler,
        duration='while_on_battlefield'
    )


def add_one_shot_cost_reduction(player, card_type_filter, amount, duration='this_turn'):
    """
    Add a one-shot cost reduction modifier to a player.
    Used by Preparation ("next spell costs 3 less"), Kirin Tor Mage ("next Secret costs 0").

    Args:
        player: Player object to add modifier to
        card_type_filter: CardType to reduce (e.g. CardType.SPELL, CardType.SECRET)
        amount: How much to reduce
        duration: 'this_turn' (cleared at end of turn) or 'next_only' (consumed after one use)
    """
    player.cost_modifiers.append({
        'id': f"oneshot_{new_id()}",
        'card_type': card_type_filter,
        'amount': amount,
        'duration': duration,
        'uses_remaining': 1,
    })


# =============================================================================
# GAP-FILLER FILTERS (parity with src/engine/abilities/targets.py)
# =============================================================================

def all_creatures_filter() -> Callable[[GameObject, GameState], bool]:
    """Filter: Every creature on the battlefield (both players).

    Mirrors ``AllCreaturesFilter`` from the abilities DSL.
    """
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in target.characteristics.types)
    return filter_fn


def opponent_creatures_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter: Creatures controlled by opponents of ``source``'s controller.

    Mirrors ``OpponentCreaturesFilter`` from the abilities DSL.
    """
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.controller != source.controller and
                target.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in target.characteristics.types)
    return filter_fn


def nonland_permanents_filter() -> Callable[[GameObject, GameState], bool]:
    """Filter: Nonland permanents on the battlefield.

    Mirrors the ``NonlandPermanent`` trigger-target predicate.
    """
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.zone == ZoneType.BATTLEFIELD and
                CardType.LAND not in target.characteristics.types)
    return filter_fn


# =============================================================================
# GAP-FILLER INTERCEPTORS
# =============================================================================

def type_grant_interceptor(
    source_obj: GameObject,
    added_types: list[str],
    duration: str = 'while_on_battlefield',
    affects_filter: Optional[Callable[[GameObject, GameState], bool]] = None,
) -> Interceptor:
    """Create a QUERY_TYPES interceptor that adds subtypes to matching objects.

    Args:
        source_obj: The permanent granting the subtypes.
        added_types: List of subtype strings to inject (e.g. ``["Zombie"]``).
        duration: Interceptor duration tag (default: while_on_battlefield).
        affects_filter: Predicate ``(target, state) -> bool``. If omitted,
            grants to every object on the battlefield (same shape as TypeGrant
            with a permissive filter). Callers almost always want to pass a
            filter such as ``creatures_you_control(source_obj)``.

    Event: QUERY_TYPES. Transforms ``payload['subtypes']`` to include added_types.
    """
    source_id = source_obj.id
    types_to_add = list(added_types)
    filter_fn = affects_filter

    def type_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_TYPES:
            return False
        source = state.objects.get(source_id)
        if not source or source.zone != ZoneType.BATTLEFIELD:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        if filter_fn is None:
            return True
        return filter_fn(target, state)

    def type_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        subtypes = set(new_event.payload.get('subtypes', set()))
        for t in types_to_add:
            subtypes.add(t)
        new_event.payload['subtypes'] = subtypes
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=type_filter,
        handler=type_handler,
        duration=duration,
    )


def make_cant_block(
    source_obj: GameObject,
    filter_fn: Optional[Callable[[GameObject, GameState], bool]] = None,
) -> Interceptor:
    """Create a PREVENT interceptor on BLOCK_DECLARED.

    If ``filter_fn`` is None, prevents blocks only when the blocker *is*
    ``source_obj`` itself ("{this} can't block"). When given a filter, prevents
    any blocker matching the filter (lord-style "creatures you control can't
    block"). Mirrors ``CantBlockEffect`` from the abilities DSL.
    """
    source_id = source_obj.id
    predicate = filter_fn

    def cant_block_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.BLOCK_DECLARED:
            return False
        blocker_id = event.payload.get('blocker_id')
        if predicate is None:
            return blocker_id == source_id
        blocker = state.objects.get(blocker_id)
        if not blocker:
            return False
        return predicate(blocker, state)

    def cant_block_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=cant_block_filter,
        handler=cant_block_handler,
        duration='while_on_battlefield',
    )


# =============================================================================
# REPLACEMENT HELPERS
# =============================================================================
# Thin re-exports of the framework defined in src/engine/replacements.py so
# card files can import everything they need from interceptor_helpers in the
# usual way.

from src.engine.replacements import (  # noqa: E402  (re-export below)
    make_replacement_interceptor,
    make_life_gain_replacer,
    make_life_gain_prevention,
    make_draw_replacer,
    make_counter_doubler,
    make_dies_to_exile_replacer,
    make_damage_doubler,
    make_skip_to_graveyard_replacer,
    make_graveyard_to_exile_replacer,
)


# =============================================================================
# LIBRARY SEARCH HELPERS
# =============================================================================
#
# These wrap src/engine/library_search.py with card-friendly defaults. Cards
# typically just need an ETB-style "search your library for an X, put it into
# your hand, then shuffle." All of these helpers create a PendingChoice on
# state.pending_choice and return [] (no events) — the card's effect_fn should
# return whatever this helper returns.
#
# Example (Rune-Scarred Demon):
#     def runescarred_demon_setup(obj, state):
#         def effect_fn(event, state):
#             return open_library_search(
#                 state, obj.controller, obj.id,
#                 filter_fn=any_card_filter(),
#                 destination="hand",
#             )
#         return [make_etb_trigger(obj, effect_fn)]


def open_library_search(
    state: GameState,
    player_id: str,
    source_id: str,
    *,
    filter_fn: Optional[Callable[[GameObject, GameState], bool]] = None,
    min_count: int = 0,
    max_count: int = 1,
    destination: str = "hand",
    reveal: bool = False,
    shuffle_after: bool = True,
    tapped: bool = False,
    prompt: Optional[str] = None,
    optional: bool = True,
    on_chosen: Optional[Callable] = None,
    extra_callback_data: Optional[dict] = None,
) -> list[Event]:
    """Open a library-search PendingChoice. Returns [] (use as the effect_fn return).

    See `src.engine.library_search.create_library_search_choice` for full
    parameter documentation.
    """
    from src.engine.library_search import create_library_search_choice

    create_library_search_choice(
        state,
        player_id,
        source_id,
        filter_fn=filter_fn,
        min_count=min_count,
        max_count=max_count,
        destination=destination,
        reveal=reveal,
        shuffle_after=shuffle_after,
        tapped=tapped,
        prompt=prompt,
        optional=optional,
        on_chosen=on_chosen,
        extra_callback_data=extra_callback_data,
    )
    return []


def make_library_search_etb_trigger(
    source_obj: GameObject,
    *,
    filter_fn: Optional[Callable[[GameObject, GameState], bool]] = None,
    destination: str = "hand",
    reveal: bool = False,
    shuffle_after: bool = True,
    tapped: bool = False,
    max_count: int = 1,
    optional: bool = True,
    prompt: Optional[str] = None,
    on_chosen: Optional[Callable] = None,
) -> Interceptor:
    """Convenience: ETB trigger that opens a library search with the given filter.

    Common pattern for tutor creatures like Rune-Scarred Demon, Fierce Empath,
    Vile Entomber, Hoarding Dragon, Campus Guide, etc.
    """
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return open_library_search(
            state,
            source_obj.controller,
            source_obj.id,
            filter_fn=filter_fn,
            destination=destination,
            reveal=reveal,
            shuffle_after=shuffle_after,
            tapped=tapped,
            max_count=max_count,
            optional=optional,
            prompt=prompt,
            on_chosen=on_chosen,
        )
    return make_etb_trigger(source_obj, effect_fn)


# --- Library filter shortcuts (re-exports of the engine module's factories) ---

def basic_land_filter() -> Callable[[GameObject, GameState], bool]:
    """Filter: any basic land card."""
    from src.engine.library_search import is_basic_land
    return is_basic_land()


def basic_subtype_filter(subtype: str) -> Callable[[GameObject, GameState], bool]:
    """Filter: a basic with the given subtype (e.g. 'Forest', 'Mountain')."""
    from src.engine.library_search import is_basic_with_subtype
    return is_basic_with_subtype(subtype)


def creature_filter_lib() -> Callable[[GameObject, GameState], bool]:
    """Filter: any creature card."""
    from src.engine.library_search import is_card_type
    return is_card_type(CardType.CREATURE)


def artifact_filter_lib() -> Callable[[GameObject, GameState], bool]:
    """Filter: any artifact card."""
    from src.engine.library_search import is_card_type
    return is_card_type(CardType.ARTIFACT)


def enchantment_filter_lib() -> Callable[[GameObject, GameState], bool]:
    """Filter: any enchantment card."""
    from src.engine.library_search import is_card_type
    return is_card_type(CardType.ENCHANTMENT)


def creature_with_mv_at_least(min_mv: int) -> Callable[[GameObject, GameState], bool]:
    """Filter: creature card with mana value >= min_mv."""
    from src.engine.library_search import is_creature_with_mv_at_least
    return is_creature_with_mv_at_least(min_mv)


def instant_or_sorcery_with_mv(target_mv: int) -> Callable[[GameObject, GameState], bool]:
    """Filter: instant or sorcery with exactly target_mv mana value."""
    from src.engine.library_search import is_instant_or_sorcery_with_mv
    return is_instant_or_sorcery_with_mv(target_mv)


def subtype_filter_lib(subtype: str) -> Callable[[GameObject, GameState], bool]:
    """Filter: any card with the given subtype (e.g. 'Aura', 'Equipment')."""
    from src.engine.library_search import is_subtype
    return is_subtype(subtype)


def any_card_filter() -> Callable[[GameObject, GameState], bool]:
    """Filter: any card in library (unconditional tutor)."""
    from src.engine.library_search import any_card
    return any_card()


# =============================================================================
# Token-copy from graveyard / Look-N-land-pick
# =============================================================================
#
# Two narrowly-scoped helpers used by FIN cards (Sin, Spira's Punishment;
# Ignis Scientia) but generic enough for any set:
#
# * ``make_token_copy_from_graveyard`` - emit an OBJECT_CREATED event whose
#   ``copy_of`` points at a card currently in a graveyard. The pipeline's
#   ``_handle_object_created`` already deep-copies printed characteristics
#   from any object regardless of zone, so the only special handling here is
#   defaulting ``is_token=True`` and routing the resulting permanent onto
#   the battlefield (optionally tapped). The original graveyard card is
#   untouched (the engine creates a new GameObject with fresh id).
#
# * ``make_top_n_land_pick`` - look at top N cards of a library and offer a
#   PendingChoice in which the controller may pick exactly one LAND from
#   among them. The picked land moves LIBRARY -> BATTLEFIELD (tapped iff
#   ``put_tapped``); every other revealed card goes to the bottom of the
#   library in a random order. Declining (when ``optional=True`` or no land
#   is present) puts every revealed card on the bottom in random order.
# =============================================================================


def make_token_copy_from_graveyard(
    state: GameState,
    controller: str,
    source_card_id: str,
    *,
    source_id: Optional[str] = None,
    tapped: bool = False,
    count: int = 1,
    add_subtypes: Optional[set] = None,
) -> list[Event]:
    """Build OBJECT_CREATED events that token-copy a card currently in a graveyard.

    Args:
        state: Current GameState (used to validate the source card exists).
        controller: Player ID who will control the new token.
        source_card_id: Object id of a card sitting in a graveyard zone.
        source_id: Object id of the spell/ability creating the copy
            (used as ``Event.source`` for downstream triggers).
        tapped: Whether the copy enters tapped.
        count: Number of token copies to create. Default 1.
        add_subtypes: Subtypes to add in addition to the copied subtypes.

    Returns:
        ``count`` OBJECT_CREATED events targeting ``source_card_id`` via the
        ``copy_of`` payload field. If the source card is missing or no longer
        in a graveyard, returns ``[]``.

    Notes:
        The pipeline's ``_handle_object_created`` looks up ``copy_of`` in
        ``state.objects`` regardless of the source's zone, so it works for
        graveyard sources just as it does for battlefield sources. The
        original graveyard card is *not* moved: a new GameObject is created
        with a fresh id, deep-copied characteristics, and the source's
        ``card_def`` is inherited so its ``setup_interceptors`` fire on ETB.
    """
    src_obj = state.objects.get(source_card_id)
    if src_obj is None or src_obj.zone != ZoneType.GRAVEYARD:
        return []

    return make_copy_token_event(
        target_id=source_card_id,
        controller=controller,
        source_id=source_id,
        count=count,
        tapped=tapped,
        add_subtypes=add_subtypes,
    )


def make_top_n_land_pick(
    state: GameState,
    controller: str,
    source_id: str,
    *,
    n: int = 5,
    put_tapped: bool = True,
    optional: bool = True,
    prompt: Optional[str] = None,
) -> list[Event]:
    """Open a PendingChoice for "look at top N, may put a land onto the battlefield".

    Reveal the top ``n`` cards of ``controller``'s library to themselves. They
    may pick exactly one LAND card from among the revealed cards; that card
    moves LIBRARY -> BATTLEFIELD (tapped iff ``put_tapped``). Every other
    revealed card (including non-picked lands and all non-lands) goes to the
    bottom of the library in a random order.

    When ``optional=True`` the controller may decline and bottom every
    revealed card. When no land is among the revealed cards the controller
    is auto-resolved to "decline" without a choice prompt.

    Args:
        state: Current GameState.
        controller: Player ID looking at the top of their library.
        source_id: Source card id (Sin Spira / Ignis Scientia / etc.).
        n: Number of cards to look at (default 5).
        put_tapped: Whether the chosen land enters tapped (default True).
        optional: Whether the player may decline picking a land (default True).
        prompt: Optional override for the choice prompt.

    Returns:
        ``[]`` (the helper installs ``state.pending_choice`` directly, the
        same pattern as ``open_library_search``). Use as the ``effect_fn``
        return value for an ETB trigger or activated ability.

    Edge cases:
        - Library smaller than N: looks at whatever is available.
        - Empty library: returns [] without installing a choice.
        - No land in revealed cards: bottoms everything in random order
          (no choice presented).
    """
    library_key = f"library_{controller}"
    library = state.zones.get(library_key)
    if library is None or not library.objects:
        return []

    revealed = list(library.objects[:n])
    if not revealed:
        return []

    land_ids: list[str] = []
    for cid in revealed:
        obj = state.objects.get(cid)
        if obj is None:
            continue
        if CardType.LAND in obj.characteristics.types:
            land_ids.append(cid)

    def _bottom_in_random_order(cids: list[str], st: GameState) -> None:
        """Bottom each card in ``cids`` (random order) onto the library."""
        import random as _rnd
        from src.engine.pipeline._shared import _remove_object_from_all_zones
        ordering = list(cids)
        _rnd.shuffle(ordering)
        lib = st.zones.get(library_key)
        if lib is None:
            return
        for cid in ordering:
            obj = st.objects.get(cid)
            if obj is None:
                continue
            _remove_object_from_all_zones(cid, st)
            lib.objects.append(cid)
            obj.zone = ZoneType.LIBRARY
            obj.entered_zone_at = st.timestamp

    # No land available -> auto-bottom everything; no choice presented.
    if not land_ids:
        _bottom_in_random_order(revealed, state)
        return []

    def _resolve(
        choice: PendingChoice, selected: list, st: GameState
    ) -> list[Event]:
        # Selection format: a single card-id (str) or a {'id': ...} dict, or
        # an empty list / 'decline' marker for the optional path.
        picked: Optional[str] = None
        if selected:
            first = selected[0]
            picked_id = first.get('id') if isinstance(first, dict) else first
            if picked_id == 'decline':
                picked = None
            elif picked_id in land_ids:
                picked = picked_id

        others = [cid for cid in revealed if cid != picked]

        from src.engine.pipeline._shared import _remove_object_from_all_zones

        if picked is not None:
            obj = st.objects.get(picked)
            if obj is not None:
                _remove_object_from_all_zones(picked, st)
                bf = st.zones.get('battlefield')
                if bf is not None:
                    bf.objects.append(picked)
                    obj.zone = ZoneType.BATTLEFIELD
                    obj.controller = controller
                    obj.state.tapped = bool(put_tapped)
                    obj.state.summoning_sickness = False  # Lands don't have summoning sickness
                    obj.entered_zone_at = st.timestamp
                    # Re-run setup_interceptors (the create-from-hand pipeline
                    # would normally do this; we're shortcutting LIBRARY->BF).
                    cd = obj.card_def
                    if cd is not None and getattr(cd, 'setup_interceptors', None):
                        try:
                            new_ints = cd.setup_interceptors(obj, st) or []
                            for it in new_ints:
                                it.timestamp = st.next_timestamp()
                                st.interceptors[it.id] = it
                                obj.interceptor_ids.append(it.id)
                        except Exception:
                            pass

        _bottom_in_random_order(others, st)
        return []

    # Build option list. When optional, append a 'decline' synthetic option.
    options: list[Any] = list(land_ids)
    if optional:
        options.append({'id': 'decline', 'label': 'Decline (bottom all in random order)'})

    choice = PendingChoice(
        choice_type="top_n_land_pick",
        player=controller,
        prompt=prompt or f"Look at top {len(revealed)}: choose a land to put onto the battlefield"
                        + (" tapped" if put_tapped else "")
                        + (", or decline." if optional else "."),
        options=options,
        source_id=source_id,
        min_choices=0 if optional else 1,
        max_choices=1,
        callback_data={
            'handler': _resolve,
            'revealed': list(revealed),
            'land_ids': list(land_ids),
        },
    )
    state.pending_choice = choice
    return []


# =============================================================================
# CAST-FROM-ZONE PERMISSIONS (W7)
# =============================================================================
#
# Thin wrapper around src/engine/cast_permission.py. Lets a setup_interceptors
# function grant permission to cast a specific card from graveyard, exile, or
# the top of the library — optionally for an alternate cost.
#
# Example (Bestial Bloodline-style "graveyard activation":
#     def my_card_setup(obj, state):
#         def activate(ev, st):
#             # Find a target card in graveyard and grant a one-shot cast
#             # permission until end of turn.
#             return make_castable_from_graveyard(
#                 obj, target_card_id=target.id, duration='end_of_turn',
#             )
#         ...
#
# For a continuous "Future Sight"-style permission ("you may cast the top
# card of your library"), use ``make_castable_from_zone`` directly and pass
# ``zone='library_top'`` with ``library_top_only=True``.
# =============================================================================


def make_castable_from_zone(
    source_obj: GameObject,
    *,
    target_card_id: str,
    zone,
    duration: str = "permanent",
    cost_modifier=None,
    library_top_only: bool = False,
) -> list[Interceptor]:
    """Grant permission to cast ``target_card_id`` from ``zone``.

    Returns a list of interceptors. Caller is responsible for registering
    each via ``state.interceptors[i.id] = i`` (or by returning it from a
    ``setup_interceptors`` function that the engine wires up automatically).
    """
    from src.engine.cast_permission import (
        make_castable_from_zone as _impl,
    )
    return _impl(
        source_obj,
        target_card_id=target_card_id,
        zone=zone,
        duration=duration,
        cost_modifier=cost_modifier,
        library_top_only=library_top_only,
    )


def make_castable_from_graveyard(
    source_obj: GameObject,
    *,
    target_card_id: str,
    duration: str = "permanent",
    cost_modifier=None,
) -> list[Interceptor]:
    """Convenience: grant permission to cast a specific card from a graveyard.

    Common pattern: a Flashback-style ETB or one-shot effect that lets the
    controller cast a specific card from a graveyard until end of turn. Pass
    ``cost_modifier`` to use an alternate cost (e.g. ``ManaCost()`` for
    "without paying its mana cost").
    """
    return make_castable_from_zone(
        source_obj,
        target_card_id=target_card_id,
        zone="graveyard",
        duration=duration,
        cost_modifier=cost_modifier,
    )


def make_castable_from_exile(
    source_obj: GameObject,
    *,
    target_card_id: str,
    duration: str = "permanent",
    cost_modifier=None,
) -> list[Interceptor]:
    """Convenience: grant permission to cast a specific card from exile."""
    return make_castable_from_zone(
        source_obj,
        target_card_id=target_card_id,
        zone="exile",
        duration=duration,
        cost_modifier=cost_modifier,
    )


def make_castable_from_library_top(
    source_obj: GameObject,
    *,
    duration: str = "permanent",
    cost_modifier=None,
) -> list[Interceptor]:
    """Convenience: continuous "may cast the top card of your library" effect.

    Grants permission for any card the source's controller owns when that
    card is currently the top of their library. Bolas's Citadel / Future
    Sight-style.
    """
    return make_castable_from_zone(
        source_obj,
        target_card_id="*",
        zone="library_top",
        duration=duration,
        cost_modifier=cost_modifier,
        library_top_only=True,
    )


# =============================================================================
# HAND -> BATTLEFIELD CHOICE (Kona, Rescue Beastie / Ghalta template)
# =============================================================================
#
# Many cards say "you may put a [permanent] card from your hand onto the
# battlefield". The engine handles ZONE_CHANGE from HAND to BATTLEFIELD
# directly, but choosing the card requires a PendingChoice over the player's
# hand filtered to the relevant card kind. ``make_hand_to_battlefield_choice``
# builds the events needed to open that choice from inside an effect_fn.
# =============================================================================


def _is_permanent_card(obj: GameObject, _state: GameState) -> bool:
    """Default permanent filter: anything that becomes a permanent on the
    battlefield (creature, artifact, enchantment, planeswalker, land,
    battle). Excludes instants and sorceries.
    """
    permanent_types = {
        CardType.CREATURE,
        CardType.ARTIFACT,
        CardType.ENCHANTMENT,
        CardType.PLANESWALKER,
        CardType.LAND,
    }
    # MTG "Battle" type — added in March of the Machine. Not yet in our enum,
    # but include it dynamically if/when added.
    if hasattr(CardType, 'BATTLE'):
        permanent_types.add(getattr(CardType, 'BATTLE'))
    types = getattr(obj.characteristics, 'types', set()) or set()
    return any(t in types for t in permanent_types)


def make_hand_to_battlefield_choice(
    state: GameState,
    player_id: str,
    source_id: str,
    *,
    filter_fn: Optional[Callable[[GameObject, GameState], bool]] = None,
    optional: bool = True,
    tapped: bool = False,
    prompt: Optional[str] = None,
) -> list[Event]:
    """Open a PendingChoice over ``player_id``'s hand for "put a card from
    hand onto the battlefield" effects.

    Args:
        state: The game state. ``state.pending_choice`` will be set on success.
        player_id: The owner of the hand we're searching.
        source_id: Card/ability id (for log + targeting).
        filter_fn: ``(card_obj, state) -> bool``. Defaults to "any permanent
            card" (creature, artifact, enchantment, planeswalker, land,
            battle — excludes instants and sorceries).
        optional: If True (default), player may decline (min_choices=0).
        tapped: If True, the chosen card enters tapped.
        prompt: Optional UI prompt. Auto-generated if absent.

    Returns:
        ``[]`` (the PendingChoice does the work). Use this as the return value
        of an ``effect_fn``. If the hand has no legal cards and the choice is
        optional, no choice is opened and ``[]`` is returned.
    """
    actual_filter = filter_fn or _is_permanent_card

    hand_key = f"hand_{player_id}"
    hand = state.zones.get(hand_key)
    if hand is None:
        return []

    legal_ids: list[str] = []
    for cid in hand.objects:
        cobj = state.objects.get(cid)
        if cobj is None:
            continue
        try:
            if actual_filter(cobj, state):
                legal_ids.append(cid)
        except Exception:
            continue

    if not legal_ids:
        return []

    def _on_chosen(choice: PendingChoice, selected: list, st: GameState) -> list[Event]:
        if not selected:
            return []
        chosen_id = selected[0]
        chosen = st.objects.get(chosen_id)
        if chosen is None or chosen.zone != ZoneType.HAND:
            return []
        # Emit ZONE_CHANGE from HAND -> BATTLEFIELD. The pipeline's
        # _handle_zone_change handler will move the object, fire ETB,
        # run setup_interceptors, etc.
        zc_payload = {
            'object_id': chosen_id,
            'from_zone_type': ZoneType.HAND,
            'from_zone_owner': chosen.owner,
            'to_zone_type': ZoneType.BATTLEFIELD,
        }
        events = [Event(
            type=EventType.ZONE_CHANGE,
            payload=zc_payload,
            source=source_id,
            controller=player_id,
        )]
        if tapped:
            # Schedule a follow-up TAP after the ZONE_CHANGE resolves.
            events.append(Event(
                type=EventType.TAP,
                payload={'object_id': chosen_id},
                source=source_id,
                controller=player_id,
            ))
        return events

    choice_prompt = prompt or (
        "Choose a permanent card to put onto the battlefield"
        if filter_fn is None
        else "Choose a card to put onto the battlefield"
    )

    choice = PendingChoice(
        choice_type="hand_to_battlefield",
        player=player_id,
        prompt=choice_prompt,
        options=legal_ids,
        source_id=source_id,
        min_choices=0 if optional else 1,
        max_choices=1,
        callback_data={
            'handler': _on_chosen,
            'tapped': bool(tapped),
        },
    )
    state.pending_choice = choice
    return []


# =============================================================================
# REVEAL TOP N WITH DISTINCT-ATTR FILTER (Rip, Spawn Hunter template)
# =============================================================================
#
# Some cards reveal the top N of the library, then let the player put any
# number of revealed cards matching some filter into hand (or another zone),
# subject to a "different X" constraint (e.g. "with different powers").
# Cards not chosen go to a configurable destination — typically the bottom
# of the library in random order ("randomize the rest").
# =============================================================================


def reveal_top_n_with_distinct_filter(
    state: GameState,
    player_id: str,
    source_id: str,
    n: int,
    *,
    filter_fn: Optional[Callable[[GameObject, GameState], bool]] = None,
    distinct_attr: str = 'power',
    destination: str = 'hand',
    remainder: str = 'bottom_random',
    prompt: Optional[str] = None,
) -> list[Event]:
    """Reveal the top ``n`` cards of ``player_id``'s library and open a choice
    where the player picks any subset matching ``filter_fn`` such that all
    chosen cards have *distinct* values for ``distinct_attr``. Selected cards
    go to ``destination``; the rest go per ``remainder``.

    Sibling of :func:`src.engine.face_down._handle_manifest_dread`: pulls cards
    off the top of the library, but instead of manifesting one and milling the
    rest, surfaces a multi-target PendingChoice gated by a distinctness rule.

    Args:
        state: Game state.
        player_id: Library owner / chooser.
        source_id: Card/ability id (for log + targeting).
        n: Number of cards to reveal from the top.
        filter_fn: Eligibility check, ``(obj, state) -> bool``. Cards failing
            the filter still go to ``remainder`` automatically; they're not
            offered as options.
        distinct_attr: Power-name to enforce distinctness over. Default 'power'
            (Rip, Spawn Hunter). Other plausible values: 'toughness',
            'mana_value'. Read off ``obj.characteristics`` (or the helpers
            ``get_power``/``get_toughness`` if available) at choice-open time.
        destination: Where chosen cards go. Currently 'hand' (Rip).
            Other supported destinations route through ZONE_CHANGE events.
        remainder: Where unchosen + non-eligible revealed cards go. Default
            'bottom_random' (per Rip's text). Other values: 'bottom' (top->
            bottom, preserving order), 'graveyard'.
        prompt: Optional UI prompt.

    Returns:
        ``[]`` — the choice does the work. If the library is empty or
        ``n <= 0``, nothing happens.
    """
    import random as _random

    if n <= 0:
        return []

    library = state.zones.get(f"library_{player_id}")
    if library is None or not library.objects:
        return []

    # Pull up to n from the top, strictly off the front of the list.
    revealed_ids: list[str] = []
    while library.objects and len(revealed_ids) < n:
        revealed_ids.append(library.objects.pop(0))

    if not revealed_ids:
        return []

    def _attr_value(obj: GameObject, attr: str) -> Any:
        chars = getattr(obj, 'characteristics', None)
        if chars is None:
            return None
        if attr == 'power':
            return getattr(chars, 'power', None)
        if attr == 'toughness':
            return getattr(chars, 'toughness', None)
        if attr in ('mana_value', 'mv', 'cmc'):
            mc = getattr(chars, 'mana_cost', None)
            if mc is None:
                return 0
            try:
                return int(getattr(mc, 'mana_value', 0)) if hasattr(mc, 'mana_value') else int(mc)
            except Exception:
                return 0
        return getattr(chars, attr, None)

    # Eligible set: cards whose filter_fn returns True. Ineligible cards are
    # routed straight to the remainder. We keep them in a secondary list.
    eligible_ids: list[str] = []
    ineligible_ids: list[str] = []
    for cid in revealed_ids:
        cobj = state.objects.get(cid)
        if cobj is None:
            ineligible_ids.append(cid)
            continue
        try:
            if filter_fn is None or filter_fn(cobj, state):
                eligible_ids.append(cid)
            else:
                ineligible_ids.append(cid)
        except Exception:
            ineligible_ids.append(cid)

    def _route_to_remainder(ids: list[str]) -> list[Event]:
        """Build events that move ``ids`` to ``remainder``."""
        evs: list[Event] = []
        if not ids:
            return evs
        if remainder == 'bottom_random':
            order = list(ids)
            _random.shuffle(order)
            lib = state.zones.get(f"library_{player_id}")
            if lib is None:
                return []
            for oid in order:
                ob = state.objects.get(oid)
                if ob is None:
                    continue
                lib.objects.append(oid)
                ob.zone = ZoneType.LIBRARY
                ob.entered_zone_at = state.timestamp
        elif remainder == 'bottom':
            lib = state.zones.get(f"library_{player_id}")
            if lib is None:
                return []
            for oid in ids:
                ob = state.objects.get(oid)
                if ob is None:
                    continue
                lib.objects.append(oid)
                ob.zone = ZoneType.LIBRARY
                ob.entered_zone_at = state.timestamp
        elif remainder == 'graveyard':
            gy = state.zones.get(f"graveyard_{player_id}")
            if gy is None:
                return []
            for oid in ids:
                ob = state.objects.get(oid)
                if ob is None:
                    continue
                gy.objects.append(oid)
                ob.zone = ZoneType.GRAVEYARD
                ob.entered_zone_at = state.timestamp
        return evs

    def _on_chosen(choice: PendingChoice, selected: list, st: GameState) -> list[Event]:
        # Validate the distinctness constraint.
        seen_attr_values: set = set()
        accepted: list[str] = []
        for cid in selected:
            if cid not in eligible_ids:
                continue
            cobj = st.objects.get(cid)
            if cobj is None:
                continue
            v = _attr_value(cobj, distinct_attr)
            if v in seen_attr_values:
                # Skip duplicate-attr picks. We can't error here without
                # re-opening the choice; tolerate by ignoring extras.
                continue
            seen_attr_values.add(v)
            accepted.append(cid)

        events: list[Event] = []
        # Move accepted to destination.
        for cid in accepted:
            cobj = st.objects.get(cid)
            if cobj is None:
                continue
            if destination == 'hand':
                hand = st.zones.get(f"hand_{player_id}")
                if hand is None:
                    continue
                hand.objects.append(cid)
                cobj.zone = ZoneType.HAND
                cobj.entered_zone_at = st.timestamp
            elif destination == 'battlefield':
                events.append(Event(
                    type=EventType.ZONE_CHANGE,
                    payload={
                        'object_id': cid,
                        'from_zone_type': ZoneType.LIBRARY,
                        'to_zone_type': ZoneType.BATTLEFIELD,
                    },
                    source=source_id,
                    controller=player_id,
                ))
            elif destination == 'graveyard':
                gy = st.zones.get(f"graveyard_{player_id}")
                if gy is None:
                    continue
                gy.objects.append(cid)
                cobj.zone = ZoneType.GRAVEYARD
                cobj.entered_zone_at = st.timestamp
            elif destination == 'exile':
                ex = st.zones.get('exile')
                if ex is None:
                    continue
                ex.objects.append(cid)
                cobj.zone = ZoneType.EXILE
                cobj.entered_zone_at = st.timestamp

        # Route non-accepted (eligible-but-not-chosen + ineligible) to remainder.
        rest = [cid for cid in eligible_ids if cid not in accepted] + ineligible_ids
        events.extend(_route_to_remainder(rest))
        return events

    if not eligible_ids:
        # Nothing to choose — route everything to remainder and finish.
        _route_to_remainder(ineligible_ids)
        return []

    choice_prompt = prompt or (
        f"Choose any number of cards (with different {distinct_attr}s)"
    )

    choice = PendingChoice(
        choice_type="reveal_distinct",
        player=player_id,
        prompt=choice_prompt,
        options=list(eligible_ids),
        source_id=source_id,
        min_choices=0,
        max_choices=len(eligible_ids),
        callback_data={
            'handler': _on_chosen,
            'distinct_attr': distinct_attr,
            'destination': destination,
            'remainder': remainder,
            'eligible_ids': list(eligible_ids),
            'ineligible_ids': list(ineligible_ids),
        },
    )
    state.pending_choice = choice
    return []


# === SAGA HELPERS ===
# MTG Saga subsystem helpers. The engine-level event handling lives in
# ``src/engine/saga.py``; this section provides the card-level helper that
# wires up a Saga's ETB lore counter, draw-step lore counter, chapter
# triggers, and final-chapter sacrifice.

from dataclasses import dataclass as _dataclass  # local alias; module-level dataclass import lives later


@_dataclass
class SagaChapter:
    """Declarative chapter spec for ``make_saga_setup``.

    Supports the new keyword API:

        make_saga_setup(
            chapters=[
                SagaChapter(label="I", effect_fn=ch_one),
                SagaChapter(label="II, III", effect_fn=ch_two_three),
                SagaChapter(label="IV", effect_fn=ch_four),
            ],
        )

    The ``label`` may be a single roman numeral (e.g. ``"I"``) or a comma-
    separated list (e.g. ``"I, II"``) for combined-chapter abilities. The
    legacy ``{int: fn}`` form is still accepted by ``make_saga_setup``.
    """
    label: str
    effect_fn: Callable[[GameObject, GameState], list[Event]]
    description: str = ""


def _saga_chapters_to_dict(
    chapters: list,
) -> dict[int, Callable[[GameObject, GameState], list[Event]]]:
    """Convert a list of ``SagaChapter`` (or dict) into the legacy dict form.

    Combined-chapter labels like ``"I, II"`` register the same callback for
    each listed chapter. Labels are case-insensitive Roman numerals.
    """
    if isinstance(chapters, dict):
        return dict(chapters)

    result: dict[int, Callable[[GameObject, GameState], list[Event]]] = {}
    for ch in chapters:
        if not isinstance(ch, SagaChapter):
            raise TypeError(
                f"chapters must be SagaChapter or dict; got {type(ch).__name__}"
            )
        # Label may be "I", "II, III", or "I,II". Split on comma, strip.
        parts = [p.strip() for p in str(ch.label).split(',') if p.strip()]
        for part in parts:
            try:
                n = _roman_to_int_helper(part)
            except Exception:
                raise ValueError(
                    f"SagaChapter label {part!r} is not a recognized "
                    f"Roman numeral (full label: {ch.label!r})"
                )
            if n <= 0:
                raise ValueError(
                    f"SagaChapter label {part!r} evaluated to non-positive {n}"
                )
            result[n] = ch.effect_fn
    return result


def _roman_to_int_helper(s: str) -> int:
    """Helper: Roman numeral to int. Mirrors ``src.engine.saga._roman_to_int``."""
    table = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    total = 0
    prev = 0
    for ch in reversed(s.upper()):
        v = table.get(ch, 0)
        if v == 0:
            raise ValueError(f"Unknown Roman digit: {ch!r}")
        if v < prev:
            total -= v
        else:
            total += v
        prev = v
    return total


def make_saga_setup(
    source_obj: GameObject = None,
    chapter_handlers: dict[int, Callable[[GameObject, GameState], list[Event]]] = None,
    final_chapter: Optional[int] = None,
    *,
    chapters: list = None,
    sacrifice_after_final: bool = True,
) -> list[Interceptor]:
    """
    Build the interceptors for a Saga enchantment.

    Two calling conventions are supported:

    Legacy (still used by ~30+ wired cards):
        ``make_saga_setup(source_obj, {1: ch_i, 2: ch_ii_iii, 3: ch_ii_iii},
                         final_chapter=3)``

    Declarative (new, preferred for fresh wirings):
        ``make_saga_setup(source_obj,
                         chapters=[
                             SagaChapter("I", ch_i),
                             SagaChapter("II, III", ch_ii_iii),
                         ])``

    Args:
        source_obj: The Saga ``GameObject``.
        chapter_handlers: ``{chapter_number: effect_fn}``. Each ``effect_fn``
            takes ``(saga_obj, state)`` and returns a list of follow-up events
            to emit when that chapter triggers. Multiple chapters that share an
            ability (e.g. "I, II — ...") should map to the same callable.
        final_chapter: Optional explicit final-chapter number. If omitted, it
            is inferred from the rules text (``"Sacrifice after <ROMAN>."``)
            and falls back to ``max(chapter_handlers)``.
        chapters: Alternative declarative API. A list of ``SagaChapter``
            entries; combined-chapter labels (``"I, II"``) register the same
            ``effect_fn`` against each listed chapter. Mutually exclusive with
            ``chapter_handlers``.
        sacrifice_after_final: If True (default), after the final chapter
            resolves the Saga is sacrificed (CR 714.5). Pass ``False`` for
            Sagas that explicitly persist past the last chapter (e.g.
            transforming Sagas where the back face replaces the Saga). The
            framework always advances lore counters; only the sacrifice step
            is gated.

    Canonical lore-counter trigger:
        Per CR 714.3 the lore counter is added "after your draw step." This
        implementation reacts to ``EventType.PHASE_START`` with
        ``payload.phase == 'draw'`` and the Saga's controller being the
        active player. The pipeline emits this event at the *start* of the
        draw step rather than at end — but because we react before the chapter
        resolves on the stack, and there is currently no other code that races
        the lore counter against the draw itself, this is functionally
        equivalent to "after draw step" for every card wired today. The
        alternative (an `END_PHASE` hook on draw, or a `BEGIN_MAIN_PHASE`
        hook) would be more spec-accurate but the engine has no dedicated
        end-of-draw event yet.

    Returns:
        A list of interceptors:

        1. ``REACT`` on ZONE_CHANGE -> battlefield (this Saga): emits
           ``SAGA_LORE_ADDED`` so chapter I fires immediately on entry.
        2. ``REACT`` on PHASE_START phase ``'draw'`` while controller is the
           active player: emits ``SAGA_LORE_ADDED`` for the next chapter.
        3. ``REACT`` on ``SAGA_CHAPTER`` for this Saga: dispatches to the
           registered chapter handler and (if ``sacrifice_after_final``)
           queues a final-chapter SACRIFICE event.

    Notes:
        * Chapter handlers may return ``[]`` for chapters whose effect is not
          fully implementable yet (e.g. interactive targeting). The Saga still
          ticks through every chapter and is sacrificed normally.
        * ``source_obj.card_def._saga_final_chapter`` is set to ``final_chapter``
          if provided; the engine reads that override when computing the final
          chapter for this Saga.
        * If the Saga leaves the battlefield before the final chapter (e.g.
          destroyed by removal), no spurious sacrifice fires — the chapter
          interceptor's filter only matches while the Saga remains on the
          battlefield, and ``SAGA_LORE_ADDED`` no-ops on a non-battlefield
          Saga (see ``src/engine/saga.py::_handle_saga_lore_added``).
    """
    # Normalize new declarative API → legacy dict form.
    if chapters is not None:
        if chapter_handlers is not None:
            raise TypeError(
                "make_saga_setup: pass either chapter_handlers or chapters, "
                "not both"
            )
        chapter_handlers = _saga_chapters_to_dict(chapters)
    if source_obj is None:
        raise TypeError("make_saga_setup: source_obj is required")
    if chapter_handlers is None:
        chapter_handlers = {}

    saga_id = source_obj.id
    controller_id = source_obj.controller

    # Resolve the final chapter:
    #   1. explicit argument
    #   2. card_def._saga_final_chapter override (set by previous calls)
    #   3. text parse via engine helper (fallback inside engine)
    #   4. last fallback: max chapter in handlers
    if final_chapter is None:
        from src.engine.saga import _saga_final_chapter as _engine_final
        final_chapter = _engine_final(source_obj)
        if chapter_handlers:
            final_chapter = max(final_chapter, max(chapter_handlers.keys()))
    # Stash explicit override on the card_def so the engine handler honors it
    # consistently across the Saga's lifetime.
    if source_obj.card_def is not None:
        try:
            source_obj.card_def._saga_final_chapter = int(final_chapter)
        except Exception:
            pass

    # ---------------------------------------------------------------- ETB lore
    def etb_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.ZONE_CHANGE
            and event.payload.get('object_id') == saga_id
            and event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD
        )

    def etb_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.SAGA_LORE_ADDED,
                payload={'object_id': saga_id, 'amount': 1},
                source=saga_id,
                controller=controller_id,
            )],
        )

    etb_interceptor = Interceptor(
        id=new_id(),
        source=saga_id,
        controller=controller_id,
        priority=InterceptorPriority.REACT,
        filter=etb_filter,
        handler=etb_handler,
        duration='while_on_battlefield',
    )

    # --------------------------------------------- Draw-step lore (post-draw)
    def draw_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'draw':
            return False
        # Only on this Saga's controller's turn.
        saga = state.objects.get(saga_id)
        if saga is None or saga.zone != ZoneType.BATTLEFIELD:
            return False
        if state.active_player != saga.controller:
            return False
        return True

    def draw_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.SAGA_LORE_ADDED,
                payload={'object_id': saga_id, 'amount': 1},
                source=saga_id,
                controller=controller_id,
            )],
        )

    draw_interceptor = Interceptor(
        id=new_id(),
        source=saga_id,
        controller=controller_id,
        priority=InterceptorPriority.REACT,
        filter=draw_filter,
        handler=draw_handler,
        duration='while_on_battlefield',
    )

    # ----------------------------------------- Chapter dispatcher + sacrifice
    handlers_by_chapter = dict(chapter_handlers or {})

    def chapter_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.SAGA_CHAPTER
            and event.payload.get('object_id') == saga_id
        )

    def chapter_handler(event: Event, state: GameState) -> InterceptorResult:
        chapter = int(event.payload.get('chapter', 0) or 0)
        # Use the live final_chapter — _saga_final_chapter() reads from card_def.
        from src.engine.saga import _saga_final_chapter as _engine_final
        live_final = _engine_final(source_obj) if source_obj else final_chapter
        # Confirm the Saga is still on the battlefield before dispatching the
        # chapter effect. If a previous chapter (or some other effect) caused
        # it to leave the battlefield mid-resolution, the chapter ability
        # still resolves with no targets — but a sacrifice event would be a
        # spurious double-fire.
        live_saga = state.objects.get(saga_id)
        on_battlefield = live_saga is not None and live_saga.zone == ZoneType.BATTLEFIELD
        new_events: list[Event] = []
        # Dispatch the chapter effect (if any).
        cb = handlers_by_chapter.get(chapter)
        if cb is not None:
            try:
                produced = cb(source_obj, state) or []
            except Exception:
                produced = []
            new_events.extend(list(produced))
        # Final chapter -> sacrifice the Saga (unless the caller opted out
        # or the Saga has already left the battlefield).
        if (sacrifice_after_final
                and on_battlefield
                and chapter >= int(live_final or 0)):
            new_events.append(Event(
                type=EventType.SACRIFICE,
                payload={'object_id': saga_id, 'player': controller_id},
                source=saga_id,
                controller=controller_id,
            ))
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events,
        )

    # CR 715.4: A Saga's chapter ability is a triggered ability that goes on
    # the stack. The ETB-lore and draw-step-lore interceptors above are
    # state-transition observers that just emit SAGA_LORE_ADDED — they don't
    # represent triggered abilities themselves.
    def _chapter_effect_fn(event: Event, state: GameState) -> list[Event]:
        chapter = int(event.payload.get('chapter', 0) or 0)
        from src.engine.saga import _saga_final_chapter as _engine_final
        live_final = _engine_final(source_obj) if source_obj else final_chapter
        live_saga = state.objects.get(saga_id)
        on_battlefield = live_saga is not None and live_saga.zone == ZoneType.BATTLEFIELD
        new_events: list[Event] = []
        cb = handlers_by_chapter.get(chapter)
        if cb is not None:
            try:
                produced = cb(source_obj, state) or []
            except Exception:
                produced = []
            new_events.extend(list(produced))
        if (sacrifice_after_final
                and on_battlefield
                and chapter >= int(live_final or 0)):
            new_events.append(Event(
                type=EventType.SACRIFICE,
                payload={'object_id': saga_id, 'player': controller_id},
                source=saga_id,
                controller=controller_id,
            ))
        return new_events

    chapter_interceptor = Interceptor(
        id=new_id(),
        source=saga_id,
        controller=controller_id,
        priority=InterceptorPriority.REACT,
        filter=chapter_filter,
        handler=chapter_handler,
        duration='while_on_battlefield',
    )
    _mark_triggered_ability(chapter_interceptor, _chapter_effect_fn, description="Saga chapter trigger")

    return [etb_interceptor, draw_interceptor, chapter_interceptor]


# === CRIME HELPERS ===
# =============================================================================
# OTJ Crime mechanic: a player commits a crime when they target an opponent,
# an opponent's permanent, or a card in an opponent's graveyard with a spell
# or ability.
#
# Crime detection is wired in:
#   - src/engine/game.py        (after target choices resolve)
#   - src/engine/priority.py    (when a spell with pre-chosen targets is cast)
#
# These helpers thinly wrap the engine API so card scripts don't import
# ``src.engine.crime`` directly.

def is_crime_committed(player: str, state: GameState) -> bool:
    """Return True if ``player`` has committed a crime this turn."""
    from src.engine.crime import is_crime_committed as _impl
    return _impl(player, state)


def crime_count(player: str, state: GameState) -> int:
    """Return how many crimes ``player`` has committed this turn."""
    from src.engine.crime import crime_count as _impl
    return _impl(player, state)


def make_crime_committed_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    once_per_turn: bool = False,
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None,
) -> Interceptor:
    """Create a "whenever you commit a crime" trigger.

    Fires on ``EventType.CRIME_COMMITTED`` for the source's controller.

    Args:
        source_obj: The object with the trigger.
        effect_fn: Function(event, state) -> list[Event] when trigger fires.
        once_per_turn: If True, only fires once per turn (uses
            ``state.turn_data['crime_trigger_<source_id>_<turn>']``).
        filter_fn: Optional extra filter ``(event, state, source) -> bool``.

    Event: CRIME_COMMITTED
    Payload: {'player': str, 'targets': list, 'source': str}
    Priority: REACT
    """
    source_id = source_obj.id

    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CRIME_COMMITTED:
            return False
        # Look up the source object live (the closure capture may be stale
        # if the controller changed via Gain Control etc.).
        live = state.objects.get(source_id, source_obj)
        if event.payload.get('player') != live.controller:
            return False
        if once_per_turn:
            key = f'crime_trigger_{source_id}_{state.turn_number}'
            if state.turn_data.get(key):
                return False
        if filter_fn is not None and not filter_fn(event, state, live):
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        if once_per_turn:
            key = f'crime_trigger_{source_id}_{state.turn_number}'
            state.turn_data[key] = True
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events,
        )

    # Wrap effect_fn so the once-per-turn marker is set on resolution, not on
    # queueing. This matches CR 603.4: a triggered ability that's still on the
    # stack hasn't "fired" yet from the per-turn perspective.
    def _resolved_effect(event: Event, state: GameState) -> list[Event]:
        if once_per_turn:
            key = f'crime_trigger_{source_id}_{state.turn_number}'
            state.turn_data[key] = True
        return effect_fn(event, state) or []

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
    )
    return _mark_triggered_ability(interceptor, _resolved_effect, description="Crime trigger")


# Short alias requested by ``src/engine/crime.py`` consumers. Identical
# semantics to ``make_crime_committed_trigger``.
def make_crime_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    *,
    controller_only: bool = True,
    once_per_turn: bool = False,
    filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None,
) -> Interceptor:
    """Whenever you commit a crime, fire ``effect_fn``.

    ``controller_only`` is True by default and matches MTG semantics
    ("Whenever you commit a crime") — the trigger only fires for the
    source's controller. Setting it to False causes the trigger to fire
    on any player's CRIME_COMMITTED (rare; useful for "whenever a player
    commits a crime" cards).
    """
    if controller_only:
        return make_crime_committed_trigger(
            source_obj, effect_fn,
            once_per_turn=once_per_turn,
            filter_fn=filter_fn,
        )

    # controller_only=False: bypass the controller match in the filter.
    source_id = source_obj.id

    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CRIME_COMMITTED:
            return False
        live = state.objects.get(source_id, source_obj)
        if once_per_turn:
            key = f'crime_trigger_{source_id}_{state.turn_number}'
            if state.turn_data.get(key):
                return False
        if filter_fn is not None and not filter_fn(event, state, live):
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        if once_per_turn:
            key = f'crime_trigger_{source_id}_{state.turn_number}'
            state.turn_data[key] = True
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=effect_fn(event, state),
        )

    def _resolved_effect(event: Event, state: GameState) -> list[Event]:
        if once_per_turn:
            key = f'crime_trigger_{source_id}_{state.turn_number}'
            state.turn_data[key] = True
        return effect_fn(event, state) or []

    interceptor = Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
    )
    return _mark_triggered_ability(interceptor, _resolved_effect, description="Crime trigger")


# =============================================================================
# WARP HELPERS
# =============================================================================
#
# Edge of Eternities (EOE) Warp mechanic.
#
# Warp lets a card be cast from your hand for an alternate (warp) cost. The
# resulting permanent is exiled at the beginning of the next end step, and
# may then be cast again from exile on a later turn (paying its printed mana
# cost). Each card may only be warp-cast once per game.
#
# The actual cast wiring (alternate cost, end-step exile registration) lives
# in ``src/engine/warp.py`` and ``src/engine/priority.py``. The helper below
# is for card scripts that want to attach a Warp ability to a card.
#
# Usage:
#
#     CARD = make_creature(
#         name="Nova Hellkite",
#         power=4, toughness=4,
#         mana_cost="{4}{R}{R}",
#         text="Flying, haste\nWhen this creature enters, it deals 1 damage "
#              "to target creature an opponent controls.\nWarp {2}{R} (...)",
#         setup_interceptors=make_warp_setup(
#             "{2}{R}",
#             inner_setup=nova_hellkite_etb_setup,  # optional
#         ),
#     )
#
# The ``inner_setup`` argument lets you compose Warp with the card's
# existing ETB/death/etc. setup function. If None, only Warp's bookkeeping
# is set up (rare — most warp cards have other abilities).


def make_warp_setup(
    warp_cost: str,
    inner_setup: Optional[Callable[[GameObject, GameState], list[Interceptor]]] = None,
) -> Callable[[GameObject, GameState], list[Interceptor]]:
    """Wrap a card's setup_interceptors with Warp end-step-exile bookkeeping.

    The returned function:
      1. Calls ``inner_setup`` if provided, collecting its interceptors.
      2. If the object is currently warp-pending (was cast for its warp
         cost), schedules the one-shot end-step exile interceptor.

    The ``warp_cost`` argument is currently informational; the engine
    parses the cost from the card's rules text. Passing it explicitly keeps
    card definitions self-documenting.

    Args:
        warp_cost: The warp cost string (e.g. "{2}{R}{R}"). Informational.
        inner_setup: Optional existing setup_interceptors function to compose.

    Returns:
        A new setup_interceptors function suitable for ``CardDefinition``.
    """
    # Imported lazily to avoid a circular import at module load time.
    from src.engine.warp import (
        is_warp_pending,
        schedule_warp_exile_for_object,
    )

    def _warp_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        interceptors: list[Interceptor] = []
        if inner_setup is not None:
            try:
                inner = inner_setup(obj, state) or []
                interceptors.extend(inner)
            except Exception as e:
                # Don't crash the cast pipeline if the inner setup raises;
                # log and continue. Matches existing engine resilience.
                import logging
                logging.getLogger(__name__).warning(
                    "Warp inner_setup for %s raised: %s", obj.name, e
                )

        if is_warp_pending(obj):
            interceptor = schedule_warp_exile_for_object(state, obj, obj.controller)
            if interceptor is not None and interceptor.id in state.interceptors:
                # Already registered against obj.interceptor_ids by
                # schedule_warp_exile_for_object; do not duplicate here.
                pass

        return interceptors

    # Annotate so `make_warp_setup` results are easy to spot in debugging.
    _warp_setup.__name__ = (
        f"warp_setup({warp_cost})"
        if inner_setup is None
        else f"warp_setup({warp_cost})+{getattr(inner_setup, '__name__', 'inner')}"
    )
    setattr(_warp_setup, "_warp_cost", warp_cost)
    setattr(_warp_setup, "_warp_inner", inner_setup)
    return _warp_setup

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
    )
# === SPM MECHANICS HELPERS ===
# =============================================================================
# Helpers for the Marvel's Spider-Man set's two alt-cast mechanics:
#   * Web-slinging — alt cost from hand: pay {alt_cost} AND return a tapped
#     creature you control to its owner's hand instead of the spell's mana cost.
#   * Mayhem — alt cost from graveyard if the card was discarded this turn
#     (sorcery-speed timing).
#
# The engine's priority/cast layer already understands the printed Mayhem cost
# (see ``priority._get_mayhem_cost``) and tags resulting cast events with
# ``payload['mayhem']=True``. These helpers add the *card-side* book-keeping:
# they (a) stamp the alt cost onto the card definition so it survives the
# engine's cast-cost lookups, and (b) register a DISCARD interceptor so we
# can populate ``state.turn_data['discarded_card_ids']`` for downstream
# triggers that don't go through the priority layer.
# =============================================================================


def make_web_slinging_setup(
    alt_cost,
    *,
    on_websling_cast: Optional[Callable] = None,
):
    """Build a ``setup_interceptors`` function that wires Web-slinging.

    ``alt_cost`` is the web-slinging mana cost (a string like ``"{W}"`` or a
    pre-parsed ``ManaCost``). It is stamped onto ``obj.card_def.web_slinging_cost``
    so the priority/cast layer (and any hand-cast option logic) can see it
    without re-parsing the rules text.

    ``on_websling_cast`` is an optional callback invoked when *this card* is
    cast via web-slinging. It receives ``(event, state, obj)`` and returns a
    list of follow-up events. Use it for Sensational Save and similar
    "if cast for its web-slinging cost, ..." triggers.
    """
    from src.engine.spm_mechanics import register_web_slinging, track_web_slinging_cast

    def setup(obj, state):
        # Stamp the alt cost on the CardDefinition so other systems can see it.
        if getattr(obj, "card_def", None) is not None:
            register_web_slinging(obj.card_def, alt_cost)

        source_id = obj.id

        # React to the moment *this card* is cast for its web-slinging cost.
        # Convention: the cast event sets payload['web_slinging']=True when the
        # alt cost is paid (mirrors the existing payload['mayhem'] flag).
        # We always install the tracking interceptor so downstream "if this was
        # cast via web-slinging" ETB triggers can ask state.turn_data.
        def cast_filter(event: Event, state: GameState) -> bool:
            if event.type not in (EventType.CAST, EventType.SPELL_CAST):
                return False
            payload = event.payload or {}
            if not payload.get('web_slinging'):
                return False
            return payload.get('spell_id') == source_id or payload.get('card_id') == source_id

        def cast_handler(event: Event, state: GameState) -> InterceptorResult:
            payload = event.payload or {}
            try:
                returned_mv = int(payload.get('web_slinging_returned_mv', 0) or 0)
            except (TypeError, ValueError):
                returned_mv = 0
            track_web_slinging_cast(state, source_id, returned_mv)

            new_events: list = []
            if on_websling_cast is not None:
                new_events = list(on_websling_cast(event, state, obj) or [])
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=new_events,
            )

        def _ws_eff(event: Event, state: GameState) -> list[Event]:
            payload = event.payload or {}
            try:
                returned_mv = int(payload.get('web_slinging_returned_mv', 0) or 0)
            except (TypeError, ValueError):
                returned_mv = 0
            track_web_slinging_cast(state, source_id, returned_mv)
            if on_websling_cast is not None:
                return list(on_websling_cast(event, state, obj) or [])
            return []

        cast_int = Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=cast_filter,
            handler=cast_handler,
            duration='forever',
        )
        _mark_triggered_ability(cast_int, _ws_eff, description="Web-slinging cast trigger")
        return [cast_int]

    return setup


def make_mayhem_setup(
    mayhem_cost,
    *,
    on_mayhem_cast: Optional[Callable] = None,
):
    """Build a ``setup_interceptors`` function that wires Mayhem.

    ``mayhem_cost`` is the alt cast cost (string or ``ManaCost``) and is
    stamped onto ``obj.card_def.mayhem_cost`` so it survives lookup and is
    visible to the engine's graveyard-cast option list.

    The returned setup also installs a DISCARD interceptor that records this
    card's id in ``state.turn_data['discarded_card_ids']`` whenever it is
    discarded, so downstream cards can ask "was this discarded this turn?"
    without consulting ``ObjectState.last_discarded_turn`` directly.

    ``on_mayhem_cast`` is an optional callback invoked when this card is
    cast via mayhem (mirrors ``make_web_slinging_setup``).
    """
    from src.engine.spm_mechanics import register_mayhem, track_discard

    def setup(obj, state):
        if getattr(obj, "card_def", None) is not None:
            register_mayhem(obj.card_def, mayhem_cost)

        interceptors: list = []

        source_id = obj.id

        # Discard tracker: record this object's id in turn_data when it's
        # discarded. Active forever so it works in any zone (hand at the moment
        # of discard, graveyard afterwards).
        def discard_filter(event: Event, state: GameState) -> bool:
            if event.type != EventType.DISCARD:
                return False
            payload = event.payload or {}
            return payload.get('object_id') == source_id

        def discard_handler(event: Event, state: GameState) -> InterceptorResult:
            track_discard(state, source_id)
            return InterceptorResult(action=InterceptorAction.PASS)

        interceptors.append(Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=discard_filter,
            handler=discard_handler,
            duration='forever',
        ))

        if on_mayhem_cast is not None:
            def cast_filter(event: Event, state: GameState) -> bool:
                if event.type not in (EventType.CAST, EventType.SPELL_CAST):
                    return False
                payload = event.payload or {}
                if not payload.get('mayhem'):
                    return False
                return payload.get('spell_id') == source_id or payload.get('card_id') == source_id

            def cast_handler(event: Event, state: GameState) -> InterceptorResult:
                new_events = on_mayhem_cast(event, state, obj) or []
                return InterceptorResult(
                    action=InterceptorAction.REACT,
                    new_events=list(new_events),
                )

            def _mh_eff(event: Event, state: GameState) -> list[Event]:
                return list(on_mayhem_cast(event, state, obj) or [])

            mayhem_int = Interceptor(
                id=new_id(),
                source=obj.id,
                controller=obj.controller,
                priority=InterceptorPriority.REACT,
                filter=cast_filter,
                handler=cast_handler,
                duration='forever',
            )
            _mark_triggered_ability(mayhem_int, _mh_eff, description="Mayhem cast trigger")
            interceptors.append(mayhem_int)

        return interceptors

    return setup


def combine_setups(*setup_fns):
    """Combine multiple ``setup_interceptors`` callables into one.

    Convenience helper for cards whose setup is "wire web-slinging AND wire
    an ETB trigger AND wire a static effect". Each returned setup runs in
    order; their interceptor lists are concatenated. ``None`` entries are
    skipped.
    """
    fns = tuple(fn for fn in setup_fns if fn is not None)

    def combined(obj, state):
        out: list = []
        for fn in fns:
            try:
                got = fn(obj, state) or []
            except Exception:
                got = []
            out.extend(got)
        return out

    return combined
# === LANDER HELPERS ===
# =============================================================================
# Edge of Eternities — Lander mechanic. Re-exports + trigger helpers for cards
# that create Lander tokens on ETB / death.
from src.engine.lander import (
    make_lander_token_event,
    make_lander_token_events,
    is_lander,
    landers_sacced_this_turn,
)


def make_lander_etb_trigger(obj):
    """ETB: create one Lander token for obj.controller."""
    def filt(event, state):
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        return event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD

    def handler(event, state):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[make_lander_token_event(obj.controller, source_obj_id=obj.id)],
        )

    def _eff(event, state):
        return [make_lander_token_event(obj.controller, source_obj_id=obj.id)]

    interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        duration='while_on_battlefield',
    )
    return _mark_triggered_ability(interceptor, _eff, description="Lander ETB trigger")


def make_lander_death_trigger(obj):
    """Death: create one Lander token for obj.controller."""
    def filt(event, state):
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        return event.payload.get('object_id') == obj.id

    def handler(event, state):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[make_lander_token_event(obj.controller, source_obj_id=obj.id)],
        )

    def _eff(event, state):
        return [make_lander_token_event(obj.controller, source_obj_id=obj.id)]

    interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        duration='while_on_battlefield',
    )
    return _mark_triggered_ability(interceptor, _eff, description="Lander death trigger")


def make_lander_for_each_player_death_trigger(obj):
    """Death: each player gets a Lander token (used by 'Each player' effects)."""
    def filt(event, state):
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        return event.payload.get('object_id') == obj.id

    def handler(event, state):
        events = []
        for pid in state.players.keys():
            events.append(make_lander_token_event(pid, source_obj_id=obj.id))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    def _eff(event, state):
        return [make_lander_token_event(pid, source_obj_id=obj.id) for pid in state.players.keys()]

    interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        duration='while_on_battlefield',
    )
    return _mark_triggered_ability(interceptor, _eff, description="Lander each-player death trigger")


# =============================================================================
# === VOID HELPERS ===
# =============================================================================
# EOE Void mechanic. Engine logic in src/engine/void.py tracks
# state.turn_data['void_<player>'] each turn. These card-side helpers
# wrap that check around common trigger patterns.
from src.engine.void import is_void_active  # noqa: E402  (re-export)


def make_void_end_step_trigger(obj, effect_fn):
    """Beginning of YOUR end step: if void, run effect_fn. effect_fn(event, state) -> list[Event]."""
    def filt(event, state):
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'end':
            return False
        if state.active_player != obj.controller:
            return False
        return is_void_active(obj.controller, state)

    def handler(event, state):
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    interceptor = Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=filt, handler=handler,
        duration='while_on_battlefield',
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Void end-step trigger")


def make_void_attack_trigger(obj, effect_fn):
    """When obj attacks: if void, run effect_fn."""
    def filt(event, state):
        if event.type != EventType.ATTACK_DECLARED:
            return False
        if event.payload.get('attacker_id') != obj.id and event.payload.get('attacker') != obj.id:
            return False
        return is_void_active(obj.controller, state)

    def handler(event, state):
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    interceptor = Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=filt, handler=handler,
        duration='while_on_battlefield',
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Void attack trigger")


# =============================================================================
# === STATION HELPERS ===
# =============================================================================
# EOE Station mechanic. A Spacecraft / Planet has thresholds keyed by charge
# counter count; when count >= threshold, the card gains stats and abilities.
# Implementation: register QUERY_POWER, QUERY_TOUGHNESS, QUERY_TYPES,
# and QUERY_ABILITIES interceptors that check the current charge count and
# return the appropriate tier.
from src.engine.station import get_station_charge  # noqa: E402  (re-export)


def make_station_creature_setup(obj, thresholds):
    """Wire a Spacecraft/Planet to become a creature when charge crosses a
    threshold.

    `thresholds` is a list of (min_charge, {power, toughness, keywords})
    in ascending min_charge order. The highest-applicable tier wins.

    Example:
        thresholds = [
            (3, {'power': 4, 'toughness': 3, 'keywords': ['flying']}),
            (5, {'power': 5, 'toughness': 4, 'keywords': ['flying', 'vigilance']}),
        ]
    """
    def best_tier(state):
        charge = get_station_charge(obj)
        match = None
        for min_c, props in thresholds:
            if charge >= min_c:
                match = props
        return match

    def power_filter(event, state):
        return (event.type == EventType.QUERY_POWER
                and event.payload.get('object_id') == obj.id)

    def power_handler(event, state):
        tier = best_tier(state)
        if tier is None or 'power' not in tier:
            return InterceptorResult(action=InterceptorAction.PASS, new_events=[])
        new_event = event.copy()
        new_event.payload['value'] = tier['power']
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    def tough_filter(event, state):
        return (event.type == EventType.QUERY_TOUGHNESS
                and event.payload.get('object_id') == obj.id)

    def tough_handler(event, state):
        tier = best_tier(state)
        if tier is None or 'toughness' not in tier:
            return InterceptorResult(action=InterceptorAction.PASS, new_events=[])
        new_event = event.copy()
        new_event.payload['value'] = tier['toughness']
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    def types_filter(event, state):
        return (event.type == EventType.QUERY_TYPES
                and event.payload.get('object_id') == obj.id)

    def types_handler(event, state):
        tier = best_tier(state)
        if tier is None:
            return InterceptorResult(action=InterceptorAction.PASS, new_events=[])
        new_event = event.copy()
        types = set(new_event.payload.get('value', set()))
        types.add(CardType.CREATURE)
        new_event.payload['value'] = types
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    def kw_filter(event, state):
        return (event.type == EventType.QUERY_ABILITIES
                and event.payload.get('object_id') == obj.id)

    def kw_handler(event, state):
        tier = best_tier(state)
        if tier is None or 'keywords' not in tier:
            return InterceptorResult(action=InterceptorAction.PASS, new_events=[])
        new_event = event.copy()
        kws = set(new_event.payload.get('value', set()))
        for kw in tier['keywords']:
            kws.add(kw)
        new_event.payload['value'] = kws
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY, filter=power_filter,
                    handler=power_handler, duration='while_on_battlefield'),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY, filter=tough_filter,
                    handler=tough_handler, duration='while_on_battlefield'),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY, filter=types_filter,
                    handler=types_handler, duration='while_on_battlefield'),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY, filter=kw_filter,
                    handler=kw_handler, duration='while_on_battlefield'),
    ]


# =============================================================================
# === TURN STATE HELPERS ===
# =============================================================================
# Engine-side trackers live in src/engine/turn_state.py and are wired by
# Game._setup_system_interceptors. These card-side re-exports give card
# scripts a single import surface for "did X happen this turn" checks and
# for the coin flip primitive.
from src.engine.turn_state import (  # noqa: E402  (re-exports)
    life_gained_this_turn,
    life_lost_this_turn,
    spells_cast_this_turn,
    nth_spell_this_turn,
    attacked_alone_this_turn,
    creatures_died_this_turn,
    cards_drawn_this_turn,
    combat_damage_dealt_to_this_turn,
    cards_exiled_this_turn,
    card_was_exiled_this_turn,
    flip_coin,
    emit_coin_flip,
)


# =============================================================================
# === EOE Station + Void ===
# =============================================================================
# Edge of Eternities Station + Void mechanics.
#
# Station ("Tap an untapped creature you control: charge counters") is the
# Spacecraft / Planet activated ability. ``make_station_ability`` registers
# the printed activation and an optional threshold-gated effect that fires
# once when the charge first reaches the threshold.
#
# ``make_charge_threshold_ability`` wires the Planet "12+ | <cost>: <effect>"
# pattern — an activated ability that's only legal once charge >= 12.
#
# Void is a triggered ability gated on the per-turn condition "a card was
# exiled / a nonland permanent left the battlefield / a spell was warped".
# ``make_void_trigger`` builds the canonical "at the beginning of your end
# step, if void, ..." trigger; the engine-side condition tracking lives in
# ``src.engine.void`` and ``src.engine.turn_state``.
#
# All three helpers are thin re-exports of the mechanic modules.
from src.engine.eoe_mechanics import (  # noqa: E402  (re-exports)
    make_station_ability,
    make_charge_threshold_ability,
    make_void_trigger,
    CHARGE_COUNTER,
    add_station_charge,
    get_station_charge,
    is_stationed,
)


def make_coin_flip_event(state, player_id=None, source=None):
    """Build a COIN_FLIP marker event with a freshly-flipped result.

    Convenience wrapper around :func:`emit_coin_flip` for card scripts.
    """
    return emit_coin_flip(state, player_id=player_id, source=source)


def make_life_gain_threshold_trigger(obj, threshold, effect_fn,
                                     who="controller"):
    """Trigger when ``obj.controller`` (or "any" player) crosses a life-gained
    threshold this turn.

    Listens to LIFE_CHANGE; on the event that pushes the running total at or
    above ``threshold``, fires ``effect_fn(event, state) -> list[Event]``.
    Fires once per turn (uses turn_data flag).
    """
    flag_key = f"_life_gain_threshold_{obj.id}"

    def filt(event, state):
        if event.type != EventType.LIFE_CHANGE:
            return False
        amount = event.payload.get("amount", 0)
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return False
        if amount <= 0:
            return False
        target_player = event.payload.get("player")
        if not target_player:
            return False
        if who == "controller" and target_player != obj.controller:
            return False
        td = getattr(state, "turn_data", None) or {}
        if td.get(flag_key):
            return False
        return life_gained_this_turn(target_player, state) >= threshold

    def handler(event, state):
        td = getattr(state, "turn_data", None)
        if td is not None:
            td[flag_key] = True
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=list(effect_fn(event, state) or []),
        )

    def _eff(event, state):
        td = getattr(state, "turn_data", None)
        if td is not None:
            td[flag_key] = True
        return list(effect_fn(event, state) or [])

    interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        duration="while_on_battlefield",
    )
    return _mark_triggered_ability(interceptor, _eff, description="Life-gain threshold trigger")


def make_nth_spell_cast_trigger(obj, n, effect_fn):
    """Trigger when controller casts their Nth spell this turn (e.g. Celebration).

    ``effect_fn(event, state) -> list[Event]``. Fires whenever a CAST/SPELL_CAST
    event lifts ``spells_cast_<controller>`` to exactly ``n``. The trigger
    re-fires each turn at the Nth spell.
    """
    def filt(event, state):
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = (
            event.payload.get("caster")
            or event.payload.get("controller")
            or event.payload.get("player")
            or event.controller
        )
        if caster != obj.controller:
            return False
        # Engine tracker increments BEFORE this REACT-priority observer runs
        # because the system tracker is also REACT priority but registered
        # earlier. Defensive: also accept off-by-one.
        count = spells_cast_this_turn(caster, state)
        return count == int(n)

    def handler(event, state):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=list(effect_fn(event, state) or []),
        )

    interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        duration="while_on_battlefield",
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Nth spell cast trigger")


def make_morbid_etb_trigger(obj, effect_fn):
    """Morbid ETB: fire effect_fn only if a creature died this turn.

    ``effect_fn(event, state) -> list[Event]``.
    """
    def filt(event, state):
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get("object_id") != obj.id:
            return False
        if event.payload.get("to_zone_type") != ZoneType.BATTLEFIELD:
            return False
        return creatures_died_this_turn(state) >= 1

    def handler(event, state):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=list(effect_fn(event, state) or []),
        )

    interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        duration="while_on_battlefield",
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Morbid ETB trigger")


def make_attacks_alone_trigger(obj, effect_fn):
    """Trigger when ``obj`` attacks alone (and that's its controller's only
    attacker this turn).

    ``effect_fn(event, state) -> list[Event]``. Reads
    ``attacked_alone_<controller>`` after COMBAT_DECLARED so the answer is
    authoritative for the just-declared combat step.
    """
    def filt(event, state):
        if event.type != EventType.COMBAT_DECLARED:
            return False
        attacking_player = event.payload.get("attacking_player")
        if attacking_player != obj.controller:
            return False
        attackers = event.payload.get("attackers") or []
        if list(attackers) != [obj.id]:
            return False
        return True

    def handler(event, state):
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=list(effect_fn(event, state) or []),
        )

    interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        duration="while_on_battlefield",
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Attacks alone trigger")


# =============================================================================
# === FACE-DOWN HELPERS ===
# =============================================================================
# Manifest / Manifest Dread / Cloak / Disguise / Morph all share one mechanism:
#
#   1. Some game action turns a card into a face-down 2/2 colourless creature
#      with no name, no abilities (and, for Disguise/Morph, ward {2}).
#   2. The face-down permanent's *real* card_def is preserved on the GameObject;
#      its real characteristics are masked by QUERY interceptors.
#   3. The controller can pay a face-up cost at any time (instant speed for
#      Manifest/Cloak's underlying creature card; specific cost for the others)
#      to turn it face-up. The flip removes the masking interceptors and
#      re-runs ``card_def.setup_interceptors`` so the card's real abilities
#      come online (ETB triggers fire — see CR 707.4).
#
# Engine-side support lives in ``src/engine/face_down.py``. The helpers below
# are the card-author-facing API.
from src.engine.face_down import (  # noqa: E402  (re-export)
    FACE_DOWN_TAG,
    DEFAULT_FACE_DOWN_POWER,
    DEFAULT_FACE_DOWN_TOUGHNESS,
    is_face_down,
    turn_face_up,
    register_face_down_handler,
    make_face_down_object,
)


def _face_down_query_interceptors(
    obj: GameObject,
    *,
    face_down_power: int = DEFAULT_FACE_DOWN_POWER,
    face_down_toughness: int = DEFAULT_FACE_DOWN_TOUGHNESS,
    face_down_keywords: Optional[list[str]] = None,
) -> list[Interceptor]:
    """
    Build the set of QUERY interceptors that mask a face-down permanent.

    Each interceptor only fires while ``obj.state.face_down`` is True so flipping
    the card face-up immediately reveals its real characteristics, even before
    the masking interceptors get cleaned up.

    The returned interceptors are tagged ``_face_down_tag = FACE_DOWN_TAG`` so
    :func:`turn_face_up` can identify and remove them.
    """
    face_down_keywords = list(face_down_keywords or [])

    def _active() -> bool:
        return is_face_down(obj)

    # --- POWER ---
    def power_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_POWER
                and event.payload.get('object_id') == obj.id
                and _active())

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['value'] = face_down_power
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # --- TOUGHNESS ---
    def tough_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_TOUGHNESS
                and event.payload.get('object_id') == obj.id
                and _active())

    def tough_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['value'] = face_down_toughness
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # --- TYPES (face-down: just creature, no subtypes) ---
    def types_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_TYPES
                and event.payload.get('object_id') == obj.id
                and _active())

    def types_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['value'] = {CardType.CREATURE}
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # --- COLORS (face-down: colourless) ---
    def colors_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_COLORS
                and event.payload.get('object_id') == obj.id
                and _active())

    def colors_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['value'] = set()  # colourless
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # --- ABILITIES (face-down: only the granted keywords, if any) ---
    def abilities_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_ABILITIES
                and event.payload.get('object_id') == obj.id
                and _active())

    def abilities_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        # `value` may be either a list of ability dicts or a set/list of keyword
        # strings depending on the caller. Normalize to a set of granted keyword
        # names — this matches how `make_keyword_grant`-style helpers expose
        # face-down-specific keywords like Disguise's ward {2}.
        granted = set(face_down_keywords)
        new_event.payload['value'] = granted
        new_event.payload['granted'] = granted
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    interceptors = []
    for filt, hand in (
        (power_filter, power_handler),
        (tough_filter, tough_handler),
        (types_filter, types_handler),
        (colors_filter, colors_handler),
        (abilities_filter, abilities_handler),
    ):
        ic = Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=filt,
            handler=hand,
            duration='while_on_battlefield',
        )
        # Tag so turn_face_up() can identify and strip these specifically
        # (rather than wiping every QUERY interceptor on the object, which
        # would also nuke things like +1/+1 counter-derived abilities).
        setattr(ic, '_face_down_tag', FACE_DOWN_TAG)
        interceptors.append(ic)

    return interceptors


def make_face_down_setup(
    obj: GameObject,
    face_up_cost: Optional[str] = None,
    face_up_handler: Optional[Callable[[GameObject, GameState], list[Event]]] = None,
    *,
    face_down_power: int = DEFAULT_FACE_DOWN_POWER,
    face_down_toughness: int = DEFAULT_FACE_DOWN_TOUGHNESS,
    face_down_keywords: Optional[list[str]] = None,
) -> list[Interceptor]:
    """
    Mask a permanent so it acts as a face-down 2/2.

    Sets ``obj.state.face_down = True`` and registers the QUERY-masking
    interceptors. If ``face_up_cost`` is provided, also stores a callable on
    ``obj.state`` (``pay_face_up_cost``) that the controller can invoke to flip
    the card. ``face_up_handler(obj, state)`` runs *after* the flip and may
    return any extra events (e.g. "manifest dread: search for a card").

    Returns the new interceptors so the caller can prepend them to its own
    list (or use this directly as a card's ``setup_interceptors``).

    Example:
        def my_card_setup(obj, state):
            return make_face_down_setup(obj, face_up_cost="{2}")
    """
    obj.state.face_down = True

    # Stash the face-up activation as a closure on obj.state. Activated abilities
    # in this engine don't have a uniform action payload yet — exposing the
    # closure here lets card-side helpers (or the server's ability dispatcher)
    # invoke it without needing to know the card's specific cost.
    def pay_face_up_cost(state: GameState) -> list[Event]:
        if not is_face_down(obj):
            return []  # Already face-up; activation does nothing.

        # Best-effort cost payment. Card-script callers may have already paid
        # the cost via the priority/casting subsystem; in that case face_up_cost
        # is treated as informational.
        if face_up_cost:
            try:
                from src.engine.mana import ManaSystem, parse_cost
                if isinstance(state, GameState) and hasattr(state, 'objects'):
                    # State may not have a mana system; we look for one if available.
                    mana_sys = getattr(state, 'mana_system', None)
                    if mana_sys is not None:
                        cost = parse_cost(face_up_cost)
                        if not mana_sys.pay_cost(obj.controller, cost):
                            return []  # Could not pay; abort.
            except Exception:
                # Don't block flipping if mana plumbing isn't available in this
                # context (e.g. a unit test). The TURN_FACE_UP event itself
                # records the intended cost.
                pass

        events: list[Event] = [Event(
            type=EventType.TURN_FACE_UP,
            payload={
                'object_id': obj.id,
                'mana_paid_cost': face_up_cost,
            },
            source=obj.id,
            controller=obj.controller,
        )]

        if face_up_handler is not None:
            try:
                extra = face_up_handler(obj, state) or []
                events.extend(extra)
            except Exception:
                # A misbehaving handler shouldn't strand the card face-down.
                pass

        return events

    obj.state.pay_face_up_cost = pay_face_up_cost  # type: ignore[attr-defined]
    obj.state.face_up_cost = face_up_cost          # type: ignore[attr-defined]

    return _face_down_query_interceptors(
        obj,
        face_down_power=face_down_power,
        face_down_toughness=face_down_toughness,
        face_down_keywords=face_down_keywords,
    )


def make_manifest_etb_event(
    controller: str,
    source_id: Optional[str] = None,
    *,
    card_def=None,
    face_down_power: int = DEFAULT_FACE_DOWN_POWER,
    face_down_toughness: int = DEFAULT_FACE_DOWN_TOUGHNESS,
) -> Event:
    """
    Build an OBJECT_CREATED event that summons a face-down 2/2 creature on the
    battlefield.

    The created object will be processed through the standard pipeline:
    ``_handle_object_created`` runs first (creating the GameObject + zoning it),
    then a separate ``ZONE_CHANGE`` follow-up — emitted by callers that need ETB
    triggers — installs the masking interceptors. Most callers should follow
    the simpler pattern:

        events = [
            make_manifest_etb_event(player_id, source_id=source.id, card_def=top),
            Event(type=EventType.FACE_DOWN_ENTER, payload={'controller': player_id}),
        ]

    Pass ``card_def`` (the top of library card, etc.) to preserve the real card
    underneath; ``turn_face_up`` will re-run its ``setup_interceptors`` on flip.
    """
    return Event(
        type=EventType.OBJECT_CREATED,
        payload={
            'controller': controller,
            'owner': controller,
            'name': '',                      # face-down has no public name
            'zone_type': ZoneType.BATTLEFIELD,
            'types': {CardType.CREATURE},
            'subtypes': set(),
            'colors': set(),
            'power': face_down_power,
            'toughness': face_down_toughness,
            'is_token': False,
            'face_down': True,
            'card_def': card_def,           # for pipeline.zone handler use (best-effort)
        },
        source=source_id,
        controller=controller,
    )


# =============================================================================
# Phase 5b: Disguise / Cloak / face-up trigger helpers
# =============================================================================
#
# Disguise (MKM) and Cloak (DSK) put a card onto the battlefield face down as a
# 2/2 with ward {2}, then let the controller flip it face-up later for its
# disguise / mana cost. The pipeline already supports the flip itself through
# ``EventType.TURN_FACE_UP`` (resolved in ``src/engine/face_down.py``). What was
# missing was an ergonomic card-author surface:
#
#   * ``make_turned_face_up_trigger(obj, effect_fn, *, self_or_other_yours)`` —
#     "Whenever this creature [or another creature you control] is turned face
#     up, …". Cards like Pyrotechnic Performer (MKM) and Growing Dread (DSK)
#     express this pattern.
#   * ``make_disguise_setup(*, disguise_cost)`` — register the activated ability
#     "{disguise_cost}: Turn this face up." while the permanent is face-down.
#
# Both helpers are thin wrappers around the existing TURN_FACE_UP event +
# masking machinery in ``face_down.py``.
# =============================================================================


def make_turned_face_up_trigger(
    obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    *,
    self_or_other_yours: str = "self",
    description: str = "",
) -> Interceptor:
    """
    Register a triggered ability that fires when a creature is turned face up.

    ``self_or_other_yours`` controls which flips fire the trigger:

      * ``"self"`` (default) — only when *this* creature is turned face up
        (i.e. the TURN_FACE_UP's ``object_id`` equals ``obj.id``).
        Use for "When this creature is turned face up, …" wording.
      * ``"both"`` — when this creature OR any other creature controlled by
        ``obj.controller`` is turned face up. Use for "Whenever this creature
        or another creature you control is turned face up, …" (e.g.
        Pyrotechnic Performer, MKM).
      * ``"controller"`` — any creature controlled by ``obj.controller``
        (no requirement that the flipped object is/isn't ``obj`` itself).
        Equivalent to ``"both"`` in practice; provided for spec clarity.

    The trigger handler routes through the standard React→effect_fn path the
    pipeline already uses for triggered abilities. Effect_fn receives the
    TURN_FACE_UP event so the handler can inspect which creature flipped
    (``event.payload['object_id']``) — e.g. "that creature deals damage equal
    to its power".

    Returns a single Interceptor; setup_interceptors functions typically wrap
    this in ``[ ... ]``.
    """
    if self_or_other_yours not in {"self", "both", "controller"}:
        raise ValueError(
            f"self_or_other_yours must be 'self', 'both', or 'controller'; "
            f"got {self_or_other_yours!r}"
        )

    def filter_fn(event: Event, state: GameState) -> bool:
        if event.type != EventType.TURN_FACE_UP:
            return False
        target_id = event.payload.get('object_id')
        if not target_id:
            return False
        # Self-only: only fire when this exact object flips.
        if self_or_other_yours == "self":
            return target_id == obj.id
        # "both" / "controller": fire when any of obj.controller's creatures
        # flips. (Self counts.)
        target = state.objects.get(target_id)
        if target is None:
            return False
        if target.controller != obj.controller:
            return False
        # Must still be on the battlefield (defensive — turn_face_up only
        # operates on battlefield permanents but late triggers could see
        # post-flip state).
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        return True

    def handler(event: Event, state: GameState) -> InterceptorResult:
        # ``effect_fn`` may return a list directly (preferred) or a falsy
        # value if there's nothing to do (e.g. no legal targets).
        new_events = effect_fn(event, state) or []
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        duration='while_on_battlefield',
    )
    return _mark_triggered_ability(interceptor, effect_fn, description=description)


def make_disguise_setup(
    obj: GameObject,
    *,
    disguise_cost: str,
    face_up_handler: Optional[Callable[[GameObject, GameState], list[Event]]] = None,
) -> list[Interceptor]:
    """
    Register Disguise on a permanent.

    Disguise (MKM): "Disguise {cost} (You may cast this card face down for {3}
    as a 2/2 creature with ward {2}. Turn it face up any time for its disguise
    cost.)"

    This helper currently focuses on the **face-up activation** side: while
    ``obj`` is on the battlefield, register an activated ability
    "{disguise_cost}: Turn this face up." that flips the permanent face-up by
    emitting ``EventType.TURN_FACE_UP``. The flip path is implemented in
    :func:`src.engine.face_down.turn_face_up` — it strips the masking
    interceptors, restores characteristics, and fires ETB-style triggers
    (including any ``make_turned_face_up_trigger`` registered on this card or
    on other permanents).

    The alt-cast face-down path is a CASTING-layer concern (the player
    declares "cast face-down for {3}"); it is handled by the priority
    subsystem via ``make_face_down_setup``. Cards that wish to register both
    paths can compose these helpers — see the wired MKM cards below.

    Args:
        obj: the permanent (battlefield-side instance).
        disguise_cost: the mana-string cost to flip face-up (e.g. ``"{R}"``).
        face_up_handler: optional extra hook that runs *during* the flip
            activation; mostly redundant since ``make_turned_face_up_trigger``
            handles the "when turned face up" effect more cleanly.

    Returns an empty list of interceptors — the disguise activated ability is
    registered on ``obj.state.activated_abilities`` rather than as a pipeline
    interceptor. Callers should still ``return ... + []`` or simply call this
    for side effects.
    """
    if not disguise_cost:
        raise ValueError("make_disguise_setup requires a disguise_cost")

    def flip_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        # Only meaningful while face-down. (Engine quietly no-ops if the
        # permanent is already face-up — guarded here for defensive clarity.)
        if not is_face_down(o):
            return []
        events: list[Event] = [Event(
            type=EventType.TURN_FACE_UP,
            payload={
                'object_id': o.id,
                'mana_paid_cost': disguise_cost,
                'disguise': True,
            },
            source=o.id,
            controller=o.controller,
        )]
        if face_up_handler is not None:
            try:
                extra = face_up_handler(o, st) or []
                events.extend(extra)
            except Exception:
                # Don't strand the flip if the optional handler misbehaves.
                pass
        return events

    def is_face_down_precondition(o: GameObject, st: GameState) -> bool:
        # The disguise activation is only legal while the card is face-down.
        return is_face_down(o)

    make_activated_ability(
        obj,
        cost=disguise_cost,
        effect_fn=flip_effect,
        description=f"Disguise {disguise_cost} — turn face up",
        precondition_fn=is_face_down_precondition,
    )
    return []


# =============================================================================
# Phase 4: Activated-ability helpers
# =============================================================================
#
# Cards expose activated abilities by registering descriptors on
# ``obj.state.activated_abilities``. The priority system in ``priority.py``
# enumerates them in ``_get_activatable_abilities`` and dispatches in
# ``_handle_activate_ability``.
#
# Effect signature: ``(obj, state, targets) -> list[Event]``. ``targets`` is a
# flat list of ``Target`` objects already chosen by the player (or empty when
# no targeting was needed).
# =============================================================================


def make_activated_ability(
    obj: GameObject,
    cost: str,
    effect_fn: Callable[[GameObject, GameState, list], list[Event]],
    *,
    description: str = "",
    sorcery_speed: bool = False,
    own_turn_only: bool = False,
    once_per_turn: bool = False,
    once_per_game: bool = False,
    targets_required: int = 0,
    target_kind: str = "any",
    target_requirements: Optional[list] = None,
    precondition_fn: Optional[Callable[[GameObject, GameState], bool]] = None,
):
    """Register an activated ability on ``obj`` and return the descriptor.

    Use inside a ``setup_interceptors`` function. The setup function should
    still return ``[]`` (or any other interceptors it wants to register) — the
    activated ability is consulted via ``obj.state.activated_abilities``, not
    via the event pipeline.

    Phase 5b: ``target_requirements`` (a list of ``TargetRequirement |
    TargetRequirementBuilder``, same shape as ``CardDefinition.target_requirements``)
    routes the ability through the engine-authoritative cast-time target picker.
    The priority handler emits a ``PendingChoice`` before paying costs, mirroring
    CR 602.1 (announce → choose targets → pay costs). Legacy abilities omit
    ``target_requirements`` and continue to work the old way (no validation,
    pre-supplied ``action.targets`` only).

    Example::

        def cathar_commando_setup(obj, state):
            def destroy_target(o, st, targets):
                if not targets:
                    return []
                return [Event(type=EventType.DESTROY,
                              payload={'object_id': targets[0].object_id},
                              source=o.id, controller=o.controller)]
            make_activated_ability(
                obj,
                cost="{1}, Sacrifice this creature",
                effect_fn=destroy_target,
                description="Destroy target artifact or enchantment",
                targets_required=1,
                target_kind="artifact_or_enchantment",
            )
            return []
    """
    from src.engine.activated import register_activated_ability
    return register_activated_ability(
        obj,
        cost=cost,
        effect_fn=effect_fn,
        description=description,
        sorcery_speed=sorcery_speed,
        own_turn_only=own_turn_only,
        once_per_turn=once_per_turn,
        once_per_game=once_per_game,
        targets_required=targets_required,
        target_kind=target_kind,
        target_requirements=target_requirements,
        precondition_fn=precondition_fn,
    )


def make_exhaust_ability(
    obj: GameObject,
    cost: str,
    effect_fn: Callable[[GameObject, GameState, list], list[Event]],
    *,
    description: str = "",
    sorcery_speed: bool = False,
    own_turn_only: bool = False,
    targets_required: int = 0,
    target_kind: str = "any",
):
    """Register an Exhaust ability — activate at most once per permanent, ever.

    Exhaust is from Aetherdrift / Avatar: TLA. The ability is written
    "Exhaust — {cost}: <effect>" and includes the reminder
    "(Activate each exhaust ability only once.)". Once activated, the same
    ability descriptor cannot be re-activated on the same permanent — even
    across turns. A new permanent (different ``obj.id``, e.g. recasting from
    the graveyard or a fresh copy) registers its own descriptor and starts
    fresh.

    The description is prefixed with ``Exhaust — `` to make the legal-action
    surface readable to humans and AIs.
    """
    desc = description or f"{cost}: ..."
    if not desc.lower().startswith("exhaust"):
        desc = f"Exhaust — {desc}"
    return make_activated_ability(
        obj,
        cost=cost,
        effect_fn=effect_fn,
        description=desc,
        sorcery_speed=sorcery_speed,
        own_turn_only=own_turn_only,
        once_per_game=True,
        targets_required=targets_required,
        target_kind=target_kind,
    )


def make_exhaust_reset_effect(
    source: GameObject,
    state: GameState,
    *,
    target_id: Optional[str] = None,
    ability_index: Optional[int] = None,
    controller: Optional[str] = None,
) -> list[Event]:
    """Reset Exhaust ability descriptors and emit an EXHAUST_RESET marker.

    Use this inside an effect_fn for cards like Aetherdrift's Elvish
    Refueler that say "you may activate exhaust abilities as though they
    hadn't been activated." The function:

    1. Calls ``reset_exhaust`` immediately so the ``once_per_game_used``
       flag is cleared before legal-action generation re-runs.
    2. Returns a single ``EXHAUST_RESET`` marker event so observers /
       logs / UI can react.

    Filters (most specific to least):
      - ``target_id`` + ``ability_index``: reset that one descriptor.
      - ``target_id``: reset every Exhaust ability on that permanent.
      - ``controller``: reset every Exhaust ability that player controls.
      - none: reset every Exhaust ability in the game.

    Example (whole-controller reset)::

        def elvish_refueler_effect(o, st, targets):
            return make_exhaust_reset_effect(o, st, controller=o.controller)
    """
    from src.engine.activated import reset_exhaust as _reset_exhaust
    _reset_exhaust(
        state,
        target_id=target_id,
        ability_index=ability_index,
        controller=controller,
    )
    payload: dict = {}
    if target_id is not None:
        payload["target_id"] = target_id
    if ability_index is not None:
        payload["ability_index"] = ability_index
    if controller is not None:
        payload["controller"] = controller
    return [Event(
        type=EventType.EXHAUST_RESET,
        payload=payload,
        source=source.id,
        controller=source.controller,
    )]


# =============================================================================
# Planeswalker loyalty
# =============================================================================
#
# Re-exports from ``src/engine/planeswalker.py``. Card scripts wire
# ``make_planeswalker_setup`` for ETB / damage redirection / once-per-turn
# bookkeeping, then call ``make_loyalty_ability`` once per loyalty ability.
#
# Typical usage::
#
#     def ral_setup(obj, state):
#         interceptors = make_planeswalker_setup(obj, starting_loyalty=4)
#
#         def plus1_effect(o, st, targets):
#             # +1: Create a 1/1 blue and red Otter creature token with prowess.
#             return [Event(type=EventType.CREATE_TOKEN, ...)]
#         make_loyalty_ability(
#             obj, cost=+1, effect_fn=plus1_effect, ability_id="+1",
#         )
#
#         def minus3_effect(o, st, targets):
#             # -3: Draw three cards, then discard two cards.
#             return [
#                 Event(type=EventType.DRAW, payload={'player': o.controller, 'count': 3}),
#                 Event(type=EventType.DISCARD_CHOICE, payload={'player': o.controller, 'count': 2}),
#             ]
#         make_loyalty_ability(
#             obj, cost=-3, effect_fn=minus3_effect, ability_id="-3",
#         )
#
#         return interceptors
#
# CR 113.5g (damage redirection), 606 (loyalty abilities), 716 (planeswalkers):
# the helpers handle ETB starting loyalty, damage-to-loyalty redirection, the
# once-per-turn-per-planeswalker activation lock, and pre-validation of
# negative loyalty costs (planeswalker must have >= |cost| loyalty). The
# 0-loyalty SBA (planeswalker destroyed when loyalty hits 0) lives in the
# state-based-actions hook in src/engine/turn.py.
# -----------------------------------------------------------------------------

from src.engine.planeswalker import (
    make_loyalty_ability,
    make_planeswalker_setup,
    planeswalkers_with_zero_loyalty,
    get_loyalty,
    is_planeswalker,
    planeswalkers_controlled_by,
    redirect_attack_to_planeswalker,
    redirect_damage_to_planeswalker,
)


# =============================================================================
# W15: Emblems (CR 113.1c)
# =============================================================================
#
# Emblems are persistent global effects with no characteristics other than
# "Emblem". They never leave play. Created by planeswalker ultimates ("you
# get an emblem with...").
#
# Helper API:
#
#   make_emblem_setup(name, static_effects_fn) -> callable
#
# The returned callable takes ``(state, controller, source_id) -> list[Event]``
# and is intended to be called from a loyalty ability's effect_fn::
#
#       def minus10_effect(o, state, targets):
#           setup_fn = make_emblem_setup(
#               name="Ral Emblem",
#               text='Whenever you cast an instant or sorcery, this emblem deals 4 damage to any target.',
#               static_effects_fn=ral_emblem_statics,
#           )
#           return setup_fn(state, o.controller, o.id)
#
# ``static_effects_fn(emblem, state) -> list[Interceptor]`` builds the static
# interceptors. Their ``source`` defaults to the emblem's id, their
# ``controller`` to the emblem's controller, and their ``duration`` is forced
# to ``"forever"`` so they survive battlefield sweeps and end-of-turn cleanup.
#
# Emblems live on ``state.emblems``. Lookup helpers are exported from
# ``src.engine.emblem``.
# -----------------------------------------------------------------------------

from src.engine.emblem import (
    Emblem,
    create_emblem,
    get_emblems,
    get_emblems_for_player,
)


def make_emblem_setup(
    *,
    source_card_name: str,
    static_effects_fn: Callable[["Emblem", GameState], list[Interceptor]],
    name: str = "",
    text: str = "",
):
    """Return a callable usable as the body of a planeswalker ultimate.

    The returned function has signature
    ``(state, controller, source_id) -> list[Event]`` and creates the emblem
    + registers its interceptors as a side-effect, returning an
    EMBLEM_CREATED marker event for the caller to bubble back to the
    pipeline.
    """
    def _create(state: GameState, controller: str, source_id: Optional[str] = None) -> list[Event]:
        _emblem, events = create_emblem(
            state,
            controller=controller,
            source_id=source_id,
            source_card_name=source_card_name,
            static_effects_fn=static_effects_fn,
            name=name,
            text=text,
        )
        return events

    return _create


def make_emblem_creatures_have_keywords(
    *,
    source_card_name: str,
    keywords: list[str],
    name: str = "",
):
    """Common emblem pattern: "Creatures you control have <keyword(s)>".

    Builds an emblem whose static QUERY_ABILITIES interceptor grants the
    listed keywords to creatures controlled by the emblem's owner. Used by
    Ajani, Caller of the Pride's -8 ultimate (in spirit; see card text).
    """
    text = f"Creatures you control have {', '.join(keywords)}."

    def _statics(emblem, state):
        controller = emblem.controller

        def _filter(event: Event, st: GameState) -> bool:
            if event.type != EventType.QUERY_ABILITIES:
                return False
            target_id = event.payload.get('object_id')
            target = st.objects.get(target_id)
            if not target:
                return False
            if target.controller != controller:
                return False
            if target.zone != ZoneType.BATTLEFIELD:
                return False
            from src.engine.queries import is_creature
            if not is_creature(target, st):
                return False
            return True

        def _handler(event: Event, st: GameState) -> InterceptorResult:
            new_event = event.copy()
            granted = list(new_event.payload.get('granted', []))
            for kw in keywords:
                if kw not in granted:
                    granted.append(kw)
            new_event.payload['granted'] = granted
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event,
            )

        return [Interceptor(
            id=new_id(),
            source=emblem.id,
            controller=controller,
            priority=InterceptorPriority.QUERY,
            filter=_filter,
            handler=_handler,
            duration='forever',
        )]

    return make_emblem_setup(
        source_card_name=source_card_name,
        static_effects_fn=_statics,
        name=name,
        text=text,
    )


# =============================================================================
# Tiered cost (FIN)
# =============================================================================
#
# Re-exports from ``src/engine/tiered.py``. Card scripts wire ``make_tiered_setup``
# on ``setup_interceptors`` and ``make_tiered_resolve`` on the card def's
# ``resolve=`` so the chosen tier's effect_fn fires on resolution.
#
# Typical usage::
#
#     def fire_magic_setup(obj, state):
#         tiers = [
#             TierDefinition(name="Fire",   extra_cost="{0}", effect_fn=fire_fn,
#                            description="Deal 1 to each creature"),
#             TierDefinition(name="Fira",   extra_cost="{2}", effect_fn=fira_fn,
#                            description="Deal 2 to each creature"),
#             TierDefinition(name="Firaga", extra_cost="{5}", effect_fn=firaga_fn,
#                            description="Deal 3 to each creature"),
#         ]
#         return make_tiered_setup(obj, tiers=tiers)
#
#     FIRE_MAGIC = make_instant(
#         name="Fire Magic", mana_cost="{R}", colors={Color.RED},
#         text="Tiered ...",
#         setup_interceptors=fire_magic_setup,
#         resolve=make_tiered_resolve(_FIRE_MAGIC_TIERS),
#     )
# -----------------------------------------------------------------------------

from src.engine.tiered import (
    TierDefinition,
    make_tiered_setup,
    make_tiered_resolve,
    compute_affordable_tiers,
    get_chosen_tier_index,
    get_chosen_tier_indices,
    clear_chosen_tier,
)


# =============================================================================
# EXHAUST-ECOSYSTEM HELPERS
# =============================================================================
#
# Two helpers for cards that *react* to or *transform* exhaust ability costs,
# rather than registering an exhaust ability directly.
#
#   - ``make_activate_exhaust_trigger``: react to any exhaust-ability
#     ACTIVATE event (Rangers' Refueler / Afterburner Expert pattern).
#   - ``make_activated_cost_reduction``: register a TRANSFORM-priority
#     interceptor on QUERY_ACTIVATION_COST that reduces the generic mana
#     portion of a matching ability's cost (Boom Scholar pattern).
# -----------------------------------------------------------------------------


def make_activate_exhaust_trigger(
    obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    *,
    controller_only: bool = True,
    while_in_zone: Optional[Any] = None,
) -> Interceptor:
    """React when an exhaust ability is activated by ``obj``'s controller.

    Args:
        obj: the card with the trigger (Rangers' Refueler, Afterburner Expert).
        effect_fn: ``(event, state) -> list[Event]``. The triggered effect.
        controller_only: when True (default), only fires for activations by
            ``obj.controller``. Set False to react to any player's exhaust
            activation.
        while_in_zone: when not None, restrict the trigger to fire only while
            ``obj`` is in this zone (e.g. ``ZoneType.GRAVEYARD`` for
            Afterburner Expert's "...from your graveyard..." reaction).

    The trigger uses the new ``is_exhaust`` payload key emitted by
    ``priority._handle_activate_ability`` on every ``EventType.ACTIVATE``.
    """
    obj_id = obj.id
    obj_controller = obj.controller

    def _filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ACTIVATE:
            return False
        if not event.payload.get('is_exhaust', False):
            return False
        if controller_only and event.payload.get('controller') != obj_controller:
            return False
        if while_in_zone is not None:
            current = state.objects.get(obj_id)
            if current is None or current.zone != while_in_zone:
                return False
        return True

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        try:
            new_events = effect_fn(event, state) or []
        except Exception:
            new_events = []
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=list(new_events),
        )

    # Pick a sensible duration so the interceptor is gated correctly when the
    # source moves zones. Battlefield triggers use the standard
    # ``while_on_battlefield`` duration so they're swept by
    # ``_cleanup_departed_interceptors`` when the card leaves play. Graveyard
    # triggers (Afterburner Expert) need a non-battlefield duration so they're
    # NOT swept when the card enters the graveyard; the filter itself gates by
    # zone via ``while_in_zone``.
    if while_in_zone is None or while_in_zone is ZoneType.BATTLEFIELD:
        duration = 'while_on_battlefield'
    else:
        duration = 'forever'

    interceptor = Interceptor(
        id=new_id(),
        source=obj_id,
        controller=obj_controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration=duration,
    )
    return _mark_triggered_ability(interceptor, effect_fn, description="Exhaust-activate trigger")


def make_activated_cost_reduction(
    obj: GameObject,
    *,
    amount,
    applies_filter: Callable[[Any, Any, GameState], bool],
) -> Interceptor:
    """Reduce activated-ability mana costs (generic only) when ``applies_filter`` matches.

    Used for Boom Scholar and similar "[matched abilities] cost {N} less to
    activate" effects. Coloured pips are never reduced.

    Args:
        obj: the source permanent (e.g. Boom Scholar).
        amount: int reduction (or callable ``(ability, source, state) -> int``).
        applies_filter: ``(ability, source, state) -> bool`` predicate.
            Return True iff the reduction applies to the queried activation.

    Implementation is a TRANSFORM-priority interceptor on
    ``EventType.QUERY_ACTIVATION_COST`` consumed by
    ``cost_query.get_effective_activation_cost``.
    """
    from src.engine.cost_query import REDUCTION_KEY

    source_id = obj.id

    def _filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_ACTIVATION_COST:
            return False
        # Only fire while the source is on the battlefield (unless it's been
        # removed mid-evaluation; safer to gate explicitly).
        src = state.objects.get(source_id)
        if not src or src.zone != ZoneType.BATTLEFIELD:
            return False
        try:
            return bool(applies_filter(
                event.payload.get('ability'),
                event.payload.get('source'),
                state,
            ))
        except Exception:
            return False

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        try:
            if callable(amount):
                amt = int(amount(
                    event.payload.get('ability'),
                    event.payload.get('source'),
                    state,
                ) or 0)
            else:
                amt = int(amount or 0)
        except (TypeError, ValueError):
            amt = 0
        if amt <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        new_event = event.copy()
        running = int(new_event.payload.get(REDUCTION_KEY, 0))
        new_event.payload[REDUCTION_KEY] = running + amt
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    return Interceptor(
        id=new_id(),
        source=source_id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=_filter,
        handler=_handler,
        duration='while_on_battlefield',
    )


def make_pump_self_ability(
    obj: GameObject,
    cost: str,
    *,
    power_mod: int = 1,
    toughness_mod: int = 0,
    grant_keyword: Optional[str] = None,
    description: str = "",
    once_per_turn: bool = False,
):
    """Register ``{cost}: This creature gets +X/+Y [and gains <keyword>] until end of turn``."""
    desc = description or f"+{power_mod}/+{toughness_mod} until end of turn"
    if grant_keyword:
        desc = f"{desc} and gains {grant_keyword}"

    def _effect(o: GameObject, state: GameState, targets) -> list[Event]:
        events: list[Event] = []
        if power_mod or toughness_mod:
            events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': o.id,
                    'power_mod': power_mod,
                    'toughness_mod': toughness_mod,
                    'duration': 'end_of_turn',
                },
                source=o.id,
                controller=o.controller,
            ))
        if grant_keyword:
            events.append(Event(
                type=EventType.GRANT_KEYWORD,
                payload={
                    'object_id': o.id,
                    'keyword': grant_keyword,
                    'duration': 'end_of_turn',
                },
                source=o.id,
                controller=o.controller,
            ))
        return events

    return make_activated_ability(
        obj, cost=cost, effect_fn=_effect,
        description=desc, once_per_turn=once_per_turn,
    )


def make_draw_ability(
    obj: GameObject,
    cost: str,
    count: int = 1,
    *,
    description: str = "",
    sorcery_speed: bool = False,
    once_per_turn: bool = False,
):
    """Register ``{cost}: Draw N cards``."""
    desc = description or (f"Draw {count} cards" if count > 1 else "Draw a card")

    def _effect(o: GameObject, state: GameState, targets) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': o.controller, 'count': count},
            source=o.id,
            controller=o.controller,
        )]

    return make_activated_ability(
        obj, cost=cost, effect_fn=_effect,
        description=desc, sorcery_speed=sorcery_speed, once_per_turn=once_per_turn,
    )


def make_loot_ability(
    obj: GameObject,
    cost: str,
    *,
    description: str = "",
    once_per_turn: bool = False,
):
    """Register ``{cost}: Draw a card, then discard a card`` (looting)."""
    desc = description or "Draw a card, then discard a card"

    def _effect(o: GameObject, state: GameState, targets) -> list[Event]:
        return [
            Event(
                type=EventType.DRAW,
                payload={'player': o.controller, 'count': 1},
                source=o.id, controller=o.controller,
            ),
            Event(
                type=EventType.DISCARD_CHOICE,
                payload={'player': o.controller, 'count': 1},
                source=o.id, controller=o.controller,
            ),
        ]

    return make_activated_ability(
        obj, cost=cost, effect_fn=_effect,
        description=desc, once_per_turn=once_per_turn,
    )


def make_surveil_ability(
    obj: GameObject,
    cost: str,
    surveil_n: int = 1,
    *,
    description: str = "",
    sorcery_speed: bool = False,
    once_per_turn: bool = False,
):
    """Register ``{cost}: Surveil N`` activated ability.

    Used by Spider-Man hideout lands and similar. Emits a SURVEIL event
    that opens a player choice for which of the top N to graveyard.
    """
    desc = description or f"Surveil {surveil_n}"

    def _effect(o: GameObject, state: GameState, targets) -> list[Event]:
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': o.controller, 'amount': surveil_n},
            source=o.id, controller=o.controller,
        )]

    return make_activated_ability(
        obj, cost=cost, effect_fn=_effect,
        description=desc, sorcery_speed=sorcery_speed, once_per_turn=once_per_turn,
    )


def make_lifeland_setup(amount: int = 1):
    """Return a setup_interceptors function for ETB-life-gain lands.

    Pattern: "This land enters tapped. When this land enters, you gain N life."
    The ETB-tapped flag is auto-detected from card text by ``_handle_play_land``;
    this helper only wires the life-gain trigger.
    """
    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        def _gain_life(event: Event, state: GameState) -> list[Event]:
            return [Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': amount},
                source=obj.id,
            )]
        return [make_etb_trigger(obj, _gain_life)]
    return _setup


def make_life_gain_ability(
    obj: GameObject,
    cost: str,
    amount: int,
    *,
    description: str = "",
    once_per_turn: bool = False,
):
    """Register ``{cost}: You gain N life``."""
    desc = description or f"You gain {amount} life"

    def _effect(o: GameObject, state: GameState, targets) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': o.controller, 'amount': amount},
            source=o.id, controller=o.controller,
        )]

    return make_activated_ability(
        obj, cost=cost, effect_fn=_effect,
        description=desc, once_per_turn=once_per_turn,
    )


def make_damage_ability(
    obj: GameObject,
    cost: str,
    damage: int,
    *,
    description: str = "",
    target_kind: str = "any",
    sorcery_speed: bool = False,
    once_per_turn: bool = False,
):
    """Register ``{cost}: Deal N damage to <target>``.

    Target choice is provided by the caller via the standard targeting flow;
    the resolve callback reads the first target and emits a DAMAGE event.
    """
    desc = description or f"Deal {damage} damage to any target"

    def _effect(o: GameObject, state: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or getattr(t, "player_id", None) or t
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': damage, 'source': o.id},
            source=o.id, controller=o.controller,
        )]

    return make_activated_ability(
        obj, cost=cost, effect_fn=_effect,
        description=desc, sorcery_speed=sorcery_speed,
        targets_required=1, target_kind=target_kind, once_per_turn=once_per_turn,
    )


def make_destroy_ability(
    obj: GameObject,
    cost: str,
    *,
    description: str = "",
    target_kind: str = "permanent",
    sorcery_speed: bool = False,
    once_per_turn: bool = False,
):
    """Register ``{cost}: Destroy target <type>``."""
    desc = description or f"Destroy target {target_kind}"

    def _effect(o: GameObject, state: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or t
        return [Event(
            type=EventType.DESTROY,
            payload={'object_id': target_id},
            source=o.id, controller=o.controller,
        )]

    return make_activated_ability(
        obj, cost=cost, effect_fn=_effect,
        description=desc, sorcery_speed=sorcery_speed,
        targets_required=1, target_kind=target_kind, once_per_turn=once_per_turn,
    )


def make_counter_ability(
    obj: GameObject,
    cost: str,
    *,
    counter_type: str = "+1/+1",
    amount: int = 1,
    target_self: bool = True,
    description: str = "",
    sorcery_speed: bool = False,
    once_per_turn: bool = False,
):
    """Register ``{cost}: Put N <type> counters on <self|target creature>``."""
    desc = description or f"Put {amount} {counter_type} counter(s) on {'this' if target_self else 'target creature'}"

    def _effect(o: GameObject, state: GameState, targets) -> list[Event]:
        if target_self:
            target_id = o.id
        else:
            if not targets:
                return []
            t = targets[0]
            target_id = getattr(t, "object_id", None) or t
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={
                'object_id': target_id,
                'counter_type': counter_type,
                'amount': amount,
            },
            source=o.id, controller=o.controller,
        )]

    return make_activated_ability(
        obj, cost=cost, effect_fn=_effect,
        description=desc, sorcery_speed=sorcery_speed,
        targets_required=0 if target_self else 1,
        target_kind="creature" if not target_self else "any",
        once_per_turn=once_per_turn,
    )


# -----------------------------------------------------------------------------
# TLA Waterbend activated ability — re-exported from src/engine/bending.py so
# avatar_tla.py setups can import it from the same module as other helpers.
# The framework's docstring lives on the canonical definition; this is a thin
# alias matching the pattern other bending helpers follow (firebend/earthbend
# are imported directly from src.engine.bending in avatar_tla.py — we re-export
# waterbend here because it composes with make_activated_ability's family and
# benefits from co-location).
# -----------------------------------------------------------------------------
from src.engine.bending import (
    make_waterbend_activated_ability,
    emit_waterbend_marker,
)


def make_token_creation_ability(
    obj: GameObject,
    cost: str,
    *,
    token_count: int = 1,
    token_name: str = "Spirit",
    token_power: int = 1,
    token_toughness: int = 1,
    token_subtypes: Optional[set] = None,
    token_colors: Optional[set] = None,
    token_keywords: Optional[list] = None,
    description: str = "",
    sorcery_speed: bool = True,
    once_per_turn: bool = False,
):
    """Register ``{cost}: Create N <stat> <name> creature tokens``."""
    desc = description or f"Create {token_count} {token_power}/{token_toughness} {token_name} token(s)"
    subtypes = token_subtypes or {token_name}
    colors = token_colors or set()
    keywords = token_keywords or []

    def _effect(o: GameObject, state: GameState, targets) -> list[Event]:
        events = []
        for _ in range(token_count):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': token_name,
                    'controller': o.controller,
                    'owner': o.controller,
                    'to_zone_type': ZoneType.BATTLEFIELD,
                    'types': {CardType.CREATURE},
                    'subtypes': set(subtypes),
                    'colors': set(colors),
                    'power': token_power,
                    'toughness': token_toughness,
                    'abilities': list(keywords),
                    'is_token': True,
                },
                source=o.id, controller=o.controller,
            ))
        return events

    return make_activated_ability(
        obj, cost=cost, effect_fn=_effect,
        description=desc, sorcery_speed=sorcery_speed, once_per_turn=once_per_turn,
    )


def make_copy_token_event(
    target_id: str,
    controller: str,
    source_id: Optional[str] = None,
    *,
    count: int = 1,
    owner: Optional[str] = None,
    tapped: bool = False,
    add_subtypes: Optional[set] = None,
    except_subtypes: Optional[set] = None,
    except_power: Optional[int] = None,
    except_toughness: Optional[int] = None,
    except_colors: Optional[set] = None,
    except_keywords: Optional[list] = None,
    except_name: Optional[str] = None,
) -> list[Event]:
    """Build OBJECT_CREATED events that create N tokens copying ``target_id``.

    The copy gets the original's printed characteristics (types, subtypes,
    colors, P/T, abilities) and inherits its ``card_def`` so the original's
    setup_interceptors fire when the copy enters the battlefield.

    Args:
        target_id: object id of the permanent to copy.
        controller: player id who will control the copy.
        source_id: object id of the spell/ability creating the copy
            (used as ``Event.source`` for downstream triggers).
        count: number of copies to create. Default 1.
        owner: optional owner override (defaults to ``controller``).
        tapped: whether the copy enters tapped.
        add_subtypes: subtypes to add *in addition* to the copied subtypes
            (e.g. "...except it's a Reflection in addition to its other
            creature types").
        except_subtypes: replace the copied subtypes entirely.
        except_power: override the copied power.
        except_toughness: override the copied toughness.
        except_colors: replace the copied colors entirely.
        except_keywords: replace the copied keyword abilities entirely
            (list of lowercase keyword strings).
        except_name: override the copied name.

    Returns:
        ``count`` OBJECT_CREATED events; emit each through ``state.emit`` /
        ``game.emit`` to instantiate the tokens.
    """
    payload_template: dict = {
        'copy_of': target_id,
        'controller': controller,
        'owner': owner or controller,
        'is_token': True,
        'to_zone_type': ZoneType.BATTLEFIELD,
        'tapped': bool(tapped),
    }
    if add_subtypes:
        payload_template['add_subtypes'] = set(add_subtypes)
    if except_subtypes is not None:
        payload_template['except_subtypes'] = set(except_subtypes)
    if except_power is not None:
        payload_template['except_power'] = int(except_power)
    if except_toughness is not None:
        payload_template['except_toughness'] = int(except_toughness)
    if except_colors is not None:
        payload_template['except_colors'] = set(except_colors)
    if except_keywords is not None:
        payload_template['except_keywords'] = list(except_keywords)
    if except_name is not None:
        payload_template['except_name'] = str(except_name)

    events: list[Event] = []
    for _ in range(max(0, int(count))):
        events.append(Event(
            type=EventType.OBJECT_CREATED,
            payload=dict(payload_template),
            source=source_id,
            controller=controller,
        ))
    return events


def make_sac_destroy_ability(
    obj: GameObject,
    cost: str,
    *,
    target_kind: str = "artifact_or_enchantment",
    description: str = "",
):
    """Register ``{cost}, Sacrifice this: Destroy target artifact or enchantment``.

    This is a common Cathar-Commando-style pattern. The cost text must include
    the sac (e.g. ``{1}, Sacrifice this creature``).
    """
    return make_destroy_ability(
        obj, cost=cost,
        description=description or f"Destroy target {target_kind}",
        target_kind=target_kind,
    )


__all_phase4__ = [
    "make_activated_ability",
    "make_exhaust_ability",
    "make_exhaust_reset_effect",
    "make_activate_exhaust_trigger",
    "make_activated_cost_reduction",
    "make_pump_self_ability",
    "make_draw_ability",
    "make_loot_ability",
    "make_life_gain_ability",
    "make_damage_ability",
    "make_destroy_ability",
    "make_counter_ability",
    "make_token_creation_ability",
    "make_sac_destroy_ability",
    # Planeswalker loyalty framework — re-exported from src/engine/planeswalker.py
    "make_loyalty_ability",
    "make_planeswalker_setup",
    "planeswalkers_with_zero_loyalty",
    "get_loyalty",
    # W15: PW combat redirect + emblems.
    "is_planeswalker",
    "planeswalkers_controlled_by",
    "redirect_attack_to_planeswalker",
    "redirect_damage_to_planeswalker",
    "Emblem",
    "create_emblem",
    "get_emblems",
    "get_emblems_for_player",
    "make_emblem_setup",
    "make_emblem_creatures_have_keywords",
]


# =============================================================================
# Phase 3: Equipment / Aura attach helpers
# =============================================================================
#
# An Equipment with text like "Equipped creature gets +1/+1 and has
# vigilance.  Equip {2}" registers:
#   1. A QUERY_POWER + QUERY_TOUGHNESS interceptor that applies the boost
#      to whatever creature is currently attached to it.
#   2. A QUERY_ABILITIES interceptor that grants the listed keywords to
#      that creature.
#   3. An activated ability ``{equip_cost}: Attach to target creature you
#      control. Activate only as a sorcery.``
#
# An Aura's setup function emits an ATTACH event when the aura ETBs and
# registers the same QUERY interceptors. (The pipeline's ZONE_CHANGE ->
# BATTLEFIELD path runs setup_interceptors after the aura enters; the
# attach itself happens here.)
# =============================================================================


def get_attached_target_id(obj: GameObject) -> Optional[str]:
    """Return the object-id of the creature this Equipment/Aura is attached to,
    or None if not attached.

    The canonical pointer is ``obj.state.attached_to`` (set by
    ``src/engine/attach.py::_handle_attach`` on the ATTACH event). Cards
    written against the legacy ``_aura_target_id`` / ``_attached_target_id``
    attrs should migrate to either this helper or read ``attached_to``
    directly — `make_aura_setup` already syncs the back-pointer on attach.

    Use in setup_interceptors / activated abilities / triggers that need
    to read the equipped creature mid-game::

        def equip_trigger(event, state):
            target_id = get_attached_target_id(obj)
            if target_id is None:
                return []
            target = state.objects.get(target_id)
            ...
    """
    state_obj = getattr(obj, "state", None)
    if state_obj is None:
        return None
    return getattr(state_obj, "attached_to", None)


def _make_attached_pt_interceptors(
    source_obj: GameObject,
    power_mod: int,
    toughness_mod: int,
) -> list[Interceptor]:
    """Build QUERY_POWER + QUERY_TOUGHNESS interceptors that fire on the
    creature currently attached to ``source_obj``.

    Filter is dynamic: it reads ``source.state.attached_to`` at query time.
    """
    interceptors: list[Interceptor] = []
    source_id = source_obj.id

    if power_mod != 0:
        def power_filter(event: Event, state: GameState) -> bool:
            if event.type != EventType.QUERY_POWER:
                return False
            source = state.objects.get(source_id)
            if not source or source.zone != ZoneType.BATTLEFIELD:
                return False
            attached = source.state.attached_to
            if not attached:
                return False
            return event.payload.get('object_id') == attached

        def power_handler(event: Event, state: GameState) -> InterceptorResult:
            new_event = event.copy()
            new_event.payload['value'] = new_event.payload.get('value', 0) + power_mod
            return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

        interceptors.append(Interceptor(
            id=new_id(),
            source=source_id,
            controller=source_obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=power_filter,
            handler=power_handler,
            duration='while_on_battlefield',
        ))

    if toughness_mod != 0:
        def toughness_filter(event: Event, state: GameState) -> bool:
            if event.type != EventType.QUERY_TOUGHNESS:
                return False
            source = state.objects.get(source_id)
            if not source or source.zone != ZoneType.BATTLEFIELD:
                return False
            attached = source.state.attached_to
            if not attached:
                return False
            return event.payload.get('object_id') == attached

        def toughness_handler(event: Event, state: GameState) -> InterceptorResult:
            new_event = event.copy()
            new_event.payload['value'] = new_event.payload.get('value', 0) + toughness_mod
            return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

        interceptors.append(Interceptor(
            id=new_id(),
            source=source_id,
            controller=source_obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=toughness_filter,
            handler=toughness_handler,
            duration='while_on_battlefield',
        ))

    return interceptors


def _make_attached_keyword_interceptor(
    source_obj: GameObject,
    keywords: list[str],
) -> Optional[Interceptor]:
    """Build a QUERY_ABILITIES interceptor that grants ``keywords`` to the
    creature currently attached to ``source_obj``."""
    if not keywords:
        return None
    source_id = source_obj.id

    def ability_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        source = state.objects.get(source_id)
        if not source or source.zone != ZoneType.BATTLEFIELD:
            return False
        attached = source.state.attached_to
        if not attached:
            return False
        return event.payload.get('object_id') == attached

    def ability_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []))
        for kw in keywords:
            if kw not in granted:
                granted.append(kw)
        new_event.payload['granted'] = granted
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return Interceptor(
        id=new_id(),
        source=source_id,
        controller=source_obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=ability_filter,
        handler=ability_handler,
        duration='while_on_battlefield',
    )


def _make_attached_subtypes_listener(
    source_obj: GameObject,
    subtypes_to_add: set[str],
) -> Optional[Interceptor]:
    """Build an ATTACH/UNATTACH REACT interceptor that mutates the attached
    creature's subtypes set whenever the source attaches or detaches.

    Direct mutation is used (instead of a QUERY_SUBTYPES interceptor)
    because the engine doesn't yet have a get_subtypes() query — most
    callers read characteristics.subtypes directly. We keep the original
    set on ``obj.state._subtypes_grant_target`` so we can revert cleanly.
    """
    if not subtypes_to_add:
        return None
    source_id = source_obj.id
    subs_set = set(subtypes_to_add)

    def _filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.ATTACH, EventType.UNATTACH):
            return False
        return event.payload.get("object_id") == source_id

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        source = state.objects.get(source_id)
        if source is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        if event.type == EventType.ATTACH:
            target_id = event.payload.get("target_id") or event.payload.get("target")
            target = state.objects.get(target_id) if target_id else None
            if target is None:
                return InterceptorResult(action=InterceptorAction.PASS)
            target.characteristics.subtypes = set(target.characteristics.subtypes) | subs_set
            setattr(source.state, "_subtypes_grant_target", target_id)
        else:  # UNATTACH
            target_id = getattr(source.state, "_subtypes_grant_target", None)
            if target_id:
                target = state.objects.get(target_id)
                if target is not None:
                    target.characteristics.subtypes = set(target.characteristics.subtypes) - subs_set
            try:
                delattr(source.state, "_subtypes_grant_target")
            except AttributeError:
                pass
        return InterceptorResult(action=InterceptorAction.PASS)

    return Interceptor(
        id=new_id(),
        source=source_id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration='while_on_battlefield',
    )


def _make_attached_ward_interceptor(
    source_obj: GameObject,
    ward_cost: Optional[str],
) -> Optional[Interceptor]:
    """Build a TARGET_CHOSEN REACT interceptor that grants Ward to whichever
    creature ``source_obj`` (an Equipment or Aura) is currently attached to.

    ``ward_cost`` is a cost string like "{1}" or "{2}{U}". When None, no
    interceptor is built.
    """
    if not ward_cost:
        return None
    source_id = source_obj.id
    controller_id = source_obj.controller

    def ward_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.TARGET_CHOSEN:
            return False
        source = state.objects.get(source_id)
        if not source or source.zone != ZoneType.BATTLEFIELD:
            return False
        attached = source.state.attached_to
        if not attached:
            return False
        if event.payload.get('target_id') != attached:
            return False
        target_obj = state.objects.get(attached)
        target_controller = target_obj.controller if target_obj else controller_id
        spell_controller = event.payload.get('controller')
        if not spell_controller or spell_controller == target_controller:
            return False
        return True

    def ward_handler(event: Event, state: GameState) -> InterceptorResult:
        spell_id = event.payload.get('spell_id')
        if not spell_id:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.COUNTER_SPELL_UNLESS_PAY,
                payload={
                    'spell_id': spell_id,
                    'target_id': event.payload.get('target_id'),
                    'reason': 'ward',
                    'mana_cost': ward_cost,
                },
                source=source_id,
                controller=controller_id,
            )],
        )

    return Interceptor(
        id=new_id(),
        source=source_id,
        controller=controller_id,
        priority=InterceptorPriority.REACT,
        filter=ward_filter,
        handler=ward_handler,
        duration='while_on_battlefield',
    )


def _make_attached_triggered_ability_listener(
    source_obj: GameObject,
    specs: Optional[Any],
) -> Optional[Interceptor]:
    """Build an ATTACH/UNATTACH REACT interceptor that grants/revokes a
    triggered ability on whichever creature ``source_obj`` is attached to.

    Parallel to ``src.engine.attach.make_granted_abilities_listener`` (which
    handles *activated* abilities). Each spec is a dict::

        {
            "event_filter": Callable[[Event, GameState, str], bool],
            "effect_fn":    Callable[[GameObject, Event, GameState], list[Event]],
            "description":  str,                 # optional, for logs/tests
            "duration":     "while_on_battlefield",  # optional; default
            "one_shot":     False,               # optional
        }

    The granted Interceptor IDs are stashed on
    ``source_obj.state._granted_triggered_ability_ids`` so UNATTACH (or the
    equipment leaving the battlefield) can revoke them. ``grant_triggered_ability``
    registers each Interceptor on ``state.interceptors``; revocation simply
    pops them out.
    """
    normalized = _normalise_triggered_specs(specs) if specs is not None else []
    if not normalized:
        return None

    source_id = source_obj.id
    controller_id = source_obj.controller

    def _filter(event: Event, state: GameState) -> bool:
        if event.type in (EventType.ATTACH, EventType.UNATTACH):
            return event.payload.get("object_id") == source_id
        # Catch equipment leaving the battlefield in the same REACT phase
        # before _cleanup_departed_interceptors strips this listener.
        if event.type == EventType.ZONE_CHANGE:
            if event.payload.get("object_id") != source_id:
                return False
            from_t = event.payload.get("from_zone_type")
            to_t = event.payload.get("to_zone_type")
            return from_t == ZoneType.BATTLEFIELD and to_t != ZoneType.BATTLEFIELD
        return False

    def _revoke(state: GameState, source: GameObject) -> None:
        ids = list(getattr(source.state, "_granted_triggered_ability_ids", []) or [])
        for int_id in ids:
            state.interceptors.pop(int_id, None)
        try:
            delattr(source.state, "_granted_triggered_ability_ids")
        except AttributeError:
            pass

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        source = state.objects.get(source_id)
        if source is None:
            return InterceptorResult(action=InterceptorAction.PASS)

        if event.type == EventType.ATTACH:
            target_id = event.payload.get("target_id") or event.payload.get("target")
            if not target_id:
                return InterceptorResult(action=InterceptorAction.PASS)
            target = state.objects.get(target_id)
            if target is None:
                return InterceptorResult(action=InterceptorAction.PASS)
            # If we were granting to a prior target, revoke first.
            _revoke(state, source)
            granted_ids: list[str] = []
            for spec in normalized:
                interceptor = grant_triggered_ability(
                    target,
                    source,
                    state,
                    event_filter=spec["event_filter"],
                    effect_fn=spec["effect_fn"],
                    duration=spec.get("duration", "while_on_battlefield"),
                    one_shot=bool(spec.get("one_shot", False)),
                )
                granted_ids.append(interceptor.id)
            setattr(source.state, "_granted_triggered_ability_ids", granted_ids)
            return InterceptorResult(action=InterceptorAction.PASS)

        # UNATTACH or ZONE_CHANGE leaving battlefield: revoke.
        _revoke(state, source)
        return InterceptorResult(action=InterceptorAction.PASS)

    return Interceptor(
        id=new_id(),
        source=source_id,
        controller=controller_id,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration='while_on_battlefield',
    )


def _normalise_triggered_specs(specs: Any) -> list[dict]:
    """Coerce ``specs`` to a list of dicts. Accepts a single dict, a list
    of dicts, or None. Filters out entries missing ``event_filter`` or
    ``effect_fn`` so a malformed spec doesn't blow up at runtime."""
    if specs is None:
        return []
    if isinstance(specs, dict):
        specs = [specs]
    result: list[dict] = []
    for s in specs:
        if not isinstance(s, dict):
            continue
        if not callable(s.get("event_filter")) or not callable(s.get("effect_fn")):
            continue
        result.append(s)
    return result


def make_equipment_setup(
    *,
    power_mod: int = 0,
    toughness_mod: int = 0,
    keywords: Optional[list[str]] = None,
    subtypes_to_add: Optional[set[str]] = None,
    equip_cost: Optional[str] = None,
    ward_cost: Optional[str] = None,
    granted_activated_abilities: Optional[Any] = None,
    granted_triggered_abilities: Optional[Any] = None,
):
    """Return a setup_interceptors callable for an Equipment card.

    Example::

        WRENCH = make_equipment(
            name="Wrench",
            mana_cost="{1}",
            text='Equipped creature gets +1/+1 and has vigilance. Equip {2}',
            setup_interceptors=make_equipment_setup(
                power_mod=1, toughness_mod=1,
                keywords=["vigilance"],
                equip_cost="{2}",
            ),
        )

    ``subtypes_to_add`` (set of strings) covers Equipment that grants the
    attached creature additional creature subtypes — e.g. "Equipped
    creature is a Shaman in addition to its other types." Subtypes are
    applied on ATTACH and reverted on UNATTACH via direct mutation of
    ``target.characteristics.subtypes`` (no QUERY_SUBTYPES yet).

    ``ward_cost`` ("{1}", "{2}{U}", ...) grants Ward to the equipped
    creature. See ``make_ward()`` for v1 limitations (always counter, no
    cost prompt).

    ``granted_activated_abilities`` covers Equipment that says "Equipped
    creature has '<cost>: <effect>'" — the activated ability is registered
    on the equipped creature (not the equipment) on ATTACH and removed on
    UNATTACH or when the equipment leaves the battlefield. Each spec is a
    dict with ``cost`` (str), ``effect_fn`` (Callable[[GameObject, GameState,
    list], list[Event]]), and ``description`` (str), plus optional
    activated-ability flags (``sorcery_speed``, ``targets_required``, etc.).
    Pass a single dict or a list of dicts to grant multiple abilities.
    """
    keywords_list = list(keywords) if keywords else []
    subs = set(subtypes_to_add) if subtypes_to_add else set()

    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        interceptors = _make_attached_pt_interceptors(obj, power_mod, toughness_mod)
        ki = _make_attached_keyword_interceptor(obj, keywords_list)
        if ki is not None:
            interceptors.append(ki)
        sti = _make_attached_subtypes_listener(obj, subs)
        if sti is not None:
            interceptors.append(sti)
        wi = _make_attached_ward_interceptor(obj, ward_cost)
        if wi is not None:
            interceptors.append(wi)
        from src.engine.attach import make_granted_abilities_listener
        gi = make_granted_abilities_listener(obj, granted_activated_abilities)
        if gi is not None:
            interceptors.append(gi)
        ti = _make_attached_triggered_ability_listener(obj, granted_triggered_abilities)
        if ti is not None:
            interceptors.append(ti)
        if equip_cost:
            _make_equip_activated_ability(obj, equip_cost)
        return interceptors

    return _setup


def make_aura_setup(
    *,
    power_mod: int = 0,
    toughness_mod: int = 0,
    keywords: Optional[list[str]] = None,
    subtypes_to_add: Optional[set[str]] = None,
    target_id_attr: str = "_aura_target_id",
    ward_cost: Optional[str] = None,
    granted_activated_abilities: Optional[Any] = None,
    granted_triggered_abilities: Optional[Any] = None,
):
    """Return a setup_interceptors callable for an Aura card.

    The Aura must already have its target stored on ``obj.state`` via
    ``setattr(obj.state, target_id_attr, target_id)`` before setup runs
    — this is typically set by the cast/resolve flow. The setup function
    emits an ATTACH event to that target and registers the QUERY
    interceptors that grant the aura's static effects to it.

    ``subtypes_to_add`` covers Auras like "Enchanted creature is an
    Angel/Symbiote/Avatar in addition to its other types" — applied via
    direct mutation on ATTACH and reverted on UNATTACH.

    ``ward_cost`` ("{1}", "{2}{U}", ...) grants Ward to the enchanted
    creature. See ``make_ward()`` for v1 limitations.

    ``granted_activated_abilities`` covers Auras like "Enchanted creature
    has '<cost>: <effect>'." See ``make_equipment_setup`` docs for the
    spec shape.
    """
    keywords_list = list(keywords) if keywords else []
    subs = set(subtypes_to_add) if subtypes_to_add else set()

    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        target_id = getattr(obj.state, target_id_attr, None) or obj.state.attached_to
        if target_id and obj.state.attached_to != target_id:
            # Best-effort: synchronise the attached_to back-pointer; the
            # ATTACH event handler will do this cleanly when fired through
            # the pipeline, but cards that bypass the stack rely on this.
            obj.state.attached_to = target_id
            target = state.objects.get(target_id)
            if target and obj.id not in target.state.attachments:
                target.state.attachments.append(obj.id)
            # If we already have a target (cast/resolve fast-path), apply
            # subtypes immediately too. Otherwise the ATTACH listener picks
            # them up.
            if subs:
                target_obj = state.objects.get(target_id)
                if target_obj is not None:
                    target_obj.characteristics.subtypes = set(target_obj.characteristics.subtypes) | subs
                    setattr(obj.state, "_subtypes_grant_target", target_id)
        interceptors = _make_attached_pt_interceptors(obj, power_mod, toughness_mod)
        ki = _make_attached_keyword_interceptor(obj, keywords_list)
        if ki is not None:
            interceptors.append(ki)
        sti = _make_attached_subtypes_listener(obj, subs)
        if sti is not None:
            interceptors.append(sti)
        wi = _make_attached_ward_interceptor(obj, ward_cost)
        if wi is not None:
            interceptors.append(wi)
        from src.engine.attach import make_granted_abilities_listener
        gi = make_granted_abilities_listener(obj, granted_activated_abilities)
        if gi is not None:
            interceptors.append(gi)
        ti = _make_attached_triggered_ability_listener(obj, granted_triggered_abilities)
        if ti is not None:
            interceptors.append(ti)
        return interceptors

    return _setup


# =============================================================================
# === Granted activated abilities ===
# =============================================================================
#
# "Equipped creature has '<cost>: <effect>'" — the activated ability is
# registered on the *equipped creature* (so the priority system discovers
# it like any other) but tagged with ``_granted_by=<equipment_id>`` so the
# attach listener can revoke it when the equipment unattaches or leaves
# the battlefield.
#
# Most cards declare this via ``granted_activated_abilities`` on
# ``make_equipment_setup`` / ``make_aura_setup``. Use the standalone
# ``make_granted_activated_ability`` helper for *conditional* grants —
# cards that only bestow the ability under some predicate (e.g. only
# while equipped to a creature of a particular subtype).


def make_granted_activated_ability(
    equipped_target: GameObject,
    equipment_source: GameObject,
    cost: str,
    effect_fn: Callable[[GameObject, GameState, list], list[Event]],
    *,
    description: str = "",
    sorcery_speed: bool = False,
    own_turn_only: bool = False,
    once_per_turn: bool = False,
    once_per_game: bool = False,
    targets_required: int = 0,
    target_kind: str = "any",
):
    """Register an activated ability on ``equipped_target`` granted by
    ``equipment_source``.

    The descriptor is appended to ``equipped_target.state.activated_abilities``
    and tagged ``_granted_by=equipment_source.id`` so cleanup on UNATTACH /
    leaves-battlefield can find and remove it.

    Returns the registered ``ActivatedAbility`` (whose ``_granted_by``
    attribute mirrors ``equipment_source.id``).
    """
    from src.engine.attach import grant_activated_ability_on_attach
    spec = {
        "cost": cost,
        "effect_fn": effect_fn,
        "description": description or f"{cost}: ...",
        "sorcery_speed": sorcery_speed,
        "own_turn_only": own_turn_only,
        "once_per_turn": once_per_turn,
        "once_per_game": once_per_game,
        "targets_required": targets_required,
        "target_kind": target_kind,
    }
    grant_activated_ability_on_attach(equipped_target, equipment_source.id, spec, None)
    # Find and return the freshly-registered descriptor.
    for ability in reversed(getattr(equipped_target.state, "activated_abilities", []) or []):
        if (
            getattr(ability, "_granted_by", None) == equipment_source.id
            and ability.cost_text == cost
        ):
            return ability
    return None


def make_equipment_granted_ability(
    obj: GameObject,
    cost: str,
    effect_fn: Callable[[GameObject, GameState, list], list[Event]],
    *,
    description: str = "",
    sorcery_speed: bool = False,
    own_turn_only: bool = False,
    once_per_turn: bool = False,
    once_per_game: bool = False,
    targets_required: int = 0,
    target_kind: str = "any",
    target_requirements: Optional[list] = None,
) -> list[Interceptor]:
    """Equipment-side helper: grant ``"<cost>: <effect>"`` to the equipped
    creature for as long as ``obj`` (the Equipment / Aura) is attached.

    The granted ability is registered on the equipped creature (not on the
    Equipment) so the priority system surfaces it like any other activated
    ability. The cost is paid by the equipped creature (a ``{T}`` tap-cost
    taps the creature, not the Equipment). When the Equipment unattaches
    or leaves the battlefield, the granted ability is cleaned up by the
    standard attach-listener cleanup path.

    Returns a list containing a single ATTACH/UNATTACH listener interceptor
    that wires the grant/revoke. Append the result to the setup function's
    return list. Designed for cards where ``make_equipment_setup`` isn't
    convenient — e.g. cards that mix granted abilities with custom triggers
    in a hand-rolled setup function. For boilerplate Equipment, prefer
    ``make_equipment_setup(granted_activated_abilities=...)``.

    Example::

        def trusty_boomerang_setup(obj, state):
            def _bounce(o, st, targets):
                # tap target, bounce boomerang
                ...
            ics = make_equipment_granted_ability(
                obj,
                cost="{1}, {T}",
                effect_fn=_bounce,
                description="Tap target creature. Return Boomerang.",
                targets_required=1,
                target_kind="creature",
            )
            _make_equip_activated_ability(obj, "{1}")
            return ics

    The Equipment-side equip cost is still registered via
    ``_make_equip_activated_ability`` (or the ``equip_cost`` parameter on
    ``make_equipment_setup``).
    """
    from src.engine.attach import make_granted_abilities_listener
    spec = {
        "cost": cost,
        "effect_fn": effect_fn,
        "description": description or f"{cost}: ...",
        "sorcery_speed": sorcery_speed,
        "own_turn_only": own_turn_only,
        "once_per_turn": once_per_turn,
        "once_per_game": once_per_game,
        "targets_required": targets_required,
        "target_kind": target_kind,
    }
    if target_requirements is not None:
        spec["target_requirements"] = target_requirements
    interceptor = make_granted_abilities_listener(obj, spec)
    return [interceptor] if interceptor is not None else []


def _make_equip_activated_ability(obj: GameObject, equip_cost: str) -> None:
    """Register the standard ``{equip_cost}: Attach to target creature you
    control. Activate only as a sorcery.`` activated ability on ``obj``.
    """
    def _equip_effect(o: GameObject, state: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        # Targets may be Target dataclasses (with .id), strings, or objects.
        target_id = getattr(t, "id", None) or getattr(t, "object_id", None) or t
        return [Event(
            type=EventType.ATTACH,
            payload={"object_id": o.id, "target_id": target_id},
            source=o.id,
            controller=o.controller,
        )]

    make_activated_ability(
        obj,
        cost=equip_cost,
        effect_fn=_equip_effect,
        description=f"Equip {equip_cost}",
        sorcery_speed=True,
        targets_required=1,
        target_kind="creature_you_control",
    )


def attach_aura_to_target(
    obj: GameObject,
    state: GameState,
    target_id: str,
) -> list[Event]:
    """Helper for an Aura's resolve-step: emit an ATTACH event and stash
    the chosen target so make_aura_setup can read it.

    Returns the list of events to be enqueued by the resolve callback.
    """
    setattr(obj.state, "_aura_target_id", target_id)
    return [Event(
        type=EventType.ATTACH,
        payload={"object_id": obj.id, "target_id": target_id},
        source=obj.id,
        controller=obj.controller,
    )]


__all_phase3__ = [
    "make_equipment_setup",
    "make_aura_setup",
    "attach_aura_to_target",
    "make_granted_activated_ability",
    "make_equipment_granted_ability",
]


# =============================================================================
# === Type-overwrite auras ===
# =============================================================================
#
# Implements Lignify-style auras: "Enchanted creature is a 0/4 Treefolk
# creature with no abilities" (Lignify) or "Enchanted creature is a 1/1 Elf
# with no abilities and loses all other types and subtypes" (Song of the
# Dryads-shaped templates).
#
# Distinct from ``make_aura_setup``: that helper grants ADDITIVE
# modifications (+X/+Y, +keyword, +subtype). Type-overwrite auras REPLACE
# the enchanted creature's queryable characteristics — base power and
# toughness, subtypes, types, colors, and (typically) abilities.
#
# Implementation strategy:
#
# 1. Install QUERY interceptors sourced on the *aura* (``while_on_battlefield``)
#    that match ``event.payload.get('object_id') == aura.state.attached_to``
#    (read live, so a re-attach updates the override target). Each QUERY
#    interceptor TRANSFORMs the queried value to the aura's prescribed
#    base. Counters and ``pt_modifiers`` apply LATER in get_power /
#    get_toughness, so CR layer 7c (counters last) is preserved without
#    extra effort.
#
# 2. Install an ATTACH / UNATTACH / ZONE_CHANGE-leaves-bf REACT listener
#    that dual-writes onto ``target.characteristics`` (subtypes, types,
#    colors, abilities, base power/toughness) so the ~250 direct readers
#    across the codebase see the override. Originals are stashed on the
#    aura's state so they can be restored on UNATTACH or when the aura
#    leaves the battlefield.
#
# 3. The REACT listener uses ``duration='forever'`` plus the
#    ``_cleanup_on_zone_change`` flag so it can still fire during the
#    REACT phase that runs after the aura's ZONE_CHANGE-leaves-battlefield
#    handler — the standard ``while_on_battlefield`` gate would suppress
#    the listener because the aura's zone has already moved out of the
#    battlefield by then. The cleanup pass at the end of the same emit()
#    call evicts the listener via the zone-change tag, so it doesn't leak.
# =============================================================================


def _capture_overwrite_snapshot(target: 'GameObject') -> dict:
    """Return a snapshot of the fields that a type-overwrite aura mutates.

    The snapshot is later consumed by ``_restore_overwrite_snapshot`` when
    the aura unattaches or leaves the battlefield.
    """
    return {
        'subtypes': set(target.characteristics.subtypes),
        'types': set(target.characteristics.types),
        'colors': set(target.characteristics.colors),
        'abilities': list(target.characteristics.abilities),
        'power': target.characteristics.power,
        'toughness': target.characteristics.toughness,
    }


def _apply_overwrite_dual_write(
    target: 'GameObject',
    *,
    base_power: int,
    base_toughness: int,
    new_subtypes: set,
    new_types: set,
    new_colors: set,
    keep_keywords: list,
    lose_abilities: bool,
) -> None:
    """Mutate ``target.characteristics`` to reflect the aura's overwrite.

    Direct mutation is required because ~250 callsites read
    ``obj.characteristics.subtypes`` / ``.power`` / etc. directly without
    going through the QUERY-interceptor pipeline. The QUERY interceptors
    handle the get_power / get_subtypes paths; this dual-write covers the
    rest.
    """
    target.characteristics.subtypes = set(new_subtypes)
    target.characteristics.types = set(new_types)
    target.characteristics.colors = set(new_colors)
    if lose_abilities:
        # Keep only the printed keywords listed in keep_keywords (e.g. for
        # "Enchanted creature is a 1/1 Elf with flying" templates).
        kept_lower = {str(k).strip().lower() for k in (keep_keywords or [])}
        new_abilities: list[dict] = []
        for ab in target.characteristics.abilities:
            if isinstance(ab, dict):
                kw = str(ab.get('keyword') or ab.get('name') or '').strip().lower()
                if kw and kw in kept_lower:
                    new_abilities.append(ab)
        # Append any keep_keywords that weren't already on the target so
        # callers who pass keep_keywords=['flying'] but the original
        # creature didn't have flying still see it on the overwrite.
        existing_lower = {
            str(ab.get('keyword') or ab.get('name') or '').strip().lower()
            for ab in new_abilities if isinstance(ab, dict)
        }
        for kw in (keep_keywords or []):
            kw_norm = str(kw).strip().lower()
            if kw_norm and kw_norm not in existing_lower:
                new_abilities.append({'keyword': kw_norm})
        target.characteristics.abilities = new_abilities
    target.characteristics.power = int(base_power)
    target.characteristics.toughness = int(base_toughness)


def _restore_overwrite_snapshot(target: 'GameObject', snap: dict) -> None:
    """Inverse of ``_apply_overwrite_dual_write``: restore original fields."""
    target.characteristics.subtypes = set(snap.get('subtypes') or set())
    target.characteristics.types = set(snap.get('types') or set())
    target.characteristics.colors = set(snap.get('colors') or set())
    target.characteristics.abilities = list(snap.get('abilities') or [])
    target.characteristics.power = snap.get('power')
    target.characteristics.toughness = snap.get('toughness')


def make_type_overwrite_aura(
    obj: 'GameObject',
    *,
    base_power: int,
    base_toughness: int,
    new_subtypes: list,
    new_types: Optional[list] = None,
    new_colors: Optional[set] = None,
    lose_abilities: bool = True,
    keep_keywords: Optional[list] = None,
    ward_cost: Optional[str] = None,
):
    """Return a setup_interceptors callable for a type-overwrite Aura.

    Implements Lignify-style auras whose static effect REPLACES (not
    augments) the enchanted creature's queryable characteristics.

    Args:
        obj: The Aura ``GameObject``. The helper signature accepts the
            object up-front (mirroring ``make_replacement_effect``) so the
            returned setup callable can close over it without a second
            indirection.
        base_power, base_toughness: New base P/T for the enchanted creature.
            Counters and ``pt_modifiers`` still apply on top (CR 7c).
        new_subtypes: List of subtypes to grant (replaces the creature's
            existing subtypes). Example: ``['Treefolk']``.
        new_types: List of card types to grant (default
            ``[CardType.CREATURE]``). The CREATURE type is always added
            even if not present in ``new_types``.
        new_colors: Set of ``Color`` values for the new permanent. Defaults
            to the aura's own ``characteristics.colors``.
        lose_abilities: When True (default), the enchanted creature loses
            all abilities. When False, abilities pass through unchanged.
        keep_keywords: List of keyword strings to grant on top of the
            overwrite (e.g. ``['flying']`` for "is a 1/1 Elf with flying").
        ward_cost: Layered separately via the standard ward grant — Lignify
            doesn't grant ward but the parameter is exposed for future
            cards (e.g. "is a 0/4 Treefolk with ward {1}"). Falls through
            to the same primitive ``make_aura_setup`` uses.

    Returns:
        A setup_interceptors callable: ``(obj, state) -> list[Interceptor]``.
        The QUERY interceptors are sourced on the aura with
        ``duration='while_on_battlefield'`` so they self-evict when the
        aura leaves play. The ATTACH/UNATTACH listener uses
        ``duration='forever'`` plus the ``_cleanup_on_zone_change`` flag
        so it can fire during REACT for the aura's leaves-battlefield
        ZONE_CHANGE (the post-RESOLVE zone has already moved, so the
        ``while_on_battlefield`` gate would otherwise suppress it).

    Edge cases handled:
        - Counter stacking: counters on the enchanted creature add on top
          of the new base in ``get_power`` / ``get_toughness`` (CR 7c).
        - Re-attach: the QUERY interceptors filter on the aura's live
          ``attached_to``, so attaching to a new creature instantly moves
          the override.
        - Aura leaves BF (destroyed / bounced): the synchronous
          ZONE_CHANGE branch of the listener restores the original
          characteristics before ``_cleanup_departed_interceptors``
          evicts the aura's QUERY interceptors.
        - Multiple overlapping auras: each registers its own QUERY
          interceptor; the latest-timestamp wins (the loop in
          ``get_power`` etc. applies them in timestamp order, and each
          TRANSFORMs the value, so the last one's value sticks).
    """
    # Normalise inputs.
    new_subtypes_set = set(new_subtypes or [])
    types_input = list(new_types) if new_types else [CardType.CREATURE]
    new_types_set = set(types_input)
    new_types_set.add(CardType.CREATURE)
    keep_kw_list = [str(k).strip().lower() for k in (keep_keywords or []) if str(k).strip()]
    aura_id = obj.id
    aura_controller = obj.controller
    # Capture the aura's printed colors at definition time so the runtime
    # default doesn't re-read characteristics (which may be live-mutated).
    default_colors = set(obj.characteristics.colors) if new_colors is None else set(new_colors)

    # ------------------------------------------------------------------
    # QUERY filter: matches whichever creature the aura is *currently*
    # attached to (read live so re-attaches re-target).
    # ------------------------------------------------------------------
    def _matches_attached(ev_type, event: Event, state: GameState) -> bool:
        if event.type != ev_type:
            return False
        aura = state.objects.get(aura_id)
        if aura is None or aura.zone != ZoneType.BATTLEFIELD:
            return False
        attached = aura.state.attached_to
        if not attached:
            return False
        return event.payload.get('object_id') == attached

    # ------------------------------------------------------------------
    # POWER override
    # ------------------------------------------------------------------
    def power_filter(event: Event, state: GameState) -> bool:
        return _matches_attached(EventType.QUERY_POWER, event, state)

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['value'] = int(base_power)
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # ------------------------------------------------------------------
    # TOUGHNESS override
    # ------------------------------------------------------------------
    def tough_filter(event: Event, state: GameState) -> bool:
        return _matches_attached(EventType.QUERY_TOUGHNESS, event, state)

    def tough_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['value'] = int(base_toughness)
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # ------------------------------------------------------------------
    # TYPES override (replace, but always include CREATURE)
    # ------------------------------------------------------------------
    def types_filter(event: Event, state: GameState) -> bool:
        return _matches_attached(EventType.QUERY_TYPES, event, state)

    def types_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['value'] = set(new_types_set)
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # ------------------------------------------------------------------
    # SUBTYPES override (replace)
    # ------------------------------------------------------------------
    def subtypes_filter(event: Event, state: GameState) -> bool:
        return _matches_attached(EventType.QUERY_SUBTYPES, event, state)

    def subtypes_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['value'] = set(new_subtypes_set)
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # ------------------------------------------------------------------
    # COLORS override (replace)
    # ------------------------------------------------------------------
    def colors_filter(event: Event, state: GameState) -> bool:
        return _matches_attached(EventType.QUERY_COLORS, event, state)

    def colors_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['value'] = set(default_colors)
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # ------------------------------------------------------------------
    # ABILITIES override
    #   - lose_abilities=True: only ``keep_keywords`` survive the
    #     overwrite (the QUERY_ABILITIES interceptor produces a granted
    #     list containing only those keywords; ``has_ability`` checks
    #     printed abilities first, so the dual-write step strips printed
    #     keywords too).
    #   - lose_abilities=False: abilities pass through (the dual-write
    #     leaves printed abilities alone, and the keep_keywords list is
    #     simply added to granted).
    # ------------------------------------------------------------------
    def abilities_filter(event: Event, state: GameState) -> bool:
        return _matches_attached(EventType.QUERY_ABILITIES, event, state)

    def abilities_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        if lose_abilities:
            # REPLACE the granted set with just the kept keywords.
            new_event.payload['granted'] = list(keep_kw_list)
            existing_value = new_event.payload.get('value')
            if isinstance(existing_value, (set, list)):
                new_event.payload['value'] = set(keep_kw_list)
        else:
            granted = list(new_event.payload.get('granted', []) or [])
            for kw in keep_kw_list:
                if kw not in granted:
                    granted.append(kw)
            new_event.payload['granted'] = granted
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # ------------------------------------------------------------------
    # ATTACH / UNATTACH / ZONE_CHANGE-leaves-bf REACT listener.
    # Handles dual-write of characteristics so direct readers stay
    # consistent with the QUERY-pipeline result.
    # ------------------------------------------------------------------
    def _listener_filter(event: Event, state: GameState) -> bool:
        if event.type in (EventType.ATTACH, EventType.UNATTACH):
            return event.payload.get('object_id') == aura_id
        if event.type == EventType.ZONE_CHANGE:
            if event.payload.get('object_id') != aura_id:
                return False
            from_t = event.payload.get('from_zone_type')
            to_t = event.payload.get('to_zone_type')
            return from_t == ZoneType.BATTLEFIELD and to_t != ZoneType.BATTLEFIELD
        return False

    def _listener_handler(event: Event, state: GameState) -> InterceptorResult:
        aura = state.objects.get(aura_id)
        if aura is None:
            return InterceptorResult(action=InterceptorAction.PASS)

        if event.type == EventType.ATTACH:
            target_id = event.payload.get('target_id') or event.payload.get('target')
            if not target_id:
                return InterceptorResult(action=InterceptorAction.PASS)
            target = state.objects.get(target_id)
            if target is None:
                return InterceptorResult(action=InterceptorAction.PASS)
            # If we were already overwriting a different creature, restore it.
            prior_target_id = getattr(aura.state, '_overwrite_target_id', None)
            prior_snap = getattr(aura.state, '_overwrite_snapshot', None)
            if prior_target_id and prior_target_id != target_id and prior_snap is not None:
                prior = state.objects.get(prior_target_id)
                if prior is not None:
                    _restore_overwrite_snapshot(prior, prior_snap)
            # Snapshot original, then apply the overwrite.
            snap = _capture_overwrite_snapshot(target)
            _apply_overwrite_dual_write(
                target,
                base_power=base_power,
                base_toughness=base_toughness,
                new_subtypes=new_subtypes_set,
                new_types=new_types_set,
                new_colors=default_colors,
                keep_keywords=keep_kw_list,
                lose_abilities=lose_abilities,
            )
            setattr(aura.state, '_overwrite_target_id', target_id)
            setattr(aura.state, '_overwrite_snapshot', snap)
            return InterceptorResult(action=InterceptorAction.PASS)

        # UNATTACH or aura leaves BF — restore the prior snapshot.
        prior_target_id = getattr(aura.state, '_overwrite_target_id', None)
        prior_snap = getattr(aura.state, '_overwrite_snapshot', None)
        if prior_target_id and prior_snap is not None:
            prior = state.objects.get(prior_target_id)
            if prior is not None:
                _restore_overwrite_snapshot(prior, prior_snap)
        try:
            delattr(aura.state, '_overwrite_target_id')
        except AttributeError:
            pass
        try:
            delattr(aura.state, '_overwrite_snapshot')
        except AttributeError:
            pass
        return InterceptorResult(action=InterceptorAction.PASS)

    def _setup(setup_obj: 'GameObject', state: GameState) -> list:
        # Build interceptor list. All QUERY interceptors are sourced on the
        # aura so they self-evict when the aura leaves the battlefield.
        pairs = [
            (power_filter, power_handler),
            (tough_filter, tough_handler),
            (types_filter, types_handler),
            (subtypes_filter, subtypes_handler),
            (colors_filter, colors_handler),
            (abilities_filter, abilities_handler),
        ]
        interceptors: list[Interceptor] = []
        for filt, hand in pairs:
            interceptors.append(Interceptor(
                id=new_id(),
                source=aura_id,
                controller=aura_controller,
                priority=InterceptorPriority.QUERY,
                filter=filt,
                handler=hand,
                duration='while_on_battlefield',
            ))
        # Attach/unattach listener (REACT, dual-write). We use
        # ``duration='forever'`` plus ``_cleanup_on_zone_change=True`` so
        # the listener still fires during the REACT phase that runs after
        # the aura's ZONE_CHANGE-leaves-battlefield handler — the standard
        # ``while_on_battlefield`` gate would suppress it because the
        # aura's zone has already moved out of the battlefield by then.
        # The cleanup pass at the end of the same emit() call evicts the
        # listener via the zone-change tag.
        listener = Interceptor(
            id=new_id(),
            source=aura_id,
            controller=aura_controller,
            priority=InterceptorPriority.REACT,
            filter=_listener_filter,
            handler=_listener_handler,
            duration='forever',
        )
        setattr(listener, '_cleanup_on_zone_change', True)
        interceptors.append(listener)

        # Optional ward grant (matches make_aura_setup behaviour).
        if ward_cost:
            wi = _make_attached_ward_interceptor(setup_obj, ward_cost)
            if wi is not None:
                interceptors.append(wi)

        # Fast-path: if the aura already knows its target (cast/resolve
        # set ``_aura_target_id`` before our setup runs), apply the
        # overwrite immediately so direct readers see it before the
        # ATTACH event fires through the pipeline.
        target_id = getattr(setup_obj.state, '_aura_target_id', None) or setup_obj.state.attached_to
        if target_id:
            if setup_obj.state.attached_to != target_id:
                setup_obj.state.attached_to = target_id
                target = state.objects.get(target_id)
                if target is not None and setup_obj.id not in target.state.attachments:
                    target.state.attachments.append(setup_obj.id)
            target = state.objects.get(target_id)
            if target is not None and not getattr(setup_obj.state, '_overwrite_snapshot', None):
                snap = _capture_overwrite_snapshot(target)
                _apply_overwrite_dual_write(
                    target,
                    base_power=base_power,
                    base_toughness=base_toughness,
                    new_subtypes=new_subtypes_set,
                    new_types=new_types_set,
                    new_colors=default_colors,
                    keep_keywords=keep_kw_list,
                    lose_abilities=lose_abilities,
                )
                setattr(setup_obj.state, '_overwrite_target_id', target_id)
                setattr(setup_obj.state, '_overwrite_snapshot', snap)
        return interceptors

    return _setup


__all_type_overwrite_aura__ = [
    "make_type_overwrite_aura",
]


# =============================================================================
# Phase 5: Suspect mechanic (Murders at Karlov Manor)
# =============================================================================
#
# A "suspected" creature has menace and can't block. Suspect persists until
# it's removed (typically by a "no longer suspected" trigger that none of the
# wired cards include yet, so we treat it as forever).
# =============================================================================


def suspect_creature(target_id: str, source_id: str, controller: str,
                     state: Optional[GameState] = None) -> list[Event]:
    """Emit the events needed to suspect a creature.

    A suspected creature gains menace and can't block. Both grants use
    duration='forever' since there is no engine concept of "becomes
    no longer suspected" yet.

    If ``state`` is provided, also sets ``obj.state.suspected = True`` for
    cards (e.g. Repeat Offender) that branch on suspect status.
    """
    if state is not None:
        target = state.objects.get(target_id)
        if target is not None:
            target.state.suspected = True
    return [
        Event(
            type=EventType.GRANT_KEYWORD,
            payload={
                'object_id': target_id,
                'keyword': 'menace',
                'duration': 'forever',
            },
            source=source_id,
            controller=controller,
        ),
        Event(
            type=EventType.CANT_BLOCK,
            payload={
                'object_id': target_id,
                'duration': 'forever',
            },
            source=source_id,
            controller=controller,
        ),
    ]


__all_phase5__ = [
    "suspect_creature",
    "collect_evidence",
    "was_bargained",
    "make_room_setup",
    "is_door_unlocked",
]


# =============================================================================
# Sweep 4: becomes_creature
# =============================================================================
#
# Implements "[permanent] becomes an X/Y creature with [keywords] [until end
# of turn]". Common patterns:
#   * "Target land you control becomes a 3/3 Elemental creature with haste
#     until end of turn. It's still a land."
#   * "{4}: This artifact becomes a 4/4 artifact creature until end of turn."
#
# Implementation: install QUERY interceptors that override the target's
# power, toughness, types (add CREATURE), subtypes, and ability set. The
# interceptors carry duration='end_of_turn' so the standard cleanup runs at
# end-step.
# =============================================================================


def becomes_creature(
    target: GameObject,
    state: GameState,
    *,
    power: int,
    toughness: int,
    subtypes: Optional[set[str]] = None,
    keywords: Optional[list[str]] = None,
    duration: str = "end_of_turn",
    keep_land: bool = True,
) -> list[Event]:
    """Install QUERY interceptors that turn ``target`` into a creature.

    Returns ``[]`` (no events to enqueue) — the helper mutates state
    directly. The interceptors are tagged with ``_becomes_creature_tag``
    so they can be identified for removal if the caller wants to revert
    the effect early.

    ``keep_land=True`` preserves the LAND type if the target is a land.
    Same for artifact / enchantment.
    """
    subtypes_to_add = set(subtypes or set())
    keywords_to_grant = list(keywords or [])
    target_id = target.id
    tag_id = new_id()

    # --- POWER ---
    def power_filter(event: Event, st: GameState) -> bool:
        return (event.type == EventType.QUERY_POWER
                and event.payload.get('object_id') == target_id)

    def power_handler(event: Event, st: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['value'] = power
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # --- TOUGHNESS ---
    def tough_filter(event: Event, st: GameState) -> bool:
        return (event.type == EventType.QUERY_TOUGHNESS
                and event.payload.get('object_id') == target_id)

    def tough_handler(event: Event, st: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['value'] = toughness
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # --- TYPES (add CREATURE; preserve original by default if keep_land) ---
    def types_filter(event: Event, st: GameState) -> bool:
        return (event.type == EventType.QUERY_TYPES
                and event.payload.get('object_id') == target_id)

    def types_handler(event: Event, st: GameState) -> InterceptorResult:
        new_event = event.copy()
        existing = new_event.payload.get('value') or set(target.characteristics.types)
        new_types = set(existing)
        new_types.add(CardType.CREATURE)
        new_event.payload['value'] = new_types
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # --- ABILITIES (add granted keywords) ---
    def abilities_filter(event: Event, st: GameState) -> bool:
        return (event.type == EventType.QUERY_ABILITIES
                and event.payload.get('object_id') == target_id)

    def abilities_handler(event: Event, st: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []) or [])
        for kw in keywords_to_grant:
            if kw not in granted:
                granted.append(kw)
        new_event.payload['granted'] = granted
        # Some callers read 'value' as a set/list of names too:
        existing_value = new_event.payload.get('value')
        if isinstance(existing_value, (set, list)):
            value_set = set(existing_value) | set(keywords_to_grant)
            new_event.payload['value'] = value_set
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    pairs = [
        (power_filter, power_handler),
        (tough_filter, tough_handler),
        (types_filter, types_handler),
        (abilities_filter, abilities_handler),
    ]

    for filt, hand in pairs:
        ic = Interceptor(
            id=new_id(),
            source=target_id,
            controller=target.controller,
            priority=InterceptorPriority.QUERY,
            filter=filt,
            handler=hand,
            duration=duration,
        )
        setattr(ic, '_becomes_creature_tag', tag_id)
        state.interceptors[ic.id] = ic
        ic.timestamp = state.next_timestamp()

    # If subtypes were specified, dual-write onto the target so direct
    # readers stay consistent — and stash the original for cleanup so the
    # subtypes don't leak past the end of the duration.
    if subtypes_to_add:
        prior_subtypes = set(target.characteristics.subtypes)
        target.characteristics.subtypes |= subtypes_to_add

        if duration == "end_of_turn":
            cleanups = getattr(state, '_becomes_creature_cleanups', None)
            if cleanups is None:
                cleanups = {}
                state._becomes_creature_cleanups = cleanups
            cleanups[tag_id] = {
                'target_id': target_id,
                'original_subtypes': prior_subtypes,
            }

    return []


__all_sweep4__ = [
    "becomes_creature",
]


# =============================================================================
# "Until your next turn" land/creature animation
# =============================================================================
#
# Some cards (Rootwise Survivor — DSK Survival) animate a permanent "until
# your next turn" rather than "until end of turn". The animation must persist
# through the opponent's turn and only revert at the start of the controller's
# *next* turn. ``becomes_creature`` already accepts ``duration='until_your_next_turn'``
# (the duration string flows down to every QUERY interceptor it installs), but
# its EOT-only cleanup hook does not stash subtype dual-writes for that
# duration. This wrapper fills that gap by recording the original subtypes in
# ``state._until_your_next_turn_cleanups`` so ``TurnManager`` can peel them off
# at TURN_START for the controller.
# =============================================================================


def make_until_next_turn_animation(
    target: GameObject,
    state: GameState,
    *,
    controller: str,
    power: int,
    toughness: int,
    subtypes: Optional[set[str]] = None,
    keywords: Optional[list[str]] = None,
    keep_land: bool = True,
) -> list[Event]:
    """Animate ``target`` as a creature until ``controller``'s next turn.

    Thin wrapper around :func:`becomes_creature` that:
      * forces ``duration='until_your_next_turn'`` on every QUERY interceptor;
      * stashes original subtypes (and the controller scope) into
        ``state._until_your_next_turn_cleanups`` so the TurnManager sweep
        at the controller's TURN_START restores them.

    ``controller`` is the player whose next turn ends the effect — typically
    the source's controller, not necessarily the target's controller (a land
    you control with this animation reverts at *your* next turn).
    """
    subtypes_to_add = set(subtypes or set())
    prior_subtypes = set(target.characteristics.subtypes)
    target_id = target.id

    # Snapshot interceptor ids registered before the call, so we can identify
    # the ones becomes_creature just installed and tag them with the cleanup
    # payload's controller (the TurnManager filters on ic.controller).
    pre_ids = set(state.interceptors.keys())
    becomes_creature(
        target,
        state,
        power=power,
        toughness=toughness,
        subtypes=subtypes_to_add or None,
        keywords=keywords,
        duration="until_your_next_turn",
        keep_land=keep_land,
    )
    new_ids = [iid for iid in state.interceptors.keys() if iid not in pre_ids]

    # Override the controller on the freshly-installed interceptors so the
    # cleanup sweep matches against the *animation owner's* turn, not the
    # target's controller (in MTG these usually coincide, but the helper
    # accepts a separate controller for safety).
    tag_id = None
    for iid in new_ids:
        ic = state.interceptors.get(iid)
        if ic is None:
            continue
        ic.controller = controller
        if tag_id is None:
            tag_id = getattr(ic, "_becomes_creature_tag", None)

    # Stash subtype dual-write cleanup keyed by tag id. ``becomes_creature``
    # only stashes for duration='end_of_turn'; we mirror that for
    # 'until_your_next_turn'.
    if subtypes_to_add and tag_id is not None:
        cleanups = getattr(state, "_until_your_next_turn_cleanups", None)
        if cleanups is None:
            cleanups = {}
            state._until_your_next_turn_cleanups = cleanups
        cleanups[tag_id] = {
            "target_id": target_id,
            "original_subtypes": prior_subtypes,
            "controller": controller,
        }

    return []


__all_until_next_turn__ = [
    "make_until_next_turn_animation",
]


# =============================================================================
# Vehicle animation: Exhaust ability that turns the source into a creature
# =============================================================================
#
# Aetherdrift "vehicle" pattern: an artifact with a printed Exhaust ability
# of the form
#
#     Exhaust — {N}: This Vehicle becomes an artifact creature with
#                    base P/T <p>/<t> until end of turn.
#
# The helper wraps make_exhaust_ability so the effect_fn calls
# ``becomes_creature`` on the source. EOT cleanup is handled by the existing
# subtype-restoration hook plus the QUERY-interceptor sweep.
# =============================================================================


def make_animate_via_exhaust(
    obj: GameObject,
    *,
    cost: str,
    power: int,
    toughness: int,
    subtypes_to_add: Optional[set[str]] = None,
    keywords: Optional[list[str]] = None,
    plus_one_counters: int = 0,
    description: Optional[str] = None,
):
    """Register an Exhaust ability that animates the source into a creature.

    ``cost`` is the activation cost text (e.g. ``"{4}"``). On activation the
    source becomes a creature with the given base ``power``/``toughness``,
    optional creature ``subtypes_to_add`` (e.g. {"Vehicle", "Construct"}),
    and optional ``keywords`` (e.g. ["haste"]) until end of turn. If
    ``plus_one_counters`` > 0, that many +1/+1 counters are placed on the
    source as a rider (Aetherdrift's printed Vehicle-animate template adds
    one +1/+1 counter; Marshals' Pathcruiser adds two; Invasion Submersible
    adds three).

    Implementation: composes ``make_vehicle_animation_ability`` (which goes
    through ``GRANT_CREATURE_TYPE`` + ``PT_MODIFICATION`` events) plus a
    ``becomes_creature`` sweep when ``subtypes_to_add`` is non-empty (so
    those subtypes are dual-written onto ``obj.characteristics`` and
    cleaned up at EOT) plus a ``COUNTER_ADDED`` rider when
    ``plus_one_counters > 0``.
    """
    subtypes_set = set(subtypes_to_add or set())
    keyword_list = list(keywords or [])
    counters = int(plus_one_counters)
    desc = description or (
        f"{cost}: This Vehicle becomes an artifact creature with "
        f"base P/T {power}/{toughness} until end of turn."
    )

    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        # 1. GRANT_CREATURE_TYPE — install the QUERY interceptor that adds
        #    CREATURE to the type-set. Mirrors the pipeline handler so the
        #    type flip is visible to ``get_types`` immediately.
        _install_grant_creature_type(o, st, duration='end_of_turn')
        # 2. PT_MODIFICATION — set the effective P/T to the requested base.
        #    Mutate state directly (mirroring _handle_pt_modification) so the
        #    effect lands even when callers consume resolve_fn directly.
        printed_power = o.characteristics.power
        if printed_power is None:
            printed_power = 0
        printed_toughness = o.characteristics.toughness
        if printed_toughness is None:
            printed_toughness = 0
        if not hasattr(o.state, 'pt_modifiers'):
            o.state.pt_modifiers = []
        o.state.pt_modifiers.append({
            'power': power - printed_power,
            'toughness': toughness - printed_toughness,
            'duration': 'end_of_turn',
            'timestamp': st.timestamp,
        })
        # 3. Optional keyword grants — apply directly (mirroring
        #    _handle_grant_keyword) so dual-readers on direct
        #    ``obj.characteristics.abilities`` see the keyword.
        for kw in keyword_list:
            kw_norm = str(kw).strip().lower()
            if not kw_norm:
                continue
            o.characteristics.abilities.append({
                'keyword': kw_norm,
                '_temporary': True,
                '_duration': 'end_of_turn',
            })
        # 4. Subtype dual-write (matches becomes_creature's subtype-only
        #    path, which stashes original subtypes for EOT cleanup).
        if subtypes_set:
            prior_subtypes = set(o.characteristics.subtypes)
            o.characteristics.subtypes |= subtypes_set
            cleanups = getattr(st, '_becomes_creature_cleanups', None)
            if cleanups is None:
                cleanups = {}
                st._becomes_creature_cleanups = cleanups
            cleanups[new_id()] = {
                'target_id': o.id,
                'original_subtypes': prior_subtypes,
            }
        # 5. Optional +1/+1 counter rider — emit as an event so the
        #    counter handler runs.
        events: list[Event] = []
        if counters > 0:
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    'object_id': o.id,
                    'counter_type': '+1/+1',
                    'amount': counters,
                },
                source=o.id, controller=o.controller,
            ))
        return events

    return make_exhaust_ability(
        obj, cost=cost, effect_fn=_effect, description=desc,
    )


# =============================================================================
# Vehicle animation: GRANT_CREATURE_TYPE-based activated ability
# =============================================================================
#
# Lower-level vehicle-animation helper. Unlike ``make_animate_via_exhaust``
# (which delegates to the full ``becomes_creature`` sweep), this helper
# composes two pipeline events:
#
#   1. ``GRANT_CREATURE_TYPE`` — installs a QUERY interceptor on the target
#      so ``get_types(obj, state)`` returns a set that includes
#      ``CardType.CREATURE``.
#   2. ``PT_MODIFICATION`` — sets the source's effective P/T to the given
#      base values for the duration.
#
# Plus an optional set of granted ``keywords`` (e.g. ``["vigilance"]``) via
# ``GRANT_KEYWORD`` events. The activated ability is registered through
# ``make_activated_ability`` so callers can plug arbitrary cost text and
# the ``once_per_game`` flag is opt-in (the default is ``False``; pass
# ``once_per_game=True`` to wrap the Aetherdrift Exhaust contract on top).
#
# This is the API the four wired Aetherdrift vehicle cards consume.
# =============================================================================


def _install_grant_creature_type(
    obj: GameObject,
    state: GameState,
    *,
    duration: str = "end_of_turn",
):
    """Install the QUERY_TYPES interceptor that adds CREATURE to ``obj``.

    Mirrors the side-effect of the ``GRANT_CREATURE_TYPE`` pipeline handler
    so callers (including the Vehicle animation activated abilities) can
    take the effect immediately on ability resolution rather than waiting
    for an event hop. The interceptor is tagged with
    ``_grant_creature_type_tag`` and carries ``duration='end_of_turn'`` so
    the standard cleanup sweep removes it.
    """
    target_id = obj.id
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
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=_filter,
        handler=_handler,
        duration=duration,
    )
    setattr(interceptor, "_grant_creature_type_tag", tag_id)
    state.interceptors[interceptor.id] = interceptor
    interceptor.timestamp = state.next_timestamp()
    return interceptor


def make_vehicle_animation_ability(
    obj: GameObject,
    *,
    cost: str,
    power: int,
    toughness: int,
    duration: str = "end_of_turn",
    keywords: Optional[list[str]] = None,
    once_per_game: bool = False,
    sorcery_speed: bool = False,
    own_turn_only: bool = False,
    description: Optional[str] = None,
):
    """Register an activated ability that animates a non-creature artifact.

    On activation:
      1. Adds ``CardType.CREATURE`` to the target's type-set via a QUERY
         interceptor (matching the ``GRANT_CREATURE_TYPE`` event handler).
      2. Sets the effective P/T to the requested base via a
         ``PT_MODIFICATION`` event (the priority system emits this
         through the pipeline; ``_handle_pt_modification`` records the
         mod on ``obj.state.pt_modifiers`` for ``get_power`` / ``get_toughness``).
      3. Optionally grants ``keywords`` via ``GRANT_KEYWORD`` events.

    ``duration`` is one of:
      - ``"end_of_turn"`` (default): standard EOT cleanup sweep removes
        the QUERY interceptor and the P/T mod.
      - ``"until_leaves"``: granted until the source leaves the battlefield.
      - ``"forever"``: persists permanently (rarely used; reserved for
        cards that say "this Vehicle is also a creature").

    ``once_per_game=True`` makes the ability follow the Exhaust contract
    (one activation per permanent, ever). ``sorcery_speed`` and
    ``own_turn_only`` mirror ``make_activated_ability``.

    Returns the registered ``ActivatedAbility`` descriptor.
    """
    keyword_list = list(keywords or [])
    desc = description or (
        f"{cost}: Until end of turn, this Vehicle becomes a "
        f"{power}/{toughness} artifact creature"
        + (f" with {', '.join(keyword_list)}." if keyword_list else ".")
    )

    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        # 1. Install the GRANT_CREATURE_TYPE QUERY interceptor (mirrors the
        #    pipeline handler so the type flip is visible to ``get_types``
        #    immediately).
        _install_grant_creature_type(o, st, duration=duration)
        # 2. PT_MODIFICATION — apply directly so ``get_power`` /
        #    ``get_toughness`` see the override even when the caller
        #    consumes the resolve_fn return list directly.
        printed_power = o.characteristics.power
        if printed_power is None:
            printed_power = 0
        printed_toughness = o.characteristics.toughness
        if printed_toughness is None:
            printed_toughness = 0
        if not hasattr(o.state, 'pt_modifiers'):
            o.state.pt_modifiers = []
        o.state.pt_modifiers.append({
            'power': power - printed_power,
            'toughness': toughness - printed_toughness,
            'duration': duration,
            'timestamp': st.timestamp,
        })
        # 3. Granted keywords — apply directly so direct readers on
        #    ``obj.characteristics.abilities`` see them.
        for kw in keyword_list:
            kw_norm = str(kw).strip().lower()
            if not kw_norm:
                continue
            o.characteristics.abilities.append({
                'keyword': kw_norm,
                '_temporary': True,
                '_duration': duration,
            })
        return []

    return make_activated_ability(
        obj,
        cost=cost,
        effect_fn=_effect,
        description=desc,
        sorcery_speed=sorcery_speed,
        own_turn_only=own_turn_only,
        once_per_game=once_per_game,
    )


# =============================================================================
# Sweep 4b: becomes_copy_of (continuous-effect copy)
# =============================================================================
#
# Implements "X becomes a copy of Y until end of turn" — distinct from
# token-copy (which creates a fresh permanent) in that it OVERRIDES an
# existing permanent's queryable characteristics via QUERY interceptors.
#
# Reference cards:
#   * Oko, the Ringleader: "Oko becomes a copy of up to one target creature
#     you control until end of turn, except he has hexproof."
#   * Fleeting Reflection: "Until end of turn, [target] becomes a copy of up
#     to one other target creature."
#   * Likeness Looter: "{X}: This creature becomes a copy of target creature
#     card in your graveyard with mana value X, except it has flying ..."
#
# Implementation notes (CR 707.2):
#   - Copy is a continuous effect that re-evaluates each query, so the
#     installed handlers read **live** from the source object whenever
#     possible (so a +1/+1 counter, a pump effect, or a layered enchant
#     applied to the source after install propagates to the target).
#   - If the source leaves the zone, fall back to the snapshot taken at
#     install time (CR 707.4 — once a copy effect has copied the
#     characteristics it doesn't lose them when the source leaves).
#   - `except_*` overrides are applied LAST so they win over the live read.
#   - Subtypes are dual-written onto target.characteristics.subtypes so the
#     ~250 direct readers across the codebase stay consistent. Snapshot
#     of the original printed subtypes is kept for cleanup.
# =============================================================================


def becomes_copy_of(
    target: GameObject,
    source: GameObject,
    state: GameState,
    *,
    duration: str = "end_of_turn",
    except_subtypes: Optional[set[str]] = None,
    add_subtypes: Optional[set[str]] = None,
    except_keywords: Optional[list[str]] = None,
    except_pt: Optional[tuple] = None,
    except_colors: Optional[set] = None,
    except_types: Optional[set] = None,
    keep_card_def: bool = True,
) -> list[Event]:
    """Make ``target`` become a copy of ``source`` for ``duration``.

    Installs QUERY interceptors on ``target`` for POWER, TOUGHNESS, TYPES,
    SUBTYPES, COLORS, and ABILITIES that read live from
    ``state.objects.get(source.id)`` whenever the source is still on the
    battlefield (CR 707.2 — copy is a continuous effect that re-evaluates
    each query). If the source has since left, the handlers fall back to a
    snapshot of the source's characteristics taken at install time.

    The ``except_*`` overrides apply LAST, so e.g. Oko's
    ``except_keywords=['hexproof']`` keeps hexproof even if the live source
    later loses it.

    Subtypes are dual-written onto ``target.characteristics.subtypes`` to
    keep the 250+ direct readers across the codebase consistent. The
    original printed subtypes are stashed on a snapshot and restored when
    the EOT sweep removes the QUERY interceptors.

    Cycle guard: copying-from-a-copy recurses into the source's queries
    (so chains "C copies B copies A" work). A per-state stack
    (``state._copy_resolution_stack``) breaks self-cycles by falling back
    to the snapshot.
    """
    import copy as _copy

    # Late import: ``queries`` lives next to the engine, but importing it
    # at module load time creates a circular import (interceptor_helpers
    # is imported by card files which are loaded by engine startup).
    from src.engine.queries import (
        get_power, get_toughness, get_types, get_subtypes,
        get_supertypes, get_colors, _make_query_event, _is_abilities_query,
    )

    target_id = target.id
    source_id = source.id
    tag_id = new_id()

    # Snapshot of source characteristics for the source-leaves-zone path.
    # Use deepcopy so later mutation of source.characteristics can't bleed
    # into the snapshot.
    snapshot = _copy.deepcopy(source.characteristics)
    snapshot_card_def = source.card_def

    # Snapshot of target's printed subtypes/supertypes for cleanup.
    original_target_subtypes = set(target.characteristics.subtypes)
    original_target_supertypes = set(target.characteristics.supertypes)

    # Pre-compute except_* canonical forms.
    except_keywords_lower = (
        [str(k).lower() for k in (except_keywords or [])]
    )
    except_subtypes_set = set(except_subtypes) if except_subtypes else None
    add_subtypes_set = set(add_subtypes or set())

    # ------------------------------------------------------------------
    # Helpers shared by the handlers below.
    # ------------------------------------------------------------------
    def _live_source(st: GameState):
        """Return the live source object iff it's still on the battlefield."""
        live = st.objects.get(source_id)
        if live is None:
            return None
        if getattr(live, 'zone', None) != ZoneType.BATTLEFIELD:
            return None
        return live

    def _push_cycle_guard(st: GameState) -> bool:
        """Push target_id onto the copy-resolution stack; return False if
        we're already mid-resolution for this target (cycle)."""
        stack = getattr(st, '_copy_resolution_stack', None)
        if stack is None:
            stack = set()
            st._copy_resolution_stack = stack
        if target_id in stack:
            return False
        stack.add(target_id)
        return True

    def _pop_cycle_guard(st: GameState) -> None:
        stack = getattr(st, '_copy_resolution_stack', None)
        if stack and target_id in stack:
            stack.discard(target_id)

    # ------------------------------------------------------------------
    # POWER
    # ------------------------------------------------------------------
    def power_filter(event: Event, st: GameState) -> bool:
        return (event.type == EventType.QUERY_POWER
                and event.payload.get('object_id') == target_id)

    def power_handler(event: Event, st: GameState) -> InterceptorResult:
        new_event = event.copy()
        if not _push_cycle_guard(st):
            # Self-cycle: fall back to snapshot.
            value = snapshot.power if snapshot.power is not None else 0
        else:
            try:
                live = _live_source(st)
                if live is not None:
                    # Recurse into queries so layered effects on source
                    # (counters, pump, becomes_copy chains) propagate.
                    value = get_power(live, st)
                else:
                    value = snapshot.power if snapshot.power is not None else 0
            finally:
                _pop_cycle_guard(st)
        if except_pt is not None:
            value = except_pt[0]
        new_event.payload['value'] = value
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # ------------------------------------------------------------------
    # TOUGHNESS
    # ------------------------------------------------------------------
    def tough_filter(event: Event, st: GameState) -> bool:
        return (event.type == EventType.QUERY_TOUGHNESS
                and event.payload.get('object_id') == target_id)

    def tough_handler(event: Event, st: GameState) -> InterceptorResult:
        new_event = event.copy()
        if not _push_cycle_guard(st):
            value = snapshot.toughness if snapshot.toughness is not None else 0
        else:
            try:
                live = _live_source(st)
                if live is not None:
                    value = get_toughness(live, st)
                else:
                    value = snapshot.toughness if snapshot.toughness is not None else 0
            finally:
                _pop_cycle_guard(st)
        if except_pt is not None:
            value = except_pt[1]
        new_event.payload['value'] = value
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # ------------------------------------------------------------------
    # TYPES
    # ------------------------------------------------------------------
    def types_filter(event: Event, st: GameState) -> bool:
        return (event.type == EventType.QUERY_TYPES
                and event.payload.get('object_id') == target_id)

    def types_handler(event: Event, st: GameState) -> InterceptorResult:
        new_event = event.copy()
        if not _push_cycle_guard(st):
            value = set(snapshot.types)
        else:
            try:
                live = _live_source(st)
                if live is not None:
                    value = set(get_types(live, st))
                else:
                    value = set(snapshot.types)
            finally:
                _pop_cycle_guard(st)
        if except_types is not None:
            value = set(except_types)
        new_event.payload['value'] = value
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # ------------------------------------------------------------------
    # SUBTYPES
    # ------------------------------------------------------------------
    def subtypes_filter(event: Event, st: GameState) -> bool:
        return (event.type == EventType.QUERY_SUBTYPES
                and event.payload.get('object_id') == target_id)

    def subtypes_handler(event: Event, st: GameState) -> InterceptorResult:
        new_event = event.copy()
        if not _push_cycle_guard(st):
            value = set(snapshot.subtypes)
        else:
            try:
                live = _live_source(st)
                if live is not None:
                    value = set(get_subtypes(live, st))
                else:
                    value = set(snapshot.subtypes)
            finally:
                _pop_cycle_guard(st)
        if except_subtypes_set is not None:
            value = set(except_subtypes_set)
        if add_subtypes_set:
            value = value | add_subtypes_set
        new_event.payload['value'] = value
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # ------------------------------------------------------------------
    # SUPERTYPES (Legendary, Snow, World, Basic)
    # ------------------------------------------------------------------
    def supertypes_filter(event: Event, st: GameState) -> bool:
        return (event.type == EventType.QUERY_SUPERTYPES
                and event.payload.get('object_id') == target_id)

    def supertypes_handler(event: Event, st: GameState) -> InterceptorResult:
        new_event = event.copy()
        if not _push_cycle_guard(st):
            value = set(snapshot.supertypes)
        else:
            try:
                live = _live_source(st)
                if live is not None:
                    value = set(get_supertypes(live, st))
                else:
                    value = set(snapshot.supertypes)
            finally:
                _pop_cycle_guard(st)
        new_event.payload['value'] = value
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # ------------------------------------------------------------------
    # COLORS
    # ------------------------------------------------------------------
    def colors_filter(event: Event, st: GameState) -> bool:
        return (event.type == EventType.QUERY_COLORS
                and event.payload.get('object_id') == target_id)

    def colors_handler(event: Event, st: GameState) -> InterceptorResult:
        new_event = event.copy()
        if not _push_cycle_guard(st):
            value = set(snapshot.colors)
        else:
            try:
                live = _live_source(st)
                if live is not None:
                    value = set(get_colors(live, st))
                else:
                    value = set(snapshot.colors)
            finally:
                _pop_cycle_guard(st)
        if except_colors is not None:
            value = set(except_colors)
        new_event.payload['value'] = value
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # ------------------------------------------------------------------
    # ABILITIES
    # ------------------------------------------------------------------
    def abilities_filter(event: Event, st: GameState) -> bool:
        return (event.type == EventType.QUERY_ABILITIES
                and event.payload.get('object_id') == target_id)

    def abilities_handler(event: Event, st: GameState) -> InterceptorResult:
        new_event = event.copy()
        # Build the ability/keyword set from the source.
        source_keywords: set[str] = set()
        if not _push_cycle_guard(st):
            for ab in snapshot.abilities or []:
                if isinstance(ab, dict) and ab.get('keyword'):
                    source_keywords.add(str(ab['keyword']).lower())
        else:
            try:
                live = _live_source(st)
                if live is not None:
                    # Read printed abilities from the live source.
                    for ab in (live.characteristics.abilities or []):
                        if isinstance(ab, dict) and ab.get('keyword'):
                            source_keywords.add(str(ab['keyword']).lower())
                    # AND chain through any QUERY_ABILITIES interceptors on
                    # the source (so copy-of-copy granted keywords flow up).
                    sub_event = _make_query_event('abilities', live, [])
                    for ic in sorted(
                        [i for i in st.interceptors.values()
                         if i.priority == InterceptorPriority.QUERY
                         and _is_abilities_query(i, live, st)],
                        key=lambda i: i.timestamp,
                    ):
                        result = ic.handler(sub_event, st)
                        if result.transformed_event is not None:
                            sub_event = result.transformed_event
                    granted = sub_event.payload.get('granted') or []
                    for kw in granted:
                        source_keywords.add(str(kw).lower())
                else:
                    for ab in snapshot.abilities or []:
                        if isinstance(ab, dict) and ab.get('keyword'):
                            source_keywords.add(str(ab['keyword']).lower())
            finally:
                _pop_cycle_guard(st)

        # except_keywords: REPLACE rather than augment (matches token-copy
        # semantics in zone.py which sets characteristics.abilities to the
        # except_keywords list verbatim).
        if except_keywords is not None:
            keywords = set(except_keywords_lower)
        else:
            keywords = source_keywords

        granted = list(new_event.payload.get('granted', []) or [])
        for kw in keywords:
            if kw not in granted:
                granted.append(kw)
        new_event.payload['granted'] = granted

        existing_value = new_event.payload.get('value')
        if isinstance(existing_value, (set, list)):
            new_event.payload['value'] = set(existing_value) | set(keywords)
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    # ------------------------------------------------------------------
    # Register all six interceptors.
    # ------------------------------------------------------------------
    pairs = [
        (power_filter, power_handler),
        (tough_filter, tough_handler),
        (types_filter, types_handler),
        (subtypes_filter, subtypes_handler),
        (supertypes_filter, supertypes_handler),
        (colors_filter, colors_handler),
        (abilities_filter, abilities_handler),
    ]

    interceptor_ids: list[str] = []
    for filt, hand in pairs:
        ic = Interceptor(
            id=new_id(),
            source=target_id,
            controller=target.controller,
            priority=InterceptorPriority.QUERY,
            filter=filt,
            handler=hand,
            duration=duration,
        )
        setattr(ic, '_becomes_copy_tag', tag_id)
        setattr(ic, '_becomes_copy_target', target_id)
        state.interceptors[ic.id] = ic
        ic.timestamp = state.next_timestamp()
        interceptor_ids.append(ic.id)

    # ------------------------------------------------------------------
    # Dual-write subtypes onto the target so direct readers stay
    # consistent. Stash the original for restoration in cleanup.
    # ------------------------------------------------------------------
    new_subtypes = set(snapshot.subtypes)
    if except_subtypes_set is not None:
        new_subtypes = set(except_subtypes_set)
    if add_subtypes_set:
        new_subtypes = new_subtypes | add_subtypes_set
    target.characteristics.subtypes = set(new_subtypes)
    target.characteristics.supertypes = set(snapshot.supertypes)

    # Register a cleanup hook on the state that the EOT sweep will run to
    # restore the dual-write fields. The existing _do_cleanup_step removes
    # interceptors with duration='end_of_turn' but doesn't touch
    # obj.characteristics, so we attach a small restoration callback list
    # keyed by tag.
    if duration == "end_of_turn":
        cleanups = getattr(state, '_becomes_copy_cleanups', None)
        if cleanups is None:
            cleanups = {}
            state._becomes_copy_cleanups = cleanups
        cleanups[tag_id] = {
            'target_id': target_id,
            'original_subtypes': original_target_subtypes,
            'original_supertypes': original_target_supertypes,
            'interceptor_ids': interceptor_ids,
        }

    return []


__all_sweep4b__ = [
    "becomes_copy_of",
]


# =============================================================================
# Replacement effects
# =============================================================================
#
# A replacement effect rewrites an event as it passes through the pipeline:
# "If X would happen, Y instead." Implemented as TRANSFORM-priority
# interceptors. A loop-prevention marker is pinned on the event payload so a
# replacement does not re-fire on its own output (see ``apply_once_per_event``).
#
# This helper is a card-side wrapper around the engine-level primitive in
# ``src/engine/replacements.py::make_replacement_interceptor``. The core
# differences:
#
#   * ``replace_fn`` is allowed to return either a single ``Event`` or a
#     ``list[Event]`` for ergonomics. The first event is what the resolver
#     actually applies; any extras are queued as REACT-phase follow-ups via a
#     one-shot interceptor so they ride out on the same emit() call (this is a
#     v1 simplification for the rare multi-event replacement; the common case
#     is a single rewritten event).
#   * ``duration`` accepts ``'permanent'`` (alias for ``'forever'``),
#     ``'end_of_turn'`` (swept by the existing TurnManager cleanup), and
#     ``'one_shot'`` (use it once, then self-destruct). Permanent replacements
#     get tagged with ``_cleanup_on_zone_change`` so the source's death/exile
#     evicts the interceptor automatically.
#   * Optionally fires ``EventType.REPLACEMENT_FIRED`` for tracing.
# =============================================================================


def make_replacement_effect(
    source: GameObject,
    *,
    event_filter: Callable[[Event, GameState], bool],
    replace_fn: Callable[[Event, GameState], Any],
    duration: str = 'permanent',
    apply_once_per_event: bool = True,
    emit_telemetry: bool = False,
    require_battlefield: bool = True,
) -> list[Interceptor]:
    """Build a generic "if X would happen, Y instead" replacement effect.

    Args:
        source: the permanent providing the replacement effect.
        event_filter: ``(event, state) -> bool``. Return True to replace.
        replace_fn: ``(event, state) -> Event | list[Event] | None``. The
            returned event(s) replace the original. Return None or an empty
            list to fall through (no replacement happens).
        duration: ``'permanent'`` (alias for ``'forever'``), ``'end_of_turn'``
            (swept by TurnManager cleanup), or ``'one_shot'`` (one use,
            self-destruct after firing).
        apply_once_per_event: when True (default), the marker
            ``_replaced_by_<interceptor_id>`` is pinned on the replacement
            event so this same replacer cannot re-fire on its own output.
            *Other* replacers may still rewrite the output.
        emit_telemetry: when True, fires an ``EventType.REPLACEMENT_FIRED``
            event after the replacement. The event is added as a REACT-phase
            follow-up so it doesn't itself get replaced.
        require_battlefield: gate on the source still being on the
            battlefield. Almost always desirable.

    Returns:
        A list with one ``Interceptor`` (returning a list keeps a uniform shape
        with other helpers like ``becomes_creature``). Permanent replacements
        get the ``_cleanup_on_zone_change`` tag so they self-evict if the
        source leaves play.
    """
    # Normalise duration aliases.
    duration_norm = (duration or 'permanent').strip().lower().replace(' ', '_')
    if duration_norm in ('permanent', 'forever', 'static'):
        engine_duration = 'forever'
    elif duration_norm in ('end_of_turn', 'eot', 'until_end_of_turn',
                           'until_eot', 'this_turn', 'next_end_step',
                           'end_of_this_turn'):
        engine_duration = 'end_of_turn'
    elif duration_norm in ('one_shot', 'oneshot', 'once', 'use_once'):
        engine_duration = 'forever'  # self-destructs via uses_remaining=1
    else:
        engine_duration = duration_norm  # passthrough for advanced callers

    one_shot = duration_norm in ('one_shot', 'oneshot', 'once', 'use_once')

    source_id = source.id
    interceptor_id = new_id()
    marker_key = f"_replaced_by_{interceptor_id}"

    def _has_marker(event: Event) -> bool:
        return bool(event.payload.get(marker_key))

    def _set_marker(event: Event) -> None:
        event.payload[marker_key] = True

    def filter_fn(event: Event, state: GameState) -> bool:
        if apply_once_per_event and _has_marker(event):
            return False
        if require_battlefield:
            src = state.objects.get(source_id)
            if not src or src.zone != ZoneType.BATTLEFIELD:
                return False
        try:
            return bool(event_filter(event, state))
        except Exception:
            return False

    def handler(event: Event, state: GameState) -> InterceptorResult:
        try:
            replacement = replace_fn(event, state)
        except Exception:
            return InterceptorResult(action=InterceptorAction.PASS)

        # Normalise return shape: None / [] -> no-op; Event -> [Event].
        if replacement is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        if isinstance(replacement, Event):
            replacement_events = [replacement]
        elif isinstance(replacement, (list, tuple)):
            replacement_events = [e for e in replacement if isinstance(e, Event)]
        else:
            return InterceptorResult(action=InterceptorAction.PASS)
        if not replacement_events:
            return InterceptorResult(action=InterceptorAction.PASS)

        primary = replacement_events[0]
        extras = list(replacement_events[1:])

        # Pin the loop-prevention marker on every replacement event so this
        # replacer cannot fire on its own output. Other replacers still can.
        if apply_once_per_event:
            _set_marker(primary)
            for extra in extras:
                _set_marker(extra)

        react_followups: list[Event] = []
        if extras:
            # Queue extras as REACT-phase events so they ride out on the same
            # emit() call. They're already marker-tagged so the same replacer
            # won't bite them.
            react_followups.extend(extras)

        if emit_telemetry:
            try:
                original_payload = {
                    k: v for k, v in event.payload.items()
                    if not (isinstance(k, str) and k.startswith('_replaced_by_'))
                }
            except Exception:
                original_payload = {}
            react_followups.append(Event(
                type=EventType.REPLACEMENT_FIRED,
                payload={
                    'source': source_id,
                    'replacer_id': interceptor_id,
                    'original_type': event.type,
                    'original_payload': original_payload,
                    'replacement_count': len(replacement_events),
                },
                source=source_id,
                controller=getattr(source, 'controller', None),
            ))

        # If we have any react-phase follow-ups, stash them on the state so
        # a sibling REACT interceptor can drain them. Simpler: put them on
        # state._replacement_effect_followups, drained by a system REACT
        # interceptor we register lazily.
        if react_followups:
            buf = getattr(state, '_replacement_effect_followups', None)
            if buf is None:
                buf = []
                state._replacement_effect_followups = buf  # type: ignore[attr-defined]
            buf.extend(react_followups)
            _ensure_replacement_followup_drainer(state)

        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=primary,
        )

    interceptor = Interceptor(
        id=interceptor_id,
        source=source_id,
        controller=source.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        duration=engine_duration,
        uses_remaining=1 if one_shot else None,
    )
    if engine_duration == 'forever':
        # Self-evict on source leaving the battlefield (graveyard / exile),
        # mirroring how ``make_cost_reduction(self_only=True)`` works.
        setattr(interceptor, "_cleanup_on_zone_change", True)
    return [interceptor]


def _ensure_replacement_followup_drainer(state: GameState) -> None:
    """Lazily install a system REACT interceptor that drains queued follow-ups.

    The drainer fires after every event, walks ``state._replacement_effect_followups``,
    and emits one new event per buffered entry. This is the v1 mechanism for
    multi-event replacements and ``REPLACEMENT_FIRED`` telemetry — both ride
    out on the same ``emit()`` call as the original event.
    """
    if getattr(state, '_replacement_effect_drainer_installed', False):
        return

    drainer_id = new_id()

    def drain_filter(event: Event, st: GameState) -> bool:
        # Avoid recursing on our own telemetry / extras: the marker is set so
        # the original replacer skips them, but the drainer should still
        # process *every other event* once (so extras emitted during a TRANSFORM
        # get drained promptly).
        buf = getattr(st, '_replacement_effect_followups', None)
        return bool(buf)

    def drain_handler(event: Event, st: GameState) -> InterceptorResult:
        buf = getattr(st, '_replacement_effect_followups', None) or []
        if not buf:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Drain everything currently queued. New entries added during the
        # subsequent emits will be picked up on the next pipeline iteration.
        outgoing = list(buf)
        buf.clear()
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=outgoing,
        )

    drainer = Interceptor(
        id=drainer_id,
        source="SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=drain_filter,
        handler=drain_handler,
        duration='forever',
    )
    state.interceptors[drainer_id] = drainer
    state._replacement_effect_drainer_installed = True  # type: ignore[attr-defined]


__all_replacement_effects__ = [
    "make_replacement_effect",
]


# =============================================================================
# Sweep 7: Threaten — "Gain control of target + untap + haste EOT"
# =============================================================================
#
# The CONTROL_CHANGE event handler already restores the original controller
# at end of turn. This helper bundles the three events that make up the
# canonical Threaten / Act of Treason effect.
# =============================================================================


def threaten_creature(
    target_id: str,
    new_controller: str,
    source_id: str,
    *,
    duration: str = "end_of_turn",
) -> list[Event]:
    """Standard "gain control + untap + haste" Threaten effect.

    Returns three events to enqueue:
      1. CONTROL_CHANGE — switches controller for the duration
      2. UNTAP — readies the creature
      3. GRANT_KEYWORD haste — lets it attack this turn

    The CONTROL_CHANGE handler stashes the original controller and the turn
    manager restores it at end of turn (see src/engine/turn.py).
    """
    return [
        Event(
            type=EventType.CONTROL_CHANGE,
            payload={
                'object_id': target_id,
                'new_controller': new_controller,
                'duration': duration,
            },
            source=source_id,
            controller=new_controller,
        ),
        Event(
            type=EventType.UNTAP,
            payload={'object_id': target_id},
            source=source_id,
            controller=new_controller,
        ),
        Event(
            type=EventType.GRANT_KEYWORD,
            payload={
                'object_id': target_id,
                'keyword': 'haste',
                'duration': duration,
            },
            source=source_id,
            controller=new_controller,
        ),
    ]


__all_sweep7__ = [
    "threaten_creature",
]


# =============================================================================
# Sweep 10: granted death triggers
# =============================================================================
#
# Pattern: "Until end of turn, target creature gains 'When this creature
# dies, X.'" — a temporary triggered ability granted to another permanent.
# We install a one-shot REACT interceptor on the state that fires on the
# target's OBJECT_DESTROYED and emits the granted effect's events.
# =============================================================================


def grant_death_trigger(
    target: GameObject,
    source: GameObject,
    state: GameState,
    effect_fn: Callable[[GameObject, GameState], list[Event]],
    *,
    duration: str = "end_of_turn",
) -> Interceptor:
    """Install a one-shot REACT interceptor that grants ``target`` a
    "when this creature dies" trigger lasting ``duration``.

    ``effect_fn(target_obj, state)`` returns the events to enqueue when the
    target dies. The interceptor self-removes after firing.

    Returns the installed Interceptor so callers can also remove it
    early if the temporary effect ends some other way.
    """
    target_id = target.id
    source_id = source.id
    controller = source.controller
    int_id = new_id()
    fired = {"done": False}

    def _filter(event: Event, st: GameState) -> bool:
        if fired["done"]:
            return False
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        return event.payload.get("object_id") == target_id

    def _handler(event: Event, st: GameState) -> InterceptorResult:
        fired["done"] = True
        target_obj = st.objects.get(target_id)
        if target_obj is None:
            st.interceptors.pop(int_id, None)
            return InterceptorResult(action=InterceptorAction.PASS)
        try:
            new_events = effect_fn(target_obj, st) or []
        except Exception:
            new_events = []
        st.interceptors.pop(int_id, None)
        if not new_events:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events,
        )

    def _grant_death_eff(event: Event, st: GameState) -> list[Event]:
        fired["done"] = True
        target_obj = st.objects.get(target_id)
        if target_obj is None:
            st.interceptors.pop(int_id, None)
            return []
        try:
            new_events = effect_fn(target_obj, st) or []
        except Exception:
            new_events = []
        st.interceptors.pop(int_id, None)
        return list(new_events)

    interceptor = Interceptor(
        id=int_id,
        source=source_id,
        controller=controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration=duration,
    )
    _mark_triggered_ability(interceptor, _grant_death_eff, description="Granted death trigger")
    interceptor.timestamp = state.next_timestamp()
    state.interceptors[int_id] = interceptor
    return interceptor


__all_sweep10__ = [
    "grant_death_trigger",
]


# =============================================================================
# Sweep 12: generic granted triggered ability
# =============================================================================
#
# Generalises grant_death_trigger to any trigger filter — for cards like
# Embereth Veteran's Young Hero Role token ("Enchanted creature has
# 'Whenever this creature attacks, if its toughness is 3 or less, put a
# +1/+1 counter on it.'") or Requiem Monolith's "Whenever this creature
# is dealt damage, draw cards" rider.
# =============================================================================


def grant_triggered_ability(
    target: GameObject,
    source: GameObject,
    state: GameState,
    *,
    event_filter: Callable[[Event, GameState, str], bool],
    effect_fn: Callable[[GameObject, Event, GameState], list[Event]],
    duration: str = "end_of_turn",
    one_shot: bool = False,
) -> Interceptor:
    """Install a REACT interceptor that grants ``target`` a triggered ability.

    ``event_filter(event, state, target_id)`` returns True when the event
    should activate the granted trigger. The helper threads ``target_id``
    in as the third arg so filters can scope to the granted target without
    closing over it.

    ``effect_fn(target_obj, event, state)`` returns the events to enqueue
    when the trigger fires.

    If ``one_shot`` is True, the interceptor self-removes after the first
    fire (useful for "until X dies, return it" style riders).
    """
    target_id = target.id
    source_id = source.id
    controller = source.controller
    int_id = new_id()
    fired = {"done": False}

    def _filter(event: Event, st: GameState) -> bool:
        if one_shot and fired["done"]:
            return False
        try:
            return bool(event_filter(event, st, target_id))
        except Exception:
            return False

    def _handler(event: Event, st: GameState) -> InterceptorResult:
        target_obj = st.objects.get(target_id)
        if target_obj is None:
            if one_shot:
                fired["done"] = True
                st.interceptors.pop(int_id, None)
            return InterceptorResult(action=InterceptorAction.PASS)
        try:
            new_events = effect_fn(target_obj, event, st) or []
        except Exception:
            new_events = []
        if one_shot:
            fired["done"] = True
            st.interceptors.pop(int_id, None)
        if not new_events:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events,
        )

    def _granted_eff(event: Event, st: GameState) -> list[Event]:
        target_obj = st.objects.get(target_id)
        if target_obj is None:
            if one_shot:
                fired["done"] = True
                st.interceptors.pop(int_id, None)
            return []
        try:
            new_events = effect_fn(target_obj, event, st) or []
        except Exception:
            new_events = []
        if one_shot:
            fired["done"] = True
            st.interceptors.pop(int_id, None)
        return list(new_events)

    interceptor = Interceptor(
        id=int_id,
        source=source_id,
        controller=controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration=duration,
    )
    _mark_triggered_ability(interceptor, _granted_eff, description="Granted triggered ability")
    interceptor.timestamp = state.next_timestamp()
    state.interceptors[int_id] = interceptor
    return interceptor


__all_sweep12__ = [
    "grant_triggered_ability",
]


# =============================================================================
# CONSPIRE GRANT (W29) — Shadowmoor / Lorwyn (CR 702.78)
# =============================================================================
#
# "Each <filtered spell> you cast has conspire" — Raiding Schemes,
# Wort, the Raidmother, etc. This is a thin re-export of
# ``src/engine/conspire.grant_conspire`` so card scripts can call
# ``make_conspire_grant(obj, spell_filter=...)`` from setup_interceptors
# without importing the engine module directly.
#
# Quick-reference filter recipes
# ------------------------------
#
#   # Noncreature spells (Raiding Schemes):
#   def noncreature_filter(spell, state):
#       return CardType.CREATURE not in spell.characteristics.types
#
#   # Red or green instant/sorcery (Wort, the Raidmother):
#   def rg_instant_sorcery_filter(spell, state):
#       types = spell.characteristics.types
#       if not (CardType.INSTANT in types or CardType.SORCERY in types):
#           return False
#       colors = spell.characteristics.colors or set()
#       return Color.RED in colors or Color.GREEN in colors
#
# The filter is invoked at cast time with the spell GameObject and the
# current state. Filters that raise are treated as a non-match (defensive).
# =============================================================================

from src.engine.conspire import grant_conspire as _engine_grant_conspire


def make_conspire_grant(
    obj: GameObject,
    state: GameState,
    *,
    spell_filter: Callable[[GameObject, GameState], bool],
    color_share_required: bool = True,
) -> Interceptor:
    """Install a conspire grant tied to ``obj`` (Raiding Schemes / Wort).

    See ``src/engine/conspire.grant_conspire`` for full semantics. Returns
    the installed Interceptor — typically appended to the list returned by
    ``setup_interceptors``.

    Args:
        obj: the permanent providing the grant.
        state: GameState — needed so the grant is registered on the
            runtime registry on install.
        spell_filter: ``(spell_obj, state) -> bool`` — return True iff
            this grant's conspire applies to the spell about to be cast.
        color_share_required: True (default) = follow CR 702.78 (the two
            tapped creatures must share a color with the spell). Reserved
            for future custom-set variants.

    Example
    -------
    .. code-block:: python

        def raiding_schemes_setup(obj, state):
            def noncreature(spell, _state):
                return CardType.CREATURE not in spell.characteristics.types
            return [make_conspire_grant(obj, state, spell_filter=noncreature)]
    """
    return _engine_grant_conspire(
        obj,
        state,
        spell_filter=spell_filter,
        color_share_required=color_share_required,
    )


__all_conspire__ = [
    "make_conspire_grant",
]


# =============================================================================
# Cycling (W8)
# =============================================================================
#
# "Cycling {cost}" — while in hand, pay {cost} and discard this card to draw
# a card. Variants supported by the engine module ``src/engine/cycling.py``:
#
#   - Plain cycling: discard, draw 1.
#   - Landcycling: ``landcycling=['Mountain']`` -> search library for a land
#     of that subtype, reveal, put it into hand, shuffle.
#   - Typecycling: ``typecycling='Wizard'`` -> search library for a card with
#     that subtype, reveal, put it into hand, shuffle.
#   - Rider: ``rider_effect_fn=(obj, state) -> list[Event]`` to add a
#     "When you cycle this card, ..." trigger.
#
# These helpers are thin re-exports of the engine module so card scripts
# don't have to import from src.engine directly.
# =============================================================================

from src.engine.cycling import (
    make_cycling_ability,
    make_cycling_setup,
)


__all_cycling__ = [
    "make_cycling_ability",
    "make_cycling_setup",
]


# =============================================================================
# Adventure
# =============================================================================
#
# A card with Adventure has two halves separated by ``// Adventure —``.
# The "main" half is a creature/permanent, the Adventure half is an
# instant/sorcery. Casting the Adventure half exiles the card.
#
# v1 implementation:
#   - The Adventure side is registered as a hand-zone activated ability whose
#     cost is "{adventure_mana}, Exile this card" — the cost parser
#     recognises "Exile this card" and the activated framework emits an
#     EXILE event for self.
#   - The effect_fn returns the events of the Adventure spell's effect.
#   - The activated ability is flagged ``is_adventure=True`` so paying the
#     ``exile_self`` cost also sets ``obj.state.adventure_exile = True``.
#     The cast subsystem (priority.get_legal_actions / _handle_cast_spell_sync)
#     surfaces a CAST_SPELL action for cards in exile carrying that flag, and
#     casting it pays the printed mana cost and resolves the main half. The
#     flag is cleared as the card moves from exile to the stack so it can't
#     be cast a second time from exile.
# =============================================================================


def make_adventure_setup(
    adventure_cost: str,
    effect_fn: Callable[["GameObject", "GameState", list], list[Event]],
    *,
    description: str = "",
    targets_required: int = 0,
    target_kind: str = "any",
):
    """Return a ``setup_in_hand`` callable that registers the Adventure
    half of a split card as a hand-zone activated ability.

    ``adventure_cost`` is the mana portion of the Adventure spell's cost
    ("{1}{R}", etc.). The "Exile this card" portion is added automatically.

    ``effect_fn(obj, state, targets) -> list[Event]`` returns the events
    the Adventure spell produces. Targets are pre-selected via the standard
    targeting flow before the effect_fn fires.
    """
    from src.engine.activated import register_activated_ability

    cost_text = f"{adventure_cost}, Exile this card"

    def _setup(obj: "GameObject", state: "GameState") -> list[Interceptor]:
        register_activated_ability(
            obj,
            cost=cost_text,
            effect_fn=effect_fn,
            description=description or f"Adventure ({adventure_cost})",
            sorcery_speed=False,
            targets_required=targets_required,
            target_kind=target_kind,
            is_adventure=True,
        )
        return []

    return _setup


__all_adventure__ = [
    "make_adventure_setup",
    "make_plot_setup",
]


def make_plot_setup(plot_cost: str, *, description: str = ""):
    """Return a ``setup_in_hand`` callable that registers Plot as a hand-zone
    activated ability.

    OTJ Plot mechanic (CR 702.166):

        Plot {cost} (You may pay {cost} and exile this card from your hand.
        Cast it as a sorcery on a later turn without paying its mana cost.
        Plot only as a sorcery.)

    The activated ability's cost is ``{plot_cost}, Exile this card`` and it
    is restricted to sorcery speed. Paying the cost sets the source object's
    ``state.plotted_turn`` to the current turn number (handled in
    ``pay_activation_cost``); this makes the card eligible to be cast from
    exile via ``ability_id="exile:plot"`` on any subsequent turn during a
    sorcery window.

    The ability's effect_fn is a no-op (Plot has no resolution effect — the
    "value" is the deferred free cast, not the cost-payment). The
    ``PLOT_PAID`` and ``PLOT_BECOMES_PLOTTED`` events are emitted as part
    of cost payment so "When this card becomes plotted" triggers fire.

    Args:
        plot_cost: mana portion of the Plot cost, e.g. ``"{1}{W}"``,
            ``"{R}"``, ``"{4}{U}"``.
        description: optional UI string. Defaults to ``"Plot ({cost})"``.

    Returns:
        A setup_in_hand callable suitable for ``CardDefinition.setup_in_hand``.
    """
    from src.engine.activated import register_activated_ability

    cost_text = f"{plot_cost}, Exile this card"

    def _plot_effect_fn(obj: "GameObject", state: "GameState", targets: list) -> list[Event]:
        # Plot has no resolvable effect — the ability is purely a cost-step.
        # Returning [] here means the activated-ability stack item resolves
        # to nothing (mana was already paid, card already exiled, plotted_turn
        # already set during ``pay_activation_cost``).
        return []

    def _setup(obj: "GameObject", state: "GameState") -> list[Interceptor]:
        register_activated_ability(
            obj,
            cost=cost_text,
            effect_fn=_plot_effect_fn,
            description=description or f"Plot ({plot_cost})",
            sorcery_speed=True,
            is_plot=True,
        )
        return []

    return _setup


# =============================================================================
# Sweep helpers: count_* primitives for dynamic P/T scaling
# =============================================================================
#
# These return the *count* of a particular thing in state — used inside the
# ``mod_fn`` of make_dynamic_pt_boost / make_attached_dynamic_pt_boost to
# express "+X/+Y for each <thing> you control".
# =============================================================================


def count_permanents_with_subtype(controller: str, subtype: str, state: GameState) -> int:
    bf = state.zones.get('battlefield')
    if not bf:
        return 0
    n = 0
    for obj_id in bf.objects:
        obj = state.objects.get(obj_id)
        if obj and obj.controller == controller and subtype in obj.characteristics.subtypes:
            n += 1
    return n


def count_permanents_of_type(controller: str, card_type, state: GameState) -> int:
    bf = state.zones.get('battlefield')
    if not bf:
        return 0
    n = 0
    for obj_id in bf.objects:
        obj = state.objects.get(obj_id)
        if obj and obj.controller == controller and card_type in obj.characteristics.types:
            n += 1
    return n


def count_cards_in_graveyard(controller: str, state: GameState,
                             type_filter=None) -> int:
    gy = state.zones.get(f'graveyard_{controller}')
    if not gy:
        return 0
    if type_filter is None:
        return len(gy.objects)
    n = 0
    for cid in gy.objects:
        obj = state.objects.get(cid)
        if obj and type_filter in obj.characteristics.types:
            n += 1
    return n


def count_cards_in_hand(controller: str, state: GameState) -> int:
    hand = state.zones.get(f'hand_{controller}')
    return len(hand.objects) if hand else 0


def count_attachments(target: GameObject, kind_filter=None) -> int:
    """Count Auras / Equipment attached to ``target``.

    ``kind_filter`` is an optional callable ``(obj) -> bool``.
    """
    if not target.state.attachments:
        return 0
    if kind_filter is None:
        return len(target.state.attachments)
    # Need state for resolution; but caller can iterate the IDs themselves.
    return len(target.state.attachments)


# =============================================================================
# Attached dynamic P/T (Equipment / Aura with "+X/+Y for each ...")
# =============================================================================


def make_attached_dynamic_pt_boost(
    source_obj: GameObject,
    mod_fn: Callable[[GameObject, GameObject, GameState], tuple[int, int]],
) -> list[Interceptor]:
    """Same as make_dynamic_pt_boost but the affects_filter is the standard
    "object currently attached to this Equipment / Aura" check.
    """
    source_id = source_obj.id

    def _attached_filter(target: GameObject, state: GameState) -> bool:
        source = state.objects.get(source_id)
        if not source:
            return False
        return source.state.attached_to == target.id

    return make_dynamic_pt_boost(source_obj, mod_fn, _attached_filter)


# =============================================================================
# Phase 5D: Rooms / Doors (Duskmourn)
# =============================================================================
#
# A Room is an enchantment with two halves separated by ``//``. Each half is
# a "door" with its own name, mana cost, and effect.
# Pragmatic implementation: Door 1 unlocks on ETB. Door 2 has a sorcery-speed
# activated ability `{door2_cost}: Unlock`. Each door's "unlock effect" is
# emitted by an interceptor that listens for UNLOCK_DOOR events on this Room.
# =============================================================================


def is_door_unlocked(obj: GameObject, door_name: str) -> bool:
    """Helper: true iff the given door has been unlocked on this Room."""
    doors = getattr(obj.state, "unlocked_doors", None)
    if not isinstance(doors, list):
        return False
    return door_name in doors


def make_room_setup(
    *,
    door1_name: str,
    door1_unlock_effect: Optional[Callable[[GameObject, GameState], list[Event]]] = None,
    door2_name: str,
    door2_cost: str,
    door2_unlock_effect: Optional[Callable[[GameObject, GameState], list[Event]]] = None,
    extra_setup: Optional[Callable[[GameObject, GameState], list[Interceptor]]] = None,
):
    """Return a setup_interceptors callable for a Room enchantment.

    On ETB the setup:
      1. Initializes ``obj.state.unlocked_doors = []``.
      2. Fires an UNLOCK_DOOR event for ``door1_name`` (Door 1 enters
         unlocked by default — cast-time door selection is engine gap).
      3. Registers an UNLOCK_DOOR REACT interceptor that emits the door's
         unlock effect events whenever the matching door is unlocked.
      4. Registers a sorcery-speed activated ability for door2_cost that
         emits UNLOCK_DOOR for door2.
      5. Calls ``extra_setup`` for any extra interceptors (continuous
         statics, attack triggers, etc. — the second-half "passive" parts
         that aren't gated on unlock).

    The unlock-effect callables receive (room_obj, state) and return Events.
    """
    from src.engine.activated import register_activated_ability

    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        # Initialise tracking.
        if not isinstance(getattr(obj.state, "unlocked_doors", None), list):
            obj.state.unlocked_doors = []

        interceptors: list[Interceptor] = []

        # UNLOCK_DOOR REACT — emits the door-specific unlock effect events.
        def _unlock_filter(event: Event, st: GameState) -> bool:
            if event.type != EventType.UNLOCK_DOOR:
                return False
            return event.payload.get("object_id") == obj.id

        def _unlock_handler(event: Event, st: GameState) -> InterceptorResult:
            door_name = event.payload.get("door_name")
            current = st.objects.get(obj.id)
            if current is None:
                return InterceptorResult(action=InterceptorAction.PASS)
            new_events: list[Event] = []
            if door_name == door1_name and door1_unlock_effect is not None:
                new_events.extend(door1_unlock_effect(current, st) or [])
            elif door_name == door2_name and door2_unlock_effect is not None:
                new_events.extend(door2_unlock_effect(current, st) or [])
            if not new_events:
                return InterceptorResult(action=InterceptorAction.PASS)
            return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

        def _unlock_effect_fn(event: Event, st: GameState) -> list[Event]:
            door_name = event.payload.get("door_name")
            current = st.objects.get(obj.id)
            if current is None:
                return []
            new_events: list[Event] = []
            if door_name == door1_name and door1_unlock_effect is not None:
                new_events.extend(door1_unlock_effect(current, st) or [])
            elif door_name == door2_name and door2_unlock_effect is not None:
                new_events.extend(door2_unlock_effect(current, st) or [])
            return new_events

        unlock_int = Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_unlock_filter,
            handler=_unlock_handler,
            duration='while_on_battlefield',
        )
        _mark_triggered_ability(unlock_int, _unlock_effect_fn, description="Door unlock trigger")
        interceptors.append(unlock_int)

        # Activated ability: pay door2_cost to unlock door 2.
        def _door2_effect(o: GameObject, st: GameState, targets) -> list[Event]:
            return [Event(
                type=EventType.UNLOCK_DOOR,
                payload={"object_id": o.id, "door_name": door2_name},
                source=o.id,
                controller=o.controller,
            )]
        register_activated_ability(
            obj,
            cost=door2_cost,
            effect_fn=_door2_effect,
            description=f"Unlock {door2_name}",
            sorcery_speed=True,
            once_per_turn=False,
        )

        # ETB trigger: unlock Door 1.
        def _etb_filter(event: Event, st: GameState) -> bool:
            if event.type != EventType.ZONE_CHANGE:
                return False
            return (
                event.payload.get("object_id") == obj.id
                and event.payload.get("to_zone_type") == ZoneType.BATTLEFIELD
            )

        _fired_etb = {"done": False}
        def _etb_handler(event: Event, st: GameState) -> InterceptorResult:
            if _fired_etb["done"]:
                return InterceptorResult(action=InterceptorAction.PASS)
            _fired_etb["done"] = True
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.UNLOCK_DOOR,
                    payload={"object_id": obj.id, "door_name": door1_name},
                    source=obj.id,
                    controller=obj.controller,
                )],
            )

        def _etb_effect_fn(event: Event, st: GameState) -> list[Event]:
            if _fired_etb["done"]:
                return []
            _fired_etb["done"] = True
            return [Event(
                type=EventType.UNLOCK_DOOR,
                payload={"object_id": obj.id, "door_name": door1_name},
                source=obj.id,
                controller=obj.controller,
            )]

        etb_int = Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_etb_filter,
            handler=_etb_handler,
            duration='forever',
        )
        _mark_triggered_ability(etb_int, _etb_effect_fn, description="Room ETB unlock trigger")
        interceptors.append(etb_int)

        if extra_setup is not None:
            extra = extra_setup(obj, state)
            if extra:
                interceptors.extend(extra)

        return interceptors

    return _setup


# =============================================================================
# Phase 5: Collect Evidence (Murders at Karlov Manor)
# =============================================================================
#
# "Collect evidence N" is a cost: exile any number of cards from your
# graveyard with total mana value at least N. Used as both a cost on
# activated abilities and as a triggered-ability gate.
# =============================================================================


def collect_evidence(player_id: str, n: int, state: GameState,
                     source_id: str = "") -> Optional[list[Event]]:
    """Greedy collect-evidence: exile graveyard cards (highest MV first) until
    total MV ≥ ``n``. Returns the EXILE events to enqueue, or ``None`` if the
    player can't meet the requirement.

    The pipeline's EXILE handler moves the cards to exile; we do not need to
    mutate state here.
    """
    from src.engine.types import CardType
    grave = state.zones.get(f"graveyard_{player_id}")
    if not grave:
        return None

    candidates: list[tuple[int, str]] = []
    for cid in grave.objects:
        obj = state.objects.get(cid)
        if obj is None or obj.card_def is None:
            continue
        # Use mana_cost CMC if available; lands and 0-cost cards count as 0.
        try:
            mv = obj.card_def.characteristics.mana_cost_value()
        except AttributeError:
            mv = _approx_mana_value(obj.card_def.mana_cost or "")
        candidates.append((mv, cid))

    candidates.sort(key=lambda x: -x[0])
    total = 0
    chosen: list[str] = []
    for mv, cid in candidates:
        if total >= n:
            break
        chosen.append(cid)
        total += mv
    if total < n:
        return None

    return [
        Event(
            type=EventType.EXILE,
            payload={'object_id': cid},
            source=source_id or cid,
            controller=player_id,
        )
        for cid in chosen
    ]


def _approx_mana_value(mana_cost: str) -> int:
    """Approximate the mana value of a cost string. Treats X as 0."""
    if not mana_cost:
        return 0
    import re as _re
    total = 0
    for sym in _re.findall(r'\{([^}]+)\}', mana_cost):
        s = sym.upper()
        if s.isdigit():
            total += int(s)
        elif s in ('W', 'U', 'B', 'R', 'G', 'C', 'S'):
            total += 1
        elif s == 'X' or s == 'Y' or s == 'Z':
            total += 0
        elif '/' in s:
            # Hybrid mana — counts as 1
            total += 1
        elif 'P' in s:
            total += 1
    return total


# =============================================================================
# Phase 5: Bargain (Wilds of Eldraine)
# =============================================================================
#
# "Bargain (You may sacrifice an artifact, enchantment, or token as you cast
#  this spell.)"
# Cards with Bargain have a base effect plus an "If this spell was bargained,
# ..." bonus. Resolve callbacks consult was_bargained() to decide.
#
# The cast subsystem must set obj.state.was_bargained = True on the spell
# card object before resolve when the bargain cost is paid. (For now this
# isn't auto-prompted by the cast UI — the flag can be set via test fixtures
# or a future cast-option extension.)
# =============================================================================


def was_bargained(state: GameState, card_name: str) -> bool:
    """Look up the spell currently being resolved by name and return its
    was_bargained flag.

    Use inside a card's ``resolve=`` callback to branch on the bargain
    bonus path.
    """
    stack_zone = state.zones.get('stack')
    if not stack_zone:
        return False
    for cid in stack_zone.objects:
        obj = state.objects.get(cid)
        if obj and obj.name == card_name:
            return bool(getattr(obj.state, 'was_bargained', False))
    return False


# =============================================================================
# Modal multi-choice helper
# =============================================================================
#
# Many spells use the "Choose one — / Choose two — / Choose one or more —"
# pattern with several bullet-pointed effects. The engine's
# ``create_modal_choice`` PendingChoice already handles the player UI; this
# helper bundles the resolve= boilerplate so card scripts don't need to
# write 30+ lines per spell.
#
# Two styles are supported:
#
#   1. **Legacy tuple form** — ``(text, effect_fn)`` where ``effect_fn`` has
#      signature ``(state, caster_id, spell_id)`` and returns events. Modes
#      that need a target chain a follow-up ``create_target_choice`` inside
#      their own ``effect_fn``.
#
#   2. **ModeSpec form** (Phase 5b) — declares an optional ``target_requirement``
#      on each mode. After mode selection, the helper chains one PendingChoice
#      per chosen-mode-with-targets, accumulates the picks, and dispatches each
#      ``effect_fn(state, caster_id, spell_id, targets=...)`` with the targets
#      list for that mode.
#
# Usage (legacy)::
#
#     from src.cards.interceptor_helpers import make_modal_resolve
#
#     def mode0_effect(state, caster_id, spell_id):
#         return [Event(type=EventType.LIFE_CHANGE,
#                       payload={'player': caster_id, 'amount': 3},
#                       source=spell_id, controller=caster_id)]
#
#     SOMETHING = make_sorcery(
#         ...,
#         text="Choose one or more —\n• Gain 3 life.\n• Draw a card.",
#         resolve=make_modal_resolve(
#             "Something",
#             modes=[
#                 ("Gain 3 life", mode0_effect),
#                 ("Draw a card", mode1_effect),
#             ],
#             min_modes=1, max_modes=2,
#         ),
#     )
#
# Usage (ModeSpec with per-mode target requirements)::
#
#     from src.cards.interceptor_helpers import make_modal_resolve, ModeSpec
#     from src.engine.targeting import target_creature, target_player
#
#     def bolt_mode(state, caster_id, spell_id, targets=None):
#         tid = targets[0].id if targets else None
#         return [Event(type=EventType.DAMAGE,
#                       payload={'target': tid, 'amount': 3, 'source': spell_id},
#                       source=spell_id, controller=caster_id)]
#
#     def life_mode(state, caster_id, spell_id, targets=None):
#         return [Event(type=EventType.LIFE_CHANGE,
#                       payload={'player': caster_id, 'amount': 3},
#                       source=spell_id, controller=caster_id)]
#
#     SOMETHING = make_sorcery(
#         ...,
#         resolve=make_modal_resolve(
#             "Something",
#             modes=[
#                 ModeSpec("Deal 3 damage", bolt_mode,
#                          target_requirement=target_creature()),
#                 ModeSpec("Gain 3 life", life_mode),  # no target
#             ],
#             min_modes=1, max_modes=1,
#         ),
#     )
# =============================================================================

from dataclasses import dataclass, field


@dataclass
class ModeSpec:
    """One mode of a modal spell.

    Args:
        text: Display label, shown in the mode-selection prompt.
        effect_fn: Resolver for this mode. Signature when
            ``target_requirement`` is ``None``: ``(state, caster_id, spell_id)
            -> list[Event]``. When ``target_requirement`` is set (single or
            list): ``(state, caster_id, spell_id, targets=list[Target]) ->
            list[Event]``. With multiple requirements, ``targets`` is the
            flat list of one ``Target`` per requirement (in declaration order).
        target_requirement: Optional cast-resolution target spec. May be a
            single ``TargetRequirement`` or a list of them. If set, after
            mode selection the resolver chains one target choice per
            requirement and passes the picked targets to ``effect_fn`` as a
            ``targets=`` kwarg (flat list). If ``None``, ``effect_fn`` is
            called with the 3-arg legacy signature.
        prompt: Optional override for the target choice prompt. Defaults to
            each requirement's ``label``.
    """
    text: str
    effect_fn: Callable[..., list[Event]]
    target_requirement: Optional[Any] = None  # TargetRequirement or list; Any to avoid circular import
    prompt: Optional[str] = None


def _coerce_modes(modes) -> list[ModeSpec]:
    """Accept legacy ``(text, effect_fn)`` tuples and normalize to ``ModeSpec``."""
    out: list[ModeSpec] = []
    for m in modes:
        if isinstance(m, ModeSpec):
            out.append(m)
        elif isinstance(m, tuple) and len(m) == 2:
            out.append(ModeSpec(text=m[0], effect_fn=m[1]))
        else:
            raise TypeError(
                f"make_modal_resolve: each mode must be a ModeSpec or "
                f"(text, effect_fn) tuple, got {type(m).__name__}: {m!r}"
            )
    return out


def make_modal_resolve(
    card_name: str,
    modes,
    *,
    min_modes: int = 1,
    max_modes: int = 1,
    prompt: Optional[str] = None,
):
    """Build a ``resolve=`` callback for a modal spell.

    ``modes`` is a list of ``ModeSpec`` or ``(text, effect_fn)`` tuples
    (legacy). See module docstring for usage examples.
    """
    mode_specs = _coerce_modes(modes)
    if min_modes < 0 or max_modes < min_modes or max_modes > len(mode_specs):
        raise ValueError(
            f"make_modal_resolve: bad min/max ({min_modes}/{max_modes}) for "
            f"{len(mode_specs)} modes"
        )

    def _resolve(targets: list, state: GameState) -> list[Event]:
        # Locate the resolving spell on the stack.
        stack_zone = state.zones.get('stack')
        spell_id = None
        caster_id = None
        spell_obj = None
        if stack_zone:
            for cid in stack_zone.objects:
                obj = state.objects.get(cid)
                if obj and obj.name == card_name:
                    spell_id = obj.id
                    caster_id = obj.controller
                    spell_obj = obj
                    break
        if caster_id is None:
            caster_id = getattr(state, 'active_player', None) or getattr(state, 'priority_player', None)
        if spell_id is None:
            spell_id = f"{card_name.lower().replace(' ', '_')}_spell"
        if caster_id is None:
            return []

        mode_options = [
            {"index": i, "text": ms.text}
            for i, ms in enumerate(mode_specs)
        ]
        choice_prompt = prompt or f"{card_name} — choose " + (
            "one" if min_modes == max_modes == 1 else
            f"{min_modes}-{max_modes}"
        ) + ":"

        choice = create_modal_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            modes=mode_options,
            min_modes=min_modes,
            max_modes=max_modes,
            prompt=choice_prompt,
        )

        def _mode_reqs(ms: ModeSpec) -> list:
            """Return the list of TargetRequirements for a mode (0, 1, or N)."""
            if ms.target_requirement is None:
                return []
            if isinstance(ms.target_requirement, list):
                return list(ms.target_requirement)
            return [ms.target_requirement]

        def _dispatch_modes(
            st: GameState,
            chosen_idx_list: list[int],
            per_mode_targets: dict[int, list],
        ) -> list[Event]:
            """Run each chosen mode's effect_fn, returning aggregated events.

            MTG rule: if a chosen mode requires targets and none were legal,
            that mode's effect simply doesn't happen (the mode "does nothing").
            We detect this via an empty targets list in ``per_mode_targets``
            for a mode whose ``target_requirement`` has ``min_targets() >= 1``.
            """
            events: list[Event] = []
            for idx in chosen_idx_list:
                if not (0 <= idx < len(mode_specs)):
                    continue
                ms = mode_specs[idx]
                reqs = _mode_reqs(ms)
                try:
                    if reqs:
                        picked = per_mode_targets.get(idx, [])
                        # If any required-target slot is empty, the mode does
                        # nothing (MTG: illegally chosen mode).
                        if any(
                            (not picked[i] if i < len(picked) else True)
                            and reqs[i].min_targets() >= 1
                            for i in range(len(reqs))
                        ):
                            continue
                        new_evs = ms.effect_fn(
                            st, caster_id, spell_id,
                            targets=picked,
                        ) or []
                    else:
                        new_evs = ms.effect_fn(st, caster_id, spell_id) or []
                except Exception:
                    new_evs = []
                events.extend(new_evs)
            return events

        def _chain_target_picks(
            st: GameState,
            chosen_with_targets: list[int],
            chosen_idx_list: list[int],
            mode_cursor: int,
            req_cursor: int,
            per_mode_targets: dict[int, list],
        ) -> list[Event]:
            """Chain one PendingChoice per chosen mode/requirement pair.

            Base case (``mode_cursor == len(chosen_with_targets)``): all
            targets collected; dispatch each chosen mode's effect_fn.
            """
            if mode_cursor >= len(chosen_with_targets):
                return _dispatch_modes(st, chosen_idx_list, per_mode_targets)

            mode_idx = chosen_with_targets[mode_cursor]
            ms = mode_specs[mode_idx]
            reqs = _mode_reqs(ms)

            # Advance past empty req lists or past last req.
            if req_cursor >= len(reqs):
                return _chain_target_picks(
                    st, chosen_with_targets, chosen_idx_list,
                    mode_cursor + 1, 0, per_mode_targets,
                )

            req = reqs[req_cursor]

            # Re-evaluate legal targets at resolution time.
            from src.engine.targeting import TargetingSystem, Target
            legal_ids: list[str] = []
            if spell_obj is not None:
                try:
                    ts = TargetingSystem(st)
                    legal_ids = ts.get_legal_targets(req, spell_obj, caster_id)
                except Exception:
                    legal_ids = []
            else:
                for oid, obj in st.objects.items():
                    try:
                        if req.filter.matches(obj, st, None):
                            legal_ids.append(oid)
                    except Exception:
                        pass
                if getattr(req.filter, 'types', None) is None or getattr(
                    req.filter, 'includes_players', False
                ):
                    for pid in st.players.keys():
                        if req.filter.controller == 'you' and pid != caster_id:
                            continue
                        if req.filter.controller == 'opponent' and pid == caster_id:
                            continue
                        legal_ids.append(pid)

            # No legal targets — this whole mode does nothing.
            if not legal_ids:
                per_mode_targets[mode_idx] = []
                return _chain_target_picks(
                    st, chosen_with_targets, chosen_idx_list,
                    mode_cursor + 1, 0, per_mode_targets,
                )

            options = []
            for tid in legal_ids:
                obj = st.objects.get(tid)
                if obj is not None:
                    label = getattr(obj, "name", None) or tid
                else:
                    player = st.players.get(tid)
                    label = getattr(player, "name", None) or f"Player {tid[:8]}"
                options.append({"id": tid, "label": label})

            def _target_handler(_ch, selected, st2: GameState) -> list[Event]:
                picked_ids = [
                    s.get("id") if isinstance(s, dict) else s for s in (selected or [])
                ]
                picks: list = []
                for tid in picked_ids:
                    is_player = tid in st2.players
                    picks.append(Target(id=str(tid), is_player=is_player))
                # Append to the per-mode bucket. The bucket is a flat list of
                # the resolved targets across all the mode's requirements.
                bucket = per_mode_targets.setdefault(mode_idx, [])
                # Single-target requirements: take the first pick (most common).
                # Multi-target (count > 1 or up_to N): bucket gets a Target per pick.
                # We store one Target per pick (the dispatcher reads them in order).
                if picks:
                    bucket.append(picks[0])
                else:
                    bucket.append(None)
                return _chain_target_picks(
                    st2, chosen_with_targets, chosen_idx_list,
                    mode_cursor, req_cursor + 1, per_mode_targets,
                )

            from src.engine.pending_choice_helpers import create_choice_and_resolve
            max_t = req.max_targets()
            mode_prompt = ms.prompt or req.label or f"{card_name} — choose a target"
            return create_choice_and_resolve(
                st,
                choice_type="target",
                player_id=caster_id,
                prompt=mode_prompt,
                options=options,
                source_id=spell_id,
                min_choices=req.min_targets(),
                max_choices=int(max_t) if max_t != float('inf') else len(options),
                handler=_target_handler,
                heuristic_pick=[legal_ids[0]],
            )

        def _handler(ch, selected_modes, st: GameState) -> list[Event]:
            # Normalize chosen mode indices.
            chosen_idx_list: list[int] = []
            for mi in (selected_modes or []):
                try:
                    chosen_idx_list.append(int(mi))
                except (TypeError, ValueError):
                    continue

            # Which chosen modes need a target?
            chosen_with_targets = [
                i for i in chosen_idx_list
                if 0 <= i < len(mode_specs) and mode_specs[i].target_requirement is not None
            ]

            # No targeted modes — fast path matches legacy behavior.
            if not chosen_with_targets:
                return _dispatch_modes(st, chosen_idx_list, {})

            return _chain_target_picks(
                st, chosen_with_targets, chosen_idx_list, 0, 0, {}
            )

        choice.choice_type = "modal_with_callback"
        choice.callback_data['handler'] = _handler
        return []

    return _resolve


__all_modal__ = [
    "make_modal_resolve",
    "ModeSpec",
]


# =============================================================================
# DIVIDE-DAMAGE RESOLVE HELPER (Phase 5b)
# =============================================================================
#
# "Deal N damage divided as you choose among any number of target
# creatures and/or players." MTG ships this template on burn spells like
# Twin Bolt (2 damage, 1-2 targets), Arc Lightning (3 damage, 1-3 targets),
# and X-cost spells like Comet Storm, Ureni, Chandra (-4).
#
# When the engine sees a CardDefinition declare a ``TargetRequirement``
# with ``divide_amount=N`` (see ``src/engine/targeting.py:198``), the cast
# pipeline emits a ``divide_allocation`` PendingChoice at cast time. The
# choice carries ``options=[{id, label, ...}]`` for each legal target and
# ``callback_data['total_amount']=N``; the player (or AI) submits a list
# of ``{target_id, amount}`` dicts that must sum to N.
#
# The handler is then called with the normalized allocation dict, and we
# convert it into one DAMAGE event per target. ``action.targets`` for the
# resolving spell is set to a single list[Target] with each Target's
# ``divided_amount`` set, so the spell's ``resolve=`` callback can simply
# unpack ``targets[0]``.
#
# This helper bundles the resolve= boilerplate: it inspects the targets
# list (which carries ``divided_amount`` per Target), and emits one DAMAGE
# event per non-zero allocation.
#
# Usage::
#
#     from src.cards.interceptor_helpers import make_divide_damage_resolve
#     from src.engine.targeting import TargetRequirement, any_target_filter
#
#     TWIN_BOLT = make_instant(
#         name="Twin Bolt",
#         mana_cost="{1}{R}",
#         colors={Color.RED},
#         text="Twin Bolt deals 2 damage divided as you choose among one "
#              "or two targets.",
#         resolve=make_divide_damage_resolve("Twin Bolt", total_damage=2,
#                                             target_filter=any_target_filter(),
#                                             min_targets=1, max_targets=2),
#         target_requirements=[
#             TargetRequirement(
#                 filter=any_target_filter(),
#                 count=2,
#                 count_type='up_to',
#                 label="any target",
#                 divide_amount=2,
#             ),
#         ],
#     )
# =============================================================================


def make_divide_damage_resolve(
    card_name: str,
    *,
    total_damage,
    target_filter=None,  # accepted for symmetry / docs; engine reads it from target_requirements
    min_targets: int = 1,
    max_targets=float('inf'),
):
    """Build a ``resolve=`` callback for 'deal N damage divided' spells.

    At cast time the engine emits a ``divide_allocation`` PendingChoice
    (see priority._emit_cast_target_choice_step). The handler stuffs each
    target's allocation into ``Target.divided_amount`` and re-enters the
    cast with ``action.targets = [[Target(id, divided_amount=...), ...]]``.

    At resolve time we read those Target objects and emit one DAMAGE event
    per allocation, with the printed source set to the resolving spell on
    the stack.

    Args:
        card_name: Card name. Used to locate the resolving spell on the
            stack so the DAMAGE event carries the correct ``source``.
        total_damage: Either ``int`` (fixed amount like Twin Bolt's 2) or
            a callable ``(state, caster_id) -> int`` for X-cost spells
            (Comet Storm: X+1; Ureni: number of lands you control).
            Stored on the resolver and used by the cast-time prompt to
            compute the prompt-time allocation budget. The engine reads
            this via ``divide_amount`` on the TargetRequirement; if you
            want a callable budget, set
            ``TargetRequirement.divide_amount = callable`` too.
        target_filter: TargetFilter (re-stated for docs / symmetry). The
            engine reads the actual filter from ``card.target_requirements``.
            Pass it here so the helper docstring matches the card text;
            it's not used directly by the resolver.
        min_targets: Minimum target count (default 1). Currently unused at
            resolve time — enforcement happens via the TargetRequirement.
        max_targets: Maximum target count (default unlimited). Same as
            min_targets.

    Returns:
        A ``resolve(targets, state) -> list[Event]`` callable suitable for
        ``CardDefinition.resolve``.
    """
    def _resolve(targets: list, state: GameState) -> list[Event]:
        # Locate the resolving spell on the stack to attach ``source``.
        stack_zone = state.zones.get('stack')
        source_id = None
        caster_id = None
        if stack_zone:
            for cid in stack_zone.objects:
                obj = state.objects.get(cid)
                if obj and obj.name == card_name:
                    source_id = obj.id
                    caster_id = obj.controller
                    break

        # ``targets`` is the engine's standard list[list[Target]] shape.
        # For divide-damage spells, ``targets[0]`` is a flat list of
        # Targets, each carrying ``divided_amount`` set by the cast-time
        # allocation handler.
        if not targets:
            return []
        first_group = targets[0] if targets else []
        if not first_group:
            return []

        events: list[Event] = []
        # Fallback budget — used only if every Target has no
        # ``divided_amount`` set (defensive: shouldn't happen via the
        # standard cast path, but covers manual resolve calls in tests).
        if callable(total_damage):
            try:
                fallback_budget = int(total_damage(state, caster_id) or 0)
            except Exception:
                fallback_budget = 0
        else:
            fallback_budget = int(total_damage or 0)

        # Sum the per-target allocations actually present.
        explicit_total = sum(
            int(getattr(t, 'divided_amount', None) or 0)
            for t in first_group
        )

        # If no explicit allocations were set, fall back to even split.
        if explicit_total == 0 and fallback_budget > 0 and first_group:
            per = max(1, fallback_budget // len(first_group))
            remaining = fallback_budget
            for t in first_group:
                amount = min(per, remaining)
                if amount <= 0:
                    break
                tid = getattr(t, 'id', None) or t
                is_player = getattr(t, 'is_player', None)
                if is_player is None:
                    is_player = tid in state.players
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={
                        'target': tid,
                        'amount': amount,
                        'source': source_id,
                        'is_combat': False,
                        'is_player': is_player,
                    },
                    source=source_id,
                ))
                remaining -= amount
            # If we still have leftover (integer-division remainder), pile
            # it on the first target.
            if remaining > 0 and events:
                events[0].payload['amount'] += remaining
            return events

        # Standard path: each Target's divided_amount is honored.
        for t in first_group:
            amount = int(getattr(t, 'divided_amount', None) or 0)
            if amount <= 0:
                continue
            tid = getattr(t, 'id', None) or t
            is_player = getattr(t, 'is_player', None)
            if is_player is None:
                is_player = tid in state.players
            events.append(Event(
                type=EventType.DAMAGE,
                payload={
                    'target': tid,
                    'amount': amount,
                    'source': source_id,
                    'is_combat': False,
                    'is_player': is_player,
                },
                source=source_id,
            ))
        return events

    return _resolve


__all_divide_damage__ = [
    "make_divide_damage_resolve",
]


# =============================================================================
# COPY STACK-ITEM HELPER (Virtue of Knowledge / Peter Parker's Camera / Gogo)
# =============================================================================

def make_copy_ability_event(
    stack_item_id: str,
    controller: str,
    source_id: str,
    *,
    new_targets: Optional[list] = None,
) -> Event:
    """Build a ``COPY_STACK_ITEM`` event.

    Resolves to a copy of the targeted stack item being pushed onto the stack
    (the engine handler clones via ``StackManager.push_copy``). The copy keeps
    the original's ``resolve_fn`` and ``source_id`` so it produces the same
    effect; if ``new_targets`` is supplied, the copy resolves against those
    instead of the original's chosen targets.

    Use this from a card's resolve callback or from an effect_fn that already
    runs after the player has chosen which stack item to copy.

    Args:
        stack_item_id: id of the StackItem to copy (must be currently on the
            stack — copies are pushed immediately).
        controller: player who's doing the copying (used for event.controller).
        source_id: object id of the card causing the copy (Virtue of Knowledge,
            Peter Parker's Camera, Gogo, etc.). Used as event.source.
        new_targets: optional new targets in the engine's standard
            ``list[list[Target]]`` shape. Pass ``None`` to keep the original
            targets.
    """
    payload: dict = {'stack_item_id': stack_item_id}
    if new_targets is not None:
        payload['new_targets'] = new_targets
    return Event(
        type=EventType.COPY_STACK_ITEM,
        payload=payload,
        source=source_id,
        controller=controller,
    )


# =============================================================================
# Per-turn destruction tracker (for "if X was destroyed this turn" predicates)
# =============================================================================
#
# Used by Vader-style reassembly abilities and any "when target died this turn"
# checks. The tracker is installed lazily the first time `was_destroyed_this_turn`
# is queried — installing once per game keeps it cheap and safe to call from card
# scripts without each card worrying about lifecycle.

_DESTRUCTION_TRACKER_FLAG = "_destruction_tracker_installed"


def _ensure_destruction_tracker(state: GameState) -> None:
    """Install the system-level destruction tracker once per game state."""
    if getattr(state, _DESTRUCTION_TRACKER_FLAG, False):
        return
    setattr(state, _DESTRUCTION_TRACKER_FLAG, True)

    def record_destruction(event: Event, _st: GameState) -> InterceptorResult:
        oid = event.payload.get("object_id")
        if oid:
            destroyed: set = state.turn_data.setdefault("destroyed_this_turn", set())
            destroyed.add(oid)
        return InterceptorResult(action=InterceptorAction.PASS)

    def reset_on_turn_start(_event: Event, _st: GameState) -> InterceptorResult:
        state.turn_data["destroyed_this_turn"] = set()
        return InterceptorResult(action=InterceptorAction.PASS)

    record_int = Interceptor(
        id=new_id(),
        source="SYSTEM_DESTRUCTION_TRACKER",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=lambda e, _s: e.type == EventType.OBJECT_DESTROYED,
        handler=record_destruction,
        duration="forever",
    )
    reset_int = Interceptor(
        id=new_id(),
        source="SYSTEM_DESTRUCTION_TRACKER",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=lambda e, _s: e.type == EventType.TURN_START,
        handler=reset_on_turn_start,
        duration="forever",
    )
    state.interceptors[record_int.id] = record_int
    state.interceptors[reset_int.id] = reset_int


def was_destroyed_this_turn(obj_id: str, state: GameState) -> bool:
    """Return True iff `obj_id` was destroyed since the start of the current turn.

    Lazy-installs the per-turn destruction tracker on first call. Cheap idempotent
    install; subsequent calls are O(1) lookups against `state.turn_data`.
    """
    _ensure_destruction_tracker(state)
    destroyed: set = state.turn_data.get("destroyed_this_turn") or set()
    return obj_id in destroyed


# =============================================================================
# DSK Impending mechanic (CR 702.x — alt-cast with time counters)
# =============================================================================
#
# Reference card text:
#     "Impending N—{cost} (If you cast this spell for its impending cost,
#      it enters with N time counters and isn't a creature until the last
#      is removed. At the beginning of your end step, remove a time counter
#      from it.)
#      Whenever this permanent enters or attacks, <effect>."
#
# Three moving pieces:
#   1. Alt-cost cast option. Surfaced in priority.py as the
#      ``hand:impending`` ability_id. The cast site flags the in-flight
#      object via ``mark_impending_cast`` so the ETB-installer below can
#      detect the impending path.
#   2. ETB-time installer. Installed as a REACT interceptor on the source.
#      On ETB it checks ``is_impending_pending`` and, if set, emits
#      COUNTER_ADDED events to put N time counters on the object and
#      clears the pending flag.
#   3. While time counters > 0:
#      a) A QUERY_TYPES interceptor strips CardType.CREATURE from the
#         effective types. The interceptor's filter checks the live
#         counter count so once counters reach 0, the strip stops
#         applying without any teardown.
#      b) An end-step trigger emits COUNTER_REMOVED to take one off.
#
# The "Whenever this enters or attacks" trigger is created separately by
# the card script (via ``make_etb_trigger`` / ``make_attack_trigger``)
# because each card has a unique effect. Triggers fire regardless of
# whether the permanent is currently a creature — they live on the
# battlefield zone, not on creature-type gating.
# =============================================================================

def make_impending_setup(
    *,
    impending_cost: str,
    time_counters: int,
):
    """Return a ``setup_interceptors`` callable that wires the Impending
    bookkeeping for a permanent (time-counter ETB add, type strip while
    counters > 0, end-step decrement).

    Args:
        impending_cost: The mana portion of the impending alt cost,
            e.g. ``"{2}{W}{W}"``. Stored on the object for diagnostics /
            UI; the actual cast-time parsing reads from the card text.
        time_counters: N — number of time counters the permanent enters
            with when cast for impending.

    Usage:

        def my_card_setup(obj, state):
            base = make_impending_setup(
                impending_cost="{2}{W}{W}", time_counters=4,
            )(obj, state)
            # Add the card's enter / attack triggered ability:
            def effect(event, state):
                return [...]
            return base + [
                make_etb_trigger(obj, effect),
                make_attack_trigger(obj, effect),
            ]

    Returns a callable ``(obj, state) -> list[Interceptor]`` suitable for
    direct use as a ``CardDefinition.setup_interceptors`` (in which case
    only the impending bookkeeping is installed) or as the seed for a
    composite setup function (in which case the caller appends their own
    triggers).

    Engine support / limitations:
      * The QUERY_TYPES strip is implemented (the permanent is correctly
        not a creature while time counters > 0). However, downstream
        consumers that read ``obj.characteristics.types`` directly (rather
        than going through ``get_types``) will not see the strip. The
        engine consistently goes through ``get_types`` for creature
        identification (combat, can-attack, can-block, etc.) so this is
        correct for the engine, but custom scripts reading characteristics
        raw may need adjustment.
      * Casting "normally" (printed cost) does not install time counters,
        and the printed creature type stays intact — verified by the
        ETB-installer reading ``is_impending_pending`` only at ETB.
      * Counter decrement fires on the controller's end step, matching
        the printed rules (CR 702.144 / impending reminder text). The
        decrement only happens while time counters > 0.
    """
    # Import locally so the engine package is fully built before the
    # impending module is touched (this file is imported very early).
    from src.engine.impending import (
        is_impending_pending,
        clear_impending_pending,
    )

    n_counters = int(time_counters)
    if n_counters <= 0:
        raise ValueError(
            f"make_impending_setup: time_counters must be >= 1, got {n_counters}"
        )

    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        # Stash the impending cost on the object for diagnostics / UI.
        try:
            setattr(obj, "_impending_cost", impending_cost)
            setattr(obj, "_impending_n", n_counters)
        except Exception:  # pragma: no cover
            pass

        source_id = obj.id

        # ----- 1) ETB-time time-counter installer -------------------------
        # Fires once on the controller's ETB; if the in-flight object was
        # marked impending-pending by the cast pipeline, add the N time
        # counters and clear the marker so a re-ETB (flicker / reanimate)
        # doesn't accidentally re-arm the impending state.
        def etb_filter(event: Event, st: GameState, src: GameObject) -> bool:
            if event.type == EventType.ZONE_CHANGE:
                return (event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD and
                        event.payload.get('object_id') == src.id)
            if event.type == EventType.OBJECT_CREATED:
                return (event.payload.get('object_id') == src.id and
                        event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD)
            return False

        def etb_install_effect(event: Event, st: GameState) -> list[Event]:
            live = st.objects.get(source_id)
            if live is None:
                return []
            if not is_impending_pending(live):
                return []
            # Consume the pending flag so a future flicker / blink doesn't
            # reset the time counters.
            clear_impending_pending(live)
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    'object_id': source_id,
                    'counter_type': 'time',
                    'amount': n_counters,
                },
                source=source_id,
                controller=live.controller,
            )]

        def etb_handler(event: Event, st: GameState) -> InterceptorResult:
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=etb_install_effect(event, st),
            )

        etb_interceptor = Interceptor(
            id=new_id(),
            source=source_id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=lambda e, st: etb_filter(e, st, obj),
            handler=etb_handler,
            duration='while_on_battlefield',
        )
        _mark_triggered_ability(
            etb_interceptor, etb_install_effect,
            description=f"Impending {n_counters} — install time counters on ETB",
        )

        # ----- 2) QUERY_TYPES strip while time counters > 0 ---------------
        # Removes CardType.CREATURE from the effective types of this
        # object whenever it has time counters. Implemented as a TRANSFORM
        # interceptor on QUERY_TYPES (the standard mechanism, used by
        # ``becomes_creature`` etc.).
        def types_filter(event: Event, st: GameState) -> bool:
            if event.type != EventType.QUERY_TYPES:
                return False
            if event.payload.get('object_id') != source_id:
                return False
            live = st.objects.get(source_id)
            if live is None:
                return False
            # Only strip while time counters > 0; once they reach 0 this
            # interceptor turns into a no-op without needing teardown.
            return int(live.state.counters.get('time', 0)) > 0

        def types_handler(event: Event, st: GameState) -> InterceptorResult:
            new_event = event.copy()
            live = st.objects.get(source_id)
            base_types = (
                new_event.payload.get('value')
                or set(live.characteristics.types) if live else set()
            )
            stripped = {t for t in base_types if t != CardType.CREATURE}
            new_event.payload['value'] = stripped
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event,
            )

        types_interceptor = Interceptor(
            id=new_id(),
            source=source_id,
            controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=types_filter,
            handler=types_handler,
            duration='while_on_battlefield',
        )

        # ----- 3) End-step decrement of time counters ---------------------
        def upkeep_decrement_effect(event: Event, st: GameState) -> list[Event]:
            live = st.objects.get(source_id)
            if live is None or live.zone != ZoneType.BATTLEFIELD:
                return []
            current = int(live.state.counters.get('time', 0))
            if current <= 0:
                return []
            return [Event(
                type=EventType.COUNTER_REMOVED,
                payload={
                    'object_id': source_id,
                    'counter_type': 'time',
                    'amount': 1,
                },
                source=source_id,
                controller=live.controller,
            )]

        end_step_interceptor = make_end_step_trigger(
            obj, upkeep_decrement_effect, controller_only=True,
        )

        return [etb_interceptor, types_interceptor, end_step_interceptor]

    return _setup


__all_impending__ = [
    "make_impending_setup",
]
