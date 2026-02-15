"""
Hearthstone Unhappy Path Tests - Batch 101

Card definition validation, deck-building constraints, and game setup edge cases.

Tests cover:
- Card definition validation (names, mana costs, stats)
- Card type checks (creature, spell, weapon)
- Hero and hero power validation
- Class card organization
- Card characteristics validation
- Setup edge cases
- Card effect function validation
- Edge cases for game initialization
"""

from src.engine.game import Game
from src.engine.types import CardType, ZoneType

# Import card sets
from src.cards.hearthstone.basic import BASIC_CARDS
from src.cards.hearthstone.classic import CLASSIC_CARDS
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.tokens import ALL_TOKENS

# Import specific cards for validation
from src.cards.hearthstone.basic import (
    WISP, CHILLWIND_YETI, BOULDERFIST_OGRE, BLOODFEN_RAPTOR, RIVER_CROCOLISK
)

# Import class card lists
from src.cards.hearthstone.mage import MAGE_CARDS
from src.cards.hearthstone.warlock import WARLOCK_CARDS
from src.cards.hearthstone.priest import PRIEST_CARDS
from src.cards.hearthstone.rogue import ROGUE_CARDS
from src.cards.hearthstone.paladin import PALADIN_CARDS
from src.cards.hearthstone.warrior import WARRIOR_CARDS
from src.cards.hearthstone.hunter import HUNTER_CARDS
from src.cards.hearthstone.shaman import SHAMAN_CARDS
from src.cards.hearthstone.druid import DRUID_CARDS


# ============================================================
# Test 1-8: Card Definition Validation
# ============================================================

class TestCardDefinitionValidation:
    """Tests for card definition validation."""

    def test_all_basic_cards_have_valid_names(self):
        """All basic cards should have valid names (non-empty strings)."""
        for card in BASIC_CARDS:
            assert hasattr(card, 'name'), f"Card {card} missing name attribute"
            assert card.name, f"Card has empty name"
            assert isinstance(card.name, str), f"Card name is not a string: {card.name}"
            assert len(card.name) > 0, f"Card name is empty string"

    def test_all_basic_cards_have_valid_mana_costs(self):
        """All basic cards should have valid mana costs."""
        for card in BASIC_CARDS:
            assert hasattr(card, 'mana_cost'), f"Card {card.name} missing mana_cost"
            assert card.mana_cost is not None, f"Card {card.name} has None mana_cost"
            assert isinstance(card.mana_cost, str), f"Card {card.name} mana_cost not a string"
            # Mana cost format: {X} where X is 0-10
            assert card.mana_cost.startswith('{'), f"Card {card.name} mana_cost doesn't start with {{"
            assert card.mana_cost.endswith('}'), f"Card {card.name} mana_cost doesn't end with }}"

    def test_all_classic_cards_have_valid_names(self):
        """All classic cards should have valid names (non-empty strings)."""
        for card in CLASSIC_CARDS:
            assert hasattr(card, 'name'), f"Card {card} missing name attribute"
            assert card.name, f"Card has empty name"
            assert isinstance(card.name, str), f"Card name is not a string: {card.name}"
            assert len(card.name) > 0, f"Card name is empty string"

    def test_all_classic_cards_have_valid_mana_costs(self):
        """All classic cards should have valid mana costs."""
        for card in CLASSIC_CARDS:
            assert hasattr(card, 'mana_cost'), f"Card {card.name} missing mana_cost"
            assert card.mana_cost is not None, f"Card {card.name} has None mana_cost"
            assert isinstance(card.mana_cost, str), f"Card {card.name} mana_cost not a string"

    def test_creature_cards_have_power_and_health(self):
        """Creature cards (minions) have power and health defined."""
        for card in BASIC_CARDS + CLASSIC_CARDS:
            if hasattr(card, 'characteristics') and CardType.MINION in card.characteristics.types:
                assert hasattr(card.characteristics, 'power'), f"Minion {card.name} missing power"
                assert hasattr(card.characteristics, 'toughness'), f"Minion {card.name} missing health"
                assert card.characteristics.power is not None, f"Minion {card.name} has None power"
                assert card.characteristics.toughness is not None, f"Minion {card.name} has None health"

    def test_spell_cards_have_spell_effect_function(self):
        """Spell cards have spell_effect function."""
        for card in BASIC_CARDS + CLASSIC_CARDS:
            if hasattr(card, 'characteristics') and CardType.SPELL in card.characteristics.types:
                # Spell cards should have a spell_effect callable
                assert hasattr(card, 'spell_effect'), f"Spell {card.name} missing spell_effect"
                assert callable(card.spell_effect), f"Spell {card.name} spell_effect is not callable"

    def test_weapon_cards_have_attack_and_durability(self):
        """Weapon cards have attack and durability defined."""
        for card in BASIC_CARDS + CLASSIC_CARDS:
            if hasattr(card, 'characteristics') and CardType.WEAPON in card.characteristics.types:
                # Weapons use power for attack and toughness for durability
                assert hasattr(card.characteristics, 'power'), f"Weapon {card.name} missing attack (power)"
                assert hasattr(card.characteristics, 'toughness'), f"Weapon {card.name} missing durability (toughness)"
                assert card.characteristics.power is not None, f"Weapon {card.name} has None attack"
                assert card.characteristics.toughness is not None, f"Weapon {card.name} has None durability"

    def test_no_duplicate_card_names_within_basic_set(self):
        """No duplicate card names within basic set."""
        names = [card.name for card in BASIC_CARDS]
        duplicates = [name for name in names if names.count(name) > 1]
        assert len(duplicates) == 0, f"Duplicate card names in basic set: {set(duplicates)}"


# ============================================================
# Test 9-12: Card Type Checks
# ============================================================

class TestCardTypeChecks:
    """Tests for card type validation."""

    def test_creature_cards_are_marked_as_minion(self):
        """Creature cards are marked as CardType.MINION."""
        # Check a few known minions
        assert CardType.MINION in WISP.characteristics.types
        assert CardType.MINION in CHILLWIND_YETI.characteristics.types
        assert CardType.MINION in BLOODFEN_RAPTOR.characteristics.types

    def test_spell_cards_are_marked_as_spell(self):
        """Spell cards are marked as CardType.SPELL."""
        from src.cards.hearthstone.classic import FIREBALL, FROSTBOLT
        assert CardType.SPELL in FIREBALL.characteristics.types
        assert CardType.SPELL in FROSTBOLT.characteristics.types

    def test_weapon_cards_are_marked_as_weapon(self):
        """Weapon cards are marked as CardType.WEAPON."""
        from src.cards.hearthstone.basic import FIERY_WAR_AXE, ARCANITE_REAPER
        assert CardType.WEAPON in FIERY_WAR_AXE.characteristics.types
        assert CardType.WEAPON in ARCANITE_REAPER.characteristics.types

    def test_secret_cards_have_secret_type(self):
        """Secret cards are marked with SECRET type."""
        from src.cards.hearthstone.mage import COUNTERSPELL, MIRROR_ENTITY
        # Secrets are CardType.SECRET
        assert CardType.SECRET in COUNTERSPELL.characteristics.types
        assert CardType.SECRET in MIRROR_ENTITY.characteristics.types


# ============================================================
# Test 13-16: Hero and Hero Power Validation
# ============================================================

class TestHeroValidation:
    """Tests for hero and hero power validation."""

    def test_all_9_classes_have_a_hero_defined(self):
        """All 9 classes have a hero defined."""
        classes = ["Mage", "Warlock", "Priest", "Rogue", "Paladin", "Warrior", "Hunter", "Shaman", "Druid"]
        for cls in classes:
            assert cls in HEROES, f"Class {cls} missing from HEROES"
            assert HEROES[cls] is not None, f"Class {cls} has None hero"

    def test_all_9_classes_have_a_hero_power_defined(self):
        """All 9 classes have a hero power defined."""
        classes = ["Mage", "Warlock", "Priest", "Rogue", "Paladin", "Warrior", "Hunter", "Shaman", "Druid"]
        for cls in classes:
            assert cls in HERO_POWERS, f"Class {cls} missing from HERO_POWERS"
            assert HERO_POWERS[cls] is not None, f"Class {cls} has None hero power"

    def test_heroes_have_30_health(self):
        """Heroes have 30 starting health."""
        for cls, hero in HEROES.items():
            assert hasattr(hero, 'characteristics'), f"Hero {hero.name} missing characteristics"
            # Heroes use toughness for starting health
            assert hasattr(hero.characteristics, 'toughness'), f"Hero {hero.name} missing toughness (health)"
            assert hero.characteristics.toughness == 30, f"Hero {hero.name} has {hero.characteristics.toughness} HP, expected 30"

    def test_hero_powers_cost_2_mana(self):
        """Hero powers cost 2 mana."""
        for cls, hero_power in HERO_POWERS.items():
            # Hero powers use mana_cost like other cards
            assert hasattr(hero_power, 'mana_cost'), f"Hero power {hero_power.name} missing mana_cost"
            assert hero_power.mana_cost == "{2}", f"Hero power {hero_power.name} costs {hero_power.mana_cost}, expected {{2}}"


# ============================================================
# Test 17-25: Class Card Organization
# ============================================================

class TestClassCardOrganization:
    """Tests for class card organization."""

    def test_mage_cards_exist_and_are_non_empty(self):
        """Mage cards exist and are non-empty."""
        assert MAGE_CARDS is not None
        assert len(MAGE_CARDS) > 0, "Mage cards list is empty"
        assert isinstance(MAGE_CARDS, list), "Mage cards is not a list"

    def test_warlock_cards_exist_and_are_non_empty(self):
        """Warlock cards exist and are non-empty."""
        assert WARLOCK_CARDS is not None
        assert len(WARLOCK_CARDS) > 0, "Warlock cards list is empty"
        assert isinstance(WARLOCK_CARDS, list), "Warlock cards is not a list"

    def test_priest_cards_exist_and_are_non_empty(self):
        """Priest cards exist and are non-empty."""
        assert PRIEST_CARDS is not None
        assert len(PRIEST_CARDS) > 0, "Priest cards list is empty"
        assert isinstance(PRIEST_CARDS, list), "Priest cards is not a list"

    def test_rogue_cards_exist_and_are_non_empty(self):
        """Rogue cards exist and are non-empty."""
        assert ROGUE_CARDS is not None
        assert len(ROGUE_CARDS) > 0, "Rogue cards list is empty"
        assert isinstance(ROGUE_CARDS, list), "Rogue cards is not a list"

    def test_paladin_cards_exist_and_are_non_empty(self):
        """Paladin cards exist and are non-empty."""
        assert PALADIN_CARDS is not None
        assert len(PALADIN_CARDS) > 0, "Paladin cards list is empty"
        assert isinstance(PALADIN_CARDS, list), "Paladin cards is not a list"

    def test_warrior_cards_exist_and_are_non_empty(self):
        """Warrior cards exist and are non-empty."""
        assert WARRIOR_CARDS is not None
        assert len(WARRIOR_CARDS) > 0, "Warrior cards list is empty"
        assert isinstance(WARRIOR_CARDS, list), "Warrior cards is not a list"

    def test_hunter_cards_exist_and_are_non_empty(self):
        """Hunter cards exist and are non-empty."""
        assert HUNTER_CARDS is not None
        assert len(HUNTER_CARDS) > 0, "Hunter cards list is empty"
        assert isinstance(HUNTER_CARDS, list), "Hunter cards is not a list"

    def test_shaman_cards_exist_and_are_non_empty(self):
        """Shaman cards exist and are non-empty."""
        assert SHAMAN_CARDS is not None
        assert len(SHAMAN_CARDS) > 0, "Shaman cards list is empty"
        assert isinstance(SHAMAN_CARDS, list), "Shaman cards is not a list"

    def test_druid_cards_exist_and_are_non_empty(self):
        """Druid cards exist and are non-empty."""
        assert DRUID_CARDS is not None
        assert len(DRUID_CARDS) > 0, "Druid cards list is empty"
        assert isinstance(DRUID_CARDS, list), "Druid cards is not a list"


# ============================================================
# Test 26-30: Card Characteristics
# ============================================================

class TestCardCharacteristics:
    """Tests for specific card characteristics."""

    def test_wisp_has_0_mana_cost(self):
        """Wisp has 0 mana cost."""
        assert WISP.mana_cost == "{0}", f"Wisp has mana cost {WISP.mana_cost}, expected {{0}}"

    def test_chillwind_yeti_is_4_5_for_4_mana(self):
        """Chillwind Yeti is 4/5 for 4 mana."""
        assert CHILLWIND_YETI.characteristics.power == 4, f"Chillwind Yeti has {CHILLWIND_YETI.characteristics.power} attack, expected 4"
        assert CHILLWIND_YETI.characteristics.toughness == 5, f"Chillwind Yeti has {CHILLWIND_YETI.characteristics.toughness} health, expected 5"
        assert CHILLWIND_YETI.mana_cost == "{4}", f"Chillwind Yeti costs {CHILLWIND_YETI.mana_cost}, expected {{4}}"

    def test_boulderfist_ogre_is_6_7_for_6_mana(self):
        """Boulderfist Ogre is 6/7 for 6 mana."""
        assert BOULDERFIST_OGRE.characteristics.power == 6, f"Boulderfist Ogre has {BOULDERFIST_OGRE.characteristics.power} attack, expected 6"
        assert BOULDERFIST_OGRE.characteristics.toughness == 7, f"Boulderfist Ogre has {BOULDERFIST_OGRE.characteristics.toughness} health, expected 7"
        assert BOULDERFIST_OGRE.mana_cost == "{6}", f"Boulderfist Ogre costs {BOULDERFIST_OGRE.mana_cost}, expected {{6}}"

    def test_bloodfen_raptor_is_3_2_for_2_mana(self):
        """Bloodfen Raptor is 3/2 for 2 mana."""
        assert BLOODFEN_RAPTOR.characteristics.power == 3, f"Bloodfen Raptor has {BLOODFEN_RAPTOR.characteristics.power} attack, expected 3"
        assert BLOODFEN_RAPTOR.characteristics.toughness == 2, f"Bloodfen Raptor has {BLOODFEN_RAPTOR.characteristics.toughness} health, expected 2"
        assert BLOODFEN_RAPTOR.mana_cost == "{2}", f"Bloodfen Raptor costs {BLOODFEN_RAPTOR.mana_cost}, expected {{2}}"

    def test_river_crocolisk_is_2_3_for_2_mana(self):
        """River Crocolisk is 2/3 for 2 mana."""
        assert RIVER_CROCOLISK.characteristics.power == 2, f"River Crocolisk has {RIVER_CROCOLISK.characteristics.power} attack, expected 2"
        assert RIVER_CROCOLISK.characteristics.toughness == 3, f"River_CROCOLISK has {RIVER_CROCOLISK.characteristics.toughness} health, expected 3"
        assert RIVER_CROCOLISK.mana_cost == "{2}", f"River Crocolisk costs {RIVER_CROCOLISK.mana_cost}, expected {{2}}"


# ============================================================
# Test 31-35: Setup Edge Cases
# ============================================================

class TestSetupEdgeCases:
    """Tests for game setup edge cases."""

    def test_creating_game_with_mode_hearthstone_works(self):
        """Creating game with mode='hearthstone' works."""
        game = Game(mode='hearthstone')
        assert game is not None
        assert game.state is not None
        assert hasattr(game, 'mana_system')

    def test_adding_two_players_works(self):
        """Adding two players works."""
        game = Game(mode='hearthstone')
        p1 = game.add_player("Player1", life=30)
        p2 = game.add_player("Player2", life=30)
        assert p1 is not None
        assert p2 is not None
        assert p1.id in game.state.players
        assert p2.id in game.state.players

    def test_setting_up_heroes_and_hero_powers_works(self):
        """Setting up heroes and hero powers works."""
        game = Game(mode='hearthstone')
        p1 = game.add_player("Player1", life=30)
        p2 = game.add_player("Player2", life=30)
        game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
        game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])
        assert p1.hero_id is not None
        assert p2.hero_id is not None
        assert p1.hero_power_id is not None
        assert p2.hero_power_id is not None

    def test_mana_system_initializes_correctly(self):
        """Mana system initializes correctly."""
        game = Game(mode='hearthstone')
        p1 = game.add_player("Player1", life=30)
        p2 = game.add_player("Player2", life=30)
        game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
        game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

        # Initial mana should be 0
        assert p1.mana_crystals == 0
        assert p2.mana_crystals == 0

        # After first turn start, should have 1 mana
        game.mana_system.on_turn_start(p1.id)
        assert p1.mana_crystals == 1

    def test_players_start_with_0_armor(self):
        """Players start with 0 armor."""
        game = Game(mode='hearthstone')
        p1 = game.add_player("Player1", life=30)
        p2 = game.add_player("Player2", life=30)
        game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
        game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])
        assert p1.armor == 0
        assert p2.armor == 0


# ============================================================
# Test 36-40: Card Effect Function Validation
# ============================================================

class TestCardEffectFunctionValidation:
    """Tests for card effect function validation."""

    def test_cards_with_battlecry_have_setup_or_battlecry_fn(self):
        """Cards with battlecry have setup_interceptors or battlecry function."""
        from src.cards.hearthstone.basic import ELVEN_ARCHER, SHATTERED_SUN_CLERIC

        # Check that battlecry cards have battlecry function
        assert hasattr(ELVEN_ARCHER, 'battlecry'), f"Elven Archer missing battlecry"
        assert callable(ELVEN_ARCHER.battlecry), f"Elven Archer battlecry not callable"

        assert hasattr(SHATTERED_SUN_CLERIC, 'battlecry'), f"Shattered Sun Cleric missing battlecry"
        assert callable(SHATTERED_SUN_CLERIC.battlecry), f"Shattered Sun Cleric battlecry not callable"

    def test_cards_with_deathrattle_have_deathrattle_fn(self):
        """Cards with deathrattle have deathrattle function."""
        from src.cards.hearthstone.basic import LEPER_GNOME, HARVEST_GOLEM

        assert hasattr(LEPER_GNOME, 'deathrattle'), f"Leper Gnome missing deathrattle"
        assert callable(LEPER_GNOME.deathrattle), f"Leper Gnome deathrattle not callable"

        assert hasattr(HARVEST_GOLEM, 'deathrattle'), f"Harvest Golem missing deathrattle"
        assert callable(HARVEST_GOLEM.deathrattle), f"Harvest Golem deathrattle not callable"

    def test_cards_with_ongoing_effects_have_setup_interceptors(self):
        """Cards with ongoing effects have setup_interceptors."""
        from src.cards.hearthstone.basic import STORMWIND_CHAMPION, RAID_LEADER

        assert hasattr(STORMWIND_CHAMPION, 'setup_interceptors'), f"Stormwind Champion missing setup_interceptors"
        assert callable(STORMWIND_CHAMPION.setup_interceptors), f"Stormwind Champion setup_interceptors not callable"

        assert hasattr(RAID_LEADER, 'setup_interceptors'), f"Raid Leader missing setup_interceptors"
        assert callable(RAID_LEADER.setup_interceptors), f"Raid Leader setup_interceptors not callable"

    def test_spell_cards_have_spell_effect_callable(self):
        """Spell cards have spell_effect callable."""
        from src.cards.hearthstone.classic import FIREBALL, FROSTBOLT

        assert hasattr(FIREBALL, 'spell_effect'), f"Fireball missing spell_effect"
        assert callable(FIREBALL.spell_effect), f"Fireball spell_effect not callable"

        assert hasattr(FROSTBOLT, 'spell_effect'), f"Frostbolt missing spell_effect"
        assert callable(FROSTBOLT.spell_effect), f"Frostbolt spell_effect not callable"

    def test_token_cards_exist_and_have_valid_stats(self):
        """Token cards exist and have valid stats."""
        assert ALL_TOKENS is not None
        assert len(ALL_TOKENS) > 0, "Token list is empty"

        # Check a few known tokens
        from src.cards.hearthstone.tokens import SHEEP, SILVER_HAND_RECRUIT

        assert SHEEP.characteristics.power == 1
        assert SHEEP.characteristics.toughness == 1

        assert SILVER_HAND_RECRUIT.characteristics.power == 1
        assert SILVER_HAND_RECRUIT.characteristics.toughness == 1


# ============================================================
# Test 41-45: Edge Cases
# ============================================================

class TestEdgeCases:
    """Tests for edge cases in game setup and card creation."""

    def test_creating_multiple_games_doesnt_interfere(self):
        """Creating multiple games doesn't interfere."""
        game1 = Game(mode='hearthstone')
        p1_g1 = game1.add_player("Player1", life=30)

        game2 = Game(mode='hearthstone')
        p1_g2 = game2.add_player("Player1", life=30)

        # Different game instances
        assert game1 is not game2
        # Different player instances
        assert p1_g1.id != p1_g2.id
        # Different state objects
        assert game1.state is not game2.state

    def test_same_card_can_be_created_multiple_times(self):
        """Same card can be created multiple times (not singleton)."""
        game = Game(mode='hearthstone')
        p1 = game.add_player("Player1", life=30)
        game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])

        # Create two Wisps
        wisp1 = game.create_object(
            name=WISP.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=WISP.characteristics, card_def=WISP
        )
        wisp2 = game.create_object(
            name=WISP.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=WISP.characteristics, card_def=WISP
        )

        # Should be different objects
        assert wisp1.id != wisp2.id
        # But same name
        assert wisp1.name == wisp2.name == "Wisp"

    def test_card_ids_are_unique_per_instance(self):
        """Card IDs are unique per instance."""
        game = Game(mode='hearthstone')
        p1 = game.add_player("Player1", life=30)
        game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])

        # Create 10 cards
        card_ids = []
        for _ in range(10):
            card = game.create_object(
                name=WISP.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
                characteristics=WISP.characteristics, card_def=WISP
            )
            card_ids.append(card.id)

        # All IDs should be unique
        assert len(card_ids) == len(set(card_ids)), "Duplicate card IDs found"

    def test_player_ids_are_unique(self):
        """Player IDs are unique."""
        game = Game(mode='hearthstone')
        p1 = game.add_player("Player1", life=30)
        p2 = game.add_player("Player2", life=30)

        assert p1.id != p2.id, "Player IDs should be unique"

    def test_zone_system_initializes_with_required_zones(self):
        """Zone system initializes with required zones (battlefield, hand, library, graveyard)."""
        game = Game(mode='hearthstone')
        p1 = game.add_player("Player1", life=30)
        p2 = game.add_player("Player2", life=30)
        game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
        game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])

        # Check that zones exist
        assert 'battlefield' in game.state.zones, "Battlefield zone missing"
        assert f'hand_{p1.id}' in game.state.zones, "Player 1 hand zone missing"
        assert f'hand_{p2.id}' in game.state.zones, "Player 2 hand zone missing"
        assert f'library_{p1.id}' in game.state.zones, "Player 1 library zone missing"
        assert f'library_{p2.id}' in game.state.zones, "Player 2 library zone missing"
        assert f'graveyard_{p1.id}' in game.state.zones, "Player 1 graveyard zone missing"
        assert f'graveyard_{p2.id}' in game.state.zones, "Player 2 graveyard zone missing"


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
