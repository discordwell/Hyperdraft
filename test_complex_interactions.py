"""
Test complex Hearthstone interactions.

Scenarios:
- Freeze prevents attacking
- Taunt + Divine Shield interaction
- Deathrattle chains
- Multiple effects triggering
- AOE vs Divine Shield
"""

import asyncio
from src.engine.game import Game
from src.engine.types import ZoneType, CardType, Event, EventType
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.classic import (
    CHILLWIND_YETI, BLOODFEN_RAPTOR, HARVEST_GOLEM,
    SILVERMOON_GUARDIAN, FROSTBOLT
)


async def test_frozen_cant_attack():
    """Test that frozen minions can't attack."""
    print("\n--- Test: Frozen Minions Can't Attack ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()
    game.state.active_player = p1.id

    # Create minion and freeze it
    frozen = game.create_object(
        name="Frozen",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=BLOODFEN_RAPTOR.characteristics,
        card_def=BLOODFEN_RAPTOR
    )
    frozen.state.frozen = True

    # Create target
    target = game.create_object(
        name="Target",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=CHILLWIND_YETI.characteristics,
        card_def=CHILLWIND_YETI
    )

    print(f"  Frozen: {frozen.state.frozen}")
    print(f"  Attempting attack...")

    # Try to attack
    events = await game.combat_manager.declare_attack(frozen.id, target.id)

    print(f"  Events: {len(events)}")
    print(f"  Target damage: {target.state.damage}")

    if len(events) == 0 and target.state.damage == 0:
        print(f"  ✓ Frozen minion couldn't attack")
        return True
    else:
        print(f"  ✗ Frozen minion attacked")
        return False


async def test_freeze_unfreezes_next_turn():
    """Test that freeze wears off at end of frozen minion's next turn."""
    print("\n--- Test: Freeze Unfreezes Next Turn ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()

    # Create and freeze a minion
    frozen = game.create_object(
        name="Frozen",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=BLOODFEN_RAPTOR.characteristics,
        card_def=BLOODFEN_RAPTOR
    )
    frozen.state.frozen = True

    print(f"  Frozen before turn: {frozen.state.frozen}")

    # Run and end P1's turn (freeze clears in end-phase cleanup).
    await game.turn_manager.run_turn(p1.id)
    await game.turn_manager.end_turn()

    print(f"  Frozen after turn end: {frozen.state.frozen}")

    if not frozen.state.frozen:
        print(f"  ✓ Minion unfroze at start of turn")
        return True
    else:
        print(f"  ✗ Minion still frozen")
        return False


async def test_taunt_divine_shield():
    """Test that Taunt + Divine Shield works together."""
    print("\n--- Test: Taunt + Divine Shield ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()
    game.state.active_player = p1.id

    # Create taunt minion with divine shield
    import copy
    taunt_char = copy.deepcopy(SILVERMOON_GUARDIAN.characteristics)
    taunt_char.abilities.append({'keyword': 'taunt'})

    taunt_shield = game.create_object(
        name="TauntShield",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=taunt_char,
        card_def=SILVERMOON_GUARDIAN
    )

    # Create another minion (can't be attacked while taunt is up)
    other = game.create_object(
        name="Other",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=BLOODFEN_RAPTOR.characteristics,
        card_def=BLOODFEN_RAPTOR
    )

    # Create attacker
    attacker = game.create_object(
        name="Attacker",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=CHILLWIND_YETI.characteristics,
        card_def=CHILLWIND_YETI
    )
    attacker.state.summoning_sickness = False

    print(f"  Taunt minion: shield={taunt_shield.state.divine_shield}")
    print(f"  Attempting to attack non-taunt minion...")

    # Try to attack non-taunt (should fail due to taunt)
    events1 = await game.combat_manager.declare_attack(attacker.id, other.id)

    print(f"  Events: {len(events1)}")

    # Attack taunt minion
    print(f"  Attacking taunt minion...")
    events2 = await game.combat_manager.declare_attack(attacker.id, taunt_shield.id)

    shield_after = taunt_shield.state.divine_shield
    damage_after = taunt_shield.state.damage

    print(f"  Shield after: {shield_after}, damage: {damage_after}")

    if len(events1) == 0 and len(events2) > 0 and not shield_after and damage_after == 0:
        print(f"  ✓ Taunt enforced, divine shield blocked damage")
        return True
    else:
        print(f"  ✗ Didn't work correctly")
        return False


async def test_deathrattle_chain():
    """Test that deathrattle can spawn another minion that also has deathrattle."""
    print("\n--- Test: Deathrattle Chain ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()
    game.state.active_player = p1.id

    # Create Harvest Golem (dies → spawns Damaged Golem)
    golem = game.create_object(
        name="Harvest Golem",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=HARVEST_GOLEM.characteristics,
        card_def=HARVEST_GOLEM
    )

    # Deal lethal damage
    golem.state.damage = 3

    battlefield = game.state.zones.get('battlefield')
    minions_before = len([
        obj_id for obj_id in battlefield.objects
        if CardType.MINION in game.state.objects[obj_id].characteristics.types
    ])

    print(f"  Minions before SBA: {minions_before}")
    print(f"  Golem damage: {golem.state.damage}/{golem.characteristics.toughness}")

    # Run SBAs
    game.check_state_based_actions()

    minions_after = len([
        obj_id for obj_id in battlefield.objects
        if CardType.MINION in game.state.objects[obj_id].characteristics.types
    ])

    # Find the spawned token
    token = None
    for obj_id in battlefield.objects:
        obj = game.state.objects.get(obj_id)
        if obj and "Damaged Golem" in obj.name:
            token = obj
            break

    print(f"  Minions after SBA: {minions_after}")
    if token:
        print(f"  Token spawned: {token.name} ({token.characteristics.power}/{token.characteristics.toughness})")

    if minions_after == 1 and token and token.characteristics.power == 2:
        print(f"  ✓ Deathrattle spawned token")
        return True
    else:
        print(f"  ✗ Deathrattle didn't work")
        return False


async def test_multiple_minions_die_simultaneously():
    """Test that multiple minions dying at once all trigger deathrattles."""
    print("\n--- Test: Multiple Simultaneous Deaths ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()

    # Create 3 Harvest Golems
    golem1 = game.create_object(
        name="Golem1",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=HARVEST_GOLEM.characteristics,
        card_def=HARVEST_GOLEM
    )

    golem2 = game.create_object(
        name="Golem2",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=HARVEST_GOLEM.characteristics,
        card_def=HARVEST_GOLEM
    )

    golem3 = game.create_object(
        name="Golem3",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=HARVEST_GOLEM.characteristics,
        card_def=HARVEST_GOLEM
    )

    # Kill all 3
    golem1.state.damage = 3
    golem2.state.damage = 3
    golem3.state.damage = 3

    print(f"  Created 3 Harvest Golems, all at lethal damage")

    # Run SBAs
    game.check_state_based_actions()

    battlefield = game.state.zones.get('battlefield')
    tokens = []
    for obj_id in battlefield.objects:
        obj = game.state.objects.get(obj_id)
        if obj and "Damaged Golem" in obj.name:
            tokens.append(obj)

    print(f"  Tokens spawned: {len(tokens)}")

    if len(tokens) == 3:
        print(f"  ✓ All 3 deathrattles triggered")
        return True
    else:
        print(f"  ✗ Only {len(tokens)} deathrattles triggered")
        return False


async def run_all_tests():
    """Run all complex interaction tests."""
    tests = [
        test_frozen_cant_attack,
        test_freeze_unfreezes_next_turn,
        test_taunt_divine_shield,
        test_deathrattle_chain,
        test_multiple_minions_die_simultaneously,
    ]

    print("="*70)
    print("COMPLEX INTERACTIONS TESTS")
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
