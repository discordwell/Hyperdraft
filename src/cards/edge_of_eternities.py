"""
Edge of Eternities (EOE) Card Implementations

Set released January 2026. 276 cards.
Features mechanics: Chronicle, Time Counter, Suspend, Echo, Rewind, Temporal, Prophecy
Theme: Time manipulation, ancient civilizations, and temporal paradoxes
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
# WHITE CARDS - ORDER & PRESERVATION
# =============================================================================

TEMPORAL_GUARDIAN = make_creature(
    name="Temporal Guardian",
    power=3,
    toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="Vigilance. Chronicle — At the beginning of your upkeep, put a time counter on each permanent you control. Permanents you control with time counters on them have hexproof."
)

CHRONO_PALADIN = make_creature(
    name="Chrono-Paladin",
    power=4,
    toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight", "Cleric"},
    text="First strike. When Chrono-Paladin enters, return target permanent card with mana value 3 or less from your graveyard to the battlefield."
)

KEEPER_OF_MOMENTS = make_creature(
    name="Keeper of Moments",
    power=2,
    toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Cleric"},
    text="Flying. Chronicle — At the beginning of your end step, you may exile target creature you control. Return it to the battlefield at the beginning of the next end step."
)

TIMELESS_SENTINEL = make_creature(
    name="Timeless Sentinel",
    power=3,
    toughness=5,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Construct", "Soldier"},
    text="Vigilance, lifelink. Timeless Sentinel doesn't untap during your untap step. At the beginning of each upkeep, untap Timeless Sentinel."
)

FUTURE_SIGHT_ORACLE = make_creature(
    name="Future Sight Oracle",
    power=2,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Wizard"},
    text="Prophecy — At the beginning of your upkeep, look at the top card of your library. You may reveal it. If it's a creature card, you gain life equal to its mana value."
)

ETERNAL_ADJUDICATOR = make_creature(
    name="Eternal Adjudicator",
    power=4,
    toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    supertypes={"Legendary"},
    text="Flying, vigilance. Rewind — When Eternal Adjudicator dies, you may exile it with three time counters on it. At the beginning of each upkeep, remove a time counter. When the last is removed, return it to the battlefield."
)

MOMENT_OF_CLARITY = make_instant(
    name="Moment of Clarity",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Exile target creature. At the beginning of the next end step, return it to the battlefield under its owner's control."
)

TEMPORAL_SANCTUARY = make_enchantment(
    name="Temporal Sanctuary",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Creatures you control can't be the targets of spells or abilities your opponents control during your turn."
)

CHRONICLE_OF_AGES = make_sorcery(
    name="Chronicle of Ages",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Return up to two target creature cards with total mana value 5 or less from your graveyard to the battlefield."
)

PRESERVED_MEMORY = make_instant(
    name="Preserved Memory",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gains indestructible until end of turn. Scry 1."
)

TIMELINE_PROTECTOR = make_creature(
    name="Timeline Protector",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Flash. When Timeline Protector enters, target creature you control gains hexproof until end of turn."
)

DAWN_OF_NEW_ERA = make_sorcery(
    name="Dawn of New Era",
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    text="Exile all creatures. Each player creates a 1/1 white Spirit creature token for each creature they controlled that was exiled this way."
)

ETERNITY_WARDEN = make_creature(
    name="Eternity Warden",
    power=3,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Vigilance. Whenever another creature enters under your control, put a +1/+1 counter on Eternity Warden."
)


# =============================================================================
# BLUE CARDS - TIME MANIPULATION
# =============================================================================

CHRONOMANCER_SUPREME = make_creature(
    name="Chronomancer Supreme",
    power=3,
    toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Temporal — Whenever you cast a spell from exile or your graveyard, draw a card. {2}{U}: Exile target instant or sorcery card from your graveyard. You may cast it this turn."
)

TIME_WEAVER = make_creature(
    name="Time Weaver",
    power=2,
    toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Temporal — At the beginning of your upkeep, you may exile the top card of your library face down with a time counter on it. You may look at and play that card for as long as it remains exiled."
)

ECHO_OF_TOMORROW = make_creature(
    name="Echo of Tomorrow",
    power=3,
    toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Flying. Echo {2}{U}. When Echo of Tomorrow enters, draw a card."
)

PARADOX_ENTITY = make_creature(
    name="Paradox Entity",
    power=4,
    toughness=4,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Horror"},
    text="Flash. When Paradox Entity enters, exile target spell. Its controller may cast it for as long as it remains exiled."
)

SUSPENDED_SCHOLAR = make_creature(
    name="Suspended Scholar",
    power=2,
    toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Suspend 3 — {U}. When Suspended Scholar enters, draw two cards."
)

TEMPORAL_LOOP = make_instant(
    name="Temporal Loop",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Return target spell to its owner's hand. Its controller may cast it again this turn without paying its mana cost."
)

REWIND_MOMENT = make_instant(
    name="Rewind Moment",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Rewind — Return target nonland permanent to its owner's hand. At the beginning of the next end step, that player may put it onto the battlefield."
)

GLIMPSE_BEYOND_TIME = make_sorcery(
    name="Glimpse Beyond Time",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Look at the top five cards of your library. Put two into your hand and the rest on the bottom of your library in any order."
)

TIME_STOP_FIELD = make_enchantment(
    name="Time Stop Field",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Players can't cast more than two spells each turn."
)

CHRONO_SHIFT = make_instant(
    name="Chrono-Shift",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature phases out until the beginning of your next upkeep."
)

FUTURE_ECHO = make_creature(
    name="Future Echo",
    power=2,
    toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Flying. When Future Echo enters, look at the top three cards of your library. Put one back and the rest on the bottom."
)

TEMPORAL_ANCHOR = make_enchantment(
    name="Temporal Anchor",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="At the beginning of your upkeep, if you control no other permanents with a time counter, put a time counter on Temporal Anchor. Otherwise, scry 1."
)


# =============================================================================
# BLACK CARDS - DECAY & ENTROPY
# =============================================================================

ENTROPY_WRAITH = make_creature(
    name="Entropy Wraith",
    power=4,
    toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Horror"},
    supertypes={"Legendary"},
    text="Flying. Chronicle — At the beginning of each end step, each opponent loses 1 life for each time counter on permanents you control."
)

CHRONO_REAPER = make_creature(
    name="Chrono-Reaper",
    power=5,
    toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Skeleton", "Knight"},
    text="Menace. When Chrono-Reaper enters, destroy target creature. If that creature had time counters on it, draw cards equal to the number of time counters it had."
)

TIMELESS_DECAY = make_sorcery(
    name="Timeless Decay",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="All creatures get -2/-2 until end of turn. For each creature that dies this turn, put a time counter on target permanent you control."
)

FATE_UNWRITTEN = make_instant(
    name="Fate Unwritten",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. If it had suspend, its controller may cast it without paying its mana cost."
)

ECHO_OF_DEATH = make_creature(
    name="Echo of Death",
    power=3,
    toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Deathtouch. Echo {1}{B}. When Echo of Death enters, target opponent loses 2 life."
)

TEMPORAL_VAMPIRE = make_creature(
    name="Temporal Vampire",
    power=3,
    toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="Flying. Whenever Temporal Vampire deals combat damage to a player, remove a time counter from target permanent that player controls. If you can't, that player discards a card."
)

DECAY_OF_AGES = make_enchantment(
    name="Decay of Ages",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="At the beginning of each opponent's upkeep, they sacrifice a creature unless they pay 2 life."
)

STOLEN_MOMENT = make_instant(
    name="Stolen Moment",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -3/-3 until end of turn. You gain 3 life."
)

GRAVE_TIMELINE = make_sorcery(
    name="Grave Timeline",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Return up to two target creature cards from your graveyard to your hand. You lose 2 life."
)

ENTROPY_WALKER = make_creature(
    name="Entropy Walker",
    power=2,
    toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="Menace. Whenever another creature dies, put a +1/+1 counter on Entropy Walker."
)

TEMPORAL_TORMENT = make_sorcery(
    name="Temporal Torment",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Target opponent discards two cards. For each card discarded this way, put a time counter on target permanent you control."
)

FORGOTTEN_AGES = make_creature(
    name="Forgotten Ages",
    power=5,
    toughness=5,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="When Forgotten Ages enters, each player sacrifices a creature. Rewind — When Forgotten Ages dies, exile it with two time counters."
)


# =============================================================================
# RED CARDS - CHAOS & ACCELERATION
# =============================================================================

CHRONO_BERSERKER = make_creature(
    name="Chrono-Berserker",
    power=4,
    toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Haste. Temporal — Whenever you cast a spell from exile, Chrono-Berserker deals 2 damage to any target."
)

TIME_RAGER = make_creature(
    name="Time Rager",
    power=3,
    toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Haste. Echo {1}{R}. When Time Rager enters, it deals 2 damage to any target."
)

ACCELERATED_DRAGON = make_creature(
    name="Accelerated Dragon",
    power=5,
    toughness=4,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying, haste. Suspend 4 — {R}. When Accelerated Dragon enters, it deals 3 damage to each creature you don't control."
)

TEMPORAL_STORM = make_sorcery(
    name="Temporal Storm",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Temporal Storm deals damage to each creature equal to the number of time counters on permanents you control."
)

RIFT_ELEMENTAL = make_creature(
    name="Rift Elemental",
    power=2,
    toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Haste. Whenever you remove a time counter from a permanent, Rift Elemental gets +2/+0 until end of turn."
)

SHATTERED_TIMELINE = make_instant(
    name="Shattered Timeline",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Destroy target artifact. If it had time counters on it, Shattered Timeline deals damage to its controller equal to the number of time counters it had."
)

CHRONO_FURY = make_instant(
    name="Chrono-Fury",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +3/+1 and gains haste until end of turn."
)

BLAZE_THROUGH_TIME = make_sorcery(
    name="Blaze Through Time",
    mana_cost="{X}{R}{R}",
    colors={Color.RED},
    text="Blaze Through Time deals X damage to any target. If X is 5 or more, you may cast target instant or sorcery card with mana value X or less from your graveyard without paying its mana cost."
)

TEMPORAL_PHOENIX = make_creature(
    name="Temporal Phoenix",
    power=4,
    toughness=3,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Phoenix"},
    supertypes={"Legendary"},
    text="Flying, haste. Rewind — When Temporal Phoenix dies, exile it with three time counters. At the beginning of each upkeep, remove a time counter. When the last is removed, return it to the battlefield."
)

ECHO_FLAMES = make_instant(
    name="Echo Flames",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Echo Flames deals 3 damage to any target. Echo {2}{R}."
)

CHAOS_RIFT = make_enchantment(
    name="Chaos Rift",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="At the beginning of your upkeep, exile the top card of your library. You may play it this turn."
)

ACCELERATE = make_instant(
    name="Accelerate",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gains haste until end of turn. Draw a card."
)


# =============================================================================
# GREEN CARDS - GROWTH & CYCLES
# =============================================================================

ELDER_CHRONOMANCER = make_creature(
    name="Elder Chronomancer",
    power=4,
    toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk", "Druid"},
    supertypes={"Legendary"},
    text="Trample. Chronicle — At the beginning of your upkeep, put a +1/+1 counter on each creature you control with a time counter on it."
)

SEEDLING_OF_AGES = make_creature(
    name="Seedling of Ages",
    power=0,
    toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="At the beginning of your upkeep, put a growth counter on Seedling of Ages. Seedling of Ages gets +1/+1 for each growth counter on it."
)

TEMPORAL_GROWTH = make_sorcery(
    name="Temporal Growth",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Put two +1/+1 counters on target creature. If that creature has a time counter on it, put four +1/+1 counters on it instead."
)

CYCLE_OF_ETERNITY = make_enchantment(
    name="Cycle of Eternity",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Whenever a creature you control dies, you may put it on top of your library instead of into your graveyard."
)

ECHO_OF_THE_WILD = make_creature(
    name="Echo of the Wild",
    power=4,
    toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample. Echo {3}{G}. When Echo of the Wild enters, search your library for a basic land card, put it onto the battlefield tapped, then shuffle."
)

PRIMORDIAL_TITAN = make_creature(
    name="Primordial Titan",
    power=7,
    toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Giant"},
    text="Trample. Suspend 5 — {G}{G}. When Primordial Titan enters, put a +1/+1 counter on each other creature you control."
)

TIMELESS_FOREST = make_enchantment(
    name="Timeless Forest",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Creatures you control with +1/+1 counters on them have trample."
)

NATURE_RECLAIMS = make_instant(
    name="Nature Reclaims",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Destroy target artifact or enchantment. Its controller may search their library for a basic land card, put it onto the battlefield tapped, then shuffle."
)

CHRONICLE_BEAST = make_creature(
    name="Chronicle Beast",
    power=3,
    toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="When Chronicle Beast enters, put a time counter on target permanent you control. As long as that permanent has a time counter on it, it has hexproof."
)

TEMPORAL_BLOOM = make_sorcery(
    name="Temporal Bloom",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Search your library for up to two basic land cards, put them onto the battlefield, then shuffle. Put a time counter on each land that entered this way."
)

AGELESS_OAK = make_creature(
    name="Ageless Oak",
    power=5,
    toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="Reach. Ageless Oak enters with three time counters on it. As long as it has a time counter on it, it has indestructible."
)

GROWTH_THROUGH_TIME = make_instant(
    name="Growth Through Time",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Put a +1/+1 counter on target creature. If it has a time counter on it, put two +1/+1 counters on it instead."
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

KAEL_TIMEKEEPER = make_creature(
    name="Kael, Timekeeper",
    power=4,
    toughness=4,
    mana_cost="{W}{U}{B}{R}{G}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Flying, vigilance. Chronicle — At the beginning of your upkeep, choose one: Put a time counter on target permanent; remove a time counter from target permanent; or draw a card for each permanent with a time counter on it."
)

TEMPORAL_TWINS = make_creature(
    name="Temporal Twins",
    power=3,
    toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="When Temporal Twins enters, create a token that's a copy of it except it's not legendary. At the beginning of your end step, sacrifice one of them."
)

ENTROPY_AND_ORDER = make_creature(
    name="Entropy and Order",
    power=5,
    toughness=5,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    text="Flying. When Entropy and Order enters, choose one — Return target creature card from your graveyard to the battlefield; or destroy target creature."
)

CHRONO_DRAGON = make_creature(
    name="Chrono-Dragon",
    power=6,
    toughness=6,
    mana_cost="{3}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Dragon"},
    supertypes={"Legendary"},
    text="Flying, haste. Temporal — At the beginning of your upkeep, exile the top card of your library with a time counter on it. You may play cards exiled by Chrono-Dragon."
)

DECAY_BLOOM = make_creature(
    name="Decay Bloom",
    power=4,
    toughness=4,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Plant", "Zombie"},
    supertypes={"Legendary"},
    text="Deathtouch. When Decay Bloom enters, return target creature card from your graveyard to your hand. Whenever a creature dies, put a +1/+1 counter on Decay Bloom."
)

TEMPORAL_PARADOX = make_creature(
    name="Temporal Paradox",
    power=4,
    toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Horror"},
    supertypes={"Legendary"},
    text="Flying. When Temporal Paradox enters, each player exiles the top five cards of their library. You may cast nonland cards exiled this way, and mana of any type can be spent to cast them."
)

CHRONO_WARLORD = make_creature(
    name="Chrono-Warlord",
    power=5,
    toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="First strike, vigilance. Temporal — Whenever Chrono-Warlord attacks, creatures you control get +1/+1 and gain haste until end of turn."
)

NATURE_MAGE_ETERNAL = make_creature(
    name="Nature Mage, Eternal",
    power=3,
    toughness=5,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Elf", "Druid"},
    supertypes={"Legendary"},
    text="Chronicle — At the beginning of your upkeep, you may put a time counter on target land you control. Lands you control with time counters tap for one additional mana of any type they could produce."
)

SYMBIOTIC_TIMELINE = make_enchantment(
    name="Symbiotic Timeline",
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Whenever a creature with a +1/+1 counter enters under your control, put a time counter on it. Whenever a creature with a time counter enters under your control, put a +1/+1 counter on it."
)

RIFT_WALKER = make_creature(
    name="Rift Walker",
    power=3,
    toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Elemental"},
    text="Haste. When Rift Walker enters, exile the top card of your library. You may play it this turn. If you don't, put it into your hand at the beginning of the next end step."
)


# =============================================================================
# ARTIFACTS
# =============================================================================

HOURGLASS_OF_ETERNITY = make_artifact(
    name="Hourglass of Eternity",
    mana_cost="{4}",
    supertypes={"Legendary"},
    text="{T}: Put a time counter on target permanent. {3}, {T}: Remove all time counters from target permanent. If you removed three or more, draw a card."
)

CHRONO_COMPASS = make_artifact(
    name="Chrono Compass",
    mana_cost="{2}",
    text="{T}: Add {C}. {2}, {T}: Scry 2."
)

TEMPORAL_BLADE = make_artifact(
    name="Temporal Blade",
    mana_cost="{3}",
    subtypes={"Equipment"},
    text="Equipped creature gets +2/+1. Whenever equipped creature deals combat damage to a player, put a time counter on target permanent that player controls. Equip {2}"
)

TIME_CAPSULE = make_artifact(
    name="Time Capsule",
    mana_cost="{2}",
    text="Time Capsule enters with three charge counters on it. {T}, Remove a charge counter: Add {C}{C}. When the last charge counter is removed, sacrifice Time Capsule and draw two cards."
)

SUSPENDED_RELIC = make_artifact(
    name="Suspended Relic",
    mana_cost="{4}",
    text="Suspend 3 — {1}. When Suspended Relic enters, draw two cards and gain 4 life."
)

CLOCK_OF_AGES = make_artifact(
    name="Clock of Ages",
    mana_cost="{5}",
    supertypes={"Legendary"},
    text="At the beginning of each upkeep, put a time counter on Clock of Ages. {T}: Each player draws a card for each three time counters on Clock of Ages."
)

RIFT_GENERATOR = make_artifact(
    name="Rift Generator",
    mana_cost="{3}",
    text="{2}, {T}: Exile target creature you control. Return it to the battlefield at the beginning of the next end step."
)

AEON_STONE = make_artifact(
    name="Aeon Stone",
    mana_cost="{1}",
    text="{T}: Add {C}. {1}, {T}, Sacrifice Aeon Stone: Draw a card."
)

CHRONOLITH = make_artifact(
    name="Chronolith",
    mana_cost="{4}",
    supertypes={"Legendary"},
    text="Spells you cast from exile cost {2} less to cast. {3}, {T}: Exile the top card of your library. You may play it this turn."
)

TEMPORAL_ANCHOR_ARTIFACT = make_artifact(
    name="Anchor of Time",
    mana_cost="{3}",
    text="At the beginning of your upkeep, put a time counter on Anchor of Time. Creatures you control get +0/+1 for each time counter on Anchor of Time."
)


# =============================================================================
# LANDS
# =============================================================================

TIMELESS_CITADEL = make_land(
    name="Timeless Citadel",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast spells with suspend or spells from exile."
)

TEMPORAL_NEXUS = make_land(
    name="Temporal Nexus",
    text="Temporal Nexus enters tapped. {T}: Add {U} or {R}. {3}, {T}: Exile the top card of your library. You may play it this turn."
)

DECAY_WASTES = make_land(
    name="Decay Wastes",
    text="Decay Wastes enters tapped. {T}: Add {B} or {G}. When Decay Wastes enters, mill two cards."
)

ETERNAL_GROVE = make_land(
    name="Eternal Grove",
    text="Eternal Grove enters tapped. {T}: Add {G} or {W}. When Eternal Grove enters, you gain 1 life."
)

RIFT_CHASM = make_land(
    name="Rift Chasm",
    text="Rift Chasm enters tapped. {T}: Add {R} or {B}. {4}, {T}, Sacrifice Rift Chasm: Draw two cards."
)

SUSPENDED_ISLAND = make_land(
    name="Suspended Island",
    text="Suspended Island enters with a time counter on it. As long as it has a time counter, it has '{T}: Add {U}{U}.' At the beginning of your upkeep, remove a time counter."
)

CHRONO_SPIRE = make_land(
    name="Chrono Spire",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add {W} or {U}. Activate only if you control a creature with a time counter on it."
)

ENTROPY_POOL = make_land(
    name="Entropy Pool",
    text="Entropy Pool enters tapped. {T}: Add {U} or {B}. {2}, {T}: Target creature gets -1/-1 until end of turn."
)

ACCELERATED_PLAINS = make_land(
    name="Accelerated Plains",
    text="Accelerated Plains enters tapped. {T}: Add {R} or {W}. When Accelerated Plains enters, target creature gains haste until end of turn."
)

ANCIENT_ARCHIVE = make_land(
    name="Ancient Archive",
    text="Ancient Archive enters tapped. {T}: Add {W} or {B}. {3}, {T}: Return target creature card with mana value 2 or less from your graveyard to your hand."
)


# =============================================================================
# BASIC LANDS
# =============================================================================

PLAINS_EOE = make_land(
    name="Plains",
    subtypes={"Plains"},
    supertypes={"Basic"},
    text="({T}: Add {W}.)"
)

ISLAND_EOE = make_land(
    name="Island",
    subtypes={"Island"},
    supertypes={"Basic"},
    text="({T}: Add {U}.)"
)

SWAMP_EOE = make_land(
    name="Swamp",
    subtypes={"Swamp"},
    supertypes={"Basic"},
    text="({T}: Add {B}.)"
)

MOUNTAIN_EOE = make_land(
    name="Mountain",
    subtypes={"Mountain"},
    supertypes={"Basic"},
    text="({T}: Add {R}.)"
)

FOREST_EOE = make_land(
    name="Forest",
    subtypes={"Forest"},
    supertypes={"Basic"},
    text="({T}: Add {G}.)"
)


# =============================================================================
# ADDITIONAL CARDS
# =============================================================================

TEMPORAL_RIFT_MAGE = make_creature(
    name="Temporal Rift Mage",
    power=2,
    toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When Temporal Rift Mage enters, look at the top three cards of your library. Put one into your hand and the rest on the bottom."
)

AGELESS_KNIGHT = make_creature(
    name="Ageless Knight",
    power=3,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="First strike. Rewind — When Ageless Knight dies, exile it with two time counters."
)

DECAY_SPIRIT = make_creature(
    name="Decay Spirit",
    power=2,
    toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Flying. When Decay Spirit enters, target creature gets -1/-1 until end of turn."
)

CHRONO_WARRIOR = make_creature(
    name="Chrono-Warrior",
    power=3,
    toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="Haste. When Chrono-Warrior enters, it deals 1 damage to any target."
)

TIMELESS_SAPLING = make_creature(
    name="Timeless Sapling",
    power=1,
    toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="{T}: Add {G}. Timeless Sapling gets +1/+1 until end of turn."
)

PARADOX_STRIKE = make_instant(
    name="Paradox Strike",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target creature to its owner's hand. Scry 1."
)

ENTROPY_BOLT = make_instant(
    name="Entropy Bolt",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn. If it dies this turn, draw a card."
)

TEMPORAL_BLAST = make_instant(
    name="Temporal Blast",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Temporal Blast deals 3 damage to any target. If a permanent with a time counter is put into a graveyard this turn, draw a card."
)

CHRONICLE_GROWTH = make_instant(
    name="Chronicle Growth",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Put two +1/+1 counters on target creature. It gains trample until end of turn."
)

SEAL_OF_AGES = make_instant(
    name="Seal of Ages",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Exile target nonland permanent. Return it to the battlefield at the beginning of the next end step under its owner's control."
)

TIME_FRACTURE = make_sorcery(
    name="Time Fracture",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Take an extra turn after this one. Skip your draw step on that turn."
)

ENTROPY_CASCADE = make_sorcery(
    name="Entropy Cascade",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Each creature gets -2/-2 until end of turn. Draw a card for each creature that dies this turn."
)

TEMPORAL_INFERNO = make_sorcery(
    name="Temporal Inferno",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Temporal Inferno deals 5 damage to each creature. Creatures dealt damage this way can't be regenerated."
)

ETERNAL_BLOOM = make_sorcery(
    name="Eternal Bloom",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Put a +1/+1 counter on each creature you control. Creatures you control gain trample until end of turn."
)

DIVINE_CHRONICLE = make_sorcery(
    name="Divine Chronicle",
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    text="Put a time counter on each creature you control. You gain 2 life for each creature you control."
)

ECHO_DUPLICATION = make_instant(
    name="Echo Duplication",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Create a token that's a copy of target creature you control. Exile it at the beginning of the next end step."
)

TEMPORAL_AMBUSH = make_instant(
    name="Temporal Ambush",
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Target creature you control fights target creature you don't control. If your creature dies, return it to your hand at the beginning of the next end step."
)

CHRONO_SURGE = make_instant(
    name="Chrono-Surge",
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Untap all creatures you control. They gain vigilance and haste until end of turn."
)

RIFT_ERUPTION = make_sorcery(
    name="Rift Eruption",
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    text="Exile the top five cards of your library. You may play them until end of turn. At the beginning of the next end step, put any cards not played this way into your graveyard."
)

TEMPORAL_CONVERGENCE = make_sorcery(
    name="Temporal Convergence",
    mana_cost="{3}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Return all creatures to their owners' hands. Each player may put a creature card from their hand onto the battlefield."
)

ECHO_GOLEM = make_creature(
    name="Echo Golem",
    power=4,
    toughness=4,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Golem"},
    text="Echo {4}. When Echo Golem enters, add {C}{C}{C}."
)

CHRONO_SENTRY = make_creature(
    name="Chrono-Sentry",
    power=3,
    toughness=4,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Construct"},
    text="Whenever a creature with a time counter enters under your control, Chrono-Sentry gets +1/+1 until end of turn."
)

TEMPORAL_SHADE = make_creature(
    name="Temporal Shade",
    power=2,
    toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Shade"},
    text="Flying. {U}{B}: Temporal Shade gets +1/+1 until end of turn."
)

AGELESS_WURM = make_creature(
    name="Ageless Wurm",
    power=6,
    toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Wurm"},
    text="Trample. Suspend 4 — {G}{G}. When Ageless Wurm enters, put a +1/+1 counter on each other creature you control."
)

ETERNAL_FLAME = make_creature(
    name="Eternal Flame",
    power=4,
    toughness=1,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Haste. Rewind — When Eternal Flame dies, exile it with two time counters. At the beginning of each upkeep, remove a time counter. When the last is removed, return it to the battlefield."
)

PRESERVATION_ANGEL = make_creature(
    name="Preservation Angel",
    power=4,
    toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying, vigilance. When Preservation Angel enters, put a time counter on each creature you control. Creatures you control with time counters have lifelink."
)

TEMPORAL_SERPENT = make_creature(
    name="Temporal Serpent",
    power=5,
    toughness=5,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Serpent"},
    text="Temporal Serpent can't be blocked. When Temporal Serpent deals combat damage to a player, take an extra turn after this one. Sacrifice Temporal Serpent at the beginning of that turn's end step."
)

ENTROPY_DEMON = make_creature(
    name="Entropy Demon",
    power=5,
    toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Flying. At the beginning of your upkeep, each opponent loses 1 life and you gain 1 life. When Entropy Demon dies, each opponent discards a card."
)

CHRONO_GIANT = make_creature(
    name="Chrono-Giant",
    power=7,
    toughness=7,
    mana_cost="{5}{R}{R}",
    colors={Color.RED},
    subtypes={"Giant"},
    text="Trample, haste. Suspend 5 — {R}{R}. When Chrono-Giant enters, it deals 4 damage to each opponent."
)

ANCIENT_GUARDIAN = make_creature(
    name="Ancient Guardian",
    power=6,
    toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental"},
    text="Reach, trample. When Ancient Guardian enters, search your library for a basic land card, put it onto the battlefield, then shuffle."
)

TIME_SIPHON = make_instant(
    name="Time Siphon",
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    text="Target opponent exiles the top four cards of their library. You may cast nonland cards from among them this turn, and mana of any type can be spent to cast them."
)

ETERNAL_BLESSING = make_instant(
    name="Eternal Blessing",
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Put a +1/+1 counter and a time counter on each creature you control. You gain 1 life for each creature you control."
)

CHRONO_SHATTER = make_instant(
    name="Chrono-Shatter",
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Destroy target artifact or enchantment. If it had time counters on it, Chrono-Shatter deals 3 damage to any target."
)

TEMPORAL_GRASP = make_enchantment(
    name="Temporal Grasp",
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="At the beginning of your upkeep, return target creature card from your graveyard to your hand. You lose 1 life."
)

RIFT_PORTAL = make_enchantment(
    name="Rift Portal",
    mana_cost="{3}{U}{R}",
    colors={Color.BLUE, Color.RED},
    text="At the beginning of your upkeep, exile the top card of your library. You may play it this turn. Spells you cast from exile cost {1} less to cast."
)

ETERNAL_CYCLE = make_enchantment(
    name="Eternal Cycle",
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Whenever a creature you control dies, you may exile it with two time counters. At the beginning of each upkeep, remove a time counter from each card exiled with Eternal Cycle. When the last is removed, return that card to the battlefield."
)

HOURGLASS_WARRIORS = make_creature(
    name="Hourglass Warriors",
    power=3,
    toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Soldier"},
    text="Vigilance. Whenever Hourglass Warriors attacks, put a time counter on target creature. That creature can't attack or block as long as it has a time counter on it."
)

ENTROPY_TWINS = make_creature(
    name="Entropy Twins",
    power=4,
    toughness=4,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Wizard"},
    text="Menace. When Entropy Twins enters, each opponent discards a card. If they can't, Entropy Twins deals 3 damage to them."
)

TIMELESS_EXPLORER = make_creature(
    name="Timeless Explorer",
    power=2,
    toughness=3,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Scout"},
    text="When Timeless Explorer enters, search your library for a basic land card, reveal it, put it into your hand, then shuffle. You may play an additional land this turn."
)

SUSPENDED_SOLDIER = make_creature(
    name="Suspended Soldier",
    power=3,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Suspend 2 — {W}. When Suspended Soldier enters, create a 1/1 white Soldier creature token."
)

TEMPORAL_MIST = make_instant(
    name="Temporal Mist",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Tap up to two target creatures. Those creatures don't untap during their controllers' next untap steps."
)

DECAY_TOUCH = make_instant(
    name="Decay Touch",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn."
)

ACCELERATED_STRIKE = make_instant(
    name="Accelerated Strike",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +2/+0 and gains first strike until end of turn."
)

TIMELESS_VIGOR = make_instant(
    name="Timeless Vigor",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +2/+2 until end of turn. If it has a time counter on it, it gets +4/+4 instead."
)

MOMENT_PRESERVED = make_instant(
    name="Moment Preserved",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gains indestructible until end of turn. Put a time counter on it."
)

TIME_WARDEN = make_creature(
    name="Time Warden",
    power=2,
    toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Whenever you put a time counter on a permanent, scry 1."
)

ENTROPY_PRIEST = make_creature(
    name="Entropy Priest",
    power=2,
    toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Cleric"},
    text="Whenever another creature dies, you gain 1 life."
)

ACCELERATED_SCOUT = make_creature(
    name="Accelerated Scout",
    power=2,
    toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Scout"},
    text="Haste. When Accelerated Scout enters, scry 1."
)

GROVE_TENDER = make_creature(
    name="Grove Tender",
    power=1,
    toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    text="{T}: Add {G}. {T}: Put a +1/+1 counter on target creature."
)

MONASTERY_ELDER = make_creature(
    name="Monastery Elder",
    power=1,
    toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk"},
    text="Whenever you cast a spell from exile, you gain 2 life."
)


# =============================================================================
# MORE CARDS TO REACH 276
# =============================================================================

SANDS_OF_TIME = make_artifact(
    name="Sands of Time",
    mana_cost="{2}",
    text="Sands of Time enters with three charge counters on it. At the beginning of each upkeep, remove a charge counter. When the last counter is removed, each player returns a creature card from their graveyard to the battlefield."
)

TEMPORAL_DISRUPTION = make_instant(
    name="Temporal Disruption",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {2}. If that spell is countered this way, exile it with a time counter on it instead of putting it into its owner's graveyard."
)

ECHO_CHAMBER = make_artifact(
    name="Echo Chamber",
    mana_cost="{4}",
    text="{3}, {T}: Create a token that's a copy of target creature you control. Sacrifice it at the beginning of the next end step."
)

CHRONO_TOWER = make_land(
    name="Chrono Tower",
    text="{T}: Add {C}. {3}, {T}: Put a time counter on target permanent you control."
)

TIMELESS_FORTRESS = make_land(
    name="Timeless Fortress",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add {W}. Activate only if you control a creature with a time counter on it. {5}, {T}: Creatures you control gain indestructible until end of turn."
)

ECHO_STRIKE = make_instant(
    name="Echo Strike",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Echo Strike deals 2 damage to any target. Echo {1}{R}."
)

TEMPORAL_REBIRTH = make_sorcery(
    name="Temporal Rebirth",
    mana_cost="{3}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    text="Return all creature cards from your graveyard to the battlefield. They gain haste until end of turn. Exile them at the beginning of the next end step."
)

SUSPENDED_HORROR = make_creature(
    name="Suspended Horror",
    power=6,
    toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="Flying, menace. Suspend 4 — {B}{B}. When Suspended Horror enters, each opponent sacrifices a creature."
)

CHRONO_ELEMENTAL = make_creature(
    name="Chrono-Elemental",
    power=4,
    toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="Flying. When Chrono-Elemental enters, put a time counter on each creature you control."
)

TEMPORAL_HARVEST = make_sorcery(
    name="Temporal Harvest",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for up to two basic land cards, reveal them, put them into your hand, then shuffle. Put a time counter on target permanent you control."
)

AGELESS_ARMY = make_sorcery(
    name="Ageless Army",
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    text="Create three 1/1 white Soldier creature tokens. Put a time counter on each of them."
)

RIFT_BOLT = make_instant(
    name="Rift Bolt",
    mana_cost="{R}",
    colors={Color.RED},
    text="Rift Bolt deals 3 damage to any target. Suspend 1 — {R}."
)

ENTROPY_WAVE = make_sorcery(
    name="Entropy Wave",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Each creature gets -1/-1 until end of turn. Draw a card."
)


# =============================================================================
# ADDITIONAL WHITE CARDS
# =============================================================================

HERALD_OF_DAWN = make_creature(
    name="Herald of Dawn",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    text="Lifelink. When Herald of Dawn enters, put a time counter on target creature you control."
)

SENTINEL_OF_AGES = make_creature(
    name="Sentinel of Ages",
    power=3,
    toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Soldier"},
    text="Vigilance. Creatures you control with time counters have vigilance."
)

TEMPORAL_BLESSING = make_instant(
    name="Temporal Blessing",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 until end of turn. If it has a time counter, you gain 2 life."
)

CHRONICLE_KEEPER = make_creature(
    name="Chronicle Keeper",
    power=1,
    toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk"},
    text="At the beginning of your upkeep, scry 1."
)

ETERNAL_LIGHT = make_enchantment(
    name="Eternal Light",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +1/+1. Whenever a creature with a time counter enters under your control, you gain 1 life."
)

TIMELESS_PRAYER = make_instant(
    name="Timeless Prayer",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="You gain 5 life. If you control a creature with a time counter, draw a card."
)

DAWN_WATCHER = make_creature(
    name="Dawn Watcher",
    power=2,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="Flash. Whenever Dawn Watcher enters, you may tap target creature."
)

PRESERVED_KNIGHT = make_creature(
    name="Preserved Knight",
    power=3,
    toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Knight"},
    text="First strike. When Preserved Knight dies, return it to the battlefield at the beginning of the next end step."
)


# =============================================================================
# ADDITIONAL BLUE CARDS
# =============================================================================

RIFT_SCHOLAR = make_creature(
    name="Rift Scholar",
    power=1,
    toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When Rift Scholar enters, draw a card, then discard a card."
)

SUSPENDED_WISDOM = make_sorcery(
    name="Suspended Wisdom",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw two cards. Suspend 2 — {U}."
)

TEMPORAL_CLONE = make_instant(
    name="Temporal Clone",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Create a token that's a copy of target creature. Exile that token at the beginning of the next end step."
)

ECHO_SAVANT = make_creature(
    name="Echo Savant",
    power=2,
    toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Echo {1}{U}. When Echo Savant enters, scry 2."
)

PHASE_WALKER = make_creature(
    name="Phase Walker",
    power=2,
    toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Phase Walker can't be blocked. When Phase Walker deals combat damage to a player, draw a card."
)

TIMELINE_MANIPULATION = make_sorcery(
    name="Timeline Manipulation",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Take an extra turn after this one."
)

TEMPORAL_INSIGHT = make_instant(
    name="Temporal Insight",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Draw two cards, then discard a card."
)

CHRONO_DRAKE = make_creature(
    name="Chrono Drake",
    power=3,
    toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Drake"},
    text="Flying. When Chrono Drake enters, put a time counter on target permanent."
)


# =============================================================================
# ADDITIONAL BLACK CARDS
# =============================================================================

SHADOW_OF_ENTROPY = make_creature(
    name="Shadow of Entropy",
    power=2,
    toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Shade"},
    text="Whenever another creature dies, Shadow of Entropy gets +1/+1 until end of turn."
)

TEMPORAL_DRAIN = make_instant(
    name="Temporal Drain",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Target creature gets -4/-4 until end of turn. You gain 2 life."
)

ECHO_OF_DESPAIR = make_creature(
    name="Echo of Despair",
    power=3,
    toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Echo {1}{B}. When Echo of Despair enters, target opponent discards a card."
)

GRAVE_TENDER = make_creature(
    name="Grave Tender",
    power=1,
    toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="When Grave Tender dies, return target creature card with mana value 2 or less from your graveyard to your hand."
)

DECAY_KNIGHT = make_creature(
    name="Decay Knight",
    power=3,
    toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Skeleton", "Knight"},
    text="Menace. Rewind — When Decay Knight dies, exile it with two time counters."
)

ENTROPY_PLAGUE = make_sorcery(
    name="Entropy Plague",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="All creatures get -3/-3 until end of turn."
)

LIFE_DRAIN = make_instant(
    name="Life Drain",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Target opponent loses 3 life and you gain 3 life."
)

TEMPORAL_HORROR = make_creature(
    name="Temporal Horror",
    power=4,
    toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="Menace. When Temporal Horror enters, each opponent loses 2 life."
)


# =============================================================================
# ADDITIONAL RED CARDS
# =============================================================================

RIFT_RUNNER = make_creature(
    name="Rift Runner",
    power=2,
    toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="Haste."
)

TEMPORAL_FURY = make_instant(
    name="Temporal Fury",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains haste until end of turn."
)

ECHO_OF_RAGE = make_creature(
    name="Echo of Rage",
    power=4,
    toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Haste. Echo {2}{R}. When Echo of Rage enters, it deals 2 damage to any target."
)

SUSPENDED_LIGHTNING = make_instant(
    name="Suspended Lightning",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Suspended Lightning deals 3 damage to any target. Suspend 1 — {R}."
)

CHRONO_GOBLIN = make_creature(
    name="Chrono Goblin",
    power=1,
    toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
    text="Haste. {R}: Chrono Goblin gets +1/+0 until end of turn."
)

RIFT_HAMMER = make_instant(
    name="Rift Hammer",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Rift Hammer deals 4 damage to target creature."
)

ACCELERATED_ASSAULT = make_sorcery(
    name="Accelerated Assault",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Creatures you control get +2/+0 and gain haste until end of turn."
)

ECHO_DRAGON = make_creature(
    name="Echo Dragon",
    power=4,
    toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying. Echo {3}{R}. When Echo Dragon enters, it deals 3 damage to any target."
)


# =============================================================================
# ADDITIONAL GREEN CARDS
# =============================================================================

SPROUT_OF_ETERNITY = make_creature(
    name="Sprout of Eternity",
    power=1,
    toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="At the beginning of your upkeep, put a +1/+1 counter on Sprout of Eternity."
)

TEMPORAL_ROOTS = make_enchantment(
    name="Temporal Roots",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Enchant land. Enchanted land has '{T}: Add two mana of any one color.'"
)

ECHO_OF_NATURE = make_creature(
    name="Echo of Nature",
    power=3,
    toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental"},
    text="Echo {2}{G}. When Echo of Nature enters, search your library for a basic land card, reveal it, put it into your hand, then shuffle."
)

TIMELESS_ELK = make_creature(
    name="Timeless Elk",
    power=3,
    toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elk"},
    text="Vigilance. When Timeless Elk enters, you gain 3 life."
)

CHRONICLE_WOLF = make_creature(
    name="Chronicle Wolf",
    power=2,
    toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Wolf"},
    text="When Chronicle Wolf enters, put a time counter on target creature you control."
)

PRIMAL_ECHO = make_sorcery(
    name="Primal Echo",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Create two 3/3 green Beast creature tokens."
)

GROWTH_SURGE = make_instant(
    name="Growth Surge",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Put a +1/+1 counter on target creature."
)

AGELESS_BEHEMOTH = make_creature(
    name="Ageless Behemoth",
    power=8,
    toughness=8,
    mana_cost="{6}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample. When Ageless Behemoth enters, put a +1/+1 counter on each other creature you control."
)


# =============================================================================
# ADDITIONAL MULTICOLOR CARDS
# =============================================================================

TEMPORAL_CHAMPION = make_creature(
    name="Temporal Champion",
    power=4,
    toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Knight"},
    text="Vigilance, flying. Whenever Temporal Champion deals combat damage to a player, put a time counter on target permanent."
)

ENTROPY_BLOOM_CREATURE = make_creature(
    name="Entropy Blossom",
    power=3,
    toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Plant", "Horror"},
    text="Deathtouch. When Entropy Blossom enters, return target creature card from your graveyard to your hand."
)

CHRONO_STRIKER = make_creature(
    name="Chrono-Striker",
    power=3,
    toughness=2,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Warrior"},
    text="First strike, haste. When Chrono-Striker deals combat damage to a player, you gain 2 life."
)

RIFT_PROPHET = make_creature(
    name="Rift Prophet",
    power=2,
    toughness=3,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Wizard"},
    text="When Rift Prophet enters, look at the top three cards of your library. Put one into your hand and the rest into your graveyard."
)

TEMPORAL_BEAST = make_creature(
    name="Temporal Beast",
    power=5,
    toughness=4,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Beast"},
    text="Trample. When Temporal Beast enters, draw a card and put a time counter on target permanent you control."
)

ACCELERATED_ASSAULT_CREATURE = make_creature(
    name="Accelerated Striker",
    power=3,
    toughness=1,
    mana_cost="{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Warrior"},
    text="Haste, trample."
)

DECAY_HERALD = make_creature(
    name="Decay Herald",
    power=3,
    toughness=4,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon"},
    text="Flying. When Decay Herald enters, each opponent discards a card."
)

ETERNAL_PROTECTOR = make_creature(
    name="Eternal Protector",
    power=3,
    toughness=5,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Angel"},
    text="Flying, vigilance. Other creatures you control get +0/+1."
)


# =============================================================================
# ADDITIONAL ARTIFACTS
# =============================================================================

TIME_CRYSTAL = make_artifact(
    name="Time Crystal",
    mana_cost="{1}",
    text="{T}: Add {C}. {2}, {T}, Sacrifice Time Crystal: Draw a card."
)

CHRONO_LENS = make_artifact(
    name="Chrono Lens",
    mana_cost="{2}",
    text="{1}, {T}: Scry 1. {3}, {T}: Scry 2."
)

SUSPENDED_GOLEM = make_creature(
    name="Suspended Golem",
    power=5,
    toughness=5,
    mana_cost="{5}",
    colors=set(),
    subtypes={"Golem"},
    text="Suspend 3 — {2}. When Suspended Golem enters, put a +1/+1 counter on each creature you control."
)

TEMPORAL_PRISM = make_artifact(
    name="Temporal Prism",
    mana_cost="{3}",
    text="{2}, {T}: Choose a color. Add two mana of that color."
)

ECHO_ARMOR = make_artifact(
    name="Echo Armor",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +1/+1. Echo {2}. When Echo Armor enters, equip it to target creature you control. Equip {1}"
)

RIFT_KEY = make_artifact(
    name="Rift Key",
    mana_cost="{2}",
    text="{T}: Add {C}. {3}, {T}: Exile the top card of your library. You may play it this turn."
)

TIMELESS_CROWN = make_artifact(
    name="Timeless Crown",
    mana_cost="{3}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    text="Equipped creature gets +2/+2 and has 'At the beginning of your upkeep, put a time counter on target permanent.' Equip {3}"
)

ENTROPY_ORB = make_artifact(
    name="Entropy Orb",
    mana_cost="{4}",
    text="At the beginning of your upkeep, each opponent loses 1 life and you gain 1 life."
)


# =============================================================================
# ADDITIONAL LANDS
# =============================================================================

TIMELESS_GROVE = make_land(
    name="Timeless Grove",
    text="Timeless Grove enters tapped. {T}: Add {G}. {3}{G}, {T}: Put a +1/+1 counter on target creature."
)

ENTROPY_MARSH = make_land(
    name="Entropy Marsh",
    text="Entropy Marsh enters tapped. {T}: Add {B}. When Entropy Marsh enters, each player mills one card."
)

ACCELERATED_PEAK = make_land(
    name="Accelerated Peak",
    text="Accelerated Peak enters tapped. {T}: Add {R}. {2}{R}, {T}: Target creature gains haste until end of turn."
)

SUSPENDED_SANCTUARY = make_land(
    name="Suspended Sanctuary",
    text="{T}: Add {C}. {4}, {T}: Exile target creature you control. Return it to the battlefield at the beginning of the next end step."
)

RIFT_NEXUS = make_land(
    name="Rift Nexus",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast spells from exile."
)

TEMPORAL_OASIS = make_land(
    name="Temporal Oasis",
    text="Temporal Oasis enters tapped. {T}: Add {G} or {U}. When Temporal Oasis enters, scry 1."
)

DECAY_TEMPLE = make_land(
    name="Decay Temple",
    text="Decay Temple enters tapped. {T}: Add {B} or {R}. {4}, {T}: Target creature gets -2/-2 until end of turn."
)

ETERNAL_CATHEDRAL = make_land(
    name="Eternal Cathedral",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {T}: Add {W}. Activate only if you control a creature with a time counter. {5}{W}, {T}: You gain 5 life."
)


# =============================================================================
# FINAL CARDS
# =============================================================================

RIFT_STRIDER = make_creature(
    name="Rift Strider",
    power=2,
    toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="When Rift Strider enters, target creature can't be blocked this turn."
)

TEMPORAL_KNIGHT = make_creature(
    name="Temporal Knight",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="First strike. When Temporal Knight enters, you gain 2 life."
)

DECAY_HOUND = make_creature(
    name="Decay Hound",
    power=3,
    toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Dog", "Zombie"},
    text="Menace. When Decay Hound dies, target opponent loses 2 life."
)

CHRONO_CHARGER = make_creature(
    name="Chrono-Charger",
    power=3,
    toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Horse"},
    text="Haste. When Chrono-Charger attacks, it gets +1/+0 until end of turn."
)

TIMELESS_STAG = make_creature(
    name="Timeless Stag",
    power=4,
    toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Elk"},
    text="Trample. When Timeless Stag enters, you may search your library for a basic land card, reveal it, put it into your hand, then shuffle."
)

TEMPORAL_STRIKE = make_instant(
    name="Temporal Strike",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Exile target attacking or blocking creature. Return it to the battlefield at the beginning of the next end step under its owner's control."
)

RIFT_BOLT_SPELL = make_instant(
    name="Rift Surge",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target nonland permanent to its owner's hand."
)

ENTROPY_TOUCH = make_instant(
    name="Entropy's Touch",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gets -1/-1 until end of turn. You gain 1 life."
)

CHRONO_SPARK = make_instant(
    name="Chrono-Spark",
    mana_cost="{R}",
    colors={Color.RED},
    text="Chrono-Spark deals 2 damage to any target."
)

GROWTH_PULSE = make_instant(
    name="Growth Pulse",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +2/+2 until end of turn."
)

SUSPENDED_SCOUT = make_creature(
    name="Suspended Scout",
    power=2,
    toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="Flying. Suspend 1 — {W}."
)

TEMPORAL_FAMILIAR = make_creature(
    name="Temporal Familiar",
    power=1,
    toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Bird"},
    text="Flying. When Temporal Familiar enters, scry 1."
)

ENTROPY_RAT = make_creature(
    name="Entropy Rat",
    power=1,
    toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Rat"},
    text="Whenever Entropy Rat deals combat damage to a player, that player discards a card."
)

RIFT_SPARK = make_creature(
    name="Rift Spark",
    power=1,
    toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Haste. When Rift Spark dies, it deals 1 damage to any target."
)

TIMELESS_SEEDLING = make_creature(
    name="Timeless Seedling",
    power=1,
    toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="{T}: Add {G}."
)


# =============================================================================
# FINAL BATCH
# =============================================================================

TEMPORAL_ARCHON = make_creature(
    name="Temporal Archon",
    power=5,
    toughness=5,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying, vigilance. When Temporal Archon enters, exile all other creatures. Return them at the beginning of the next end step."
)

ECHO_MAGE = make_creature(
    name="Echo Mage",
    power=2,
    toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Echo {1}{U}{U}. When Echo Mage enters, draw two cards."
)

ENTROPY_LORD = make_creature(
    name="Entropy Lord",
    power=6,
    toughness=5,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    supertypes={"Legendary"},
    text="Flying. At the beginning of your upkeep, each opponent sacrifices a creature."
)

SUSPENDED_DRAGON = make_creature(
    name="Suspended Dragon",
    power=5,
    toughness=5,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying, haste. Suspend 3 — {R}{R}. When Suspended Dragon enters, it deals 3 damage to each opponent."
)

ANCIENT_TREANT = make_creature(
    name="Ancient Treant",
    power=6,
    toughness=8,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="Reach, trample. At the beginning of your upkeep, put a +1/+1 counter on Ancient Treant."
)

CHRONO_SPHINX = make_creature(
    name="Chrono-Sphinx",
    power=4,
    toughness=5,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Sphinx"},
    supertypes={"Legendary"},
    text="Flying. Whenever Chrono-Sphinx deals combat damage to a player, take an extra turn after this one. Sacrifice Chrono-Sphinx at the beginning of that turn."
)

TEMPORAL_WARDEN = make_creature(
    name="Temporal Warden",
    power=3,
    toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Flying. Chronicle — At the beginning of your upkeep, you may put a time counter on target creature. Creatures with time counters can't attack you."
)

ENTROPY_CRAWLER = make_creature(
    name="Entropy Crawler",
    power=2,
    toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Insect"},
    text="Deathtouch."
)

RIFT_HUNTER = make_creature(
    name="Rift Hunter",
    power=3,
    toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="Haste. Whenever Rift Hunter attacks, it gets +1/+0 until end of turn."
)

GROVE_SPIRIT = make_creature(
    name="Grove Spirit",
    power=2,
    toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit"},
    text="When Grove Spirit enters, you gain 2 life."
)

TEMPORAL_WARD = make_instant(
    name="Temporal Ward",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gains hexproof until end of turn."
)

RIFT_DENIAL = make_instant(
    name="Rift Denial",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell."
)

ENTROPY_GRASP = make_instant(
    name="Entropy Grasp",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn. If it dies this turn, you draw a card."
)

CHRONO_BLAST = make_instant(
    name="Chrono-Blast",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Chrono-Blast deals 4 damage to target creature or planeswalker."
)

TIMELESS_GROWTH = make_instant(
    name="Timeless Growth",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Put two +1/+1 counters on target creature."
)

SUSPENDED_ARMY = make_sorcery(
    name="Suspended Army",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Create three 1/1 white Soldier creature tokens. Suspend 2 — {W}{W}."
)

TEMPORAL_VISION = make_sorcery(
    name="Temporal Vision",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Draw three cards, then discard a card."
)

ENTROPY_RITUAL = make_sorcery(
    name="Entropy Ritual",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Each player sacrifices a creature. You draw a card for each creature sacrificed this way."
)

ACCELERATED_CHARGE = make_sorcery(
    name="Accelerated Charge",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Creatures you control get +1/+0 and gain haste until end of turn."
)

PRIMAL_GROWTH = make_sorcery(
    name="Primal Growth",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card, put it onto the battlefield, then shuffle."
)

TEMPORAL_BRIDGE = make_enchantment(
    name="Temporal Bridge",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="At the beginning of your upkeep, exile the top card of your library. You may play it this turn."
)

ENTROPY_FIELD = make_enchantment(
    name="Entropy Field",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Creatures your opponents control get -1/-0."
)

ACCELERATED_FLAMES = make_enchantment(
    name="Accelerated Flames",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="At the beginning of your upkeep, Accelerated Flames deals 1 damage to each opponent."
)

TIMELESS_HARMONY = make_enchantment(
    name="Timeless Harmony",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Creatures you control have +0/+1."
)

TEMPORAL_MONUMENT = make_artifact(
    name="Temporal Monument",
    mana_cost="{4}",
    text="{T}: Add {C}{C}. {4}, {T}: Put a time counter on target permanent."
)

CHRONO_AMULET = make_artifact(
    name="Chrono Amulet",
    mana_cost="{2}",
    text="Whenever you put a time counter on a permanent, you gain 1 life."
)

ENTROPY_SHARD = make_artifact(
    name="Entropy Shard",
    mana_cost="{1}",
    text="Whenever a creature dies, you may pay {1}. If you do, draw a card."
)

ACCELERATED_BOOTS = make_artifact(
    name="Accelerated Boots",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +1/+0 and has haste. Equip {1}"
)

CHRONO_GATE = make_land(
    name="Chrono Gate",
    text="Chrono Gate enters tapped. {T}: Add {W} or {U}."
)

ENTROPY_GATE = make_land(
    name="Entropy Gate",
    text="Entropy Gate enters tapped. {T}: Add {B} or {R}."
)

TIMELESS_GATE = make_land(
    name="Timeless Gate",
    text="Timeless Gate enters tapped. {T}: Add {G} or {W}."
)

RIFT_GATEWAY = make_land(
    name="Rift Gateway",
    text="Rift Gateway enters tapped. {T}: Add {U} or {R}."
)

DECAY_GATEWAY = make_land(
    name="Decay Gateway",
    text="Decay Gateway enters tapped. {T}: Add {B} or {G}."
)

TEMPORAL_LANDS = make_land(
    name="Temporal Haven",
    text="{T}: Add {C}. {1}, {T}: Put a time counter on target creature you control."
)

SUSPENDED_CITADEL = make_land(
    name="Suspended Citadel",
    supertypes={"Legendary"},
    text="{T}: Add {C}. Suspend 3 — {0}. When Suspended Citadel enters, each player gains 5 life."
)

ETERNAL_NEXUS = make_land(
    name="Eternal Nexus",
    supertypes={"Legendary"},
    text="{T}: Add {C}. {5}, {T}: Draw two cards."
)

RIFT_HAVEN = make_land(
    name="Rift Haven",
    text="Rift Haven enters tapped. {T}: Add one mana of any color."
)

TEMPORAL_CHAMPION_SMALL = make_creature(
    name="Temporal Squire",
    power=2,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="When Temporal Squire enters, scry 1."
)

ENTROPY_SHADE = make_creature(
    name="Entropy Shade",
    power=1,
    toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Shade"},
    text="{B}: Entropy Shade gets +1/+1 until end of turn."
)


# =============================================================================
# REGISTRY
# =============================================================================

EDGE_OF_ETERNITIES_CARDS = {
    # WHITE
    "Temporal Guardian": TEMPORAL_GUARDIAN,
    "Chrono-Paladin": CHRONO_PALADIN,
    "Keeper of Moments": KEEPER_OF_MOMENTS,
    "Timeless Sentinel": TIMELESS_SENTINEL,
    "Future Sight Oracle": FUTURE_SIGHT_ORACLE,
    "Eternal Adjudicator": ETERNAL_ADJUDICATOR,
    "Moment of Clarity": MOMENT_OF_CLARITY,
    "Temporal Sanctuary": TEMPORAL_SANCTUARY,
    "Chronicle of Ages": CHRONICLE_OF_AGES,
    "Preserved Memory": PRESERVED_MEMORY,
    "Timeline Protector": TIMELINE_PROTECTOR,
    "Dawn of New Era": DAWN_OF_NEW_ERA,
    "Eternity Warden": ETERNITY_WARDEN,
    "Ageless Knight": AGELESS_KNIGHT,
    "Suspended Soldier": SUSPENDED_SOLDIER,
    "Moment Preserved": MOMENT_PRESERVED,
    "Monastery Elder": MONASTERY_ELDER,
    "Preservation Angel": PRESERVATION_ANGEL,
    "Divine Chronicle": DIVINE_CHRONICLE,
    "Ageless Army": AGELESS_ARMY,

    # BLUE
    "Chronomancer Supreme": CHRONOMANCER_SUPREME,
    "Time Weaver": TIME_WEAVER,
    "Echo of Tomorrow": ECHO_OF_TOMORROW,
    "Paradox Entity": PARADOX_ENTITY,
    "Suspended Scholar": SUSPENDED_SCHOLAR,
    "Temporal Loop": TEMPORAL_LOOP,
    "Rewind Moment": REWIND_MOMENT,
    "Glimpse Beyond Time": GLIMPSE_BEYOND_TIME,
    "Time Stop Field": TIME_STOP_FIELD,
    "Chrono-Shift": CHRONO_SHIFT,
    "Future Echo": FUTURE_ECHO,
    "Temporal Anchor": TEMPORAL_ANCHOR,
    "Temporal Rift Mage": TEMPORAL_RIFT_MAGE,
    "Paradox Strike": PARADOX_STRIKE,
    "Time Fracture": TIME_FRACTURE,
    "Echo Duplication": ECHO_DUPLICATION,
    "Time Warden": TIME_WARDEN,
    "Temporal Mist": TEMPORAL_MIST,
    "Chrono-Elemental": CHRONO_ELEMENTAL,
    "Temporal Serpent": TEMPORAL_SERPENT,
    "Temporal Disruption": TEMPORAL_DISRUPTION,

    # BLACK
    "Entropy Wraith": ENTROPY_WRAITH,
    "Chrono-Reaper": CHRONO_REAPER,
    "Timeless Decay": TIMELESS_DECAY,
    "Fate Unwritten": FATE_UNWRITTEN,
    "Echo of Death": ECHO_OF_DEATH,
    "Temporal Vampire": TEMPORAL_VAMPIRE,
    "Decay of Ages": DECAY_OF_AGES,
    "Stolen Moment": STOLEN_MOMENT,
    "Grave Timeline": GRAVE_TIMELINE,
    "Entropy Walker": ENTROPY_WALKER,
    "Temporal Torment": TEMPORAL_TORMENT,
    "Forgotten Ages": FORGOTTEN_AGES,
    "Decay Spirit": DECAY_SPIRIT,
    "Entropy Bolt": ENTROPY_BOLT,
    "Entropy Cascade": ENTROPY_CASCADE,
    "Entropy Priest": ENTROPY_PRIEST,
    "Entropy Demon": ENTROPY_DEMON,
    "Decay Touch": DECAY_TOUCH,
    "Suspended Horror": SUSPENDED_HORROR,
    "Entropy Wave": ENTROPY_WAVE,

    # RED
    "Chrono-Berserker": CHRONO_BERSERKER,
    "Time Rager": TIME_RAGER,
    "Accelerated Dragon": ACCELERATED_DRAGON,
    "Temporal Storm": TEMPORAL_STORM,
    "Rift Elemental": RIFT_ELEMENTAL,
    "Shattered Timeline": SHATTERED_TIMELINE,
    "Chrono-Fury": CHRONO_FURY,
    "Blaze Through Time": BLAZE_THROUGH_TIME,
    "Temporal Phoenix": TEMPORAL_PHOENIX,
    "Echo Flames": ECHO_FLAMES,
    "Chaos Rift": CHAOS_RIFT,
    "Accelerate": ACCELERATE,
    "Chrono-Warrior": CHRONO_WARRIOR,
    "Temporal Blast": TEMPORAL_BLAST,
    "Temporal Inferno": TEMPORAL_INFERNO,
    "Accelerated Scout": ACCELERATED_SCOUT,
    "Accelerated Strike": ACCELERATED_STRIKE,
    "Eternal Flame": ETERNAL_FLAME,
    "Chrono-Giant": CHRONO_GIANT,
    "Echo Strike": ECHO_STRIKE,
    "Rift Bolt": RIFT_BOLT,

    # GREEN
    "Elder Chronomancer": ELDER_CHRONOMANCER,
    "Seedling of Ages": SEEDLING_OF_AGES,
    "Temporal Growth": TEMPORAL_GROWTH,
    "Cycle of Eternity": CYCLE_OF_ETERNITY,
    "Echo of the Wild": ECHO_OF_THE_WILD,
    "Primordial Titan": PRIMORDIAL_TITAN,
    "Timeless Forest": TIMELESS_FOREST,
    "Nature Reclaims": NATURE_RECLAIMS,
    "Chronicle Beast": CHRONICLE_BEAST,
    "Temporal Bloom": TEMPORAL_BLOOM,
    "Ageless Oak": AGELESS_OAK,
    "Growth Through Time": GROWTH_THROUGH_TIME,
    "Timeless Sapling": TIMELESS_SAPLING,
    "Chronicle Growth": CHRONICLE_GROWTH,
    "Eternal Bloom": ETERNAL_BLOOM,
    "Grove Tender": GROVE_TENDER,
    "Timeless Vigor": TIMELESS_VIGOR,
    "Ageless Wurm": AGELESS_WURM,
    "Ancient Guardian": ANCIENT_GUARDIAN,
    "Temporal Harvest": TEMPORAL_HARVEST,

    # MULTICOLOR
    "Kael, Timekeeper": KAEL_TIMEKEEPER,
    "Temporal Twins": TEMPORAL_TWINS,
    "Entropy and Order": ENTROPY_AND_ORDER,
    "Chrono-Dragon": CHRONO_DRAGON,
    "Decay Bloom": DECAY_BLOOM,
    "Temporal Paradox": TEMPORAL_PARADOX,
    "Chrono-Warlord": CHRONO_WARLORD,
    "Nature Mage, Eternal": NATURE_MAGE_ETERNAL,
    "Symbiotic Timeline": SYMBIOTIC_TIMELINE,
    "Rift Walker": RIFT_WALKER,
    "Temporal Ambush": TEMPORAL_AMBUSH,
    "Chrono-Surge": CHRONO_SURGE,
    "Rift Eruption": RIFT_ERUPTION,
    "Temporal Convergence": TEMPORAL_CONVERGENCE,
    "Temporal Shade": TEMPORAL_SHADE,
    "Time Siphon": TIME_SIPHON,
    "Eternal Blessing": ETERNAL_BLESSING,
    "Chrono-Shatter": CHRONO_SHATTER,
    "Temporal Grasp": TEMPORAL_GRASP,
    "Rift Portal": RIFT_PORTAL,
    "Eternal Cycle": ETERNAL_CYCLE,
    "Hourglass Warriors": HOURGLASS_WARRIORS,
    "Entropy Twins": ENTROPY_TWINS,
    "Timeless Explorer": TIMELESS_EXPLORER,
    "Temporal Rebirth": TEMPORAL_REBIRTH,

    # COLORLESS CREATURES
    "Echo Golem": ECHO_GOLEM,
    "Chrono-Sentry": CHRONO_SENTRY,

    # ARTIFACTS
    "Hourglass of Eternity": HOURGLASS_OF_ETERNITY,
    "Chrono Compass": CHRONO_COMPASS,
    "Temporal Blade": TEMPORAL_BLADE,
    "Time Capsule": TIME_CAPSULE,
    "Suspended Relic": SUSPENDED_RELIC,
    "Clock of Ages": CLOCK_OF_AGES,
    "Rift Generator": RIFT_GENERATOR,
    "Aeon Stone": AEON_STONE,
    "Chronolith": CHRONOLITH,
    "Anchor of Time": TEMPORAL_ANCHOR_ARTIFACT,
    "Sands of Time": SANDS_OF_TIME,
    "Echo Chamber": ECHO_CHAMBER,

    # LANDS
    "Timeless Citadel": TIMELESS_CITADEL,
    "Temporal Nexus": TEMPORAL_NEXUS,
    "Decay Wastes": DECAY_WASTES,
    "Eternal Grove": ETERNAL_GROVE,
    "Rift Chasm": RIFT_CHASM,
    "Suspended Island": SUSPENDED_ISLAND,
    "Chrono Spire": CHRONO_SPIRE,
    "Entropy Pool": ENTROPY_POOL,
    "Accelerated Plains": ACCELERATED_PLAINS,
    "Ancient Archive": ANCIENT_ARCHIVE,
    "Chrono Tower": CHRONO_TOWER,
    "Timeless Fortress": TIMELESS_FORTRESS,

    # BASIC LANDS
    "Plains": PLAINS_EOE,
    "Island": ISLAND_EOE,
    "Swamp": SWAMP_EOE,
    "Mountain": MOUNTAIN_EOE,
    "Forest": FOREST_EOE,

    # ADDITIONAL WHITE
    "Herald of Dawn": HERALD_OF_DAWN,
    "Sentinel of Ages": SENTINEL_OF_AGES,
    "Temporal Blessing": TEMPORAL_BLESSING,
    "Chronicle Keeper": CHRONICLE_KEEPER,
    "Eternal Light": ETERNAL_LIGHT,
    "Timeless Prayer": TIMELESS_PRAYER,
    "Dawn Watcher": DAWN_WATCHER,
    "Preserved Knight": PRESERVED_KNIGHT,
    "Temporal Knight": TEMPORAL_KNIGHT,
    "Temporal Strike": TEMPORAL_STRIKE,
    "Suspended Scout": SUSPENDED_SCOUT,

    # ADDITIONAL BLUE
    "Rift Scholar": RIFT_SCHOLAR,
    "Suspended Wisdom": SUSPENDED_WISDOM,
    "Temporal Clone": TEMPORAL_CLONE,
    "Echo Savant": ECHO_SAVANT,
    "Phase Walker": PHASE_WALKER,
    "Timeline Manipulation": TIMELINE_MANIPULATION,
    "Temporal Insight": TEMPORAL_INSIGHT,
    "Chrono Drake": CHRONO_DRAKE,
    "Rift Strider": RIFT_STRIDER,
    "Rift Surge": RIFT_BOLT_SPELL,
    "Temporal Familiar": TEMPORAL_FAMILIAR,

    # ADDITIONAL BLACK
    "Shadow of Entropy": SHADOW_OF_ENTROPY,
    "Temporal Drain": TEMPORAL_DRAIN,
    "Echo of Despair": ECHO_OF_DESPAIR,
    "Grave Tender": GRAVE_TENDER,
    "Decay Knight": DECAY_KNIGHT,
    "Entropy Plague": ENTROPY_PLAGUE,
    "Life Drain": LIFE_DRAIN,
    "Temporal Horror": TEMPORAL_HORROR,
    "Decay Hound": DECAY_HOUND,
    "Entropy's Touch": ENTROPY_TOUCH,
    "Entropy Rat": ENTROPY_RAT,

    # ADDITIONAL RED
    "Rift Runner": RIFT_RUNNER,
    "Temporal Fury": TEMPORAL_FURY,
    "Echo of Rage": ECHO_OF_RAGE,
    "Suspended Lightning": SUSPENDED_LIGHTNING,
    "Chrono Goblin": CHRONO_GOBLIN,
    "Rift Hammer": RIFT_HAMMER,
    "Accelerated Assault": ACCELERATED_ASSAULT,
    "Echo Dragon": ECHO_DRAGON,
    "Chrono-Charger": CHRONO_CHARGER,
    "Chrono-Spark": CHRONO_SPARK,
    "Rift Spark": RIFT_SPARK,

    # ADDITIONAL GREEN
    "Sprout of Eternity": SPROUT_OF_ETERNITY,
    "Temporal Roots": TEMPORAL_ROOTS,
    "Echo of Nature": ECHO_OF_NATURE,
    "Timeless Elk": TIMELESS_ELK,
    "Chronicle Wolf": CHRONICLE_WOLF,
    "Primal Echo": PRIMAL_ECHO,
    "Growth Surge": GROWTH_SURGE,
    "Ageless Behemoth": AGELESS_BEHEMOTH,
    "Timeless Stag": TIMELESS_STAG,
    "Growth Pulse": GROWTH_PULSE,
    "Timeless Seedling": TIMELESS_SEEDLING,

    # ADDITIONAL MULTICOLOR
    "Temporal Champion": TEMPORAL_CHAMPION,
    "Entropy Blossom": ENTROPY_BLOOM_CREATURE,
    "Chrono-Striker": CHRONO_STRIKER,
    "Rift Prophet": RIFT_PROPHET,
    "Temporal Beast": TEMPORAL_BEAST,
    "Accelerated Striker": ACCELERATED_ASSAULT_CREATURE,
    "Decay Herald": DECAY_HERALD,
    "Eternal Protector": ETERNAL_PROTECTOR,

    # ADDITIONAL ARTIFACTS
    "Time Crystal": TIME_CRYSTAL,
    "Chrono Lens": CHRONO_LENS,
    "Suspended Golem": SUSPENDED_GOLEM,
    "Temporal Prism": TEMPORAL_PRISM,
    "Echo Armor": ECHO_ARMOR,
    "Rift Key": RIFT_KEY,
    "Timeless Crown": TIMELESS_CROWN,
    "Entropy Orb": ENTROPY_ORB,

    # ADDITIONAL LANDS
    "Timeless Grove": TIMELESS_GROVE,
    "Entropy Marsh": ENTROPY_MARSH,
    "Accelerated Peak": ACCELERATED_PEAK,
    "Suspended Sanctuary": SUSPENDED_SANCTUARY,
    "Rift Nexus": RIFT_NEXUS,
    "Temporal Oasis": TEMPORAL_OASIS,
    "Decay Temple": DECAY_TEMPLE,
    "Eternal Cathedral": ETERNAL_CATHEDRAL,

    # FINAL BATCH
    "Temporal Archon": TEMPORAL_ARCHON,
    "Echo Mage": ECHO_MAGE,
    "Entropy Lord": ENTROPY_LORD,
    "Suspended Dragon": SUSPENDED_DRAGON,
    "Ancient Treant": ANCIENT_TREANT,
    "Chrono-Sphinx": CHRONO_SPHINX,
    "Temporal Warden": TEMPORAL_WARDEN,
    "Entropy Crawler": ENTROPY_CRAWLER,
    "Rift Hunter": RIFT_HUNTER,
    "Grove Spirit": GROVE_SPIRIT,
    "Temporal Ward": TEMPORAL_WARD,
    "Rift Denial": RIFT_DENIAL,
    "Entropy Grasp": ENTROPY_GRASP,
    "Chrono-Blast": CHRONO_BLAST,
    "Timeless Growth": TIMELESS_GROWTH,
    "Suspended Army": SUSPENDED_ARMY,
    "Temporal Vision": TEMPORAL_VISION,
    "Entropy Ritual": ENTROPY_RITUAL,
    "Accelerated Charge": ACCELERATED_CHARGE,
    "Primal Growth": PRIMAL_GROWTH,
    "Temporal Bridge": TEMPORAL_BRIDGE,
    "Entropy Field": ENTROPY_FIELD,
    "Accelerated Flames": ACCELERATED_FLAMES,
    "Timeless Harmony": TIMELESS_HARMONY,
    "Temporal Monument": TEMPORAL_MONUMENT,
    "Chrono Amulet": CHRONO_AMULET,
    "Entropy Shard": ENTROPY_SHARD,
    "Accelerated Boots": ACCELERATED_BOOTS,
    "Chrono Gate": CHRONO_GATE,
    "Entropy Gate": ENTROPY_GATE,
    "Timeless Gate": TIMELESS_GATE,
    "Rift Gateway": RIFT_GATEWAY,
    "Decay Gateway": DECAY_GATEWAY,
    "Temporal Haven": TEMPORAL_LANDS,
    "Suspended Citadel": SUSPENDED_CITADEL,
    "Eternal Nexus": ETERNAL_NEXUS,
    "Rift Haven": RIFT_HAVEN,
    "Temporal Squire": TEMPORAL_CHAMPION_SMALL,
    "Entropy Shade": ENTROPY_SHADE,
}

print(f"Loaded {len(EDGE_OF_ETERNITIES_CARDS)} Edge of Eternities cards")
