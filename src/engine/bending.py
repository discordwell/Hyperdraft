"""
Avatar: The Last Airbender (TLA) Bending Subsystem

Bending is a four-element family of triggered abilities and X-cost effects
unique to the TLA set. Each element has a characteristic rider:

- Firebending X     - Whenever this attacks, add X {R} (mana lasts until end of combat)
- Waterbend {X}     - Activated cost; while paying, you may tap artifacts/creatures to help
- Earthbend X       - Target land you control becomes a 0/0 creature with haste, gets X +1/+1 counters
- Airbend           - Exile target nonland permanent; owner may cast it for {2}

This module provides:
- Marker events (`BENDING_*`) emitted whenever a bending action resolves so other
  cards (e.g. Avatar Aang's transform) can observe them.
- Helper factories that build the boilerplate interceptors for each rider.

Many bending effects still rely on existing engine machinery (MANA_ADDED for
firebend, COUNTER_ADDED for earthbend, target-choice/exile for airbend). The
helpers here unify the pattern, emit the marker events, and accept either a
fixed integer or a callable for the dynamic-X case (e.g. "Firebending X, where
X is this creature's power").
"""

from typing import Callable, Optional, Union

from .types import (
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    CardType,
    ZoneType,
    PendingChoice,
    new_id,
)


# Type aliases
# An "amount source" is either a fixed int or a callable taking (obj, state) -> int.
AmountSource = Union[int, Callable[[GameObject, GameState], int]]


def _resolve_amount(amount: AmountSource, obj: GameObject, state: GameState) -> int:
    """Resolve a fixed-or-dynamic amount to a concrete non-negative int."""
    if callable(amount):
        try:
            value = amount(obj, state)
        except Exception:
            value = 0
    else:
        value = int(amount or 0)
    if value < 0:
        return 0
    return int(value)


def _tla_lands_you_control(obj: GameObject, state: GameState) -> list[GameObject]:
    """Return all lands the source's controller owns that are on the battlefield."""
    return [
        o for o in state.objects.values()
        if o.controller == obj.controller
        and o.zone == ZoneType.BATTLEFIELD
        and CardType.LAND in o.characteristics.types
    ]


# === BENDING HELPERS ===

def make_firebend_attack_trigger(
    obj: GameObject,
    x_amount: AmountSource,
) -> Interceptor:
    """Firebending X (Whenever this creature attacks, add X {R}).

    Emits MANA_ADDED({R: X}) plus a BENDING_FIREBEND marker so trackers can
    observe firebend has happened this turn.

    `x_amount` may be a fixed int or a callable `(obj, state) -> int` for
    dynamic-X effects like "X is this creature's power".
    """

    def filter_fn(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.ATTACK_DECLARED
            and event.payload.get('attacker_id') == obj.id
        )

    def handler(event: Event, state: GameState) -> InterceptorResult:
        x = _resolve_amount(x_amount, obj, state)
        if x <= 0:
            return InterceptorResult(action=InterceptorAction.PASS)
        new_events = [
            Event(
                type=EventType.MANA_ADDED,
                payload={'player': obj.controller, 'mana': {'R': x}},
                source=obj.id,
            ),
            Event(
                type=EventType.BENDING_FIREBEND,
                payload={'amount': x, 'controller': obj.controller, 'source': obj.id},
                source=obj.id,
            ),
        ]
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        duration='while_on_battlefield',
    )


def make_earthbend_etb_trigger(
    obj: GameObject,
    x_amount: AmountSource,
) -> Interceptor:
    """Earthbend X on enter (when this enters, earthbend X).

    Picks the first eligible land you control, adds X +1/+1 counters to it,
    and emits a BENDING_EARTHBEND marker. If no land is available, only the
    marker is emitted with land_id=None (still counts as bending for trackers).

    Earthbend's full text says the chosen land becomes a 0/0 creature with
    haste; the +1/+1 counters and the bending marker are the engine's current
    representation. Targeting/animation is the engine gap.
    """

    def filter_fn(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.ZONE_CHANGE
            and event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD
            and event.payload.get('object_id') == obj.id
        )

    def handler(event: Event, state: GameState) -> InterceptorResult:
        x = _resolve_amount(x_amount, obj, state)
        new_events = _earthbend_events(obj, state, x)
        if not new_events:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        duration='while_on_battlefield',
    )


def make_earthbend_attack_trigger(
    obj: GameObject,
    x_amount: AmountSource,
) -> Interceptor:
    """Earthbend X on attack."""

    def filter_fn(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.ATTACK_DECLARED
            and event.payload.get('attacker_id') == obj.id
        )

    def handler(event: Event, state: GameState) -> InterceptorResult:
        x = _resolve_amount(x_amount, obj, state)
        new_events = _earthbend_events(obj, state, x)
        if not new_events:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        duration='while_on_battlefield',
    )


def make_earthbend_death_trigger(
    obj: GameObject,
    x_amount: AmountSource,
    on_creature_death_filter: Optional[Callable[[Event, GameState], bool]] = None,
) -> Interceptor:
    """Earthbend X when this dies (or, optionally, when another matching creature dies).

    `on_creature_death_filter`, if provided, narrows to deaths of *another*
    creature. The default is the source itself dying.
    """

    def default_self_death_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.ZONE_CHANGE
            and event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD
            and event.payload.get('to_zone_type') == ZoneType.GRAVEYARD
            and event.payload.get('object_id') == obj.id
        )

    actual_filter = on_creature_death_filter or default_self_death_filter

    def handler(event: Event, state: GameState) -> InterceptorResult:
        x = _resolve_amount(x_amount, obj, state)
        new_events = _earthbend_events(obj, state, x)
        if not new_events:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=actual_filter,
        handler=handler,
        duration='while_on_battlefield',
    )


def make_earthbend_spell_cast_trigger(
    obj: GameObject,
    x_amount: AmountSource,
    cast_filter_fn: Optional[Callable[[Event, GameState, GameObject], bool]] = None,
) -> Interceptor:
    """Earthbend X whenever you cast a spell (with optional spell filter).

    Used by cards like Toph, Hardheaded Teacher (every spell -> earthbend 1)
    or scoped variants ("whenever you cast a Lesson, earthbend 1").
    """

    def default_filter(event: Event, state: GameState, source: GameObject) -> bool:
        return (
            event.type == EventType.CAST
            and event.payload.get('caster') == source.controller
        )

    actual_filter = cast_filter_fn or default_filter

    def filter_fn(event: Event, state: GameState) -> bool:
        return actual_filter(event, state, obj)

    def handler(event: Event, state: GameState) -> InterceptorResult:
        x = _resolve_amount(x_amount, obj, state)
        new_events = _earthbend_events(obj, state, x)
        if not new_events:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        duration='while_on_battlefield',
    )


def make_earthbend_end_step_trigger(
    obj: GameObject,
    x_amount: AmountSource,
) -> Interceptor:
    """Earthbend X at the beginning of your end step."""

    def filter_fn(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.PHASE_START, EventType.PHASE_CHANGE):
            return False
        phase = event.payload.get('phase', '')
        step = event.payload.get('step', '')
        return 'end' in str(phase).lower() or 'end' in str(step).lower()

    def handler(event: Event, state: GameState) -> InterceptorResult:
        x = _resolve_amount(x_amount, obj, state)
        new_events = _earthbend_events(obj, state, x)
        if not new_events:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        duration='while_on_battlefield',
    )


def earthbend_events(obj: GameObject, state: GameState, amount: int) -> list[Event]:
    """Public alias for ``_earthbend_events`` so card scripts can resolve
    an earthbend X event list directly (e.g. inside an Exhaust effect_fn
    or any ad-hoc rider). Behaves identically to the internal helper.
    """
    return _earthbend_events(obj, state, amount)


def _earthbend_events(obj: GameObject, state: GameState, x: int) -> list[Event]:
    """Build the events for a single earthbend X resolution.

    Picks the first land you control without +1/+1 counters yet (else the
    first land), adds X counters to it, and emits the marker. Returns an
    empty list if x <= 0 and no marker is appropriate.
    """
    if x <= 0:
        # Still emit a marker so that "trigger" effects know bending happened,
        # but only if there's at least one viable target. Cards with X==0
        # almost never want a no-op marker, so skip entirely.
        return []
    lands = _tla_lands_you_control(obj, state)
    if not lands:
        # No land to earthbend onto; emit only the marker so transform-style
        # tracking still notices the action.
        return [
            Event(
                type=EventType.BENDING_EARTHBEND,
                payload={
                    'amount': x,
                    'controller': obj.controller,
                    'source': obj.id,
                    'land_id': None,
                },
                source=obj.id,
            )
        ]
    # Prefer a land that doesn't already have +1/+1 counters so we spread
    # earthbends across multiple lands when possible.
    chosen = next(
        (lnd for lnd in lands if lnd.state.counters.get('+1/+1', 0) == 0),
        lands[0],
    )
    return [
        Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': chosen.id, 'counter_type': '+1/+1', 'amount': x},
            source=obj.id,
        ),
        Event(
            type=EventType.BENDING_EARTHBEND,
            payload={
                'amount': x,
                'controller': obj.controller,
                'source': obj.id,
                'land_id': chosen.id,
            },
            source=obj.id,
        ),
    ]


def make_airbend_etb_trigger(
    obj: GameObject,
    target_filter: Optional[Callable[[GameObject, GameState], bool]] = None,
    min_targets: int = 0,
    max_targets: int = 1,
    prompt: str = "Airbend up to one target nonland permanent",
) -> Interceptor:
    """Airbend on enter (exile target nonland permanent; owner may cast for {2}).

    Schedules a target-choice; the actual exile + flashback-from-exile is the
    engine gap. Emits BENDING_AIRBEND marker so trackers see the action.

    `target_filter(target_obj, state)` decides which permanents are eligible.
    Default: any nonland permanent on the battlefield other than the source.
    """

    def default_filter(target: GameObject, state: GameState) -> bool:
        return (
            target.id != obj.id
            and target.zone == ZoneType.BATTLEFIELD
            and CardType.LAND not in target.characteristics.types
        )

    actual_filter = target_filter or default_filter

    def filter_fn(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.ZONE_CHANGE
            and event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD
            and event.payload.get('object_id') == obj.id
        )

    def handler(event: Event, state: GameState) -> InterceptorResult:
        legal = [o.id for o in state.objects.values() if actual_filter(o, state)]
        events: list[Event] = []
        if legal:
            choice = PendingChoice(
                choice_type="target",
                player=obj.controller,
                prompt=prompt,
                options=legal,
                source_id=obj.id,
                min_choices=min_targets,
                max_choices=max_targets,
                callback_data={'effect': 'airbend', 'source_id': obj.id},
            )
            state.pending_choice = choice
        # Emit the marker regardless so tracker effects fire.
        events.append(
            Event(
                type=EventType.BENDING_AIRBEND,
                payload={
                    'amount': 1,
                    'controller': obj.controller,
                    'source': obj.id,
                    'target_id': None,
                },
                source=obj.id,
            )
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        duration='while_on_battlefield',
    )


def make_airbend_attack_trigger(
    obj: GameObject,
    target_filter: Optional[Callable[[GameObject, GameState], bool]] = None,
    prompt: str = "Airbend target nonland permanent",
) -> Interceptor:
    """Airbend on attack."""

    def default_filter(target: GameObject, state: GameState) -> bool:
        return (
            target.id != obj.id
            and target.zone == ZoneType.BATTLEFIELD
            and CardType.LAND not in target.characteristics.types
        )

    actual_filter = target_filter or default_filter

    def filter_fn(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.ATTACK_DECLARED
            and event.payload.get('attacker_id') == obj.id
        )

    def handler(event: Event, state: GameState) -> InterceptorResult:
        legal = [o.id for o in state.objects.values() if actual_filter(o, state)]
        events: list[Event] = []
        if legal:
            choice = PendingChoice(
                choice_type="target",
                player=obj.controller,
                prompt=prompt,
                options=legal,
                source_id=obj.id,
                min_choices=0,
                max_choices=1,
                callback_data={'effect': 'airbend', 'source_id': obj.id},
            )
            state.pending_choice = choice
        events.append(
            Event(
                type=EventType.BENDING_AIRBEND,
                payload={
                    'amount': 1,
                    'controller': obj.controller,
                    'source': obj.id,
                    'target_id': None,
                },
                source=obj.id,
            )
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler,
        duration='while_on_battlefield',
    )


def emit_waterbend_marker(
    obj: GameObject,
    amount: int,
) -> Event:
    """Build a BENDING_WATERBEND marker event.

    Waterbend itself is an X-cost activated cost (engine gap for the cost-
    reduction tap-helper), so this helper is used by setup functions that
    detect a waterbend payment and want to broadcast a marker. Card scripts
    can include this in their event list when they fire a waterbend rider
    so that trackers (like Avatar Aang's transform) see the action.
    """
    return Event(
        type=EventType.BENDING_WATERBEND,
        payload={'amount': int(amount or 0), 'controller': obj.controller, 'source': obj.id},
        source=obj.id,
    )


def _parse_waterbend_amount(waterbend_cost: str) -> int:
    """Extract the numeric portion of a waterbend cost string for the marker.

    The marker carries an ``amount`` field used by trackers (e.g. Avatar Aang's
    transform). For "{4}" this is 4; for "{4}{U}" it's 4 (only the generic
    portion counts toward the waterbend amount paid). For "{X}" it's 0 — the
    actual X value is unknown at activation-effect time without engine
    plumbing, so trackers reading the marker need to consult the activation
    descriptor for {X} amounts (engine gap).
    """
    if not waterbend_cost:
        return 0
    total = 0
    i = 0
    s = waterbend_cost
    while i < len(s):
        if s[i] == '{':
            j = s.find('}', i + 1)
            if j == -1:
                break
            sym = s[i + 1:j].strip()
            try:
                total += int(sym)
            except ValueError:
                pass  # colored mana / {X} / {T} contribute 0 to the amount marker
            i = j + 1
        else:
            i += 1
    return total


def make_waterbend_activated_ability(
    obj: GameObject,
    waterbend_cost: str,
    effect_fn: Callable,
    *,
    description: str = "",
    sorcery_speed: bool = False,
    own_turn_only: bool = False,
    targets_required: int = 0,
    target_kind: str = "any",
    target_requirements: Optional[list] = None,
    once_per_turn: bool = False,
    precondition_fn: Optional[Callable] = None,
):
    """Register a "Waterbend {X}: <effect>" activated ability on ``obj``.

    Waterbend is the TLA water-tribe activated cost. The card text reads::

        Waterbend {X}: <effect>. (While paying a waterbend cost, you can
        tap your artifacts and creatures to help. Each one pays for {1}.)

    Functionally this is a plain activated ability whose mana cost is
    ``{X}``. The "tap artifacts/creatures to help" cost-payment hook is
    not yet wired (engine gap — pending a real "alternate payment with
    tap-helpers" subsystem), so the ability behaves like a vanilla mana
    activation for now and the marker reports the printed cost.

    After the user-supplied ``effect_fn`` runs, this helper appends a
    ``BENDING_WATERBEND`` marker event so trackers (e.g. Avatar Aang's
    transform) observe the action.

    Args:
        obj: the source permanent.
        waterbend_cost: cost string fragment such as ``"{3}"``, ``"{4}{U}"``.
            Note: card text writes "Waterbend {3}: <effect>" — pass the
            ``{3}`` portion; the helper handles the rest.
        effect_fn: ``(obj, state, targets) -> list[Event]``. Standard
            activated-ability effect signature.
        description: human-readable description for the ability surface.
            Defaults to ``"Waterbend {cost}: ..."``.
        sorcery_speed / own_turn_only / once_per_turn / precondition_fn:
            forwarded to ``register_activated_ability`` (same semantics).
        targets_required / target_kind / target_requirements: target picker
            shape, matching ``make_activated_ability``.

    Returns the ``ActivatedAbility`` descriptor (same as
    ``register_activated_ability``). The setup function should return
    ``[]`` (or any other interceptors it wants) since the ability is
    consulted via ``obj.state.activated_abilities``.
    """
    from .activated import register_activated_ability

    # The marker amount reflects the printed generic mana — colored / {X}
    # symbols contribute 0. TODO(engine-gap): once the tap-helper cost
    # subsystem lands, the marker should reflect the actual amount paid
    # (printed cost minus helpers) and {X} announcements should be
    # forwarded so trackers can see the resolved value.
    marker_amount = _parse_waterbend_amount(waterbend_cost)

    user_effect_fn = effect_fn

    def _wrapped_effect(o: GameObject, state: GameState, targets) -> list[Event]:
        try:
            events = list(user_effect_fn(o, state, targets) or [])
        except TypeError:
            # Tolerate legacy zero-arg effect_fns for transition.
            events = list(user_effect_fn(o, state) or [])
        events.append(emit_waterbend_marker(o, marker_amount))
        return events

    desc = description or f"Waterbend {waterbend_cost}: ..."

    return register_activated_ability(
        obj,
        cost=waterbend_cost,
        effect_fn=_wrapped_effect,
        description=desc,
        sorcery_speed=sorcery_speed,
        own_turn_only=own_turn_only,
        once_per_turn=once_per_turn,
        targets_required=targets_required,
        target_kind=target_kind,
        target_requirements=target_requirements,
        precondition_fn=precondition_fn,
    )


# Convenience: build all four "an X-bend happened on attack" wrappers from a
# single attacker. Useful for cards with combined bending riders.
def make_combined_bend_attack_trigger(
    obj: GameObject,
    firebend: Optional[AmountSource] = None,
    earthbend: Optional[AmountSource] = None,
) -> list[Interceptor]:
    """Convenience: wire firebend and/or earthbend on attack in one call."""
    out: list[Interceptor] = []
    if firebend is not None:
        out.append(make_firebend_attack_trigger(obj, firebend))
    if earthbend is not None:
        out.append(make_earthbend_attack_trigger(obj, earthbend))
    return out
