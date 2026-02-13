"""
Test new Hearthstone cards: Harvest Golem, Argent Commander, Arcane Missiles
"""

import asyncio
from src.engine.game import Game
from src.engine.types import ZoneType, EventType, Event, CardType
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.classic import (
    HARVEST_GOLEM, ARGENT_COMMANDER, ARCANE_MISSILES
)


async def test_harvest_golem_deathrattle():
    """Test that Harvest Golem spawns a 2/1 on death."""
    print("\n--- Test: Harvest Golem Deathrattle ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    await game.start_game()

    # Create Harvest Golem
    golem = game.create_object(
        name="Harvest Golem",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=HARVEST_GOLEM.characteristics,
        card_def=HARVEST_GOLEM
    )

    battlefield = game.state.zones.get('battlefield')
    minions_before = len([
        obj_id for obj_id in battlefield.objects
        if game.state.objects.get(obj_id) and
        CardType.MINION in game.state.objects[obj_id].characteristics.types
    ])

    # Kill the golem
    damage_event = Event(
        type=EventType.DAMAGE,
        payload={'target': golem.id, 'amount': 10, 'source': None}
    )
    game.pipeline.emit(damage_event)

    # Check state-based actions to remove dead minion
    game.check_state_based_actions()

    minions_after = len([
        obj_id for obj_id in battlefield.objects
        if game.state.objects.get(obj_id) and
        CardType.MINION in game.state.objects[obj_id].characteristics.types
    ])

    # Should have same number of minions (1 died, 1 spawned)
    if minions_after == minions_before:
        # Check if the new minion is 2/1
        damaged_golem = None
        for obj_id in battlefield.objects:
            obj = game.state.objects.get(obj_id)
            if obj and "Damaged Golem" in obj.name:
                damaged_golem = obj
                break

        if damaged_golem and damaged_golem.characteristics.power == 2:
            print(f"  ✓ Harvest Golem spawned 2/1 token on death")
        else:
            print(f"  ✗ Token stats incorrect")
    else:
        print(f"  ✗ Minion count: {minions_before} → {minions_after}")


async def test_argent_commander_dual_keywords():
    """Test Argent Commander has both Charge and Divine Shield."""
    print("\n--- Test: Argent Commander (Charge + Divine Shield) ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    await game.start_game()

    game.state.active_player = p1.id

    # Create Argent Commander
    commander = game.create_object(
        name="Argent Commander",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=ARGENT_COMMANDER.characteristics,
        card_def=ARGENT_COMMANDER
    )

    # Test Charge - should be able to attack immediately
    life_before = p2.life
    attack_events = await game.combat_manager.declare_attack(commander.id, p2.hero_id)

    can_attack = len(attack_events) > 0

    # Test Divine Shield - should have it
    has_shield = commander.state.divine_shield

    if can_attack and has_shield:
        print(f"  ✓ Argent Commander has Charge (attacked) and Divine Shield")
    else:
        print(f"  ✗ Charge: {can_attack}, Divine Shield: {has_shield}")


async def test_arcane_missiles_random_damage():
    """Test that Arcane Missiles distributes 3 damage."""
    print("\n--- Test: Arcane Missiles (Random 3 Damage) ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    await game.start_game()

    # Create enemy minion
    minion = game.create_object(
        name="Yeti",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=HARVEST_GOLEM.characteristics,  # Just need any minion
        card_def=HARVEST_GOLEM
    )

    # Create spell object
    spell = game.create_object(
        name="Arcane Missiles",
        owner_id=p1.id,
        zone=ZoneType.STACK,
        characteristics=ARCANE_MISSILES.characteristics,
        card_def=ARCANE_MISSILES
    )

    life_before = p2.life
    minion_dmg_before = minion.state.damage

    # Cast spell
    if ARCANE_MISSILES.spell_effect:
        events = ARCANE_MISSILES.spell_effect(spell, game.state, [])
        for event in events:
            game.pipeline.emit(event)

    total_damage = (p2.life < life_before) + (minion.state.damage > minion_dmg_before)
    life_damage = life_before - p2.life
    minion_damage = minion.state.damage - minion_dmg_before

    # Should deal exactly 3 damage total
    if life_damage + minion_damage == 3:
        print(f"  ✓ Arcane Missiles dealt 3 damage (hero: {life_damage}, minion: {minion_damage})")
    else:
        print(f"  ✗ Total damage: {life_damage + minion_damage} (expected 3)")


async def run_all_tests():
    """Run all new card tests."""
    tests = [
        test_harvest_golem_deathrattle,
        test_argent_commander_dual_keywords,
        test_arcane_missiles_random_damage,
    ]

    print("="*70)
    print("NEW HEARTHSTONE CARDS TEST")
    print("="*70)

    for test in tests:
        try:
            await test()
        except Exception as e:
            print(f"✗ {test.__name__} crashed: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*70)
    print("NEW CARDS TEST COMPLETE")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
