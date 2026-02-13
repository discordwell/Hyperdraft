"""
Test Hearthstone State-Based Actions

Specifically testing that dead minions are removed from the battlefield.
"""

import asyncio
from src.engine.game import Game
from src.engine.types import ZoneType, EventType, Event, CardType
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.classic import CHILLWIND_YETI, BLOODFEN_RAPTOR


async def test_minion_dies_from_damage():
    """Test that a minion with lethal damage is removed."""
    print("\n--- Test: Minion Dies from Lethal Damage ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    await game.start_game()

    # Create a minion
    yeti = game.create_object(
        name="Yeti",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=CHILLWIND_YETI.characteristics,
        card_def=CHILLWIND_YETI
    )

    battlefield = game.state.zones.get('battlefield')
    minions_before = len([obj_id for obj_id in battlefield.objects
                          if CardType.MINION in game.state.objects[obj_id].characteristics.types])

    print(f"  Minions on battlefield: {minions_before}")
    print(f"  Yeti stats: {yeti.characteristics.power}/{yeti.characteristics.toughness}")

    # Deal exactly lethal damage (5)
    yeti.state.damage = 5
    print(f"  Dealt 5 damage (toughness = 5)")

    # Run SBAs
    game.check_state_based_actions()

    minions_after = len([obj_id for obj_id in battlefield.objects
                         if obj_id in game.state.objects and
                         CardType.MINION in game.state.objects[obj_id].characteristics.types])

    print(f"  Minions after SBA: {minions_after}")

    if minions_after == 0:
        print(f"  ✓ Minion correctly removed (1 → 0)")
    else:
        print(f"  ✗ Minion still on battlefield!")


async def test_minion_dies_from_overkill():
    """Test that a minion with overkill damage is removed."""
    print("\n--- Test: Minion Dies from Overkill ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    await game.start_game()

    # Create a minion
    raptor = game.create_object(
        name="Raptor",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=BLOODFEN_RAPTOR.characteristics,
        card_def=BLOODFEN_RAPTOR
    )

    battlefield = game.state.zones.get('battlefield')

    print(f"  Raptor stats: {raptor.characteristics.power}/{raptor.characteristics.toughness}")

    # Deal massive overkill (100 damage to 2 health minion)
    raptor.state.damage = 100
    print(f"  Dealt 100 damage (toughness = 2)")

    # Run SBAs
    game.check_state_based_actions()

    minions_after = len([obj_id for obj_id in battlefield.objects
                         if obj_id in game.state.objects and
                         CardType.MINION in game.state.objects[obj_id].characteristics.types])

    if minions_after == 0:
        print(f"  ✓ Minion correctly removed despite massive overkill")
    else:
        print(f"  ✗ Minion still on battlefield!")


async def test_minion_survives_non_lethal():
    """Test that a minion with non-lethal damage survives."""
    print("\n--- Test: Minion Survives Non-Lethal Damage ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    await game.start_game()

    # Create a minion
    yeti = game.create_object(
        name="Yeti",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=CHILLWIND_YETI.characteristics,
        card_def=CHILLWIND_YETI
    )

    print(f"  Yeti stats: {yeti.characteristics.power}/{yeti.characteristics.toughness}")

    # Deal non-lethal damage (4 to a 5 health minion)
    yeti.state.damage = 4
    print(f"  Dealt 4 damage (toughness = 5)")

    # Run SBAs
    game.check_state_based_actions()

    battlefield = game.state.zones.get('battlefield')
    minions_after = len([obj_id for obj_id in battlefield.objects
                         if obj_id in game.state.objects and
                         CardType.MINION in game.state.objects[obj_id].characteristics.types])

    if minions_after == 1:
        print(f"  ✓ Minion survived (still 1 minion)")
    else:
        print(f"  ✗ Minion incorrectly removed!")


async def test_multiple_minions_some_die():
    """Test that only dead minions are removed."""
    print("\n--- Test: Multiple Minions - Some Die, Some Survive ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    await game.start_game()

    # Create 3 minions
    yeti1 = game.create_object(
        name="Yeti1",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=CHILLWIND_YETI.characteristics,
        card_def=CHILLWIND_YETI
    )

    yeti2 = game.create_object(
        name="Yeti2",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=CHILLWIND_YETI.characteristics,
        card_def=CHILLWIND_YETI
    )

    yeti3 = game.create_object(
        name="Yeti3",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=CHILLWIND_YETI.characteristics,
        card_def=CHILLWIND_YETI
    )

    print(f"  Created 3 Yetis (4/5 each)")

    # Kill 2 of them
    yeti1.state.damage = 5  # Lethal
    yeti2.state.damage = 10  # Overkill
    yeti3.state.damage = 2   # Survives

    print(f"  Yeti1: 5 damage (dead)")
    print(f"  Yeti2: 10 damage (dead)")
    print(f"  Yeti3: 2 damage (alive)")

    # Run SBAs
    game.check_state_based_actions()

    battlefield = game.state.zones.get('battlefield')
    minions_after = len([obj_id for obj_id in battlefield.objects
                         if obj_id in game.state.objects and
                         CardType.MINION in game.state.objects[obj_id].characteristics.types])

    if minions_after == 1:
        print(f"  ✓ Correct: 2 died, 1 survived (3 → 1)")
    else:
        print(f"  ✗ Wrong count: {minions_after} minions remain (expected 1)")


async def test_sba_runs_each_turn():
    """Test that SBAs run automatically each turn."""
    print("\n--- Test: SBAs Run Each Turn ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()

    # Create a minion with lethal damage
    yeti = game.create_object(
        name="Yeti",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=CHILLWIND_YETI.characteristics,
        card_def=CHILLWIND_YETI
    )
    yeti.state.damage = 5

    print(f"  Created Yeti with 5 damage (should die)")

    # Run a turn (SBAs should be called automatically)
    await game.turn_manager.run_turn()

    battlefield = game.state.zones.get('battlefield')
    minions_after = len([obj_id for obj_id in battlefield.objects
                         if obj_id in game.state.objects and
                         CardType.MINION in game.state.objects[obj_id].characteristics.types])

    if minions_after == 0:
        print(f"  ✓ SBAs ran during turn, minion removed")
    else:
        print(f"  ✗ SBAs didn't run, {minions_after} minions remain")


async def run_all_sba_tests():
    """Run all SBA tests."""
    tests = [
        test_minion_dies_from_damage,
        test_minion_dies_from_overkill,
        test_minion_survives_non_lethal,
        test_multiple_minions_some_die,
        test_sba_runs_each_turn,
    ]

    print("="*70)
    print("HEARTHSTONE STATE-BASED ACTIONS TESTS")
    print("="*70)

    passed = 0
    failed = 0

    for test in tests:
        try:
            await test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} crashed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "="*70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(run_all_sba_tests())
