"""
Hearthstone Deck Definitions

30-card decks for each class following Hearthstone deck-building rules:
- Exactly 30 cards
- Max 2 copies of any card (1 for Legendaries)
- Class cards + Neutral cards allowed
"""

from src.cards.hearthstone.basic import *
from src.cards.hearthstone.classic import *


# =============================================================================
# Mage Deck - Tempo/Spell Focus
# =============================================================================
MAGE_DECK = [
    # 1-drops (2 cards)
    ARCANE_MISSILES, ARCANE_MISSILES,

    # 2-drops (6 cards)
    KNIFE_JUGGLER, KNIFE_JUGGLER,
    FROSTBOLT, FROSTBOLT,
    BLOODFEN_RAPTOR, BLOODFEN_RAPTOR,

    # 3-drops (6 cards)
    SHATTERED_SUN_CLERIC, SHATTERED_SUN_CLERIC,
    IRONFORGE_RIFLEMAN, IRONFORGE_RIFLEMAN,
    HARVEST_GOLEM, HARVEST_GOLEM,

    # 4-drops (8 cards)
    WATER_ELEMENTAL, WATER_ELEMENTAL,
    FIREBALL, FIREBALL,
    SEN_JIN_SHIELDMASTA, SEN_JIN_SHIELDMASTA,
    GNOMISH_INVENTOR, GNOMISH_INVENTOR,

    # 5-drops (2 cards)
    NIGHTBLADE, NIGHTBLADE,

    # 6-drops (2 cards)
    BOULDERFIST_OGRE, BOULDERFIST_OGRE,

    # 7-drops (4 cards)
    FLAMESTRIKE, FLAMESTRIKE,
    STORMWIND_CHAMPION, STORMWIND_CHAMPION,
]

# =============================================================================
# Warrior Deck - Weapon/Control Focus
# =============================================================================
WARRIOR_DECK = [
    # 1-drops (2 cards)
    STONETUSK_BOAR, STONETUSK_BOAR,

    # 2-drops (6 cards)
    ACIDIC_SWAMP_OOZE, ACIDIC_SWAMP_OOZE,
    BLOODFEN_RAPTOR, BLOODFEN_RAPTOR,
    LOOT_HOARDER, LOOT_HOARDER,

    # 3-drops (8 cards)
    RAID_LEADER, RAID_LEADER,
    SHATTERED_SUN_CLERIC, SHATTERED_SUN_CLERIC,
    WOLFRIDER, WOLFRIDER,
    HARVEST_GOLEM, HARVEST_GOLEM,

    # 4-drops (6 cards)
    CHILLWIND_YETI, CHILLWIND_YETI,
    GNOMISH_INVENTOR, GNOMISH_INVENTOR,
    SEN_JIN_SHIELDMASTA, SEN_JIN_SHIELDMASTA,

    # 5-drops (2 cards)
    STORMPIKE_COMMANDO, STORMPIKE_COMMANDO,

    # 6-drops (3 cards)
    BOULDERFIST_OGRE, BOULDERFIST_OGRE,
    ARGENT_COMMANDER,

    # Weapons (3 cards)
    FIERY_WAR_AXE, FIERY_WAR_AXE,
    ARCANITE_REAPER,
]

# =============================================================================
# Hunter Deck - Beast/Aggro Focus
# =============================================================================
HUNTER_DECK = [
    # 1-drops (6 cards)
    WISP, WISP,
    STONETUSK_BOAR, STONETUSK_BOAR,
    LEPER_GNOME, LEPER_GNOME,

    # 2-drops (8 cards)
    KNIFE_JUGGLER, KNIFE_JUGGLER,
    BLOODFEN_RAPTOR, BLOODFEN_RAPTOR,
    RIVER_CROCOLISK, RIVER_CROCOLISK,
    LOOT_HOARDER, LOOT_HOARDER,

    # 3-drops (8 cards)
    WOLFRIDER, WOLFRIDER,
    RAID_LEADER, RAID_LEADER,
    HARVEST_GOLEM, HARVEST_GOLEM,
    IRONFORGE_RIFLEMAN, IRONFORGE_RIFLEMAN,

    # 4-drops (4 cards)
    CHILLWIND_YETI, CHILLWIND_YETI,
    SEN_JIN_SHIELDMASTA, SEN_JIN_SHIELDMASTA,

    # 5-drops (2 cards)
    NIGHTBLADE, NIGHTBLADE,

    # 6-drops (2 cards)
    RECKLESS_ROCKETEER, RECKLESS_ROCKETEER,
]

# =============================================================================
# Paladin Deck - Token/Buff Focus
# =============================================================================
PALADIN_DECK = [
    # 1-drops (4 cards)
    ELVEN_ARCHER, ELVEN_ARCHER,
    LIGHT_S_JUSTICE, LIGHT_S_JUSTICE,

    # 2-drops (6 cards)
    BLOODFEN_RAPTOR, BLOODFEN_RAPTOR,
    RIVER_CROCOLISK, RIVER_CROCOLISK,
    ACIDIC_SWAMP_OOZE, ACIDIC_SWAMP_OOZE,

    # 3-drops (8 cards)
    SHATTERED_SUN_CLERIC, SHATTERED_SUN_CLERIC,
    RAID_LEADER, RAID_LEADER,
    HARVEST_GOLEM, HARVEST_GOLEM,
    IRONFORGE_RIFLEMAN, IRONFORGE_RIFLEMAN,

    # 4-drops (6 cards)
    CHILLWIND_YETI, CHILLWIND_YETI,
    SEN_JIN_SHIELDMASTA, SEN_JIN_SHIELDMASTA,
    SILVERMOON_GUARDIAN, SILVERMOON_GUARDIAN,

    # 5-drops (2 cards)
    STORMPIKE_COMMANDO, STORMPIKE_COMMANDO,

    # 6-drops (2 cards)
    LORD_OF_THE_ARENA, LORD_OF_THE_ARENA,

    # 7-drops (2 cards)
    STORMWIND_CHAMPION, STORMWIND_CHAMPION,
]

# =============================================================================
# Priest Deck - Control/Healing Focus
# =============================================================================
PRIEST_DECK = [
    # 1-drops (2 cards)
    ELVEN_ARCHER, ELVEN_ARCHER,

    # 2-drops (6 cards)
    BLOODFEN_RAPTOR, BLOODFEN_RAPTOR,
    RIVER_CROCOLISK, RIVER_CROCOLISK,
    NOVICE_ENGINEER, NOVICE_ENGINEER,

    # 3-drops (6 cards)
    SHATTERED_SUN_CLERIC, SHATTERED_SUN_CLERIC,
    HARVEST_GOLEM, HARVEST_GOLEM,
    IRONFORGE_RIFLEMAN, IRONFORGE_RIFLEMAN,

    # 4-drops (8 cards)
    CHILLWIND_YETI, CHILLWIND_YETI,
    SEN_JIN_SHIELDMASTA, SEN_JIN_SHIELDMASTA,
    GNOMISH_INVENTOR, GNOMISH_INVENTOR,
    SILVERMOON_GUARDIAN, SILVERMOON_GUARDIAN,

    # 5-drops (2 cards)
    STORMPIKE_COMMANDO, STORMPIKE_COMMANDO,

    # 6-drops (4 cards)
    BOULDERFIST_OGRE, BOULDERFIST_OGRE,
    LORD_OF_THE_ARENA, LORD_OF_THE_ARENA,

    # 7-drops (2 cards)
    STORMWIND_CHAMPION, STORMWIND_CHAMPION,
]

# =============================================================================
# Rogue Deck - Tempo/Weapon Focus
# =============================================================================
ROGUE_DECK = [
    # 0-drops (2 cards)
    BACKSTAB, BACKSTAB,

    # 1-drops (4 cards)
    LEPER_GNOME, LEPER_GNOME,
    ELVEN_ARCHER, ELVEN_ARCHER,

    # 2-drops (8 cards)
    BLOODFEN_RAPTOR, BLOODFEN_RAPTOR,
    ACIDIC_SWAMP_OOZE, ACIDIC_SWAMP_OOZE,
    LOOT_HOARDER, LOOT_HOARDER,
    NOVICE_ENGINEER, NOVICE_ENGINEER,

    # 3-drops (8 cards)
    WOLFRIDER, WOLFRIDER,
    SHATTERED_SUN_CLERIC, SHATTERED_SUN_CLERIC,
    HARVEST_GOLEM, HARVEST_GOLEM,
    IRONFORGE_RIFLEMAN, IRONFORGE_RIFLEMAN,

    # 4-drops (4 cards)
    CHILLWIND_YETI, CHILLWIND_YETI,
    GNOMISH_INVENTOR, GNOMISH_INVENTOR,

    # 5-drops (2 cards)
    NIGHTBLADE, NIGHTBLADE,

    # 6-drops (2 cards)
    ARGENT_COMMANDER, RECKLESS_ROCKETEER,
]

# =============================================================================
# Shaman Deck - Totem/Midrange Focus
# =============================================================================
SHAMAN_DECK = [
    # 1-drops (4 cards)
    STONETUSK_BOAR, STONETUSK_BOAR,
    ELVEN_ARCHER, ELVEN_ARCHER,

    # 2-drops (6 cards)
    BLOODFEN_RAPTOR, BLOODFEN_RAPTOR,
    RIVER_CROCOLISK, RIVER_CROCOLISK,
    NOVICE_ENGINEER, NOVICE_ENGINEER,

    # 3-drops (8 cards)
    RAID_LEADER, RAID_LEADER,
    SHATTERED_SUN_CLERIC, SHATTERED_SUN_CLERIC,
    HARVEST_GOLEM, HARVEST_GOLEM,
    WOLFRIDER, WOLFRIDER,

    # 4-drops (6 cards)
    CHILLWIND_YETI, CHILLWIND_YETI,
    SEN_JIN_SHIELDMASTA, SEN_JIN_SHIELDMASTA,
    GNOMISH_INVENTOR, GNOMISH_INVENTOR,

    # 5-drops (2 cards)
    STORMPIKE_COMMANDO, STORMPIKE_COMMANDO,

    # 6-drops (2 cards)
    BOULDERFIST_OGRE, BOULDERFIST_OGRE,

    # 7-drops (2 cards)
    STORMWIND_CHAMPION, STORMWIND_CHAMPION,
]

# =============================================================================
# Warlock Deck - Zoo/Aggro Focus
# =============================================================================
WARLOCK_DECK = [
    # 1-drops (6 cards)
    WISP, WISP,
    LEPER_GNOME, LEPER_GNOME,
    STONETUSK_BOAR, STONETUSK_BOAR,

    # 2-drops (8 cards)
    KNIFE_JUGGLER, KNIFE_JUGGLER,
    BLOODFEN_RAPTOR, BLOODFEN_RAPTOR,
    ACIDIC_SWAMP_OOZE, ACIDIC_SWAMP_OOZE,
    LOOT_HOARDER, LOOT_HOARDER,

    # 3-drops (8 cards)
    WOLFRIDER, WOLFRIDER,
    RAID_LEADER, RAID_LEADER,
    SHATTERED_SUN_CLERIC, SHATTERED_SUN_CLERIC,
    HARVEST_GOLEM, HARVEST_GOLEM,

    # 4-drops (4 cards)
    CHILLWIND_YETI, CHILLWIND_YETI,
    SILVERMOON_GUARDIAN, SILVERMOON_GUARDIAN,

    # 5-drops (2 cards)
    NIGHTBLADE, NIGHTBLADE,

    # 6-drops (2 cards)
    ARGENT_COMMANDER, RECKLESS_ROCKETEER,
]

# =============================================================================
# Druid Deck - Ramp/Big Minions Focus
# =============================================================================
DRUID_DECK = [
    # 1-drops (2 cards)
    STONETUSK_BOAR, STONETUSK_BOAR,

    # 2-drops (6 cards)
    BLOODFEN_RAPTOR, BLOODFEN_RAPTOR,
    RIVER_CROCOLISK, RIVER_CROCOLISK,
    NOVICE_ENGINEER, NOVICE_ENGINEER,

    # 3-drops (6 cards)
    SHATTERED_SUN_CLERIC, SHATTERED_SUN_CLERIC,
    HARVEST_GOLEM, HARVEST_GOLEM,
    RAID_LEADER, RAID_LEADER,

    # 4-drops (8 cards)
    CHILLWIND_YETI, CHILLWIND_YETI,
    SEN_JIN_SHIELDMASTA, SEN_JIN_SHIELDMASTA,
    GNOMISH_INVENTOR, GNOMISH_INVENTOR,
    SILVERMOON_GUARDIAN, SILVERMOON_GUARDIAN,

    # 5-drops (2 cards)
    STORMPIKE_COMMANDO, STORMPIKE_COMMANDO,

    # 6-drops (4 cards)
    BOULDERFIST_OGRE, BOULDERFIST_OGRE,
    LORD_OF_THE_ARENA, LORD_OF_THE_ARENA,

    # 7-drops (2 cards)
    STORMWIND_CHAMPION, STORMWIND_CHAMPION,
]


# =============================================================================
# Deck Registry
# =============================================================================
HEARTHSTONE_DECKS = {
    "Mage": MAGE_DECK,
    "Warrior": WARRIOR_DECK,
    "Hunter": HUNTER_DECK,
    "Paladin": PALADIN_DECK,
    "Priest": PRIEST_DECK,
    "Rogue": ROGUE_DECK,
    "Shaman": SHAMAN_DECK,
    "Warlock": WARLOCK_DECK,
    "Druid": DRUID_DECK,
}


def get_deck_for_hero(hero_class: str):
    """Get the appropriate deck for a hero class."""
    return HEARTHSTONE_DECKS.get(hero_class, MAGE_DECK)


def validate_deck(deck: list) -> tuple[bool, str]:
    """
    Validate a Hearthstone deck.

    Returns: (is_valid, error_message)
    """
    if len(deck) != 30:
        return False, f"Deck must have exactly 30 cards (has {len(deck)})"

    # Count card copies
    card_counts = {}
    for card in deck:
        name = card.name
        card_counts[name] = card_counts.get(name, 0) + 1

    # Check max 2 copies rule
    for card_name, count in card_counts.items():
        if count > 2:
            return False, f"Card '{card_name}' has {count} copies (max 2)"

    return True, ""


# Validate all decks on module load
for hero_class, deck in HEARTHSTONE_DECKS.items():
    is_valid, error = validate_deck(deck)
    if not is_valid:
        print(f"WARNING: {hero_class} deck is invalid: {error}")
