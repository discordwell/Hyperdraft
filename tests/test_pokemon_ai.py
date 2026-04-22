"""
Pokemon TCG AI Unit Tests

Tests for the overhauled AI system covering:
- Energy Commitment (multi-turn planning)
- Trainer Intelligence (effect-aware scoring)
- Retreat Decisions (multi-factor evaluation)
- Prize Awareness (strategy adaptation)
- Difficulty Differentiation (easy vs ultra behavior)
"""

import asyncio
import copy
import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ != "__main__":
    import pytest
    pytest.skip("Run directly: `python tests/test_pokemon_ai.py`", allow_module_level=True)

from src.engine.game import Game, make_pokemon, make_basic_energy, make_trainer_item, make_trainer_supporter
from src.engine.types import (
    CardType, ZoneType, PokemonType, EventType,
    CardDefinition,
)
from src.engine.pokemon_energy import PokemonEnergySystem
from src.engine.pokemon_combat import PokemonCombatManager
from src.engine.pokemon_status import apply_status
from src.ai.pokemon_adapter import (
    PokemonAIAdapter, TurnContext, EnergyPlan, TRAINER_SCORERS,
)


def run(coro):
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
# Helpers
# =============================================================================

def make_ai_test_game(difficulty='hard'):
    """Create a game with AI adapter for unit testing."""
    game = Game(mode='pokemon')
    p1 = game.add_player('AI')
    p2 = game.add_player('Opponent')
    ai = PokemonAIAdapter(difficulty=difficulty)
    return game, p1, p2, ai


def place_pokemon(game, player_id, name, hp, ptype, zone_type,
                  attacks=None, evolution_stage="Basic", evolves_from=None,
                  is_ex=False, weakness_type=None, retreat_cost=0,
                  resistance_type=None, prize_count=None):
    """Place a pokemon in the specified zone."""
    card_def = make_pokemon(
        name=name, hp=hp, pokemon_type=ptype,
        evolution_stage=evolution_stage, evolves_from=evolves_from,
        attacks=attacks or [{"name": "Tackle", "cost": [{"type": "C", "count": 1}], "damage": 20, "text": ""}],
        weakness_type=weakness_type, retreat_cost=retreat_cost,
        is_ex=is_ex, resistance_type=resistance_type,
        prize_count=prize_count or (2 if is_ex else 1),
    )
    obj = game.create_object(name, player_id, zone_type,
                              copy.deepcopy(card_def.characteristics), card_def)
    zone_key = f"{zone_type.value}_{player_id}"
    if zone_key in game.state.zones and obj.id not in game.state.zones[zone_key].objects:
        game.state.zones[zone_key].objects.append(obj.id)
    return obj


def place_energy(game, player_id, energy_type, zone_type):
    """Place an energy card in a zone."""
    type_names = {'R': 'Fire', 'W': 'Water', 'G': 'Grass', 'L': 'Lightning',
                  'P': 'Psychic', 'F': 'Fighting', 'D': 'Darkness', 'M': 'Metal'}
    name = f"{type_names.get(energy_type, 'Basic')} Energy"
    card_def = make_basic_energy(name, energy_type)
    obj = game.create_object(name, player_id, zone_type,
                              copy.deepcopy(card_def.characteristics), card_def)
    zone_key = f"{zone_type.value}_{player_id}"
    if zone_key in game.state.zones and obj.id not in game.state.zones[zone_key].objects:
        game.state.zones[zone_key].objects.append(obj.id)
    return obj


def attach_energy_to(game, pokemon_obj, energy_type):
    """Attach an energy card directly to a pokemon (bypasses turn limits)."""
    type_names = {'R': 'Fire', 'W': 'Water', 'G': 'Grass', 'L': 'Lightning',
                  'P': 'Psychic', 'F': 'Fighting', 'D': 'Darkness', 'M': 'Metal'}
    name = f"{type_names.get(energy_type, 'Basic')} Energy"
    card_def = make_basic_energy(name, energy_type)
    obj = game.create_object(name, pokemon_obj.owner, ZoneType.ACTIVE_SPOT,
                              copy.deepcopy(card_def.characteristics), card_def)
    obj.zone = pokemon_obj.zone
    pokemon_obj.state.attached_energy.append(obj.id)
    return obj


def place_trainer(game, player_id, name, text="", card_type=CardType.ITEM):
    """Place a trainer card in hand."""
    if card_type == CardType.SUPPORTER:
        card_def = make_trainer_supporter(name=name, text=text)
    else:
        card_def = make_trainer_item(name=name, text=text)
    obj = game.create_object(name, player_id, ZoneType.HAND,
                              copy.deepcopy(card_def.characteristics), card_def)
    hand_key = f"hand_{player_id}"
    if hand_key in game.state.zones and obj.id not in game.state.zones[hand_key].objects:
        game.state.zones[hand_key].objects.append(obj.id)
    return obj


def set_prizes(game, player_id, count):
    """Set a player's remaining prizes."""
    player = game.state.players[player_id]
    player.prizes_remaining = count


# =============================================================================
# Test 1: Energy Commitment
# =============================================================================

print("\n=== Test 1: Energy Commitment ===")

# 1a: Active gets energy when 1 away from attacking
game, p1, p2, ai = make_ai_test_game('hard')
active = place_pokemon(game, p1.id, "Charmeleon", 90, PokemonType.FIRE.value,
                       ZoneType.ACTIVE_SPOT,
                       attacks=[{"name": "Flamethrower", "cost": [{"type": "R", "count": 2}],
                                 "damage": 70, "text": ""}])
attach_energy_to(game, active, 'R')  # Has 1 R, needs 2 R
bench = place_pokemon(game, p1.id, "Pikachu", 60, PokemonType.LIGHTNING.value,
                      ZoneType.BENCH)
opp = place_pokemon(game, p2.id, "Squirtle", 70, PokemonType.WATER.value,
                    ZoneType.ACTIVE_SPOT)
fire_e = place_energy(game, p1.id, 'R', ZoneType.HAND)

ctx = ai._build_turn_context(p1.id, game.state)
ai._current_context = ctx
target = ai._select_energy_target(ctx, game.state, p1.id, [fire_e.id])
check("Active 1 energy from attacking gets priority", target == active.id)

# 1b: Type matching - fire energy goes to fire pokemon
game, p1, p2, ai = make_ai_test_game('hard')
fire_pkm = place_pokemon(game, p1.id, "Charmander", 70, PokemonType.FIRE.value,
                         ZoneType.ACTIVE_SPOT,
                         attacks=[{"name": "Ember", "cost": [{"type": "R", "count": 1}],
                                   "damage": 30, "text": ""}])
water_pkm = place_pokemon(game, p1.id, "Squirtle", 70, PokemonType.WATER.value,
                          ZoneType.BENCH,
                          attacks=[{"name": "Water Gun", "cost": [{"type": "W", "count": 1}],
                                    "damage": 20, "text": ""}])
place_pokemon(game, p2.id, "Pikachu", 60, PokemonType.LIGHTNING.value, ZoneType.ACTIVE_SPOT)
fire_e = place_energy(game, p1.id, 'R', ZoneType.HAND)

best = ai._pick_best_energy_for_target(fire_pkm.id, [fire_e.id], game.state)
check("Fire energy matched to fire pokemon", best == fire_e.id)

# 1c: Energy plan validity - plan invalidated when target KO'd
game, p1, p2, ai = make_ai_test_game('hard')
pkm = place_pokemon(game, p1.id, "Charmander", 70, PokemonType.FIRE.value,
                    ZoneType.ACTIVE_SPOT)
plan = EnergyPlan(
    target_pokemon_id=pkm.id,
    target_attack_index=0,
    energy_type_needed='R',
    turns_remaining=2,
    priority=50.0,
    created_turn=1,
)
check("Energy plan valid while target alive", ai._is_energy_plan_valid(plan, game.state))
# Move pokemon to graveyard (simulating KO)
pkm.zone = ZoneType.GRAVEYARD
check("Energy plan invalid after target KO", not ai._is_energy_plan_valid(plan, game.state))

# 1d: Already-powered pokemon deprioritized
game, p1, p2, ai = make_ai_test_game('hard')
loaded = place_pokemon(game, p1.id, "Charizard", 150, PokemonType.FIRE.value,
                       ZoneType.ACTIVE_SPOT,
                       attacks=[{"name": "Fire Spin", "cost": [{"type": "R", "count": 2}, {"type": "C", "count": 1}],
                                 "damage": 100, "text": ""}])
attach_energy_to(game, loaded, 'R')
attach_energy_to(game, loaded, 'R')
attach_energy_to(game, loaded, 'R')  # Already has enough
needy = place_pokemon(game, p1.id, "Charmeleon", 90, PokemonType.FIRE.value,
                      ZoneType.BENCH,
                      attacks=[{"name": "Flame", "cost": [{"type": "R", "count": 1}],
                                "damage": 40, "text": ""}])
place_pokemon(game, p2.id, "Squirtle", 70, PokemonType.WATER.value, ZoneType.ACTIVE_SPOT)
set_prizes(game, p1.id, 6)
set_prizes(game, p2.id, 6)

ctx = ai._build_turn_context(p1.id, game.state)
ai._current_context = ctx
score_loaded = ai._score_investment_target(
    loaded, loaded.card_def.attacks[0], 0, ctx, game.state)
score_needy = ai._score_investment_target(
    needy, needy.card_def.attacks[0], 0, ctx, game.state)
check("Already-powered pokemon scores lower for investment", score_needy > score_loaded)

# 1e: Sunk cost - partially invested pokemon preferred over fresh
game, p1, p2, ai = make_ai_test_game('hard')
invested = place_pokemon(game, p1.id, "Charizard", 150, PokemonType.FIRE.value,
                         ZoneType.BENCH,
                         attacks=[{"name": "Fire Blast", "cost": [{"type": "R", "count": 3}],
                                   "damage": 120, "text": ""}])
attach_energy_to(game, invested, 'R')
attach_energy_to(game, invested, 'R')  # 2 of 3 attached
fresh = place_pokemon(game, p1.id, "Arcanine", 130, PokemonType.FIRE.value,
                      ZoneType.BENCH,
                      attacks=[{"name": "Flamethrower", "cost": [{"type": "R", "count": 3}],
                                "damage": 110, "text": ""}])
# fresh has 0 energy
place_pokemon(game, p1.id, "Charmander", 70, PokemonType.FIRE.value, ZoneType.ACTIVE_SPOT)
place_pokemon(game, p2.id, "Squirtle", 70, PokemonType.WATER.value, ZoneType.ACTIVE_SPOT)

ctx = ai._build_turn_context(p1.id, game.state)
score_invested = ai._score_investment_target(
    invested, invested.card_def.attacks[0], 0, ctx, game.state)
score_fresh = ai._score_investment_target(
    fresh, fresh.card_def.attacks[0], 0, ctx, game.state)
check("Partially invested pokemon preferred over fresh start", score_invested > score_fresh)


# =============================================================================
# Test 2: Trainer Intelligence
# =============================================================================

print("\n=== Test 2: Trainer Intelligence ===")

# 2a: Potion scored high on damaged pokemon, low on full health
game, p1, p2, ai = make_ai_test_game('hard')
damaged = place_pokemon(game, p1.id, "Charmander", 70, PokemonType.FIRE.value,
                        ZoneType.ACTIVE_SPOT)
damaged.state.damage_counters = 5  # 50 damage
place_pokemon(game, p2.id, "Squirtle", 70, PokemonType.WATER.value, ZoneType.ACTIVE_SPOT)

ctx = ai._build_turn_context(p1.id, game.state)
ai._current_context = ctx
score_damaged = TRAINER_SCORERS["Potion"](ctx, game.state, p1.id)

# Reset - full health
damaged.state.damage_counters = 0
ctx2 = ai._build_turn_context(p1.id, game.state)
score_full = TRAINER_SCORERS["Potion"](ctx2, game.state, p1.id)
check("Potion scored higher on damaged pokemon", score_damaged > score_full)

# 2b: Nest Ball better with empty bench
game, p1, p2, ai = make_ai_test_game('hard')
place_pokemon(game, p1.id, "Charmander", 70, PokemonType.FIRE.value, ZoneType.ACTIVE_SPOT)
place_pokemon(game, p2.id, "Squirtle", 70, PokemonType.WATER.value, ZoneType.ACTIVE_SPOT)

ctx = ai._build_turn_context(p1.id, game.state)
score_empty = TRAINER_SCORERS["Nest Ball"](ctx, game.state, p1.id)

# Add 4 bench pokemon
for i in range(4):
    place_pokemon(game, p1.id, f"Bench{i}", 60, PokemonType.FIRE.value, ZoneType.BENCH)
ctx2 = ai._build_turn_context(p1.id, game.state)
score_full = TRAINER_SCORERS["Nest Ball"](ctx2, game.state, p1.id)
check("Nest Ball scores higher with empty bench", score_empty > score_full)

# 2c: Boss's Orders returns negative when no bench targets
game, p1, p2, ai = make_ai_test_game('hard')
place_pokemon(game, p1.id, "Charmander", 70, PokemonType.FIRE.value, ZoneType.ACTIVE_SPOT)
place_pokemon(game, p2.id, "Squirtle", 70, PokemonType.WATER.value, ZoneType.ACTIVE_SPOT)
# No opponent bench

ctx = ai._build_turn_context(p1.id, game.state)
score = TRAINER_SCORERS["Boss's Orders"](ctx, game.state, p1.id)
check("Boss's Orders negative with no opponent bench", score < 0)

# 2d: Switch scored high when active is paralyzed
game, p1, p2, ai = make_ai_test_game('hard')
active = place_pokemon(game, p1.id, "Charmander", 70, PokemonType.FIRE.value,
                       ZoneType.ACTIVE_SPOT)
place_pokemon(game, p1.id, "Pikachu", 60, PokemonType.LIGHTNING.value, ZoneType.BENCH)
place_pokemon(game, p2.id, "Squirtle", 70, PokemonType.WATER.value, ZoneType.ACTIVE_SPOT)
apply_status(active.id, 'paralyzed', game.state)

ctx = ai._build_turn_context(p1.id, game.state)
score_paralyzed = TRAINER_SCORERS["Switch"](ctx, game.state, p1.id)

# Without paralysis
active.state.status_conditions.clear()
ctx2 = ai._build_turn_context(p1.id, game.state)
score_normal = TRAINER_SCORERS["Switch"](ctx2, game.state, p1.id)
check("Switch scored much higher when active paralyzed", score_paralyzed > score_normal + 30)

# 2e: Professor's Research better with small hand
game, p1, p2, ai = make_ai_test_game('hard')
place_pokemon(game, p1.id, "Charmander", 70, PokemonType.FIRE.value, ZoneType.ACTIVE_SPOT)
place_pokemon(game, p2.id, "Squirtle", 70, PokemonType.WATER.value, ZoneType.ACTIVE_SPOT)

# Small hand (only the active, no hand cards)
ctx = ai._build_turn_context(p1.id, game.state)
score_small = TRAINER_SCORERS["Professor's Research"](ctx, game.state, p1.id)

# Large hand
for i in range(7):
    place_energy(game, p1.id, 'R', ZoneType.HAND)
ctx2 = ai._build_turn_context(p1.id, game.state)
score_large = TRAINER_SCORERS["Professor's Research"](ctx2, game.state, p1.id)
check("Professor's Research better with small hand", score_small > score_large)

# 2f: Super Rod scored higher late game with graveyard cards
game, p1, p2, ai = make_ai_test_game('hard')
place_pokemon(game, p1.id, "Charmander", 70, PokemonType.FIRE.value, ZoneType.ACTIVE_SPOT)
place_pokemon(game, p2.id, "Squirtle", 70, PokemonType.WATER.value, ZoneType.ACTIVE_SPOT)
set_prizes(game, p1.id, 1)  # Late game

# Put some pokemon in graveyard
grave_key = f"graveyard_{p1.id}"
for i in range(3):
    grave_obj = place_pokemon(game, p1.id, f"Fallen{i}", 60, PokemonType.FIRE.value,
                              ZoneType.GRAVEYARD)

ctx = ai._build_turn_context(p1.id, game.state)
score_late = TRAINER_SCORERS["Super Rod"](ctx, game.state, p1.id)

# Early game
set_prizes(game, p1.id, 6)
ctx2 = ai._build_turn_context(p1.id, game.state)
score_early = TRAINER_SCORERS["Super Rod"](ctx2, game.state, p1.id)
check("Super Rod scores higher in late game", score_late > score_early)

# 2g: Choice Belt scored higher vs EX opponents
game, p1, p2, ai = make_ai_test_game('hard')
place_pokemon(game, p1.id, "Charmander", 70, PokemonType.FIRE.value, ZoneType.ACTIVE_SPOT)
opp_ex = place_pokemon(game, p2.id, "Mewtwo ex", 180, PokemonType.PSYCHIC.value,
                       ZoneType.ACTIVE_SPOT, is_ex=True)

ctx = ai._build_turn_context(p1.id, game.state)
score_vs_ex = TRAINER_SCORERS["Choice Belt"](ctx, game.state, p1.id)

# Replace with non-EX
game2, p1b, p2b, ai2 = make_ai_test_game('hard')
place_pokemon(game2, p1b.id, "Charmander", 70, PokemonType.FIRE.value, ZoneType.ACTIVE_SPOT)
place_pokemon(game2, p2b.id, "Abra", 60, PokemonType.PSYCHIC.value, ZoneType.ACTIVE_SPOT)

ctx2 = ai2._build_turn_context(p1b.id, game2.state)
score_vs_normal = TRAINER_SCORERS["Choice Belt"](ctx2, game2.state, p1b.id)
check("Choice Belt scores higher vs EX", score_vs_ex > score_vs_normal)

# 2h: Registry fallback to text scoring for unknown card
game, p1, p2, ai = make_ai_test_game('hard')
place_pokemon(game, p1.id, "Charmander", 70, PokemonType.FIRE.value, ZoneType.ACTIVE_SPOT)
place_pokemon(game, p2.id, "Squirtle", 70, PokemonType.WATER.value, ZoneType.ACTIVE_SPOT)
unknown = place_trainer(game, p1.id, "Custom Card", text="Draw 3 cards")

ctx = ai._build_turn_context(p1.id, game.state)
ai._current_context = ctx
score = ai._score_trainer(unknown, game.state, p1.id)
check("Unknown trainer falls back to text scoring", score > 0)


# =============================================================================
# Test 3: Retreat Decisions
# =============================================================================

print("\n=== Test 3: Retreat Decisions ===")

# 3a: Retreat urgency high when opponent can KO
game, p1, p2, ai = make_ai_test_game('hard')
active = place_pokemon(game, p1.id, "Charmander", 70, PokemonType.FIRE.value,
                       ZoneType.ACTIVE_SPOT, retreat_cost=1)
active.state.damage_counters = 4  # 40 damage, 30 HP remaining
place_pokemon(game, p1.id, "Pikachu", 60, PokemonType.LIGHTNING.value, ZoneType.BENCH)
opp = place_pokemon(game, p2.id, "Squirtle", 70, PokemonType.WATER.value,
                    ZoneType.ACTIVE_SPOT,
                    attacks=[{"name": "Water Gun", "cost": [{"type": "W", "count": 1}],
                              "damage": 40, "text": ""}],
                    weakness_type=PokemonType.LIGHTNING.value)
attach_energy_to(game, opp, 'W')  # Opp can attack for 40

ctx = ai._build_turn_context(p1.id, game.state)
urgency = ctx.retreat_urgency
check("Retreat urgency high when opponent can KO", urgency >= 35)

# 3b: Retreat urgency high for paralyzed active
game, p1, p2, ai = make_ai_test_game('hard')
active = place_pokemon(game, p1.id, "Charmander", 70, PokemonType.FIRE.value,
                       ZoneType.ACTIVE_SPOT)
place_pokemon(game, p1.id, "Pikachu", 60, PokemonType.LIGHTNING.value, ZoneType.BENCH)
place_pokemon(game, p2.id, "Squirtle", 70, PokemonType.WATER.value, ZoneType.ACTIVE_SPOT)
apply_status(active.id, 'paralyzed', game.state)

ctx = ai._build_turn_context(p1.id, game.state)
# Paralyzed = 45, can't attack = 40 -> at least 85
check("Paralyzed active has very high retreat urgency", ctx.retreat_urgency >= 80)

# 3c: No urgency for healthy, able active
game, p1, p2, ai = make_ai_test_game('hard')
active = place_pokemon(game, p1.id, "Charizard", 150, PokemonType.FIRE.value,
                       ZoneType.ACTIVE_SPOT,
                       attacks=[{"name": "Slash", "cost": [{"type": "C", "count": 1}],
                                 "damage": 30, "text": ""}])
attach_energy_to(game, active, 'R')
place_pokemon(game, p2.id, "Squirtle", 70, PokemonType.WATER.value,
              ZoneType.ACTIVE_SPOT,
              attacks=[{"name": "Water Gun", "cost": [{"type": "W", "count": 1}],
                        "damage": 20, "text": ""}])

ctx = ai._build_turn_context(p1.id, game.state)
check("Healthy active with attacks has low retreat urgency", ctx.retreat_urgency < 20)

# 3d: EX about to die increases urgency
game, p1, p2, ai = make_ai_test_game('hard')
active_ex = place_pokemon(game, p1.id, "Charizard ex", 180, PokemonType.FIRE.value,
                          ZoneType.ACTIVE_SPOT, is_ex=True, retreat_cost=2)
active_ex.state.damage_counters = 16  # 160 damage, 20 HP remaining
place_pokemon(game, p1.id, "Charmander", 70, PokemonType.FIRE.value, ZoneType.BENCH)
opp = place_pokemon(game, p2.id, "Blastoise", 150, PokemonType.WATER.value,
                    ZoneType.ACTIVE_SPOT,
                    attacks=[{"name": "Hydro Pump", "cost": [{"type": "W", "count": 2}],
                              "damage": 80, "text": ""}],
                    weakness_type=PokemonType.GRASS.value)
attach_energy_to(game, opp, 'W')
attach_energy_to(game, opp, 'W')

ctx = ai._build_turn_context(p1.id, game.state)
check("Damaged EX about to die has very high urgency", ctx.retreat_urgency >= 50)

# 3e: Sacrifice strategy when behind on prizes
game, p1, p2, ai = make_ai_test_game('hard')
active_ex = place_pokemon(game, p1.id, "Charizard ex", 180, PokemonType.FIRE.value,
                          ZoneType.ACTIVE_SPOT, is_ex=True)
expendable = place_pokemon(game, p1.id, "Magikarp", 30, PokemonType.WATER.value,
                           ZoneType.BENCH)
place_pokemon(game, p2.id, "Mewtwo", 120, PokemonType.PSYCHIC.value, ZoneType.ACTIVE_SPOT)
set_prizes(game, p1.id, 5)  # We have 5 left
set_prizes(game, p2.id, 2)  # They have 2 left -> we're behind by 3

ctx = ai._build_turn_context(p1.id, game.state)
ai._current_context = ctx
replacement_id, replacement_score = ai._find_best_replacement(ctx, game.state, p1.id)
# Expendable non-EX with no energy should get sacrifice boost
check("Sacrifice strategy boosts expendable when behind", replacement_id == expendable.id)


# =============================================================================
# Test 4: Prize Awareness
# =============================================================================

print("\n=== Test 4: Prize Awareness ===")

# 4a: Game-winning KO gets massive bonus
game, p1, p2, ai = make_ai_test_game('hard')
active = place_pokemon(game, p1.id, "Charizard", 150, PokemonType.FIRE.value,
                       ZoneType.ACTIVE_SPOT,
                       attacks=[{"name": "Slash", "cost": [{"type": "C", "count": 1}],
                                 "damage": 60, "text": ""}])
attach_energy_to(game, active, 'R')
opp = place_pokemon(game, p2.id, "Pikachu", 60, PokemonType.LIGHTNING.value,
                    ZoneType.ACTIVE_SPOT)
set_prizes(game, p1.id, 1)  # One prize left - any KO wins

score_winning = ai._score_attack(active, active.card_def.attacks[0], game.state, p1.id)

set_prizes(game, p1.id, 6)
score_normal = ai._score_attack(active, active.card_def.attacks[0], game.state, p1.id)
check("Game-winning KO gets massive score bonus", score_winning > score_normal + 50)

# 4b: Direct lethal detection (Path 1)
game, p1, p2, ai = make_ai_test_game('hard')
active = place_pokemon(game, p1.id, "Charizard", 150, PokemonType.FIRE.value,
                       ZoneType.ACTIVE_SPOT,
                       attacks=[{"name": "Fire Spin", "cost": [{"type": "R", "count": 1}],
                                 "damage": 100, "text": ""}])
attach_energy_to(game, active, 'R')
opp = place_pokemon(game, p2.id, "Pikachu", 60, PokemonType.LIGHTNING.value,
                    ZoneType.ACTIVE_SPOT)
set_prizes(game, p1.id, 1)

ctx = ai._build_turn_context(p1.id, game.state)
lethal = ai._check_lethal(ctx, game.state, p1.id)
check("Direct lethal detected (Path 1)", lethal is not None and lethal['path'] == 1)

# 4c: No lethal when prizes remaining > prize value of KO
game, p1, p2, ai = make_ai_test_game('hard')
active = place_pokemon(game, p1.id, "Charizard", 150, PokemonType.FIRE.value,
                       ZoneType.ACTIVE_SPOT,
                       attacks=[{"name": "Fire Spin", "cost": [{"type": "R", "count": 1}],
                                 "damage": 100, "text": ""}])
attach_energy_to(game, active, 'R')
opp = place_pokemon(game, p2.id, "Pikachu", 60, PokemonType.LIGHTNING.value,
                    ZoneType.ACTIVE_SPOT)
set_prizes(game, p1.id, 3)  # Need 3 more prizes, KO only gives 1

ctx = ai._build_turn_context(p1.id, game.state)
lethal = ai._check_lethal(ctx, game.state, p1.id)
check("No lethal when prizes remaining > KO value", lethal is None)

# 4d: Anti-lethal detects opponent near win
game, p1, p2, ai = make_ai_test_game('ultra')
active = place_pokemon(game, p1.id, "Charizard ex", 180, PokemonType.FIRE.value,
                       ZoneType.ACTIVE_SPOT, is_ex=True, prize_count=2)
active.state.damage_counters = 10  # 100 damage, 80 HP remaining
opp = place_pokemon(game, p2.id, "Blastoise", 150, PokemonType.WATER.value,
                    ZoneType.ACTIVE_SPOT,
                    attacks=[{"name": "Hydro Pump", "cost": [{"type": "W", "count": 2}],
                              "damage": 160, "text": ""}],
                    weakness_type=PokemonType.GRASS.value)
attach_energy_to(game, opp, 'W')
attach_energy_to(game, opp, 'W')
set_prizes(game, p2.id, 2)  # Opponent needs 2 prizes, our EX gives 2

ctx = ai._build_turn_context(p1.id, game.state)
near_lethal = ai._opponent_near_lethal(ctx, game.state, p1.id)
check("Anti-lethal detects opponent near win", near_lethal is True)

# 4e: Avoid benching EX when behind on prizes
game, p1, p2, ai = make_ai_test_game('hard')
place_pokemon(game, p1.id, "Charmander", 70, PokemonType.FIRE.value, ZoneType.ACTIVE_SPOT)
place_pokemon(game, p2.id, "Squirtle", 70, PokemonType.WATER.value, ZoneType.ACTIVE_SPOT)
set_prizes(game, p1.id, 2)
set_prizes(game, p2.id, 5)  # We're behind

ex_card_def = make_pokemon(
    name="Mewtwo ex", hp=180, pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Basic", is_ex=True, prize_count=2,
    attacks=[{"name": "Psystrike", "cost": [{"type": "P", "count": 2}], "damage": 100, "text": ""}],
)
ex_card = game.create_object("Mewtwo ex", p1.id, ZoneType.HAND,
                              copy.deepcopy(ex_card_def.characteristics), ex_card_def)
game.state.zones[f"hand_{p1.id}"].objects.append(ex_card.id)

basic_card_def = make_pokemon(
    name="Abra", hp=60, pokemon_type=PokemonType.PSYCHIC.value,
    evolution_stage="Basic",
    attacks=[{"name": "Psybeam", "cost": [{"type": "P", "count": 1}], "damage": 20, "text": ""}],
)
basic_card = game.create_object("Abra", p1.id, ZoneType.HAND,
                                 copy.deepcopy(basic_card_def.characteristics), basic_card_def)
game.state.zones[f"hand_{p1.id}"].objects.append(basic_card.id)

score_ex = ai._score_basic_play(ex_card, game.state, p1.id)
score_basic = ai._score_basic_play(basic_card, game.state, p1.id)
check("EX deprioritized when behind on prizes", score_basic >= score_ex)


# =============================================================================
# Test 5: Difficulty Differentiation
# =============================================================================

print("\n=== Test 5: Difficulty Differentiation ===")

# 5a: Easy AI never uses context
ai_easy = PokemonAIAdapter(difficulty='easy')
settings_easy = ai_easy._get_settings()
check("Easy: context disabled", settings_easy['use_context'] is False)
check("Easy: energy commitment disabled", settings_easy['use_energy_commitment'] is False)
check("Easy: trainer registry disabled", settings_easy['use_trainer_registry'] is False)
check("Easy: lethal check disabled", settings_easy['use_lethal_check'] is False)

# 5b: Ultra AI uses all features
ai_ultra = PokemonAIAdapter(difficulty='ultra')
settings_ultra = ai_ultra._get_settings()
check("Ultra: context enabled", settings_ultra['use_context'] is True)
check("Ultra: energy commitment enabled", settings_ultra['use_energy_commitment'] is True)
check("Ultra: lethal check enabled", settings_ultra['use_lethal_check'] is True)
check("Ultra: anti-lethal enabled", settings_ultra['use_anti_lethal'] is True)
check("Ultra: action reordering enabled", settings_ultra['use_action_reordering'] is True)

# 5c: Hard uses KO math, medium does not
ai_hard = PokemonAIAdapter(difficulty='hard')
ai_medium = PokemonAIAdapter(difficulty='medium')
check("Hard: KO math enabled", ai_hard._get_settings()['use_ko_math'] is True)
check("Medium: KO math disabled", ai_medium._get_settings()['use_ko_math'] is False)

# 5d: Hard picks lower-damage KO over higher-damage non-KO
game, p1, p2, ai = make_ai_test_game('hard')
active = place_pokemon(game, p1.id, "Charizard", 150, PokemonType.FIRE.value,
                       ZoneType.ACTIVE_SPOT,
                       attacks=[
                           {"name": "Slash", "cost": [{"type": "C", "count": 1}],
                            "damage": 50, "text": ""},  # 50 = KOs the 50HP target
                           {"name": "Scratch", "cost": [{"type": "C", "count": 1}],
                            "damage": 40, "text": ""},  # 40 = doesn't KO
                       ])
attach_energy_to(game, active, 'R')
opp = place_pokemon(game, p2.id, "Pikachu", 50, PokemonType.LIGHTNING.value,
                    ZoneType.ACTIVE_SPOT)

score_ko = ai._score_attack(active, active.card_def.attacks[0], game.state, p1.id)
score_noko = ai._score_attack(active, active.card_def.attacks[1], game.state, p1.id)
# Hard's KO math should make the 50-damage KO outscore the 40-damage non-KO by a wide margin
check("Hard prefers KO attack over non-KO attack", score_ko > score_noko + 30)

# 5e: Easy has high random factor and mistake chance
check("Easy: high random factor", settings_easy['random_factor'] >= 0.4)
check("Easy: high mistake chance", settings_easy['mistake_chance'] >= 0.2)
check("Ultra: zero random factor", settings_ultra['random_factor'] == 0.0)
check("Ultra: zero mistake chance", settings_ultra['mistake_chance'] == 0.0)

# 5f: TurnContext correctly computed
game, p1, p2, ai = make_ai_test_game('hard')
active = place_pokemon(game, p1.id, "Charmander", 70, PokemonType.FIRE.value,
                       ZoneType.ACTIVE_SPOT,
                       attacks=[{"name": "Ember", "cost": [{"type": "R", "count": 1}],
                                 "damage": 30, "text": ""}],
                       weakness_type=PokemonType.WATER.value)
bench1 = place_pokemon(game, p1.id, "Pikachu", 60, PokemonType.LIGHTNING.value,
                       ZoneType.BENCH)
opp = place_pokemon(game, p2.id, "Squirtle", 70, PokemonType.WATER.value,
                    ZoneType.ACTIVE_SPOT,
                    attacks=[{"name": "Water Gun", "cost": [{"type": "W", "count": 1}],
                              "damage": 20, "text": ""}],
                    weakness_type=PokemonType.LIGHTNING.value)
set_prizes(game, p1.id, 4)
set_prizes(game, p2.id, 6)
fire_e = place_energy(game, p1.id, 'R', ZoneType.HAND)

ctx = ai._build_turn_context(p1.id, game.state)
check("Context: my_active correct", ctx.my_active == active.id)
check("Context: bench populated", len(ctx.my_bench) == 1 and ctx.my_bench[0] == bench1.id)
check("Context: opp_active correct", ctx.opp_active == opp.id)
check("Context: hand energy found", len(ctx.my_hand_energy) == 1)
check("Context: prize gap positive (winning)", ctx.prize_gap > 0)
check("Context: game phase mid", ctx.game_phase == 'mid')
check("Context: weakness exposed (water vs fire)", ctx.my_weakness_exposed is True)

# 5g: Board evaluation returns sane value
board_eval = ai._evaluate_board(p1.id, game.state)
check("Board eval returns value in [-1, 1]", -1.0 <= board_eval <= 1.0)

# 5h: choose_promote picks best attacker (hard)
game, p1, p2, ai = make_ai_test_game('hard')
place_pokemon(game, p2.id, "Squirtle", 70, PokemonType.WATER.value, ZoneType.ACTIVE_SPOT)
weak = place_pokemon(game, p1.id, "Magikarp", 30, PokemonType.WATER.value,
                     ZoneType.BENCH)
strong = place_pokemon(game, p1.id, "Charizard", 150, PokemonType.FIRE.value,
                       ZoneType.BENCH,
                       attacks=[{"name": "Fire Spin", "cost": [{"type": "R", "count": 1}],
                                 "damage": 100, "text": ""}])
attach_energy_to(game, strong, 'R')
promoted = ai.choose_promote(p1.id, game.state)
check("choose_promote picks strongest bench pokemon", promoted == strong.id)

# 5i: choose_promote avoids EX when behind on prizes
game, p1, p2, ai = make_ai_test_game('hard')
# Use high HP opponent so neither bench pokemon can KO (avoids KO math bonus)
place_pokemon(game, p2.id, "Blastoise", 200, PokemonType.WATER.value, ZoneType.ACTIVE_SPOT)
ex_bench = place_pokemon(game, p1.id, "Mewtwo ex", 100, PokemonType.PSYCHIC.value,
                         ZoneType.BENCH, is_ex=True,
                         attacks=[{"name": "Psystrike", "cost": [{"type": "P", "count": 1}],
                                   "damage": 40, "text": ""}])
attach_energy_to(game, ex_bench, 'P')
normal_bench = place_pokemon(game, p1.id, "Pikachu", 90, PokemonType.LIGHTNING.value,
                             ZoneType.BENCH,
                             attacks=[{"name": "Thunder", "cost": [{"type": "L", "count": 1}],
                                       "damage": 40, "text": ""}])
attach_energy_to(game, normal_bench, 'L')
set_prizes(game, p1.id, 5)
set_prizes(game, p2.id, 2)  # Behind by 3 prizes
promoted = ai.choose_promote(p1.id, game.state)
# With -3 prize gap, EX gets -20 penalty. Equal damage and similar HP → normal wins.
check("choose_promote avoids EX when behind on prizes", promoted == normal_bench.id)


# =============================================================================
# Summary
# =============================================================================

print(f"\n{'=' * 60}")
print(f"Results: {passed} passed, {failed} failed out of {passed + failed} tests")
if failed > 0:
    print("SOME TESTS FAILED")
    sys.exit(1)
else:
    print("ALL TESTS PASSED")
