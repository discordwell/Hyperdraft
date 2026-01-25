"""
Avatar_The_Last_Airbender (TLA) Card Implementations

Real card data fetched from Scryfall API.
286 cards in set.
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

AANGS_JOURNEY = make_sorcery(
    name="Aang's Journey",
    mana_cost="{2}",
    colors=set(),
    text="Kicker {2} (You may pay an additional {2} as you cast this spell.)\nSearch your library for a basic land card. If this spell was kicked, instead search your library for a basic land card and a Shrine card. Reveal those cards, put them into your hand, then shuffle.\nYou gain 2 life.",
    subtypes={"Lesson"},
)

ENERGYBENDING = make_instant(
    name="Energybending",
    mana_cost="{2}",
    colors=set(),
    text="Lands you control gain all basic land types until end of turn.\nDraw a card.",
    subtypes={"Lesson"},
)

ZUKOS_EXILE = make_instant(
    name="Zuko's Exile",
    mana_cost="{5}",
    colors=set(),
    text="Exile target artifact, creature, or enchantment. Its controller creates a Clue token. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    subtypes={"Lesson"},
)

AANG_THE_LAST_AIRBENDER = make_creature(
    name="Aang, the Last Airbender",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Ally", "Avatar", "Human"},
    supertypes={"Legendary"},
    text="Flying\nWhen Aang enters, airbend up to one other target nonland permanent. (Exile it. While it's exiled, its owner may cast it for {2} rather than its mana cost.)\nWhenever you cast a Lesson spell, Aang gains lifelink until end of turn.",
)

AANGS_ICEBERG = make_enchantment(
    name="Aang's Iceberg",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Flash\nWhen this enchantment enters, exile up to one other target nonland permanent until this enchantment leaves the battlefield.\nWaterbend {3}: Sacrifice this enchantment. If you do, scry 2. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)",
)

AIRBENDER_ASCENSION = make_enchantment(
    name="Airbender Ascension",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, airbend up to one target creature.\nWhenever a creature you control enters, put a quest counter on this enchantment.\nAt the beginning of your end step, if this enchantment has four or more quest counters on it, exile up to one target creature you control, then return it to the battlefield under its owner's control.",
)

AIRBENDERS_REVERSAL = make_instant(
    name="Airbender's Reversal",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Destroy target attacking creature.\n• Airbend target creature you control. (Exile it. While it's exiled, its owner may cast it for {2} rather than its mana cost.)",
    subtypes={"Lesson"},
)

AIRBENDING_LESSON = make_instant(
    name="Airbending Lesson",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Airbend target nonland permanent. (Exile it. While it's exiled, its owner may cast it for {2} rather than its mana cost.)\nDraw a card.",
    subtypes={"Lesson"},
)

APPA_LOYAL_SKY_BISON = make_creature(
    name="Appa, Loyal Sky Bison",
    power=4, toughness=4,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Ally", "Bison"},
    supertypes={"Legendary"},
    text="Flying\nWhenever Appa enters or attacks, choose one —\n• Target creature you control gains flying until end of turn.\n• Airbend another target nonland permanent you control. (Exile it. While it's exiled, its owner may cast it for {2} rather than its mana cost.)",
)

APPA_STEADFAST_GUARDIAN = make_creature(
    name="Appa, Steadfast Guardian",
    power=3, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Ally", "Bison"},
    supertypes={"Legendary"},
    text="Flash\nFlying\nWhen Appa enters, airbend any number of other target nonland permanents you control. (Exile them. While each one is exiled, its owner may cast it for {2} rather than its mana cost.)\nWhenever you cast a spell from exile, create a 1/1 white Ally creature token.",
)

AVATAR_ENTHUSIASTS = make_creature(
    name="Avatar Enthusiasts",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Ally", "Human", "Peasant"},
    text="Whenever another Ally you control enters, put a +1/+1 counter on this creature.",
)

AVATARS_WRATH = make_sorcery(
    name="Avatar's Wrath",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Choose up to one target creature, then airbend all other creatures. (Exile them. While each one is exiled, its owner may cast it for {2} rather than its mana cost.)\nUntil your next turn, your opponents can't cast spells from anywhere other than their hands.\nExile Avatar's Wrath.",
)

COMPASSIONATE_HEALER = make_creature(
    name="Compassionate Healer",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Ally", "Cleric", "Human"},
    text="Whenever this creature becomes tapped, you gain 1 life and scry 1. (Look at the top card of your library. You may put it on the bottom.)",
)

CURIOUS_FARM_ANIMALS = make_creature(
    name="Curious Farm Animals",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Bird", "Boar", "Elk", "Ox"},
    text="When this creature dies, you gain 3 life.\n{2}, Sacrifice this creature: Destroy up to one target artifact or enchantment.",
)

DESTINED_CONFRONTATION = make_sorcery(
    name="Destined Confrontation",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Each player chooses any number of creatures they control with total power 4 or less, then sacrifices all other creatures they control.",
)

EARTH_KINGDOM_JAILER = make_creature(
    name="Earth Kingdom Jailer",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Ally", "Human", "Soldier"},
    text="When this creature enters, exile up to one target artifact, creature, or enchantment an opponent controls with mana value 3 or greater until this creature leaves the battlefield.",
)

EARTH_KINGDOM_PROTECTORS = make_creature(
    name="Earth Kingdom Protectors",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Ally", "Human", "Soldier"},
    text="Vigilance\nSacrifice this creature: Another target Ally you control gains indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)",
)

ENTER_THE_AVATAR_STATE = make_instant(
    name="Enter the Avatar State",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Until end of turn, target creature you control becomes an Avatar in addition to its other types and gains flying, first strike, lifelink, and hexproof. (A creature with hexproof can't be the target of spells or abilities your opponents control.)",
    subtypes={"Lesson"},
)

FANCY_FOOTWORK = make_instant(
    name="Fancy Footwork",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Untap one or two target creatures. They each get +2/+2 until end of turn.",
    subtypes={"Lesson"},
)

GATHER_THE_WHITE_LOTUS = make_sorcery(
    name="Gather the White Lotus",
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    text="Create a 1/1 white Ally creature token for each Plains you control. Scry 2. (Look at the top two cards of your library, then put any number of them on the bottom and the rest on top in any order.)",
)

GLIDER_KIDS = make_creature(
    name="Glider Kids",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Ally", "Human", "Pilot"},
    text="Flying\nWhen this creature enters, scry 1. (Look at the top card of your library. You may put it on the bottom.)",
)

GLIDER_STAFF = make_artifact(
    name="Glider Staff",
    mana_cost="{2}{W}",
    text="When this Equipment enters, airbend up to one target creature. (Exile it. While it's exiled, its owner may cast it for {2} rather than its mana cost.)\nEquipped creature gets +1/+1 and has flying.\nEquip {2}",
    subtypes={"Equipment"},
)

HAKODA_SELFLESS_COMMANDER = make_creature(
    name="Hakoda, Selfless Commander",
    power=3, toughness=5,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Ally", "Human", "Warrior"},
    supertypes={"Legendary"},
    text="Vigilance\nYou may look at the top card of your library any time.\nYou may cast Ally spells from the top of your library.\nSacrifice Hakoda: Creatures you control get +0/+5 and gain indestructible until end of turn.",
)

INVASION_REINFORCEMENTS = make_creature(
    name="Invasion Reinforcements",
    power=1, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Ally", "Human", "Warrior"},
    text="Flash\nWhen this creature enters, create a 1/1 white Ally creature token.",
)

JEONG_JEONGS_DESERTERS = make_creature(
    name="Jeong Jeong's Deserters",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Ally", "Human", "Rebel"},
    text="When this creature enters, put a +1/+1 counter on target creature.",
)

KYOSHI_WARRIORS = make_creature(
    name="Kyoshi Warriors",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Ally", "Human", "Warrior"},
    text="When this creature enters, create a 1/1 white Ally creature token.",
)

THE_LEGEND_OF_YANGCHEN = make_creature(
    name="The Legend of Yangchen",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Legendary", "Saga"},
    text="",
)

MASTER_PIANDAO = make_creature(
    name="Master Piandao",
    power=4, toughness=4,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Ally", "Human", "Warrior"},
    supertypes={"Legendary"},
    text="First strike\nWhenever Master Piandao attacks, look at the top four cards of your library. You may reveal an Ally, Equipment, or Lesson card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
)

MOMO_FRIENDLY_FLIER = make_creature(
    name="Momo, Friendly Flier",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Ally", "Bat", "Lemur"},
    supertypes={"Legendary"},
    text="Flying\nThe first non-Lemur creature spell with flying you cast during each of your turns costs {1} less to cast.\nWhenever another creature you control with flying enters, Momo gets +1/+1 until end of turn.",
)

MOMO_PLAYFUL_PET = make_creature(
    name="Momo, Playful Pet",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Ally", "Bat", "Lemur"},
    supertypes={"Legendary"},
    text="Flying, vigilance\nWhen Momo leaves the battlefield, choose one —\n• Create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\n• Put a +1/+1 counter on target creature you control.\n• Scry 2.",
)

PATH_TO_REDEMPTION = make_enchantment(
    name="Path to Redemption",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Enchant creature\nEnchanted creature can't attack or block.\n{5}, Sacrifice this Aura: Exile enchanted creature. Create a 1/1 white Ally creature token. Activate only during your turn.",
    subtypes={"Aura"},
)

RABAROO_TROOP = make_creature(
    name="Rabaroo Troop",
    power=3, toughness=5,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Kangaroo", "Rabbit"},
    text="Landfall — Whenever a land you control enters, this creature gains flying until end of turn and you gain 1 life.\nPlainscycling {2} ({2}, Discard this card: Search your library for a Plains card, reveal it, put it into your hand, then shuffle.)",
)

RAZOR_RINGS = make_instant(
    name="Razor Rings",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Razor Rings deals 4 damage to target attacking or blocking creature. You gain life equal to the excess damage dealt this way.",
)

SANDBENDERS_STORM = make_instant(
    name="Sandbenders' Storm",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Choose one—\n• Destroy target creature with power 4 or greater.\n• Earthbend 3. (Target land you control becomes a 0/0 creature with haste that's still a land. Put three +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped.)",
)

SOUTH_POLE_VOYAGER = make_creature(
    name="South Pole Voyager",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Ally", "Human", "Scout"},
    text="Whenever this creature or another Ally you control enters, you gain 1 life. If this is the second time this ability has resolved this turn, draw a card.",
)

SOUTHERN_AIR_TEMPLE = make_enchantment(
    name="Southern Air Temple",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="When Southern Air Temple enters, put X +1/+1 counters on each creature you control, where X is the number of Shrines you control.\nWhenever another Shrine you control enters, put a +1/+1 counter on each creature you control.",
    subtypes={"Shrine"},
    supertypes={"Legendary"},
)

SUKI_COURAGEOUS_RESCUER = make_creature(
    name="Suki, Courageous Rescuer",
    power=2, toughness=4,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Ally", "Human", "Warrior"},
    supertypes={"Legendary"},
    text="Other creatures you control get +1/+0.\nWhenever another permanent you control leaves the battlefield during your turn, create a 1/1 white Ally creature token. This ability triggers only once each turn.",
)

TEAM_AVATAR = make_enchantment(
    name="Team Avatar",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Whenever a creature you control attacks alone, it gets +X/+X until end of turn, where X is the number of creatures you control.\n{2}{W}, Discard this card: It deals damage equal to the number of creatures you control to target creature.",
)

UNITED_FRONT = make_sorcery(
    name="United Front",
    mana_cost="{X}{W}{W}",
    colors={Color.WHITE},
    text="Create X 1/1 white Ally creature tokens, then put a +1/+1 counter on each creature you control.",
)

VENGEFUL_VILLAGERS = make_creature(
    name="Vengeful Villagers",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Citizen", "Human"},
    text="Whenever this creature attacks, choose target creature an opponent controls. Tap it, then you may sacrifice an artifact or creature. If you do, put a stun counter on the chosen creature. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

WATER_TRIBE_CAPTAIN = make_creature(
    name="Water Tribe Captain",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Ally", "Human", "Soldier"},
    text="{5}: Creatures you control get +1/+1 until end of turn.",
)

WATER_TRIBE_RALLIER = make_creature(
    name="Water Tribe Rallier",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Ally", "Human", "Soldier"},
    text="Waterbend {5}: Look at the top four cards of your library. You may reveal a creature card with power 3 or less from among them and put it into your hand. Put the rest on the bottom of your library in a random order. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)",
)

YIP_YIP = make_instant(
    name="Yip Yip!",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature you control gets +2/+2 until end of turn. If that creature is an Ally, it also gains flying until end of turn.",
    subtypes={"Lesson"},
)

ACCUMULATE_WISDOM = make_instant(
    name="Accumulate Wisdom",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Look at the top three cards of your library. Put one of those cards into your hand and the rest on the bottom of your library in any order. Put each of those cards into your hand instead if there are three or more Lesson cards in your graveyard.",
    subtypes={"Lesson"},
)

BENEVOLENT_RIVER_SPIRIT = make_creature(
    name="Benevolent River Spirit",
    power=4, toughness=5,
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="As an additional cost to cast this spell, waterbend {5}. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)\nFlying, ward {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nWhen this creature enters, scry 2.",
)

BOOMERANG_BASICS = make_sorcery(
    name="Boomerang Basics",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Return target nonland permanent to its owner's hand. If you controlled that permanent, draw a card.",
    subtypes={"Lesson"},
)

CRASHING_WAVE = make_sorcery(
    name="Crashing Wave",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="As an additional cost to cast this spell, waterbend {X}. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)\nTap up to X target creatures, then distribute three stun counters among any number of tapped creatures your opponents control. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

EMBER_ISLAND_PRODUCTION = make_sorcery(
    name="Ember Island Production",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Choose one—\n• Create a token that's a copy of target creature you control, except it's not legendary and it's a 4/4 Hero in addition to its other types.\n• Create a token that's a copy of target creature an opponent controls, except it's not legendary and it's a 2/2 Coward in addition to its other types.",
)

FIRSTTIME_FLYER = make_creature(
    name="First-Time Flyer",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Ally", "Human", "Pilot"},
    text="Flying\nThis creature gets +1/+1 as long as there's a Lesson card in your graveyard.",
)

FLEXIBLE_WATERBENDER = make_creature(
    name="Flexible Waterbender",
    power=2, toughness=5,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Ally", "Human", "Warrior"},
    text="Vigilance\nWaterbend {3}: This creature has base power and toughness 5/2 until end of turn. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)",
)

FORECASTING_FORTUNE_TELLER = make_creature(
    name="Forecasting Fortune Teller",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Advisor", "Ally", "Human"},
    text="When this creature enters, create a Clue token. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

GEYSER_LEAPER = make_creature(
    name="Geyser Leaper",
    power=4, toughness=3,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Ally", "Human", "Warrior"},
    text="Flying\nWaterbend {4}: Draw a card, then discard a card. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)",
)

GIANT_KOI = make_creature(
    name="Giant Koi",
    power=5, toughness=7,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Fish"},
    text="Waterbend {3}: This creature can't be blocked this turn. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)\nIslandcycling {2} ({2}, Discard this card: Search your library for an Island card, reveal it, put it into your hand, then shuffle.)",
)

GRANGRAN = make_creature(
    name="Gran-Gran",
    power=1, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Ally", "Human", "Peasant"},
    supertypes={"Legendary"},
    text="Whenever Gran-Gran becomes tapped, draw a card, then discard a card.\nNoncreature spells you cast cost {1} less to cast as long as there are three or more Lesson cards in your graveyard.",
)

HONEST_WORK = make_enchantment(
    name="Honest Work",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Enchant creature an opponent controls\nWhen this Aura enters, tap enchanted creature and remove all counters from it.\nEnchanted creature loses all abilities and is a Citizen with base power and toughness 1/1 and \"{T}: Add {C}\" named Humble Merchant. (It loses all other creature types and names.)",
    subtypes={"Aura"},
)

IGUANA_PARROT = make_creature(
    name="Iguana Parrot",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Lizard", "Pirate"},
    text="Flying, vigilance\nProwess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)",
)

INVASION_SUBMERSIBLE = make_artifact(
    name="Invasion Submersible",
    mana_cost="{2}{U}",
    text="When this Vehicle enters, return up to one other target nonland permanent to its owner's hand.\nExhaust — Waterbend {3}: This Vehicle becomes an artifact creature. Put three +1/+1 counters on it. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}. Activate each exhaust ability only once.)",
    subtypes={"Vehicle"},
)

ITLL_QUENCH_YA = make_instant(
    name="It'll Quench Ya!",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {2}.",
    subtypes={"Lesson"},
)

KATARA_BENDING_PRODIGY = make_creature(
    name="Katara, Bending Prodigy",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Ally", "Human", "Warrior"},
    supertypes={"Legendary"},
    text="At the beginning of your end step, if Katara is tapped, put a +1/+1 counter on her.\nWaterbend {6}: Draw a card. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)",
)

KNOWLEDGE_SEEKER = make_creature(
    name="Knowledge Seeker",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Fox", "Spirit"},
    text="Vigilance\nWhenever you draw your second card each turn, put a +1/+1 counter on this creature.\nWhen this creature dies, create a Clue token. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

THE_LEGEND_OF_KURUK = make_creature(
    name="The Legend of Kuruk",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Legendary", "Saga"},
    text="",
)

LOST_DAYS = make_instant(
    name="Lost Days",
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    text="The owner of target creature or enchantment puts it into their library second from the top or on the bottom. You create a Clue token. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    subtypes={"Lesson"},
)

MASTER_PAKKU = make_creature(
    name="Master Pakku",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Advisor", "Ally", "Human"},
    supertypes={"Legendary"},
    text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nWhenever Master Pakku becomes tapped, target player mills X cards, where X is the number of Lesson cards in your graveyard. (They put the top X cards of their library into their graveyard.)",
)

THE_MECHANIST_AERIAL_ARTISAN = make_creature(
    name="The Mechanist, Aerial Artisan",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Ally", "Artificer", "Human"},
    supertypes={"Legendary"},
    text="Whenever you cast a noncreature spell, create a Clue token. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\n{T}: Until end of turn, target artifact token you control becomes a 3/1 Construct artifact creature with flying.",
)

NORTH_POLE_PATROL = make_creature(
    name="North Pole Patrol",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Ally", "Human", "Soldier"},
    text="{T}: Untap another target permanent you control.\nWaterbend {3}, {T}: Tap target creature an opponent controls. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)",
)

OCTOPUS_FORM = make_instant(
    name="Octopus Form",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature you control gets +1/+1 and gains hexproof until end of turn. Untap it. (It can't be the target of spells or abilities your opponents control.)",
    subtypes={"Lesson"},
)

OTTERPENGUIN = make_creature(
    name="Otter-Penguin",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Otter"},
    text="Whenever you draw your second card each turn, this creature gets +1/+2 until end of turn and can't be blocked this turn.",
)

ROWDY_SNOWBALLERS = make_creature(
    name="Rowdy Snowballers",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Ally", "Human", "Peasant"},
    text="When this creature enters, tap target creature an opponent controls and put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

SECRET_OF_BLOODBENDING = make_sorcery(
    name="Secret of Bloodbending",
    mana_cost="{U}{U}{U}{U}",
    colors={Color.BLUE},
    text="As an additional cost to cast this spell, you may waterbend {10}.\nYou control target opponent during their next combat phase. If this spell's additional cost was paid, you control that player during their next turn instead. (You see all cards that player could see and make all decisions for them.)\nExile Secret of Bloodbending.",
    subtypes={"Lesson"},
)

SERPENT_OF_THE_PASS = make_creature(
    name="Serpent of the Pass",
    power=6, toughness=5,
    mana_cost="{5}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Serpent"},
    text="If there are three or more Lesson cards in your graveyard, you may cast this spell as though it had flash.\nThis spell costs {1} less to cast for each noncreature, nonland card in your graveyard.",
)

SOKKAS_HAIKU = make_instant(
    name="Sokka's Haiku",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell.\nDraw a card, then mill three cards.\nUntap target land.",
    subtypes={"Lesson"},
)

THE_SPIRIT_OASIS = make_enchantment(
    name="The Spirit Oasis",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="When The Spirit Oasis enters, draw a card for each Shrine you control.\nWhenever another Shrine you control enters, draw a card.",
    subtypes={"Shrine"},
    supertypes={"Legendary"},
)

SPIRIT_WATER_REVIVAL = make_sorcery(
    name="Spirit Water Revival",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="As an additional cost to cast this spell, you may waterbend {6}. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)\nDraw two cards. If this spell's additional cost was paid, instead shuffle your graveyard into your library, draw seven cards, and you have no maximum hand size for the rest of the game.\nExile Spirit Water Revival.",
)

TEO_SPIRITED_GLIDER = make_creature(
    name="Teo, Spirited Glider",
    power=1, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Ally", "Human", "Pilot"},
    supertypes={"Legendary"},
    text="Flying\nWhenever one or more creatures you control with flying attack, draw a card, then discard a card. When you discard a nonland card this way, put a +1/+1 counter on target creature you control.",
)

TIGERSEAL = make_creature(
    name="Tiger-Seal",
    power=3, toughness=3,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Cat", "Seal"},
    text="Vigilance\nAt the beginning of your upkeep, tap this creature.\nWhenever you draw your second card each turn, untap this creature.",
)

TY_LEE_CHI_BLOCKER = make_creature(
    name="Ty Lee, Chi Blocker",
    power=2, toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Ally", "Human", "Performer"},
    supertypes={"Legendary"},
    text="Flash\nProwess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nWhen Ty Lee enters, tap up to one target creature. It doesn't untap during its controller's untap step for as long as you control Ty Lee.",
)

THE_UNAGI_OF_KYOSHI_ISLAND = make_creature(
    name="The Unagi of Kyoshi Island",
    power=5, toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Serpent"},
    supertypes={"Legendary"},
    text="Flash\nWard—Waterbend {4}. (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {4}. They can tap their artifacts and creatures to help. Each one pays for {1}.)\nWhenever an opponent draws their second card each turn, you draw two cards.",
)

WAN_SHI_TONG_LIBRARIAN = make_creature(
    name="Wan Shi Tong, Librarian",
    power=1, toughness=1,
    mana_cost="{X}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Spirit"},
    supertypes={"Legendary"},
    text="Flash\nFlying, vigilance\nWhen Wan Shi Tong enters, put X +1/+1 counters on him. Then draw half X cards, rounded down.\nWhenever an opponent searches their library, put a +1/+1 counter on Wan Shi Tong and draw a card.",
)

WATERBENDER_ASCENSION = make_enchantment(
    name="Waterbender Ascension",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Whenever a creature you control deals combat damage to a player, put a quest counter on this enchantment. Then if it has four or more quest counters on it, draw a card.\nWaterbend {4}: Target creature can't be blocked this turn. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)",
)

WATERBENDING_LESSON = make_sorcery(
    name="Waterbending Lesson",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Draw three cards. Then discard a card unless you waterbend {2}. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)",
    subtypes={"Lesson"},
)

WATERBENDING_SCROLL = make_artifact(
    name="Waterbending Scroll",
    mana_cost="{1}{U}",
    text="{6}, {T}: Draw a card. This ability costs {1} less to activate for each Island you control.",
)

WATERY_GRASP = make_enchantment(
    name="Watery Grasp",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Enchant creature\nEnchanted creature doesn't untap during its controller's untap step.\nWaterbend {5}: Enchanted creature's owner shuffles it into their library. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)",
    subtypes={"Aura"},
)

YUE_THE_MOON_SPIRIT = make_creature(
    name="Yue, the Moon Spirit",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Ally", "Spirit"},
    supertypes={"Legendary"},
    text="Flying, vigilance\nWaterbend {5}, {T}: You may cast a noncreature spell from your hand without paying its mana cost. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)",
)

AZULA_ALWAYS_LIES = make_instant(
    name="Azula Always Lies",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Choose one or both —\n• Target creature gets -1/-1 until end of turn.\n• Put a +1/+1 counter on target creature.",
    subtypes={"Lesson"},
)

AZULA_ON_THE_HUNT = make_creature(
    name="Azula, On the Hunt",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Firebending 2 (Whenever this creature attacks, add {R}{R}. This mana lasts until end of combat.)\nWhenever Azula attacks, you lose 1 life and create a Clue token. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

BEETLEHEADED_MERCHANTS = make_creature(
    name="Beetle-Headed Merchants",
    power=5, toughness=4,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Citizen", "Human"},
    text="Whenever this creature attacks, you may sacrifice another creature or artifact. If you do, draw a card and put a +1/+1 counter on this creature.",
)

BOILING_ROCK_RIOTER = make_creature(
    name="Boiling Rock Rioter",
    power=3, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Ally", "Human", "Rogue"},
    text="Firebending 1 (Whenever this creature attacks, add {R}. This mana lasts until end of combat.)\nTap an untapped Ally you control: Exile target card from a graveyard.\nWhenever this creature attacks, you may cast an Ally spell from among cards you own exiled with this creature.",
)

BUZZARDWASP_COLONY = make_creature(
    name="Buzzard-Wasp Colony",
    power=2, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Bird", "Insect"},
    text="Flying\nWhen this creature enters, you may sacrifice an artifact or creature. If you do, draw a card.\nWhenever another creature you control dies, if it had counters on it, put its counters on this creature.",
)

CALLOUS_INSPECTOR = make_creature(
    name="Callous Inspector",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhen this creature dies, it deals 1 damage to you. Create a Clue token. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

CANYON_CRAWLER = make_creature(
    name="Canyon Crawler",
    power=6, toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Beast", "Spider"},
    text="Deathtouch\nWhen this creature enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\nSwampcycling {2} ({2}, Discard this card: Search your library for a Swamp card, reveal it, put it into your hand, then shuffle.)",
)

CATGATOR = make_creature(
    name="Cat-Gator",
    power=3, toughness=2,
    mana_cost="{6}{B}",
    colors={Color.BLACK},
    subtypes={"Crocodile", "Fish"},
    text="Lifelink\nWhen this creature enters, it deals damage equal to the number of Swamps you control to any target.",
)

CORRUPT_COURT_OFFICIAL = make_creature(
    name="Corrupt Court Official",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Advisor", "Human"},
    text="When this creature enters, target opponent discards a card.",
)

DAI_LI_INDOCTRINATION = make_sorcery(
    name="Dai Li Indoctrination",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Choose one —\n• Target opponent reveals their hand. You choose a nonland permanent card from it. That player discards that card.\n• Earthbend 2. (Target land you control becomes a 0/0 creature with haste that's still a land. Put two +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped.)",
    subtypes={"Lesson"},
)

DAY_OF_BLACK_SUN = make_sorcery(
    name="Day of Black Sun",
    mana_cost="{X}{B}{B}",
    colors={Color.BLACK},
    text="Each creature with mana value X or less loses all abilities until end of turn. Destroy those creatures.",
)

DEADLY_PRECISION = make_sorcery(
    name="Deadly Precision",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, pay {4} or sacrifice an artifact or creature.\nDestroy target creature.",
)

EPIC_DOWNFALL = make_sorcery(
    name="Epic Downfall",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Exile target creature with mana value 3 or greater.",
)

FATAL_FISSURE = make_instant(
    name="Fatal Fissure",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Choose target creature. When that creature dies this turn, you earthbend 4. (Target land you control becomes a 0/0 creature with haste that's still a land. Put four +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped.)",
)

THE_FIRE_NATION_DRILL = make_artifact(
    name="The Fire Nation Drill",
    mana_cost="{2}{B}{B}",
    text="Trample\nWhen The Fire Nation Drill enters, you may tap it. When you do, destroy target creature with power 4 or less.\n{1}: Permanents your opponents control lose hexproof and indestructible until end of turn.\nCrew 2",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
)

FIRE_NATION_ENGINEER = make_creature(
    name="Fire Nation Engineer",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Artificer", "Human"},
    text="Raid — At the beginning of your end step, if you attacked this turn, put a +1/+1 counter on another target creature or Vehicle you control.",
)

FIRE_NAVY_TREBUCHET = make_artifact_creature(
    name="Fire Navy Trebuchet",
    power=0, toughness=4,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Wall"},
    text="Defender, reach\nWhenever you attack, create a 2/1 colorless Construct artifact creature token with flying named Ballistic Boulder that's tapped and attacking. Sacrifice that token at the beginning of the next end step.",
)

FOGGY_SWAMP_HUNTERS = make_creature(
    name="Foggy Swamp Hunters",
    power=3, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Ally", "Human", "Ranger"},
    text="As long as you've drawn two or more cards this turn, this creature has lifelink and menace. (It can't be blocked except by two or more creatures.)",
)

FOGGY_SWAMP_VISIONS = make_sorcery(
    name="Foggy Swamp Visions",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, waterbend {X}. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)\nExile X target creature cards from graveyards. For each creature card exiled this way, create a token that's a copy of it. At the beginning of your next end step, sacrifice those tokens.",
)

HEARTLESS_ACT = make_instant(
    name="Heartless Act",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Choose one —\n• Destroy target creature with no counters on it.\n• Remove up to three counters from target creature.",
)

HOGMONKEY = make_creature(
    name="Hog-Monkey",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Boar", "Monkey"},
    text="At the beginning of combat on your turn, target creature you control with a +1/+1 counter on it gains menace until end of turn. (It can't be blocked except by two or more creatures.)\nExhaust — {5}: Put two +1/+1 counters on this creature. (Activate each exhaust ability only once.)",
)

JOO_DEE_ONE_OF_MANY = make_creature(
    name="Joo Dee, One of Many",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Advisor", "Human"},
    text="{B}, {T}: Surveil 1. Create a token that's a copy of this creature, then sacrifice an artifact or creature. Activate only as a sorcery. (To surveil 1, look at the top card of your library. You may put it into your graveyard.)",
)

JUNE_BOUNTY_HUNTER = make_creature(
    name="June, Bounty Hunter",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Mercenary"},
    supertypes={"Legendary"},
    text="June can't be blocked as long as you've drawn two or more cards this turn.\n{1}, Sacrifice another creature: Create a Clue token. Activate only during your turn. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

KOH_THE_FACE_STEALER = make_creature(
    name="Koh, the Face Stealer",
    power=6, toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Shapeshifter", "Spirit"},
    supertypes={"Legendary"},
    text="When Koh enters, exile up to one other target creature.\nWhenever another nontoken creature dies, you may exile it.\nPay 1 life: Choose a creature card exiled with Koh.\nKoh has all activated and triggered abilities of the last chosen card.",
)

LO_AND_LI_TWIN_TUTORS = make_creature(
    name="Lo and Li, Twin Tutors",
    power=2, toughness=2,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Advisor", "Human"},
    supertypes={"Legendary"},
    text="When Lo and Li enter, search your library for a Lesson or Noble card, reveal it, put it into your hand, then shuffle.\nNoble creatures you control and Lesson spells you control have lifelink.",
)

MAI_SCORNFUL_STRIKER = make_creature(
    name="Mai, Scornful Striker",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Ally", "Human", "Noble"},
    supertypes={"Legendary"},
    text="First strike\nWhenever a player casts a noncreature spell, they lose 2 life.",
)

MERCHANT_OF_MANY_HATS = make_creature(
    name="Merchant of Many Hats",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Ally", "Human", "Peasant"},
    text="{2}{B}: Return this card from your graveyard to your hand.",
)

NORTHERN_AIR_TEMPLE = make_enchantment(
    name="Northern Air Temple",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="When Northern Air Temple enters, each opponent loses X life and you gain X life, where X is the number of Shrines you control.\nWhenever another Shrine you control enters, each opponent loses 1 life and you gain 1 life.",
    subtypes={"Shrine"},
    supertypes={"Legendary"},
)

OBSESSIVE_PURSUIT = make_enchantment(
    name="Obsessive Pursuit",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="When this enchantment enters and at the beginning of your upkeep, you lose 1 life and create a Clue token. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nWhenever you attack, put X +1/+1 counters on target attacking creature, where X is the number of permanents you've sacrificed this turn. If X is three or greater, that creature gains lifelink until end of turn.",
)

OZAIS_CRUELTY = make_sorcery(
    name="Ozai's Cruelty",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Ozai's Cruelty deals 2 damage to target player. That player discards two cards.",
    subtypes={"Lesson"},
)

PHOENIX_FLEET_AIRSHIP = make_artifact(
    name="Phoenix Fleet Airship",
    mana_cost="{2}{B}{B}",
    text="Flying\nAt the beginning of your end step, if you sacrificed a permanent this turn, create a token that's a copy of this Vehicle.\nAs long as you control eight or more permanents named Phoenix Fleet Airship, this Vehicle is an artifact creature.\nCrew 1",
    subtypes={"Vehicle"},
)

PIRATE_PEDDLERS = make_creature(
    name="Pirate Peddlers",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate"},
    text="Deathtouch\nWhenever you sacrifice another permanent, put a +1/+1 counter on this creature.",
)

RAVEN_EAGLE = make_creature(
    name="Raven Eagle",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Bird"},
    text="Flying\nWhenever this creature enters or attacks, exile up to one target card from a graveyard. If a creature card is exiled this way, create a Clue token. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nWhenever you draw your second card each turn, each opponent loses 1 life and you gain 1 life.",
)

THE_RISE_OF_SOZIN = make_creature(
    name="The Rise of Sozin",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Legendary", "Saga"},
    text="",
)

RUINOUS_WATERBENDING = make_sorcery(
    name="Ruinous Waterbending",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, you may waterbend {4}. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)\nAll creatures get -2/-2 until end of turn. If this spell's additional cost was paid, whenever a creature dies this turn, you gain 1 life.",
    subtypes={"Lesson"},
)

SOLD_OUT = make_instant(
    name="Sold Out",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Exile target creature. If it was dealt damage this turn, create a Clue token. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

SWAMPSNARE_TRAP = make_enchantment(
    name="Swampsnare Trap",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="This spell costs {1} less to cast if it targets a creature with flying.\nEnchant creature\nEnchanted creature gets -5/-3.",
    subtypes={"Aura"},
)

TUNDRA_TANK = make_artifact(
    name="Tundra Tank",
    mana_cost="{2}{B}",
    text="Firebending 1 (Whenever this creature attacks, add {R}. This mana lasts until end of combat.)\nWhen this Vehicle enters, target creature you control gains indestructible until end of turn.\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
)

WOLFBAT = make_creature(
    name="Wolfbat",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "Wolf"},
    text="Flying\nWhenever you draw your second card each turn, you may pay {B}. If you do, return this card from your graveyard to the battlefield with a finality counter on it. (If a creature with a finality counter on it would die, exile it instead.)",
)

ZUKOS_CONVICTION = make_instant(
    name="Zuko's Conviction",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Kicker {4} (You may pay an additional {4} as you cast this spell.)\nReturn target creature card from your graveyard to your hand. If this spell was kicked, instead put that card onto the battlefield tapped.",
)

BOARQPINE = make_creature(
    name="Boar-q-pine",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Boar", "Porcupine"},
    text="Whenever you cast a noncreature spell, put a +1/+1 counter on this creature.",
)

BUMI_BASH = make_sorcery(
    name="Bumi Bash",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Choose one —\n• Bumi Bash deals damage equal to the number of lands you control to target creature.\n• Destroy target land creature or nonbasic land.",
)

THE_CAVE_OF_TWO_LOVERS = make_enchantment(
    name="The Cave of Two Lovers",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Create two 1/1 white Ally creature tokens.\nII — Search your library for a Mountain or Cave card, reveal it, put it into your hand, then shuffle.\nIII — Earthbend 3. (Target land you control becomes a 0/0 creature with haste that's still a land. Put three +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped.)",
    subtypes={"Saga"},
)

COMBUSTION_MAN = make_creature(
    name="Combustion Man",
    power=4, toughness=6,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Assassin", "Human"},
    supertypes={"Legendary"},
    text="Whenever Combustion Man attacks, destroy target permanent unless its controller has Combustion Man deal damage to them equal to his power.",
)

COMBUSTION_TECHNIQUE = make_instant(
    name="Combustion Technique",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Combustion Technique deals damage equal to 2 plus the number of Lesson cards in your graveyard to target creature. If that creature would die this turn, exile it instead.",
    subtypes={"Lesson"},
)

CRESCENT_ISLAND_TEMPLE = make_enchantment(
    name="Crescent Island Temple",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="When Crescent Island Temple enters, for each Shrine you control, create a 1/1 red Monk creature token with prowess. (Whenever you cast a noncreature spell, it gets +1/+1 until end of turn.)\nWhenever another Shrine you control enters, create a 1/1 red Monk creature token with prowess.",
    subtypes={"Shrine"},
    supertypes={"Legendary"},
)

CUNNING_MANEUVER = make_instant(
    name="Cunning Maneuver",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+1 until end of turn.\nCreate a Clue token. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

DESERTERS_DISCIPLE = make_creature(
    name="Deserter's Disciple",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Ally", "Human", "Rebel"},
    text="{T}: Another target creature you control with power 2 or less can't be blocked this turn.",
)

FATED_FIREPOWER = make_enchantment(
    name="Fated Firepower",
    mana_cost="{X}{R}{R}{R}",
    colors={Color.RED},
    text="Flash\nThis enchantment enters with X fire counters on it.\nIf a source you control would deal damage to an opponent or a permanent an opponent controls, it deals that much damage plus an amount of damage equal to the number of fire counters on this enchantment instead.",
)

FIRE_NATION_ATTACKS = make_instant(
    name="Fire Nation Attacks",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="Create two 2/2 red Soldier creature tokens with firebending 1. (Whenever a creature with firebending 1 attacks, add {R}. This mana lasts until end of combat.)\nFlashback {8}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

FIRE_NATION_CADETS = make_creature(
    name="Fire Nation Cadets",
    power=1, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="This creature has firebending 2 as long as there's a Lesson card in your graveyard. (Whenever this creature attacks, add {R}{R}. This mana lasts until end of combat.)\n{2}: This creature gets +1/+0 until end of turn.",
)

FIRE_NATION_RAIDER = make_creature(
    name="Fire Nation Raider",
    power=4, toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="Raid — When this creature enters, if you attacked this turn, create a Clue token. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

FIRE_SAGES = make_creature(
    name="Fire Sages",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Cleric", "Human"},
    text="Firebending 1 (Whenever this creature attacks, add {R}. This mana lasts until end of combat.)\n{1}{R}{R}: Put a +1/+1 counter on this creature.",
)

FIREBENDER_ASCENSION = make_enchantment(
    name="Firebender Ascension",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="When this enchantment enters, create a 2/2 red Soldier creature token with firebending 1.\nWhenever a creature you control attacking causes a triggered ability of that creature to trigger, put a quest counter on this enchantment. Then if it has four or more quest counters on it, you may copy that ability. You may choose new targets for the copy.",
)

FIREBENDING_LESSON = make_instant(
    name="Firebending Lesson",
    mana_cost="{R}",
    colors={Color.RED},
    text="Kicker {4} (You may pay an additional {4} as you cast this spell.)\nFirebending Lesson deals 2 damage to target creature. If this spell was kicked, it deals 5 damage to that creature instead.",
    subtypes={"Lesson"},
)

FIREBENDING_STUDENT = make_creature(
    name="Firebending Student",
    power=1, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Monk"},
    text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nFirebending X, where X is this creature's power. (Whenever this creature attacks, add X {R}. This mana lasts until end of combat.)",
)

HOW_TO_START_A_RIOT = make_instant(
    name="How to Start a Riot",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Target creature gains menace until end of turn. (It can't be blocked except by two or more creatures.)\nCreatures target player controls get +2/+0 until end of turn.",
    subtypes={"Lesson"},
)

IROHS_DEMONSTRATION = make_sorcery(
    name="Iroh's Demonstration",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Choose one —\n• Iroh's Demonstration deals 1 damage to each creature your opponents control.\n• Iroh's Demonstration deals 4 damage to target creature.",
    subtypes={"Lesson"},
)

JEONG_JEONG_THE_DESERTER = make_creature(
    name="Jeong Jeong, the Deserter",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Ally", "Human", "Rebel"},
    supertypes={"Legendary"},
    text="Firebending 1 (Whenever this creature attacks, add {R}. This mana lasts until end of combat.)\nExhaust — {3}: Put a +1/+1 counter on Jeong Jeong. When you next cast a Lesson spell this turn, copy it and you may choose new targets for the copy. (Activate each exhaust ability only once.)",
)

JETS_BRAINWASHING = make_sorcery(
    name="Jet's Brainwashing",
    mana_cost="{R}",
    colors={Color.RED},
    text="Kicker {3} (You may pay an additional {3} as you cast this spell.)\nTarget creature can't block this turn. If this spell was kicked, gain control of that creature until end of turn, untap it, and it gains haste until end of turn.\nCreate a Clue token. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

THE_LAST_AGNI_KAI = make_instant(
    name="The Last Agni Kai",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature you control fights target creature an opponent controls. If the creature the opponent controls is dealt excess damage this way, add that much {R}.\nUntil end of turn, you don't lose unspent red mana as steps and phases end.",
)

THE_LEGEND_OF_ROKU = make_creature(
    name="The Legend of Roku",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Legendary", "Saga"},
    text="",
)

LIGHTNING_STRIKE = make_instant(
    name="Lightning Strike",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Lightning Strike deals 3 damage to any target.",
)

MAI_JADED_EDGE = make_creature(
    name="Mai, Jaded Edge",
    power=1, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nExhaust — {3}: Put a double strike counter on Mai. (Activate each exhaust ability only once.)",
)

MONGOOSE_LIZARD = make_creature(
    name="Mongoose Lizard",
    power=5, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Mongoose"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhen this creature enters, it deals 1 damage to any target.\nMountaincycling {2} ({2}, Discard this card: Search your library for a Mountain card, reveal it, put it into your hand, then shuffle.)",
)

PRICE_OF_FREEDOM = make_sorcery(
    name="Price of Freedom",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Destroy target artifact or land an opponent controls. Its controller may search their library for a basic land card, put it onto the battlefield tapped, then shuffle.\nDraw a card.",
    subtypes={"Lesson"},
)

RAN_AND_SHAW = make_creature(
    name="Ran and Shaw",
    power=4, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    supertypes={"Legendary"},
    text="Flying, firebending 2\nWhen Ran and Shaw enter, if you cast them and there are three or more Dragon and/or Lesson cards in your graveyard, create a token that's a copy of Ran and Shaw, except it's not legendary.\n{3}{R}: Dragons you control get +2/+0 until end of turn.",
)

REDIRECT_LIGHTNING = make_instant(
    name="Redirect Lightning",
    mana_cost="{R}",
    colors={Color.RED},
    text="As an additional cost to cast this spell, pay 5 life or pay {2}.\nChange the target of target spell or ability with a single target.",
    subtypes={"Lesson"},
)

ROUGH_RHINO_CAVALRY = make_creature(
    name="Rough Rhino Cavalry",
    power=5, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Human", "Mercenary"},
    text="Firebending 2 (Whenever this creature attacks, add {R}{R}. This mana lasts until end of combat.)\nExhaust — {8}: Put two +1/+1 counters on this creature. It gains trample until end of turn. (Activate each exhaust ability only once.)",
)

SOLSTICE_REVELATIONS = make_instant(
    name="Solstice Revelations",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Exile cards from the top of your library until you exile a nonland card. You may cast that card without paying its mana cost if the spell's mana value is less than the number of Mountains you control. If you don't cast that card this way, put it into your hand.\nFlashback {6}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
    subtypes={"Lesson"},
)

SOZINS_COMET = make_sorcery(
    name="Sozin's Comet",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Each creature you control gains firebending 5 until end of turn. (Whenever it attacks, add {R}{R}{R}{R}{R}. This mana lasts until end of combat.)\nForetell {2}{R} (During your turn, you may pay {2} and exile this card from your hand face down. Cast it on a later turn for its foretell cost.)",
)

TIGERDILLO = make_creature(
    name="Tiger-Dillo",
    power=4, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Armadillo", "Cat"},
    text="This creature can't attack or block unless you control another creature with power 4 or greater.",
)

TREETOP_FREEDOM_FIGHTERS = make_creature(
    name="Treetop Freedom Fighters",
    power=2, toughness=1,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Ally", "Human", "Rebel"},
    text="Haste\nWhen this creature enters, create a 1/1 white Ally creature token.",
)

TWIN_BLADES = make_artifact(
    name="Twin Blades",
    mana_cost="{2}{R}",
    text="Flash\nWhen this Equipment enters, attach it to target creature you control. That creature gains double strike until end of turn.\nEquipped creature gets +1/+1.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

TY_LEE_ARTFUL_ACROBAT = make_creature(
    name="Ty Lee, Artful Acrobat",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Performer"},
    supertypes={"Legendary"},
    text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nWhenever Ty Lee attacks, you may pay {1}. When you do, target creature can't block this turn.",
)

WAR_BALLOON = make_artifact(
    name="War Balloon",
    mana_cost="{2}{R}",
    text="Flying\n{1}: Put a fire counter on this Vehicle.\nAs long as this Vehicle has three or more fire counters on it, it's an artifact creature.\nCrew 3 (Tap any number of creatures you control with total power 3 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
)

WARTIME_PROTESTORS = make_creature(
    name="Wartime Protestors",
    power=4, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Ally", "Human", "Rebel"},
    text="Haste\nWhenever another Ally you control enters, put a +1/+1 counter on that creature and it gains haste until end of turn.",
)

YUYAN_ARCHERS = make_creature(
    name="Yuyan Archers",
    power=3, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Archer", "Human"},
    text="Reach\nWhen this creature enters, you may discard a card. If you do, draw a card.",
)

ZHAO_THE_MOON_SLAYER = make_creature(
    name="Zhao, the Moon Slayer",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Menace\nNonbasic lands enter tapped.\n{7}: Put a conqueror counter on Zhao.\nAs long as Zhao has a conqueror counter on him, nonbasic lands are Mountains. (They lose all other land types and abilities and have \"{T}: Add {R}.\")",
)

ZUKO_EXILED_PRINCE = make_creature(
    name="Zuko, Exiled Prince",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Firebending 3 (Whenever this creature attacks, add {R}{R}{R}. This mana lasts until end of combat.)\n{3}: Exile the top card of your library. You may play that card this turn.",
)

ALLIES_AT_LAST = make_instant(
    name="Allies at Last",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Affinity for Allies (This spell costs {1} less to cast for each Ally you control.)\nUp to two target creatures you control each deal damage equal to their power to target creature an opponent controls.",
)

AVATAR_DESTINY = make_enchantment(
    name="Avatar Destiny",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Enchant creature you control\nEnchanted creature gets +1/+1 for each creature card in your graveyard and is an Avatar in addition to its other types.\nWhen enchanted creature dies, mill cards equal to its power. Return this card to its owner's hand and up to one creature card milled this way to the battlefield under your control.",
    subtypes={"Aura"},
)

BADGERMOLE = make_creature(
    name="Badgermole",
    power=4, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Badger", "Mole"},
    text="When this creature enters, earthbend 2. (Target land you control becomes a 0/0 creature with haste that's still a land. Put two +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped.)\nCreatures you control with +1/+1 counters on them have trample.",
)

BADGERMOLE_CUB = make_creature(
    name="Badgermole Cub",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Badger", "Mole"},
    text="When this creature enters, earthbend 1. (Target land you control becomes a 0/0 creature with haste that's still a land. Put a +1/+1 counter on it. When it dies or is exiled, return it to the battlefield tapped.)\nWhenever you tap a creature for mana, add an additional {G}.",
)

THE_BOULDER_READY_TO_RUMBLE = make_creature(
    name="The Boulder, Ready to Rumble",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Performer", "Warrior"},
    supertypes={"Legendary"},
    text="Whenever The Boulder attacks, earthbend X, where X is the number of creatures you control with power 4 or greater. (Target land you control becomes a 0/0 creature with haste that's still a land. Put X +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped.)",
)

BUMI_KING_OF_THREE_TRIALS = make_creature(
    name="Bumi, King of Three Trials",
    power=4, toughness=4,
    mana_cost="{5}{G}",
    colors={Color.GREEN},
    subtypes={"Ally", "Human", "Noble"},
    supertypes={"Legendary"},
    text="When Bumi enters, choose up to X, where X is the number of Lesson cards in your graveyard —\n• Put three +1/+1 counters on Bumi.\n• Target player scries 3.\n• Earthbend 3. (Target land you control becomes a 0/0 creature with haste that's still a land. Put three +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped.)",
)

CYCLE_OF_RENEWAL = make_instant(
    name="Cycle of Renewal",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Sacrifice a land. Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.",
    subtypes={"Lesson"},
)

DILIGENT_ZOOKEEPER = make_creature(
    name="Diligent Zookeeper",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Ally", "Citizen", "Human"},
    text="Each non-Human creature you control gets +1/+1 for each of its creature types, to a maximum of 10.",
)

THE_EARTH_KING = make_creature(
    name="The Earth King",
    power=2, toughness=2,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Ally", "Human", "Noble"},
    supertypes={"Legendary"},
    text="When The Earth King enters, create a 4/4 green Bear creature token.\nWhenever one or more creatures you control with power 4 or greater attack, search your library for up to that many basic land cards, put them onto the battlefield tapped, then shuffle.",
)

EARTH_KINGDOM_GENERAL = make_creature(
    name="Earth Kingdom General",
    power=2, toughness=2,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Ally", "Human", "Soldier"},
    text="When this creature enters, earthbend 2. (Target land you control becomes a 0/0 creature with haste that's still a land. Put two +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped.)\nWhenever you put one or more +1/+1 counters on a creature, you may gain that much life. Do this only once each turn.",
)

EARTH_RUMBLE = make_sorcery(
    name="Earth Rumble",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Earthbend 2. When you do, up to one target creature you control fights target creature an opponent controls. (To earthbend 2, target land you control becomes a 0/0 creature with haste that's still a land. Put two +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped. Creatures that fight each deal damage equal to their power to the other.)",
)

EARTHBENDER_ASCENSION = make_enchantment(
    name="Earthbender Ascension",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, earthbend 2. Then search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\nLandfall — Whenever a land you control enters, put a quest counter on this enchantment. When you do, if it has four or more quest counters on it, put a +1/+1 counter on target creature you control. It gains trample until end of turn.",
)

EARTHBENDING_LESSON = make_sorcery(
    name="Earthbending Lesson",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Earthbend 4. (Target land you control becomes a 0/0 creature with haste that's still a land. Put four +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped.)",
    subtypes={"Lesson"},
)

EARTHEN_ALLY = make_creature(
    name="Earthen Ally",
    power=0, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Ally", "Human", "Soldier"},
    text="This creature gets +1/+0 for each color among Allies you control.\n{2}{W}{U}{B}{R}{G}: Earthbend 5. (Target land you control becomes a 0/0 creature with haste that's still a land. Put five +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped.)",
)

ELEMENTAL_TEACHINGS = make_instant(
    name="Elemental Teachings",
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    text="Search your library for up to four land cards with different names and reveal them. An opponent chooses two of those cards. Put the chosen cards into your graveyard and the rest onto the battlefield tapped, then shuffle.",
    subtypes={"Lesson"},
)

FLOPSIE_BUMIS_BUDDY = make_creature(
    name="Flopsie, Bumi's Buddy",
    power=4, toughness=4,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Ape", "Goat"},
    supertypes={"Legendary"},
    text="When Flopsie enters, put a +1/+1 counter on each creature you control.\nEach creature you control with power 4 or greater can't be blocked by more than one creature.",
)

FOGGY_SWAMP_VINEBENDER = make_creature(
    name="Foggy Swamp Vinebender",
    power=4, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Ally", "Human", "Plant"},
    text="This creature can't be blocked by creatures with power 2 or less.\nWaterbend {5}: Put a +1/+1 counter on this creature. Activate only during your turn. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)",
)

GREAT_DIVIDE_GUIDE = make_creature(
    name="Great Divide Guide",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Ally", "Human", "Scout"},
    text="Each land and Ally you control has \"{T}: Add one mana of any color.\"",
)

HARU_HIDDEN_TALENT = make_creature(
    name="Haru, Hidden Talent",
    power=1, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Ally", "Human", "Peasant"},
    supertypes={"Legendary"},
    text="Whenever another Ally you control enters, earthbend 1. (Target land you control becomes a 0/0 creature with haste that's still a land. Put a +1/+1 counter on it. When it dies or is exiled, return it to the battlefield tapped.)",
)

INVASION_TACTICS = make_enchantment(
    name="Invasion Tactics",
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, creatures you control get +2/+2 until end of turn.\nWhenever one or more Allies you control deal combat damage to a player, draw a card.",
)

KYOSHI_ISLAND_PLAZA = make_enchantment(
    name="Kyoshi Island Plaza",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="When Kyoshi Island Plaza enters, search your library for up to X basic land cards, where X is the number of Shrines you control. Put those cards onto the battlefield tapped, then shuffle.\nWhenever another Shrine you control enters, search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
    subtypes={"Shrine"},
    supertypes={"Legendary"},
)

LEAVES_FROM_THE_VINE = make_enchantment(
    name="Leaves from the Vine",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Mill three cards, then create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\nII — Put a +1/+1 counter on each of up to two target creatures you control.\nIII — Draw a card if there's a creature or Lesson card in your graveyard.",
    subtypes={"Saga"},
)

THE_LEGEND_OF_KYOSHI = make_creature(
    name="The Legend of Kyoshi",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Legendary", "Saga"},
    text="",
)

ORIGIN_OF_METALBENDING = make_instant(
    name="Origin of Metalbending",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Destroy target artifact or enchantment.\n• Put a +1/+1 counter on target creature you control. It gains indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)",
    subtypes={"Lesson"},
)

OSTRICHHORSE = make_creature(
    name="Ostrich-Horse",
    power=3, toughness=1,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Bird", "Horse"},
    text="When this creature enters, mill three cards. You may put a land card from among them into your hand. If you don't, put a +1/+1 counter on this creature. (To mill three cards, put the top three cards of your library into your graveyard.)",
)

PILLAR_LAUNCH = make_instant(
    name="Pillar Launch",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +2/+2 and gains reach until end of turn. Untap it.",
)

RAUCOUS_AUDIENCE = make_creature(
    name="Raucous Audience",
    power=2, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Citizen", "Human"},
    text="{T}: Add {G}. If you control a creature with power 4 or greater, add {G}{G} instead.",
)

REBELLIOUS_CAPTIVES = make_creature(
    name="Rebellious Captives",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Ally", "Human", "Peasant"},
    text="Exhaust — {6}: Put two +1/+1 counters on this creature, then earthbend 2. (Target land you control becomes a 0/0 creature with haste that's still a land. Put two +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped. Activate each exhaust ability only once.)",
)

ROCKALANCHE = make_sorcery(
    name="Rockalanche",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Earthbend X, where X is the number of Forests you control. (Target land you control becomes a 0/0 creature with haste that's still a land. Put X +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped.)\nFlashback {5}{G} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
    subtypes={"Lesson"},
)

ROCKY_REBUKE = make_instant(
    name="Rocky Rebuke",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control deals damage equal to its power to target creature an opponent controls.",
)

SABERTOOTH_MOOSELION = make_creature(
    name="Saber-Tooth Moose-Lion",
    power=7, toughness=7,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Cat", "Elk"},
    text="Reach\nForestcycling {2} ({2}, Discard this card: Search your library for a Forest card, reveal it, put it into your hand, then shuffle.)",
)

SEISMIC_SENSE = make_sorcery(
    name="Seismic Sense",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Look at the top X cards of your library, where X is the number of lands you control. You may reveal a creature or land card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
    subtypes={"Lesson"},
)

SHARED_ROOTS = make_sorcery(
    name="Shared Roots",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
    subtypes={"Lesson"},
)

SPARRING_DUMMY = make_artifact_creature(
    name="Sparring Dummy",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Scarecrow"},
    text="Defender\n{T}: Mill a card. You may put a land card milled this way into your hand. You gain 2 life if a Lesson card is milled this way. (To mill a card, put the top card of your library into your graveyard.)",
)

TOPH_THE_BLIND_BANDIT = make_creature(
    name="Toph, the Blind Bandit",
    power=0, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Ally", "Human", "Warrior"},
    supertypes={"Legendary"},
    text="When Toph enters, earthbend 2. (Target land you control becomes a 0/0 creature with haste that's still a land. Put two +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped.)\nToph's power is equal to the number of +1/+1 counters on lands you control.",
)

TRUE_ANCESTRY = make_sorcery(
    name="True Ancestry",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Return up to one target permanent card from your graveyard to your hand.\nCreate a Clue token. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    subtypes={"Lesson"},
)

TURTLEDUCK = make_creature(
    name="Turtle-Duck",
    power=0, toughness=4,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Bird", "Turtle"},
    text="{3}: Until end of turn, this creature has base power 4 and gains trample.",
)

UNLUCKY_CABBAGE_MERCHANT = make_creature(
    name="Unlucky Cabbage Merchant",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Citizen", "Human"},
    text="When this creature enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\nWhenever you sacrifice a Food, you may search your library for a basic land card and put it onto the battlefield tapped. If you search your library this way, put this creature on the bottom of its owner's library, then shuffle.",
)

WALLTOP_SENTRIES = make_creature(
    name="Walltop Sentries",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Ally", "Human", "Soldier"},
    text="Reach, deathtouch\nWhen this creature dies, if there's a Lesson card in your graveyard, you gain 2 life.",
)

AANG_AT_THE_CROSSROADS = make_creature(
    name="Aang, at the Crossroads",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Ally", "Avatar", "Creature", "Human", "Legendary"},
    supertypes={"Legendary"},
    text="",
)

AANG_SWIFT_SAVIOR = make_creature(
    name="Aang, Swift Savior",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Ally", "Avatar", "Creature", "Human", "Legendary"},
    supertypes={"Legendary"},
    text="",
)

ABANDON_ATTACHMENTS = make_instant(
    name="Abandon Attachments",
    mana_cost="{1}{U/R}",
    colors={Color.RED, Color.BLUE},
    text="You may discard a card. If you do, draw two cards.",
    subtypes={"Lesson"},
)

AIR_NOMAD_LEGACY = make_enchantment(
    name="Air Nomad Legacy",
    mana_cost="{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    text="When this enchantment enters, create a Clue token. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nCreatures you control with flying get +1/+1.",
)

AVATAR_AANG = make_creature(
    name="Avatar Aang",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Ally", "Avatar", "Creature", "Human", "Legendary"},
    supertypes={"Legendary"},
    text="",
)

AZULA_CUNNING_USURPER = make_creature(
    name="Azula, Cunning Usurper",
    power=4, toughness=4,
    mana_cost="{2}{U}{B}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Noble", "Rogue"},
    supertypes={"Legendary"},
    text="Firebending 2 (Whenever this creature attacks, add {R}{R}. This mana lasts until end of combat.)\nWhen Azula enters, target opponent exiles a nontoken creature they control, then they exile a nonland card from their graveyard.\nDuring your turn, you may cast cards exiled with Azula and you may cast them as though they had flash. Mana of any type can be spent to cast those spells.",
)

BEIFONGS_BOUNTY_HUNTERS = make_creature(
    name="Beifong's Bounty Hunters",
    power=4, toughness=4,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Mercenary"},
    text="Whenever a nonland creature you control dies, earthbend X, where X is that creature's power. (Target land you control becomes a 0/0 creature with haste that's still a land. Put X +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped.)",
)

BITTER_WORK = make_enchantment(
    name="Bitter Work",
    mana_cost="{1}{R}{G}",
    colors={Color.GREEN, Color.RED},
    text="Whenever you attack a player with one or more creatures with power 4 or greater, draw a card.\nExhaust — {4}: Earthbend 4. Activate only during your turn. (Target land you control becomes a 0/0 creature with haste that's still a land. Put four +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped. Activate each exhaust ability only once.)",
)

BUMI_UNLEASHED = make_creature(
    name="Bumi, Unleashed",
    power=5, toughness=4,
    mana_cost="{3}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Ally", "Human", "Noble"},
    supertypes={"Legendary"},
    text="Trample\nWhen Bumi enters, earthbend 4.\nWhenever Bumi deals combat damage to a player, untap all lands you control. After this phase, there is an additional combat phase. Only land creatures can attack during that combat phase.",
)

CATOWL = make_creature(
    name="Cat-Owl",
    power=3, toughness=3,
    mana_cost="{3}{W/U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Bird", "Cat"},
    text="Flying\nWhenever this creature attacks, untap target artifact or creature.",
)

CRUEL_ADMINISTRATOR = make_creature(
    name="Cruel Administrator",
    power=5, toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Soldier"},
    text="Raid — This creature enters with a +1/+1 counter on it if you attacked this turn.\nWhenever this creature attacks, create a 2/2 red Soldier creature token with firebending 1. (Whenever it attacks, add {R}. This mana lasts until end of combat.)",
)

DAI_LI_AGENTS = make_creature(
    name="Dai Li Agents",
    power=3, toughness=4,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Soldier"},
    text="When this creature enters, earthbend 1, then earthbend 1. (To earthbend 1, target land you control becomes a 0/0 creature with haste that's still a land. Put a +1/+1 counter on it. When it dies or is exiled, return it to the battlefield tapped.)\nWhenever this creature attacks, each opponent loses X life and you gain X life, where X is the number of creatures you control with +1/+1 counters on them.",
)

DRAGONFLY_SWARM = make_creature(
    name="Dragonfly Swarm",
    power=0, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Dragon", "Insect"},
    text="Flying, ward {1} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {1}.)\nThis creature's power is equal to the number of noncreature, nonland cards in your graveyard.\nWhen this creature dies, if there's a Lesson card in your graveyard, draw a card.",
)

EARTH_KINGDOM_SOLDIER = make_creature(
    name="Earth Kingdom Soldier",
    power=3, toughness=4,
    mana_cost="{4}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Vigilance\nWhen this creature enters, put a +1/+1 counter on each of up to two target creatures you control.",
)

EARTH_KINGS_LIEUTENANT = make_creature(
    name="Earth King's Lieutenant",
    power=1, toughness=1,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Ally", "Human", "Soldier"},
    text="Trample\nWhen this creature enters, put a +1/+1 counter on each other Ally creature you control.\nWhenever another Ally you control enters, put a +1/+1 counter on this creature.",
)

EARTH_RUMBLE_WRESTLERS = make_creature(
    name="Earth Rumble Wrestlers",
    power=3, toughness=4,
    mana_cost="{3}{R/G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Performer", "Warrior"},
    text="Reach\nThis creature gets +1/+0 and has trample as long as you control a land creature or a land entered the battlefield under your control this turn.",
)

EARTH_VILLAGE_RUFFIANS = make_creature(
    name="Earth Village Ruffians",
    power=3, toughness=1,
    mana_cost="{2}{B/G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Rogue", "Soldier"},
    text="When this creature dies, earthbend 2. (Target land you control becomes a 0/0 creature with haste that's still a land. Put two +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped.)",
)

FIRE_LORD_AZULA = make_creature(
    name="Fire Lord Azula",
    power=4, toughness=4,
    mana_cost="{1}{U}{B}{R}",
    colors={Color.BLACK, Color.RED, Color.BLUE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Firebending 2 (Whenever this creature attacks, add {R}{R}. This mana lasts until end of combat.)\nWhenever you cast a spell while Fire Lord Azula is attacking, copy that spell. You may choose new targets for the copy. (A copy of a permanent spell becomes a token.)",
)

FIRE_LORD_ZUKO = make_creature(
    name="Fire Lord Zuko",
    power=2, toughness=4,
    mana_cost="{R}{W}{B}",
    colors={Color.BLACK, Color.RED, Color.WHITE},
    subtypes={"Ally", "Human", "Noble"},
    supertypes={"Legendary"},
    text="Firebending X, where X is Fire Lord Zuko's power. (Whenever this creature attacks, add X {R}. This mana lasts until end of combat.)\nWhenever you cast a spell from exile and whenever a permanent you control enters from exile, put a +1/+1 counter on each creature you control.",
)

FOGGY_SWAMP_SPIRIT_KEEPER = make_creature(
    name="Foggy Swamp Spirit Keeper",
    power=2, toughness=4,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Ally", "Druid", "Human"},
    text="Lifelink\nWhenever you draw your second card each turn, create a 1/1 colorless Spirit creature token with \"This token can't block or be blocked by non-Spirit creatures.\"",
)

GURU_PATHIK = make_creature(
    name="Guru Pathik",
    power=2, toughness=4,
    mana_cost="{2}{G/U}{G/U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Ally", "Human", "Monk"},
    supertypes={"Legendary"},
    text="When Guru Pathik enters, look at the top five cards of your library. You may reveal a Lesson, Saga, or Shrine card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.\nWhenever you cast a Lesson, Saga, or Shrine spell, put a +1/+1 counter on another target creature you control.",
)

HAMA_THE_BLOODBENDER = make_creature(
    name="Hama, the Bloodbender",
    power=3, toughness=3,
    mana_cost="{2}{U/B}{U/B}{U/B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="When Hama enters, target opponent mills three cards. Exile up to one noncreature, nonland card from that player's graveyard. For as long as you control Hama, you may cast the exiled card during your turn by waterbending {X} rather than paying its mana cost, where X is its mana value. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)",
)

HEI_BAI_SPIRIT_OF_BALANCE = make_creature(
    name="Hei Bai, Spirit of Balance",
    power=3, toughness=3,
    mana_cost="{2}{W/B}{W/B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Bear", "Spirit"},
    supertypes={"Legendary"},
    text="Whenever Hei Bai enters or attacks, you may sacrifice another creature or artifact. If you do, put two +1/+1 counters on Hei Bai.\nWhen Hei Bai leaves the battlefield, put its counters on target creature you control.",
)

HERMITIC_HERBALIST = make_creature(
    name="Hermitic Herbalist",
    power=2, toughness=3,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Ally", "Druid", "Human"},
    text="{T}: Add one mana of any color.\n{T}: Add two mana in any combination of colors. Spend this mana only to cast Lesson spells.",
)

IROH_GRAND_LOTUS = make_creature(
    name="Iroh, Grand Lotus",
    power=5, toughness=5,
    mana_cost="{3}{G}{U}{R}",
    colors={Color.GREEN, Color.RED, Color.BLUE},
    subtypes={"Ally", "Human", "Noble"},
    supertypes={"Legendary"},
    text="Firebending 2\nDuring your turn, each non-Lesson instant and sorcery card in your graveyard has flashback. The flashback cost is equal to that card's mana cost. (You may cast a card from your graveyard for its flashback cost. Then exile it.)\nDuring your turn, each Lesson card in your graveyard has flashback {1}.",
)

IROH_TEA_MASTER = make_creature(
    name="Iroh, Tea Master",
    power=2, toughness=2,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Ally", "Citizen", "Human"},
    supertypes={"Legendary"},
    text="When Iroh enters, create a Food token.\nAt the beginning of combat on your turn, you may have target opponent gain control of target permanent you control. When you do, create a 1/1 white Ally creature token. Put a +1/+1 counter on that token for each permanent you own that your opponents control.",
)

JET_FREEDOM_FIGHTER = make_creature(
    name="Jet, Freedom Fighter",
    power=3, toughness=1,
    mana_cost="{2}{R/W}{R/W}{R/W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Ally", "Human", "Rebel"},
    supertypes={"Legendary"},
    text="When Jet enters, he deals damage equal to the number of creatures you control to target creature an opponent controls.\nWhen Jet dies, put a +1/+1 counter on each of up to two target creatures.",
)

KATARA_THE_FEARLESS = make_creature(
    name="Katara, the Fearless",
    power=3, toughness=3,
    mana_cost="{G}{W}{U}",
    colors={Color.GREEN, Color.BLUE, Color.WHITE},
    subtypes={"Ally", "Human", "Warrior"},
    supertypes={"Legendary"},
    text="If a triggered ability of an Ally you control triggers, that ability triggers an additional time.",
)

KATARA_WATER_TRIBES_HOPE = make_creature(
    name="Katara, Water Tribe's Hope",
    power=3, toughness=3,
    mana_cost="{2}{W}{U}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Ally", "Human", "Warrior"},
    supertypes={"Legendary"},
    text="Vigilance\nWhen Katara enters, create a 1/1 white Ally creature token.\nWaterbend {X}: Creatures you control have base power and toughness X/X until end of turn. X can't be 0. Activate only during your turn. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)",
)

THE_LIONTURTLE = make_creature(
    name="The Lion-Turtle",
    power=3, toughness=6,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Cat", "Elder", "Turtle"},
    supertypes={"Legendary"},
    text="Vigilance, reach\nWhen The Lion-Turtle enters, you gain 3 life.\nThe Lion-Turtle can't attack or block unless there are three or more Lesson cards in your graveyard.\n{T}: Add one mana of any color.",
)

LONG_FENG_GRAND_SECRETARIAT = make_creature(
    name="Long Feng, Grand Secretariat",
    power=2, toughness=3,
    mana_cost="{1}{B/G}{B/G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Advisor", "Human"},
    supertypes={"Legendary"},
    text="Whenever another creature you control or a land you control is put into a graveyard from the battlefield, put a +1/+1 counter on target creature you control.",
)

MESSENGER_HAWK = make_creature(
    name="Messenger Hawk",
    power=1, toughness=2,
    mana_cost="{2}{U/B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Bird", "Scout"},
    text="Flying\nWhen this creature enters, create a Clue token. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nThis creature gets +2/+0 as long as you've drawn two or more cards this turn.",
)

OZAI_THE_PHOENIX_KING = make_creature(
    name="Ozai, the Phoenix King",
    power=7, toughness=7,
    mana_cost="{2}{B}{B}{R}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Trample, firebending 4, haste\nIf you would lose unspent mana, that mana becomes red instead.\nOzai has flying and indestructible as long as you have six or more unspent mana.",
)

PLATYPUSBEAR = make_creature(
    name="Platypus-Bear",
    power=2, toughness=3,
    mana_cost="{1}{G/U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Bear", "Platypus"},
    text="Defender\nWhen this creature enters, mill two cards. (Put the top two cards of your library into your graveyard.)\nAs long as there is a Lesson card in your graveyard, this creature can attack as though it didn't have defender.",
)

PRETENDING_POXBEARERS = make_creature(
    name="Pretending Poxbearers",
    power=2, toughness=1,
    mana_cost="{1}{W/B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Ally", "Citizen", "Human"},
    text="When this creature dies, create a 1/1 white Ally creature token.",
)

PROFESSOR_ZEI_ANTHROPOLOGIST = make_creature(
    name="Professor Zei, Anthropologist",
    power=0, toughness=3,
    mana_cost="{U/R}{U/R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Advisor", "Ally", "Human"},
    supertypes={"Legendary"},
    text="{T}, Discard a card: Draw a card.\n{1}, {T}, Sacrifice Professor Zei: Return target instant or sorcery card from your graveyard to your hand. Activate only during your turn.",
)

SANDBENDER_SCAVENGERS = make_creature(
    name="Sandbender Scavengers",
    power=1, toughness=1,
    mana_cost="{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Rogue"},
    text="Whenever you sacrifice another permanent, put a +1/+1 counter on this creature.\nWhen this creature dies, you may exile it. When you do, return target creature card with mana value less than or equal to this creature's power from your graveyard to the battlefield.",
)

SOKKA_BOLD_BOOMERANGER = make_creature(
    name="Sokka, Bold Boomeranger",
    power=1, toughness=1,
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Ally", "Human", "Warrior"},
    supertypes={"Legendary"},
    text="When Sokka enters, discard up to two cards, then draw that many cards.\nWhenever you cast an artifact or Lesson spell, put a +1/+1 counter on Sokka.",
)

SOKKA_LATERAL_STRATEGIST = make_creature(
    name="Sokka, Lateral Strategist",
    power=2, toughness=4,
    mana_cost="{1}{W/U}{W/U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Ally", "Human", "Warrior"},
    supertypes={"Legendary"},
    text="Vigilance\nWhenever Sokka and at least one other creature attack, draw a card.",
)

SOKKA_TENACIOUS_TACTICIAN = make_creature(
    name="Sokka, Tenacious Tactician",
    power=3, toughness=3,
    mana_cost="{1}{U}{R}{W}",
    colors={Color.RED, Color.BLUE, Color.WHITE},
    subtypes={"Ally", "Human", "Warrior"},
    supertypes={"Legendary"},
    text="Menace, prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nOther Allies you control have menace and prowess.\nWhenever you cast a noncreature spell, create a 1/1 white Ally creature token.",
)

SUKI_KYOSHI_WARRIOR = make_creature(
    name="Suki, Kyoshi Warrior",
    power=0, toughness=4,
    mana_cost="{2}{G/W}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Ally", "Human", "Warrior"},
    supertypes={"Legendary"},
    text="Suki's power is equal to the number of creatures you control.\nWhenever Suki attacks, create a 1/1 white Ally creature token that's tapped and attacking.",
)

SUN_WARRIORS = make_creature(
    name="Sun Warriors",
    power=3, toughness=5,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Ally", "Human", "Warrior"},
    text="Firebending X, where X is the number of creatures you control. (Whenever this creature attacks, add X {R}. This mana lasts until end of combat.)\n{5}: Create a 1/1 white Ally creature token.",
)

TOLLS_OF_WAR = make_enchantment(
    name="Tolls of War",
    mana_cost="{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    text="When this enchantment enters, create a Clue token. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nWhenever you sacrifice a permanent during your turn, create a 1/1 white Ally creature token. This ability triggers only once each turn.",
)

TOPH_HARDHEADED_TEACHER = make_creature(
    name="Toph, Hardheaded Teacher",
    power=3, toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Ally", "Human", "Warrior"},
    supertypes={"Legendary"},
    text="When Toph enters, you may discard a card. If you do, return target instant or sorcery card from your graveyard to your hand.\nWhenever you cast a spell, earthbend 1. If that spell is a Lesson, put an additional +1/+1 counter on that land. (Target land you control becomes a 0/0 creature with haste that's still a land. Put a +1/+1 counter on it. When it dies or is exiled, return it to the battlefield tapped.)",
)

TOPH_THE_FIRST_METALBENDER = make_creature(
    name="Toph, the First Metalbender",
    power=3, toughness=3,
    mana_cost="{1}{R}{G}{W}",
    colors={Color.GREEN, Color.RED, Color.WHITE},
    subtypes={"Ally", "Human", "Warrior"},
    supertypes={"Legendary"},
    text="Nontoken artifacts you control are lands in addition to their other types. (They don't gain the ability to {T} for mana.)\nAt the beginning of your end step, earthbend 2. (Target land you control becomes a 0/0 creature with haste that's still a land. Put two +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped.)",
)

UNCLE_IROH = make_creature(
    name="Uncle Iroh",
    power=4, toughness=2,
    mana_cost="{1}{R/G}{R/G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Ally", "Human", "Noble"},
    supertypes={"Legendary"},
    text="Firebending 1 (Whenever this creature attacks, add {R}. This mana lasts until end of combat.)\nLesson spells you cast cost {1} less to cast.",
)

VINDICTIVE_WARDEN = make_creature(
    name="Vindictive Warden",
    power=2, toughness=3,
    mana_cost="{2}{B/R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Soldier"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nFirebending 1 (Whenever this creature attacks, add {R}. This mana lasts until end of combat.)\n{3}: This creature deals 1 damage to each opponent.",
)

WANDERING_MUSICIANS = make_creature(
    name="Wandering Musicians",
    power=2, toughness=5,
    mana_cost="{3}{R/W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Ally", "Bard", "Human"},
    text="Whenever this creature attacks, creatures you control get +1/+0 until end of turn.",
)

WHITE_LOTUS_REINFORCEMENTS = make_creature(
    name="White Lotus Reinforcements",
    power=2, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Ally", "Human", "Soldier"},
    text="Vigilance\nOther Allies you control get +1/+1.",
)

ZHAO_RUTHLESS_ADMIRAL = make_creature(
    name="Zhao, Ruthless Admiral",
    power=3, toughness=4,
    mana_cost="{2}{B/R}{B/R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Firebending 2 (Whenever this creature attacks, add {R}{R}. This mana lasts until end of combat.)\nWhenever you sacrifice another permanent, creatures you control get +1/+0 until end of turn.",
)

ZUKO_CONFLICTED = make_creature(
    name="Zuko, Conflicted",
    power=2, toughness=3,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="At the beginning of your first main phase, choose one that hasn't been chosen and you lose 2 life —\n• Draw a card.\n• Put a +1/+1 counter on Zuko.\n• Add {R}.\n• Exile Zuko, then return him to the battlefield under an opponent's control.",
)

BARRELS_OF_BLASTING_JELLY = make_artifact(
    name="Barrels of Blasting Jelly",
    mana_cost="{1}",
    text="{1}: Add one mana of any color. Activate only once each turn.\n{5}, {T}, Sacrifice this artifact: It deals 5 damage to target creature.",
)

BENDERS_WATERSKIN = make_artifact(
    name="Bender's Waterskin",
    mana_cost="{3}",
    text="Untap this artifact during each other player's untap step.\n{T}: Add one mana of any color.",
)

FIRE_NATION_WARSHIP = make_artifact(
    name="Fire Nation Warship",
    mana_cost="{3}",
    text="Reach\nWhen this Vehicle dies, create a Clue token. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nCrew 2 (Tap any number of creatures you control with total power 2 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
)

KYOSHI_BATTLE_FAN = make_artifact(
    name="Kyoshi Battle Fan",
    mana_cost="{2}",
    text="When this Equipment enters, create a 1/1 white Ally creature token, then attach this Equipment to it.\nEquipped creature gets +1/+0.\nEquip {2} ({2}:Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

METEOR_SWORD = make_artifact(
    name="Meteor Sword",
    mana_cost="{7}",
    text="When this Equipment enters, destroy target permanent.\nEquipped creature gets +3/+3.\nEquip {3} ({3}:Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

PLANETARIUM_OF_WAN_SHI_TONG = make_artifact(
    name="Planetarium of Wan Shi Tong",
    mana_cost="{6}",
    text="{1}, {T}: Scry 2.\nWhenever you scry or surveil, look at the top card of your library. You may cast that card without paying its mana cost. Do this only once each turn. (Look at the card after you scry or surveil.)",
    supertypes={"Legendary"},
)

TRUSTY_BOOMERANG = make_artifact(
    name="Trusty Boomerang",
    mana_cost="{1}",
    text="Equipped creature has \"{1}, {T}: Tap target creature. Return Trusty Boomerang to its owner's hand.\"\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

THE_WALLS_OF_BA_SING_SE = make_artifact_creature(
    name="The Walls of Ba Sing Se",
    power=0, toughness=30,
    mana_cost="{8}",
    colors=set(),
    subtypes={"Wall"},
    supertypes={"Legendary"},
    text="Defender\nOther permanents you control have indestructible.",
)

WHITE_LOTUS_TILE = make_artifact(
    name="White Lotus Tile",
    mana_cost="{4}",
    text="This artifact enters tapped.\n{T}: Add X mana of any one color, where X is the greatest number of creatures you control that have a creature type in common.",
)

ABANDONED_AIR_TEMPLE = make_land(
    name="Abandoned Air Temple",
    text="This land enters tapped unless you control a basic land.\n{T}: Add {W}.\n{3}{W}, {T}: Put a +1/+1 counter on each creature you control.",
)

AGNA_QELA = make_land(
    name="Agna Qel'a",
    text="This land enters tapped unless you control a basic land.\n{T}: Add {U}.\n{2}{U}, {T}: Draw a card, then discard a card.",
)

AIRSHIP_ENGINE_ROOM = make_land(
    name="Airship Engine Room",
    text="This land enters tapped.\n{T}: Add {U} or {R}.\n{4}, {T}, Sacrifice this land: Draw a card.",
)

BA_SING_SE = make_land(
    name="Ba Sing Se",
    text="This land enters tapped unless you control a basic land.\n{T}: Add {G}.\n{2}{G}, {T}: Earthbend 2. Activate only as a sorcery. (Target land you control becomes a 0/0 creature with haste that's still a land. Put two +1/+1 counters on it. When it dies or is exiled, return it to the battlefield tapped.)",
)

BOILING_ROCK_PRISON = make_land(
    name="Boiling Rock Prison",
    text="This land enters tapped.\n{T}: Add {B} or {R}.\n{4}, {T}, Sacrifice this land: Draw a card.",
)

FIRE_NATION_PALACE = make_land(
    name="Fire Nation Palace",
    text="This land enters tapped unless you control a basic land.\n{T}: Add {R}.\n{1}{R}, {T}: Target creature you control gains firebending 4 until end of turn. (Whenever it attacks, add {R}{R}{R}{R}. This mana lasts until end of combat.)",
)

FOGGY_BOTTOM_SWAMP = make_land(
    name="Foggy Bottom Swamp",
    text="This land enters tapped.\n{T}: Add {B} or {G}.\n{4}, {T}, Sacrifice this land: Draw a card.",
)

JASMINE_DRAGON_TEA_SHOP = make_land(
    name="Jasmine Dragon Tea Shop",
    text="{T}: Add {C}.\n{T}: Add one mana of any color. Spend this mana only to cast an Ally spell or activate an ability of an Ally source.\n{5}, {T}: Create a 1/1 white Ally creature token.",
)

KYOSHI_VILLAGE = make_land(
    name="Kyoshi Village",
    text="This land enters tapped.\n{T}: Add {G} or {W}.\n{4}, {T}, Sacrifice this land: Draw a card.",
)

MEDITATION_POOLS = make_land(
    name="Meditation Pools",
    text="This land enters tapped.\n{T}: Add {G} or {U}.\n{4}, {T}, Sacrifice this land: Draw a card.",
)

MISTY_PALMS_OASIS = make_land(
    name="Misty Palms Oasis",
    text="This land enters tapped.\n{T}: Add {W} or {B}.\n{4}, {T}, Sacrifice this land: Draw a card.",
)

NORTH_POLE_GATES = make_land(
    name="North Pole Gates",
    text="This land enters tapped.\n{T}: Add {W} or {U}.\n{4}, {T}, Sacrifice this land: Draw a card.",
)

OMASHU_CITY = make_land(
    name="Omashu City",
    text="This land enters tapped.\n{T}: Add {R} or {G}.\n{4}, {T}, Sacrifice this land: Draw a card.",
)

REALM_OF_KOH = make_land(
    name="Realm of Koh",
    text="This land enters tapped unless you control a basic land.\n{T}: Add {B}.\n{3}{B}, {T}: Create a 1/1 colorless Spirit creature token with \"This token can't block or be blocked by non-Spirit creatures.\"",
)

RUMBLE_ARENA = make_land(
    name="Rumble Arena",
    text="Vigilance\nWhen this land enters, scry 1. (Look at the top card of your library. You may put it on the bottom.)\n{T}: Add {C}.\n{1}, {T}: Add one mana of any color.",
)

SECRET_TUNNEL = make_land(
    name="Secret Tunnel",
    text="This land can't be blocked.\n{T}: Add {C}.\n{4}, {T}: Two target creatures you control that share a creature type can't be blocked this turn.",
    subtypes={"Cave"},
)

SERPENTS_PASS = make_land(
    name="Serpent's Pass",
    text="This land enters tapped.\n{T}: Add {U} or {B}.\n{4}, {T}, Sacrifice this land: Draw a card.",
)

SUNBLESSED_PEAK = make_land(
    name="Sun-Blessed Peak",
    text="This land enters tapped.\n{T}: Add {R} or {W}.\n{4}, {T}, Sacrifice this land: Draw a card.",
)

WHITE_LOTUS_HIDEOUT = make_land(
    name="White Lotus Hideout",
    text="{T}: Add {C}.\n{T}: Add one mana of any color. Spend this mana only to cast a Lesson or Shrine spell.\n{1}, {T}: Add one mana of any color.",
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

AVATAR_TLA_CARDS = {
    "Aang's Journey": AANGS_JOURNEY,
    "Energybending": ENERGYBENDING,
    "Zuko's Exile": ZUKOS_EXILE,
    "Aang, the Last Airbender": AANG_THE_LAST_AIRBENDER,
    "Aang's Iceberg": AANGS_ICEBERG,
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
    "Kyoshi Warriors": KYOSHI_WARRIORS,
    "The Legend of Yangchen": THE_LEGEND_OF_YANGCHEN,
    "Master Piandao": MASTER_PIANDAO,
    "Momo, Friendly Flier": MOMO_FRIENDLY_FLIER,
    "Momo, Playful Pet": MOMO_PLAYFUL_PET,
    "Path to Redemption": PATH_TO_REDEMPTION,
    "Rabaroo Troop": RABAROO_TROOP,
    "Razor Rings": RAZOR_RINGS,
    "Sandbenders' Storm": SANDBENDERS_STORM,
    "South Pole Voyager": SOUTH_POLE_VOYAGER,
    "Southern Air Temple": SOUTHERN_AIR_TEMPLE,
    "Suki, Courageous Rescuer": SUKI_COURAGEOUS_RESCUER,
    "Team Avatar": TEAM_AVATAR,
    "United Front": UNITED_FRONT,
    "Vengeful Villagers": VENGEFUL_VILLAGERS,
    "Water Tribe Captain": WATER_TRIBE_CAPTAIN,
    "Water Tribe Rallier": WATER_TRIBE_RALLIER,
    "Yip Yip!": YIP_YIP,
    "Accumulate Wisdom": ACCUMULATE_WISDOM,
    "Benevolent River Spirit": BENEVOLENT_RIVER_SPIRIT,
    "Boomerang Basics": BOOMERANG_BASICS,
    "Crashing Wave": CRASHING_WAVE,
    "Ember Island Production": EMBER_ISLAND_PRODUCTION,
    "First-Time Flyer": FIRSTTIME_FLYER,
    "Flexible Waterbender": FLEXIBLE_WATERBENDER,
    "Forecasting Fortune Teller": FORECASTING_FORTUNE_TELLER,
    "Geyser Leaper": GEYSER_LEAPER,
    "Giant Koi": GIANT_KOI,
    "Gran-Gran": GRANGRAN,
    "Honest Work": HONEST_WORK,
    "Iguana Parrot": IGUANA_PARROT,
    "Invasion Submersible": INVASION_SUBMERSIBLE,
    "It'll Quench Ya!": ITLL_QUENCH_YA,
    "Katara, Bending Prodigy": KATARA_BENDING_PRODIGY,
    "Knowledge Seeker": KNOWLEDGE_SEEKER,
    "The Legend of Kuruk": THE_LEGEND_OF_KURUK,
    "Lost Days": LOST_DAYS,
    "Master Pakku": MASTER_PAKKU,
    "The Mechanist, Aerial Artisan": THE_MECHANIST_AERIAL_ARTISAN,
    "North Pole Patrol": NORTH_POLE_PATROL,
    "Octopus Form": OCTOPUS_FORM,
    "Otter-Penguin": OTTERPENGUIN,
    "Rowdy Snowballers": ROWDY_SNOWBALLERS,
    "Secret of Bloodbending": SECRET_OF_BLOODBENDING,
    "Serpent of the Pass": SERPENT_OF_THE_PASS,
    "Sokka's Haiku": SOKKAS_HAIKU,
    "The Spirit Oasis": THE_SPIRIT_OASIS,
    "Spirit Water Revival": SPIRIT_WATER_REVIVAL,
    "Teo, Spirited Glider": TEO_SPIRITED_GLIDER,
    "Tiger-Seal": TIGERSEAL,
    "Ty Lee, Chi Blocker": TY_LEE_CHI_BLOCKER,
    "The Unagi of Kyoshi Island": THE_UNAGI_OF_KYOSHI_ISLAND,
    "Wan Shi Tong, Librarian": WAN_SHI_TONG_LIBRARIAN,
    "Waterbender Ascension": WATERBENDER_ASCENSION,
    "Waterbending Lesson": WATERBENDING_LESSON,
    "Waterbending Scroll": WATERBENDING_SCROLL,
    "Watery Grasp": WATERY_GRASP,
    "Yue, the Moon Spirit": YUE_THE_MOON_SPIRIT,
    "Azula Always Lies": AZULA_ALWAYS_LIES,
    "Azula, On the Hunt": AZULA_ON_THE_HUNT,
    "Beetle-Headed Merchants": BEETLEHEADED_MERCHANTS,
    "Boiling Rock Rioter": BOILING_ROCK_RIOTER,
    "Buzzard-Wasp Colony": BUZZARDWASP_COLONY,
    "Callous Inspector": CALLOUS_INSPECTOR,
    "Canyon Crawler": CANYON_CRAWLER,
    "Cat-Gator": CATGATOR,
    "Corrupt Court Official": CORRUPT_COURT_OFFICIAL,
    "Dai Li Indoctrination": DAI_LI_INDOCTRINATION,
    "Day of Black Sun": DAY_OF_BLACK_SUN,
    "Deadly Precision": DEADLY_PRECISION,
    "Epic Downfall": EPIC_DOWNFALL,
    "Fatal Fissure": FATAL_FISSURE,
    "The Fire Nation Drill": THE_FIRE_NATION_DRILL,
    "Fire Nation Engineer": FIRE_NATION_ENGINEER,
    "Fire Navy Trebuchet": FIRE_NAVY_TREBUCHET,
    "Foggy Swamp Hunters": FOGGY_SWAMP_HUNTERS,
    "Foggy Swamp Visions": FOGGY_SWAMP_VISIONS,
    "Heartless Act": HEARTLESS_ACT,
    "Hog-Monkey": HOGMONKEY,
    "Joo Dee, One of Many": JOO_DEE_ONE_OF_MANY,
    "June, Bounty Hunter": JUNE_BOUNTY_HUNTER,
    "Koh, the Face Stealer": KOH_THE_FACE_STEALER,
    "Lo and Li, Twin Tutors": LO_AND_LI_TWIN_TUTORS,
    "Mai, Scornful Striker": MAI_SCORNFUL_STRIKER,
    "Merchant of Many Hats": MERCHANT_OF_MANY_HATS,
    "Northern Air Temple": NORTHERN_AIR_TEMPLE,
    "Obsessive Pursuit": OBSESSIVE_PURSUIT,
    "Ozai's Cruelty": OZAIS_CRUELTY,
    "Phoenix Fleet Airship": PHOENIX_FLEET_AIRSHIP,
    "Pirate Peddlers": PIRATE_PEDDLERS,
    "Raven Eagle": RAVEN_EAGLE,
    "The Rise of Sozin": THE_RISE_OF_SOZIN,
    "Ruinous Waterbending": RUINOUS_WATERBENDING,
    "Sold Out": SOLD_OUT,
    "Swampsnare Trap": SWAMPSNARE_TRAP,
    "Tundra Tank": TUNDRA_TANK,
    "Wolfbat": WOLFBAT,
    "Zuko's Conviction": ZUKOS_CONVICTION,
    "Boar-q-pine": BOARQPINE,
    "Bumi Bash": BUMI_BASH,
    "The Cave of Two Lovers": THE_CAVE_OF_TWO_LOVERS,
    "Combustion Man": COMBUSTION_MAN,
    "Combustion Technique": COMBUSTION_TECHNIQUE,
    "Crescent Island Temple": CRESCENT_ISLAND_TEMPLE,
    "Cunning Maneuver": CUNNING_MANEUVER,
    "Deserter's Disciple": DESERTERS_DISCIPLE,
    "Fated Firepower": FATED_FIREPOWER,
    "Fire Nation Attacks": FIRE_NATION_ATTACKS,
    "Fire Nation Cadets": FIRE_NATION_CADETS,
    "Fire Nation Raider": FIRE_NATION_RAIDER,
    "Fire Sages": FIRE_SAGES,
    "Firebender Ascension": FIREBENDER_ASCENSION,
    "Firebending Lesson": FIREBENDING_LESSON,
    "Firebending Student": FIREBENDING_STUDENT,
    "How to Start a Riot": HOW_TO_START_A_RIOT,
    "Iroh's Demonstration": IROHS_DEMONSTRATION,
    "Jeong Jeong, the Deserter": JEONG_JEONG_THE_DESERTER,
    "Jet's Brainwashing": JETS_BRAINWASHING,
    "The Last Agni Kai": THE_LAST_AGNI_KAI,
    "The Legend of Roku": THE_LEGEND_OF_ROKU,
    "Lightning Strike": LIGHTNING_STRIKE,
    "Mai, Jaded Edge": MAI_JADED_EDGE,
    "Mongoose Lizard": MONGOOSE_LIZARD,
    "Price of Freedom": PRICE_OF_FREEDOM,
    "Ran and Shaw": RAN_AND_SHAW,
    "Redirect Lightning": REDIRECT_LIGHTNING,
    "Rough Rhino Cavalry": ROUGH_RHINO_CAVALRY,
    "Solstice Revelations": SOLSTICE_REVELATIONS,
    "Sozin's Comet": SOZINS_COMET,
    "Tiger-Dillo": TIGERDILLO,
    "Treetop Freedom Fighters": TREETOP_FREEDOM_FIGHTERS,
    "Twin Blades": TWIN_BLADES,
    "Ty Lee, Artful Acrobat": TY_LEE_ARTFUL_ACROBAT,
    "War Balloon": WAR_BALLOON,
    "Wartime Protestors": WARTIME_PROTESTORS,
    "Yuyan Archers": YUYAN_ARCHERS,
    "Zhao, the Moon Slayer": ZHAO_THE_MOON_SLAYER,
    "Zuko, Exiled Prince": ZUKO_EXILED_PRINCE,
    "Allies at Last": ALLIES_AT_LAST,
    "Avatar Destiny": AVATAR_DESTINY,
    "Badgermole": BADGERMOLE,
    "Badgermole Cub": BADGERMOLE_CUB,
    "The Boulder, Ready to Rumble": THE_BOULDER_READY_TO_RUMBLE,
    "Bumi, King of Three Trials": BUMI_KING_OF_THREE_TRIALS,
    "Cycle of Renewal": CYCLE_OF_RENEWAL,
    "Diligent Zookeeper": DILIGENT_ZOOKEEPER,
    "The Earth King": THE_EARTH_KING,
    "Earth Kingdom General": EARTH_KINGDOM_GENERAL,
    "Earth Rumble": EARTH_RUMBLE,
    "Earthbender Ascension": EARTHBENDER_ASCENSION,
    "Earthbending Lesson": EARTHBENDING_LESSON,
    "Earthen Ally": EARTHEN_ALLY,
    "Elemental Teachings": ELEMENTAL_TEACHINGS,
    "Flopsie, Bumi's Buddy": FLOPSIE_BUMIS_BUDDY,
    "Foggy Swamp Vinebender": FOGGY_SWAMP_VINEBENDER,
    "Great Divide Guide": GREAT_DIVIDE_GUIDE,
    "Haru, Hidden Talent": HARU_HIDDEN_TALENT,
    "Invasion Tactics": INVASION_TACTICS,
    "Kyoshi Island Plaza": KYOSHI_ISLAND_PLAZA,
    "Leaves from the Vine": LEAVES_FROM_THE_VINE,
    "The Legend of Kyoshi": THE_LEGEND_OF_KYOSHI,
    "Origin of Metalbending": ORIGIN_OF_METALBENDING,
    "Ostrich-Horse": OSTRICHHORSE,
    "Pillar Launch": PILLAR_LAUNCH,
    "Raucous Audience": RAUCOUS_AUDIENCE,
    "Rebellious Captives": REBELLIOUS_CAPTIVES,
    "Rockalanche": ROCKALANCHE,
    "Rocky Rebuke": ROCKY_REBUKE,
    "Saber-Tooth Moose-Lion": SABERTOOTH_MOOSELION,
    "Seismic Sense": SEISMIC_SENSE,
    "Shared Roots": SHARED_ROOTS,
    "Sparring Dummy": SPARRING_DUMMY,
    "Toph, the Blind Bandit": TOPH_THE_BLIND_BANDIT,
    "True Ancestry": TRUE_ANCESTRY,
    "Turtle-Duck": TURTLEDUCK,
    "Unlucky Cabbage Merchant": UNLUCKY_CABBAGE_MERCHANT,
    "Walltop Sentries": WALLTOP_SENTRIES,
    "Aang, at the Crossroads": AANG_AT_THE_CROSSROADS,
    "Aang, Swift Savior": AANG_SWIFT_SAVIOR,
    "Abandon Attachments": ABANDON_ATTACHMENTS,
    "Air Nomad Legacy": AIR_NOMAD_LEGACY,
    "Avatar Aang": AVATAR_AANG,
    "Azula, Cunning Usurper": AZULA_CUNNING_USURPER,
    "Beifong's Bounty Hunters": BEIFONGS_BOUNTY_HUNTERS,
    "Bitter Work": BITTER_WORK,
    "Bumi, Unleashed": BUMI_UNLEASHED,
    "Cat-Owl": CATOWL,
    "Cruel Administrator": CRUEL_ADMINISTRATOR,
    "Dai Li Agents": DAI_LI_AGENTS,
    "Dragonfly Swarm": DRAGONFLY_SWARM,
    "Earth Kingdom Soldier": EARTH_KINGDOM_SOLDIER,
    "Earth King's Lieutenant": EARTH_KINGS_LIEUTENANT,
    "Earth Rumble Wrestlers": EARTH_RUMBLE_WRESTLERS,
    "Earth Village Ruffians": EARTH_VILLAGE_RUFFIANS,
    "Fire Lord Azula": FIRE_LORD_AZULA,
    "Fire Lord Zuko": FIRE_LORD_ZUKO,
    "Foggy Swamp Spirit Keeper": FOGGY_SWAMP_SPIRIT_KEEPER,
    "Guru Pathik": GURU_PATHIK,
    "Hama, the Bloodbender": HAMA_THE_BLOODBENDER,
    "Hei Bai, Spirit of Balance": HEI_BAI_SPIRIT_OF_BALANCE,
    "Hermitic Herbalist": HERMITIC_HERBALIST,
    "Iroh, Grand Lotus": IROH_GRAND_LOTUS,
    "Iroh, Tea Master": IROH_TEA_MASTER,
    "Jet, Freedom Fighter": JET_FREEDOM_FIGHTER,
    "Katara, the Fearless": KATARA_THE_FEARLESS,
    "Katara, Water Tribe's Hope": KATARA_WATER_TRIBES_HOPE,
    "The Lion-Turtle": THE_LIONTURTLE,
    "Long Feng, Grand Secretariat": LONG_FENG_GRAND_SECRETARIAT,
    "Messenger Hawk": MESSENGER_HAWK,
    "Ozai, the Phoenix King": OZAI_THE_PHOENIX_KING,
    "Platypus-Bear": PLATYPUSBEAR,
    "Pretending Poxbearers": PRETENDING_POXBEARERS,
    "Professor Zei, Anthropologist": PROFESSOR_ZEI_ANTHROPOLOGIST,
    "Sandbender Scavengers": SANDBENDER_SCAVENGERS,
    "Sokka, Bold Boomeranger": SOKKA_BOLD_BOOMERANGER,
    "Sokka, Lateral Strategist": SOKKA_LATERAL_STRATEGIST,
    "Sokka, Tenacious Tactician": SOKKA_TENACIOUS_TACTICIAN,
    "Suki, Kyoshi Warrior": SUKI_KYOSHI_WARRIOR,
    "Sun Warriors": SUN_WARRIORS,
    "Tolls of War": TOLLS_OF_WAR,
    "Toph, Hardheaded Teacher": TOPH_HARDHEADED_TEACHER,
    "Toph, the First Metalbender": TOPH_THE_FIRST_METALBENDER,
    "Uncle Iroh": UNCLE_IROH,
    "Vindictive Warden": VINDICTIVE_WARDEN,
    "Wandering Musicians": WANDERING_MUSICIANS,
    "White Lotus Reinforcements": WHITE_LOTUS_REINFORCEMENTS,
    "Zhao, Ruthless Admiral": ZHAO_RUTHLESS_ADMIRAL,
    "Zuko, Conflicted": ZUKO_CONFLICTED,
    "Barrels of Blasting Jelly": BARRELS_OF_BLASTING_JELLY,
    "Bender's Waterskin": BENDERS_WATERSKIN,
    "Fire Nation Warship": FIRE_NATION_WARSHIP,
    "Kyoshi Battle Fan": KYOSHI_BATTLE_FAN,
    "Meteor Sword": METEOR_SWORD,
    "Planetarium of Wan Shi Tong": PLANETARIUM_OF_WAN_SHI_TONG,
    "Trusty Boomerang": TRUSTY_BOOMERANG,
    "The Walls of Ba Sing Se": THE_WALLS_OF_BA_SING_SE,
    "White Lotus Tile": WHITE_LOTUS_TILE,
    "Abandoned Air Temple": ABANDONED_AIR_TEMPLE,
    "Agna Qel'a": AGNA_QELA,
    "Airship Engine Room": AIRSHIP_ENGINE_ROOM,
    "Ba Sing Se": BA_SING_SE,
    "Boiling Rock Prison": BOILING_ROCK_PRISON,
    "Fire Nation Palace": FIRE_NATION_PALACE,
    "Foggy Bottom Swamp": FOGGY_BOTTOM_SWAMP,
    "Jasmine Dragon Tea Shop": JASMINE_DRAGON_TEA_SHOP,
    "Kyoshi Village": KYOSHI_VILLAGE,
    "Meditation Pools": MEDITATION_POOLS,
    "Misty Palms Oasis": MISTY_PALMS_OASIS,
    "North Pole Gates": NORTH_POLE_GATES,
    "Omashu City": OMASHU_CITY,
    "Realm of Koh": REALM_OF_KOH,
    "Rumble Arena": RUMBLE_ARENA,
    "Secret Tunnel": SECRET_TUNNEL,
    "Serpent's Pass": SERPENTS_PASS,
    "Sun-Blessed Peak": SUNBLESSED_PEAK,
    "White Lotus Hideout": WHITE_LOTUS_HIDEOUT,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
}

print(f"Loaded {len(AVATAR_TLA_CARDS)} Avatar_The_Last_Airbender cards")
