"""
Edge of Eternities (EOE) Card Implementations

Real card data fetched from Scryfall API.
266 cards in set.
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

ANTICAUSAL_VESTIGE = make_creature(
    name="Anticausal Vestige",
    power=7, toughness=5,
    mana_cost="{6}",
    colors=set(),
    subtypes={"Eldrazi"},
    text="When this creature leaves the battlefield, draw a card, then you may put a permanent card with mana value less than or equal to the number of lands you control from your hand onto the battlefield tapped.\nWarp {4} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

TEZZERET_CRUEL_CAPTAIN = make_planeswalker(
    name="Tezzeret, Cruel Captain",
    mana_cost="{3}",
    colors=set(),
    loyalty=4,
    subtypes={"Tezzeret"},
    supertypes={"Legendary"},
    text="Whenever an artifact you control enters, put a loyalty counter on Tezzeret.\n0: Untap target artifact or creature. If it's an artifact creature, put a +1/+1 counter on it.\n−3: Search your library for an artifact card with mana value 1 or less, reveal it, put it into your hand, then shuffle.\n−7: You get an emblem with \"At the beginning of combat on your turn, put three +1/+1 counters on target artifact you control. If it's not a creature, it becomes a 0/0 Robot artifact creature.\"",
)

ALLFATES_STALKER = make_creature(
    name="All-Fates Stalker",
    power=2, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Assassin", "Drix"},
    text="When this creature enters, exile up to one target non-Assassin creature until this creature leaves the battlefield.\nWarp {1}{W} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

ASTELLI_RECLAIMER = make_creature(
    name="Astelli Reclaimer",
    power=5, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel", "Warrior"},
    text="Flying\nWhen this creature enters, return target noncreature, nonland permanent card with mana value X or less from your graveyard to the battlefield, where X is the amount of mana spent to cast this creature.\nWarp {2}{W}",
)

AUXILIARY_BOOSTERS = make_artifact(
    name="Auxiliary Boosters",
    mana_cost="{4}{W}",
    text="When this Equipment enters, create a 2/2 colorless Robot artifact creature token and attach this Equipment to it.\nEquipped creature gets +1/+2 and has flying.\nEquip {3} ({3}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

BANISHING_LIGHT = make_enchantment(
    name="Banishing Light",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, exile target nonland permanent an opponent controls until this enchantment leaves the battlefield.",
)

BEYOND_THE_QUIET = make_sorcery(
    name="Beyond the Quiet",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Exile all creatures and Spacecraft.",
)

BRIGHTSPEAR_ZEALOT = make_creature(
    name="Brightspear Zealot",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Vigilance\nThis creature gets +2/+0 as long as you've cast two or more spells this turn.",
)

COSMOGRAND_ZENITH = make_creature(
    name="Cosmogrand Zenith",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Whenever you cast your second spell each turn, choose one —\n• Create two 1/1 white Human Soldier creature tokens.\n• Put a +1/+1 counter on each creature you control.",
)

DAWNSTRIKE_VANGUARD = make_creature(
    name="Dawnstrike Vanguard",
    power=4, toughness=5,
    mana_cost="{5}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Lifelink\nAt the beginning of your end step, if you control two or more tapped creatures, put a +1/+1 counter on each creature you control other than this creature.",
)

DOCKWORKER_DRONE = make_artifact_creature(
    name="Dockworker Drone",
    power=1, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Robot"},
    text="This creature enters with a +1/+1 counter on it.\nWhen this creature dies, put its counters on target creature you control.",
)

DUALSUN_ADEPTS = make_creature(
    name="Dual-Sun Adepts",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Double strike\n{5}: Creatures you control get +1/+1 until end of turn.",
)

DUALSUN_TECHNIQUE = make_instant(
    name="Dual-Sun Technique",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature you control gains double strike until end of turn. If it has a +1/+1 counter on it, draw a card.",
)

EMERGENCY_EJECT = make_instant(
    name="Emergency Eject",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Destroy target nonland permanent. Its controller creates a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

EXALTED_SUNBORN = make_creature(
    name="Exalted Sunborn",
    power=4, toughness=5,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel", "Wizard"},
    text="Flying, lifelink\nIf one or more tokens would be created under your control, twice that many of those tokens are created instead.\nWarp {1}{W} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

EXOSUIT_SAVIOR = make_creature(
    name="Exosuit Savior",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Flying\nWhen this creature enters, return up to one other target permanent you control to its owner's hand.",
)

FLIGHTDECK_COORDINATOR = make_creature(
    name="Flight-Deck Coordinator",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="At the beginning of your end step, if you control two or more tapped creatures, you gain 2 life.",
)

FOCUS_FIRE = make_instant(
    name="Focus Fire",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Focus Fire deals X damage to target attacking or blocking creature, where X is 2 plus the number of creatures and/or Spacecraft you control.",
)

HALIYA_GUIDED_BY_LIGHT = make_creature(
    name="Haliya, Guided by Light",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Whenever Haliya or another creature or artifact you control enters, you gain 1 life.\nAt the beginning of your end step, draw a card if you've gained 3 or more life this turn.\nWarp {W} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

HARDLIGHT_CONTAINMENT = make_enchantment(
    name="Hardlight Containment",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Enchant artifact you control\nWhen this Aura enters, exile target creature an opponent controls until this Aura leaves the battlefield.\nEnchanted permanent has ward {1}.",
    subtypes={"Aura"},
)

HONOR = make_sorcery(
    name="Honor",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Put a +1/+1 counter on target creature.\nDraw a card.",
)

HONORED_KNIGHTCAPTAIN = make_creature(
    name="Honored Knight-Captain",
    power=1, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Advisor", "Human", "Knight"},
    text="When this creature enters, create a 1/1 white Human Soldier creature token.\n{4}{W}{W}, Sacrifice this creature: Search your library for an Equipment card, put it onto the battlefield, then shuffle.",
)

KNIGHT_LUMINARY = make_creature(
    name="Knight Luminary",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="When this creature enters, create a 1/1 white Human Soldier creature token.\nWarp {1}{W} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

LIGHTSTALL_INQUISITOR = make_creature(
    name="Lightstall Inquisitor",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Angel", "Wizard"},
    text="Vigilance\nWhen this creature enters, each opponent exiles a card from their hand and may play that card for as long as it remains exiled. Each spell cast this way costs {1} more to cast. Each land played this way enters tapped.",
)

LUMENCLASS_FRIGATE = make_artifact(
    name="Lumen-Class Frigate",
    mana_cost="{1}{W}",
    text="Station (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 12+.)\n2+ | Other creatures you control get +1/+1.\n12+ | Flying, lifelink",
    subtypes={"Spacecraft"},
)

LUXKNIGHT_BREACHER = make_creature(
    name="Luxknight Breacher",
    power=2, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="This creature enters with a +1/+1 counter on it for each other creature and/or artifact you control.",
)

PINNACLE_STARCAGE = make_artifact(
    name="Pinnacle Starcage",
    mana_cost="{1}{W}{W}",
    text="When this artifact enters, exile all artifacts and creatures with mana value 2 or less until this artifact leaves the battlefield.\n{6}{W}{W}: Put each card exiled with this artifact into its owner's graveyard, then create a 2/2 colorless Robot artifact creature token for each card put into a graveyard this way. Sacrifice this artifact.",
)

PULSAR_SQUADRON_ACE = make_creature(
    name="Pulsar Squadron Ace",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Pilot"},
    text="When this creature enters, look at the top five cards of your library. You may reveal a Spacecraft card from among them and put it into your hand. Put the rest on the bottom of your library in a random order. If you didn't put a card into your hand this way, put a +1/+1 counter on this creature.",
)

RADIANT_STRIKE = make_instant(
    name="Radiant Strike",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Destroy target artifact or tapped creature. You gain 3 life.",
)

RAYBLADE_TROOPER = make_creature(
    name="Rayblade Trooper",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="When this creature enters, put a +1/+1 counter on target creature you control.\nWhenever a nontoken creature you control with a +1/+1 counter on it dies, create a 1/1 white Human Soldier creature token.\nWarp {1}{W} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

REROUTE_SYSTEMS = make_instant(
    name="Reroute Systems",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Target artifact or creature gains indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)\n• Reroute Systems deals 2 damage to target tapped creature.",
)

RESCUE_SKIFF = make_artifact(
    name="Rescue Skiff",
    mana_cost="{5}{W}",
    text="When this Spacecraft enters, return target creature or enchantment card from your graveyard to the battlefield.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 10+.)\n10+ | Flying",
    subtypes={"Spacecraft"},
)

SCOUT_FOR_SURVIVORS = make_sorcery(
    name="Scout for Survivors",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Return up to three target creature cards with total mana value 3 or less from your graveyard to the battlefield. Put a +1/+1 counter on each of them.",
)

SEAM_RIP = make_enchantment(
    name="Seam Rip",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, exile target nonland permanent an opponent controls with mana value 2 or less until this enchantment leaves the battlefield.",
)

THE_SERIEMA = make_artifact(
    name="The Seriema",
    mana_cost="{1}{W}{W}",
    text="When The Seriema enters, search your library for a legendary creature card, reveal it, put it into your hand, then shuffle.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 7+.)\n7+ | Flying\nOther tapped legendary creatures you control have indestructible.",
    subtypes={"Spacecraft"},
    supertypes={"Legendary"},
)

SQUIRES_LIGHTBLADE = make_artifact(
    name="Squire's Lightblade",
    mana_cost="{W}",
    text="Flash\nWhen this Equipment enters, attach it to target creature you control. That creature gains first strike until end of turn.\nEquipped creature gets +1/+0.\nEquip {3}",
    subtypes={"Equipment"},
)

STARFIELD_SHEPHERD = make_creature(
    name="Starfield Shepherd",
    power=3, toughness=2,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nWhen this creature enters, search your library for a basic Plains card or a creature card with mana value 1 or less, reveal it, put it into your hand, then shuffle.\nWarp {1}{W} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

STARFIGHTER_PILOT = make_creature(
    name="Starfighter Pilot",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Pilot"},
    text="Whenever this creature becomes tapped, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

STARPORT_SECURITY = make_artifact_creature(
    name="Starport Security",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Robot", "Soldier"},
    text="{3}{W}, {T}: Tap another target creature. This ability costs {2} less to activate if you control a creature with a +1/+1 counter on it.",
)

SUNSTAR_CHAPLAIN = make_creature(
    name="Sunstar Chaplain",
    power=3, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Human"},
    text="At the beginning of your end step, if you control two or more tapped creatures, put a +1/+1 counter on target creature you control.\n{2}, Remove a +1/+1 counter from a creature you control: Tap target artifact or creature.",
)

SUNSTAR_EXPANSIONIST = make_creature(
    name="Sunstar Expansionist",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="When this creature enters, if an opponent controls more lands than you, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")\nLandfall — Whenever a land you control enters, this creature gets +1/+0 until end of turn.",
)

SUNSTAR_LIGHTSMITH = make_creature(
    name="Sunstar Lightsmith",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Artificer", "Human"},
    text="Whenever you cast your second spell each turn, put a +1/+1 counter on this creature and draw a card.",
)

WEDGELIGHT_RAMMER = make_artifact(
    name="Wedgelight Rammer",
    mana_cost="{3}{W}",
    text="When this Spacecraft enters, create a 2/2 colorless Robot artifact creature token.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 9+.)\n9+ | Flying, first strike",
    subtypes={"Spacecraft"},
)

WEFTBLADE_ENHANCER = make_creature(
    name="Weftblade Enhancer",
    power=3, toughness=4,
    mana_cost="{5}{W}",
    colors={Color.WHITE},
    subtypes={"Artificer", "Drix"},
    text="When this creature enters, put a +1/+1 counter on each of up to two target creatures.\nWarp {2}{W} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

ZEALOUS_DISPLAY = make_instant(
    name="Zealous Display",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +2/+0 until end of turn. If it's not your turn, untap those creatures.",
)

ANNUL = make_instant(
    name="Annul",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Counter target artifact or enchantment spell.",
)

ATOMIC_MICROSIZER = make_artifact(
    name="Atomic Microsizer",
    mana_cost="{U}",
    text="Equipped creature gets +1/+0.\nWhenever equipped creature attacks, choose up to one target creature. That creature can't be blocked this turn and has base power and toughness 1/1 until end of turn.\nEquip {2}",
    subtypes={"Equipment"},
)

CEREBRAL_DOWNLOAD = make_instant(
    name="Cerebral Download",
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    text="Surveil X, where X is the number of artifacts you control. Then draw three cards. (To surveil X, look at the top X cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
)

CLOUDSCULPT_TECHNICIAN = make_creature(
    name="Cloudsculpt Technician",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Artificer", "Jellyfish"},
    text="Flying\nAs long as you control an artifact, this creature gets +1/+0.",
)

CODECRACKER_HOUND = make_creature(
    name="Codecracker Hound",
    power=2, toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Dog"},
    text="When this creature enters, look at the top two cards of your library. Put one into your hand and the other into your graveyard.\nWarp {2}{U} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

CONSULT_THE_STAR_CHARTS = make_instant(
    name="Consult the Star Charts",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Kicker {1}{U} (You may pay an additional {1}{U} as you cast this spell.)\nLook at the top X cards of your library, where X is the number of lands you control. Put one of those cards into your hand. If this spell was kicked, put two of those cards into your hand instead. Put the rest on the bottom of your library in a random order.",
)

CRYOGEN_RELIC = make_artifact(
    name="Cryogen Relic",
    mana_cost="{1}{U}",
    text="When this artifact enters or leaves the battlefield, draw a card.\n{1}{U}, Sacrifice this artifact: Put a stun counter on up to one target tapped creature. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

CRYOSHATTER = make_enchantment(
    name="Cryoshatter",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Enchant creature\nEnchanted creature gets -5/-0.\nWhen enchanted creature becomes tapped or is dealt damage, destroy it.",
    subtypes={"Aura"},
)

DESCULPTING_BLAST = make_instant(
    name="Desculpting Blast",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target nonland permanent to its owner's hand. If it was attacking, create a 1/1 colorless Drone artifact creature token with flying and \"This token can block only creatures with flying.\"",
)

DIVERT_DISASTER = make_instant(
    name="Divert Disaster",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {2}. If they do, you create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

EMISSARY_ESCORT = make_artifact_creature(
    name="Emissary Escort",
    power=0, toughness=4,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Robot", "Soldier"},
    text="This creature gets +X/+0, where X is the greatest mana value among other artifacts you control.",
)

GIGASTORM_TITAN = make_creature(
    name="Gigastorm Titan",
    power=4, toughness=4,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="This spell costs {3} less to cast if you've cast another spell this turn.",
)

ILLVOI_GALEBLADE = make_creature(
    name="Illvoi Galeblade",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Jellyfish", "Warrior"},
    text="Flash\nFlying\n{2}, Sacrifice this creature: Draw a card.",
)

ILLVOI_INFILTRATOR = make_creature(
    name="Illvoi Infiltrator",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Jellyfish", "Rogue"},
    text="This creature can't be blocked if you've cast two or more spells this turn.\nWhenever this creature deals combat damage to a player, draw a card.",
)

ILLVOI_LIGHT_JAMMER = make_artifact(
    name="Illvoi Light Jammer",
    mana_cost="{1}{U}",
    text="Flash\nWhen this Equipment enters, attach it to target creature you control. That creature gains hexproof until end of turn. (It can't be the target of spells or abilities your opponents control.)\nEquipped creature gets +1/+2.\nEquip {3}",
    subtypes={"Equipment"},
)

ILLVOI_OPERATIVE = make_creature(
    name="Illvoi Operative",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Jellyfish", "Rogue"},
    text="Whenever you cast your second spell each turn, put a +1/+1 counter on this creature.",
)

LOST_IN_SPACE = make_instant(
    name="Lost in Space",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Target artifact or creature's owner puts it on their choice of the top or bottom of their library. Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

MECHAN_ASSEMBLER = make_artifact_creature(
    name="Mechan Assembler",
    power=4, toughness=4,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Artificer", "Robot"},
    text="Whenever another artifact you control enters, create a 2/2 colorless Robot artifact creature token. This ability triggers only once each turn.",
)

MECHAN_NAVIGATOR = make_artifact_creature(
    name="Mechan Navigator",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Pilot", "Robot"},
    text="Whenever this creature becomes tapped, draw a card, then discard a card.",
)

MECHAN_SHIELDMATE = make_artifact_creature(
    name="Mechan Shieldmate",
    power=3, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Robot", "Soldier"},
    text="Defender\nAs long as an artifact entered the battlefield under your control this turn, this creature can attack as though it didn't have defender.",
)

MECHANOZOA = make_artifact_creature(
    name="Mechanozoa",
    power=5, toughness=5,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Jellyfish", "Robot"},
    text="When this creature enters, tap target artifact or creature an opponent controls and put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nWarp {2}{U} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

MENTAL_MODULATION = make_instant(
    name="Mental Modulation",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="This spell costs {1} less to cast during your turn.\nTap target artifact or creature.\nDraw a card.",
)

MMMENON_THE_RIGHT_HAND = make_creature(
    name="Mm'menon, the Right Hand",
    power=3, toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Advisor", "Jellyfish"},
    supertypes={"Legendary"},
    text="Flying\nYou may look at the top card of your library any time.\nYou may cast artifact spells from the top of your library.\nArtifacts you control have \"{T}: Add {U}. Spend this mana only to cast a spell from anywhere other than your hand.\"",
)

MOONLIT_MEDITATION = make_enchantment(
    name="Moonlit Meditation",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Enchant artifact or creature you control\nThe first time you would create one or more tokens each turn, you may instead create that many tokens that are copies of enchanted permanent.",
    subtypes={"Aura"},
)

MOUTH_OF_THE_STORM = make_creature(
    name="Mouth of the Storm",
    power=6, toughness=6,
    mana_cost="{6}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="Flying\nWard {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nWhen this creature enters, creatures your opponents control get -3/-0 until your next turn.",
)

NANOFORM_SENTINEL = make_artifact_creature(
    name="Nanoform Sentinel",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Robot"},
    text="Whenever this creature becomes tapped, untap another target permanent. This ability triggers only once each turn.",
)

QUANTUM_RIDDLER = make_creature(
    name="Quantum Riddler",
    power=4, toughness=6,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Sphinx"},
    text="Flying\nWhen this creature enters, draw a card.\nAs long as you have one or fewer cards in hand, if you would draw one or more cards, you draw that many cards plus one instead.\nWarp {1}{U}",
)

SCOUR_FOR_SCRAP = make_instant(
    name="Scour for Scrap",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Choose one or both —\n• Search your library for an artifact card, reveal it, put it into your hand, then shuffle.\n• Return target artifact card from your graveyard to your hand.",
)

SELFCRAFT_MECHAN = make_artifact_creature(
    name="Selfcraft Mechan",
    power=3, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Artificer", "Robot"},
    text="When this creature enters, you may sacrifice an artifact. When you do, put a +1/+1 counter on target creature and draw a card.",
)

SINISTER_CRYOLOGIST = make_creature(
    name="Sinister Cryologist",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Jellyfish", "Wizard"},
    text="When this creature enters, target creature an opponent controls gets -3/-0 until end of turn.\nWarp {U} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

SPECIMEN_FREIGHTER = make_artifact(
    name="Specimen Freighter",
    mana_cost="{5}{U}",
    text="When this Spacecraft enters, return up to two target non-Spacecraft creatures to their owners' hands.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 9+.)\n9+ | Flying\nWhenever this Spacecraft attacks, defending player mills four cards.",
    subtypes={"Spacecraft"},
)

STARBREACH_WHALE = make_creature(
    name="Starbreach Whale",
    power=3, toughness=5,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Whale"},
    text="Flying\nWhen this creature enters, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\nWarp {1}{U} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

STARFIELD_VOCALIST = make_creature(
    name="Starfield Vocalist",
    power=3, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Bard", "Human"},
    text="If a permanent entering the battlefield causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.\nWarp {1}{U} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

STARWINDER = make_creature(
    name="Starwinder",
    power=7, toughness=7,
    mana_cost="{5}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Leviathan"},
    text="Whenever a creature you control deals combat damage to a player, you may draw that many cards.\nWarp {2}{U}{U} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

STEELSWARM_OPERATOR = make_artifact_creature(
    name="Steelswarm Operator",
    power=1, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Robot", "Soldier"},
    text="Flying\n{T}: Add {U}. Spend this mana only to cast an artifact spell.\n{T}: Add {U}{U}. Spend this mana only to activate abilities of artifact sources.",
)

SYNTHESIZER_LABSHIP = make_artifact(
    name="Synthesizer Labship",
    mana_cost="{U}",
    text="Station (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 9+.)\n2+ | At the beginning of combat on your turn, up to one other target artifact you control becomes an artifact creature with base power and toughness 2/2 and gains flying until end of turn.\n9+ | Flying, vigilance",
    subtypes={"Spacecraft"},
)

TRACTOR_BEAM = make_enchantment(
    name="Tractor Beam",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Enchant creature or Spacecraft\nWhen this Aura enters, tap enchanted permanent.\nYou control enchanted permanent.\nEnchanted permanent doesn't untap during its controller's untap step.",
    subtypes={"Aura"},
)

UNRAVEL = make_instant(
    name="Unravel",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell. If the amount of mana spent to cast that spell was less than its mana value, you draw a card.",
)

UTHROS_PSIONICIST = make_creature(
    name="Uthros Psionicist",
    power=2, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Jellyfish", "Scientist"},
    text="The second spell you cast each turn costs {2} less to cast.",
)

UTHROS_SCANSHIP = make_artifact(
    name="Uthros Scanship",
    mana_cost="{3}{U}",
    text="When this Spacecraft enters, draw two cards, then discard a card.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 8+.)\n8+ | Flying",
    subtypes={"Spacecraft"},
)

WEFTWALKING = make_enchantment(
    name="Weftwalking",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="When this enchantment enters, if you cast it, shuffle your hand and graveyard into your library, then draw seven cards.\nThe first spell each player casts during each of their turns may be cast without paying its mana cost.",
)

ALPHARAEL_STONECHOSEN = make_creature(
    name="Alpharael, Stonechosen",
    power=3, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Human"},
    supertypes={"Legendary"},
    text="Ward—Discard a card at random.\nVoid — Whenever Alpharael attacks, if a nonland permanent left the battlefield this turn or a spell was warped this turn, defending player loses half their life, rounded up.",
)

ARCHENEMYS_CHARM = make_instant(
    name="Archenemy's Charm",
    mana_cost="{B}{B}{B}",
    colors={Color.BLACK},
    text="Choose one —\n• Exile target creature or planeswalker.\n• Return one or two target creature and/or planeswalker cards from your graveyard to your hand.\n• Put two +1/+1 counters on target creature you control. It gains lifelink until end of turn.",
)

BEAMSAW_PROSPECTOR = make_creature(
    name="Beamsaw Prospector",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Artificer", "Human"},
    text="When this creature dies, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

BLADE_OF_THE_SWARM = make_creature(
    name="Blade of the Swarm",
    power=3, toughness=1,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Insect"},
    text="When this creature enters, choose one —\n• Put two +1/+1 counters on this creature.\n• Put target exiled card with warp on the bottom of its owner's library.",
)

CHORALE_OF_THE_VOID = make_enchantment(
    name="Chorale of the Void",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Enchant creature you control\nWhenever enchanted creature attacks, put target creature card from defending player's graveyard onto the battlefield under your control tapped and attacking.\nVoid — At the beginning of your end step, sacrifice this Aura unless a nonland permanent left the battlefield this turn or a spell was warped this turn.",
    subtypes={"Aura"},
)

COMET_CRAWLER = make_creature(
    name="Comet Crawler",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Insect"},
    text="Lifelink\nWhenever this creature attacks, you may sacrifice another creature or artifact. If you do, this creature gets +2/+0 until end of turn.",
)

DARK_ENDURANCE = make_instant(
    name="Dark Endurance",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="This spell costs {1} less to cast if it targets a blocking creature.\nTarget creature gets +2/+0 and gains indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)",
)

DECODE_TRANSMISSIONS = make_sorcery(
    name="Decode Transmissions",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="You draw two cards and lose 2 life.\nVoid — If a nonland permanent left the battlefield this turn or a spell was warped this turn, instead you draw two cards and each opponent loses 2 life.",
)

DEPRESSURIZE = make_instant(
    name="Depressurize",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -3/-0 until end of turn. Then if that creature's power is 0 or less, destroy it.",
)

DUBIOUS_DELICACY = make_artifact(
    name="Dubious Delicacy",
    mana_cost="{2}{B}",
    text="Flash\nWhen this artifact enters, up to one target creature gets -3/-3 until end of turn.\n{2}, {T}, Sacrifice this artifact: You gain 3 life.\n{2}, {T}, Sacrifice this artifact: Target opponent loses 3 life.",
    subtypes={"Food"},
)

ELEGY_ACOLYTE = make_creature(
    name="Elegy Acolyte",
    power=4, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Human"},
    text="Lifelink\nWhenever one or more creatures you control deal combat damage to a player, you draw a card and lose 1 life.\nVoid — At the beginning of your end step, if a nonland permanent left the battlefield this turn or a spell was warped this turn, create a 2/2 colorless Robot artifact creature token.",
)

EMBRACE_OBLIVION = make_sorcery(
    name="Embrace Oblivion",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, sacrifice an artifact or creature.\nDestroy target creature or Spacecraft.",
)

ENTROPIC_BATTLECRUISER = make_artifact(
    name="Entropic Battlecruiser",
    mana_cost="{3}{B}",
    text="Station (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 8+.)\n1+ | Whenever an opponent discards a card, they lose 3 life.\n8+ | Flying, deathtouch\nWhenever this Spacecraft attacks, each opponent discards a card. Each opponent who can't loses 3 life.",
    subtypes={"Spacecraft"},
)

FALLERS_FAITHFUL = make_creature(
    name="Faller's Faithful",
    power=3, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard"},
    text="When this creature enters, destroy up to one other target creature. If that creature wasn't dealt damage this turn, its controller draws two cards.",
)

FELL_GRAVSHIP = make_artifact(
    name="Fell Gravship",
    mana_cost="{2}{B}",
    text="When this Spacecraft enters, mill three cards, then return a creature or Spacecraft card from your graveyard to your hand.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 8+.)\n8+ | Flying, lifelink",
    subtypes={"Spacecraft"},
)

GRAVBLADE_HEAVY = make_creature(
    name="Gravblade Heavy",
    power=3, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    text="As long as you control an artifact, this creature gets +1/+0 and has deathtouch.",
)

GRAVKILL = make_instant(
    name="Gravkill",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Exile target creature or Spacecraft.",
)

GRAVPACK_MONOIST = make_creature(
    name="Gravpack Monoist",
    power=2, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Scout"},
    text="Flying\nWhen this creature dies, create a tapped 2/2 colorless Robot artifact creature token.",
)

HULLCARVER = make_artifact_creature(
    name="Hullcarver",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Robot"},
    text="Deathtouch",
)

HYLDERBLADE = make_artifact(
    name="Hylderblade",
    mana_cost="{B}",
    text="Equipped creature gets +3/+1.\nVoid — At the beginning of your end step, if a nonland permanent left the battlefield this turn or a spell was warped this turn, attach this Equipment to target creature you control.\nEquip {4} ({4}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

HYMN_OF_THE_FALLER = make_sorcery(
    name="Hymn of the Faller",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Surveil 1, then you draw a card and lose 1 life. (To surveil 1, look at the top card of your library. You may put it into your graveyard.)\nVoid — If a nonland permanent left the battlefield this turn or a spell was warped this turn, draw another card.",
)

INSATIABLE_SKITTERMAW = make_creature(
    name="Insatiable Skittermaw",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Insect"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nVoid — At the beginning of your end step, if a nonland permanent left the battlefield this turn or a spell was warped this turn, put a +1/+1 counter on this creature.",
)

LIGHTLESS_EVANGEL = make_creature(
    name="Lightless Evangel",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Vampire"},
    text="Whenever you sacrifice another creature or artifact, put a +1/+1 counter on this creature.",
)

MONOIST_CIRCUITFEEDER = make_artifact_creature(
    name="Monoist Circuit-Feeder",
    power=4, toughness=4,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Nautilus"},
    text="Flying\nWhen this creature enters, until end of turn, target creature you control gets +X/+0 and target creature an opponent controls gets -0/-X, where X is the number of artifacts you control.",
)

MONOIST_SENTRY = make_artifact_creature(
    name="Monoist Sentry",
    power=4, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Robot"},
    text="Defender",
)

PERIGEE_BECKONER = make_creature(
    name="Perigee Beckoner",
    power=4, toughness=5,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="When this creature enters, until end of turn, another target creature you control gets +2/+0 and gains \"When this creature dies, return it to the battlefield tapped under its owner's control.\"\nWarp {1}{B} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

REQUIEM_MONOLITH = make_artifact(
    name="Requiem Monolith",
    mana_cost="{2}{B}",
    text="{T}: Until end of turn, target creature gains \"Whenever this creature is dealt damage, you draw that many cards and lose that much life.\" That creature's controller may have this artifact deal 1 damage to it. Activate only as a sorcery.",
)

SCROUNGE_FOR_ETERNITY = make_sorcery(
    name="Scrounge for Eternity",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, sacrifice an artifact or creature.\nReturn target creature or Spacecraft card with mana value 5 or less from your graveyard to the battlefield. Then create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

SOTHERA_THE_SUPERVOID = make_enchantment(
    name="Sothera, the Supervoid",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Whenever a creature you control dies, each opponent chooses a creature they control and exiles it.\nAt the beginning of your end step, if a player controls no creatures, sacrifice Sothera, then put a creature card exiled with it onto the battlefield under your control with two additional +1/+1 counters on it.",
    supertypes={"Legendary"},
)

SUNSET_SABOTEUR = make_creature(
    name="Sunset Saboteur",
    power=4, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="Menace\nWard—Discard a card.\nWhenever this creature attacks, put a +1/+1 counter on target creature an opponent controls.",
)

SUSURIAN_DIRGECRAFT = make_artifact(
    name="Susurian Dirgecraft",
    mana_cost="{4}{B}",
    text="When this Spacecraft enters, each opponent sacrifices a nontoken creature of their choice.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 7+.)\n7+ | Flying",
    subtypes={"Spacecraft"},
)

SUSURIAN_VOIDBORN = make_creature(
    name="Susurian Voidborn",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Soldier", "Vampire"},
    text="Whenever this creature or another creature or artifact you control dies, target opponent loses 1 life and you gain 1 life.\nWarp {B} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

SWARM_CULLER = make_creature(
    name="Swarm Culler",
    power=2, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Insect", "Warrior"},
    text="Flying\nWhenever this creature becomes tapped, you may sacrifice another creature or artifact. If you do, draw a card.",
)

TEMPORAL_INTERVENTION = make_sorcery(
    name="Temporal Intervention",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Void — This spell costs {2} less to cast if a nonland permanent left the battlefield this turn or a spell was warped this turn.\nTarget opponent reveals their hand. You choose a nonland card from it. That player discards that card.",
)

TIMELINE_CULLER = make_creature(
    name="Timeline Culler",
    power=2, toughness=2,
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    subtypes={"Drix", "Warlock"},
    text="Haste\nYou may cast this card from your graveyard using its warp ability.\nWarp—{B}, Pay 2 life. (You may cast this card from your hand or graveyard for its warp cost. If you do, exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

TRAGIC_TRAJECTORY = make_sorcery(
    name="Tragic Trajectory",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn.\nVoid — That creature gets -10/-10 until end of turn instead if a nonland permanent left the battlefield this turn or a spell was warped this turn.",
)

UMBRAL_COLLAR_ZEALOT = make_creature(
    name="Umbral Collar Zealot",
    power=3, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Human"},
    text="Sacrifice another creature or artifact: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

VIRUS_BEETLE = make_artifact_creature(
    name="Virus Beetle",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Insect"},
    text="When this creature enters, each opponent discards a card.",
)

VOIDFORGED_TITAN = make_artifact_creature(
    name="Voidforged Titan",
    power=5, toughness=4,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Robot", "Warrior"},
    text="Void — At the beginning of your end step, if a nonland permanent left the battlefield this turn or a spell was warped this turn, you draw a card and lose 1 life.",
)

VOTE_OUT = make_sorcery(
    name="Vote Out",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nDestroy target creature.",
)

XUIFIT_OSTEOHARMONIST = make_creature(
    name="Xu-Ifit, Osteoharmonist",
    power=2, toughness=3,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="{T}: Return target creature card from your graveyard to the battlefield. It's a Skeleton in addition to its other types and has no abilities. Activate only as a sorcery.",
)

ZERO_POINT_BALLAD = make_sorcery(
    name="Zero Point Ballad",
    mana_cost="{X}{B}",
    colors={Color.BLACK},
    text="Destroy all creatures with toughness X or less. You lose X life. If X is 6 or more, return a creature card put into a graveyard this way to the battlefield under your control.",
)

BOMBARD = make_instant(
    name="Bombard",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Bombard deals 4 damage to target creature.",
)

CUT_PROPULSION = make_instant(
    name="Cut Propulsion",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Target creature deals damage to itself equal to its power. If that creature has flying, it deals twice that much damage to itself instead.",
)

DEBRIS_FIELD_CRUSHER = make_artifact(
    name="Debris Field Crusher",
    mana_cost="{4}{R}",
    text="When this Spacecraft enters, it deals 3 damage to any target.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 8+.)\n8+ | Flying\n{1}{R}: This Spacecraft gets +2/+0 until end of turn.",
    subtypes={"Spacecraft"},
)

DEVASTATING_ONSLAUGHT = make_sorcery(
    name="Devastating Onslaught",
    mana_cost="{X}{X}{R}",
    colors={Color.RED},
    text="Create X tokens that are copies of target artifact or creature you control. Those tokens gain haste until end of turn. Sacrifice them at the beginning of the next end step.",
)

DRILL_TOO_DEEP = make_instant(
    name="Drill Too Deep",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Choose one —\n• Put five charge counters on target Spacecraft or Planet you control.\n• Destroy target artifact.",
)

FRONTLINE_WARRAGER = make_creature(
    name="Frontline War-Rager",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Kavu", "Soldier"},
    text="At the beginning of your end step, if you control two or more tapped creatures, put a +1/+1 counter on this creature.",
)

FULL_BORE = make_instant(
    name="Full Bore",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature you control gets +3/+2 until end of turn. If that creature was cast for its warp cost, it also gains trample and haste until end of turn.",
)

GALVANIZING_SAWSHIP = make_artifact(
    name="Galvanizing Sawship",
    mana_cost="{5}{R}",
    text="Station (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 3+.)\n3+ | Flying, haste",
    subtypes={"Spacecraft"},
)

INVASIVE_MANEUVERS = make_instant(
    name="Invasive Maneuvers",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Invasive Maneuvers deals 3 damage to target creature. It deals 5 damage instead if you control a Spacecraft.",
)

KAV_LANDSEEKER = make_creature(
    name="Kav Landseeker",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Kavu", "Soldier"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhen this creature enters, create a Lander token. At the beginning of the end step on your next turn, sacrifice that token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

KAVARON_HARRIER = make_artifact_creature(
    name="Kavaron Harrier",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Robot", "Soldier"},
    text="Whenever this creature attacks, you may pay {2}. If you do, create a 2/2 colorless Robot artifact creature token that's tapped and attacking. Sacrifice that token at end of combat.",
)

KAVARON_SKYWARDEN = make_creature(
    name="Kavaron Skywarden",
    power=4, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Kavu", "Soldier"},
    text="Reach\nVoid — At the beginning of your end step, if a nonland permanent left the battlefield this turn or a spell was warped this turn, put a +1/+1 counter on this creature.",
)

KAVARON_TURBODRONE = make_artifact_creature(
    name="Kavaron Turbodrone",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Robot", "Scout"},
    text="{T}: Target creature you control gets +1/+1 and gains haste until end of turn. Activate only as a sorcery.",
)

LITHOBRAKING = make_instant(
    name="Lithobraking",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Create a Lander token. Then you may sacrifice an artifact. When you do, Lithobraking deals 2 damage to each creature. (A Lander token is an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

MELDED_MOXITE = make_artifact(
    name="Melded Moxite",
    mana_cost="{1}{R}",
    text="When this artifact enters, you may discard a card. If you do, draw two cards.\n{3}, Sacrifice this artifact: Create a tapped 2/2 colorless Robot artifact creature token.",
)

MEMORIAL_TEAM_LEADER = make_creature(
    name="Memorial Team Leader",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Kavu", "Soldier"},
    text="During your turn, other creatures you control get +1/+0.\nWarp {1}{R} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

MEMORIAL_VAULT = make_artifact(
    name="Memorial Vault",
    mana_cost="{3}{R}",
    text="{T}, Sacrifice another artifact: Exile the top X cards of your library, where X is one plus the mana value of the sacrificed artifact. You may play those cards this turn.",
)

MOLECULAR_MODIFIER = make_creature(
    name="Molecular Modifier",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Artificer", "Kavu"},
    text="At the beginning of combat on your turn, target creature you control gets +1/+0 and gains first strike until end of turn.",
)

NEBULA_DRAGON = make_creature(
    name="Nebula Dragon",
    power=4, toughness=4,
    mana_cost="{6}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\nWhen this creature enters, it deals 3 damage to any target.",
)

NOVA_HELLKITE = make_creature(
    name="Nova Hellkite",
    power=4, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying, haste\nWhen this creature enters, it deals 1 damage to target creature an opponent controls.\nWarp {2}{R} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

ORBITAL_PLUNGE = make_sorcery(
    name="Orbital Plunge",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Orbital Plunge deals 6 damage to target creature. If excess damage was dealt this way, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

OREPLATE_PANGOLIN = make_artifact_creature(
    name="Oreplate Pangolin",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Pangolin", "Robot"},
    text="Whenever another artifact you control enters, you may pay {1}. If you do, put a +1/+1 counter on this creature.",
)

PAIN_FOR_ALL = make_enchantment(
    name="Pain for All",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Enchant creature you control\nWhen this Aura enters, enchanted creature deals damage equal to its power to any other target.\nWhenever enchanted creature is dealt damage, it deals that much damage to each opponent.",
    subtypes={"Aura"},
)

PLASMA_BOLT = make_sorcery(
    name="Plasma Bolt",
    mana_cost="{R}",
    colors={Color.RED},
    text="Plasma Bolt deals 2 damage to any target.\nVoid — Plasma Bolt deals 3 damage instead if a nonland permanent left the battlefield this turn or a spell was warped this turn.",
)

POSSIBILITY_TECHNICIAN = make_creature(
    name="Possibility Technician",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Artificer", "Kavu"},
    text="Whenever this creature or another Kavu you control enters, exile the top card of your library. For as long as that card remains exiled, you may play it if you control a Kavu.\nWarp {1}{R} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

RED_TIGER_MECHAN = make_artifact_creature(
    name="Red Tiger Mechan",
    power=3, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Cat", "Robot"},
    text="Haste\nWarp {1}{R} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

REMNANT_ELEMENTAL = make_creature(
    name="Remnant Elemental",
    power=0, toughness=4,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Reach\nLandfall — Whenever a land you control enters, this creature gets +2/+0 until end of turn.",
)

RIG_FOR_WAR = make_instant(
    name="Rig for War",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains first strike and reach until end of turn.",
)

ROVING_ACTUATOR = make_artifact_creature(
    name="Roving Actuator",
    power=3, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Robot"},
    text="Void — When this creature enters, if a nonland permanent left the battlefield this turn or a spell was warped this turn, exile up to one target instant or sorcery card with mana value 2 or less from your graveyard. Copy it. You may cast the copy without paying its mana cost.",
)

RUINOUS_RAMPAGE = make_sorcery(
    name="Ruinous Rampage",
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    text="Choose one —\n• Ruinous Rampage deals 3 damage to each opponent.\n• Exile all artifacts with mana value 3 or less.",
)

RUST_HARVESTER = make_artifact_creature(
    name="Rust Harvester",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Robot"},
    text="Menace\n{2}, {T}, Exile an artifact card from your graveyard: Put a +1/+1 counter on this creature, then it deals damage equal to its power to any target.",
)

SLAGDRILL_SCRAPPER = make_artifact_creature(
    name="Slagdrill Scrapper",
    power=1, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Robot", "Scout"},
    text="{2}, {T}, Sacrifice another artifact or land: Draw a card.",
)

SYSTEMS_OVERRIDE = make_sorcery(
    name="Systems Override",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Gain control of target artifact or creature until end of turn. Untap that permanent. It gains haste until end of turn. If it's a Spacecraft, put ten charge counters on it. If you do, remove ten charge counters from it at the beginning of the next end step.",
)

TANNUK_STEADFAST_SECOND = make_creature(
    name="Tannuk, Steadfast Second",
    power=3, toughness=5,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Kavu", "Pilot"},
    supertypes={"Legendary"},
    text="Other creatures you control have haste.\nArtifact cards and red creature cards in your hand have warp {2}{R}. (You may cast a card from your hand for its warp cost. Exile that permanent at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

TERMINAL_VELOCITY = make_sorcery(
    name="Terminal Velocity",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="You may put an artifact or creature card from your hand onto the battlefield. That permanent gains haste, \"When this permanent leaves the battlefield, it deals damage equal to its mana value to each creature,\" and \"At the beginning of your end step, sacrifice this permanent.\"",
)

TERRAPACT_INTIMIDATOR = make_creature(
    name="Terrapact Intimidator",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Kavu", "Scout"},
    text="When this creature enters, target opponent may have you create two Lander tokens. If they don't, put two +1/+1 counters on this creature. (A Lander token is an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

TERRITORIAL_BRUNTAR = make_creature(
    name="Territorial Bruntar",
    power=6, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Beast"},
    text="Reach\nLandfall — Whenever a land you control enters, exile cards from the top of your library until you exile a nonland card. You may cast that card this turn.",
)

VAULTGUARD_TROOPER = make_creature(
    name="Vaultguard Trooper",
    power=5, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Kavu", "Soldier"},
    text="At the beginning of your end step, if you control two or more tapped creatures, you may discard your hand. If you do, draw two cards.",
)

WARMAKER_GUNSHIP = make_artifact(
    name="Warmaker Gunship",
    mana_cost="{2}{R}",
    text="When this Spacecraft enters, it deals damage equal to the number of artifacts you control to target creature an opponent controls.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 6+.)\n6+ | Flying",
    subtypes={"Spacecraft"},
)

WEAPONS_MANUFACTURING = make_enchantment(
    name="Weapons Manufacturing",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Whenever a nontoken artifact you control enters, create a colorless artifact token named Munitions with \"When this token leaves the battlefield, it deals 2 damage to any target.\"",
)

WEFTSTALKER_ARDENT = make_creature(
    name="Weftstalker Ardent",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Artificer", "Drix"},
    text="Whenever another creature or artifact you control enters, this creature deals 1 damage to each opponent.\nWarp {R} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

ZOOKEEPER_MECHAN = make_artifact_creature(
    name="Zookeeper Mechan",
    power=1, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Robot"},
    text="{T}: Add {R}.\n{6}{R}: Target creature you control gets +4/+0 until end of turn. Activate only as a sorcery.",
)

ATMOSPHERIC_GREENHOUSE = make_artifact(
    name="Atmospheric Greenhouse",
    mana_cost="{4}{G}",
    text="When this Spacecraft enters, put a +1/+1 counter on each creature you control.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 8+.)\n8+ | Flying, trample",
    subtypes={"Spacecraft"},
)

BIOENGINEERED_FUTURE = make_enchantment(
    name="Bioengineered Future",
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")\nEach creature you control enters with an additional +1/+1 counter on it for each land that entered the battlefield under your control this turn.",
)

BIOSYNTHIC_BURST = make_instant(
    name="Biosynthic Burst",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Put a +1/+1 counter on target creature you control. It gains reach, trample, and indestructible until end of turn. Untap it. (Damage and effects that say \"destroy\" don't destroy it.)",
)

BLOOMING_STINGER = make_creature(
    name="Blooming Stinger",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Scorpion"},
    text="Deathtouch\nWhen this creature enters, another target creature you control gains deathtouch until end of turn.",
)

BROODGUARD_ELITE = make_creature(
    name="Broodguard Elite",
    power=0, toughness=0,
    mana_cost="{X}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Insect", "Knight"},
    text="This creature enters with X +1/+1 counters on it.\nWhen this creature leaves the battlefield, put its counters on target creature you control.\nWarp {X}{G} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

CLOSE_ENCOUNTER = make_instant(
    name="Close Encounter",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="As an additional cost to cast this spell, choose a creature you control or a warped creature card you own in exile.\nClose Encounter deals damage equal to the power of the chosen creature or card to target creature.",
)

DIPLOMATIC_RELATIONS = make_instant(
    name="Diplomatic Relations",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +1/+0 and gains vigilance until end of turn. It deals damage equal to its power to target creature an opponent controls.",
)

DRIX_FATEMAKER = make_creature(
    name="Drix Fatemaker",
    power=3, toughness=2,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Drix", "Wizard"},
    text="When this creature enters, put a +1/+1 counter on target creature.\nEach creature you control with a +1/+1 counter on it has trample.\nWarp {1}{G} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

EDGE_ROVER = make_artifact_creature(
    name="Edge Rover",
    power=2, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Robot", "Scout"},
    text="Reach\nWhen this creature dies, each player creates a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

EUMIDIAN_TERRABOTANIST = make_creature(
    name="Eumidian Terrabotanist",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Insect"},
    text="Landfall — Whenever a land you control enters, you gain 1 life.",
)

EUSOCIAL_ENGINEERING = make_enchantment(
    name="Eusocial Engineering",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Landfall — Whenever a land you control enters, create a 2/2 colorless Robot artifact creature token.\nWarp {1}{G} (You may cast this card from your hand for its warp cost. Exile this enchantment at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

FAMISHED_WORLDSIRE = make_creature(
    name="Famished Worldsire",
    power=0, toughness=0,
    mana_cost="{5}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Leviathan"},
    text="Ward {3}\nDevour land 3 (As this creature enters, you may sacrifice any number of lands. It enters with three times that many +1/+1 counters on it.)\nWhen this creature enters, look at the top X cards of your library, where X is this creature's power. Put any number of land cards from among them onto the battlefield tapped, then shuffle.",
)

FRENZIED_BALOTH = make_creature(
    name="Frenzied Baloth",
    power=3, toughness=2,
    mana_cost="{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="This spell can't be countered.\nTrample, haste\nCreature spells you control can't be countered.\nCombat damage can't be prevented.",
)

FUNGAL_COLOSSUS = make_creature(
    name="Fungal Colossus",
    power=5, toughness=5,
    mana_cost="{6}{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Fungus"},
    text="This spell costs {X} less to cast, where X is the number of differently named lands you control.",
)

GALACTIC_WAYFARER = make_creature(
    name="Galactic Wayfarer",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout"},
    text="When this creature enters, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

GENE_POLLINATOR = make_artifact_creature(
    name="Gene Pollinator",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Insect", "Robot"},
    text="{T}, Tap an untapped permanent you control: Add one mana of any color.",
)

GERMINATING_WURM = make_creature(
    name="Germinating Wurm",
    power=5, toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Wurm"},
    text="When this creature enters, you gain 2 life.\nWarp {1}{G} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

GLACIER_GODMAW = make_creature(
    name="Glacier Godmaw",
    power=6, toughness=6,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Leviathan"},
    text="Trample\nWhen this creature enters, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")\nLandfall — Whenever a land you control enters, creatures you control get +1/+1 and gain vigilance and haste until end of turn.",
)

HARMONIOUS_GROVESTRIDER = make_creature(
    name="Harmonious Grovestrider",
    power=0, toughness=0,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Ward {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nHarmonious Grovestrider's power and toughness are each equal to the number of lands you control.",
)

HEMOSYMBIC_MITE = make_creature(
    name="Hemosymbic Mite",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Mite"},
    text="Whenever this creature becomes tapped, another target creature you control gets +X/+X until end of turn, where X is this creature's power.",
)

ICECAVE_CRASHER = make_creature(
    name="Icecave Crasher",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample\nLandfall — Whenever a land you control enters, this creature gets +1/+0 until end of turn.",
)

ICETILL_EXPLORER = make_creature(
    name="Icetill Explorer",
    power=2, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Insect", "Scout"},
    text="You may play an additional land on each of your turns.\nYou may play lands from your graveyard.\nLandfall — Whenever a land you control enters, mill a card.",
)

INTREPID_TENDERFOOT = make_creature(
    name="Intrepid Tenderfoot",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Citizen", "Insect"},
    text="{3}: Put a +1/+1 counter on this creature. Activate only as a sorcery.",
)

LARVAL_SCOUTLANDER = make_artifact(
    name="Larval Scoutlander",
    mana_cost="{2}{G}",
    text="When this Spacecraft enters, you may sacrifice a land or Lander. If you do, search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 7+.)\n7+ | Flying",
    subtypes={"Spacecraft"},
)

LASHWHIP_PREDATOR = make_creature(
    name="Lashwhip Predator",
    power=5, toughness=7,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Plant"},
    text="This spell costs {2} less to cast if your opponents control three or more creatures.\nReach",
)

LOADING_ZONE = make_enchantment(
    name="Loading Zone",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="If one or more counters would be put on a creature, Spacecraft, or Planet you control, twice that many of each of those kinds of counters are put on it instead.\nWarp {G} (You may cast this card from your hand for its warp cost. Exile this enchantment at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

MELTSTRIDER_EULOGIST = make_creature(
    name="Meltstrider Eulogist",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Insect", "Soldier"},
    text="Whenever a creature you control with a +1/+1 counter on it dies, draw a card.",
)

MELTSTRIDERS_GEAR = make_artifact(
    name="Meltstrider's Gear",
    mana_cost="{G}",
    text="When this Equipment enters, attach it to target creature you control.\nEquipped creature gets +2/+1 and has reach.\nEquip {5} ({5}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

MELTSTRIDERS_RESOLVE = make_enchantment(
    name="Meltstrider's Resolve",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Enchant creature you control\nWhen this Aura enters, enchanted creature fights up to one target creature an opponent controls. (Each deals damage equal to its power to the other.)\nEnchanted creature gets +0/+2 and can't be blocked by more than one creature.",
    subtypes={"Aura"},
)

MIGHTFORM_HARMONIZER = make_creature(
    name="Mightform Harmonizer",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Insect"},
    text="Landfall — Whenever a land you control enters, double the power of target creature you control until end of turn.\nWarp {2}{G} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

OUROBOROID = make_creature(
    name="Ouroboroid",
    power=1, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Wurm"},
    text="At the beginning of combat on your turn, put X +1/+1 counters on each creature you control, where X is this creature's power.",
)

PULL_THROUGH_THE_WEFT = make_sorcery(
    name="Pull Through the Weft",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Return up to two target nonland permanent cards from your graveyard to your hand, then return up to two target land cards from your graveyard to the battlefield tapped.",
)

SAMIS_CURIOSITY = make_sorcery(
    name="Sami's Curiosity",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="You gain 2 life. Create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

SEEDSHIP_AGRARIAN = make_creature(
    name="Seedship Agrarian",
    power=3, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Insect", "Scientist"},
    text="Whenever this creature becomes tapped, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")\nLandfall — Whenever a land you control enters, put a +1/+1 counter on this creature.",
)

SEEDSHIP_IMPACT = make_instant(
    name="Seedship Impact",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Destroy target artifact or enchantment. If its mana value was 2 or less, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

SHATTERED_WINGS = make_sorcery(
    name="Shattered Wings",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Destroy target artifact, enchantment, or creature with flying. Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

SKYSTINGER = make_creature(
    name="Skystinger",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Insect", "Warrior"},
    text="Reach\nWhenever this creature blocks a creature with flying, this creature gets +5/+0 until end of turn.",
)

SLEDGECLASS_SEEDSHIP = make_artifact(
    name="Sledge-Class Seedship",
    mana_cost="{2}{G}",
    text="Station (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 7+.)\n7+ | Flying\nWhenever this Spacecraft attacks, you may put a creature card from your hand onto the battlefield.",
    subtypes={"Spacecraft"},
)

TAPESTRY_WARDEN = make_artifact_creature(
    name="Tapestry Warden",
    power=3, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Robot", "Soldier"},
    text="Vigilance\nEach creature you control with toughness greater than its power assigns combat damage equal to its toughness rather than its power.\nEach creature you control with toughness greater than its power stations permanents using its toughness rather than its power.",
)

TERRASYMBIOSIS = make_enchantment(
    name="Terrasymbiosis",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Whenever you put one or more +1/+1 counters on a creature you control, you may draw that many cards. Do this only once each turn.",
)

THAWBRINGER = make_creature(
    name="Thawbringer",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Insect", "Scout"},
    text="When this creature enters or dies, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

ALPHARAEL_DREAMING_ACOLYTE = make_creature(
    name="Alpharael, Dreaming Acolyte",
    power=2, toughness=3,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Cleric", "Human"},
    supertypes={"Legendary"},
    text="When Alpharael enters, draw two cards. Then discard two cards unless you discard an artifact card.\nDuring your turn, Alpharael has deathtouch.",
)

BIOMECHAN_ENGINEER = make_creature(
    name="Biomechan Engineer",
    power=2, toughness=2,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Artificer", "Insect"},
    text="When this creature enters, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")\n{8}: Draw two cards and create a 2/2 colorless Robot artifact creature token.",
)

BIOTECH_SPECIALIST = make_creature(
    name="Biotech Specialist",
    power=1, toughness=3,
    mana_cost="{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Insect", "Scientist"},
    text="When this creature enters, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")\nWhenever you sacrifice an artifact, this creature deals 2 damage to target opponent.",
)

COSMOGOYF = make_creature(
    name="Cosmogoyf",
    power=0, toughness=0,
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Elemental", "Lhurgoyf"},
    text="Cosmogoyf's power is equal to the number of cards you own in exile and its toughness is equal to that number plus 1.",
)

DYADRINE_SYNTHESIS_AMALGAM = make_artifact_creature(
    name="Dyadrine, Synthesis Amalgam",
    power=0, toughness=1,
    mana_cost="{X}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Construct"},
    supertypes={"Legendary"},
    text="Trample\nDyadrine enters with a number of +1/+1 counters on it equal to the amount of mana spent to cast it.\nWhenever you attack, you may remove a +1/+1 counter from each of two creatures you control. If you do, draw a card and create a 2/2 colorless Robot artifact creature token.",
)

GENEMORPH_IMAGO = make_creature(
    name="Genemorph Imago",
    power=1, toughness=3,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Druid", "Insect"},
    text="Flying\nLandfall — Whenever a land you control enters, target creature has base power and toughness 3/3 until end of turn. If you control six or more lands, that creature has base power and toughness 6/6 until end of turn instead.",
)

HALIYA_ASCENDANT_CADET = make_creature(
    name="Haliya, Ascendant Cadet",
    power=3, toughness=3,
    mana_cost="{2}{G}{W}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Whenever Haliya enters or attacks, put a +1/+1 counter on target creature you control.\nWhenever one or more creatures you control with +1/+1 counters on them deal combat damage to a player, draw a card.",
)

INFINITE_GUIDELINE_STATION = make_artifact(
    name="Infinite Guideline Station",
    mana_cost="{W}{U}{B}{R}{G}",
    text="When Infinite Guideline Station enters, create a tapped 2/2 colorless Robot artifact creature token for each multicolored permanent you control.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 12+.)\n12+ | Flying\nWhenever Infinite Guideline Station attacks, draw a card for each multicolored permanent you control.",
    subtypes={"Spacecraft"},
    supertypes={"Legendary"},
)

INTERCEPTOR_MECHAN = make_artifact_creature(
    name="Interceptor Mechan",
    power=2, toughness=2,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Robot"},
    text="Flying\nWhen this creature enters, return target artifact or creature card from your graveyard to your hand.\nVoid — At the beginning of your end step, if a nonland permanent left the battlefield this turn or a spell was warped this turn, put a +1/+1 counter on this creature.",
)

MMMENON_UTHROS_EXILE = make_creature(
    name="Mm'menon, Uthros Exile",
    power=1, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Advisor", "Jellyfish"},
    supertypes={"Legendary"},
    text="Flying\nWhenever an artifact you control enters, put a +1/+1 counter on target creature.",
)

MUTINOUS_MASSACRE = make_sorcery(
    name="Mutinous Massacre",
    mana_cost="{3}{B}{B}{R}{R}",
    colors={Color.BLACK, Color.RED},
    text="Choose odd or even. Destroy each creature with mana value of the chosen quality. Then gain control of all creatures until end of turn. Untap them. They gain haste until end of turn. (Zero is even.)",
)

PINNACLE_EMISSARY = make_artifact_creature(
    name="Pinnacle Emissary",
    power=3, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Robot"},
    text="Whenever you cast an artifact spell, create a 1/1 colorless Drone artifact creature token with flying and \"This token can block only creatures with flying.\"\nWarp {U/R} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

RAGOST_DEFT_GASTRONAUT = make_creature(
    name="Ragost, Deft Gastronaut",
    power=2, toughness=2,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Citizen", "Lobster"},
    supertypes={"Legendary"},
    text="Artifacts you control are Foods in addition to their other types and have \"{2}, {T}, Sacrifice this artifact: You gain 3 life.\"\n{1}, {T}, Sacrifice a Food: Ragost deals 3 damage to each opponent.\nAt the beginning of each end step, if you gained life this turn, untap Ragost.",
)

SAMI_SHIPS_ENGINEER = make_creature(
    name="Sami, Ship's Engineer",
    power=2, toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Artificer", "Human"},
    supertypes={"Legendary"},
    text="At the beginning of your end step, if you control two or more tapped creatures, create a tapped 2/2 colorless Robot artifact creature token.",
)

SAMI_WILDCAT_CAPTAIN = make_creature(
    name="Sami, Wildcat Captain",
    power=4, toughness=4,
    mana_cost="{4}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Artificer", "Human", "Rogue"},
    supertypes={"Legendary"},
    text="Double strike, vigilance\nSpells you cast have affinity for artifacts. (They cost {1} less to cast for each artifact you control.)",
)

SEEDSHIP_BROODTENDER = make_creature(
    name="Seedship Broodtender",
    power=2, toughness=3,
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Citizen", "Insect"},
    text="When this creature enters, mill three cards. (Put the top three cards of your library into your graveyard.)\n{3}{B}{G}, Sacrifice this creature: Return target creature or Spacecraft card from your graveyard to the battlefield. Activate only as a sorcery.",
)

SINGULARITY_RUPTURE = make_sorcery(
    name="Singularity Rupture",
    mana_cost="{3}{U}{B}{B}",
    colors={Color.BLACK, Color.BLUE},
    text="Destroy all creatures, then any number of target players each mill half their library, rounded down.",
)

SPACETIME_ANOMALY = make_sorcery(
    name="Space-Time Anomaly",
    mana_cost="{2}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    text="Target player mills cards equal to your life total.",
)

STATION_MONITOR = make_creature(
    name="Station Monitor",
    power=2, toughness=2,
    mana_cost="{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Artificer", "Lizard"},
    text="Whenever you cast your second spell each turn, create a 1/1 colorless Drone artifact creature token with flying and \"This token can block only creatures with flying.\"",
)

SYR_VONDAM_SUNSTAR_EXEMPLAR = make_creature(
    name="Syr Vondam, Sunstar Exemplar",
    power=2, toughness=2,
    mana_cost="{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="Vigilance, menace\nWhenever another creature you control dies or is put into exile, put a +1/+1 counter on Syr Vondam and you gain 1 life.\nWhen Syr Vondam dies or is put into exile while its power is 4 or greater, destroy up to one target nonland permanent.",
)

SYR_VONDAM_THE_LUCENT = make_creature(
    name="Syr Vondam, the Lucent",
    power=4, toughness=4,
    mana_cost="{2}{W}{B}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="Deathtouch, lifelink\nWhenever Syr Vondam enters or attacks, other creatures you control get +1/+0 and gain deathtouch until end of turn.",
)

TANNUK_MEMORIAL_ENSIGN = make_creature(
    name="Tannuk, Memorial Ensign",
    power=2, toughness=4,
    mana_cost="{1}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Kavu", "Pilot"},
    supertypes={"Legendary"},
    text="Landfall — Whenever a land you control enters, Tannuk deals 1 damage to each opponent. If this is the second time this ability has resolved this turn, draw a card.",
)

ALLFATES_SCROLL = make_artifact(
    name="All-Fates Scroll",
    mana_cost="{3}",
    text="{T}: Add one mana of any color.\n{7}, {T}, Sacrifice this artifact: Draw X cards, where X is the number of differently named lands you control.",
)

BYGONE_COLOSSUS = make_artifact_creature(
    name="Bygone Colossus",
    power=9, toughness=9,
    mana_cost="{9}",
    colors=set(),
    subtypes={"Giant", "Robot"},
    text="Warp {3} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
)

CHROME_COMPANION = make_artifact_creature(
    name="Chrome Companion",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Dog"},
    text="Whenever this creature becomes tapped, you gain 1 life.\n{2}, {T}: Put target card from a graveyard on the bottom of its owner's library.",
)

DAUNTLESS_SCRAPBOT = make_artifact_creature(
    name="Dauntless Scrapbot",
    power=3, toughness=1,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Robot"},
    text="When this creature enters, exile each opponent's graveyard. Create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

DAWNSIRE_SUNSTAR_DREADNOUGHT = make_artifact(
    name="Dawnsire, Sunstar Dreadnought",
    mana_cost="{5}",
    text="Station (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 20+.)\n10+ | Whenever you attack, Dawnsire deals 100 damage to up to one target creature or planeswalker.\n20+ | Flying",
    subtypes={"Spacecraft"},
    supertypes={"Legendary"},
)

THE_DOMINION_BRACELET = make_artifact(
    name="The Dominion Bracelet",
    mana_cost="{2}",
    text="Equipped creature gets +1/+1 and has \"{15}, Exile The Dominion Bracelet: You control target opponent during their next turn. This ability costs {X} less to activate, where X is this creature's power. Activate only as a sorcery.\" (You see all cards that player could see and make all decisions for them.)\nEquip {1}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
)

THE_ENDSTONE = make_artifact(
    name="The Endstone",
    mana_cost="{7}",
    text="Whenever you play a land or cast a spell, draw a card.\nAt the beginning of your end step, your life total becomes half your starting life total, rounded up.",
    supertypes={"Legendary"},
)

THE_ETERNITY_ELEVATOR = make_artifact(
    name="The Eternity Elevator",
    mana_cost="{5}",
    text="{T}: Add {C}{C}{C}.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery.)\n20+ | {T}: Add X mana of any one color, where X is the number of charge counters on The Eternity Elevator.",
    subtypes={"Spacecraft"},
    supertypes={"Legendary"},
)

EXTINGUISHER_BATTLESHIP = make_artifact(
    name="Extinguisher Battleship",
    mana_cost="{8}",
    text="When this Spacecraft enters, destroy target noncreature permanent. Then this Spacecraft deals 4 damage to each creature.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 5+.)\n5+ | Flying, trample",
    subtypes={"Spacecraft"},
)

NUTRIENT_BLOCK = make_artifact(
    name="Nutrient Block",
    mana_cost="{1}",
    text="Indestructible (Effects that say \"destroy\" don't destroy this artifact.)\n{2}, {T}, Sacrifice this artifact: You gain 3 life.\nWhen this artifact is put into a graveyard from the battlefield, draw a card.",
    subtypes={"Food"},
)

PINNACLE_KILLSHIP = make_artifact(
    name="Pinnacle Kill-Ship",
    mana_cost="{7}",
    text="When this Spacecraft enters, it deals 10 damage to up to one target creature.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 7+.)\n7+ | Flying",
    subtypes={"Spacecraft"},
)

SURVEY_MECHAN = make_artifact_creature(
    name="Survey Mechan",
    power=1, toughness=3,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Robot"},
    text="Flying\nHexproof (This creature can't be the target of spells or abilities your opponents control.)\n{10}, Sacrifice this creature: It deals 3 damage to any target. Target player draws three cards and gains 3 life. This ability costs {X} less to activate, where X is the number of differently named lands you control.",
)

THAUMATON_TORPEDO = make_artifact(
    name="Thaumaton Torpedo",
    mana_cost="{1}",
    text="{6}, {T}, Sacrifice this artifact: Destroy target nonland permanent. This ability costs {3} less to activate if you attacked with a Spacecraft this turn.",
)

THRUMMING_HIVEPOOL = make_artifact(
    name="Thrumming Hivepool",
    mana_cost="{6}",
    text="Affinity for Slivers (This spell costs {1} less to cast for each Sliver you control.)\nSlivers you control have double strike and haste.\nAt the beginning of your upkeep, create two 1/1 colorless Sliver creature tokens.",
)

VIRULENT_SILENCER = make_artifact_creature(
    name="Virulent Silencer",
    power=2, toughness=3,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Assassin", "Robot"},
    text="Whenever a nontoken artifact creature you control deals combat damage to a player, that player gets two poison counters. (A player with ten or more poison counters loses the game.)",
)

WURMWALL_SWEEPER = make_artifact(
    name="Wurmwall Sweeper",
    mana_cost="{2}",
    text="When this Spacecraft enters, surveil 2.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 4+.)\n4+ | Flying",
    subtypes={"Spacecraft"},
)

ADAGIA_WINDSWEPT_BASTION = make_land(
    name="Adagia, Windswept Bastion",
    text="This land enters tapped.\n{T}: Add {W}.\nStation (Tap another creature you control: Put charge counters equal to its power on this Planet. Station only as a sorcery.)\n12+ | {3}{W}, {T}: Create a token that's a copy of target artifact or enchantment you control, except it's legendary. Activate only as a sorcery.",
    subtypes={"Planet"},
)

BREEDING_POOL = make_land(
    name="Breeding Pool",
    text="({T}: Add {G} or {U}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
    subtypes={"Forest", "Island"},
)

COMMAND_BRIDGE = make_land(
    name="Command Bridge",
    text="This land enters tapped.\nWhen this land enters, sacrifice it unless you tap an untapped permanent you control.\n{T}: Add one mana of any color.",
)

EVENDO_WAKING_HAVEN = make_land(
    name="Evendo, Waking Haven",
    text="This land enters tapped.\n{T}: Add {G}.\nStation (Tap another creature you control: Put charge counters equal to its power on this Planet. Station only as a sorcery.)\n12+ | {G}, {T}: Add {G} for each creature you control.",
    subtypes={"Planet"},
)

GODLESS_SHRINE = make_land(
    name="Godless Shrine",
    text="({T}: Add {W} or {B}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
    subtypes={"Plains", "Swamp"},
)

KAVARON_MEMORIAL_WORLD = make_land(
    name="Kavaron, Memorial World",
    text="This land enters tapped.\n{T}: Add {R}.\nStation (Tap another creature you control: Put charge counters equal to its power on this Planet. Station only as a sorcery.)\n12+ | {1}{R}, {T}, Sacrifice a land: Create a 2/2 colorless Robot artifact creature token, then creatures you control get +1/+0 and gain haste until end of turn.",
    subtypes={"Planet"},
)

SACRED_FOUNDRY = make_land(
    name="Sacred Foundry",
    text="({T}: Add {R} or {W}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
    subtypes={"Mountain", "Plains"},
)

SECLUDED_STARFORGE = make_land(
    name="Secluded Starforge",
    text="{T}: Add {C}.\n{2}, {T}, Tap X untapped artifacts you control: Target creature gets +X/+0 until end of turn. Activate only as a sorcery.\n{5}, {T}: Create a 2/2 colorless Robot artifact creature token.",
)

STOMPING_GROUND = make_land(
    name="Stomping Ground",
    text="({T}: Add {R} or {G}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
    subtypes={"Forest", "Mountain"},
)

SUSUR_SECUNDI_VOID_ALTAR = make_land(
    name="Susur Secundi, Void Altar",
    text="This land enters tapped.\n{T}: Add {B}.\nStation (Tap another creature you control: Put charge counters equal to its power on this Planet. Station only as a sorcery.)\n12+ | {1}{B}, {T}, Pay 2 life, Sacrifice a creature: Draw cards equal to the sacrificed creature's power. Activate only as a sorcery.",
    subtypes={"Planet"},
)

UTHROS_TITANIC_GODCORE = make_land(
    name="Uthros, Titanic Godcore",
    text="This land enters tapped.\n{T}: Add {U}.\nStation (Tap another creature you control: Put charge counters equal to its power on this Planet. Station only as a sorcery.)\n12+ | {U}, {T}: Add {U} for each artifact you control.",
    subtypes={"Planet"},
)

WATERY_GRAVE = make_land(
    name="Watery Grave",
    text="({T}: Add {U} or {B}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
    subtypes={"Island", "Swamp"},
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

EDGE_OF_ETERNITIES_CARDS = {
    "Anticausal Vestige": ANTICAUSAL_VESTIGE,
    "Tezzeret, Cruel Captain": TEZZERET_CRUEL_CAPTAIN,
    "All-Fates Stalker": ALLFATES_STALKER,
    "Astelli Reclaimer": ASTELLI_RECLAIMER,
    "Auxiliary Boosters": AUXILIARY_BOOSTERS,
    "Banishing Light": BANISHING_LIGHT,
    "Beyond the Quiet": BEYOND_THE_QUIET,
    "Brightspear Zealot": BRIGHTSPEAR_ZEALOT,
    "Cosmogrand Zenith": COSMOGRAND_ZENITH,
    "Dawnstrike Vanguard": DAWNSTRIKE_VANGUARD,
    "Dockworker Drone": DOCKWORKER_DRONE,
    "Dual-Sun Adepts": DUALSUN_ADEPTS,
    "Dual-Sun Technique": DUALSUN_TECHNIQUE,
    "Emergency Eject": EMERGENCY_EJECT,
    "Exalted Sunborn": EXALTED_SUNBORN,
    "Exosuit Savior": EXOSUIT_SAVIOR,
    "Flight-Deck Coordinator": FLIGHTDECK_COORDINATOR,
    "Focus Fire": FOCUS_FIRE,
    "Haliya, Guided by Light": HALIYA_GUIDED_BY_LIGHT,
    "Hardlight Containment": HARDLIGHT_CONTAINMENT,
    "Honor": HONOR,
    "Honored Knight-Captain": HONORED_KNIGHTCAPTAIN,
    "Knight Luminary": KNIGHT_LUMINARY,
    "Lightstall Inquisitor": LIGHTSTALL_INQUISITOR,
    "Lumen-Class Frigate": LUMENCLASS_FRIGATE,
    "Luxknight Breacher": LUXKNIGHT_BREACHER,
    "Pinnacle Starcage": PINNACLE_STARCAGE,
    "Pulsar Squadron Ace": PULSAR_SQUADRON_ACE,
    "Radiant Strike": RADIANT_STRIKE,
    "Rayblade Trooper": RAYBLADE_TROOPER,
    "Reroute Systems": REROUTE_SYSTEMS,
    "Rescue Skiff": RESCUE_SKIFF,
    "Scout for Survivors": SCOUT_FOR_SURVIVORS,
    "Seam Rip": SEAM_RIP,
    "The Seriema": THE_SERIEMA,
    "Squire's Lightblade": SQUIRES_LIGHTBLADE,
    "Starfield Shepherd": STARFIELD_SHEPHERD,
    "Starfighter Pilot": STARFIGHTER_PILOT,
    "Starport Security": STARPORT_SECURITY,
    "Sunstar Chaplain": SUNSTAR_CHAPLAIN,
    "Sunstar Expansionist": SUNSTAR_EXPANSIONIST,
    "Sunstar Lightsmith": SUNSTAR_LIGHTSMITH,
    "Wedgelight Rammer": WEDGELIGHT_RAMMER,
    "Weftblade Enhancer": WEFTBLADE_ENHANCER,
    "Zealous Display": ZEALOUS_DISPLAY,
    "Annul": ANNUL,
    "Atomic Microsizer": ATOMIC_MICROSIZER,
    "Cerebral Download": CEREBRAL_DOWNLOAD,
    "Cloudsculpt Technician": CLOUDSCULPT_TECHNICIAN,
    "Codecracker Hound": CODECRACKER_HOUND,
    "Consult the Star Charts": CONSULT_THE_STAR_CHARTS,
    "Cryogen Relic": CRYOGEN_RELIC,
    "Cryoshatter": CRYOSHATTER,
    "Desculpting Blast": DESCULPTING_BLAST,
    "Divert Disaster": DIVERT_DISASTER,
    "Emissary Escort": EMISSARY_ESCORT,
    "Gigastorm Titan": GIGASTORM_TITAN,
    "Illvoi Galeblade": ILLVOI_GALEBLADE,
    "Illvoi Infiltrator": ILLVOI_INFILTRATOR,
    "Illvoi Light Jammer": ILLVOI_LIGHT_JAMMER,
    "Illvoi Operative": ILLVOI_OPERATIVE,
    "Lost in Space": LOST_IN_SPACE,
    "Mechan Assembler": MECHAN_ASSEMBLER,
    "Mechan Navigator": MECHAN_NAVIGATOR,
    "Mechan Shieldmate": MECHAN_SHIELDMATE,
    "Mechanozoa": MECHANOZOA,
    "Mental Modulation": MENTAL_MODULATION,
    "Mm'menon, the Right Hand": MMMENON_THE_RIGHT_HAND,
    "Moonlit Meditation": MOONLIT_MEDITATION,
    "Mouth of the Storm": MOUTH_OF_THE_STORM,
    "Nanoform Sentinel": NANOFORM_SENTINEL,
    "Quantum Riddler": QUANTUM_RIDDLER,
    "Scour for Scrap": SCOUR_FOR_SCRAP,
    "Selfcraft Mechan": SELFCRAFT_MECHAN,
    "Sinister Cryologist": SINISTER_CRYOLOGIST,
    "Specimen Freighter": SPECIMEN_FREIGHTER,
    "Starbreach Whale": STARBREACH_WHALE,
    "Starfield Vocalist": STARFIELD_VOCALIST,
    "Starwinder": STARWINDER,
    "Steelswarm Operator": STEELSWARM_OPERATOR,
    "Synthesizer Labship": SYNTHESIZER_LABSHIP,
    "Tractor Beam": TRACTOR_BEAM,
    "Unravel": UNRAVEL,
    "Uthros Psionicist": UTHROS_PSIONICIST,
    "Uthros Scanship": UTHROS_SCANSHIP,
    "Weftwalking": WEFTWALKING,
    "Alpharael, Stonechosen": ALPHARAEL_STONECHOSEN,
    "Archenemy's Charm": ARCHENEMYS_CHARM,
    "Beamsaw Prospector": BEAMSAW_PROSPECTOR,
    "Blade of the Swarm": BLADE_OF_THE_SWARM,
    "Chorale of the Void": CHORALE_OF_THE_VOID,
    "Comet Crawler": COMET_CRAWLER,
    "Dark Endurance": DARK_ENDURANCE,
    "Decode Transmissions": DECODE_TRANSMISSIONS,
    "Depressurize": DEPRESSURIZE,
    "Dubious Delicacy": DUBIOUS_DELICACY,
    "Elegy Acolyte": ELEGY_ACOLYTE,
    "Embrace Oblivion": EMBRACE_OBLIVION,
    "Entropic Battlecruiser": ENTROPIC_BATTLECRUISER,
    "Faller's Faithful": FALLERS_FAITHFUL,
    "Fell Gravship": FELL_GRAVSHIP,
    "Gravblade Heavy": GRAVBLADE_HEAVY,
    "Gravkill": GRAVKILL,
    "Gravpack Monoist": GRAVPACK_MONOIST,
    "Hullcarver": HULLCARVER,
    "Hylderblade": HYLDERBLADE,
    "Hymn of the Faller": HYMN_OF_THE_FALLER,
    "Insatiable Skittermaw": INSATIABLE_SKITTERMAW,
    "Lightless Evangel": LIGHTLESS_EVANGEL,
    "Monoist Circuit-Feeder": MONOIST_CIRCUITFEEDER,
    "Monoist Sentry": MONOIST_SENTRY,
    "Perigee Beckoner": PERIGEE_BECKONER,
    "Requiem Monolith": REQUIEM_MONOLITH,
    "Scrounge for Eternity": SCROUNGE_FOR_ETERNITY,
    "Sothera, the Supervoid": SOTHERA_THE_SUPERVOID,
    "Sunset Saboteur": SUNSET_SABOTEUR,
    "Susurian Dirgecraft": SUSURIAN_DIRGECRAFT,
    "Susurian Voidborn": SUSURIAN_VOIDBORN,
    "Swarm Culler": SWARM_CULLER,
    "Temporal Intervention": TEMPORAL_INTERVENTION,
    "Timeline Culler": TIMELINE_CULLER,
    "Tragic Trajectory": TRAGIC_TRAJECTORY,
    "Umbral Collar Zealot": UMBRAL_COLLAR_ZEALOT,
    "Virus Beetle": VIRUS_BEETLE,
    "Voidforged Titan": VOIDFORGED_TITAN,
    "Vote Out": VOTE_OUT,
    "Xu-Ifit, Osteoharmonist": XUIFIT_OSTEOHARMONIST,
    "Zero Point Ballad": ZERO_POINT_BALLAD,
    "Bombard": BOMBARD,
    "Cut Propulsion": CUT_PROPULSION,
    "Debris Field Crusher": DEBRIS_FIELD_CRUSHER,
    "Devastating Onslaught": DEVASTATING_ONSLAUGHT,
    "Drill Too Deep": DRILL_TOO_DEEP,
    "Frontline War-Rager": FRONTLINE_WARRAGER,
    "Full Bore": FULL_BORE,
    "Galvanizing Sawship": GALVANIZING_SAWSHIP,
    "Invasive Maneuvers": INVASIVE_MANEUVERS,
    "Kav Landseeker": KAV_LANDSEEKER,
    "Kavaron Harrier": KAVARON_HARRIER,
    "Kavaron Skywarden": KAVARON_SKYWARDEN,
    "Kavaron Turbodrone": KAVARON_TURBODRONE,
    "Lithobraking": LITHOBRAKING,
    "Melded Moxite": MELDED_MOXITE,
    "Memorial Team Leader": MEMORIAL_TEAM_LEADER,
    "Memorial Vault": MEMORIAL_VAULT,
    "Molecular Modifier": MOLECULAR_MODIFIER,
    "Nebula Dragon": NEBULA_DRAGON,
    "Nova Hellkite": NOVA_HELLKITE,
    "Orbital Plunge": ORBITAL_PLUNGE,
    "Oreplate Pangolin": OREPLATE_PANGOLIN,
    "Pain for All": PAIN_FOR_ALL,
    "Plasma Bolt": PLASMA_BOLT,
    "Possibility Technician": POSSIBILITY_TECHNICIAN,
    "Red Tiger Mechan": RED_TIGER_MECHAN,
    "Remnant Elemental": REMNANT_ELEMENTAL,
    "Rig for War": RIG_FOR_WAR,
    "Roving Actuator": ROVING_ACTUATOR,
    "Ruinous Rampage": RUINOUS_RAMPAGE,
    "Rust Harvester": RUST_HARVESTER,
    "Slagdrill Scrapper": SLAGDRILL_SCRAPPER,
    "Systems Override": SYSTEMS_OVERRIDE,
    "Tannuk, Steadfast Second": TANNUK_STEADFAST_SECOND,
    "Terminal Velocity": TERMINAL_VELOCITY,
    "Terrapact Intimidator": TERRAPACT_INTIMIDATOR,
    "Territorial Bruntar": TERRITORIAL_BRUNTAR,
    "Vaultguard Trooper": VAULTGUARD_TROOPER,
    "Warmaker Gunship": WARMAKER_GUNSHIP,
    "Weapons Manufacturing": WEAPONS_MANUFACTURING,
    "Weftstalker Ardent": WEFTSTALKER_ARDENT,
    "Zookeeper Mechan": ZOOKEEPER_MECHAN,
    "Atmospheric Greenhouse": ATMOSPHERIC_GREENHOUSE,
    "Bioengineered Future": BIOENGINEERED_FUTURE,
    "Biosynthic Burst": BIOSYNTHIC_BURST,
    "Blooming Stinger": BLOOMING_STINGER,
    "Broodguard Elite": BROODGUARD_ELITE,
    "Close Encounter": CLOSE_ENCOUNTER,
    "Diplomatic Relations": DIPLOMATIC_RELATIONS,
    "Drix Fatemaker": DRIX_FATEMAKER,
    "Edge Rover": EDGE_ROVER,
    "Eumidian Terrabotanist": EUMIDIAN_TERRABOTANIST,
    "Eusocial Engineering": EUSOCIAL_ENGINEERING,
    "Famished Worldsire": FAMISHED_WORLDSIRE,
    "Frenzied Baloth": FRENZIED_BALOTH,
    "Fungal Colossus": FUNGAL_COLOSSUS,
    "Galactic Wayfarer": GALACTIC_WAYFARER,
    "Gene Pollinator": GENE_POLLINATOR,
    "Germinating Wurm": GERMINATING_WURM,
    "Glacier Godmaw": GLACIER_GODMAW,
    "Harmonious Grovestrider": HARMONIOUS_GROVESTRIDER,
    "Hemosymbic Mite": HEMOSYMBIC_MITE,
    "Icecave Crasher": ICECAVE_CRASHER,
    "Icetill Explorer": ICETILL_EXPLORER,
    "Intrepid Tenderfoot": INTREPID_TENDERFOOT,
    "Larval Scoutlander": LARVAL_SCOUTLANDER,
    "Lashwhip Predator": LASHWHIP_PREDATOR,
    "Loading Zone": LOADING_ZONE,
    "Meltstrider Eulogist": MELTSTRIDER_EULOGIST,
    "Meltstrider's Gear": MELTSTRIDERS_GEAR,
    "Meltstrider's Resolve": MELTSTRIDERS_RESOLVE,
    "Mightform Harmonizer": MIGHTFORM_HARMONIZER,
    "Ouroboroid": OUROBOROID,
    "Pull Through the Weft": PULL_THROUGH_THE_WEFT,
    "Sami's Curiosity": SAMIS_CURIOSITY,
    "Seedship Agrarian": SEEDSHIP_AGRARIAN,
    "Seedship Impact": SEEDSHIP_IMPACT,
    "Shattered Wings": SHATTERED_WINGS,
    "Skystinger": SKYSTINGER,
    "Sledge-Class Seedship": SLEDGECLASS_SEEDSHIP,
    "Tapestry Warden": TAPESTRY_WARDEN,
    "Terrasymbiosis": TERRASYMBIOSIS,
    "Thawbringer": THAWBRINGER,
    "Alpharael, Dreaming Acolyte": ALPHARAEL_DREAMING_ACOLYTE,
    "Biomechan Engineer": BIOMECHAN_ENGINEER,
    "Biotech Specialist": BIOTECH_SPECIALIST,
    "Cosmogoyf": COSMOGOYF,
    "Dyadrine, Synthesis Amalgam": DYADRINE_SYNTHESIS_AMALGAM,
    "Genemorph Imago": GENEMORPH_IMAGO,
    "Haliya, Ascendant Cadet": HALIYA_ASCENDANT_CADET,
    "Infinite Guideline Station": INFINITE_GUIDELINE_STATION,
    "Interceptor Mechan": INTERCEPTOR_MECHAN,
    "Mm'menon, Uthros Exile": MMMENON_UTHROS_EXILE,
    "Mutinous Massacre": MUTINOUS_MASSACRE,
    "Pinnacle Emissary": PINNACLE_EMISSARY,
    "Ragost, Deft Gastronaut": RAGOST_DEFT_GASTRONAUT,
    "Sami, Ship's Engineer": SAMI_SHIPS_ENGINEER,
    "Sami, Wildcat Captain": SAMI_WILDCAT_CAPTAIN,
    "Seedship Broodtender": SEEDSHIP_BROODTENDER,
    "Singularity Rupture": SINGULARITY_RUPTURE,
    "Space-Time Anomaly": SPACETIME_ANOMALY,
    "Station Monitor": STATION_MONITOR,
    "Syr Vondam, Sunstar Exemplar": SYR_VONDAM_SUNSTAR_EXEMPLAR,
    "Syr Vondam, the Lucent": SYR_VONDAM_THE_LUCENT,
    "Tannuk, Memorial Ensign": TANNUK_MEMORIAL_ENSIGN,
    "All-Fates Scroll": ALLFATES_SCROLL,
    "Bygone Colossus": BYGONE_COLOSSUS,
    "Chrome Companion": CHROME_COMPANION,
    "Dauntless Scrapbot": DAUNTLESS_SCRAPBOT,
    "Dawnsire, Sunstar Dreadnought": DAWNSIRE_SUNSTAR_DREADNOUGHT,
    "The Dominion Bracelet": THE_DOMINION_BRACELET,
    "The Endstone": THE_ENDSTONE,
    "The Eternity Elevator": THE_ETERNITY_ELEVATOR,
    "Extinguisher Battleship": EXTINGUISHER_BATTLESHIP,
    "Nutrient Block": NUTRIENT_BLOCK,
    "Pinnacle Kill-Ship": PINNACLE_KILLSHIP,
    "Survey Mechan": SURVEY_MECHAN,
    "Thaumaton Torpedo": THAUMATON_TORPEDO,
    "Thrumming Hivepool": THRUMMING_HIVEPOOL,
    "Virulent Silencer": VIRULENT_SILENCER,
    "Wurmwall Sweeper": WURMWALL_SWEEPER,
    "Adagia, Windswept Bastion": ADAGIA_WINDSWEPT_BASTION,
    "Breeding Pool": BREEDING_POOL,
    "Command Bridge": COMMAND_BRIDGE,
    "Evendo, Waking Haven": EVENDO_WAKING_HAVEN,
    "Godless Shrine": GODLESS_SHRINE,
    "Kavaron, Memorial World": KAVARON_MEMORIAL_WORLD,
    "Sacred Foundry": SACRED_FOUNDRY,
    "Secluded Starforge": SECLUDED_STARFORGE,
    "Stomping Ground": STOMPING_GROUND,
    "Susur Secundi, Void Altar": SUSUR_SECUNDI_VOID_ALTAR,
    "Uthros, Titanic Godcore": UTHROS_TITANIC_GODCORE,
    "Watery Grave": WATERY_GRAVE,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
}

print(f"Loaded {len(EDGE_OF_ETERNITIES_CARDS)} Edge of Eternities cards")
