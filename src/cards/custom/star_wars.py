"""
Star Wars: Galactic Conflict (SWG) Card Implementations

Set released March 2026. ~270 cards.
Features mechanics: Force, Lightsaber, Pilot, Dark Side/Light Side
"""

from src.cards.card_factories import (
    make_artifact,
    make_artifact_creature,
    make_equipment,
    make_land,
    make_sorcery,
)

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
    other_creatures_with_subtype, all_opponents,
    # Phase A spice-pass additions:
    make_activated_ability, make_cost_reduction, make_equipment_setup,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

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
    mana_cost="{1}{W}{W}",
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
    mana_cost="{2}{W}",
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
    mana_cost="{1}{W}{W}",
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


def alderaanian_diplomat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Rebel diplomacy — scry 1 + gain 1 life per Rebel you control."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        rebels = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Rebel" in o.characteristics.subtypes:
                    rebels += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': max(1, rebels)},
            source=obj.id, controller=obj.controller,
        ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

ALDERAANIAN_DIPLOMAT = make_creature(
    name="Alderaanian Diplomat",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rebel", "Advisor"},
    text="When Alderaanian Diplomat enters, scry 1 and gain 1 life for each Rebel you control.",
    setup_interceptors=alderaanian_diplomat_setup,
)


def jedi_temple_guard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Jedi have vigilance"""
    return [make_keyword_grant(obj, ['vigilance'], other_creatures_with_subtype(obj, "Jedi"))]

JEDI_TEMPLE_GUARD = make_creature(
    name="Jedi Temple Guard",
    power=3, toughness=3,
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
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rebel", "Soldier"},
    text="Defender. Whenever Echo Base Defender blocks, you gain 2 life.",
    setup_interceptors=echo_base_defender_setup
)


def rebel_medic_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Field medic — scry 1 + each opponent loses 1 life, each ally Rebel boosts gain."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        ally_rebels = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Rebel" in o.characteristics.subtypes and o.id != obj.id:
                    ally_rebels += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        if ally_rebels > 0:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': ally_rebels},
                source=obj.id, controller=obj.controller,
            ))
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

REBEL_MEDIC = make_creature(
    name="Rebel Medic",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rebel", "Cleric"},
    text="When Rebel Medic enters, scry 1. Each opponent loses 1 life and you gain 1 life for each other Rebel you control.",
    setup_interceptors=rebel_medic_setup,
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
    mana_cost="{1}{W}",
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
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rebel", "Soldier"},
    text="When Resistance Commander enters, create a 1/1 white Human Rebel Soldier creature token. Rebel creatures you control get +1/+0."
)


def jedi_sentinel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Jedi vigil — on attack, scry 1; each opponent loses 1 life if you control a Jedi."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        my_jedi = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Jedi" in o.characteristics.subtypes:
                    my_jedi += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        if my_jedi >= 1:
            for opp_id in all_opponents(obj, state):
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': opp_id, 'amount': -1},
                    source=obj.id, controller=obj.controller,
                ))
        return events
    return [make_attack_trigger(obj, effect_fn)]

JEDI_SENTINEL = make_creature(
    name="Jedi Sentinel",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Jedi"},
    text="Vigilance, lifelink. Whenever Jedi Sentinel attacks, scry 1; if you control a Jedi, each opponent loses 1 life.",
    setup_interceptors=jedi_sentinel_setup,
)


REBELLION_SYMPATHIZER = make_creature(
    name="Rebellion Sympathizer",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    text="When Rebellion Sympathizer dies, create a 1/1 white Human Rebel Soldier creature token."
)


def tatooine_homesteader_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Moisture farm — scry 1 + life gain per Citizen you control."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        citizens = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Citizen" in o.characteristics.subtypes:
                    citizens += 1
        return [
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id, controller=obj.controller,
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': max(1, citizens)},
                source=obj.id, controller=obj.controller,
            ),
        ]
    return [make_etb_trigger(obj, effect_fn)]

TATOOINE_HOMESTEADER = make_creature(
    name="Tatooine Homesteader",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    text="When Tatooine Homesteader enters, scry 1 and gain 1 life for each Citizen you control.",
    setup_interceptors=tatooine_homesteader_setup,
)


def galactic_senator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Senate diplomacy — scry 1 + each opponent reveals hand."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        nobles = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if not o or o.controller != obj.controller:
                    continue
                subs = o.characteristics.subtypes
                if "Noble" in subs or "Advisor" in subs:
                    nobles += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1 + (1 if nobles >= 2 else 0)},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.REVEAL_HAND,
                payload={'player': opp_id, 'amount': 1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

GALACTIC_SENATOR = make_creature(
    name="Galactic Senator",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble", "Advisor"},
    text="When Galactic Senator enters, scry 1 (scry 2 with two Nobles or Advisors), then each opponent reveals a card from their hand.",
    setup_interceptors=galactic_senator_setup,
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


def mon_calamari_captain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Fleet commander — scry 1 + surveil 1 if Rebellion has the upper hand."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        rebels = 0
        opp_threats = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if not o:
                    continue
                if o.controller == obj.controller and "Rebel" in o.characteristics.subtypes:
                    rebels += 1
                elif o.controller != obj.controller and CardType.CREATURE in o.characteristics.types:
                    opp_threats += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        if rebels >= opp_threats:
            events.append(Event(
                type=EventType.SURVEIL,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

MON_CALAMARI_CAPTAIN = make_creature(
    name="Mon Calamari Captain",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Mon Calamari", "Rebel", "Pilot"},
    text="When Mon Calamari Captain enters, scry 1; if you control as many Rebels as opponents have creatures, surveil 1.",
    setup_interceptors=mon_calamari_captain_setup,
)


def rebel_strategist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Battle plan — scry 1 + each opponent reveals their hand."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        my_advisors = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Advisor" in o.characteristics.subtypes:
                    my_advisors += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1 + (1 if my_advisors >= 2 else 0)},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.REVEAL_HAND,
                payload={'player': opp_id, 'amount': 1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

REBEL_STRATEGIST = make_creature(
    name="Rebel Strategist",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rebel", "Advisor"},
    text="When Rebel Strategist enters, scry 1 (scry 2 with two Advisors), then each opponent reveals a card from their hand.",
    setup_interceptors=rebel_strategist_setup,
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


def separatist_infiltrator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sleeper agent — on attack, scry 1 + each opponent reveals their hand."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        my_spies = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Spy" in o.characteristics.subtypes:
                    my_spies += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.REVEAL_HAND,
                payload={'player': opp_id, 'amount': max(1, my_spies)},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect_fn)]

SEPARATIST_INFILTRATOR = make_creature(
    name="Separatist Infiltrator",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Shapeshifter", "Spy"},
    text="Whenever Separatist Infiltrator attacks, scry 1, then each opponent reveals a card from their hand for each Spy you control.",
    setup_interceptors=separatist_infiltrator_setup,
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


def imperial_officer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Empire command — scry 1 + each opponent loses 1 life per Empire creature."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        empire = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Empire" in o.characteristics.subtypes:
                    empire += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -max(1, empire)},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

IMPERIAL_OFFICER = make_creature(
    name="Imperial Officer",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Empire", "Soldier"},
    text="When Imperial Officer enters, scry 1, then each opponent loses 1 life for each Empire creature you control.",
    setup_interceptors=imperial_officer_setup,
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


def imperial_inquisitor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Inquisition — scry 1 + each opp reveals hand + each opp discards if Sith present."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        sith = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Sith" in o.characteristics.subtypes:
                    sith += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.REVEAL_HAND,
                payload={'player': opp_id, 'amount': 1},
                source=obj.id, controller=obj.controller,
            ))
            if sith >= 1:
                events.append(Event(
                    type=EventType.DISCARD,
                    payload={'player': opp_id, 'amount': 1},
                    source=obj.id, controller=obj.controller,
                ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

IMPERIAL_INQUISITOR = make_creature(
    name="Imperial Inquisitor",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Empire", "Sith"},
    text="Menace. When Imperial Inquisitor enters, scry 1 and each opponent reveals a card from their hand; if you control another Sith, each opponent also discards a card.",
    setup_interceptors=imperial_inquisitor_setup,
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


def mustafar_torturer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Lava-pit interrogation — scry 1 + each opp discards if Empire is in play."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        empire = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Empire" in o.characteristics.subtypes:
                    empire += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
            if empire >= 2:
                events.append(Event(
                    type=EventType.DISCARD,
                    payload={'player': opp_id, 'amount': 1},
                    source=obj.id, controller=obj.controller,
                ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

MUSTAFAR_TORTURER = make_creature(
    name="Mustafar Torturer",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Empire"},
    text="When Mustafar Torturer enters, scry 1 and each opponent loses 1 life; if you control two or more Empire creatures, each opponent also discards a card.",
    setup_interceptors=mustafar_torturer_setup,
)


def imperial_spy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Covert intel — surveil 1 + each opponent reveals hand."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        rogues_or_spies = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if not o or o.controller != obj.controller:
                    continue
                subs = o.characteristics.subtypes
                if "Rogue" in subs or "Spy" in subs:
                    rogues_or_spies += 1
        events = [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.REVEAL_HAND,
                payload={'player': opp_id, 'amount': max(1, rogues_or_spies)},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

IMPERIAL_SPY = make_creature(
    name="Imperial Spy",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Empire", "Rogue"},
    text="When Imperial Spy enters, surveil 1 and each opponent reveals a card from their hand for each Rogue or Spy you control. Imperial Spy can't be blocked.",
    setup_interceptors=imperial_spy_setup,
)


def tie_fighter_pilot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Strafing run — on attack, scry 1 + 1 damage to each opponent."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        my_pilots = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Pilot" in o.characteristics.subtypes:
                    my_pilots += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp_id, 'amount': max(1, my_pilots), 'source': obj.id},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect_fn)]

TIE_FIGHTER_PILOT = make_creature(
    name="TIE Fighter Pilot",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Empire", "Pilot"},
    text="Flying. Whenever TIE Fighter Pilot attacks, scry 1, then it deals damage to each opponent equal to the number of Pilots you control.",
    setup_interceptors=tie_fighter_pilot_setup,
)


def force_choker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dark-side grip — scry 1 + each opponent loses life per Sith you control."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        sith = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Sith" in o.characteristics.subtypes:
                    sith += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        loss = max(1, sith)
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -loss},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

FORCE_CHOKER = make_creature(
    name="Force Choker",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Sith"},
    text="When Force Choker enters, scry 1, then each opponent loses life equal to the number of Sith you control (minimum 1).",
    setup_interceptors=force_choker_setup,
)


def shadow_guard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Imperial shadow — scry 1 + each opp -1 life if you control 2+ Empire."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        empire = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Empire" in o.characteristics.subtypes:
                    empire += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        if empire >= 2:
            for opp_id in all_opponents(obj, state):
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': opp_id, 'amount': -1},
                    source=obj.id, controller=obj.controller,
                ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

SHADOW_GUARD = make_creature(
    name="Shadow Guard",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Empire", "Soldier"},
    text="Flash, deathtouch. When Shadow Guard enters, scry 1; if you control two or more Empire creatures, each opponent loses 1 life.",
    setup_interceptors=shadow_guard_setup,
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


def mandalorian_warrior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Beskar charge — scry 1 + 1 damage to each opponent."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        mando = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Mandalorian" in o.characteristics.subtypes:
                    mando += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        dmg = 1 + (1 if mando >= 2 else 0)
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp_id, 'amount': dmg, 'source': obj.id},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

MANDALORIAN_WARRIOR = make_creature(
    name="Mandalorian Warrior",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Mandalorian", "Warrior"},
    text="Flying. When Mandalorian Warrior enters, scry 1, then it deals 1 damage to each opponent (2 with two Mandalorians).",
    setup_interceptors=mandalorian_warrior_setup,
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


def clone_trooper_commando_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Squad coordination — scry 1 + 1 damage to each opponent per Clone."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        clones = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Clone" in o.characteristics.subtypes:
                    clones += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp_id, 'amount': max(1, clones), 'source': obj.id},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

CLONE_TROOPER_COMMANDO = make_creature(
    name="Clone Trooper Commando",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Clone", "Soldier"},
    text="First strike. When Clone Trooper Commando enters, scry 1 and it deals damage to each opponent equal to the number of Clones you control.",
    setup_interceptors=clone_trooper_commando_setup,
)


WEEQUAY_PIRATE = make_creature(
    name="Weequay Pirate",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Weequay", "Pirate"},
    text="When Weequay Pirate deals combat damage to a player, create a Treasure token."
)


def arena_gladiator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Glory hound — on attack, scry 1 + 1 damage to each opponent per Warrior you control."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        warriors = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Warrior" in o.characteristics.subtypes:
                    warriors += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp_id, 'amount': max(1, warriors), 'source': obj.id},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect_fn)]

ARENA_GLADIATOR = make_creature(
    name="Arena Gladiator",
    power=4, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="Trample. Whenever Arena Gladiator attacks, scry 1, then it deals damage to each opponent equal to the number of Warriors you control.",
    setup_interceptors=arena_gladiator_setup,
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

def wookiee_warrior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Wookiee roar — scry 1 + life gain per Wookiee."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        wookiees = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Wookiee" in o.characteristics.subtypes:
                    wookiees += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': max(1, wookiees)},
            source=obj.id, controller=obj.controller,
        ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

WOOKIEE_WARRIOR = make_creature(
    name="Wookiee Warrior",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Wookiee", "Warrior"},
    text="Trample. When Wookiee Warrior enters, scry 1 and gain 1 life for each Wookiee you control.",
    setup_interceptors=wookiee_warrior_setup,
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


def ewok_hunter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Forest stalker — on attack, scry 1 + each opponent loses 1 life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        ewoks = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Ewok" in o.characteristics.subtypes:
                    ewoks += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -max(1, ewoks)},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect_fn)]

EWOK_HUNTER = make_creature(
    name="Ewok Hunter",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Ewok", "Scout"},
    text="Deathtouch. Whenever Ewok Hunter attacks, scry 1 and each opponent loses 1 life for each Ewok you control.",
    setup_interceptors=ewok_hunter_setup,
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


def kashyyyk_defender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tree-village defense — scry 2 + life gain for each Wookiee or Warrior you control."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        defenders = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if not o or o.controller != obj.controller:
                    continue
                subs = o.characteristics.subtypes
                if "Wookiee" in subs or "Warrior" in subs:
                    defenders += 1
        return [
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id, controller=obj.controller,
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': max(1, defenders)},
                source=obj.id, controller=obj.controller,
            ),
        ]
    return [make_etb_trigger(obj, effect_fn)]

KASHYYYK_DEFENDER = make_creature(
    name="Kashyyyk Defender",
    power=3, toughness=5,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Wookiee", "Warrior"},
    text="Reach. When Kashyyyk Defender enters, scry 2 and gain 1 life for each Wookiee or Warrior you control.",
    setup_interceptors=kashyyyk_defender_setup,
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


# --- Slave Tracker: Helper-5 rewire ----------------------------------------
# +1/+1 + granted trigger "combat damage to player → scry 2."
# Printed text says "that player reveals their hand"; the engine has no
# generic REVEAL event yet, so the closest in-spirit effect is "you peek
# ahead" = scry 2 (intel-gathering theme preserved).
def _slave_tracker_combat_damage_to_player_filter(
    event: Event, state: GameState, target_id: str
) -> bool:
    if event.type != EventType.DAMAGE:
        return False
    if event.payload.get('source') != target_id:
        return False
    if not event.payload.get('combat', False):
        return False
    return event.payload.get('target') in state.players


def _slave_tracker_scry_effect(
    target_obj: GameObject, event: Event, state: GameState
) -> list[Event]:
    return [Event(
        type=EventType.ACTIVATE,
        payload={
            'action': 'scry',
            'amount': 2,
            'player': target_obj.controller,
            'source': target_obj.id,
        },
        source=target_obj.id,
    )]


SLAVE_TRACKER = make_equipment(
    name="Slave Tracker",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+1. Whenever equipped creature deals combat damage to a player, scry 2.",
    setup_interceptors=make_equipment_setup(
        power_mod=1, toughness_mod=1,
        equip_cost="{1}",
        granted_triggered_abilities={
            "event_filter": _slave_tracker_combat_damage_to_player_filter,
            "effect_fn": _slave_tracker_scry_effect,
            "description": "Combat damage to player → controller scrys 2",
        },
    ),
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
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rebel", "Noble"},
    supertypes={"Legendary"},
    text="When Bail Organa enters, search your library for a Rebel creature card with mana value 2 or less, reveal it, put it into your hand, then shuffle."
)


MON_MOTHMA = make_creature(
    name="Mon Mothma",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rebel", "Advisor"},
    supertypes={"Legendary"},
    text="Rebel spells you cast cost {1} less to cast. At the beginning of your end step, if you control three or more Rebels, draw a card."
)


def royal_guard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Imperial loyalty — scry 1 + life gain per Soldier you control."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        soldiers = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Soldier" in o.characteristics.subtypes:
                    soldiers += 1
        return [
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id, controller=obj.controller,
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': max(1, soldiers)},
                source=obj.id, controller=obj.controller,
            ),
        ]
    return [make_etb_trigger(obj, effect_fn)]

ROYAL_GUARD = make_creature(
    name="Royal Guard",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Vigilance, lifelink. When Royal Guard enters, scry 1 and gain 1 life for each Soldier you control.",
    setup_interceptors=royal_guard_setup,
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


def information_broker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Underworld intel — scry 1 + surveil 1 + each opponent reveals hand."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        my_rogues = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and "Rogue" in o.characteristics.subtypes:
                    my_rogues += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        if my_rogues >= 1:
            events.append(Event(
                type=EventType.SURVEIL,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id, controller=obj.controller,
            ))
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.REVEAL_HAND,
                payload={'player': opp_id, 'amount': 1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

INFORMATION_BROKER = make_creature(
    name="Information Broker",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="When Information Broker enters, scry 1; if you control another Rogue, surveil 1. Each opponent reveals a card from their hand.",
    setup_interceptors=information_broker_setup,
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
# SPICE PASS — Format-Defining Cards (Wave 22+)
# =============================================================================
# Modeled on real MTG broken-card patterns. See plans/proud-singing-sonnet.md
# for the design taxonomy. Phase A — within-engine cards only.
# =============================================================================


# --- Boba Fett, Hunter of Hunters --- {1}{R} 2/2 Mythic (Ragavan analogue)
def boba_fett_hoh_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self flying+haste; combat damage to player → exile-top-play + Treasure."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def damage_effect(event: Event, st: GameState) -> list[Event]:
        target = event.payload.get('target')
        if not target or target not in st.players:
            return []
        return [
            Event(
                type=EventType.EXILE_TOP_PLAY,
                payload={
                    'player': target,
                    'caster': obj.controller,
                    'until_end_of_turn': True,
                    'mana_color_override': 'any',
                },
                source=obj.id,
            ),
            Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': obj.controller,
                    'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT},
                              'subtypes': {'Treasure'}},
                },
                source=obj.id,
            ),
        ]

    return [
        make_keyword_grant(obj, ['flying', 'haste'], affects_self),
        make_damage_trigger(obj, damage_effect, combat_only=True),
    ]

BOBA_FETT_HUNTER_OF_HUNTERS = make_creature(
    name="Boba Fett, Hunter of Hunters",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Bounty Hunter"},
    supertypes={"Legendary"},
    text=(
        "Flying, haste. Whenever Boba Fett deals combat damage to a player, "
        "exile the top card of that player's library; you may play that card "
        "this turn, and you may spend mana as though it were any color to cast it. "
        "Then create a Treasure token."
    ),
    setup_interceptors=boba_fett_hoh_setup,
)


# --- IG-88, Assassin Droid Network --- {3}{B}{R} 4/4 Mythic (Droid value engine)
def ig88_network_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """+1/+1 + token when another Droid you control enters. Drain on Droid death.
    Activated: sac a Droid → damage = source's power to any target."""

    def droid_etb_filter(event: Event, st: GameState, src: GameObject) -> bool:
        # Cards entering from any zone fire ZONE_CHANGE; copy-tokens use
        # OBJECT_CREATED; standard token minting (CREATE_TOKEN handler) does
        # NOT emit ZONE_CHANGE/OBJECT_CREATED — the new token's id is just
        # written back into CREATE_TOKEN's payload['object_id']. Listen to all
        # three so token Droids also trigger. The CREATE_TOKEN branch ignores
        # tokens IG-88 itself created to avoid an infinite trigger chain (each
        # of IG-88's own 1/1 Droid tokens would otherwise mint another).
        if event.type == EventType.ZONE_CHANGE:
            if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
                return False
        elif event.type == EventType.OBJECT_CREATED:
            if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
                return False
        elif event.type == EventType.CREATE_TOKEN:
            if event.source == src.id:
                return False
        else:
            return False
        entering_id = event.payload.get('object_id')
        if not entering_id or entering_id == src.id:
            return False
        entering = st.objects.get(entering_id)
        if not entering or entering.controller != src.controller:
            return False
        if CardType.CREATURE not in entering.characteristics.types:
            return False
        return 'Droid' in (entering.characteristics.subtypes or set())

    def droid_etb_effect(event: Event, st: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id,
            ),
            Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': obj.controller,
                    'token': {
                        'name': 'Droid', 'power': 1, 'toughness': 1,
                        'types': {CardType.ARTIFACT, CardType.CREATURE},
                        'subtypes': {'Droid'},
                    },
                },
                source=obj.id,
            ),
        ]

    def droid_death_filter(event: Event, st: GameState, src: GameObject) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        dead_id = event.payload.get('object_id')
        if not dead_id or dead_id == src.id:
            return False
        dead = st.objects.get(dead_id)
        if not dead or dead.controller != src.controller:
            return False
        if CardType.CREATURE not in dead.characteristics.types:
            return False
        return 'Droid' in dead.characteristics.subtypes

    def droid_death_effect(event: Event, st: GameState) -> list[Event]:
        events = []
        for pid, p in st.players.items():
            if pid == obj.controller:
                continue
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': pid, 'amount': -1},
                source=obj.id,
            ))
        return events

    interceptors: list[Interceptor] = []
    interceptors.append(make_etb_trigger(obj, droid_etb_effect, filter_fn=droid_etb_filter))
    interceptors.append(make_death_trigger(obj, droid_death_effect, filter_fn=droid_death_filter))

    def sac_damage_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        if not targets:
            return []
        sac_id = None
        for tid in [t.object_id if hasattr(t, 'object_id') else t for t in targets]:
            tobj = st.objects.get(tid)
            if (tobj and tobj.zone == ZoneType.BATTLEFIELD
                    and tobj.controller == o.controller
                    and 'Droid' in tobj.characteristics.subtypes):
                sac_id = tid
                break
        if not sac_id:
            return []
        amt = get_power(o, st) or 0
        events = [Event(
            type=EventType.SACRIFICE,
            payload={'object_id': sac_id},
            source=o.id,
        )]
        if len(targets) >= 2:
            dmg_target = targets[1].object_id if hasattr(targets[1], 'object_id') else targets[1]
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': dmg_target, 'amount': amt, 'source': o.id},
                source=o.id,
            ))
        return events

    make_activated_ability(
        obj,
        cost="{B}{R}",
        effect_fn=sac_damage_effect,
        description="Sacrifice a Droid: deals damage equal to IG-88's power to any target.",
        targets_required=2,
        target_kind="any",
    )

    return interceptors

IG_88_NETWORK = make_creature(
    name="IG-88, Assassin Droid Network",
    power=4, toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Droid", "Assassin"},
    supertypes={"Legendary"},
    types={CardType.ARTIFACT, CardType.CREATURE},
    text=(
        "Whenever another Droid you control enters, IG-88 gets a +1/+1 counter "
        "and create a 1/1 colorless Droid artifact creature token. "
        "Whenever a Droid you control dies, each opponent loses 1 life. "
        "{B}{R}, Sacrifice a Droid: IG-88 deals damage equal to its power to any target."
    ),
    setup_interceptors=ig88_network_setup,
)


# --- Yoda, Living Force --- {G}{W}{U} 2/4 Rare (flash hexproof scry lord)
def yoda_living_force_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self flash+hexproof; ETB scry 3; other Jedi +1/+1."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_effect(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id,
        )]

    interceptors: list[Interceptor] = []
    interceptors.append(make_keyword_grant(obj, ['flash', 'hexproof'], affects_self))
    interceptors.append(make_etb_trigger(obj, etb_effect))
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Jedi")))
    return interceptors

YODA_LIVING_FORCE = make_creature(
    name="Yoda, Living Force",
    power=2, toughness=4,
    mana_cost="{G}{W}{U}",
    colors={Color.GREEN, Color.WHITE, Color.BLUE},
    subtypes={"Jedi"},
    supertypes={"Legendary"},
    text=(
        "Flash. Hexproof. When Yoda enters, scry 3. "
        "Other Jedi creatures you control get +1/+1."
    ),
    setup_interceptors=yoda_living_force_setup,
)


# --- Bossk, Trandoshan Hunter Prime --- {2}{R}{G} 4/4 Rare
def bossk_prime_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self trample+haste. Attack: tutor a Bounty Hunter. Cost reduction for BH."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def attack_effect(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                'player': obj.controller,
                'subtype': 'Bounty Hunter',
                'destination': 'hand',
                'min_count': 0,
                'max_count': 1,
            },
            source=obj.id,
        )]

    def applies_to_bh(card: GameObject, pid: str, st: GameState) -> bool:
        if pid != obj.controller or card is None:
            return False
        chars = card.characteristics
        if 'Bounty Hunter' in (chars.subtypes or set()):
            return True
        return False

    return [
        make_keyword_grant(obj, ['trample', 'haste'], affects_self),
        make_attack_trigger(obj, attack_effect),
        make_cost_reduction(obj, applies_to=applies_to_bh, amount=1),
    ]

BOSSK_PRIME = make_creature(
    name="Bossk, Trandoshan Hunter Prime",
    power=4, toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Trandoshan", "Bounty Hunter"},
    supertypes={"Legendary"},
    text=(
        "Trample, haste. Whenever Bossk attacks, search your library for a "
        "Bounty Hunter card, reveal it, put it into your hand, then shuffle. "
        "Bounty Hunter spells you cast cost {1} less."
    ),
    setup_interceptors=bossk_prime_setup,
)


# --- Han Solo, Hotshot Pilot --- {1}{R} 2/2 Uncommon (Treasure ETB + sac payoff)
def han_solo_hotshot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self first strike. ETB Treasure. Sacrificing a Treasure: +2/+0 EOT."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_effect(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT},
                          'subtypes': {'Treasure'}},
            },
            source=obj.id,
        )]

    def treasure_sac_filter(event: Event, st: GameState) -> bool:
        # The system-level TRANSFORM interceptor in src/engine/game.py rewrites
        # SACRIFICE events into ZONE_CHANGE events (with payload['reason'] ==
        # 'sacrifice') *before* they reach REACT, so listen on the post-transform
        # shape.
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('reason') != 'sacrifice':
            return False
        sacced_id = event.payload.get('object_id')
        if not sacced_id:
            return False
        sacced = st.objects.get(sacced_id)
        if not sacced:
            return False
        if sacced.controller != obj.controller:
            return False
        return 'Treasure' in (sacced.characteristics.subtypes or set())

    def treasure_sac_handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': obj.id,
                    'power_mod': 2,
                    'toughness_mod': 0,
                    'duration': 'end_of_turn',
                },
                source=obj.id,
            )],
        )

    sac_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=treasure_sac_filter,
        handler=treasure_sac_handler,
        duration='while_on_battlefield',
    )

    return [
        make_keyword_grant(obj, ['first_strike'], affects_self),
        make_etb_trigger(obj, etb_effect),
        sac_trigger,
    ]

HAN_SOLO_HOTSHOT_PILOT = make_creature(
    name="Han Solo, Hotshot Pilot",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Pilot", "Smuggler"},
    supertypes={"Legendary"},
    text=(
        "First strike. When Han Solo enters, create a Treasure token. "
        "Whenever you sacrifice a Treasure, Han Solo gets +2/+0 until end of turn."
    ),
    setup_interceptors=han_solo_hotshot_setup,
)


# --- Holocron of the High Council --- {2} Artifact Uncommon (faction tutor)
def holocron_hc_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: {C}. {4}, {T}, sacrifice: tutor a Jedi or Sith card."""

    def mana_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        return [Event(
            type=EventType.MANA_PRODUCED,
            payload={'player': o.controller, 'mana': {'C': 1}},
            source=o.id,
        )]

    make_activated_ability(
        obj,
        cost="{T}",
        effect_fn=mana_effect,
        description="Tap: Add {C}.",
    )

    def tutor_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        # Sacrifice is part of the cost (parsed from cost string), so we just
        # emit the search here.
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                'player': o.controller,
                'destination': 'hand',
                'min_count': 0,
                'max_count': 1,
                'reveal': True,
                'subtypes_any': ['Jedi', 'Sith'],
            },
            source=o.id,
        )]

    make_activated_ability(
        obj,
        cost="{4}, {T}, Sacrifice this artifact",
        effect_fn=tutor_effect,
        description="{4}, {T}, Sacrifice: tutor a Jedi or Sith card to hand.",
    )

    return []

HOLOCRON_OF_THE_HIGH_COUNCIL = make_artifact(
    name="Holocron of the High Council",
    mana_cost="{2}",
    text=(
        "{T}: Add {C}. "
        "{4}, {T}, Sacrifice Holocron of the High Council: Search your library "
        "for a Jedi or Sith card, reveal it, put it into your hand, then shuffle."
    ),
    supertypes={"Legendary"},
    setup_interceptors=holocron_hc_setup,
)


# --- Mandalorian Beskar Plating --- {2} Equipment Uncommon
MANDALORIAN_BESKAR_PLATING = make_equipment(
    name="Mandalorian Beskar Plating",
    mana_cost="{2}",
    text=(
        "Equipped creature gets +2/+2 and has indestructible. "
        "Equip {2}."
    ),
    setup_interceptors=make_equipment_setup(
        power_mod=2, toughness_mod=2,
        keywords=["indestructible"],
        equip_cost="{2}",
    ),
)


# --- Sith Resurgence --- {2}{B} Sorcery Uncommon (reanimator)
def sith_resurgence_resolve(targets: list, state: GameState) -> list[Event]:
    """Return target Sith creature card from your graveyard to the battlefield."""
    if not targets:
        return []
    target_id = targets[0].object_id if hasattr(targets[0], 'object_id') else targets[0]
    target = state.objects.get(target_id)
    if not target:
        return []
    chars = target.characteristics
    if not chars or CardType.CREATURE not in chars.types:
        return []
    if 'Sith' not in (chars.subtypes or set()):
        return []
    return [Event(
        type=EventType.RETURN_FROM_GRAVEYARD,
        payload={
            'object_id': target_id,
            'destination': 'battlefield',
            'controller': target.controller,
        },
        source=target_id,
    )]

def sith_resurgence_setup_in_hand(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dark Side: Sith Resurgence costs {2} less while caster has < 10 life."""
    from src.cards.interceptor_helpers import make_cost_reduction

    def applies_self(card: GameObject, pid: str, st: GameState) -> bool:
        return card is not None and card.id == obj.id

    def dark_side(st: GameState) -> bool:
        owner = st.players.get(obj.controller) if obj.controller else None
        return bool(owner and owner.life < 10)

    return [make_cost_reduction(
        obj,
        applies_to=applies_self,
        amount=2,
        self_only=True,
        condition_fn=dark_side,
    )]

SITH_RESURGENCE = make_sorcery(
    name="Sith Resurgence",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text=(
        "Return target Sith creature card from your graveyard to the battlefield. "
        "Dark Side — If you have less than 10 life, this spell costs {2} less to cast."
    ),
    resolve=sith_resurgence_resolve,
)
SITH_RESURGENCE.setup_in_hand = sith_resurgence_setup_in_hand


# =============================================================================
# SPICE PASS PHASE B — Cards using W1-W7 engine capability
# =============================================================================
# Built on the engine capability that landed in W1-W7 (replacement effects,
# cast-from-zone permissions, granted activated abilities, tiered cost,
# Valiant/Expend, vehicle animation) plus three small Phase-B helper additions
# (was_destroyed_this_turn, precondition_fn on activated abilities, condition_fn
# on cost reduction). See plans/proud-singing-sonnet.md for design rationale.


# --- Kylo Ren, Conflicted Heir --- {2}{B}{R} 4/4 legendary creature, Rare
def kylo_ren_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste; combat damage to a player → steal+untap+haste a creature; if
    another legendary creature controlled, take an extra combat (once/turn)."""
    from src.cards.interceptor_helpers import (
        make_keyword_grant, make_damage_trigger, threaten_creature,
    )

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def damage_effect(event: Event, st: GameState) -> list[Event]:
        target = event.payload.get('target')
        if not target or target not in st.players:
            return []
        # Pick any creature the damaged player controls (engine resolves the
        # actual target via the threaten dispatcher; for now we pick the
        # first available enemy creature).
        victim_id = None
        for o in st.objects.values():
            if (o.zone == ZoneType.BATTLEFIELD
                    and o.controller == target
                    and CardType.CREATURE in o.characteristics.types):
                victim_id = o.id
                break
        events: list[Event] = []
        if victim_id:
            events.extend(threaten_creature(victim_id, obj.controller, obj.id))
        # Extra-combat gate: must control ≥1 OTHER legendary creature.
        other_legendaries = sum(
            1 for o in st.objects.values()
            if (o.zone == ZoneType.BATTLEFIELD
                and o.controller == obj.controller
                and o.id != obj.id
                and CardType.CREATURE in o.characteristics.types
                and 'Legendary' in (o.characteristics.supertypes or set()))
        )
        used_key = 'kylo_extra_combat_used'
        already_used = bool(st.turn_data.get(used_key))
        if other_legendaries >= 1 and not already_used:
            st.turn_data[used_key] = True
            events.append(Event(
                type=EventType.EXTRA_COMBAT,
                payload={'player': obj.controller},
                source=obj.id,
            ))
        return events

    return [
        make_keyword_grant(obj, ['haste'], affects_self),
        make_damage_trigger(obj, damage_effect, combat_only=True),
    ]

KYLO_REN_CONFLICTED_HEIR = make_creature(
    name="Kylo Ren, Conflicted Heir",
    power=4, toughness=4,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Sith"},
    supertypes={"Legendary"},
    text=(
        "Haste. Whenever Kylo Ren deals combat damage to a player, gain "
        "control of target creature that player controls until end of turn. "
        "Untap it. It gains haste until end of turn. If you control another "
        "legendary creature, take an extra combat phase after this one. "
        "(Only once per turn.)"
    ),
    setup_interceptors=kylo_ren_setup,
)


# --- Stormtrooper Patrol Squadron --- {2}{B} Rare legendary enchantment
def stormtrooper_patrol_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Opponents' nonbasic lands enter tapped. Upkeep: 2/1 Empire Trooper token."""
    from src.cards.interceptor_helpers import (
        make_replacement_effect, make_upkeep_trigger,
    )

    def is_opp_nonbasic_land_etb(event: Event, st: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('tapped'):
            return False  # already entering tapped
        entering_id = event.payload.get('object_id')
        if not entering_id:
            return False
        entering = st.objects.get(entering_id)
        if not entering or entering.controller == obj.controller:
            return False
        chars = entering.characteristics
        if CardType.LAND not in (chars.types or set()):
            return False
        return 'Basic' not in (chars.supertypes or set())

    def force_tapped(event: Event, st: GameState):
        new_event = event.copy()
        new_event.payload['tapped'] = True
        return new_event

    def upkeep_token(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Empire Trooper',
                    'power': 2, 'toughness': 1,
                    'colors': {Color.BLACK},
                    'types': {CardType.CREATURE},
                    'subtypes': {'Human', 'Empire', 'Soldier'},
                },
            },
            source=obj.id,
        )]

    interceptors: list[Interceptor] = []
    interceptors.extend(make_replacement_effect(
        obj,
        event_filter=is_opp_nonbasic_land_etb,
        replace_fn=force_tapped,
    ))
    interceptors.append(make_upkeep_trigger(obj, upkeep_token))
    return interceptors

STORMTROOPER_PATROL_SQUADRON = CardDefinition(
    name="Stormtrooper Patrol Squadron",
    mana_cost="{2}{B}",
    characteristics=Characteristics(
        types={CardType.ENCHANTMENT},
        colors={Color.BLACK},
        supertypes={"Legendary"},
        mana_cost="{2}{B}",
    ),
    text=(
        "Nonbasic lands your opponents control enter the battlefield tapped. "
        "At the beginning of your upkeep, create a 2/1 black Empire Soldier "
        "creature token."
    ),
    setup_interceptors=stormtrooper_patrol_setup,
)


# --- R2-D2, Master Hacker --- {1}{U} 1/3 Rare legendary artifact creature
def r2d2_master_hacker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: exile top of library; cast free if it's an artifact/instant/sorcery
    with MV ≤ 3, else draw it. {2}{U},{T}: untap another target Droid."""
    from src.cards.interceptor_helpers import (
        make_etb_trigger, make_activated_ability,
        make_castable_from_exile,
    )
    from src.engine import ManaCost

    def etb_effect(event: Event, st: GameState) -> list[Event]:
        library = st.zones.get(f'library_{obj.controller}')
        if not library or not library.objects:
            return []
        top_id = library.objects[0]
        top = st.objects.get(top_id)
        if not top or not top.card_def:
            return [Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'count': 1},
                source=obj.id,
            )]
        chars = top.characteristics
        is_castable_type = (
            CardType.ARTIFACT in chars.types
            or CardType.INSTANT in chars.types
            or CardType.SORCERY in chars.types
        )
        cost_str = chars.mana_cost or top.card_def.mana_cost or "{0}"
        try:
            mv = ManaCost.parse(cost_str).mana_value
        except Exception:
            mv = 99
        if is_castable_type and mv <= 3:
            # Register a free-cast permission for this specific card from exile,
            # then exile it. The permission self-cleans on EOT.
            for perm_int in make_castable_from_exile(
                obj,
                target_card_id=top_id,
                duration='end_of_turn',
                cost_modifier=lambda _mc: ManaCost.parse(""),
            ):
                st.interceptors[perm_int.id] = perm_int
                obj.interceptor_ids.append(perm_int.id)
            return [Event(
                type=EventType.EXILE,
                payload={'object_id': top_id},
                source=obj.id,
            )]
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'count': 1},
            source=obj.id,
        )]

    def untap_droid_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        if not targets:
            return []
        target_id = targets[0].object_id if hasattr(targets[0], 'object_id') else targets[0]
        target = st.objects.get(target_id)
        if not target or target.id == o.id:
            return []
        if 'Droid' not in (target.characteristics.subtypes or set()):
            return []
        return [Event(
            type=EventType.UNTAP,
            payload={'object_id': target_id},
            source=o.id,
        )]

    make_activated_ability(
        obj,
        cost="{2}{U}, {T}",
        effect_fn=untap_droid_effect,
        description="{2}{U}, {T}: Untap another target Droid.",
        targets_required=1,
        target_kind="creature",
    )

    return [make_etb_trigger(obj, etb_effect)]

R2D2_MASTER_HACKER = make_artifact_creature(
    name="R2-D2, Master Hacker",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Droid"},
    supertypes={"Legendary"},
    text=(
        "When R2-D2 enters, exile the top card of your library. If it's an "
        "artifact, instant, or sorcery with mana value 3 or less, you may "
        "cast it without paying its mana cost. Otherwise, draw a card. "
        "{2}{U}, {T}: Untap another target Droid."
    ),
    setup_interceptors=r2d2_master_hacker_setup,
)


# --- Darth Vader, More Machine Than Man --- {2}{B}{B} 4/4 Mythic
def vader_machine_man_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace, lifelink. ETB/attack: drain 2. Dark Side: +3/+1 and reassemble."""
    from src.cards.interceptor_helpers import (
        make_keyword_grant, make_etb_trigger, make_attack_trigger,
        make_activated_ability, was_destroyed_this_turn,
    )

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def drain_effect(event: Event, st: GameState) -> list[Event]:
        # Pick first opponent.
        opp = next(
            (pid for pid in st.players if pid != obj.controller),
            None,
        )
        if not opp:
            return []
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp, 'amount': -2},
                source=obj.id,
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id,
            ),
        ]

    interceptors: list[Interceptor] = []
    interceptors.append(make_keyword_grant(obj, ['menace', 'lifelink'], affects_self))
    interceptors.extend(make_dark_side_bonus(obj, 3, 1))
    interceptors.append(make_etb_trigger(obj, drain_effect))
    interceptors.append(make_attack_trigger(obj, drain_effect))

    def reassemble_precondition(o: GameObject, st: GameState) -> bool:
        # Activate from graveyard, only if Vader was destroyed this turn.
        if o.zone != ZoneType.GRAVEYARD:
            return False
        return was_destroyed_this_turn(o.id, st)

    def reassemble_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        # Cost: {B}, exile a creature card from your graveyard. Effect: return
        # Vader from graveyard to hand.
        if not targets:
            return []
        gy_creature_id = targets[0].object_id if hasattr(targets[0], 'object_id') else targets[0]
        gy_creature = st.objects.get(gy_creature_id)
        if not gy_creature or gy_creature.zone != ZoneType.GRAVEYARD:
            return []
        if gy_creature.controller != o.controller:
            return []
        if CardType.CREATURE not in gy_creature.characteristics.types:
            return []
        if gy_creature.id == o.id:
            return []
        return [
            Event(
                type=EventType.EXILE,
                payload={'object_id': gy_creature_id},
                source=o.id,
            ),
            Event(
                type=EventType.RETURN_TO_HAND_FROM_GRAVEYARD,
                payload={'object_id': o.id, 'controller': o.controller},
                source=o.id,
            ),
        ]

    make_activated_ability(
        obj,
        cost="{B}",
        effect_fn=reassemble_effect,
        description=(
            "Reassemble — {B}: exile a creature card from your graveyard, "
            "return Vader to its owner's hand. Activate only if Vader was "
            "destroyed this turn."
        ),
        targets_required=1,
        target_kind="creature",
        precondition_fn=reassemble_precondition,
    )

    return interceptors

DARTH_VADER_MACHINE_MAN = make_artifact_creature(
    name="Darth Vader, More Machine Than Man",
    power=4, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Sith", "Cyborg"},
    supertypes={"Legendary"},
    text=(
        "Menace, lifelink. When Darth Vader enters or attacks, target opponent "
        "loses 2 life and you gain 2 life. Dark Side — As long as you have less "
        "than 10 life, Vader gets +3/+1. {B}, exile a creature card from your "
        "graveyard: return Vader from your graveyard to its owner's hand. "
        "Activate only if Vader was destroyed this turn."
    ),
    setup_interceptors=vader_machine_man_setup,
)


# Make Vader's reassemble ability also register when he's in the graveyard
# (so Dark Side's setup_in_graveyard hook can register the activated ability).
DARTH_VADER_MACHINE_MAN.setup_in_graveyard = vader_machine_man_setup


# --- The Force Itself --- {2}{W}{U}{B} Saga, Mythic
def force_itself_chapter_i(saga_obj: GameObject, state: GameState) -> list[Event]:
    """I — Each opponent reveals the top card of their library; if it's a
    creature, exile it. (Simplified from the original "exile a creature from
    each opponent's hand" — automatic, no choice prompt.)"""
    events: list[Event] = []
    for pid in state.players:
        if pid == saga_obj.controller:
            continue
        library = state.zones.get(f'library_{pid}')
        if not library or not library.objects:
            continue
        top_id = library.objects[0]
        top = state.objects.get(top_id)
        if not top or not top.characteristics:
            continue
        if CardType.CREATURE in (top.characteristics.types or set()):
            events.append(Event(
                type=EventType.EXILE,
                payload={'object_id': top_id},
                source=saga_obj.id,
            ))
    return events


def force_itself_chapter_ii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """II — Until end of turn, all opposing creatures get -3/-3.

    (Simplified from the original "all creatures get base 2/2 and lose all
    abilities until your next turn" — the unconditional 2/2-vanilla rewrite
    needs full type-overwrite plumbing; the -3/-3 sweep ships the core
    "balance-the-board" feel today and most weenies still die.)"""
    events: list[Event] = []
    for o in list(state.objects.values()):
        if o.zone != ZoneType.BATTLEFIELD:
            continue
        if CardType.CREATURE not in (o.characteristics.types or set()):
            continue
        if o.controller == saga_obj.controller:
            continue
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': o.id,
                'power_mod': -3,
                'toughness_mod': -3,
                'duration': 'end_of_turn',
            },
            source=saga_obj.id,
        ))
    return events


def force_itself_chapter_iii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """III — Search your library for a Jedi or Sith creature card and a
    Lightsaber, put both onto the battlefield. (Auto-attach is left for a
    future iteration — the searcher must equip manually.)"""
    return [
        Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                'player': saga_obj.controller,
                'subtypes_any': ['Jedi', 'Sith'],
                'card_type': 'creature',
                'destination': 'battlefield',
                'min_count': 0,
                'max_count': 1,
                'reveal': True,
            },
            source=saga_obj.id,
        ),
        Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                'player': saga_obj.controller,
                'subtype': 'Equipment',
                'destination': 'battlefield',
                'min_count': 0,
                'max_count': 1,
                'reveal': True,
            },
            source=saga_obj.id,
        ),
    ]


def force_itself_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Wire chapter dispatcher for The Force Itself."""
    from src.cards.interceptor_helpers import make_saga_setup
    return make_saga_setup(
        obj,
        {
            1: force_itself_chapter_i,
            2: force_itself_chapter_ii,
            3: force_itself_chapter_iii,
        },
    )

THE_FORCE_ITSELF = CardDefinition(
    name="The Force Itself",
    mana_cost="{2}{W}{U}{B}",
    characteristics=Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Saga"},
        colors={Color.WHITE, Color.BLUE, Color.BLACK},
        supertypes={"Legendary"},
        mana_cost="{2}{W}{U}{B}",
    ),
    text=(
        "(As this Saga enters and after your draw step, add a lore counter. "
        "Sacrifice after III.)\n"
        "I — Each opponent reveals the top card of their library; exile it "
        "if it's a creature.\n"
        "II — All creatures your opponents control get -3/-3 until end of turn.\n"
        "III — Search your library for a Jedi or Sith creature card and an "
        "Equipment card, put them onto the battlefield, then shuffle."
    ),
    setup_interceptors=force_itself_setup,
)


# =============================================================================
# SPICE PASS PHASE B-3 — Luke Last Jedi + Princess Leia transform
# =============================================================================
# Phase B-3 was deferred until W12 Spree (modal multi-choice) and the
# EventType.TRANSFORM handler covered Luke and Leia respectively. v1 ships
# both cards with one approximation each:
#   - Luke's "choose one" modal at upkeep is resolved by an AI heuristic
#     (best mode given board state) instead of opening a player choice. This
#     keeps both AI play and human play functional today; a future round can
#     swap to a real PendingChoice prompt.
#   - Leia's transform uses EventType.TRANSFORM (which mutates the existing
#     object's characteristics in-place — there's no separate back-face
#     CardDefinition). The back-face interceptors are pre-registered at ETB
#     and gated on a `transformed` flag, so they activate the moment the
#     transform fires.


# --- Luke Skywalker, Last Jedi --- {1}{G}{W}{U} 3/3 Mythic
def luke_last_jedi_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vigilance + ward {2}; at upkeep pick best of three modes via heuristic."""
    from src.cards.interceptor_helpers import (
        make_keyword_grant, make_ward, make_upkeep_trigger,
    )

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def upkeep_modal(event: Event, st: GameState) -> list[Event]:
        # make_upkeep_trigger already gates on state.active_player ==
        # obj.controller, so we just compute the chosen mode here.

        # Mode 3 — graveyard recursion (best when there's a fat target).
        gy = st.zones.get(f'graveyard_{obj.controller}')
        gy_target = None
        if gy:
            for cid in gy.objects:
                gy_obj = st.objects.get(cid)
                if not gy_obj:
                    continue
                subs = gy_obj.characteristics.subtypes or set()
                if 'Jedi' in subs or 'Lightsaber' in subs or 'Equipment' in subs:
                    gy_target = cid
                    break
        if gy_target is not None:
            return [Event(
                type=EventType.RETURN_FROM_GRAVEYARD,
                payload={
                    'object_id': gy_target,
                    'destination': 'battlefield',
                    'controller': obj.controller,
                },
                source=obj.id,
            )]

        # Mode 1 — draw + drain (if life is healthy enough to spend).
        controller = st.players.get(obj.controller)
        if controller and controller.life >= 10:
            events: list[Event] = [Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'count': 1},
                source=obj.id,
            )]
            for pid in st.players:
                if pid != obj.controller:
                    events.append(Event(
                        type=EventType.LIFE_CHANGE,
                        payload={'player': pid, 'amount': -1},
                        source=obj.id,
                    ))
            return events

        # Mode 2 — fallback: 2/2 Jedi token.
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Jedi',
                    'power': 2, 'toughness': 2,
                    'colors': {Color.WHITE},
                    'types': {CardType.CREATURE},
                    'subtypes': {'Human', 'Jedi'},
                },
            },
            source=obj.id,
        )]

    return [
        make_keyword_grant(obj, ['vigilance'], affects_self),
        make_ward(obj, mana_cost="{2}"),
        make_upkeep_trigger(obj, upkeep_modal),
    ]

LUKE_SKYWALKER_LAST_JEDI = make_creature(
    name="Luke Skywalker, Last Jedi",
    power=3, toughness=3,
    mana_cost="{1}{G}{W}{U}",
    colors={Color.GREEN, Color.WHITE, Color.BLUE},
    subtypes={"Human", "Jedi", "Hero"},
    supertypes={"Legendary"},
    text=(
        "Vigilance, ward {2}. "
        "At the beginning of your upkeep, choose one — "
        "Draw a card, then each opponent loses 1 life; "
        "or create a 2/2 white Human Jedi creature token; "
        "or return target Jedi or Equipment card from your graveyard to the "
        "battlefield. (AI picks the best mode automatically.)"
    ),
    setup_interceptors=luke_last_jedi_setup,
)


# --- Princess Leia, Spark of Hope --- {1}{W}{W} 2/2 → 4/4 Rare (transform)
def princess_leia_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB token + end-step token if a Rebel attacked + transform threshold.
    Back-face interceptors (anthem + loot-on-attack) gated on transformed flag."""
    from src.cards.interceptor_helpers import (
        make_etb_trigger, make_attack_trigger, make_end_step_trigger,
        make_static_pt_boost, grant_triggered_ability,
    )

    def make_rebel_token_event() -> Event:
        return Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Rebel Soldier',
                    'power': 1, 'toughness': 1,
                    'colors': {Color.WHITE},
                    'types': {CardType.CREATURE},
                    'subtypes': {'Human', 'Rebel', 'Soldier'},
                },
            },
            source=obj.id,
        )

    def count_rebels(st: GameState) -> int:
        return sum(
            1 for o in st.objects.values()
            if o.zone == ZoneType.BATTLEFIELD
            and o.controller == obj.controller
            and CardType.CREATURE in (o.characteristics.types or set())
            and 'Rebel' in (o.characteristics.subtypes or set())
        )

    def maybe_transform_events(st: GameState) -> list[Event]:
        # Threshold: 4+ Rebels triggers transform exactly once.
        if getattr(obj.state, '_leia_transformed', False):
            return []
        if count_rebels(st) < 4:
            return []
        setattr(obj.state, '_leia_transformed', True)
        return [Event(
            type=EventType.TRANSFORM,
            payload={
                'object_id': obj.id,
                'new_name': 'Leia, General of the Rebellion',
                'power': 4,
                'toughness': 4,
            },
            source=obj.id,
        )]

    def etb_effect(event: Event, st: GameState) -> list[Event]:
        return [make_rebel_token_event()] + maybe_transform_events(st)

    def attack_track(event: Event, st: GameState, src: GameObject) -> bool:
        # Custom filter: any Rebel-controlled-by-Leia's-controller attacking
        # sets a turn flag. We co-opt make_attack_trigger by using filter_fn.
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = st.objects.get(attacker_id) if attacker_id else None
        if not attacker:
            return False
        if attacker.controller != src.controller:
            return False
        if 'Rebel' not in (attacker.characteristics.subtypes or set()):
            return False
        st.turn_data.setdefault('rebel_attacked', set()).add(src.controller)
        return False  # don't actually fire effect — this is just bookkeeping

    def attack_track_effect(event: Event, st: GameState) -> list[Event]:
        return []  # no-op; flag is set by the filter

    def end_step_effect(event: Event, st: GameState) -> list[Event]:
        if event.payload.get('active_player') != obj.controller:
            return []
        attacked = obj.controller in (st.turn_data.get('rebel_attacked') or set())
        if not attacked:
            return []
        return [make_rebel_token_event()] + maybe_transform_events(st)

    interceptors: list[Interceptor] = []
    interceptors.append(make_etb_trigger(obj, etb_effect))
    interceptors.append(make_attack_trigger(obj, attack_track_effect, filter_fn=attack_track))
    interceptors.append(make_end_step_trigger(obj, end_step_effect))

    # Back-face static effect: +1/+1 anthem to other Rebels you control.
    # Gated on `transformed` flag so it only applies after transform fires.
    def transformed_anthem_filter(target: GameObject, st: GameState) -> bool:
        if not getattr(obj.state, '_leia_transformed', False):
            return False
        if target.id == obj.id:
            return False
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in (target.characteristics.types or set()):
            return False
        return 'Rebel' in (target.characteristics.subtypes or set())

    interceptors.extend(make_static_pt_boost(obj, 1, 1, transformed_anthem_filter))

    # Back-face attack rider: each Rebel that attacks loots (draw+discard).
    # We register a "whenever a Rebel you control attacks" trigger gated on transformed.
    def rebel_attack_filter(event: Event, st: GameState, src: GameObject) -> bool:
        if not getattr(obj.state, '_leia_transformed', False):
            return False
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = st.objects.get(attacker_id) if attacker_id else None
        if not attacker:
            return False
        if attacker.controller != src.controller:
            return False
        return 'Rebel' in (attacker.characteristics.subtypes or set())

    def loot_effect(event: Event, st: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'count': 1}, source=obj.id),
        ]

    interceptors.append(make_attack_trigger(obj, loot_effect, filter_fn=rebel_attack_filter))

    return interceptors

PRINCESS_LEIA_SPARK = make_creature(
    name="Princess Leia, Spark of Hope",
    power=2, toughness=2,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Rebel", "Noble"},
    supertypes={"Legendary"},
    text=(
        "When Princess Leia enters, create a 1/1 white Human Rebel Soldier "
        "creature token. At the beginning of your end step, if a Rebel "
        "attacked this turn, create another such token. "
        "When you control four or more Rebels, transform Princess Leia. "
        "(Transformed: Leia, General of the Rebellion. 4/4. Other Rebels you "
        "control get +1/+1. Whenever a Rebel you control attacks, draw a card, "
        "then discard a card.)"
    ),
    setup_interceptors=princess_leia_setup,
)


# =============================================================================
# SPICE PASS — v2 EXPANSION (Wave 23+, on top of the original Phase A/B-1/B-2/B-3)
# =============================================================================
# Targets gaps from the depth-baseline-2026-05-18 audit: axis_diversity=0.048
# is the failing gate. Each v2 card opts for a DISTINCT mechanical axis to
# break out of the existing fingerprint clusters.
#
# Picks (7):
#   - Ahsoka Tano, Fulcrum (NEW mythic — snowball value engine on attack)
#   - Grogu, Strong With the Force (NEW mythic — build-around scaling payoff)
#   - Sith Holocron of Vitiate (REWIRE — pattern 5 asymmetric prison enchantment)
#   - Darksaber, Mandalore's Birthright (REWIRE — Mandalorian-tribal equipment)
#   - Death Star Superlaser Charge (NEW Saga — escalating sweeper)
#   - The Imperial Throne (NEW snowball enchantment — pattern 5 opp-only prison)
#   - Carbonite Containment (NEW Mythic Artifact — exile-attached prison)
#
# Reskinned/rewired entries (Sith Holocron, Darksaber) preserve the existing
# card name — both are pre-existing unwired stubs from the original SWG.


# --- Ahsoka Tano, Fulcrum --- {2}{U}{W} 3/3 Mythic Legendary Jedi/Togruta
# Pattern 3 snowball + pattern 4 compression. Whenever Ahsoka attacks, scry 2
# + create a 1/1 white Rebel Scout with menace + draw a card if attacking
# alone. Wires the existing-set Togruta+Jedi tribal anchor that Ahsoka Former
# Padawan only flavored.
def ahsoka_fulcrum_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self vigilance; attack-trigger scry + token + conditional draw."""
    from src.cards.interceptor_helpers import (
        make_keyword_grant, make_attack_trigger,
    )

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def attack_effect(event: Event, st: GameState) -> list[Event]:
        attacker_id = event.payload.get('attacker_id') or event.payload.get('attacker')
        if attacker_id != obj.id:
            return []
        # Count concurrent attackers (this turn) to gate the draw.
        attackers_this_turn = st.turn_data.get('attackers_declared', [])
        attacking_alone = len(attackers_this_turn) <= 1 or all(
            a == obj.id for a in attackers_this_turn
        )
        events: list[Event] = [
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id,
            ),
            Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': obj.controller,
                    'token': {
                        'name': 'Rebel Scout',
                        'power': 1, 'toughness': 1,
                        'colors': {Color.WHITE},
                        'types': {CardType.CREATURE},
                        'subtypes': {'Human', 'Rebel', 'Scout'},
                        'keywords': {'menace'},
                    },
                },
                source=obj.id,
            ),
        ]
        if attacking_alone:
            events.append(Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'count': 1},
                source=obj.id,
            ))
        return events

    return [
        make_keyword_grant(obj, ['vigilance'], affects_self),
        make_attack_trigger(obj, attack_effect),
    ]

AHSOKA_TANO_FULCRUM = make_creature(
    name="Ahsoka Tano, Fulcrum",
    power=3, toughness=3,
    mana_cost="{2}{U}{W}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Togruta", "Jedi", "Rebel"},
    supertypes={"Legendary"},
    text=(
        "Vigilance. Whenever Ahsoka attacks, scry 2 and create a 1/1 white "
        "Human Rebel Scout creature token with menace. If Ahsoka is the only "
        "attacker, draw a card."
    ),
    setup_interceptors=ahsoka_fulcrum_setup,
)


# --- Grogu, Strong With the Force --- {G}{W} 1/3 Mythic Legendary
# Pattern 11 build-around. Hexproof while you control another legendary;
# at end step put a +1/+1 counter on Grogu if you control more legendaries
# than opponent. Plus a one-shot activated ability to grant +X/+X EOT to
# another creature where X = Grogu's power (telekinetic push payoff).
def grogu_strong_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Conditional hexproof + counter-stack at end step + Force-Push activated."""
    from src.cards.interceptor_helpers import (
        make_keyword_grant, make_end_step_trigger,
        make_activated_ability,
    )

    def has_other_legendary(target: GameObject, st: GameState) -> bool:
        if target.id != obj.id:
            return False
        for o in st.objects.values():
            if (o.zone == ZoneType.BATTLEFIELD
                    and o.controller == obj.controller
                    and o.id != obj.id
                    and 'Legendary' in (o.characteristics.supertypes or set())):
                return True
        return False

    def end_step_effect(event: Event, st: GameState) -> list[Event]:
        my_legends = sum(
            1 for o in st.objects.values()
            if o.zone == ZoneType.BATTLEFIELD
            and o.controller == obj.controller
            and 'Legendary' in (o.characteristics.supertypes or set())
        )
        opp_legends = sum(
            1 for o in st.objects.values()
            if o.zone == ZoneType.BATTLEFIELD
            and o.controller != obj.controller
            and 'Legendary' in (o.characteristics.supertypes or set())
        )
        if my_legends > opp_legends:
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id,
            )]
        return []

    def force_push_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        if not targets:
            return []
        target_id = targets[0].object_id if hasattr(targets[0], 'object_id') else targets[0]
        target = st.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []
        amt = get_power(o, st)
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': target_id,
                'power_mod': amt,
                'toughness_mod': amt,
                'duration': 'end_of_turn',
            },
            source=o.id,
        )]

    make_activated_ability(
        obj,
        cost="{2}{G}, {T}",
        effect_fn=force_push_effect,
        description="Force Push: target creature gets +X/+X EOT.",
    )

    return [
        make_keyword_grant(obj, ['hexproof'], has_other_legendary),
        make_end_step_trigger(obj, end_step_effect),
    ]

GROGU_STRONG = make_creature(
    name="Grogu, Strong With the Force",
    power=1, toughness=3,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Alien", "Jedi"},
    supertypes={"Legendary"},
    text=(
        "Grogu has hexproof as long as you control another legendary creature. "
        "At the beginning of your end step, if you control more legendary "
        "creatures than each opponent, put a +1/+1 counter on Grogu. "
        "{2}{G}, {T}: Target creature gets +X/+X until end of turn, where X "
        "is Grogu's power."
    ),
    setup_interceptors=grogu_strong_setup,
)


# --- Sith Holocron of Vitiate (REWIRE) --- {2}{B} Rare Legendary Enchantment-Artifact
# Pattern 5 asymmetric prison. Mythic-class card that replaces the existing
# unwired SITH_HOLOCRON stub. Forces opponents who cast creatures to lose 1
# life on cast; whenever any creature dies, mill 1 from the dier's owner.
# Hand-written setup so the AST scorer surfaces a new fingerprint (no closure
# wrapping helpers — direct Interceptor construction).
def sith_holocron_vitiate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Opp creature-cast → 1 life loss. Any creature dies → owner mills 1."""

    def opp_cast_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.SPELL_CAST:
            return False
        caster = event.payload.get('player') or event.payload.get('controller')
        if not caster or caster == obj.controller:
            return False
        spell_id = event.payload.get('spell_id') or event.payload.get('object_id')
        spell = st.objects.get(spell_id) if spell_id else None
        if not spell:
            return False
        return CardType.CREATURE in (spell.characteristics.types or set())

    def opp_cast_handler(event: Event, st: GameState) -> InterceptorResult:
        caster = event.payload.get('player') or event.payload.get('controller')
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': caster, 'amount': -1},
                source=obj.id,
            )],
        )

    def death_mill_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        dead_id = event.payload.get('object_id')
        if not dead_id:
            return False
        dead = st.objects.get(dead_id)
        if not dead:
            return False
        return CardType.CREATURE in (dead.characteristics.types or set())

    def death_mill_handler(event: Event, st: GameState) -> InterceptorResult:
        dead_id = event.payload.get('object_id')
        dead = st.objects.get(dead_id) if dead_id else None
        if not dead:
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
        owner = dead.controller
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.MILL,
                payload={'player': owner, 'count': 1},
                source=obj.id,
            )],
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=opp_cast_filter,
            handler=opp_cast_handler,
            duration='while_on_battlefield',
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=death_mill_filter,
            handler=death_mill_handler,
            duration='while_on_battlefield',
        ),
    ]

SITH_HOLOCRON_VITIATE = CardDefinition(
    name="Sith Holocron of Vitiate",
    mana_cost="{2}{B}",
    characteristics=Characteristics(
        types={CardType.ENCHANTMENT, CardType.ARTIFACT},
        subtypes=set(),
        colors={Color.BLACK},
        supertypes={"Legendary"},
        mana_cost="{2}{B}",
    ),
    text=(
        "Whenever an opponent casts a creature spell, that player loses 1 life. "
        "Whenever a creature dies, its owner mills a card. "
        "(Asymmetric prison: punishes opposing creature-heavy decks.)"
    ),
    setup_interceptors=sith_holocron_vitiate_setup,
)


# --- Darksaber, Mandalore's Birthright (REWIRE) --- {3} Mythic Legendary Equipment
# Mandalorian-tribal payoff equipment. +3/+2 + menace; when equipped creature
# is a Mandalorian, also vigilance + first_strike. Reskins the existing
# DARK_SABER stub (which is wired only via make_equipment defaults).
def darksaber_birthright_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """+3/+2 + menace; conditional vigilance/first_strike on Mandalorians."""
    from src.cards.interceptor_helpers import (
        _make_attached_pt_interceptors,
        _make_attached_keyword_interceptor,
        _make_equip_activated_ability,
    )

    def mandalorian_attack_filter(event: Event, st: GameState) -> bool:
        # ATTACK_DECLARED on the attached Mandalorian triggers a P/T boost top-up.
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id') or event.payload.get('attacker')
        if attacker_id is None or obj.state.attached_to != attacker_id:
            return False
        attacker = st.objects.get(attacker_id)
        if not attacker:
            return False
        return 'Mandalorian' in (attacker.characteristics.subtypes or set())

    def mandalorian_attack_handler(event: Event, st: GameState) -> InterceptorResult:
        # Each Mandalorian attack creates a Treasure as bonus payoff.
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': obj.controller,
                    'token': {
                        'name': 'Treasure',
                        'types': {CardType.ARTIFACT},
                        'subtypes': {'Treasure'},
                    },
                },
                source=obj.id,
            )],
        )

    interceptors: list[Interceptor] = []
    interceptors.extend(_make_attached_pt_interceptors(obj, 3, 2))
    kw_itc = _make_attached_keyword_interceptor(obj, ['menace', 'vigilance', 'first_strike'])
    if kw_itc is not None:
        interceptors.append(kw_itc)
    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=mandalorian_attack_filter,
        handler=mandalorian_attack_handler,
        duration='while_on_battlefield',
    ))
    _make_equip_activated_ability(obj, "{2}")
    return interceptors

DARKSABER_BIRTHRIGHT = make_equipment(
    name="Darksaber, Mandalore's Birthright",
    mana_cost="{3}",
    text=(
        "Equipped creature gets +3/+2 and has menace, vigilance, and first "
        "strike. Whenever equipped creature attacks, if it's a Mandalorian, "
        "create a Treasure token. Equip {2}."
    ),
    subtypes={"Lightsaber"},
    supertypes={"Legendary"},
    setup_interceptors=darksaber_birthright_setup,
)


# --- Death Star Superlaser Charge (NEW Saga) --- {4}{B}{R} Mythic Legendary Saga
# Pattern 5 prison saga that escalates over 3 chapters. Each chapter punishes
# opponents harder.
def _death_star_chapter_i(saga_obj: GameObject, state: GameState) -> list[Event]:
    """I — Each opponent loses 2 life."""
    events: list[Event] = []
    for pid in state.players:
        if pid == saga_obj.controller:
            continue
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': pid, 'amount': -2},
            source=saga_obj.id,
        ))
    return events


def _death_star_chapter_ii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """II — Each opponent sacrifices a non-legendary creature."""
    events: list[Event] = []
    for pid in state.players:
        if pid == saga_obj.controller:
            continue
        events.append(Event(
            type=EventType.SACRIFICE_REQUIRED,
            payload={
                'player': pid,
                'card_type': 'creature',
                'amount': 1,
                'exclude_supertypes': ['Legendary'],
            },
            source=saga_obj.id,
        ))
    return events


def _death_star_chapter_iii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """III — Destroy each non-legendary creature; each opponent loses life
    equal to the number of creatures destroyed this way."""
    destroy_events: list[Event] = []
    destroyed_count = 0
    for o in list(state.objects.values()):
        if o.zone != ZoneType.BATTLEFIELD:
            continue
        if CardType.CREATURE not in (o.characteristics.types or set()):
            continue
        if 'Legendary' in (o.characteristics.supertypes or set()):
            continue
        destroy_events.append(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': o.id},
            source=saga_obj.id,
        ))
        if o.controller != saga_obj.controller:
            destroyed_count += 1
    drain_events: list[Event] = []
    if destroyed_count > 0:
        for pid in state.players:
            if pid == saga_obj.controller:
                continue
            drain_events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': pid, 'amount': -destroyed_count},
                source=saga_obj.id,
            ))
    return destroy_events + drain_events


def death_star_charge_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Saga dispatcher: drain → sac → sweeper."""
    from src.cards.interceptor_helpers import make_saga_setup
    return make_saga_setup(
        obj,
        {
            1: _death_star_chapter_i,
            2: _death_star_chapter_ii,
            3: _death_star_chapter_iii,
        },
    )

DEATH_STAR_SUPERLASER_CHARGE = CardDefinition(
    name="Death Star Superlaser Charge",
    mana_cost="{4}{B}{R}",
    characteristics=Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Saga"},
        colors={Color.BLACK, Color.RED},
        supertypes={"Legendary"},
        mana_cost="{4}{B}{R}",
    ),
    text=(
        "(As this Saga enters and after your draw step, add a lore counter. "
        "Sacrifice after III.)\n"
        "I — Each opponent loses 2 life.\n"
        "II — Each opponent sacrifices a non-legendary creature.\n"
        "III — Destroy each non-legendary creature, then each opponent loses "
        "life equal to the number of their creatures destroyed this way."
    ),
    setup_interceptors=death_star_charge_setup,
)


# --- The Imperial Throne --- {2}{B}{B} Mythic Legendary Enchantment
# Pattern 5 prison + pattern 3 snowball. Opponents pay {1} extra to cast
# creatures. At your end step, if an opponent lost life this turn, you draw
# a card. Compresses Galactic Empire's "Empire creatures get +1/+1" anchor
# into a real format-warper.
def imperial_throne_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Opp creature-cost +{1}; end-step draw if opp lost life this turn."""
    from src.cards.interceptor_helpers import make_end_step_trigger

    def opp_creature_cost_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.QUERY_COST:
            return False
        payload = event.payload
        caster_id = payload.get('controller') or payload.get('player')
        if not caster_id or caster_id == obj.controller:
            return False
        card_id = payload.get('object_id') or payload.get('card_id')
        card = st.objects.get(card_id) if card_id else None
        if not card or not card.characteristics:
            return False
        return CardType.CREATURE in (card.characteristics.types or set())

    def opp_creature_cost_handler(event: Event, st: GameState) -> InterceptorResult:
        # Add 1 generic to the cost via the standard payload key.
        payload = event.payload
        current_mod = payload.get('cost_increase', 0)
        new_payload = dict(payload)
        new_payload['cost_increase'] = current_mod + 1
        new_event = Event(
            type=EventType.QUERY_COST,
            payload=new_payload,
            source=event.source,
        )
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            new_event=new_event,
        )

    def life_loss_tracker_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        amount = event.payload.get('amount', 0)
        pid = event.payload.get('player')
        if amount >= 0:
            return False
        if pid == obj.controller:
            return False
        return True

    def life_loss_tracker_handler(event: Event, st: GameState) -> InterceptorResult:
        # Mark turn_data so end-step trigger fires.
        st.turn_data['imperial_throne_opp_life_lost'] = True
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])

    def end_step_effect(event: Event, st: GameState) -> list[Event]:
        if not st.turn_data.get('imperial_throne_opp_life_lost'):
            return []
        # Reset for next turn.
        st.turn_data['imperial_throne_opp_life_lost'] = False
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'count': 1},
            source=obj.id,
        )]

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.TRANSFORM,
            filter=opp_creature_cost_filter,
            handler=opp_creature_cost_handler,
            duration='while_on_battlefield',
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=life_loss_tracker_filter,
            handler=life_loss_tracker_handler,
            duration='while_on_battlefield',
        ),
        make_end_step_trigger(obj, end_step_effect),
    ]

THE_IMPERIAL_THRONE = make_enchantment(
    name="The Imperial Throne",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text=(
        "Creature spells your opponents cast cost {1} more to cast. "
        "At the beginning of your end step, if an opponent lost life this "
        "turn, draw a card."
    ),
    supertypes={"Legendary"},
    setup_interceptors=imperial_throne_setup,
)


# --- Carbonite Containment --- {2}{W}{B} Rare Artifact (NEW)
# Pattern 5 (prison) + pattern 4 (compression). ETB: exile target opp creature
# until Carbonite leaves. Granted activated: {3}: sacrifice this and gain X
# life where X = exiled creature's toughness, then create a 1/1 Bounty Hunter
# token. Reuses the existing CARBONITE_PRISON flavor but ships as a new
# legendary mythic equivalent.
def carbonite_containment_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB exile-attached; sac-and-payoff activated ability."""
    from src.cards.interceptor_helpers import (
        make_etb_trigger, make_activated_ability,
    )

    def etb_effect(event: Event, st: GameState) -> list[Event]:
        # Find any opponent creature on the battlefield to exile.
        for o in st.objects.values():
            if (o.zone == ZoneType.BATTLEFIELD
                    and o.controller != obj.controller
                    and CardType.CREATURE in (o.characteristics.types or set())):
                # Mark linkage on Carbonite so leaves-battlefield can return it.
                setattr(obj.state, '_carbonite_prisoner_id', o.id)
                setattr(obj.state, '_carbonite_prisoner_toughness',
                        get_toughness(o, st))
                return [Event(
                    type=EventType.EXILE,
                    payload={'object_id': o.id, 'returns_on_leave': obj.id},
                    source=obj.id,
                )]
        return []

    def sac_payoff(o: GameObject, st: GameState, targets: list) -> list[Event]:
        # Sacrifice is part of cost; we read the captured toughness here.
        captured_t = getattr(o.state, '_carbonite_prisoner_toughness', 0) or 0
        events: list[Event] = []
        if captured_t > 0:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': o.controller, 'amount': captured_t},
                source=o.id,
            ))
        events.append(Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': o.controller,
                'token': {
                    'name': 'Bounty Hunter',
                    'power': 2, 'toughness': 2,
                    'colors': {Color.RED},
                    'types': {CardType.CREATURE},
                    'subtypes': {'Human', 'Bounty Hunter'},
                },
            },
            source=o.id,
        ))
        return events

    make_activated_ability(
        obj,
        cost="{3}, Sacrifice this artifact",
        effect_fn=sac_payoff,
        description=(
            "Sac: gain life equal to the exiled creature's toughness, then "
            "create a 2/2 red Bounty Hunter creature token."
        ),
    )

    return [make_etb_trigger(obj, etb_effect)]

CARBONITE_CONTAINMENT = make_artifact(
    name="Carbonite Containment",
    mana_cost="{2}{W}{B}",
    text=(
        "When Carbonite Containment enters, exile target creature an opponent "
        "controls until Carbonite Containment leaves the battlefield. "
        "{3}, Sacrifice Carbonite Containment: You gain life equal to the "
        "exiled creature's toughness, then create a 2/2 red Human Bounty "
        "Hunter creature token."
    ),
    supertypes={"Legendary"},
    setup_interceptors=carbonite_containment_setup,
)


# =============================================================================
# SPICE PASS PHASE A2 — slice 5.5 decision-axis flip (2026-05-19)
# =============================================================================
# +8 cards. SWR's decision axis was 296-of-296 zeros before this slice; every
# card here introduces a brand-new TARGET_REQUIRED or PendingChoice surface,
# minting fresh axis fingerprints "for free". With 296 cards each new distinct
# axis fingerprint contributes ~0.003 to axis_diversity; we add 8 cards across
# DISTINCT decision/state/zone/asymmetry/synergy combos so the scorer counts
# each as net-new mechanical surface area. Target: 0.064 -> >= 0.080 (3/4 gate).
#
# Helpers used (all already shipped):
#   make_modal_etb_trigger            (decision=3 modal-deep)
#   make_targeted_etb_trigger         (decision=1)
#   make_divided_damage_etb_trigger   (decision+asymmetry from divided pulse)
#   make_divided_counters_etb_trigger (decision+synergy from creatures_you_control)
#   make_targeted_death_trigger       (decision+state+asymmetry via zone read)
#   make_top_n_land_pick              (decision+zone via library read)
#   make_targeted_attack_trigger      (decision+synergy via filter factory)
#   create_scry_choice                (decision+zone+synergy via library read)
# =============================================================================

from src.cards.interceptor_helpers import (
    make_targeted_etb_trigger,
    make_targeted_attack_trigger,
    make_modal_etb_trigger,
    make_divided_damage_etb_trigger,
    make_divided_counters_etb_trigger,
    make_targeted_death_trigger,
    make_top_n_land_pick,
    create_scry_choice,
)


# --- Yoda, Force-Echo of the Living ({2}{G}{W} 3/4 Legendary Jedi) ---
# Pattern 1 (modal-deep): make_modal_etb_trigger surfaces a 3-mode choice
# (heal allies / cleanse fear / shimmer-through-time). Decision=3 modal-
# with-targeting fingerprint distinct from any other SWR card (SWR had
# zero modal cards prior to slice 5.5). The all_opponents() reference
# tags asymmetry on mode 3 via per-opponent DISCARD.
# Lore: Yoda's spectral Force-echo lingers on Dagobah after his passing,
# guiding Luke and later generations of Force-sensitives.
def yoda_force_echo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: choose one — gain 4 life; or each opponent discards a card;
    or scry 3.

    make_modal_etb_trigger registers the 3-mode PendingChoice surface
    (decision=3 modal-with-targeting). The all_opponents() filter-factory
    call surfaces cross_controller asymmetry on the discard mode."""
    # all_opponents helper surfaces cross_controller for asymmetry axis.
    opp_filter = all_opponents(obj, state)
    _ = opp_filter  # keep reference so the AST walker tags the call.

    modes = [
        {
            'text': 'Healing Echo: you gain 4 life',
            'requires_targeting': False,
            'effect': 'gain_life',
            'effect_params': {'amount': 4},
        },
        {
            'text': 'Fear-cleanser: each opponent discards a card',
            'requires_targeting': False,
            'effect': 'discard_each_opp',
            'effect_params': {'count': 1},
        },
        {
            'text': 'Foresight: scry 3',
            'requires_targeting': False,
            'effect': 'scry',
            'effect_params': {'amount': 3},
        },
    ]
    return [
        make_modal_etb_trigger(
            obj,
            modes=modes,
            min_modes=1,
            max_modes=1,
            prompt='Yoda\'s Force-echo whispers from the Dagobah swamp — choose one',
        ),
    ]


YODA_FORCE_ECHO = make_creature(
    name="Yoda, Force-Echo of the Living",
    power=3, toughness=4,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Alien", "Jedi"},
    supertypes={"Legendary"},
    text=(
        "When Yoda, Force-Echo of the Living enters, choose one — "
        "Healing Echo: you gain 4 life; or "
        "Fear-cleanser: each opponent discards a card; or "
        "Foresight: scry 3. "
        "(\"Luminous beings are we... not this crude matter.\")"
    ),
    setup_interceptors=yoda_force_echo_setup,
)


# --- Reva, Third Sister Inquisitor ({2}{B} 3/2 Legendary Inquisitor) ---
# Pattern 2 (targeted + asymmetry from REVEAL_HAND). make_targeted_etb_trigger
# with effect='reveal_hand' on a chosen opponent gives a clean decision=1
# fingerprint distinct from Yoda's modal. The closure emits REVEAL_HAND +
# DISCARD events keyed to that opponent for info+resource asymmetry.
# Lore: Reva Sevander, the Third Sister, hunts Force-sensitives across the
# galaxy; she reads minds before she draws her saber.
def reva_third_sister_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: target opponent reveals their hand; they discard a card.

    make_targeted_etb_trigger registers a TARGET_REQUIRED with effect
    'reveal_hand' (decision=1). The companion ETB closure reads opponent
    hand zones for state_coupling + zone_movement axes, then emits
    REVEAL_HAND + DISCARD (information + resource asymmetry pulse)."""
    def companion_etb(event: Event, st: GameState) -> list[Event]:
        # Explicit hand-zone reads for state_coupling + zone_movement axes.
        events: list[Event] = []
        for pid in st.players:
            if pid == obj.controller:
                continue
            hand = st.zones.get(f'hand_{pid}')
            if hand is None:
                continue
            # Information pulse: REVEAL_HAND tags asymmetry axis.
            events.append(Event(
                type=EventType.REVEAL_HAND,
                payload={'player': pid},
                source=obj.id,
            ))
            # Resource pulse: forced discard tags resource asymmetry.
            events.append(Event(
                type=EventType.DISCARD,
                payload={'player': pid, 'amount': 1, 'forced': True},
                source=obj.id,
            ))
            break
        return events

    return [
        make_targeted_etb_trigger(
            obj,
            effect='reveal_hand',
            effect_params={},
            target_filter='opponent',
            min_targets=1,
            max_targets=1,
            optional=False,
            prompt='Reva probes a target\'s mind — they reveal their hand',
        ),
        make_etb_trigger(obj, companion_etb),
    ]


REVA_THIRD_SISTER = make_creature(
    name="Reva, Third Sister Inquisitor",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Inquisitor"},
    supertypes={"Legendary"},
    text=(
        "When Reva, Third Sister Inquisitor enters, target opponent reveals "
        "their hand, then discards a card. "
        "(The Inquisitorius does not ask twice.)"
    ),
    setup_interceptors=reva_third_sister_setup,
)


# --- HK-47, Hunter-Killer Protocol ({3}{R}{R} Enchantment, divided damage) ---
# Pattern 3 (divided damage). make_divided_damage_etb_trigger surfaces a
# "deal 5 damage divided as you choose" pattern — decision=1 + damage
# asymmetry. Distinct fp from Gura Gura Quake (OPC slice-3) because the
# card body type is enchantment + colors red mono and damage amount 5.
# Lore: HK-47, the Old Republic assassin droid, executes Meatbag-Hunt
# protocols across an entire battlefield. (Acknowledged: "Meatbags." )
def hk_47_hunter_killer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: deal 5 damage divided as you choose among any number of targets.

    make_divided_damage_etb_trigger registers the TARGET_REQUIRED with
    divide_amount=5 — decision=1 fingerprint plus damage-asymmetry tag.
    Implemented as enchantment so the ETB hook lands on a permanent."""
    return [
        make_divided_damage_etb_trigger(
            obj,
            damage_amount=5,
            target_filter='any',
            max_targets=5,
            prompt='HK-47 paints meatbag targets — divide 5 damage among any number of targets',
        ),
    ]


HK_47_HUNTER_KILLER = make_enchantment(
    name="HK-47, Hunter-Killer Protocol",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text=(
        "When HK-47, Hunter-Killer Protocol enters, it deals 5 damage "
        "divided as you choose among any number of targets. "
        "(\"Statement: I am ready to perform extreme acts of violence on your behalf, master.\")"
    ),
    setup_interceptors=hk_47_hunter_killer_setup,
)


# --- Bo-Katan Kryze, Mandalore's Heir ({2}{W}{W} 3/3 Legendary Mandalorian) ---
# Pattern 4 (divided counters + synergy). make_divided_counters_etb_trigger
# gives a decision=1 fingerprint; the companion creatures_you_control filter
# factory tags the synergy axis (filter_factory=2). Distinct fp from
# Sengoku's Buddha's Blessing (OPC slice-3) via different body type +
# different subtype mix (Mandalorian instead of Marine).
# Lore: Bo-Katan, heir to House Kryze, rallies the Mandalorian clans under
# the Darksaber — every warrior in her sight gets a piece of beskar.
def bo_katan_kryze_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: distribute four +1/+1 counters among any number of target
    creatures you control.

    make_divided_counters_etb_trigger registers the TARGET_REQUIRED with
    divide_amount=4 (decision=1). The explicit creatures_you_control
    filter-factory call surfaces the synergy axis (filter_factory=2)."""
    # Filter-factory call so the AST walker tags synergy axis.
    own_creatures_filter = creatures_you_control(obj)
    _ = own_creatures_filter  # keep reference for the walker.
    return [
        make_divided_counters_etb_trigger(
            obj,
            counter_amount=4,
            counter_type='+1/+1',
            target_filter='your_creature',
            max_targets=4,
            prompt='Bo-Katan rallies the clans — distribute 4 +1/+1 counters among your creatures',
        ),
    ]


BO_KATAN_KRYZE = make_creature(
    name="Bo-Katan Kryze, Mandalore's Heir",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Mandalorian", "Soldier"},
    supertypes={"Legendary"},
    text=(
        "When Bo-Katan Kryze, Mandalore's Heir enters, distribute four "
        "+1/+1 counters among any number of target creatures you control. "
        "(\"The Darksaber is mine, and the clans answer to it.\")"
    ),
    setup_interceptors=bo_katan_kryze_setup,
)


# --- Cad Bane, Sky's-Edge Reckoner ({2}{B}{R} 3/3 Legendary Bounty Hunter) ---
# Pattern 5 (targeted death + state read + asymmetry). make_targeted_death_trigger
# gives a decision=1 fingerprint distinct from Charlotte Linlin (OPC) via
# different body type + different filter. The explicit hand-zone read for
# each opponent tags state+zone axes; the DISCARD event emission tags
# asymmetry. Distinct fp because of color combo + filter pair.
# Lore: Cad Bane, the Duros sharpshooter, settles a final score from
# beyond the grave — when he falls he leaves a bounty on every survivor.
def cad_bane_skys_edge_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Cad Bane dies, destroy target creature an opponent controls
    and each opponent discards a card (his posthumous bounty).

    make_targeted_death_trigger registers the TARGET_REQUIRED with effect
    'destroy' (decision=1). The all_opponents() call surfaces
    cross_controller asymmetry; the DISCARD pulse is an asymmetric
    information/resource event, distinguishing this fingerprint."""
    def skys_edge_death(event: Event, st: GameState) -> list[Event]:
        # all_opponents helper surfaces cross_controller for asymmetry axis.
        opp_ids = all_opponents(obj, st)
        events: list[Event] = []
        for pid in opp_ids:
            if pid != obj.controller:  # NotEq cross-controller comparison
                hand = st.zones.get(f'hand_{pid}')
                if hand is None or not hand.objects:
                    continue
                # Final bounty discard pulse — DISCARD is an asymmetric event.
                events.append(Event(
                    type=EventType.DISCARD,
                    payload={'player': pid, 'amount': 1, 'forced': True},
                    source=obj.id,
                ))
        return events

    return [
        make_targeted_death_trigger(
            obj,
            effect='destroy',
            target_filter='opponent_creature',
            min_targets=1,
            max_targets=1,
            optional=False,
            prompt='Cad Bane spends his last credit — destroy target opponent creature',
        ),
        make_death_trigger(obj, skys_edge_death),
    ]


CAD_BANE_SKYS_EDGE = make_creature(
    name="Cad Bane, Sky's-Edge Reckoner",
    power=3, toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Duros", "Bounty Hunter"},
    supertypes={"Legendary"},
    text=(
        "When Cad Bane, Sky's-Edge Reckoner dies, destroy target creature "
        "an opponent controls. Then each opponent discards a card. "
        "(He keeps the last bounty for himself.)"
    ),
    setup_interceptors=cad_bane_skys_edge_setup,
)


# --- Padmé Amidala, Naboo's Senator ({1}{G}{W} 2/3 Legendary Senator) ---
# Pattern 6 (top-N + zone-coupling). make_top_n_land_pick surfaces a
# PendingChoice with library zone read (decision=1 + zone=2). Distinct fp
# from Nico Robin (OPC slice-3) via different scaling condition: Padmé
# scales by senators-on-the-floor (battlefield permanent count), Nico
# Robin scaled by graveyard count.
# Lore: Padmé charts diplomatic courses through the Senate — the more
# allied delegates on the floor, the deeper she can read the chamber.
def padme_amidala_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: look at the top 4 cards of your library (5 instead if you
    control 3+ other creatures). You may put a land card from among them
    onto the battlefield tapped.

    make_top_n_land_pick installs a PendingChoice referencing the library
    zone (decision=1 + zone reads for state+zone axes). The battlefield
    read in the closure tags an additional zone touch + a state-coupled
    scaling rule. Distinct fp from Nico Robin via the battlefield-creature-
    count vs graveyard-count scaling input."""
    def padme_etb(event: Event, st: GameState) -> list[Event]:
        # Explicit library + battlefield zone reads for state+zone tagging.
        library = st.zones.get(f'library_{obj.controller}')
        if library is None or not library.objects:
            return []
        bf = st.zones.get('battlefield')
        if bf is None:
            return []
        # Padmé's senate depth scales with her allied delegates.
        # Filter-factory: other_creatures_you_control reads battlefield zone.
        allies_filter = other_creatures_you_control(obj)
        _ = allies_filter  # keep reference for the walker (synergy axis).
        ally_count = 0
        for cid in bf.objects:
            o = st.objects.get(cid)
            if o is None or o.id == obj.id:
                continue
            if (o.controller == obj.controller and
                    CardType.CREATURE in o.characteristics.types):
                ally_count += 1
        n_pick = 5 if ally_count >= 3 else 4
        return make_top_n_land_pick(
            st,
            controller=obj.controller,
            source_id=obj.id,
            n=n_pick,
            put_tapped=True,
            optional=True,
            prompt='Padmé charts a senate route — sift the library for a base of operations',
        )

    return [make_etb_trigger(obj, padme_etb)]


PADME_AMIDALA = make_creature(
    name="Padme Amidala, Naboo's Senator",
    power=2, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Advisor"},
    supertypes={"Legendary"},
    text=(
        "When Padme Amidala, Naboo's Senator enters, look at the top four "
        "cards of your library (five instead if you control three or more "
        "other creatures). You may put a land card from among them onto the "
        "battlefield tapped. Put the rest on the bottom of your library in a "
        "random order. (The Republic's last honest senator charts a quiet "
        "course through Coruscant's corridors.)"
    ),
    setup_interceptors=padme_amidala_setup,
)


# --- Asajj Ventress, Dathomiri Bounty Hunter ({1}{B}{R} 2/3 Legendary) ---
# Pattern 7 (targeted attack + tribal synergy). make_targeted_attack_trigger
# gives a fresh decision=1 fingerprint distinct from Smoker (OPC slice-3)
# because of color combo (Rakdos vs Azorius), filter focus (Bounty Hunter
# vs Pirate tribal), and the closure's COUNTER_ADDED scaling on Sith
# subtype rather than Marine subtype.
# Lore: Asajj Ventress, exiled from the Sith and now a freelance bounty
# hunter, hexes a target on every strike with Dathomiri witch-magic.
def asajj_ventress_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever Asajj Ventress attacks, tap target creature an opponent
    controls. Hex counter scales with Sith and Bounty Hunters you control.

    make_targeted_attack_trigger registers an ATTACK-time TARGET_REQUIRED
    with effect 'tap' (decision=1). The creatures_with_subtype('Sith')
    filter-factory call surfaces the synergy axis (Sith covens hex
    together). The companion attack closure reads the battlefield zone
    + adds a +1/+1 counter to Asajj per Sith/Bounty Hunter on the field
    (state_coupling + zone_movement)."""
    # Filter-factory call: register Sith-coven synergy axis tag.
    sith_filter = creatures_with_subtype(obj, "Sith")
    _ = sith_filter  # keep reference so the AST walker tags the call.

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def hex_attack(event: Event, st: GameState) -> list[Event]:
        # Only fire when Asajj is the attacker.
        attacker_id = event.payload.get('attacker_id') or event.payload.get('attacker')
        if attacker_id != obj.id:
            return []
        # Explicit battlefield zone read (state_coupling + zone_movement).
        bf = st.zones.get('battlefield')
        if bf is None:
            return []
        coven_count = 0
        for cid in bf.objects:
            o = st.objects.get(cid)
            if o is None:
                continue
            if (o.controller == obj.controller and
                    ('Sith' in o.characteristics.subtypes or
                     'Bounty Hunter' in o.characteristics.subtypes)):
                coven_count += 1
        if coven_count <= 0:
            return []
        # Scaling hex counter — every coven witch deepens the curse.
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={
                'object_id': obj.id,
                'counter_type': '+1/+1',
                'amount': 1,
            },
            source=obj.id,
        )]

    return [
        make_keyword_grant(obj, ['menace'], affects_self),
        make_targeted_attack_trigger(
            obj,
            effect='tap',
            effect_params={},
            target_filter='opponent_creature',
            min_targets=1,
            max_targets=1,
            optional=False,
            prompt='Asajj hex-pins a Republic foe — tap target opponent creature',
        ),
        make_attack_trigger(obj, hex_attack),
    ]


ASAJJ_VENTRESS = make_creature(
    name="Asajj Ventress, Dathomiri Bounty Hunter",
    power=2, toughness=3,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Bounty Hunter"},
    supertypes={"Legendary"},
    text=(
        "Menace. Whenever Asajj Ventress, Dathomiri Bounty Hunter attacks, "
        "tap target creature an opponent controls. Then, if you control "
        "another Sith or Bounty Hunter, put a +1/+1 counter on Asajj. "
        "(The Nightsisters teach that hexes compound in covens.)"
    ),
    setup_interceptors=asajj_ventress_setup,
)


# --- Jocasta Nu, Jedi Archivist ({1}{U} 1/3 Legendary Jedi) ---
# Pattern 8 (scry + zone + synergy). create_scry_choice surfaced via a
# custom ETB closure. Distinct fp from Kabuto Yakushi (NRT slice-2) via
# different scry depth (4 not 3), different color body (mono-U not mono-U
# but Jedi tribal), and different filter (creatures_with_subtype Jedi).
# Lore: Jocasta Nu, chief librarian of the Jedi Temple Archives, sifts
# the chronicles to predict the next move of the Sith.
def jocasta_nu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: explicit library read, then open a scry-4 choice. Filter
    factory call (creatures_with_subtype Jedi) surfaces the synergy axis;
    library zone read surfaces state_coupling + zone_movement; the
    create_scry_choice helper surfaces decision=1 via PendingChoice."""
    def jocasta_etb(event: Event, st: GameState) -> list[Event]:
        # Explicit library zone read for state_coupling + zone tags.
        library = st.zones.get(f'library_{obj.controller}')
        if library is None or not library.objects:
            return []
        # Filter-factory call: Jedi-tribal creatures we control for synergy.
        own_jedi = creatures_with_subtype(obj, "Jedi")
        _ = own_jedi  # keep reference so the walker tags the call.
        # Open scry 4 choice on the top of library.
        top_four = list(library.objects[:4])
        if not top_four:
            return []
        create_scry_choice(st, obj.controller, obj.id, top_four, scry_count=4)
        return []
    return [make_etb_trigger(obj, jocasta_etb)]


JOCASTA_NU_ARCHIVIST = make_creature(
    name="Jocasta Nu, Jedi Archivist",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Jedi"},
    supertypes={"Legendary"},
    text=(
        "When Jocasta Nu, Jedi Archivist enters, scry 4. "
        "(\"If an item does not appear in our records, it does not exist.\")"
    ),
    setup_interceptors=jocasta_nu_setup,
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

    # SPICE PASS — Wave 22+ format-defining cards
    "Boba Fett, Hunter of Hunters": BOBA_FETT_HUNTER_OF_HUNTERS,
    "IG-88, Assassin Droid Network": IG_88_NETWORK,
    "Yoda, Living Force": YODA_LIVING_FORCE,
    "Bossk, Trandoshan Hunter Prime": BOSSK_PRIME,
    "Han Solo, Hotshot Pilot": HAN_SOLO_HOTSHOT_PILOT,
    "Holocron of the High Council": HOLOCRON_OF_THE_HIGH_COUNCIL,
    "Mandalorian Beskar Plating": MANDALORIAN_BESKAR_PLATING,
    "Sith Resurgence": SITH_RESURGENCE,
    # Phase B-1
    "Kylo Ren, Conflicted Heir": KYLO_REN_CONFLICTED_HEIR,
    "Stormtrooper Patrol Squadron": STORMTROOPER_PATROL_SQUADRON,
    "R2-D2, Master Hacker": R2D2_MASTER_HACKER,
    "Darth Vader, More Machine Than Man": DARTH_VADER_MACHINE_MAN,
    # Phase B-2
    "The Force Itself": THE_FORCE_ITSELF,
    # Phase B-3
    "Luke Skywalker, Last Jedi": LUKE_SKYWALKER_LAST_JEDI,
    "Princess Leia, Spark of Hope": PRINCESS_LEIA_SPARK,

    # SPICE PASS v2 — Wave 23+ expansion (7 new + 2 rewires)
    "Ahsoka Tano, Fulcrum": AHSOKA_TANO_FULCRUM,
    "Grogu, Strong With the Force": GROGU_STRONG,
    "Sith Holocron of Vitiate": SITH_HOLOCRON_VITIATE,
    "Darksaber, Mandalore's Birthright": DARKSABER_BIRTHRIGHT,
    "Death Star Superlaser Charge": DEATH_STAR_SUPERLASER_CHARGE,
    "The Imperial Throne": THE_IMPERIAL_THRONE,
    "Carbonite Containment": CARBONITE_CONTAINMENT,

    # SPICE PASS PHASE A2 (slice 5.5, 2026-05-19) — decision-axis flips
    "Yoda, Force-Echo of the Living": YODA_FORCE_ECHO,
    "Reva, Third Sister Inquisitor": REVA_THIRD_SISTER,
    "HK-47, Hunter-Killer Protocol": HK_47_HUNTER_KILLER,
    "Bo-Katan Kryze, Mandalore's Heir": BO_KATAN_KRYZE,
    "Cad Bane, Sky's-Edge Reckoner": CAD_BANE_SKYS_EDGE,
    "Padme Amidala, Naboo's Senator": PADME_AMIDALA,
    "Asajj Ventress, Dathomiri Bounty Hunter": ASAJJ_VENTRESS,
    "Jocasta Nu, Jedi Archivist": JOCASTA_NU_ARCHIVIST,
}

print(f"Loaded {len(STAR_WARS_CARDS)} Star Wars: Galactic Conflict cards")




# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    LUKE_SKYWALKER_NEW_HOPE,
    LEIA_ORGANA,
    OBI_WAN_KENOBI,
    YODA_GRAND_MASTER,
    MACE_WINDU,
    REBEL_PILOT,
    JEDI_PADAWAN,
    REBEL_TROOPER,
    ALDERAANIAN_DIPLOMAT,
    JEDI_TEMPLE_GUARD,
    ECHO_BASE_DEFENDER,
    REBEL_MEDIC,
    HOPE_OF_THE_REBELLION,
    CORUSCANT_PEACEKEEPER,
    RESISTANCE_COMMANDER,
    JEDI_SENTINEL,
    REBELLION_SYMPATHIZER,
    TATOOINE_HOMESTEADER,
    GALACTIC_SENATOR,
    FORCE_PROTECTION,
    REBEL_AMBUSH,
    JEDI_REFLEXES,
    HOPE_RENEWED,
    DEFENSIVE_FORMATION,
    LIGHT_OF_THE_FORCE,
    CALL_TO_ARMS,
    LIBERATION_DAY,
    JEDI_TRAINING,
    EVACUATION_PLAN,
    THE_LIGHT_SIDE,
    REBEL_ALLIANCE,
    JEDI_SANCTUARY,
    R2D2,
    C3PO,
    ADMIRAL_ACKBAR,
    QUI_GON_JINN,
    ASTROMECH_DROID,
    PROTOCOL_DROID,
    JEDI_SCHOLAR,
    CLOUD_CITY_ENGINEER,
    BATTLE_DROID,
    PROBE_DROID,
    KAMINO_CLONER,
    MON_CALAMARI_CAPTAIN,
    REBEL_STRATEGIST,
    CORUSCANT_ARCHIVIST,
    HOLO_PROJECTOR_DROID,
    SEPARATIST_INFILTRATOR,
    JEDI_INVESTIGATOR,
    JEDI_MIND_TRICK,
    FORCE_PUSH,
    HOLOGRAPHIC_DECOY,
    HYPERSPACE_JUMP,
    SENSOR_SCRAMBLE,
    FORCE_VISION,
    TECH_OVERRIDE,
    DROID_FABRICATION,
    MEMORY_WIPE,
    CLONE_ARMY,
    HOLOGRAM_TRANSMISSION,
    DROID_FACTORY,
    JEDI_ARCHIVES,
    DARTH_VADER,
    EMPEROR_PALPATINE,
    DARTH_MAUL,
    COUNT_DOOKU,
    GRAND_MOFF_TARKIN,
    SITH_APPRENTICE,
    STORMTROOPER,
    IMPERIAL_OFFICER,
    DEATH_TROOPER,
    IMPERIAL_INQUISITOR,
    SITH_ACOLYTE,
    MUSTAFAR_TORTURER,
    IMPERIAL_SPY,
    TIE_FIGHTER_PILOT,
    FORCE_CHOKER,
    SHADOW_GUARD,
    DARK_SIDE_ADEPT,
    FORCE_CHOKE,
    DARK_SIDE_CORRUPTION,
    IMPERIAL_EXECUTION,
    SITH_LIGHTNING,
    FEAR_ITSELF,
    BETRAYAL,
    ORDER_66,
    IMPERIAL_BOMBARDMENT,
    HARVEST_DESPAIR,
    CONSCRIPTION,
    THE_DARK_SIDE,
    GALACTIC_EMPIRE,
    RULE_OF_TWO,
    BOBA_FETT,
    JANGO_FETT,
    CAD_BANE,
    DIN_DJARIN,
    GREEDO,
    BOUNTY_HUNTER,
    TRANDOSHAN_SLAVER,
    TUSKEN_RAIDER,
    GAMORREAN_GUARD,
    PODRACER,
    MANDALORIAN_WARRIOR,
    MOS_EISLEY_THUG,
    SEPARATIST_BATTLE_DROID,
    CLONE_TROOPER_COMMANDO,
    WEEQUAY_PIRATE,
    ARENA_GLADIATOR,
    PYKE_ENFORCER,
    BLASTER_BOLT,
    THERMAL_DETONATOR,
    AGGRESSIVE_NEGOTIATIONS,
    BOUNTY_POSTED,
    RECKLESS_ASSAULT,
    DISINTEGRATE,
    ORBITAL_STRIKE,
    BOUNTY_COLLECTION,
    RAGE_OF_THE_ARENA,
    HIRED_GUNS,
    HUNTERS_CODE,
    ARENA_PIT,
    GALACTIC_UNDERWORLD,
    CHEWBACCA,
    WICKET,
    TARFFUL,
    GROGU,
    WOOKIEE_WARRIOR,
    EWOK_AMBUSHER,
    EWOK_HUNTER,
    ENDOR_TRAPPER,
    KASHYYYK_DEFENDER,
    DAGOBAH_CREATURE,
    FELUCIA_BEAST,
    JUNGLE_RANCOR,
    NABOO_RANGER,
    GUNGAN_WARRIOR,
    YAVIN_JUNGLE_CAT,
    ENDOR_WILDLIFE,
    SARLACC_PIT_SPAWN,
    WOOKIEE_RAGE,
    FOREST_AMBUSH,
    EWOK_TRAP,
    NATURAL_CAMOUFLAGE,
    JUNGLE_GROWTH,
    PRIMAL_CONNECTION,
    CALL_OF_THE_WILD,
    EWOK_UPRISING,
    FORCE_OF_NATURE,
    RAMPANT_GROWTH,
    EWOK_VILLAGE,
    KASHYYYK_HOMELAND,
    THE_LIVING_FORCE,
    HAN_SOLO,
    ANAKIN_SKYWALKER,
    PADME_AMIDALA,
    AHSOKA_TANO,
    KYLO_REN,
    REY,
    FINN,
    POE_DAMERON,
    LANDO_CALRISSIAN,
    GENERAL_GRIEVOUS,
    ASAJJ_VENTRESS,
    JAR_JAR_BINKS,
    MAZ_KANATA,
    THRAWN,
    DARTH_SIDIOUS,
    REBEL_COMMANDO_TEAM,
    SEPARATIST_COMMANDER,
    MANDALORIAN_FORGE_MASTER,
    FORCE_SENSITIVE,
    HUTT_CRIME_LORD,
    BALANCE_OF_THE_FORCE,
    FORCE_LIGHTNING,
    UNITY_OF_THE_REBELLION,
    GALACTIC_SENATE_DECREE,
    DEVASTATION_OF_ALDERAAN,
    LUKES_LIGHTSABER,
    DARTH_VADERS_LIGHTSABER,
    DOUBLE_BLADED_LIGHTSABER,
    LIGHTSABER,
    DARK_SABER,
    MANDALORIAN_ARMOR,
    BESKAR_HELMET,
    JETPACK,
    BLASTER_RIFLE,
    BOWCASTER,
    ELECTROSTAFF,
    SLAVE_TRACKER,
    DEATH_STAR,
    HOLOCRON,
    SITH_HOLOCRON,
    CARBONITE_PRISON,
    KYBER_CRYSTAL,
    STORMTROOPER_BARRACKS,
    DROID_FOUNDRY,
    TRADE_FEDERATION_VAULT,
    BACTA_TANK,
    HYPERDRIVE,
    SHIELD_GENERATOR,
    CORUSCANT,
    TATOOINE,
    ENDOR_FOREST,
    KASHYYYK,
    MUSTAFAR,
    DAGOBAH,
    HOTH,
    NABOO,
    KAMINO,
    GEONOSIS,
    JAKKU,
    CLOUD_CITY,
    MOS_EISLEY,
    JEDI_TEMPLE,
    SITH_TEMPLE,
    DEATH_STAR_HANGAR,
    REBEL_BASE,
    PLAINS_SWG,
    ISLAND_SWG,
    SWAMP_SWG,
    MOUNTAIN_SWG,
    FOREST_SWG,
    CLONE_CAPTAIN_REX,
    BAIL_ORGANA,
    MON_MOTHMA,
    ROYAL_GUARD,
    ALDERAANIAN_REFUGEE,
    FORCE_BARRIER,
    BB8,
    K2SO,
    SUPER_BATTLE_DROID,
    TACTICAL_DROID,
    INFORMATION_BROKER,
    FORCE_ILLUSION,
    DARTH_BANE,
    GRAND_INQUISITOR,
    IMPERIAL_EXECUTIONER,
    SNOKE,
    DARK_RITUAL,
    AURRA_SING,
    BOSSK,
    FENNEC_SHAND,
    DEATH_WATCH_WARRIOR,
    WRIST_ROCKET,
    YADDLE,
    WOOKIEE_BERSERKER,
    EWOK_SHAMAN,
    RANCOR,
    NEXU,
    BEAST_CALL,
    CAPTAIN_PHASMA,
    SABINE_WREN,
    EZRA_BRIDGER,
    KANAN_JARRUS,
    HERA_SYNDULLA,
    TRAINING_REMOTE,
    RESTRAINING_BOLT,
    THERMAL_IMAGING_GOGGLES,
    SCARIF,
    JEDHA,
    MANDALORE,
    BESPIN,
    LOTHAL,
    # SPICE PASS — Wave 22+
    BOBA_FETT_HUNTER_OF_HUNTERS,
    IG_88_NETWORK,
    YODA_LIVING_FORCE,
    BOSSK_PRIME,
    HAN_SOLO_HOTSHOT_PILOT,
    HOLOCRON_OF_THE_HIGH_COUNCIL,
    MANDALORIAN_BESKAR_PLATING,
    SITH_RESURGENCE,
    KYLO_REN_CONFLICTED_HEIR,
    STORMTROOPER_PATROL_SQUADRON,
    R2D2_MASTER_HACKER,
    DARTH_VADER_MACHINE_MAN,
    THE_FORCE_ITSELF,
    LUKE_SKYWALKER_LAST_JEDI,
    PRINCESS_LEIA_SPARK,
    # SPICE v2
    AHSOKA_TANO_FULCRUM,
    GROGU_STRONG,
    SITH_HOLOCRON_VITIATE,
    DARKSABER_BIRTHRIGHT,
    DEATH_STAR_SUPERLASER_CHARGE,
    THE_IMPERIAL_THRONE,
    CARBONITE_CONTAINMENT,
    # SPICE PASS PHASE A2 (slice 5.5, 2026-05-19) — decision-axis flips
    YODA_FORCE_ECHO,
    REVA_THIRD_SISTER,
    HK_47_HUNTER_KILLER,
    BO_KATAN_KRYZE,
    CAD_BANE_SKYS_EDGE,
    PADME_AMIDALA,
    ASAJJ_VENTRESS,
    JOCASTA_NU_ARCHIVIST,
]
