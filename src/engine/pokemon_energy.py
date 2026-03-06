"""
Pokemon Energy System

Energy attachment system for Pokemon TCG mode:
- Energy cards are attached to individual Pokemon (not pooled)
- 1 energy attachment per turn from hand
- Energy persists (not spent on use) unless discarded by attack/effect
- Colorless cost can be satisfied by any energy type
"""

from .types import (
    GameState, Player, Event, EventType, ZoneType, CardType, PokemonType
)


class PokemonEnergySystem:
    """
    Pokemon TCG energy system.

    Key differences from MTG/HS mana:
    - Energy is attached to individual Pokemon, not pooled
    - 1 energy attachment per turn from hand
    - Energy persists unless explicitly discarded
    - Colorless cost satisfied by any energy type
    """

    def __init__(self, state: GameState):
        self.state = state

    def can_attach_energy(self, player_id: str) -> bool:
        """Check if player has used their energy attachment this turn."""
        player = self.state.players.get(player_id)
        if not player:
            return False
        return not player.energy_attached_this_turn

    def attach_energy(self, player_id: str, energy_card_id: str,
                      target_pokemon_id: str) -> list[Event]:
        """Move energy card from hand to Pokemon's attached_energy."""
        player = self.state.players.get(player_id)
        if not player or player.energy_attached_this_turn:
            return []

        energy_obj = self.state.objects.get(energy_card_id)
        if not energy_obj or energy_obj.zone != ZoneType.HAND:
            return []
        if CardType.ENERGY not in energy_obj.characteristics.types:
            return []

        target = self.state.objects.get(target_pokemon_id)
        if not target or CardType.POKEMON not in target.characteristics.types:
            return []
        if target.controller != player_id:
            return []
        # Target must be in active spot or bench
        if target.zone not in (ZoneType.ACTIVE_SPOT, ZoneType.BENCH):
            return []

        # Move energy from hand to attached
        hand_key = f"hand_{player_id}"
        if hand_key in self.state.zones:
            zone = self.state.zones[hand_key]
            if energy_card_id in zone.objects:
                zone.objects.remove(energy_card_id)

        energy_obj.zone = ZoneType.BATTLEFIELD  # Energy on a Pokemon is "in play"
        energy_obj.entered_zone_at = self.state.timestamp
        target.state.attached_energy.append(energy_card_id)

        player.energy_attached_this_turn = True

        return [Event(
            type=EventType.PKM_ATTACH_ENERGY,
            payload={
                'player': player_id,
                'energy_id': energy_card_id,
                'target_id': target_pokemon_id,
                'energy_type': self._get_energy_type(energy_obj),
            },
            source=energy_card_id,
        )]

    def get_attached_energy(self, pokemon_id: str) -> dict[str, int]:
        """Count energy by type on a Pokemon. Returns {type_value: count}."""
        pokemon = self.state.objects.get(pokemon_id)
        if not pokemon:
            return {}

        counts: dict[str, int] = {}
        for energy_id in pokemon.state.attached_energy:
            energy_obj = self.state.objects.get(energy_id)
            if energy_obj:
                etype = self._get_energy_type(energy_obj)
                counts[etype] = counts.get(etype, 0) + 1
        return counts

    def get_total_energy(self, pokemon_id: str) -> int:
        """Get total number of energy cards attached."""
        pokemon = self.state.objects.get(pokemon_id)
        if not pokemon:
            return 0
        return len(pokemon.state.attached_energy)

    def can_pay_cost(self, pokemon_id: str, cost: list[dict]) -> bool:
        """
        Check if Pokemon has enough energy to pay an attack cost.

        Cost format: [{"type": "R", "count": 2}, {"type": "C", "count": 1}]
        Colorless ("C") can be satisfied by any energy type.
        """
        attached = self.get_attached_energy(pokemon_id)
        # Copy so we can decrement
        available = dict(attached)
        total_available = sum(available.values())

        # First satisfy typed costs
        typed_needed = 0
        for req in cost:
            etype = req.get('type', 'C')
            count = req.get('count', 0)
            if etype == 'C':
                continue  # Handle colorless last
            if available.get(etype, 0) < count:
                return False
            available[etype] = available.get(etype, 0) - count
            typed_needed += count

        # Then check colorless (any remaining energy)
        colorless_needed = sum(
            req.get('count', 0) for req in cost if req.get('type', 'C') == 'C'
        )
        remaining = sum(available.values())
        return remaining >= colorless_needed

    def select_energy_for_cost(self, pokemon_id: str, cost: list[dict]) -> list[str]:
        """
        Select specific energy card IDs to pay a cost (for retreat/attack discard).
        Returns list of energy object IDs, or empty list if can't pay.
        """
        pokemon = self.state.objects.get(pokemon_id)
        if not pokemon:
            return []

        # Group energy by type
        energy_by_type: dict[str, list[str]] = {}
        for energy_id in pokemon.state.attached_energy:
            energy_obj = self.state.objects.get(energy_id)
            if energy_obj:
                etype = self._get_energy_type(energy_obj)
                energy_by_type.setdefault(etype, []).append(energy_id)

        selected: list[str] = []

        # Satisfy typed costs first
        for req in cost:
            etype = req.get('type', 'C')
            count = req.get('count', 0)
            if etype == 'C':
                continue
            pool = energy_by_type.get(etype, [])
            if len(pool) < count:
                return []
            for _ in range(count):
                selected.append(pool.pop(0))

        # Satisfy colorless with whatever's left
        colorless_needed = sum(
            req.get('count', 0) for req in cost if req.get('type', 'C') == 'C'
        )
        remaining = []
        for ids in energy_by_type.values():
            remaining.extend(ids)
        if len(remaining) < colorless_needed:
            return []
        for _ in range(colorless_needed):
            selected.append(remaining.pop(0))

        return selected

    def discard_energy(self, pokemon_id: str, energy_ids: list[str]) -> list[Event]:
        """Discard specific energy cards from a Pokemon."""
        pokemon = self.state.objects.get(pokemon_id)
        if not pokemon:
            return []

        events = []
        for energy_id in energy_ids:
            if energy_id in pokemon.state.attached_energy:
                pokemon.state.attached_energy.remove(energy_id)
                energy_obj = self.state.objects.get(energy_id)
                if energy_obj:
                    # Move to discard pile (graveyard)
                    graveyard_key = f"graveyard_{energy_obj.owner}"
                    if graveyard_key in self.state.zones:
                        self.state.zones[graveyard_key].objects.append(energy_id)
                    energy_obj.zone = ZoneType.GRAVEYARD
                    energy_obj.entered_zone_at = self.state.timestamp

                events.append(Event(
                    type=EventType.PKM_DISCARD_ENERGY,
                    payload={
                        'pokemon_id': pokemon_id,
                        'energy_id': energy_id,
                    },
                    source=pokemon_id,
                ))

        return events

    def on_turn_start(self, player_id: str):
        """Reset energy_attached_this_turn flag."""
        player = self.state.players.get(player_id)
        if player:
            player.energy_attached_this_turn = False

    def _get_energy_type(self, energy_obj) -> str:
        """Get the PokemonType value for an energy card."""
        if energy_obj.card_def and energy_obj.card_def.pokemon_type:
            return energy_obj.card_def.pokemon_type
        # Fallback: check name
        name = energy_obj.name.lower()
        type_map = {
            'grass': PokemonType.GRASS.value,
            'fire': PokemonType.FIRE.value,
            'water': PokemonType.WATER.value,
            'lightning': PokemonType.LIGHTNING.value,
            'psychic': PokemonType.PSYCHIC.value,
            'fighting': PokemonType.FIGHTING.value,
            'darkness': PokemonType.DARKNESS.value,
            'dark': PokemonType.DARKNESS.value,
            'metal': PokemonType.METAL.value,
            'steel': PokemonType.METAL.value,
        }
        for key, val in type_map.items():
            if key in name:
                return val
        return PokemonType.COLORLESS.value

    # MTG/HS compatibility methods (no-ops for Pokemon mode)

    def get_pool(self, player_id: str):
        """MTG compatibility - returns None in Pokemon mode."""
        return None

    def get_untapped_lands(self, player_id: str) -> list:
        """MTG compatibility - returns empty list in Pokemon mode."""
        return []

    def can_pay_cost_mana(self, player_id: str, cost: int) -> bool:
        """HS compatibility - not used in Pokemon mode."""
        return False

    def pay_cost(self, player_id: str, cost: int) -> bool:
        """HS compatibility - not used in Pokemon mode."""
        return False

    def get_available_mana(self, player_id: str) -> int:
        """HS compatibility - not used in Pokemon mode."""
        return 0
