"""
Duskmourn (DSK) Card Implementations

Real card data fetched from Scryfall API.
277 cards in set.
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


def make_enchantment_creature(name: str, power: int, toughness: int, mana_cost: str, colors: set,
                              subtypes: set = None, supertypes: set = None, text: str = "", setup_interceptors=None):
    """Helper to create enchantment creature card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT, CardType.CREATURE},
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

ACROBATIC_CHEERLEADER = make_creature(
    name="Acrobatic Cheerleader",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Survivor"},
    text="Survival — At the beginning of your second main phase, if this creature is tapped, put a flying counter on it. This ability triggers only once.",
)

CULT_HEALER = make_creature(
    name="Cult Healer",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Doctor", "Human"},
    text="Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, this creature gains lifelink until end of turn.",
)

DAZZLING_THEATER = make_enchantment(
    name="Dazzling Theater",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Dazzling Theater {3}{W}: Creature spells you cast have convoke. (Your creatures can help cast those spells. Each creature you tap while casting a creature spell pays for {1} or one mana of that creature's color.)\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nProp Room {2}{W}: Untap each creature you control during each other player's untap step.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

DOLLMAKERS_SHOP = make_enchantment(
    name="Dollmaker's Shop",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Dollmaker's Shop {1}{W}: Whenever one or more non-Toy creatures you control attack a player, create a 1/1 white Toy artifact creature token.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nPorcelain Gallery {4}{W}{W}: Creatures you control have base power and toughness each equal to the number of creatures you control.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

EMERGE_FROM_THE_COCOON = make_sorcery(
    name="Emerge from the Cocoon",
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    text="Return target creature card from your graveyard to the battlefield. You gain 3 life.",
)

ENDURING_INNOCENCE = make_enchantment_creature(
    name="Enduring Innocence",
    power=2, toughness=1,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Glimmer", "Sheep"},
    text="Lifelink\nWhenever one or more other creatures you control with power 2 or less enter, draw a card. This ability triggers only once each turn.\nWhen Enduring Innocence dies, if it was a creature, return it to the battlefield under its owner's control. It's an enchantment. (It's not a creature.)",
)

ETHEREAL_ARMOR = make_enchantment(
    name="Ethereal Armor",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Enchant creature\nEnchanted creature gets +1/+1 for each enchantment you control and has first strike.",
    subtypes={"Aura"},
)

EXORCISE = make_sorcery(
    name="Exorcise",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Exile target artifact, enchantment, or creature with power 4 or greater.",
)

FEAR_OF_ABDUCTION = make_enchantment_creature(
    name="Fear of Abduction",
    power=5, toughness=5,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Nightmare"},
    text="As an additional cost to cast this spell, exile a creature you control.\nFlying\nWhen this creature enters, exile target creature an opponent controls.\nWhen this creature leaves the battlefield, put each card exiled with it into its owner's hand.",
)

FEAR_OF_IMMOBILITY = make_enchantment_creature(
    name="Fear of Immobility",
    power=4, toughness=4,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Nightmare"},
    text="When this creature enters, tap up to one target creature. If an opponent controls that creature, put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

FEAR_OF_SURVEILLANCE = make_enchantment_creature(
    name="Fear of Surveillance",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Nightmare"},
    text="Vigilance\nWhenever this creature attacks, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

FRIENDLY_GHOST = make_creature(
    name="Friendly Ghost",
    power=2, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
    text="Flying\nWhen this creature enters, target creature gets +2/+4 until end of turn.",
)

GHOSTLY_DANCERS = make_creature(
    name="Ghostly Dancers",
    power=2, toughness=5,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
    text="Flying\nWhen this creature enters, return an enchantment card from your graveyard to your hand or unlock a locked door of a Room you control.\nEerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, create a 3/1 white Spirit creature token with flying.",
)

GLIMMER_SEEKER = make_creature(
    name="Glimmer Seeker",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Survivor"},
    text="Survival — At the beginning of your second main phase, if this creature is tapped, draw a card if you control a Glimmer creature. If you don't control a Glimmer creature, create a 1/1 white Glimmer enchantment creature token.",
)

GRAND_ENTRYWAY = make_enchantment(
    name="Grand Entryway",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Grand Entryway {1}{W}: When you unlock this door, create a 1/1 white Glimmer enchantment creature token.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nElegant Rotunda {2}{W}: When you unlock this door, put a +1/+1 counter on each of up to two target creatures.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

HARDENED_ESCORT = make_creature(
    name="Hardened Escort",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Whenever this creature attacks, another target creature you control gets +1/+0 and gains indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)",
)

JUMP_SCARE = make_instant(
    name="Jump Scare",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Until end of turn, target creature gets +2/+2, gains flying, and becomes a Horror enchantment creature in addition to its other types.",
)

LEYLINE_OF_HOPE = make_enchantment(
    name="Leyline of Hope",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="If this card is in your opening hand, you may begin the game with it on the battlefield.\nIf you would gain life, you gain that much life plus 1 instead.\nAs long as you have at least 7 life more than your starting life total, creatures you control get +2/+2.",
)

LIONHEART_GLIMMER = make_enchantment_creature(
    name="Lionheart Glimmer",
    power=2, toughness=5,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Glimmer"},
    text="Ward {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nWhenever you attack, creatures you control get +1/+1 until end of turn.",
)

LIVING_PHONE = make_artifact_creature(
    name="Living Phone",
    power=2, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Toy"},
    text="When this creature dies, look at the top five cards of your library. You may reveal a creature card with power 2 or less from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
)

OPTIMISTIC_SCAVENGER = make_creature(
    name="Optimistic Scavenger",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, put a +1/+1 counter on target creature.",
)

ORPHANS_OF_THE_WHEAT = make_creature(
    name="Orphans of the Wheat",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human"},
    text="Whenever this creature attacks, tap any number of untapped creatures you control. This creature gets +1/+1 until end of turn for each creature tapped this way.",
)

OVERLORD_OF_THE_MISTMOORS = make_enchantment_creature(
    name="Overlord of the Mistmoors",
    power=6, toughness=6,
    mana_cost="{5}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Avatar", "Horror"},
    text="Impending 4—{2}{W}{W} (If you cast this spell for its impending cost, it enters with four time counters and isn't a creature until the last is removed. At the beginning of your end step, remove a time counter from it.)\nWhenever this permanent enters or attacks, create two 2/1 white Insect creature tokens with flying.",
)

PATCHED_PLAYTHING = make_artifact_creature(
    name="Patched Plaything",
    power=4, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Toy"},
    text="Double strike\nThis creature enters with two -1/-1 counters on it if you cast it from your hand.",
)

POSSESSED_GOAT = make_creature(
    name="Possessed Goat",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Goat"},
    text="{3}, Discard a card: Put three +1/+1 counters on this creature and it becomes a black Demon in addition to its other colors and types. Activate only once.",
)

RELUCTANT_ROLE_MODEL = make_creature(
    name="Reluctant Role Model",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Survivor"},
    text="Survival — At the beginning of your second main phase, if this creature is tapped, put a flying, lifelink, or +1/+1 counter on it.\nWhenever this creature or another creature you control dies, if it had counters on it, put those counters on up to one target creature.",
)

SAVIOR_OF_THE_SMALL = make_creature(
    name="Savior of the Small",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Kor", "Survivor"},
    text="Survival — At the beginning of your second main phase, if this creature is tapped, return target creature card with mana value 3 or less from your graveyard to your hand.",
)

SEIZED_FROM_SLUMBER = make_instant(
    name="Seized from Slumber",
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    text="This spell costs {3} less to cast if it targets a tapped creature.\nDestroy target creature.",
)

SHARDMAGES_RESCUE = make_enchantment(
    name="Shardmage's Rescue",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Flash\nEnchant creature you control\nAs long as this Aura entered this turn, enchanted creature has hexproof.\nEnchanted creature gets +1/+1.",
    subtypes={"Aura"},
)

SHELTERED_BY_GHOSTS = make_enchantment(
    name="Sheltered by Ghosts",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Enchant creature you control\nWhen this Aura enters, exile target nonland permanent an opponent controls until this Aura leaves the battlefield.\nEnchanted creature gets +1/+0 and has lifelink and ward {2}.",
    subtypes={"Aura"},
)

SHEPHERDING_SPIRITS = make_creature(
    name="Shepherding Spirits",
    power=4, toughness=5,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
    text="Flying\nPlainscycling {2} ({2}, Discard this card: Search your library for a Plains card, reveal it, put it into your hand, then shuffle.)",
)

SPLIT_UP = make_sorcery(
    name="Split Up",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Destroy all tapped creatures.\n• Destroy all untapped creatures.",
)

SPLITSKIN_DOLL = make_artifact_creature(
    name="Splitskin Doll",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Toy"},
    text="When this creature enters, draw a card. Then discard a card unless you control another creature with power 2 or less.",
)

SURGICAL_SUITE = make_enchantment(
    name="Surgical Suite",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Surgical Suite {1}{W}: When you unlock this door, return target creature card with mana value 3 or less from your graveyard to the battlefield.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nHospital Room {3}{W}: Whenever you attack, put a +1/+1 counter on target attacking creature.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

TOBY_BEASTIE_BEFRIENDER = make_creature(
    name="Toby, Beastie Befriender",
    power=1, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="When Toby enters, create a 4/4 white Beast creature token with \"This token can't attack or block alone.\"\nAs long as you control four or more creature tokens, creature tokens you control have flying.",
)

TRAPPED_IN_THE_SCREEN = make_enchantment(
    name="Trapped in the Screen",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Ward {2} (Whenever this enchantment becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nWhen this enchantment enters, exile target artifact, creature, or enchantment an opponent controls until this enchantment leaves the battlefield.",
)

UNIDENTIFIED_HOVERSHIP = make_artifact(
    name="Unidentified Hovership",
    mana_cost="{1}{W}{W}",
    text="Flying\nWhen this Vehicle enters, exile up to one target creature with toughness 5 or less.\nWhen this Vehicle leaves the battlefield, the exiled card's owner manifests dread.\nCrew 1",
    subtypes={"Vehicle"},
)

UNSETTLING_TWINS = make_creature(
    name="Unsettling Twins",
    power=2, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human"},
    text="When this creature enters, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
)

UNWANTED_REMAKE = make_instant(
    name="Unwanted Remake",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Destroy target creature. Its controller manifests dread. (That player looks at the top two cards of their library, then puts one onto the battlefield face down as a 2/2 creature and the other into their graveyard. If it's a creature card, it can be turned face up any time for its mana cost.)",
)

VETERAN_SURVIVOR = make_creature(
    name="Veteran Survivor",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Survivor"},
    text="Survival — At the beginning of your second main phase, if this creature is tapped, exile up to one target card from a graveyard.\nAs long as there are three or more cards exiled with this creature, it gets +3/+3 and has hexproof. (It can't be the target of spells or abilities your opponents control.)",
)

THE_WANDERING_RESCUER = make_creature(
    name="The Wandering Rescuer",
    power=3, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble", "Samurai"},
    supertypes={"Legendary"},
    text="Flash\nConvoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nDouble strike\nOther tapped creatures you control have hexproof.",
)

ABHORRENT_OCULUS = make_creature(
    name="Abhorrent Oculus",
    power=5, toughness=5,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Eye"},
    text="As an additional cost to cast this spell, exile six cards from your graveyard.\nFlying\nAt the beginning of each opponent's upkeep, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
)

BOTTOMLESS_POOL = make_enchantment(
    name="Bottomless Pool",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Bottomless Pool {U}: When you unlock this door, return up to one target creature to its owner's hand.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nLocker Room {4}{U}: Whenever one or more creatures you control deal combat damage to a player, draw a card.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

CENTRAL_ELEVATOR = make_enchantment(
    name="Central Elevator",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Central Elevator {3}{U}: When you unlock this door, search your library for a Room card that doesn't have the same name as a Room you control, reveal it, put it into your hand, then shuffle.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nPromising Stairs {2}{U}: At the beginning of your upkeep, surveil 1. You win the game if there are eight or more different names among unlocked doors of Rooms you control.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

CLAMMY_PROWLER = make_enchantment_creature(
    name="Clammy Prowler",
    power=2, toughness=5,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Horror"},
    text="Whenever this creature attacks, another target attacking creature can't be blocked this turn.",
)

CREEPING_PEEPER = make_creature(
    name="Creeping Peeper",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Eye"},
    text="{T}: Add {U}. Spend this mana only to cast an enchantment spell, unlock a door, or turn a permanent face up.",
)

CURSED_WINDBREAKER = make_artifact(
    name="Cursed Windbreaker",
    mana_cost="{2}{U}",
    text="When this Equipment enters, manifest dread, then attach this Equipment to that creature. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)\nEquipped creature has flying.\nEquip {3}",
    subtypes={"Equipment"},
)

DAGGERMAW_MEGALODON = make_creature(
    name="Daggermaw Megalodon",
    power=5, toughness=7,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Shark"},
    text="Vigilance\nIslandcycling {2} ({2}, Discard this card: Search your library for an Island card, reveal it, put it into your hand, then shuffle.)",
)

DONT_MAKE_A_SOUND = make_instant(
    name="Don't Make a Sound",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {2}. If they do, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
)

DUSKMOURNS_DOMINATION = make_enchantment(
    name="Duskmourn's Domination",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Enchant creature\nYou control enchanted creature.\nEnchanted creature gets -3/-0 and loses all abilities.",
    subtypes={"Aura"},
)

ENDURING_CURIOSITY = make_enchantment_creature(
    name="Enduring Curiosity",
    power=4, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Cat", "Glimmer"},
    text="Flash\nWhenever a creature you control deals combat damage to a player, draw a card.\nWhen Enduring Curiosity dies, if it was a creature, return it to the battlefield under its owner's control. It's an enchantment. (It's not a creature.)",
)

ENTER_THE_ENIGMA = make_sorcery(
    name="Enter the Enigma",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature can't be blocked this turn.\nDraw a card.",
)

ENTITY_TRACKER = make_creature(
    name="Entity Tracker",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout"},
    text="Flash\nEerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, draw a card.",
)

ERRATIC_APPARITION = make_creature(
    name="Erratic Apparition",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Flying, vigilance\nEerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, this creature gets +1/+1 until end of turn.",
)

FEAR_OF_FAILED_TESTS = make_enchantment_creature(
    name="Fear of Failed Tests",
    power=2, toughness=7,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Nightmare"},
    text="Whenever this creature deals combat damage to a player, draw that many cards.",
)

FEAR_OF_FALLING = make_enchantment_creature(
    name="Fear of Falling",
    power=4, toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Nightmare"},
    text="Flying\nWhenever this creature attacks, target creature defending player controls gets -2/-0 and loses flying until your next turn.",
)

FEAR_OF_IMPOSTORS = make_enchantment_creature(
    name="Fear of Impostors",
    power=3, toughness=2,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Nightmare"},
    text="Flash\nWhen this creature enters, counter target spell. Its controller manifests dread. (That player looks at the top two cards of their library, then puts one onto the battlefield face down as a 2/2 creature and the other into their graveyard. If it's a creature card, it can be turned face up any time for its mana cost.)",
)

FEAR_OF_ISOLATION = make_enchantment_creature(
    name="Fear of Isolation",
    power=2, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Nightmare"},
    text="As an additional cost to cast this spell, return a permanent you control to its owner's hand.\nFlying",
)

FLOODPITS_DROWNER = make_creature(
    name="Floodpits Drowner",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk"},
    text="Flash\nVigilance\nWhen this creature enters, tap target creature an opponent controls and put a stun counter on it.\n{1}{U}, {T}: Shuffle this creature and target creature with a stun counter on it into their owners' libraries.",
)

GET_OUT = make_instant(
    name="Get Out",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Choose one —\n• Counter target creature or enchantment spell.\n• Return one or two target creatures and/or enchantments you own to your hand.",
)

GHOSTLY_KEYBEARER = make_creature(
    name="Ghostly Keybearer",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Flying\nWhenever this creature deals combat damage to a player, unlock a locked door of up to one target Room you control.",
)

GLIMMERBURST = make_instant(
    name="Glimmerburst",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Draw two cards. Create a 1/1 white Glimmer enchantment creature token.",
)

LEYLINE_OF_TRANSFORMATION = make_enchantment(
    name="Leyline of Transformation",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="If this card is in your opening hand, you may begin the game with it on the battlefield.\nAs this enchantment enters, choose a creature type.\nCreatures you control are the chosen type in addition to their other types. The same is true for creature spells you control and creature cards you own that aren't on the battlefield.",
)

MARINA_VENDRELLS_GRIMOIRE = make_artifact(
    name="Marina Vendrell's Grimoire",
    mana_cost="{5}{U}",
    text="When Marina Vendrell's Grimoire enters, if you cast it, draw five cards.\nYou have no maximum hand size and don't lose the game for having 0 or less life.\nWhenever you gain life, draw that many cards.\nWhenever you lose life, discard that many cards. Then if you have no cards in hand, you lose the game.",
    supertypes={"Legendary"},
)

MEAT_LOCKER = make_enchantment(
    name="Meat Locker",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Meat Locker {2}{U}: When you unlock this door, tap up to one target creature and put two stun counters on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nDrowned Diner {3}{U}{U}: When you unlock this door, draw three cards, then discard a card.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

THE_MINDSKINNER = make_enchantment_creature(
    name="The Mindskinner",
    power=10, toughness=1,
    mana_cost="{U}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Nightmare"},
    supertypes={"Legendary"},
    text="The Mindskinner can't be blocked.\nIf a source you control would deal damage to an opponent, prevent that damage and each opponent mills that many cards.",
)

MIRROR_ROOM = make_enchantment(
    name="Mirror Room",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Mirror Room {2}{U}: When you unlock this door, create a token that's a copy of target creature you control, except it's a Reflection in addition to its other creature types.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nFractured Realm {5}{U}{U}: If a triggered ability of a permanent you control triggers, that ability triggers an additional time.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

OVERLORD_OF_THE_FLOODPITS = make_enchantment_creature(
    name="Overlord of the Floodpits",
    power=5, toughness=3,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Avatar", "Horror"},
    text="Impending 4—{1}{U}{U} (If you cast this spell for its impending cost, it enters with four time counters and isn't a creature until the last is removed. At the beginning of your end step, remove a time counter from it.)\nFlying\nWhenever this permanent enters or attacks, draw two cards, then discard a card.",
)

PARANORMAL_ANALYST = make_creature(
    name="Paranormal Analyst",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Human"},
    text="Whenever you manifest dread, put a card you put into your graveyard this way into your hand.",
)

PIRANHA_FLY = make_creature(
    name="Piranha Fly",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Fish", "Insect"},
    text="Flying\nThis creature enters tapped.",
)

SCRABBLING_SKULLCRAB = make_creature(
    name="Scrabbling Skullcrab",
    power=0, toughness=3,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Crab", "Skeleton"},
    text="Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, target player mills two cards. (They put the top two cards of their library into their graveyard.)",
)

SILENT_HALLCREEPER = make_enchantment_creature(
    name="Silent Hallcreeper",
    power=1, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Horror"},
    text="This creature can't be blocked.\nWhenever this creature deals combat damage to a player, choose one that hasn't been chosen —\n• Put two +1/+1 counters on this creature.\n• Draw a card.\n• This creature becomes a copy of another target creature you control.",
)

STALKED_RESEARCHER = make_creature(
    name="Stalked Researcher",
    power=3, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Defender\nEerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, this creature can attack this turn as though it didn't have defender.",
)

STAY_HIDDEN_STAY_SILENT = make_enchantment(
    name="Stay Hidden, Stay Silent",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Enchant creature\nWhen this Aura enters, tap enchanted creature.\nEnchanted creature doesn't untap during its controller's untap step.\n{4}{U}{U}: Shuffle enchanted creature into its owner's library, then manifest dread. Activate only as a sorcery.",
    subtypes={"Aura"},
)

THE_TALE_OF_TAMIYO = make_enchantment(
    name="The Tale of Tamiyo",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after IV.)\nI, II, III — Mill two cards. If two cards that share a card type were milled this way, draw a card and repeat this process.\nIV — Exile any number of target instant, sorcery, and/or Tamiyo planeswalker cards from your graveyard. Copy them. You may cast any number of the copies.",
    subtypes={"Saga"},
    supertypes={"Legendary"},
)

TUNNEL_SURVEYOR = make_creature(
    name="Tunnel Surveyor",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Human"},
    text="When this creature enters, create a 1/1 white Glimmer enchantment creature token.",
)

TWIST_REALITY = make_instant(
    name="Twist Reality",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Choose one —\n• Counter target spell.\n• Manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
)

UNABLE_TO_SCREAM = make_enchantment(
    name="Unable to Scream",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Enchant creature\nEnchanted creature loses all abilities and is a Toy artifact creature with base power and toughness 0/2 in addition to its other types.\nAs long as enchanted creature is face down, it can't be turned face up.",
    subtypes={"Aura"},
)

UNDERWATER_TUNNEL = make_enchantment(
    name="Underwater Tunnel",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Underwater Tunnel {U}: When you unlock this door, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nSlimy Aquarium {3}{U}: When you unlock this door, manifest dread, then put a +1/+1 counter on that creature.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

UNNERVING_GRASP = make_sorcery(
    name="Unnerving Grasp",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Return up to one target nonland permanent to its owner's hand. Manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
)

UNWILLING_VESSEL = make_creature(
    name="Unwilling Vessel",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Vigilance\nEerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, put a possession counter on this creature.\nWhen this creature dies, create an X/X blue Spirit creature token with flying, where X is the number of counters on this creature.",
)

VANISH_FROM_SIGHT = make_instant(
    name="Vanish from Sight",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Target nonland permanent's owner puts it on their choice of the top or bottom of their library. Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

APPENDAGE_AMALGAM = make_enchantment_creature(
    name="Appendage Amalgam",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="Flash\nWhenever this creature attacks, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

BALEMURK_LEECH = make_creature(
    name="Balemurk Leech",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Leech"},
    text="Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, each opponent loses 1 life.",
)

CACKLING_SLASHER = make_creature(
    name="Cackling Slasher",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Human"},
    text="Deathtouch\nThis creature enters with a +1/+1 counter on it if a creature died this turn.",
)

COME_BACK_WRONG = make_sorcery(
    name="Come Back Wrong",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. If a creature card is put into a graveyard this way, return it to the battlefield under your control. Sacrifice it at the beginning of your next end step.",
)

COMMUNE_WITH_EVIL = make_sorcery(
    name="Commune with Evil",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Look at the top four cards of your library. Put one of them into your hand and the rest into your graveyard. You gain 3 life.",
)

CRACKED_SKULL = make_enchantment(
    name="Cracked Skull",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Enchant creature\nWhen this Aura enters, look at target player's hand. You may choose a nonland card from it. That player discards that card.\nWhen enchanted creature is dealt damage, destroy it.",
    subtypes={"Aura"},
)

CYNICAL_LONER = make_creature(
    name="Cynical Loner",
    power=3, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Survivor"},
    text="This creature can't be blocked by Glimmers.\nSurvival — At the beginning of your second main phase, if this creature is tapped, you may search your library for a card, put it into your graveyard, then shuffle.",
)

DASHING_BLOODSUCKER = make_creature(
    name="Dashing Bloodsucker",
    power=2, toughness=5,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Warrior"},
    text="Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, this creature gets +2/+0 and gains lifelink until end of turn.",
)

DEFILED_CRYPT = make_enchantment(
    name="Defiled Crypt",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Defiled Crypt {3}{B}: Whenever one or more cards leave your graveyard, create a 2/2 black Horror enchantment creature token. This ability triggers only once each turn.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nCadaver Lab {B}: When you unlock this door, return target creature card from your graveyard to your hand.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

DEMONIC_COUNSEL = make_sorcery(
    name="Demonic Counsel",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Search your library for a Demon card, reveal it, put it into your hand, then shuffle.\nDelirium — If there are four or more card types among cards in your graveyard, instead search your library for any card, put it into your hand, then shuffle.",
)

DERELICT_ATTIC = make_enchantment(
    name="Derelict Attic",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Derelict Attic {2}{B}: When you unlock this door, you draw two cards and you lose 2 life.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nWidow's Walk {3}{B}: Whenever a creature you control attacks alone, it gets +1/+0 and gains deathtouch until end of turn.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

DOOMSDAY_EXCRUCIATOR = make_creature(
    name="Doomsday Excruciator",
    power=6, toughness=6,
    mana_cost="{B}{B}{B}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Flying\nWhen this creature enters, if it was cast, each player exiles all but the bottom six cards of their library face down.\nAt the beginning of your upkeep, draw a card.",
)

ENDURING_TENACITY = make_enchantment_creature(
    name="Enduring Tenacity",
    power=4, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Glimmer", "Snake"},
    text="Whenever you gain life, target opponent loses that much life.\nWhen Enduring Tenacity dies, if it was a creature, return it to the battlefield under its owner's control. It's an enchantment. (It's not a creature.)",
)

FANATIC_OF_THE_HARROWING = make_creature(
    name="Fanatic of the Harrowing",
    power=2, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Human"},
    text="When this creature enters, each player discards a card. If you discarded a card this way, draw a card.",
)

FEAR_OF_LOST_TEETH = make_enchantment_creature(
    name="Fear of Lost Teeth",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare"},
    text="When this creature dies, it deals 1 damage to any target and you gain 1 life.",
)

FEAR_OF_THE_DARK = make_enchantment_creature(
    name="Fear of the Dark",
    power=5, toughness=5,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare"},
    text="Whenever this creature attacks, if defending player controls no Glimmer creatures, it gains menace and deathtouch until end of turn. (A creature with menace can't be blocked except by two or more creatures.)",
)

FINAL_VENGEANCE = make_sorcery(
    name="Final Vengeance",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, sacrifice a creature or enchantment.\nExile target creature.",
)

FUNERAL_ROOM = make_enchantment(
    name="Funeral Room",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Funeral Room {2}{B}: Whenever a creature you control dies, each opponent loses 1 life and you gain 1 life.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nAwakening Hall {6}{B}{B}: When you unlock this door, return all creature cards from your graveyard to the battlefield.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

GIVE_IN_TO_VIOLENCE = make_instant(
    name="Give In to Violence",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets +2/+2 and gains lifelink until end of turn.",
)

GRIEVOUS_WOUND = make_enchantment(
    name="Grievous Wound",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Enchant player\nEnchanted player can't gain life.\nWhenever enchanted player is dealt damage, they lose half their life, rounded up.",
    subtypes={"Aura"},
)

INNOCUOUS_RAT = make_creature(
    name="Innocuous Rat",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rat"},
    text="When this creature dies, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
)

KILLERS_MASK = make_artifact(
    name="Killer's Mask",
    mana_cost="{2}{B}",
    text="When this Equipment enters, manifest dread, then attach this Equipment to that creature. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)\nEquipped creature has menace.\nEquip {2}",
    subtypes={"Equipment"},
)

LETS_PLAY_A_GAME = make_sorcery(
    name="Let's Play a Game",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Delirium — Choose one. If there are four or more card types among cards in your graveyard, choose one or more instead.\n• Creatures your opponents control get -1/-1 until end of turn.\n• Each opponent discards two cards.\n• Each opponent loses 3 life and you gain 3 life.",
)

LEYLINE_OF_THE_VOID = make_enchantment(
    name="Leyline of the Void",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="If this card is in your opening hand, you may begin the game with it on the battlefield.\nIf a card would be put into an opponent's graveyard from anywhere, exile it instead.",
)

LIVE_OR_DIE = make_instant(
    name="Live or Die",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Choose one —\n• Return target creature card from your graveyard to the battlefield.\n• Destroy target creature.",
)

MEATHOOK_MASSACRE_II = make_enchantment(
    name="Meathook Massacre II",
    mana_cost="{X}{X}{B}{B}{B}{B}",
    colors={Color.BLACK},
    text="When Meathook Massacre II enters, each player sacrifices X creatures of their choice.\nWhenever a creature you control dies, you may pay 3 life. If you do, return that card under your control with a finality counter on it.\nWhenever a creature an opponent controls dies, they may pay 3 life. If they don't, return that card under your control with a finality counter on it.",
    supertypes={"Legendary"},
)

MIASMA_DEMON = make_creature(
    name="Miasma Demon",
    power=5, toughness=4,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Flying\nWhen this creature enters, you may discard any number of cards. When you do, up to that many target creatures each get -2/-2 until end of turn.",
)

MURDER = make_instant(
    name="Murder",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature.",
)

NOWHERE_TO_RUN = make_enchantment(
    name="Nowhere to Run",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Flash\nWhen this enchantment enters, target creature an opponent controls gets -3/-3 until end of turn.\nCreatures your opponents control can be the targets of spells and abilities as though they didn't have hexproof. Ward abilities of those creatures don't trigger.",
)

OSSEOUS_STICKTWISTER = make_artifact_creature(
    name="Osseous Sticktwister",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Scarecrow"},
    text="Lifelink\nDelirium — At the beginning of your end step, if there are four or more card types among cards in your graveyard, each opponent may sacrifice a nonland permanent of their choice or discard a card. Then this creature deals damage equal to its power to each opponent who didn't sacrifice a permanent or discard a card this way.",
)

OVERLORD_OF_THE_BALEMURK = make_enchantment_creature(
    name="Overlord of the Balemurk",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Avatar", "Horror"},
    text="Impending 5—{1}{B} (If you cast this spell for its impending cost, it enters with five time counters and isn't a creature until the last is removed. At the beginning of your end step, remove a time counter from it.)\nWhenever this permanent enters or attacks, mill four cards, then you may return a non-Avatar creature card or a planeswalker card from your graveyard to your hand.",
)

POPULAR_EGOTIST = make_creature(
    name="Popular Egotist",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="{1}{B}, Sacrifice another creature or enchantment: This creature gains indestructible until end of turn. Tap it. (Damage and effects that say \"destroy\" don't destroy it.)\nWhenever you sacrifice a permanent, target opponent loses 1 life and you gain 1 life.",
)

RESURRECTED_CULTIST = make_creature(
    name="Resurrected Cultist",
    power=4, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Human"},
    text="Delirium — {2}{B}{B}: Return this card from your graveyard to the battlefield with a finality counter on it. Activate only if there are four or more card types among cards in your graveyard and only as a sorcery. (If a creature with a finality counter on it would die, exile it instead.)",
)

SPECTRAL_SNATCHER = make_creature(
    name="Spectral Snatcher",
    power=6, toughness=5,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Ward—Discard a card. (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player discards a card.)\nSwampcycling {2} ({2}, Discard this card: Search your library for a Swamp card, reveal it, put it into your hand, then shuffle.)",
)

SPOROGENIC_INFECTION = make_enchantment(
    name="Sporogenic Infection",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Enchant creature\nWhen this Aura enters, target player sacrifices a creature of their choice other than enchanted creature.\nWhen enchanted creature is dealt damage, destroy it.",
    subtypes={"Aura"},
)

UNHOLY_ANNEX = make_enchantment(
    name="Unholy Annex",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Unholy Annex {2}{B}: At the beginning of your end step, draw a card. If you control a Demon, each opponent loses 2 life and you gain 2 life. Otherwise, you lose 2 life.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nRitual Chamber {3}{B}{B}: When you unlock this door, create a 6/6 black Demon creature token with flying.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

UNSTOPPABLE_SLASHER = make_creature(
    name="Unstoppable Slasher",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Zombie"},
    text="Deathtouch\nWhenever this creature deals combat damage to a player, they lose half their life, rounded up.\nWhen this creature dies, if it had no counters on it, return it to the battlefield tapped under its owner's control with two stun counters on it.",
)

VALGAVOTH_TERROR_EATER = make_creature(
    name="Valgavoth, Terror Eater",
    power=9, toughness=9,
    mana_cost="{6}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Elder"},
    supertypes={"Legendary"},
    text="Flying, lifelink\nWard—Sacrifice three nonland permanents.\nIf a card you didn't control would be put into an opponent's graveyard from anywhere, exile it instead.\nDuring your turn, you may play cards exiled with Valgavoth. If you cast a spell this way, pay life equal to its mana value rather than pay its mana cost.",
)

VALGAVOTHS_FAITHFUL = make_creature(
    name="Valgavoth's Faithful",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Human"},
    text="{3}{B}, Sacrifice this creature: Return target creature card from your graveyard to the battlefield. Activate only as a sorcery.",
)

VILE_MUTILATOR = make_creature(
    name="Vile Mutilator",
    power=6, toughness=5,
    mana_cost="{5}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="As an additional cost to cast this spell, sacrifice a creature or enchantment.\nFlying, trample\nWhen this creature enters, each opponent sacrifices a nontoken enchantment of their choice, then sacrifices a nontoken creature of their choice.",
)

WINTERS_INTERVENTION = make_instant(
    name="Winter's Intervention",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Winter's Intervention deals 2 damage to target creature. You gain 2 life.",
)

WITHERING_TORMENT = make_instant(
    name="Withering Torment",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target creature or enchantment. You lose 2 life.",
)

BEDHEAD_BEASTIE = make_creature(
    name="Bedhead Beastie",
    power=5, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Beast"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nMountaincycling {2} ({2}, Discard this card: Search your library for a Mountain card, reveal it, put it into your hand, then shuffle.)",
)

BETRAYERS_BARGAIN = make_instant(
    name="Betrayer's Bargain",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="As an additional cost to cast this spell, sacrifice a creature or enchantment or pay {2}.\nBetrayer's Bargain deals 5 damage to target creature. If that creature would die this turn, exile it instead.",
)

BOILERBILGES_RIPPER = make_creature(
    name="Boilerbilges Ripper",
    power=4, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Assassin", "Human"},
    text="When this creature enters, you may sacrifice another creature or enchantment. When you do, this creature deals 2 damage to any target.",
)

CHAINSAW = make_artifact(
    name="Chainsaw",
    mana_cost="{1}{R}",
    text="When this Equipment enters, it deals 3 damage to up to one target creature.\nWhenever one or more creatures die, put a rev counter on this Equipment.\nEquipped creature gets +X/+0, where X is the number of rev counters on this Equipment.\nEquip {3}",
    subtypes={"Equipment"},
)

CHARRED_FOYER = make_enchantment(
    name="Charred Foyer",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Charred Foyer {3}{R}: At the beginning of your upkeep, exile the top card of your library. You may play it this turn.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nWarped Space {4}{R}{R}: Once each turn, you may pay {0} rather than pay the mana cost for a spell you cast from exile.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

CLOCKWORK_PERCUSSIONIST = make_artifact_creature(
    name="Clockwork Percussionist",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Monkey", "Toy"},
    text="Haste\nWhen this creature dies, exile the top card of your library. You may play it until the end of your next turn.",
)

CURSED_RECORDING = make_artifact(
    name="Cursed Recording",
    mana_cost="{2}{R}{R}",
    text="Whenever you cast an instant or sorcery spell, put a time counter on this artifact. Then if there are seven or more time counters on it, remove those counters and it deals 20 damage to you.\n{T}: When you next cast an instant or sorcery spell this turn, copy that spell. You may choose new targets for the copy.",
)

DIVERSION_SPECIALIST = make_creature(
    name="Diversion Specialist",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\n{1}, Sacrifice another creature or enchantment: Exile the top card of your library. You may play it this turn.",
)

ENDURING_COURAGE = make_enchantment_creature(
    name="Enduring Courage",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Dog", "Glimmer"},
    text="Whenever another creature you control enters, it gets +2/+0 and gains haste until end of turn.\nWhen Enduring Courage dies, if it was a creature, return it to the battlefield under its owner's control. It's an enchantment. (It's not a creature.)",
)

FEAR_OF_BEING_HUNTED = make_enchantment_creature(
    name="Fear of Being Hunted",
    power=4, toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Nightmare"},
    text="Haste\nThis creature must be blocked if able.",
)

FEAR_OF_BURNING_ALIVE = make_enchantment_creature(
    name="Fear of Burning Alive",
    power=4, toughness=4,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Nightmare"},
    text="When this creature enters, it deals 4 damage to each opponent.\nDelirium — Whenever a source you control deals noncombat damage to an opponent, if there are four or more card types among cards in your graveyard, this creature deals that amount of damage to target creature that player controls.",
)

FEAR_OF_MISSING_OUT = make_enchantment_creature(
    name="Fear of Missing Out",
    power=2, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Nightmare"},
    text="When this creature enters, discard a card, then draw a card.\nDelirium — Whenever this creature attacks for the first time each turn, if there are four or more card types among cards in your graveyard, untap target creature. After this phase, there is an additional combat phase.",
)

GLASSWORKS = make_enchantment(
    name="Glassworks",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Glassworks {2}{R}: When you unlock this door, this Room deals 4 damage to target creature an opponent controls.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nShattered Yard {4}{R}: At the beginning of your end step, this Room deals 1 damage to each opponent.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

GRAB_THE_PRIZE = make_sorcery(
    name="Grab the Prize",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="As an additional cost to cast this spell, discard a card.\nDraw two cards. If the discarded card wasn't a land card, Grab the Prize deals 2 damage to each opponent.",
)

HAND_THAT_FEEDS = make_creature(
    name="Hand That Feeds",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Mutant"},
    text="Delirium — Whenever this creature attacks while there are four or more card types among cards in your graveyard, it gets +2/+0 and gains menace until end of turn. (It can't be blocked except by two or more creatures.)",
)

IMPOSSIBLE_INFERNO = make_instant(
    name="Impossible Inferno",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="Impossible Inferno deals 6 damage to target creature.\nDelirium — If there are four or more card types among cards in your graveyard, exile the top card of your library. You may play it until the end of your next turn.",
)

INFERNAL_PHANTOM = make_creature(
    name="Infernal Phantom",
    power=2, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Spirit"},
    text="Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, this creature gets +2/+0 until end of turn.\nWhen this creature dies, it deals damage equal to its power to any target.",
)

IRREVERENT_GREMLIN = make_creature(
    name="Irreverent Gremlin",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Gremlin"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhenever another creature you control with power 2 or less enters, you may discard a card. If you do, draw a card. Do this only once each turn.",
)

LEYLINE_OF_RESONANCE = make_enchantment(
    name="Leyline of Resonance",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="If this card is in your opening hand, you may begin the game with it on the battlefield.\nWhenever you cast an instant or sorcery spell that targets only a single creature you control, copy that spell. You may choose new targets for the copy.",
)

ALEYLINE_OF_RESONANCE = make_enchantment(
    name="A-Leyline of Resonance",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="If this card is in your opening hand, you may begin the game with it on the battlefield.\nWhenever you cast an instant or sorcery spell that targets only a single creature you control, you may pay {1}. If you do, copy that spell. You may choose new targets for the copy.",
)

MOST_VALUABLE_SLAYER = make_creature(
    name="Most Valuable Slayer",
    power=2, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="Whenever you attack, target attacking creature gets +1/+0 and gains first strike until end of turn.",
)

NORIN_SWIFT_SURVIVALIST = make_creature(
    name="Norin, Swift Survivalist",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Coward", "Human"},
    supertypes={"Legendary"},
    text="Norin can't block.\nWhenever a creature you control becomes blocked, you may exile it. You may play that card from exile this turn.",
)

OVERLORD_OF_THE_BOILERBILGES = make_enchantment_creature(
    name="Overlord of the Boilerbilges",
    power=5, toughness=5,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Avatar", "Horror"},
    text="Impending 4—{2}{R}{R} (If you cast this spell for its impending cost, it enters with four time counters and isn't a creature until the last is removed. At the beginning of your end step, remove a time counter from it.)\nWhenever this permanent enters or attacks, it deals 4 damage to any target.",
)

PAINTERS_STUDIO = make_enchantment(
    name="Painter's Studio",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Painter's Studio {2}{R}: When you unlock this door, exile the top two cards of your library. You may play them until the end of your next turn.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nDefaced Gallery {1}{R}: Whenever you attack, attacking creatures you control get +1/+0 until end of turn.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

PIGGY_BANK = make_artifact_creature(
    name="Piggy Bank",
    power=3, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Boar", "Toy"},
    text="When this creature dies, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

PYROCLASM = make_sorcery(
    name="Pyroclasm",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Pyroclasm deals 2 damage to each creature.",
)

RAGGED_PLAYMATE = make_artifact_creature(
    name="Ragged Playmate",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Toy"},
    text="{1}, {T}: Target creature with power 2 or less can't be blocked this turn.",
)

RAMPAGING_SOULRAGER = make_creature(
    name="Rampaging Soulrager",
    power=1, toughness=4,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Spirit"},
    text="This creature gets +3/+0 as long as there are two or more unlocked doors among Rooms you control.",
)

RAZORKIN_HORDECALLER = make_creature(
    name="Razorkin Hordecaller",
    power=4, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Berserker", "Clown", "Human"},
    text="Haste\nWhenever you attack, create a 1/1 red Gremlin creature token.",
)

RAZORKIN_NEEDLEHEAD = make_creature(
    name="Razorkin Needlehead",
    power=2, toughness=2,
    mana_cost="{R}{R}",
    colors={Color.RED},
    subtypes={"Assassin", "Human"},
    text="This creature has first strike during your turn.\nWhenever an opponent draws a card, this creature deals 1 damage to them.",
)

RIPCHAIN_RAZORKIN = make_creature(
    name="Ripchain Razorkin",
    power=5, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Berserker", "Human"},
    text="Reach\n{2}{R}, Sacrifice a land: Draw a card.",
)

THE_ROLLERCRUSHER_RIDE = make_enchantment(
    name="The Rollercrusher Ride",
    mana_cost="{X}{2}{R}",
    colors={Color.RED},
    text="Delirium — If a source you control would deal noncombat damage to a permanent or player while there are four or more card types among cards in your graveyard, it deals double that damage instead.\nWhen The Rollercrusher Ride enters, it deals X damage to each of up to X target creatures.",
    supertypes={"Legendary"},
)

SCORCHING_DRAGONFIRE = make_instant(
    name="Scorching Dragonfire",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Scorching Dragonfire deals 3 damage to target creature or planeswalker. If that creature or planeswalker would die this turn, exile it instead.",
)

SCREAMING_NEMESIS = make_creature(
    name="Screaming Nemesis",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Spirit"},
    text="Haste\nWhenever this creature is dealt damage, it deals that much damage to any other target. If a player is dealt damage this way, they can't gain life for the rest of the game.",
)

TICKET_BOOTH = make_enchantment(
    name="Ticket Booth",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Ticket Booth {2}{R}: When you unlock this door, manifest dread.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nTunnel of Hate {4}{R}{R}: Whenever you attack, target attacking creature gains double strike until end of turn.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

TRIAL_OF_AGONY = make_sorcery(
    name="Trial of Agony",
    mana_cost="{R}",
    colors={Color.RED},
    text="Choose two target creatures controlled by the same opponent. That player chooses one of those creatures. Trial of Agony deals 5 damage to that creature, and the other can't block this turn.",
)

TURN_INSIDE_OUT = make_instant(
    name="Turn Inside Out",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 until end of turn. When it dies this turn, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
)

UNTIMELY_MALFUNCTION = make_instant(
    name="Untimely Malfunction",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Choose one —\n• Destroy target artifact.\n• Change the target of target spell or ability with a single target.\n• One or two target creatures can't block this turn.",
)

VENGEFUL_POSSESSION = make_sorcery(
    name="Vengeful Possession",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Gain control of target creature until end of turn. Untap it. It gains haste until end of turn. You may discard a card. If you do, draw a card.",
)

VICIOUS_CLOWN = make_creature(
    name="Vicious Clown",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Clown", "Human"},
    text="Whenever another creature you control with power 2 or less enters, this creature gets +2/+0 until end of turn.",
)

VIOLENT_URGE = make_instant(
    name="Violent Urge",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +1/+0 and gains first strike until end of turn.\nDelirium — If there are four or more card types among cards in your graveyard, that creature gains double strike until end of turn.",
)

WALTZ_OF_RAGE = make_sorcery(
    name="Waltz of Rage",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Target creature you control deals damage equal to its power to each other creature. Until end of turn, whenever a creature you control dies, exile the top card of your library. You may play it until the end of your next turn.",
)

ALTANAK_THE_THRICECALLED = make_creature(
    name="Altanak, the Thrice-Called",
    power=9, toughness=9,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Insect"},
    supertypes={"Legendary"},
    text="Trample\nWhenever Altanak becomes the target of a spell or ability an opponent controls, draw a card.\n{1}{G}, Discard this card: Return target land card from your graveyard to the battlefield tapped.",
)

ANTHROPEDE = make_creature(
    name="Anthropede",
    power=3, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Insect"},
    text="Reach\nWhen this creature enters, you may discard a card or pay {2}. When you do, destroy target Room.",
)

BALUSTRADE_WURM = make_creature(
    name="Balustrade Wurm",
    power=5, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Wurm"},
    text="This spell can't be countered.\nTrample, haste\nDelirium — {2}{G}{G}: Return this card from your graveyard to the battlefield with a finality counter on it. Activate only if there are four or more card types among cards in your graveyard and only as a sorcery.",
)

BASHFUL_BEASTIE = make_creature(
    name="Bashful Beastie",
    power=5, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="When this creature dies, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
)

BREAK_DOWN_THE_DOOR = make_instant(
    name="Break Down the Door",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Exile target artifact.\n• Exile target enchantment.\n• Manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
)

CATHARTIC_PARTING = make_sorcery(
    name="Cathartic Parting",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="The owner of target artifact or enchantment an opponent controls shuffles it into their library. You may shuffle up to four target cards from your graveyard into your library.",
)

CAUTIOUS_SURVIVOR = make_creature(
    name="Cautious Survivor",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Survivor"},
    text="Survival — At the beginning of your second main phase, if this creature is tapped, you gain 2 life.",
)

COORDINATED_CLOBBERING = make_sorcery(
    name="Coordinated Clobbering",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Tap one or two target untapped creatures you control. They each deal damage equal to their power to target creature an opponent controls.",
)

CRYPTID_INSPECTOR = make_creature(
    name="Cryptid Inspector",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    text="Vigilance\nWhenever a face-down permanent you control enters and whenever this creature or another permanent you control is turned face up, put a +1/+1 counter on this creature.",
)

DEFIANT_SURVIVOR = make_creature(
    name="Defiant Survivor",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Survivor"},
    text="Survival — At the beginning of your second main phase, if this creature is tapped, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
)

ENDURING_VITALITY = make_enchantment_creature(
    name="Enduring Vitality",
    power=3, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elk", "Glimmer"},
    text="Vigilance\nCreatures you control have \"{T}: Add one mana of any color.\"\nWhen Enduring Vitality dies, if it was a creature, return it to the battlefield under its owner's control. It's an enchantment. (It's not a creature.)",
)

FEAR_OF_EXPOSURE = make_enchantment_creature(
    name="Fear of Exposure",
    power=5, toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Nightmare"},
    text="As an additional cost to cast this spell, tap two untapped creatures and/or lands you control.\nTrample",
)

FLESH_BURROWER = make_creature(
    name="Flesh Burrower",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Insect"},
    text="Deathtouch\nWhenever this creature attacks, another target creature you control gains deathtouch until end of turn.",
)

FRANTIC_STRENGTH = make_enchantment(
    name="Frantic Strength",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Flash\nEnchant creature\nEnchanted creature gets +2/+2 and has trample.",
    subtypes={"Aura"},
)

GRASPING_LONGNECK = make_enchantment_creature(
    name="Grasping Longneck",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Horror"},
    text="Reach\nWhen this creature dies, you gain 2 life.",
)

GREENHOUSE = make_enchantment(
    name="Greenhouse",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Greenhouse {2}{G}: Lands you control have \"{T}: Add one mana of any color.\"\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nRickety Gazebo {3}{G}: When you unlock this door, mill four cards, then return up to two permanent cards from among them to your hand.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

HAUNTWOODS_SHRIEKER = make_creature(
    name="Hauntwoods Shrieker",
    power=3, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Mutant"},
    text="Whenever this creature attacks, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)\n{1}{G}: Reveal target face-down permanent. If it's a creature card, you may turn it face up.",
)

HEDGE_SHREDDER = make_artifact(
    name="Hedge Shredder",
    mana_cost="{2}{G}{G}",
    text="Whenever this Vehicle attacks, you may mill two cards.\nWhenever one or more land cards are put into your graveyard from your library, put them onto the battlefield tapped.\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
)

HORRID_VIGOR = make_instant(
    name="Horrid Vigor",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gains deathtouch and indestructible until end of turn.",
)

HOUSE_CARTOGRAPHER = make_creature(
    name="House Cartographer",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout", "Survivor"},
    text="Survival — At the beginning of your second main phase, if this creature is tapped, reveal cards from the top of your library until you reveal a land card. Put that card into your hand and the rest on the bottom of your library in a random order.",
)

INSIDIOUS_FUNGUS = make_creature(
    name="Insidious Fungus",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Fungus"},
    text="{2}, Sacrifice this creature: Choose one —\n• Destroy target artifact.\n• Destroy target enchantment.\n• Draw a card. Then you may put a land card from your hand onto the battlefield tapped.",
)

KONA_RESCUE_BEASTIE = make_creature(
    name="Kona, Rescue Beastie",
    power=4, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Survivor"},
    supertypes={"Legendary"},
    text="Survival — At the beginning of your second main phase, if Kona is tapped, you may put a permanent card from your hand onto the battlefield.",
)

LEYLINE_OF_MUTATION = make_enchantment(
    name="Leyline of Mutation",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="If this card is in your opening hand, you may begin the game with it on the battlefield.\nYou may pay {W}{U}{B}{R}{G} rather than pay the mana cost for spells you cast.",
)

MANIFEST_DREAD = make_sorcery(
    name="Manifest Dread",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
)

MOLDERING_GYM = make_enchantment(
    name="Moldering Gym",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Moldering Gym {2}{G}: When you unlock this door, search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nWeight Room {5}{G}: When you unlock this door, manifest dread, then put three +1/+1 counters on that creature.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

MONSTROUS_EMERGENCE = make_sorcery(
    name="Monstrous Emergence",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="As an additional cost to cast this spell, choose a creature you control or reveal a creature card from your hand.\nMonstrous Emergence deals damage equal to the power of the creature you chose or the card you revealed to target creature.",
)

OMNIVOROUS_FLYTRAP = make_creature(
    name="Omnivorous Flytrap",
    power=2, toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="Delirium — Whenever this creature enters or attacks, if there are four or more card types among cards in your graveyard, distribute two +1/+1 counters among one or two target creatures. Then if there are six or more card types among cards in your graveyard, double the number of +1/+1 counters on those creatures.",
)

OVERGROWN_ZEALOT = make_creature(
    name="Overgrown Zealot",
    power=0, toughness=4,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Elf"},
    text="{T}: Add one mana of any color.\n{T}: Add two mana of any one color. Spend this mana only to turn permanents face up.",
)

OVERLORD_OF_THE_HAUNTWOODS = make_enchantment_creature(
    name="Overlord of the Hauntwoods",
    power=6, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Avatar", "Horror"},
    text="Impending 4—{1}{G}{G} (If you cast this spell for its impending cost, it enters with four time counters and isn't a creature until the last is removed. At the beginning of your end step, remove a time counter from it.)\nWhenever this permanent enters or attacks, create a tapped colorless land token named Everywhere that is every basic land type.",
)

PATCHWORK_BEASTIE = make_artifact_creature(
    name="Patchwork Beastie",
    power=3, toughness=3,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Delirium — This creature can't attack or block unless there are four or more card types among cards in your graveyard.\nAt the beginning of your upkeep, you may mill a card. (You may put the top card of your library into your graveyard.)",
)

ROOTWISE_SURVIVOR = make_creature(
    name="Rootwise Survivor",
    power=3, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Survivor"},
    text="Haste\nSurvival — At the beginning of your second main phase, if this creature is tapped, put three +1/+1 counters on up to one target land you control. That land becomes a 0/0 Elemental creature in addition to its other types. It gains haste until your next turn.",
)

SAY_ITS_NAME = make_sorcery(
    name="Say Its Name",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Mill three cards. Then you may return a creature or land card from your graveyard to your hand.\nExile this card and two other cards named Say Its Name from your graveyard: Search your graveyard, hand, and/or library for a card named Altanak, the Thrice-Called and put it onto the battlefield. If you search your library this way, shuffle. Activate only as a sorcery.",
)

SLAVERING_BRANCHSNAPPER = make_creature(
    name="Slavering Branchsnapper",
    power=7, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Lizard"},
    text="Trample\nForestcycling {2} ({2}, Discard this card: Search your library for a Forest card, reveal it, put it into your hand, then shuffle.)",
)

SPINESEEKER_CENTIPEDE = make_creature(
    name="Spineseeker Centipede",
    power=2, toughness=1,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Insect"},
    text="When this creature enters, search your library for a basic land card, reveal it, put it into your hand, then shuffle.\nDelirium — This creature gets +1/+2 and has vigilance as long as there are four or more card types among cards in your graveyard.",
)

THREATS_AROUND_EVERY_CORNER = make_enchantment(
    name="Threats Around Every Corner",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, manifest dread.\nWhenever a face-down permanent you control enters, search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
)

TWITCHING_DOLL = make_artifact_creature(
    name="Twitching Doll",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Spider", "Toy"},
    text="{T}: Add one mana of any color. Put a nest counter on this creature.\n{T}, Sacrifice this creature: Create a 2/2 green Spider creature token with reach for each counter on this creature. Activate only as a sorcery.",
)

TYVAR_THE_PUMMELER = make_creature(
    name="Tyvar, the Pummeler",
    power=3, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    supertypes={"Legendary"},
    text="Tap another untapped creature you control: Tyvar gains indestructible until end of turn. Tap it.\n{3}{G}{G}: Creatures you control get +X/+X until end of turn, where X is the greatest power among creatures you control.",
)

UNDER_THE_SKIN = make_sorcery(
    name="Under the Skin",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)\nYou may return a permanent card from your graveyard to your hand.",
)

VALGAVOTHS_ONSLAUGHT = make_sorcery(
    name="Valgavoth's Onslaught",
    mana_cost="{X}{X}{G}",
    colors={Color.GREEN},
    text="Manifest dread X times, then put X +1/+1 counters on each of those creatures. (To manifest dread, look at the top two cards of your library, then put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
)

WALKIN_CLOSET = make_enchantment(
    name="Walk-In Closet",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Walk-In Closet {2}{G}: You may play lands from your graveyard.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nForgotten Cellar {3}{G}{G}: When you unlock this door, you may cast spells from your graveyard this turn, and if a card would be put into your graveyard from anywhere this turn, exile it instead.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

WARY_WATCHDOG = make_creature(
    name="Wary Watchdog",
    power=3, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Dog"},
    text="When this creature enters or dies, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

WICKERFOLK_THRESHER = make_artifact_creature(
    name="Wickerfolk Thresher",
    power=5, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Scarecrow"},
    text="Delirium — Whenever this creature attacks, if there are four or more card types among cards in your graveyard, look at the top card of your library. If it's a land card, you may put it onto the battlefield. If you don't put the card onto the battlefield, put it into your hand.",
)

ARABELLA_ABANDONED_DOLL = make_artifact_creature(
    name="Arabella, Abandoned Doll",
    power=1, toughness=3,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Toy"},
    supertypes={"Legendary"},
    text="Whenever Arabella attacks, it deals X damage to each opponent and you gain X life, where X is the number of creatures you control with power 2 or less.",
)

BASEBALL_BAT = make_artifact(
    name="Baseball Bat",
    mana_cost="{G}{W}",
    text="When this Equipment enters, attach it to target creature you control.\nEquipped creature gets +1/+1.\nWhenever equipped creature attacks, tap up to one target creature.\nEquip {3} ({3}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

BEASTIE_BEATDOWN = make_sorcery(
    name="Beastie Beatdown",
    mana_cost="{R}{G}",
    colors={Color.GREEN, Color.RED},
    text="Choose target creature you control and target creature an opponent controls.\nDelirium — If there are four or more card types among cards in your graveyard, put two +1/+1 counters on the creature you control.\nThe creature you control deals damage equal to its power to the creature an opponent controls.",
)

BROODSPINNER = make_creature(
    name="Broodspinner",
    power=2, toughness=3,
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Spider"},
    text="Reach\nWhen this creature enters, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\n{4}{B}{G}, {T}, Sacrifice this creature: Create a number of 1/1 black and green Insect creature tokens with flying equal to the number of card types among cards in your graveyard.",
)

DISTURBING_MIRTH = make_enchantment(
    name="Disturbing Mirth",
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="When this enchantment enters, you may sacrifice another enchantment or creature. If you do, draw two cards.\nWhen you sacrifice this enchantment, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)",
)

DRAG_TO_THE_ROOTS = make_instant(
    name="Drag to the Roots",
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Delirium — This spell costs {2} less to cast as long as there are four or more card types among cards in your graveyard.\nDestroy target nonland permanent.",
)

FEAR_OF_INFINITY = make_enchantment_creature(
    name="Fear of Infinity",
    power=2, toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Nightmare"},
    text="Flying, lifelink\nThis creature can't block.\nEerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, you may return this card from your graveyard to your hand.",
)

GREMLIN_TAMER = make_creature(
    name="Gremlin Tamer",
    power=2, toughness=2,
    mana_cost="{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Scout"},
    text="Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, create a 1/1 red Gremlin creature token.",
)

GROWING_DREAD = make_enchantment(
    name="Growing Dread",
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    text="Flash\nWhen this enchantment enters, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)\nWhenever you turn a permanent face up, put a +1/+1 counter on it.",
)

INQUISITIVE_GLIMMER = make_enchantment_creature(
    name="Inquisitive Glimmer",
    power=2, toughness=3,
    mana_cost="{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Fox", "Glimmer"},
    text="Enchantment spells you cast cost {1} less to cast.\nUnlock costs you pay cost {1} less.",
)

INTRUDING_SOULRAGER = make_creature(
    name="Intruding Soulrager",
    power=2, toughness=2,
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Spirit"},
    text="Vigilance\n{T}, Sacrifice a Room: This creature deals 2 damage to each opponent. Draw a card.",
)

THE_JOLLY_BALLOON_MAN = make_creature(
    name="The Jolly Balloon Man",
    power=1, toughness=4,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Clown", "Human"},
    supertypes={"Legendary"},
    text="Haste\n{1}, {T}: Create a token that's a copy of another target creature you control, except it's a 1/1 red Balloon creature in addition to its other colors and types and it has flying and haste. Sacrifice it at the beginning of the next end step. Activate only as a sorcery.",
)

KAITO_BANE_OF_NIGHTMARES = make_planeswalker(
    name="Kaito, Bane of Nightmares",
    mana_cost="{2}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    loyalty=4,
    subtypes={"Kaito"},
    supertypes={"Legendary"},
    text="Ninjutsu {1}{U}{B} ({1}{U}{B}, Return an unblocked attacker you control to hand: Put this card onto the battlefield from your hand tapped and attacking.)\nDuring your turn, as long as Kaito has one or more loyalty counters on him, he's a 3/4 Ninja creature and has hexproof.\n+1: You get an emblem with \"Ninjas you control get +1/+1.\"\n0: Surveil 2. Then draw a card for each opponent who lost life this turn.\n−2: Tap target creature. Put two stun counters on it.",
)

MARINA_VENDRELL = make_creature(
    name="Marina Vendrell",
    power=3, toughness=5,
    mana_cost="{W}{U}{B}{R}{G}",
    colors={Color.BLACK, Color.GREEN, Color.RED, Color.BLUE, Color.WHITE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="When Marina Vendrell enters, reveal the top seven cards of your library. Put all enchantment cards from among them into your hand and the rest on the bottom of your library in a random order.\n{T}: Lock or unlock a door of target Room you control. Activate only as a sorcery.",
)

MIDNIGHT_MAYHEM = make_sorcery(
    name="Midnight Mayhem",
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Create three 1/1 red Gremlin creature tokens. Gremlins you control gain menace, lifelink, and haste until end of turn. (A creature with menace can't be blocked except by two or more creatures.)",
)

NASHI_SEARCHER_IN_THE_DARK = make_creature(
    name="Nashi, Searcher in the Dark",
    power=2, toughness=2,
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Ninja", "Rat", "Wizard"},
    supertypes={"Legendary"},
    text="Menace\nWhenever Nashi deals combat damage to a player, you mill that many cards. You may put any number of legendary and/or enchantment cards from among them into your hand. If you put no cards into your hand this way, put a +1/+1 counter on Nashi.",
)

NIKO_LIGHT_OF_HOPE = make_creature(
    name="Niko, Light of Hope",
    power=3, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="When Niko enters, create two Shard tokens. (They're enchantments with \"{2}, Sacrifice this token: Scry 1, then draw a card.\")\n{2}, {T}: Exile target nonlegendary creature you control. Shards you control become copies of it until the next end step. Return it to the battlefield under its owner's control at the beginning of the next end step.",
)

OBLIVIOUS_BOOKWORM = make_creature(
    name="Oblivious Bookworm",
    power=2, toughness=3,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="At the beginning of your end step, you may draw a card. If you do, discard a card unless a permanent entered the battlefield face down under your control this turn or you turned a permanent face up this turn.",
)

PEER_PAST_THE_VEIL = make_instant(
    name="Peer Past the Veil",
    mana_cost="{2}{R}{G}",
    colors={Color.GREEN, Color.RED},
    text="Discard your hand. Then draw X cards, where X is the number of card types among cards in your graveyard.",
)

RESTRICTED_OFFICE = make_enchantment(
    name="Restricted Office",
    mana_cost="{2}{W}{W}",
    colors={Color.BLUE, Color.WHITE},
    text="Restricted Office {2}{W}{W}: When you unlock this door, destroy all creatures with power 3 or greater.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nLecture Hall {5}{U}{U}: Other permanents you control have hexproof.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

RIP_SPAWN_HUNTER = make_creature(
    name="Rip, Spawn Hunter",
    power=4, toughness=4,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Survivor"},
    supertypes={"Legendary"},
    text="Survival — At the beginning of your second main phase, if Rip is tapped, reveal the top X cards of your library, where X is its power. Put any number of creature and/or Vehicle cards with different powers from among them into your hand. Put the rest on the bottom of your library in a random order.",
)

RITE_OF_THE_MOTH = make_sorcery(
    name="Rite of the Moth",
    mana_cost="{1}{W}{B}{B}",
    colors={Color.BLACK, Color.WHITE},
    text="Return target creature card from your graveyard to the battlefield with a finality counter on it. (If a creature with a finality counter on it would die, exile it instead.)\nFlashback {3}{W}{W}{B} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

ROARING_FURNACE = make_enchantment(
    name="Roaring Furnace",
    mana_cost="{1}{R}",
    colors={Color.RED, Color.BLUE},
    text="Roaring Furnace {1}{R}: When you unlock this door, this Room deals damage equal to the number of cards in your hand to target creature an opponent controls.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nSteaming Sauna {3}{U}{U}: You have no maximum hand size.\nAt the beginning of your end step, draw a card.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

SAWBLADE_SKINRIPPER = make_creature(
    name="Sawblade Skinripper",
    power=3, toughness=2,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Assassin", "Human"},
    text="Menace\n{2}, Sacrifice another creature or enchantment: Put a +1/+1 counter on this creature.\nAt the beginning of your end step, if you sacrificed one or more permanents this turn, this creature deals that much damage to any target.",
)

SHREWD_STORYTELLER = make_creature(
    name="Shrewd Storyteller",
    power=3, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Survivor"},
    text="Survival — At the beginning of your second main phase, if this creature is tapped, put a +1/+1 counter on target creature.",
)

SHROUDSTOMPER = make_creature(
    name="Shroudstomper",
    power=5, toughness=5,
    mana_cost="{3}{W}{W}{B}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Elemental"},
    text="Deathtouch\nWhenever this creature enters or attacks, each opponent loses 2 life. You gain 2 life and draw a card.",
)

SKULLSNAP_NUISANCE = make_creature(
    name="Skullsnap Nuisance",
    power=1, toughness=4,
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Insect", "Skeleton"},
    text="Flying\nEerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

SMOKY_LOUNGE = make_enchantment(
    name="Smoky Lounge",
    mana_cost="{2}{R}",
    colors={Color.RED, Color.BLUE},
    text="Smoky Lounge {2}{R}: At the beginning of your first main phase, add {R}{R}. Spend this mana only to cast Room spells and unlock doors.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)\n//\nMisty Salon {3}{U}: When you unlock this door, create an X/X blue Spirit creature token with flying, where X is the number of unlocked doors among Rooms you control.\n(You may cast either half. That door unlocks on the battlefield. As a sorcery, you may pay the mana cost of a locked door to unlock it.)",
    subtypes={"Room"},
)

THE_SWARMWEAVER = make_artifact_creature(
    name="The Swarmweaver",
    power=2, toughness=3,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Scarecrow"},
    supertypes={"Legendary"},
    text="When The Swarmweaver enters, create two 1/1 black and green Insect creature tokens with flying.\nDelirium — As long as there are four or more card types among cards in your graveyard, Insects and Spiders you control get +1/+1 and have deathtouch.",
)

UNDEAD_SPRINTER = make_creature(
    name="Undead Sprinter",
    power=2, toughness=2,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Zombie"},
    text="Trample, haste\nYou may cast this card from your graveyard if a non-Zombie creature died this turn. If you do, this creature enters with a +1/+1 counter on it.",
)

VICTOR_VALGAVOTHS_SENESCHAL = make_creature(
    name="Victor, Valgavoth's Seneschal",
    power=3, toughness=3,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Eerie — Whenever an enchantment you control enters and whenever you fully unlock a Room, surveil 2 if this is the first time this ability has resolved this turn. If it's the second time, each opponent discards a card. If it's the third time, put a creature card from a graveyard onto the battlefield under your control.",
)

WILDFIRE_WICKERFOLK = make_artifact_creature(
    name="Wildfire Wickerfolk",
    power=3, toughness=2,
    mana_cost="{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Scarecrow"},
    text="Haste\nDelirium — This creature gets +1/+1 and has trample as long as there are four or more card types among cards in your graveyard.",
)

WINTER_MISANTHROPIC_GUIDE = make_creature(
    name="Winter, Misanthropic Guide",
    power=3, toughness=4,
    mana_cost="{1}{B}{R}{G}",
    colors={Color.BLACK, Color.GREEN, Color.RED},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Ward {2}\nAt the beginning of your upkeep, each player draws two cards.\nDelirium — As long as there are four or more card types among cards in your graveyard, each opponent's maximum hand size is equal to seven minus the number of those card types.",
)

ZIMONE_ALLQUESTIONING = make_creature(
    name="Zimone, All-Questioning",
    power=1, toughness=1,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="At the beginning of your end step, if a land entered the battlefield under your control this turn and you control a prime number of lands, create Primo, the Indivisible, a legendary 0/0 green and blue Fractal creature token, then put that many +1/+1 counters on it. (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, and 31 are prime numbers.)",
)

ATTACKINTHEBOX = make_artifact_creature(
    name="Attack-in-the-Box",
    power=2, toughness=4,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Toy"},
    text="Whenever this creature attacks, you may have it get +4/+0 until end of turn. If you do, sacrifice it at the beginning of the next end step.",
)

BEAR_TRAP = make_artifact(
    name="Bear Trap",
    mana_cost="{1}",
    text="Flash\n{3}, {T}, Sacrifice this artifact: It deals 3 damage to target creature.",
)

CONDUCTIVE_MACHETE = make_artifact(
    name="Conductive Machete",
    mana_cost="{4}",
    text="When this Equipment enters, manifest dread, then attach this Equipment to that creature. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard. Turn it face up any time for its mana cost if it's a creature card.)\nEquipped creature gets +2/+1.\nEquip {4}",
    subtypes={"Equipment"},
)

DISSECTION_TOOLS = make_artifact(
    name="Dissection Tools",
    mana_cost="{5}",
    text="When this Equipment enters, manifest dread, then attach this Equipment to that creature.\nEquipped creature gets +2/+2 and has deathtouch and lifelink.\nEquip—Sacrifice a creature.",
    subtypes={"Equipment"},
)

FOUND_FOOTAGE = make_artifact(
    name="Found Footage",
    mana_cost="{1}",
    text="You may look at face-down creatures your opponents control any time.\n{2}, Sacrifice this artifact: Surveil 2, then draw a card. (To surveil 2, look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
    subtypes={"Clue"},
)

FRIENDLY_TEDDY = make_artifact_creature(
    name="Friendly Teddy",
    power=2, toughness=2,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Bear", "Toy"},
    text="When this creature dies, each player draws a card.",
)

GHOST_VACUUM = make_artifact(
    name="Ghost Vacuum",
    mana_cost="{1}",
    text="{T}: Exile target card from a graveyard.\n{6}, {T}, Sacrifice this artifact: Put each creature card exiled with this artifact onto the battlefield under your control with a flying counter on it. Each of them is a 1/1 Spirit in addition to its other types. Activate only as a sorcery.",
)

GLIMMERLIGHT = make_artifact(
    name="Glimmerlight",
    mana_cost="{2}",
    text="When this Equipment enters, create a 1/1 white Glimmer enchantment creature token.\nEquipped creature gets +1/+1.\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

HAUNTED_SCREEN = make_artifact(
    name="Haunted Screen",
    mana_cost="{3}",
    text="{T}: Add {W} or {B}.\n{T}, Pay 1 life: Add {G}, {U}, or {R}.\n{7}: Put seven +1/+1 counters on this artifact. It becomes a 0/0 Spirit creature in addition to its other types. Activate only once.",
)

KEYS_TO_THE_HOUSE = make_artifact(
    name="Keys to the House",
    mana_cost="{1}",
    text="{1}, {T}, Sacrifice this artifact: Search your library for a basic land card, reveal it, put it into your hand, then shuffle.\n{3}, {T}, Sacrifice this artifact: Lock or unlock a door of target Room you control. Activate only as a sorcery.",
)

MALEVOLENT_CHANDELIER = make_artifact_creature(
    name="Malevolent Chandelier",
    power=4, toughness=4,
    mana_cost="{6}",
    colors=set(),
    subtypes={"Construct"},
    text="Flying\n{2}: Put target card from a graveyard on the bottom of its owner's library. Activate only as a sorcery.",
)

MARVIN_MURDEROUS_MIMIC = make_artifact_creature(
    name="Marvin, Murderous Mimic",
    power=2, toughness=2,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Toy"},
    supertypes={"Legendary"},
    text="Marvin has all activated abilities of creatures you control that don't have the same name as this creature.",
)

SAW = make_artifact(
    name="Saw",
    mana_cost="{2}",
    text="Equipped creature gets +2/+0.\nWhenever equipped creature attacks, you may sacrifice a permanent other than that creature or this Equipment. If you do, draw a card.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

ABANDONED_CAMPGROUND = make_land(
    name="Abandoned Campground",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {W} or {U}.",
)

BLAZEMIRE_VERGE = make_land(
    name="Blazemire Verge",
    text="{T}: Add {B}.\n{T}: Add {R}. Activate only if you control a Swamp or a Mountain.",
)

BLEEDING_WOODS = make_land(
    name="Bleeding Woods",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {R} or {G}.",
)

ETCHED_CORNFIELD = make_land(
    name="Etched Cornfield",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {G} or {W}.",
)

FLOODFARM_VERGE = make_land(
    name="Floodfarm Verge",
    text="{T}: Add {W}.\n{T}: Add {U}. Activate only if you control a Plains or an Island.",
)

GLOOMLAKE_VERGE = make_land(
    name="Gloomlake Verge",
    text="{T}: Add {U}.\n{T}: Add {B}. Activate only if you control an Island or a Swamp.",
)

HUSHWOOD_VERGE = make_land(
    name="Hushwood Verge",
    text="{T}: Add {G}.\n{T}: Add {W}. Activate only if you control a Forest or a Plains.",
)

LAKESIDE_SHACK = make_land(
    name="Lakeside Shack",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {G} or {U}.",
)

MURKY_SEWER = make_land(
    name="Murky Sewer",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {U} or {B}.",
)

NEGLECTED_MANOR = make_land(
    name="Neglected Manor",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {W} or {B}.",
)

PECULIAR_LIGHTHOUSE = make_land(
    name="Peculiar Lighthouse",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {U} or {R}.",
)

RAUCOUS_CARNIVAL = make_land(
    name="Raucous Carnival",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {R} or {W}.",
)

RAZORTRAP_GORGE = make_land(
    name="Razortrap Gorge",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {B} or {R}.",
)

STRANGLED_CEMETERY = make_land(
    name="Strangled Cemetery",
    text="This land enters tapped unless a player has 13 or less life.\n{T}: Add {B} or {G}.",
)

TERRAMORPHIC_EXPANSE = make_land(
    name="Terramorphic Expanse",
    text="{T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
)

THORNSPIRE_VERGE = make_land(
    name="Thornspire Verge",
    text="{T}: Add {R}.\n{T}: Add {G}. Activate only if you control a Mountain or a Forest.",
)

VALGAVOTHS_LAIR = make_enchantment(
    name="Valgavoth's Lair",
    mana_cost="",
    colors=set(),
    text="Hexproof\nThis land enters tapped. As it enters, choose a color.\n{T}: Add one mana of the chosen color.",
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

DUSKMOURN_CARDS = {
    "Acrobatic Cheerleader": ACROBATIC_CHEERLEADER,
    "Cult Healer": CULT_HEALER,
    "Dazzling Theater": DAZZLING_THEATER,
    "Dollmaker's Shop": DOLLMAKERS_SHOP,
    "Emerge from the Cocoon": EMERGE_FROM_THE_COCOON,
    "Enduring Innocence": ENDURING_INNOCENCE,
    "Ethereal Armor": ETHEREAL_ARMOR,
    "Exorcise": EXORCISE,
    "Fear of Abduction": FEAR_OF_ABDUCTION,
    "Fear of Immobility": FEAR_OF_IMMOBILITY,
    "Fear of Surveillance": FEAR_OF_SURVEILLANCE,
    "Friendly Ghost": FRIENDLY_GHOST,
    "Ghostly Dancers": GHOSTLY_DANCERS,
    "Glimmer Seeker": GLIMMER_SEEKER,
    "Grand Entryway": GRAND_ENTRYWAY,
    "Hardened Escort": HARDENED_ESCORT,
    "Jump Scare": JUMP_SCARE,
    "Leyline of Hope": LEYLINE_OF_HOPE,
    "Lionheart Glimmer": LIONHEART_GLIMMER,
    "Living Phone": LIVING_PHONE,
    "Optimistic Scavenger": OPTIMISTIC_SCAVENGER,
    "Orphans of the Wheat": ORPHANS_OF_THE_WHEAT,
    "Overlord of the Mistmoors": OVERLORD_OF_THE_MISTMOORS,
    "Patched Plaything": PATCHED_PLAYTHING,
    "Possessed Goat": POSSESSED_GOAT,
    "Reluctant Role Model": RELUCTANT_ROLE_MODEL,
    "Savior of the Small": SAVIOR_OF_THE_SMALL,
    "Seized from Slumber": SEIZED_FROM_SLUMBER,
    "Shardmage's Rescue": SHARDMAGES_RESCUE,
    "Sheltered by Ghosts": SHELTERED_BY_GHOSTS,
    "Shepherding Spirits": SHEPHERDING_SPIRITS,
    "Split Up": SPLIT_UP,
    "Splitskin Doll": SPLITSKIN_DOLL,
    "Surgical Suite": SURGICAL_SUITE,
    "Toby, Beastie Befriender": TOBY_BEASTIE_BEFRIENDER,
    "Trapped in the Screen": TRAPPED_IN_THE_SCREEN,
    "Unidentified Hovership": UNIDENTIFIED_HOVERSHIP,
    "Unsettling Twins": UNSETTLING_TWINS,
    "Unwanted Remake": UNWANTED_REMAKE,
    "Veteran Survivor": VETERAN_SURVIVOR,
    "The Wandering Rescuer": THE_WANDERING_RESCUER,
    "Abhorrent Oculus": ABHORRENT_OCULUS,
    "Bottomless Pool": BOTTOMLESS_POOL,
    "Central Elevator": CENTRAL_ELEVATOR,
    "Clammy Prowler": CLAMMY_PROWLER,
    "Creeping Peeper": CREEPING_PEEPER,
    "Cursed Windbreaker": CURSED_WINDBREAKER,
    "Daggermaw Megalodon": DAGGERMAW_MEGALODON,
    "Don't Make a Sound": DONT_MAKE_A_SOUND,
    "Duskmourn's Domination": DUSKMOURNS_DOMINATION,
    "Enduring Curiosity": ENDURING_CURIOSITY,
    "Enter the Enigma": ENTER_THE_ENIGMA,
    "Entity Tracker": ENTITY_TRACKER,
    "Erratic Apparition": ERRATIC_APPARITION,
    "Fear of Failed Tests": FEAR_OF_FAILED_TESTS,
    "Fear of Falling": FEAR_OF_FALLING,
    "Fear of Impostors": FEAR_OF_IMPOSTORS,
    "Fear of Isolation": FEAR_OF_ISOLATION,
    "Floodpits Drowner": FLOODPITS_DROWNER,
    "Get Out": GET_OUT,
    "Ghostly Keybearer": GHOSTLY_KEYBEARER,
    "Glimmerburst": GLIMMERBURST,
    "Leyline of Transformation": LEYLINE_OF_TRANSFORMATION,
    "Marina Vendrell's Grimoire": MARINA_VENDRELLS_GRIMOIRE,
    "Meat Locker": MEAT_LOCKER,
    "The Mindskinner": THE_MINDSKINNER,
    "Mirror Room": MIRROR_ROOM,
    "Overlord of the Floodpits": OVERLORD_OF_THE_FLOODPITS,
    "Paranormal Analyst": PARANORMAL_ANALYST,
    "Piranha Fly": PIRANHA_FLY,
    "Scrabbling Skullcrab": SCRABBLING_SKULLCRAB,
    "Silent Hallcreeper": SILENT_HALLCREEPER,
    "Stalked Researcher": STALKED_RESEARCHER,
    "Stay Hidden, Stay Silent": STAY_HIDDEN_STAY_SILENT,
    "The Tale of Tamiyo": THE_TALE_OF_TAMIYO,
    "Tunnel Surveyor": TUNNEL_SURVEYOR,
    "Twist Reality": TWIST_REALITY,
    "Unable to Scream": UNABLE_TO_SCREAM,
    "Underwater Tunnel": UNDERWATER_TUNNEL,
    "Unnerving Grasp": UNNERVING_GRASP,
    "Unwilling Vessel": UNWILLING_VESSEL,
    "Vanish from Sight": VANISH_FROM_SIGHT,
    "Appendage Amalgam": APPENDAGE_AMALGAM,
    "Balemurk Leech": BALEMURK_LEECH,
    "Cackling Slasher": CACKLING_SLASHER,
    "Come Back Wrong": COME_BACK_WRONG,
    "Commune with Evil": COMMUNE_WITH_EVIL,
    "Cracked Skull": CRACKED_SKULL,
    "Cynical Loner": CYNICAL_LONER,
    "Dashing Bloodsucker": DASHING_BLOODSUCKER,
    "Defiled Crypt": DEFILED_CRYPT,
    "Demonic Counsel": DEMONIC_COUNSEL,
    "Derelict Attic": DERELICT_ATTIC,
    "Doomsday Excruciator": DOOMSDAY_EXCRUCIATOR,
    "Enduring Tenacity": ENDURING_TENACITY,
    "Fanatic of the Harrowing": FANATIC_OF_THE_HARROWING,
    "Fear of Lost Teeth": FEAR_OF_LOST_TEETH,
    "Fear of the Dark": FEAR_OF_THE_DARK,
    "Final Vengeance": FINAL_VENGEANCE,
    "Funeral Room": FUNERAL_ROOM,
    "Give In to Violence": GIVE_IN_TO_VIOLENCE,
    "Grievous Wound": GRIEVOUS_WOUND,
    "Innocuous Rat": INNOCUOUS_RAT,
    "Killer's Mask": KILLERS_MASK,
    "Let's Play a Game": LETS_PLAY_A_GAME,
    "Leyline of the Void": LEYLINE_OF_THE_VOID,
    "Live or Die": LIVE_OR_DIE,
    "Meathook Massacre II": MEATHOOK_MASSACRE_II,
    "Miasma Demon": MIASMA_DEMON,
    "Murder": MURDER,
    "Nowhere to Run": NOWHERE_TO_RUN,
    "Osseous Sticktwister": OSSEOUS_STICKTWISTER,
    "Overlord of the Balemurk": OVERLORD_OF_THE_BALEMURK,
    "Popular Egotist": POPULAR_EGOTIST,
    "Resurrected Cultist": RESURRECTED_CULTIST,
    "Spectral Snatcher": SPECTRAL_SNATCHER,
    "Sporogenic Infection": SPOROGENIC_INFECTION,
    "Unholy Annex": UNHOLY_ANNEX,
    "Unstoppable Slasher": UNSTOPPABLE_SLASHER,
    "Valgavoth, Terror Eater": VALGAVOTH_TERROR_EATER,
    "Valgavoth's Faithful": VALGAVOTHS_FAITHFUL,
    "Vile Mutilator": VILE_MUTILATOR,
    "Winter's Intervention": WINTERS_INTERVENTION,
    "Withering Torment": WITHERING_TORMENT,
    "Bedhead Beastie": BEDHEAD_BEASTIE,
    "Betrayer's Bargain": BETRAYERS_BARGAIN,
    "Boilerbilges Ripper": BOILERBILGES_RIPPER,
    "Chainsaw": CHAINSAW,
    "Charred Foyer": CHARRED_FOYER,
    "Clockwork Percussionist": CLOCKWORK_PERCUSSIONIST,
    "Cursed Recording": CURSED_RECORDING,
    "Diversion Specialist": DIVERSION_SPECIALIST,
    "Enduring Courage": ENDURING_COURAGE,
    "Fear of Being Hunted": FEAR_OF_BEING_HUNTED,
    "Fear of Burning Alive": FEAR_OF_BURNING_ALIVE,
    "Fear of Missing Out": FEAR_OF_MISSING_OUT,
    "Glassworks": GLASSWORKS,
    "Grab the Prize": GRAB_THE_PRIZE,
    "Hand That Feeds": HAND_THAT_FEEDS,
    "Impossible Inferno": IMPOSSIBLE_INFERNO,
    "Infernal Phantom": INFERNAL_PHANTOM,
    "Irreverent Gremlin": IRREVERENT_GREMLIN,
    "Leyline of Resonance": LEYLINE_OF_RESONANCE,
    "A-Leyline of Resonance": ALEYLINE_OF_RESONANCE,
    "Most Valuable Slayer": MOST_VALUABLE_SLAYER,
    "Norin, Swift Survivalist": NORIN_SWIFT_SURVIVALIST,
    "Overlord of the Boilerbilges": OVERLORD_OF_THE_BOILERBILGES,
    "Painter's Studio": PAINTERS_STUDIO,
    "Piggy Bank": PIGGY_BANK,
    "Pyroclasm": PYROCLASM,
    "Ragged Playmate": RAGGED_PLAYMATE,
    "Rampaging Soulrager": RAMPAGING_SOULRAGER,
    "Razorkin Hordecaller": RAZORKIN_HORDECALLER,
    "Razorkin Needlehead": RAZORKIN_NEEDLEHEAD,
    "Ripchain Razorkin": RIPCHAIN_RAZORKIN,
    "The Rollercrusher Ride": THE_ROLLERCRUSHER_RIDE,
    "Scorching Dragonfire": SCORCHING_DRAGONFIRE,
    "Screaming Nemesis": SCREAMING_NEMESIS,
    "Ticket Booth": TICKET_BOOTH,
    "Trial of Agony": TRIAL_OF_AGONY,
    "Turn Inside Out": TURN_INSIDE_OUT,
    "Untimely Malfunction": UNTIMELY_MALFUNCTION,
    "Vengeful Possession": VENGEFUL_POSSESSION,
    "Vicious Clown": VICIOUS_CLOWN,
    "Violent Urge": VIOLENT_URGE,
    "Waltz of Rage": WALTZ_OF_RAGE,
    "Altanak, the Thrice-Called": ALTANAK_THE_THRICECALLED,
    "Anthropede": ANTHROPEDE,
    "Balustrade Wurm": BALUSTRADE_WURM,
    "Bashful Beastie": BASHFUL_BEASTIE,
    "Break Down the Door": BREAK_DOWN_THE_DOOR,
    "Cathartic Parting": CATHARTIC_PARTING,
    "Cautious Survivor": CAUTIOUS_SURVIVOR,
    "Coordinated Clobbering": COORDINATED_CLOBBERING,
    "Cryptid Inspector": CRYPTID_INSPECTOR,
    "Defiant Survivor": DEFIANT_SURVIVOR,
    "Enduring Vitality": ENDURING_VITALITY,
    "Fear of Exposure": FEAR_OF_EXPOSURE,
    "Flesh Burrower": FLESH_BURROWER,
    "Frantic Strength": FRANTIC_STRENGTH,
    "Grasping Longneck": GRASPING_LONGNECK,
    "Greenhouse": GREENHOUSE,
    "Hauntwoods Shrieker": HAUNTWOODS_SHRIEKER,
    "Hedge Shredder": HEDGE_SHREDDER,
    "Horrid Vigor": HORRID_VIGOR,
    "House Cartographer": HOUSE_CARTOGRAPHER,
    "Insidious Fungus": INSIDIOUS_FUNGUS,
    "Kona, Rescue Beastie": KONA_RESCUE_BEASTIE,
    "Leyline of Mutation": LEYLINE_OF_MUTATION,
    "Manifest Dread": MANIFEST_DREAD,
    "Moldering Gym": MOLDERING_GYM,
    "Monstrous Emergence": MONSTROUS_EMERGENCE,
    "Omnivorous Flytrap": OMNIVOROUS_FLYTRAP,
    "Overgrown Zealot": OVERGROWN_ZEALOT,
    "Overlord of the Hauntwoods": OVERLORD_OF_THE_HAUNTWOODS,
    "Patchwork Beastie": PATCHWORK_BEASTIE,
    "Rootwise Survivor": ROOTWISE_SURVIVOR,
    "Say Its Name": SAY_ITS_NAME,
    "Slavering Branchsnapper": SLAVERING_BRANCHSNAPPER,
    "Spineseeker Centipede": SPINESEEKER_CENTIPEDE,
    "Threats Around Every Corner": THREATS_AROUND_EVERY_CORNER,
    "Twitching Doll": TWITCHING_DOLL,
    "Tyvar, the Pummeler": TYVAR_THE_PUMMELER,
    "Under the Skin": UNDER_THE_SKIN,
    "Valgavoth's Onslaught": VALGAVOTHS_ONSLAUGHT,
    "Walk-In Closet": WALKIN_CLOSET,
    "Wary Watchdog": WARY_WATCHDOG,
    "Wickerfolk Thresher": WICKERFOLK_THRESHER,
    "Arabella, Abandoned Doll": ARABELLA_ABANDONED_DOLL,
    "Baseball Bat": BASEBALL_BAT,
    "Beastie Beatdown": BEASTIE_BEATDOWN,
    "Broodspinner": BROODSPINNER,
    "Disturbing Mirth": DISTURBING_MIRTH,
    "Drag to the Roots": DRAG_TO_THE_ROOTS,
    "Fear of Infinity": FEAR_OF_INFINITY,
    "Gremlin Tamer": GREMLIN_TAMER,
    "Growing Dread": GROWING_DREAD,
    "Inquisitive Glimmer": INQUISITIVE_GLIMMER,
    "Intruding Soulrager": INTRUDING_SOULRAGER,
    "The Jolly Balloon Man": THE_JOLLY_BALLOON_MAN,
    "Kaito, Bane of Nightmares": KAITO_BANE_OF_NIGHTMARES,
    "Marina Vendrell": MARINA_VENDRELL,
    "Midnight Mayhem": MIDNIGHT_MAYHEM,
    "Nashi, Searcher in the Dark": NASHI_SEARCHER_IN_THE_DARK,
    "Niko, Light of Hope": NIKO_LIGHT_OF_HOPE,
    "Oblivious Bookworm": OBLIVIOUS_BOOKWORM,
    "Peer Past the Veil": PEER_PAST_THE_VEIL,
    "Restricted Office": RESTRICTED_OFFICE,
    "Rip, Spawn Hunter": RIP_SPAWN_HUNTER,
    "Rite of the Moth": RITE_OF_THE_MOTH,
    "Roaring Furnace": ROARING_FURNACE,
    "Sawblade Skinripper": SAWBLADE_SKINRIPPER,
    "Shrewd Storyteller": SHREWD_STORYTELLER,
    "Shroudstomper": SHROUDSTOMPER,
    "Skullsnap Nuisance": SKULLSNAP_NUISANCE,
    "Smoky Lounge": SMOKY_LOUNGE,
    "The Swarmweaver": THE_SWARMWEAVER,
    "Undead Sprinter": UNDEAD_SPRINTER,
    "Victor, Valgavoth's Seneschal": VICTOR_VALGAVOTHS_SENESCHAL,
    "Wildfire Wickerfolk": WILDFIRE_WICKERFOLK,
    "Winter, Misanthropic Guide": WINTER_MISANTHROPIC_GUIDE,
    "Zimone, All-Questioning": ZIMONE_ALLQUESTIONING,
    "Attack-in-the-Box": ATTACKINTHEBOX,
    "Bear Trap": BEAR_TRAP,
    "Conductive Machete": CONDUCTIVE_MACHETE,
    "Dissection Tools": DISSECTION_TOOLS,
    "Found Footage": FOUND_FOOTAGE,
    "Friendly Teddy": FRIENDLY_TEDDY,
    "Ghost Vacuum": GHOST_VACUUM,
    "Glimmerlight": GLIMMERLIGHT,
    "Haunted Screen": HAUNTED_SCREEN,
    "Keys to the House": KEYS_TO_THE_HOUSE,
    "Malevolent Chandelier": MALEVOLENT_CHANDELIER,
    "Marvin, Murderous Mimic": MARVIN_MURDEROUS_MIMIC,
    "Saw": SAW,
    "Abandoned Campground": ABANDONED_CAMPGROUND,
    "Blazemire Verge": BLAZEMIRE_VERGE,
    "Bleeding Woods": BLEEDING_WOODS,
    "Etched Cornfield": ETCHED_CORNFIELD,
    "Floodfarm Verge": FLOODFARM_VERGE,
    "Gloomlake Verge": GLOOMLAKE_VERGE,
    "Hushwood Verge": HUSHWOOD_VERGE,
    "Lakeside Shack": LAKESIDE_SHACK,
    "Murky Sewer": MURKY_SEWER,
    "Neglected Manor": NEGLECTED_MANOR,
    "Peculiar Lighthouse": PECULIAR_LIGHTHOUSE,
    "Raucous Carnival": RAUCOUS_CARNIVAL,
    "Razortrap Gorge": RAZORTRAP_GORGE,
    "Strangled Cemetery": STRANGLED_CEMETERY,
    "Terramorphic Expanse": TERRAMORPHIC_EXPANSE,
    "Thornspire Verge": THORNSPIRE_VERGE,
    "Valgavoth's Lair": VALGAVOTHS_LAIR,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
}

print(f"Loaded {len(DUSKMOURN_CARDS)} Duskmourn cards")
