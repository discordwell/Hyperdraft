"""
Lost_Caverns_of_Ixalan (LCI) Card Implementations

Real card data fetched from Scryfall API.
292 cards in set.
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

ABUELOS_AWAKENING = make_sorcery(
    name="Abuelo's Awakening",
    mana_cost="{X}{3}{W}",
    colors={Color.WHITE},
    text="Return target artifact or non-Aura enchantment card from your graveyard to the battlefield with X additional +1/+1 counters on it. It's a 1/1 Spirit creature with flying in addition to its other types.",
)

ACROBATIC_LEAP = make_instant(
    name="Acrobatic Leap",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gets +1/+3 and gains flying until end of turn. Untap it.",
)

ADAPTIVE_GEMGUARD = make_artifact_creature(
    name="Adaptive Gemguard",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Gnome"},
    text="Tap two untapped artifacts and/or creatures you control: Put a +1/+1 counter on this creature. Activate only as a sorcery.",
)

ATTENTIVE_SUNSCRIBE = make_artifact_creature(
    name="Attentive Sunscribe",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Gnome"},
    text="Whenever this creature becomes tapped, scry 1. (Look at the top card of your library. You may put that card on the bottom.)",
)

BAT_COLONY = make_enchantment(
    name="Bat Colony",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, create a 1/1 black Bat creature token with flying for each mana from a Cave spent to cast it.\nWhenever a Cave you control enters, put a +1/+1 counter on target creature you control.",
)

CLAYFIRED_BRICKS = make_artifact(
    name="Clay-Fired Bricks",
    mana_cost="",
    text="",
)

COSMIUM_BLAST = make_instant(
    name="Cosmium Blast",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Cosmium Blast deals 4 damage to target attacking or blocking creature.",
)

DAUNTLESS_DISMANTLER = make_creature(
    name="Dauntless Dismantler",
    power=1, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Artificer", "Human"},
    text="Artifacts your opponents control enter tapped.\n{X}{X}{W}, Sacrifice this creature: Destroy each artifact with mana value X.",
)

DECONSTRUCTION_HAMMER = make_artifact(
    name="Deconstruction Hammer",
    mana_cost="{W}",
    text="Equipped creature gets +1/+1 and has \"{3}, {T}, Sacrifice Deconstruction Hammer: Destroy target artifact or enchantment.\"\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

DUSK_ROSE_RELIQUARY = make_artifact(
    name="Dusk Rose Reliquary",
    mana_cost="{W}",
    text="As an additional cost to cast this spell, sacrifice an artifact or creature.\nWard {2}\nWhen this artifact enters, exile target artifact or creature an opponent controls until this artifact leaves the battlefield.",
)

ENVOY_OF_OKINEC_AHAU = make_creature(
    name="Envoy of Okinec Ahau",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Advisor", "Cat"},
    text="{4}{W}: Create a 1/1 colorless Gnome artifact creature token.",
)

FABRICATION_FOUNDRY = make_artifact(
    name="Fabrication Foundry",
    mana_cost="{1}{W}",
    text="{T}: Add {W}. Spend this mana only to cast an artifact spell or activate an ability of an artifact source.\n{2}{W}, {T}, Exile one or more other artifacts you control with total mana value X: Return target artifact card with mana value X or less from your graveyard to the battlefield. Activate only as a sorcery.",
)

FAMILY_REUNION = make_instant(
    name="Family Reunion",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Creatures you control get +1/+1 until end of turn.\n• Creatures you control gain hexproof until end of turn. (They can't be the targets of spells or abilities your opponents control.)",
)

GET_LOST = make_instant(
    name="Get Lost",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Destroy target creature, enchantment, or planeswalker. Its controller creates two Map tokens. (They're artifacts with \"{1}, {T}, Sacrifice this token: Target creature you control explores. Activate only as a sorcery.\")",
)

GLORIFIER_OF_SUFFERING = make_creature(
    name="Glorifier of Suffering",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Soldier", "Vampire"},
    text="When this creature enters, you may sacrifice another creature or artifact. When you do, put a +1/+1 counter on each of up to two target creatures.",
)

GUARDIAN_OF_THE_GREAT_DOOR = make_creature(
    name="Guardian of the Great Door",
    power=4, toughness=4,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="As an additional cost to cast this spell, tap four untapped artifacts, creatures, and/or lands you control.\nFlying",
)

HELPING_HAND = make_sorcery(
    name="Helping Hand",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Return target creature card with mana value 3 or less from your graveyard to the battlefield tapped.",
)

IRONPAW_ASPIRANT = make_creature(
    name="Ironpaw Aspirant",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Warrior"},
    text="When this creature enters, put a +1/+1 counter on target creature.",
)

KINJALLIS_DAWNRUNNER = make_creature(
    name="Kinjalli's Dawnrunner",
    power=1, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="Double strike\nWhen this creature enters, it explores. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put the card back or put it into your graveyard.)",
)

KUTZILS_FLANKER = make_creature(
    name="Kutzil's Flanker",
    power=3, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Warrior"},
    text="Flash\nWhen this creature enters, choose one —\n• Put a +1/+1 counter on this creature for each creature that left the battlefield under your control this turn.\n• You gain 2 life and scry 2.\n• Exile target player's graveyard.",
)

MALAMET_WAR_SCRIBE = make_creature(
    name="Malamet War Scribe",
    power=4, toughness=3,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Warrior"},
    text="When this creature enters, creatures you control get +2/+1 until end of turn.",
)

MARKET_GNOME = make_artifact_creature(
    name="Market Gnome",
    power=0, toughness=3,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Gnome"},
    text="When this creature dies, you gain 1 life and draw a card.\nWhen this creature is exiled from the battlefield while you're activating a craft ability, you gain 1 life and draw a card.",
)

MIGHT_OF_THE_ANCESTORS = make_enchantment(
    name="Might of the Ancestors",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="At the beginning of combat on your turn, target creature you control gets +2/+0 and gains vigilance until end of turn.",
)

MINERS_GUIDEWING = make_creature(
    name="Miner's Guidewing",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Bird"},
    text="Flying, vigilance\nWhen this creature dies, target creature you control explores. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on that creature, then put the card back or put it into your graveyard.)",
)

MISCHIEVOUS_PUP = make_creature(
    name="Mischievous Pup",
    power=3, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Dog"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nWhen this creature enters, return up to one other target permanent you control to its owner's hand.",
)

OJER_TAQ_DEEPEST_FOUNDATION = make_creature(
    name="Ojer Taq, Deepest Foundation",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "God", "Land"},
    supertypes={"Legendary"},
    text="",
)

OLTEC_ARCHAEOLOGISTS = make_creature(
    name="Oltec Archaeologists",
    power=4, toughness=4,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Artificer", "Human", "Scout"},
    text="When this creature enters, choose one —\n• Return target artifact card from your graveyard to your hand.\n• Scry 3. (Look at the top three cards of your library, then put any number of them on the bottom and the rest on top in any order.)",
)

OLTEC_CLOUD_GUARD = make_creature(
    name="Oltec Cloud Guard",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Flying\nWhen this creature enters, create a 1/1 colorless Gnome artifact creature token.",
)

OTECLAN_LANDMARK = make_artifact_creature(
    name="Oteclan Landmark",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Golem"},
    text="",
)

PETRIFY = make_enchantment(
    name="Petrify",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Enchant artifact or creature\nEnchanted permanent can't attack or block, and its activated abilities can't be activated.",
    subtypes={"Aura"},
)

QUICKSAND_WHIRLPOOL = make_instant(
    name="Quicksand Whirlpool",
    mana_cost="{5}{W}",
    colors={Color.WHITE},
    text="This spell costs {3} less to cast if it targets a tapped creature.\nExile target creature.",
)

RESPLENDENT_ANGEL = make_creature(
    name="Resplendent Angel",
    power=3, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nAt the beginning of each end step, if you gained 5 or more life this turn, create a 4/4 white Angel creature token with flying and vigilance.\n{3}{W}{W}{W}: Until end of turn, this creature gets +2/+2 and gains lifelink.",
)

RUINLURKER_BAT = make_creature(
    name="Ruin-Lurker Bat",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Bat"},
    text="Flying, lifelink\nAt the beginning of your end step, if you descended this turn, scry 1. (You descended if a permanent card was put into your graveyard from anywhere.)",
)

SANGUINE_EVANGELIST = make_creature(
    name="Sanguine Evangelist",
    power=2, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Vampire"},
    text="Battle cry (Whenever this creature attacks, each other attacking creature gets +1/+0 until end of turn.)\nWhen this creature enters or dies, create a 1/1 black Bat creature token with flying.",
)

SOARING_SANDWING = make_creature(
    name="Soaring Sandwing",
    power=3, toughness=5,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Dinosaur"},
    text="Flying\nWhen this creature enters, you gain 3 life.\nPlainscycling {2} ({2}, Discard this card: Search your library for a Plains card, reveal it, put it into your hand, then shuffle.)",
)

SPRINGLOADED_SAWBLADES = make_artifact(
    name="Spring-Loaded Sawblades",
    mana_cost="",
    text="",
    subtypes={"Vehicle"},
)

THOUSAND_MOONS_CRACKSHOT = make_creature(
    name="Thousand Moons Crackshot",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Whenever this creature attacks, you may pay {2}{W}. When you do, tap target creature.",
)

THOUSAND_MOONS_INFANTRY = make_creature(
    name="Thousand Moons Infantry",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Untap this creature during each other player's untap step.",
)

THOUSAND_MOONS_SMITHY = make_artifact(
    name="Thousand Moons Smithy",
    mana_cost="",
    text="",
    supertypes={"Legendary"},
)

TINKERS_TOTE = make_artifact(
    name="Tinker's Tote",
    mana_cost="{2}{W}",
    text="When this artifact enters, create two 1/1 colorless Gnome artifact creature tokens.\n{W}, Sacrifice this artifact: You gain 3 life.",
)

UNSTABLE_GLYPHBRIDGE = make_artifact_creature(
    name="Unstable Glyphbridge",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Golem"},
    text="",
)

VANGUARD_OF_THE_ROSE = make_creature(
    name="Vanguard of the Rose",
    power=3, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Knight", "Vampire"},
    text="{1}, Sacrifice another creature or artifact: This creature gains indestructible until end of turn. Tap it.",
)

WARDEN_OF_THE_INNER_SKY = make_creature(
    name="Warden of the Inner Sky",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="As long as this creature has three or more counters on it, it has flying and vigilance.\nTap three untapped artifacts and/or creatures you control: Put a +1/+1 counter on this creature. Scry 1. Activate only as a sorcery.",
)

AKAL_PAKAL_FIRST_AMONG_EQUALS = make_creature(
    name="Akal Pakal, First Among Equals",
    power=1, toughness=5,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Advisor", "Human"},
    supertypes={"Legendary"},
    text="At the beginning of each player's end step, if an artifact entered the battlefield under your control this turn, look at the top two cards of your library. Put one of them into your hand and the other into your graveyard.",
)

ANCESTRAL_REMINISCENCE = make_sorcery(
    name="Ancestral Reminiscence",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Draw three cards, then discard a card.",
)

BRACKISH_BLUNDER = make_instant(
    name="Brackish Blunder",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target creature to its owner's hand. If it was tapped, create a Map token. (It's an artifact with \"{1}, {T}, Sacrifice this token: Target creature you control explores. Activate only as a sorcery.\")",
)

BRAIDED_NET = make_artifact(
    name="Braided Net",
    mana_cost="",
    text="",
)

CHART_A_COURSE = make_sorcery(
    name="Chart a Course",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Draw two cards. Then discard a card unless you attacked this turn.",
)

COGWORK_WRESTLER = make_artifact_creature(
    name="Cogwork Wrestler",
    power=1, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Gnome"},
    text="Flash\nWhen this creature enters, target creature an opponent controls gets -2/-0 until end of turn.",
)

CONFOUNDING_RIDDLE = make_instant(
    name="Confounding Riddle",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Choose one —\n• Look at the top four cards of your library. Put one of them into your hand and the rest into your graveyard.\n• Counter target spell unless its controller pays {4}.",
)

COUNCIL_OF_ECHOES = make_creature(
    name="Council of Echoes",
    power=4, toughness=4,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Advisor", "Spirit"},
    text="Flying\nDescend 4 — When this creature enters, if there are four or more permanent cards in your graveyard, return up to one target nonland permanent other than this creature to its owner's hand.",
)

DEEPROOT_PILGRIMAGE = make_enchantment(
    name="Deeproot Pilgrimage",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Whenever one or more nontoken Merfolk you control become tapped, create a 1/1 blue Merfolk creature token with hexproof.",
)

DIDACT_ECHO = make_creature(
    name="Didact Echo",
    power=3, toughness=2,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Cleric", "Spirit"},
    text="When this creature enters, draw a card.\nDescend 4 — This creature has flying as long as there are four or more permanent cards in your graveyard.",
)

EATEN_BY_PIRANHAS = make_enchantment(
    name="Eaten by Piranhas",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Flash (You may cast this spell any time you could cast an instant.)\nEnchant creature\nEnchanted creature loses all abilities and is a black Skeleton creature with base power and toughness 1/1. (It loses all other colors, card types, and creature types.)",
    subtypes={"Aura"},
)

THE_ENIGMA_JEWEL = make_artifact(
    name="The Enigma Jewel",
    mana_cost="",
    text="",
    supertypes={"Legendary"},
)

THE_EVERFLOWING_WELL = make_artifact(
    name="The Everflowing Well",
    mana_cost="",
    text="",
    supertypes={"Legendary"},
)

FRILLED_CAVEWURM = make_creature(
    name="Frilled Cave-Wurm",
    power=2, toughness=5,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Salamander", "Wurm"},
    text="Descend 4 — This creature gets +2/+0 as long as there are four or more permanent cards in your graveyard.",
)

HERMITIC_NAUTILUS = make_artifact_creature(
    name="Hermitic Nautilus",
    power=1, toughness=4,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Nautilus"},
    text="Vigilance\n{1}{U}: This creature gets +3/-3 until end of turn.",
)

HURL_INTO_HISTORY = make_instant(
    name="Hurl into History",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Counter target artifact or creature spell. Discover X, where X is that spell's mana value. (Exile cards from the top of your library until you exile a nonland card with that mana value or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
)

INVERTED_ICEBERG = make_artifact_creature(
    name="Inverted Iceberg",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Golem"},
    text="",
)

KITESAIL_LARCENIST = make_creature(
    name="Kitesail Larcenist",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="Flying, ward {1}\nWhen this creature enters, for each player, choose up to one other target artifact or creature that player controls. For as long as this creature remains on the battlefield, the chosen permanents become Treasure artifacts with \"{T}, Sacrifice this artifact: Add one mana of any color\" and lose all other abilities.",
)

LODESTONE_NEEDLE = make_artifact(
    name="Lodestone Needle",
    mana_cost="",
    text="",
)

MALCOLM_ALLURING_SCOUNDREL = make_creature(
    name="Malcolm, Alluring Scoundrel",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Pirate", "Siren"},
    supertypes={"Legendary"},
    text="Flash\nFlying\nWhenever Malcolm deals combat damage to a player, put a chorus counter on it. Draw a card, then discard a card. If there are four or more chorus counters on Malcolm, you may cast the discarded card without paying its mana cost.",
)

MARAUDING_BRINEFANG = make_creature(
    name="Marauding Brinefang",
    power=6, toughness=7,
    mana_cost="{5}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Dinosaur"},
    text="Ward {3} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {3}.)\nIslandcycling {2} ({2}, Discard this card: Search your library for an Island card, reveal it, put it into your hand, then shuffle.)",
)

MERFOLK_CAVEDIVER = make_creature(
    name="Merfolk Cave-Diver",
    power=2, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Scout"},
    text="Whenever a creature you control explores, this creature gets +1/+0 until end of turn and can't be blocked this turn.",
)

OAKEN_SIREN = make_artifact_creature(
    name="Oaken Siren",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Pirate", "Siren"},
    text="Flying, vigilance\n{T}: Add {U}. Spend this mana only to cast an artifact spell or activate an ability of an artifact source.",
)

OJER_PAKPATIQ_DEEPEST_EPOCH = make_creature(
    name="Ojer Pakpatiq, Deepest Epoch",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "God", "Land"},
    supertypes={"Legendary"},
    text="",
)

ORAZCA_PUZZLEDOOR = make_artifact(
    name="Orazca Puzzle-Door",
    mana_cost="{U}",
    text="{1}, {T}, Sacrifice this artifact: Look at the top two cards of your library. Put one of those cards into your hand and the other into your graveyard.",
)

OUT_OF_AIR = make_instant(
    name="Out of Air",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="This spell costs {2} less to cast if it targets a creature spell.\nCounter target spell.",
)

PIRATE_HAT = make_artifact(
    name="Pirate Hat",
    mana_cost="{1}{U}",
    text="Equipped creature gets +1/+1 and has \"Whenever this creature attacks, draw a card, then discard a card.\"\nEquip Pirate {1}\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

RELICS_ROAR = make_instant(
    name="Relic's Roar",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Until end of turn, target artifact or creature becomes a Dinosaur artifact creature with base power and toughness 4/3 in addition to its other types.",
)

RIVER_HERALD_SCOUT = make_creature(
    name="River Herald Scout",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Scout"},
    text="When this creature enters, it explores. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put the card back or put it into your graveyard.)",
)

SAGE_OF_DAYS = make_creature(
    name="Sage of Days",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When this creature enters, look at the top three cards of your library. You may put one of those cards back on top of your library. Put the rest into your graveyard.",
)

SELFREFLECTION = make_sorcery(
    name="Self-Reflection",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Create a token that's a copy of target creature you control.\nFlashback {3}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

SHIPWRECK_SENTRY = make_creature(
    name="Shipwreck Sentry",
    power=3, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="Defender\nAs long as an artifact entered the battlefield under your control this turn, this creature can attack as though it didn't have defender.",
)

SINUOUS_BENTHISAUR = make_creature(
    name="Sinuous Benthisaur",
    power=4, toughness=4,
    mana_cost="{5}{U}",
    colors={Color.BLUE},
    subtypes={"Dinosaur"},
    text="When this creature enters, look at the top X cards of your library, where X is the number of Caves you control plus the number of Cave cards in your graveyard. Put two of those cards into your hand and the rest on the bottom of your library in a random order.",
)

SONG_OF_STUPEFACTION = make_enchantment(
    name="Song of Stupefaction",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Enchant creature or Vehicle\nWhen this Aura enters, you may mill two cards. (You may put the top two cards of your library into your graveyard.)\nFathomless descent — Enchanted permanent gets -X/-0, where X is the number of permanent cards in your graveyard.",
    subtypes={"Aura"},
)

SPYGLASS_SIREN = make_creature(
    name="Spyglass Siren",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Pirate", "Siren"},
    text="Flying\nWhen this creature enters, create a Map token. (It's an artifact with \"{1}, {T}, Sacrifice this token: Target creature you control explores. Activate only as a sorcery.\")",
)

STAUNCH_CREWMATE = make_creature(
    name="Staunch Crewmate",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="When this creature enters, look at the top four cards of your library. You may reveal an artifact or Pirate card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
)

SUBTERRANEAN_SCHOONER = make_artifact(
    name="Subterranean Schooner",
    mana_cost="{1}{U}",
    text="Whenever this Vehicle attacks, target creature that crewed it this turn explores. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on that creature, then put the card back or put it into your graveyard.)\nCrew 1",
    subtypes={"Vehicle"},
)

TISHANAS_TIDEBINDER = make_creature(
    name="Tishana's Tidebinder",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="Flash\nWhen this creature enters, counter up to one target activated or triggered ability. If an ability of an artifact, creature, or planeswalker is countered this way, that permanent loses all abilities for as long as this creature remains on the battlefield. (Mana abilities can't be targeted.)",
)

UNLUCKY_DROP = make_instant(
    name="Unlucky Drop",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Target artifact or creature's owner puts it on their choice of the top or bottom of their library.",
)

WATERLOGGED_HULK = make_artifact(
    name="Waterlogged Hulk",
    mana_cost="",
    text="",
    subtypes={"Vehicle"},
)

WATERWIND_SCOUT = make_creature(
    name="Waterwind Scout",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Scout"},
    text="Flying\nWhen this creature enters, create a Map token. (It's an artifact with \"{1}, {T}, Sacrifice this token: Target creature you control explores. Activate only as a sorcery.\")",
)

WAYLAYING_PIRATES = make_creature(
    name="Waylaying Pirates",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="When this creature enters, if you control an artifact, tap target artifact or creature an opponent controls and put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

ZOETIC_GLYPH = make_enchantment(
    name="Zoetic Glyph",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Enchant artifact\nEnchanted artifact is a Golem creature with base power and toughness 5/4 in addition to its other types.\nWhen this Aura is put into a graveyard from the battlefield, discover 3.",
    subtypes={"Aura"},
)

ABYSSAL_GORESTALKER = make_creature(
    name="Abyssal Gorestalker",
    power=6, toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="When this creature enters, each player sacrifices two creatures of their choice.",
)

ACLAZOTZ_DEEPEST_BETRAYAL = make_creature(
    name="Aclazotz, Deepest Betrayal",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Bat", "God", "Land"},
    supertypes={"Legendary"},
    text="",
)

ACOLYTE_OF_ACLAZOTZ = make_creature(
    name="Acolyte of Aclazotz",
    power=1, toughness=4,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Vampire"},
    text="{T}, Sacrifice another creature or artifact: Each opponent loses 1 life and you gain 1 life.",
)

ANOTHER_CHANCE = make_instant(
    name="Another Chance",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="You may mill two cards. Then return up to two creature cards from your graveyard to your hand. (To mill two cards, put the top two cards of your library into your graveyard.)",
)

BITTER_TRIUMPH = make_instant(
    name="Bitter Triumph",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, discard a card or pay 3 life.\nDestroy target creature or planeswalker.",
)

BLOODLETTER_OF_ACLAZOTZ = make_creature(
    name="Bloodletter of Aclazotz",
    power=2, toughness=4,
    mana_cost="{1}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Vampire"},
    text="Flying\nIf an opponent would lose life during your turn, they lose twice that much life instead. (Damage causes loss of life.)",
)

BLOODTHORN_FLAIL = make_artifact(
    name="Bloodthorn Flail",
    mana_cost="{B}",
    text="Equipped creature gets +2/+1.\nEquip—Pay {3} or discard a card.",
    subtypes={"Equipment"},
)

BRINGER_OF_THE_LAST_GIFT = make_creature(
    name="Bringer of the Last Gift",
    power=6, toughness=6,
    mana_cost="{6}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Vampire"},
    text="Flying\nWhen this creature enters, if you cast it, each player sacrifices all other creatures they control. Then each player returns all creature cards from their graveyard that weren't put there this way to the battlefield.",
)

BROODRAGE_MYCOID = make_creature(
    name="Broodrage Mycoid",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Fungus"},
    text="At the beginning of your end step, if you descended this turn, create a 1/1 black Fungus creature token with \"This token can't block.\" (You descended if a permanent card was put into your graveyard from anywhere.)",
)

CANONIZED_IN_BLOOD = make_enchantment(
    name="Canonized in Blood",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="At the beginning of your end step, if you descended this turn, put a +1/+1 counter on target creature you control. (You descended if a permanent card was put into your graveyard from anywhere.)\n{5}{B}{B}, Sacrifice this enchantment: Create a 4/3 white and black Vampire Demon creature token with flying.",
)

CHUPACABRA_ECHO = make_creature(
    name="Chupacabra Echo",
    power=3, toughness=2,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Beast", "Horror", "Spirit"},
    text="Fathomless descent — When this creature enters, target creature an opponent controls gets -X/-X until end of turn, where X is the number of permanent cards in your graveyard.",
)

CORPSES_OF_THE_LOST = make_enchantment(
    name="Corpses of the Lost",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Skeletons you control get +1/+0 and have haste.\nWhen this enchantment enters, create a 2/2 black Skeleton Pirate creature token.\nAt the beginning of your end step, if you descended this turn, you may pay 1 life. If you do, return this enchantment to its owner's hand. (You descended if a permanent card was put into your graveyard from anywhere.)",
)

DEAD_WEIGHT = make_enchantment(
    name="Dead Weight",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Enchant creature\nEnchanted creature gets -2/-2.",
    subtypes={"Aura"},
)

DEATHCAP_MARIONETTE = make_creature(
    name="Deathcap Marionette",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Fungus"},
    text="Deathtouch\nWhen this creature enters, you may mill two cards. (You may put the top two cards of your library into your graveyard.)",
)

DEEP_GOBLIN_SKULLTAKER = make_creature(
    name="Deep Goblin Skulltaker",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Warrior"},
    text="Menace\nAt the beginning of your end step, if you descended this turn, put a +1/+1 counter on this creature. (You descended if a permanent card was put into your graveyard from anywhere.)",
)

DEEPCAVERN_BAT = make_creature(
    name="Deep-Cavern Bat",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Bat"},
    text="Flying, lifelink\nWhen this creature enters, look at target opponent's hand. You may exile a nonland card from it until this creature leaves the battlefield.",
)

DEFOSSILIZE = make_sorcery(
    name="Defossilize",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield. That creature explores, then it explores again. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on that creature, then put the card back or put it into your graveyard. Then repeat this process.)",
)

ECHO_OF_DUSK = make_creature(
    name="Echo of Dusk",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Vampire"},
    text="Descend 4 — As long as there are four or more permanent cards in your graveyard, this creature gets +1/+1 and has lifelink.",
)

FANATICAL_OFFERING = make_instant(
    name="Fanatical Offering",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, sacrifice an artifact or creature.\nDraw two cards and create a Map token. (It's an artifact with \"{1}, {T}, Sacrifice this token: Target creature you control explores. Activate only as a sorcery.\")",
)

FUNGAL_FORTITUDE = make_enchantment(
    name="Fungal Fortitude",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Flash\nEnchant creature\nEnchanted creature gets +2/+0.\nWhen enchanted creature dies, return it to the battlefield tapped under its owner's control.",
    subtypes={"Aura"},
)

GARGANTUAN_LEECH = make_creature(
    name="Gargantuan Leech",
    power=5, toughness=5,
    mana_cost="{7}{B}",
    colors={Color.BLACK},
    subtypes={"Leech"},
    text="This spell costs {1} less to cast for each Cave you control and each Cave card in your graveyard.\nLifelink",
)

GRASPING_SHADOWS = make_enchantment(
    name="Grasping Shadows",
    mana_cost="",
    colors=set(),
    text="",
    subtypes={"Cave"},
)

GREEDY_FREEBOOTER = make_creature(
    name="Greedy Freebooter",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate"},
    text="When this creature dies, scry 1 and create a Treasure token. (To scry 1, look at the top card of your library. You may put that card on the bottom. A Treasure token is an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

JOIN_THE_DEAD = make_instant(
    name="Join the Dead",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Target creature gets -5/-5 until end of turn.\nDescend 4 — That creature gets -10/-10 until end of turn instead if there are four or more permanent cards in your graveyard.",
)

MALICIOUS_ECLIPSE = make_sorcery(
    name="Malicious Eclipse",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="All creatures get -2/-2 until end of turn. If a creature an opponent controls would die this turn, exile it instead.",
)

MEPHITIC_DRAUGHT = make_artifact(
    name="Mephitic Draught",
    mana_cost="{1}{B}",
    text="When this artifact enters or is put into a graveyard from the battlefield, you draw a card and you lose 1 life.",
)

PREACHER_OF_THE_SCHISM = make_creature(
    name="Preacher of the Schism",
    power=2, toughness=4,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Vampire"},
    text="Deathtouch\nWhenever this creature attacks the player with the most life or tied for most life, create a 1/1 white Vampire creature token with lifelink.\nWhenever this creature attacks while you have the most life or are tied for most life, you draw a card and you lose 1 life.",
)

PRIMORDIAL_GNAWER = make_creature(
    name="Primordial Gnawer",
    power=5, toughness=2,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Insect"},
    text="When this creature dies, discover 3. (Exile cards from the top of your library until you exile a nonland card with mana value 3 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
)

QUEENS_BAY_PALADIN = make_creature(
    name="Queen's Bay Paladin",
    power=5, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Knight", "Vampire"},
    text="Whenever this creature enters or attacks, return up to one target Vampire card from your graveyard to the battlefield with a finality counter on it. You lose life equal to its mana value. (If a creature with a finality counter on it would die, exile it instead.)",
)

RAMPAGING_SPIKETAIL = make_creature(
    name="Rampaging Spiketail",
    power=5, toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Dinosaur"},
    text="When this creature enters, target creature you control gets +2/+0 and gains indestructible until end of turn.\nSwampcycling {2} ({2}, Discard this card: Search your library for a Swamp card, reveal it, put it into your hand, then shuffle.)",
)

RAY_OF_RUIN = make_sorcery(
    name="Ray of Ruin",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="Exile target creature, Vehicle, or nonbasic land. Scry 1. (Look at the top card of your library. You may put that card on the bottom.)",
)

SCREAMING_PHANTOM = make_creature(
    name="Screaming Phantom",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Flying\nWhenever this creature attacks, mill a card. (Put the top card of your library into your graveyard.)",
)

SKULLCAP_SNAIL = make_creature(
    name="Skullcap Snail",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Fungus", "Snail"},
    text="When this creature enters, target opponent exiles a card from their hand.",
)

SOULCOIL_VIPER = make_creature(
    name="Soulcoil Viper",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Snake"},
    text="{B}, {T}, Sacrifice this creature: Return target creature card from your graveyard to the battlefield with a finality counter on it. Activate only as a sorcery. (If a creature with a finality counter on it would die, exile it instead.)",
)

SOULS_OF_THE_LOST = make_creature(
    name="Souls of the Lost",
    power=0, toughness=0,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="As an additional cost to cast this spell, discard a card or sacrifice a permanent.\nFathomless descent — Souls of the Lost's power is equal to the number of permanent cards in your graveyard and its toughness is equal to that number plus 1.",
)

STALACTITE_STALKER = make_creature(
    name="Stalactite Stalker",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Rogue"},
    text="Menace\nAt the beginning of your end step, if you descended this turn, put a +1/+1 counter on this creature. (You descended if a permanent card was put into your graveyard from anywhere.)\n{2}{B}, Sacrifice this creature: Target creature gets -X/-X until end of turn, where X is this creature's power.",
)

STARVING_REVENANT = make_creature(
    name="Starving Revenant",
    power=4, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Spirit"},
    text="When this creature enters, surveil 2. Then for each card you put on top of your library, you draw a card and you lose 3 life.\nDescend 8 — Whenever you draw a card, if there are eight or more permanent cards in your graveyard, target opponent loses 1 life and you gain 1 life.",
)

STINGING_CAVE_CRAWLER = make_creature(
    name="Stinging Cave Crawler",
    power=1, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Insect"},
    text="Deathtouch\nDescend 4 — Whenever this creature attacks, if there are four or more permanent cards in your graveyard, you draw a card and you lose 1 life.",
)

SYNAPSE_NECROMAGE = make_creature(
    name="Synapse Necromage",
    power=3, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Fungus", "Wizard"},
    text="When this creature dies, create two 1/1 black Fungus creature tokens with \"This token can't block.\"",
)

TARRIANS_JOURNAL = make_artifact(
    name="Tarrian's Journal",
    mana_cost="",
    text="",
    subtypes={"Cave"},
    supertypes={"Legendary"},
)

TERROR_TIDE = make_sorcery(
    name="Terror Tide",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Fathomless descent — All creatures get -X/-X until end of turn, where X is the number of permanent cards in your graveyard.",
)

TITHING_BLADE = make_artifact(
    name="Tithing Blade",
    mana_cost="",
    text="",
)

VISAGE_OF_DREAD = make_artifact_creature(
    name="Visage of Dread",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Dinosaur", "Horror", "Skeleton"},
    text="",
)

VITOS_INQUISITOR = make_creature(
    name="Vito's Inquisitor",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Knight", "Vampire"},
    text="{B}, Sacrifice another creature or artifact: Put a +1/+1 counter on this creature. It gains menace until end of turn.",
)

ABRADE = make_instant(
    name="Abrade",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Choose one —\n• Abrade deals 3 damage to target creature.\n• Destroy target artifact.",
)

ANCESTORS_AID = make_instant(
    name="Ancestors' Aid",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +2/+0 and gains first strike until end of turn.\nCreate a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

BELLIGERENT_YEARLING = make_creature(
    name="Belligerent Yearling",
    power=3, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur"},
    text="Trample\nWhenever another Dinosaur you control enters, you may have this creature's base power become equal to that creature's power until end of turn.",
)

BONEHOARD_DRACOSAUR = make_creature(
    name="Bonehoard Dracosaur",
    power=5, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur", "Dragon"},
    text="Flying, first strike\nAt the beginning of your upkeep, exile the top two cards of your library. You may play them this turn. If you exiled a land card this way, create a 3/1 red Dinosaur creature token. If you exiled a nonland card this way, create a Treasure token.",
)

BRASSS_TUNNELGRINDER = make_artifact(
    name="Brass's Tunnel-Grinder",
    mana_cost="",
    text="",
    subtypes={"Cave"},
    supertypes={"Legendary"},
)

BRAZEN_BLADEMASTER = make_creature(
    name="Brazen Blademaster",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Orc", "Pirate"},
    text="Whenever this creature attacks while you control two or more artifacts, it gets +2/+1 until end of turn.",
)

BREECHES_EAGER_PILLAGER = make_creature(
    name="Breeches, Eager Pillager",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Pirate"},
    supertypes={"Legendary"},
    text="First strike\nWhenever a Pirate you control attacks, choose one that hasn't been chosen this turn —\n• Create a Treasure token.\n• Target creature can't block this turn.\n• Exile the top card of your library. You may play it this turn.",
)

BURNING_SUN_CAVALRY = make_creature(
    name="Burning Sun Cavalry",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Knight"},
    text="Whenever this creature attacks or blocks while you control a Dinosaur, this creature gets +1/+1 until end of turn.",
)

CALAMITOUS_CAVEIN = make_sorcery(
    name="Calamitous Cave-In",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Calamitous Cave-In deals X damage to each creature and each planeswalker, where X is the number of Caves you control plus the number of Cave cards in your graveyard.",
)

CHILD_OF_THE_VOLCANO = make_creature(
    name="Child of the Volcano",
    power=3, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Trample\nAt the beginning of your end step, if you descended this turn, put a +1/+1 counter on this creature. (You descended if a permanent card was put into your graveyard from anywhere.)",
)

CURATOR_OF_SUNS_CREATION = make_creature(
    name="Curator of Sun's Creation",
    power=3, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Artificer", "Human"},
    text="Whenever you discover, discover again for the same value. This ability triggers only once each turn.",
)

DARING_DISCOVERY = make_sorcery(
    name="Daring Discovery",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="Up to three target creatures can't block this turn.\nDiscover 4. (Exile cards from the top of your library until you exile a nonland card with mana value 4 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
)

DIAMOND_PICKAXE = make_artifact(
    name="Diamond Pick-Axe",
    mana_cost="{R}",
    text="Indestructible (Effects that say \"destroy\" don't destroy this Equipment.)\nEquipped creature gets +1/+1 and has \"Whenever this creature attacks, create a Treasure token.\" (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nEquip {2}",
    subtypes={"Equipment"},
)

DINOTOMATON = make_artifact_creature(
    name="Dinotomaton",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur", "Gnome"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhen this creature enters, target creature you control gains menace until end of turn.",
)

DIRE_FLAIL = make_artifact(
    name="Dire Flail",
    mana_cost="",
    text="",
    subtypes={"//", "Artifact", "Equipment"},
)

DOWSING_DEVICE = make_artifact(
    name="Dowsing Device",
    mana_cost="",
    text="",
    subtypes={"Cave"},
)

DREADMAWS_IRE = make_instant(
    name="Dreadmaw's Ire",
    mana_cost="{R}",
    colors={Color.RED},
    text="Until end of turn, target attacking creature gets +2/+2 and gains trample and \"Whenever this creature deals combat damage to a player, destroy target artifact that player controls.\"",
)

ENTERPRISING_SCALLYWAG = make_creature(
    name="Enterprising Scallywag",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Pirate"},
    text="At the beginning of your end step, if you descended this turn, create a Treasure token. (You descended if a permanent card was put into your graveyard from anywhere.)",
)

ETALIS_FAVOR = make_enchantment(
    name="Etali's Favor",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Enchant creature you control\nWhen this Aura enters, discover 3. (Exile cards from the top of your library until you exile a nonland card with mana value 3 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)\nEnchanted creature gets +1/+1 and has trample.",
    subtypes={"Aura"},
)

GEOLOGICAL_APPRAISER = make_creature(
    name="Geological Appraiser",
    power=3, toughness=2,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Artificer", "Human"},
    text="When this creature enters, if you cast it, discover 3. (Exile cards from the top of your library until you exile a nonland card with mana value 3 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
)

AGEOLOGICAL_APPRAISER = make_creature(
    name="A-Geological Appraiser",
    power=3, toughness=2,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Artificer", "Human"},
    text="When Geological Appraiser enters, if you cast it, discover 3. (Exile cards from the top of your library until you exile a nonland card with mana value 3 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
)

GOBLIN_TOMB_RAIDER = make_creature(
    name="Goblin Tomb Raider",
    power=1, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Pirate"},
    text="As long as you control an artifact, this creature gets +1/+0 and has haste.",
)

GOLDFURY_STRIDER = make_artifact_creature(
    name="Goldfury Strider",
    power=3, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Golem"},
    text="Trample\nTap two untapped artifacts and/or creatures you control: Target creature gets +2/+0 until end of turn. Activate only as a sorcery.",
)

HIT_THE_MOTHER_LODE = make_sorcery(
    name="Hit the Mother Lode",
    mana_cost="{4}{R}{R}{R}",
    colors={Color.RED},
    text="Discover 10. If the discovered card's mana value is less than 10, create a number of tapped Treasure tokens equal to the difference. (To discover 10, exile cards from the top of your library until you exile a nonland card with mana value 10 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
)

HOTFOOT_GNOME = make_artifact_creature(
    name="Hotfoot Gnome",
    power=3, toughness=1,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Gnome"},
    text="Haste\n{T}: Another target creature gains haste until end of turn.",
)

IDOL_OF_THE_DEEP_KING = make_artifact(
    name="Idol of the Deep King",
    mana_cost="",
    text="",
    subtypes={"Equipment"},
)

INTI_SENESCHAL_OF_THE_SUN = make_creature(
    name="Inti, Seneschal of the Sun",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="Whenever you attack, you may discard a card. When you do, put a +1/+1 counter on target attacking creature. It gains trample until end of turn.\nWhenever you discard one or more cards, exile the top card of your library. You may play that card until your next end step.",
)

MAGMATIC_GALLEON = make_artifact(
    name="Magmatic Galleon",
    mana_cost="{3}{R}{R}",
    text="When this Vehicle enters, it deals 5 damage to target creature an opponent controls.\nWhenever one or more creatures your opponents control are dealt excess noncombat damage, create a Treasure token.\nCrew 2",
    subtypes={"Vehicle"},
)

OJER_AXONIL_DEEPEST_MIGHT = make_creature(
    name="Ojer Axonil, Deepest Might",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "God", "Land"},
    supertypes={"Legendary"},
    text="",
)

PANICKED_ALTISAUR = make_creature(
    name="Panicked Altisaur",
    power=4, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur"},
    text="Reach\n{T}: This creature deals 2 damage to each opponent.",
)

PLUNDERING_PIRATE = make_creature(
    name="Plundering Pirate",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Orc", "Pirate"},
    text="When this creature enters, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

POETIC_INGENUITY = make_enchantment(
    name="Poetic Ingenuity",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Whenever one or more Dinosaurs you control attack, create that many Treasure tokens.\nWhenever you cast an artifact spell, create a 3/1 red Dinosaur creature token. This ability triggers only once each turn.",
)

RAMPAGING_CERATOPS = make_creature(
    name="Rampaging Ceratops",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur"},
    text="This creature can't be blocked except by three or more creatures.",
)

RUMBLING_ROCKSLIDE = make_sorcery(
    name="Rumbling Rockslide",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Rumbling Rockslide deals damage to target creature equal to the number of lands you control.",
)

SAHEELIS_LATTICE = make_artifact_creature(
    name="Saheeli's Lattice",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Dinosaur"},
    text="",
)

SCYTHECLAW_RAPTOR = make_creature(
    name="Scytheclaw Raptor",
    power=4, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur"},
    text="Whenever a player casts a spell, if it's not their turn, this creature deals 4 damage to them.",
)

SEISMIC_MONSTROSAUR = make_creature(
    name="Seismic Monstrosaur",
    power=6, toughness=5,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur"},
    text="Trample\n{2}{R}, Sacrifice a land: Draw a card.\nMountaincycling {2} ({2}, Discard this card: Search your library for a Mountain card, reveal it, put it into your hand, then shuffle.)",
)

SUNFIRE_TORCH = make_artifact(
    name="Sunfire Torch",
    mana_cost="{R}",
    text="Equipped creature gets +1/+0 and has \"Whenever this creature attacks, you may sacrifice Sunfire Torch. When you do, this creature deals 2 damage to any target.\"\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

SUNSHOT_MILITIA = make_creature(
    name="Sunshot Militia",
    power=1, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="Tap two untapped artifacts and/or creatures you control: This creature deals 1 damage to each opponent. Activate only as a sorcery.",
)

TECTONIC_HAZARD = make_sorcery(
    name="Tectonic Hazard",
    mana_cost="{R}",
    colors={Color.RED},
    text="Tectonic Hazard deals 1 damage to each opponent and each creature they control.",
)

TRIUMPHANT_CHOMP = make_sorcery(
    name="Triumphant Chomp",
    mana_cost="{R}",
    colors={Color.RED},
    text="Triumphant Chomp deals damage to target creature equal to 2 or the greatest power among Dinosaurs you control, whichever is greater.",
)

TRUMPETING_CARNOSAUR = make_creature(
    name="Trumpeting Carnosaur",
    power=7, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur"},
    text="Trample\nWhen this creature enters, discover 5.\n{2}{R}, Discard this card: It deals 3 damage to target creature or planeswalker.",
)

VOLATILE_WANDERGLYPH = make_artifact_creature(
    name="Volatile Wanderglyph",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Golem"},
    text="Whenever this creature becomes tapped, you may discard a card. If you do, draw a card.",
)

ZOYOWAS_JUSTICE = make_instant(
    name="Zoyowa's Justice",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="The owner of target artifact or creature with mana value 1 or greater shuffles it into their library. Then that player discovers X, where X is its mana value. (They exile cards from the top of their library until they exile a nonland card with that mana value or less. They cast it without paying its mana cost or put it into their hand. They put the rest on the bottom in a random order.)",
)

ARMORED_KINCALLER = make_creature(
    name="Armored Kincaller",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="When this creature enters, you may reveal a Dinosaur card from your hand. If you do or if you control another Dinosaur, you gain 3 life.",
)

BASKING_CAPYBARA = make_creature(
    name="Basking Capybara",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Capybara"},
    text="Descend 4 — This creature gets +3/+0 as long as there are four or more permanent cards in your graveyard.",
)

BEDROCK_TORTOISE = make_creature(
    name="Bedrock Tortoise",
    power=0, toughness=6,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Turtle"},
    text="During your turn, creatures you control have hexproof.\nEach creature you control with toughness greater than its power assigns combat damage equal to its toughness rather than its power.",
)

CAVERN_STOMPER = make_creature(
    name="Cavern Stomper",
    power=7, toughness=7,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="When this creature enters, scry 2. (Look at the top two cards of your library, then put any number of them on the bottom and the rest on top in any order.)\n{3}{G}: This creature can't be blocked by creatures with power 2 or less this turn.",
)

CENOTE_SCOUT = make_creature(
    name="Cenote Scout",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Merfolk", "Scout"},
    text="When this creature enters, it explores. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put the card back or put it into your graveyard.)",
)

COATI_SCAVENGER = make_creature(
    name="Coati Scavenger",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Raccoon"},
    text="Descend 4 — When this creature enters, if there are four or more permanent cards in your graveyard, return target permanent card from your graveyard to your hand.",
)

COLOSSADACTYL = make_creature(
    name="Colossadactyl",
    power=4, toughness=5,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Reach, trample",
)

COSMIUM_CONFLUENCE = make_sorcery(
    name="Cosmium Confluence",
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    text="Choose three. You may choose the same mode more than once.\n• Search your library for a Cave card, put it onto the battlefield tapped, then shuffle.\n• Put three +1/+1 counters on a Cave you control. It becomes a 0/0 Elemental creature with haste. It's still a land.\n• Destroy target enchantment.",
)

DISTURBED_SLUMBER = make_instant(
    name="Disturbed Slumber",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Until end of turn, target land you control becomes a 4/4 Dinosaur creature with reach and haste. It's still a land. It must be blocked this turn if able.",
)

EARTHSHAKER_DREADMAW = make_creature(
    name="Earthshaker Dreadmaw",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Trample\nWhen this creature enters, draw a card for each other Dinosaur you control.",
)

EXPLORERS_CACHE = make_artifact(
    name="Explorer's Cache",
    mana_cost="{1}{G}",
    text="This artifact enters with two +1/+1 counters on it.\nWhenever a creature you control with a +1/+1 counter on it dies, put a +1/+1 counter on this artifact.\n{T}: Move a +1/+1 counter from this artifact onto target creature. Activate only as a sorcery.",
)

GHALTA_STAMPEDE_TYRANT = make_creature(
    name="Ghalta, Stampede Tyrant",
    power=12, toughness=12,
    mana_cost="{5}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur", "Elder"},
    supertypes={"Legendary"},
    text="Trample\nWhen Ghalta enters, put any number of creature cards from your hand onto the battlefield.",
)

GLIMPSE_THE_CORE = make_sorcery(
    name="Glimpse the Core",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Search your library for a basic Forest card, put that card onto the battlefield tapped, then shuffle.\n• Return target Cave card from your graveyard to the battlefield tapped.",
)

GLOWCAP_LANTERN = make_artifact(
    name="Glowcap Lantern",
    mana_cost="{G}",
    text="Equipped creature has \"You may look at the top card of your library any time\" and \"Whenever this creature attacks, it explores.\" (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on that creature, then put the card back or put it into your graveyard.)\nEquip {2}",
    subtypes={"Equipment"},
)

GROWING_RITES_OF_ITLIMOC = make_enchantment(
    name="Growing Rites of Itlimoc",
    mana_cost="",
    colors=set(),
    text="",
    supertypes={"Legendary"},
)

HUATLI_POET_OF_UNITY = make_creature(
    name="Huatli, Poet of Unity",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Bard", "Enchantment", "Human", "Warrior"},
    supertypes={"Legendary"},
    text="",
)

HUATLIS_FINAL_STRIKE = make_instant(
    name="Huatli's Final Strike",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +1/+0 until end of turn. It deals damage equal to its power to target creature an opponent controls.",
)

HULKING_RAPTOR = make_creature(
    name="Hulking Raptor",
    power=5, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Ward {2}\nAt the beginning of your first main phase, add {G}{G}.",
)

IN_THE_PRESENCE_OF_AGES = make_instant(
    name="In the Presence of Ages",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Reveal the top four cards of your library. You may put a creature card and/or a land card from among them into your hand. Put the rest into your graveyard.",
)

INTREPID_PALEONTOLOGIST = make_creature(
    name="Intrepid Paleontologist",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Human"},
    text="{T}: Add one mana of any color.\n{2}: Exile target card from a graveyard.\nYou may cast Dinosaur creature spells from among cards you own exiled with this creature. If you cast a spell this way, that creature enters with a finality counter on it. (If a creature with a finality counter on it would die, exile it instead.)",
)

IXALLIS_LOREKEEPER = make_creature(
    name="Ixalli's Lorekeeper",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Human"},
    text="{T}: Add one mana of any color. Spend this mana only to cast a Dinosaur spell or activate an ability of a Dinosaur source.",
)

JADE_SEEDSTONES = make_artifact_creature(
    name="Jade Seedstones",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Golem"},
    text="",
)

JADELIGHT_SPELUNKER = make_creature(
    name="Jadelight Spelunker",
    power=1, toughness=1,
    mana_cost="{X}{G}",
    colors={Color.GREEN},
    subtypes={"Merfolk", "Scout"},
    text="When this creature enters, it explores X times. (To have it explore, reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on that creature, then put the card back or put it into your graveyard.)",
)

KASLEMS_STONETREE = make_artifact_creature(
    name="Kaslem's Stonetree",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Golem"},
    text="",
)

MALAMET_BATTLE_GLYPH = make_sorcery(
    name="Malamet Battle Glyph",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Choose target creature you control and target creature you don't control. If the creature you control entered this turn, put a +1/+1 counter on it. Then those creatures fight each other.",
)

MALAMET_BRAWLER = make_creature(
    name="Malamet Brawler",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Cat", "Warrior"},
    text="Whenever this creature attacks, target attacking creature gains trample until end of turn.",
)

MALAMET_SCYTHE = make_artifact(
    name="Malamet Scythe",
    mana_cost="{2}{G}",
    text="Flash\nWhen this Equipment enters, attach it to target creature you control.\nEquipped creature gets +2/+2.\nEquip {4} ({4}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

MALAMET_VETERAN = make_creature(
    name="Malamet Veteran",
    power=5, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Cat", "Warrior"},
    text="Trample\nDescend 4 — Whenever this creature attacks, if there are four or more permanent cards in your graveyard, put a +1/+1 counter on target creature.",
)

MINESHAFT_SPIDER = make_creature(
    name="Mineshaft Spider",
    power=3, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Spider"},
    text="Reach\nWhen this creature enters, you may mill two cards. (You may put the top two cards of your library into your graveyard.)",
)

NURTURING_BRISTLEBACK = make_creature(
    name="Nurturing Bristleback",
    power=5, toughness=5,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="When this creature enters, create a 3/3 green Dinosaur creature token.\nForestcycling {2} ({2}, Discard this card: Search your library for a Forest card, reveal it, put it into your hand, then shuffle.)",
)

OJER_KASLEM_DEEPEST_GROWTH = make_creature(
    name="Ojer Kaslem, Deepest Growth",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "God", "Land"},
    supertypes={"Legendary"},
    text="",
)

OVER_THE_EDGE = make_sorcery(
    name="Over the Edge",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Destroy target artifact or enchantment.\n• Target creature you control explores, then it explores again. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on that creature, then put the card back or put it into your graveyard. Then repeat this process.)",
)

PATHFINDING_AXEJAW = make_creature(
    name="Pathfinding Axejaw",
    power=4, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="When this creature enters, it explores. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put the card back or put it into your graveyard.)",
)

POISON_DART_FROG = make_creature(
    name="Poison Dart Frog",
    power=1, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Frog"},
    text="Reach\n{T}: Add one mana of any color.\n{2}: This creature gains deathtouch until end of turn.",
)

PUGNACIOUS_HAMMERSKULL = make_creature(
    name="Pugnacious Hammerskull",
    power=6, toughness=6,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Whenever this creature attacks while you don't control another Dinosaur, put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

RIVER_HERALD_GUIDE = make_creature(
    name="River Herald Guide",
    power=3, toughness=1,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Merfolk", "Scout"},
    text="Vigilance\nWhen this creature enters, it explores. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put the card back or put it into your graveyard.)",
)

SEEKER_OF_SUNLIGHT = make_creature(
    name="Seeker of Sunlight",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Merfolk", "Scout"},
    text="{2}{G}: This creature explores. Activate only as a sorcery. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put the card back or put it into your graveyard.)",
)

SENTINEL_OF_THE_NAMELESS_CITY = make_creature(
    name="Sentinel of the Nameless City",
    power=3, toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Merfolk", "Scout", "Warrior"},
    text="Vigilance\nWhenever this creature enters or attacks, create a Map token. (It's an artifact with \"{1}, {T}, Sacrifice this token: Target creature you control explores. Activate only as a sorcery.\")",
)

THE_SKULLSPORE_NEXUS = make_artifact(
    name="The Skullspore Nexus",
    mana_cost="{6}{G}{G}",
    text="This spell costs {X} less to cast, where X is the greatest power among creatures you control.\nWhenever one or more nontoken creatures you control die, create a green Fungus Dinosaur creature token with base power and toughness each equal to the total power of those creatures.\n{2}, {T}: Double target creature's power until end of turn.",
    supertypes={"Legendary"},
)

SPELUNKING = make_enchantment(
    name="Spelunking",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, draw a card, then you may put a land card from your hand onto the battlefield. If you put a Cave onto the battlefield this way, you gain 4 life.\nLands you control enter untapped.",
)

STAGGERING_SIZE = make_instant(
    name="Staggering Size",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 and gains trample until end of turn.",
)

TENDRIL_OF_THE_MYCOTYRANT = make_creature(
    name="Tendril of the Mycotyrant",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Fungus", "Wizard"},
    text="{5}{G}{G}: Put seven +1/+1 counters on target noncreature land you control. It becomes a 0/0 Fungus creature with haste. It's still a land.",
)

THRASHING_BRONTODON = make_creature(
    name="Thrashing Brontodon",
    power=3, toughness=4,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="{1}, Sacrifice this creature: Destroy target artifact or enchantment.",
)

TWISTS_AND_TURNS = make_enchantment(
    name="Twists and Turns",
    mana_cost="",
    colors=set(),
    text="",
    subtypes={"Cave"},
)

WALK_WITH_THE_ANCESTORS = make_sorcery(
    name="Walk with the Ancestors",
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    text="Return up to one target permanent card from your graveyard to your hand. Discover 4. (Exile cards from the top of your library until you exile a nonland card with mana value 4 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
)

ABUELO_ANCESTRAL_ECHO = make_creature(
    name="Abuelo, Ancestral Echo",
    power=2, toughness=2,
    mana_cost="{1}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    text="Flying, ward {2}\n{1}{W}{U}: Exile another target creature or artifact you control. Return it to the battlefield under its owner's control at the beginning of the next end step.",
)

AKAWALLI_THE_SEETHING_TOWER = make_creature(
    name="Akawalli, the Seething Tower",
    power=3, toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Fungus"},
    supertypes={"Legendary"},
    text="Descend 4 — As long as there are four or more permanent cards in your graveyard, Akawalli gets +2/+2 and has trample.\nDescend 8 — As long as there are eight or more permanent cards in your graveyard, Akawalli gets an additional +2/+2 and can't be blocked by more than one creature.",
)

AMALIA_BENAVIDES_AGUIRRE = make_creature(
    name="Amalia Benavides Aguirre",
    power=2, toughness=2,
    mana_cost="{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Scout", "Vampire"},
    supertypes={"Legendary"},
    text="Ward—Pay 3 life.\nWhenever you gain life, Amalia Benavides Aguirre explores. Then destroy all other creatures if its power is exactly 20. (To have this creature explore, reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put the card back or put it into your graveyard.)",
)

THE_ANCIENT_ONE = make_creature(
    name="The Ancient One",
    power=8, toughness=8,
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"God", "Spirit"},
    supertypes={"Legendary"},
    text="Descend 8 — The Ancient One can't attack or block unless there are eight or more permanent cards in your graveyard.\n{2}{U}{B}: Draw a card, then discard a card. When you discard a card this way, target player mills cards equal to its mana value.",
)

ANIM_PAKAL_THOUSANDTH_MOON = make_creature(
    name="Anim Pakal, Thousandth Moon",
    power=1, toughness=2,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Whenever you attack with one or more non-Gnome creatures, put a +1/+1 counter on Anim Pakal, then create X 1/1 colorless Gnome artifact creature tokens that are tapped and attacking, where X is the number of +1/+1 counters on Anim Pakal.",
)

BARTOLOM_DEL_PRESIDIO = make_creature(
    name="Bartolomé del Presidio",
    power=2, toughness=1,
    mana_cost="{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Knight", "Vampire"},
    supertypes={"Legendary"},
    text="Sacrifice another creature or artifact: Put a +1/+1 counter on Bartolomé del Presidio.",
)

THE_BELLIGERENT = make_artifact(
    name="The Belligerent",
    mana_cost="{2}{U}{R}",
    text="Whenever The Belligerent attacks, create a Treasure token. Until end of turn, you may look at the top card of your library any time, and you may play lands and cast spells from the top of your library.\nCrew 3",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
)

CAPAROCTI_SUNBORN = make_creature(
    name="Caparocti Sunborn",
    power=4, toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Whenever Caparocti Sunborn attacks, you may tap two untapped artifacts and/or creatures you control. If you do, discover 3. (Exile cards from the top of your library until you exile a nonland card with mana value 3 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
)

CAPTAIN_STORM_COSMIUM_RAIDER = make_creature(
    name="Captain Storm, Cosmium Raider",
    power=2, toughness=2,
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Whenever an artifact you control enters, put a +1/+1 counter on target Pirate you control.",
)

DEEPFATHOM_ECHO = make_creature(
    name="Deepfathom Echo",
    power=4, toughness=4,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Merfolk", "Spirit"},
    text="At the beginning of combat on your turn, this creature explores. Then you may have it become a copy of another creature you control until end of turn. (To have this creature explore, reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put the card back or put it into your graveyard.)",
)

GISHATH_SUNS_AVATAR = make_creature(
    name="Gishath, Sun's Avatar",
    power=7, toughness=6,
    mana_cost="{5}{R}{G}{W}",
    colors={Color.GREEN, Color.RED, Color.WHITE},
    subtypes={"Avatar", "Dinosaur"},
    supertypes={"Legendary"},
    text="Vigilance, trample, haste\nWhenever Gishath deals combat damage to a player, reveal that many cards from the top of your library. Put any number of Dinosaur creature cards from among them onto the battlefield and the rest on the bottom of your library in a random order.",
)

ITZQUINTH_FIRSTBORN_OF_GISHATH = make_creature(
    name="Itzquinth, Firstborn of Gishath",
    power=2, toughness=3,
    mana_cost="{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Dinosaur"},
    supertypes={"Legendary"},
    text="Haste\nWhen Itzquinth enters, you may pay {2}. When you do, target Dinosaur you control deals damage equal to its power to another target creature.",
)

KELLAN_DARING_TRAVELER = make_creature(
    name="Kellan, Daring Traveler",
    power=2, toughness=3,
    mana_cost="{1}{W} // {G}",
    colors={Color.WHITE},
    subtypes={"//", "Faerie", "Human", "Scout", "Sorcery"},
    supertypes={"Legendary"},
    text="",
)

KUTZIL_MALAMET_EXEMPLAR = make_creature(
    name="Kutzil, Malamet Exemplar",
    power=3, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Cat", "Warrior"},
    supertypes={"Legendary"},
    text="Your opponents can't cast spells during your turn.\nWhenever one or more creatures you control each with power greater than its base power deals combat damage to a player, draw a card.",
)

MASTERS_GUIDEMURAL = make_artifact(
    name="Master's Guide-Mural",
    mana_cost="",
    text="",
)

MOLTEN_COLLAPSE = make_sorcery(
    name="Molten Collapse",
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Choose one. If you descended this turn, you may choose both instead. (You descended if a permanent card was put into your graveyard from anywhere.)\n• Destroy target creature or planeswalker.\n• Destroy target noncreature, nonland permanent with mana value 1 or less.",
)

THE_MYCOTYRANT = make_creature(
    name="The Mycotyrant",
    power=0, toughness=0,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Elder", "Fungus"},
    supertypes={"Legendary"},
    text="Trample\nThe Mycotyrant's power and toughness are each equal to the number of creatures you control that are Fungi and/or Saprolings.\nAt the beginning of your end step, create X 1/1 black Fungus creature tokens with \"This token can't block,\" where X is the number of times you descended this turn. (You descend each time a permanent card is put into your graveyard from anywhere.)",
)

NICANZIL_CURRENT_CONDUCTOR = make_creature(
    name="Nicanzil, Current Conductor",
    power=2, toughness=3,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Merfolk", "Scout"},
    supertypes={"Legendary"},
    text="Whenever a creature you control explores a land card, you may put a land card from your hand onto the battlefield tapped.\nWhenever a creature you control explores a nonland card, put a +1/+1 counter on Nicanzil.",
)

PALANIS_HATCHER = make_creature(
    name="Palani's Hatcher",
    power=5, toughness=3,
    mana_cost="{3}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Dinosaur"},
    text="Other Dinosaurs you control have haste.\nWhen this creature enters, create two 0/1 green Dinosaur Egg creature tokens.\nAt the beginning of combat on your turn, if you control one or more Eggs, sacrifice an Egg, then create a 3/3 green Dinosaur creature token.",
)

QUINTORIUS_KAND = make_planeswalker(
    name="Quintorius Kand",
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    loyalty=4,
    subtypes={"Quintorius"},
    supertypes={"Legendary"},
    text="Whenever you cast a spell from exile, Quintorius Kand deals 2 damage to each opponent and you gain 2 life.\n+1: Create a 3/2 red and white Spirit creature token.\n−3: Discover 4.\n−6: Exile any number of target cards from your graveyard. Add {R} for each card exiled this way. You may play those cards this turn.",
)

SAHEELI_THE_SUNS_BRILLIANCE = make_creature(
    name="Saheeli, the Sun's Brilliance",
    power=2, toughness=2,
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Artificer", "Human"},
    supertypes={"Legendary"},
    text="{U}{R}, {T}: Create a token that's a copy of another target creature or artifact you control, except it's an artifact in addition to its other types. It gains haste. Sacrifice it at the beginning of the next end step.",
)

SOVEREIGN_OKINEC_AHAU = make_creature(
    name="Sovereign Okinec Ahau",
    power=3, toughness=4,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Cat", "Noble"},
    supertypes={"Legendary"},
    text="Ward {2}\nWhenever Sovereign Okinec Ahau attacks, for each creature you control with power greater than that creature's base power, put a number of +1/+1 counters on that creature equal to the difference.",
)

SQUIRMING_EMERGENCE = make_sorcery(
    name="Squirming Emergence",
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Fathomless descent — Return to the battlefield target nonland permanent card in your graveyard with mana value less than or equal to the number of permanent cards in your graveyard.",
)

UCHBENBAK_THE_GREAT_MISTAKE = make_creature(
    name="Uchbenbak, the Great Mistake",
    power=6, toughness=4,
    mana_cost="{3}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Horror", "Skeleton"},
    supertypes={"Legendary"},
    text="Vigilance, menace\nDescend 8 — {4}{U}{B}: Return this card from your graveyard to the battlefield with a finality counter on it. Activate only if there are eight or more permanent cards in your graveyard and only as a sorcery. (If a creature with a finality counter on it would die, exile it instead.)",
)

VITO_FANATIC_OF_ACLAZOTZ = make_creature(
    name="Vito, Fanatic of Aclazotz",
    power=4, toughness=4,
    mana_cost="{2}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Demon", "Vampire"},
    supertypes={"Legendary"},
    text="Flying\nWhenever you sacrifice another permanent, you gain 2 life if this is the first time this ability has resolved this turn. If it's the second time, each opponent loses 2 life. If it's the third time, create a 4/3 white and black Vampire Demon creature token with flying.",
)

WAIL_OF_THE_FORGOTTEN = make_sorcery(
    name="Wail of the Forgotten",
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    text="Descend 8 — Choose one. If there are eight or more permanent cards in your graveyard as you cast this spell, choose one or more instead.\n• Return target nonland permanent to its owner's hand.\n• Target opponent discards a card.\n• Look at the top three cards of your library. Put one of them into your hand and the rest into your graveyard.",
)

ZOYOWA_LAVATONGUE = make_creature(
    name="Zoyowa Lava-Tongue",
    power=2, toughness=2,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Goblin", "Warlock"},
    supertypes={"Legendary"},
    text="Deathtouch\nAt the beginning of your end step, if you descended this turn, each opponent may discard a card or sacrifice a permanent of their choice. Zoyowa deals 3 damage to each opponent who didn't. (You descended if a permanent card was put into your graveyard from anywhere.)",
)

BURIED_TREASURE = make_artifact(
    name="Buried Treasure",
    mana_cost="{2}",
    text="{T}, Sacrifice this artifact: Add one mana of any color.\n{5}, Exile this card from your graveyard: Discover 5. Activate only as a sorcery. (Exile cards from the top of your library until you exile a nonland card with mana value 5 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
    subtypes={"Treasure"},
)

CAREENING_MINE_CART = make_artifact(
    name="Careening Mine Cart",
    mana_cost="{3}",
    text="Whenever this Vehicle attacks, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
)

CARTOGRAPHERS_COMPANION = make_artifact_creature(
    name="Cartographer's Companion",
    power=2, toughness=1,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Gnome"},
    text="When this creature enters, create a Map token. (It's an artifact with \"{1}, {T}, Sacrifice this token: Target creature you control explores. Activate only as a sorcery.\")",
)

CHIMIL_THE_INNER_SUN = make_artifact(
    name="Chimil, the Inner Sun",
    mana_cost="{6}",
    text="Spells you control can't be countered.\nAt the beginning of your end step, discover 5. (Exile cards from the top of your library until you exile a nonland card with mana value 5 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
    supertypes={"Legendary"},
)

COMPASS_GNOME = make_artifact_creature(
    name="Compass Gnome",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Gnome"},
    text="When this creature enters, you may search your library for a basic land card or Cave card, reveal it, then shuffle and put that card on top.",
)

CONTESTED_GAME_BALL = make_artifact(
    name="Contested Game Ball",
    mana_cost="{2}",
    text="Whenever you're dealt combat damage, the attacking player gains control of this artifact and untaps it.\n{2}, {T}: Draw a card and put a point counter on this artifact. Then if it has five or more point counters on it, sacrifice it and create a Treasure token.",
)

DIGSITE_CONSERVATOR = make_artifact_creature(
    name="Digsite Conservator",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Gnome"},
    text="Sacrifice this creature: Exile up to four target cards from a single graveyard. Activate only as a sorcery.\nWhen this creature dies, you may pay {4}. If you do, discover 4. (Exile cards from the top of your library until you exile a nonland card with mana value 4 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
)

DISRUPTOR_WANDERGLYPH = make_artifact_creature(
    name="Disruptor Wanderglyph",
    power=3, toughness=4,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Golem"},
    text="Whenever this creature attacks, exile target card from an opponent's graveyard.",
)

HOVERSTONE_PILGRIM = make_artifact_creature(
    name="Hoverstone Pilgrim",
    power=2, toughness=5,
    mana_cost="{5}",
    colors=set(),
    subtypes={"Golem"},
    text="Flying\nWard {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\n{2}: Put target card from a graveyard on the bottom of its owner's library.",
)

HUNTERS_BLOWGUN = make_artifact(
    name="Hunter's Blowgun",
    mana_cost="{1}",
    text="Equipped creature gets +1/+1.\nEquipped creature has deathtouch during your turn. Otherwise, it has reach.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

MATZALANTLI_THE_GREAT_DOOR = make_artifact(
    name="Matzalantli, the Great Door",
    mana_cost="",
    text="",
    supertypes={"Legendary"},
)

THE_MILLENNIUM_CALENDAR = make_artifact(
    name="The Millennium Calendar",
    mana_cost="{1}",
    text="Whenever you untap one or more permanents during your untap step, put that many time counters on The Millennium Calendar.\n{2}, {T}: Double the number of time counters on The Millennium Calendar.\nWhen there are 1,000 or more time counters on The Millennium Calendar, sacrifice it and each opponent loses 1,000 life.",
    supertypes={"Legendary"},
)

ROAMING_THRONE = make_artifact_creature(
    name="Roaming Throne",
    power=4, toughness=4,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Golem"},
    text="Ward {2}\nAs this creature enters, choose a creature type.\nThis creature is the chosen type in addition to its other types.\nIf a triggered ability of another creature you control of the chosen type triggers, it triggers an additional time.",
)

RUNAWAY_BOULDER = make_artifact(
    name="Runaway Boulder",
    mana_cost="{6}",
    text="Flash\nWhen this artifact enters, it deals 6 damage to target creature an opponent controls.\nCycling {2} ({2}, Discard this card: Draw a card.)",
)

SCAMPERING_SURVEYOR = make_artifact_creature(
    name="Scampering Surveyor",
    power=3, toughness=2,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Gnome"},
    text="When this creature enters, search your library for a basic land card or Cave card, put it onto the battlefield tapped, then shuffle.",
)

SORCEROUS_SPYGLASS = make_artifact(
    name="Sorcerous Spyglass",
    mana_cost="{2}",
    text="As this artifact enters, look at an opponent's hand, then choose any card name.\nActivated abilities of sources with the chosen name can't be activated unless they're mana abilities.",
)

SUNBIRD_STANDARD = make_artifact_creature(
    name="Sunbird Standard",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Bird", "Construct"},
    text="",
)

SWASHBUCKLERS_WHIP = make_artifact(
    name="Swashbuckler's Whip",
    mana_cost="{1}",
    text="Equipped creature has reach, \"{2}, {T}: Tap target artifact or creature,\" and \"{8}, {T}: Discover 10.\" (Exile cards from the top of your library until you exile a nonland card with mana value 10 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)\nEquip {1}",
    subtypes={"Equipment"},
)

TARRIANS_SOULCLEAVER = make_artifact(
    name="Tarrian's Soulcleaver",
    mana_cost="{1}",
    text="Equipped creature has vigilance.\nWhenever another artifact or creature is put into a graveyard from the battlefield, put a +1/+1 counter on equipped creature.\nEquip {2}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
)

THREEFOLD_THUNDERHULK = make_artifact_creature(
    name="Threefold Thunderhulk",
    power=0, toughness=0,
    mana_cost="{7}",
    colors=set(),
    subtypes={"Gnome"},
    text="This creature enters with three +1/+1 counters on it.\nWhenever this creature enters or attacks, create a number of 1/1 colorless Gnome artifact creature tokens equal to its power.\n{2}, Sacrifice another artifact: Put a +1/+1 counter on this creature.",
)

THRONE_OF_THE_GRIM_CAPTAIN = make_artifact_creature(
    name="Throne of the Grim Captain",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Pirate", "Skeleton", "Spirit"},
    supertypes={"Legendary"},
    text="",
)

TREASURE_MAP = make_artifact(
    name="Treasure Map",
    mana_cost="",
    text="",
)

CAPTIVATING_CAVE = make_land(
    name="Captivating Cave",
    text="{T}: Add {C}.\n{1}, {T}: Add one mana of any color.\n{4}, {T}, Sacrifice this land: Put two +1/+1 counters on target creature. Activate only as a sorcery.",
    subtypes={"Cave"},
)

CAVERN_OF_SOULS = make_land(
    name="Cavern of Souls",
    text="As this land enters, choose a creature type.\n{T}: Add {C}.\n{T}: Add one mana of any color. Spend this mana only to cast a creature spell of the chosen type, and that spell can't be countered.",
)

CAVERNOUS_MAW = make_land(
    name="Cavernous Maw",
    text="{T}: Add {C}.\n{2}: This land becomes a 3/3 Elemental creature until end of turn. It's still a Cave land. Activate only if the number of other Caves you control plus the number of Cave cards in your graveyard is three or greater.",
    subtypes={"Cave"},
)

ECHOING_DEEPS = make_land(
    name="Echoing Deeps",
    text="You may have this land enter tapped as a copy of any land card in a graveyard, except it's a Cave in addition to its other types.\n{T}: Add {C}.",
    subtypes={"Cave"},
)

FORGOTTEN_MONUMENT = make_land(
    name="Forgotten Monument",
    text="{T}: Add {C}.\nOther Caves you control have \"{T}, Pay 1 life: Add one mana of any color.\"",
    subtypes={"Cave"},
)

HIDDEN_CATARACT = make_land(
    name="Hidden Cataract",
    text="This land enters tapped.\n{T}: Add {U}.\n{4}{U}, {T}, Sacrifice this land: Discover 4. Activate only as a sorcery. (Exile cards from the top of your library until you exile a nonland card with mana value 4 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
    subtypes={"Cave"},
)

HIDDEN_COURTYARD = make_land(
    name="Hidden Courtyard",
    text="This land enters tapped.\n{T}: Add {W}.\n{4}{W}, {T}, Sacrifice this land: Discover 4. Activate only as a sorcery. (Exile cards from the top of your library until you exile a nonland card with mana value 4 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
    subtypes={"Cave"},
)

HIDDEN_NECROPOLIS = make_land(
    name="Hidden Necropolis",
    text="This land enters tapped.\n{T}: Add {B}.\n{4}{B}, {T}, Sacrifice this land: Discover 4. Activate only as a sorcery. (Exile cards from the top of your library until you exile a nonland card with mana value 4 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
    subtypes={"Cave"},
)

HIDDEN_NURSERY = make_land(
    name="Hidden Nursery",
    text="This land enters tapped.\n{T}: Add {G}.\n{4}{G}, {T}, Sacrifice this land: Discover 4. Activate only as a sorcery. (Exile cards from the top of your library until you exile a nonland card with mana value 4 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
    subtypes={"Cave"},
)

HIDDEN_VOLCANO = make_land(
    name="Hidden Volcano",
    text="This land enters tapped.\n{T}: Add {R}.\n{4}{R}, {T}, Sacrifice this land: Discover 4. Activate only as a sorcery. (Exile cards from the top of your library until you exile a nonland card with mana value 4 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
    subtypes={"Cave"},
)

PIT_OF_OFFERINGS = make_land(
    name="Pit of Offerings",
    text="This land enters tapped.\nWhen this land enters, exile up to three target cards from graveyards.\n{T}: Add {C}.\n{T}: Add one mana of any of the exiled cards' colors.",
    subtypes={"Cave"},
)

PROMISING_VEIN = make_land(
    name="Promising Vein",
    text="{T}: Add {C}.\n{1}, {T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
    subtypes={"Cave"},
)

RESTLESS_ANCHORAGE = make_land(
    name="Restless Anchorage",
    text="This land enters tapped.\n{T}: Add {W} or {U}.\n{1}{W}{U}: Until end of turn, this land becomes a 2/3 white and blue Bird creature with flying. It's still a land.\nWhenever this land attacks, create a Map token.",
)

RESTLESS_PRAIRIE = make_land(
    name="Restless Prairie",
    text="This land enters tapped.\n{T}: Add {G} or {W}.\n{2}{G}{W}: This land becomes a 3/3 green and white Llama creature until end of turn. It's still a land.\nWhenever this land attacks, other creatures you control get +1/+1 until end of turn.",
)

RESTLESS_REEF = make_land(
    name="Restless Reef",
    text="This land enters tapped.\n{T}: Add {U} or {B}.\n{2}{U}{B}: Until end of turn, this land becomes a 4/4 blue and black Shark creature with deathtouch. It's still a land.\nWhenever this land attacks, target player mills four cards.",
)

RESTLESS_RIDGELINE = make_land(
    name="Restless Ridgeline",
    text="This land enters tapped.\n{T}: Add {R} or {G}.\n{2}{R}{G}: This land becomes a 3/4 red and green Dinosaur creature until end of turn. It's still a land.\nWhenever this land attacks, another target attacking creature gets +2/+0 until end of turn. Untap that creature.",
)

RESTLESS_VENTS = make_land(
    name="Restless Vents",
    text="This land enters tapped.\n{T}: Add {B} or {R}.\n{1}{B}{R}: Until end of turn, this land becomes a 2/3 black and red Insect creature with menace. It's still a land.\nWhenever this land attacks, you may discard a card. If you do, draw a card.",
)

SUNKEN_CITADEL = make_land(
    name="Sunken Citadel",
    text="This land enters tapped. As it enters, choose a color.\n{T}: Add one mana of the chosen color.\n{T}: Add two mana of the chosen color. Spend this mana only to activate abilities of land sources.",
    subtypes={"Cave"},
)

VOLATILE_FAULT = make_land(
    name="Volatile Fault",
    text="{T}: Add {C}.\n{1}, {T}, Sacrifice this land: Destroy target nonbasic land an opponent controls. That player may search their library for a basic land card, put it onto the battlefield, then shuffle. You create a Treasure token.",
    subtypes={"Cave"},
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

LOST_CAVERNS_IXALAN_CARDS = {
    "Abuelo's Awakening": ABUELOS_AWAKENING,
    "Acrobatic Leap": ACROBATIC_LEAP,
    "Adaptive Gemguard": ADAPTIVE_GEMGUARD,
    "Attentive Sunscribe": ATTENTIVE_SUNSCRIBE,
    "Bat Colony": BAT_COLONY,
    "Clay-Fired Bricks": CLAYFIRED_BRICKS,
    "Cosmium Blast": COSMIUM_BLAST,
    "Dauntless Dismantler": DAUNTLESS_DISMANTLER,
    "Deconstruction Hammer": DECONSTRUCTION_HAMMER,
    "Dusk Rose Reliquary": DUSK_ROSE_RELIQUARY,
    "Envoy of Okinec Ahau": ENVOY_OF_OKINEC_AHAU,
    "Fabrication Foundry": FABRICATION_FOUNDRY,
    "Family Reunion": FAMILY_REUNION,
    "Get Lost": GET_LOST,
    "Glorifier of Suffering": GLORIFIER_OF_SUFFERING,
    "Guardian of the Great Door": GUARDIAN_OF_THE_GREAT_DOOR,
    "Helping Hand": HELPING_HAND,
    "Ironpaw Aspirant": IRONPAW_ASPIRANT,
    "Kinjalli's Dawnrunner": KINJALLIS_DAWNRUNNER,
    "Kutzil's Flanker": KUTZILS_FLANKER,
    "Malamet War Scribe": MALAMET_WAR_SCRIBE,
    "Market Gnome": MARKET_GNOME,
    "Might of the Ancestors": MIGHT_OF_THE_ANCESTORS,
    "Miner's Guidewing": MINERS_GUIDEWING,
    "Mischievous Pup": MISCHIEVOUS_PUP,
    "Ojer Taq, Deepest Foundation": OJER_TAQ_DEEPEST_FOUNDATION,
    "Oltec Archaeologists": OLTEC_ARCHAEOLOGISTS,
    "Oltec Cloud Guard": OLTEC_CLOUD_GUARD,
    "Oteclan Landmark": OTECLAN_LANDMARK,
    "Petrify": PETRIFY,
    "Quicksand Whirlpool": QUICKSAND_WHIRLPOOL,
    "Resplendent Angel": RESPLENDENT_ANGEL,
    "Ruin-Lurker Bat": RUINLURKER_BAT,
    "Sanguine Evangelist": SANGUINE_EVANGELIST,
    "Soaring Sandwing": SOARING_SANDWING,
    "Spring-Loaded Sawblades": SPRINGLOADED_SAWBLADES,
    "Thousand Moons Crackshot": THOUSAND_MOONS_CRACKSHOT,
    "Thousand Moons Infantry": THOUSAND_MOONS_INFANTRY,
    "Thousand Moons Smithy": THOUSAND_MOONS_SMITHY,
    "Tinker's Tote": TINKERS_TOTE,
    "Unstable Glyphbridge": UNSTABLE_GLYPHBRIDGE,
    "Vanguard of the Rose": VANGUARD_OF_THE_ROSE,
    "Warden of the Inner Sky": WARDEN_OF_THE_INNER_SKY,
    "Akal Pakal, First Among Equals": AKAL_PAKAL_FIRST_AMONG_EQUALS,
    "Ancestral Reminiscence": ANCESTRAL_REMINISCENCE,
    "Brackish Blunder": BRACKISH_BLUNDER,
    "Braided Net": BRAIDED_NET,
    "Chart a Course": CHART_A_COURSE,
    "Cogwork Wrestler": COGWORK_WRESTLER,
    "Confounding Riddle": CONFOUNDING_RIDDLE,
    "Council of Echoes": COUNCIL_OF_ECHOES,
    "Deeproot Pilgrimage": DEEPROOT_PILGRIMAGE,
    "Didact Echo": DIDACT_ECHO,
    "Eaten by Piranhas": EATEN_BY_PIRANHAS,
    "The Enigma Jewel": THE_ENIGMA_JEWEL,
    "The Everflowing Well": THE_EVERFLOWING_WELL,
    "Frilled Cave-Wurm": FRILLED_CAVEWURM,
    "Hermitic Nautilus": HERMITIC_NAUTILUS,
    "Hurl into History": HURL_INTO_HISTORY,
    "Inverted Iceberg": INVERTED_ICEBERG,
    "Kitesail Larcenist": KITESAIL_LARCENIST,
    "Lodestone Needle": LODESTONE_NEEDLE,
    "Malcolm, Alluring Scoundrel": MALCOLM_ALLURING_SCOUNDREL,
    "Marauding Brinefang": MARAUDING_BRINEFANG,
    "Merfolk Cave-Diver": MERFOLK_CAVEDIVER,
    "Oaken Siren": OAKEN_SIREN,
    "Ojer Pakpatiq, Deepest Epoch": OJER_PAKPATIQ_DEEPEST_EPOCH,
    "Orazca Puzzle-Door": ORAZCA_PUZZLEDOOR,
    "Out of Air": OUT_OF_AIR,
    "Pirate Hat": PIRATE_HAT,
    "Relic's Roar": RELICS_ROAR,
    "River Herald Scout": RIVER_HERALD_SCOUT,
    "Sage of Days": SAGE_OF_DAYS,
    "Self-Reflection": SELFREFLECTION,
    "Shipwreck Sentry": SHIPWRECK_SENTRY,
    "Sinuous Benthisaur": SINUOUS_BENTHISAUR,
    "Song of Stupefaction": SONG_OF_STUPEFACTION,
    "Spyglass Siren": SPYGLASS_SIREN,
    "Staunch Crewmate": STAUNCH_CREWMATE,
    "Subterranean Schooner": SUBTERRANEAN_SCHOONER,
    "Tishana's Tidebinder": TISHANAS_TIDEBINDER,
    "Unlucky Drop": UNLUCKY_DROP,
    "Waterlogged Hulk": WATERLOGGED_HULK,
    "Waterwind Scout": WATERWIND_SCOUT,
    "Waylaying Pirates": WAYLAYING_PIRATES,
    "Zoetic Glyph": ZOETIC_GLYPH,
    "Abyssal Gorestalker": ABYSSAL_GORESTALKER,
    "Aclazotz, Deepest Betrayal": ACLAZOTZ_DEEPEST_BETRAYAL,
    "Acolyte of Aclazotz": ACOLYTE_OF_ACLAZOTZ,
    "Another Chance": ANOTHER_CHANCE,
    "Bitter Triumph": BITTER_TRIUMPH,
    "Bloodletter of Aclazotz": BLOODLETTER_OF_ACLAZOTZ,
    "Bloodthorn Flail": BLOODTHORN_FLAIL,
    "Bringer of the Last Gift": BRINGER_OF_THE_LAST_GIFT,
    "Broodrage Mycoid": BROODRAGE_MYCOID,
    "Canonized in Blood": CANONIZED_IN_BLOOD,
    "Chupacabra Echo": CHUPACABRA_ECHO,
    "Corpses of the Lost": CORPSES_OF_THE_LOST,
    "Dead Weight": DEAD_WEIGHT,
    "Deathcap Marionette": DEATHCAP_MARIONETTE,
    "Deep Goblin Skulltaker": DEEP_GOBLIN_SKULLTAKER,
    "Deep-Cavern Bat": DEEPCAVERN_BAT,
    "Defossilize": DEFOSSILIZE,
    "Echo of Dusk": ECHO_OF_DUSK,
    "Fanatical Offering": FANATICAL_OFFERING,
    "Fungal Fortitude": FUNGAL_FORTITUDE,
    "Gargantuan Leech": GARGANTUAN_LEECH,
    "Grasping Shadows": GRASPING_SHADOWS,
    "Greedy Freebooter": GREEDY_FREEBOOTER,
    "Join the Dead": JOIN_THE_DEAD,
    "Malicious Eclipse": MALICIOUS_ECLIPSE,
    "Mephitic Draught": MEPHITIC_DRAUGHT,
    "Preacher of the Schism": PREACHER_OF_THE_SCHISM,
    "Primordial Gnawer": PRIMORDIAL_GNAWER,
    "Queen's Bay Paladin": QUEENS_BAY_PALADIN,
    "Rampaging Spiketail": RAMPAGING_SPIKETAIL,
    "Ray of Ruin": RAY_OF_RUIN,
    "Screaming Phantom": SCREAMING_PHANTOM,
    "Skullcap Snail": SKULLCAP_SNAIL,
    "Soulcoil Viper": SOULCOIL_VIPER,
    "Souls of the Lost": SOULS_OF_THE_LOST,
    "Stalactite Stalker": STALACTITE_STALKER,
    "Starving Revenant": STARVING_REVENANT,
    "Stinging Cave Crawler": STINGING_CAVE_CRAWLER,
    "Synapse Necromage": SYNAPSE_NECROMAGE,
    "Tarrian's Journal": TARRIANS_JOURNAL,
    "Terror Tide": TERROR_TIDE,
    "Tithing Blade": TITHING_BLADE,
    "Visage of Dread": VISAGE_OF_DREAD,
    "Vito's Inquisitor": VITOS_INQUISITOR,
    "Abrade": ABRADE,
    "Ancestors' Aid": ANCESTORS_AID,
    "Belligerent Yearling": BELLIGERENT_YEARLING,
    "Bonehoard Dracosaur": BONEHOARD_DRACOSAUR,
    "Brass's Tunnel-Grinder": BRASSS_TUNNELGRINDER,
    "Brazen Blademaster": BRAZEN_BLADEMASTER,
    "Breeches, Eager Pillager": BREECHES_EAGER_PILLAGER,
    "Burning Sun Cavalry": BURNING_SUN_CAVALRY,
    "Calamitous Cave-In": CALAMITOUS_CAVEIN,
    "Child of the Volcano": CHILD_OF_THE_VOLCANO,
    "Curator of Sun's Creation": CURATOR_OF_SUNS_CREATION,
    "Daring Discovery": DARING_DISCOVERY,
    "Diamond Pick-Axe": DIAMOND_PICKAXE,
    "Dinotomaton": DINOTOMATON,
    "Dire Flail": DIRE_FLAIL,
    "Dowsing Device": DOWSING_DEVICE,
    "Dreadmaw's Ire": DREADMAWS_IRE,
    "Enterprising Scallywag": ENTERPRISING_SCALLYWAG,
    "Etali's Favor": ETALIS_FAVOR,
    "Geological Appraiser": GEOLOGICAL_APPRAISER,
    "A-Geological Appraiser": AGEOLOGICAL_APPRAISER,
    "Goblin Tomb Raider": GOBLIN_TOMB_RAIDER,
    "Goldfury Strider": GOLDFURY_STRIDER,
    "Hit the Mother Lode": HIT_THE_MOTHER_LODE,
    "Hotfoot Gnome": HOTFOOT_GNOME,
    "Idol of the Deep King": IDOL_OF_THE_DEEP_KING,
    "Inti, Seneschal of the Sun": INTI_SENESCHAL_OF_THE_SUN,
    "Magmatic Galleon": MAGMATIC_GALLEON,
    "Ojer Axonil, Deepest Might": OJER_AXONIL_DEEPEST_MIGHT,
    "Panicked Altisaur": PANICKED_ALTISAUR,
    "Plundering Pirate": PLUNDERING_PIRATE,
    "Poetic Ingenuity": POETIC_INGENUITY,
    "Rampaging Ceratops": RAMPAGING_CERATOPS,
    "Rumbling Rockslide": RUMBLING_ROCKSLIDE,
    "Saheeli's Lattice": SAHEELIS_LATTICE,
    "Scytheclaw Raptor": SCYTHECLAW_RAPTOR,
    "Seismic Monstrosaur": SEISMIC_MONSTROSAUR,
    "Sunfire Torch": SUNFIRE_TORCH,
    "Sunshot Militia": SUNSHOT_MILITIA,
    "Tectonic Hazard": TECTONIC_HAZARD,
    "Triumphant Chomp": TRIUMPHANT_CHOMP,
    "Trumpeting Carnosaur": TRUMPETING_CARNOSAUR,
    "Volatile Wanderglyph": VOLATILE_WANDERGLYPH,
    "Zoyowa's Justice": ZOYOWAS_JUSTICE,
    "Armored Kincaller": ARMORED_KINCALLER,
    "Basking Capybara": BASKING_CAPYBARA,
    "Bedrock Tortoise": BEDROCK_TORTOISE,
    "Cavern Stomper": CAVERN_STOMPER,
    "Cenote Scout": CENOTE_SCOUT,
    "Coati Scavenger": COATI_SCAVENGER,
    "Colossadactyl": COLOSSADACTYL,
    "Cosmium Confluence": COSMIUM_CONFLUENCE,
    "Disturbed Slumber": DISTURBED_SLUMBER,
    "Earthshaker Dreadmaw": EARTHSHAKER_DREADMAW,
    "Explorer's Cache": EXPLORERS_CACHE,
    "Ghalta, Stampede Tyrant": GHALTA_STAMPEDE_TYRANT,
    "Glimpse the Core": GLIMPSE_THE_CORE,
    "Glowcap Lantern": GLOWCAP_LANTERN,
    "Growing Rites of Itlimoc": GROWING_RITES_OF_ITLIMOC,
    "Huatli, Poet of Unity": HUATLI_POET_OF_UNITY,
    "Huatli's Final Strike": HUATLIS_FINAL_STRIKE,
    "Hulking Raptor": HULKING_RAPTOR,
    "In the Presence of Ages": IN_THE_PRESENCE_OF_AGES,
    "Intrepid Paleontologist": INTREPID_PALEONTOLOGIST,
    "Ixalli's Lorekeeper": IXALLIS_LOREKEEPER,
    "Jade Seedstones": JADE_SEEDSTONES,
    "Jadelight Spelunker": JADELIGHT_SPELUNKER,
    "Kaslem's Stonetree": KASLEMS_STONETREE,
    "Malamet Battle Glyph": MALAMET_BATTLE_GLYPH,
    "Malamet Brawler": MALAMET_BRAWLER,
    "Malamet Scythe": MALAMET_SCYTHE,
    "Malamet Veteran": MALAMET_VETERAN,
    "Mineshaft Spider": MINESHAFT_SPIDER,
    "Nurturing Bristleback": NURTURING_BRISTLEBACK,
    "Ojer Kaslem, Deepest Growth": OJER_KASLEM_DEEPEST_GROWTH,
    "Over the Edge": OVER_THE_EDGE,
    "Pathfinding Axejaw": PATHFINDING_AXEJAW,
    "Poison Dart Frog": POISON_DART_FROG,
    "Pugnacious Hammerskull": PUGNACIOUS_HAMMERSKULL,
    "River Herald Guide": RIVER_HERALD_GUIDE,
    "Seeker of Sunlight": SEEKER_OF_SUNLIGHT,
    "Sentinel of the Nameless City": SENTINEL_OF_THE_NAMELESS_CITY,
    "The Skullspore Nexus": THE_SKULLSPORE_NEXUS,
    "Spelunking": SPELUNKING,
    "Staggering Size": STAGGERING_SIZE,
    "Tendril of the Mycotyrant": TENDRIL_OF_THE_MYCOTYRANT,
    "Thrashing Brontodon": THRASHING_BRONTODON,
    "Twists and Turns": TWISTS_AND_TURNS,
    "Walk with the Ancestors": WALK_WITH_THE_ANCESTORS,
    "Abuelo, Ancestral Echo": ABUELO_ANCESTRAL_ECHO,
    "Akawalli, the Seething Tower": AKAWALLI_THE_SEETHING_TOWER,
    "Amalia Benavides Aguirre": AMALIA_BENAVIDES_AGUIRRE,
    "The Ancient One": THE_ANCIENT_ONE,
    "Anim Pakal, Thousandth Moon": ANIM_PAKAL_THOUSANDTH_MOON,
    "Bartolomé del Presidio": BARTOLOM_DEL_PRESIDIO,
    "The Belligerent": THE_BELLIGERENT,
    "Caparocti Sunborn": CAPAROCTI_SUNBORN,
    "Captain Storm, Cosmium Raider": CAPTAIN_STORM_COSMIUM_RAIDER,
    "Deepfathom Echo": DEEPFATHOM_ECHO,
    "Gishath, Sun's Avatar": GISHATH_SUNS_AVATAR,
    "Itzquinth, Firstborn of Gishath": ITZQUINTH_FIRSTBORN_OF_GISHATH,
    "Kellan, Daring Traveler": KELLAN_DARING_TRAVELER,
    "Kutzil, Malamet Exemplar": KUTZIL_MALAMET_EXEMPLAR,
    "Master's Guide-Mural": MASTERS_GUIDEMURAL,
    "Molten Collapse": MOLTEN_COLLAPSE,
    "The Mycotyrant": THE_MYCOTYRANT,
    "Nicanzil, Current Conductor": NICANZIL_CURRENT_CONDUCTOR,
    "Palani's Hatcher": PALANIS_HATCHER,
    "Quintorius Kand": QUINTORIUS_KAND,
    "Saheeli, the Sun's Brilliance": SAHEELI_THE_SUNS_BRILLIANCE,
    "Sovereign Okinec Ahau": SOVEREIGN_OKINEC_AHAU,
    "Squirming Emergence": SQUIRMING_EMERGENCE,
    "Uchbenbak, the Great Mistake": UCHBENBAK_THE_GREAT_MISTAKE,
    "Vito, Fanatic of Aclazotz": VITO_FANATIC_OF_ACLAZOTZ,
    "Wail of the Forgotten": WAIL_OF_THE_FORGOTTEN,
    "Zoyowa Lava-Tongue": ZOYOWA_LAVATONGUE,
    "Buried Treasure": BURIED_TREASURE,
    "Careening Mine Cart": CAREENING_MINE_CART,
    "Cartographer's Companion": CARTOGRAPHERS_COMPANION,
    "Chimil, the Inner Sun": CHIMIL_THE_INNER_SUN,
    "Compass Gnome": COMPASS_GNOME,
    "Contested Game Ball": CONTESTED_GAME_BALL,
    "Digsite Conservator": DIGSITE_CONSERVATOR,
    "Disruptor Wanderglyph": DISRUPTOR_WANDERGLYPH,
    "Hoverstone Pilgrim": HOVERSTONE_PILGRIM,
    "Hunter's Blowgun": HUNTERS_BLOWGUN,
    "Matzalantli, the Great Door": MATZALANTLI_THE_GREAT_DOOR,
    "The Millennium Calendar": THE_MILLENNIUM_CALENDAR,
    "Roaming Throne": ROAMING_THRONE,
    "Runaway Boulder": RUNAWAY_BOULDER,
    "Scampering Surveyor": SCAMPERING_SURVEYOR,
    "Sorcerous Spyglass": SORCEROUS_SPYGLASS,
    "Sunbird Standard": SUNBIRD_STANDARD,
    "Swashbuckler's Whip": SWASHBUCKLERS_WHIP,
    "Tarrian's Soulcleaver": TARRIANS_SOULCLEAVER,
    "Threefold Thunderhulk": THREEFOLD_THUNDERHULK,
    "Throne of the Grim Captain": THRONE_OF_THE_GRIM_CAPTAIN,
    "Treasure Map": TREASURE_MAP,
    "Captivating Cave": CAPTIVATING_CAVE,
    "Cavern of Souls": CAVERN_OF_SOULS,
    "Cavernous Maw": CAVERNOUS_MAW,
    "Echoing Deeps": ECHOING_DEEPS,
    "Forgotten Monument": FORGOTTEN_MONUMENT,
    "Hidden Cataract": HIDDEN_CATARACT,
    "Hidden Courtyard": HIDDEN_COURTYARD,
    "Hidden Necropolis": HIDDEN_NECROPOLIS,
    "Hidden Nursery": HIDDEN_NURSERY,
    "Hidden Volcano": HIDDEN_VOLCANO,
    "Pit of Offerings": PIT_OF_OFFERINGS,
    "Promising Vein": PROMISING_VEIN,
    "Restless Anchorage": RESTLESS_ANCHORAGE,
    "Restless Prairie": RESTLESS_PRAIRIE,
    "Restless Reef": RESTLESS_REEF,
    "Restless Ridgeline": RESTLESS_RIDGELINE,
    "Restless Vents": RESTLESS_VENTS,
    "Sunken Citadel": SUNKEN_CITADEL,
    "Volatile Fault": VOLATILE_FAULT,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
}

print(f"Loaded {len(LOST_CAVERNS_IXALAN_CARDS)} Lost_Caverns_of_Ixalan cards")
