"""
Duskmourn — Impending mechanic.

Reference card text:
    "Impending 4—{2}{W}{W} (If you cast this spell for its impending cost,
     it enters with four time counters and isn't a creature until the last
     is removed. At the beginning of your end step, remove a time counter
     from it.)
     Whenever this permanent enters or attacks, <effect>."

Mechanic semantics (CR 702.166-style alt cost, paired with a QUERY_TYPES
strip):

1. **Alt cost.** Adds a cast-for-impending option alongside the printed
   mana cost. Each card may be cast for its impending cost at most once
   per game (mirrors Plot/Warp): the alt-cost forks a separate cast path.
2. **Time counters on ETB.** When cast for the impending cost, the
   permanent enters with N "time" counters.
3. **Not a creature while counters > 0.** A QUERY_TYPES interceptor strips
   ``CardType.CREATURE`` from the object's effective types while time
   counters are positive. The card text says "isn't a creature" — the
   enchantment / other non-creature types remain.
4. **End step decrement.** At the beginning of the controller's end step,
   remove one time counter.
5. **Become a creature when counters reach 0.** Once the last counter is
   removed, the strip interceptor stops applying (since the gating
   predicate checks the live counter count), so the printed creature
   type is restored to the effective type set on the next QUERY_TYPES.
6. **Enter/attack triggers fire either way.** "Whenever this permanent
   enters or attacks" is checked against ZONE_CHANGE (enter) and
   ATTACK_DECLARED (attack) — both of which happen on the battlefield
   regardless of whether the object is currently a creature.

Architecture:
- ``parse_impending_cost(text)`` extracts ``(N, ManaCost)`` from card text.
- ``card_has_impending(card)`` / ``has_impending_been_used(card_def)`` /
  ``mark_impending_used`` mirror the warp tracking pattern.
- ``mark_impending_cast(obj)`` / ``is_impending_pending(obj)`` /
  ``clear_impending_pending(obj)`` mark an in-flight cast for the
  setup-interceptor side to read on ETB.
- ``is_impending_castable_from_hand`` gates the alt-cast surface.

The actual cast integration lives in ``src/engine/priority.py`` (a single
``hand:impending`` cast-option block, parallel to the Warp block).
"""

from __future__ import annotations

import re
from typing import Optional, Tuple, TYPE_CHECKING

from .types import (
    Event,
    EventType,
    GameObject,
    GameState,
    ZoneType,
)
from .mana import ManaCost

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from .types import CardDefinition


# =============================================================================
# Text parsing
# =============================================================================

# Match "Impending N—{...}{...}..." or "Impending N-{...}{...}..." (em/en/hyphen
# variants). N is a small integer (1-9). The reminder text is ignored.
_IMPENDING_COST_RE = re.compile(
    r"\bImpending\s+(\d+)\s*[—–\-]\s*((?:\{[^}]+\})+)",
    re.IGNORECASE,
)


def parse_impending_cost(text: Optional[str]) -> Optional[Tuple[int, ManaCost]]:
    """Return ``(time_counters, mana_cost)`` parsed from rules text, or None.

    Examples:
        "Impending 4—{2}{W}{W}"   -> (4, ManaCost({2}{W}{W}))
        "Impending 5-{1}{B}"      -> (5, ManaCost({1}{B}))
        "no impending here"       -> None
    """
    if not text:
        return None
    m = _IMPENDING_COST_RE.search(text)
    if not m:
        return None
    try:
        n = int(m.group(1))
    except (TypeError, ValueError):
        return None
    cost_str = m.group(2)
    try:
        cost = ManaCost.parse(cost_str)
    except Exception:
        return None
    return n, cost


def card_has_impending(card: object) -> bool:
    """Return True if the card definition (or game object) has impending."""
    card_def = getattr(card, "card_def", None) or card
    text = getattr(card_def, "text", None)
    return parse_impending_cost(text) is not None


def get_impending_cost(card: object) -> Optional[ManaCost]:
    """Return the parsed impending mana cost, or None."""
    parsed = _parse_from_card(card)
    if parsed is None:
        return None
    return parsed[1]


def get_impending_counter_count(card: object) -> Optional[int]:
    """Return N (the printed time counter count) for an impending card, or None."""
    parsed = _parse_from_card(card)
    if parsed is None:
        return None
    return parsed[0]


def _parse_from_card(card: object) -> Optional[Tuple[int, ManaCost]]:
    text = None
    card_def = getattr(card, "card_def", None)
    if card_def is not None:
        text = getattr(card_def, "text", None)
    if text is None:
        text = getattr(card, "text", None)
    return parse_impending_cost(text)


# =============================================================================
# Per-card impending-cast tracking
# =============================================================================
#
# Each CardDefinition can be impending-cast at most once per game (matches
# Warp). The flag lives on the shared CardDefinition; new games should call
# ``reset_impending_used`` if they reuse definitions across games.

_IMPENDING_USED_FLAG = "_impending_cast_used"


def has_impending_been_used(card_def: "CardDefinition") -> bool:
    return bool(getattr(card_def, _IMPENDING_USED_FLAG, False))


def mark_impending_used(card_def: "CardDefinition") -> None:
    try:
        setattr(card_def, _IMPENDING_USED_FLAG, True)
    except Exception:  # pragma: no cover - extremely defensive
        pass


def reset_impending_used(card_def: "CardDefinition") -> None:
    try:
        if hasattr(card_def, _IMPENDING_USED_FLAG):
            delattr(card_def, _IMPENDING_USED_FLAG)
    except Exception:  # pragma: no cover
        pass


# =============================================================================
# Per-object cast-time marker
# =============================================================================
#
# Set on the in-flight GameObject's state so the setup_interceptors call
# at ETB can detect "this card was cast for its impending cost" and
# install the time-counter / type-strip interceptors.

_IMPENDING_PENDING_FLAG = "_impending_pending"


def mark_impending_cast(obj: GameObject) -> None:
    """Mark the object as having been cast for its impending cost."""
    if obj is None or getattr(obj, "state", None) is None:
        return
    setattr(obj.state, _IMPENDING_PENDING_FLAG, True)


def is_impending_pending(obj: GameObject) -> bool:
    """Return True if this object is mid-cast for its impending cost."""
    if obj is None or getattr(obj, "state", None) is None:
        return False
    return bool(getattr(obj.state, _IMPENDING_PENDING_FLAG, False))


def clear_impending_pending(obj: GameObject) -> None:
    """Clear the pending flag (after ETB consumes it)."""
    if obj is None or getattr(obj, "state", None) is None:
        return
    if hasattr(obj.state, _IMPENDING_PENDING_FLAG):
        try:
            delattr(obj.state, _IMPENDING_PENDING_FLAG)
        except Exception:  # pragma: no cover
            setattr(obj.state, _IMPENDING_PENDING_FLAG, False)


# =============================================================================
# Cast-from-hand eligibility
# =============================================================================

def is_impending_castable_from_hand(
    card: GameObject,
    state: GameState,
    player_id: str,
) -> bool:
    """Return True if the player may currently cast ``card`` for impending.

    Checks:
      1. ``card`` has a parseable Impending cost.
      2. ``card`` is in ``player_id``'s hand.
      3. The card definition has not already been impending-cast this game.

    Mana payability and timing checks are handled by the standard cast
    machinery in ``priority.py``.
    """
    if card is None:
        return False
    if card.zone != ZoneType.HAND:
        return False
    if card.controller != player_id and card.owner != player_id:
        return False
    if not card_has_impending(card):
        return False
    card_def = getattr(card, "card_def", None)
    if card_def is None:
        return False
    if has_impending_been_used(card_def):
        return False
    return True


# =============================================================================
# Public API
# =============================================================================

__all__ = [
    "parse_impending_cost",
    "card_has_impending",
    "get_impending_cost",
    "get_impending_counter_count",
    "has_impending_been_used",
    "mark_impending_used",
    "reset_impending_used",
    "mark_impending_cast",
    "is_impending_pending",
    "clear_impending_pending",
    "is_impending_castable_from_hand",
]
