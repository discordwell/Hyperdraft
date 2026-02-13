"""
Test that hero power effects actually execute.
"""

import asyncio
from src.engine.game import Game
from src.engine.types import ZoneType, EventType, Event
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.classic import CHILLWIND_YETI
from src.ai.hearthstone_adapter import HearthstoneAIAdapter


async def test_warrior_armor_up():
    """Test that Warrior's Armor Up hero power grants 2 armor."""
    print("\n--- Test: Warrior Armor Up ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()

    # Give P1 mana to use hero power
    p1.mana_crystals = 10
    p1.mana_crystals_available = 10
    armor_before = p1.armor

    print(f"  Armor before: {armor_before}")
    print(f"  Mana: {p1.mana_crystals_available}/10")

    # Use AI to activate hero power
    ai = HearthstoneAIAdapter()
    events = await ai._use_hero_power(p1.id, game.state, game)

    print(f"  Armor after: {p1.armor}")
    print(f"  Mana after: {p1.mana_crystals_available}/10")
    print(f"  Events emitted: {len(events)}")

    if p1.armor == armor_before + 2:
        print(f"  ✓ Armor Up worked (gained 2 armor)")
        return True
    else:
        print(f"  ✗ Armor Up didn't work (expected +2, got +{p1.armor - armor_before})")
        return False


async def test_hunter_steady_shot():
    """Test that Hunter's Steady Shot deals 2 damage to enemy hero."""
    print("\n--- Test: Hunter Steady Shot ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Hunter"], HERO_POWERS["Hunter"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()

    # Give P1 mana
    p1.mana_crystals = 10
    p1.mana_crystals_available = 10

    # Track P2's HP and armor
    life_before = p2.life
    armor_before = p2.armor

    print(f"  Enemy life before: {life_before}")
    print(f"  Enemy armor before: {armor_before}")

    # Use hero power
    ai = HearthstoneAIAdapter()
    events = await ai._use_hero_power(p1.id, game.state, game)

    print(f"  Enemy life after: {p2.life}")
    print(f"  Enemy armor after: {p2.armor}")

    # Calculate total damage (armor absorbed some, life took the rest)
    armor_lost = armor_before - p2.armor
    life_lost = life_before - p2.life
    total_damage = armor_lost + life_lost

    print(f"  Total damage dealt: {total_damage}")

    if total_damage == 2:
        print(f"  ✓ Steady Shot worked (2 damage to enemy hero)")
        return True
    else:
        print(f"  ✗ Steady Shot didn't work (expected 2, dealt {total_damage})")
        return False


async def test_paladin_reinforce():
    """Test that Paladin's Reinforce summons a 1/1 token."""
    print("\n--- Test: Paladin Reinforce ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Paladin"], HERO_POWERS["Paladin"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()

    # Give P1 mana
    p1.mana_crystals = 10
    p1.mana_crystals_available = 10

    # Count minions before
    battlefield = game.state.zones.get('battlefield')
    minions_before = 0
    if battlefield:
        from src.engine.types import CardType
        minions_before = len([
            obj_id for obj_id in battlefield.objects
            if CardType.MINION in game.state.objects[obj_id].characteristics.types
            and game.state.objects[obj_id].controller == p1.id
        ])

    print(f"  Minions before: {minions_before}")

    # Use hero power
    ai = HearthstoneAIAdapter()
    events = await ai._use_hero_power(p1.id, game.state, game)

    # Count minions after
    minions_after = 0
    if battlefield:
        from src.engine.types import CardType
        minions_after = len([
            obj_id for obj_id in battlefield.objects
            if CardType.MINION in game.state.objects[obj_id].characteristics.types
            and game.state.objects[obj_id].controller == p1.id
        ])

    print(f"  Minions after: {minions_after}")

    # Check if a 1/1 was created
    if minions_after == minions_before + 1:
        # Find the new minion
        new_minion = None
        for obj_id in battlefield.objects:
            obj = game.state.objects.get(obj_id)
            if obj and obj.name == "Silver Hand Recruit":
                new_minion = obj
                break

        if new_minion:
            power = new_minion.characteristics.power
            toughness = new_minion.characteristics.toughness
            print(f"  Token stats: {power}/{toughness}")

            if power == 1 and toughness == 1:
                print(f"  ✓ Reinforce worked (summoned 1/1 token)")
                return True
            else:
                print(f"  ✗ Wrong stats (expected 1/1, got {power}/{toughness})")
                return False
        else:
            print(f"  ✗ Token created but not named Silver Hand Recruit")
            return False
    else:
        print(f"  ✗ No token summoned")
        return False


async def run_tests():
    """Run all hero power effect tests."""
    tests = [
        test_warrior_armor_up,
        test_hunter_steady_shot,
        test_paladin_reinforce,
    ]

    print("="*70)
    print("HERO POWER EFFECTS TESTS")
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
    asyncio.run(run_tests())
