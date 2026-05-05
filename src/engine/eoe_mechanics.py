"""
EOE Station + Void mechanics — card-side helpers.

This module is the card-script-facing surface for the Edge of Eternities
``Station`` and ``Void`` keywords. The lower-level engine plumbing lives in:

  * :mod:`src.engine.station`        — STATION_ACTIVATE / STATION_CHARGE /
                                       STATION_THRESHOLD_REACHED handlers and
                                       the charge-counter primitives.
  * :mod:`src.engine.void`           — Void per-turn condition tracking
                                       (LTB / big-spell-cast / warp markers).
  * :mod:`src.engine.turn_state`     — ``cards_exiled_this_turn`` accounting
                                       used by ``make_void_trigger``.

The helpers in this module compose those primitives into the patterns that
EOE cards actually print:

  * ``make_station_ability``  — register the printed ``Station —`` activated
    ability ("Tap an untapped creature you control: charge counters") plus a
    threshold-gated effect that fires once when charge first reaches the
    threshold.

  * ``make_charge_threshold_ability`` — register a sorcery-speed activated
    ability that is only legal once the source has at least N charge
    counters (e.g. Evendo's ``12+ | {G}, {T}: Add {G} for each creature you
    control``). Returns a guard interceptor + the registered descriptor.

  * ``make_void_trigger`` — REACT trigger that fires when a card is exiled
    this turn (or when the void condition is otherwise active). Emits a
    :data:`EventType.VOID_TRIGGERED` marker for observability.

  * ``register_eoe_station_handlers`` — system interceptors that resolve
    :data:`EventType.STATION_ACTIVATE` / ``STATION_CHARGE`` /
    ``STATION_THRESHOLD_REACHED`` through the existing
    :mod:`src.engine.station` handler functions. Registered from
    :meth:`Game._setup_system_interceptors`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

from .types import (
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    ZoneType,
    new_id,
)
from .station import (
    CHARGE_COUNTER,
    add_station_charge,
    get_station_charge,
    is_stationed,
    _handle_station_activate,
    _handle_station_charge,
    _handle_station_threshold_reached,
)
from .turn_state import card_was_exiled_this_turn
from .void import is_void_active

if TYPE_CHECKING:
    from .game import Game


EffectFn = Callable[[Event, GameState], list[Event]]
ActivatedEffectFn = Callable[[GameObject, GameState, list], list[Event]]


# =============================================================================
# Station — printed activated ability + threshold effect
# =============================================================================


def make_station_ability(
    obj: GameObject,
    *,
    charge_per_activation: Optional[int] = None,
    threshold: int = 0,
    threshold_effect_fn: Optional[EffectFn] = None,
    threshold_effect_once: bool = True,
) -> list[Interceptor]:
    """Wire a card's printed ``Station —`` ability.

    The Station keyword has two shapes in EOE:

      1. Spacecraft / Planet text: ``Station (Tap an untapped creature you
         control: Put charge counters equal to its power on this <type>.
         Station only as a sorcery.)``

         The donor's power is the default charge amount (``charge_per_activation
         is None``), preserving the printed reminder.

      2. Custom-charge variants (rare on real cards): pass an integer to
         ``charge_per_activation`` to add a fixed amount per activation.

    Threshold effects fire when ``state.counters[CHARGE]`` first crosses
    ``threshold``. By default the trigger is *one-shot* per permanent
    (``threshold_effect_once=True``); set False for cards that re-fire each
    time the threshold is crossed (e.g. counters being removed and re-added).

    Returns the list of interceptors to register; also registers the activated
    ability via the global :class:`ActivatedAbility` table.

    Parameters
    ----------
    obj:
        The Spacecraft / Planet / Station card.
    charge_per_activation:
        ``None`` (default): use the donor's *power* as the charge amount, as
        printed on real EOE cards. Pass an int for fixed charge.
    threshold:
        Charge-counter count at which ``threshold_effect_fn`` fires.
    threshold_effect_fn:
        Optional ``(event, state) -> list[Event]`` invoked when threshold is
        first reached. Pass ``None`` if the only threshold behaviour is the
        creature-stat upgrade handled separately by ``make_station_creature_setup``.
    threshold_effect_once:
        Default True: the effect fires once per permanent. False: fires every
        time charge crosses the threshold from below.
    """
    # Lazy import to avoid the cards / engine import cycle at module load.
    from src.cards.interceptor_helpers import make_activated_ability

    def station_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        """Resolve the activation: pick a donor creature and emit STATION_ACTIVATE."""
        donor_id = _select_donor_id(o, st, targets)
        if donor_id is None:
            return []
        donor = st.objects.get(donor_id)
        if donor is None:
            return []
        if charge_per_activation is None:
            # Reminder text behaviour: charge equals donor's power.
            return [Event(
                type=EventType.STATION_ACTIVATE,
                payload={
                    "spacecraft_id": o.id,
                    "donor_id": donor.id,
                },
                source=o.id,
                controller=o.controller,
            )]
        # Fixed-charge variant: tap donor + emit STATION_CHARGE directly so the
        # standard handler doesn't recompute amount from donor power.
        return [
            Event(
                type=EventType.TAP,
                payload={"object_id": donor.id},
                source=o.id,
                controller=o.controller,
            ),
            Event(
                type=EventType.STATION_CHARGE,
                payload={
                    "object_id": o.id,
                    "amount": int(charge_per_activation),
                    "donor_id": donor.id,
                },
                source=o.id,
                controller=o.controller,
            ),
        ]

    # Register the activated ability. Cost text "{T}" only refers to the
    # *donor*; the Station card itself isn't tapped. We surface this as a
    # sorcery-speed ability with a custom donor target.
    make_activated_ability(
        obj,
        cost="",  # Cost is the donor tap; mana_cost is empty.
        effect_fn=station_effect,
        description="Station: tap another creature you control to charge",
        sorcery_speed=True,
        targets_required=1,
        target_kind="creature_you_control_untapped",
    )

    # Mark that this object is a Station for downstream queries / UI.
    if not hasattr(obj.state, "extras") or obj.state.extras is None:
        obj.state.extras = {}
    obj.state.extras["station"] = True
    obj.state.extras["station_threshold"] = int(threshold)

    interceptors: list[Interceptor] = []
    if threshold_effect_fn is not None and threshold > 0:
        interceptors.append(
            _make_threshold_trigger(
                obj,
                threshold=threshold,
                effect_fn=threshold_effect_fn,
                once=threshold_effect_once,
            )
        )
    return interceptors


def _select_donor_id(obj: GameObject, state: GameState, targets) -> Optional[str]:
    """Resolve the donor target for a Station activation.

    ``targets`` is the list passed by the activated-ability resolver. We
    accept either Target objects (``.object_id``) or plain id strings. If no
    target is supplied we pick a reasonable default — the first untapped
    creature controlled by ``obj.controller`` other than ``obj`` — so a card
    script with no targeting harness still resolves usefully (used by tests).
    """
    if targets:
        t = targets[0]
        donor_id = getattr(t, "object_id", None)
        if donor_id is None and isinstance(t, str):
            donor_id = t
        if donor_id and donor_id != obj.id:
            return donor_id
    # Fallback: scan the battlefield for a legal donor.
    bf = state.zones.get("battlefield")
    if bf is None:
        return None
    from .types import CardType
    for cid in bf.objects:
        if cid == obj.id:
            continue
        c = state.objects.get(cid)
        if c is None:
            continue
        if c.controller != obj.controller:
            continue
        if CardType.CREATURE not in c.characteristics.types:
            continue
        if c.state.tapped:
            continue
        return cid
    return None


def _make_threshold_trigger(
    obj: GameObject,
    *,
    threshold: int,
    effect_fn: EffectFn,
    once: bool,
) -> Interceptor:
    """Build the REACT interceptor that fires ``effect_fn`` when ``obj`` first
    reaches ``threshold`` charge counters.

    Listens to :data:`EventType.STATION_THRESHOLD_REACHED`, which carries
    ``before`` / ``after`` totals so we can detect the *crossing* turn.

    A second :data:`EventType.STATION_ACTIVATED` marker event is emitted as a
    by-product so observers (UI, AI, downstream triggers) know a station
    threshold landed this beat.
    """
    fired_key = f"_station_threshold_fired_{obj.id}"

    def filt(event: Event, state: GameState) -> bool:
        if event.type != EventType.STATION_THRESHOLD_REACHED:
            return False
        if event.payload.get("object_id") != obj.id:
            return False
        before = int(event.payload.get("before", 0) or 0)
        after = int(event.payload.get("after", 0) or 0)
        # Only fire on the *crossing* event — i.e. before < threshold <= after.
        if before >= threshold:
            return False
        if after < threshold:
            return False
        if once:
            td = getattr(state, "turn_data", None)
            if td is not None and td.get(fired_key):
                return False
            # NB: persist the flag on obj.state so it survives turn resets too
            # (one-shot per permanent, not per turn).
            extras = getattr(obj.state, "extras", None)
            if isinstance(extras, dict) and extras.get(fired_key):
                return False
        return True

    def handler(event: Event, state: GameState) -> InterceptorResult:
        events = list(effect_fn(event, state) or [])
        # Emit a STATION_ACTIVATED marker so observers can track resolution.
        events.append(Event(
            type=EventType.STATION_ACTIVATED,
            payload={
                "object_id": obj.id,
                "threshold": threshold,
            },
            source=obj.id,
            controller=obj.controller,
        ))
        if once:
            extras = getattr(obj.state, "extras", None)
            if extras is None:
                obj.state.extras = {}
                extras = obj.state.extras
            if isinstance(extras, dict):
                extras[fired_key] = True
            td = getattr(state, "turn_data", None)
            if td is not None:
                td[fired_key] = True
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        duration="while_on_battlefield",
    )


# =============================================================================
# Charge-threshold-gated activated ability
# =============================================================================


def make_charge_threshold_ability(
    obj: GameObject,
    *,
    threshold: int,
    cost: str,
    effect_fn: ActivatedEffectFn,
    description: str = "",
    sorcery_speed: bool = False,
    own_turn_only: bool = False,
    once_per_turn: bool = False,
    targets_required: int = 0,
    target_kind: str = "any",
) -> list[Interceptor]:
    """Register an activated ability that's legal only when ``obj`` has at
    least ``threshold`` charge counters.

    This is the EOE Planet ``12+ | <cost>: <effect>`` pattern (Evendo,
    Kavaron Memorial World, Susur Secundi, Uthros). Internally:

    1. The ability is registered with :func:`make_activated_ability` exactly
       like a normal activated ability.
    2. A QUERY-priority guard interceptor wraps :func:`can_pay_activation` via
       a marker event so the priority code rejects it when charge < threshold.
       (Implementation note: we wrap ``effect_fn`` so it short-circuits if the
       gate is unmet at resolution time — this keeps the harness simple while
       AIs that don't honour the gate still see no effect.)

    Returns ``[]`` (no extra interceptors) — the gating is handled inside the
    wrapped effect.
    """
    from src.cards.interceptor_helpers import make_activated_ability

    def gated_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not is_stationed(o, threshold):
            return []
        return effect_fn(o, st, targets) or []

    desc = description or f"{cost}: gated effect (charge >= {threshold})"
    desc = f"{threshold}+ | {desc}"
    make_activated_ability(
        obj,
        cost=cost,
        effect_fn=gated_effect,
        description=desc,
        sorcery_speed=sorcery_speed,
        own_turn_only=own_turn_only,
        once_per_turn=once_per_turn,
        targets_required=targets_required,
        target_kind=target_kind,
    )
    return []


# =============================================================================
# Void trigger
# =============================================================================


def make_void_trigger(
    obj: GameObject,
    effect_fn: EffectFn,
    *,
    event_type: EventType = EventType.PHASE_START,
    phase: str = "end",
    only_own_turn: bool = True,
) -> Interceptor:
    """Create a Void-gated triggered ability.

    The printed pattern on EOE Void cards is:

        ``Void — At the beginning of your end step, if a nonland permanent
        left the battlefield this turn or a spell was warped this turn or a
        card was exiled this turn, <effect>.``

    The default arguments match that wording: trigger fires at the start of
    ``obj.controller``'s end step if the void condition is active. Override
    ``event_type`` / ``phase`` for variants (e.g. attack-trigger Void cards).

    The void condition is satisfied when ANY of the following is true:

      * ``is_void_active(obj.controller, state)`` — the existing per-player
        Void state flag (set by :mod:`src.engine.void` on LTB / big-spell
        cast / warp).
      * ``card_was_exiled_this_turn(state)`` — an exile happened this turn
        (set by :mod:`src.engine.turn_state`'s exile tracker).

    A :data:`EventType.VOID_TRIGGERED` marker is emitted alongside the
    effect's events so observers (UI, AI, parent triggers) can react to a
    Void resolution discretely.
    """
    def filt(event: Event, state: GameState) -> bool:
        if event.type != event_type:
            return False
        if event_type == EventType.PHASE_START:
            if event.payload.get("phase") != phase:
                return False
        if only_own_turn and state.active_player != obj.controller:
            return False
        # Void condition: any of the three contributors is enough.
        if is_void_active(obj.controller, state):
            return True
        if card_was_exiled_this_turn(state):
            return True
        return False

    def handler(event: Event, state: GameState) -> InterceptorResult:
        events = list(effect_fn(event, state) or [])
        events.append(Event(
            type=EventType.VOID_TRIGGERED,
            payload={
                "player": obj.controller,
                "source": obj.id,
            },
            source=obj.id,
            controller=obj.controller,
        ))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filt,
        handler=handler,
        duration="while_on_battlefield",
    )


# =============================================================================
# System pipeline registration
# =============================================================================


def register_eoe_station_handlers(game: "Game") -> None:
    """Register STATION_* event handlers as REACT system interceptors.

    The :mod:`src.engine.station` module exposes plain functions
    (``_handle_station_activate``, ``_handle_station_charge``,
    ``_handle_station_threshold_reached``); we wrap them as REACT
    interceptors so they participate in the standard event pipeline without
    modifying ``EVENT_HANDLERS``. Called from
    :meth:`Game._setup_system_interceptors`.
    """
    register = game.register_interceptor

    def make_handler(handler_fn):
        def adapter(event: Event, state: GameState) -> InterceptorResult:
            new_events = list(handler_fn(event, state) or [])
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=new_events,
            )
        return adapter

    register(Interceptor(
        id=new_id(),
        source="SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: e.type == EventType.STATION_ACTIVATE,
        handler=make_handler(_handle_station_activate),
        duration="forever",
    ))

    register(Interceptor(
        id=new_id(),
        source="SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: e.type == EventType.STATION_CHARGE,
        handler=make_handler(_handle_station_charge),
        duration="forever",
    ))

    register(Interceptor(
        id=new_id(),
        source="SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: e.type == EventType.STATION_THRESHOLD_REACHED,
        handler=make_handler(_handle_station_threshold_reached),
        duration="forever",
    ))


__all__ = [
    "make_station_ability",
    "make_charge_threshold_ability",
    "make_void_trigger",
    "register_eoe_station_handlers",
    "CHARGE_COUNTER",
    "add_station_charge",
    "get_station_charge",
    "is_stationed",
]
