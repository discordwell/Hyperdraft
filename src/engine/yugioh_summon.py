"""
Yu-Gi-Oh! Summoning Manager

Handles validation and execution for all summoning types:
- Fusion: Polymerization + named/generic materials from hand/field -> Extra Deck monster
- Synchro: 1 Tuner + non-Tuners on field, levels sum to Synchro level
- Xyz: 2+ same-level field monsters -> Xyz, materials become overlay units
- Pendulum: 2 Pendulum monsters in Pendulum Zones, summon from hand/face-up Extra Deck
- Link: Field monsters as materials, count = Link Rating
- Ritual: Ritual Spell + tributes with levels >= Ritual monster level
"""

from typing import Optional, TYPE_CHECKING

from .types import (
    GameState, GameObject, Event, EventType, CardType, ZoneType, new_id
)
from .yugioh_types import YGOMonsterType

if TYPE_CHECKING:
    from .yugioh_turn import YugiohTurnManager


class YugiohSummonManager:
    """
    Validates and executes Extra Deck and Ritual summoning procedures.
    """

    def __init__(self, state: GameState):
        self.state = state
        self.turn_manager: Optional['YugiohTurnManager'] = None

    # =========================================================================
    # Fusion Summon
    # =========================================================================

    def can_fusion_summon(self, player_id: str, fusion_id: str,
                          material_ids: list[str]) -> tuple[bool, str]:
        """Validate a Fusion Summon."""
        fusion = self.state.objects.get(fusion_id)
        if not fusion or not fusion.card_def:
            return False, "Fusion monster not found"

        if fusion.zone != ZoneType.EXTRA_DECK:
            return False, "Fusion monster must be in Extra Deck"

        if getattr(fusion.card_def, 'ygo_monster_type', None) != 'Fusion':
            return False, "Not a Fusion monster"

        # Check materials exist and are on field or in hand
        for mid in material_ids:
            mat = self.state.objects.get(mid)
            if not mat:
                return False, f"Material {mid} not found"
            if mat.zone not in (ZoneType.MONSTER_ZONE, ZoneType.HAND):
                return False, f"Material must be on field or in hand"
            if mat.controller != player_id and mat.zone == ZoneType.MONSTER_ZONE:
                return False, "Must control materials on field"

        if len(material_ids) < 2:
            return False, "Fusion requires at least 2 materials"

        return True, ""

    def fusion_summon(self, player_id: str, fusion_id: str,
                      material_ids: list[str]) -> list[Event]:
        """Execute a Fusion Summon."""
        events = []
        can, reason = self.can_fusion_summon(player_id, fusion_id, material_ids)
        if not can:
            return events

        # Send materials to GY
        for mid in material_ids:
            self._send_to_graveyard(mid)

        # Summon fusion monster from Extra Deck
        events.extend(self._summon_from_extra_deck(fusion_id, player_id, 'face_up_atk'))

        fusion = self.state.objects.get(fusion_id)
        events.append(Event(
            type=EventType.YGO_SPECIAL_SUMMON,
            payload={
                'player': player_id,
                'card_id': fusion_id,
                'card_name': fusion.name if fusion else '',
                'summon_type': 'fusion',
                'materials': material_ids,
            },
            source=fusion_id,
            controller=player_id,
        ))

        return events

    # =========================================================================
    # Synchro Summon
    # =========================================================================

    def can_synchro_summon(self, player_id: str, synchro_id: str,
                           material_ids: list[str]) -> tuple[bool, str]:
        """Validate a Synchro Summon."""
        synchro = self.state.objects.get(synchro_id)
        if not synchro or not synchro.card_def:
            return False, "Synchro monster not found"

        if synchro.zone != ZoneType.EXTRA_DECK:
            return False, "Synchro monster must be in Extra Deck"

        if getattr(synchro.card_def, 'ygo_monster_type', None) != 'Synchro':
            return False, "Not a Synchro monster"

        synchro_level = getattr(synchro.card_def, 'level', 0) or 0

        # Validate materials: all on field, exactly 1 Tuner, levels sum correctly
        tuner_count = 0
        level_sum = 0
        for mid in material_ids:
            mat = self.state.objects.get(mid)
            if not mat or not mat.card_def:
                return False, f"Material {mid} not found"
            if mat.zone != ZoneType.MONSTER_ZONE:
                return False, "Synchro materials must be on the field"
            if mat.controller != player_id:
                return False, "Must control all materials"

            mat_level = getattr(mat.card_def, 'level', 0) or 0
            level_sum += mat_level

            if getattr(mat.card_def, 'is_tuner', False):
                tuner_count += 1

        if tuner_count != 1:
            return False, f"Synchro Summon requires exactly 1 Tuner (got {tuner_count})"

        if level_sum != synchro_level:
            return False, f"Material levels ({level_sum}) must equal Synchro level ({synchro_level})"

        return True, ""

    def synchro_summon(self, player_id: str, synchro_id: str,
                       material_ids: list[str]) -> list[Event]:
        """Execute a Synchro Summon."""
        events = []
        can, reason = self.can_synchro_summon(player_id, synchro_id, material_ids)
        if not can:
            return events

        for mid in material_ids:
            self._send_to_graveyard(mid)

        events.extend(self._summon_from_extra_deck(synchro_id, player_id, 'face_up_atk'))

        synchro = self.state.objects.get(synchro_id)
        events.append(Event(
            type=EventType.YGO_SPECIAL_SUMMON,
            payload={
                'player': player_id,
                'card_id': synchro_id,
                'card_name': synchro.name if synchro else '',
                'summon_type': 'synchro',
                'materials': material_ids,
            },
            source=synchro_id,
            controller=player_id,
        ))

        return events

    # =========================================================================
    # Xyz Summon
    # =========================================================================

    def can_xyz_summon(self, player_id: str, xyz_id: str,
                       material_ids: list[str]) -> tuple[bool, str]:
        """Validate an Xyz Summon."""
        xyz = self.state.objects.get(xyz_id)
        if not xyz or not xyz.card_def:
            return False, "Xyz monster not found"

        if xyz.zone != ZoneType.EXTRA_DECK:
            return False, "Xyz monster must be in Extra Deck"

        if getattr(xyz.card_def, 'ygo_monster_type', None) != 'Xyz':
            return False, "Not an Xyz monster"

        xyz_rank = getattr(xyz.card_def, 'rank', 0) or 0

        if len(material_ids) < 2:
            return False, "Xyz Summon requires at least 2 materials"

        # All materials must be same level, on field
        expected_level = None
        for mid in material_ids:
            mat = self.state.objects.get(mid)
            if not mat or not mat.card_def:
                return False, f"Material {mid} not found"
            if mat.zone != ZoneType.MONSTER_ZONE:
                return False, "Xyz materials must be on the field"
            if mat.controller != player_id:
                return False, "Must control all materials"

            mat_level = getattr(mat.card_def, 'level', 0) or 0
            if expected_level is None:
                expected_level = mat_level
            elif mat_level != expected_level:
                return False, "All Xyz materials must be the same level"

        if expected_level != xyz_rank:
            return False, f"Material level ({expected_level}) must equal Xyz rank ({xyz_rank})"

        return True, ""

    def xyz_summon(self, player_id: str, xyz_id: str,
                   material_ids: list[str]) -> list[Event]:
        """Execute an Xyz Summon — materials become overlay units."""
        events = []
        can, reason = self.can_xyz_summon(player_id, xyz_id, material_ids)
        if not can:
            return events

        # Remove materials from field (but don't send to GY — they become overlay units)
        for mid in material_ids:
            self._remove_from_zone(mid)
            mat = self.state.objects.get(mid)
            if mat:
                mat.zone = ZoneType.EXTRA_DECK  # Mark as detached (overlay)

        # Summon Xyz monster
        events.extend(self._summon_from_extra_deck(xyz_id, player_id, 'face_up_atk'))

        # Attach overlay units
        xyz = self.state.objects.get(xyz_id)
        if xyz:
            xyz.state.overlay_units = list(material_ids)

        events.append(Event(
            type=EventType.YGO_SPECIAL_SUMMON,
            payload={
                'player': player_id,
                'card_id': xyz_id,
                'card_name': xyz.name if xyz else '',
                'summon_type': 'xyz',
                'materials': material_ids,
            },
            source=xyz_id,
            controller=player_id,
        ))

        return events

    def detach_material(self, xyz_id: str, count: int = 1) -> list[str]:
        """Detach overlay materials from an Xyz monster (send to GY)."""
        xyz = self.state.objects.get(xyz_id)
        if not xyz:
            return []

        detached = []
        for _ in range(min(count, len(xyz.state.overlay_units))):
            mat_id = xyz.state.overlay_units.pop(0)
            self._send_to_graveyard(mat_id)
            detached.append(mat_id)

        return detached

    # =========================================================================
    # Pendulum Summon
    # =========================================================================

    def can_pendulum_summon(self, player_id: str,
                            summon_ids: list[str]) -> tuple[bool, str]:
        """Validate a Pendulum Summon."""
        # Check Pendulum Zones
        pz_key = f"pendulum_zone_{player_id}"
        pz = self.state.zones.get(pz_key)
        if not pz or len([oid for oid in pz.objects if oid]) < 2:
            return False, "Need 2 Pendulum monsters in Pendulum Zones"

        # Get scales
        scales = []
        for oid in pz.objects:
            if oid is None:
                continue
            obj = self.state.objects.get(oid)
            if obj and obj.card_def:
                scale = getattr(obj.card_def, 'pendulum_scale', None)
                if scale is not None:
                    scales.append(scale)

        if len(scales) < 2:
            return False, "Both Pendulum Zones must have Pendulum monsters"

        low_scale = min(scales)
        high_scale = max(scales)

        if low_scale == high_scale:
            return False, "Pendulum Scales must be different"

        # Check summon targets
        for sid in summon_ids:
            obj = self.state.objects.get(sid)
            if not obj or not obj.card_def:
                return False, f"Card {sid} not found"
            # Must be in hand or face-up Extra Deck
            if obj.zone not in (ZoneType.HAND, ZoneType.EXTRA_DECK):
                return False, "Can only Pendulum Summon from hand or face-up Extra Deck"
            level = getattr(obj.card_def, 'level', 0) or 0
            if not (low_scale < level < high_scale):
                return False, f"Level {level} not between scales {low_scale} and {high_scale}"

        # Check monster zone space
        monsters = self._count_monsters(player_id)
        if monsters + len(summon_ids) > 5:
            return False, "Not enough Monster Zone space"

        return True, ""

    def pendulum_summon(self, player_id: str,
                        summon_ids: list[str]) -> list[Event]:
        """Execute a Pendulum Summon."""
        events = []
        can, reason = self.can_pendulum_summon(player_id, summon_ids)
        if not can:
            return events

        for sid in summon_ids:
            self._remove_from_zone(sid)
            slot = self._find_empty_monster_slot(player_id)
            if slot is not None:
                self._place_in_monster_zone(sid, player_id, slot)
                obj = self.state.objects.get(sid)
                if obj:
                    obj.state.ygo_position = 'face_up_atk'
                    obj.state.face_down = False

        events.append(Event(
            type=EventType.YGO_SPECIAL_SUMMON,
            payload={
                'player': player_id,
                'card_ids': summon_ids,
                'summon_type': 'pendulum',
            },
            controller=player_id,
        ))

        return events

    # =========================================================================
    # Link Summon
    # =========================================================================

    def can_link_summon(self, player_id: str, link_id: str,
                        material_ids: list[str]) -> tuple[bool, str]:
        """Validate a Link Summon."""
        link = self.state.objects.get(link_id)
        if not link or not link.card_def:
            return False, "Link monster not found"

        if link.zone != ZoneType.EXTRA_DECK:
            return False, "Link monster must be in Extra Deck"

        if getattr(link.card_def, 'ygo_monster_type', None) != 'Link':
            return False, "Not a Link monster"

        link_rating = getattr(link.card_def, 'link_rating', 0) or 0

        # Count material value (each monster = 1, or Link monster = its rating)
        material_value = 0
        for mid in material_ids:
            mat = self.state.objects.get(mid)
            if not mat or not mat.card_def:
                return False, f"Material {mid} not found"
            if mat.zone != ZoneType.MONSTER_ZONE:
                return False, "Link materials must be on the field"
            if mat.controller != player_id:
                return False, "Must control all materials"
            material_value += 1  # Each counts as 1 (simplified)

        if material_value != link_rating:
            return False, f"Material count ({material_value}) must equal Link Rating ({link_rating})"

        return True, ""

    def link_summon(self, player_id: str, link_id: str,
                    material_ids: list[str]) -> list[Event]:
        """Execute a Link Summon."""
        events = []
        can, reason = self.can_link_summon(player_id, link_id, material_ids)
        if not can:
            return events

        for mid in material_ids:
            self._send_to_graveyard(mid)

        # Link monsters always in face-up ATK (no DEF)
        events.extend(self._summon_from_extra_deck(link_id, player_id, 'face_up_atk'))

        link = self.state.objects.get(link_id)
        events.append(Event(
            type=EventType.YGO_SPECIAL_SUMMON,
            payload={
                'player': player_id,
                'card_id': link_id,
                'card_name': link.name if link else '',
                'summon_type': 'link',
                'materials': material_ids,
            },
            source=link_id,
            controller=player_id,
        ))

        return events

    # =========================================================================
    # Ritual Summon
    # =========================================================================

    def can_ritual_summon(self, player_id: str, ritual_id: str,
                          tribute_ids: list[str]) -> tuple[bool, str]:
        """Validate a Ritual Summon."""
        ritual = self.state.objects.get(ritual_id)
        if not ritual or not ritual.card_def:
            return False, "Ritual monster not found"

        if getattr(ritual.card_def, 'ygo_monster_type', None) != 'Ritual':
            return False, "Not a Ritual monster"

        if ritual.zone != ZoneType.HAND:
            return False, "Ritual monster must be in hand"

        ritual_level = getattr(ritual.card_def, 'level', 0) or 0

        # Tributes must have total levels >= ritual level
        total_levels = 0
        for tid in tribute_ids:
            trib = self.state.objects.get(tid)
            if not trib or not trib.card_def:
                return False, f"Tribute {tid} not found"
            if trib.zone not in (ZoneType.MONSTER_ZONE, ZoneType.HAND):
                return False, "Tributes must be on field or in hand"
            total_levels += getattr(trib.card_def, 'level', 0) or 0

        if total_levels < ritual_level:
            return False, f"Tribute levels ({total_levels}) must be >= Ritual level ({ritual_level})"

        return True, ""

    def ritual_summon(self, player_id: str, ritual_id: str,
                      tribute_ids: list[str]) -> list[Event]:
        """Execute a Ritual Summon."""
        events = []
        can, reason = self.can_ritual_summon(player_id, ritual_id, tribute_ids)
        if not can:
            return events

        for tid in tribute_ids:
            self._send_to_graveyard(tid)

        # Summon ritual monster from hand to field
        self._remove_from_zone(ritual_id)
        slot = self._find_empty_monster_slot(player_id)
        if slot is not None:
            self._place_in_monster_zone(ritual_id, player_id, slot)
            ritual = self.state.objects.get(ritual_id)
            if ritual:
                ritual.state.ygo_position = 'face_up_atk'
                ritual.state.face_down = False

        ritual = self.state.objects.get(ritual_id)
        events.append(Event(
            type=EventType.YGO_SPECIAL_SUMMON,
            payload={
                'player': player_id,
                'card_id': ritual_id,
                'card_name': ritual.name if ritual else '',
                'summon_type': 'ritual',
                'tributes': tribute_ids,
            },
            source=ritual_id,
            controller=player_id,
        ))

        return events

    # =========================================================================
    # Zone Helpers
    # =========================================================================

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
        obj.state.ygo_position = None

    def _remove_from_zone(self, card_id: str):
        """Remove a card from its current zone."""
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

    def _summon_from_extra_deck(self, card_id: str, player_id: str,
                                 position: str) -> list[Event]:
        """Move a card from Extra Deck to Monster Zone."""
        self._remove_from_zone(card_id)
        slot = self._find_empty_monster_slot(player_id)
        if slot is not None:
            self._place_in_monster_zone(card_id, player_id, slot)
            obj = self.state.objects.get(card_id)
            if obj:
                obj.state.ygo_position = position
                obj.state.face_down = False
                obj.controller = player_id
        return []

    def _place_in_monster_zone(self, card_id: str, player_id: str, slot: int):
        """Place a card in a monster zone slot."""
        zone_key = f"monster_zone_{player_id}"
        zone = self.state.zones.get(zone_key)
        if zone:
            while len(zone.objects) <= slot:
                zone.objects.append(None)
            zone.objects[slot] = card_id
        obj = self.state.objects.get(card_id)
        if obj:
            obj.zone = ZoneType.MONSTER_ZONE

    def _find_empty_monster_slot(self, player_id: str) -> Optional[int]:
        """Find an empty monster zone slot."""
        zone_key = f"monster_zone_{player_id}"
        zone = self.state.zones.get(zone_key)
        if not zone:
            return None
        for i in range(5):
            if i >= len(zone.objects) or zone.objects[i] is None:
                return i
        if len(zone.objects) < 5:
            return len(zone.objects)
        return None

    def _count_monsters(self, player_id: str) -> int:
        """Count monsters on a player's field."""
        zone_key = f"monster_zone_{player_id}"
        zone = self.state.zones.get(zone_key)
        if not zone:
            return 0
        return sum(1 for oid in zone.objects if oid is not None)
