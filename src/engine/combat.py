"""
Hyperdraft Combat Manager

Handles the combat phase:
- Declare Attackers
- Declare Blockers
- Combat Damage (with first strike split)
- End of Combat

Uses simplified Foundations-era rules where damage assignment
no longer requires ordering blockers first.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional, TYPE_CHECKING
from enum import Enum, auto

from .types import (
    GameState, GameObject, Event, EventType, CardType, ZoneType
)
from .queries import get_power, get_toughness, is_creature, has_ability

if TYPE_CHECKING:
    from .turn import TurnManager, Step
    from .priority import PrioritySystem
    from .pipeline import EventPipeline


@dataclass
class AttackDeclaration:
    """Declaration of an attacking creature."""
    attacker_id: str
    defending_player_id: str  # Or planeswalker ID
    is_attacking_planeswalker: bool = False


@dataclass
class BlockDeclaration:
    """Declaration of a blocking creature."""
    blocker_id: str
    blocking_attacker_id: str


@dataclass
class DamageAssignment:
    """How a creature assigns its combat damage."""
    source_id: str
    assignments: list[tuple[str, int]]  # (target_id, amount)


@dataclass
class CombatState:
    """State of the current combat."""
    attackers: list[AttackDeclaration] = field(default_factory=list)
    blockers: list[BlockDeclaration] = field(default_factory=list)

    # Which attackers are blocked
    blocked_attackers: set[str] = field(default_factory=set)

    # Damage assignments
    attacker_damage: dict[str, DamageAssignment] = field(default_factory=dict)
    blocker_damage: dict[str, DamageAssignment] = field(default_factory=dict)

    # Tracking
    combat_damage_dealt: bool = False
    first_strike_damage_dealt: bool = False


class CombatManager:
    """
    Manages combat phase mechanics.
    """

    def __init__(self, state: GameState):
        self.state = state
        self.combat_state = CombatState()

        # Other systems (set by Game class)
        self.turn_manager: Optional['TurnManager'] = None
        self.priority_system: Optional['PrioritySystem'] = None
        self.pipeline: Optional['EventPipeline'] = None

        # Callbacks for getting player decisions
        self.get_attack_declarations: Optional[Callable[[str, list[str]], list[AttackDeclaration]]] = None
        self.get_block_declarations: Optional[Callable[[str, list[AttackDeclaration], list[str]], list[BlockDeclaration]]] = None
        self.get_damage_assignment: Optional[Callable[[str, list[str], int], list[tuple[str, int]]]] = None

    def reset_combat(self) -> None:
        """Reset combat state for a new combat phase."""
        self.combat_state = CombatState()
        # Clear any combat flags from the previous combat.
        battlefield = self.state.zones.get('battlefield')
        if battlefield:
            for obj_id in list(battlefield.objects):
                obj = self.state.objects.get(obj_id)
                if obj:
                    obj.state.attacking = False
                    obj.state.blocking = False

    async def run_combat(self) -> list[Event]:
        """
        Run the complete combat phase.

        Returns all events generated.
        """
        events = []
        self.reset_combat()

        # Declare Attackers Step
        events.extend(await self._declare_attackers_step())

        # If no attackers, skip rest of combat
        if not self.combat_state.attackers:
            return events

        # Declare Blockers Step
        events.extend(await self._declare_blockers_step())

        # Combat Damage Step(s)
        events.extend(await self._combat_damage_step())

        return events

    async def _declare_attackers_step(self) -> list[Event]:
        """
        Declare Attackers Step.

        Active player declares all attackers simultaneously.
        """
        events = []

        if self.turn_manager:
            from .turn import Step
            self.turn_manager._set_step(Step.DECLARE_ATTACKERS)

        active_player = self._get_active_player()
        if not active_player:
            return events

        # Get legal attackers
        legal_attackers = self._get_legal_attackers(active_player)

        if not legal_attackers:
            return events

        # Get attack declarations from player/AI
        declarations = await self._get_player_attacks(active_player, legal_attackers)

        if not declarations:
            return events

        # Process declarations
        for decl in declarations:
            # Validate attacker
            if not self._can_attack(decl.attacker_id, active_player):
                continue

            self.combat_state.attackers.append(decl)

            # Tap attacking creature (unless vigilance)
            attacker = self.state.objects.get(decl.attacker_id)
            if attacker and not has_ability(attacker, 'vigilance', self.state):
                attacker.state.attacking = True
                tap_event = Event(
                    type=EventType.TAP,
                    payload={'object_id': decl.attacker_id}
                )
                self._emit_event(tap_event)
                events.append(tap_event)
            elif attacker:
                attacker.state.attacking = True

            # Emit attack declared event
            attack_event = Event(
                type=EventType.ATTACK_DECLARED,
                payload={
                    'attacker_id': decl.attacker_id,
                    'defending_player': decl.defending_player_id,
                    'is_attacking_planeswalker': decl.is_attacking_planeswalker
                }
            )
            self._emit_event(attack_event)
            events.append(attack_event)

        # Priority after attackers declared
        if self.priority_system:
            await self.priority_system.run_priority_loop()

        return events

    async def _declare_blockers_step(self) -> list[Event]:
        """
        Declare Blockers Step.

        Defending player(s) declare blockers for attackers.
        """
        events = []

        if self.turn_manager:
            from .turn import Step
            self.turn_manager._set_step(Step.DECLARE_BLOCKERS)

        # Get defending players
        defending_players = self._get_defending_players()

        for defender_id in defending_players:
            # Get attackers this player needs to block
            relevant_attackers = [
                a for a in self.combat_state.attackers
                if a.defending_player_id == defender_id
            ]

            if not relevant_attackers:
                continue

            # Get legal blockers
            legal_blockers = self._get_legal_blockers(defender_id)

            # Get block declarations from player/AI
            declarations = await self._get_player_blocks(
                defender_id, relevant_attackers, legal_blockers
            )

            # Process declarations
            for decl in declarations:
                if not self._can_block(decl.blocker_id, decl.blocking_attacker_id, defender_id):
                    continue

                self.combat_state.blockers.append(decl)
                self.combat_state.blocked_attackers.add(decl.blocking_attacker_id)
                blocker = self.state.objects.get(decl.blocker_id)
                if blocker:
                    blocker.state.blocking = True

                events.append(Event(
                    type=EventType.BLOCK_DECLARED,
                    payload={
                        'blocker_id': decl.blocker_id,
                        'attacker_id': decl.blocking_attacker_id
                    }
                ))

        # Priority after blockers declared
        if self.priority_system:
            await self.priority_system.run_priority_loop()

        return events

    async def _combat_damage_step(self) -> list[Event]:
        """
        Combat Damage Step.

        Handle first strike damage, then regular damage.
        """
        events = []

        # Check for first strike / double strike creatures
        first_strikers = self._get_first_strike_creatures()
        regular_creatures = self._get_regular_damage_creatures()

        # First Strike Damage (if any first strikers)
        if first_strikers:
            if self.turn_manager:
                from .turn import Step
                self.turn_manager._set_step(Step.FIRST_STRIKE_DAMAGE)

            events.extend(await self._deal_combat_damage(first_strikers, is_first_strike=True))
            self.combat_state.first_strike_damage_dealt = True

            # Check state-based actions (creatures may die)
            # Priority after first strike damage
            if self.priority_system:
                await self.priority_system.run_priority_loop()

        # Regular Combat Damage
        if self.turn_manager:
            from .turn import Step
            self.turn_manager._set_step(Step.COMBAT_DAMAGE)

        # Include double strikers again
        double_strikers = [
            cid for cid in first_strikers
            if cid in self.state.objects and
            has_ability(self.state.objects[cid], 'double_strike', self.state)
        ]
        all_regular = list(set(regular_creatures + double_strikers))

        events.extend(await self._deal_combat_damage(all_regular, is_first_strike=False))
        self.combat_state.combat_damage_dealt = True

        # Priority after combat damage
        if self.priority_system:
            await self.priority_system.run_priority_loop()

        return events

    def _emit_event(self, event: Event) -> None:
        """Emit an event through the pipeline if available."""
        if self.pipeline:
            self.pipeline.emit(event)

    async def _deal_combat_damage(
        self,
        creature_ids: list[str],
        is_first_strike: bool
    ) -> list[Event]:
        """
        Deal combat damage for a set of creatures.
        """
        events = []

        # Attackers deal damage
        for attacker_decl in self.combat_state.attackers:
            if attacker_decl.attacker_id not in creature_ids:
                continue

            attacker = self.state.objects.get(attacker_decl.attacker_id)
            if not attacker or attacker.zone != ZoneType.BATTLEFIELD:
                continue

            power = get_power(attacker, self.state)
            if power <= 0:
                continue

            if attacker_decl.attacker_id in self.combat_state.blocked_attackers:
                # Blocked - damage blockers
                blockers = [
                    b.blocker_id for b in self.combat_state.blockers
                    if b.blocking_attacker_id == attacker_decl.attacker_id
                ]

                if blockers:
                    # Get damage assignment
                    assignments = await self._get_attacker_damage_assignment(
                        attacker_decl.attacker_id, blockers, power
                    )

                    for target_id, amount in assignments:
                        if amount > 0:
                            event = Event(
                                type=EventType.DAMAGE,
                                payload={
                                    'target': target_id,
                                    'amount': amount,
                                    'source': attacker_decl.attacker_id,
                                    'is_combat': True
                                },
                                source=attacker_decl.attacker_id
                            )
                            self._emit_event(event)
                            events.append(event)

                    # Trample - excess damage to defending player
                    if has_ability(attacker, 'trample', self.state):
                        total_assigned = sum(a[1] for a in assignments)
                        excess = power - total_assigned
                        if excess > 0:
                            event = Event(
                                type=EventType.DAMAGE,
                                payload={
                                    'target': attacker_decl.defending_player_id,
                                    'amount': excess,
                                    'source': attacker_decl.attacker_id,
                                    'is_combat': True
                                },
                                source=attacker_decl.attacker_id
                            )
                            self._emit_event(event)
                            events.append(event)
            else:
                # Unblocked - damage defending player/planeswalker
                event = Event(
                    type=EventType.DAMAGE,
                    payload={
                        'target': attacker_decl.defending_player_id,
                        'amount': power,
                        'source': attacker_decl.attacker_id,
                        'is_combat': True
                    },
                    source=attacker_decl.attacker_id
                )
                self._emit_event(event)
                events.append(event)

        # Blockers deal damage
        for block_decl in self.combat_state.blockers:
            if block_decl.blocker_id not in creature_ids:
                continue

            blocker = self.state.objects.get(block_decl.blocker_id)
            if not blocker or blocker.zone != ZoneType.BATTLEFIELD:
                continue

            power = get_power(blocker, self.state)
            if power <= 0:
                continue

            # Blocker deals damage to the attacker it's blocking
            attacker = self.state.objects.get(block_decl.blocking_attacker_id)
            if attacker and attacker.zone == ZoneType.BATTLEFIELD:
                event = Event(
                    type=EventType.DAMAGE,
                    payload={
                        'target': block_decl.blocking_attacker_id,
                        'amount': power,
                        'source': block_decl.blocker_id,
                        'is_combat': True
                    },
                    source=block_decl.blocker_id
                )
                self._emit_event(event)
                events.append(event)

        return events

    def _get_legal_attackers(self, player_id: str) -> list[str]:
        """Get all creatures that can legally attack."""
        attackers = []
        battlefield = self.state.zones.get('battlefield')

        if not battlefield:
            return attackers

        for obj_id in battlefield.objects:
            obj = self.state.objects.get(obj_id)
            if not obj:
                continue

            if obj.controller != player_id:
                continue

            if not is_creature(obj, self.state):
                continue

            if self._can_attack(obj_id, player_id):
                attackers.append(obj_id)

        return attackers

    def _can_attack(self, creature_id: str, controller_id: str) -> bool:
        """Check if a creature can attack."""
        creature = self.state.objects.get(creature_id)
        if not creature:
            return False

        # Must be a creature
        if not is_creature(creature, self.state):
            return False

        # Must be controlled by attacking player
        if creature.controller != controller_id:
            return False

        # Can't be tapped (unless vigilance and already attacking somehow)
        if creature.state.tapped:
            return False

        # Check summoning sickness (can't attack unless haste)
        # Simplified: check if creature entered this turn
        if creature.entered_zone_at == self.state.timestamp:
            if not has_ability(creature, 'haste', self.state):
                return False

        # Check for "can't attack" abilities
        if has_ability(creature, 'defender', self.state):
            return False

        if has_ability(creature, 'cant_attack', self.state):
            return False

        return True

    def _get_legal_blockers(self, player_id: str) -> list[str]:
        """Get all creatures that can legally block."""
        blockers = []
        battlefield = self.state.zones.get('battlefield')

        if not battlefield:
            return blockers

        for obj_id in battlefield.objects:
            obj = self.state.objects.get(obj_id)
            if not obj:
                continue

            if obj.controller != player_id:
                continue

            if not is_creature(obj, self.state):
                continue

            # Must be untapped to block
            if obj.state.tapped:
                continue

            # Check for "can't block" abilities
            if has_ability(obj, 'cant_block', self.state):
                continue

            blockers.append(obj_id)

        return blockers

    def _can_block(
        self,
        blocker_id: str,
        attacker_id: str,
        defender_id: str
    ) -> bool:
        """Check if a creature can block a specific attacker."""
        blocker = self.state.objects.get(blocker_id)
        attacker = self.state.objects.get(attacker_id)

        if not blocker or not attacker:
            return False

        # Must be controlled by defending player
        if blocker.controller != defender_id:
            return False

        # Must be untapped
        if blocker.state.tapped:
            return False

        # Check evasion abilities
        if has_ability(attacker, 'flying', self.state):
            # Can only be blocked by flying or reach
            if not (has_ability(blocker, 'flying', self.state) or
                    has_ability(blocker, 'reach', self.state)):
                return False

        if has_ability(attacker, 'menace', self.state):
            # Must be blocked by two or more creatures
            current_blockers = [
                b for b in self.combat_state.blockers
                if b.blocking_attacker_id == attacker_id
            ]
            # This is simplified - proper menace check would need all blockers
            pass

        if has_ability(attacker, 'shadow', self.state):
            # Can only be blocked by shadow creatures
            if not has_ability(blocker, 'shadow', self.state):
                return False

        # Check protection
        # (Would check if blocker has protection from attacker's qualities)

        return True

    def _get_first_strike_creatures(self) -> list[str]:
        """Get creatures with first strike or double strike."""
        creatures = []

        for decl in self.combat_state.attackers:
            creature = self.state.objects.get(decl.attacker_id)
            if creature and creature.zone == ZoneType.BATTLEFIELD:
                if (has_ability(creature, 'first_strike', self.state) or
                    has_ability(creature, 'double_strike', self.state)):
                    creatures.append(decl.attacker_id)

        for decl in self.combat_state.blockers:
            creature = self.state.objects.get(decl.blocker_id)
            if creature and creature.zone == ZoneType.BATTLEFIELD:
                if (has_ability(creature, 'first_strike', self.state) or
                    has_ability(creature, 'double_strike', self.state)):
                    if decl.blocker_id not in creatures:
                        creatures.append(decl.blocker_id)

        return creatures

    def _get_regular_damage_creatures(self) -> list[str]:
        """Get creatures that deal damage in regular combat damage step."""
        creatures = []

        for decl in self.combat_state.attackers:
            creature = self.state.objects.get(decl.attacker_id)
            if creature and creature.zone == ZoneType.BATTLEFIELD:
                # First strike only creatures don't deal regular damage
                if not has_ability(creature, 'first_strike', self.state):
                    creatures.append(decl.attacker_id)
                elif has_ability(creature, 'double_strike', self.state):
                    # Double strike deals in both steps
                    creatures.append(decl.attacker_id)

        for decl in self.combat_state.blockers:
            creature = self.state.objects.get(decl.blocker_id)
            if creature and creature.zone == ZoneType.BATTLEFIELD:
                if not has_ability(creature, 'first_strike', self.state):
                    if decl.blocker_id not in creatures:
                        creatures.append(decl.blocker_id)
                elif has_ability(creature, 'double_strike', self.state):
                    if decl.blocker_id not in creatures:
                        creatures.append(decl.blocker_id)

        return creatures

    def _get_active_player(self) -> Optional[str]:
        """Get the active player (attacker)."""
        if self.turn_manager:
            return self.turn_manager.active_player
        return list(self.state.players.keys())[0] if self.state.players else None

    def _get_defending_players(self) -> list[str]:
        """Get defending player(s)."""
        active = self._get_active_player()
        return [pid for pid in self.state.players.keys() if pid != active]

    async def _get_player_attacks(
        self,
        player_id: str,
        legal_attackers: list[str]
    ) -> list[AttackDeclaration]:
        """Get attack declarations from a player."""
        if self.get_attack_declarations:
            return self.get_attack_declarations(player_id, legal_attackers)

        # Default: no attacks
        return []

    async def _get_player_blocks(
        self,
        player_id: str,
        attackers: list[AttackDeclaration],
        legal_blockers: list[str]
    ) -> list[BlockDeclaration]:
        """Get block declarations from a player."""
        if self.get_block_declarations:
            return self.get_block_declarations(player_id, attackers, legal_blockers)

        # Default: no blocks
        return []

    async def _get_attacker_damage_assignment(
        self,
        attacker_id: str,
        blocker_ids: list[str],
        power: int
    ) -> list[tuple[str, int]]:
        """Get damage assignment for an attacker vs blockers."""
        if len(blocker_ids) == 1:
            # Single blocker gets all damage
            return [(blocker_ids[0], power)]

        if self.get_damage_assignment:
            return self.get_damage_assignment(attacker_id, blocker_ids, power)

        # Default: split evenly (simplified)
        per_blocker = power // len(blocker_ids)
        remainder = power % len(blocker_ids)

        assignments = [(bid, per_blocker) for bid in blocker_ids]
        if remainder > 0:
            # Give remainder to first blocker
            assignments[0] = (assignments[0][0], assignments[0][1] + remainder)

        return assignments

    # Combat query helpers

    def is_attacking(self, creature_id: str) -> bool:
        """Check if a creature is attacking."""
        return any(a.attacker_id == creature_id for a in self.combat_state.attackers)

    def is_blocking(self, creature_id: str) -> bool:
        """Check if a creature is blocking."""
        return any(b.blocker_id == creature_id for b in self.combat_state.blockers)

    def is_blocked(self, attacker_id: str) -> bool:
        """Check if an attacker is blocked."""
        return attacker_id in self.combat_state.blocked_attackers

    def get_blockers_of(self, attacker_id: str) -> list[str]:
        """Get all blockers blocking a specific attacker."""
        return [
            b.blocker_id for b in self.combat_state.blockers
            if b.blocking_attacker_id == attacker_id
        ]

    def get_blocked_by(self, blocker_id: str) -> Optional[str]:
        """Get the attacker a blocker is blocking."""
        for b in self.combat_state.blockers:
            if b.blocker_id == blocker_id:
                return b.blocking_attacker_id
        return None
