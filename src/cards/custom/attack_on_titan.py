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


def make_artifact(name: str, mana_cost: str, text: str, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
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


def make_equipment(name: str, mana_cost: str, text: str, equip_cost: str, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
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
        setup_interceptors=setup_interceptors
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
    def is_self(target: GameObject, state: GameState) -> bool:
        return target.id == source_obj.id

    interceptors = []
    interceptors.append(make_keyword_grant(source_obj, ['defender'], is_self))
    interceptors.extend(make_static_pt_boost(source_obj, 0, toughness_bonus, is_self))
    return interceptors


def scout_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Scout")


def soldier_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Soldier")


def titan_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Titan")


def warrior_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Warrior")


# =============================================================================
# WHITE CARDS - SURVEY CORPS, HUMANITY'S HOPE
# =============================================================================

# --- Legendary Creatures ---

def eren_yeager_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack trigger - other Scouts get +1/+0"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'boost': 'scouts_plus_one', 'controller': obj.controller, 'duration': 'end_of_turn'},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]

EREN_YEAGER_SCOUT = make_creature(
    name="Eren Yeager, Survey Corps",
    power=3, toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    text="Haste. Whenever Eren attacks, other Scout creatures you control get +1/+0 until end of turn.",
    setup_interceptors=eren_yeager_setup
)


def mikasa_ackerman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """First strike, protection from Titans"""
    interceptors = []
    def is_self(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    interceptors.append(make_keyword_grant(obj, ['first_strike'], is_self))
    return interceptors

MIKASA_ACKERMAN = make_creature(
    name="Mikasa Ackerman, Humanity's Strongest",
    power=4, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier", "Ackerman"},
    supertypes={"Legendary"},
    text="First strike, vigilance. Mikasa Ackerman has protection from Titans.",
    setup_interceptors=mikasa_ackerman_setup
)


def armin_arlert_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - scry 2, then draw"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 2}, source=obj.id),
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

ARMIN_ARLERT = make_creature(
    name="Armin Arlert, Tactician",
    power=1, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Scout", "Advisor"},
    supertypes={"Legendary"},
    text="When Armin enters, scry 2, then draw a card.",
    setup_interceptors=armin_arlert_setup
)


def levi_ackerman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Double strike, other Scouts get +1/+1"""
    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Scout")))
    return interceptors

LEVI_ACKERMAN = make_creature(
    name="Levi Ackerman, Captain",
    power=4, toughness=4,
    mana_cost="{2}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier", "Ackerman"},
    supertypes={"Legendary"},
    text="Double strike, flying. Other Scout creatures you control get +1/+1.",
    setup_interceptors=levi_ackerman_setup
)


def erwin_smith_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack trigger - Scouts gain indestructible"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'boost': 'scouts_indestructible', 'controller': obj.controller, 'duration': 'end_of_turn'},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]

ERWIN_SMITH = make_creature(
    name="Erwin Smith, Commander",
    power=3, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Noble"},
    supertypes={"Legendary"},
    text="Vigilance. Whenever Erwin attacks, Scout creatures you control gain indestructible until end of turn.",
    setup_interceptors=erwin_smith_setup
)


def hange_zoe_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a Titan dies, draw a card"""
    def titan_death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if not dying:
            return False
        return 'Titan' in dying.characteristics.subtypes

    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: titan_death_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=draw_effect(e, s)),
        duration='while_on_battlefield'
    )]

HANGE_ZOE = make_creature(
    name="Hange Zoe, Researcher",
    power=2, toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Scout", "Artificer"},
    supertypes={"Legendary"},
    text="Whenever a Titan dies, draw a card.",
    setup_interceptors=hange_zoe_setup
)


# --- Regular Creatures ---

def survey_corps_recruit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - gain 2 life"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

SURVEY_CORPS_RECRUIT = make_creature(
    name="Survey Corps Recruit",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    text="When Survey Corps Recruit enters, you gain 2 life.",
    setup_interceptors=survey_corps_recruit_setup
)


SURVEY_CORPS_VETERAN = make_creature(
    name="Survey Corps Veteran",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    text="First strike. Whenever Survey Corps Veteran deals combat damage to a Titan, draw a card."
)


def garrison_soldier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Defender, when blocks gain 2 life"""
    def block_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]

    def block_filter(event: Event, state: GameState, source: GameObject) -> bool:
        return (event.type == EventType.BLOCK_DECLARED and
                event.payload.get('blocker_id') == source.id)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: block_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=block_effect(e, s)),
        duration='while_on_battlefield'
    )]

GARRISON_SOLDIER = make_creature(
    name="Garrison Soldier",
    power=1, toughness=4,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Defender. Whenever Garrison Soldier blocks, you gain 2 life.",
    setup_interceptors=garrison_soldier_setup
)


MILITARY_POLICE_OFFICER = make_creature(
    name="Military Police Officer",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Noble"},
    text="Lifelink."
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
    text="Defender. Wall Defender gets +0/+2.",
    setup_interceptors=wall_defender_setup
)


TRAINING_CORPS_CADET = make_creature(
    name="Training Corps Cadet",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="When Training Corps Cadet dies, you may search your library for a Scout card, reveal it, and put it into your hand."
)


def historia_reiss_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Humans get +1/+1"""
    return make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Human"))

HISTORIA_REISS = make_creature(
    name="Historia Reiss, True Queen",
    power=2, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Other Human creatures you control get +1/+1.",
    setup_interceptors=historia_reiss_setup
)


SASHA_BLOUSE = make_creature(
    name="Sasha Blouse, Hunter",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    text="Reach. When Sasha enters, create a Food token."
)


CONNIE_SPRINGER = make_creature(
    name="Connie Springer, Loyal Friend",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    text="Haste. Whenever another Scout you control dies, Connie gets +1/+1 until end of turn."
)


JEAN_KIRSTEIN = make_creature(
    name="Jean Kirstein, Natural Leader",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    text="First strike. Other Scout creatures you control have vigilance."
)


MICHE_ZACHARIAS = make_creature(
    name="Miche Zacharias, Squad Leader",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    text="Vigilance. Miche Zacharias can block an additional creature each combat."
)


PETRA_RAL = make_creature(
    name="Petra Ral, Levi Squad",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    text="Flying. When Petra Ral dies, target Scout creature you control gains indestructible until end of turn."
)


OLUO_BOZADO = make_creature(
    name="Oluo Bozado, Levi Squad",
    power=3, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    supertypes={"Legendary"},
    text="First strike. Oluo Bozado gets +2/+0 as long as you control Levi Ackerman."
)


SQUAD_CAPTAIN = make_creature(
    name="Squad Captain",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    text="When Squad Captain enters, create a 1/1 white Human Scout Soldier creature token."
)


WALL_GARRISON_ELITE = make_creature(
    name="Wall Garrison Elite",
    power=2, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Defender, vigilance. {2}{W}: Wall Garrison Elite can attack this turn as though it didn't have defender."
)


INTERIOR_POLICE = make_creature(
    name="Interior Police",
    power=2, toughness=2,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Rogue"},
    text="Flash. When Interior Police enters, exile target creature an opponent controls until Interior Police leaves the battlefield."
)


SHIGANSHINA_CITIZEN = make_creature(
    name="Shiganshina Citizen",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    text="When Shiganshina Citizen dies, you gain 2 life."
)


ELDIAN_REFUGEE = make_creature(
    name="Eldian Refugee",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    text="When Eldian Refugee enters, you may return target Scout creature card with mana value 2 or less from your graveyard to your hand."
)


WALL_CULTIST = make_creature(
    name="Wall Cultist",
    power=0, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    text="Defender. {T}: You gain 1 life for each Wall you control."
)


HORSE_MOUNTED_SCOUT = make_creature(
    name="Horse Mounted Scout",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout", "Soldier"},
    text="Haste. Horse Mounted Scout can't be blocked by creatures with power 4 or greater."
)


# --- Instants ---

DEVOTED_HEART = make_instant(
    name="Devoted Heart",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gains indestructible until end of turn. If it's a Scout, you also gain 3 life."
)


SURVEY_CORPS_CHARGE = make_instant(
    name="Survey Corps Charge",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +2/+1 until end of turn. Scout creatures you control also gain first strike until end of turn."
)


WALL_DEFENSE = make_instant(
    name="Wall Defense",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +0/+3 and gain vigilance until end of turn."
)


HUMANITYS_HOPE = make_instant(
    name="Humanity's Hope",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Exile target attacking creature. You gain life equal to its power."
)


SALUTE_OF_HEARTS = make_instant(
    name="Salute of Hearts",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target Scout creature gets +2/+2 until end of turn. If you control a commander, draw a card."
)


STRATEGIC_RETREAT = make_instant(
    name="Strategic Retreat",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Return up to two target creatures you control to their owner's hand. You gain 2 life."
)


FORMATION_BREAK = make_instant(
    name="Formation Break",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gains flying until end of turn. Draw a card."
)


GARRISON_REINFORCEMENTS = make_instant(
    name="Garrison Reinforcements",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Create three 1/1 white Human Soldier creature tokens with defender."
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

def survey_corps_banner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Scouts get +1/+1"""
    return make_static_pt_boost(obj, 1, 1, creatures_with_subtype(obj, "Scout"))

SURVEY_CORPS_BANNER = make_enchantment(
    name="Survey Corps Banner",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Scout creatures you control get +1/+1. At the beginning of your end step, if you control four or more Scouts, create a 1/1 white Human Scout Soldier creature token.",
    setup_interceptors=survey_corps_banner_setup
)


WINGS_OF_FREEDOM = make_enchantment(
    name="Wings of Freedom",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Scout creatures you control have flying and can't be sacrificed."
)


WALL_FAITH = make_enchantment(
    name="Wall Faith",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="At the beginning of your upkeep, you gain 1 life for each Wall you control. Creatures with defender you control get +0/+2."
)


# =============================================================================
# BLUE CARDS - STRATEGY, PLANNING, INTELLIGENCE
# =============================================================================

# --- Legendary Creatures ---

def armin_colossal_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - each opponent sacrifices a creature"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for p_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.SACRIFICE,
                payload={'player': p_id, 'type': 'creature'},
                source=obj.id
            ))
        return events
    return [make_etb_trigger(obj, etb_effect)]

ARMIN_COLOSSAL_TITAN = make_creature(
    name="Armin, Colossal Titan",
    power=10, toughness=10,
    mana_cost="{5}{U}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    text="Trample. When Armin enters, each opponent sacrifices a creature.",
    setup_interceptors=armin_colossal_setup
)


def erwin_gambit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an instant or sorcery, scry 1"""
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_spell_cast_trigger(obj, spell_effect, spell_type_filter={CardType.INSTANT, CardType.SORCERY})]

ERWIN_GAMBIT = make_creature(
    name="Erwin Smith, The Gambit",
    power=2, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout", "Noble"},
    supertypes={"Legendary"},
    text="Whenever you cast an instant or sorcery spell, scry 1. {U}: Draw a card, then discard a card.",
    setup_interceptors=erwin_gambit_setup
)


def pieck_finger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Can't be blocked"""
    def is_self(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    return [make_keyword_grant(obj, ['unblockable'], is_self)]

PIECK_FINGER = make_creature(
    name="Pieck Finger, Cart Titan",
    power=3, toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    text="Pieck Finger can't be blocked. {2}{U}: Return Pieck to her owner's hand.",
    setup_interceptors=pieck_finger_setup
)


# --- Regular Creatures ---

def intelligence_officer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - scry 2"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

INTELLIGENCE_OFFICER = make_creature(
    name="Intelligence Officer",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout", "Advisor"},
    text="When Intelligence Officer enters, scry 2.",
    setup_interceptors=intelligence_officer_setup
)


MARLEYAN_SPY = make_creature(
    name="Marleyan Spy",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="Marleyan Spy can't be blocked. When Marleyan Spy deals combat damage to a player, draw a card."
)


SURVEY_CARTOGRAPHER = make_creature(
    name="Survey Cartographer",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout"},
    text="{T}: Scry 1. If you control three or more Scouts, scry 2 instead."
)


TITAN_RESEARCHER = make_creature(
    name="Titan Researcher",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Artificer"},
    text="Whenever a Titan enters under any player's control, draw a card."
)


STRATEGIC_ADVISOR = make_creature(
    name="Strategic Advisor",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Advisor"},
    text="At the beginning of combat on your turn, you may have target creature gain flying until end of turn."
)


WALL_ARCHITECT = make_creature(
    name="Wall Architect",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Artificer"},
    text="When Wall Architect enters, create a 0/4 white Wall artifact creature token with defender."
)


MILITARY_TACTICIAN = make_creature(
    name="Military Tactician",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Soldier", "Advisor"},
    text="Flash. When Military Tactician enters, tap target creature an opponent controls."
)


SIGNAL_CORPS_OPERATOR = make_creature(
    name="Signal Corps Operator",
    power=1, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Soldier"},
    text="{T}, Sacrifice Signal Corps Operator: Draw a card."
)


SUPPLY_CORPS_QUARTERMASTER = make_creature(
    name="Supply Corps Quartermaster",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Soldier"},
    text="Artifact spells you cast cost {1} less to cast."
)


COASTAL_SCOUT = make_creature(
    name="Coastal Scout",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout"},
    text="Flying. When Coastal Scout deals combat damage to a player, scry 1."
)


FORMATION_ANALYST = make_creature(
    name="Formation Analyst",
    power=0, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Advisor"},
    text="Defender. {T}: Look at the top card of target player's library."
)


# --- Instants ---

STRATEGIC_ANALYSIS = make_instant(
    name="Strategic Analysis",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Draw two cards."
)


TACTICAL_RETREAT = make_instant(
    name="Tactical Retreat",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Return target creature to its owner's hand. Scry 1."
)


FORMATION_SHIFT = make_instant(
    name="Formation Shift",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target creature you control to its owner's hand. Draw a card."
)


COUNTER_STRATEGY = make_instant(
    name="Counter Strategy",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell."
)


FLARE_SIGNAL = make_instant(
    name="Flare Signal",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Tap or untap target creature. Draw a card."
)


INTELLIGENCE_REPORT = make_instant(
    name="Intelligence Report",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw two cards. If you control a Scout, draw three cards instead."
)


RECONNAISSANCE = make_instant(
    name="Reconnaissance",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Look at the top three cards of your library. Put one into your hand and the rest on the bottom in any order."
)


ESCAPE_ROUTE = make_instant(
    name="Escape Route",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target creature you control and target creature you don't control to their owners' hands."
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
    text="At the beginning of your upkeep, scry 1. Whenever you scry, if you put one or more cards on the bottom of your library, draw a card."
)


INFORMATION_NETWORK = make_enchantment(
    name="Information Network",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Whenever a creature enters under an opponent's control, scry 1."
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
    text="Indestructible. Titan Shift {3}: Reiner becomes a 6/6 until end of turn. Pay 3 life.",
    setup_interceptors=reiner_braun_setup
)


def bertholdt_hoover_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - deal 5 damage to each creature"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': 'all_creatures', 'amount': 5, 'source': obj.id},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

BERTHOLDT_HOOVER = make_creature(
    name="Bertholdt Hoover, Colossal Titan",
    power=10, toughness=10,
    mana_cost="{6}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    text="Trample. When Bertholdt enters, he deals 5 damage to each other creature.",
    setup_interceptors=bertholdt_hoover_setup
)


def annie_leonhart_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch, can crystallize"""
    def is_self(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    return [make_keyword_grant(obj, ['deathtouch'], is_self)]

ANNIE_LEONHART = make_creature(
    name="Annie Leonhart, Female Titan",
    power=5, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    text="Deathtouch. {2}{B}: Annie gains hexproof and indestructible until end of turn. Tap her.",
    setup_interceptors=annie_leonhart_setup
)


def zeke_yeager_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Titans get +2/+2"""
    return make_static_pt_boost(obj, 2, 2, other_creatures_with_subtype(obj, "Titan"))

ZEKE_YEAGER = make_creature(
    name="Zeke Yeager, Beast Titan",
    power=6, toughness=6,
    mana_cost="{4}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    text="Reach, trample. Other Titan creatures you control get +2/+2.",
    setup_interceptors=zeke_yeager_setup
)


def war_hammer_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Can create weapon tokens"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Hardened Weapon', 'power': 0, 'toughness': 0, 'types': {CardType.ARTIFACT}, 'subtypes': {'Equipment'}}
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

WAR_HAMMER_TITAN = make_creature(
    name="War Hammer Titan",
    power=5, toughness=5,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    text="When War Hammer Titan enters, create a colorless Equipment artifact token with 'Equipped creature gets +3/+0 and has first strike. Equip {2}.'",
    setup_interceptors=war_hammer_titan_setup
)


# --- Regular Creatures ---

def marleyan_warrior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace"""
    def is_self(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    return [make_keyword_grant(obj, ['menace'], is_self)]

MARLEYAN_WARRIOR = make_creature(
    name="Marleyan Warrior",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior", "Soldier"},
    text="Menace.",
    setup_interceptors=marleyan_warrior_setup
)


def warrior_candidate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death trigger - opponent loses 2 life"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for p_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': p_id, 'amount': -2}, source=obj.id))
        return events
    return [make_death_trigger(obj, death_effect)]

WARRIOR_CANDIDATE = make_creature(
    name="Warrior Candidate",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior"},
    text="When Warrior Candidate dies, each opponent loses 2 life.",
    setup_interceptors=warrior_candidate_setup
)


MARLEYAN_OFFICER = make_creature(
    name="Marleyan Officer",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    text="Deathtouch."
)


INFILTRATOR = make_creature(
    name="Infiltrator",
    power=2, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="Infiltrator can't be blocked. When Infiltrator deals combat damage to a player, that player discards a card."
)


ELDIAN_INTERNMENT_GUARD = make_creature(
    name="Eldian Internment Guard",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    text="Whenever a creature an opponent controls dies, you gain 1 life."
)


TITAN_INHERITOR = make_creature(
    name="Titan Inheritor",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior"},
    text="When Titan Inheritor enters, you may sacrifice a creature. If you do, draw two cards."
)


MILITARY_EXECUTIONER = make_creature(
    name="Military Executioner",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    text="When Military Executioner enters, destroy target creature with power 2 or less."
)


RESTORATIONIST = make_creature(
    name="Restorationist",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Cleric"},
    text="{2}{B}, {T}, Sacrifice Restorationist: Return target creature card from your graveyard to your hand."
)


PURE_TITAN = make_creature(
    name="Pure Titan",
    power=4, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    text="Pure Titan attacks each combat if able."
)


ABNORMAL_TITAN = make_creature(
    name="Abnormal Titan",
    power=5, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    text="Haste. Abnormal Titan attacks each combat if able. When Abnormal Titan dies, each player sacrifices a creature."
)


SMALL_TITAN = make_creature(
    name="Small Titan",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    text="Small Titan attacks each combat if able."
)


TITAN_HORDE = make_creature(
    name="Titan Horde",
    power=6, toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    text="Trample. When Titan Horde enters, create two 2/2 black Titan creature tokens. Titans you control attack each combat if able."
)


MINDLESS_TITAN = make_creature(
    name="Mindless Titan",
    power=3, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    text="Mindless Titan attacks each combat if able. Mindless Titan can't block."
)


CRAWLING_TITAN = make_creature(
    name="Crawling Titan",
    power=2, toughness=4,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    text="Crawling Titan attacks each combat if able. When Crawling Titan dies, each opponent loses 2 life."
)


# --- Instants ---

BETRAYAL = make_instant(
    name="Betrayal",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. Its controller loses life equal to its toughness."
)


TITANS_HUNGER = make_instant(
    name="Titan's Hunger",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Target creature gets -3/-3 until end of turn. You gain 3 life."
)


COORDINATE_POWER = make_instant(
    name="Coordinate Power",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gets +2/+0 until end of turn. If it's a Titan, it also gains menace until end of turn."
)


MEMORY_MANIPULATION = make_instant(
    name="Memory Manipulation",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target player discards two cards. If you control a Warrior, you draw a card."
)


CRYSTALLIZATION = make_instant(
    name="Crystallization",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gains hexproof and indestructible until end of turn. Tap it."
)


SACRIFICE_PLAY = make_instant(
    name="Sacrifice Play",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost, sacrifice a creature. Draw two cards."
)


WARRIOR_RESOLVE = make_instant(
    name="Warrior's Resolve",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gains indestructible until end of turn. You lose 2 life."
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

def paths_of_titans_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a Titan dies, draw a card"""
    def titan_death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if not dying:
            return False
        return 'Titan' in dying.characteristics.subtypes

    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: titan_death_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=draw_effect(e, s)),
        duration='while_on_battlefield'
    )]

PATHS_OF_TITANS = make_enchantment(
    name="Paths of Titans",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Whenever a Titan dies, you draw a card and each opponent loses 1 life.",
    setup_interceptors=paths_of_titans_setup
)


WARRIOR_PROGRAM = make_enchantment(
    name="Warrior Program",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Warrior creatures you control get +1/+1. At the beginning of your upkeep, you may pay 2 life. If you do, create a 2/2 black Warrior creature token."
)


MARLEYAN_DOMINION = make_enchantment(
    name="Marleyan Dominion",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="At the beginning of each opponent's upkeep, that player sacrifices a creature unless they pay 2 life."
)


# =============================================================================
# RED CARDS - ATTACK TITAN, RAGE, DESTRUCTION
# =============================================================================

# --- Legendary Creatures ---

def eren_attack_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack trigger - deal 2 damage to any target"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': 'any', 'amount': 2, 'source': obj.id},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]

EREN_ATTACK_TITAN = make_creature(
    name="Eren Yeager, Attack Titan",
    power=6, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    text="Haste, trample. Whenever Eren attacks, he deals 2 damage to any target.",
    setup_interceptors=eren_attack_titan_setup
)


def eren_founding_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Titans get +3/+3 and have haste"""
    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 3, 3, other_creatures_with_subtype(obj, "Titan")))
    interceptors.append(make_keyword_grant(obj, ['haste'], other_creatures_with_subtype(obj, "Titan")))
    return interceptors

EREN_FOUNDING_TITAN = make_creature(
    name="Eren Yeager, Founding Titan",
    power=10, toughness=10,
    mana_cost="{5}{R}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    text="Trample, indestructible. Other Titan creatures you control get +3/+3 and have haste.",
    setup_interceptors=eren_founding_setup
)


def grisha_yeager_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death trigger - search for Titan"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SEARCH,
            payload={'player': obj.controller, 'search': 'Titan', 'zone': ZoneType.LIBRARY},
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]

GRISHA_YEAGER = make_creature(
    name="Grisha Yeager, Rogue Titan",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    text="Haste. When Grisha dies, you may search your library for a Titan card, reveal it, and put it into your hand.",
    setup_interceptors=grisha_yeager_setup
)


JAW_TITAN = make_creature(
    name="Jaw Titan",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="Haste, first strike. Jaw Titan gets +2/+0 as long as it's attacking."
)


# --- Regular Creatures ---

def berserker_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Double strike when attacking"""
    def is_attacking(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id and state.combat and obj.id in state.combat.attackers
    return [make_keyword_grant(obj, ['double_strike'], is_attacking)]

BERSERKER_TITAN = make_creature(
    name="Berserker Titan",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Titan"},
    text="Berserker Titan has double strike as long as it's attacking.",
    setup_interceptors=berserker_titan_setup
)


RAGING_TITAN = make_creature(
    name="Raging Titan",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Titan"},
    text="Trample, haste. Raging Titan attacks each combat if able."
)


CHARGING_TITAN = make_creature(
    name="Charging Titan",
    power=4, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Titan"},
    text="Haste. When Charging Titan enters, it deals 2 damage to target creature."
)


WALL_BREAKER = make_creature(
    name="Wall Breaker",
    power=6, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Titan"},
    text="Trample. Wall Breaker can't be blocked by creatures with defender."
)


ELDIAN_REBEL = make_creature(
    name="Eldian Rebel",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="Haste. When Eldian Rebel dies, it deals 1 damage to any target."
)


ATTACK_TITAN_ACOLYTE = make_creature(
    name="Attack Titan Acolyte",
    power=3, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="First strike. Whenever Attack Titan Acolyte deals combat damage to a player, you may discard a card. If you do, draw a card."
)


YEAGERIST_SOLDIER = make_creature(
    name="Yeagerist Soldier",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="Haste. Yeagerist Soldier gets +2/+0 as long as you control Eren Yeager."
)


YEAGERIST_FANATIC = make_creature(
    name="Yeagerist Fanatic",
    power=3, toughness=1,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="Haste. When Yeagerist Fanatic enters, it deals 2 damage to any target and 1 damage to you."
)


EXPLOSIVE_SPECIALIST = make_creature(
    name="Explosive Specialist",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier", "Artificer"},
    text="{T}, Sacrifice Explosive Specialist: It deals 3 damage to target creature."
)


THUNDER_SPEAR_TROOPER = make_creature(
    name="Thunder Spear Trooper",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Scout", "Soldier"},
    text="When Thunder Spear Trooper enters, it deals 3 damage to target Titan."
)


CANNON_OPERATOR = make_creature(
    name="Cannon Operator",
    power=1, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="{T}: Cannon Operator deals 2 damage to target attacking or blocking creature."
)


FLOCH_FORSTER = make_creature(
    name="Floch Forster, Yeagerist Leader",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Haste. Other Soldiers you control get +1/+0. Whenever another creature you control dies, Floch gets +1/+0 until end of turn."
)


# --- Instants ---

TITANS_RAGE = make_instant(
    name="Titan's Rage",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains trample until end of turn. If it's a Titan, it also gains indestructible until end of turn."
)


THUNDER_SPEAR_STRIKE = make_instant(
    name="Thunder Spear Strike",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Thunder Spear Strike deals 4 damage to target creature. If that creature is a Titan, Thunder Spear Strike deals 6 damage instead."
)


WALL_BOMBARDMENT = make_instant(
    name="Wall Bombardment",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Wall Bombardment deals 4 damage to target creature and 2 damage to its controller."
)


COORDINATE_ATTACK = make_instant(
    name="Coordinate Attack",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +2/+0 until end of turn. Draw a card."
)


DESPERATE_CHARGE = make_instant(
    name="Desperate Charge",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Creatures you control get +2/+0 and gain haste until end of turn."
)


BURNING_WILL = make_instant(
    name="Burning Will",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +3/+1 until end of turn."
)


CANNON_BARRAGE = make_instant(
    name="Cannon Barrage",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Cannon Barrage deals 3 damage divided as you choose among one, two, or three targets."
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

def attack_on_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Titans get +2/+0"""
    return make_static_pt_boost(obj, 2, 0, creatures_with_subtype(obj, "Titan"))

ATTACK_ON_TITAN = make_enchantment(
    name="Attack on Titan",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Titan creatures you control get +2/+0 and have haste.",
    setup_interceptors=attack_on_titan_setup
)


RAGE_OF_THE_TITANS = make_enchantment(
    name="Rage of the Titans",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Whenever a creature you control attacks, it gets +1/+0 until end of turn."
)


FOUNDING_TITAN_POWER = make_enchantment(
    name="Founding Titan's Power",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="At the beginning of your upkeep, create a 4/4 red Titan creature token with trample. Titans you control attack each combat if able."
)


# =============================================================================
# GREEN CARDS - COLOSSAL FORCES, BEAST TITAN, NATURE
# =============================================================================

# --- Legendary Creatures ---

def beast_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach, can throw boulders"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': 'any_creature', 'amount': 3, 'source': obj.id},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]

BEAST_TITAN = make_creature(
    name="Beast Titan",
    power=7, toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="Reach, trample. Whenever Beast Titan attacks, it deals 3 damage to target creature.",
    setup_interceptors=beast_titan_setup
)


def colossal_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - deal damage equal to power to each creature"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': 'all_other_creatures', 'amount': 10, 'source': obj.id},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

COLOSSAL_TITAN = make_creature(
    name="Colossal Titan",
    power=10, toughness=10,
    mana_cost="{7}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="Trample. When Colossal Titan enters, it deals 10 damage to each other creature.",
    setup_interceptors=colossal_titan_setup
)


TOM_KSAVER = make_creature(
    name="Tom Ksaver, Beast Inheritor",
    power=2, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    text="When Tom Ksaver enters, you may search your library for a Titan card, reveal it, and put it into your hand."
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
    text="Defender. Wall Titan gets +0/+4.",
    setup_interceptors=wall_titan_setup
)


FOREST_TITAN = make_creature(
    name="Forest Titan",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan"},
    text="Trample, reach."
)


TOWERING_TITAN = make_creature(
    name="Towering Titan",
    power=8, toughness=8,
    mana_cost="{6}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan"},
    text="Trample. Towering Titan can't be blocked by creatures with power 2 or less."
)


ANCIENT_TITAN = make_creature(
    name="Ancient Titan",
    power=7, toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan"},
    text="Trample. When Ancient Titan enters, put a +1/+1 counter on each other creature you control."
)


def primordial_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - search for land"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SEARCH,
            payload={'player': obj.controller, 'search': 'land', 'zone': ZoneType.BATTLEFIELD},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

PRIMORDIAL_TITAN = make_creature(
    name="Primordial Titan",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Titan"},
    text="Trample. When Primordial Titan enters, search your library for a land card and put it onto the battlefield tapped.",
    setup_interceptors=primordial_titan_setup
)


FOREST_DWELLER = make_creature(
    name="Forest Dweller",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human"},
    text="{T}: Add {G}."
)


PARADIS_FARMER = make_creature(
    name="Paradis Farmer",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Citizen"},
    text="{T}: Add {G}. Spend this mana only to cast creature spells."
)


TITAN_HUNTER = make_creature(
    name="Titan Hunter",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout"},
    text="Reach. Titan Hunter gets +2/+2 as long as you control no other creatures."
)


FOREST_SCOUT = make_creature(
    name="Forest Scout",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout"},
    text="When Forest Scout enters, you may search your library for a basic land card, reveal it, and put it into your hand."
)


ELDIAN_WOODCUTTER = make_creature(
    name="Eldian Woodcutter",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Citizen"},
    text="{T}: Add {G}{G}. Activate only if you control a creature with power 5 or greater."
)


WILD_HORSE = make_creature(
    name="Wild Horse",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Horse"},
    text="Haste. When Wild Horse enters, target creature gains haste until end of turn."
)


SURVEY_CORPS_MOUNT = make_creature(
    name="Survey Corps Mount",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Horse"},
    text="When Survey Corps Mount enters, target Scout creature gets +1/+1 and gains trample until end of turn."
)


# --- Instants ---

TITANS_GROWTH = make_instant(
    name="Titan's Growth",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +4/+4 until end of turn."
)


HARDENING_ABILITY = make_instant(
    name="Hardening Ability",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +0/+5 and gains indestructible until end of turn."
)


REGENERATION = make_instant(
    name="Regeneration",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Regenerate target creature. If it's a Titan, put two +1/+1 counters on it."
)


FOREST_AMBUSH = make_instant(
    name="Forest Ambush",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Target creature you control fights target creature you don't control. Your creature gets +2/+2 until end of turn first."
)


COLOSSAL_STRENGTH = make_instant(
    name="Colossal Strength",
    mana_cost="{G}{G}",
    colors={Color.GREEN},
    text="Target creature gets +4/+4 and gains trample until end of turn."
)


NATURAL_REGENERATION = make_instant(
    name="Natural Regeneration",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Put a +1/+1 counter on each creature you control."
)


WILD_CHARGE = make_instant(
    name="Wild Charge",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +2/+2 and gains trample until end of turn."
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

def titans_dominion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Titans get +2/+2"""
    return make_static_pt_boost(obj, 2, 2, creatures_with_subtype(obj, "Titan"))

TITANS_DOMINION = make_enchantment(
    name="Titan's Dominion",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Titan creatures you control get +2/+2 and have trample.",
    setup_interceptors=titans_dominion_setup
)


FORCE_OF_NATURE = make_enchantment(
    name="Force of Nature",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="At the beginning of your upkeep, put a +1/+1 counter on target creature you control."
)


HARDENED_SKIN = make_enchantment(
    name="Hardened Skin",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Enchanted creature gets +0/+4 and has hexproof."
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
    text="Indestructible, trample, hexproof. When The Founding Titan enters, you control all Titan creatures until end of turn. At the beginning of your upkeep, create a 6/6 colorless Titan creature token."
)


ATTACK_TITAN_CARD = make_creature(
    name="The Attack Titan",
    power=8, toughness=6,
    mana_cost="{3}{R}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="Haste, trample. Whenever The Attack Titan attacks, it gets +3/+0 and gains indestructible until end of turn."
)


ARMORED_TITAN = make_creature(
    name="The Armored Titan",
    power=6, toughness=8,
    mana_cost="{3}{B}{B}{W}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="Indestructible. The Armored Titan can't be blocked except by three or more creatures."
)


FEMALE_TITAN = make_creature(
    name="The Female Titan",
    power=6, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="First strike, deathtouch. {2}{B}: The Female Titan gains hexproof until end of turn."
)


COLOSSAL_TITAN_LEGENDARY = make_creature(
    name="The Colossal Titan",
    power=15, toughness=15,
    mana_cost="{7}{B}{G}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="Trample. When The Colossal Titan enters, it deals 10 damage to each creature and each opponent."
)


BEAST_TITAN_LEGENDARY = make_creature(
    name="The Beast Titan",
    power=8, toughness=8,
    mana_cost="{4}{B}{G}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="Reach, trample. Other Titan creatures you control get +2/+2. {T}: The Beast Titan deals 4 damage to target creature with flying."
)


CART_TITAN = make_creature(
    name="The Cart Titan",
    power=3, toughness=6,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="The Cart Titan can't be blocked. Whenever The Cart Titan deals combat damage to a player, draw two cards."
)


JAW_TITAN_LEGENDARY = make_creature(
    name="The Jaw Titan",
    power=5, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="Haste, first strike. Whenever The Jaw Titan attacks, destroy target artifact or enchantment defending player controls."
)


WAR_HAMMER_TITAN_LEGENDARY = make_creature(
    name="The War Hammer Titan",
    power=6, toughness=6,
    mana_cost="{3}{B}{B}{W}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Titan"},
    supertypes={"Legendary"},
    text="First strike. When The War Hammer Titan enters, create three colorless Equipment artifact tokens with 'Equipped creature gets +2/+0. Equip {2}.' {2}: Create a 1/1 colorless Construct artifact creature token."
)


# Other Multicolor

def kenny_ackerman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch, can't be blocked"""
    def is_self(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id
    return [make_keyword_grant(obj, ['deathtouch'], is_self)]

KENNY_ACKERMAN = make_creature(
    name="Kenny Ackerman, The Ripper",
    power=4, toughness=3,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Rogue", "Ackerman"},
    supertypes={"Legendary"},
    text="Deathtouch, first strike. Kenny Ackerman can't be blocked except by two or more creatures.",
    setup_interceptors=kenny_ackerman_setup
)


PORCO_GALLIARD = make_creature(
    name="Porco Galliard, Jaw Titan",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    text="Haste, first strike. When Porco Galliard dies, you may search your library for a Warrior card, reveal it, and put it into your hand."
)


MARCEL_GALLIARD = make_creature(
    name="Marcel Galliard, Fallen Warrior",
    power=2, toughness=2,
    mana_cost="{1}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="When Marcel Galliard dies, target creature you control gains indestructible until end of turn."
)


YMIR = make_creature(
    name="Ymir, Original Titan",
    power=4, toughness=4,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    text="When Ymir dies, you may search your library for a Titan card, reveal it, and put it into your hand. Then shuffle."
)


GABI_BRAUN = make_creature(
    name="Gabi Braun, Warrior Candidate",
    power=2, toughness=2,
    mana_cost="{1}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Warrior", "Soldier"},
    supertypes={"Legendary"},
    text="First strike. Whenever Gabi deals combat damage to a player, that player sacrifices a creature."
)


FALCO_GRICE = make_creature(
    name="Falco Grice, Jaw Inheritor",
    power=3, toughness=3,
    mana_cost="{2}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Warrior", "Titan"},
    supertypes={"Legendary"},
    text="Flying, vigilance. Falco Grice can transform into a 5/4 Titan with flying and trample."
)


COLT_GRICE = make_creature(
    name="Colt Grice, Beast Candidate",
    power=2, toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Reach. When Colt Grice enters, you may search your library for a Titan card with mana value 5 or less, reveal it, and put it into your hand."
)


URI_REISS = make_creature(
    name="Uri Reiss, Founding Inheritor",
    power=3, toughness=5,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Noble", "Titan"},
    supertypes={"Legendary"},
    text="Lifelink. At the beginning of your upkeep, you may pay 3 life. If you do, draw a card."
)


ROD_REISS = make_creature(
    name="Rod Reiss, Aberrant Titan",
    power=1, toughness=15,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    text="Defender. Rod Reiss gets +10/+0 as long as you have 5 or less life. When Rod Reiss dies, each player sacrifices three creatures."
)


# =============================================================================
# EQUIPMENT
# =============================================================================

def odm_gear_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Grants flying and first strike"""
    # Equipment setup would require tracking equipped creature
    return []

ODM_GEAR = make_equipment(
    name="ODM Gear",
    mana_cost="{2}",
    text="Equipped creature gets +1/+0 and has flying and first strike.",
    equip_cost="{2}",
    setup_interceptors=odm_gear_setup
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
    text="Other Soldiers you control get +0/+1. {T}: Tap target creature."
)


DARIUS_ZACKLY = make_creature(
    name="Darius Zackly, Premier",
    power=1, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, you may tap target creature. It doesn't untap during its controller's next untap step."
)


DOT_PIXIS = make_creature(
    name="Dot Pixis, Garrison Commander",
    power=2, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Noble"},
    supertypes={"Legendary"},
    text="Defender creatures you control can attack as though they didn't have defender. Soldiers you control get +1/+0."
)


HANNES = make_creature(
    name="Hannes, Garrison Captain",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="When Hannes dies, target creature you control gains indestructible and vigilance until end of turn."
)


CARLA_YEAGER = make_creature(
    name="Carla Yeager, Eren's Mother",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    supertypes={"Legendary"},
    text="When Carla Yeager dies, target creature you control gets +2/+2 until end of turn. If you control Eren Yeager, that creature also gains indestructible until end of turn."
)


WALL_ROSE_GARRISON = make_creature(
    name="Wall Rose Garrison",
    power=1, toughness=5,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier", "Wall"},
    text="Defender. When Wall Rose Garrison blocks, you gain 3 life."
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
    text="When Moblit enters, scry 2. If you control Hange Zoe, draw a card instead."
)


ONYANKOPON = make_creature(
    name="Onyankopon, Anti-Marleyan",
    power=2, toughness=2,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Pilot"},
    supertypes={"Legendary"},
    text="Flying. When Onyankopon deals combat damage to a player, that player discards a card and you draw a card."
)


YELENA = make_creature(
    name="Yelena, True Believer",
    power=2, toughness=3,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Menace. When Yelena enters, look at target opponent's hand. You may choose a nonland card from it. That player discards that card."
)


ILSE_LANGNAR = make_creature(
    name="Ilse Langnar, Titan Chronicler",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout"},
    supertypes={"Legendary"},
    text="When Ilse Langnar dies, draw two cards if a Titan is on the battlefield."
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
    text="Whenever a Titan enters or dies, scry 1 and draw a card."
)


# Additional Black Cards
DINA_FRITZ = make_creature(
    name="Dina Fritz, Smiling Titan",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    text="When Dina Fritz enters, each opponent sacrifices a creature. Dina Fritz attacks each combat if able."
)


KRUGER = make_creature(
    name="Eren Kruger, The Owl",
    power=4, toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Titan"},
    supertypes={"Legendary"},
    text="Haste. When Eren Kruger dies, you may search your library for a Titan card or a creature card with Titan Shift, reveal it, and put it into your hand."
)


GROSS = make_creature(
    name="Sergeant Major Gross",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Whenever a creature an opponent controls dies, that player loses 1 life."
)


MAGATH = make_creature(
    name="Theo Magath, Marleyan General",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier", "Noble"},
    supertypes={"Legendary"},
    text="Other Warriors you control get +1/+1. When Magath dies, each opponent sacrifices a creature."
)


WILLY_TYBUR = make_creature(
    name="Willy Tybur, Declaration of War",
    power=2, toughness=2,
    mana_cost="{2}{B}{W}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="When Willy Tybur enters, each player sacrifices a creature. When Willy Tybur dies, create a 6/6 colorless Titan creature token."
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
    text="When Kaya enters, if you control Sasha Blouse, create two Food tokens. Otherwise, create one Food token."
)


KEITH_SHADIS = make_creature(
    name="Keith Shadis, Instructor",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="When Keith Shadis enters, target creature you control gets +2/+0 and gains first strike until end of turn."
)


LOUISE = make_creature(
    name="Louise, Yeagerist Devotee",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="First strike. Louise gets +2/+0 as long as you control a creature named Mikasa Ackerman."
)


TITAN_TRANSFORMATION = make_instant(
    name="Titan Transformation",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Target creature becomes a Titan in addition to its other types and gets +4/+4 and gains trample until end of turn."
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
    text="Indestructible. When Ymir Fritz enters, create three 6/6 green Titan creature tokens with trample. Titans you control have hexproof."
)


KING_FRITZ = make_creature(
    name="King Fritz, First Eldian King",
    power=3, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, create a 2/2 colorless Titan creature token. Titans you control get +1/+1."
)


TITANS_BLESSING = make_instant(
    name="Titan's Blessing",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn. If it's a Titan, it also gains trample and hexproof until end of turn."
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
