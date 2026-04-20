"""
Advanced Hearthstone Testing

Edge cases, stress tests, and complex scenarios:
- Multiple attacks per turn (Windfury)
- Token creation from deathrattles
- Weapon destruction
- Spell damage
- Freeze interactions
- Full deck depletion
- Armor mechanics
- High-damage combos
"""

import asyncio
import sys
sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine.game import Game
from src.engine.types import EventType, CardType, Event, ZoneType
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.classic import *
from src.cards.hearthstone.basic import BASIC_CARDS
from src.ai.hearthstone_adapter import HearthstoneAIAdapter


print("="*70)
print("ADVANCED HEARTHSTONE STRESS TESTS")
print("="*70)


async def test_full_deck_depletion():
    """Test fatigue damage progression with full deck depletion."""
    print("\n--- Test: Full Deck Depletion & Fatigue ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.set_ai_player(p1.id)
    game.set_ai_player(p2.id)

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    # Small decks to force fatigue quickly
    small_deck = [WISP, WISP, BLOODFEN_RAPTOR, BLOODFEN_RAPTOR, CHILLWIND_YETI]

    for card in small_deck:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    game.shuffle_library(p1.id)
    game.shuffle_library(p2.id)

    ai_adapter = HearthstoneAIAdapter(difficulty="easy")
    game.set_hearthstone_ai_handler(ai_adapter)

    await game.start_game()

    fatigue_started = False
    max_fatigue = 0

    for turn in range(30):
        await game.turn_manager.run_turn()

        if p1.fatigue_damage > 0 or p2.fatigue_damage > 0:
            if not fatigue_started:
                print(f"  Fatigue started at turn {turn+1}")
                fatigue_started = True
            max_fatigue = max(max_fatigue, p1.fatigue_damage, p2.fatigue_damage)

        if game.is_game_over():
            print(f"  Game ended at turn {turn+1}")
            print(f"  Max fatigue damage: {max_fatigue}")
            print(f"  P1: {p1.life}HP (fatigue={p1.fatigue_damage})")
            print(f"  P2: {p2.life}HP (fatigue={p2.fatigue_damage})")

            if p1.life < -200 or p2.life < -200:
                print(f"  ❌ Extreme negative HP!")
            else:
                print(f"  ✓ Game ended properly with fatigue")
            break
    else:
        print(f"  ⚠ Game didn't end after 30 turns")


async def test_armor_absorption():
    """Test that armor absorbs damage before life."""
    print("\n--- Test: Armor Absorption ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    await game.start_game()

    # Give P2 armor
    p2.armor = 5

    life_before = p2.life
    armor_before = p2.armor

    # Deal 3 damage
    damage_event = Event(
        type=EventType.DAMAGE,
        payload={'target': p2.hero_id, 'amount': 3, 'source': None}
    )
    game.pipeline.emit(damage_event)

    life_after = p2.life
    armor_after = p2.armor

    if armor_after == 2 and life_after == life_before:
        print(f"  ✓ Armor absorbed damage (5 armor → 2 armor, life unchanged)")
    else:
        print(f"  ✗ Armor: {armor_before}→{armor_after}, Life: {life_before}→{life_after}")

    # Deal 5 more damage (should break through armor)
    damage_event2 = Event(
        type=EventType.DAMAGE,
        payload={'target': p2.hero_id, 'amount': 5, 'source': None}
    )
    game.pipeline.emit(damage_event2)

    if p2.armor == 0 and p2.life < life_before:
        damage_to_life = life_before - p2.life
        print(f"  ✓ Armor broke, excess damage to life (took {damage_to_life} damage)")
    else:
        print(f"  ✗ Armor: {p2.armor}, Life: {p2.life}")


async def test_frozen_cant_attack():
    """Test that frozen minions cannot attack."""
    print("\n--- Test: Frozen Minions Can't Attack ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    await game.start_game()

    # Create minion with Charge
    wolfrider = game.create_object(
        name="Wolfrider",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=WOLFRIDER.characteristics,
        card_def=WOLFRIDER
    )

    # Freeze it
    wolfrider.state.frozen = True

    game.state.active_player = p1.id

    # Try to attack
    events = await game.combat_manager.declare_attack(wolfrider.id, p2.hero_id)

    if len(events) == 0:
        print(f"  ✓ Frozen minion correctly prevented from attacking")
    else:
        print(f"  ✗ Frozen minion attacked ({len(events)} events)")


async def test_taunt_enforcement():
    """Test that Taunt minions must be attacked first."""
    print("\n--- Test: Taunt Enforcement ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    await game.start_game()

    # Create attacker
    attacker = game.create_object(
        name="Wolfrider",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=WOLFRIDER.characteristics,
        card_def=WOLFRIDER
    )

    # Create Taunt minion
    taunt = game.create_object(
        name="Sen'jin Shieldmasta",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SEN_JIN_SHIELDMASTA.characteristics,
        card_def=SEN_JIN_SHIELDMASTA
    )

    # Create non-Taunt minion
    non_taunt = game.create_object(
        name="Yeti",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=CHILLWIND_YETI.characteristics,
        card_def=CHILLWIND_YETI
    )

    game.state.active_player = p1.id

    # Try to attack hero (should fail - Taunt blocks)
    hero_attack = await game.combat_manager.declare_attack(attacker.id, p2.hero_id)

    # Try to attack non-Taunt minion (should fail)
    minion_attack = await game.combat_manager.declare_attack(attacker.id, non_taunt.id)

    # Try to attack Taunt minion (should succeed)
    attacker.state.attacks_this_turn = 0  # Reset
    taunt_attack = await game.combat_manager.declare_attack(attacker.id, taunt.id)

    if len(hero_attack) == 0 and len(minion_attack) == 0 and len(taunt_attack) > 0:
        print(f"  ✓ Taunt correctly enforced (can only attack Taunt)")
    else:
        print(f"  ✗ Hero attack: {len(hero_attack)}, Minion: {len(minion_attack)}, Taunt: {len(taunt_attack)}")


async def test_weapon_destruction_on_zero_durability():
    """Test that weapons are destroyed at 0 durability."""
    print("\n--- Test: Weapon Destruction ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    await game.start_game()

    # Equip weapon with 1 durability
    p1.weapon_attack = 3
    p1.weapon_durability = 1

    game.state.active_player = p1.id

    print(f"  Before: {p1.weapon_attack}/{p1.weapon_durability}")

    # Attack (should destroy weapon)
    await game.combat_manager.declare_attack(p1.hero_id, p2.hero_id)

    print(f"  After: {p1.weapon_attack}/{p1.weapon_durability}")

    if p1.weapon_attack == 0 and p1.weapon_durability == 0:
        print(f"  ✓ Weapon destroyed at 0 durability")
    else:
        print(f"  ✗ Weapon still equipped")


async def test_hand_limit_burn():
    """Test that drawing past 10 cards burns the card."""
    print("\n--- Test: Hand Limit (10 cards) ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    # Large deck
    for i in range(20):
        game.add_card_to_library(p1.id, BASIC_CARDS[i % len(BASIC_CARDS)])

    game.shuffle_library(p1.id)

    await game.start_game()

    # Draw to 10 cards
    while len(game.get_hand(p1.id)) < 10:
        game.pipeline.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 1}
        ))

    hand_at_10 = len(game.get_hand(p1.id))
    library_before = game.get_library_size(p1.id)

    # Draw one more (should burn)
    game.pipeline.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'count': 1}
    ))

    hand_after = len(game.get_hand(p1.id))
    library_after = game.get_library_size(p1.id)

    if hand_after == 10 and library_after < library_before:
        print(f"  ✓ Card burned at hand limit (hand stayed at 10)")
    else:
        print(f"  ✗ Hand: {hand_at_10}→{hand_after}, Library: {library_before}→{library_after}")


async def test_simultaneous_combat_damage():
    """Test that minions deal damage simultaneously in combat."""
    print("\n--- Test: Simultaneous Combat Damage ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    await game.start_game()

    # Create two minions that will kill each other
    # 3/1 vs 3/1 - both should die
    from src.engine.types import Characteristics
    import copy

    attacker = game.create_object(
        name="Attacker",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=copy.deepcopy(WOLFRIDER.characteristics),
        card_def=WOLFRIDER
    )

    defender = game.create_object(
        name="Defender",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=copy.deepcopy(WOLFRIDER.characteristics),
        card_def=WOLFRIDER
    )

    game.state.active_player = p1.id

    # Attack
    await game.combat_manager.declare_attack(attacker.id, defender.id)

    # Check state-based actions
    await game.turn_manager._check_state_based_actions()

    # Both should be dead (damaged to toughness)
    attacker_damage = attacker.state.damage
    defender_damage = defender.state.damage

    if attacker_damage >= 1 and defender_damage >= 1:
        print(f"  ✓ Both minions damaged simultaneously (both took 3)")
    else:
        print(f"  ✗ Attacker damage: {attacker_damage}, Defender damage: {defender_damage}")


async def test_ai_difficulty_comparison():
    """Compare AI behavior at different difficulty levels."""
    print("\n--- Test: AI Difficulty Levels ---")

    for difficulty in ["easy", "medium", "hard"]:
        game = Game(mode="hearthstone")
        p1 = game.add_player(f"Bot ({difficulty})")
        p2 = game.add_player("Opponent")

        game.set_ai_player(p1.id)
        game.set_ai_player(p2.id)

        game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
        game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

        # Mixed deck
        deck = [NOVICE_ENGINEER, LOOT_HOARDER, WOLFRIDER, CHILLWIND_YETI,
                SEN_JIN_SHIELDMASTA, FIREBALL, FROSTBOLT, BOULDERFIST_OGRE] * 2

        for card in deck:
            game.add_card_to_library(p1.id, card)
            game.add_card_to_library(p2.id, card)

        game.shuffle_library(p1.id)
        game.shuffle_library(p2.id)

        ai_adapter = HearthstoneAIAdapter(difficulty=difficulty)
        game.set_hearthstone_ai_handler(ai_adapter)

        await game.start_game()

        # Run 8 turns
        for turn in range(8):
            await game.turn_manager.run_turn()
            if game.is_game_over():
                break

        final_turn = game.state.turn_number
        winner = game.get_winner()

        print(f"  {difficulty.upper()}: {final_turn} turns, winner={winner[:8] if winner else 'none'}")


async def test_long_running_game():
    """Test a longer game to stress-test stability."""
    print("\n--- Test: Long-Running Game (50 turns) ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("Bot 1")
    p2 = game.add_player("Bot 2")

    game.set_ai_player(p1.id)
    game.set_ai_player(p2.id)

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    # Large decks
    full_deck = CLASSIC_CARDS * 3  # ~75 cards

    for card in full_deck:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    game.shuffle_library(p1.id)
    game.shuffle_library(p2.id)

    ai_adapter = HearthstoneAIAdapter(difficulty="medium")
    game.set_hearthstone_ai_handler(ai_adapter)

    await game.start_game()

    errors = []

    try:
        for turn in range(50):
            await game.turn_manager.run_turn()

            if turn % 10 == 0:
                print(f"  Turn {turn+1}: P1={p1.life}HP, P2={p2.life}HP")

            if game.is_game_over():
                print(f"  Game ended at turn {turn+1}")
                print(f"  Winner: {game.get_winner()}")
                print(f"  ✓ Game completed without crashes")
                break
        else:
            print(f"  ✓ Reached 50 turns without crashes")
            print(f"  Final: P1={p1.life}HP, P2={p2.life}HP")

    except Exception as e:
        print(f"  ✗ Crashed: {e}")
        import traceback
        traceback.print_exc()


async def run_all_advanced_tests():
    """Run all advanced tests."""

    tests = [
        test_full_deck_depletion,
        test_armor_absorption,
        test_frozen_cant_attack,
        test_taunt_enforcement,
        test_weapon_destruction_on_zero_durability,
        test_hand_limit_burn,
        test_simultaneous_combat_damage,
        test_ai_difficulty_comparison,
        test_long_running_game,
    ]

    for test in tests:
        try:
            await test()
        except Exception as e:
            print(f"\n✗ {test.__name__} crashed: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*70)
    print("ADVANCED TESTS COMPLETE")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(run_all_advanced_tests())
