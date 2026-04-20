"""
Manual Hearthstone Game - Claude pilots a deck!
"""

import asyncio
from src.engine.game import Game
from src.engine.types import ZoneType, EventType, Event, CardType
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.decks import HEARTHSTONE_DECKS
from src.ai.hearthstone_adapter import HearthstoneAIAdapter


async def play_manual_game():
    """Play a Hearthstone game with manual control."""
    print("="*70)
    print("🔥 HEARTHSTONE LIVE GAME - CLAUDE VS BOT 🔥")
    print("="*70)

    # Create game
    game = Game(mode="hearthstone")
    claude = game.add_player("Claude")
    bot = game.add_player("Bot")

    # Choose random heroes
    import random
    available_classes = ["Mage", "Warrior", "Hunter", "Paladin", "Priest", "Rogue", "Shaman", "Warlock", "Druid"]
    claude_class = random.choice(available_classes)
    bot_class = random.choice([c for c in available_classes if c != claude_class])

    print(f"\n⚔️  MATCHUP: {claude_class} (Claude) vs {bot_class} (Bot)")
    print(f"📚 Deck: {len(HEARTHSTONE_DECKS[claude_class])} cards each\n")

    # Setup heroes
    game.setup_hearthstone_player(claude, HEROES[claude_class], HERO_POWERS[claude_class])
    game.setup_hearthstone_player(bot, HEROES[bot_class], HERO_POWERS[bot_class])

    # Load decks
    for card in HEARTHSTONE_DECKS[claude_class]:
        game.add_card_to_library(claude.id, card)

    for card in HEARTHSTONE_DECKS[bot_class]:
        game.add_card_to_library(bot.id, card)

    # Setup AI for both players (for demo purposes)
    ai_adapter = HearthstoneAIAdapter(difficulty="hard")

    # Configure turn manager to use AI for both players
    game.turn_manager.hearthstone_ai_handler = ai_adapter
    game.turn_manager.ai_players = {claude.id, bot.id}

    # Start game
    await game.start_game()

    print("🎮 GAME START!\n")

    # Manually set first active player if not set
    if not game.state.active_player:
        game.state.active_player = claude.id

    # Play turns
    turn_count = 0
    max_turns = 30

    while turn_count < max_turns:
        turn_count += 1

        if not game.state.active_player:
            print("⚠️  No active player, game may have ended")
            break

        active_player = game.state.players[game.state.active_player]

        print("="*70)
        print(f"⏰ TURN {turn_count} - {active_player.name}'s Turn")
        print("="*70)

        # Show game state
        print(f"\n📊 BOARD STATE:")
        print(f"  Claude ({claude_class}): {claude.life}HP, {claude.armor} Armor, {claude.mana_crystals_available}/{claude.mana_crystals} Mana")
        print(f"  Bot ({bot_class}): {bot.life}HP, {bot.armor} Armor, {bot.mana_crystals_available}/{bot.mana_crystals} Mana")

        # Show hands
        claude_hand = game.get_hand(claude.id)
        bot_hand = game.get_hand(bot.id)
        print(f"\n🎴 HAND SIZES: Claude: {len(claude_hand)}, Bot: {len(bot_hand)}")

        # Show Claude's hand
        if active_player.id == claude.id:
            print(f"\n🃏 YOUR HAND:")
            for i, card in enumerate(claude_hand):
                cost = card.characteristics.mana_cost or "{0}"
                if CardType.MINION in card.characteristics.types:
                    stats = f"{card.characteristics.power}/{card.characteristics.toughness}"
                    print(f"  {i+1}. {card.name} ({cost}) - {stats}")
                else:
                    print(f"  {i+1}. {card.name} ({cost})")

        # Show battlefield
        battlefield = game.state.zones.get('battlefield')
        claude_minions = []
        bot_minions = []

        if battlefield:
            for obj_id in battlefield.objects:
                obj = game.state.objects.get(obj_id)
                if obj and CardType.MINION in obj.characteristics.types:
                    if obj.controller == claude.id:
                        claude_minions.append(obj)
                    else:
                        bot_minions.append(obj)

        print(f"\n⚔️  BATTLEFIELD:")
        print(f"  Claude's Minions ({len(claude_minions)}):")
        for minion in claude_minions:
            power = minion.characteristics.power
            current_health = minion.characteristics.toughness - minion.state.damage
            attacks = f"[{minion.state.attacks_this_turn} attacks]" if minion.state.attacks_this_turn > 0 else ""
            shields = " 🛡️" if minion.state.divine_shield else ""
            taunt = " 🚫" if any(a.get('keyword') == 'taunt' for a in minion.characteristics.abilities) else ""
            print(f"    - {minion.name}: {power}/{current_health}{shields}{taunt} {attacks}")

        print(f"  Bot's Minions ({len(bot_minions)}):")
        for minion in bot_minions:
            power = minion.characteristics.power
            current_health = minion.characteristics.toughness - minion.state.damage
            attacks = f"[{minion.state.attacks_this_turn} attacks]" if minion.state.attacks_this_turn > 0 else ""
            shields = " 🛡️" if minion.state.divine_shield else ""
            taunt = " 🚫" if any(a.get('keyword') == 'taunt' for a in minion.characteristics.abilities) else ""
            print(f"    - {minion.name}: {power}/{current_health}{shields}{taunt} {attacks}")

        # Execute turn using turn manager
        if active_player.id == claude.id:
            print(f"\n🧠 CLAUDE'S TURN - Making strategic plays...")
        else:
            print(f"\n🤖 BOT'S TURN - Calculating moves...")

        # Let turn manager handle the turn (don't pass player_id to let it auto-advance)
        turn_events = await game.turn_manager.run_turn()

        # Check for winner
        if claude.life <= 0 and not claude.has_lost:
            print(f"\n💀 Claude has been defeated!")
            print(f"🏆 BOT WINS! ({bot_class})")
            break

        if bot.life <= 0 and not bot.has_lost:
            print(f"\n💀 Bot has been defeated!")
            print(f"🏆 CLAUDE WINS! ({claude_class})")
            break

        # Check for actual player loss flags
        if claude.has_lost:
            print(f"\n💀 Claude lost!")
            print(f"🏆 BOT WINS! ({bot_class})")
            break

        if bot.has_lost:
            print(f"\n💀 Bot lost!")
            print(f"🏆 CLAUDE WINS! ({claude_class})")
            break

        print()

        # Short pause for readability
        await asyncio.sleep(0.1)

    # Final stats
    print("\n" + "="*70)
    print("📈 FINAL STATS")
    print("="*70)
    print(f"  Claude: {claude.life}HP, {len(claude_minions)} minions")
    print(f"  Bot: {bot.life}HP, {len(bot_minions)} minions")
    print(f"  Turns played: {turn_count}")

    if claude.life > bot.life:
        print(f"\n🏆 VICTORY! Claude ({claude_class}) defeats Bot ({bot_class})!")
    elif bot.life > claude.life:
        print(f"\n💀 DEFEAT! Bot ({bot_class}) defeats Claude ({claude_class})!")
    else:
        print(f"\n🤝 DRAW!")


if __name__ == "__main__":
    asyncio.run(play_manual_game())
