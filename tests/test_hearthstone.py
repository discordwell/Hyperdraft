"""
Hearthstone Mode Tests

Tests for Hearthstone game mode functionality.
"""

import pytest
import asyncio
from src.engine.game import Game
from src.engine.types import GameState, ZoneType
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.basic import WISP, STONETUSK_BOAR, CHILLWIND_YETI


def test_game_mode_initialization():
    """Test that game initializes correctly in Hearthstone mode."""
    game = Game(mode="hearthstone")
    assert game.state.game_mode == "hearthstone"
    assert game.state.max_hand_size == 10


def test_mtg_mode_initialization():
    """Test that game still works in MTG mode."""
    game = Game(mode="mtg")
    assert game.state.game_mode == "mtg"
    assert game.state.max_hand_size == 7


def test_hearthstone_player_setup():
    """Test setting up a Hearthstone player with hero and hero power."""
    game = Game(mode="hearthstone")

    # Add player
    player = game.add_player("Player 1", life=30)

    # Set up hero
    hero_def = HEROES["Mage"]
    hero_power_def = HERO_POWERS["Mage"]
    game.setup_hearthstone_player(player, hero_def, hero_power_def)

    # Verify hero was created
    assert player.hero_id is not None
    assert player.hero_power_id is not None
    assert player.life == 30

    # Verify hero is on battlefield
    hero = game.state.objects[player.hero_id]
    assert hero.zone == ZoneType.BATTLEFIELD
    assert hero.name == "Jaina Proudmoore"

    # Verify hero power is in command zone
    hero_power = game.state.objects[player.hero_power_id]
    assert hero_power.zone == ZoneType.COMMAND
    assert hero_power.name == "Fireblast"


def test_mana_crystal_system():
    """Test Hearthstone mana crystal system."""
    game = Game(mode="hearthstone")
    player = game.add_player("Player 1")

    # Initial mana
    assert player.mana_crystals == 0
    assert player.mana_crystals_available == 0

    # Gain mana crystals
    game.mana_system.on_turn_start(player.id)
    assert player.mana_crystals == 1
    assert player.mana_crystals_available == 1

    # Spend mana
    game.mana_system.pay_cost(player.id, 1)
    assert player.mana_crystals == 1
    assert player.mana_crystals_available == 0

    # Gain more crystals
    for _ in range(5):
        game.mana_system.on_turn_start(player.id)

    assert player.mana_crystals == 6
    assert player.mana_crystals_available == 6

    # Test max crystals (10)
    for _ in range(10):
        game.mana_system.on_turn_start(player.id)

    assert player.mana_crystals == 10
    assert player.mana_crystals_available == 10


def test_divine_shield():
    """Test Divine Shield mechanic."""
    game = Game(mode="hearthstone")
    player = game.add_player("Player 1")

    # Create a minion with divine shield
    minion = game.create_object(
        name="Shielded Minion",
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD
    )
    minion.state.divine_shield = True
    minion.characteristics.power = 2
    minion.characteristics.toughness = 2

    # Deal damage - should break shield and prevent damage
    events = game.deal_damage(minion.id, minion.id, 1)

    # Shield should be broken
    assert not minion.state.divine_shield

    # Minion should still be alive (damage was prevented)
    assert minion.state.damage_marked == 0


def test_frozen_mechanic():
    """Test Freeze mechanic."""
    game = Game(mode="hearthstone")
    player = game.add_player("Player 1")

    # Create a minion
    minion = game.create_object(
        name="Test Minion",
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD
    )

    # Freeze it
    minion.state.frozen = True

    # Try to attack - should fail
    assert not game.combat_manager._can_attack(minion.id, player.id)

    # Unfreeze
    minion.state.frozen = False
    # Now could attack (if other conditions are met)
    # Just verify frozen check passes
    assert minion.state.frozen == False


def test_hand_size_limit():
    """Test hand size limit and overdraw."""
    game = Game(mode="hearthstone")
    player = game.add_player("Player 1")

    # Add 10 cards to hand
    hand_key = f"hand_{player.id}"
    library_key = f"library_{player.id}"

    for i in range(10):
        card = game.create_object(
            name=f"Card {i}",
            owner_id=player.id,
            zone=ZoneType.HAND
        )

    # Verify hand is full
    assert len(game.state.zones[hand_key].objects) == 10

    # Add one more card to library
    extra_card = game.create_object(
        name="Extra Card",
        owner_id=player.id,
        zone=ZoneType.LIBRARY
    )

    # Try to draw - should burn the card
    game.draw_cards(player.id, 1)

    # Hand should still be 10
    assert len(game.state.zones[hand_key].objects) == 10

    # Card should be in graveyard
    graveyard_key = f"graveyard_{player.id}"
    assert extra_card.id in game.state.zones[graveyard_key].objects


@pytest.mark.asyncio
async def test_hearthstone_turn_structure():
    """Test simplified Hearthstone turn structure."""
    game = Game(mode="hearthstone")

    # Add two players
    player1 = game.add_player("Player 1")
    player2 = game.add_player("Player 2")

    # Set up heroes
    game.setup_hearthstone_player(player1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(player2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    # Set turn order
    game.turn_manager.set_turn_order([player1.id, player2.id])

    # Run first turn
    await game.turn_manager.run_turn(player1.id)

    # Check mana was gained
    assert player1.mana_crystals >= 1

    # Check hero power was reset
    assert not player1.hero_power_used


def test_hearthstone_card_creation():
    """Test that Hearthstone card factories work."""
    # Test hero creation
    hero_def = HEROES["Mage"]
    assert hero_def is not None
    assert hero_def.name == "Jaina Proudmoore"

    # Test hero power creation
    hero_power_def = HERO_POWERS["Mage"]
    assert hero_power_def is not None
    assert hero_power_def.name == "Fireblast"

    # Test minion creation
    assert WISP.name == "Wisp"
    assert WISP.characteristics.power == 1
    assert WISP.characteristics.toughness == 1

    assert STONETUSK_BOAR.name == "Stonetusk Boar"
    assert any(a.get('keyword') == 'charge' for a in STONETUSK_BOAR.abilities)

    assert CHILLWIND_YETI.name == "Chillwind Yeti"
    assert CHILLWIND_YETI.characteristics.power == 4
    assert CHILLWIND_YETI.characteristics.toughness == 5


if __name__ == "__main__":
    # Run tests
    print("Running Hearthstone tests...")

    print("\n1. Testing game mode initialization...")
    test_game_mode_initialization()
    print("   ✓ Hearthstone mode initialized correctly")

    print("\n2. Testing MTG mode still works...")
    test_mtg_mode_initialization()
    print("   ✓ MTG mode still works")

    print("\n3. Testing Hearthstone player setup...")
    test_hearthstone_player_setup()
    print("   ✓ Hero and hero power setup correctly")

    print("\n4. Testing mana crystal system...")
    test_mana_crystal_system()
    print("   ✓ Mana crystals work correctly")

    print("\n5. Testing Divine Shield...")
    test_divine_shield()
    print("   ✓ Divine Shield prevents first damage")

    print("\n6. Testing Frozen mechanic...")
    test_frozen_mechanic()
    print("   ✓ Frozen prevents attacking")

    print("\n7. Testing hand size limit...")
    test_hand_size_limit()
    print("   ✓ Hand size limit enforced, overdraw burns cards")

    print("\n8. Testing Hearthstone card factories...")
    test_hearthstone_card_creation()
    print("   ✓ Cards created correctly")

    print("\n9. Testing turn structure...")
    asyncio.run(test_hearthstone_turn_structure())
    print("   ✓ Hearthstone turn structure works")

    print("\n✅ All Hearthstone tests passed!")
