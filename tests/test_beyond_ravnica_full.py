"""
Beyond Ravnica — full 10-guild smoke test.

Validates that the package aggregator exposes all 10 guilds, that every guild
registry holds 8 cards, every deck builder yields 60 cards, and that two random
guilds can mirror-match through a few AI-vs-AI turns without crashing.
"""

import asyncio
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ != "__main__":
    import pytest
    pytest.skip(
        "Run directly: `python tests/test_beyond_ravnica_full.py`",
        allow_module_level=True,
    )

from src.engine.game import Game
from src.cards.pokemon.beyond.ravnica import (
    BEYOND_RAVNICA_CARDS,
    GUILD_REGISTRIES,
    GUILD_DECK_BUILDERS,
)


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


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =============================================================================
# Test 1: Aggregator exposes all 10 guilds
# =============================================================================

print("\n=== Test 1: 10 guilds wired into aggregator ===")
EXPECTED_GUILDS = {
    "azorius", "boros", "dimir", "golgari", "gruul",
    "izzet", "orzhov", "rakdos", "selesnya", "simic",
}
check("GUILD_REGISTRIES has 10 entries",
      set(GUILD_REGISTRIES.keys()) == EXPECTED_GUILDS,
      f"got {sorted(GUILD_REGISTRIES.keys())}")
check("GUILD_DECK_BUILDERS has 10 entries",
      set(GUILD_DECK_BUILDERS.keys()) == EXPECTED_GUILDS)


# =============================================================================
# Test 2: Each guild registry has 8 cards
# =============================================================================

print("\n=== Test 2: Each guild has 15 cards ===")
for guild, registry in GUILD_REGISTRIES.items():
    check(f"{guild} registry has 15 cards",
          len(registry) == 15, f"got {len(registry)}")


# =============================================================================
# Test 3: Each deck builder returns 60 cards
# =============================================================================

print("\n=== Test 3: Each deck builds to 60 ===")
for guild, builder in GUILD_DECK_BUILDERS.items():
    deck = builder()
    check(f"{guild} deck = 60", len(deck) == 60, f"got {len(deck)}")


# =============================================================================
# Test 4: Aggregate registry has 80 unique cards
# =============================================================================

print("\n=== Test 4: Aggregate registry ===")
check("BEYOND_RAVNICA_CARDS has 150 entries",
      len(BEYOND_RAVNICA_CARDS) == 150,
      f"got {len(BEYOND_RAVNICA_CARDS)}")


# =============================================================================
# Test 5: Random guild-vs-guild AI smoke test
# =============================================================================

print("\n=== Test 5: AI vs AI smoke (every guild plays once) ===")


async def run_one_match(guild_a, guild_b):
    from src.ai.pokemon_adapter import PokemonAIAdapter
    g = Game(mode="pokemon")
    p1 = g.add_player(guild_a)
    p2 = g.add_player(guild_b)
    g.setup_pokemon_player(p1, GUILD_DECK_BUILDERS[guild_a]())
    g.setup_pokemon_player(p2, GUILD_DECK_BUILDERS[guild_b]())
    ai = PokemonAIAdapter(difficulty="medium")
    g.turn_manager.set_ai_handler(ai)
    g.turn_manager.set_ai_player(p1.id)
    g.turn_manager.set_ai_player(p2.id)
    g.turn_manager.turn_order = [p1.id, p2.id]
    await g.turn_manager.setup_game()
    for _ in range(80):
        if g.is_game_over():
            break
        await g.turn_manager.run_turn()
    return True


random.seed(42)
guild_list = sorted(EXPECTED_GUILDS)
crashes = 0
# Every guild plays at least once: pair guild i with guild (i+1) mod 10
for i, a in enumerate(guild_list):
    b = guild_list[(i + 1) % len(guild_list)]
    try:
        run(run_one_match(a, b))
        print(f"  PASS: {a} vs {b}")
        passed += 1
    except Exception as ex:
        crashes += 1
        print(f"  FAIL: {a} vs {b} — {type(ex).__name__}: {ex}")
        failed += 1

check("All 10 matches ran without crashing", crashes == 0,
      f"{crashes} crashes")


# =============================================================================
# Summary
# =============================================================================

print(f"\n{'=' * 60}")
print(f"PASSED: {passed}    FAILED: {failed}")
print(f"{'=' * 60}")
sys.exit(0 if failed == 0 else 1)
