"""
Avatar: The Last Airbender (TLA) Card Implementations

Set released November 21, 2025. 286 cards.
Features mechanics: Airbend, Waterbend, Earthbend, Firebend, Lesson spells, Allies
"""

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, ObjectState,
    make_creature, make_instant, make_enchantment,
    new_id, get_power, get_toughness
)
from typing import Optional, Callable


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def make_sorcery(name: str, mana_cost: str, colors: set, text: str, subtypes: set = None, resolve=None):
    """Helper to create sorcery card definitions."""
    from src.engine import CardDefinition, Characteristics
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.SORCERY},
            subtypes=subtypes or set(),
            colors=colors,
            mana_cost=mana_cost
        ),
        text=text,
        resolve=resolve
    )


def make_artifact(name: str, mana_cost: str, text: str, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create artifact card definitions."""
    from src.engine import CardDefinition, Characteristics
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            mana_cost=mana_cost
        ),
        text=text,
        setup_interceptors=setup_interceptors
    )


def make_land(name: str, subtypes: set = None, supertypes: set = None, text: str = ""):
    """Helper to create land card definitions."""
    from src.engine import CardDefinition, Characteristics
    return CardDefinition(
        name=name,
        mana_cost="",
        characteristics=Characteristics(
            types={CardType.LAND},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            mana_cost=""
        ),
        text=text
    )


# =============================================================================
# WHITE CARDS
# =============================================================================

AANGS_ICEBERG = make_enchantment(
    name="Aang's Iceberg",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Flash. When this enchantment enters, exile up to one other target nonland permanent until this enchantment leaves the battlefield."
)

AANG_THE_LAST_AIRBENDER = make_creature(
    name="Aang, the Last Airbender",
    power=3,
    toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Avatar", "Ally"},
    supertypes={"Legendary"},
    text="Flying. Airbend — Whenever Aang attacks, you may return target nonland permanent to its owner's hand. Whenever you cast a Lesson spell, Aang gains lifelink until end of turn."
)

AIRBENDER_ASCENSION = make_enchantment(
    name="Airbender Ascension",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, airbend up to one target creature. (Return it to its owner's hand.)"
)

AIRBENDERS_REVERSAL = make_instant(
    name="Airbender's Reversal",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Lesson — Choose one: Destroy target creature with flying; or return target nonland permanent you control to its owner's hand."
)

AIRBENDING_LESSON = make_instant(
    name="Airbending Lesson",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Lesson — Airbend target nonland permanent. Draw a card."
)

APPA_LOYAL_SKY_BISON = make_creature(
    name="Appa, Loyal Sky Bison",
    power=4,
    toughness=4,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Bison", "Ally"},
    supertypes={"Legendary"},
    text="Flying. When Appa enters, create two 1/1 white Ally creature tokens. Whenever Appa attacks, Allies you control get +1/+1 until end of turn."
)

APPA_STEADFAST_GUARDIAN = make_creature(
    name="Appa, Steadfast Guardian",
    power=3,
    toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Bison", "Ally"},
    supertypes={"Legendary"},
    text="Flash. Flying. When Appa enters, airbend any number of other target nonland permanents you control."
)

AVATAR_ENTHUSIASTS = make_creature(
    name="Avatar Enthusiasts",
    power=2,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Peasant", "Ally"},
    text="Whenever another Ally enters under your control, put a +1/+1 counter on Avatar Enthusiasts."
)

AVATARS_WRATH = make_sorcery(
    name="Avatar's Wrath",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Choose up to one target creature, then return all other creatures to their owners' hands."
)

COMPASSIONATE_HEALER = make_creature(
    name="Compassionate Healer",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric", "Ally"},
    text="Whenever this creature becomes tapped, you gain 1 life and scry 1."
)

CURIOUS_FARM_ANIMALS = make_creature(
    name="Curious Farm Animals",
    power=1,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Boar", "Elk", "Bird", "Ox"},
    text="When this creature dies, you gain 3 life."
)

DESTINED_CONFRONTATION = make_sorcery(
    name="Destined Confrontation",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Each player chooses any number of creatures they control with total power 4 or less, then sacrifices the rest."
)

EARTH_KINGDOM_JAILER = make_creature(
    name="Earth Kingdom Jailer",
    power=3,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Ally"},
    text="When this creature enters, exile up to one target artifact, creature, or enchantment an opponent controls with mana value 3 or greater until this creature leaves the battlefield."
)

EARTH_KINGDOM_PROTECTORS = make_creature(
    name="Earth Kingdom Protectors",
    power=1,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Ally"},
    text="Vigilance. Sacrifice this creature: Another target Ally you control gains indestructible until end of turn."
)

ENTER_THE_AVATAR_STATE = make_instant(
    name="Enter the Avatar State",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Lesson — Until end of turn, target creature becomes an Avatar in addition to its other types and gains flying, first strike, lifelink, and hexproof."
)

FANCY_FOOTWORK = make_instant(
    name="Fancy Footwork",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Lesson — Untap one or two target creatures. They each get +2/+2 until end of turn."
)

GATHER_THE_WHITE_LOTUS = make_sorcery(
    name="Gather the White Lotus",
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    text="Create a 1/1 white Ally creature token for each Plains you control. Scry 2."
)

GLIDER_KIDS = make_creature(
    name="Glider Kids",
    power=2,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Pilot", "Ally"},
    text="Flying. When this creature enters, scry 1."
)

GLIDER_STAFF = make_artifact(
    name="Glider Staff",
    mana_cost="{2}{W}",
    subtypes={"Equipment"},
    text="When this Equipment enters, airbend up to one target creature. Equipped creature gets +1/+1 and has flying. Equip {2}"
)

HAKODA_SELFLESS_COMMANDER = make_creature(
    name="Hakoda, Selfless Commander",
    power=3,
    toughness=5,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Warrior", "Ally"},
    supertypes={"Legendary"},
    text="Vigilance. You may look at the top card of your library any time. You may cast Ally spells from the top of your library."
)

INVASION_REINFORCEMENTS = make_creature(
    name="Invasion Reinforcements",
    power=1,
    toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Warrior", "Ally"},
    text="Flash. When this creature enters, create a 1/1 white Ally creature token."
)

JEONG_JEONGS_DESERTERS = make_creature(
    name="Jeong Jeong's Deserters",
    power=1,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rebel", "Ally"},
    text="When this creature enters, put a +1/+1 counter on target creature you control."
)

KATARA_WATERBENDING_MASTER = make_creature(
    name="Katara, Waterbending Master",
    power=2,
    toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Wizard", "Ally"},
    supertypes={"Legendary"},
    text="Ward {2}. Waterbend — Whenever you cast an instant or sorcery spell, you may tap or untap target creature."
)

SOKKA_SWORDSMAN = make_creature(
    name="Sokka, Swordsman",
    power=3,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Warrior", "Ally"},
    supertypes={"Legendary"},
    text="First strike. Whenever Sokka deals combat damage to a player, draw a card."
)

SUKI_KYOSHI_WARRIOR = make_creature(
    name="Suki, Kyoshi Warrior",
    power=2,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Warrior", "Ally"},
    supertypes={"Legendary"},
    text="First strike. Other Warrior creatures you control get +1/+0. Whenever another Warrior enters under your control, Suki gains indestructible until end of turn."
)

UNCLE_IROH_TEA_MASTER = make_creature(
    name="Uncle Iroh, Tea Master",
    power=2,
    toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Advisor", "Ally"},
    supertypes={"Legendary"},
    text="At the beginning of your end step, if you gained life this turn, draw a card. {T}: You gain 2 life."
)

WHITE_LOTUS_MEMBER = make_creature(
    name="White Lotus Member",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk", "Ally"},
    text="When this creature enters, look at the top three cards of your library. You may reveal an Ally card from among them and put it into your hand. Put the rest on the bottom of your library in any order."
)


# =============================================================================
# BLUE CARDS
# =============================================================================

AANG_SWIFT_SAVIOR = make_creature(
    name="Aang, Swift Savior",
    power=2,
    toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Avatar", "Ally"},
    supertypes={"Legendary"},
    text="Flash. Flying. When Aang enters, airbend up to one other target creature or counter target spell with mana value 2 or less."
)

ABANDON_ATTACHMENTS = make_instant(
    name="Abandon Attachments",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Lesson — You may discard a card. If you do, draw two cards."
)

ACCUMULATE_WISDOM = make_instant(
    name="Accumulate Wisdom",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Lesson — Look at the top three cards of your library. Put one into your hand and the rest on the bottom of your library in any order."
)

BENEVOLENT_RIVER_SPIRIT = make_creature(
    name="Benevolent River Spirit",
    power=4,
    toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Flying, ward {2}. When this creature enters, scry 2."
)

BOOMERANG_BASICS = make_sorcery(
    name="Boomerang Basics",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Lesson — Return target nonland permanent to its owner's hand. If you controlled it, draw a card."
)

KNOWLEDGE_SEEKER = make_creature(
    name="Knowledge Seeker",
    power=1,
    toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When this creature enters, draw a card, then discard a card."
)

LIBRARY_GUARDIAN = make_creature(
    name="Library Guardian",
    power=3,
    toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Flying. Whenever you cast an instant or sorcery spell, scry 1."
)

MASTER_PAKKU = make_creature(
    name="Master Pakku",
    power=3,
    toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard", "Ally"},
    supertypes={"Legendary"},
    text="Waterbend — {U}, {T}: Tap target creature. It doesn't untap during its controller's next untap step."
)

MOON_SPIRIT_BLESSING = make_instant(
    name="Moon Spirit Blessing",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Target creature gains hexproof until end of turn. Draw a card."
)

NORTHERN_WATER_TRIBE = make_creature(
    name="Northern Water Tribe",
    power=2,
    toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard", "Ally"},
    text="When this creature enters, tap up to one target creature an opponent controls."
)

OCEAN_SPIRIT_FURY = make_sorcery(
    name="Ocean Spirit Fury",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Return all creatures to their owners' hands."
)

PRINCESS_YUE = make_creature(
    name="Princess Yue",
    power=1,
    toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Noble", "Ally"},
    supertypes={"Legendary"},
    text="When Princess Yue dies, you may exile her. If you do, create a 4/4 blue Spirit creature token with flying named Moon Spirit."
)

SPIRIT_LIBRARY = make_enchantment(
    name="Spirit Library",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="When Spirit Library enters, draw two cards. Whenever you cast a Lesson spell, draw a card."
)

WATERBENDING_LESSON = make_instant(
    name="Waterbending Lesson",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Lesson — Tap up to two target creatures. Those creatures don't untap during their controllers' next untap steps."
)

WAN_SHI_TONG = make_creature(
    name="Wan Shi Tong",
    power=4,
    toughness=6,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit", "Owl"},
    supertypes={"Legendary"},
    text="Flying. Whenever you cast a noncreature spell, draw a card. At the beginning of your end step, if you drew three or more cards this turn, each opponent mills five cards."
)


# =============================================================================
# BLACK CARDS
# =============================================================================

AZULA_ALWAYS_LIES = make_instant(
    name="Azula Always Lies",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Lesson — Choose one or both: Target creature gets -1/-1 until end of turn; and/or put a +1/+1 counter on target creature."
)

AZULA_CUNNING_USURPER = make_creature(
    name="Azula, Cunning Usurper",
    power=4,
    toughness=4,
    mana_cost="{2}{U}{B}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Noble", "Rogue"},
    supertypes={"Legendary"},
    text="Firebend 2 — Whenever Azula attacks, exile the top two cards of target opponent's library. You may cast spells from among those cards this turn, and mana of any type can be spent to cast them."
)

AZULA_ON_THE_HUNT = make_creature(
    name="Azula, On the Hunt",
    power=4,
    toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Firebend 2 — Whenever Azula attacks, you lose 1 life and create a Clue token. Menace."
)

BEETLE_HEADED_MERCHANTS = make_creature(
    name="Beetle-Headed Merchants",
    power=5,
    toughness=4,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Citizen"},
    text="Whenever this creature attacks, you may sacrifice another creature or artifact. If you do, draw a card and put a +1/+1 counter on this creature."
)

BOILING_ROCK_RIOTER = make_creature(
    name="Boiling Rock Rioter",
    power=3,
    toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue", "Ally"},
    text="Firebend 1. {T}, Tap two other untapped Allies you control: Exile target card from a graveyard. You may cast Ally spells from among cards exiled with this creature."
)

BUZZARD_WASP_COLONY = make_creature(
    name="Buzzard-Wasp Colony",
    power=2,
    toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Bird", "Insect"},
    text="Flying. When this creature enters, you may sacrifice an artifact or creature. If you do, draw a card. Whenever another creature you control dies, if it had counters on it, move those counters onto this creature."
)

CANYON_CRAWLER = make_creature(
    name="Canyon Crawler",
    power=6,
    toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Spider", "Beast"},
    text="Deathtouch. When this creature enters, create a Food token. Swampcycling {2}"
)

CORRUPT_COURT_OFFICIAL = make_creature(
    name="Corrupt Court Official",
    power=1,
    toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Advisor"},
    text="When this creature enters, target opponent discards a card."
)

CRUEL_ADMINISTRATOR = make_creature(
    name="Cruel Administrator",
    power=5,
    toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Soldier"},
    text="Raid — This creature enters with a +1/+1 counter on it if you attacked this turn. Whenever this creature attacks, create a 1/1 red Soldier creature token that's tapped and attacking."
)

DAI_LI_INDOCTRINATION = make_sorcery(
    name="Dai Li Indoctrination",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Lesson — Choose one: Target opponent discards a card; or earthbend 2."
)

DAY_OF_BLACK_SUN = make_sorcery(
    name="Day of Black Sun",
    mana_cost="{X}{B}{B}",
    colors={Color.BLACK},
    text="All creatures with mana value X or less lose all abilities until end of turn, then destroy all creatures with mana value X or less."
)

DEADLY_PRECISION = make_sorcery(
    name="Deadly Precision",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, pay {4} or sacrifice a nonland permanent. Destroy target creature."
)

EPIC_DOWNFALL = make_sorcery(
    name="Epic Downfall",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Exile target creature with mana value 3 or greater."
)

FATAL_FISSURE = make_instant(
    name="Fatal Fissure",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. When that creature dies this turn, earthbend 4."
)

FIRE_LORD_OZAI = make_creature(
    name="Fire Lord Ozai",
    power=5,
    toughness=5,
    mana_cost="{3}{B}{R}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Firebend 3. Menace. At the beginning of your end step, Fire Lord Ozai deals damage equal to its power to each opponent."
)

LONG_FENG = make_creature(
    name="Long Feng",
    power=3,
    toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Advisor"},
    supertypes={"Legendary"},
    text="Earthbend 2. At the beginning of your upkeep, each opponent loses 1 life for each creature you control with a +1/+1 counter on it."
)

MAI_KNIVES_EXPERT = make_creature(
    name="Mai, Knives Expert",
    power=2,
    toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Assassin"},
    supertypes={"Legendary"},
    text="Deathtouch. Whenever Mai deals combat damage to a player, that player discards a card."
)


# =============================================================================
# RED CARDS
# =============================================================================

BOAR_Q_PINE = make_creature(
    name="Boar-q-pine",
    power=2,
    toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Boar", "Porcupine"},
    text="Whenever you cast a noncreature spell, put a +1/+1 counter on this creature."
)

BUMI_BASH = make_sorcery(
    name="Bumi Bash",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Choose one — Bumi Bash deals damage equal to the number of lands you control to target creature; or destroy target land creature or nonbasic land."
)

COMBUSTION_MAN = make_creature(
    name="Combustion Man",
    power=4,
    toughness=6,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Assassin"},
    supertypes={"Legendary"},
    text="Whenever Combustion Man attacks, destroy target permanent unless its controller has Combustion Man deal damage to them equal to his power."
)

COMBUSTION_TECHNIQUE = make_instant(
    name="Combustion Technique",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Lesson — Combustion Technique deals damage equal to 2 plus the number of Lesson cards in your graveyard to target creature. If that creature would die this turn, exile it instead."
)

FATED_FIREPOWER = make_enchantment(
    name="Fated Firepower",
    mana_cost="{X}{R}{R}{R}",
    colors={Color.RED},
    text="Flash. This enchantment enters with X fire counters on it. If a source you control would deal damage to an opponent or a permanent an opponent controls, it deals that much damage plus the number of fire counters on this enchantment instead."
)

FIREBENDING_LESSON = make_instant(
    name="Firebending Lesson",
    mana_cost="{R}",
    colors={Color.RED},
    text="Lesson — Kicker {4}. Firebending Lesson deals 2 damage to target creature. If this spell was kicked, it deals 5 damage instead."
)

FIREBENDING_STUDENT = make_creature(
    name="Firebending Student",
    power=1,
    toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Monk"},
    text="Prowess. Firebend X, where X is this creature's power."
)

FIRE_NATION_ATTACKS = make_instant(
    name="Fire Nation Attacks",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="Create two 2/2 red Soldier creature tokens with firebend 1. Flashback {8}{R}."
)

FIRE_NATION_CADETS = make_creature(
    name="Fire Nation Cadets",
    power=1,
    toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="This creature has firebend 2 as long as there's a Lesson card in your graveyard. {2}: This creature gets +1/+0 until end of turn."
)

FIRE_NATION_WARSHIP = make_artifact(
    name="Fire Nation Warship",
    mana_cost="{4}{R}",
    subtypes={"Vehicle"},
    text="Flying. Firebend 2 — Whenever this Vehicle attacks, it deals 2 damage to any target. Crew 2"
)

JEONG_JEONG_THE_DESERTER = make_creature(
    name="Jeong Jeong, the Deserter",
    power=3,
    toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard", "Ally"},
    supertypes={"Legendary"},
    text="Firebend 3. At the beginning of your end step, if a source you controlled dealt 5 or more damage this turn, draw a card."
)

PRINCE_ZUKO = make_creature(
    name="Prince Zuko",
    power=3,
    toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Firebend 2. Whenever Prince Zuko attacks, you may discard a card. If you do, draw a card."
)

ZUKO_REDEEMED = make_creature(
    name="Zuko, Redeemed",
    power=4,
    toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Noble", "Ally"},
    supertypes={"Legendary"},
    text="Firebend 2. First strike. Whenever Zuko deals combat damage, put a +1/+1 counter on another target Ally you control."
)


# =============================================================================
# GREEN CARDS
# =============================================================================

ALLIES_AT_LAST = make_instant(
    name="Allies at Last",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Affinity for Allies. Up to two target creatures you control each deal damage equal to their power to target creature an opponent controls."
)

AVATAR_DESTINY = make_enchantment(
    name="Avatar Destiny",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Enchant creature. Enchanted creature gets +1/+1 for each creature card in your graveyard and is an Avatar in addition to its other types. When enchanted creature dies, mill cards equal to its power."
)

BADGERMOLE = make_creature(
    name="Badgermole",
    power=4,
    toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Badger", "Mole"},
    text="When this creature enters, earthbend 2. Creatures you control with +1/+1 counters on them have trample."
)

BADGERMOLE_CUB = make_creature(
    name="Badgermole Cub",
    power=2,
    toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Badger", "Mole"},
    text="When this creature enters, earthbend 1. Whenever you tap a creature for mana, add an additional {G}."
)

BUMI_KING_OF_THREE_TRIALS = make_creature(
    name="Bumi, King of Three Trials",
    power=4,
    toughness=4,
    mana_cost="{5}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Noble", "Ally"},
    supertypes={"Legendary"},
    text="When Bumi enters, choose up to X, where X is the number of Lesson cards in your graveyard: Put three +1/+1 counters on Bumi; target player scries 3; earthbend 3."
)

CYCLE_OF_RENEWAL = make_instant(
    name="Cycle of Renewal",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Lesson — Sacrifice a land. Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle."
)

EARTHBENDER_ASCENSION = make_enchantment(
    name="Earthbender Ascension",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, earthbend 2. Then search your library for a basic land card, put it onto the battlefield tapped, then shuffle. Landfall — Whenever a land you control enters, put a quest counter on this enchantment."
)

EARTHBENDING_LESSON = make_sorcery(
    name="Earthbending Lesson",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Lesson — Earthbend 4. (Target land you control becomes a 0/0 creature with haste that's still a land. Put four +1/+1 counters on it.)"
)

EARTH_KINGDOM_GENERAL = make_creature(
    name="Earth Kingdom General",
    power=2,
    toughness=2,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Soldier", "Ally"},
    text="When this creature enters, earthbend 2. Whenever you put one or more +1/+1 counters on a creature, you may gain that much life. Do this only once each turn."
)

EARTH_RUMBLE = make_sorcery(
    name="Earth Rumble",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Earthbend 2. When you do, up to one target creature you control fights target creature an opponent controls."
)

TOPH_BEIFONG = make_creature(
    name="Toph Beifong",
    power=3,
    toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Warrior", "Ally"},
    supertypes={"Legendary"},
    text="Earthbend 3. Creatures you control with +1/+1 counters have trample and hexproof."
)

TOPH_METALBENDER = make_creature(
    name="Toph, Metalbender",
    power=4,
    toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Warrior", "Ally"},
    supertypes={"Legendary"},
    text="Earthbend 4. You may cast artifact spells as though they had flash. Artifact creatures you control get +2/+2."
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

AANG_AND_LA = make_creature(
    name="Aang and La, Ocean's Fury",
    power=5,
    toughness=5,
    mana_cost="{3}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Avatar", "Spirit", "Ally"},
    supertypes={"Legendary"},
    text="Flying. Hexproof. When this creature enters, return all creatures your opponents control to their owners' hands."
)

BEIFONGS_BOUNTY_HUNTERS = make_creature(
    name="Beifong's Bounty Hunters",
    power=4,
    toughness=4,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Mercenary"},
    text="Whenever a nontoken creature you control dies, earthbend X, where X is that creature's power."
)

BITTER_WORK = make_enchantment(
    name="Bitter Work",
    mana_cost="{1}{R}{G}",
    colors={Color.RED, Color.GREEN},
    text="Whenever you attack a player with one or more creatures with power 4 or greater, draw a card. Exhaust — {4}: Earthbend 4."
)

BUMI_UNLEASHED = make_creature(
    name="Bumi, Unleashed",
    power=5,
    toughness=4,
    mana_cost="{3}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Noble", "Ally"},
    supertypes={"Legendary"},
    text="Trample. When Bumi enters, earthbend 4. Whenever Bumi deals combat damage to a player, untap all lands you control. After this phase, there is an additional combat phase."
)

DAI_LI_AGENTS = make_creature(
    name="Dai Li Agents",
    power=3,
    toughness=4,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Soldier"},
    text="When this creature enters, earthbend 1, then earthbend 1. Whenever this creature attacks, each opponent loses X life and you gain X life, where X is the number of creatures you control with +1/+1 counters on them."
)

FIRE_LORD_AZULA = make_creature(
    name="Fire Lord Azula",
    power=4,
    toughness=4,
    mana_cost="{1}{U}{B}{R}",
    colors={Color.BLUE, Color.BLACK, Color.RED},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Firebend 2. Whenever you cast an instant or sorcery spell while attacking, copy that spell. You may choose new targets for the copy."
)

FIRE_LORD_ZUKO = make_creature(
    name="Fire Lord Zuko",
    power=2,
    toughness=4,
    mana_cost="{R}{W}{B}",
    colors={Color.RED, Color.WHITE, Color.BLACK},
    subtypes={"Human", "Noble", "Ally"},
    supertypes={"Legendary"},
    text="Firebend X, where X is the number of cards you've cast from exile this turn. Whenever you cast a spell from exile, put a +1/+1 counter on Fire Lord Zuko."
)

TEAM_AVATAR = make_creature(
    name="Team Avatar",
    power=4,
    toughness=4,
    mana_cost="{W}{U}{B}{R}{G}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    subtypes={"Human", "Avatar", "Ally"},
    supertypes={"Legendary"},
    text="Flying, vigilance, trample. When Team Avatar enters, choose any number: Airbend up to one creature; waterbend (tap target creature, it doesn't untap); earthbend 3; firebend 3."
)

TY_LEE_ACROBAT = make_creature(
    name="Ty Lee, Acrobat",
    power=2,
    toughness=2,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Double strike. Whenever Ty Lee deals combat damage to a creature, tap that creature. It doesn't untap during its controller's next untap step."
)


# =============================================================================
# ARTIFACT CARDS
# =============================================================================

AANG_STATUE = make_artifact(
    name="Aang Statue",
    mana_cost="{3}",
    text="When Aang Statue enters, create a 1/1 white Ally creature token. {T}: Add one mana of any color. Spend this mana only to cast Ally spells."
)

EARTH_KINGDOM_TANK = make_artifact(
    name="Earth Kingdom Tank",
    mana_cost="{4}",
    subtypes={"Vehicle"},
    text="Trample. Earthbend 1 — Whenever this Vehicle attacks, put a +1/+1 counter on target land creature you control. Crew 2"
)

METEORITE_SWORD = make_artifact(
    name="Meteorite Sword",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +2/+1 and has first strike. Whenever equipped creature deals combat damage to a player, you may search your library for an Equipment card, reveal it, put it into your hand, then shuffle. Equip {2}"
)

SPIRIT_OASIS = make_artifact(
    name="Spirit Oasis",
    mana_cost="{3}",
    text="At the beginning of your upkeep, you gain 1 life. {T}: Add one mana of any color. {3}, {T}, Sacrifice Spirit Oasis: Create a 4/4 blue Spirit creature token with flying."
)


# =============================================================================
# LAND CARDS
# =============================================================================

AIR_TEMPLE = make_land(
    name="Air Temple",
    text="Air Temple enters tapped. {T}: Add {W}. {T}: Add {U}. Activate only if you control an Ally."
)

BA_SING_SE = make_land(
    name="Ba Sing Se",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add {G} or {W}. Activate only if you control a creature with a +1/+1 counter on it."
)

FIRE_NATION_CAPITAL = make_land(
    name="Fire Nation Capital",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add {B} or {R}. Activate only if a source you controlled dealt damage to an opponent this turn."
)

SPIRIT_WORLD_GATE = make_land(
    name="Spirit World Gate",
    text="Spirit World Gate enters tapped. When Spirit World Gate enters, scry 1. {T}: Add one mana of any color."
)

WATER_TRIBE_VILLAGE = make_land(
    name="Water Tribe Village",
    text="Water Tribe Village enters tapped. {T}: Add {W} or {U}."
)

FIRE_NATION_OUTPOST = make_land(
    name="Fire Nation Outpost",
    text="Fire Nation Outpost enters tapped. {T}: Add {B} or {R}."
)

EARTH_KINGDOM_FORTRESS = make_land(
    name="Earth Kingdom Fortress",
    text="Earth Kingdom Fortress enters tapped. {T}: Add {G}. {1}{G}, {T}, Sacrifice this land: Earthbend 2."
)

OMASHU = make_land(
    name="Omashu",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add {G}. Activate only if you control a legendary creature."
)

EMBER_ISLAND = make_land(
    name="Ember Island",
    text="Ember Island enters tapped. {T}: Add {R}. Firebend 1 — {3}{R}, {T}: Put a +1/+1 counter on target creature you control."
)

FOG_OF_LOST_SOULS = make_land(
    name="Fog of Lost Souls",
    text="{T}: Add {C}. {2}, {T}: Target creature gets -2/-0 until end of turn."
)


# =============================================================================
# ADDITIONAL WHITE CARDS
# =============================================================================

KYOSHI_ISLAND_DEFENDER = make_creature(
    name="Kyoshi Island Defender",
    power=2,
    toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Warrior", "Ally"},
    text="First strike. Other Warrior creatures you control have vigilance."
)

MEELO_THE_TROUBLEMAKER = make_creature(
    name="Meelo, the Troublemaker",
    power=1,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk", "Ally"},
    supertypes={"Legendary"},
    text="Airbend — When Meelo enters or attacks, you may airbend target creature with power 2 or less."
)

MOMO_LOYAL_COMPANION = make_creature(
    name="Momo, Loyal Companion",
    power=1,
    toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Bat", "Lemur", "Ally"},
    supertypes={"Legendary"},
    text="Flying. Whenever another Ally you control enters, scry 1."
)

AIRBENDER_INITIATE = make_creature(
    name="Airbender Initiate",
    power=1,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk"},
    text="Flying. Whenever you cast a Lesson spell, Airbender Initiate gets +1/+1 until end of turn."
)

CABBAGE_MERCHANT = make_creature(
    name="Cabbage Merchant",
    power=0,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Peasant"},
    text="When Cabbage Merchant dies, create three Food tokens. 'MY CABBAGES!'"
)

MONASTIC_DISCIPLINE = make_instant(
    name="Monastic Discipline",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Lesson — Target creature you control gains indestructible until end of turn. Untap it."
)

WINDS_OF_CHANGE = make_sorcery(
    name="Winds of Change",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Airbend up to two target creatures."
)

AVATAR_KORRA_SPIRIT = make_creature(
    name="Avatar Korra, Spirit Bridge",
    power=3,
    toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Avatar", "Ally"},
    supertypes={"Legendary"},
    text="Flying. Whenever Avatar Korra attacks, you may airbend or waterbend target creature."
)

PEACEFUL_SANCTUARY = make_enchantment(
    name="Peaceful Sanctuary",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Creatures can't attack you unless their controller pays {2} for each creature attacking you."
)

GURU_PATHIK = make_creature(
    name="Guru Pathik",
    power=0,
    toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk"},
    supertypes={"Legendary"},
    text="{T}: Target Avatar you control gains hexproof and lifelink until end of turn. Scry 1."
)

LION_TURTLE_BLESSING = make_instant(
    name="Lion Turtle Blessing",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Target creature becomes an Avatar in addition to its other types and gains flying, first strike, vigilance, trample, and lifelink until end of turn."
)

GYATSO_WISE_MENTOR = make_creature(
    name="Gyatso, Wise Mentor",
    power=2,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk", "Ally"},
    supertypes={"Legendary"},
    text="Whenever you cast a Lesson spell, create a 1/1 white Ally creature token."
)


# =============================================================================
# ADDITIONAL BLUE CARDS
# =============================================================================

HAMA_BLOODBENDER = make_creature(
    name="Hama, Bloodbender",
    power=2,
    toughness=3,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Waterbend — {2}{U}{B}, {T}: Gain control of target creature until end of turn. Untap it. It gains haste."
)

SERPENTS_PASS_HORROR = make_creature(
    name="Serpent's Pass Horror",
    power=6,
    toughness=6,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Serpent"},
    text="Hexproof. Serpent's Pass Horror can't be blocked except by creatures with flying."
)

SOUTHERN_WATER_TRIBE = make_creature(
    name="Southern Water Tribe",
    power=1,
    toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard", "Ally"},
    text="When this creature enters, draw a card, then discard a card."
)

FOGGY_SWAMP_WATERBENDER = make_creature(
    name="Foggy Swamp Waterbender",
    power=3,
    toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Flash. When this creature enters, waterbend up to one target creature. (Tap it. It doesn't untap during its controller's next untap step.)"
)

SPIRIT_FOX = make_creature(
    name="Spirit Fox",
    power=2,
    toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Fox", "Spirit"},
    text="When Spirit Fox enters, scry 2."
)

UNAGI_ATTACK = make_instant(
    name="Unagi Attack",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Create a 4/3 blue Serpent creature token with 'When this creature dies, draw a card.'"
)

WISDOM_OF_AGES = make_sorcery(
    name="Wisdom of Ages",
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    text="Draw three cards. If you control an Avatar, draw four cards instead."
)

AVATAR_ROKU = make_creature(
    name="Avatar Roku",
    power=4,
    toughness=4,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Avatar"},
    supertypes={"Legendary"},
    text="Flying. Firebend 2. When Avatar Roku enters, you may return target instant or sorcery card from your graveyard to your hand."
)

SPIRIT_WORLD_WANDERER = make_creature(
    name="Spirit World Wanderer",
    power=2,
    toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Flying. Whenever Spirit World Wanderer deals combat damage to a player, scry 2."
)

WATER_TRIBE_HEALER = make_creature(
    name="Water Tribe Healer",
    power=1,
    toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Cleric", "Ally"},
    text="{T}: Prevent the next 2 damage that would be dealt to target creature this turn."
)

TUI_AND_LA = make_creature(
    name="Tui and La",
    power=4,
    toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Fish", "Spirit"},
    supertypes={"Legendary"},
    text="Hexproof. Waterbend — Whenever a creature enters under your control, you may tap or untap target permanent."
)

MIST_VEIL = make_instant(
    name="Mist Veil",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature you control gains hexproof until end of turn. Draw a card."
)


# =============================================================================
# ADDITIONAL BLACK CARDS
# =============================================================================

ZHAO_THE_CONQUEROR = make_creature(
    name="Zhao, the Conqueror",
    power=4,
    toughness=3,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Menace. Firebend 2. Whenever Zhao attacks, destroy target creature with the least toughness among creatures you don't control."
)

DAI_LI_ENFORCER = make_creature(
    name="Dai Li Enforcer",
    power=2,
    toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    text="Earthbend 1. Whenever this creature attacks, target opponent discards a card."
)

SPIRIT_CORRUPTION = make_enchantment(
    name="Spirit Corruption",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Enchant creature. Enchanted creature gets -3/-3. When enchanted creature dies, create a 2/2 black Spirit creature token with flying."
)

BLOODBENDING_LESSON = make_instant(
    name="Bloodbending Lesson",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Lesson — Gain control of target creature until end of turn. Untap it. It gains haste and 'At end of turn, sacrifice this creature.'"
)

SHADOW_OF_THE_PAST = make_sorcery(
    name="Shadow of the Past",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Return up to two target creature cards from your graveyard to your hand. You lose 2 life."
)

FIRE_NATION_PRISON = make_enchantment(
    name="Fire Nation Prison",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="When Fire Nation Prison enters, exile target creature an opponent controls until Fire Nation Prison leaves the battlefield. That creature's controller creates a Food token."
)

CRUEL_AMBITION = make_sorcery(
    name="Cruel Ambition",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Each opponent sacrifices a creature. You draw a card for each creature sacrificed this way."
)

SPIRIT_OF_REVENGE = make_creature(
    name="Spirit of Revenge",
    power=3,
    toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Flying, deathtouch. When Spirit of Revenge dies, each opponent loses 2 life."
)

WAR_BALLOON_CREW = make_creature(
    name="War Balloon Crew",
    power=2,
    toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    text="Flying. Firebend 1. When War Balloon Crew dies, each opponent loses 2 life."
)

LAKE_LAOGAI = make_enchantment(
    name="Lake Laogai",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="When Lake Laogai enters, exile target creature. For as long as Lake Laogai remains on the battlefield, that creature's controller may cast that card. When they do, sacrifice Lake Laogai."
)


# =============================================================================
# ADDITIONAL RED CARDS
# =============================================================================

FIRE_NATION_COMMANDER = make_creature(
    name="Fire Nation Commander",
    power=4,
    toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="Firebend 2. Other creatures you control have firebend 1."
)

IROH_DRAGON_OF_THE_WEST = make_creature(
    name="Iroh, Dragon of the West",
    power=4,
    toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior", "Ally"},
    supertypes={"Legendary"},
    text="Firebend 3. At the beginning of your upkeep, you may pay {R}. If you do, Iroh deals 2 damage to any target."
)

LIGHTNING_REDIRECTION = make_instant(
    name="Lightning Redirection",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Lesson — Change the target of target spell or ability with a single target to a new target."
)

SOZINS_COMET = make_sorcery(
    name="Sozin's Comet",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Until end of turn, if a red source you control would deal damage, it deals double that damage instead. Creatures you control with firebend get +3/+0 until end of turn."
)

AGNI_KAI = make_sorcery(
    name="Agni Kai",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature you control fights target creature you don't control. If your creature wins, firebend 2."
)

DRAGON_DANCE = make_instant(
    name="Dragon Dance",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Lesson — Target creature gets +3/+0 and gains first strike until end of turn. If it's an Avatar, it also gains trample."
)

RAN_AND_SHAW = make_creature(
    name="Ran and Shaw",
    power=6,
    toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    supertypes={"Legendary"},
    text="Flying. Firebend 4. When Ran and Shaw enters, you may have it deal 4 damage divided as you choose among any number of targets."
)

FIRE_LILY = make_creature(
    name="Fire Lily",
    power=1,
    toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Haste. Firebend 1. At the beginning of your end step, sacrifice Fire Lily."
)

VOLCANIC_ERUPTION = make_sorcery(
    name="Volcanic Eruption",
    mana_cost="{X}{R}{R}",
    colors={Color.RED},
    text="Volcanic Eruption deals X damage to each creature without flying. Earthbend X."
)

PHOENIX_REBORN = make_creature(
    name="Phoenix Reborn",
    power=3,
    toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Phoenix"},
    text="Flying, haste. When Phoenix Reborn dies, you may pay {2}{R}. If you do, return it to the battlefield at the beginning of the next end step."
)


# =============================================================================
# ADDITIONAL GREEN CARDS
# =============================================================================

SWAMPBENDER = make_creature(
    name="Swampbender",
    power=3,
    toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Wizard"},
    text="Reach. When Swampbender enters, create a 2/2 green Plant creature token."
)

FLYING_BISON_HERD = make_creature(
    name="Flying Bison Herd",
    power=5,
    toughness=5,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Bison"},
    text="Flying. When Flying Bison Herd enters, create two 1/1 white Ally creature tokens with flying."
)

AVATAR_KYOSHI = make_creature(
    name="Avatar Kyoshi",
    power=4,
    toughness=5,
    mana_cost="{3}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Avatar", "Warrior"},
    supertypes={"Legendary"},
    text="Vigilance. Earthbend 3. When Avatar Kyoshi enters, create a legendary artifact token named Kyoshi's Fans with '{T}: Target creature you control gains +2/+0 and first strike until end of turn.'"
)

FOREST_SPIRIT = make_creature(
    name="Forest Spirit",
    power=4,
    toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Treefolk"},
    text="Reach. When Forest Spirit enters, search your library for a basic land card, reveal it, put it into your hand, then shuffle."
)

CATGATOR = make_creature(
    name="Catgator",
    power=3,
    toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Cat", "Crocodile"},
    text="Whenever Catgator deals combat damage to a player, draw a card."
)

SWAMP_GIANT = make_creature(
    name="Swamp Giant",
    power=7,
    toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Giant"},
    text="Trample. When Swamp Giant enters, you may return target creature card from your graveyard to your hand."
)

EARTH_KINGDOM_FARMER = make_creature(
    name="Earth Kingdom Farmer",
    power=1,
    toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Peasant"},
    text="{T}: Add {G}. {2}{G}, {T}: Earthbend 1."
)

NATURAL_HARMONY = make_enchantment(
    name="Natural Harmony",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Whenever a land enters under your control, you gain 1 life. Whenever a creature with a +1/+1 counter enters under your control, draw a card."
)

PRIMAL_FURY = make_instant(
    name="Primal Fury",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Lesson — Target creature gets +3/+3 and gains trample until end of turn."
)

PLATYPUS_BEAR = make_creature(
    name="Platypus Bear",
    power=4,
    toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Bear", "Platypus"},
    text="Trample. Whenever Platypus Bear deals combat damage to a player, create a Food token."
)

SPIRIT_VINE = make_creature(
    name="Spirit Vine",
    power=0,
    toughness=4,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Spirit"},
    text="Defender. {T}: Add one mana of any color. {4}{G}, {T}: Put three +1/+1 counters on Spirit Vine. It loses defender."
)


# =============================================================================
# ADDITIONAL MULTICOLOR CARDS
# =============================================================================

SOKKA_AND_SUKI = make_creature(
    name="Sokka and Suki",
    power=3,
    toughness=4,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Warrior", "Ally"},
    supertypes={"Legendary"},
    text="First strike, vigilance. Whenever Sokka and Suki attacks, up to one other target attacking Warrior gets +2/+2 until end of turn."
)

ZUKO_AND_IROH = make_creature(
    name="Zuko and Iroh",
    power=4,
    toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Noble", "Ally"},
    supertypes={"Legendary"},
    text="Firebend 2. At the beginning of your end step, if you dealt damage to an opponent this turn, draw a card and you gain 2 life."
)

KATARA_AND_AANG = make_creature(
    name="Katara and Aang",
    power=3,
    toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Avatar", "Ally"},
    supertypes={"Legendary"},
    text="Flying. Whenever Katara and Aang attacks, choose one — Airbend target creature; or waterbend target creature."
)

AZULA_AND_DAI_LI = make_creature(
    name="Azula and Dai Li",
    power=4,
    toughness=4,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Menace. Earthbend 2. Whenever Azula and Dai Li attacks, target opponent sacrifices a creature."
)

SPIRIT_WORLD_PORTAL = make_enchantment(
    name="Spirit World Portal",
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    text="At the beginning of your upkeep, scry 1. {2}{G}{U}: Create a 2/2 blue Spirit creature token with flying."
)

FIRELORD_SOZIN = make_creature(
    name="Firelord Sozin",
    power=5,
    toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Firebend 3. Menace. When Firelord Sozin enters, destroy target nonland permanent an opponent controls with mana value 3 or less."
)

AVATAR_YANGCHEN = make_creature(
    name="Avatar Yangchen",
    power=3,
    toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Avatar"},
    supertypes={"Legendary"},
    text="Flying. Airbend — Whenever Avatar Yangchen attacks, airbend up to two target creatures."
)

AVATAR_KURUK = make_creature(
    name="Avatar Kuruk",
    power=4,
    toughness=3,
    mana_cost="{2}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Avatar"},
    supertypes={"Legendary"},
    text="Waterbend — Whenever Avatar Kuruk attacks, you may tap or untap up to two target permanents."
)

LION_TURTLE = make_creature(
    name="Lion Turtle",
    power=8,
    toughness=8,
    mana_cost="{6}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Turtle", "Spirit"},
    supertypes={"Legendary"},
    text="Hexproof. Islandwalk. When Lion Turtle enters, target creature becomes an Avatar in addition to its other types and gains hexproof until end of turn."
)

KOIZILLA = make_creature(
    name="Koizilla",
    power=10,
    toughness=10,
    mana_cost="{5}{U}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Avatar", "Spirit", "Fish"},
    supertypes={"Legendary"},
    text="This spell costs {2} less to cast if you control an Avatar. Trample, hexproof. When Koizilla enters, return all other creatures to their owners' hands."
)

HEIBAIFACED_SPIRIT = make_creature(
    name="Hei Bai, Forest Spirit",
    power=4,
    toughness=4,
    mana_cost="{3}{G}{B}",
    colors={Color.GREEN, Color.BLACK},
    subtypes={"Spirit", "Panda"},
    supertypes={"Legendary"},
    text="When Hei Bai enters, choose one — Create two 1/1 green Sapling creature tokens; or destroy target creature with mana value 3 or less."
)


# =============================================================================
# ADDITIONAL ARTIFACTS
# =============================================================================

WAR_BALLOON = make_artifact(
    name="War Balloon",
    mana_cost="{4}",
    subtypes={"Vehicle"},
    text="Flying. Whenever War Balloon attacks, firebend 1. Crew 2"
)

AZULAS_CROWN = make_artifact(
    name="Azula's Crown",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +2/+1 and has menace. Whenever equipped creature deals combat damage to a player, that player discards a card. Equip {3}"
)

WATER_POUCH = make_artifact(
    name="Water Pouch",
    mana_cost="{1}",
    text="Water Pouch enters with three water counters on it. {T}, Remove a water counter: Add {U}. {T}, Remove a water counter: Target creature doesn't untap during its controller's next untap step."
)

FIRE_NATION_HELM = make_artifact(
    name="Fire Nation Helm",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +1/+1 and has firebend 1. Equip {2}"
)

AANGS_STAFF = make_artifact(
    name="Aang's Staff",
    mana_cost="{3}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    text="Equipped creature gets +2/+0 and has flying. Whenever equipped creature attacks, airbend target creature. Equip Avatar {1}. Equip {3}"
)

TOPHS_BRACELET = make_artifact(
    name="Toph's Bracelet",
    mana_cost="{2}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    text="Equipped creature gets +1/+2 and has earthbend 2. Equip {2}"
)

SUNSTONE = make_artifact(
    name="Sunstone",
    mana_cost="{3}",
    text="{T}: Add {R}{R}. {3}, {T}: Firebending Lesson deals 3 damage to any target."
)

MOONSTONE = make_artifact(
    name="Moonstone",
    mana_cost="{3}",
    text="{T}: Add {U}{U}. {3}, {T}: Tap target creature. It doesn't untap during its controller's next untap step."
)

LOTUS_TILE = make_artifact(
    name="Lotus Tile",
    mana_cost="{2}",
    text="When Lotus Tile enters, scry 2. {T}: Add one mana of any color. {2}, {T}, Sacrifice Lotus Tile: Draw a card."
)

DRILL = make_artifact(
    name="The Drill",
    mana_cost="{6}",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
    text="Trample. Whenever The Drill deals combat damage to a player, destroy target land that player controls. Crew 4"
)


# =============================================================================
# ADDITIONAL INSTANTS AND SORCERIES
# =============================================================================

BLUE_SPIRIT_STRIKE = make_instant(
    name="Blue Spirit Strike",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature you control gets +2/+0 and gains deathtouch until end of turn. If that creature is an Ally, it also gains hexproof until end of turn."
)

SIEGE_OF_THE_NORTH = make_sorcery(
    name="Siege of the North",
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Destroy all creatures. Then firebend 3 for each creature destroyed this way."
)

CROSSROADS_OF_DESTINY = make_instant(
    name="Crossroads of Destiny",
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    text="Choose one — Exile target creature; or return target creature card from your graveyard to the battlefield."
)

FINAL_AGNI_KAI = make_sorcery(
    name="Final Agni Kai",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Two target creatures fight each other. Then if a creature died this way, firebend 3."
)

BLOODBENDING = make_instant(
    name="Bloodbending",
    mana_cost="{3}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    text="Gain control of target creature until end of turn. Untap it. It gains haste. At end of turn, tap it. It doesn't untap during its controller's next untap step."
)

ECLIPSE_DARKNESS = make_instant(
    name="Eclipse Darkness",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Until end of turn, all creatures lose all abilities and become black."
)

AVATAR_STATE_FURY = make_instant(
    name="Avatar State Fury",
    mana_cost="{W}{U}{B}{R}{G}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    text="Target Avatar you control gains +5/+5 and gains flying, first strike, vigilance, trample, lifelink, and hexproof until end of turn. It can't be blocked this turn."
)

INVASION_DAY = make_sorcery(
    name="Invasion Day",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Create three 1/1 white Ally creature tokens. Then put a +1/+1 counter on each Ally you control."
)

TUNNEL_THROUGH = make_instant(
    name="Tunnel Through",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Earthbend 2. Target creature you control can't be blocked this turn."
)

SPIRIT_BOMB = make_sorcery(
    name="Spirit Bomb",
    mana_cost="{X}{U}{U}",
    colors={Color.BLUE},
    text="Return X target nonland permanents to their owners' hands. If X is 5 or more, draw a card for each permanent returned this way."
)


# =============================================================================
# MORE WHITE CARDS
# =============================================================================

JINORA_SPIRITUAL_GUIDE = make_creature(
    name="Jinora, Spiritual Guide",
    power=2,
    toughness=2,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Monk", "Ally"},
    supertypes={"Legendary"},
    text="Flying. Whenever you cast a Lesson spell, scry 2, then draw a card."
)

KORRA_AVATAR_UNLEASHED = make_creature(
    name="Korra, Avatar Unleashed",
    power=4,
    toughness=4,
    mana_cost="{2}{W}{U}{R}",
    colors={Color.WHITE, Color.BLUE, Color.RED},
    subtypes={"Human", "Avatar", "Ally"},
    supertypes={"Legendary"},
    text="Flying, vigilance. Whenever Korra attacks, choose any number: Airbend target creature; waterbend target creature; firebend 2."
)

AIRBENDING_MASTER = make_creature(
    name="Airbending Master",
    power=2,
    toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk"},
    text="Flying. Airbend — At the beginning of your end step, if you returned a permanent to its owner's hand this turn, draw a card."
)

NOMAD_MUSICIAN = make_creature(
    name="Nomad Musician",
    power=1,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Bard", "Ally"},
    text="When Nomad Musician enters, you gain 2 life for each Ally you control."
)

AIR_ACOLYTE = make_creature(
    name="Air Acolyte",
    power=1,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk"},
    text="Lifelink. {2}{W}: Air Acolyte gains flying until end of turn."
)

RESTORATION_RITUAL = make_sorcery(
    name="Restoration Ritual",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Return up to two target permanent cards with mana value 3 or less from your graveyard to the battlefield."
)

SPIRITUAL_GUIDANCE = make_enchantment(
    name="Spiritual Guidance",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Whenever a creature you control attacks alone, it gets +2/+2 and gains lifelink until end of turn."
)


# =============================================================================
# MORE BLUE CARDS
# =============================================================================

KANNA_GRAN_GRAN = make_creature(
    name="Kanna, Gran Gran",
    power=1,
    toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Advisor", "Ally"},
    supertypes={"Legendary"},
    text="Whenever another Ally enters under your control, scry 1. {T}: Target Ally you control gains hexproof until end of turn."
)

OCEAN_DEPTHS_LEVIATHAN = make_creature(
    name="Ocean Depths Leviathan",
    power=8,
    toughness=8,
    mana_cost="{6}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Leviathan"},
    text="This spell costs {1} less to cast for each Island you control. Hexproof. When Ocean Depths Leviathan enters, return up to two target nonland permanents to their owners' hands."
)

THOUGHT_MANIPULATION = make_instant(
    name="Thought Manipulation",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell. Its controller draws a card."
)

SPIRIT_VISION = make_sorcery(
    name="Spirit Vision",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Look at the top five cards of your library. Put two of them into your hand and the rest on the bottom of your library in any order."
)

WATER_WHIP = make_instant(
    name="Water Whip",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Waterbend target creature. (Tap it. It doesn't untap during its controller's next untap step.)"
)

CRASHING_WAVES = make_sorcery(
    name="Crashing Waves",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Return up to two target nonland permanents to their owners' hands. Draw a card."
)

ICE_SHIELD = make_instant(
    name="Ice Shield",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Target creature you control gets +0/+4 and gains hexproof until end of turn."
)


# =============================================================================
# MORE BLACK CARDS
# =============================================================================

KUVIRA_GREAT_UNITER = make_creature(
    name="Kuvira, Great Uniter",
    power=4,
    toughness=4,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Earthbend 2. Menace. Whenever Kuvira attacks, you may sacrifice another creature. If you do, Kuvira gets +3/+3 and gains indestructible until end of turn."
)

SHADOW_OPERATIVE = make_creature(
    name="Shadow Operative",
    power=2,
    toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Assassin"},
    text="Deathtouch. When Shadow Operative deals combat damage to a player, that player discards a card."
)

DARK_SPIRITS_BLESSING = make_enchantment(
    name="Dark Spirit's Blessing",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Enchanted creature gets +2/+1 and has deathtouch and 'When this creature dies, each opponent loses 2 life.'"
)

MIND_BREAK = make_sorcery(
    name="Mind Break",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Target opponent reveals their hand. You choose a nonland card from it. That player discards that card. You lose life equal to that card's mana value."
)

CORRUPT_OFFICIAL = make_creature(
    name="Corrupt Official",
    power=2,
    toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Advisor"},
    text="When Corrupt Official enters, target opponent sacrifices a creature with the least toughness among creatures they control."
)

DEATH_BY_LIGHTNING = make_instant(
    name="Death by Lightning",
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Destroy target creature. Firebend 2."
)

PRISON_BREAK = make_sorcery(
    name="Prison Break",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Return up to two target creature cards from your graveyard to your hand. You gain 2 life for each card returned this way."
)


# =============================================================================
# MORE RED CARDS
# =============================================================================

PIANDAO_SWORD_MASTER = make_creature(
    name="Piandao, Sword Master",
    power=3,
    toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior", "Ally"},
    supertypes={"Legendary"},
    text="First strike. Whenever Piandao attacks, you may discard a card. If you do, draw two cards."
)

FIRE_NATION_SOLDIER = make_creature(
    name="Fire Nation Soldier",
    power=2,
    toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="Firebend 1."
)

RAGE_OF_FIRE = make_instant(
    name="Rage of Fire",
    mana_cost="{X}{R}{R}",
    colors={Color.RED},
    text="Rage of Fire deals X damage to any target. If X is 5 or more, firebend X."
)

LIGHTNING_BOLT_LESSON = make_instant(
    name="Lightning Bolt Lesson",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Lesson — Lightning Bolt Lesson deals 3 damage to any target."
)

FIRE_WALL = make_enchantment(
    name="Fire Wall",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Creatures can't attack you unless their controller pays {2} for each creature attacking you. Whenever an opponent attacks you, Fire Wall deals 1 damage to each attacking creature."
)

COMET_ENHANCED = make_instant(
    name="Comet Enhanced",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains first strike until end of turn. That creature gains trample until end of turn if you control an Avatar."
)

CALDERA_ERUPTION = make_sorcery(
    name="Caldera Eruption",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Caldera Eruption deals 5 damage to each creature. Firebend 3."
)


# =============================================================================
# MORE GREEN CARDS
# =============================================================================

DUE_THE_EARTH_SPIRIT = make_creature(
    name="Due, the Earth Spirit",
    power=3,
    toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Badger"},
    supertypes={"Legendary"},
    text="Hexproof. Earthbend 2. Whenever you put one or more +1/+1 counters on a land, draw a card."
)

FOREST_GUARDIAN = make_creature(
    name="Forest Guardian",
    power=5,
    toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Bear"},
    text="Trample. Reach. When Forest Guardian enters, search your library for a basic land card, put it onto the battlefield tapped, then shuffle."
)

OASIS_HERMIT = make_creature(
    name="Oasis Hermit",
    power=1,
    toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Druid"},
    text="{T}: Add {G}. {T}: Target land you control becomes a 0/0 creature with haste that's still a land. Put a +1/+1 counter on it."
)

WILD_GROWTH = make_enchantment(
    name="Wild Growth",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Enchant land. Whenever enchanted land is tapped for mana, its controller adds an additional {G}."
)

BEAST_SUMMONS = make_sorcery(
    name="Beast Summons",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Create two 3/3 green Beast creature tokens with trample."
)

NATURE_RECLAMATION = make_instant(
    name="Nature Reclamation",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Destroy target artifact or enchantment. You gain 3 life."
)

STANDING_TALL = make_instant(
    name="Standing Tall",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +2/+2 until end of turn. If it has a +1/+1 counter on it, it also gains trample until end of turn."
)


# =============================================================================
# MORE MULTICOLOR CARDS
# =============================================================================

MAI_AND_TY_LEE = make_creature(
    name="Mai and Ty Lee",
    power=3,
    toughness=3,
    mana_cost="{1}{R}{W}{B}",
    colors={Color.RED, Color.WHITE, Color.BLACK},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="First strike, deathtouch. Whenever Mai and Ty Lee deals combat damage to a player, that player discards a card and you draw a card."
)

AMON_THE_EQUALIST = make_creature(
    name="Amon, the Equalist",
    power=4,
    toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="Flash. When Amon enters, target creature loses all abilities until your next turn. {2}{U}{B}: Target creature loses all abilities until your next turn."
)

UNALAQ_DARK_AVATAR = make_creature(
    name="Unalaq, Dark Avatar",
    power=5,
    toughness=5,
    mana_cost="{3}{U}{B}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Avatar"},
    supertypes={"Legendary"},
    text="Flying. Waterbend — At the beginning of your upkeep, tap up to one target creature. It doesn't untap during its controller's next untap step. When Unalaq dies, each opponent loses 5 life."
)

SPIRIT_OF_RAAVA = make_creature(
    name="Spirit of Raava",
    power=5,
    toughness=6,
    mana_cost="{4}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    text="Flying, vigilance. Other Spirits you control get +1/+1. At the beginning of your end step, if you gained life this turn, create a 2/2 white Spirit creature token with flying."
)

SPIRIT_OF_VAATU = make_creature(
    name="Spirit of Vaatu",
    power=6,
    toughness=5,
    mana_cost="{4}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    text="Flying, menace. At the beginning of your end step, Spirit of Vaatu deals 2 damage to each opponent. If an opponent lost life this turn, draw a card."
)

RED_LOTUS = make_creature(
    name="Red Lotus",
    power=3,
    toughness=3,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Assassin"},
    text="Haste, menace. Whenever Red Lotus deals combat damage to a player, that player sacrifices a permanent."
)

WHITE_LOTUS_GRANDMASTER = make_creature(
    name="White Lotus Grandmaster",
    power=3,
    toughness=4,
    mana_cost="{W}{U}{B}{R}{G}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    subtypes={"Human", "Monk", "Ally"},
    supertypes={"Legendary"},
    text="Vigilance, hexproof. Other Allies you control get +1/+1 and have vigilance. At the beginning of your upkeep, you may airbend, waterbend, earthbend 2, or firebend 2."
)


# =============================================================================
# MORE ARTIFACTS
# =============================================================================

BOOMERANG_ARTIFACT = make_artifact(
    name="Sokka's Boomerang",
    mana_cost="{2}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    text="Equipped creature gets +1/+1. Whenever equipped creature deals combat damage to a player, return up to one target nonland permanent to its owner's hand. Equip {1}"
)

CACTUS_JUICE = make_artifact(
    name="Cactus Juice",
    mana_cost="{1}",
    text="{T}, Sacrifice Cactus Juice: Draw two cards, then discard a card at random. 'It's the quenchiest!'"
)

FIREBENDING_SCROLL = make_artifact(
    name="Firebending Scroll",
    mana_cost="{2}",
    text="When Firebending Scroll enters, firebend 1. {2}, {T}, Sacrifice Firebending Scroll: Firebend 2 and draw a card."
)

EARTHBENDING_SCROLL = make_artifact(
    name="Earthbending Scroll",
    mana_cost="{2}",
    text="When Earthbending Scroll enters, earthbend 1. {2}, {T}, Sacrifice Earthbending Scroll: Earthbend 2 and draw a card."
)

WATERBENDING_SCROLL = make_artifact(
    name="Waterbending Scroll",
    mana_cost="{2}",
    text="When Waterbending Scroll enters, waterbend target creature. {2}, {T}, Sacrifice Waterbending Scroll: Waterbend up to two target creatures. Draw a card."
)

AIRBENDING_SCROLL = make_artifact(
    name="Airbending Scroll",
    mana_cost="{2}",
    text="When Airbending Scroll enters, airbend target creature. {2}, {T}, Sacrifice Airbending Scroll: Airbend up to two target creatures. Draw a card."
)

SUBMARINE = make_artifact(
    name="Fire Nation Submarine",
    mana_cost="{5}",
    subtypes={"Vehicle"},
    text="Islandwalk. Firebend 2 — Whenever this Vehicle deals combat damage to a player, draw a card. Crew 3"
)

CHI_BLOCKER_GLOVES = make_artifact(
    name="Chi Blocker Gloves",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +1/+0 and has 'Whenever this creature deals combat damage to a creature, tap that creature. It doesn't untap during its controller's next untap step and loses all abilities until your next turn.' Equip {2}"
)


# =============================================================================
# MORE LANDS
# =============================================================================

SOUTHERN_AIR_TEMPLE = make_land(
    name="Southern Air Temple",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add {W}. Activate only if you control a creature with flying."
)

WESTERN_AIR_TEMPLE = make_land(
    name="Western Air Temple",
    text="Western Air Temple enters tapped. {T}: Add {W} or {U}. {2}, {T}: Target creature gains flying until end of turn."
)

KYOSHI_ISLAND = make_land(
    name="Kyoshi Island",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add {G} or {W}. Activate only if you control a Warrior."
)

BOILING_ROCK_PRISON = make_land(
    name="Boiling Rock Prison",
    text="Boiling Rock Prison enters tapped. {T}: Add {B} or {R}. {3}, {T}: Target creature can't attack or block this turn."
)

SERPENTS_PASS = make_land(
    name="Serpent's Pass",
    text="Serpent's Pass enters tapped. {T}: Add {U} or {G}. {4}, {T}: Create a 4/3 blue Serpent creature token."
)

FOGGY_SWAMP = make_land(
    name="Foggy Swamp",
    text="Foggy Swamp enters tapped. {T}: Add {U} or {G}. {2}, {T}: Create a 2/2 green Plant creature token."
)

SI_WONG_DESERT = make_land(
    name="Si Wong Desert",
    text="{T}: Add {C}. {2}, {T}: Add two mana of any one color. You lose 1 life."
)

NORTHERN_WATER_TRIBE_CAPITAL = make_land(
    name="Northern Water Tribe Capital",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add {U}{U}. Activate only if you control two or more creatures with waterbend."
)


# =============================================================================
# LEGEND OF KORRA ERA CARDS
# =============================================================================

REPUBLIC_CITY = make_land(
    name="Republic City",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add one mana of any color. Activate only if you control creatures of three or more different colors."
)

PRO_BENDING_ARENA = make_land(
    name="Pro-Bending Arena",
    text="Pro-Bending Arena enters tapped. {T}: Add {R}, {U}, or {G}. {3}, {T}: Target creature you control fights target creature an opponent controls."
)

MAKO_FIREBENDER = make_creature(
    name="Mako, Firebender",
    power=3,
    toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard", "Ally"},
    supertypes={"Legendary"},
    text="Firebend 2. Whenever Mako deals combat damage to a player, you may pay {R}. If you do, Mako deals 2 damage to any target."
)

BOLIN_LAVABENDER = make_creature(
    name="Bolin, Lavabender",
    power=3,
    toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Wizard", "Ally"},
    supertypes={"Legendary"},
    text="Earthbend 2. When Bolin enters, he deals 3 damage to target creature you don't control. Whenever Bolin attacks, earthbend 1."
)

ASAMI_SATO = make_creature(
    name="Asami Sato",
    power=2,
    toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Artificer", "Ally"},
    supertypes={"Legendary"},
    text="Artifacts you control have '{T}: Add {C}.' {2}, {T}: Create a Clue token."
)

LIN_BEIFONG = make_creature(
    name="Lin Beifong",
    power=4,
    toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Soldier", "Ally"},
    supertypes={"Legendary"},
    text="Vigilance. Earthbend 3. Whenever Lin attacks, target creature an opponent controls can't block this turn."
)

TENZIN_AIRBENDING_MASTER = make_creature(
    name="Tenzin, Airbending Master",
    power=3,
    toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Monk", "Ally"},
    supertypes={"Legendary"},
    text="Flying. Airbend — Whenever Tenzin attacks, airbend up to one target creature. Whenever you cast a Lesson spell, create a 1/1 white Ally creature token with flying."
)

ZAHEER_RED_LOTUS_LEADER = make_creature(
    name="Zaheer, Red Lotus Leader",
    power=4,
    toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Monk"},
    supertypes={"Legendary"},
    text="Flying. Airbend — Whenever Zaheer deals combat damage to a player, that player sacrifices a permanent."
)

PLI_COMBUSTION_BENDER = make_creature(
    name="P'Li, Combustion Bender",
    power=3,
    toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Reach. Firebend 3. {T}: P'Li deals 3 damage to target creature or planeswalker."
)

GHAZAN_LAVABENDER = make_creature(
    name="Ghazan, Lavabender",
    power=4,
    toughness=3,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="When Ghazan enters, destroy target land. Earthbend 2. Ghazan has trample as long as you control four or more lands."
)

MING_HUA_WATERBENDER = make_creature(
    name="Ming-Hua, Armless Waterbender",
    power=3,
    toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Flash. Double strike. Waterbend — {U}: Ming-Hua gets +1/+0 until end of turn."
)

NAGA_POLAR_BEAR_DOG = make_creature(
    name="Naga, Polar Bear Dog",
    power=4,
    toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Dog", "Bear", "Ally"},
    supertypes={"Legendary"},
    text="Vigilance. Whenever Naga attacks, target Ally you control gets +2/+2 until end of turn."
)

PABU_FIRE_FERRET = make_creature(
    name="Pabu the Fire Ferret",
    power=1,
    toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Ferret", "Ally"},
    supertypes={"Legendary"},
    text="Haste. Whenever another Ally enters under your control, Pabu gets +1/+1 until end of turn."
)

VARRICK_INDUSTRIALIST = make_creature(
    name="Varrick, Industrialist",
    power=2,
    toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Artificer"},
    supertypes={"Legendary"},
    text="Whenever an artifact enters under your control, create a Treasure token. {T}: Create a 0/1 colorless Construct artifact creature token."
)

ZHU_LI_ASSISTANT = make_creature(
    name="Zhu Li, Personal Assistant",
    power=1,
    toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Advisor"},
    supertypes={"Legendary"},
    text="Whenever Zhu Li becomes tapped, draw a card, then discard a card. Partner with Varrick, Industrialist."
)

TARRLOK_BLOODBENDER = make_creature(
    name="Tarrlok, Bloodbender",
    power=3,
    toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Wizard", "Noble"},
    supertypes={"Legendary"},
    text="Waterbend — {2}{U}{B}, {T}: Gain control of target creature until end of turn. Untap it. It gains haste."
)

NOATAK_AMON = make_creature(
    name="Noatak (Amon)",
    power=4,
    toughness=4,
    mana_cost="{2}{U}{B}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Flash. When Noatak enters, target creature loses all abilities permanently. Whenever Noatak deals combat damage to a player, choose a creature that player controls. It loses all abilities permanently."
)

EQUALIST_CHI_BLOCKER = make_creature(
    name="Equalist Chi Blocker",
    power=2,
    toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="When Equalist Chi Blocker deals combat damage to a creature, tap that creature. It doesn't untap during its controller's next untap step and loses all abilities until your next turn."
)

MECHA_TANK = make_artifact(
    name="Mecha Tank",
    mana_cost="{4}",
    subtypes={"Vehicle"},
    text="Trample. When Mecha Tank deals combat damage to a player, create a Treasure token. Crew 2"
)

SPIRIT_WILDS = make_enchantment(
    name="Spirit Wilds",
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    text="At the beginning of your upkeep, create a 2/2 green and blue Spirit creature token with flying."
)

HARMONIC_CONVERGENCE = make_sorcery(
    name="Harmonic Convergence",
    mana_cost="{3}{W}{U}{B}{R}{G}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    text="Return all creatures from all graveyards to the battlefield under their owners' control. Each player draws cards equal to the number of creatures they control."
)

AIR_NATION_RESTORED = make_sorcery(
    name="Air Nation Restored",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Create three 1/1 white Ally creature tokens with flying. You gain 3 life for each creature you control with flying."
)

PRO_BENDING_MATCH = make_instant(
    name="Pro-Bending Match",
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    text="Three target creatures you control each deal damage equal to their power to up to three different target creatures you don't control."
)

PLATINUM_MECH_SUIT = make_artifact(
    name="Platinum Mech Suit",
    mana_cost="{6}",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
    text="Trample, hexproof. Whenever Platinum Mech Suit deals combat damage to a player, destroy target land that player controls. Crew 4"
)

SPIRIT_CANNON = make_artifact(
    name="Spirit Cannon",
    mana_cost="{6}",
    supertypes={"Legendary"},
    text="{T}: Spirit Cannon deals 5 damage to any target. If a permanent is destroyed this way, its controller loses 5 life."
)

AIRBENDERS_FLIGHT = make_instant(
    name="Airbender's Flight",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gains flying and hexproof until end of turn. Scry 1."
)

LAVABENDING = make_sorcery(
    name="Lavabending",
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    text="Destroy target land. Earthbend 3."
)

METALBENDING_CABLE = make_artifact(
    name="Metalbending Cable",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +1/+1 and has reach. Whenever equipped creature attacks, tap target creature an opponent controls. Equip {2}"
)

SPIRIT_PORTAL = make_land(
    name="Spirit Portal",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {5}, {T}: Create a 3/3 blue Spirit creature token with flying and hexproof."
)

KORRA_AND_ASAMI = make_creature(
    name="Korra and Asami",
    power=4,
    toughness=4,
    mana_cost="{2}{W}{U}{R}",
    colors={Color.WHITE, Color.BLUE, Color.RED},
    subtypes={"Human", "Avatar", "Ally"},
    supertypes={"Legendary"},
    text="Flying, vigilance. Whenever Korra and Asami attacks, choose two: Airbend target creature; waterbend target creature; create a Treasure token; target Ally gets +2/+2 until end of turn."
)


# =============================================================================
# BASIC LANDS
# =============================================================================

PLAINS_TLA = make_land(
    name="Plains",
    subtypes={"Plains"},
    supertypes={"Basic"},
    text="({T}: Add {W}.)"
)

ISLAND_TLA = make_land(
    name="Island",
    subtypes={"Island"},
    supertypes={"Basic"},
    text="({T}: Add {U}.)"
)

SWAMP_TLA = make_land(
    name="Swamp",
    subtypes={"Swamp"},
    supertypes={"Basic"},
    text="({T}: Add {B}.)"
)

MOUNTAIN_TLA = make_land(
    name="Mountain",
    subtypes={"Mountain"},
    supertypes={"Basic"},
    text="({T}: Add {R}.)"
)

FOREST_TLA = make_land(
    name="Forest",
    subtypes={"Forest"},
    supertypes={"Basic"},
    text="({T}: Add {G}.)"
)


# =============================================================================
# REGISTRY
# =============================================================================

AVATAR_TLA_CARDS = {
    # WHITE
    "Aang's Iceberg": AANGS_ICEBERG,
    "Aang, the Last Airbender": AANG_THE_LAST_AIRBENDER,
    "Airbender Ascension": AIRBENDER_ASCENSION,
    "Airbender's Reversal": AIRBENDERS_REVERSAL,
    "Airbending Lesson": AIRBENDING_LESSON,
    "Appa, Loyal Sky Bison": APPA_LOYAL_SKY_BISON,
    "Appa, Steadfast Guardian": APPA_STEADFAST_GUARDIAN,
    "Avatar Enthusiasts": AVATAR_ENTHUSIASTS,
    "Avatar's Wrath": AVATARS_WRATH,
    "Compassionate Healer": COMPASSIONATE_HEALER,
    "Curious Farm Animals": CURIOUS_FARM_ANIMALS,
    "Destined Confrontation": DESTINED_CONFRONTATION,
    "Earth Kingdom Jailer": EARTH_KINGDOM_JAILER,
    "Earth Kingdom Protectors": EARTH_KINGDOM_PROTECTORS,
    "Enter the Avatar State": ENTER_THE_AVATAR_STATE,
    "Fancy Footwork": FANCY_FOOTWORK,
    "Gather the White Lotus": GATHER_THE_WHITE_LOTUS,
    "Glider Kids": GLIDER_KIDS,
    "Glider Staff": GLIDER_STAFF,
    "Hakoda, Selfless Commander": HAKODA_SELFLESS_COMMANDER,
    "Invasion Reinforcements": INVASION_REINFORCEMENTS,
    "Jeong Jeong's Deserters": JEONG_JEONGS_DESERTERS,
    "Katara, Waterbending Master": KATARA_WATERBENDING_MASTER,
    "Sokka, Swordsman": SOKKA_SWORDSMAN,
    "Suki, Kyoshi Warrior": SUKI_KYOSHI_WARRIOR,
    "Uncle Iroh, Tea Master": UNCLE_IROH_TEA_MASTER,
    "White Lotus Member": WHITE_LOTUS_MEMBER,
    "Kyoshi Island Defender": KYOSHI_ISLAND_DEFENDER,
    "Meelo, the Troublemaker": MEELO_THE_TROUBLEMAKER,
    "Momo, Loyal Companion": MOMO_LOYAL_COMPANION,
    "Airbender Initiate": AIRBENDER_INITIATE,
    "Cabbage Merchant": CABBAGE_MERCHANT,
    "Monastic Discipline": MONASTIC_DISCIPLINE,
    "Winds of Change": WINDS_OF_CHANGE,
    "Avatar Korra, Spirit Bridge": AVATAR_KORRA_SPIRIT,
    "Peaceful Sanctuary": PEACEFUL_SANCTUARY,
    "Guru Pathik": GURU_PATHIK,
    "Lion Turtle Blessing": LION_TURTLE_BLESSING,
    "Gyatso, Wise Mentor": GYATSO_WISE_MENTOR,
    "Jinora, Spiritual Guide": JINORA_SPIRITUAL_GUIDE,
    "Korra, Avatar Unleashed": KORRA_AVATAR_UNLEASHED,
    "Airbending Master": AIRBENDING_MASTER,
    "Nomad Musician": NOMAD_MUSICIAN,
    "Air Acolyte": AIR_ACOLYTE,
    "Restoration Ritual": RESTORATION_RITUAL,
    "Spiritual Guidance": SPIRITUAL_GUIDANCE,

    # BLUE
    "Aang, Swift Savior": AANG_SWIFT_SAVIOR,
    "Abandon Attachments": ABANDON_ATTACHMENTS,
    "Accumulate Wisdom": ACCUMULATE_WISDOM,
    "Benevolent River Spirit": BENEVOLENT_RIVER_SPIRIT,
    "Boomerang Basics": BOOMERANG_BASICS,
    "Knowledge Seeker": KNOWLEDGE_SEEKER,
    "Library Guardian": LIBRARY_GUARDIAN,
    "Master Pakku": MASTER_PAKKU,
    "Moon Spirit Blessing": MOON_SPIRIT_BLESSING,
    "Northern Water Tribe": NORTHERN_WATER_TRIBE,
    "Ocean Spirit Fury": OCEAN_SPIRIT_FURY,
    "Princess Yue": PRINCESS_YUE,
    "Spirit Library": SPIRIT_LIBRARY,
    "Waterbending Lesson": WATERBENDING_LESSON,
    "Wan Shi Tong": WAN_SHI_TONG,
    "Hama, Bloodbender": HAMA_BLOODBENDER,
    "Serpent's Pass Horror": SERPENTS_PASS_HORROR,
    "Southern Water Tribe": SOUTHERN_WATER_TRIBE,
    "Foggy Swamp Waterbender": FOGGY_SWAMP_WATERBENDER,
    "Spirit Fox": SPIRIT_FOX,
    "Unagi Attack": UNAGI_ATTACK,
    "Wisdom of Ages": WISDOM_OF_AGES,
    "Avatar Roku": AVATAR_ROKU,
    "Spirit World Wanderer": SPIRIT_WORLD_WANDERER,
    "Water Tribe Healer": WATER_TRIBE_HEALER,
    "Tui and La": TUI_AND_LA,
    "Mist Veil": MIST_VEIL,
    "Kanna, Gran Gran": KANNA_GRAN_GRAN,
    "Ocean Depths Leviathan": OCEAN_DEPTHS_LEVIATHAN,
    "Thought Manipulation": THOUGHT_MANIPULATION,
    "Spirit Vision": SPIRIT_VISION,
    "Water Whip": WATER_WHIP,
    "Crashing Waves": CRASHING_WAVES,
    "Ice Shield": ICE_SHIELD,

    # BLACK
    "Azula Always Lies": AZULA_ALWAYS_LIES,
    "Azula, Cunning Usurper": AZULA_CUNNING_USURPER,
    "Azula, On the Hunt": AZULA_ON_THE_HUNT,
    "Beetle-Headed Merchants": BEETLE_HEADED_MERCHANTS,
    "Boiling Rock Rioter": BOILING_ROCK_RIOTER,
    "Buzzard-Wasp Colony": BUZZARD_WASP_COLONY,
    "Canyon Crawler": CANYON_CRAWLER,
    "Corrupt Court Official": CORRUPT_COURT_OFFICIAL,
    "Cruel Administrator": CRUEL_ADMINISTRATOR,
    "Dai Li Indoctrination": DAI_LI_INDOCTRINATION,
    "Day of Black Sun": DAY_OF_BLACK_SUN,
    "Deadly Precision": DEADLY_PRECISION,
    "Epic Downfall": EPIC_DOWNFALL,
    "Fatal Fissure": FATAL_FISSURE,
    "Fire Lord Ozai": FIRE_LORD_OZAI,
    "Long Feng": LONG_FENG,
    "Mai, Knives Expert": MAI_KNIVES_EXPERT,
    "Zhao, the Conqueror": ZHAO_THE_CONQUEROR,
    "Dai Li Enforcer": DAI_LI_ENFORCER,
    "Spirit Corruption": SPIRIT_CORRUPTION,
    "Bloodbending Lesson": BLOODBENDING_LESSON,
    "Shadow of the Past": SHADOW_OF_THE_PAST,
    "Fire Nation Prison": FIRE_NATION_PRISON,
    "Cruel Ambition": CRUEL_AMBITION,
    "Spirit of Revenge": SPIRIT_OF_REVENGE,
    "War Balloon Crew": WAR_BALLOON_CREW,
    "Lake Laogai": LAKE_LAOGAI,
    "Kuvira, Great Uniter": KUVIRA_GREAT_UNITER,
    "Shadow Operative": SHADOW_OPERATIVE,
    "Dark Spirit's Blessing": DARK_SPIRITS_BLESSING,
    "Mind Break": MIND_BREAK,
    "Corrupt Official": CORRUPT_OFFICIAL,
    "Death by Lightning": DEATH_BY_LIGHTNING,
    "Prison Break": PRISON_BREAK,

    # RED
    "Boar-q-pine": BOAR_Q_PINE,
    "Bumi Bash": BUMI_BASH,
    "Combustion Man": COMBUSTION_MAN,
    "Combustion Technique": COMBUSTION_TECHNIQUE,
    "Fated Firepower": FATED_FIREPOWER,
    "Firebending Lesson": FIREBENDING_LESSON,
    "Firebending Student": FIREBENDING_STUDENT,
    "Fire Nation Attacks": FIRE_NATION_ATTACKS,
    "Fire Nation Cadets": FIRE_NATION_CADETS,
    "Fire Nation Warship": FIRE_NATION_WARSHIP,
    "Jeong Jeong, the Deserter": JEONG_JEONG_THE_DESERTER,
    "Prince Zuko": PRINCE_ZUKO,
    "Zuko, Redeemed": ZUKO_REDEEMED,
    "Fire Nation Commander": FIRE_NATION_COMMANDER,
    "Iroh, Dragon of the West": IROH_DRAGON_OF_THE_WEST,
    "Lightning Redirection": LIGHTNING_REDIRECTION,
    "Sozin's Comet": SOZINS_COMET,
    "Agni Kai": AGNI_KAI,
    "Dragon Dance": DRAGON_DANCE,
    "Ran and Shaw": RAN_AND_SHAW,
    "Fire Lily": FIRE_LILY,
    "Volcanic Eruption": VOLCANIC_ERUPTION,
    "Phoenix Reborn": PHOENIX_REBORN,
    "Piandao, Sword Master": PIANDAO_SWORD_MASTER,
    "Fire Nation Soldier": FIRE_NATION_SOLDIER,
    "Rage of Fire": RAGE_OF_FIRE,
    "Lightning Bolt Lesson": LIGHTNING_BOLT_LESSON,
    "Fire Wall": FIRE_WALL,
    "Comet Enhanced": COMET_ENHANCED,
    "Caldera Eruption": CALDERA_ERUPTION,

    # GREEN
    "Allies at Last": ALLIES_AT_LAST,
    "Avatar Destiny": AVATAR_DESTINY,
    "Badgermole": BADGERMOLE,
    "Badgermole Cub": BADGERMOLE_CUB,
    "Bumi, King of Three Trials": BUMI_KING_OF_THREE_TRIALS,
    "Cycle of Renewal": CYCLE_OF_RENEWAL,
    "Earthbender Ascension": EARTHBENDER_ASCENSION,
    "Earthbending Lesson": EARTHBENDING_LESSON,
    "Earth Kingdom General": EARTH_KINGDOM_GENERAL,
    "Earth Rumble": EARTH_RUMBLE,
    "Toph Beifong": TOPH_BEIFONG,
    "Toph, Metalbender": TOPH_METALBENDER,
    "Swampbender": SWAMPBENDER,
    "Flying Bison Herd": FLYING_BISON_HERD,
    "Avatar Kyoshi": AVATAR_KYOSHI,
    "Forest Spirit": FOREST_SPIRIT,
    "Catgator": CATGATOR,
    "Swamp Giant": SWAMP_GIANT,
    "Earth Kingdom Farmer": EARTH_KINGDOM_FARMER,
    "Natural Harmony": NATURAL_HARMONY,
    "Primal Fury": PRIMAL_FURY,
    "Platypus Bear": PLATYPUS_BEAR,
    "Spirit Vine": SPIRIT_VINE,
    "Due, the Earth Spirit": DUE_THE_EARTH_SPIRIT,
    "Forest Guardian": FOREST_GUARDIAN,
    "Oasis Hermit": OASIS_HERMIT,
    "Wild Growth": WILD_GROWTH,
    "Beast Summons": BEAST_SUMMONS,
    "Nature Reclamation": NATURE_RECLAMATION,
    "Standing Tall": STANDING_TALL,

    # MULTICOLOR
    "Aang and La, Ocean's Fury": AANG_AND_LA,
    "Beifong's Bounty Hunters": BEIFONGS_BOUNTY_HUNTERS,
    "Bitter Work": BITTER_WORK,
    "Bumi, Unleashed": BUMI_UNLEASHED,
    "Dai Li Agents": DAI_LI_AGENTS,
    "Fire Lord Azula": FIRE_LORD_AZULA,
    "Fire Lord Zuko": FIRE_LORD_ZUKO,
    "Team Avatar": TEAM_AVATAR,
    "Ty Lee, Acrobat": TY_LEE_ACROBAT,
    "Sokka and Suki": SOKKA_AND_SUKI,
    "Zuko and Iroh": ZUKO_AND_IROH,
    "Katara and Aang": KATARA_AND_AANG,
    "Azula and Dai Li": AZULA_AND_DAI_LI,
    "Spirit World Portal": SPIRIT_WORLD_PORTAL,
    "Firelord Sozin": FIRELORD_SOZIN,
    "Avatar Yangchen": AVATAR_YANGCHEN,
    "Avatar Kuruk": AVATAR_KURUK,
    "Lion Turtle": LION_TURTLE,
    "Koizilla": KOIZILLA,
    "Hei Bai, Forest Spirit": HEIBAIFACED_SPIRIT,
    "Mai and Ty Lee": MAI_AND_TY_LEE,
    "Amon, the Equalist": AMON_THE_EQUALIST,
    "Unalaq, Dark Avatar": UNALAQ_DARK_AVATAR,
    "Spirit of Raava": SPIRIT_OF_RAAVA,
    "Spirit of Vaatu": SPIRIT_OF_VAATU,
    "Red Lotus": RED_LOTUS,
    "White Lotus Grandmaster": WHITE_LOTUS_GRANDMASTER,

    # ARTIFACTS
    "Aang Statue": AANG_STATUE,
    "Earth Kingdom Tank": EARTH_KINGDOM_TANK,
    "Meteorite Sword": METEORITE_SWORD,
    "Spirit Oasis": SPIRIT_OASIS,
    "War Balloon": WAR_BALLOON,
    "Azula's Crown": AZULAS_CROWN,
    "Water Pouch": WATER_POUCH,
    "Fire Nation Helm": FIRE_NATION_HELM,
    "Aang's Staff": AANGS_STAFF,
    "Toph's Bracelet": TOPHS_BRACELET,
    "Sunstone": SUNSTONE,
    "Moonstone": MOONSTONE,
    "Lotus Tile": LOTUS_TILE,
    "The Drill": DRILL,
    "Sokka's Boomerang": BOOMERANG_ARTIFACT,
    "Cactus Juice": CACTUS_JUICE,
    "Firebending Scroll": FIREBENDING_SCROLL,
    "Earthbending Scroll": EARTHBENDING_SCROLL,
    "Waterbending Scroll": WATERBENDING_SCROLL,
    "Airbending Scroll": AIRBENDING_SCROLL,
    "Fire Nation Submarine": SUBMARINE,
    "Chi Blocker Gloves": CHI_BLOCKER_GLOVES,

    # LANDS
    "Air Temple": AIR_TEMPLE,
    "Ba Sing Se": BA_SING_SE,
    "Fire Nation Capital": FIRE_NATION_CAPITAL,
    "Spirit World Gate": SPIRIT_WORLD_GATE,
    "Water Tribe Village": WATER_TRIBE_VILLAGE,
    "Fire Nation Outpost": FIRE_NATION_OUTPOST,
    "Earth Kingdom Fortress": EARTH_KINGDOM_FORTRESS,
    "Omashu": OMASHU,
    "Ember Island": EMBER_ISLAND,
    "Fog of Lost Souls": FOG_OF_LOST_SOULS,
    "Southern Air Temple": SOUTHERN_AIR_TEMPLE,
    "Western Air Temple": WESTERN_AIR_TEMPLE,
    "Kyoshi Island": KYOSHI_ISLAND,
    "Boiling Rock Prison": BOILING_ROCK_PRISON,
    "Serpent's Pass": SERPENTS_PASS,
    "Foggy Swamp": FOGGY_SWAMP,
    "Si Wong Desert": SI_WONG_DESERT,
    "Northern Water Tribe Capital": NORTHERN_WATER_TRIBE_CAPITAL,

    # FINAL BATCH
    "Republic City": REPUBLIC_CITY,
    "Pro-Bending Arena": PRO_BENDING_ARENA,
    "Mako, Firebender": MAKO_FIREBENDER,
    "Bolin, Lavabender": BOLIN_LAVABENDER,
    "Asami Sato": ASAMI_SATO,
    "Lin Beifong": LIN_BEIFONG,
    "Tenzin, Airbending Master": TENZIN_AIRBENDING_MASTER,
    "Zaheer, Red Lotus Leader": ZAHEER_RED_LOTUS_LEADER,
    "P'Li, Combustion Bender": PLI_COMBUSTION_BENDER,
    "Ghazan, Lavabender": GHAZAN_LAVABENDER,
    "Ming-Hua, Armless Waterbender": MING_HUA_WATERBENDER,
    "Naga, Polar Bear Dog": NAGA_POLAR_BEAR_DOG,
    "Pabu the Fire Ferret": PABU_FIRE_FERRET,
    "Varrick, Industrialist": VARRICK_INDUSTRIALIST,
    "Zhu Li, Personal Assistant": ZHU_LI_ASSISTANT,
    "Tarrlok, Bloodbender": TARRLOK_BLOODBENDER,
    "Noatak (Amon)": NOATAK_AMON,
    "Equalist Chi Blocker": EQUALIST_CHI_BLOCKER,
    "Mecha Tank": MECHA_TANK,
    "Spirit Wilds": SPIRIT_WILDS,
    "Harmonic Convergence": HARMONIC_CONVERGENCE,
    "Air Nation Restored": AIR_NATION_RESTORED,
    "Pro-Bending Match": PRO_BENDING_MATCH,
    "Platinum Mech Suit": PLATINUM_MECH_SUIT,
    "Spirit Cannon": SPIRIT_CANNON,
    "Airbender's Flight": AIRBENDERS_FLIGHT,
    "Lavabending": LAVABENDING,
    "Metalbending Cable": METALBENDING_CABLE,
    "Spirit Portal": SPIRIT_PORTAL,
    "Korra and Asami": KORRA_AND_ASAMI,

    # BASIC LANDS
    "Plains": PLAINS_TLA,
    "Island": ISLAND_TLA,
    "Swamp": SWAMP_TLA,
    "Mountain": MOUNTAIN_TLA,
    "Forest": FOREST_TLA,

    # INSTANTS & SORCERIES
    "Blue Spirit Strike": BLUE_SPIRIT_STRIKE,
    "Siege of the North": SIEGE_OF_THE_NORTH,
    "Crossroads of Destiny": CROSSROADS_OF_DESTINY,
    "Final Agni Kai": FINAL_AGNI_KAI,
    "Bloodbending": BLOODBENDING,
    "Eclipse Darkness": ECLIPSE_DARKNESS,
    "Avatar State Fury": AVATAR_STATE_FURY,
    "Invasion Day": INVASION_DAY,
    "Tunnel Through": TUNNEL_THROUGH,
    "Spirit Bomb": SPIRIT_BOMB,
}

print(f"Loaded {len(AVATAR_TLA_CARDS)} Avatar: The Last Airbender cards")
