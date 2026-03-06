"""
Pokemon Status Conditions

Implements all 5 status conditions as interceptors:
- Poisoned: 1 damage counter per checkup. Can stack with Burned.
- Burned: 2 damage counters per checkup, flip: heads = cured.
- Asleep: Can't attack/retreat. Flip each checkup: heads = wake.
- Paralyzed: Can't attack/retreat. Auto-cures after owner's next turn.
- Confused: On attack, flip: tails = 3 damage counters to self, turn ends.

Rules:
- Asleep/Confused/Paralyzed are mutually exclusive (replace each other).
- Poisoned/Burned can coexist with each other AND with one rotation condition.
- Moving to Bench or evolving removes ALL conditions.
"""

import random
from typing import Optional

from .types import (
    GameState, GameObject, Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    ZoneType, CardType, new_id,
)

# Rotation conditions are mutually exclusive
ROTATION_CONDITIONS = {'asleep', 'confused', 'paralyzed'}
# Marker conditions can stack with rotation and each other
MARKER_CONDITIONS = {'poisoned', 'burned'}
ALL_CONDITIONS = ROTATION_CONDITIONS | MARKER_CONDITIONS


def apply_status(pokemon_id: str, condition: str, state: GameState) -> list[Event]:
    """
    Apply a status condition to a Pokemon.

    Handles mutual exclusivity for rotation conditions.
    """
    pokemon = state.objects.get(pokemon_id)
    if not pokemon or CardType.POKEMON not in pokemon.characteristics.types:
        return []

    # Only apply to Active Pokemon (bench Pokemon can't be statused)
    if pokemon.zone != ZoneType.ACTIVE_SPOT:
        return []

    condition = condition.lower()
    if condition not in ALL_CONDITIONS:
        return []

    # If applying a rotation condition, remove existing rotation condition
    if condition in ROTATION_CONDITIONS:
        pokemon.state.status_conditions -= ROTATION_CONDITIONS

    pokemon.state.status_conditions.add(condition)

    # Track when paralysis was applied for correct cure timing
    if condition == 'paralyzed':
        turn_number = getattr(state, 'turn_number', 0) if hasattr(state, 'turn_number') else 0
        pokemon.state.paralyzed_on_turn = turn_number

    return [Event(
        type=EventType.PKM_APPLY_STATUS,
        payload={
            'pokemon_id': pokemon_id,
            'condition': condition,
        },
        source=pokemon_id,
    )]


def remove_status(pokemon_id: str, condition: str, state: GameState) -> list[Event]:
    """Remove a specific status condition."""
    pokemon = state.objects.get(pokemon_id)
    if not pokemon:
        return []

    condition = condition.lower()
    pokemon.state.status_conditions.discard(condition)

    return [Event(
        type=EventType.PKM_REMOVE_STATUS,
        payload={
            'pokemon_id': pokemon_id,
            'condition': condition,
        },
        source=pokemon_id,
    )]


def remove_all_status(pokemon_id: str, state: GameState) -> list[Event]:
    """Remove all status conditions (e.g., when evolving or retreating to bench)."""
    pokemon = state.objects.get(pokemon_id)
    if not pokemon:
        return []

    events = []
    for condition in list(pokemon.state.status_conditions):
        pokemon.state.status_conditions.discard(condition)
        events.append(Event(
            type=EventType.PKM_REMOVE_STATUS,
            payload={'pokemon_id': pokemon_id, 'condition': condition},
            source=pokemon_id,
        ))
    return events


def run_checkup(state: GameState, pipeline=None) -> list[Event]:
    """
    Run between-turns checkup for all Pokemon.

    Order: Poison -> Burn -> other checks -> KO check
    """
    events = []

    # Process checkup for all active Pokemon
    for zone_key, zone in state.zones.items():
        if zone.type != ZoneType.ACTIVE_SPOT:
            continue
        for obj_id in list(zone.objects):
            obj = state.objects.get(obj_id)
            if not obj or CardType.POKEMON not in obj.characteristics.types:
                continue

            # Poison: 1 damage counter
            if 'poisoned' in obj.state.status_conditions:
                obj.state.damage_counters += 1
                poison_event = Event(
                    type=EventType.PKM_CHECKUP_POISON,
                    payload={
                        'pokemon_id': obj_id,
                        'counters': 1,
                        'total_counters': obj.state.damage_counters,
                    },
                    source=obj_id,
                )
                if pipeline:
                    pipeline.emit(poison_event)
                events.append(poison_event)

            # Burn: 2 damage counters, then flip to cure
            if 'burned' in obj.state.status_conditions:
                obj.state.damage_counters += 2
                burn_event = Event(
                    type=EventType.PKM_CHECKUP_BURN,
                    payload={
                        'pokemon_id': obj_id,
                        'counters': 2,
                        'total_counters': obj.state.damage_counters,
                    },
                    source=obj_id,
                )
                if pipeline:
                    pipeline.emit(burn_event)
                events.append(burn_event)

                # Flip to cure burn
                flip = random.choice(['heads', 'tails'])
                flip_event = Event(
                    type=EventType.PKM_COIN_FLIP,
                    payload={'result': flip, 'reason': 'burn_cure', 'pokemon_id': obj_id},
                    source=obj_id,
                )
                events.append(flip_event)
                if flip == 'heads':
                    events.extend(remove_status(obj_id, 'burned', state))

            # Sleep: flip to wake
            if 'asleep' in obj.state.status_conditions:
                flip = random.choice(['heads', 'tails'])
                sleep_event = Event(
                    type=EventType.PKM_CHECKUP_SLEEP,
                    payload={
                        'pokemon_id': obj_id,
                        'flip_result': flip,
                    },
                    source=obj_id,
                )
                if pipeline:
                    pipeline.emit(sleep_event)
                events.append(sleep_event)

                if flip == 'heads':
                    obj.state.status_conditions.discard('asleep')

            # Paralysis: cured at the end of the affected player's next turn.
            # We track paralyzed_on_turn; cure only after the owner has had a turn.
            if 'paralyzed' in obj.state.status_conditions:
                para_event = Event(
                    type=EventType.PKM_CHECKUP_PARALYSIS,
                    payload={'pokemon_id': obj_id},
                    source=obj_id,
                )
                if pipeline:
                    pipeline.emit(para_event)
                events.append(para_event)
                paralyzed_on = getattr(obj.state, 'paralyzed_on_turn', 0)
                current_turn = getattr(state, 'turn_number', 0) if hasattr(state, 'turn_number') else 0
                if current_turn > paralyzed_on:
                    obj.state.status_conditions.discard('paralyzed')
                    events.extend(remove_status(obj_id, 'paralyzed', state))

    return events


def can_retreat(pokemon_id: str, state: GameState) -> tuple[bool, str]:
    """Check if a Pokemon can retreat based on status conditions."""
    pokemon = state.objects.get(pokemon_id)
    if not pokemon:
        return False, "Pokemon not found"

    if 'asleep' in pokemon.state.status_conditions:
        return False, "Pokemon is Asleep"
    if 'paralyzed' in pokemon.state.status_conditions:
        return False, "Pokemon is Paralyzed"

    return True, ""


def can_attack(pokemon_id: str, state: GameState) -> tuple[bool, str]:
    """Check if a Pokemon can attack based on status conditions."""
    pokemon = state.objects.get(pokemon_id)
    if not pokemon:
        return False, "Pokemon not found"

    if 'asleep' in pokemon.state.status_conditions:
        return False, "Pokemon is Asleep"
    if 'paralyzed' in pokemon.state.status_conditions:
        return False, "Pokemon is Paralyzed"

    # Confused Pokemon CAN attack, but must flip a coin (handled in combat)
    return True, ""
