"""
Murders at Karlov Manor (MKM) Card Implementations

Real card data fetched from Scryfall API.
279 cards in set.
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

CASE_OF_THE_SHATTERED_PACT = make_enchantment(
    name="Case of the Shattered Pact",
    mana_cost="{2}",
    colors=set(),
    text="When this Case enters, search your library for a basic land card, reveal it, put it into your hand, then shuffle.\nTo solve — There are five colors among permanents you control. (If unsolved, solve at the beginning of your end step.)\nSolved — At the beginning of combat on your turn, target creature you control gains flying, double strike, and vigilance until end of turn.",
    subtypes={"Case"},
)

ABSOLVING_LAMMASU = make_creature(
    name="Absolving Lammasu",
    power=4, toughness=3,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Lammasu"},
    text="Flying\nWhen this creature enters, all suspected creatures are no longer suspected.\nWhen this creature dies, you gain 3 life and suspect up to one target creature an opponent controls. (A suspected creature has menace and can't block.)",
)

ASSEMBLE_THE_PLAYERS = make_enchantment(
    name="Assemble the Players",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="You may look at the top card of your library any time.\nOnce each turn, you may cast a creature spell with power 2 or less from the top of your library.",
)

AURELIAS_VINDICATOR = make_creature(
    name="Aurelia's Vindicator",
    power=4, toughness=2,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying, lifelink, ward {2}\nDisguise {X}{3}{W}\nWhen this creature is turned face up, exile up to X other target creatures from the battlefield and/or creature cards from graveyards.\nWhen this creature leaves the battlefield, return the exiled cards to their owners' hands.",
)

AUSPICIOUS_ARRIVAL = make_instant(
    name="Auspicious Arrival",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 until end of turn. Investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

CALL_A_SURPRISE_WITNESS = make_sorcery(
    name="Call a Surprise Witness",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Return target creature card with mana value 3 or less from your graveyard to the battlefield. Put a flying counter on it. It's a Spirit in addition to its other types.",
)

CASE_FILE_AUDITOR = make_creature(
    name="Case File Auditor",
    power=1, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Detective", "Human"},
    text="When this creature enters and whenever you solve a Case, look at the top six cards of your library. You may reveal an enchantment card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.\nYou may spend mana as though it were mana of any color to cast Case spells.",
)

CASE_OF_THE_GATEWAY_EXPRESS = make_enchantment(
    name="Case of the Gateway Express",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="When this Case enters, choose target creature you don't control. Each creature you control deals 1 damage to that creature.\nTo solve — Three or more creatures attacked this turn. (If unsolved, solve at the beginning of your end step.)\nSolved — Creatures you control get +1/+0.",
    subtypes={"Case"},
)

CASE_OF_THE_PILFERED_PROOF = make_enchantment(
    name="Case of the Pilfered Proof",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Whenever a Detective you control enters or is turned face up, put a +1/+1 counter on it.\nTo solve — You control three or more Detectives. (If unsolved, solve at the beginning of your end step.)\nSolved — If one or more tokens would be created under your control, those tokens plus a Clue token are created instead. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    subtypes={"Case"},
)

CASE_OF_THE_UNEATEN_FEAST = make_enchantment(
    name="Case of the Uneaten Feast",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Whenever a creature you control enters, you gain 1 life.\nTo solve — You've gained 5 or more life this turn. (If unsolved, solve at the beginning of your end step.)\nSolved — Sacrifice this Case: Creature cards in your graveyard gain \"You may cast this card from your graveyard\" until end of turn.",
    subtypes={"Case"},
)

DEFENESTRATED_PHANTOM = make_creature(
    name="Defenestrated Phantom",
    power=4, toughness=3,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
    text="Flying\nDisguise {4}{W} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

DELNEY_STREETWISE_LOOKOUT = make_creature(
    name="Delney, Streetwise Lookout",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    supertypes={"Legendary"},
    text="Creatures you control with power 2 or less can't be blocked by creatures with power 3 or greater.\nIf an ability of a creature you control with power 2 or less triggers, that ability triggers an additional time.",
)

DOORKEEPER_THRULL = make_creature(
    name="Doorkeeper Thrull",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Thrull"},
    text="Flash\nFlying\nArtifacts and creatures entering don't cause abilities to trigger.",
)

DUE_DILIGENCE = make_enchantment(
    name="Due Diligence",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Enchant creature\nWhen this Aura enters, target creature you control other than enchanted creature gets +2/+2 and gains vigilance until end of turn.\nEnchanted creature gets +2/+2 and has vigilance.",
    subtypes={"Aura"},
)

ESSENCE_OF_ANTIQUITY = make_artifact_creature(
    name="Essence of Antiquity",
    power=1, toughness=10,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Golem"},
    text="Disguise {2}{W} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, creatures you control gain hexproof until end of turn. Untap them.",
)

FORUM_FAMILIAR = make_creature(
    name="Forum Familiar",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Cat"},
    text="Disguise {1}{W} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, return another target permanent you control to its owner's hand and put a +1/+1 counter on this creature.",
)

GRIFFNAUT_TRACKER = make_creature(
    name="Griffnaut Tracker",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Detective", "Human"},
    text="Flying\nWhen this creature enters, exile up to two target cards from a single graveyard.",
)

HAAZDA_VIGILANTE = make_creature(
    name="Haazda Vigilante",
    power=4, toughness=4,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Giant", "Soldier"},
    text="Whenever this creature enters or attacks, put a +1/+1 counter on target creature you control with power 2 or less.",
)

INSIDE_SOURCE = make_creature(
    name="Inside Source",
    power=1, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Citizen", "Human"},
    text="When this creature enters, create a 2/2 white and blue Detective creature token.\n{3}, {T}: Target Detective you control gets +2/+0 and gains vigilance until end of turn. Activate only as a sorcery.",
)

KARLOV_WATCHDOG = make_creature(
    name="Karlov Watchdog",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Dog"},
    text="Vigilance\nPermanents your opponents control can't be turned face up during your turn.\nWhenever you attack with three or more creatures, creatures you control get +1/+1 until end of turn.",
)

KROVOD_HAUNCH = make_artifact(
    name="Krovod Haunch",
    mana_cost="{W}",
    text="Equipped creature gets +2/+0.\n{2}, {T}, Sacrifice this Equipment: You gain 3 life.\nWhen this Equipment is put into a graveyard from the battlefield, you may pay {1}{W}. If you do, create two 1/1 white Dog creature tokens.\nEquip {2}",
    subtypes={"Equipment", "Food"},
)

MAKE_YOUR_MOVE = make_instant(
    name="Make Your Move",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Destroy target artifact, enchantment, or creature with power 4 or greater.",
)

MAKESHIFT_BINDING = make_enchantment(
    name="Makeshift Binding",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, exile target creature an opponent controls until this enchantment leaves the battlefield. You gain 2 life.",
)

MARKETWATCH_PHANTOM = make_creature(
    name="Marketwatch Phantom",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Detective", "Spirit"},
    text="Whenever another creature you control with power 2 or less enters, this creature gains flying until end of turn.",
)

MUSEUM_NIGHTWATCH = make_creature(
    name="Museum Nightwatch",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Centaur", "Soldier"},
    text="When this creature dies, create a 2/2 white and blue Detective creature token.\nDisguise {1}{W} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

NEIGHBORHOOD_GUARDIAN = make_creature(
    name="Neighborhood Guardian",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Unicorn"},
    text="Whenever another creature you control with power 2 or less enters, target creature you control gets +1/+1 until end of turn.",
)

NO_WITNESSES = make_sorcery(
    name="No Witnesses",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Each player who controls the most creatures investigates. Then destroy all creatures. (To investigate, create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

NOT_ON_MY_WATCH = make_instant(
    name="Not on My Watch",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Exile target attacking creature.",
)

NOVICE_INSPECTOR = make_creature(
    name="Novice Inspector",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Detective", "Human"},
    text="When this creature enters, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

ON_THE_JOB = make_instant(
    name="On the Job",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +2/+1 until end of turn. Investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

PERIMETER_ENFORCER = make_creature(
    name="Perimeter Enforcer",
    power=1, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Detective", "Human"},
    text="Flying, lifelink\nWhenever another Detective you control enters and whenever a Detective you control is turned face up, this creature gets +1/+1 until end of turn.",
)

SANCTUARY_WALL = make_artifact_creature(
    name="Sanctuary Wall",
    power=0, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Wall"},
    text="Defender\n{2}{W}, {T}: Tap target creature. You may put a stun counter on it. If you do, put a stun counter on this creature. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

SEASONED_CONSULTANT = make_creature(
    name="Seasoned Consultant",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Detective", "Human"},
    text="Whenever you attack with three or more creatures, this creature gets +2/+0 until end of turn.",
)

TENTH_DISTRICT_HERO = make_creature(
    name="Tenth District Hero",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human"},
    text="{1}{W}, Collect evidence 2: This creature becomes a Human Detective with base power and toughness 4/4 and gains vigilance.\n{2}{W}, Collect evidence 4: If this creature is a Detective, it becomes a legendary creature named Mileva, the Stalwart, it has base power and toughness 5/5, and it gains \"Other creatures you control have indestructible.\"",
)

UNYIELDING_GATEKEEPER = make_creature(
    name="Unyielding Gatekeeper",
    power=3, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Elephant"},
    text="Disguise {1}{W} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, exile another target nonland permanent. If you controlled it, return it to the battlefield tapped. Otherwise, its controller creates a 2/2 white and blue Detective creature token.",
)

WOJEK_INVESTIGATOR = make_creature(
    name="Wojek Investigator",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Angel", "Detective"},
    text="Flying, vigilance\nAt the beginning of your upkeep, investigate once for each opponent who has more cards in hand than you. (To investigate, create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

WRENCH = make_artifact(
    name="Wrench",
    mana_cost="{W}",
    text="Equipped creature gets +1/+1 and has vigilance and \"{3}, {T}: Tap target creature.\"\n{2}, Sacrifice this Equipment: Draw a card.\nEquip {2}",
    subtypes={"Clue", "Equipment"},
)

AGENCY_OUTFITTER = make_creature(
    name="Agency Outfitter",
    power=4, toughness=3,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Sphinx"},
    text="Flying\nWhen this creature enters, you may search your graveyard, hand and/or library for a card named Magnifying Glass and/or a card named Thinking Cap and put them onto the battlefield. If you search your library this way, shuffle.",
)

BEHIND_THE_MASK = make_instant(
    name="Behind the Mask",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="As an additional cost to cast this spell, you may collect evidence 6. (Exile cards with total mana value 6 or greater from your graveyard.)\nUntil end of turn, target artifact or creature becomes an artifact creature with base power and toughness 4/3. If evidence was collected, it has base power and toughness 1/1 until end of turn instead.",
)

BENTHIC_CRIMINOLOGISTS = make_creature(
    name="Benthic Criminologists",
    power=4, toughness=5,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="Whenever this creature enters or attacks, you may sacrifice an artifact. If you do, draw a card.",
)

BUBBLE_SMUGGLER = make_creature(
    name="Bubble Smuggler",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Fish", "Octopus"},
    text="Disguise {5}{U} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nAs this creature is turned face up, put four +1/+1 counters on it.",
)

BURDEN_OF_PROOF = make_enchantment(
    name="Burden of Proof",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Flash\nEnchant creature\nEnchanted creature gets +2/+2 as long as it's a Detective you control. Otherwise, it has base power and toughness 1/1 and can't block Detectives.",
    subtypes={"Aura"},
)

CANDLESTICK = make_artifact(
    name="Candlestick",
    mana_cost="{U}",
    text="Equipped creature gets +1/+1 and has \"Whenever this creature attacks, surveil 2.\" (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\n{2}, Sacrifice this Equipment: Draw a card.\nEquip {2}",
    subtypes={"Clue", "Equipment"},
)

CASE_OF_THE_FILCHED_FALCON = make_enchantment(
    name="Case of the Filched Falcon",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="When this Case enters, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nTo solve — You control three or more artifacts. (If unsolved, solve at the beginning of your end step.)\nSolved — {2}{U}, Sacrifice this Case: Put four +1/+1 counters on target noncreature artifact. It becomes a 0/0 Bird creature with flying in addition to its other types.",
    subtypes={"Case"},
)

CASE_OF_THE_RANSACKED_LAB = make_enchantment(
    name="Case of the Ransacked Lab",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Instant and sorcery spells you cast cost {1} less to cast.\nTo solve — You've cast four or more instant and sorcery spells this turn. (If unsolved, solve at the beginning of your end step.)\nSolved — Whenever you cast an instant or sorcery spell, draw a card.",
    subtypes={"Case"},
)

COLD_CASE_CRACKER = make_creature(
    name="Cold Case Cracker",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Spirit"},
    text="Flying\nWhen this creature dies, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

CONSPIRACY_UNRAVELER = make_creature(
    name="Conspiracy Unraveler",
    power=6, toughness=6,
    mana_cost="{5}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Sphinx"},
    text="Flying\nYou may collect evidence 10 rather than pay the mana cost for spells you cast. (To collect evidence 10, exile cards with total mana value 10 or greater from your graveyard.)",
)

COVETED_FALCON = make_artifact_creature(
    name="Coveted Falcon",
    power=1, toughness=4,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Bird"},
    text="Flying\nWhenever this creature attacks, gain control of target permanent you own but don't control.\nDisguise {1}{U}\nWhen this creature is turned face up, target opponent gains control of any number of target permanents you control. Draw a card for each one they gained control of this way.",
)

CRIMESTOPPER_SPRITE = make_creature(
    name="Crimestopper Sprite",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Faerie"},
    text="As an additional cost to cast this spell, you may collect evidence 6. (Exile cards with total mana value 6 or greater from your graveyard.)\nFlying\nWhen this creature enters, tap target creature. If evidence was collected, put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

CRYPTIC_COAT = make_artifact(
    name="Cryptic Coat",
    mana_cost="{2}{U}",
    text="When this Equipment enters, cloak the top card of your library, then attach this Equipment to it. (To cloak a card, put it onto the battlefield face down as a 2/2 creature with ward {2}. Turn it face up any time for its mana cost if it's a creature card.)\nEquipped creature gets +1/+0 and can't be blocked.\n{1}{U}: Return this Equipment to its owner's hand.",
    subtypes={"Equipment"},
)

CURIOUS_INQUIRY = make_enchantment(
    name="Curious Inquiry",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Enchant creature\nEnchanted creature gets +1/+1 and has \"Whenever this creature deals combat damage to a player, investigate.\" (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    subtypes={"Aura"},
)

DEDUCE = make_instant(
    name="Deduce",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Draw a card. Investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

DRAMATIC_ACCUSATION = make_enchantment(
    name="Dramatic Accusation",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Enchant creature\nWhen this Aura enters, tap enchanted creature.\nEnchanted creature doesn't untap during its controller's untap step.\n{U}{U}: Shuffle enchanted creature into its owner's library.",
    subtypes={"Aura"},
)

ELIMINATE_THE_IMPOSSIBLE = make_instant(
    name="Eliminate the Impossible",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Investigate. Creatures your opponents control get -2/-0 until end of turn. If any of them are suspected, they're no longer suspected. (To investigate, create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

EXIT_SPECIALIST = make_creature(
    name="Exit Specialist",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Human"},
    text="This creature can't be blocked by creatures with power 3 or greater.\nDisguise {1}{U} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, return another target creature to its owner's hand.",
)

FAE_FLIGHT = make_enchantment(
    name="Fae Flight",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Flash\nEnchant creature\nWhen this Aura enters, enchanted creature gains hexproof until end of turn.\nEnchanted creature gets +1/+0 and has flying.",
    subtypes={"Aura"},
)

FORENSIC_GADGETEER = make_creature(
    name="Forensic Gadgeteer",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Artificer", "Detective", "Vedalken"},
    text="Whenever you cast an artifact spell, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nActivated abilities of artifacts you control cost {1} less to activate. This effect can't reduce the mana in that cost to less than one mana.",
)

FORENSIC_RESEARCHER = make_creature(
    name="Forensic Researcher",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Merfolk"},
    text="{T}: Untap another target permanent you control.\n{T}, Collect evidence 3: Tap target creature you don't control. (To collect evidence 3, exile cards with total mana value 3 or greater from your graveyard.)",
)

FURTIVE_COURIER = make_creature(
    name="Furtive Courier",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Advisor", "Merfolk"},
    text="This creature can't be blocked as long as you've sacrificed an artifact this turn.\nWhenever this creature attacks, draw a card, then discard a card.",
)

HOTSHOT_INVESTIGATORS = make_creature(
    name="Hotshot Investigators",
    power=4, toughness=4,
    mana_cost="{5}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Vedalken"},
    text="When this creature enters, return up to one other target creature to its owner's hand. If you controlled it, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

INTRUDE_ON_THE_MIND = make_instant(
    name="Intrude on the Mind",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Reveal the top five cards of your library and separate them into two piles. An opponent chooses one of those piles. Put that pile into your hand and the other into your graveyard. Create a 0/0 colorless Thopter artifact creature token with flying, then put a +1/+1 counter on it for each card put into your graveyard this way.",
)

JADED_ANALYST = make_creature(
    name="Jaded Analyst",
    power=3, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Human"},
    text="Defender\nWhenever you draw your second card each turn, this creature loses defender and gains vigilance until end of turn.",
)

LIVING_CONUNDRUM = make_creature(
    name="Living Conundrum",
    power=2, toughness=5,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="Hexproof\nIf you would draw a card while your library has no cards in it, skip that draw instead.\nAs long as there are no cards in your library, this creature has base power and toughness 10/10 and has flying and vigilance.",
)

LOST_IN_THE_MAZE = make_enchantment(
    name="Lost in the Maze",
    mana_cost="{X}{U}{U}",
    colors={Color.BLUE},
    text="Flash\nWhen this enchantment enters, tap X target creatures. Put a stun counter on each of those creatures you don't control. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nTapped creatures you control have hexproof.",
)

MISTWAY_SPY = make_creature(
    name="Mistway Spy",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Merfolk"},
    text="Flying\nDisguise {1}{U} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, until end of turn, whenever a creature you control deals combat damage to a player, investigate.",
)

OUT_COLD = make_instant(
    name="Out Cold",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="This spell can't be countered. (This includes by the ward ability.)\nTap up to two target creatures and put a stun counter on each of them. Investigate. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

PROFTS_EIDETIC_MEMORY = make_enchantment(
    name="Proft's Eidetic Memory",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="When Proft's Eidetic Memory enters, draw a card.\nYou have no maximum hand size.\nAt the beginning of combat on your turn, if you've drawn more than one card this turn, put X +1/+1 counters on target creature you control, where X is the number of cards you've drawn this turn minus one.",
    supertypes={"Legendary"},
)

PROJEKTOR_INSPECTOR = make_creature(
    name="Projektor Inspector",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Human"},
    text="Whenever this creature or another Detective you control enters and whenever a Detective you control is turned face up, you may draw a card. If you do, discard a card.",
)

REASONABLE_DOUBT = make_instant(
    name="Reasonable Doubt",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {2}.\nSuspect up to one target creature. (A suspected creature has menace and can't block.)",
)

REENACT_THE_CRIME = make_instant(
    name="Reenact the Crime",
    mana_cost="{1}{U}{U}{U}",
    colors={Color.BLUE},
    text="Exile target nonland card in a graveyard that was put there from anywhere this turn. Copy it. You may cast the copy without paying its mana cost.",
)

STEAMCORE_SCHOLAR = make_creature(
    name="Steamcore Scholar",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Weird"},
    text="Flying, vigilance\nWhen this creature enters, draw two cards. Then discard two cards unless you discard an instant or sorcery card or a creature card with flying.",
)

SUDDEN_SETBACK = make_instant(
    name="Sudden Setback",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="The owner of target spell or nonland permanent puts it on their choice of the top or bottom of their library.",
)

SURVEILLANCE_MONITOR = make_creature(
    name="Surveillance Monitor",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Vedalken"},
    text="When this creature enters, you may collect evidence 4. (Exile cards with total mana value 4 or greater from your graveyard.)\nWhenever you collect evidence, create a 1/1 colorless Thopter artifact creature token with flying.",
)

UNAUTHORIZED_EXIT = make_instant(
    name="Unauthorized Exit",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target nonland permanent to its owner's hand. Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

AGENCY_CORONER = make_creature(
    name="Agency Coroner",
    power=3, toughness=6,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Ogre"},
    text="{2}{B}, Sacrifice another creature: Draw a card. If the sacrificed creature was suspected, draw two cards instead.",
)

ALLEY_ASSAILANT = make_creature(
    name="Alley Assailant",
    power=3, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Vampire"},
    text="This creature enters tapped.\nDisguise {4}{B}{B} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, target opponent loses 3 life and you gain 3 life.",
)

BARBED_SERVITOR = make_artifact_creature(
    name="Barbed Servitor",
    power=1, toughness=1,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Construct"},
    text="Indestructible\nWhen this creature enters, suspect it. (It has menace and can't block.)\nWhenever this creature deals combat damage to a player, you draw a card and you lose 1 life.\nWhenever this creature is dealt damage, target opponent loses that much life.",
)

BASILICA_STALKER = make_creature(
    name="Basilica Stalker",
    power=3, toughness=4,
    mana_cost="{5}{B}",
    colors={Color.BLACK},
    subtypes={"Detective", "Vampire"},
    text="Flying\nWhenever this creature deals combat damage to a player, you gain 1 life and surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\nDisguise {4}{B} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

CASE_OF_THE_GORGONS_KISS = make_enchantment(
    name="Case of the Gorgon's Kiss",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="When this Case enters, destroy up to one target creature that was dealt damage this turn.\nTo solve — Three or more creature cards were put into graveyards from anywhere this turn. (If unsolved, solve at the beginning of your end step.)\nSolved — This Case is a 4/4 Gorgon creature with deathtouch and lifelink in addition to its other types.",
    subtypes={"Case"},
)

CASE_OF_THE_STASHED_SKELETON = make_enchantment(
    name="Case of the Stashed Skeleton",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="When this Case enters, create a 2/1 black Skeleton creature token and suspect it. (It has menace and can't block.)\nTo solve — You control no suspected Skeletons. (If unsolved, solve at the beginning of your end step.)\nSolved — {1}{B}, Sacrifice this Case: Search your library for a card, put it into your hand, then shuffle. Activate only as a sorcery.",
    subtypes={"Case"},
)

CEREBRAL_CONFISCATION = make_sorcery(
    name="Cerebral Confiscation",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Choose one —\n• Target opponent discards two cards.\n• Target opponent reveals their hand. You choose a nonland card from it. That player discards that card.",
)

CLANDESTINE_MEDDLER = make_creature(
    name="Clandestine Meddler",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Vampire"},
    text="When this creature enters, suspect up to one other target creature you control. (A suspected creature has menace and can't block.)\nWhenever one or more suspected creatures you control attack, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

DEADLY_COVERUP = make_sorcery(
    name="Deadly Cover-Up",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, you may collect evidence 6.\nDestroy all creatures. If evidence was collected, exile a card from an opponent's graveyard. Then search its owner's graveyard, hand, and library for any number of cards with that name and exile them. That player shuffles, then draws a card for each card exiled from their hand this way.",
)

EXTRACT_A_CONFESSION = make_sorcery(
    name="Extract a Confession",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, you may collect evidence 6. (Exile cards with total mana value 6 or greater from your graveyard.)\nEach opponent sacrifices a creature of their choice. If evidence was collected, instead each opponent sacrifices a creature with the greatest power among creatures they control.",
)

FESTERLEECH = make_creature(
    name="Festerleech",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Leech", "Zombie"},
    text="Whenever this creature deals combat damage to a player, you mill two cards.\n{1}{B}: This creature gets +2/+2 until end of turn. Activate only once each turn.",
)

HOMICIDE_INVESTIGATOR = make_creature(
    name="Homicide Investigator",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Detective", "Human"},
    text="Whenever one or more nontoken creatures you control die, investigate. This ability triggers only once each turn. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

HUNTED_BONEBRUTE = make_creature(
    name="Hunted Bonebrute",
    power=6, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Beast", "Skeleton"},
    text="Menace\nWhen this creature enters, target opponent creates two 1/1 white Dog creature tokens.\nWhen this creature dies, each opponent loses 3 life.\nDisguise {1}{B}",
)

ILLICIT_MASQUERADE = make_enchantment(
    name="Illicit Masquerade",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Flash\nWhen this enchantment enters, put an impostor counter on each creature you control.\nWhenever a creature you control with an impostor counter on it dies, exile it. Return up to one other target creature card from your graveyard to the battlefield.",
)

IT_DOESNT_ADD_UP = make_instant(
    name="It Doesn't Add Up",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield. Suspect it. (It has menace and can't block.)",
)

LEAD_PIPE = make_artifact(
    name="Lead Pipe",
    mana_cost="{B}",
    text="Equipped creature gets +2/+0.\nWhenever equipped creature dies, each opponent loses 1 life.\n{2}, Sacrifice this Equipment: Draw a card.\nEquip {2}",
    subtypes={"Clue", "Equipment"},
)

LEERING_ONLOOKER = make_creature(
    name="Leering Onlooker",
    power=1, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="Flying\n{2}{B}{B}, Exile this card from your graveyard: Create two tapped 1/1 black Bat creature tokens with flying.",
)

LONG_GOODBYE = make_instant(
    name="Long Goodbye",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="This spell can't be countered. (This includes by the ward ability.)\nDestroy target creature or planeswalker with mana value 3 or less.",
)

MACABRE_RECONSTRUCTION = make_sorcery(
    name="Macabre Reconstruction",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="This spell costs {2} less to cast if a creature card was put into your graveyard from anywhere this turn.\nReturn up to two target creature cards from your graveyard to your hand.",
)

MASSACRE_GIRL_KNOWN_KILLER = make_creature(
    name="Massacre Girl, Known Killer",
    power=4, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Human"},
    supertypes={"Legendary"},
    text="Menace\nCreatures you control have wither. (They deal damage to creatures in the form of -1/-1 counters.)\nWhenever a creature an opponent controls dies, if its toughness was less than 1, draw a card.",
)

MURDER = make_instant(
    name="Murder",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature.",
)

NIGHTDRINKER_MOROII = make_creature(
    name="Nightdrinker Moroii",
    power=4, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="Flying\nWhen this creature enters, you lose 3 life.\nDisguise {B}{B} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

OUTRAGEOUS_ROBBERY = make_instant(
    name="Outrageous Robbery",
    mana_cost="{X}{B}{B}",
    colors={Color.BLACK},
    text="Target opponent exiles the top X cards of their library face down. You may look at and play those cards for as long as they remain exiled. If you cast a spell this way, you may spend mana as though it were mana of any type to cast it.",
)

PERSUASIVE_INTERROGATORS = make_creature(
    name="Persuasive Interrogators",
    power=5, toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Detective", "Gorgon"},
    text="When this creature enters, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nWhenever you sacrifice a Clue, target opponent gets two poison counters. (A player with ten or more poison counters loses the game.)",
)

POLYGRAPH_ORB = make_artifact(
    name="Polygraph Orb",
    mana_cost="{4}{B}",
    text="When this artifact enters, look at the top four cards of your library. Put two of them into your hand and the rest into your graveyard. You lose 2 life.\n{2}, {T}, Collect evidence 3: Each opponent loses 3 life unless they discard a card or sacrifice a creature. (To collect evidence 3, exile cards with total mana value 3 or greater from your graveyard.)",
)

PRESUMED_DEAD = make_instant(
    name="Presumed Dead",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Until end of turn, target creature gets +2/+0 and gains \"When this creature dies, return it to the battlefield under its owner's control and suspect it.\" (A suspected creature has menace and can't block.)",
)

REPEAT_OFFENDER = make_creature(
    name="Repeat Offender",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Human"},
    text="{2}{B}: If this creature is suspected, put a +1/+1 counter on it. Otherwise, suspect it. (A suspected creature has menace and can't block.)",
)

ROT_FARM_MORTIPEDE = make_creature(
    name="Rot Farm Mortipede",
    power=3, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Insect"},
    text="Whenever one or more creature cards leave your graveyard, this creature gets +1/+0 and gains menace and lifelink until end of turn.",
)

SLICE_FROM_THE_SHADOWS = make_instant(
    name="Slice from the Shadows",
    mana_cost="{X}{B}",
    colors={Color.BLACK},
    text="This spell can't be countered. (This includes by the ward ability.)\nTarget creature gets -X/-X until end of turn.",
)

SLIMY_DUALLEECH = make_creature(
    name="Slimy Dualleech",
    power=2, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Leech"},
    text="At the beginning of combat on your turn, target creature you control with power 2 or less gets +1/+0 and gains deathtouch until end of turn.",
)

SNARLING_GOREHOUND = make_creature(
    name="Snarling Gorehound",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Dog"},
    text="Menace\nWhenever another creature you control with power 2 or less enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

SOUL_ENERVATION = make_enchantment(
    name="Soul Enervation",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Flash\nWhen this enchantment enters, target creature gets -4/-4 until end of turn.\nWhenever one or more creature cards leave your graveyard, each opponent loses 1 life and you gain 1 life.",
)

TOXIN_ANALYSIS = make_instant(
    name="Toxin Analysis",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gains deathtouch and lifelink until end of turn. Investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

UNDERCITY_ELIMINATOR = make_creature(
    name="Undercity Eliminator",
    power=3, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Gorgon"},
    text="When this creature enters, you may sacrifice an artifact or creature. When you do, exile target creature an opponent controls.",
)

UNSCRUPULOUS_AGENT = make_creature(
    name="Unscrupulous Agent",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Detective", "Elf"},
    text="When this creature enters, target opponent exiles a card from their hand.",
)

VEIN_RIPPER = make_creature(
    name="Vein Ripper",
    power=6, toughness=5,
    mana_cost="{3}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Vampire"},
    text="Flying\nWard—Sacrifice a creature.\nWhenever a creature dies, target opponent loses 2 life and you gain 2 life.",
)

ANZRAGS_RAMPAGE = make_sorcery(
    name="Anzrag's Rampage",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Destroy all artifacts you don't control, then exile the top X cards of your library, where X is the number of artifacts that were put into graveyards from the battlefield this turn. You may put a creature card exiled this way onto the battlefield. It gains haste. Return it to your hand at the beginning of the next end step.",
)

BOLRACCLAN_BASHER = make_creature(
    name="Bolrac-Clan Basher",
    power=3, toughness=2,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Cyclops", "Warrior"},
    text="Double strike, trample\nDisguise {3}{R}{R} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

CASE_OF_THE_BURNING_MASKS = make_enchantment(
    name="Case of the Burning Masks",
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    text="When this Case enters, it deals 3 damage to target creature an opponent controls.\nTo solve — Three or more sources you controlled dealt damage this turn. (If unsolved, solve at the beginning of your end step.)\nSolved — Sacrifice this Case: Exile the top three cards of your library. Choose one of them. You may play that card this turn.",
    subtypes={"Case"},
)

CASE_OF_THE_CRIMSON_PULSE = make_enchantment(
    name="Case of the Crimson Pulse",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="When this Case enters, discard a card, then draw two cards.\nTo solve — You have no cards in hand. (If unsolved, solve at the beginning of your end step.)\nSolved — At the beginning of your upkeep, discard your hand, then draw two cards.",
    subtypes={"Case"},
)

CAUGHT_REDHANDED = make_instant(
    name="Caught Red-Handed",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="This spell can't be countered. (This includes by the ward ability.)\nGain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. Suspect it. (It has menace and can't block.)",
)

THE_CHASE_IS_ON = make_instant(
    name="The Chase Is On",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains first strike until end of turn. Investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

CONCEALED_WEAPON = make_artifact(
    name="Concealed Weapon",
    mana_cost="{1}{R}",
    text="Equipped creature gets +3/+0.\nDisguise {2}{R} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this Equipment is turned face up, attach it to target creature you control.\nEquip {1}{R}",
    subtypes={"Equipment"},
)

CONNECTING_THE_DOTS = make_enchantment(
    name="Connecting the Dots",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Whenever a creature you control attacks, exile the top card of your library face down. (You can't look at it.)\n{1}{R}, Discard your hand, Sacrifice this enchantment: Put all cards exiled with this enchantment into their owners' hands.",
)

CONVENIENT_TARGET = make_enchantment(
    name="Convenient Target",
    mana_cost="{R}",
    colors={Color.RED},
    text="Enchant creature\nWhen this Aura enters, suspect enchanted creature. (It has menace and can't block.)\nEnchanted creature gets +1/+1.\n{2}{R}: Return this card from your graveyard to your hand.",
    subtypes={"Aura"},
)

CORNERED_CROOK = make_creature(
    name="Cornered Crook",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Warrior"},
    text="When this creature enters, you may sacrifice an artifact. When you do, this creature deals 3 damage to any target.",
)

CRIME_NOVELIST = make_creature(
    name="Crime Novelist",
    power=1, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Bard", "Goblin"},
    text="Whenever you sacrifice an artifact, put a +1/+1 counter on this creature and add {R}.",
)

DEMAND_ANSWERS = make_instant(
    name="Demand Answers",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="As an additional cost to cast this spell, sacrifice an artifact or discard a card.\nDraw two cards.",
)

EXPEDITED_INHERITANCE = make_enchantment(
    name="Expedited Inheritance",
    mana_cost="{R}{R}",
    colors={Color.RED},
    text="Whenever a creature is dealt damage, its controller may exile that many cards from the top of their library. They may play those cards until the end of their next turn.",
)

EXPOSE_THE_CULPRIT = make_instant(
    name="Expose the Culprit",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Choose one or both —\n• Turn target face-down creature face up.\n• Exile any number of face-up creatures you control with disguise in a face-down pile, shuffle that pile, then cloak them. (To cloak a card, put it onto the battlefield face down as a 2/2 creature with ward {2}. Turn it face up any time for its mana cost if it's a creature card.)",
)

FELONIOUS_RAGE = make_instant(
    name="Felonious Rage",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature you control gets +2/+0 and gains haste until end of turn. When that creature dies this turn, create a 2/2 white and blue Detective creature token.",
)

FRANTIC_SCAPEGOAT = make_creature(
    name="Frantic Scapegoat",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goat"},
    text="Haste\nWhen this creature enters, suspect it. (It has menace and can't block.)\nWhenever one or more other creatures you control enter, if this creature is suspected, you may suspect one of the other creatures. If you do, this creature is no longer suspected.",
)

FUGITIVE_CODEBREAKER = make_creature(
    name="Fugitive Codebreaker",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Rogue"},
    text="Prowess, haste\nDisguise {5}{R}. This cost is reduced by {1} for each instant and sorcery card in your graveyard. (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, discard your hand, then draw three cards.",
)

GALVANIZE = make_instant(
    name="Galvanize",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Galvanize deals 3 damage to target creature. If you've drawn two or more cards this turn, Galvanize deals 5 damage to that creature instead.",
)

GEARBANE_ORANGUTAN = make_creature(
    name="Gearbane Orangutan",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Ape"},
    text="Reach\nWhen this creature enters, choose one —\n• Destroy up to one target artifact.\n• Sacrifice an artifact. If you do, put two +1/+1 counters on this creature.",
)

GOBLIN_MASKMAKER = make_creature(
    name="Goblin Maskmaker",
    power=1, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Citizen", "Goblin"},
    text="Whenever this creature attacks, face-down spells you cast this turn cost {1} less to cast.",
)

HARRIED_DRONESMITH = make_creature(
    name="Harried Dronesmith",
    power=2, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Artificer", "Human"},
    text="At the beginning of combat on your turn, create a 1/1 colorless Thopter artifact creature token with flying. It gains haste until end of turn. Sacrifice it at the beginning of your next end step.",
)

INCINERATOR_OF_THE_GUILTY = make_creature(
    name="Incinerator of the Guilty",
    power=6, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying, trample\nWhenever this creature deals combat damage to a player, you may collect evidence X. When you do, this creature deals X damage to each creature and planeswalker that player controls. (To collect evidence X, exile cards with total mana value X or greater from your graveyard.)",
)

INNOCENT_BYSTANDER = make_creature(
    name="Innocent Bystander",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Citizen", "Goblin"},
    text="Whenever this creature is dealt 3 or more damage, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

KNIFE = make_artifact(
    name="Knife",
    mana_cost="{R}",
    text="During your turn, equipped creature gets +1/+0 and has first strike.\n{2}, Sacrifice this Equipment: Draw a card.\nEquip {2}",
    subtypes={"Clue", "Equipment"},
)

KRENKO_BARON_OF_TIN_STREET = make_creature(
    name="Krenko, Baron of Tin Street",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
    supertypes={"Legendary"},
    text="Haste\n{T}, Sacrifice an artifact: Put a +1/+1 counter on each Goblin you control.\nWhenever an artifact is put into a graveyard from the battlefield, you may pay {R}. If you do, create a 1/1 red Goblin creature token. It gains haste until end of turn.",
)

KRENKOS_BUZZCRUSHER = make_artifact_creature(
    name="Krenko's Buzzcrusher",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Insect", "Thopter"},
    text="Flying, trample\nWhen this creature enters, for each player, destroy up to one nonbasic land that player controls. For each land destroyed this way, its controller may search their library for a basic land card, put it onto the battlefield tapped, then shuffle.",
)

LAMPLIGHT_PHOENIX = make_creature(
    name="Lamplight Phoenix",
    power=3, toughness=3,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Phoenix"},
    text="Flying\nWhen this creature dies, you may exile it and collect evidence 4. If you do, return this card to the battlefield tapped. (To collect evidence 4, exile cards with total mana value 4 or greater from your graveyard.)",
)

OFFENDER_AT_LARGE = make_creature(
    name="Offender at Large",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Giant", "Rogue"},
    text="Disguise {4}{R} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature enters or is turned face up, up to one target creature gets +2/+0 until end of turn.",
)

PERSON_OF_INTEREST = make_creature(
    name="Person of Interest",
    power=2, toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rogue"},
    text="When this creature enters, suspect it. Create a 2/2 white and blue Detective creature token. (A suspected creature has menace and can't block.)",
)

PYROTECHNIC_PERFORMER = make_creature(
    name="Pyrotechnic Performer",
    power=3, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Assassin", "Lizard"},
    text="Disguise {R} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhenever this creature or another creature you control is turned face up, that creature deals damage equal to its power to each opponent.",
)

RECKLESS_DETECTIVE = make_creature(
    name="Reckless Detective",
    power=0, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Detective", "Devil"},
    text="Whenever this creature attacks, you may sacrifice an artifact or discard a card. If you do, draw a card and this creature gets +2/+0 until end of turn.",
)

RED_HERRING = make_artifact_creature(
    name="Red Herring",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Clue", "Fish"},
    text="Haste\nThis creature attacks each combat if able.\n{2}, Sacrifice this creature: Draw a card.",
)

RUBBLEBELT_BRAGGART = make_creature(
    name="Rubblebelt Braggart",
    power=5, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Warrior"},
    text="Whenever this creature attacks, if it's not suspected, you may suspect it. (A suspected creature has menace and can't block.)",
)

SHOCK = make_instant(
    name="Shock",
    mana_cost="{R}",
    colors={Color.RED},
    text="Shock deals 2 damage to any target.",
)

SUSPICIOUS_DETONATION = make_sorcery(
    name="Suspicious Detonation",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="This spell costs {3} less to cast if you've sacrificed an artifact this turn.\nThis spell can't be countered. (This includes by the ward ability.)\nSuspicious Detonation deals 4 damage to target creature.",
)

TORCH_THE_WITNESS = make_sorcery(
    name="Torch the Witness",
    mana_cost="{X}{R}",
    colors={Color.RED},
    text="Torch the Witness deals twice X damage to target creature. If excess damage was dealt to that creature this way, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

VENGEFUL_TRACKER = make_creature(
    name="Vengeful Tracker",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Detective", "Human"},
    text="Whenever an opponent sacrifices an artifact, this creature deals 2 damage to them.",
)

AFTERMATH_ANALYST = make_creature(
    name="Aftermath Analyst",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Detective", "Elf"},
    text="When this creature enters, mill three cards. (Put the top three cards of your library into your graveyard.)\n{3}{G}, Sacrifice this creature: Return all land cards from your graveyard to the battlefield tapped.",
)

AIRTIGHT_ALIBI = make_enchantment(
    name="Airtight Alibi",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Flash\nEnchant creature\nWhen this Aura enters, untap enchanted creature. It gains hexproof until end of turn. If it's suspected, it's no longer suspected.\nEnchanted creature gets +2/+2 and can't become suspected.",
    subtypes={"Aura"},
)

ANALYZE_THE_POLLEN = make_sorcery(
    name="Analyze the Pollen",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="As an additional cost to cast this spell, you may collect evidence 8. (Exile cards with total mana value 8 or greater from your graveyard.)\nSearch your library for a basic land card. If evidence was collected, instead search your library for a creature or land card. Reveal that card, put it into your hand, then shuffle.",
)

ARCHDRUIDS_CHARM = make_instant(
    name="Archdruid's Charm",
    mana_cost="{G}{G}{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Search your library for a creature or land card and reveal it. Put it onto the battlefield tapped if it's a land card. Otherwise, put it into your hand. Then shuffle.\n• Put a +1/+1 counter on target creature you control. It deals damage equal to its power to target creature you don't control.\n• Exile target artifact or enchantment.",
)

AUDIENCE_WITH_TROSTANI = make_sorcery(
    name="Audience with Trostani",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Create a 0/1 green Plant creature token, then draw cards equal to the number of differently named creature tokens you control.",
)

AXEBANE_FEROX = make_creature(
    name="Axebane Ferox",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Deathtouch, haste\nWard—Collect evidence 4. (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player exiles cards with total mana value 4 or greater from their graveyard.)",
)

BITE_DOWN_ON_CRIME = make_sorcery(
    name="Bite Down on Crime",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="As an additional cost to cast this spell, you may collect evidence 6. This spell costs {2} less to cast if evidence was collected. (To collect evidence 6, exile cards with total mana value 6 or greater from your graveyard.)\nTarget creature you control gets +2/+0 until end of turn. It deals damage equal to its power to target creature you don't control.",
)

CASE_OF_THE_LOCKED_HOTHOUSE = make_enchantment(
    name="Case of the Locked Hothouse",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="You may play an additional land on each of your turns.\nTo solve — You control seven or more lands. (If unsolved, solve at the beginning of your end step.)\nSolved — You may look at the top card of your library any time, and you may play lands and cast creature and enchantment spells from the top of your library.",
    subtypes={"Case"},
)

CASE_OF_THE_TRAMPLED_GARDEN = make_enchantment(
    name="Case of the Trampled Garden",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="When this Case enters, distribute two +1/+1 counters among one or two target creatures you control.\nTo solve — Creatures you control have total power 8 or greater. (If unsolved, solve at the beginning of your end step.)\nSolved — Whenever you attack, put a +1/+1 counter on target attacking creature. It gains trample until end of turn.",
    subtypes={"Case"},
)

CHALK_OUTLINE = make_enchantment(
    name="Chalk Outline",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Whenever one or more creature cards leave your graveyard, create a 2/2 white and blue Detective creature token, then investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

CULVERT_AMBUSHER = make_creature(
    name="Culvert Ambusher",
    power=4, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Horror", "Wurm"},
    text="When this creature enters or is turned face up, target creature blocks this turn if able.\nDisguise {4}{G} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

FANATICAL_STRENGTH = make_instant(
    name="Fanatical Strength",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 and gains trample until end of turn.",
)

FLOURISHING_BLOOMKIN = make_creature(
    name="Flourishing Bloom-Kin",
    power=0, toughness=0,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental", "Plant"},
    text="This creature gets +1/+1 for each Forest you control.\nDisguise {4}{G}\nWhen this creature is turned face up, search your library for up to two Forest cards and reveal them. Put one of them onto the battlefield tapped and the other into your hand, then shuffle.",
)

GET_A_LEG_UP = make_instant(
    name="Get a Leg Up",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Until end of turn, target creature gets +1/+1 for each creature you control and gains reach.",
)

GLINT_WEAVER = make_creature(
    name="Glint Weaver",
    power=3, toughness=3,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Spider"},
    text="Reach\nWhen this creature enters, distribute three +1/+1 counters among one, two, or three target creatures, then you gain life equal to the greatest toughness among creatures you control.",
)

GREENBELT_RADICAL = make_creature(
    name="Greenbelt Radical",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Centaur", "Citizen"},
    text="Disguise {5}{G}{G} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, put a +1/+1 counter on each creature you control. Creatures you control gain trample until end of turn.",
)

HARDHITTING_QUESTION = make_sorcery(
    name="Hard-Hitting Question",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature you control deals damage equal to its power to target creature or planeswalker you don't control.",
)

HEDGE_WHISPERER = make_creature(
    name="Hedge Whisperer",
    power=0, toughness=3,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Detective", "Druid", "Elf"},
    text="You may choose not to untap this creature during your untap step.\n{3}{G}, {T}, Collect evidence 4: Target land you control becomes a 5/5 green Plant Boar creature with haste for as long as this creature remains tapped. It's still a land. Activate only as a sorcery. (To collect evidence 4, exile cards with total mana value 4 or greater from your graveyard.)",
)

HIDE_IN_PLAIN_SIGHT = make_sorcery(
    name="Hide in Plain Sight",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Look at the top five cards of your library, cloak two of them, and put the rest on the bottom of your library in a random order. (To cloak a card, put it onto the battlefield face down as a 2/2 creature with ward {2}. Turn it face up any time for its mana cost if it's a creature card.)",
)

A_KILLER_AMONG_US = make_enchantment(
    name="A Killer Among Us",
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, create a 1/1 white Human creature token, a 1/1 blue Merfolk creature token, and a 1/1 red Goblin creature token. Then secretly choose Human, Merfolk, or Goblin.\nSacrifice this enchantment, Reveal the creature type you chose: If target attacking creature token is the chosen type, put three +1/+1 counters on it and it gains deathtouch until end of turn.",
)

LOXODON_EAVESDROPPER = make_creature(
    name="Loxodon Eavesdropper",
    power=3, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Detective", "Elephant"},
    text="When this creature enters, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nWhenever you draw your second card each turn, this creature gets +1/+1 and gains vigilance until end of turn.",
)

NERVOUS_GARDENER = make_creature(
    name="Nervous Gardener",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Dryad"},
    text="Disguise {G} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, search your library for a land card with a basic land type, reveal it, put it into your hand, then shuffle.",
)

PICK_YOUR_POISON = make_sorcery(
    name="Pick Your Poison",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Each opponent sacrifices an artifact of their choice.\n• Each opponent sacrifices an enchantment of their choice.\n• Each opponent sacrifices a creature with flying of their choice.",
)

POMPOUS_GADABOUT = make_creature(
    name="Pompous Gadabout",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Citizen", "Human"},
    text="During your turn, this creature has hexproof.\nThis creature can't be blocked by creatures that don't have a name.",
)

THE_PRIDE_OF_HULL_CLADE = make_creature(
    name="The Pride of Hull Clade",
    power=2, toughness=15,
    mana_cost="{10}{G}",
    colors={Color.GREEN},
    subtypes={"Crocodile", "Elk", "Turtle"},
    supertypes={"Legendary"},
    text="This spell costs {X} less to cast, where X is the total toughness of creatures you control.\nDefender\n{2}{U}{U}: Until end of turn, target creature you control gets +1/+0, gains \"Whenever this creature deals combat damage to a player, draw cards equal to its toughness,\" and can attack as though it didn't have defender.",
)

ROPE = make_artifact(
    name="Rope",
    mana_cost="{G}",
    text="Equipped creature gets +1/+2, has reach, and can't be blocked by more than one creature.\n{2}, Sacrifice this Equipment: Draw a card.\nEquip {3}",
    subtypes={"Clue", "Equipment"},
)

RUBBLEBELT_MAVERICK = make_creature(
    name="Rubblebelt Maverick",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Detective", "Human"},
    text="When this creature enters, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\n{G}, Exile this card from your graveyard: Put a +1/+1 counter on target creature. Activate only as a sorcery.",
)

SAMPLE_COLLECTOR = make_creature(
    name="Sample Collector",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Detective", "Troll"},
    text="Whenever this creature attacks, you may collect evidence 3. When you do, put a +1/+1 counter on target creature you control. (To collect evidence 3, exile cards with total mana value 3 or greater from your graveyard.)",
)

SHARPEYED_ROOKIE = make_creature(
    name="Sharp-Eyed Rookie",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Detective", "Human"},
    text="Vigilance\nWhenever a creature you control enters, if its power is greater than this creature's power or its toughness is greater than this creature's toughness, put a +1/+1 counter on this creature and investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

SLIME_AGAINST_HUMANITY = make_sorcery(
    name="Slime Against Humanity",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Create a 0/0 green Ooze creature token with trample. Put X +1/+1 counters on it, where X is two plus the total number of cards you own in exile and in your graveyard that are Oozes or are named Slime Against Humanity.\nA deck can have any number of cards named Slime Against Humanity.",
)

THEY_WENT_THIS_WAY = make_sorcery(
    name="They Went This Way",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. Investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

TOPIARY_PANTHER = make_creature(
    name="Topiary Panther",
    power=6, toughness=5,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Cat", "Plant"},
    text="Trample\nBasic landcycling {1}{G} ({1}{G}, Discard this card: Search your library for a basic land card, reveal it, put it into your hand, then shuffle.)",
)

TUNNEL_TIPSTER = make_creature(
    name="Tunnel Tipster",
    power=1, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Mole", "Scout"},
    text="At the beginning of your end step, if a face-down creature entered the battlefield under your control this turn, put a +1/+1 counter on this creature.\n{T}: Add {G}.",
)

UNDERGROWTH_RECON = make_enchantment(
    name="Undergrowth Recon",
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    text="At the beginning of your upkeep, return target land card from your graveyard to the battlefield tapped.",
)

VENGEFUL_CREEPER = make_creature(
    name="Vengeful Creeper",
    power=5, toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental", "Plant"},
    text="Disguise {5}{G} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, destroy target artifact or enchantment an opponent controls.",
)

VITUGHAZI_INSPECTOR = make_creature(
    name="Vitu-Ghazi Inspector",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Detective", "Elf"},
    text="As an additional cost to cast this spell, you may collect evidence 6. (Exile cards with total mana value 6 or greater from your graveyard.)\nReach\nWhen this creature enters, if evidence was collected, put a +1/+1 counter on target creature and you gain 2 life.",
)

AGRUS_KOS_SPIRIT_OF_JUSTICE = make_creature(
    name="Agrus Kos, Spirit of Justice",
    power=2, toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Detective", "Spirit"},
    supertypes={"Legendary"},
    text="Double strike, vigilance\nWhenever Agrus Kos enters or attacks, choose up to one target creature. If it's suspected, exile it. Otherwise, suspect it. (A suspected creature has menace and can't block.)",
)

ALQUIST_PROFT_MASTER_SLEUTH = make_creature(
    name="Alquist Proft, Master Sleuth",
    power=3, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Detective", "Human"},
    supertypes={"Legendary"},
    text="Vigilance\nWhen Alquist Proft enters, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\n{X}{W}{U}{U}, {T}, Sacrifice a Clue: You draw X cards and gain X life.",
)

ANZRAG_THE_QUAKEMOLE = make_creature(
    name="Anzrag, the Quake-Mole",
    power=8, toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"God", "Mole"},
    supertypes={"Legendary"},
    text="Whenever Anzrag becomes blocked, untap each creature you control. After this phase, there is an additional combat phase.\n{3}{R}{R}{G}{G}: Anzrag must be blocked each combat this turn if able.",
)

ASSASSINS_TROPHY = make_instant(
    name="Assassin's Trophy",
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Destroy target permanent an opponent controls. Its controller may search their library for a basic land card, put it onto the battlefield, then shuffle.",
)

AURELIA_THE_LAW_ABOVE = make_creature(
    name="Aurelia, the Law Above",
    power=4, toughness=4,
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Angel"},
    supertypes={"Legendary"},
    text="Flying, vigilance, haste\nWhenever a player attacks with three or more creatures, you draw a card.\nWhenever a player attacks with five or more creatures, Aurelia deals 3 damage to each of your opponents and you gain 3 life.",
)

BLOOD_SPATTER_ANALYSIS = make_enchantment(
    name="Blood Spatter Analysis",
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="When this enchantment enters, it deals 3 damage to target creature an opponent controls.\nWhenever one or more creatures die, mill a card and put a bloodstain counter on this enchantment. Then sacrifice it if it has five or more bloodstain counters on it. When you do, return target creature card from your graveyard to your hand.",
)

BREAK_OUT = make_sorcery(
    name="Break Out",
    mana_cost="{R}{G}",
    colors={Color.GREEN, Color.RED},
    text="Look at the top six cards of your library. You may reveal a creature card from among them. If that card has mana value 2 or less, you may put it onto the battlefield and it gains haste until end of turn. If you didn't put the revealed card onto the battlefield this way, put it into your hand. Put the rest on the bottom of your library in a random order.",
)

BURIED_IN_THE_GARDEN = make_enchantment(
    name="Buried in the Garden",
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Enchant land\nWhen this Aura enters, exile target nonland permanent you don't control until this Aura leaves the battlefield.\nWhenever enchanted land is tapped for mana, its controller adds an additional one mana of any color.",
    subtypes={"Aura"},
)

COERCED_TO_KILL = make_enchantment(
    name="Coerced to Kill",
    mana_cost="{3}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    text="Enchant creature\nYou control enchanted creature.\nEnchanted creature has base power and toughness 1/1, has deathtouch, and is an Assassin in addition to its other types.",
    subtypes={"Aura"},
)

CROWDCONTROL_WARDEN = make_creature(
    name="Crowd-Control Warden",
    power=4, toughness=4,
    mana_cost="{3}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Centaur", "Soldier"},
    text="As this creature enters or is turned face up, put X +1/+1 counters on it, where X is the number of other creatures you control.\nDisguise {3}{G/W}{G/W} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

CURIOUS_CADAVER = make_creature(
    name="Curious Cadaver",
    power=3, toughness=1,
    mana_cost="{2}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Detective", "Zombie"},
    text="Flying\nWhen you sacrifice a Clue, return this card from your graveyard to your hand.",
)

DEADLY_COMPLICATION = make_sorcery(
    name="Deadly Complication",
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Choose one or both —\n• Destroy target creature.\n• Put a +1/+1 counter on target suspected creature you control. You may have it become no longer suspected.",
)

DETECTIVES_SATCHEL = make_artifact(
    name="Detective's Satchel",
    mana_cost="{2}{U}{R}",
    text="When this artifact enters, investigate twice. (To investigate, create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\n{T}: Create a 1/1 colorless Thopter artifact creature token with flying. Activate only if you've sacrificed an artifact this turn.",
)

DOG_WALKER = make_creature(
    name="Dog Walker",
    power=3, toughness=1,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Citizen", "Human"},
    text="Vigilance\nDisguise {R/W}{R/W} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, create two tapped 1/1 white Dog creature tokens.",
)

DOPPELGANG = make_sorcery(
    name="Doppelgang",
    mana_cost="{X}{X}{X}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    text="For each of X target permanents, create X tokens that are copies of that permanent.",
)

DRAG_THE_CANAL = make_instant(
    name="Drag the Canal",
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    text="Create a 2/2 white and blue Detective creature token. If a creature died this turn, you gain 2 life, surveil 2, then investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

ETRATA_DEADLY_FUGITIVE = make_creature(
    name="Etrata, Deadly Fugitive",
    power=1, toughness=4,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Assassin", "Vampire"},
    supertypes={"Legendary"},
    text="Deathtouch\nFace-down creatures you control have \"{2}{U}{B}: Turn this creature face up. If you can't, exile it, then you may cast the exiled card without paying its mana cost.\"\nWhenever an Assassin you control deals combat damage to an opponent, cloak the top card of that player's library.",
)

EVIDENCE_EXAMINER = make_creature(
    name="Evidence Examiner",
    power=2, toughness=2,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Detective", "Merfolk"},
    text="At the beginning of combat on your turn, you may collect evidence 4. (Exile cards with total mana value 4 or greater from your graveyard.)\nWhenever you collect evidence, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

EZRIM_AGENCY_CHIEF = make_creature(
    name="Ezrim, Agency Chief",
    power=5, toughness=5,
    mana_cost="{1}{W}{W}{U}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Archon", "Detective"},
    supertypes={"Legendary"},
    text="Flying\nWhen Ezrim enters, investigate twice. (To investigate, create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\n{1}, Sacrifice an artifact: Ezrim gains your choice of vigilance, lifelink, or hexproof until end of turn.",
)

FAERIE_SNOOP = make_creature(
    name="Faerie Snoop",
    power=1, toughness=4,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Detective", "Faerie"},
    text="Flying\nDisguise {1}{U/B}{U/B} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, look at the top two cards of your library. Put one into your hand and the other into your graveyard.",
)

GADGET_TECHNICIAN = make_creature(
    name="Gadget Technician",
    power=3, toughness=2,
    mana_cost="{2}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Artificer", "Goblin"},
    text="When this creature enters or is turned face up, create a 1/1 colorless Thopter artifact creature token with flying.\nDisguise {U/R}{U/R} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

GLEAMING_GEARDRAKE = make_artifact_creature(
    name="Gleaming Geardrake",
    power=1, toughness=1,
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Drake"},
    text="Flying\nWhen this creature enters, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nWhenever you sacrifice an artifact, put a +1/+1 counter on this creature.",
)

GRANITE_WITNESS = make_artifact_creature(
    name="Granite Witness",
    power=3, toughness=2,
    mana_cost="{2}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Detective", "Gargoyle"},
    text="Flying, vigilance\nDisguise {W/U}{W/U} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, you may tap or untap target creature.",
)

ILLTIMED_EXPLOSION = make_sorcery(
    name="Ill-Timed Explosion",
    mana_cost="{2}{U}{R}",
    colors={Color.RED, Color.BLUE},
    text="Draw two cards. Then you may discard two cards. When you do, Ill-Timed Explosion deals X damage to each creature, where X is the greatest mana value among cards discarded this way.",
)

INSIDIOUS_ROOTS = make_enchantment(
    name="Insidious Roots",
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Creature tokens you control have \"{T}: Add one mana of any color.\"\nWhenever one or more creature cards leave your graveyard, create a 0/1 green Plant creature token, then put a +1/+1 counter on each Plant you control.",
)

IZONI_CENTER_OF_THE_WEB = make_creature(
    name="Izoni, Center of the Web",
    power=5, toughness=4,
    mana_cost="{4}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Detective", "Elf"},
    supertypes={"Legendary"},
    text="Menace\nWhenever Izoni enters or attacks, you may collect evidence 4. If you do, create two 2/1 black and green Spider creature tokens with menace and reach.\nSacrifice four tokens: Surveil 2, then draw two cards. You gain 2 life.",
)

JUDITH_CARNAGE_CONNOISSEUR = make_creature(
    name="Judith, Carnage Connoisseur",
    power=3, toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Shaman"},
    supertypes={"Legendary"},
    text="Whenever you cast an instant or sorcery spell, choose one —\n• That spell gains deathtouch and lifelink.\n• Create a 2/2 red Imp creature token with \"When this token dies, it deals 2 damage to each opponent.\"",
)

KAYA_SPIRITS_JUSTICE = make_planeswalker(
    name="Kaya, Spirits' Justice",
    mana_cost="{2}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    loyalty=3,
    subtypes={"Kaya"},
    supertypes={"Legendary"},
    text="Whenever one or more creatures you control and/or creature cards in your graveyard are put into exile, you may choose a creature card from among them. Until end of turn, target token you control becomes a copy of it, except it has flying.\n+2: Surveil 2, then exile a card from a graveyard.\n+1: Create a 1/1 white and black Spirit creature token with flying.\n−2: Exile target creature you control. For each other player, exile up to one target creature that player controls.",
)

KELLAN_INQUISITIVE_PRODIGY = make_creature(
    name="Kellan, Inquisitive Prodigy",
    power=3, toughness=4,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Detective", "Faerie", "Human"},
    supertypes={"Legendary"},
    text="Flying, vigilance\nWhenever Kellan attacks, destroy up to one target artifact. If you controlled that permanent, draw a card.\n// Adventure — Tail the Suspect {G}{U}\nInvestigate. You may play an additional land this turn. (Then exile this card. You may cast the creature later from exile.)",
)

KRAUL_WHIPCRACKER = make_creature(
    name="Kraul Whipcracker",
    power=3, toughness=2,
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Assassin", "Insect"},
    text="Reach\nWhen this creature enters, destroy target token an opponent controls.",
)

KYLOX_VISIONARY_INVENTOR = make_creature(
    name="Kylox, Visionary Inventor",
    power=4, toughness=4,
    mana_cost="{5}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Artificer", "Lizard"},
    supertypes={"Legendary"},
    text="Menace, ward {2}, haste\nWhenever Kylox attacks, sacrifice any number of other creatures, then exile the top X cards of your library, where X is their total power. You may cast any number of instant and/or sorcery spells from among the exiled cards without paying their mana costs.",
)

KYLOXS_VOLTSTRIDER = make_artifact(
    name="Kylox's Voltstrider",
    mana_cost="{1}{U}{R}",
    text="Collect evidence 6: This Vehicle becomes an artifact creature until end of turn.\nWhenever this Vehicle attacks, you may cast an instant or sorcery spell from among cards exiled with it. If that spell would be put into a graveyard, put it on the bottom of its owner's library instead.\nCrew 2",
    subtypes={"Vehicle"},
)

LAZAV_WEARER_OF_FACES = make_creature(
    name="Lazav, Wearer of Faces",
    power=2, toughness=3,
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Detective", "Shapeshifter"},
    supertypes={"Legendary"},
    text="Whenever Lazav attacks, exile target card from a graveyard, then investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nWhenever you sacrifice a Clue, you may have Lazav become a copy of a creature card exiled with it until end of turn.",
)

LEYLINE_OF_THE_GUILDPACT = make_enchantment(
    name="Leyline of the Guildpact",
    mana_cost="{G/W}{G/U}{B/G}{R/G}",
    colors={Color.BLACK, Color.GREEN, Color.RED, Color.BLUE, Color.WHITE},
    text="If this card is in your opening hand, you may begin the game with it on the battlefield.\nEach nonland permanent you control is all colors.\nLands you control are every basic land type in addition to their other types.",
)

LIGHTNING_HELIX = make_instant(
    name="Lightning Helix",
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Lightning Helix deals 3 damage to any target and you gain 3 life.",
)

MEDDLING_YOUTHS = make_creature(
    name="Meddling Youths",
    power=4, toughness=5,
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Detective", "Human"},
    text="Haste\nWhenever you attack with three or more creatures, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

NIVMIZZET_GUILDPACT = make_creature(
    name="Niv-Mizzet, Guildpact",
    power=6, toughness=6,
    mana_cost="{W}{U}{B}{R}{G}",
    colors={Color.BLACK, Color.GREEN, Color.RED, Color.BLUE, Color.WHITE},
    subtypes={"Avatar", "Dragon"},
    supertypes={"Legendary"},
    text="Flying, hexproof from multicolored\nWhenever Niv-Mizzet deals combat damage to a player, it deals X damage to any target, target player draws X cards, and you gain X life, where X is the number of different color pairs among permanents you control that are exactly two colors.",
)

NO_MORE_LIES = make_instant(
    name="No More Lies",
    mana_cost="{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    text="Counter target spell unless its controller pays {3}. If that spell is countered this way, exile it instead of putting it into its owner's graveyard.",
)

OFFICIOUS_INTERROGATION = make_instant(
    name="Officious Interrogation",
    mana_cost="{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    text="This spell costs {W}{U} more to cast for each target beyond the first.\nChoose any number of target players. Investigate X times, where X is the total number of creatures those players control.",
)

PRIVATE_EYE = make_creature(
    name="Private Eye",
    power=3, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Detective", "Homunculus"},
    text="Other Detectives you control get +1/+1.\nWhenever you draw your second card each turn, target Detective can't be blocked this turn.",
)

RAKDOS_PATRON_OF_CHAOS = make_creature(
    name="Rakdos, Patron of Chaos",
    power=6, toughness=6,
    mana_cost="{4}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon"},
    supertypes={"Legendary"},
    text="Flying, trample\nAt the beginning of your end step, target opponent may sacrifice two nonland, nontoken permanents of their choice. If they don't, you draw two cards.",
)

RAKISH_SCOUNDREL = make_creature(
    name="Rakish Scoundrel",
    power=3, toughness=3,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Elf", "Rogue"},
    text="Deathtouch\nWhen this creature enters or is turned face up, target creature gains indestructible until end of turn.\nDisguise {4}{B/G}{B/G} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

RELIVE_THE_PAST = make_sorcery(
    name="Relive the Past",
    mana_cost="{5}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Return up to one target artifact card, up to one target land card, and up to one target non-Aura enchantment card from your graveyard to the battlefield. They are 5/5 Elemental creatures in addition to their other types.",
)

REPULSIVE_MUTATION = make_instant(
    name="Repulsive Mutation",
    mana_cost="{X}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    text="Put X +1/+1 counters on target creature you control. Then counter up to one target spell unless its controller pays mana equal to the greatest power among creatures you control.",
)

RIFTBURST_HELLION = make_creature(
    name="Riftburst Hellion",
    power=6, toughness=7,
    mana_cost="{5}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Hellion"},
    text="Reach\nDisguise {4}{R/G}{R/G} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

RUNEBRAND_JUGGLER = make_creature(
    name="Rune-Brand Juggler",
    power=2, toughness=2,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Shaman"},
    text="When this creature enters, suspect up to one target creature you control. (A suspected creature has menace and can't block.)\n{3}{B}{R}, Sacrifice a suspected creature: Target creature gets -5/-5 until end of turn.",
)

SANGUINE_SAVIOR = make_creature(
    name="Sanguine Savior",
    power=2, toughness=1,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Cleric", "Vampire"},
    text="Flying, lifelink\nDisguise {W/B}{W/B} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, another target creature you control gains lifelink until end of turn.",
)

SHADY_INFORMANT = make_creature(
    name="Shady Informant",
    power=4, toughness=2,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Ogre", "Rogue"},
    text="When this creature dies, it deals 2 damage to any target.\nDisguise {2}{B/R}{B/R} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

SOUL_SEARCH = make_sorcery(
    name="Soul Search",
    mana_cost="{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    text="Target opponent reveals their hand. You choose a nonland card from it. Exile that card. If the card's mana value is 1 or less, create a 1/1 white and black Spirit creature token with flying.",
)

SUMALA_SENTRY = make_creature(
    name="Sumala Sentry",
    power=1, toughness=3,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Archer", "Elf"},
    text="Reach\nWhenever a face-down permanent you control is turned face up, put a +1/+1 counter on it and a +1/+1 counter on this creature.",
)

TEYSA_OPULENT_OLIGARCH = make_creature(
    name="Teysa, Opulent Oligarch",
    power=2, toughness=3,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Advisor", "Human"},
    supertypes={"Legendary"},
    text="Deathtouch\nAt the beginning of your end step, investigate for each opponent who lost life this turn.\nWhenever a Clue you control is put into a graveyard from the battlefield, create a 1/1 white and black Spirit creature token with flying. This ability triggers only once each turn.",
)

TIN_STREET_GOSSIP = make_creature(
    name="Tin Street Gossip",
    power=4, toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Advisor", "Lizard"},
    text="Vigilance\n{T}: Add {R}{G}. Spend this mana only to cast face-down spells or to turn creatures face up.",
)

TOLSIMIR_MIDNIGHTS_LIGHT = make_creature(
    name="Tolsimir, Midnight's Light",
    power=3, toughness=2,
    mana_cost="{2}{G}{W}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Elf", "Scout"},
    supertypes={"Legendary"},
    text="Lifelink\nWhen Tolsimir enters, create Voja Fenstalker, a legendary 5/5 green and white Wolf creature token with trample.\nWhenever a Wolf you control attacks, if Tolsimir attacked this combat, target creature an opponent controls blocks that Wolf this combat if able.",
)

TREACHEROUS_GREED = make_instant(
    name="Treacherous Greed",
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    text="As an additional cost to cast this spell, sacrifice a creature that dealt damage this turn.\nDraw three cards. Each opponent loses 3 life and you gain 3 life.",
)

TROSTANI_THREE_WHISPERS = make_creature(
    name="Trostani, Three Whispers",
    power=4, toughness=4,
    mana_cost="{G}{G/W}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Dryad"},
    supertypes={"Legendary"},
    text="{1}{G}: Target creature gains deathtouch until end of turn.\n{G/W}: Target creature gains vigilance until end of turn.\n{2}{W}: Target creature gains double strike until end of turn.",
)

UNDERCOVER_CROCODELF = make_creature(
    name="Undercover Crocodelf",
    power=5, toughness=5,
    mana_cost="{4}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Crocodile", "Detective", "Elf"},
    text="Whenever this creature deals combat damage to a player, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nDisguise {3}{G/U}{G/U} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

URGENT_NECROPSY = make_instant(
    name="Urgent Necropsy",
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="As an additional cost to cast this spell, collect evidence X, where X is the total mana value of the permanents this spell targets.\nDestroy up to one target artifact, up to one target creature, up to one target enchantment, and up to one target planeswalker.",
)

VANNIFAR_EVOLVED_ENIGMA = make_creature(
    name="Vannifar, Evolved Enigma",
    power=3, toughness=4,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Elf", "Ooze", "Wizard"},
    supertypes={"Legendary"},
    text="At the beginning of combat on your turn, choose one —\n• Cloak a card from your hand. (Put it onto the battlefield face down as a 2/2 creature with ward {2}. Turn it face up any time for its mana cost if it's a creature card.)\n• Put a +1/+1 counter on each colorless creature you control.",
)

WARLEADERS_CALL = make_enchantment(
    name="Warleader's Call",
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Creatures you control get +1/+1.\nWhenever a creature you control enters, this enchantment deals 1 damage to each opponent.",
)

WISPDRINKER_VAMPIRE = make_creature(
    name="Wispdrinker Vampire",
    power=2, toughness=4,
    mana_cost="{2}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Rogue", "Vampire"},
    text="Flying\nWhenever another creature you control with power 2 or less enters, each opponent loses 1 life and you gain 1 life.\n{5}{W}{B}: Creatures you control with power 2 or less gain deathtouch and lifelink until end of turn.",
)

WORLDSOULS_RAGE = make_sorcery(
    name="Worldsoul's Rage",
    mana_cost="{X}{R}{G}",
    colors={Color.GREEN, Color.RED},
    text="Worldsoul's Rage deals X damage to any target. Put up to X land cards from your hand and/or graveyard onto the battlefield tapped.",
)

YARUS_ROAR_OF_THE_OLD_GODS = make_creature(
    name="Yarus, Roar of the Old Gods",
    power=4, toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Centaur", "Druid"},
    supertypes={"Legendary"},
    text="Other creatures you control have haste.\nWhenever one or more face-down creatures you control deal combat damage to a player, draw a card.\nWhenever a face-down creature you control dies, return it to the battlefield face down under its owner's control if it's a permanent card, then turn it face up.",
)

CEASE = make_instant(
    name="Cease",
    mana_cost="{1}{B/G}",
    colors={Color.BLACK, Color.GREEN, Color.WHITE},
    text="Cease {1}{B/G}: Exile up to two target cards from a single graveyard. Target player gains 2 life and draws a card.\n//\nDesist {4}{G/W}{G/W}: Destroy all artifacts and enchantments.",
)

FLOTSAM = make_instant(
    name="Flotsam",
    mana_cost="{1}{G/U}",
    colors={Color.BLACK, Color.GREEN, Color.BLUE},
    text="Flotsam {1}{G/U}: Mill three cards. Investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\n//\nJetsam {4}{U/B}{U/B}: Each opponent mills three cards, then you may cast a spell from each opponent's graveyard without paying its mana cost. If a spell cast this way would be put into a graveyard, exile it instead.",
)

FUSS = make_instant(
    name="Fuss",
    mana_cost="{2}{R/W}",
    colors={Color.RED, Color.BLUE, Color.WHITE},
    text="Fuss {2}{R/W}: Put a +1/+1 counter on each attacking creature you control.\n//\nBother {4}{W/U}{W/U}: Create three 1/1 colorless Thopter artifact creature tokens with flying. Surveil 2.",
)

HUSTLE = make_instant(
    name="Hustle",
    mana_cost="{U/R}",
    colors={Color.GREEN, Color.RED, Color.BLUE},
    text="Hustle {U/R}: Target creature attacks or blocks this turn if able.\n//\nBustle {4}{R/G}{R/G}: Creatures you control get +2/+2 and gain trample until end of turn. You may turn a creature you control face up.",
)

PUSH = make_sorcery(
    name="Push",
    mana_cost="{1}{W/B}",
    colors={Color.BLACK, Color.RED, Color.WHITE},
    text="Push {1}{W/B}: Destroy target tapped creature.\n//\nPull {4}{B/R}{B/R}: Put up to two target creature cards from a single graveyard onto the battlefield under your control. They gain haste until end of turn. Sacrifice them at the beginning of the next end step.",
)

CRYPTEX = make_artifact(
    name="Cryptex",
    mana_cost="{2}",
    text="{T}, Collect evidence 3: Add one mana of any color. Put an unlock counter on this artifact. (To collect evidence 3, exile cards with total mana value 3 or greater from your graveyard.)\nSacrifice this artifact: Surveil 3, then draw three cards. Activate only if this artifact has five or more unlock counters on it.",
)

GRAVESTONE_STRIDER = make_artifact_creature(
    name="Gravestone Strider",
    power=1, toughness=3,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Golem"},
    text="{1}: Add one mana of any color. Activate only once each turn.\n{2}, Exile this card from your graveyard: Exile target card from a graveyard.",
)

LUMBERING_LAUNDRY = make_artifact_creature(
    name="Lumbering Laundry",
    power=4, toughness=5,
    mana_cost="{5}",
    colors=set(),
    subtypes={"Golem"},
    text="{2}: Until end of turn, you may look at face-down creatures you don't control any time.\nDisguise {5} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

MAGNETIC_SNUFFLER = make_artifact_creature(
    name="Magnetic Snuffler",
    power=4, toughness=4,
    mana_cost="{5}",
    colors=set(),
    subtypes={"Construct"},
    text="When this creature enters, return target Equipment card from your graveyard to the battlefield attached to this creature.\nWhenever you sacrifice an artifact, put a +1/+1 counter on this creature.",
)

MAGNIFYING_GLASS = make_artifact(
    name="Magnifying Glass",
    mana_cost="{3}",
    text="{T}: Add {C}.\n{4}, {T}: Investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

SANITATION_AUTOMATON = make_artifact_creature(
    name="Sanitation Automaton",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Construct"},
    text="When this creature enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

THINKING_CAP = make_artifact(
    name="Thinking Cap",
    mana_cost="{1}",
    text="Equipped creature gets +1/+2.\nEquip Detective {1}\nEquip {3} ({3}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

BRANCH_OF_VITUGHAZI = make_land(
    name="Branch of Vitu-Ghazi",
    text="{T}: Add {C}.\nDisguise {3} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this land is turned face up, add two mana of any one color. Until end of turn, you don't lose this mana as steps and phases end.",
)

COMMERCIAL_DISTRICT = make_land(
    name="Commercial District",
    text="({T}: Add {R} or {G}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Forest", "Mountain"},
)

ELEGANT_PARLOR = make_land(
    name="Elegant Parlor",
    text="({T}: Add {R} or {W}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Mountain", "Plains"},
)

ESCAPE_TUNNEL = make_land(
    name="Escape Tunnel",
    text="{T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\n{T}, Sacrifice this land: Target creature with power 2 or less can't be blocked this turn.",
)

HEDGE_MAZE = make_land(
    name="Hedge Maze",
    text="({T}: Add {G} or {U}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Forest", "Island"},
)

LUSH_PORTICO = make_land(
    name="Lush Portico",
    text="({T}: Add {G} or {W}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Forest", "Plains"},
)

METICULOUS_ARCHIVE = make_land(
    name="Meticulous Archive",
    text="({T}: Add {W} or {U}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Island", "Plains"},
)

PUBLIC_THOROUGHFARE = make_land(
    name="Public Thoroughfare",
    text="This land enters tapped.\nWhen this land enters, sacrifice it unless you tap an untapped artifact or land you control.\n{T}: Add one mana of any color.",
)

RAUCOUS_THEATER = make_land(
    name="Raucous Theater",
    text="({T}: Add {B} or {R}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Mountain", "Swamp"},
)

SCENE_OF_THE_CRIME = make_artifact(
    name="Scene of the Crime",
    mana_cost="",
    text="This land enters tapped.\n{T}: Add {C}.\n{T}, Tap an untapped creature you control: Add one mana of any color.\n{2}, Sacrifice this land: Draw a card.",
    subtypes={"Clue"},
)

SHADOWY_BACKSTREET = make_land(
    name="Shadowy Backstreet",
    text="({T}: Add {W} or {B}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Plains", "Swamp"},
)

THUNDERING_FALLS = make_land(
    name="Thundering Falls",
    text="({T}: Add {U} or {R}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Island", "Mountain"},
)

UNDERCITY_SEWERS = make_land(
    name="Undercity Sewers",
    text="({T}: Add {U} or {B}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Island", "Swamp"},
)

UNDERGROUND_MORTUARY = make_land(
    name="Underground Mortuary",
    text="({T}: Add {B} or {G}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Forest", "Swamp"},
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

MELEK_REFORGED_RESEARCHER = make_creature(
    name="Melek, Reforged Researcher",
    power=0, toughness=0,
    mana_cost="{3}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Detective", "Weird"},
    supertypes={"Legendary"},
    text="Melek's power and toughness are each equal to twice the number of instant and sorcery cards in your graveyard.\nThe first instant or sorcery spell you cast each turn costs {3} less to cast.",
)

TOMIK_WIELDER_OF_LAW = make_creature(
    name="Tomik, Wielder of Law",
    power=2, toughness=4,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Advisor", "Human"},
    supertypes={"Legendary"},
    text="Affinity for planeswalkers (This spell costs {1} less to cast for each planeswalker you control.)\nFlying, vigilance\nWhenever an opponent attacks with creatures, if two or more of those creatures are attacking you and/or planeswalkers you control, that opponent loses 3 life and you draw a card.",
)

VOJA_JAWS_OF_THE_CONCLAVE = make_creature(
    name="Voja, Jaws of the Conclave",
    power=5, toughness=5,
    mana_cost="{2}{R}{G}{W}",
    colors={Color.GREEN, Color.RED, Color.WHITE},
    subtypes={"Wolf"},
    supertypes={"Legendary"},
    text="Vigilance, trample, ward {3}\nWhenever Voja attacks, put X +1/+1 counters on each creature you control, where X is the number of Elves you control. Draw a card for each Wolf you control.",
)

# =============================================================================
# CARD REGISTRY
# =============================================================================

MURDERS_KARLOV_MANOR_CARDS = {
    "Case of the Shattered Pact": CASE_OF_THE_SHATTERED_PACT,
    "Absolving Lammasu": ABSOLVING_LAMMASU,
    "Assemble the Players": ASSEMBLE_THE_PLAYERS,
    "Aurelia's Vindicator": AURELIAS_VINDICATOR,
    "Auspicious Arrival": AUSPICIOUS_ARRIVAL,
    "Call a Surprise Witness": CALL_A_SURPRISE_WITNESS,
    "Case File Auditor": CASE_FILE_AUDITOR,
    "Case of the Gateway Express": CASE_OF_THE_GATEWAY_EXPRESS,
    "Case of the Pilfered Proof": CASE_OF_THE_PILFERED_PROOF,
    "Case of the Uneaten Feast": CASE_OF_THE_UNEATEN_FEAST,
    "Defenestrated Phantom": DEFENESTRATED_PHANTOM,
    "Delney, Streetwise Lookout": DELNEY_STREETWISE_LOOKOUT,
    "Doorkeeper Thrull": DOORKEEPER_THRULL,
    "Due Diligence": DUE_DILIGENCE,
    "Essence of Antiquity": ESSENCE_OF_ANTIQUITY,
    "Forum Familiar": FORUM_FAMILIAR,
    "Griffnaut Tracker": GRIFFNAUT_TRACKER,
    "Haazda Vigilante": HAAZDA_VIGILANTE,
    "Inside Source": INSIDE_SOURCE,
    "Karlov Watchdog": KARLOV_WATCHDOG,
    "Krovod Haunch": KROVOD_HAUNCH,
    "Make Your Move": MAKE_YOUR_MOVE,
    "Makeshift Binding": MAKESHIFT_BINDING,
    "Marketwatch Phantom": MARKETWATCH_PHANTOM,
    "Museum Nightwatch": MUSEUM_NIGHTWATCH,
    "Neighborhood Guardian": NEIGHBORHOOD_GUARDIAN,
    "No Witnesses": NO_WITNESSES,
    "Not on My Watch": NOT_ON_MY_WATCH,
    "Novice Inspector": NOVICE_INSPECTOR,
    "On the Job": ON_THE_JOB,
    "Perimeter Enforcer": PERIMETER_ENFORCER,
    "Sanctuary Wall": SANCTUARY_WALL,
    "Seasoned Consultant": SEASONED_CONSULTANT,
    "Tenth District Hero": TENTH_DISTRICT_HERO,
    "Unyielding Gatekeeper": UNYIELDING_GATEKEEPER,
    "Wojek Investigator": WOJEK_INVESTIGATOR,
    "Wrench": WRENCH,
    "Agency Outfitter": AGENCY_OUTFITTER,
    "Behind the Mask": BEHIND_THE_MASK,
    "Benthic Criminologists": BENTHIC_CRIMINOLOGISTS,
    "Bubble Smuggler": BUBBLE_SMUGGLER,
    "Burden of Proof": BURDEN_OF_PROOF,
    "Candlestick": CANDLESTICK,
    "Case of the Filched Falcon": CASE_OF_THE_FILCHED_FALCON,
    "Case of the Ransacked Lab": CASE_OF_THE_RANSACKED_LAB,
    "Cold Case Cracker": COLD_CASE_CRACKER,
    "Conspiracy Unraveler": CONSPIRACY_UNRAVELER,
    "Coveted Falcon": COVETED_FALCON,
    "Crimestopper Sprite": CRIMESTOPPER_SPRITE,
    "Cryptic Coat": CRYPTIC_COAT,
    "Curious Inquiry": CURIOUS_INQUIRY,
    "Deduce": DEDUCE,
    "Dramatic Accusation": DRAMATIC_ACCUSATION,
    "Eliminate the Impossible": ELIMINATE_THE_IMPOSSIBLE,
    "Exit Specialist": EXIT_SPECIALIST,
    "Fae Flight": FAE_FLIGHT,
    "Forensic Gadgeteer": FORENSIC_GADGETEER,
    "Forensic Researcher": FORENSIC_RESEARCHER,
    "Furtive Courier": FURTIVE_COURIER,
    "Hotshot Investigators": HOTSHOT_INVESTIGATORS,
    "Intrude on the Mind": INTRUDE_ON_THE_MIND,
    "Jaded Analyst": JADED_ANALYST,
    "Living Conundrum": LIVING_CONUNDRUM,
    "Lost in the Maze": LOST_IN_THE_MAZE,
    "Mistway Spy": MISTWAY_SPY,
    "Out Cold": OUT_COLD,
    "Proft's Eidetic Memory": PROFTS_EIDETIC_MEMORY,
    "Projektor Inspector": PROJEKTOR_INSPECTOR,
    "Reasonable Doubt": REASONABLE_DOUBT,
    "Reenact the Crime": REENACT_THE_CRIME,
    "Steamcore Scholar": STEAMCORE_SCHOLAR,
    "Sudden Setback": SUDDEN_SETBACK,
    "Surveillance Monitor": SURVEILLANCE_MONITOR,
    "Unauthorized Exit": UNAUTHORIZED_EXIT,
    "Agency Coroner": AGENCY_CORONER,
    "Alley Assailant": ALLEY_ASSAILANT,
    "Barbed Servitor": BARBED_SERVITOR,
    "Basilica Stalker": BASILICA_STALKER,
    "Case of the Gorgon's Kiss": CASE_OF_THE_GORGONS_KISS,
    "Case of the Stashed Skeleton": CASE_OF_THE_STASHED_SKELETON,
    "Cerebral Confiscation": CEREBRAL_CONFISCATION,
    "Clandestine Meddler": CLANDESTINE_MEDDLER,
    "Deadly Cover-Up": DEADLY_COVERUP,
    "Extract a Confession": EXTRACT_A_CONFESSION,
    "Festerleech": FESTERLEECH,
    "Homicide Investigator": HOMICIDE_INVESTIGATOR,
    "Hunted Bonebrute": HUNTED_BONEBRUTE,
    "Illicit Masquerade": ILLICIT_MASQUERADE,
    "It Doesn't Add Up": IT_DOESNT_ADD_UP,
    "Lead Pipe": LEAD_PIPE,
    "Leering Onlooker": LEERING_ONLOOKER,
    "Long Goodbye": LONG_GOODBYE,
    "Macabre Reconstruction": MACABRE_RECONSTRUCTION,
    "Massacre Girl, Known Killer": MASSACRE_GIRL_KNOWN_KILLER,
    "Murder": MURDER,
    "Nightdrinker Moroii": NIGHTDRINKER_MOROII,
    "Outrageous Robbery": OUTRAGEOUS_ROBBERY,
    "Persuasive Interrogators": PERSUASIVE_INTERROGATORS,
    "Polygraph Orb": POLYGRAPH_ORB,
    "Presumed Dead": PRESUMED_DEAD,
    "Repeat Offender": REPEAT_OFFENDER,
    "Rot Farm Mortipede": ROT_FARM_MORTIPEDE,
    "Slice from the Shadows": SLICE_FROM_THE_SHADOWS,
    "Slimy Dualleech": SLIMY_DUALLEECH,
    "Snarling Gorehound": SNARLING_GOREHOUND,
    "Soul Enervation": SOUL_ENERVATION,
    "Toxin Analysis": TOXIN_ANALYSIS,
    "Undercity Eliminator": UNDERCITY_ELIMINATOR,
    "Unscrupulous Agent": UNSCRUPULOUS_AGENT,
    "Vein Ripper": VEIN_RIPPER,
    "Anzrag's Rampage": ANZRAGS_RAMPAGE,
    "Bolrac-Clan Basher": BOLRACCLAN_BASHER,
    "Case of the Burning Masks": CASE_OF_THE_BURNING_MASKS,
    "Case of the Crimson Pulse": CASE_OF_THE_CRIMSON_PULSE,
    "Caught Red-Handed": CAUGHT_REDHANDED,
    "The Chase Is On": THE_CHASE_IS_ON,
    "Concealed Weapon": CONCEALED_WEAPON,
    "Connecting the Dots": CONNECTING_THE_DOTS,
    "Convenient Target": CONVENIENT_TARGET,
    "Cornered Crook": CORNERED_CROOK,
    "Crime Novelist": CRIME_NOVELIST,
    "Demand Answers": DEMAND_ANSWERS,
    "Expedited Inheritance": EXPEDITED_INHERITANCE,
    "Expose the Culprit": EXPOSE_THE_CULPRIT,
    "Felonious Rage": FELONIOUS_RAGE,
    "Frantic Scapegoat": FRANTIC_SCAPEGOAT,
    "Fugitive Codebreaker": FUGITIVE_CODEBREAKER,
    "Galvanize": GALVANIZE,
    "Gearbane Orangutan": GEARBANE_ORANGUTAN,
    "Goblin Maskmaker": GOBLIN_MASKMAKER,
    "Harried Dronesmith": HARRIED_DRONESMITH,
    "Incinerator of the Guilty": INCINERATOR_OF_THE_GUILTY,
    "Innocent Bystander": INNOCENT_BYSTANDER,
    "Knife": KNIFE,
    "Krenko, Baron of Tin Street": KRENKO_BARON_OF_TIN_STREET,
    "Krenko's Buzzcrusher": KRENKOS_BUZZCRUSHER,
    "Lamplight Phoenix": LAMPLIGHT_PHOENIX,
    "Offender at Large": OFFENDER_AT_LARGE,
    "Person of Interest": PERSON_OF_INTEREST,
    "Pyrotechnic Performer": PYROTECHNIC_PERFORMER,
    "Reckless Detective": RECKLESS_DETECTIVE,
    "Red Herring": RED_HERRING,
    "Rubblebelt Braggart": RUBBLEBELT_BRAGGART,
    "Shock": SHOCK,
    "Suspicious Detonation": SUSPICIOUS_DETONATION,
    "Torch the Witness": TORCH_THE_WITNESS,
    "Vengeful Tracker": VENGEFUL_TRACKER,
    "Aftermath Analyst": AFTERMATH_ANALYST,
    "Airtight Alibi": AIRTIGHT_ALIBI,
    "Analyze the Pollen": ANALYZE_THE_POLLEN,
    "Archdruid's Charm": ARCHDRUIDS_CHARM,
    "Audience with Trostani": AUDIENCE_WITH_TROSTANI,
    "Axebane Ferox": AXEBANE_FEROX,
    "Bite Down on Crime": BITE_DOWN_ON_CRIME,
    "Case of the Locked Hothouse": CASE_OF_THE_LOCKED_HOTHOUSE,
    "Case of the Trampled Garden": CASE_OF_THE_TRAMPLED_GARDEN,
    "Chalk Outline": CHALK_OUTLINE,
    "Culvert Ambusher": CULVERT_AMBUSHER,
    "Fanatical Strength": FANATICAL_STRENGTH,
    "Flourishing Bloom-Kin": FLOURISHING_BLOOMKIN,
    "Get a Leg Up": GET_A_LEG_UP,
    "Glint Weaver": GLINT_WEAVER,
    "Greenbelt Radical": GREENBELT_RADICAL,
    "Hard-Hitting Question": HARDHITTING_QUESTION,
    "Hedge Whisperer": HEDGE_WHISPERER,
    "Hide in Plain Sight": HIDE_IN_PLAIN_SIGHT,
    "A Killer Among Us": A_KILLER_AMONG_US,
    "Loxodon Eavesdropper": LOXODON_EAVESDROPPER,
    "Nervous Gardener": NERVOUS_GARDENER,
    "Pick Your Poison": PICK_YOUR_POISON,
    "Pompous Gadabout": POMPOUS_GADABOUT,
    "The Pride of Hull Clade": THE_PRIDE_OF_HULL_CLADE,
    "Rope": ROPE,
    "Rubblebelt Maverick": RUBBLEBELT_MAVERICK,
    "Sample Collector": SAMPLE_COLLECTOR,
    "Sharp-Eyed Rookie": SHARPEYED_ROOKIE,
    "Slime Against Humanity": SLIME_AGAINST_HUMANITY,
    "They Went This Way": THEY_WENT_THIS_WAY,
    "Topiary Panther": TOPIARY_PANTHER,
    "Tunnel Tipster": TUNNEL_TIPSTER,
    "Undergrowth Recon": UNDERGROWTH_RECON,
    "Vengeful Creeper": VENGEFUL_CREEPER,
    "Vitu-Ghazi Inspector": VITUGHAZI_INSPECTOR,
    "Agrus Kos, Spirit of Justice": AGRUS_KOS_SPIRIT_OF_JUSTICE,
    "Alquist Proft, Master Sleuth": ALQUIST_PROFT_MASTER_SLEUTH,
    "Anzrag, the Quake-Mole": ANZRAG_THE_QUAKEMOLE,
    "Assassin's Trophy": ASSASSINS_TROPHY,
    "Aurelia, the Law Above": AURELIA_THE_LAW_ABOVE,
    "Blood Spatter Analysis": BLOOD_SPATTER_ANALYSIS,
    "Break Out": BREAK_OUT,
    "Buried in the Garden": BURIED_IN_THE_GARDEN,
    "Coerced to Kill": COERCED_TO_KILL,
    "Crowd-Control Warden": CROWDCONTROL_WARDEN,
    "Curious Cadaver": CURIOUS_CADAVER,
    "Deadly Complication": DEADLY_COMPLICATION,
    "Detective's Satchel": DETECTIVES_SATCHEL,
    "Dog Walker": DOG_WALKER,
    "Doppelgang": DOPPELGANG,
    "Drag the Canal": DRAG_THE_CANAL,
    "Etrata, Deadly Fugitive": ETRATA_DEADLY_FUGITIVE,
    "Evidence Examiner": EVIDENCE_EXAMINER,
    "Ezrim, Agency Chief": EZRIM_AGENCY_CHIEF,
    "Faerie Snoop": FAERIE_SNOOP,
    "Gadget Technician": GADGET_TECHNICIAN,
    "Gleaming Geardrake": GLEAMING_GEARDRAKE,
    "Granite Witness": GRANITE_WITNESS,
    "Ill-Timed Explosion": ILLTIMED_EXPLOSION,
    "Insidious Roots": INSIDIOUS_ROOTS,
    "Izoni, Center of the Web": IZONI_CENTER_OF_THE_WEB,
    "Judith, Carnage Connoisseur": JUDITH_CARNAGE_CONNOISSEUR,
    "Kaya, Spirits' Justice": KAYA_SPIRITS_JUSTICE,
    "Kellan, Inquisitive Prodigy": KELLAN_INQUISITIVE_PRODIGY,
    "Kraul Whipcracker": KRAUL_WHIPCRACKER,
    "Kylox, Visionary Inventor": KYLOX_VISIONARY_INVENTOR,
    "Kylox's Voltstrider": KYLOXS_VOLTSTRIDER,
    "Lazav, Wearer of Faces": LAZAV_WEARER_OF_FACES,
    "Leyline of the Guildpact": LEYLINE_OF_THE_GUILDPACT,
    "Lightning Helix": LIGHTNING_HELIX,
    "Meddling Youths": MEDDLING_YOUTHS,
    "Niv-Mizzet, Guildpact": NIVMIZZET_GUILDPACT,
    "No More Lies": NO_MORE_LIES,
    "Officious Interrogation": OFFICIOUS_INTERROGATION,
    "Private Eye": PRIVATE_EYE,
    "Rakdos, Patron of Chaos": RAKDOS_PATRON_OF_CHAOS,
    "Rakish Scoundrel": RAKISH_SCOUNDREL,
    "Relive the Past": RELIVE_THE_PAST,
    "Repulsive Mutation": REPULSIVE_MUTATION,
    "Riftburst Hellion": RIFTBURST_HELLION,
    "Rune-Brand Juggler": RUNEBRAND_JUGGLER,
    "Sanguine Savior": SANGUINE_SAVIOR,
    "Shady Informant": SHADY_INFORMANT,
    "Soul Search": SOUL_SEARCH,
    "Sumala Sentry": SUMALA_SENTRY,
    "Teysa, Opulent Oligarch": TEYSA_OPULENT_OLIGARCH,
    "Tin Street Gossip": TIN_STREET_GOSSIP,
    "Tolsimir, Midnight's Light": TOLSIMIR_MIDNIGHTS_LIGHT,
    "Treacherous Greed": TREACHEROUS_GREED,
    "Trostani, Three Whispers": TROSTANI_THREE_WHISPERS,
    "Undercover Crocodelf": UNDERCOVER_CROCODELF,
    "Urgent Necropsy": URGENT_NECROPSY,
    "Vannifar, Evolved Enigma": VANNIFAR_EVOLVED_ENIGMA,
    "Warleader's Call": WARLEADERS_CALL,
    "Wispdrinker Vampire": WISPDRINKER_VAMPIRE,
    "Worldsoul's Rage": WORLDSOULS_RAGE,
    "Yarus, Roar of the Old Gods": YARUS_ROAR_OF_THE_OLD_GODS,
    "Cease": CEASE,
    "Flotsam": FLOTSAM,
    "Fuss": FUSS,
    "Hustle": HUSTLE,
    "Push": PUSH,
    "Cryptex": CRYPTEX,
    "Gravestone Strider": GRAVESTONE_STRIDER,
    "Lumbering Laundry": LUMBERING_LAUNDRY,
    "Magnetic Snuffler": MAGNETIC_SNUFFLER,
    "Magnifying Glass": MAGNIFYING_GLASS,
    "Sanitation Automaton": SANITATION_AUTOMATON,
    "Thinking Cap": THINKING_CAP,
    "Branch of Vitu-Ghazi": BRANCH_OF_VITUGHAZI,
    "Commercial District": COMMERCIAL_DISTRICT,
    "Elegant Parlor": ELEGANT_PARLOR,
    "Escape Tunnel": ESCAPE_TUNNEL,
    "Hedge Maze": HEDGE_MAZE,
    "Lush Portico": LUSH_PORTICO,
    "Meticulous Archive": METICULOUS_ARCHIVE,
    "Public Thoroughfare": PUBLIC_THOROUGHFARE,
    "Raucous Theater": RAUCOUS_THEATER,
    "Scene of the Crime": SCENE_OF_THE_CRIME,
    "Shadowy Backstreet": SHADOWY_BACKSTREET,
    "Thundering Falls": THUNDERING_FALLS,
    "Undercity Sewers": UNDERCITY_SEWERS,
    "Underground Mortuary": UNDERGROUND_MORTUARY,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
    "Melek, Reforged Researcher": MELEK_REFORGED_RESEARCHER,
    "Tomik, Wielder of Law": TOMIK_WIELDER_OF_LAW,
    "Voja, Jaws of the Conclave": VOJA_JAWS_OF_THE_CONCLAVE,
}

print(f"Loaded {len(MURDERS_KARLOV_MANOR_CARDS)} Murders at Karlov Manor cards")
