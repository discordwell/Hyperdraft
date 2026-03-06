"""
Pokemon Combat Manager

Attack declaration, damage calculation (weakness/resistance), and knockout handling.

Damage pipeline:
1. Base damage (from attack definition + coin flips + conditionals)
2. Attacking-side modifiers (tools, abilities, effects)
3. Weakness (x2 if defender weak to attacker's type)
4. Resistance (-30 if defender resistant)
5. Defending-side modifiers (damage reduction)
6. Floor at 0
7. Apply as damage counters (each 10 HP = 1 counter)
"""

import random
from typing import Optional, TYPE_CHECKING

from .types import (
    GameState, GameObject, Event, EventType, EventStatus, CardType, ZoneType
)

if TYPE_CHECKING:
    from .pipeline import EventPipeline


class PokemonCombatManager:
    """
    Pokemon TCG combat system.

    Key differences from MTG/HS:
    - Only the Active Pokemon can attack
    - Attacks target the opponent's Active Pokemon (usually)
    - Damage calculation includes weakness/resistance
    - Damage is tracked as counters (each = 10 HP)
    - KO'd Pokemon go to discard, opponent takes prize cards
    """

    def __init__(self, state: GameState):
        self.state = state
        self.pipeline: Optional['EventPipeline'] = None
        # Wired by Game class
        self.turn_manager = None
        self.priority_system = None

    def can_attack(self, pokemon_id: str) -> tuple[bool, str]:
        """Check if Active Pokemon can attack."""
        pokemon = self.state.objects.get(pokemon_id)
        if not pokemon:
            return False, "Pokemon not found"
        if CardType.POKEMON not in pokemon.characteristics.types:
            return False, "Not a Pokemon"
        if pokemon.zone != ZoneType.ACTIVE_SPOT:
            return False, "Not in Active Spot"

        # Status condition checks
        if 'asleep' in pokemon.state.status_conditions:
            return False, "Pokemon is Asleep"
        if 'paralyzed' in pokemon.state.status_conditions:
            return False, "Pokemon is Paralyzed"

        # Must have energy for at least one attack
        attacks = self.get_available_attacks(pokemon_id)
        if not attacks:
            return False, "No attacks with sufficient energy"

        return True, ""

    def get_available_attacks(self, pokemon_id: str) -> list[dict]:
        """Return attacks the Pokemon can currently use (has energy for)."""
        pokemon = self.state.objects.get(pokemon_id)
        if not pokemon or not pokemon.card_def:
            return []

        from .pokemon_energy import PokemonEnergySystem
        energy_system = PokemonEnergySystem(self.state)

        available = []
        for i, attack in enumerate(pokemon.card_def.attacks):
            cost = attack.get('cost', [])
            if energy_system.can_pay_cost(pokemon_id, cost):
                available.append({**attack, '_index': i})
        return available

    def declare_attack(self, attacker_id: str, attack_index: int,
                       targets: list[str] = None) -> list[Event]:
        """Execute an attack. Returns events for the full attack resolution."""
        events = []
        attacker = self.state.objects.get(attacker_id)
        if not attacker or not attacker.card_def:
            return events

        attacks = attacker.card_def.attacks
        if attack_index < 0 or attack_index >= len(attacks):
            return events

        attack = attacks[attack_index]

        # Confusion check: flip coin, tails = 3 damage counters to self
        if 'confused' in attacker.state.status_conditions:
            flip = random.choice(['heads', 'tails'])
            flip_event = Event(
                type=EventType.PKM_COIN_FLIP,
                payload={'result': flip, 'reason': 'confusion', 'pokemon_id': attacker_id},
                source=attacker_id,
            )
            events.append(flip_event)
            if self.pipeline:
                self.pipeline.emit(flip_event)

            if flip == 'tails':
                # 3 damage counters to self (30 damage)
                self_damage_events = self.place_damage_counters(attacker_id, 3)
                events.extend(self_damage_events)
                return events  # Turn ends, attack fails

        # Emit attack declaration
        declare_event = Event(
            type=EventType.PKM_ATTACK_DECLARE,
            payload={
                'attacker_id': attacker_id,
                'attack_name': attack.get('name', 'Attack'),
                'attack_index': attack_index,
                'targets': targets or [],
            },
            source=attacker_id,
            controller=attacker.controller,
        )
        if self.pipeline:
            result_events = self.pipeline.emit(declare_event)
            events.extend(result_events)
            # Check if prevented
            for ev in result_events:
                if ev.type == EventType.PKM_ATTACK_DECLARE and ev.status == EventStatus.PREVENTED:
                    return events

        # Find defender (opponent's active Pokemon)
        defender_id = self._get_opponent_active(attacker.controller)

        # Calculate and apply base damage
        base_damage = attack.get('damage', 0)

        # Execute attack effect function if present
        effect_fn = attack.get('effect_fn')
        if effect_fn:
            effect_events = effect_fn(attacker, self.state)
            for ev in (effect_events or []):
                if self.pipeline:
                    self.pipeline.emit(ev)
                events.append(ev)

        # Apply damage if attack has damage
        if base_damage > 0 and defender_id:
            damage = self.calculate_damage(attacker_id, defender_id, base_damage)
            if damage > 0:
                damage_events = self.apply_damage(defender_id, damage)
                events.extend(damage_events)

        # Discard energy if attack requires it
        discard_cost = attack.get('discard_cost')
        if discard_cost:
            from .pokemon_energy import PokemonEnergySystem
            energy_system = PokemonEnergySystem(self.state)
            to_discard = energy_system.select_energy_for_cost(attacker_id, discard_cost)
            if to_discard:
                discard_events = energy_system.discard_energy(attacker_id, to_discard)
                events.extend(discard_events)

        # Check for knockouts
        ko_events = self.check_knockouts()
        events.extend(ko_events)

        return events

    def calculate_damage(self, attacker_id: str, defender_id: str,
                         base_damage: int) -> int:
        """Apply weakness, resistance, and modifiers. Returns final damage."""
        attacker = self.state.objects.get(attacker_id)
        defender = self.state.objects.get(defender_id)
        if not attacker or not defender:
            return max(0, base_damage)

        damage = base_damage

        # Weakness: x2 if defender is weak to attacker's type
        attacker_type = None
        if attacker.card_def:
            attacker_type = attacker.card_def.pokemon_type
        if attacker_type and defender.card_def:
            if defender.card_def.weakness_type == attacker_type:
                modifier = defender.card_def.weakness_modifier
                if modifier == "x2":
                    damage *= 2

        # Resistance: -30 if defender is resistant to attacker's type
        if attacker_type and defender.card_def:
            if defender.card_def.resistance_type == attacker_type:
                damage += defender.card_def.resistance_modifier  # negative value

        # Floor at 0
        return max(0, damage)

    def apply_damage(self, pokemon_id: str, damage: int) -> list[Event]:
        """Apply damage as damage counters. Each 10 damage = 1 counter."""
        pokemon = self.state.objects.get(pokemon_id)
        if not pokemon or damage <= 0:
            return []

        # Round to nearest 10 (Pokemon damage is always multiples of 10)
        counters = damage // 10
        if counters <= 0:
            counters = 1  # Minimum 1 counter if damage > 0

        return self.place_damage_counters(pokemon_id, counters)

    def place_damage_counters(self, pokemon_id: str, count: int) -> list[Event]:
        """
        Direct counter placement (bypasses W/R).
        Used by Poison, Burn, effects.
        """
        pokemon = self.state.objects.get(pokemon_id)
        if not pokemon or count <= 0:
            return []

        pokemon.state.damage_counters += count

        event = Event(
            type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
            payload={
                'pokemon_id': pokemon_id,
                'count': count,
                'total_counters': pokemon.state.damage_counters,
            },
            source=pokemon_id,
        )
        if self.pipeline:
            self.pipeline.emit(event)
        return [event]

    def heal(self, pokemon_id: str, amount: int) -> list[Event]:
        """Remove damage counters (amount in HP, so 30 = remove 3 counters)."""
        pokemon = self.state.objects.get(pokemon_id)
        if not pokemon or amount <= 0:
            return []

        counters_to_remove = amount // 10
        actual_removed = min(counters_to_remove, pokemon.state.damage_counters)
        pokemon.state.damage_counters -= actual_removed

        if actual_removed > 0:
            event = Event(
                type=EventType.PKM_HEAL,
                payload={
                    'pokemon_id': pokemon_id,
                    'counters_removed': actual_removed,
                    'hp_healed': actual_removed * 10,
                },
                source=pokemon_id,
            )
            if self.pipeline:
                self.pipeline.emit(event)
            return [event]
        return []

    def check_knockouts(self) -> list[Event]:
        """Check all Pokemon for KO (damage_counters * 10 >= HP)."""
        events = []
        # Check active spots and benches for both players
        for zone_key, zone in self.state.zones.items():
            if zone.type not in (ZoneType.ACTIVE_SPOT, ZoneType.BENCH):
                continue
            for obj_id in list(zone.objects):
                obj = self.state.objects.get(obj_id)
                if not obj or CardType.POKEMON not in obj.characteristics.types:
                    continue
                hp = 0
                if obj.card_def:
                    hp = obj.card_def.hp or 0
                if hp > 0 and obj.state.damage_counters * 10 >= hp:
                    ko_events = self.handle_knockout(obj_id)
                    events.extend(ko_events)
        return events

    def handle_knockout(self, pokemon_id: str) -> list[Event]:
        """
        KO a Pokemon: discard it + attachments, opponent takes prizes,
        owner must promote if active was KO'd.
        """
        events = []
        pokemon = self.state.objects.get(pokemon_id)
        if not pokemon:
            return events

        was_active = pokemon.zone == ZoneType.ACTIVE_SPOT
        owner = pokemon.owner
        controller = pokemon.controller

        # Determine prize count
        prize_count = 1
        if pokemon.card_def:
            prize_count = pokemon.card_def.prize_count

        # Emit KO event
        ko_event = Event(
            type=EventType.PKM_KNOCKOUT,
            payload={
                'pokemon_id': pokemon_id,
                'owner': owner,
                'prize_count': prize_count,
                'was_active': was_active,
            },
            source=pokemon_id,
        )
        if self.pipeline:
            self.pipeline.emit(ko_event)
        events.append(ko_event)

        # Discard attached energy
        for energy_id in list(pokemon.state.attached_energy):
            energy_obj = self.state.objects.get(energy_id)
            if energy_obj:
                graveyard_key = f"graveyard_{energy_obj.owner}"
                if graveyard_key in self.state.zones:
                    self.state.zones[graveyard_key].objects.append(energy_id)
                energy_obj.zone = ZoneType.GRAVEYARD
                energy_obj.entered_zone_at = self.state.timestamp
        pokemon.state.attached_energy.clear()

        # Discard attached tool
        if pokemon.state.attached_tool:
            tool_obj = self.state.objects.get(pokemon.state.attached_tool)
            if tool_obj:
                graveyard_key = f"graveyard_{tool_obj.owner}"
                if graveyard_key in self.state.zones:
                    self.state.zones[graveyard_key].objects.append(tool_obj.id)
                tool_obj.zone = ZoneType.GRAVEYARD
                tool_obj.entered_zone_at = self.state.timestamp
            pokemon.state.attached_tool = None

        # Move Pokemon to discard pile
        self._remove_from_zone(pokemon_id)
        graveyard_key = f"graveyard_{owner}"
        if graveyard_key in self.state.zones:
            self.state.zones[graveyard_key].objects.append(pokemon_id)
        pokemon.zone = ZoneType.GRAVEYARD
        pokemon.entered_zone_at = self.state.timestamp

        # Opponent takes prizes
        opponent_id = self._get_opponent_id(controller)
        if opponent_id:
            prize_events = self._take_prizes(opponent_id, prize_count)
            events.extend(prize_events)

        # Owner must promote a new active if the KO'd Pokemon was active
        if was_active:
            promote_event = Event(
                type=EventType.PKM_PROMOTE_ACTIVE,
                payload={
                    'player': owner,
                    'reason': 'knockout',
                },
            )
            events.append(promote_event)

        return events

    def _take_prizes(self, player_id: str, count: int) -> list[Event]:
        """Player takes prize cards and puts them in hand."""
        events = []
        player = self.state.players.get(player_id)
        if not player:
            return events

        prize_key = f"prize_cards_{player_id}"
        prize_zone = self.state.zones.get(prize_key)
        hand_key = f"hand_{player_id}"
        hand_zone = self.state.zones.get(hand_key)

        if not prize_zone or not hand_zone:
            return events

        for _ in range(min(count, len(prize_zone.objects))):
            card_id = prize_zone.objects.pop(0)
            hand_zone.objects.append(card_id)
            card = self.state.objects.get(card_id)
            if card:
                card.zone = ZoneType.HAND
                card.entered_zone_at = self.state.timestamp

            player.prizes_remaining = len(prize_zone.objects)

            events.append(Event(
                type=EventType.PKM_TAKE_PRIZE,
                payload={
                    'player': player_id,
                    'card_id': card_id,
                    'prizes_remaining': player.prizes_remaining,
                },
            ))

        return events

    def _get_opponent_active(self, player_id: str) -> Optional[str]:
        """Get opponent's active Pokemon ID."""
        opponent_id = self._get_opponent_id(player_id)
        if not opponent_id:
            return None
        active_key = f"active_spot_{opponent_id}"
        active_zone = self.state.zones.get(active_key)
        if active_zone and active_zone.objects:
            return active_zone.objects[0]
        return None

    def _get_opponent_id(self, player_id: str) -> Optional[str]:
        """Get opponent player ID."""
        for pid in self.state.players:
            if pid != player_id:
                return pid
        return None

    def _remove_from_zone(self, object_id: str):
        """Remove object from whatever zone it's currently in."""
        for zone in self.state.zones.values():
            if object_id in zone.objects:
                zone.objects.remove(object_id)

    # MTG compatibility methods
    async def run_combat(self) -> list[Event]:
        """MTG compatibility - no-op in Pokemon mode."""
        return []

    async def _declare_attackers_step(self) -> list[Event]:
        """MTG compatibility - no-op."""
        return []

    async def _declare_blockers_step(self) -> list[Event]:
        """MTG compatibility - no-op."""
        return []

    async def _combat_damage_step(self) -> list[Event]:
        """MTG compatibility - no-op."""
        return []

    def reset_combat(self, player_id: str = None) -> None:
        """MTG/HS compatibility - no-op in Pokemon mode."""
        pass
