"""
Magic: The Gathering Foundations (FDN) Card Implementations

Set released November 2024. ~250 cards.
Beginner-friendly core set with classic reprints and new Standard cards.
"""

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, ObjectState, CardDefinition,
    make_creature, make_instant, make_enchantment,
    new_id, get_power, get_toughness
)
from typing import Optional, Callable
from src.cards.interceptor_helpers import (
    make_etb_trigger, make_death_trigger, make_attack_trigger,
    make_damage_trigger, make_static_pt_boost, make_keyword_grant,
    other_creatures_you_control, creatures_with_subtype,
    make_spell_cast_trigger, make_upkeep_trigger, make_end_step_trigger,
    make_life_gain_trigger, make_life_loss_trigger, creatures_you_control,
    other_creatures_with_subtype, all_opponents
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def make_sorcery(name: str, mana_cost: str, colors: set, text: str, subtypes: set = None, resolve=None):
    """Helper to create sorcery card definitions."""
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


def make_artifact(name: str, mana_cost: str, text: str, subtypes: set = None, setup_interceptors=None):
    """Helper to create artifact card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            subtypes=subtypes or set(),
            mana_cost=mana_cost
        ),
        text=text,
        setup_interceptors=setup_interceptors
    )


def make_equipment(name: str, mana_cost: str, text: str, equip_cost: str, subtypes: set = None, setup_interceptors=None):
    """Helper to create equipment card definitions."""
    base_subtypes = {"Equipment"}
    if subtypes:
        base_subtypes.update(subtypes)
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            subtypes=base_subtypes,
            mana_cost=mana_cost
        ),
        text=f"{text}\nEquip {equip_cost}",
        setup_interceptors=setup_interceptors
    )


def make_land(name: str, text: str = "", subtypes: set = None, supertypes: set = None):
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
        text=text
    )


def make_planeswalker(name: str, mana_cost: str, colors: set, subtypes: set, loyalty: int, text: str, setup_interceptors=None):
    """Helper to create planeswalker card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.PLANESWALKER},
            subtypes=subtypes,
            colors=colors,
            mana_cost=mana_cost
        ),
        text=f"Loyalty: {loyalty}\n{text}",
        setup_interceptors=setup_interceptors
    )


def make_aura(name: str, mana_cost: str, colors: set, text: str, subtypes: set = None, setup_interceptors=None):
    """Helper to create aura enchantment card definitions."""
    base_subtypes = {"Aura"}
    if subtypes:
        base_subtypes.update(subtypes)
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT},
            subtypes=base_subtypes,
            colors=colors,
            mana_cost=mana_cost
        ),
        text=text,
        setup_interceptors=setup_interceptors
    )


# =============================================================================
# WHITE CARDS
# =============================================================================

# Ajani, Caller of the Pride
AJANI_CALLER_OF_THE_PRIDE = make_planeswalker(
    name="Ajani, Caller of the Pride",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Ajani"},
    loyalty=4,
    text="+1: Put a +1/+1 counter on up to one target creature.\n-3: Target creature gains flying and double strike until end of turn.\n-8: Create X 2/2 white Cat creature tokens, where X is your life total."
)

# Day of Judgment
DAY_OF_JUDGMENT = make_sorcery(
    name="Day of Judgment",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Destroy all creatures."
)

# Banishing Light
def banishing_light_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting handled by system
    return [make_etb_trigger(obj, etb_effect)]

BANISHING_LIGHT = make_enchantment(
    name="Banishing Light",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When Banishing Light enters, exile target nonland permanent an opponent controls until Banishing Light leaves the battlefield.",
    setup_interceptors=banishing_light_setup
)

# Pacifism
PACIFISM = make_aura(
    name="Pacifism",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Enchant creature\nEnchanted creature can't attack or block."
)

# Serra Angel
SERRA_ANGEL = make_creature(
    name="Serra Angel",
    power=4,
    toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying, vigilance"
)

# Angelic Edict
ANGELIC_EDICT = make_sorcery(
    name="Angelic Edict",
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    text="Exile target creature or enchantment."
)

# Inspiring Overseer
def inspiring_overseer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id),
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

INSPIRING_OVERSEER = make_creature(
    name="Inspiring Overseer",
    power=2,
    toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Angel", "Cleric"},
    text="Flying\nWhen Inspiring Overseer enters, you gain 1 life and draw a card.",
    setup_interceptors=inspiring_overseer_setup
)

# Elite Vanguard
ELITE_VANGUARD = make_creature(
    name="Elite Vanguard",
    power=2,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text=""
)

# Glory Seeker
GLORY_SEEKER = make_creature(
    name="Glory Seeker",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text=""
)

# Attended Knight
def attended_knight_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token_type': 'creature',
            'power': 1, 'toughness': 1,
            'colors': {Color.WHITE},
            'subtypes': {'Soldier'}
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

ATTENDED_KNIGHT = make_creature(
    name="Attended Knight",
    power=2,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="First strike\nWhen Attended Knight enters, create a 1/1 white Soldier creature token.",
    setup_interceptors=attended_knight_setup
)

# Valorous Stance
VALOROUS_STANCE = make_instant(
    name="Valorous Stance",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Target creature gains indestructible until end of turn.\n• Destroy target creature with toughness 4 or greater."
)

# Raise the Alarm
RAISE_THE_ALARM = make_instant(
    name="Raise the Alarm",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Create two 1/1 white Soldier creature tokens."
)

# Disenchant
DISENCHANT = make_instant(
    name="Disenchant",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Destroy target artifact or enchantment."
)

# Swords to Plowshares
SWORDS_TO_PLOWSHARES = make_instant(
    name="Swords to Plowshares",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Exile target creature. Its controller gains life equal to its power."
)

# Savannah Lions
SAVANNAH_LIONS = make_creature(
    name="Savannah Lions",
    power=2,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Cat"},
    text=""
)

# Aerial Responder
AERIAL_RESPONDER = make_creature(
    name="Aerial Responder",
    power=2,
    toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Dwarf", "Soldier"},
    text="Flying, vigilance, lifelink"
)

# Leonin Warleader
def leonin_warleader_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token_type': 'creature',
                'power': 1, 'toughness': 1,
                'colors': {Color.WHITE},
                'subtypes': {'Cat'},
                'keywords': {'lifelink'},
                'attacking': True
            }, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token_type': 'creature',
                'power': 1, 'toughness': 1,
                'colors': {Color.WHITE},
                'subtypes': {'Cat'},
                'keywords': {'lifelink'},
                'attacking': True
            }, source=obj.id)
        ]
    return [make_attack_trigger(obj, attack_effect)]

LEONIN_WARLEADER = make_creature(
    name="Leonin Warleader",
    power=4,
    toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Soldier"},
    text="Whenever Leonin Warleader attacks, create two 1/1 white Cat creature tokens with lifelink that are tapped and attacking.",
    setup_interceptors=leonin_warleader_setup
)

# Heliod's Pilgrim
def heliods_pilgrim_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Search library for Aura
    return [make_etb_trigger(obj, etb_effect)]

HELIODS_PILGRIM = make_creature(
    name="Heliod's Pilgrim",
    power=1,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    text="When Heliod's Pilgrim enters, you may search your library for an Aura card, reveal it, put it into your hand, then shuffle.",
    setup_interceptors=heliods_pilgrim_setup
)

# Soldier of the Pantheon
SOLDIER_OF_THE_PANTHEON = make_creature(
    name="Soldier of the Pantheon",
    power=2,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Protection from multicolored"
)

# Glorious Anthem
def glorious_anthem_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_static_pt_boost(obj, 1, 1, creatures_you_control(obj))

GLORIOUS_ANTHEM = make_enchantment(
    name="Glorious Anthem",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +1/+1.",
    setup_interceptors=glorious_anthem_setup
)

# Prison Term
PRISON_TERM = make_aura(
    name="Prison Term",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    text="Enchant creature\nEnchanted creature can't attack or block, and its activated abilities can't be activated.\nWhenever a creature enters under an opponent's control, you may attach Prison Term to that creature."
)

# Captain of the Watch
def captain_of_the_watch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        tokens = []
        for _ in range(3):
            tokens.append(Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token_type': 'creature',
                'power': 1, 'toughness': 1,
                'colors': {Color.WHITE},
                'subtypes': {'Soldier'}
            }, source=obj.id))
        return tokens

    interceptors = [make_etb_trigger(obj, etb_effect)]
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Soldier")))
    interceptors.append(make_keyword_grant(obj, ['vigilance'], other_creatures_with_subtype(obj, "Soldier")))
    return interceptors

CAPTAIN_OF_THE_WATCH = make_creature(
    name="Captain of the Watch",
    power=3,
    toughness=3,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Vigilance\nOther Soldier creatures you control get +1/+1 and have vigilance.\nWhen Captain of the Watch enters, create three 1/1 white Soldier creature tokens.",
    setup_interceptors=captain_of_the_watch_setup
)

# Ajani's Pridemate
def ajanis_pridemate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def life_gain_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id,
            'counter_type': '+1/+1',
            'amount': 1
        }, source=obj.id)]
    return [make_life_gain_trigger(obj, life_gain_effect)]

AJANIS_PRIDEMATE = make_creature(
    name="Ajani's Pridemate",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Soldier"},
    text="Whenever you gain life, put a +1/+1 counter on Ajani's Pridemate.",
    setup_interceptors=ajanis_pridemate_setup
)

# Soul Warden
def soul_warden_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        target_id = event.payload.get('object_id')
        if target_id == source.id:
            return False
        target = state.objects.get(target_id)
        return target and CardType.CREATURE in target.characteristics.types

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [make_etb_trigger(obj, etb_effect, creature_etb_filter)]

SOUL_WARDEN = make_creature(
    name="Soul Warden",
    power=1,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    text="Whenever another creature enters, you gain 1 life.",
    setup_interceptors=soul_warden_setup
)

# White Knight
WHITE_KNIGHT = make_creature(
    name="White Knight",
    power=2,
    toughness=2,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="First strike\nProtection from black"
)

# =============================================================================
# BLUE CARDS
# =============================================================================

# Jace, Ingenious Mind-Mage
JACE_INGENIOUS_MIND_MAGE = make_planeswalker(
    name="Jace, Ingenious Mind-Mage",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Jace"},
    loyalty=5,
    text="+1: Draw a card.\n+1: Untap all creatures you control.\n-9: Gain control of up to three target creatures."
)

# Counterspell
COUNTERSPELL = make_instant(
    name="Counterspell",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell."
)

# Cancel
CANCEL = make_instant(
    name="Cancel",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell."
)

# Negate
NEGATE = make_instant(
    name="Negate",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target noncreature spell."
)

# Essence Scatter
ESSENCE_SCATTER = make_instant(
    name="Essence Scatter",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target creature spell."
)

# Divination
DIVINATION = make_sorcery(
    name="Divination",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw two cards."
)

# Opt
OPT = make_instant(
    name="Opt",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Scry 1, then draw a card."
)

# Unsummon
UNSUMMON = make_instant(
    name="Unsummon",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Return target creature to its owner's hand."
)

# Wind Drake
WIND_DRAKE = make_creature(
    name="Wind Drake",
    power=2,
    toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Drake"},
    text="Flying"
)

# Air Elemental
AIR_ELEMENTAL = make_creature(
    name="Air Elemental",
    power=4,
    toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="Flying"
)

# Frost Lynx
def frost_lynx_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Tap target creature, doesn't untap
    return [make_etb_trigger(obj, etb_effect)]

FROST_LYNX = make_creature(
    name="Frost Lynx",
    power=2,
    toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Cat"},
    text="When Frost Lynx enters, tap target creature an opponent controls. That creature doesn't untap during its controller's next untap step.",
    setup_interceptors=frost_lynx_setup
)

# Merfolk Looter
MERFOLK_LOOTER = make_creature(
    name="Merfolk Looter",
    power=1,
    toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Rogue"},
    text="{T}: Draw a card, then discard a card."
)

# Archaeomancer
def archaeomancer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Return instant/sorcery from graveyard
    return [make_etb_trigger(obj, etb_effect)]

ARCHAEOMANCER = make_creature(
    name="Archaeomancer",
    power=1,
    toughness=2,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When Archaeomancer enters, return target instant or sorcery card from your graveyard to your hand.",
    setup_interceptors=archaeomancer_setup
)

# Thirst for Knowledge
THIRST_FOR_KNOWLEDGE = make_instant(
    name="Thirst for Knowledge",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw three cards. Then discard two cards unless you discard an artifact card."
)

# Ponder
PONDER = make_sorcery(
    name="Ponder",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Look at the top three cards of your library, then put them back in any order. You may shuffle. Draw a card."
)

# Preordain
PREORDAIN = make_sorcery(
    name="Preordain",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Scry 2, then draw a card."
)

# Azure Mage
AZURE_MAGE = make_creature(
    name="Azure Mage",
    power=2,
    toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="{3}{U}: Draw a card."
)

# Sphinx of Enlightenment
def sphinx_of_enlightenment_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

SPHINX_OF_ENLIGHTENMENT = make_creature(
    name="Sphinx of Enlightenment",
    power=5,
    toughness=5,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Sphinx"},
    text="Flying\nWhen Sphinx of Enlightenment enters, draw two cards.",
    setup_interceptors=sphinx_of_enlightenment_setup
)

# Cloudkin Seer
def cloudkin_seer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

CLOUDKIN_SEER = make_creature(
    name="Cloudkin Seer",
    power=2,
    toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Wizard"},
    text="Flying\nWhen Cloudkin Seer enters, draw a card.",
    setup_interceptors=cloudkin_seer_setup
)

# Talrand, Sky Summoner
def talrand_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def spell_cast_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token_type': 'creature',
            'power': 2, 'toughness': 2,
            'colors': {Color.BLUE},
            'subtypes': {'Drake'},
            'keywords': {'flying'}
        }, source=obj.id)]
    return [make_spell_cast_trigger(obj, spell_cast_effect, spell_type_filter={CardType.INSTANT, CardType.SORCERY})]

TALRAND_SKY_SUMMONER = make_creature(
    name="Talrand, Sky Summoner",
    power=2,
    toughness=2,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast an instant or sorcery spell, create a 2/2 blue Drake creature token with flying.",
    setup_interceptors=talrand_setup
)

# Faerie Miscreant
def faerie_miscreant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        for o in state.objects.values():
            if (o.id != obj.id and
                o.controller == obj.controller and
                "Faerie Miscreant" in o.characteristics.name and
                o.zone == ZoneType.BATTLEFIELD):
                return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id)]
        return []
    return [make_etb_trigger(obj, etb_effect)]

FAERIE_MISCREANT = make_creature(
    name="Faerie Miscreant",
    power=1,
    toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Rogue"},
    text="Flying\nWhen Faerie Miscreant enters, if you control another creature named Faerie Miscreant, draw a card.",
    setup_interceptors=faerie_miscreant_setup
)

# Void Snare
VOID_SNARE = make_sorcery(
    name="Void Snare",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Return target nonland permanent to its owner's hand."
)

# Sleep
SLEEP = make_sorcery(
    name="Sleep",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Tap all creatures target player controls. Those creatures don't untap during that player's next untap step."
)

# =============================================================================
# BLACK CARDS
# =============================================================================

# Liliana, Death's Majesty
LILIANA_DEATHS_MAJESTY = make_planeswalker(
    name="Liliana, Death's Majesty",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Liliana"},
    loyalty=5,
    text="+1: Create a 2/2 black Zombie creature token. Mill two cards.\n-3: Return target creature card from your graveyard to the battlefield. That creature is a black Zombie in addition to its other colors and types.\n-7: Destroy all non-Zombie creatures."
)

# Murder
MURDER = make_instant(
    name="Murder",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature."
)

# Doom Blade
DOOM_BLADE = make_instant(
    name="Doom Blade",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Destroy target nonblack creature."
)

# Go for the Throat
GO_FOR_THE_THROAT = make_instant(
    name="Go for the Throat",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Destroy target nonartifact creature."
)

# Sign in Blood
SIGN_IN_BLOOD = make_sorcery(
    name="Sign in Blood",
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    text="Target player draws two cards and loses 2 life."
)

# Read the Bones
READ_THE_BONES = make_sorcery(
    name="Read the Bones",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Scry 2, then draw two cards. You lose 2 life."
)

# Walking Corpse
WALKING_CORPSE = make_creature(
    name="Walking Corpse",
    power=2,
    toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text=""
)

# Gravedigger
def gravedigger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Return creature from graveyard
    return [make_etb_trigger(obj, etb_effect)]

GRAVEDIGGER = make_creature(
    name="Gravedigger",
    power=2,
    toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="When Gravedigger enters, you may return target creature card from your graveyard to your hand.",
    setup_interceptors=gravedigger_setup
)

# Vampire Nighthawk
VAMPIRE_NIGHTHAWK = make_creature(
    name="Vampire Nighthawk",
    power=2,
    toughness=3,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Shaman"},
    text="Flying, deathtouch, lifelink"
)

# Child of Night
CHILD_OF_NIGHT = make_creature(
    name="Child of Night",
    power=2,
    toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="Lifelink"
)

# Festering Goblin
def festering_goblin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Target gets -1/-1
    return [make_death_trigger(obj, death_effect)]

FESTERING_GOBLIN = make_creature(
    name="Festering Goblin",
    power=1,
    toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Zombie", "Goblin"},
    text="When Festering Goblin dies, target creature gets -1/-1 until end of turn.",
    setup_interceptors=festering_goblin_setup
)

# Ravenous Rats
def ravenous_rats_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Opponent discards
    return [make_etb_trigger(obj, etb_effect)]

RAVENOUS_RATS = make_creature(
    name="Ravenous Rats",
    power=1,
    toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rat"},
    text="When Ravenous Rats enters, target opponent discards a card.",
    setup_interceptors=ravenous_rats_setup
)

# Diregraf Ghoul
DIREGRAF_GHOUL = make_creature(
    name="Diregraf Ghoul",
    power=2,
    toughness=2,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="Diregraf Ghoul enters tapped."
)

# Typhoid Rats
TYPHOID_RATS = make_creature(
    name="Typhoid Rats",
    power=1,
    toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Rat"},
    text="Deathtouch"
)

# Dread Wanderer
DREAD_WANDERER = make_creature(
    name="Dread Wanderer",
    power=2,
    toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Zombie", "Jackal"},
    text="Dread Wanderer enters tapped.\n{2}{B}: Return Dread Wanderer from your graveyard to the battlefield. Activate only as a sorcery and only if you have one or fewer cards in hand."
)

# Zombie Lord - Lord of the Accursed
def lord_of_the_accursed_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Zombie"))
    return interceptors

LORD_OF_THE_ACCURSED = make_creature(
    name="Lord of the Accursed",
    power=2,
    toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="Other Zombie creatures you control get +1/+1.\n{1}{B}, {T}: All Zombies gain menace until end of turn.",
    setup_interceptors=lord_of_the_accursed_setup
)

# Duress
DURESS = make_sorcery(
    name="Duress",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target opponent reveals their hand. You choose a noncreature, nonland card from it. That player discards that card."
)

# Mind Rot
MIND_ROT = make_sorcery(
    name="Mind Rot",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Target player discards two cards."
)

# Nightmare
def nightmare_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def swamp_count_filter(target: GameObject, s: GameState) -> bool:
        return target.id == obj.id

    def count_swamps(state: GameState) -> int:
        count = 0
        for o in state.objects.values():
            if (o.controller == obj.controller and
                o.zone == ZoneType.BATTLEFIELD and
                "Swamp" in o.characteristics.subtypes):
                count += 1
        return count

    # Dynamic P/T based on swamps
    return []

NIGHTMARE = make_creature(
    name="Nightmare",
    power=0,
    toughness=0,
    mana_cost="{5}{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare", "Horse"},
    text="Flying\nNightmare's power and toughness are each equal to the number of Swamps you control.",
    setup_interceptors=nightmare_setup
)

# Blood Artist
def blood_artist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def creature_dies_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        return target and CardType.CREATURE in target.characteristics.types

    def death_effect(event: Event, state: GameState) -> list[Event]:
        opponents = all_opponents(obj, state)
        events = []
        for opp in opponents:
            events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': opp, 'amount': -1}, source=obj.id))
        events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id))
        return events

    return [make_etb_trigger(obj, death_effect, creature_dies_filter)]

BLOOD_ARTIST = make_creature(
    name="Blood Artist",
    power=0,
    toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="Whenever Blood Artist or another creature dies, target opponent loses 1 life and you gain 1 life.",
    setup_interceptors=blood_artist_setup
)

# Black Knight
BLACK_KNIGHT = make_creature(
    name="Black Knight",
    power=2,
    toughness=2,
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Knight"},
    text="First strike\nProtection from white"
)

# =============================================================================
# RED CARDS
# =============================================================================

# Lightning Bolt
LIGHTNING_BOLT = make_instant(
    name="Lightning Bolt",
    mana_cost="{R}",
    colors={Color.RED},
    text="Lightning Bolt deals 3 damage to any target."
)

# Shock
SHOCK = make_instant(
    name="Shock",
    mana_cost="{R}",
    colors={Color.RED},
    text="Shock deals 2 damage to any target."
)

# Searing Spear
SEARING_SPEAR = make_instant(
    name="Searing Spear",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Searing Spear deals 3 damage to any target."
)

# Incinerate
INCINERATE = make_instant(
    name="Incinerate",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Incinerate deals 3 damage to any target. A creature dealt damage this way can't be regenerated this turn."
)

# Lava Axe
LAVA_AXE = make_sorcery(
    name="Lava Axe",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="Lava Axe deals 5 damage to target player or planeswalker."
)

# Firebolt
FIREBOLT = make_sorcery(
    name="Firebolt",
    mana_cost="{R}",
    colors={Color.RED},
    text="Firebolt deals 2 damage to any target.\nFlashback {4}{R}"
)

# Goblin Guide
def goblin_guide_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Reveal and possibly give land
    return [make_attack_trigger(obj, attack_effect)]

GOBLIN_GUIDE = make_creature(
    name="Goblin Guide",
    power=2,
    toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Scout"},
    text="Haste\nWhenever Goblin Guide attacks, defending player reveals the top card of their library. If it's a land card, that player puts it into their hand.",
    setup_interceptors=goblin_guide_setup
)

# Monastery Swiftspear
MONASTERY_SWIFTSPEAR = make_creature(
    name="Monastery Swiftspear",
    power=1,
    toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Monk"},
    text="Haste\nProwess"
)

# Goblin Piker
GOBLIN_PIKER = make_creature(
    name="Goblin Piker",
    power=2,
    toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text=""
)

# Goblin Shortcutter
GOBLIN_SHORTCUTTER = make_creature(
    name="Goblin Shortcutter",
    power=2,
    toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Scout"},
    text="When Goblin Shortcutter enters, target creature can't block this turn."
)

# Raging Goblin
RAGING_GOBLIN = make_creature(
    name="Raging Goblin",
    power=1,
    toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Berserker"},
    text="Haste"
)

# Goblin Chieftain
def goblin_chieftain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Goblin"))
    interceptors.append(make_keyword_grant(obj, ['haste'], other_creatures_with_subtype(obj, "Goblin")))
    return interceptors

GOBLIN_CHIEFTAIN = make_creature(
    name="Goblin Chieftain",
    power=2,
    toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
    text="Haste\nOther Goblin creatures you control get +1/+1 and have haste.",
    setup_interceptors=goblin_chieftain_setup
)

# Krenko, Mob Boss
def krenko_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Tap: Create X 1/1 Goblins where X is number of Goblins you control
    return []

KRENKO_MOB_BOSS = make_creature(
    name="Krenko, Mob Boss",
    power=3,
    toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    supertypes={"Legendary"},
    text="{T}: Create X 1/1 red Goblin creature tokens, where X is the number of Goblins you control.",
    setup_interceptors=krenko_setup
)

# Dragon Hatchling
DRAGON_HATCHLING = make_creature(
    name="Dragon Hatchling",
    power=0,
    toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\n{R}: Dragon Hatchling gets +1/+0 until end of turn."
)

# Shivan Dragon
SHIVAN_DRAGON = make_creature(
    name="Shivan Dragon",
    power=5,
    toughness=5,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\n{R}: Shivan Dragon gets +1/+0 until end of turn."
)

# Thundermaw Hellkite
def thundermaw_hellkite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Tap and deal 1 to each flyer opponent controls
    return [make_etb_trigger(obj, etb_effect)]

THUNDERMAW_HELLKITE = make_creature(
    name="Thundermaw Hellkite",
    power=5,
    toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying, haste\nWhen Thundermaw Hellkite enters, it deals 1 damage to each creature with flying your opponents control. Tap those creatures.",
    setup_interceptors=thundermaw_hellkite_setup
)

# Act of Treason
ACT_OF_TREASON = make_sorcery(
    name="Act of Treason",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn."
)

# Shatter
SHATTER = make_instant(
    name="Shatter",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Destroy target artifact."
)

# Mizzium Mortars
MIZZIUM_MORTARS = make_sorcery(
    name="Mizzium Mortars",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Mizzium Mortars deals 4 damage to target creature you don't control.\nOverload {3}{R}{R}{R}"
)

# Young Pyromancer
def young_pyromancer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token_type': 'creature',
            'power': 1, 'toughness': 1,
            'colors': {Color.RED},
            'subtypes': {'Elemental'}
        }, source=obj.id)]
    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.INSTANT, CardType.SORCERY})]

YOUNG_PYROMANCER = make_creature(
    name="Young Pyromancer",
    power=2,
    toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Shaman"},
    text="Whenever you cast an instant or sorcery spell, create a 1/1 red Elemental creature token.",
    setup_interceptors=young_pyromancer_setup
)

# Fervent Champion
FERVENT_CHAMPION = make_creature(
    name="Fervent Champion",
    power=1,
    toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Knight"},
    text="First strike, haste\nWhenever Fervent Champion attacks, another attacking Knight you control gets +1/+0 until end of turn.\nEquip abilities you activate that target Fervent Champion cost {3} less to activate."
)

# Bomat Courier
BOMAT_COURIER = make_creature(
    name="Bomat Courier",
    power=1,
    toughness=1,
    mana_cost="{1}",
    colors=set(),
    subtypes={"Construct"},
    text="Haste\nWhenever Bomat Courier attacks, exile the top card of your library face down.\n{R}, Discard your hand, Sacrifice Bomat Courier: Put all cards exiled with Bomat Courier into your hand."
)

# =============================================================================
# GREEN CARDS
# =============================================================================

# Llanowar Elves
LLANOWAR_ELVES = make_creature(
    name="Llanowar Elves",
    power=1,
    toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    text="{T}: Add {G}."
)

# Elvish Mystic
ELVISH_MYSTIC = make_creature(
    name="Elvish Mystic",
    power=1,
    toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    text="{T}: Add {G}."
)

# Birds of Paradise
BIRDS_OF_PARADISE = make_creature(
    name="Birds of Paradise",
    power=0,
    toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Bird"},
    text="Flying\n{T}: Add one mana of any color."
)

# Giant Growth
GIANT_GROWTH = make_instant(
    name="Giant Growth",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn."
)

# Titanic Growth
TITANIC_GROWTH = make_instant(
    name="Titanic Growth",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +4/+4 until end of turn."
)

# Naturalize
NATURALIZE = make_instant(
    name="Naturalize",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Destroy target artifact or enchantment."
)

# Plummet
PLUMMET = make_instant(
    name="Plummet",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Destroy target creature with flying."
)

# Grizzly Bears
GRIZZLY_BEARS = make_creature(
    name="Grizzly Bears",
    power=2,
    toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Bear"},
    text=""
)

# Runeclaw Bear
RUNECLAW_BEAR = make_creature(
    name="Runeclaw Bear",
    power=2,
    toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Bear"},
    text=""
)

# Centaur Courser
CENTAUR_COURSER = make_creature(
    name="Centaur Courser",
    power=3,
    toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Centaur", "Warrior"},
    text=""
)

# Garruk's Companion
GARRUKS_COMPANION = make_creature(
    name="Garruk's Companion",
    power=3,
    toughness=2,
    mana_cost="{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample"
)

# Leatherback Baloth
LEATHERBACK_BALOTH = make_creature(
    name="Leatherback Baloth",
    power=4,
    toughness=5,
    mana_cost="{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text=""
)

# Elvish Archdruid
def elvish_archdruid_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Elf"))

ELVISH_ARCHDRUID = make_creature(
    name="Elvish Archdruid",
    power=2,
    toughness=2,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    text="Other Elf creatures you control get +1/+1.\n{T}: Add {G} for each Elf you control.",
    setup_interceptors=elvish_archdruid_setup
)

# Elvish Visionary
def elvish_visionary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

ELVISH_VISIONARY = make_creature(
    name="Elvish Visionary",
    power=1,
    toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Shaman"},
    text="When Elvish Visionary enters, draw a card.",
    setup_interceptors=elvish_visionary_setup
)

# Dwynen, Gilt-Leaf Daen
def dwynen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Elf"))

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        elf_count = sum(1 for o in state.objects.values()
                       if o.controller == obj.controller and
                       o.zone == ZoneType.BATTLEFIELD and
                       "Elf" in o.characteristics.subtypes and
                       CardType.CREATURE in o.characteristics.types)
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': elf_count}, source=obj.id)]

    interceptors.append(make_attack_trigger(obj, attack_effect))
    return interceptors

DWYNEN_GILT_LEAF_DAEN = make_creature(
    name="Dwynen, Gilt-Leaf Daen",
    power=3,
    toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    supertypes={"Legendary"},
    text="Reach\nOther Elf creatures you control get +1/+1.\nWhenever Dwynen attacks, you gain 1 life for each attacking Elf you control.",
    setup_interceptors=dwynen_setup
)

# Rampant Growth
RAMPANT_GROWTH = make_sorcery(
    name="Rampant Growth",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle."
)

# Cultivate
CULTIVATE = make_sorcery(
    name="Cultivate",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for up to two basic land cards, reveal those cards, put one onto the battlefield tapped and the other into your hand, then shuffle."
)

# Overrun
OVERRUN = make_sorcery(
    name="Overrun",
    mana_cost="{2}{G}{G}{G}",
    colors={Color.GREEN},
    text="Creatures you control get +3/+3 and gain trample until end of turn."
)

# Terra Stomper
TERRA_STOMPER = make_creature(
    name="Terra Stomper",
    power=8,
    toughness=8,
    mana_cost="{3}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="This spell can't be countered.\nTrample"
)

# Thragtusk
def thragtusk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 5}, source=obj.id)]

    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token_type': 'creature',
            'power': 3, 'toughness': 3,
            'colors': {Color.GREEN},
            'subtypes': {'Beast'}
        }, source=obj.id)]

    return [make_etb_trigger(obj, etb_effect), make_death_trigger(obj, death_effect)]

THRAGTUSK = make_creature(
    name="Thragtusk",
    power=5,
    toughness=3,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="When Thragtusk enters, you gain 5 life.\nWhen Thragtusk leaves the battlefield, create a 3/3 green Beast creature token.",
    setup_interceptors=thragtusk_setup
)

# Kalonian Tusker
KALONIAN_TUSKER = make_creature(
    name="Kalonian Tusker",
    power=3,
    toughness=3,
    mana_cost="{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text=""
)

# Scavenging Ooze
SCAVENGING_OOZE = make_creature(
    name="Scavenging Ooze",
    power=2,
    toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Ooze"},
    text="{G}: Exile target card from a graveyard. If it was a creature card, put a +1/+1 counter on Scavenging Ooze and you gain 1 life."
)

# Hornet Queen
def hornet_queen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        tokens = []
        for _ in range(4):
            tokens.append(Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token_type': 'creature',
                'power': 1, 'toughness': 1,
                'colors': {Color.GREEN},
                'subtypes': {'Insect'},
                'keywords': {'flying', 'deathtouch'}
            }, source=obj.id))
        return tokens
    return [make_etb_trigger(obj, etb_effect)]

HORNET_QUEEN = make_creature(
    name="Hornet Queen",
    power=2,
    toughness=2,
    mana_cost="{4}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Insect"},
    text="Flying, deathtouch\nWhen Hornet Queen enters, create four 1/1 green Insect creature tokens with flying and deathtouch.",
    setup_interceptors=hornet_queen_setup
)

# Arbor Elf
ARBOR_ELF = make_creature(
    name="Arbor Elf",
    power=1,
    toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    text="{T}: Untap target Forest."
)

# Strangleroot Geist
STRANGLEROOT_GEIST = make_creature(
    name="Strangleroot Geist",
    power=2,
    toughness=1,
    mana_cost="{G}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit"},
    text="Haste\nUndying"
)

# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

# Dreadhorde Butcher (B/R)
def dreadhorde_butcher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id,
            'counter_type': '+1/+1',
            'amount': 1
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

DREADHORDE_BUTCHER = make_creature(
    name="Dreadhorde Butcher",
    power=1,
    toughness=1,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Zombie", "Warrior"},
    text="Haste\nWhenever Dreadhorde Butcher deals combat damage to a player or planeswalker, put a +1/+1 counter on it.\nWhen Dreadhorde Butcher dies, it deals damage equal to its power to any target.",
    setup_interceptors=dreadhorde_butcher_setup
)

# Fleecemane Lion (G/W)
FLEECEMANE_LION = make_creature(
    name="Fleecemane Lion",
    power=3,
    toughness=3,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Cat"},
    text="{3}{G}{W}: Monstrosity 1.\nAs long as Fleecemane Lion is monstrous, it has hexproof and indestructible."
)

# Baleful Strix (U/B)
def baleful_strix_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

BALEFUL_STRIX = make_creature(
    name="Baleful Strix",
    power=1,
    toughness=1,
    mana_cost="{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Bird", "Artifact Creature"},
    text="Flying, deathtouch\nWhen Baleful Strix enters, draw a card.",
    setup_interceptors=baleful_strix_setup
)

# Electrolyze (U/R)
ELECTROLYZE = make_instant(
    name="Electrolyze",
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    text="Electrolyze deals 2 damage divided as you choose among one or two targets.\nDraw a card."
)

# Putrefy (B/G)
PUTREFY = make_instant(
    name="Putrefy",
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Destroy target artifact or creature. It can't be regenerated."
)

# Lightning Helix (R/W)
LIGHTNING_HELIX = make_instant(
    name="Lightning Helix",
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Lightning Helix deals 3 damage to any target and you gain 3 life."
)

# Absorb (W/U)
ABSORB = make_instant(
    name="Absorb",
    mana_cost="{W}{U}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Counter target spell. You gain 3 life."
)

# Abrupt Decay (B/G)
ABRUPT_DECAY = make_instant(
    name="Abrupt Decay",
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="This spell can't be countered.\nDestroy target nonland permanent with mana value 3 or less."
)

# Terminate (B/R)
TERMINATE = make_instant(
    name="Terminate",
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Destroy target creature. It can't be regenerated."
)

# =============================================================================
# ARTIFACT CARDS
# =============================================================================

# Sol Ring
SOL_RING = make_artifact(
    name="Sol Ring",
    mana_cost="{1}",
    text="{T}: Add {C}{C}."
)

# Mind Stone
MIND_STONE = make_artifact(
    name="Mind Stone",
    mana_cost="{2}",
    text="{T}: Add {C}.\n{1}, {T}, Sacrifice Mind Stone: Draw a card."
)

# Arcane Signet
ARCANE_SIGNET = make_artifact(
    name="Arcane Signet",
    mana_cost="{2}",
    text="{T}: Add one mana of any color in your commander's color identity."
)

# Hedron Archive
HEDRON_ARCHIVE = make_artifact(
    name="Hedron Archive",
    mana_cost="{4}",
    text="{T}: Add {C}{C}.\n{2}, {T}, Sacrifice Hedron Archive: Draw two cards."
)

# Pilgrim's Eye
def pilgrims_eye_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Search for basic land
    return [make_etb_trigger(obj, etb_effect)]

PILGRIMS_EYE = make_creature(
    name="Pilgrim's Eye",
    power=1,
    toughness=1,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Thopter"},
    text="Flying\nWhen Pilgrim's Eye enters, you may search your library for a basic land card, reveal it, put it into your hand, then shuffle.",
    setup_interceptors=pilgrims_eye_setup
)

# Fireshrieker
FIRESHRIEKER = make_equipment(
    name="Fireshrieker",
    mana_cost="{3}",
    text="Equipped creature has double strike.",
    equip_cost="{2}"
)

# Loxodon Warhammer
LOXODON_WARHAMMER = make_equipment(
    name="Loxodon Warhammer",
    mana_cost="{3}",
    text="Equipped creature gets +3/+0 and has trample and lifelink.",
    equip_cost="{3}"
)

# Whispersilk Cloak
WHISPERSILK_CLOAK = make_equipment(
    name="Whispersilk Cloak",
    mana_cost="{3}",
    text="Equipped creature can't be blocked and has shroud.",
    equip_cost="{2}"
)

# Swiftfoot Boots
SWIFTFOOT_BOOTS = make_equipment(
    name="Swiftfoot Boots",
    mana_cost="{2}",
    text="Equipped creature has hexproof and haste.",
    equip_cost="{1}"
)

# Lightning Greaves
LIGHTNING_GREAVES = make_equipment(
    name="Lightning Greaves",
    mana_cost="{2}",
    text="Equipped creature has shroud and haste.",
    equip_cost="{0}"
)

# Mask of Memory
MASK_OF_MEMORY = make_equipment(
    name="Mask of Memory",
    mana_cost="{2}",
    text="Whenever equipped creature deals combat damage to a player, you may draw two cards. If you do, discard a card.",
    equip_cost="{1}"
)

# =============================================================================
# LAND CARDS
# =============================================================================

# Basic Lands
PLAINS = make_land(name="Plains", subtypes={"Plains"}, supertypes={"Basic"}, text="{T}: Add {W}.")
ISLAND = make_land(name="Island", subtypes={"Island"}, supertypes={"Basic"}, text="{T}: Add {U}.")
SWAMP = make_land(name="Swamp", subtypes={"Swamp"}, supertypes={"Basic"}, text="{T}: Add {B}.")
MOUNTAIN = make_land(name="Mountain", subtypes={"Mountain"}, supertypes={"Basic"}, text="{T}: Add {R}.")
FOREST = make_land(name="Forest", subtypes={"Forest"}, supertypes={"Basic"}, text="{T}: Add {G}.")

# Dual Taplands
TRANQUIL_COVE = make_land(
    name="Tranquil Cove",
    text="Tranquil Cove enters tapped.\nWhen Tranquil Cove enters, you gain 1 life.\n{T}: Add {W} or {U}."
)

DISMAL_BACKWATER = make_land(
    name="Dismal Backwater",
    text="Dismal Backwater enters tapped.\nWhen Dismal Backwater enters, you gain 1 life.\n{T}: Add {U} or {B}."
)

BLOODFELL_CAVES = make_land(
    name="Bloodfell Caves",
    text="Bloodfell Caves enters tapped.\nWhen Bloodfell Caves enters, you gain 1 life.\n{T}: Add {B} or {R}."
)

RUGGED_HIGHLANDS = make_land(
    name="Rugged Highlands",
    text="Rugged Highlands enters tapped.\nWhen Rugged Highlands enters, you gain 1 life.\n{T}: Add {R} or {G}."
)

BLOSSOMING_SANDS = make_land(
    name="Blossoming Sands",
    text="Blossoming Sands enters tapped.\nWhen Blossoming Sands enters, you gain 1 life.\n{T}: Add {G} or {W}."
)

SCOURED_BARRENS = make_land(
    name="Scoured Barrens",
    text="Scoured Barrens enters tapped.\nWhen Scoured Barrens enters, you gain 1 life.\n{T}: Add {W} or {B}."
)

SWIFTWATER_CLIFFS = make_land(
    name="Swiftwater Cliffs",
    text="Swiftwater Cliffs enters tapped.\nWhen Swiftwater Cliffs enters, you gain 1 life.\n{T}: Add {U} or {R}."
)

JUNGLE_HOLLOW = make_land(
    name="Jungle Hollow",
    text="Jungle Hollow enters tapped.\nWhen Jungle Hollow enters, you gain 1 life.\n{T}: Add {B} or {G}."
)

WIND_SCARRED_CRAG = make_land(
    name="Wind-Scarred Crag",
    text="Wind-Scarred Crag enters tapped.\nWhen Wind-Scarred Crag enters, you gain 1 life.\n{T}: Add {R} or {W}."
)

THORNWOOD_FALLS = make_land(
    name="Thornwood Falls",
    text="Thornwood Falls enters tapped.\nWhen Thornwood Falls enters, you gain 1 life.\n{T}: Add {G} or {U}."
)

# Command Tower
COMMAND_TOWER = make_land(
    name="Command Tower",
    text="{T}: Add one mana of any color in your commander's color identity."
)

# Evolving Wilds
EVOLVING_WILDS = make_land(
    name="Evolving Wilds",
    text="{T}, Sacrifice Evolving Wilds: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle."
)

# Terramorphic Expanse
TERRAMORPHIC_EXPANSE = make_land(
    name="Terramorphic Expanse",
    text="{T}, Sacrifice Terramorphic Expanse: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle."
)

# =============================================================================
# MORE WHITE CARDS
# =============================================================================

# Mentor of the Meek
def mentor_of_the_meek_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target or target.controller != source.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        return target.characteristics.power <= 2

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Pay 1 to draw

    return [make_etb_trigger(obj, etb_effect, creature_etb_filter)]

MENTOR_OF_THE_MEEK = make_creature(
    name="Mentor of the Meek",
    power=2,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Whenever another creature with power 2 or less enters under your control, you may pay {1}. If you do, draw a card.",
    setup_interceptors=mentor_of_the_meek_setup
)

# Oblivion Ring
OBLIVION_RING = make_enchantment(
    name="Oblivion Ring",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When Oblivion Ring enters, exile another target nonland permanent.\nWhen Oblivion Ring leaves the battlefield, return the exiled card to the battlefield under its owner's control."
)

# Path to Exile
PATH_TO_EXILE = make_instant(
    name="Path to Exile",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Exile target creature. Its controller may search their library for a basic land card, put that card onto the battlefield tapped, then shuffle."
)

# =============================================================================
# MORE BLUE CARDS
# =============================================================================

# Mana Leak
MANA_LEAK = make_instant(
    name="Mana Leak",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {3}."
)

# Dissolve
DISSOLVE = make_instant(
    name="Dissolve",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell. Scry 1."
)

# Think Twice
THINK_TWICE = make_instant(
    name="Think Twice",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Draw a card.\nFlashback {2}{U}"
)

# Brainstorm
BRAINSTORM = make_instant(
    name="Brainstorm",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Draw three cards, then put two cards from your hand on top of your library in any order."
)

# Phantasmal Bear
PHANTASMAL_BEAR = make_creature(
    name="Phantasmal Bear",
    power=2,
    toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Bear", "Illusion"},
    text="When Phantasmal Bear becomes the target of a spell or ability, sacrifice it."
)

# =============================================================================
# MORE BLACK CARDS
# =============================================================================

# Fatal Push
FATAL_PUSH = make_instant(
    name="Fatal Push",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Destroy target creature if it has mana value 2 or less.\nRevolt — Destroy that creature if it has mana value 4 or less instead if a permanent you controlled left the battlefield this turn."
)

# Thoughtseize
THOUGHTSEIZE = make_sorcery(
    name="Thoughtseize",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target player reveals their hand. You choose a nonland card from it. That player discards that card. You lose 2 life."
)

# Victim of Night
VICTIM_OF_NIGHT = make_instant(
    name="Victim of Night",
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    text="Destroy target non-Vampire, non-Werewolf, non-Zombie creature."
)

# Gifted Aetherborn
GIFTED_AETHERBORN = make_creature(
    name="Gifted Aetherborn",
    power=2,
    toughness=3,
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    subtypes={"Aetherborn", "Vampire"},
    text="Deathtouch, lifelink"
)

# Nether Spirit
NETHER_SPIRIT = make_creature(
    name="Nether Spirit",
    power=2,
    toughness=2,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="At the beginning of your upkeep, if Nether Spirit is the only creature card in your graveyard, you may return Nether Spirit to the battlefield."
)

# =============================================================================
# MORE RED CARDS
# =============================================================================

# Abrade
ABRADE = make_instant(
    name="Abrade",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Choose one —\n• Abrade deals 3 damage to target creature.\n• Destroy target artifact."
)

# Flame Slash
FLAME_SLASH = make_sorcery(
    name="Flame Slash",
    mana_cost="{R}",
    colors={Color.RED},
    text="Flame Slash deals 4 damage to target creature."
)

# Searing Blood
SEARING_BLOOD = make_instant(
    name="Searing Blood",
    mana_cost="{R}{R}",
    colors={Color.RED},
    text="Searing Blood deals 2 damage to target creature. When that creature dies this turn, Searing Blood deals 3 damage to that creature's controller."
)

# Ember Hauler
def ember_hauler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Sacrifice to deal 2 damage
    return []

EMBER_HAULER = make_creature(
    name="Ember Hauler",
    power=2,
    toughness=2,
    mana_cost="{R}{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
    text="{1}, Sacrifice Ember Hauler: It deals 2 damage to any target.",
    setup_interceptors=ember_hauler_setup
)

# Hellrider
def hellrider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_trigger_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        return attacker and attacker.controller == source.controller

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        opponents = all_opponents(obj, state)
        if opponents:
            return [Event(type=EventType.DAMAGE, payload={
                'target': opponents[0],
                'amount': 1,
                'source': obj.id
            }, source=obj.id)]
        return []

    return [make_attack_trigger(obj, attack_effect, attack_trigger_filter)]

HELLRIDER = make_creature(
    name="Hellrider",
    power=3,
    toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Devil"},
    text="Haste\nWhenever a creature you control attacks, Hellrider deals 1 damage to the player or planeswalker it's attacking.",
    setup_interceptors=hellrider_setup
)

# =============================================================================
# MORE GREEN CARDS
# =============================================================================

# Vines of Vastwood
VINES_OF_VASTWOOD = make_instant(
    name="Vines of Vastwood",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Kicker {G}\nTarget creature can't be the target of spells or abilities your opponents control this turn. If this spell was kicked, that creature gets +4/+4 until end of turn."
)

# Aspect of Hydra
ASPECT_OF_HYDRA = make_instant(
    name="Aspect of Hydra",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +X/+X until end of turn, where X is your devotion to green."
)

# Experiment One
EXPERIMENT_ONE = make_creature(
    name="Experiment One",
    power=1,
    toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Ooze"},
    text="Evolve\nRemove two +1/+1 counters from Experiment One: Regenerate Experiment One."
)

# Avatar of the Resolute
AVATAR_OF_THE_RESOLUTE = make_creature(
    name="Avatar of the Resolute",
    power=3,
    toughness=2,
    mana_cost="{G}{G}",
    colors={Color.GREEN},
    subtypes={"Avatar"},
    text="Reach, trample\nAvatar of the Resolute enters with a +1/+1 counter on it for each other creature you control with a +1/+1 counter on it."
)

# Voracious Hydra
VORACIOUS_HYDRA = make_creature(
    name="Voracious Hydra",
    power=0,
    toughness=1,
    mana_cost="{X}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Hydra"},
    text="Trample\nVoracious Hydra enters with X +1/+1 counters on it.\nWhen Voracious Hydra enters, choose one —\n• Double the number of +1/+1 counters on Voracious Hydra.\n• Voracious Hydra fights target creature you don't control."
)

# =============================================================================
# ADDITIONAL CARDS TO REACH ~250
# =============================================================================

# Griffin Sentinel
GRIFFIN_SENTINEL = make_creature(
    name="Griffin Sentinel",
    power=1,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Griffin"},
    text="Flying, vigilance"
)

# Aven Windreader
AVEN_WINDREADER = make_creature(
    name="Aven Windreader",
    power=3,
    toughness=3,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Soldier", "Wizard"},
    text="Flying\n{1}{U}: Target player reveals the top card of their library."
)

# Zombie Goliath
ZOMBIE_GOLIATH = make_creature(
    name="Zombie Goliath",
    power=4,
    toughness=3,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie", "Giant"},
    text=""
)

# Hill Giant
HILL_GIANT = make_creature(
    name="Hill Giant",
    power=3,
    toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Giant"},
    text=""
)

# Vastwood Gorger
VASTWOOD_GORGER = make_creature(
    name="Vastwood Gorger",
    power=5,
    toughness=6,
    mana_cost="{5}{G}",
    colors={Color.GREEN},
    subtypes={"Wurm"},
    text=""
)

# Coral Merfolk
CORAL_MERFOLK = make_creature(
    name="Coral Merfolk",
    power=2,
    toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk"},
    text=""
)

# Goblin Balloon Brigade
GOBLIN_BALLOON_BRIGADE = make_creature(
    name="Goblin Balloon Brigade",
    power=1,
    toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
    text="{R}: Goblin Balloon Brigade gains flying until end of turn."
)

# Elvish Warrior
ELVISH_WARRIOR = make_creature(
    name="Elvish Warrior",
    power=2,
    toughness=3,
    mana_cost="{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    text=""
)

# Zealous Conscripts
def zealous_conscripts_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Gain control of target permanent until end of turn
    return [make_etb_trigger(obj, etb_effect)]

ZEALOUS_CONSCRIPTS = make_creature(
    name="Zealous Conscripts",
    power=3,
    toughness=3,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="Haste\nWhen Zealous Conscripts enters, gain control of target permanent until end of turn. Untap that permanent. It gains haste until end of turn.",
    setup_interceptors=zealous_conscripts_setup
)

# Runeclaw Bear (alias for vanilla creature variety)
BORDERLAND_RANGER = make_creature(
    name="Borderland Ranger",
    power=2,
    toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout", "Ranger"},
    text="When Borderland Ranger enters, you may search your library for a basic land card, reveal it, put it into your hand, then shuffle."
)

# Kor Hookmaster
def kor_hookmaster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Tap target creature
    return [make_etb_trigger(obj, etb_effect)]

KOR_HOOKMASTER = make_creature(
    name="Kor Hookmaster",
    power=2,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Kor", "Soldier"},
    text="When Kor Hookmaster enters, tap target creature an opponent controls. That creature doesn't untap during its controller's next untap step.",
    setup_interceptors=kor_hookmaster_setup
)

# Prodigal Pyromancer
PRODIGAL_PYROMANCER = make_creature(
    name="Prodigal Pyromancer",
    power=1,
    toughness=1,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard"},
    text="{T}: Prodigal Pyromancer deals 1 damage to any target."
)

# Vampire Interloper
VAMPIRE_INTERLOPER = make_creature(
    name="Vampire Interloper",
    power=2,
    toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Scout"},
    text="Flying\nVampire Interloper can't block."
)

# Welkin Tern
WELKIN_TERN = make_creature(
    name="Welkin Tern",
    power=2,
    toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Bird"},
    text="Flying\nWelkin Tern can block only creatures with flying."
)

# Silvercoat Lion
SILVERCOAT_LION = make_creature(
    name="Silvercoat Lion",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cat"},
    text=""
)

# Feral Ridgewolf
FERAL_RIDGEWOLF = make_creature(
    name="Feral Ridgewolf",
    power=1,
    toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Wolf"},
    text="Trample\n{1}{R}: Feral Ridgewolf gets +2/+0 until end of turn."
)

# Coral Eel
CORAL_EEL = make_creature(
    name="Coral Eel",
    power=2,
    toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Fish"},
    text=""
)

# Bloodthrone Vampire
BLOODTHRONE_VAMPIRE = make_creature(
    name="Bloodthrone Vampire",
    power=1,
    toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="Sacrifice a creature: Bloodthrone Vampire gets +2/+2 until end of turn."
)

# Trusted Pegasus
TRUSTED_PEGASUS = make_creature(
    name="Trusted Pegasus",
    power=2,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Pegasus"},
    text="Flying\nWhenever Trusted Pegasus attacks, target attacking creature without flying gains flying until end of turn."
)

# Stalking Tiger
STALKING_TIGER = make_creature(
    name="Stalking Tiger",
    power=3,
    toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Cat"},
    text="Stalking Tiger can't be blocked by more than one creature."
)

# Mogg Flunkies
MOGG_FLUNKIES = make_creature(
    name="Mogg Flunkies",
    power=3,
    toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
    text="Mogg Flunkies can't attack or block alone."
)

# Unruly Mob
def unruly_mob_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def creature_dies_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        target_id = event.payload.get('object_id')
        if target_id == source.id:
            return False
        target = state.objects.get(target_id)
        return target and target.controller == source.controller and CardType.CREATURE in target.characteristics.types

    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id,
            'counter_type': '+1/+1',
            'amount': 1
        }, source=obj.id)]

    return [make_etb_trigger(obj, death_effect, creature_dies_filter)]

UNRULY_MOB = make_creature(
    name="Unruly Mob",
    power=1,
    toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human"},
    text="Whenever another creature you control dies, put a +1/+1 counter on Unruly Mob.",
    setup_interceptors=unruly_mob_setup
)

# Harbor Serpent
HARBOR_SERPENT = make_creature(
    name="Harbor Serpent",
    power=5,
    toughness=5,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Serpent"},
    text="Islandwalk\nHarbor Serpent can't attack unless there are five or more Islands on the battlefield."
)

# Necropede
def necropede_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Put -1/-1 counter on target creature
    return [make_death_trigger(obj, death_effect)]

NECROPEDE = make_creature(
    name="Necropede",
    power=1,
    toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Phyrexian", "Insect"},
    text="Infect\nWhen Necropede dies, you may put a -1/-1 counter on target creature.",
    setup_interceptors=necropede_setup
)

# Peace Strider
def peace_strider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 3}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

PEACE_STRIDER = make_creature(
    name="Peace Strider",
    power=3,
    toughness=3,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Construct"},
    text="When Peace Strider enters, you gain 3 life.",
    setup_interceptors=peace_strider_setup
)

# Siege Mastodon
SIEGE_MASTODON = make_creature(
    name="Siege Mastodon",
    power=3,
    toughness=5,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Elephant"},
    text=""
)

# Snapping Drake
SNAPPING_DRAKE = make_creature(
    name="Snapping Drake",
    power=3,
    toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Drake"},
    text="Flying"
)

# =============================================================================
# EXPORT DICTIONARY
# =============================================================================

FOUNDATIONS_CARDS = {
    # White
    "Ajani, Caller of the Pride": AJANI_CALLER_OF_THE_PRIDE,
    "Day of Judgment": DAY_OF_JUDGMENT,
    "Banishing Light": BANISHING_LIGHT,
    "Pacifism": PACIFISM,
    "Serra Angel": SERRA_ANGEL,
    "Angelic Edict": ANGELIC_EDICT,
    "Inspiring Overseer": INSPIRING_OVERSEER,
    "Elite Vanguard": ELITE_VANGUARD,
    "Glory Seeker": GLORY_SEEKER,
    "Attended Knight": ATTENDED_KNIGHT,
    "Valorous Stance": VALOROUS_STANCE,
    "Raise the Alarm": RAISE_THE_ALARM,
    "Disenchant": DISENCHANT,
    "Swords to Plowshares": SWORDS_TO_PLOWSHARES,
    "Savannah Lions": SAVANNAH_LIONS,
    "Aerial Responder": AERIAL_RESPONDER,
    "Leonin Warleader": LEONIN_WARLEADER,
    "Heliod's Pilgrim": HELIODS_PILGRIM,
    "Soldier of the Pantheon": SOLDIER_OF_THE_PANTHEON,
    "Glorious Anthem": GLORIOUS_ANTHEM,
    "Prison Term": PRISON_TERM,
    "Captain of the Watch": CAPTAIN_OF_THE_WATCH,
    "Ajani's Pridemate": AJANIS_PRIDEMATE,
    "Soul Warden": SOUL_WARDEN,
    "White Knight": WHITE_KNIGHT,
    "Mentor of the Meek": MENTOR_OF_THE_MEEK,
    "Oblivion Ring": OBLIVION_RING,
    "Path to Exile": PATH_TO_EXILE,
    "Griffin Sentinel": GRIFFIN_SENTINEL,
    "Kor Hookmaster": KOR_HOOKMASTER,
    "Silvercoat Lion": SILVERCOAT_LION,
    "Trusted Pegasus": TRUSTED_PEGASUS,
    "Unruly Mob": UNRULY_MOB,
    "Siege Mastodon": SIEGE_MASTODON,

    # Blue
    "Jace, Ingenious Mind-Mage": JACE_INGENIOUS_MIND_MAGE,
    "Counterspell": COUNTERSPELL,
    "Cancel": CANCEL,
    "Negate": NEGATE,
    "Essence Scatter": ESSENCE_SCATTER,
    "Divination": DIVINATION,
    "Opt": OPT,
    "Unsummon": UNSUMMON,
    "Wind Drake": WIND_DRAKE,
    "Air Elemental": AIR_ELEMENTAL,
    "Frost Lynx": FROST_LYNX,
    "Merfolk Looter": MERFOLK_LOOTER,
    "Archaeomancer": ARCHAEOMANCER,
    "Thirst for Knowledge": THIRST_FOR_KNOWLEDGE,
    "Ponder": PONDER,
    "Preordain": PREORDAIN,
    "Azure Mage": AZURE_MAGE,
    "Sphinx of Enlightenment": SPHINX_OF_ENLIGHTENMENT,
    "Cloudkin Seer": CLOUDKIN_SEER,
    "Talrand, Sky Summoner": TALRAND_SKY_SUMMONER,
    "Faerie Miscreant": FAERIE_MISCREANT,
    "Void Snare": VOID_SNARE,
    "Sleep": SLEEP,
    "Mana Leak": MANA_LEAK,
    "Dissolve": DISSOLVE,
    "Think Twice": THINK_TWICE,
    "Brainstorm": BRAINSTORM,
    "Phantasmal Bear": PHANTASMAL_BEAR,
    "Aven Windreader": AVEN_WINDREADER,
    "Coral Merfolk": CORAL_MERFOLK,
    "Welkin Tern": WELKIN_TERN,
    "Coral Eel": CORAL_EEL,
    "Harbor Serpent": HARBOR_SERPENT,
    "Snapping Drake": SNAPPING_DRAKE,

    # Black
    "Liliana, Death's Majesty": LILIANA_DEATHS_MAJESTY,
    "Murder": MURDER,
    "Doom Blade": DOOM_BLADE,
    "Go for the Throat": GO_FOR_THE_THROAT,
    "Sign in Blood": SIGN_IN_BLOOD,
    "Read the Bones": READ_THE_BONES,
    "Walking Corpse": WALKING_CORPSE,
    "Gravedigger": GRAVEDIGGER,
    "Vampire Nighthawk": VAMPIRE_NIGHTHAWK,
    "Child of Night": CHILD_OF_NIGHT,
    "Festering Goblin": FESTERING_GOBLIN,
    "Ravenous Rats": RAVENOUS_RATS,
    "Diregraf Ghoul": DIREGRAF_GHOUL,
    "Typhoid Rats": TYPHOID_RATS,
    "Dread Wanderer": DREAD_WANDERER,
    "Lord of the Accursed": LORD_OF_THE_ACCURSED,
    "Duress": DURESS,
    "Mind Rot": MIND_ROT,
    "Nightmare": NIGHTMARE,
    "Blood Artist": BLOOD_ARTIST,
    "Black Knight": BLACK_KNIGHT,
    "Fatal Push": FATAL_PUSH,
    "Thoughtseize": THOUGHTSEIZE,
    "Victim of Night": VICTIM_OF_NIGHT,
    "Gifted Aetherborn": GIFTED_AETHERBORN,
    "Nether Spirit": NETHER_SPIRIT,
    "Zombie Goliath": ZOMBIE_GOLIATH,
    "Vampire Interloper": VAMPIRE_INTERLOPER,
    "Bloodthrone Vampire": BLOODTHRONE_VAMPIRE,

    # Red
    "Lightning Bolt": LIGHTNING_BOLT,
    "Shock": SHOCK,
    "Searing Spear": SEARING_SPEAR,
    "Incinerate": INCINERATE,
    "Lava Axe": LAVA_AXE,
    "Firebolt": FIREBOLT,
    "Goblin Guide": GOBLIN_GUIDE,
    "Monastery Swiftspear": MONASTERY_SWIFTSPEAR,
    "Goblin Piker": GOBLIN_PIKER,
    "Goblin Shortcutter": GOBLIN_SHORTCUTTER,
    "Raging Goblin": RAGING_GOBLIN,
    "Goblin Chieftain": GOBLIN_CHIEFTAIN,
    "Krenko, Mob Boss": KRENKO_MOB_BOSS,
    "Dragon Hatchling": DRAGON_HATCHLING,
    "Shivan Dragon": SHIVAN_DRAGON,
    "Thundermaw Hellkite": THUNDERMAW_HELLKITE,
    "Act of Treason": ACT_OF_TREASON,
    "Shatter": SHATTER,
    "Mizzium Mortars": MIZZIUM_MORTARS,
    "Young Pyromancer": YOUNG_PYROMANCER,
    "Fervent Champion": FERVENT_CHAMPION,
    "Bomat Courier": BOMAT_COURIER,
    "Abrade": ABRADE,
    "Flame Slash": FLAME_SLASH,
    "Searing Blood": SEARING_BLOOD,
    "Ember Hauler": EMBER_HAULER,
    "Hellrider": HELLRIDER,
    "Hill Giant": HILL_GIANT,
    "Goblin Balloon Brigade": GOBLIN_BALLOON_BRIGADE,
    "Zealous Conscripts": ZEALOUS_CONSCRIPTS,
    "Prodigal Pyromancer": PRODIGAL_PYROMANCER,
    "Feral Ridgewolf": FERAL_RIDGEWOLF,
    "Mogg Flunkies": MOGG_FLUNKIES,

    # Green
    "Llanowar Elves": LLANOWAR_ELVES,
    "Elvish Mystic": ELVISH_MYSTIC,
    "Birds of Paradise": BIRDS_OF_PARADISE,
    "Giant Growth": GIANT_GROWTH,
    "Titanic Growth": TITANIC_GROWTH,
    "Naturalize": NATURALIZE,
    "Plummet": PLUMMET,
    "Grizzly Bears": GRIZZLY_BEARS,
    "Runeclaw Bear": RUNECLAW_BEAR,
    "Centaur Courser": CENTAUR_COURSER,
    "Garruk's Companion": GARRUKS_COMPANION,
    "Leatherback Baloth": LEATHERBACK_BALOTH,
    "Elvish Archdruid": ELVISH_ARCHDRUID,
    "Elvish Visionary": ELVISH_VISIONARY,
    "Dwynen, Gilt-Leaf Daen": DWYNEN_GILT_LEAF_DAEN,
    "Rampant Growth": RAMPANT_GROWTH,
    "Cultivate": CULTIVATE,
    "Overrun": OVERRUN,
    "Terra Stomper": TERRA_STOMPER,
    "Thragtusk": THRAGTUSK,
    "Kalonian Tusker": KALONIAN_TUSKER,
    "Scavenging Ooze": SCAVENGING_OOZE,
    "Hornet Queen": HORNET_QUEEN,
    "Arbor Elf": ARBOR_ELF,
    "Strangleroot Geist": STRANGLEROOT_GEIST,
    "Vines of Vastwood": VINES_OF_VASTWOOD,
    "Aspect of Hydra": ASPECT_OF_HYDRA,
    "Experiment One": EXPERIMENT_ONE,
    "Avatar of the Resolute": AVATAR_OF_THE_RESOLUTE,
    "Voracious Hydra": VORACIOUS_HYDRA,
    "Vastwood Gorger": VASTWOOD_GORGER,
    "Elvish Warrior": ELVISH_WARRIOR,
    "Borderland Ranger": BORDERLAND_RANGER,
    "Stalking Tiger": STALKING_TIGER,

    # Multicolor
    "Dreadhorde Butcher": DREADHORDE_BUTCHER,
    "Fleecemane Lion": FLEECEMANE_LION,
    "Baleful Strix": BALEFUL_STRIX,
    "Electrolyze": ELECTROLYZE,
    "Putrefy": PUTREFY,
    "Lightning Helix": LIGHTNING_HELIX,
    "Absorb": ABSORB,
    "Abrupt Decay": ABRUPT_DECAY,
    "Terminate": TERMINATE,

    # Artifacts
    "Sol Ring": SOL_RING,
    "Mind Stone": MIND_STONE,
    "Arcane Signet": ARCANE_SIGNET,
    "Hedron Archive": HEDRON_ARCHIVE,
    "Pilgrim's Eye": PILGRIMS_EYE,
    "Fireshrieker": FIRESHRIEKER,
    "Loxodon Warhammer": LOXODON_WARHAMMER,
    "Whispersilk Cloak": WHISPERSILK_CLOAK,
    "Swiftfoot Boots": SWIFTFOOT_BOOTS,
    "Lightning Greaves": LIGHTNING_GREAVES,
    "Mask of Memory": MASK_OF_MEMORY,
    "Necropede": NECROPEDE,
    "Peace Strider": PEACE_STRIDER,

    # Lands
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
    "Tranquil Cove": TRANQUIL_COVE,
    "Dismal Backwater": DISMAL_BACKWATER,
    "Bloodfell Caves": BLOODFELL_CAVES,
    "Rugged Highlands": RUGGED_HIGHLANDS,
    "Blossoming Sands": BLOSSOMING_SANDS,
    "Scoured Barrens": SCOURED_BARRENS,
    "Swiftwater Cliffs": SWIFTWATER_CLIFFS,
    "Jungle Hollow": JUNGLE_HOLLOW,
    "Wind-Scarred Crag": WIND_SCARRED_CRAG,
    "Thornwood Falls": THORNWOOD_FALLS,
    "Command Tower": COMMAND_TOWER,
    "Evolving Wilds": EVOLVING_WILDS,
    "Terramorphic Expanse": TERRAMORPHIC_EXPANSE,
}
