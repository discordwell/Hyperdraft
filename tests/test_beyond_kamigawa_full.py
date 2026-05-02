"""
Beyond Kamigawa — full 5-archetype smoke test.

Validates that the package aggregator exposes all 5 archetypes, every archetype
registry holds enough cards, every deck builder yields a legal 40-Main deck
with a ≤15-card Extra Deck, and that one mirror match per archetype runs to
completion without crashing the YGO engine.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ != "__main__":
    import pytest
    pytest.skip(
        "Run directly: `python tests/test_beyond_kamigawa_full.py`",
        allow_module_level=True,
    )


from src.engine.game import Game
from src.cards.yugioh.beyond.kamigawa import (
    BEYOND_KAMIGAWA_CARDS,
    BEYOND_KAMIGAWA_STAPLES,
    ARCHETYPE_REGISTRIES,
    ARCHETYPE_DECK_BUILDERS,
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
# Test 1: Aggregator exposes all 5 archetypes
# =============================================================================

print("\n=== Test 1: 5 archetypes wired into aggregator ===")
EXPECTED_ARCHETYPES = {
    "samurai", "ninja", "spirit_dragons", "moonfolk", "modified",
}
check("ARCHETYPE_REGISTRIES has 5 entries",
      set(ARCHETYPE_REGISTRIES.keys()) == EXPECTED_ARCHETYPES,
      f"got {sorted(ARCHETYPE_REGISTRIES.keys())}")
check("ARCHETYPE_DECK_BUILDERS has 5 entries",
      set(ARCHETYPE_DECK_BUILDERS.keys()) == EXPECTED_ARCHETYPES)


# =============================================================================
# Test 2: Each archetype has a substantial registry
# =============================================================================

print("\n=== Test 2: Each archetype has >= 30 cards ===")
for name, registry in ARCHETYPE_REGISTRIES.items():
    check(f"{name} registry has >= 30 cards",
          len(registry) >= 30, f"got {len(registry)}")


# =============================================================================
# Test 3: Each deck builder returns a legal 40-Main / <=15-Extra
# =============================================================================

print("\n=== Test 3: Each deck is legal 40-Main + <=15 Extra ===")
from collections import Counter
for name, builder in ARCHETYPE_DECK_BUILDERS.items():
    main, extra = builder()
    check(f"{name} main deck = 40", len(main) == 40, f"got {len(main)}")
    check(f"{name} extra deck <= 15", len(extra) <= 15, f"got {len(extra)}")
    counts = Counter(c.name for c in main)
    violations = [(n, k) for n, k in counts.items() if k > 3]
    check(f"{name} main has no >3 copies", not violations,
          f"violations: {violations}")
    extra_counts = Counter(c.name for c in extra)
    extra_violations = [(n, k) for n, k in extra_counts.items() if k > 3]
    check(f"{name} extra has no >3 copies", not extra_violations,
          f"violations: {extra_violations}")


# =============================================================================
# Test 4: Aggregate registry size
# =============================================================================

print("\n=== Test 4: Aggregate set size ===")
check(f"BEYOND_KAMIGAWA_CARDS has >= 200 entries (has {len(BEYOND_KAMIGAWA_CARDS)})",
      len(BEYOND_KAMIGAWA_CARDS) >= 200,
      f"got {len(BEYOND_KAMIGAWA_CARDS)}")
check(f"BEYOND_KAMIGAWA_STAPLES has >= 30 entries (has {len(BEYOND_KAMIGAWA_STAPLES)})",
      len(BEYOND_KAMIGAWA_STAPLES) >= 30,
      f"got {len(BEYOND_KAMIGAWA_STAPLES)}")


# =============================================================================
# Test 5: 5-Honden cycle is complete
# =============================================================================

print("\n=== Test 5: 5-Honden Field-Spell cycle ===")
HONDEN_NAMES = [
    "Honden of Cleansing Fire", "Honden of Night's Reach",
    "Honden of Infinite Rage", "Honden of Life's Web",
    "Honden of Seeing Winds",
]
for hn in HONDEN_NAMES:
    check(f"{hn} exists in staples", hn in BEYOND_KAMIGAWA_STAPLES)


# =============================================================================
# Test 6: AI vs AI mirror — every archetype plays at least once
# =============================================================================

print("\n=== Test 6: AI mirror smoke (every archetype) ===")


async def run_one_match(name, builder, max_turns=25):
    from src.ai.yugioh_adapter import YugiohAIAdapter
    g = Game(mode="yugioh")
    p1 = g.add_player(f"{name} A")
    p2 = g.add_player(f"{name} B")
    main_a, extra_a = builder()
    main_b, extra_b = builder()
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
    return turns


crashes = 0
for arche, builder in ARCHETYPE_DECK_BUILDERS.items():
    try:
        turns = run(run_one_match(arche, builder, max_turns=20))
        print(f"  PASS: {arche} mirror ran {turns} turns")
        passed += 1
    except Exception as ex:
        crashes += 1
        print(f"  FAIL: {arche} mirror — {type(ex).__name__}: {ex}")
        failed += 1

check("All 5 archetype mirror matches ran without crashing",
      crashes == 0, f"{crashes} crashes")


# =============================================================================
# Summary
# =============================================================================

print(f"\n{'=' * 60}")
print(f"PASSED: {passed}    FAILED: {failed}")
print(f"{'=' * 60}")
sys.exit(0 if failed == 0 else 1)
