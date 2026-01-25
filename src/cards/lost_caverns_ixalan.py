"""
The Lost Caverns of Ixalan (LCI) Card Implementations

Set released November 2023. ~250 cards.
Features mechanics: Descend, Discover, Craft, Map tokens, Explore
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


# =============================================================================
# IXALAN KEYWORD MECHANICS
# =============================================================================

def make_explore_trigger(source_obj: GameObject, effect_fn: Callable[[Event, GameState], list[Event]] = None) -> Interceptor:
    """
    Explore - Reveal top card. If land, put in hand. Otherwise, +1/+1 counter on this creature.
    Creates an explore event when triggered.
    """
    def default_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.EXPLORE,
            payload={'creature_id': source_obj.id, 'controller': source_obj.controller},
            source=source_obj.id
        )]

    actual_effect = effect_fn or default_effect
    return make_etb_trigger(source_obj, actual_effect)


def make_descend_trigger(source_obj: GameObject, threshold: int, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Descend N - Trigger when you have N or more permanent cards in your graveyard.
    """
    def descend_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        # Check if controller has threshold permanents in graveyard
        player = state.players.get(source_obj.controller)
        if not player:
            return False
        permanent_types = {CardType.CREATURE, CardType.ARTIFACT, CardType.ENCHANTMENT, CardType.LAND, CardType.PLANESWALKER}
        graveyard_permanents = sum(1 for obj_id in player.graveyard
                                   if state.objects.get(obj_id) and
                                   permanent_types.intersection(state.objects[obj_id].characteristics.types))
        return graveyard_permanents >= threshold

    def descend_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=descend_filter,
        handler=descend_handler,
        duration='while_on_battlefield'
    )


def make_discover_effect(source_obj: GameObject, discover_value: int) -> list[Event]:
    """
    Discover N - Exile cards from top of library until you hit one with mana value N or less.
    Cast it without paying its mana cost or put it into hand.
    """
    return [Event(
        type=EventType.DISCOVER,
        payload={'controller': source_obj.controller, 'value': discover_value},
        source=source_obj.id
    )]


def make_craft_ability(source_obj: GameObject, craft_cost: str, exile_count: int) -> Interceptor:
    """
    Craft with [materials] - Exile materials from graveyard to transform this artifact.
    """
    def craft_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ACTIVATE:
            return False
        return (event.payload.get('source') == source_obj.id and
                event.payload.get('ability') == 'craft')

    def craft_handler(event: Event, state: GameState) -> InterceptorResult:
        transform_event = Event(
            type=EventType.TRANSFORM,
            payload={'object_id': source_obj.id, 'craft': True},
            source=source_obj.id
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[transform_event])

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=craft_filter,
        handler=craft_handler,
        duration='while_on_battlefield'
    )


def create_map_token(controller: str, source_id: str) -> Event:
    """Create a Map artifact token."""
    return Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': controller,
            'token': {
                'name': 'Map',
                'types': {CardType.ARTIFACT},
                'subtypes': {'Map'},
                'text': '{1}, {T}, Sacrifice this artifact: Target creature you control explores.'
            }
        },
        source=source_id
    )


def pirate_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Pirate creatures you control."""
    return creatures_with_subtype(source, "Pirate")


def dinosaur_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Dinosaur creatures you control."""
    return creatures_with_subtype(source, "Dinosaur")


def vampire_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Vampire creatures you control."""
    return creatures_with_subtype(source, "Vampire")


def merfolk_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Merfolk creatures you control."""
    return creatures_with_subtype(source, "Merfolk")


def fungus_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Fungus creatures you control."""
    return creatures_with_subtype(source, "Fungus")


# =============================================================================
# WHITE CARDS - VAMPIRES, SOLDIERS, DESCEND
# =============================================================================

# --- Legendary Creatures ---

def ojer_taq_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Triple token creation"""
    def token_multiplier_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CREATE_TOKEN:
            return False
        return event.payload.get('controller') == obj.controller

    def token_multiplier_handler(event: Event, state: GameState) -> InterceptorResult:
        # Create two additional copies
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[event.copy(), event.copy()]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=token_multiplier_filter,
        handler=token_multiplier_handler,
        duration='while_on_battlefield'
    )]

OJER_TAQ = make_creature(
    name="Ojer Taq, Deepest Foundation",
    power=6, toughness=6,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"God"},
    supertypes={"Legendary"},
    text="Vigilance. If one or more creature tokens would be created under your control, three times that many of those tokens are created instead. When Ojer Taq dies, return it transformed.",
    setup_interceptors=ojer_taq_setup
)


def aclazotz_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, lifelink; when deals combat damage, opponent discards"""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target_player = event.payload.get('target')
        if target_player and target_player in state.players:
            return [Event(
                type=EventType.DISCARD,
                payload={'player': target_player, 'count': 1},
                source=obj.id
            )]
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

ACLAZOTZ = make_creature(
    name="Aclazotz, Deepest Betrayal",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "God"},
    supertypes={"Legendary"},
    text="Flying, lifelink. Whenever Aclazotz deals combat damage to a player, that player discards a card. When Aclazotz dies, return it transformed.",
    setup_interceptors=aclazotz_setup
)


def quintorius_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When a card leaves your graveyard, Spirits get +1/+0"""
    def graveyard_leave_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        return (event.payload.get('from_zone_type') == ZoneType.GRAVEYARD and
                event.payload.get('controller') == obj.controller)

    def boost_effect(event: Event, state: GameState) -> InterceptorResult:
        boost_event = Event(
            type=EventType.BUFF,
            payload={'subtype': 'Spirit', 'controller': obj.controller, 'power': 1, 'toughness': 0, 'duration': 'end_of_turn'},
            source=obj.id
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[boost_event])

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=graveyard_leave_filter,
        handler=boost_effect,
        duration='while_on_battlefield'
    )]

QUINTORIUS_LOREMASTER = make_creature(
    name="Quintorius Kand",
    power=3, toughness=4,
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Elephant", "Cleric"},
    supertypes={"Legendary"},
    text="Whenever you discover, you may cast the exiled card without paying its mana cost. Whenever one or more cards leave your graveyard, Quintorius Kand deals 2 damage to each opponent.",
    setup_interceptors=quintorius_setup
)


def chimil_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Spells you control can't be countered; discover at end step"""
    def uncounterable_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.COUNTER:
            return False
        target_id = event.payload.get('target_id')
        target = state.objects.get(target_id)
        return target and target.controller == obj.controller

    def uncounterable_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    interceptors = [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=uncounterable_filter,
        handler=uncounterable_handler,
        duration='while_on_battlefield'
    )]

    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        return make_discover_effect(obj, 5)

    interceptors.append(make_end_step_trigger(obj, end_step_effect))
    return interceptors

CHIMIL = make_artifact(
    name="Chimil, the Inner Sun",
    mana_cost="{6}",
    text="Spells you control can't be countered. At the beginning of your end step, discover 5.",
    supertypes={"Legendary"},
    setup_interceptors=chimil_setup
)


def clavileño_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Vampire you control deals combat damage to player, draw and lose 1 life"""
    def vampire_damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('is_combat'):
            return False
        source_id = event.payload.get('source')
        source = state.objects.get(source_id)
        return (source and source.controller == obj.controller and
                'Vampire' in source.characteristics.subtypes)

    def draw_effect(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id),
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': -1}, source=obj.id)
        ])

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=vampire_damage_filter,
        handler=draw_effect,
        duration='while_on_battlefield'
    )]

CLAVILENO = make_creature(
    name="Clavileno, First of the Blessed",
    power=2, toughness=2,
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Vampire", "Knight"},
    supertypes={"Legendary"},
    text="Flying. Whenever a Vampire you control deals combat damage to a player, draw a card and lose 1 life.",
    setup_interceptors=clavileño_setup
)


# --- Regular White Creatures ---

def bartolome_del_presidio_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sacrifice another creature: put +1/+1 counter on Bartolome"""
    def sacrifice_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'count': 1},
            source=obj.id
        )]

    def sacrifice_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        if event.payload.get('reason') != 'sacrifice':
            return False
        sacrificed = state.objects.get(event.payload.get('object_id'))
        return (sacrificed and sacrificed.id != obj.id and
                sacrificed.controller == obj.controller and
                CardType.CREATURE in sacrificed.characteristics.types)

    return [make_death_trigger(obj, sacrifice_effect, filter_fn=sacrifice_filter)]

BARTOLOME_DEL_PRESIDIO = make_creature(
    name="Bartolome del Presidio",
    power=2, toughness=2,
    mana_cost="{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Vampire", "Knight"},
    supertypes={"Legendary"},
    text="Whenever you sacrifice another creature, put a +1/+1 counter on Bartolome del Presidio.",
    setup_interceptors=bartolome_del_presidio_setup
)


def dusk_legion_sergeant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Vampires get +1/+1"""
    return make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Vampire"))

DUSK_LEGION_SERGEANT = make_creature(
    name="Dusk Legion Sergeant",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Vampire", "Soldier"},
    text="Other Vampire creatures you control get +1/+1.",
    setup_interceptors=dusk_legion_sergeant_setup
)


def envoy_of_okinec_ahau_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When ETB, create Map token"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [create_map_token(obj.controller, obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

ENVOY_OF_OKINEC_AHAU = make_creature(
    name="Envoy of Okinec Ahau",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="When Envoy of Okinec Ahau enters, create a Map token.",
    setup_interceptors=envoy_of_okinec_ahau_setup
)


def sanguine_evangelist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - create 1/1 Vampire token with lifelink"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {'name': 'Vampire', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE},
                          'subtypes': {'Vampire'}, 'keywords': ['lifelink']}
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

SANGUINE_EVANGELIST = make_creature(
    name="Sanguine Evangelist",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Vampire", "Cleric"},
    text="When Sanguine Evangelist enters, create a 1/1 white Vampire creature token with lifelink.",
    setup_interceptors=sanguine_evangelist_setup
)


DUSK_ROSE_RELIQUARY = make_artifact(
    name="Dusk Rose Reliquary",
    mana_cost="{1}{W}",
    text="Whenever a Vampire you control dies, you gain 1 life. {T}: Add one mana of any color."
)

LEGION_CONQUISTADOR = make_creature(
    name="Legion Conquistador",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Vampire", "Soldier"},
    text="When Legion Conquistador enters, you may search your library for any number of cards named Legion Conquistador, reveal them, put them into your hand, then shuffle."
)

PALADIN_OF_THE_BLOODSTAINED = make_creature(
    name="Paladin of the Bloodstained",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Vampire", "Knight"},
    text="When Paladin of the Bloodstained enters, create a 1/1 white Vampire creature token with lifelink."
)

GLORIFIER_OF_SUFFERING = make_creature(
    name="Glorifier of Suffering",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Vampire", "Cleric"},
    text="Descend 4 - Glorifier of Suffering gets +1/+1 as long as there are four or more permanent cards in your graveyard."
)

PENITENT_NOMAD = make_creature(
    name="Penitent Nomad",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Nomad"},
    text="When Penitent Nomad enters, you gain 2 life."
)


# =============================================================================
# BLUE CARDS - MERFOLK, ARTIFACTS, DISCOVER
# =============================================================================

# --- Legendary Creatures ---

def ojer_pakpatiq_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Instants have rebound"""
    def cast_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        spell_id = event.payload.get('spell_id')
        spell = state.objects.get(spell_id)
        return (spell and spell.controller == obj.controller and
                CardType.INSTANT in spell.characteristics.types)

    def rebound_handler(event: Event, state: GameState) -> InterceptorResult:
        spell_id = event.payload.get('spell_id')
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[
            Event(type=EventType.GRANT_REBOUND, payload={'spell_id': spell_id}, source=obj.id)
        ])

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=cast_filter,
        handler=rebound_handler,
        duration='while_on_battlefield'
    )]

OJER_PAKPATIQ = make_creature(
    name="Ojer Pakpatiq, Deepest Epoch",
    power=4, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"God"},
    supertypes={"Legendary"},
    text="Flying. Instant spells you cast from your hand have rebound. When Ojer Pakpatiq dies, return it transformed.",
    setup_interceptors=ojer_pakpatiq_setup
)


def hakbal_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When you explore, draw a card if you put land in hand"""
    def explore_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.EXPLORE:
            return False
        return event.payload.get('controller') == obj.controller

    def explore_handler(event: Event, state: GameState) -> InterceptorResult:
        if event.payload.get('was_land'):
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[
                Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id)
            ])
        return InterceptorResult(action=InterceptorAction.PASS)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=explore_filter,
        handler=explore_handler,
        duration='while_on_battlefield'
    )]

HAKBAL = make_creature(
    name="Hakbal of the Surging Soul",
    power=3, toughness=3,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Merfolk", "Scout"},
    supertypes={"Legendary"},
    text="At the beginning of combat, target Merfolk you control explores. Whenever a creature you control explores, if you put a land card into your hand, draw a card.",
    setup_interceptors=hakbal_setup
)


def tishana_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Merfolk you control get +1/+1 for each card in your hand"""
    def merfolk_filter(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                'Merfolk' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)

    def power_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        target = state.objects.get(event.payload.get('object_id'))
        return target and merfolk_filter(target, state)

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        player = state.players.get(obj.controller)
        hand_size = len(player.hand) if player else 0
        new_event = event.copy()
        new_event.payload['value'] = event.payload.get('value', 0) + hand_size
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    def toughness_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        target = state.objects.get(event.payload.get('object_id'))
        return target and merfolk_filter(target, state)

    def toughness_handler(event: Event, state: GameState) -> InterceptorResult:
        player = state.players.get(obj.controller)
        hand_size = len(player.hand) if player else 0
        new_event = event.copy()
        new_event.payload['value'] = event.payload.get('value', 0) + hand_size
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY, filter=power_filter,
                    handler=power_handler, duration='while_on_battlefield'),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY, filter=toughness_filter,
                    handler=toughness_handler, duration='while_on_battlefield')
    ]

TISHANA = make_creature(
    name="Tishana, Voice of Thunder",
    power=1, toughness=1,
    mana_cost="{5}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Merfolk", "Shaman"},
    supertypes={"Legendary"},
    text="Tishana's power and toughness are each equal to the number of cards in your hand. When Tishana enters, draw a card for each creature you control.",
    setup_interceptors=tishana_setup
)


# --- Regular Blue Creatures ---

def waterwind_scout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - explore"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.EXPLORE, payload={'creature_id': obj.id, 'controller': obj.controller}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

WATERWIND_SCOUT = make_creature(
    name="Waterwind Scout",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Scout"},
    text="When Waterwind Scout enters, it explores.",
    setup_interceptors=waterwind_scout_setup
)


def deeproot_pilgrimage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Merfolk becomes tapped, create 1/1 Merfolk token"""
    def tap_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.TAP:
            return False
        tapped_obj = state.objects.get(event.payload.get('object_id'))
        return (tapped_obj and tapped_obj.controller == obj.controller and
                'Merfolk' in tapped_obj.characteristics.subtypes)

    def create_token(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Merfolk', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN, Color.BLUE},
                          'subtypes': {'Merfolk'}, 'keywords': ['hexproof']}
            }, source=obj.id)
        ])

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=tap_filter,
        handler=create_token, duration='while_on_battlefield'
    )]

DEEPROOT_PILGRIMAGE = make_enchantment(
    name="Deeproot Pilgrimage",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Whenever one or more Merfolk you control become tapped, create a 1/1 hexproof Merfolk token.",
    setup_interceptors=deeproot_pilgrimage_setup
)


RIVER_HERALD_SCOUT = make_creature(
    name="River Herald Scout",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Scout"},
    text="When River Herald Scout enters, draw a card, then discard a card."
)

JADE_BEARER = make_creature(
    name="Jade Bearer",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Merfolk", "Shaman"},
    text="When Jade Bearer enters, put a +1/+1 counter on another target Merfolk you control."
)

SENTINEL_OF_THE_NAMELESS_CITY = make_creature(
    name="Sentinel of the Nameless City",
    power=3, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Warrior"},
    text="Vigilance. When Sentinel of the Nameless City enters, create a Map token."
)

NICANZIL_CURRENT_CONDUCTOR = make_creature(
    name="Nicanzil, Current Conductor",
    power=2, toughness=3,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Merfolk", "Scout"},
    supertypes={"Legendary"},
    text="Whenever a creature you control explores, you may put a land card from your hand onto the battlefield."
)

SINGER_OF_SWIFT_RIVERS = make_creature(
    name="Singer of Swift Rivers",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Shaman"},
    text="Merfolk you control can't be blocked."
)


# =============================================================================
# BLACK CARDS - VAMPIRES, SACRIFICE, DESCEND
# =============================================================================

# --- Legendary Creatures ---

def ojer_axonil_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Noncombat damage from sources you control = Ojer Axonil's power"""
    def damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('is_combat'):
            return False
        source_id = event.payload.get('source')
        source = state.objects.get(source_id)
        return source and source.controller == obj.controller

    def damage_handler(event: Event, state: GameState) -> InterceptorResult:
        ojer_power = get_power(obj, state)
        new_event = event.copy()
        new_event.payload['amount'] = max(event.payload.get('amount', 0), ojer_power)
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM, filter=damage_filter,
        handler=damage_handler, duration='while_on_battlefield'
    )]

OJER_AXONIL = make_creature(
    name="Ojer Axonil, Deepest Might",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"God"},
    supertypes={"Legendary"},
    text="Trample. If a source you control would deal noncombat damage to an opponent, it deals damage equal to Ojer Axonil's power instead. When Ojer Axonil dies, return it transformed.",
    setup_interceptors=ojer_axonil_setup
)


def vito_fanatic_of_aclazotz_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Lifelink; when you gain life, opponents lose that much"""
    def life_gain_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        return (event.payload.get('player') == obj.controller and
                event.payload.get('amount', 0) > 0)

    def drain_handler(event: Event, state: GameState) -> InterceptorResult:
        amount = event.payload.get('amount', 0)
        events = []
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -amount},
                source=obj.id
            ))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=life_gain_filter,
        handler=drain_handler, duration='while_on_battlefield'
    )]

VITO_FANATIC = make_creature(
    name="Vito, Fanatic of Aclazotz",
    power=4, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Cleric"},
    supertypes={"Legendary"},
    text="Flying, lifelink. Whenever you gain life, each opponent loses that much life.",
    setup_interceptors=vito_fanatic_of_aclazotz_setup
)


def bloodletter_of_aclazotz_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Double life loss for opponents"""
    def life_loss_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        amount = event.payload.get('amount', 0)
        if amount >= 0:
            return False
        return event.payload.get('player') != obj.controller

    def double_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['amount'] = event.payload.get('amount', 0) * 2
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM, filter=life_loss_filter,
        handler=double_handler, duration='while_on_battlefield'
    )]

BLOODLETTER_OF_ACLAZOTZ = make_creature(
    name="Bloodletter of Aclazotz",
    power=2, toughness=4,
    mana_cost="{1}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Knight"},
    text="Flying. If an opponent would lose life during your turn, they lose twice that much life instead.",
    setup_interceptors=bloodletter_of_aclazotz_setup
)


# --- Regular Black Creatures ---

def defossilize_setup(obj: GameObject, state: GameState) -> list[Event]:
    """Return creature from graveyard to hand, explore"""
    return [
        Event(type=EventType.ZONE_CHANGE, payload={'to_zone_type': ZoneType.HAND, 'target_type': 'creature'}, source=obj.id),
        Event(type=EventType.EXPLORE, payload={'creature_id': None, 'controller': obj.controller}, source=obj.id)
    ]

DEFOSSILIZE = make_sorcery(
    name="Defossilize",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to your hand. A creature you control explores.",
    resolve=defossilize_setup
)


def dead_weight_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enchanted creature gets -2/-2"""
    def pt_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.attached_to

    return make_static_pt_boost(obj, -2, -2, pt_filter)

DEAD_WEIGHT = make_enchantment(
    name="Dead Weight",
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Aura"},
    text="Enchant creature. Enchanted creature gets -2/-2.",
    setup_interceptors=dead_weight_setup
)


DUSK_LEGION_ZEALOT = make_creature(
    name="Dusk Legion Zealot",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Soldier"},
    text="When Dusk Legion Zealot enters, you draw a card and you lose 1 life."
)

VAMPIRE_OPPORTUNIST = make_creature(
    name="Vampire Opportunist",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="{6}{B}: Each opponent loses 2 life and you gain 2 life."
)

SKULLCAP_SNAIL = make_creature(
    name="Skullcap Snail",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Fungus", "Snail"},
    text="When Skullcap Snail enters, target opponent discards a card. Descend 4 - When Skullcap Snail dies, if there are four or more permanent cards in your graveyard, draw a card."
)

CHUPACABRA_ECHO = make_creature(
    name="Chupacabra Echo",
    power=3, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Beast", "Horror"},
    text="When Chupacabra Echo enters, destroy target creature an opponent controls."
)

MALAMET_VETERAN = make_creature(
    name="Malamet Veteran",
    power=4, toughness=3,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Soldier"},
    text="Lifelink. When Malamet Veteran dies, create a 1/1 white Vampire creature token with lifelink."
)

SOULS_OF_THE_LOST = make_creature(
    name="Souls of the Lost",
    power=0, toughness=0,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Souls of the Lost's power and toughness are each equal to the number of creature cards in your graveyard."
)


# =============================================================================
# RED CARDS - PIRATES, DINOSAURS, DISCOVER
# =============================================================================

# --- Legendary Creatures ---

def ojer_kaslem_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When creature you control deals combat damage, look at that many cards"""
    def combat_damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('is_combat'):
            return False
        source_id = event.payload.get('source')
        source = state.objects.get(source_id)
        return (source and source.controller == obj.controller and
                CardType.CREATURE in source.characteristics.types)

    def look_handler(event: Event, state: GameState) -> InterceptorResult:
        amount = event.payload.get('amount', 0)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[
            Event(type=EventType.LOOK_TOP, payload={'player': obj.controller, 'count': amount, 'may_put_creature': True}, source=obj.id)
        ])

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=combat_damage_filter,
        handler=look_handler, duration='while_on_battlefield'
    )]

OJER_KASLEM = make_creature(
    name="Ojer Kaslem, Deepest Growth",
    power=6, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"God"},
    supertypes={"Legendary"},
    text="Trample. Whenever a creature you control deals combat damage to a player, look at that many cards from the top of your library. You may put a creature card from among them onto the battlefield. Put the rest on the bottom of your library.",
    setup_interceptors=ojer_kaslem_setup
)


def captain_storm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Vehicle crewed, create Treasure"""
    def crew_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.TAP:
            return False
        return event.payload.get('reason') == 'crew' and event.payload.get('controller') == obj.controller

    def treasure_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'}}
            }, source=obj.id)
        ])

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=crew_filter,
        handler=treasure_handler, duration='while_on_battlefield'
    )]

CAPTAIN_STORM = make_creature(
    name="Captain Storm, Cosmium Raider",
    power=3, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Whenever you crew a Vehicle, create a Treasure token. Vehicles you control have haste.",
    setup_interceptors=captain_storm_setup
)


def etali_primal_conqueror_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - exile top card of each library, may cast nonlands"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players:
            events.append(Event(
                type=EventType.EXILE_TOP,
                payload={'player': player_id, 'may_cast': True},
                source=obj.id
            ))
        return events
    return [make_etb_trigger(obj, etb_effect)]

ETALI_PRIMAL_CONQUEROR = make_creature(
    name="Etali, Primal Conqueror",
    power=7, toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elder", "Dinosaur"},
    supertypes={"Legendary"},
    text="Trample. When Etali enters, each player exiles cards from the top of their library until they exile a nonland card. You may cast any number of spells from among the nonland cards exiled this way without paying their mana costs.",
    setup_interceptors=etali_primal_conqueror_setup
)


def dinosaur_enrage_trigger(source_obj: GameObject, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """Enrage - Trigger when this creature is dealt damage."""
    def enrage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        return event.payload.get('target') == source_obj.id

    def enrage_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=enrage_filter,
        handler=enrage_handler,
        duration='while_on_battlefield'
    )


def ripjaw_raptor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enrage - draw a card"""
    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id)]
    return [dinosaur_enrage_trigger(obj, draw_effect)]

RIPJAW_RAPTOR = make_creature(
    name="Ripjaw Raptor",
    power=4, toughness=5,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Enrage - Whenever Ripjaw Raptor is dealt damage, draw a card.",
    setup_interceptors=ripjaw_raptor_setup
)


# --- Regular Red Creatures ---

def burning_sun_cavalry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack trigger - deal 1 damage to target creature"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={'amount': 1, 'source': obj.id, 'is_combat': False}, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

BURNING_SUNS_CAVALRY = make_creature(
    name="Burning Sun's Cavalry",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Knight"},
    text="Whenever Burning Sun's Cavalry attacks, it deals 1 damage to target creature.",
    setup_interceptors=burning_sun_cavalry_setup
)


BRAZEN_BUCCANEER = make_creature(
    name="Brazen Buccaneer",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Pirate"},
    text="Haste. When Brazen Buccaneer enters, create a Treasure token."
)

DIRE_FLEET_DAREDEVIL = make_creature(
    name="Dire Fleet Daredevil",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Pirate"},
    text="First strike. When Dire Fleet Daredevil enters, exile target instant or sorcery card from an opponent's graveyard. You may cast it this turn, and mana of any type can be spent to cast it."
)

GOBLIN_TRAILBLAZER = make_creature(
    name="Goblin Trailblazer",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Pirate"},
    text="Menace"
)

FRILLED_DEATHSPITTER = make_creature(
    name="Frilled Deathspitter",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur"},
    text="Enrage - Whenever Frilled Deathspitter is dealt damage, it deals 2 damage to target opponent."
)

RAMPAGING_FEROCIDON = make_creature(
    name="Rampaging Ferocidon",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur"},
    text="Menace. Players can't gain life. Whenever another creature enters the battlefield, Rampaging Ferocidon deals 1 damage to that creature's controller."
)

MAGMATIC_GALLEON = make_artifact(
    name="Magmatic Galleon",
    mana_cost="{3}{R}{R}",
    text="When Magmatic Galleon enters, it deals 5 damage to target creature. Crew 2. Whenever Magmatic Galleon deals combat damage to a player, exile the top two cards. You may play them this turn.",
    subtypes={"Vehicle"}
)


# =============================================================================
# GREEN CARDS - DINOSAURS, EXPLORE, MERFOLK
# =============================================================================

# --- Legendary Creatures ---

def ghalta_stampede_tyrant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - put all creatures from hand onto battlefield"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PUT_CREATURES_FROM_HAND,
            payload={'player': obj.controller},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

GHALTA_STAMPEDE_TYRANT = make_creature(
    name="Ghalta, Stampede Tyrant",
    power=12, toughness=12,
    mana_cost="{6}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elder", "Dinosaur"},
    supertypes={"Legendary"},
    text="Trample. When Ghalta enters, put any number of creature cards from your hand onto the battlefield.",
    setup_interceptors=ghalta_stampede_tyrant_setup
)


def zoyowa_lava_tongue_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death trigger - discover 3"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return make_discover_effect(obj, 3)
    return [make_death_trigger(obj, death_effect)]

ZOYOWA_LAVA_TONGUE = make_creature(
    name="Zoyowa Lava-Tongue",
    power=2, toughness=2,
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Fungus", "Shaman"},
    supertypes={"Legendary"},
    text="Deathtouch. When Zoyowa Lava-Tongue dies, discover 3.",
    setup_interceptors=zoyowa_lava_tongue_setup
)


def inti_seneschal_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When you discard, exile top card and play it this turn"""
    def discard_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DISCARD:
            return False
        return event.payload.get('player') == obj.controller

    def exile_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[
            Event(type=EventType.EXILE_TOP, payload={'player': obj.controller, 'may_play': True}, source=obj.id)
        ])

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=discard_filter,
        handler=exile_handler, duration='while_on_battlefield'
    )]

INTI_SENESCHAL = make_creature(
    name="Inti, Seneschal of the Sun",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="Whenever you discard one or more cards, exile the top card of your library. You may play it until your next end step.",
    setup_interceptors=inti_seneschal_setup
)


# --- Regular Green Creatures ---

def merfolk_branchwalker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - explore"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.EXPLORE, payload={'creature_id': obj.id, 'controller': obj.controller}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

MERFOLK_BRANCHWALKER = make_creature(
    name="Merfolk Branchwalker",
    power=2, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Merfolk", "Scout"},
    text="When Merfolk Branchwalker enters, it explores.",
    setup_interceptors=merfolk_branchwalker_setup
)


def jadelight_ranger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - explore twice"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.EXPLORE, payload={'creature_id': obj.id, 'controller': obj.controller}, source=obj.id),
            Event(type=EventType.EXPLORE, payload={'creature_id': obj.id, 'controller': obj.controller}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

JADELIGHT_RANGER = make_creature(
    name="Jadelight Ranger",
    power=2, toughness=1,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Merfolk", "Scout"},
    text="When Jadelight Ranger enters, it explores, then it explores again.",
    setup_interceptors=jadelight_ranger_setup
)


def wayward_swordtooth_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Play additional land; can't attack unless descended"""
    def additional_land_filter(event: Event, state: GameState) -> bool:
        return False  # Simplified - would need land drop tracking

    return []

WAYWARD_SWORDTOOTH = make_creature(
    name="Wayward Swordtooth",
    power=5, toughness=5,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Ascend. You may play an additional land on each of your turns. Wayward Swordtooth can't attack or block unless you have the city's blessing.",
    setup_interceptors=wayward_swordtooth_setup
)


THRASHING_BRONTODON = make_creature(
    name="Thrashing Brontodon",
    power=3, toughness=4,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="{1}, Sacrifice Thrashing Brontodon: Destroy target artifact or enchantment."
)

COLOSSAL_DREADMAW = make_creature(
    name="Colossal Dreadmaw",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Trample"
)

TYRRANAX_REX = make_creature(
    name="Tyrranax Rex",
    power=8, toughness=8,
    mana_cost="{4}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Trample, ward {4}, haste. This spell can't be countered."
)

TOPIARY_STOMPER = make_creature(
    name="Topiary Stomper",
    power=4, toughness=4,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Dinosaur"},
    text="Vigilance. When Topiary Stomper enters, search your library for a basic land card, put it onto the battlefield tapped, then shuffle."
)

CARNAGE_TYRANT = make_creature(
    name="Carnage Tyrant",
    power=7, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="This spell can't be countered. Trample, hexproof."
)

INTREPID_PALEONTOLOGIST = make_creature(
    name="Intrepid Paleontologist",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Druid"},
    text="{T}: Add {G}. {2}{G}, {T}: Mill two cards, then return a creature card from your graveyard to your hand."
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

def huatli_poet_of_unity_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - search for basic land"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SEARCH_LIBRARY, payload={'player': obj.controller, 'card_type': 'basic_land'}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

HUATLI_POET_OF_UNITY = make_creature(
    name="Huatli, Poet of Unity",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="When Huatli enters, search your library for a basic land card, reveal it, put it into your hand, then shuffle. {2}{W}{W}: Transform Huatli.",
    setup_interceptors=huatli_poet_of_unity_setup
)


def kellan_daring_traveler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Double strike; when deals combat damage, create Map"""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [create_map_token(obj.controller, obj.id)]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

KELLAN_DARING_TRAVELER = make_creature(
    name="Kellan, Daring Traveler",
    power=2, toughness=2,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Faerie"},
    supertypes={"Legendary"},
    text="Double strike. Whenever Kellan deals combat damage to a player, create a Map token.",
    setup_interceptors=kellan_daring_traveler_setup
)


def admiral_brass_unsinkable_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Pirate attacks, return creature from graveyard attacking"""
    def attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker = state.objects.get(event.payload.get('attacker_id'))
        return (attacker and attacker.controller == obj.controller and
                'Pirate' in attacker.characteristics.subtypes)

    def reanimate_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[
            Event(type=EventType.REANIMATE_ATTACKING, payload={'controller': obj.controller}, source=obj.id)
        ])

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT, filter=attack_filter,
        handler=reanimate_handler, duration='while_on_battlefield'
    )]

ADMIRAL_BRASS_UNSINKABLE = make_creature(
    name="Admiral Brass, Unsinkable",
    power=4, toughness=4,
    mana_cost="{2}{U}{B}{R}",
    colors={Color.BLUE, Color.BLACK, Color.RED},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Whenever one or more Pirates you control attack, return up to one target Pirate creature card from your graveyard to the battlefield tapped and attacking.",
    setup_interceptors=admiral_brass_unsinkable_setup
)


def kumena_tyrant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tap Merfolk abilities"""
    # Simplified - would need activated ability infrastructure
    return []

KUMENA_TYRANT = make_creature(
    name="Kumena, Tyrant of Orazca",
    power=2, toughness=4,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Merfolk", "Shaman"},
    supertypes={"Legendary"},
    text="Tap another untapped Merfolk you control: Kumena can't be blocked. Tap three untapped Merfolk you control: Draw a card. Tap five untapped Merfolk you control: Put a +1/+1 counter on each Merfolk you control.",
    setup_interceptors=kumena_tyrant_setup
)


def zacama_primal_calamity_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - untap all lands; activated abilities"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.UNTAP_ALL_LANDS, payload={'player': obj.controller}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

ZACAMA_PRIMAL_CALAMITY = make_creature(
    name="Zacama, Primal Calamity",
    power=9, toughness=9,
    mana_cost="{6}{R}{G}{W}",
    colors={Color.RED, Color.GREEN, Color.WHITE},
    subtypes={"Elder", "Dinosaur"},
    supertypes={"Legendary"},
    text="Vigilance, reach, trample. When Zacama enters, if you cast it, untap all lands you control. {2}{R}: Zacama deals 3 damage to target creature. {2}{G}: Destroy target artifact or enchantment. {2}{W}: You gain 3 life.",
    setup_interceptors=zacama_primal_calamity_setup
)


GISHATH_SUNS_AVATAR = make_creature(
    name="Gishath, Sun's Avatar",
    power=7, toughness=6,
    mana_cost="{5}{R}{G}{W}",
    colors={Color.RED, Color.GREEN, Color.WHITE},
    subtypes={"Elder", "Dinosaur"},
    supertypes={"Legendary"},
    text="Vigilance, trample, haste. Whenever Gishath deals combat damage to a player, reveal that many cards from the top of your library. Put any number of Dinosaur creature cards revealed this way onto the battlefield."
)

KITESAIL_LARCENIST = make_creature(
    name="Kitesail Larcenist",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="Flying. When Kitesail Larcenist enters, exile target nonland permanent an opponent controls until Kitesail Larcenist leaves the battlefield."
)

HOSTAGE_TAKER = make_creature(
    name="Hostage Taker",
    power=2, toughness=3,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Pirate"},
    text="When Hostage Taker enters, exile another target creature or artifact until Hostage Taker leaves the battlefield. You may cast that card for as long as it remains exiled."
)

WAKER_OF_WAVES = make_creature(
    name="Waker of Waves",
    power=7, toughness=7,
    mana_cost="{5}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Whale"},
    text="Creatures your opponents control get -1/-0. {1}{U}, Discard Waker of Waves: Look at the top two cards of your library. Put one into your hand and the other into your graveyard."
)

DEEPFATHOM_SKULKER = make_creature(
    name="Deepfathom Skulker",
    power=4, toughness=4,
    mana_cost="{5}{U}",
    colors={Color.BLUE},
    subtypes={"Eldrazi"},
    text="Devoid. Whenever a creature you control deals combat damage to a player, you may draw a card. {3}{C}: Target creature can't be blocked this turn."
)


# =============================================================================
# ARTIFACTS
# =============================================================================

def tarrian_soulcleaver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipped creature gets +1/+1 for each creature that died"""
    # Simplified implementation
    return []

TARRIAN_SOULCLEAVER = make_equipment(
    name="Tarrian's Soulcleaver",
    mana_cost="{1}",
    text="Whenever equipped creature deals combat damage to a player, put a +1/+1 counter on it. Equipped creature gets +1/+1 for each creature card in your graveyard.",
    equip_cost="{1}",
    setup_interceptors=tarrian_soulcleaver_setup
)


THOUSAND_MOONS_SMITHY = make_artifact(
    name="The Thousand Moons Smithy",
    mana_cost="{2}{W}{W}",
    text="When The Thousand Moons Smithy enters, create a 1/1 white Gnome artifact creature token. Tap three untapped artifacts and/or creatures you control: Create a white Gnome Soldier artifact creature token with 'This creature's power and toughness are each equal to the number of artifacts and/or creatures you control.'",
    supertypes={"Legendary"}
)

MATZALANTLI = make_artifact(
    name="Matzalantli, the Great Door",
    mana_cost="{2}",
    text="{T}: Add one mana of any color. Descend 4 - {T}: Transform Matzalantli. Activate only if there are four or more permanent cards in your graveyard.",
    supertypes={"Legendary"}
)

OLTEC_MATTERWEAVER = make_artifact_creature(
    name="Oltec Matterweaver",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Golem"},
    text="When Oltec Matterweaver enters, create a Map token. Craft with artifact {3}{W}{W}."
)

FABRICATION_FOUNDRY = make_artifact(
    name="Fabrication Foundry",
    mana_cost="{1}{W}",
    text="Whenever an artifact enters the battlefield under your control, put a +1/+1 counter on target creature you control. {3}{W}, Exile Fabrication Foundry: Return all artifact cards from your graveyard to the battlefield."
)

DIDACTS_HEXPROOF = make_artifact(
    name="The Enigma Jewel",
    mana_cost="{5}",
    text="{T}: Untap another target permanent you control. Craft with four or more nonland permanents you control and/or permanent cards in your graveyard with four or more different mana values {7}.",
    supertypes={"Legendary"}
)

THRONE_OF_THE_GRIM_CAPTAIN = make_artifact(
    name="Throne of the Grim Captain",
    mana_cost="{2}",
    text="Tap, Sacrifice Throne: Exile target card from a graveyard. Craft with a Pirate, a Merfolk, a Dinosaur, and a Vampire from your graveyard.",
    supertypes={"Legendary"}
)

MAP_TOKEN = make_artifact(
    name="Map",
    mana_cost="{0}",
    text="{1}, {T}, Sacrifice this artifact: Target creature you control explores."
)

COSMIUM_CATALYST = make_artifact(
    name="Cosmium Catalyst",
    mana_cost="{2}",
    text="{1}, {T}: Add two mana in any combination of colors. Spend this mana only to cast spells that have discover or to activate discover abilities."
)


# =============================================================================
# LANDS
# =============================================================================

CAVERN_OF_SOULS = make_land(
    name="Cavern of Souls",
    text="As Cavern of Souls enters, choose a creature type. {T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast a creature spell of the chosen type, and that spell can't be countered."
)

UNCLAIMED_TERRITORY = make_land(
    name="Unclaimed Territory",
    text="As Unclaimed Territory enters, choose a creature type. {T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast a creature spell of the chosen type."
)

RESTLESS_ANCHORAGE = make_land(
    name="Restless Anchorage",
    text="Restless Anchorage enters tapped. {T}: Add {W} or {U}. {1}{W}{U}: Restless Anchorage becomes a 2/3 white and blue Bird artifact creature with flying until end of turn. It's still a land. Whenever Restless Anchorage attacks, create a Map token."
)

RESTLESS_REEF = make_land(
    name="Restless Reef",
    text="Restless Reef enters tapped. {T}: Add {U} or {B}. {1}{U}{B}: Restless Reef becomes a 4/4 blue and black Fish creature with deathtouch until end of turn. It's still a land. Whenever Restless Reef attacks, each player mills four cards."
)

RESTLESS_RIDGELINE = make_land(
    name="Restless Ridgeline",
    text="Restless Ridgeline enters tapped. {T}: Add {R} or {G}. {2}{R}{G}: Restless Ridgeline becomes a 5/4 red and green Dinosaur creature with trample and haste until end of turn. It's still a land."
)

RESTLESS_VENTS = make_land(
    name="Restless Vents",
    text="Restless Vents enters tapped. {T}: Add {B} or {R}. {2}{B}{R}: Restless Vents becomes a 2/3 black and red Scorpion creature with first strike and deathtouch until end of turn. It's still a land."
)

RESTLESS_PRAIRIE = make_land(
    name="Restless Prairie",
    text="Restless Prairie enters tapped. {T}: Add {G} or {W}. {1}{G}{W}: Restless Prairie becomes a 3/3 green and white Dinosaur creature with vigilance until end of turn. It's still a land. Whenever Restless Prairie deals combat damage, create a Map token."
)

HIDDEN_CATARACT = make_land(
    name="Hidden Cataract",
    text="Hidden Cataract enters tapped. {T}: Add {U}. Descend 8 - {2}{U}{U}: Hidden Cataract becomes a 4/4 blue Merfolk creature with hexproof. Activate only if there are eight or more permanent cards in your graveyard.",
    subtypes={"Cave"}
)

HIDDEN_VOLCANO = make_land(
    name="Hidden Volcano",
    text="Hidden Volcano enters tapped. {T}: Add {R}. Descend 8 - {2}{R}{R}: Hidden Volcano becomes a 6/1 red Dinosaur creature with haste. Activate only if there are eight or more permanent cards in your graveyard.",
    subtypes={"Cave"}
)

HIDDEN_NURSERY = make_land(
    name="Hidden Nursery",
    text="Hidden Nursery enters tapped. {T}: Add {G}. Descend 8 - {2}{G}{G}: Hidden Nursery becomes a 3/3 green Fungus creature with 'This creature gets +1/+1 for each creature card in your graveyard.' Activate only if there are eight or more permanent cards in your graveyard.",
    subtypes={"Cave"}
)

HIDDEN_NECROPOLIS = make_land(
    name="Hidden Necropolis",
    text="Hidden Necropolis enters tapped. {T}: Add {B}. Descend 8 - {2}{B}{B}: Hidden Necropolis becomes a 4/4 black Vampire creature with lifelink and menace. Activate only if there are eight or more permanent cards in your graveyard.",
    subtypes={"Cave"}
)

HIDDEN_COURTYARD = make_land(
    name="Hidden Courtyard",
    text="Hidden Courtyard enters tapped. {T}: Add {W}. Descend 8 - {2}{W}{W}: Hidden Courtyard becomes a 3/4 white Spirit creature with flying and vigilance. Activate only if there are eight or more permanent cards in your graveyard.",
    subtypes={"Cave"}
)

ECHOING_DEEP = make_land(
    name="Echoing Deep",
    text="As Echoing Deep enters, you may reveal a Cave card from your hand. If you don't, Echoing Deep enters tapped. {T}: Add one mana of any color.",
    subtypes={"Cave"}
)

CAVERNOUS_MAWS = make_land(
    name="Cavernous Maw",
    text="{T}: Add {C}. {2}, {T}: Until end of turn, Cavernous Maw becomes a 3/3 colorless Elemental creature with 'Whenever this creature attacks, target land you control becomes a copy of Cavernous Maw until end of turn.' It's still a land.",
    subtypes={"Cave"}
)


# =============================================================================
# INSTANTS & SORCERIES
# =============================================================================

def geological_appraiser_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - discover 3"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return make_discover_effect(obj, 3)
    return [make_etb_trigger(obj, etb_effect)]

GEOLOGICAL_APPRAISER = make_creature(
    name="Geological Appraiser",
    power=3, toughness=2,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Viashino", "Druid"},
    text="When Geological Appraiser enters, discover 3.",
    setup_interceptors=geological_appraiser_setup
)


def trumpeting_carnosaur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - discover 5"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return make_discover_effect(obj, 5)
    return [make_etb_trigger(obj, etb_effect)]

TRUMPETING_CARNOSAUR = make_creature(
    name="Trumpeting Carnosaur",
    power=7, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur"},
    text="When Trumpeting Carnosaur enters, discover 5. When you cast a spell using discover, Trumpeting Carnosaur deals damage equal to that spell's mana value to target creature you don't control.",
    setup_interceptors=trumpeting_carnosaur_setup
)


LIGHTNING_STRIKE = make_instant(
    name="Lightning Strike",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Lightning Strike deals 3 damage to any target."
)

BITTER_TRIUMPH = make_instant(
    name="Bitter Triumph",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, pay 3 life or discard a card. Destroy target creature or planeswalker."
)

GROWING_RITES_OF_ITLIMOC = make_enchantment(
    name="Growing Rites of Itlimoc",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    supertypes={"Legendary"},
    text="When Growing Rites of Itlimoc enters, look at the top four cards of your library. You may reveal a creature card and put it into your hand. Put the rest on the bottom of your library in any order. At the beginning of your end step, if you control four or more creatures, transform Growing Rites of Itlimoc."
)

PRIMAL_WELLSPRING = make_land(
    name="Primal Wellspring",
    text="{T}: Add one mana of any color. When this mana is spent to cast an instant or sorcery spell, copy that spell. You may choose new targets for the copy.",
    supertypes={"Legendary"}
)

GET_LOST = make_instant(
    name="Get Lost",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Destroy target creature, enchantment, or planeswalker. Its controller creates two Map tokens."
)

MOLTEN_COLLAPSE = make_sorcery(
    name="Molten Collapse",
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Choose one. If you descended this turn, you may choose both instead. - Destroy target creature with mana value 3 or less. - Destroy target noncreature, nonland permanent with mana value 3 or less."
)

ROAR_OF_THE_FIFTH_PEOPLE = make_sorcery(
    name="Roar of the Fifth People",
    mana_cost="{4}{R}{G}{W}",
    colors={Color.RED, Color.GREEN, Color.WHITE},
    text="Search your library for any number of Dinosaur creature cards, reveal them, and put them into your hand. Then shuffle."
)

SUBTERRANEAN_SCHOONER = make_artifact(
    name="Subterranean Schooner",
    mana_cost="{2}",
    text="Crew 1. Whenever Subterranean Schooner attacks, target creature you control explores.",
    subtypes={"Vehicle"}
)

SOUL_SHATTER = make_instant(
    name="Soul Shatter",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Each opponent sacrifices a creature or planeswalker with the highest mana value among creatures and planeswalkers they control."
)


# =============================================================================
# MORE CREATURES
# =============================================================================

SWASHBUCKLER_EXTRAORDINAIRE = make_creature(
    name="Swashbuckler Extraordinaire",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Pirate"},
    text="Double strike. Whenever Swashbuckler Extraordinaire attacks, you may sacrifice an artifact. If you do, creatures you control get +1/+0 until end of turn."
)

WAYLAYING_PIRATES = make_creature(
    name="Waylaying Pirates",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="Flash. When Waylaying Pirates enters, tap up to two target nonland permanents."
)

CORSAIR_CAPTAIN = make_creature(
    name="Corsair Captain",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="When Corsair Captain enters, create a Treasure token. Other Pirates you control get +1/+1."
)

DEATHBLOOM_GARDENER = make_creature(
    name="Deathbloom Gardener",
    power=1, toughness=1,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    text="Deathtouch. {T}: Add one mana of any color."
)

MARAUDING_BLIGHT_PRIEST = make_creature(
    name="Marauding Blight-Priest",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Cleric"},
    text="Whenever you gain life, each opponent loses 1 life."
)

MASTER_OF_DARK_RITES = make_creature(
    name="Master of Dark Rites",
    power=1, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Cleric"},
    text="{T}, Sacrifice another creature: Add {B}{B}{B}."
)

DEATHCAP_CULTIVATOR = make_creature(
    name="Deathcap Cultivator",
    power=2, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Druid"},
    text="{T}: Add {B} or {G}. Delirium - Deathcap Cultivator has deathtouch as long as there are four or more card types among cards in your graveyard."
)

STALWART_CAVE_DWELLER = make_creature(
    name="Stalwart Cave-Dweller",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Fungus"},
    text="Reach. When Stalwart Cave-Dweller enters, if you control a Cave, create a 1/1 black Fungus creature token."
)

FUNGAL_REBIRTH = make_instant(
    name="Fungal Rebirth",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Return target permanent card from your graveyard to your hand. If a creature died this turn, create two 1/1 green Saproling creature tokens."
)

SCYTHECLAW_RAPTOR = make_creature(
    name="Scytheclaw Raptor",
    power=5, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Trample. When Scytheclaw Raptor enters, you may have it fight target creature you don't control."
)

KNIGHT_OF_THE_STAMPEDE = make_creature(
    name="Knight of the Stampede",
    power=2, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Knight"},
    text="Dinosaur spells you cast cost {2} less to cast."
)

BURNING_SUNS_AVATAR = make_creature(
    name="Burning Sun's Avatar",
    power=6, toughness=6,
    mana_cost="{3}{R}{R}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur", "Avatar"},
    text="When Burning Sun's Avatar enters, it deals 3 damage to target opponent or planeswalker and 3 damage to up to one target creature."
)

REGISAUR_ALPHA = make_creature(
    name="Regisaur Alpha",
    power=4, toughness=4,
    mana_cost="{3}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Dinosaur"},
    text="Other Dinosaurs you control have haste. When Regisaur Alpha enters, create a 3/3 green Dinosaur creature token with trample."
)

FORERUNNER_OF_THE_EMPIRE = make_creature(
    name="Forerunner of the Empire",
    power=1, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="When Forerunner of the Empire enters, you may search your library for a Dinosaur card, reveal it, then shuffle and put that card on top. Whenever a Dinosaur enters the battlefield under your control, you may have Forerunner of the Empire deal 1 damage to each creature."
)

TEMPLE_THIEF = make_creature(
    name="Temple Thief",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="Temple Thief can't be blocked by enchanted creatures."
)

DIRE_FLEET_CAPTAIN = make_creature(
    name="Dire Fleet Captain",
    power=2, toughness=2,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Orc", "Pirate"},
    text="Whenever Dire Fleet Captain attacks, it gets +1/+1 until end of turn for each other attacking Pirate."
)

FATHOM_FLEET_CAPTAIN = make_creature(
    name="Fathom Fleet Captain",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate"},
    text="Menace. Whenever Fathom Fleet Captain attacks, if you control another nontoken Pirate, you may pay {2}. If you do, create a 2/2 black Pirate creature token with menace."
)

STORM_FLEET_SPRINTER = make_creature(
    name="Storm Fleet Sprinter",
    power=2, toughness=2,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Pirate"},
    text="Haste. Storm Fleet Sprinter can't be blocked."
)

BRASS_HERALD = make_artifact_creature(
    name="Brass's Bounty",
    power=2, toughness=2,
    mana_cost="{5}",
    colors=set(),
    subtypes={"Golem"},
    text="As Brass's Herald enters, choose a creature type. When Brass's Herald enters, reveal the top four cards of your library. Put all cards of the chosen type revealed this way into your hand and the rest on the bottom of your library."
)

CENOTE_SCOUT = make_creature(
    name="Cenote Scout",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Merfolk", "Scout"},
    text="When Cenote Scout enters, it explores."
)

WILDGROWTH_WALKER = make_creature(
    name="Wildgrowth Walker",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental"},
    text="Whenever a creature you control explores, put a +1/+1 counter on Wildgrowth Walker and you gain 3 life."
)

PATH_OF_DISCOVERY = make_enchantment(
    name="Path of Discovery",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Whenever a creature enters the battlefield under your control, it explores."
)

CURIOUS_OBSESSION = make_enchantment(
    name="Curious Obsession",
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Aura"},
    text="Enchant creature. Enchanted creature gets +1/+1 and has 'Whenever this creature deals combat damage to a player, draw a card.' At the beginning of your end step, if you didn't attack with a creature this turn, sacrifice Curious Obsession."
)

DROWN_IN_THE_LOCH = make_instant(
    name="Drown in the Loch",
    mana_cost="{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    text="Choose one - Counter target spell with mana value less than or equal to the number of cards in its controller's graveyard. - Destroy target creature with mana value less than or equal to the number of cards in its controller's graveyard."
)

COSMIUM_CONFLUENCE = make_sorcery(
    name="Cosmium Confluence",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Choose three. You may choose the same mode more than once. - Put a +1/+1 counter on each creature you control. - Choose land or artifact. Destroy all permanents of that type. - Search your library for a Cave card, put it onto the battlefield, then shuffle."
)

HELPING_HAND = make_instant(
    name="Helping Hand",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Return target creature card with mana value 3 or less from your graveyard to the battlefield tapped."
)


# =============================================================================
# EXPORT DICTIONARY
# =============================================================================

LOST_CAVERNS_IXALAN_CARDS = {
    # White
    "Ojer Taq, Deepest Foundation": OJER_TAQ,
    "Clavileno, First of the Blessed": CLAVILENO,
    "Bartolome del Presidio": BARTOLOME_DEL_PRESIDIO,
    "Dusk Legion Sergeant": DUSK_LEGION_SERGEANT,
    "Envoy of Okinec Ahau": ENVOY_OF_OKINEC_AHAU,
    "Sanguine Evangelist": SANGUINE_EVANGELIST,
    "Dusk Rose Reliquary": DUSK_ROSE_RELIQUARY,
    "Legion Conquistador": LEGION_CONQUISTADOR,
    "Paladin of the Bloodstained": PALADIN_OF_THE_BLOODSTAINED,
    "Glorifier of Suffering": GLORIFIER_OF_SUFFERING,
    "Penitent Nomad": PENITENT_NOMAD,

    # Blue
    "Ojer Pakpatiq, Deepest Epoch": OJER_PAKPATIQ,
    "Hakbal of the Surging Soul": HAKBAL,
    "Tishana, Voice of Thunder": TISHANA,
    "Waterwind Scout": WATERWIND_SCOUT,
    "Deeproot Pilgrimage": DEEPROOT_PILGRIMAGE,
    "River Herald Scout": RIVER_HERALD_SCOUT,
    "Jade Bearer": JADE_BEARER,
    "Sentinel of the Nameless City": SENTINEL_OF_THE_NAMELESS_CITY,
    "Nicanzil, Current Conductor": NICANZIL_CURRENT_CONDUCTOR,
    "Singer of Swift Rivers": SINGER_OF_SWIFT_RIVERS,
    "Kitesail Larcenist": KITESAIL_LARCENIST,
    "Waylaying Pirates": WAYLAYING_PIRATES,
    "Corsair Captain": CORSAIR_CAPTAIN,
    "Waker of Waves": WAKER_OF_WAVES,
    "Deepfathom Skulker": DEEPFATHOM_SKULKER,

    # Black
    "Aclazotz, Deepest Betrayal": ACLAZOTZ,
    "Vito, Fanatic of Aclazotz": VITO_FANATIC,
    "Bloodletter of Aclazotz": BLOODLETTER_OF_ACLAZOTZ,
    "Defossilize": DEFOSSILIZE,
    "Dead Weight": DEAD_WEIGHT,
    "Dusk Legion Zealot": DUSK_LEGION_ZEALOT,
    "Vampire Opportunist": VAMPIRE_OPPORTUNIST,
    "Skullcap Snail": SKULLCAP_SNAIL,
    "Chupacabra Echo": CHUPACABRA_ECHO,
    "Malamet Veteran": MALAMET_VETERAN,
    "Souls of the Lost": SOULS_OF_THE_LOST,
    "Marauding Blight-Priest": MARAUDING_BLIGHT_PRIEST,
    "Master of Dark Rites": MASTER_OF_DARK_RITES,
    "Temple Thief": TEMPLE_THIEF,
    "Fathom Fleet Captain": FATHOM_FLEET_CAPTAIN,
    "Soul Shatter": SOUL_SHATTER,
    "Bitter Triumph": BITTER_TRIUMPH,

    # Red
    "Ojer Axonil, Deepest Might": OJER_AXONIL,
    "Captain Storm, Cosmium Raider": CAPTAIN_STORM,
    "Etali, Primal Conqueror": ETALI_PRIMAL_CONQUEROR,
    "Burning Sun's Cavalry": BURNING_SUNS_CAVALRY,
    "Brazen Buccaneer": BRAZEN_BUCCANEER,
    "Dire Fleet Daredevil": DIRE_FLEET_DAREDEVIL,
    "Goblin Trailblazer": GOBLIN_TRAILBLAZER,
    "Frilled Deathspitter": FRILLED_DEATHSPITTER,
    "Rampaging Ferocidon": RAMPAGING_FEROCIDON,
    "Magmatic Galleon": MAGMATIC_GALLEON,
    "Trumpeting Carnosaur": TRUMPETING_CARNOSAUR,
    "Lightning Strike": LIGHTNING_STRIKE,
    "Swashbuckler Extraordinaire": SWASHBUCKLER_EXTRAORDINAIRE,
    "Burning Sun's Avatar": BURNING_SUNS_AVATAR,
    "Forerunner of the Empire": FORERUNNER_OF_THE_EMPIRE,
    "Dire Fleet Captain": DIRE_FLEET_CAPTAIN,
    "Inti, Seneschal of the Sun": INTI_SENESCHAL,

    # Green
    "Ojer Kaslem, Deepest Growth": OJER_KASLEM,
    "Ghalta, Stampede Tyrant": GHALTA_STAMPEDE_TYRANT,
    "Zoyowa Lava-Tongue": ZOYOWA_LAVA_TONGUE,
    "Ripjaw Raptor": RIPJAW_RAPTOR,
    "Merfolk Branchwalker": MERFOLK_BRANCHWALKER,
    "Jadelight Ranger": JADELIGHT_RANGER,
    "Wayward Swordtooth": WAYWARD_SWORDTOOTH,
    "Thrashing Brontodon": THRASHING_BRONTODON,
    "Colossal Dreadmaw": COLOSSAL_DREADMAW,
    "Tyrranax Rex": TYRRANAX_REX,
    "Topiary Stomper": TOPIARY_STOMPER,
    "Carnage Tyrant": CARNAGE_TYRANT,
    "Intrepid Paleontologist": INTREPID_PALEONTOLOGIST,
    "Deathbloom Gardener": DEATHBLOOM_GARDENER,
    "Deathcap Cultivator": DEATHCAP_CULTIVATOR,
    "Stalwart Cave-Dweller": STALWART_CAVE_DWELLER,
    "Fungal Rebirth": FUNGAL_REBIRTH,
    "Scytheclaw Raptor": SCYTHECLAW_RAPTOR,
    "Knight of the Stampede": KNIGHT_OF_THE_STAMPEDE,
    "Cenote Scout": CENOTE_SCOUT,
    "Wildgrowth Walker": WILDGROWTH_WALKER,
    "Path of Discovery": PATH_OF_DISCOVERY,
    "Cosmium Confluence": COSMIUM_CONFLUENCE,

    # Multicolor
    "Quintorius Kand": QUINTORIUS_LOREMASTER,
    "Huatli, Poet of Unity": HUATLI_POET_OF_UNITY,
    "Kellan, Daring Traveler": KELLAN_DARING_TRAVELER,
    "Admiral Brass, Unsinkable": ADMIRAL_BRASS_UNSINKABLE,
    "Kumena, Tyrant of Orazca": KUMENA_TYRANT,
    "Zacama, Primal Calamity": ZACAMA_PRIMAL_CALAMITY,
    "Gishath, Sun's Avatar": GISHATH_SUNS_AVATAR,
    "Hostage Taker": HOSTAGE_TAKER,
    "Geological Appraiser": GEOLOGICAL_APPRAISER,
    "Regisaur Alpha": REGISAUR_ALPHA,
    "Storm Fleet Sprinter": STORM_FLEET_SPRINTER,
    "Molten Collapse": MOLTEN_COLLAPSE,
    "Roar of the Fifth People": ROAR_OF_THE_FIFTH_PEOPLE,
    "Drown in the Loch": DROWN_IN_THE_LOCH,

    # Artifacts
    "Chimil, the Inner Sun": CHIMIL,
    "Tarrian's Soulcleaver": TARRIAN_SOULCLEAVER,
    "The Thousand Moons Smithy": THOUSAND_MOONS_SMITHY,
    "Matzalantli, the Great Door": MATZALANTLI,
    "Oltec Matterweaver": OLTEC_MATTERWEAVER,
    "Fabrication Foundry": FABRICATION_FOUNDRY,
    "The Enigma Jewel": DIDACTS_HEXPROOF,
    "Throne of the Grim Captain": THRONE_OF_THE_GRIM_CAPTAIN,
    "Map": MAP_TOKEN,
    "Cosmium Catalyst": COSMIUM_CATALYST,
    "Subterranean Schooner": SUBTERRANEAN_SCHOONER,
    "Brass's Herald": BRASS_HERALD,

    # Lands
    "Cavern of Souls": CAVERN_OF_SOULS,
    "Unclaimed Territory": UNCLAIMED_TERRITORY,
    "Restless Anchorage": RESTLESS_ANCHORAGE,
    "Restless Reef": RESTLESS_REEF,
    "Restless Ridgeline": RESTLESS_RIDGELINE,
    "Restless Vents": RESTLESS_VENTS,
    "Restless Prairie": RESTLESS_PRAIRIE,
    "Hidden Cataract": HIDDEN_CATARACT,
    "Hidden Volcano": HIDDEN_VOLCANO,
    "Hidden Nursery": HIDDEN_NURSERY,
    "Hidden Necropolis": HIDDEN_NECROPOLIS,
    "Hidden Courtyard": HIDDEN_COURTYARD,
    "Echoing Deep": ECHOING_DEEP,
    "Cavernous Maw": CAVERNOUS_MAWS,
    "Growing Rites of Itlimoc": GROWING_RITES_OF_ITLIMOC,
    "Primal Wellspring": PRIMAL_WELLSPRING,

    # Instants/Sorceries/Enchantments
    "Get Lost": GET_LOST,
    "Curious Obsession": CURIOUS_OBSESSION,
    "Helping Hand": HELPING_HAND,
}
