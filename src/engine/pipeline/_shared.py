"""
Shared helpers used across multiple pipeline handler modules.

Lives inside the pipeline package so handlers can import from a single place
without circular dependencies.
"""

from typing import Optional

from ..types import (
    Event, EventType, GameObject, GameState, ZoneType,
)


# =============================================================================
# Zone / object list helpers
# =============================================================================

def _remove_object_from_all_zones(object_id: str, state: GameState) -> None:
    """Remove an object id from every zone list (robust against zone corruption)."""
    for zone in state.zones.values():
        while object_id in zone.objects:
            zone.objects.remove(object_id)


# =============================================================================
# Keyword-counter bookkeeping (shared by counters.py and zone.py)
# =============================================================================

_KEYWORD_COUNTER_TYPES: set[str] = {
    # MTG keyword counters (702.* / 122.*). We model these as real keyword
    # abilities for compatibility with older card logic that checks
    # `obj.characteristics.keywords` directly.
    "deathtouch",
    "double strike",
    "first strike",
    "flying",
    "haste",
    "hexproof",
    "indestructible",
    "lifelink",
    "menace",
    "reach",
    "trample",
    "vigilance",
}


def _sync_keyword_counter_abilities(obj: GameObject) -> None:
    """Mirror keyword counters into `obj.characteristics.abilities`."""
    abilities = obj.characteristics.abilities or []

    # Remove previously injected keyword-counter abilities.
    abilities = [
        a for a in abilities
        if not (isinstance(a, dict) and a.get("_from_counter") is True)
    ]

    # Add abilities for any active keyword counters.
    for kw in sorted(_KEYWORD_COUNTER_TYPES):
        if obj.state.counters.get(kw, 0) > 0:
            abilities.append({"keyword": kw, "_from_counter": True})

    obj.characteristics.abilities = abilities


# =============================================================================
# Turn-scoped permission helpers (cast-from-graveyard, exile-instead-of-gy, etc.)
# =============================================================================

def _turn_permission_active(expires_turn: Optional[int], state: GameState) -> bool:
    """Return True if an inclusive-turn permission is active."""
    if expires_turn is None:
        return True
    return state.turn_number <= int(expires_turn)


def _merge_turn_permission(existing: Optional[int], new: Optional[int]) -> Optional[int]:
    """Combine two inclusive-turn permissions (None = forever)."""
    if existing is None or new is None:
        return None
    return max(int(existing), int(new))


def _set_turn_permission(mapping: dict[str, Optional[int]], player_id: str, expires_turn: Optional[int]) -> None:
    """
    Extend/overwrite a player's permission in-place.

    - If the player already has a "forever" permission (None), keep it.
    - Otherwise, take the max(expiry).
    """
    if not player_id:
        return
    if player_id in mapping:
        mapping[player_id] = _merge_turn_permission(mapping.get(player_id), expires_turn)
    else:
        mapping[player_id] = expires_turn


def _exile_instead_of_graveyard_active(player_id: str, state: GameState) -> bool:
    mapping = getattr(state, "exile_instead_of_graveyard_until", {}) or {}
    if player_id not in mapping:
        return False
    return _turn_permission_active(mapping.get(player_id), state)


def _parse_duration_turns(duration: object, state: GameState) -> Optional[int]:
    """
    Convert common duration strings into an inclusive turn number.

    Returns:
        int: last turn number the permission is valid for (inclusive)
        None: if unknown/unbounded
    """
    if not isinstance(duration, str):
        return None

    d = duration.strip().lower().replace(" ", "_")
    if d in {"", "forever"}:
        return None

    # "next_end_step" is still this turn.
    if d in {"next_end_step", "end_of_turn", "end_of_this_turn", "this_turn", "until_end_of_turn", "until_eot", "eot"}:
        return state.turn_number

    if d in {"end_of_next_turn", "until_end_of_next_turn", "next_turn"}:
        return state.turn_number + 1

    return None
