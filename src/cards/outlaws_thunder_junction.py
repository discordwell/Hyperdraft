"""
Outlaws_of_Thunder_Junction (OTJ) Card Implementations

Real card data fetched from Scryfall API.
276 cards in set.
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

ANOTHER_ROUND = make_sorcery(
    name="Another Round",
    mana_cost="{X}{X}{2}{W}",
    colors={Color.WHITE},
    text="Exile any number of creatures you control, then return them to the battlefield under their owner's control. Then repeat this process X more times.",
)

ARCHANGEL_OF_TITHES = make_creature(
    name="Archangel of Tithes",
    power=3, toughness=5,
    mana_cost="{1}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nAs long as this creature is untapped, creatures can't attack you or planeswalkers you control unless their controller pays {1} for each of those creatures.\nAs long as this creature is attacking, creatures can't block unless their controller pays {1} for each of those creatures.",
)

ARMORED_ARMADILLO = make_creature(
    name="Armored Armadillo",
    power=0, toughness=4,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Armadillo"},
    text="Ward {1} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {1}.)\n{3}{W}: This creature gets +X/+0 until end of turn, where X is its toughness.",
)

AVEN_INTERRUPTER = make_creature(
    name="Aven Interrupter",
    power=2, toughness=2,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Bird", "Rogue"},
    text="Flash\nFlying\nWhen this creature enters, exile target spell. It becomes plotted. (Its owner may cast it as a sorcery on a later turn without paying its mana cost.)\nSpells your opponents cast from graveyards or from exile cost {2} more to cast.",
)

BOUNDING_FELIDAR = make_creature(
    name="Bounding Felidar",
    power=4, toughness=7,
    mana_cost="{5}{W}",
    colors={Color.WHITE},
    subtypes={"Beast", "Cat", "Mount"},
    text="Whenever this creature attacks while saddled, put a +1/+1 counter on each other creature you control. You gain 1 life for each of those creatures.\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

BOVINE_INTERVENTION = make_instant(
    name="Bovine Intervention",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Destroy target artifact or creature. Its controller creates a 2/2 white Ox creature token.",
)

BRIDLED_BIGHORN = make_creature(
    name="Bridled Bighorn",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Mount", "Sheep"},
    text="Vigilance\nWhenever this creature attacks while saddled, create a 1/1 white Sheep creature token.\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

CLAIM_JUMPER = make_creature(
    name="Claim Jumper",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Mercenary", "Rabbit"},
    text="Vigilance\nWhen this creature enters, if an opponent controls more lands than you, you may search your library for a Plains card and put it onto the battlefield tapped. Then if an opponent controls more lands than you, repeat this process once. If you search your library this way, shuffle.",
)

DUST_ANIMUS = make_creature(
    name="Dust Animus",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
    text="Flying\nIf you control five or more untapped lands, this creature enters with two +1/+1 counters and a lifelink counter on it.\nPlot {1}{W} (You may pay {1}{W} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

ERIETTES_LULLABY = make_sorcery(
    name="Eriette's Lullaby",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Destroy target tapped creature. You gain 2 life.",
)

FINAL_SHOWDOWN = make_instant(
    name="Final Showdown",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Spree (Choose one or more additional costs.)\n+ {1} — All creatures lose all abilities until end of turn.\n+ {1} — Choose a creature you control. It gains indestructible until end of turn.\n+ {3}{W}{W} — Destroy all creatures.",
)

FORTUNE_LOYAL_STEED = make_creature(
    name="Fortune, Loyal Steed",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Beast", "Mount"},
    supertypes={"Legendary"},
    text="When Fortune enters, scry 2.\nWhenever Fortune attacks while saddled, at end of combat, exile it and up to one creature that saddled it this turn, then return those cards to the battlefield under their owner's control.\nSaddle 1",
)

FRONTIER_SEEKER = make_creature(
    name="Frontier Seeker",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="When this creature enters, look at the top five cards of your library. You may reveal a Mount creature card or a Plains card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
)

GETAWAY_GLAMER = make_instant(
    name="Getaway Glamer",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Exile target nontoken creature. Return it to the battlefield under its owner's control at the beginning of the next end step.\n+ {2} — Destroy target creature if no other creature has greater power.",
)

HIGH_NOON = make_enchantment(
    name="High Noon",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Each player can't cast more than one spell each turn.\n{4}{R}, Sacrifice this enchantment: It deals 5 damage to any target.",
)

HOLY_COW = make_creature(
    name="Holy Cow",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Angel", "Ox"},
    text="Flash\nFlying\nWhen this creature enters, you gain 2 life and scry 1. (Look at the top card of your library. You may put that card on the bottom.)",
)

INVENTIVE_WINGSMITH = make_creature(
    name="Inventive Wingsmith",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Artificer", "Dwarf"},
    text="At the beginning of your end step, if you haven't cast a spell from your hand this turn and this creature doesn't have a flying counter on it, put a flying counter on it.",
)

LASSOED_BY_THE_LAW = make_enchantment(
    name="Lassoed by the Law",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, exile target nonland permanent an opponent controls until this enchantment leaves the battlefield.\nWhen this enchantment enters, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
)

MYSTICAL_TETHER = make_enchantment(
    name="Mystical Tether",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="You may cast this spell as though it had flash if you pay {2} more to cast it.\nWhen this enchantment enters, exile target artifact or creature an opponent controls until this enchantment leaves the battlefield.",
)

NURTURING_PIXIE = make_creature(
    name="Nurturing Pixie",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Faerie", "Rogue"},
    text="Flying\nWhen this creature enters, return up to one target non-Faerie, nonland permanent you control to its owner's hand. If a permanent was returned this way, put a +1/+1 counter on this creature.",
)

OMENPORT_VIGILANTE = make_creature(
    name="Omenport Vigilante",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Mercenary"},
    text="This creature has double strike as long as you've committed a crime this turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

ONE_LAST_JOB = make_sorcery(
    name="One Last Job",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Spree (Choose one or more additional costs.)\n+ {2} — Return target creature card from your graveyard to the battlefield.\n+ {1} — Return target Mount or Vehicle card from your graveyard to the battlefield.\n+ {1} — Return target Aura or Equipment card from your graveyard to the battlefield attached to a creature you control.",
)

OUTLAW_MEDIC = make_creature(
    name="Outlaw Medic",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rogue"},
    text="Lifelink\nWhen this creature dies, draw a card.",
)

PRAIRIE_DOG = make_creature(
    name="Prairie Dog",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Squirrel"},
    text="Lifelink\nAt the beginning of your end step, if you haven't cast a spell from your hand this turn, put a +1/+1 counter on this creature.\n{4}{W}: Until end of turn, if you would put one or more +1/+1 counters on a creature you control, put that many plus one +1/+1 counters on it instead.",
)

PROSPERITY_TYCOON = make_creature(
    name="Prosperity Tycoon",
    power=4, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    text="When this creature enters, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"\n{2}, Sacrifice a token: This creature gains indestructible until end of turn. Tap it. (Damage and effects that say \"destroy\" don't destroy it.)",
)

REQUISITION_RAID = make_sorcery(
    name="Requisition Raid",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Destroy target artifact.\n+ {1} — Destroy target enchantment.\n+ {1} — Put a +1/+1 counter on each creature target player controls.",
)

RUSTLER_RAMPAGE = make_instant(
    name="Rustler Rampage",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Untap all creatures target player controls.\n+ {1} — Target creature gains double strike until end of turn.",
)

SHEPHERD_OF_THE_CLOUDS = make_creature(
    name="Shepherd of the Clouds",
    power=4, toughness=3,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Pegasus"},
    text="Flying, vigilance\nWhen this creature enters, return target permanent card with mana value 3 or less from your graveyard to your hand. Return that card to the battlefield instead if you control a Mount.",
)

SHERIFF_OF_SAFE_PASSAGE = make_creature(
    name="Sheriff of Safe Passage",
    power=0, toughness=0,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="This creature enters with a +1/+1 counter on it plus an additional +1/+1 counter on it for each other creature you control.\nPlot {1}{W} (You may pay {1}{W} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

STAGECOACH_SECURITY = make_creature(
    name="Stagecoach Security",
    power=4, toughness=5,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="When this creature enters, creatures you control get +1/+1 and gain vigilance until end of turn.\nPlot {3}{W} (You may pay {3}{W} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

STEER_CLEAR = make_instant(
    name="Steer Clear",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Steer Clear deals 2 damage to target attacking or blocking creature. Steer Clear deals 4 damage to that creature instead if you controlled a Mount as you cast this spell.",
)

STERLING_KEYKEEPER = make_creature(
    name="Sterling Keykeeper",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Mercenary"},
    text="{2}, {T}: Tap target non-Mount creature.",
)

STERLING_SUPPLIER = make_creature(
    name="Sterling Supplier",
    power=3, toughness=4,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Bird", "Soldier"},
    text="Flying\nWhen this creature enters, put a +1/+1 counter on another target creature you control.",
)

TAKE_UP_THE_SHIELD = make_instant(
    name="Take Up the Shield",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Put a +1/+1 counter on target creature. It gains lifelink and indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)",
)

THUNDER_LASSO = make_artifact(
    name="Thunder Lasso",
    mana_cost="{2}{W}",
    text="When this Equipment enters, attach it to target creature you control.\nEquipped creature gets +1/+1.\nWhenever equipped creature attacks, tap target creature defending player controls.\nEquip {2}",
    subtypes={"Equipment"},
)

TRAINED_ARYNX = make_creature(
    name="Trained Arynx",
    power=3, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Beast", "Cat", "Mount"},
    text="Whenever this creature attacks while saddled, it gains first strike until end of turn. Scry 1. (Look at the top card of your library. You may put that card on the bottom.)\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

VENGEFUL_TOWNSFOLK = make_creature(
    name="Vengeful Townsfolk",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Citizen", "Human"},
    text="Whenever one or more other creatures you control die, put a +1/+1 counter on this creature.",
)

WANTED_GRIFFIN = make_creature(
    name="Wanted Griffin",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Griffin"},
    text="Flying\nWhen this creature dies, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
)

ARCHMAGES_NEWT = make_creature(
    name="Archmage's Newt",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Mount", "Salamander"},
    text="Whenever this creature deals combat damage to a player, target instant or sorcery card in your graveyard gains flashback until end of turn. The flashback cost is equal to its mana cost. That card gains flashback {0} until end of turn instead if this creature is saddled. (You may cast that card from your graveyard for its flashback cost. Then exile it.)\nSaddle 3",
)

CANYON_CRAB = make_creature(
    name="Canyon Crab",
    power=0, toughness=5,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Crab"},
    text="{1}{U}: This creature gets +2/-2 until end of turn.\nAt the beginning of your end step, if you haven't cast a spell from your hand this turn, draw a card, then discard a card.",
)

DARING_THUNDERTHIEF = make_creature(
    name="Daring Thunder-Thief",
    power=4, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Rogue", "Turtle"},
    text="Flash\nThis creature enters tapped.",
)

DEEPMUCK_DESPERADO = make_creature(
    name="Deepmuck Desperado",
    power=2, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Homarid", "Mercenary"},
    text="Whenever you commit a crime, each opponent mills three cards. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

DJINN_OF_FOOLS_FALL = make_creature(
    name="Djinn of Fool's Fall",
    power=4, toughness=3,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Djinn"},
    text="Flying\nPlot {3}{U} (You may pay {3}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

DOUBLE_DOWN = make_enchantment(
    name="Double Down",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Whenever you cast an outlaw spell, copy that spell. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws. Copies of permanent spells become tokens.)",
)

DUELIST_OF_THE_MIND = make_creature(
    name="Duelist of the Mind",
    power=0, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Advisor", "Human"},
    text="Flying, vigilance\nDuelist of the Mind's power is equal to the number of cards you've drawn this turn.\nWhenever you commit a crime, you may draw a card. If you do, discard a card. This ability triggers only once each turn.",
)

EMERGENT_HAUNTING = make_enchantment(
    name="Emergent Haunting",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="At the beginning of your end step, if you haven't cast a spell from your hand this turn and this enchantment isn't a creature, it becomes a 3/3 Spirit creature with flying in addition to its other types.\n{2}{U}: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

FAILED_FORDING = make_instant(
    name="Failed Fording",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target nonland permanent to its owner's hand. If you control a Desert, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

FBLTHP_LOST_ON_THE_RANGE = make_creature(
    name="Fblthp, Lost on the Range",
    power=1, toughness=1,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Homunculus"},
    supertypes={"Legendary"},
    text="Ward {2}\nYou may look at the top card of your library any time.\nThe top card of your library has plot. The plot cost is equal to its mana cost.\nYou may plot nonland cards from the top of your library.",
)

FLEETING_REFLECTION = make_instant(
    name="Fleeting Reflection",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Target creature you control gains hexproof until end of turn. Untap that creature. Until end of turn, it becomes a copy of up to one other target creature.",
)

GERALF_THE_FLESHWRIGHT = make_creature(
    name="Geralf, the Fleshwright",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Whenever you cast a spell during your turn other than your first spell that turn, create a 2/2 blue and black Zombie Rogue creature token.\nWhenever a Zombie you control enters, put a +1/+1 counter on it for each other Zombie that entered the battlefield under your control this turn.",
)

GEYSER_DRAKE = make_creature(
    name="Geyser Drake",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Drake"},
    text="Flying\nDuring turns other than yours, spells you cast cost {1} less to cast.",
)

HARRIER_STRIX = make_creature(
    name="Harrier Strix",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Bird"},
    text="Flying\nWhen this creature enters, tap target permanent.\n{2}{U}: Draw a card, then discard a card.",
)

JAILBREAK_SCHEME = make_sorcery(
    name="Jailbreak Scheme",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Spree (Choose one or more additional costs.)\n+ {3} — Put a +1/+1 counter on target creature. It can't be blocked this turn.\n+ {2} — Target artifact or creature's owner puts it on their choice of the top or bottom of their library.",
)

THE_KEY_TO_THE_VAULT = make_artifact(
    name="The Key to the Vault",
    mana_cost="{1}{U}",
    text="Whenever equipped creature deals combat damage to a player, look at that many cards from the top of your library. You may exile a nonland card from among them. Put the rest on the bottom of your library in a random order. You may cast the exiled card without paying its mana cost.\nEquip {2}{U}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
)

LOAN_SHARK = make_creature(
    name="Loan Shark",
    power=3, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Rogue", "Shark"},
    text="When this creature enters, if you've cast two or more spells this turn, draw a card.\nPlot {3}{U} (You may pay {3}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

MARAUDING_SPHINX = make_creature(
    name="Marauding Sphinx",
    power=3, toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Rogue", "Sphinx"},
    text="Flying, vigilance, ward {2}\nWhenever you commit a crime, surveil 2. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

METAMORPHIC_BLAST = make_instant(
    name="Metamorphic Blast",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Until end of turn, target creature becomes a white Rabbit with base power and toughness 0/1.\n+ {3} — Target player draws two cards.",
)

NIMBLE_BRIGAND = make_creature(
    name="Nimble Brigand",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="This creature can't be blocked if you've committed a crime this turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\nWhenever this creature deals combat damage to a player, draw a card.",
)

OUTLAW_STITCHER = make_creature(
    name="Outlaw Stitcher",
    power=1, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Warlock"},
    text="When this creature enters, create a 2/2 blue and black Zombie Rogue creature token, then put two +1/+1 counters on that token for each spell you've cast this turn other than the first.\nPlot {4}{U} (You may pay {4}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

PEERLESS_ROPEMASTER = make_creature(
    name="Peerless Ropemaster",
    power=4, toughness=4,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="When this creature enters, return up to one target tapped creature to its owner's hand.",
)

PHANTOM_INTERFERENCE = make_instant(
    name="Phantom Interference",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Spree (Choose one or more additional costs.)\n+ {3} — Create a 2/2 white Spirit creature token with flying.\n+ {1} — Counter target spell unless its controller pays {2}.",
)

PLAN_THE_HEIST = make_sorcery(
    name="Plan the Heist",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Surveil 3 if you have no cards in hand. Then draw three cards. (To surveil 3, look at the top three cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\nPlot {3}{U} (You may pay {3}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

RAZZLEDAZZLER = make_creature(
    name="Razzle-Dazzler",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Whenever you cast your second spell each turn, put a +1/+1 counter on this creature. It can't be blocked this turn.",
)

SEIZE_THE_SECRETS = make_sorcery(
    name="Seize the Secrets",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="This spell costs {1} less to cast if you've committed a crime this turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\nDraw two cards.",
)

SHACKLE_SLINGER = make_creature(
    name="Shackle Slinger",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Soldier"},
    text="Whenever you cast your second spell each turn, choose target creature an opponent controls. If it's tapped, put a stun counter on it. Otherwise, tap it. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

SHIFTING_GRIFT = make_sorcery(
    name="Shifting Grift",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Spree (Choose one or more additional costs.)\n+ {2} — Exchange control of two target creatures.\n+ {1} — Exchange control of two target artifacts.\n+ {1} — Exchange control of two target enchantments.",
)

SLICKSHOT_LOCKPICKER = make_creature(
    name="Slickshot Lockpicker",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="When this creature enters, target instant or sorcery card in your graveyard gains flashback until end of turn. The flashback cost is equal to its mana cost. (You may cast that card from your graveyard for its flashback cost. Then exile it.)\nPlot {2}{U} (You may pay {2}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

SLICKSHOT_VAULTBUSTER = make_creature(
    name="Slickshot Vault-Buster",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="Vigilance\nThis creature gets +2/+0 as long as you've committed a crime this turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

SPRING_SPLASHER = make_creature(
    name="Spring Splasher",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Beast", "Frog"},
    text="Whenever this creature attacks, target creature defending player controls gets -3/-0 until end of turn.",
)

STEP_BETWEEN_WORLDS = make_sorcery(
    name="Step Between Worlds",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Each player may shuffle their hand and graveyard into their library. Each player who does draws seven cards. Exile Step Between Worlds.\nPlot {4}{U}{U} (You may pay {4}{U}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

STOIC_SPHINX = make_creature(
    name="Stoic Sphinx",
    power=5, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Sphinx"},
    text="Flash\nFlying\nThis creature has hexproof as long as you haven't cast a spell this turn.",
)

STOP_COLD = make_enchantment(
    name="Stop Cold",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Flash\nEnchant artifact or creature\nWhen this Aura enters, tap enchanted permanent.\nEnchanted permanent loses all abilities and doesn't untap during its controller's untap step.",
    subtypes={"Aura"},
)

TAKE_THE_FALL = make_instant(
    name="Take the Fall",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature gets -1/-0 until end of turn. It gets -4/-0 until end of turn instead if you control an outlaw. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)\nDraw a card.",
)

THIS_TOWN_AINT_BIG_ENOUGH = make_instant(
    name="This Town Ain't Big Enough",
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    text="This spell costs {3} less to cast if it targets a permanent you control.\nReturn up to two target nonland permanents to their owners' hands.",
)

THREE_STEPS_AHEAD = make_instant(
    name="Three Steps Ahead",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Spree (Choose one or more additional costs.)\n+ {1}{U} — Counter target spell.\n+ {3} — Create a token that's a copy of target artifact or creature you control.\n+ {2} — Draw two cards, then discard a card.",
)

VISAGE_BANDIT = make_creature(
    name="Visage Bandit",
    power=2, toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Rogue", "Shapeshifter"},
    text="You may have this creature enter as a copy of a creature you control, except it's a Shapeshifter Rogue in addition to its other types.\nPlot {2}{U} (You may pay {2}{U} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

AMBUSH_GIGAPEDE = make_creature(
    name="Ambush Gigapede",
    power=6, toughness=2,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Insect"},
    text="Flash\nWhen this creature enters, target creature an opponent controls gets -2/-2 until end of turn.",
)

BINDING_NEGOTIATION = make_sorcery(
    name="Binding Negotiation",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target opponent reveals their hand. You may choose a nonland card from it. If you do, they discard it. Otherwise, you may put a face-up exiled card they own into their graveyard.",
)

BLACKSNAG_BUZZARD = make_creature(
    name="Blacksnag Buzzard",
    power=2, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Bird"},
    text="Flying\nThis creature enters with a +1/+1 counter on it if a creature died this turn.\nPlot {1}{B} (You may pay {1}{B} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

BLOOD_HUSTLER = make_creature(
    name="Blood Hustler",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Vampire"},
    text="Whenever you commit a crime, put a +1/+1 counter on this creature. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\n{3}{B}: Target opponent loses 1 life and you gain 1 life.",
)

BONEYARD_DESECRATOR = make_creature(
    name="Boneyard Desecrator",
    power=3, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Mercenary", "Zombie"},
    text="Menace\n{1}{B}, Sacrifice another creature: Put a +1/+1 counter on this creature. If an outlaw was sacrificed this way, create a Treasure token. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)",
)

CAUSTIC_BRONCO = make_creature(
    name="Caustic Bronco",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Horse", "Mount", "Snake"},
    text="Whenever this creature attacks, reveal the top card of your library and put it into your hand. You lose life equal to that card's mana value if this creature isn't saddled. Otherwise, each opponent loses that much life.\nSaddle 3 (Tap any number of other creatures you control with total power 3 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

CONSUMING_ASHES = make_instant(
    name="Consuming Ashes",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Exile target creature. If it had mana value 3 or less, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
)

CORRUPTED_CONVICTION = make_instant(
    name="Corrupted Conviction",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, sacrifice a creature.\nDraw two cards.",
)

DESERTS_DUE = make_instant(
    name="Desert's Due",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn. It gets an additional -1/-1 until end of turn for each Desert you control.",
)

DESPERATE_BLOODSEEKER = make_creature(
    name="Desperate Bloodseeker",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="Lifelink\nWhen this creature enters, target player mills two cards. (They put the top two cards of their library into their graveyard.)",
)

FAKE_YOUR_OWN_DEATH = make_instant(
    name="Fake Your Own Death",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Until end of turn, target creature gets +2/+0 and gains \"When this creature dies, return it to the battlefield tapped under its owner's control and you create a Treasure token.\" (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

FORSAKEN_MINER = make_creature(
    name="Forsaken Miner",
    power=2, toughness=2,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Skeleton"},
    text="This creature can't block.\nWhenever you commit a crime, you may pay {B}. If you do, return this card from your graveyard to the battlefield. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

GISA_THE_HELLRAISER = make_creature(
    name="Gisa, the Hellraiser",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Ward—{2}, Pay 2 life.\nSkeletons and Zombies you control get +1/+1 and have menace.\nWhenever you commit a crime, create two tapped 2/2 blue and black Zombie Rogue creature tokens. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

HOLLOW_MARAUDER = make_creature(
    name="Hollow Marauder",
    power=4, toughness=2,
    mana_cost="{6}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Specter"},
    text="This spell costs {1} less to cast for each creature card in your graveyard.\nFlying\nWhen this creature enters, any number of target opponents each discard a card. For each of those opponents who didn't discard a card with mana value 4 or greater, draw a card.",
)

INSATIABLE_AVARICE = make_sorcery(
    name="Insatiable Avarice",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Spree (Choose one or more additional costs.)\n+ {2} — Search your library for a card, then shuffle and put that card on top.\n+ {B}{B} — Target player draws three cards and loses 3 life.",
)

KAERVEK_THE_PUNISHER = make_creature(
    name="Kaervek, the Punisher",
    power=3, toughness=3,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Whenever you commit a crime, exile up to one target black card from your graveyard and copy it. You may cast the copy. If you do, you lose 2 life. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime. Copies of permanent spells become tokens.)",
)

LIVELY_DIRGE = make_sorcery(
    name="Lively Dirge",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Search your library for a card, put it into your graveyard, then shuffle.\n+ {2} — Return up to two creature cards with total mana value 4 or less from your graveyard to the battlefield.",
)

MOURNERS_SURPRISE = make_sorcery(
    name="Mourner's Surprise",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Return up to one target creature card from your graveyard to your hand. Create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
)

NEUTRALIZE_THE_GUARDS = make_instant(
    name="Neutralize the Guards",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Creatures target opponent controls get -1/-1 until end of turn. Surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
)

NEZUMI_LINKBREAKER = make_creature(
    name="Nezumi Linkbreaker",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Rat", "Warlock"},
    text="When this creature dies, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
)

OVERZEALOUS_MUSCLE = make_creature(
    name="Overzealous Muscle",
    power=5, toughness=4,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Mercenary", "Ogre"},
    text="Whenever you commit a crime during your turn, this creature gains indestructible until end of turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime. Damage and effects that say \"destroy\" don't destroy a creature with indestructible.)",
)

PITILESS_CARNAGE = make_sorcery(
    name="Pitiless Carnage",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Sacrifice any number of permanents you control, then draw that many cards.\nPlot {1}{B}{B} (You may pay {1}{B}{B} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

RAKISH_CREW = make_enchantment(
    name="Rakish Crew",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="When this enchantment enters, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"\nWhenever an outlaw you control dies, each opponent loses 1 life and you gain 1 life. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)",
)

RATTLEBACK_APOTHECARY = make_creature(
    name="Rattleback Apothecary",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Gorgon", "Warlock"},
    text="Deathtouch\nWhenever you commit a crime, target creature you control gains your choice of menace or lifelink until end of turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

RAVEN_OF_FELL_OMENS = make_creature(
    name="Raven of Fell Omens",
    power=1, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Bird"},
    text="Flying\nWhenever you commit a crime, each opponent loses 1 life and you gain 1 life. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

RICTUS_ROBBER = make_creature(
    name="Rictus Robber",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Zombie"},
    text="When this creature enters, if a creature died this turn, create a 2/2 blue and black Zombie Rogue creature token.\nPlot {2}{B} (You may pay {2}{B} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

ROOFTOP_ASSASSIN = make_creature(
    name="Rooftop Assassin",
    power=2, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Vampire"},
    text="Flash\nFlying, lifelink\nWhen this creature enters, destroy target creature an opponent controls that was dealt damage this turn.",
)

RUSH_OF_DREAD = make_sorcery(
    name="Rush of Dread",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Target opponent sacrifices half the creatures they control of their choice, rounded up.\n+ {2} — Target opponent discards half the cards in their hand, rounded up.\n+ {2} — Target opponent loses half their life, rounded up.",
)

SERVANT_OF_THE_STINGER = make_creature(
    name="Servant of the Stinger",
    power=1, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="Deathtouch\nWhenever this creature deals combat damage to a player, if you've committed a crime this turn, you may sacrifice this creature. If you do, search your library for a card, put it into your hand, then shuffle. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

SHOOT_THE_SHERIFF = make_instant(
    name="Shoot the Sheriff",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Destroy target non-outlaw creature. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws. Everyone else is fair game.)",
)

SKULDUGGERY = make_instant(
    name="Skulduggery",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Until end of turn, target creature you control gets +1/+1 and target creature an opponent controls gets -1/-1.",
)

TINYBONES_JOINS_UP = make_enchantment(
    name="Tinybones Joins Up",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="When Tinybones Joins Up enters, any number of target players each discard a card.\nWhenever a legendary creature you control enters, any number of target players each mill a card and lose 1 life.",
    supertypes={"Legendary"},
)

TINYBONES_THE_PICKPOCKET = make_creature(
    name="Tinybones, the Pickpocket",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Skeleton"},
    supertypes={"Legendary"},
    text="Deathtouch\nWhenever Tinybones deals combat damage to a player, you may cast target nonland permanent card from that player's graveyard, and mana of any type can be spent to cast that spell.",
)

TREASURE_DREDGER = make_creature(
    name="Treasure Dredger",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="{1}, {T}, Pay 1 life: Create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

UNFORTUNATE_ACCIDENT = make_instant(
    name="Unfortunate Accident",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Spree (Choose one or more additional costs.)\n+ {2}{B} — Destroy target creature.\n+ {1} — Create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
)

UNSCRUPULOUS_CONTRACTOR = make_creature(
    name="Unscrupulous Contractor",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Human"},
    text="When this creature enters, you may sacrifice a creature. When you do, target player draws two cards and loses 2 life.\nPlot {2}{B} (You may pay {2}{B} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

VADMIR_NEW_BLOOD = make_creature(
    name="Vadmir, New Blood",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Vampire"},
    supertypes={"Legendary"},
    text="Whenever you commit a crime, put a +1/+1 counter on Vadmir. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\nAs long as Vadmir has four or more +1/+1 counters on it, it has menace and lifelink.",
)

VAULT_PLUNDERER = make_creature(
    name="Vault Plunderer",
    power=3, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="When this creature enters, target player draws a card and loses 1 life.",
)

BRIMSTONE_ROUNDUP = make_enchantment(
    name="Brimstone Roundup",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Whenever you cast your second spell each turn, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"\nPlot {2}{R} (You may pay {2}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

CALAMITY_GALLOPING_INFERNO = make_creature(
    name="Calamity, Galloping Inferno",
    power=4, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Horse", "Mount"},
    supertypes={"Legendary"},
    text="Haste\nWhenever Calamity attacks while saddled, choose a nonlegendary creature that saddled it this turn and create a tapped and attacking token that's a copy of it. Sacrifice that token at the beginning of the next end step. Repeat this process once.\nSaddle 1",
)

CAUGHT_IN_THE_CROSSFIRE = make_instant(
    name="Caught in the Crossfire",
    mana_cost="{R}{R}",
    colors={Color.RED},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Caught in the Crossfire deals 2 damage to each outlaw creature. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)\n+ {1} — Caught in the Crossfire deals 2 damage to each non-outlaw creature.",
)

CUNNING_COYOTE = make_creature(
    name="Cunning Coyote",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Coyote"},
    text="Haste\nWhen this creature enters, another target creature you control gets +1/+1 and gains haste until end of turn.\nPlot {1}{R} (You may pay {1}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

DEADEYE_DUELIST = make_creature(
    name="Deadeye Duelist",
    power=1, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Assassin", "Human"},
    text="Reach\n{1}, {T}: This creature deals 1 damage to target opponent.",
)

DEMONIC_RUCKUS = make_enchantment(
    name="Demonic Ruckus",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Enchant creature\nEnchanted creature gets +1/+1 and has menace and trample.\nWhen this Aura is put into a graveyard from the battlefield, draw a card.\nPlot {R} (You may pay {R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
    subtypes={"Aura"},
)

DISCERNING_PEDDLER = make_creature(
    name="Discerning Peddler",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rogue"},
    text="When this creature enters, you may discard a card. If you do, draw a card.",
)

EXPLOSIVE_DERAILMENT = make_instant(
    name="Explosive Derailment",
    mana_cost="{R}",
    colors={Color.RED},
    text="Spree (Choose one or more additional costs.)\n+ {2} — Explosive Derailment deals 4 damage to target creature.\n+ {2} — Destroy target artifact.",
)

FEROCIFICATION = make_enchantment(
    name="Ferocification",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="At the beginning of combat on your turn, choose one —\n• Target creature you control gets +2/+0 until end of turn.\n• Target creature you control gains menace and haste until end of turn.",
)

GILA_COURSER = make_creature(
    name="Gila Courser",
    power=4, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Mount"},
    text="Whenever this creature attacks while saddled, exile the top card of your library. Until the end of your next turn, you may play that card.\nSaddle 1 (Tap any number of other creatures you control with total power 1 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

GREAT_TRAIN_HEIST = make_instant(
    name="Great Train Heist",
    mana_cost="{R}",
    colors={Color.RED},
    text="Spree (Choose one or more additional costs.)\n+ {2}{R} — Untap all creatures you control. If it's your combat phase, there is an additional combat phase after this phase.\n+ {2} — Creatures you control get +1/+0 and gain first strike until end of turn.\n+ {R} — Choose target opponent. Whenever a creature you control deals combat damage to that player this turn, create a tapped Treasure token.",
)

HELL_TO_PAY = make_sorcery(
    name="Hell to Pay",
    mana_cost="{X}{R}",
    colors={Color.RED},
    text="Hell to Pay deals X damage to target creature. Create a number of tapped Treasure tokens equal to the amount of excess damage dealt to that creature this way.",
)

HELLSPUR_BRUTE = make_creature(
    name="Hellspur Brute",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Mercenary", "Minotaur"},
    text="Affinity for outlaws (This spell costs {1} less to cast for each Assassin, Mercenary, Pirate, Rogue, and/or Warlock you control.)\nTrample",
)

HELLSPUR_POSSE_BOSS = make_creature(
    name="Hellspur Posse Boss",
    power=2, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Rogue"},
    text="Other outlaws you control have haste. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)\nWhen this creature enters, create two 1/1 red Mercenary creature tokens with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
)

HIGHWAY_ROBBERY = make_sorcery(
    name="Highway Robbery",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="You may discard a card or sacrifice a land. If you do, draw two cards.\nPlot {1}{R} (You may pay {1}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

IRASCIBLE_WOLVERINE = make_creature(
    name="Irascible Wolverine",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Wolverine"},
    text="When this creature enters, exile the top card of your library. Until end of turn, you may play that card.\nPlot {2}{R} (You may pay {2}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

IRONFIST_PULVERIZER = make_creature(
    name="Iron-Fist Pulverizer",
    power=4, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Giant", "Warrior"},
    text="Reach\nWhenever you cast your second spell each turn, this creature deals 2 damage to target opponent. Scry 1. (Look at the top card of your library. You may put that card on the bottom.)",
)

LONGHORN_SHARPSHOOTER = make_creature(
    name="Longhorn Sharpshooter",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Minotaur", "Rogue"},
    text="Reach\nWhen this card becomes plotted, it deals 2 damage to any target.\nPlot {3}{R} (You may pay {3}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

MAGDA_THE_HOARDMASTER = make_creature(
    name="Magda, the Hoardmaster",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Berserker", "Dwarf"},
    supertypes={"Legendary"},
    text="Whenever you commit a crime, create a tapped Treasure token. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\nSacrifice three Treasures: Create a 4/4 red Scorpion Dragon creature token with flying and haste. Activate only as a sorcery.",
)

MAGEBANE_LIZARD = make_creature(
    name="Magebane Lizard",
    power=1, toughness=4,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Lizard"},
    text="Whenever a player casts a noncreature spell, this creature deals damage to that player equal to the number of noncreature spells they've cast this turn.",
)

MINE_RAIDER = make_creature(
    name="Mine Raider",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rogue"},
    text="Trample\nWhen this creature enters, if you control another outlaw, create a Treasure token. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws. A Treasure token is an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

OUTLAWS_FURY = make_instant(
    name="Outlaws' Fury",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Creatures you control get +2/+0 until end of turn. If you control an outlaw, exile the top card of your library. Until the end of your next turn, you may play that card. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)",
)

PRICKLY_PAIR = make_creature(
    name="Prickly Pair",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Mercenary", "Plant"},
    text="When this creature enters, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
)

QUICK_DRAW = make_instant(
    name="Quick Draw",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature you control gets +1/+1 and gains first strike until end of turn. Creatures target opponent controls lose first strike and double strike until end of turn.",
)

QUILLED_CHARGER = make_creature(
    name="Quilled Charger",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Mount", "Porcupine"},
    text="Whenever this creature attacks while saddled, it gets +1/+2 and gains menace until end of turn. (It can't be blocked except by two or more creatures.)\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

RECKLESS_LACKEY = make_creature(
    name="Reckless Lackey",
    power=1, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Pirate"},
    text="First strike, haste\n{2}{R}, Sacrifice this creature: Draw a card and create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

RESILIENT_ROADRUNNER = make_creature(
    name="Resilient Roadrunner",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Bird"},
    text="Haste, protection from Coyotes\n{3}: This creature can't be blocked this turn except by creatures with haste.",
)

RETURN_THE_FAVOR = make_instant(
    name="Return the Favor",
    mana_cost="{R}{R}",
    colors={Color.RED},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Copy target instant spell, sorcery spell, activated ability, or triggered ability. You may choose new targets for the copy.\n+ {1} — Change the target of target spell or ability with a single target.",
)

RODEO_PYROMANCERS = make_creature(
    name="Rodeo Pyromancers",
    power=3, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Mercenary"},
    text="Whenever you cast your first spell each turn, add {R}{R}.",
)

SCALESTORM_SUMMONER = make_creature(
    name="Scalestorm Summoner",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warlock"},
    text="Whenever this creature attacks, create a 3/1 red Dinosaur creature token if you control a creature with power 4 or greater.",
)

SCORCHING_SHOT = make_sorcery(
    name="Scorching Shot",
    mana_cost="{R}{R}",
    colors={Color.RED},
    text="Scorching Shot deals 5 damage to target creature.",
)

SLICKSHOT_SHOWOFF = make_creature(
    name="Slickshot Show-Off",
    power=1, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Bird", "Wizard"},
    text="Flying, haste\nWhenever you cast a noncreature spell, this creature gets +2/+0 until end of turn.\nPlot {1}{R} (You may pay {1}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

STINGERBACK_TERROR = make_creature(
    name="Stingerback Terror",
    power=7, toughness=7,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon", "Scorpion"},
    text="Flying, trample\nThis creature gets -1/-1 for each card in your hand.\nPlot {2}{R} (You may pay {2}{R} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

TAKE_FOR_A_RIDE = make_sorcery(
    name="Take for a Ride",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Take for a Ride has flash as long as you've committed a crime this turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\nGain control of target creature until end of turn. Untap that creature. It gains haste until end of turn.",
)

TERROR_OF_THE_PEAKS = make_creature(
    name="Terror of the Peaks",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\nSpells your opponents cast that target this creature cost an additional 3 life to cast.\nWhenever another creature you control enters, this creature deals damage equal to that creature's power to any target.",
)

THUNDER_SALVO = make_instant(
    name="Thunder Salvo",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Thunder Salvo deals X damage to target creature, where X is 2 plus the number of other spells you've cast this turn.",
)

TRICK_SHOT = make_instant(
    name="Trick Shot",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="Trick Shot deals 6 damage to target creature and 2 damage to up to one other target creature token.",
)

ALOE_ALCHEMIST = make_creature(
    name="Aloe Alchemist",
    power=3, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Warlock"},
    text="Trample\nWhen this card becomes plotted, target creature gets +3/+2 and gains trample until end of turn.\nPlot {1}{G} (You may pay {1}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

ANKLE_BITER = make_creature(
    name="Ankle Biter",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Snake"},
    text="Deathtouch",
)

BEASTBOND_OUTCASTER = make_creature(
    name="Beastbond Outcaster",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Human"},
    text="When this creature enters, if you control a creature with power 4 or greater, draw a card.\nPlot {1}{G} (You may pay {1}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

BETRAYAL_AT_THE_VAULT = make_instant(
    name="Betrayal at the Vault",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Target creature you control deals damage equal to its power to each of two other target creatures.",
)

BRISTLEPACK_SENTRY = make_creature(
    name="Bristlepack Sentry",
    power=3, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Wolf"},
    text="Defender\nAs long as you control a creature with power 4 or greater, this creature can attack as though it didn't have defender.",
)

BRISTLY_BILL_SPINE_SOWER = make_creature(
    name="Bristly Bill, Spine Sower",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Plant"},
    supertypes={"Legendary"},
    text="Landfall — Whenever a land you control enters, put a +1/+1 counter on target creature.\n{3}{G}{G}: Double the number of +1/+1 counters on each creature you control.",
)

CACTARANTULA = make_creature(
    name="Cactarantula",
    power=6, toughness=5,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Spider"},
    text="This spell costs {1} less to cast if you control a Desert.\nReach\nWhenever this creature becomes the target of a spell or ability an opponent controls, you may draw a card.",
)

COLOSSAL_RATTLEWURM = make_creature(
    name="Colossal Rattlewurm",
    power=6, toughness=5,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Wurm"},
    text="Colossal Rattlewurm has flash as long as you control a Desert.\nTrample\n{1}{G}, Exile this card from your graveyard: Search your library for a Desert card, put it onto the battlefield tapped, then shuffle.",
)

DANCE_OF_THE_TUMBLEWEEDS = make_sorcery(
    name="Dance of the Tumbleweeds",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Spree (Choose one or more additional costs.)\n+ {1} — Search your library for a basic land card or a Desert card, put it onto the battlefield, then shuffle.\n+ {3} — Create an X/X green Elemental creature token, where X is the number of lands you control.",
)

DROVER_GRIZZLY = make_creature(
    name="Drover Grizzly",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Bear", "Mount"},
    text="Whenever this creature attacks while saddled, creatures you control gain trample until end of turn.\nSaddle 1 (Tap any number of other creatures you control with total power 1 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

FREESTRIDER_COMMANDO = make_creature(
    name="Freestrider Commando",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Centaur", "Mercenary"},
    text="This creature enters with two +1/+1 counters on it if it wasn't cast or no mana was spent to cast it.\nPlot {3}{G} (You may pay {3}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

FREESTRIDER_LOOKOUT = make_creature(
    name="Freestrider Lookout",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Rogue"},
    text="Reach\nWhenever you commit a crime, look at the top five cards of your library. You may put a land card from among them onto the battlefield tapped. Put the rest on the bottom of your library in a random order. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

FULL_STEAM_AHEAD = make_sorcery(
    name="Full Steam Ahead",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Until end of turn, each creature you control gets +2/+2 and gains trample and \"This creature can't be blocked by more than one creature.\"",
)

GIANT_BEAVER = make_creature(
    name="Giant Beaver",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Beaver", "Mount"},
    text="Vigilance\nWhenever this creature attacks while saddled, put a +1/+1 counter on target creature that saddled it this turn.\nSaddle 3 (Tap any number of other creatures you control with total power 3 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

GOLD_RUSH = make_instant(
    name="Gold Rush",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Create a Treasure token. Until end of turn, up to one target creature gets +2/+2 for each Treasure you control.",
)

GOLDVEIN_HYDRA = make_creature(
    name="Goldvein Hydra",
    power=0, toughness=0,
    mana_cost="{X}{G}",
    colors={Color.GREEN},
    subtypes={"Hydra"},
    text="Vigilance, trample, haste\nThis creature enters with X +1/+1 counters on it.\nWhen this creature dies, create a number of tapped Treasure tokens equal to its power.",
)

HARDBRISTLE_BANDIT = make_creature(
    name="Hardbristle Bandit",
    power=1, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Rogue"},
    text="{T}: Add one mana of any color.\nWhenever you commit a crime, untap this creature. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

INTREPID_STABLEMASTER = make_creature(
    name="Intrepid Stablemaster",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout"},
    text="Reach\n{T}: Add {G}.\n{T}: Add two mana of any one color. Spend this mana only to cast Mount or Vehicle spells.",
)

MAP_THE_FRONTIER = make_sorcery(
    name="Map the Frontier",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Search your library for up to two basic land cards and/or Desert cards, put them onto the battlefield tapped, then shuffle.",
)

ORNERY_TUMBLEWAGG = make_creature(
    name="Ornery Tumblewagg",
    power=2, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Brushwagg", "Mount"},
    text="At the beginning of combat on your turn, put a +1/+1 counter on target creature.\nWhenever this creature attacks while saddled, double the number of +1/+1 counters on target creature.\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

OUTCASTER_GREENBLADE = make_creature(
    name="Outcaster Greenblade",
    power=1, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Mercenary"},
    text="When this creature enters, search your library for a basic land card or a Desert card, reveal it, put it into your hand, then shuffle.\nThis creature gets +1/+1 for each Desert you control.",
)

OUTCASTER_TRAILBLAZER = make_creature(
    name="Outcaster Trailblazer",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Human"},
    text="When this creature enters, add one mana of any color.\nWhenever another creature you control with power 4 or greater enters, draw a card.\nPlot {2}{G} (You may pay {2}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

PATIENT_NATURALIST = make_creature(
    name="Patient Naturalist",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout"},
    text="When this creature enters, mill three cards. Put a land card from among the milled cards into your hand. If you can't, create a Treasure token. (To mill three cards, put the top three cards of your library into your graveyard.)",
)

RAILWAY_BRAWLER = make_creature(
    name="Railway Brawler",
    power=5, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Rhino", "Warrior"},
    text="Reach, trample\nWhenever another creature you control enters, put X +1/+1 counters on it, where X is its power.\nPlot {3}{G} (You may pay {3}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

RAMBLING_POSSUM = make_creature(
    name="Rambling Possum",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Mount", "Possum"},
    text="Whenever this creature attacks while saddled, it gets +1/+2 until end of turn. Then you may return any number of creatures that saddled it this turn to their owner's hand.\nSaddle 1 (Tap any number of other creatures you control with total power 1 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

RAUCOUS_ENTERTAINER = make_creature(
    name="Raucous Entertainer",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Bard", "Plant"},
    text="{1}, {T}: Put a +1/+1 counter on each creature you control that entered this turn.",
)

REACH_FOR_THE_SKY = make_enchantment(
    name="Reach for the Sky",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Flash\nEnchant creature\nEnchanted creature gets +3/+2 and has reach.\nWhen this Aura is put into a graveyard from the battlefield, draw a card.",
    subtypes={"Aura"},
)

RISE_OF_THE_VARMINTS = make_sorcery(
    name="Rise of the Varmints",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Create X 2/1 green Varmint creature tokens, where X is the number of creature cards in your graveyard.\nPlot {2}{G} (You may pay {2}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

SMUGGLERS_SURPRISE = make_instant(
    name="Smuggler's Surprise",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Spree (Choose one or more additional costs.)\n+ {2} — Mill four cards. You may put up to two creature and/or land cards from among the milled cards into your hand.\n+ {4}{G} — You may put up to two creature cards from your hand onto the battlefield.\n+ {1} — Creatures you control with power 4 or greater gain hexproof and indestructible until end of turn.",
)

SNAKESKIN_VEIL = make_instant(
    name="Snakeskin Veil",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Put a +1/+1 counter on target creature you control. It gains hexproof until end of turn. (It can't be the target of spells or abilities your opponents control.)",
)

SPINEWOODS_ARMADILLO = make_creature(
    name="Spinewoods Armadillo",
    power=7, toughness=7,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Armadillo"},
    text="Reach\nWard {3} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {3}.)\n{1}{G}, Discard this card: Search your library for a basic land card or a Desert card, reveal it, put it into your hand, then shuffle. You gain 3 life.",
)

SPINEWOODS_PALADIN = make_creature(
    name="Spinewoods Paladin",
    power=5, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Knight"},
    text="Trample\nWhen this creature enters, you gain 3 life.\nPlot {3}{G} (You may pay {3}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

STUBBORN_BURROWFIEND = make_creature(
    name="Stubborn Burrowfiend",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Badger", "Beast", "Mount"},
    text="Whenever this creature becomes saddled for the first time each turn, mill two cards, then this creature gets +X/+X until end of turn, where X is the number of creature cards in your graveyard.\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

THROW_FROM_THE_SADDLE = make_sorcery(
    name="Throw from the Saddle",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +1/+1 until end of turn. Put a +1/+1 counter on it instead if it's a Mount. Then it deals damage equal to its power to target creature you don't control.",
)

TRASH_THE_TOWN = make_instant(
    name="Trash the Town",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Spree (Choose one or more additional costs.)\n+ {2} — Put two +1/+1 counters on target creature.\n+ {1} — Target creature gains trample until end of turn.\n+ {1} — Until end of turn, target creature gains \"Whenever this creature deals combat damage to a player, draw two cards.\"",
)

TUMBLEWEED_RISING = make_sorcery(
    name="Tumbleweed Rising",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Create an X/X green Elemental creature token, where X is the greatest power among creatures you control.\nPlot {2}{G} (You may pay {2}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

VORACIOUS_VARMINT = make_creature(
    name="Voracious Varmint",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Varmint"},
    text="Vigilance\n{1}, Sacrifice this creature: Destroy target artifact or enchantment.",
)

AKUL_THE_UNREPENTANT = make_creature(
    name="Akul the Unrepentant",
    power=5, toughness=5,
    mana_cost="{B}{B}{R}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Dragon", "Rogue", "Scorpion"},
    supertypes={"Legendary"},
    text="Flying, trample\nSacrifice three other creatures: You may put a creature card from your hand onto the battlefield. Activate only as a sorcery and only once each turn.",
)

ANNIE_FLASH_THE_VETERAN = make_creature(
    name="Annie Flash, the Veteran",
    power=4, toughness=5,
    mana_cost="{3}{R}{G}{W}",
    colors={Color.GREEN, Color.RED, Color.WHITE},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="Flash\nWhen Annie Flash enters, if you cast it, return target permanent card with mana value 3 or less from your graveyard to the battlefield tapped.\nWhenever Annie Flash becomes tapped, exile the top two cards of your library. You may play those cards this turn.",
)

ANNIE_JOINS_UP = make_enchantment(
    name="Annie Joins Up",
    mana_cost="{1}{R}{G}{W}",
    colors={Color.GREEN, Color.RED, Color.WHITE},
    text="When Annie Joins Up enters, it deals 5 damage to target creature or planeswalker an opponent controls.\nIf a triggered ability of a legendary creature you control triggers, that ability triggers an additional time.",
    supertypes={"Legendary"},
)

ASSIMILATION_AEGIS = make_artifact(
    name="Assimilation Aegis",
    mana_cost="{1}{W}{U}",
    text="When this Equipment enters, exile up to one target creature until this Equipment leaves the battlefield.\nWhenever this Equipment becomes attached to a creature, for as long as this Equipment remains attached to it, that creature becomes a copy of a creature card exiled with this Equipment.\nEquip {2}",
    subtypes={"Equipment"},
)

AT_KNIFEPOINT = make_enchantment(
    name="At Knifepoint",
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="During your turn, outlaws you control have first strike. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)\nWhenever you commit a crime, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\" This ability triggers only once each turn.",
)

BADLANDS_REVIVAL = make_sorcery(
    name="Badlands Revival",
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Return up to one target creature card from your graveyard to the battlefield. Return up to one target permanent card from your graveyard to your hand.",
)

BARON_BERTRAM_GRAYWATER = make_creature(
    name="Baron Bertram Graywater",
    power=3, toughness=4,
    mana_cost="{2}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Noble", "Vampire"},
    supertypes={"Legendary"},
    text="Whenever one or more tokens you control enter, create a 1/1 black Vampire Rogue creature token with lifelink. This ability triggers only once each turn.\n{1}{B}, Sacrifice another creature or artifact: Draw a card.",
)

BONNY_PALL_CLEARCUTTER = make_creature(
    name="Bonny Pall, Clearcutter",
    power=6, toughness=5,
    mana_cost="{3}{G}{U}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Giant", "Scout"},
    supertypes={"Legendary"},
    text="Reach\nWhen Bonny Pall enters, create Beau, a legendary blue Ox creature token with \"Beau's power and toughness are each equal to the number of lands you control.\"\nWhenever you attack, draw a card, then you may put a land card from your hand or graveyard onto the battlefield.",
)

BREECHES_THE_BLASTMAKER = make_creature(
    name="Breeches, the Blastmaker",
    power=3, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Goblin", "Pirate"},
    supertypes={"Legendary"},
    text="Menace\nWhenever you cast your second spell each turn, you may sacrifice an artifact. If you do, flip a coin. When you win the flip, copy that spell. You may choose new targets for the copy. When you lose the flip, Breeches deals damage equal to that spell's mana value to any target.",
)

BRUSE_TARL_ROVING_RANCHER = make_creature(
    name="Bruse Tarl, Roving Rancher",
    power=4, toughness=3,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Oxen you control have double strike.\nWhenever Bruse Tarl enters or attacks, exile the top card of your library. If it's a land card, create a 2/2 white Ox creature token. Otherwise, you may cast it until the end of your next turn.",
)

CACTUSFOLK_SURESHOT = make_creature(
    name="Cactusfolk Sureshot",
    power=4, toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Mercenary", "Plant"},
    text="Reach\nWard {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nAt the beginning of combat on your turn, other creatures you control with power 4 or greater gain trample and haste until end of turn.",
)

CONGREGATION_GRYFF = make_creature(
    name="Congregation Gryff",
    power=1, toughness=4,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hippogriff", "Mount"},
    text="Flying, lifelink\nWhenever this creature attacks while saddled, it gets +X/+X until end of turn, where X is the number of Mounts you control.\nSaddle 3 (Tap any number of other creatures you control with total power 3 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

DOC_AURLOCK_GRIZZLED_GENIUS = make_creature(
    name="Doc Aurlock, Grizzled Genius",
    power=2, toughness=3,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Bear", "Druid"},
    supertypes={"Legendary"},
    text="Spells you cast from your graveyard or from exile cost {2} less to cast.\nPlotting cards from your hand costs {2} less.",
)

ERIETTE_THE_BEGUILER = make_creature(
    name="Eriette, the Beguiler",
    power=4, toughness=4,
    mana_cost="{1}{W}{U}{B}",
    colors={Color.BLACK, Color.BLUE, Color.WHITE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Lifelink\nWhenever an Aura you control becomes attached to a nonland permanent an opponent controls with mana value less than or equal to that Aura's mana value, gain control of that permanent for as long as that Aura is attached to it.",
)

ERTHA_JO_FRONTIER_MENTOR = make_creature(
    name="Ertha Jo, Frontier Mentor",
    power=2, toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Advisor", "Kor"},
    supertypes={"Legendary"},
    text="When Ertha Jo enters, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"\nWhenever you activate an ability that targets a creature or player, copy that ability. You may choose new targets for the copy.",
)

FORM_A_POSSE = make_sorcery(
    name="Form a Posse",
    mana_cost="{X}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Create X 1/1 red Mercenary creature tokens with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"",
)

GHIRED_MIRROR_OF_THE_WILDS = make_creature(
    name="Ghired, Mirror of the Wilds",
    power=3, toughness=3,
    mana_cost="{R}{G}{W}",
    colors={Color.GREEN, Color.RED, Color.WHITE},
    subtypes={"Human", "Shaman"},
    supertypes={"Legendary"},
    text="Haste\nNontoken creatures you control have \"{T}: Create a token that's a copy of target token you control that entered this turn.\"",
)

THE_GITROG_RAVENOUS_RIDE = make_creature(
    name="The Gitrog, Ravenous Ride",
    power=6, toughness=5,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Frog", "Horror", "Mount"},
    supertypes={"Legendary"},
    text="Trample, haste\nWhenever The Gitrog deals combat damage to a player, you may sacrifice a creature that saddled it this turn. If you do, draw X cards, then put up to X land cards from your hand onto the battlefield tapped, where X is the sacrificed creature's power.\nSaddle 1",
)

HONEST_RUTSTEIN = make_creature(
    name="Honest Rutstein",
    power=3, toughness=2,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="When Honest Rutstein enters, return target creature card from your graveyard to your hand.\nCreature spells you cast cost {1} less to cast.",
)

INTIMIDATION_CAMPAIGN = make_enchantment(
    name="Intimidation Campaign",
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    text="When this enchantment enters, each opponent loses 1 life, you gain 1 life, and you draw a card.\nWhenever you commit a crime, you may return this enchantment to its owner's hand. (It returns only from the battlefield. Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

JEM_LIGHTFOOTE_SKY_EXPLORER = make_creature(
    name="Jem Lightfoote, Sky Explorer",
    power=3, toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Scout"},
    supertypes={"Legendary"},
    text="Flying, vigilance\nAt the beginning of your end step, if you haven't cast a spell from your hand this turn, draw a card.",
)

JOLENE_PLUNDERING_PUGILIST = make_creature(
    name="Jolene, Plundering Pugilist",
    power=4, toughness=2,
    mana_cost="{1}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Mercenary"},
    supertypes={"Legendary"},
    text="Whenever you attack with one or more creatures with power 4 or greater, create a Treasure token.\n{1}{R}, Sacrifice a Treasure: Jolene deals 1 damage to any target.",
)

KAMBAL_PROFITEERING_MAYOR = make_creature(
    name="Kambal, Profiteering Mayor",
    power=2, toughness=4,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Advisor", "Human"},
    supertypes={"Legendary"},
    text="Whenever one or more tokens your opponents control enter, for each of them, create a tapped token that's a copy of it. This ability triggers only once each turn.\nWhenever one or more tokens you control enter, each opponent loses 1 life and you gain 1 life.",
)

KELLAN_JOINS_UP = make_enchantment(
    name="Kellan Joins Up",
    mana_cost="{G}{W}{U}",
    colors={Color.GREEN, Color.BLUE, Color.WHITE},
    text="When Kellan Joins Up enters, you may exile a nonland card with mana value 3 or less from your hand. If you do, it becomes plotted. (You may cast it as a sorcery on a later turn without paying its mana cost.)\nWhenever a legendary creature you control enters, put a +1/+1 counter on each creature you control.",
    supertypes={"Legendary"},
)

KELLAN_THE_KID = make_creature(
    name="Kellan, the Kid",
    power=3, toughness=3,
    mana_cost="{G}{W}{U}",
    colors={Color.GREEN, Color.BLUE, Color.WHITE},
    subtypes={"Faerie", "Human", "Rogue"},
    supertypes={"Legendary"},
    text="Flying, lifelink\nWhenever you cast a spell from anywhere other than your hand, you may cast a permanent spell with equal or lesser mana value from your hand without paying its mana cost. If you don't, you may put a land card from your hand onto the battlefield.",
)

KRAUM_VIOLENT_CACOPHONY = make_creature(
    name="Kraum, Violent Cacophony",
    power=2, toughness=3,
    mana_cost="{2}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Horror", "Zombie"},
    supertypes={"Legendary"},
    text="Flying\nWhenever you cast your second spell each turn, put a +1/+1 counter on Kraum and draw a card.",
)

LAUGHING_JASPER_FLINT = make_creature(
    name="Laughing Jasper Flint",
    power=4, toughness=3,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Lizard", "Rogue"},
    supertypes={"Legendary"},
    text="Creatures you control but don't own are Mercenaries in addition to their other types.\nAt the beginning of your upkeep, exile the top X cards of target opponent's library, where X is the number of outlaws you control. Until end of turn, you may cast spells from among those cards, and mana of any type can be spent to cast those spells.",
)

LAZAV_FAMILIAR_STRANGER = make_creature(
    name="Lazav, Familiar Stranger",
    power=1, toughness=4,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Shapeshifter"},
    supertypes={"Legendary"},
    text="Whenever you commit a crime, put a +1/+1 counter on Lazav. Then you may exile a card from a graveyard. If a creature card was exiled this way, you may have Lazav become a copy of that card until end of turn. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

LILAH_UNDEFEATED_SLICKSHOT = make_creature(
    name="Lilah, Undefeated Slickshot",
    power=3, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nWhenever you cast a multicolored instant or sorcery spell from your hand, exile that spell instead of putting it into your graveyard as it resolves. If you do, it becomes plotted. (You may cast it as a sorcery on a later turn without paying its mana cost.)",
)

MAKE_YOUR_OWN_LUCK = make_sorcery(
    name="Make Your Own Luck",
    mana_cost="{3}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    text="Look at the top three cards of your library. You may exile a nonland card from among them. If you do, it becomes plotted. Put the rest into your hand. (You may cast it as a sorcery on a later turn without paying its mana cost.)",
)

MALCOLM_THE_EYES = make_creature(
    name="Malcolm, the Eyes",
    power=2, toughness=2,
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Pirate", "Siren"},
    supertypes={"Legendary"},
    text="Flying, haste\nWhenever you cast your second spell each turn, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

MARCHESA_DEALER_OF_DEATH = make_creature(
    name="Marchesa, Dealer of Death",
    power=3, toughness=4,
    mana_cost="{U}{B}{R}",
    colors={Color.BLACK, Color.RED, Color.BLUE},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="Whenever you commit a crime, you may pay {1}. If you do, look at the top two cards of your library. Put one of them into your hand and the other into your graveyard. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)",
)

MIRIAM_HERD_WHISPERER = make_creature(
    name="Miriam, Herd Whisperer",
    power=3, toughness=2,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Druid", "Human"},
    supertypes={"Legendary"},
    text="During your turn, Mounts and Vehicles you control have hexproof.\nWhenever a Mount or Vehicle you control attacks, put a +1/+1 counter on it.",
)

OBEKA_SPLITTER_OF_SECONDS = make_creature(
    name="Obeka, Splitter of Seconds",
    power=2, toughness=5,
    mana_cost="{1}{U}{B}{R}",
    colors={Color.BLACK, Color.RED, Color.BLUE},
    subtypes={"Ogre", "Warlock"},
    supertypes={"Legendary"},
    text="Menace\nWhenever Obeka deals combat damage to a player, you get that many additional upkeep steps after this phase.",
)

OKO_THE_RINGLEADER = make_planeswalker(
    name="Oko, the Ringleader",
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    loyalty=3,
    subtypes={"Oko"},
    supertypes={"Legendary"},
    text="At the beginning of combat on your turn, Oko becomes a copy of up to one target creature you control until end of turn, except he has hexproof.\n+1: Draw two cards. If you've committed a crime this turn, discard a card. Otherwise, discard two cards.\n−1: Create a 3/3 green Elk creature token.\n−5: For each other nonland permanent you control, create a token that's a copy of that permanent.",
)

PILLAGE_THE_BOG = make_sorcery(
    name="Pillage the Bog",
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Look at the top X cards of your library, where X is twice the number of lands you control. Put one of them into your hand and the rest on the bottom of your library in a random order.\nPlot {1}{B}{G} (You may pay {1}{B}{G} and exile this card from your hand. Cast it as a sorcery on a later turn without paying its mana cost. Plot only as a sorcery.)",
)

RAKDOS_JOINS_UP = make_enchantment(
    name="Rakdos Joins Up",
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="When Rakdos Joins Up enters, return target creature card from your graveyard to the battlefield with two additional +1/+1 counters on it.\nWhenever a legendary creature you control dies, Rakdos Joins Up deals damage equal to that creature's power to target opponent.",
    supertypes={"Legendary"},
)

RAKDOS_THE_MUSCLE = make_creature(
    name="Rakdos, the Muscle",
    power=6, toughness=5,
    mana_cost="{2}{B}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon", "Mercenary"},
    supertypes={"Legendary"},
    text="Flying, trample\nWhenever you sacrifice another creature, exile cards equal to its mana value from the top of target player's library. Until your next end step, you may play those cards, and mana of any type can be spent to cast those spells.\nSacrifice another creature: Rakdos gains indestructible until end of turn. Tap it. Activate only once each turn.",
)

RIKU_OF_MANY_PATHS = make_creature(
    name="Riku of Many Paths",
    power=3, toughness=3,
    mana_cost="{G}{U}{R}",
    colors={Color.GREEN, Color.RED, Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast a modal spell, choose up to X, where X is the number of times you chose a mode for that spell —\n• Exile the top card of your library. Until the end of your next turn, you may play it.\n• Put a +1/+1 counter on Riku. It gains trample until end of turn.\n• Create a 1/1 blue Bird creature token with flying.",
)

ROXANNE_STARFALL_SAVANT = make_creature(
    name="Roxanne, Starfall Savant",
    power=4, toughness=3,
    mana_cost="{3}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Cat", "Druid"},
    supertypes={"Legendary"},
    text="Whenever Roxanne enters or attacks, create a tapped colorless artifact token named Meteorite with \"When this token enters, it deals 2 damage to any target\" and \"{T}: Add one mana of any color.\"\nWhenever you tap an artifact token for mana, add one mana of any type that artifact token produced.",
)

RUTHLESS_LAWBRINGER = make_creature(
    name="Ruthless Lawbringer",
    power=3, toughness=2,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Assassin", "Vampire"},
    text="When this creature enters, you may sacrifice another creature. When you do, destroy target nonland permanent.",
)

SATORU_THE_INFILTRATOR = make_creature(
    name="Satoru, the Infiltrator",
    power=2, toughness=3,
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Ninja", "Rogue"},
    supertypes={"Legendary"},
    text="Menace\nWhenever Satoru and/or one or more other nontoken creatures you control enter, if none of them were cast or no mana was spent to cast them, draw a card.",
)

SELVALA_EAGER_TRAILBLAZER = make_creature(
    name="Selvala, Eager Trailblazer",
    power=4, toughness=5,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Elf", "Scout"},
    supertypes={"Legendary"},
    text="Vigilance\nWhenever you cast a creature spell, create a 1/1 red Mercenary creature token with \"{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.\"\n{T}: Choose a color. Add one mana of that color for each different power among creatures you control.",
)

SERAPHIC_STEED = make_creature(
    name="Seraphic Steed",
    power=2, toughness=2,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Mount", "Unicorn"},
    text="First strike, lifelink\nWhenever this creature attacks while saddled, create a 3/3 white Angel creature token with flying.\nSaddle 4 (Tap any number of other creatures you control with total power 4 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
)

SLICK_SEQUENCE = make_instant(
    name="Slick Sequence",
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    text="Slick Sequence deals 2 damage to any target. If you've cast another spell this turn, draw a card.",
)

TAII_WAKEEN_PERFECT_SHOT = make_creature(
    name="Taii Wakeen, Perfect Shot",
    power=2, toughness=3,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Mercenary"},
    supertypes={"Legendary"},
    text="Whenever a source you control deals noncombat damage to a creature equal to that creature's toughness, draw a card.\n{X}, {T}: If a source you control would deal noncombat damage to a permanent or player this turn, it deals that much damage plus X instead.",
)

VIAL_SMASHER_GLEEFUL_GRENADIER = make_creature(
    name="Vial Smasher, Gleeful Grenadier",
    power=3, toughness=2,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Goblin", "Mercenary"},
    supertypes={"Legendary"},
    text="Whenever another outlaw you control enters, Vial Smasher deals 1 damage to target opponent. (Assassins, Mercenaries, Pirates, Rogues, and Warlocks are outlaws.)",
)

VRASKA_JOINS_UP = make_enchantment(
    name="Vraska Joins Up",
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="When Vraska Joins Up enters, put a deathtouch counter on each creature you control.\nWhenever a legendary creature you control deals combat damage to a player, draw a card.",
    supertypes={"Legendary"},
)

VRASKA_THE_SILENCER = make_creature(
    name="Vraska, the Silencer",
    power=3, toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Assassin", "Gorgon"},
    supertypes={"Legendary"},
    text="Deathtouch\nWhenever a nontoken creature an opponent controls dies, you may pay {1}. If you do, return that card to the battlefield tapped under your control. It's a Treasure artifact with \"{T}, Sacrifice this artifact: Add one mana of any color,\" and it loses all other card types.",
)

WRANGLER_OF_THE_DAMNED = make_creature(
    name="Wrangler of the Damned",
    power=1, toughness=4,
    mana_cost="{3}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Flash\nAt the beginning of your end step, if you haven't cast a spell from your hand this turn, create a 2/2 white Spirit creature token with flying.",
)

WYLIE_DUKE_ATIIN_HERO = make_creature(
    name="Wylie Duke, Atiin Hero",
    power=4, toughness=2,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Ranger"},
    supertypes={"Legendary"},
    text="Vigilance\nWhenever Wylie Duke becomes tapped, you gain 1 life and draw a card.",
)

BANDITS_HAUL = make_artifact(
    name="Bandit's Haul",
    mana_cost="{3}",
    text="Whenever you commit a crime, put a loot counter on this artifact. This ability triggers only once each turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)\n{T}: Add one mana of any color.\n{2}, {T}, Remove two loot counters from this artifact: Draw a card.",
)

BOOM_BOX = make_artifact(
    name="Boom Box",
    mana_cost="{2}",
    text="{6}, {T}, Sacrifice this artifact: Destroy up to one target artifact, up to one target creature, and up to one target land.",
)

GOLD_PAN = make_artifact(
    name="Gold Pan",
    mana_cost="{2}",
    text="When this Equipment enters, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nEquipped creature gets +1/+1.\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

LAVASPUR_BOOTS = make_artifact(
    name="Lavaspur Boots",
    mana_cost="{1}",
    text="Equipped creature gets +1/+0 and has haste and ward {1}. (Whenever it becomes the target of a spell or ability an opponent controls, counter it unless that player pays {1}.)\nEquip {1}",
    subtypes={"Equipment"},
)

LUXURIOUS_LOCOMOTIVE = make_artifact(
    name="Luxurious Locomotive",
    mana_cost="{5}",
    text="Whenever this Vehicle attacks, create a Treasure token for each creature that crewed it this turn. (They're artifacts with \"{T}, Sacrifice this token: Add one mana of any color.\")\nCrew 1. Activate only once each turn. (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
)

MOBILE_HOMESTEAD = make_artifact(
    name="Mobile Homestead",
    mana_cost="{2}",
    text="This Vehicle has haste as long as you control a Mount.\nWhenever this Vehicle attacks, look at the top card of your library. If it's a land card, you may put it onto the battlefield tapped.\nCrew 2 (Tap any number of creatures you control with total power 2 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
)

OASIS_GARDENER = make_artifact_creature(
    name="Oasis Gardener",
    power=2, toughness=2,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Scarecrow"},
    text="When this creature enters, you gain 2 life.\n{T}: Add one mana of any color.",
)

REDROCK_SENTINEL = make_artifact_creature(
    name="Redrock Sentinel",
    power=2, toughness=4,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Golem"},
    text="Defender\n{2}, {T}, Sacrifice a land: Draw a card and create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

SILVER_DEPUTY = make_artifact_creature(
    name="Silver Deputy",
    power=1, toughness=2,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Mercenary"},
    text="When this creature enters, you may search your library for a basic land card or a Desert card, reveal it, then shuffle and put it on top.\n{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery.",
)

STERLING_HOUND = make_artifact_creature(
    name="Sterling Hound",
    power=3, toughness=2,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Dog"},
    text="When this creature enters, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
)

TOMB_TRAWLER = make_artifact_creature(
    name="Tomb Trawler",
    power=0, toughness=4,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Golem"},
    text="{2}: Put target card from your graveyard on the bottom of your library.",
)

ABRADED_BLUFFS = make_land(
    name="Abraded Bluffs",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {R} or {W}.",
    subtypes={"Desert"},
)

ARID_ARCHWAY = make_land(
    name="Arid Archway",
    text="This land enters tapped.\nWhen this land enters, return a land you control to its owner's hand. If another Desert was returned this way, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\n{T}: Add {C}{C}.",
    subtypes={"Desert"},
)

BRISTLING_BACKWOODS = make_land(
    name="Bristling Backwoods",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {R} or {G}.",
    subtypes={"Desert"},
)

CONDUIT_PYLONS = make_land(
    name="Conduit Pylons",
    text="When this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\n{T}: Add {C}.\n{1}, {T}: Add one mana of any color.",
    subtypes={"Desert"},
)

CREOSOTE_HEATH = make_land(
    name="Creosote Heath",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {G} or {W}.",
    subtypes={"Desert"},
)

ERODED_CANYON = make_land(
    name="Eroded Canyon",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {U} or {R}.",
    subtypes={"Desert"},
)

FESTERING_GULCH = make_land(
    name="Festering Gulch",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {B} or {G}.",
    subtypes={"Desert"},
)

FORLORN_FLATS = make_land(
    name="Forlorn Flats",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {W} or {B}.",
    subtypes={"Desert"},
)

JAGGED_BARRENS = make_land(
    name="Jagged Barrens",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {B} or {R}.",
    subtypes={"Desert"},
)

LONELY_ARROYO = make_land(
    name="Lonely Arroyo",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {W} or {U}.",
    subtypes={"Desert"},
)

LUSH_OASIS = make_land(
    name="Lush Oasis",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {G} or {U}.",
    subtypes={"Desert"},
)

MIRAGE_MESA = make_land(
    name="Mirage Mesa",
    text="This land enters tapped. As it enters, choose a color.\n{T}: Add one mana of the chosen color.",
    subtypes={"Desert"},
)

SANDSTORM_VERGE = make_land(
    name="Sandstorm Verge",
    text="{T}: Add {C}.\n{3}, {T}: Target creature can't block this turn. Activate only as a sorcery.",
    subtypes={"Desert"},
)

SOURED_SPRINGS = make_land(
    name="Soured Springs",
    text="This land enters tapped.\nWhen this land enters, it deals 1 damage to target opponent.\n{T}: Add {U} or {B}.",
    subtypes={"Desert"},
)

BUCOLIC_RANCH = make_land(
    name="Bucolic Ranch",
    text="{T}: Add {C}.\n{T}: Add one mana of any color. Spend this mana only to cast a Mount spell.\n{3}, {T}: Look at the top card of your library. If it's a Mount card, you may reveal it and put it into your hand. If you don't put it into your hand, you may put it on the bottom of your library.",
    subtypes={"Desert"},
)

BLOOMING_MARSH = make_land(
    name="Blooming Marsh",
    text="This land enters tapped unless you control two or fewer other lands.\n{T}: Add {B} or {G}.",
)

BOTANICAL_SANCTUM = make_land(
    name="Botanical Sanctum",
    text="This land enters tapped unless you control two or fewer other lands.\n{T}: Add {G} or {U}.",
)

CONCEALED_COURTYARD = make_land(
    name="Concealed Courtyard",
    text="This land enters tapped unless you control two or fewer other lands.\n{T}: Add {W} or {B}.",
)

INSPIRING_VANTAGE = make_land(
    name="Inspiring Vantage",
    text="This land enters tapped unless you control two or fewer other lands.\n{T}: Add {R} or {W}.",
)

SPIREBLUFF_CANAL = make_land(
    name="Spirebluff Canal",
    text="This land enters tapped unless you control two or fewer other lands.\n{T}: Add {U} or {R}.",
)

JACE_REAWAKENED = make_planeswalker(
    name="Jace Reawakened",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    loyalty=3,
    subtypes={"Jace"},
    supertypes={"Legendary"},
    text="You can't cast Jace Reawakened during your first, second, or third turns of the game.\n+1: Draw a card, then discard a card.\n+1: You may exile a nonland card with mana value 3 or less from your hand. If you do, it becomes plotted.\n−6: Until end of turn, whenever you cast a spell, copy it. You may choose new targets for the copy.",
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

OUTLAWS_THUNDER_JUNCTION_CARDS = {
    "Another Round": ANOTHER_ROUND,
    "Archangel of Tithes": ARCHANGEL_OF_TITHES,
    "Armored Armadillo": ARMORED_ARMADILLO,
    "Aven Interrupter": AVEN_INTERRUPTER,
    "Bounding Felidar": BOUNDING_FELIDAR,
    "Bovine Intervention": BOVINE_INTERVENTION,
    "Bridled Bighorn": BRIDLED_BIGHORN,
    "Claim Jumper": CLAIM_JUMPER,
    "Dust Animus": DUST_ANIMUS,
    "Eriette's Lullaby": ERIETTES_LULLABY,
    "Final Showdown": FINAL_SHOWDOWN,
    "Fortune, Loyal Steed": FORTUNE_LOYAL_STEED,
    "Frontier Seeker": FRONTIER_SEEKER,
    "Getaway Glamer": GETAWAY_GLAMER,
    "High Noon": HIGH_NOON,
    "Holy Cow": HOLY_COW,
    "Inventive Wingsmith": INVENTIVE_WINGSMITH,
    "Lassoed by the Law": LASSOED_BY_THE_LAW,
    "Mystical Tether": MYSTICAL_TETHER,
    "Nurturing Pixie": NURTURING_PIXIE,
    "Omenport Vigilante": OMENPORT_VIGILANTE,
    "One Last Job": ONE_LAST_JOB,
    "Outlaw Medic": OUTLAW_MEDIC,
    "Prairie Dog": PRAIRIE_DOG,
    "Prosperity Tycoon": PROSPERITY_TYCOON,
    "Requisition Raid": REQUISITION_RAID,
    "Rustler Rampage": RUSTLER_RAMPAGE,
    "Shepherd of the Clouds": SHEPHERD_OF_THE_CLOUDS,
    "Sheriff of Safe Passage": SHERIFF_OF_SAFE_PASSAGE,
    "Stagecoach Security": STAGECOACH_SECURITY,
    "Steer Clear": STEER_CLEAR,
    "Sterling Keykeeper": STERLING_KEYKEEPER,
    "Sterling Supplier": STERLING_SUPPLIER,
    "Take Up the Shield": TAKE_UP_THE_SHIELD,
    "Thunder Lasso": THUNDER_LASSO,
    "Trained Arynx": TRAINED_ARYNX,
    "Vengeful Townsfolk": VENGEFUL_TOWNSFOLK,
    "Wanted Griffin": WANTED_GRIFFIN,
    "Archmage's Newt": ARCHMAGES_NEWT,
    "Canyon Crab": CANYON_CRAB,
    "Daring Thunder-Thief": DARING_THUNDERTHIEF,
    "Deepmuck Desperado": DEEPMUCK_DESPERADO,
    "Djinn of Fool's Fall": DJINN_OF_FOOLS_FALL,
    "Double Down": DOUBLE_DOWN,
    "Duelist of the Mind": DUELIST_OF_THE_MIND,
    "Emergent Haunting": EMERGENT_HAUNTING,
    "Failed Fording": FAILED_FORDING,
    "Fblthp, Lost on the Range": FBLTHP_LOST_ON_THE_RANGE,
    "Fleeting Reflection": FLEETING_REFLECTION,
    "Geralf, the Fleshwright": GERALF_THE_FLESHWRIGHT,
    "Geyser Drake": GEYSER_DRAKE,
    "Harrier Strix": HARRIER_STRIX,
    "Jailbreak Scheme": JAILBREAK_SCHEME,
    "The Key to the Vault": THE_KEY_TO_THE_VAULT,
    "Loan Shark": LOAN_SHARK,
    "Marauding Sphinx": MARAUDING_SPHINX,
    "Metamorphic Blast": METAMORPHIC_BLAST,
    "Nimble Brigand": NIMBLE_BRIGAND,
    "Outlaw Stitcher": OUTLAW_STITCHER,
    "Peerless Ropemaster": PEERLESS_ROPEMASTER,
    "Phantom Interference": PHANTOM_INTERFERENCE,
    "Plan the Heist": PLAN_THE_HEIST,
    "Razzle-Dazzler": RAZZLEDAZZLER,
    "Seize the Secrets": SEIZE_THE_SECRETS,
    "Shackle Slinger": SHACKLE_SLINGER,
    "Shifting Grift": SHIFTING_GRIFT,
    "Slickshot Lockpicker": SLICKSHOT_LOCKPICKER,
    "Slickshot Vault-Buster": SLICKSHOT_VAULTBUSTER,
    "Spring Splasher": SPRING_SPLASHER,
    "Step Between Worlds": STEP_BETWEEN_WORLDS,
    "Stoic Sphinx": STOIC_SPHINX,
    "Stop Cold": STOP_COLD,
    "Take the Fall": TAKE_THE_FALL,
    "This Town Ain't Big Enough": THIS_TOWN_AINT_BIG_ENOUGH,
    "Three Steps Ahead": THREE_STEPS_AHEAD,
    "Visage Bandit": VISAGE_BANDIT,
    "Ambush Gigapede": AMBUSH_GIGAPEDE,
    "Binding Negotiation": BINDING_NEGOTIATION,
    "Blacksnag Buzzard": BLACKSNAG_BUZZARD,
    "Blood Hustler": BLOOD_HUSTLER,
    "Boneyard Desecrator": BONEYARD_DESECRATOR,
    "Caustic Bronco": CAUSTIC_BRONCO,
    "Consuming Ashes": CONSUMING_ASHES,
    "Corrupted Conviction": CORRUPTED_CONVICTION,
    "Desert's Due": DESERTS_DUE,
    "Desperate Bloodseeker": DESPERATE_BLOODSEEKER,
    "Fake Your Own Death": FAKE_YOUR_OWN_DEATH,
    "Forsaken Miner": FORSAKEN_MINER,
    "Gisa, the Hellraiser": GISA_THE_HELLRAISER,
    "Hollow Marauder": HOLLOW_MARAUDER,
    "Insatiable Avarice": INSATIABLE_AVARICE,
    "Kaervek, the Punisher": KAERVEK_THE_PUNISHER,
    "Lively Dirge": LIVELY_DIRGE,
    "Mourner's Surprise": MOURNERS_SURPRISE,
    "Neutralize the Guards": NEUTRALIZE_THE_GUARDS,
    "Nezumi Linkbreaker": NEZUMI_LINKBREAKER,
    "Overzealous Muscle": OVERZEALOUS_MUSCLE,
    "Pitiless Carnage": PITILESS_CARNAGE,
    "Rakish Crew": RAKISH_CREW,
    "Rattleback Apothecary": RATTLEBACK_APOTHECARY,
    "Raven of Fell Omens": RAVEN_OF_FELL_OMENS,
    "Rictus Robber": RICTUS_ROBBER,
    "Rooftop Assassin": ROOFTOP_ASSASSIN,
    "Rush of Dread": RUSH_OF_DREAD,
    "Servant of the Stinger": SERVANT_OF_THE_STINGER,
    "Shoot the Sheriff": SHOOT_THE_SHERIFF,
    "Skulduggery": SKULDUGGERY,
    "Tinybones Joins Up": TINYBONES_JOINS_UP,
    "Tinybones, the Pickpocket": TINYBONES_THE_PICKPOCKET,
    "Treasure Dredger": TREASURE_DREDGER,
    "Unfortunate Accident": UNFORTUNATE_ACCIDENT,
    "Unscrupulous Contractor": UNSCRUPULOUS_CONTRACTOR,
    "Vadmir, New Blood": VADMIR_NEW_BLOOD,
    "Vault Plunderer": VAULT_PLUNDERER,
    "Brimstone Roundup": BRIMSTONE_ROUNDUP,
    "Calamity, Galloping Inferno": CALAMITY_GALLOPING_INFERNO,
    "Caught in the Crossfire": CAUGHT_IN_THE_CROSSFIRE,
    "Cunning Coyote": CUNNING_COYOTE,
    "Deadeye Duelist": DEADEYE_DUELIST,
    "Demonic Ruckus": DEMONIC_RUCKUS,
    "Discerning Peddler": DISCERNING_PEDDLER,
    "Explosive Derailment": EXPLOSIVE_DERAILMENT,
    "Ferocification": FEROCIFICATION,
    "Gila Courser": GILA_COURSER,
    "Great Train Heist": GREAT_TRAIN_HEIST,
    "Hell to Pay": HELL_TO_PAY,
    "Hellspur Brute": HELLSPUR_BRUTE,
    "Hellspur Posse Boss": HELLSPUR_POSSE_BOSS,
    "Highway Robbery": HIGHWAY_ROBBERY,
    "Irascible Wolverine": IRASCIBLE_WOLVERINE,
    "Iron-Fist Pulverizer": IRONFIST_PULVERIZER,
    "Longhorn Sharpshooter": LONGHORN_SHARPSHOOTER,
    "Magda, the Hoardmaster": MAGDA_THE_HOARDMASTER,
    "Magebane Lizard": MAGEBANE_LIZARD,
    "Mine Raider": MINE_RAIDER,
    "Outlaws' Fury": OUTLAWS_FURY,
    "Prickly Pair": PRICKLY_PAIR,
    "Quick Draw": QUICK_DRAW,
    "Quilled Charger": QUILLED_CHARGER,
    "Reckless Lackey": RECKLESS_LACKEY,
    "Resilient Roadrunner": RESILIENT_ROADRUNNER,
    "Return the Favor": RETURN_THE_FAVOR,
    "Rodeo Pyromancers": RODEO_PYROMANCERS,
    "Scalestorm Summoner": SCALESTORM_SUMMONER,
    "Scorching Shot": SCORCHING_SHOT,
    "Slickshot Show-Off": SLICKSHOT_SHOWOFF,
    "Stingerback Terror": STINGERBACK_TERROR,
    "Take for a Ride": TAKE_FOR_A_RIDE,
    "Terror of the Peaks": TERROR_OF_THE_PEAKS,
    "Thunder Salvo": THUNDER_SALVO,
    "Trick Shot": TRICK_SHOT,
    "Aloe Alchemist": ALOE_ALCHEMIST,
    "Ankle Biter": ANKLE_BITER,
    "Beastbond Outcaster": BEASTBOND_OUTCASTER,
    "Betrayal at the Vault": BETRAYAL_AT_THE_VAULT,
    "Bristlepack Sentry": BRISTLEPACK_SENTRY,
    "Bristly Bill, Spine Sower": BRISTLY_BILL_SPINE_SOWER,
    "Cactarantula": CACTARANTULA,
    "Colossal Rattlewurm": COLOSSAL_RATTLEWURM,
    "Dance of the Tumbleweeds": DANCE_OF_THE_TUMBLEWEEDS,
    "Drover Grizzly": DROVER_GRIZZLY,
    "Freestrider Commando": FREESTRIDER_COMMANDO,
    "Freestrider Lookout": FREESTRIDER_LOOKOUT,
    "Full Steam Ahead": FULL_STEAM_AHEAD,
    "Giant Beaver": GIANT_BEAVER,
    "Gold Rush": GOLD_RUSH,
    "Goldvein Hydra": GOLDVEIN_HYDRA,
    "Hardbristle Bandit": HARDBRISTLE_BANDIT,
    "Intrepid Stablemaster": INTREPID_STABLEMASTER,
    "Map the Frontier": MAP_THE_FRONTIER,
    "Ornery Tumblewagg": ORNERY_TUMBLEWAGG,
    "Outcaster Greenblade": OUTCASTER_GREENBLADE,
    "Outcaster Trailblazer": OUTCASTER_TRAILBLAZER,
    "Patient Naturalist": PATIENT_NATURALIST,
    "Railway Brawler": RAILWAY_BRAWLER,
    "Rambling Possum": RAMBLING_POSSUM,
    "Raucous Entertainer": RAUCOUS_ENTERTAINER,
    "Reach for the Sky": REACH_FOR_THE_SKY,
    "Rise of the Varmints": RISE_OF_THE_VARMINTS,
    "Smuggler's Surprise": SMUGGLERS_SURPRISE,
    "Snakeskin Veil": SNAKESKIN_VEIL,
    "Spinewoods Armadillo": SPINEWOODS_ARMADILLO,
    "Spinewoods Paladin": SPINEWOODS_PALADIN,
    "Stubborn Burrowfiend": STUBBORN_BURROWFIEND,
    "Throw from the Saddle": THROW_FROM_THE_SADDLE,
    "Trash the Town": TRASH_THE_TOWN,
    "Tumbleweed Rising": TUMBLEWEED_RISING,
    "Voracious Varmint": VORACIOUS_VARMINT,
    "Akul the Unrepentant": AKUL_THE_UNREPENTANT,
    "Annie Flash, the Veteran": ANNIE_FLASH_THE_VETERAN,
    "Annie Joins Up": ANNIE_JOINS_UP,
    "Assimilation Aegis": ASSIMILATION_AEGIS,
    "At Knifepoint": AT_KNIFEPOINT,
    "Badlands Revival": BADLANDS_REVIVAL,
    "Baron Bertram Graywater": BARON_BERTRAM_GRAYWATER,
    "Bonny Pall, Clearcutter": BONNY_PALL_CLEARCUTTER,
    "Breeches, the Blastmaker": BREECHES_THE_BLASTMAKER,
    "Bruse Tarl, Roving Rancher": BRUSE_TARL_ROVING_RANCHER,
    "Cactusfolk Sureshot": CACTUSFOLK_SURESHOT,
    "Congregation Gryff": CONGREGATION_GRYFF,
    "Doc Aurlock, Grizzled Genius": DOC_AURLOCK_GRIZZLED_GENIUS,
    "Eriette, the Beguiler": ERIETTE_THE_BEGUILER,
    "Ertha Jo, Frontier Mentor": ERTHA_JO_FRONTIER_MENTOR,
    "Form a Posse": FORM_A_POSSE,
    "Ghired, Mirror of the Wilds": GHIRED_MIRROR_OF_THE_WILDS,
    "The Gitrog, Ravenous Ride": THE_GITROG_RAVENOUS_RIDE,
    "Honest Rutstein": HONEST_RUTSTEIN,
    "Intimidation Campaign": INTIMIDATION_CAMPAIGN,
    "Jem Lightfoote, Sky Explorer": JEM_LIGHTFOOTE_SKY_EXPLORER,
    "Jolene, Plundering Pugilist": JOLENE_PLUNDERING_PUGILIST,
    "Kambal, Profiteering Mayor": KAMBAL_PROFITEERING_MAYOR,
    "Kellan Joins Up": KELLAN_JOINS_UP,
    "Kellan, the Kid": KELLAN_THE_KID,
    "Kraum, Violent Cacophony": KRAUM_VIOLENT_CACOPHONY,
    "Laughing Jasper Flint": LAUGHING_JASPER_FLINT,
    "Lazav, Familiar Stranger": LAZAV_FAMILIAR_STRANGER,
    "Lilah, Undefeated Slickshot": LILAH_UNDEFEATED_SLICKSHOT,
    "Make Your Own Luck": MAKE_YOUR_OWN_LUCK,
    "Malcolm, the Eyes": MALCOLM_THE_EYES,
    "Marchesa, Dealer of Death": MARCHESA_DEALER_OF_DEATH,
    "Miriam, Herd Whisperer": MIRIAM_HERD_WHISPERER,
    "Obeka, Splitter of Seconds": OBEKA_SPLITTER_OF_SECONDS,
    "Oko, the Ringleader": OKO_THE_RINGLEADER,
    "Pillage the Bog": PILLAGE_THE_BOG,
    "Rakdos Joins Up": RAKDOS_JOINS_UP,
    "Rakdos, the Muscle": RAKDOS_THE_MUSCLE,
    "Riku of Many Paths": RIKU_OF_MANY_PATHS,
    "Roxanne, Starfall Savant": ROXANNE_STARFALL_SAVANT,
    "Ruthless Lawbringer": RUTHLESS_LAWBRINGER,
    "Satoru, the Infiltrator": SATORU_THE_INFILTRATOR,
    "Selvala, Eager Trailblazer": SELVALA_EAGER_TRAILBLAZER,
    "Seraphic Steed": SERAPHIC_STEED,
    "Slick Sequence": SLICK_SEQUENCE,
    "Taii Wakeen, Perfect Shot": TAII_WAKEEN_PERFECT_SHOT,
    "Vial Smasher, Gleeful Grenadier": VIAL_SMASHER_GLEEFUL_GRENADIER,
    "Vraska Joins Up": VRASKA_JOINS_UP,
    "Vraska, the Silencer": VRASKA_THE_SILENCER,
    "Wrangler of the Damned": WRANGLER_OF_THE_DAMNED,
    "Wylie Duke, Atiin Hero": WYLIE_DUKE_ATIIN_HERO,
    "Bandit's Haul": BANDITS_HAUL,
    "Boom Box": BOOM_BOX,
    "Gold Pan": GOLD_PAN,
    "Lavaspur Boots": LAVASPUR_BOOTS,
    "Luxurious Locomotive": LUXURIOUS_LOCOMOTIVE,
    "Mobile Homestead": MOBILE_HOMESTEAD,
    "Oasis Gardener": OASIS_GARDENER,
    "Redrock Sentinel": REDROCK_SENTINEL,
    "Silver Deputy": SILVER_DEPUTY,
    "Sterling Hound": STERLING_HOUND,
    "Tomb Trawler": TOMB_TRAWLER,
    "Abraded Bluffs": ABRADED_BLUFFS,
    "Arid Archway": ARID_ARCHWAY,
    "Bristling Backwoods": BRISTLING_BACKWOODS,
    "Conduit Pylons": CONDUIT_PYLONS,
    "Creosote Heath": CREOSOTE_HEATH,
    "Eroded Canyon": ERODED_CANYON,
    "Festering Gulch": FESTERING_GULCH,
    "Forlorn Flats": FORLORN_FLATS,
    "Jagged Barrens": JAGGED_BARRENS,
    "Lonely Arroyo": LONELY_ARROYO,
    "Lush Oasis": LUSH_OASIS,
    "Mirage Mesa": MIRAGE_MESA,
    "Sandstorm Verge": SANDSTORM_VERGE,
    "Soured Springs": SOURED_SPRINGS,
    "Bucolic Ranch": BUCOLIC_RANCH,
    "Blooming Marsh": BLOOMING_MARSH,
    "Botanical Sanctum": BOTANICAL_SANCTUM,
    "Concealed Courtyard": CONCEALED_COURTYARD,
    "Inspiring Vantage": INSPIRING_VANTAGE,
    "Spirebluff Canal": SPIREBLUFF_CANAL,
    "Jace Reawakened": JACE_REAWAKENED,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
}

print(f"Loaded {len(OUTLAWS_THUNDER_JUNCTION_CARDS)} Outlaws_of_Thunder_Junction cards")
