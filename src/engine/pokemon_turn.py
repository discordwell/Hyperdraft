"""
Pokemon Turn Manager

Turn structure for Pokemon TCG mode:
1. Draw step (draw 1 card, deck-out = lose)
2. Main phase (all actions in any order)
3. Attack phase (Active Pokemon attacks, ends turn)
4. Checkup (between-turns: Poison, Burn, Sleep, Paralysis, KO check)

Per-turn limits: 1 energy attachment, 1 Supporter, 1 retreat, 1 Stadium.
First-turn restrictions: no attacks (going first), no evolving (both).
"""

import random
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
from enum import Enum, auto

from .types import (
    GameState, Event, EventType, ZoneType, CardType, new_id
)
from .turn import TurnManager, Phase, Step, TurnState

if TYPE_CHECKING:
    from .priority import PrioritySystem
    from .combat import CombatManager
    from .pipeline import EventPipeline


class PokemonPhase(Enum):
    """Pokemon TCG turn phases."""
    DRAW = auto()
    MAIN = auto()
    ATTACK = auto()
    CHECKUP = auto()


@dataclass
class PokemonTurnState:
    """Turn state for Pokemon TCG mode."""
    turn_number: int = 0
    active_player_id: Optional[str] = None
    phase: PokemonPhase = PokemonPhase.DRAW
    game_turn_count: int = 0  # Total turns played (for first-turn restrictions)
    first_player_id: Optional[str] = None  # Who went first

    # Extra turns
    extra_turns: list[str] = field(default_factory=list)


class PokemonTurnManager(TurnManager):
    """
    Pokemon TCG turn manager.

    Key differences from MTG/HS:
    - Draw 1 card (deck-out = instant loss)
    - Main phase: play basics, evolve, attach energy, play trainers, use abilities, retreat
    - Attack phase: one attack, ends the turn
    - Between-turns checkup: status condition resolution
    - No priority/stack system
    """

    def __init__(self, state: GameState):
        super().__init__(state)
        self.pkm_turn_state = PokemonTurnState()
        self.pokemon_ai_handler = None
        self.ai_players: set[str] = set()
        self.human_action_handler = None  # async fn(player_id, game_state) -> action_dict

    async def setup_game(self) -> list[Event]:
        """
        Pokemon TCG game setup:
        1. Both players shuffle, draw 7
        2. Check for Basic Pokemon — mulligan if none
        3. Place 1 Basic face-down as Active
        4. Optionally place more Basics on Bench
        5. Set 6 Prize Cards from top of deck
        6. Coin flip for first player
        """
        events = []
        player_ids = list(self.state.players.keys())
        if len(player_ids) < 2:
            return events

        # Shuffle decks
        for pid in player_ids:
            library_key = f"library_{pid}"
            if library_key in self.state.zones:
                zone = self.state.zones[library_key]
                random.shuffle(zone.objects)

        # Draw 7 cards each, mulligan if no basics
        for pid in player_ids:
            await self._draw_opening_hand(pid)
            events.extend(await self._check_mulligan(pid))

        # Auto-setup: place first Basic as Active, rest optional on Bench
        for pid in player_ids:
            events.extend(self._auto_place_basics(pid))

        # Set 6 prize cards
        for pid in player_ids:
            events.extend(self._set_prize_cards(pid))

        # Coin flip for first player
        flip = random.choice([0, 1])
        self.pkm_turn_state.first_player_id = player_ids[flip]
        self.turn_order = [player_ids[flip], player_ids[1 - flip]]
        self.current_player_index = 0

        events.append(Event(
            type=EventType.PKM_SETUP,
            payload={
                'first_player': player_ids[flip],
                'second_player': player_ids[1 - flip],
            },
        ))

        # Emit game start
        game_start = Event(
            type=EventType.GAME_START,
            payload={'players': self.turn_order}
        )
        if self.pipeline:
            self.pipeline.emit(game_start)
        events.append(game_start)

        return events

    async def run_turn(self, player_id: str = None) -> list[Event]:
        """Run a complete Pokemon TCG turn."""
        events = []

        # Determine active player
        if player_id:
            self.pkm_turn_state.active_player_id = player_id
            if player_id in self.turn_order:
                self.current_player_index = self.turn_order.index(player_id)
        else:
            self.pkm_turn_state.active_player_id = self.turn_order[self.current_player_index]

        active_pid = self.pkm_turn_state.active_player_id
        self.state.active_player = active_pid

        self.pkm_turn_state.turn_number += 1
        self.pkm_turn_state.game_turn_count += 1
        self.state.turn_number = self.pkm_turn_state.turn_number
        self.turn_state.turn_number = self.pkm_turn_state.turn_number

        # Reset per-turn flags
        self._reset_turn_flags(active_pid)

        # Emit turn start
        events.extend(await self._emit_turn_start())

        # Draw Phase
        self.pkm_turn_state.phase = PokemonPhase.DRAW
        events.extend(await self._run_draw_phase())
        if self._is_game_over():
            return events

        # Main Phase
        self.pkm_turn_state.phase = PokemonPhase.MAIN
        is_ai = self._is_ai_player(active_pid)

        if is_ai and self.pokemon_ai_handler:
            ai_events = await self._run_ai_turn()
            events.extend(ai_events)
        elif not is_ai and self.human_action_handler:
            human_events = await self._run_human_turn()
            events.extend(human_events)

        # Between-turns checkup
        if not self._is_game_over():
            self.pkm_turn_state.phase = PokemonPhase.CHECKUP
            events.extend(self._run_checkup())

        # Check KOs from checkup
        if not self._is_game_over():
            events.extend(self._check_pokemon_knockouts())

        # End turn
        if not self._is_game_over():
            events.extend(await self._emit_turn_end())

        # Advance to next player
        self.current_player_index = (self.current_player_index + 1) % len(self.turn_order)

        return events

    async def _run_draw_phase(self) -> list[Event]:
        """Draw 1 card. Empty deck = lose."""
        events = []
        active_pid = self.pkm_turn_state.active_player_id
        player = self.state.players.get(active_pid)
        if not player:
            return events

        # First turn of the game: going-first player doesn't draw
        if (self.pkm_turn_state.game_turn_count == 1 and
                active_pid == self.pkm_turn_state.first_player_id):
            return events

        library_key = f"library_{active_pid}"
        library = self.state.zones.get(library_key)

        if not library or not library.objects:
            # Deck-out: player loses
            player.has_lost = True
            events.append(Event(
                type=EventType.PLAYER_LOSES,
                payload={'player': active_pid, 'reason': 'deck_out'},
            ))
            return events

        # Draw 1 card
        draw_event = Event(
            type=EventType.DRAW,
            payload={'player': active_pid, 'count': 1}
        )
        if self.pipeline:
            self.pipeline.emit(draw_event)
        events.append(draw_event)

        return events

    async def _run_human_turn(self) -> list[Event]:
        """Handle human player's main phase via action handler callback."""
        events = []
        player_id = self.pkm_turn_state.active_player_id

        for _ in range(200):  # Safety cap
            if self._is_game_over():
                break

            action = await self.human_action_handler(player_id, self.state)
            if action is None:
                break

            action_type = action.get('action_type', '')

            if action_type == 'PKM_END_TURN':
                break

            elif action_type == 'PKM_ATTACK':
                attack_index = action.get('attack_index', 0)
                targets = action.get('targets', [])
                attack_events = await self._execute_attack(player_id, attack_index, targets)
                events.extend(attack_events)
                break  # Attack ends the turn

            elif action_type == 'PKM_PLAY_BASIC':
                card_id = action.get('card_id')
                if card_id:
                    events.extend(self._play_basic(player_id, card_id))

            elif action_type == 'PKM_EVOLVE':
                card_id = action.get('card_id')
                target_id = action.get('target_id')
                if card_id and target_id:
                    events.extend(self.evolve_pokemon(target_id, card_id))

            elif action_type == 'PKM_ATTACH_ENERGY':
                energy_id = action.get('energy_id')
                target_id = action.get('target_id')
                if energy_id and target_id:
                    events.extend(self._attach_energy(player_id, energy_id, target_id))

            elif action_type == 'PKM_PLAY_ITEM':
                card_id = action.get('card_id')
                if card_id:
                    events.extend(self._play_trainer(player_id, card_id, 'item'))

            elif action_type == 'PKM_PLAY_SUPPORTER':
                card_id = action.get('card_id')
                if card_id:
                    events.extend(self._play_trainer(player_id, card_id, 'supporter'))

            elif action_type == 'PKM_PLAY_STADIUM':
                card_id = action.get('card_id')
                if card_id:
                    events.extend(self._play_trainer(player_id, card_id, 'stadium'))

            elif action_type == 'PKM_RETREAT':
                bench_id = action.get('bench_pokemon_id')
                if bench_id:
                    events.extend(self._retreat(player_id, bench_id))

            elif action_type == 'PKM_USE_ABILITY':
                pokemon_id = action.get('pokemon_id')
                if pokemon_id:
                    events.extend(self._use_ability(player_id, pokemon_id))

            # Check for KOs after each action
            events.extend(self._check_pokemon_knockouts())

        return events

    async def _execute_attack(self, player_id: str, attack_index: int,
                               targets: list[str] = None) -> list[Event]:
        """Execute an attack with the active Pokemon."""
        events = []

        # First-turn restriction: going-first player can't attack turn 1
        if (self.pkm_turn_state.game_turn_count == 1 and
                player_id == self.pkm_turn_state.first_player_id):
            return events

        # Get active Pokemon
        active_key = f"active_spot_{player_id}"
        active_zone = self.state.zones.get(active_key)
        if not active_zone or not active_zone.objects:
            return events

        attacker_id = active_zone.objects[0]

        # Use combat manager
        game = getattr(self.state, '_game', None)
        if game and hasattr(game, 'combat_manager'):
            attack_events = game.combat_manager.declare_attack(
                attacker_id, attack_index, targets
            )
            events.extend(attack_events)

        return events

    def _play_basic(self, player_id: str, card_id: str) -> list[Event]:
        """Play a Basic Pokemon from hand to bench."""
        obj = self.state.objects.get(card_id)
        if not obj or obj.zone != ZoneType.HAND:
            return []
        if CardType.POKEMON not in obj.characteristics.types:
            return []
        if not obj.card_def or obj.card_def.evolution_stage != "Basic":
            return []

        # Check bench limit (5 max)
        bench_key = f"bench_{player_id}"
        bench = self.state.zones.get(bench_key)
        if not bench or len(bench.objects) >= 5:
            return []

        # Move from hand to bench
        hand_key = f"hand_{player_id}"
        if hand_key in self.state.zones:
            hand = self.state.zones[hand_key]
            if card_id in hand.objects:
                hand.objects.remove(card_id)

        bench.objects.append(card_id)
        obj.zone = ZoneType.BENCH
        obj.entered_zone_at = self.state.timestamp
        obj.state.damage_counters = 0
        obj.state.turns_in_play = 0
        obj.state.evolved_this_turn = False
        obj.state.status_conditions = set()

        return [Event(
            type=EventType.PKM_PLAY_BASIC,
            payload={
                'player': player_id,
                'pokemon_id': card_id,
                'pokemon_name': obj.name,
            },
            source=card_id,
        )]

    def can_evolve(self, pokemon_id: str, evolution_card_id: str) -> tuple[bool, str]:
        """Check if evolution is legal."""
        pokemon = self.state.objects.get(pokemon_id)
        evolution = self.state.objects.get(evolution_card_id)

        if not pokemon or not evolution:
            return False, "Invalid Pokemon or evolution card"

        if not evolution.card_def:
            return False, "No card definition"

        # Check evolves_from matches
        if evolution.card_def.evolves_from != pokemon.name:
            return False, f"{evolution.name} doesn't evolve from {pokemon.name}"

        # Check not played this turn
        if pokemon.state.turns_in_play < 1:
            return False, "Pokemon was just played this turn"

        # Check not already evolved this turn
        if pokemon.state.evolved_this_turn:
            return False, "Pokemon already evolved this turn"

        # First turn of the game: no evolving
        if self.pkm_turn_state.game_turn_count <= 2:  # Neither player's first turn
            return False, "Cannot evolve on the first turn"

        return True, ""

    def evolve_pokemon(self, pokemon_id: str, evolution_card_id: str) -> list[Event]:
        """
        Evolve a Pokemon:
        - Update characteristics to new card
        - Keep attached energy, tools, damage counters
        - Remove all status conditions
        - Set evolved_this_turn = True
        """
        ok, msg = self.can_evolve(pokemon_id, evolution_card_id)
        if not ok:
            return []

        pokemon = self.state.objects.get(pokemon_id)
        evolution = self.state.objects.get(evolution_card_id)

        # Remove evolution card from hand
        hand_key = f"hand_{pokemon.controller}"
        if hand_key in self.state.zones:
            hand = self.state.zones[hand_key]
            if evolution_card_id in hand.objects:
                hand.objects.remove(evolution_card_id)

        # Store previous stage
        old_name = pokemon.name
        old_card_def = pokemon.card_def

        # Update Pokemon to new stage
        pokemon.name = evolution.name
        pokemon.card_def = evolution.card_def
        if evolution.card_def:
            import copy
            pokemon.characteristics = copy.deepcopy(evolution.card_def.characteristics)

        # Track evolution
        pokemon.state.evolution_stage_num += 1
        pokemon.state.evolved_from_id = evolution_card_id
        pokemon.state.evolved_this_turn = True

        # Remove all status conditions
        from .pokemon_status import remove_all_status
        remove_all_status(pokemon_id, self.state)

        # Remove the evolution card object (it's now part of the Pokemon)
        if evolution_card_id in self.state.objects:
            del self.state.objects[evolution_card_id]

        # Re-register interceptors from new card_def
        if pokemon.card_def and pokemon.card_def.setup_interceptors:
            # Clean old interceptors
            for int_id in list(pokemon.interceptor_ids):
                if int_id in self.state.interceptors:
                    del self.state.interceptors[int_id]
            pokemon.interceptor_ids.clear()

            new_interceptors = pokemon.card_def.setup_interceptors(pokemon, self.state) or []
            for interceptor in new_interceptors:
                interceptor.timestamp = self.state.next_timestamp()
                self.state.interceptors[interceptor.id] = interceptor
                pokemon.interceptor_ids.append(interceptor.id)

        return [Event(
            type=EventType.PKM_EVOLVE,
            payload={
                'pokemon_id': pokemon_id,
                'from_name': old_name,
                'to_name': pokemon.name,
                'player': pokemon.controller,
            },
            source=pokemon_id,
        )]

    def _attach_energy(self, player_id: str, energy_id: str, target_id: str) -> list[Event]:
        """Attach an energy card from hand to a Pokemon."""
        from .pokemon_energy import PokemonEnergySystem
        energy_system = PokemonEnergySystem(self.state)
        return energy_system.attach_energy(player_id, energy_id, target_id)

    def _play_trainer(self, player_id: str, card_id: str, trainer_type: str) -> list[Event]:
        """Play a Trainer card (Item, Supporter, or Stadium)."""
        obj = self.state.objects.get(card_id)
        if not obj or obj.zone != ZoneType.HAND:
            return []

        player = self.state.players.get(player_id)
        if not player:
            return []

        # Check per-turn limits
        if trainer_type == 'supporter':
            if player.supporter_played_this_turn:
                return []
            # First turn going first: no supporters
            if (self.pkm_turn_state.game_turn_count == 1 and
                    player_id == self.pkm_turn_state.first_player_id):
                return []
            player.supporter_played_this_turn = True

        if trainer_type == 'stadium':
            if player.stadium_played_this_turn:
                return []
            player.stadium_played_this_turn = True

        # Determine event type
        event_type_map = {
            'item': EventType.PKM_PLAY_ITEM,
            'supporter': EventType.PKM_PLAY_SUPPORTER,
            'stadium': EventType.PKM_PLAY_STADIUM,
        }
        event_type = event_type_map.get(trainer_type, EventType.PKM_PLAY_ITEM)

        events = []

        # Emit play event
        play_event = Event(
            type=event_type,
            payload={
                'player': player_id,
                'card_id': card_id,
                'card_name': obj.name,
            },
            source=card_id,
        )
        if self.pipeline:
            self.pipeline.emit(play_event)
        events.append(play_event)

        # Execute card effect
        if obj.card_def and obj.card_def.resolve:
            effect_events = obj.card_def.resolve(
                Event(type=event_type, payload={'card_id': card_id}, source=card_id),
                self.state
            )
            for ev in (effect_events or []):
                if self.pipeline:
                    self.pipeline.emit(ev)
                events.append(ev)

        # Remove from hand
        hand_key = f"hand_{player_id}"
        if hand_key in self.state.zones:
            hand = self.state.zones[hand_key]
            if card_id in hand.objects:
                hand.objects.remove(card_id)

        # Stadium goes to stadium zone; others go to discard
        if trainer_type == 'stadium':
            # Replace existing stadium
            stadium_key = "stadium_zone"
            stadium_zone = self.state.zones.get(stadium_key)
            if stadium_zone:
                for old_id in list(stadium_zone.objects):
                    old_obj = self.state.objects.get(old_id)
                    if old_obj:
                        graveyard_key = f"graveyard_{old_obj.owner}"
                        if graveyard_key in self.state.zones:
                            self.state.zones[graveyard_key].objects.append(old_id)
                        old_obj.zone = ZoneType.GRAVEYARD
                    stadium_zone.objects.remove(old_id)
                stadium_zone.objects.append(card_id)
            obj.zone = ZoneType.STADIUM_ZONE
        else:
            graveyard_key = f"graveyard_{player_id}"
            if graveyard_key in self.state.zones:
                self.state.zones[graveyard_key].objects.append(card_id)
            obj.zone = ZoneType.GRAVEYARD

        obj.entered_zone_at = self.state.timestamp

        return events

    def _retreat(self, player_id: str, bench_pokemon_id: str) -> list[Event]:
        """Retreat active Pokemon and replace with bench Pokemon."""
        player = self.state.players.get(player_id)
        if not player or player.retreated_this_turn:
            return []

        active_key = f"active_spot_{player_id}"
        active_zone = self.state.zones.get(active_key)
        if not active_zone or not active_zone.objects:
            return []

        active_id = active_zone.objects[0]
        active = self.state.objects.get(active_id)
        if not active:
            return []

        # Check status conditions
        from .pokemon_status import can_retreat
        ok, msg = can_retreat(active_id, self.state)
        if not ok:
            return []

        # Check retreat cost
        retreat_cost = 0
        if active.card_def:
            retreat_cost = active.card_def.retreat_cost

        from .pokemon_energy import PokemonEnergySystem
        energy_system = PokemonEnergySystem(self.state)

        if retreat_cost > 0:
            # Build colorless cost for retreat
            cost = [{'type': 'C', 'count': retreat_cost}]
            if not energy_system.can_pay_cost(active_id, cost):
                return []
            to_discard = energy_system.select_energy_for_cost(active_id, cost)
            if not to_discard:
                return []
            energy_system.discard_energy(active_id, to_discard)

        # Check bench Pokemon exists
        bench_key = f"bench_{player_id}"
        bench = self.state.zones.get(bench_key)
        bench_pokemon = self.state.objects.get(bench_pokemon_id)
        if not bench or bench_pokemon_id not in bench.objects or not bench_pokemon:
            return []

        # Swap: active -> bench, bench -> active
        active_zone.objects.remove(active_id)
        bench.objects.remove(bench_pokemon_id)

        active_zone.objects.append(bench_pokemon_id)
        bench.objects.append(active_id)

        bench_pokemon.zone = ZoneType.ACTIVE_SPOT
        bench_pokemon.entered_zone_at = self.state.timestamp
        active.zone = ZoneType.BENCH
        active.entered_zone_at = self.state.timestamp

        # Remove all status conditions from retreated Pokemon
        from .pokemon_status import remove_all_status
        remove_all_status(active_id, self.state)

        player.retreated_this_turn = True

        return [Event(
            type=EventType.PKM_RETREAT,
            payload={
                'player': player_id,
                'retreated_id': active_id,
                'promoted_id': bench_pokemon_id,
            },
            source=active_id,
        )]

    def _use_ability(self, player_id: str, pokemon_id: str) -> list[Event]:
        """Use a Pokemon's Ability."""
        pokemon = self.state.objects.get(pokemon_id)
        if not pokemon or not pokemon.card_def or not pokemon.card_def.ability:
            return []

        ability = pokemon.card_def.ability
        effect_fn = ability.get('effect_fn')
        if not effect_fn:
            return []

        events = []
        ability_event = Event(
            type=EventType.PKM_USE_ABILITY,
            payload={
                'player': player_id,
                'pokemon_id': pokemon_id,
                'ability_name': ability.get('name', 'Ability'),
            },
            source=pokemon_id,
        )
        if self.pipeline:
            self.pipeline.emit(ability_event)
        events.append(ability_event)

        effect_events = effect_fn(pokemon, self.state)
        for ev in (effect_events or []):
            if self.pipeline:
                self.pipeline.emit(ev)
            events.append(ev)

        return events

    def promote_active(self, player_id: str, bench_pokemon_id: str) -> list[Event]:
        """Promote a bench Pokemon to active (after KO or forced switch)."""
        active_key = f"active_spot_{player_id}"
        active_zone = self.state.zones.get(active_key)
        bench_key = f"bench_{player_id}"
        bench = self.state.zones.get(bench_key)

        if not active_zone or not bench:
            return []
        if bench_pokemon_id not in bench.objects:
            return []

        bench.objects.remove(bench_pokemon_id)
        active_zone.objects.append(bench_pokemon_id)

        pokemon = self.state.objects.get(bench_pokemon_id)
        if pokemon:
            pokemon.zone = ZoneType.ACTIVE_SPOT
            pokemon.entered_zone_at = self.state.timestamp

        return [Event(
            type=EventType.PKM_PROMOTE_ACTIVE,
            payload={
                'player': player_id,
                'pokemon_id': bench_pokemon_id,
            },
            source=bench_pokemon_id,
        )]

    def _run_checkup(self) -> list[Event]:
        """Run between-turns checkup."""
        from .pokemon_status import run_checkup
        return run_checkup(self.state, self.pipeline)

    def _check_pokemon_knockouts(self) -> list[Event]:
        """Check all Pokemon for KO and handle."""
        game = getattr(self.state, '_game', None)
        if game and hasattr(game, 'combat_manager'):
            return game.combat_manager.check_knockouts()
        return []

    def check_win_conditions(self) -> Optional[str]:
        """
        Check win conditions. Returns winner player_id or None.
        - All prizes taken
        - Opponent has no Pokemon in play
        - Opponent deck-out (handled in draw phase)
        """
        for pid, player in self.state.players.items():
            if player.has_lost:
                # Return the other player as winner
                for other_pid in self.state.players:
                    if other_pid != pid:
                        return other_pid

            # All prizes taken
            if player.prizes_remaining == 0 and self.pkm_turn_state.game_turn_count > 0:
                # Mark opponents as lost so game.is_game_over() detects it
                for other_pid, other_player in self.state.players.items():
                    if other_pid != pid:
                        other_player.has_lost = True
                return pid

        # Check if any player has no Pokemon in play
        for pid in self.state.players:
            active_key = f"active_spot_{pid}"
            bench_key = f"bench_{pid}"
            active = self.state.zones.get(active_key)
            bench = self.state.zones.get(bench_key)

            has_pokemon = False
            if active and active.objects:
                has_pokemon = True
            if bench and bench.objects:
                has_pokemon = True

            if not has_pokemon and self.pkm_turn_state.game_turn_count > 0:
                # This player loses - mark and return opponent as winner
                self.state.players[pid].has_lost = True
                for other_pid in self.state.players:
                    if other_pid != pid:
                        return other_pid

        return None

    def _reset_turn_flags(self, player_id: str):
        """Reset per-turn flags."""
        player = self.state.players.get(player_id)
        if player:
            player.energy_attached_this_turn = False
            player.supporter_played_this_turn = False
            player.stadium_played_this_turn = False
            player.retreated_this_turn = False

        # Increment turns_in_play for this player's Pokemon and reset per-turn flags
        for zone_key, zone in self.state.zones.items():
            if zone.type in (ZoneType.ACTIVE_SPOT, ZoneType.BENCH) and zone.owner == player_id:
                for obj_id in zone.objects:
                    obj = self.state.objects.get(obj_id)
                    if obj and CardType.POKEMON in obj.characteristics.types:
                        obj.state.turns_in_play += 1
                        obj.state.evolved_this_turn = False
                        obj.state.ability_used_this_turn = False

    # ---- Setup helpers ----

    async def _draw_opening_hand(self, player_id: str):
        """Draw 7 cards for opening hand."""
        draw_event = Event(
            type=EventType.DRAW,
            payload={'player': player_id, 'count': 7}
        )
        if self.pipeline:
            self.pipeline.emit(draw_event)

    async def _check_mulligan(self, player_id: str) -> list[Event]:
        """Check for Basic Pokemon in hand; mulligan if none."""
        events = []
        hand_key = f"hand_{player_id}"
        hand = self.state.zones.get(hand_key)
        library_key = f"library_{player_id}"
        library = self.state.zones.get(library_key)

        if not hand or not library:
            return events

        max_mulligans = 10  # Safety cap
        mulligan_count = 0

        while mulligan_count < max_mulligans:
            # Check for basics
            has_basic = False
            for obj_id in hand.objects:
                obj = self.state.objects.get(obj_id)
                if (obj and CardType.POKEMON in obj.characteristics.types
                        and obj.card_def and obj.card_def.evolution_stage == "Basic"):
                    has_basic = True
                    break

            if has_basic:
                break

            # Mulligan: shuffle hand back, draw 7 again
            mulligan_count += 1
            events.append(Event(
                type=EventType.PKM_MULLIGAN,
                payload={'player': player_id, 'mulligan_number': mulligan_count},
            ))

            # Put hand back in library
            for obj_id in list(hand.objects):
                library.objects.append(obj_id)
                obj = self.state.objects.get(obj_id)
                if obj:
                    obj.zone = ZoneType.LIBRARY
            hand.objects.clear()

            # Shuffle and draw again
            random.shuffle(library.objects)
            draw_event = Event(
                type=EventType.DRAW,
                payload={'player': player_id, 'count': 7}
            )
            if self.pipeline:
                self.pipeline.emit(draw_event)

        # Opponent draws extra cards for each mulligan
        if mulligan_count > 0:
            opponent_id = None
            for pid in self.state.players:
                if pid != player_id:
                    opponent_id = pid
                    break
            if opponent_id:
                draw_event = Event(
                    type=EventType.DRAW,
                    payload={'player': opponent_id, 'count': mulligan_count}
                )
                if self.pipeline:
                    self.pipeline.emit(draw_event)

        return events

    def _auto_place_basics(self, player_id: str) -> list[Event]:
        """Auto-place Basic Pokemon from hand to Active/Bench during setup."""
        events = []
        hand_key = f"hand_{player_id}"
        hand = self.state.zones.get(hand_key)
        active_key = f"active_spot_{player_id}"
        active_zone = self.state.zones.get(active_key)
        bench_key = f"bench_{player_id}"
        bench = self.state.zones.get(bench_key)

        if not hand or not active_zone or not bench:
            return events

        basics_in_hand = []
        for obj_id in list(hand.objects):
            obj = self.state.objects.get(obj_id)
            if (obj and CardType.POKEMON in obj.characteristics.types
                    and obj.card_def and obj.card_def.evolution_stage == "Basic"):
                basics_in_hand.append(obj_id)

        if not basics_in_hand:
            return events

        # First basic goes to Active Spot
        first_basic = basics_in_hand[0]
        hand.objects.remove(first_basic)
        active_zone.objects.append(first_basic)
        obj = self.state.objects.get(first_basic)
        if obj:
            obj.zone = ZoneType.ACTIVE_SPOT
            obj.entered_zone_at = self.state.timestamp
            obj.state.turns_in_play = 0

        # Remaining basics go to bench (up to 5)
        for basic_id in basics_in_hand[1:6]:  # Max 5 on bench
            hand.objects.remove(basic_id)
            bench.objects.append(basic_id)
            obj = self.state.objects.get(basic_id)
            if obj:
                obj.zone = ZoneType.BENCH
                obj.entered_zone_at = self.state.timestamp
                obj.state.turns_in_play = 0

        return events

    def _set_prize_cards(self, player_id: str) -> list[Event]:
        """Set 6 prize cards from top of deck."""
        library_key = f"library_{player_id}"
        prize_key = f"prize_cards_{player_id}"
        library = self.state.zones.get(library_key)
        prize_zone = self.state.zones.get(prize_key)

        if not library or not prize_zone:
            return []

        for _ in range(min(6, len(library.objects))):
            card_id = library.objects.pop(0)
            prize_zone.objects.append(card_id)
            card = self.state.objects.get(card_id)
            if card:
                card.zone = ZoneType.PRIZE_CARDS

        player = self.state.players.get(player_id)
        if player:
            player.prizes_remaining = len(prize_zone.objects)

        return []

    # ---- Game state helpers ----

    def _is_game_over(self) -> bool:
        """Check if the game is over."""
        winner = self.check_win_conditions()
        if winner:
            return True
        alive = [p for p in self.state.players.values() if not p.has_lost]
        return len(alive) <= 1

    async def _emit_turn_start(self) -> list[Event]:
        """Emit turn start event."""
        events = []
        turn_start = Event(
            type=EventType.TURN_START,
            payload={
                'player': self.pkm_turn_state.active_player_id,
                'turn_number': self.pkm_turn_state.turn_number,
            }
        )
        if self.pipeline:
            self.pipeline.emit(turn_start)
        events.append(turn_start)
        return events

    async def _emit_turn_end(self) -> list[Event]:
        """Emit turn end event."""
        events = []
        turn_end = Event(
            type=EventType.TURN_END,
            payload={
                'player': self.pkm_turn_state.active_player_id,
                'turn_number': self.pkm_turn_state.turn_number,
            }
        )
        if self.pipeline:
            self.pipeline.emit(turn_end)
        events.append(turn_end)
        return events

    # ---- AI Integration ----

    def set_ai_handler(self, handler):
        """Set the Pokemon AI handler."""
        self.pokemon_ai_handler = handler

    def set_ai_player(self, player_id: str):
        """Mark a player as AI-controlled."""
        self.ai_players.add(player_id)

    def _is_ai_player(self, player_id: str) -> bool:
        """Check if player is AI-controlled."""
        return player_id in self.ai_players

    async def _run_ai_turn(self) -> list[Event]:
        """Execute AI turn using the configured handler."""
        if not self.pokemon_ai_handler:
            return []

        game = getattr(self.state, '_game', None)
        if not game:
            if hasattr(self, 'pipeline') and hasattr(self.pipeline, 'game'):
                game = self.pipeline.game

        if not game:
            return []

        return await self.pokemon_ai_handler.take_turn(
            self.pkm_turn_state.active_player_id,
            self.state,
            game
        )

    # ---- MTG compatibility ----

    async def _run_beginning_phase(self) -> list[Event]:
        return []

    async def _run_combat_phase(self) -> list[Event]:
        return []

    async def _run_ending_phase(self) -> list[Event]:
        return []

    @property
    def turn_number(self) -> int:
        return self.pkm_turn_state.turn_number

    @property
    def active_player(self) -> Optional[str]:
        return self.pkm_turn_state.active_player_id

    @property
    def phase(self) -> Phase:
        phase_map = {
            PokemonPhase.DRAW: Phase.BEGINNING,
            PokemonPhase.MAIN: Phase.PRECOMBAT_MAIN,
            PokemonPhase.ATTACK: Phase.COMBAT,
            PokemonPhase.CHECKUP: Phase.ENDING,
        }
        return phase_map.get(self.pkm_turn_state.phase, Phase.PRECOMBAT_MAIN)

    @property
    def step(self) -> Step:
        phase_map = {
            PokemonPhase.DRAW: Step.DRAW,
            PokemonPhase.MAIN: Step.MAIN,
            PokemonPhase.ATTACK: Step.DECLARE_ATTACKERS,
            PokemonPhase.CHECKUP: Step.END_STEP,
        }
        return phase_map.get(self.pkm_turn_state.phase, Step.MAIN)
