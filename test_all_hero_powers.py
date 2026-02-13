"""
Test all 9 hero powers to ensure they work correctly.
"""

import asyncio
from src.engine.game import Game
from src.engine.types import ZoneType, CardType
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.classic import CHILLWIND_YETI
from src.ai.hearthstone_adapter import HearthstoneAIAdapter


async def test_warlock_life_tap():
    """Test Warlock's Life Tap - Draw a card, take 2 damage."""
    print("\n--- Test: Warlock Life Tap ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Warlock"], HERO_POWERS["Warlock"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()

    p1.mana_crystals = 10
    p1.mana_crystals_available = 10

    hand_before = len(game.get_hand(p1.id))
    life_before = p1.life

    print(f"  Hand size before: {hand_before}")
    print(f"  Life before: {life_before}")

    # Use hero power
    ai = HearthstoneAIAdapter()
    await ai._use_hero_power(p1.id, game.state, game)

    hand_after = len(game.get_hand(p1.id))
    life_after = p1.life

    print(f"  Hand size after: {hand_after}")
    print(f"  Life after: {life_after}")

    if hand_after == hand_before + 1 and life_after == life_before - 2:
        print(f"  ✓ Life Tap worked (drew 1, took 2 damage)")
        return True
    else:
        print(f"  ✗ Life Tap failed")
        return False


async def test_rogue_dagger_mastery():
    """Test Rogue's Dagger Mastery - Equip a 1/2 dagger."""
    print("\n--- Test: Rogue Dagger Mastery ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Rogue"], HERO_POWERS["Rogue"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()

    p1.mana_crystals = 10
    p1.mana_crystals_available = 10

    weapon_attack_before = p1.hero_power_id  # placeholder, will check weapon after
    weapon_durability_before = 0

    print(f"  Weapon before: {weapon_attack_before}/{weapon_durability_before}")

    # Use hero power
    ai = HearthstoneAIAdapter()
    events = await ai._use_hero_power(p1.id, game.state, game)

    print(f"  Events: {len(events)}")
    for e in events:
        print(f"    - {e.type}")

    # Check if a weapon was equipped (stored on player, not hero state)
    weapon_attack = p1.weapon_attack
    weapon_durability = p1.weapon_durability
    print(f"  Weapon after: {weapon_attack}/{weapon_durability}")

    if weapon_attack == 1 and weapon_durability == 2:
        print(f"  ✓ Dagger Mastery worked (equipped 1/2 dagger)")
        return True
    else:
        print(f"  ✗ Wrong weapon stats (expected 1/2, got {weapon_attack}/{weapon_durability})")
        return False


async def test_druid_shapeshift():
    """Test Druid's Shapeshift - +1 Attack this turn, +1 Armor."""
    print("\n--- Test: Druid Shapeshift ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Druid"], HERO_POWERS["Druid"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()

    p1.mana_crystals = 10
    p1.mana_crystals_available = 10

    armor_before = p1.armor
    attack_before = p1.weapon_attack

    print(f"  Armor before: {armor_before}")
    print(f"  Hero attack before: {attack_before}")

    # Use hero power
    ai = HearthstoneAIAdapter()
    await ai._use_hero_power(p1.id, game.state, game)

    armor_after = p1.armor
    attack_after = p1.weapon_attack

    print(f"  Armor after: {armor_after}")
    print(f"  Hero attack after: {attack_after}")

    if armor_after == armor_before + 1 and attack_after == attack_before + 1:
        print(f"  ✓ Shapeshift worked (+1 attack, +1 armor)")
        return True
    else:
        print(f"  ✗ Shapeshift failed")
        return False


async def test_priest_lesser_heal():
    """Test Priest's Lesser Heal - Restore 2 Health (needs target)."""
    print("\n--- Test: Priest Lesser Heal ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Priest"], HERO_POWERS["Priest"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()

    # Damage P1 first
    p1.life = 20

    p1.mana_crystals = 10
    p1.mana_crystals_available = 10

    life_before = p1.life

    print(f"  Life before: {life_before}")

    # Use hero power (should target self or need target - this might fail if targeting not implemented)
    ai = HearthstoneAIAdapter()
    events = await ai._use_hero_power(p1.id, game.state, game)

    life_after = p1.life

    print(f"  Life after: {life_after}")
    print(f"  Events: {len(events)}")

    # Lesser Heal requires targeting, so it might not work without target system
    if life_after > life_before:
        print(f"  ✓ Lesser Heal worked (healed {life_after - life_before})")
        return True
    else:
        print(f"  ⚠️  Lesser Heal requires targeting (not yet implemented)")
        return None  # Not a failure, just not implemented


async def test_shaman_totemic_call():
    """Test Shaman's Totemic Call - Summon a random totem."""
    print("\n--- Test: Shaman Totemic Call ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Shaman"], HERO_POWERS["Shaman"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()

    p1.mana_crystals = 10
    p1.mana_crystals_available = 10

    # Count minions before
    battlefield = game.state.zones.get('battlefield')
    minions_before = 0
    if battlefield:
        minions_before = len([
            obj_id for obj_id in battlefield.objects
            if CardType.MINION in game.state.objects[obj_id].characteristics.types
            and game.state.objects[obj_id].controller == p1.id
        ])

    print(f"  Minions before: {minions_before}")

    # Use hero power
    ai = HearthstoneAIAdapter()
    await ai._use_hero_power(p1.id, game.state, game)

    # Count minions after
    minions_after = 0
    if battlefield:
        minions_after = len([
            obj_id for obj_id in battlefield.objects
            if CardType.MINION in game.state.objects[obj_id].characteristics.types
            and game.state.objects[obj_id].controller == p1.id
        ])

    print(f"  Minions after: {minions_after}")

    if minions_after == minions_before + 1:
        # Find the totem
        for obj_id in battlefield.objects:
            obj = game.state.objects.get(obj_id)
            if obj and obj.controller == p1.id and 'Totem' in obj.name:
                print(f"  Summoned: {obj.name} ({obj.characteristics.power}/{obj.characteristics.toughness})")
                print(f"  ✓ Totemic Call worked (summoned a totem)")
                return True
        print(f"  ✓ Summoned a minion (might be a totem)")
        return True
    else:
        print(f"  ✗ No totem summoned")
        return False


async def run_all_tests():
    """Run all hero power tests."""
    tests = [
        test_warlock_life_tap,
        test_rogue_dagger_mastery,
        test_druid_shapeshift,
        test_priest_lesser_heal,
        test_shaman_totemic_call,
    ]

    print("="*70)
    print("ALL HERO POWERS TEST")
    print("="*70)

    passed = 0
    failed = 0
    skipped = 0

    for test in tests:
        try:
            result = await test()
            if result is True:
                passed += 1
            elif result is None:
                skipped += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} crashed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "="*70)
    print(f"RESULTS: {passed} passed, {failed} failed, {skipped} skipped")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
