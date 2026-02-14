"""
Hearthstone Deck Definitions

30-card decks for each class following Hearthstone deck-building rules:
- Exactly 30 cards
- Max 2 copies of any card (1 for Legendaries)
- Class cards + Neutral cards allowed
"""

from src.cards.hearthstone.basic import *
from src.cards.hearthstone.classic import *
from src.cards.hearthstone.mage import *
from src.cards.hearthstone.warrior import *
from src.cards.hearthstone.hunter import *
from src.cards.hearthstone.paladin import *
from src.cards.hearthstone.priest import *
from src.cards.hearthstone.rogue import *
from src.cards.hearthstone.shaman import *
from src.cards.hearthstone.warlock import *
from src.cards.hearthstone.druid import *


# =============================================================================
# Mage Deck - Spell-Heavy Tempo
# =============================================================================
# Strategy: Control the board with efficient spells (Frostbolt, Fireball,
# Flamestrike), grow Mana Wyrm with spell casts, finish with burn damage.
# Curve: aggressive early with Mana Wyrm + spells, strong midgame removal.
MAGE_DECK = [
    # 0-cost (2 cards)
    MIRROR_IMAGE, MIRROR_IMAGE,

    # 1-cost (4 cards)
    ARCANE_MISSILES, ARCANE_MISSILES,
    MANA_WYRM, MANA_WYRM,

    # 2-cost (6 cards)
    FROSTBOLT, FROSTBOLT,
    SORCERERS_APPRENTICE, SORCERERS_APPRENTICE,
    KOBOLD_GEOMANCER, LOOT_HOARDER,

    # 3-cost (6 cards)
    ARCANE_INTELLECT, ARCANE_INTELLECT,
    FROST_NOVA, KIRIN_TOR_MAGE,
    HARVEST_GOLEM, HARVEST_GOLEM,

    # 4-cost (6 cards)
    FIREBALL, FIREBALL,
    POLYMORPH, POLYMORPH,
    WATER_ELEMENTAL, WATER_ELEMENTAL,

    # 5-cost (2 cards)
    AZURE_DRAKE, AZURE_DRAKE,

    # 6-cost (2 cards)
    BLIZZARD, BOULDERFIST_OGRE,

    # 7-cost (2 cards)
    FLAMESTRIKE, FLAMESTRIKE,
]

# =============================================================================
# Warrior Deck - Weapon/Armor Control
# =============================================================================
# Strategy: Gain armor with Shield Block and Armorsmith, control the board
# with weapons (Fiery War Axe, Arcanite Reaper) and removal (Execute),
# Whirlwind combos with Execute and Frothing Berserker for value.
WARRIOR_DECK = [
    # 0-cost (2 cards)
    INNER_RAGE, INNER_RAGE,

    # 1-cost (4 cards)
    EXECUTE, EXECUTE,
    SHIELD_SLAM, WHIRLWIND,

    # 2-cost (6 cards)
    ARMORSMITH, ARMORSMITH,
    CRUEL_TASKMASTER, CRUEL_TASKMASTER,
    HEROIC_STRIKE, SLAM,

    # 3-cost (6 cards)
    FIERY_WAR_AXE, FIERY_WAR_AXE,
    SHIELD_BLOCK, SHIELD_BLOCK,
    FROTHING_BERSERKER, FROTHING_BERSERKER,

    # 4-cost (4 cards)
    KOR_KRON_ELITE, KOR_KRON_ELITE,
    ARATHI_WEAPONSMITH, MORTAL_STRIKE,

    # 5-cost (4 cards)
    ARCANITE_REAPER, BRAWL,
    AZURE_DRAKE, AZURE_DRAKE,

    # 7-cost (2 cards)
    GOREHOWL, STORMWIND_CHAMPION,

    # 8-cost (2 cards) - Legendary
    GROMMASH_HELLSCREAM, BOULDERFIST_OGRE,
]

# =============================================================================
# Hunter Deck - Face/Beast Aggro
# =============================================================================
# Strategy: Flood the board with cheap Beasts, buff with Timber Wolf and
# Houndmaster, use Kill Command for 5 damage burst with Beast synergy.
# Aggressive mana curve focused on ending the game fast.
HUNTER_DECK = [
    # 1-cost (8 cards)
    ARCANE_SHOT, ARCANE_SHOT,
    TRACKING, TRACKING,
    TIMBER_WOLF, TIMBER_WOLF,
    LEPER_GNOME, LEPER_GNOME,

    # 2-cost (6 cards)
    SCAVENGING_HYENA, SCAVENGING_HYENA,
    KNIFE_JUGGLER, KNIFE_JUGGLER,
    EXPLOSIVE_TRAP, FREEZING_TRAP,

    # 3-cost (6 cards)
    KILL_COMMAND, KILL_COMMAND,
    ANIMAL_COMPANION, ANIMAL_COMPANION,
    EAGLEHORN_BOW, UNLEASH_THE_HOUNDS,

    # 4-cost (4 cards)
    HOUNDMASTER, HOUNDMASTER,
    MULTI_SHOT, MULTI_SHOT,

    # 5-cost (2 cards)
    STARVING_BUZZARD, STRANGLETHORN_TIGER,

    # 6-cost (4 cards)
    SAVANNAH_HIGHMANE, SAVANNAH_HIGHMANE,
    RECKLESS_ROCKETEER, ARGENT_COMMANDER,
]

# =============================================================================
# Paladin Deck - Midrange Buff/Control
# =============================================================================
# Strategy: Strong buffs (Blessing of Kings, Blessing of Might) turn
# cheap minions into threats. Consecration and Truesilver Champion for
# board control. Guardian of Kings and Holy Light for sustain.
PALADIN_DECK = [
    # 1-cost (4 cards)
    BLESSING_OF_MIGHT, BLESSING_OF_MIGHT,
    NOBLE_SACRIFICE, NOBLE_SACRIFICE,

    # 2-cost (4 cards)
    EQUALITY, EQUALITY,
    KNIFE_JUGGLER, KNIFE_JUGGLER,

    # 3-cost (6 cards)
    ALDOR_PEACEKEEPER, ALDOR_PEACEKEEPER,
    SWORD_OF_JUSTICE, HARVEST_GOLEM,
    HARVEST_GOLEM, DIVINE_FAVOR,

    # 4-cost (8 cards)
    BLESSING_OF_KINGS, BLESSING_OF_KINGS,
    CONSECRATION, CONSECRATION,
    TRUESILVER_CHAMPION, TRUESILVER_CHAMPION,
    CHILLWIND_YETI, SEN_JIN_SHIELDMASTA,

    # 5-cost (2 cards)
    AZURE_DRAKE, SILVER_HAND_KNIGHT,

    # 6-cost (2 cards)
    AVENGING_WRATH, SUNWALKER,

    # 7-cost (2 cards)
    GUARDIAN_OF_KINGS, GUARDIAN_OF_KINGS,

    # 8-cost (2 cards) - Legendary
    TIRION_FORDRING, LAY_ON_HANDS,
]

# =============================================================================
# Priest Deck - Control/Healing
# =============================================================================
# Strategy: Heal minions to keep them alive, buff health with Divine Spirit
# and Power Word: Shield, remove threats with Shadow Word: Pain/Death.
# Holy Nova for board clear + heal. Mind Control as ultimate late-game answer.
PRIEST_DECK = [
    # 0-cost (2 cards)
    CIRCLE_OF_HEALING, SILENCE_SPELL,

    # 1-cost (6 cards)
    NORTHSHIRE_CLERIC, NORTHSHIRE_CLERIC,
    POWER_WORD_SHIELD, POWER_WORD_SHIELD,
    HOLY_SMITE, HOLY_SMITE,

    # 2-cost (4 cards)
    SHADOW_WORD_PAIN, SHADOW_WORD_PAIN,
    DIVINE_SPIRIT, DIVINE_SPIRIT,

    # 3-cost (4 cards)
    SHADOW_WORD_DEATH, SHADOW_WORD_DEATH,
    THOUGHTSTEAL, INJURED_BLADEMASTER,

    # 4-cost (6 cards)
    AUCHENAI_SOULPRIEST, AUCHENAI_SOULPRIEST,
    MASS_DISPEL, CHILLWIND_YETI,
    SEN_JIN_SHIELDMASTA, SEN_JIN_SHIELDMASTA,

    # 5-cost (2 cards)
    HOLY_NOVA, HOLY_NOVA,

    # 6-cost (4 cards)
    HOLY_FIRE, TEMPLE_ENFORCER,
    CABAL_SHADOW_PRIEST, SYLVANAS_WINDRUNNER,

    # 10-cost (2 cards)
    MIND_CONTROL, MIND_CONTROL,
]

# =============================================================================
# Rogue Deck - Tempo/Combo
# =============================================================================
# Strategy: Cheap removal (Backstab, Eviscerate, SI:7 Agent combo) to
# maintain board control. Cold Blood on stealthed minions for big damage.
# Sprint for late-game refill. Efficient tempo plays every turn.
ROGUE_DECK = [
    # 0-cost (4 cards)
    BACKSTAB, BACKSTAB,
    PREPARATION, PREPARATION,

    # 1-cost (4 cards)
    COLD_BLOOD, COLD_BLOOD,
    DEADLY_POISON, DEADLY_POISON,

    # 2-cost (6 cards)
    EVISCERATE, EVISCERATE,
    SAP, SAP,
    DEFIAS_RINGLEADER, DEFIAS_RINGLEADER,

    # 3-cost (6 cards)
    SI7_AGENT, SI7_AGENT,
    FAN_OF_KNIVES, FAN_OF_KNIVES,
    EARTHEN_RING_FARSEER, HARVEST_GOLEM,

    # 4-cost (2 cards)
    DARK_IRON_DWARF, DARK_IRON_DWARF,

    # 5-cost (4 cards)
    ASSASSINATE, ASSASSINATE,
    AZURE_DRAKE, AZURE_DRAKE,

    # 6-cost (2 cards)
    ARGENT_COMMANDER, ARGENT_COMMANDER,

    # 7-cost (2 cards)
    SPRINT, SPRINT,
]

# =============================================================================
# Shaman Deck - Midrange Overload
# =============================================================================
# Strategy: Efficient overload cards (Lightning Bolt, Lightning Storm) for
# early removal, Flametongue Totem and Feral Spirit for board presence.
# Fire Elemental as a strong 6-drop finisher. Bloodlust for burst lethal.
SHAMAN_DECK = [
    # 0-cost (1 card)
    ANCESTRAL_HEALING,

    # 1-cost (5 cards)
    LIGHTNING_BOLT, LIGHTNING_BOLT,
    EARTH_SHOCK, EARTH_SHOCK,
    FORKED_LIGHTNING,

    # 2-cost (4 cards)
    FLAMETONGUE_TOTEM, FLAMETONGUE_TOTEM,
    STORMFORGED_AXE, STORMFORGED_AXE,

    # 3-cost (8 cards)
    FERAL_SPIRIT, FERAL_SPIRIT,
    HEX, HEX,
    LIGHTNING_STORM, LIGHTNING_STORM,
    LAVA_BURST, MANA_TIDE_TOTEM,

    # 4-cost (2 cards)
    CHILLWIND_YETI, DEFENDER_OF_ARGUS,

    # 5-cost (4 cards)
    EARTH_ELEMENTAL, BLOODLUST,
    AZURE_DRAKE, AZURE_DRAKE,

    # 6-cost (4 cards)
    FIRE_ELEMENTAL, FIRE_ELEMENTAL,
    ARGENT_COMMANDER, BOULDERFIST_OGRE,

    # 8-cost (2 cards) - Legendary
    AL_AKIR_THE_WINDLORD, STORMWIND_CHAMPION,
]

# =============================================================================
# Warlock Deck - Zoo Aggro
# =============================================================================
# Strategy: Cheap efficient minions (Flame Imp, Voidwalker) that leverage
# the Warlock hero power (Life Tap) for card draw. Flood the board fast,
# buff with Power Overwhelming, Doomguard as a 5/7 Charge finisher.
WARLOCK_DECK = [
    # 0-cost (2 cards)
    WISP, WISP,

    # 1-cost (8 cards)
    SOULFIRE, SOULFIRE,
    MORTAL_COIL, MORTAL_COIL,
    FLAME_IMP, FLAME_IMP,
    VOIDWALKER, VOIDWALKER,

    # 2-cost (6 cards)
    KNIFE_JUGGLER, KNIFE_JUGGLER,
    DIRE_WOLF_ALPHA, DIRE_WOLF_ALPHA,
    SUCCUBUS, LOOT_HOARDER,

    # 3-cost (4 cards)
    HARVEST_GOLEM, HARVEST_GOLEM,
    SHATTERED_SUN_CLERIC, SHATTERED_SUN_CLERIC,

    # 4-cost (4 cards)
    DARK_IRON_DWARF, DARK_IRON_DWARF,
    DEFENDER_OF_ARGUS, DEFENDER_OF_ARGUS,

    # 5-cost (4 cards)
    DOOMGUARD, DOOMGUARD,
    NIGHTBLADE, NIGHTBLADE,

    # 1-cost buff (2 cards)
    POWER_OVERWHELMING, POWER_OVERWHELMING,
]

# =============================================================================
# Druid Deck - Ramp/Big Minions
# =============================================================================
# Strategy: Ramp with Innervate and Wild Growth to reach big minions early.
# Swipe and Wrath for removal. Druid of the Claw for flexible midgame.
# Force of Nature + Savage Roar combo for burst finisher (14 damage).
DRUID_DECK = [
    # 0-cost (2 cards)
    INNERVATE, INNERVATE,

    # 1-cost (2 cards)
    CLAW, CLAW,

    # 2-cost (4 cards)
    WILD_GROWTH, WILD_GROWTH,
    WRATH, WRATH,

    # 3-cost (4 cards)
    SAVAGE_ROAR, SAVAGE_ROAR,
    MARK_OF_NATURE, HARVEST_GOLEM,

    # 4-cost (4 cards)
    SWIPE, SWIPE,
    KEEPER_OF_THE_GROVE, KEEPER_OF_THE_GROVE,

    # 5-cost (4 cards)
    DRUID_OF_THE_CLAW, DRUID_OF_THE_CLAW,
    NOURISH, AZURE_DRAKE,

    # 6-cost (2 cards)
    FORCE_OF_NATURE, STARFIRE,

    # 7-cost (4 cards)
    ANCIENT_OF_LORE, ANCIENT_OF_LORE,
    ANCIENT_OF_WAR, ANCIENT_OF_WAR,

    # 8-cost (2 cards)
    IRONBARK_PROTECTOR, IRONBARK_PROTECTOR,

    # 9-cost (2 cards) - Legendary
    CENARIUS, STORMWIND_CHAMPION,
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
