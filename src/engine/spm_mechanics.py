"""
Marvel's Spider-Man (SPM) set mechanics.

Implements the two SPM set-defining alternative-cost mechanics:

* **Web-slinging {cost}** — Alt cast cost from hand. The controller may cast
  the spell for {cost} if they also return a tapped creature they control to
  its owner's hand. Sorcery speed unless the spell has flash (the engine's
  normal timing checks already enforce this).

* **Mayhem {cost}** — Alt cast cost from graveyard if the card was discarded
  this turn (by its controller). Sorcery speed only. Tracking lives in
  ``state.turn_data['discarded_card_ids']`` (cleared each turn) so other
  cards can observe "was this card discarded this turn".

Both mechanics already have *cost extraction* support inside priority.py
(via ``_get_mayhem_cost`` and friends). This module adds:

* Public regex helpers so other code (helpers, tests) can detect these costs
  without duplicating regex.
* A small registration helper that books the alt costs onto each
  ``CardDefinition`` (used by interceptor helpers).
* A discard tracker: ``track_discard(state, object_id)`` which records that
  a particular card was discarded this turn.

The actual cast resolution still flows through the normal priority/stack
path — these helpers are book-keeping that lets card-side ``setup_interceptors``
react to "this was cast via web-slinging" or "this was discarded this turn"
without having to re-parse rules text at runtime.
"""

from __future__ import annotations

import re
from typing import Optional, Iterable, TYPE_CHECKING

from .mana import ManaCost

if TYPE_CHECKING:  # pragma: no cover
    from .types import GameState


# ---------------------------------------------------------------------------
# Cost extraction (regex)
# ---------------------------------------------------------------------------

# Centralised so card-side helpers don't have to duplicate them.
_WEBSLING_COST_RE = re.compile(
    r"web[-\s]?slinging\s*[—-]?\s*((?:\{[^}]+\})+)",
    re.IGNORECASE,
)
_MAYHEM_COST_RE = re.compile(
    r"mayhem\s*[—-]?\s*((?:\{[^}]+\})+)",
    re.IGNORECASE,
)


def _card_text(card_or_def) -> str:
    """Return the rules text for a CardDefinition or a GameObject's card_def."""
    if card_or_def is None:
        return ""
    # GameObject case: indirect via .card_def
    sub = getattr(card_or_def, "card_def", None)
    if sub is not None:
        text = getattr(sub, "text", "") or ""
        if text:
            return text
    # CardDefinition case (or anything else with a .text attribute)
    text = getattr(card_or_def, "text", "") or ""
    return text


def parse_web_slinging_cost(card_or_def) -> Optional[ManaCost]:
    """Return the parsed web-slinging cost from rules text, or ``None``."""
    text = _card_text(card_or_def)
    if not text:
        return None
    m = _WEBSLING_COST_RE.search(text)
    if not m:
        return None
    try:
        return ManaCost.parse(m.group(1))
    except Exception:
        return None


def parse_mayhem_cost(card_or_def) -> Optional[ManaCost]:
    """Return the parsed mayhem cost from rules text, or ``None``."""
    text = _card_text(card_or_def)
    if not text:
        return None
    m = _MAYHEM_COST_RE.search(text)
    if not m:
        return None
    try:
        return ManaCost.parse(m.group(1))
    except Exception:
        return None


def has_web_slinging(card_or_def) -> bool:
    return parse_web_slinging_cost(card_or_def) is not None


def has_mayhem(card_or_def) -> bool:
    return parse_mayhem_cost(card_or_def) is not None


# ---------------------------------------------------------------------------
# CardDefinition metadata stamping
# ---------------------------------------------------------------------------

def register_web_slinging(card_def, alt_cost) -> None:
    """Stamp ``alt_cost`` onto ``card_def`` so card-side helpers can read it back.

    Uses dynamic attributes so we don't have to extend ``CardDefinition``
    itself. Mirrors the convention used by HS dynamic_cost (see MEMORY.md).
    """
    if isinstance(alt_cost, str):
        try:
            alt_cost = ManaCost.parse(alt_cost)
        except Exception:
            return
    setattr(card_def, "web_slinging_cost", alt_cost)


def register_mayhem(card_def, mayhem_cost) -> None:
    """Stamp the mayhem alt cost onto ``card_def``."""
    if isinstance(mayhem_cost, str):
        try:
            mayhem_cost = ManaCost.parse(mayhem_cost)
        except Exception:
            return
    setattr(card_def, "mayhem_cost", mayhem_cost)


def get_web_slinging_cost(card_def) -> Optional[ManaCost]:
    cost = getattr(card_def, "web_slinging_cost", None)
    if cost is None:
        cost = parse_web_slinging_cost(card_def)
    return cost


def get_mayhem_cost(card_def) -> Optional[ManaCost]:
    cost = getattr(card_def, "mayhem_cost", None)
    if cost is None:
        cost = parse_mayhem_cost(card_def)
    return cost


# ---------------------------------------------------------------------------
# Per-turn discard tracking (Mayhem)
# ---------------------------------------------------------------------------

DISCARDED_KEY = "discarded_card_ids"
WEBSLING_CAST_KEY = "web_slinging_cast_ids"
WEBSLING_RETURNED_MV_KEY = "web_slinging_returned_mv_by_id"


def _get_discarded_set(state: "GameState") -> set:
    """Return the (mutable) set of object ids discarded this turn.

    ``turn_data`` is cleared by the turn manager at turn boundaries
    (see ``TurnManager._reset_turn_state``).
    """
    bucket = state.turn_data.get(DISCARDED_KEY)
    if not isinstance(bucket, set):
        bucket = set()
        state.turn_data[DISCARDED_KEY] = bucket
    return bucket


def track_discard(state: "GameState", object_id: str) -> None:
    """Mark ``object_id`` as having been discarded this turn."""
    if not object_id:
        return
    _get_discarded_set(state).add(object_id)


def was_discarded_this_turn(state: "GameState", object_id: Optional[str]) -> bool:
    if not object_id:
        return False
    return object_id in _get_discarded_set(state)


def discarded_this_turn(state: "GameState") -> Iterable[str]:
    """Iterate over object ids that were discarded this turn (snapshot copy)."""
    return tuple(_get_discarded_set(state))


# ---------------------------------------------------------------------------
# Web-slinging cast tracking (so ETB triggers can ask "was I web-slung?")
# ---------------------------------------------------------------------------

def _get_websling_cast_set(state: "GameState") -> set:
    bucket = state.turn_data.get(WEBSLING_CAST_KEY)
    if not isinstance(bucket, set):
        bucket = set()
        state.turn_data[WEBSLING_CAST_KEY] = bucket
    return bucket


def _get_websling_mv_map(state: "GameState") -> dict:
    bucket = state.turn_data.get(WEBSLING_RETURNED_MV_KEY)
    if not isinstance(bucket, dict):
        bucket = {}
        state.turn_data[WEBSLING_RETURNED_MV_KEY] = bucket
    return bucket


def track_web_slinging_cast(state: "GameState", object_id: str, returned_mv: int = 0) -> None:
    """Record that ``object_id`` was cast via web-slinging this turn."""
    if not object_id:
        return
    _get_websling_cast_set(state).add(object_id)
    _get_websling_mv_map(state)[object_id] = int(returned_mv or 0)


def was_web_slung_this_turn(state: "GameState", object_id: Optional[str]) -> bool:
    if not object_id:
        return False
    return object_id in _get_websling_cast_set(state)


def web_slinging_returned_mv_for(state: "GameState", object_id: Optional[str]) -> int:
    if not object_id:
        return 0
    return int(_get_websling_mv_map(state).get(object_id, 0))


# ---------------------------------------------------------------------------
# Web-slinging / Mayhem cast detection (event payload helpers)
# ---------------------------------------------------------------------------

def is_web_slinging_cast(event) -> bool:
    """Return True iff the given CAST/SPELL_CAST event used web-slinging.

    Convention: the priority system tags the cast event with
    ``payload['web_slinging']=True`` and (optionally) ``payload['returned_card_id']``
    plus ``payload['web_slinging_returned_mv']`` when the alternate cost is paid.
    """
    if event is None:
        return False
    payload = getattr(event, "payload", None) or {}
    return bool(payload.get("web_slinging"))


def web_slinging_returned_mv(event) -> int:
    """Return the mana value of the creature returned to pay the web-slinging cost."""
    if event is None:
        return 0
    payload = getattr(event, "payload", None) or {}
    try:
        return int(payload.get("web_slinging_returned_mv", 0) or 0)
    except (TypeError, ValueError):
        return 0


def is_mayhem_cast(event) -> bool:
    """Return True iff the given CAST/SPELL_CAST event used mayhem."""
    if event is None:
        return False
    payload = getattr(event, "payload", None) or {}
    return bool(payload.get("mayhem"))


__all__ = [
    "DISCARDED_KEY",
    "WEBSLING_CAST_KEY",
    "WEBSLING_RETURNED_MV_KEY",
    "parse_web_slinging_cost",
    "parse_mayhem_cost",
    "has_web_slinging",
    "has_mayhem",
    "register_web_slinging",
    "register_mayhem",
    "get_web_slinging_cost",
    "get_mayhem_cost",
    "track_discard",
    "was_discarded_this_turn",
    "discarded_this_turn",
    "track_web_slinging_cast",
    "was_web_slung_this_turn",
    "web_slinging_returned_mv_for",
    "is_web_slinging_cast",
    "web_slinging_returned_mv",
    "is_mayhem_cast",
]
