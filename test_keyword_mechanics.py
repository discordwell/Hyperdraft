"""
Test Hearthstone keyword mechanics.

Keywords to test:
- Divine Shield (prevents first damage)
- Stealth (can't be targeted, breaks on attack)
- Windfury (attack twice per turn)
- Taunt (must be attacked first)
- Freeze (can't attack next turn)
"""

import asyncio
from src.engine.game import Game
from src.engine.types import ZoneType, CardType
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.classic import CHILLWIND_YETI, BLOODFEN_RAPTOR, SILVERMOON_GUARDIAN


async def test_divine_shield_blocks_damage():
    """Test that Divine Shield prevents the first instance of damage."""
    print("\n--- Test: Divine Shield Blocks Damage ---")

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

    # Create minion with Divine Shield
    shielded = game.create_object(
        name="Silvermoon Guardian",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SILVERMOON_GUARDIAN.characteristics,
        card_def=SILVERMOON_GUARDIAN
    )

    # Create attacker
    attacker = game.create_object(
        name="Raptor",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=BLOODFEN_RAPTOR.characteristics,
        card_def=BLOODFEN_RAPTOR
    )
    attacker.state.summoning_sickness = False

    print(f"  Shielded minion: {shielded.characteristics.power}/{shielded.characteristics.toughness}")
    print(f"  Has Divine Shield: {shielded.state.divine_shield}")
    print(f"  Attacker: {attacker.characteristics.power}/{attacker.characteristics.toughness}")

    # Set active player to attacker's controller
    game.state.active_player = p2.id

    # Attack the shielded minion
    await game.combat_manager.declare_attack(attacker.id, shielded.id)

    health_after = shielded.characteristics.toughness - shielded.state.damage
    shield_after = shielded.state.divine_shield
    attacker_health = attacker.characteristics.toughness - attacker.state.damage

    print(f"  After attack:")
    print(f"    Shielded minion: {health_after}/{shielded.characteristics.toughness} (damage: {shielded.state.damage})")
    print(f"    Divine Shield: {shield_after}")
    print(f"    Attacker health: {attacker_health}/{attacker.characteristics.toughness}")

    # Divine Shield should break but minion takes no damage
    # Attacker should take full damage from shielded minion
    if not shield_after and shielded.state.damage == 0 and attacker.state.damage > 0:
        print(f"  ✓ Divine Shield worked (broke, no damage taken)")
        return True
    else:
        print(f"  ✗ Divine Shield didn't work correctly")
        return False


async def test_divine_shield_breaks_then_takes_damage():
    """Test that after Divine Shield breaks, the minion takes damage normally."""
    print("\n--- Test: Divine Shield Breaks Then Takes Damage ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    for card in [CHILLWIND_YETI] * 30:
        game.add_card_to_library(p1.id, card)
        game.add_card_to_library(p2.id, card)

    await game.start_game()

    # Create minion with Divine Shield
    shielded = game.create_object(
        name="Silvermoon Guardian",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SILVERMOON_GUARDIAN.characteristics,
        card_def=SILVERMOON_GUARDIAN
    )

    # Create two attackers
    attacker1 = game.create_object(
        name="Raptor1",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=BLOODFEN_RAPTOR.characteristics,
        card_def=BLOODFEN_RAPTOR
    )
    attacker1.state.summoning_sickness = False

    attacker2 = game.create_object(
        name="Raptor2",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=BLOODFEN_RAPTOR.characteristics,
        card_def=BLOODFEN_RAPTOR
    )
    attacker2.state.summoning_sickness = False

    print(f"  Shielded minion: 3/{shielded.characteristics.toughness}")
    print(f"  Shield: {shielded.state.divine_shield}")

    game.state.active_player = p2.id

    # First attack - breaks shield
    await game.combat_manager.declare_attack(attacker1.id, shielded.id)

    damage_after_first = shielded.state.damage
    shield_after_first = shielded.state.divine_shield

    print(f"  After first attack: damage={damage_after_first}, shield={shield_after_first}")

    # Second attack - should deal damage
    await game.combat_manager.declare_attack(attacker2.id, shielded.id)

    damage_after_second = shielded.state.damage
    shield_after_second = shielded.state.divine_shield

    print(f"  After second attack: damage={damage_after_second}, shield={shield_after_second}")

    if damage_after_first == 0 and not shield_after_first and damage_after_second == 3:
        print(f"  ✓ First attack broke shield, second dealt damage")
        return True
    else:
        print(f"  ✗ Damage progression wrong")
        return False


async def test_stealth_cant_be_targeted():
    """Test that Stealth minions can't be targeted by attacks."""
    print("\n--- Test: Stealth Can't Be Targeted ---")

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

    # Create stealthed minion
    stealthed = game.create_object(
        name="Stealthed",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=CHILLWIND_YETI.characteristics,
        card_def=CHILLWIND_YETI
    )
    stealthed.state.stealth = True

    # Create attacker
    attacker = game.create_object(
        name="Attacker",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=BLOODFEN_RAPTOR.characteristics,
        card_def=BLOODFEN_RAPTOR
    )
    attacker.state.summoning_sickness = False

    print(f"  Stealthed: {stealthed.state.stealth}")
    print(f"  Attempting to attack stealthed minion...")

    # Try to attack stealthed minion
    events = await game.combat_manager.declare_attack(attacker.id, stealthed.id)

    print(f"  Events returned: {len(events)}")
    print(f"  Stealthed damage: {stealthed.state.damage}")

    if len(events) == 0 and stealthed.state.damage == 0:
        print(f"  ✓ Attack blocked by stealth")
        return True
    else:
        print(f"  ✗ Stealth didn't block attack")
        return False


async def test_stealth_breaks_on_attack():
    """Test that Stealth breaks when the minion attacks."""
    print("\n--- Test: Stealth Breaks on Attack ---")

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

    # Create stealthed minion
    stealthed = game.create_object(
        name="Stealthed",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=BLOODFEN_RAPTOR.characteristics,
        card_def=BLOODFEN_RAPTOR
    )
    stealthed.state.stealth = True
    stealthed.state.summoning_sickness = False

    # Create target
    target = game.create_object(
        name="Target",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=CHILLWIND_YETI.characteristics,
        card_def=CHILLWIND_YETI
    )

    print(f"  Stealth before attack: {stealthed.state.stealth}")

    # Stealthed minion attacks
    await game.combat_manager.declare_attack(stealthed.id, target.id)

    print(f"  Stealth after attack: {stealthed.state.stealth}")

    if not stealthed.state.stealth:
        print(f"  ✓ Stealth broke on attack")
        return True
    else:
        print(f"  ✗ Stealth didn't break")
        return False


async def test_windfury_double_attack():
    """Test that Windfury allows attacking twice."""
    print("\n--- Test: Windfury Double Attack ---")

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

    # Create windfury minion
    windfury = game.create_object(
        name="Windfury",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=BLOODFEN_RAPTOR.characteristics,
        card_def=BLOODFEN_RAPTOR
    )
    windfury.state.windfury = True
    windfury.state.summoning_sickness = False

    # Create target
    target = game.create_object(
        name="Target",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=CHILLWIND_YETI.characteristics,
        card_def=CHILLWIND_YETI
    )

    print(f"  Windfury minion: {windfury.characteristics.power}/{windfury.characteristics.toughness}")
    print(f"  Target: {target.characteristics.power}/{target.characteristics.toughness}")

    # First attack
    events1 = await game.combat_manager.declare_attack(windfury.id, target.id)
    damage_after_first = target.state.damage
    attacks_after_first = windfury.state.attacks_this_turn

    print(f"  After first attack: target damage={damage_after_first}, attacks={attacks_after_first}")

    # Second attack
    events2 = await game.combat_manager.declare_attack(windfury.id, target.id)
    damage_after_second = target.state.damage
    attacks_after_second = windfury.state.attacks_this_turn

    print(f"  After second attack: target damage={damage_after_second}, attacks={attacks_after_second}")

    # Third attack (should fail)
    events3 = await game.combat_manager.declare_attack(windfury.id, target.id)

    print(f"  Third attack events: {len(events3)}")

    if len(events1) > 0 and len(events2) > 0 and len(events3) == 0:
        print(f"  ✓ Windfury allowed 2 attacks, blocked 3rd")
        return True
    else:
        print(f"  ✗ Windfury didn't work correctly")
        return False


async def run_all_tests():
    """Run all keyword tests."""
    tests = [
        test_divine_shield_blocks_damage,
        test_divine_shield_breaks_then_takes_damage,
        test_stealth_cant_be_targeted,
        test_stealth_breaks_on_attack,
        test_windfury_double_attack,
    ]

    print("="*70)
    print("KEYWORD MECHANICS TESTS")
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
