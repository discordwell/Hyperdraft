"""
Marvels_Spider-Man (SPM) Card Implementations

Real card data fetched from Scryfall API.
193 cards in set.
"""

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, ObjectState, CardDefinition,
    make_creature, make_enchantment,
    new_id, get_power, get_toughness
)
from typing import Optional, Callable


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def make_instant(name: str, mana_cost: str, colors: set, text: str, subtypes: set = None, supertypes: set = None, resolve=None):
    """Helper to create instant card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.INSTANT},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            mana_cost=mana_cost
        ),
        text=text,
        resolve=resolve
    )


def make_sorcery(name: str, mana_cost: str, colors: set, text: str, subtypes: set = None, supertypes: set = None, resolve=None):
    """Helper to create sorcery card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.SORCERY},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            mana_cost=mana_cost
        ),
        text=text,
        resolve=resolve
    )


def make_artifact(name: str, mana_cost: str, text: str, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create artifact card definitions."""
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


def make_artifact_creature(name: str, power: int, toughness: int, mana_cost: str, colors: set,
                           subtypes: set = None, supertypes: set = None, text: str = "", setup_interceptors=None):
    """Helper to create artifact creature card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT, CardType.CREATURE},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            power=power,
            toughness=toughness,
            mana_cost=mana_cost
        ),
        text=text,
        setup_interceptors=setup_interceptors
    )


def make_land(name: str, text: str = "", subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create land card definitions."""
    return CardDefinition(
        name=name,
        mana_cost="",
        characteristics=Characteristics(
            types={CardType.LAND},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            mana_cost=""
        ),
        text=text,
        setup_interceptors=setup_interceptors
    )


def make_planeswalker(name: str, mana_cost: str, colors: set, loyalty: int,
                      subtypes: set = None, supertypes: set = None, text: str = "", setup_interceptors=None):
    """Helper to create planeswalker card definitions."""
    base_supertypes = supertypes or set()
    # Note: loyalty is prepended to text since Characteristics doesn't have loyalty field
    loyalty_text = f"[Loyalty: {loyalty}] " + text if text else f"[Loyalty: {loyalty}]"
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.PLANESWALKER},
            subtypes=subtypes or set(),
            supertypes=base_supertypes,
            colors=colors,
            mana_cost=mana_cost
        ),
        text=loyalty_text,
        setup_interceptors=setup_interceptors
    )


# =============================================================================
# CARD DEFINITIONS
# =============================================================================

ANTIVENOM_HORRIFYING_HEALER = make_creature(
    name="Anti-Venom, Horrifying Healer",
    power=5, toughness=5,
    mana_cost="{W}{W}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Hero", "Symbiote"},
    supertypes={"Legendary"},
    text="When Anti-Venom enters, if he was cast, return target creature card from your graveyard to the battlefield.\nIf damage would be dealt to Anti-Venom, prevent that damage and put that many +1/+1 counters on him.",
)

ARACHNE_PSIONIC_WEAVER = make_creature(
    name="Arachne, Psionic Weaver",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Web-slinging {W} (You may cast this spell for {W} if you also return a tapped creature you control to its owner's hand.)\nAs Arachne enters, look at an opponent's hand, then choose a card type other than creature.\nSpells of the chosen type cost {1} more to cast.",
)

AUNT_MAY = make_creature(
    name="Aunt May",
    power=0, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Citizen", "Human"},
    supertypes={"Legendary"},
    text="Whenever another creature you control enters, you gain 1 life. If it's a Spider, put a +1/+1 counter on it.",
)

CITY_PIGEON = make_creature(
    name="City Pigeon",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Bird"},
    text="Flying\nWhen this creature leaves the battlefield, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")",
)

COSTUME_CLOSET = make_artifact(
    name="Costume Closet",
    mana_cost="{1}{W}",
    text="This artifact enters with two +1/+1 counters on it.\n{T}: Move a +1/+1 counter from this artifact onto target creature you control. Activate only as a sorcery.\nWhenever a modified creature you control leaves the battlefield, put a +1/+1 counter on this artifact. (Equipment, Auras you control, and counters are modifications.)",
)

DAILY_BUGLE_REPORTERS = make_creature(
    name="Daily Bugle Reporters",
    power=2, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Citizen", "Human"},
    text="When this creature enters, choose one —\n• Puff Piece — Put a +1/+1 counter on each of up to two target creatures.\n• Investigative Journalism — Return target creature card with mana value 2 or less from your graveyard to your hand.",
)

FLASH_THOMPSON_SPIDERFAN = make_creature(
    name="Flash Thompson, Spider-Fan",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Citizen", "Human"},
    supertypes={"Legendary"},
    text="Flash\nWhen Flash Thompson enters, choose one or both —\n• Heckle — Tap target creature.\n• Hero Worship — Untap target creature.",
)

FRIENDLY_NEIGHBORHOOD = make_enchantment(
    name="Friendly Neighborhood",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Enchant land\nWhen this Aura enters, create three 1/1 green and white Human Citizen creature tokens.\nEnchanted land has \"{1}, {T}: Target creature gets +1/+1 until end of turn for each creature you control. Activate only as a sorcery.\"",
    subtypes={"Aura"},
)

ORIGIN_OF_SPIDERMAN = make_enchantment(
    name="Origin of Spider-Man",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Create a 2/1 green Spider creature token with reach.\nII — Put a +1/+1 counter on target creature you control. It becomes a legendary Spider Hero in addition to its other types.\nIII — Target creature you control gains double strike until end of turn.",
    subtypes={"Saga"},
)

PETER_PARKER = make_creature(
    name="Peter Parker",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Hero", "Human", "Legendary", "Scientist"},
    supertypes={"Legendary"},
    text="",
)

RENT_IS_DUE = make_enchantment(
    name="Rent Is Due",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="At the beginning of your end step, you may tap two untapped creatures and/or Treasures you control. If you do, draw a card. Otherwise, sacrifice this enchantment.",
)

SELFLESS_POLICE_CAPTAIN = make_creature(
    name="Selfless Police Captain",
    power=1, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Detective", "Human"},
    text="This creature enters with a +1/+1 counter on it.\nWhen this creature leaves the battlefield, put its +1/+1 counters on target creature you control.",
)

SILVER_SABLE_MERCENARY_LEADER = make_creature(
    name="Silver Sable, Mercenary Leader",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Hero", "Human", "Mercenary"},
    supertypes={"Legendary"},
    text="When Silver Sable enters, put a +1/+1 counter on another target creature.\nWhenever Silver Sable attacks, target modified creature you control gains lifelink until end of turn. (Equipment, Auras you control, and counters are modifications.)",
)

SPECTACULAR_SPIDERMAN = make_creature(
    name="Spectacular Spider-Man",
    power=3, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Flash\n{1}: Spectacular Spider-Man gains flying until end of turn.\n{1}, Sacrifice Spectacular Spider-Man: Creatures you control gain hexproof and indestructible until end of turn.",
)

SPECTACULAR_TACTICS = make_instant(
    name="Spectacular Tactics",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Put a +1/+1 counter on target creature you control. It gains hexproof until end of turn.\n• Destroy target creature with power 4 or greater.",
)

SPIDERMAN_WEBSLINGER = make_creature(
    name="Spider-Man, Web-Slinger",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Web-slinging {W} (You may cast this spell for {W} if you also return a tapped creature you control to its owner's hand.)",
)

SPIDERUK = make_creature(
    name="Spider-UK",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Web-slinging {2}{W} (You may cast this spell for {2}{W} if you also return a tapped creature you control to its owner's hand.)\nAt the beginning of your end step, if two or more creatures entered the battlefield under your control this turn, you draw a card and gain 2 life.",
)

STARLING_AERIAL_ALLY = make_creature(
    name="Starling, Aerial Ally",
    power=3, toughness=4,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Hero", "Human"},
    supertypes={"Legendary"},
    text="Flying\nWhen Starling enters, another target creature you control gains flying until end of turn.",
)

SUDDEN_STRIKE = make_instant(
    name="Sudden Strike",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Destroy target attacking or blocking creature.",
)

THWIP = make_instant(
    name="Thwip!",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 and gains flying until end of turn. If it's a Spider, you gain 2 life.",
)

WEB_UP = make_enchantment(
    name="Web Up",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, exile target nonland permanent an opponent controls until this enchantment leaves the battlefield.",
)

WEBSHOOTERS = make_artifact(
    name="Web-Shooters",
    mana_cost="{1}{W}",
    text="Equipped creature gets +1/+1 and has reach and \"Whenever this creature attacks, tap target creature an opponent controls.\"\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

WILD_PACK_SQUAD = make_creature(
    name="Wild Pack Squad",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Mercenary"},
    text="At the beginning of combat on your turn, up to one target creature gains first strike and vigilance until end of turn.",
)

WITH_GREAT_POWER = make_enchantment(
    name="With Great Power...",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Enchant creature you control\nEnchanted creature gets +2/+2 for each Aura and Equipment attached to it.\nAll damage that would be dealt to you is dealt to enchanted creature instead.",
    subtypes={"Aura"},
)

AMAZING_ACROBATICS = make_instant(
    name="Amazing Acrobatics",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Choose one or both —\n• Counter target spell.\n• Tap one or two target creatures.",
)

BEETLE_LEGACY_CRIMINAL = make_creature(
    name="Beetle, Legacy Criminal",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue", "Villain"},
    supertypes={"Legendary"},
    text="Flying\n{1}{U}, Exile this card from your graveyard: Put a +1/+1 counter on target creature. It gains flying until end of turn. Activate only as a sorcery.",
)

CHAMELEON_MASTER_OF_DISGUISE = make_creature(
    name="Chameleon, Master of Disguise",
    power=2, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Shapeshifter", "Villain"},
    supertypes={"Legendary"},
    text="You may have Chameleon enter as a copy of a creature you control, except his name is Chameleon, Master of Disguise.\nMayhem {2}{U} (You may cast this card from your graveyard for {2}{U} if you discarded it this turn. Timing rules still apply.)",
)

THE_CLONE_SAGA = make_enchantment(
    name="The Clone Saga",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Surveil 3.\nII — When you next cast a creature spell this turn, copy it, except the copy isn't legendary.\nIII — Choose a card name. Whenever a creature with the chosen name deals combat damage to a player this turn, draw a card.",
    subtypes={"Saga"},
)

DOC_OCK_SINISTER_SCIENTIST = make_creature(
    name="Doc Ock, Sinister Scientist",
    power=4, toughness=5,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scientist", "Villain"},
    supertypes={"Legendary"},
    text="As long as there are eight or more cards in your graveyard, Doc Ock has base power and toughness 8/8.\nAs long as you control another Villain, Doc Ock has hexproof. (He can't be the target of spells or abilities your opponents control.)",
)

DOC_OCKS_HENCHMEN = make_creature(
    name="Doc Ock's Henchmen",
    power=2, toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Villain"},
    text="Flash\nWhenever this creature attacks, it connives. (Draw a card, then discard a card. If you discarded a nonland card, put a +1/+1 counter on this creature.)",
)

FLYING_OCTOBOT = make_artifact_creature(
    name="Flying Octobot",
    power=1, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Robot", "Villain"},
    text="Flying\nWhenever another Villain you control enters, put a +1/+1 counter on this creature. This ability triggers only once each turn.",
)

HIDE_ON_THE_CEILING = make_instant(
    name="Hide on the Ceiling",
    mana_cost="{X}{U}",
    colors={Color.BLUE},
    text="Exile X target artifacts and/or creatures. Return the exiled cards to the battlefield under their owners' control at the beginning of the next end step.",
)

HYDROMAN_FLUID_FELON = make_creature(
    name="Hydro-Man, Fluid Felon",
    power=2, toughness=2,
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Villain"},
    supertypes={"Legendary"},
    text="Whenever you cast a blue spell, if Hydro-Man is a creature, he gets +1/+1 until end of turn.\nAt the beginning of your end step, untap Hydro-Man. Until your next turn, he becomes a land and gains \"{T}: Add {U}.\" (He's not a creature during that time.)",
)

IMPOSTOR_SYNDROME = make_enchantment(
    name="Impostor Syndrome",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Whenever a nontoken creature you control deals combat damage to a player, create a token that's a copy of it, except it isn't legendary.",
)

LADY_OCTOPUS_INSPIRED_INVENTOR = make_creature(
    name="Lady Octopus, Inspired Inventor",
    power=0, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scientist", "Villain"},
    supertypes={"Legendary"},
    text="Whenever you draw your first or second card each turn, put an ingenuity counter on Lady Octopus.\n{T}: You may cast an artifact spell from your hand with mana value less than or equal to the number of ingenuity counters on Lady Octopus without paying its mana cost.",
)

MADAME_WEB_CLAIRVOYANT = make_creature(
    name="Madame Web, Clairvoyant",
    power=4, toughness=4,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Advisor", "Mutant"},
    supertypes={"Legendary"},
    text="You may look at the top card of your library any time.\nYou may cast Spider spells and noncreature spells from the top of your library.\nWhenever you attack, you may mill a card. (You may put the top card of your library into your graveyard.)",
)

MYSTERIO_MASTER_OF_ILLUSION = make_creature(
    name="Mysterio, Master of Illusion",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="When Mysterio enters, create a 3/3 blue Illusion Villain creature token for each nontoken Villain you control. Exile those tokens when Mysterio leaves the battlefield.",
)

MYSTERIOS_PHANTASM = make_creature(
    name="Mysterio's Phantasm",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Illusion", "Villain"},
    text="Flying, vigilance\nWhenever this creature attacks, mill a card. (Put the top card of your library into your graveyard.)",
)

NORMAN_OSBORN = make_creature(
    name="Norman Osborn",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Human", "Legendary", "Scientist", "Villain"},
    supertypes={"Legendary"},
    text="",
)

OSCORP_RESEARCH_TEAM = make_creature(
    name="Oscorp Research Team",
    power=1, toughness=5,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scientist"},
    text="{6}{U}: Draw two cards.",
)

ROBOTICS_MASTERY = make_enchantment(
    name="Robotics Mastery",
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    text="Flash\nEnchant creature\nWhen this Aura enters, create two 1/1 colorless Robot artifact creature tokens with flying.\nEnchanted creature gets +2/+2.",
    subtypes={"Aura"},
)

SCHOOL_DAZE = make_instant(
    name="School Daze",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Choose one —\n• Do Homework — Draw three cards.\n• Fight Crime — Counter target spell. Draw a card.",
)

SECRET_IDENTITY = make_instant(
    name="Secret Identity",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Choose one —\n• Conceal — Until end of turn, target creature you control becomes a Citizen with base power and toughness 1/1 and gains hexproof.\n• Reveal — Until end of turn, target creature you control becomes a Hero with base power and toughness 3/4 and gains flying and vigilance.",
)

SPIDERBYTE_WEB_WARDEN = make_creature(
    name="Spider-Byte, Web Warden",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Avatar", "Hero", "Spider"},
    supertypes={"Legendary"},
    text="When Spider-Byte enters, return up to one target nonland permanent to its owner's hand.",
)

SPIDERMAN_NO_MORE = make_enchantment(
    name="Spider-Man No More",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Enchant creature\nEnchanted creature is a Citizen with base power and toughness 1/1. It has defender and loses all other abilities. (It also loses all other creature types.)",
    subtypes={"Aura"},
)

SPIDERSENSE = make_instant(
    name="Spider-Sense",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Web-slinging {U} (You may cast this spell for {U} if you also return a tapped creature you control to its owner's hand.)\nCounter target instant spell, sorcery spell, or triggered ability.",
)

UNSTABLE_EXPERIMENT = make_instant(
    name="Unstable Experiment",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Target player draws a card, then up to one target creature you control connives. (Draw a card, then discard a card. If you discarded a nonland card, put a +1/+1 counter on that creature.)",
)

WHOOSH = make_instant(
    name="Whoosh!",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Kicker {1}{U} (You may pay an additional {1}{U} as you cast this spell.)\nReturn target nonland permanent to its owner's hand. If this spell was kicked, draw a card.",
)

AGENT_VENOM = make_creature(
    name="Agent Venom",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Hero", "Soldier", "Symbiote"},
    supertypes={"Legendary"},
    text="Flash\nMenace\nWhenever another nontoken creature you control dies, you draw a card and lose 1 life.",
)

ALIEN_SYMBIOSIS = make_enchantment(
    name="Alien Symbiosis",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Enchant creature\nEnchanted creature gets +1/+1, has menace, and is a Symbiote in addition to its other types.\nYou may cast this card from your graveyard by discarding a card in addition to paying its other costs.",
    subtypes={"Aura"},
)

BEHOLD_THE_SINISTER_SIX = make_sorcery(
    name="Behold the Sinister Six!",
    mana_cost="{6}{B}",
    colors={Color.BLACK},
    text="Return up to six target creature cards with different names from your graveyard to the battlefield.",
)

BLACK_CAT_CUNNING_THIEF = make_creature(
    name="Black Cat, Cunning Thief",
    power=2, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue", "Villain"},
    supertypes={"Legendary"},
    text="When Black Cat enters, look at the top nine cards of target opponent's library, exile two of them face down, then put the rest on the bottom of their library in a random order. You may play the exiled cards for as long as they remain exiled. Mana of any type can be spent to cast spells this way.",
)

COMMON_CROOK = make_creature(
    name="Common Crook",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue", "Villain"},
    text="When this creature dies, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

THE_DEATH_OF_GWEN_STACY = make_enchantment(
    name="The Death of Gwen Stacy",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Destroy target creature.\nII — Each player may discard a card. Each player who doesn't loses 3 life.\nIII — Exile any number of target players' graveyards.",
    subtypes={"Saga"},
)

EDDIE_BROCK = make_creature(
    name="Eddie Brock",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Hero", "Human", "Legendary", "Villain"},
    supertypes={"Legendary"},
    text="",
)

GWENOM_REMORSELESS = make_creature(
    name="Gwenom, Remorseless",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Hero", "Spider", "Symbiote"},
    supertypes={"Legendary"},
    text="Deathtouch, lifelink\nWhenever Gwenom attacks, until end of turn, you may look at the top card of your library any time and you may play cards from the top of your library. If you cast a spell this way, pay life equal to its mana value rather than pay its mana cost.",
)

INNER_DEMONS_GANGSTERS = make_creature(
    name="Inner Demons Gangsters",
    power=3, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue", "Villain"},
    text="Discard a card: This creature gets +1/+0 and gains menace until end of turn. Activate only as a sorcery. (It can't be blocked except by two or more creatures.)",
)

MERCILESS_ENFORCERS = make_creature(
    name="Merciless Enforcers",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Mercenary", "Villain"},
    text="Lifelink\n{3}{B}: This creature deals 1 damage to each opponent.",
)

MORLUN_DEVOURER_OF_SPIDERS = make_creature(
    name="Morlun, Devourer of Spiders",
    power=2, toughness=1,
    mana_cost="{X}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Villain"},
    supertypes={"Legendary"},
    text="Lifelink\nMorlun enters with X +1/+1 counters on him.\nWhen Morlun enters, he deals X damage to target opponent.",
)

PARKER_LUCK = make_enchantment(
    name="Parker Luck",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="At the beginning of your end step, two target players each reveal the top card of their library. They each lose life equal to the mana value of the card revealed by the other player. Then they each put the card they revealed into their hand.",
)

PRISON_BREAK = make_sorcery(
    name="Prison Break",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield with an additional +1/+1 counter on it.\nMayhem {3}{B} (You may cast this card from your graveyard for {3}{B} if you discarded it this turn. Timing rules still apply.)",
)

RISKY_RESEARCH = make_sorcery(
    name="Risky Research",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Surveil 2, then draw two cards. You lose 2 life. (To surveil 2, look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
)

SANDMANS_QUICKSAND = make_sorcery(
    name="Sandman's Quicksand",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Mayhem {3}{B} (You may cast this card from your graveyard for {3}{B} if you discarded it this turn. Timing rules still apply.)\nAll creatures get -2/-2 until end of turn. If this spell's mayhem cost was paid, creatures your opponents control get -2/-2 until end of turn instead.",
)

SCORPION_SEETHING_STRIKER = make_creature(
    name="Scorpion, Seething Striker",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Scorpion", "Villain"},
    supertypes={"Legendary"},
    text="Deathtouch\nAt the beginning of your end step, if a creature died this turn, target creature you control connives. (Draw a card, then discard a card. If you discarded a nonland card, put a +1/+1 counter on that creature.)",
)

SCORPIONS_STING = make_instant(
    name="Scorpion's Sting",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -3/-3 until end of turn.",
)

THE_SOUL_STONE = make_artifact(
    name="The Soul Stone",
    mana_cost="{1}{B}",
    text="Indestructible\n{T}: Add {B}.\n{6}{B}, {T}, Exile a creature you control: Harness The Soul Stone. (Once harnessed, its ∞ ability is active.)\n∞ — At the beginning of your upkeep, return target creature card from your graveyard to the battlefield.",
    subtypes={"Infinity", "Stone"},
    supertypes={"Legendary"},
)

SPIDERMAN_NOIR = make_creature(
    name="Spider-Man Noir",
    power=4, toughness=4,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Menace\nWhenever a creature you control attacks alone, put a +1/+1 counter on it. Then surveil X, where X is the number of counters on it. (Look at the top X cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
)

THE_SPOTS_PORTAL = make_instant(
    name="The Spot's Portal",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Put target creature on the bottom of its owner's library. You lose 2 life unless you control a Villain.",
)

SWARM_BEING_OF_BEES = make_creature(
    name="Swarm, Being of Bees",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Insect", "Villain"},
    supertypes={"Legendary"},
    text="Flash\nFlying\nMayhem {B} (You may cast this card from your graveyard for {B} if you discarded it this turn. Timing rules still apply.)",
)

TOMBSTONE_CAREER_CRIMINAL = make_creature(
    name="Tombstone, Career Criminal",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="When Tombstone enters, return target Villain card from your graveyard to your hand.\nVillain spells you cast cost {1} less to cast.",
)

VENOM_EVIL_UNLEASHED = make_creature(
    name="Venom, Evil Unleashed",
    power=4, toughness=5,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Symbiote", "Villain"},
    supertypes={"Legendary"},
    text="Deathtouch\n{2}{B}, Exile this card from your graveyard: Put two +1/+1 counters on target creature. It gains deathtouch until end of turn. Activate only as a sorcery.",
)

VENOMIZED_CAT = make_creature(
    name="Venomized Cat",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Cat", "Symbiote", "Villain"},
    text="Deathtouch\nWhen this creature enters, mill two cards. (Put the top two cards of your library into your graveyard.)",
)

VENOMS_HUNGER = make_sorcery(
    name="Venom's Hunger",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="This spell costs {2} less to cast if you control a Villain.\nDestroy target creature. You gain 2 life.",
)

VILLAINOUS_WRATH = make_sorcery(
    name="Villainous Wrath",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Target opponent loses life equal to the number of creatures they control. Then destroy all creatures.",
)

ANGRY_RABBLE = make_creature(
    name="Angry Rabble",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Citizen", "Human"},
    text="Trample\nWhenever you cast a spell with mana value 4 or greater, this creature deals 1 damage to each opponent.\n{5}{R}: Put two +1/+1 counters on this creature. Activate only as a sorcery.",
)

ELECTRO_ASSAULTING_BATTERY = make_creature(
    name="Electro, Assaulting Battery",
    power=2, toughness=3,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Flying\nYou don't lose unspent red mana as steps and phases end.\nWhenever you cast an instant or sorcery spell, add {R}.\nWhen Electro leaves the battlefield, you may pay {X}. When you do, he deals X damage to target player.",
)

ELECTROS_BOLT = make_sorcery(
    name="Electro's Bolt",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Electro's Bolt deals 4 damage to target creature.\nMayhem {1}{R} (You may cast this card from your graveyard for {1}{R} if you discarded it this turn. Timing rules still apply.)",
)

GWEN_STACY = make_creature(
    name="Gwen Stacy",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Hero", "Human", "Legendary", "Performer"},
    supertypes={"Legendary"},
    text="",
)

HEROES_HANGOUT = make_sorcery(
    name="Heroes' Hangout",
    mana_cost="{R}",
    colors={Color.RED},
    text="Choose one —\n• Date Night — Exile the top two cards of your library. Choose one of them. Until the end of your next turn, you may play that card.\n• Patrol Night — One or two target creatures each get +1/+0 and gain first strike until end of turn.",
)

HOBGOBLIN_MANTLED_MARAUDER = make_creature(
    name="Hobgoblin, Mantled Marauder",
    power=1, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Human", "Villain"},
    supertypes={"Legendary"},
    text="Flying, haste\nWhenever you discard a card, Hobgoblin gets +2/+0 until end of turn.",
)

J_JONAH_JAMESON = make_creature(
    name="J. Jonah Jameson",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Citizen", "Human"},
    supertypes={"Legendary"},
    text="When J. Jonah Jameson enters, suspect up to one target creature. (A suspected creature has menace and can't block.)\nWhenever a creature you control with menace attacks, create a Treasure token.",
)

MASKED_MEOWER = make_creature(
    name="Masked Meower",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Cat", "Hero", "Spider"},
    text="Haste\nDiscard a card, Sacrifice this creature: Draw a card.",
)

MAXIMUM_CARNAGE = make_enchantment(
    name="Maximum Carnage",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Until your next turn, each creature attacks each combat if able and attacks a player other than you if able.\nII — Add {R}{R}{R}.\nIII — This Saga deals 5 damage to each opponent.",
    subtypes={"Saga"},
)

MOLTEN_MAN_INFERNO_INCARNATE = make_creature(
    name="Molten Man, Inferno Incarnate",
    power=0, toughness=0,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Villain"},
    supertypes={"Legendary"},
    text="When Molten Man enters, search your library for a basic Mountain card, put it onto the battlefield tapped, then shuffle.\nMolten Man gets +1/+1 for each Mountain you control.\nWhen Molten Man leaves the battlefield, sacrifice a land.",
)

RAGING_GOBLINOIDS = make_creature(
    name="Raging Goblinoids",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Berserker", "Goblin", "Villain"},
    text="Haste\nMayhem {2}{R} (You may cast this card from your graveyard for {2}{R} if you discarded it this turn. Timing rules still apply.)",
)

ROMANTIC_RENDEZVOUS = make_sorcery(
    name="Romantic Rendezvous",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Discard a card, then draw two cards.",
)

SHADOW_OF_THE_GOBLIN = make_enchantment(
    name="Shadow of the Goblin",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Unreliable Visions — At the beginning of your first main phase, discard a card. If you do, draw a card.\nUndying Vengeance — Whenever you play a land or cast a spell from anywhere other than your hand, this enchantment deals 1 damage to each opponent.",
)

SHOCK = make_instant(
    name="Shock",
    mana_cost="{R}",
    colors={Color.RED},
    text="Shock deals 2 damage to any target.",
)

SHOCKER_UNSHAKABLE = make_creature(
    name="Shocker, Unshakable",
    power=5, toughness=5,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rogue", "Villain"},
    supertypes={"Legendary"},
    text="During your turn, Shocker has first strike.\nVibro-Shock Gauntlets — When Shocker enters, he deals 2 damage to target creature and 2 damage to that creature's controller.",
)

SPIDERGWEN_FREE_SPIRIT = make_creature(
    name="Spider-Gwen, Free Spirit",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Reach\nWhenever Spider-Gwen becomes tapped, you may discard a card. If you do, draw a card.",
)

SPIDERISLANDERS = make_creature(
    name="Spider-Islanders",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Citizen", "Horror", "Spider"},
    text="Mayhem {1}{R} (You may cast this card from your graveyard for {1}{R} if you discarded it this turn. Timing rules still apply.)",
)

SPIDERPUNK = make_creature(
    name="Spider-Punk",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Riot (This creature enters with your choice of a +1/+1 counter or haste.)\nOther Spiders you control have riot.\nSpells and abilities can't be countered.\nDamage can't be prevented.",
)

SPIDERVERSE = make_enchantment(
    name="Spider-Verse",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="The \"legend rule\" doesn't apply to Spiders you control.\nWhenever you cast a spell from anywhere other than your hand, you may copy it. If you do, you may choose new targets for the copy. If the copy is a permanent spell, it gains haste. Do this only once each turn.",
)

SPINNERET_AND_SPIDERLING = make_creature(
    name="Spinneret and Spiderling",
    power=1, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Whenever you attack with two or more Spiders, put a +1/+1 counter on Spinneret and Spiderling.\nWhenever Spinneret and Spiderling deals 4 or more damage, exile the top card of your library. Until the end of your next turn, you may play that card.",
)

STEGRON_THE_DINOSAUR_MAN = make_creature(
    name="Stegron the Dinosaur Man",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur", "Villain"},
    supertypes={"Legendary"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nDinosaur Formula — {1}{R}, Discard this card: Until end of turn, target creature you control gets +3/+1 and becomes a Dinosaur in addition to its other types.",
)

SUPERIOR_FOES_OF_SPIDERMAN = make_creature(
    name="Superior Foes of Spider-Man",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rogue", "Villain"},
    text="Trample\nWhenever you cast a spell with mana value 4 or greater, you may exile the top card of your library. If you do, you may play that card until you exile another card with this creature.",
)

TAXI_DRIVER = make_creature(
    name="Taxi Driver",
    power=3, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Pilot"},
    text="{1}, {T}: Target creature gains haste until end of turn.",
)

WISECRACK = make_instant(
    name="Wisecrack",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Target creature deals damage equal to its power to itself. If that creature is attacking, Wisecrack deals 2 damage to that creature's controller.",
)

DAMAGE_CONTROL_CREW = make_creature(
    name="Damage Control Crew",
    power=3, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Citizen", "Human"},
    text="When this creature enters, choose one —\n• Repair — Return target card with mana value 4 or greater from your graveyard to your hand.\n• Impound — Exile target artifact or enchantment.",
)

EZEKIEL_SIMS_SPIDERTOTEM = make_creature(
    name="Ezekiel Sims, Spider-Totem",
    power=3, toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Advisor", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Reach\nAt the beginning of combat on your turn, target Spider you control gets +2/+2 until end of turn.",
)

GROW_EXTRA_ARMS = make_instant(
    name="Grow Extra Arms",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="This spell costs {1} less to cast if it targets a Spider.\nTarget creature gets +4/+4 until end of turn.",
)

GUY_IN_THE_CHAIR = make_creature(
    name="Guy in the Chair",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Advisor", "Human"},
    text="{T}: Add one mana of any color.\nWeb Support — {2}{G}, {T}: Put a +1/+1 counter on target Spider. Activate only as a sorcery.",
)

KAPOW = make_sorcery(
    name="Kapow!",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Put a +1/+1 counter on target creature you control. It fights target creature an opponent controls. (Each deals damage equal to its power to the other.)",
)

KRAVENS_CATS = make_creature(
    name="Kraven's Cats",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Cat", "Villain"},
    text="{2}{G}: This creature gets +2/+2 until end of turn. Activate only once each turn.",
)

KRAVENS_LAST_HUNT = make_enchantment(
    name="Kraven's Last Hunt",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Mill five cards. When you do, this Saga deals damage equal to the greatest power among creature cards in your graveyard to target creature.\nII — Target creature you control gets +2/+2 until end of turn.\nIII — Return target creature card from your graveyard to your hand.",
    subtypes={"Saga"},
)

LIZARD_CONNORSS_CURSE = make_creature(
    name="Lizard, Connors's Curse",
    power=5, toughness=5,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Lizard", "Villain"},
    supertypes={"Legendary"},
    text="Trample\nLizard Formula — When Lizard, Connors's Curse enters, up to one other target creature loses all abilities and becomes a green Lizard creature with base power and toughness 4/4.",
)

LURKING_LIZARDS = make_creature(
    name="Lurking Lizards",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Lizard", "Villain"},
    text="Trample\nWhenever you cast a spell with mana value 4 or greater, put a +1/+1 counter on this creature.",
)

MILES_MORALES = make_creature(
    name="Miles Morales",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Citizen", "Creature", "Hero", "Human", "Legendary"},
    supertypes={"Legendary"},
    text="",
)

PICTURES_OF_SPIDERMAN = make_artifact(
    name="Pictures of Spider-Man",
    mana_cost="{2}{G}",
    text="When this artifact enters, look at the top five cards of your library. You may reveal up to two creature cards from among them and put them into your hand. Put the rest on the bottom of your library in a random order.\n{1}, {T}, Sacrifice this artifact: Create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

PROFESSIONAL_WRESTLER = make_creature(
    name="Professional Wrestler",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Performer", "Warrior"},
    text="When this creature enters, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nThis creature can't be blocked by more than one creature.",
)

RADIOACTIVE_SPIDER = make_creature(
    name="Radioactive Spider",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Spider"},
    text="Reach, deathtouch\nFateful Bite — {2}, Sacrifice this creature: Search your library for a Spider Hero card, reveal it, put it into your hand, then shuffle. Activate only as a sorcery.",
)

SANDMAN_SHIFTING_SCOUNDREL = make_creature(
    name="Sandman, Shifting Scoundrel",
    power=0, toughness=0,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental", "Sand", "Villain"},
    supertypes={"Legendary"},
    text="Sandman's power and toughness are each equal to the number of lands you control.\nSandman can't be blocked by creatures with power 2 or less.\n{3}{G}{G}: Return this card and target land card from your graveyard to the battlefield tapped.",
)

SCOUT_THE_CITY = make_sorcery(
    name="Scout the City",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Look Around — Mill three cards. You may put a permanent card from among them into your hand. You gain 3 life. (To mill three cards, put the top three cards of your library into your graveyard.)\n• Bring Down — Destroy target creature with flying.",
)

SPIDERHAM_PETER_PORKER = make_creature(
    name="Spider-Ham, Peter Porker",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Boar", "Hero", "Spider"},
    supertypes={"Legendary"},
    text="When Spider-Ham enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\nAnimal May-Ham — Other Spiders, Boars, Bats, Bears, Birds, Cats, Dogs, Frogs, Jackals, Lizards, Mice, Otters, Rabbits, Raccoons, Rats, Squirrels, Turtles, and Wolves you control get +1/+1.",
)

SPIDERMAN_BROOKLYN_VISIONARY = make_creature(
    name="Spider-Man, Brooklyn Visionary",
    power=4, toughness=3,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Web-slinging {2}{G} (You may cast this spell for {2}{G} if you also return a tapped creature you control to its owner's hand.)\nWhen Spider-Man enters, search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
)

SPIDERREX_DARING_DINO = make_creature(
    name="Spider-Rex, Daring Dino",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur", "Hero", "Spider"},
    supertypes={"Legendary"},
    text="Reach, trample\nWard {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)",
)

SPIDERSMAN_HEROIC_HORDE = make_creature(
    name="Spiders-Man, Heroic Horde",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Hero", "Spider"},
    supertypes={"Legendary"},
    text="Web-slinging {4}{G}{G} (You may cast this spell for {4}{G}{G} if you also return a tapped creature you control to its owner's hand.)\nWhen Spiders-Man enters, if they were cast using web-slinging, you gain 3 life and create two 2/1 green Spider creature tokens with reach.",
)

STRENGTH_OF_WILL = make_instant(
    name="Strength of Will",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Until end of turn, target creature you control gains indestructible and \"Whenever this creature is dealt damage, put that many +1/+1 counters on it.\"",
)

SUPPORTIVE_PARENTS = make_creature(
    name="Supportive Parents",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Citizen", "Human"},
    text="Tap two untapped creatures you control: Add one mana of any color.",
)

TERRIFIC_TEAMUP = make_instant(
    name="Terrific Team-Up",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="This spell costs {2} less to cast if you control a permanent with mana value 4 or greater.\nOne or two target creatures you control each get +1/+0 until end of turn. They each deal damage equal to their power to target creature an opponent controls.",
)

WALL_CRAWL = make_enchantment(
    name="Wall Crawl",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, create a 2/1 green Spider creature token with reach, then you gain 1 life for each Spider you control.\nSpiders you control get +1/+1 and can't be blocked by creatures with defender.",
)

WEB_OF_LIFE_AND_DESTINY = make_enchantment(
    name="Web of Life and Destiny",
    mana_cost="{6}{G}{G}",
    colors={Color.GREEN},
    text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nAt the beginning of combat on your turn, look at the top five cards of your library. You may put a creature card from among them onto the battlefield. Put the rest on the bottom of your library in a random order.",
)

ARAA_HEART_OF_THE_SPIDER = make_creature(
    name="Araña, Heart of the Spider",
    power=3, toughness=3,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Whenever you attack, put a +1/+1 counter on target attacking creature.\nWhenever a modified creature you control deals combat damage to a player, exile the top card of your library. You may play that card this turn. (Equipment, Auras you control, and counters are modifications.)",
)

BIORGANIC_CARAPACE = make_artifact(
    name="Biorganic Carapace",
    mana_cost="{2}{W}{U}",
    text="When this Equipment enters, attach it to target creature you control.\nEquipped creature gets +2/+2 and has \"Whenever this creature deals combat damage to a player, draw a card for each modified creature you control.\" (Equipment, Auras you control, and counters are modifications.)\nEquip {2}",
    subtypes={"Equipment"},
)

CARNAGE_CRIMSON_CHAOS = make_creature(
    name="Carnage, Crimson Chaos",
    power=4, toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Symbiote", "Villain"},
    supertypes={"Legendary"},
    text="Trample\nWhen Carnage enters, return target creature card with mana value 3 or less from your graveyard to the battlefield. It gains \"This creature attacks each combat if able\" and \"When this creature deals combat damage to a player, sacrifice it.\"\nMayhem {B}{R}",
)

CHEERING_CROWD = make_creature(
    name="Cheering Crowd",
    power=2, toughness=2,
    mana_cost="{1}{R/G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Citizen", "Human"},
    text="At the beginning of each player's first main phase, that player may put a +1/+1 counter on this creature. If they do, they add {C} for each counter on it.",
)

COSMIC_SPIDERMAN = make_creature(
    name="Cosmic Spider-Man",
    power=5, toughness=5,
    mana_cost="{W}{U}{B}{R}{G}",
    colors={Color.BLACK, Color.GREEN, Color.RED, Color.BLUE, Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Flying, first strike, trample, lifelink, haste\nAt the beginning of combat on your turn, other Spiders you control gain flying, first strike, trample, lifelink, and haste until end of turn.",
)

DOCTOR_OCTOPUS_MASTER_PLANNER = make_creature(
    name="Doctor Octopus, Master Planner",
    power=4, toughness=8,
    mana_cost="{5}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Scientist", "Villain"},
    supertypes={"Legendary"},
    text="Other Villains you control get +2/+2.\nYour maximum hand size is eight.\nAt the beginning of your end step, if you have fewer than eight cards in hand, draw cards equal to the difference.",
)

GALLANT_CITIZEN = make_creature(
    name="Gallant Citizen",
    power=1, toughness=1,
    mana_cost="{G/W}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Citizen", "Human"},
    text="When this creature enters, draw a card.",
)

GREEN_GOBLIN_REVENANT = make_creature(
    name="Green Goblin, Revenant",
    power=3, toughness=3,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Goblin", "Human", "Villain"},
    supertypes={"Legendary"},
    text="Flying, deathtouch\nWhenever Green Goblin attacks, discard a card. Then draw a card for each card you've discarded this turn.",
)

JACKAL_GENIUS_GENETICIST = make_creature(
    name="Jackal, Genius Geneticist",
    power=1, toughness=1,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Scientist", "Villain"},
    supertypes={"Legendary"},
    text="Trample\nWhenever you cast a creature spell with mana value equal to Jackal's power, copy that spell, except the copy isn't legendary. Then put a +1/+1 counter on Jackal. (The copy becomes a token.)",
)

KRAVEN_PROUD_PREDATOR = make_creature(
    name="Kraven, Proud Predator",
    power=0, toughness=4,
    mana_cost="{1}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Villain", "Warrior"},
    supertypes={"Legendary"},
    text="Vigilance\nTop of the Food Chain — Kraven's power is equal to the greatest mana value among permanents you control.",
)

KRAVEN_THE_HUNTER = make_creature(
    name="Kraven the Hunter",
    power=4, toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Villain", "Warrior"},
    supertypes={"Legendary"},
    text="Trample\nWhenever a creature an opponent controls with the greatest power among creatures that player controls dies, draw a card and put a +1/+1 counter on Kraven the Hunter.",
)

MARY_JANE_WATSON = make_creature(
    name="Mary Jane Watson",
    power=2, toughness=2,
    mana_cost="{1}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Performer"},
    supertypes={"Legendary"},
    text="Whenever a Spider you control enters, draw a card. This ability triggers only once each turn.",
)

MISTER_NEGATIVE = make_creature(
    name="Mister Negative",
    power=5, toughness=5,
    mana_cost="{5}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Vigilance, lifelink\nDarkforce Inversion — When Mister Negative enters, you may exchange life totals with target opponent. If you lost life this way, draw that many cards.",
)

MOB_LOOKOUT = make_creature(
    name="Mob Lookout",
    power=0, toughness=3,
    mana_cost="{1}{U/B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Rogue", "Villain"},
    text="When this creature enters, target creature you control connives. (Draw a card, then discard a card. If you discarded a nonland card, put a +1/+1 counter on that creature.)",
)

MORBIUS_THE_LIVING_VAMPIRE = make_creature(
    name="Morbius the Living Vampire",
    power=3, toughness=1,
    mana_cost="{2}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Scientist", "Vampire", "Villain"},
    supertypes={"Legendary"},
    text="Flying, vigilance, lifelink\n{U}{B}, Exile this card from your graveyard: Look at the top three cards of your library. Put one of them into your hand and the rest on the bottom of your library in any order.",
)

PROWLER_CLAWED_THIEF = make_creature(
    name="Prowler, Clawed Thief",
    power=2, toughness=3,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Rogue", "Villain"},
    supertypes={"Legendary"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhenever another Villain you control enters, Prowler connives. (Draw a card, then discard a card. If you discarded a nonland card, put a +1/+1 counter on this creature.)",
)

PUMPKIN_BOMBARDMENT = make_sorcery(
    name="Pumpkin Bombardment",
    mana_cost="{B/R}",
    colors={Color.BLACK, Color.RED},
    text="As an additional cost to cast this spell, discard a card or pay {2}.\nPumpkin Bombardment deals 3 damage to target creature.",
)

RHINO_BARRELING_BRUTE = make_creature(
    name="Rhino, Barreling Brute",
    power=6, toughness=7,
    mana_cost="{3}{R}{R}{G}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Vigilance, trample, haste\nWhenever Rhino attacks, if you've cast a spell with mana value 4 or greater this turn, draw a card.",
)

RHINOS_RAMPAGE = make_sorcery(
    name="Rhino's Rampage",
    mana_cost="{R/G}",
    colors={Color.GREEN, Color.RED},
    text="Target creature you control gets +1/+0 until end of turn. It fights target creature an opponent controls. When excess damage is dealt to the creature an opponent controls this way, destroy up to one target noncreature artifact with mana value 3 or less.",
)

SCARLET_SPIDER_BEN_REILLY = make_creature(
    name="Scarlet Spider, Ben Reilly",
    power=4, toughness=3,
    mana_cost="{1}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Web-slinging {R}{G} (You may cast this spell for {R}{G} if you also return a tapped creature you control to its owner's hand.)\nTrample\nSensational Save — If Scarlet Spider was cast using web-slinging, he enters with X +1/+1 counters on him, where X is the mana value of the returned creature.",
)

SCARLET_SPIDER_KAINE = make_creature(
    name="Scarlet Spider, Kaine",
    power=2, toughness=1,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhen Scarlet Spider enters, you may discard a card. If you do, put a +1/+1 counter on him.\nMayhem {B/R} (You may cast this card from your graveyard for {B/R} if you discarded it this turn. Timing rules still apply.)",
)

SHRIEK_TREBLEMAKER = make_creature(
    name="Shriek, Treblemaker",
    power=2, toughness=3,
    mana_cost="{2}{B/R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Mutant", "Villain"},
    supertypes={"Legendary"},
    text="At the beginning of your first main phase, you may discard a card. When you do, target creature can't block this turn.\nSonic Blast — Whenever a creature an opponent controls dies, Shriek deals 1 damage to that player.",
)

SILK_WEB_WEAVER = make_creature(
    name="Silk, Web Weaver",
    power=3, toughness=5,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Web-slinging {1}{G}{W} (You may cast this spell for {1}{G}{W} if you also return a tapped creature you control to its owner's hand.)\nWhenever you cast a creature spell, create a 1/1 green and white Human Citizen creature token.\n{3}{G}{W}: Creatures you control get +2/+2 and gain vigilance until end of turn.",
)

SKYWARD_SPIDER = make_creature(
    name="Skyward Spider",
    power=2, toughness=2,
    mana_cost="{W/U}{W/U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    text="Ward {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nThis creature has flying as long as it's modified. (Equipment, Auras you control, and counters are modifications.)",
)

SPDR_PILOTED_BY_PENI = make_artifact_creature(
    name="SP//dr, Piloted by Peni",
    power=4, toughness=4,
    mana_cost="{3}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Hero", "Spider"},
    supertypes={"Legendary"},
    text="Vigilance\nWhen SP//dr enters, put a +1/+1 counter on target creature.\nWhenever a modified creature you control deals combat damage to a player, draw a card. (Equipment, Auras you control, and counters are modifications.)",
)

SPIDER_MANIFESTATION = make_creature(
    name="Spider Manifestation",
    power=2, toughness=2,
    mana_cost="{1}{R/G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Avatar", "Spider"},
    text="Reach\n{T}: Add {R} or {G}.\nWhenever you cast a spell with mana value 4 or greater, untap this creature.",
)

SPIDERGIRL_LEGACY_HERO = make_creature(
    name="Spider-Girl, Legacy Hero",
    power=2, toughness=2,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="During your turn, Spider-Girl has flying.\nWhen Spider-Girl leaves the battlefield, create a 1/1 green and white Human Citizen creature token.",
)

SPIDERMAN_2099 = make_creature(
    name="Spider-Man 2099",
    power=2, toughness=3,
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="From the Future — You can't cast Spider-Man 2099 during your first, second, or third turns of the game.\nDouble strike, vigilance\nAt the beginning of your end step, if you've played a land or cast a spell this turn from anywhere other than your hand, Spider-Man 2099 deals damage equal to his power to any target.",
)

SPIDERMAN_INDIA = make_creature(
    name="Spider-Man India",
    power=4, toughness=4,
    mana_cost="{3}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Web-slinging {1}{G}{W} (You may cast this spell for {1}{G}{W} if you also return a tapped creature you control to its owner's hand.)\nPavitr's Sevā — Whenever you cast a creature spell, put a +1/+1 counter on target creature you control. It gains flying until end of turn.",
)

SPIDERWOMAN_STUNNING_SAVIOR = make_creature(
    name="Spider-Woman, Stunning Savior",
    power=2, toughness=2,
    mana_cost="{1}{W/U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Flying\nVenom Blast — Artifacts and creatures your opponents control enter tapped.",
)

THE_SPOT_LIVING_PORTAL = make_creature(
    name="The Spot, Living Portal",
    power=4, toughness=4,
    mana_cost="{3}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Scientist", "Villain"},
    supertypes={"Legendary"},
    text="When The Spot enters, exile up to one target nonland permanent and up to one target nonland permanent card from a graveyard.\nWhen The Spot dies, put him on the bottom of his owner's library. If you do, return the exiled cards to their owners' hands.",
)

SUNSPIDER_NIMBLE_WEBBER = make_creature(
    name="Sun-Spider, Nimble Webber",
    power=3, toughness=2,
    mana_cost="{3}{W/U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="During your turn, Sun-Spider has flying.\nWhen Sun-Spider enters, search your library for an Aura or Equipment card, reveal it, put it into your hand, then shuffle.",
)

SUPERIOR_SPIDERMAN = make_creature(
    name="Superior Spider-Man",
    power=4, toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Mind Swap — You may have Superior Spider-Man enter as a copy of any creature card in a graveyard, except his name is Superior Spider-Man and he's a 4/4 Spider Human Hero in addition to his other types. When you do, exile that card.",
)

SYMBIOTE_SPIDERMAN = make_creature(
    name="Symbiote Spider-Man",
    power=2, toughness=4,
    mana_cost="{2}{U/B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Hero", "Spider", "Symbiote"},
    supertypes={"Legendary"},
    text="Whenever this creature deals combat damage to a player, look at that many cards from the top of your library. Put one of them into your hand and the rest into your graveyard.\nFind New Host — {2}{U/B}, Exile this card from your graveyard: Put a +1/+1 counter on target creature you control. It gains this card's other abilities. Activate only as a sorcery.",
)

ULTIMATE_GREEN_GOBLIN = make_creature(
    name="Ultimate Green Goblin",
    power=5, toughness=4,
    mana_cost="{1}{B/R}{B/R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Goblin", "Villain"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, discard a card, then create a Treasure token.\nMayhem {2}{B/R} (You may cast this card from your graveyard for {2}{B/R} if you discarded it this turn. Timing rules still apply.)",
)

VULTURE_SCHEMING_SCAVENGER = make_creature(
    name="Vulture, Scheming Scavenger",
    power=4, toughness=6,
    mana_cost="{5}{U/B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Artificer", "Human", "Villain"},
    supertypes={"Legendary"},
    text="Flying\nWhenever Vulture attacks, other Villains you control gain flying until end of turn.",
)

WEBWARRIORS = make_creature(
    name="Web-Warriors",
    power=4, toughness=3,
    mana_cost="{4}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hero", "Spider"},
    text="When this creature enters, put a +1/+1 counter on each other creature you control.",
)

WRAITH_VICIOUS_VIGILANTE = make_creature(
    name="Wraith, Vicious Vigilante",
    power=1, toughness=1,
    mana_cost="{1}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Detective", "Hero", "Human"},
    supertypes={"Legendary"},
    text="Double strike\nFear Gas — Wraith can't be blocked.",
)

BAGEL_AND_SCHMEAR = make_artifact(
    name="Bagel and Schmear",
    mana_cost="{1}",
    text="Share — {W}, {T}, Sacrifice this artifact: Put a +1/+1 counter on up to one target creature. Draw a card. Activate only as a sorcery.\nNosh — {2}, {T}, Sacrifice this artifact: You gain 3 life and draw a card.",
    subtypes={"Food"},
)

DOC_OCKS_TENTACLES = make_artifact(
    name="Doc Ock's Tentacles",
    mana_cost="{1}",
    text="Whenever a creature you control with mana value 5 or greater enters, you may attach this Equipment to it.\nEquipped creature gets +4/+4.\nEquip {5}",
    subtypes={"Equipment"},
)

EERIE_GRAVESTONE = make_artifact(
    name="Eerie Gravestone",
    mana_cost="{2}",
    text="When this artifact enters, draw a card.\n{1}{B}, Sacrifice this artifact: Mill four cards. You may put a creature card from among them into your hand. (To mill four cards, put the top four cards of your library into your graveyard.)",
)

HOT_DOG_CART = make_artifact(
    name="Hot Dog Cart",
    mana_cost="{3}",
    text="When this artifact enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\n{T}: Add one mana of any color.",
)

INTERDIMENSIONAL_WEB_WATCH = make_artifact(
    name="Interdimensional Web Watch",
    mana_cost="{4}",
    text="When this artifact enters, exile the top two cards of your library. Until the end of your next turn, you may play those cards.\n{T}: Add two mana in any combination of colors. Spend this mana only to cast spells from exile.",
)

IRON_SPIDER_STARK_UPGRADE = make_artifact_creature(
    name="Iron Spider, Stark Upgrade",
    power=2, toughness=3,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Hero", "Spider"},
    supertypes={"Legendary"},
    text="Vigilance\n{T}: Put a +1/+1 counter on each artifact creature and/or Vehicle you control.\n{2}, Remove two +1/+1 counters from among artifacts you control: Draw a card.",
)

LIVING_BRAIN_MECHANICAL_MARVEL = make_artifact_creature(
    name="Living Brain, Mechanical Marvel",
    power=3, toughness=3,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Robot", "Villain"},
    supertypes={"Legendary"},
    text="At the beginning of combat on your turn, target non-Equipment artifact you control becomes an artifact creature with base power and toughness 3/3 until end of turn. Untap it.",
)

MECHANICAL_MOBSTER = make_artifact_creature(
    name="Mechanical Mobster",
    power=2, toughness=1,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Human", "Robot", "Villain"},
    text="When this creature enters, exile up to one target card from a graveyard. Target creature you control connives. (Draw a card, then discard a card. If you discarded a nonland card, put a +1/+1 counter on that creature.)",
)

NEWS_HELICOPTER = make_artifact_creature(
    name="News Helicopter",
    power=1, toughness=1,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Construct"},
    text="Flying\nWhen this creature enters, create a 1/1 green and white Human Citizen creature token.",
)

PASSENGER_FERRY = make_artifact(
    name="Passenger Ferry",
    mana_cost="{3}",
    text="Whenever this Vehicle attacks, you may pay {U}. When you do, another target attacking creature can't be blocked this turn.\nCrew 2 (Tap any number of creatures you control with total power 2 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
)

PETER_PARKERS_CAMERA = make_artifact(
    name="Peter Parker's Camera",
    mana_cost="{1}",
    text="This artifact enters with three film counters on it.\n{2}, {T}, Remove a film counter from this artifact: Copy target activated or triggered ability you control. You may choose new targets for the copy.",
)

ROCKETPOWERED_GOBLIN_GLIDER = make_artifact(
    name="Rocket-Powered Goblin Glider",
    mana_cost="{3}",
    text="When this Equipment enters, if it was cast from your graveyard, attach it to target creature you control.\nEquipped creature gets +2/+0 and has flying and haste.\nEquip {2}\nMayhem {2}",
    subtypes={"Equipment"},
)

SPIDERBOT = make_artifact_creature(
    name="Spider-Bot",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Robot", "Scout", "Spider"},
    text="Reach\nWhen this creature enters, you may search your library for a basic land card, reveal it, then shuffle and put that card on top.",
)

SPIDERMOBILE = make_artifact(
    name="Spider-Mobile",
    mana_cost="{3}",
    text="Trample\nWhenever this Vehicle attacks or blocks, it gets +1/+1 until end of turn for each Spider you control.\nCrew 2",
    subtypes={"Vehicle"},
)

SPIDERSLAYER_HATRED_HONED = make_artifact_creature(
    name="Spider-Slayer, Hatred Honed",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Whenever Spider-Slayer deals damage to a Spider, destroy that creature.\n{6}, Exile this card from your graveyard: Create two tapped 1/1 colorless Robot artifact creature tokens with flying.",
)

SPIDERSUIT = make_artifact(
    name="Spider-Suit",
    mana_cost="{1}",
    text="Equipped creature gets +2/+2 and is a Spider Hero in addition to its other types.\nEquip {3} ({3}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

STEEL_WRECKING_BALL = make_artifact(
    name="Steel Wrecking Ball",
    mana_cost="{5}",
    text="When this artifact enters, it deals 5 damage to target creature.\n{1}{R}, Discard this card: Destroy target artifact.",
)

SUBWAY_TRAIN = make_artifact(
    name="Subway Train",
    mana_cost="{2}",
    text="When this Vehicle enters, you may pay {G}. If you do, search your library for a basic land card, reveal it, put it into your hand, then shuffle.\nCrew 2 (Tap any number of creatures you control with total power 2 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
)

DAILY_BUGLE_BUILDING = make_land(
    name="Daily Bugle Building",
    text="{T}: Add {C}.\n{1}, {T}: Add one mana of any color.\nSmear Campaign — {1}, {T}: Target legendary creature gains menace until end of turn. Activate only as a sorcery.",
)

MULTIVERSAL_PASSAGE = make_land(
    name="Multiversal Passage",
    text="As this land enters, choose a basic land type. Then you may pay 2 life. If you don't, it enters tapped.\nThis land is the chosen type.",
)

OMINOUS_ASYLUM = make_land(
    name="Ominous Asylum",
    text="This land enters tapped.\n{T}: Add {B} or {R}.\n{4}, {T}: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

OSCORP_INDUSTRIES = make_land(
    name="Oscorp Industries",
    text="This land enters tapped.\nWhen this land enters from a graveyard, you lose 2 life.\n{T}: Add {U}, {B}, or {R}.\nMayhem (You may play this card from your graveyard if you discarded it this turn. Timing rules still apply.)",
)

SAVAGE_MANSION = make_land(
    name="Savage Mansion",
    text="This land enters tapped.\n{T}: Add {R} or {G}.\n{4}, {T}: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

SINISTER_HIDEOUT = make_land(
    name="Sinister Hideout",
    text="This land enters tapped.\n{T}: Add {U} or {B}.\n{4}, {T}: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

SUBURBAN_SANCTUARY = make_land(
    name="Suburban Sanctuary",
    text="This land enters tapped.\n{T}: Add {G} or {W}.\n{4}, {T}: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

UNIVERSITY_CAMPUS = make_land(
    name="University Campus",
    text="This land enters tapped.\n{T}: Add {W} or {U}.\n{4}, {T}: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

URBAN_RETREAT = make_land(
    name="Urban Retreat",
    text="This land enters tapped.\n{T}: Add {G}, {W}, or {U}.\n{2}, Return a tapped creature you control to its owner's hand: Put this card from your hand onto the battlefield. Activate only as a sorcery.",
)

VIBRANT_CITYSCAPE = make_land(
    name="Vibrant Cityscape",
    text="{T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
)

PLAINS = make_land(
    name="Plains",
    text="({T}: Add {W}.)",
    subtypes={"Plains"},
    supertypes={"Basic"},
)

ISLAND = make_land(
    name="Island",
    text="({T}: Add {U}.)",
    subtypes={"Island"},
    supertypes={"Basic"},
)

SWAMP = make_land(
    name="Swamp",
    text="({T}: Add {B}.)",
    subtypes={"Swamp"},
    supertypes={"Basic"},
)

MOUNTAIN = make_land(
    name="Mountain",
    text="({T}: Add {R}.)",
    subtypes={"Mountain"},
    supertypes={"Basic"},
)

FOREST = make_land(
    name="Forest",
    text="({T}: Add {G}.)",
    subtypes={"Forest"},
    supertypes={"Basic"},
)

# =============================================================================
# CARD REGISTRY
# =============================================================================

SPIDER_MAN_CARDS = {
    "Anti-Venom, Horrifying Healer": ANTIVENOM_HORRIFYING_HEALER,
    "Arachne, Psionic Weaver": ARACHNE_PSIONIC_WEAVER,
    "Aunt May": AUNT_MAY,
    "City Pigeon": CITY_PIGEON,
    "Costume Closet": COSTUME_CLOSET,
    "Daily Bugle Reporters": DAILY_BUGLE_REPORTERS,
    "Flash Thompson, Spider-Fan": FLASH_THOMPSON_SPIDERFAN,
    "Friendly Neighborhood": FRIENDLY_NEIGHBORHOOD,
    "Origin of Spider-Man": ORIGIN_OF_SPIDERMAN,
    "Peter Parker": PETER_PARKER,
    "Rent Is Due": RENT_IS_DUE,
    "Selfless Police Captain": SELFLESS_POLICE_CAPTAIN,
    "Silver Sable, Mercenary Leader": SILVER_SABLE_MERCENARY_LEADER,
    "Spectacular Spider-Man": SPECTACULAR_SPIDERMAN,
    "Spectacular Tactics": SPECTACULAR_TACTICS,
    "Spider-Man, Web-Slinger": SPIDERMAN_WEBSLINGER,
    "Spider-UK": SPIDERUK,
    "Starling, Aerial Ally": STARLING_AERIAL_ALLY,
    "Sudden Strike": SUDDEN_STRIKE,
    "Thwip!": THWIP,
    "Web Up": WEB_UP,
    "Web-Shooters": WEBSHOOTERS,
    "Wild Pack Squad": WILD_PACK_SQUAD,
    "With Great Power...": WITH_GREAT_POWER,
    "Amazing Acrobatics": AMAZING_ACROBATICS,
    "Beetle, Legacy Criminal": BEETLE_LEGACY_CRIMINAL,
    "Chameleon, Master of Disguise": CHAMELEON_MASTER_OF_DISGUISE,
    "The Clone Saga": THE_CLONE_SAGA,
    "Doc Ock, Sinister Scientist": DOC_OCK_SINISTER_SCIENTIST,
    "Doc Ock's Henchmen": DOC_OCKS_HENCHMEN,
    "Flying Octobot": FLYING_OCTOBOT,
    "Hide on the Ceiling": HIDE_ON_THE_CEILING,
    "Hydro-Man, Fluid Felon": HYDROMAN_FLUID_FELON,
    "Impostor Syndrome": IMPOSTOR_SYNDROME,
    "Lady Octopus, Inspired Inventor": LADY_OCTOPUS_INSPIRED_INVENTOR,
    "Madame Web, Clairvoyant": MADAME_WEB_CLAIRVOYANT,
    "Mysterio, Master of Illusion": MYSTERIO_MASTER_OF_ILLUSION,
    "Mysterio's Phantasm": MYSTERIOS_PHANTASM,
    "Norman Osborn": NORMAN_OSBORN,
    "Oscorp Research Team": OSCORP_RESEARCH_TEAM,
    "Robotics Mastery": ROBOTICS_MASTERY,
    "School Daze": SCHOOL_DAZE,
    "Secret Identity": SECRET_IDENTITY,
    "Spider-Byte, Web Warden": SPIDERBYTE_WEB_WARDEN,
    "Spider-Man No More": SPIDERMAN_NO_MORE,
    "Spider-Sense": SPIDERSENSE,
    "Unstable Experiment": UNSTABLE_EXPERIMENT,
    "Whoosh!": WHOOSH,
    "Agent Venom": AGENT_VENOM,
    "Alien Symbiosis": ALIEN_SYMBIOSIS,
    "Behold the Sinister Six!": BEHOLD_THE_SINISTER_SIX,
    "Black Cat, Cunning Thief": BLACK_CAT_CUNNING_THIEF,
    "Common Crook": COMMON_CROOK,
    "The Death of Gwen Stacy": THE_DEATH_OF_GWEN_STACY,
    "Eddie Brock": EDDIE_BROCK,
    "Gwenom, Remorseless": GWENOM_REMORSELESS,
    "Inner Demons Gangsters": INNER_DEMONS_GANGSTERS,
    "Merciless Enforcers": MERCILESS_ENFORCERS,
    "Morlun, Devourer of Spiders": MORLUN_DEVOURER_OF_SPIDERS,
    "Parker Luck": PARKER_LUCK,
    "Prison Break": PRISON_BREAK,
    "Risky Research": RISKY_RESEARCH,
    "Sandman's Quicksand": SANDMANS_QUICKSAND,
    "Scorpion, Seething Striker": SCORPION_SEETHING_STRIKER,
    "Scorpion's Sting": SCORPIONS_STING,
    "The Soul Stone": THE_SOUL_STONE,
    "Spider-Man Noir": SPIDERMAN_NOIR,
    "The Spot's Portal": THE_SPOTS_PORTAL,
    "Swarm, Being of Bees": SWARM_BEING_OF_BEES,
    "Tombstone, Career Criminal": TOMBSTONE_CAREER_CRIMINAL,
    "Venom, Evil Unleashed": VENOM_EVIL_UNLEASHED,
    "Venomized Cat": VENOMIZED_CAT,
    "Venom's Hunger": VENOMS_HUNGER,
    "Villainous Wrath": VILLAINOUS_WRATH,
    "Angry Rabble": ANGRY_RABBLE,
    "Electro, Assaulting Battery": ELECTRO_ASSAULTING_BATTERY,
    "Electro's Bolt": ELECTROS_BOLT,
    "Gwen Stacy": GWEN_STACY,
    "Heroes' Hangout": HEROES_HANGOUT,
    "Hobgoblin, Mantled Marauder": HOBGOBLIN_MANTLED_MARAUDER,
    "J. Jonah Jameson": J_JONAH_JAMESON,
    "Masked Meower": MASKED_MEOWER,
    "Maximum Carnage": MAXIMUM_CARNAGE,
    "Molten Man, Inferno Incarnate": MOLTEN_MAN_INFERNO_INCARNATE,
    "Raging Goblinoids": RAGING_GOBLINOIDS,
    "Romantic Rendezvous": ROMANTIC_RENDEZVOUS,
    "Shadow of the Goblin": SHADOW_OF_THE_GOBLIN,
    "Shock": SHOCK,
    "Shocker, Unshakable": SHOCKER_UNSHAKABLE,
    "Spider-Gwen, Free Spirit": SPIDERGWEN_FREE_SPIRIT,
    "Spider-Islanders": SPIDERISLANDERS,
    "Spider-Punk": SPIDERPUNK,
    "Spider-Verse": SPIDERVERSE,
    "Spinneret and Spiderling": SPINNERET_AND_SPIDERLING,
    "Stegron the Dinosaur Man": STEGRON_THE_DINOSAUR_MAN,
    "Superior Foes of Spider-Man": SUPERIOR_FOES_OF_SPIDERMAN,
    "Taxi Driver": TAXI_DRIVER,
    "Wisecrack": WISECRACK,
    "Damage Control Crew": DAMAGE_CONTROL_CREW,
    "Ezekiel Sims, Spider-Totem": EZEKIEL_SIMS_SPIDERTOTEM,
    "Grow Extra Arms": GROW_EXTRA_ARMS,
    "Guy in the Chair": GUY_IN_THE_CHAIR,
    "Kapow!": KAPOW,
    "Kraven's Cats": KRAVENS_CATS,
    "Kraven's Last Hunt": KRAVENS_LAST_HUNT,
    "Lizard, Connors's Curse": LIZARD_CONNORSS_CURSE,
    "Lurking Lizards": LURKING_LIZARDS,
    "Miles Morales": MILES_MORALES,
    "Pictures of Spider-Man": PICTURES_OF_SPIDERMAN,
    "Professional Wrestler": PROFESSIONAL_WRESTLER,
    "Radioactive Spider": RADIOACTIVE_SPIDER,
    "Sandman, Shifting Scoundrel": SANDMAN_SHIFTING_SCOUNDREL,
    "Scout the City": SCOUT_THE_CITY,
    "Spider-Ham, Peter Porker": SPIDERHAM_PETER_PORKER,
    "Spider-Man, Brooklyn Visionary": SPIDERMAN_BROOKLYN_VISIONARY,
    "Spider-Rex, Daring Dino": SPIDERREX_DARING_DINO,
    "Spiders-Man, Heroic Horde": SPIDERSMAN_HEROIC_HORDE,
    "Strength of Will": STRENGTH_OF_WILL,
    "Supportive Parents": SUPPORTIVE_PARENTS,
    "Terrific Team-Up": TERRIFIC_TEAMUP,
    "Wall Crawl": WALL_CRAWL,
    "Web of Life and Destiny": WEB_OF_LIFE_AND_DESTINY,
    "Araña, Heart of the Spider": ARAA_HEART_OF_THE_SPIDER,
    "Biorganic Carapace": BIORGANIC_CARAPACE,
    "Carnage, Crimson Chaos": CARNAGE_CRIMSON_CHAOS,
    "Cheering Crowd": CHEERING_CROWD,
    "Cosmic Spider-Man": COSMIC_SPIDERMAN,
    "Doctor Octopus, Master Planner": DOCTOR_OCTOPUS_MASTER_PLANNER,
    "Gallant Citizen": GALLANT_CITIZEN,
    "Green Goblin, Revenant": GREEN_GOBLIN_REVENANT,
    "Jackal, Genius Geneticist": JACKAL_GENIUS_GENETICIST,
    "Kraven, Proud Predator": KRAVEN_PROUD_PREDATOR,
    "Kraven the Hunter": KRAVEN_THE_HUNTER,
    "Mary Jane Watson": MARY_JANE_WATSON,
    "Mister Negative": MISTER_NEGATIVE,
    "Mob Lookout": MOB_LOOKOUT,
    "Morbius the Living Vampire": MORBIUS_THE_LIVING_VAMPIRE,
    "Prowler, Clawed Thief": PROWLER_CLAWED_THIEF,
    "Pumpkin Bombardment": PUMPKIN_BOMBARDMENT,
    "Rhino, Barreling Brute": RHINO_BARRELING_BRUTE,
    "Rhino's Rampage": RHINOS_RAMPAGE,
    "Scarlet Spider, Ben Reilly": SCARLET_SPIDER_BEN_REILLY,
    "Scarlet Spider, Kaine": SCARLET_SPIDER_KAINE,
    "Shriek, Treblemaker": SHRIEK_TREBLEMAKER,
    "Silk, Web Weaver": SILK_WEB_WEAVER,
    "Skyward Spider": SKYWARD_SPIDER,
    "SP//dr, Piloted by Peni": SPDR_PILOTED_BY_PENI,
    "Spider Manifestation": SPIDER_MANIFESTATION,
    "Spider-Girl, Legacy Hero": SPIDERGIRL_LEGACY_HERO,
    "Spider-Man 2099": SPIDERMAN_2099,
    "Spider-Man India": SPIDERMAN_INDIA,
    "Spider-Woman, Stunning Savior": SPIDERWOMAN_STUNNING_SAVIOR,
    "The Spot, Living Portal": THE_SPOT_LIVING_PORTAL,
    "Sun-Spider, Nimble Webber": SUNSPIDER_NIMBLE_WEBBER,
    "Superior Spider-Man": SUPERIOR_SPIDERMAN,
    "Symbiote Spider-Man": SYMBIOTE_SPIDERMAN,
    "Ultimate Green Goblin": ULTIMATE_GREEN_GOBLIN,
    "Vulture, Scheming Scavenger": VULTURE_SCHEMING_SCAVENGER,
    "Web-Warriors": WEBWARRIORS,
    "Wraith, Vicious Vigilante": WRAITH_VICIOUS_VIGILANTE,
    "Bagel and Schmear": BAGEL_AND_SCHMEAR,
    "Doc Ock's Tentacles": DOC_OCKS_TENTACLES,
    "Eerie Gravestone": EERIE_GRAVESTONE,
    "Hot Dog Cart": HOT_DOG_CART,
    "Interdimensional Web Watch": INTERDIMENSIONAL_WEB_WATCH,
    "Iron Spider, Stark Upgrade": IRON_SPIDER_STARK_UPGRADE,
    "Living Brain, Mechanical Marvel": LIVING_BRAIN_MECHANICAL_MARVEL,
    "Mechanical Mobster": MECHANICAL_MOBSTER,
    "News Helicopter": NEWS_HELICOPTER,
    "Passenger Ferry": PASSENGER_FERRY,
    "Peter Parker's Camera": PETER_PARKERS_CAMERA,
    "Rocket-Powered Goblin Glider": ROCKETPOWERED_GOBLIN_GLIDER,
    "Spider-Bot": SPIDERBOT,
    "Spider-Mobile": SPIDERMOBILE,
    "Spider-Slayer, Hatred Honed": SPIDERSLAYER_HATRED_HONED,
    "Spider-Suit": SPIDERSUIT,
    "Steel Wrecking Ball": STEEL_WRECKING_BALL,
    "Subway Train": SUBWAY_TRAIN,
    "Daily Bugle Building": DAILY_BUGLE_BUILDING,
    "Multiversal Passage": MULTIVERSAL_PASSAGE,
    "Ominous Asylum": OMINOUS_ASYLUM,
    "Oscorp Industries": OSCORP_INDUSTRIES,
    "Savage Mansion": SAVAGE_MANSION,
    "Sinister Hideout": SINISTER_HIDEOUT,
    "Suburban Sanctuary": SUBURBAN_SANCTUARY,
    "University Campus": UNIVERSITY_CAMPUS,
    "Urban Retreat": URBAN_RETREAT,
    "Vibrant Cityscape": VIBRANT_CITYSCAPE,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
}

print(f"Loaded {len(SPIDER_MAN_CARDS)} Marvels_Spider-Man cards")
