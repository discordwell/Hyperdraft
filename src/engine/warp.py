"""
Edge of Eternities — Warp mechanic.

Cards with Warp may be cast from your hand for their warp cost (an alternate
cost). The resulting permanent is exiled at the beginning of the next end
step. Each card may only be warp-cast once per game; if the warp-cast copy
is exiled and then later cast again from exile, that subsequent cast pays
the printed mana cost (not the warp cost).

Reference card text:
    "Warp {2}{R}{R} (You may cast this card from your hand for its warp
     cost. Exile this creature at the beginning of the next end step,
     then you may cast it from exile on a later turn.)"

Architecture:
- ``parse_warp_cost(text)`` extracts the warp cost from rules text.
- ``card_has_warp(card)`` and ``has_warp_been_used(card)`` are introspection
  helpers used by the priority system to decide whether a "Cast for warp"
  action should be surfaced.
- ``mark_warp_cast(state, obj)`` records the warp-cast on the in-flight
  spell so the cast site can later set up the end-step exile.
- ``register_warp_end_step_exile(state, obj, controller_id)`` registers a
  one-shot interceptor that exiles the object at the next end step if it
  is still on the battlefield.

The actual integration into the casting pipeline lives in
``src/engine/priority.py`` (it adds a Warp ``CastOption`` for cards in
hand).  This module is intentionally framework-agnostic so that tests can
exercise the helpers directly.
"""

from __future__ import annotations

import re
from typing import Optional, TYPE_CHECKING

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
from .mana import ManaCost

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from .types import CardDefinition


# =============================================================================
# Text parsing
# =============================================================================

# Match "Warp {2}{R}{R}" — a Warp keyword followed by one or more {...} symbols.
# The reminder text in parentheses (if present) is ignored by this regex.
_WARP_COST_RE = re.compile(
    r"\bWarp\s*((?:\{[^}]+\})+)",
    re.IGNORECASE,
)


def parse_warp_cost(text: Optional[str]) -> Optional[ManaCost]:
    """Return the parsed warp cost from a card's rules text, or None.

    Examples:
        "Warp {2}{R}{R}"       -> ManaCost({2}{R}{R})
        "Warp {W}"             -> ManaCost({W})
        "Warp {X}{G}"          -> ManaCost({X}{G})
        "no warp here"         -> None
    """
    if not text:
        return None
    m = _WARP_COST_RE.search(text)
    if not m:
        return None
    cost_str = m.group(1)
    try:
        return ManaCost.parse(cost_str)
    except Exception:
        return None


def card_has_warp(card: object) -> bool:
    """Return True if the card definition (or game object) has a printed warp cost."""
    text: Optional[str] = None
    card_def = getattr(card, "card_def", None) or card
    text = getattr(card_def, "text", None)
    return parse_warp_cost(text) is not None


# =============================================================================
# Per-card warp-cast tracking
# =============================================================================

# Each card definition can be warp-cast at most once per game. We track this
# by setting a flag directly on the CardDefinition (which is a shared template
# across all copies). Per-game resets are handled by Game.start_game() callers
# elsewhere if needed; in practice, a printed card is exactly one CardDefinition
# instance per game, so this is safe for normal play sessions.

_WARP_USED_FLAG = "_warp_cast_used"


def has_warp_been_used(card_def: "CardDefinition") -> bool:
    """Return True if this card definition has already been warp-cast."""
    return bool(getattr(card_def, _WARP_USED_FLAG, False))


def mark_warp_used(card_def: "CardDefinition") -> None:
    """Record that this card definition has been warp-cast.

    After this is called, ``has_warp_been_used`` will return True until the
    flag is cleared (e.g. by ``reset_warp_used``). Casting from the warp
    exile pile uses the printed mana cost, not the warp cost, so a single
    "warp use" is what we track here.
    """
    try:
        setattr(card_def, _WARP_USED_FLAG, True)
    except Exception:  # pragma: no cover - extremely defensive
        pass


def reset_warp_used(card_def: "CardDefinition") -> None:
    """Clear the per-card warp-cast flag (mainly for tests / new games)."""
    try:
        if hasattr(card_def, _WARP_USED_FLAG):
            delattr(card_def, _WARP_USED_FLAG)
    except Exception:  # pragma: no cover
        pass


# =============================================================================
# Cast-time bookkeeping (used by the priority system)
# =============================================================================

# Marker attribute on GameObject.state. When set, the object was cast for
# its warp cost and should be exiled at the next end step.
_WARP_PENDING_FLAG = "_warp_pending_exile"


def mark_warp_cast(obj: GameObject) -> None:
    """Mark this object as having been warp-cast (for end-step exile)."""
    if obj is None or getattr(obj, "state", None) is None:
        return
    setattr(obj.state, _WARP_PENDING_FLAG, True)


def is_warp_pending(obj: GameObject) -> bool:
    """Return True if this object was warp-cast and is awaiting end-step exile."""
    if obj is None or getattr(obj, "state", None) is None:
        return False
    return bool(getattr(obj.state, _WARP_PENDING_FLAG, False))


def clear_warp_pending(obj: GameObject) -> None:
    """Clear the warp-pending flag (after exile fires or if cast is countered)."""
    if obj is None or getattr(obj, "state", None) is None:
        return
    if hasattr(obj.state, _WARP_PENDING_FLAG):
        try:
            delattr(obj.state, _WARP_PENDING_FLAG)
        except Exception:  # pragma: no cover
            setattr(obj.state, _WARP_PENDING_FLAG, False)


# =============================================================================
# End-step exile interceptor
# =============================================================================

def register_warp_end_step_exile(
    state: GameState,
    obj: GameObject,
    controller_id: str,
) -> Interceptor:
    """Register a one-shot interceptor that exiles ``obj`` at the next end step.

    The interceptor fires once on PHASE_START with phase == 'end_step'. If
    the object is still on the battlefield, it emits an EXILE event; if not
    (it died, was bounced, etc.), the trigger does nothing — matching the
    actual card behavior.

    The interceptor is registered against ``obj`` so it is cleaned up when
    the object's interceptors are cleaned up.
    """
    obj_id = obj.id

    def _filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        return event.payload.get("phase") == "end_step"

    def _handler(event: Event, st: GameState) -> InterceptorResult:
        current = st.objects.get(obj_id)
        if current is None or current.zone != ZoneType.BATTLEFIELD:
            # Already left the battlefield — nothing to do.
            return InterceptorResult(action=InterceptorAction.PASS)

        clear_warp_pending(current)

        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.WARP_EXILE,
                    payload={"object_id": obj_id, "reason": "warp_end_step"},
                    source=obj_id,
                    controller=controller_id,
                ),
                Event(
                    type=EventType.EXILE,
                    payload={"object_id": obj_id, "reason": "warp_end_step"},
                    source=obj_id,
                    controller=controller_id,
                ),
            ],
        )

    interceptor = Interceptor(
        id=new_id(),
        source=obj_id,
        controller=controller_id,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration="forever",
        uses_remaining=1,
    )
    interceptor.timestamp = state.next_timestamp()
    state.interceptors[interceptor.id] = interceptor
    if interceptor.id not in obj.interceptor_ids:
        obj.interceptor_ids.append(interceptor.id)

    # Emit a marker event so triggers on warp-cast can react.
    # (Not pushed through the pipeline here; callers may emit if desired.)
    return interceptor


def schedule_warp_exile_for_object(
    state: GameState,
    obj: GameObject,
    controller_id: str,
) -> Optional[Interceptor]:
    """Public entry point: if ``obj`` was warp-cast, set up its end-step exile.

    Idempotent: returns the existing/new interceptor or None if the object
    is not warp-pending.
    """
    if obj is None:
        return None
    if not is_warp_pending(obj):
        return None
    # Avoid double-registration if this is called multiple times.
    for iid in list(obj.interceptor_ids):
        existing = state.interceptors.get(iid)
        if existing is None:
            continue
        if getattr(existing, "_warp_marker", False):
            return existing
    interceptor = register_warp_end_step_exile(state, obj, controller_id)
    setattr(interceptor, "_warp_marker", True)
    return interceptor


# =============================================================================
# Cast-from-hand eligibility
# =============================================================================

def is_warp_castable_from_hand(
    card: GameObject,
    state: GameState,
    player_id: str,
) -> bool:
    """Return True if the player may currently cast ``card`` for its warp cost.

    Checks:
      1. ``card`` has a parseable Warp cost.
      2. ``card`` is in ``player_id``'s hand.
      3. The card definition has not already been warp-cast this game.

    Mana payability and timing checks are handled by the standard cast
    machinery in ``priority.py``.
    """
    if card is None:
        return False
    if card.zone != ZoneType.HAND:
        return False
    if card.controller != player_id and card.owner != player_id:
        return False
    if not card_has_warp(card):
        return False
    card_def = getattr(card, "card_def", None)
    if card_def is None:
        return False
    if has_warp_been_used(card_def):
        return False
    return True


def get_warp_cost(card: GameObject) -> Optional[ManaCost]:
    """Return the parsed warp cost for ``card``, or None if it has no Warp."""
    text = None
    card_def = getattr(card, "card_def", None)
    if card_def is not None:
        text = getattr(card_def, "text", None)
    if text is None:
        text = getattr(card, "text", None)
    return parse_warp_cost(text)
