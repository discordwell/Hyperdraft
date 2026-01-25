"""
Foundations (FDN) Card Implementations

Real card data fetched from Scryfall API.
517 cards in set.
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

SIRE_OF_SEVEN_DEATHS = make_creature(
    name="Sire of Seven Deaths",
    power=7, toughness=7,
    mana_cost="{7}",
    colors=set(),
    subtypes={"Eldrazi"},
    text="First strike, vigilance\nMenace, trample\nReach, lifelink\nWard—Pay 7 life.",
)

ARAHBO_THE_FIRST_FANG = make_creature(
    name="Arahbo, the First Fang",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Avatar", "Cat"},
    supertypes={"Legendary"},
    text="Other Cats you control get +1/+1.\nWhenever Arahbo or another nontoken Cat you control enters, create a 1/1 white Cat creature token.",
)

ARMASAUR_GUIDE = make_creature(
    name="Armasaur Guide",
    power=4, toughness=4,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Dinosaur"},
    text="Vigilance (Attacking doesn't cause this creature to tap.)\nWhenever you attack with three or more creatures, put a +1/+1 counter on target creature you control.",
)

CAT_COLLECTOR = make_creature(
    name="Cat Collector",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Citizen", "Human"},
    text="When this creature enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\nWhenever you gain life for the first time during each of your turns, create a 1/1 white Cat creature token.",
)

CELESTIAL_ARMOR = make_artifact(
    name="Celestial Armor",
    mana_cost="{2}{W}",
    text="Flash (You may cast this spell any time you could cast an instant.)\nWhen this Equipment enters, attach it to target creature you control. That creature gains hexproof and indestructible until end of turn.\nEquipped creature gets +2/+0 and has flying.\nEquip {3}{W} ({3}{W}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

CLAWS_OUT = make_instant(
    name="Claws Out",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Affinity for Cats (This spell costs {1} less to cast for each Cat you control.)\nCreatures you control get +2/+2 until end of turn.",
)

CRYSTAL_BARRICADE = make_artifact_creature(
    name="Crystal Barricade",
    power=0, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Wall"},
    text="Defender (This creature can't attack.)\nYou have hexproof. (You can't be the target of spells or abilities your opponents control.)\nPrevent all noncombat damage that would be dealt to other creatures you control.",
)

DAUNTLESS_VETERAN = make_creature(
    name="Dauntless Veteran",
    power=2, toughness=2,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Whenever this creature attacks, creatures you control get +1/+1 until end of turn.",
)

DAZZLING_ANGEL = make_creature(
    name="Dazzling Angel",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nWhenever another creature you control enters, you gain 1 life.",
)

DIVINE_RESILIENCE = make_instant(
    name="Divine Resilience",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Kicker {2}{W} (You may pay an additional {2}{W} as you cast this spell.)\nTarget creature you control gains indestructible until end of turn. If this spell was kicked, instead any number of target creatures you control gain indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy them.)",
)

EXEMPLAR_OF_LIGHT = make_creature(
    name="Exemplar of Light",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nWhenever you gain life, put a +1/+1 counter on this creature.\nWhenever you put one or more +1/+1 counters on this creature, draw a card. This ability triggers only once each turn.",
)

FELIDAR_SAVIOR = make_creature(
    name="Felidar Savior",
    power=2, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Beast", "Cat"},
    text="Lifelink (Damage dealt by this creature also causes you to gain that much life.)\nWhen this creature enters, put a +1/+1 counter on each of up to two other target creatures you control.",
)

FLEETING_FLIGHT = make_instant(
    name="Fleeting Flight",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Put a +1/+1 counter on target creature. It gains flying until end of turn. Prevent all combat damage that would be dealt to it this turn.",
)

GUARDED_HEIR = make_creature(
    name="Guarded Heir",
    power=1, toughness=1,
    mana_cost="{5}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    text="Lifelink (Damage dealt by this creature also causes you to gain that much life.)\nWhen this creature enters, create two 3/3 white Knight creature tokens.",
)

HARE_APPARENT = make_creature(
    name="Hare Apparent",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Noble", "Rabbit"},
    text="When this creature enters, create a number of 1/1 white Rabbit creature tokens equal to the number of other creatures you control named Hare Apparent.\nA deck can have any number of cards named Hare Apparent.",
)

HELPFUL_HUNTER = make_creature(
    name="Helpful Hunter",
    power=1, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cat"},
    text="When this creature enters, draw a card.",
)

HERALD_OF_ETERNAL_DAWN = make_creature(
    name="Herald of Eternal Dawn",
    power=6, toughness=6,
    mana_cost="{4}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nFlying\nYou can't lose the game and your opponents can't win the game.",
)

INSPIRING_PALADIN = make_creature(
    name="Inspiring Paladin",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="During your turn, this creature has first strike. (It deals combat damage before creatures without first strike.)\nDuring your turn, creatures you control with +1/+1 counters on them have first strike.",
)

JOUST_THROUGH = make_instant(
    name="Joust Through",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Joust Through deals 3 damage to target attacking or blocking creature. You gain 1 life.",
)

LUMINOUS_REBUKE = make_instant(
    name="Luminous Rebuke",
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    text="This spell costs {3} less to cast if it targets a tapped creature.\nDestroy target creature.",
)

PRIDEFUL_PARENT = make_creature(
    name="Prideful Parent",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Cat"},
    text="Vigilance (Attacking doesn't cause this creature to tap.)\nWhen this creature enters, create a 1/1 white Cat creature token.",
)

RAISE_THE_PAST = make_sorcery(
    name="Raise the Past",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Return all creature cards with mana value 2 or less from your graveyard to the battlefield.",
)

SKYKNIGHT_SQUIRE = make_creature(
    name="Skyknight Squire",
    power=1, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Scout"},
    text="Whenever another creature you control enters, put a +1/+1 counter on this creature.\nAs long as this creature has three or more +1/+1 counters on it, it has flying and is a Knight in addition to its other types.",
)

SQUAD_RALLIER = make_creature(
    name="Squad Rallier",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="{2}{W}: Look at the top four cards of your library. You may reveal a creature card with power 2 or less from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
)

SUNBLESSED_HEALER = make_creature(
    name="Sun-Blessed Healer",
    power=3, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Human"},
    text="Kicker {1}{W} (You may pay an additional {1}{W} as you cast this spell.)\nLifelink (Damage dealt by this creature also causes you to gain that much life.)\nWhen this creature enters, if it was kicked, return target nonland permanent card with mana value 2 or less from your graveyard to the battlefield.",
)

TWINBLADE_BLESSING = make_enchantment(
    name="Twinblade Blessing",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    text="Flash (You may cast this spell any time you could cast an instant.)\nEnchant creature\nEnchanted creature has double strike. (It deals both first-strike and regular combat damage.)",
    subtypes={"Aura"},
)

VALKYRIES_CALL = make_enchantment(
    name="Valkyrie's Call",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Whenever a nontoken, non-Angel creature you control dies, return that card to the battlefield under its owner's control with a +1/+1 counter on it. It has flying and is an Angel in addition to its other types.",
)

VANGUARD_SERAPH = make_creature(
    name="Vanguard Seraph",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Angel", "Warrior"},
    text="Flying\nWhenever you gain life for the first time each turn, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

ARCANE_EPIPHANY = make_instant(
    name="Arcane Epiphany",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="This spell costs {1} less to cast if you control a Wizard.\nDraw three cards.",
)

ARCHMAGE_OF_RUNES = make_creature(
    name="Archmage of Runes",
    power=3, toughness=6,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Giant", "Wizard"},
    text="Instant and sorcery spells you cast cost {1} less to cast.\nWhenever you cast an instant or sorcery spell, draw a card.",
)

BIGFIN_BOUNCER = make_creature(
    name="Bigfin Bouncer",
    power=3, toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Pirate", "Shark"},
    text="When this creature enters, return target creature an opponent controls to its owner's hand.",
)

CEPHALID_INKMAGE = make_creature(
    name="Cephalid Inkmage",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Octopus", "Wizard"},
    text="When this creature enters, surveil 3. (Look at the top three cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\nThreshold — This creature can't be blocked as long as there are seven or more cards in your graveyard.",
)

CLINQUANT_SKYMAGE = make_creature(
    name="Clinquant Skymage",
    power=1, toughness=1,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Wizard"},
    text="Flying\nWhenever you draw a card, put a +1/+1 counter on this creature.",
)

CURATOR_OF_DESTINIES = make_creature(
    name="Curator of Destinies",
    power=5, toughness=5,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Sphinx"},
    text="This spell can't be countered.\nFlying\nWhen this creature enters, look at the top five cards of your library and separate them into a face-down pile and a face-up pile. An opponent chooses one of those piles. Put that pile into your hand and the other into your graveyard.",
)

DRAKE_HATCHER = make_creature(
    name="Drake Hatcher",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Vigilance, prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nWhenever this creature deals combat damage to a player, put that many incubation counters on it.\nRemove three incubation counters from this creature: Create a 2/2 blue Drake creature token with flying.",
)

ELEMENTALIST_ADEPT = make_creature(
    name="Elementalist Adept",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nProwess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)",
)

ERUDITE_WIZARD = make_creature(
    name="Erudite Wizard",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Whenever you draw your second card each turn, put a +1/+1 counter on this creature.",
)

FAEBLOOM_TRICK = make_instant(
    name="Faebloom Trick",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Create two 1/1 blue Faerie creature tokens with flying. When you do, tap target creature an opponent controls.",
)

GRAPPLING_KRAKEN = make_creature(
    name="Grappling Kraken",
    power=5, toughness=6,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Kraken"},
    text="Landfall — Whenever a land you control enters, tap target creature an opponent controls and put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

HIGH_FAE_TRICKSTER = make_creature(
    name="High Fae Trickster",
    power=4, toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nFlying\nYou may cast spells as though they had flash.",
)

HOMUNCULUS_HORDE = make_creature(
    name="Homunculus Horde",
    power=2, toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Homunculus"},
    text="Whenever you draw your second card each turn, create a token that's a copy of this creature.",
)

ICEWIND_ELEMENTAL = make_creature(
    name="Icewind Elemental",
    power=3, toughness=4,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="Flying\nWhen this creature enters, draw a card, then discard a card.",
)

INSPIRATION_FROM_BEYOND = make_sorcery(
    name="Inspiration from Beyond",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Mill three cards, then return an instant or sorcery card from your graveyard to your hand.\nFlashback {5}{U}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

KAITO_CUNNING_INFILTRATOR = make_planeswalker(
    name="Kaito, Cunning Infiltrator",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    loyalty=3,
    subtypes={"Kaito"},
    supertypes={"Legendary"},
    text="Whenever a creature you control deals combat damage to a player, put a loyalty counter on Kaito.\n+1: Up to one target creature you control can't be blocked this turn. Draw a card, then discard a card.\n−2: Create a 2/1 blue Ninja creature token.\n−9: You get an emblem with \"Whenever a player casts a spell, you create a 2/1 blue Ninja creature token.\"",
)

KIORA_THE_RISING_TIDE = make_creature(
    name="Kiora, the Rising Tide",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Noble"},
    supertypes={"Legendary"},
    text="When Kiora enters, draw two cards, then discard two cards.\nThreshold — Whenever Kiora attacks, if there are seven or more cards in your graveyard, you may create Scion of the Deep, a legendary 8/8 blue Octopus creature token.",
)

LUNAR_INSIGHT = make_sorcery(
    name="Lunar Insight",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw a card for each different mana value among nonland permanents you control.",
)

MISCHIEVOUS_MYSTIC = make_creature(
    name="Mischievous Mystic",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Flying\nWhenever you draw your second card each turn, create a 1/1 blue Faerie creature token with flying.",
)

REFUTE = make_instant(
    name="Refute",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell. Draw a card, then discard a card.",
)

RUNESEALED_WALL = make_artifact_creature(
    name="Rune-Sealed Wall",
    power=0, toughness=6,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Wall"},
    text="Defender\n{T}: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

SKYSHIP_BUCCANEER = make_creature(
    name="Skyship Buccaneer",
    power=4, toughness=3,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="Flying\nRaid — When this creature enters, if you attacked this turn, draw a card.",
)

SPHINX_OF_FORGOTTEN_LORE = make_creature(
    name="Sphinx of Forgotten Lore",
    power=3, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Sphinx"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nFlying\nWhenever this creature attacks, target instant or sorcery card in your graveyard gains flashback until end of turn. The flashback cost is equal to that card's mana cost. (You may cast that card from your graveyard for its flashback cost. Then exile it.)",
)

STRIX_LOOKOUT = make_creature(
    name="Strix Lookout",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Bird"},
    text="Flying, vigilance (Attacking doesn't cause this creature to tap.)\n{1}{U}, {T}: Draw a card, then discard a card.",
)

UNCHARTED_VOYAGE = make_instant(
    name="Uncharted Voyage",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Target creature's owner puts it on their choice of the top or bottom of their library.\nSurveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

ABYSSAL_HARVESTER = make_creature(
    name="Abyssal Harvester",
    power=3, toughness=2,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Warlock"},
    text="{T}: Exile target creature card from a graveyard that was put there this turn. Create a token that's a copy of it, except it's a Nightmare in addition to its other types. Then exile all other Nightmare tokens you control.",
)

ARBITER_OF_WOE = make_creature(
    name="Arbiter of Woe",
    power=5, toughness=4,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="As an additional cost to cast this spell, sacrifice a creature.\nFlying\nWhen this creature enters, each opponent discards a card and loses 2 life. You draw a card and gain 2 life.",
)

BILLOWING_SHRIEKMASS = make_creature(
    name="Billowing Shriekmass",
    power=2, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Flying\nWhen this creature enters, mill three cards. (Put the top three cards of your library into your graveyard.)\nThreshold — This creature gets +2/+1 as long as there are seven or more cards in your graveyard.",
)

BLASPHEMOUS_EDICT = make_sorcery(
    name="Blasphemous Edict",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="You may pay {B} rather than pay this spell's mana cost if there are thirteen or more creatures on the battlefield.\nEach player sacrifices thirteen creatures of their choice.",
)

BLOODTHIRSTY_CONQUEROR = make_creature(
    name="Bloodthirsty Conqueror",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Knight", "Vampire"},
    text="Flying, deathtouch\nWhenever an opponent loses life, you gain that much life. (Damage causes loss of life.)",
)

CRYPT_FEASTER = make_creature(
    name="Crypt Feaster",
    power=3, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nThreshold — Whenever this creature attacks, if there are seven or more cards in your graveyard, this creature gets +2/+0 until end of turn.",
)

GUTLESS_PLUNDERER = make_creature(
    name="Gutless Plunderer",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Pirate", "Skeleton"},
    text="Deathtouch (Any amount of damage this deals to a creature is enough to destroy it.)\nRaid — When this creature enters, if you attacked this turn, look at the top three cards of your library. You may put one of those cards back on top of your library. Put the rest into your graveyard.",
)

HIGHSOCIETY_HUNTER = make_creature(
    name="High-Society Hunter",
    power=5, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Noble", "Vampire"},
    text="Flying\nWhenever this creature attacks, you may sacrifice another creature. If you do, put a +1/+1 counter on this creature.\nWhenever another nontoken creature dies, draw a card.",
)

HUNGRY_GHOUL = make_creature(
    name="Hungry Ghoul",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="{1}, Sacrifice another creature: Put a +1/+1 counter on this creature.",
)

INFERNAL_VESSEL = make_creature(
    name="Infernal Vessel",
    power=2, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Human"},
    text="When this creature dies, if it wasn't a Demon, return it to the battlefield under its owner's control with two +1/+1 counters on it. It's a Demon in addition to its other types.",
)

INFESTATION_SAGE = make_creature(
    name="Infestation Sage",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Elf", "Warlock"},
    text="When this creature dies, create a 1/1 black and green Insect creature token with flying.",
)

MIDNIGHT_SNACK = make_enchantment(
    name="Midnight Snack",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Raid — At the beginning of your end step, if you attacked this turn, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\n{2}{B}, Sacrifice this enchantment: Target opponent loses X life, where X is the amount of life you gained this turn.",
)

NINELIVES_FAMILIAR = make_creature(
    name="Nine-Lives Familiar",
    power=1, toughness=1,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Cat"},
    text="This creature enters with eight revival counters on it if you cast it.\nWhen this creature dies, if it had a revival counter on it, return it to the battlefield with one fewer revival counter on it at the beginning of the next end step.",
)

REVENGE_OF_THE_RATS = make_sorcery(
    name="Revenge of the Rats",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Create a tapped 1/1 black Rat creature token for each creature card in your graveyard.\nFlashback {2}{B}{B} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

SANGUINE_SYPHONER = make_creature(
    name="Sanguine Syphoner",
    power=1, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Warlock"},
    text="Whenever this creature attacks, each opponent loses 1 life and you gain 1 life.",
)

SEEKERS_FOLLY = make_sorcery(
    name="Seeker's Folly",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Choose one —\n• Target opponent discards two cards.\n• Creatures your opponents control get -1/-1 until end of turn.",
)

SOULSHACKLED_ZOMBIE = make_creature(
    name="Soul-Shackled Zombie",
    power=4, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="When this creature enters, exile up to two target cards from a single graveyard. If at least one creature card was exiled this way, each opponent loses 2 life and you gain 2 life.",
)

STAB = make_instant(
    name="Stab",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn.",
)

TINYBONES_BAUBLE_BURGLAR = make_creature(
    name="Tinybones, Bauble Burglar",
    power=1, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Skeleton"},
    supertypes={"Legendary"},
    text="Whenever an opponent discards a card, exile it from their graveyard with a stash counter on it.\nDuring your turn, you may play cards you don't own with stash counters on them from exile, and mana of any type can be spent to cast those spells.\n{3}{B}, {T}: Each opponent discards a card. Activate only as a sorcery.",
)

TRAGIC_BANSHEE = make_creature(
    name="Tragic Banshee",
    power=5, toughness=3,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Morbid — When this creature enters, target creature an opponent controls gets -1/-1 until end of turn. If a creature died this turn, that creature gets -13/-13 until end of turn instead.",
)

VAMPIRE_GOURMAND = make_creature(
    name="Vampire Gourmand",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="Whenever this creature attacks, you may sacrifice another creature. If you do, draw a card and this creature can't be blocked this turn.",
)

VAMPIRE_SOULCALLER = make_creature(
    name="Vampire Soulcaller",
    power=3, toughness=2,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Warlock"},
    text="Flying\nThis creature can't block.\nWhen this creature enters, return target creature card from your graveyard to your hand.",
)

VENGEFUL_BLOODWITCH = make_creature(
    name="Vengeful Bloodwitch",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Warlock"},
    text="Whenever this creature or another creature you control dies, target opponent loses 1 life and you gain 1 life.",
)

ZUL_ASHUR_LICH_LORD = make_creature(
    name="Zul Ashur, Lich Lord",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Warlock", "Zombie"},
    supertypes={"Legendary"},
    text="Ward—Pay 2 life. (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays 2 life.)\n{T}: You may cast target Zombie creature card from your graveyard this turn.",
)

BATTLESONG_BERSERKER = make_creature(
    name="Battlesong Berserker",
    power=3, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Berserker", "Human"},
    text="Whenever you attack, target creature you control gets +1/+0 and gains menace until end of turn. (It can't be blocked except by two or more creatures.)",
)

BOLTWAVE = make_sorcery(
    name="Boltwave",
    mana_cost="{R}",
    colors={Color.RED},
    text="Boltwave deals 3 damage to each opponent.",
)

BULK_UP = make_instant(
    name="Bulk Up",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Double target creature's power until end of turn.\nFlashback {4}{R}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

CHANDRA_FLAMESHAPER = make_planeswalker(
    name="Chandra, Flameshaper",
    mana_cost="{5}{R}{R}",
    colors={Color.RED},
    loyalty=6,
    subtypes={"Chandra"},
    supertypes={"Legendary"},
    text="+2: Add {R}{R}{R}. Exile the top three cards of your library. Choose one. You may play that card this turn.\n+1: Create a token that's a copy of target creature you control, except it has haste and \"At the beginning of the end step, sacrifice this token.\"\n−4: Chandra deals 8 damage divided as you choose among any number of target creatures and/or planeswalkers.",
)

COURAGEOUS_GOBLIN = make_creature(
    name="Courageous Goblin",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
    text="Whenever this creature attacks while you control a creature with power 4 or greater, this creature gets +1/+0 and gains menace until end of turn. (It can't be blocked except by two or more creatures.)",
)

CRACKLING_CYCLOPS = make_creature(
    name="Crackling Cyclops",
    power=0, toughness=4,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Cyclops", "Wizard"},
    text="Whenever you cast a noncreature spell, this creature gets +3/+0 until end of turn.",
)

DRAGON_TRAINER = make_creature(
    name="Dragon Trainer",
    power=1, toughness=1,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human"},
    text="When this creature enters, create a 4/4 red Dragon creature token with flying.",
)

ELECTRODUPLICATE = make_sorcery(
    name="Electroduplicate",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Create a token that's a copy of target creature you control, except it has haste and \"At the beginning of the end step, sacrifice this token.\"\nFlashback {2}{R}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

FIERY_ANNIHILATION = make_instant(
    name="Fiery Annihilation",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Fiery Annihilation deals 5 damage to target creature. Exile up to one target Equipment attached to that creature. If that creature would die this turn, exile it instead.",
)

GOBLIN_BOARDERS = make_creature(
    name="Goblin Boarders",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Pirate"},
    text="Raid — This creature enters with a +1/+1 counter on it if you attacked this turn.",
)

GOBLIN_NEGOTIATION = make_sorcery(
    name="Goblin Negotiation",
    mana_cost="{X}{R}{R}",
    colors={Color.RED},
    text="Goblin Negotiation deals X damage to target creature. Create a number of 1/1 red Goblin creature tokens equal to the amount of excess damage dealt to that creature this way.",
)

GOREHORN_RAIDER = make_creature(
    name="Gorehorn Raider",
    power=4, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Minotaur", "Pirate"},
    text="Raid — When this creature enters, if you attacked this turn, this creature deals 2 damage to any target.",
)

INCINERATING_BLAST = make_sorcery(
    name="Incinerating Blast",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="Incinerating Blast deals 6 damage to target creature.\nYou may discard a card. If you do, draw a card.",
)

KELLAN_PLANAR_TRAILBLAZER = make_creature(
    name="Kellan, Planar Trailblazer",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Faerie", "Human", "Scout"},
    supertypes={"Legendary"},
    text="{1}{R}: If Kellan is a Scout, it becomes a Human Faerie Detective and gains \"Whenever Kellan deals combat damage to a player, exile the top card of your library. You may play that card this turn.\"\n{2}{R}: If Kellan is a Detective, it becomes a 3/2 Human Faerie Rogue and gains double strike.",
)

RITE_OF_THE_DRAGONCALLER = make_enchantment(
    name="Rite of the Dragoncaller",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Whenever you cast an instant or sorcery spell, create a 5/5 red Dragon creature token with flying.",
)

SEARSLICER_GOBLIN = make_creature(
    name="Searslicer Goblin",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="Raid — At the beginning of your end step, if you attacked this turn, create a 1/1 red Goblin creature token.",
)

SLUMBERING_CERBERUS = make_creature(
    name="Slumbering Cerberus",
    power=4, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Dog"},
    text="This creature doesn't untap during your untap step.\nMorbid — At the beginning of each end step, if a creature died this turn, untap this creature.",
)

SOWER_OF_CHAOS = make_creature(
    name="Sower of Chaos",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Devil"},
    text="{2}{R}: Target creature can't block this turn.",
)

STRONGBOX_RAIDER = make_creature(
    name="Strongbox Raider",
    power=5, toughness=2,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Orc", "Pirate"},
    text="Raid — When this creature enters, if you attacked this turn, exile the top two cards of your library. Choose one of them. Until the end of your next turn, you may play that card.",
)

TWINFLAME_TYRANT = make_creature(
    name="Twinflame Tyrant",
    power=3, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\nIf a source you control would deal damage to an opponent or a permanent an opponent controls, it deals double that damage instead.",
)

AMBUSH_WOLF = make_creature(
    name="Ambush Wolf",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Wolf"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nWhen this creature enters, exile up to one target card from a graveyard.",
)

APOTHECARY_STOMPER = make_creature(
    name="Apothecary Stomper",
    power=4, toughness=4,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elephant"},
    text="Vigilance (Attacking doesn't cause this creature to tap.)\nWhen this creature enters, choose one —\n• Put two +1/+1 counters on target creature you control.\n• You gain 4 life.",
)

BEASTKIN_RANGER = make_creature(
    name="Beast-Kin Ranger",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Ranger"},
    text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nWhenever another creature you control enters, this creature gets +1/+0 until end of turn.",
)

CACKLING_PROWLER = make_creature(
    name="Cackling Prowler",
    power=4, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Hyena", "Rogue"},
    text="Ward {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nMorbid — At the beginning of your end step, if a creature died this turn, put a +1/+1 counter on this creature.",
)

EAGER_TRUFFLESNOUT = make_creature(
    name="Eager Trufflesnout",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Boar"},
    text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nWhenever this creature deals combat damage to a player, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")",
)

ELFSWORN_GIANT = make_creature(
    name="Elfsworn Giant",
    power=5, toughness=3,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Giant"},
    text="Reach (This creature can block creatures with flying.)\nLandfall — Whenever a land you control enters, create a 1/1 green Elf Warrior creature token.",
)

ELVISH_REGROWER = make_creature(
    name="Elvish Regrower",
    power=4, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Elf"},
    text="When this creature enters, return target permanent card from your graveyard to your hand.",
)

FELLING_BLOW = make_sorcery(
    name="Felling Blow",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Put a +1/+1 counter on target creature you control. Then that creature deals damage equal to its power to target creature an opponent controls.",
)

LOOT_EXUBERANT_EXPLORER = make_creature(
    name="Loot, Exuberant Explorer",
    power=1, toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Noble"},
    supertypes={"Legendary"},
    text="You may play an additional land on each of your turns.\n{4}{G}{G}, {T}: Look at the top six cards of your library. You may reveal a creature card with mana value less than or equal to the number of lands you control from among them and put it onto the battlefield. Put the rest on the bottom in a random order.",
)

MOSSBORN_HYDRA = make_creature(
    name="Mossborn Hydra",
    power=0, toughness=0,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental", "Hydra"},
    text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nThis creature enters with a +1/+1 counter on it.\nLandfall — Whenever a land you control enters, double the number of +1/+1 counters on this creature.",
)

NEEDLETOOTH_PACK = make_creature(
    name="Needletooth Pack",
    power=4, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Morbid — At the beginning of your end step, if a creature died this turn, put two +1/+1 counters on target creature you control.",
)

PREPOSTEROUS_PROPORTIONS = make_sorcery(
    name="Preposterous Proportions",
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    text="Creatures you control get +10/+10 and gain vigilance until end of turn.",
)

QUAKESTRIDER_CERATOPS = make_creature(
    name="Quakestrider Ceratops",
    power=12, toughness=8,
    mana_cost="{3}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="",
)

QUILLED_GREATWURM = make_creature(
    name="Quilled Greatwurm",
    power=7, toughness=7,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Wurm"},
    text="Trample\nWhenever a creature you control deals combat damage during your turn, put that many +1/+1 counters on it. (It must survive to get the counters.)\nYou may cast this card from your graveyard by removing six counters from among creatures you control in addition to paying its other costs.",
)

SPINNER_OF_SOULS = make_creature(
    name="Spinner of Souls",
    power=4, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Spider", "Spirit"},
    text="Reach\nWhenever another nontoken creature you control dies, you may reveal cards from the top of your library until you reveal a creature card. Put that card into your hand and the rest on the bottom of your library in a random order.",
)

SYLVAN_SCAVENGING = make_enchantment(
    name="Sylvan Scavenging",
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    text="At the beginning of your end step, choose one —\n• Put a +1/+1 counter on target creature you control.\n• Create a 3/3 green Raccoon creature token if you control a creature with power 4 or greater.",
)

TREETOP_SNARESPINNER = make_creature(
    name="Treetop Snarespinner",
    power=1, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Spider"},
    text="Reach (This creature can block creatures with flying.)\nDeathtouch (Any amount of damage this deals to a creature is enough to destroy it.)\n{2}{G}: Put a +1/+1 counter on target creature you control. Activate only as a sorcery.",
)

ALESHA_WHO_LAUGHS_AT_FATE = make_creature(
    name="Alesha, Who Laughs at Fate",
    power=2, toughness=2,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="First strike\nWhenever Alesha attacks, put a +1/+1 counter on it.\nRaid — At the beginning of your end step, if you attacked this turn, return target creature card with mana value less than or equal to Alesha's power from your graveyard to the battlefield.",
)

ANTHEM_OF_CHAMPIONS = make_enchantment(
    name="Anthem of Champions",
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Creatures you control get +1/+1.",
)

ASHROOT_ANIMIST = make_creature(
    name="Ashroot Animist",
    power=4, toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Druid", "Lizard"},
    text="Trample\nWhenever this creature attacks, another target creature you control gains trample and gets +X/+X until end of turn, where X is this creature's power.",
)

DREADWING_SCAVENGER = make_creature(
    name="Dreadwing Scavenger",
    power=2, toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Bird", "Nightmare"},
    text="Flying\nWhenever this creature enters or attacks, draw a card, then discard a card.\nThreshold — This creature gets +1/+1 and has deathtouch as long as there are seven or more cards in your graveyard.",
)

ELENDA_SAINT_OF_DUSK = make_creature(
    name="Elenda, Saint of Dusk",
    power=4, toughness=4,
    mana_cost="{2}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Knight", "Vampire"},
    supertypes={"Legendary"},
    text="Lifelink, hexproof from instants\nAs long as your life total is greater than your starting life total, Elenda gets +1/+1 and has menace. Elenda gets an additional +5/+5 as long as your life total is at least 10 greater than your starting life total.",
)

FIENDISH_PANDA = make_creature(
    name="Fiendish Panda",
    power=3, toughness=2,
    mana_cost="{2}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Bear", "Demon"},
    text="Whenever you gain life, put a +1/+1 counter on this creature.\nWhen this creature dies, return another target non-Bear creature card with mana value less than or equal to this creature's power from your graveyard to the battlefield.",
)

KOMA_WORLDEATER = make_creature(
    name="Koma, World-Eater",
    power=8, toughness=12,
    mana_cost="{3}{G}{G}{U}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Serpent"},
    supertypes={"Legendary"},
    text="This spell can't be countered.\nTrample, ward {4}\nWhenever Koma deals combat damage to a player, create four 3/3 blue Serpent creature tokens named Koma's Coil.",
)

KYKAR_ZEPHYR_AWAKENER = make_creature(
    name="Kykar, Zephyr Awakener",
    power=3, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Bird", "Wizard"},
    supertypes={"Legendary"},
    text="Flying\nWhenever you cast a noncreature spell, choose one —\n• Exile another target creature you control. Return that card to the battlefield under its owner's control at the beginning of the next end step.\n• Create a 1/1 white Spirit creature token with flying.",
)

NIVMIZZET_VISIONARY = make_creature(
    name="Niv-Mizzet, Visionary",
    power=5, toughness=5,
    mana_cost="{4}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Dragon", "Wizard"},
    supertypes={"Legendary"},
    text="Flying\nYou have no maximum hand size.\nWhenever a source you control deals noncombat damage to an opponent, you draw that many cards.",
)

PERFORATING_ARTIST = make_creature(
    name="Perforating Artist",
    power=3, toughness=2,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Devil"},
    text="Deathtouch (Any amount of damage this deals to a creature is enough to destroy it.)\nRaid — At the beginning of your end step, if you attacked this turn, each opponent loses 3 life unless that player sacrifices a nonland permanent of their choice or discards a card.",
)

WARDENS_OF_THE_CYCLE = make_creature(
    name="Wardens of the Cycle",
    power=3, toughness=4,
    mana_cost="{1}{B}{G}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Elf", "Warlock"},
    text="Morbid — At the beginning of your end step, if a creature died this turn, choose one —\n• You gain 2 life.\n• You draw a card and you lose 1 life.",
)

ZIMONE_PARADOX_SCULPTOR = make_creature(
    name="Zimone, Paradox Sculptor",
    power=1, toughness=4,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="At the beginning of combat on your turn, put a +1/+1 counter on each of up to two target creatures you control.\n{G}{U}, {T}: Double the number of each kind of counter on up to two target creatures and/or artifacts you control.",
)

BANNER_OF_KINSHIP = make_artifact(
    name="Banner of Kinship",
    mana_cost="{5}",
    text="As this artifact enters, choose a creature type. This artifact enters with a fellowship counter on it for each creature you control of the chosen type.\nCreatures you control of the chosen type get +1/+1 for each fellowship counter on this artifact.",
)

FISHING_POLE = make_artifact(
    name="Fishing Pole",
    mana_cost="{1}",
    text="Equipped creature has \"{1}, {T}, Tap Fishing Pole: Put a bait counter on Fishing Pole.\"\nWhenever equipped creature becomes untapped, remove a bait counter from this Equipment. If you do, create a 1/1 blue Fish creature token.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

LEYLINE_AXE = make_artifact(
    name="Leyline Axe",
    mana_cost="{4}",
    text="If this card is in your opening hand, you may begin the game with it on the battlefield.\nEquipped creature gets +1/+1 and has double strike and trample.\nEquip {3} ({3}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

QUICKDRAW_KATANA = make_artifact(
    name="Quick-Draw Katana",
    mana_cost="{2}",
    text="During your turn, equipped creature gets +2/+0 and has first strike. (It deals combat damage before creatures without first strike.)\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

RAVENOUS_AMULET = make_artifact(
    name="Ravenous Amulet",
    mana_cost="{2}",
    text="{1}, {T}, Sacrifice a creature: Draw a card and put a soul counter on this artifact. Activate only as a sorcery.\n{4}, {T}, Sacrifice this artifact: Each opponent loses life equal to the number of soul counters on this artifact.",
)

SCRAWLING_CRAWLER = make_artifact_creature(
    name="Scrawling Crawler",
    power=3, toughness=2,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Construct", "Phyrexian"},
    text="At the beginning of your upkeep, each player draws a card.\nWhenever an opponent draws a card, that player loses 1 life.",
)

SOULSTONE_SANCTUARY = make_land(
    name="Soulstone Sanctuary",
    text="{T}: Add {C}.\n{4}: This land becomes a 3/3 creature with vigilance and all creature types. It's still a land.",
)

AJANI_CALLER_OF_THE_PRIDE = make_planeswalker(
    name="Ajani, Caller of the Pride",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    loyalty=4,
    subtypes={"Ajani"},
    supertypes={"Legendary"},
    text="+1: Put a +1/+1 counter on up to one target creature.\n−3: Target creature gains flying and double strike until end of turn.\n−8: Create X 2/2 white Cat creature tokens, where X is your life total.",
)

AJANIS_PRIDEMATE = make_creature(
    name="Ajani's Pridemate",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Soldier"},
    text="Whenever you gain life, put a +1/+1 counter on this creature.",
)

ANGEL_OF_FINALITY = make_creature(
    name="Angel of Finality",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nWhen this creature enters, exile target player's graveyard.",
)

AUTHORITY_OF_THE_CONSULS = make_enchantment(
    name="Authority of the Consuls",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Creatures your opponents control enter tapped.\nWhenever a creature an opponent controls enters, you gain 1 life.",
)

BANISHING_LIGHT = make_enchantment(
    name="Banishing Light",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, exile target nonland permanent an opponent controls until this enchantment leaves the battlefield.",
)

CATHAR_COMMANDO = make_creature(
    name="Cathar Commando",
    power=3, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Flash\n{1}, Sacrifice this creature: Destroy target artifact or enchantment.",
)

DAY_OF_JUDGMENT = make_sorcery(
    name="Day of Judgment",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Destroy all creatures.",
)

GIADA_FONT_OF_HOPE = make_creature(
    name="Giada, Font of Hope",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    supertypes={"Legendary"},
    text="Flying, vigilance\nEach other Angel you control enters with an additional +1/+1 counter on it for each Angel you already control.\n{T}: Add {W}. Spend this mana only to cast an Angel spell.",
)

HEALERS_HAWK = make_creature(
    name="Healer's Hawk",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Bird"},
    text="Flying\nLifelink (Damage dealt by this creature also causes you to gain that much life.)",
)

MAKE_YOUR_MOVE = make_instant(
    name="Make Your Move",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Destroy target artifact, enchantment, or creature with power 4 or greater.",
)

MISCHIEVOUS_PUP = make_creature(
    name="Mischievous Pup",
    power=3, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Dog"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nWhen this creature enters, return up to one other target permanent you control to its owner's hand.",
)

RESOLUTE_REINFORCEMENTS = make_creature(
    name="Resolute Reinforcements",
    power=1, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nWhen this creature enters, create a 1/1 white Soldier creature token.",
)

SAVANNAH_LIONS = make_creature(
    name="Savannah Lions",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Cat"},
    text="",
)

SERRA_ANGEL = make_creature(
    name="Serra Angel",
    power=4, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nVigilance (Attacking doesn't cause this creature to tap.)",
)

STROKE_OF_MIDNIGHT = make_instant(
    name="Stroke of Midnight",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Destroy target nonland permanent. Its controller creates a 1/1 white Human creature token.",
)

YOUTHFUL_VALKYRIE = make_creature(
    name="Youthful Valkyrie",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nWhenever another Angel you control enters, put a +1/+1 counter on this creature.",
)

AEGIS_TURTLE = make_creature(
    name="Aegis Turtle",
    power=0, toughness=5,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Turtle"},
    text="",
)

AETHERIZE = make_instant(
    name="Aetherize",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Return all attacking creatures to their owner's hand.",
)

BRINEBORN_CUTTHROAT = make_creature(
    name="Brineborn Cutthroat",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Pirate"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nWhenever you cast a spell during an opponent's turn, put a +1/+1 counter on this creature.",
)

ESSENCE_SCATTER = make_instant(
    name="Essence Scatter",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target creature spell.",
)

EXTRAVAGANT_REPLICATION = make_enchantment(
    name="Extravagant Replication",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="At the beginning of your upkeep, create a token that's a copy of another target nonland permanent you control.",
)

FLEETING_DISTRACTION = make_instant(
    name="Fleeting Distraction",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature gets -1/-0 until end of turn.\nDraw a card.",
)

IMPRISONED_IN_THE_MOON = make_enchantment(
    name="Imprisoned in the Moon",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Enchant creature, land, or planeswalker\nEnchanted permanent is a colorless land with \"{T}: Add {C}\" and loses all other card types and abilities.",
    subtypes={"Aura"},
)

LIGHTSHELL_DUO = make_creature(
    name="Lightshell Duo",
    power=3, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Otter", "Rat"},
    text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nWhen this creature enters, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
)

MICROMANCER = make_creature(
    name="Micromancer",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When this creature enters, you may search your library for an instant or sorcery card with mana value 1, reveal it, put it into your hand, then shuffle.",
)

MOCKING_SPRITE = make_creature(
    name="Mocking Sprite",
    power=2, toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Rogue"},
    text="Flying\nInstant and sorcery spells you cast cost {1} less to cast.",
)

AN_OFFER_YOU_CANT_REFUSE = make_instant(
    name="An Offer You Can't Refuse",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Counter target noncreature spell. Its controller creates two Treasure tokens. (They're artifacts with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

OMNISCIENCE = make_enchantment(
    name="Omniscience",
    mana_cost="{7}{U}{U}{U}",
    colors={Color.BLUE},
    text="You may cast spells from your hand without paying their mana costs.",
)

RUN_AWAY_TOGETHER = make_instant(
    name="Run Away Together",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Choose two target creatures controlled by different players. Return those creatures to their owners' hands.",
)

SELFREFLECTION = make_sorcery(
    name="Self-Reflection",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Create a token that's a copy of target creature you control.\nFlashback {3}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

SPECTRAL_SAILOR = make_creature(
    name="Spectral Sailor",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Pirate", "Spirit"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nFlying\n{3}{U}: Draw a card.",
)

THINK_TWICE = make_instant(
    name="Think Twice",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Draw a card.\nFlashback {2}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

TIME_STOP = make_instant(
    name="Time Stop",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="End the turn. (Exile all spells and abilities, including this spell. The player whose turn it is discards down to their maximum hand size. Damage heals and \"this turn\" and \"until end of turn\" effects end.)",
)

TOLARIAN_TERROR = make_creature(
    name="Tolarian Terror",
    power=5, toughness=5,
    mana_cost="{6}{U}",
    colors={Color.BLUE},
    subtypes={"Serpent"},
    text="This spell costs {1} less to cast for each instant and sorcery card in your graveyard.\nWard {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)",
)

WITNESS_PROTECTION = make_enchantment(
    name="Witness Protection",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Enchant creature\nEnchanted creature loses all abilities and is a green and white Citizen creature with base power and toughness 1/1 named Legitimate Businessperson. (It loses all other colors, card types, creature types, and names.)",
    subtypes={"Aura"},
)

BAKE_INTO_A_PIE = make_instant(
    name="Bake into a Pie",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. Create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")",
)

BURGLAR_RAT = make_creature(
    name="Burglar Rat",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rat"},
    text="When this creature enters, each opponent discards a card.",
)

DIREGRAF_GHOUL = make_creature(
    name="Diregraf Ghoul",
    power=2, toughness=2,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="This creature enters tapped.",
)

EATEN_ALIVE = make_sorcery(
    name="Eaten Alive",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, sacrifice a creature or pay {3}{B}.\nExile target creature or planeswalker.",
)

EXSANGUINATE = make_sorcery(
    name="Exsanguinate",
    mana_cost="{X}{B}{B}",
    colors={Color.BLACK},
    text="Each opponent loses X life. You gain life equal to the life lost this way.",
)

FAKE_YOUR_OWN_DEATH = make_instant(
    name="Fake Your Own Death",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Until end of turn, target creature gets +2/+0 and gains \"When this creature dies, return it to the battlefield tapped under its owner's control and you create a Treasure token.\" (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

HEROS_DOWNFALL = make_instant(
    name="Hero's Downfall",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature or planeswalker.",
)

LILIANA_DREADHORDE_GENERAL = make_planeswalker(
    name="Liliana, Dreadhorde General",
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    loyalty=6,
    subtypes={"Liliana"},
    supertypes={"Legendary"},
    text="Whenever a creature you control dies, draw a card.\n+1: Create a 2/2 black Zombie creature token.\n−4: Each player sacrifices two creatures of their choice.\n−9: Each opponent chooses a permanent they control of each permanent type and sacrifices the rest.",
)

MACABRE_WALTZ = make_sorcery(
    name="Macabre Waltz",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Return up to two target creature cards from your graveyard to your hand, then discard a card.",
)

MARAUDING_BLIGHTPRIEST = make_creature(
    name="Marauding Blight-Priest",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Vampire"},
    text="Whenever you gain life, each opponent loses 1 life.",
)

PAINFUL_QUANDARY = make_enchantment(
    name="Painful Quandary",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Whenever an opponent casts a spell, that player loses 5 life unless they discard a card.",
)

PHYREXIAN_ARENA = make_enchantment(
    name="Phyrexian Arena",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, you draw a card and you lose 1 life.",
)

PILFER = make_sorcery(
    name="Pilfer",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target opponent reveals their hand. You choose a nonland card from it. That player discards that card.",
)

REASSEMBLING_SKELETON = make_creature(
    name="Reassembling Skeleton",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Skeleton", "Warrior"},
    text="{1}{B}: Return this card from your graveyard to the battlefield tapped.",
)

RISE_OF_THE_DARK_REALMS = make_sorcery(
    name="Rise of the Dark Realms",
    mana_cost="{7}{B}{B}",
    colors={Color.BLACK},
    text="Put all creature cards from all graveyards onto the battlefield under your control.",
)

RUNESCARRED_DEMON = make_creature(
    name="Rune-Scarred Demon",
    power=6, toughness=6,
    mana_cost="{5}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Flying\nWhen this creature enters, search your library for a card, put it into your hand, then shuffle.",
)

STROMKIRK_BLOODTHIEF = make_creature(
    name="Stromkirk Bloodthief",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Vampire"},
    text="At the beginning of your end step, if an opponent lost life this turn, put a +1/+1 counter on target Vampire you control.",
)

VAMPIRE_NIGHTHAWK = make_creature(
    name="Vampire Nighthawk",
    power=2, toughness=3,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Shaman", "Vampire"},
    text="Flying\nDeathtouch (Any amount of damage this deals to a creature is enough to destroy it.)\nLifelink (Damage dealt by this creature also causes you to gain that much life.)",
)

ZOMBIFY = make_sorcery(
    name="Zombify",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield.",
)

ABRADE = make_instant(
    name="Abrade",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Choose one —\n• Abrade deals 3 damage to target creature.\n• Destroy target artifact.",
)

AXGARD_CAVALRY = make_creature(
    name="Axgard Cavalry",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Berserker", "Dwarf"},
    text="{T}: Target creature gains haste until end of turn. (It can attack and {T} this turn.)",
)

BRASSS_BOUNTY = make_sorcery(
    name="Brass's Bounty",
    mana_cost="{6}{R}",
    colors={Color.RED},
    text="For each land you control, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

BRAZEN_SCOURGE = make_creature(
    name="Brazen Scourge",
    power=3, toughness=3,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Gremlin"},
    text="Haste (This creature can attack and {T} as soon as it comes under your control.)",
)

BURST_LIGHTNING = make_instant(
    name="Burst Lightning",
    mana_cost="{R}",
    colors={Color.RED},
    text="Kicker {4} (You may pay an additional {4} as you cast this spell.)\nBurst Lightning deals 2 damage to any target. If this spell was kicked, it deals 4 damage instead.",
)

DRAKUSETH_MAW_OF_FLAMES = make_creature(
    name="Drakuseth, Maw of Flames",
    power=7, toughness=7,
    mana_cost="{4}{R}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    supertypes={"Legendary"},
    text="Flying\nWhenever Drakuseth attacks, it deals 4 damage to any target and 3 damage to each of up to two other targets.",
)

ETALI_PRIMAL_STORM = make_creature(
    name="Etali, Primal Storm",
    power=6, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur", "Elder"},
    supertypes={"Legendary"},
    text="Whenever Etali attacks, exile the top card of each player's library, then you may cast any number of spells from among those cards without paying their mana costs.",
)

FANATICAL_FIREBRAND = make_creature(
    name="Fanatical Firebrand",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Pirate"},
    text="Haste (This creature can attack and {T} as soon as it comes under your control.)\n{T}, Sacrifice this creature: It deals 1 damage to any target.",
)

FIREBRAND_ARCHER = make_creature(
    name="Firebrand Archer",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Archer", "Human"},
    text="Whenever you cast a noncreature spell, this creature deals 1 damage to each opponent.",
)

FIRESPITTER_WHELP = make_creature(
    name="Firespitter Whelp",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\nWhenever you cast a noncreature or Dragon spell, this creature deals 1 damage to each opponent.",
)

FLAMEWAKE_PHOENIX = make_creature(
    name="Flamewake Phoenix",
    power=2, toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Phoenix"},
    text="Flying, haste\nThis creature attacks each combat if able.\nFerocious — At the beginning of combat on your turn, if you control a creature with power 4 or greater, you may pay {R}. If you do, return this card from your graveyard to the battlefield.",
)

FRENZIED_GOBLIN = make_creature(
    name="Frenzied Goblin",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Berserker", "Goblin"},
    text="Whenever this creature attacks, you may pay {R}. If you do, target creature can't block this turn.",
)

GOBLIN_SURPRISE = make_instant(
    name="Goblin Surprise",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Choose one —\n• Creatures you control get +2/+0 until end of turn.\n• Create two 1/1 red Goblin creature tokens.",
)

HEARTFIRE_IMMOLATOR = make_creature(
    name="Heartfire Immolator",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard"},
    text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\n{R}, Sacrifice this creature: It deals damage equal to its power to target creature or planeswalker.",
)

HIDETSUGUS_SECOND_RITE = make_instant(
    name="Hidetsugu's Second Rite",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="If target player has exactly 10 life, Hidetsugu's Second Rite deals 10 damage to that player.",
)

INVOLUNTARY_EMPLOYMENT = make_sorcery(
    name="Involuntary Employment",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. Create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

KRENKO_MOB_BOSS = make_creature(
    name="Krenko, Mob Boss",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    supertypes={"Legendary"},
    text="{T}: Create X 1/1 red Goblin creature tokens, where X is the number of Goblins you control.",
)

SEISMIC_RUPTURE = make_sorcery(
    name="Seismic Rupture",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Seismic Rupture deals 2 damage to each creature without flying.",
)

SHIVAN_DRAGON = make_creature(
    name="Shivan Dragon",
    power=5, toughness=5,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\n{R}: This creature gets +1/+0 until end of turn.",
)

SLAGSTORM = make_sorcery(
    name="Slagstorm",
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    text="Choose one —\n• Slagstorm deals 3 damage to each creature.\n• Slagstorm deals 3 damage to each player.",
)

SPITFIRE_LAGAC = make_creature(
    name="Spitfire Lagac",
    power=3, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Lizard"},
    text="Landfall — Whenever a land you control enters, this creature deals 1 damage to each opponent.",
)

SURE_STRIKE = make_instant(
    name="Sure Strike",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains first strike until end of turn. (It deals combat damage before creatures without first strike.)",
)

THRILL_OF_POSSIBILITY = make_instant(
    name="Thrill of Possibility",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="As an additional cost to cast this spell, discard a card.\nDraw two cards.",
)

AFFECTIONATE_INDRIK = make_creature(
    name="Affectionate Indrik",
    power=4, toughness=4,
    mana_cost="{5}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="When this creature enters, you may have it fight target creature you don't control. (Each deals damage equal to its power to the other.)",
)

BITE_DOWN = make_instant(
    name="Bite Down",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control deals damage equal to its power to target creature or planeswalker you don't control.",
)

BLANCHWOOD_ARMOR = make_enchantment(
    name="Blanchwood Armor",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Enchant creature\nEnchanted creature gets +1/+1 for each Forest you control.",
    subtypes={"Aura"},
)

BROKEN_WINGS = make_instant(
    name="Broken Wings",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Destroy target artifact, enchantment, or creature with flying.",
)

BUSHWHACK = make_sorcery(
    name="Bushwhack",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Search your library for a basic land card, reveal it, put it into your hand, then shuffle.\n• Target creature you control fights target creature you don't control. (Each deals damage equal to its power to the other.)",
)

DOUBLING_SEASON = make_enchantment(
    name="Doubling Season",
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    text="If an effect would create one or more tokens under your control, it creates twice that many of those tokens instead.\nIf an effect would put one or more counters on a permanent you control, it puts twice that many of those counters on that permanent instead.",
)

DWYNEN_GILTLEAF_DAEN = make_creature(
    name="Dwynen, Gilt-Leaf Daen",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    supertypes={"Legendary"},
    text="Reach (This creature can block creatures with flying.)\nOther Elf creatures you control get +1/+1.\nWhenever Dwynen attacks, you gain 1 life for each attacking Elf you control.",
)

DWYNENS_ELITE = make_creature(
    name="Dwynen's Elite",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    text="When this creature enters, if you control another Elf, create a 1/1 green Elf Warrior creature token.",
)

ELVISH_ARCHDRUID = make_creature(
    name="Elvish Archdruid",
    power=2, toughness=2,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Elf"},
    text="Other Elf creatures you control get +1/+1.\n{T}: Add {G} for each Elf you control.",
)

GARRUKS_UPRISING = make_enchantment(
    name="Garruk's Uprising",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, if you control a creature with power 4 or greater, draw a card.\nCreatures you control have trample. (Each of those creatures can deal excess combat damage to the player or planeswalker it's attacking.)\nWhenever a creature you control with power 4 or greater enters, draw a card.",
)

GENESIS_WAVE = make_sorcery(
    name="Genesis Wave",
    mana_cost="{X}{G}{G}{G}",
    colors={Color.GREEN},
    text="Reveal the top X cards of your library. You may put any number of permanent cards with mana value X or less from among them onto the battlefield. Then put all cards revealed this way that weren't put onto the battlefield into your graveyard.",
)

GHALTA_PRIMAL_HUNGER = make_creature(
    name="Ghalta, Primal Hunger",
    power=12, toughness=12,
    mana_cost="{10}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur", "Elder"},
    supertypes={"Legendary"},
    text="This spell costs {X} less to cast, where X is the total power of creatures you control.\nTrample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)",
)

GIANT_GROWTH = make_instant(
    name="Giant Growth",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn.",
)

GNARLID_COLONY = make_creature(
    name="Gnarlid Colony",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Kicker {2}{G} (You may pay an additional {2}{G} as you cast this spell.)\nIf this creature was kicked, it enters with two +1/+1 counters on it.\nEach creature you control with a +1/+1 counter on it has trample. (It can deal excess combat damage to the player or planeswalker it's attacking.)",
)

GROW_FROM_THE_ASHES = make_sorcery(
    name="Grow from the Ashes",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Kicker {2} (You may pay an additional {2} as you cast this spell.)\nSearch your library for a basic land card, put it onto the battlefield, then shuffle. If this spell was kicked, instead search your library for two basic land cards, put them onto the battlefield, then shuffle.",
)

INSPIRING_CALL = make_instant(
    name="Inspiring Call",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Draw a card for each creature you control with a +1/+1 counter on it. Those creatures gain indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy them.)",
)

LLANOWAR_ELVES = make_creature(
    name="Llanowar Elves",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Elf"},
    text="{T}: Add {G}.",
)

MILDMANNERED_LIBRARIAN = make_creature(
    name="Mild-Mannered Librarian",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Human"},
    text="{3}{G}: This creature becomes a Werewolf. Put two +1/+1 counters on it and you draw a card. Activate only once.",
)

NESSIAN_HORNBEETLE = make_creature(
    name="Nessian Hornbeetle",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Insect"},
    text="At the beginning of combat on your turn, if you control another creature with power 4 or greater, put a +1/+1 counter on this creature.",
)

OVERRUN = make_sorcery(
    name="Overrun",
    mana_cost="{2}{G}{G}{G}",
    colors={Color.GREEN},
    text="Creatures you control get +3/+3 and gain trample until end of turn. (Each of those creatures can deal excess combat damage to the player or planeswalker it's attacking.)",
)

RECLAMATION_SAGE = make_creature(
    name="Reclamation Sage",
    power=2, toughness=1,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Shaman"},
    text="When this creature enters, you may destroy target artifact or enchantment.",
)

SCAVENGING_OOZE = make_creature(
    name="Scavenging Ooze",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Ooze"},
    text="{G}: Exile target card from a graveyard. If it was a creature card, put a +1/+1 counter on this creature and you gain 1 life.",
)

SNAKESKIN_VEIL = make_instant(
    name="Snakeskin Veil",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Put a +1/+1 counter on target creature you control. It gains hexproof until end of turn. (It can't be the target of spells or abilities your opponents control.)",
)

VIVIEN_REID = make_planeswalker(
    name="Vivien Reid",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    loyalty=5,
    subtypes={"Vivien"},
    supertypes={"Legendary"},
    text="+1: Look at the top four cards of your library. You may reveal a creature or land card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.\n−3: Destroy target artifact, enchantment, or creature with flying.\n−8: You get an emblem with \"Creatures you control get +2/+2 and have vigilance, trample, and indestructible.\"",
)

WARY_THESPIAN = make_creature(
    name="Wary Thespian",
    power=3, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Cat", "Druid"},
    text="When this creature enters or dies, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

WILDWOOD_SCOURGE = make_creature(
    name="Wildwood Scourge",
    power=0, toughness=0,
    mana_cost="{X}{G}",
    colors={Color.GREEN},
    subtypes={"Hydra"},
    text="This creature enters with X +1/+1 counters on it.\nWhenever one or more +1/+1 counters are put on another non-Hydra creature you control, put a +1/+1 counter on this creature.",
)

BALMOR_BATTLEMAGE_CAPTAIN = make_creature(
    name="Balmor, Battlemage Captain",
    power=1, toughness=3,
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Bird", "Wizard"},
    supertypes={"Legendary"},
    text="Flying\nWhenever you cast an instant or sorcery spell, creatures you control get +1/+0 and gain trample until end of turn.",
)

CONSUMING_ABERRATION = make_creature(
    name="Consuming Aberration",
    power=0, toughness=0,
    mana_cost="{3}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Horror"},
    text="Consuming Aberration's power and toughness are each equal to the number of cards in your opponents' graveyards.\nWhenever you cast a spell, each opponent reveals cards from the top of their library until they reveal a land card, then puts those cards into their graveyard.",
)

EMPYREAN_EAGLE = make_creature(
    name="Empyrean Eagle",
    power=2, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Bird", "Spirit"},
    text="Flying\nOther creatures you control with flying get +1/+1.",
)

GOODFORTUNE_UNICORN = make_creature(
    name="Good-Fortune Unicorn",
    power=2, toughness=2,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Unicorn"},
    text="Whenever another creature you control enters, put a +1/+1 counter on that creature.",
)

HEROIC_REINFORCEMENTS = make_sorcery(
    name="Heroic Reinforcements",
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Create two 1/1 white Soldier creature tokens. Until end of turn, creatures you control get +1/+1 and gain haste. (They can attack and {T} this turn.)",
)

LATHRIL_BLADE_OF_THE_ELVES = make_creature(
    name="Lathril, Blade of the Elves",
    power=2, toughness=3,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Elf", "Noble"},
    supertypes={"Legendary"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhenever Lathril deals combat damage to a player, create that many 1/1 green Elf Warrior creature tokens.\n{T}, Tap ten untapped Elves you control: Each opponent loses 10 life and you gain 10 life.",
)

MULDROTHA_THE_GRAVETIDE = make_creature(
    name="Muldrotha, the Gravetide",
    power=6, toughness=6,
    mana_cost="{3}{B}{G}{U}",
    colors={Color.BLACK, Color.GREEN, Color.BLUE},
    subtypes={"Avatar", "Elemental"},
    supertypes={"Legendary"},
    text="During each of your turns, you may play a land and cast a permanent spell of each permanent type from your graveyard. (If a card has multiple permanent types, choose one as you play it.)",
)

PROGENITUS = make_creature(
    name="Progenitus",
    power=10, toughness=10,
    mana_cost="{W}{W}{U}{U}{B}{B}{R}{R}{G}{G}",
    colors={Color.BLACK, Color.GREEN, Color.RED, Color.BLUE, Color.WHITE},
    subtypes={"Avatar", "Hydra"},
    supertypes={"Legendary"},
    text="Protection from everything\nIf Progenitus would be put into a graveyard from anywhere, reveal Progenitus and shuffle it into its owner's library instead.",
)

RUBY_DARING_TRACKER = make_creature(
    name="Ruby, Daring Tracker",
    power=1, toughness=2,
    mana_cost="{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Scout"},
    supertypes={"Legendary"},
    text="Haste (This creature can attack and {T} as soon as it comes under your control.)\nWhenever Ruby attacks while you control a creature with power 4 or greater, Ruby gets +2/+2 until end of turn.\n{T}: Add {R} or {G}.",
)

SWIFTBLADE_VINDICATOR = make_creature(
    name="Swiftblade Vindicator",
    power=1, toughness=1,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Double strike (This creature deals both first-strike and regular combat damage.)\nVigilance (Attacking doesn't cause this creature to tap.)\nTrample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)",
)

TATYOVA_BENTHIC_DRUID = make_creature(
    name="Tatyova, Benthic Druid",
    power=3, toughness=3,
    mana_cost="{3}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Druid", "Merfolk"},
    supertypes={"Legendary"},
    text="Landfall — Whenever a land you control enters, you gain 1 life and draw a card.",
)

THOUSANDYEAR_STORM = make_enchantment(
    name="Thousand-Year Storm",
    mana_cost="{4}{U}{R}",
    colors={Color.RED, Color.BLUE},
    text="Whenever you cast an instant or sorcery spell, copy it for each other instant and sorcery spell you've cast before it this turn. You may choose new targets for the copies.",
)

ADVENTURING_GEAR = make_artifact(
    name="Adventuring Gear",
    mana_cost="{1}",
    text="Landfall — Whenever a land you control enters, equipped creature gets +2/+2 until end of turn.\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

BURNISHED_HART = make_artifact_creature(
    name="Burnished Hart",
    power=2, toughness=2,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Elk"},
    text="{3}, Sacrifice this creature: Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.",
)

CAMPUS_GUIDE = make_artifact_creature(
    name="Campus Guide",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Golem"},
    text="When this creature enters, you may search your library for a basic land card, reveal it, then shuffle and put that card on top.",
)

GLEAMING_BARRIER = make_artifact_creature(
    name="Gleaming Barrier",
    power=0, toughness=4,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Wall"},
    text="Defender\nWhen this creature dies, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

GOLDVEIN_PICK = make_artifact(
    name="Goldvein Pick",
    mana_cost="{2}",
    text="Equipped creature gets +1/+1.\nWhenever equipped creature deals combat damage to a player, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

HERALDIC_BANNER = make_artifact(
    name="Heraldic Banner",
    mana_cost="{3}",
    text="As this artifact enters, choose a color.\nCreatures you control of the chosen color get +1/+0.\n{T}: Add one mana of the chosen color.",
)

JUGGERNAUT = make_artifact_creature(
    name="Juggernaut",
    power=5, toughness=3,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Juggernaut"},
    text="This creature attacks each combat if able.\nThis creature can't be blocked by Walls.",
)

METEOR_GOLEM = make_artifact_creature(
    name="Meteor Golem",
    power=3, toughness=3,
    mana_cost="{7}",
    colors=set(),
    subtypes={"Golem"},
    text="When this creature enters, destroy target nonland permanent an opponent controls.",
)

SOLEMN_SIMULACRUM = make_artifact_creature(
    name="Solemn Simulacrum",
    power=2, toughness=2,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Golem"},
    text="When this creature enters, you may search your library for a basic land card, put that card onto the battlefield tapped, then shuffle.\nWhen this creature dies, you may draw a card.",
)

SWIFTFOOT_BOOTS = make_artifact(
    name="Swiftfoot Boots",
    mana_cost="{2}",
    text="Equipped creature has hexproof and haste. (It can't be the target of spells or abilities your opponents control. It can attack and {T} no matter when it came under your control.)\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

BLOODFELL_CAVES = make_land(
    name="Bloodfell Caves",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {B} or {R}.",
)

BLOSSOMING_SANDS = make_land(
    name="Blossoming Sands",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {G} or {W}.",
)

DISMAL_BACKWATER = make_land(
    name="Dismal Backwater",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {U} or {B}.",
)

EVOLVING_WILDS = make_land(
    name="Evolving Wilds",
    text="{T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
)

JUNGLE_HOLLOW = make_land(
    name="Jungle Hollow",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {B} or {G}.",
)

ROGUES_PASSAGE = make_land(
    name="Rogue's Passage",
    text="{T}: Add {C}.\n{4}, {T}: Target creature can't be blocked this turn.",
)

RUGGED_HIGHLANDS = make_land(
    name="Rugged Highlands",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {R} or {G}.",
)

SCOURED_BARRENS = make_land(
    name="Scoured Barrens",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {W} or {B}.",
)

SECLUDED_COURTYARD = make_land(
    name="Secluded Courtyard",
    text="As this land enters, choose a creature type.\n{T}: Add {C}.\n{T}: Add one mana of any color. Spend this mana only to cast a creature spell of the chosen type or activate an ability of a creature source of the chosen type.",
)

SWIFTWATER_CLIFFS = make_land(
    name="Swiftwater Cliffs",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {U} or {R}.",
)

THORNWOOD_FALLS = make_land(
    name="Thornwood Falls",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {G} or {U}.",
)

TRANQUIL_COVE = make_land(
    name="Tranquil Cove",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {W} or {U}.",
)

WINDSCARRED_CRAG = make_land(
    name="Wind-Scarred Crag",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {R} or {W}.",
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

ADAMANT_WILL = make_instant(
    name="Adamant Will",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 and gains indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)",
)

ANCESTOR_DRAGON = make_creature(
    name="Ancestor Dragon",
    power=5, toughness=6,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Dragon"},
    text="Flying\nWhenever one or more creatures you control attack, you gain 1 life for each attacking creature.",
)

ANGELIC_EDICT = make_sorcery(
    name="Angelic Edict",
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    text="Exile target creature or enchantment.",
)

BISHOPS_SOLDIER = make_creature(
    name="Bishop's Soldier",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Soldier", "Vampire"},
    text="Lifelink (Damage dealt by this creature also causes you to gain that much life.)",
)

DEADLY_RIPOSTE = make_instant(
    name="Deadly Riposte",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Deadly Riposte deals 3 damage to target tapped creature and you gain 2 life.",
)

ELSPETHS_SMITE = make_instant(
    name="Elspeth's Smite",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Elspeth's Smite deals 3 damage to target attacking or blocking creature. If that creature would die this turn, exile it instead.",
)

HERALD_OF_FAITH = make_creature(
    name="Herald of Faith",
    power=4, toughness=3,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nWhenever this creature attacks, you gain 2 life.",
)

INGENIOUS_LEONIN = make_creature(
    name="Ingenious Leonin",
    power=4, toughness=4,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Soldier"},
    text="{3}{W}: Put a +1/+1 counter on another target attacking creature you control. If that creature is a Cat, it gains first strike until end of turn. (It deals combat damage before creatures without first strike.)",
)

INSPIRING_OVERSEER = make_creature(
    name="Inspiring Overseer",
    power=2, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Angel", "Cleric"},
    text="Flying\nWhen this creature enters, you gain 1 life and draw a card.",
)

JAZAL_GOLDMANE = make_creature(
    name="Jazal Goldmane",
    power=4, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Warrior"},
    supertypes={"Legendary"},
    text="First strike (This creature deals combat damage before creatures without first strike.)\n{3}{W}{W}: Attacking creatures you control get +X/+X until end of turn, where X is the number of attacking creatures.",
)

LEONIN_SKYHUNTER = make_creature(
    name="Leonin Skyhunter",
    power=2, toughness=2,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Knight"},
    text="Flying",
)

LEONIN_VANGUARD = make_creature(
    name="Leonin Vanguard",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Soldier"},
    text="At the beginning of combat on your turn, if you control three or more creatures, this creature gets +1/+1 until end of turn and you gain 1 life.",
)

MOMENT_OF_TRIUMPH = make_instant(
    name="Moment of Triumph",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 until end of turn. You gain 2 life.",
)

PACIFISM = make_enchantment(
    name="Pacifism",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Enchant creature\nEnchanted creature can't attack or block.",
    subtypes={"Aura"},
)

PRAYER_OF_BINDING = make_enchantment(
    name="Prayer of Binding",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Flash\nWhen this enchantment enters, exile up to one target nonland permanent an opponent controls until this enchantment leaves the battlefield. You gain 2 life.",
)

TWINBLADE_PALADIN = make_creature(
    name="Twinblade Paladin",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Whenever you gain life, put a +1/+1 counter on this creature.\nAs long as you have 25 or more life, this creature has double strike. (It deals both first-strike and regular combat damage.)",
)

BURROG_BEFUDDLER = make_creature(
    name="Burrog Befuddler",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Frog", "Wizard"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nWhen this creature enters, target creature an opponent controls gets -1/-0 until end of turn.",
)

CANCEL = make_instant(
    name="Cancel",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell.",
)

CORSAIR_CAPTAIN = make_creature(
    name="Corsair Captain",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="When this creature enters, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nOther Pirates you control get +1/+1.",
)

EATEN_BY_PIRANHAS = make_enchantment(
    name="Eaten by Piranhas",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Flash (You may cast this spell any time you could cast an instant.)\nEnchant creature\nEnchanted creature loses all abilities and is a black Skeleton creature with base power and toughness 1/1. (It loses all other colors, card types, and creature types.)",
    subtypes={"Aura"},
)

EXCLUSION_MAGE = make_creature(
    name="Exclusion Mage",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When this creature enters, return target creature an opponent controls to its owner's hand.",
)

INTO_THE_ROIL = make_instant(
    name="Into the Roil",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Kicker {1}{U} (You may pay an additional {1}{U} as you cast this spell.)\nReturn target nonland permanent to its owner's hand. If this spell was kicked, draw a card.",
)

KITESAIL_CORSAIR = make_creature(
    name="Kitesail Corsair",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="This creature has flying as long as it's attacking.",
)

MYSTIC_ARCHAEOLOGIST = make_creature(
    name="Mystic Archaeologist",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="{3}{U}{U}: Draw two cards.",
)

OPT = make_instant(
    name="Opt",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Scry 1. (Look at the top card of your library. You may put that card on the bottom.)\nDraw a card.",
)

QUICK_STUDY = make_instant(
    name="Quick Study",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw two cards.",
)

STARLIGHT_SNARE = make_enchantment(
    name="Starlight Snare",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Enchant creature\nWhen this Aura enters, tap enchanted creature.\nEnchanted creature doesn't untap during its controller's untap step.",
    subtypes={"Aura"},
)

STORM_FLEET_SPY = make_creature(
    name="Storm Fleet Spy",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="Raid — When this creature enters, if you attacked this turn, draw a card.",
)

BLOODTITHE_COLLECTOR = make_creature(
    name="Bloodtithe Collector",
    power=3, toughness=4,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Noble", "Vampire"},
    text="Flying\nWhen this creature enters, if an opponent lost life this turn, each opponent discards a card.",
)

CEMETERY_RECRUITMENT = make_sorcery(
    name="Cemetery Recruitment",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to your hand. If it's a Zombie card, draw a card.",
)

CROSSWAY_TROUBLEMAKERS = make_creature(
    name="Crossway Troublemakers",
    power=5, toughness=5,
    mana_cost="{5}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="Attacking Vampires you control have deathtouch and lifelink. (Any amount of damage they deal to a creature is enough to destroy it. Damage dealt by those creatures also causes their controller to gain that much life.)\nWhenever a Vampire you control dies, you may pay 2 life. If you do, draw a card.",
)

CROW_OF_DARK_TIDINGS = make_creature(
    name="Crow of Dark Tidings",
    power=2, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Bird", "Zombie"},
    text="Flying\nWhen this creature enters or dies, mill two cards. (Put the top two cards of your library into your graveyard.)",
)

DEADLY_PLOT = make_instant(
    name="Deadly Plot",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Choose one —\n• Destroy target creature or planeswalker.\n• Return target Zombie creature card from your graveyard to the battlefield tapped.",
)

DEATH_BARON = make_creature(
    name="Death Baron",
    power=2, toughness=2,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Wizard", "Zombie"},
    text="Skeletons you control and other Zombies you control get +1/+1 and have deathtouch. (Any amount of damage they deal to a creature is enough to destroy it.)",
)

HIGHBORN_VAMPIRE = make_creature(
    name="Highborn Vampire",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Warrior"},
    text="",
)

MAALFELD_TWINS = make_creature(
    name="Maalfeld Twins",
    power=4, toughness=4,
    mana_cost="{5}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="When this creature dies, create two 2/2 black Zombie creature tokens.",
)

MOMENT_OF_CRAVING = make_instant(
    name="Moment of Craving",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn. You gain 2 life.",
)

OFFER_IMMORTALITY = make_instant(
    name="Offer Immortality",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gains deathtouch and indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)",
)

SKELETON_ARCHER = make_creature(
    name="Skeleton Archer",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Archer", "Skeleton"},
    text="When this creature enters, it deals 1 damage to any target.",
)

SUSPICIOUS_SHAMBLER = make_creature(
    name="Suspicious Shambler",
    power=4, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="{4}{B}{B}, Exile this card from your graveyard: Create two 2/2 black Zombie creature tokens. Activate only as a sorcery.",
)

UNDYING_MALICE = make_instant(
    name="Undying Malice",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Until end of turn, target creature gains \"When this creature dies, return it to the battlefield tapped under its owner's control with a +1/+1 counter on it.\"",
)

UNTAMED_HUNGER = make_enchantment(
    name="Untamed Hunger",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Enchant creature\nEnchanted creature gets +2/+1 and has menace. (It can't be blocked except by two or more creatures.)",
    subtypes={"Aura"},
)

VAMPIRE_INTERLOPER = make_creature(
    name="Vampire Interloper",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Scout", "Vampire"},
    text="Flying\nThis creature can't block.",
)

VAMPIRE_NEONATE = make_creature(
    name="Vampire Neonate",
    power=0, toughness=3,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="{2}, {T}: Each opponent loses 1 life and you gain 1 life.",
)

VAMPIRE_SPAWN = make_creature(
    name="Vampire Spawn",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="When this creature enters, each opponent loses 2 life and you gain 2 life.",
)

BATTLERATTLE_SHAMAN = make_creature(
    name="Battle-Rattle Shaman",
    power=2, toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Shaman"},
    text="At the beginning of combat on your turn, you may have target creature get +2/+0 until end of turn.",
)

CARNELIAN_ORB_OF_DRAGONKIND = make_artifact(
    name="Carnelian Orb of Dragonkind",
    mana_cost="{2}{R}",
    text="{T}: Add {R}. If that mana is spent on a Dragon creature spell, it gains haste until end of turn.",
)

DRAGON_FODDER = make_sorcery(
    name="Dragon Fodder",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Create two 1/1 red Goblin creature tokens.",
)

DRAGONLORDS_SERVANT = make_creature(
    name="Dragonlord's Servant",
    power=1, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Shaman"},
    text="Dragon spells you cast cost {1} less to cast.",
)

DROPKICK_BOMBER = make_creature(
    name="Dropkick Bomber",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="Other Goblins you control get +1/+1.\n{R}: Until end of turn, another target Goblin you control gains flying and \"When this creature deals combat damage, sacrifice it.\"",
)

FIRE_ELEMENTAL = make_creature(
    name="Fire Elemental",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="",
)

GOBLIN_ORIFLAMME = make_enchantment(
    name="Goblin Oriflamme",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Attacking creatures you control get +1/+0.",
)

GOBLIN_SMUGGLER = make_creature(
    name="Goblin Smuggler",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Rogue"},
    text="Haste (This creature can attack and {T} as soon as it comes under your control.)\n{T}: Another target creature with power 2 or less can't be blocked this turn.",
)

KARGAN_DRAGONRIDER = make_creature(
    name="Kargan Dragonrider",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="As long as you control a Dragon, this creature has flying.",
)

KINDLED_FURY = make_instant(
    name="Kindled Fury",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +1/+0 and gains first strike until end of turn. (It deals combat damage before creatures without first strike.)",
)

RAGING_REDCAP = make_creature(
    name="Raging Redcap",
    power=1, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Knight"},
    text="Double strike (This creature deals both first-strike and regular combat damage.)",
)

RAPACIOUS_DRAGON = make_creature(
    name="Rapacious Dragon",
    power=3, toughness=3,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\nWhen this creature enters, create two Treasure tokens. (They're artifacts with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

SCORCHING_DRAGONFIRE = make_instant(
    name="Scorching Dragonfire",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Scorching Dragonfire deals 3 damage to target creature or planeswalker. If that creature or planeswalker would die this turn, exile it instead.",
)

SEIZE_THE_SPOILS = make_sorcery(
    name="Seize the Spoils",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="As an additional cost to cast this spell, discard a card.\nDraw two cards and create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

SKYRAKER_GIANT = make_creature(
    name="Skyraker Giant",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Giant"},
    text="Reach (This creature can block creatures with flying.)",
)

SWAB_GOBLIN = make_creature(
    name="Swab Goblin",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Pirate"},
    text="",
)

TERROR_OF_MOUNT_VELUS = make_creature(
    name="Terror of Mount Velus",
    power=5, toughness=5,
    mana_cost="{5}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\nDouble strike (This creature deals both first-strike and regular combat damage.)\nWhen this creature enters, creatures you control gain double strike until end of turn.",
)

VOLLEY_VETERAN = make_creature(
    name="Volley Veteran",
    power=4, toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="When this creature enters, it deals damage to target creature an opponent controls equal to the number of Goblins you control.",
)

AGGRESSIVE_MAMMOTH = make_creature(
    name="Aggressive Mammoth",
    power=8, toughness=8,
    mana_cost="{3}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elephant"},
    text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nOther creatures you control have trample.",
)

BEAR_CUB = make_creature(
    name="Bear Cub",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Bear"},
    text="",
)

BIOGENIC_UPGRADE = make_sorcery(
    name="Biogenic Upgrade",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Distribute three +1/+1 counters among one, two, or three target creatures, then double the number of +1/+1 counters on each of those creatures.",
)

DRUID_OF_THE_COWL = make_creature(
    name="Druid of the Cowl",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Elf"},
    text="{T}: Add {G}.",
)

JORAGA_INVOCATION = make_sorcery(
    name="Joraga Invocation",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Each creature you control gets +3/+3 until end of turn and must be blocked this turn if able.",
)

MAGNIGOTH_SENTRY = make_creature(
    name="Magnigoth Sentry",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="Reach (This creature can block creatures with flying.)",
)

NEW_HORIZONS = make_enchantment(
    name="New Horizons",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Enchant land\nWhen this Aura enters, put a +1/+1 counter on target creature you control.\nEnchanted land has \"{T}: Add two mana of any one color.\"",
    subtypes={"Aura"},
)

TAJURU_PATHWARDEN = make_creature(
    name="Tajuru Pathwarden",
    power=5, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Ally", "Elf", "Warrior"},
    text="Vigilance (Attacking doesn't cause this creature to tap.)\nTrample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)",
)

THORNWEALD_ARCHER = make_creature(
    name="Thornweald Archer",
    power=2, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Archer", "Elf"},
    text="Reach (This creature can block creatures with flying.)\nDeathtouch (Any amount of damage this deals to a creature is enough to destroy it.)",
)

THRASHING_BRONTODON = make_creature(
    name="Thrashing Brontodon",
    power=3, toughness=4,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="{1}, Sacrifice this creature: Destroy target artifact or enchantment.",
)

WILDHEART_INVOKER = make_creature(
    name="Wildheart Invoker",
    power=4, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Shaman"},
    text="{8}: Target creature gets +5/+5 and gains trample until end of turn. (It can deal excess combat damage to the player or planeswalker it's attacking.)",
)

GOBLIN_FIREBOMB = make_artifact(
    name="Goblin Firebomb",
    mana_cost="{1}",
    text="Flash\n{7}, {T}, Sacrifice this artifact: Destroy target permanent.",
)

PIRATES_CUTLASS = make_artifact(
    name="Pirate's Cutlass",
    mana_cost="{3}",
    text="When this Equipment enters, attach it to target Pirate you control.\nEquipped creature gets +2/+1.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

UNCHARTED_HAVEN = make_land(
    name="Uncharted Haven",
    text="This land enters tapped. As it enters, choose a color.\n{T}: Add one mana of the chosen color.",
)

ANGELIC_DESTINY = make_enchantment(
    name="Angelic Destiny",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Enchant creature\nEnchanted creature gets +4/+4, has flying and first strike, and is an Angel in addition to its other types.\nWhen enchanted creature dies, return this card to its owner's hand.",
    subtypes={"Aura"},
)

ARCHWAY_ANGEL = make_creature(
    name="Archway Angel",
    power=3, toughness=4,
    mana_cost="{5}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nWhen this creature enters, you gain 2 life for each Gate you control.",
)

BALLYRUSH_BANNERET = make_creature(
    name="Ballyrush Banneret",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Soldier"},
    text="Kithkin spells and Soldier spells you cast cost {1} less to cast.",
)

CHARMING_PRINCE = make_creature(
    name="Charming Prince",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    text="When this creature enters, choose one —\n• Scry 2.\n• You gain 3 life.\n• Exile another target creature you own. Return it to the battlefield under your control at the beginning of the next end step.",
)

CRUSADER_OF_ODRIC = make_creature(
    name="Crusader of Odric",
    power=0, toughness=0,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Crusader of Odric's power and toughness are each equal to the number of creatures you control.",
)

DAWNWING_MARSHAL = make_creature(
    name="Dawnwing Marshal",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Soldier"},
    text="Flying\n{4}{W}: Creatures you control get +1/+1 until end of turn.",
)

DEVOUT_DECREE = make_sorcery(
    name="Devout Decree",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Exile target creature or planeswalker that's black or red. Scry 1. (Look at the top card of your library. You may put that card on the bottom.)",
)

DISENCHANT = make_instant(
    name="Disenchant",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Destroy target artifact or enchantment.",
)

FELIDAR_CUB = make_creature(
    name="Felidar Cub",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Beast", "Cat"},
    text="Sacrifice this creature: Destroy target enchantment.",
)

FELIDAR_RETREAT = make_enchantment(
    name="Felidar Retreat",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Landfall — Whenever a land you control enters, choose one —\n• Create a 2/2 white Cat Beast creature token.\n• Put a +1/+1 counter on each creature you control. Those creatures gain vigilance until end of turn.",
)

FUMIGATE = make_sorcery(
    name="Fumigate",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Destroy all creatures. You gain 1 life for each creature destroyed this way.",
)

KNIGHT_OF_GRACE = make_creature(
    name="Knight of Grace",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="First strike (This creature deals combat damage before creatures without first strike.)\nHexproof from black (This creature can't be the target of black spells or abilities your opponents control.)\nThis creature gets +1/+0 as long as any player controls a black permanent.",
)

LINDEN_THE_STEADFAST_QUEEN = make_creature(
    name="Linden, the Steadfast Queen",
    power=3, toughness=3,
    mana_cost="{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Vigilance (Attacking doesn't cause this creature to tap.)\nWhenever a white creature you control attacks, you gain 1 life.",
)

MENTOR_OF_THE_MEEK = make_creature(
    name="Mentor of the Meek",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Whenever another creature you control with power 2 or less enters, you may pay {1}. If you do, draw a card.",
)

REGAL_CARACAL = make_creature(
    name="Regal Caracal",
    power=3, toughness=3,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Cat"},
    text="Other Cats you control get +1/+1 and have lifelink. (Damage dealt by those creatures also causes you to gain that much life.)\nWhen this creature enters, create two 1/1 white Cat creature tokens with lifelink.",
)

RELEASE_THE_DOGS = make_sorcery(
    name="Release the Dogs",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Create four 1/1 white Dog creature tokens.",
)

STASIS_SNARE = make_enchantment(
    name="Stasis Snare",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    text="Flash (You may cast this spell any time you could cast an instant.)\nWhen this enchantment enters, exile target creature an opponent controls until this enchantment leaves the battlefield.",
)

SYR_ALIN_THE_LIONS_CLAW = make_creature(
    name="Syr Alin, the Lion's Claw",
    power=4, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="First strike (This creature deals combat damage before creatures without first strike.)\nWhenever Syr Alin attacks, other creatures you control get +1/+1 until end of turn.",
)

VALOROUS_STANCE = make_instant(
    name="Valorous Stance",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Target creature gains indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)\n• Destroy target creature with toughness 4 or greater.",
)

ZETALPA_PRIMAL_DAWN = make_creature(
    name="Zetalpa, Primal Dawn",
    power=4, toughness=8,
    mana_cost="{6}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Dinosaur", "Elder"},
    supertypes={"Legendary"},
    text="Flying, double strike, vigilance, trample, indestructible",
)

ARCANIS_THE_OMNIPOTENT = make_creature(
    name="Arcanis the Omnipotent",
    power=3, toughness=4,
    mana_cost="{3}{U}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Wizard"},
    supertypes={"Legendary"},
    text="{T}: Draw three cards.\n{2}{U}{U}: Return Arcanis to its owner's hand.",
)

CHART_A_COURSE = make_sorcery(
    name="Chart a Course",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Draw two cards. Then discard a card unless you attacked this turn.",
)

DICTATE_OF_KRUPHIX = make_enchantment(
    name="Dictate of Kruphix",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Flash (You may cast this spell any time you could cast an instant.)\nAt the beginning of each player's draw step, that player draws an additional card.",
)

DIVE_DOWN = make_instant(
    name="Dive Down",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature you control gets +0/+3 and gains hexproof until end of turn. (It can't be the target of spells or abilities your opponents control.)",
)

FINALE_OF_REVELATION = make_sorcery(
    name="Finale of Revelation",
    mana_cost="{X}{U}{U}",
    colors={Color.BLUE},
    text="Draw X cards. If X is 10 or more, instead shuffle your graveyard into your library, draw X cards, untap up to five lands, and you have no maximum hand size for the rest of the game.\nExile Finale of Revelation.",
)

FLASHFREEZE = make_instant(
    name="Flashfreeze",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target red or green spell.",
)

FOG_BANK = make_creature(
    name="Fog Bank",
    power=0, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Wall"},
    text="Defender (This creature can't attack.)\nFlying\nPrevent all combat damage that would be dealt to and dealt by this creature.",
)

GATEWAY_SNEAK = make_creature(
    name="Gateway Sneak",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Rogue", "Vedalken"},
    text="Whenever a Gate you control enters, this creature can't be blocked this turn.\nWhenever this creature deals combat damage to a player, draw a card.",
)

HARBINGER_OF_THE_TIDES = make_creature(
    name="Harbinger of the Tides",
    power=2, toughness=2,
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="You may cast this spell as though it had flash if you pay {2} more to cast it. (You may cast it any time you could cast an instant.)\nWhen this creature enters, you may return target tapped creature an opponent controls to its owner's hand.",
)

MYSTICAL_TEACHINGS = make_instant(
    name="Mystical Teachings",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Search your library for an instant card or a card with flash, reveal it, put it into your hand, then shuffle.\nFlashback {5}{B} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

RIVERS_REBUKE = make_sorcery(
    name="River's Rebuke",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Return all nonland permanents target player controls to their owner's hand.",
)

SHIPWRECK_DOWSER = make_creature(
    name="Shipwreck Dowser",
    power=3, toughness=3,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nWhen this creature enters, return target instant or sorcery card from your graveyard to your hand.",
)

SPHINX_OF_THE_FINAL_WORD = make_creature(
    name="Sphinx of the Final Word",
    power=5, toughness=5,
    mana_cost="{5}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Sphinx"},
    text="This spell can't be countered.\nFlying\nHexproof (This creature can't be the target of spells or abilities your opponents control.)\nInstant and sorcery spells you control can't be countered.",
)

TEMPEST_DJINN = make_creature(
    name="Tempest Djinn",
    power=0, toughness=4,
    mana_cost="{U}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Djinn"},
    text="Flying\nThis creature gets +1/+0 for each basic Island you control.",
)

UNSUMMON = make_instant(
    name="Unsummon",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Return target creature to its owner's hand.",
)

VORACIOUS_GREATSHARK = make_creature(
    name="Voracious Greatshark",
    power=5, toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Shark"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nWhen this creature enters, counter target artifact or creature spell.",
)

DEATHMARK = make_sorcery(
    name="Deathmark",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Destroy target green or white creature.",
)

DEMONIC_PACT = make_enchantment(
    name="Demonic Pact",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, choose one that hasn't been chosen —\n• This enchantment deals 4 damage to any target and you gain 4 life.\n• Target opponent discards two cards.\n• Draw two cards.\n• You lose the game.",
)

DESECRATION_DEMON = make_creature(
    name="Desecration Demon",
    power=6, toughness=6,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Flying\nAt the beginning of each combat, any opponent may sacrifice a creature of their choice. If a player does, tap this creature and put a +1/+1 counter on it.",
)

DREAD_SUMMONS = make_sorcery(
    name="Dread Summons",
    mana_cost="{X}{B}{B}",
    colors={Color.BLACK},
    text="Each player mills X cards. For each creature card put into a graveyard this way, you create a tapped 2/2 black Zombie creature token. (To mill a card, a player puts the top card of their library into their graveyard.)",
)

DRIVER_OF_THE_DEAD = make_creature(
    name="Driver of the Dead",
    power=3, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="When this creature dies, return target creature card with mana value 2 or less from your graveyard to the battlefield.",
)

DURESS = make_sorcery(
    name="Duress",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target opponent reveals their hand. You choose a noncreature, nonland card from it. That player discards that card.",
)

KALASTRIA_HIGHBORN = make_creature(
    name="Kalastria Highborn",
    power=2, toughness=2,
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    subtypes={"Shaman", "Vampire"},
    text="Whenever this creature or another Vampire you control dies, you may pay {B}. If you do, target player loses 2 life and you gain 2 life.",
)

KNIGHT_OF_MALICE = make_creature(
    name="Knight of Malice",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Knight"},
    text="First strike (This creature deals combat damage before creatures without first strike.)\nHexproof from white (This creature can't be the target of white spells or abilities your opponents control.)\nThis creature gets +1/+0 as long as any player controls a white permanent.",
)

MIDNIGHT_REAPER = make_creature(
    name="Midnight Reaper",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Knight", "Zombie"},
    text="Whenever a nontoken creature you control dies, this creature deals 1 damage to you and you draw a card.",
)

MYOJIN_OF_NIGHTS_REACH = make_creature(
    name="Myojin of Night's Reach",
    power=5, toughness=2,
    mana_cost="{5}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    text="Myojin of Night's Reach enters with a divinity counter on it if you cast it from your hand.\nMyojin of Night's Reach has indestructible as long as it has a divinity counter on it.\nRemove a divinity counter from Myojin of Night's Reach: Each opponent discards their hand.",
)

NULLPRIEST_OF_OBLIVION = make_creature(
    name="Nullpriest of Oblivion",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Vampire"},
    text="Kicker {3}{B} (You may pay an additional {3}{B} as you cast this spell.)\nLifelink\nMenace (This creature can't be blocked except by two or more creatures.)\nWhen this creature enters, if it was kicked, return target creature card from your graveyard to the battlefield.",
)

PULSE_TRACKER = make_creature(
    name="Pulse Tracker",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Vampire"},
    text="Whenever this creature attacks, each opponent loses 1 life.",
)

SANGUINE_INDULGENCE = make_sorcery(
    name="Sanguine Indulgence",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="This spell costs {3} less to cast if you've gained 3 or more life this turn.\nReturn up to two target creature cards from your graveyard to your hand.",
)

TRIBUTE_TO_HUNGER = make_instant(
    name="Tribute to Hunger",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Target opponent sacrifices a creature of their choice. You gain life equal to that creature's toughness.",
)

VAMPIRIC_RITES = make_enchantment(
    name="Vampiric Rites",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="{1}{B}, Sacrifice a creature: You gain 1 life and draw a card.",
)

VILE_ENTOMBER = make_creature(
    name="Vile Entomber",
    power=2, toughness=2,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Warlock", "Zombie"},
    text="Deathtouch (Any amount of damage this deals to a creature is enough to destroy it.)\nWhen this creature enters, search your library for a card, put that card into your graveyard, then shuffle.",
)

WISHCLAW_TALISMAN = make_artifact(
    name="Wishclaw Talisman",
    mana_cost="{1}{B}",
    text="This artifact enters with three wish counters on it.\n{1}, {T}, Remove a wish counter from this artifact: Search your library for a card, put it into your hand, then shuffle. An opponent gains control of this artifact. Activate only during your turn.",
)

BALL_LIGHTNING = make_creature(
    name="Ball Lightning",
    power=6, toughness=1,
    mana_cost="{R}{R}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nHaste (This creature can attack and {T} as soon as it comes under your control.)\nAt the beginning of the end step, sacrifice this creature.",
)

BOLT_BEND = make_instant(
    name="Bolt Bend",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="This spell costs {3} less to cast if you control a creature with power 4 or greater.\nChange the target of target spell or ability with a single target.",
)

CRASH_THROUGH = make_sorcery(
    name="Crash Through",
    mana_cost="{R}",
    colors={Color.RED},
    text="Creatures you control gain trample until end of turn. (Each of those creatures can deal excess combat damage to the player or planeswalker it's attacking.)\nDraw a card.",
)

DRAGON_MAGE = make_creature(
    name="Dragon Mage",
    power=5, toughness=5,
    mana_cost="{5}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon", "Wizard"},
    text="Flying\nWhenever this creature deals combat damage to a player, each player discards their hand, then draws seven cards.",
)

DRAGONMASTER_OUTCAST = make_creature(
    name="Dragonmaster Outcast",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Shaman"},
    text="At the beginning of your upkeep, if you control six or more lands, create a 5/5 red Dragon creature token with flying.",
)

GHITU_LAVARUNNER = make_creature(
    name="Ghitu Lavarunner",
    power=1, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard"},
    text="As long as there are two or more instant and/or sorcery cards in your graveyard, this creature gets +1/+0 and has haste. (It can attack and {T} as soon as it comes under your control.)",
)

GIANT_CINDERMAW = make_creature(
    name="Giant Cindermaw",
    power=4, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Beast", "Dinosaur"},
    text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nPlayers can't gain life.",
)

HARMLESS_OFFERING = make_sorcery(
    name="Harmless Offering",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Target opponent gains control of target permanent you control.",
)

HOARDING_DRAGON = make_creature(
    name="Hoarding Dragon",
    power=4, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\nWhen this creature enters, you may search your library for an artifact card, exile it, then shuffle.\nWhen this creature dies, you may put the exiled card into its owner's hand.",
)

LATHLISS_DRAGON_QUEEN = make_creature(
    name="Lathliss, Dragon Queen",
    power=6, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    supertypes={"Legendary"},
    text="Flying\nWhenever another nontoken Dragon you control enters, create a 5/5 red Dragon creature token with flying.\n{1}{R}: Dragons you control get +1/+0 until end of turn.",
)

MINDSPARKER = make_creature(
    name="Mindsparker",
    power=3, toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="First strike (This creature deals combat damage before creatures without first strike.)\nWhenever an opponent casts a white or blue instant or sorcery spell, this creature deals 2 damage to that player.",
)

OBLITERATING_BOLT = make_sorcery(
    name="Obliterating Bolt",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Obliterating Bolt deals 4 damage to target creature or planeswalker. If that creature or planeswalker would die this turn, exile it instead.",
)

RAVENOUS_GIANT = make_creature(
    name="Ravenous Giant",
    power=5, toughness=5,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Giant"},
    text="At the beginning of your upkeep, this creature deals 1 damage to you.",
)

REDCAP_GUTTERDWELLER = make_creature(
    name="Redcap Gutter-Dweller",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="Menace\nWhen this creature enters, create two 1/1 black Rat creature tokens with \"This token can't block.\"\nAt the beginning of your upkeep, you may sacrifice another creature. If you do, put a +1/+1 counter on this creature and exile the top card of your library. You may play that card this turn.",
)

STROMKIRK_NOBLE = make_creature(
    name="Stromkirk Noble",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Noble", "Vampire"},
    text="This creature can't be blocked by Humans.\nWhenever this creature deals combat damage to a player, put a +1/+1 counter on it.",
)

TAUREAN_MAULER = make_creature(
    name="Taurean Mauler",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Shapeshifter"},
    text="Changeling (This card is every creature type.)\nWhenever an opponent casts a spell, you may put a +1/+1 counter on this creature.",
)

VIASHINO_PYROMANCER = make_creature(
    name="Viashino Pyromancer",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Wizard"},
    text="When this creature enters, it deals 2 damage to target player or planeswalker.",
)

CIRCUITOUS_ROUTE = make_sorcery(
    name="Circuitous Route",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Search your library for up to two basic land cards and/or Gate cards, put them onto the battlefield tapped, then shuffle.",
)

FIERCE_EMPATH = make_creature(
    name="Fierce Empath",
    power=1, toughness=1,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elf"},
    text="When this creature enters, you may search your library for a creature card with mana value 6 or greater, reveal it, put it into your hand, then shuffle.",
)

FYNN_THE_FANGBEARER = make_creature(
    name="Fynn, the Fangbearer",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Deathtouch (Any amount of damage this deals to a creature is enough to destroy it.)\nWhenever a creature you control with deathtouch deals combat damage to a player, that player gets two poison counters. (A player with ten or more poison counters loses the game.)",
)

GNARLBACK_RHINO = make_creature(
    name="Gnarlback Rhino",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Rhino"},
    text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nWhenever you cast a spell that targets this creature, draw a card.",
)

HEROES_BANE = make_creature(
    name="Heroes' Bane",
    power=0, toughness=0,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Hydra"},
    text="This creature enters with four +1/+1 counters on it.\n{2}{G}{G}: Put X +1/+1 counters on this creature, where X is its power.",
)

MOLD_ADDER = make_creature(
    name="Mold Adder",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Fungus", "Snake"},
    text="Whenever an opponent casts a blue or black spell, you may put a +1/+1 counter on this creature.",
)

ORDEAL_OF_NYLEA = make_enchantment(
    name="Ordeal of Nylea",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Enchant creature\nWhenever enchanted creature attacks, put a +1/+1 counter on it. Then if it has three or more +1/+1 counters on it, sacrifice this Aura.\nWhen you sacrifice this Aura, search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.",
    subtypes={"Aura"},
)

PREDATOR_OOZE = make_creature(
    name="Predator Ooze",
    power=1, toughness=1,
    mana_cost="{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Ooze"},
    text="Indestructible (Damage and effects that say \"destroy\" don't destroy this creature.)\nWhenever this creature attacks, put a +1/+1 counter on it.\nWhenever a creature dealt damage by this creature this turn dies, put a +1/+1 counter on this creature.",
)

PRIMAL_MIGHT = make_sorcery(
    name="Primal Might",
    mana_cost="{X}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +X/+X until end of turn. Then it fights up to one target creature you don't control. (Each deals damage equal to its power to the other.)",
)

PRIMEVAL_BOUNTY = make_enchantment(
    name="Primeval Bounty",
    mana_cost="{5}{G}",
    colors={Color.GREEN},
    text="Whenever you cast a creature spell, create a 3/3 green Beast creature token.\nWhenever you cast a noncreature spell, put three +1/+1 counters on target creature you control.\nLandfall — Whenever a land you control enters, you gain 3 life.",
)

RAMPAGING_BALOTHS = make_creature(
    name="Rampaging Baloths",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample\nLandfall — Whenever a land you control enters, create a 4/4 green Beast creature token.",
)

SPRINGBLOOM_DRUID = make_creature(
    name="Springbloom Druid",
    power=1, toughness=1,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Elf"},
    text="When this creature enters, you may sacrifice a land. If you do, search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.",
)

SURRAK_THE_HUNT_CALLER = make_creature(
    name="Surrak, the Hunt Caller",
    power=5, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Formidable — At the beginning of combat on your turn, if creatures you control have total power 8 or greater, target creature you control gains haste until end of turn. (It can attack and {T} no matter when it came under your control.)",
)

VENOM_CONNOISSEUR = make_creature(
    name="Venom Connoisseur",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Human"},
    text="Alliance — Whenever another creature you control enters, this creature gains deathtouch until end of turn. If this is the second time this ability has resolved this turn, all creatures you control gain deathtouch until end of turn.",
)

VIZIER_OF_THE_MENAGERIE = make_creature(
    name="Vizier of the Menagerie",
    power=3, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Cleric", "Snake"},
    text="You may look at the top card of your library any time.\nYou may cast creature spells from the top of your library.\nYou can spend mana of any type to cast creature spells.",
)

WILDBORN_PRESERVER = make_creature(
    name="Wildborn Preserver",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Archer", "Elf"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nReach (This creature can block creatures with flying.)\nWhenever another non-Human creature you control enters, you may pay {X}. When you do, put X +1/+1 counters on this creature.",
)

AURELIA_THE_WARLEADER = make_creature(
    name="Aurelia, the Warleader",
    power=3, toughness=4,
    mana_cost="{2}{R}{R}{W}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Angel"},
    supertypes={"Legendary"},
    text="Flying, vigilance, haste\nWhenever Aurelia attacks for the first time each turn, untap all creatures you control. After this phase, there is an additional combat phase.",
)

AYLI_ETERNAL_PILGRIM = make_creature(
    name="Ayli, Eternal Pilgrim",
    power=2, toughness=3,
    mana_cost="{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Cleric", "Kor"},
    supertypes={"Legendary"},
    text="Deathtouch (Any amount of damage this deals to a creature is enough to destroy it.)\n{1}, Sacrifice another creature: You gain life equal to the sacrificed creature's toughness.\n{1}{W}{B}, Sacrifice another creature: Exile target nonland permanent. Activate only if you have at least 10 life more than your starting life total.",
)

CLOUDBLAZER = make_creature(
    name="Cloudblazer",
    power=2, toughness=2,
    mana_cost="{3}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Scout"},
    text="Flying\nWhen this creature enters, you gain 2 life and draw two cards.",
)

DEADLY_BREW = make_sorcery(
    name="Deadly Brew",
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Each player sacrifices a creature or planeswalker of their choice. If you sacrificed a permanent this way, you may return another permanent card from your graveyard to your hand.",
)

DROGSKOL_REAVER = make_creature(
    name="Drogskol Reaver",
    power=3, toughness=5,
    mana_cost="{5}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Spirit"},
    text="Flying\nDouble strike (This creature deals both first-strike and regular combat damage.)\nLifelink (Damage dealt by this creature also causes you to gain that much life.)\nWhenever you gain life, draw a card.",
)

DRYAD_MILITANT = make_creature(
    name="Dryad Militant",
    power=2, toughness=1,
    mana_cost="{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Dryad", "Soldier"},
    text="({G/W} can be paid with either {G} or {W}.)\nIf an instant or sorcery card would be put into a graveyard from anywhere, exile it instead.",
)

ENIGMA_DRAKE = make_creature(
    name="Enigma Drake",
    power=0, toughness=4,
    mana_cost="{1}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Drake"},
    text="Flying\nEnigma Drake's power is equal to the number of instant and sorcery cards in your graveyard.",
)

GARNA_BLOODFIST_OF_KELD = make_creature(
    name="Garna, Bloodfist of Keld",
    power=4, toughness=3,
    mana_cost="{1}{B}{R}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Berserker", "Human"},
    supertypes={"Legendary"},
    text="Whenever another creature you control dies, draw a card if it was attacking. Otherwise, Garna deals 1 damage to each opponent.",
)

HALANA_AND_ALENA_PARTNERS = make_creature(
    name="Halana and Alena, Partners",
    power=2, toughness=3,
    mana_cost="{2}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Ranger"},
    supertypes={"Legendary"},
    text="First strike (This creature deals combat damage before creatures without first strike.)\nReach (This creature can block creatures with flying.)\nAt the beginning of combat on your turn, put X +1/+1 counters on another target creature you control, where X is Halana and Alena's power. That creature gains haste until end of turn.",
)

IMMERSTURM_PREDATOR = make_creature(
    name="Immersturm Predator",
    power=3, toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Dragon", "Vampire"},
    text="Flying\nWhenever this creature becomes tapped, exile up to one target card from a graveyard and put a +1/+1 counter on this creature.\nSacrifice another creature: This creature gains indestructible until end of turn. Tap it.",
)

MAELSTROM_PULSE = make_sorcery(
    name="Maelstrom Pulse",
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Destroy target nonland permanent and all other permanents with the same name as that permanent.",
)

MORTIFY = make_instant(
    name="Mortify",
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    text="Destroy target creature or enchantment.",
)

OVIKA_ENIGMA_GOLIATH = make_creature(
    name="Ovika, Enigma Goliath",
    power=6, toughness=6,
    mana_cost="{5}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Nightmare", "Phyrexian"},
    supertypes={"Legendary"},
    text="Flying\nWard—{3}, Pay 3 life.\nWhenever you cast a noncreature spell, create X 1/1 red Phyrexian Goblin creature tokens, where X is the mana value of that spell. They gain haste until end of turn.",
)

PRIME_SPEAKER_ZEGANA = make_creature(
    name="Prime Speaker Zegana",
    power=1, toughness=1,
    mana_cost="{2}{G}{G}{U}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    supertypes={"Legendary"},
    text="Prime Speaker Zegana enters with X +1/+1 counters on it, where X is the greatest power among other creatures you control.\nWhen Prime Speaker Zegana enters, draw cards equal to its power.",
)

SAVAGE_VENTMAW = make_creature(
    name="Savage Ventmaw",
    power=4, toughness=4,
    mana_cost="{4}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Dragon"},
    text="Flying\nWhenever this creature attacks, add {R}{R}{R}{G}{G}{G}. Until end of turn, you don't lose this mana as steps and phases end.",
)

TEACH_BY_EXAMPLE = make_instant(
    name="Teach by Example",
    mana_cost="{U/R}{U/R}",
    colors={Color.RED, Color.BLUE},
    text="({U/R} can be paid with either {U} or {R}.)\nWhen you next cast an instant or sorcery spell this turn, copy that spell. You may choose new targets for the copy.",
)

TRYGON_PREDATOR = make_creature(
    name="Trygon Predator",
    power=2, toughness=3,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Beast"},
    text="Flying\nWhenever this creature deals combat damage to a player, you may destroy target artifact or enchantment that player controls.",
)

WILTLEAF_LIEGE = make_creature(
    name="Wilt-Leaf Liege",
    power=4, toughness=4,
    mana_cost="{1}{G/W}{G/W}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Elf", "Knight"},
    text="({G/W} can be paid with either {G} or {W}.)\nOther green creatures you control get +1/+1.\nOther white creatures you control get +1/+1.\nIf a spell or ability an opponent controls causes you to discard this card, put it onto the battlefield instead of putting it into your graveyard.",
)

BASILISK_COLLAR = make_artifact(
    name="Basilisk Collar",
    mana_cost="{1}",
    text="Equipped creature has deathtouch and lifelink. (Any amount of damage it deals to a creature is enough to destroy it. Damage dealt by this creature also causes you to gain that much life.)\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

CULTIVATORS_CARAVAN = make_artifact(
    name="Cultivator's Caravan",
    mana_cost="{3}",
    text="{T}: Add one mana of any color.\nCrew 3 (Tap any number of creatures you control with total power 3 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
)

DARKSTEEL_COLOSSUS = make_artifact_creature(
    name="Darksteel Colossus",
    power=11, toughness=11,
    mana_cost="{11}",
    colors=set(),
    subtypes={"Golem"},
    text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nIndestructible (Damage and effects that say \"destroy\" don't destroy this creature.)\nIf Darksteel Colossus would be put into a graveyard from anywhere, reveal Darksteel Colossus and shuffle it into its owner's library instead.",
)

DIAMOND_MARE = make_artifact_creature(
    name="Diamond Mare",
    power=1, toughness=3,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Horse"},
    text="As this creature enters, choose a color.\nWhenever you cast a spell of the chosen color, you gain 1 life.",
)

FELDONS_CANE = make_artifact(
    name="Feldon's Cane",
    mana_cost="{1}",
    text="{T}, Exile this artifact: Shuffle your graveyard into your library.",
)

FIRESHRIEKER = make_artifact(
    name="Fireshrieker",
    mana_cost="{3}",
    text="Equipped creature has double strike. (It deals both first-strike and regular combat damage.)\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

GATE_COLOSSUS = make_artifact_creature(
    name="Gate Colossus",
    power=8, toughness=8,
    mana_cost="{8}",
    colors=set(),
    subtypes={"Construct"},
    text="Affinity for Gates (This spell costs {1} less to cast for each Gate you control.)\nThis creature can't be blocked by creatures with power 2 or less.\nWhenever a Gate you control enters, you may put this card from your graveyard on top of your library.",
)

MAZEMIND_TOME = make_artifact(
    name="Mazemind Tome",
    mana_cost="{2}",
    text="{T}, Put a page counter on this artifact: Scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{2}, {T}, Put a page counter on this artifact: Draw a card.\nWhen there are four or more page counters on this artifact, exile it. If you do, you gain 4 life.",
)

PYROMANCERS_GOGGLES = make_artifact(
    name="Pyromancer's Goggles",
    mana_cost="{5}",
    text="{T}: Add {R}. When that mana is spent to cast a red instant or sorcery spell, copy that spell and you may choose new targets for the copy.",
    supertypes={"Legendary"},
)

RAMOS_DRAGON_ENGINE = make_artifact_creature(
    name="Ramos, Dragon Engine",
    power=4, toughness=4,
    mana_cost="{6}",
    colors=set(),
    subtypes={"Dragon"},
    supertypes={"Legendary"},
    text="Flying\nWhenever you cast a spell, put a +1/+1 counter on Ramos for each of that spell's colors.\nRemove five +1/+1 counters from Ramos: Add {W}{W}{U}{U}{B}{B}{R}{R}{G}{G}. Activate only once each turn.",
)

SORCEROUS_SPYGLASS = make_artifact(
    name="Sorcerous Spyglass",
    mana_cost="{2}",
    text="As this artifact enters, look at an opponent's hand, then choose any card name.\nActivated abilities of sources with the chosen name can't be activated unless they're mana abilities.",
)

SOULGUIDE_LANTERN = make_artifact(
    name="Soul-Guide Lantern",
    mana_cost="{1}",
    text="When this artifact enters, exile target card from a graveyard.\n{T}, Sacrifice this artifact: Exile each opponent's graveyard.\n{1}, {T}, Sacrifice this artifact: Draw a card.",
)

STEEL_HELLKITE = make_artifact_creature(
    name="Steel Hellkite",
    power=5, toughness=5,
    mana_cost="{6}",
    colors=set(),
    subtypes={"Dragon"},
    text="Flying\n{2}: This creature gets +1/+0 until end of turn.\n{X}: Destroy each nonland permanent with mana value X whose controller was dealt combat damage by this creature this turn. Activate only once each turn.",
)

THREE_TREE_MASCOT = make_artifact_creature(
    name="Three Tree Mascot",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Shapeshifter"},
    text="Changeling (This card is every creature type.)\n{1}: Add one mana of any color. Activate only once each turn.",
)

AZORIUS_GUILDGATE = make_land(
    name="Azorius Guildgate",
    text="This land enters tapped.\n{T}: Add {W} or {U}.",
    subtypes={"Gate"},
)

BOROS_GUILDGATE = make_land(
    name="Boros Guildgate",
    text="This land enters tapped.\n{T}: Add {R} or {W}.",
    subtypes={"Gate"},
)

CRAWLING_BARRENS = make_land(
    name="Crawling Barrens",
    text="{T}: Add {C}.\n{4}: Put two +1/+1 counters on this land. Then you may have it become a 0/0 Elemental creature until end of turn. It's still a land.",
)

CRYPTIC_CAVES = make_land(
    name="Cryptic Caves",
    text="{T}: Add {C}.\n{1}, {T}, Sacrifice this land: Draw a card. Activate only if you control five or more lands.",
)

DEMOLITION_FIELD = make_land(
    name="Demolition Field",
    text="{T}: Add {C}.\n{2}, {T}, Sacrifice this land: Destroy target nonbasic land an opponent controls. That land's controller may search their library for a basic land card, put it onto the battlefield, then shuffle. You may search your library for a basic land card, put it onto the battlefield, then shuffle.",
)

DIMIR_GUILDGATE = make_land(
    name="Dimir Guildgate",
    text="This land enters tapped.\n{T}: Add {U} or {B}.",
    subtypes={"Gate"},
)

GOLGARI_GUILDGATE = make_land(
    name="Golgari Guildgate",
    text="This land enters tapped.\n{T}: Add {B} or {G}.",
    subtypes={"Gate"},
)

GRUUL_GUILDGATE = make_land(
    name="Gruul Guildgate",
    text="This land enters tapped.\n{T}: Add {R} or {G}.",
    subtypes={"Gate"},
)

IZZET_GUILDGATE = make_land(
    name="Izzet Guildgate",
    text="This land enters tapped.\n{T}: Add {U} or {R}.",
    subtypes={"Gate"},
)

ORZHOV_GUILDGATE = make_land(
    name="Orzhov Guildgate",
    text="This land enters tapped.\n{T}: Add {W} or {B}.",
    subtypes={"Gate"},
)

RAKDOS_GUILDGATE = make_land(
    name="Rakdos Guildgate",
    text="This land enters tapped.\n{T}: Add {B} or {R}.",
    subtypes={"Gate"},
)

SELESNYA_GUILDGATE = make_land(
    name="Selesnya Guildgate",
    text="This land enters tapped.\n{T}: Add {G} or {W}.",
    subtypes={"Gate"},
)

SIMIC_GUILDGATE = make_land(
    name="Simic Guildgate",
    text="This land enters tapped.\n{T}: Add {G} or {U}.",
    subtypes={"Gate"},
)

TEMPLE_OF_ABANDON = make_land(
    name="Temple of Abandon",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {R} or {G}.",
)

TEMPLE_OF_DECEIT = make_land(
    name="Temple of Deceit",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {U} or {B}.",
)

TEMPLE_OF_ENLIGHTENMENT = make_land(
    name="Temple of Enlightenment",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {W} or {U}.",
)

TEMPLE_OF_EPIPHANY = make_land(
    name="Temple of Epiphany",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {U} or {R}.",
)

TEMPLE_OF_MALADY = make_land(
    name="Temple of Malady",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {B} or {G}.",
)

TEMPLE_OF_MALICE = make_land(
    name="Temple of Malice",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {B} or {R}.",
)

TEMPLE_OF_MYSTERY = make_land(
    name="Temple of Mystery",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {G} or {U}.",
)

TEMPLE_OF_PLENTY = make_land(
    name="Temple of Plenty",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {G} or {W}.",
)

TEMPLE_OF_SILENCE = make_land(
    name="Temple of Silence",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {W} or {B}.",
)

TEMPLE_OF_TRIUMPH = make_land(
    name="Temple of Triumph",
    text="This land enters tapped.\nWhen this land enters, scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{T}: Add {R} or {W}.",
)

ANGEL_OF_VITALITY = make_creature(
    name="Angel of Vitality",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nIf you would gain life, you gain that much life plus 1 instead.\nThis creature gets +2/+2 as long as you have 25 or more life.",
)

LYRA_DAWNBRINGER = make_creature(
    name="Lyra Dawnbringer",
    power=5, toughness=5,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    supertypes={"Legendary"},
    text="Flying\nFirst strike (This creature deals combat damage before creatures without first strike.)\nLifelink (Damage dealt by this creature also causes you to gain that much life.)\nOther Angels you control get +1/+1 and have lifelink.",
)

MAKE_A_STAND = make_instant(
    name="Make a Stand",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +1/+0 and gain indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy them.)",
)

CONFISCATE = make_enchantment(
    name="Confiscate",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Enchant permanent\nYou control enchanted permanent.",
    subtypes={"Aura"},
)

NEGATE = make_instant(
    name="Negate",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target noncreature spell.",
)

RITE_OF_REPLICATION = make_sorcery(
    name="Rite of Replication",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Kicker {5} (You may pay an additional {5} as you cast this spell.)\nCreate a token that's a copy of target creature. If this spell was kicked, create five of those tokens instead.",
)

FEED_THE_SWARM = make_sorcery(
    name="Feed the Swarm",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Destroy target creature or enchantment an opponent controls. You lose life equal to that permanent's mana value.",
)

GATEKEEPER_OF_MALAKIR = make_creature(
    name="Gatekeeper of Malakir",
    power=2, toughness=2,
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Warrior"},
    text="Kicker {B} (You may pay an additional {B} as you cast this spell.)\nWhen this creature enters, if it was kicked, target player sacrifices a creature of their choice.",
)

MASSACRE_WURM = make_creature(
    name="Massacre Wurm",
    power=6, toughness=5,
    mana_cost="{3}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Phyrexian", "Wurm"},
    text="When this creature enters, creatures your opponents control get -2/-2 until end of turn.\nWhenever a creature an opponent controls dies, that player loses 2 life.",
)

GRATUITOUS_VIOLENCE = make_enchantment(
    name="Gratuitous Violence",
    mana_cost="{2}{R}{R}{R}",
    colors={Color.RED},
    text="If a creature you control would deal damage to a permanent or player, it deals double that damage instead.",
)

GUTTERSNIPE = make_creature(
    name="Guttersnipe",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Shaman"},
    text="Whenever you cast an instant or sorcery spell, this creature deals 2 damage to each opponent.",
)

IMPACT_TREMORS = make_enchantment(
    name="Impact Tremors",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Whenever a creature you control enters, this enchantment deals 1 damage to each opponent.",
)

GIGANTOSAURUS = make_creature(
    name="Gigantosaurus",
    power=10, toughness=10,
    mana_cost="{G}{G}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="",
)

IMPERIOUS_PERFECT = make_creature(
    name="Imperious Perfect",
    power=2, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    text="Other Elves you control get +1/+1.\n{G}, {T}: Create a 1/1 green Elf Warrior creature token.",
)

PELAKKA_WURM = make_creature(
    name="Pelakka Wurm",
    power=7, toughness=7,
    mana_cost="{4}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Wurm"},
    text="Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nWhen this creature enters, you gain 7 life.\nWhen this creature dies, draw a card.",
)

BOROS_CHARM = make_instant(
    name="Boros Charm",
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Choose one —\n• Boros Charm deals 4 damage to target player or planeswalker.\n• Permanents you control gain indestructible until end of turn.\n• Target creature gains double strike until end of turn.",
)

UNFLINCHING_COURAGE = make_enchantment(
    name="Unflinching Courage",
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Enchant creature\nEnchanted creature gets +2/+2 and has trample and lifelink. (Damage dealt by the creature also causes its controller to gain that much life.)",
    subtypes={"Aura"},
)

ADAPTIVE_AUTOMATON = make_artifact_creature(
    name="Adaptive Automaton",
    power=2, toughness=2,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Construct"},
    text="As this creature enters, choose a creature type.\nThis creature is the chosen type in addition to its other types.\nOther creatures you control of the chosen type get +1/+1.",
)

EXPEDITION_MAP = make_artifact(
    name="Expedition Map",
    mana_cost="{1}",
    text="{2}, {T}, Sacrifice this artifact: Search your library for a land card, reveal it, put it into your hand, then shuffle.",
)

GILDED_LOTUS = make_artifact(
    name="Gilded Lotus",
    mana_cost="{5}",
    text="{T}: Add three mana of any one color.",
)

HEDRON_ARCHIVE = make_artifact(
    name="Hedron Archive",
    mana_cost="{4}",
    text="{T}: Add {C}{C}.\n{2}, {T}, Sacrifice this artifact: Draw two cards.",
)

MAZES_END = make_land(
    name="Maze's End",
    text="This land enters tapped.\n{T}: Add {C}.\n{3}, {T}, Return this land to its owner's hand: Search your library for a Gate card, put it onto the battlefield, then shuffle. If you control ten or more Gates with different names, you win the game.",
)

HINTERLAND_SANCTIFIER = make_creature(
    name="Hinterland Sanctifier",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Rabbit"},
    text="Whenever another creature you control enters, you gain 1 life.",
)

# =============================================================================
# CARD REGISTRY
# =============================================================================

FOUNDATIONS_CARDS = {
    "Sire of Seven Deaths": SIRE_OF_SEVEN_DEATHS,
    "Arahbo, the First Fang": ARAHBO_THE_FIRST_FANG,
    "Armasaur Guide": ARMASAUR_GUIDE,
    "Cat Collector": CAT_COLLECTOR,
    "Celestial Armor": CELESTIAL_ARMOR,
    "Claws Out": CLAWS_OUT,
    "Crystal Barricade": CRYSTAL_BARRICADE,
    "Dauntless Veteran": DAUNTLESS_VETERAN,
    "Dazzling Angel": DAZZLING_ANGEL,
    "Divine Resilience": DIVINE_RESILIENCE,
    "Exemplar of Light": EXEMPLAR_OF_LIGHT,
    "Felidar Savior": FELIDAR_SAVIOR,
    "Fleeting Flight": FLEETING_FLIGHT,
    "Guarded Heir": GUARDED_HEIR,
    "Hare Apparent": HARE_APPARENT,
    "Helpful Hunter": HELPFUL_HUNTER,
    "Herald of Eternal Dawn": HERALD_OF_ETERNAL_DAWN,
    "Inspiring Paladin": INSPIRING_PALADIN,
    "Joust Through": JOUST_THROUGH,
    "Luminous Rebuke": LUMINOUS_REBUKE,
    "Prideful Parent": PRIDEFUL_PARENT,
    "Raise the Past": RAISE_THE_PAST,
    "Skyknight Squire": SKYKNIGHT_SQUIRE,
    "Squad Rallier": SQUAD_RALLIER,
    "Sun-Blessed Healer": SUNBLESSED_HEALER,
    "Twinblade Blessing": TWINBLADE_BLESSING,
    "Valkyrie's Call": VALKYRIES_CALL,
    "Vanguard Seraph": VANGUARD_SERAPH,
    "Arcane Epiphany": ARCANE_EPIPHANY,
    "Archmage of Runes": ARCHMAGE_OF_RUNES,
    "Bigfin Bouncer": BIGFIN_BOUNCER,
    "Cephalid Inkmage": CEPHALID_INKMAGE,
    "Clinquant Skymage": CLINQUANT_SKYMAGE,
    "Curator of Destinies": CURATOR_OF_DESTINIES,
    "Drake Hatcher": DRAKE_HATCHER,
    "Elementalist Adept": ELEMENTALIST_ADEPT,
    "Erudite Wizard": ERUDITE_WIZARD,
    "Faebloom Trick": FAEBLOOM_TRICK,
    "Grappling Kraken": GRAPPLING_KRAKEN,
    "High Fae Trickster": HIGH_FAE_TRICKSTER,
    "Homunculus Horde": HOMUNCULUS_HORDE,
    "Icewind Elemental": ICEWIND_ELEMENTAL,
    "Inspiration from Beyond": INSPIRATION_FROM_BEYOND,
    "Kaito, Cunning Infiltrator": KAITO_CUNNING_INFILTRATOR,
    "Kiora, the Rising Tide": KIORA_THE_RISING_TIDE,
    "Lunar Insight": LUNAR_INSIGHT,
    "Mischievous Mystic": MISCHIEVOUS_MYSTIC,
    "Refute": REFUTE,
    "Rune-Sealed Wall": RUNESEALED_WALL,
    "Skyship Buccaneer": SKYSHIP_BUCCANEER,
    "Sphinx of Forgotten Lore": SPHINX_OF_FORGOTTEN_LORE,
    "Strix Lookout": STRIX_LOOKOUT,
    "Uncharted Voyage": UNCHARTED_VOYAGE,
    "Abyssal Harvester": ABYSSAL_HARVESTER,
    "Arbiter of Woe": ARBITER_OF_WOE,
    "Billowing Shriekmass": BILLOWING_SHRIEKMASS,
    "Blasphemous Edict": BLASPHEMOUS_EDICT,
    "Bloodthirsty Conqueror": BLOODTHIRSTY_CONQUEROR,
    "Crypt Feaster": CRYPT_FEASTER,
    "Gutless Plunderer": GUTLESS_PLUNDERER,
    "High-Society Hunter": HIGHSOCIETY_HUNTER,
    "Hungry Ghoul": HUNGRY_GHOUL,
    "Infernal Vessel": INFERNAL_VESSEL,
    "Infestation Sage": INFESTATION_SAGE,
    "Midnight Snack": MIDNIGHT_SNACK,
    "Nine-Lives Familiar": NINELIVES_FAMILIAR,
    "Revenge of the Rats": REVENGE_OF_THE_RATS,
    "Sanguine Syphoner": SANGUINE_SYPHONER,
    "Seeker's Folly": SEEKERS_FOLLY,
    "Soul-Shackled Zombie": SOULSHACKLED_ZOMBIE,
    "Stab": STAB,
    "Tinybones, Bauble Burglar": TINYBONES_BAUBLE_BURGLAR,
    "Tragic Banshee": TRAGIC_BANSHEE,
    "Vampire Gourmand": VAMPIRE_GOURMAND,
    "Vampire Soulcaller": VAMPIRE_SOULCALLER,
    "Vengeful Bloodwitch": VENGEFUL_BLOODWITCH,
    "Zul Ashur, Lich Lord": ZUL_ASHUR_LICH_LORD,
    "Battlesong Berserker": BATTLESONG_BERSERKER,
    "Boltwave": BOLTWAVE,
    "Bulk Up": BULK_UP,
    "Chandra, Flameshaper": CHANDRA_FLAMESHAPER,
    "Courageous Goblin": COURAGEOUS_GOBLIN,
    "Crackling Cyclops": CRACKLING_CYCLOPS,
    "Dragon Trainer": DRAGON_TRAINER,
    "Electroduplicate": ELECTRODUPLICATE,
    "Fiery Annihilation": FIERY_ANNIHILATION,
    "Goblin Boarders": GOBLIN_BOARDERS,
    "Goblin Negotiation": GOBLIN_NEGOTIATION,
    "Gorehorn Raider": GOREHORN_RAIDER,
    "Incinerating Blast": INCINERATING_BLAST,
    "Kellan, Planar Trailblazer": KELLAN_PLANAR_TRAILBLAZER,
    "Rite of the Dragoncaller": RITE_OF_THE_DRAGONCALLER,
    "Searslicer Goblin": SEARSLICER_GOBLIN,
    "Slumbering Cerberus": SLUMBERING_CERBERUS,
    "Sower of Chaos": SOWER_OF_CHAOS,
    "Strongbox Raider": STRONGBOX_RAIDER,
    "Twinflame Tyrant": TWINFLAME_TYRANT,
    "Ambush Wolf": AMBUSH_WOLF,
    "Apothecary Stomper": APOTHECARY_STOMPER,
    "Beast-Kin Ranger": BEASTKIN_RANGER,
    "Cackling Prowler": CACKLING_PROWLER,
    "Eager Trufflesnout": EAGER_TRUFFLESNOUT,
    "Elfsworn Giant": ELFSWORN_GIANT,
    "Elvish Regrower": ELVISH_REGROWER,
    "Felling Blow": FELLING_BLOW,
    "Loot, Exuberant Explorer": LOOT_EXUBERANT_EXPLORER,
    "Mossborn Hydra": MOSSBORN_HYDRA,
    "Needletooth Pack": NEEDLETOOTH_PACK,
    "Preposterous Proportions": PREPOSTEROUS_PROPORTIONS,
    "Quakestrider Ceratops": QUAKESTRIDER_CERATOPS,
    "Quilled Greatwurm": QUILLED_GREATWURM,
    "Spinner of Souls": SPINNER_OF_SOULS,
    "Sylvan Scavenging": SYLVAN_SCAVENGING,
    "Treetop Snarespinner": TREETOP_SNARESPINNER,
    "Alesha, Who Laughs at Fate": ALESHA_WHO_LAUGHS_AT_FATE,
    "Anthem of Champions": ANTHEM_OF_CHAMPIONS,
    "Ashroot Animist": ASHROOT_ANIMIST,
    "Dreadwing Scavenger": DREADWING_SCAVENGER,
    "Elenda, Saint of Dusk": ELENDA_SAINT_OF_DUSK,
    "Fiendish Panda": FIENDISH_PANDA,
    "Koma, World-Eater": KOMA_WORLDEATER,
    "Kykar, Zephyr Awakener": KYKAR_ZEPHYR_AWAKENER,
    "Niv-Mizzet, Visionary": NIVMIZZET_VISIONARY,
    "Perforating Artist": PERFORATING_ARTIST,
    "Wardens of the Cycle": WARDENS_OF_THE_CYCLE,
    "Zimone, Paradox Sculptor": ZIMONE_PARADOX_SCULPTOR,
    "Banner of Kinship": BANNER_OF_KINSHIP,
    "Fishing Pole": FISHING_POLE,
    "Leyline Axe": LEYLINE_AXE,
    "Quick-Draw Katana": QUICKDRAW_KATANA,
    "Ravenous Amulet": RAVENOUS_AMULET,
    "Scrawling Crawler": SCRAWLING_CRAWLER,
    "Soulstone Sanctuary": SOULSTONE_SANCTUARY,
    "Ajani, Caller of the Pride": AJANI_CALLER_OF_THE_PRIDE,
    "Ajani's Pridemate": AJANIS_PRIDEMATE,
    "Angel of Finality": ANGEL_OF_FINALITY,
    "Authority of the Consuls": AUTHORITY_OF_THE_CONSULS,
    "Banishing Light": BANISHING_LIGHT,
    "Cathar Commando": CATHAR_COMMANDO,
    "Day of Judgment": DAY_OF_JUDGMENT,
    "Giada, Font of Hope": GIADA_FONT_OF_HOPE,
    "Healer's Hawk": HEALERS_HAWK,
    "Make Your Move": MAKE_YOUR_MOVE,
    "Mischievous Pup": MISCHIEVOUS_PUP,
    "Resolute Reinforcements": RESOLUTE_REINFORCEMENTS,
    "Savannah Lions": SAVANNAH_LIONS,
    "Serra Angel": SERRA_ANGEL,
    "Stroke of Midnight": STROKE_OF_MIDNIGHT,
    "Youthful Valkyrie": YOUTHFUL_VALKYRIE,
    "Aegis Turtle": AEGIS_TURTLE,
    "Aetherize": AETHERIZE,
    "Brineborn Cutthroat": BRINEBORN_CUTTHROAT,
    "Essence Scatter": ESSENCE_SCATTER,
    "Extravagant Replication": EXTRAVAGANT_REPLICATION,
    "Fleeting Distraction": FLEETING_DISTRACTION,
    "Imprisoned in the Moon": IMPRISONED_IN_THE_MOON,
    "Lightshell Duo": LIGHTSHELL_DUO,
    "Micromancer": MICROMANCER,
    "Mocking Sprite": MOCKING_SPRITE,
    "An Offer You Can't Refuse": AN_OFFER_YOU_CANT_REFUSE,
    "Omniscience": OMNISCIENCE,
    "Run Away Together": RUN_AWAY_TOGETHER,
    "Self-Reflection": SELFREFLECTION,
    "Spectral Sailor": SPECTRAL_SAILOR,
    "Think Twice": THINK_TWICE,
    "Time Stop": TIME_STOP,
    "Tolarian Terror": TOLARIAN_TERROR,
    "Witness Protection": WITNESS_PROTECTION,
    "Bake into a Pie": BAKE_INTO_A_PIE,
    "Burglar Rat": BURGLAR_RAT,
    "Diregraf Ghoul": DIREGRAF_GHOUL,
    "Eaten Alive": EATEN_ALIVE,
    "Exsanguinate": EXSANGUINATE,
    "Fake Your Own Death": FAKE_YOUR_OWN_DEATH,
    "Hero's Downfall": HEROS_DOWNFALL,
    "Liliana, Dreadhorde General": LILIANA_DREADHORDE_GENERAL,
    "Macabre Waltz": MACABRE_WALTZ,
    "Marauding Blight-Priest": MARAUDING_BLIGHTPRIEST,
    "Painful Quandary": PAINFUL_QUANDARY,
    "Phyrexian Arena": PHYREXIAN_ARENA,
    "Pilfer": PILFER,
    "Reassembling Skeleton": REASSEMBLING_SKELETON,
    "Rise of the Dark Realms": RISE_OF_THE_DARK_REALMS,
    "Rune-Scarred Demon": RUNESCARRED_DEMON,
    "Stromkirk Bloodthief": STROMKIRK_BLOODTHIEF,
    "Vampire Nighthawk": VAMPIRE_NIGHTHAWK,
    "Zombify": ZOMBIFY,
    "Abrade": ABRADE,
    "Axgard Cavalry": AXGARD_CAVALRY,
    "Brass's Bounty": BRASSS_BOUNTY,
    "Brazen Scourge": BRAZEN_SCOURGE,
    "Burst Lightning": BURST_LIGHTNING,
    "Drakuseth, Maw of Flames": DRAKUSETH_MAW_OF_FLAMES,
    "Etali, Primal Storm": ETALI_PRIMAL_STORM,
    "Fanatical Firebrand": FANATICAL_FIREBRAND,
    "Firebrand Archer": FIREBRAND_ARCHER,
    "Firespitter Whelp": FIRESPITTER_WHELP,
    "Flamewake Phoenix": FLAMEWAKE_PHOENIX,
    "Frenzied Goblin": FRENZIED_GOBLIN,
    "Goblin Surprise": GOBLIN_SURPRISE,
    "Heartfire Immolator": HEARTFIRE_IMMOLATOR,
    "Hidetsugu's Second Rite": HIDETSUGUS_SECOND_RITE,
    "Involuntary Employment": INVOLUNTARY_EMPLOYMENT,
    "Krenko, Mob Boss": KRENKO_MOB_BOSS,
    "Seismic Rupture": SEISMIC_RUPTURE,
    "Shivan Dragon": SHIVAN_DRAGON,
    "Slagstorm": SLAGSTORM,
    "Spitfire Lagac": SPITFIRE_LAGAC,
    "Sure Strike": SURE_STRIKE,
    "Thrill of Possibility": THRILL_OF_POSSIBILITY,
    "Affectionate Indrik": AFFECTIONATE_INDRIK,
    "Bite Down": BITE_DOWN,
    "Blanchwood Armor": BLANCHWOOD_ARMOR,
    "Broken Wings": BROKEN_WINGS,
    "Bushwhack": BUSHWHACK,
    "Doubling Season": DOUBLING_SEASON,
    "Dwynen, Gilt-Leaf Daen": DWYNEN_GILTLEAF_DAEN,
    "Dwynen's Elite": DWYNENS_ELITE,
    "Elvish Archdruid": ELVISH_ARCHDRUID,
    "Garruk's Uprising": GARRUKS_UPRISING,
    "Genesis Wave": GENESIS_WAVE,
    "Ghalta, Primal Hunger": GHALTA_PRIMAL_HUNGER,
    "Giant Growth": GIANT_GROWTH,
    "Gnarlid Colony": GNARLID_COLONY,
    "Grow from the Ashes": GROW_FROM_THE_ASHES,
    "Inspiring Call": INSPIRING_CALL,
    "Llanowar Elves": LLANOWAR_ELVES,
    "Mild-Mannered Librarian": MILDMANNERED_LIBRARIAN,
    "Nessian Hornbeetle": NESSIAN_HORNBEETLE,
    "Overrun": OVERRUN,
    "Reclamation Sage": RECLAMATION_SAGE,
    "Scavenging Ooze": SCAVENGING_OOZE,
    "Snakeskin Veil": SNAKESKIN_VEIL,
    "Vivien Reid": VIVIEN_REID,
    "Wary Thespian": WARY_THESPIAN,
    "Wildwood Scourge": WILDWOOD_SCOURGE,
    "Balmor, Battlemage Captain": BALMOR_BATTLEMAGE_CAPTAIN,
    "Consuming Aberration": CONSUMING_ABERRATION,
    "Empyrean Eagle": EMPYREAN_EAGLE,
    "Good-Fortune Unicorn": GOODFORTUNE_UNICORN,
    "Heroic Reinforcements": HEROIC_REINFORCEMENTS,
    "Lathril, Blade of the Elves": LATHRIL_BLADE_OF_THE_ELVES,
    "Muldrotha, the Gravetide": MULDROTHA_THE_GRAVETIDE,
    "Progenitus": PROGENITUS,
    "Ruby, Daring Tracker": RUBY_DARING_TRACKER,
    "Swiftblade Vindicator": SWIFTBLADE_VINDICATOR,
    "Tatyova, Benthic Druid": TATYOVA_BENTHIC_DRUID,
    "Thousand-Year Storm": THOUSANDYEAR_STORM,
    "Adventuring Gear": ADVENTURING_GEAR,
    "Burnished Hart": BURNISHED_HART,
    "Campus Guide": CAMPUS_GUIDE,
    "Gleaming Barrier": GLEAMING_BARRIER,
    "Goldvein Pick": GOLDVEIN_PICK,
    "Heraldic Banner": HERALDIC_BANNER,
    "Juggernaut": JUGGERNAUT,
    "Meteor Golem": METEOR_GOLEM,
    "Solemn Simulacrum": SOLEMN_SIMULACRUM,
    "Swiftfoot Boots": SWIFTFOOT_BOOTS,
    "Bloodfell Caves": BLOODFELL_CAVES,
    "Blossoming Sands": BLOSSOMING_SANDS,
    "Dismal Backwater": DISMAL_BACKWATER,
    "Evolving Wilds": EVOLVING_WILDS,
    "Jungle Hollow": JUNGLE_HOLLOW,
    "Rogue's Passage": ROGUES_PASSAGE,
    "Rugged Highlands": RUGGED_HIGHLANDS,
    "Scoured Barrens": SCOURED_BARRENS,
    "Secluded Courtyard": SECLUDED_COURTYARD,
    "Swiftwater Cliffs": SWIFTWATER_CLIFFS,
    "Thornwood Falls": THORNWOOD_FALLS,
    "Tranquil Cove": TRANQUIL_COVE,
    "Wind-Scarred Crag": WINDSCARRED_CRAG,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
    "Adamant Will": ADAMANT_WILL,
    "Ancestor Dragon": ANCESTOR_DRAGON,
    "Angelic Edict": ANGELIC_EDICT,
    "Bishop's Soldier": BISHOPS_SOLDIER,
    "Deadly Riposte": DEADLY_RIPOSTE,
    "Elspeth's Smite": ELSPETHS_SMITE,
    "Herald of Faith": HERALD_OF_FAITH,
    "Ingenious Leonin": INGENIOUS_LEONIN,
    "Inspiring Overseer": INSPIRING_OVERSEER,
    "Jazal Goldmane": JAZAL_GOLDMANE,
    "Leonin Skyhunter": LEONIN_SKYHUNTER,
    "Leonin Vanguard": LEONIN_VANGUARD,
    "Moment of Triumph": MOMENT_OF_TRIUMPH,
    "Pacifism": PACIFISM,
    "Prayer of Binding": PRAYER_OF_BINDING,
    "Twinblade Paladin": TWINBLADE_PALADIN,
    "Burrog Befuddler": BURROG_BEFUDDLER,
    "Cancel": CANCEL,
    "Corsair Captain": CORSAIR_CAPTAIN,
    "Eaten by Piranhas": EATEN_BY_PIRANHAS,
    "Exclusion Mage": EXCLUSION_MAGE,
    "Into the Roil": INTO_THE_ROIL,
    "Kitesail Corsair": KITESAIL_CORSAIR,
    "Mystic Archaeologist": MYSTIC_ARCHAEOLOGIST,
    "Opt": OPT,
    "Quick Study": QUICK_STUDY,
    "Starlight Snare": STARLIGHT_SNARE,
    "Storm Fleet Spy": STORM_FLEET_SPY,
    "Bloodtithe Collector": BLOODTITHE_COLLECTOR,
    "Cemetery Recruitment": CEMETERY_RECRUITMENT,
    "Crossway Troublemakers": CROSSWAY_TROUBLEMAKERS,
    "Crow of Dark Tidings": CROW_OF_DARK_TIDINGS,
    "Deadly Plot": DEADLY_PLOT,
    "Death Baron": DEATH_BARON,
    "Highborn Vampire": HIGHBORN_VAMPIRE,
    "Maalfeld Twins": MAALFELD_TWINS,
    "Moment of Craving": MOMENT_OF_CRAVING,
    "Offer Immortality": OFFER_IMMORTALITY,
    "Skeleton Archer": SKELETON_ARCHER,
    "Suspicious Shambler": SUSPICIOUS_SHAMBLER,
    "Undying Malice": UNDYING_MALICE,
    "Untamed Hunger": UNTAMED_HUNGER,
    "Vampire Interloper": VAMPIRE_INTERLOPER,
    "Vampire Neonate": VAMPIRE_NEONATE,
    "Vampire Spawn": VAMPIRE_SPAWN,
    "Battle-Rattle Shaman": BATTLERATTLE_SHAMAN,
    "Carnelian Orb of Dragonkind": CARNELIAN_ORB_OF_DRAGONKIND,
    "Dragon Fodder": DRAGON_FODDER,
    "Dragonlord's Servant": DRAGONLORDS_SERVANT,
    "Dropkick Bomber": DROPKICK_BOMBER,
    "Fire Elemental": FIRE_ELEMENTAL,
    "Goblin Oriflamme": GOBLIN_ORIFLAMME,
    "Goblin Smuggler": GOBLIN_SMUGGLER,
    "Kargan Dragonrider": KARGAN_DRAGONRIDER,
    "Kindled Fury": KINDLED_FURY,
    "Raging Redcap": RAGING_REDCAP,
    "Rapacious Dragon": RAPACIOUS_DRAGON,
    "Scorching Dragonfire": SCORCHING_DRAGONFIRE,
    "Seize the Spoils": SEIZE_THE_SPOILS,
    "Skyraker Giant": SKYRAKER_GIANT,
    "Swab Goblin": SWAB_GOBLIN,
    "Terror of Mount Velus": TERROR_OF_MOUNT_VELUS,
    "Volley Veteran": VOLLEY_VETERAN,
    "Aggressive Mammoth": AGGRESSIVE_MAMMOTH,
    "Bear Cub": BEAR_CUB,
    "Biogenic Upgrade": BIOGENIC_UPGRADE,
    "Druid of the Cowl": DRUID_OF_THE_COWL,
    "Joraga Invocation": JORAGA_INVOCATION,
    "Magnigoth Sentry": MAGNIGOTH_SENTRY,
    "New Horizons": NEW_HORIZONS,
    "Tajuru Pathwarden": TAJURU_PATHWARDEN,
    "Thornweald Archer": THORNWEALD_ARCHER,
    "Thrashing Brontodon": THRASHING_BRONTODON,
    "Wildheart Invoker": WILDHEART_INVOKER,
    "Goblin Firebomb": GOBLIN_FIREBOMB,
    "Pirate's Cutlass": PIRATES_CUTLASS,
    "Uncharted Haven": UNCHARTED_HAVEN,
    "Angelic Destiny": ANGELIC_DESTINY,
    "Archway Angel": ARCHWAY_ANGEL,
    "Ballyrush Banneret": BALLYRUSH_BANNERET,
    "Charming Prince": CHARMING_PRINCE,
    "Crusader of Odric": CRUSADER_OF_ODRIC,
    "Dawnwing Marshal": DAWNWING_MARSHAL,
    "Devout Decree": DEVOUT_DECREE,
    "Disenchant": DISENCHANT,
    "Felidar Cub": FELIDAR_CUB,
    "Felidar Retreat": FELIDAR_RETREAT,
    "Fumigate": FUMIGATE,
    "Knight of Grace": KNIGHT_OF_GRACE,
    "Linden, the Steadfast Queen": LINDEN_THE_STEADFAST_QUEEN,
    "Mentor of the Meek": MENTOR_OF_THE_MEEK,
    "Regal Caracal": REGAL_CARACAL,
    "Release the Dogs": RELEASE_THE_DOGS,
    "Stasis Snare": STASIS_SNARE,
    "Syr Alin, the Lion's Claw": SYR_ALIN_THE_LIONS_CLAW,
    "Valorous Stance": VALOROUS_STANCE,
    "Zetalpa, Primal Dawn": ZETALPA_PRIMAL_DAWN,
    "Arcanis the Omnipotent": ARCANIS_THE_OMNIPOTENT,
    "Chart a Course": CHART_A_COURSE,
    "Dictate of Kruphix": DICTATE_OF_KRUPHIX,
    "Dive Down": DIVE_DOWN,
    "Finale of Revelation": FINALE_OF_REVELATION,
    "Flashfreeze": FLASHFREEZE,
    "Fog Bank": FOG_BANK,
    "Gateway Sneak": GATEWAY_SNEAK,
    "Harbinger of the Tides": HARBINGER_OF_THE_TIDES,
    "Mystical Teachings": MYSTICAL_TEACHINGS,
    "River's Rebuke": RIVERS_REBUKE,
    "Shipwreck Dowser": SHIPWRECK_DOWSER,
    "Sphinx of the Final Word": SPHINX_OF_THE_FINAL_WORD,
    "Tempest Djinn": TEMPEST_DJINN,
    "Unsummon": UNSUMMON,
    "Voracious Greatshark": VORACIOUS_GREATSHARK,
    "Deathmark": DEATHMARK,
    "Demonic Pact": DEMONIC_PACT,
    "Desecration Demon": DESECRATION_DEMON,
    "Dread Summons": DREAD_SUMMONS,
    "Driver of the Dead": DRIVER_OF_THE_DEAD,
    "Duress": DURESS,
    "Kalastria Highborn": KALASTRIA_HIGHBORN,
    "Knight of Malice": KNIGHT_OF_MALICE,
    "Midnight Reaper": MIDNIGHT_REAPER,
    "Myojin of Night's Reach": MYOJIN_OF_NIGHTS_REACH,
    "Nullpriest of Oblivion": NULLPRIEST_OF_OBLIVION,
    "Pulse Tracker": PULSE_TRACKER,
    "Sanguine Indulgence": SANGUINE_INDULGENCE,
    "Tribute to Hunger": TRIBUTE_TO_HUNGER,
    "Vampiric Rites": VAMPIRIC_RITES,
    "Vile Entomber": VILE_ENTOMBER,
    "Wishclaw Talisman": WISHCLAW_TALISMAN,
    "Ball Lightning": BALL_LIGHTNING,
    "Bolt Bend": BOLT_BEND,
    "Crash Through": CRASH_THROUGH,
    "Dragon Mage": DRAGON_MAGE,
    "Dragonmaster Outcast": DRAGONMASTER_OUTCAST,
    "Ghitu Lavarunner": GHITU_LAVARUNNER,
    "Giant Cindermaw": GIANT_CINDERMAW,
    "Harmless Offering": HARMLESS_OFFERING,
    "Hoarding Dragon": HOARDING_DRAGON,
    "Lathliss, Dragon Queen": LATHLISS_DRAGON_QUEEN,
    "Mindsparker": MINDSPARKER,
    "Obliterating Bolt": OBLITERATING_BOLT,
    "Ravenous Giant": RAVENOUS_GIANT,
    "Redcap Gutter-Dweller": REDCAP_GUTTERDWELLER,
    "Stromkirk Noble": STROMKIRK_NOBLE,
    "Taurean Mauler": TAUREAN_MAULER,
    "Viashino Pyromancer": VIASHINO_PYROMANCER,
    "Circuitous Route": CIRCUITOUS_ROUTE,
    "Fierce Empath": FIERCE_EMPATH,
    "Fynn, the Fangbearer": FYNN_THE_FANGBEARER,
    "Gnarlback Rhino": GNARLBACK_RHINO,
    "Heroes' Bane": HEROES_BANE,
    "Mold Adder": MOLD_ADDER,
    "Ordeal of Nylea": ORDEAL_OF_NYLEA,
    "Predator Ooze": PREDATOR_OOZE,
    "Primal Might": PRIMAL_MIGHT,
    "Primeval Bounty": PRIMEVAL_BOUNTY,
    "Rampaging Baloths": RAMPAGING_BALOTHS,
    "Springbloom Druid": SPRINGBLOOM_DRUID,
    "Surrak, the Hunt Caller": SURRAK_THE_HUNT_CALLER,
    "Venom Connoisseur": VENOM_CONNOISSEUR,
    "Vizier of the Menagerie": VIZIER_OF_THE_MENAGERIE,
    "Wildborn Preserver": WILDBORN_PRESERVER,
    "Aurelia, the Warleader": AURELIA_THE_WARLEADER,
    "Ayli, Eternal Pilgrim": AYLI_ETERNAL_PILGRIM,
    "Cloudblazer": CLOUDBLAZER,
    "Deadly Brew": DEADLY_BREW,
    "Drogskol Reaver": DROGSKOL_REAVER,
    "Dryad Militant": DRYAD_MILITANT,
    "Enigma Drake": ENIGMA_DRAKE,
    "Garna, Bloodfist of Keld": GARNA_BLOODFIST_OF_KELD,
    "Halana and Alena, Partners": HALANA_AND_ALENA_PARTNERS,
    "Immersturm Predator": IMMERSTURM_PREDATOR,
    "Maelstrom Pulse": MAELSTROM_PULSE,
    "Mortify": MORTIFY,
    "Ovika, Enigma Goliath": OVIKA_ENIGMA_GOLIATH,
    "Prime Speaker Zegana": PRIME_SPEAKER_ZEGANA,
    "Savage Ventmaw": SAVAGE_VENTMAW,
    "Teach by Example": TEACH_BY_EXAMPLE,
    "Trygon Predator": TRYGON_PREDATOR,
    "Wilt-Leaf Liege": WILTLEAF_LIEGE,
    "Basilisk Collar": BASILISK_COLLAR,
    "Cultivator's Caravan": CULTIVATORS_CARAVAN,
    "Darksteel Colossus": DARKSTEEL_COLOSSUS,
    "Diamond Mare": DIAMOND_MARE,
    "Feldon's Cane": FELDONS_CANE,
    "Fireshrieker": FIRESHRIEKER,
    "Gate Colossus": GATE_COLOSSUS,
    "Mazemind Tome": MAZEMIND_TOME,
    "Pyromancer's Goggles": PYROMANCERS_GOGGLES,
    "Ramos, Dragon Engine": RAMOS_DRAGON_ENGINE,
    "Sorcerous Spyglass": SORCEROUS_SPYGLASS,
    "Soul-Guide Lantern": SOULGUIDE_LANTERN,
    "Steel Hellkite": STEEL_HELLKITE,
    "Three Tree Mascot": THREE_TREE_MASCOT,
    "Azorius Guildgate": AZORIUS_GUILDGATE,
    "Boros Guildgate": BOROS_GUILDGATE,
    "Crawling Barrens": CRAWLING_BARRENS,
    "Cryptic Caves": CRYPTIC_CAVES,
    "Demolition Field": DEMOLITION_FIELD,
    "Dimir Guildgate": DIMIR_GUILDGATE,
    "Golgari Guildgate": GOLGARI_GUILDGATE,
    "Gruul Guildgate": GRUUL_GUILDGATE,
    "Izzet Guildgate": IZZET_GUILDGATE,
    "Orzhov Guildgate": ORZHOV_GUILDGATE,
    "Rakdos Guildgate": RAKDOS_GUILDGATE,
    "Selesnya Guildgate": SELESNYA_GUILDGATE,
    "Simic Guildgate": SIMIC_GUILDGATE,
    "Temple of Abandon": TEMPLE_OF_ABANDON,
    "Temple of Deceit": TEMPLE_OF_DECEIT,
    "Temple of Enlightenment": TEMPLE_OF_ENLIGHTENMENT,
    "Temple of Epiphany": TEMPLE_OF_EPIPHANY,
    "Temple of Malady": TEMPLE_OF_MALADY,
    "Temple of Malice": TEMPLE_OF_MALICE,
    "Temple of Mystery": TEMPLE_OF_MYSTERY,
    "Temple of Plenty": TEMPLE_OF_PLENTY,
    "Temple of Silence": TEMPLE_OF_SILENCE,
    "Temple of Triumph": TEMPLE_OF_TRIUMPH,
    "Angel of Vitality": ANGEL_OF_VITALITY,
    "Lyra Dawnbringer": LYRA_DAWNBRINGER,
    "Make a Stand": MAKE_A_STAND,
    "Confiscate": CONFISCATE,
    "Negate": NEGATE,
    "Rite of Replication": RITE_OF_REPLICATION,
    "Feed the Swarm": FEED_THE_SWARM,
    "Gatekeeper of Malakir": GATEKEEPER_OF_MALAKIR,
    "Massacre Wurm": MASSACRE_WURM,
    "Gratuitous Violence": GRATUITOUS_VIOLENCE,
    "Guttersnipe": GUTTERSNIPE,
    "Impact Tremors": IMPACT_TREMORS,
    "Gigantosaurus": GIGANTOSAURUS,
    "Imperious Perfect": IMPERIOUS_PERFECT,
    "Pelakka Wurm": PELAKKA_WURM,
    "Boros Charm": BOROS_CHARM,
    "Unflinching Courage": UNFLINCHING_COURAGE,
    "Adaptive Automaton": ADAPTIVE_AUTOMATON,
    "Expedition Map": EXPEDITION_MAP,
    "Gilded Lotus": GILDED_LOTUS,
    "Hedron Archive": HEDRON_ARCHIVE,
    "Maze's End": MAZES_END,
    "Hinterland Sanctifier": HINTERLAND_SANCTIFIER,
}

print(f"Loaded {len(FOUNDATIONS_CARDS)} Foundations cards")
