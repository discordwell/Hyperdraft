"""
EOE Station Mechanic

Station: "{T}: Put N charge counters on this Spacecraft."
A Station card (Spacecraft or Planet) accumulates ``charge`` counters.
When the count crosses a threshold, the Spacecraft becomes a creature with
specified power/toughness/keywords (and the Planet unlocks an ability).

Implementation philosophy
-------------------------
* Counters live on ``obj.state.counters['charge']`` like every other counter.
* Three new EventTypes drive the mechanic:
    - ``STATION_ACTIVATE``      Player taps another creature to charge this card.
    - ``STATION_CHARGE``        Charge counters being added (transformable).
    - ``STATION_THRESHOLD_REACHED`` Marker fired when threshold crossed (for
                                triggers and listeners).
* Threshold-gated creature abilities are implemented as continuous effects via
  QUERY_POWER / QUERY_TOUGHNESS / QUERY_TYPES / QUERY_ABILITIES interceptors
  (see ``make_station_creature_setup`` in interceptor_helpers.py).
"""

from __future__ import annotations

from typing import Any

from .types import (
    Event,
    EventType,
    GameObject,
    GameState,
    ZoneType,
)


CHARGE_COUNTER = "charge"


# =============================================================================
# Public helpers
# =============================================================================


def get_station_charge(obj: GameObject) -> int:
    """Return the number of charge counters currently on a Spacecraft/Planet."""
    if obj is None:
        return 0
    return int(obj.state.counters.get(CHARGE_COUNTER, 0))


def is_stationed(obj: GameObject, threshold: int) -> bool:
    """Return True if ``obj`` has at least ``threshold`` charge counters."""
    return get_station_charge(obj) >= int(threshold)


def add_station_charge(obj: GameObject, amount: int) -> None:
    """Mutate ``obj.state.counters['charge']`` directly (no event emission).

    Most callers should emit a :data:`EventType.STATION_CHARGE` event instead;
    this helper exists for tests and for the pipeline handlers below.
    """
    if obj is None or amount <= 0:
        return
    current = int(obj.state.counters.get(CHARGE_COUNTER, 0))
    obj.state.counters[CHARGE_COUNTER] = current + int(amount)


# =============================================================================
# Event handlers
# =============================================================================


def _handle_station_activate(event: Event, state: GameState) -> list[Event]:
    """Handle a Station activated ability.

    Payload:
        spacecraft_id (str): The Spacecraft/Planet being stationed.
        donor_id (str):      The other creature being tapped to provide charge.
        controller (str):    Player activating Station.

    Effect:
        * Tap the donor creature.
        * Emit a STATION_CHARGE event whose ``amount`` equals the donor's
          (computed) power.

    Returns a list of follow-up events to enqueue.
    """
    follow_ups: list[Event] = []
    if not isinstance(event.payload, dict):
        return follow_ups

    spacecraft_id = event.payload.get("spacecraft_id") or event.payload.get("object_id")
    donor_id = event.payload.get("donor_id")
    if not spacecraft_id or not donor_id:
        return follow_ups

    spacecraft = state.objects.get(spacecraft_id)
    donor = state.objects.get(donor_id)
    if not spacecraft or not donor:
        return follow_ups

    # Sanity: donor must be a different, untapped creature on the battlefield
    # controlled by the same player. We don't *enforce* sorcery-speed timing
    # here — that's a UI/turn-manager concern. We just guard hard rules.
    if donor.id == spacecraft.id:
        return follow_ups
    if donor.zone != ZoneType.BATTLEFIELD or spacecraft.zone != ZoneType.BATTLEFIELD:
        return follow_ups
    if donor.controller != spacecraft.controller:
        return follow_ups
    if donor.state.tapped:
        return follow_ups

    # Compute donor's power *now* so QUERY interceptors apply.
    from .queries import get_power  # local import: queries imports types

    amount = max(0, int(get_power(donor, state)))

    # Tap the donor as part of the activation cost.
    follow_ups.append(
        Event(
            type=EventType.TAP,
            payload={"object_id": donor.id},
            source=spacecraft.id,
            controller=spacecraft.controller,
        )
    )

    # Issue the charge event (always, even when amount is 0 — interceptors may
    # still want to react to the activation).
    follow_ups.append(
        Event(
            type=EventType.STATION_CHARGE,
            payload={
                "object_id": spacecraft.id,
                "amount": amount,
                "donor_id": donor.id,
            },
            source=spacecraft.id,
            controller=spacecraft.controller,
        )
    )

    return follow_ups


def _handle_station_charge(event: Event, state: GameState) -> list[Event]:
    """Handle STATION_CHARGE: add charge counters and fire threshold markers.

    Payload:
        object_id (str): Spacecraft/Planet receiving counters.
        amount (int):    Number of charge counters to add (0 is a no-op for
                         counter accumulation but still fires the event).
    """
    follow_ups: list[Event] = []
    if not isinstance(event.payload, dict):
        return follow_ups

    target_id = event.payload.get("object_id")
    amount = int(event.payload.get("amount", 0) or 0)
    obj = state.objects.get(target_id)
    if obj is None:
        return follow_ups

    before = get_station_charge(obj)

    # Emit a COUNTER_ADDED event so existing engine subsystems (e.g.
    # counter_added triggers, terrasymbiosis-style watchers) see the
    # accumulation through the normal pipeline.
    if amount > 0:
        follow_ups.append(
            Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    "object_id": obj.id,
                    "counter_type": CHARGE_COUNTER,
                    "amount": amount,
                },
                source=event.source or obj.id,
                controller=event.controller or obj.controller,
            )
        )

    after = before + max(0, amount)

    # Fire a THRESHOLD_REACHED marker carrying both totals so listeners can
    # check whether *their* threshold was just crossed.
    follow_ups.append(
        Event(
            type=EventType.STATION_THRESHOLD_REACHED,
            payload={
                "object_id": obj.id,
                "before": before,
                "after": after,
                "amount": amount,
            },
            source=event.source or obj.id,
            controller=event.controller or obj.controller,
        )
    )

    return follow_ups


def _handle_station_threshold_reached(event: Event, state: GameState) -> list[Event]:
    """No-op handler — STATION_THRESHOLD_REACHED is purely a marker event.

    Threshold-gated triggers attach REACT interceptors filtered on this event
    type and inspect ``payload['before']`` / ``payload['after']`` to decide
    whether their own threshold was just crossed.
    """
    return []


# =============================================================================
# Pipeline registration
# =============================================================================


STATION_EVENT_HANDLERS: dict[EventType, Any] = {
    EventType.STATION_ACTIVATE: _handle_station_activate,
    EventType.STATION_CHARGE: _handle_station_charge,
    EventType.STATION_THRESHOLD_REACHED: _handle_station_threshold_reached,
}


__all__ = [
    "CHARGE_COUNTER",
    "STATION_EVENT_HANDLERS",
    "add_station_charge",
    "get_station_charge",
    "is_stationed",
]
