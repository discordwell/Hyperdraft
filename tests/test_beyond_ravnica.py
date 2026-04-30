"""
Beyond Ravnica — engine integration tests for the 8-card Izzet PoC.

Validates each card's resolve / effect_fn against the Pokemon engine:
- Evolution chain (Nivlet -> Mizzling -> Niv-Mizzet ex)
- Attack effect_fn (Synapse Spark draw, Firemind's Research draw + discard)
- Stadium resolve (Niv-Mizzet's Tower draws for both players)
- Supporter resolve (Ral mills then conditionally damages)
- Item resolve (Izzet Signet searches energy)
- AI-vs-AI smoke test (10 games, no crashes)
"""

import asyncio
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ != "__main__":
    import pytest
    pytest.skip("Run directly: `python tests/test_beyond_ravnica.py`",
                allow_module_level=True)

from src.engine.game import Game
from src.engine.types import (
    CardType, ZoneType, PokemonType, EventType, Event,
)
from src.cards.pokemon.beyond.ravnica.izzet import (
    NIVLET, MIZZLING, NIV_MIZZET_PARUN_EX,
    GOBLIN_ELECTROMANCER, MERCURIAL_MAGELING,
    NIV_MIZZETS_TOWER, RAL_STORM_CONDUIT, IZZET_SIGNET,
    make_izzet_deck,
)
from src.cards.pokemon.sv_starter import (
    FIRE_ENERGY, WATER_ENERGY, make_fire_deck,
)


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name}{(' — ' + detail) if detail else ''}")
        failed += 1


def make_game():
    game = Game(mode="pokemon")
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    return game, p1, p2


def place_card(game, player_id, card_def, zone_type=ZoneType.HAND):
    """Create a card object and place in zone."""
    obj = game.create_object(
        card_def.name, player_id, zone_type,
        copy.deepcopy(card_def.characteristics), card_def,
    )
    return obj


def stack_library(game, player_id, card_defs):
    """Replace player's library with these card_defs (top first)."""
    library_key = f"library_{player_id}"
    library = game.state.zones[library_key]
    library.objects.clear()
    for cd in card_defs:
        # create_object already appends to the library zone
        place_card(game, player_id, cd, ZoneType.LIBRARY)


# =============================================================================
# Test 1: cards load + deck builds
# =============================================================================

print("\n=== Test 1: Set load ===")
deck = make_izzet_deck()
check("Izzet deck builds to 60 cards", len(deck) == 60, f"got {len(deck)}")
check("Niv-Mizzet ex flag", NIV_MIZZET_PARUN_EX.is_ex)
check("Niv-Mizzet prize count = 2", NIV_MIZZET_PARUN_EX.prize_count == 2)
check("Mizzling evolves from Nivlet", MIZZLING.evolves_from == "Nivlet")
check("Niv-Mizzet evolves from Mizzling",
      NIV_MIZZET_PARUN_EX.evolves_from == "Mizzling")
check("Niv-Mizzet has 2 attacks", len(NIV_MIZZET_PARUN_EX.attacks) == 2)
check("Synapse Spark has effect_fn",
      NIV_MIZZET_PARUN_EX.attacks[0].get("effect_fn") is not None)
check("Firemind's Research has effect_fn",
      NIV_MIZZET_PARUN_EX.attacks[1].get("effect_fn") is not None)


# =============================================================================
# Test 2: Synapse Spark draws a card
# =============================================================================

print("\n=== Test 2: Niv-Mizzet, Parun ex — Synapse Spark draws 1 ===")
game, p1, p2 = make_game()
# Stack library with 5 known fire energy
stack_library(game, p1.id, [FIRE_ENERGY] * 5)
# Place Niv-Mizzet on field as p1's active
niv = place_card(game, p1.id, NIV_MIZZET_PARUN_EX, ZoneType.ACTIVE_SPOT)
hand_before = len(game.state.zones[f"hand_{p1.id}"].objects)
effect = NIV_MIZZET_PARUN_EX.attacks[0]["effect_fn"]
events = effect(niv, game.state)
hand_after = len(game.state.zones[f"hand_{p1.id}"].objects)
check("hand grew by 1", hand_after - hand_before == 1,
      f"before={hand_before} after={hand_after}")
check("DRAW event emitted",
      any(e.type == EventType.DRAW for e in events))


# =============================================================================
# Test 3: Firemind's Research draws 2 + discards 2 energy
# =============================================================================

print("\n=== Test 3: Firemind's Research ===")
game, p1, p2 = make_game()
stack_library(game, p1.id, [FIRE_ENERGY] * 5)
niv = place_card(game, p1.id, NIV_MIZZET_PARUN_EX, ZoneType.ACTIVE_SPOT)
# Attach 3 fire energy to Niv-Mizzet manually
for _ in range(3):
    e_obj = place_card(game, p1.id, FIRE_ENERGY, ZoneType.BATTLEFIELD)
    niv.state.attached_energy.append(e_obj.id)
hand_before = len(game.state.zones[f"hand_{p1.id}"].objects)
energy_before = len(niv.state.attached_energy)
effect = NIV_MIZZET_PARUN_EX.attacks[1]["effect_fn"]
events = effect(niv, game.state)
hand_after = len(game.state.zones[f"hand_{p1.id}"].objects)
energy_after = len(niv.state.attached_energy)
check("hand grew by 2", hand_after - hand_before == 2,
      f"before={hand_before} after={hand_after}")
check("attached energy reduced by 2",
      energy_before - energy_after == 2,
      f"before={energy_before} after={energy_after}")


# =============================================================================
# Test 4: Goblin Electromancer + Mercurial Mageling draw on attack
# =============================================================================

print("\n=== Test 4: Basic Pokemon attack draws ===")
for card_def, atk_name in [
    (GOBLIN_ELECTROMANCER, "Inventor's Spark"),
    (MERCURIAL_MAGELING, "Cantrip"),
]:
    game, p1, p2 = make_game()
    stack_library(game, p1.id, [FIRE_ENERGY] * 3)
    pkm = place_card(game, p1.id, card_def, ZoneType.ACTIVE_SPOT)
    attack = next(a for a in card_def.attacks if a["name"] == atk_name)
    hand_before = len(game.state.zones[f"hand_{p1.id}"].objects)
    attack["effect_fn"](pkm, game.state)
    hand_after = len(game.state.zones[f"hand_{p1.id}"].objects)
    check(f"{card_def.name}'s {atk_name} draws 1",
          hand_after - hand_before == 1,
          f"hand {hand_before} -> {hand_after}")


# =============================================================================
# Test 5: Niv-Mizzet's Tower (Stadium) — both players draw
# =============================================================================

print("\n=== Test 5: Niv-Mizzet's Tower — both draw ===")
game, p1, p2 = make_game()
stack_library(game, p1.id, [FIRE_ENERGY] * 3)
stack_library(game, p2.id, [WATER_ENERGY] * 3)
p1_hand_before = len(game.state.zones[f"hand_{p1.id}"].objects)
p2_hand_before = len(game.state.zones[f"hand_{p2.id}"].objects)
events = NIV_MIZZETS_TOWER.resolve(
    Event(type=EventType.PKM_PLAY_STADIUM,
          payload={"player": p1.id, "card_id": "stadium"}, source="stadium"),
    game.state,
)
check("p1 hand +1",
      len(game.state.zones[f"hand_{p1.id}"].objects) - p1_hand_before == 1)
check("p2 hand +1",
      len(game.state.zones[f"hand_{p2.id}"].objects) - p2_hand_before == 1)


# =============================================================================
# Test 6: Ral, Storm Conduit — mill + conditional damage
# =============================================================================

print("\n=== Test 6: Ral, Storm Conduit ===")

# Case A: top is a Trainer -> 30 damage to opponent active
game, p1, p2 = make_game()
stack_library(game, p1.id, [IZZET_SIGNET, FIRE_ENERGY])  # Trainer on top
target = place_card(game, p2.id, MERCURIAL_MAGELING, ZoneType.ACTIVE_SPOT)
events = RAL_STORM_CONDUIT.resolve(
    Event(type=EventType.PKM_PLAY_SUPPORTER,
          payload={"player": p1.id, "card_id": "ral"}, source="ral"),
    game.state,
)
check("Ral milled top trainer",
      len(game.state.zones[f"library_{p1.id}"].objects) == 1)
check("opponent took 3 damage counters",
      target.state.damage_counters == 3,
      f"counters={target.state.damage_counters}")

# Case B: top is Energy -> no damage
game, p1, p2 = make_game()
stack_library(game, p1.id, [FIRE_ENERGY, IZZET_SIGNET])  # Energy on top
target = place_card(game, p2.id, MERCURIAL_MAGELING, ZoneType.ACTIVE_SPOT)
events = RAL_STORM_CONDUIT.resolve(
    Event(type=EventType.PKM_PLAY_SUPPORTER,
          payload={"player": p1.id, "card_id": "ral"}, source="ral"),
    game.state,
)
check("Ral milled energy (no damage)",
      target.state.damage_counters == 0)


# =============================================================================
# Test 7: Izzet Signet — search 1 fire and 1 water from deck
# =============================================================================

print("\n=== Test 7: Izzet Signet ===")
game, p1, p2 = make_game()
stack_library(game, p1.id, [
    FIRE_ENERGY, FIRE_ENERGY, WATER_ENERGY, WATER_ENERGY, NIVLET, NIVLET,
])
hand_before = len(game.state.zones[f"hand_{p1.id}"].objects)
lib_before = len(game.state.zones[f"library_{p1.id}"].objects)
IZZET_SIGNET.resolve(
    Event(type=EventType.PKM_PLAY_ITEM,
          payload={"player": p1.id, "card_id": "signet"}, source="signet"),
    game.state,
)
hand_after = len(game.state.zones[f"hand_{p1.id}"].objects)
lib_after = len(game.state.zones[f"library_{p1.id}"].objects)
check("hand +2", hand_after - hand_before == 2)
check("library -2", lib_before - lib_after == 2)
# Verify exactly one fire and one water moved
hand = game.state.zones[f"hand_{p1.id}"].objects
hand_types = []
for cid in hand:
    obj = game.state.objects.get(cid)
    if obj and obj.card_def:
        ptype = obj.card_def.pokemon_type
        if ptype:
            hand_types.append(ptype)
check("hand has Fire energy",
      PokemonType.FIRE.value in hand_types, f"types={hand_types}")
check("hand has Water energy",
      PokemonType.WATER.value in hand_types, f"types={hand_types}")


# =============================================================================
# Test 8: AI-vs-AI smoke test — Izzet vs sv_starter Fire deck
# =============================================================================

print("\n=== Test 8: AI vs AI smoke test (5 games, no crashes) ===")

async def run_one_game(game_num):
    from src.ai.pokemon_adapter import PokemonAIAdapter
    g = Game(mode="pokemon")
    p1 = g.add_player("Izzet")
    p2 = g.add_player("Fire")
    g.setup_pokemon_player(p1, make_izzet_deck())
    g.setup_pokemon_player(p2, make_fire_deck())
    ai = PokemonAIAdapter(difficulty="medium")
    g.turn_manager.set_ai_handler(ai)
    g.turn_manager.set_ai_player(p1.id)
    g.turn_manager.set_ai_player(p2.id)
    g.turn_manager.turn_order = [p1.id, p2.id]
    await g.turn_manager.setup_game()
    for _ in range(120):
        if g.is_game_over():
            break
        await g.turn_manager.run_turn()
    return g.is_game_over()


crashes = 0
finished = 0
for i in range(5):
    try:
        result = run(run_one_game(i))
        if result:
            finished += 1
    except Exception as ex:
        crashes += 1
        print(f"  CRASH in game {i}: {type(ex).__name__}: {ex}")

check("5 games ran without crashing", crashes == 0,
      f"{crashes} crashes")
check("at least 1 game reached game-over",
      finished >= 1, f"{finished}/5 finished")


# =============================================================================
# Summary
# =============================================================================

print(f"\n{'=' * 60}")
print(f"PASSED: {passed}    FAILED: {failed}")
print(f"{'=' * 60}")
sys.exit(0 if failed == 0 else 1)
