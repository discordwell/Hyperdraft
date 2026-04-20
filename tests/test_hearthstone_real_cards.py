"""
Real Hearthstone Cards Testing Suite

Test actual Hearthstone cards with complex mechanics:
- Battlecries
- Deathrattles
- Spell effects
- Weapons
- Combat interactions
"""

import asyncio
import sys
sys.path.insert(0, '/Users/discordwell/Projects/Hyperdraft')

from src.engine.game import Game
from src.engine.types import EventType, CardType, Event, ZoneType
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.classic import *
from src.ai.hearthstone_adapter import HearthstoneAIAdapter


class TestTracker:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []

    def test_pass(self, name, details=""):
        self.passed.append((name, details))
        print(f"  ✓ {name}: {details}")

    def test_fail(self, name, details=""):
        self.failed.append((name, details))
        print(f"  ✗ FAIL {name}: {details}")

    def warn(self, name, details=""):
        self.warnings.append((name, details))
        print(f"  ⚠ {name}: {details}")

    def summary(self):
        print("\n" + "="*70)
        print(f"RESULTS: {len(self.passed)} passed, {len(self.failed)} failed, {len(self.warnings)} warnings")
        print("="*70)
        if self.failed:
            print("\nFailed tests:")
            for name, details in self.failed:
                print(f"  ✗ {name}: {details}")
        if self.warnings:
            print("\nWarnings:")
            for name, details in self.warnings:
                print(f"  ⚠ {name}: {details}")


tracker = TestTracker()


async def test_battlecry_draw():
    """Test Novice Engineer battlecry (draw 1 card)."""
    print("\n--- Testing Novice Engineer Battlecry ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    for i in range(10):
        game.add_card_to_library(p1.id, CLASSIC_CARDS[i % len(CLASSIC_CARDS)])

    game.shuffle_library(p1.id)
    await game.start_game()

    # Give P1 enough mana
    p1.mana_crystals = 10
    p1.mana_crystals_available = 10

    # Check hand size before
    hand_before = len(game.get_hand(p1.id))

    # Manually play Novice Engineer to battlefield
    engineer = game.create_object(
        name="Novice Engineer",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=NOVICE_ENGINEER.characteristics,
        card_def=NOVICE_ENGINEER
    )

    # Trigger battlecry
    if NOVICE_ENGINEER.battlecry:
        events = NOVICE_ENGINEER.battlecry(engineer, game.state)
        for event in events:
            game.pipeline.emit(event)

    # Check hand size after
    hand_after = len(game.get_hand(p1.id))

    if hand_after > hand_before:
        tracker.test_pass("Novice Engineer", f"Drew card (hand {hand_before} → {hand_after})")
    else:
        tracker.test_fail("Novice Engineer", f"Didn't draw (hand {hand_before} → {hand_after})")


async def test_deathrattle():
    """Test Loot Hoarder deathrattle (draw on death)."""
    print("\n--- Testing Loot Hoarder Deathrattle ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    for i in range(10):
        game.add_card_to_library(p1.id, CLASSIC_CARDS[i % len(CLASSIC_CARDS)])

    game.shuffle_library(p1.id)
    await game.start_game()

    # Create Loot Hoarder on battlefield
    hoarder = game.create_object(
        name="Loot Hoarder",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=LOOT_HOARDER.characteristics,
        card_def=LOOT_HOARDER
    )

    hand_before = len(game.get_hand(p1.id))

    # Kill it (deal 1 damage to 1 health minion)
    hoarder.state.damage = 1

    # Trigger state-based actions
    if hasattr(game.turn_manager, '_check_state_based_actions'):
        await game.turn_manager._check_state_based_actions()

    # Manually trigger deathrattle
    if LOOT_HOARDER.deathrattle:
        events = LOOT_HOARDER.deathrattle(hoarder, game.state)
        for event in events:
            game.pipeline.emit(event)

    hand_after = len(game.get_hand(p1.id))

    if hand_after > hand_before:
        tracker.test_pass("Loot Hoarder", f"Drew on death (hand {hand_before} → {hand_after})")
    else:
        tracker.test_fail("Loot Hoarder", f"Didn't draw (hand {hand_before} → {hand_after})")


async def test_spell_damage():
    """Test Fireball spell (6 damage)."""
    print("\n--- Testing Fireball Spell ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    await game.start_game()

    life_before = p2.life

    # Cast Fireball at P2's hero
    if FIREBALL.spell_effect:
        fireball_obj = game.create_object(
            name="Fireball",
            owner_id=p1.id,
            zone=ZoneType.HAND,
            characteristics=FIREBALL.characteristics,
            card_def=FIREBALL
        )

        fireball_obj.controller = p1.id
        events = FIREBALL.spell_effect(fireball_obj, game.state, [[p2.hero_id]])

        for event in events:
            game.pipeline.emit(event)

    life_after = p2.life

    if life_before - life_after == 6:
        tracker.test_pass("Fireball", f"Dealt 6 damage ({life_before} → {life_after})")
    else:
        tracker.test_fail("Fireball", f"Wrong damage ({life_before} → {life_after}, expected -6)")


async def test_freeze_effect():
    """Test Frostbolt freeze effect."""
    print("\n--- Testing Frostbolt Freeze ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    await game.start_game()

    # Create target minion
    target = game.create_object(
        name="Yeti",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=CHILLWIND_YETI.characteristics,
        card_def=CHILLWIND_YETI
    )

    frozen_before = target.state.frozen

    # Cast Frostbolt
    if FROSTBOLT.spell_effect:
        frostbolt_obj = game.create_object(
            name="Frostbolt",
            owner_id=p1.id,
            zone=ZoneType.HAND,
            characteristics=FROSTBOLT.characteristics,
            card_def=FROSTBOLT
        )
        frostbolt_obj.controller = p1.id

        events = FROSTBOLT.spell_effect(frostbolt_obj, game.state, [[target.id]])
        for event in events:
            game.pipeline.emit(event)

    frozen_after = target.state.frozen

    if not frozen_before and frozen_after:
        tracker.test_pass("Frostbolt Freeze", "Target frozen successfully")
    else:
        tracker.test_fail("Frostbolt Freeze", f"frozen: {frozen_before} → {frozen_after}")


async def test_aoe_spell():
    """Test Consecration (AOE damage to all enemies)."""
    print("\n--- Testing Consecration AOE ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Paladin"], HERO_POWERS["Paladin"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    await game.start_game()

    # Create 3 enemy minions
    minions = []
    for i in range(3):
        minion = game.create_object(
            name=f"Yeti{i}",
            owner_id=p2.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=CHILLWIND_YETI.characteristics,
            card_def=CHILLWIND_YETI
        )
        minions.append(minion)

    hero_life_before = p2.life

    # Cast Consecration
    if CONSECRATION.spell_effect:
        consec_obj = game.create_object(
            name="Consecration",
            owner_id=p1.id,
            zone=ZoneType.HAND,
            characteristics=CONSECRATION.characteristics,
            card_def=CONSECRATION
        )
        consec_obj.controller = p1.id

        events = CONSECRATION.spell_effect(consec_obj, game.state, [])
        for event in events:
            game.pipeline.emit(event)

    # Check minion damage
    damaged_count = sum(1 for m in minions if m.state.damage >= 2)
    hero_damage = hero_life_before - p2.life

    if damaged_count == 3 and hero_damage == 2:
        tracker.test_pass("Consecration", f"Hit {damaged_count} minions and hero for 2")
    else:
        tracker.test_fail("Consecration", f"Hit {damaged_count}/3 minions, hero took {hero_damage}")


async def test_charge_attack():
    """Test Charge minions can attack immediately."""
    print("\n--- Testing Charge Mechanic ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    await game.start_game()

    # Create Wolfrider (Charge)
    wolfrider = game.create_object(
        name="Wolfrider",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=WOLFRIDER.characteristics,
        card_def=WOLFRIDER
    )

    # Check if it has charge
    has_charge = 'charge' in wolfrider.characteristics.keywords

    life_before = p2.life

    # Set active player for combat
    game.state.active_player = p1.id

    # Try to attack (AI adapter would handle this)
    if has_charge and hasattr(game, 'combat_manager'):
        await game.combat_manager.declare_attack(wolfrider.id, p2.hero_id)

    life_after = p2.life

    if has_charge:
        if life_after < life_before:
            tracker.test_pass("Charge", f"Attacked immediately (damage: {life_before - life_after})")
        else:
            tracker.test_fail("Charge", "Has charge but didn't deal damage")
    else:
        tracker.test_fail("Charge", "Wolfrider missing charge keyword")


async def test_divine_shield_interaction():
    """Test Divine Shield blocking damage."""
    print("\n--- Testing Divine Shield ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Paladin"], HERO_POWERS["Paladin"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    await game.start_game()

    # Create Silvermoon Guardian (Divine Shield)
    guardian = game.create_object(
        name="Silvermoon Guardian",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SILVERMOON_GUARDIAN.characteristics,
        card_def=SILVERMOON_GUARDIAN
    )

    # Set divine shield
    guardian.state.divine_shield = True

    shield_before = guardian.state.divine_shield
    damage_before = guardian.state.damage

    # Deal 1 damage
    damage_event = Event(
        type=EventType.DAMAGE,
        payload={'target': guardian.id, 'amount': 1, 'source': None}
    )
    game.pipeline.emit(damage_event)

    shield_after = guardian.state.divine_shield
    damage_after = guardian.state.damage

    if shield_before and not shield_after and damage_after == 0:
        tracker.test_pass("Divine Shield", "Shield broke but no damage taken")
    else:
        tracker.test_fail("Divine Shield", f"shield: {shield_before}→{shield_after}, damage: {damage_before}→{damage_after}")


async def test_weapon_equip_and_attack():
    """Test equipping weapon and attacking with it."""
    print("\n--- Testing Weapon ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])

    await game.start_game()

    # Equip Fiery War Axe (3/2)
    p1.weapon_attack = 3
    p1.weapon_durability = 2

    life_before = p2.life

    # Set active player for combat
    game.state.active_player = p1.id

    # Hero attacks with weapon
    if p1.hero_id and hasattr(game, 'combat_manager'):
        await game.combat_manager.declare_attack(p1.hero_id, p2.hero_id)

    life_after = p2.life
    durability_after = p1.weapon_durability

    damage_dealt = life_before - life_after

    if damage_dealt == 3 and durability_after == 1:
        tracker.test_pass("Weapon Attack", f"Dealt {damage_dealt} damage, durability 2→{durability_after}")
    else:
        tracker.test_fail("Weapon Attack", f"Damage: {damage_dealt}, Durability: {durability_after}")


async def test_full_ai_game_with_real_cards():
    """Test full AI game with real Hearthstone cards."""
    print("\n--- Testing Full AI Game with Real Cards ---")

    game = Game(mode="hearthstone")
    p1 = game.add_player("Mage Bot")
    p2 = game.add_player("Warrior Bot")

    game.set_ai_player(p1.id)
    game.set_ai_player(p2.id)

    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    # Build decks with real cards
    mage_deck = [
        NOVICE_ENGINEER, LOOT_HOARDER, FROSTBOLT,
        ARCANE_INTELLECT, WOLFRIDER, CHILLWIND_YETI,
        SEN_JIN_SHIELDMASTA, FIREBALL, BOULDERFIST_OGRE,
        RECKLESS_ROCKETEER
    ]

    warrior_deck = [
        BLOODFEN_RAPTOR, ACIDIC_SWAMP_OOZE, FIERY_WAR_AXE,
        IRONFORGE_RIFLEMAN, SHATTERED_SUN_CLERIC, SILVERMOON_GUARDIAN,
        CONSECRATION, CHILLWIND_YETI, BOULDERFIST_OGRE,
        ARCANITE_REAPER
    ]

    for card in mage_deck:
        game.add_card_to_library(p1.id, card)
    for card in warrior_deck:
        game.add_card_to_library(p2.id, card)

    game.shuffle_library(p1.id)
    game.shuffle_library(p2.id)

    # Setup AI
    ai_adapter = HearthstoneAIAdapter(difficulty="easy")
    game.set_hearthstone_ai_handler(ai_adapter)

    await game.start_game()

    turns_played = 0
    max_turns = 20

    try:
        for turn in range(max_turns):
            await game.turn_manager.run_turn()
            turns_played = turn + 1

            if turn % 3 == 0:  # Print every 3 turns
                print(f"  T{turn+1}: P1={p1.life}HP/{p1.mana_crystals}m, P2={p2.life}HP/{p2.mana_crystals}m")

            if game.is_game_over():
                winner = game.get_winner()
                print(f"  Game ended at turn {turns_played}")
                print(f"  Winner: {winner}")
                print(f"  P1: {p1.life}HP, P2: {p2.life}HP")

                if p1.life < -100 or p2.life < -100:
                    tracker.test_fail("AI Game", "Extreme negative HP bug")
                elif p1.has_lost or p2.has_lost:
                    tracker.test_pass("AI Game", f"Completed in {turns_played} turns")
                else:
                    tracker.warn("AI Game", "Ended but no winner marked")
                break
        else:
            tracker.test_pass("AI Game", f"{turns_played} turns without crash")

    except Exception as e:
        tracker.test_fail("AI Game", f"Exception: {e}")
        import traceback
        traceback.print_exc()


async def run_all_tests():
    print("="*70)
    print("HEARTHSTONE REAL CARDS TEST SUITE")
    print("="*70)

    tests = [
        test_battlecry_draw,
        test_deathrattle,
        test_spell_damage,
        test_freeze_effect,
        test_aoe_spell,
        test_charge_attack,
        test_divine_shield_interaction,
        test_weapon_equip_and_attack,
        test_full_ai_game_with_real_cards,
    ]

    for test in tests:
        try:
            await test()
        except Exception as e:
            tracker.test_fail(test.__name__, f"Unhandled exception: {e}")
            import traceback
            traceback.print_exc()

    tracker.summary()


if __name__ == "__main__":
    asyncio.run(run_all_tests())
