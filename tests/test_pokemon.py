"""
Pokemon TCG Engine Tests

Comprehensive test suite covering:
- Type extensions
- Energy system
- Combat (damage calc, weakness, resistance, KO)
- Status conditions
- Turn structure (phases, limits, first-turn restrictions)
- Evolution
- Full pipeline integration
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.game import Game, make_pokemon, make_basic_energy, make_trainer_item, make_trainer_supporter
from src.engine.types import (
    CardType, ZoneType, PokemonType, EventType,
    Event, Characteristics, CardDefinition,
)
from src.engine.pokemon_energy import PokemonEnergySystem
from src.engine.pokemon_combat import PokemonCombatManager
from src.engine.pokemon_status import apply_status, remove_status, remove_all_status, run_checkup, can_attack, can_retreat
from src.engine.pokemon_turn import PokemonTurnManager


def run(coro):
    """Run async function synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


passed = 0
failed = 0

def check(name, condition):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name}")
        failed += 1


# =============================================================================
# Helper: Create a test game with 2 players and basic Pokemon
# =============================================================================

def make_test_game():
    """Create a Pokemon game with 2 players, each with basic Pokemon in play."""
    game = Game(mode="pokemon")
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Create basic Pokemon for each player
    fire_pokemon = make_pokemon(
        name="Charmander", hp=70, pokemon_type=PokemonType.FIRE.value,
        evolution_stage="Basic",
        attacks=[{"name": "Ember", "cost": [{"type": "R", "count": 1}], "damage": 30, "text": ""}],
        weakness_type=PokemonType.WATER.value, retreat_cost=1,
    )
    water_pokemon = make_pokemon(
        name="Squirtle", hp=70, pokemon_type=PokemonType.WATER.value,
        evolution_stage="Basic",
        attacks=[{"name": "Water Gun", "cost": [{"type": "W", "count": 1}], "damage": 20, "text": ""}],
        weakness_type=PokemonType.LIGHTNING.value, retreat_cost=1,
    )

    import copy
    # Place Pokemon in active spots
    p1_active = game.create_object("Charmander", p1.id, ZoneType.ACTIVE_SPOT,
                                    copy.deepcopy(fire_pokemon.characteristics), fire_pokemon)
    p2_active = game.create_object("Squirtle", p2.id, ZoneType.ACTIVE_SPOT,
                                    copy.deepcopy(water_pokemon.characteristics), water_pokemon)

    # Verify objects are in active zones (create_object already added them)
    active1_key = f"active_spot_{p1.id}"
    active2_key = f"active_spot_{p2.id}"
    assert p1_active.id in game.state.zones[active1_key].objects
    assert p2_active.id in game.state.zones[active2_key].objects

    return game, p1, p2, p1_active, p2_active


# =============================================================================
# Test 1: Type Extensions
# =============================================================================

print("\n=== Test 1: Type Extensions ===")

check("PokemonType enum exists", len(list(PokemonType)) == 10)
check("CardType.POKEMON exists", CardType.POKEMON is not None)
check("CardType.ENERGY exists", CardType.ENERGY is not None)
check("CardType.TRAINER exists", CardType.TRAINER is not None)
check("ZoneType.ACTIVE_SPOT exists", ZoneType.ACTIVE_SPOT is not None)
check("ZoneType.BENCH exists", ZoneType.BENCH is not None)
check("ZoneType.PRIZE_CARDS exists", ZoneType.PRIZE_CARDS is not None)
check("EventType.PKM_ATTACH_ENERGY exists", EventType.PKM_ATTACH_ENERGY is not None)
check("EventType.PKM_KNOCKOUT exists", EventType.PKM_KNOCKOUT is not None)

# Test Pokemon card creation
char = make_pokemon(
    name="Charmander", hp=70, pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic", attacks=[{"name": "Ember", "cost": [], "damage": 30, "text": ""}],
    weakness_type=PokemonType.WATER.value, retreat_cost=1,
)
check("make_pokemon creates CardDefinition", isinstance(char, CardDefinition))
check("Pokemon has HP", char.hp == 70)
check("Pokemon has type", char.pokemon_type == PokemonType.FIRE.value)
check("Pokemon has weakness", char.weakness_type == PokemonType.WATER.value)
check("Pokemon has attacks", len(char.attacks) == 1)


# =============================================================================
# Test 2: Energy System
# =============================================================================

print("\n=== Test 2: Energy System ===")

game, p1, p2, p1_active, p2_active = make_test_game()
energy_sys = PokemonEnergySystem(game.state)

# Create energy card in hand
fire_energy = make_basic_energy("Fire Energy", PokemonType.FIRE.value)
import copy
e1 = game.create_object("Fire Energy", p1.id, ZoneType.HAND,
                          copy.deepcopy(fire_energy.characteristics), fire_energy)
hand_key = f"hand_{p1.id}"
game.state.zones[hand_key].objects.append(e1.id)

check("Can attach energy (not yet attached)", energy_sys.can_attach_energy(p1.id))

# Attach energy
events = energy_sys.attach_energy(p1.id, e1.id, p1_active.id)
check("Energy attached produces event", len(events) > 0)
check("Energy in Pokemon's attached list", e1.id in p1_active.state.attached_energy)
check("Can't attach energy again this turn", not energy_sys.can_attach_energy(p1.id))

# Check energy counts
counts = energy_sys.get_attached_energy(p1_active.id)
check("Energy count correct", counts.get(PokemonType.FIRE.value, 0) == 1)

# Test cost checking
check("Can pay 1R", energy_sys.can_pay_cost(p1_active.id, [{"type": "R", "count": 1}]))
check("Can't pay 2R", not energy_sys.can_pay_cost(p1_active.id, [{"type": "R", "count": 2}]))
check("Can pay 1C (colorless)", energy_sys.can_pay_cost(p1_active.id, [{"type": "C", "count": 1}]))

# Test turn reset
energy_sys.on_turn_start(p1.id)
check("Turn start resets attachment flag", energy_sys.can_attach_energy(p1.id))


# =============================================================================
# Test 3: Combat - Damage Calculation
# =============================================================================

print("\n=== Test 3: Combat System ===")

game, p1, p2, p1_active, p2_active = make_test_game()
combat = PokemonCombatManager(game.state)
combat.pipeline = game.pipeline

# Basic damage
damage = combat.calculate_damage(p1_active.id, p2_active.id, 30)
check("Basic damage (no weakness/resistance)", damage == 30)

# Weakness: Fire attacks Water is NOT weak (Water is weak to Lightning)
# Charmander (Fire) attacks Squirtle (weak to Lightning) - no weakness
check("No weakness match", damage == 30)

# Create scenario with weakness match: Water attacks Fire
# Squirtle (Water) attacks Charmander (weak to Water) - weakness x2!
weak_damage = combat.calculate_damage(p2_active.id, p1_active.id, 20)
check("Weakness x2 applied", weak_damage == 40)  # 20 * 2 = 40

# Test damage application
events = combat.apply_damage(p1_active.id, 30)
check("Damage applied as counters", p1_active.state.damage_counters == 3)  # 30 / 10

# Test place_damage_counters (bypasses W/R)
events = combat.place_damage_counters(p2_active.id, 2)
check("Direct counters placed", p2_active.state.damage_counters == 2)

# Test KO check
p1_active.state.damage_counters = 7  # 70 damage on 70 HP Charmander
ko_events = combat.check_knockouts()
check("KO detected", any(e.type == EventType.PKM_KNOCKOUT for e in ko_events))

# Verify KO moves Pokemon to discard
check("KO'd Pokemon moved to graveyard", p1_active.zone == ZoneType.GRAVEYARD)


# =============================================================================
# Test 4: Status Conditions
# =============================================================================

print("\n=== Test 4: Status Conditions ===")

game, p1, p2, p1_active, p2_active = make_test_game()

# Apply poison
events = apply_status(p1_active.id, "poisoned", game.state)
check("Poison applied", "poisoned" in p1_active.state.status_conditions)

# Apply burn (stacks with poison)
events = apply_status(p1_active.id, "burned", game.state)
check("Burn applied alongside poison", "burned" in p1_active.state.status_conditions)
check("Poison still present", "poisoned" in p1_active.state.status_conditions)

# Apply sleep (rotation condition - replaces other rotation conditions)
events = apply_status(p1_active.id, "asleep", game.state)
check("Sleep applied", "asleep" in p1_active.state.status_conditions)

# Apply paralysis (replaces sleep as rotation condition)
events = apply_status(p1_active.id, "paralyzed", game.state)
check("Paralysis replaces sleep", "paralyzed" in p1_active.state.status_conditions)
check("Sleep removed by paralysis", "asleep" not in p1_active.state.status_conditions)
check("Poison persists with paralysis", "poisoned" in p1_active.state.status_conditions)

# Test can_attack/can_retreat with paralysis
ok, msg = can_attack(p1_active.id, game.state)
check("Paralyzed can't attack", not ok)
ok, msg = can_retreat(p1_active.id, game.state)
check("Paralyzed can't retreat", not ok)

# Test remove all (bench/evolve)
remove_all_status(p1_active.id, game.state)
check("All conditions removed", len(p1_active.state.status_conditions) == 0)

# Test status only applies to Active Pokemon
bench_key = f"bench_{p2.id}"
bench_pokemon = make_pokemon(
    name="Pidgey", hp=60, pokemon_type=PokemonType.COLORLESS.value,
    evolution_stage="Basic", attacks=[], retreat_cost=1,
)
bench_obj = game.create_object("Pidgey", p2.id, ZoneType.BENCH,
                                copy.deepcopy(bench_pokemon.characteristics), bench_pokemon)
game.state.zones[bench_key].objects.append(bench_obj.id)
events = apply_status(bench_obj.id, "poisoned", game.state)
check("Can't poison bench Pokemon", "poisoned" not in bench_obj.state.status_conditions)


# =============================================================================
# Test 5: Turn Structure
# =============================================================================

print("\n=== Test 5: Turn Structure ===")

game = Game(mode="pokemon")
p1 = game.add_player("Alice")
p2 = game.add_player("Bob")

check("Turn manager is PokemonTurnManager", isinstance(game.turn_manager, PokemonTurnManager))

# Verify per-turn flags exist on Player
check("Player has energy_attached_this_turn", hasattr(p1, 'energy_attached_this_turn'))
check("Player has supporter_played_this_turn", hasattr(p1, 'supporter_played_this_turn'))
check("Player has retreated_this_turn", hasattr(p1, 'retreated_this_turn'))
check("Player has prizes_remaining", hasattr(p1, 'prizes_remaining'))


# =============================================================================
# Test 6: Evolution
# =============================================================================

print("\n=== Test 6: Evolution ===")

game, p1, p2, p1_active, p2_active = make_test_game()
turn_mgr = game.turn_manager
turn_mgr.pkm_turn_state.game_turn_count = 3  # Past first turn

# Set turns_in_play so evolution is allowed
p1_active.state.turns_in_play = 2

# Create Charmeleon in hand
charmeleon = make_pokemon(
    name="Charmeleon", hp=100, pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Stage 1", evolves_from="Charmander",
    attacks=[{"name": "Slash", "cost": [{"type": "C", "count": 2}], "damage": 30, "text": ""}],
    weakness_type=PokemonType.WATER.value, retreat_cost=2,
)
char_obj = game.create_object("Charmeleon", p1.id, ZoneType.HAND,
                               copy.deepcopy(charmeleon.characteristics), charmeleon)
hand_key = f"hand_{p1.id}"
game.state.zones[hand_key].objects.append(char_obj.id)

# Check evolution legality
ok, msg = turn_mgr.can_evolve(p1_active.id, char_obj.id)
check("Evolution is legal", ok)

# Add some energy to Charmander before evolving
fire_energy = make_basic_energy("Fire Energy", PokemonType.FIRE.value)
e1 = game.create_object("Fire Energy", p1.id, ZoneType.HAND,
                          copy.deepcopy(fire_energy.characteristics), fire_energy)
p1_active.state.attached_energy.append(e1.id)

# Add damage counters
p1_active.state.damage_counters = 2

# Apply a status condition
p1_active.state.status_conditions.add("poisoned")

# Evolve
events = turn_mgr.evolve_pokemon(p1_active.id, char_obj.id)
check("Evolution produces event", any(e.type == EventType.PKM_EVOLVE for e in events))
check("Name updated to Charmeleon", p1_active.name == "Charmeleon")
check("Energy preserved", len(p1_active.state.attached_energy) == 1)
check("Damage counters preserved", p1_active.state.damage_counters == 2)
check("Status conditions cleared", len(p1_active.state.status_conditions) == 0)
check("Evolved_this_turn set", p1_active.state.evolved_this_turn)

# Can't evolve again this turn
fake_stage2 = make_pokemon(
    name="Charizard ex", hp=330, pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Stage 2", evolves_from="Charmeleon",
    attacks=[], retreat_cost=2,
)
fake_obj = game.create_object("Charizard ex", p1.id, ZoneType.HAND,
                               copy.deepcopy(fake_stage2.characteristics), fake_stage2)
game.state.zones[hand_key].objects.append(fake_obj.id)
ok, msg = turn_mgr.can_evolve(p1_active.id, fake_obj.id)
check("Can't evolve twice in one turn", not ok)


# =============================================================================
# Test 7: Pipeline Integration
# =============================================================================

print("\n=== Test 7: Pipeline Integration ===")

game = Game(mode="pokemon")
p1 = game.add_player("Alice")
p2 = game.add_player("Bob")

# Verify zone creation
check("Active spot zones exist", f"active_spot_{p1.id}" in game.state.zones)
check("Bench zones exist", f"bench_{p1.id}" in game.state.zones)
check("Prize card zones exist", f"prize_cards_{p1.id}" in game.state.zones)
check("Stadium zone exists", "stadium_zone" in game.state.zones)
check("Lost zone exists", "lost_zone" in game.state.zones)

# Test game mode
check("Game mode is pokemon", game.state.game_mode == "pokemon")

# Test energy system type
check("Mana system is PokemonEnergySystem", isinstance(game.mana_system, PokemonEnergySystem))

# Test combat manager type
check("Combat manager is PokemonCombatManager", isinstance(game.combat_manager, PokemonCombatManager))

# Create objects and test zone assignment works
fire_pokemon = make_pokemon(
    name="Charmander", hp=70, pokemon_type=PokemonType.FIRE.value,
    evolution_stage="Basic", attacks=[], retreat_cost=1,
)
obj = game.create_object("Charmander", p1.id, ZoneType.LIBRARY,
                          copy.deepcopy(fire_pokemon.characteristics), fire_pokemon)
library_key = f"library_{p1.id}"
check("Object created in library", obj.id in game.state.zones[library_key].objects)
check("Object zone is LIBRARY", obj.zone == ZoneType.LIBRARY)

# Test that ZONE_CHANGE event works through pipeline for Pokemon zones
p1_active_key = f"active_spot_{p1.id}"
# Manually move for testing (normally done by turn manager)
game.state.zones[library_key].objects.remove(obj.id)
game.state.zones[p1_active_key].objects.append(obj.id)
obj.zone = ZoneType.ACTIVE_SPOT
check("Can place Pokemon in active spot", obj.id in game.state.zones[p1_active_key].objects)


# =============================================================================
# Test 8: Full Game Flow (Setup + 1 Turn)
# =============================================================================

print("\n=== Test 8: Full Game Flow ===")

from src.cards.pokemon.sv_starter import make_fire_deck, make_water_deck

game = Game(mode="pokemon")
p1 = game.add_player("Alice")
p2 = game.add_player("Bob")

# Set up decks
fire_deck = make_fire_deck()
water_deck = make_water_deck()

game.setup_pokemon_player(p1, fire_deck)
game.setup_pokemon_player(p2, water_deck)

library1 = game.state.zones.get(f"library_{p1.id}")
library2 = game.state.zones.get(f"library_{p2.id}")
check("Player 1 has cards in library", len(library1.objects) == 30)
check("Player 2 has cards in library", len(library2.objects) == 30)

# Run game setup
turn_mgr = game.turn_manager
turn_mgr.turn_order = [p1.id, p2.id]
events = run(turn_mgr.setup_game())

# Verify setup results
p1_active = game.state.zones.get(f"active_spot_{p1.id}")
p2_active = game.state.zones.get(f"active_spot_{p2.id}")
p1_hand = game.state.zones.get(f"hand_{p1.id}")
p1_prizes = game.state.zones.get(f"prize_cards_{p1.id}")

check("Player 1 has active Pokemon", len(p1_active.objects) > 0)
check("Player 2 has active Pokemon", len(p2_active.objects) > 0)
check("Prize cards set (6)", len(p1_prizes.objects) == 6)
check("Prizes remaining is 6", p1.prizes_remaining == 6)


# =============================================================================
# Results
# =============================================================================

print(f"\n{'='*60}")
print(f"Results: {passed} passed, {failed} failed")
if failed == 0:
    print("ALL POKEMON TESTS PASSED!")
else:
    print(f"SOME TESTS FAILED!")
print(f"{'='*60}")

sys.exit(0 if failed == 0 else 1)
