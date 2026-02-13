"""Simple debug - just emit the event without manual testing."""

import asyncio
from src.engine.game import Game
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.classic import CHILLWIND_YETI


async def test():
    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()

    print(f"Hero power ID: {p1.hero_power_id}")
    print(f"Total interceptors: {len(game.state.interceptors)}")

    # Check if hero power interceptor exists
    hero_power_interceptors = [i for i in game.state.interceptors.values() if 'hero_power' in i.id and i.source == p1.hero_power_id]
    print(f"Hero power interceptors for P1: {len(hero_power_interceptors)}")
    if hero_power_interceptors:
        interceptor = hero_power_interceptors[0]
        print(f"  ID: {interceptor.id}")
        print(f"  Priority: {interceptor.priority}")

    print(f"\nArmor before: {p1.armor}")
    print(f"hero_power_used before: {p1.hero_power_used}")

    # Emit event
    from src.engine.types import Event, EventType

    power_event = Event(
        type=EventType.HERO_POWER_ACTIVATE,
        payload={'hero_power_id': p1.hero_power_id, 'player': p1.id},
        source=p1.hero_power_id
    )

    # Test filter and handler manually first
    print(f"\nManual test of filter/handler:")
    if hero_power_interceptors:
        interceptor = hero_power_interceptors[0]
        filter_matches = interceptor.filter(power_event, game.state)
        print(f"  Filter matches: {filter_matches}")
        if filter_matches:
            print(f"  Calling handler...")
            handler_result = interceptor.handler(power_event, game.state)
            print(f"  Handler action: {handler_result.action}")
            print(f"  Handler new_events: {len(handler_result.new_events)}")
            print(f"  Armor after manual handler call: {p1.armor}")
            print(f"  hero_power_used after manual handler call: {p1.hero_power_used}")

            # Reset for actual test
            p1.armor = 0
            p1.hero_power_used = False
            print(f"  (Reset state for actual pipeline test)")

    print(f"\nEmitting event via pipeline...")
    result_events = game.pipeline.emit(power_event)

    print(f"\nPipeline result:")
    print(f"  Events returned: {len(result_events)}")
    for e in result_events:
        print(f"    - {e.type}")
    print(f"  Armor after: {p1.armor}")
    print(f"  hero_power_used after: {p1.hero_power_used}")


if __name__ == "__main__":
    asyncio.run(test())
