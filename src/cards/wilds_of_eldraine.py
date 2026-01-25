"""
Wilds of Eldraine (WOE) Card Implementations

Real card data fetched from Scryfall API.
281 cards in set.
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

ARCHON_OF_THE_WILD_ROSE = make_creature(
    name="Archon of the Wild Rose",
    power=4, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Archon"},
    text="Flying\nOther creatures you control that are enchanted by Auras you control have base power and toughness 4/4 and have flying.",
)

ARCHONS_GLORY = make_instant(
    name="Archon's Glory",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nTarget creature gets +2/+2 until end of turn. If this spell was bargained, that creature also gains flying and lifelink until end of turn.",
)

ARMORY_MICE = make_creature(
    name="Armory Mice",
    power=3, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Mouse"},
    text="Celebration — This creature gets +0/+2 as long as two or more nonland permanents entered the battlefield under your control this turn.",
)

BESOTTED_KNIGHT = make_creature(
    name="Besotted Knight",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="\n// Adventure — Betroth the Beast {W}\nCreate a Royal Role token attached to target creature you control. (Enchanted creature gets +1/+1 and has ward {1}.)",
)

BREAK_THE_SPELL = make_instant(
    name="Break the Spell",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Destroy target enchantment. If a permanent you controlled or a token was destroyed this way, draw a card.",
)

CHARMED_CLOTHIER = make_creature(
    name="Charmed Clothier",
    power=3, toughness=3,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Advisor", "Faerie"},
    text="Flying\nWhen this creature enters, create a Royal Role token attached to another target creature you control. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1 and has ward {1}.)",
)

CHEEKY_HOUSEMOUSE = make_creature(
    name="Cheeky House-Mouse",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Mouse"},
    text="\n// Adventure — Squeak By {W}\nTarget creature you control gets +1/+1 until end of turn. It can't be blocked by creatures with power 3 or greater this turn.",
)

COOPED_UP = make_enchantment(
    name="Cooped Up",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Enchant creature\nEnchanted creature can't attack or block.\n{2}{W}: Exile enchanted creature.",
    subtypes={"Aura"},
)

CURSED_COURTIER = make_creature(
    name="Cursed Courtier",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    text="Lifelink\nWhen this creature enters, create a Cursed Role token attached to it. (Enchanted creature is 1/1.)",
)

DISCERNING_FINANCIER = make_creature(
    name="Discerning Financier",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    text="At the beginning of your upkeep, if an opponent controls more lands than you, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\n{2}{W}: Choose another player. That player gains control of target Treasure you control. You draw a card.",
)

DUTIFUL_GRIFFIN = make_creature(
    name="Dutiful Griffin",
    power=4, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Griffin"},
    text="Flying\n{2}{W}, Sacrifice two enchantments: Return this card from your graveyard to your hand.",
)

EERIE_INTERFERENCE = make_instant(
    name="Eerie Interference",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Prevent all damage that would be dealt to you and creatures you control this turn by creatures.",
)

EXPEL_THE_INTERLOPERS = make_sorcery(
    name="Expel the Interlopers",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Choose a number between 0 and 10. Destroy all creatures with power greater than or equal to the chosen number.",
)

FROSTBRIDGE_GUARD = make_creature(
    name="Frostbridge Guard",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Elemental", "Soldier"},
    text="{2}{W}, {T}: Tap target creature.",
)

GALLANT_PIEWIELDER = make_creature(
    name="Gallant Pie-Wielder",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Dwarf", "Knight"},
    text="First strike\nCelebration — This creature has double strike as long as two or more nonland permanents entered the battlefield under your control this turn.",
)

GLASS_CASKET = make_artifact(
    name="Glass Casket",
    mana_cost="{1}{W}",
    text="When this artifact enters, exile target creature an opponent controls with mana value 3 or less until this artifact leaves the battlefield.",
)

HOPEFUL_VIGIL = make_enchantment(
    name="Hopeful Vigil",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, create a 2/2 white Knight creature token with vigilance.\nWhen this enchantment is put into a graveyard from the battlefield, scry 2.\n{2}{W}: Sacrifice this enchantment.",
)

KELLANS_LIGHTBLADES = make_instant(
    name="Kellan's Lightblades",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nKellan's Lightblades deals 3 damage to target attacking or blocking creature. If this spell was bargained, destroy that creature instead.",
)

KNIGHT_OF_DOVES = make_creature(
    name="Knight of Doves",
    power=1, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Whenever an enchantment you control is put into a graveyard from the battlefield, create a 1/1 white Bird creature token with flying.",
)

MOMENT_OF_VALOR = make_instant(
    name="Moment of Valor",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Untap target creature. It gets +1/+0 and gains indestructible until end of turn.\n• Destroy target creature with power 4 or greater.",
)

MOONSHAKER_CAVALRY = make_creature(
    name="Moonshaker Cavalry",
    power=6, toughness=6,
    mana_cost="{5}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Knight", "Spirit"},
    text="Flying\nWhen this creature enters, creatures you control gain flying and get +X/+X until end of turn, where X is the number of creatures you control.",
)

PLUNGE_INTO_WINTER = make_instant(
    name="Plunge into Winter",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Tap up to one target creature. Scry 1, then draw a card.",
)

THE_PRINCESS_TAKES_FLIGHT = make_enchantment(
    name="The Princess Takes Flight",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Exile up to one target creature.\nII — Target creature you control gets +2/+2 and gains flying until end of turn.\nIII — Return the exiled card to the battlefield under its owner's control.",
    subtypes={"Saga"},
)

PROTECTIVE_PARENTS = make_creature(
    name="Protective Parents",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Peasant"},
    text="When this creature dies, create a Young Hero Role token attached to up to one target creature you control. (If you control another Role on it, put that one into the graveyard. Enchanted creature has \"Whenever this creature attacks, if its toughness is 3 or less, put a +1/+1 counter on it.\")",
)

REGAL_BUNNICORN = make_creature(
    name="Regal Bunnicorn",
    power=0, toughness=0,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Rabbit", "Unicorn"},
    text="Regal Bunnicorn's power and toughness are each equal to the number of nonland permanents you control.",
)

RETURN_TRIUMPHANT = make_sorcery(
    name="Return Triumphant",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Return target creature card with mana value 3 or less from your graveyard to the battlefield. Create a Young Hero Role token attached to it. (Enchanted creature has \"Whenever this creature attacks, if its toughness is 3 or less, put a +1/+1 counter on it.\" If you put another Role on the creature later, put this one into the graveyard.)",
)

RIMEFUR_REINDEER = make_creature(
    name="Rimefur Reindeer",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Elk"},
    text="Whenever an enchantment you control enters, tap target creature an opponent controls.",
)

SAVIOR_OF_THE_SLEEPING = make_creature(
    name="Savior of the Sleeping",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Vigilance\nWhenever an enchantment you control is put into a graveyard from the battlefield, put a +1/+1 counter on this creature.",
)

SLUMBERING_KEEPGUARD = make_creature(
    name="Slumbering Keepguard",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Whenever an enchantment you control enters, scry 1.\n{2}{W}: This creature gets +1/+1 until end of turn for each enchantment you control.",
)

SOLITARY_SANCTUARY = make_enchantment(
    name="Solitary Sanctuary",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, tap target creature an opponent controls and put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nWhenever you tap an untapped creature an opponent controls, put a +1/+1 counter on target creature you control.",
)

SPELLBOOK_VENDOR = make_creature(
    name="Spellbook Vendor",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Peasant"},
    text="Vigilance\nAt the beginning of combat on your turn, you may pay {1}. When you do, create a Sorcerer Role token attached to target creature you control. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1 and has \"Whenever this creature attacks, scry 1.\")",
)

STOCKPILING_CELEBRANT = make_creature(
    name="Stockpiling Celebrant",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Dwarf", "Knight"},
    text="When this creature enters, you may return another target nonland permanent you control to its owner's hand. If you do, scry 2.",
)

STROKE_OF_MIDNIGHT = make_instant(
    name="Stroke of Midnight",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Destroy target nonland permanent. Its controller creates a 1/1 white Human creature token.",
)

A_TALE_FOR_THE_AGES = make_enchantment(
    name="A Tale for the Ages",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Enchanted creatures you control get +2/+2.",
)

THREE_BLIND_MICE = make_enchantment(
    name="Three Blind Mice",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after IV.)\nI — Create a 1/1 white Mouse creature token.\nII, III — Create a token that's a copy of target token you control.\nIV — Creatures you control get +1/+1 and gain vigilance until end of turn.",
    subtypes={"Saga"},
)

TUINVALE_GUIDE = make_creature(
    name="Tuinvale Guide",
    power=2, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Faerie", "Scout"},
    text="Flying\nCelebration — This creature gets +1/+0 and has lifelink as long as two or more nonland permanents entered the battlefield under your control this turn.",
)

UNASSUMING_SAGE = make_creature(
    name="Unassuming Sage",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Peasant", "Wizard"},
    text="When this creature enters, you may pay {2}. If you do, create a Sorcerer Role token attached to it. (Enchanted creature gets +1/+1 and has \"Whenever this creature attacks, scry 1.\")",
)

VIRTUE_OF_LOYALTY = make_enchantment(
    name="Virtue of Loyalty",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="At the beginning of your end step, put a +1/+1 counter on each creature you control. Untap those creatures.\n// Adventure — Ardenvale Fealty {1}{W}\nCreate a 2/2 white Knight creature token with vigilance. (Then exile this card. You may cast the enchantment later from exile.)",
)

WEREFOX_BODYGUARD = make_creature(
    name="Werefox Bodyguard",
    power=2, toughness=2,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Elf", "Fox", "Knight"},
    text="Flash\nWhen this creature enters, exile up to one other target non-Fox creature until this creature leaves the battlefield.\n{1}{W}, Sacrifice this creature: You gain 2 life.",
)

AQUATIC_ALCHEMIST = make_creature(
    name="Aquatic Alchemist",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="Whenever you cast your first instant or sorcery spell each turn, this creature gets +2/+0 until end of turn.\n// Adventure — Bubble Up {2}{U}\nPut target instant or sorcery card from your graveyard on top of your library. (Then exile this card. You may cast the creature later from exile.)",
)

ARCHIVE_DRAGON = make_creature(
    name="Archive Dragon",
    power=4, toughness=6,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Dragon", "Wizard"},
    text="Flying\nWard {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nWhen this creature enters, scry 2.",
)

ASININE_ANTICS = make_sorcery(
    name="Asinine Antics",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="You may cast this spell as though it had flash if you pay {2} more to cast it.\nFor each creature your opponents control, create a Cursed Role token attached to that creature. (If you control another Role on it, put that one into the graveyard. Enchanted creature is 1/1.)",
)

BELUNAS_GATEKEEPER = make_creature(
    name="Beluna's Gatekeeper",
    power=6, toughness=5,
    mana_cost="{5}{U}",
    colors={Color.BLUE},
    subtypes={"Giant", "Soldier"},
    text="\n// Adventure — Entry Denied {1}{U}\nReturn target creature you don't control with mana value 3 or less to its owner's hand. (Then exile this card. You may cast the creature later from exile.)",
)

BITTER_CHILL = make_enchantment(
    name="Bitter Chill",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Enchant creature\nWhen this Aura enters, tap enchanted creature.\nEnchanted creature doesn't untap during its controller's untap step.\nWhen this Aura is put into a graveyard from the battlefield, you may pay {1}. If you do, scry 1, then draw a card.",
    subtypes={"Aura"},
)

CHANCELLOR_OF_TALES = make_creature(
    name="Chancellor of Tales",
    power=2, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Advisor", "Faerie"},
    text="Flying\nWhenever you cast an Adventure spell, you may copy it. You may choose new targets for the copy.",
)

DIMINISHER_WITCH = make_creature(
    name="Diminisher Witch",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Warlock"},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nWhen this creature enters, if it was bargained, create a Cursed Role token attached to target creature an opponent controls. (If you control another Role on it, put that one into the graveyard. Enchanted creature is 1/1.)",
)

DISDAINFUL_STROKE = make_instant(
    name="Disdainful Stroke",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target spell with mana value 4 or greater.",
)

EXTRAORDINARY_JOURNEY = make_enchantment(
    name="Extraordinary Journey",
    mana_cost="{X}{X}{U}{U}",
    colors={Color.BLUE},
    text="When this enchantment enters, exile up to X target creatures. For each of those cards, its owner may play it for as long as it remains exiled.\nWhenever one or more nontoken creatures enter, if one or more of them entered from exile or was cast from exile, you draw a card. This ability triggers only once each turn.",
)

FARSIGHT_RITUAL = make_instant(
    name="Farsight Ritual",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nLook at the top four cards of your library. If this spell was bargained, look at the top eight cards of your library instead. Put two of them into your hand and the rest on the bottom of your library in a random order.",
)

FREEZE_IN_PLACE = make_sorcery(
    name="Freeze in Place",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Tap target creature an opponent controls and put three stun counters on it. Scry 2. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

GADWICKS_FIRST_DUEL = make_enchantment(
    name="Gadwick's First Duel",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Create a Cursed Role token attached to up to one target creature. (If you control another Role on it, put that one into the graveyard. Enchanted creature is 1/1.)\nII — Scry 2.\nIII — When you next cast an instant or sorcery spell with mana value 3 or less this turn, copy that spell. You may choose new targets for the copy.",
    subtypes={"Saga"},
)

GALVANIC_GIANT = make_creature(
    name="Galvanic Giant",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Giant", "Wizard"},
    text="Whenever you cast a spell with mana value 5 or greater, tap target creature an opponent controls and put a stun counter on it.\n// Adventure — Storm Reading {5}{U}{U}\nDraw four cards, then discard two cards. (Then exile this card. You may cast the creature later from exile.)",
)

HORNED_LOCHWHALE = make_creature(
    name="Horned Loch-Whale",
    power=6, toughness=6,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Whale"},
    text="Flash\nWard {2}\nThis creature enters tapped unless it's your turn.\n// Adventure — Lagoon Breach {1}{U}\nThe owner of target attacking creature you don't control puts it on their choice of the top or bottom of their library.",
)

ICE_OUT = make_instant(
    name="Ice Out",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nThis spell costs {1} less to cast if it's bargained.\nCounter target spell.",
)

ICEWROUGHT_SENTRY = make_creature(
    name="Icewrought Sentry",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Soldier"},
    text="Vigilance\nWhenever this creature attacks, you may pay {1}{U}. When you do, tap target creature an opponent controls.\nWhenever you tap an untapped creature an opponent controls, this creature gets +2/+1 until end of turn.",
)

INGENIOUS_PRODIGY = make_creature(
    name="Ingenious Prodigy",
    power=0, toughness=1,
    mana_cost="{X}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Skulk (This creature can't be blocked by creatures with greater power.)\nThis creature enters with X +1/+1 counters on it.\nAt the beginning of your upkeep, if this creature has one or more +1/+1 counters on it, you may remove a +1/+1 counter from it. If you do, draw a card.",
)

INTO_THE_FAE_COURT = make_sorcery(
    name="Into the Fae Court",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Draw three cards. Create a 1/1 blue Faerie creature token with flying and \"This token can block only creatures with flying.\"",
)

JOHANNS_STOPGAP = make_sorcery(
    name="Johann's Stopgap",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nThis spell costs {2} less to cast if it's bargained.\nReturn target nonland permanent to its owner's hand. Draw a card.",
)

LIVING_LECTERN = make_artifact_creature(
    name="Living Lectern",
    power=0, toughness=4,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Construct"},
    text="{1}, Sacrifice this creature: Draw a card. Create a Sorcerer Role token attached to up to one other target creature you control. Activate only as a sorcery. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1 and has \"Whenever this creature attacks, scry 1.\")",
)

MERFOLK_CORALSMITH = make_creature(
    name="Merfolk Coralsmith",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk"},
    text="{1}: This creature gets +1/-1 until end of turn.\nWhen this creature dies, scry 2.",
)

MISLEADING_MOTES = make_instant(
    name="Misleading Motes",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Target creature's owner puts it on their choice of the top or bottom of their library.",
)

MOCKING_SPRITE = make_creature(
    name="Mocking Sprite",
    power=2, toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Rogue"},
    text="Flying\nInstant and sorcery spells you cast cost {1} less to cast.",
)

OBYRAS_ATTENDANTS = make_creature(
    name="Obyra's Attendants",
    power=3, toughness=4,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flying\n// Adventure — Desperate Parry {1}{U}\nTarget creature gets -4/-0 until end of turn. (Then exile this card. You may cast the creature later from exile.)",
)

PICKLOCK_PRANKSTER = make_creature(
    name="Picklock Prankster",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Rogue"},
    text="Flying, vigilance\n// Adventure — Free the Fae {1}{U}\nMill four cards. Then put an instant, sorcery, or Faerie card from among the milled cards into your hand.",
)

QUICK_STUDY = make_instant(
    name="Quick Study",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw two cards.",
)

SLEEPCURSED_FAERIE = make_creature(
    name="Sleep-Cursed Faerie",
    power=3, toughness=3,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flying, ward {2}\nThis creature enters tapped with three stun counters on it. (If it would become untapped, remove a stun counter from it instead.)\n{1}{U}: Untap this creature.",
)

SLEIGHT_OF_HAND = make_sorcery(
    name="Sleight of Hand",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Look at the top two cards of your library. Put one of them into your hand and the other on the bottom of your library.",
)

SNAREMASTER_SPRITE = make_creature(
    name="Snaremaster Sprite",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flying\nWhen this creature enters, you may pay {2}. When you do, tap target creature an opponent controls and put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

SPELL_STUTTER = make_instant(
    name="Spell Stutter",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {2} plus an additional {1} for each Faerie you control.",
)

SPLASHY_SPELLCASTER = make_creature(
    name="Splashy Spellcaster",
    power=2, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Wizard"},
    text="Whenever you cast an instant or sorcery spell, create a Sorcerer Role token attached to up to one other target creature you control. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1 and has \"Whenever this creature attacks, scry 1.\")",
)

STORMKELD_PROWLER = make_creature(
    name="Stormkeld Prowler",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="Whenever you cast a spell with mana value 5 or greater, put two +1/+1 counters on this creature.",
)

SUCCUMB_TO_THE_COLD = make_instant(
    name="Succumb to the Cold",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Tap one or two target creatures an opponent controls. Put a stun counter on each of them. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

TALIONS_MESSENGER = make_creature(
    name="Talion's Messenger",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Noble"},
    text="Flying\nWhenever you attack with one or more Faeries, draw a card, then discard a card. When you discard a card this way, put a +1/+1 counter on target Faerie you control.",
)

TENACIOUS_TOMESEEKER = make_creature(
    name="Tenacious Tomeseeker",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Knight"},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nWhen this creature enters, if it was bargained, return target instant or sorcery card from your graveyard to your hand.",
)

VANTRESS_TRANSMUTER = make_creature(
    name="Vantress Transmuter",
    power=3, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="\n// Adventure — Croaking Curse {1}{U}\nTap target creature. Create a Cursed Role token attached to it. (Enchanted creature is 1/1.)",
)

VIRTUE_OF_KNOWLEDGE = make_enchantment(
    name="Virtue of Knowledge",
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    text="If a permanent entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.\n// Adventure — Vantress Visions {1}{U}\nCopy target activated or triggered ability you control. You may choose new targets for the copy.",
)

WATER_WINGS = make_instant(
    name="Water Wings",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Until end of turn, target creature you control has base power and toughness 4/4 and gains flying and hexproof. (It can't be the target of spells or abilities your opponents control.)",
)

ASHIOK_WICKED_MANIPULATOR = make_planeswalker(
    name="Ashiok, Wicked Manipulator",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    loyalty=5,
    subtypes={"Ashiok"},
    supertypes={"Legendary"},
    text="If you would pay life while your library has at least that many cards in it, exile that many cards from the top of your library instead.\n+1: Look at the top two cards of your library. Exile one of them and put the other into your hand.\n−2: Create two 1/1 black Nightmare creature tokens with \"At the beginning of combat on your turn, if a card was put into exile this turn, put a +1/+1 counter on this token.\"\n−7: Target player exiles the top X cards of their library, where X is the total mana value of cards you own in exile.",
)

ASHIOKS_REAPER = make_creature(
    name="Ashiok's Reaper",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare"},
    text="Whenever an enchantment you control is put into a graveyard from the battlefield, draw a card.",
)

BACK_FOR_SECONDS = make_sorcery(
    name="Back for Seconds",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nReturn up to two target creature cards from your graveyard to your hand. If this spell was bargained, you may put one of those cards with mana value 4 or less onto the battlefield instead of putting it into your hand.",
)

BARROW_NAUGHTY = make_creature(
    name="Barrow Naughty",
    power=1, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie"},
    text="Flying\nThis creature has lifelink as long as you control another Faerie.\n{2}{B}: This creature gets +1/+0 until end of turn.",
)

BESEECH_THE_MIRROR = make_sorcery(
    name="Beseech the Mirror",
    mana_cost="{1}{B}{B}{B}",
    colors={Color.BLACK},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nSearch your library for a card, exile it face down, then shuffle. If this spell was bargained, you may cast the exiled card without paying its mana cost if that spell's mana value is 4 or less. Put the exiled card into your hand if it wasn't cast this way.",
)

CANDY_GRAPPLE = make_instant(
    name="Candy Grapple",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nTarget creature gets -3/-3 until end of turn. If this spell was bargained, that creature gets -5/-5 until end of turn instead.",
)

CONCEITED_WITCH = make_creature(
    name="Conceited Witch",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\n// Adventure — Price of Beauty {B}\nCreate a Wicked Role token attached to target creature you control. (Then exile this card. You may cast the creature later from exile.)",
)

DREAM_SPOILERS = make_creature(
    name="Dream Spoilers",
    power=2, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Warlock"},
    text="Flying\nWhenever you cast a spell during an opponent's turn, up to one target creature an opponent controls gets -1/-1 until end of turn.",
)

EGO_DRAIN = make_sorcery(
    name="Ego Drain",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target opponent reveals their hand. You choose a nonland card from it. That player discards that card. If you don't control a Faerie, exile a card from your hand.",
)

THE_END = make_instant(
    name="The End",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="This spell costs {2} less to cast if your life total is 5 or less.\nExile target creature or planeswalker. Search its controller's graveyard, hand, and library for any number of cards with the same name as that permanent and exile them. That player shuffles, then draws a card for each card exiled from their hand this way.",
)

ERIETTES_WHISPER = make_sorcery(
    name="Eriette's Whisper",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Target opponent discards two cards. Create a Wicked Role token attached to up to one target creature you control. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1. When this token is put into a graveyard, each opponent loses 1 life.)",
)

FAERIE_DREAMTHIEF = make_creature(
    name="Faerie Dreamthief",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Warlock"},
    text="Flying\nWhen this creature enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\n{2}{B}, Exile this card from your graveyard: You draw a card and you lose 1 life.",
)

FAERIE_FENCING = make_instant(
    name="Faerie Fencing",
    mana_cost="{X}{B}",
    colors={Color.BLACK},
    text="Target creature gets -X/-X until end of turn. That creature gets an additional -3/-3 until end of turn if you controlled a Faerie as you cast this spell.",
)

FEED_THE_CAULDRON = make_instant(
    name="Feed the Cauldron",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target creature with mana value 3 or less. If it's your turn, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")",
)

FELL_HORSEMAN = make_creature(
    name="Fell Horseman",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Knight", "Zombie"},
    text="When this creature dies, put it on the bottom of its owner's library.\n// Adventure — Deathly Ride {1}{B}\nReturn target creature card from your graveyard to your hand. (Then exile this card. You may cast the creature later from exile.)",
)

GUMDROP_POISONER = make_creature(
    name="Gumdrop Poisoner",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="Lifelink\nWhen this creature enters, up to one target creature gets -X/-X until end of turn, where X is the amount of life you gained this turn.\n// Adventure — Tempt with Treats {B}\nCreate a Food token. (Then exile this card. You may cast the creature later from exile.)",
)

HIGH_FAE_NEGOTIATOR = make_creature(
    name="High Fae Negotiator",
    power=3, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Warlock"},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nFlying\nWhen this creature enters, if it was bargained, each opponent loses 3 life and you gain 3 life.",
)

HOPELESS_NIGHTMARE = make_enchantment(
    name="Hopeless Nightmare",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="When this enchantment enters, each opponent discards a card and loses 2 life.\nWhen this enchantment is put into a graveyard from the battlefield, scry 2.\n{2}{B}: Sacrifice this enchantment.",
)

LICHKNIGHTS_CONQUEST = make_sorcery(
    name="Lich-Knights' Conquest",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="Sacrifice any number of artifacts, enchantments, and/or tokens. Return that many creature cards from your graveyard to the battlefield.",
)

LORD_SKITTER_SEWER_KING = make_creature(
    name="Lord Skitter, Sewer King",
    power=3, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Noble", "Rat"},
    supertypes={"Legendary"},
    text="Whenever another Rat you control enters, exile up to one target card from an opponent's graveyard.\nAt the beginning of combat on your turn, create a 1/1 black Rat creature token with \"This token can't block.\"",
)

LORD_SKITTERS_BLESSING = make_enchantment(
    name="Lord Skitter's Blessing",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="When this enchantment enters, create a Wicked Role token attached to target creature you control. (Enchanted creature gets +1/+1. When this token is put into a graveyard, each opponent loses 1 life.)\nAt the beginning of your draw step, if you control an enchanted creature, you lose 1 life and you draw an additional card.",
)

LORD_SKITTERS_BUTCHER = make_creature(
    name="Lord Skitter's Butcher",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Peasant", "Rat"},
    text="When this creature enters, choose one —\n• Create a 1/1 black Rat creature token with \"This token can't block.\"\n• You may sacrifice another creature. If you do, scry 2, then draw a card.\n• Creatures you control gain menace until end of turn.",
)

MINTSTROSITY = make_creature(
    name="Mintstrosity",
    power=3, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="When this creature dies, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")",
)

NOT_DEAD_AFTER_ALL = make_instant(
    name="Not Dead After All",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Until end of turn, target creature you control gains \"When this creature dies, return it to the battlefield tapped under its owner's control, then create a Wicked Role token attached to it.\" (Enchanted creature gets +1/+1. When this token is put into a graveyard, each opponent loses 1 life.)",
)

RANKLES_PRANK = make_sorcery(
    name="Rankle's Prank",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Choose one or more —\n• Each player discards two cards.\n• Each player loses 4 life.\n• Each player sacrifices two creatures of their choice.",
)

RAT_OUT = make_instant(
    name="Rat Out",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Up to one target creature gets -1/-1 until end of turn. You create a 1/1 black Rat creature token with \"This token can't block.\"",
)

ROWANS_GRIM_SEARCH = make_instant(
    name="Rowan's Grim Search",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nIf this spell was bargained, look at the top four cards of your library, then put up to two of them back on top of your library in any order and the rest into your graveyard.\nYou draw two cards and you lose 2 life.",
)

SCREAM_PUFF = make_creature(
    name="Scream Puff",
    power=4, toughness=5,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="Deathtouch\nWhenever this creature deals combat damage to a player, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")",
)

SHATTER_THE_OATH = make_sorcery(
    name="Shatter the Oath",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature or enchantment. Create a Wicked Role token attached to up to one target creature you control. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1. When this token is put into a graveyard, each opponent loses 1 life.)",
)

SPECTER_OF_MORTALITY = make_creature(
    name="Specter of Mortality",
    power=3, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Specter"},
    text="Flying\nWhen this creature enters, you may exile one or more creature cards from your graveyard. When you do, each other creature gets -X/-X until end of turn, where X is the number of cards exiled this way.",
)

SPITEFUL_HEXMAGE = make_creature(
    name="Spiteful Hexmage",
    power=3, toughness=2,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="When this creature enters, create a Cursed Role token attached to target creature you control. (If you control another Role on it, put that one into the graveyard. Enchanted creature is 1/1.)",
)

STINGBLADE_ASSASSIN = make_creature(
    name="Stingblade Assassin",
    power=3, toughness=1,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Faerie"},
    text="Flash\nFlying\nWhen this creature enters, destroy target creature an opponent controls that was dealt damage this turn.",
)

SUGAR_RUSH = make_instant(
    name="Sugar Rush",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets +3/+0 until end of turn.\nDraw a card.",
)

SWEETTOOTH_WITCH = make_creature(
    name="Sweettooth Witch",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="When this creature enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\n{2}, Sacrifice a Food: Target player loses 2 life.",
)

TAKEN_BY_NIGHTMARES = make_instant(
    name="Taken by Nightmares",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Exile target creature. If you control an enchantment, scry 2.",
)

TANGLED_COLONY = make_creature(
    name="Tangled Colony",
    power=3, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rat"},
    text="This creature can't block.\nWhen this creature dies, create X 1/1 black Rat creature tokens with \"This token can't block,\" where X is the amount of damage dealt to it this turn.",
)

TWISTED_SEWERWITCH = make_creature(
    name="Twisted Sewer-Witch",
    power=3, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="When this creature enters, create a 1/1 black Rat creature token with \"This creature can't block.\" Then for each Rat you control, create a Wicked Role token attached to that Rat. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1. When this token is put into a graveyard, each opponent loses 1 life.)",
)

VIRTUE_OF_PERSISTENCE = make_enchantment(
    name="Virtue of Persistence",
    mana_cost="{5}{B}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, put target creature card from a graveyard onto the battlefield under your control.\n// Adventure — Locthwain Scorn {1}{B}\nTarget creature gets -3/-3 until end of turn. You gain 2 life.",
)

VORACIOUS_VERMIN = make_creature(
    name="Voracious Vermin",
    power=2, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Rat"},
    text="When this creature enters, create a 1/1 black Rat creature token with \"This token can't block.\"\nWhenever another creature you control dies, put a +1/+1 counter on this creature.",
)

WAREHOUSE_TABBY = make_creature(
    name="Warehouse Tabby",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Cat"},
    text="Whenever an enchantment you control is put into a graveyard from the battlefield, create a 1/1 black Rat creature token with \"This token can't block.\"\n{1}{B}: This creature gains deathtouch until end of turn.",
)

WICKED_VISITOR = make_creature(
    name="Wicked Visitor",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare"},
    text="Whenever an enchantment you control is put into a graveyard from the battlefield, each opponent loses 1 life.",
)

THE_WITCHS_VANITY = make_enchantment(
    name="The Witch's Vanity",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Destroy target creature an opponent controls with mana value 2 or less.\nII — Create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\nIII — Create a Wicked Role token attached to target creature you control.",
    subtypes={"Saga"},
)

BELLIGERENT_OF_THE_BALL = make_creature(
    name="Belligerent of the Ball",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Ogre", "Warrior"},
    text="Celebration — At the beginning of combat on your turn, if two or more nonland permanents entered the battlefield under your control this turn, target creature you control gets +1/+0 and gains menace until end of turn. (It can't be blocked except by two or more creatures.)",
)

BELLOWING_BRUISER = make_creature(
    name="Bellowing Bruiser",
    power=4, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Ogre"},
    text="Haste\n// Adventure — Beat a Path {2}{R}\nUp to two target creatures can't block this turn. (Then exile this card. You may cast the creature later from exile.)",
)

BESPOKE_BATTLEGARB = make_artifact(
    name="Bespoke Battlegarb",
    mana_cost="{1}{R}",
    text="Equipped creature gets +2/+0.\nCelebration — At the beginning of combat on your turn, if two or more nonland permanents entered the battlefield under your control this turn, attach this Equipment to up to one target creature you control.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

BOUNDARY_LANDS_RANGER = make_creature(
    name="Boundary Lands Ranger",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ranger"},
    text="At the beginning of combat on your turn, if you control a creature with power 4 or greater, you may discard a card. If you do, draw a card.",
)

CHARMING_SCOUNDREL = make_creature(
    name="Charming Scoundrel",
    power=1, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rogue"},
    text="Haste\nWhen this creature enters, choose one —\n• Discard a card, then draw a card.\n• Create a Treasure token.\n• Create a Wicked Role token attached to target creature you control.",
)

CUT_IN = make_sorcery(
    name="Cut In",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Cut In deals 4 damage to target creature.\nCreate a Young Hero Role token attached to up to one target creature you control. (If you control another Role on it, put that one into the graveyard. Enchanted creature has \"Whenever this creature attacks, if its toughness is 3 or less, put a +1/+1 counter on it.\")",
)

EDGEWALL_PACK = make_creature(
    name="Edgewall Pack",
    power=3, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Dog"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhen this creature enters, create a 1/1 black Rat creature token with \"This token can't block.\"",
)

EMBERETH_VETERAN = make_creature(
    name="Embereth Veteran",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Knight"},
    text="{1}, Sacrifice this creature: Create a Young Hero Role token attached to another target creature. (If you control another Role on it, put that one into the graveyard. Enchanted creature has \"Whenever this creature attacks, if its toughness is 3 or less, put a +1/+1 counter on it.\")",
)

FLICK_A_COIN = make_instant(
    name="Flick a Coin",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Flick a Coin deals 1 damage to any target. You create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nDraw a card.",
)

FOOD_FIGHT = make_enchantment(
    name="Food Fight",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Artifacts you control have \"{2}, Sacrifice this artifact: It deals damage to any target equal to 1 plus the number of permanents named Food Fight you control.\"",
)

FRANTIC_FIREBOLT = make_instant(
    name="Frantic Firebolt",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Frantic Firebolt deals X damage to target creature, where X is 2 plus the number of cards in your graveyard that are instant cards, sorcery cards, and/or have an Adventure.",
)

GNAWING_CRESCENDO = make_instant(
    name="Gnawing Crescendo",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Creatures you control get +2/+0 until end of turn. Whenever a nontoken creature you control dies this turn, create a 1/1 black Rat creature token with \"This token can't block.\"",
)

GODDRIC_CLOAKED_REVELER = make_creature(
    name="Goddric, Cloaked Reveler",
    power=3, toughness=3,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Haste\nCelebration — As long as two or more nonland permanents entered the battlefield under your control this turn, Goddric is a Dragon with base power and toughness 4/4, flying, and \"{R}: Dragons you control get +1/+0 until end of turn.\" (It loses all other creature types.)",
)

GRABBY_GIANT = make_creature(
    name="Grabby Giant",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Giant"},
    text="Reach\n{2}{R}, Sacrifice an artifact or land: Draw a card.\n// Adventure — That's Mine {1}{R}\nCreate a Treasure token. (Then exile this card. You may cast the creature later from exile.)",
)

GRAND_BALL_GUEST = make_creature(
    name="Grand Ball Guest",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Peasant"},
    text="Celebration — This creature gets +1/+1 and has trample as long as two or more nonland permanents entered the battlefield under your control this turn.",
)

HARRIED_SPEARGUARD = make_creature(
    name="Harried Spearguard",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="Haste\nWhen this creature dies, create a 1/1 black Rat creature token with \"This token can't block.\"",
)

HEARTH_ELEMENTAL = make_creature(
    name="Hearth Elemental",
    power=4, toughness=5,
    mana_cost="{5}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="This spell costs {X} less to cast, where X is the number of cards in your graveyard that are instant cards, sorcery cards, and/or have an Adventure.\n// Adventure — Stoke Genius {1}{R}\nDiscard your hand, then draw two cards. (Then exile this card. You may cast the creature later from exile.)",
)

IMODANE_THE_PYROHAMMER = make_creature(
    name="Imodane, the Pyrohammer",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="Whenever an instant or sorcery spell you control that targets only a single creature deals damage to that creature, Imodane deals that much damage to each opponent.",
)

KINDLED_HEROISM = make_instant(
    name="Kindled Heroism",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +1/+0 and gains first strike until end of turn. Scry 1.",
)

KORVOLD_AND_THE_NOBLE_THIEF = make_enchantment(
    name="Korvold and the Noble Thief",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI, II — Create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nIII — Exile the top three cards of target opponent's library. You may play those cards this turn.",
    subtypes={"Saga"},
)

MERRY_BARDS = make_creature(
    name="Merry Bards",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Bard", "Human"},
    text="When this creature enters, you may pay {1}. When you do, create a Young Hero Role token attached to target creature you control. (If you control another Role on it, put that one into the graveyard. Enchanted creature has \"Whenever this creature attacks, if its toughness is 3 or less, put a +1/+1 counter on it.\")",
)

MINECART_DAREDEVIL = make_creature(
    name="Minecart Daredevil",
    power=4, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Knight"},
    text="\n// Adventure — Ride the Rails {1}{R}\nTarget creature gets +2/+1 until end of turn. (Then exile this card. You may cast the creature later from exile.)",
)

MONSTROUS_RAGE = make_instant(
    name="Monstrous Rage",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +2/+0 until end of turn. Create a Monster Role token attached to it. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1 and has trample.)",
)

RAGING_BATTLE_MOUSE = make_creature(
    name="Raging Battle Mouse",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Mouse"},
    text="The second spell you cast each turn costs {1} less to cast.\nCelebration — At the beginning of combat on your turn, if two or more nonland permanents entered the battlefield under your control this turn, target creature you control gets +1/+1 until end of turn.",
)

RATCATCHER_TRAINEE = make_creature(
    name="Ratcatcher Trainee",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Peasant"},
    text="During your turn, this creature has first strike.\n// Adventure — Pest Problem {2}{R}\nCreate two 1/1 black Rat creature tokens with \"This token can't block.\" (Then exile this card. You may cast the creature later from exile.)",
)

REALMSCORCHER_HELLKITE = make_creature(
    name="Realm-Scorcher Hellkite",
    power=4, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nFlying, haste\nWhen this creature enters, if it was bargained, add four mana in any combination of colors.\n{1}{R}: This creature deals 1 damage to any target.",
)

REDCAP_GUTTERDWELLER = make_creature(
    name="Redcap Gutter-Dweller",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="Menace\nWhen this creature enters, create two 1/1 black Rat creature tokens with \"This token can't block.\"\nAt the beginning of your upkeep, you may sacrifice another creature. If you do, put a +1/+1 counter on this creature and exile the top card of your library. You may play that card this turn.",
)

REDCAP_THIEF = make_creature(
    name="Redcap Thief",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Rogue"},
    text="When this creature enters, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

ROTISSERIE_ELEMENTAL = make_creature(
    name="Rotisserie Elemental",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Menace\nWhenever this creature deals combat damage to a player, put a skewer counter on this creature. Then you may sacrifice it. If you do, exile the top X cards of your library, where X is the number of skewer counters on this creature. You may play those cards this turn.",
)

SKEWER_SLINGER = make_creature(
    name="Skewer Slinger",
    power=1, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Knight"},
    text="Reach\nWhenever this creature blocks or becomes blocked by a creature, this creature deals 1 damage to that creature.",
)

SONG_OF_TOTENTANZ = make_sorcery(
    name="Song of Totentanz",
    mana_cost="{X}{R}",
    colors={Color.RED},
    text="Create X 1/1 black Rat creature tokens with \"This token can't block.\" Creatures you control gain haste until end of turn.",
)

STONESPLITTER_BOLT = make_instant(
    name="Stonesplitter Bolt",
    mana_cost="{X}{R}",
    colors={Color.RED},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nStonesplitter Bolt deals X damage to target creature or planeswalker. If this spell was bargained, it deals twice X damage to that permanent instead.",
)

TATTERED_RATTER = make_creature(
    name="Tattered Ratter",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Peasant"},
    text="Whenever a Rat you control becomes blocked, it gets +2/+0 until end of turn.",
)

TORCH_THE_TOWER = make_instant(
    name="Torch the Tower",
    mana_cost="{R}",
    colors={Color.RED},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nTorch the Tower deals 2 damage to target creature or planeswalker. If this spell was bargained, instead it deals 3 damage to that permanent and you scry 1.\nIf a permanent dealt damage by Torch the Tower would die this turn, exile it instead.",
)

TWISTED_FEALTY = make_sorcery(
    name="Twisted Fealty",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn.\nCreate a Wicked Role token attached to up to one target creature. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1. When this token is put into a graveyard, each opponent loses 1 life.)",
)

TWOHEADED_HUNTER = make_creature(
    name="Two-Headed Hunter",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Giant"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\n// Adventure — Twice the Rage {1}{R}\nTarget creature gains double strike until end of turn. (Then exile this card. You may cast the creature later from exile.)",
)

UNRULY_CATAPULT = make_artifact_creature(
    name="Unruly Catapult",
    power=0, toughness=4,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Construct"},
    text="Defender\n{T}: This creature deals 1 damage to each opponent.\nWhenever you cast an instant or sorcery spell, untap this creature.",
)

VIRTUE_OF_COURAGE = make_enchantment(
    name="Virtue of Courage",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Whenever a source you control deals noncombat damage to an opponent, you may exile that many cards from the top of your library. You may play those cards this turn.\n// Adventure — Embereth Blaze {1}{R}\nEmbereth Blaze deals 2 damage to any target. (Then exile this card. You may cast the enchantment later from exile.)",
)

WITCHS_MARK = make_sorcery(
    name="Witch's Mark",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="You may discard a card. If you do, draw two cards.\nCreate a Wicked Role token attached to up to one target creature you control. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1. When this token is put into a graveyard, each opponent loses 1 life.)",
)

WITCHSTALKER_FRENZY = make_instant(
    name="Witchstalker Frenzy",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="This spell costs {1} less to cast for each creature that attacked this turn.\nWitchstalker Frenzy deals 5 damage to target creature.",
)

AGATHAS_CHAMPION = make_creature(
    name="Agatha's Champion",
    power=4, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Knight"},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nTrample\nWhen this creature enters, if it was bargained, it fights up to one target creature you don't control. (Each deals damage equal to its power to the other.)",
)

BEANSTALK_WURM = make_creature(
    name="Beanstalk Wurm",
    power=5, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Wurm"},
    text="Reach\n// Adventure — Plant Beans {1}{G}\nYou may play an additional land this turn. (Then exile this card. You may cast the creature later from exile.)",
)

BESTIAL_BLOODLINE = make_enchantment(
    name="Bestial Bloodline",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Enchant creature\nEnchanted creature gets +2/+2.\n{4}{G}: Return this card from your graveyard to your hand.",
    subtypes={"Aura"},
)

BLOSSOMING_TORTOISE = make_creature(
    name="Blossoming Tortoise",
    power=3, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Turtle"},
    text="Whenever this creature enters or attacks, mill three cards, then return a land card from your graveyard to the battlefield tapped.\nActivated abilities of lands you control cost {1} less to activate.\nLand creatures you control get +1/+1.",
)

BRAMBLE_FAMILIAR = make_creature(
    name="Bramble Familiar",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental", "Raccoon"},
    text="{T}: Add {G}.\n{1}{G}, {T}, Discard a card: Return this creature to its owner's hand.\n// Adventure — Fetch Quest {5}{G}{G}\nMill seven cards. Then put a creature, enchantment, or land card from among the milled cards onto the battlefield.",
)

BRAVE_THE_WILDS = make_sorcery(
    name="Brave the Wilds",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nIf this spell was bargained, target land you control becomes a 3/3 Elemental creature with haste that's still a land.\nSearch your library for a basic land card, reveal it, put it into your hand, then shuffle.",
)

COMMUNE_WITH_NATURE = make_sorcery(
    name="Commune with Nature",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Look at the top five cards of your library. You may reveal a creature card from among them and put it into your hand. Put the rest on the bottom of your library in any order.",
)

CURSE_OF_THE_WEREFOX = make_sorcery(
    name="Curse of the Werefox",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Create a Monster Role token attached to target creature you control. When you do, that creature fights up to one target creature you don't control. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1 and has trample. Creatures that fight each deal damage equal to their power to the other.)",
)

ELVISH_ARCHIVIST = make_creature(
    name="Elvish Archivist",
    power=0, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Artificer", "Elf"},
    text="Whenever one or more artifacts you control enter, put two +1/+1 counters on this creature. This ability triggers only once each turn.\nWhenever one or more enchantments you control enter, draw a card. This ability triggers only once each turn.",
)

FERAL_ENCOUNTER = make_sorcery(
    name="Feral Encounter",
    mana_cost="{G}{G}",
    colors={Color.GREEN},
    text="Look at the top five cards of your library. You may exile a creature card from among them. Put the rest on the bottom of your library in a random order. You may cast the exiled card this turn. At the beginning of the next combat phase this turn, target creature you control deals damage equal to its power to up to one target creature you don't control.",
)

FEROCIOUS_WEREFOX = make_creature(
    name="Ferocious Werefox",
    power=4, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Fox", "Warrior"},
    text="Trample\n// Adventure — Guard Change {1}{G}\nCreate a Monster Role token attached to target creature you control. (Enchanted creature gets +1/+1 and has trample.)",
)

GRACEFUL_TAKEDOWN = make_sorcery(
    name="Graceful Takedown",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Any number of target enchanted creatures you control and up to one other target creature you control each deal damage equal to their power to target creature you don't control.",
)

GRUFF_TRIPLETS = make_creature(
    name="Gruff Triplets",
    power=3, toughness=3,
    mana_cost="{3}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Satyr", "Warrior"},
    text="Trample\nWhen this creature enters, if it isn't a token, create two tokens that are copies of it.\nWhen this creature dies, put a number of +1/+1 counters equal to its power on each creature you control named Gruff Triplets.",
)

HAMLET_GLUTTON = make_creature(
    name="Hamlet Glutton",
    power=6, toughness=6,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Giant"},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nThis spell costs {2} less to cast if it's bargained.\nTrample\nWhen this creature enters, you gain 3 life.",
)

HOLLOW_SCAVENGER = make_creature(
    name="Hollow Scavenger",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Wolf"},
    text="{1}, Sacrifice a Food: This creature gets +2/+2 until end of turn. Activate only once each turn.\n// Adventure — Bakery Raid {G}\nCreate a Food token. (Then exile this card. You may cast the creature later from exile.)",
)

HOWLING_GALEFANG = make_creature(
    name="Howling Galefang",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Vigilance\nThis creature has haste as long as you own a card in exile that has an Adventure.",
)

THE_HUNTSMANS_REDEMPTION = make_enchantment(
    name="The Huntsman's Redemption",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Create a 3/3 green Beast creature token.\nII — You may sacrifice a creature. If you do, search your library for a creature or basic land card, reveal it, put it into your hand, then shuffle.\nIII — Up to two target creatures each get +2/+2 and gain trample until end of turn.",
    subtypes={"Saga"},
)

LEAPING_AMBUSH = make_instant(
    name="Leaping Ambush",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +1/+3 and gains reach until end of turn. Untap it.",
)

NIGHT_OF_THE_SWEETS_REVENGE = make_enchantment(
    name="Night of the Sweets' Revenge",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\nFoods you control have \"{T}: Add {G}.\"\n{5}{G}{G}, Sacrifice this enchantment: Creatures you control get +X/+X until end of turn, where X is the number of Foods you control. Activate only as a sorcery.",
)

REDTOOTH_GENEALOGIST = make_creature(
    name="Redtooth Genealogist",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Advisor", "Elf"},
    text="When this creature enters, create a Royal Role token attached to another target creature you control. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1 and has ward {1}.)",
)

REDTOOTH_VANGUARD = make_creature(
    name="Redtooth Vanguard",
    power=3, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    text="Trample\nWhenever an enchantment you control enters, you may pay {2}. If you do, return this card from your graveyard to your hand.",
)

RETURN_FROM_THE_WILDS = make_sorcery(
    name="Return from the Wilds",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Choose two —\n• Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\n• Create a 1/1 white Human creature token.\n• Create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")",
)

ROOTRIDER_FAUN = make_creature(
    name="Rootrider Faun",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Satyr", "Scout"},
    text="{T}: Add {G}.\n{1}, {T}: Add one mana of any color.",
)

ROYAL_TREATMENT = make_instant(
    name="Royal Treatment",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature you control gains hexproof until end of turn. Create a Royal Role token attached to that creature. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1 and has ward {1}.)",
)

SENTINEL_OF_LOST_LORE = make_creature(
    name="Sentinel of Lost Lore",
    power=3, toughness=4,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Knight"},
    text="When this creature enters, choose one or more —\n• Return target card you own in exile that has an Adventure to your hand.\n• Put target card you don't own in exile that has an Adventure on the bottom of its owner's library.\n• Exile target player's graveyard.",
)

SKYBEAST_TRACKER = make_creature(
    name="Skybeast Tracker",
    power=2, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Archer", "Giant"},
    text="Reach\nWhenever you cast a spell with mana value 5 or greater, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")",
)

SPIDER_FOOD = make_sorcery(
    name="Spider Food",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Destroy up to one target artifact, enchantment, or creature with flying. Create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")",
)

STORMKELD_VANGUARD = make_creature(
    name="Stormkeld Vanguard",
    power=6, toughness=7,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Giant", "Warrior"},
    text="This creature can't be blocked by creatures with power 2 or less.\n// Adventure — Bear Down {1}{G}\nDestroy target artifact or enchantment. (Then exile this card. You may cast the creature later from exile.)",
)

TANGLESPAN_LOOKOUT = make_creature(
    name="Tanglespan Lookout",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Satyr"},
    text="Whenever an Aura you control enters, draw a card.",
)

TERRITORIAL_WITCHSTALKER = make_creature(
    name="Territorial Witchstalker",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Wolf"},
    text="Defender\nAt the beginning of combat on your turn, if you control a creature with power 4 or greater, this creature gets +1/+0 until end of turn and can attack this turn as though it didn't have defender.",
)

THUNDEROUS_DEBUT = make_sorcery(
    name="Thunderous Debut",
    mana_cost="{6}{G}{G}",
    colors={Color.GREEN},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nLook at the top twenty cards of your library. You may reveal up to two creature cards from among them. If this spell was bargained, put the revealed cards onto the battlefield. Otherwise, put the revealed cards into your hand. Then shuffle.",
)

TITANIC_GROWTH = make_instant(
    name="Titanic Growth",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +4/+4 until end of turn.",
)

TOADSTOOL_ADMIRER = make_creature(
    name="Toadstool Admirer",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Ouphe"},
    text="Ward {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\n{3}{G}: Put a +1/+1 counter on this creature.",
)

TOUGH_COOKIE = make_artifact_creature(
    name="Tough Cookie",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Food", "Golem"},
    text="When this creature enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\n{2}{G}: Until end of turn, target noncreature artifact you control becomes a 4/4 artifact creature.\n{2}, {T}, Sacrifice this creature: You gain 3 life.",
)

TROUBLEMAKER_OUPHE = make_creature(
    name="Troublemaker Ouphe",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Ouphe"},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nWhen this creature enters, if it was bargained, exile target artifact or enchantment an opponent controls.",
)

UP_THE_BEANSTALK = make_enchantment(
    name="Up the Beanstalk",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters and whenever you cast a spell with mana value 5 or greater, draw a card.",
)

VERDANT_OUTRIDER = make_creature(
    name="Verdant Outrider",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Knight"},
    text="{1}{G}: This creature can't be blocked by creatures with power 2 or less this turn.",
)

VIRTUE_OF_STRENGTH = make_enchantment(
    name="Virtue of Strength",
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    text="If you tap a basic land for mana, it produces three times as much of that mana instead.\n// Adventure — Garenbrig Growth {G}\nReturn target creature or land card from your graveyard to your hand. (Then exile this card. You may cast the enchantment later from exile.)",
)

WELCOME_TO_SWEETTOOTH = make_enchantment(
    name="Welcome to Sweettooth",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Create a 1/1 white Human creature token.\nII — Create a Food token.\nIII — Put X +1/+1 counters on target creature you control, where X is one plus the number of Foods you control.",
    subtypes={"Saga"},
)

AGATHA_OF_THE_VILE_CAULDRON = make_creature(
    name="Agatha of the Vile Cauldron",
    power=1, toughness=1,
    mana_cost="{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Activated abilities of creatures you control cost {X} less to activate, where X is Agatha's power. This effect can't reduce the mana in that cost to less than one mana.\n{4}{R}{G}: Other creatures you control get +1/+1 and gain trample and haste until end of turn.",
)

THE_APPRENTICES_FOLLY = make_enchantment(
    name="The Apprentice's Folly",
    mana_cost="{2}{U}{R}",
    colors={Color.RED, Color.BLUE},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI, II — Choose target nontoken creature you control that doesn't have the same name as a token you control. Create a token that's a copy of it, except it isn't legendary, is a Reflection in addition to its other types, and has haste.\nIII — Sacrifice all Reflections you control.",
    subtypes={"Saga"},
)

ASH_PARTY_CRASHER = make_creature(
    name="Ash, Party Crasher",
    power=2, toughness=2,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Peasant"},
    supertypes={"Legendary"},
    text="Haste\nCelebration — Whenever Ash attacks, if two or more nonland permanents entered the battlefield under your control this turn, put a +1/+1 counter on Ash.",
)

ERIETTE_OF_THE_CHARMED_APPLE = make_creature(
    name="Eriette of the Charmed Apple",
    power=2, toughness=4,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Each creature that's enchanted by an Aura you control can't attack you or planeswalkers you control.\nAt the beginning of your end step, each opponent loses X life and you gain X life, where X is the number of Auras you control.",
)

FAUNSBANE_TROLL = make_creature(
    name="Faunsbane Troll",
    power=4, toughness=4,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Troll"},
    text="When this creature enters, create a Monster Role token attached to it. (Enchanted creature gets +1/+1 and has trample.)\n{1}, Sacrifice an Aura attached to this creature: This creature fights target creature you don't control. If that creature would die this turn, exile it instead. Activate only as a sorcery.",
)

THE_GOOSE_MOTHER = make_creature(
    name="The Goose Mother",
    power=2, toughness=2,
    mana_cost="{X}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Bird", "Hydra"},
    supertypes={"Legendary"},
    text="Flying\nThe Goose Mother enters with X +1/+1 counters on it.\nWhen The Goose Mother enters, create half X Food tokens, rounded up.\nWhenever The Goose Mother attacks, you may sacrifice a Food. If you do, draw a card.",
)

GRETA_SWEETTOOTH_SCOURGE = make_creature(
    name="Greta, Sweettooth Scourge",
    power=3, toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="When Greta enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\n{G}, Sacrifice a Food: Put a +1/+1 counter on target creature. Activate only as a sorcery.\n{1}{B}, Sacrifice a Food: You draw a card and you lose 1 life.",
)

HYLDA_OF_THE_ICY_CROWN = make_creature(
    name="Hylda of the Icy Crown",
    power=3, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Whenever you tap an untapped creature an opponent controls, you may pay {1}. When you do, choose one —\n• Create a 4/4 white and blue Elemental creature token.\n• Put a +1/+1 counter on each creature you control.\n• Scry 2, then draw a card.",
)

JOHANN_APPRENTICE_SORCERER = make_creature(
    name="Johann, Apprentice Sorcerer",
    power=2, toughness=5,
    mana_cost="{2}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Human", "Sorcerer", "Wizard"},
    supertypes={"Legendary"},
    text="You may look at the top card of your library any time.\nOnce each turn, you may cast an instant or sorcery spell from the top of your library. (You still pay its costs. Timing rules still apply.)",
)

LIKENESS_LOOTER = make_creature(
    name="Likeness Looter",
    power=1, toughness=1,
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Faerie", "Shapeshifter"},
    text="Flying\n{T}: Draw a card, then discard a card.\n{X}: This creature becomes a copy of target creature card in your graveyard with mana value X, except it has flying and this ability. Activate only as a sorcery.",
)

NEVA_STALKED_BY_NIGHTMARES = make_creature(
    name="Neva, Stalked by Nightmares",
    power=2, toughness=2,
    mana_cost="{2}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Menace\nWhen Neva enters, return target creature or enchantment card from your graveyard to your hand.\nWhenever an enchantment you control is put into a graveyard from the battlefield, put a +1/+1 counter on Neva, then scry 1.",
)

OBYRA_DREAMING_DUELIST = make_creature(
    name="Obyra, Dreaming Duelist",
    power=2, toughness=2,
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Faerie", "Warrior"},
    supertypes={"Legendary"},
    text="Flash\nFlying\nWhenever another Faerie you control enters, each opponent loses 1 life.",
)

ROWAN_SCION_OF_WAR = make_creature(
    name="Rowan, Scion of War",
    power=4, toughness=2,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Menace\n{T}: Spells you cast this turn that are black and/or red cost {X} less to cast, where X is the amount of life you lost this turn. Activate only as a sorcery.",
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

SHARAE_OF_NUMBING_DEPTHS = make_creature(
    name="Sharae of Numbing Depths",
    power=2, toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Merfolk", "Wizard"},
    supertypes={"Legendary"},
    text="When Sharae enters, tap target creature an opponent controls and put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nWhenever you tap one or more untapped creatures your opponents control, draw a card. This ability triggers only once each turn.",
)

SYR_ARMONT_THE_REDEEMER = make_creature(
    name="Syr Armont, the Redeemer",
    power=4, toughness=4,
    mana_cost="{3}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="When Syr Armont enters, create a Monster Role token attached to another target creature you control. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1 and has trample.)\nEnchanted creatures you control get +1/+1.",
)

TALION_THE_KINDLY_LORD = make_creature(
    name="Talion, the Kindly Lord",
    power=3, toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Faerie", "Noble"},
    supertypes={"Legendary"},
    text="Flying\nAs Talion enters, choose a number between 1 and 10.\nWhenever an opponent casts a spell with mana value, power, or toughness equal to the chosen number, that player loses 2 life and you draw a card.",
)

TOTENTANZ_SWARM_PIPER = make_creature(
    name="Totentanz, Swarm Piper",
    power=2, toughness=3,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Bard", "Human", "Warlock"},
    supertypes={"Legendary"},
    text="Whenever Totentanz or another nontoken creature you control dies, create a 1/1 black Rat creature token with \"This token can't block.\"\n{1}{B}: Target attacking Rat you control gains deathtouch until end of turn.",
)

TROYAN_GUTSY_EXPLORER = make_creature(
    name="Troyan, Gutsy Explorer",
    power=1, toughness=3,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Scout", "Vedalken"},
    supertypes={"Legendary"},
    text="{T}: Add {G}{U}. Spend this mana only to cast spells with mana value 5 or greater or spells with {X} in their mana costs.\n{U}, {T}: Draw a card, then discard a card.",
)

WILL_SCION_OF_PEACE = make_creature(
    name="Will, Scion of Peace",
    power=2, toughness=4,
    mana_cost="{1}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Vigilance\n{T}: Spells you cast this turn that are white and/or blue cost {X} less to cast, where X is the amount of life you gained this turn. Activate only as a sorcery.",
)

YENNA_REDTOOTH_REGENT = make_creature(
    name="Yenna, Redtooth Regent",
    power=4, toughness=4,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Elf", "Noble"},
    supertypes={"Legendary"},
    text="{2}, {T}: Choose target enchantment you control that doesn't have the same name as another permanent you control. Create a token that's a copy of it, except it isn't legendary. If the token is an Aura, untap Yenna, then scry 2. Activate only as a sorcery.",
)

BELUNA_GRANDSQUALL = make_creature(
    name="Beluna Grandsquall",
    power=4, toughness=4,
    mana_cost="{G}{U}{R}",
    colors={Color.GREEN, Color.RED, Color.BLUE},
    subtypes={"Giant", "Noble"},
    supertypes={"Legendary"},
    text="Trample\nPermanent spells you cast that have an Adventure cost {1} less to cast.\n// Adventure — Seek Thrills {2}{G}{U}{R}\nMill seven cards. Then put all cards that have an Adventure from among the milled cards into your hand.",
)

CALLOUS_SELLSWORD = make_creature(
    name="Callous Sell-Sword",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    text="This creature enters with a +1/+1 counter on it for each creature that died under your control this turn.\n// Adventure — Burn Together {R}\nTarget creature you control deals damage equal to its power to any other target. Then sacrifice it.",
)

CRUEL_SOMNOPHAGE = make_creature(
    name="Cruel Somnophage",
    power=0, toughness=0,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare"},
    text="Cruel Somnophage's power and toughness are each equal to the number of creature cards in all graveyards.\n// Adventure — Can't Wake Up {1}{U}\nTarget player mills four cards. (Then exile this card. You may cast the creature later from exile.)",
)

DECADENT_DRAGON = make_creature(
    name="Decadent Dragon",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying, trample\nWhenever this creature attacks, create a Treasure token.\n// Adventure — Expensive Taste {2}{B}\nExile the top two cards of target opponent's library face down. You may look at and play those cards for as long as they remain exiled.",
)

DEVOURING_SUGARMAW = make_creature(
    name="Devouring Sugarmaw",
    power=6, toughness=6,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="Menace, trample\nAt the beginning of your upkeep, you may sacrifice an artifact, enchantment, or token. If you don't, tap this creature.\n// Adventure — Have for Dinner {1}{W}\nCreate a 1/1 white Human creature token and a Food token. (Then exile this card. You may cast the creature later from exile.)",
)

ELUSIVE_OTTER = make_creature(
    name="Elusive Otter",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Otter"},
    text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nCreatures with power less than this creature's power can't block it.\n// Adventure — Grove's Bounty {X}{G}\nDistribute X +1/+1 counters among any number of target creatures you control. (Then exile this card. You may cast the creature later from exile.)",
)

FROLICKING_FAMILIAR = make_creature(
    name="Frolicking Familiar",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Otter", "Wizard"},
    text="Flying\nWhenever you cast an instant or sorcery spell, this creature gets +1/+1 until end of turn.\n// Adventure — Blow Off Steam {R}\nBlow Off Steam deals 1 damage to any target. (Then exile this card. You may cast the creature later from exile.)",
)

GINGERBREAD_HUNTER = make_creature(
    name="Gingerbread Hunter",
    power=5, toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Giant"},
    text="When this creature enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\n// Adventure — Puny Snack {2}{B}\nTarget creature gets -2/-2 until end of turn. (Then exile this card. You may cast the creature later from exile.)",
)

HEARTFLAME_DUELIST = make_creature(
    name="Heartflame Duelist",
    power=3, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Instant and sorcery spells you control have lifelink.\n// Adventure — Heartflame Slash {2}{R}\nHeartflame Slash deals 3 damage to any target. (Then exile this card. You may cast the creature later from exile.)",
)

IMODANES_RECRUITER = make_creature(
    name="Imodane's Recruiter",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Knight"},
    text="When this creature enters, creatures you control get +1/+0 and gain haste until end of turn.\n// Adventure — Train Troops {4}{W}\nCreate two 2/2 white Knight creature tokens with vigilance. (Then exile this card. You may cast the creature later from exile.)",
)

KELLAN_THE_FAEBLOODED = make_creature(
    name="Kellan, the Fae-Blooded",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Faerie", "Human"},
    supertypes={"Legendary"},
    text="Double strike\nOther creatures you control get +1/+0 for each Aura and Equipment attached to Kellan.\n// Adventure — Birthright Boon {1}{W}\nSearch your library for an Aura or Equipment card, reveal it, put it into your hand, then shuffle.",
)

MOSSWOOD_DREADKNIGHT = make_creature(
    name="Mosswood Dreadknight",
    power=3, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Knight"},
    text="Trample\nWhen this creature dies, you may cast it from your graveyard as an Adventure until the end of your next turn.\n// Adventure — Dread Whispers {1}{B}\nYou draw a card and you lose 1 life. (Then exile this card. You may cast the creature later from exile.)",
)

PICNIC_RUINER = make_creature(
    name="Picnic Ruiner",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Rogue"},
    text="Whenever this creature attacks while you control a creature with power 4 or greater, this creature gains double strike until end of turn.\n// Adventure — Stolen Goodies {3}{G}\nDistribute three +1/+1 counters among any number of target creatures you control.",
)

POLLENSHIELD_HARE = make_creature(
    name="Pollen-Shield Hare",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Rabbit"},
    text="Creature tokens you control get +1/+1.\n// Adventure — Hare Raising {G}\nTarget creature you control gains vigilance and gets +X/+X until end of turn, where X is the number of creatures you control.",
)

QUESTING_DRUID = make_creature(
    name="Questing Druid",
    power=1, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Human"},
    text="Whenever you cast a spell that's white, blue, black, or red, put a +1/+1 counter on this creature.\n// Adventure — Seek the Beast {1}{R}\nExile the top two cards of your library. Until your next end step, you may play those cards.",
)

SCALDING_VIPER = make_creature(
    name="Scalding Viper",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Snake"},
    text="Whenever an opponent casts a spell with mana value 3 or less, this creature deals 1 damage to that player.\n// Adventure — Steam Clean {1}{U}\nReturn target nonland permanent to its owner's hand. (Then exile this card. You may cast the creature later from exile.)",
)

SHROUDED_SHEPHERD = make_creature(
    name="Shrouded Shepherd",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Warrior"},
    text="When this creature enters, target creature you control gets +2/+2 until end of turn.\n// Adventure — Cleave Shadows {1}{B}\nCreatures your opponents control get -1/-1 until end of turn. (Then exile this card. You may cast the creature later from exile.)",
)

SPELLSCORN_COVEN = make_creature(
    name="Spellscorn Coven",
    power=2, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Warlock"},
    text="Flying\nWhen this creature enters, each opponent discards a card.\n// Adventure — Take It Back {2}{U}\nReturn target spell to its owner's hand. (Then exile this card. You may cast the creature later from exile.)",
)

TEMPEST_HART = make_creature(
    name="Tempest Hart",
    power=3, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental", "Elk"},
    text="Trample\nWhenever you cast a spell with mana value 5 or greater, put a +1/+1 counter on this creature.\n// Adventure — Scan the Clouds {1}{U}\nDraw two cards, then discard two cards. (Then exile this card. You may cast the creature later from exile.)",
)

THREADBIND_CLIQUE = make_creature(
    name="Threadbind Clique",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie"},
    text="Flying\n// Adventure — Rip the Seams {2}{W}\nDestroy target tapped creature. (Then exile this card. You may cast the creature later from exile.)",
)

TWINING_TWINS = make_creature(
    name="Twining Twins",
    power=4, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flying, vigilance, ward {1}\n// Adventure — Swift Spiral {1}{W}\nExile target nontoken creature. Return it to the battlefield under its owner's control at the beginning of the next end step.",
)

WOODLAND_ACOLYTE = make_creature(
    name="Woodland Acolyte",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Human"},
    text="When this creature enters, draw a card.\n// Adventure — Mend the Wilds {G}\nPut target permanent card from your graveyard on top of your library. (Then exile this card. You may cast the creature later from exile.)",
)

AGATHAS_SOUL_CAULDRON = make_artifact(
    name="Agatha's Soul Cauldron",
    mana_cost="{2}",
    text="You may spend mana as though it were mana of any color to activate abilities of creatures you control.\nCreatures you control with +1/+1 counters on them have all activated abilities of all creature cards exiled with Agatha's Soul Cauldron.\n{T}: Exile target card from a graveyard. When a creature card is exiled this way, put a +1/+1 counter on target creature you control.",
    supertypes={"Legendary"},
)

CANDY_TRAIL = make_artifact(
    name="Candy Trail",
    mana_cost="{1}",
    text="When this artifact enters, scry 2.\n{2}, {T}, Sacrifice this artifact: You gain 3 life and draw a card.",
    subtypes={"Clue", "Food"},
)

COLLECTORS_VAULT = make_artifact(
    name="Collector's Vault",
    mana_cost="{2}",
    text="{2}, {T}: Draw a card, then discard a card. Create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

ERIETTES_TEMPTING_APPLE = make_artifact(
    name="Eriette's Tempting Apple",
    mana_cost="{4}",
    text="When Eriette's Tempting Apple enters, gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn.\n{2}, {T}, Sacrifice Eriette's Tempting Apple: You gain 3 life.\n{2}, {T}, Sacrifice Eriette's Tempting Apple: Target opponent loses 3 life.",
    subtypes={"Food"},
    supertypes={"Legendary"},
)

GINGERBRUTE = make_artifact_creature(
    name="Gingerbrute",
    power=1, toughness=1,
    mana_cost="{1}",
    colors=set(),
    subtypes={"Food", "Golem"},
    text="Haste (This creature can attack and {T} as soon as it comes under your control.)\n{1}: This creature can't be blocked this turn except by creatures with haste.\n{2}, {T}, Sacrifice this creature: You gain 3 life.",
)

HYLDAS_CROWN_OF_WINTER = make_artifact(
    name="Hylda's Crown of Winter",
    mana_cost="{3}",
    text="{1}, {T}: Tap target creature. This ability costs {1} less to activate during your turn.\n{3}, Sacrifice Hylda's Crown of Winter: Draw a card for each tapped creature your opponents control.",
    supertypes={"Legendary"},
)

THE_IRENCRAG = make_artifact(
    name="The Irencrag",
    mana_cost="{2}",
    text="{T}: Add {C}.\nWhenever a legendary creature you control enters, you may have The Irencrag become a legendary Equipment artifact named Everflame, Heroes' Legacy. If you do, it gains equip {3} and \"Equipped creature gets +3/+3\" and loses all other abilities.",
    supertypes={"Legendary"},
)

PROPHETIC_PRISM = make_artifact(
    name="Prophetic Prism",
    mana_cost="{2}",
    text="When this artifact enters, draw a card.\n{1}, {T}: Add one mana of any color.",
)

SCARECROW_GUIDE = make_artifact_creature(
    name="Scarecrow Guide",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Scarecrow"},
    text="Reach\n{1}: Add one mana of any color. Activate only once each turn.",
)

SOULGUIDE_LANTERN = make_artifact(
    name="Soul-Guide Lantern",
    mana_cost="{1}",
    text="When this artifact enters, exile target card from a graveyard.\n{T}, Sacrifice this artifact: Exile each opponent's graveyard.\n{1}, {T}, Sacrifice this artifact: Draw a card.",
)

SYR_GINGER_THE_MEAL_ENDER = make_artifact_creature(
    name="Syr Ginger, the Meal Ender",
    power=3, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Food", "Knight"},
    supertypes={"Legendary"},
    text="Syr Ginger has trample, hexproof, and haste as long as an opponent controls a planeswalker.\nWhenever another artifact you control is put into a graveyard from the battlefield, put a +1/+1 counter on Syr Ginger and scry 1.\n{2}, {T}, Sacrifice Syr Ginger: You gain life equal to its power.",
)

THREE_BOWLS_OF_PORRIDGE = make_artifact(
    name="Three Bowls of Porridge",
    mana_cost="{2}",
    text="{2}, {T}: Choose one that hasn't been chosen —\n• This artifact deals 2 damage to target creature.\n• Tap target creature.\n• Sacrifice this artifact. You gain 3 life.",
    subtypes={"Food"},
)

CRYSTAL_GROTTO = make_land(
    name="Crystal Grotto",
    text="When this land enters, scry 1.\n{T}: Add {C}.\n{1}, {T}: Add one mana of any color.",
)

EDGEWALL_INN = make_land(
    name="Edgewall Inn",
    text="This land enters tapped.\nAs this land enters, choose a color.\n{T}: Add one mana of the chosen color.\n{3}, {T}, Sacrifice this land: Return target card that has an Adventure from your graveyard to your hand.",
)

EVOLVING_WILDS = make_land(
    name="Evolving Wilds",
    text="{T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
)

RESTLESS_BIVOUAC = make_land(
    name="Restless Bivouac",
    text="This land enters tapped.\n{T}: Add {R} or {W}.\n{1}{R}{W}: This land becomes a 2/2 red and white Ox creature until end of turn. It's still a land.\nWhenever this land attacks, put a +1/+1 counter on target creature you control.",
)

RESTLESS_COTTAGE = make_land(
    name="Restless Cottage",
    text="This land enters tapped.\n{T}: Add {B} or {G}.\n{2}{B}{G}: This land becomes a 4/4 black and green Horror creature until end of turn. It's still a land.\nWhenever this land attacks, create a Food token and exile up to one target card from a graveyard.",
)

RESTLESS_FORTRESS = make_land(
    name="Restless Fortress",
    text="This land enters tapped.\n{T}: Add {W} or {B}.\n{2}{W}{B}: This land becomes a 1/4 white and black Nightmare creature until end of turn. It's still a land.\nWhenever this land attacks, defending player loses 2 life and you gain 2 life.",
)

RESTLESS_SPIRE = make_land(
    name="Restless Spire",
    text="This land enters tapped.\n{T}: Add {U} or {R}.\n{U}{R}: Until end of turn, this land becomes a 2/1 blue and red Elemental creature with \"During your turn, this creature has first strike.\" It's still a land.\nWhenever this land attacks, scry 1.",
)

RESTLESS_VINESTALK = make_land(
    name="Restless Vinestalk",
    text="This land enters tapped.\n{T}: Add {G} or {U}.\n{3}{G}{U}: Until end of turn, this land becomes a 5/5 green and blue Plant creature with trample. It's still a land.\nWhenever this land attacks, up to one other target creature has base power and toughness 3/3 until end of turn.",
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

FOOD_COMA = make_enchantment(
    name="Food Coma",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, exile target creature an opponent controls until this enchantment leaves the battlefield. Create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")",
)

LADY_OF_LAUGHTER = make_creature(
    name="Lady of Laughter",
    power=4, toughness=5,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Faerie", "Noble"},
    text="Flying\nCelebration — At the beginning of your end step, if two or more nonland permanents entered the battlefield under your control this turn, draw a card.",
)

PESTS_OF_HONOR = make_creature(
    name="Pests of Honor",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Mouse"},
    text="Celebration — At the beginning of combat on your turn, if two or more nonland permanents entered the battlefield under your control this turn, put a +1/+1 counter on this creature.",
)

FAERIE_SLUMBER_PARTY = make_sorcery(
    name="Faerie Slumber Party",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Return all creatures to their owners' hands. For each opponent who controlled a creature returned this way, you create two 1/1 blue Faerie creature tokens with flying and \"This token can block only creatures with flying.\"",
)

ROWDY_RESEARCH = make_instant(
    name="Rowdy Research",
    mana_cost="{6}{U}",
    colors={Color.BLUE},
    text="This spell costs {1} less to cast for each creature that attacked this turn.\nDraw three cards.",
)

STORYTELLER_PIXIE = make_creature(
    name="Storyteller Pixie",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Wizard"},
    text="Flying\nWhenever you cast an Adventure spell, draw a card.",
)

EXPERIMENTAL_CONFECTIONER = make_creature(
    name="Experimental Confectioner",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Peasant"},
    text="When this creature enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\nWhenever you sacrifice a Food, create a 1/1 black Rat creature token with \"This token can't block.\"",
)

MALEVOLENT_WITCHKITE = make_creature(
    name="Malevolent Witchkite",
    power=5, toughness=4,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Dragon", "Warlock"},
    text="Flying\nWhen this creature enters, sacrifice any number of artifacts, enchantments, and/or tokens, then draw that many cards.",
)

OLD_FLITTERFANG = make_creature(
    name="Old Flitterfang",
    power=3, toughness=4,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Rat"},
    supertypes={"Legendary"},
    text="Flying\nAt the beginning of each end step, if a creature died this turn, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\n{2}{B}, Sacrifice another creature or artifact: Old Flitterfang gets +2/+2 until end of turn.",
)

BECOME_BRUTES = make_sorcery(
    name="Become Brutes",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="One or two target creatures each gain haste until end of turn. For each of those creatures, create a Monster Role token attached to it. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1 and has trample.)",
)

CHARGING_HOOLIGAN = make_creature(
    name="Charging Hooligan",
    power=3, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Peasant"},
    text="Whenever this creature attacks, it gets +1/+0 until end of turn for each attacking creature. If a Rat is attacking, this creature gains trample until end of turn.",
)

OGRE_CHITTERLORD = make_creature(
    name="Ogre Chitterlord",
    power=6, toughness=5,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Ogre", "Warrior"},
    text="Menace\nWhenever this creature enters or attacks, create two 1/1 black Rat creature tokens with \"This token can't block.\" Then if you control five or more Rats, each Rat you control gets +2/+0 until end of turn.",
)

INTREPID_TRUFFLESNOUT = make_creature(
    name="Intrepid Trufflesnout",
    power=3, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Boar"},
    text="Whenever this creature attacks alone, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\n// Adventure — Go Hog Wild {1}{G}\nTarget creature gets +2/+2 until end of turn. (Then exile this card. You may cast the creature later from exile.)",
)

PROVISIONS_MERCHANT = make_creature(
    name="Provisions Merchant",
    power=3, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Peasant"},
    text="When this creature enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\nWhenever this creature attacks, you may sacrifice a Food. If you do, attacking creatures get +1/+1 and gain trample until end of turn.",
)

WILDWOOD_MENTOR = make_creature(
    name="Wildwood Mentor",
    power=1, toughness=1,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="Whenever a token you control enters, put a +1/+1 counter on this creature.\nWhenever this creature attacks, another target attacking creature gets +X/+X until end of turn, where X is this creature's power.",
)

# =============================================================================
# CARD REGISTRY
# =============================================================================

WILDS_OF_ELDRAINE_CARDS = {
    "Archon of the Wild Rose": ARCHON_OF_THE_WILD_ROSE,
    "Archon's Glory": ARCHONS_GLORY,
    "Armory Mice": ARMORY_MICE,
    "Besotted Knight": BESOTTED_KNIGHT,
    "Break the Spell": BREAK_THE_SPELL,
    "Charmed Clothier": CHARMED_CLOTHIER,
    "Cheeky House-Mouse": CHEEKY_HOUSEMOUSE,
    "Cooped Up": COOPED_UP,
    "Cursed Courtier": CURSED_COURTIER,
    "Discerning Financier": DISCERNING_FINANCIER,
    "Dutiful Griffin": DUTIFUL_GRIFFIN,
    "Eerie Interference": EERIE_INTERFERENCE,
    "Expel the Interlopers": EXPEL_THE_INTERLOPERS,
    "Frostbridge Guard": FROSTBRIDGE_GUARD,
    "Gallant Pie-Wielder": GALLANT_PIEWIELDER,
    "Glass Casket": GLASS_CASKET,
    "Hopeful Vigil": HOPEFUL_VIGIL,
    "Kellan's Lightblades": KELLANS_LIGHTBLADES,
    "Knight of Doves": KNIGHT_OF_DOVES,
    "Moment of Valor": MOMENT_OF_VALOR,
    "Moonshaker Cavalry": MOONSHAKER_CAVALRY,
    "Plunge into Winter": PLUNGE_INTO_WINTER,
    "The Princess Takes Flight": THE_PRINCESS_TAKES_FLIGHT,
    "Protective Parents": PROTECTIVE_PARENTS,
    "Regal Bunnicorn": REGAL_BUNNICORN,
    "Return Triumphant": RETURN_TRIUMPHANT,
    "Rimefur Reindeer": RIMEFUR_REINDEER,
    "Savior of the Sleeping": SAVIOR_OF_THE_SLEEPING,
    "Slumbering Keepguard": SLUMBERING_KEEPGUARD,
    "Solitary Sanctuary": SOLITARY_SANCTUARY,
    "Spellbook Vendor": SPELLBOOK_VENDOR,
    "Stockpiling Celebrant": STOCKPILING_CELEBRANT,
    "Stroke of Midnight": STROKE_OF_MIDNIGHT,
    "A Tale for the Ages": A_TALE_FOR_THE_AGES,
    "Three Blind Mice": THREE_BLIND_MICE,
    "Tuinvale Guide": TUINVALE_GUIDE,
    "Unassuming Sage": UNASSUMING_SAGE,
    "Virtue of Loyalty": VIRTUE_OF_LOYALTY,
    "Werefox Bodyguard": WEREFOX_BODYGUARD,
    "Aquatic Alchemist": AQUATIC_ALCHEMIST,
    "Archive Dragon": ARCHIVE_DRAGON,
    "Asinine Antics": ASININE_ANTICS,
    "Beluna's Gatekeeper": BELUNAS_GATEKEEPER,
    "Bitter Chill": BITTER_CHILL,
    "Chancellor of Tales": CHANCELLOR_OF_TALES,
    "Diminisher Witch": DIMINISHER_WITCH,
    "Disdainful Stroke": DISDAINFUL_STROKE,
    "Extraordinary Journey": EXTRAORDINARY_JOURNEY,
    "Farsight Ritual": FARSIGHT_RITUAL,
    "Freeze in Place": FREEZE_IN_PLACE,
    "Gadwick's First Duel": GADWICKS_FIRST_DUEL,
    "Galvanic Giant": GALVANIC_GIANT,
    "Horned Loch-Whale": HORNED_LOCHWHALE,
    "Ice Out": ICE_OUT,
    "Icewrought Sentry": ICEWROUGHT_SENTRY,
    "Ingenious Prodigy": INGENIOUS_PRODIGY,
    "Into the Fae Court": INTO_THE_FAE_COURT,
    "Johann's Stopgap": JOHANNS_STOPGAP,
    "Living Lectern": LIVING_LECTERN,
    "Merfolk Coralsmith": MERFOLK_CORALSMITH,
    "Misleading Motes": MISLEADING_MOTES,
    "Mocking Sprite": MOCKING_SPRITE,
    "Obyra's Attendants": OBYRAS_ATTENDANTS,
    "Picklock Prankster": PICKLOCK_PRANKSTER,
    "Quick Study": QUICK_STUDY,
    "Sleep-Cursed Faerie": SLEEPCURSED_FAERIE,
    "Sleight of Hand": SLEIGHT_OF_HAND,
    "Snaremaster Sprite": SNAREMASTER_SPRITE,
    "Spell Stutter": SPELL_STUTTER,
    "Splashy Spellcaster": SPLASHY_SPELLCASTER,
    "Stormkeld Prowler": STORMKELD_PROWLER,
    "Succumb to the Cold": SUCCUMB_TO_THE_COLD,
    "Talion's Messenger": TALIONS_MESSENGER,
    "Tenacious Tomeseeker": TENACIOUS_TOMESEEKER,
    "Vantress Transmuter": VANTRESS_TRANSMUTER,
    "Virtue of Knowledge": VIRTUE_OF_KNOWLEDGE,
    "Water Wings": WATER_WINGS,
    "Ashiok, Wicked Manipulator": ASHIOK_WICKED_MANIPULATOR,
    "Ashiok's Reaper": ASHIOKS_REAPER,
    "Back for Seconds": BACK_FOR_SECONDS,
    "Barrow Naughty": BARROW_NAUGHTY,
    "Beseech the Mirror": BESEECH_THE_MIRROR,
    "Candy Grapple": CANDY_GRAPPLE,
    "Conceited Witch": CONCEITED_WITCH,
    "Dream Spoilers": DREAM_SPOILERS,
    "Ego Drain": EGO_DRAIN,
    "The End": THE_END,
    "Eriette's Whisper": ERIETTES_WHISPER,
    "Faerie Dreamthief": FAERIE_DREAMTHIEF,
    "Faerie Fencing": FAERIE_FENCING,
    "Feed the Cauldron": FEED_THE_CAULDRON,
    "Fell Horseman": FELL_HORSEMAN,
    "Gumdrop Poisoner": GUMDROP_POISONER,
    "High Fae Negotiator": HIGH_FAE_NEGOTIATOR,
    "Hopeless Nightmare": HOPELESS_NIGHTMARE,
    "Lich-Knights' Conquest": LICHKNIGHTS_CONQUEST,
    "Lord Skitter, Sewer King": LORD_SKITTER_SEWER_KING,
    "Lord Skitter's Blessing": LORD_SKITTERS_BLESSING,
    "Lord Skitter's Butcher": LORD_SKITTERS_BUTCHER,
    "Mintstrosity": MINTSTROSITY,
    "Not Dead After All": NOT_DEAD_AFTER_ALL,
    "Rankle's Prank": RANKLES_PRANK,
    "Rat Out": RAT_OUT,
    "Rowan's Grim Search": ROWANS_GRIM_SEARCH,
    "Scream Puff": SCREAM_PUFF,
    "Shatter the Oath": SHATTER_THE_OATH,
    "Specter of Mortality": SPECTER_OF_MORTALITY,
    "Spiteful Hexmage": SPITEFUL_HEXMAGE,
    "Stingblade Assassin": STINGBLADE_ASSASSIN,
    "Sugar Rush": SUGAR_RUSH,
    "Sweettooth Witch": SWEETTOOTH_WITCH,
    "Taken by Nightmares": TAKEN_BY_NIGHTMARES,
    "Tangled Colony": TANGLED_COLONY,
    "Twisted Sewer-Witch": TWISTED_SEWERWITCH,
    "Virtue of Persistence": VIRTUE_OF_PERSISTENCE,
    "Voracious Vermin": VORACIOUS_VERMIN,
    "Warehouse Tabby": WAREHOUSE_TABBY,
    "Wicked Visitor": WICKED_VISITOR,
    "The Witch's Vanity": THE_WITCHS_VANITY,
    "Belligerent of the Ball": BELLIGERENT_OF_THE_BALL,
    "Bellowing Bruiser": BELLOWING_BRUISER,
    "Bespoke Battlegarb": BESPOKE_BATTLEGARB,
    "Boundary Lands Ranger": BOUNDARY_LANDS_RANGER,
    "Charming Scoundrel": CHARMING_SCOUNDREL,
    "Cut In": CUT_IN,
    "Edgewall Pack": EDGEWALL_PACK,
    "Embereth Veteran": EMBERETH_VETERAN,
    "Flick a Coin": FLICK_A_COIN,
    "Food Fight": FOOD_FIGHT,
    "Frantic Firebolt": FRANTIC_FIREBOLT,
    "Gnawing Crescendo": GNAWING_CRESCENDO,
    "Goddric, Cloaked Reveler": GODDRIC_CLOAKED_REVELER,
    "Grabby Giant": GRABBY_GIANT,
    "Grand Ball Guest": GRAND_BALL_GUEST,
    "Harried Spearguard": HARRIED_SPEARGUARD,
    "Hearth Elemental": HEARTH_ELEMENTAL,
    "Imodane, the Pyrohammer": IMODANE_THE_PYROHAMMER,
    "Kindled Heroism": KINDLED_HEROISM,
    "Korvold and the Noble Thief": KORVOLD_AND_THE_NOBLE_THIEF,
    "Merry Bards": MERRY_BARDS,
    "Minecart Daredevil": MINECART_DAREDEVIL,
    "Monstrous Rage": MONSTROUS_RAGE,
    "Raging Battle Mouse": RAGING_BATTLE_MOUSE,
    "Ratcatcher Trainee": RATCATCHER_TRAINEE,
    "Realm-Scorcher Hellkite": REALMSCORCHER_HELLKITE,
    "Redcap Gutter-Dweller": REDCAP_GUTTERDWELLER,
    "Redcap Thief": REDCAP_THIEF,
    "Rotisserie Elemental": ROTISSERIE_ELEMENTAL,
    "Skewer Slinger": SKEWER_SLINGER,
    "Song of Totentanz": SONG_OF_TOTENTANZ,
    "Stonesplitter Bolt": STONESPLITTER_BOLT,
    "Tattered Ratter": TATTERED_RATTER,
    "Torch the Tower": TORCH_THE_TOWER,
    "Twisted Fealty": TWISTED_FEALTY,
    "Two-Headed Hunter": TWOHEADED_HUNTER,
    "Unruly Catapult": UNRULY_CATAPULT,
    "Virtue of Courage": VIRTUE_OF_COURAGE,
    "Witch's Mark": WITCHS_MARK,
    "Witchstalker Frenzy": WITCHSTALKER_FRENZY,
    "Agatha's Champion": AGATHAS_CHAMPION,
    "Beanstalk Wurm": BEANSTALK_WURM,
    "Bestial Bloodline": BESTIAL_BLOODLINE,
    "Blossoming Tortoise": BLOSSOMING_TORTOISE,
    "Bramble Familiar": BRAMBLE_FAMILIAR,
    "Brave the Wilds": BRAVE_THE_WILDS,
    "Commune with Nature": COMMUNE_WITH_NATURE,
    "Curse of the Werefox": CURSE_OF_THE_WEREFOX,
    "Elvish Archivist": ELVISH_ARCHIVIST,
    "Feral Encounter": FERAL_ENCOUNTER,
    "Ferocious Werefox": FEROCIOUS_WEREFOX,
    "Graceful Takedown": GRACEFUL_TAKEDOWN,
    "Gruff Triplets": GRUFF_TRIPLETS,
    "Hamlet Glutton": HAMLET_GLUTTON,
    "Hollow Scavenger": HOLLOW_SCAVENGER,
    "Howling Galefang": HOWLING_GALEFANG,
    "The Huntsman's Redemption": THE_HUNTSMANS_REDEMPTION,
    "Leaping Ambush": LEAPING_AMBUSH,
    "Night of the Sweets' Revenge": NIGHT_OF_THE_SWEETS_REVENGE,
    "Redtooth Genealogist": REDTOOTH_GENEALOGIST,
    "Redtooth Vanguard": REDTOOTH_VANGUARD,
    "Return from the Wilds": RETURN_FROM_THE_WILDS,
    "Rootrider Faun": ROOTRIDER_FAUN,
    "Royal Treatment": ROYAL_TREATMENT,
    "Sentinel of Lost Lore": SENTINEL_OF_LOST_LORE,
    "Skybeast Tracker": SKYBEAST_TRACKER,
    "Spider Food": SPIDER_FOOD,
    "Stormkeld Vanguard": STORMKELD_VANGUARD,
    "Tanglespan Lookout": TANGLESPAN_LOOKOUT,
    "Territorial Witchstalker": TERRITORIAL_WITCHSTALKER,
    "Thunderous Debut": THUNDEROUS_DEBUT,
    "Titanic Growth": TITANIC_GROWTH,
    "Toadstool Admirer": TOADSTOOL_ADMIRER,
    "Tough Cookie": TOUGH_COOKIE,
    "Troublemaker Ouphe": TROUBLEMAKER_OUPHE,
    "Up the Beanstalk": UP_THE_BEANSTALK,
    "Verdant Outrider": VERDANT_OUTRIDER,
    "Virtue of Strength": VIRTUE_OF_STRENGTH,
    "Welcome to Sweettooth": WELCOME_TO_SWEETTOOTH,
    "Agatha of the Vile Cauldron": AGATHA_OF_THE_VILE_CAULDRON,
    "The Apprentice's Folly": THE_APPRENTICES_FOLLY,
    "Ash, Party Crasher": ASH_PARTY_CRASHER,
    "Eriette of the Charmed Apple": ERIETTE_OF_THE_CHARMED_APPLE,
    "Faunsbane Troll": FAUNSBANE_TROLL,
    "The Goose Mother": THE_GOOSE_MOTHER,
    "Greta, Sweettooth Scourge": GRETA_SWEETTOOTH_SCOURGE,
    "Hylda of the Icy Crown": HYLDA_OF_THE_ICY_CROWN,
    "Johann, Apprentice Sorcerer": JOHANN_APPRENTICE_SORCERER,
    "Likeness Looter": LIKENESS_LOOTER,
    "Neva, Stalked by Nightmares": NEVA_STALKED_BY_NIGHTMARES,
    "Obyra, Dreaming Duelist": OBYRA_DREAMING_DUELIST,
    "Rowan, Scion of War": ROWAN_SCION_OF_WAR,
    "Ruby, Daring Tracker": RUBY_DARING_TRACKER,
    "Sharae of Numbing Depths": SHARAE_OF_NUMBING_DEPTHS,
    "Syr Armont, the Redeemer": SYR_ARMONT_THE_REDEEMER,
    "Talion, the Kindly Lord": TALION_THE_KINDLY_LORD,
    "Totentanz, Swarm Piper": TOTENTANZ_SWARM_PIPER,
    "Troyan, Gutsy Explorer": TROYAN_GUTSY_EXPLORER,
    "Will, Scion of Peace": WILL_SCION_OF_PEACE,
    "Yenna, Redtooth Regent": YENNA_REDTOOTH_REGENT,
    "Beluna Grandsquall": BELUNA_GRANDSQUALL,
    "Callous Sell-Sword": CALLOUS_SELLSWORD,
    "Cruel Somnophage": CRUEL_SOMNOPHAGE,
    "Decadent Dragon": DECADENT_DRAGON,
    "Devouring Sugarmaw": DEVOURING_SUGARMAW,
    "Elusive Otter": ELUSIVE_OTTER,
    "Frolicking Familiar": FROLICKING_FAMILIAR,
    "Gingerbread Hunter": GINGERBREAD_HUNTER,
    "Heartflame Duelist": HEARTFLAME_DUELIST,
    "Imodane's Recruiter": IMODANES_RECRUITER,
    "Kellan, the Fae-Blooded": KELLAN_THE_FAEBLOODED,
    "Mosswood Dreadknight": MOSSWOOD_DREADKNIGHT,
    "Picnic Ruiner": PICNIC_RUINER,
    "Pollen-Shield Hare": POLLENSHIELD_HARE,
    "Questing Druid": QUESTING_DRUID,
    "Scalding Viper": SCALDING_VIPER,
    "Shrouded Shepherd": SHROUDED_SHEPHERD,
    "Spellscorn Coven": SPELLSCORN_COVEN,
    "Tempest Hart": TEMPEST_HART,
    "Threadbind Clique": THREADBIND_CLIQUE,
    "Twining Twins": TWINING_TWINS,
    "Woodland Acolyte": WOODLAND_ACOLYTE,
    "Agatha's Soul Cauldron": AGATHAS_SOUL_CAULDRON,
    "Candy Trail": CANDY_TRAIL,
    "Collector's Vault": COLLECTORS_VAULT,
    "Eriette's Tempting Apple": ERIETTES_TEMPTING_APPLE,
    "Gingerbrute": GINGERBRUTE,
    "Hylda's Crown of Winter": HYLDAS_CROWN_OF_WINTER,
    "The Irencrag": THE_IRENCRAG,
    "Prophetic Prism": PROPHETIC_PRISM,
    "Scarecrow Guide": SCARECROW_GUIDE,
    "Soul-Guide Lantern": SOULGUIDE_LANTERN,
    "Syr Ginger, the Meal Ender": SYR_GINGER_THE_MEAL_ENDER,
    "Three Bowls of Porridge": THREE_BOWLS_OF_PORRIDGE,
    "Crystal Grotto": CRYSTAL_GROTTO,
    "Edgewall Inn": EDGEWALL_INN,
    "Evolving Wilds": EVOLVING_WILDS,
    "Restless Bivouac": RESTLESS_BIVOUAC,
    "Restless Cottage": RESTLESS_COTTAGE,
    "Restless Fortress": RESTLESS_FORTRESS,
    "Restless Spire": RESTLESS_SPIRE,
    "Restless Vinestalk": RESTLESS_VINESTALK,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
    "Food Coma": FOOD_COMA,
    "Lady of Laughter": LADY_OF_LAUGHTER,
    "Pests of Honor": PESTS_OF_HONOR,
    "Faerie Slumber Party": FAERIE_SLUMBER_PARTY,
    "Rowdy Research": ROWDY_RESEARCH,
    "Storyteller Pixie": STORYTELLER_PIXIE,
    "Experimental Confectioner": EXPERIMENTAL_CONFECTIONER,
    "Malevolent Witchkite": MALEVOLENT_WITCHKITE,
    "Old Flitterfang": OLD_FLITTERFANG,
    "Become Brutes": BECOME_BRUTES,
    "Charging Hooligan": CHARGING_HOOLIGAN,
    "Ogre Chitterlord": OGRE_CHITTERLORD,
    "Intrepid Trufflesnout": INTREPID_TRUFFLESNOUT,
    "Provisions Merchant": PROVISIONS_MERCHANT,
    "Wildwood Mentor": WILDWOOD_MENTOR,
}

print(f"Loaded {len(WILDS_OF_ELDRAINE_CARDS)} Wilds of Eldraine cards")
