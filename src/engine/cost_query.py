"""
Cost Query System

Computes the effective mana cost of a spell, applying any registered
cost-reduction effects. This is the canonical place the priority/casting
system asks "what does this card actually cost to cast right now?"

Design
------
Cost reductions are registered as QUERY_COST interceptors. When a player
attempts to (or considers being able to) cast a spell, the priority system
calls ``get_effective_mana_cost(card, player_id, state, base_cost=...)``,
which:

  1. Starts with ``base_cost`` (defaulting to the card's printed mana cost).
  2. Builds a synthetic QUERY_COST event whose payload carries the card and
     player context plus a running ``reduction`` counter.
  3. Iterates every QUERY-priority interceptor whose filter accepts the
     synthetic event. Each interceptor's handler returns a TRANSFORM result
     whose new payload contains an updated ``reduction`` value.
  4. Applies the accumulated reduction to the generic component of the
     mana cost. Coloured/colourless/snow/hybrid/phyrexian symbols are
     never reduced (so {2}{R}{R} reduced by {3} stays at {R}{R}, never
     below the coloured-mana floor). Generic itself is clamped at 0.

The interceptor model gives us:

  - Multiple reductions stack additively (each interceptor adds to the
    running ``reduction`` total).
  - Reductions only apply while the source object is on the battlefield
    (the pipeline's ``_get_interceptors`` gating already enforces this for
    ``while_on_battlefield`` interceptors).
  - Conditional reductions ("...if you control a Wizard") are expressed as
    a predicate inside the filter or by computing ``amount`` dynamically.

Out of scope for this module:

  - Cost *increases* ("costs {1} more").
  - Choice-driven reductions (tiered costs at cast time).
  - Reducing colored mana symbols.
"""

from __future__ import annotations

from typing import Optional

from .types import (
    Event, EventType, GameObject, GameState,
    Interceptor, InterceptorPriority, ZoneType,
)
from .mana import ManaCost


# Sentinel payload key used by reduction interceptors to publish how much
# the cost has been reduced so far (in generic mana symbols).
REDUCTION_KEY = "reduction"

# Other payload keys the synthetic QUERY_COST event exposes to filters/handlers:
#   - card_id          str   -- the casting card's object id
#   - card             GameObject (the casting card)
#   - player_id        str   -- the casting player
#   - base_cost        ManaCost (printed/original; never mutated)


def _make_query_event(card: GameObject, player_id: str, base_cost: ManaCost) -> Event:
    """Build the synthetic QUERY_COST event consumed by reduction interceptors."""
    return Event(
        type=EventType.QUERY_COST,
        payload={
            "card_id": card.id,
            "card": card,
            "player_id": player_id,
            "base_cost": base_cost,
            REDUCTION_KEY: 0,
        },
        controller=player_id,
    )


def _apply_reduction(cost: ManaCost, reduction: int) -> ManaCost:
    """
    Reduce the generic portion of ``cost`` by ``reduction``, clamped at 0.

    Coloured, colourless ({C}), snow ({S}), hybrid, and Phyrexian costs are
    left untouched - matching MTG's rule that cost reductions can't reduce
    coloured or otherwise specific costs unless the reduction text says so.
    """
    if reduction <= 0:
        return cost
    new_generic = max(0, cost.generic - int(reduction))
    if new_generic == cost.generic:
        return cost
    return ManaCost(
        white=cost.white,
        blue=cost.blue,
        black=cost.black,
        red=cost.red,
        green=cost.green,
        colorless=cost.colorless,
        generic=new_generic,
        snow=cost.snow,
        x_count=cost.x_count,
        hybrid=list(cost.hybrid),
        phyrexian=list(cost.phyrexian),
    )


def get_effective_mana_cost(
    card: GameObject,
    player_id: str,
    state: GameState,
    base_cost: Optional[ManaCost] = None,
) -> ManaCost:
    """
    Compute the effective mana cost of casting ``card`` from ``player_id``'s
    perspective, applying every registered cost-reduction interceptor.

    Args:
        card: the casting object (typically in HAND, but may be GRAVEYARD/EXILE
              for alt-cast mechanics like flashback).
        player_id: the would-be caster.
        state: the current game state.
        base_cost: starting cost, defaulting to the card's printed mana cost.
                   Pass an alt cost (e.g. a flashback cost) when you need to
                   reduce that instead.

    Returns:
        A new ManaCost reflecting all applied reductions. Generic is clamped
        to 0; coloured/colourless/snow/hybrid/phyrexian costs are unchanged.
    """
    if base_cost is None:
        base_cost = ManaCost.parse(card.characteristics.mana_cost or "")

    # Build a synthetic event and walk every QUERY-priority interceptor whose
    # filter accepts it. This mirrors the pattern in queries.py for QUERY_POWER
    # / QUERY_TOUGHNESS, but lives here because cost queries fire from priority
    # / casting code rather than from object reads.
    event = _make_query_event(card, player_id, base_cost)

    # Sort by timestamp for deterministic ordering (matches queries.py).
    interceptors = sorted(
        [
            i for i in state.interceptors.values()
            if i.priority == InterceptorPriority.QUERY
            and _is_cost_query(i, event, state)
        ],
        key=lambda i: i.timestamp,
    )

    total_reduction = 0
    for interceptor in interceptors:
        # Each handler receives an event whose REDUCTION_KEY shows the running
        # total. Handlers add to it and emit a TRANSFORM result with the new
        # payload. We prefer this additive shape (rather than each handler
        # returning a delta) because it leaves the door open for handlers that
        # cap further reductions, etc.
        ev = event.copy()
        ev.payload[REDUCTION_KEY] = total_reduction
        result = interceptor.handler(ev, state)
        if result and result.transformed_event:
            new_total = result.transformed_event.payload.get(REDUCTION_KEY, total_reduction)
            try:
                total_reduction = int(new_total)
            except (TypeError, ValueError):
                continue

    return _apply_reduction(base_cost, total_reduction)


def _is_cost_query(interceptor: Interceptor, event: Event, state: GameState) -> bool:
    """Run the interceptor's filter against the synthetic event safely."""
    try:
        return bool(interceptor.filter(event, state))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Compatibility shim: external code may want to ask "is the source still on
# the battlefield?" (a common precondition for cost-reduction triggers).
# Most reduction interceptors carry duration='while_on_battlefield', and the
# pipeline's _get_interceptors already gates those - but cost queries don't
# go through the pipeline (they're a synthesised read), so we expose a small
# helper here for filters that want an explicit check.
# ---------------------------------------------------------------------------

def source_on_battlefield(source_id: str, state: GameState) -> bool:
    """True if the named object is currently on the battlefield."""
    obj = state.objects.get(source_id)
    return bool(obj and obj.zone == ZoneType.BATTLEFIELD)
