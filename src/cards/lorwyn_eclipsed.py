"""
Lorwyn Eclipsed (ECL) Card Implementations

Real card data fetched from Scryfall API.
273 cards in set.
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

CHANGELING_WAYFINDER = make_creature(
    name="Changeling Wayfinder",
    power=1, toughness=2,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Shapeshifter"},
    text="Changeling (This card is every creature type.)\nWhen this creature enters, you may search your library for a basic land card, reveal it, put it into your hand, then shuffle.",
)

ROOFTOP_PERCHER = make_creature(
    name="Rooftop Percher",
    power=3, toughness=3,
    mana_cost="{5}",
    colors=set(),
    subtypes={"Shapeshifter"},
    text="Changeling (This card is every creature type.)\nFlying\nWhen this creature enters, exile up to two target cards from graveyards. You gain 3 life.",
)

ADEPT_WATERSHAPER = make_creature(
    name="Adept Watershaper",
    power=3, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Merfolk"},
    text="Other tapped creatures you control have indestructible.",
)

AJANI_OUTLAND_CHAPERONE = make_planeswalker(
    name="Ajani, Outland Chaperone",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    loyalty=3,
    subtypes={"Ajani"},
    supertypes={"Legendary"},
    text="+1: Create a 1/1 green and white Kithkin creature token.\n−2: Ajani deals 4 damage to target tapped creature.\n−8: Look at the top X cards of your library, where X is your life total. You may put any number of nonland permanent cards with mana value 3 or less from among them onto the battlefield. Then shuffle.",
)

APPEAL_TO_EIRDU = make_instant(
    name="Appeal to Eirdu",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nOne or two target creatures each get +2/+1 until end of turn.",
)

BARK_OF_DORAN = make_artifact(
    name="Bark of Doran",
    mana_cost="{1}{W}",
    text="Equipped creature gets +0/+1.\nAs long as equipped creature's toughness is greater than its power, it assigns combat damage equal to its toughness rather than its power.\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

BRIGID_CLACHANS_HEART = make_creature(
    name="Brigid, Clachan's Heart",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Warrior"},
    supertypes={"Legendary"},
    text="Whenever this creature enters or transforms into Brigid, Clachan's Heart, create a 1/1 green and white Kithkin creature token.\nAt the beginning of your first main phase, you may pay {G}. If you do, transform Brigid.\n// Transforms into: Brigid, Doun's Mind (3/2)\n{T}: Add X {G} or X {W}, where X is the number of other creatures you control.\nAt the beginning of your first main phase, you may pay {W}. If you do, transform Brigid.",
)

BURDENED_STONEBACK = make_creature(
    name="Burdened Stoneback",
    power=4, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Giant", "Warrior"},
    text="This creature enters with two -1/-1 counters on it.\n{1}{W}, Remove a counter from this creature: Target creature gains indestructible until end of turn. Activate only as a sorcery. (Damage and effects that say \"destroy\" don't destroy it. If its toughness is 0 or less, it still dies.)",
)

CHAMPION_OF_THE_CLACHAN = make_creature(
    name="Champion of the Clachan",
    power=4, toughness=5,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Knight"},
    text="Flash\nAs an additional cost to cast this spell, behold a Kithkin and exile it. (Exile a Kithkin you control or a Kithkin card from your hand.)\nOther Kithkin you control get +1/+1.\nWhen this creature leaves the battlefield, return the exiled card to its owner's hand.",
)

CLACHAN_FESTIVAL = make_enchantment(
    name="Clachan Festival",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, create two 1/1 green and white Kithkin creature tokens.\n{4}{W}: Create a 1/1 green and white Kithkin creature token.",
    subtypes={"Kithkin"},
)

CRIB_SWAP = make_instant(
    name="Crib Swap",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Changeling (This card is every creature type.)\nExile target creature. Its controller creates a 1/1 colorless Shapeshifter creature token with changeling.",
    subtypes={"Shapeshifter"},
)

CURIOUS_COLOSSUS = make_creature(
    name="Curious Colossus",
    power=7, toughness=7,
    mana_cost="{5}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Giant", "Warrior"},
    text="When this creature enters, each creature target opponent controls loses all abilities, becomes a Coward in addition to its other types, and has base power and toughness 1/1.",
)

EIRDU_CARRIER_OF_DAWN = make_creature(
    name="Eirdu, Carrier of Dawn",
    power=5, toughness=5,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Elemental", "God"},
    supertypes={"Legendary"},
    text="Flying, lifelink\nCreature spells you cast have convoke. (Your creatures can help cast those spells. Each creature you tap while casting a creature spell pays for {1} or one mana of that creature's color.)\nAt the beginning of your first main phase, you may pay {B}. If you do, transform Eirdu.\n// Transforms into: Isilu, Carrier of Twilight (5/5)\nFlying, lifelink\nEach other nontoken creature you control has persist. (When it dies, if it had no -1/-1 counters on it, return it to the battlefield under its owner's control with a -1/-1 counter on it.)\nAt the beginning of your first main phase, you may pay {W}. If you do, transform Isilu.",
)

ENCUMBERED_REEJEREY = make_creature(
    name="Encumbered Reejerey",
    power=5, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Merfolk", "Soldier"},
    text="This creature enters with three -1/-1 counters on it.\nWhenever this creature becomes tapped while it has a -1/-1 counter on it, remove a -1/-1 counter from it.",
)

EVERSHRIKES_GIFT = make_enchantment(
    name="Evershrike's Gift",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Enchant creature\nEnchanted creature gets +1/+0 and has flying.\n{1}{W}, Blight 2: Return this card from your graveyard to your hand. Activate only as a sorcery. (To blight 2, put two -1/-1 counters on a creature you control.)",
    subtypes={"Aura"},
)

FLOCK_IMPOSTOR = make_creature(
    name="Flock Impostor",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Shapeshifter"},
    text="Changeling (This card is every creature type.)\nFlash\nFlying\nWhen this creature enters, return up to one other target creature you control to its owner's hand.",
)

GALLANT_FOWLKNIGHT = make_creature(
    name="Gallant Fowlknight",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Knight"},
    text="When this creature enters, creatures you control get +1/+0 until end of turn. Kithkin creatures you control also gain first strike until end of turn.",
)

GOLDMEADOW_NOMAD = make_creature(
    name="Goldmeadow Nomad",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Scout"},
    text="{W}, Exile this card from your graveyard: Create a 1/1 green and white Kithkin creature token. Activate only as a sorcery.",
)

KEEP_OUT = make_instant(
    name="Keep Out",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Keep Out deals 4 damage to target tapped creature.\n• Destroy target enchantment.",
)

KINBINDING = make_enchantment(
    name="Kinbinding",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +X/+X, where X is the number of creatures that entered the battlefield under your control this turn.\nAt the beginning of combat on your turn, create a 1/1 green and white Kithkin creature token.",
)

KINSBAILE_ASPIRANT = make_creature(
    name="Kinsbaile Aspirant",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Citizen", "Kithkin"},
    text="As an additional cost to cast this spell, behold a Kithkin or pay {2}. (To behold a Kithkin, choose a Kithkin you control or reveal a Kithkin card from your hand.)\nWhenever another creature you control enters, this creature gets +1/+1 until end of turn.",
)

KINSCAER_SENTRY = make_creature(
    name="Kinscaer Sentry",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Soldier"},
    text="First strike, lifelink\nWhenever this creature attacks, you may put a creature card with mana value X or less from your hand onto the battlefield tapped and attacking, where X is the number of attacking creatures you control.",
)

KITHKEEPER = make_creature(
    name="Kithkeeper",
    power=3, toughness=3,
    mana_cost="{6}{W}",
    colors={Color.WHITE},
    subtypes={"Elemental"},
    text="Vivid — When this creature enters, create X 1/1 green and white Kithkin creature tokens, where X is the number of colors among permanents you control.\nTap three untapped creatures you control: This creature gets +3/+0 and gains flying until end of turn.",
)

LIMINAL_HOLD = make_enchantment(
    name="Liminal Hold",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, exile up to one target nonland permanent an opponent controls until this enchantment leaves the battlefield. You gain 2 life.",
)

MEANDERS_GUIDE = make_creature(
    name="Meanders Guide",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Merfolk", "Scout"},
    text="Whenever this creature attacks, you may tap another untapped Merfolk you control. When you do, return target creature card with mana value 3 or less from your graveyard to the battlefield.",
)

MOONLIT_LAMENTER = make_creature(
    name="Moonlit Lamenter",
    power=2, toughness=5,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Treefolk"},
    text="This creature enters with a -1/-1 counter on it.\n{1}{W}, Remove a counter from this creature: Draw a card. Activate only as a sorcery.",
)

MORNINGTIDES_LIGHT = make_sorcery(
    name="Morningtide's Light",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Exile any number of target creatures. At the beginning of the next end step, return those cards to the battlefield tapped under their owners' control.\nUntil your next turn, prevent all damage that would be dealt to you.\nExile Morningtide's Light.",
)

PERSONIFY = make_instant(
    name="Personify",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Exile target creature you control, then return that card to the battlefield under its owner's control. Create a 1/1 colorless Shapeshifter creature token with changeling. (It's every creature type.)",
)

PROTECTIVE_RESPONSE = make_instant(
    name="Protective Response",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nDestroy target attacking or blocking creature.",
)

PYRRHIC_STRIKE = make_instant(
    name="Pyrrhic Strike",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="As an additional cost to cast this spell, you may blight 2. (You may put two -1/-1 counters on a creature you control.)\nChoose one. If this spell's additional cost was paid, choose both instead.\n• Destroy target artifact or enchantment.\n• Destroy target creature with mana value 3 or greater.",
)

RELUCTANT_DOUNGUARD = make_creature(
    name="Reluctant Dounguard",
    power=4, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Soldier"},
    text="This creature enters with two -1/-1 counters on it.\nWhenever another creature you control enters while this creature has a -1/-1 counter on it, remove a -1/-1 counter from this creature.",
)

RHYS_THE_EVERMORE = make_creature(
    name="Rhys, the Evermore",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Elf", "Warrior"},
    supertypes={"Legendary"},
    text="Flash\nWhen Rhys enters, another target creature you control gains persist until end of turn. (When it dies, if it had no -1/-1 counters on it, return it to the battlefield under its owner's control with a -1/-1 counter on it.)\n{W}, {T}: Remove any number of counters from target creature you control. Activate only as a sorcery.",
)

RIVERGUARDS_REFLEXES = make_instant(
    name="Riverguard's Reflexes",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 and gains first strike until end of turn. Untap it.",
)

SHORE_LURKER = make_creature(
    name="Shore Lurker",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Merfolk", "Scout"},
    text="Flying\nWhen this creature enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

SLUMBERING_WALKER = make_creature(
    name="Slumbering Walker",
    power=4, toughness=7,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Giant", "Warrior"},
    text="This creature enters with two -1/-1 counters on it.\nAt the beginning of your end step, you may remove a counter from this creature. When you do, return target creature card with power 2 or less from your graveyard to the battlefield.",
)

SPIRAL_INTO_SOLITUDE = make_enchantment(
    name="Spiral into Solitude",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Enchant creature\nEnchanted creature can't attack or block.\n{1}{W}, Blight 1, Sacrifice this Aura: Exile enchanted creature. (To blight 1, put a -1/-1 counter on a creature you control.)",
    subtypes={"Aura"},
)

SUNDAPPLED_CELEBRANT = make_creature(
    name="Sun-Dappled Celebrant",
    power=5, toughness=6,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Treefolk"},
    text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nVigilance",
)

THOUGHTWEFT_IMBUER = make_creature(
    name="Thoughtweft Imbuer",
    power=0, toughness=5,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Advisor", "Kithkin"},
    text="Whenever a creature you control attacks alone, it gets +X/+X until end of turn, where X is the number of Kithkin you control.",
)

TIMID_SHIELDBEARER = make_creature(
    name="Timid Shieldbearer",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Kithkin", "Soldier"},
    text="{4}{W}: Creatures you control get +1/+1 until end of turn.",
)

TRIBUTARY_VAULTER = make_creature(
    name="Tributary Vaulter",
    power=1, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Merfolk", "Warrior"},
    text="Flying\nWhenever this creature becomes tapped, another target Merfolk you control gets +2/+0 until end of turn.",
)

WANDERBRINE_PREACHER = make_creature(
    name="Wanderbrine Preacher",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Merfolk"},
    text="Whenever this creature becomes tapped, you gain 2 life.",
)

WANDERBRINE_TRAPPER = make_creature(
    name="Wanderbrine Trapper",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Merfolk", "Scout"},
    text="{1}, {T}, Tap another untapped creature you control: Tap target creature an opponent controls.",
)

WINNOWING = make_sorcery(
    name="Winnowing",
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nFor each player, you choose a creature that player controls. Then each player sacrifices all other creatures they control that don't share a creature type with the chosen creature they control.",
)

AQUITECTS_DEFENSES = make_enchantment(
    name="Aquitect's Defenses",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Flash\nEnchant creature you control\nWhen this Aura enters, enchanted creature gains hexproof until end of turn. (It can't be the target of spells or abilities your opponents control.)\nEnchanted creature gets +1/+2.",
    subtypes={"Aura"},
)

BLOSSOMBIND = make_enchantment(
    name="Blossombind",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Enchant creature\nWhen this Aura enters, tap enchanted creature.\nEnchanted creature can't become untapped and can't have counters put on it.",
    subtypes={"Aura"},
)

CHAMPIONS_OF_THE_SHOAL = make_creature(
    name="Champions of the Shoal",
    power=4, toughness=6,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Soldier"},
    text="As an additional cost to cast this spell, behold a Merfolk and exile it. (Exile a Merfolk you control or a Merfolk card from your hand.)\nWhenever this creature enters or becomes tapped, tap up to one target creature and put a stun counter on it.\nWhen this creature leaves the battlefield, return the exiled card to its owner's hand.",
)

DISRUPTOR_OF_CURRENTS = make_creature(
    name="Disruptor of Currents",
    power=3, toughness=3,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="Flash\nConvoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nWhen this creature enters, return up to one other target nonland permanent to its owner's hand.",
)

FLITTERWING_NUISANCE = make_creature(
    name="Flitterwing Nuisance",
    power=2, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Rogue"},
    text="Flying\nThis creature enters with a -1/-1 counter on it.\n{2}{U}, Remove a counter from this creature: Whenever a creature you control deals combat damage to a player or planeswalker this turn, draw a card.",
)

GLAMER_GIFTER = make_creature(
    name="Glamer Gifter",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flash\nFlying\nWhen this creature enters, choose up to one other target creature. Until end of turn, that creature has base power and toughness 4/4 and gains all creature types.",
)

GLAMERMITE = make_creature(
    name="Glamermite",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Rogue"},
    text="Flash\nFlying\nWhen this creature enters, choose one —\n• Tap target creature.\n• Untap target creature.",
)

GLEN_ELENDRA_GUARDIAN = make_creature(
    name="Glen Elendra Guardian",
    power=3, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flash\nFlying\nThis creature enters with a -1/-1 counter on it.\n{1}{U}, Remove a counter from this creature: Counter target noncreature spell. Its controller draws a card.",
)

GLEN_ELENDRAS_ANSWER = make_instant(
    name="Glen Elendra's Answer",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="This spell can't be countered.\nCounter all spells your opponents control and all abilities your opponents control. Create a 1/1 blue and black Faerie creature token with flying for each spell and ability countered this way.",
)

GRAVELGILL_SCOUNDREL = make_creature(
    name="Gravelgill Scoundrel",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Rogue"},
    text="Vigilance\nWhenever this creature attacks, you may tap another untapped creature you control. If you do, this creature can't be blocked this turn.",
)

HARMONIZED_CRESCENDO = make_instant(
    name="Harmonized Crescendo",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nChoose a creature type. Draw a card for each permanent you control of that type.",
)

ILLUSION_SPINNERS = make_creature(
    name="Illusion Spinners",
    power=4, toughness=3,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="You may cast this spell as though it had flash if you control a Faerie.\nFlying\nThis creature has hexproof as long as it's untapped. (It can't be the target of spells or abilities your opponents control.)",
)

KULRATH_MYSTIC = make_creature(
    name="Kulrath Mystic",
    power=2, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Wizard"},
    text="Whenever you cast a spell with mana value 4 or greater, this creature gets +2/+0 and gains vigilance until end of turn.",
)

LOCH_MARE = make_creature(
    name="Loch Mare",
    power=4, toughness=5,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Horse", "Serpent"},
    text="This creature enters with three -1/-1 counters on it.\n{1}{U}, Remove a counter from this creature: Draw a card.\n{2}{U}, Remove two counters from this creature: Tap target creature. Put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

LOFTY_DREAMS = make_enchantment(
    name="Lofty Dreams",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nEnchant creature\nWhen this Aura enters, draw a card.\nEnchanted creature gets +2/+2 and has flying.",
    subtypes={"Aura"},
)

MIRRORFORM = make_instant(
    name="Mirrorform",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Each nonland permanent you control becomes a copy of target non-Aura permanent.",
)

NOGGLE_THE_MIND = make_enchantment(
    name="Noggle the Mind",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Flash\nEnchant creature\nEnchanted creature loses all abilities and is a colorless Noggle with base power and toughness 1/1. (It loses all colors and all other creature types.)",
    subtypes={"Aura"},
)

OKO_LORWYN_LIEGE = make_planeswalker(
    name="Oko, Lorwyn Liege",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    loyalty=3,
    subtypes={"Oko"},
    supertypes={"Legendary"},
    text="At the beginning of your first main phase, you may pay {G}. If you do, transform Oko.\n+2: Up to one target creature gains all creature types. (This effect doesn't end.)\n+1: Target creature gets -2/-0 until your next turn.\n// Transforms into: Oko, Shadowmoor Scion\nAt the beginning of your first main phase, you may pay {U}. If you do, transform Oko.\n−1: Mill three cards. You may put a permanent card from among them into your hand.\n−3: Create two 3/3 green Elk creature tokens.\n−6: Choose a creature type. You get an emblem with \"Creatures you control of the chosen type get +3/+3 and have vigilance and hexproof.\"",
)

OMNICHANGELING = make_creature(
    name="Omni-Changeling",
    power=0, toughness=0,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Shapeshifter"},
    text="Changeling (This card is every creature type.)\nConvoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nYou may have this creature enter as a copy of any creature on the battlefield, except it has changeling.",
)

PESTERED_WELLGUARD = make_creature(
    name="Pestered Wellguard",
    power=3, toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Soldier"},
    text="Whenever this creature becomes tapped, create a 1/1 blue and black Faerie creature token with flying.",
)

RIME_CHILL = make_instant(
    name="Rime Chill",
    mana_cost="{6}{U}",
    colors={Color.BLUE},
    text="Vivid — This spell costs {1} less to cast for each color among permanents you control.\nTap up to two target creatures. Put a stun counter on each of them. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nDraw a card.",
)

RIMEFIRE_TORQUE = make_artifact(
    name="Rimefire Torque",
    mana_cost="{1}{U}",
    text="As this artifact enters, choose a creature type.\nWhenever a permanent you control of the chosen type enters, put a charge counter on this artifact.\n{T}, Remove three charge counters from this artifact: When you next cast an instant or sorcery spell this turn, copy it. You may choose new targets for the copy.",
)

RIMEKIN_RECLUSE = make_creature(
    name="Rimekin Recluse",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Wizard"},
    text="When this creature enters, return up to one other target creature to its owner's hand.",
)

RUN_AWAY_TOGETHER = make_instant(
    name="Run Away Together",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Choose two target creatures controlled by different players. Return those creatures to their owners' hands.",
)

SHINESTRIKER = make_creature(
    name="Shinestriker",
    power=3, toughness=3,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="Flying\nVivid — When this creature enters, draw cards equal to the number of colors among permanents you control.",
)

SILVERGILL_MENTOR = make_creature(
    name="Silvergill Mentor",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="As an additional cost to cast this spell, behold a Merfolk or pay {2}. (To behold a Merfolk, choose a Merfolk you control or reveal a Merfolk from your hand.)\nWhen this creature enters, create a 1/1 white and blue Merfolk creature token.",
)

SILVERGILL_PEDDLER = make_creature(
    name="Silvergill Peddler",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Citizen", "Merfolk"},
    text="Whenever this creature becomes tapped, draw a card, then discard a card.",
)

SPELL_SNARE = make_instant(
    name="Spell Snare",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Counter target spell with mana value 2.",
)

STRATOSOARER = make_creature(
    name="Stratosoarer",
    power=3, toughness=5,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="Flying\nWhen this creature enters, target creature gains flying until end of turn.\nBasic landcycling {1}{U} ({1}{U}, Discard this card: Search your library for a basic land card, reveal it, put it into your hand, then shuffle.)",
)

SUMMIT_SENTINEL = make_creature(
    name="Summit Sentinel",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Soldier"},
    text="When this creature dies, draw a card.",
)

SUNDERFLOCK = make_creature(
    name="Sunderflock",
    power=5, toughness=5,
    mana_cost="{7}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="This spell costs {X} less to cast, where X is the greatest mana value among Elementals you control.\nFlying\nWhen this creature enters, if you cast it, return all non-Elemental creatures to their owners' hands.",
)

SWAT_AWAY = make_instant(
    name="Swat Away",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="This spell costs {2} less to cast if a creature is attacking you.\nThe owner of target spell or creature puts it on their choice of the top or bottom of their library.",
)

SYGG_WANDERWINE_WISDOM = make_creature(
    name="Sygg, Wanderwine Wisdom",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    supertypes={"Legendary"},
    text="Sygg can't be blocked.\nWhenever this creature enters or transforms into Sygg, Wanderwine Wisdom, target creature gains \"Whenever this creature deals combat damage to a player or planeswalker, draw a card\" until end of turn.\nAt the beginning of your first main phase, you may pay {W}. If you do, transform Sygg.\n// Transforms into: Sygg, Wanderbrine Shield (2/2)\nSygg can't be blocked.\nWhenever this creature transforms into Sygg, Wanderbrine Shield, target creature you control gains protection from each color until your next turn.\nAt the beginning of your first main phase, you may pay {U}. If you do, transform Sygg.",
)

TANUFEL_RIMESPEAKER = make_creature(
    name="Tanufel Rimespeaker",
    power=2, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Wizard"},
    text="Whenever you cast a spell with mana value 4 or greater, draw a card.",
)

TEMPORAL_CLEANSING = make_sorcery(
    name="Temporal Cleansing",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nThe owner of target nonland permanent puts it into their library second from the top or on the bottom.",
)

THIRST_FOR_IDENTITY = make_instant(
    name="Thirst for Identity",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw three cards. Then discard two cards unless you discard a creature card.",
)

UNEXPECTED_ASSISTANCE = make_instant(
    name="Unexpected Assistance",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nDraw three cards, then discard a card.",
)

UNWELCOME_SPRITE = make_creature(
    name="Unwelcome Sprite",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Rogue"},
    text="Flying\nWhenever you cast a spell during an opponent's turn, surveil 2. (Look at the top two cards of your library. You may put any number of them into your graveyard and the rest on top of your library in any order.)",
)

WANDERWINE_DISTRACTER = make_creature(
    name="Wanderwine Distracter",
    power=4, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="Whenever this creature becomes tapped, target creature an opponent controls gets -3/-0 until end of turn.",
)

WANDERWINE_FAREWELL = make_sorcery(
    name="Wanderwine Farewell",
    mana_cost="{5}{U}{U}",
    colors={Color.BLUE},
    text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nReturn one or two target nonland permanents to their owners' hands. Then if you control a Merfolk, create a 1/1 white and blue Merfolk creature token for each permanent returned to its owner's hand this way.",
    subtypes={"Merfolk"},
)

WILD_UNRAVELING = make_instant(
    name="Wild Unraveling",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="As an additional cost to cast this spell, blight 2 or pay {1}. (To blight 2, put two -1/-1 counters on a creature you control.)\nCounter target spell.",
)

AUNTIES_SENTENCE = make_sorcery(
    name="Auntie's Sentence",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Choose one —\n• Target opponent reveals their hand. You choose a nonland permanent card from it. That player discards that card.\n• Target creature gets -2/-2 until end of turn.",
)

BARBED_BLOODLETTER = make_artifact(
    name="Barbed Bloodletter",
    mana_cost="{1}{B}",
    text="Flash\nWhen this Equipment enters, attach it to target creature you control. That creature gains wither until end of turn. (It deals damage to creatures in the form of -1/-1 counters.)\nEquipped creature gets +1/+2.\nEquip {2}",
    subtypes={"Equipment"},
)

BILEVIAL_BOGGART = make_creature(
    name="Bile-Vial Boggart",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Goblin"},
    text="When this creature dies, put a -1/-1 counter on up to one target creature.",
)

BITTERBLOOM_BEARER = make_creature(
    name="Bitterbloom Bearer",
    power=1, toughness=1,
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Rogue"},
    text="Flash\nFlying\nAt the beginning of your upkeep, you lose 1 life and create a 1/1 blue and black Faerie creature token with flying.",
)

BLIGHT_ROT = make_instant(
    name="Blight Rot",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Put four -1/-1 counters on target creature.",
)

BLIGHTED_BLACKTHORN = make_creature(
    name="Blighted Blackthorn",
    power=3, toughness=7,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Treefolk", "Warlock"},
    text="Whenever this creature enters or attacks, you may blight 2. If you do, you draw a card and lose 1 life. (To blight 2, put two -1/-1 counters on a creature you control.)",
)

BLOODLINE_BIDDING = make_sorcery(
    name="Bloodline Bidding",
    mana_cost="{6}{B}{B}",
    colors={Color.BLACK},
    text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nChoose a creature type. Return all creature cards of the chosen type from your graveyard to the battlefield.",
)

BOGGART_MISCHIEF = make_enchantment(
    name="Boggart Mischief",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="When this enchantment enters, you may blight 1. If you do, create two 1/1 black and red Goblin creature tokens. (To blight 1, put a -1/-1 counter on a creature you control.)\nWhenever a Goblin creature you control dies, each opponent loses 1 life and you gain 1 life.",
    subtypes={"Goblin"},
)

BOGGART_PRANKSTER = make_creature(
    name="Boggart Prankster",
    power=1, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Warrior"},
    text="Whenever you attack, target attacking Goblin you control gets +1/+0 until end of turn.",
)

BOGSLITHERS_EMBRACE = make_sorcery(
    name="Bogslither's Embrace",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, blight 1 or pay {3}. (To blight 1, put a -1/-1 counter on a creature you control.)\nExile target creature.",
)

CHAMPION_OF_THE_WEIRD = make_creature(
    name="Champion of the Weird",
    power=5, toughness=5,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Berserker", "Goblin"},
    text="As an additional cost to cast this spell, behold a Goblin and exile it. (Exile a Goblin you control or a Goblin card from your hand.)\nPay 1 life, Blight 2: Target opponent blights 2. Activate only as a sorcery.\nWhen this creature leaves the battlefield, return the exiled card to its owner's hand.",
)

CREAKWOOD_SAFEWRIGHT = make_creature(
    name="Creakwood Safewright",
    power=5, toughness=5,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Elf", "Warrior"},
    text="This creature enters with three -1/-1 counters on it.\nAt the beginning of your end step, if there is an Elf card in your graveyard and this creature has a -1/-1 counter on it, remove a -1/-1 counter from this creature.",
)

DARKNESS_DESCENDS = make_sorcery(
    name="Darkness Descends",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Put two -1/-1 counters on each creature.",
)

DAWNHAND_DISSIDENT = make_creature(
    name="Dawnhand Dissident",
    power=1, toughness=2,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Elf", "Warlock"},
    text="{T}, Blight 1: Surveil 1.\n{T}, Blight 2: Exile target card from a graveyard.\nDuring your turn, you may cast creature spells from among cards you own exiled with this creature by removing three counters from among creatures you control in addition to paying their other costs.",
)

DAWNHAND_EULOGIST = make_creature(
    name="Dawnhand Eulogist",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Elf", "Warlock"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhen this creature enters, mill three cards. Then if there is an Elf card in your graveyard, each opponent loses 2 life and you gain 2 life. (To mill three cards, put the top three cards of your library into your graveyard.)",
)

DOSE_OF_DAWNGLOW = make_instant(
    name="Dose of Dawnglow",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield. Then if it isn't your main phase, blight 2. (Put two -1/-1 counters on a creature you control.)",
)

DREAM_SEIZER = make_creature(
    name="Dream Seizer",
    power=3, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Rogue"},
    text="Flying\nWhen this creature enters, you may blight 1. If you do, each opponent discards a card. (To blight 1, put a -1/-1 counter on a creature you control.)",
)

GLOOM_RIPPER = make_creature(
    name="Gloom Ripper",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Elf"},
    text="When this creature enters, target creature you control gets +X/+0 until end of turn and up to one target creature an opponent controls gets -0/-X until end of turn, where X is the number of Elves you control plus the number of Elf cards in your graveyard.",
)

GNARLBARK_ELM = make_creature(
    name="Gnarlbark Elm",
    power=3, toughness=4,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Treefolk", "Warlock"},
    text="This creature enters with two -1/-1 counters on it.\n{2}{B}, Remove two counters from this creature: Target creature gets -2/-2 until end of turn. Activate only as a sorcery.",
)

GRAVESHIFTER = make_creature(
    name="Graveshifter",
    power=2, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Shapeshifter"},
    text="Changeling (This card is every creature type.)\nWhen this creature enters, you may return target creature card from your graveyard to your hand.",
)

GRUB_STORIED_MATRIARCH = make_creature(
    name="Grub, Storied Matriarch",
    power=2, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Warlock"},
    supertypes={"Legendary"},
    text="Menace\nWhenever this creature enters or transforms into Grub, Storied Matriarch, return up to one target Goblin card from your graveyard to your hand.\nAt the beginning of your first main phase, you may pay {R}. If you do, transform Grub.\n// Transforms into: Grub, Notorious Auntie (2/1)\nMenace\nWhenever Grub attacks, you may blight 1. If you do, create a tapped and attacking token that's a copy of the blighted creature, except it has \"At the beginning of the end step, sacrifice this token.\"\nAt the beginning of your first main phase, you may pay {B}. If you do, transform Grub.",
)

GUTSPLITTER_GANG = make_creature(
    name="Gutsplitter Gang",
    power=6, toughness=6,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Berserker", "Goblin"},
    text="At the beginning of your first main phase, you may blight 2. If you don't, you lose 3 life. (To blight 2, put two -1/-1 counters on a creature you control.)",
)

HEIRLOOM_AUNTIE = make_creature(
    name="Heirloom Auntie",
    power=4, toughness=4,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Warlock"},
    text="This creature enters with two -1/-1 counters on it.\nWhenever another creature you control dies, surveil 1, then remove a -1/-1 counter from this creature. (To surveil 1, look at the top card of your library. You may put it into your graveyard.)",
)

IRONSHIELD_ELF = make_creature(
    name="Iron-Shield Elf",
    power=3, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Elf", "Warrior"},
    text="Discard a card: This creature gains indestructible until end of turn. Tap it. (Damage and effects that say \"destroy\" don't destroy it. If its toughness is 0 or less, it still dies.)",
)

MOONGLOVE_EXTRACTOR = make_creature(
    name="Moonglove Extractor",
    power=2, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Elf", "Warlock"},
    text="Whenever this creature attacks, you draw a card and lose 1 life.",
)

MOONSHADOW = make_creature(
    name="Moonshadow",
    power=7, toughness=7,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Elemental"},
    text="Menace\nThis creature enters with six -1/-1 counters on it.\nWhenever one or more permanent cards are put into your graveyard from anywhere while this creature has a -1/-1 counter on it, remove a -1/-1 counter from this creature.",
)

MORNSONG_ARIA = make_enchantment(
    name="Mornsong Aria",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Players can't draw cards or gain life.\nAt the beginning of each player's draw step, that player loses 3 life, searches their library for a card, puts it into their hand, then shuffles.",
    supertypes={"Legendary"},
)

MUDBUTTON_CURSETOSSER = make_creature(
    name="Mudbutton Cursetosser",
    power=2, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Warlock"},
    text="As an additional cost to cast this spell, behold a Goblin or pay {2}. (To behold a Goblin, choose a Goblin you control or reveal a Goblin card from your hand.)\nThis creature can't block.\nWhen this creature dies, destroy target creature an opponent controls with power 2 or less.",
)

NAMELESS_INVERSION = make_instant(
    name="Nameless Inversion",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Changeling (This card is every creature type.)\nTarget creature gets +3/-3 and loses all creature types until end of turn.",
    subtypes={"Shapeshifter"},
)

NIGHTMARE_SOWER = make_creature(
    name="Nightmare Sower",
    power=2, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Faerie"},
    text="Flying, lifelink\nWhenever you cast a spell during an opponent's turn, put a -1/-1 counter on up to one target creature.",
)

PERFECT_INTIMIDATION = make_sorcery(
    name="Perfect Intimidation",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Choose one or both —\n• Target opponent exiles two cards from their hand.\n• Remove all counters from target creature.",
)

REQUITING_HEX = make_instant(
    name="Requiting Hex",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, you may blight 1. (You may put a -1/-1 counter on a creature you control.)\nDestroy target creature with mana value 2 or less. If this spell's additional cost was paid, you gain 2 life.",
)

RETCHED_WRETCH = make_creature(
    name="Retched Wretch",
    power=4, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin"},
    text="When this creature dies, if it had a -1/-1 counter on it, return it to the battlefield under its owner's control and it loses all abilities.",
)

SCARBLADE_SCOUT = make_creature(
    name="Scarblade Scout",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Elf", "Scout"},
    text="Lifelink\nWhen this creature enters, mill two cards. (Put the top two cards of your library into your graveyard.)",
)

SCARBLADES_MALICE = make_instant(
    name="Scarblade's Malice",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature you control gains deathtouch and lifelink until end of turn. When that creature dies this turn, create a 2/2 black and green Elf creature token.",
)

SHIMMERCREEP = make_creature(
    name="Shimmercreep",
    power=3, toughness=5,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Elemental"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nVivid — When this creature enters, each opponent loses X life and you gain X life, where X is the number of colors among permanents you control.",
)

TASTER_OF_WARES = make_creature(
    name="Taster of Wares",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Warlock"},
    text="When this creature enters, target opponent reveals X cards from their hand, where X is the number of Goblins you control. You choose one of those cards. That player exiles it. If an instant or sorcery card is exiled this way, you may cast it for as long as you control this creature, and mana of any type can be spent to cast that spell.",
)

TWILIGHT_DIVINER = make_creature(
    name="Twilight Diviner",
    power=3, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Elf"},
    text="When this creature enters, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\nWhenever one or more other creatures you control enter, if they entered or were cast from a graveyard, create a token that's a copy of one of them. This ability triggers only once each turn.",
)

UNBURY = make_instant(
    name="Unbury",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Choose one —\n• Return target creature card from your graveyard to your hand.\n• Return two target creature cards that share a creature type from your graveyard to your hand.",
)

ASHLING_REKINDLED = make_creature(
    name="Ashling, Rekindled",
    power=1, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Sorcerer"},
    supertypes={"Legendary"},
    text="Whenever this creature enters or transforms into Ashling, Rekindled, you may discard a card. If you do, draw a card.\nAt the beginning of your first main phase, you may pay {U}. If you do, transform Ashling.\n// Transforms into: Ashling, Rimebound (1/3)\nWhenever this creature transforms into Ashling, Rimebound and at the beginning of your first main phase, add two mana of any one color. Spend this mana only to cast spells with mana value 4 or greater.\nAt the beginning of your first main phase, you may pay {R}. If you do, transform Ashling.",
)

BOLDWYR_AGGRESSOR = make_creature(
    name="Boldwyr Aggressor",
    power=2, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Giant", "Warrior"},
    text="Double strike\nOther Giants you control have double strike.",
)

BONECLUB_BERSERKER = make_creature(
    name="Boneclub Berserker",
    power=2, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Berserker", "Goblin"},
    text="This creature gets +2/+0 for each other Goblin you control.",
)

BOULDER_DASH = make_sorcery(
    name="Boulder Dash",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Boulder Dash deals 2 damage to any target and 1 damage to any other target.",
)

BRAMBLEBACK_BRUTE = make_creature(
    name="Brambleback Brute",
    power=4, toughness=5,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Giant", "Warrior"},
    text="This creature enters with two -1/-1 counters on it.\n{1}{R}, Remove a counter from this creature: Target creature can't block this turn. Activate only as a sorcery.",
)

BURNING_CURIOSITY = make_sorcery(
    name="Burning Curiosity",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="As an additional cost to cast this spell, you may blight 1. (You may put a -1/-1 counter on a creature you control.)\nExile the top two cards of your library. If this spell's additional cost was paid, exile the top three cards instead. Until the end of your next turn, you may play those cards.",
)

CHAMPION_OF_THE_PATH = make_creature(
    name="Champion of the Path",
    power=7, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Sorcerer"},
    text="As an additional cost to cast this spell, behold an Elemental and exile it. (Exile an Elemental you control or an Elemental card from your hand.)\nWhenever another Elemental you control enters, it deals damage equal to its power to each opponent.\nWhen this creature leaves the battlefield, return the exiled card to its owner's hand.",
)

CINDER_STRIKE = make_sorcery(
    name="Cinder Strike",
    mana_cost="{R}",
    colors={Color.RED},
    text="As an additional cost to cast this spell, you may blight 1. (You may put a -1/-1 counter on a creature you control.)\nCinder Strike deals 2 damage to target creature. It deals 4 damage to that creature instead if this spell's additional cost was paid.",
)

COLLECTIVE_INFERNO = make_enchantment(
    name="Collective Inferno",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nAs this enchantment enters, choose a creature type.\nDouble all damage that sources you control of the chosen type would deal.",
)

ELDER_AUNTIE = make_creature(
    name="Elder Auntie",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warlock"},
    text="When this creature enters, create a 1/1 black and red Goblin creature token.",
)

ENDBLAZE_EPIPHANY = make_instant(
    name="End-Blaze Epiphany",
    mana_cost="{X}{R}",
    colors={Color.RED},
    text="End-Blaze Epiphany deals X damage to target creature. When that creature dies this turn, exile a number of cards from the top of your library equal to its power, then choose a card exiled this way. Until the end of your next turn, you may play that card.",
)

ENRAGED_FLAMECASTER = make_creature(
    name="Enraged Flamecaster",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Sorcerer"},
    text="Reach\nWhenever you cast a spell with mana value 4 or greater, this creature deals 2 damage to each opponent.",
)

EXPLOSIVE_PRODIGY = make_creature(
    name="Explosive Prodigy",
    power=1, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Sorcerer"},
    text="Vivid — When this creature enters, it deals X damage to target creature an opponent controls, where X is the number of colors among permanents you control.",
)

FEED_THE_FLAMES = make_instant(
    name="Feed the Flames",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Feed the Flames deals 5 damage to target creature. If that creature would die this turn, exile it instead.",
)

FLAMECHAIN_MAULER = make_creature(
    name="Flame-Chain Mauler",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Warrior"},
    text="{1}{R}: This creature gets +1/+0 and gains menace until end of turn. (It can't be blocked except by two or more creatures.)",
)

FLAMEBRAIDER = make_creature(
    name="Flamebraider",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Bard", "Elemental"},
    text="{T}: Add two mana in any combination of colors. Spend this mana only to cast Elemental spells or activate abilities of Elemental sources.",
)

FLAMEKIN_GILDWEAVER = make_creature(
    name="Flamekin Gildweaver",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Sorcerer"},
    text="Trample\nWhen this creature enters, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

GIANTFALL = make_instant(
    name="Giantfall",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Choose one —\n• Target creature you control deals damage equal to its power to target creature an opponent controls.\n• Destroy target artifact.",
)

GOATNAP = make_sorcery(
    name="Goatnap",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. If that creature is a Goat, it also gets +3/+0 until end of turn.",
)

GOLIATH_DAYDREAMER = make_creature(
    name="Goliath Daydreamer",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Giant", "Wizard"},
    text="Whenever you cast an instant or sorcery spell from your hand, exile that card with a dream counter on it instead of putting it into your graveyard as it resolves.\nWhenever this creature attacks, you may cast a spell from among cards you own in exile with dream counters on them without paying its mana cost.",
)

GRISTLE_GLUTTON = make_creature(
    name="Gristle Glutton",
    power=1, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Scout"},
    text="{T}, Blight 1: Discard a card. If you do, draw a card. (To blight 1, put a -1/-1 counter on a creature you control.)",
)

HEXING_SQUELCHER = make_creature(
    name="Hexing Squelcher",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Sorcerer"},
    text="This spell can't be countered.\nWard—Pay 2 life.\nSpells you control can't be countered.\nOther creatures you control have \"Ward—Pay 2 life.\"",
)

IMPOLITE_ENTRANCE = make_sorcery(
    name="Impolite Entrance",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gains trample and haste until end of turn.\nDraw a card.",
)

KINDLE_THE_INNER_FLAME = make_sorcery(
    name="Kindle the Inner Flame",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Create a token that's a copy of target creature you control, except it has haste and \"At the beginning of the end step, sacrifice this token.\"\nFlashback—{1}{R}, Behold three Elementals. (You may cast this card from your graveyard for its flashback cost. Then exile it. To behold an Elemental, choose an Elemental you control or reveal an Elemental card from your hand.)",
    subtypes={"Elemental"},
)

KULRATH_ZEALOT = make_creature(
    name="Kulrath Zealot",
    power=6, toughness=5,
    mana_cost="{5}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Warrior"},
    text="When this creature enters, exile the top card of your library. Until the end of your next turn, you may play that card.\nBasic landcycling {1}{R} ({1}{R}, Discard this card: Search your library for a basic land card, reveal it, put it into your hand, then shuffle.)",
)

LASTING_TARFIRE = make_enchantment(
    name="Lasting Tarfire",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="At the beginning of each end step, if you put a counter on a creature this turn, this enchantment deals 2 damage to each opponent.",
)

LAVALEAPER = make_creature(
    name="Lavaleaper",
    power=4, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="All creatures have haste.\nWhenever a player taps a basic land for mana, that player adds one mana of any type that land produced.",
)

MEEK_ATTACK = make_enchantment(
    name="Meek Attack",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="{1}{R}: You may put a creature card with total power and toughness 5 or less from your hand onto the battlefield. That creature gains haste. At the beginning of the next end step, sacrifice that creature.",
)

RECKLESS_RANSACKING = make_instant(
    name="Reckless Ransacking",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+2 until end of turn. Create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

SCUZZBACK_SCROUNGER = make_creature(
    name="Scuzzback Scrounger",
    power=3, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="At the beginning of your first main phase, you may blight 1. If you do, create a Treasure token. (To blight 1, put a -1/-1 counter on a creature you control. A Treasure token is an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

SEAR = make_instant(
    name="Sear",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Sear deals 4 damage to target creature or planeswalker.",
)

SIZZLING_CHANGELING = make_creature(
    name="Sizzling Changeling",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Shapeshifter"},
    text="Changeling (This card is every creature type.)\nWhen this creature dies, exile the top card of your library. Until the end of your next turn, you may play that card.",
)

SOUL_IMMOLATION = make_sorcery(
    name="Soul Immolation",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="As an additional cost to cast this spell, blight X. X can't be greater than the greatest toughness among creatures you control. (Put X -1/-1 counters on a creature you control.)\nSoul Immolation deals X damage to each opponent and each creature they control.",
)

SOULBRIGHT_SEEKER = make_creature(
    name="Soulbright Seeker",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Sorcerer"},
    text="As an additional cost to cast this spell, behold an Elemental or pay {2}. (To behold an Elemental, choose an Elemental you control or reveal an Elemental card from your hand.)\n{R}: Target creature you control gains trample until end of turn. If this is the third time this ability has resolved this turn, add {R}{R}{R}{R}.",
)

SOURBREAD_AUNTIE = make_creature(
    name="Sourbread Auntie",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="When this creature enters, you may blight 2. If you do, create two 1/1 black and red Goblin creature tokens. (To blight 2, put two -1/-1 counters on a creature you control.)",
)

SPINEROCK_TYRANT = make_creature(
    name="Spinerock Tyrant",
    power=6, toughness=6,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\nWither (This deals damage to creatures in the form of -1/-1 counters.)\nWhenever you cast an instant or sorcery spell with a single target, you may copy it. If you do, those spells gain wither. You may choose new targets for the copy.",
)

SQUAWKROASTER = make_creature(
    name="Squawkroaster",
    power=0, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Double strike\nVivid — Squawkroaster's power is equal to the number of colors among permanents you control.",
)

STINGSLINGER = make_creature(
    name="Sting-Slinger",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="{1}{R}, {T}, Blight 1: This creature deals 2 damage to each opponent. (To blight 1, put a -1/-1 counter on a creature you control.)",
)

TWEEZE = make_instant(
    name="Tweeze",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Tweeze deals 3 damage to any target. You may discard a card. If you do, draw a card.",
)

WARREN_TORCHMASTER = make_creature(
    name="Warren Torchmaster",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="At the beginning of combat on your turn, you may blight 1. When you do, target creature gains haste until end of turn. (To blight 1, put a -1/-1 counter on a creature you control.)",
)

ASSERT_PERFECTION = make_sorcery(
    name="Assert Perfection",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +1/+0 until end of turn. It deals damage equal to its power to up to one target creature an opponent controls.",
)

AURORA_AWAKENER = make_creature(
    name="Aurora Awakener",
    power=7, toughness=7,
    mana_cost="{6}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Giant"},
    text="Trample\nVivid — When this creature enters, reveal cards from the top of your library until you reveal X permanent cards, where X is the number of colors among permanents you control. Put any number of those permanent cards onto the battlefield, then put the rest of the revealed cards on the bottom of your library in a random order.",
)

BLOOM_TENDER = make_creature(
    name="Bloom Tender",
    power=1, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Elf"},
    text="Vivid — {T}: For each color among permanents you control, add one mana of that color.",
)

BLOSSOMING_DEFENSE = make_instant(
    name="Blossoming Defense",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +2/+2 and gains hexproof until end of turn. (It can't be the target of spells or abilities your opponents control.)",
)

BRISTLEBANE_BATTLER = make_creature(
    name="Bristlebane Battler",
    power=6, toughness=6,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Kithkin", "Soldier"},
    text="Trample, ward {2}\nThis creature enters with five -1/-1 counters on it.\nWhenever another creature you control enters while this creature has a -1/-1 counter on it, remove a -1/-1 counter from this creature.",
)

BRISTLEBANE_OUTRIDER = make_creature(
    name="Bristlebane Outrider",
    power=3, toughness=5,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Kithkin", "Knight"},
    text="This creature can't be blocked by creatures with power 2 or less.\nAs long as another creature entered the battlefield under your control this turn, this creature gets +2/+0.",
)

CELESTIAL_REUNION = make_sorcery(
    name="Celestial Reunion",
    mana_cost="{X}{G}",
    colors={Color.GREEN},
    text="As an additional cost to cast this spell, you may choose a creature type and behold two creatures of that type.\nSearch your library for a creature card with mana value X or less, reveal it, put it into your hand, then shuffle. If this spell's additional cost was paid and the revealed card is the chosen type, put that card onto the battlefield instead of putting it into your hand.",
)

CHAMPIONS_OF_THE_PERFECT = make_creature(
    name="Champions of the Perfect",
    power=6, toughness=6,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    text="As an additional cost to cast this spell, behold an Elf and exile it. (Exile an Elf you control or an Elf card from your hand.)\nWhenever you cast a creature spell, draw a card.\nWhen this creature leaves the battlefield, return the exiled card to its owner's hand.",
)

CHOMPING_CHANGELING = make_creature(
    name="Chomping Changeling",
    power=1, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Shapeshifter"},
    text="Changeling (This card is every creature type.)\nWhen this creature enters, destroy up to one target artifact or enchantment.",
)

CROSSROADS_WATCHER = make_creature(
    name="Crossroads Watcher",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Kithkin", "Ranger"},
    text="Trample\nWhenever another creature you control enters, this creature gets +1/+0 until end of turn.",
)

DAWNS_LIGHT_ARCHER = make_creature(
    name="Dawn's Light Archer",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Archer", "Elf"},
    text="Flash\nReach",
)

DUNDOOLIN_WEAVER = make_creature(
    name="Dundoolin Weaver",
    power=2, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Kithkin"},
    text="When this creature enters, if you control three or more creatures, return target permanent card from your graveyard to your hand.",
)

FORMIDABLE_SPEAKER = make_creature(
    name="Formidable Speaker",
    power=2, toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Elf"},
    text="When this creature enters, you may discard a card. If you do, search your library for a creature card, reveal it, put it into your hand, then shuffle.\n{1}, {T}: Untap another target permanent.",
)

GILTLEAFS_EMBRACE = make_enchantment(
    name="Gilt-Leaf's Embrace",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Flash\nEnchant creature\nWhen this Aura enters, enchanted creature gains trample and indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it. If its toughness is 0 or less, it still dies.)\nEnchanted creature gets +2/+0.",
    subtypes={"Aura"},
)

GREAT_FOREST_DRUID = make_creature(
    name="Great Forest Druid",
    power=0, toughness=4,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Treefolk"},
    text="{T}: Add one mana of any color.",
)

LUMINOLLUSK = make_creature(
    name="Luminollusk",
    power=2, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental"},
    text="Deathtouch\nVivid — When this creature enters, you gain life equal to the number of colors among permanents you control.",
)

LYS_ALANA_DIGNITARY = make_creature(
    name="Lys Alana Dignitary",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Advisor", "Elf"},
    text="As an additional cost to cast this spell, behold an Elf or pay {2}. (To behold an Elf, choose an Elf you control or reveal an Elf card from your hand.)\n{T}: Add {G}{G}. Activate only if there is an Elf card in your graveyard.",
)

LYS_ALANA_INFORMANT = make_creature(
    name="Lys Alana Informant",
    power=3, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Scout"},
    text="When this creature enters or dies, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

MIDNIGHT_TILLING = make_instant(
    name="Midnight Tilling",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Mill four cards, then you may return a permanent card from among them to your hand. (To mill four cards, put the top four cards of your library into your graveyard.)",
)

MISTMEADOW_COUNCIL = make_creature(
    name="Mistmeadow Council",
    power=4, toughness=3,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Advisor", "Kithkin"},
    text="This spell costs {1} less to cast if you control a Kithkin.\nWhen this creature enters, draw a card.",
)

MOONVIGIL_ADHERENTS = make_creature(
    name="Moon-Vigil Adherents",
    power=0, toughness=0,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Elf"},
    text="Trample\nThis creature gets +1/+1 for each creature you control and each creature card in your graveyard.",
)

MORCANTS_EYES = make_enchantment(
    name="Morcant's Eyes",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="At the beginning of your upkeep, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\n{4}{G}{G}, Sacrifice this enchantment: Create X 2/2 black and green Elf creature tokens, where X is the number of Elf cards in your graveyard. Activate only as a sorcery.",
    subtypes={"Elf"},
)

MUTABLE_EXPLORER = make_creature(
    name="Mutable Explorer",
    power=1, toughness=1,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Shapeshifter"},
    text="Changeling (This card is every creature type.)\nWhen this creature enters, create a tapped Mutavault token. (It's a land with \"{T}: Add {C}\" and \"{1}: This token becomes a 2/2 creature with all creature types until end of turn. It's still a land.\")",
)

PITILESS_FISTS = make_enchantment(
    name="Pitiless Fists",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Enchant creature you control\nWhen this Aura enters, enchanted creature fights up to one target creature an opponent controls. (Each deals damage equal to its power to the other.)\nEnchanted creature gets +2/+2.",
    subtypes={"Aura"},
)

PRISMABASHER = make_creature(
    name="Prismabasher",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental"},
    text="Trample\nVivid — When this creature enters, up to X target creatures you control get +X/+X until end of turn, where X is the number of colors among permanents you control.",
)

PRISMATIC_UNDERCURRENTS = make_enchantment(
    name="Prismatic Undercurrents",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Vivid — When this enchantment enters, search your library for up to X basic land cards, where X is the number of colors among permanents you control. Reveal those cards, put them into your hand, then shuffle.\nYou may play an additional land on each of your turns.",
)

PUMMELER_FOR_HIRE = make_creature(
    name="Pummeler for Hire",
    power=4, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Giant", "Mercenary"},
    text="Vigilance, reach\nWard {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nWhen this creature enters, you gain X life, where X is the greatest power among Giants you control.",
)

SAFEWRIGHT_CAVALRY = make_creature(
    name="Safewright Cavalry",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    text="This creature can't be blocked by more than one creature.\n{5}: Target Elf you control gets +2/+2 until end of turn.",
)

SAPLING_NURSERY = make_enchantment(
    name="Sapling Nursery",
    mana_cost="{6}{G}{G}",
    colors={Color.GREEN},
    text="Affinity for Forests (This spell costs {1} less to cast for each Forest you control.)\nLandfall — Whenever a land you control enters, create a 3/4 green Treefolk creature token with reach.\n{1}{G}, Exile this enchantment: Treefolk and Forests you control gain indestructible until end of turn.",
)

SELFLESS_SAFEWRIGHT = make_creature(
    name="Selfless Safewright",
    power=4, toughness=2,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    text="Flash\nConvoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nWhen this creature enters, choose a creature type. Other permanents you control of that type gain hexproof and indestructible until end of turn.",
)

SHIMMERWILDS_GROWTH = make_enchantment(
    name="Shimmerwilds Growth",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Enchant land\nAs this Aura enters, choose a color.\nEnchanted land is the chosen color.\nWhenever enchanted land is tapped for mana, its controller adds an additional one mana of the chosen color.",
    subtypes={"Aura"},
)

SPRY_AND_MIGHTY = make_sorcery(
    name="Spry and Mighty",
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    text="Choose two creatures you control. You draw X cards and the chosen creatures get +X/+X and gain trample until end of turn, where X is the difference between the chosen creatures' powers.",
)

SURLY_FARRIER = make_creature(
    name="Surly Farrier",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Citizen", "Kithkin"},
    text="{T}: Target creature you control gets +1/+1 and gains vigilance until end of turn. Activate only as a sorcery.",
)

TEND_THE_SPRIGS = make_sorcery(
    name="Tend the Sprigs",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. Then if you control seven or more lands and/or Treefolk, create a 3/4 green Treefolk creature token with reach. (It can block creatures with flying.)",
)

THOUGHTWEFT_CHARGE = make_instant(
    name="Thoughtweft Charge",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn. If a creature entered the battlefield under your control this turn, draw a card.",
)

TRYSTAN_CALLOUS_CULTIVATOR = make_creature(
    name="Trystan, Callous Cultivator",
    power=3, toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Elf"},
    supertypes={"Legendary"},
    text="Deathtouch\nWhenever this creature enters or transforms into Trystan, Callous Cultivator, mill three cards. Then if there is an Elf card in your graveyard, you gain 2 life.\nAt the beginning of your first main phase, you may pay {B}. If you do, transform Trystan.\n// Transforms into: Trystan, Penitent Culler (3/4)\nDeathtouch\nWhenever this creature transforms into Trystan, Penitent Culler, mill three cards, then you may exile an Elf card from your graveyard. If you do, each opponent loses 2 life.\nAt the beginning of your first main phase, you may pay {G}. If you do, transform Trystan.",
)

UNFORGIVING_AIM = make_instant(
    name="Unforgiving Aim",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Destroy target creature with flying.\n• Destroy target enchantment.\n• Create a 2/2 black and green Elf creature token.",
)

VINEBRED_BRAWLER = make_creature(
    name="Vinebred Brawler",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Berserker", "Elf"},
    text="This creature must be blocked if able.\nWhenever this creature attacks, another target Elf you control gets +2/+1 until end of turn.",
)

VIRULENT_EMISSARY = make_creature(
    name="Virulent Emissary",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Assassin", "Elf"},
    text="Deathtouch\nWhenever another creature you control enters, you gain 1 life.",
)

WILDVINE_PUMMELER = make_creature(
    name="Wildvine Pummeler",
    power=6, toughness=5,
    mana_cost="{6}{G}",
    colors={Color.GREEN},
    subtypes={"Berserker", "Giant"},
    text="Vivid — This spell costs {1} less to cast for each color among permanents you control.\nReach, trample",
)

ABIGALE_ELOQUENT_FIRSTYEAR = make_creature(
    name="Abigale, Eloquent First-Year",
    power=1, toughness=1,
    mana_cost="{W/B}{W/B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Bard", "Bird"},
    supertypes={"Legendary"},
    text="Flying, first strike, lifelink\nWhen Abigale enters, up to one other target creature loses all abilities. Put a flying counter, a first strike counter, and a lifelink counter on that creature.",
)

ASHLINGS_COMMAND = make_instant(
    name="Ashling's Command",
    mana_cost="{3}{U}{R}",
    colors={Color.RED, Color.BLUE},
    text="Choose two —\n• Create a token that's a copy of target Elemental you control.\n• Target player draws two cards.\n• Ashling's Command deals 2 damage to each creature target player controls.\n• Target player creates two Treasure tokens.",
    subtypes={"Elemental"},
)

BOGGART_CURSECRAFTER = make_creature(
    name="Boggart Cursecrafter",
    power=2, toughness=3,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Goblin", "Warlock"},
    text="Deathtouch\nWhenever another Goblin you control dies, this creature deals 1 damage to each opponent.",
)

BRE_OF_CLAN_STOUTARM = make_creature(
    name="Bre of Clan Stoutarm",
    power=4, toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Giant", "Warrior"},
    supertypes={"Legendary"},
    text="{1}{W}, {T}: Another target creature you control gains flying and lifelink until end of turn.\nAt the beginning of your end step, if you gained life this turn, exile cards from the top of your library until you exile a nonland card. You may cast that card without paying its mana cost if the spell's mana value is less than or equal to the amount of life you gained this turn. Otherwise, put it into your hand.",
)

BRIGIDS_COMMAND = make_sorcery(
    name="Brigid's Command",
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Choose two —\n• Create a token that's a copy of target Kithkin you control.\n• Target player creates a 1/1 green and white Kithkin creature token.\n• Target creature you control gets +3/+3 until end of turn.\n• Target creature you control fights target creature an opponent controls.",
    subtypes={"Kithkin"},
)

CATHARSIS = make_creature(
    name="Catharsis",
    power=3, toughness=4,
    mana_cost="{4}{R/W}{R/W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Elemental", "Incarnation"},
    text="When this creature enters, if {W}{W} was spent to cast it, create two 1/1 green and white Kithkin creature tokens.\nWhen this creature enters, if {R}{R} was spent to cast it, creatures you control get +1/+1 and gain haste until end of turn.\nEvoke {R/W}{R/W} (You may cast this spell for its evoke cost. If you do, it's sacrificed when it enters.)",
)

CHAOS_SPEWER = make_creature(
    name="Chaos Spewer",
    power=5, toughness=4,
    mana_cost="{2}{B/R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Goblin", "Warlock"},
    text="When this creature enters, you may pay {2}. If you don't, blight 2. (To blight 2, put two -1/-1 counters on a creature you control.)",
)

CHITINOUS_GRASPLING = make_creature(
    name="Chitinous Graspling",
    power=3, toughness=4,
    mana_cost="{3}{G/U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Shapeshifter"},
    text="Changeling (This card is every creature type.)\nReach",
)

DECEIT = make_creature(
    name="Deceit",
    power=5, toughness=5,
    mana_cost="{4}{U/B}{U/B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Elemental", "Incarnation"},
    text="When this creature enters, if {U}{U} was spent to cast it, return up to one other target nonland permanent to its owner's hand.\nWhen this creature enters, if {B}{B} was spent to cast it, target opponent reveals their hand. You choose a nonland card from it. That player discards that card.\nEvoke {U/B}{U/B}",
)

DEEPCHANNEL_DUELIST = make_creature(
    name="Deepchannel Duelist",
    power=2, toughness=2,
    mana_cost="{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Merfolk", "Soldier"},
    text="At the beginning of your end step, untap target Merfolk you control.\nOther Merfolk you control get +1/+1.",
)

DEEPWAY_NAVIGATOR = make_creature(
    name="Deepway Navigator",
    power=2, toughness=2,
    mana_cost="{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Merfolk", "Wizard"},
    text="Flash\nWhen this creature enters, untap each other Merfolk you control.\nAs long as you attacked with three or more Merfolk this turn, Merfolk you control get +1/+0.",
)

DORAN_BESIEGED_BY_TIME = make_creature(
    name="Doran, Besieged by Time",
    power=0, toughness=5,
    mana_cost="{1}{W}{B}{G}",
    colors={Color.BLACK, Color.GREEN, Color.WHITE},
    subtypes={"Druid", "Treefolk"},
    supertypes={"Legendary"},
    text="Each creature spell you cast with toughness greater than its power costs {1} less to cast.\nWhenever a creature you control attacks or blocks, it gets +X/+X until end of turn, where X is the difference between its power and toughness.",
)

DREAM_HARVEST = make_sorcery(
    name="Dream Harvest",
    mana_cost="{5}{U/B}{U/B}",
    colors={Color.BLACK, Color.BLUE},
    text="Each opponent exiles cards from the top of their library until they have exiled cards with total mana value 5 or greater this way. Until end of turn, you may cast cards exiled this way without paying their mana costs.",
)

ECLIPSED_BOGGART = make_creature(
    name="Eclipsed Boggart",
    power=2, toughness=3,
    mana_cost="{B/R}{B/R}{B/R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Goblin", "Scout"},
    text="When this creature enters, look at the top four cards of your library. You may reveal a Goblin, Swamp, or Mountain card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
)

ECLIPSED_ELF = make_creature(
    name="Eclipsed Elf",
    power=3, toughness=2,
    mana_cost="{B/G}{B/G}{B/G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Elf", "Scout"},
    text="When this creature enters, look at the top four cards of your library. You may reveal an Elf, Swamp, or Forest card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
)

ECLIPSED_FLAMEKIN = make_creature(
    name="Eclipsed Flamekin",
    power=1, toughness=4,
    mana_cost="{1}{U/R}{U/R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Elemental", "Scout"},
    text="When this creature enters, look at the top four cards of your library. You may reveal an Elemental, Island, or Mountain card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
)

ECLIPSED_KITHKIN = make_creature(
    name="Eclipsed Kithkin",
    power=2, toughness=1,
    mana_cost="{G/W}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Kithkin", "Scout"},
    text="When this creature enters, look at the top four cards of your library. You may reveal a Kithkin, Forest, or Plains card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
)

ECLIPSED_MERROW = make_creature(
    name="Eclipsed Merrow",
    power=2, toughness=3,
    mana_cost="{W/U}{W/U}{W/U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Merfolk", "Scout"},
    text="When this creature enters, look at the top four cards of your library. You may reveal a Merfolk, Plains, or Island card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
)

EMPTINESS = make_creature(
    name="Emptiness",
    power=3, toughness=5,
    mana_cost="{4}{W/B}{W/B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Elemental", "Incarnation"},
    text="When this creature enters, if {W}{W} was spent to cast it, return target creature card with mana value 3 or less from your graveyard to the battlefield.\nWhen this creature enters, if {B}{B} was spent to cast it, put three -1/-1 counters on up to one target creature.\nEvoke {W/B}{W/B}",
)

FEISTY_SPIKELING = make_creature(
    name="Feisty Spikeling",
    power=2, toughness=1,
    mana_cost="{1}{R/W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Shapeshifter"},
    text="Changeling (This card is every creature type.)\nDuring your turn, this creature has first strike.",
)

FIGURE_OF_FABLE = make_creature(
    name="Figure of Fable",
    power=1, toughness=1,
    mana_cost="{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Kithkin"},
    text="{G/W}: This creature becomes a Kithkin Scout with base power and toughness 2/3.\n{1}{G/W}{G/W}: If this creature is a Scout, it becomes a Kithkin Soldier with base power and toughness 4/5.\n{3}{G/W}{G/W}{G/W}: If this creature is a Soldier, it becomes a Kithkin Avatar with base power and toughness 7/8 and protection from each of your opponents.",
)

FLARING_CINDER = make_creature(
    name="Flaring Cinder",
    power=3, toughness=2,
    mana_cost="{1}{U/R}{U/R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Elemental", "Sorcerer"},
    text="When this creature enters and whenever you cast a spell with mana value 4 or greater, you may discard a card. If you do, draw a card.",
)

GANGLY_STOMPLING = make_creature(
    name="Gangly Stompling",
    power=4, toughness=2,
    mana_cost="{2}{R/G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Shapeshifter"},
    text="Changeling (This card is every creature type.)\nTrample",
)

GLISTER_BAIRN = make_creature(
    name="Glister Bairn",
    power=1, toughness=4,
    mana_cost="{2}{G/U}{G/U}{G/U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Ouphe"},
    text="Vivid — At the beginning of combat on your turn, another target creature you control gets +X/+X until end of turn, where X is the number of colors among permanents you control.",
)

GRUBS_COMMAND = make_sorcery(
    name="Grub's Command",
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Choose two —\n• Create a token that's a copy of target Goblin you control.\n• Creatures target player controls get +1/+1 and gain haste until end of turn.\n• Destroy target artifact or creature.\n• Target player mills five cards, then puts each Goblin card milled this way into their hand.",
    subtypes={"Goblin"},
)

HIGH_PERFECT_MORCANT = make_creature(
    name="High Perfect Morcant",
    power=4, toughness=4,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Elf", "Noble"},
    supertypes={"Legendary"},
    text="Whenever High Perfect Morcant or another Elf you control enters, each opponent blights 1. (They each put a -1/-1 counter on a creature they control.)\nTap three untapped Elves you control: Proliferate. Activate only as a sorcery. (Choose any number of permanents and/or players, then give each another counter of each kind already there.)",
)

HOVEL_HURLER = make_creature(
    name="Hovel Hurler",
    power=6, toughness=7,
    mana_cost="{3}{R/W}{R/W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Giant", "Warrior"},
    text="This creature enters with two -1/-1 counters on it.\n{R/W}{R/W}, Remove a counter from this creature: Another target creature you control gets +1/+0 and gains flying until end of turn. Activate only as a sorcery.",
)

KIROL_ATTENTIVE_FIRSTYEAR = make_creature(
    name="Kirol, Attentive First-Year",
    power=3, toughness=3,
    mana_cost="{1}{R/W}{R/W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Cleric", "Vampire"},
    supertypes={"Legendary"},
    text="Tap two untapped creatures you control: Copy target triggered ability you control. You may choose new targets for the copy. Activate only once each turn.",
)

LLUWEN_IMPERFECT_NATURALIST = make_creature(
    name="Lluwen, Imperfect Naturalist",
    power=1, toughness=3,
    mana_cost="{B/G}{B/G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Druid", "Elf"},
    supertypes={"Legendary"},
    text="When Lluwen enters, mill four cards, then you may put a creature or land card from among the milled cards on top of your library.\n{2}{B/G}{B/G}{B/G}, {T}, Discard a land card: Create a 1/1 black and green Worm creature token for each land card in your graveyard.",
)

MARALEN_FAE_ASCENDANT = make_creature(
    name="Maralen, Fae Ascendant",
    power=4, toughness=5,
    mana_cost="{2}{B}{G}{U}",
    colors={Color.BLACK, Color.GREEN, Color.BLUE},
    subtypes={"Elf", "Faerie", "Noble"},
    supertypes={"Legendary"},
    text="Flying\nWhenever Maralen or another Elf or Faerie you control enters, exile the top two cards of target opponent's library.\nOnce each turn, you may cast a spell with mana value less than or equal to the number of Elves and Faeries you control from among cards exiled with Maralen this turn without paying its mana cost.",
)

MERROW_SKYSWIMMER = make_creature(
    name="Merrow Skyswimmer",
    power=2, toughness=2,
    mana_cost="{3}{W/U}{W/U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Merfolk", "Soldier"},
    text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nFlying, vigilance\nWhen this creature enters, create a 1/1 white and blue Merfolk creature token.",
)

MISCHIEVOUS_SNEAKLING = make_creature(
    name="Mischievous Sneakling",
    power=2, toughness=2,
    mana_cost="{1}{U/B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Shapeshifter"},
    text="Changeling (This card is every creature type.)\nFlash",
)

MORCANTS_LOYALIST = make_creature(
    name="Morcant's Loyalist",
    power=3, toughness=2,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Elf", "Warrior"},
    text="Other Elves you control get +1/+1.\nWhen this creature dies, return another target Elf card from your graveyard to your hand.",
)

NOGGLE_ROBBER = make_creature(
    name="Noggle Robber",
    power=3, toughness=3,
    mana_cost="{1}{R/G}{R/G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Noggle", "Rogue"},
    text="When this creature enters or dies, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

PRIDEFUL_FEASTLING = make_creature(
    name="Prideful Feastling",
    power=2, toughness=3,
    mana_cost="{2}{W/B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Shapeshifter"},
    text="Changeling (This card is every creature type.)\nLifelink",
)

RAIDING_SCHEMES = make_enchantment(
    name="Raiding Schemes",
    mana_cost="{3}{R}{G}",
    colors={Color.GREEN, Color.RED},
    text="Each noncreature spell you cast has conspire. (As you cast a noncreature spell, you may tap two untapped creatures you control that share a color with it. When you do, copy it and you may choose new targets for the copy. A copy of a permanent spell becomes a token.)",
)

REAPING_WILLOW = make_creature(
    name="Reaping Willow",
    power=3, toughness=6,
    mana_cost="{1}{W/B}{W/B}{W/B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Cleric", "Treefolk"},
    text="Lifelink\nThis creature enters with two -1/-1 counters on it.\n{1}{W/B}, Remove two counters from this creature: Return target creature card with mana value 3 or less from your graveyard to the battlefield. Activate only as a sorcery.",
)

SANAR_INNOVATIVE_FIRSTYEAR = make_creature(
    name="Sanar, Innovative First-Year",
    power=2, toughness=4,
    mana_cost="{2}{U/R}{U/R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Goblin", "Sorcerer"},
    supertypes={"Legendary"},
    text="Vivid — At the beginning of your first main phase, reveal cards from the top of your library until you reveal X nonland cards, where X is the number of colors among permanents you control. For each of those colors, you may exile a card of that color from among the revealed cards. Then shuffle. You may cast the exiled cards this turn.",
)

SHADOW_URCHIN = make_creature(
    name="Shadow Urchin",
    power=3, toughness=4,
    mana_cost="{2}{B/R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Ouphe"},
    text="Whenever this creature attacks, blight 1. (Put a -1/-1 counter on a creature you control.)\nWhenever a creature you control with one or more counters on it dies, exile that many cards from the top of your library. Until your next end step, you may play those cards.",
)

STOIC_GROVEGUIDE = make_creature(
    name="Stoic Grove-Guide",
    power=5, toughness=4,
    mana_cost="{4}{B/G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Druid", "Elf"},
    text="{1}{B/G}, Exile this card from your graveyard: Create a 2/2 black and green Elf creature token. Activate only as a sorcery.",
)

SYGGS_COMMAND = make_sorcery(
    name="Sygg's Command",
    mana_cost="{1}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    text="Choose two —\n• Create a token that's a copy of target Merfolk you control.\n• Creatures target player controls gain lifelink until end of turn.\n• Target player draws a card.\n• Tap target creature. Put a stun counter on it.",
    subtypes={"Merfolk"},
)

TAM_MINDFUL_FIRSTYEAR = make_creature(
    name="Tam, Mindful First-Year",
    power=2, toughness=2,
    mana_cost="{1}{G/U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Gorgon", "Wizard"},
    supertypes={"Legendary"},
    text="Each other creature you control has hexproof from each of its colors.\n{T}: Target creature you control becomes all colors until end of turn.",
)

THOUGHTWEFT_LIEUTENANT = make_creature(
    name="Thoughtweft Lieutenant",
    power=2, toughness=2,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Kithkin", "Soldier"},
    text="Whenever this creature or another Kithkin you control enters, target creature you control gets +1/+1 and gains trample until end of turn.",
)

TRYSTANS_COMMAND = make_sorcery(
    name="Trystan's Command",
    mana_cost="{4}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Choose two —\n• Create a token that's a copy of target Elf you control.\n• Return one or two target permanent cards from your graveyard to your hand.\n• Destroy target creature or enchantment.\n• Creatures target player controls get +3/+3 until end of turn. Untap them.",
    subtypes={"Elf"},
)

TWINFLAME_TRAVELERS = make_creature(
    name="Twinflame Travelers",
    power=3, toughness=3,
    mana_cost="{2}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Elemental", "Sorcerer"},
    text="Flying\nIf a triggered ability of another Elemental you control triggers, it triggers an additional time.",
)

VIBRANCE = make_creature(
    name="Vibrance",
    power=4, toughness=4,
    mana_cost="{3}{R/G}{R/G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Elemental", "Incarnation"},
    text="When this creature enters, if {R}{R} was spent to cast it, this creature deals 3 damage to any target.\nWhen this creature enters, if {G}{G} was spent to cast it, search your library for a land card, reveal it, put it into your hand, then shuffle. You gain 2 life.\nEvoke {R/G}{R/G}",
)

VORACIOUS_TOMESKIMMER = make_creature(
    name="Voracious Tome-Skimmer",
    power=2, toughness=3,
    mana_cost="{U/B}{U/B}{U/B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Faerie", "Rogue"},
    text="Flying\nWhenever you cast a spell during an opponent's turn, you may pay 1 life. If you do, draw a card.",
)

WARY_FARMER = make_creature(
    name="Wary Farmer",
    power=3, toughness=3,
    mana_cost="{1}{G/W}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Citizen", "Kithkin"},
    text="At the beginning of your end step, if another creature entered the battlefield under your control this turn, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

WISTFULNESS = make_creature(
    name="Wistfulness",
    power=6, toughness=5,
    mana_cost="{3}{G/U}{G/U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Elemental", "Incarnation"},
    text="When this creature enters, if {G}{G} was spent to cast it, exile target artifact or enchantment an opponent controls.\nWhen this creature enters, if {U}{U} was spent to cast it, draw two cards, then discard a card.\nEvoke {G/U}{G/U} (You may cast this spell for its evoke cost. If you do, it's sacrificed when it enters.)",
)

CHRONICLE_OF_VICTORY = make_artifact(
    name="Chronicle of Victory",
    mana_cost="{6}",
    text="As Chronicle of Victory enters, choose a creature type.\nCreatures you control of the chosen type get +2/+2 and have first strike and trample.\nWhenever you cast a spell of the chosen type, draw a card.",
    supertypes={"Legendary"},
)

DAWNBLESSED_PENNANT = make_artifact(
    name="Dawn-Blessed Pennant",
    mana_cost="{1}",
    text="As this artifact enters, choose Elemental, Elf, Faerie, Giant, Goblin, Kithkin, Merfolk, or Treefolk.\nWhenever a permanent you control of the chosen type enters, you gain 1 life.\n{2}, {T}, Sacrifice this artifact: Return target card of the chosen type from your graveyard to your hand.",
)

FIRDOCH_CORE = make_artifact(
    name="Firdoch Core",
    mana_cost="{3}",
    text="Changeling (This card is every creature type.)\n{T}: Add one mana of any color.\n{4}: This artifact becomes a 4/4 artifact creature until end of turn.",
    subtypes={"Shapeshifter"},
)

FORAGING_WICKERMAW = make_artifact_creature(
    name="Foraging Wickermaw",
    power=1, toughness=3,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Scarecrow"},
    text="When this creature enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\n{1}: Add one mana of any color. This creature becomes that color until end of turn. Activate only once each turn.",
)

GATHERING_STONE = make_artifact(
    name="Gathering Stone",
    mana_cost="{4}",
    text="As this artifact enters, choose a creature type.\nSpells you cast of the chosen type cost {1} less to cast.\nWhen this artifact enters and at the beginning of your upkeep, look at the top card of your library. If it's a card of the chosen type, you may reveal it and put it into your hand. If you don't put the card into your hand, you may put it into your graveyard.",
)

MIRRORMIND_CROWN = make_artifact(
    name="Mirrormind Crown",
    mana_cost="{4}",
    text="As long as this Equipment is attached to a creature, the first time you would create one or more tokens each turn, you may instead create that many tokens that are copies of equipped creature.\nEquip {2}",
    subtypes={"Equipment"},
)

PUCAS_EYE = make_artifact(
    name="Puca's Eye",
    mana_cost="{2}",
    text="When this artifact enters, draw a card, then choose a color. This artifact becomes the chosen color.\n{3}, {T}: Draw a card. Activate only if there are five colors among permanents you control.",
)

SPRINGLEAF_DRUM = make_artifact(
    name="Springleaf Drum",
    mana_cost="{1}",
    text="{T}, Tap an untapped creature you control: Add one mana of any color.",
)

STALACTITE_DAGGER = make_artifact(
    name="Stalactite Dagger",
    mana_cost="{2}",
    text="When this Equipment enters, create a 1/1 colorless Shapeshifter creature token with changeling. (It's every creature type.)\nEquipped creature gets +1/+1 and is all creature types.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

BLOOD_CRYPT = make_land(
    name="Blood Crypt",
    text="({T}: Add {B} or {R}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
    subtypes={"Mountain", "Swamp"},
)

ECLIPSED_REALMS = make_land(
    name="Eclipsed Realms",
    text="As this land enters, choose Elemental, Elf, Faerie, Giant, Goblin, Kithkin, Merfolk, or Treefolk.\n{T}: Add {C}.\n{T}: Add one mana of any color. Spend this mana only to cast a spell of the chosen type or activate an ability of a source of the chosen type.",
)

EVOLVING_WILDS = make_land(
    name="Evolving Wilds",
    text="{T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
)

HALLOWED_FOUNTAIN = make_land(
    name="Hallowed Fountain",
    text="({T}: Add {W} or {U}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
    subtypes={"Island", "Plains"},
)

OVERGROWN_TOMB = make_land(
    name="Overgrown Tomb",
    text="({T}: Add {B} or {G}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
    subtypes={"Forest", "Swamp"},
)

STEAM_VENTS = make_land(
    name="Steam Vents",
    text="({T}: Add {U} or {R}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
    subtypes={"Island", "Mountain"},
)

TEMPLE_GARDEN = make_land(
    name="Temple Garden",
    text="({T}: Add {G} or {W}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
    subtypes={"Forest", "Plains"},
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

LORWYN_ECLIPSED_CARDS = {
    "Changeling Wayfinder": CHANGELING_WAYFINDER,
    "Rooftop Percher": ROOFTOP_PERCHER,
    "Adept Watershaper": ADEPT_WATERSHAPER,
    "Ajani, Outland Chaperone": AJANI_OUTLAND_CHAPERONE,
    "Appeal to Eirdu": APPEAL_TO_EIRDU,
    "Bark of Doran": BARK_OF_DORAN,
    "Brigid, Clachan's Heart": BRIGID_CLACHANS_HEART,
    "Burdened Stoneback": BURDENED_STONEBACK,
    "Champion of the Clachan": CHAMPION_OF_THE_CLACHAN,
    "Clachan Festival": CLACHAN_FESTIVAL,
    "Crib Swap": CRIB_SWAP,
    "Curious Colossus": CURIOUS_COLOSSUS,
    "Eirdu, Carrier of Dawn": EIRDU_CARRIER_OF_DAWN,
    "Encumbered Reejerey": ENCUMBERED_REEJEREY,
    "Evershrike's Gift": EVERSHRIKES_GIFT,
    "Flock Impostor": FLOCK_IMPOSTOR,
    "Gallant Fowlknight": GALLANT_FOWLKNIGHT,
    "Goldmeadow Nomad": GOLDMEADOW_NOMAD,
    "Keep Out": KEEP_OUT,
    "Kinbinding": KINBINDING,
    "Kinsbaile Aspirant": KINSBAILE_ASPIRANT,
    "Kinscaer Sentry": KINSCAER_SENTRY,
    "Kithkeeper": KITHKEEPER,
    "Liminal Hold": LIMINAL_HOLD,
    "Meanders Guide": MEANDERS_GUIDE,
    "Moonlit Lamenter": MOONLIT_LAMENTER,
    "Morningtide's Light": MORNINGTIDES_LIGHT,
    "Personify": PERSONIFY,
    "Protective Response": PROTECTIVE_RESPONSE,
    "Pyrrhic Strike": PYRRHIC_STRIKE,
    "Reluctant Dounguard": RELUCTANT_DOUNGUARD,
    "Rhys, the Evermore": RHYS_THE_EVERMORE,
    "Riverguard's Reflexes": RIVERGUARDS_REFLEXES,
    "Shore Lurker": SHORE_LURKER,
    "Slumbering Walker": SLUMBERING_WALKER,
    "Spiral into Solitude": SPIRAL_INTO_SOLITUDE,
    "Sun-Dappled Celebrant": SUNDAPPLED_CELEBRANT,
    "Thoughtweft Imbuer": THOUGHTWEFT_IMBUER,
    "Timid Shieldbearer": TIMID_SHIELDBEARER,
    "Tributary Vaulter": TRIBUTARY_VAULTER,
    "Wanderbrine Preacher": WANDERBRINE_PREACHER,
    "Wanderbrine Trapper": WANDERBRINE_TRAPPER,
    "Winnowing": WINNOWING,
    "Aquitect's Defenses": AQUITECTS_DEFENSES,
    "Blossombind": BLOSSOMBIND,
    "Champions of the Shoal": CHAMPIONS_OF_THE_SHOAL,
    "Disruptor of Currents": DISRUPTOR_OF_CURRENTS,
    "Flitterwing Nuisance": FLITTERWING_NUISANCE,
    "Glamer Gifter": GLAMER_GIFTER,
    "Glamermite": GLAMERMITE,
    "Glen Elendra Guardian": GLEN_ELENDRA_GUARDIAN,
    "Glen Elendra's Answer": GLEN_ELENDRAS_ANSWER,
    "Gravelgill Scoundrel": GRAVELGILL_SCOUNDREL,
    "Harmonized Crescendo": HARMONIZED_CRESCENDO,
    "Illusion Spinners": ILLUSION_SPINNERS,
    "Kulrath Mystic": KULRATH_MYSTIC,
    "Loch Mare": LOCH_MARE,
    "Lofty Dreams": LOFTY_DREAMS,
    "Mirrorform": MIRRORFORM,
    "Noggle the Mind": NOGGLE_THE_MIND,
    "Oko, Lorwyn Liege": OKO_LORWYN_LIEGE,
    "Omni-Changeling": OMNICHANGELING,
    "Pestered Wellguard": PESTERED_WELLGUARD,
    "Rime Chill": RIME_CHILL,
    "Rimefire Torque": RIMEFIRE_TORQUE,
    "Rimekin Recluse": RIMEKIN_RECLUSE,
    "Run Away Together": RUN_AWAY_TOGETHER,
    "Shinestriker": SHINESTRIKER,
    "Silvergill Mentor": SILVERGILL_MENTOR,
    "Silvergill Peddler": SILVERGILL_PEDDLER,
    "Spell Snare": SPELL_SNARE,
    "Stratosoarer": STRATOSOARER,
    "Summit Sentinel": SUMMIT_SENTINEL,
    "Sunderflock": SUNDERFLOCK,
    "Swat Away": SWAT_AWAY,
    "Sygg, Wanderwine Wisdom": SYGG_WANDERWINE_WISDOM,
    "Tanufel Rimespeaker": TANUFEL_RIMESPEAKER,
    "Temporal Cleansing": TEMPORAL_CLEANSING,
    "Thirst for Identity": THIRST_FOR_IDENTITY,
    "Unexpected Assistance": UNEXPECTED_ASSISTANCE,
    "Unwelcome Sprite": UNWELCOME_SPRITE,
    "Wanderwine Distracter": WANDERWINE_DISTRACTER,
    "Wanderwine Farewell": WANDERWINE_FAREWELL,
    "Wild Unraveling": WILD_UNRAVELING,
    "Auntie's Sentence": AUNTIES_SENTENCE,
    "Barbed Bloodletter": BARBED_BLOODLETTER,
    "Bile-Vial Boggart": BILEVIAL_BOGGART,
    "Bitterbloom Bearer": BITTERBLOOM_BEARER,
    "Blight Rot": BLIGHT_ROT,
    "Blighted Blackthorn": BLIGHTED_BLACKTHORN,
    "Bloodline Bidding": BLOODLINE_BIDDING,
    "Boggart Mischief": BOGGART_MISCHIEF,
    "Boggart Prankster": BOGGART_PRANKSTER,
    "Bogslither's Embrace": BOGSLITHERS_EMBRACE,
    "Champion of the Weird": CHAMPION_OF_THE_WEIRD,
    "Creakwood Safewright": CREAKWOOD_SAFEWRIGHT,
    "Darkness Descends": DARKNESS_DESCENDS,
    "Dawnhand Dissident": DAWNHAND_DISSIDENT,
    "Dawnhand Eulogist": DAWNHAND_EULOGIST,
    "Dose of Dawnglow": DOSE_OF_DAWNGLOW,
    "Dream Seizer": DREAM_SEIZER,
    "Gloom Ripper": GLOOM_RIPPER,
    "Gnarlbark Elm": GNARLBARK_ELM,
    "Graveshifter": GRAVESHIFTER,
    "Grub, Storied Matriarch": GRUB_STORIED_MATRIARCH,
    "Gutsplitter Gang": GUTSPLITTER_GANG,
    "Heirloom Auntie": HEIRLOOM_AUNTIE,
    "Iron-Shield Elf": IRONSHIELD_ELF,
    "Moonglove Extractor": MOONGLOVE_EXTRACTOR,
    "Moonshadow": MOONSHADOW,
    "Mornsong Aria": MORNSONG_ARIA,
    "Mudbutton Cursetosser": MUDBUTTON_CURSETOSSER,
    "Nameless Inversion": NAMELESS_INVERSION,
    "Nightmare Sower": NIGHTMARE_SOWER,
    "Perfect Intimidation": PERFECT_INTIMIDATION,
    "Requiting Hex": REQUITING_HEX,
    "Retched Wretch": RETCHED_WRETCH,
    "Scarblade Scout": SCARBLADE_SCOUT,
    "Scarblade's Malice": SCARBLADES_MALICE,
    "Shimmercreep": SHIMMERCREEP,
    "Taster of Wares": TASTER_OF_WARES,
    "Twilight Diviner": TWILIGHT_DIVINER,
    "Unbury": UNBURY,
    "Ashling, Rekindled": ASHLING_REKINDLED,
    "Boldwyr Aggressor": BOLDWYR_AGGRESSOR,
    "Boneclub Berserker": BONECLUB_BERSERKER,
    "Boulder Dash": BOULDER_DASH,
    "Brambleback Brute": BRAMBLEBACK_BRUTE,
    "Burning Curiosity": BURNING_CURIOSITY,
    "Champion of the Path": CHAMPION_OF_THE_PATH,
    "Cinder Strike": CINDER_STRIKE,
    "Collective Inferno": COLLECTIVE_INFERNO,
    "Elder Auntie": ELDER_AUNTIE,
    "End-Blaze Epiphany": ENDBLAZE_EPIPHANY,
    "Enraged Flamecaster": ENRAGED_FLAMECASTER,
    "Explosive Prodigy": EXPLOSIVE_PRODIGY,
    "Feed the Flames": FEED_THE_FLAMES,
    "Flame-Chain Mauler": FLAMECHAIN_MAULER,
    "Flamebraider": FLAMEBRAIDER,
    "Flamekin Gildweaver": FLAMEKIN_GILDWEAVER,
    "Giantfall": GIANTFALL,
    "Goatnap": GOATNAP,
    "Goliath Daydreamer": GOLIATH_DAYDREAMER,
    "Gristle Glutton": GRISTLE_GLUTTON,
    "Hexing Squelcher": HEXING_SQUELCHER,
    "Impolite Entrance": IMPOLITE_ENTRANCE,
    "Kindle the Inner Flame": KINDLE_THE_INNER_FLAME,
    "Kulrath Zealot": KULRATH_ZEALOT,
    "Lasting Tarfire": LASTING_TARFIRE,
    "Lavaleaper": LAVALEAPER,
    "Meek Attack": MEEK_ATTACK,
    "Reckless Ransacking": RECKLESS_RANSACKING,
    "Scuzzback Scrounger": SCUZZBACK_SCROUNGER,
    "Sear": SEAR,
    "Sizzling Changeling": SIZZLING_CHANGELING,
    "Soul Immolation": SOUL_IMMOLATION,
    "Soulbright Seeker": SOULBRIGHT_SEEKER,
    "Sourbread Auntie": SOURBREAD_AUNTIE,
    "Spinerock Tyrant": SPINEROCK_TYRANT,
    "Squawkroaster": SQUAWKROASTER,
    "Sting-Slinger": STINGSLINGER,
    "Tweeze": TWEEZE,
    "Warren Torchmaster": WARREN_TORCHMASTER,
    "Assert Perfection": ASSERT_PERFECTION,
    "Aurora Awakener": AURORA_AWAKENER,
    "Bloom Tender": BLOOM_TENDER,
    "Blossoming Defense": BLOSSOMING_DEFENSE,
    "Bristlebane Battler": BRISTLEBANE_BATTLER,
    "Bristlebane Outrider": BRISTLEBANE_OUTRIDER,
    "Celestial Reunion": CELESTIAL_REUNION,
    "Champions of the Perfect": CHAMPIONS_OF_THE_PERFECT,
    "Chomping Changeling": CHOMPING_CHANGELING,
    "Crossroads Watcher": CROSSROADS_WATCHER,
    "Dawn's Light Archer": DAWNS_LIGHT_ARCHER,
    "Dundoolin Weaver": DUNDOOLIN_WEAVER,
    "Formidable Speaker": FORMIDABLE_SPEAKER,
    "Gilt-Leaf's Embrace": GILTLEAFS_EMBRACE,
    "Great Forest Druid": GREAT_FOREST_DRUID,
    "Luminollusk": LUMINOLLUSK,
    "Lys Alana Dignitary": LYS_ALANA_DIGNITARY,
    "Lys Alana Informant": LYS_ALANA_INFORMANT,
    "Midnight Tilling": MIDNIGHT_TILLING,
    "Mistmeadow Council": MISTMEADOW_COUNCIL,
    "Moon-Vigil Adherents": MOONVIGIL_ADHERENTS,
    "Morcant's Eyes": MORCANTS_EYES,
    "Mutable Explorer": MUTABLE_EXPLORER,
    "Pitiless Fists": PITILESS_FISTS,
    "Prismabasher": PRISMABASHER,
    "Prismatic Undercurrents": PRISMATIC_UNDERCURRENTS,
    "Pummeler for Hire": PUMMELER_FOR_HIRE,
    "Safewright Cavalry": SAFEWRIGHT_CAVALRY,
    "Sapling Nursery": SAPLING_NURSERY,
    "Selfless Safewright": SELFLESS_SAFEWRIGHT,
    "Shimmerwilds Growth": SHIMMERWILDS_GROWTH,
    "Spry and Mighty": SPRY_AND_MIGHTY,
    "Surly Farrier": SURLY_FARRIER,
    "Tend the Sprigs": TEND_THE_SPRIGS,
    "Thoughtweft Charge": THOUGHTWEFT_CHARGE,
    "Trystan, Callous Cultivator": TRYSTAN_CALLOUS_CULTIVATOR,
    "Unforgiving Aim": UNFORGIVING_AIM,
    "Vinebred Brawler": VINEBRED_BRAWLER,
    "Virulent Emissary": VIRULENT_EMISSARY,
    "Wildvine Pummeler": WILDVINE_PUMMELER,
    "Abigale, Eloquent First-Year": ABIGALE_ELOQUENT_FIRSTYEAR,
    "Ashling's Command": ASHLINGS_COMMAND,
    "Boggart Cursecrafter": BOGGART_CURSECRAFTER,
    "Bre of Clan Stoutarm": BRE_OF_CLAN_STOUTARM,
    "Brigid's Command": BRIGIDS_COMMAND,
    "Catharsis": CATHARSIS,
    "Chaos Spewer": CHAOS_SPEWER,
    "Chitinous Graspling": CHITINOUS_GRASPLING,
    "Deceit": DECEIT,
    "Deepchannel Duelist": DEEPCHANNEL_DUELIST,
    "Deepway Navigator": DEEPWAY_NAVIGATOR,
    "Doran, Besieged by Time": DORAN_BESIEGED_BY_TIME,
    "Dream Harvest": DREAM_HARVEST,
    "Eclipsed Boggart": ECLIPSED_BOGGART,
    "Eclipsed Elf": ECLIPSED_ELF,
    "Eclipsed Flamekin": ECLIPSED_FLAMEKIN,
    "Eclipsed Kithkin": ECLIPSED_KITHKIN,
    "Eclipsed Merrow": ECLIPSED_MERROW,
    "Emptiness": EMPTINESS,
    "Feisty Spikeling": FEISTY_SPIKELING,
    "Figure of Fable": FIGURE_OF_FABLE,
    "Flaring Cinder": FLARING_CINDER,
    "Gangly Stompling": GANGLY_STOMPLING,
    "Glister Bairn": GLISTER_BAIRN,
    "Grub's Command": GRUBS_COMMAND,
    "High Perfect Morcant": HIGH_PERFECT_MORCANT,
    "Hovel Hurler": HOVEL_HURLER,
    "Kirol, Attentive First-Year": KIROL_ATTENTIVE_FIRSTYEAR,
    "Lluwen, Imperfect Naturalist": LLUWEN_IMPERFECT_NATURALIST,
    "Maralen, Fae Ascendant": MARALEN_FAE_ASCENDANT,
    "Merrow Skyswimmer": MERROW_SKYSWIMMER,
    "Mischievous Sneakling": MISCHIEVOUS_SNEAKLING,
    "Morcant's Loyalist": MORCANTS_LOYALIST,
    "Noggle Robber": NOGGLE_ROBBER,
    "Prideful Feastling": PRIDEFUL_FEASTLING,
    "Raiding Schemes": RAIDING_SCHEMES,
    "Reaping Willow": REAPING_WILLOW,
    "Sanar, Innovative First-Year": SANAR_INNOVATIVE_FIRSTYEAR,
    "Shadow Urchin": SHADOW_URCHIN,
    "Stoic Grove-Guide": STOIC_GROVEGUIDE,
    "Sygg's Command": SYGGS_COMMAND,
    "Tam, Mindful First-Year": TAM_MINDFUL_FIRSTYEAR,
    "Thoughtweft Lieutenant": THOUGHTWEFT_LIEUTENANT,
    "Trystan's Command": TRYSTANS_COMMAND,
    "Twinflame Travelers": TWINFLAME_TRAVELERS,
    "Vibrance": VIBRANCE,
    "Voracious Tome-Skimmer": VORACIOUS_TOMESKIMMER,
    "Wary Farmer": WARY_FARMER,
    "Wistfulness": WISTFULNESS,
    "Chronicle of Victory": CHRONICLE_OF_VICTORY,
    "Dawn-Blessed Pennant": DAWNBLESSED_PENNANT,
    "Firdoch Core": FIRDOCH_CORE,
    "Foraging Wickermaw": FORAGING_WICKERMAW,
    "Gathering Stone": GATHERING_STONE,
    "Mirrormind Crown": MIRRORMIND_CROWN,
    "Puca's Eye": PUCAS_EYE,
    "Springleaf Drum": SPRINGLEAF_DRUM,
    "Stalactite Dagger": STALACTITE_DAGGER,
    "Blood Crypt": BLOOD_CRYPT,
    "Eclipsed Realms": ECLIPSED_REALMS,
    "Evolving Wilds": EVOLVING_WILDS,
    "Hallowed Fountain": HALLOWED_FOUNTAIN,
    "Overgrown Tomb": OVERGROWN_TOMB,
    "Steam Vents": STEAM_VENTS,
    "Temple Garden": TEMPLE_GARDEN,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
}

print(f"Loaded {len(LORWYN_ECLIPSED_CARDS)} Lorwyn Eclipsed cards")
