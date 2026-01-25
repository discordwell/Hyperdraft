"""
Final Fantasy (FIN) Card Implementations

Real card data fetched from Scryfall API.
313 cards in set.
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

SUMMON_BAHAMUT = make_enchantment_creature(
    name="Summon: Bahamut",
    power=9, toughness=9,
    mana_cost="{9}",
    colors=set(),
    subtypes={"Dragon", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after IV.)\nI, II — Destroy up to one target nonland permanent.\nIII — Draw two cards.\nIV — Mega Flare — This creature deals damage equal to the total mana value of other permanents you control to each opponent.\nFlying",
)

ULTIMA_ORIGIN_OF_OBLIVION = make_creature(
    name="Ultima, Origin of Oblivion",
    power=4, toughness=4,
    mana_cost="{5}",
    colors=set(),
    subtypes={"God"},
    supertypes={"Legendary"},
    text="Flying\nWhenever Ultima attacks, put a blight counter on target land. For as long as that land has a blight counter on it, it loses all land types and abilities and has \"{T}: Add {C}.\"\nWhenever you tap a land for {C}, add an additional {C}.",
)

ADELBERT_STEINER = make_creature(
    name="Adelbert Steiner",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="Lifelink\nAdelbert Steiner gets +1/+1 for each Equipment you control.",
)

AERITH_GAINSBOROUGH = make_creature(
    name="Aerith Gainsborough",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Human"},
    supertypes={"Legendary"},
    text="Lifelink\nWhenever you gain life, put a +1/+1 counter on Aerith Gainsborough.\nWhen Aerith Gainsborough dies, put X +1/+1 counters on each legendary creature you control, where X is the number of +1/+1 counters on Aerith Gainsborough.",
)

AERITH_RESCUE_MISSION = make_sorcery(
    name="Aerith Rescue Mission",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Take the Elevator — Create three 1/1 colorless Hero creature tokens.\n• Take 59 Flights of Stairs — Tap up to three target creatures. Put a stun counter on one of them. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

AMBROSIA_WHITEHEART = make_creature(
    name="Ambrosia Whiteheart",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Bird"},
    supertypes={"Legendary"},
    text="Flash\nWhen Ambrosia Whiteheart enters, you may return another permanent you control to its owner's hand.\nLandfall — Whenever a land you control enters, Ambrosia Whiteheart gets +1/+0 until end of turn.",
)

ASHE_PRINCESS_OF_DALMASCA = make_creature(
    name="Ashe, Princess of Dalmasca",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble", "Rebel"},
    supertypes={"Legendary"},
    text="Whenever Ashe attacks, look at the top five cards of your library. You may reveal an artifact card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
)

AURONS_INSPIRATION = make_instant(
    name="Auron's Inspiration",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Attacking creatures get +2/+0 until end of turn.\nFlashback {2}{W}{W} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

BATTLE_MENU = make_instant(
    name="Battle Menu",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Attack — Create a 2/2 white Knight creature token.\n• Ability — Target creature gets +0/+4 until end of turn.\n• Magic — Destroy target creature with power 4 or greater.\n• Item — You gain 4 life.",
)

CLOUD_MIDGAR_MERCENARY = make_creature(
    name="Cloud, Midgar Mercenary",
    power=2, toughness=1,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Mercenary", "Soldier"},
    supertypes={"Legendary"},
    text="When Cloud enters, search your library for an Equipment card, reveal it, put it into your hand, then shuffle.\nAs long as Cloud is equipped, if an ability of Cloud or an Equipment attached to it triggers, that ability triggers an additional time.",
)

CLOUDBOUND_MOOGLE = make_creature(
    name="Cloudbound Moogle",
    power=2, toughness=3,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Moogle"},
    text="Flying\nWhen this creature enters, put a +1/+1 counter on target creature.\nPlainscycling {2} ({2}, Discard this card: Search your library for a Plains card, reveal it, put it into your hand, then shuffle.)",
)

COEURL = make_creature(
    name="Coeurl",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Beast", "Cat"},
    text="{1}{W}, {T}: Tap target nonenchantment creature.",
)

CRYSTAL_FRAGMENTS = make_artifact(
    name="Crystal Fragments",
    mana_cost="{W}",
    text="Equipped creature gets +1/+1.\n{5}{W}{W}: Exile this Equipment, then return it to the battlefield transformed under its owner's control. Activate only as a sorcery.\nEquip {1}\n// Transforms into: Summon: Alexander (4/3)\n(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI, II — Prevent all damage that would be dealt to creatures you control this turn.\nIII — Tap all creatures your opponents control.\nFlying",
    subtypes={"Equipment"},
)

THE_CRYSTALS_CHOSEN = make_sorcery(
    name="The Crystal's Chosen",
    mana_cost="{5}{W}{W}",
    colors={Color.WHITE},
    text="Create four 1/1 colorless Hero creature tokens. Then put a +1/+1 counter on each creature you control.",
)

DELIVERY_MOOGLE = make_creature(
    name="Delivery Moogle",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Moogle"},
    text="Flying\nWhen this creature enters, search your library and/or graveyard for an artifact card with mana value 2 or less, reveal it, and put it into your hand. If you search your library this way, shuffle.",
)

DION_BAHAMUTS_DOMINANT = make_creature(
    name="Dion, Bahamut's Dominant",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight", "Noble"},
    supertypes={"Legendary"},
    text="Dragonfire Dive — During your turn, Dion and other Knights you control have flying.\nWhen Dion enters, create a 2/2 white Knight creature token.\n{4}{W}{W}, {T}: Exile Dion, then return it to the battlefield transformed under its owner's control. Activate only as a sorcery.\n// Transforms into: Bahamut, Warden of Light (5/5)\n(As this Saga enters and after your draw step, add a lore counter.)\nI, II — Wings of Light — Put a +1/+1 counter on each other creature you control. Those creatures gain flying until end of turn.\nIII — Gigaflare — Destroy target permanent. Exile Bahamut, then return it to the battlefield (front face up).\nFlying",
)

DRAGOONS_LANCE = make_artifact(
    name="Dragoon's Lance",
    mana_cost="{1}{W}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +1/+0 and is a Knight in addition to its other types.\nDuring your turn, equipped creature has flying.\nGae Bolg — Equip {4}",
    subtypes={"Equipment"},
)

DWARVEN_CASTLE_GUARD = make_creature(
    name="Dwarven Castle Guard",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Dwarf", "Soldier"},
    text="When this creature dies, create a 1/1 colorless Hero creature token.",
)

FATE_OF_THE_SUNCRYST = make_instant(
    name="Fate of the Sun-Cryst",
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    text="This spell costs {2} less to cast if it targets a tapped creature.\nDestroy target nonland permanent.",
)

FROM_FATHER_TO_SON = make_sorcery(
    name="From Father to Son",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Search your library for a Vehicle card, reveal it, and put it into your hand. If this spell was cast from a graveyard, put that card onto the battlefield instead. Then shuffle.\nFlashback {4}{W}{W}{W} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

GRAHA_TIA = make_creature(
    name="G'raha Tia",
    power=3, toughness=5,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Archer", "Cat"},
    supertypes={"Legendary"},
    text="Reach\nThe Allagan Eye — Whenever one or more other creatures and/or artifacts you control die, draw a card. This ability triggers only once each turn.",
)

GAELICAT = make_creature(
    name="Gaelicat",
    power=1, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Cat"},
    text="Flying, vigilance\nAs long as you control two or more artifacts, this creature gets +2/+0.",
)

MACHINISTS_ARSENAL = make_artifact(
    name="Machinist's Arsenal",
    mana_cost="{4}{W}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +2/+2 for each artifact you control and is an Artificer in addition to its other types.\nMachina — Equip {4} ({4}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

MAGITEK_ARMOR = make_artifact(
    name="Magitek Armor",
    mana_cost="{3}{W}",
    text="When this Vehicle enters, create a 1/1 colorless Hero creature token.\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
)

MAGITEK_INFANTRY = make_artifact_creature(
    name="Magitek Infantry",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Robot", "Soldier"},
    text="This creature gets +1/+0 as long as you control another artifact.\n{2}{W}: Search your library for a card named Magitek Infantry, put it onto the battlefield tapped, then shuffle.",
)

MINWU_WHITE_MAGE = make_creature(
    name="Minwu, White Mage",
    power=3, toughness=3,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Human"},
    supertypes={"Legendary"},
    text="Vigilance, lifelink\nWhenever you gain life, put a +1/+1 counter on each Cleric you control.",
)

MOOGLES_VALOR = make_instant(
    name="Moogles' Valor",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="For each creature you control, create a 1/2 white Moogle creature token with lifelink. Then creatures you control gain indestructible until end of turn.",
)

PALADINS_ARMS = make_artifact(
    name="Paladin's Arms",
    mana_cost="{2}{W}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +2/+1, has ward {1}, and is a Knight in addition to its other types.\nLightbringer and Hero's Shield — Equip {4} ({4}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

PHOENIX_DOWN = make_artifact(
    name="Phoenix Down",
    mana_cost="{W}",
    text="{1}{W}, {T}, Exile this artifact: Choose one —\n• Return target creature card with mana value 4 or less from your graveyard to the battlefield tapped.\n• Exile target Skeleton, Spirit, or Zombie.",
)

RESTORATION_MAGIC = make_instant(
    name="Restoration Magic",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Tiered (Choose one additional cost.)\n• Cure — {0} — Target permanent gains hexproof and indestructible until end of turn.\n• Cura — {1} — Target permanent gains hexproof and indestructible until end of turn. You gain 3 life.\n• Curaga — {3}{W} — Permanents you control gain hexproof and indestructible until end of turn. You gain 6 life.",
)

SIDEQUEST_CATCH_A_FISH = make_enchantment(
    name="Sidequest: Catch a Fish",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="At the beginning of your upkeep, look at the top card of your library. If it's an artifact or creature card, you may reveal it and put it into your hand. If you put a card into your hand this way, create a Food token and transform this enchantment.\n// Transforms into: Cooking Campsite\n{T}: Add {W}.\n{3}, {T}, Sacrifice an artifact: Put a +1/+1 counter on each creature you control. Activate only as a sorcery.",
)

SLASH_OF_LIGHT = make_instant(
    name="Slash of Light",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Slash of Light deals damage equal to the number of creatures you control plus the number of Equipment you control to target creature.",
)

SNOW_VILLIERS = make_creature(
    name="Snow Villiers",
    power=0, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk", "Rebel"},
    supertypes={"Legendary"},
    text="Vigilance\nSnow Villiers's power is equal to the number of creatures you control.",
)

STILTZKIN_MOOGLE_MERCHANT = make_creature(
    name="Stiltzkin, Moogle Merchant",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Moogle"},
    supertypes={"Legendary"},
    text="Lifelink\n{2}, {T}: Target opponent gains control of another target permanent you control. If they do, you draw a card.",
)

SUMMON_CHOCOMOG = make_enchantment_creature(
    name="Summon: Choco/Mog",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Bird", "Moogle", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after IV.)\nI, II, III, IV — Stampede! — Other creatures you control get +1/+0 until end of turn.",
)

SUMMON_KNIGHTS_OF_ROUND = make_enchantment_creature(
    name="Summon: Knights of Round",
    power=3, toughness=3,
    mana_cost="{6}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Knight", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after V.)\nI, II, III, IV — Create three 2/2 white Knight creature tokens.\nV — Ultimate End — Other creatures you control get +2/+2 until end of turn. Put an indestructible counter on each of them.\nIndestructible",
)

SUMMON_PRIMAL_GARUDA = make_enchantment_creature(
    name="Summon: Primal Garuda",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Harpy", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Aerial Blast — This creature deals 4 damage to target tapped creature an opponent controls.\nII, III — Slipstream — Another target creature you control gets +1/+0 and gains flying until end of turn.\nFlying",
)

ULTIMA = make_sorcery(
    name="Ultima",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Destroy all artifacts and creatures. End the turn. (Exile all spells and abilities from the stack, including this card. The player whose turn it is discards down to their maximum hand size. Damage wears off, and \"this turn\" and \"until end of turn\" effects end.)",
)

VENAT_HEART_OF_HYDAELYN = make_creature(
    name="Venat, Heart of Hydaelyn",
    power=3, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Elder", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast a legendary spell, draw a card. This ability triggers only once each turn.\nHero's Sundering — {7}, {T}: Exile target nonland permanent. Transform Venat. Activate only as a sorcery.\n// Transforms into: Hydaelyn, the Mothercrystal (4/4)\nIndestructible\nBlessing of Light — At the beginning of combat on your turn, put a +1/+1 counter on another target creature you control. Until your next turn, it gains indestructible. If that creature is legendary, draw a card.",
)

WEAPONS_VENDOR = make_creature(
    name="Weapons Vendor",
    power=2, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Artificer", "Human"},
    text="When this creature enters, draw a card.\nAt the beginning of combat on your turn, if you control an Equipment, you may pay {1}. When you do, attach target Equipment you control to target creature you control.",
)

WHITE_AURACITE = make_artifact(
    name="White Auracite",
    mana_cost="{2}{W}{W}",
    text="When this artifact enters, exile target nonland permanent an opponent controls until this artifact leaves the battlefield.\n{T}: Add {W}.",
)

WHITE_MAGES_STAFF = make_artifact(
    name="White Mage's Staff",
    mana_cost="{1}{W}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +1/+1, has \"Whenever this creature attacks, you gain 1 life,\" and is a Cleric in addition to its other types.\nEquip {3} ({3}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

THE_WIND_CRYSTAL = make_artifact(
    name="The Wind Crystal",
    mana_cost="{2}{W}{W}",
    text="White spells you cast cost {1} less to cast.\nIf you would gain life, you gain twice that much life instead.\n{4}{W}{W}, {T}: Creatures you control gain flying and lifelink until end of turn.",
    supertypes={"Legendary"},
)

YOURE_NOT_ALONE = make_instant(
    name="You're Not Alone",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 until end of turn. If you control three or more creatures, it gets +4/+4 until end of turn instead.",
)

ZACK_FAIR = make_creature(
    name="Zack Fair",
    power=0, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Zack Fair enters with a +1/+1 counter on it.\n{1}, Sacrifice Zack Fair: Target creature you control gains indestructible until end of turn. Put Zack Fair's counters on that creature and attach an Equipment that was attached to Zack Fair to that creature.",
)

ASTROLOGIANS_PLANISPHERE = make_artifact(
    name="Astrologian's Planisphere",
    mana_cost="{1}{U}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature is a Wizard in addition to its other types and has \"Whenever you cast a noncreature spell and whenever you draw your third card each turn, put a +1/+1 counter on this creature.\"\nDiana — Equip {2}",
    subtypes={"Equipment"},
)

CARGO_SHIP = make_artifact(
    name="Cargo Ship",
    mana_cost="{1}{U}",
    text="Flying, vigilance\n{T}: Add {C}. Spend this mana only to cast an artifact spell or activate an ability of an artifact source.\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
)

COMBAT_TUTORIAL = make_sorcery(
    name="Combat Tutorial",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Target player draws two cards. Put a +1/+1 counter on up to one target creature you control.",
)

DRAGOONS_WYVERN = make_creature(
    name="Dragoon's Wyvern",
    power=2, toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Drake"},
    text="Flying\nWhen this creature enters, create a 1/1 colorless Hero creature token.",
)

DREAMS_OF_LAGUNA = make_instant(
    name="Dreams of Laguna",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Surveil 1, then draw a card. (To surveil 1, look at the top card of your library. You may put it into your graveyard.)\nFlashback {3}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

EDGAR_KING_OF_FIGARO = make_creature(
    name="Edgar, King of Figaro",
    power=4, toughness=5,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Artificer", "Human", "Noble"},
    supertypes={"Legendary"},
    text="When Edgar enters, draw a card for each artifact you control.\nTwo-Headed Coin — The first time you flip one or more coins each turn, those coins come up heads and you win those flips.",
)

EJECT = make_instant(
    name="Eject",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="This spell can't be countered.\nReturn target nonland permanent to its owner's hand.\nDraw a card.",
)

ETHER = make_artifact(
    name="Ether",
    mana_cost="{3}{U}",
    text="{T}, Exile this artifact: Add {U}. When you next cast an instant or sorcery spell this turn, copy that spell. You may choose new targets for the copy.",
)

GOGO_MASTER_OF_MIMICRY = make_creature(
    name="Gogo, Master of Mimicry",
    power=2, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Wizard"},
    supertypes={"Legendary"},
    text="{X}{X}, {T}: Copy target activated or triggered ability you control X times. You may choose new targets for the copies. This ability can't be copied and X can't be 0. (Mana abilities can't be targeted.)",
)

ICE_FLAN = make_creature(
    name="Ice Flan",
    power=5, toughness=4,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Ooze"},
    text="When this creature enters, tap target artifact or creature an opponent controls. Put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nIslandcycling {2} ({2}, Discard this card: Search your library for an Island card, reveal it, put it into your hand, then shuffle.)",
)

ICE_MAGIC = make_instant(
    name="Ice Magic",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Tiered (Choose one additional cost.)\n• Blizzard — {0} — Return target creature to its owner's hand.\n• Blizzara — {2} — Target creature's owner puts it on their choice of the top or bottom of their library.\n• Blizzaga — {5}{U} — Target creature's owner shuffles it into their library.",
)

IL_MHEG_PIXIE = make_creature(
    name="Il Mheg Pixie",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie"},
    text="Flying\nWhenever this creature attacks, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

JILL_SHIVAS_DOMINANT = make_creature(
    name="Jill, Shiva's Dominant",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Noble", "Warrior"},
    supertypes={"Legendary"},
    text="When Jill enters, return up to one other target nonland permanent to its owner's hand.\n{3}{U}{U}, {T}: Exile Jill, then return it to the battlefield transformed under its owner's control. Activate only as a sorcery.\n// Transforms into: Shiva, Warden of Ice (4/5)\n(As this Saga enters and after your draw step, add a lore counter.)\nI, II — Mesmerize — Target creature can't be blocked this turn.\nIII — Cold Snap — Tap all lands your opponents control. Exile Shiva, then return it to the battlefield (front face up).",
)

LOUISOIXS_SACRIFICE = make_instant(
    name="Louisoix's Sacrifice",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="As an additional cost to cast this spell, sacrifice a legendary creature or pay {2}.\nCounter target activated ability, triggered ability, or noncreature spell.",
)

THE_LUNAR_WHALE = make_artifact(
    name="The Lunar Whale",
    mana_cost="{3}{U}",
    text="Flying\nYou may look at the top card of your library any time.\nAs long as The Lunar Whale attacked this turn, you may play the top card of your library.\nCrew 1",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
)

MAGIC_DAMPER = make_instant(
    name="Magic Damper",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature you control gets +1/+1 and gains hexproof until end of turn. Untap it.",
)

MATOYA_ARCHON_ELDER = make_creature(
    name="Matoya, Archon Elder",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Whenever you scry or surveil, draw a card. (Draw after you scry or surveil.)",
)

MEMORIES_RETURNING = make_sorcery(
    name="Memories Returning",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Reveal the top five cards of your library. Put one of them into your hand. Then choose an opponent. They put one on the bottom of your library. Then you put one into your hand. Then they put one on the bottom of your library. Put the other into your hand.\nFlashback {7}{U}{U}",
)

THE_PRIMA_VISTA = make_artifact(
    name="The Prima Vista",
    mana_cost="{4}{U}",
    text="Flying\nWhenever you cast a noncreature spell, if at least four mana was spent to cast it, The Prima Vista becomes an artifact creature until end of turn.\nCrew 2 (Tap any number of creatures you control with total power 2 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
)

QIQIRN_MERCHANT = make_creature(
    name="Qiqirn Merchant",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Beast", "Citizen"},
    text="{1}, {T}: Draw a card, then discard a card.\n{7}, {T}, Sacrifice this creature: Draw three cards. This ability costs {1} less to activate for each Town you control.",
)

QUISTIS_TREPE = make_creature(
    name="Quistis Trepe",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Blue Magic — When Quistis Trepe enters, you may cast target instant or sorcery card from a graveyard, and mana of any type can be spent to cast that spell. If that spell would be put into a graveyard, exile it instead.",
)

RELMS_SKETCHING = make_sorcery(
    name="Relm's Sketching",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Create a token that's a copy of target artifact, creature, or land.",
)

RETRIEVE_THE_ESPER = make_sorcery(
    name="Retrieve the Esper",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Create a 3/3 blue Robot Warrior artifact creature token. Then if this spell was cast from a graveyard, put two +1/+1 counters on that token.\nFlashback {5}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

ROOK_TURRET = make_artifact_creature(
    name="Rook Turret",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Construct"},
    text="Flying\nWhenever another artifact you control enters, you may draw a card. If you do, discard a card.",
)

SAGES_NOULITHS = make_artifact(
    name="Sage's Nouliths",
    mana_cost="{1}{U}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +1/+0, has \"Whenever this creature attacks, untap target attacking creature,\" and is a Cleric in addition to its other types.\nHagneia — Equip {3}",
    subtypes={"Equipment"},
)

SAHAGIN = make_creature(
    name="Sahagin",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Warrior"},
    text="Whenever you cast a noncreature spell, if at least four mana was spent to cast it, put a +1/+1 counter on this creature and it can't be blocked this turn.",
)

SCORPION_SENTINEL = make_artifact_creature(
    name="Scorpion Sentinel",
    power=1, toughness=4,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Robot", "Scorpion"},
    text="As long as you control seven or more lands, this creature gets +3/+0.",
)

SIDEQUEST_CARD_COLLECTION = make_enchantment(
    name="Sidequest: Card Collection",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="When this enchantment enters, draw three cards, then discard two cards.\nAt the beginning of your end step, if eight or more cards are in your graveyard, transform this enchantment.\n// Transforms into: Magicked Card (4/4)\nFlying\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
)

SLEEP_MAGIC = make_enchantment(
    name="Sleep Magic",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Enchant creature\nWhen this Aura enters, tap enchanted creature.\nEnchanted creature doesn't untap during its controller's untap step.\nWhen enchanted creature is dealt damage, sacrifice this Aura.",
    subtypes={"Aura"},
)

STOLEN_UNIFORM = make_instant(
    name="Stolen Uniform",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Choose target creature you control and target Equipment. Gain control of that Equipment until end of turn. Attach it to the chosen creature. When you lose control of that Equipment this turn, if it's attached to a creature you control, unattach it.",
)

STUCK_IN_SUMMONERS_SANCTUM = make_enchantment(
    name="Stuck in Summoner's Sanctum",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Flash\nEnchant artifact or creature\nWhen this Aura enters, tap enchanted permanent.\nEnchanted permanent doesn't untap during its controller's untap step and its activated abilities can't be activated.",
    subtypes={"Aura"},
)

SUMMON_LEVIATHAN = make_enchantment_creature(
    name="Summon: Leviathan",
    power=6, toughness=6,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Leviathan", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Return each creature that isn't a Kraken, Leviathan, Merfolk, Octopus, or Serpent to its owner's hand.\nII, III — Until end of turn, whenever a Kraken, Leviathan, Merfolk, Octopus, or Serpent attacks, draw a card.\nWard {2}",
)

SUMMON_SHIVA = make_enchantment_creature(
    name="Summon: Shiva",
    power=4, toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI, II — Heavenly Strike — Tap target creature an opponent controls. Put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nIII — Diamond Dust — Draw a card for each tapped creature your opponents control.",
)

SWALLOWED_BY_LEVIATHAN = make_instant(
    name="Swallowed by Leviathan",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Choose target spell. Surveil 2, then counter the chosen spell unless its controller pays {1} for each card in your graveyard. (To surveil 2, look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
)

SYNCOPATE = make_instant(
    name="Syncopate",
    mana_cost="{X}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {X}. If that spell is countered this way, exile it instead of putting it into its owner's graveyard.",
)

THIEFS_KNIFE = make_artifact(
    name="Thief's Knife",
    mana_cost="{2}{U}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +1/+1, has \"Whenever this creature deals combat damage to a player, draw a card,\" and is a Rogue in addition to its other types.\nEquip {4}",
    subtypes={"Equipment"},
)

TRAVEL_THE_OVERWORLD = make_sorcery(
    name="Travel the Overworld",
    mana_cost="{5}{U}{U}",
    colors={Color.BLUE},
    text="Affinity for Towns (This spell costs {1} less to cast for each Town you control.)\nDraw four cards.",
)

ULTROS_OBNOXIOUS_OCTOPUS = make_creature(
    name="Ultros, Obnoxious Octopus",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Octopus"},
    supertypes={"Legendary"},
    text="Whenever you cast a noncreature spell, if at least four mana was spent to cast it, tap target creature an opponent controls and put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nWhenever you cast a noncreature spell, if at least eight mana was spent to cast it, put eight +1/+1 counters on Ultros.",
)

VALKYRIE_AERIAL_UNIT = make_artifact_creature(
    name="Valkyrie Aerial Unit",
    power=5, toughness=4,
    mana_cost="{5}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Construct"},
    text="Affinity for artifacts (This spell costs {1} less to cast for each artifact you control.)\nFlying\nWhen this creature enters, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
)

THE_WATER_CRYSTAL = make_artifact(
    name="The Water Crystal",
    mana_cost="{2}{U}{U}",
    text="Blue spells you cast cost {1} less to cast.\nIf an opponent would mill one or more cards, they mill that many cards plus four instead.\n{4}{U}{U}, {T}: Each opponent mills cards equal to the number of cards in your hand.",
    supertypes={"Legendary"},
)

YSHTOLA_RHUL = make_creature(
    name="Y'shtola Rhul",
    power=3, toughness=5,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Cat", "Druid"},
    supertypes={"Legendary"},
    text="At the beginning of your end step, exile target creature you control, then return it to the battlefield under its owner's control. Then if it's the first end step of the turn, there is an additional end step after this step.",
)

AHRIMAN = make_creature(
    name="Ahriman",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Eye", "Horror"},
    text="Flying, deathtouch\n{3}, Sacrifice another creature or artifact: Draw a card.",
)

AL_BHED_SALVAGERS = make_creature(
    name="Al Bhed Salvagers",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Artificer", "Human", "Warrior"},
    text="Whenever this creature or another creature or artifact you control dies, target opponent loses 1 life and you gain 1 life.",
)

ARDYN_THE_USURPER = make_creature(
    name="Ardyn, the Usurper",
    power=4, toughness=4,
    mana_cost="{5}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Elder", "Human", "Noble"},
    supertypes={"Legendary"},
    text="Demons you control have menace, lifelink, and haste.\nStarscourge — At the beginning of combat on your turn, exile up to one target creature card from a graveyard. If you exiled a card this way, create a token that's a copy of that card, except it's a 5/5 black Demon.",
)

BLACK_MAGES_ROD = make_artifact(
    name="Black Mage's Rod",
    mana_cost="{1}{B}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +1/+0, has \"Whenever you cast a noncreature spell, this creature deals 1 damage to each opponent,\" and is a Wizard in addition to its other types.\nEquip {3}",
    subtypes={"Equipment"},
)

CECIL_DARK_KNIGHT = make_creature(
    name="Cecil, Dark Knight",
    power=2, toughness=3,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="Deathtouch\nDarkness — Whenever Cecil deals damage, you lose that much life. Then if your life total is less than or equal to half your starting life total, untap Cecil and transform it.\n// Transforms into: Cecil, Redeemed Paladin (4/4)\nLifelink\nProtect — Whenever Cecil attacks, other attacking creatures gain indestructible until end of turn.",
)

CIRCLE_OF_POWER = make_sorcery(
    name="Circle of Power",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="You draw two cards and you lose 2 life. Create a 0/1 black Wizard creature token with \"Whenever you cast a noncreature spell, this token deals 1 damage to each opponent.\"\nWizards you control get +1/+0 and gain lifelink until end of turn.",
)

CORNERED_BY_BLACK_MAGES = make_sorcery(
    name="Cornered by Black Mages",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Target opponent sacrifices a creature of their choice.\nCreate a 0/1 black Wizard creature token with \"Whenever you cast a noncreature spell, this token deals 1 damage to each opponent.\"",
)

DARK_CONFIDANT = make_creature(
    name="Dark Confidant",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard"},
    text="At the beginning of your upkeep, reveal the top card of your library and put that card into your hand. You lose life equal to its mana value.",
)

DARK_KNIGHTS_GREATSWORD = make_artifact(
    name="Dark Knight's Greatsword",
    mana_cost="{2}{B}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +3/+0 and is a Knight in addition to its other types.\nChaosbringer — Equip—Pay 3 life. Activate only once each turn.",
    subtypes={"Equipment"},
)

THE_DARKNESS_CRYSTAL = make_artifact(
    name="The Darkness Crystal",
    mana_cost="{2}{B}{B}",
    text="Black spells you cast cost {1} less to cast.\nIf a nontoken creature an opponent controls would die, instead exile it and you gain 2 life.\n{4}{B}{B}, {T}: Put target creature card exiled with The Darkness Crystal onto the battlefield tapped under your control with two additional +1/+1 counters on it.",
    supertypes={"Legendary"},
)

DEMON_WALL = make_artifact_creature(
    name="Demon Wall",
    power=3, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Wall"},
    text="Defender\nMenace (This creature can't be blocked except by two or more creatures.)\nAs long as this creature has a counter on it, it can attack as though it didn't have defender.\n{5}{B}: Put two +1/+1 counters on this creature.",
)

EVIL_REAWAKENED = make_sorcery(
    name="Evil Reawakened",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield with two additional +1/+1 counters on it.",
)

FANG_FEARLESS_LCIE = make_creature(
    name="Fang, Fearless l'Cie",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Whenever one or more cards leave your graveyard, you draw a card and you lose 1 life. This ability triggers only once each turn.\n(Melds with Vanille, Cheerful l'Cie.)",
)

RAGNAROK_DIVINE_DELIVERANCE = make_creature(
    name="Ragnarok, Divine Deliverance",
    power=7, toughness=6,
    mana_cost="",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Avatar", "Beast"},
    supertypes={"Legendary"},
    text="Vigilance, menace, trample, reach, haste\nWhen Ragnarok dies, destroy target permanent and return target nonlegendary permanent card from your graveyard to the battlefield.",
)

FIGHT_ON = make_instant(
    name="Fight On!",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Return up to two target creature cards from your graveyard to your hand.",
)

THE_FINAL_DAYS = make_sorcery(
    name="The Final Days",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Create two tapped 2/2 black Horror creature tokens. If this spell was cast from a graveyard, instead create X of those tokens, where X is the number of creature cards in your graveyard.\nFlashback {4}{B}{B} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

GAIUS_VAN_BAELSAR = make_creature(
    name="Gaius van Baelsar",
    power=3, toughness=2,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="When Gaius van Baelsar enters, choose one —\n• Each player sacrifices a creature token of their choice.\n• Each player sacrifices a nontoken creature of their choice.\n• Each player sacrifices an enchantment of their choice.",
)

HECTEYES = make_creature(
    name="Hecteyes",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Ooze"},
    text="When this creature enters, each opponent discards a card.",
)

JECHT_RELUCTANT_GUARDIAN = make_creature(
    name="Jecht, Reluctant Guardian",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Menace\nWhenever Jecht deals combat damage to a player, you may exile it, then return it to the battlefield transformed under its owner's control.\n// Transforms into: Braska's Final Aeon (7/7)\n(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI, II — Jecht Beam — Each opponent discards a card and you draw a card.\nIII — Ultimate Jecht Shot — Each opponent sacrifices two creatures of their choice.\nMenace",
)

KAIN_TRAITOROUS_DRAGOON = make_creature(
    name="Kain, Traitorous Dragoon",
    power=2, toughness=4,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="Jump — During your turn, Kain has flying.\nWhenever Kain deals combat damage to a player, that player gains control of Kain. If they do, you draw that many cards, create that many tapped Treasure tokens, then lose that much life.",
)

MALBORO = make_creature(
    name="Malboro",
    power=4, toughness=4,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Plant"},
    text="Bad Breath — When this creature enters, each opponent discards a card, loses 2 life, and exiles the top three cards of their library.\nSwampcycling {2} ({2}, Discard this card: Search your library for a Swamp card, reveal it, put it into your hand, then shuffle.)",
)

NAMAZU_TRADER = make_creature(
    name="Namazu Trader",
    power=3, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Citizen", "Fish"},
    text="When this creature enters, you lose 1 life and create a Treasure token.\nWhenever this creature attacks, you may sacrifice another creature or artifact. If you do, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
)

NINJAS_BLADES = make_artifact(
    name="Ninja's Blades",
    mana_cost="{2}{B}",
    text="Job select\nEquipped creature gets +1/+1, is a Ninja in addition to its other types, and has \"Whenever this creature deals combat damage to a player, draw a card, then discard a card. That player loses life equal to the discarded card's mana value.\"\nMutsunokami — Equip {2}",
    subtypes={"Equipment"},
)

OVERKILL = make_instant(
    name="Overkill",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Target creature gets -0/-9999 until end of turn.",
)

PHANTOM_TRAIN = make_artifact(
    name="Phantom Train",
    mana_cost="{3}{B}",
    text="Trample\nSacrifice another artifact or creature: Put a +1/+1 counter on this Vehicle. It becomes a Spirit artifact creature in addition to its other types until end of turn.",
    subtypes={"Vehicle"},
)

POISON_THE_WATERS = make_sorcery(
    name="Poison the Waters",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Choose one —\n• All creatures get -1/-1 until end of turn.\n• Target player reveals their hand. You choose an artifact or creature card from it. That player discards that card.",
)

QUTRUB_FORAYER = make_creature(
    name="Qutrub Forayer",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Zombie"},
    text="When this creature enters, choose one —\n• Destroy target creature that was dealt damage this turn.\n• Exile up to two target cards from a single graveyard.",
)

RENO_AND_RUDE = make_creature(
    name="Reno and Rude",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Human"},
    supertypes={"Legendary"},
    text="Menace\nWhenever Reno and Rude deals combat damage to a player, exile the top card of that player's library. Then you may sacrifice another creature or artifact. If you do, you may play the exiled card this turn, and mana of any type can be spent to cast it.",
)

RESENTFUL_REVELATION = make_sorcery(
    name="Resentful Revelation",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Look at the top three cards of your library. Put one of them into your hand and the rest into your graveyard.\nFlashback {6}{B} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

SEPHIROTH_FABLED_SOLDIER = make_creature(
    name="Sephiroth, Fabled SOLDIER",
    power=3, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Avatar", "Human", "Soldier"},
    supertypes={"Legendary"},
    text="Whenever Sephiroth enters or attacks, you may sacrifice another creature. If you do, draw a card.\nWhenever another creature dies, target opponent loses 1 life and you gain 1 life. If this is the fourth time this ability has resolved this turn, transform Sephiroth.\n// Transforms into: Sephiroth, One-Winged Angel (5/5)\nFlying\nSuper Nova — As this creature transforms into Sephiroth, One-Winged Angel, you get an emblem with \"Whenever a creature dies, target opponent loses 1 life and you gain 1 life.\"\nWhenever Sephiroth attacks, you may sacrifice any number of other creatures. If you do, draw that many cards.",
)

SEPHIROTHS_INTERVENTION = make_instant(
    name="Sephiroth's Intervention",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. You gain 2 life.",
)

SHAMBLING_CIETH = make_creature(
    name="Shambling Cie'th",
    power=3, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Mutant"},
    text="This creature enters tapped.\nWhenever you cast a noncreature spell, you may pay {B}. If you do, return this card from your graveyard to your hand.",
)

SHINRA_REINFORCEMENTS = make_creature(
    name="Shinra Reinforcements",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    text="When this creature enters, mill three cards and you gain 3 life. (To mill three cards, put the top three cards of your library into your graveyard.)",
)

SIDEQUEST_HUNT_THE_MARK = make_enchantment(
    name="Sidequest: Hunt the Mark",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="When this enchantment enters, destroy up to one target creature.\nAt the beginning of your end step, if a creature died under an opponent's control this turn, create a Treasure token. Then if you control three or more Treasures, transform this enchantment.\n// Transforms into: Yiazmat, Ultimate Mark (5/6)\n{1}{B}, Sacrifice another creature or artifact: Yiazmat gains indestructible until end of turn. Tap it.",
)

SUMMON_ANIMA = make_enchantment_creature(
    name="Summon: Anima",
    power=4, toughness=4,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after IV.)\nI, II, III — Pain — You draw a card and you lose 1 life.\nIV — Oblivion — Each opponent sacrifices a creature of their choice and loses 3 life.\nMenace",
)

SUMMON_PRIMAL_ODIN = make_enchantment_creature(
    name="Summon: Primal Odin",
    power=5, toughness=3,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Knight", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Gungnir — Destroy target creature an opponent controls.\nII — Zantetsuken — This creature gains \"Whenever this creature deals combat damage to a player, that player loses the game.\"\nIII — Hall of Sorrow — Draw two cards. Each player loses 2 life.",
)

TONBERRY = make_creature(
    name="Tonberry",
    power=2, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Salamander"},
    text="This creature enters tapped with a stun counter on it. (If it would become untapped, remove a stun counter from it instead.)\nChef's Knife — During your turn, this creature has first strike and deathtouch.",
)

UNDERCITY_DIRE_RAT = make_creature(
    name="Undercity Dire Rat",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rat"},
    text="Rat Tail — When this creature dies, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

VAYNES_TREACHERY = make_instant(
    name="Vayne's Treachery",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Kicker—Sacrifice an artifact or creature. (You may sacrifice an artifact or creature in addition to any other costs as you cast this spell.)\nTarget creature gets -2/-2 until end of turn. If this spell was kicked, that creature gets -6/-6 until end of turn instead.",
)

VINCENT_VALENTINE = make_creature(
    name="Vincent Valentine",
    power=2, toughness=2,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin"},
    supertypes={"Legendary"},
    text="Whenever a creature an opponent controls dies, put a number of +1/+1 counters on Vincent Valentine equal to that creature's power.\nWhenever Vincent Valentine attacks, you may transform it.\n// Transforms into: Galian Beast (3/2)\nTrample, lifelink\nWhen Galian Beast dies, return it to the battlefield tapped (front face up).",
)

VINCENTS_LIMIT_BREAK = make_instant(
    name="Vincent's Limit Break",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Tiered (Choose one additional cost.)\nUntil end of turn, target creature you control gains \"When this creature dies, return it to the battlefield tapped under its owner's control\" and has the chosen base power and toughness.\n• Galian Beast — {0} — 3/2.\n• Death Gigas — {1} — 5/2.\n• Hellmasker — {3} — 7/2.",
)

ZENOS_YAE_GALVUS = make_creature(
    name="Zenos yae Galvus",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Noble", "Warrior"},
    supertypes={"Legendary"},
    text="My First Friend — When Zenos yae Galvus enters, choose a creature an opponent controls. Until end of turn, creatures other than Zenos yae Galvus and the chosen creature get -2/-2.\nWhen the chosen creature leaves the battlefield, transform Zenos yae Galvus.\n// Transforms into: Shinryu, Transcendent Rival (8/8)\nFlying\nAs this creature transforms into Shinryu, choose an opponent.\nBurning Chains — When the chosen player loses the game, you win the game.",
)

ZODIARK_UMBRAL_GOD = make_creature(
    name="Zodiark, Umbral God",
    power=5, toughness=5,
    mana_cost="{B}{B}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"God"},
    supertypes={"Legendary"},
    text="Indestructible\nWhen Zodiark enters, each player sacrifices half the non-God creatures they control of their choice, rounded down.\nWhenever a player sacrifices another creature, put a +1/+1 counter on Zodiark.",
)

BARRET_WALLACE = make_creature(
    name="Barret Wallace",
    power=4, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rebel"},
    supertypes={"Legendary"},
    text="Reach\nWhenever Barret Wallace attacks, it deals damage equal to the number of equipped creatures you control to defending player.",
)

BLAZING_BOMB = make_creature(
    name="Blazing Bomb",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Whenever you cast a noncreature spell, if at least four mana was spent to cast it, put a +1/+1 counter on this creature.\nBlow Up — {T}, Sacrifice this creature: It deals damage equal to its power to target creature. Activate only as a sorcery.",
)

CALL_THE_MOUNTAIN_CHOCOBO = make_sorcery(
    name="Call the Mountain Chocobo",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Search your library for a Mountain card, reveal it, put it into your hand, then shuffle. Create a 2/2 green Bird creature token with \"Whenever a land you control enters, this token gets +1/+0 until end of turn.\"\nFlashback {5}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

CHOCOCOMET = make_sorcery(
    name="Choco-Comet",
    mana_cost="{X}{R}{R}",
    colors={Color.RED},
    text="Choco-Comet deals X damage to any target.\nCreate a 2/2 green Bird creature token with \"Whenever a land you control enters, this token gets +1/+0 until end of turn.\"",
)

CLIVE_IFRITS_DOMINANT = make_creature(
    name="Clive, Ifrit's Dominant",
    power=5, toughness=5,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Noble", "Warrior"},
    supertypes={"Legendary"},
    text="When Clive enters, you may discard your hand, then draw cards equal to your devotion to red. (Each {R} in the mana costs of permanents you control counts toward your devotion to red.)\n{4}{R}{R}, {T}: Exile Clive, then return it to the battlefield transformed under its owner's control. Activate only as a sorcery.\n// Transforms into: Ifrit, Warden of Inferno (9/9)\n(As this Saga enters and after your draw step, add a lore counter.)\nI — Lunge — Ifrit fights up to one other target creature.\nII, III — Brimstone — Add {R}{R}{R}{R}. If Ifrit has three or more lore counters on it, exile it, then return it to the battlefield (front face up).",
)

CORAL_SWORD = make_artifact(
    name="Coral Sword",
    mana_cost="{R}",
    text="Flash\nWhen this Equipment enters, attach it to target creature you control. That creature gains first strike until end of turn.\nEquipped creature gets +1/+0.\nEquip {1}",
    subtypes={"Equipment"},
)

THE_FIRE_CRYSTAL = make_artifact(
    name="The Fire Crystal",
    mana_cost="{2}{R}{R}",
    text="Red spells you cast cost {1} less to cast.\nCreatures you control have haste.\n{4}{R}{R}, {T}: Create a token that's a copy of target creature you control. Sacrifice it at the beginning of the next end step.",
    supertypes={"Legendary"},
)

FIRE_MAGIC = make_instant(
    name="Fire Magic",
    mana_cost="{R}",
    colors={Color.RED},
    text="Tiered (Choose one additional cost.)\n• Fire — {0} — Fire Magic deals 1 damage to each creature.\n• Fira — {2} — Fire Magic deals 2 damage to each creature.\n• Firaga — {5} — Fire Magic deals 3 damage to each creature.",
)

FIRION_WILD_ROSE_WARRIOR = make_creature(
    name="Firion, Wild Rose Warrior",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rebel", "Warrior"},
    supertypes={"Legendary"},
    text="Equipped creatures you control have haste.\nWhenever a nontoken Equipment you control enters, create a token that's a copy of it, except it has \"This Equipment's equip abilities cost {2} less to activate.\" Sacrifice that token at the beginning of the next upkeep.",
)

FREYA_CRESCENT = make_creature(
    name="Freya Crescent",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Knight", "Rat"},
    supertypes={"Legendary"},
    text="Jump — During your turn, Freya Crescent has flying.\n{T}: Add {R}. Spend this mana only to cast an Equipment spell or activate an equip ability.",
)

GILGAMESH_MASTERATARMS = make_creature(
    name="Gilgamesh, Master-at-Arms",
    power=6, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Samurai"},
    supertypes={"Legendary"},
    text="Whenever Gilgamesh enters or attacks, look at the top six cards of your library. You may put any number of Equipment cards from among them onto the battlefield. Put the rest on the bottom of your library in a random order. When you put one or more Equipment onto the battlefield this way, you may attach one of them to a Samurai you control.",
)

HASTE_MAGIC = make_instant(
    name="Haste Magic",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+1 and gains haste until end of turn. Exile the top card of your library. You may play it until your next end step.",
)

HILL_GIGAS = make_creature(
    name="Hill Gigas",
    power=5, toughness=4,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Giant"},
    text="Trample, haste\nMountaincycling {2} ({2}, Discard this card: Search your library for a Mountain card, reveal it, put it into your hand, then shuffle.)",
)

ITEM_SHOPKEEP = make_creature(
    name="Item Shopkeep",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Citizen", "Human"},
    text="Whenever you attack, target attacking equipped creature gains menace until end of turn. (It can't be blocked except by two or more creatures.)",
)

LAUGHING_MAD = make_instant(
    name="Laughing Mad",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="As an additional cost to cast this spell, discard a card.\nDraw two cards.\nFlashback {3}{R} (You may cast this card from your graveyard for its flashback cost and any additional costs. Then exile it.)",
)

LIGHT_OF_JUDGMENT = make_instant(
    name="Light of Judgment",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="Light of Judgment deals 6 damage to target creature. Destroy up to one Equipment attached to that creature.",
)

MYSIDIAN_ELDER = make_creature(
    name="Mysidian Elder",
    power=1, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard"},
    text="When this creature enters, create a 0/1 black Wizard creature token with \"Whenever you cast a noncreature spell, this token deals 1 damage to each opponent.\"",
)

NIBELHEIM_AFLAME = make_sorcery(
    name="Nibelheim Aflame",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Choose target creature you control. It deals damage equal to its power to each other creature. If this spell was cast from a graveyard, discard your hand and draw four cards.\nFlashback {5}{R}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

OPERA_LOVE_SONG = make_instant(
    name="Opera Love Song",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Choose one —\n• Exile the top two cards of your library. You may play those cards until your next end step.\n• One or two target creatures each get +2/+0 until end of turn.",
)

PROMPTO_ARGENTUM = make_creature(
    name="Prompto Argentum",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Scout"},
    supertypes={"Legendary"},
    text="Haste\nSelfie Shot — Whenever you cast a noncreature spell, if at least four mana was spent to cast it, create a Treasure token.",
)

QUEEN_BRAHNE = make_creature(
    name="Queen Brahne",
    power=2, toughness=1,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nWhenever Queen Brahne attacks, create a 0/1 black Wizard creature token with \"Whenever you cast a noncreature spell, this token deals 1 damage to each opponent.\"",
)

RANDOM_ENCOUNTER = make_sorcery(
    name="Random Encounter",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Shuffle your library, then mill four cards. Put each creature card milled this way onto the battlefield. They gain haste. At the beginning of the next end step, return those creatures to their owner's hand.\nFlashback {6}{R}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

RAUBAHN_BULL_OF_ALA_MHIGO = make_creature(
    name="Raubahn, Bull of Ala Mhigo",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Ward—Pay life equal to Raubahn's power.\nWhenever Raubahn attacks, attach up to one target Equipment you control to target attacking creature.",
)

RED_MAGES_RAPIER = make_artifact(
    name="Red Mage's Rapier",
    mana_cost="{1}{R}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature has \"Whenever you cast a noncreature spell, this creature gets +2/+0 until end of turn\" and is a Wizard in addition to its other types.\nEquip {3}",
    subtypes={"Equipment"},
)

SABOTENDER = make_creature(
    name="Sabotender",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Plant"},
    text="Reach\nLandfall — Whenever a land you control enters, this creature deals 1 damage to each opponent.",
)

SAMURAIS_KATANA = make_artifact(
    name="Samurai's Katana",
    mana_cost="{2}{R}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +2/+2, has trample and haste, and is a Samurai in addition to its other types.\nMurasame — Equip {5}",
    subtypes={"Equipment"},
)

SANDWORM = make_creature(
    name="Sandworm",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Worm"},
    text="Haste\nWhen this creature enters, destroy target land. Its controller may search their library for a basic land card, put it onto the battlefield tapped, then shuffle.",
)

SEIFER_ALMASY = make_creature(
    name="Seifer Almasy",
    power=3, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="Whenever a creature you control attacks alone, it gains double strike until end of turn.\nFire Cross — Whenever Seifer Almasy deals combat damage to a player, you may cast target instant or sorcery card with mana value 3 or less from your graveyard without paying its mana cost. If that spell would be put into your graveyard, exile it instead.",
)

SELFDESTRUCT = make_instant(
    name="Self-Destruct",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature you control deals X damage to any other target and X damage to itself, where X is its power.",
)

SIDEQUEST_PLAY_BLITZBALL = make_enchantment(
    name="Sidequest: Play Blitzball",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="At the beginning of combat on your turn, target creature you control gets +2/+0 until end of turn.\nAt the end of combat on your turn, if a player was dealt 6 or more combat damage this turn, transform this enchantment, then attach it to a creature you control.\n// Transforms into: World Champion, Celestial Weapon\nDouble Overdrive — Equipped creature gets +2/+0 and has double strike.\nEquip {3} ({3}: Attach to target creature you control. Equip only as a sorcery.)",
)

SORCERESSS_SCHEMES = make_sorcery(
    name="Sorceress's Schemes",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Return target instant or sorcery card from your graveyard or exiled card with flashback you own to your hand. Add {R}.\nFlashback {4}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

SUMMON_BRYNHILDR = make_enchantment_creature(
    name="Summon: Brynhildr",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Knight", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Chain — Exile the top card of your library. During any turn you put a lore counter on this Saga, you may play that card.\nII, III — Gestalt Mode — When you next cast a creature spell this turn, it gains haste until end of turn.",
)

SUMMON_ESPER_RAMUH = make_enchantment_creature(
    name="Summon: Esper Ramuh",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Saga", "Wizard"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Judgment Bolt — This creature deals damage equal to the number of noncreature, nonland cards in your graveyard to target creature an opponent controls.\nII, III — Wizards you control get +1/+0 until end of turn.",
)

SUMMON_GF_CERBERUS = make_enchantment_creature(
    name="Summon: G.F. Cerberus",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Dog", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\nII — Double — When you next cast an instant or sorcery spell this turn, copy it. You may choose new targets for the copy.\nIII — Triple — When you next cast an instant or sorcery spell this turn, copy it twice. You may choose new targets for the copies.",
)

SUMMON_GF_IFRIT = make_enchantment_creature(
    name="Summon: G.F. Ifrit",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Demon", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after IV.)\nI, II — You may discard a card. If you do, draw a card.\nIII, IV — Add {R}.",
)

SUPLEX = make_sorcery(
    name="Suplex",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Choose one —\n• Suplex deals 3 damage to target creature. If that creature would die this turn, exile it instead.\n• Exile target artifact.",
)

THUNDER_MAGIC = make_instant(
    name="Thunder Magic",
    mana_cost="{R}",
    colors={Color.RED},
    text="Tiered (Choose one additional cost.)\n• Thunder — {0} — Thunder Magic deals 2 damage to target creature.\n• Thundara — {3} — Thunder Magic deals 4 damage to target creature.\n• Thundaga — {5}{R} — Thunder Magic deals 8 damage to target creature.",
)

TRIPLE_TRIAD = make_enchantment(
    name="Triple Triad",
    mana_cost="{3}{R}{R}{R}",
    colors={Color.RED},
    text="At the beginning of your upkeep, each player exiles the top card of their library. Until end of turn, you may play the card you own exiled this way and each other card exiled this way with lesser mana value than it without paying their mana costs.",
)

UNEXPECTED_REQUEST = make_sorcery(
    name="Unexpected Request",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. You may attach an Equipment you control to that creature. If you do, unattach it at the beginning of the next end step.",
)

VAAN_STREET_THIEF = make_creature(
    name="Vaan, Street Thief",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Scout"},
    supertypes={"Legendary"},
    text="Whenever one or more Scouts, Pirates, and/or Rogues you control deal combat damage to a player, exile the top card of that player's library. You may cast it. If you don't, create a Treasure token.\nWhenever you cast a spell you don't own, put a +1/+1 counter on each Scout, Pirate, and Rogue you control.",
)

WARRIORS_SWORD = make_artifact(
    name="Warrior's Sword",
    mana_cost="{3}{R}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +3/+2 and is a Warrior in addition to its other types.\nEquip {5} ({5}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

ZELL_DINCHT = make_creature(
    name="Zell Dincht",
    power=0, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Monk"},
    supertypes={"Legendary"},
    text="You may play an additional land on each of your turns.\nZell Dincht gets +1/+0 for each land you control.\nAt the beginning of your end step, return a land you control to its owner's hand.",
)

AIRSHIP_CRASH = make_instant(
    name="Airship Crash",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Destroy target artifact, enchantment, or creature with flying.\nCycling {2} ({2}, Discard this card: Draw a card.)",
)

ANCIENT_ADAMANTOISE = make_creature(
    name="Ancient Adamantoise",
    power=8, toughness=20,
    mana_cost="{5}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Turtle"},
    text="Vigilance, ward {3}\nDamage isn't removed from this creature during cleanup steps.\nAll damage that would be dealt to you and other permanents you control is dealt to this creature instead.\nWhen this creature dies, exile it and create ten tapped Treasure tokens.",
)

BALAMB_TREXAUR = make_creature(
    name="Balamb T-Rexaur",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Trample\nWhen this creature enters, you gain 3 life.\nForestcycling {2} ({2}, Discard this card: Search your library for a Forest card, reveal it, put it into your hand, then shuffle.)",
)

BARDS_BOW = make_artifact(
    name="Bard's Bow",
    mana_cost="{2}{G}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +2/+2, has reach, and is a Bard in addition to its other types.\nPerseus's Bow — Equip {6} ({6}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

BARTZ_AND_BOKO = make_creature(
    name="Bartz and Boko",
    power=4, toughness=3,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Bird", "Human"},
    supertypes={"Legendary"},
    text="Affinity for Birds (This spell costs {1} less to cast for each Bird you control.)\nWhen Bartz and Boko enters, each other Bird you control deals damage equal to its power to target creature an opponent controls.",
)

BLITZBALL_SHOT = make_instant(
    name="Blitzball Shot",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 and gains trample until end of turn.",
)

CACTUAR = make_creature(
    name="Cactuar",
    power=3, toughness=3,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="Trample\nAt the beginning of your end step, if this creature didn't enter the battlefield this turn, return it to its owner's hand.",
)

CHOCOBO_KICK = make_sorcery(
    name="Chocobo Kick",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Kicker—Return a land you control to its owner's hand. (You may return a land you control to its owner's hand in addition to any other costs as you cast this spell.)\nTarget creature you control deals damage equal to its power to target creature an opponent controls. If this spell was kicked, the creature you control deals twice that much damage instead.",
)

CHOCOBO_RACETRACK = make_artifact(
    name="Chocobo Racetrack",
    mana_cost="{3}{G}{G}",
    text="Landfall — Whenever a land you control enters, create a 2/2 green Bird creature token with \"Whenever a land you control enters, this token gets +1/+0 until end of turn.\"",
)

CLASH_OF_THE_EIKONS = make_sorcery(
    name="Clash of the Eikons",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Choose one or more —\n• Target creature you control fights target creature an opponent controls.\n• Remove a lore counter from target Saga you control. (Removing lore counters doesn't cause chapter abilities to trigger.)\n• Put a lore counter on target Saga you control.",
)

COLISEUM_BEHEMOTH = make_creature(
    name="Coliseum Behemoth",
    power=7, toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample\nWhen this creature enters, choose one —\n• Destroy target artifact or enchantment.\n• Draw a card.",
)

COMMUNE_WITH_BEAVERS = make_sorcery(
    name="Commune with Beavers",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Look at the top three cards of your library. You may reveal an artifact, creature, or land card from among them and put it into your hand. Put the rest on the bottom of your library in any order.",
)

DIAMOND_WEAPON = make_artifact_creature(
    name="Diamond Weapon",
    power=8, toughness=8,
    mana_cost="{7}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental"},
    supertypes={"Legendary"},
    text="This spell costs {1} less to cast for each permanent card in your graveyard.\nReach\nImmune — Prevent all combat damage that would be dealt to Diamond Weapon.",
)

THE_EARTH_CRYSTAL = make_artifact(
    name="The Earth Crystal",
    mana_cost="{2}{G}{G}",
    text="Green spells you cast cost {1} less to cast.\nIf one or more +1/+1 counters would be put on a creature you control, twice that many +1/+1 counters are put on that creature instead.\n{4}{G}{G}, {T}: Distribute two +1/+1 counters among one or two target creatures you control.",
    supertypes={"Legendary"},
)

ESPER_ORIGINS = make_sorcery(
    name="Esper Origins",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Surveil 2. You gain 2 life. If this spell was cast from a graveyard, exile it, then put it onto the battlefield transformed under its owner's control with a finality counter on it. (If a creature with a finality counter on it would die, exile it instead.)\nFlashback {3}{G} (You may cast this card from your graveyard for its flashback cost. Then exile it.)\n// Transforms into: Summon: Esper Maduin (4/4)\n(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Reveal the top card of your library. If it's a permanent card, put it into your hand.\nII — Add {G}{G}.\nIII — Other creatures you control get +2/+2 and gain trample until end of turn.",
)

GALUFS_FINAL_ACT = make_instant(
    name="Galuf's Final Act",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Until end of turn, target creature gets +1/+0 and gains \"When this creature dies, put a number of +1/+1 counters equal to its power on up to one target creature.\"",
)

GIGANTOAD = make_creature(
    name="Gigantoad",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Frog"},
    text="As long as you control seven or more lands, this creature gets +2/+2.",
)

GOOBBUE_GARDENER = make_creature(
    name="Goobbue Gardener",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Plant"},
    text="{T}: Add {G}.",
)

GRAN_PULSE_OCHU = make_creature(
    name="Gran Pulse Ochu",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Plant"},
    text="Deathtouch\n{8}: Until end of turn, this creature gets +1/+1 for each permanent card in your graveyard.",
)

GYSAHL_GREENS = make_sorcery(
    name="Gysahl Greens",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Create a 2/2 green Bird creature token with \"Whenever a land you control enters, this token gets +1/+0 until end of turn.\"\nFlashback {6}{G} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

JUMBO_CACTUAR = make_creature(
    name="Jumbo Cactuar",
    power=1, toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="10,000 Needles — Whenever this creature attacks, it gets +9999/+0 until end of turn.",
)

LOPORRIT_SCOUT = make_creature(
    name="Loporrit Scout",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Rabbit", "Scout"},
    text="Whenever another creature you control enters, this creature gets +1/+1 until end of turn.",
)

PRISHES_WANDERINGS = make_instant(
    name="Prishe's Wanderings",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card or Town card, put it onto the battlefield tapped, then shuffle. When you search your library this way, put a +1/+1 counter on target creature you control.",
)

QUINA_QU_GOURMET = make_creature(
    name="Quina, Qu Gourmet",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Qu"},
    supertypes={"Legendary"},
    text="If one or more tokens would be created under your control, those tokens plus a 1/1 green Frog creature token are created instead.\n{2}, Sacrifice a Frog: Put a +1/+1 counter on Quina.",
)

REACH_THE_HORIZON = make_sorcery(
    name="Reach the Horizon",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Search your library for up to two basic land cards and/or Town cards with different names, put them onto the battlefield tapped, then shuffle.",
)

A_REALM_REBORN = make_enchantment(
    name="A Realm Reborn",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Other permanents you control have \"{T}: Add one mana of any color.\"",
)

RIDE_THE_SHOOPUF = make_enchantment(
    name="Ride the Shoopuf",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Landfall — Whenever a land you control enters, put a +1/+1 counter on target creature you control.\n{5}{G}{G}: This enchantment becomes a 7/7 Beast creature in addition to its other types.",
)

RYDIAS_RETURN = make_sorcery(
    name="Rydia's Return",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Creatures you control get +3/+3 until end of turn.\n• Return up to two target permanent cards from your graveyard to your hand.",
)

SAZH_KATZROY = make_creature(
    name="Sazh Katzroy",
    power=3, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Pilot"},
    supertypes={"Legendary"},
    text="When Sazh Katzroy enters, you may search your library for a Bird or basic land card, reveal it, put it into your hand, then shuffle.\nWhenever Sazh Katzroy attacks, put a +1/+1 counter on target creature, then double the number of +1/+1 counters on that creature.",
)

SAZHS_CHOCOBO = make_creature(
    name="Sazh's Chocobo",
    power=0, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Bird"},
    text="Landfall — Whenever a land you control enters, put a +1/+1 counter on this creature.",
)

SIDEQUEST_RAISE_A_CHOCOBO = make_enchantment(
    name="Sidequest: Raise a Chocobo",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, create a 2/2 green Bird creature token with \"Whenever a land you control enters, this token gets +1/+0 until end of turn.\"\nAt the beginning of your first main phase, if you control four or more Birds, transform this enchantment.\n// Transforms into: Black Chocobo (2/2)\nWhen this permanent transforms into Black Chocobo, search your library for a land card, put it onto the battlefield tapped, then shuffle.\nLandfall — Whenever a land you control enters, Birds you control get +1/+0 until end of turn.",
)

SUMMON_FAT_CHOCOBO = make_enchantment_creature(
    name="Summon: Fat Chocobo",
    power=4, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Bird", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after IV.)\nI — Wark — Create a 2/2 green Bird creature token with \"Whenever a land you control enters, this token gets +1/+0 until end of turn.\"\nII, III, IV — Kerplunk — Creatures you control gain trample until end of turn.",
)

SUMMON_FENRIR = make_enchantment_creature(
    name="Summon: Fenrir",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Saga", "Wolf"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Crescent Fang — Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\nII — Heavenward Howl — When you next cast a creature spell this turn, that creature enters with an additional +1/+1 counter on it.\nIII — Ecliptic Growl — Draw a card if you control the creature with the greatest power or tied for the greatest power.",
)

SUMMON_TITAN = make_enchantment_creature(
    name="Summon: Titan",
    power=7, toughness=7,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Giant", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Mill five cards.\nII — Return all land cards from your graveyard to the battlefield tapped.\nIII — Until end of turn, another target creature you control gains trample and gets +X/+X, where X is the number of lands you control.\nReach, trample",
)

SUMMONERS_GRIMOIRE = make_artifact(
    name="Summoner's Grimoire",
    mana_cost="{3}{G}",
    text="Job select\nEquipped creature is a Shaman in addition to its other types and has \"Whenever this creature attacks, you may put a creature card from your hand onto the battlefield. If that card is an enchantment card, it enters tapped and attacking.\"\nAbraxas — Equip {3}",
    subtypes={"Equipment"},
)

TIFA_LOCKHART = make_creature(
    name="Tifa Lockhart",
    power=1, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Monk"},
    supertypes={"Legendary"},
    text="Trample\nLandfall — Whenever a land you control enters, double Tifa Lockhart's power until end of turn.",
)

TIFAS_LIMIT_BREAK = make_instant(
    name="Tifa's Limit Break",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Tiered (Choose one additional cost.)\n• Somersault — {0} — Target creature gets +2/+2 until end of turn.\n• Meteor Strikes — {2} — Double target creature's power and toughness until end of turn.\n• Final Heaven — {6}{G} — Triple target creature's power and toughness until end of turn.",
)

TORGAL_A_FINE_HOUND = make_creature(
    name="Torgal, A Fine Hound",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Wolf"},
    supertypes={"Legendary"},
    text="Whenever you cast your first Human creature spell each turn, that creature enters with an additional +1/+1 counter on it for each Dog and/or Wolf you control.\n{T}: Add one mana of any color.",
)

TOWN_GREETER = make_creature(
    name="Town Greeter",
    power=1, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Citizen", "Human"},
    text="When this creature enters, mill four cards. You may put a land card from among them into your hand. If you put a Town card into your hand this way, you gain 2 life. (To mill four cards, a player puts the top four cards of their library into their graveyard.)",
)

TRAVELING_CHOCOBO = make_creature(
    name="Traveling Chocobo",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Bird"},
    text="You may look at the top card of your library any time.\nYou may play lands and cast Bird spells from the top of your library.\nIf a land or Bird you control entering the battlefield causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.",
)

VANILLE_CHEERFUL_LCIE = make_creature(
    name="Vanille, Cheerful l'Cie",
    power=3, toughness=2,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Cleric", "Human"},
    supertypes={"Legendary"},
    text="When Vanille enters, mill two cards, then return a permanent card from your graveyard to your hand.\nAt the beginning of your first main phase, if you both own and control Vanille and a creature named Fang, Fearless l'Cie, you may pay {3}{B}{G}. If you do, exile them, then meld them into Ragnarok, Divine Deliverance.",
)

ABSOLUTE_VIRTUE = make_creature(
    name="Absolute Virtue",
    power=8, toughness=8,
    mana_cost="{6}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Avatar", "Warrior"},
    supertypes={"Legendary"},
    text="This spell can't be countered.\nFlying\nYou have protection from each of your opponents. (You can't be dealt damage, enchanted, or targeted by anything controlled by your opponents.)",
)

BALTHIER_AND_FRAN = make_creature(
    name="Balthier and Fran",
    power=4, toughness=3,
    mana_cost="{1}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Rabbit"},
    supertypes={"Legendary"},
    text="Reach\nVehicles you control get +1/+1 and have vigilance and reach.\nWhenever a Vehicle crewed by Balthier and Fran this turn attacks, if it's the first combat phase of the turn, you may pay {1}{R}{G}. If you do, after this phase, there is an additional combat phase.",
)

BLACK_WALTZ_NO_3 = make_creature(
    name="Black Waltz No. 3",
    power=2, toughness=2,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Wizard"},
    supertypes={"Legendary"},
    text="Flying, deathtouch\nWhenever you cast a noncreature spell, Black Waltz No. 3 deals 2 damage to each opponent.",
)

CHOCO_SEEKER_OF_PARADISE = make_creature(
    name="Choco, Seeker of Paradise",
    power=3, toughness=5,
    mana_cost="{1}{G}{W}{U}",
    colors={Color.GREEN, Color.BLUE, Color.WHITE},
    subtypes={"Bird"},
    supertypes={"Legendary"},
    text="Whenever one or more Birds you control attack, look at that many cards from the top of your library. You may put one of them into your hand. Then put any number of land cards from among them onto the battlefield tapped and the rest into your graveyard.\nLandfall — Whenever a land you control enters, Choco gets +1/+0 until end of turn.",
)

CID_TIMELESS_ARTIFICER = make_creature(
    name="Cid, Timeless Artificer",
    power=4, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Artificer", "Human"},
    supertypes={"Legendary"},
    text="Artifact creatures and Heroes you control get +1/+1 for each Artificer you control and each Artificer card in your graveyard.\nA deck can have any number of cards named Cid, Timeless Artificer.\nCycling {W}{U} ({W}{U}, Discard this card: Draw a card.)",
)

CLOUD_OF_DARKNESS = make_creature(
    name="Cloud of Darkness",
    power=3, toughness=3,
    mana_cost="{2}{B}{G}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Avatar"},
    supertypes={"Legendary"},
    text="Flying\nParticle Beam — When Cloud of Darkness enters, target creature an opponent controls gets -X/-X until end of turn, where X is the number of permanent cards in your graveyard.",
)

EMETSELCH_UNSUNDERED = make_creature(
    name="Emet-Selch, Unsundered",
    power=2, toughness=4,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Elder", "Wizard"},
    supertypes={"Legendary"},
    text="Vigilance\nWhenever Emet-Selch enters or attacks, draw a card, then discard a card.\nAt the beginning of your upkeep, if there are fourteen or more cards in your graveyard, you may transform Emet-Selch.\n// Transforms into: Hades, Sorcerer of Eld (6/6)\nVigilance\nEcho of the Lost — During your turn, you may play cards from your graveyard.\nIf a card or token would be put into your graveyard from anywhere, exile it instead.",
)

THE_EMPEROR_OF_PALAMECIA = make_creature(
    name="The Emperor of Palamecia",
    power=2, toughness=2,
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Human", "Noble", "Wizard"},
    supertypes={"Legendary"},
    text="{T}: Add {U} or {R}. Spend this mana only to cast a noncreature spell.\nWhenever you cast a noncreature spell, if at least four mana was spent to cast it, put a +1/+1 counter on The Emperor of Palamecia. Then if it has three or more +1/+1 counters on it, transform it.\n// Transforms into: The Lord Master of Hell (3/3)\nStarfall — Whenever The Lord Master of Hell attacks, it deals X damage to each opponent, where X is the number of noncreature, nonland cards in your graveyard.",
)

EXDEATH_VOID_WARLOCK = make_creature(
    name="Exdeath, Void Warlock",
    power=3, toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Spirit", "Warlock"},
    supertypes={"Legendary"},
    text="When Exdeath enters, you gain 3 life.\nAt the beginning of your end step, if there are six or more permanent cards in your graveyard, transform Exdeath.\n// Transforms into: Neo Exdeath, Dimension's End (*/3)\nTrample\nNeo Exdeath's power is equal to the number of permanent cards in your graveyard.",
)

GARLAND_KNIGHT_OF_CORNELIA = make_creature(
    name="Garland, Knight of Cornelia",
    power=3, toughness=2,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="Whenever you cast a noncreature spell, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\n{3}{B}{B}{R}{R}: Return this card from your graveyard to the battlefield transformed. Activate only as a sorcery.\n// Transforms into: Chaos, the Endless (5/5)\nFlying\nWhen Chaos dies, put it on the bottom of its owner's library.",
)

GARNET_PRINCESS_OF_ALEXANDRIA = make_creature(
    name="Garnet, Princess of Alexandria",
    power=2, toughness=2,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Cleric", "Human", "Noble"},
    supertypes={"Legendary"},
    text="Lifelink\nWhenever Garnet attacks, you may remove a lore counter from each of any number of Sagas you control. Put a +1/+1 counter on Garnet for each lore counter removed this way.",
)

GIOTT_KING_OF_THE_DWARVES = make_creature(
    name="Giott, King of the Dwarves",
    power=1, toughness=1,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Dwarf", "Noble"},
    supertypes={"Legendary"},
    text="Double strike\nWhenever Giott or another Dwarf you control enters and whenever an Equipment you control enters, you may discard a card. If you do, draw a card.",
)

GLADIOLUS_AMICITIA = make_creature(
    name="Gladiolus Amicitia",
    power=6, toughness=6,
    mana_cost="{4}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="When Gladiolus Amicitia enters, search your library for a land card, put it onto the battlefield tapped, then shuffle.\nLandfall — Whenever a land you control enters, another target creature you control gets +2/+2 and gains trample until end of turn.",
)

GOLBEZ_CRYSTAL_COLLECTOR = make_creature(
    name="Golbez, Crystal Collector",
    power=1, toughness=4,
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever an artifact you control enters, surveil 1.\nAt the beginning of your end step, if you control four or more artifacts, return target creature card from your graveyard to your hand. Then if you control eight or more artifacts, each opponent loses life equal to that card's power.",
)

HOPE_ESTHEIM = make_creature(
    name="Hope Estheim",
    power=2, toughness=2,
    mana_cost="{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Lifelink\nAt the beginning of your end step, each opponent mills X cards, where X is the amount of life you gained this turn.",
)

IGNIS_SCIENTIA = make_creature(
    name="Ignis Scientia",
    power=2, toughness=2,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Advisor", "Human"},
    supertypes={"Legendary"},
    text="When Ignis Scientia enters, look at the top six cards of your library. You may put a land card from among them onto the battlefield tapped. Put the rest on the bottom of your library in a random order.\nI've Come Up with a New Recipe! — {1}{G}{U}, {T}: Exile target card from a graveyard. If a creature card was exiled this way, create a Food token.",
)

JENOVA_ANCIENT_CALAMITY = make_creature(
    name="Jenova, Ancient Calamity",
    power=1, toughness=5,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Alien"},
    supertypes={"Legendary"},
    text="At the beginning of combat on your turn, put a number of +1/+1 counters equal to Jenova's power on up to one other target creature. That creature becomes a Mutant in addition to its other types.\nWhenever a Mutant you control dies during your turn, you draw cards equal to its power.",
)

JOSHUA_PHOENIXS_DOMINANT = make_creature(
    name="Joshua, Phoenix's Dominant",
    power=3, toughness=4,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Noble", "Wizard"},
    supertypes={"Legendary"},
    text="When Joshua enters, discard up to two cards, then draw that many cards.\n{3}{R}{W}, {T}: Exile Joshua, then return it to the battlefield transformed under its owner's control. Activate only as a sorcery.\n// Transforms into: Phoenix, Warden of Fire (4/4)\n(As this Saga enters and after your draw step, add a lore counter.)\nI, II — Rising Flames — Phoenix deals 2 damage to each opponent.\nIII — Flames of Rebirth — Return any number of target creature cards with total mana value 6 or less from your graveyard to the battlefield. Exile Phoenix, then return it to the battlefield (front face up).\nFlying, lifelink",
)

JUDGE_MAGISTER_GABRANTH = make_creature(
    name="Judge Magister Gabranth",
    power=2, toughness=2,
    mana_cost="{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Advisor", "Human", "Knight"},
    supertypes={"Legendary"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhenever another creature or artifact you control dies, put a +1/+1 counter on Judge Magister Gabranth.",
)

KEFKA_COURT_MAGE = make_creature(
    name="Kefka, Court Mage",
    power=4, toughness=5,
    mana_cost="{2}{U}{B}{R}",
    colors={Color.BLACK, Color.RED, Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever Kefka enters or attacks, each player discards a card. Then you draw a card for each card type among cards discarded this way.\n{8}: Each opponent sacrifices a permanent of their choice. Transform Kefka. Activate only as a sorcery.\n// Transforms into: Kefka, Ruler of Ruin (5/7)\nFlying\nWhenever an opponent loses life during your turn, you draw that many cards.",
)

KUJA_GENOME_SORCERER = make_creature(
    name="Kuja, Genome Sorcerer",
    power=3, toughness=4,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Mutant", "Wizard"},
    supertypes={"Legendary"},
    text="At the beginning of your end step, create a tapped 0/1 black Wizard creature token with \"Whenever you cast a noncreature spell, this token deals 1 damage to each opponent.\" Then if you control four or more Wizards, transform Kuja.\n// Transforms into: Trance Kuja, Fate Defied (4/6)\nFlare Star — If a Wizard you control would deal damage to a permanent or player, it deals double that damage instead.",
)

LIGHTNING_ARMY_OF_ONE = make_creature(
    name="Lightning, Army of One",
    power=3, toughness=2,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="First strike, trample, lifelink\nStagger — Whenever Lightning deals combat damage to a player, until your next turn, if a source would deal damage to that player or a permanent that player controls, it deals double that damage instead.",
)

LOCKE_COLE = make_creature(
    name="Locke Cole",
    power=2, toughness=3,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="Deathtouch, lifelink\nWhenever Locke Cole deals combat damage to a player, draw a card, then discard a card.",
)

NOCTIS_PRINCE_OF_LUCIS = make_creature(
    name="Noctis, Prince of Lucis",
    power=4, toughness=3,
    mana_cost="{1}{W}{U}{B}",
    colors={Color.BLACK, Color.BLUE, Color.WHITE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Lifelink\nYou may cast artifact spells from your graveyard by paying 3 life in addition to paying their other costs. If you cast a spell this way, that artifact enters with a finality counter on it.",
)

OMEGA_HEARTLESS_EVOLUTION = make_artifact_creature(
    name="Omega, Heartless Evolution",
    power=8, toughness=8,
    mana_cost="{5}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Robot"},
    supertypes={"Legendary"},
    text="Wave Cannon — When Omega enters, for each opponent, tap up to one target nonland permanent that opponent controls. Put X stun counters on each of those permanents and you gain X life, where X is the number of nonbasic lands you control. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

RINOA_HEARTILLY = make_creature(
    name="Rinoa Heartilly",
    power=4, toughness=4,
    mana_cost="{3}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Rebel", "Warlock"},
    supertypes={"Legendary"},
    text="When Rinoa Heartilly enters, create Angelo, a legendary 1/1 green and white Dog creature token.\nAngelo Cannon — Whenever Rinoa Heartilly attacks, another target creature you control gets +1/+1 until end of turn for each creature you control.",
)

RUFUS_SHINRA = make_creature(
    name="Rufus Shinra",
    power=2, toughness=4,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Whenever Rufus Shinra attacks, if you don't control a creature named Darkstar, create Darkstar, a legendary 2/2 white and black Dog creature token.",
)

RYDIA_SUMMONER_OF_MIST = make_creature(
    name="Rydia, Summoner of Mist",
    power=1, toughness=2,
    mana_cost="{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Shaman"},
    supertypes={"Legendary"},
    text="Landfall — Whenever a land you control enters, you may discard a card. If you do, draw a card.\nSummon — {X}, {T}: Return target Saga card with mana value X from your graveyard to the battlefield with a finality counter on it. It gains haste until end of turn. Activate only as a sorcery.",
)

SERAH_FARRON = make_creature(
    name="Serah Farron",
    power=2, toughness=2,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Citizen", "Human"},
    supertypes={"Legendary"},
    text="The first legendary creature spell you cast each turn costs {2} less to cast.\nAt the beginning of combat on your turn, if you control two or more other legendary creatures, you may transform Serah Farron.\n// Transforms into: Crystallized Serah\nThe first legendary creature spell you cast each turn costs {2} less to cast.\nLegendary creatures you control get +2/+2.",
)

SHANTOTTO_TACTICIAN_MAGICIAN = make_creature(
    name="Shantotto, Tactician Magician",
    power=0, toughness=4,
    mana_cost="{1}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Dwarf", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast a noncreature spell, Shantotto gets +X/+0 until end of turn, where X is the amount of mana spent to cast that spell. If X is 4 or more, draw a card.",
)

SIN_SPIRAS_PUNISHMENT = make_creature(
    name="Sin, Spira's Punishment",
    power=7, toughness=7,
    mana_cost="{4}{B}{G}{U}",
    colors={Color.BLACK, Color.GREEN, Color.BLUE},
    subtypes={"Avatar", "Leviathan"},
    supertypes={"Legendary"},
    text="Flying\nWhenever Sin enters or attacks, exile a permanent card from your graveyard at random, then create a tapped token that's a copy of that card. If the exiled card is a land card, repeat this process.",
)

SQUALL_SEED_MERCENARY = make_creature(
    name="Squall, SeeD Mercenary",
    power=3, toughness=4,
    mana_cost="{2}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Knight", "Mercenary"},
    supertypes={"Legendary"},
    text="Rough Divide — Whenever a creature you control attacks alone, it gains double strike until end of turn.\nWhenever Squall deals combat damage to a player, return target permanent card with mana value 3 or less from your graveyard to the battlefield.",
)

TELLAH_GREAT_SAGE = make_creature(
    name="Tellah, Great Sage",
    power=3, toughness=3,
    mana_cost="{3}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast a noncreature spell, create a 1/1 colorless Hero creature token. If four or more mana was spent to cast that spell, draw two cards. If eight or more mana was spent to cast that spell, sacrifice Tellah and it deals that much damage to each opponent.",
)

TERRA_MAGICAL_ADEPT = make_creature(
    name="Terra, Magical Adept",
    power=4, toughness=2,
    mana_cost="{1}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Warrior", "Wizard"},
    supertypes={"Legendary"},
    text="When Terra enters, mill five cards. Put up to one enchantment card milled this way into your hand.\nTrance — {4}{R}{G}, {T}: Exile Terra, then return it to the battlefield transformed under its owner's control. Activate only as a sorcery.\n// Transforms into: Esper Terra (6/6)\n(As this Saga enters and after your draw step, add a lore counter.)\nI, II, III — Create a token that's a copy of target nonlegendary enchantment you control. It gains haste. If it's a Saga, put up to three lore counters on it. Sacrifice it at the beginning of your next end step.\nIV — Add {W}{W}, {U}{U}, {B}{B}, {R}{R}, and {G}{G}. Exile Esper Terra, then return it to the battlefield (front face up).\nFlying",
)

TIDUS_BLITZBALL_STAR = make_creature(
    name="Tidus, Blitzball Star",
    power=2, toughness=1,
    mana_cost="{1}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Whenever an artifact you control enters, put a +1/+1 counter on Tidus.\nWhenever Tidus attacks, tap target creature an opponent controls.",
)

ULTIMECIA_TIME_SORCERESS = make_creature(
    name="Ultimecia, Time Sorceress",
    power=4, toughness=5,
    mana_cost="{3}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Whenever Ultimecia enters or attacks, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\nAt the beginning of your end step, you may pay {4}{U}{U}{B}{B} and exile eight cards from your graveyard. If you do, transform Ultimecia.\n// Transforms into: Ultimecia, Omnipotent (7/7)\nMenace (This creature can't be blocked except by two or more creatures.)\nTime Compression — When this creature transforms into Ultimecia, Omnipotent, take an extra turn after this one.",
)

VIVI_ORNITIER = make_creature(
    name="Vivi Ornitier",
    power=0, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Wizard"},
    supertypes={"Legendary"},
    text="{0}: Add X mana in any combination of {U} and/or {R}, where X is Vivi Ornitier's power. Activate only during your turn and only once each turn.\nWhenever you cast a noncreature spell, put a +1/+1 counter on Vivi Ornitier and it deals 1 damage to each opponent.",
)

AVIVI_ORNITIER = make_creature(
    name="A-Vivi Ornitier",
    power=0, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Wizard"},
    supertypes={"Legendary"},
    text="{T}: Add X mana in any combination of {U} and/or {R}, where X is Vivi Ornitier's power.\nWhenever you cast a noncreature spell, put a +1/+1 counter on Vivi Ornitier and it deals 1 damage to each opponent.",
)

THE_WANDERING_MINSTREL = make_creature(
    name="The Wandering Minstrel",
    power=1, toughness=3,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Bard", "Human"},
    supertypes={"Legendary"},
    text="Lands you control enter untapped.\nThe Minstrel's Ballad — At the beginning of combat on your turn, if you control five or more Towns, create a 2/2 Elemental creature token that's all colors.\n{3}{W}{U}{B}{R}{G}: Other creatures you control get +X/+X until end of turn, where X is the number of Towns you control.",
)

YUNA_HOPE_OF_SPIRA = make_creature(
    name="Yuna, Hope of Spira",
    power=3, toughness=5,
    mana_cost="{3}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Cleric", "Human"},
    supertypes={"Legendary"},
    text="During your turn, Yuna and enchantment creatures you control have trample, lifelink, and ward {2}.\nAt the beginning of your end step, return up to one target enchantment card from your graveyard to the battlefield with a finality counter on it. (If a permanent with a finality counter on it would be put into a graveyard from the battlefield, exile it instead.)",
)

ZIDANE_TANTALUS_THIEF = make_creature(
    name="Zidane, Tantalus Thief",
    power=3, toughness=3,
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Mutant", "Scout"},
    supertypes={"Legendary"},
    text="When Zidane enters, gain control of target creature an opponent controls until end of turn. Untap it. It gains lifelink and haste until end of turn.\nWhenever an opponent gains control of a permanent from you, you create a Treasure token.",
)

ADVENTURERS_AIRSHIP = make_artifact(
    name="Adventurer's Airship",
    mana_cost="{3}",
    text="Flying\nWhenever this Vehicle attacks, draw a card, then discard a card.\nCrew 2 (Tap any number of creatures you control with total power 2 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
)

AETTIR_AND_PRIWEN = make_artifact(
    name="Aettir and Priwen",
    mana_cost="{6}",
    text="Equipped creature has base power and toughness X/X, where X is your life total.\nEquip {5}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
)

BLITZBALL = make_artifact(
    name="Blitzball",
    mana_cost="{3}",
    text="{T}: Add one mana of any color.\nGOOOOAAAALLL! — {T}, Sacrifice this artifact: Draw two cards. Activate only if an opponent was dealt combat damage by a legendary creature this turn.",
)

BUSTER_SWORD = make_artifact(
    name="Buster Sword",
    mana_cost="{3}",
    text="Equipped creature gets +3/+2.\nWhenever equipped creature deals combat damage to a player, draw a card, then you may cast a spell from your hand with mana value less than or equal to that damage without paying its mana cost.\nEquip {2}",
    subtypes={"Equipment"},
)

ELIXIR = make_artifact(
    name="Elixir",
    mana_cost="{1}",
    text="This artifact enters tapped.\n{5}, {T}, Exile this artifact: Shuffle all nonland cards from your graveyard into your library. You gain life equal to the number of cards shuffled into your library this way.",
)

EXCALIBUR_II = make_artifact(
    name="Excalibur II",
    mana_cost="{1}",
    text="Whenever you gain life, put a charge counter on Excalibur II.\nEquipped creature gets +1/+1 for each charge counter on Excalibur II.\nEquip {3}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
)

GENJI_GLOVE = make_artifact(
    name="Genji Glove",
    mana_cost="{5}",
    text="Equipped creature has double strike.\nWhenever equipped creature attacks, if it's the first combat phase of the turn, untap it. After this phase, there is an additional combat phase.\nEquip {3}",
    subtypes={"Equipment"},
)

INSTANT_RAMEN = make_artifact(
    name="Instant Ramen",
    mana_cost="{2}",
    text="Flash\nWhen this artifact enters, draw a card.\n{2}, {T}, Sacrifice this artifact: You gain 3 life.",
    subtypes={"Food"},
)

IRON_GIANT = make_artifact_creature(
    name="Iron Giant",
    power=6, toughness=6,
    mana_cost="{7}",
    colors=set(),
    subtypes={"Demon"},
    text="Vigilance, reach, trample",
)

LION_HEART = make_artifact(
    name="Lion Heart",
    mana_cost="{4}",
    text="When this Equipment enters, it deals 2 damage to any target.\nEquipped creature gets +2/+1.\nEquip {2}",
    subtypes={"Equipment"},
)

LUNATIC_PANDORA = make_artifact(
    name="Lunatic Pandora",
    mana_cost="{1}",
    text="{2}, {T}: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\n{6}, {T}, Sacrifice Lunatic Pandora: Destroy target nonland permanent.",
    supertypes={"Legendary"},
)

MAGIC_POT = make_artifact_creature(
    name="Magic Pot",
    power=1, toughness=4,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Construct", "Goblin"},
    text="When this creature dies, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\n{2}, {T}: Exile target card from a graveyard.",
)

THE_MASAMUNE = make_artifact(
    name="The Masamune",
    mana_cost="{3}",
    text="As long as equipped creature is attacking, it has first strike and must be blocked if able.\nEquipped creature has \"If a creature dying causes a triggered ability of this creature or an emblem you own to trigger, that ability triggers an additional time.\"\nEquip {2}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
)

MONKS_FIST = make_artifact(
    name="Monk's Fist",
    mana_cost="{2}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +1/+0 and is a Monk in addition to its other types.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

PUPU_UFO = make_artifact_creature(
    name="PuPu UFO",
    power=0, toughness=4,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Alien", "Construct"},
    text="Flying\n{T}: You may put a land card from your hand onto the battlefield.\n{3}: Until end of turn, this creature's base power becomes equal to the number of Towns you control.",
)

THE_REGALIA = make_artifact(
    name="The Regalia",
    mana_cost="{4}",
    text="Haste\nWhenever The Regalia attacks, reveal cards from the top of your library until you reveal a land card. Put that card onto the battlefield tapped and the rest on the bottom of your library in a random order.\nCrew 1",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
)

RELENTLESS_XATM092 = make_artifact_creature(
    name="Relentless X-ATM092",
    power=6, toughness=5,
    mana_cost="{6}",
    colors=set(),
    subtypes={"Robot", "Spider"},
    text="This creature can't be blocked except by three or more creatures.\n{8}: Return this card from your graveyard to the battlefield tapped with a finality counter on it. (If a creature with a finality counter on it would die, exile it instead.)",
)

RING_OF_THE_LUCII = make_artifact(
    name="Ring of the Lucii",
    mana_cost="{4}",
    text="{T}: Add {C}{C}.\n{2}, {T}, Pay 1 life: Tap target nonland permanent.",
    supertypes={"Legendary"},
)

WORLD_MAP = make_artifact(
    name="World Map",
    mana_cost="{1}",
    text="{1}, {T}, Sacrifice this artifact: Search your library for a basic land card, reveal it, put it into your hand, then shuffle.\n{3}, {T}, Sacrifice this artifact: Search your library for a land card, reveal it, put it into your hand, then shuffle.",
)

ADVENTURERS_INN = make_land(
    name="Adventurer's Inn",
    text="When this land enters, you gain 2 life.\n{T}: Add {C}.",
    subtypes={"Town"},
)

BALAMB_GARDEN_SEED_ACADEMY = make_land(
    name="Balamb Garden, SeeD Academy",
    text="This land enters tapped.\n{T}: Add {G} or {U}.\n{5}{G}{U}, {T}: Transform this land. This ability costs {1} less to activate for each other Town you control.\n// Transforms into: Balamb Garden, Airborne (5/4)\nFlying\nWhenever Balamb Garden attacks, draw a card.\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Town"},
)

BARON_AIRSHIP_KINGDOM = make_land(
    name="Baron, Airship Kingdom",
    text="This land enters tapped.\n{T}: Add {U} or {R}.",
    subtypes={"Town"},
)

CAPITAL_CITY = make_land(
    name="Capital City",
    text="{T}: Add {C}.\n{1}, {T}: Add one mana of any color.\nCycling {2} ({2}, Discard this card: Draw a card.)",
    subtypes={"Town"},
)

CLIVES_HIDEAWAY = make_land(
    name="Clive's Hideaway",
    text="Hideaway 4 (When this land enters, look at the top four cards of your library, exile one face down, then put the rest on the bottom in a random order.)\n{T}: Add {C}.\n{2}, {T}: You may play the exiled card without paying its mana cost if you control four or more legendary creatures.",
    subtypes={"Town"},
)

CROSSROADS_VILLAGE = make_land(
    name="Crossroads Village",
    text="This land enters tapped. As it enters, choose a color.\n{T}: Add one mana of the chosen color.",
    subtypes={"Town"},
)

EDEN_SEAT_OF_THE_SANCTUM = make_land(
    name="Eden, Seat of the Sanctum",
    text="{T}: Add {C}.\n{5}, {T}: Mill two cards. Then you may sacrifice this land. When you do, return another target permanent card from your graveyard to your hand.",
    subtypes={"Town"},
)

GOHN_TOWN_OF_RUIN = make_land(
    name="Gohn, Town of Ruin",
    text="This land enters tapped.\n{T}: Add {B} or {G}.",
    subtypes={"Town"},
)

THE_GOLD_SAUCER = make_land(
    name="The Gold Saucer",
    text="{T}: Add {C}.\n{2}, {T}: Flip a coin. If you win the flip, create a Treasure token.\n{3}, {T}, Sacrifice two artifacts: Draw a card.",
    subtypes={"Town"},
)

GONGAGA_REACTOR_TOWN = make_land(
    name="Gongaga, Reactor Town",
    text="This land enters tapped.\n{T}: Add {R} or {G}.",
    subtypes={"Town"},
)

GUADOSALAM_FARPLANE_GATEWAY = make_land(
    name="Guadosalam, Farplane Gateway",
    text="This land enters tapped.\n{T}: Add {G} or {U}.",
    subtypes={"Town"},
)

INSOMNIA_CROWN_CITY = make_land(
    name="Insomnia, Crown City",
    text="This land enters tapped.\n{T}: Add {W} or {B}.",
    subtypes={"Town"},
)

ISHGARD_THE_HOLY_SEE = make_land(
    name="Ishgard, the Holy See",
    text="This land enters tapped.\n{T}: Add {W}.\n// Adventure — Faith & Grief {3}{W}{W}\nReturn up to two target artifact and/or enchantment cards from your graveyard to your hand. (Then exile this card. You may play the land later from exile.)",
    subtypes={"Town"},
)

JIDOOR_ARISTOCRATIC_CAPITAL = make_land(
    name="Jidoor, Aristocratic Capital",
    text="This land enters tapped.\n{T}: Add {U}.\n// Adventure — Overture {4}{U}{U}\nTarget opponent mills half their library, rounded down. (Then exile this card. You may play the land later from exile.)",
    subtypes={"Town"},
)

LINDBLUM_INDUSTRIAL_REGENCY = make_land(
    name="Lindblum, Industrial Regency",
    text="This land enters tapped.\n{T}: Add {R}.\n// Adventure — Mage Siege {2}{R}\nCreate a 0/1 black Wizard creature token with \"Whenever you cast a noncreature spell, this token deals 1 damage to each opponent.\"",
    subtypes={"Town"},
)

MIDGAR_CITY_OF_MAKO = make_land(
    name="Midgar, City of Mako",
    text="This land enters tapped.\n{T}: Add {B}.\n// Adventure — Reactor Raid {2}{B}\nYou may sacrifice an artifact or creature. If you do, draw two cards. (Then exile this card. You may play the land later from exile.)",
    subtypes={"Town"},
)

RABANASTRE_ROYAL_CITY = make_land(
    name="Rabanastre, Royal City",
    text="This land enters tapped.\n{T}: Add {R} or {W}.",
    subtypes={"Town"},
)

SHARLAYAN_NATION_OF_SCHOLARS = make_land(
    name="Sharlayan, Nation of Scholars",
    text="This land enters tapped.\n{T}: Add {W} or {U}.",
    subtypes={"Town"},
)

STARTING_TOWN = make_land(
    name="Starting Town",
    text="This land enters tapped unless it's your first, second, or third turn of the game.\n{T}: Add {C}.\n{T}, Pay 1 life: Add one mana of any color.",
    subtypes={"Town"},
)

TRENO_DARK_CITY = make_land(
    name="Treno, Dark City",
    text="This land enters tapped.\n{T}: Add {U} or {B}.",
    subtypes={"Town"},
)

VECTOR_IMPERIAL_CAPITAL = make_land(
    name="Vector, Imperial Capital",
    text="This land enters tapped.\n{T}: Add {B} or {R}.",
    subtypes={"Town"},
)

WINDURST_FEDERATION_CENTER = make_land(
    name="Windurst, Federation Center",
    text="This land enters tapped.\n{T}: Add {G} or {W}.",
    subtypes={"Town"},
)

ZANARKAND_ANCIENT_METROPOLIS = make_land(
    name="Zanarkand, Ancient Metropolis",
    text="This land enters tapped.\n{T}: Add {G}.\n// Adventure — Lasting Fayth {4}{G}{G}\nCreate a 1/1 colorless Hero creature token. Put a +1/+1 counter on it for each land you control. (Then exile this card. You may play the land later from exile.)",
    subtypes={"Town"},
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

WASTES = make_land(
    name="Wastes",
    text="{T}: Add {C}.",
    supertypes={"Basic"},
)

CLOUD_PLANETS_CHAMPION = make_creature(
    name="Cloud, Planet's Champion",
    power=4, toughness=4,
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Mercenary", "Soldier"},
    supertypes={"Legendary"},
    text="During your turn, as long as Cloud is equipped, it has double strike and indestructible. (This creature deals both first-strike and regular combat damage. Damage and effects that say \"destroy\" don't destroy this creature.)\nEquip abilities you activate that target Cloud cost {2} less to activate.",
)

SEPHIROTH_PLANETS_HEIR = make_creature(
    name="Sephiroth, Planet's Heir",
    power=4, toughness=4,
    mana_cost="{4}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Avatar", "Human", "Soldier"},
    supertypes={"Legendary"},
    text="Vigilance (Attacking doesn't cause this creature to tap.)\nWhen Sephiroth enters, creatures your opponents control get -2/-2 until end of turn.\nWhenever a creature an opponent controls dies, put a +1/+1 counter on Sephiroth.",
)

BEATRIX_LOYAL_GENERAL = make_creature(
    name="Beatrix, Loyal General",
    power=4, toughness=4,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Vigilance (Attacking doesn't cause this creature to tap.)\nAt the beginning of combat on your turn, you may attach any number of Equipment you control to target creature you control.",
)

ROSA_RESOLUTE_WHITE_MAGE = make_creature(
    name="Rosa, Resolute White Mage",
    power=2, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Human", "Noble"},
    supertypes={"Legendary"},
    text="Reach (This creature can block creatures with flying.)\nAt the beginning of combat on your turn, put a +1/+1 counter on target creature you control. It gains lifelink until end of turn. (Damage dealt by the creature also causes you to gain that much life.)",
)

ULTIMECIA_TEMPORAL_THREAT = make_creature(
    name="Ultimecia, Temporal Threat",
    power=4, toughness=4,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="When Ultimecia enters, tap all creatures your opponents control.\nWhenever a creature you control deals combat damage to a player, draw a card.",
)

DEADLY_EMBRACE = make_sorcery(
    name="Deadly Embrace",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature an opponent controls. Then draw a card for each creature that died this turn.",
)

SEYMOUR_FLUX = make_creature(
    name="Seymour Flux",
    power=5, toughness=5,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Avatar", "Spirit"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, you may pay 1 life. If you do, draw a card and put a +1/+1 counter on Seymour Flux.",
)

JUDGMENT_BOLT = make_instant(
    name="Judgment Bolt",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Judgment Bolt deals 5 damage to target creature and X damage to that creature's controller, where X is the number of Equipment you control.",
)

LIGHTNING_SECURITY_SERGEANT = make_creature(
    name="Lightning, Security Sergeant",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhenever Lightning deals combat damage to a player, exile the top card of your library. You may play that card for as long as you control Lightning.",
)

XANDE_DARK_MAGE = make_creature(
    name="Xande, Dark Mage",
    power=3, toughness=3,
    mana_cost="{2}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nXande gets +1/+1 for each noncreature, nonland card in your graveyard.",
)

MAGITEK_SCYTHE = make_artifact(
    name="Magitek Scythe",
    mana_cost="{4}",
    text="A Test of Your Reflexes! — When this Equipment enters, you may attach it to target creature you control. If you do, that creature gains first strike until end of turn and must be blocked this turn if able.\nEquipped creature gets +2/+1.\nEquip {2}",
    subtypes={"Equipment"},
)

ULTIMA_WEAPON = make_artifact(
    name="Ultima Weapon",
    mana_cost="{7}",
    text="Whenever equipped creature attacks, destroy target creature an opponent controls.\nEquipped creature gets +7/+7.\nEquip {7}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
)

# =============================================================================
# CARD REGISTRY
# =============================================================================

FINAL_FANTASY_CARDS = {
    "Summon: Bahamut": SUMMON_BAHAMUT,
    "Ultima, Origin of Oblivion": ULTIMA_ORIGIN_OF_OBLIVION,
    "Adelbert Steiner": ADELBERT_STEINER,
    "Aerith Gainsborough": AERITH_GAINSBOROUGH,
    "Aerith Rescue Mission": AERITH_RESCUE_MISSION,
    "Ambrosia Whiteheart": AMBROSIA_WHITEHEART,
    "Ashe, Princess of Dalmasca": ASHE_PRINCESS_OF_DALMASCA,
    "Auron's Inspiration": AURONS_INSPIRATION,
    "Battle Menu": BATTLE_MENU,
    "Cloud, Midgar Mercenary": CLOUD_MIDGAR_MERCENARY,
    "Cloudbound Moogle": CLOUDBOUND_MOOGLE,
    "Coeurl": COEURL,
    "Crystal Fragments": CRYSTAL_FRAGMENTS,
    "The Crystal's Chosen": THE_CRYSTALS_CHOSEN,
    "Delivery Moogle": DELIVERY_MOOGLE,
    "Dion, Bahamut's Dominant": DION_BAHAMUTS_DOMINANT,
    "Dragoon's Lance": DRAGOONS_LANCE,
    "Dwarven Castle Guard": DWARVEN_CASTLE_GUARD,
    "Fate of the Sun-Cryst": FATE_OF_THE_SUNCRYST,
    "From Father to Son": FROM_FATHER_TO_SON,
    "G'raha Tia": GRAHA_TIA,
    "Gaelicat": GAELICAT,
    "Machinist's Arsenal": MACHINISTS_ARSENAL,
    "Magitek Armor": MAGITEK_ARMOR,
    "Magitek Infantry": MAGITEK_INFANTRY,
    "Minwu, White Mage": MINWU_WHITE_MAGE,
    "Moogles' Valor": MOOGLES_VALOR,
    "Paladin's Arms": PALADINS_ARMS,
    "Phoenix Down": PHOENIX_DOWN,
    "Restoration Magic": RESTORATION_MAGIC,
    "Sidequest: Catch a Fish": SIDEQUEST_CATCH_A_FISH,
    "Slash of Light": SLASH_OF_LIGHT,
    "Snow Villiers": SNOW_VILLIERS,
    "Stiltzkin, Moogle Merchant": STILTZKIN_MOOGLE_MERCHANT,
    "Summon: Choco/Mog": SUMMON_CHOCOMOG,
    "Summon: Knights of Round": SUMMON_KNIGHTS_OF_ROUND,
    "Summon: Primal Garuda": SUMMON_PRIMAL_GARUDA,
    "Ultima": ULTIMA,
    "Venat, Heart of Hydaelyn": VENAT_HEART_OF_HYDAELYN,
    "Weapons Vendor": WEAPONS_VENDOR,
    "White Auracite": WHITE_AURACITE,
    "White Mage's Staff": WHITE_MAGES_STAFF,
    "The Wind Crystal": THE_WIND_CRYSTAL,
    "You're Not Alone": YOURE_NOT_ALONE,
    "Zack Fair": ZACK_FAIR,
    "Astrologian's Planisphere": ASTROLOGIANS_PLANISPHERE,
    "Cargo Ship": CARGO_SHIP,
    "Combat Tutorial": COMBAT_TUTORIAL,
    "Dragoon's Wyvern": DRAGOONS_WYVERN,
    "Dreams of Laguna": DREAMS_OF_LAGUNA,
    "Edgar, King of Figaro": EDGAR_KING_OF_FIGARO,
    "Eject": EJECT,
    "Ether": ETHER,
    "Gogo, Master of Mimicry": GOGO_MASTER_OF_MIMICRY,
    "Ice Flan": ICE_FLAN,
    "Ice Magic": ICE_MAGIC,
    "Il Mheg Pixie": IL_MHEG_PIXIE,
    "Jill, Shiva's Dominant": JILL_SHIVAS_DOMINANT,
    "Louisoix's Sacrifice": LOUISOIXS_SACRIFICE,
    "The Lunar Whale": THE_LUNAR_WHALE,
    "Magic Damper": MAGIC_DAMPER,
    "Matoya, Archon Elder": MATOYA_ARCHON_ELDER,
    "Memories Returning": MEMORIES_RETURNING,
    "The Prima Vista": THE_PRIMA_VISTA,
    "Qiqirn Merchant": QIQIRN_MERCHANT,
    "Quistis Trepe": QUISTIS_TREPE,
    "Relm's Sketching": RELMS_SKETCHING,
    "Retrieve the Esper": RETRIEVE_THE_ESPER,
    "Rook Turret": ROOK_TURRET,
    "Sage's Nouliths": SAGES_NOULITHS,
    "Sahagin": SAHAGIN,
    "Scorpion Sentinel": SCORPION_SENTINEL,
    "Sidequest: Card Collection": SIDEQUEST_CARD_COLLECTION,
    "Sleep Magic": SLEEP_MAGIC,
    "Stolen Uniform": STOLEN_UNIFORM,
    "Stuck in Summoner's Sanctum": STUCK_IN_SUMMONERS_SANCTUM,
    "Summon: Leviathan": SUMMON_LEVIATHAN,
    "Summon: Shiva": SUMMON_SHIVA,
    "Swallowed by Leviathan": SWALLOWED_BY_LEVIATHAN,
    "Syncopate": SYNCOPATE,
    "Thief's Knife": THIEFS_KNIFE,
    "Travel the Overworld": TRAVEL_THE_OVERWORLD,
    "Ultros, Obnoxious Octopus": ULTROS_OBNOXIOUS_OCTOPUS,
    "Valkyrie Aerial Unit": VALKYRIE_AERIAL_UNIT,
    "The Water Crystal": THE_WATER_CRYSTAL,
    "Y'shtola Rhul": YSHTOLA_RHUL,
    "Ahriman": AHRIMAN,
    "Al Bhed Salvagers": AL_BHED_SALVAGERS,
    "Ardyn, the Usurper": ARDYN_THE_USURPER,
    "Black Mage's Rod": BLACK_MAGES_ROD,
    "Cecil, Dark Knight": CECIL_DARK_KNIGHT,
    "Circle of Power": CIRCLE_OF_POWER,
    "Cornered by Black Mages": CORNERED_BY_BLACK_MAGES,
    "Dark Confidant": DARK_CONFIDANT,
    "Dark Knight's Greatsword": DARK_KNIGHTS_GREATSWORD,
    "The Darkness Crystal": THE_DARKNESS_CRYSTAL,
    "Demon Wall": DEMON_WALL,
    "Evil Reawakened": EVIL_REAWAKENED,
    "Fang, Fearless l'Cie": FANG_FEARLESS_LCIE,
    "Ragnarok, Divine Deliverance": RAGNAROK_DIVINE_DELIVERANCE,
    "Fight On!": FIGHT_ON,
    "The Final Days": THE_FINAL_DAYS,
    "Gaius van Baelsar": GAIUS_VAN_BAELSAR,
    "Hecteyes": HECTEYES,
    "Jecht, Reluctant Guardian": JECHT_RELUCTANT_GUARDIAN,
    "Kain, Traitorous Dragoon": KAIN_TRAITOROUS_DRAGOON,
    "Malboro": MALBORO,
    "Namazu Trader": NAMAZU_TRADER,
    "Ninja's Blades": NINJAS_BLADES,
    "Overkill": OVERKILL,
    "Phantom Train": PHANTOM_TRAIN,
    "Poison the Waters": POISON_THE_WATERS,
    "Qutrub Forayer": QUTRUB_FORAYER,
    "Reno and Rude": RENO_AND_RUDE,
    "Resentful Revelation": RESENTFUL_REVELATION,
    "Sephiroth, Fabled SOLDIER": SEPHIROTH_FABLED_SOLDIER,
    "Sephiroth's Intervention": SEPHIROTHS_INTERVENTION,
    "Shambling Cie'th": SHAMBLING_CIETH,
    "Shinra Reinforcements": SHINRA_REINFORCEMENTS,
    "Sidequest: Hunt the Mark": SIDEQUEST_HUNT_THE_MARK,
    "Summon: Anima": SUMMON_ANIMA,
    "Summon: Primal Odin": SUMMON_PRIMAL_ODIN,
    "Tonberry": TONBERRY,
    "Undercity Dire Rat": UNDERCITY_DIRE_RAT,
    "Vayne's Treachery": VAYNES_TREACHERY,
    "Vincent Valentine": VINCENT_VALENTINE,
    "Vincent's Limit Break": VINCENTS_LIMIT_BREAK,
    "Zenos yae Galvus": ZENOS_YAE_GALVUS,
    "Zodiark, Umbral God": ZODIARK_UMBRAL_GOD,
    "Barret Wallace": BARRET_WALLACE,
    "Blazing Bomb": BLAZING_BOMB,
    "Call the Mountain Chocobo": CALL_THE_MOUNTAIN_CHOCOBO,
    "Choco-Comet": CHOCOCOMET,
    "Clive, Ifrit's Dominant": CLIVE_IFRITS_DOMINANT,
    "Coral Sword": CORAL_SWORD,
    "The Fire Crystal": THE_FIRE_CRYSTAL,
    "Fire Magic": FIRE_MAGIC,
    "Firion, Wild Rose Warrior": FIRION_WILD_ROSE_WARRIOR,
    "Freya Crescent": FREYA_CRESCENT,
    "Gilgamesh, Master-at-Arms": GILGAMESH_MASTERATARMS,
    "Haste Magic": HASTE_MAGIC,
    "Hill Gigas": HILL_GIGAS,
    "Item Shopkeep": ITEM_SHOPKEEP,
    "Laughing Mad": LAUGHING_MAD,
    "Light of Judgment": LIGHT_OF_JUDGMENT,
    "Mysidian Elder": MYSIDIAN_ELDER,
    "Nibelheim Aflame": NIBELHEIM_AFLAME,
    "Opera Love Song": OPERA_LOVE_SONG,
    "Prompto Argentum": PROMPTO_ARGENTUM,
    "Queen Brahne": QUEEN_BRAHNE,
    "Random Encounter": RANDOM_ENCOUNTER,
    "Raubahn, Bull of Ala Mhigo": RAUBAHN_BULL_OF_ALA_MHIGO,
    "Red Mage's Rapier": RED_MAGES_RAPIER,
    "Sabotender": SABOTENDER,
    "Samurai's Katana": SAMURAIS_KATANA,
    "Sandworm": SANDWORM,
    "Seifer Almasy": SEIFER_ALMASY,
    "Self-Destruct": SELFDESTRUCT,
    "Sidequest: Play Blitzball": SIDEQUEST_PLAY_BLITZBALL,
    "Sorceress's Schemes": SORCERESSS_SCHEMES,
    "Summon: Brynhildr": SUMMON_BRYNHILDR,
    "Summon: Esper Ramuh": SUMMON_ESPER_RAMUH,
    "Summon: G.F. Cerberus": SUMMON_GF_CERBERUS,
    "Summon: G.F. Ifrit": SUMMON_GF_IFRIT,
    "Suplex": SUPLEX,
    "Thunder Magic": THUNDER_MAGIC,
    "Triple Triad": TRIPLE_TRIAD,
    "Unexpected Request": UNEXPECTED_REQUEST,
    "Vaan, Street Thief": VAAN_STREET_THIEF,
    "Warrior's Sword": WARRIORS_SWORD,
    "Zell Dincht": ZELL_DINCHT,
    "Airship Crash": AIRSHIP_CRASH,
    "Ancient Adamantoise": ANCIENT_ADAMANTOISE,
    "Balamb T-Rexaur": BALAMB_TREXAUR,
    "Bard's Bow": BARDS_BOW,
    "Bartz and Boko": BARTZ_AND_BOKO,
    "Blitzball Shot": BLITZBALL_SHOT,
    "Cactuar": CACTUAR,
    "Chocobo Kick": CHOCOBO_KICK,
    "Chocobo Racetrack": CHOCOBO_RACETRACK,
    "Clash of the Eikons": CLASH_OF_THE_EIKONS,
    "Coliseum Behemoth": COLISEUM_BEHEMOTH,
    "Commune with Beavers": COMMUNE_WITH_BEAVERS,
    "Diamond Weapon": DIAMOND_WEAPON,
    "The Earth Crystal": THE_EARTH_CRYSTAL,
    "Esper Origins": ESPER_ORIGINS,
    "Galuf's Final Act": GALUFS_FINAL_ACT,
    "Gigantoad": GIGANTOAD,
    "Goobbue Gardener": GOOBBUE_GARDENER,
    "Gran Pulse Ochu": GRAN_PULSE_OCHU,
    "Gysahl Greens": GYSAHL_GREENS,
    "Jumbo Cactuar": JUMBO_CACTUAR,
    "Loporrit Scout": LOPORRIT_SCOUT,
    "Prishe's Wanderings": PRISHES_WANDERINGS,
    "Quina, Qu Gourmet": QUINA_QU_GOURMET,
    "Reach the Horizon": REACH_THE_HORIZON,
    "A Realm Reborn": A_REALM_REBORN,
    "Ride the Shoopuf": RIDE_THE_SHOOPUF,
    "Rydia's Return": RYDIAS_RETURN,
    "Sazh Katzroy": SAZH_KATZROY,
    "Sazh's Chocobo": SAZHS_CHOCOBO,
    "Sidequest: Raise a Chocobo": SIDEQUEST_RAISE_A_CHOCOBO,
    "Summon: Fat Chocobo": SUMMON_FAT_CHOCOBO,
    "Summon: Fenrir": SUMMON_FENRIR,
    "Summon: Titan": SUMMON_TITAN,
    "Summoner's Grimoire": SUMMONERS_GRIMOIRE,
    "Tifa Lockhart": TIFA_LOCKHART,
    "Tifa's Limit Break": TIFAS_LIMIT_BREAK,
    "Torgal, A Fine Hound": TORGAL_A_FINE_HOUND,
    "Town Greeter": TOWN_GREETER,
    "Traveling Chocobo": TRAVELING_CHOCOBO,
    "Vanille, Cheerful l'Cie": VANILLE_CHEERFUL_LCIE,
    "Absolute Virtue": ABSOLUTE_VIRTUE,
    "Balthier and Fran": BALTHIER_AND_FRAN,
    "Black Waltz No. 3": BLACK_WALTZ_NO_3,
    "Choco, Seeker of Paradise": CHOCO_SEEKER_OF_PARADISE,
    "Cid, Timeless Artificer": CID_TIMELESS_ARTIFICER,
    "Cloud of Darkness": CLOUD_OF_DARKNESS,
    "Emet-Selch, Unsundered": EMETSELCH_UNSUNDERED,
    "The Emperor of Palamecia": THE_EMPEROR_OF_PALAMECIA,
    "Exdeath, Void Warlock": EXDEATH_VOID_WARLOCK,
    "Garland, Knight of Cornelia": GARLAND_KNIGHT_OF_CORNELIA,
    "Garnet, Princess of Alexandria": GARNET_PRINCESS_OF_ALEXANDRIA,
    "Giott, King of the Dwarves": GIOTT_KING_OF_THE_DWARVES,
    "Gladiolus Amicitia": GLADIOLUS_AMICITIA,
    "Golbez, Crystal Collector": GOLBEZ_CRYSTAL_COLLECTOR,
    "Hope Estheim": HOPE_ESTHEIM,
    "Ignis Scientia": IGNIS_SCIENTIA,
    "Jenova, Ancient Calamity": JENOVA_ANCIENT_CALAMITY,
    "Joshua, Phoenix's Dominant": JOSHUA_PHOENIXS_DOMINANT,
    "Judge Magister Gabranth": JUDGE_MAGISTER_GABRANTH,
    "Kefka, Court Mage": KEFKA_COURT_MAGE,
    "Kuja, Genome Sorcerer": KUJA_GENOME_SORCERER,
    "Lightning, Army of One": LIGHTNING_ARMY_OF_ONE,
    "Locke Cole": LOCKE_COLE,
    "Noctis, Prince of Lucis": NOCTIS_PRINCE_OF_LUCIS,
    "Omega, Heartless Evolution": OMEGA_HEARTLESS_EVOLUTION,
    "Rinoa Heartilly": RINOA_HEARTILLY,
    "Rufus Shinra": RUFUS_SHINRA,
    "Rydia, Summoner of Mist": RYDIA_SUMMONER_OF_MIST,
    "Serah Farron": SERAH_FARRON,
    "Shantotto, Tactician Magician": SHANTOTTO_TACTICIAN_MAGICIAN,
    "Sin, Spira's Punishment": SIN_SPIRAS_PUNISHMENT,
    "Squall, SeeD Mercenary": SQUALL_SEED_MERCENARY,
    "Tellah, Great Sage": TELLAH_GREAT_SAGE,
    "Terra, Magical Adept": TERRA_MAGICAL_ADEPT,
    "Tidus, Blitzball Star": TIDUS_BLITZBALL_STAR,
    "Ultimecia, Time Sorceress": ULTIMECIA_TIME_SORCERESS,
    "Vivi Ornitier": VIVI_ORNITIER,
    "A-Vivi Ornitier": AVIVI_ORNITIER,
    "The Wandering Minstrel": THE_WANDERING_MINSTREL,
    "Yuna, Hope of Spira": YUNA_HOPE_OF_SPIRA,
    "Zidane, Tantalus Thief": ZIDANE_TANTALUS_THIEF,
    "Adventurer's Airship": ADVENTURERS_AIRSHIP,
    "Aettir and Priwen": AETTIR_AND_PRIWEN,
    "Blitzball": BLITZBALL,
    "Buster Sword": BUSTER_SWORD,
    "Elixir": ELIXIR,
    "Excalibur II": EXCALIBUR_II,
    "Genji Glove": GENJI_GLOVE,
    "Instant Ramen": INSTANT_RAMEN,
    "Iron Giant": IRON_GIANT,
    "Lion Heart": LION_HEART,
    "Lunatic Pandora": LUNATIC_PANDORA,
    "Magic Pot": MAGIC_POT,
    "The Masamune": THE_MASAMUNE,
    "Monk's Fist": MONKS_FIST,
    "PuPu UFO": PUPU_UFO,
    "The Regalia": THE_REGALIA,
    "Relentless X-ATM092": RELENTLESS_XATM092,
    "Ring of the Lucii": RING_OF_THE_LUCII,
    "World Map": WORLD_MAP,
    "Adventurer's Inn": ADVENTURERS_INN,
    "Balamb Garden, SeeD Academy": BALAMB_GARDEN_SEED_ACADEMY,
    "Baron, Airship Kingdom": BARON_AIRSHIP_KINGDOM,
    "Capital City": CAPITAL_CITY,
    "Clive's Hideaway": CLIVES_HIDEAWAY,
    "Crossroads Village": CROSSROADS_VILLAGE,
    "Eden, Seat of the Sanctum": EDEN_SEAT_OF_THE_SANCTUM,
    "Gohn, Town of Ruin": GOHN_TOWN_OF_RUIN,
    "The Gold Saucer": THE_GOLD_SAUCER,
    "Gongaga, Reactor Town": GONGAGA_REACTOR_TOWN,
    "Guadosalam, Farplane Gateway": GUADOSALAM_FARPLANE_GATEWAY,
    "Insomnia, Crown City": INSOMNIA_CROWN_CITY,
    "Ishgard, the Holy See": ISHGARD_THE_HOLY_SEE,
    "Jidoor, Aristocratic Capital": JIDOOR_ARISTOCRATIC_CAPITAL,
    "Lindblum, Industrial Regency": LINDBLUM_INDUSTRIAL_REGENCY,
    "Midgar, City of Mako": MIDGAR_CITY_OF_MAKO,
    "Rabanastre, Royal City": RABANASTRE_ROYAL_CITY,
    "Sharlayan, Nation of Scholars": SHARLAYAN_NATION_OF_SCHOLARS,
    "Starting Town": STARTING_TOWN,
    "Treno, Dark City": TRENO_DARK_CITY,
    "Vector, Imperial Capital": VECTOR_IMPERIAL_CAPITAL,
    "Windurst, Federation Center": WINDURST_FEDERATION_CENTER,
    "Zanarkand, Ancient Metropolis": ZANARKAND_ANCIENT_METROPOLIS,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
    "Wastes": WASTES,
    "Cloud, Planet's Champion": CLOUD_PLANETS_CHAMPION,
    "Sephiroth, Planet's Heir": SEPHIROTH_PLANETS_HEIR,
    "Beatrix, Loyal General": BEATRIX_LOYAL_GENERAL,
    "Rosa, Resolute White Mage": ROSA_RESOLUTE_WHITE_MAGE,
    "Ultimecia, Temporal Threat": ULTIMECIA_TEMPORAL_THREAT,
    "Deadly Embrace": DEADLY_EMBRACE,
    "Seymour Flux": SEYMOUR_FLUX,
    "Judgment Bolt": JUDGMENT_BOLT,
    "Lightning, Security Sergeant": LIGHTNING_SECURITY_SERGEANT,
    "Xande, Dark Mage": XANDE_DARK_MAGE,
    "Magitek Scythe": MAGITEK_SCYTHE,
    "Ultima Weapon": ULTIMA_WEAPON,
}

print(f"Loaded {len(FINAL_FANTASY_CARDS)} Final Fantasy cards")
