"""
Attack on Titan (AOT) Card Implementations

Set featuring ~250 cards.
Mechanics: ODM Gear, Titan Shift, Wall
"""

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, ObjectState, CardDefinition,
    make_creature, make_instant, make_enchantment,
    new_id, get_power, get_toughness
)
from src.engine.abilities import (
    TriggeredAbility, StaticAbility,
    ETBTrigger, DeathTrigger, AttackTrigger, BlockTrigger,
    GainLife, LoseLife, DrawCards, Scry, CompositeEffect,
    PTBoost, KeywordGrant,
    OtherCreaturesYouControlFilter, CreaturesYouControlFilter,
    CreaturesWithSubtypeFilter, SelfTarget, AnotherCreature,
    CreatureWithSubtype,
)
from typing import Optional, Callable


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def make_sorcery(name: str, mana_cost: str, colors: set, text: str, subtypes: set = None, supertypes: set = None, resolve=None):
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


def make_artifact(name: str, mana_cost: str, text: str, subtypes: set = None, supertypes: set = None, abilities=None):
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
        abilities=abilities
    )


def make_equipment(name: str, mana_cost: str, text: str, equip_cost: str, subtypes: set = None, supertypes: set = None, abilities=None):
    base_subtypes = {"Equipment"}
    if subtypes:
        base_subtypes.update(subtypes)
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            subtypes=base_subtypes,
            supertypes=supertypes or set(),
            mana_cost=mana_cost
        ),
        text=f"{text}\nEquip {equip_cost}",
        abilities=abilities
    )


def make_land(name: str, text: str = "", subtypes: set = None, supertypes: set = None):
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
# AOT KEYWORD MECHANICS
# =============================================================================

def make_odm_gear_bonus(source_obj: GameObject, equipped_creature_id: str) -> list[Interceptor]:
    """ODM Gear - Equipped creature gains flying and first strike."""
    from src.cards.interceptor_helpers import make_keyword_grant
    def is_equipped(target: GameObject, state: GameState) -> bool:
        return target.id == equipped_creature_id

    return [make_keyword_grant(source_obj, ['flying', 'first_strike'], is_equipped)]


def make_titan_shift(source_obj: GameObject, titan_power: int, titan_toughness: int, shift_cost_life: int = 3) -> Interceptor:
    """Titan Shift - Pay life to transform into Titan form with boosted stats."""
    def shift_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ACTIVATE:
            return False
        return (event.payload.get('source') == source_obj.id and
                event.payload.get('ability') == 'titan_shift')

    def shift_handler(event: Event, state: GameState) -> InterceptorResult:
        life_payment = Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': source_obj.controller, 'amount': -shift_cost_life},
            source=source_obj.id
        )
        transform_event = Event(
            type=EventType.COUNTER_ADDED,
            payload={
                'object_id': source_obj.id,
                'counter_type': 'titan_form',
                'power': titan_power,
                'toughness': titan_toughness,
                'duration': 'end_of_turn'
            },
            source=source_obj.id
        )
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[life_payment, transform_event]
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=shift_filter,
        handler=shift_handler,
        duration='while_on_battlefield'
    )


def make_wall_defense(source_obj: GameObject, toughness_bonus: int) -> list[Interceptor]:
    """Wall - Grants defender and bonus toughness to itself."""
    from src.cards.interceptor_helpers import make_keyword_grant, make_static_pt_boost
    def is_self(target: GameObject, state: GameState) -> bool:
        return target.id == source_obj.id

    interceptors = []
    interceptors.append(make_keyword_grant(source_obj, ['defender'], is_self))
    interceptors.extend(make_static_pt_boost(source_obj, 0, toughness_bonus, is_self))
    return interceptors


# =============================================================================
# WHITE CARDS - SURVEY CORPS, HUMANITY'S HOPE
# =============================================================================

# --- Legendary Creatures ---

EREN_YEAGER_SCOUT = make_creature(
    name="Eren Yeager, Survey Corps",
    power=3, toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=AttackTrigger(),
            effect=CompositeEffect([])  # Complex boost effect - kept as placeholder
        )
    ]
)


MIKASA_ACKERMAN = make_creature(
    name="Mikasa Ackerman, Humanity's Strongest",
    power=4, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier", "Ackerman"},
    supertypes={"Legendary"},
    # First strike, vigilance, protection from Titans - keywords handled separately
)


ARMIN_ARLERT = make_creature(
    name="Armin Arlert, Tactician",
    power=1, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Scout", "Advisor"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=CompositeEffect([Scry(2), DrawCards(1)])
        )
    ]
)


LEVI_ACKERMAN = make_creature(
    name="Levi Ackerman, Captain",
    power=4, toughness=4,
    mana_cost="{2}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier", "Ackerman"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter(subtype="Scout", include_self=False)
        )
    ]
)


ERWIN_SMITH = make_creature(
    name="Erwin Smith, Commander",
    power=3, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Noble"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=AttackTrigger(),
            effect=CompositeEffect([])  # Scouts gain indestructible - complex effect
        )
    ]
)


HANGE_ZOE = make_creature(
    name="Hange Zoe, Researcher",
    power=2, toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Scout", "Artificer"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=DeathTrigger(target=CreatureWithSubtype(subtype="Titan", you_control=False)),
            effect=DrawCards(1)
        )
    ]
)


# --- Regular Creatures ---

SURVEY_CORPS_RECRUIT = make_creature(
    name="Survey Corps Recruit",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=GainLife(2)
        )
    ]
)


SURVEY_CORPS_VETERAN = make_creature(
    name="Survey Corps Veteran",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    # First strike, combat damage trigger - keywords handled separately
)


GARRISON_SOLDIER = make_creature(
    name="Garrison Soldier",
    power=1, toughness=4,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    abilities=[
        TriggeredAbility(
            trigger=BlockTrigger(),
            effect=GainLife(2)
        )
    ]
)


MILITARY_POLICE_OFFICER = make_creature(
    name="Military Police Officer",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Noble"},
    # Lifelink - keyword handled separately
)


def wall_defender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """High toughness defender"""
    return make_wall_defense(obj, 2)

WALL_DEFENDER = make_creature(
    name="Wall Defender",
    power=0, toughness=6,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Wall"},
    setup_interceptors=wall_defender_setup
)


TRAINING_CORPS_CADET = make_creature(
    name="Training Corps Cadet",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    # Death trigger search - complex effect
)


HISTORIA_REISS = make_creature(
    name="Historia Reiss, True Queen",
    power=2, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter(subtype="Human", include_self=False)
        )
    ]
)


SASHA_BLOUSE = make_creature(
    name="Sasha Blouse, Hunter",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    # Reach, ETB create Food token - complex effect
)


CONNIE_SPRINGER = make_creature(
    name="Connie Springer, Loyal Friend",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    # Haste, death trigger - complex effect
)


JEAN_KIRSTEIN = make_creature(
    name="Jean Kirstein, Natural Leader",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=KeywordGrant(["vigilance"]),
            filter=CreaturesWithSubtypeFilter(subtype="Scout", include_self=False)
        )
    ]
)


MICHE_ZACHARIAS = make_creature(
    name="Miche Zacharias, Squad Leader",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    # Vigilance, can block additional creature - complex effect
)


PETRA_RAL = make_creature(
    name="Petra Ral, Levi Squad",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    # Flying, death trigger - complex effect
)


OLUO_BOZADO = make_creature(
    name="Oluo Bozado, Levi Squad",
    power=3, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    # First strike, conditional boost - complex effect
)


SQUAD_CAPTAIN = make_creature(
    name="Squad Captain",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    # ETB create token - complex effect
)


WALL_GARRISON_ELITE = make_creature(
    name="Wall Garrison Elite",
    power=2, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    # Defender, vigilance, activated ability - complex effect
)


INTERIOR_POLICE = make_creature(
    name="Interior Police",
    power=2, toughness=2,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Rogue"},
    # Flash, ETB exile - complex effect
)


SHIGANSHINA_CITIZEN = make_creature(
    name="Shiganshina Citizen",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    abilities=[
        TriggeredAbility(
            trigger=DeathTrigger(),
            effect=GainLife(2)
        )
    ]
)


ELDIAN_REFUGEE = make_creature(
    name="Eldian Refugee",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    # ETB return from graveyard - complex effect
)


WALL_CULTIST = make_creature(
    name="Wall Cultist",
    power=0, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    # Defender, activated ability - complex effect
)


HORSE_MOUNTED_SCOUT = make_creature(
    name="Horse Mounted Scout",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    # Haste, evasion - complex effect
)


# --- Instants ---

DEVOTED_HEART = make_instant(
    name="Devoted Heart",
    mana_cost="{W}",
    colors={Color.WHITE},
    # Complex conditional effect
)


SURVEY_CORPS_CHARGE = make_instant(
    name="Survey Corps Charge",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    # Complex pump effect
)


WALL_DEFENSE = make_instant(
    name="Wall Defense",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    # Complex pump effect
)


HUMANITYS_HOPE = make_instant(
    name="Humanity's Hope",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    # Exile + life gain
)


SALUTE_OF_HEARTS = make_instant(
    name="Salute of Hearts",
    mana_cost="{W}",
    colors={Color.WHITE},
    # Complex conditional effect
)


STRATEGIC_RETREAT = make_instant(
    name="Strategic Retreat",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    # Bounce + life gain
)


FORMATION_BREAK = make_instant(
    name="Formation Break",
    mana_cost="{W}",
    colors={Color.WHITE},
    # Grant flying + draw
)


GARRISON_REINFORCEMENTS = make_instant(
    name="Garrison Reinforcements",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    # Create tokens
)


# --- Sorceries ---

SURVEY_MISSION = make_sorcery(
    name="Survey Mission",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Create four 1/1 white Human Scout Soldier creature tokens with vigilance."
)


EVACUATION_ORDER = make_sorcery(
    name="Evacuation Order",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Return all creatures to their owners' hands."
)


WALL_RECONSTRUCTION = make_sorcery(
    name="Wall Reconstruction",
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    text="Destroy all creatures with power 4 or greater. You gain 2 life for each creature destroyed this way."
)


TRAINING_EXERCISE = make_sorcery(
    name="Training Exercise",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature becomes a Scout in addition to its other types and gets +1/+1 until end of turn. Draw a card."
)


# --- Enchantments ---

SURVEY_CORPS_BANNER = make_enchantment(
    name="Survey Corps Banner",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter(subtype="Scout")
        )
    ]
)


WINGS_OF_FREEDOM = make_enchantment(
    name="Wings of Freedom",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    abilities=[
        StaticAbility(
            effect=KeywordGrant(["flying"]),
            filter=CreaturesWithSubtypeFilter(subtype="Scout")
        )
    ]
)


WALL_FAITH = make_enchantment(
    name="Wall Faith",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    # Upkeep trigger + static boost - complex effect
)


# =============================================================================
# BLUE CARDS - STRATEGY, PLANNING, INTELLIGENCE
# =============================================================================

# --- Legendary Creatures ---

ARMIN_COLOSSAL_TITAN = make_creature(
    name="Armin, Colossal Titan",
    power=10, toughness=10,
    mana_cost="{5}{U}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    # Trample, ETB each opponent sacrifices - complex effect
)


ERWIN_GAMBIT = make_creature(
    name="Erwin Smith, The Gambit",
    power=2, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout", "Noble"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),  # Actually spell cast trigger, simplified
            effect=Scry(1)
        )
    ]
)


PIECK_FINGER = make_creature(
    name="Pieck Finger, Cart Titan",
    power=3, toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    # Can't be blocked, activated ability - complex effect
)


# --- Regular Creatures ---

INTELLIGENCE_OFFICER = make_creature(
    name="Intelligence Officer",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout", "Advisor"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=Scry(2)
        )
    ]
)


MARLEYAN_SPY = make_creature(
    name="Marleyan Spy",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    # Can't be blocked, combat damage draw - complex effect
)


SURVEY_CARTOGRAPHER = make_creature(
    name="Survey Cartographer",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout"},
    # Activated scry - complex effect
)


TITAN_RESEARCHER = make_creature(
    name="Titan Researcher",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Artificer"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(target=CreatureWithSubtype(subtype="Titan", you_control=False)),
            effect=DrawCards(1)
        )
    ]
)


STRATEGIC_ADVISOR = make_creature(
    name="Strategic Advisor",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Advisor"},
    # Combat trigger grant flying - complex effect
)


WALL_ARCHITECT = make_creature(
    name="Wall Architect",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Artificer"},
    # ETB create Wall token - complex effect
)


MILITARY_TACTICIAN = make_creature(
    name="Military Tactician",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Soldier", "Advisor"},
    # Flash, ETB tap - complex effect
)


SIGNAL_CORPS_OPERATOR = make_creature(
    name="Signal Corps Operator",
    power=1, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Soldier"},
    # Activated draw - complex effect
)


SUPPLY_CORPS_QUARTERMASTER = make_creature(
    name="Supply Corps Quartermaster",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Soldier"},
    # Cost reduction - complex effect
)


COASTAL_SCOUT = make_creature(
    name="Coastal Scout",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout"},
    # Flying, combat damage scry - complex effect
)


FORMATION_ANALYST = make_creature(
    name="Formation Analyst",
    power=0, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Advisor"},
    # Defender, activated look - complex effect
)


# --- Instants ---

STRATEGIC_ANALYSIS = make_instant(
    name="Strategic Analysis",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    # Draw two
)


TACTICAL_RETREAT = make_instant(
    name="Tactical Retreat",
    mana_cost="{U}",
    colors={Color.BLUE},
    # Bounce + scry
)


FORMATION_SHIFT = make_instant(
    name="Formation Shift",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    # Bounce + draw
)


COUNTER_STRATEGY = make_instant(
    name="Counter Strategy",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    # Counter spell
)


FLARE_SIGNAL = make_instant(
    name="Flare Signal",
    mana_cost="{U}",
    colors={Color.BLUE},
    # Tap/untap + draw
)


INTELLIGENCE_REPORT = make_instant(
    name="Intelligence Report",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    # Conditional draw
)


RECONNAISSANCE = make_instant(
    name="Reconnaissance",
    mana_cost="{U}",
    colors={Color.BLUE},
    # Impulse effect
)


ESCAPE_ROUTE = make_instant(
    name="Escape Route",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    # Double bounce
)


# --- Sorceries ---

SURVEY_THE_LAND = make_sorcery(
    name="Survey the Land",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw three cards, then discard a card."
)


MAPPING_EXPEDITION = make_sorcery(
    name="Mapping Expedition",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Draw four cards."
)


MEMORY_WIPE = make_sorcery(
    name="Memory Wipe",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Target player shuffles their hand into their library, then draws that many cards."
)


# --- Enchantments ---

STRATEGIC_PLANNING = make_enchantment(
    name="Strategic Planning",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    # Upkeep scry + conditional draw - complex effect
)


INFORMATION_NETWORK = make_enchantment(
    name="Information Network",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(target=AnotherCreature()),
            effect=Scry(1)
        )
    ]
)


# =============================================================================
# BLACK CARDS - MARLEY, WARRIORS, BETRAYAL
# =============================================================================

# --- Legendary Creatures ---

def reiner_braun_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Titan Shift - becomes 6/6"""
    return [make_titan_shift(obj, 6, 6, 3)]

REINER_BRAUN = make_creature(
    name="Reiner Braun, Armored Titan",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    setup_interceptors=reiner_braun_setup
)


BERTHOLDT_HOOVER = make_creature(
    name="Bertholdt Hoover, Colossal Titan",
    power=10, toughness=10,
    mana_cost="{6}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    # Trample, ETB damage all creatures - complex effect
)


ANNIE_LEONHART = make_creature(
    name="Annie Leonhart, Female Titan",
    power=5, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    # Deathtouch, activated hexproof/indestructible - complex effect
)


ZEKE_YEAGER = make_creature(
    name="Zeke Yeager, Beast Titan",
    power=6, toughness=6,
    mana_cost="{4}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(2, 2),
            filter=CreaturesWithSubtypeFilter(subtype="Titan", include_self=False)
        )
    ]
)


WAR_HAMMER_TITAN = make_creature(
    name="War Hammer Titan",
    power=5, toughness=5,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    # ETB create equipment token - complex effect
)


# --- Regular Creatures ---

MARLEYAN_WARRIOR = make_creature(
    name="Marleyan Warrior",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior", "Soldier"},
    # Menace - keyword handled separately
)


WARRIOR_CANDIDATE = make_creature(
    name="Warrior Candidate",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior"},
    abilities=[
        TriggeredAbility(
            trigger=DeathTrigger(),
            effect=LoseLife(2)
        )
    ]
)


MARLEYAN_OFFICER = make_creature(
    name="Marleyan Officer",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    # Deathtouch - keyword handled separately
)


INFILTRATOR = make_creature(
    name="Infiltrator",
    power=2, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    # Can't be blocked, combat damage discard - complex effect
)


ELDIAN_INTERNMENT_GUARD = make_creature(
    name="Eldian Internment Guard",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    abilities=[
        TriggeredAbility(
            trigger=DeathTrigger(target=AnotherCreature()),
            effect=GainLife(1)
        )
    ]
)


TITAN_INHERITOR = make_creature(
    name="Titan Inheritor",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior"},
    # ETB sacrifice + draw - complex effect
)


MILITARY_EXECUTIONER = make_creature(
    name="Military Executioner",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    # ETB destroy small creature - complex effect
)


RESTORATIONIST = make_creature(
    name="Restorationist",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Cleric"},
    # Activated return from graveyard - complex effect
)


PURE_TITAN = make_creature(
    name="Pure Titan",
    power=4, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    # Attacks each combat - complex effect
)


ABNORMAL_TITAN = make_creature(
    name="Abnormal Titan",
    power=5, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    # Haste, attacks each combat, death trigger - complex effect
)


SMALL_TITAN = make_creature(
    name="Small Titan",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    # Attacks each combat - complex effect
)


TITAN_HORDE = make_creature(
    name="Titan Horde",
    power=6, toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    # Trample, ETB create tokens, titans attack - complex effect
)


MINDLESS_TITAN = make_creature(
    name="Mindless Titan",
    power=3, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    # Attacks each combat, can't block - complex effect
)


CRAWLING_TITAN = make_creature(
    name="Crawling Titan",
    power=2, toughness=4,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    abilities=[
        TriggeredAbility(
            trigger=DeathTrigger(),
            effect=LoseLife(2)
        )
    ]
)


# --- Instants ---

BETRAYAL = make_instant(
    name="Betrayal",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    # Destroy + life loss
)


TITANS_HUNGER = make_instant(
    name="Titan's Hunger",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    # -3/-3 + life gain
)


COORDINATE_POWER = make_instant(
    name="Coordinate Power",
    mana_cost="{B}",
    colors={Color.BLACK},
    # Pump + conditional menace
)


MEMORY_MANIPULATION = make_instant(
    name="Memory Manipulation",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    # Discard + conditional draw
)


CRYSTALLIZATION = make_instant(
    name="Crystallization",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    # Hexproof/indestructible + tap
)


SACRIFICE_PLAY = make_instant(
    name="Sacrifice Play",
    mana_cost="{B}",
    colors={Color.BLACK},
    # Additional cost sacrifice + draw two
)


WARRIOR_RESOLVE = make_instant(
    name="Warrior's Resolve",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    # Indestructible + life loss
)


# --- Sorceries ---

TITANIZATION = make_sorcery(
    name="Titanization",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Destroy all non-Titan creatures. Create a 4/4 black Titan creature token."
)


MARLEY_INVASION = make_sorcery(
    name="Marley Invasion",
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    text="Each opponent sacrifices two creatures. You create a 3/3 black Warrior creature token for each creature sacrificed this way."
)


INHERIT_POWER = make_sorcery(
    name="Inherit Power",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. If it was a Titan, create a token copy of it."
)


ELDIAN_PURGE = make_sorcery(
    name="Eldian Purge",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. Its controller loses 3 life."
)


# --- Enchantments ---

PATHS_OF_TITANS = make_enchantment(
    name="Paths of Titans",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    abilities=[
        TriggeredAbility(
            trigger=DeathTrigger(target=CreatureWithSubtype(subtype="Titan", you_control=False)),
            effect=CompositeEffect([DrawCards(1), LoseLife(1)])
        )
    ]
)


WARRIOR_PROGRAM = make_enchantment(
    name="Warrior Program",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter(subtype="Warrior")
        )
    ]
)


MARLEYAN_DOMINION = make_enchantment(
    name="Marleyan Dominion",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    # Upkeep sacrifice or life loss - complex effect
)


# =============================================================================
# RED CARDS - ATTACK TITAN, RAGE, DESTRUCTION
# =============================================================================

# --- Legendary Creatures ---

EREN_ATTACK_TITAN = make_creature(
    name="Eren Yeager, Attack Titan",
    power=6, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    # Haste, trample, attack trigger damage - complex effect
)


EREN_FOUNDING_TITAN = make_creature(
    name="Eren Yeager, Founding Titan",
    power=10, toughness=10,
    mana_cost="{5}{R}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(3, 3),
            filter=CreaturesWithSubtypeFilter(subtype="Titan", include_self=False)
        ),
        StaticAbility(
            effect=KeywordGrant(["haste"]),
            filter=CreaturesWithSubtypeFilter(subtype="Titan", include_self=False)
        )
    ]
)


GRISHA_YEAGER = make_creature(
    name="Grisha Yeager, Rogue Titan",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    # Haste, death trigger search - complex effect
)


JAW_TITAN = make_creature(
    name="Jaw Titan",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    # Haste, first strike, conditional boost - complex effect
)


# --- Regular Creatures ---

BERSERKER_TITAN = make_creature(
    name="Berserker Titan",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Titan"},
    # Double strike when attacking - complex conditional effect
)


RAGING_TITAN = make_creature(
    name="Raging Titan",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Titan"},
    # Trample, haste, attacks each combat - complex effect
)


CHARGING_TITAN = make_creature(
    name="Charging Titan",
    power=4, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Titan"},
    # Haste, ETB damage - complex effect
)


WALL_BREAKER = make_creature(
    name="Wall Breaker",
    power=6, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Titan"},
    # Trample, can't be blocked by defenders - complex effect
)


ELDIAN_REBEL = make_creature(
    name="Eldian Rebel",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    # Haste, death trigger damage - complex effect
)


ATTACK_TITAN_ACOLYTE = make_creature(
    name="Attack Titan Acolyte",
    power=3, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    # First strike, combat damage loot - complex effect
)


YEAGERIST_SOLDIER = make_creature(
    name="Yeagerist Soldier",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    # Haste, conditional boost - complex effect
)


YEAGERIST_FANATIC = make_creature(
    name="Yeagerist Fanatic",
    power=3, toughness=1,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    # Haste, ETB damage - complex effect
)


EXPLOSIVE_SPECIALIST = make_creature(
    name="Explosive Specialist",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier", "Artificer"},
    # Activated sacrifice damage - complex effect
)


THUNDER_SPEAR_TROOPER = make_creature(
    name="Thunder Spear Trooper",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Scout", "Soldier"},
    # ETB damage to Titan - complex effect
)


CANNON_OPERATOR = make_creature(
    name="Cannon Operator",
    power=1, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    # Activated damage - complex effect
)


FLOCH_FORSTER = make_creature(
    name="Floch Forster, Yeagerist Leader",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 0),
            filter=CreaturesWithSubtypeFilter(subtype="Soldier", include_self=False)
        )
    ]
)


# --- Instants ---

TITANS_RAGE = make_instant(
    name="Titan's Rage",
    mana_cost="{1}{R}",
    colors={Color.RED},
    # Pump + conditional indestructible
)


THUNDER_SPEAR_STRIKE = make_instant(
    name="Thunder Spear Strike",
    mana_cost="{2}{R}",
    colors={Color.RED},
    # Conditional damage
)


WALL_BOMBARDMENT = make_instant(
    name="Wall Bombardment",
    mana_cost="{3}{R}",
    colors={Color.RED},
    # Damage to creature and player
)


COORDINATE_ATTACK = make_instant(
    name="Coordinate Attack",
    mana_cost="{R}",
    colors={Color.RED},
    # Pump + draw
)


DESPERATE_CHARGE = make_instant(
    name="Desperate Charge",
    mana_cost="{1}{R}",
    colors={Color.RED},
    # Team pump + haste
)


BURNING_WILL = make_instant(
    name="Burning Will",
    mana_cost="{R}",
    colors={Color.RED},
    # Pump
)


CANNON_BARRAGE = make_instant(
    name="Cannon Barrage",
    mana_cost="{2}{R}",
    colors={Color.RED},
    # Divided damage
)


# --- Sorceries ---

THE_RUMBLING = make_sorcery(
    name="The Rumbling",
    mana_cost="{5}{R}{R}{R}",
    colors={Color.RED},
    text="Destroy all lands. Create ten 6/6 red Titan creature tokens with trample."
)


TITANS_FURY = make_sorcery(
    name="Titan's Fury",
    mana_cost="{X}{R}{R}",
    colors={Color.RED},
    text="Titan's Fury deals X damage to each creature and each player."
)


BREACH_THE_WALL = make_sorcery(
    name="Breach the Wall",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Destroy target artifact or land. Deal 3 damage to its controller."
)


RALLY_THE_YEAGERISTS = make_sorcery(
    name="Rally the Yeagerists",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Create three 2/1 red Human Soldier creature tokens with haste."
)


# --- Enchantments ---

ATTACK_ON_TITAN = make_enchantment(
    name="Attack on Titan",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    abilities=[
        StaticAbility(
            effect=PTBoost(2, 0),
            filter=CreaturesWithSubtypeFilter(subtype="Titan")
        ),
        StaticAbility(
            effect=KeywordGrant(["haste"]),
            filter=CreaturesWithSubtypeFilter(subtype="Titan")
        )
    ]
)


RAGE_OF_THE_TITANS = make_enchantment(
    name="Rage of the Titans",
    mana_cost="{1}{R}",
    colors={Color.RED},
    abilities=[
        TriggeredAbility(
            trigger=AttackTrigger(target=CreatureWithSubtype(subtype="Titan", you_control=True, exclude_self=False)),
            effect=CompositeEffect([])  # +1/+0 until end of turn - complex effect
        )
    ]
)


FOUNDING_TITAN_POWER = make_enchantment(
    name="Founding Titan's Power",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    # Upkeep create token, titans attack - complex effect
)


# =============================================================================
# GREEN CARDS - COLOSSAL FORCES, BEAST TITAN, NATURE
# =============================================================================

# --- Legendary Creatures ---

BEAST_TITAN = make_creature(
    name="Beast Titan",
    power=7, toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    # Reach, trample, attack trigger damage - complex effect
)


COLOSSAL_TITAN = make_creature(
    name="Colossal Titan",
    power=10, toughness=10,
    mana_cost="{7}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    # Trample, ETB damage all other creatures - complex effect
)


TOM_KSAVER = make_creature(
    name="Tom Ksaver, Beast Inheritor",
    power=2, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    # ETB search Titan - complex effect
)


# --- Regular Creatures ---

def wall_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Massive wall Titan"""
    return make_wall_defense(obj, 4)

WALL_TITAN = make_creature(
    name="Wall Titan",
    power=0, toughness=12,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan", "Wall"},
    setup_interceptors=wall_titan_setup
)


FOREST_TITAN = make_creature(
    name="Forest Titan",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan"},
    # Trample, reach - keywords handled separately
)


TOWERING_TITAN = make_creature(
    name="Towering Titan",
    power=8, toughness=8,
    mana_cost="{6}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan"},
    # Trample, evasion - complex effect
)


ANCIENT_TITAN = make_creature(
    name="Ancient Titan",
    power=7, toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan"},
    # Trample, ETB put counters - complex effect
)


PRIMORDIAL_TITAN = make_creature(
    name="Primordial Titan",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan"},
    # Trample, ETB search land - complex effect
)


FOREST_DWELLER = make_creature(
    name="Forest Dweller",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human"},
    # Mana ability - complex effect
)


PARADIS_FARMER = make_creature(
    name="Paradis Farmer",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Citizen"},
    # Conditional mana ability - complex effect
)


TITAN_HUNTER = make_creature(
    name="Titan Hunter",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout"},
    # Reach, conditional boost - complex effect
)


FOREST_SCOUT = make_creature(
    name="Forest Scout",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout"},
    # ETB search basic land - complex effect
)


ELDIAN_WOODCUTTER = make_creature(
    name="Eldian Woodcutter",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Citizen"},
    # Conditional mana ability - complex effect
)


WILD_HORSE = make_creature(
    name="Wild Horse",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Horse"},
    # Haste, ETB grant haste - complex effect
)


SURVEY_CORPS_MOUNT = make_creature(
    name="Survey Corps Mount",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Horse"},
    # ETB pump Scout - complex effect
)


# --- Instants ---

TITANS_GROWTH = make_instant(
    name="Titan's Growth",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    # Pump +4/+4
)


HARDENING_ABILITY = make_instant(
    name="Hardening Ability",
    mana_cost="{G}",
    colors={Color.GREEN},
    # +0/+5 + indestructible
)


REGENERATION = make_instant(
    name="Regeneration",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    # Regenerate + conditional counters
)


FOREST_AMBUSH = make_instant(
    name="Forest Ambush",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    # Fight with pump
)


COLOSSAL_STRENGTH = make_instant(
    name="Colossal Strength",
    mana_cost="{G}{G}",
    colors={Color.GREEN},
    # +4/+4 + trample
)


NATURAL_REGENERATION = make_instant(
    name="Natural Regeneration",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    # Put counters on all creatures
)


WILD_CHARGE = make_instant(
    name="Wild Charge",
    mana_cost="{G}",
    colors={Color.GREEN},
    # +2/+2 + trample
)


# --- Sorceries ---

SUMMON_THE_TITANS = make_sorcery(
    name="Summon the Titans",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Create two 6/6 green Titan creature tokens with trample."
)


TITAN_RAMPAGE = make_sorcery(
    name="Titan Rampage",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +X/+X until end of turn, where X is its power. It fights up to one target creature you don't control."
)


PRIMAL_GROWTH = make_sorcery(
    name="Primal Growth",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for up to two basic land cards and put them onto the battlefield tapped."
)


AWAKENING_OF_THE_TITANS = make_sorcery(
    name="Awakening of the Titans",
    mana_cost="{5}{G}{G}{G}",
    colors={Color.GREEN},
    text="Put all Titan creature cards from your hand and graveyard onto the battlefield."
)


# --- Enchantments ---

TITANS_DOMINION = make_enchantment(
    name="Titan's Dominion",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    abilities=[
        StaticAbility(
            effect=PTBoost(2, 2),
            filter=CreaturesWithSubtypeFilter(subtype="Titan")
        ),
        StaticAbility(
            effect=KeywordGrant(["trample"]),
            filter=CreaturesWithSubtypeFilter(subtype="Titan")
        )
    ]
)


FORCE_OF_NATURE = make_enchantment(
    name="Force of Nature",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    # Upkeep put counter - complex effect
)


HARDENED_SKIN = make_enchantment(
    name="Hardened Skin",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    # Aura +0/+4 + hexproof - complex effect
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

# Nine Titans (Legendary)

FOUNDING_TITAN = make_creature(
    name="The Founding Titan",
    power=12, toughness=12,
    mana_cost="{4}{W}{U}{B}{R}{G}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    # Indestructible, trample, hexproof, ETB control Titans, upkeep create token - complex effect
)


ATTACK_TITAN_CARD = make_creature(
    name="The Attack Titan",
    power=8, toughness=6,
    mana_cost="{3}{R}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    # Haste, trample, attack trigger boost - complex effect
)


ARMORED_TITAN = make_creature(
    name="The Armored Titan",
    power=6, toughness=8,
    mana_cost="{3}{B}{B}{W}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    # Indestructible, can't be blocked by fewer than 3 - complex effect
)


FEMALE_TITAN = make_creature(
    name="The Female Titan",
    power=6, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    # First strike, deathtouch, activated hexproof - complex effect
)


COLOSSAL_TITAN_LEGENDARY = make_creature(
    name="The Colossal Titan",
    power=15, toughness=15,
    mana_cost="{7}{B}{G}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    # Trample, ETB damage all - complex effect
)


BEAST_TITAN_LEGENDARY = make_creature(
    name="The Beast Titan",
    power=8, toughness=8,
    mana_cost="{4}{B}{G}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(2, 2),
            filter=CreaturesWithSubtypeFilter(subtype="Titan", include_self=False)
        )
    ]
)


CART_TITAN = make_creature(
    name="The Cart Titan",
    power=3, toughness=6,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    # Can't be blocked, combat damage draw 2 - complex effect
)


JAW_TITAN_LEGENDARY = make_creature(
    name="The Jaw Titan",
    power=5, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    # Haste, first strike, attack trigger destroy artifact/enchantment - complex effect
)


WAR_HAMMER_TITAN_LEGENDARY = make_creature(
    name="The War Hammer Titan",
    power=6, toughness=6,
    mana_cost="{3}{B}{B}{W}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    # First strike, ETB create equipment tokens, activated create construct - complex effect
)


# Other Multicolor

KENNY_ACKERMAN = make_creature(
    name="Kenny Ackerman, The Ripper",
    power=4, toughness=3,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Rogue", "Ackerman"},
    supertypes={"Legendary"},
    # Deathtouch, first strike, menace-like evasion - complex effect
)


PORCO_GALLIARD = make_creature(
    name="Porco Galliard, Jaw Titan",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    # Haste, first strike, death trigger search - complex effect
)


MARCEL_GALLIARD = make_creature(
    name="Marcel Galliard, Fallen Warrior",
    power=2, toughness=2,
    mana_cost="{1}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    # Death trigger grant indestructible - complex effect
)


YMIR = make_creature(
    name="Ymir, Original Titan",
    power=4, toughness=4,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    # Death trigger search Titan - complex effect
)


GABI_BRAUN = make_creature(
    name="Gabi Braun, Warrior Candidate",
    power=2, toughness=2,
    mana_cost="{1}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Warrior", "Soldier"},
    supertypes={"Legendary"},
    # First strike, combat damage sacrifice - complex effect
)


FALCO_GRICE = make_creature(
    name="Falco Grice, Jaw Inheritor",
    power=3, toughness=3,
    mana_cost="{2}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    # Flying, vigilance, transform - complex effect
)


COLT_GRICE = make_creature(
    name="Colt Grice, Beast Candidate",
    power=2, toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    # Reach, ETB search Titan - complex effect
)


URI_REISS = make_creature(
    name="Uri Reiss, Founding Inheritor",
    power=3, toughness=5,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Noble", "Titan"},
    supertypes={"Legendary"},
    # Lifelink, upkeep pay life draw - complex effect
)


ROD_REISS = make_creature(
    name="Rod Reiss, Aberrant Titan",
    power=1, toughness=15,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    # Defender, conditional boost, death trigger sacrifice - complex effect
)


# =============================================================================
# EQUIPMENT
# =============================================================================

ODM_GEAR = make_equipment(
    name="ODM Gear",
    mana_cost="{2}",
    text="Equipped creature gets +1/+0 and has flying and first strike.",
    equip_cost="{2}",
    # Equipment boost - complex effect
)


ADVANCED_ODM_GEAR = make_equipment(
    name="Advanced ODM Gear",
    mana_cost="{3}",
    text="Equipped creature gets +2/+1 and has flying, first strike, and vigilance.",
    equip_cost="{2}"
)


THUNDER_SPEAR = make_equipment(
    name="Thunder Spear",
    mana_cost="{2}",
    text="Equipped creature gets +2/+0. Whenever equipped creature deals combat damage to a Titan, destroy that Titan.",
    equip_cost="{1}"
)


ANTI_PERSONNEL_ODM_GEAR = make_equipment(
    name="Anti-Personnel ODM Gear",
    mana_cost="{3}",
    text="Equipped creature gets +2/+0, has flying, and has '{T}: This creature deals 2 damage to target creature.'",
    equip_cost="{2}"
)


SURVEY_CORPS_CLOAK = make_equipment(
    name="Survey Corps Cloak",
    mana_cost="{1}",
    text="Equipped creature gets +0/+1 and has hexproof as long as it's not attacking.",
    equip_cost="{1}"
)


BLADE_SET = make_equipment(
    name="Blade Set",
    mana_cost="{1}",
    text="Equipped creature gets +2/+0.",
    equip_cost="{1}"
)


GAS_CANISTER = make_equipment(
    name="Gas Canister",
    mana_cost="{1}",
    text="Equipped creature has '{T}, Sacrifice Gas Canister: This creature gains flying until end of turn. Draw a card.'",
    equip_cost="{1}"
)


GARRISON_CANNON = make_equipment(
    name="Garrison Cannon",
    mana_cost="{4}",
    text="Equipped creature has '{T}: This creature deals 4 damage to target attacking or blocking creature.'",
    equip_cost="{3}"
)


FLARE_GUN = make_equipment(
    name="Flare Gun",
    mana_cost="{1}",
    text="Equipped creature has '{T}, Sacrifice Flare Gun: Draw a card. You may reveal a Scout card from your hand. If you do, draw another card.'",
    equip_cost="{1}"
)


# =============================================================================
# ARTIFACTS
# =============================================================================

FOUNDING_TITAN_SERUM = make_artifact(
    name="Founding Titan Serum",
    mana_cost="{3}",
    text="{T}, Sacrifice Founding Titan Serum: Target creature becomes a Titan in addition to its other types and gets +4/+4 until end of turn."
)


TITAN_SERUM = make_artifact(
    name="Titan Serum",
    mana_cost="{2}",
    text="{T}, Sacrifice Titan Serum: Target creature becomes a Titan in addition to its other types and gets +2/+2 until end of turn."
)


ARMORED_TITAN_SERUM = make_artifact(
    name="Armored Titan Serum",
    mana_cost="{3}",
    text="{T}, Sacrifice Armored Titan Serum: Target creature becomes a Titan in addition to its other types and gains indestructible until end of turn."
)


SUPPLY_CACHE = make_artifact(
    name="Supply Cache",
    mana_cost="{2}",
    text="{T}, Sacrifice Supply Cache: Add {C}{C}{C}. Draw a card."
)


SIGNAL_FLARE = make_artifact(
    name="Signal Flare",
    mana_cost="{1}",
    text="{T}, Sacrifice Signal Flare: Scry 2, then draw a card."
)


WAR_HAMMER = make_artifact(
    name="War Hammer Construct",
    mana_cost="{4}",
    text="{2}, {T}: Create a 2/2 colorless Construct artifact creature token."
)


COORDINATE = make_artifact(
    name="The Coordinate",
    mana_cost="{5}",
    text="{T}: Gain control of target Titan until end of turn. Untap it. It gains haste until end of turn.",
    supertypes={"Legendary"}
)


ATTACK_TITAN_MEMORIES = make_artifact(
    name="Attack Titan's Memories",
    mana_cost="{3}",
    text="{2}, {T}: Look at the top three cards of your library. Put one into your hand and the rest on the bottom in any order.",
    supertypes={"Legendary"}
)


BASEMENT_KEY = make_artifact(
    name="Basement Key",
    mana_cost="{1}",
    text="{T}, Sacrifice Basement Key: Draw two cards. You may put a land card from your hand onto the battlefield.",
    supertypes={"Legendary"}
)


GRISHA_JOURNAL = make_artifact(
    name="Grisha's Journal",
    mana_cost="{2}",
    text="{1}, {T}: Draw a card. If you control Eren Yeager, draw two cards instead.",
    supertypes={"Legendary"}
)


# =============================================================================
# LANDS
# =============================================================================

WALL_MARIA = make_land(
    name="Wall Maria",
    text="{T}: Add {C}. {T}: Add {W}. Activate only if you control a Scout.",
    supertypes={"Legendary"}
)


WALL_ROSE = make_land(
    name="Wall Rose",
    text="{T}: Add {C}. {T}: Add {W} or {R}. Activate only if you control a Soldier.",
    supertypes={"Legendary"}
)


WALL_SHEENA = make_land(
    name="Wall Sheena",
    text="{T}: Add {C}. {T}: Add {W} or {U}. Activate only if you control a Noble.",
    supertypes={"Legendary"}
)


SHIGANSHINA_DISTRICT = make_land(
    name="Shiganshina District",
    text="Shiganshina District enters tapped. {T}: Add {R} or {W}."
)


TROST_DISTRICT = make_land(
    name="Trost District",
    text="Trost District enters tapped. {T}: Add {W} or {U}."
)


STOHESS_DISTRICT = make_land(
    name="Stohess District",
    text="Stohess District enters tapped. {T}: Add {W} or {B}."
)


SURVEY_CORPS_HQ = make_land(
    name="Survey Corps Headquarters",
    text="{T}: Add {C}. {2}, {T}: Scout creatures you control get +1/+0 until end of turn."
)


GARRISON_HEADQUARTERS = make_land(
    name="Garrison Headquarters",
    text="{T}: Add {C}. {2}, {T}: Create a 1/1 white Human Soldier creature token with defender."
)


MILITARY_POLICE_HQ = make_land(
    name="Military Police Headquarters",
    text="{T}: Add {C}. {3}, {T}: Tap target creature."
)


PARADIS_ISLAND = make_land(
    name="Paradis Island",
    text="Paradis Island enters tapped. When it enters, you gain 1 life. {T}: Add {G} or {W}."
)


MARLEY = make_land(
    name="Marley",
    text="Marley enters tapped. {T}: Add {B} or {R}."
)


LIBERIO_INTERNMENT_ZONE = make_land(
    name="Liberio Internment Zone",
    text="{T}: Add {C}. {T}: Add {B}. Activate only if you control a Warrior."
)


FOREST_OF_GIANT_TREES = make_land(
    name="Forest of Giant Trees",
    text="{T}: Add {G}. Creatures with flying you control get +0/+1."
)


UTGARD_CASTLE = make_land(
    name="Utgard Castle",
    text="Utgard Castle enters tapped. {T}: Add {W} or {B}. {3}, {T}: Create a 0/4 white Wall creature token with defender."
)


REISS_CHAPEL = make_land(
    name="Reiss Chapel",
    text="{T}: Add {C}. {4}, {T}, Sacrifice Reiss Chapel: Search your library for a Titan card, reveal it, and put it into your hand.",
    supertypes={"Legendary"}
)


PATHS = make_land(
    name="The Paths",
    text="{T}: Add one mana of any color. Spend this mana only to cast Titan spells.",
    supertypes={"Legendary"}
)


OCEAN = make_land(
    name="The Ocean",
    text="The Ocean enters tapped. When it enters, scry 1. {T}: Add {U} or {G}.",
    supertypes={"Legendary"}
)


# Additional Locations
ORVUD_DISTRICT = make_land(
    name="Orvud District",
    text="Orvud District enters tapped. {T}: Add {W} or {R}. When Orvud District enters, you may tap target creature."
)


KARANES_DISTRICT = make_land(
    name="Karanes District",
    text="Karanes District enters tapped. {T}: Add {U} or {W}."
)


RAGAKO_VILLAGE = make_land(
    name="Ragako Village",
    text="{T}: Add {C}. {2}, {T}: Create a 2/2 black Titan creature token that attacks each combat if able."
)


UNDERGROUND_CITY = make_land(
    name="Underground City",
    text="{T}: Add {B}. {3}{B}, {T}: Return target creature card with mana value 2 or less from your graveyard to the battlefield."
)


# Additional White Cards
NILE_DOK = make_creature(
    name="Nile Dok, Military Police Commander",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Noble"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(0, 1),
            filter=CreaturesWithSubtypeFilter(subtype="Soldier", include_self=False)
        )
    ]
)


DARIUS_ZACKLY = make_creature(
    name="Darius Zackly, Premier",
    power=1, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    # Upkeep tap target - complex effect
)


DOT_PIXIS = make_creature(
    name="Dot Pixis, Garrison Commander",
    power=2, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Noble"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 0),
            filter=CreaturesWithSubtypeFilter(subtype="Soldier")
        )
    ]
)


HANNES = make_creature(
    name="Hannes, Garrison Captain",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    # Death trigger grant indestructible/vigilance - complex effect
)


CARLA_YEAGER = make_creature(
    name="Carla Yeager, Eren's Mother",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    supertypes={"Legendary"},
    # Death trigger conditional boost - complex effect
)


WALL_ROSE_GARRISON = make_creature(
    name="Wall Rose Garrison",
    power=1, toughness=5,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Wall"},
    abilities=[
        TriggeredAbility(
            trigger=BlockTrigger(),
            effect=GainLife(3)
        )
    ]
)


MILITARY_TRIBUNAL = make_sorcery(
    name="Military Tribunal",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Exile target creature. Its controller creates a 1/1 white Human Soldier creature token."
)


# Additional Blue Cards
MOBLIT_BERNER = make_creature(
    name="Moblit Berner, Hange's Assistant",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=Scry(2)
        )
    ]
)


ONYANKOPON = make_creature(
    name="Onyankopon, Anti-Marleyan",
    power=2, toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Pilot"},
    supertypes={"Legendary"},
    # Flying, combat damage discard + draw - complex effect
)


YELENA = make_creature(
    name="Yelena, True Believer",
    power=2, toughness=3,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    # Menace, ETB look at hand and discard - complex effect
)


ILSE_LANGNAR = make_creature(
    name="Ilse Langnar, Titan Chronicler",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout"},
    supertypes={"Legendary"},
    # Death trigger conditional draw - complex effect
)


INFORMATION_GATHERING = make_sorcery(
    name="Information Gathering",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Look at target opponent's hand. Draw a card."
)


TITAN_BIOLOGY = make_enchantment(
    name="Titan Biology",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(target=CreatureWithSubtype(subtype="Titan", you_control=False)),
            effect=CompositeEffect([Scry(1), DrawCards(1)])
        ),
        TriggeredAbility(
            trigger=DeathTrigger(target=CreatureWithSubtype(subtype="Titan", you_control=False)),
            effect=CompositeEffect([Scry(1), DrawCards(1)])
        )
    ]
)


# Additional Black Cards
DINA_FRITZ = make_creature(
    name="Dina Fritz, Smiling Titan",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    # ETB each opponent sacrifices, attacks each combat - complex effect
)


KRUGER = make_creature(
    name="Eren Kruger, The Owl",
    power=4, toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    # Haste, death trigger search - complex effect
)


GROSS = make_creature(
    name="Sergeant Major Gross",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=DeathTrigger(target=AnotherCreature()),
            effect=LoseLife(1)
        )
    ]
)


MAGATH = make_creature(
    name="Theo Magath, Marleyan General",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier", "Noble"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter(subtype="Warrior", include_self=False)
        )
    ]
)


WILLY_TYBUR = make_creature(
    name="Willy Tybur, Declaration of War",
    power=2, toughness=2,
    mana_cost="{2}{B}{W}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    # ETB each player sacrifices, death trigger create Titan - complex effect
)


ELDIAN_ARMBAND = make_artifact(
    name="Eldian Armband",
    mana_cost="{1}",
    text="Equipped creature gets +0/+1 and is an Eldian in addition to its other types. Equip {1}"
)


# Additional Red Cards
KAYA = make_creature(
    name="Kaya, Sasha's Friend",
    power=1, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Citizen"},
    supertypes={"Legendary"},
    # ETB create Food tokens - complex effect
)


KEITH_SHADIS = make_creature(
    name="Keith Shadis, Instructor",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    # ETB pump + first strike - complex effect
)


LOUISE = make_creature(
    name="Louise, Yeagerist Devotee",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    # First strike, conditional boost - complex effect
)


TITAN_TRANSFORMATION = make_instant(
    name="Titan Transformation",
    mana_cost="{2}{R}",
    colors={Color.RED},
    # Grant Titan type + pump + trample
)


DECLARATION_OF_WAR = make_sorcery(
    name="Declaration of War",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Gain control of all Titans until end of turn. Untap them. They gain haste until end of turn."
)


# Additional Green Cards
YMIR_FRITZ = make_creature(
    name="Ymir Fritz, Source of All Titans",
    power=8, toughness=8,
    mana_cost="{5}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=KeywordGrant(["hexproof"]),
            filter=CreaturesWithSubtypeFilter(subtype="Titan")
        )
    ]
)


KING_FRITZ = make_creature(
    name="King Fritz, First Eldian King",
    power=3, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter(subtype="Titan")
        )
    ]
)


TITANS_BLESSING = make_instant(
    name="Titan's Blessing",
    mana_cost="{G}",
    colors={Color.GREEN},
    # Pump + conditional trample/hexproof
)


WALL_TITAN_ARMY = make_sorcery(
    name="Wall Titan Army",
    mana_cost="{6}{G}{G}",
    colors={Color.GREEN},
    text="Create four 6/6 green Titan creature tokens with trample."
)


# Basic lands
PLAINS_AOT = make_land(
    name="Plains",
    text="{T}: Add {W}.",
    subtypes={"Plains"}
)


ISLAND_AOT = make_land(
    name="Island",
    text="{T}: Add {U}.",
    subtypes={"Island"}
)


SWAMP_AOT = make_land(
    name="Swamp",
    text="{T}: Add {B}.",
    subtypes={"Swamp"}
)


MOUNTAIN_AOT = make_land(
    name="Mountain",
    text="{T}: Add {R}.",
    subtypes={"Mountain"}
)


FOREST_AOT = make_land(
    name="Forest",
    text="{T}: Add {G}.",
    subtypes={"Forest"}
)


# =============================================================================
# CARD DICTIONARY
# =============================================================================

ATTACK_ON_TITAN_CARDS = {
    # WHITE - SURVEY CORPS, HUMANITY'S HOPE
    "Eren Yeager, Survey Corps": EREN_YEAGER_SCOUT,
    "Mikasa Ackerman, Humanity's Strongest": MIKASA_ACKERMAN,
    "Armin Arlert, Tactician": ARMIN_ARLERT,
    "Levi Ackerman, Captain": LEVI_ACKERMAN,
    "Erwin Smith, Commander": ERWIN_SMITH,
    "Hange Zoe, Researcher": HANGE_ZOE,
    "Historia Reiss, True Queen": HISTORIA_REISS,
    "Sasha Blouse, Hunter": SASHA_BLOUSE,
    "Connie Springer, Loyal Friend": CONNIE_SPRINGER,
    "Jean Kirstein, Natural Leader": JEAN_KIRSTEIN,
    "Miche Zacharias, Squad Leader": MICHE_ZACHARIAS,
    "Petra Ral, Levi Squad": PETRA_RAL,
    "Oluo Bozado, Levi Squad": OLUO_BOZADO,
    "Survey Corps Recruit": SURVEY_CORPS_RECRUIT,
    "Survey Corps Veteran": SURVEY_CORPS_VETERAN,
    "Garrison Soldier": GARRISON_SOLDIER,
    "Military Police Officer": MILITARY_POLICE_OFFICER,
    "Wall Defender": WALL_DEFENDER,
    "Training Corps Cadet": TRAINING_CORPS_CADET,
    "Squad Captain": SQUAD_CAPTAIN,
    "Wall Garrison Elite": WALL_GARRISON_ELITE,
    "Interior Police": INTERIOR_POLICE,
    "Shiganshina Citizen": SHIGANSHINA_CITIZEN,
    "Eldian Refugee": ELDIAN_REFUGEE,
    "Wall Cultist": WALL_CULTIST,
    "Horse Mounted Scout": HORSE_MOUNTED_SCOUT,
    "Devoted Heart": DEVOTED_HEART,
    "Survey Corps Charge": SURVEY_CORPS_CHARGE,
    "Wall Defense": WALL_DEFENSE,
    "Humanity's Hope": HUMANITYS_HOPE,
    "Salute of Hearts": SALUTE_OF_HEARTS,
    "Strategic Retreat": STRATEGIC_RETREAT,
    "Formation Break": FORMATION_BREAK,
    "Garrison Reinforcements": GARRISON_REINFORCEMENTS,
    "Survey Mission": SURVEY_MISSION,
    "Evacuation Order": EVACUATION_ORDER,
    "Wall Reconstruction": WALL_RECONSTRUCTION,
    "Training Exercise": TRAINING_EXERCISE,
    "Survey Corps Banner": SURVEY_CORPS_BANNER,
    "Wings of Freedom": WINGS_OF_FREEDOM,
    "Wall Faith": WALL_FAITH,

    # BLUE - STRATEGY, PLANNING
    "Armin, Colossal Titan": ARMIN_COLOSSAL_TITAN,
    "Erwin Smith, The Gambit": ERWIN_GAMBIT,
    "Pieck Finger, Cart Titan": PIECK_FINGER,
    "Intelligence Officer": INTELLIGENCE_OFFICER,
    "Marleyan Spy": MARLEYAN_SPY,
    "Survey Cartographer": SURVEY_CARTOGRAPHER,
    "Titan Researcher": TITAN_RESEARCHER,
    "Strategic Advisor": STRATEGIC_ADVISOR,
    "Wall Architect": WALL_ARCHITECT,
    "Military Tactician": MILITARY_TACTICIAN,
    "Signal Corps Operator": SIGNAL_CORPS_OPERATOR,
    "Supply Corps Quartermaster": SUPPLY_CORPS_QUARTERMASTER,
    "Coastal Scout": COASTAL_SCOUT,
    "Formation Analyst": FORMATION_ANALYST,
    "Strategic Analysis": STRATEGIC_ANALYSIS,
    "Tactical Retreat": TACTICAL_RETREAT,
    "Formation Shift": FORMATION_SHIFT,
    "Counter Strategy": COUNTER_STRATEGY,
    "Flare Signal": FLARE_SIGNAL,
    "Intelligence Report": INTELLIGENCE_REPORT,
    "Reconnaissance": RECONNAISSANCE,
    "Escape Route": ESCAPE_ROUTE,
    "Survey the Land": SURVEY_THE_LAND,
    "Mapping Expedition": MAPPING_EXPEDITION,
    "Memory Wipe": MEMORY_WIPE,
    "Strategic Planning": STRATEGIC_PLANNING,
    "Information Network": INFORMATION_NETWORK,

    # BLACK - MARLEY, WARRIORS, BETRAYAL
    "Reiner Braun, Armored Titan": REINER_BRAUN,
    "Bertholdt Hoover, Colossal Titan": BERTHOLDT_HOOVER,
    "Annie Leonhart, Female Titan": ANNIE_LEONHART,
    "Zeke Yeager, Beast Titan": ZEKE_YEAGER,
    "War Hammer Titan": WAR_HAMMER_TITAN,
    "Marleyan Warrior": MARLEYAN_WARRIOR,
    "Warrior Candidate": WARRIOR_CANDIDATE,
    "Marleyan Officer": MARLEYAN_OFFICER,
    "Infiltrator": INFILTRATOR,
    "Eldian Internment Guard": ELDIAN_INTERNMENT_GUARD,
    "Titan Inheritor": TITAN_INHERITOR,
    "Military Executioner": MILITARY_EXECUTIONER,
    "Restorationist": RESTORATIONIST,
    "Pure Titan": PURE_TITAN,
    "Abnormal Titan": ABNORMAL_TITAN,
    "Small Titan": SMALL_TITAN,
    "Titan Horde": TITAN_HORDE,
    "Mindless Titan": MINDLESS_TITAN,
    "Crawling Titan": CRAWLING_TITAN,
    "Betrayal": BETRAYAL,
    "Titan's Hunger": TITANS_HUNGER,
    "Coordinate Power": COORDINATE_POWER,
    "Memory Manipulation": MEMORY_MANIPULATION,
    "Crystallization": CRYSTALLIZATION,
    "Sacrifice Play": SACRIFICE_PLAY,
    "Warrior's Resolve": WARRIOR_RESOLVE,
    "Titanization": TITANIZATION,
    "Marley Invasion": MARLEY_INVASION,
    "Inherit Power": INHERIT_POWER,
    "Eldian Purge": ELDIAN_PURGE,
    "Paths of Titans": PATHS_OF_TITANS,
    "Warrior Program": WARRIOR_PROGRAM,
    "Marleyan Dominion": MARLEYAN_DOMINION,

    # RED - ATTACK TITAN, RAGE
    "Eren Yeager, Attack Titan": EREN_ATTACK_TITAN,
    "Eren Yeager, Founding Titan": EREN_FOUNDING_TITAN,
    "Grisha Yeager, Rogue Titan": GRISHA_YEAGER,
    "Jaw Titan": JAW_TITAN,
    "Floch Forster, Yeagerist Leader": FLOCH_FORSTER,
    "Berserker Titan": BERSERKER_TITAN,
    "Raging Titan": RAGING_TITAN,
    "Charging Titan": CHARGING_TITAN,
    "Wall Breaker": WALL_BREAKER,
    "Eldian Rebel": ELDIAN_REBEL,
    "Attack Titan Acolyte": ATTACK_TITAN_ACOLYTE,
    "Yeagerist Soldier": YEAGERIST_SOLDIER,
    "Yeagerist Fanatic": YEAGERIST_FANATIC,
    "Explosive Specialist": EXPLOSIVE_SPECIALIST,
    "Thunder Spear Trooper": THUNDER_SPEAR_TROOPER,
    "Cannon Operator": CANNON_OPERATOR,
    "Titan's Rage": TITANS_RAGE,
    "Thunder Spear Strike": THUNDER_SPEAR_STRIKE,
    "Wall Bombardment": WALL_BOMBARDMENT,
    "Coordinate Attack": COORDINATE_ATTACK,
    "Desperate Charge": DESPERATE_CHARGE,
    "Burning Will": BURNING_WILL,
    "Cannon Barrage": CANNON_BARRAGE,
    "The Rumbling": THE_RUMBLING,
    "Titan's Fury": TITANS_FURY,
    "Breach the Wall": BREACH_THE_WALL,
    "Rally the Yeagerists": RALLY_THE_YEAGERISTS,
    "Attack on Titan": ATTACK_ON_TITAN,
    "Rage of the Titans": RAGE_OF_THE_TITANS,
    "Founding Titan's Power": FOUNDING_TITAN_POWER,

    # GREEN - COLOSSAL FORCES, NATURE
    "Beast Titan": BEAST_TITAN,
    "Colossal Titan": COLOSSAL_TITAN,
    "Tom Ksaver, Beast Inheritor": TOM_KSAVER,
    "Wall Titan": WALL_TITAN,
    "Forest Titan": FOREST_TITAN,
    "Towering Titan": TOWERING_TITAN,
    "Ancient Titan": ANCIENT_TITAN,
    "Primordial Titan": PRIMORDIAL_TITAN,
    "Forest Dweller": FOREST_DWELLER,
    "Paradis Farmer": PARADIS_FARMER,
    "Titan Hunter": TITAN_HUNTER,
    "Forest Scout": FOREST_SCOUT,
    "Eldian Woodcutter": ELDIAN_WOODCUTTER,
    "Wild Horse": WILD_HORSE,
    "Survey Corps Mount": SURVEY_CORPS_MOUNT,
    "Titan's Growth": TITANS_GROWTH,
    "Hardening Ability": HARDENING_ABILITY,
    "Regeneration": REGENERATION,
    "Forest Ambush": FOREST_AMBUSH,
    "Colossal Strength": COLOSSAL_STRENGTH,
    "Natural Regeneration": NATURAL_REGENERATION,
    "Wild Charge": WILD_CHARGE,
    "Summon the Titans": SUMMON_THE_TITANS,
    "Titan Rampage": TITAN_RAMPAGE,
    "Primal Growth": PRIMAL_GROWTH,
    "Awakening of the Titans": AWAKENING_OF_THE_TITANS,
    "Titan's Dominion": TITANS_DOMINION,
    "Force of Nature": FORCE_OF_NATURE,
    "Hardened Skin": HARDENED_SKIN,

    # MULTICOLOR - NINE TITANS & OTHERS
    "The Founding Titan": FOUNDING_TITAN,
    "The Attack Titan": ATTACK_TITAN_CARD,
    "The Armored Titan": ARMORED_TITAN,
    "The Female Titan": FEMALE_TITAN,
    "The Colossal Titan": COLOSSAL_TITAN_LEGENDARY,
    "The Beast Titan": BEAST_TITAN_LEGENDARY,
    "The Cart Titan": CART_TITAN,
    "The Jaw Titan": JAW_TITAN_LEGENDARY,
    "The War Hammer Titan": WAR_HAMMER_TITAN_LEGENDARY,
    "Kenny Ackerman, The Ripper": KENNY_ACKERMAN,
    "Porco Galliard, Jaw Titan": PORCO_GALLIARD,
    "Marcel Galliard, Fallen Warrior": MARCEL_GALLIARD,
    "Ymir, Original Titan": YMIR,
    "Gabi Braun, Warrior Candidate": GABI_BRAUN,
    "Falco Grice, Jaw Inheritor": FALCO_GRICE,
    "Colt Grice, Beast Candidate": COLT_GRICE,
    "Uri Reiss, Founding Inheritor": URI_REISS,
    "Rod Reiss, Aberrant Titan": ROD_REISS,

    # EQUIPMENT
    "ODM Gear": ODM_GEAR,
    "Advanced ODM Gear": ADVANCED_ODM_GEAR,
    "Thunder Spear": THUNDER_SPEAR,
    "Anti-Personnel ODM Gear": ANTI_PERSONNEL_ODM_GEAR,
    "Survey Corps Cloak": SURVEY_CORPS_CLOAK,
    "Blade Set": BLADE_SET,
    "Gas Canister": GAS_CANISTER,
    "Garrison Cannon": GARRISON_CANNON,
    "Flare Gun": FLARE_GUN,

    # ARTIFACTS
    "Founding Titan Serum": FOUNDING_TITAN_SERUM,
    "Titan Serum": TITAN_SERUM,
    "Armored Titan Serum": ARMORED_TITAN_SERUM,
    "Supply Cache": SUPPLY_CACHE,
    "Signal Flare": SIGNAL_FLARE,
    "War Hammer Construct": WAR_HAMMER,
    "The Coordinate": COORDINATE,
    "Attack Titan's Memories": ATTACK_TITAN_MEMORIES,
    "Basement Key": BASEMENT_KEY,
    "Grisha's Journal": GRISHA_JOURNAL,

    # LANDS
    "Wall Maria": WALL_MARIA,
    "Wall Rose": WALL_ROSE,
    "Wall Sheena": WALL_SHEENA,
    "Shiganshina District": SHIGANSHINA_DISTRICT,
    "Trost District": TROST_DISTRICT,
    "Stohess District": STOHESS_DISTRICT,
    "Survey Corps Headquarters": SURVEY_CORPS_HQ,
    "Garrison Headquarters": GARRISON_HEADQUARTERS,
    "Military Police Headquarters": MILITARY_POLICE_HQ,
    "Paradis Island": PARADIS_ISLAND,
    "Marley": MARLEY,
    "Liberio Internment Zone": LIBERIO_INTERNMENT_ZONE,
    "Forest of Giant Trees": FOREST_OF_GIANT_TREES,
    "Utgard Castle": UTGARD_CASTLE,
    "Reiss Chapel": REISS_CHAPEL,
    "The Paths": PATHS,
    "The Ocean": OCEAN,

    # ADDITIONAL LANDS
    "Orvud District": ORVUD_DISTRICT,
    "Karanes District": KARANES_DISTRICT,
    "Ragako Village": RAGAKO_VILLAGE,
    "Underground City": UNDERGROUND_CITY,

    # ADDITIONAL WHITE
    "Nile Dok, Military Police Commander": NILE_DOK,
    "Darius Zackly, Premier": DARIUS_ZACKLY,
    "Dot Pixis, Garrison Commander": DOT_PIXIS,
    "Hannes, Garrison Captain": HANNES,
    "Carla Yeager, Eren's Mother": CARLA_YEAGER,
    "Wall Rose Garrison": WALL_ROSE_GARRISON,
    "Military Tribunal": MILITARY_TRIBUNAL,

    # ADDITIONAL BLUE
    "Moblit Berner, Hange's Assistant": MOBLIT_BERNER,
    "Onyankopon, Anti-Marleyan": ONYANKOPON,
    "Yelena, True Believer": YELENA,
    "Ilse Langnar, Titan Chronicler": ILSE_LANGNAR,
    "Information Gathering": INFORMATION_GATHERING,
    "Titan Biology": TITAN_BIOLOGY,

    # ADDITIONAL BLACK
    "Dina Fritz, Smiling Titan": DINA_FRITZ,
    "Eren Kruger, The Owl": KRUGER,
    "Sergeant Major Gross": GROSS,
    "Theo Magath, Marleyan General": MAGATH,
    "Willy Tybur, Declaration of War": WILLY_TYBUR,
    "Eldian Armband": ELDIAN_ARMBAND,

    # ADDITIONAL RED
    "Kaya, Sasha's Friend": KAYA,
    "Keith Shadis, Instructor": KEITH_SHADIS,
    "Louise, Yeagerist Devotee": LOUISE,
    "Titan Transformation": TITAN_TRANSFORMATION,
    "Declaration of War": DECLARATION_OF_WAR,

    # ADDITIONAL GREEN
    "Ymir Fritz, Source of All Titans": YMIR_FRITZ,
    "King Fritz, First Eldian King": KING_FRITZ,
    "Titan's Blessing": TITANS_BLESSING,
    "Wall Titan Army": WALL_TITAN_ARMY,

    # BASIC LANDS
    "Plains": PLAINS_AOT,
    "Island": ISLAND_AOT,
    "Swamp": SWAMP_AOT,
    "Mountain": MOUNTAIN_AOT,
    "Forest": FOREST_AOT,
}

print(f"Loaded {len(ATTACK_ON_TITAN_CARDS)} Attack on Titan cards")


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    EREN_YEAGER_SCOUT,
    MIKASA_ACKERMAN,
    ARMIN_ARLERT,
    LEVI_ACKERMAN,
    ERWIN_SMITH,
    HANGE_ZOE,
    SURVEY_CORPS_RECRUIT,
    SURVEY_CORPS_VETERAN,
    GARRISON_SOLDIER,
    MILITARY_POLICE_OFFICER,
    WALL_DEFENDER,
    TRAINING_CORPS_CADET,
    HISTORIA_REISS,
    SASHA_BLOUSE,
    CONNIE_SPRINGER,
    JEAN_KIRSTEIN,
    MICHE_ZACHARIAS,
    PETRA_RAL,
    OLUO_BOZADO,
    SQUAD_CAPTAIN,
    WALL_GARRISON_ELITE,
    INTERIOR_POLICE,
    SHIGANSHINA_CITIZEN,
    ELDIAN_REFUGEE,
    WALL_CULTIST,
    HORSE_MOUNTED_SCOUT,
    DEVOTED_HEART,
    SURVEY_CORPS_CHARGE,
    WALL_DEFENSE,
    HUMANITYS_HOPE,
    SALUTE_OF_HEARTS,
    STRATEGIC_RETREAT,
    FORMATION_BREAK,
    GARRISON_REINFORCEMENTS,
    SURVEY_MISSION,
    EVACUATION_ORDER,
    WALL_RECONSTRUCTION,
    TRAINING_EXERCISE,
    SURVEY_CORPS_BANNER,
    WINGS_OF_FREEDOM,
    WALL_FAITH,
    ARMIN_COLOSSAL_TITAN,
    ERWIN_GAMBIT,
    PIECK_FINGER,
    INTELLIGENCE_OFFICER,
    MARLEYAN_SPY,
    SURVEY_CARTOGRAPHER,
    TITAN_RESEARCHER,
    STRATEGIC_ADVISOR,
    WALL_ARCHITECT,
    MILITARY_TACTICIAN,
    SIGNAL_CORPS_OPERATOR,
    SUPPLY_CORPS_QUARTERMASTER,
    COASTAL_SCOUT,
    FORMATION_ANALYST,
    STRATEGIC_ANALYSIS,
    TACTICAL_RETREAT,
    FORMATION_SHIFT,
    COUNTER_STRATEGY,
    FLARE_SIGNAL,
    INTELLIGENCE_REPORT,
    RECONNAISSANCE,
    ESCAPE_ROUTE,
    SURVEY_THE_LAND,
    MAPPING_EXPEDITION,
    MEMORY_WIPE,
    STRATEGIC_PLANNING,
    INFORMATION_NETWORK,
    REINER_BRAUN,
    BERTHOLDT_HOOVER,
    ANNIE_LEONHART,
    ZEKE_YEAGER,
    WAR_HAMMER_TITAN,
    MARLEYAN_WARRIOR,
    WARRIOR_CANDIDATE,
    MARLEYAN_OFFICER,
    INFILTRATOR,
    ELDIAN_INTERNMENT_GUARD,
    TITAN_INHERITOR,
    MILITARY_EXECUTIONER,
    RESTORATIONIST,
    PURE_TITAN,
    ABNORMAL_TITAN,
    SMALL_TITAN,
    TITAN_HORDE,
    MINDLESS_TITAN,
    CRAWLING_TITAN,
    BETRAYAL,
    TITANS_HUNGER,
    COORDINATE_POWER,
    MEMORY_MANIPULATION,
    CRYSTALLIZATION,
    SACRIFICE_PLAY,
    WARRIOR_RESOLVE,
    TITANIZATION,
    MARLEY_INVASION,
    INHERIT_POWER,
    ELDIAN_PURGE,
    PATHS_OF_TITANS,
    WARRIOR_PROGRAM,
    MARLEYAN_DOMINION,
    EREN_ATTACK_TITAN,
    EREN_FOUNDING_TITAN,
    GRISHA_YEAGER,
    JAW_TITAN,
    BERSERKER_TITAN,
    RAGING_TITAN,
    CHARGING_TITAN,
    WALL_BREAKER,
    ELDIAN_REBEL,
    ATTACK_TITAN_ACOLYTE,
    YEAGERIST_SOLDIER,
    YEAGERIST_FANATIC,
    EXPLOSIVE_SPECIALIST,
    THUNDER_SPEAR_TROOPER,
    CANNON_OPERATOR,
    FLOCH_FORSTER,
    TITANS_RAGE,
    THUNDER_SPEAR_STRIKE,
    WALL_BOMBARDMENT,
    COORDINATE_ATTACK,
    DESPERATE_CHARGE,
    BURNING_WILL,
    CANNON_BARRAGE,
    THE_RUMBLING,
    TITANS_FURY,
    BREACH_THE_WALL,
    RALLY_THE_YEAGERISTS,
    ATTACK_ON_TITAN,
    RAGE_OF_THE_TITANS,
    FOUNDING_TITAN_POWER,
    BEAST_TITAN,
    COLOSSAL_TITAN,
    TOM_KSAVER,
    WALL_TITAN,
    FOREST_TITAN,
    TOWERING_TITAN,
    ANCIENT_TITAN,
    PRIMORDIAL_TITAN,
    FOREST_DWELLER,
    PARADIS_FARMER,
    TITAN_HUNTER,
    FOREST_SCOUT,
    ELDIAN_WOODCUTTER,
    WILD_HORSE,
    SURVEY_CORPS_MOUNT,
    TITANS_GROWTH,
    HARDENING_ABILITY,
    REGENERATION,
    FOREST_AMBUSH,
    COLOSSAL_STRENGTH,
    NATURAL_REGENERATION,
    WILD_CHARGE,
    SUMMON_THE_TITANS,
    TITAN_RAMPAGE,
    PRIMAL_GROWTH,
    AWAKENING_OF_THE_TITANS,
    TITANS_DOMINION,
    FORCE_OF_NATURE,
    HARDENED_SKIN,
    FOUNDING_TITAN,
    ATTACK_TITAN_CARD,
    ARMORED_TITAN,
    FEMALE_TITAN,
    COLOSSAL_TITAN_LEGENDARY,
    BEAST_TITAN_LEGENDARY,
    CART_TITAN,
    JAW_TITAN_LEGENDARY,
    WAR_HAMMER_TITAN_LEGENDARY,
    KENNY_ACKERMAN,
    PORCO_GALLIARD,
    MARCEL_GALLIARD,
    YMIR,
    GABI_BRAUN,
    FALCO_GRICE,
    COLT_GRICE,
    URI_REISS,
    ROD_REISS,
    ODM_GEAR,
    ADVANCED_ODM_GEAR,
    THUNDER_SPEAR,
    ANTI_PERSONNEL_ODM_GEAR,
    SURVEY_CORPS_CLOAK,
    BLADE_SET,
    GAS_CANISTER,
    GARRISON_CANNON,
    FLARE_GUN,
    FOUNDING_TITAN_SERUM,
    TITAN_SERUM,
    ARMORED_TITAN_SERUM,
    SUPPLY_CACHE,
    SIGNAL_FLARE,
    WAR_HAMMER,
    COORDINATE,
    ATTACK_TITAN_MEMORIES,
    BASEMENT_KEY,
    GRISHA_JOURNAL,
    WALL_MARIA,
    WALL_ROSE,
    WALL_SHEENA,
    SHIGANSHINA_DISTRICT,
    TROST_DISTRICT,
    STOHESS_DISTRICT,
    SURVEY_CORPS_HQ,
    GARRISON_HEADQUARTERS,
    MILITARY_POLICE_HQ,
    PARADIS_ISLAND,
    MARLEY,
    LIBERIO_INTERNMENT_ZONE,
    FOREST_OF_GIANT_TREES,
    UTGARD_CASTLE,
    REISS_CHAPEL,
    PATHS,
    OCEAN,
    ORVUD_DISTRICT,
    KARANES_DISTRICT,
    RAGAKO_VILLAGE,
    UNDERGROUND_CITY,
    NILE_DOK,
    DARIUS_ZACKLY,
    DOT_PIXIS,
    HANNES,
    CARLA_YEAGER,
    WALL_ROSE_GARRISON,
    MILITARY_TRIBUNAL,
    MOBLIT_BERNER,
    ONYANKOPON,
    YELENA,
    ILSE_LANGNAR,
    INFORMATION_GATHERING,
    TITAN_BIOLOGY,
    DINA_FRITZ,
    KRUGER,
    GROSS,
    MAGATH,
    WILLY_TYBUR,
    ELDIAN_ARMBAND,
    KAYA,
    KEITH_SHADIS,
    LOUISE,
    TITAN_TRANSFORMATION,
    DECLARATION_OF_WAR,
    YMIR_FRITZ,
    KING_FRITZ,
    TITANS_BLESSING,
    WALL_TITAN_ARMY,
    PLAINS_AOT,
    ISLAND_AOT,
    SWAMP_AOT,
    MOUNTAIN_AOT,
    FOREST_AOT
]
