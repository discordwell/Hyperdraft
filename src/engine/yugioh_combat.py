"""
Yu-Gi-Oh! Combat Manager

Attack declaration, damage calculation, and battle resolution.

Battle scenarios:
- ATK vs ATK: Lower destroyed, difference = damage to that player. Equal = both destroyed.
- ATK vs DEF: ATK > DEF = defender destroyed (no damage). ATK < DEF = damage to attacker.
  ATK == DEF = no destruction, no damage.
- Direct Attack: Full ATK as damage to opponent.
- Link monsters: Always in ATK position, no DEF stat.

Battle sub-steps: Start -> Battle Step (declare) -> Damage Step -> Damage Calc -> End
"""

from typing import Optional, TYPE_CHECKING

from .types import (
    GameState, GameObject, Event, EventType, EventStatus, CardType, ZoneType
)
from .yugioh_types import YGOPosition

if TYPE_CHECKING:
    from .pipeline import EventPipeline


class YugiohCombatManager:
    """
    Yu-Gi-Oh! combat system.

    Key differences from MTG:
    - No blocking — attacker chooses target
    - Damage is calculated based on position (ATK vs ATK, ATK vs DEF)
    - Face-down monsters are flipped before damage
    - No combat damage to defending player from ATK vs DEF battles
    """

    def __init__(self, state: GameState):
        self.state = state
        self.pipeline: Optional['EventPipeline'] = None
        self.turn_manager = None
        self.priority_system = None

    def can_attack(self, monster_id: str) -> tuple[bool, str]:
        """Check if a monster can declare an attack."""
        monster = self.state.objects.get(monster_id)
        if not monster:
            return False, "Monster not found"
        if monster.zone != ZoneType.MONSTER_ZONE:
            return False, "Not on the field"
        if monster.state.ygo_position != 'face_up_atk':
            return False, "Not in ATK position"

        # Check if already attacked this turn
        turn_mgr = self.turn_manager
        if turn_mgr and hasattr(turn_mgr, 'ygo_turn_state'):
            attacks = turn_mgr.ygo_turn_state.attacks_declared.get(monster_id, 0)
            if attacks >= 1:
                return False, "Already attacked this turn"

        return True, ""

    def get_attack_targets(self, attacker_id: str, opponent_id: str) -> list[dict]:
        """Get valid attack targets for a monster."""
        targets = []
        attacker = self.state.objects.get(attacker_id)
        if not attacker:
            return targets

        # Check opponent's monsters
        opp_monsters = self._get_opponent_monsters(opponent_id)
        if not opp_monsters:
            # Can attack directly
            targets.append({
                'id': None,
                'type': 'direct',
                'name': 'Direct Attack',
            })
        else:
            for mon in opp_monsters:
                targets.append({
                    'id': mon.id,
                    'type': 'monster',
                    'name': mon.name if not mon.state.face_down else 'Set Monster',
                    'position': mon.state.ygo_position,
                })

        return targets

    def resolve_attack(self, attacker_pid: str, attacker_id: str,
                       target_id: Optional[str], opponent_id: str) -> list[Event]:
        """
        Resolve a complete attack from declaration through damage.
        Delegates to the turn manager's inline resolution for now.
        """
        events = []
        attacker = self.state.objects.get(attacker_id)
        if not attacker:
            return events

        # Validate attack
        can, reason = self.can_attack(attacker_id)
        if not can:
            return events

        atk_val = getattr(attacker.card_def, 'atk', 0) or 0

        # Direct attack
        if target_id is None:
            opp_monsters = self._get_opponent_monsters(opponent_id)
            if opp_monsters:
                return events  # Can't direct attack with monsters on field

            opponent = self.state.players.get(opponent_id)
            if opponent:
                opponent.lp = max(0, opponent.lp - atk_val)
                events.append(Event(
                    type=EventType.YGO_BATTLE_DAMAGE,
                    payload={
                        'player': opponent_id,
                        'amount': atk_val,
                        'source': attacker_id,
                        'direct': True,
                    }
                ))
                if opponent.lp <= 0:
                    opponent.has_lost = True

            self._track_attack(attacker_id)
            return events

        # Monster vs Monster
        defender = self.state.objects.get(target_id)
        if not defender:
            return events

        # Flip face-down before damage calc
        if defender.state.face_down:
            defender.state.face_down = False
            if defender.state.ygo_position == 'face_down_def':
                defender.state.ygo_position = 'face_up_def'
            events.append(Event(
                type=EventType.YGO_FLIP,
                payload={'card_id': target_id, 'card_name': defender.name}
            ))
            # Trigger flip effect
            if defender.card_def and getattr(defender.card_def, 'flip_effect', None):
                events.append(Event(
                    type=EventType.YGO_FLIP,
                    payload={'card_id': target_id, 'card_name': defender.name, 'is_flip_effect': True}
                ))

        def_atk = getattr(defender.card_def, 'atk', 0) or 0
        def_def = getattr(defender.card_def, 'def_val', 0) or 0

        if defender.state.ygo_position == 'face_up_atk':
            events.extend(self._resolve_atk_vs_atk(
                attacker_pid, attacker_id, atk_val,
                opponent_id, target_id, def_atk
            ))
        else:
            events.extend(self._resolve_atk_vs_def(
                attacker_pid, attacker_id, atk_val,
                opponent_id, target_id, def_def
            ))

        self._track_attack(attacker_id)

        # Check for game over
        for pid in [attacker_pid, opponent_id]:
            p = self.state.players.get(pid)
            if p and p.lp <= 0:
                p.has_lost = True

        return events

    def _resolve_atk_vs_atk(self, atk_pid: str, atk_id: str, atk_val: int,
                             def_pid: str, def_id: str, def_atk: int) -> list[Event]:
        """ATK position vs ATK position battle."""
        events = []
        if atk_val > def_atk:
            damage = atk_val - def_atk
            self._destroy_monster(def_id)
            opp = self.state.players.get(def_pid)
            if opp:
                opp.lp = max(0, opp.lp - damage)
            events.append(Event(
                type=EventType.YGO_BATTLE_DAMAGE,
                payload={'player': def_pid, 'amount': damage, 'source': atk_id}
            ))
        elif atk_val == def_atk:
            self._destroy_monster(atk_id)
            self._destroy_monster(def_id)
        else:
            damage = def_atk - atk_val
            self._destroy_monster(atk_id)
            p = self.state.players.get(atk_pid)
            if p:
                p.lp = max(0, p.lp - damage)
            events.append(Event(
                type=EventType.YGO_BATTLE_DAMAGE,
                payload={'player': atk_pid, 'amount': damage, 'source': def_id}
            ))
        return events

    def _resolve_atk_vs_def(self, atk_pid: str, atk_id: str, atk_val: int,
                             def_pid: str, def_id: str, def_val: int) -> list[Event]:
        """ATK position vs DEF position battle."""
        events = []
        if atk_val > def_val:
            self._destroy_monster(def_id)
            # No battle damage in ATK vs DEF
        elif atk_val == def_val:
            pass  # No destruction, no damage
        else:
            damage = def_val - atk_val
            p = self.state.players.get(atk_pid)
            if p:
                p.lp = max(0, p.lp - damage)
            events.append(Event(
                type=EventType.YGO_BATTLE_DAMAGE,
                payload={'player': atk_pid, 'amount': damage, 'source': def_id}
            ))
        return events

    def _destroy_monster(self, monster_id: str):
        """Destroy a monster — send to owner's GY."""
        obj = self.state.objects.get(monster_id)
        if not obj:
            return
        # Remove from monster zone
        for zone_key, zone in self.state.zones.items():
            if monster_id in zone.objects:
                for i, oid in enumerate(zone.objects):
                    if oid == monster_id:
                        zone.objects[i] = None
                        break
                while monster_id in zone.objects:
                    zone.objects.remove(monster_id)
                break

        # Add to graveyard
        gy_key = f"graveyard_{obj.owner}"
        gy = self.state.zones.get(gy_key)
        if gy:
            gy.objects.append(monster_id)
        obj.zone = ZoneType.GRAVEYARD
        obj.state.face_down = False
        obj.state.ygo_position = None

    def _get_opponent_monsters(self, opponent_id: str) -> list[GameObject]:
        """Get all monsters on the opponent's field."""
        zone_key = f"monster_zone_{opponent_id}"
        zone = self.state.zones.get(zone_key)
        if not zone:
            return []
        monsters = []
        for obj_id in zone.objects:
            if obj_id is None:
                continue
            obj = self.state.objects.get(obj_id)
            if obj:
                monsters.append(obj)
        return monsters

    def _track_attack(self, monster_id: str):
        """Track that a monster has declared an attack this turn."""
        turn_mgr = self.turn_manager
        if turn_mgr and hasattr(turn_mgr, 'ygo_turn_state'):
            attacks = turn_mgr.ygo_turn_state.attacks_declared
            attacks[monster_id] = attacks.get(monster_id, 0) + 1
