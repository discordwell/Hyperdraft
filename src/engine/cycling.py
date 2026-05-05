"""Cycling (CR 702.32) — engine module (W8).

Cycling is an activated ability available only while the source card is in
its owner's hand. The cost is ``{cost}, Discard this card`` and the printed
effect is ``Draw a card``. Variants:

- **Plain cycling** — discard this card, draw 1.
- **Landcycling / typecycling** — discard this card, search library for a
  land of the named subtype (or any card of the named type for typecycling),
  reveal it, put it into your hand, then shuffle. The draw is replaced.
- **With rider trigger** — "When you cycle this card, <effect>". The rider
  fires once per cycling activation and is enqueued alongside the search/draw.

The implementation reuses the existing activated-ability framework
(``src/engine/activated.py``):

- The cycling cost is registered as ``"<mana>, Discard this card"`` so the
  framework's parser recognises ``Discard this card`` and emits a ``DISCARD``
  event during cost-payment (moving the card from HAND to GRAVEYARD).
- The effect_fn returned by ``make_cycling_ability`` emits a CYCLE marker
  event followed by either a DRAW (plain) or a SEARCH_LIBRARY-driven
  PendingChoice (landcycling/typecycling). If a rider was supplied its
  events are appended after the CYCLE marker.

Card scripts wire cycling via ``setup_in_hand`` callables — see the
re-exports in ``src/cards/interceptor_helpers.py``.
"""
from __future__ import annotations

from typing import Callable, Optional, TYPE_CHECKING

from .types import (
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    ZoneType,
)

if TYPE_CHECKING:  # pragma: no cover
    from .activated import ActivatedAbility


CycleEffectFn = Callable[[GameObject, GameState, list], list[Event]]
RiderFn = Callable[[GameObject, GameState], list[Event]]


def _open_typecycling_search(
    obj: GameObject,
    state: GameState,
    *,
    landcycling: Optional[list[str]] = None,
    typecycling: Optional[str] = None,
) -> list[Event]:
    """Open a library-search PendingChoice for landcycling / typecycling.

    Filter semantics:
      - ``landcycling=['Mountain']`` -> any land card with subtype 'Mountain'
        (basic OR non-basic; a Stomping Ground is a legal landcycling find).
      - ``landcycling=['Plains', 'Island']`` -> any card with EITHER subtype.
      - ``typecycling='Wizard'`` -> any card whose name/subtypes include the
        type. We accept matches against subtypes (the most common case for
        typecycling: "Wizardcycling" finds creatures with subtype Wizard).

    Returns an empty list (the search is opened by side effect on ``state``).
    Callers should append our return to whatever events they otherwise emit
    so the pipeline keeps moving.
    """
    from .types import CardType
    from .library_search import create_library_search_choice

    target_subtypes = set(landcycling or [])
    if typecycling:
        target_subtypes.add(typecycling)

    def _filter(o: GameObject, st: GameState) -> bool:
        # For landcycling: must be a land AND have at least one of the named
        # land subtypes.
        if landcycling:
            if CardType.LAND not in o.characteristics.types:
                return False
            return bool(set(o.characteristics.subtypes or set()) & set(landcycling))
        # For typecycling: subtype match is sufficient.
        if typecycling:
            return typecycling in (o.characteristics.subtypes or set())
        return False

    prompt_label = (
        "land card of type " + "/".join(landcycling)
        if landcycling
        else f"{typecycling} card"
    )

    create_library_search_choice(
        state,
        obj.controller,
        obj.id,
        filter_fn=_filter,
        min_count=0,
        max_count=1,
        destination="hand",
        reveal=True,
        shuffle_after=True,
        optional=True,
        prompt=f"Search your library for a {prompt_label}, reveal it, put it into your hand, then shuffle.",
    )
    return []


def _build_cycle_effect(
    cost: str,
    *,
    landcycling: Optional[list[str]] = None,
    typecycling: Optional[str] = None,
    rider_effect_fn: Optional[RiderFn] = None,
) -> CycleEffectFn:
    """Build the resolve effect_fn for a cycling activated ability.

    The returned function:
      1. Emits a CYCLE marker event (always — used by external triggers).
      2. Either opens a library search (landcycling/typecycling) or emits
         DRAW {player} 1 (plain).
      3. If ``rider_effect_fn`` is supplied, runs it and appends a
         CYCLING_TRIGGERED marker so logs/tests can see the rider fired.

    The cost-discard happens earlier in pay_activation_cost; by the time this
    function is invoked the source object has already moved from HAND to
    GRAVEYARD (or been redirected by an exile-instead replacement).
    """
    variant = (
        "landcycling" if landcycling
        else ("typecycling" if typecycling else "plain")
    )

    def _effect(obj: GameObject, state: GameState, targets) -> list[Event]:  # noqa: ARG001
        events: list[Event] = []

        events.append(Event(
            type=EventType.CYCLE,
            payload={
                'player': obj.controller,
                'card_id': obj.id,
                'card_name': obj.name,
                'variant': variant,
                'mana_cost': cost,
            },
            source=obj.id,
            controller=obj.controller,
        ))

        if landcycling or typecycling:
            events.extend(_open_typecycling_search(
                obj, state, landcycling=landcycling, typecycling=typecycling,
            ))
        else:
            events.append(Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'count': 1},
                source=obj.id,
                controller=obj.controller,
            ))

        if rider_effect_fn is not None:
            try:
                rider_events = list(rider_effect_fn(obj, state) or [])
            except Exception:
                rider_events = []
            events.extend(rider_events)
            events.append(Event(
                type=EventType.CYCLING_TRIGGERED,
                payload={
                    'player': obj.controller,
                    'card_id': obj.id,
                    'card_name': obj.name,
                    'rider_event_count': len(rider_events),
                },
                source=obj.id,
                controller=obj.controller,
            ))

        return events

    return _effect


def make_cycling_ability(
    obj: GameObject,
    cost: str,
    *,
    landcycling: Optional[list[str]] = None,
    typecycling: Optional[str] = None,
    rider_effect_fn: Optional[RiderFn] = None,
) -> "ActivatedAbility":
    """Register a cycling activated ability on ``obj``.

    Args:
        obj: The card object (must be in HAND for the ability to activate).
        cost: The mana portion of the cycling cost, e.g. ``"{2}"`` or ``"{W}"``.
            ``Discard this card`` is appended automatically.
        landcycling: Optional list of land subtypes to find (e.g.
            ``['Mountain']`` for "Mountaincycling", ``['Plains', 'Island']``
            for "Plainscycling and Islandcycling"). Mutually exclusive with
            ``typecycling``.
        typecycling: Optional generic subtype filter (e.g. ``'Wizard'`` for
            "Wizardcycling"). Subtype match against the card's printed
            subtypes set. Mutually exclusive with ``landcycling``.
        rider_effect_fn: Optional ``(obj, state) -> list[Event]`` for a
            "When you cycle this card, ..." rider trigger. Returned events
            are appended to the cycling resolution.

    Returns the registered ``ActivatedAbility`` descriptor.

    Plain cycling::

        make_cycling_ability(obj, "{2}")

    Mountaincycling::

        make_cycling_ability(obj, "{1}{R}", landcycling=["Mountain"])

    With rider trigger::

        def damage_rider(o, st):
            return [Event(type=EventType.DAMAGE,
                          payload={'target': st.priority_player, 'amount': 1},
                          source=o.id, controller=o.controller)]
        make_cycling_ability(obj, "{2}", rider_effect_fn=damage_rider)
    """
    if landcycling and typecycling:
        raise ValueError("cycling: pass landcycling or typecycling, not both")

    from .activated import register_activated_ability

    cost_text = f"{cost}, Discard this card"
    effect_fn = _build_cycle_effect(
        cost,
        landcycling=landcycling,
        typecycling=typecycling,
        rider_effect_fn=rider_effect_fn,
    )

    if landcycling:
        desc = f"Cycling {cost} (land: {'/'.join(landcycling)})"
    elif typecycling:
        desc = f"Cycling {cost} (type: {typecycling})"
    else:
        desc = f"Cycling {cost}"

    return register_activated_ability(
        obj,
        cost=cost_text,
        effect_fn=effect_fn,
        description=desc,
        sorcery_speed=False,
    )


def make_cycling_setup(
    cost: str,
    *,
    landcycling: Optional[list[str]] = None,
    typecycling: Optional[str] = None,
    rider_effect_fn: Optional[RiderFn] = None,
) -> Callable[[GameObject, GameState], list[Interceptor]]:
    """Return a ``setup_in_hand`` callable that registers cycling on entry.

    Pair with ``card_def.setup_in_hand = make_cycling_setup(...)`` (the
    factory helpers ``make_creature``, ``make_instant``, etc. don't currently
    accept ``setup_in_hand=`` directly, so assign the attribute after
    construction).
    """
    def _setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        make_cycling_ability(
            obj,
            cost,
            landcycling=landcycling,
            typecycling=typecycling,
            rider_effect_fn=rider_effect_fn,
        )
        return []
    return _setup


def _handle_cycle_action(
    state: GameState,
    player_id: str,
    card_id: str,
    *,
    cost: str,
    landcycling: Optional[list[str]] = None,
    typecycling: Optional[str] = None,
    rider_effect_fn: Optional[RiderFn] = None,
) -> list[Event]:
    """Execute a cycling action imperatively.

    Used by tests and by anything that wants to invoke cycling without going
    through the activated-ability dispatch path. The standard production
    path is the activated-ability framework: this is a low-level utility.

    Returns the events that would be enqueued (DISCARD + CYCLE + DRAW or
    SEARCH_LIBRARY). The caller is responsible for emitting them through
    the pipeline.

    Note: this helper does NOT pay the mana cost; callers should use the
    activated-ability dispatch path (which handles mana, timing, triggers)
    in real games.
    """
    obj = state.objects.get(card_id)
    if obj is None or obj.zone != ZoneType.HAND or obj.owner != player_id:
        return []

    events: list[Event] = []

    # Discard cost (move HAND -> GRAVEYARD).
    events.append(Event(
        type=EventType.DISCARD,
        payload={'player': player_id, 'object_id': card_id},
        source=card_id,
        controller=player_id,
    ))

    # Build the resolve effect and append its events.
    effect_fn = _build_cycle_effect(
        cost,
        landcycling=landcycling,
        typecycling=typecycling,
        rider_effect_fn=rider_effect_fn,
    )
    events.extend(effect_fn(obj, state, []))
    return events


__all__ = [
    "make_cycling_ability",
    "make_cycling_setup",
    "_handle_cycle_action",
    "CycleEffectFn",
    "RiderFn",
]
