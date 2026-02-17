"""
Test Hearthstone Fatigue Mechanics

Verify that:
1. Drawing from empty deck deals increasing fatigue damage
2. Fatigue counter increments correctly
3. Players can lose from fatigue
"""

import asyncio
from src.engine.game import Game
from src.engine.types import ZoneType, EventType, Event
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.classic import CHILLWIND_YETI


async def test_fatigue_damage_progression():
    """Test that fatigue damage increases each time (1, 2, 3, 4...)."""
    print("\n--- Test: Fatigue Damage Progression ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    # Seed decks so opening hand draws don't trigger fatigue before test setup.
    for _ in range(10):
        game.add_card_to_library(p1.id, CHILLWIND_YETI)
        game.add_card_to_library(p2.id, CHILLWIND_YETI)

    await game.start_game()

    # Empty P1's deck completely
    library_zone_id = f"library_{p1.id}"
    library = game.state.zones.get(library_zone_id)
    library.objects.clear()

    print(f"  Starting life: {p1.life}")
    print(f"  Emptied deck, fatigue counter: {p1.fatigue_damage}")

    # Set active player for draw phase
    game.turn_manager.hs_turn_state.active_player_id = p1.id
    game.state.active_player = p1.id

    # Simulate multiple draw phases (fatigue triggers)
    expected_damages = [1, 2, 3, 4, 5]

    for i, expected in enumerate(expected_damages):
        life_before = p1.life

        # Trigger fatigue by running draw phase
        await game.turn_manager._run_draw_phase()

        actual_damage = life_before - p1.life

        print(f"  Fatigue {i+1}: Expected -{expected} damage, got -{actual_damage}, life: {life_before} → {p1.life}")

        if actual_damage != expected:
            print(f"  ✗ Wrong damage amount!")
            return False

        if p1.fatigue_damage != i + 1:
            print(f"  ✗ Fatigue counter wrong: {p1.fatigue_damage} (expected {i+1})")
            return False

    print(f"  ✓ Fatigue progression correct (1, 2, 3, 4, 5)")
    return True


async def test_fatigue_lethal():
    """Test that a player can die from fatigue damage."""
    print("\n--- Test: Lethal Fatigue Damage ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    # Seed decks so opening hand draws don't trigger fatigue before test setup.
    for _ in range(10):
        game.add_card_to_library(p1.id, CHILLWIND_YETI)
        game.add_card_to_library(p2.id, CHILLWIND_YETI)

    await game.start_game()

    # Set P1 to low life
    p1.life = 5

    # Empty deck
    library_zone_id = f"library_{p1.id}"
    library = game.state.zones.get(library_zone_id)
    library.objects.clear()

    # Set fatigue counter to 4 (next fatigue will be 5 damage, exactly lethal)
    p1.fatigue_damage = 4

    print(f"  Life: {p1.life}, Fatigue counter: {p1.fatigue_damage}")
    print(f"  Next fatigue will deal 5 damage (lethal)")

    # Set active player
    game.turn_manager.hs_turn_state.active_player_id = p1.id
    game.state.active_player = p1.id

    # Trigger fatigue
    await game.turn_manager._run_draw_phase()

    print(f"  After fatigue: Life = {p1.life}, Has lost = {p1.has_lost}")

    if p1.life <= 0 and p1.has_lost:
        print(f"  ✓ Player correctly died from fatigue")
        return True
    else:
        print(f"  ✗ Player should have died but didn't")
        return False


async def test_no_fatigue_with_cards():
    """Test that fatigue doesn't trigger when deck has cards."""
    print("\n--- Test: No Fatigue With Cards In Deck ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    # Add cards to deck
    for _ in range(10):
        game.add_card_to_library(p1.id, CHILLWIND_YETI)
        game.add_card_to_library(p2.id, CHILLWIND_YETI)

    await game.start_game()

    life_before = p1.life
    fatigue_before = p1.fatigue_damage

    # Run draw phase (should draw card, not take fatigue)
    await game.turn_manager._run_draw_phase()

    print(f"  Life: {life_before} → {p1.life}")
    print(f"  Fatigue counter: {fatigue_before} → {p1.fatigue_damage}")

    if p1.life == life_before and p1.fatigue_damage == 0:
        print(f"  ✓ No fatigue taken (deck has cards)")
        return True
    else:
        print(f"  ✗ Fatigue incorrectly triggered")
        return False


async def test_fatigue_in_full_turn():
    """Test that fatigue triggers during a normal turn cycle."""
    print("\n--- Test: Fatigue During Full Turn ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    # Seed both decks so opening hand draws don't trigger fatigue before setup.
    for _ in range(10):
        game.add_card_to_library(p1.id, CHILLWIND_YETI)
        game.add_card_to_library(p2.id, CHILLWIND_YETI)

    # Add extra cards for P2 only
    for _ in range(30):
        game.add_card_to_library(p2.id, CHILLWIND_YETI)

    await game.start_game()

    # Empty P1's deck
    library_zone_id = f"library_{p1.id}"
    library = game.state.zones.get(library_zone_id)
    library.objects.clear()

    life_before = p1.life

    # Run full turn (includes draw phase)
    await game.turn_manager.run_turn(p1.id)

    fatigue_damage_dealt = life_before - p1.life

    print(f"  Life before turn: {life_before}")
    print(f"  Life after turn: {p1.life}")
    print(f"  Fatigue damage: {fatigue_damage_dealt}")
    print(f"  Fatigue counter: {p1.fatigue_damage}")

    if p1.fatigue_damage == 1 and fatigue_damage_dealt == 1:
        print(f"  ✓ Fatigue correctly triggered during turn")
        return True
    else:
        print(f"  ✗ Fatigue didn't work in full turn cycle")
        return False


async def run_all_fatigue_tests():
    """Run all fatigue tests."""
    tests = [
        test_fatigue_damage_progression,
        test_fatigue_lethal,
        test_no_fatigue_with_cards,
        test_fatigue_in_full_turn,
    ]

    print("="*70)
    print("HEARTHSTONE FATIGUE MECHANICS TESTS")
    print("="*70)

    passed = 0
    failed = 0

    for test in tests:
        try:
            result = await test()
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} crashed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "="*70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(run_all_fatigue_tests())
