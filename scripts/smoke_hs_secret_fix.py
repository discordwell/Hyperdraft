"""
Smoke test for the Hearthstone SECRET legal-action gap fix.

Runs 5 AI-vs-AI games (Hunter vs Paladin) and tracks how often the
3 shipping starter-deck secrets reach the battlefield:

  - Explosive Trap (Hunter)
  - Freezing Trap (Hunter)
  - Noble Sacrifice (Paladin)  -- 2 copies

Before the fix, NONE of these would reach the battlefield because the
MINION/WEAPON/SPELL elif chain in both card-play dispatchers silently
no-op'd on CardType.SECRET.

Acceptance: at least one copy of each shipping secret reaches the
battlefield across 5 games.
"""

import asyncio
import sys
import os

# Run-from-anywhere
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.engine.game import Game
from src.engine.types import CardType, ZoneType
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.decks import HEARTHSTONE_DECKS
from src.ai.hearthstone_adapter import HearthstoneAIAdapter


SHIPPING_SECRETS = {"Explosive Trap", "Freezing Trap", "Noble Sacrifice"}


async def run_game(class1: str, class2: str, game_number: int, max_turns: int = 30):
    """Run one HS game; return per-secret-name counts of (saw_battlefield, saw_graveyard)."""
    game = Game(mode="hearthstone")
    p1 = game.add_player(f"P1_{class1}", life=30)
    p2 = game.add_player(f"P2_{class2}", life=30)

    game.setup_hearthstone_player(p1, HEROES[class1], HERO_POWERS[class1])
    game.setup_hearthstone_player(p2, HEROES[class2], HERO_POWERS[class2])

    for card_def in HEARTHSTONE_DECKS[class1]:
        game.add_card_to_library(p1.id, card_def)
    for card_def in HEARTHSTONE_DECKS[class2]:
        game.add_card_to_library(p2.id, card_def)
    game.shuffle_library(p1.id)
    game.shuffle_library(p2.id)

    ai_adapter = HearthstoneAIAdapter(difficulty="hard")
    game.turn_manager.hearthstone_ai_handler = ai_adapter
    game.turn_manager.ai_players = {p1.id, p2.id}
    game.get_mulligan_decision = lambda pid, hand, count: True
    await game.start_game()
    if not game.state.active_player:
        game.state.active_player = p1.id

    # Per-game tracking
    saw_on_battlefield = set()
    saw_in_graveyard = set()
    seen_object_ids_on_bf = set()

    turn_count = 0
    while turn_count < max_turns:
        turn_count += 1
        if p1.has_lost or p2.has_lost or p1.life <= 0 or p2.life <= 0:
            break
        try:
            await game.turn_manager.run_turn()
        except Exception as e:
            print(f"  game {game_number} turn {turn_count}: {type(e).__name__}: {e}")
            break

        # Scan battlefield for shipping secrets
        bf_zone = game.state.zones.get("battlefield")
        if bf_zone:
            for oid in bf_zone.objects:
                obj = game.state.objects.get(oid)
                if not obj:
                    continue
                if (
                    CardType.SECRET in obj.characteristics.types
                    and obj.name in SHIPPING_SECRETS
                ):
                    saw_on_battlefield.add(obj.name)
                    seen_object_ids_on_bf.add(oid)

        # Scan graveyards for any of those secrets that have already triggered
        for pid in (p1.id, p2.id):
            gy = game.state.zones.get(f"graveyard_{pid}")
            if not gy:
                continue
            for oid in gy.objects:
                obj = game.state.objects.get(oid)
                if not obj:
                    continue
                if (
                    CardType.SECRET in obj.characteristics.types
                    and obj.name in SHIPPING_SECRETS
                ):
                    saw_in_graveyard.add(obj.name)

    return {
        "game_number": game_number,
        "turns": turn_count,
        "p1_life": p1.life,
        "p2_life": p2.life,
        "saw_on_battlefield": saw_on_battlefield,
        "saw_in_graveyard": saw_in_graveyard,
    }


async def main():
    matchups = [
        ("Hunter", "Paladin"),
        ("Paladin", "Hunter"),
        ("Hunter", "Hunter"),
        ("Paladin", "Paladin"),
        ("Hunter", "Mage"),
    ]

    aggregate_bf = set()
    aggregate_gy = set()
    print("--- HS SECRET smoke test (5 games) ---")
    for i, (a, b) in enumerate(matchups, 1):
        result = await run_game(a, b, i)
        print(
            f"game {i} ({a} vs {b}): turns={result['turns']} "
            f"p1.life={result['p1_life']} p2.life={result['p2_life']} "
            f"bf={sorted(result['saw_on_battlefield'])} "
            f"gy={sorted(result['saw_in_graveyard'])}"
        )
        aggregate_bf |= result["saw_on_battlefield"]
        aggregate_gy |= result["saw_in_graveyard"]

    print()
    print(f"aggregate on battlefield: {sorted(aggregate_bf)}")
    print(f"aggregate fired (in graveyard): {sorted(aggregate_gy)}")
    missing = SHIPPING_SECRETS - aggregate_bf
    if missing:
        print(f"MISSING (never reached battlefield in 5 games): {sorted(missing)}")
        return 1
    print("PASS: all 3 shipping secrets reached battlefield at least once.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
