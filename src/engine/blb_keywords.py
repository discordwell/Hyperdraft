"""
Bloomburrow Keyword Frameworks: Valiant + Expend
================================================

This module provides per-card interceptor builders for the two keyword
abilities Bloomburrow introduces that the rest of the engine had not yet
exposed as first-class helpers:

* **Valiant** — "Whenever this creature becomes the target of a spell or
  ability you control for the first time each turn, [effect]."
  (CR 702.176, Bloomburrow.)

* **Expend N** — "Whenever you spend N or more mana on a spell, [effect]."
  Triggers when the cumulative mana paid for a single cast crosses the
  threshold N for that player on that turn. The engine already wires the
  threshold detection in ``priority.py`` via
  ``record_mana_spent_for_expend`` — see ``blb_mechanics.py``.

Both helpers are pure interceptor factories (no engine modifications). They
react to events the existing pipeline already emits:

* ``EventType.TARGET_CHOSEN`` — emitted in ``stack.py``
  ``build_target_chosen_events`` for both cast spells and activated/triggered
  abilities once their chosen targets are committed.
* ``EventType.EXPEND_4_REACHED`` / ``EventType.EXPEND_8_REACHED`` — emitted
  by ``record_mana_spent_for_expend`` after a successful ``pay_cost`` in the
  cast-spell handler.

The Valiant gating is per-creature, per-turn: ``state.turn_data`` carries a
``valiant_fired_this_turn`` dict keyed by ``(turn_number, object_id)`` so the
trigger fires at most once per creature per turn even if the creature is
targeted by several spells/abilities. The dict is automatically cleared at
turn boundaries because ``TurnManager._emit_turn_end`` calls
``state.turn_data.clear()``.

Re-exported from ``src/cards/interceptor_helpers.py`` (under the BLB-keywords
section near ``make_attack_trigger``) so card modules can write::

    from src.cards.interceptor_helpers import (
        make_valiant_trigger, make_expend_trigger,
    )

without importing engine-internal modules directly.
"""

from __future__ import annotations

from typing import Callable, Optional

from .types import (
    Event, EventType, GameObject, GameState,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    new_id,
)


# =============================================================================
# Valiant — TARGET_CHOSEN-driven trigger with once-per-turn gating
# =============================================================================

# Stored under state.turn_data; reset implicitly when the turn manager clears
# turn_data on TURN_END. The key is namespaced by (turn_number, object_id) so
# multiple Valiant creatures coexist without colliding, and the gate naturally
# resets between turns even if turn_data isn't fully cleared (defensive).
_VALIANT_FIRED_KEY = "valiant_fired_this_turn"


def _valiant_gate_key(obj_id: str, turn_number: int) -> tuple:
    return (turn_number, obj_id)


def make_valiant_trigger(
    source_obj: GameObject,
    effect_fn: Callable[[Event, GameState], list[Event]],
) -> Interceptor:
    """Build a Valiant trigger interceptor.

    Fires when ``source_obj`` becomes the target of a spell or ability whose
    controller equals ``source_obj.controller``. Fires at most once per turn
    per creature, regardless of how many spells/abilities target it.

    Args:
        source_obj: The creature with Valiant.
        effect_fn: ``(event, state) -> list[Event]`` — produces the
            triggered effect's events. Receives the ``TARGET_CHOSEN``
            event so callers can read e.g. the spell id from the payload.

    Reacts to: ``EventType.TARGET_CHOSEN``
    Priority: ``REACT``
    Duration: ``while_on_battlefield``
    """

    def valiant_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.TARGET_CHOSEN:
            return False
        if event.payload.get('target_id') != source_obj.id:
            return False
        # Source-spell/ability must be controlled by the Valiant creature's
        # controller. ``controller`` is set when ``build_target_chosen_events``
        # constructs the event from the casting player's stack item.
        if event.payload.get('controller') != source_obj.controller:
            return False
        # Once-per-turn gating
        gate = state.turn_data.setdefault(_VALIANT_FIRED_KEY, {})
        if not isinstance(gate, dict):
            gate = {}
            state.turn_data[_VALIANT_FIRED_KEY] = gate
        if gate.get(_valiant_gate_key(source_obj.id, state.turn_number)):
            return False
        return True

    def valiant_handler(event: Event, state: GameState) -> InterceptorResult:
        gate = state.turn_data.setdefault(_VALIANT_FIRED_KEY, {})
        if not isinstance(gate, dict):
            gate = {}
            state.turn_data[_VALIANT_FIRED_KEY] = gate
        gate[_valiant_gate_key(source_obj.id, state.turn_number)] = True
        try:
            new_events = effect_fn(event, state) or []
        except Exception:
            new_events = []
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=list(new_events),
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=valiant_filter,
        handler=valiant_handler,
        duration='while_on_battlefield',
    )


# =============================================================================
# Expend N — react to EXPEND_<N>_REACHED markers
# =============================================================================
#
# The engine emits EXPEND_4_REACHED / EXPEND_8_REACHED via
# ``record_mana_spent_for_expend`` (called from priority.py after every
# successful pay_cost). All printed Bloomburrow Expend cards use N=4 or N=8,
# matching the Magic 2024 rule for the keyword.
#
# Notes on mana counting (engine convention):
# * The threshold tracker accumulates ``mana_value`` of the paid cost plus the
#   spell's chosen ``x_value``. So a 2-mana spell with X=3 contributes 5
#   mana toward the per-turn total — it WILL trigger Expend 4.
# * The accumulator is per-player per-turn; once a threshold fires for a
#   player on a turn, it does not fire again that turn. This matches the
#   printed text "the first time you spend N or more mana".

_EXPEND_EVENT_TYPES: dict[int, EventType] = {
    4: EventType.EXPEND_4_REACHED,
    8: EventType.EXPEND_8_REACHED,
}


def make_expend_trigger(
    source_obj: GameObject,
    n: int,
    effect_fn: Callable[[Event, GameState], list[Event]],
) -> Interceptor:
    """Build an Expend N trigger interceptor.

    Fires the first time ``source_obj.controller`` crosses the cumulative
    mana-spent threshold ``n`` this turn. ``n`` must be 4 or 8 — those are
    the only thresholds Bloomburrow uses, and the only ones the engine
    surfaces as ``EXPEND_<N>_REACHED`` events.

    Args:
        source_obj: The permanent with the Expend N ability.
        n: Threshold (4 or 8).
        effect_fn: ``(event, state) -> list[Event]`` — produces the
            triggered effect's events.

    Reacts to: ``EventType.EXPEND_4_REACHED`` or ``EXPEND_8_REACHED``
    Priority: ``REACT``
    Duration: ``while_on_battlefield``

    Raises:
        ValueError: if ``n`` is not 4 or 8.
    """
    wanted_type = _EXPEND_EVENT_TYPES.get(int(n))
    if wanted_type is None:
        raise ValueError(
            f"Expend threshold must be 4 or 8 (got {n!r}). "
            "Bloomburrow only uses N=4 and N=8."
        )

    def expend_filter(event: Event, state: GameState) -> bool:
        if event.type != wanted_type:
            return False
        return event.payload.get('controller') == source_obj.controller

    def expend_handler(event: Event, state: GameState) -> InterceptorResult:
        try:
            new_events = effect_fn(event, state) or []
        except Exception:
            new_events = []
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=list(new_events),
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=expend_filter,
        handler=expend_handler,
        duration='while_on_battlefield',
    )


__all__ = [
    'make_valiant_trigger',
    'make_expend_trigger',
]
