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

if __name__ != "__main__":
    import pytest
    pytest.skip("Run directly: `python tests/test_pokemon.py`", allow_module_level=True)

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
check("Player 1 has cards in library", len(library1.objects) == 60)
check("Player 2 has cards in library", len(library2.objects) == 60)

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
# Test 9: Phase 4 PendingChoice migration — Isperia ex / Supreme Judgment
# =============================================================================
#
# Verifies the bench-swap attack now emits a PendingChoice over the
# opponent's bench instead of auto-picking the lowest-HP body. Three
# scenarios: human path (choice stays pending), heuristic preservation
# (callback_data['heuristic_pick'] still matches the old min-HP pick),
# and empty short-circuit (no bench => no-op).

print("\n=== Test 9: Phase 4 PendingChoice — Supreme Judgment bench-swap ===")

from src.cards.pokemon.beyond.ravnica.azorius import (
    ISPERIA_SUPREME_JUDGE_EX,
    _supreme_judgment_effect,
)


def _make_judgment_scenario(*, bench_specs: list[tuple[str, int, int]]):
    """Build a 2-player Pokemon game with Isperia ex Active for p1 and a
    populated/empty bench for p2.

    ``bench_specs`` = ``[(name, max_hp, damage_counters), ...]``. Empty
    list means p2 has no bench Pokemon — the short-circuit scenario.
    """
    import copy as _copy
    game = Game(mode="pokemon")
    p1 = game.add_player("Judge")
    p2 = game.add_player("Defendant")

    isperia_obj = game.create_object(
        ISPERIA_SUPREME_JUDGE_EX.name, p1.id, ZoneType.ACTIVE_SPOT,
        _copy.deepcopy(ISPERIA_SUPREME_JUDGE_EX.characteristics),
        ISPERIA_SUPREME_JUDGE_EX,
    )

    # Opponent active — must exist for the swap to be legal.
    opp_active_def = make_pokemon(
        name="Squirtle", hp=70, pokemon_type=PokemonType.WATER.value,
        evolution_stage="Basic",
        attacks=[{"name": "Water Gun", "cost": [{"type": "W", "count": 1}],
                  "damage": 20, "text": ""}],
        weakness_type=PokemonType.LIGHTNING.value, retreat_cost=1,
    )
    opp_active = game.create_object(
        opp_active_def.name, p2.id, ZoneType.ACTIVE_SPOT,
        _copy.deepcopy(opp_active_def.characteristics), opp_active_def,
    )

    bench_objs = []
    for name, max_hp, damage in bench_specs:
        cdef = make_pokemon(
            name=name, hp=max_hp, pokemon_type=PokemonType.GRASS.value,
            evolution_stage="Basic",
            attacks=[{"name": "Stub", "cost": [{"type": "G", "count": 1}],
                      "damage": 10, "text": ""}],
            weakness_type=PokemonType.FIRE.value, retreat_cost=1,
        )
        bobj = game.create_object(
            cdef.name, p2.id, ZoneType.BENCH,
            _copy.deepcopy(cdef.characteristics), cdef,
        )
        bobj.state.damage_counters = damage
        bench_objs.append(bobj)

    return game, p1, p2, isperia_obj, opp_active, bench_objs


# --- Scenario A: Human controller — choice stays pending ---------------------

game, p1, p2, isperia, opp_active, bench_objs = _make_judgment_scenario(
    bench_specs=[
        ("Hurt Hopper", 60, 5),   # current HP = 60 - 50 = 10  (weakest)
        ("Healthy Hopper", 90, 0),  # current HP = 90
    ],
)
weakest = bench_objs[0]
healthy = bench_objs[1]

# No AI handler registered → resolver treats both players as humans.
# pkm_force_switch / PKM_SWITCH must NOT happen yet.
opp_active_before = game.state.zones[f"active_spot_{p2.id}"].objects[0]
events = _supreme_judgment_effect(isperia, game.state)

check("Supreme Judgment human path returns no events", events == [])
pc = game.state.pending_choice
check("Pending choice is set", pc is not None)
check("Pending choice type is 'target'", pc is not None and pc.choice_type == "target")
check("Choice belongs to the attacker's controller (p1)",
      pc is not None and pc.player == p1.id)
check("Choice source is the Isperia object",
      pc is not None and pc.source_id == isperia.id)
option_ids = {opt["id"] for opt in (pc.options if pc else [])}
check("Both bench Pokemon are options",
      weakest.id in option_ids and healthy.id in option_ids)
check("Opponent's Active is NOT an option (it's the target of the swap)",
      opp_active.id not in option_ids)
check("Bench swap has not happened yet (human still choosing)",
      game.state.zones[f"active_spot_{p2.id}"].objects[0] == opp_active_before)

# --- Scenario B: Heuristic preservation --------------------------------------
# The original code picked the LOWEST-current-HP bench Pokemon. The
# heuristic_pick in callback_data must reproduce that exactly.

hp_pick = (pc.callback_data or {}).get("heuristic_pick")
check("heuristic_pick is set", hp_pick is not None)
check("heuristic_pick matches the original min-HP pick (weakest body)",
      hp_pick == [weakest.id])

# Sanity-check: tearing down the choice and firing the handler with the
# heuristic produces the swap (this proves the handler is wired right).
handler = (pc.callback_data or {}).get("handler") if pc else None
check("Handler is registered on the choice", handler is not None)
if handler is not None:
    handler_events = handler(pc, [weakest.id], game.state)
    check("Handler swap emits a PKM_SWITCH event",
          len(handler_events) == 1 and handler_events[0].type == EventType.PKM_SWITCH)
    check("After handler runs, weakest bench Pokemon is now Active",
          game.state.zones[f"active_spot_{p2.id}"].objects[0] == weakest.id)
    check("After handler runs, previous Active is on the bench",
          opp_active.id in game.state.zones[f"bench_{p2.id}"].objects)
# Clear the choice after manual resolution so we don't leak state between
# scenarios.
game.state.pending_choice = None

# --- Scenario C: Empty short-circuit ----------------------------------------
# With an empty opponent bench, the effect is a no-op (no choice, no events).

game2, _p1b, _p2b, isperia2, _opp_active2, _benches2 = _make_judgment_scenario(
    bench_specs=[],
)
events2 = _supreme_judgment_effect(isperia2, game2.state)
check("Empty bench short-circuit returns no events", events2 == [])
check("Empty bench leaves pending_choice clear",
      game2.state.pending_choice is None)


# =============================================================================
# Test 10: Phase 4 PendingChoice migration — bench-target / heal-target cards
# =============================================================================
#
# Migrates: Switch, Boss's Orders, Potion, Plaxcaster Frogling,
# Cytoplast Manipulator, Trygon Predator, Emmara, Vitu-Ghazi. For each card we
# verify three scenarios: human path (no AI registered → choice stays
# pending), heuristic preservation (callback_data['heuristic_pick'] matches
# the original deterministic pick), and empty short-circuit (no candidates
# = no-op).
#
# Pattern: use ``game = Game(mode="pokemon")``, ``game.add_player`` without
# registering an AI handler → ``ai_players`` is empty → all players are
# humans → resolver leaves ``state.pending_choice`` set.

print("\n=== Test 10: Phase 4 PendingChoice — additional target-pick cards ===")

import copy as _copy
from src.cards.pokemon.sv_starter import (
    _switch_effect, _boss_orders_effect, _potion_effect,
)
from src.cards.pokemon.beyond.ravnica.simic import (
    _plaxcaster_frogling_effect, PLAXCASTER_FROGLING,
    _cytoplast_manipulator_effect, CYTOPLAST_MANIPULATOR,
    _reef_sunder_effect, TRYGON_PREDATOR,
)
from src.cards.pokemon.beyond.ravnica.selesnya import (
    _soul_of_the_accord_effect, EMMARA_SOUL_OF_THE_ACCORD,
    _vitu_ghazi_effect,
)


def _make_basic_pokemon(name, hp, ptype, evolution_stage="Basic"):
    return make_pokemon(
        name=name, hp=hp, pokemon_type=ptype,
        evolution_stage=evolution_stage,
        attacks=[{"name": "Stub", "cost": [{"type": "C", "count": 1}],
                  "damage": 10, "text": ""}],
        weakness_type=PokemonType.PSYCHIC.value, retreat_cost=1,
    )


def _make_game_p1_active(active_def):
    """Build a 2-player Pokemon game with ``active_def`` as p1 Active."""
    game = Game(mode="pokemon")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    active = game.create_object(
        active_def.name, p1.id, ZoneType.ACTIVE_SPOT,
        _copy.deepcopy(active_def.characteristics), active_def,
    )
    # p2 needs an Active too for legal state.
    opp_def = _make_basic_pokemon("OppActive", 70, PokemonType.WATER.value)
    opp_active = game.create_object(
        opp_def.name, p2.id, ZoneType.ACTIVE_SPOT,
        _copy.deepcopy(opp_def.characteristics), opp_def,
    )
    return game, p1, p2, active, opp_active


def _bench_pokemon(game, player_id, name, hp, ptype, damage=0,
                   evolution_stage="Basic"):
    cdef = _make_basic_pokemon(name, hp, ptype, evolution_stage)
    obj = game.create_object(
        cdef.name, player_id, ZoneType.BENCH,
        _copy.deepcopy(cdef.characteristics), cdef,
    )
    obj.state.damage_counters = damage
    return obj


# --- Switch ---------------------------------------------------------------
print("\n--- Switch ---")
# Build with a stand-in Active and a populated bench
game = Game(mode="pokemon")
p1 = game.add_player("P1"); p2 = game.add_player("P2")
active_def = _make_basic_pokemon("StarterActive", 60, PokemonType.FIRE.value)
game.create_object(active_def.name, p1.id, ZoneType.ACTIVE_SPOT,
                   _copy.deepcopy(active_def.characteristics), active_def)
game.create_object(active_def.name, p2.id, ZoneType.ACTIVE_SPOT,
                   _copy.deepcopy(active_def.characteristics), active_def)
weak_bench = _bench_pokemon(game, p1.id, "WeakBench", 60, PokemonType.GRASS.value)
strong_bench = _bench_pokemon(game, p1.id, "StrongBench", 120, PokemonType.WATER.value)
event = Event(type=EventType.PKM_PLAY_ITEM, payload={'player': p1.id})
events = _switch_effect(event, game.state)
check("Switch human path returns no events", events == [])
pc = game.state.pending_choice
check("Switch sets a pending_choice", pc is not None)
check("Switch choice is 'target' type", pc is not None and pc.choice_type == "target")
check("Switch choice belongs to caster (p1)",
      pc is not None and pc.player == p1.id)
opt_ids = {o["id"] for o in (pc.options if pc else [])}
check("Switch options include both bench Pokemon",
      weak_bench.id in opt_ids and strong_bench.id in opt_ids)
hp_pick = (pc.callback_data or {}).get("heuristic_pick")
check("Switch heuristic_pick is the higher-HP bench",
      hp_pick == [strong_bench.id])
handler = (pc.callback_data or {}).get("handler")
if handler:
    handler_events = handler(pc, [strong_bench.id], game.state)
    check("Switch handler emits PKM_SWITCH",
          len(handler_events) == 1 and handler_events[0].type == EventType.PKM_SWITCH)
    check("Switch handler promotes the chosen bench",
          game.state.zones[f"active_spot_{p1.id}"].objects[0] == strong_bench.id)
game.state.pending_choice = None

# Empty short-circuit: no bench
game_e = Game(mode="pokemon")
p1e = game_e.add_player("P1"); p2e = game_e.add_player("P2")
game_e.create_object(active_def.name, p1e.id, ZoneType.ACTIVE_SPOT,
                     _copy.deepcopy(active_def.characteristics), active_def)
game_e.create_object(active_def.name, p2e.id, ZoneType.ACTIVE_SPOT,
                     _copy.deepcopy(active_def.characteristics), active_def)
events_e = _switch_effect(Event(type=EventType.PKM_PLAY_ITEM,
                                payload={'player': p1e.id}), game_e.state)
check("Switch empty-bench short-circuit returns no events", events_e == [])
check("Switch empty-bench leaves pending_choice clear",
      game_e.state.pending_choice is None)


# --- Boss's Orders --------------------------------------------------------
print("\n--- Boss's Orders ---")
game = Game(mode="pokemon")
p1 = game.add_player("P1"); p2 = game.add_player("P2")
game.create_object(active_def.name, p1.id, ZoneType.ACTIVE_SPOT,
                   _copy.deepcopy(active_def.characteristics), active_def)
game.create_object(active_def.name, p2.id, ZoneType.ACTIVE_SPOT,
                   _copy.deepcopy(active_def.characteristics), active_def)
opp_weak = _bench_pokemon(game, p2.id, "OppWeak", 60, PokemonType.GRASS.value, damage=4)
opp_strong = _bench_pokemon(game, p2.id, "OppStrong", 120, PokemonType.WATER.value)
event = Event(type=EventType.PKM_PLAY_ITEM, payload={'player': p1.id})
events = _boss_orders_effect(event, game.state)
check("Boss's Orders human path returns no events", events == [])
pc = game.state.pending_choice
check("Boss's Orders pending_choice set", pc is not None)
check("Boss's Orders choice belongs to caster (p1)",
      pc is not None and pc.player == p1.id)
opt_ids = {o["id"] for o in (pc.options if pc else [])}
check("Boss's Orders options include opp bench Pokemon",
      opp_weak.id in opt_ids and opp_strong.id in opt_ids)
hp_pick = (pc.callback_data or {}).get("heuristic_pick")
# Weakest body (opp_weak: 60 HP - 40 damage = 20 HP remaining) wins.
check("Boss's Orders heuristic_pick is the weakest body",
      hp_pick == [opp_weak.id])
game.state.pending_choice = None

# Empty short-circuit: no opp bench
game_e = Game(mode="pokemon")
p1e = game_e.add_player("P1"); p2e = game_e.add_player("P2")
game_e.create_object(active_def.name, p1e.id, ZoneType.ACTIVE_SPOT,
                     _copy.deepcopy(active_def.characteristics), active_def)
game_e.create_object(active_def.name, p2e.id, ZoneType.ACTIVE_SPOT,
                     _copy.deepcopy(active_def.characteristics), active_def)
events_e = _boss_orders_effect(Event(type=EventType.PKM_PLAY_ITEM,
                                     payload={'player': p1e.id}), game_e.state)
check("Boss's Orders empty-bench short-circuit returns no events", events_e == [])


# --- Potion ---------------------------------------------------------------
print("\n--- Potion ---")
game = Game(mode="pokemon")
p1 = game.add_player("P1"); p2 = game.add_player("P2")
active_obj = game.create_object(
    active_def.name, p1.id, ZoneType.ACTIVE_SPOT,
    _copy.deepcopy(active_def.characteristics), active_def,
)
active_obj.state.damage_counters = 2  # 20 damage
game.create_object(active_def.name, p2.id, ZoneType.ACTIVE_SPOT,
                   _copy.deepcopy(active_def.characteristics), active_def)
hurt_bench = _bench_pokemon(game, p1.id, "Hurt", 60, PokemonType.GRASS.value, damage=5)
events = _potion_effect(Event(type=EventType.PKM_PLAY_ITEM,
                              payload={'player': p1.id}), game.state)
check("Potion human path returns no events", events == [])
pc = game.state.pending_choice
check("Potion pending_choice set", pc is not None)
opt_ids = {o["id"] for o in (pc.options if pc else [])}
check("Potion options include both damaged Pokemon",
      active_obj.id in opt_ids and hurt_bench.id in opt_ids)
hp_pick = (pc.callback_data or {}).get("heuristic_pick")
# Most-damaged: hurt_bench (5 counters) > active_obj (2)
check("Potion heuristic_pick is most-damaged Pokemon",
      hp_pick == [hurt_bench.id])
game.state.pending_choice = None

# Empty short-circuit: no damaged Pokemon
game_e = Game(mode="pokemon")
p1e = game_e.add_player("P1"); p2e = game_e.add_player("P2")
game_e.create_object(active_def.name, p1e.id, ZoneType.ACTIVE_SPOT,
                     _copy.deepcopy(active_def.characteristics), active_def)
game_e.create_object(active_def.name, p2e.id, ZoneType.ACTIVE_SPOT,
                     _copy.deepcopy(active_def.characteristics), active_def)
events_e = _potion_effect(Event(type=EventType.PKM_PLAY_ITEM,
                                payload={'player': p1e.id}), game_e.state)
check("Potion empty-damage short-circuit returns no events", events_e == [])


# --- Plaxcaster Frogling --------------------------------------------------
print("\n--- Plaxcaster Frogling ---")
game, p1, p2, plax, _opp = _make_game_p1_active(PLAXCASTER_FROGLING)
healthy = _bench_pokemon(game, p1.id, "Healthy", 90, PokemonType.WATER.value, damage=0)
hurt = _bench_pokemon(game, p1.id, "Hurt", 80, PokemonType.WATER.value, damage=3)
events = _plaxcaster_frogling_effect(plax, game.state)
check("Plaxcaster human path returns no events", events == [])
pc = game.state.pending_choice
check("Plaxcaster pending_choice set", pc is not None)
hp_pick = (pc.callback_data or {}).get("heuristic_pick")
# First DAMAGED bench Pokemon — order matters: healthy first then hurt
# (healthy has 0 damage, hurt has 3), so heuristic picks hurt.
check("Plaxcaster heuristic_pick is first damaged bench Pokemon",
      hp_pick == [hurt.id])
handler = (pc.callback_data or {}).get("handler")
if handler:
    handler_events = handler(pc, [hurt.id], game.state)
    check("Plaxcaster handler emits a PKM_HEAL",
          len(handler_events) == 1 and handler_events[0].type == EventType.PKM_HEAL)
    check("Plaxcaster handler reduces damage counters on target",
          hurt.state.damage_counters == 1)
game.state.pending_choice = None

# Empty short-circuit
game_e, _p1, _p2, plax_e, _opp = _make_game_p1_active(PLAXCASTER_FROGLING)
events_e = _plaxcaster_frogling_effect(plax_e, game_e.state)
check("Plaxcaster empty-bench short-circuit returns no events", events_e == [])


# --- Cytoplast Manipulator -----------------------------------------------
print("\n--- Cytoplast Manipulator ---")
game, p1, p2, cyto, _opp = _make_game_p1_active(CYTOPLAST_MANIPULATOR)
# Cytoplast needs an attached energy on the attacker
energy_def = make_basic_energy("Grass Energy", PokemonType.GRASS.value)
energy_obj = game.create_object(
    energy_def.name, p1.id, ZoneType.BATTLEFIELD,
    _copy.deepcopy(energy_def.characteristics), energy_def,
)
cyto.state.attached_energy.append(energy_obj.id)
bench_a = _bench_pokemon(game, p1.id, "BenchA", 90, PokemonType.GRASS.value)
bench_b = _bench_pokemon(game, p1.id, "BenchB", 120, PokemonType.GRASS.value)
events = _cytoplast_manipulator_effect(cyto, game.state)
check("Cytoplast human path returns no events", events == [])
pc = game.state.pending_choice
check("Cytoplast pending_choice set", pc is not None)
hp_pick = (pc.callback_data or {}).get("heuristic_pick")
check("Cytoplast heuristic_pick is the first bench Pokemon",
      hp_pick == [bench_a.id])
game.state.pending_choice = None

# Empty: no bench
game_e, _p1, _p2, cyto_e, _opp = _make_game_p1_active(CYTOPLAST_MANIPULATOR)
energy_e = game_e.create_object(
    energy_def.name, _p1.id, ZoneType.BATTLEFIELD,
    _copy.deepcopy(energy_def.characteristics), energy_def,
)
cyto_e.state.attached_energy.append(energy_e.id)
events_e = _cytoplast_manipulator_effect(cyto_e, game_e.state)
check("Cytoplast empty-bench short-circuit returns no events", events_e == [])

# Empty: no attached energy
game_e2, _p1, _p2, cyto_e2, _opp = _make_game_p1_active(CYTOPLAST_MANIPULATOR)
_bench_pokemon(game_e2, _p1.id, "BenchX", 90, PokemonType.GRASS.value)
events_e2 = _cytoplast_manipulator_effect(cyto_e2, game_e2.state)
check("Cytoplast no-energy short-circuit returns no events", events_e2 == [])


# --- Trygon Predator (Reef Sunder) ---------------------------------------
print("\n--- Trygon Predator ---")
game, p1, p2, trygon, opp_active = _make_game_p1_active(TRYGON_PREDATOR)
# Opponent Active needs attached energy for Reef Sunder to move
opp_energy = game.create_object(
    energy_def.name, p2.id, ZoneType.BATTLEFIELD,
    _copy.deepcopy(energy_def.characteristics), energy_def,
)
opp_active.state.attached_energy.append(opp_energy.id)
# Two opp bench Pokemon — one with no energy (lowest), one with 1
opp_b_empty = _bench_pokemon(game, p2.id, "OppEmpty", 80, PokemonType.WATER.value)
opp_b_loaded = _bench_pokemon(game, p2.id, "OppLoaded", 80, PokemonType.WATER.value)
loaded_energy = game.create_object(
    energy_def.name, p2.id, ZoneType.BATTLEFIELD,
    _copy.deepcopy(energy_def.characteristics), energy_def,
)
opp_b_loaded.state.attached_energy.append(loaded_energy.id)

events = _reef_sunder_effect(trygon, game.state)
check("Trygon human path returns no events", events == [])
pc = game.state.pending_choice
check("Trygon pending_choice set", pc is not None)
check("Trygon chooser is the caster", pc is not None and pc.player == p1.id)
opt_ids = {o["id"] for o in (pc.options if pc else [])}
check("Trygon options are opp bench Pokemon",
      opp_b_empty.id in opt_ids and opp_b_loaded.id in opt_ids)
hp_pick = (pc.callback_data or {}).get("heuristic_pick")
check("Trygon heuristic_pick is lowest-attached-energy bench",
      hp_pick == [opp_b_empty.id])
game.state.pending_choice = None

# Empty bench → discard energy (legacy fallback)
game_e, _p1, _p2, trygon_e, opp_e = _make_game_p1_active(TRYGON_PREDATOR)
opp_energy_e = game_e.create_object(
    energy_def.name, _p2.id, ZoneType.BATTLEFIELD,
    _copy.deepcopy(energy_def.characteristics), energy_def,
)
opp_e.state.attached_energy.append(opp_energy_e.id)
events_e = _reef_sunder_effect(trygon_e, game_e.state)
check("Trygon empty-bench discards opp energy (no choice)",
      any(ev.type == EventType.PKM_DISCARD_ENERGY for ev in events_e))
check("Trygon empty-bench leaves pending_choice clear",
      game_e.state.pending_choice is None)

# Empty: opp Active has no attached energy
game_e2, _p1, _p2, trygon_e2, opp_e2 = _make_game_p1_active(TRYGON_PREDATOR)
_bench_pokemon(game_e2, _p2.id, "OppBench", 70, PokemonType.WATER.value)
events_e2 = _reef_sunder_effect(trygon_e2, game_e2.state)
check("Trygon no-energy short-circuit returns no events", events_e2 == [])


# --- Emmara, Soul of the Accord ------------------------------------------
print("\n--- Emmara, Soul of the Accord ---")
game, p1, p2, emmara, _opp = _make_game_p1_active(EMMARA_SOUL_OF_THE_ACCORD)
# Need a Grass Energy in deck and a bench Pokemon
grass_energy = game.create_object(
    energy_def.name, p1.id, ZoneType.LIBRARY,
    _copy.deepcopy(energy_def.characteristics), energy_def,
)
library = game.state.zones[f"library_{p1.id}"]
library.objects.append(grass_energy.id)
bench_a = _bench_pokemon(game, p1.id, "BenchA", 90, PokemonType.GRASS.value)
bench_b = _bench_pokemon(game, p1.id, "BenchB", 70, PokemonType.GRASS.value)

events = _soul_of_the_accord_effect(emmara, game.state)
check("Emmara human path returns no events", events == [])
pc = game.state.pending_choice
check("Emmara pending_choice set", pc is not None)
hp_pick = (pc.callback_data or {}).get("heuristic_pick")
check("Emmara heuristic_pick is first bench Pokemon",
      hp_pick == [bench_a.id])
game.state.pending_choice = None

# Empty: no bench
game_e, _p1, _p2, emmara_e, _opp = _make_game_p1_active(EMMARA_SOUL_OF_THE_ACCORD)
grass_e = game_e.create_object(
    energy_def.name, _p1.id, ZoneType.LIBRARY,
    _copy.deepcopy(energy_def.characteristics), energy_def,
)
game_e.state.zones[f"library_{_p1.id}"].objects.append(grass_e.id)
events_e = _soul_of_the_accord_effect(emmara_e, game_e.state)
check("Emmara empty-bench short-circuit returns no events", events_e == [])


# --- Vitu-Ghazi (caster branch) ------------------------------------------
print("\n--- Vitu-Ghazi, the City-Tree ---")
game = Game(mode="pokemon")
p1 = game.add_player("P1"); p2 = game.add_player("P2")
# Both Actives needed
caster_active = game.create_object(
    active_def.name, p1.id, ZoneType.ACTIVE_SPOT,
    _copy.deepcopy(active_def.characteristics), active_def,
)
opp_active = game.create_object(
    active_def.name, p2.id, ZoneType.ACTIVE_SPOT,
    _copy.deepcopy(active_def.characteristics), active_def,
)
# Caster needs 3+ bench
b1 = _bench_pokemon(game, p1.id, "CB1", 90, PokemonType.GRASS.value)
b2 = _bench_pokemon(game, p1.id, "CB2", 90, PokemonType.GRASS.value)
b3 = _bench_pokemon(game, p1.id, "CB3", 90, PokemonType.GRASS.value)
# Give b2 some attached energy to test the lowest-attached heuristic
extra_energy = game.create_object(
    energy_def.name, p1.id, ZoneType.BATTLEFIELD,
    _copy.deepcopy(energy_def.characteristics), energy_def,
)
b2.state.attached_energy.append(extra_energy.id)
# Caster needs energy in hand to attach
hand_energy = game.create_object(
    energy_def.name, p1.id, ZoneType.HAND,
    _copy.deepcopy(energy_def.characteristics), energy_def,
)
game.state.zones[f"hand_{p1.id}"].objects.append(hand_energy.id)

events = _vitu_ghazi_effect(
    Event(type=EventType.PKM_PLAY_ITEM, payload={'player': p1.id}),
    game.state,
)
# Note: heal events still emit synchronously; only the attach is gated by choice.
check("Vitu-Ghazi pending_choice set after caster attach branch",
      game.state.pending_choice is not None)
pc = game.state.pending_choice
check("Vitu-Ghazi caster choice belongs to p1",
      pc is not None and pc.player == p1.id)
opt_ids = {o["id"] for o in (pc.options if pc else [])}
check("Vitu-Ghazi caster options are caster's bench",
      b1.id in opt_ids and b2.id in opt_ids and b3.id in opt_ids)
hp_pick = (pc.callback_data or {}).get("heuristic_pick")
# Lowest-attached: b1 or b3 (both 0), b2 has 1. First-seen wins.
check("Vitu-Ghazi heuristic_pick is a 0-energy bench Pokemon",
      hp_pick is not None and hp_pick[0] in {b1.id, b3.id})
game.state.pending_choice = None

# Empty short-circuit: not enough bench
game_e = Game(mode="pokemon")
p1e = game_e.add_player("P1"); p2e = game_e.add_player("P2")
game_e.create_object(active_def.name, p1e.id, ZoneType.ACTIVE_SPOT,
                     _copy.deepcopy(active_def.characteristics), active_def)
game_e.create_object(active_def.name, p2e.id, ZoneType.ACTIVE_SPOT,
                     _copy.deepcopy(active_def.characteristics), active_def)
_bench_pokemon(game_e, p1e.id, "OnlyOne", 60, PokemonType.GRASS.value)
events_e = _vitu_ghazi_effect(
    Event(type=EventType.PKM_PLAY_ITEM, payload={'player': p1e.id}),
    game_e.state,
)
check("Vitu-Ghazi <3 bench leaves pending_choice clear",
      game_e.state.pending_choice is None)


# =============================================================================
# Test 11: Residual deterministic-pick cards migrated to PendingChoice
# =============================================================================
#
# Migrated: Selesnya Cluestone (wide-board bench attach), Skyknight Vanguard
# (place damage on opp bench), Burning-Tree Emissary (Cascade attach to
# own bench).
#
# Same pattern as Test 10: human path leaves a pending_choice; the
# callback_data's heuristic_pick preserves the v1 deterministic choice
# so AI behavior is unchanged.

print("\n=== Test 11: Residual deterministic-pick migrations ===")

from src.cards.pokemon.beyond.ravnica.selesnya import (
    _selesnya_cluestone_effect, SELESNYA_CLUESTONE,
)
from src.cards.pokemon.beyond.ravnica.boros import (
    _skyknight_vanguard_effect, SKYKNIGHT_VANGUARD,
)
from src.cards.pokemon.beyond.ravnica.gruul import (
    _cascade_attach_effect, BURNING_TREE_EMISSARY,
)


# --- Selesnya Cluestone --------------------------------------------------
print("\n--- Selesnya Cluestone ---")
game = Game(mode="pokemon")
p1 = game.add_player("P1"); p2 = game.add_player("P2")
game.create_object(active_def.name, p1.id, ZoneType.ACTIVE_SPOT,
                   _copy.deepcopy(active_def.characteristics), active_def)
game.create_object(active_def.name, p2.id, ZoneType.ACTIVE_SPOT,
                   _copy.deepcopy(active_def.characteristics), active_def)
# Three bench Pokemon to trigger the wide-board branch (>=3)
b1 = _bench_pokemon(game, p1.id, "SLB1", 90, PokemonType.GRASS.value)
b2 = _bench_pokemon(game, p1.id, "SLB2", 90, PokemonType.GRASS.value)
b3 = _bench_pokemon(game, p1.id, "SLB3", 90, PokemonType.GRASS.value)
# Give b2 some attached energy so b1/b3 (0 energy) are the heuristic pick
loaded_energy = game.create_object(
    energy_def.name, p1.id, ZoneType.BATTLEFIELD,
    _copy.deepcopy(energy_def.characteristics), energy_def,
)
b2.state.attached_energy.append(loaded_energy.id)
# Energy cards in deck: one Grass + one Fighting
grass_e = make_basic_energy("Grass Energy", PokemonType.GRASS.value)
fighting_e = make_basic_energy("Fighting Energy", PokemonType.FIGHTING.value)
grass_obj = game.create_object(grass_e.name, p1.id, ZoneType.LIBRARY,
                               _copy.deepcopy(grass_e.characteristics), grass_e)
fighting_obj = game.create_object(fighting_e.name, p1.id, ZoneType.LIBRARY,
                                  _copy.deepcopy(fighting_e.characteristics), fighting_e)
library = game.state.zones[f"library_{p1.id}"]
library.objects.extend([grass_obj.id, fighting_obj.id])

events = _selesnya_cluestone_effect(
    Event(type=EventType.PKM_PLAY_ITEM, payload={'player': p1.id}),
    game.state,
)
check("Selesnya Cluestone human path returns no events", events == [])
pc = game.state.pending_choice
check("Selesnya Cluestone sets a pending_choice", pc is not None)
check("Selesnya Cluestone choice belongs to caster (p1)",
      pc is not None and pc.player == p1.id)
opt_ids = {o["id"] for o in (pc.options if pc else [])}
check("Selesnya Cluestone options are caster's bench",
      b1.id in opt_ids and b2.id in opt_ids and b3.id in opt_ids)
hp_pick = (pc.callback_data or {}).get("heuristic_pick")
# Lowest-attached: b1 or b3 (both 0 energy); b2 has 1.
check("Selesnya Cluestone heuristic_pick is a 0-energy bench Pokemon",
      hp_pick is not None and hp_pick[0] in {b1.id, b3.id})
game.state.pending_choice = None

# Empty short-circuit: only 2 bench (<3) → no attach branch
game_e = Game(mode="pokemon")
p1e = game_e.add_player("P1"); p2e = game_e.add_player("P2")
game_e.create_object(active_def.name, p1e.id, ZoneType.ACTIVE_SPOT,
                     _copy.deepcopy(active_def.characteristics), active_def)
game_e.create_object(active_def.name, p2e.id, ZoneType.ACTIVE_SPOT,
                     _copy.deepcopy(active_def.characteristics), active_def)
_bench_pokemon(game_e, p1e.id, "OnlyOne", 60, PokemonType.GRASS.value)
_bench_pokemon(game_e, p1e.id, "OnlyTwo", 60, PokemonType.GRASS.value)
grass_e2 = make_basic_energy("Grass Energy", PokemonType.GRASS.value)
g2_obj = game_e.create_object(grass_e2.name, p1e.id, ZoneType.LIBRARY,
                              _copy.deepcopy(grass_e2.characteristics), grass_e2)
game_e.state.zones[f"library_{p1e.id}"].objects.append(g2_obj.id)
events_e = _selesnya_cluestone_effect(
    Event(type=EventType.PKM_PLAY_ITEM, payload={'player': p1e.id}),
    game_e.state,
)
check("Selesnya Cluestone <3 bench leaves pending_choice clear",
      game_e.state.pending_choice is None)


# --- Skyknight Vanguard --------------------------------------------------
print("\n--- Skyknight Vanguard ---")
game, p1, p2, sky, _opp = _make_game_p1_active(SKYKNIGHT_VANGUARD)
# Skyknight needs >=2 own bench for the trigger
_bench_pokemon(game, p1.id, "OwnBench1", 60, PokemonType.FIRE.value)
_bench_pokemon(game, p1.id, "OwnBench2", 60, PokemonType.FIRE.value)
opp_weak = _bench_pokemon(game, p2.id, "OppWeak", 60, PokemonType.GRASS.value, damage=4)
opp_strong = _bench_pokemon(game, p2.id, "OppStrong", 120, PokemonType.WATER.value)

events = _skyknight_vanguard_effect(sky, game.state)
check("Skyknight human path returns no events", events == [])
pc = game.state.pending_choice
check("Skyknight pending_choice set", pc is not None)
check("Skyknight choice belongs to caster (p1)",
      pc is not None and pc.player == p1.id)
opt_ids = {o["id"] for o in (pc.options if pc else [])}
check("Skyknight options are opp bench Pokemon",
      opp_weak.id in opt_ids and opp_strong.id in opt_ids)
hp_pick = (pc.callback_data or {}).get("heuristic_pick")
# Lowest current HP: opp_weak (60 - 40 = 20 remaining) beats opp_strong (120).
check("Skyknight heuristic_pick is the lowest-HP bench",
      hp_pick == [opp_weak.id])
# Handler smoke test
handler = (pc.callback_data or {}).get("handler")
if handler:
    handler_events = handler(pc, [opp_weak.id], game.state)
    check("Skyknight handler emits PKM_PLACE_DAMAGE_COUNTERS",
          len(handler_events) == 1
          and handler_events[0].type == EventType.PKM_PLACE_DAMAGE_COUNTERS)
    check("Skyknight handler places 2 counters on the target",
          opp_weak.state.damage_counters == 4 + 2)
game.state.pending_choice = None

# Empty: no opp bench
game_e, _p1, _p2, sky_e, _opp_e = _make_game_p1_active(SKYKNIGHT_VANGUARD)
_bench_pokemon(game_e, _p1.id, "OwnA", 60, PokemonType.FIRE.value)
_bench_pokemon(game_e, _p1.id, "OwnB", 60, PokemonType.FIRE.value)
events_e = _skyknight_vanguard_effect(sky_e, game_e.state)
check("Skyknight empty-opp-bench short-circuit returns no events", events_e == [])
check("Skyknight empty-opp-bench leaves pending_choice clear",
      game_e.state.pending_choice is None)

# Empty: <2 own bench → trigger blocked
game_e2, _p1, _p2, sky_e2, _opp = _make_game_p1_active(SKYKNIGHT_VANGUARD)
_bench_pokemon(game_e2, _p2.id, "OppB", 60, PokemonType.GRASS.value)
events_e2 = _skyknight_vanguard_effect(sky_e2, game_e2.state)
check("Skyknight <2 own-bench short-circuit returns no events", events_e2 == [])


# --- Burning-Tree Emissary (Cascade) -------------------------------------
print("\n--- Burning-Tree Emissary ---")
game, p1, p2, btree, _opp = _make_game_p1_active(BURNING_TREE_EMISSARY)
bench_a = _bench_pokemon(game, p1.id, "BTA", 90, PokemonType.GRASS.value)
bench_b = _bench_pokemon(game, p1.id, "BTB", 70, PokemonType.GRASS.value)
# Put an Energy card in the deck for Cascade to fetch
grass_e_btree = make_basic_energy("Grass Energy", PokemonType.GRASS.value)
btree_energy = game.create_object(
    grass_e_btree.name, p1.id, ZoneType.LIBRARY,
    _copy.deepcopy(grass_e_btree.characteristics), grass_e_btree,
)
game.state.zones[f"library_{p1.id}"].objects.append(btree_energy.id)

events = _cascade_attach_effect(btree, game.state)
check("Burning-Tree human path returns no events", events == [])
pc = game.state.pending_choice
check("Burning-Tree pending_choice set", pc is not None)
check("Burning-Tree choice belongs to caster (p1)",
      pc is not None and pc.player == p1.id)
opt_ids = {o["id"] for o in (pc.options if pc else [])}
check("Burning-Tree options are caster's bench",
      bench_a.id in opt_ids and bench_b.id in opt_ids)
hp_pick = (pc.callback_data or {}).get("heuristic_pick")
# Heuristic: first bench Pokemon (matches v1 `break`-on-first).
check("Burning-Tree heuristic_pick is the first bench Pokemon",
      hp_pick == [bench_a.id])
game.state.pending_choice = None

# Empty: no bench
game_e, _p1, _p2, btree_e, _opp = _make_game_p1_active(BURNING_TREE_EMISSARY)
grass_e_be = make_basic_energy("Grass Energy", PokemonType.GRASS.value)
btree_e2 = game_e.create_object(
    grass_e_be.name, _p1.id, ZoneType.LIBRARY,
    _copy.deepcopy(grass_e_be.characteristics), grass_e_be,
)
game_e.state.zones[f"library_{_p1.id}"].objects.append(btree_e2.id)
events_e = _cascade_attach_effect(btree_e, game_e.state)
check("Burning-Tree empty-bench short-circuit returns no events", events_e == [])
check("Burning-Tree empty-bench leaves pending_choice clear",
      game_e.state.pending_choice is None)

# Empty: no energy in deck
game_e2, _p1, _p2, btree_e3, _opp = _make_game_p1_active(BURNING_TREE_EMISSARY)
_bench_pokemon(game_e2, _p1.id, "BTNoDeck", 60, PokemonType.GRASS.value)
events_e3 = _cascade_attach_effect(btree_e3, game_e2.state)
check("Burning-Tree no-energy-in-deck short-circuit returns no events", events_e3 == [])


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
