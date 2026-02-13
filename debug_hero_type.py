"""Debug hero type checking."""

import asyncio
from src.engine.game import Game
from src.engine.types import CardType
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.classic import CHILLWIND_YETI


async def check_hero_type():
    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()

    # Set active player
    game.state.active_player = p1.id

    hero = game.state.objects.get(p1.hero_id)
    print(f"Hero ID: {p1.hero_id}")
    print(f"Hero name: {hero.name}")
    print(f"Hero types: {hero.characteristics.types}")
    print(f"Has HERO type: {CardType.HERO in hero.characteristics.types}")
    print(f"Hero owner: {hero.owner}")
    print(f"Hero controller: {hero.controller}")

    # Try to attack
    p1.weapon_attack = 3
    p1.weapon_durability = 2

    print(f"\nWeapon: {p1.weapon_attack}/{p1.weapon_durability}")

    print(f"\nAttempting attack...")
    result = await game.combat_manager.declare_attack(p1.hero_id, p2.hero_id)

    print(f"Result events: {len(result)}")
    for e in result:
        print(f"  - {e.type}")

    print(f"\nWeapon after: {p1.weapon_attack}/{p1.weapon_durability}")
    print(f"Enemy life: {p2.life}")


if __name__ == "__main__":
    asyncio.run(check_hero_type())
