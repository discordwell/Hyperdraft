"""Phase 5D: Rooms / Doors mechanic (Duskmourn).

A Room is an enchantment with two halves separated by ``//``. Each half is
a "door" with its own name, mana cost, and effect. When a Room is cast, the
player picks one door to unlock — its mana cost is paid as the spell cost,
and that door is unlocked on ETB. A separate sorcery-speed activated
ability ``{other_door_cost}: Unlock the other door`` lets the player
unlock the second door later.

Engine integration:
- ``UNLOCK_DOOR`` event already exists in ``types.py``.
- The pipeline handler in this module mutates ``obj.state.unlocked_doors``
  (a list of door names) so cards can branch on which doors are unlocked.
- "When you unlock this door, ..." triggers are registered via
  ``make_etb_trigger``-style filters listening for the UNLOCK_DOOR event
  on this object.

Pragmatic shortcuts (engine gaps tracked):
- Cast-time door-selection UI not yet wired. The Room's setup function
  unlocks Door 1 on ETB by default. Future work: surface the cast option.
- Continuous statics on a single door (e.g. "While Hospital Room is
  unlocked, your attackers get +1/+1") not implemented unless explicitly
  wired by the card.
"""
from __future__ import annotations

from typing import Optional

from .types import (
    Event,
    EventType,
    GameObject,
    GameState,
)


def _handle_unlock_door(event: Event, state: GameState) -> list[Event]:
    """Resolve an UNLOCK_DOOR event by marking the door unlocked.

    Payload:
        object_id: the Room being mutated
        door_name: the name of the door that was unlocked
    """
    obj_id = event.payload.get("object_id")
    door_name = event.payload.get("door_name")
    if not obj_id or not door_name:
        return []
    obj = state.objects.get(obj_id)
    if obj is None:
        return []
    if not isinstance(getattr(obj.state, "unlocked_doors", None), list):
        obj.state.unlocked_doors = []
    if door_name not in obj.state.unlocked_doors:
        obj.state.unlocked_doors.append(door_name)
    return []


ROOMS_EVENT_HANDLERS = {
    EventType.UNLOCK_DOOR: _handle_unlock_door,
}


__all__ = [
    "ROOMS_EVENT_HANDLERS",
]
