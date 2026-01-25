"""
Bloomburrow (BLB) Card Implementations

Set released August 2024. ~250 cards.
Features mechanics: Valiant, Offspring, Gift, Forage, Expend
Creature types: Mice, Rabbits, Birds, Frogs, Lizards, Bats, Raccoons, Otters, Squirrels
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


def make_aura(name: str, mana_cost: str, colors: set, text: str, setup_interceptors=None):
    """Helper to create aura enchantment card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT},
            subtypes={"Aura"},
            colors=colors,
            mana_cost=mana_cost
        ),
        text=text,
        setup_interceptors=setup_interceptors
    )


# =============================================================================
# BLOOMBURROW KEYWORD MECHANICS
# =============================================================================

def make_valiant_trigger(source_obj: GameObject, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Valiant - Whenever this creature becomes the target of a spell or ability you control,
    trigger the effect. Only triggers once per targeting event.
    """
    def valiant_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.TARGET:
            return False
        if event.payload.get('target_id') != source_obj.id:
            return False
        # Must be controlled by this creature's controller
        caster = event.payload.get('controller')
        return caster == source_obj.controller

    def valiant_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=valiant_filter,
        handler=valiant_handler,
        duration='while_on_battlefield'
    )


def make_offspring_etb(source_obj: GameObject, base_power: int, base_toughness: int) -> Interceptor:
    """
    Offspring - If offspring cost was paid, create a 1/1 token copy of this creature.
    Check for 'offspring_paid' flag in the ETB event.
    """
    def offspring_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        return event.payload.get('offspring_paid', False)

    def offspring_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': source_obj.controller,
                'token': {
                    'name': f"{source_obj.characteristics.name} Token",
                    'power': 1,
                    'toughness': 1,
                    'colors': source_obj.characteristics.colors,
                    'subtypes': source_obj.characteristics.subtypes,
                    'is_copy': True
                }
            },
            source=source_obj.id
        )]

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: offspring_filter(e, s, source_obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=offspring_effect(e, s)),
        duration='while_on_battlefield'
    )


def make_gift_trigger(source_obj: GameObject, gift_effect: Callable[[Event, GameState], list[Event]], bonus_effect: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Gift - When this enters, you may give an opponent something (gift_effect).
    If you do, bonus_effect triggers.
    """
    def gift_filter(event: Event, state: GameState, obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        return event.payload.get('gift_given', False)

    def gift_handler(event: Event, state: GameState) -> InterceptorResult:
        gift_events = gift_effect(event, state)
        bonus_events = bonus_effect(event, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=gift_events + bonus_events)

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: gift_filter(e, s, source_obj),
        handler=gift_handler,
        duration='while_on_battlefield'
    )


def make_forage_trigger(source_obj: GameObject, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Forage - Exile three cards from your graveyard or sacrifice a Food.
    If you do, trigger the effect.
    """
    def forage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ACTIVATE:
            return False
        return (event.payload.get('source') == source_obj.id and
                event.payload.get('ability') == 'forage' and
                event.payload.get('forage_paid', False))

    def forage_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=forage_filter,
        handler=forage_handler,
        duration='while_on_battlefield'
    )


def make_expend_trigger(source_obj: GameObject, threshold: int, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Expend N - Whenever you spend N or more mana to cast a spell, trigger the effect.
    """
    def expend_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source_obj.controller:
            return False
        mana_spent = event.payload.get('mana_spent', 0)
        return mana_spent >= threshold

    def expend_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=expend_filter,
        handler=expend_handler,
        duration='while_on_battlefield'
    )


# Creature type filters
def mouse_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Mouse")

def rabbit_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Rabbit")

def bird_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Bird")

def frog_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Frog")

def lizard_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Lizard")

def bat_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Bat")

def raccoon_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Raccoon")

def otter_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Otter")

def squirrel_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, "Squirrel")


# =============================================================================
# WHITE CARDS - MICE, RABBITS, COMMUNITY
# =============================================================================

# --- Legendary Creatures ---

def mabel_heir_to_cragflame_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Mice get +1/+1 and have vigilance. When Mabel attacks, equip a free equipment."""
    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Mouse")))
    interceptors.append(make_keyword_grant(obj, ['vigilance'], other_creatures_with_subtype(obj, "Mouse")))

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.EQUIP_FREE,
            payload={'controller': obj.controller, 'attacker_id': obj.id},
            source=obj.id
        )]
    interceptors.append(make_attack_trigger(obj, attack_effect))
    return interceptors

MABEL_HEIR_TO_CRAGFLAME = make_creature(
    name="Mabel, Heir to Cragflame",
    power=3, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Mouse", "Knight"},
    supertypes={"Legendary"},
    text="Vigilance. Other Mouse creatures you control get +1/+1 and have vigilance. Whenever Mabel attacks, you may attach target Equipment you control to target creature you control.",
    setup_interceptors=mabel_heir_to_cragflame_setup
)


def finneas_ace_archer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach. Whenever you draw second card each turn, put +1/+1 counter on target creature."""
    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'target_type': 'creature', 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    # Track second draw each turn
    def second_draw_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DRAW:
            return False
        if event.payload.get('player') != obj.controller:
            return False
        # Check if this is the second draw this turn
        return event.payload.get('draw_count_this_turn', 0) == 2

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=second_draw_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=draw_effect(e, s)),
        duration='while_on_battlefield'
    )]

FINNEAS_ACE_ARCHER = make_creature(
    name="Finneas, Ace Archer",
    power=2, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Rabbit", "Archer"},
    supertypes={"Legendary"},
    text="Reach. Whenever you draw your second card each turn, put a +1/+1 counter on target creature you control.",
    setup_interceptors=finneas_ace_archer_setup
)


def hugs_grisly_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you gain life, put that many +1/+1 counters on Hugs."""
    def life_gain_effect(event: Event, state: GameState) -> list[Event]:
        amount = event.payload.get('amount', 0)
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': amount},
            source=obj.id
        )]
    return [make_life_gain_trigger(obj, life_gain_effect)]

HUGS_GRISLY_GUARDIAN = make_creature(
    name="Hugs, Grisly Guardian",
    power=2, toughness=2,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Badger", "Warrior"},
    supertypes={"Legendary"},
    text="Lifelink. Whenever you gain life, put that many +1/+1 counters on Hugs, Grisly Guardian.",
    setup_interceptors=hugs_grisly_guardian_setup
)


def zoraline_cosmos_caller_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Bats get +1/+1. Whenever a Bat you control attacks, you gain 1 life and scry 1."""
    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Bat")))

    def bat_attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        return (attacker.controller == obj.controller and
                "Bat" in attacker.characteristics.subtypes)

    def bat_attack_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=bat_attack_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=bat_attack_effect(e, s)),
        duration='while_on_battlefield'
    ))
    return interceptors

ZORALINE_COSMOS_CALLER = make_creature(
    name="Zoraline, Cosmos Caller",
    power=2, toughness=3,
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Bat", "Cleric"},
    supertypes={"Legendary"},
    text="Flying, lifelink. Other Bat creatures you control get +1/+1. Whenever a Bat you control attacks, you gain 1 life and scry 1.",
    setup_interceptors=zoraline_cosmos_caller_setup
)


def ygra_eater_of_all_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Ygra ETB, create 3 Food tokens. Whenever a Food is sacrificed, put +1/+1 counter on Ygra."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {'name': 'Food', 'types': ['Artifact'], 'subtypes': {'Food'}},
                'count': 3
            },
            source=obj.id
        )]

    def food_sac_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        if event.payload.get('cause') != 'sacrifice':
            return False
        sacrificed_id = event.payload.get('object_id')
        sacrificed = state.objects.get(sacrificed_id)
        if not sacrificed:
            return False
        return "Food" in sacrificed.characteristics.subtypes

    def food_sac_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [
        make_etb_trigger(obj, etb_effect),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=food_sac_filter,
            handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=food_sac_effect(e, s)),
            duration='while_on_battlefield'
        )
    ]

YGRA_EATER_OF_ALL = make_creature(
    name="Ygra, Eater of All",
    power=3, toughness=3,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Cat", "Horror"},
    supertypes={"Legendary"},
    text="When Ygra, Eater of All enters, create three Food tokens. Whenever a Food is sacrificed, put a +1/+1 counter on Ygra.",
    setup_interceptors=ygra_eater_of_all_setup
)


# --- Season Elders (Mythic Rare Cycle) ---

def valley_mightcaller_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vigilance. When ETB, creatures get +2/+2 until end of turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.BUFF,
            payload={'target': 'creatures_you_control', 'power': 2, 'toughness': 2, 'duration': 'end_of_turn'},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

VALLEY_MIGHTCALLER = make_creature(
    name="Valley Mightcaller",
    power=4, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental", "Elk"},
    text="Vigilance. When Valley Mightcaller enters, creatures you control get +2/+2 until end of turn.",
    setup_interceptors=valley_mightcaller_setup
)


def oakhame_stormguard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flash. Flying. When ETB, tap up to two creatures."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.TAP_TARGET, payload={'count': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

OAKHAME_STORMGUARD = make_creature(
    name="Oakhame Stormguard",
    power=3, toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Bird"},
    text="Flash, flying. When Oakhame Stormguard enters, tap up to two target creatures.",
    setup_interceptors=oakhame_stormguard_setup
)


def sungrass_elder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, gain 5 life. When dies, gain 5 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 5}, source=obj.id)]
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 5}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect), make_death_trigger(obj, death_effect)]

SUNGRASS_ELDER = make_creature(
    name="Sungrass Elder",
    power=4, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Elemental", "Rabbit"},
    text="When Sungrass Elder enters, you gain 5 life. When Sungrass Elder dies, you gain 5 life.",
    setup_interceptors=sungrass_elder_setup
)


def shadowfire_elder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, each opponent loses 3 life and you gain that much life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        opponents = all_opponents(obj, state)
        life_gained = 0
        for opp_id in opponents:
            events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': opp_id, 'amount': -3}, source=obj.id))
            life_gained += 3
        events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': life_gained}, source=obj.id))
        return events
    return [make_etb_trigger(obj, etb_effect)]

SHADOWFIRE_ELDER = make_creature(
    name="Shadowfire Elder",
    power=4, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Elemental", "Bat"},
    text="When Shadowfire Elder enters, each opponent loses 3 life and you gain life equal to the life lost this way.",
    setup_interceptors=shadowfire_elder_setup
)


def blazeborn_elder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste. When ETB, deal 4 damage to any target."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={'amount': 4, 'target_type': 'any'}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

BLAZEBORN_ELDER = make_creature(
    name="Blazeborn Elder",
    power=4, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Lizard"},
    text="Haste. When Blazeborn Elder enters, it deals 4 damage to any target.",
    setup_interceptors=blazeborn_elder_setup
)


# --- White Creatures ---

def star_charterer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Valiant - put a +1/+1 counter on this creature."""
    def valiant_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1}, source=obj.id)]
    return [make_valiant_trigger(obj, valiant_effect)]

STAR_CHARTERER = make_creature(
    name="Star Charterer",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Mouse", "Scout"},
    text="Valiant - Whenever Star Charterer becomes the target of a spell or ability you control, put a +1/+1 counter on it.",
    setup_interceptors=star_charterer_setup
)


def warren_wardens_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, create two 1/1 white Rabbit creature tokens."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Rabbit', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE}, 'subtypes': {'Rabbit'}}
            }, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Rabbit', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE}, 'subtypes': {'Rabbit'}}
            }, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

WARREN_WARDENS = make_creature(
    name="Warren Wardens",
    power=2, toughness=2,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Rabbit", "Soldier"},
    text="When Warren Wardens enters, create two 1/1 white Rabbit creature tokens.",
    setup_interceptors=warren_wardens_setup
)


def carrot_cake_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, create a Food and a 1/1 white Rabbit token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Food', 'types': ['Artifact'], 'subtypes': {'Food'}}
            }, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Rabbit', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE}, 'subtypes': {'Rabbit'}}
            }, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

CARROT_CAKE = make_artifact(
    name="Carrot Cake",
    mana_cost="{1}{W}",
    text="When Carrot Cake enters, create a Food token and a 1/1 white Rabbit creature token.",
    setup_interceptors=carrot_cake_setup
)


def plumecreed_mentor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Birds you control get +1/+1."""
    return make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Bird"))

PLUMECREED_MENTOR = make_creature(
    name="Plumecreed Mentor",
    power=2, toughness=2,
    mana_cost="{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Bird", "Cleric"},
    text="Flying. Other Bird creatures you control get +1/+1.",
    setup_interceptors=plumecreed_mentor_setup
)


MOUSE_TRAPPER = make_creature(
    name="Mouse Trapper",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Mouse", "Soldier"},
    text="First strike. When Mouse Trapper dies, exile target creature with power 2 or less."
)


def pearl_of_wisdom_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Valiant - draw a card."""
    def valiant_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_valiant_trigger(obj, valiant_effect)]

PEARL_OF_WISDOM = make_creature(
    name="Pearl of Wisdom",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Mouse", "Wizard"},
    text="Vigilance. Valiant - Whenever Pearl of Wisdom becomes the target of a spell or ability you control, draw a card.",
    setup_interceptors=pearl_of_wisdom_setup
)


BRAVE_BURROW_WATCHER = make_creature(
    name="Brave Burrow-Watcher",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Mouse", "Soldier"},
    text="Vigilance. Offspring {2} (You may pay an additional {2} as you cast this spell. If you do, when this creature enters, create a 1/1 copy of it.)"
)


HEARTFIRE_HERO = make_creature(
    name="Heartfire Hero",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Mouse", "Warrior"},
    text="When Heartfire Hero dies, target creature gets +X/+X until end of turn, where X is Heartfire Hero's power."
)


def seedpod_squire_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, put a +1/+1 counter on another creature you control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'target_type': 'other_creature', 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

SEEDPOD_SQUIRE = make_creature(
    name="Seedpod Squire",
    power=1, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Squirrel", "Soldier"},
    text="When Seedpod Squire enters, put a +1/+1 counter on another target creature you control.",
    setup_interceptors=seedpod_squire_setup
)


VALLEY_QUESTCALLER = make_creature(
    name="Valley Questcaller",
    power=2, toughness=2,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Rabbit", "Knight"},
    text="Vigilance. Other creatures you control have vigilance."
)


def lifecreed_duo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you gain life, each opponent loses 1 life."""
    def life_gain_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': opp_id, 'amount': -1}, source=obj.id))
        return events
    return [make_life_gain_trigger(obj, life_gain_effect)]

LIFECREED_DUO = make_creature(
    name="Lifecreed Duo",
    power=3, toughness=3,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Bat", "Cleric"},
    text="Flying, lifelink. Whenever you gain life, each opponent loses 1 life.",
    setup_interceptors=lifecreed_duo_setup
)


# =============================================================================
# BLUE CARDS - BIRDS, FROGS, KNOWLEDGE
# =============================================================================

def stormchaser_hawk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Valiant - tap target creature."""
    def valiant_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.TAP_TARGET, payload={'count': 1}, source=obj.id)]
    return [make_valiant_trigger(obj, valiant_effect)]

STORMCHASER_HAWK = make_creature(
    name="Stormchaser Hawk",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Scout"},
    text="Flying. Valiant - Whenever Stormchaser Hawk becomes the target of a spell or ability you control, tap target creature.",
    setup_interceptors=stormchaser_hawk_setup
)


def festival_frog_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, scry 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

FESTIVAL_FROG = make_creature(
    name="Festival Frog",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Frog", "Bard"},
    text="When Festival Frog enters, scry 2.",
    setup_interceptors=festival_frog_setup
)


def dreadmaw_hatchling_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, draw a card if you control another Frog."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Check for other Frogs
        for obj_id, other in state.objects.items():
            if (obj_id != obj.id and
                other.controller == obj.controller and
                other.zone == ZoneType.BATTLEFIELD and
                "Frog" in other.characteristics.subtypes):
                return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
        return []
    return [make_etb_trigger(obj, etb_effect)]

DREADMAW_HATCHLING = make_creature(
    name="Dreadmaw Hatchling",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Frog", "Wizard"},
    text="When Dreadmaw Hatchling enters, if you control another Frog, draw a card.",
    setup_interceptors=dreadmaw_hatchling_setup
)


KEEN_EYED_CURATOR = make_creature(
    name="Keen-Eyed Curator",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Advisor"},
    text="Flying. {T}: Look at the top card of your library. You may put it into your graveyard."
)


def thought_stalker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When deals combat damage to player, draw a card."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

THOUGHT_STALKER = make_creature(
    name="Thought Stalker",
    power=2, toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Rogue"},
    text="Flying. Whenever Thought Stalker deals combat damage to a player, draw a card.",
    setup_interceptors=thought_stalker_setup
)


SPLASH_PORTAL = make_creature(
    name="Splash Portal",
    power=0, toughness=4,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Frog", "Wizard"},
    text="Defender. {T}: Add {U}. Spend this mana only to cast instant or sorcery spells."
)


def skyskipper_duo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, draw two cards then discard a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 2}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

SKYSKIPPER_DUO = make_creature(
    name="Skyskipper Duo",
    power=3, toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Scout"},
    text="Flying. When Skyskipper Duo enters, draw two cards, then discard a card.",
    setup_interceptors=skyskipper_duo_setup
)


def pond_prophet_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At upkeep, scry 1."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect)]

POND_PROPHET = make_creature(
    name="Pond Prophet",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Frog", "Druid"},
    text="At the beginning of your upkeep, scry 1.",
    setup_interceptors=pond_prophet_setup
)


VANTRESS_TRANSMUTER = make_creature(
    name="Vantress Transmuter",
    power=3, toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Frog", "Wizard"},
    text="Flash. When Vantress Transmuter enters, return target creature to its owner's hand."
)


WINDREADER_OWL = make_creature(
    name="Windreader Owl",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Wizard"},
    text="Flying. When Windreader Owl enters, surveil 2."
)


# =============================================================================
# BLACK CARDS - BATS, RATS, SHADOWS
# =============================================================================

def dusk_hunter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When deals combat damage, opponent discards a card."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target_player = event.payload.get('target')
        if target_player:
            return [Event(type=EventType.DISCARD, payload={'player': target_player, 'amount': 1}, source=obj.id)]
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

DUSK_HUNTER = make_creature(
    name="Dusk Hunter",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "Rogue"},
    text="Flying. Whenever Dusk Hunter deals combat damage to a player, that player discards a card.",
    setup_interceptors=dusk_hunter_setup
)


def nettling_nuisance_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, create a 1/1 black Bat token with flying."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Bat', 'power': 1, 'toughness': 1, 'colors': {Color.BLACK}, 'subtypes': {'Bat'}, 'keywords': ['flying']}
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

NETTLING_NUISANCE = make_creature(
    name="Nettling Nuisance",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "Rogue"},
    text="Flying. When Nettling Nuisance enters, create a 1/1 black Bat creature token with flying.",
    setup_interceptors=nettling_nuisance_setup
)


def moonlit_stalker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When another creature you control dies, each opponent loses 1 life."""
    def death_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dead_id = event.payload.get('object_id')
        if dead_id == obj.id:
            return False
        dead = state.objects.get(dead_id)
        if not dead:
            return False
        return (dead.controller == obj.controller and
                CardType.CREATURE in dead.characteristics.types)

    def death_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for opp_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': opp_id, 'amount': -1}, source=obj.id))
        return events

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=death_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=death_effect(e, s)),
        duration='while_on_battlefield'
    )]

MOONLIT_STALKER = make_creature(
    name="Moonlit Stalker",
    power=3, toughness=2,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "Assassin"},
    text="Flying. Whenever another creature you control dies, each opponent loses 1 life.",
    setup_interceptors=moonlit_stalker_setup
)


def persistent_packrat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, create a Food token."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Food', 'types': ['Artifact'], 'subtypes': {'Food'}}
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

PERSISTENT_PACKRAT = make_creature(
    name="Persistent Packrat",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rat", "Rogue"},
    text="Whenever Persistent Packrat attacks, create a Food token.",
    setup_interceptors=persistent_packrat_setup
)


MIDNIGHT_TRICKSTER = make_creature(
    name="Midnight Trickster",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "Warlock"},
    text="Flying. When Midnight Trickster dies, target opponent loses 2 life."
)


def bog_creeper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, destroy target creature with mana value 2 or less."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DESTROY, payload={'target_type': 'creature_mv_2_or_less'}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

BOG_CREEPER = make_creature(
    name="Bog Creeper",
    power=2, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Frog", "Horror"},
    text="Menace. When Bog Creeper enters, destroy target creature with mana value 2 or less.",
    setup_interceptors=bog_creeper_setup
)


CARRION_FEASTER = make_creature(
    name="Carrion Feaster",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "Warrior"},
    text="Flying. Forage - {B}, Exile three cards from your graveyard or sacrifice a Food: Put a +1/+1 counter on Carrion Feaster."
)


def shadow_prowler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Forage - Draw a card."""
    def forage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_forage_trigger(obj, forage_effect)]

SHADOW_PROWLER = make_creature(
    name="Shadow Prowler",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rat", "Rogue"},
    text="Menace. Forage - Exile three cards from your graveyard or sacrifice a Food: Draw a card.",
    setup_interceptors=shadow_prowler_setup
)


WHISKERQUILL_SCRIBE = make_creature(
    name="Whiskerquill Scribe",
    power=1, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rat", "Advisor"},
    text="When Whiskerquill Scribe enters, each player mills two cards."
)


GRIMTHORN_ASSASSIN = make_creature(
    name="Grimthorn Assassin",
    power=3, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "Assassin"},
    text="Flying, deathtouch."
)


# =============================================================================
# RED CARDS - LIZARDS, RACCOONS, CHAOS
# =============================================================================

def emberheart_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, deal 2 damage to any target."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={'amount': 2, 'target_type': 'any'}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

EMBERHEART_GUARDIAN = make_creature(
    name="Emberheart Guardian",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Warrior"},
    text="Haste. When Emberheart Guardian enters, it deals 2 damage to any target.",
    setup_interceptors=emberheart_guardian_setup
)


def fiery_provocateur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Valiant - deal 2 damage to target player."""
    def valiant_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={'amount': 2, 'target_type': 'player'}, source=obj.id)]
    return [make_valiant_trigger(obj, valiant_effect)]

FIERY_PROVOCATEUR = make_creature(
    name="Fiery Provocateur",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Shaman"},
    text="Valiant - Whenever Fiery Provocateur becomes the target of a spell or ability you control, it deals 2 damage to target player.",
    setup_interceptors=fiery_provocateur_setup
)


SCRAPYARD_SCRAPPER = make_creature(
    name="Scrapyard Scrapper",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Raccoon", "Berserker"},
    text="Haste. Scrapyard Scrapper can't block."
)


def rubble_rummager_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, discard a card then draw a card."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_attack_trigger(obj, attack_effect)]

RUBBLE_RUMMAGER = make_creature(
    name="Rubble Rummager",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Raccoon", "Warrior"},
    text="Whenever Rubble Rummager attacks, discard a card, then draw a card.",
    setup_interceptors=rubble_rummager_setup
)


def salamander_champion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Expend 4 - When you spend 4+ mana, this gets +2/+0 until end of turn."""
    def expend_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.BUFF, payload={'object_id': obj.id, 'power': 2, 'toughness': 0, 'duration': 'end_of_turn'}, source=obj.id)]
    return [make_expend_trigger(obj, 4, expend_effect)]

SALAMANDER_CHAMPION = make_creature(
    name="Salamander Champion",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Warrior"},
    text="First strike. Expend 4 - Whenever you spend four or more mana to cast a spell, Salamander Champion gets +2/+0 until end of turn.",
    setup_interceptors=salamander_champion_setup
)


HELLKITE_HATCHLING = make_creature(
    name="Hellkite Hatchling",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Dragon"},
    text="Flying. {R}: Hellkite Hatchling gets +1/+0 until end of turn."
)


def junk_dealer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, create a Treasure token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Treasure', 'types': ['Artifact'], 'subtypes': {'Treasure'}}
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

JUNK_DEALER = make_creature(
    name="Junk Dealer",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Raccoon", "Merchant"},
    text="When Junk Dealer enters, create a Treasure token.",
    setup_interceptors=junk_dealer_setup
)


BLAZING_CRESCENDO = make_instant(
    name="Blazing Crescendo",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +3/+1 until end of turn. When that creature dies this turn, draw a card."
)


TERRITORIAL_SALAMANDER = make_creature(
    name="Territorial Salamander",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Warrior"},
    text="Menace. Territorial Salamander must be blocked if able."
)


CHAOS_WRANGLER = make_creature(
    name="Chaos Wrangler",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Raccoon", "Warrior"},
    text="First strike. Whenever Chaos Wrangler attacks, target creature can't block this turn."
)


# =============================================================================
# GREEN CARDS - SQUIRRELS, RABBITS, NATURE
# =============================================================================

def hazel_rootfinder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Squirrels get +1/+1."""
    return make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Squirrel"))

HAZEL_ROOTFINDER = make_creature(
    name="Hazel, Rootfinder",
    power=2, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Squirrel", "Druid"},
    supertypes={"Legendary"},
    text="Other Squirrel creatures you control get +1/+1. {T}: Add one mana of any color. Spend this mana only to cast creature spells.",
    setup_interceptors=hazel_rootfinder_setup
)


def acornkeeper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, create a 1/1 green Squirrel token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Squirrel', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN}, 'subtypes': {'Squirrel'}}
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

ACORNKEEPER = make_creature(
    name="Acornkeeper",
    power=2, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Squirrel", "Druid"},
    text="When Acornkeeper enters, create a 1/1 green Squirrel creature token.",
    setup_interceptors=acornkeeper_setup
)


def barkform_pathfinder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Valiant - put a +1/+1 counter and gains trample until end of turn."""
    def valiant_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.COUNTER_ADDED, payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1}, source=obj.id),
            Event(type=EventType.GRANT_KEYWORD, payload={'object_id': obj.id, 'keyword': 'trample', 'duration': 'end_of_turn'}, source=obj.id)
        ]
    return [make_valiant_trigger(obj, valiant_effect)]

BARKFORM_PATHFINDER = make_creature(
    name="Barkform Pathfinder",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Squirrel", "Warrior"},
    text="Valiant - Whenever Barkform Pathfinder becomes the target of a spell or ability you control, put a +1/+1 counter on it. It gains trample until end of turn.",
    setup_interceptors=barkform_pathfinder_setup
)


OAKHAVEN_RANGER = make_creature(
    name="Oakhaven Ranger",
    power=3, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Rabbit", "Ranger"},
    text="Reach. Offspring {2}"
)


def thornvault_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, search for a basic land and put it onto battlefield tapped."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SEARCH_LIBRARY, payload={
            'player': obj.controller,
            'card_type': 'basic_land',
            'put_onto_battlefield': True,
            'tapped': True
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

THORNVAULT_GUARDIAN = make_creature(
    name="Thornvault Guardian",
    power=2, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Squirrel", "Druid"},
    text="When Thornvault Guardian enters, you may search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
    setup_interceptors=thornvault_guardian_setup
)


MIGHTY_OAK = make_creature(
    name="Mighty Oak",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="Trample. When Mighty Oak enters, put a +1/+1 counter on each other creature you control."
)


def nutcracker_squad_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, untap all other attacking Squirrels."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.UNTAP_ALL, payload={
            'controller': obj.controller,
            'subtype': 'Squirrel',
            'except_id': obj.id
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

NUTCRACKER_SQUAD = make_creature(
    name="Nutcracker Squad",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Squirrel", "Warrior"},
    text="Whenever Nutcracker Squad attacks, untap all other attacking Squirrel creatures you control.",
    setup_interceptors=nutcracker_squad_setup
)


BRANCH_LEAPER = make_creature(
    name="Branch Leaper",
    power=2, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Squirrel", "Scout"},
    text="Reach. When Branch Leaper dies, add {G}."
)


def grove_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Expend 8 - Draw two cards."""
    def expend_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_expend_trigger(obj, 8, expend_effect)]

GROVE_GUARDIAN = make_creature(
    name="Grove Guardian",
    power=4, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental", "Treefolk"},
    text="Vigilance, reach. Expend 8 - Whenever you spend eight or more mana to cast a spell, draw two cards.",
    setup_interceptors=grove_guardian_setup
)


WOODLAND_CHAMPION = make_creature(
    name="Woodland Champion",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Squirrel", "Warrior"},
    text="Whenever one or more tokens enter under your control, put that many +1/+1 counters on Woodland Champion."
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

def baylen_the_haymaker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, put a +1/+1 counter on each creature you control. Creatures with counters have trample."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'target_type': 'creatures_you_control',
            'counter_type': '+1/+1',
            'amount': 1
        }, source=obj.id)]

    def counter_filter(target: GameObject, state: GameState) -> bool:
        if target.controller != obj.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        counters = target.state.counters.get('+1/+1', 0)
        return counters > 0

    return [
        make_etb_trigger(obj, etb_effect),
        make_keyword_grant(obj, ['trample'], counter_filter)
    ]

BAYLEN_THE_HAYMAKER = make_creature(
    name="Baylen, the Haymaker",
    power=4, toughness=3,
    mana_cost="{1}{R}{G}{W}",
    colors={Color.RED, Color.GREEN, Color.WHITE},
    subtypes={"Rabbit", "Warrior"},
    supertypes={"Legendary"},
    text="When Baylen enters, put a +1/+1 counter on each creature you control. Each creature you control with a counter on it has trample.",
    setup_interceptors=baylen_the_haymaker_setup
)


def gev_scaled_scorch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a Lizard you control attacks, it deals 1 damage to defending player."""
    def lizard_attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        return (attacker.controller == obj.controller and
                "Lizard" in attacker.characteristics.subtypes)

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        defender = event.payload.get('defending_player')
        if defender:
            return [Event(type=EventType.DAMAGE, payload={'amount': 1, 'target': defender}, source=obj.id)]
        return []

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lizard_attack_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=attack_effect(e, s)),
        duration='while_on_battlefield'
    )]

GEV_SCALED_SCORCH = make_creature(
    name="Gev, Scaled Scorch",
    power=3, toughness=3,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Lizard", "Mercenary"},
    supertypes={"Legendary"},
    text="Menace. Whenever a Lizard you control attacks, it deals 1 damage to the defending player.",
    setup_interceptors=gev_scaled_scorch_setup
)


def clement_the_worrywort_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Frogs get +1/+1. When ETB, draw a card."""
    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Frog")))

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    interceptors.append(make_etb_trigger(obj, etb_effect))
    return interceptors

CLEMENT_THE_WORRYWORT = make_creature(
    name="Clement, the Worrywort",
    power=2, toughness=3,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Frog", "Druid"},
    supertypes={"Legendary"},
    text="Other Frog creatures you control get +1/+1. When Clement enters, draw a card.",
    setup_interceptors=clement_the_worrywort_setup
)


def ral_crackling_wit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an instant or sorcery, Otters get +1/+0 until end of turn."""
    def spell_cast_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        types = set(event.payload.get('types', []))
        return CardType.INSTANT in types or CardType.SORCERY in types

    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.BUFF, payload={
            'target_type': 'otter_creatures',
            'power': 1,
            'toughness': 0,
            'duration': 'end_of_turn'
        }, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=spell_cast_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=spell_effect(e, s)),
        duration='while_on_battlefield'
    )]

RAL_CRACKLING_WIT = make_creature(
    name="Ral, Crackling Wit",
    power=3, toughness=3,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Otter", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast an instant or sorcery spell, Otter creatures you control get +1/+0 until end of turn.",
    setup_interceptors=ral_crackling_wit_setup
)


def lumra_bellow_of_the_woods_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, mill 4. Return land cards milled this way to battlefield tapped."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MILL, payload={
            'player': obj.controller,
            'amount': 4,
            'return_lands': True
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

LUMRA_BELLOW_OF_THE_WOODS = make_creature(
    name="Lumra, Bellow of the Woods",
    power=4, toughness=4,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental", "Bear"},
    supertypes={"Legendary"},
    text="Trample. When Lumra enters, mill four cards. Return each land card milled this way to the battlefield tapped.",
    setup_interceptors=lumra_bellow_of_the_woods_setup
)


# --- Otter Cards ---

def stormcatch_mentor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When you cast instant/sorcery, draw a card."""
    def spell_cast_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        types = set(event.payload.get('types', []))
        return CardType.INSTANT in types or CardType.SORCERY in types

    def cast_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=spell_cast_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=cast_effect(e, s)),
        duration='while_on_battlefield'
    )]

STORMCATCH_MENTOR = make_creature(
    name="Stormcatch Mentor",
    power=2, toughness=2,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Otter", "Wizard"},
    text="Prowess. Whenever you cast an instant or sorcery spell, draw a card.",
    setup_interceptors=stormcatch_mentor_setup
)


OTTER_PLAYMAKER = make_creature(
    name="Otter Playmaker",
    power=2, toughness=1,
    mana_cost="{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Otter", "Wizard"},
    text="Prowess. When Otter Playmaker enters, exile the top card of your library. You may play it this turn."
)


RIVERSPLASH_TWINS = make_creature(
    name="Riversplash Twins",
    power=3, toughness=3,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Otter", "Wizard"},
    text="Whenever you cast an instant or sorcery spell, create a 1/1 blue and red Otter creature token."
)


# =============================================================================
# INSTANTS AND SORCERIES
# =============================================================================

MIGHT_OF_THE_MEEK = make_instant(
    name="Might of the Meek",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 until end of turn. If it's a Mouse, Rabbit, or Squirrel, it also gains lifelink until end of turn."
)


BRAVE_THE_WILDS = make_sorcery(
    name="Brave the Wilds",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card, reveal it, put it into your hand, then shuffle."
)


SUNSHOWER_DRUID = make_creature(
    name="Sunshower Druid",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Frog", "Druid"},
    text="When Sunshower Druid enters, you gain 2 life."
)


BANISHING_LIGHT = make_enchantment(
    name="Banishing Light",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When Banishing Light enters, exile target nonland permanent an opponent controls until Banishing Light leaves the battlefield."
)


def run_away_together_resolve(event: Event, state: GameState) -> list[Event]:
    return [Event(type=EventType.BOUNCE, payload={'count': 2}, source=event.source)]

RUN_AWAY_TOGETHER = make_instant(
    name="Run Away Together",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Choose two target creatures controlled by different players. Return those creatures to their owners' hands.",
    resolve=run_away_together_resolve
)


def lightning_strike_resolve(event: Event, state: GameState) -> list[Event]:
    return [Event(type=EventType.DAMAGE, payload={'amount': 3, 'target_type': 'any'}, source=event.source)]

LIGHTNING_STRIKE = make_instant(
    name="Lightning Strike",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Lightning Strike deals 3 damage to any target.",
    resolve=lightning_strike_resolve
)


RABID_BITE = make_sorcery(
    name="Rabid Bite",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control deals damage equal to its power to target creature you don't control."
)


MURDER = make_instant(
    name="Murder",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature."
)


NEGATE = make_instant(
    name="Negate",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target noncreature spell."
)


GIANT_GROWTH = make_instant(
    name="Giant Growth",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn."
)


SHOCK = make_instant(
    name="Shock",
    mana_cost="{R}",
    colors={Color.RED},
    text="Shock deals 2 damage to any target."
)


DURESS = make_sorcery(
    name="Duress",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target opponent reveals their hand. You choose a noncreature, nonland card from it. That player discards that card."
)


FEED_THE_SWARM = make_sorcery(
    name="Feed the Swarm",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Destroy target creature or enchantment an opponent controls. You lose life equal to that permanent's mana value."
)


TAKE_FOR_A_RIDE = make_sorcery(
    name="Take for a Ride",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn."
)


SEASONS_PAST = make_sorcery(
    name="Season's Past",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Return any number of cards with different mana values from your graveyard to your hand. Put Season's Past on the bottom of its owner's library."
)


# =============================================================================
# LANDS - VALLEY LOCATIONS
# =============================================================================

THREE_TREE_CITY = make_land(
    name="Three Tree City",
    text="{T}: Add {C}. {T}, Pay 1 life: Add one mana of any color. Spend this mana only to cast creature spells.",
    supertypes={"Legendary"}
)


LILYPAD_VILLAGE = make_land(
    name="Lilypad Village",
    text="Lilypad Village enters tapped. {T}: Add {U} or {G}."
)


SUNDOWN_PASS = make_land(
    name="Sundown Pass",
    text="Sundown Pass enters tapped unless you control two or more other lands. {T}: Add {R} or {W}."
)


DESOLATE_MIRE = make_land(
    name="Desolate Mire",
    text="Desolate Mire enters tapped unless you control two or more other lands. {T}: Add {B} or {G}."
)


VINEGLIMMER_SNARL = make_land(
    name="Vineglimmer Snarl",
    text="As Vineglimmer Snarl enters, you may reveal a Forest or Island card from your hand. If you don't, it enters tapped. {T}: Add {G} or {U}."
)


HAYSTACK_HOLLOW = make_land(
    name="Haystack Hollow",
    text="{T}: Add {C}. {T}, Sacrifice Haystack Hollow: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle."
)


FABLED_PASSAGE = make_land(
    name="Fabled Passage",
    text="{T}, Sacrifice Fabled Passage: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. Then if you control four or more lands, untap that land."
)


STARLIT_GROVE = make_land(
    name="Starlit Grove",
    text="Starlit Grove enters tapped. {T}: Add {W} or {B}. When Starlit Grove enters, scry 1."
)


# =============================================================================
# ARTIFACTS AND EQUIPMENT
# =============================================================================

PATCHWORK_BANNER = make_artifact(
    name="Patchwork Banner",
    mana_cost="{3}",
    text="As Patchwork Banner enters, choose a creature type. Creatures you control of the chosen type get +1/+1."
)


ACORN_HARVEST = make_artifact(
    name="Acorn Harvest",
    mana_cost="{2}",
    subtypes={"Food"},
    text="{2}, {T}, Sacrifice Acorn Harvest: You gain 3 life. When you sacrifice Acorn Harvest, create two 1/1 green Squirrel creature tokens."
)


def thornwood_blade_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipped creature gets +2/+0 and has first strike."""
    return []  # Equipment setup is handled by equip system

THORNWOOD_BLADE = make_artifact(
    name="Thornwood Blade",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +2/+0 and has first strike. Equip {2}",
    setup_interceptors=thornwood_blade_setup
)


TRAVELERS_PROVISIONS = make_artifact(
    name="Traveler's Provisions",
    mana_cost="{1}",
    subtypes={"Food"},
    text="{2}, {T}, Sacrifice Traveler's Provisions: You gain 3 life. When Traveler's Provisions enters, scry 1."
)


BRAMBLE_ARMOR = make_artifact(
    name="Bramble Armor",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="When Bramble Armor enters, attach it to target creature you control. Equipped creature gets +2/+1. Equip {3}"
)


BURROWGUARD_MENTOR = make_creature(
    name="Burrowguard Mentor",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Rabbit", "Knight"},
    text="Vigilance. Whenever an Equipment enters under your control, create a 1/1 white Rabbit creature token."
)


# =============================================================================
# ENCHANTMENTS
# =============================================================================

def season_of_gathering_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creatures you control get +1/+1. When ETB, create a Food token."""
    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 1, 1, creatures_you_control(obj)))

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Food', 'types': ['Artifact'], 'subtypes': {'Food'}}
        }, source=obj.id)]
    interceptors.append(make_etb_trigger(obj, etb_effect))
    return interceptors

SEASON_OF_GATHERING = make_enchantment(
    name="Season of Gathering",
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Creatures you control get +1/+1. When Season of Gathering enters, create a Food token.",
    setup_interceptors=season_of_gathering_setup
)


def gossip_of_birds_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a creature with flying enters, draw a card."""
    def etb_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        obj_id = event.payload.get('object_id')
        creature = state.objects.get(obj_id)
        if not creature:
            return False
        if creature.controller != obj.controller:
            return False
        return 'flying' in creature.characteristics.keywords if hasattr(creature.characteristics, 'keywords') else False

    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=etb_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=draw_effect(e, s)),
        duration='while_on_battlefield'
    )]

GOSSIP_OF_BIRDS = make_enchantment(
    name="Gossip of Birds",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Whenever a creature with flying enters under your control, draw a card.",
    setup_interceptors=gossip_of_birds_setup
)


BURROW_BELOW = make_aura(
    name="Burrow Below",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Enchanted creature gets +3/+3 and can't be blocked by creatures with power 2 or less."
)


NIGHT_TERRORS = make_aura(
    name="Night Terrors",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="When Night Terrors enters, target creature gets -3/-3 until end of turn. At the beginning of your upkeep, target creature gets -1/-1 until end of turn."
)


FLAMEKIN_UPRISING = make_enchantment(
    name="Flamekin Uprising",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Creatures you control get +1/+0 and have haste."
)


# =============================================================================
# MORE CREATURES TO REACH ~250 CARDS
# =============================================================================

# Additional White
LIGHTFOOT_SCOUT = make_creature(
    name="Lightfoot Scout",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Mouse", "Scout"},
    text="Vigilance."
)


MEADOW_GUARDIAN = make_creature(
    name="Meadow Guardian",
    power=2, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Rabbit", "Soldier"},
    text="First strike, lifelink."
)


SUNLIT_SHEPHERD = make_creature(
    name="Sunlit Shepherd",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Rabbit", "Cleric"},
    text="When Sunlit Shepherd enters, you gain 3 life."
)


WARREN_ELDER = make_creature(
    name="Warren Elder",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Rabbit", "Advisor"},
    text="Other Rabbits you control get +0/+1."
)


DAWNTREADER_MOUSE = make_creature(
    name="Dawntreader Mouse",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Mouse", "Scout"},
    text="{G}, Sacrifice Dawntreader Mouse: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle."
)


# Additional Blue
FOGWEAVER = make_creature(
    name="Fogweaver",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Frog", "Wizard"},
    text="Defender, hexproof."
)


STREAMDANCER = make_creature(
    name="Streamdancer",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Otter", "Bard"},
    text="Flash, flying."
)


RIPPLEWING_FALCON = make_creature(
    name="Ripplewing Falcon",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Scout"},
    text="Flying. When Ripplewing Falcon enters, target creature gains flying until end of turn."
)


TIDECALLER = make_creature(
    name="Tidecaller",
    power=2, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Frog", "Wizard"},
    text="Flash. When Tidecaller enters, tap target creature."
)


MISTFEATHER_OWL = make_creature(
    name="Mistfeather Owl",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Wizard"},
    text="Flying. {1}{U}: Mistfeather Owl gains hexproof until end of turn."
)


# Additional Black
TWILIGHT_PROWLER = make_creature(
    name="Twilight Prowler",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "Assassin"},
    text="Flying. When Twilight Prowler dies, each opponent loses 1 life."
)


HOLLOW_SCAVENGER = make_creature(
    name="Hollow Scavenger",
    power=3, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Rat", "Rogue"},
    text="Menace. When Hollow Scavenger dies, create a Food token."
)


NIGHTSHADE_HARVESTER = make_creature(
    name="Nightshade Harvester",
    power=1, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Frog", "Druid"},
    text="Deathtouch. Forage - {B}: Put a +1/+1 counter on Nightshade Harvester."
)


CRYPT_LURKER = make_creature(
    name="Crypt Lurker",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "Horror"},
    text="Flying. When Crypt Lurker enters, exile up to two target cards from graveyards."
)


SOUL_FEASTER = make_creature(
    name="Soul Feaster",
    power=3, toughness=2,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "Spirit"},
    text="Flying, lifelink. When Soul Feaster enters, target opponent sacrifices a creature."
)


# Additional Red
CINDER_RUNNER = make_creature(
    name="Cinder Runner",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Scout"},
    text="Haste. When Cinder Runner attacks, it gets +1/+0 until end of turn."
)


FLAMESCALE_CHAMPION = make_creature(
    name="Flamescale Champion",
    power=4, toughness=2,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Warrior"},
    text="First strike, haste."
)


TREASURE_HUNTER = make_creature(
    name="Treasure Hunter",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Raccoon", "Rogue"},
    text="When Treasure Hunter enters, create a Treasure token."
)


EMBER_SWALLOWER = make_creature(
    name="Ember Swallower",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Dragon"},
    text="When Ember Swallower enters, it deals 3 damage to each creature."
)


SLAG_SLINGER = make_creature(
    name="Slag Slinger",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Shaman"},
    text="{T}: Slag Slinger deals 1 damage to any target."
)


# Additional Green
ROOTWARDEN = make_creature(
    name="Rootwarden",
    power=3, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk", "Warrior"},
    text="Reach, vigilance."
)


SEEDCRAFTER = make_creature(
    name="Seedcrafter",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Squirrel", "Druid"},
    text="{T}: Add {G}. When Seedcrafter dies, search your library for a basic land card, reveal it, put it into your hand, then shuffle."
)


CANOPY_CLIMBER = make_creature(
    name="Canopy Climber",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Squirrel", "Scout"},
    text="Reach. When Canopy Climber enters, look at the top two cards of your library. Put one into your hand and the other on the bottom."
)


BRAMBLEGUARD = make_creature(
    name="Brambleguard",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental", "Warrior"},
    text="Trample. Brambleguard gets +2/+2 as long as you control four or more creatures."
)


ELDER_OAK = make_creature(
    name="Elder Oak",
    power=6, toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="Trample. When Elder Oak enters, you may return a land card from your graveyard to your hand."
)


# Additional Multicolor
STRIPED_FORAGER = make_creature(
    name="Striped Forager",
    power=3, toughness=2,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Raccoon", "Druid"},
    text="Menace. When Striped Forager enters, create a Food token."
)


RIVERBOUND_DUO = make_creature(
    name="Riverbound Duo",
    power=2, toughness=3,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Otter", "Scout"},
    text="When Riverbound Duo enters, draw a card, then discard a card."
)


DAWN_PATROL = make_creature(
    name="Dawn Patrol",
    power=2, toughness=2,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Mouse", "Knight"},
    text="First strike, vigilance."
)


SHADOWMOOR_STALKER = make_creature(
    name="Shadowmoor Stalker",
    power=3, toughness=1,
    mana_cost="{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Bat", "Rogue"},
    text="Flying. Whenever Shadowmoor Stalker deals combat damage to a player, that player mills two cards."
)


WILDFIRE_SHAMAN = make_creature(
    name="Wildfire Shaman",
    power=3, toughness=3,
    mana_cost="{1}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Lizard", "Shaman"},
    text="Trample. When Wildfire Shaman enters, it deals damage equal to its power to target creature you don't control."
)


# Colorless/Artifact creatures
STONE_SENTINEL = make_creature(
    name="Stone Sentinel",
    power=3, toughness=3,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Golem"},
    text="Defender. Stone Sentinel can attack as though it didn't have defender as long as you control five or more lands."
)


WATCHTOWER_GARGOYLE = make_creature(
    name="Watchtower Gargoyle",
    power=2, toughness=4,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Gargoyle"},
    text="Flying, defender."
)


# =============================================================================
# ADDITIONAL CARDS - COMMONS AND UNCOMMONS
# =============================================================================

# More White
HEARTH_HEALER = make_creature(
    name="Hearth Healer",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Mouse", "Cleric"},
    text="When Hearth Healer enters, you gain 2 life."
)

ARMORED_MOUSE = make_creature(
    name="Armored Mouse",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Mouse", "Knight"},
    text="Vigilance."
)

RALLYING_CRY = make_instant(
    name="Rallying Cry",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +1/+1 until end of turn."
)

PACIFISM = make_aura(
    name="Pacifism",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Enchanted creature can't attack or block."
)

REPEL_THE_VILE = make_instant(
    name="Repel the Vile",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Destroy target creature with power 4 or greater."
)

HARE_APPARENT = make_creature(
    name="Hare Apparent",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Rabbit", "Noble"},
    text="When Hare Apparent enters, create a 1/1 white Rabbit creature token."
)

GUARDIAN_OF_THE_GROVE = make_creature(
    name="Guardian of the Grove",
    power=3, toughness=5,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Rabbit", "Warrior"},
    text="Vigilance. Other creatures you control have +0/+1."
)

VALOR_SINGER = make_creature(
    name="Valor Singer",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Bird", "Bard"},
    text="Flying. {2}{W}: Target creature gains lifelink until end of turn."
)

HOMESTEAD_DEFENDER = make_creature(
    name="Homestead Defender",
    power=0, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Mouse", "Soldier"},
    text="Defender. Whenever a creature attacks you, Homestead Defender deals 1 damage to it."
)

STARLIGHT_BLESSING = make_instant(
    name="Starlight Blessing",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gains indestructible until end of turn. You gain 2 life."
)

# More Blue
CURRENT_RIDER = make_creature(
    name="Current Rider",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Otter", "Scout"},
    text="When Current Rider enters, draw a card, then discard a card."
)

QUICKSAND_FROG = make_creature(
    name="Quicksand Frog",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Frog", "Wizard"},
    text="Flash. When Quicksand Frog enters, tap target creature."
)

SPELL_STUTTER = make_instant(
    name="Spell Stutter",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {2}."
)

WISPS_WISDOM = make_instant(
    name="Wisp's Wisdom",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Draw a card. If you control a Bird, draw two cards instead, then discard a card."
)

RIPPLE_MAGE = make_creature(
    name="Ripple Mage",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Frog", "Wizard"},
    text="{T}: Scry 1."
)

ORACLE_OF_CURRENTS = make_creature(
    name="Oracle of Currents",
    power=2, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Frog", "Wizard"},
    text="At the beginning of your upkeep, scry 2."
)

SKYWATCHER = make_creature(
    name="Skywatcher",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Scout"},
    text="Flying. When Skywatcher dies, draw a card."
)

WINDBORNE_MESSENGER = make_creature(
    name="Windborne Messenger",
    power=3, toughness=2,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Wizard"},
    text="Flying. When Windborne Messenger enters, return target nonland permanent to its owner's hand."
)

COUNTERSPELL = make_instant(
    name="Counterspell",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell."
)

PONDER = make_sorcery(
    name="Ponder",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Look at the top three cards of your library, then put them back in any order. You may shuffle. Draw a card."
)

# More Black
AMBUSH_RAT = make_creature(
    name="Ambush Rat",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rat", "Rogue"},
    text="Flash, deathtouch."
)

DARK_RITUAL_RETURNS = make_instant(
    name="Dark Ritual Returns",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Add {B}{B}{B}."
)

ESSENCE_DRAIN = make_sorcery(
    name="Essence Drain",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="Essence Drain deals 3 damage to any target and you gain 3 life."
)

ROTTING_CARCASS = make_creature(
    name="Rotting Carcass",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie", "Rat"},
    text="When Rotting Carcass dies, each opponent loses 1 life."
)

FEARSOME_WARDEN = make_creature(
    name="Fearsome Warden",
    power=4, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "Warrior"},
    text="Flying, menace."
)

NIGHT_WHISPERS = make_sorcery(
    name="Night's Whisper",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="You draw two cards and you lose 2 life."
)

GRAVEDIGGER = make_creature(
    name="Gravedigger",
    power=2, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="When Gravedigger enters, you may return target creature card from your graveyard to your hand."
)

BLOODTITHE = make_sorcery(
    name="Bloodtithe",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Each opponent loses 3 life and you gain life equal to the life lost this way."
)

UNHOLY_HUNGER = make_instant(
    name="Unholy Hunger",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. You gain 2 life."
)

DREAD_RETURN = make_sorcery(
    name="Dread Return",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield."
)

# More Red
GOBLIN_GUIDE = make_creature(
    name="Goblin Guide",
    power=2, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Scout"},
    text="Haste. Whenever Goblin Guide attacks, defending player reveals the top card of their library."
)

FIREBOLT = make_sorcery(
    name="Firebolt",
    mana_cost="{R}",
    colors={Color.RED},
    text="Firebolt deals 2 damage to any target."
)

RECKLESS_CHARGE = make_sorcery(
    name="Reckless Charge",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains haste until end of turn."
)

PYROCLASM = make_sorcery(
    name="Pyroclasm",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Pyroclasm deals 2 damage to each creature."
)

RAMPAGING_SALAMANDER = make_creature(
    name="Rampaging Salamander",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Warrior"},
    text="Trample, haste."
)

INFERNO_ELEMENTAL = make_creature(
    name="Inferno Elemental",
    power=5, toughness=4,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Whenever Inferno Elemental blocks or becomes blocked, it deals 3 damage to each creature blocking or blocked by it."
)

SEARING_BLAZE = make_instant(
    name="Searing Blaze",
    mana_cost="{R}{R}",
    colors={Color.RED},
    text="Searing Blaze deals 1 damage to target player and 1 damage to target creature that player controls. Landfall - If you had a land enter this turn, deals 3 damage to each instead."
)

SMASH_TO_SMITHEREENS = make_instant(
    name="Smash to Smithereens",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Destroy target artifact. Smash to Smithereens deals 3 damage to that artifact's controller."
)

LAVA_SPIKE = make_sorcery(
    name="Lava Spike",
    mana_cost="{R}",
    colors={Color.RED},
    text="Lava Spike deals 3 damage to target player or planeswalker."
)

RAGING_GOBLIN = make_creature(
    name="Raging Goblin",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Berserker"},
    text="Haste."
)

# More Green
LLANOWAR_ELVES = make_creature(
    name="Llanowar Elves",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    text="{T}: Add {G}."
)

NATURALIZE = make_instant(
    name="Naturalize",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Destroy target artifact or enchantment."
)

CULTIVATE = make_sorcery(
    name="Cultivate",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for up to two basic land cards, reveal those cards, put one onto the battlefield tapped and the other into your hand, then shuffle."
)

RAMPANT_GROWTH = make_sorcery(
    name="Rampant Growth",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card, put that card onto the battlefield tapped, then shuffle."
)

OAKENFORM = make_aura(
    name="Oakenform",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Enchanted creature gets +3/+3."
)

ELVISH_MYSTIC = make_creature(
    name="Elvish Mystic",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    text="{T}: Add {G}."
)

FOREST_GUIDE = make_creature(
    name="Forest Guide",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Squirrel", "Scout"},
    text="When Forest Guide enters, search your library for a basic Forest card, reveal it, put it into your hand, then shuffle."
)

PRIMAL_MIGHT = make_sorcery(
    name="Primal Might",
    mana_cost="{X}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +X/+X until end of turn. Then it fights up to one target creature you don't control."
)

THORNWEALD_ARCHER = make_creature(
    name="Thornweald Archer",
    power=2, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Squirrel", "Archer"},
    text="Reach, deathtouch."
)

BEAST_WITHIN = make_instant(
    name="Beast Within",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Destroy target permanent. Its controller creates a 3/3 green Beast creature token."
)

# More Multicolor
GROWTH_SPIRAL = make_instant(
    name="Growth Spiral",
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    text="Draw a card. You may put a land card from your hand onto the battlefield."
)

PUTREFY = make_instant(
    name="Putrefy",
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Destroy target artifact or creature. It can't be regenerated."
)

ELECTROLYZE = make_instant(
    name="Electrolyze",
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    text="Electrolyze deals 2 damage divided as you choose among one or two targets. Draw a card."
)

FIRES_OF_INVENTION = make_enchantment(
    name="Fires of Invention",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="You can't cast more than two spells each turn. You may cast spells with mana value less than or equal to the number of lands you control without paying their mana costs."
)

TERMINATE = make_instant(
    name="Terminate",
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Destroy target creature. It can't be regenerated."
)

ABSORB = make_instant(
    name="Absorb",
    mana_cost="{W}{U}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Counter target spell. You gain 3 life."
)

MAELSTROM_PULSE = make_sorcery(
    name="Maelstrom Pulse",
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Destroy target nonland permanent and all other permanents with the same name as that permanent."
)

VINDICATE = make_sorcery(
    name="Vindicate",
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    text="Destroy target permanent."
)

SPRITE_DRAGON = make_creature(
    name="Sprite Dragon",
    power=1, toughness=1,
    mana_cost="{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Faerie", "Dragon"},
    text="Flying, haste. Whenever you cast a noncreature spell, put a +1/+1 counter on Sprite Dragon."
)

FLEETING_SONG = make_instant(
    name="Fleeting Song",
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Create two 1/1 white Bird creature tokens with flying. You gain 2 life."
)

# Additional Lands
TRANQUIL_COVE = make_land(
    name="Tranquil Cove",
    text="Tranquil Cove enters tapped. When it enters, you gain 1 life. {T}: Add {W} or {U}."
)

JUNGLE_HOLLOW = make_land(
    name="Jungle Hollow",
    text="Jungle Hollow enters tapped. When it enters, you gain 1 life. {T}: Add {B} or {G}."
)

SWIFTWATER_CLIFFS = make_land(
    name="Swiftwater Cliffs",
    text="Swiftwater Cliffs enters tapped. When it enters, you gain 1 life. {T}: Add {U} or {R}."
)

BLOSSOMING_SANDS = make_land(
    name="Blossoming Sands",
    text="Blossoming Sands enters tapped. When it enters, you gain 1 life. {T}: Add {G} or {W}."
)

BLOODFELL_CAVES = make_land(
    name="Bloodfell Caves",
    text="Bloodfell Caves enters tapped. When it enters, you gain 1 life. {T}: Add {B} or {R}."
)

THORNWOOD_FALLS = make_land(
    name="Thornwood Falls",
    text="Thornwood Falls enters tapped. When it enters, you gain 1 life. {T}: Add {G} or {U}."
)

SCOURED_BARRENS = make_land(
    name="Scoured Barrens",
    text="Scoured Barrens enters tapped. When it enters, you gain 1 life. {T}: Add {W} or {B}."
)

RUGGED_HIGHLANDS = make_land(
    name="Rugged Highlands",
    text="Rugged Highlands enters tapped. When it enters, you gain 1 life. {T}: Add {R} or {G}."
)

WIND_SCARRED_CRAG = make_land(
    name="Wind-Scarred Crag",
    text="Wind-Scarred Crag enters tapped. When it enters, you gain 1 life. {T}: Add {R} or {W}."
)

DISMAL_BACKWATER = make_land(
    name="Dismal Backwater",
    text="Dismal Backwater enters tapped. When it enters, you gain 1 life. {T}: Add {U} or {B}."
)

# More Artifacts
SOL_RING = make_artifact(
    name="Sol Ring",
    mana_cost="{1}",
    text="{T}: Add {C}{C}."
)

MIND_STONE = make_artifact(
    name="Mind Stone",
    mana_cost="{2}",
    text="{T}: Add {C}. {1}, {T}, Sacrifice Mind Stone: Draw a card."
)

ARCANE_SIGNET = make_artifact(
    name="Arcane Signet",
    mana_cost="{2}",
    text="{T}: Add one mana of any color in your commander's color identity."
)

COMMANDERS_SPHERE = make_artifact(
    name="Commander's Sphere",
    mana_cost="{3}",
    text="{T}: Add one mana of any color in your commander's color identity. Sacrifice Commander's Sphere: Draw a card."
)

FOOD_TOKEN_CREATOR = make_artifact(
    name="Honeycomb Bakery",
    mana_cost="{2}",
    text="{2}, {T}: Create a Food token."
)


# =============================================================================
# MORE BLOOMBURROW-THEMED CARDS
# =============================================================================

# More Mice
FIELD_MEDIC_MOUSE = make_creature(
    name="Field Medic Mouse",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Mouse", "Cleric"},
    text="{T}: Prevent the next 1 damage that would be dealt to any target this turn."
)

TAIL_TWISTER = make_creature(
    name="Tail Twister",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Mouse", "Rogue"},
    text="When Tail Twister enters, tap target creature."
)

CHEESE_MONGER = make_creature(
    name="Cheese Monger",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Mouse", "Citizen"},
    text="When Cheese Monger enters, create a Food token."
)

# More Rabbits
SPRINGFOOT_SCOUT = make_creature(
    name="Springfoot Scout",
    power=2, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Rabbit", "Scout"},
    text="Haste."
)

BURROW_DIGGER = make_creature(
    name="Burrow Digger",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Rabbit", "Druid"},
    text="{T}: Add {G}."
)

LEAPSTRIDER = make_creature(
    name="Leapstrider",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Rabbit", "Warrior"},
    text="Reach. Leapstrider can block an additional creature each combat."
)

# More Birds
AERIAL_SCOUT = make_creature(
    name="Aerial Scout",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Scout"},
    text="Flying. When Aerial Scout enters, scry 1."
)

WINGMATE_COURIER = make_creature(
    name="Wingmate Courier",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Advisor"},
    text="Flying. When Wingmate Courier enters, draw a card, then put a card from your hand on top of your library."
)

HAWKEYE_HUNTER = make_creature(
    name="Hawkeye Hunter",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Archer"},
    text="Flying. When Hawkeye Hunter deals combat damage to a player, draw a card."
)

# More Frogs
POISONOUS_DART_FROG = make_creature(
    name="Poisonous Dart Frog",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Frog"},
    text="Deathtouch."
)

LILYPAD_LOUNGER = make_creature(
    name="Lilypad Lounger",
    power=0, toughness=3,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Frog", "Citizen"},
    text="Defender. {T}: Untap target creature you control."
)

CHORUS_LEADER = make_creature(
    name="Chorus Leader",
    power=2, toughness=2,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Frog", "Bard"},
    text="Other Frogs you control get +1/+1."
)

# More Lizards
FIRE_BREATHER = make_creature(
    name="Fire Breather",
    power=1, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Shaman"},
    text="{R}: Fire Breather gets +1/+0 until end of turn."
)

MOLTEN_RUNNER = make_creature(
    name="Molten Runner",
    power=3, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Scout"},
    text="Haste. Molten Runner attacks each combat if able."
)

OBSIDIAN_SCALES = make_creature(
    name="Obsidian Scales",
    power=2, toughness=4,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Warrior"},
    text="First strike. When Obsidian Scales blocks or becomes blocked, it deals 1 damage to each creature blocking or blocked by it."
)

# More Bats
DUSK_SWOOPER = make_creature(
    name="Dusk Swooper",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "Scout"},
    text="Flying. When Dusk Swooper enters, target player loses 1 life and you gain 1 life."
)

ECHO_LOCATOR = make_creature(
    name="Echo Locator",
    power=1, toughness=2,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "Wizard"},
    text="Flying. {1}{B}: Scry 1."
)

NIGHT_SCREAMER = make_creature(
    name="Night Screamer",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "Horror"},
    text="Flying. When Night Screamer enters, each opponent discards a card."
)

# More Raccoons
TRASH_PANDA = make_creature(
    name="Trash Panda",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Raccoon", "Rogue"},
    text="Menace. When Trash Panda dies, create a Treasure token."
)

MIDNIGHT_RAIDER = make_creature(
    name="Midnight Raider",
    power=3, toughness=2,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Raccoon", "Rogue"},
    text="Menace. Whenever Midnight Raider deals combat damage to a player, create a Treasure token."
)

RING_TAIL_THIEF = make_creature(
    name="Ring-Tail Thief",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Raccoon", "Rogue"},
    text="When Ring-Tail Thief enters, it deals 1 damage to any target."
)

# More Otters
SPLASH_WEAVER = make_creature(
    name="Splash Weaver",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Otter", "Wizard"},
    text="Prowess."
)

RIVER_DANCER = make_creature(
    name="River Dancer",
    power=1, toughness=3,
    mana_cost="{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Otter", "Bard"},
    text="Whenever you cast an instant or sorcery spell, River Dancer gets +1/+0 until end of turn."
)

WHIRLPOOL_CHAMPION = make_creature(
    name="Whirlpool Champion",
    power=3, toughness=3,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Otter", "Warrior"},
    text="Prowess. When Whirlpool Champion enters, draw a card."
)

# More Squirrels
NUTKEEPER = make_creature(
    name="Nutkeeper",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Squirrel", "Druid"},
    text="When Nutkeeper dies, create a Food token."
)

TREE_HOPPER = make_creature(
    name="Tree Hopper",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Squirrel", "Scout"},
    text="Reach. Tree Hopper can't be blocked by creatures with flying."
)

ACORN_ARTILLERY = make_creature(
    name="Acorn Artillery",
    power=1, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Squirrel", "Warrior"},
    text="Reach. {T}: Acorn Artillery deals 1 damage to target creature with flying."
)

CHIEF_NUTCRACKER = make_creature(
    name="Chief Nutcracker",
    power=4, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Squirrel", "Warrior"},
    text="Trample. Other Squirrels you control have +1/+1 and trample."
)

# Additional Spells
FURRY_FRIENDSHIP = make_sorcery(
    name="Furry Friendship",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Create two 1/1 white Mouse creature tokens. You gain 2 life."
)

BURROW_TACTICS = make_instant(
    name="Burrow Tactics",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature you control gets +2/+2 until end of turn. If it's a Mouse or Rabbit, it gains lifelink until end of turn."
)

SPLASH_OF_BRILLIANCE = make_instant(
    name="Splash of Brilliance",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw two cards, then discard a card. If you control an Otter, draw three cards instead."
)

SHADOW_FEAST = make_sorcery(
    name="Shadow Feast",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Each opponent loses 2 life. Create a Food token."
)

BLAZING_TAIL = make_instant(
    name="Blazing Tail",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains first strike until end of turn. If it's a Lizard, it also gains trample."
)

FOREST_BOUNTY = make_sorcery(
    name="Forest Bounty",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Create two Food tokens. You may sacrifice a Food. If you do, draw a card."
)

VALLEY_BLESSING = make_enchantment(
    name="Valley Blessing",
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Whenever a creature enters under your control, you gain 1 life."
)

STARFALL_CHORUS = make_sorcery(
    name="Starfall Chorus",
    mana_cost="{3}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Create three 1/1 white Bird creature tokens with flying. Draw a card."
)


# =============================================================================
# EXPORT CARDS DICTIONARY
# =============================================================================

BLOOMBURROW_CARDS = {
    # WHITE - MICE, RABBITS
    "Mabel, Heir to Cragflame": MABEL_HEIR_TO_CRAGFLAME,
    "Finneas, Ace Archer": FINNEAS_ACE_ARCHER,
    "Star Charterer": STAR_CHARTERER,
    "Warren Wardens": WARREN_WARDENS,
    "Carrot Cake": CARROT_CAKE,
    "Plumecreed Mentor": PLUMECREED_MENTOR,
    "Mouse Trapper": MOUSE_TRAPPER,
    "Pearl of Wisdom": PEARL_OF_WISDOM,
    "Brave Burrow-Watcher": BRAVE_BURROW_WATCHER,
    "Heartfire Hero": HEARTFIRE_HERO,
    "Seedpod Squire": SEEDPOD_SQUIRE,
    "Valley Questcaller": VALLEY_QUESTCALLER,
    "Lifecreed Duo": LIFECREED_DUO,
    "Sungrass Elder": SUNGRASS_ELDER,
    "Lightfoot Scout": LIGHTFOOT_SCOUT,
    "Meadow Guardian": MEADOW_GUARDIAN,
    "Sunlit Shepherd": SUNLIT_SHEPHERD,
    "Warren Elder": WARREN_ELDER,
    "Dawntreader Mouse": DAWNTREADER_MOUSE,
    "Burrowguard Mentor": BURROWGUARD_MENTOR,
    "Banishing Light": BANISHING_LIGHT,
    "Might of the Meek": MIGHT_OF_THE_MEEK,

    # BLUE - BIRDS, FROGS
    "Stormchaser Hawk": STORMCHASER_HAWK,
    "Festival Frog": FESTIVAL_FROG,
    "Dreadmaw Hatchling": DREADMAW_HATCHLING,
    "Keen-Eyed Curator": KEEN_EYED_CURATOR,
    "Thought Stalker": THOUGHT_STALKER,
    "Splash Portal": SPLASH_PORTAL,
    "Skyskipper Duo": SKYSKIPPER_DUO,
    "Pond Prophet": POND_PROPHET,
    "Vantress Transmuter": VANTRESS_TRANSMUTER,
    "Windreader Owl": WINDREADER_OWL,
    "Oakhame Stormguard": OAKHAME_STORMGUARD,
    "Fogweaver": FOGWEAVER,
    "Streamdancer": STREAMDANCER,
    "Ripplewing Falcon": RIPPLEWING_FALCON,
    "Tidecaller": TIDECALLER,
    "Mistfeather Owl": MISTFEATHER_OWL,
    "Run Away Together": RUN_AWAY_TOGETHER,
    "Negate": NEGATE,
    "Gossip of Birds": GOSSIP_OF_BIRDS,

    # BLACK - BATS, RATS
    "Zoraline, Cosmos Caller": ZORALINE_COSMOS_CALLER,
    "Dusk Hunter": DUSK_HUNTER,
    "Nettling Nuisance": NETTLING_NUISANCE,
    "Moonlit Stalker": MOONLIT_STALKER,
    "Persistent Packrat": PERSISTENT_PACKRAT,
    "Midnight Trickster": MIDNIGHT_TRICKSTER,
    "Bog Creeper": BOG_CREEPER,
    "Carrion Feaster": CARRION_FEASTER,
    "Shadow Prowler": SHADOW_PROWLER,
    "Whiskerquill Scribe": WHISKERQUILL_SCRIBE,
    "Grimthorn Assassin": GRIMTHORN_ASSASSIN,
    "Shadowfire Elder": SHADOWFIRE_ELDER,
    "Twilight Prowler": TWILIGHT_PROWLER,
    "Hollow Scavenger": HOLLOW_SCAVENGER,
    "Nightshade Harvester": NIGHTSHADE_HARVESTER,
    "Crypt Lurker": CRYPT_LURKER,
    "Soul Feaster": SOUL_FEASTER,
    "Murder": MURDER,
    "Duress": DURESS,
    "Feed the Swarm": FEED_THE_SWARM,
    "Night Terrors": NIGHT_TERRORS,

    # RED - LIZARDS, RACCOONS
    "Emberheart Guardian": EMBERHEART_GUARDIAN,
    "Fiery Provocateur": FIERY_PROVOCATEUR,
    "Scrapyard Scrapper": SCRAPYARD_SCRAPPER,
    "Rubble Rummager": RUBBLE_RUMMAGER,
    "Salamander Champion": SALAMANDER_CHAMPION,
    "Hellkite Hatchling": HELLKITE_HATCHLING,
    "Junk Dealer": JUNK_DEALER,
    "Blazing Crescendo": BLAZING_CRESCENDO,
    "Territorial Salamander": TERRITORIAL_SALAMANDER,
    "Chaos Wrangler": CHAOS_WRANGLER,
    "Blazeborn Elder": BLAZEBORN_ELDER,
    "Cinder Runner": CINDER_RUNNER,
    "Flamescale Champion": FLAMESCALE_CHAMPION,
    "Treasure Hunter": TREASURE_HUNTER,
    "Ember Swallower": EMBER_SWALLOWER,
    "Slag Slinger": SLAG_SLINGER,
    "Lightning Strike": LIGHTNING_STRIKE,
    "Shock": SHOCK,
    "Take for a Ride": TAKE_FOR_A_RIDE,
    "Flamekin Uprising": FLAMEKIN_UPRISING,

    # GREEN - SQUIRRELS, NATURE
    "Hazel, Rootfinder": HAZEL_ROOTFINDER,
    "Hugs, Grisly Guardian": HUGS_GRISLY_GUARDIAN,
    "Acornkeeper": ACORNKEEPER,
    "Barkform Pathfinder": BARKFORM_PATHFINDER,
    "Oakhaven Ranger": OAKHAVEN_RANGER,
    "Thornvault Guardian": THORNVAULT_GUARDIAN,
    "Mighty Oak": MIGHTY_OAK,
    "Nutcracker Squad": NUTCRACKER_SQUAD,
    "Branch Leaper": BRANCH_LEAPER,
    "Grove Guardian": GROVE_GUARDIAN,
    "Woodland Champion": WOODLAND_CHAMPION,
    "Valley Mightcaller": VALLEY_MIGHTCALLER,
    "Sunshower Druid": SUNSHOWER_DRUID,
    "Rootwarden": ROOTWARDEN,
    "Seedcrafter": SEEDCRAFTER,
    "Canopy Climber": CANOPY_CLIMBER,
    "Brambleguard": BRAMBLEGUARD,
    "Elder Oak": ELDER_OAK,
    "Brave the Wilds": BRAVE_THE_WILDS,
    "Rabid Bite": RABID_BITE,
    "Giant Growth": GIANT_GROWTH,
    "Season's Past": SEASONS_PAST,
    "Burrow Below": BURROW_BELOW,
    "Season of Gathering": SEASON_OF_GATHERING,

    # MULTICOLOR
    "Ygra, Eater of All": YGRA_EATER_OF_ALL,
    "Baylen, the Haymaker": BAYLEN_THE_HAYMAKER,
    "Gev, Scaled Scorch": GEV_SCALED_SCORCH,
    "Clement, the Worrywort": CLEMENT_THE_WORRYWORT,
    "Ral, Crackling Wit": RAL_CRACKLING_WIT,
    "Lumra, Bellow of the Woods": LUMRA_BELLOW_OF_THE_WOODS,
    "Stormcatch Mentor": STORMCATCH_MENTOR,
    "Otter Playmaker": OTTER_PLAYMAKER,
    "Riversplash Twins": RIVERSPLASH_TWINS,
    "Striped Forager": STRIPED_FORAGER,
    "Riverbound Duo": RIVERBOUND_DUO,
    "Dawn Patrol": DAWN_PATROL,
    "Shadowmoor Stalker": SHADOWMOOR_STALKER,
    "Wildfire Shaman": WILDFIRE_SHAMAN,

    # LANDS
    "Three Tree City": THREE_TREE_CITY,
    "Lilypad Village": LILYPAD_VILLAGE,
    "Sundown Pass": SUNDOWN_PASS,
    "Desolate Mire": DESOLATE_MIRE,
    "Vineglimmer Snarl": VINEGLIMMER_SNARL,
    "Haystack Hollow": HAYSTACK_HOLLOW,
    "Fabled Passage": FABLED_PASSAGE,
    "Starlit Grove": STARLIT_GROVE,

    # ARTIFACTS
    "Patchwork Banner": PATCHWORK_BANNER,
    "Acorn Harvest": ACORN_HARVEST,
    "Thornwood Blade": THORNWOOD_BLADE,
    "Traveler's Provisions": TRAVELERS_PROVISIONS,
    "Bramble Armor": BRAMBLE_ARMOR,
    "Stone Sentinel": STONE_SENTINEL,
    "Watchtower Gargoyle": WATCHTOWER_GARGOYLE,
    "Sol Ring": SOL_RING,
    "Mind Stone": MIND_STONE,
    "Arcane Signet": ARCANE_SIGNET,
    "Commander's Sphere": COMMANDERS_SPHERE,
    "Honeycomb Bakery": FOOD_TOKEN_CREATOR,

    # ADDITIONAL WHITE
    "Hearth Healer": HEARTH_HEALER,
    "Armored Mouse": ARMORED_MOUSE,
    "Rallying Cry": RALLYING_CRY,
    "Pacifism": PACIFISM,
    "Repel the Vile": REPEL_THE_VILE,
    "Hare Apparent": HARE_APPARENT,
    "Guardian of the Grove": GUARDIAN_OF_THE_GROVE,
    "Valor Singer": VALOR_SINGER,
    "Homestead Defender": HOMESTEAD_DEFENDER,
    "Starlight Blessing": STARLIGHT_BLESSING,

    # ADDITIONAL BLUE
    "Current Rider": CURRENT_RIDER,
    "Quicksand Frog": QUICKSAND_FROG,
    "Spell Stutter": SPELL_STUTTER,
    "Wisp's Wisdom": WISPS_WISDOM,
    "Ripple Mage": RIPPLE_MAGE,
    "Oracle of Currents": ORACLE_OF_CURRENTS,
    "Skywatcher": SKYWATCHER,
    "Windborne Messenger": WINDBORNE_MESSENGER,
    "Counterspell": COUNTERSPELL,
    "Ponder": PONDER,

    # ADDITIONAL BLACK
    "Ambush Rat": AMBUSH_RAT,
    "Dark Ritual Returns": DARK_RITUAL_RETURNS,
    "Essence Drain": ESSENCE_DRAIN,
    "Rotting Carcass": ROTTING_CARCASS,
    "Fearsome Warden": FEARSOME_WARDEN,
    "Night's Whisper": NIGHT_WHISPERS,
    "Gravedigger": GRAVEDIGGER,
    "Bloodtithe": BLOODTITHE,
    "Unholy Hunger": UNHOLY_HUNGER,
    "Dread Return": DREAD_RETURN,

    # ADDITIONAL RED
    "Goblin Guide": GOBLIN_GUIDE,
    "Firebolt": FIREBOLT,
    "Reckless Charge": RECKLESS_CHARGE,
    "Pyroclasm": PYROCLASM,
    "Rampaging Salamander": RAMPAGING_SALAMANDER,
    "Inferno Elemental": INFERNO_ELEMENTAL,
    "Searing Blaze": SEARING_BLAZE,
    "Smash to Smithereens": SMASH_TO_SMITHEREENS,
    "Lava Spike": LAVA_SPIKE,
    "Raging Goblin": RAGING_GOBLIN,

    # ADDITIONAL GREEN
    "Llanowar Elves": LLANOWAR_ELVES,
    "Naturalize": NATURALIZE,
    "Cultivate": CULTIVATE,
    "Rampant Growth": RAMPANT_GROWTH,
    "Oakenform": OAKENFORM,
    "Elvish Mystic": ELVISH_MYSTIC,
    "Forest Guide": FOREST_GUIDE,
    "Primal Might": PRIMAL_MIGHT,
    "Thornweald Archer": THORNWEALD_ARCHER,
    "Beast Within": BEAST_WITHIN,

    # ADDITIONAL MULTICOLOR
    "Growth Spiral": GROWTH_SPIRAL,
    "Putrefy": PUTREFY,
    "Electrolyze": ELECTROLYZE,
    "Fires of Invention": FIRES_OF_INVENTION,
    "Terminate": TERMINATE,
    "Absorb": ABSORB,
    "Maelstrom Pulse": MAELSTROM_PULSE,
    "Vindicate": VINDICATE,
    "Sprite Dragon": SPRITE_DRAGON,
    "Fleeting Song": FLEETING_SONG,

    # ADDITIONAL LANDS
    "Tranquil Cove": TRANQUIL_COVE,
    "Jungle Hollow": JUNGLE_HOLLOW,
    "Swiftwater Cliffs": SWIFTWATER_CLIFFS,
    "Blossoming Sands": BLOSSOMING_SANDS,
    "Bloodfell Caves": BLOODFELL_CAVES,
    "Thornwood Falls": THORNWOOD_FALLS,
    "Scoured Barrens": SCOURED_BARRENS,
    "Rugged Highlands": RUGGED_HIGHLANDS,
    "Wind-Scarred Crag": WIND_SCARRED_CRAG,
    "Dismal Backwater": DISMAL_BACKWATER,

    # MORE BLOOMBURROW CREATURES
    "Field Medic Mouse": FIELD_MEDIC_MOUSE,
    "Tail Twister": TAIL_TWISTER,
    "Cheese Monger": CHEESE_MONGER,
    "Springfoot Scout": SPRINGFOOT_SCOUT,
    "Burrow Digger": BURROW_DIGGER,
    "Leapstrider": LEAPSTRIDER,
    "Aerial Scout": AERIAL_SCOUT,
    "Wingmate Courier": WINGMATE_COURIER,
    "Hawkeye Hunter": HAWKEYE_HUNTER,
    "Poisonous Dart Frog": POISONOUS_DART_FROG,
    "Lilypad Lounger": LILYPAD_LOUNGER,
    "Chorus Leader": CHORUS_LEADER,
    "Fire Breather": FIRE_BREATHER,
    "Molten Runner": MOLTEN_RUNNER,
    "Obsidian Scales": OBSIDIAN_SCALES,
    "Dusk Swooper": DUSK_SWOOPER,
    "Echo Locator": ECHO_LOCATOR,
    "Night Screamer": NIGHT_SCREAMER,
    "Trash Panda": TRASH_PANDA,
    "Midnight Raider": MIDNIGHT_RAIDER,
    "Ring-Tail Thief": RING_TAIL_THIEF,
    "Splash Weaver": SPLASH_WEAVER,
    "River Dancer": RIVER_DANCER,
    "Whirlpool Champion": WHIRLPOOL_CHAMPION,
    "Nutkeeper": NUTKEEPER,
    "Tree Hopper": TREE_HOPPER,
    "Acorn Artillery": ACORN_ARTILLERY,
    "Chief Nutcracker": CHIEF_NUTCRACKER,

    # MORE BLOOMBURROW SPELLS
    "Furry Friendship": FURRY_FRIENDSHIP,
    "Burrow Tactics": BURROW_TACTICS,
    "Splash of Brilliance": SPLASH_OF_BRILLIANCE,
    "Shadow Feast": SHADOW_FEAST,
    "Blazing Tail": BLAZING_TAIL,
    "Forest Bounty": FOREST_BOUNTY,
    "Valley Blessing": VALLEY_BLESSING,
    "Starfall Chorus": STARFALL_CHORUS,
}
