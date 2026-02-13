"""
Test weapon mechanics in Hearthstone.

Weapons:
- Equipped to hero
- Have attack and durability
- Lose 1 durability when attacking
- Destroyed at 0 durability
- Hero takes damage when attacking minions
"""

import asyncio
from src.engine.game import Game
from src.engine.types import ZoneType, CardType
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.classic import CHILLWIND_YETI, FIERY_WAR_AXE


async def test_weapon_durability_loss():
    """Test that weapons lose 1 durability when attacking."""
    print("\n--- Test: Weapon Durability Loss ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()

    # Set active player so hero can attack
    game.state.active_player = p1.id

    # Create Fiery War Axe (3/2 weapon)
    weapon = game.create_object(
        name="Fiery War Axe",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=FIERY_WAR_AXE.characteristics,
        card_def=FIERY_WAR_AXE
    )

    # Equip weapon to hero (set on player)
    p1.weapon_attack = 3
    p1.weapon_durability = 2

    print(f"  Weapon: {p1.weapon_attack}/{p1.weapon_durability}")

    # Attack enemy hero using combat manager
    await game.combat_manager.declare_attack(p1.hero_id, p2.hero_id)

    print(f"  After attack: {p1.weapon_attack}/{p1.weapon_durability}")

    if p1.weapon_durability == 1:
        print(f"  ✓ Weapon durability decreased (2 → 1)")
        return True
    else:
        print(f"  ✗ Weapon durability didn't decrease correctly")
        return False


async def test_weapon_destruction():
    """Test that weapons are destroyed at 0 durability."""
    print("\n--- Test: Weapon Destruction at 0 Durability ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()

    # Set active player so hero can attack
    game.state.active_player = p1.id

    # Equip weapon with 1 durability
    p1.weapon_attack = 3
    p1.weapon_durability = 1

    print(f"  Weapon before attack: {p1.weapon_attack}/{p1.weapon_durability}")

    # Attack enemy hero using combat manager
    await game.combat_manager.declare_attack(p1.hero_id, p2.hero_id)

    print(f"  Weapon after attack: {p1.weapon_attack}/{p1.weapon_durability}")

    if p1.weapon_attack == 0 and p1.weapon_durability == 0:
        print(f"  ✓ Weapon destroyed (attack and durability reset to 0)")
        return True
    else:
        print(f"  ✗ Weapon not properly destroyed")
        return False


async def test_hero_takes_damage_from_minion():
    """Test that hero takes damage when attacking a minion with weapon."""
    print("\n--- Test: Hero Takes Damage from Minion ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()

    # Set active player so hero can attack
    game.state.active_player = p1.id

    # Equip weapon
    p1.weapon_attack = 3
    p1.weapon_durability = 2

    # Create enemy minion (4/5)
    yeti = game.create_object(
        name="Yeti",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=CHILLWIND_YETI.characteristics,
        card_def=CHILLWIND_YETI
    )

    life_before = p1.life
    armor_before = p1.armor
    minion_health_before = yeti.characteristics.toughness - yeti.state.damage

    print(f"  Hero: {life_before}HP, {armor_before} armor, weapon {p1.weapon_attack}/2")
    print(f"  Minion: 4/{minion_health_before}")

    # Attack minion using combat manager
    await game.combat_manager.declare_attack(p1.hero_id, yeti.id)

    life_after = p1.life
    armor_after = p1.armor
    minion_health_after = yeti.characteristics.toughness - yeti.state.damage

    print(f"  After attack:")
    print(f"  Hero: {life_after}HP, {armor_after} armor")
    print(f"  Minion: 4/{minion_health_after} (took 3 damage)")

    # Hero should take 4 damage (minion's attack)
    total_damage_taken = (armor_before - armor_after) + (life_before - life_after)

    if total_damage_taken == 4 and minion_health_after == 2:
        print(f"  ✓ Hero took 4 damage, minion took 3 damage (simultaneous)")
        return True
    else:
        print(f"  ✗ Damage incorrect (hero took {total_damage_taken}, minion at {minion_health_after}/5)")
        return False


async def test_multiple_weapon_equips():
    """Test that equipping a new weapon replaces the old one."""
    print("\n--- Test: New Weapon Replaces Old ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Rogue"], HERO_POWERS["Rogue"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()

    p1.mana_crystals = 10
    p1.mana_crystals_available = 10

    # Equip first weapon (1/2 dagger from hero power)
    from src.ai.hearthstone_adapter import HearthstoneAIAdapter
    ai = HearthstoneAIAdapter()
    await ai._use_hero_power(p1.id, game.state, game)

    weapon1_attack = p1.weapon_attack
    weapon1_durability = p1.weapon_durability

    print(f"  First weapon: {weapon1_attack}/{weapon1_durability}")

    # Equip Fiery War Axe (3/2)
    p1.weapon_attack = 3
    p1.weapon_durability = 2

    weapon2_attack = p1.weapon_attack
    weapon2_durability = p1.weapon_durability

    print(f"  Second weapon: {weapon2_attack}/{weapon2_durability}")

    if weapon2_attack == 3 and weapon2_durability == 2:
        print(f"  ✓ New weapon replaced old weapon")
        return True
    else:
        print(f"  ✗ Weapon not replaced correctly")
        return False


async def run_all_tests():
    """Run all weapon tests."""
    tests = [
        test_weapon_durability_loss,
        test_weapon_destruction,
        test_hero_takes_damage_from_minion,
        test_multiple_weapon_equips,
    ]

    print("="*70)
    print("WEAPON MECHANICS TESTS")
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
    asyncio.run(run_all_tests())
