"""
Yu-Gi-Oh! Spell/Trap Activation Logic

Spell types and their activation rules:
- Normal Spell (SS1): Hand only, Main Phase only, GY after resolve
- Quick-Play Spell (SS2): Hand on your turn, or set on either turn
- Continuous Spell (SS1): Stays on field while active
- Equip Spell (SS1): Target monster, stays on field, destroyed if target leaves
- Field Spell (SS1): 1 per player, replaces previous
- Ritual Spell (SS1): Part of Ritual Summon procedure

Trap types and their activation rules:
- Normal Trap (SS2): Must be set 1+ turns, GY after resolve
- Continuous Trap (SS2): Must be set 1+ turns, stays on field
- Counter Trap (SS3): Must be set 1+ turns, only SS3 can respond
"""

from typing import Optional, TYPE_CHECKING

from .types import (
    GameState, GameObject, Event, EventType, CardType, ZoneType
)

if TYPE_CHECKING:
    from .yugioh_chain import YugiohChainManager


class YugiohSpellTrapManager:
    """
    Manages Spell/Trap card activation and lifecycle.
    """

    def __init__(self, state: GameState):
        self.state = state
        self.chain_manager: Optional['YugiohChainManager'] = None

    def can_activate_spell(self, card_id: str, player_id: str,
                           is_main_phase: bool = True,
                           is_your_turn: bool = True) -> tuple[bool, str]:
        """Check if a spell card can be activated."""
        obj = self.state.objects.get(card_id)
        if not obj or not obj.card_def:
            return False, "Card not found"
        if obj.controller != player_id:
            return False, "Not your card"

        card_def = obj.card_def
        spell_type = getattr(card_def, 'ygo_spell_type', None)
        if CardType.YGO_SPELL not in obj.characteristics.types:
            return False, "Not a Spell card"

        if spell_type == "Quick-Play":
            # From hand: only on your turn
            if obj.zone == ZoneType.HAND and not is_your_turn:
                return False, "Quick-Play from hand only on your turn"
            # From field (set): either turn, but must be set 1+ turns
            if obj.zone == ZoneType.SPELL_TRAP_ZONE and obj.state.face_down:
                if obj.state.turns_set < 1:
                    return False, "Quick-Play must be set for at least 1 turn"
            return True, ""

        # All other spells: Main Phase only, from hand
        if not is_main_phase:
            return False, "Spells can only be activated during Main Phase"

        if spell_type == "Field":
            # Can activate from hand
            if obj.zone != ZoneType.HAND:
                return False, "Field Spell must be activated from hand"
            return True, ""

        if obj.zone == ZoneType.HAND:
            return True, ""
        if obj.zone == ZoneType.SPELL_TRAP_ZONE and obj.state.face_down:
            return True, ""

        return False, "Cannot activate from this zone"

    def can_activate_trap(self, card_id: str, player_id: str) -> tuple[bool, str]:
        """Check if a trap card can be activated."""
        obj = self.state.objects.get(card_id)
        if not obj or not obj.card_def:
            return False, "Card not found"
        if obj.controller != player_id:
            return False, "Not your card"

        if CardType.YGO_TRAP not in obj.characteristics.types:
            return False, "Not a Trap card"

        # Traps must be set face-down for at least 1 turn
        if obj.zone != ZoneType.SPELL_TRAP_ZONE:
            return False, "Trap must be set on the field"
        if not obj.state.face_down:
            return False, "Trap is already face-up"
        if obj.state.turns_set < 1:
            return False, "Trap must be set for at least 1 turn before activation"

        return True, ""

    def activate_spell(self, card_id: str, player_id: str,
                       targets: list = None) -> list[Event]:
        """Activate a spell card — resolve effect, handle lifecycle."""
        events = []
        obj = self.state.objects.get(card_id)
        if not obj or not obj.card_def:
            return events

        card_def = obj.card_def
        spell_type = getattr(card_def, 'ygo_spell_type', None)

        # Flip face-up if set
        if obj.state.face_down:
            obj.state.face_down = False

        events.append(Event(
            type=EventType.YGO_ACTIVATE_SPELL,
            payload={
                'player': player_id,
                'card_id': card_id,
                'card_name': obj.name,
                'spell_type': spell_type,
            },
            source=card_id,
            controller=player_id,
        ))

        # Resolve effect
        if card_def.resolve:
            resolve_event = Event(
                type=EventType.YGO_ACTIVATE_SPELL,
                payload={'card_id': card_id, 'player': player_id, 'targets': targets or []},
                source=card_id, controller=player_id
            )
            result = card_def.resolve(resolve_event, self.state)
            if result:
                events.extend(result)

        # Handle lifecycle based on spell type
        if spell_type in (None, "Normal", "Ritual", "Quick-Play"):
            # Goes to GY after resolution
            self._send_to_graveyard(card_id)
        elif spell_type == "Equip":
            # Stays on field — handled by equip logic
            pass
        elif spell_type == "Continuous":
            # Stays on field
            if obj.zone == ZoneType.HAND:
                self._move_to_spell_trap_zone(card_id, player_id)
        elif spell_type == "Field":
            self._activate_field_spell(card_id, player_id)

        return events

    def activate_trap(self, card_id: str, player_id: str,
                      targets: list = None) -> list[Event]:
        """Activate a trap card — resolve effect, handle lifecycle."""
        events = []
        obj = self.state.objects.get(card_id)
        if not obj or not obj.card_def:
            return events

        card_def = obj.card_def
        trap_type = getattr(card_def, 'ygo_trap_type', None)

        # Flip face-up
        obj.state.face_down = False

        events.append(Event(
            type=EventType.YGO_ACTIVATE_TRAP,
            payload={
                'player': player_id,
                'card_id': card_id,
                'card_name': obj.name,
                'trap_type': trap_type,
            },
            source=card_id,
            controller=player_id,
        ))

        # Resolve effect
        if card_def.resolve:
            resolve_event = Event(
                type=EventType.YGO_ACTIVATE_TRAP,
                payload={'card_id': card_id, 'player': player_id, 'targets': targets or []},
                source=card_id, controller=player_id
            )
            result = card_def.resolve(resolve_event, self.state)
            if result:
                events.extend(result)

        # Handle lifecycle
        if trap_type in (None, "Normal"):
            self._send_to_graveyard(card_id)
        elif trap_type == "Continuous":
            pass  # Stays on field
        elif trap_type == "Counter":
            self._send_to_graveyard(card_id)

        return events

    def _send_to_graveyard(self, card_id: str):
        """Send a card to its owner's graveyard."""
        obj = self.state.objects.get(card_id)
        if not obj:
            return
        self._remove_from_zone(card_id)
        gy_key = f"graveyard_{obj.owner}"
        gy = self.state.zones.get(gy_key)
        if gy:
            gy.objects.append(card_id)
        obj.zone = ZoneType.GRAVEYARD
        obj.state.face_down = False

    def _remove_from_zone(self, card_id: str):
        """Remove a card from whatever zone it's in."""
        for zone_key, zone in self.state.zones.items():
            if card_id in zone.objects:
                if 'monster_zone_' in zone_key or 'spell_trap_zone_' in zone_key:
                    for i, oid in enumerate(zone.objects):
                        if oid == card_id:
                            zone.objects[i] = None
                            break
                else:
                    while card_id in zone.objects:
                        zone.objects.remove(card_id)
                break

    def _move_to_spell_trap_zone(self, card_id: str, player_id: str):
        """Move a card from hand to a spell/trap zone slot."""
        self._remove_from_zone(card_id)
        zone_key = f"spell_trap_zone_{player_id}"
        zone = self.state.zones.get(zone_key)
        if zone:
            placed = False
            for i in range(5):
                if i >= len(zone.objects) or zone.objects[i] is None:
                    while len(zone.objects) <= i:
                        zone.objects.append(None)
                    zone.objects[i] = card_id
                    placed = True
                    break
            if not placed and len(zone.objects) < 5:
                zone.objects.append(card_id)
        obj = self.state.objects.get(card_id)
        if obj:
            obj.zone = ZoneType.SPELL_TRAP_ZONE

    def _activate_field_spell(self, card_id: str, player_id: str):
        """Activate a Field Spell — replace any existing one."""
        obj = self.state.objects.get(card_id)
        if not obj:
            return

        field_key = f"field_spell_zone_{player_id}"
        field_zone = self.state.zones.get(field_key)
        if field_zone:
            # Destroy existing field spell
            for old_id in list(field_zone.objects):
                if old_id and old_id != card_id:
                    self._send_to_graveyard(old_id)
            field_zone.objects.clear()

        self._remove_from_zone(card_id)
        if field_zone:
            field_zone.objects.append(card_id)
        obj.zone = ZoneType.FIELD_SPELL_ZONE
        obj.state.face_down = False
