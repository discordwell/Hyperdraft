"""Debug hero power setup."""

import asyncio
from src.engine.game import Game
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.classic import CHILLWIND_YETI


async def debug_hero_power_setup():
    """Check if hero power interceptors are properly registered."""

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    print("Setting up Warrior...")
    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    print(f"\nPlayer 1 hero_power_id: {p1.hero_power_id}")

    # Check if hero power object exists
    hero_power_obj = game.state.objects.get(p1.hero_power_id)
    if hero_power_obj:
        print(f"Hero power object found: {hero_power_obj.name}")
        print(f"Hero power card_def: {hero_power_obj.card_def is not None}")
        if hero_power_obj.card_def:
            print(f"Card def has setup_interceptors: {hero_power_obj.card_def.setup_interceptors is not None}")
    else:
        print("Hero power object NOT found!")
        return

    # Check registered interceptors
    print(f"\nTotal interceptors registered: {len(game.state.interceptors)}")

    # Look for hero power interceptors
    hero_power_interceptors = [i for i in game.state.interceptors.values() if 'hero_power' in i.id.lower()]
    print(f"Hero power interceptors: {len(hero_power_interceptors)}")

    for interceptor in hero_power_interceptors:
        print(f"  - {interceptor.id}, source: {interceptor.source}, priority: {interceptor.priority}")

    # Try to emit a HERO_POWER_ACTIVATE event directly
    from src.engine.types import Event, EventType

    print(f"\nEmitting HERO_POWER_ACTIVATE event...")
    print(f"  hero_power_id: {p1.hero_power_id}")
    print(f"  player: {p1.id}")
    print(f"  Armor before: {p1.armor}")

    power_event = Event(
        type=EventType.HERO_POWER_ACTIVATE,
        payload={'hero_power_id': p1.hero_power_id, 'player': p1.id},
        source=p1.hero_power_id
    )

    # Test filter and handler manually
    print(f"\nManually testing interceptor:")
    hero_power_interceptor = hero_power_interceptors[0]
    filter_result = hero_power_interceptor.filter(power_event, game.state)
    print(f"  Filter matches: {filter_result}")

    if filter_result:
        print(f"  Calling handler...")
        print(f"  hero_power_used before: {p1.hero_power_used}")
        handler_result = hero_power_interceptor.handler(power_event, game.state)
        print(f"  Handler action: {handler_result.action}")
        print(f"  Handler new_events: {len(handler_result.new_events)}")
        for ev in handler_result.new_events:
            print(f"    - {ev.type}")
        print(f"  hero_power_used after: {p1.hero_power_used}")
        print(f"  Armor after handler: {p1.armor}")

    result_events = game.pipeline.emit(power_event)

    print(f"  Events returned: {len(result_events)}")
    for event in result_events:
        print(f"    - {event.type}, payload: {event.payload}")

    print(f"  Armor after: {p1.armor}")
    print(f"  hero_power_used: {p1.hero_power_used}")


if __name__ == "__main__":
    asyncio.run(debug_hero_power_setup())
