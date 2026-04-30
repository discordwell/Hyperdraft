"""
OTJ Plot and Saddle Mechanics

Implements the two flagship Outlaws of Thunder Junction mechanics on top of
the standard event/interceptor pipeline.

Plot
----
"You may pay {plot_cost} and exile this card from your hand. Cast it as a
sorcery on a later turn for its mana cost without paying its mana cost.
Plot only as a sorcery."

Implementation notes:
* The card is moved from hand to exile and tagged via
  ``obj.state.plotted_turn`` (the turn number when plot was paid).
* A PLOT_BECOMES_PLOTTED event fires immediately after the card is exiled,
  for "when this card becomes plotted" triggers.
* On a *later* turn during a sorcery window, ``cast_plotted_spell()`` moves
  the card from exile to the battlefield/stack with no mana cost. The card
  is single-use; ``plot_cast_used`` prevents re-casting from exile.

Saddle
------
"Saddle N (Tap any number of other creatures you control with total power N
or more: This Mount becomes saddled until end of turn. Saddle only as a
sorcery.)"

Implementation notes:
* ``pay_saddle_cost()`` validates and taps the supplied creature ids,
  ensuring the threshold is met. It emits SADDLE_PAID followed by a
  SADDLE_BECOMES_SADDLED event used by "becomes saddled" triggers.
* ``obj.state.saddled_until_eot`` flips to True; the per-turn cleanup in
  ``turn.py`` resets it (mirroring ``crewed_until_eot``).
* ``make_saddle_trigger()`` wraps an attack trigger that only fires when
  the Mount is currently saddled.
"""

from typing import Callable, Optional

from .types import (
    Event, EventType,
    GameObject, GameState, ZoneType, CardType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    new_id,
)


# =============================================================================
# === PLOT/SADDLE HELPERS ===
# =============================================================================

# -----------------------------------------------------------------------------
# Plot helpers
# -----------------------------------------------------------------------------

def is_plotted(obj: GameObject) -> bool:
    """Check if a GameObject is currently plotted (in exile, awaiting cast)."""
    if obj is None:
        return False
    if obj.zone != ZoneType.EXILE:
        return False
    if obj.state.plot_cast_used:
        return False
    return obj.state.plotted_turn is not None


def can_cast_plotted(obj: GameObject, state: GameState) -> bool:
    """
    A plotted card may be cast on any turn AFTER the turn it was plotted,
    during its controller's main phase (sorcery speed).

    The phase/main check is the responsibility of the caller (the priority
    system already gates sorceries to main phases). Here we only enforce the
    "later turn" rule.
    """
    if not is_plotted(obj):
        return False
    plotted_turn = obj.state.plotted_turn
    if plotted_turn is None:
        return False
    # "On a later turn" means strictly greater than the turn it was plotted.
    return state.turn_number > plotted_turn


def pay_plot_cost(
    state: GameState,
    card_id: str,
    player_id: str,
) -> list[Event]:
    """
    Move a card from its owner's hand to exile and mark it as plotted.

    Returns the events emitted (PLOT_PAID, ZONE_CHANGE, PLOT_BECOMES_PLOTTED)
    so callers can either return them from a setup function or inspect them.

    The mana cost itself is the responsibility of the caller — typically the
    activated-ability handler will charge the plot cost before invoking this
    helper.
    """
    obj = state.objects.get(card_id)
    if obj is None:
        return []
    if obj.zone != ZoneType.HAND:
        return []
    if obj.controller != player_id:
        return []

    events: list[Event] = []

    paid = Event(
        type=EventType.PLOT_PAID,
        payload={
            'object_id': card_id,
            'player': player_id,
            'turn': state.turn_number,
        },
        source=card_id,
        controller=player_id,
    )
    events.append(paid)

    # Move from hand to exile via ZONE_CHANGE so the standard pipeline
    # cleans up zones / removes interceptors as needed.
    zone_change = Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': card_id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.EXILE,
        },
        source=card_id,
        controller=player_id,
    )
    events.append(zone_change)

    # Mark the object as plotted. We mutate state directly (instead of
    # waiting for the ZONE_CHANGE handler) because the card may be returned
    # by the same set of events; tagging it first ensures becomes-plotted
    # triggers fire with consistent state.
    obj.state.plotted_turn = state.turn_number
    obj.state.plot_cast_used = False

    becomes_plotted = Event(
        type=EventType.PLOT_BECOMES_PLOTTED,
        payload={
            'object_id': card_id,
            'player': player_id,
            'turn': state.turn_number,
        },
        source=card_id,
        controller=player_id,
    )
    events.append(becomes_plotted)

    return events


def cast_plotted_spell(
    state: GameState,
    card_id: str,
    player_id: str,
) -> list[Event]:
    """
    Cast a plotted card from exile without paying its mana cost.

    Returns events for the cast. The card is removed from exile and routed
    through normal ZONE_CHANGE / CAST events. The plot tag is consumed so
    the same card can't be cast twice via plot.
    """
    obj = state.objects.get(card_id)
    if obj is None or not can_cast_plotted(obj, state):
        return []
    if obj.controller != player_id:
        return []

    events: list[Event] = []

    cast_evt = Event(
        type=EventType.PLOT_CAST,
        payload={
            'object_id': card_id,
            'player': player_id,
            'turn': state.turn_number,
        },
        source=card_id,
        controller=player_id,
    )
    events.append(cast_evt)

    # For permanents (creatures, artifacts, enchantments), going to the
    # battlefield directly is the closest analogue to "cast for free" given
    # how this engine resolves spells. Non-permanents resolve via the stack.
    is_permanent = bool(
        {CardType.CREATURE, CardType.ARTIFACT,
         CardType.ENCHANTMENT, CardType.PLANESWALKER, CardType.LAND}
        & obj.characteristics.types
    )
    to_zone = ZoneType.BATTLEFIELD if is_permanent else ZoneType.STACK

    zone_change = Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': card_id,
            'from_zone_type': ZoneType.EXILE,
            'to_zone_type': to_zone,
        },
        source=card_id,
        controller=player_id,
    )
    events.append(zone_change)

    # Mark plot as consumed so the card can't be cast from exile twice.
    obj.state.plot_cast_used = True
    obj.state.plotted_turn = None

    return events


def make_becomes_plotted_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
) -> Interceptor:
    """
    Trigger that fires when this specific card *becomes plotted* (i.e. its
    plot cost is paid and it moves to exile).

    Useful for cards like "When this card becomes plotted, deal 2 damage..."
    """
    src_id = source_obj.id

    def trigger_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.PLOT_BECOMES_PLOTTED and
                event.payload.get('object_id') == src_id)

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=effect_fn(event, state),
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        # Plot interceptors live with the card (in exile or wherever) so that
        # "when becomes plotted" fires even though the card isn't on the
        # battlefield. Use 'forever' so cleanup doesn't drop it on zone moves
        # away from battlefield.
        duration='forever',
    )


# -----------------------------------------------------------------------------
# Saddle helpers
# -----------------------------------------------------------------------------

def is_saddled(obj: GameObject) -> bool:
    """Return True if this Mount is currently saddled (until end of turn)."""
    if obj is None:
        return False
    return bool(obj.state.saddled_until_eot)


def _is_mount(obj: GameObject) -> bool:
    return 'Mount' in obj.characteristics.subtypes


def _power_value(obj: GameObject, state: GameState) -> int:
    """Get the (current) power of a creature, falling back to printed value."""
    base = obj.characteristics.power
    if base is None:
        return 0
    # Fold in temporary +1/+1 counter style bonuses if present.
    counters = obj.state.counters or {}
    plus = int(counters.get('+1/+1', 0))
    minus = int(counters.get('-1/-1', 0))
    return int(base) + plus - minus


def pay_saddle_cost(
    state: GameState,
    mount_id: str,
    tapper_ids: list[str],
    player_id: str,
) -> list[Event]:
    """
    Tap the listed creatures (each must be another untapped creature the
    player controls) and saddle the named Mount. Power threshold is read
    from the Mount's ``saddle_threshold`` (assigned via the card setup).

    Returns the events emitted: TAPs, SADDLE_PAID, SADDLE_BECOMES_SADDLED.
    Returns [] if validation fails (caller should report an error).
    """
    mount = state.objects.get(mount_id)
    if mount is None or mount.zone != ZoneType.BATTLEFIELD:
        return []
    if mount.controller != player_id:
        return []
    if not _is_mount(mount):
        return []

    # Threshold lives on the card_def (set via make_mount() / setup) or on
    # the GameObject's state for tokens. Default to 1 if unset.
    threshold = 1
    if mount.card_def is not None:
        threshold = int(getattr(mount.card_def, 'saddle_threshold', threshold) or 1)
    threshold = int(getattr(mount.state, 'saddle_threshold', threshold) or threshold)

    # Validate tappers: distinct, controlled by player, untapped, creature,
    # not the mount itself.
    seen: set[str] = set()
    tappers: list[GameObject] = []
    total_power = 0
    for tid in tapper_ids:
        if tid == mount_id or tid in seen:
            return []
        seen.add(tid)
        t = state.objects.get(tid)
        if t is None:
            return []
        if t.zone != ZoneType.BATTLEFIELD:
            return []
        if t.controller != player_id:
            return []
        if CardType.CREATURE not in t.characteristics.types:
            return []
        if t.state.tapped:
            return []
        tappers.append(t)
        total_power += _power_value(t, state)

    if total_power < threshold:
        return []

    events: list[Event] = []

    # Tap each saddler.
    for t in tappers:
        t.state.tapped = True
        events.append(Event(
            type=EventType.TAP,
            payload={'object_id': t.id},
            source=mount_id,
            controller=player_id,
        ))

    events.append(Event(
        type=EventType.SADDLE_PAID,
        payload={
            'object_id': mount_id,
            'player': player_id,
            'tapper_ids': [t.id for t in tappers],
            'threshold': threshold,
        },
        source=mount_id,
        controller=player_id,
    ))

    mount.state.saddled_until_eot = True
    mount.state.saddled_count_this_turn = int(mount.state.saddled_count_this_turn or 0) + 1
    saddlers_now = list(mount.state.saddled_by_this_turn or [])
    for t in tappers:
        if t.id not in saddlers_now:
            saddlers_now.append(t.id)
    mount.state.saddled_by_this_turn = saddlers_now

    events.append(Event(
        type=EventType.SADDLE_BECOMES_SADDLED,
        payload={
            'object_id': mount_id,
            'player': player_id,
            'tapper_ids': [t.id for t in tappers],
            'first_time': mount.state.saddled_count_this_turn == 1,
        },
        source=mount_id,
        controller=player_id,
    ))

    return events


def make_saddle_trigger(
    source_obj: GameObject,
    threshold: int,
    effect_fn: Callable[[Event, GameState], list[Event]],
) -> Interceptor:
    """
    "Whenever this creature attacks while saddled, <effect>."

    The trigger only fires if the Mount is currently saddled
    (``obj.state.saddled_until_eot`` is True). Pair this with
    ``set_saddle_threshold(card_def, n)`` so ``pay_saddle_cost`` knows the
    required total power.
    """
    src_id = source_obj.id

    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        if event.payload.get('attacker_id') != src_id:
            return False
        obj = state.objects.get(src_id)
        return bool(obj and is_saddled(obj))

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=effect_fn(event, state),
        )

    # Stash the threshold on the object so pay_saddle_cost() can find it.
    source_obj.state.saddle_threshold = int(threshold)

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
    )


def make_becomes_saddled_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
    first_time_only: bool = False,
) -> Interceptor:
    """Trigger that fires when this Mount becomes saddled (or first-time only)."""
    src_id = source_obj.id

    def trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.SADDLE_BECOMES_SADDLED:
            return False
        if event.payload.get('object_id') != src_id:
            return False
        if first_time_only and not event.payload.get('first_time'):
            return False
        return True

    def trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=effect_fn(event, state),
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=trigger_filter,
        handler=trigger_handler,
        duration='while_on_battlefield',
    )


def set_saddle_threshold(card_def, threshold: int) -> None:
    """
    Stash a Saddle N threshold on a CardDefinition so pay_saddle_cost()
    can find it when it instantiates the Mount on the battlefield.
    """
    setattr(card_def, 'saddle_threshold', int(threshold))


def reset_saddled_at_eot(state: GameState) -> None:
    """
    Cleanup helper used by turn.py at end of turn — clears saddled state
    on every Mount on the battlefield. Mirrors the crewed_until_eot reset.
    """
    bf = state.zones.get('battlefield')
    if not bf:
        return
    for oid in bf.objects:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        if obj.state.saddled_until_eot:
            obj.state.saddled_until_eot = False
        obj.state.saddled_by_this_turn = []
        obj.state.saddled_count_this_turn = 0


__all__ = [
    # Plot
    'is_plotted', 'can_cast_plotted',
    'pay_plot_cost', 'cast_plotted_spell',
    'make_becomes_plotted_trigger',
    # Saddle
    'is_saddled', 'pay_saddle_cost',
    'make_saddle_trigger', 'make_becomes_saddled_trigger',
    'set_saddle_threshold', 'reset_saddled_at_eot',
]
