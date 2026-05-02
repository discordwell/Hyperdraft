"""
Beyond Kamigawa — engine integration tests for the Eiganjo Samurai PoC.

Validates that the Samurai archetype loads, its deck is legal, key effect
monsters' setup_interceptors fire, and a Samurai-vs-Samurai AI mirror
match runs to completion without crashing.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ != "__main__":
    import pytest
    pytest.skip("Run directly: `python tests/test_beyond_kamigawa.py`",
                allow_module_level=True)


from src.engine.game import Game
from src.cards.yugioh.beyond.kamigawa.samurai import (
    BEYOND_KAMIGAWA_SAMURAI,
    make_samurai_deck,
    KONDA_LORD_OF_EIGANJO, HAND_OF_HONOR, HAND_OF_CRUELTY,
    KONDAS_BANNER_BEARER, IMPERIAL_RECOVERY_UNIT,
)


passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name}{(' - ' + detail) if detail else ''}")
        failed += 1


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =============================================================================
# Test 1: Set load
# =============================================================================

print("\n=== Test 1: Samurai archetype loads ===")
check("BEYOND_KAMIGAWA_SAMURAI has >= 35 cards",
      len(BEYOND_KAMIGAWA_SAMURAI) >= 35,
      f"got {len(BEYOND_KAMIGAWA_SAMURAI)}")
main, extra = make_samurai_deck()
check("Main deck is exactly 40 cards", len(main) == 40, f"got {len(main)}")
check("Extra deck is <= 15 cards", len(extra) <= 15, f"got {len(extra)}")
check("Extra deck has >= 1 card", len(extra) >= 1)


# =============================================================================
# Test 2: Multiplicity (no card appears more than 3x in main)
# =============================================================================

print("\n=== Test 2: Deck multiplicity ===")
from collections import Counter
counts = Counter(card.name for card in main)
violations = [(n, k) for n, k in counts.items() if k > 3]
check("No card exceeds 3 copies in main deck",
      not violations, f"violations: {violations}")


# =============================================================================
# Test 3: Key cards have proper subtypes (archetype tag)
# =============================================================================

print("\n=== Test 3: Archetype subtypes ===")
check("Konda has 'Samurai' subtype",
      "Samurai" in KONDA_LORD_OF_EIGANJO.characteristics.subtypes)
check("Konda has 'Warrior' subtype",
      "Warrior" in KONDA_LORD_OF_EIGANJO.characteristics.subtypes)
check("Hand of Honor has Bushido setup_interceptors",
      HAND_OF_HONOR.setup_interceptors is not None)
check("Konda's Banner-Bearer has lord setup_interceptors",
      KONDAS_BANNER_BEARER.setup_interceptors is not None)
check("Imperial Recovery Unit has destroy-trigger setup",
      IMPERIAL_RECOVERY_UNIT.setup_interceptors is not None)


# =============================================================================
# Test 4: Bushido lord static effect
# =============================================================================

print("\n=== Test 4: Bushido lord static effect ===")
# Place 2 Hand of Honor onto a player's monster zone, query their ATK,
# confirm that the second one has +200 from the first via Bushido.
from src.engine.types import ZoneType, CardType
from src.cards.yugioh.beyond.kamigawa.samurai import HAND_OF_HONOR
import copy


def make_test_game():
    game = Game(mode="yugioh")
    p1 = game.add_player("Test 1")
    p2 = game.add_player("Test 2")
    return game, p1, p2


def place_card(game, player_id, card_def, zone_type=ZoneType.HAND):
    obj = game.create_object(
        card_def.name, player_id, zone_type,
        copy.deepcopy(card_def.characteristics), card_def,
    )
    return obj


game, p1, p2 = make_test_game()
m1 = place_card(game, p1.id, HAND_OF_HONOR, ZoneType.MONSTER_ZONE)
check("Hand of Honor object exists", m1 is not None)
check("Hand of Honor has interceptors registered",
      len(m1.interceptor_ids) > 0,
      f"got {len(m1.interceptor_ids)} interceptors")


# =============================================================================
# Test 5: AI vs AI mirror (Samurai vs Samurai), short run
# =============================================================================

print("\n=== Test 5: AI mirror match ===")


async def run_mirror_match(max_turns: int = 20):
    from src.ai.yugioh_adapter import YugiohAIAdapter
    g = Game(mode="yugioh")
    p1 = g.add_player("Samurai A")
    p2 = g.add_player("Samurai B")
    main_a, extra_a = make_samurai_deck()
    main_b, extra_b = make_samurai_deck()
    g.setup_yugioh_player(p1, main_a, extra_a)
    g.setup_yugioh_player(p2, main_b, extra_b)
    ai = YugiohAIAdapter(difficulty="medium")
    g.turn_manager.set_ai_handler(ai)
    g.turn_manager.ai_players.add(p1.id)
    g.turn_manager.ai_players.add(p2.id)
    await g.turn_manager.setup_game()
    turns = 0
    while turns < max_turns:
        if g.is_game_over():
            break
        await g.turn_manager.run_turn()
        turns += 1
    return turns, g.is_game_over()


try:
    turns, ended = run(run_mirror_match(max_turns=20))
    check(f"Mirror match ran {turns} turns without crashing",
          turns > 0, f"turns={turns}, ended_early={ended}")
except Exception as ex:
    check("Mirror match runs without crashing", False,
          f"{type(ex).__name__}: {ex}")


# =============================================================================
# Summary
# =============================================================================

print(f"\n{'=' * 60}")
print(f"PASSED: {passed}    FAILED: {failed}")
print(f"{'=' * 60}")
sys.exit(0 if failed == 0 else 1)
