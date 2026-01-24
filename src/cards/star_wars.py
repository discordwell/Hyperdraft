"""
Star Wars: Galactic Conflict (SWG) Card Implementations

Set released March 2026. ~270 cards.
Features mechanics: Force, Lightsaber, Pilot, Dark Side/Light Side
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


def make_artifact_creature(name: str, power: int, toughness: int, mana_cost: str, colors: set, text: str,
                           subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create artifact creature card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT, CardType.CREATURE},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            mana_cost=mana_cost,
            power=power,
            toughness=toughness
        ),
        text=text,
        setup_interceptors=setup_interceptors
    )


def make_equipment(name: str, mana_cost: str, text: str, equip_cost: str, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
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
            supertypes=supertypes or set(),
            mana_cost=mana_cost
        ),
        text=f"{text}\nEquip {equip_cost}",
        setup_interceptors=setup_interceptors
    )


def make_vehicle(name: str, power: int, toughness: int, mana_cost: str, text: str, crew: int,
                 subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create vehicle card definitions."""
    base_subtypes = {"Vehicle"}
    if subtypes:
        base_subtypes.update(subtypes)
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            subtypes=base_subtypes,
            supertypes=supertypes or set(),
            mana_cost=mana_cost,
            power=power,
            toughness=toughness
        ),
        text=f"{text}\nCrew {crew}",
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


# =============================================================================
# STAR WARS KEYWORD MECHANICS
# =============================================================================

def make_force_ability(source_obj: GameObject, life_cost: int, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Force - Pay N life instead of mana to activate this ability.
    Creates an activated ability that costs life.
    """
    def force_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ACTIVATE:
            return False
        return (event.payload.get('source') == source_obj.id and
                event.payload.get('ability') == 'force')

    def force_handler(event: Event, state: GameState) -> InterceptorResult:
        # Pay life cost
        life_payment = Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': source_obj.controller, 'amount': -life_cost},
            source=source_obj.id
        )
        effect_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[life_payment] + effect_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=force_filter,
        handler=force_handler,
        duration='while_on_battlefield'
    )


def make_light_side_bonus(source_obj: GameObject, power_bonus: int, toughness_bonus: int, threshold: int = 10) -> list[Interceptor]:
    """
    Light Side - This creature gets +X/+Y as long as you have N or more life.
    Default threshold is 10 life.
    """
    def light_side_filter(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        player = state.players.get(source_obj.controller)
        return player and player.life >= threshold

    return make_static_pt_boost(source_obj, power_bonus, toughness_bonus, light_side_filter)


def make_dark_side_bonus(source_obj: GameObject, power_bonus: int, toughness_bonus: int, threshold: int = 10) -> list[Interceptor]:
    """
    Dark Side - This creature gets +X/+Y as long as you have less than N life.
    Default threshold is 10 life.
    """
    def dark_side_filter(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        player = state.players.get(source_obj.controller)
        return player and player.life < threshold

    return make_static_pt_boost(source_obj, power_bonus, toughness_bonus, dark_side_filter)


def make_pilot_crew_bonus(source_obj: GameObject, power_bonus: int = 1, toughness_bonus: int = 1) -> Interceptor:
    """
    Pilot - When this creature crews a Vehicle, that Vehicle gets +X/+Y until end of turn.
    """
    def crew_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.TAP:
            return False
        if event.payload.get('object_id') != source_obj.id:
            return False
        return event.payload.get('reason') == 'crew'

    def crew_handler(event: Event, state: GameState) -> InterceptorResult:
        vehicle_id = event.payload.get('vehicle_id')
        if not vehicle_id:
            return InterceptorResult(action=InterceptorAction.PASS)
        boost_event = Event(
            type=EventType.COUNTER_ADDED,
            payload={
                'object_id': vehicle_id,
                'counter_type': 'pilot_boost',
                'power': power_bonus,
                'toughness': toughness_bonus,
                'duration': 'end_of_turn'
            },
            source=source_obj.id
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[boost_event])

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=crew_filter,
        handler=crew_handler,
        duration='while_on_battlefield'
    )


def make_lightsaber_bonus(source_obj: GameObject, equipped_creature_id: str) -> list[Interceptor]:
    """
    Lightsaber - Equipped creature gets +2/+0 and has first strike.
    If equipped creature is a Jedi or Sith, it gets +3/+0 instead.
    """
    interceptors = []

    def is_equipped(target: GameObject, state: GameState) -> bool:
        return target.id == equipped_creature_id

    def is_equipped_force_user(target: GameObject, state: GameState) -> bool:
        if target.id != equipped_creature_id:
            return False
        subtypes = target.characteristics.subtypes
        return 'Jedi' in subtypes or 'Sith' in subtypes

    def is_equipped_non_force(target: GameObject, state: GameState) -> bool:
        if target.id != equipped_creature_id:
            return False
        subtypes = target.characteristics.subtypes
        return 'Jedi' not in subtypes and 'Sith' not in subtypes

    # Base bonus for non-Force users
    interceptors.extend(make_static_pt_boost(source_obj, 2, 0, is_equipped_non_force))
    # Enhanced bonus for Force users
    interceptors.extend(make_static_pt_boost(source_obj, 3, 0, is_equipped_force_user))
    # First strike for all
    interceptors.append(make_keyword_grant(source_obj, ['first_strike'], is_equipped))

    return interceptors


def jedi_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Jedi creatures you control."""
    return creatures_with_subtype(source, "Jedi")


def sith_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Sith creatures you control."""
    return creatures_with_subtype(source, "Sith")


def droid_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Droid creatures you control."""
    return creatures_with_subtype(source, "Droid")


def trooper_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Trooper creatures you control."""
    return creatures_with_subtype(source, "Trooper")


def rebel_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Rebel creatures you control."""
    return creatures_with_subtype(source, "Rebel")


def empire_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Empire creatures you control."""
    return creatures_with_subtype(source, "Empire")


# =============================================================================
# WHITE CARDS - REBELS, JEDI, LIGHT SIDE, HOPE
# =============================================================================

# --- Legendary Creatures ---

def luke_skywalker_new_hope_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Light Side bonus + when attacks, other Rebels get +1/+1"""
    interceptors = []
    interceptors.extend(make_light_side_bonus(obj, 2, 2))

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'boost': 'rebels_plus_one', 'controller': obj.controller, 'duration': 'end_of_turn'},
            source=obj.id
        )]
    interceptors.append(make_attack_trigger(obj, attack_effect))
    return interceptors

LUKE_SKYWALKER_NEW_HOPE = make_creature(
    name="Luke Skywalker, New Hope",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Jedi", "Rebel"},
    supertypes={"Legendary"},
    text="Vigilance. Light Side - Luke gets +2/+2 as long as you have 10 or more life. Whenever Luke attacks, other Rebel creatures you control get +1/+1 until end of turn.",
    setup_interceptors=luke_skywalker_new_hope_setup
)


def leia_organa_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - create two 1/1 Rebel Soldier tokens"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Rebel Soldier', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE}, 'subtypes': {'Human', 'Rebel', 'Soldier'}}
            }, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Rebel Soldier', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE}, 'subtypes': {'Human', 'Rebel', 'Soldier'}}
            }, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

LEIA_ORGANA = make_creature(
    name="Leia Organa, Rebel Leader",
    power=2, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rebel", "Noble"},
    supertypes={"Legendary"},
    text="When Leia Organa enters, create two 1/1 white Human Rebel Soldier creature tokens. Other Rebel creatures you control have vigilance.",
    setup_interceptors=leia_organa_setup
)


def obi_wan_kenobi_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death trigger - exile, then return at end step"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': obj.id, 'to_zone_type': ZoneType.EXILE, 'return_end_step': True},
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]

OBI_WAN_KENOBI = make_creature(
    name="Obi-Wan Kenobi, Wise Master",
    power=3, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Jedi"},
    supertypes={"Legendary"},
    text="Lifelink. When Obi-Wan Kenobi dies, exile him. At the beginning of your next end step, return him to the battlefield as a Spirit with 'Other creatures you control have protection from the color of your choice.'",
    setup_interceptors=obi_wan_kenobi_setup
)


def yoda_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Jedi get +1/+1 and have hexproof"""
    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Jedi")))
    interceptors.append(make_keyword_grant(obj, ['hexproof'], other_creatures_with_subtype(obj, "Jedi")))
    return interceptors

YODA_GRAND_MASTER = make_creature(
    name="Yoda, Grand Master",
    power=2, toughness=4,
    mana_cost="{1}{W}{U}{G}",
    colors={Color.WHITE, Color.BLUE, Color.GREEN},
    subtypes={"Jedi"},
    supertypes={"Legendary"},
    text="Other Jedi creatures you control get +1/+1 and have hexproof. Force 2 - Pay 2 life: Scry 2, then you may reveal the top card. If it's a creature, draw it.",
    setup_interceptors=yoda_setup
)


def mace_windu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Double strike, Light Side bonus"""
    return make_light_side_bonus(obj, 1, 1)

MACE_WINDU = make_creature(
    name="Mace Windu, Champion of Light",
    power=4, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Jedi"},
    supertypes={"Legendary"},
    text="Double strike. Light Side - Mace Windu gets +1/+1 as long as you have 10 or more life.",
    setup_interceptors=mace_windu_setup
)


# --- Regular Creatures ---

def rebel_pilot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Pilot - crew bonus"""
    return [make_pilot_crew_bonus(obj, 2, 0)]

REBEL_PILOT = make_creature(
    name="Rebel Pilot",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rebel", "Pilot"},
    text="Pilot - When Rebel Pilot crews a Vehicle, that Vehicle gets +2/+0 until end of turn.",
    setup_interceptors=rebel_pilot_setup
)


def jedi_padawan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Light Side - gains vigilance"""
    def light_side_check(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        player = state.players.get(obj.controller)
        return player and player.life >= 10

    return [make_keyword_grant(obj, ['vigilance'], light_side_check)]

JEDI_PADAWAN = make_creature(
    name="Jedi Padawan",
    power=2, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Jedi"},
    text="Light Side - Jedi Padawan has vigilance as long as you have 10 or more life.",
    setup_interceptors=jedi_padawan_setup
)


def rebel_trooper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - gain 2 life"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

REBEL_TROOPER = make_creature(
    name="Rebel Trooper",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rebel", "Soldier"},
    text="When Rebel Trooper enters, you gain 2 life.",
    setup_interceptors=rebel_trooper_setup
)


ALDERAANIAN_DIPLOMAT = make_creature(
    name="Alderaanian Diplomat",
    power=1, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rebel", "Advisor"},
    text="Creatures your opponents control can't attack you unless their controller pays {1} for each creature attacking you."
)


def jedi_temple_guard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Jedi have vigilance"""
    return [make_keyword_grant(obj, ['vigilance'], other_creatures_with_subtype(obj, "Jedi"))]

JEDI_TEMPLE_GUARD = make_creature(
    name="Jedi Temple Guard",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Jedi", "Soldier"},
    text="Vigilance. Other Jedi creatures you control have vigilance.",
    setup_interceptors=jedi_temple_guard_setup
)


def echo_base_defender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When blocks, gain 2 life"""
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

ECHO_BASE_DEFENDER = make_creature(
    name="Echo Base Defender",
    power=1, toughness=4,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rebel", "Soldier"},
    text="Defender. Whenever Echo Base Defender blocks, you gain 2 life.",
    setup_interceptors=echo_base_defender_setup
)


REBEL_MEDIC = make_creature(
    name="Rebel Medic",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rebel", "Cleric"},
    text="{T}: Prevent the next 2 damage that would be dealt to target creature this turn."
)


def hope_of_the_rebellion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you gain life, put a +1/+1 counter on a Rebel"""
    def life_gain_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'target_type': 'rebel_creature',
            'counter_type': '+1/+1',
            'amount': 1
        }, source=obj.id)]
    return [make_life_gain_trigger(obj, life_gain_effect)]

HOPE_OF_THE_REBELLION = make_creature(
    name="Hope of the Rebellion",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rebel"},
    text="Whenever you gain life, put a +1/+1 counter on target Rebel creature you control.",
    setup_interceptors=hope_of_the_rebellion_setup
)


CORUSCANT_PEACEKEEPER = make_creature(
    name="Coruscant Peacekeeper",
    power=2, toughness=2,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="First strike. {1}{W}: Coruscant Peacekeeper gains lifelink until end of turn."
)


RESISTANCE_COMMANDER = make_creature(
    name="Resistance Commander",
    power=2, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rebel", "Soldier"},
    text="When Resistance Commander enters, create a 1/1 white Human Rebel Soldier creature token. Rebel creatures you control get +1/+0."
)


JEDI_SENTINEL = make_creature(
    name="Jedi Sentinel",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Jedi"},
    text="Vigilance, lifelink."
)


REBELLION_SYMPATHIZER = make_creature(
    name="Rebellion Sympathizer",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    text="When Rebellion Sympathizer dies, create a 1/1 white Human Rebel Soldier creature token."
)


TATOOINE_HOMESTEADER = make_creature(
    name="Tatooine Homesteader",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    text="{T}: Add {C}. Spend this mana only to cast creature spells or activate abilities of creatures."
)


GALACTIC_SENATOR = make_creature(
    name="Galactic Senator",
    power=1, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble", "Advisor"},
    text="When Galactic Senator enters, choose an opponent. That player can't attack you until your next turn unless they pay {2} for each attacking creature."
)


# --- Instants ---

FORCE_PROTECTION = make_instant(
    name="Force Protection",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature you control gains indestructible until end of turn. If it's a Jedi, you also gain 3 life."
)


REBEL_AMBUSH = make_instant(
    name="Rebel Ambush",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Create three 1/1 white Human Rebel Soldier creature tokens. They gain haste until end of turn."
)


JEDI_REFLEXES = make_instant(
    name="Jedi Reflexes",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gains first strike until end of turn. If it's a Jedi, it also gains lifelink until end of turn."
)


HOPE_RENEWED = make_instant(
    name="Hope Renewed",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="You gain 4 life. Light Side - If you have 10 or more life, draw a card."
)


DEFENSIVE_FORMATION = make_instant(
    name="Defensive Formation",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Creatures you control get +0/+2 until end of turn. Untap those creatures."
)


LIGHT_OF_THE_FORCE = make_instant(
    name="Light of the Force",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Exile target creature with power 4 or greater. Its controller gains life equal to its toughness."
)


# --- Sorceries ---

CALL_TO_ARMS = make_sorcery(
    name="Call to Arms",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Create four 1/1 white Human Rebel Soldier creature tokens. You gain 1 life for each creature you control."
)


LIBERATION_DAY = make_sorcery(
    name="Liberation Day",
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    text="Destroy all creatures with power 4 or greater. You gain 2 life for each creature destroyed this way."
)


JEDI_TRAINING = make_sorcery(
    name="Jedi Training",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature becomes a Jedi in addition to its other types and gets +1/+1 until end of turn. Draw a card."
)


EVACUATION_PLAN = make_sorcery(
    name="Evacuation Plan",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Return up to two target creatures you control to their owner's hand. You gain 3 life."
)


# --- Enchantments ---

def the_light_side_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you gain life, scry 1"""
    def life_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_life_gain_trigger(obj, life_effect)]

THE_LIGHT_SIDE = make_enchantment(
    name="The Light Side",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="At the beginning of your upkeep, if you have 15 or more life, draw a card. Whenever you gain life, scry 1.",
    setup_interceptors=the_light_side_setup
)


REBEL_ALLIANCE = make_enchantment(
    name="Rebel Alliance",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Rebel creatures you control get +1/+1. At the beginning of your end step, if you control four or more Rebels, create a 1/1 white Human Rebel Soldier creature token."
)


JEDI_SANCTUARY = make_enchantment(
    name="Jedi Sanctuary",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Jedi creatures you control have hexproof and can't be sacrificed."
)


# =============================================================================
# BLUE CARDS - JEDI MIND TRICKS, TECHNOLOGY, DROIDS
# =============================================================================

# --- Legendary Creatures ---

def r2d2_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an artifact spell, scry 1"""
    def artifact_cast_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    def artifact_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.ARTIFACT in spell_types

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: artifact_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=artifact_cast_effect(e, s)),
        duration='while_on_battlefield'
    )]

R2D2 = make_artifact_creature(
    name="R2-D2, Astromech Hero",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Droid"},
    supertypes={"Legendary"},
    text="Whenever you cast an artifact spell, scry 1. {T}: Untap target artifact or Vehicle.",
    setup_interceptors=r2d2_setup
)


def c3po_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another Droid enters, draw a card"""
    def droid_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == source.id:
            return False
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                'Droid' in entering.characteristics.subtypes)

    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [make_etb_trigger(obj, draw_effect, filter_fn=droid_etb_filter)]

C3PO = make_artifact_creature(
    name="C-3PO, Protocol Droid",
    power=0, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Droid", "Advisor"},
    supertypes={"Legendary"},
    text="Whenever another Droid enters under your control, draw a card. {T}: Target creature can't attack or block until your next turn.",
    setup_interceptors=c3po_setup
)


def admiral_ackbar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vehicles you control have hexproof"""
    def vehicle_filter(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                'Vehicle' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    return [make_keyword_grant(obj, ['hexproof'], vehicle_filter)]

ADMIRAL_ACKBAR = make_creature(
    name="Admiral Ackbar, Fleet Commander",
    power=2, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Mon Calamari", "Rebel", "Advisor"},
    supertypes={"Legendary"},
    text="Vehicles you control have hexproof. Whenever a Vehicle you control deals combat damage to a player, draw a card.",
    setup_interceptors=admiral_ackbar_setup
)


def qui_gon_jinn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an instant, scry 1"""
    def instant_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [make_spell_cast_trigger(obj, instant_effect, spell_type_filter={CardType.INSTANT})]

QUI_GON_JINN = make_creature(
    name="Qui-Gon Jinn, Living Force",
    power=3, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Jedi"},
    supertypes={"Legendary"},
    text="Whenever you cast an instant spell, scry 1. {U}: Qui-Gon Jinn phases out.",
    setup_interceptors=qui_gon_jinn_setup
)


# --- Regular Creatures ---

def astromech_droid_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - scry 2"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

ASTROMECH_DROID = make_artifact_creature(
    name="Astromech Droid",
    power=1, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Droid"},
    text="When Astromech Droid enters, scry 2.",
    setup_interceptors=astromech_droid_setup
)


PROTOCOL_DROID = make_artifact_creature(
    name="Protocol Droid",
    power=0, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Droid"},
    text="{T}: Add {U}. Spend this mana only to cast artifact spells."
)


def jedi_scholar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you scry, draw a card if you put a card on bottom"""
    # Simplified - triggers on scry
    def scry_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Complex trigger handled by game engine
    return []

JEDI_SCHOLAR = make_creature(
    name="Jedi Scholar",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Jedi"},
    text="Whenever you scry, if you put one or more cards on the bottom of your library, draw a card."
)


def cloud_city_engineer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Artifacts cost 1 less"""
    def cost_reduce_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.ARTIFACT in spell_types

    def cost_reduce_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        current_reduction = new_event.payload.get('cost_reduction', 0)
        new_event.payload['cost_reduction'] = current_reduction + 1
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=cost_reduce_filter,
        handler=cost_reduce_handler,
        duration='while_on_battlefield'
    )]

CLOUD_CITY_ENGINEER = make_creature(
    name="Cloud City Engineer",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Artificer"},
    text="Artifact spells you cast cost {1} less to cast.",
    setup_interceptors=cloud_city_engineer_setup
)


BATTLE_DROID = make_artifact_creature(
    name="Battle Droid",
    power=1, toughness=1,
    mana_cost="{1}",
    colors=set(),
    subtypes={"Droid", "Soldier"},
    text="When Battle Droid dies, you may pay {1}. If you do, create a 1/1 colorless Droid Soldier artifact creature token."
)


PROBE_DROID = make_artifact_creature(
    name="Probe Droid",
    power=1, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Droid", "Scout"},
    text="Flying. When Probe Droid enters, look at target opponent's hand."
)


def kamino_cloner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - create token copy"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Clone Trooper', 'power': 2, 'toughness': 2, 'colors': {Color.WHITE}, 'subtypes': {'Human', 'Clone', 'Soldier'}}
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

KAMINO_CLONER = make_creature(
    name="Kamino Cloner",
    power=2, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Kaminoan", "Artificer"},
    text="When Kamino Cloner enters, create a 2/2 white Human Clone Soldier creature token.",
    setup_interceptors=kamino_cloner_setup
)


MON_CALAMARI_CAPTAIN = make_creature(
    name="Mon Calamari Captain",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Mon Calamari", "Rebel", "Pilot"},
    text="Pilot - When Mon Calamari Captain crews a Vehicle, draw a card."
)


REBEL_STRATEGIST = make_creature(
    name="Rebel Strategist",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rebel", "Advisor"},
    text="At the beginning of combat on your turn, you may have target creature gain flying until end of turn."
)


CORUSCANT_ARCHIVIST = make_creature(
    name="Coruscant Archivist",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Advisor"},
    text="{1}{U}, {T}: Draw a card, then discard a card. If you discarded a creature card, draw another card."
)


HOLO_PROJECTOR_DROID = make_artifact_creature(
    name="Holo-Projector Droid",
    power=0, toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Droid"},
    text="{T}: Create a token that's a copy of target creature you control, except it's an illusion in addition to its other types and has 'When this creature becomes the target of a spell, sacrifice it.' Exile that token at the beginning of the next end step."
)


SEPARATIST_INFILTRATOR = make_creature(
    name="Separatist Infiltrator",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Shapeshifter", "Spy"},
    text="Separatist Infiltrator can't be blocked. Whenever Separatist Infiltrator deals combat damage to a player, you may draw a card. If you do, discard a card."
)


JEDI_INVESTIGATOR = make_creature(
    name="Jedi Investigator",
    power=2, toughness=2,
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Jedi"},
    text="Flash. When Jedi Investigator enters, look at target player's hand."
)


# --- Instants ---

JEDI_MIND_TRICK = make_instant(
    name="Jedi Mind Trick",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn."
)


FORCE_PUSH = make_instant(
    name="Force Push",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Return target creature to its owner's hand. If you control a Jedi, scry 1."
)


HOLOGRAPHIC_DECOY = make_instant(
    name="Holographic Decoy",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {2}. If you control a Droid, counter that spell unless its controller pays {4} instead."
)


HYPERSPACE_JUMP = make_instant(
    name="Hyperspace Jump",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Return all creatures you control to their owner's hands. Draw a card for each creature returned this way."
)


SENSOR_SCRAMBLE = make_instant(
    name="Sensor Scramble",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Counter target activated or triggered ability."
)


FORCE_VISION = make_instant(
    name="Force Vision",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Look at the top four cards of your library. Put one into your hand and the rest on the bottom of your library in any order."
)


TECH_OVERRIDE = make_instant(
    name="Tech Override",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Counter target artifact spell. Draw a card."
)


# --- Sorceries ---

DROID_FABRICATION = make_sorcery(
    name="Droid Fabrication",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Create three 1/1 colorless Droid creature tokens. Draw a card for each artifact you control."
)


MEMORY_WIPE = make_sorcery(
    name="Memory Wipe",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Target player puts the top eight cards of their library into their graveyard. Draw two cards."
)


CLONE_ARMY = make_sorcery(
    name="Clone Army",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="For each creature you control, create a token that's a copy of that creature. Those tokens gain haste. Exile them at the beginning of the next end step."
)


HOLOGRAM_TRANSMISSION = make_sorcery(
    name="Hologram Transmission",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Scry 3, then draw a card."
)


# --- Enchantments ---

DROID_FACTORY = make_enchantment(
    name="Droid Factory",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="At the beginning of your upkeep, create a 1/1 colorless Droid creature token. Droids you control have '{T}: Add {C}.'"
)


JEDI_ARCHIVES = make_enchantment(
    name="Jedi Archives",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Whenever you cast an instant or sorcery spell, scry 1. {2}{U}: Draw a card. Activate only once each turn."
)


# =============================================================================
# BLACK CARDS - SITH, EMPIRE, DARK SIDE, FEAR
# =============================================================================

# --- Legendary Creatures ---

def darth_vader_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dark Side bonus + menace + when deals damage, opponent loses life"""
    interceptors = []
    interceptors.extend(make_dark_side_bonus(obj, 2, 2))

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target and target in state.players:
            return [Event(type=EventType.LIFE_CHANGE, payload={'player': target, 'amount': -2}, source=obj.id)]
        return []
    interceptors.append(make_damage_trigger(obj, damage_effect, combat_only=True))
    return interceptors

DARTH_VADER = make_creature(
    name="Darth Vader, Dark Lord",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Sith"},
    supertypes={"Legendary"},
    text="Menace. Dark Side - Darth Vader gets +2/+2 as long as you have less than 10 life. Whenever Darth Vader deals combat damage to a player, that player loses 2 life.",
    setup_interceptors=darth_vader_setup
)


def emperor_palpatine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Sith get +2/+1, opponents can't gain life"""
    return make_static_pt_boost(obj, 2, 1, other_creatures_with_subtype(obj, "Sith"))

EMPEROR_PALPATINE = make_creature(
    name="Emperor Palpatine, Sith Master",
    power=3, toughness=4,
    mana_cost="{2}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Sith"},
    supertypes={"Legendary"},
    text="Other Sith creatures you control get +2/+1. Your opponents can't gain life. {B}{B}: Each opponent loses 1 life.",
    setup_interceptors=emperor_palpatine_setup
)


def darth_maul_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Double strike + when kills creature, untap"""
    def kill_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        # Check if this was caused by combat damage from source
        return event.payload.get('damage_source') == source.id

    def untap_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.UNTAP, payload={'object_id': obj.id}, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: kill_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=untap_effect(e, s)),
        duration='while_on_battlefield'
    )]

DARTH_MAUL = make_creature(
    name="Darth Maul, Savage Assassin",
    power=4, toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Zabrak", "Sith"},
    supertypes={"Legendary"},
    text="Double strike, haste. Whenever Darth Maul destroys a creature, untap him.",
    setup_interceptors=darth_maul_setup
)


def count_dooku_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, destroy target creature with power 3 or less"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.OBJECT_DESTROYED, payload={
            'target_filter': 'creature_power_3_or_less'
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

COUNT_DOOKU = make_creature(
    name="Count Dooku, Sith Lord",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Sith", "Noble"},
    supertypes={"Legendary"},
    text="Deathtouch. When Count Dooku enters, destroy target creature with power 3 or less.",
    setup_interceptors=count_dooku_setup
)


def grand_moff_tarkin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Empire creatures get +1/+0, activated destroy ability"""
    return make_static_pt_boost(obj, 1, 0, creatures_with_subtype(obj, "Empire"))

GRAND_MOFF_TARKIN = make_creature(
    name="Grand Moff Tarkin",
    power=2, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Empire", "Advisor"},
    supertypes={"Legendary"},
    text="Empire creatures you control get +1/+0. {3}{B}{B}, {T}: Destroy target creature. Activate only as a sorcery.",
    setup_interceptors=grand_moff_tarkin_setup
)


# --- Regular Creatures ---

def sith_apprentice_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dark Side - gets deathtouch"""
    def dark_side_check(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        player = state.players.get(obj.controller)
        return player and player.life < 10

    return [make_keyword_grant(obj, ['deathtouch'], dark_side_check)]

SITH_APPRENTICE = make_creature(
    name="Sith Apprentice",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Sith"},
    text="Dark Side - Sith Apprentice has deathtouch as long as you have less than 10 life.",
    setup_interceptors=sith_apprentice_setup
)


def stormtrooper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies, opponent loses 1 life"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        opponents = all_opponents(obj, state)
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': opp, 'amount': -1}, source=obj.id) for opp in opponents]
    return [make_death_trigger(obj, death_effect)]

STORMTROOPER = make_creature(
    name="Stormtrooper",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Empire", "Trooper"},
    text="When Stormtrooper dies, each opponent loses 1 life.",
    setup_interceptors=stormtrooper_setup
)


IMPERIAL_OFFICER = make_creature(
    name="Imperial Officer",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Empire", "Soldier"},
    text="Other Empire creatures you control have menace."
)


def death_trooper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch + when deals damage to creature, exile it instead"""
    def exile_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        return event.payload.get('damage_source') == source.id

    def exile_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['to_zone_type'] = ZoneType.EXILE
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=lambda e, s: exile_filter(e, s, obj),
        handler=exile_handler,
        duration='while_on_battlefield'
    )]

DEATH_TROOPER = make_creature(
    name="Death Trooper",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Empire", "Trooper"},
    text="Deathtouch. If a creature dealt damage by Death Trooper would die, exile it instead.",
    setup_interceptors=death_trooper_setup
)


IMPERIAL_INQUISITOR = make_creature(
    name="Imperial Inquisitor",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Empire", "Sith"},
    text="Menace. When Imperial Inquisitor enters, target opponent reveals their hand. You choose a creature card from it. That player discards that card."
)


def sith_acolyte_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When another creature dies, get +1/+1 counter"""
    def creature_death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        if dying_id == source.id:
            return False
        dying = state.objects.get(dying_id)
        return dying and CardType.CREATURE in dying.characteristics.types

    def counter_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1
        }, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: creature_death_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=counter_effect(e, s)),
        duration='while_on_battlefield'
    )]

SITH_ACOLYTE = make_creature(
    name="Sith Acolyte",
    power=2, toughness=2,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Sith"},
    text="Whenever another creature dies, put a +1/+1 counter on Sith Acolyte.",
    setup_interceptors=sith_acolyte_setup
)


MUSTAFAR_TORTURER = make_creature(
    name="Mustafar Torturer",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Empire"},
    text="{1}{B}, {T}: Target creature gets -2/-2 until end of turn."
)


IMPERIAL_SPY = make_creature(
    name="Imperial Spy",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Empire", "Rogue"},
    text="When Imperial Spy enters, look at target opponent's hand. Imperial Spy can't be blocked."
)


TIE_FIGHTER_PILOT = make_creature(
    name="TIE Fighter Pilot",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Empire", "Pilot"},
    text="Flying. Pilot - When TIE Fighter Pilot crews a Vehicle, that Vehicle gains menace until end of turn."
)


FORCE_CHOKER = make_creature(
    name="Force Choker",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Sith"},
    text="When Force Choker enters, target creature gets -2/-2 until end of turn. If you control a Sith, it gets -4/-4 instead."
)


SHADOW_GUARD = make_creature(
    name="Shadow Guard",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Empire", "Soldier"},
    text="Flash, deathtouch. Shadow Guard can block any number of creatures."
)


DARK_SIDE_ADEPT = make_creature(
    name="Dark Side Adept",
    power=2, toughness=3,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Sith"},
    text="Dark Side - At the beginning of your upkeep, if you have less than 10 life, each opponent loses 1 life and you gain 1 life."
)


# --- Instants ---

FORCE_CHOKE = make_instant(
    name="Force Choke",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -3/-3 until end of turn. If you control a Sith, it gets -5/-5 instead."
)


DARK_SIDE_CORRUPTION = make_instant(
    name="Dark Side Corruption",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn. You lose 2 life."
)


IMPERIAL_EXECUTION = make_instant(
    name="Imperial Execution",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. Its controller loses life equal to that creature's toughness."
)


SITH_LIGHTNING = make_instant(
    name="Sith Lightning",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Sith Lightning deals 3 damage to target creature or planeswalker. You gain 3 life."
)


FEAR_ITSELF = make_instant(
    name="Fear Itself",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature can't block this turn. Its controller loses 2 life."
)


BETRAYAL = make_instant(
    name="Betrayal",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. If it was legendary, draw two cards."
)


# --- Sorceries ---

ORDER_66 = make_sorcery(
    name="Order 66",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Destroy all creatures. You lose 1 life for each creature you controlled that was destroyed this way."
)


IMPERIAL_BOMBARDMENT = make_sorcery(
    name="Imperial Bombardment",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Each creature gets -2/-2 until end of turn. You may sacrifice a creature. If you do, draw two cards."
)


HARVEST_DESPAIR = make_sorcery(
    name="Harvest Despair",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Each opponent sacrifices a creature. If you control a Sith, each opponent also discards a card."
)


CONSCRIPTION = make_sorcery(
    name="Conscription",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield. It's a black Empire Trooper in addition to its other colors and types."
)


# --- Enchantments ---

def the_dark_side_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you lose life, opponents lose that much life"""
    def life_loss_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        if event.payload.get('player') != obj.controller:
            return False
        return event.payload.get('amount', 0) < 0

    def opponent_damage_effect(event: Event, state: GameState) -> list[Event]:
        amount = abs(event.payload.get('amount', 0))
        opponents = all_opponents(obj, state)
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': opp, 'amount': -amount}, source=obj.id) for opp in opponents]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=life_loss_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=opponent_damage_effect(e, s)),
        duration='while_on_battlefield'
    )]

THE_DARK_SIDE = make_enchantment(
    name="The Dark Side",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Whenever you lose life, each opponent loses that much life. At the beginning of your upkeep, you lose 1 life.",
    setup_interceptors=the_dark_side_setup
)


GALACTIC_EMPIRE = make_enchantment(
    name="Galactic Empire",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Empire creatures you control get +1/+1. At the beginning of your end step, create a 2/1 black Human Empire Trooper creature token."
)


RULE_OF_TWO = make_enchantment(
    name="Rule of Two",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="You can't control more than two Sith creatures. Sith creatures you control get +2/+2 and have lifelink."
)


# =============================================================================
# RED CARDS - BOUNTY HUNTERS, AGGRESSION, BLASTERS
# =============================================================================

# --- Legendary Creatures ---

def boba_fett_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, deal 2 damage to any target"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={
            'amount': 2,
            'target_type': 'any',
            'source': obj.id
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

BOBA_FETT = make_creature(
    name="Boba Fett, Bounty Hunter",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Bounty Hunter"},
    supertypes={"Legendary"},
    text="Flying, haste. Whenever Boba Fett attacks, he deals 2 damage to any target.",
    setup_interceptors=boba_fett_setup
)


def jango_fett_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies, create Boba token"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Boba Fett', 'power': 2, 'toughness': 2, 'colors': {Color.RED}, 'subtypes': {'Human', 'Bounty Hunter'}, 'haste': True}
        }, source=obj.id)]
    return [make_death_trigger(obj, death_effect)]

JANGO_FETT = make_creature(
    name="Jango Fett, Prime Clone",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Bounty Hunter"},
    supertypes={"Legendary"},
    text="First strike, haste. When Jango Fett dies, create a 2/2 red Human Bounty Hunter creature token named Boba Fett with haste.",
    setup_interceptors=jango_fett_setup
)


def cad_bane_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch + when deals damage to player, steal an artifact"""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.ZONE_CHANGE, payload={
            'target_type': 'opponent_artifact',
            'gain_control': True
        }, source=obj.id)]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

CAD_BANE = make_creature(
    name="Cad Bane, Ruthless Mercenary",
    power=3, toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Duros", "Bounty Hunter"},
    supertypes={"Legendary"},
    text="Deathtouch. Whenever Cad Bane deals combat damage to a player, gain control of target artifact that player controls.",
    setup_interceptors=cad_bane_setup
)


def din_djarin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Protection from multicolored, Pilot bonus"""
    return [make_pilot_crew_bonus(obj, 2, 2)]

DIN_DJARIN = make_creature(
    name="Din Djarin, The Mandalorian",
    power=3, toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Mandalorian", "Bounty Hunter"},
    supertypes={"Legendary"},
    text="Protection from multicolored. Pilot - When Din Djarin crews a Vehicle, that Vehicle gets +2/+2 until end of turn.",
    setup_interceptors=din_djarin_setup
)


def greedo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """First strike only if attacks first"""
    def first_attack_check(target: GameObject, state: GameState) -> bool:
        # Greedo gets first strike if no damage has been dealt yet
        return target.id == obj.id and state.turn_number == obj.entered_zone_at

    return [make_keyword_grant(obj, ['first_strike'], first_attack_check)]

GREEDO = make_creature(
    name="Greedo, Quick Draw",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Rodian", "Bounty Hunter"},
    supertypes={"Legendary"},
    text="Haste. Greedo has first strike as long as no damage has been dealt this turn.",
    setup_interceptors=greedo_setup
)


# --- Regular Creatures ---

def bounty_hunter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When creature dies, if it was dealt damage by this, get treasure"""
    def creature_death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        return event.payload.get('damage_source') == source.id

    def treasure_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'}}
        }, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: creature_death_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=treasure_effect(e, s)),
        duration='while_on_battlefield'
    )]

BOUNTY_HUNTER = make_creature(
    name="Bounty Hunter",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Bounty Hunter"},
    text="When a creature dealt damage by Bounty Hunter this turn dies, create a Treasure token.",
    setup_interceptors=bounty_hunter_setup
)


TRANDOSHAN_SLAVER = make_creature(
    name="Trandoshan Slaver",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Trandoshan", "Bounty Hunter"},
    text="Trample. When Trandoshan Slaver deals combat damage to a player, exile target creature that player controls until Trandoshan Slaver leaves the battlefield."
)


def tusken_raider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attacks each turn if able"""
    # This is a restriction effect handled by the combat manager
    return []

TUSKEN_RAIDER = make_creature(
    name="Tusken Raider",
    power=3, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Tusken", "Warrior"},
    text="Haste. Tusken Raider attacks each combat if able.",
    setup_interceptors=tusken_raider_setup
)


GAMORREAN_GUARD = make_creature(
    name="Gamorrean Guard",
    power=4, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Gamorrean", "Soldier"},
    text="Menace."
)


PODRACER = make_creature(
    name="Podracer",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Pilot"},
    text="Haste. Pilot - When Podracer crews a Vehicle, that Vehicle gains haste until end of turn."
)


MANDALORIAN_WARRIOR = make_creature(
    name="Mandalorian Warrior",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Mandalorian", "Warrior"},
    text="Flying. When Mandalorian Warrior enters, it deals 1 damage to any target."
)


def mos_eisley_thug_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - each player discards a card"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players:
            events.append(Event(type=EventType.DISCARD, payload={'player': player_id, 'amount': 1}, source=obj.id))
        return events
    return [make_etb_trigger(obj, etb_effect)]

MOS_EISLEY_THUG = make_creature(
    name="Mos Eisley Thug",
    power=3, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rogue"},
    text="Haste. When Mos Eisley Thug enters, each player discards a card.",
    setup_interceptors=mos_eisley_thug_setup
)


SEPARATIST_BATTLE_DROID = make_artifact_creature(
    name="Separatist Battle Droid",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Droid", "Soldier"},
    text="Haste. When Separatist Battle Droid dies, it deals 1 damage to any target."
)


CLONE_TROOPER_COMMANDO = make_creature(
    name="Clone Trooper Commando",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Clone", "Soldier"},
    text="First strike. When Clone Trooper Commando enters, it deals 2 damage to target creature an opponent controls."
)


WEEQUAY_PIRATE = make_creature(
    name="Weequay Pirate",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Weequay", "Pirate"},
    text="When Weequay Pirate deals combat damage to a player, create a Treasure token."
)


ARENA_GLADIATOR = make_creature(
    name="Arena Gladiator",
    power=4, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="Trample. Arena Gladiator must be blocked if able."
)


PYKE_ENFORCER = make_creature(
    name="Pyke Enforcer",
    power=2, toughness=2,
    mana_cost="{R}{R}",
    colors={Color.RED},
    subtypes={"Pyke", "Rogue"},
    text="First strike. {R}: Pyke Enforcer gets +1/+0 until end of turn."
)


# --- Instants ---

BLASTER_BOLT = make_instant(
    name="Blaster Bolt",
    mana_cost="{R}",
    colors={Color.RED},
    text="Blaster Bolt deals 3 damage to target creature."
)


THERMAL_DETONATOR = make_instant(
    name="Thermal Detonator",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Thermal Detonator deals 4 damage to target creature or planeswalker. If that creature or planeswalker would die this turn, exile it instead."
)


AGGRESSIVE_NEGOTIATIONS = make_instant(
    name="Aggressive Negotiations",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature you control gets +2/+0 and gains first strike until end of turn. It must attack this turn if able."
)


BOUNTY_POSTED = make_instant(
    name="Bounty Posted",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature can't block this turn. If you control a Bounty Hunter, Bounty Posted deals 2 damage to that creature."
)


RECKLESS_ASSAULT = make_instant(
    name="Reckless Assault",
    mana_cost="{R}{R}",
    colors={Color.RED},
    text="Creatures you control get +2/+0 until end of turn. They attack this turn if able."
)


DISINTEGRATE = make_instant(
    name="Disintegrate",
    mana_cost="{X}{R}",
    colors={Color.RED},
    text="Disintegrate deals X damage to any target. If a creature dealt damage this way would die this turn, exile it instead."
)


# --- Sorceries ---

ORBITAL_STRIKE = make_sorcery(
    name="Orbital Strike",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Orbital Strike deals 4 damage to each creature and each player."
)


BOUNTY_COLLECTION = make_sorcery(
    name="Bounty Collection",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Destroy target creature. Create a Treasure token for each Bounty Hunter you control."
)


RAGE_OF_THE_ARENA = make_sorcery(
    name="Rage of the Arena",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Creatures you control get +2/+0 and gain trample until end of turn. They must attack this turn if able."
)


HIRED_GUNS = make_sorcery(
    name="Hired Guns",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Create two 3/2 red Human Bounty Hunter creature tokens with haste."
)


# --- Enchantments ---

HUNTERS_CODE = make_enchantment(
    name="Hunter's Code",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Bounty Hunter creatures you control get +1/+0 and have haste. Whenever a Bounty Hunter you control deals combat damage to a player, create a Treasure token."
)


ARENA_PIT = make_enchantment(
    name="Arena Pit",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="At the beginning of your upkeep, each player sacrifices a creature. Each player dealt damage this way by a creature they don't control draws a card."
)


GALACTIC_UNDERWORLD = make_enchantment(
    name="Galactic Underworld",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Whenever a creature you control attacks alone, it gets +3/+0 until end of turn. At the beginning of your end step, if three or more creatures died this turn, draw two cards."
)


# =============================================================================
# GREEN CARDS - NATURE PLANETS, WOOKIEES, EWOKS
# =============================================================================

# --- Legendary Creatures ---

def chewbacca_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When another creature you control dies, get +2/+2 until end turn"""
    def creature_death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        if dying_id == source.id:
            return False
        dying = state.objects.get(dying_id)
        return (dying and CardType.CREATURE in dying.characteristics.types and
                dying.controller == source.controller)

    def rage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id,
            'boost': '+2/+2',
            'duration': 'end_of_turn'
        }, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: creature_death_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=rage_effect(e, s)),
        duration='while_on_battlefield'
    )]

CHEWBACCA = make_creature(
    name="Chewbacca, Loyal Companion",
    power=5, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Wookiee", "Warrior"},
    supertypes={"Legendary"},
    text="Trample. Whenever another creature you control dies, Chewbacca gets +2/+2 until end of turn.",
    setup_interceptors=chewbacca_setup
)


def wicket_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Ewoks get +1/+1"""
    return make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Ewok"))

WICKET = make_creature(
    name="Wicket, Ewok Chief",
    power=2, toughness=2,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Ewok", "Scout"},
    supertypes={"Legendary"},
    text="Other Ewok creatures you control get +1/+1. When Wicket enters, create two 1/1 green Ewok creature tokens.",
    setup_interceptors=wicket_setup
)


def tarfful_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Wookiees get +2/+2"""
    return make_static_pt_boost(obj, 2, 2, other_creatures_with_subtype(obj, "Wookiee"))

TARFFUL = make_creature(
    name="Tarfful, Wookiee Chieftain",
    power=5, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Wookiee", "Warrior"},
    supertypes={"Legendary"},
    text="Reach, trample. Other Wookiee creatures you control get +2/+2.",
    setup_interceptors=tarfful_setup
)


def grogu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Force 2 - heal creature or gain life"""
    def force_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 3}, source=obj.id)]
    return [make_force_ability(obj, 2, force_effect)]

GROGU = make_creature(
    name="Grogu, The Child",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Alien", "Jedi"},
    supertypes={"Legendary"},
    text="Hexproof. Force 2 - Pay 2 life: You gain 3 life, or remove all damage from target creature.",
    setup_interceptors=grogu_setup
)


# --- Regular Creatures ---

def wookiee_warrior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Gets +1/+1 for each other Wookiee"""
    def wookiee_count_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id

    # Count based boost would need special handling
    return []

WOOKIEE_WARRIOR = make_creature(
    name="Wookiee Warrior",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Wookiee", "Warrior"},
    text="Trample. Wookiee Warrior gets +1/+1 for each other Wookiee you control."
)


def ewok_ambusher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - fight target creature"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={
            'fight': True,
            'source': obj.id,
            'target_type': 'creature'
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

EWOK_AMBUSHER = make_creature(
    name="Ewok Ambusher",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Ewok", "Warrior"},
    text="When Ewok Ambusher enters, you may have it fight target creature an opponent controls.",
    setup_interceptors=ewok_ambusher_setup
)


EWOK_HUNTER = make_creature(
    name="Ewok Hunter",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Ewok", "Scout"},
    text="Deathtouch."
)


def endor_trapper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When blocks, tap blocked creature. It doesn't untap."""
    def block_effect(event: Event, state: GameState) -> list[Event]:
        blocked_id = event.payload.get('attacker_id')
        return [Event(type=EventType.TAP, payload={
            'object_id': blocked_id,
            'freeze': True
        }, source=obj.id)]

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

ENDOR_TRAPPER = make_creature(
    name="Endor Trapper",
    power=1, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Ewok", "Scout"},
    text="Reach. When Endor Trapper blocks a creature, tap that creature. It doesn't untap during its controller's next untap step.",
    setup_interceptors=endor_trapper_setup
)


KASHYYYK_DEFENDER = make_creature(
    name="Kashyyyk Defender",
    power=3, toughness=5,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Wookiee", "Warrior"},
    text="Reach. When Kashyyyk Defender enters, you may put a +1/+1 counter on another target creature you control."
)


def dagobah_creature_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flash, hexproof, untap all lands when ETB"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.UNTAP, payload={
            'target_type': 'lands_you_control'
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

DAGOBAH_CREATURE = make_creature(
    name="Dagobah Swamp Dweller",
    power=3, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Flash, hexproof. When Dagobah Swamp Dweller enters, untap all lands you control.",
    setup_interceptors=dagobah_creature_setup
)


FELUCIA_BEAST = make_creature(
    name="Felucia Beast",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample. Felucia Beast can't be blocked by creatures with power 2 or less."
)


def jungle_rancor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies, create 3 1/1 tokens"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Beast', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN}, 'subtypes': {'Beast'}}
            }, source=obj.id) for _ in range(3)
        ]
    return [make_death_trigger(obj, death_effect)]

JUNGLE_RANCOR = make_creature(
    name="Jungle Rancor",
    power=5, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample. When Jungle Rancor dies, create three 1/1 green Beast creature tokens.",
    setup_interceptors=jungle_rancor_setup
)


NABOO_RANGER = make_creature(
    name="Naboo Ranger",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout"},
    text="When Naboo Ranger enters, search your library for a basic land card, reveal it, put it into your hand, then shuffle."
)


GUNGAN_WARRIOR = make_creature(
    name="Gungan Warrior",
    power=3, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Gungan", "Warrior"},
    text="When Gungan Warrior enters, add {G}."
)


YAVIN_JUNGLE_CAT = make_creature(
    name="Yavin Jungle Cat",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Cat", "Beast"},
    text="Haste. Yavin Jungle Cat can't be blocked by more than one creature."
)


ENDOR_WILDLIFE = make_creature(
    name="Endor Wildlife",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="When Endor Wildlife dies, you gain 3 life."
)


SARLACC_PIT_SPAWN = make_creature(
    name="Sarlacc Pit Spawn",
    power=1, toughness=6,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Defender, reach. When Sarlacc Pit Spawn blocks a creature, exile that creature at end of combat."
)


# --- Instants ---

WOOKIEE_RAGE = make_instant(
    name="Wookiee Rage",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +4/+4 until end of turn. If it's a Wookiee, it also gains trample until end of turn."
)


FOREST_AMBUSH = make_instant(
    name="Forest Ambush",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature you control fights target creature you don't control."
)


EWOK_TRAP = make_instant(
    name="Ewok Trap",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Tap target creature. It doesn't untap during its controller's next untap step. If you control an Ewok, draw a card."
)


NATURAL_CAMOUFLAGE = make_instant(
    name="Natural Camouflage",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gains hexproof and indestructible until end of turn."
)


JUNGLE_GROWTH = make_instant(
    name="Jungle Growth",
    mana_cost="{G}{G}",
    colors={Color.GREEN},
    text="Put two +1/+1 counters on target creature. It gains trample until end of turn."
)


PRIMAL_CONNECTION = make_instant(
    name="Primal Connection",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Draw cards equal to the greatest power among creatures you control."
)


# --- Sorceries ---

CALL_OF_THE_WILD = make_sorcery(
    name="Call of the Wild",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Create a 4/4 green Beast creature token with trample. Then create a 2/2 green Beast creature token."
)


EWOK_UPRISING = make_sorcery(
    name="Ewok Uprising",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Create four 1/1 green Ewok creature tokens. Ewoks you control gain trample until end of turn."
)


FORCE_OF_NATURE = make_sorcery(
    name="Force of Nature",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Put four +1/+1 counters on target creature you control. It gains trample and hexproof until end of turn."
)


RAMPANT_GROWTH = make_sorcery(
    name="Rampant Growth",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card, put it onto the battlefield tapped, then shuffle."
)


# --- Enchantments ---

EWOK_VILLAGE = make_enchantment(
    name="Ewok Village",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="At the beginning of your upkeep, create a 1/1 green Ewok creature token. Ewoks you control have '{T}: Add {G}.'"
)


KASHYYYK_HOMELAND = make_enchantment(
    name="Kashyyyk Homeland",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Wookiee creatures you control get +2/+2 and have vigilance. Whenever a Wookiee you control deals combat damage to a player, draw a card."
)


THE_LIVING_FORCE = make_enchantment(
    name="The Living Force",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Whenever a creature enters under your control, you gain 1 life. {2}{G}: Create a 1/1 green Beast creature token."
)


# =============================================================================
# MULTICOLOR CARDS - MAJOR CHARACTERS
# =============================================================================

# --- Legendary Creatures ---

def han_solo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """First strike, haste, Pilot bonus"""
    return [make_pilot_crew_bonus(obj, 3, 1)]

HAN_SOLO = make_creature(
    name="Han Solo, Scoundrel",
    power=3, toughness=3,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Rebel", "Rogue", "Pilot"},
    supertypes={"Legendary"},
    text="First strike, haste. Pilot - When Han Solo crews a Vehicle, that Vehicle gets +3/+1 and gains first strike until end of turn.",
    setup_interceptors=han_solo_setup
)


def anakin_skywalker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Light Side/Dark Side - gets different bonuses"""
    interceptors = []
    interceptors.extend(make_light_side_bonus(obj, 2, 2))
    interceptors.extend(make_dark_side_bonus(obj, 3, 0))
    return interceptors

ANAKIN_SKYWALKER = make_creature(
    name="Anakin Skywalker, Chosen One",
    power=4, toughness=4,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Jedi"},
    supertypes={"Legendary"},
    text="Flying. Light Side - Anakin gets +2/+2 as long as you have 10 or more life. Dark Side - Anakin gets +3/+0 as long as you have less than 10 life.",
    setup_interceptors=anakin_skywalker_setup
)


def padme_amidala_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Protection from creatures with power 4+, draws when creature ETB"""
    def creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == source.id:
            return False
        entering = state.objects.get(entering_id)
        return (entering and CardType.CREATURE in entering.characteristics.types and
                entering.controller == source.controller)

    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: creature_etb_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=draw_effect(e, s)),
        duration='while_on_battlefield'
    )]

PADME_AMIDALA = make_creature(
    name="Padme Amidala, Senator",
    power=2, toughness=4,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Noble", "Advisor"},
    supertypes={"Legendary"},
    text="Protection from creatures with power 4 or greater. Whenever another creature enters under your control, draw a card.",
    setup_interceptors=padme_amidala_setup
)


def ahsoka_tano_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Double strike + when deals damage, exile target card from graveyard"""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.ZONE_CHANGE, payload={
            'target_type': 'card_in_graveyard',
            'to_zone_type': ZoneType.EXILE
        }, source=obj.id)]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

AHSOKA_TANO = make_creature(
    name="Ahsoka Tano, Former Padawan",
    power=3, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Togruta", "Jedi"},
    supertypes={"Legendary"},
    text="Double strike. Whenever Ahsoka Tano deals combat damage to a player, exile target card from that player's graveyard.",
    setup_interceptors=ahsoka_tano_setup
)


def kylo_ren_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dark Side bonus + menace"""
    return make_dark_side_bonus(obj, 3, 3)

KYLO_REN = make_creature(
    name="Kylo Ren, Conflicted",
    power=4, toughness=4,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Sith"},
    supertypes={"Legendary"},
    text="Menace. Dark Side - Kylo Ren gets +3/+3 as long as you have less than 10 life. When Kylo Ren deals combat damage to a player, that player discards a card.",
    setup_interceptors=kylo_ren_setup
)


def rey_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Light Side bonus + scavenge ability"""
    return make_light_side_bonus(obj, 2, 2)

REY = make_creature(
    name="Rey, Scavenger",
    power=3, toughness=3,
    mana_cost="{1}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Human", "Jedi"},
    supertypes={"Legendary"},
    text="Vigilance. Light Side - Rey gets +2/+2 as long as you have 10 or more life. Whenever Rey attacks, you may return target artifact card from your graveyard to your hand.",
    setup_interceptors=rey_setup
)


def finn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """First strike when attacking, Rebels get +1/+1 when attacks"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'boost': 'rebels_plus_one',
            'controller': obj.controller,
            'duration': 'end_of_turn'
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

FINN = make_creature(
    name="Finn, Defector",
    power=3, toughness=2,
    mana_cost="{1}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Rebel", "Soldier"},
    supertypes={"Legendary"},
    text="First strike. Whenever Finn attacks, other Rebel creatures you control get +1/+1 until end of turn.",
    setup_interceptors=finn_setup
)


def poe_dameron_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Pilot bonus + flying"""
    return [make_pilot_crew_bonus(obj, 2, 1)]

POE_DAMERON = make_creature(
    name="Poe Dameron, Best Pilot",
    power=2, toughness=2,
    mana_cost="{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Rebel", "Pilot"},
    supertypes={"Legendary"},
    text="Flying, haste. Pilot - When Poe Dameron crews a Vehicle, that Vehicle gets +2/+1 and gains flying until end of turn.",
    setup_interceptors=poe_dameron_setup
)


def lando_calrissian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - create treasure, Pilot"""
    interceptors = []

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'}}
        }, source=obj.id)]
    interceptors.append(make_etb_trigger(obj, etb_effect))
    interceptors.append(make_pilot_crew_bonus(obj, 1, 1))
    return interceptors

LANDO_CALRISSIAN = make_creature(
    name="Lando Calrissian, Gambler",
    power=3, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Rebel", "Rogue", "Pilot"},
    supertypes={"Legendary"},
    text="When Lando Calrissian enters, create a Treasure token. Pilot - When Lando crews a Vehicle, that Vehicle gets +1/+1 until end of turn.",
    setup_interceptors=lando_calrissian_setup
)


def general_grievous_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """First strike + when kills creature, draw a card"""
    def kill_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        return event.payload.get('damage_source') == source.id

    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: kill_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=draw_effect(e, s)),
        duration='while_on_battlefield'
    )]

GENERAL_GRIEVOUS = make_artifact_creature(
    name="General Grievous, Jedi Hunter",
    power=5, toughness=4,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Droid", "Warrior"},
    supertypes={"Legendary"},
    text="First strike, menace. Whenever General Grievous destroys a creature in combat, draw a card.",
    setup_interceptors=general_grievous_setup
)


def asajj_ventress_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Double strike + Dark Side bonus"""
    return make_dark_side_bonus(obj, 2, 0)

ASAJJ_VENTRESS = make_creature(
    name="Asajj Ventress, Sith Assassin",
    power=3, toughness=3,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Dathomirian", "Sith"},
    supertypes={"Legendary"},
    text="Double strike. Dark Side - Asajj Ventress gets +2/+0 as long as you have less than 10 life.",
    setup_interceptors=asajj_ventress_setup
)


def jar_jar_binks_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a spell, random effect (coin flip)"""
    def cast_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_spell_cast_trigger(obj, cast_effect)]

JAR_JAR_BINKS = make_creature(
    name="Jar Jar Binks, Accidental Hero",
    power=1, toughness=3,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Gungan", "Ally"},
    supertypes={"Legendary"},
    text="Whenever you cast a spell, flip a coin. If you win, draw a card. If you lose, target opponent draws a card.",
    setup_interceptors=jar_jar_binks_setup
)


def maz_kanata_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - search for equipment"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.ZONE_CHANGE, payload={
            'search_type': 'equipment',
            'to_zone': ZoneType.HAND
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

MAZ_KANATA = make_creature(
    name="Maz Kanata, Ancient Pirate",
    power=1, toughness=3,
    mana_cost="{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Alien", "Pirate"},
    supertypes={"Legendary"},
    text="When Maz Kanata enters, search your library for an Equipment card, reveal it, put it into your hand, then shuffle.",
    setup_interceptors=maz_kanata_setup
)


def thrawn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At upkeep, look at top card of opponent's library"""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        opponents = all_opponents(obj, state)
        return [Event(type=EventType.SCRY, payload={
            'player': obj.controller,
            'target': opponents[0] if opponents else None,
            'look_at_opponent': True
        }, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

THRAWN = make_creature(
    name="Grand Admiral Thrawn",
    power=3, toughness=4,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Chiss", "Empire", "Advisor"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, look at the top card of target opponent's library. You may put it on the bottom of that library.",
    setup_interceptors=thrawn_setup
)


DARTH_SIDIOUS = make_creature(
    name="Darth Sidious, Puppetmaster",
    power=3, toughness=5,
    mana_cost="{2}{U}{B}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Sith"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, gain control of target creature with the least power. At the beginning of each end step, that creature's controller may pay {3}. If they do, that creature returns to their control."
)


# --- Multicolor Non-Legendary ---

REBEL_COMMANDO_TEAM = make_creature(
    name="Rebel Commando Team",
    power=3, toughness=3,
    mana_cost="{1}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Human", "Rebel", "Soldier"},
    text="Trample. When Rebel Commando Team enters, create a 1/1 white Human Rebel Soldier creature token."
)


SEPARATIST_COMMANDER = make_creature(
    name="Separatist Commander",
    power=3, toughness=3,
    mana_cost="{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Advisor"},
    text="When Separatist Commander enters, each opponent discards a card. Then you draw a card."
)


MANDALORIAN_FORGE_MASTER = make_creature(
    name="Mandalorian Forge-Master",
    power=2, toughness=3,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Mandalorian", "Artificer"},
    text="When Mandalorian Forge-Master enters, create a colorless Equipment artifact token named Beskar Armor with 'Equipped creature gets +2/+2. Equip {2}'."
)


FORCE_SENSITIVE = make_creature(
    name="Force Sensitive",
    power=2, toughness=2,
    mana_cost="{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Jedi"},
    text="When Force Sensitive enters, scry 2. Force 1 - Pay 1 life: Draw a card."
)


HUTT_CRIME_LORD = make_creature(
    name="Hutt Crime Lord",
    power=2, toughness=5,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Hutt", "Rogue"},
    text="When Hutt Crime Lord enters, create two Treasure tokens. Sacrifice a creature: Hutt Crime Lord gains indestructible until end of turn."
)


# --- Multicolor Instants ---

BALANCE_OF_THE_FORCE = make_instant(
    name="Balance of the Force",
    mana_cost="{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    text="Destroy target creature with the greatest power. You gain life equal to its power."
)


FORCE_LIGHTNING = make_instant(
    name="Force Lightning",
    mana_cost="{U}{B}{R}",
    colors={Color.BLUE, Color.BLACK, Color.RED},
    text="Force Lightning deals 4 damage to any target. If you control a Sith, Force Lightning deals 6 damage instead."
)


UNITY_OF_THE_REBELLION = make_instant(
    name="Unity of the Rebellion",
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Creatures you control get +2/+0 and gain vigilance until end of turn."
)


# --- Multicolor Sorceries ---

GALACTIC_SENATE_DECREE = make_sorcery(
    name="Galactic Senate Decree",
    mana_cost="{W}{U}{B}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK},
    text="Choose one - Destroy target creature; or counter target spell; or return target permanent to its owner's hand."
)


DEVASTATION_OF_ALDERAAN = make_sorcery(
    name="Devastation of Alderaan",
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Destroy all lands target player controls. That player may search their library for two basic land cards and put them onto the battlefield tapped."
)


# =============================================================================
# ARTIFACTS, EQUIPMENT, AND VEHICLES
# =============================================================================

# --- Lightsabers (Equipment) ---

LUKES_LIGHTSABER = make_equipment(
    name="Luke's Lightsaber",
    mana_cost="{2}",
    equip_cost="{2}",
    text="Equipped creature gets +2/+0 and has first strike. If equipped creature is a Jedi, it gets +3/+0 instead.",
    subtypes={"Lightsaber"},
    supertypes={"Legendary"}
)


DARTH_VADERS_LIGHTSABER = make_equipment(
    name="Darth Vader's Lightsaber",
    mana_cost="{2}",
    equip_cost="{2}",
    text="Equipped creature gets +2/+0 and has menace. If equipped creature is a Sith, it gets +3/+0 and has deathtouch.",
    subtypes={"Lightsaber"},
    supertypes={"Legendary"}
)


DOUBLE_BLADED_LIGHTSABER = make_equipment(
    name="Double-Bladed Lightsaber",
    mana_cost="{3}",
    equip_cost="{3}",
    text="Equipped creature gets +2/+1 and has double strike. If equipped creature is a Jedi or Sith, it gets +3/+1 instead.",
    subtypes={"Lightsaber"}
)


LIGHTSABER = make_equipment(
    name="Lightsaber",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature gets +2/+0 and has first strike.",
    subtypes={"Lightsaber"}
)


DARK_SABER = make_equipment(
    name="Darksaber",
    mana_cost="{3}",
    equip_cost="{2}",
    text="Equipped creature gets +2/+2 and has menace. Other creatures you control with Equipment attached get +1/+0.",
    subtypes={"Lightsaber"},
    supertypes={"Legendary"}
)


# --- Other Equipment ---

MANDALORIAN_ARMOR = make_equipment(
    name="Mandalorian Armor",
    mana_cost="{2}",
    equip_cost="{2}",
    text="Equipped creature gets +1/+3 and has protection from instants."
)


BESKAR_HELMET = make_equipment(
    name="Beskar Helmet",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature gets +0/+2 and has hexproof."
)


JETPACK = make_equipment(
    name="Jetpack",
    mana_cost="{2}",
    equip_cost="{1}",
    text="Equipped creature has flying and haste."
)


BLASTER_RIFLE = make_equipment(
    name="Blaster Rifle",
    mana_cost="{2}",
    equip_cost="{2}",
    text="Equipped creature gets +1/+0 and has '{T}: This creature deals 2 damage to any target.'"
)


BOWCASTER = make_equipment(
    name="Bowcaster",
    mana_cost="{3}",
    equip_cost="{2}",
    text="Equipped creature gets +2/+0 and has '{T}: This creature deals 3 damage to target creature.' If equipped creature is a Wookiee, that damage can't be prevented.",
    supertypes={"Legendary"}
)


ELECTROSTAFF = make_equipment(
    name="Electrostaff",
    mana_cost="{2}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+1 and has first strike. Whenever equipped creature blocks or becomes blocked by a creature, that creature gets -1/-0 until end of turn."
)


SLAVE_TRACKER = make_equipment(
    name="Slave Tracker",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+1. Whenever equipped creature deals combat damage to a player, that player reveals their hand."
)


# --- Vehicles ---

MILLENNIUM_FALCON = make_vehicle(
    name="Millennium Falcon",
    power=5, toughness=5,
    mana_cost="{4}",
    crew=2,
    text="Flying, haste. Whenever Millennium Falcon deals combat damage to a player, draw two cards.",
    supertypes={"Legendary"}
)


X_WING = make_vehicle(
    name="X-Wing Starfighter",
    power=3, toughness=3,
    mana_cost="{3}",
    crew=1,
    text="Flying. When X-Wing Starfighter attacks, it deals 1 damage to any target."
)


TIE_FIGHTER = make_vehicle(
    name="TIE Fighter",
    power=2, toughness=2,
    mana_cost="{2}",
    crew=1,
    text="Flying. When TIE Fighter dies, it deals 2 damage to any target."
)


STAR_DESTROYER = make_vehicle(
    name="Star Destroyer",
    power=8, toughness=8,
    mana_cost="{6}",
    crew=4,
    text="Flying, vigilance. Star Destroyer can't be blocked except by creatures with flying.",
    supertypes={"Legendary"}
)


SLAVE_I = make_vehicle(
    name="Slave I",
    power=4, toughness=4,
    mana_cost="{4}",
    crew=1,
    text="Flying. Whenever Slave I deals combat damage to a player, exile target creature that player controls until Slave I leaves the battlefield.",
    supertypes={"Legendary"}
)


SPEEDER_BIKE = make_vehicle(
    name="Speeder Bike",
    power=2, toughness=1,
    mana_cost="{2}",
    crew=1,
    text="Haste. Speeder Bike can't be blocked by creatures with power 3 or greater."
)


AT_AT = make_vehicle(
    name="AT-AT Walker",
    power=6, toughness=6,
    mana_cost="{5}",
    crew=3,
    text="Trample. AT-AT Walker can't be blocked by creatures with power 2 or less."
)


AT_ST = make_vehicle(
    name="AT-ST Walker",
    power=4, toughness=3,
    mana_cost="{3}",
    crew=2,
    text="Menace. When AT-ST Walker attacks, it deals 1 damage to each creature defending player controls."
)


REPUBLIC_GUNSHIP = make_vehicle(
    name="Republic Gunship",
    power=3, toughness=4,
    mana_cost="{3}",
    crew=2,
    text="Flying. When Republic Gunship enters, create a 2/2 white Human Clone Soldier creature token."
)


PODRACER_VEHICLE = make_vehicle(
    name="Podracer",
    power=4, toughness=2,
    mana_cost="{2}",
    crew=1,
    text="Haste. Podracer can attack the turn it enters. At the beginning of your end step, sacrifice Podracer unless you pay {1}."
)


THE_RAZOR_CREST = make_vehicle(
    name="The Razor Crest",
    power=4, toughness=5,
    mana_cost="{4}",
    crew=1,
    text="Flying. Whenever The Razor Crest deals combat damage to a player, create a Treasure token. You may pay {2}: Put a creature card from your hand onto the battlefield.",
    supertypes={"Legendary"}
)


Y_WING = make_vehicle(
    name="Y-Wing Bomber",
    power=3, toughness=4,
    mana_cost="{3}",
    crew=1,
    text="Flying. When Y-Wing Bomber attacks, it deals 2 damage to target creature defending player controls."
)


# --- Other Artifacts ---

def death_star_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tap to destroy target creature or land"""
    return []  # Activated ability handled by game engine

DEATH_STAR = make_artifact(
    name="Death Star",
    mana_cost="{8}",
    text="{5}, {T}: Destroy target permanent. If it was a land, its controller loses 5 life.",
    supertypes={"Legendary"},
    setup_interceptors=death_star_setup
)


HOLOCRON = make_artifact(
    name="Jedi Holocron",
    mana_cost="{2}",
    text="{T}: Add one mana of any color. Spend this mana only to cast creature spells or activate abilities of creatures. {2}, {T}: Scry 2."
)


SITH_HOLOCRON = make_artifact(
    name="Sith Holocron",
    mana_cost="{2}",
    text="{T}, Pay 1 life: Add {B}{B}. {2}, {T}: Each opponent loses 1 life and you gain 1 life."
)


CARBONITE_PRISON = make_artifact(
    name="Carbonite Prison",
    mana_cost="{3}",
    text="When Carbonite Prison enters, exile target creature an opponent controls until Carbonite Prison leaves the battlefield. {3}: Return that creature to the battlefield under its owner's control."
)


KYBER_CRYSTAL = make_artifact(
    name="Kyber Crystal",
    mana_cost="{1}",
    text="{T}: Add {C}. {T}, Sacrifice Kyber Crystal: Add one mana of any color. If you control a Jedi or Sith, add two mana of any one color instead."
)


STORMTROOPER_BARRACKS = make_artifact(
    name="Stormtrooper Barracks",
    mana_cost="{3}",
    text="At the beginning of your upkeep, create a 2/1 black Human Empire Trooper creature token."
)


DROID_FOUNDRY = make_artifact(
    name="Droid Foundry",
    mana_cost="{4}",
    text="At the beginning of your upkeep, create a 1/1 colorless Droid artifact creature token. Droids you control get +1/+0."
)


TRADE_FEDERATION_VAULT = make_artifact(
    name="Trade Federation Vault",
    mana_cost="{3}",
    text="At the beginning of your upkeep, create a Treasure token. Sacrifice three Treasures: Draw two cards."
)


BACTA_TANK = make_artifact(
    name="Bacta Tank",
    mana_cost="{2}",
    text="{2}, {T}: Remove all damage from target creature. You gain 2 life."
)


HYPERDRIVE = make_artifact(
    name="Hyperdrive",
    mana_cost="{3}",
    text="Vehicles you control have haste. {2}, {T}: Untap target Vehicle."
)


SHIELD_GENERATOR = make_artifact(
    name="Shield Generator",
    mana_cost="{4}",
    text="Creatures you control have hexproof. {2}, Sacrifice Shield Generator: Creatures you control gain indestructible until end of turn."
)


# =============================================================================
# LANDS
# =============================================================================

# --- Special Lands ---

CORUSCANT = make_land(
    name="Coruscant",
    text="{T}: Add {C}. {T}: Add {W} or {U}. Activate only if you control a creature.",
    supertypes={"Legendary"}
)


TATOOINE = make_land(
    name="Tatooine",
    text="{T}: Add {C}. {1}, {T}: Add {R}{R}."
)


ENDOR_FOREST = make_land(
    name="Endor Forest",
    text="{T}: Add {G}. {2}{G}, {T}: Create a 1/1 green Ewok creature token.",
    subtypes={"Forest"}
)


KASHYYYK = make_land(
    name="Kashyyyk",
    text="{T}: Add {G}. Wookiee creatures you control get +0/+1.",
    supertypes={"Legendary"}
)


MUSTAFAR = make_land(
    name="Mustafar",
    text="{T}: Add {B} or {R}. Whenever you cast a Sith spell, Mustafar deals 1 damage to each opponent.",
    supertypes={"Legendary"}
)


DAGOBAH = make_land(
    name="Dagobah",
    text="{T}: Add {G} or {U}. {2}, {T}: Scry 1.",
    supertypes={"Legendary"}
)


HOTH = make_land(
    name="Hoth",
    text="{T}: Add {W}. {T}: Target creature gets -1/-0 until end of turn."
)


NABOO = make_land(
    name="Naboo",
    text="{T}: Add {W}, {U}, or {G}. Naboo enters tapped.",
    supertypes={"Legendary"}
)


KAMINO = make_land(
    name="Kamino",
    text="{T}: Add {U}. {3}{U}, {T}: Create a 2/2 white Human Clone Soldier creature token.",
    supertypes={"Legendary"}
)


GEONOSIS = make_land(
    name="Geonosis",
    text="{T}: Add {R}. {2}{R}, {T}: Create a 1/1 colorless Droid Soldier artifact creature token."
)


JAKKU = make_land(
    name="Jakku",
    text="{T}: Add {C}. {2}, {T}: Return target artifact card from your graveyard to your hand."
)


CLOUD_CITY = make_land(
    name="Cloud City",
    text="{T}: Add {U} or {R}. Vehicles you control get +0/+1.",
    supertypes={"Legendary"}
)


MOS_EISLEY = make_land(
    name="Mos Eisley Spaceport",
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast creature spells."
)


JEDI_TEMPLE = make_land(
    name="Jedi Temple",
    text="{T}: Add {W} or {U}. Jedi creatures you control have '{T}: Add {W} or {U}.'",
    supertypes={"Legendary"}
)


SITH_TEMPLE = make_land(
    name="Sith Temple",
    text="{T}: Add {B}. {T}, Pay 1 life: Add {B}{B}. Sith creatures you control get +1/+0.",
    supertypes={"Legendary"}
)


DEATH_STAR_HANGAR = make_land(
    name="Death Star Hangar",
    text="{T}: Add {C}. {T}: Add {B}. Spend this mana only to cast artifact or Vehicle spells."
)


REBEL_BASE = make_land(
    name="Rebel Base",
    text="{T}: Add {W} or {R}. Rebel creatures you control get +0/+1.",
    supertypes={"Legendary"}
)


# --- Basic Lands ---

PLAINS_SWG = make_land(
    name="Plains",
    text="{T}: Add {W}.",
    subtypes={"Plains"}
)


ISLAND_SWG = make_land(
    name="Island",
    text="{T}: Add {U}.",
    subtypes={"Island"}
)


SWAMP_SWG = make_land(
    name="Swamp",
    text="{T}: Add {B}.",
    subtypes={"Swamp"}
)


MOUNTAIN_SWG = make_land(
    name="Mountain",
    text="{T}: Add {R}.",
    subtypes={"Mountain"}
)


FOREST_SWG = make_land(
    name="Forest",
    text="{T}: Add {G}.",
    subtypes={"Forest"}
)


# =============================================================================
# ADDITIONAL CARDS
# =============================================================================

# --- Additional White Cards ---

CLONE_CAPTAIN_REX = make_creature(
    name="Clone Captain Rex",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Clone", "Soldier"},
    supertypes={"Legendary"},
    text="First strike. Other Clone creatures you control get +1/+1."
)


BAIL_ORGANA = make_creature(
    name="Bail Organa",
    power=2, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rebel", "Noble"},
    supertypes={"Legendary"},
    text="When Bail Organa enters, search your library for a Rebel creature card with mana value 2 or less, reveal it, put it into your hand, then shuffle."
)


MON_MOTHMA = make_creature(
    name="Mon Mothma",
    power=1, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rebel", "Advisor"},
    supertypes={"Legendary"},
    text="Rebel spells you cast cost {1} less to cast. At the beginning of your end step, if you control three or more Rebels, draw a card."
)


ROYAL_GUARD = make_creature(
    name="Royal Guard",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Vigilance, lifelink."
)


ALDERAANIAN_REFUGEE = make_creature(
    name="Alderaanian Refugee",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    text="When Alderaanian Refugee enters, you gain 2 life."
)


FORCE_BARRIER = make_instant(
    name="Force Barrier",
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    text="Prevent all damage that would be dealt to creatures you control this turn. If you control a Jedi, draw a card."
)


# --- Additional Blue Cards ---

BB8 = make_artifact_creature(
    name="BB-8, Loyal Astromech",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Droid"},
    supertypes={"Legendary"},
    text="When BB-8 enters, scry 2. {T}: Target Vehicle you control can't be blocked this turn."
)


K2SO = make_artifact_creature(
    name="K-2SO, Reprogrammed",
    power=3, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Droid"},
    supertypes={"Legendary"},
    text="When K-2SO enters, draw two cards, then discard a card. K-2SO can block any number of creatures."
)


SUPER_BATTLE_DROID = make_artifact_creature(
    name="Super Battle Droid",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Droid", "Soldier"},
    text="When Super Battle Droid enters, create a 1/1 colorless Droid Soldier artifact creature token."
)


TACTICAL_DROID = make_artifact_creature(
    name="Tactical Droid",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Droid", "Advisor"},
    text="Other Droid creatures you control get +0/+1. {T}: Scry 1."
)


INFORMATION_BROKER = make_creature(
    name="Information Broker",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="{1}{U}, {T}: Look at the top three cards of target opponent's library. Put one on the bottom."
)


FORCE_ILLUSION = make_instant(
    name="Force Illusion",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Create a token that's a copy of target creature you control, except it's an illusion with 'Sacrifice this creature when it becomes the target of a spell or ability.' Exile it at end of turn."
)


# --- Additional Black Cards ---

DARTH_BANE = make_creature(
    name="Darth Bane, Rule Creator",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Sith"},
    supertypes={"Legendary"},
    text="Menace, lifelink. At the beginning of your upkeep, you may sacrifice another creature. If you do, put two +1/+1 counters on Darth Bane."
)


GRAND_INQUISITOR = make_creature(
    name="Grand Inquisitor",
    power=4, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Pau'an", "Sith"},
    supertypes={"Legendary"},
    text="Flying, deathtouch. Whenever Grand Inquisitor deals combat damage to a player, that player exiles a creature card from their graveyard. You may cast that card."
)


IMPERIAL_EXECUTIONER = make_creature(
    name="Imperial Executioner",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Empire", "Soldier"},
    text="Deathtouch. When Imperial Executioner enters, destroy target creature with power 2 or less."
)


SNOKE = make_creature(
    name="Snoke, Supreme Leader",
    power=3, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Alien", "Sith"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, each opponent loses 2 life. You gain life equal to the life lost this way."
)


DARK_RITUAL = make_instant(
    name="Dark Ritual of the Sith",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Add {B}{B}{B}. You lose 1 life."
)


# --- Additional Red Cards ---

AURRA_SING = make_creature(
    name="Aurra Sing, Sniper",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Alien", "Bounty Hunter"},
    supertypes={"Legendary"},
    text="Reach. {T}: Aurra Sing deals 2 damage to target creature or planeswalker."
)


BOSSK = make_creature(
    name="Bossk, Trandoshan Hunter",
    power=4, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Trandoshan", "Bounty Hunter"},
    supertypes={"Legendary"},
    text="Trample. Whenever Bossk deals combat damage to a player, create a Treasure token for each creature that died this turn."
)


FENNEC_SHAND = make_creature(
    name="Fennec Shand, Elite Assassin",
    power=3, toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Bounty Hunter"},
    supertypes={"Legendary"},
    text="Haste, first strike. Whenever Fennec Shand deals combat damage to a player, that player discards a card at random."
)


DEATH_WATCH_WARRIOR = make_creature(
    name="Death Watch Warrior",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Mandalorian", "Warrior"},
    text="Flying. When Death Watch Warrior enters, it deals 2 damage to each opponent."
)


WRIST_ROCKET = make_instant(
    name="Wrist Rocket",
    mana_cost="{R}",
    colors={Color.RED},
    text="Wrist Rocket deals 2 damage to any target. If you control a Mandalorian, it deals 3 damage instead."
)


# --- Additional Green Cards ---

YADDLE = make_creature(
    name="Yaddle, Jedi Council Member",
    power=2, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Alien", "Jedi"},
    supertypes={"Legendary"},
    text="Whenever you cast a creature spell, you may pay {G}. If you do, put a +1/+1 counter on target creature you control."
)


WOOKIEE_BERSERKER = make_creature(
    name="Wookiee Berserker",
    power=5, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Wookiee", "Warrior"},
    text="Trample. Wookiee Berserker gets +2/+0 as long as a creature died this turn."
)


EWOK_SHAMAN = make_creature(
    name="Ewok Shaman",
    power=1, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Ewok", "Shaman"},
    text="{T}: Add {G}. {2}{G}, {T}: Target creature you control gets +2/+2 until end of turn."
)


RANCOR = make_creature(
    name="Rancor",
    power=7, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample. Rancor can't be blocked by creatures with power 2 or less.",
    supertypes={"Legendary"}
)


NEXU = make_creature(
    name="Nexu",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Cat", "Beast"},
    text="Deathtouch, haste."
)


BEAST_CALL = make_sorcery(
    name="Beast Call",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a Beast creature card with mana value 4 or less, reveal it, put it into your hand, then shuffle."
)


# --- Additional Multicolor Cards ---

CAPTAIN_PHASMA = make_creature(
    name="Captain Phasma",
    power=4, toughness=4,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Empire", "Soldier"},
    supertypes={"Legendary"},
    text="First strike. Other Empire creatures you control get +1/+1. When Captain Phasma dies, create two 2/1 black Human Empire Trooper creature tokens."
)


SABINE_WREN = make_creature(
    name="Sabine Wren, Mandalorian Artist",
    power=3, toughness=2,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Mandalorian", "Rebel"},
    supertypes={"Legendary"},
    text="Haste. When Sabine Wren enters, you may destroy target artifact. If you do, Sabine Wren deals 2 damage to its controller."
)


EZRA_BRIDGER = make_creature(
    name="Ezra Bridger, Street Kid",
    power=2, toughness=3,
    mana_cost="{1}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Jedi", "Rebel"},
    supertypes={"Legendary"},
    text="When Ezra Bridger enters, draw a card. Ezra Bridger gets +2/+2 as long as you control another Rebel."
)


KANAN_JARRUS = make_creature(
    name="Kanan Jarrus, Blinded Master",
    power=3, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Jedi", "Rebel"},
    supertypes={"Legendary"},
    text="Vigilance, hexproof from creatures. Other Jedi and Rebel creatures you control get +1/+1."
)


HERA_SYNDULLA = make_creature(
    name="Hera Syndulla, Ghost Captain",
    power=2, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Twi'lek", "Rebel", "Pilot"},
    supertypes={"Legendary"},
    text="Flying. Pilot - When Hera Syndulla crews a Vehicle, that Vehicle gets +2/+2 and gains vigilance until end of turn."
)


# --- Additional Artifacts ---

TRAINING_REMOTE = make_artifact(
    name="Training Remote",
    mana_cost="{1}",
    text="{2}, {T}: Target creature you control gains first strike until end of turn. If it's a Jedi, it also gets +1/+1 until end of turn."
)


RESTRAINING_BOLT = make_artifact(
    name="Restraining Bolt",
    mana_cost="{1}",
    text="Enchant artifact creature. Enchanted creature can't attack or block and its activated abilities can't be activated."
)


THERMAL_IMAGING_GOGGLES = make_equipment(
    name="Thermal Imaging Goggles",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature can't be blocked by creatures with power 2 or less."
)


# --- Additional Lands ---

SCARIF = make_land(
    name="Scarif",
    text="{T}: Add {U} or {G}. {3}, {T}: Draw a card, then discard a card.",
    supertypes={"Legendary"}
)


JEDHA = make_land(
    name="Jedha",
    text="{T}: Add {W}. {2}{W}, {T}: Create a 1/1 white Human Rebel creature token."
)


MANDALORE = make_land(
    name="Mandalore",
    text="{T}: Add {R} or {W}. Mandalorian creatures you control get +0/+1.",
    supertypes={"Legendary"}
)


BESPIN = make_land(
    name="Bespin",
    text="{T}: Add {U}. Vehicles you control have '{T}: Add one mana of any color.'"
)


LOTHAL = make_land(
    name="Lothal",
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast Rebel spells."
)


# =============================================================================
# CARD REGISTRY
# =============================================================================

STAR_WARS_CARDS = {
    # WHITE - REBELS, JEDI, LIGHT SIDE
    "Luke Skywalker, New Hope": LUKE_SKYWALKER_NEW_HOPE,
    "Leia Organa, Rebel Leader": LEIA_ORGANA,
    "Obi-Wan Kenobi, Wise Master": OBI_WAN_KENOBI,
    "Yoda, Grand Master": YODA_GRAND_MASTER,
    "Mace Windu, Champion of Light": MACE_WINDU,
    "Rebel Pilot": REBEL_PILOT,
    "Jedi Padawan": JEDI_PADAWAN,
    "Rebel Trooper": REBEL_TROOPER,
    "Alderaanian Diplomat": ALDERAANIAN_DIPLOMAT,
    "Jedi Temple Guard": JEDI_TEMPLE_GUARD,
    "Echo Base Defender": ECHO_BASE_DEFENDER,
    "Rebel Medic": REBEL_MEDIC,
    "Hope of the Rebellion": HOPE_OF_THE_REBELLION,
    "Coruscant Peacekeeper": CORUSCANT_PEACEKEEPER,
    "Resistance Commander": RESISTANCE_COMMANDER,
    "Jedi Sentinel": JEDI_SENTINEL,
    "Rebellion Sympathizer": REBELLION_SYMPATHIZER,
    "Tatooine Homesteader": TATOOINE_HOMESTEADER,
    "Galactic Senator": GALACTIC_SENATOR,
    "Force Protection": FORCE_PROTECTION,
    "Rebel Ambush": REBEL_AMBUSH,
    "Jedi Reflexes": JEDI_REFLEXES,
    "Hope Renewed": HOPE_RENEWED,
    "Defensive Formation": DEFENSIVE_FORMATION,
    "Light of the Force": LIGHT_OF_THE_FORCE,
    "Call to Arms": CALL_TO_ARMS,
    "Liberation Day": LIBERATION_DAY,
    "Jedi Training": JEDI_TRAINING,
    "Evacuation Plan": EVACUATION_PLAN,
    "The Light Side": THE_LIGHT_SIDE,
    "Rebel Alliance": REBEL_ALLIANCE,
    "Jedi Sanctuary": JEDI_SANCTUARY,

    # BLUE - JEDI MIND TRICKS, TECHNOLOGY, DROIDS
    "R2-D2, Astromech Hero": R2D2,
    "C-3PO, Protocol Droid": C3PO,
    "Admiral Ackbar, Fleet Commander": ADMIRAL_ACKBAR,
    "Qui-Gon Jinn, Living Force": QUI_GON_JINN,
    "Astromech Droid": ASTROMECH_DROID,
    "Protocol Droid": PROTOCOL_DROID,
    "Jedi Scholar": JEDI_SCHOLAR,
    "Cloud City Engineer": CLOUD_CITY_ENGINEER,
    "Battle Droid": BATTLE_DROID,
    "Probe Droid": PROBE_DROID,
    "Kamino Cloner": KAMINO_CLONER,
    "Mon Calamari Captain": MON_CALAMARI_CAPTAIN,
    "Rebel Strategist": REBEL_STRATEGIST,
    "Coruscant Archivist": CORUSCANT_ARCHIVIST,
    "Holo-Projector Droid": HOLO_PROJECTOR_DROID,
    "Separatist Infiltrator": SEPARATIST_INFILTRATOR,
    "Jedi Investigator": JEDI_INVESTIGATOR,
    "Jedi Mind Trick": JEDI_MIND_TRICK,
    "Force Push": FORCE_PUSH,
    "Holographic Decoy": HOLOGRAPHIC_DECOY,
    "Hyperspace Jump": HYPERSPACE_JUMP,
    "Sensor Scramble": SENSOR_SCRAMBLE,
    "Force Vision": FORCE_VISION,
    "Tech Override": TECH_OVERRIDE,
    "Droid Fabrication": DROID_FABRICATION,
    "Memory Wipe": MEMORY_WIPE,
    "Clone Army": CLONE_ARMY,
    "Hologram Transmission": HOLOGRAM_TRANSMISSION,
    "Droid Factory": DROID_FACTORY,
    "Jedi Archives": JEDI_ARCHIVES,

    # BLACK - SITH, EMPIRE, DARK SIDE
    "Darth Vader, Dark Lord": DARTH_VADER,
    "Emperor Palpatine, Sith Master": EMPEROR_PALPATINE,
    "Darth Maul, Savage Assassin": DARTH_MAUL,
    "Count Dooku, Sith Lord": COUNT_DOOKU,
    "Grand Moff Tarkin": GRAND_MOFF_TARKIN,
    "Sith Apprentice": SITH_APPRENTICE,
    "Stormtrooper": STORMTROOPER,
    "Imperial Officer": IMPERIAL_OFFICER,
    "Death Trooper": DEATH_TROOPER,
    "Imperial Inquisitor": IMPERIAL_INQUISITOR,
    "Sith Acolyte": SITH_ACOLYTE,
    "Mustafar Torturer": MUSTAFAR_TORTURER,
    "Imperial Spy": IMPERIAL_SPY,
    "TIE Fighter Pilot": TIE_FIGHTER_PILOT,
    "Force Choker": FORCE_CHOKER,
    "Shadow Guard": SHADOW_GUARD,
    "Dark Side Adept": DARK_SIDE_ADEPT,
    "Force Choke": FORCE_CHOKE,
    "Dark Side Corruption": DARK_SIDE_CORRUPTION,
    "Imperial Execution": IMPERIAL_EXECUTION,
    "Sith Lightning": SITH_LIGHTNING,
    "Fear Itself": FEAR_ITSELF,
    "Betrayal": BETRAYAL,
    "Order 66": ORDER_66,
    "Imperial Bombardment": IMPERIAL_BOMBARDMENT,
    "Harvest Despair": HARVEST_DESPAIR,
    "Conscription": CONSCRIPTION,
    "The Dark Side": THE_DARK_SIDE,
    "Galactic Empire": GALACTIC_EMPIRE,
    "Rule of Two": RULE_OF_TWO,

    # RED - BOUNTY HUNTERS, AGGRESSION, BLASTERS
    "Boba Fett, Bounty Hunter": BOBA_FETT,
    "Jango Fett, Prime Clone": JANGO_FETT,
    "Cad Bane, Ruthless Mercenary": CAD_BANE,
    "Din Djarin, The Mandalorian": DIN_DJARIN,
    "Greedo, Quick Draw": GREEDO,
    "Bounty Hunter": BOUNTY_HUNTER,
    "Trandoshan Slaver": TRANDOSHAN_SLAVER,
    "Tusken Raider": TUSKEN_RAIDER,
    "Gamorrean Guard": GAMORREAN_GUARD,
    "Podracer": PODRACER,
    "Mandalorian Warrior": MANDALORIAN_WARRIOR,
    "Mos Eisley Thug": MOS_EISLEY_THUG,
    "Separatist Battle Droid": SEPARATIST_BATTLE_DROID,
    "Clone Trooper Commando": CLONE_TROOPER_COMMANDO,
    "Weequay Pirate": WEEQUAY_PIRATE,
    "Arena Gladiator": ARENA_GLADIATOR,
    "Pyke Enforcer": PYKE_ENFORCER,
    "Blaster Bolt": BLASTER_BOLT,
    "Thermal Detonator": THERMAL_DETONATOR,
    "Aggressive Negotiations": AGGRESSIVE_NEGOTIATIONS,
    "Bounty Posted": BOUNTY_POSTED,
    "Reckless Assault": RECKLESS_ASSAULT,
    "Disintegrate": DISINTEGRATE,
    "Orbital Strike": ORBITAL_STRIKE,
    "Bounty Collection": BOUNTY_COLLECTION,
    "Rage of the Arena": RAGE_OF_THE_ARENA,
    "Hired Guns": HIRED_GUNS,
    "Hunter's Code": HUNTERS_CODE,
    "Arena Pit": ARENA_PIT,
    "Galactic Underworld": GALACTIC_UNDERWORLD,

    # GREEN - NATURE PLANETS, WOOKIEES, EWOKS
    "Chewbacca, Loyal Companion": CHEWBACCA,
    "Wicket, Ewok Chief": WICKET,
    "Tarfful, Wookiee Chieftain": TARFFUL,
    "Grogu, The Child": GROGU,
    "Wookiee Warrior": WOOKIEE_WARRIOR,
    "Ewok Ambusher": EWOK_AMBUSHER,
    "Ewok Hunter": EWOK_HUNTER,
    "Endor Trapper": ENDOR_TRAPPER,
    "Kashyyyk Defender": KASHYYYK_DEFENDER,
    "Dagobah Swamp Dweller": DAGOBAH_CREATURE,
    "Felucia Beast": FELUCIA_BEAST,
    "Jungle Rancor": JUNGLE_RANCOR,
    "Naboo Ranger": NABOO_RANGER,
    "Gungan Warrior": GUNGAN_WARRIOR,
    "Yavin Jungle Cat": YAVIN_JUNGLE_CAT,
    "Endor Wildlife": ENDOR_WILDLIFE,
    "Sarlacc Pit Spawn": SARLACC_PIT_SPAWN,
    "Wookiee Rage": WOOKIEE_RAGE,
    "Forest Ambush": FOREST_AMBUSH,
    "Ewok Trap": EWOK_TRAP,
    "Natural Camouflage": NATURAL_CAMOUFLAGE,
    "Jungle Growth": JUNGLE_GROWTH,
    "Primal Connection": PRIMAL_CONNECTION,
    "Call of the Wild": CALL_OF_THE_WILD,
    "Ewok Uprising": EWOK_UPRISING,
    "Force of Nature": FORCE_OF_NATURE,
    "Rampant Growth": RAMPANT_GROWTH,
    "Ewok Village": EWOK_VILLAGE,
    "Kashyyyk Homeland": KASHYYYK_HOMELAND,
    "The Living Force": THE_LIVING_FORCE,

    # MULTICOLOR - MAJOR CHARACTERS
    "Han Solo, Scoundrel": HAN_SOLO,
    "Anakin Skywalker, Chosen One": ANAKIN_SKYWALKER,
    "Padme Amidala, Senator": PADME_AMIDALA,
    "Ahsoka Tano, Former Padawan": AHSOKA_TANO,
    "Kylo Ren, Conflicted": KYLO_REN,
    "Rey, Scavenger": REY,
    "Finn, Defector": FINN,
    "Poe Dameron, Best Pilot": POE_DAMERON,
    "Lando Calrissian, Gambler": LANDO_CALRISSIAN,
    "General Grievous, Jedi Hunter": GENERAL_GRIEVOUS,
    "Asajj Ventress, Sith Assassin": ASAJJ_VENTRESS,
    "Jar Jar Binks, Accidental Hero": JAR_JAR_BINKS,
    "Maz Kanata, Ancient Pirate": MAZ_KANATA,
    "Grand Admiral Thrawn": THRAWN,
    "Darth Sidious, Puppetmaster": DARTH_SIDIOUS,
    "Rebel Commando Team": REBEL_COMMANDO_TEAM,
    "Separatist Commander": SEPARATIST_COMMANDER,
    "Mandalorian Forge-Master": MANDALORIAN_FORGE_MASTER,
    "Force Sensitive": FORCE_SENSITIVE,
    "Hutt Crime Lord": HUTT_CRIME_LORD,
    "Balance of the Force": BALANCE_OF_THE_FORCE,
    "Force Lightning": FORCE_LIGHTNING,
    "Unity of the Rebellion": UNITY_OF_THE_REBELLION,
    "Galactic Senate Decree": GALACTIC_SENATE_DECREE,
    "Devastation of Alderaan": DEVASTATION_OF_ALDERAAN,

    # EQUIPMENT - LIGHTSABERS
    "Luke's Lightsaber": LUKES_LIGHTSABER,
    "Darth Vader's Lightsaber": DARTH_VADERS_LIGHTSABER,
    "Double-Bladed Lightsaber": DOUBLE_BLADED_LIGHTSABER,
    "Lightsaber": LIGHTSABER,
    "Darksaber": DARK_SABER,

    # EQUIPMENT - OTHER
    "Mandalorian Armor": MANDALORIAN_ARMOR,
    "Beskar Helmet": BESKAR_HELMET,
    "Jetpack": JETPACK,
    "Blaster Rifle": BLASTER_RIFLE,
    "Bowcaster": BOWCASTER,
    "Electrostaff": ELECTROSTAFF,
    "Slave Tracker": SLAVE_TRACKER,

    # VEHICLES
    "Millennium Falcon": MILLENNIUM_FALCON,
    "X-Wing Starfighter": X_WING,
    "TIE Fighter": TIE_FIGHTER,
    "Star Destroyer": STAR_DESTROYER,
    "Slave I": SLAVE_I,
    "Speeder Bike": SPEEDER_BIKE,
    "AT-AT Walker": AT_AT,
    "AT-ST Walker": AT_ST,
    "Republic Gunship": REPUBLIC_GUNSHIP,
    "Podracer": PODRACER_VEHICLE,
    "The Razor Crest": THE_RAZOR_CREST,
    "Y-Wing Bomber": Y_WING,

    # ARTIFACTS
    "Death Star": DEATH_STAR,
    "Jedi Holocron": HOLOCRON,
    "Sith Holocron": SITH_HOLOCRON,
    "Carbonite Prison": CARBONITE_PRISON,
    "Kyber Crystal": KYBER_CRYSTAL,
    "Stormtrooper Barracks": STORMTROOPER_BARRACKS,
    "Droid Foundry": DROID_FOUNDRY,
    "Trade Federation Vault": TRADE_FEDERATION_VAULT,
    "Bacta Tank": BACTA_TANK,
    "Hyperdrive": HYPERDRIVE,
    "Shield Generator": SHIELD_GENERATOR,

    # LANDS
    "Coruscant": CORUSCANT,
    "Tatooine": TATOOINE,
    "Endor Forest": ENDOR_FOREST,
    "Kashyyyk": KASHYYYK,
    "Mustafar": MUSTAFAR,
    "Dagobah": DAGOBAH,
    "Hoth": HOTH,
    "Naboo": NABOO,
    "Kamino": KAMINO,
    "Geonosis": GEONOSIS,
    "Jakku": JAKKU,
    "Cloud City": CLOUD_CITY,
    "Mos Eisley Spaceport": MOS_EISLEY,
    "Jedi Temple": JEDI_TEMPLE,
    "Sith Temple": SITH_TEMPLE,
    "Death Star Hangar": DEATH_STAR_HANGAR,
    "Rebel Base": REBEL_BASE,

    # BASIC LANDS
    "Plains": PLAINS_SWG,
    "Island": ISLAND_SWG,
    "Swamp": SWAMP_SWG,
    "Mountain": MOUNTAIN_SWG,
    "Forest": FOREST_SWG,

    # ADDITIONAL WHITE
    "Clone Captain Rex": CLONE_CAPTAIN_REX,
    "Bail Organa": BAIL_ORGANA,
    "Mon Mothma": MON_MOTHMA,
    "Royal Guard": ROYAL_GUARD,
    "Alderaanian Refugee": ALDERAANIAN_REFUGEE,
    "Force Barrier": FORCE_BARRIER,

    # ADDITIONAL BLUE
    "BB-8, Loyal Astromech": BB8,
    "K-2SO, Reprogrammed": K2SO,
    "Super Battle Droid": SUPER_BATTLE_DROID,
    "Tactical Droid": TACTICAL_DROID,
    "Information Broker": INFORMATION_BROKER,
    "Force Illusion": FORCE_ILLUSION,

    # ADDITIONAL BLACK
    "Darth Bane, Rule Creator": DARTH_BANE,
    "Grand Inquisitor": GRAND_INQUISITOR,
    "Imperial Executioner": IMPERIAL_EXECUTIONER,
    "Snoke, Supreme Leader": SNOKE,
    "Dark Ritual of the Sith": DARK_RITUAL,

    # ADDITIONAL RED
    "Aurra Sing, Sniper": AURRA_SING,
    "Bossk, Trandoshan Hunter": BOSSK,
    "Fennec Shand, Elite Assassin": FENNEC_SHAND,
    "Death Watch Warrior": DEATH_WATCH_WARRIOR,
    "Wrist Rocket": WRIST_ROCKET,

    # ADDITIONAL GREEN
    "Yaddle, Jedi Council Member": YADDLE,
    "Wookiee Berserker": WOOKIEE_BERSERKER,
    "Ewok Shaman": EWOK_SHAMAN,
    "Rancor": RANCOR,
    "Nexu": NEXU,
    "Beast Call": BEAST_CALL,

    # ADDITIONAL MULTICOLOR
    "Captain Phasma": CAPTAIN_PHASMA,
    "Sabine Wren, Mandalorian Artist": SABINE_WREN,
    "Ezra Bridger, Street Kid": EZRA_BRIDGER,
    "Kanan Jarrus, Blinded Master": KANAN_JARRUS,
    "Hera Syndulla, Ghost Captain": HERA_SYNDULLA,

    # ADDITIONAL ARTIFACTS
    "Training Remote": TRAINING_REMOTE,
    "Restraining Bolt": RESTRAINING_BOLT,
    "Thermal Imaging Goggles": THERMAL_IMAGING_GOGGLES,

    # ADDITIONAL LANDS
    "Scarif": SCARIF,
    "Jedha": JEDHA,
    "Mandalore": MANDALORE,
    "Bespin": BESPIN,
    "Lothal": LOTHAL,
}

print(f"Loaded {len(STAR_WARS_CARDS)} Star Wars: Galactic Conflict cards")


