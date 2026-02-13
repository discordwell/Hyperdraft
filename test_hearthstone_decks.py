"""
Test Hearthstone decks can be used in actual games.
"""

import asyncio
from src.engine.game import Game
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.decks import HEARTHSTONE_DECKS, validate_deck


async def test_all_decks():
    """Test that all 9 class decks can be used in games."""
    print("="*70)
    print("HEARTHSTONE DECK INTEGRATION TEST")
    print("="*70)

    for hero_class, deck in HEARTHSTONE_DECKS.items():
        print(f"\n--- Testing {hero_class} Deck ---")

        # Validate deck
        is_valid, error = validate_deck(deck)
        if not is_valid:
            print(f"  ✗ Deck invalid: {error}")
            continue

        # Create game
        game = Game(mode="hearthstone")
        p1 = game.add_player(f"P1_{hero_class}")
        p2 = game.add_player("P2_Opponent")

        # Setup heroes
        game.setup_hearthstone_player(p1, HEROES[hero_class], HERO_POWERS[hero_class])
        game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

        # Add cards to library
        for card in deck:
            game.add_card_to_library(p1.id, card)

        for card in HEARTHSTONE_DECKS["Warrior"]:
            game.add_card_to_library(p2.id, card)

        # Start game
        await game.start_game()

        # Check initial state
        p1_hand = len(game.get_hand(p1.id))
        p2_hand = len(game.get_hand(p2.id))
        p1_library = len(game.state.zones.get(f'library_{p1.id}').objects)
        p2_library = len(game.state.zones.get(f'library_{p2.id}').objects)

        # Play a few turns
        try:
            for _ in range(3):
                await game.turn_manager.run_turn()
        except Exception as e:
            print(f"  ✗ Turn error: {e}")
            continue

        # Check game is playable
        if p1.life > 0 and p2.life > 0:
            print(f"  ✓ {hero_class} deck works (P1: {p1.life}HP/{p1.mana_crystals}m, P2: {p2.life}HP/{p2.mana_crystals}m)")
        else:
            print(f"  ✗ Game ended too quickly")

    print("\n" + "="*70)
    print("DECK INTEGRATION TEST COMPLETE")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(test_all_decks())
