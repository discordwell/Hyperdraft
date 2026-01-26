"""
Wilds_of_Eldraine (WOE) Card Implementations

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
from src.cards.interceptor_helpers import (
    make_etb_trigger, make_death_trigger, make_attack_trigger,
    make_static_pt_boost, make_keyword_grant, make_spell_cast_trigger,
    make_upkeep_trigger, make_end_step_trigger, make_damage_trigger,
    other_creatures_you_control, other_creatures_with_subtype,
    creatures_you_control, creatures_with_subtype, create_target_choice,
    create_modal_choice
)


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
# INTERCEPTOR SETUP FUNCTIONS
# =============================================================================

# --- White Cards ---

def charmed_clothier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Royal Role token attached to another target creature you control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Royal Role',
                'controller': obj.controller,
                'types': [CardType.ENCHANTMENT],
                'subtypes': ['Aura', 'Role'],
                'is_token': True,
                'grants_power': 1,
                'grants_toughness': 1,
                'grants_ward': 1
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def cursed_courtier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Cursed Role token attached to it."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Cursed Role',
                'controller': obj.controller,
                'attach_to': obj.id,
                'types': [CardType.ENCHANTMENT],
                'subtypes': ['Aura', 'Role'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def discerning_financier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your upkeep, if an opponent controls more lands than you, create a Treasure token."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        # Count lands for controller
        controller_lands = sum(1 for o in state.objects.values()
                              if o.controller == obj.controller and
                              CardType.LAND in o.characteristics.types and
                              o.zone == ZoneType.BATTLEFIELD)
        # Check if any opponent has more
        for player_id in state.players:
            if player_id != obj.controller:
                opponent_lands = sum(1 for o in state.objects.values()
                                    if o.controller == player_id and
                                    CardType.LAND in o.characteristics.types and
                                    o.zone == ZoneType.BATTLEFIELD)
                if opponent_lands > controller_lands:
                    return [Event(
                        type=EventType.OBJECT_CREATED,
                        payload={
                            'name': 'Treasure',
                            'controller': obj.controller,
                            'types': [CardType.ARTIFACT],
                            'subtypes': ['Treasure'],
                            'is_token': True
                        },
                        source=obj.id
                    )]
        return []
    return [make_upkeep_trigger(obj, upkeep_effect)]


def knight_of_doves_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever an enchantment you control is put into a graveyard from the battlefield, create a 1/1 white Bird creature token with flying."""
    def enchantment_dies_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_obj = state.objects.get(event.payload.get('object_id'))
        if not dying_obj:
            return False
        return (dying_obj.controller == obj.controller and
                CardType.ENCHANTMENT in dying_obj.characteristics.types)

    def create_bird(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Bird Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Bird'],
                'colors': [Color.WHITE],
                'abilities': ['flying'],
                'is_token': True
            },
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=enchantment_dies_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=create_bird(e, s)),
        duration='while_on_battlefield'
    )]


def moonshaker_cavalry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, creatures you control gain flying and get +X/+X until end of turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        creature_count = sum(1 for o in state.objects.values()
                            if o.controller == obj.controller and
                            CardType.CREATURE in o.characteristics.types and
                            o.zone == ZoneType.BATTLEFIELD)
        events = []
        for o in state.objects.values():
            if (o.controller == obj.controller and
                CardType.CREATURE in o.characteristics.types and
                o.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.TEMPORARY_EFFECT,
                    payload={
                        'object_id': o.id,
                        'power_mod': creature_count,
                        'toughness_mod': creature_count,
                        'grant_abilities': ['flying'],
                        'duration': 'end_of_turn'
                    },
                    source=obj.id
                ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def protective_parents_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, create a Young Hero Role token attached to up to one target creature you control."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Young Hero Role',
                'controller': obj.controller,
                'types': [CardType.ENCHANTMENT],
                'subtypes': ['Aura', 'Role'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def savior_of_the_sleeping_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever an enchantment you control is put into a graveyard from the battlefield, put a +1/+1 counter on this creature."""
    def enchantment_dies_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_obj = state.objects.get(event.payload.get('object_id'))
        if not dying_obj:
            return False
        return (dying_obj.controller == obj.controller and
                CardType.ENCHANTMENT in dying_obj.characteristics.types)

    def add_counter(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=enchantment_dies_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=add_counter(e, s)),
        duration='while_on_battlefield'
    )]


def stockpiling_celebrant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you may return another target nonland permanent you control to its owner's hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting, simplified to just trigger scry if bounce happens
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def a_tale_for_the_ages_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enchanted creatures you control get +2/+2."""
    def affects_enchanted_creatures(target: GameObject, state: GameState) -> bool:
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        # Check if creature is enchanted (has aura attached)
        for o in state.objects.values():
            if (CardType.ENCHANTMENT in o.characteristics.types and
                'Aura' in o.characteristics.subtypes and
                o.zone == ZoneType.BATTLEFIELD and
                o.state.attached_to == target.id):
                return True
        return False

    return make_static_pt_boost(obj, 2, 2, affects_enchanted_creatures)


# --- Blue Cards ---

def archive_dragon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, scry 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def mocking_sprite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Instant and sorcery spells you cast cost {1} less to cast."""
    def cost_reduction_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_COST:
            return False
        spell_id = event.payload.get('spell_id')
        spell = state.objects.get(spell_id)
        if not spell:
            return False
        if spell.controller != obj.controller:
            return False
        types = spell.characteristics.types
        return CardType.INSTANT in types or CardType.SORCERY in types

    def reduce_cost(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        current_reduction = new_event.payload.get('generic_reduction', 0)
        new_event.payload['generic_reduction'] = current_reduction + 1
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=cost_reduction_filter,
        handler=reduce_cost,
        duration='while_on_battlefield'
    )]


def splashy_spellcaster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an instant or sorcery spell, create a Sorcerer Role token."""
    def spell_cast_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Sorcerer Role',
                'controller': obj.controller,
                'types': [CardType.ENCHANTMENT],
                'subtypes': ['Aura', 'Role'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_spell_cast_trigger(
        obj, spell_cast_effect,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY}
    )]


def stormkeld_prowler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a spell with mana value 5 or greater, put two +1/+1 counters on this creature."""
    def big_spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 2},
            source=obj.id
        )]
    return [make_spell_cast_trigger(obj, big_spell_effect, mana_value_min=5)]


def talions_messenger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you attack with one or more Faeries, draw a card, then discard a card."""
    def faerie_attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        return (attacker.controller == obj.controller and
                'Faerie' in attacker.characteristics.subtypes)

    def draw_discard_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=faerie_attack_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=draw_discard_effect(e, s)),
        duration='while_on_battlefield'
    )]


# --- Black Cards ---

def ashioks_reaper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever an enchantment you control is put into a graveyard from the battlefield, draw a card."""
    def enchantment_dies_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_obj = state.objects.get(event.payload.get('object_id'))
        if not dying_obj:
            return False
        return (dying_obj.controller == obj.controller and
                CardType.ENCHANTMENT in dying_obj.characteristics.types)

    def draw_card(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=enchantment_dies_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=draw_card(e, s)),
        duration='while_on_battlefield'
    )]


def dream_spoilers_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a spell during an opponent's turn, up to one target creature an opponent controls gets -1/-1 until end of turn."""
    def opponent_turn_cast_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        return state.active_player != obj.controller

    def minus_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={'power_mod': -1, 'toughness_mod': -1, 'duration': 'end_of_turn'},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=opponent_turn_cast_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=minus_effect(e, s)),
        duration='while_on_battlefield'
    )]


def faerie_dreamthief_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, surveil 1."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def high_fae_negotiator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, if it was bargained, each opponent loses 3 life and you gain 3 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        if not event.payload.get('bargained', False):
            return []
        events = []
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -3},
                    source=obj.id
                ))
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def hopeless_nightmare_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this enchantment enters, each opponent discards a card and loses 2 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DISCARD,
                    payload={'player': player_id, 'amount': 1},
                    source=obj.id
                ))
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -2},
                    source=obj.id
                ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def lord_skitter_sewer_king_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of combat on your turn, create a 1/1 black Rat creature token."""
    def combat_trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'combat':
            return False
        return state.active_player == obj.controller

    def create_rat(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Rat Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Rat'],
                'colors': [Color.BLACK],
                'is_token': True
            },
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_trigger_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=create_rat(e, s)),
        duration='while_on_battlefield'
    )]


def mintstrosity_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, create a Food token."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Food Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Food'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def scream_puff_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature deals combat damage to a player, create a Food token."""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target not in state.players:
            return []
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Food Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Food'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]


def sweettooth_witch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Food token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Food Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Food'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def tangled_colony_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, create X 1/1 black Rat creature tokens, where X is the damage dealt to it this turn."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        damage_taken = obj.state.damage_marked or 0
        if damage_taken <= 0:
            return []
        events = []
        for _ in range(damage_taken):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Rat Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Rat'],
                    'colors': [Color.BLACK],
                    'is_token': True
                },
                source=obj.id
            ))
        return events
    return [make_death_trigger(obj, death_effect)]


def voracious_vermin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a 1/1 black Rat creature token.
    Whenever another creature you control dies, put a +1/+1 counter on this creature."""
    interceptors = []

    # ETB trigger
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Rat Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Rat'],
                'colors': [Color.BLACK],
                'is_token': True
            },
            source=obj.id
        )]
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Creature dies trigger
    def creature_dies_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        if dying_id == obj.id:
            return False
        dying_obj = state.objects.get(dying_id)
        if not dying_obj:
            return False
        return (dying_obj.controller == obj.controller and
                CardType.CREATURE in dying_obj.characteristics.types)

    def add_counter(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=creature_dies_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=add_counter(e, s)),
        duration='while_on_battlefield'
    ))

    return interceptors


def warehouse_tabby_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever an enchantment you control is put into a graveyard from the battlefield, create a 1/1 black Rat creature token."""
    def enchantment_dies_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_obj = state.objects.get(event.payload.get('object_id'))
        if not dying_obj:
            return False
        return (dying_obj.controller == obj.controller and
                CardType.ENCHANTMENT in dying_obj.characteristics.types)

    def create_rat(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Rat Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Rat'],
                'colors': [Color.BLACK],
                'is_token': True
            },
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=enchantment_dies_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=create_rat(e, s)),
        duration='while_on_battlefield'
    )]


def wicked_visitor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever an enchantment you control is put into a graveyard from the battlefield, each opponent loses 1 life."""
    def enchantment_dies_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_obj = state.objects.get(event.payload.get('object_id'))
        if not dying_obj:
            return False
        return (dying_obj.controller == obj.controller and
                CardType.ENCHANTMENT in dying_obj.characteristics.types)

    def opponent_life_loss(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -1},
                    source=obj.id
                ))
        return events

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=enchantment_dies_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=opponent_life_loss(e, s)),
        duration='while_on_battlefield'
    )]


# --- Red Cards ---

def charming_scoundrel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, choose one: Discard then draw, create Treasure, or create Wicked Role."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Default to creating a Treasure token
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Treasure',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def edgewall_pack_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a 1/1 black Rat creature token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Rat Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Rat'],
                'colors': [Color.BLACK],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def harried_spearguard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, create a 1/1 black Rat creature token."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Rat Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Rat'],
                'colors': [Color.BLACK],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def redcap_gutterdweller_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create two 1/1 black Rat creature tokens."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for _ in range(2):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Rat Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Rat'],
                    'colors': [Color.BLACK],
                    'is_token': True
                },
                source=obj.id
            ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def redcap_thief_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Treasure token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Treasure',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def unruly_catapult_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an instant or sorcery spell, untap this creature."""
    def spell_cast_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.UNTAP,
            payload={'object_id': obj.id},
            source=obj.id
        )]
    return [make_spell_cast_trigger(
        obj, spell_cast_effect,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY}
    )]


# =============================================================================
# SPELL RESOLVE FUNCTIONS
# =============================================================================

def _monstrous_rage_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Monstrous Rage after target selection - buff +2/+0, grant trample, create Monster Role."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    # Target must be a creature on the battlefield
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []  # Target no longer valid

    return [
        # +2/+0 until end of turn
        Event(
            type=EventType.PUMP,
            payload={
                'object_id': target_id,
                'power': 2,
                'toughness': 0,
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        ),
        # Grant trample until end of turn
        Event(
            type=EventType.GRANT_KEYWORD,
            payload={
                'object_id': target_id,
                'keyword': 'trample',
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        ),
        # Create Monster Role token attached to target
        Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Monster Role',
                'controller': choice.player,
                'attach_to': target_id,
                'types': [CardType.ENCHANTMENT],
                'subtypes': ['Aura', 'Role'],
                'is_token': True
            },
            source=choice.source_id
        )
    ]


def monstrous_rage_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Monstrous Rage: Target creature gets +2/+0 and gains trample until end of turn.
    Create a Monster Role token attached to it (gives +1/+1 and trample).

    Creates a target choice for the caster. Returns empty events to pause resolution.
    """
    # Find the spell on the stack to determine who cast it
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Monstrous Rage":
                caster_id = obj.controller
                spell_id = obj.id
                break

    # Fallback to active player if we can't find the spell
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "monstrous_rage_spell"

    # Find valid targets: creatures the caster controls
    valid_targets = []
    for obj in state.objects.values():
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types and
            obj.controller == caster_id):
            valid_targets.append(obj.id)

    if not valid_targets:
        # No legal targets, spell fizzles
        return []

    # Create target choice for the player
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to buff with Monstrous Rage (+2/+0, trample, Monster Role)",
        min_targets=1,
        max_targets=1
    )

    # Set up callback for when target is selected
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _monstrous_rage_execute

    # Return empty events to pause resolution until choice is submitted
    return []


def _torch_the_tower_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Torch the Tower after target selection - deal 2 or 3 damage (if bargained)."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    # Check if the spell was bargained (stored in callback_data)
    was_bargained = choice.callback_data.get('bargained', False)
    damage_amount = 3 if was_bargained else 2

    # Target must be a creature or planeswalker
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []  # Target no longer valid

    events = [Event(
        type=EventType.DAMAGE,
        payload={
            'target': target_id,
            'amount': damage_amount,
            'source': choice.source_id,
            'is_combat': False,
            'exile_on_death': True  # If this damage kills the permanent, exile it instead
        },
        source=choice.source_id
    )]

    # If bargained, also scry 1
    if was_bargained:
        events.append(Event(
            type=EventType.SCRY,
            payload={'player': choice.player, 'amount': 1},
            source=choice.source_id
        ))

    return events


def torch_the_tower_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Torch the Tower: Deal 2 damage to target creature or planeswalker.
    If bargained, deals 3 damage instead and you scry 1.

    Creates a target choice for the caster. Returns empty events to pause resolution.
    """
    # Find the spell on the stack to determine who cast it and if it was bargained
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    was_bargained = False
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Torch the Tower":
                caster_id = obj.controller
                spell_id = obj.id
                # Check if the spell was bargained (stored in state)
                was_bargained = getattr(obj.state, 'bargained', False) if obj.state else False
                break

    # Fallback to active player if we can't find the spell
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "torch_the_tower_spell"

    damage_amount = 3 if was_bargained else 2

    # Find valid targets: creatures and planeswalkers only (not players)
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types or CardType.PLANESWALKER in obj.characteristics.types:
                valid_targets.append(obj.id)

    if not valid_targets:
        # No legal targets, spell fizzles
        return []

    # Create target choice for the player
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt=f"Choose a creature or planeswalker for Torch the Tower ({damage_amount} damage)",
        min_targets=1,
        max_targets=1
    )

    # Set up callback for when target is selected
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _torch_the_tower_execute
    choice.callback_data['bargained'] = was_bargained

    # Return empty events to pause resolution until choice is submitted
    return []


# =============================================================================
# ADDITIONAL SPELL RESOLVE FUNCTIONS
# =============================================================================

# --- BREAK THE SPELL ---
def _break_the_spell_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Break the Spell - destroy target enchantment, draw if you controlled it."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    controller_owned = target.controller == choice.player or getattr(target.state, 'is_token', False)
    events = [Event(
        type=EventType.DESTROY,
        payload={'object_id': target_id},
        source=choice.source_id
    )]
    if controller_owned:
        events.append(Event(type=EventType.DRAW, payload={'player': choice.player, 'amount': 1}, source=choice.source_id))
    return events


def break_the_spell_resolve(targets: list, state: GameState) -> list[Event]:
    """Destroy target enchantment. If a permanent you controlled or a token was destroyed this way, draw a card."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Break the Spell":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "break_the_spell_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.ENCHANTMENT in obj.characteristics.types]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose an enchantment to destroy"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _break_the_spell_execute
    return []


# --- STROKE OF MIDNIGHT ---
def _stroke_of_midnight_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Stroke of Midnight - destroy nonland permanent, give controller a 1/1 Human."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    target_controller = target.controller
    return [
        Event(type=EventType.DESTROY, payload={'object_id': target_id}, source=choice.source_id),
        Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Human Token',
                'controller': target_controller,
                'power': 1, 'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Human'],
                'colors': [Color.WHITE],
                'is_token': True
            },
            source=choice.source_id
        )
    ]


def stroke_of_midnight_resolve(targets: list, state: GameState) -> list[Event]:
    """Destroy target nonland permanent. Its controller creates a 1/1 white Human creature token."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Stroke of Midnight":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "stroke_of_midnight_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.LAND not in obj.characteristics.types]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a nonland permanent to destroy"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _stroke_of_midnight_execute
    return []


# --- CANDY GRAPPLE ---
def _candy_grapple_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Candy Grapple - give -3/-3 or -5/-5 if bargained."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    was_bargained = choice.callback_data.get('bargained', False)
    mod = -5 if was_bargained else -3
    return [Event(
        type=EventType.PUMP,
        payload={'object_id': target_id, 'power': mod, 'toughness': mod, 'duration': 'end_of_turn'},
        source=choice.source_id
    )]


def candy_grapple_resolve(targets: list, state: GameState) -> list[Event]:
    """Target creature gets -3/-3 until end of turn. If bargained, -5/-5 instead."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    was_bargained = False
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Candy Grapple":
                caster_id = obj.controller
                spell_id = obj.id
                was_bargained = getattr(obj.state, 'bargained', False) if obj.state else False
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "candy_grapple_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types]
    if not valid_targets:
        return []

    mod = -5 if was_bargained else -3
    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt=f"Choose a creature to get {mod}/{mod} until end of turn"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _candy_grapple_execute
    choice.callback_data['bargained'] = was_bargained
    return []


# --- FEED THE CAULDRON ---
def _feed_the_cauldron_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Feed the Cauldron - destroy creature MV 3 or less, create Food if your turn."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    events = [Event(type=EventType.DESTROY, payload={'object_id': target_id}, source=choice.source_id)]
    is_your_turn = choice.callback_data.get('is_your_turn', False)
    if is_your_turn:
        events.append(Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Food Token', 'controller': choice.player,
                     'types': [CardType.ARTIFACT], 'subtypes': ['Food'], 'is_token': True},
            source=choice.source_id
        ))
    return events


def feed_the_cauldron_resolve(targets: list, state: GameState) -> list[Event]:
    """Destroy target creature with mana value 3 or less. If it's your turn, create a Food token."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Feed the Cauldron":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "feed_the_cauldron_spell"

    def get_mana_value(o):
        mc = o.characteristics.mana_cost or ""
        return sum(1 for c in mc if c in 'WUBRG') + sum(int(c) for c in mc if c.isdigit())

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types
                     and get_mana_value(obj) <= 3]
    if not valid_targets:
        return []

    is_your_turn = state.active_player == caster_id
    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature with mana value 3 or less to destroy"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _feed_the_cauldron_execute
    choice.callback_data['is_your_turn'] = is_your_turn
    return []


# --- SUGAR RUSH ---
def _sugar_rush_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Sugar Rush - +3/+0 and draw a card."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(type=EventType.PUMP, payload={'object_id': target_id, 'power': 3, 'toughness': 0, 'duration': 'end_of_turn'}, source=choice.source_id),
        Event(type=EventType.DRAW, payload={'player': choice.player, 'amount': 1}, source=choice.source_id)
    ]


def sugar_rush_resolve(targets: list, state: GameState) -> list[Event]:
    """Target creature gets +3/+0 until end of turn. Draw a card."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Sugar Rush":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "sugar_rush_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to get +3/+0"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _sugar_rush_execute
    return []


# --- TAKEN BY NIGHTMARES ---
def _taken_by_nightmares_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Taken by Nightmares - exile creature, scry 2 if you control an enchantment."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    events = [Event(type=EventType.EXILE, payload={'object_id': target_id}, source=choice.source_id)]
    controls_enchantment = choice.callback_data.get('controls_enchantment', False)
    if controls_enchantment:
        events.append(Event(type=EventType.SCRY, payload={'player': choice.player, 'amount': 2}, source=choice.source_id))
    return events


def taken_by_nightmares_resolve(targets: list, state: GameState) -> list[Event]:
    """Exile target creature. If you control an enchantment, scry 2."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Taken by Nightmares":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "taken_by_nightmares_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types]
    if not valid_targets:
        return []

    controls_enchantment = any(
        obj.controller == caster_id and obj.zone == ZoneType.BATTLEFIELD and CardType.ENCHANTMENT in obj.characteristics.types
        for obj in state.objects.values()
    )
    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to exile"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _taken_by_nightmares_execute
    choice.callback_data['controls_enchantment'] = controls_enchantment
    return []


# --- TITANIC GROWTH ---
def _titanic_growth_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Titanic Growth - +4/+4 until end of turn."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.PUMP,
        payload={'object_id': target_id, 'power': 4, 'toughness': 4, 'duration': 'end_of_turn'},
        source=choice.source_id
    )]


def titanic_growth_resolve(targets: list, state: GameState) -> list[Event]:
    """Target creature gets +4/+4 until end of turn."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Titanic Growth":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "titanic_growth_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to get +4/+4"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _titanic_growth_execute
    return []


# --- LEAPING AMBUSH ---
def _leaping_ambush_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Leaping Ambush - +1/+3, reach, untap."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(type=EventType.PUMP, payload={'object_id': target_id, 'power': 1, 'toughness': 3, 'duration': 'end_of_turn'}, source=choice.source_id),
        Event(type=EventType.GRANT_KEYWORD, payload={'object_id': target_id, 'keyword': 'reach', 'duration': 'end_of_turn'}, source=choice.source_id),
        Event(type=EventType.UNTAP, payload={'object_id': target_id}, source=choice.source_id)
    ]


def leaping_ambush_resolve(targets: list, state: GameState) -> list[Event]:
    """Target creature gets +1/+3 and gains reach until end of turn. Untap it."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Leaping Ambush":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "leaping_ambush_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to get +1/+3 and reach"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _leaping_ambush_execute
    return []


# --- ROYAL TREATMENT ---
def _royal_treatment_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Royal Treatment - hexproof and Royal Role token."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(type=EventType.GRANT_KEYWORD, payload={'object_id': target_id, 'keyword': 'hexproof', 'duration': 'end_of_turn'}, source=choice.source_id),
        Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Royal Role',
                'controller': choice.player,
                'attach_to': target_id,
                'types': [CardType.ENCHANTMENT],
                'subtypes': ['Aura', 'Role'],
                'is_token': True,
                'grants_power': 1, 'grants_toughness': 1, 'grants_ward': 1
            },
            source=choice.source_id
        )
    ]


def royal_treatment_resolve(targets: list, state: GameState) -> list[Event]:
    """Target creature you control gains hexproof until end of turn. Create a Royal Role token attached to it."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Royal Treatment":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "royal_treatment_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types
                     and obj.controller == caster_id]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature you control to grant hexproof and a Royal Role"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _royal_treatment_execute
    return []


# --- KINDLED HEROISM ---
def _kindled_heroism_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Kindled Heroism - +1/+0, first strike, scry 1."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(type=EventType.PUMP, payload={'object_id': target_id, 'power': 1, 'toughness': 0, 'duration': 'end_of_turn'}, source=choice.source_id),
        Event(type=EventType.GRANT_KEYWORD, payload={'object_id': target_id, 'keyword': 'first_strike', 'duration': 'end_of_turn'}, source=choice.source_id),
        Event(type=EventType.SCRY, payload={'player': choice.player, 'amount': 1}, source=choice.source_id)
    ]


def kindled_heroism_resolve(targets: list, state: GameState) -> list[Event]:
    """Target creature gets +1/+0 and gains first strike until end of turn. Scry 1."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Kindled Heroism":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "kindled_heroism_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to get +1/+0 and first strike"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _kindled_heroism_execute
    return []


# --- WITCHSTALKER FRENZY ---
def _witchstalker_frenzy_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Witchstalker Frenzy - deal 5 damage to target creature."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': 5, 'source': choice.source_id, 'is_combat': False},
        source=choice.source_id
    )]


def witchstalker_frenzy_resolve(targets: list, state: GameState) -> list[Event]:
    """Witchstalker Frenzy deals 5 damage to target creature."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Witchstalker Frenzy":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "witchstalker_frenzy_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to deal 5 damage to"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _witchstalker_frenzy_execute
    return []


# --- CUT IN ---
def _cut_in_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Cut In - deal 4 damage to creature, create Young Hero Role on your creature."""
    target_id = selected[0] if selected else None
    role_target_id = selected[1] if len(selected) > 1 else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    events = [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': 4, 'source': choice.source_id, 'is_combat': False},
        source=choice.source_id
    )]
    if role_target_id:
        events.append(Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Young Hero Role',
                'controller': choice.player,
                'attach_to': role_target_id,
                'types': [CardType.ENCHANTMENT],
                'subtypes': ['Aura', 'Role'],
                'is_token': True
            },
            source=choice.source_id
        ))
    return events


def cut_in_resolve(targets: list, state: GameState) -> list[Event]:
    """Cut In deals 4 damage to target creature. Create a Young Hero Role attached to target creature you control."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Cut In":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "cut_in_spell"

    # All creatures are valid damage targets
    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to deal 4 damage to"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _cut_in_execute
    return []


# --- WATER WINGS ---
def _water_wings_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Water Wings - 4/4 base, flying, hexproof."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(type=EventType.TEMPORARY_EFFECT, payload={
            'object_id': target_id,
            'set_power': 4, 'set_toughness': 4,
            'duration': 'end_of_turn'
        }, source=choice.source_id),
        Event(type=EventType.GRANT_KEYWORD, payload={'object_id': target_id, 'keyword': 'flying', 'duration': 'end_of_turn'}, source=choice.source_id),
        Event(type=EventType.GRANT_KEYWORD, payload={'object_id': target_id, 'keyword': 'hexproof', 'duration': 'end_of_turn'}, source=choice.source_id)
    ]


def water_wings_resolve(targets: list, state: GameState) -> list[Event]:
    """Target creature you control has base power and toughness 4/4 and gains flying and hexproof until end of turn."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Water Wings":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "water_wings_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types
                     and obj.controller == caster_id]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to become 4/4 with flying and hexproof"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _water_wings_execute
    return []


# --- FREEZE IN PLACE ---
def _freeze_in_place_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Freeze in Place - tap, 3 stun counters, scry 2."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(type=EventType.TAP, payload={'object_id': target_id}, source=choice.source_id),
        Event(type=EventType.COUNTER_ADDED, payload={'object_id': target_id, 'counter_type': 'stun', 'amount': 3}, source=choice.source_id),
        Event(type=EventType.SCRY, payload={'player': choice.player, 'amount': 2}, source=choice.source_id)
    ]


def freeze_in_place_resolve(targets: list, state: GameState) -> list[Event]:
    """Tap target creature an opponent controls and put three stun counters on it. Scry 2."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Freeze in Place":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "freeze_in_place_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types
                     and obj.controller != caster_id]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose an opponent's creature to tap and stun"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _freeze_in_place_execute
    return []


# --- JOHANNS STOPGAP ---
def _johanns_stopgap_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Johann's Stopgap - return to hand, draw a card."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(type=EventType.ZONE_CHANGE, payload={
            'object_id': target_id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.HAND
        }, source=choice.source_id),
        Event(type=EventType.DRAW, payload={'player': choice.player, 'amount': 1}, source=choice.source_id)
    ]


def johanns_stopgap_resolve(targets: list, state: GameState) -> list[Event]:
    """Return target nonland permanent to its owner's hand. Draw a card."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Johann's Stopgap":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "johanns_stopgap_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.LAND not in obj.characteristics.types]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a nonland permanent to return to hand"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _johanns_stopgap_execute
    return []


# --- ARCHON'S GLORY ---
def _archons_glory_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Archon's Glory - +2/+2, and if bargained, flying and lifelink."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    was_bargained = choice.callback_data.get('bargained', False)
    events = [Event(type=EventType.PUMP, payload={'object_id': target_id, 'power': 2, 'toughness': 2, 'duration': 'end_of_turn'}, source=choice.source_id)]
    if was_bargained:
        events.append(Event(type=EventType.GRANT_KEYWORD, payload={'object_id': target_id, 'keyword': 'flying', 'duration': 'end_of_turn'}, source=choice.source_id))
        events.append(Event(type=EventType.GRANT_KEYWORD, payload={'object_id': target_id, 'keyword': 'lifelink', 'duration': 'end_of_turn'}, source=choice.source_id))
    return events


def archons_glory_resolve(targets: list, state: GameState) -> list[Event]:
    """Target creature gets +2/+2 until end of turn. If bargained, also flying and lifelink."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    was_bargained = False
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Archon's Glory":
                caster_id = obj.controller
                spell_id = obj.id
                was_bargained = getattr(obj.state, 'bargained', False) if obj.state else False
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "archons_glory_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to get +2/+2" + (" with flying and lifelink" if was_bargained else "")
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _archons_glory_execute
    choice.callback_data['bargained'] = was_bargained
    return []


# --- NOT DEAD AFTER ALL ---
def _not_dead_after_all_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Not Dead After All - grant return-on-death ability."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.TEMPORARY_EFFECT,
        payload={
            'object_id': target_id,
            'grant_ability': 'return_on_death_with_wicked_role',
            'duration': 'end_of_turn'
        },
        source=choice.source_id
    )]


def not_dead_after_all_resolve(targets: list, state: GameState) -> list[Event]:
    """Target creature you control gains death-return ability until end of turn."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Not Dead After All":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "not_dead_after_all_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types
                     and obj.controller == caster_id]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to grant death-return ability"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _not_dead_after_all_execute
    return []


# --- STONESPLITTER BOLT ---
def _stonesplitter_bolt_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Stonesplitter Bolt - deal X or 2X damage."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    damage = choice.callback_data.get('damage', 0)
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': damage, 'source': choice.source_id, 'is_combat': False},
        source=choice.source_id
    )]


def stonesplitter_bolt_resolve(targets: list, state: GameState) -> list[Event]:
    """Stonesplitter Bolt deals X damage (or 2X if bargained) to target creature or planeswalker."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    was_bargained = False
    x_value = 0
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Stonesplitter Bolt":
                caster_id = obj.controller
                spell_id = obj.id
                was_bargained = getattr(obj.state, 'bargained', False) if obj.state else False
                x_value = getattr(obj.state, 'x_value', 0) if obj.state else 0
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "stonesplitter_bolt_spell"

    damage = (x_value * 2) if was_bargained else x_value

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and
                     (CardType.CREATURE in obj.characteristics.types or CardType.PLANESWALKER in obj.characteristics.types)]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt=f"Choose a creature or planeswalker to deal {damage} damage to"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _stonesplitter_bolt_execute
    choice.callback_data['damage'] = damage
    return []


# --- FRANTIC FIREBOLT ---
def _frantic_firebolt_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Frantic Firebolt - deal calculated damage."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    damage = choice.callback_data.get('damage', 2)
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': damage, 'source': choice.source_id, 'is_combat': False},
        source=choice.source_id
    )]


def frantic_firebolt_resolve(targets: list, state: GameState) -> list[Event]:
    """Frantic Firebolt deals X damage to target creature (X = 2 + instants/sorceries/adventures in graveyard)."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Frantic Firebolt":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "frantic_firebolt_spell"

    # Count instants, sorceries, and cards with Adventure in graveyard
    gy_key = f"graveyard_{caster_id}"
    count = 0
    if gy_key in state.zones:
        for card_id in state.zones[gy_key].objects:
            card = state.objects.get(card_id)
            if card:
                types = card.characteristics.types
                subtypes = card.characteristics.subtypes
                if CardType.INSTANT in types or CardType.SORCERY in types or 'Adventure' in subtypes:
                    count += 1
    damage = 2 + count

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt=f"Choose a creature to deal {damage} damage to"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _frantic_firebolt_execute
    choice.callback_data['damage'] = damage
    return []


# --- MISLEADING MOTES ---
def _misleading_motes_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Misleading Motes - put creature on top or bottom of library."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    # For simplicity, put on top (would need another choice for top/bottom)
    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.LIBRARY,
            'library_position': 'top'
        },
        source=choice.source_id
    )]


def misleading_motes_resolve(targets: list, state: GameState) -> list[Event]:
    """Target creature's owner puts it on top or bottom of their library."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Misleading Motes":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "misleading_motes_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to put on top/bottom of its owner's library"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _misleading_motes_execute
    return []


# --- KELLANS LIGHTBLADES ---
def _kellans_lightblades_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Kellan's Lightblades - 3 damage or destroy if bargained."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    was_bargained = choice.callback_data.get('bargained', False)
    if was_bargained:
        return [Event(type=EventType.DESTROY, payload={'object_id': target_id}, source=choice.source_id)]
    else:
        return [Event(type=EventType.DAMAGE, payload={'target': target_id, 'amount': 3, 'source': choice.source_id, 'is_combat': False}, source=choice.source_id)]


def kellans_lightblades_resolve(targets: list, state: GameState) -> list[Event]:
    """Deal 3 damage to target attacking or blocking creature. If bargained, destroy instead."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    was_bargained = False
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Kellan's Lightblades":
                caster_id = obj.controller
                spell_id = obj.id
                was_bargained = getattr(obj.state, 'bargained', False) if obj.state else False
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "kellans_lightblades_spell"

    # In practice, would check attacking/blocking status
    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose an attacking or blocking creature"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _kellans_lightblades_execute
    choice.callback_data['bargained'] = was_bargained
    return []


# --- DISDAINFUL STROKE ---
def _disdainful_stroke_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Disdainful Stroke - counter target spell with MV >= 4."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    return [Event(type=EventType.COUNTER_SPELL, payload={'spell_id': target_id}, source=choice.source_id)]


def disdainful_stroke_resolve(targets: list, state: GameState) -> list[Event]:
    """Counter target spell with mana value 4 or greater."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Disdainful Stroke":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "disdainful_stroke_spell"

    def get_mana_value(o):
        mc = o.characteristics.mana_cost or ""
        return sum(1 for c in mc if c in 'WUBRG') + sum(int(c) for c in mc if c.isdigit())

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.STACK and get_mana_value(obj) >= 4 and obj.id != spell_id]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a spell with mana value 4 or greater to counter"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _disdainful_stroke_execute
    return []


# --- ICE OUT ---
def _ice_out_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Ice Out - counter target spell."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    return [Event(type=EventType.COUNTER_SPELL, payload={'spell_id': target_id}, source=choice.source_id)]


def ice_out_resolve(targets: list, state: GameState) -> list[Event]:
    """Counter target spell."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Ice Out":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "ice_out_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.STACK and obj.id != spell_id]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a spell to counter"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _ice_out_execute
    return []


# --- FLICK A COIN ---
def _flick_a_coin_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Flick a Coin - 1 damage, create Treasure, draw."""
    target_id = selected[0] if selected else None
    events = []

    if target_id:
        events.append(Event(type=EventType.DAMAGE, payload={'target': target_id, 'amount': 1, 'source': choice.source_id, 'is_combat': False}, source=choice.source_id))

    events.append(Event(
        type=EventType.OBJECT_CREATED,
        payload={'name': 'Treasure Token', 'controller': choice.player, 'types': [CardType.ARTIFACT], 'subtypes': ['Treasure'], 'is_token': True},
        source=choice.source_id
    ))
    events.append(Event(type=EventType.DRAW, payload={'player': choice.player, 'amount': 1}, source=choice.source_id))
    return events


def flick_a_coin_resolve(targets: list, state: GameState) -> list[Event]:
    """Deal 1 damage to any target, create Treasure, draw a card."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Flick a Coin":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "flick_a_coin_spell"

    # Any target = creatures, planeswalkers, players
    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and
                     (CardType.CREATURE in obj.characteristics.types or CardType.PLANESWALKER in obj.characteristics.types)]
    valid_targets.extend(list(state.players.keys()))

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose any target to deal 1 damage to"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _flick_a_coin_execute
    return []


# --- FAERIE FENCING ---
def _faerie_fencing_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Faerie Fencing - -X/-X, additional -3/-3 if controlling Faerie."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    x_value = choice.callback_data.get('x_value', 0)
    bonus = choice.callback_data.get('faerie_bonus', 0)
    total_mod = -(x_value + bonus)
    return [Event(type=EventType.PUMP, payload={'object_id': target_id, 'power': total_mod, 'toughness': total_mod, 'duration': 'end_of_turn'}, source=choice.source_id)]


def faerie_fencing_resolve(targets: list, state: GameState) -> list[Event]:
    """Target creature gets -X/-X. Additional -3/-3 if you control a Faerie."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    x_value = 0
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Faerie Fencing":
                caster_id = obj.controller
                spell_id = obj.id
                x_value = getattr(obj.state, 'x_value', 0) if obj.state else 0
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "faerie_fencing_spell"

    controls_faerie = any(
        obj.controller == caster_id and obj.zone == ZoneType.BATTLEFIELD and
        CardType.CREATURE in obj.characteristics.types and 'Faerie' in obj.characteristics.subtypes
        for obj in state.objects.values()
    )
    faerie_bonus = 3 if controls_faerie else 0

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt=f"Choose a creature to get -{x_value + faerie_bonus}/-{x_value + faerie_bonus}"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _faerie_fencing_execute
    choice.callback_data['x_value'] = x_value
    choice.callback_data['faerie_bonus'] = faerie_bonus
    return []


# --- THE END ---
def _the_end_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute The End - exile target creature or planeswalker."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    # Simplified - just exile the target
    return [Event(type=EventType.EXILE, payload={'object_id': target_id}, source=choice.source_id)]


def the_end_resolve(targets: list, state: GameState) -> list[Event]:
    """Exile target creature or planeswalker."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "The End":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "the_end_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and
                     (CardType.CREATURE in obj.characteristics.types or CardType.PLANESWALKER in obj.characteristics.types)]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature or planeswalker to exile"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _the_end_execute
    return []


# --- PLUNGE INTO WINTER ---
def _plunge_into_winter_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Plunge into Winter - tap creature, scry 1, draw."""
    events = []
    target_id = selected[0] if selected else None
    if target_id:
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            events.append(Event(type=EventType.TAP, payload={'object_id': target_id}, source=choice.source_id))
    events.append(Event(type=EventType.SCRY, payload={'player': choice.player, 'amount': 1}, source=choice.source_id))
    events.append(Event(type=EventType.DRAW, payload={'player': choice.player, 'amount': 1}, source=choice.source_id))
    return events


def plunge_into_winter_resolve(targets: list, state: GameState) -> list[Event]:
    """Tap up to one target creature. Scry 1, then draw a card."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Plunge into Winter":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "plunge_into_winter_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types]

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose up to one creature to tap",
        min_targets=0, max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _plunge_into_winter_execute
    return []


# --- RAT OUT ---
def _rat_out_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Rat Out - -1/-1 to creature, create Rat token."""
    events = []
    target_id = selected[0] if selected else None
    if target_id:
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            events.append(Event(type=EventType.PUMP, payload={'object_id': target_id, 'power': -1, 'toughness': -1, 'duration': 'end_of_turn'}, source=choice.source_id))
    events.append(Event(
        type=EventType.OBJECT_CREATED,
        payload={'name': 'Rat Token', 'controller': choice.player, 'power': 1, 'toughness': 1,
                 'types': [CardType.CREATURE], 'subtypes': ['Rat'], 'colors': [Color.BLACK], 'is_token': True},
        source=choice.source_id
    ))
    return events


def rat_out_resolve(targets: list, state: GameState) -> list[Event]:
    """Up to one target creature gets -1/-1. Create a 1/1 black Rat token."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Rat Out":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "rat_out_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types]

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose up to one creature to get -1/-1",
        min_targets=0, max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _rat_out_execute
    return []


# --- SUCCUMB TO THE COLD ---
def _succumb_to_the_cold_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Succumb to the Cold - tap 1-2 creatures, add stun counters."""
    events = []
    for target_id in selected:
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            events.append(Event(type=EventType.TAP, payload={'object_id': target_id}, source=choice.source_id))
            events.append(Event(type=EventType.COUNTER_ADDED, payload={'object_id': target_id, 'counter_type': 'stun', 'amount': 1}, source=choice.source_id))
    return events


def succumb_to_the_cold_resolve(targets: list, state: GameState) -> list[Event]:
    """Tap one or two target creatures an opponent controls. Put a stun counter on each."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Succumb to the Cold":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "succumb_to_the_cold_spell"

    valid_targets = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types
                     and obj.controller != caster_id]
    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose one or two opponent's creatures to tap and stun",
        min_targets=1, max_targets=2
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _succumb_to_the_cold_execute
    return []


# --- MOMENT OF VALOR ---
def moment_of_valor_resolve(targets: list, state: GameState) -> list[Event]:
    """Choose one: Untap and +1/+0 with indestructible; or destroy creature with power 4+."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Moment of Valor":
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "moment_of_valor_spell"

    modes = [
        {"id": "pump", "label": "Untap target creature. It gets +1/+0 and gains indestructible until end of turn."},
        {"id": "destroy", "label": "Destroy target creature with power 4 or greater."}
    ]

    def mode_handler(choice, selected_modes, state: GameState) -> list[Event]:
        mode = selected_modes[0] if selected_modes else "pump"
        if mode == "pump":
            valid = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types]
        else:
            valid = [obj.id for obj in state.objects.values()
                     if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types
                     and obj.power >= 4]
        if not valid:
            return []

        def execute_mode(choice2, selected2, state2: GameState) -> list[Event]:
            t_id = selected2[0] if selected2 else None
            if not t_id:
                return []
            t = state2.objects.get(t_id)
            if not t or t.zone != ZoneType.BATTLEFIELD:
                return []
            if mode == "pump":
                return [
                    Event(type=EventType.UNTAP, payload={'object_id': t_id}, source=choice2.source_id),
                    Event(type=EventType.PUMP, payload={'object_id': t_id, 'power': 1, 'toughness': 0, 'duration': 'end_of_turn'}, source=choice2.source_id),
                    Event(type=EventType.GRANT_KEYWORD, payload={'object_id': t_id, 'keyword': 'indestructible', 'duration': 'end_of_turn'}, source=choice2.source_id)
                ]
            else:
                return [Event(type=EventType.DESTROY, payload={'object_id': t_id}, source=choice2.source_id)]

        target_choice = create_target_choice(
            state=state, player_id=choice.player, source_id=choice.source_id,
            legal_targets=valid,
            prompt="Choose a target for Moment of Valor"
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = execute_mode
        return []

    choice = create_modal_choice(
        state=state, player_id=caster_id, source_id=spell_id,
        modes=modes,
        min_modes=1, max_modes=1
    )
    choice.callback_data['handler'] = mode_handler
    return []


# --- Green Cards ---

def elvish_archivist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever one or more artifacts you control enter, put two +1/+1 counters on this creature.
    Whenever one or more enchantments you control enter, draw a card."""
    interceptors = []

    # Artifact enters trigger
    def artifact_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_obj = state.objects.get(event.payload.get('object_id'))
        if not entering_obj:
            return False
        return (entering_obj.controller == obj.controller and
                CardType.ARTIFACT in entering_obj.characteristics.types)

    def add_counters(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 2},
            source=obj.id
        )]

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=artifact_enters_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=add_counters(e, s)),
        duration='while_on_battlefield'
    ))

    # Enchantment enters trigger
    def enchantment_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_obj = state.objects.get(event.payload.get('object_id'))
        if not entering_obj:
            return False
        return (entering_obj.controller == obj.controller and
                CardType.ENCHANTMENT in entering_obj.characteristics.types)

    def draw_card(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=enchantment_enters_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=draw_card(e, s)),
        duration='while_on_battlefield'
    ))

    return interceptors


def gruff_triplets_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, if it isn't a token, create two tokens that are copies of it.
    When this creature dies, put +1/+1 counters on each creature you control named Gruff Triplets."""
    interceptors = []

    # ETB trigger
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        if obj.state.is_token:
            return []
        events = []
        for _ in range(2):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Gruff Triplets',
                    'controller': obj.controller,
                    'power': 3,
                    'toughness': 3,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Satyr', 'Warrior'],
                    'colors': [Color.GREEN],
                    'abilities': ['trample'],
                    'is_token': True
                },
                source=obj.id
            ))
        return events
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Death trigger
    def death_effect(event: Event, state: GameState) -> list[Event]:
        power = get_power(obj, state)
        events = []
        for o in state.objects.values():
            if (o.controller == obj.controller and
                o.name == 'Gruff Triplets' and  # Name is on GameObject, not Characteristics
                o.zone == ZoneType.BATTLEFIELD and
                o.id != obj.id):
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': o.id, 'counter_type': '+1/+1', 'amount': power},
                    source=obj.id
                ))
        return events
    interceptors.append(make_death_trigger(obj, death_effect))

    return interceptors


def hamlet_glutton_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you gain 3 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def blossoming_tortoise_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Land creatures you control get +1/+1."""
    def affects_land_creatures(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                CardType.LAND in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)
    return make_static_pt_boost(obj, 1, 1, affects_land_creatures)


def night_of_sweets_revenge_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this enchantment enters, create a Food token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Food Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Food'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def redtooth_genealogist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Royal Role token attached to another target creature you control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Royal Role',
                'controller': obj.controller,
                'types': [CardType.ENCHANTMENT],
                'subtypes': ['Aura', 'Role'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def skybeast_tracker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a spell with mana value 5 or greater, create a Food token."""
    def big_spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Food Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Food'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_spell_cast_trigger(obj, big_spell_effect, mana_value_min=5)]


def tanglespan_lookout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever an Aura you control enters, draw a card."""
    def aura_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_obj = state.objects.get(event.payload.get('object_id'))
        if not entering_obj:
            return False
        return (entering_obj.controller == obj.controller and
                'Aura' in entering_obj.characteristics.subtypes)

    def draw_card(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=aura_enters_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=draw_card(e, s)),
        duration='while_on_battlefield'
    )]


def tough_cookie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Food token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Food Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Food'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def up_the_beanstalk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this enchantment enters and whenever you cast a spell with mana value 5 or greater, draw a card."""
    interceptors = []

    # ETB trigger
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Spell cast trigger
    def big_spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    interceptors.append(make_spell_cast_trigger(obj, big_spell_effect, mana_value_min=5))

    return interceptors


def wildwood_mentor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a token you control enters, put a +1/+1 counter on this creature."""
    def token_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_obj = state.objects.get(event.payload.get('object_id'))
        if not entering_obj:
            return False
        return entering_obj.controller == obj.controller and entering_obj.state.is_token

    def add_counter(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=token_enters_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=add_counter(e, s)),
        duration='while_on_battlefield'
    )]


# --- Multicolor Cards ---

def ash_party_crasher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever Ash attacks, if two or more nonland permanents entered this turn, put a +1/+1 counter on Ash."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Note: Would need turn tracking for celebration
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def eriette_of_the_charmed_apple_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your end step, each opponent loses X life and you gain X life, where X is the number of Auras you control."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        aura_count = sum(1 for o in state.objects.values()
                        if o.controller == obj.controller and
                        'Aura' in o.characteristics.subtypes and
                        o.zone == ZoneType.BATTLEFIELD)
        if aura_count <= 0:
            return []
        events = []
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -aura_count},
                    source=obj.id
                ))
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': aura_count},
            source=obj.id
        ))
        return events
    return [make_end_step_trigger(obj, end_step_effect)]


def faunsbane_troll_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Monster Role token attached to it."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Monster Role',
                'controller': obj.controller,
                'attach_to': obj.id,
                'types': [CardType.ENCHANTMENT],
                'subtypes': ['Aura', 'Role'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def the_goose_mother_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever The Goose Mother attacks, you may sacrifice a Food. If you do, draw a card."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified: just draw a card (would need sacrifice choice)
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]


def greta_sweettooth_scourge_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Greta enters, create a Food token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Food Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Food'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def neva_stalked_by_nightmares_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever an enchantment you control is put into a graveyard from the battlefield, put a +1/+1 counter on Neva, then scry 1."""
    def enchantment_dies_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_obj = state.objects.get(event.payload.get('object_id'))
        if not dying_obj:
            return False
        return (dying_obj.controller == obj.controller and
                CardType.ENCHANTMENT in dying_obj.characteristics.types)

    def counter_and_scry(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.COUNTER_ADDED, payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1}, source=obj.id),
            Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=enchantment_dies_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=counter_and_scry(e, s)),
        duration='while_on_battlefield'
    )]


def obyra_dreaming_duelist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another Faerie you control enters, each opponent loses 1 life."""
    def faerie_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == obj.id:
            return False
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == obj.controller and
                'Faerie' in entering_obj.characteristics.subtypes)

    def opponent_life_loss(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -1},
                    source=obj.id
                ))
        return events

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=faerie_enters_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=opponent_life_loss(e, s)),
        duration='while_on_battlefield'
    )]


def sharae_of_numbing_depths_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Sharae enters, tap target creature an opponent controls and put a stun counter on it."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TAP,
            payload={},  # Would need targeting
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def syr_armont_the_redeemer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Syr Armont enters, create a Monster Role token attached to another target creature you control.
    Enchanted creatures you control get +1/+1."""
    interceptors = []

    # ETB trigger
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Monster Role',
                'controller': obj.controller,
                'types': [CardType.ENCHANTMENT],
                'subtypes': ['Aura', 'Role'],
                'is_token': True
            },
            source=obj.id
        )]
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Static +1/+1 to enchanted creatures
    def affects_enchanted_creatures(target: GameObject, state: GameState) -> bool:
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        for o in state.objects.values():
            if (CardType.ENCHANTMENT in o.characteristics.types and
                'Aura' in o.characteristics.subtypes and
                o.zone == ZoneType.BATTLEFIELD and
                o.state.attached_to == target.id):
                return True
        return False

    interceptors.extend(make_static_pt_boost(obj, 1, 1, affects_enchanted_creatures))

    return interceptors


def totentanz_swarm_piper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever Totentanz or another nontoken creature you control dies, create a 1/1 black Rat creature token."""
    def creature_dies_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_obj = state.objects.get(event.payload.get('object_id'))
        if not dying_obj:
            return False
        if dying_obj.state.is_token:
            return False
        return (dying_obj.controller == obj.controller and
                CardType.CREATURE in dying_obj.characteristics.types)

    def create_rat(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Rat Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Rat'],
                'colors': [Color.BLACK],
                'is_token': True
            },
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=creature_dies_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=create_rat(e, s)),
        duration='while_on_battlefield'
    )]


# --- Artifact Cards ---

def candy_trail_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this artifact enters, scry 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def prophetic_prism_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this artifact enters, draw a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


def soulguide_lantern_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this artifact enters, exile target card from a graveyard."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.EXILE,
            payload={},  # Would need targeting
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def syr_ginger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another artifact you control is put into a graveyard from the battlefield, put a +1/+1 counter on Syr Ginger and scry 1."""
    def artifact_dies_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        if dying_id == obj.id:
            return False
        dying_obj = state.objects.get(dying_id)
        if not dying_obj:
            return False
        return (dying_obj.controller == obj.controller and
                CardType.ARTIFACT in dying_obj.characteristics.types)

    def counter_and_scry(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.COUNTER_ADDED, payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1}, source=obj.id),
            Event(type=EventType.SCRY, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=artifact_dies_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=counter_and_scry(e, s)),
        duration='while_on_battlefield'
    )]


# --- Additional Cards ---

def lady_of_laughter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your end step, if two or more nonland permanents entered this turn, draw a card."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        # Note: Would need turn tracking for celebration
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_end_step_trigger(obj, end_step_effect)]


def pests_of_honor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of combat on your turn, if celebration, put a +1/+1 counter on this creature."""
    def combat_trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'combat':
            return False
        return state.active_player == obj.controller

    def add_counter(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_trigger_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=add_counter(e, s)),
        duration='while_on_battlefield'
    )]


def storyteller_pixie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an Adventure spell, draw a card."""
    def adventure_cast_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        spell_id = event.payload.get('spell_id')
        spell = state.objects.get(spell_id)
        if not spell:
            return False
        return 'Adventure' in spell.characteristics.subtypes

    def draw_card(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=adventure_cast_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=draw_card(e, s)),
        duration='while_on_battlefield'
    )]


def experimental_confectioner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Food token.
    Whenever you sacrifice a Food, create a 1/1 black Rat creature token."""
    interceptors = []

    # ETB trigger
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Food Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Food'],
                'is_token': True
            },
            source=obj.id
        )]
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Food sacrifice trigger
    def food_sacrificed_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        if event.payload.get('cause') != 'sacrifice':
            return False
        dying_obj = state.objects.get(event.payload.get('object_id'))
        if not dying_obj:
            return False
        return (dying_obj.controller == obj.controller and
                'Food' in dying_obj.characteristics.subtypes)

    def create_rat(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Rat Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Rat'],
                'colors': [Color.BLACK],
                'is_token': True
            },
            source=obj.id
        )]

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=food_sacrificed_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=create_rat(e, s)),
        duration='while_on_battlefield'
    ))

    return interceptors


def malevolent_witchkite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, sacrifice any number of artifacts, enchantments, and/or tokens, then draw that many cards."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified: just the draw effect (would need sacrifice choices)
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


def old_flitterfang_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of each end step, if a creature died this turn, create a Food token."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        # Note: Would need turn death tracking
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Food Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Food'],
                'is_token': True
            },
            source=obj.id
        )]

    def end_step_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        return event.payload.get('phase') == 'end_step'

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=end_step_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=end_step_effect(e, s)),
        duration='while_on_battlefield'
    )]


def ogre_chitterlord_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature enters or attacks, create two 1/1 black Rat creature tokens."""
    interceptors = []

    def create_rats(event: Event, state: GameState) -> list[Event]:
        events = []
        for _ in range(2):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Rat Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Rat'],
                    'colors': [Color.BLACK],
                    'is_token': True
                },
                source=obj.id
            ))
        return events

    interceptors.append(make_etb_trigger(obj, create_rats))
    interceptors.append(make_attack_trigger(obj, create_rats))

    return interceptors


def provisions_merchant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Food token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Food Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Food'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- Additional White Cards ---

def rimefur_reindeer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever an enchantment you control enters, tap target creature an opponent controls."""
    def enchantment_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_obj = state.objects.get(event.payload.get('object_id'))
        if not entering_obj:
            return False
        return (entering_obj.controller == obj.controller and
                CardType.ENCHANTMENT in entering_obj.characteristics.types)

    def tap_creature(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TAP,
            payload={},  # Would need targeting
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=enchantment_enters_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=tap_creature(e, s)),
        duration='while_on_battlefield'
    )]


def hopeful_vigil_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this enchantment enters, create a 2/2 white Knight with vigilance.
    When put into graveyard from battlefield, scry 2."""
    interceptors = []

    # ETB trigger
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Knight Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Knight'],
                'colors': [Color.WHITE],
                'abilities': ['vigilance'],
                'is_token': True
            },
            source=obj.id
        )]
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Death trigger - scry 2
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    interceptors.append(make_death_trigger(obj, death_effect))

    return interceptors


def slumbering_keepguard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever an enchantment you control enters, scry 1."""
    def enchantment_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_obj = state.objects.get(event.payload.get('object_id'))
        if not entering_obj:
            return False
        return (entering_obj.controller == obj.controller and
                CardType.ENCHANTMENT in entering_obj.characteristics.types)

    def scry_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=enchantment_enters_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=scry_effect(e, s)),
        duration='while_on_battlefield'
    )]


# --- Additional Blue Cards ---

def merfolk_coralsmith_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, scry 2."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def snaremaster_sprite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you may pay {2}. When you do, tap target creature and put a stun counter on it."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TAP,
            payload={},  # Would need targeting
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def chancellor_of_tales_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an Adventure spell, you may copy it."""
    def adventure_cast_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        spell_id = event.payload.get('spell_id')
        spell = state.objects.get(spell_id)
        if not spell:
            return False
        return 'Adventure' in spell.characteristics.subtypes

    def copy_spell(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COPY_SPELL,
            payload={'spell_id': event.payload.get('spell_id')},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=adventure_cast_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=copy_spell(e, s)),
        duration='while_on_battlefield'
    )]


# --- Additional Black Cards ---

def lord_skitters_butcher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a 1/1 black Rat creature token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Rat Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Rat'],
                'colors': [Color.BLACK],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def twisted_sewer_witch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a 1/1 black Rat creature token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Rat Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Rat'],
                'colors': [Color.BLACK],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def specter_of_mortality_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you may exile one or more creature cards from your graveyard."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={'power_mod': -1, 'toughness_mod': -1, 'duration': 'end_of_turn'},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def spiteful_hexmage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Cursed Role token attached to target creature you control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Cursed Role',
                'controller': obj.controller,
                'types': [CardType.ENCHANTMENT],
                'subtypes': ['Aura', 'Role'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def stingblade_assassin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, destroy target creature that was dealt damage this turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DESTROY,
            payload={},  # Would need targeting
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- Additional Red Cards ---

def belligerent_of_the_ball_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Celebration - At beginning of combat on your turn, target creature gets +1/+0 and gains menace."""
    def combat_trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'combat':
            return False
        return state.active_player == obj.controller

    def menace_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={'power_mod': 1, 'grant_abilities': ['menace'], 'duration': 'end_of_turn'},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_trigger_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=menace_effect(e, s)),
        duration='while_on_battlefield'
    )]


def boundary_lands_ranger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At beginning of combat on your turn, if you control a creature with power 4+, you may discard then draw."""
    def combat_trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'combat':
            return False
        if state.active_player != obj.controller:
            return False
        # Check for power 4+ creature
        for o in state.objects.values():
            if (o.controller == obj.controller and
                CardType.CREATURE in o.characteristics.types and
                o.zone == ZoneType.BATTLEFIELD and
                get_power(o, state) >= 4):
                return True
        return False

    def loot_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_trigger_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=loot_effect(e, s)),
        duration='while_on_battlefield'
    )]


def merry_bards_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you may pay {1}. When you do, create a Young Hero Role token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Young Hero Role',
                'controller': obj.controller,
                'types': [CardType.ENCHANTMENT],
                'subtypes': ['Aura', 'Role'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def rotisserie_elemental_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature deals combat damage to a player, put a skewer counter on it."""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target not in state.players:
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'skewer', 'amount': 1},
            source=obj.id
        )]
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]


def skewer_slinger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature blocks or becomes blocked, deal 1 damage to that creature."""
    def block_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.BLOCK_DECLARED:
            return False
        blocker_id = event.payload.get('blocker_id')
        attacker_id = event.payload.get('attacker_id')
        return blocker_id == obj.id or attacker_id == obj.id

    def ping_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DAMAGE,
            payload={'amount': 1, 'source': obj.id},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=block_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=ping_effect(e, s)),
        duration='while_on_battlefield'
    )]


def tattered_ratter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a Rat you control becomes blocked, it gets +2/+0 until end of turn."""
    def rat_blocked_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.BLOCK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        return (attacker.controller == obj.controller and
                'Rat' in attacker.characteristics.subtypes)

    def pump_effect(event: Event, state: GameState) -> list[Event]:
        attacker_id = event.payload.get('attacker_id')
        return [Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={'object_id': attacker_id, 'power_mod': 2, 'duration': 'end_of_turn'},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=rat_blocked_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=pump_effect(e, s)),
        duration='while_on_battlefield'
    )]


def realmscorcher_hellkite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, if it was bargained, add four mana in any combination of colors."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        if not event.payload.get('bargained', False):
            return []
        return [Event(
            type=EventType.MANA_ADDED,
            payload={'player': obj.controller, 'amount': 4},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def imodane_the_pyrohammer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever an instant or sorcery you control that targets only a single creature deals damage, deal that much to each opponent."""
    def damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source_controller') != obj.controller:
            return False
        return True

    def damage_opponents(event: Event, state: GameState) -> list[Event]:
        amount = event.payload.get('amount', 0)
        events = []
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': amount, 'source': obj.id},
                    source=obj.id
                ))
        return events

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=damage_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=damage_opponents(e, s)),
        duration='while_on_battlefield'
    )]


# --- Additional Green Cards ---

def agathas_champion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, if it was bargained, it fights up to one target creature you don't control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        if not event.payload.get('bargained', False):
            return []
        return [Event(
            type=EventType.FIGHT,
            payload={'attacker': obj.id},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def troublemaker_ouphe_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, if it was bargained, exile target artifact or enchantment an opponent controls."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        if not event.payload.get('bargained', False):
            return []
        return [Event(
            type=EventType.EXILE,
            payload={},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def sentinel_of_lost_lore_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, choose one or more - various graveyard effects."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.EXILE,
            payload={},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def territorial_witchstalker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At beginning of combat on your turn, if you control a creature with power 4+, this gets +1/+0 and can attack."""
    def combat_trigger_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'combat':
            return False
        if state.active_player != obj.controller:
            return False
        for o in state.objects.values():
            if (o.controller == obj.controller and
                CardType.CREATURE in o.characteristics.types and
                o.zone == ZoneType.BATTLEFIELD and
                get_power(o, state) >= 4):
                return True
        return False

    def pump_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={'object_id': obj.id, 'power_mod': 1, 'duration': 'end_of_turn'},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_trigger_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=pump_effect(e, s)),
        duration='while_on_battlefield'
    )]


# --- Additional Multicolor Cards ---

def hylda_of_the_icy_crown_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you tap an untapped creature an opponent controls, you may pay {1}. Choose one - create 4/4 or counters or scry/draw."""
    def tap_opponent_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.TAP:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return (target.controller != obj.controller and
                CardType.CREATURE in target.characteristics.types)

    def create_elemental(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Elemental Token',
                'controller': obj.controller,
                'power': 4,
                'toughness': 4,
                'types': [CardType.CREATURE],
                'subtypes': ['Elemental'],
                'colors': [Color.WHITE, Color.BLUE],
                'is_token': True
            },
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=tap_opponent_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=create_elemental(e, s)),
        duration='while_on_battlefield'
    )]


def talion_the_kindly_lord_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever an opponent casts a spell with mana value equal to the chosen number, that player loses 2 life and you draw a card."""
    def spell_cast_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') == obj.controller:
            return False
        # Simplified: trigger on any opponent spell cast
        return True

    def drain_and_draw(event: Event, state: GameState) -> list[Event]:
        caster = event.payload.get('caster')
        return [
            Event(type=EventType.LIFE_CHANGE, payload={'player': caster, 'amount': -2}, source=obj.id),
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=spell_cast_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=drain_and_draw(e, s)),
        duration='while_on_battlefield'
    )]


def ruby_daring_tracker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever Ruby attacks while you control a creature with power 4 or greater, Ruby gets +2/+2 until end of turn."""
    def attack_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        if event.payload.get('attacker_id') != source.id:
            return False
        # Check for power 4+ creature
        for o in state.objects.values():
            if (o.controller == source.controller and
                CardType.CREATURE in o.characteristics.types and
                o.zone == ZoneType.BATTLEFIELD and
                get_power(o, state) >= 4):
                return True
        return False

    def pump_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={'object_id': obj.id, 'power_mod': 2, 'toughness_mod': 2, 'duration': 'end_of_turn'},
            source=obj.id
        )]

    return [make_attack_trigger(obj, pump_effect, filter_fn=attack_filter)]


# --- Additional Artifact Cards ---

def the_irencrag_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a legendary creature you control enters, you may have The Irencrag become Everflame, Heroes' Legacy."""
    def legendary_enters_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_obj = state.objects.get(event.payload.get('object_id'))
        if not entering_obj:
            return False
        return (entering_obj.controller == obj.controller and
                CardType.CREATURE in entering_obj.characteristics.types and
                'Legendary' in entering_obj.characteristics.supertypes)

    def transform_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TRANSFORM,
            payload={'object_id': obj.id, 'new_name': 'Everflame, Heroes\' Legacy'},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=legendary_enters_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=transform_effect(e, s)),
        duration='while_on_battlefield'
    )]


def food_coma_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this enchantment enters, exile target creature an opponent controls. Create a Food token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.EXILE, payload={}, source=obj.id),
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Food Token',
                    'controller': obj.controller,
                    'types': [CardType.ARTIFACT],
                    'subtypes': ['Food'],
                    'is_token': True
                },
                source=obj.id
            )
        ]
    return [make_etb_trigger(obj, etb_effect)]


# --- Additional Land Cards ---

def crystal_grotto_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this land enters, scry 1."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def restless_bivouac_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this land attacks, put a +1/+1 counter on target creature you control."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def restless_cottage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this land attacks, create a Food token and exile up to one target card from a graveyard."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Food Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Food'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def restless_fortress_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this land attacks, defending player loses 2 life and you gain 2 life."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id
            )
        ]
    return [make_attack_trigger(obj, attack_effect)]


def restless_spire_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this land attacks, scry 1."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def restless_vinestalk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this land attacks, up to one other target creature has base power and toughness 3/3 until end of turn."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TEMPORARY_EFFECT,
            payload={'set_power': 3, 'set_toughness': 3, 'duration': 'end_of_turn'},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


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
    resolve=archons_glory_resolve,
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
    mana_cost="{3}{W} // {W}",
    colors={Color.WHITE},
    subtypes={"//", "Human", "Knight", "Sorcery"},
    text="",
)

BREAK_THE_SPELL = make_instant(
    name="Break the Spell",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Destroy target enchantment. If a permanent you controlled or a token was destroyed this way, draw a card.",
    resolve=break_the_spell_resolve,
)

CHARMED_CLOTHIER = make_creature(
    name="Charmed Clothier",
    power=3, toughness=3,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Advisor", "Faerie"},
    text="Flying\nWhen this creature enters, create a Royal Role token attached to another target creature you control. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1 and has ward {1}.)",
    setup_interceptors=charmed_clothier_setup
)

CHEEKY_HOUSEMOUSE = make_creature(
    name="Cheeky House-Mouse",
    power=2, toughness=1,
    mana_cost="{W} // {W}",
    colors={Color.WHITE},
    subtypes={"//", "Mouse", "Sorcery"},
    text="",
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
    setup_interceptors=cursed_courtier_setup
)

DISCERNING_FINANCIER = make_creature(
    name="Discerning Financier",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    text="At the beginning of your upkeep, if an opponent controls more lands than you, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\n{2}{W}: Choose another player. That player gains control of target Treasure you control. You draw a card.",
    setup_interceptors=discerning_financier_setup
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
    setup_interceptors=hopeful_vigil_setup
)

KELLANS_LIGHTBLADES = make_instant(
    name="Kellan's Lightblades",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nKellan's Lightblades deals 3 damage to target attacking or blocking creature. If this spell was bargained, destroy that creature instead.",
    resolve=kellans_lightblades_resolve,
)

KNIGHT_OF_DOVES = make_creature(
    name="Knight of Doves",
    power=1, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Whenever an enchantment you control is put into a graveyard from the battlefield, create a 1/1 white Bird creature token with flying.",
    setup_interceptors=knight_of_doves_setup
)

MOMENT_OF_VALOR = make_instant(
    name="Moment of Valor",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Untap target creature. It gets +1/+0 and gains indestructible until end of turn.\n• Destroy target creature with power 4 or greater.",
    resolve=moment_of_valor_resolve,
)

MOONSHAKER_CAVALRY = make_creature(
    name="Moonshaker Cavalry",
    power=6, toughness=6,
    mana_cost="{5}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Knight", "Spirit"},
    text="Flying\nWhen this creature enters, creatures you control gain flying and get +X/+X until end of turn, where X is the number of creatures you control.",
    setup_interceptors=moonshaker_cavalry_setup
)

PLUNGE_INTO_WINTER = make_instant(
    name="Plunge into Winter",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Tap up to one target creature. Scry 1, then draw a card.",
    resolve=plunge_into_winter_resolve,
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
    setup_interceptors=protective_parents_setup
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
    setup_interceptors=rimefur_reindeer_setup
)

SAVIOR_OF_THE_SLEEPING = make_creature(
    name="Savior of the Sleeping",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Vigilance\nWhenever an enchantment you control is put into a graveyard from the battlefield, put a +1/+1 counter on this creature.",
    setup_interceptors=savior_of_the_sleeping_setup
)

SLUMBERING_KEEPGUARD = make_creature(
    name="Slumbering Keepguard",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Whenever an enchantment you control enters, scry 1.\n{2}{W}: This creature gets +1/+1 until end of turn for each enchantment you control.",
    setup_interceptors=slumbering_keepguard_setup
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
    setup_interceptors=stockpiling_celebrant_setup
)

STROKE_OF_MIDNIGHT = make_instant(
    name="Stroke of Midnight",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Destroy target nonland permanent. Its controller creates a 1/1 white Human creature token.",
    resolve=stroke_of_midnight_resolve,
)

A_TALE_FOR_THE_AGES = make_enchantment(
    name="A Tale for the Ages",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Enchanted creatures you control get +2/+2.",
    setup_interceptors=a_tale_for_the_ages_setup
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
    text="At the beginning of your end step, put a +1/+1 counter on each creature you control. Untap those creatures.\n// Adventure — Ardenvale Fealty {1}{W} (Instant)\nCreate a 2/2 white Knight creature token with vigilance.",
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
    mana_cost="{1}{U} // {2}{U}",
    colors={Color.BLUE},
    subtypes={"//", "Elemental", "Sorcery"},
    text="",
)

ARCHIVE_DRAGON = make_creature(
    name="Archive Dragon",
    power=4, toughness=6,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Dragon", "Wizard"},
    text="Flying\nWard {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nWhen this creature enters, scry 2.",
    setup_interceptors=archive_dragon_setup
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
    mana_cost="{5}{U} // {1}{U}",
    colors={Color.BLUE},
    subtypes={"//", "Giant", "Soldier", "Sorcery"},
    text="",
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
    setup_interceptors=chancellor_of_tales_setup
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
    resolve=disdainful_stroke_resolve,
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
    resolve=freeze_in_place_resolve,
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
    mana_cost="{3}{U} // {5}{U}{U}",
    colors={Color.BLUE},
    subtypes={"//", "Giant", "Instant", "Wizard"},
    text="",
)

HORNED_LOCHWHALE = make_creature(
    name="Horned Loch-Whale",
    power=6, toughness=6,
    mana_cost="{4}{U}{U} // {1}{U}",
    colors={Color.BLUE},
    subtypes={"//", "Instant", "Whale"},
    text="",
)

ICE_OUT = make_instant(
    name="Ice Out",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nThis spell costs {1} less to cast if it's bargained.\nCounter target spell.",
    resolve=ice_out_resolve,
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
    resolve=johanns_stopgap_resolve,
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
    setup_interceptors=merfolk_coralsmith_setup
)

MISLEADING_MOTES = make_instant(
    name="Misleading Motes",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Target creature's owner puts it on their choice of the top or bottom of their library.",
    resolve=misleading_motes_resolve,
)

MOCKING_SPRITE = make_creature(
    name="Mocking Sprite",
    power=2, toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Rogue"},
    text="Flying\nInstant and sorcery spells you cast cost {1} less to cast.",
    setup_interceptors=mocking_sprite_setup
)

OBYRAS_ATTENDANTS = make_creature(
    name="Obyra's Attendants",
    power=3, toughness=4,
    mana_cost="{4}{U} // {1}{U}",
    colors={Color.BLUE},
    subtypes={"//", "Faerie", "Instant", "Wizard"},
    text="",
)

PICKLOCK_PRANKSTER = make_creature(
    name="Picklock Prankster",
    power=1, toughness=3,
    mana_cost="{1}{U} // {1}{U}",
    colors={Color.BLUE},
    subtypes={"//", "Faerie", "Instant", "Rogue"},
    text="",
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
    setup_interceptors=snaremaster_sprite_setup
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
    setup_interceptors=splashy_spellcaster_setup
)

STORMKELD_PROWLER = make_creature(
    name="Stormkeld Prowler",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="Whenever you cast a spell with mana value 5 or greater, put two +1/+1 counters on this creature.",
    setup_interceptors=stormkeld_prowler_setup
)

SUCCUMB_TO_THE_COLD = make_instant(
    name="Succumb to the Cold",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Tap one or two target creatures an opponent controls. Put a stun counter on each of them. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
    resolve=succumb_to_the_cold_resolve,
)

TALIONS_MESSENGER = make_creature(
    name="Talion's Messenger",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Noble"},
    text="Flying\nWhenever you attack with one or more Faeries, draw a card, then discard a card. When you discard a card this way, put a +1/+1 counter on target Faerie you control.",
    setup_interceptors=talions_messenger_setup
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
    mana_cost="{3}{U} // {1}{U}",
    colors={Color.BLUE},
    subtypes={"//", "Human", "Sorcery", "Wizard"},
    text="",
)

VIRTUE_OF_KNOWLEDGE = make_enchantment(
    name="Virtue of Knowledge",
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    text="If a permanent entering causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.\n// Adventure — Vantress Visions {1}{U} (Instant)\nCopy target activated or triggered ability you control. You may choose new targets for the copy.",
)

WATER_WINGS = make_instant(
    name="Water Wings",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Until end of turn, target creature you control has base power and toughness 4/4 and gains flying and hexproof. (It can't be the target of spells or abilities your opponents control.)",
    resolve=water_wings_resolve,
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
    setup_interceptors=ashioks_reaper_setup
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
    resolve=candy_grapple_resolve,
)

CONCEITED_WITCH = make_creature(
    name="Conceited Witch",
    power=2, toughness=3,
    mana_cost="{2}{B} // {B}",
    colors={Color.BLACK},
    subtypes={"//", "Human", "Sorcery", "Warlock"},
    text="",
)

DREAM_SPOILERS = make_creature(
    name="Dream Spoilers",
    power=2, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Warlock"},
    text="Flying\nWhenever you cast a spell during an opponent's turn, up to one target creature an opponent controls gets -1/-1 until end of turn.",
    setup_interceptors=dream_spoilers_setup
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
    resolve=the_end_resolve,
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
    setup_interceptors=faerie_dreamthief_setup
)

FAERIE_FENCING = make_instant(
    name="Faerie Fencing",
    mana_cost="{X}{B}",
    colors={Color.BLACK},
    text="Target creature gets -X/-X until end of turn. That creature gets an additional -3/-3 until end of turn if you controlled a Faerie as you cast this spell.",
    resolve=faerie_fencing_resolve,
)

FEED_THE_CAULDRON = make_instant(
    name="Feed the Cauldron",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target creature with mana value 3 or less. If it's your turn, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")",
    resolve=feed_the_cauldron_resolve,
)

FELL_HORSEMAN = make_creature(
    name="Fell Horseman",
    power=3, toughness=3,
    mana_cost="{3}{B} // {1}{B}",
    colors={Color.BLACK},
    subtypes={"//", "Knight", "Sorcery", "Zombie"},
    text="",
)

GUMDROP_POISONER = make_creature(
    name="Gumdrop Poisoner",
    power=3, toughness=2,
    mana_cost="{2}{B} // {B}",
    colors={Color.BLACK},
    subtypes={"//", "Human", "Instant", "Warlock"},
    text="",
)

HIGH_FAE_NEGOTIATOR = make_creature(
    name="High Fae Negotiator",
    power=3, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Warlock"},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nFlying\nWhen this creature enters, if it was bargained, each opponent loses 3 life and you gain 3 life.",
    setup_interceptors=high_fae_negotiator_setup
)

HOPELESS_NIGHTMARE = make_enchantment(
    name="Hopeless Nightmare",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="When this enchantment enters, each opponent discards a card and loses 2 life.\nWhen this enchantment is put into a graveyard from the battlefield, scry 2.\n{2}{B}: Sacrifice this enchantment.",
    setup_interceptors=hopeless_nightmare_setup
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
    setup_interceptors=lord_skitter_sewer_king_setup
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
    setup_interceptors=lord_skitters_butcher_setup
)

MINTSTROSITY = make_creature(
    name="Mintstrosity",
    power=3, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="When this creature dies, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")",
    setup_interceptors=mintstrosity_setup
)

NOT_DEAD_AFTER_ALL = make_instant(
    name="Not Dead After All",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Until end of turn, target creature you control gains \"When this creature dies, return it to the battlefield tapped under its owner's control, then create a Wicked Role token attached to it.\" (Enchanted creature gets +1/+1. When this token is put into a graveyard, each opponent loses 1 life.)",
    resolve=not_dead_after_all_resolve,
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
    resolve=rat_out_resolve,
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
    setup_interceptors=scream_puff_setup
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
    resolve=sugar_rush_resolve,
)

SWEETTOOTH_WITCH = make_creature(
    name="Sweettooth Witch",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="When this creature enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\n{2}, Sacrifice a Food: Target player loses 2 life.",
    setup_interceptors=sweettooth_witch_setup
)

TAKEN_BY_NIGHTMARES = make_instant(
    name="Taken by Nightmares",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Exile target creature. If you control an enchantment, scry 2.",
    resolve=taken_by_nightmares_resolve,
)

TANGLED_COLONY = make_creature(
    name="Tangled Colony",
    power=3, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rat"},
    text="This creature can't block.\nWhen this creature dies, create X 1/1 black Rat creature tokens with \"This token can't block,\" where X is the amount of damage dealt to it this turn.",
    setup_interceptors=tangled_colony_setup
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
    setup_interceptors=voracious_vermin_setup
)

WAREHOUSE_TABBY = make_creature(
    name="Warehouse Tabby",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Cat"},
    text="Whenever an enchantment you control is put into a graveyard from the battlefield, create a 1/1 black Rat creature token with \"This token can't block.\"\n{1}{B}: This creature gains deathtouch until end of turn.",
    setup_interceptors=warehouse_tabby_setup
)

WICKED_VISITOR = make_creature(
    name="Wicked Visitor",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare"},
    text="Whenever an enchantment you control is put into a graveyard from the battlefield, each opponent loses 1 life.",
    setup_interceptors=wicked_visitor_setup
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
    mana_cost="{4}{R} // {2}{R}",
    colors={Color.RED},
    subtypes={"//", "Ogre", "Sorcery"},
    text="",
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
    setup_interceptors=charming_scoundrel_setup
)

CUT_IN = make_sorcery(
    name="Cut In",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Cut In deals 4 damage to target creature.\nCreate a Young Hero Role token attached to up to one target creature you control. (If you control another Role on it, put that one into the graveyard. Enchanted creature has \"Whenever this creature attacks, if its toughness is 3 or less, put a +1/+1 counter on it.\")",
    resolve=cut_in_resolve,
)

EDGEWALL_PACK = make_creature(
    name="Edgewall Pack",
    power=3, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Dog"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhen this creature enters, create a 1/1 black Rat creature token with \"This token can't block.\"",
    setup_interceptors=edgewall_pack_setup
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
    resolve=flick_a_coin_resolve,
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
    resolve=frantic_firebolt_resolve,
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
    mana_cost="{3}{R} // {1}{R}",
    colors={Color.RED},
    subtypes={"//", "Giant", "Instant"},
    text="",
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
    setup_interceptors=harried_spearguard_setup
)

HEARTH_ELEMENTAL = make_creature(
    name="Hearth Elemental",
    power=4, toughness=5,
    mana_cost="{5}{R} // {1}{R}",
    colors={Color.RED},
    subtypes={"//", "Elemental", "Sorcery"},
    text="",
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
    resolve=kindled_heroism_resolve,
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
    mana_cost="{2}{R} // {1}{R}",
    colors={Color.RED},
    subtypes={"//", "Dwarf", "Instant", "Knight"},
    text="",
)

MONSTROUS_RAGE = make_instant(
    name="Monstrous Rage",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +2/+0 until end of turn. Create a Monster Role token attached to it. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1 and has trample.)",
    resolve=monstrous_rage_resolve,
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
    mana_cost="{1}{R} // {2}{R}",
    colors={Color.RED},
    subtypes={"//", "Human", "Instant", "Peasant"},
    text="",
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
    setup_interceptors=redcap_gutterdweller_setup
)

REDCAP_THIEF = make_creature(
    name="Redcap Thief",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Rogue"},
    text="When this creature enters, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
    setup_interceptors=redcap_thief_setup
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
    resolve=stonesplitter_bolt_resolve,
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
    resolve=torch_the_tower_resolve,
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
    mana_cost="{4}{R} // {1}{R}",
    colors={Color.RED},
    subtypes={"//", "Giant", "Instant"},
    text="",
)

UNRULY_CATAPULT = make_artifact_creature(
    name="Unruly Catapult",
    power=0, toughness=4,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Construct"},
    text="Defender\n{T}: This creature deals 1 damage to each opponent.\nWhenever you cast an instant or sorcery spell, untap this creature.",
    setup_interceptors=unruly_catapult_setup
)

VIRTUE_OF_COURAGE = make_enchantment(
    name="Virtue of Courage",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Whenever a source you control deals noncombat damage to an opponent, you may exile that many cards from the top of your library. You may play those cards this turn.\n// Adventure — Embereth Blaze {1}{R} (Instant)\nEmbereth Blaze deals 2 damage to any target.",
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
    resolve=witchstalker_frenzy_resolve,
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
    mana_cost="{4}{G} // {1}{G}",
    colors={Color.GREEN},
    subtypes={"//", "Plant", "Sorcery", "Wurm"},
    text="",
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
    setup_interceptors=blossoming_tortoise_setup
)

BRAMBLE_FAMILIAR = make_creature(
    name="Bramble Familiar",
    power=2, toughness=2,
    mana_cost="{1}{G} // {5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"//", "Elemental", "Raccoon", "Sorcery"},
    text="",
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
    setup_interceptors=elvish_archivist_setup
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
    mana_cost="{3}{G} // {1}{G}",
    colors={Color.GREEN},
    subtypes={"//", "Elf", "Fox", "Instant", "Warrior"},
    text="",
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
    setup_interceptors=gruff_triplets_setup
)

HAMLET_GLUTTON = make_creature(
    name="Hamlet Glutton",
    power=6, toughness=6,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Giant"},
    text="Bargain (You may sacrifice an artifact, enchantment, or token as you cast this spell.)\nThis spell costs {2} less to cast if it's bargained.\nTrample\nWhen this creature enters, you gain 3 life.",
    setup_interceptors=hamlet_glutton_setup
)

HOLLOW_SCAVENGER = make_creature(
    name="Hollow Scavenger",
    power=3, toughness=2,
    mana_cost="{2}{G} // {G}",
    colors={Color.GREEN},
    subtypes={"//", "Sorcery", "Wolf"},
    text="",
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
    resolve=leaping_ambush_resolve,
)

NIGHT_OF_THE_SWEETS_REVENGE = make_enchantment(
    name="Night of the Sweets' Revenge",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\nFoods you control have \"{T}: Add {G}.\"\n{5}{G}{G}, Sacrifice this enchantment: Creatures you control get +X/+X until end of turn, where X is the number of Foods you control. Activate only as a sorcery.",
    setup_interceptors=night_of_sweets_revenge_setup
)

REDTOOTH_GENEALOGIST = make_creature(
    name="Redtooth Genealogist",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Advisor", "Elf"},
    text="When this creature enters, create a Royal Role token attached to another target creature you control. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1 and has ward {1}.)",
    setup_interceptors=redtooth_genealogist_setup
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
    resolve=royal_treatment_resolve,
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
    setup_interceptors=skybeast_tracker_setup
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
    mana_cost="{4}{G}{G} // {1}{G}",
    colors={Color.GREEN},
    subtypes={"//", "Giant", "Sorcery", "Warrior"},
    text="",
)

TANGLESPAN_LOOKOUT = make_creature(
    name="Tanglespan Lookout",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Satyr"},
    text="Whenever an Aura you control enters, draw a card.",
    setup_interceptors=tanglespan_lookout_setup
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
    resolve=titanic_growth_resolve,
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
    setup_interceptors=tough_cookie_setup
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
    setup_interceptors=up_the_beanstalk_setup
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
    text="If you tap a basic land for mana, it produces three times as much of that mana instead.\n// Adventure — Garenbrig Growth {G} (Sorcery)\nReturn target creature or land card from your graveyard to your hand.",
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
    setup_interceptors=ash_party_crasher_setup
)

ERIETTE_OF_THE_CHARMED_APPLE = make_creature(
    name="Eriette of the Charmed Apple",
    power=2, toughness=4,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Each creature that's enchanted by an Aura you control can't attack you or planeswalkers you control.\nAt the beginning of your end step, each opponent loses X life and you gain X life, where X is the number of Auras you control.",
    setup_interceptors=eriette_of_the_charmed_apple_setup
)

FAUNSBANE_TROLL = make_creature(
    name="Faunsbane Troll",
    power=4, toughness=4,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Troll"},
    text="When this creature enters, create a Monster Role token attached to it. (Enchanted creature gets +1/+1 and has trample.)\n{1}, Sacrifice an Aura attached to this creature: This creature fights target creature you don't control. If that creature would die this turn, exile it instead. Activate only as a sorcery.",
    setup_interceptors=faunsbane_troll_setup
)

THE_GOOSE_MOTHER = make_creature(
    name="The Goose Mother",
    power=2, toughness=2,
    mana_cost="{X}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Bird", "Hydra"},
    supertypes={"Legendary"},
    text="Flying\nThe Goose Mother enters with X +1/+1 counters on it.\nWhen The Goose Mother enters, create half X Food tokens, rounded up.\nWhenever The Goose Mother attacks, you may sacrifice a Food. If you do, draw a card.",
    setup_interceptors=the_goose_mother_setup
)

GRETA_SWEETTOOTH_SCOURGE = make_creature(
    name="Greta, Sweettooth Scourge",
    power=3, toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="When Greta enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\n{G}, Sacrifice a Food: Put a +1/+1 counter on target creature. Activate only as a sorcery.\n{1}{B}, Sacrifice a Food: You draw a card and you lose 1 life.",
    setup_interceptors=greta_sweettooth_scourge_setup
)

HYLDA_OF_THE_ICY_CROWN = make_creature(
    name="Hylda of the Icy Crown",
    power=3, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Whenever you tap an untapped creature an opponent controls, you may pay {1}. When you do, choose one —\n• Create a 4/4 white and blue Elemental creature token.\n• Put a +1/+1 counter on each creature you control.\n• Scry 2, then draw a card.",
    setup_interceptors=hylda_of_the_icy_crown_setup
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
    setup_interceptors=neva_stalked_by_nightmares_setup
)

OBYRA_DREAMING_DUELIST = make_creature(
    name="Obyra, Dreaming Duelist",
    power=2, toughness=2,
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Faerie", "Warrior"},
    supertypes={"Legendary"},
    text="Flash\nFlying\nWhenever another Faerie you control enters, each opponent loses 1 life.",
    setup_interceptors=obyra_dreaming_duelist_setup
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
    setup_interceptors=ruby_daring_tracker_setup
)

SHARAE_OF_NUMBING_DEPTHS = make_creature(
    name="Sharae of Numbing Depths",
    power=2, toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Merfolk", "Wizard"},
    supertypes={"Legendary"},
    text="When Sharae enters, tap target creature an opponent controls and put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nWhenever you tap one or more untapped creatures your opponents control, draw a card. This ability triggers only once each turn.",
    setup_interceptors=sharae_of_numbing_depths_setup
)

SYR_ARMONT_THE_REDEEMER = make_creature(
    name="Syr Armont, the Redeemer",
    power=4, toughness=4,
    mana_cost="{3}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="When Syr Armont enters, create a Monster Role token attached to another target creature you control. (If you control another Role on it, put that one into the graveyard. Enchanted creature gets +1/+1 and has trample.)\nEnchanted creatures you control get +1/+1.",
    setup_interceptors=syr_armont_the_redeemer_setup
)

TALION_THE_KINDLY_LORD = make_creature(
    name="Talion, the Kindly Lord",
    power=3, toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Faerie", "Noble"},
    supertypes={"Legendary"},
    text="Flying\nAs Talion enters, choose a number between 1 and 10.\nWhenever an opponent casts a spell with mana value, power, or toughness equal to the chosen number, that player loses 2 life and you draw a card.",
    setup_interceptors=talion_the_kindly_lord_setup
)

TOTENTANZ_SWARM_PIPER = make_creature(
    name="Totentanz, Swarm Piper",
    power=2, toughness=3,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Bard", "Human", "Warlock"},
    supertypes={"Legendary"},
    text="Whenever Totentanz or another nontoken creature you control dies, create a 1/1 black Rat creature token with \"This token can't block.\"\n{1}{B}: Target attacking Rat you control gains deathtouch until end of turn.",
    setup_interceptors=totentanz_swarm_piper_setup
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
    mana_cost="{G}{U}{R} // {2}{G}{U}{R}",
    colors={Color.GREEN, Color.RED, Color.BLUE},
    subtypes={"//", "Giant", "Instant", "Noble"},
    supertypes={"Legendary"},
    text="",
)

CALLOUS_SELLSWORD = make_creature(
    name="Callous Sell-Sword",
    power=2, toughness=2,
    mana_cost="{1}{B} // {R}",
    colors={Color.BLACK},
    subtypes={"//", "Human", "Soldier", "Sorcery"},
    text="",
)

CRUEL_SOMNOPHAGE = make_creature(
    name="Cruel Somnophage",
    power=0, toughness=0,
    mana_cost="{1}{B} // {1}{U}",
    colors={Color.BLACK},
    subtypes={"//", "Nightmare", "Sorcery"},
    text="",
)

DECADENT_DRAGON = make_creature(
    name="Decadent Dragon",
    power=4, toughness=4,
    mana_cost="{2}{R}{R} // {2}{B}",
    colors={Color.RED},
    subtypes={"//", "Dragon", "Instant"},
    text="",
)

DEVOURING_SUGARMAW = make_creature(
    name="Devouring Sugarmaw",
    power=6, toughness=6,
    mana_cost="{2}{B}{B} // {1}{W}",
    colors={Color.BLACK},
    subtypes={"//", "Horror", "Instant"},
    text="",
)

ELUSIVE_OTTER = make_creature(
    name="Elusive Otter",
    power=1, toughness=1,
    mana_cost="{U} // {X}{G}",
    colors={Color.BLUE},
    subtypes={"//", "Otter", "Sorcery"},
    text="",
)

FROLICKING_FAMILIAR = make_creature(
    name="Frolicking Familiar",
    power=2, toughness=2,
    mana_cost="{2}{U} // {R}",
    colors={Color.BLUE},
    subtypes={"//", "Instant", "Otter", "Wizard"},
    text="",
)

GINGERBREAD_HUNTER = make_creature(
    name="Gingerbread Hunter",
    power=5, toughness=5,
    mana_cost="{4}{G} // {2}{B}",
    colors={Color.GREEN},
    subtypes={"//", "Giant", "Instant"},
    text="",
)

HEARTFLAME_DUELIST = make_creature(
    name="Heartflame Duelist",
    power=3, toughness=1,
    mana_cost="{1}{W} // {2}{R}",
    colors={Color.WHITE},
    subtypes={"//", "Human", "Instant", "Knight"},
    text="",
)

IMODANES_RECRUITER = make_creature(
    name="Imodane's Recruiter",
    power=2, toughness=2,
    mana_cost="{2}{R} // {4}{W}",
    colors={Color.RED},
    subtypes={"//", "Human", "Knight", "Sorcery"},
    text="",
)

KELLAN_THE_FAEBLOODED = make_creature(
    name="Kellan, the Fae-Blooded",
    power=2, toughness=2,
    mana_cost="{2}{R} // {1}{W}",
    colors={Color.RED},
    subtypes={"//", "Faerie", "Human", "Sorcery"},
    supertypes={"Legendary"},
    text="",
)

MOSSWOOD_DREADKNIGHT = make_creature(
    name="Mosswood Dreadknight",
    power=3, toughness=2,
    mana_cost="{1}{G} // {1}{B}",
    colors={Color.GREEN},
    subtypes={"//", "Human", "Knight", "Sorcery"},
    text="",
)

PICNIC_RUINER = make_creature(
    name="Picnic Ruiner",
    power=2, toughness=2,
    mana_cost="{1}{R} // {3}{G}",
    colors={Color.RED},
    subtypes={"//", "Goblin", "Rogue", "Sorcery"},
    text="",
)

POLLENSHIELD_HARE = make_creature(
    name="Pollen-Shield Hare",
    power=2, toughness=2,
    mana_cost="{1}{W} // {G}",
    colors={Color.WHITE},
    subtypes={"//", "Rabbit", "Sorcery"},
    text="",
)

QUESTING_DRUID = make_creature(
    name="Questing Druid",
    power=1, toughness=1,
    mana_cost="{1}{G} // {1}{R}",
    colors={Color.GREEN},
    subtypes={"//", "Druid", "Human", "Instant"},
    text="",
)

SCALDING_VIPER = make_creature(
    name="Scalding Viper",
    power=2, toughness=1,
    mana_cost="{1}{R} // {1}{U}",
    colors={Color.RED},
    subtypes={"//", "Elemental", "Snake", "Sorcery"},
    text="",
)

SHROUDED_SHEPHERD = make_creature(
    name="Shrouded Shepherd",
    power=2, toughness=2,
    mana_cost="{1}{W} // {1}{B}",
    colors={Color.WHITE},
    subtypes={"//", "Sorcery", "Spirit", "Warrior"},
    text="",
)

SPELLSCORN_COVEN = make_creature(
    name="Spellscorn Coven",
    power=2, toughness=3,
    mana_cost="{3}{B} // {2}{U}",
    colors={Color.BLACK},
    subtypes={"//", "Faerie", "Instant", "Warlock"},
    text="",
)

TEMPEST_HART = make_creature(
    name="Tempest Hart",
    power=3, toughness=4,
    mana_cost="{3}{G} // {1}{U}",
    colors={Color.GREEN},
    subtypes={"//", "Elemental", "Elk", "Instant"},
    text="",
)

THREADBIND_CLIQUE = make_creature(
    name="Threadbind Clique",
    power=3, toughness=3,
    mana_cost="{3}{U} // {2}{W}",
    colors={Color.BLUE},
    subtypes={"//", "Faerie", "Instant"},
    text="",
)

TWINING_TWINS = make_creature(
    name="Twining Twins",
    power=4, toughness=4,
    mana_cost="{2}{U}{U} // {1}{W}",
    colors={Color.BLUE},
    subtypes={"//", "Faerie", "Instant", "Wizard"},
    text="",
)

WOODLAND_ACOLYTE = make_creature(
    name="Woodland Acolyte",
    power=2, toughness=2,
    mana_cost="{2}{W} // {G}",
    colors={Color.WHITE},
    subtypes={"//", "Cleric", "Human", "Instant"},
    text="",
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
    setup_interceptors=candy_trail_setup
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
    setup_interceptors=prophetic_prism_setup
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
    setup_interceptors=soulguide_lantern_setup
)

SYR_GINGER_THE_MEAL_ENDER = make_artifact_creature(
    name="Syr Ginger, the Meal Ender",
    power=3, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Food", "Knight"},
    supertypes={"Legendary"},
    text="Syr Ginger has trample, hexproof, and haste as long as an opponent controls a planeswalker.\nWhenever another artifact you control is put into a graveyard from the battlefield, put a +1/+1 counter on Syr Ginger and scry 1.\n{2}, {T}, Sacrifice Syr Ginger: You gain life equal to its power.",
    setup_interceptors=syr_ginger_setup
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
    setup_interceptors=lady_of_laughter_setup
)

PESTS_OF_HONOR = make_creature(
    name="Pests of Honor",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Mouse"},
    text="Celebration — At the beginning of combat on your turn, if two or more nonland permanents entered the battlefield under your control this turn, put a +1/+1 counter on this creature.",
    setup_interceptors=pests_of_honor_setup
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
    setup_interceptors=storyteller_pixie_setup,
    text="Flying\nWhenever you cast an Adventure spell, draw a card.",
)

EXPERIMENTAL_CONFECTIONER = make_creature(
    name="Experimental Confectioner",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Peasant"},
    text="When this creature enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\nWhenever you sacrifice a Food, create a 1/1 black Rat creature token with \"This token can't block.\"",
    setup_interceptors=experimental_confectioner_setup
)

MALEVOLENT_WITCHKITE = make_creature(
    name="Malevolent Witchkite",
    power=5, toughness=4,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Dragon", "Warlock"},
    text="Flying\nWhen this creature enters, sacrifice any number of artifacts, enchantments, and/or tokens, then draw that many cards.",
    setup_interceptors=malevolent_witchkite_setup
)

OLD_FLITTERFANG = make_creature(
    name="Old Flitterfang",
    power=3, toughness=4,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Faerie", "Rat"},
    supertypes={"Legendary"},
    text="Flying\nAt the beginning of each end step, if a creature died this turn, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\n{2}{B}, Sacrifice another creature or artifact: Old Flitterfang gets +2/+2 until end of turn.",
    setup_interceptors=old_flitterfang_setup
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
    setup_interceptors=ogre_chitterlord_setup
)

INTREPID_TRUFFLESNOUT = make_creature(
    name="Intrepid Trufflesnout",
    power=3, toughness=1,
    mana_cost="{1}{G} // {1}{G}",
    colors={Color.GREEN},
    subtypes={"//", "Boar", "Instant"},
    text="",
)

PROVISIONS_MERCHANT = make_creature(
    name="Provisions Merchant",
    power=3, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Peasant"},
    text="When this creature enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\nWhenever this creature attacks, you may sacrifice a Food. If you do, attacking creatures get +1/+1 and gain trample until end of turn.",
    setup_interceptors=provisions_merchant_setup
)

WILDWOOD_MENTOR = make_creature(
    name="Wildwood Mentor",
    power=1, toughness=1,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="Whenever a token you control enters, put a +1/+1 counter on this creature.\nWhenever this creature attacks, another target attacking creature gets +X/+X until end of turn, where X is this creature's power.",
    setup_interceptors=wildwood_mentor_setup
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

print(f"Loaded {len(WILDS_OF_ELDRAINE_CARDS)} Wilds_of_Eldraine cards")
