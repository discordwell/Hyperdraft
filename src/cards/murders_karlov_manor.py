"""
Murders_at_Karlov_Manor (MKM) Card Implementations

Real card data fetched from Scryfall API.
279 cards in set.
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
    make_static_pt_boost, make_keyword_grant, make_upkeep_trigger,
    make_spell_cast_trigger, make_damage_trigger, make_life_gain_trigger,
    other_creatures_you_control, other_creatures_with_subtype,
    creatures_you_control, creatures_with_subtype,
    create_modal_choice, create_sacrifice_choice, create_target_choice,
    create_hand_reveal_choice,
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

# --- WHITE CREATURES ---

def absolving_lammasu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies: gain 3 life"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def griffnaut_tracker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: exile up to two target cards from a single graveyard"""
    # Simplified - just trigger placeholder
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting system
    return [make_etb_trigger(obj, etb_effect)]


def haazda_vigilante_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters or attacks: put +1/+1 counter on target creature with power 2 or less"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting - placeholder
        return []

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting

    return [
        make_etb_trigger(obj, etb_effect),
        make_attack_trigger(obj, attack_effect)
    ]


def inside_source_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: create a 2/2 white and blue Detective creature token"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Detective Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Detective'],
                'colors': [Color.WHITE, Color.BLUE]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def museum_nightwatch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies: create a 2/2 white and blue Detective creature token"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Detective Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Detective'],
                'colors': [Color.WHITE, Color.BLUE]
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def novice_inspector_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: investigate (create Clue token)"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Clue',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Clue'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def wojek_investigator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At beginning of upkeep: investigate for each opponent with more cards"""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        my_hand_size = len(state.players[obj.controller].hand) if obj.controller in state.players else 0
        for p_id, player in state.players.items():
            if p_id != obj.controller and len(player.hand) > my_hand_size:
                events.append(Event(
                    type=EventType.OBJECT_CREATED,
                    payload={
                        'name': 'Clue',
                        'controller': obj.controller,
                        'types': [CardType.ARTIFACT],
                        'subtypes': ['Clue'],
                        'colors': []
                    },
                    source=obj.id
                ))
        return events
    return [make_upkeep_trigger(obj, upkeep_effect)]


# --- BLUE CREATURES ---

def agency_outfitter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: search for Magnifying Glass and/or Thinking Cap"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need search/library system
    return [make_etb_trigger(obj, etb_effect)]


def cold_case_cracker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies: investigate"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Clue',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Clue'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def benthic_criminologists_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters or attacks: may sacrifice artifact to draw a card"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need sacrifice choice + draw

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []

    return [
        make_etb_trigger(obj, etb_effect),
        make_attack_trigger(obj, attack_effect)
    ]


def forensic_gadgeteer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an artifact spell: investigate"""
    def artifact_cast_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.ARTIFACT in spell_types

    def artifact_cast_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Clue',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Clue'],
                'colors': []
            },
            source=obj.id
        )]

    return [make_spell_cast_trigger(obj, artifact_cast_effect,
                                     spell_type_filter={CardType.ARTIFACT})]


def hotshot_investigators_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: return up to one other creature to hand. If you controlled it, investigate."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find other creatures on the battlefield
        legal_targets = []
        for oid, o in state.objects.items():
            if (oid != obj.id and
                o.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in o.characteristics.types):
                legal_targets.append(oid)

        if not legal_targets:
            return []

        def handle_bounce(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            target_id = selected[0]
            target = gs.objects.get(target_id)
            if not target or target.zone != ZoneType.BATTLEFIELD:
                return []
            events = [Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': target_id,
                    'from_zone_type': ZoneType.BATTLEFIELD,
                    'to_zone_type': ZoneType.HAND
                },
                source=choice.source_id
            )]
            # If you controlled it, investigate
            if target.controller == obj.controller:
                events.append(Event(
                    type=EventType.OBJECT_CREATED,
                    payload={
                        'name': 'Clue',
                        'controller': obj.controller,
                        'types': [CardType.ARTIFACT],
                        'subtypes': ['Clue'],
                        'colors': []
                    },
                    source=choice.source_id
                ))
            return events

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Hotshot Investigators: Choose up to one other creature to return to hand",
            min_targets=0,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_bounce

        return []
    return [make_etb_trigger(obj, etb_effect)]


def projektor_inspector_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this or another Detective enters/is turned face up: draw then discard"""
    def detective_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                'Detective' in entering.characteristics.subtypes)

    def detective_etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]

    return [make_etb_trigger(obj, detective_etb_effect, filter_fn=detective_etb_filter)]


def steamcore_scholar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: draw 2, then discard 2 unless you discard instant/sorcery or flying creature"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


def surveillance_monitor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: may collect evidence 4"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Collect evidence needs implementation
    return [make_etb_trigger(obj, etb_effect)]


# --- BLACK CREATURES ---

def alley_assailant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When turned face up: opponent loses 3 life, you gain 3 life"""
    # Face-up triggers need special handling - placeholder
    return []


def barbed_servitor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: suspect it. Combat damage to player: draw, lose 1 life.
       When dealt damage: opponent loses that much life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Suspect would add menace, can't block markers
        return []

    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': -1}, source=obj.id)
        ]

    return [
        make_etb_trigger(obj, etb_effect),
        make_damage_trigger(obj, combat_damage_effect, combat_only=True)
    ]


def case_of_stashed_skeleton_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: create 2/1 black Skeleton token and suspect it"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Skeleton Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Skeleton'],
                'colors': [Color.BLACK]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def clandestine_meddler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: suspect up to one other target creature you control"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting
    return [make_etb_trigger(obj, etb_effect)]


def homicide_investigator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever one or more nontoken creatures you control die: investigate (once per turn)"""
    def creature_death_filter(event: Event, state: GameState, source: GameObject) -> bool:
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
        return (dying.controller == source.controller and
                CardType.CREATURE in dying.characteristics.types and
                not dying.characteristics.token)

    def creature_death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Clue',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Clue'],
                'colors': []
            },
            source=obj.id
        )]

    return [make_death_trigger(obj, creature_death_effect, filter_fn=creature_death_filter)]


def hunted_bonebrute_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: opponent creates two 1/1 Dog tokens. When dies: each opponent loses 3 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for p_id in state.players.keys():
            if p_id != obj.controller:
                events.append(Event(
                    type=EventType.OBJECT_CREATED,
                    payload={
                        'name': 'Dog Token',
                        'controller': p_id,
                        'power': 1,
                        'toughness': 1,
                        'types': [CardType.CREATURE],
                        'subtypes': ['Dog'],
                        'colors': [Color.WHITE]
                    },
                    source=obj.id
                ))
                events.append(Event(
                    type=EventType.OBJECT_CREATED,
                    payload={
                        'name': 'Dog Token',
                        'controller': p_id,
                        'power': 1,
                        'toughness': 1,
                        'types': [CardType.CREATURE],
                        'subtypes': ['Dog'],
                        'colors': [Color.WHITE]
                    },
                    source=obj.id
                ))
        return events

    def death_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for p_id in state.players.keys():
            if p_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': p_id, 'amount': -3},
                    source=obj.id
                ))
        return events

    return [
        make_etb_trigger(obj, etb_effect),
        make_death_trigger(obj, death_effect)
    ]


def massacre_girl_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creatures you control have wither. Whenever opponent's creature dies with toughness < 1: draw."""
    # Wither grants need ability query system
    def wither_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)

    def wither_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []))
        if 'wither' not in granted:
            granted.append('wither')
        new_event.payload['granted'] = granted
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=wither_filter,
        handler=wither_handler,
        duration='while_on_battlefield'
    )]


def nightdrinker_moroii_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: lose 3 life"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': -3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def persuasive_interrogators_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: investigate. Whenever you sacrifice a Clue: opponent gets 2 poison counters."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Clue',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Clue'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def undercity_eliminator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: may sacrifice artifact/creature. When you do, exile target opponent's creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need sacrifice + targeting
    return [make_etb_trigger(obj, etb_effect)]


def unscrupulous_agent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: opponent exiles a card from their hand"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need opponent targeting
        return []
    return [make_etb_trigger(obj, etb_effect)]


def vein_ripper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a creature dies: opponent loses 2 life, you gain 2 life"""
    def creature_death_filter(event: Event, state: GameState, source: GameObject) -> bool:
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
        return CardType.CREATURE in dying.characteristics.types

    def creature_death_effect(event: Event, state: GameState) -> list[Event]:
        events = [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
        for p_id in state.players.keys():
            if p_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': p_id, 'amount': -2},
                    source=obj.id
                ))
        return events

    # Use a custom interceptor since death_trigger is for self-dying
    def filter_fn(event: Event, state: GameState) -> bool:
        return creature_death_filter(event, state, obj)

    def handler_fn(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=creature_death_effect(event, state)
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=filter_fn,
        handler=handler_fn,
        duration='while_on_battlefield'
    )]


# --- RED CREATURES ---

def cornered_crook_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: may sacrifice artifact. When you do, deal 3 damage to any target."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need sacrifice + targeting
    return [make_etb_trigger(obj, etb_effect)]


def crime_novelist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you sacrifice an artifact: put +1/+1 counter on this and add {R}"""
    def artifact_sacrifice_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('cause') != 'sacrifice':
            return False
        sacrificed_id = event.payload.get('object_id')
        sacrificed = state.objects.get(sacrificed_id)
        if not sacrificed:
            return False
        return (sacrificed.controller == obj.controller and
                CardType.ARTIFACT in sacrificed.characteristics.types)

    def artifact_sacrifice_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.MANA_ADDED,
                payload={'player': obj.controller, 'color': 'R', 'amount': 1},
                source=obj.id
            )
        ]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=artifact_sacrifice_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=artifact_sacrifice_effect(e, s)),
        duration='while_on_battlefield'
    )]


def frantic_scapegoat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: suspect it"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Suspect markers
    return [make_etb_trigger(obj, etb_effect)]


def gearbane_orangutan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: destroy up to one artifact OR sacrifice artifact for +2 counters"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need choice + targeting
    return [make_etb_trigger(obj, etb_effect)]


def harried_dronesmith_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At beginning of combat: create 1/1 Thopter with flying and haste"""
    def combat_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.PHASE_START and
                event.payload.get('phase') == 'combat' and
                state.active_player == obj.controller)

    def combat_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Thopter Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.ARTIFACT, CardType.CREATURE],
                'subtypes': ['Thopter'],
                'colors': [],
                'keywords': ['flying', 'haste']
            },
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=combat_effect(e, s)),
        duration='while_on_battlefield'
    )]


def krenkos_buzzcrusher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: destroy nonbasic land for each player"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need land destruction logic
    return [make_etb_trigger(obj, etb_effect)]


def person_of_interest_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: suspect it. Create 2/2 Detective token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Detective Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Detective'],
                'colors': [Color.WHITE, Color.BLUE]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def pyrotechnic_performer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this or another creature you control is turned face up: deals damage to each opponent"""
    # Face-up triggers need special handling
    return []


def vengeful_tracker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever opponent sacrifices artifact: deal 2 damage to them"""
    def opponent_artifact_sac_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('cause') != 'sacrifice':
            return False
        sacrificed_id = event.payload.get('object_id')
        sacrificed = state.objects.get(sacrificed_id)
        if not sacrificed:
            return False
        return (sacrificed.controller != obj.controller and
                CardType.ARTIFACT in sacrificed.characteristics.types)

    def opponent_artifact_sac_effect(event: Event, state: GameState) -> list[Event]:
        sacrificed_id = event.payload.get('object_id')
        sacrificed = state.objects.get(sacrificed_id)
        if sacrificed:
            return [Event(
                type=EventType.DAMAGE,
                payload={'target': sacrificed.controller, 'amount': 2, 'source': obj.id, 'is_combat': False},
                source=obj.id
            )]
        return []

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=opponent_artifact_sac_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=opponent_artifact_sac_effect(e, s)),
        duration='while_on_battlefield'
    )]


# --- GREEN CREATURES ---

def aftermath_analyst_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: mill 3"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def glint_weaver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: distribute 3 +1/+1 counters, gain life equal to greatest toughness"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting for counters, then calculate toughness
        return []
    return [make_etb_trigger(obj, etb_effect)]


def loxodon_eavesdropper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: investigate"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Clue',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Clue'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def rubblebelt_maverick_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: surveil 2"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- MULTICOLOR CREATURES ---

def agrus_kos_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters or attacks: choose target creature, suspect it or exile if already suspected"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []

    return [
        make_etb_trigger(obj, etb_effect),
        make_attack_trigger(obj, attack_effect)
    ]


def alquist_proft_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: investigate"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Clue',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Clue'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def aurelia_the_law_above_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a player attacks with 3+ creatures: draw. With 5+: deal 3 to opponents, gain 3."""
    def attack_filter(event: Event, state: GameState) -> bool:
        # Would need to track attack declaration with creature counts
        return False

    return []  # Complex tracking needed


def blood_spatter_analysis_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: deal 3 damage to target opponent's creature"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting
    return [make_etb_trigger(obj, etb_effect)]


def detectives_satchel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: investigate twice"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.OBJECT_CREATED,
                payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
                source=obj.id
            ),
            Event(
                type=EventType.OBJECT_CREATED,
                payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
                source=obj.id
            )
        ]
    return [make_etb_trigger(obj, etb_effect)]


def dog_walker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When turned face up: create two 1/1 Dog tokens"""
    # Face-up trigger
    return []


def ezrim_agency_chief_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: investigate twice"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.OBJECT_CREATED,
                payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
                source=obj.id
            ),
            Event(
                type=EventType.OBJECT_CREATED,
                payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
                source=obj.id
            )
        ]
    return [make_etb_trigger(obj, etb_effect)]


def gadget_technician_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters or turned face up: create 1/1 Thopter with flying"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Thopter Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.ARTIFACT, CardType.CREATURE],
                'subtypes': ['Thopter'],
                'colors': [],
                'keywords': ['flying']
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def gleaming_geardrake_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: investigate. Whenever you sacrifice artifact: +1/+1 counter."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
            source=obj.id
        )]

    def artifact_sacrifice_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('cause') != 'sacrifice':
            return False
        sacrificed_id = event.payload.get('object_id')
        sacrificed = state.objects.get(sacrificed_id)
        if not sacrificed:
            return False
        return (sacrificed.controller == obj.controller and
                CardType.ARTIFACT in sacrificed.characteristics.types)

    def artifact_sacrifice_effect(event: Event, state: GameState) -> list[Event]:
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
            filter=artifact_sacrifice_filter,
            handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=artifact_sacrifice_effect(e, s)),
            duration='while_on_battlefield'
        )
    ]


def izoni_center_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters or attacks: may collect evidence 4, create two Spider tokens"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Spider Token',
                    'controller': obj.controller,
                    'power': 2,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Spider'],
                    'colors': [Color.BLACK, Color.GREEN],
                    'keywords': ['menace', 'reach']
                },
                source=obj.id
            ),
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Spider Token',
                    'controller': obj.controller,
                    'power': 2,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Spider'],
                    'colors': [Color.BLACK, Color.GREEN],
                    'keywords': ['menace', 'reach']
                },
                source=obj.id
            )
        ]

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return etb_effect(event, state)

    return [
        make_etb_trigger(obj, etb_effect),
        make_attack_trigger(obj, attack_effect)
    ]


def judith_carnage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast instant/sorcery: choose deathtouch+lifelink OR create Imp token"""
    def instant_sorcery_cast_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified: create Imp token
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Imp Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Imp'],
                'colors': [Color.RED]
            },
            source=obj.id
        )]

    return [make_spell_cast_trigger(obj, instant_sorcery_cast_effect,
                                     spell_type_filter={CardType.INSTANT, CardType.SORCERY})]


def kraul_whipcracker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: destroy target token an opponent controls"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting
    return [make_etb_trigger(obj, etb_effect)]


def lazav_wearer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks: exile target card from graveyard, investigate"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def meddling_youths_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you attack with 3+ creatures: investigate"""
    # Would need attack tracking
    return []


def private_eye_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Detectives you control get +1/+1"""
    def affects_detectives(target: GameObject, state: GameState) -> bool:
        return (target.id != obj.id and
                target.controller == obj.controller and
                'Detective' in target.characteristics.subtypes and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)

    return make_static_pt_boost(obj, 1, 1, affects_detectives)


def rakdos_patron_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At beginning of end step: opponent may sacrifice 2 nonland/nontoken permanents or you draw 2"""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified: just draw 2
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]

    def end_step_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.PHASE_START and
                event.payload.get('phase') == 'end_step' and
                state.active_player == obj.controller)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=end_step_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=end_step_effect(e, s)),
        duration='while_on_battlefield'
    )]


def shady_informant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies: deal 2 damage to any target"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting
    return [make_death_trigger(obj, death_effect)]


def tolsimir_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: create Voja Fenstalker, legendary 5/5 Wolf with trample"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Voja Fenstalker',
                'controller': obj.controller,
                'power': 5,
                'toughness': 5,
                'types': [CardType.CREATURE],
                'subtypes': ['Wolf'],
                'supertypes': ['Legendary'],
                'colors': [Color.GREEN, Color.WHITE],
                'keywords': ['trample']
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def voja_jaws_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks: put X +1/+1 counters on each creature you control (X = Elves). Draw card per Wolf."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Count elves
        elf_count = 0
        wolf_count = 0
        for oid, o in state.objects.items():
            if (o.controller == obj.controller and
                o.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in o.characteristics.types):
                if 'Elf' in o.characteristics.subtypes:
                    elf_count += 1
                if 'Wolf' in o.characteristics.subtypes:
                    wolf_count += 1

        events = []
        # Add counters to each creature
        if elf_count > 0:
            for oid, o in state.objects.items():
                if (o.controller == obj.controller and
                    o.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in o.characteristics.types):
                    events.append(Event(
                        type=EventType.COUNTER_ADDED,
                        payload={'object_id': oid, 'counter_type': '+1/+1', 'amount': elf_count},
                        source=obj.id
                    ))

        # Draw for wolves
        if wolf_count > 0:
            events.append(Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': wolf_count},
                source=obj.id
            ))

        return events

    return [make_attack_trigger(obj, attack_effect)]


def warleaders_call_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creatures you control get +1/+1. Whenever a creature you control enters: deal 1 to each opponent."""
    # Static +1/+1 boost
    interceptors = make_static_pt_boost(obj, 1, 1, creatures_you_control(obj))

    # ETB trigger for creatures
    def creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                CardType.CREATURE in entering.characteristics.types)

    def creature_etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for p_id in state.players.keys():
            if p_id != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': p_id, 'amount': 1, 'source': obj.id, 'is_combat': False},
                    source=obj.id
                ))
        return events

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: creature_etb_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=creature_etb_effect(e, s)),
        duration='while_on_battlefield'
    ))

    return interceptors


def wispdrinker_vampire_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another creature you control with power 2 or less enters: opponent loses 1, you gain 1"""
    def small_creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering or entering.id == source.id:
            return False
        if entering.controller != source.controller:
            return False
        if CardType.CREATURE not in entering.characteristics.types:
            return False
        power = entering.characteristics.power or 0
        return power <= 2

    def small_creature_etb_effect(event: Event, state: GameState) -> list[Event]:
        events = [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
        for p_id in state.players.keys():
            if p_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': p_id, 'amount': -1},
                    source=obj.id
                ))
        return events

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: small_creature_etb_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=small_creature_etb_effect(e, s)),
        duration='while_on_battlefield'
    )]


def yarus_roar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other creatures you control have haste"""
    def haste_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target or target.id == obj.id:
            return False
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)

    def haste_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []))
        if 'haste' not in granted:
            granted.append('haste')
        new_event.payload['granted'] = granted
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=haste_filter,
        handler=haste_handler,
        duration='while_on_battlefield'
    )]


# --- ARTIFACT CREATURES ---

def magnetic_snuffler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: return Equipment from graveyard. Whenever you sacrifice artifact: +1/+1 counter."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need graveyard search

    def artifact_sacrifice_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('cause') != 'sacrifice':
            return False
        sacrificed_id = event.payload.get('object_id')
        sacrificed = state.objects.get(sacrificed_id)
        if not sacrificed:
            return False
        return (sacrificed.controller == obj.controller and
                CardType.ARTIFACT in sacrificed.characteristics.types)

    def artifact_sacrifice_effect(event: Event, state: GameState) -> list[Event]:
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
            filter=artifact_sacrifice_filter,
            handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=artifact_sacrifice_effect(e, s)),
            duration='while_on_battlefield'
        )
    ]


def sanitation_automaton_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: surveil 1"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- CASE ENCHANTMENTS (simplified) ---

def case_of_uneaten_feast_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a creature you control enters: gain 1 life"""
    def creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                CardType.CREATURE in entering.characteristics.types)

    def creature_etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: creature_etb_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=creature_etb_effect(e, s)),
        duration='while_on_battlefield'
    )]


def case_of_filched_falcon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: investigate"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def case_of_burning_masks_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: deal 3 damage to target opponent's creature"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting
    return [make_etb_trigger(obj, etb_effect)]


def insidious_roots_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever 1+ creature cards leave your graveyard: create 0/1 Plant, +1/+1 counter on each Plant"""
    def graveyard_leave_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.GRAVEYARD:
            return False
        leaving_id = event.payload.get('object_id')
        # Would need to check if it's a creature card
        return True  # Simplified

    def graveyard_leave_effect(event: Event, state: GameState) -> list[Event]:
        events = [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Plant Token',
                'controller': obj.controller,
                'power': 0,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Plant'],
                'colors': [Color.GREEN]
            },
            source=obj.id
        )]
        # Add counters to all Plants
        for oid, o in state.objects.items():
            if (o.controller == obj.controller and
                o.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in o.characteristics.types and
                'Plant' in o.characteristics.subtypes):
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': oid, 'counter_type': '+1/+1', 'amount': 1},
                    source=obj.id
                ))
        return events

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=graveyard_leave_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=graveyard_leave_effect(e, s)),
        duration='while_on_battlefield'
    )]


def chalk_outline_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever 1+ creature cards leave your graveyard: create Detective token, investigate"""
    def graveyard_leave_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.GRAVEYARD:
            return False
        return True  # Simplified

    def graveyard_leave_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Detective Token',
                    'controller': obj.controller,
                    'power': 2,
                    'toughness': 2,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Detective'],
                    'colors': [Color.WHITE, Color.BLUE]
                },
                source=obj.id
            ),
            Event(
                type=EventType.OBJECT_CREATED,
                payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
                source=obj.id
            )
        ]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=graveyard_leave_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=graveyard_leave_effect(e, s)),
        duration='while_on_battlefield'
    )]


# --- ADDITIONAL WHITE CREATURES ---

def marketwatch_phantom_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another creature you control with power 2 or less enters: gains flying"""
    def small_creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering or entering.id == source.id:
            return False
        if entering.controller != source.controller:
            return False
        if CardType.CREATURE not in entering.characteristics.types:
            return False
        power = entering.characteristics.power or 0
        return power <= 2

    def small_creature_etb_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified - grants flying to self until end of turn
        return []  # Placeholder for keyword granting

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: small_creature_etb_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=small_creature_etb_effect(e, s)),
        duration='while_on_battlefield'
    )]


def neighborhood_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another creature you control with power 2 or less enters: target creature gets +1/+1"""
    def small_creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering or entering.id == source.id:
            return False
        if entering.controller != source.controller:
            return False
        if CardType.CREATURE not in entering.characteristics.types:
            return False
        power = entering.characteristics.power or 0
        return power <= 2

    def small_creature_etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting - simplified
        return []

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: small_creature_etb_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=small_creature_etb_effect(e, s)),
        duration='while_on_battlefield'
    )]


def perimeter_enforcer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another Detective enters or is turned face up: +1/+1 until end of turn"""
    def detective_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering or entering.id == source.id:
            return False
        return (entering.controller == source.controller and
                'Detective' in entering.characteristics.subtypes)

    def detective_etb_effect(event: Event, state: GameState) -> list[Event]:
        # Temporary boost - simplified
        return []

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: detective_etb_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=detective_etb_effect(e, s)),
        duration='while_on_battlefield'
    )]


def case_file_auditor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: look at top 6 cards, may reveal an enchantment"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need library manipulation
        return []
    return [make_etb_trigger(obj, etb_effect)]


def doorkeeper_thrull_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Artifacts and creatures entering don't cause abilities to trigger"""
    # This is a replacement effect - would need special handling
    return []


def delney_streetwise_lookout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creatures with power 2 or less can't be blocked by power 3+. Ability triggers twice."""
    # Complex static ability - placeholder
    return []


# --- ADDITIONAL BLUE CREATURES ---

def jaded_analyst_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you draw your second card each turn: loses defender, gains vigilance"""
    # Would need draw counting
    return []


def furtive_courier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever attacks: draw then discard"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_attack_trigger(obj, attack_effect)]


def coveted_falcon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever attacks: gain control of target permanent you own but don't control"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting
    return [make_attack_trigger(obj, attack_effect)]


def crimestopper_sprite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: tap target creature"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting
    return [make_etb_trigger(obj, etb_effect)]


# --- ADDITIONAL BLACK CREATURES ---

def basilica_stalker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever deals combat damage to player: gain 1 life and surveil 1"""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.SURVEIL, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]


def festerleech_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever deals combat damage to player: mill 2"""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MILL, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]


def rot_farm_mortipede_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever 1+ creature cards leave your graveyard: +1/+0, menace, lifelink"""
    def graveyard_leave_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.GRAVEYARD:
            return False
        leaving_id = event.payload.get('object_id')
        leaving = state.objects.get(leaving_id)
        if leaving and leaving.controller == obj.controller:
            return CardType.CREATURE in leaving.characteristics.types
        return False

    def graveyard_leave_effect(event: Event, state: GameState) -> list[Event]:
        # Temporary power boost - simplified
        return []

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=graveyard_leave_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=graveyard_leave_effect(e, s)),
        duration='while_on_battlefield'
    )]


def snarling_gorehound_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another creature with power 2 or less enters: surveil 1"""
    def small_creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering or entering.id == source.id:
            return False
        if entering.controller != source.controller:
            return False
        if CardType.CREATURE not in entering.characteristics.types:
            return False
        power = entering.characteristics.power or 0
        return power <= 2

    def small_creature_etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SURVEIL, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: small_creature_etb_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=small_creature_etb_effect(e, s)),
        duration='while_on_battlefield'
    )]


def soul_enervation_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: -4/-4 to target. Whenever creature cards leave graveyard: opponents lose 1, you gain 1"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting

    def graveyard_leave_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.GRAVEYARD:
            return False
        leaving_id = event.payload.get('object_id')
        leaving = state.objects.get(leaving_id)
        if leaving and leaving.controller == obj.controller:
            return CardType.CREATURE in leaving.characteristics.types
        return False

    def graveyard_leave_effect(event: Event, state: GameState) -> list[Event]:
        events = [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
        for p_id in state.players.keys():
            if p_id != obj.controller:
                events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': p_id, 'amount': -1}, source=obj.id))
        return events

    return [
        make_etb_trigger(obj, etb_effect),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=graveyard_leave_filter,
            handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=graveyard_leave_effect(e, s)),
            duration='while_on_battlefield'
        )
    ]


# --- ADDITIONAL RED CREATURES ---

def innocent_bystander_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever dealt 3 or more damage: investigate"""
    def damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('target') != obj.id:
            return False
        amount = event.payload.get('amount', 0)
        return amount >= 3

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=damage_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=damage_effect(e, s)),
        duration='while_on_battlefield'
    )]


def krenko_baron_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever artifact goes to graveyard: may pay R to create Goblin token"""
    def artifact_death_filter(event: Event, state: GameState) -> bool:
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
        return CardType.ARTIFACT in dying.characteristics.types

    def artifact_death_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified - creates token without mana check
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Goblin Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Goblin'],
                'colors': [Color.RED],
                'keywords': ['haste']
            },
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=artifact_death_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=artifact_death_effect(e, s)),
        duration='while_on_battlefield'
    )]


def lamplight_phoenix_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies: may exile and collect evidence 4 to return to battlefield"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        # Complex effect - placeholder
        return []
    return [make_death_trigger(obj, death_effect)]


def reckless_detective_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever attacks: may sacrifice artifact or discard to draw and get +2/+0"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need choice system
    return [make_attack_trigger(obj, attack_effect)]


def incinerator_of_guilty_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever deals combat damage to player: may collect evidence X to deal X damage"""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need collect evidence system
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]


# --- ADDITIONAL GREEN CREATURES ---

def sharp_eyed_rookie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a creature enters with greater P/T: put +1/+1 counter and investigate"""
    def creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        if entering.controller != source.controller:
            return False
        if CardType.CREATURE not in entering.characteristics.types:
            return False
        # Check if power or toughness is greater
        entering_power = entering.characteristics.power or 0
        entering_toughness = entering.characteristics.toughness or 0
        source_power = source.characteristics.power or 0
        source_toughness = source.characteristics.toughness or 0
        return entering_power > source_power or entering_toughness > source_toughness

    def creature_etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.COUNTER_ADDED, payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1}, source=obj.id),
            Event(type=EventType.OBJECT_CREATED, payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []}, source=obj.id)
        ]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: creature_etb_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=creature_etb_effect(e, s)),
        duration='while_on_battlefield'
    )]


def sample_collector_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever attacks: may collect evidence 3, put +1/+1 counter on target"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need collect evidence system
    return [make_attack_trigger(obj, attack_effect)]


def tunnel_tipster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At end step: if face-down creature entered, put +1/+1 counter on this"""
    # Would need face-down creature tracking
    return []


def culvert_ambusher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters or turned face up: target creature must block this turn"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting
    return [make_etb_trigger(obj, etb_effect)]


# --- ADDITIONAL MULTICOLOR CREATURES ---

def teysa_opulent_oligarch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At end step: investigate for each opponent who lost life. Clue sacrifice: create Spirit."""
    def end_step_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.PHASE_START and
                event.payload.get('phase') == 'end_step' and
                state.active_player == obj.controller)

    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified - creates one clue
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=end_step_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=end_step_effect(e, s)),
        duration='while_on_battlefield'
    )]


def sumala_sentry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever face-down creature turned face up: +1/+1 counter on it and this"""
    # Would need face-up tracking
    return []


def runebrand_juggler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: suspect up to one target creature you control"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting + suspect
    return [make_etb_trigger(obj, etb_effect)]


def rakish_scoundrel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters or turned face up: target creature gains indestructible"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting
    return [make_etb_trigger(obj, etb_effect)]


def undercover_crocodelf_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever deals combat damage to player: investigate"""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
            source=obj.id
        )]
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]


def evidence_examiner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At beginning of combat: may collect evidence 4. Whenever you collect evidence: investigate."""
    # Would need collect evidence tracking
    return []


def niv_mizzet_guildpact_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever deals combat damage: deals X damage, target draws X, you gain X life"""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        # Count two-color permanents
        color_pairs = 0
        for oid, o in state.objects.items():
            if o.controller == obj.controller and o.zone == ZoneType.BATTLEFIELD:
                colors = o.characteristics.colors or set()
                if len(colors) == 2:
                    color_pairs += 1
        if color_pairs > 0:
            return [
                Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': color_pairs}, source=obj.id),
                Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': color_pairs}, source=obj.id)
            ]
        return []
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]


def tomik_wielder_of_law_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever opponent attacks with 2+ creatures targeting you/planeswalkers: they lose 3 life, you draw"""
    # Would need attack tracking
    return []


def melek_reforged_researcher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Power/toughness = 2x instant/sorcery in graveyard"""
    def power_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        return event.payload.get('object_id') == obj.id

    def toughness_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        return event.payload.get('object_id') == obj.id

    def get_instant_sorcery_count(state: GameState) -> int:
        count = 0
        # Would need to access graveyard
        return count

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        count = get_instant_sorcery_count(state) * 2
        new_event = event.copy()
        new_event.payload['value'] = count
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    def toughness_handler(event: Event, state: GameState) -> InterceptorResult:
        count = get_instant_sorcery_count(state) * 2
        new_event = event.copy()
        new_event.payload['value'] = count
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=power_filter,
            handler=power_handler,
            duration='while_on_battlefield'
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=toughness_filter,
            handler=toughness_handler,
            duration='while_on_battlefield'
        )
    ]


# --- Additional setup functions for cards that were wired ---

def griffnaut_tracker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: exile up to two target cards from a single graveyard"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting
    return [make_etb_trigger(obj, etb_effect)]


def haazda_vigilante_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters or attacks: put +1/+1 counter on target creature with power 2 or less"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting
    return [make_etb_trigger(obj, etb_effect), make_attack_trigger(obj, attack_effect)]


def inside_source_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: create 2/2 Detective token"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Detective Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Detective'],
                'colors': [Color.WHITE, Color.BLUE]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def museum_nightwatch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies: create 2/2 Detective token"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Detective Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Detective'],
                'colors': [Color.WHITE, Color.BLUE]
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def novice_inspector_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: investigate (create Clue)"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def wojek_investigator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At upkeep: investigate for each opponent with more cards"""
    return [make_upkeep_trigger(obj, lambda e, s: [])]  # Simplified


def agency_outfitter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: search for Magnifying Glass/Thinking Cap"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need library search
    return [make_etb_trigger(obj, etb_effect)]


def benthic_criminologists_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters or attacks: may sacrifice artifact to draw"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need sacrifice choice
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []
    return [make_etb_trigger(obj, etb_effect), make_attack_trigger(obj, attack_effect)]


def case_of_filched_falcon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: investigate"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def cold_case_cracker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies: investigate"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def forensic_gadgeteer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast artifact spell: investigate"""
    def artifact_cast_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.SPELL_CAST:
            return False
        spell_id = event.payload.get('object_id')
        spell = state.objects.get(spell_id)
        if not spell or spell.controller != obj.controller:
            return False
        return CardType.ARTIFACT in spell.characteristics.types

    def artifact_cast_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=artifact_cast_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=artifact_cast_effect(e, s)),
        duration='while_on_battlefield'
    )]


def hotshot_investigators_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: return target creature to hand, investigate if yours"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting
    return [make_etb_trigger(obj, etb_effect)]


def steamcore_scholar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: draw 2, then discard 2 (or 1 instant/sorcery/flyer)"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 2}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]


def surveillance_monitor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: may collect evidence 4"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need collect evidence
    return [make_etb_trigger(obj, etb_effect)]


def barbed_servitor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: suspect it. Deals combat damage: draw + lose 1. Dealt damage: opponent loses that much."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need suspect mechanic
    return [make_etb_trigger(obj, etb_effect)]


def case_of_stashed_skeleton_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: create 2/1 Skeleton token and suspect it"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Skeleton Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Skeleton'],
                'colors': [Color.BLACK]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def clandestine_meddler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: suspect up to one creature. Suspected creatures attack: surveil 1."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting + suspect
    return [make_etb_trigger(obj, etb_effect)]


def homicide_investigator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever nontoken creature you control dies: investigate (once per turn)"""
    def death_filter(event: Event, state: GameState) -> bool:
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
        if dying.controller != obj.controller:
            return False
        if CardType.CREATURE not in dying.characteristics.types:
            return False
        return not dying.is_token

    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=death_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=death_effect(e, s)),
        duration='while_on_battlefield'
    )]


def hunted_bonebrute_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: opponent creates 2 Dogs. When dies: each opponent loses 3."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified - in reality would need opponent targeting
        return []
    def death_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for p_id in state.players.keys():
            if p_id != obj.controller:
                events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': p_id, 'amount': -3}, source=obj.id))
        return events
    return [make_etb_trigger(obj, etb_effect), make_death_trigger(obj, death_effect)]


def nightdrinker_moroii_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: lose 3 life"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': -3}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


def persuasive_interrogators_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: investigate. Sacrifice Clue: opponent gets 2 poison."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def undercity_eliminator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: may sacrifice artifact/creature, then exile target opponent creature"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need sacrifice + targeting
    return [make_etb_trigger(obj, etb_effect)]


def unscrupulous_agent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: target opponent exiles a card from hand"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find opponents
        opponents = [p_id for p_id in state.players.keys() if p_id != obj.controller]
        if not opponents:
            return []

        # For now, target first opponent and make them exile at random (simplified)
        target_opp = opponents[0]

        # Find cards in opponent's hand
        hand_zone = state.zones.get(f"{target_opp}_hand")
        if not hand_zone or not hand_zone.objects:
            return []

        # Create choice for opponent to exile a card
        def handle_exile(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            card_id = selected[0]
            return [Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': card_id,
                    'from_zone_type': ZoneType.HAND,
                    'to_zone_type': ZoneType.EXILE
                },
                source=choice.source_id
            )]

        choice = PendingChoice(
            choice_type="hand_exile",
            player=target_opp,
            prompt="Unscrupulous Agent: Exile a card from your hand",
            options=list(hand_zone.objects),
            source_id=obj.id,
            min_choices=1,
            max_choices=1,
            callback_data={'handler': handle_exile}
        )
        state.pending_choice = choice

        return []
    return [make_etb_trigger(obj, etb_effect)]


def vein_ripper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a creature dies: target opponent loses 2, you gain 2"""
    def death_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        return dying and CardType.CREATURE in dying.characteristics.types

    def death_effect(event: Event, state: GameState) -> list[Event]:
        events = [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
        # Would need opponent targeting
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


def case_of_burning_masks_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: deals 3 damage to target opponent creature"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find opponent's creatures
        legal_targets = []
        for oid, o in state.objects.items():
            if (o.zone == ZoneType.BATTLEFIELD and
                o.controller != obj.controller and
                CardType.CREATURE in o.characteristics.types):
                legal_targets.append(oid)

        if not legal_targets:
            return []

        def handle_damage(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            target_id = selected[0]
            return [Event(
                type=EventType.DAMAGE,
                payload={'target': target_id, 'amount': 3, 'source': choice.source_id, 'is_combat': False},
                source=choice.source_id
            )]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Case of the Burning Masks: Choose an opponent's creature to deal 3 damage"
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_damage

        return []
    return [make_etb_trigger(obj, etb_effect)]


def cornered_crook_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: may sacrifice artifact, then deal 3 damage"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find artifacts to sacrifice
        artifacts = []
        for oid, o in state.objects.items():
            if (o.zone == ZoneType.BATTLEFIELD and
                o.controller == obj.controller and
                CardType.ARTIFACT in o.characteristics.types):
                artifacts.append(oid)

        if not artifacts:
            return []

        # TODO: implement sacrifice choice then damage targeting
        return []
    return [make_etb_trigger(obj, etb_effect)]


def crime_novelist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you sacrifice artifact: +1/+1 counter and add R"""
    def sacrifice_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('cause') != 'sacrifice':
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if not dying or dying.controller != obj.controller:
            return False
        return CardType.ARTIFACT in dying.characteristics.types

    def sacrifice_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.COUNTER_ADDED, payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1}, source=obj.id),
            Event(type=EventType.MANA_ADDED, payload={'player': obj.controller, 'mana': 'R'}, source=obj.id)
        ]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=sacrifice_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=sacrifice_effect(e, s)),
        duration='while_on_battlefield'
    )]


def frantic_scapegoat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: suspect it"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need suspect mechanic
    return [make_etb_trigger(obj, etb_effect)]


def gearbane_orangutan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: destroy artifact OR sacrifice artifact for +1/+1 counters"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need modal choice
    return [make_etb_trigger(obj, etb_effect)]


def harried_dronesmith_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At beginning of combat: create Thopter token with haste"""
    def combat_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.PHASE_START and
                event.payload.get('phase') == 'combat' and
                state.active_player == obj.controller)

    def combat_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Thopter Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.ARTIFACT, CardType.CREATURE],
                'subtypes': ['Thopter'],
                'colors': [],
                'keywords': ['flying', 'haste']
            },
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=combat_effect(e, s)),
        duration='while_on_battlefield'
    )]


def krenkos_buzzcrusher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: destroy nonbasic lands"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need land destruction
    return [make_etb_trigger(obj, etb_effect)]


def person_of_interest_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: suspect self, create Detective token"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Detective Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Detective'],
                'colors': [Color.WHITE, Color.BLUE]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def vengeful_tracker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever opponent sacrifices artifact: deal 2 damage to them"""
    def sacrifice_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('cause') != 'sacrifice':
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if not dying or dying.controller == obj.controller:
            return False
        return CardType.ARTIFACT in dying.characteristics.types

    def sacrifice_effect(event: Event, state: GameState) -> list[Event]:
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if dying:
            return [Event(type=EventType.DAMAGE, payload={'source': obj.id, 'target': dying.controller, 'amount': 2}, source=obj.id)]
        return []

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=sacrifice_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=sacrifice_effect(e, s)),
        duration='while_on_battlefield'
    )]


def aftermath_analyst_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: mill 3"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MILL, payload={'player': obj.controller, 'amount': 3}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


def glint_weaver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: distribute 3 +1/+1 counters, gain life equal to highest toughness"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting + toughness query
    return [make_etb_trigger(obj, etb_effect)]


def loxodon_eavesdropper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: investigate. Draw second card: gets +1/+1 and vigilance."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def rubblebelt_maverick_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: surveil 2"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SURVEIL, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


def agrus_kos_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters or attacks: suspect target or exile if suspected"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting + suspect
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []
    return [make_etb_trigger(obj, etb_effect), make_attack_trigger(obj, attack_effect)]


def alquist_proft_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: investigate"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def blood_spatter_analysis_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: deal 3 damage to target opponent's creature. Creature dies: mill, add counter."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find opponent's creatures
        legal_targets = []
        for oid, o in state.objects.items():
            if (o.zone == ZoneType.BATTLEFIELD and
                o.controller != obj.controller and
                CardType.CREATURE in o.characteristics.types):
                legal_targets.append(oid)

        if not legal_targets:
            return []

        def handle_damage(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            target_id = selected[0]
            return [Event(
                type=EventType.DAMAGE,
                payload={'target': target_id, 'amount': 3, 'source': choice.source_id, 'is_combat': False},
                source=choice.source_id
            )]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Blood Spatter Analysis: Choose an opponent's creature to deal 3 damage"
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_damage

        return []
    return [make_etb_trigger(obj, etb_effect)]


def detectives_satchel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: investigate twice"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.OBJECT_CREATED, payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []}, source=obj.id),
            Event(type=EventType.OBJECT_CREATED, payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]


def ezrim_agency_chief_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: investigate twice"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.OBJECT_CREATED, payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []}, source=obj.id),
            Event(type=EventType.OBJECT_CREATED, payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]


def gadget_technician_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: create Thopter token"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Thopter Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.ARTIFACT, CardType.CREATURE],
                'subtypes': ['Thopter'],
                'colors': [],
                'keywords': ['flying']
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def gleaming_geardrake_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: investigate. Sacrifice artifact: +1/+1 counter."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={'name': 'Clue', 'controller': obj.controller, 'types': [CardType.ARTIFACT], 'subtypes': ['Clue'], 'colors': []},
            source=obj.id
        )]

    def sacrifice_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('cause') != 'sacrifice':
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if not dying or dying.controller != obj.controller:
            return False
        return CardType.ARTIFACT in dying.characteristics.types

    def sacrifice_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1}, source=obj.id)]

    return [
        make_etb_trigger(obj, etb_effect),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=sacrifice_filter,
            handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=sacrifice_effect(e, s)),
            duration='while_on_battlefield'
        )
    ]


def insidious_roots_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creature cards leave graveyard: create Plant token, +1/+1 counters on Plants"""
    def graveyard_leave_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.GRAVEYARD:
            return False
        leaving_id = event.payload.get('object_id')
        leaving = state.objects.get(leaving_id)
        if leaving and leaving.controller == obj.controller:
            return CardType.CREATURE in leaving.characteristics.types
        return False

    def graveyard_leave_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Plant Token',
                'controller': obj.controller,
                'power': 0,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Plant'],
                'colors': [Color.GREEN]
            },
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=graveyard_leave_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=graveyard_leave_effect(e, s)),
        duration='while_on_battlefield'
    )]


def kraul_whipcracker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: destroy target token opponent controls"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find opponent's tokens
        legal_targets = []
        for oid, o in state.objects.items():
            if (o.zone == ZoneType.BATTLEFIELD and
                o.controller != obj.controller and
                getattr(o, 'is_token', False)):
                legal_targets.append(oid)

        if not legal_targets:
            return []

        def handle_destroy(choice, selected: list, gs: GameState) -> list[Event]:
            if not selected:
                return []
            target_id = selected[0]
            return [Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': target_id},
                source=choice.source_id
            )]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Kraul Whipcracker: Choose a token an opponent controls to destroy"
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = handle_destroy

        return []
    return [make_etb_trigger(obj, etb_effect)]


def meddling_youths_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you attack with 3+ creatures: investigate"""
    # Engine emits ATTACK_DECLARED once per attacker. Approximate the "attack with
    # 3+ creatures" trigger by counting attackers this combat and firing on the
    # third attacker declared.
    def reset_filter(event: Event, state: GameState) -> bool:
        return (
            event.type == EventType.PHASE_START
            and event.payload.get("phase") == "combat"
            and state.active_player == obj.controller
        )

    def reset_handler(event: Event, state: GameState) -> InterceptorResult:
        setattr(obj.state, "_attack_count_this_combat", 0)
        return InterceptorResult(action=InterceptorAction.PASS)

    def attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get("attacker_id")
        attacker = state.objects.get(attacker_id) if attacker_id else None
        return bool(attacker and attacker.controller == obj.controller)

    def attack_handler(event: Event, state: GameState) -> InterceptorResult:
        current = int(getattr(obj.state, "_attack_count_this_combat", 0))
        current += 1
        setattr(obj.state, "_attack_count_this_combat", current)

        if current != 3:
            return InterceptorResult(action=InterceptorAction.PASS)

        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Clue',
                    'controller': obj.controller,
                    'types': [CardType.ARTIFACT],
                    'subtypes': ['Clue'],
                    'colors': []
                },
                source=obj.id
            )],
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=reset_filter,
            handler=reset_handler,
            duration='while_on_battlefield',
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=attack_filter,
            handler=attack_handler,
            duration='while_on_battlefield',
        ),
    ]


def shady_informant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies: deals 2 damage to any target"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting
    return [make_death_trigger(obj, death_effect)]


def tolsimir_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: create Voja Fenstalker token"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Voja Fenstalker',
                'controller': obj.controller,
                'power': 5,
                'toughness': 5,
                'types': [CardType.CREATURE],
                'subtypes': ['Wolf'],
                'supertypes': ['Legendary'],
                'colors': [Color.GREEN, Color.WHITE],
                'keywords': ['trample']
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def yarus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other creatures have haste. Face-down deals damage: draw. Face-down dies: return + flip."""
    return [make_keyword_grant(obj, 'haste', lambda o, src: o.controller == src.controller and o.id != src.id)]


def sanitation_automaton_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: surveil 1"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SURVEIL, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


def magnetic_snuffler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters: return Equipment from graveyard. Sacrifice artifact: +1/+1 counter."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need graveyard targeting

    def sacrifice_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('cause') != 'sacrifice':
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if not dying or dying.controller != obj.controller:
            return False
        return CardType.ARTIFACT in dying.characteristics.types

    def sacrifice_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1}, source=obj.id)]

    return [
        make_etb_trigger(obj, etb_effect),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=sacrifice_filter,
            handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=sacrifice_effect(e, s)),
            duration='while_on_battlefield'
        )
    ]


# =============================================================================
# CARD DEFINITIONS
# =============================================================================
# =============================================================================
# TARGETED SPELL RESOLVE FUNCTIONS
# =============================================================================

def _get_spell_and_caster(state: GameState, spell_name: str) -> tuple[str | None, str | None]:
    """Helper to get spell ID and caster from the stack."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == spell_name:
                caster_id = obj.controller
                spell_id = obj.id
                break
    # Fallback to active player
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = f"{spell_name.lower().replace(' ', '_')}_spell"
    return spell_id, caster_id


def _handle_murder_target(choice, selected: list, state: GameState) -> list[Event]:
    """Handle Murder target selection - destroy the creature."""
    if not selected:
        return []
    target_id = selected[0]
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []  # Target no longer valid
    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def murder_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Murder: Destroy target creature.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "Murder")

    # Find all creatures on the battlefield
    legal_targets = []
    for obj_id, obj in state.objects.items():
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types):
            legal_targets.append(obj_id)

    if not legal_targets:
        return []  # No valid targets

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_targets,
        prompt="Murder: Choose a creature to destroy"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _handle_murder_target

    return []


def _handle_shock_target(choice, selected: list, state: GameState) -> list[Event]:
    """Handle Shock target selection - deal 2 damage."""
    if not selected:
        return []
    target_id = selected[0]
    # Check if target is a player or creature/planeswalker
    if target_id in state.players:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 2, 'source': choice.source_id, 'is_combat': False},
            source=choice.source_id
        )]
    target = state.objects.get(target_id)
    if target and target.zone == ZoneType.BATTLEFIELD:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 2, 'source': choice.source_id, 'is_combat': False},
            source=choice.source_id
        )]
    return []


def shock_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Shock: Shock deals 2 damage to any target.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "Shock")

    # Find all valid targets (creatures, planeswalkers, players)
    legal_targets = list(state.players.keys())
    for obj_id, obj in state.objects.items():
        if obj.zone == ZoneType.BATTLEFIELD:
            if (CardType.CREATURE in obj.characteristics.types or
                CardType.PLANESWALKER in obj.characteristics.types):
                legal_targets.append(obj_id)

    if not legal_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_targets,
        prompt="Shock: Choose a target to deal 2 damage"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _handle_shock_target

    return []


def _handle_long_goodbye_target(choice, selected: list, state: GameState) -> list[Event]:
    """Handle Long Goodbye target selection - destroy creature/planeswalker MV <= 3."""
    if not selected:
        return []
    target_id = selected[0]
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def long_goodbye_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Long Goodbye: This spell can't be countered.
    Destroy target creature or planeswalker with mana value 3 or less.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "Long Goodbye")

    # Find creatures and planeswalkers with MV <= 3
    legal_targets = []
    for obj_id, obj in state.objects.items():
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        if not (CardType.CREATURE in obj.characteristics.types or
                CardType.PLANESWALKER in obj.characteristics.types):
            continue
        # Calculate mana value
        mv = obj.characteristics.mana_value if hasattr(obj.characteristics, 'mana_value') else 0
        if mv is None:
            # Parse from mana cost
            mana_cost = obj.characteristics.mana_cost or ""
            mv = 0
            import re
            # Count generic mana
            generic = re.findall(r'\{(\d+)\}', mana_cost)
            mv += sum(int(g) for g in generic)
            # Count colored mana symbols
            colored = re.findall(r'\{[WUBRGC]\}', mana_cost)
            mv += len(colored)
            # Count hybrid mana
            hybrid = re.findall(r'\{[^}]+/[^}]+\}', mana_cost)
            mv += len(hybrid)
        if mv <= 3:
            legal_targets.append(obj_id)

    if not legal_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_targets,
        prompt="Long Goodbye: Choose a creature or planeswalker with mana value 3 or less to destroy"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _handle_long_goodbye_target

    return []


def _handle_assassins_trophy_target(choice, selected: list, state: GameState) -> list[Event]:
    """Handle Assassin's Trophy target selection - destroy permanent, opponent may search for basic."""
    if not selected:
        return []
    target_id = selected[0]
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def assassins_trophy_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Assassin's Trophy: Destroy target permanent an opponent controls.
    Its controller may search their library for a basic land card,
    put it onto the battlefield, then shuffle.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "Assassin's Trophy")

    # Find all permanents opponents control
    legal_targets = []
    for obj_id, obj in state.objects.items():
        if (obj.zone == ZoneType.BATTLEFIELD and
            obj.controller != caster_id):
            legal_targets.append(obj_id)

    if not legal_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_targets,
        prompt="Assassin's Trophy: Choose a permanent an opponent controls to destroy"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _handle_assassins_trophy_target

    return []


def _handle_no_more_lies_target(choice, selected: list, state: GameState) -> list[Event]:
    """Handle No More Lies target selection - counter unless controller pays {3}."""
    if not selected:
        return []
    target_id = selected[0]
    # For now, just counter the spell (simplified - no pay 3 choice)
    return [Event(
        type=EventType.COUNTER,
        payload={'spell_id': target_id, 'exile': True},
        source=choice.source_id
    )]


def no_more_lies_resolve(targets: list, state: GameState) -> list[Event]:
    """
    No More Lies: Counter target spell unless its controller pays {3}.
    If that spell is countered this way, exile it instead of putting it into its owner's graveyard.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "No More Lies")

    # Find all spells on the stack (except this one)
    stack_zone = state.zones.get('stack')
    legal_targets = []
    if stack_zone:
        for obj_id in stack_zone.objects:
            if obj_id != spell_id:
                legal_targets.append(obj_id)

    if not legal_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_targets,
        prompt="No More Lies: Choose a spell to counter (unless controller pays {3})"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _handle_no_more_lies_target

    return []


def _handle_make_your_move_target(choice, selected: list, state: GameState) -> list[Event]:
    """Handle Make Your Move target selection - destroy artifact/enchantment/power 4+ creature."""
    if not selected:
        return []
    target_id = selected[0]
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def make_your_move_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Make Your Move: Destroy target artifact, enchantment, or creature with power 4 or greater.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "Make Your Move")

    # Find legal targets
    legal_targets = []
    for obj_id, obj in state.objects.items():
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        # Artifact or enchantment
        if (CardType.ARTIFACT in obj.characteristics.types or
            CardType.ENCHANTMENT in obj.characteristics.types):
            legal_targets.append(obj_id)
        # Creature with power 4+
        elif CardType.CREATURE in obj.characteristics.types:
            power = get_power(obj, state)
            if power >= 4:
                legal_targets.append(obj_id)

    if not legal_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_targets,
        prompt="Make Your Move: Choose an artifact, enchantment, or creature with power 4+ to destroy"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _handle_make_your_move_target

    return []


def _handle_not_on_my_watch_target(choice, selected: list, state: GameState) -> list[Event]:
    """Handle Not on My Watch target selection - exile attacking creature."""
    if not selected:
        return []
    target_id = selected[0]
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.EXILE
        },
        source=choice.source_id
    )]


def not_on_my_watch_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Not on My Watch: Exile target attacking creature.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "Not on My Watch")

    # Find attacking creatures
    legal_targets = []
    for obj_id, obj in state.objects.items():
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types and
            getattr(obj, 'attacking', False)):
            legal_targets.append(obj_id)

    if not legal_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_targets,
        prompt="Not on My Watch: Choose an attacking creature to exile"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _handle_not_on_my_watch_target

    return []


def _handle_lightning_helix_target(choice, selected: list, state: GameState) -> list[Event]:
    """Handle Lightning Helix target selection - deal 3 damage and gain 3 life."""
    if not selected:
        return []
    target_id = selected[0]
    events = []

    # Deal damage
    if target_id in state.players:
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 3, 'source': choice.source_id, 'is_combat': False},
            source=choice.source_id
        ))
    else:
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': target_id, 'amount': 3, 'source': choice.source_id, 'is_combat': False},
                source=choice.source_id
            ))

    # Gain 3 life (caster gains life)
    events.append(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': choice.player, 'amount': 3},
        source=choice.source_id
    ))

    return events


def lightning_helix_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Lightning Helix: Lightning Helix deals 3 damage to any target and you gain 3 life.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "Lightning Helix")

    # Find all valid targets (creatures, planeswalkers, players)
    legal_targets = list(state.players.keys())
    for obj_id, obj in state.objects.items():
        if obj.zone == ZoneType.BATTLEFIELD:
            if (CardType.CREATURE in obj.characteristics.types or
                CardType.PLANESWALKER in obj.characteristics.types):
                legal_targets.append(obj_id)

    if not legal_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_targets,
        prompt="Lightning Helix: Choose a target to deal 3 damage (and gain 3 life)"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _handle_lightning_helix_target

    return []


def _handle_out_cold_targets(choice, selected: list, state: GameState) -> list[Event]:
    """Handle Out Cold targets - tap up to 2 creatures and add stun counters, investigate."""
    events = []
    for target_id in selected:
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            # Tap the creature
            events.append(Event(
                type=EventType.TAP,
                payload={'object_id': target_id},
                source=choice.source_id
            ))
            # Add stun counter
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': target_id, 'counter_type': 'stun', 'amount': 1},
                source=choice.source_id
            ))

    # Investigate
    events.append(Event(
        type=EventType.OBJECT_CREATED,
        payload={
            'name': 'Clue',
            'controller': choice.player,
            'types': [CardType.ARTIFACT],
            'subtypes': ['Clue'],
            'colors': []
        },
        source=choice.source_id
    ))

    return events


def out_cold_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Out Cold: This spell can't be countered.
    Tap up to two target creatures and put a stun counter on each of them. Investigate.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "Out Cold")

    # Find all creatures on the battlefield
    legal_targets = []
    for obj_id, obj in state.objects.items():
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types):
            legal_targets.append(obj_id)

    if not legal_targets:
        # Still investigate even with no targets
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Clue',
                'controller': caster_id,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Clue'],
                'colors': []
            },
            source=spell_id
        )]

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_targets,
        prompt="Out Cold: Choose up to two creatures to tap and stun",
        min_targets=0,
        max_targets=2
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _handle_out_cold_targets

    return []


def _handle_torch_the_witness_target(choice, selected: list, state: GameState) -> list[Event]:
    """Handle Torch the Witness - deal 2X damage to creature, investigate if excess."""
    if not selected:
        return []
    target_id = selected[0]
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    x_value = choice.callback_data.get('x_value', 0)
    damage = x_value * 2

    events = [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': damage, 'source': choice.source_id, 'is_combat': False},
        source=choice.source_id
    )]

    # Check for excess damage (simplified - investigate if damage > toughness)
    toughness = get_toughness(target, state)
    if damage > toughness:
        events.append(Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Clue',
                'controller': choice.player,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Clue'],
                'colors': []
            },
            source=choice.source_id
        ))

    return events


def torch_the_witness_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Torch the Witness: Torch the Witness deals twice X damage to target creature.
    If excess damage was dealt to that creature this way, investigate.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "Torch the Witness")

    # Find all creatures on the battlefield
    legal_targets = []
    for obj_id, obj in state.objects.items():
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types):
            legal_targets.append(obj_id)

    if not legal_targets:
        return []

    # Get X value from the spell (simplified - assume X=2 for now, would need mana payment tracking)
    x_value = 2  # Placeholder

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_targets,
        prompt=f"Torch the Witness: Choose a creature to deal {x_value * 2} damage"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _handle_torch_the_witness_target
    choice.callback_data['x_value'] = x_value

    return []


def _handle_suspicious_detonation_target(choice, selected: list, state: GameState) -> list[Event]:
    """Handle Suspicious Detonation - deal 4 damage to creature."""
    if not selected:
        return []
    target_id = selected[0]
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': 4, 'source': choice.source_id, 'is_combat': False},
        source=choice.source_id
    )]


def suspicious_detonation_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Suspicious Detonation: This spell costs {3} less to cast if you've sacrificed an artifact this turn.
    This spell can't be countered. Suspicious Detonation deals 4 damage to target creature.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "Suspicious Detonation")

    # Find all creatures
    legal_targets = []
    for obj_id, obj in state.objects.items():
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types):
            legal_targets.append(obj_id)

    if not legal_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_targets,
        prompt="Suspicious Detonation: Choose a creature to deal 4 damage"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _handle_suspicious_detonation_target

    return []


def _handle_slice_from_shadows_target(choice, selected: list, state: GameState) -> list[Event]:
    """Handle Slice from the Shadows - target creature gets -X/-X."""
    if not selected:
        return []
    target_id = selected[0]
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    x_value = choice.callback_data.get('x_value', 2)
    return [Event(
        type=EventType.PT_MODIFY,
        payload={'object_id': target_id, 'power': -x_value, 'toughness': -x_value, 'until': 'end_of_turn'},
        source=choice.source_id
    )]


def slice_from_the_shadows_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Slice from the Shadows: This spell can't be countered.
    Target creature gets -X/-X until end of turn.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "Slice from the Shadows")

    # Find all creatures
    legal_targets = []
    for obj_id, obj in state.objects.items():
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types):
            legal_targets.append(obj_id)

    if not legal_targets:
        return []

    x_value = 2  # Placeholder

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_targets,
        prompt=f"Slice from the Shadows: Choose a creature to get -{x_value}/-{x_value}"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _handle_slice_from_shadows_target
    choice.callback_data['x_value'] = x_value

    return []


def _handle_deadly_complication_mode(choice, selected: list, state: GameState) -> list[Event]:
    """Execute the chosen mode(s) for Deadly Complication."""
    if not selected:
        return []

    events = []
    # Modal selections can come through as either:
    # - dicts: {"index": int, "text": str}
    # - raw ints: index
    mode_indices = []
    for m in selected:
        if isinstance(m, dict):
            idx = m.get("index")
        else:
            idx = m
        try:
            mode_indices.append(int(idx))
        except Exception:
            continue

    spell_id = choice.source_id
    caster_id = choice.player

    # Mode 0: Destroy target creature
    if 0 in mode_indices:
        legal_creatures = []
        for obj_id, obj in state.objects.items():
            if (obj.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in obj.characteristics.types):
                legal_creatures.append(obj_id)

        if legal_creatures:
            destroy_choice = create_target_choice(
                state=state,
                player_id=caster_id,
                source_id=spell_id,
                legal_targets=legal_creatures,
                prompt="Deadly Complication: Choose a creature to destroy"
            )
            destroy_choice.choice_type = "target_with_callback"
            destroy_choice.callback_data['handler'] = lambda c, s, gs: [Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': s[0] if s else None},
                source=c.source_id
            )] if s else []

    # Mode 1 would need suspected creature tracking - simplified

    return events


def deadly_complication_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Deadly Complication: Choose one or both -
    - Destroy target creature.
    - Put a +1/+1 counter on target suspected creature you control.
      You may have it become no longer suspected.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "Deadly Complication")

    # Create modal choice
    modes = [
        {"index": 0, "text": "Destroy target creature."},
        {"index": 1, "text": "Put a +1/+1 counter on target suspected creature you control."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        min_modes=1,
        max_modes=2,
        prompt="Deadly Complication - Choose one or both:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _handle_deadly_complication_mode

    return []


def _handle_soul_search_target(choice, selected: list, state: GameState) -> list[Event]:
    """Handle Soul Search - exile chosen nonland card, maybe create Spirit."""
    if not selected:
        return []
    card_id = selected[0]
    card = state.objects.get(card_id)
    if not card:
        return []

    events = [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': card_id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.EXILE
        },
        source=choice.source_id
    )]

    # Check mana value for Spirit token
    mv = 0
    mana_cost = card.characteristics.mana_cost or ""
    import re
    generic = re.findall(r'\{(\d+)\}', mana_cost)
    mv += sum(int(g) for g in generic)
    colored = re.findall(r'\{[WUBRGC]\}', mana_cost)
    mv += len(colored)
    hybrid = re.findall(r'\{[^}]+/[^}]+\}', mana_cost)
    mv += len(hybrid)

    if mv <= 1:
        events.append(Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Spirit Token',
                'controller': choice.player,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Spirit'],
                'colors': [Color.WHITE, Color.BLACK],
                'keywords': ['flying']
            },
            source=choice.source_id
        ))

    return events


def soul_search_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Soul Search: Target opponent reveals their hand. You choose a nonland card from it.
    Exile that card. If the card's mana value is 1 or less,
    create a 1/1 white and black Spirit creature token with flying.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "Soul Search")

    # Find opponents
    opponents = [p_id for p_id in state.players.keys() if p_id != caster_id]
    if not opponents:
        return []

    # For simplicity, target first opponent (would need targeting for multiple opponents)
    target_opponent = opponents[0]

    def nonland_filter(card: GameObject) -> bool:
        return CardType.LAND not in card.characteristics.types

    choice = create_hand_reveal_choice(
        state=state,
        choosing_player_id=caster_id,
        source_id=spell_id,
        target_player_id=target_opponent,
        card_filter=nonland_filter,
        min_choices=1,
        max_choices=1,
        prompt="Soul Search: Choose a nonland card to exile"
    )
    if choice:
        choice.choice_type = "hand_reveal_with_callback"
        choice.callback_data['handler'] = _handle_soul_search_target

    return []


def _handle_toxin_analysis_target(choice, selected: list, state: GameState) -> list[Event]:
    """Handle Toxin Analysis - give creature deathtouch and lifelink, investigate."""
    if not selected:
        return []
    target_id = selected[0]
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(
            type=EventType.KEYWORD_GRANT,
            payload={'object_id': target_id, 'keywords': ['deathtouch', 'lifelink'], 'until': 'end_of_turn'},
            source=choice.source_id
        ),
        Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Clue',
                'controller': choice.player,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Clue'],
                'colors': []
            },
            source=choice.source_id
        )
    ]


def toxin_analysis_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Toxin Analysis: Target creature gains deathtouch and lifelink until end of turn. Investigate.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "Toxin Analysis")

    # Find all creatures
    legal_targets = []
    for obj_id, obj in state.objects.items():
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types):
            legal_targets.append(obj_id)

    if not legal_targets:
        # Still investigate
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Clue',
                'controller': caster_id,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Clue'],
                'colors': []
            },
            source=spell_id
        )]

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_targets,
        prompt="Toxin Analysis: Choose a creature to gain deathtouch and lifelink"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _handle_toxin_analysis_target

    return []


def _handle_presumed_dead_target(choice, selected: list, state: GameState) -> list[Event]:
    """Handle Presumed Dead - creature gets +2/+0 and death return ability."""
    if not selected:
        return []
    target_id = selected[0]
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.PT_MODIFY,
        payload={'object_id': target_id, 'power': 2, 'toughness': 0, 'until': 'end_of_turn'},
        source=choice.source_id
    )]


def presumed_dead_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Presumed Dead: Until end of turn, target creature gets +2/+0 and gains
    "When this creature dies, return it to the battlefield under its owner's control and suspect it."
    """
    spell_id, caster_id = _get_spell_and_caster(state, "Presumed Dead")

    # Find all creatures
    legal_targets = []
    for obj_id, obj in state.objects.items():
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types):
            legal_targets.append(obj_id)

    if not legal_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_targets,
        prompt="Presumed Dead: Choose a creature to get +2/+0 and death trigger"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _handle_presumed_dead_target

    return []


def _handle_caught_redhanded_target(choice, selected: list, state: GameState) -> list[Event]:
    """Handle Caught Red-Handed - gain control, untap, haste, suspect."""
    if not selected:
        return []
    target_id = selected[0]
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(
            type=EventType.CONTROL_CHANGE,
            payload={'object_id': target_id, 'new_controller': choice.player, 'until': 'end_of_turn'},
            source=choice.source_id
        ),
        Event(
            type=EventType.UNTAP,
            payload={'object_id': target_id},
            source=choice.source_id
        ),
        Event(
            type=EventType.KEYWORD_GRANT,
            payload={'object_id': target_id, 'keywords': ['haste'], 'until': 'end_of_turn'},
            source=choice.source_id
        )
    ]


def caught_redhanded_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Caught Red-Handed: This spell can't be countered.
    Gain control of target creature until end of turn. Untap that creature.
    It gains haste until end of turn. Suspect it.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "Caught Red-Handed")

    # Find all creatures
    legal_targets = []
    for obj_id, obj in state.objects.items():
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types):
            legal_targets.append(obj_id)

    if not legal_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_targets,
        prompt="Caught Red-Handed: Choose a creature to gain control of"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _handle_caught_redhanded_target

    return []


def _handle_chase_is_on_target(choice, selected: list, state: GameState) -> list[Event]:
    """Handle The Chase Is On - +3/+0, first strike, investigate."""
    if not selected:
        return []
    target_id = selected[0]
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(
            type=EventType.PT_MODIFY,
            payload={'object_id': target_id, 'power': 3, 'toughness': 0, 'until': 'end_of_turn'},
            source=choice.source_id
        ),
        Event(
            type=EventType.KEYWORD_GRANT,
            payload={'object_id': target_id, 'keywords': ['first strike'], 'until': 'end_of_turn'},
            source=choice.source_id
        ),
        Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Clue',
                'controller': choice.player,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Clue'],
                'colors': []
            },
            source=choice.source_id
        )
    ]


def chase_is_on_resolve(targets: list, state: GameState) -> list[Event]:
    """
    The Chase Is On: Target creature gets +3/+0 and gains first strike until end of turn. Investigate.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "The Chase Is On")

    # Find all creatures
    legal_targets = []
    for obj_id, obj in state.objects.items():
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types):
            legal_targets.append(obj_id)

    if not legal_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_targets,
        prompt="The Chase Is On: Choose a creature to get +3/+0 and first strike"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _handle_chase_is_on_target

    return []


def no_witnesses_resolve(targets: list, state: GameState) -> list[Event]:
    """
    No Witnesses: Each player who controls the most creatures investigates.
    Then destroy all creatures.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "No Witnesses")

    # Count creatures per player
    creature_counts = {}
    for obj_id, obj in state.objects.items():
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types):
            creature_counts[obj.controller] = creature_counts.get(obj.controller, 0) + 1

    events = []

    if creature_counts:
        max_creatures = max(creature_counts.values())
        # Players with most creatures investigate
        for player_id, count in creature_counts.items():
            if count == max_creatures:
                events.append(Event(
                    type=EventType.OBJECT_CREATED,
                    payload={
                        'name': 'Clue',
                        'controller': player_id,
                        'types': [CardType.ARTIFACT],
                        'subtypes': ['Clue'],
                        'colors': []
                    },
                    source=spell_id
                ))

    # Destroy all creatures
    for obj_id, obj in state.objects.items():
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types):
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': obj_id},
                source=spell_id
            ))

    return events


def deduce_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Deduce: Draw a card. Investigate.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "Deduce")

    return [
        Event(
            type=EventType.DRAW,
            payload={'player': caster_id, 'amount': 1},
            source=spell_id
        ),
        Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Clue',
                'controller': caster_id,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Clue'],
                'colors': []
            },
            source=spell_id
        )
    ]


def _handle_fanatical_strength_target(choice, selected: list, state: GameState) -> list[Event]:
    """Handle Fanatical Strength - +3/+3 and trample."""
    if not selected:
        return []
    target_id = selected[0]
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(
            type=EventType.PT_MODIFY,
            payload={'object_id': target_id, 'power': 3, 'toughness': 3, 'until': 'end_of_turn'},
            source=choice.source_id
        ),
        Event(
            type=EventType.KEYWORD_GRANT,
            payload={'object_id': target_id, 'keywords': ['trample'], 'until': 'end_of_turn'},
            source=choice.source_id
        )
    ]


def fanatical_strength_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Fanatical Strength: Target creature gets +3/+3 and gains trample until end of turn.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "Fanatical Strength")

    # Find all creatures
    legal_targets = []
    for obj_id, obj in state.objects.items():
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types):
            legal_targets.append(obj_id)

    if not legal_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_targets,
        prompt="Fanatical Strength: Choose a creature to get +3/+3 and trample"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _handle_fanatical_strength_target

    return []


def _handle_reasonable_doubt_target(choice, selected: list, state: GameState) -> list[Event]:
    """Handle Reasonable Doubt - counter spell unless pay 2, suspect creature."""
    events = []
    spell_target = choice.callback_data.get('spell_target')
    creature_target = choice.callback_data.get('creature_target')

    if spell_target:
        events.append(Event(
            type=EventType.COUNTER,
            payload={'spell_id': spell_target, 'unless_pay': 2},
            source=choice.source_id
        ))

    return events


def reasonable_doubt_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Reasonable Doubt: Counter target spell unless its controller pays {2}.
    Suspect up to one target creature.
    """
    spell_id, caster_id = _get_spell_and_caster(state, "Reasonable Doubt")

    # Find spells on stack
    stack_zone = state.zones.get('stack')
    legal_spells = []
    if stack_zone:
        for obj_id in stack_zone.objects:
            if obj_id != spell_id:
                legal_spells.append(obj_id)

    if not legal_spells:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=legal_spells,
        prompt="Reasonable Doubt: Choose a spell to counter (unless controller pays {2})"
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _handle_reasonable_doubt_target

    return []



CASE_OF_THE_SHATTERED_PACT = make_enchantment(
    name="Case of the Shattered Pact",
    mana_cost="{2}",
    colors=set(),
    text="When this Case enters, search your library for a basic land card, reveal it, put it into your hand, then shuffle.\nTo solve — There are five colors among permanents you control. (If unsolved, solve at the beginning of your end step.)\nSolved — At the beginning of combat on your turn, target creature you control gains flying, double strike, and vigilance until end of turn.",
    subtypes={"Case"},
)

ABSOLVING_LAMMASU = make_creature(
    name="Absolving Lammasu",
    power=4, toughness=3,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Lammasu"},
    text="Flying\nWhen this creature enters, all suspected creatures are no longer suspected.\nWhen this creature dies, you gain 3 life and suspect up to one target creature an opponent controls. (A suspected creature has menace and can't block.)",
    setup_interceptors=absolving_lammasu_setup
)

ASSEMBLE_THE_PLAYERS = make_enchantment(
    name="Assemble the Players",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="You may look at the top card of your library any time.\nOnce each turn, you may cast a creature spell with power 2 or less from the top of your library.",
)

AURELIAS_VINDICATOR = make_creature(
    name="Aurelia's Vindicator",
    power=4, toughness=2,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying, lifelink, ward {2}\nDisguise {X}{3}{W}\nWhen this creature is turned face up, exile up to X other target creatures from the battlefield and/or creature cards from graveyards.\nWhen this creature leaves the battlefield, return the exiled cards to their owners' hands.",
)

AUSPICIOUS_ARRIVAL = make_instant(
    name="Auspicious Arrival",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 until end of turn. Investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

CALL_A_SURPRISE_WITNESS = make_sorcery(
    name="Call a Surprise Witness",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Return target creature card with mana value 3 or less from your graveyard to the battlefield. Put a flying counter on it. It's a Spirit in addition to its other types.",
)

CASE_FILE_AUDITOR = make_creature(
    name="Case File Auditor",
    power=1, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Detective", "Human"},
    text="When this creature enters and whenever you solve a Case, look at the top six cards of your library. You may reveal an enchantment card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.\nYou may spend mana as though it were mana of any color to cast Case spells.",
    setup_interceptors=case_file_auditor_setup
)

CASE_OF_THE_GATEWAY_EXPRESS = make_enchantment(
    name="Case of the Gateway Express",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="When this Case enters, choose target creature you don't control. Each creature you control deals 1 damage to that creature.\nTo solve — Three or more creatures attacked this turn. (If unsolved, solve at the beginning of your end step.)\nSolved — Creatures you control get +1/+0.",
    subtypes={"Case"},
)

CASE_OF_THE_PILFERED_PROOF = make_enchantment(
    name="Case of the Pilfered Proof",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Whenever a Detective you control enters or is turned face up, put a +1/+1 counter on it.\nTo solve — You control three or more Detectives. (If unsolved, solve at the beginning of your end step.)\nSolved — If one or more tokens would be created under your control, those tokens plus a Clue token are created instead. (It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    subtypes={"Case"},
)

CASE_OF_THE_UNEATEN_FEAST = make_enchantment(
    name="Case of the Uneaten Feast",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Whenever a creature you control enters, you gain 1 life.\nTo solve — You've gained 5 or more life this turn. (If unsolved, solve at the beginning of your end step.)\nSolved — Sacrifice this Case: Creature cards in your graveyard gain \"You may cast this card from your graveyard\" until end of turn.",
    subtypes={"Case"},
    setup_interceptors=case_of_uneaten_feast_setup
)

DEFENESTRATED_PHANTOM = make_creature(
    name="Defenestrated Phantom",
    power=4, toughness=3,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
    text="Flying\nDisguise {4}{W} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

DELNEY_STREETWISE_LOOKOUT = make_creature(
    name="Delney, Streetwise Lookout",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    supertypes={"Legendary"},
    text="Creatures you control with power 2 or less can't be blocked by creatures with power 3 or greater.\nIf an ability of a creature you control with power 2 or less triggers, that ability triggers an additional time.",
)

DOORKEEPER_THRULL = make_creature(
    name="Doorkeeper Thrull",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Thrull"},
    text="Flash\nFlying\nArtifacts and creatures entering don't cause abilities to trigger.",
)

DUE_DILIGENCE = make_enchantment(
    name="Due Diligence",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Enchant creature\nWhen this Aura enters, target creature you control other than enchanted creature gets +2/+2 and gains vigilance until end of turn.\nEnchanted creature gets +2/+2 and has vigilance.",
    subtypes={"Aura"},
)

ESSENCE_OF_ANTIQUITY = make_artifact_creature(
    name="Essence of Antiquity",
    power=1, toughness=10,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Golem"},
    text="Disguise {2}{W} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, creatures you control gain hexproof until end of turn. Untap them.",
)

FORUM_FAMILIAR = make_creature(
    name="Forum Familiar",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Cat"},
    text="Disguise {1}{W} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, return another target permanent you control to its owner's hand and put a +1/+1 counter on this creature.",
)

GRIFFNAUT_TRACKER = make_creature(
    name="Griffnaut Tracker",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Detective", "Human"},
    text="Flying\nWhen this creature enters, exile up to two target cards from a single graveyard.",
    setup_interceptors=griffnaut_tracker_setup
)

HAAZDA_VIGILANTE = make_creature(
    name="Haazda Vigilante",
    power=4, toughness=4,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Giant", "Soldier"},
    text="Whenever this creature enters or attacks, put a +1/+1 counter on target creature you control with power 2 or less.",
    setup_interceptors=haazda_vigilante_setup
)

INSIDE_SOURCE = make_creature(
    name="Inside Source",
    power=1, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Citizen", "Human"},
    text="When this creature enters, create a 2/2 white and blue Detective creature token.\n{3}, {T}: Target Detective you control gets +2/+0 and gains vigilance until end of turn. Activate only as a sorcery.",
    setup_interceptors=inside_source_setup
)

KARLOV_WATCHDOG = make_creature(
    name="Karlov Watchdog",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Dog"},
    text="Vigilance\nPermanents your opponents control can't be turned face up during your turn.\nWhenever you attack with three or more creatures, creatures you control get +1/+1 until end of turn.",
)

KROVOD_HAUNCH = make_artifact(
    name="Krovod Haunch",
    mana_cost="{W}",
    text="Equipped creature gets +2/+0.\n{2}, {T}, Sacrifice this Equipment: You gain 3 life.\nWhen this Equipment is put into a graveyard from the battlefield, you may pay {1}{W}. If you do, create two 1/1 white Dog creature tokens.\nEquip {2}",
    subtypes={"Equipment", "Food"},
)

MAKE_YOUR_MOVE = make_instant(
    name="Make Your Move",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Destroy target artifact, enchantment, or creature with power 4 or greater.",
    # resolve=make_your_move_resolve,  # TODO: function defined later in file
)

MAKESHIFT_BINDING = make_enchantment(
    name="Makeshift Binding",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, exile target creature an opponent controls until this enchantment leaves the battlefield. You gain 2 life.",
)

MARKETWATCH_PHANTOM = make_creature(
    name="Marketwatch Phantom",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Detective", "Spirit"},
    text="Whenever another creature you control with power 2 or less enters, this creature gains flying until end of turn.",
    setup_interceptors=marketwatch_phantom_setup
)

MUSEUM_NIGHTWATCH = make_creature(
    name="Museum Nightwatch",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Centaur", "Soldier"},
    text="When this creature dies, create a 2/2 white and blue Detective creature token.\nDisguise {1}{W} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
    setup_interceptors=museum_nightwatch_setup
)

NEIGHBORHOOD_GUARDIAN = make_creature(
    name="Neighborhood Guardian",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Unicorn"},
    text="Whenever another creature you control with power 2 or less enters, target creature you control gets +1/+1 until end of turn.",
    setup_interceptors=neighborhood_guardian_setup
)

NO_WITNESSES = make_sorcery(
    name="No Witnesses",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Each player who controls the most creatures investigates. Then destroy all creatures. (To investigate, create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    resolve=no_witnesses_resolve,
)

NOT_ON_MY_WATCH = make_instant(
    name="Not on My Watch",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Exile target attacking creature.",
    resolve=not_on_my_watch_resolve,
)

NOVICE_INSPECTOR = make_creature(
    name="Novice Inspector",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Detective", "Human"},
    text="When this creature enters, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    setup_interceptors=novice_inspector_setup
)

ON_THE_JOB = make_instant(
    name="On the Job",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +2/+1 until end of turn. Investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

PERIMETER_ENFORCER = make_creature(
    name="Perimeter Enforcer",
    power=1, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Detective", "Human"},
    text="Flying, lifelink\nWhenever another Detective you control enters and whenever a Detective you control is turned face up, this creature gets +1/+1 until end of turn.",
    setup_interceptors=perimeter_enforcer_setup
)

SANCTUARY_WALL = make_artifact_creature(
    name="Sanctuary Wall",
    power=0, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Wall"},
    text="Defender\n{2}{W}, {T}: Tap target creature. You may put a stun counter on it. If you do, put a stun counter on this creature. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

SEASONED_CONSULTANT = make_creature(
    name="Seasoned Consultant",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Detective", "Human"},
    text="Whenever you attack with three or more creatures, this creature gets +2/+0 until end of turn.",
)

TENTH_DISTRICT_HERO = make_creature(
    name="Tenth District Hero",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human"},
    text="{1}{W}, Collect evidence 2: This creature becomes a Human Detective with base power and toughness 4/4 and gains vigilance.\n{2}{W}, Collect evidence 4: If this creature is a Detective, it becomes a legendary creature named Mileva, the Stalwart, it has base power and toughness 5/5, and it gains \"Other creatures you control have indestructible.\"",
)

UNYIELDING_GATEKEEPER = make_creature(
    name="Unyielding Gatekeeper",
    power=3, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Elephant"},
    text="Disguise {1}{W} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, exile another target nonland permanent. If you controlled it, return it to the battlefield tapped. Otherwise, its controller creates a 2/2 white and blue Detective creature token.",
)

WOJEK_INVESTIGATOR = make_creature(
    name="Wojek Investigator",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Angel", "Detective"},
    text="Flying, vigilance\nAt the beginning of your upkeep, investigate once for each opponent who has more cards in hand than you. (To investigate, create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    setup_interceptors=wojek_investigator_setup
)

WRENCH = make_artifact(
    name="Wrench",
    mana_cost="{W}",
    text="Equipped creature gets +1/+1 and has vigilance and \"{3}, {T}: Tap target creature.\"\n{2}, Sacrifice this Equipment: Draw a card.\nEquip {2}",
    subtypes={"Clue", "Equipment"},
)

AGENCY_OUTFITTER = make_creature(
    name="Agency Outfitter",
    power=4, toughness=3,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Sphinx"},
    text="Flying\nWhen this creature enters, you may search your graveyard, hand and/or library for a card named Magnifying Glass and/or a card named Thinking Cap and put them onto the battlefield. If you search your library this way, shuffle.",
    setup_interceptors=agency_outfitter_setup
)

BEHIND_THE_MASK = make_instant(
    name="Behind the Mask",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="As an additional cost to cast this spell, you may collect evidence 6. (Exile cards with total mana value 6 or greater from your graveyard.)\nUntil end of turn, target artifact or creature becomes an artifact creature with base power and toughness 4/3. If evidence was collected, it has base power and toughness 1/1 until end of turn instead.",
)

BENTHIC_CRIMINOLOGISTS = make_creature(
    name="Benthic Criminologists",
    power=4, toughness=5,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="Whenever this creature enters or attacks, you may sacrifice an artifact. If you do, draw a card.",
    setup_interceptors=benthic_criminologists_setup
)

BUBBLE_SMUGGLER = make_creature(
    name="Bubble Smuggler",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Fish", "Octopus"},
    text="Disguise {5}{U} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nAs this creature is turned face up, put four +1/+1 counters on it.",
)

BURDEN_OF_PROOF = make_enchantment(
    name="Burden of Proof",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Flash\nEnchant creature\nEnchanted creature gets +2/+2 as long as it's a Detective you control. Otherwise, it has base power and toughness 1/1 and can't block Detectives.",
    subtypes={"Aura"},
)

CANDLESTICK = make_artifact(
    name="Candlestick",
    mana_cost="{U}",
    text="Equipped creature gets +1/+1 and has \"Whenever this creature attacks, surveil 2.\" (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\n{2}, Sacrifice this Equipment: Draw a card.\nEquip {2}",
    subtypes={"Clue", "Equipment"},
)

CASE_OF_THE_FILCHED_FALCON = make_enchantment(
    name="Case of the Filched Falcon",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="When this Case enters, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nTo solve — You control three or more artifacts. (If unsolved, solve at the beginning of your end step.)\nSolved — {2}{U}, Sacrifice this Case: Put four +1/+1 counters on target noncreature artifact. It becomes a 0/0 Bird creature with flying in addition to its other types.",
    subtypes={"Case"},
    setup_interceptors=case_of_filched_falcon_setup
)

CASE_OF_THE_RANSACKED_LAB = make_enchantment(
    name="Case of the Ransacked Lab",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Instant and sorcery spells you cast cost {1} less to cast.\nTo solve — You've cast four or more instant and sorcery spells this turn. (If unsolved, solve at the beginning of your end step.)\nSolved — Whenever you cast an instant or sorcery spell, draw a card.",
    subtypes={"Case"},
)

COLD_CASE_CRACKER = make_creature(
    name="Cold Case Cracker",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Spirit"},
    text="Flying\nWhen this creature dies, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    setup_interceptors=cold_case_cracker_setup
)

CONSPIRACY_UNRAVELER = make_creature(
    name="Conspiracy Unraveler",
    power=6, toughness=6,
    mana_cost="{5}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Sphinx"},
    text="Flying\nYou may collect evidence 10 rather than pay the mana cost for spells you cast. (To collect evidence 10, exile cards with total mana value 10 or greater from your graveyard.)",
)

COVETED_FALCON = make_artifact_creature(
    name="Coveted Falcon",
    power=1, toughness=4,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Bird"},
    text="Flying\nWhenever this creature attacks, gain control of target permanent you own but don't control.\nDisguise {1}{U}\nWhen this creature is turned face up, target opponent gains control of any number of target permanents you control. Draw a card for each one they gained control of this way.",
)

CRIMESTOPPER_SPRITE = make_creature(
    name="Crimestopper Sprite",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Faerie"},
    text="As an additional cost to cast this spell, you may collect evidence 6. (Exile cards with total mana value 6 or greater from your graveyard.)\nFlying\nWhen this creature enters, tap target creature. If evidence was collected, put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

CRYPTIC_COAT = make_artifact(
    name="Cryptic Coat",
    mana_cost="{2}{U}",
    text="When this Equipment enters, cloak the top card of your library, then attach this Equipment to it. (To cloak a card, put it onto the battlefield face down as a 2/2 creature with ward {2}. Turn it face up any time for its mana cost if it's a creature card.)\nEquipped creature gets +1/+0 and can't be blocked.\n{1}{U}: Return this Equipment to its owner's hand.",
    subtypes={"Equipment"},
)

CURIOUS_INQUIRY = make_enchantment(
    name="Curious Inquiry",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Enchant creature\nEnchanted creature gets +1/+1 and has \"Whenever this creature deals combat damage to a player, investigate.\" (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    subtypes={"Aura"},
)

DEDUCE = make_instant(
    name="Deduce",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Draw a card. Investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    resolve=deduce_resolve,
)

DRAMATIC_ACCUSATION = make_enchantment(
    name="Dramatic Accusation",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Enchant creature\nWhen this Aura enters, tap enchanted creature.\nEnchanted creature doesn't untap during its controller's untap step.\n{U}{U}: Shuffle enchanted creature into its owner's library.",
    subtypes={"Aura"},
)

ELIMINATE_THE_IMPOSSIBLE = make_instant(
    name="Eliminate the Impossible",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Investigate. Creatures your opponents control get -2/-0 until end of turn. If any of them are suspected, they're no longer suspected. (To investigate, create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

EXIT_SPECIALIST = make_creature(
    name="Exit Specialist",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Human"},
    text="This creature can't be blocked by creatures with power 3 or greater.\nDisguise {1}{U} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, return another target creature to its owner's hand.",
)

FAE_FLIGHT = make_enchantment(
    name="Fae Flight",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Flash\nEnchant creature\nWhen this Aura enters, enchanted creature gains hexproof until end of turn.\nEnchanted creature gets +1/+0 and has flying.",
    subtypes={"Aura"},
)

FORENSIC_GADGETEER = make_creature(
    name="Forensic Gadgeteer",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Artificer", "Detective", "Vedalken"},
    text="Whenever you cast an artifact spell, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nActivated abilities of artifacts you control cost {1} less to activate. This effect can't reduce the mana in that cost to less than one mana.",
    setup_interceptors=forensic_gadgeteer_setup
)

FORENSIC_RESEARCHER = make_creature(
    name="Forensic Researcher",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Merfolk"},
    text="{T}: Untap another target permanent you control.\n{T}, Collect evidence 3: Tap target creature you don't control. (To collect evidence 3, exile cards with total mana value 3 or greater from your graveyard.)",
)

FURTIVE_COURIER = make_creature(
    name="Furtive Courier",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Advisor", "Merfolk"},
    text="This creature can't be blocked as long as you've sacrificed an artifact this turn.\nWhenever this creature attacks, draw a card, then discard a card.",
    setup_interceptors=furtive_courier_setup
)

HOTSHOT_INVESTIGATORS = make_creature(
    name="Hotshot Investigators",
    power=4, toughness=4,
    mana_cost="{5}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Vedalken"},
    text="When this creature enters, return up to one other target creature to its owner's hand. If you controlled it, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    setup_interceptors=hotshot_investigators_setup
)

INTRUDE_ON_THE_MIND = make_instant(
    name="Intrude on the Mind",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Reveal the top five cards of your library and separate them into two piles. An opponent chooses one of those piles. Put that pile into your hand and the other into your graveyard. Create a 0/0 colorless Thopter artifact creature token with flying, then put a +1/+1 counter on it for each card put into your graveyard this way.",
)

JADED_ANALYST = make_creature(
    name="Jaded Analyst",
    power=3, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Human"},
    text="Defender\nWhenever you draw your second card each turn, this creature loses defender and gains vigilance until end of turn.",
)

LIVING_CONUNDRUM = make_creature(
    name="Living Conundrum",
    power=2, toughness=5,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="Hexproof\nIf you would draw a card while your library has no cards in it, skip that draw instead.\nAs long as there are no cards in your library, this creature has base power and toughness 10/10 and has flying and vigilance.",
)

LOST_IN_THE_MAZE = make_enchantment(
    name="Lost in the Maze",
    mana_cost="{X}{U}{U}",
    colors={Color.BLUE},
    text="Flash\nWhen this enchantment enters, tap X target creatures. Put a stun counter on each of those creatures you don't control. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nTapped creatures you control have hexproof.",
)

MISTWAY_SPY = make_creature(
    name="Mistway Spy",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Merfolk"},
    text="Flying\nDisguise {1}{U} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, until end of turn, whenever a creature you control deals combat damage to a player, investigate.",
)

OUT_COLD = make_instant(
    name="Out Cold",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="This spell can't be countered. (This includes by the ward ability.)\nTap up to two target creatures and put a stun counter on each of them. Investigate. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
    resolve=out_cold_resolve,
)

PROFTS_EIDETIC_MEMORY = make_enchantment(
    name="Proft's Eidetic Memory",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="When Proft's Eidetic Memory enters, draw a card.\nYou have no maximum hand size.\nAt the beginning of combat on your turn, if you've drawn more than one card this turn, put X +1/+1 counters on target creature you control, where X is the number of cards you've drawn this turn minus one.",
    supertypes={"Legendary"},
)

PROJEKTOR_INSPECTOR = make_creature(
    name="Projektor Inspector",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Human"},
    text="Whenever this creature or another Detective you control enters and whenever a Detective you control is turned face up, you may draw a card. If you do, discard a card.",
    setup_interceptors=projektor_inspector_setup
)

REASONABLE_DOUBT = make_instant(
    name="Reasonable Doubt",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {2}.\nSuspect up to one target creature. (A suspected creature has menace and can't block.)",
    resolve=reasonable_doubt_resolve,
)

REENACT_THE_CRIME = make_instant(
    name="Reenact the Crime",
    mana_cost="{1}{U}{U}{U}",
    colors={Color.BLUE},
    text="Exile target nonland card in a graveyard that was put there from anywhere this turn. Copy it. You may cast the copy without paying its mana cost.",
)

STEAMCORE_SCHOLAR = make_creature(
    name="Steamcore Scholar",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Weird"},
    text="Flying, vigilance\nWhen this creature enters, draw two cards. Then discard two cards unless you discard an instant or sorcery card or a creature card with flying.",
    setup_interceptors=steamcore_scholar_setup
)

SUDDEN_SETBACK = make_instant(
    name="Sudden Setback",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="The owner of target spell or nonland permanent puts it on their choice of the top or bottom of their library.",
)

SURVEILLANCE_MONITOR = make_creature(
    name="Surveillance Monitor",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Detective", "Vedalken"},
    text="When this creature enters, you may collect evidence 4. (Exile cards with total mana value 4 or greater from your graveyard.)\nWhenever you collect evidence, create a 1/1 colorless Thopter artifact creature token with flying.",
    setup_interceptors=surveillance_monitor_setup
)

UNAUTHORIZED_EXIT = make_instant(
    name="Unauthorized Exit",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target nonland permanent to its owner's hand. Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

AGENCY_CORONER = make_creature(
    name="Agency Coroner",
    power=3, toughness=6,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Ogre"},
    text="{2}{B}, Sacrifice another creature: Draw a card. If the sacrificed creature was suspected, draw two cards instead.",
)

ALLEY_ASSAILANT = make_creature(
    name="Alley Assailant",
    power=3, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Vampire"},
    text="This creature enters tapped.\nDisguise {4}{B}{B} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, target opponent loses 3 life and you gain 3 life.",
)

BARBED_SERVITOR = make_artifact_creature(
    name="Barbed Servitor",
    power=1, toughness=1,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Construct"},
    text="Indestructible\nWhen this creature enters, suspect it. (It has menace and can't block.)\nWhenever this creature deals combat damage to a player, you draw a card and you lose 1 life.\nWhenever this creature is dealt damage, target opponent loses that much life.",
    setup_interceptors=barbed_servitor_setup
)

BASILICA_STALKER = make_creature(
    name="Basilica Stalker",
    power=3, toughness=4,
    mana_cost="{5}{B}",
    colors={Color.BLACK},
    subtypes={"Detective", "Vampire"},
    text="Flying\nWhenever this creature deals combat damage to a player, you gain 1 life and surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\nDisguise {4}{B} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
    setup_interceptors=basilica_stalker_setup
)

CASE_OF_THE_GORGONS_KISS = make_enchantment(
    name="Case of the Gorgon's Kiss",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="When this Case enters, destroy up to one target creature that was dealt damage this turn.\nTo solve — Three or more creature cards were put into graveyards from anywhere this turn. (If unsolved, solve at the beginning of your end step.)\nSolved — This Case is a 4/4 Gorgon creature with deathtouch and lifelink in addition to its other types.",
    subtypes={"Case"},
)

CASE_OF_THE_STASHED_SKELETON = make_enchantment(
    name="Case of the Stashed Skeleton",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="When this Case enters, create a 2/1 black Skeleton creature token and suspect it. (It has menace and can't block.)\nTo solve — You control no suspected Skeletons. (If unsolved, solve at the beginning of your end step.)\nSolved — {1}{B}, Sacrifice this Case: Search your library for a card, put it into your hand, then shuffle. Activate only as a sorcery.",
    subtypes={"Case"},
    setup_interceptors=case_of_stashed_skeleton_setup
)

CEREBRAL_CONFISCATION = make_sorcery(
    name="Cerebral Confiscation",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Choose one —\n• Target opponent discards two cards.\n• Target opponent reveals their hand. You choose a nonland card from it. That player discards that card.",
)

CLANDESTINE_MEDDLER = make_creature(
    name="Clandestine Meddler",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Vampire"},
    text="When this creature enters, suspect up to one other target creature you control. (A suspected creature has menace and can't block.)\nWhenever one or more suspected creatures you control attack, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    setup_interceptors=clandestine_meddler_setup
)

DEADLY_COVERUP = make_sorcery(
    name="Deadly Cover-Up",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, you may collect evidence 6.\nDestroy all creatures. If evidence was collected, exile a card from an opponent's graveyard. Then search its owner's graveyard, hand, and library for any number of cards with that name and exile them. That player shuffles, then draws a card for each card exiled from their hand this way.",
)

EXTRACT_A_CONFESSION = make_sorcery(
    name="Extract a Confession",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, you may collect evidence 6. (Exile cards with total mana value 6 or greater from your graveyard.)\nEach opponent sacrifices a creature of their choice. If evidence was collected, instead each opponent sacrifices a creature with the greatest power among creatures they control.",
)

FESTERLEECH = make_creature(
    name="Festerleech",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Leech", "Zombie"},
    text="Whenever this creature deals combat damage to a player, you mill two cards.\n{1}{B}: This creature gets +2/+2 until end of turn. Activate only once each turn.",
    setup_interceptors=festerleech_setup
)

HOMICIDE_INVESTIGATOR = make_creature(
    name="Homicide Investigator",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Detective", "Human"},
    text="Whenever one or more nontoken creatures you control die, investigate. This ability triggers only once each turn. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    setup_interceptors=homicide_investigator_setup
)

HUNTED_BONEBRUTE = make_creature(
    name="Hunted Bonebrute",
    power=6, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Beast", "Skeleton"},
    text="Menace\nWhen this creature enters, target opponent creates two 1/1 white Dog creature tokens.\nWhen this creature dies, each opponent loses 3 life.\nDisguise {1}{B}",
    setup_interceptors=hunted_bonebrute_setup
)

ILLICIT_MASQUERADE = make_enchantment(
    name="Illicit Masquerade",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Flash\nWhen this enchantment enters, put an impostor counter on each creature you control.\nWhenever a creature you control with an impostor counter on it dies, exile it. Return up to one other target creature card from your graveyard to the battlefield.",
)

IT_DOESNT_ADD_UP = make_instant(
    name="It Doesn't Add Up",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield. Suspect it. (It has menace and can't block.)",
)

LEAD_PIPE = make_artifact(
    name="Lead Pipe",
    mana_cost="{B}",
    text="Equipped creature gets +2/+0.\nWhenever equipped creature dies, each opponent loses 1 life.\n{2}, Sacrifice this Equipment: Draw a card.\nEquip {2}",
    subtypes={"Clue", "Equipment"},
)

LEERING_ONLOOKER = make_creature(
    name="Leering Onlooker",
    power=1, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="Flying\n{2}{B}{B}, Exile this card from your graveyard: Create two tapped 1/1 black Bat creature tokens with flying.",
)

LONG_GOODBYE = make_instant(
    name="Long Goodbye",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="This spell can't be countered. (This includes by the ward ability.)\nDestroy target creature or planeswalker with mana value 3 or less.",
    resolve=long_goodbye_resolve,
)

MACABRE_RECONSTRUCTION = make_sorcery(
    name="Macabre Reconstruction",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="This spell costs {2} less to cast if a creature card was put into your graveyard from anywhere this turn.\nReturn up to two target creature cards from your graveyard to your hand.",
)

MASSACRE_GIRL_KNOWN_KILLER = make_creature(
    name="Massacre Girl, Known Killer",
    power=4, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Human"},
    supertypes={"Legendary"},
    text="Menace\nCreatures you control have wither. (They deal damage to creatures in the form of -1/-1 counters.)\nWhenever a creature an opponent controls dies, if its toughness was less than 1, draw a card.",
    setup_interceptors=massacre_girl_setup
)

MURDER = make_instant(
    name="Murder",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature.",
    resolve=murder_resolve,
)

NIGHTDRINKER_MOROII = make_creature(
    name="Nightdrinker Moroii",
    power=4, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="Flying\nWhen this creature enters, you lose 3 life.\nDisguise {B}{B} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
    setup_interceptors=nightdrinker_moroii_setup
)

OUTRAGEOUS_ROBBERY = make_instant(
    name="Outrageous Robbery",
    mana_cost="{X}{B}{B}",
    colors={Color.BLACK},
    text="Target opponent exiles the top X cards of their library face down. You may look at and play those cards for as long as they remain exiled. If you cast a spell this way, you may spend mana as though it were mana of any type to cast it.",
)

PERSUASIVE_INTERROGATORS = make_creature(
    name="Persuasive Interrogators",
    power=5, toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Detective", "Gorgon"},
    text="When this creature enters, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nWhenever you sacrifice a Clue, target opponent gets two poison counters. (A player with ten or more poison counters loses the game.)",
    setup_interceptors=persuasive_interrogators_setup
)

POLYGRAPH_ORB = make_artifact(
    name="Polygraph Orb",
    mana_cost="{4}{B}",
    text="When this artifact enters, look at the top four cards of your library. Put two of them into your hand and the rest into your graveyard. You lose 2 life.\n{2}, {T}, Collect evidence 3: Each opponent loses 3 life unless they discard a card or sacrifice a creature. (To collect evidence 3, exile cards with total mana value 3 or greater from your graveyard.)",
)

PRESUMED_DEAD = make_instant(
    name="Presumed Dead",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Until end of turn, target creature gets +2/+0 and gains \"When this creature dies, return it to the battlefield under its owner's control and suspect it.\" (A suspected creature has menace and can't block.)",
    resolve=presumed_dead_resolve,
)

REPEAT_OFFENDER = make_creature(
    name="Repeat Offender",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Human"},
    text="{2}{B}: If this creature is suspected, put a +1/+1 counter on it. Otherwise, suspect it. (A suspected creature has menace and can't block.)",
)

ROT_FARM_MORTIPEDE = make_creature(
    name="Rot Farm Mortipede",
    power=3, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Insect"},
    text="Whenever one or more creature cards leave your graveyard, this creature gets +1/+0 and gains menace and lifelink until end of turn.",
    setup_interceptors=rot_farm_mortipede_setup
)

SLICE_FROM_THE_SHADOWS = make_instant(
    name="Slice from the Shadows",
    mana_cost="{X}{B}",
    colors={Color.BLACK},
    text="This spell can't be countered. (This includes by the ward ability.)\nTarget creature gets -X/-X until end of turn.",
    resolve=slice_from_the_shadows_resolve,
)

SLIMY_DUALLEECH = make_creature(
    name="Slimy Dualleech",
    power=2, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Leech"},
    text="At the beginning of combat on your turn, target creature you control with power 2 or less gets +1/+0 and gains deathtouch until end of turn.",
)

SNARLING_GOREHOUND = make_creature(
    name="Snarling Gorehound",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Dog"},
    text="Menace\nWhenever another creature you control with power 2 or less enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    setup_interceptors=snarling_gorehound_setup
)

SOUL_ENERVATION = make_enchantment(
    name="Soul Enervation",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Flash\nWhen this enchantment enters, target creature gets -4/-4 until end of turn.\nWhenever one or more creature cards leave your graveyard, each opponent loses 1 life and you gain 1 life.",
)

TOXIN_ANALYSIS = make_instant(
    name="Toxin Analysis",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gains deathtouch and lifelink until end of turn. Investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    resolve=toxin_analysis_resolve,
)

UNDERCITY_ELIMINATOR = make_creature(
    name="Undercity Eliminator",
    power=3, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Gorgon"},
    text="When this creature enters, you may sacrifice an artifact or creature. When you do, exile target creature an opponent controls.",
    setup_interceptors=undercity_eliminator_setup
)

UNSCRUPULOUS_AGENT = make_creature(
    name="Unscrupulous Agent",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Detective", "Elf"},
    text="When this creature enters, target opponent exiles a card from their hand.",
    setup_interceptors=unscrupulous_agent_setup
)

VEIN_RIPPER = make_creature(
    name="Vein Ripper",
    power=6, toughness=5,
    mana_cost="{3}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Vampire"},
    text="Flying\nWard—Sacrifice a creature.\nWhenever a creature dies, target opponent loses 2 life and you gain 2 life.",
    setup_interceptors=vein_ripper_setup
)

ANZRAGS_RAMPAGE = make_sorcery(
    name="Anzrag's Rampage",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Destroy all artifacts you don't control, then exile the top X cards of your library, where X is the number of artifacts that were put into graveyards from the battlefield this turn. You may put a creature card exiled this way onto the battlefield. It gains haste. Return it to your hand at the beginning of the next end step.",
)

BOLRACCLAN_BASHER = make_creature(
    name="Bolrac-Clan Basher",
    power=3, toughness=2,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Cyclops", "Warrior"},
    text="Double strike, trample\nDisguise {3}{R}{R} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

CASE_OF_THE_BURNING_MASKS = make_enchantment(
    name="Case of the Burning Masks",
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    text="When this Case enters, it deals 3 damage to target creature an opponent controls.\nTo solve — Three or more sources you controlled dealt damage this turn. (If unsolved, solve at the beginning of your end step.)\nSolved — Sacrifice this Case: Exile the top three cards of your library. Choose one of them. You may play that card this turn.",
    subtypes={"Case"},
    setup_interceptors=case_of_burning_masks_setup
)

CASE_OF_THE_CRIMSON_PULSE = make_enchantment(
    name="Case of the Crimson Pulse",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="When this Case enters, discard a card, then draw two cards.\nTo solve — You have no cards in hand. (If unsolved, solve at the beginning of your end step.)\nSolved — At the beginning of your upkeep, discard your hand, then draw two cards.",
    subtypes={"Case"},
)

CAUGHT_REDHANDED = make_instant(
    name="Caught Red-Handed",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="This spell can't be countered. (This includes by the ward ability.)\nGain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. Suspect it. (It has menace and can't block.)",
    resolve=caught_redhanded_resolve,
)

THE_CHASE_IS_ON = make_instant(
    name="The Chase Is On",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains first strike until end of turn. Investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    resolve=chase_is_on_resolve,
)

CONCEALED_WEAPON = make_artifact(
    name="Concealed Weapon",
    mana_cost="{1}{R}",
    text="Equipped creature gets +3/+0.\nDisguise {2}{R} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this Equipment is turned face up, attach it to target creature you control.\nEquip {1}{R}",
    subtypes={"Equipment"},
)

CONNECTING_THE_DOTS = make_enchantment(
    name="Connecting the Dots",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Whenever a creature you control attacks, exile the top card of your library face down. (You can't look at it.)\n{1}{R}, Discard your hand, Sacrifice this enchantment: Put all cards exiled with this enchantment into their owners' hands.",
)

CONVENIENT_TARGET = make_enchantment(
    name="Convenient Target",
    mana_cost="{R}",
    colors={Color.RED},
    text="Enchant creature\nWhen this Aura enters, suspect enchanted creature. (It has menace and can't block.)\nEnchanted creature gets +1/+1.\n{2}{R}: Return this card from your graveyard to your hand.",
    subtypes={"Aura"},
)

CORNERED_CROOK = make_creature(
    name="Cornered Crook",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Warrior"},
    text="When this creature enters, you may sacrifice an artifact. When you do, this creature deals 3 damage to any target.",
    setup_interceptors=cornered_crook_setup
)

CRIME_NOVELIST = make_creature(
    name="Crime Novelist",
    power=1, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Bard", "Goblin"},
    text="Whenever you sacrifice an artifact, put a +1/+1 counter on this creature and add {R}.",
    setup_interceptors=crime_novelist_setup
)

DEMAND_ANSWERS = make_instant(
    name="Demand Answers",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="As an additional cost to cast this spell, sacrifice an artifact or discard a card.\nDraw two cards.",
)

EXPEDITED_INHERITANCE = make_enchantment(
    name="Expedited Inheritance",
    mana_cost="{R}{R}",
    colors={Color.RED},
    text="Whenever a creature is dealt damage, its controller may exile that many cards from the top of their library. They may play those cards until the end of their next turn.",
)

EXPOSE_THE_CULPRIT = make_instant(
    name="Expose the Culprit",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Choose one or both —\n• Turn target face-down creature face up.\n• Exile any number of face-up creatures you control with disguise in a face-down pile, shuffle that pile, then cloak them. (To cloak a card, put it onto the battlefield face down as a 2/2 creature with ward {2}. Turn it face up any time for its mana cost if it's a creature card.)",
)

FELONIOUS_RAGE = make_instant(
    name="Felonious Rage",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature you control gets +2/+0 and gains haste until end of turn. When that creature dies this turn, create a 2/2 white and blue Detective creature token.",
)

FRANTIC_SCAPEGOAT = make_creature(
    name="Frantic Scapegoat",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goat"},
    text="Haste\nWhen this creature enters, suspect it. (It has menace and can't block.)\nWhenever one or more other creatures you control enter, if this creature is suspected, you may suspect one of the other creatures. If you do, this creature is no longer suspected.",
    setup_interceptors=frantic_scapegoat_setup
)

FUGITIVE_CODEBREAKER = make_creature(
    name="Fugitive Codebreaker",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Rogue"},
    text="Prowess, haste\nDisguise {5}{R}. This cost is reduced by {1} for each instant and sorcery card in your graveyard. (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, discard your hand, then draw three cards.",
)

GALVANIZE = make_instant(
    name="Galvanize",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Galvanize deals 3 damage to target creature. If you've drawn two or more cards this turn, Galvanize deals 5 damage to that creature instead.",
)

GEARBANE_ORANGUTAN = make_creature(
    name="Gearbane Orangutan",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Ape"},
    text="Reach\nWhen this creature enters, choose one —\n• Destroy up to one target artifact.\n• Sacrifice an artifact. If you do, put two +1/+1 counters on this creature.",
    setup_interceptors=gearbane_orangutan_setup
)

GOBLIN_MASKMAKER = make_creature(
    name="Goblin Maskmaker",
    power=1, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Citizen", "Goblin"},
    text="Whenever this creature attacks, face-down spells you cast this turn cost {1} less to cast.",
)

HARRIED_DRONESMITH = make_creature(
    name="Harried Dronesmith",
    power=2, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Artificer", "Human"},
    text="At the beginning of combat on your turn, create a 1/1 colorless Thopter artifact creature token with flying. It gains haste until end of turn. Sacrifice it at the beginning of your next end step.",
    setup_interceptors=harried_dronesmith_setup
)

INCINERATOR_OF_THE_GUILTY = make_creature(
    name="Incinerator of the Guilty",
    power=6, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying, trample\nWhenever this creature deals combat damage to a player, you may collect evidence X. When you do, this creature deals X damage to each creature and planeswalker that player controls. (To collect evidence X, exile cards with total mana value X or greater from your graveyard.)",
)

INNOCENT_BYSTANDER = make_creature(
    name="Innocent Bystander",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Citizen", "Goblin"},
    text="Whenever this creature is dealt 3 or more damage, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    setup_interceptors=innocent_bystander_setup
)

KNIFE = make_artifact(
    name="Knife",
    mana_cost="{R}",
    text="During your turn, equipped creature gets +1/+0 and has first strike.\n{2}, Sacrifice this Equipment: Draw a card.\nEquip {2}",
    subtypes={"Clue", "Equipment"},
)

KRENKO_BARON_OF_TIN_STREET = make_creature(
    name="Krenko, Baron of Tin Street",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
    supertypes={"Legendary"},
    text="Haste\n{T}, Sacrifice an artifact: Put a +1/+1 counter on each Goblin you control.\nWhenever an artifact is put into a graveyard from the battlefield, you may pay {R}. If you do, create a 1/1 red Goblin creature token. It gains haste until end of turn.",
    setup_interceptors=krenko_baron_setup
)

KRENKOS_BUZZCRUSHER = make_artifact_creature(
    name="Krenko's Buzzcrusher",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Insect", "Thopter"},
    text="Flying, trample\nWhen this creature enters, for each player, destroy up to one nonbasic land that player controls. For each land destroyed this way, its controller may search their library for a basic land card, put it onto the battlefield tapped, then shuffle.",
    setup_interceptors=krenkos_buzzcrusher_setup
)

LAMPLIGHT_PHOENIX = make_creature(
    name="Lamplight Phoenix",
    power=3, toughness=3,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Phoenix"},
    text="Flying\nWhen this creature dies, you may exile it and collect evidence 4. If you do, return this card to the battlefield tapped. (To collect evidence 4, exile cards with total mana value 4 or greater from your graveyard.)",
)

OFFENDER_AT_LARGE = make_creature(
    name="Offender at Large",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Giant", "Rogue"},
    text="Disguise {4}{R} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature enters or is turned face up, up to one target creature gets +2/+0 until end of turn.",
)

PERSON_OF_INTEREST = make_creature(
    name="Person of Interest",
    power=2, toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rogue"},
    text="When this creature enters, suspect it. Create a 2/2 white and blue Detective creature token. (A suspected creature has menace and can't block.)",
    setup_interceptors=person_of_interest_setup
)

PYROTECHNIC_PERFORMER = make_creature(
    name="Pyrotechnic Performer",
    power=3, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Assassin", "Lizard"},
    text="Disguise {R} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhenever this creature or another creature you control is turned face up, that creature deals damage equal to its power to each opponent.",
)

RECKLESS_DETECTIVE = make_creature(
    name="Reckless Detective",
    power=0, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Detective", "Devil"},
    text="Whenever this creature attacks, you may sacrifice an artifact or discard a card. If you do, draw a card and this creature gets +2/+0 until end of turn.",
)

RED_HERRING = make_artifact_creature(
    name="Red Herring",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Clue", "Fish"},
    text="Haste\nThis creature attacks each combat if able.\n{2}, Sacrifice this creature: Draw a card.",
)

RUBBLEBELT_BRAGGART = make_creature(
    name="Rubblebelt Braggart",
    power=5, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Warrior"},
    text="Whenever this creature attacks, if it's not suspected, you may suspect it. (A suspected creature has menace and can't block.)",
)

SHOCK = make_instant(
    name="Shock",
    mana_cost="{R}",
    colors={Color.RED},
    text="Shock deals 2 damage to any target.",
    resolve=shock_resolve,
)

SUSPICIOUS_DETONATION = make_sorcery(
    name="Suspicious Detonation",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="This spell costs {3} less to cast if you've sacrificed an artifact this turn.\nThis spell can't be countered. (This includes by the ward ability.)\nSuspicious Detonation deals 4 damage to target creature.",
    resolve=suspicious_detonation_resolve,
)

TORCH_THE_WITNESS = make_sorcery(
    name="Torch the Witness",
    mana_cost="{X}{R}",
    colors={Color.RED},
    text="Torch the Witness deals twice X damage to target creature. If excess damage was dealt to that creature this way, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    resolve=torch_the_witness_resolve,
)

VENGEFUL_TRACKER = make_creature(
    name="Vengeful Tracker",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Detective", "Human"},
    text="Whenever an opponent sacrifices an artifact, this creature deals 2 damage to them.",
    setup_interceptors=vengeful_tracker_setup
)

AFTERMATH_ANALYST = make_creature(
    name="Aftermath Analyst",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Detective", "Elf"},
    text="When this creature enters, mill three cards. (Put the top three cards of your library into your graveyard.)\n{3}{G}, Sacrifice this creature: Return all land cards from your graveyard to the battlefield tapped.",
    setup_interceptors=aftermath_analyst_setup
)

AIRTIGHT_ALIBI = make_enchantment(
    name="Airtight Alibi",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Flash\nEnchant creature\nWhen this Aura enters, untap enchanted creature. It gains hexproof until end of turn. If it's suspected, it's no longer suspected.\nEnchanted creature gets +2/+2 and can't become suspected.",
    subtypes={"Aura"},
)

ANALYZE_THE_POLLEN = make_sorcery(
    name="Analyze the Pollen",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="As an additional cost to cast this spell, you may collect evidence 8. (Exile cards with total mana value 8 or greater from your graveyard.)\nSearch your library for a basic land card. If evidence was collected, instead search your library for a creature or land card. Reveal that card, put it into your hand, then shuffle.",
)

ARCHDRUIDS_CHARM = make_instant(
    name="Archdruid's Charm",
    mana_cost="{G}{G}{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Search your library for a creature or land card and reveal it. Put it onto the battlefield tapped if it's a land card. Otherwise, put it into your hand. Then shuffle.\n• Put a +1/+1 counter on target creature you control. It deals damage equal to its power to target creature you don't control.\n• Exile target artifact or enchantment.",
)

AUDIENCE_WITH_TROSTANI = make_sorcery(
    name="Audience with Trostani",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Create a 0/1 green Plant creature token, then draw cards equal to the number of differently named creature tokens you control.",
)

AXEBANE_FEROX = make_creature(
    name="Axebane Ferox",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Deathtouch, haste\nWard—Collect evidence 4. (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player exiles cards with total mana value 4 or greater from their graveyard.)",
)

BITE_DOWN_ON_CRIME = make_sorcery(
    name="Bite Down on Crime",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="As an additional cost to cast this spell, you may collect evidence 6. This spell costs {2} less to cast if evidence was collected. (To collect evidence 6, exile cards with total mana value 6 or greater from your graveyard.)\nTarget creature you control gets +2/+0 until end of turn. It deals damage equal to its power to target creature you don't control.",
)

CASE_OF_THE_LOCKED_HOTHOUSE = make_enchantment(
    name="Case of the Locked Hothouse",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="You may play an additional land on each of your turns.\nTo solve — You control seven or more lands. (If unsolved, solve at the beginning of your end step.)\nSolved — You may look at the top card of your library any time, and you may play lands and cast creature and enchantment spells from the top of your library.",
    subtypes={"Case"},
)

CASE_OF_THE_TRAMPLED_GARDEN = make_enchantment(
    name="Case of the Trampled Garden",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="When this Case enters, distribute two +1/+1 counters among one or two target creatures you control.\nTo solve — Creatures you control have total power 8 or greater. (If unsolved, solve at the beginning of your end step.)\nSolved — Whenever you attack, put a +1/+1 counter on target attacking creature. It gains trample until end of turn.",
    subtypes={"Case"},
)

CHALK_OUTLINE = make_enchantment(
    name="Chalk Outline",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Whenever one or more creature cards leave your graveyard, create a 2/2 white and blue Detective creature token, then investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    setup_interceptors=chalk_outline_setup
)

CULVERT_AMBUSHER = make_creature(
    name="Culvert Ambusher",
    power=4, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Horror", "Wurm"},
    text="When this creature enters or is turned face up, target creature blocks this turn if able.\nDisguise {4}{G} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

FANATICAL_STRENGTH = make_instant(
    name="Fanatical Strength",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 and gains trample until end of turn.",
    resolve=fanatical_strength_resolve,
)

FLOURISHING_BLOOMKIN = make_creature(
    name="Flourishing Bloom-Kin",
    power=0, toughness=0,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental", "Plant"},
    text="This creature gets +1/+1 for each Forest you control.\nDisguise {4}{G}\nWhen this creature is turned face up, search your library for up to two Forest cards and reveal them. Put one of them onto the battlefield tapped and the other into your hand, then shuffle.",
)

GET_A_LEG_UP = make_instant(
    name="Get a Leg Up",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Until end of turn, target creature gets +1/+1 for each creature you control and gains reach.",
)

GLINT_WEAVER = make_creature(
    name="Glint Weaver",
    power=3, toughness=3,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Spider"},
    text="Reach\nWhen this creature enters, distribute three +1/+1 counters among one, two, or three target creatures, then you gain life equal to the greatest toughness among creatures you control.",
    setup_interceptors=glint_weaver_setup
)

GREENBELT_RADICAL = make_creature(
    name="Greenbelt Radical",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Centaur", "Citizen"},
    text="Disguise {5}{G}{G} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, put a +1/+1 counter on each creature you control. Creatures you control gain trample until end of turn.",
)

HARDHITTING_QUESTION = make_sorcery(
    name="Hard-Hitting Question",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature you control deals damage equal to its power to target creature or planeswalker you don't control.",
)

HEDGE_WHISPERER = make_creature(
    name="Hedge Whisperer",
    power=0, toughness=3,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Detective", "Druid", "Elf"},
    text="You may choose not to untap this creature during your untap step.\n{3}{G}, {T}, Collect evidence 4: Target land you control becomes a 5/5 green Plant Boar creature with haste for as long as this creature remains tapped. It's still a land. Activate only as a sorcery. (To collect evidence 4, exile cards with total mana value 4 or greater from your graveyard.)",
)

HIDE_IN_PLAIN_SIGHT = make_sorcery(
    name="Hide in Plain Sight",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Look at the top five cards of your library, cloak two of them, and put the rest on the bottom of your library in a random order. (To cloak a card, put it onto the battlefield face down as a 2/2 creature with ward {2}. Turn it face up any time for its mana cost if it's a creature card.)",
)

A_KILLER_AMONG_US = make_enchantment(
    name="A Killer Among Us",
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, create a 1/1 white Human creature token, a 1/1 blue Merfolk creature token, and a 1/1 red Goblin creature token. Then secretly choose Human, Merfolk, or Goblin.\nSacrifice this enchantment, Reveal the creature type you chose: If target attacking creature token is the chosen type, put three +1/+1 counters on it and it gains deathtouch until end of turn.",
)

LOXODON_EAVESDROPPER = make_creature(
    name="Loxodon Eavesdropper",
    power=3, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Detective", "Elephant"},
    text="When this creature enters, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nWhenever you draw your second card each turn, this creature gets +1/+1 and gains vigilance until end of turn.",
    setup_interceptors=loxodon_eavesdropper_setup
)

NERVOUS_GARDENER = make_creature(
    name="Nervous Gardener",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Dryad"},
    text="Disguise {G} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, search your library for a land card with a basic land type, reveal it, put it into your hand, then shuffle.",
)


# =============================================================================
# PICK YOUR POISON - Modal edict effect
# =============================================================================

def _pick_your_poison_handle_sacrifice(choice, selected: list, state: GameState) -> list[Event]:
    """Handle sacrifice selection from an opponent."""
    if not selected:
        return []

    permanent_id = selected[0]
    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': permanent_id, 'sacrificed': True},
        source=choice.source_id
    )]


def _pick_your_poison_execute_mode(choice, selected: list, state: GameState) -> list[Event]:
    """Execute the chosen mode - make opponents sacrifice."""
    if not selected:
        return []

    selected_mode = selected[0]
    mode_index = selected_mode["index"] if isinstance(selected_mode, dict) else selected_mode

    # Get the caster to identify opponents
    caster_id = choice.player
    opponents = [p_id for p_id in state.players.keys() if p_id != caster_id]

    events = []

    for opp_id in opponents:
        # Find legal permanents for this opponent based on mode
        legal_permanents = []
        for obj_id, obj in state.objects.items():
            if obj.zone != ZoneType.BATTLEFIELD:
                continue
            if obj.controller != opp_id:
                continue

            if mode_index == 0:
                # Mode 0: Artifact
                if CardType.ARTIFACT in obj.characteristics.types:
                    legal_permanents.append(obj_id)
            elif mode_index == 1:
                # Mode 1: Enchantment
                if CardType.ENCHANTMENT in obj.characteristics.types:
                    legal_permanents.append(obj_id)
            else:
                # Mode 2: Creature with flying
                if CardType.CREATURE in obj.characteristics.types:
                    # Check for flying keyword
                    abilities = obj.characteristics.abilities or []
                    if 'flying' in abilities:
                        legal_permanents.append(obj_id)

        if legal_permanents:
            # Create sacrifice choice for this opponent
            if mode_index == 0:
                prompt = "Sacrifice an artifact"
            elif mode_index == 1:
                prompt = "Sacrifice an enchantment"
            else:
                prompt = "Sacrifice a creature with flying"

            create_sacrifice_choice(
                state=state,
                player_id=opp_id,
                source_id=choice.source_id,
                permanent_ids=legal_permanents,
                sacrifice_count=1,
                prompt=prompt
            )
            state.pending_choice.callback_data['handler'] = _pick_your_poison_handle_sacrifice

    return events


def pick_your_poison_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Pick Your Poison: Choose one —
    - Each opponent sacrifices an artifact
    - Each opponent sacrifices an enchantment
    - Each opponent sacrifices a creature with flying

    Creates a modal choice first, then sacrifice choices for opponents.
    """
    # Find the spell on the stack to determine who cast it
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Pick Your Poison":
                caster_id = obj.controller
                spell_id = obj.id
                break

    # Fallback to active player if we can't find the spell
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "pick_your_poison_spell"

    # Create modal choice
    modes = [
        {"index": 0, "text": "Each opponent sacrifices an artifact."},
        {"index": 1, "text": "Each opponent sacrifices an enchantment."},
        {"index": 2, "text": "Each opponent sacrifices a creature with flying."}
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        prompt="Pick Your Poison - Choose one:"
    )

    # Use modal_with_callback for handler support
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _pick_your_poison_execute_mode

    return []



PICK_YOUR_POISON = make_sorcery(
    name="Pick Your Poison",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Each opponent sacrifices an artifact of their choice.\n• Each opponent sacrifices an enchantment of their choice.\n• Each opponent sacrifices a creature with flying of their choice.",
    resolve=pick_your_poison_resolve,
)

POMPOUS_GADABOUT = make_creature(
    name="Pompous Gadabout",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Citizen", "Human"},
    text="During your turn, this creature has hexproof.\nThis creature can't be blocked by creatures that don't have a name.",
)

THE_PRIDE_OF_HULL_CLADE = make_creature(
    name="The Pride of Hull Clade",
    power=2, toughness=15,
    mana_cost="{10}{G}",
    colors={Color.GREEN},
    subtypes={"Crocodile", "Elk", "Turtle"},
    supertypes={"Legendary"},
    text="This spell costs {X} less to cast, where X is the total toughness of creatures you control.\nDefender\n{2}{U}{U}: Until end of turn, target creature you control gets +1/+0, gains \"Whenever this creature deals combat damage to a player, draw cards equal to its toughness,\" and can attack as though it didn't have defender.",
)

ROPE = make_artifact(
    name="Rope",
    mana_cost="{G}",
    text="Equipped creature gets +1/+2, has reach, and can't be blocked by more than one creature.\n{2}, Sacrifice this Equipment: Draw a card.\nEquip {3}",
    subtypes={"Clue", "Equipment"},
)

RUBBLEBELT_MAVERICK = make_creature(
    name="Rubblebelt Maverick",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Detective", "Human"},
    text="When this creature enters, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\n{G}, Exile this card from your graveyard: Put a +1/+1 counter on target creature. Activate only as a sorcery.",
    setup_interceptors=rubblebelt_maverick_setup
)

SAMPLE_COLLECTOR = make_creature(
    name="Sample Collector",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Detective", "Troll"},
    text="Whenever this creature attacks, you may collect evidence 3. When you do, put a +1/+1 counter on target creature you control. (To collect evidence 3, exile cards with total mana value 3 or greater from your graveyard.)",
)

SHARPEYED_ROOKIE = make_creature(
    name="Sharp-Eyed Rookie",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Detective", "Human"},
    text="Vigilance\nWhenever a creature you control enters, if its power is greater than this creature's power or its toughness is greater than this creature's toughness, put a +1/+1 counter on this creature and investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    setup_interceptors=sharp_eyed_rookie_setup
)

SLIME_AGAINST_HUMANITY = make_sorcery(
    name="Slime Against Humanity",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Create a 0/0 green Ooze creature token with trample. Put X +1/+1 counters on it, where X is two plus the total number of cards you own in exile and in your graveyard that are Oozes or are named Slime Against Humanity.\nA deck can have any number of cards named Slime Against Humanity.",
)

THEY_WENT_THIS_WAY = make_sorcery(
    name="They Went This Way",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. Investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

TOPIARY_PANTHER = make_creature(
    name="Topiary Panther",
    power=6, toughness=5,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Cat", "Plant"},
    text="Trample\nBasic landcycling {1}{G} ({1}{G}, Discard this card: Search your library for a basic land card, reveal it, put it into your hand, then shuffle.)",
)

TUNNEL_TIPSTER = make_creature(
    name="Tunnel Tipster",
    power=1, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Mole", "Scout"},
    text="At the beginning of your end step, if a face-down creature entered the battlefield under your control this turn, put a +1/+1 counter on this creature.\n{T}: Add {G}.",
)

UNDERGROWTH_RECON = make_enchantment(
    name="Undergrowth Recon",
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    text="At the beginning of your upkeep, return target land card from your graveyard to the battlefield tapped.",
)

VENGEFUL_CREEPER = make_creature(
    name="Vengeful Creeper",
    power=5, toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental", "Plant"},
    text="Disguise {5}{G} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, destroy target artifact or enchantment an opponent controls.",
)

VITUGHAZI_INSPECTOR = make_creature(
    name="Vitu-Ghazi Inspector",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Detective", "Elf"},
    text="As an additional cost to cast this spell, you may collect evidence 6. (Exile cards with total mana value 6 or greater from your graveyard.)\nReach\nWhen this creature enters, if evidence was collected, put a +1/+1 counter on target creature and you gain 2 life.",
)

AGRUS_KOS_SPIRIT_OF_JUSTICE = make_creature(
    name="Agrus Kos, Spirit of Justice",
    power=2, toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Detective", "Spirit"},
    supertypes={"Legendary"},
    text="Double strike, vigilance\nWhenever Agrus Kos enters or attacks, choose up to one target creature. If it's suspected, exile it. Otherwise, suspect it. (A suspected creature has menace and can't block.)",
    setup_interceptors=agrus_kos_setup
)

ALQUIST_PROFT_MASTER_SLEUTH = make_creature(
    name="Alquist Proft, Master Sleuth",
    power=3, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Detective", "Human"},
    supertypes={"Legendary"},
    text="Vigilance\nWhen Alquist Proft enters, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\n{X}{W}{U}{U}, {T}, Sacrifice a Clue: You draw X cards and gain X life.",
    setup_interceptors=alquist_proft_setup
)

ANZRAG_THE_QUAKEMOLE = make_creature(
    name="Anzrag, the Quake-Mole",
    power=8, toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"God", "Mole"},
    supertypes={"Legendary"},
    text="Whenever Anzrag becomes blocked, untap each creature you control. After this phase, there is an additional combat phase.\n{3}{R}{R}{G}{G}: Anzrag must be blocked each combat this turn if able.",
)

ASSASSINS_TROPHY = make_instant(
    name="Assassin's Trophy",
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Destroy target permanent an opponent controls. Its controller may search their library for a basic land card, put it onto the battlefield, then shuffle.",
    resolve=assassins_trophy_resolve,
)

AURELIA_THE_LAW_ABOVE = make_creature(
    name="Aurelia, the Law Above",
    power=4, toughness=4,
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Angel"},
    supertypes={"Legendary"},
    text="Flying, vigilance, haste\nWhenever a player attacks with three or more creatures, you draw a card.\nWhenever a player attacks with five or more creatures, Aurelia deals 3 damage to each of your opponents and you gain 3 life.",
)

BLOOD_SPATTER_ANALYSIS = make_enchantment(
    name="Blood Spatter Analysis",
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="When this enchantment enters, it deals 3 damage to target creature an opponent controls.\nWhenever one or more creatures die, mill a card and put a bloodstain counter on this enchantment. Then sacrifice it if it has five or more bloodstain counters on it. When you do, return target creature card from your graveyard to your hand.",
    setup_interceptors=blood_spatter_analysis_setup
)

BREAK_OUT = make_sorcery(
    name="Break Out",
    mana_cost="{R}{G}",
    colors={Color.GREEN, Color.RED},
    text="Look at the top six cards of your library. You may reveal a creature card from among them. If that card has mana value 2 or less, you may put it onto the battlefield and it gains haste until end of turn. If you didn't put the revealed card onto the battlefield this way, put it into your hand. Put the rest on the bottom of your library in a random order.",
)

BURIED_IN_THE_GARDEN = make_enchantment(
    name="Buried in the Garden",
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Enchant land\nWhen this Aura enters, exile target nonland permanent you don't control until this Aura leaves the battlefield.\nWhenever enchanted land is tapped for mana, its controller adds an additional one mana of any color.",
    subtypes={"Aura"},
)

COERCED_TO_KILL = make_enchantment(
    name="Coerced to Kill",
    mana_cost="{3}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    text="Enchant creature\nYou control enchanted creature.\nEnchanted creature has base power and toughness 1/1, has deathtouch, and is an Assassin in addition to its other types.",
    subtypes={"Aura"},
)

CROWDCONTROL_WARDEN = make_creature(
    name="Crowd-Control Warden",
    power=4, toughness=4,
    mana_cost="{3}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Centaur", "Soldier"},
    text="As this creature enters or is turned face up, put X +1/+1 counters on it, where X is the number of other creatures you control.\nDisguise {3}{G/W}{G/W} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

CURIOUS_CADAVER = make_creature(
    name="Curious Cadaver",
    power=3, toughness=1,
    mana_cost="{2}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Detective", "Zombie"},
    text="Flying\nWhen you sacrifice a Clue, return this card from your graveyard to your hand.",
)

DEADLY_COMPLICATION = make_sorcery(
    name="Deadly Complication",
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Choose one or both —\n• Destroy target creature.\n• Put a +1/+1 counter on target suspected creature you control. You may have it become no longer suspected.",
    resolve=deadly_complication_resolve,
)

DETECTIVES_SATCHEL = make_artifact(
    name="Detective's Satchel",
    mana_cost="{2}{U}{R}",
    text="When this artifact enters, investigate twice. (To investigate, create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\n{T}: Create a 1/1 colorless Thopter artifact creature token with flying. Activate only if you've sacrificed an artifact this turn.",
    setup_interceptors=detectives_satchel_setup
)

DOG_WALKER = make_creature(
    name="Dog Walker",
    power=3, toughness=1,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Citizen", "Human"},
    text="Vigilance\nDisguise {R/W}{R/W} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, create two tapped 1/1 white Dog creature tokens.",
)

DOPPELGANG = make_sorcery(
    name="Doppelgang",
    mana_cost="{X}{X}{X}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    text="For each of X target permanents, create X tokens that are copies of that permanent.",
)

DRAG_THE_CANAL = make_instant(
    name="Drag the Canal",
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    text="Create a 2/2 white and blue Detective creature token. If a creature died this turn, you gain 2 life, surveil 2, then investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

ETRATA_DEADLY_FUGITIVE = make_creature(
    name="Etrata, Deadly Fugitive",
    power=1, toughness=4,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Assassin", "Vampire"},
    supertypes={"Legendary"},
    text="Deathtouch\nFace-down creatures you control have \"{2}{U}{B}: Turn this creature face up. If you can't, exile it, then you may cast the exiled card without paying its mana cost.\"\nWhenever an Assassin you control deals combat damage to an opponent, cloak the top card of that player's library.",
)

EVIDENCE_EXAMINER = make_creature(
    name="Evidence Examiner",
    power=2, toughness=2,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Detective", "Merfolk"},
    text="At the beginning of combat on your turn, you may collect evidence 4. (Exile cards with total mana value 4 or greater from your graveyard.)\nWhenever you collect evidence, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

EZRIM_AGENCY_CHIEF = make_creature(
    name="Ezrim, Agency Chief",
    power=5, toughness=5,
    mana_cost="{1}{W}{W}{U}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Archon", "Detective"},
    supertypes={"Legendary"},
    text="Flying\nWhen Ezrim enters, investigate twice. (To investigate, create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\n{1}, Sacrifice an artifact: Ezrim gains your choice of vigilance, lifelink, or hexproof until end of turn.",
    setup_interceptors=ezrim_agency_chief_setup
)

FAERIE_SNOOP = make_creature(
    name="Faerie Snoop",
    power=1, toughness=4,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Detective", "Faerie"},
    text="Flying\nDisguise {1}{U/B}{U/B} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, look at the top two cards of your library. Put one into your hand and the other into your graveyard.",
)

GADGET_TECHNICIAN = make_creature(
    name="Gadget Technician",
    power=3, toughness=2,
    mana_cost="{2}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Artificer", "Goblin"},
    text="When this creature enters or is turned face up, create a 1/1 colorless Thopter artifact creature token with flying.\nDisguise {U/R}{U/R} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
    setup_interceptors=gadget_technician_setup
)

GLEAMING_GEARDRAKE = make_artifact_creature(
    name="Gleaming Geardrake",
    power=1, toughness=1,
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Drake"},
    text="Flying\nWhen this creature enters, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nWhenever you sacrifice an artifact, put a +1/+1 counter on this creature.",
    setup_interceptors=gleaming_geardrake_setup
)

GRANITE_WITNESS = make_artifact_creature(
    name="Granite Witness",
    power=3, toughness=2,
    mana_cost="{2}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Detective", "Gargoyle"},
    text="Flying, vigilance\nDisguise {W/U}{W/U} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, you may tap or untap target creature.",
)

ILLTIMED_EXPLOSION = make_sorcery(
    name="Ill-Timed Explosion",
    mana_cost="{2}{U}{R}",
    colors={Color.RED, Color.BLUE},
    text="Draw two cards. Then you may discard two cards. When you do, Ill-Timed Explosion deals X damage to each creature, where X is the greatest mana value among cards discarded this way.",
)

INSIDIOUS_ROOTS = make_enchantment(
    name="Insidious Roots",
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Creature tokens you control have \"{T}: Add one mana of any color.\"\nWhenever one or more creature cards leave your graveyard, create a 0/1 green Plant creature token, then put a +1/+1 counter on each Plant you control.",
    setup_interceptors=insidious_roots_setup
)

IZONI_CENTER_OF_THE_WEB = make_creature(
    name="Izoni, Center of the Web",
    power=5, toughness=4,
    mana_cost="{4}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Detective", "Elf"},
    supertypes={"Legendary"},
    text="Menace\nWhenever Izoni enters or attacks, you may collect evidence 4. If you do, create two 2/1 black and green Spider creature tokens with menace and reach.\nSacrifice four tokens: Surveil 2, then draw two cards. You gain 2 life.",
)

JUDITH_CARNAGE_CONNOISSEUR = make_creature(
    name="Judith, Carnage Connoisseur",
    power=3, toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Shaman"},
    supertypes={"Legendary"},
    text="Whenever you cast an instant or sorcery spell, choose one —\n• That spell gains deathtouch and lifelink.\n• Create a 2/2 red Imp creature token with \"When this token dies, it deals 2 damage to each opponent.\"",
)

KAYA_SPIRITS_JUSTICE = make_planeswalker(
    name="Kaya, Spirits' Justice",
    mana_cost="{2}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    loyalty=3,
    subtypes={"Kaya"},
    supertypes={"Legendary"},
    text="Whenever one or more creatures you control and/or creature cards in your graveyard are put into exile, you may choose a creature card from among them. Until end of turn, target token you control becomes a copy of it, except it has flying.\n+2: Surveil 2, then exile a card from a graveyard.\n+1: Create a 1/1 white and black Spirit creature token with flying.\n−2: Exile target creature you control. For each other player, exile up to one target creature that player controls.",
)

KELLAN_INQUISITIVE_PRODIGY = make_creature(
    name="Kellan, Inquisitive Prodigy",
    power=3, toughness=4,
    mana_cost="{2}{G}{U} // {G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"//", "Detective", "Faerie", "Human", "Sorcery"},
    supertypes={"Legendary"},
    text="",
)

KRAUL_WHIPCRACKER = make_creature(
    name="Kraul Whipcracker",
    power=3, toughness=2,
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Assassin", "Insect"},
    text="Reach\nWhen this creature enters, destroy target token an opponent controls.",
    setup_interceptors=kraul_whipcracker_setup
)

KYLOX_VISIONARY_INVENTOR = make_creature(
    name="Kylox, Visionary Inventor",
    power=4, toughness=4,
    mana_cost="{5}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Artificer", "Lizard"},
    supertypes={"Legendary"},
    text="Menace, ward {2}, haste\nWhenever Kylox attacks, sacrifice any number of other creatures, then exile the top X cards of your library, where X is their total power. You may cast any number of instant and/or sorcery spells from among the exiled cards without paying their mana costs.",
)

KYLOXS_VOLTSTRIDER = make_artifact(
    name="Kylox's Voltstrider",
    mana_cost="{1}{U}{R}",
    text="Collect evidence 6: This Vehicle becomes an artifact creature until end of turn.\nWhenever this Vehicle attacks, you may cast an instant or sorcery spell from among cards exiled with it. If that spell would be put into a graveyard, put it on the bottom of its owner's library instead.\nCrew 2",
    subtypes={"Vehicle"},
)

LAZAV_WEARER_OF_FACES = make_creature(
    name="Lazav, Wearer of Faces",
    power=2, toughness=3,
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Detective", "Shapeshifter"},
    supertypes={"Legendary"},
    text="Whenever Lazav attacks, exile target card from a graveyard, then investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nWhenever you sacrifice a Clue, you may have Lazav become a copy of a creature card exiled with it until end of turn.",
)

LEYLINE_OF_THE_GUILDPACT = make_enchantment(
    name="Leyline of the Guildpact",
    mana_cost="{G/W}{G/U}{B/G}{R/G}",
    colors={Color.BLACK, Color.GREEN, Color.RED, Color.BLUE, Color.WHITE},
    text="If this card is in your opening hand, you may begin the game with it on the battlefield.\nEach nonland permanent you control is all colors.\nLands you control are every basic land type in addition to their other types.",
)

LIGHTNING_HELIX = make_instant(
    name="Lightning Helix",
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Lightning Helix deals 3 damage to any target and you gain 3 life.",
    resolve=lightning_helix_resolve,
)

MEDDLING_YOUTHS = make_creature(
    name="Meddling Youths",
    power=4, toughness=5,
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Detective", "Human"},
    text="Haste\nWhenever you attack with three or more creatures, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
    setup_interceptors=meddling_youths_setup
)

NIVMIZZET_GUILDPACT = make_creature(
    name="Niv-Mizzet, Guildpact",
    power=6, toughness=6,
    mana_cost="{W}{U}{B}{R}{G}",
    colors={Color.BLACK, Color.GREEN, Color.RED, Color.BLUE, Color.WHITE},
    subtypes={"Avatar", "Dragon"},
    supertypes={"Legendary"},
    text="Flying, hexproof from multicolored\nWhenever Niv-Mizzet deals combat damage to a player, it deals X damage to any target, target player draws X cards, and you gain X life, where X is the number of different color pairs among permanents you control that are exactly two colors.",
)

NO_MORE_LIES = make_instant(
    name="No More Lies",
    mana_cost="{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    text="Counter target spell unless its controller pays {3}. If that spell is countered this way, exile it instead of putting it into its owner's graveyard.",
    resolve=no_more_lies_resolve,
)

OFFICIOUS_INTERROGATION = make_instant(
    name="Officious Interrogation",
    mana_cost="{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    text="This spell costs {W}{U} more to cast for each target beyond the first.\nChoose any number of target players. Investigate X times, where X is the total number of creatures those players control.",
)

PRIVATE_EYE = make_creature(
    name="Private Eye",
    power=3, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Detective", "Homunculus"},
    text="Other Detectives you control get +1/+1.\nWhenever you draw your second card each turn, target Detective can't be blocked this turn.",
    setup_interceptors=private_eye_setup
)

RAKDOS_PATRON_OF_CHAOS = make_creature(
    name="Rakdos, Patron of Chaos",
    power=6, toughness=6,
    mana_cost="{4}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon"},
    supertypes={"Legendary"},
    text="Flying, trample\nAt the beginning of your end step, target opponent may sacrifice two nonland, nontoken permanents of their choice. If they don't, you draw two cards.",
)

RAKISH_SCOUNDREL = make_creature(
    name="Rakish Scoundrel",
    power=3, toughness=3,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Elf", "Rogue"},
    text="Deathtouch\nWhen this creature enters or is turned face up, target creature gains indestructible until end of turn.\nDisguise {4}{B/G}{B/G} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

RELIVE_THE_PAST = make_sorcery(
    name="Relive the Past",
    mana_cost="{5}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Return up to one target artifact card, up to one target land card, and up to one target non-Aura enchantment card from your graveyard to the battlefield. They are 5/5 Elemental creatures in addition to their other types.",
)

REPULSIVE_MUTATION = make_instant(
    name="Repulsive Mutation",
    mana_cost="{X}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    text="Put X +1/+1 counters on target creature you control. Then counter up to one target spell unless its controller pays mana equal to the greatest power among creatures you control.",
)

RIFTBURST_HELLION = make_creature(
    name="Riftburst Hellion",
    power=6, toughness=7,
    mana_cost="{5}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Hellion"},
    text="Reach\nDisguise {4}{R/G}{R/G} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

RUNEBRAND_JUGGLER = make_creature(
    name="Rune-Brand Juggler",
    power=2, toughness=2,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Shaman"},
    text="When this creature enters, suspect up to one target creature you control. (A suspected creature has menace and can't block.)\n{3}{B}{R}, Sacrifice a suspected creature: Target creature gets -5/-5 until end of turn.",
)

SANGUINE_SAVIOR = make_creature(
    name="Sanguine Savior",
    power=2, toughness=1,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Cleric", "Vampire"},
    text="Flying, lifelink\nDisguise {W/B}{W/B} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, another target creature you control gains lifelink until end of turn.",
)

SHADY_INFORMANT = make_creature(
    name="Shady Informant",
    power=4, toughness=2,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Ogre", "Rogue"},
    text="When this creature dies, it deals 2 damage to any target.\nDisguise {2}{B/R}{B/R} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
    setup_interceptors=shady_informant_setup
)

SOUL_SEARCH = make_sorcery(
    name="Soul Search",
    mana_cost="{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    text="Target opponent reveals their hand. You choose a nonland card from it. Exile that card. If the card's mana value is 1 or less, create a 1/1 white and black Spirit creature token with flying.",
    resolve=soul_search_resolve,
)

SUMALA_SENTRY = make_creature(
    name="Sumala Sentry",
    power=1, toughness=3,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Archer", "Elf"},
    text="Reach\nWhenever a face-down permanent you control is turned face up, put a +1/+1 counter on it and a +1/+1 counter on this creature.",
)

TEYSA_OPULENT_OLIGARCH = make_creature(
    name="Teysa, Opulent Oligarch",
    power=2, toughness=3,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Advisor", "Human"},
    supertypes={"Legendary"},
    text="Deathtouch\nAt the beginning of your end step, investigate for each opponent who lost life this turn.\nWhenever a Clue you control is put into a graveyard from the battlefield, create a 1/1 white and black Spirit creature token with flying. This ability triggers only once each turn.",
    setup_interceptors=teysa_opulent_oligarch_setup
)

TIN_STREET_GOSSIP = make_creature(
    name="Tin Street Gossip",
    power=4, toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Advisor", "Lizard"},
    text="Vigilance\n{T}: Add {R}{G}. Spend this mana only to cast face-down spells or to turn creatures face up.",
)

TOLSIMIR_MIDNIGHTS_LIGHT = make_creature(
    name="Tolsimir, Midnight's Light",
    power=3, toughness=2,
    mana_cost="{2}{G}{W}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Elf", "Scout"},
    supertypes={"Legendary"},
    text="Lifelink\nWhen Tolsimir enters, create Voja Fenstalker, a legendary 5/5 green and white Wolf creature token with trample.\nWhenever a Wolf you control attacks, if Tolsimir attacked this combat, target creature an opponent controls blocks that Wolf this combat if able.",
    setup_interceptors=tolsimir_setup
)

TREACHEROUS_GREED = make_instant(
    name="Treacherous Greed",
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    text="As an additional cost to cast this spell, sacrifice a creature that dealt damage this turn.\nDraw three cards. Each opponent loses 3 life and you gain 3 life.",
)

TROSTANI_THREE_WHISPERS = make_creature(
    name="Trostani, Three Whispers",
    power=4, toughness=4,
    mana_cost="{G}{G/W}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Dryad"},
    supertypes={"Legendary"},
    text="{1}{G}: Target creature gains deathtouch until end of turn.\n{G/W}: Target creature gains vigilance until end of turn.\n{2}{W}: Target creature gains double strike until end of turn.",
)

UNDERCOVER_CROCODELF = make_creature(
    name="Undercover Crocodelf",
    power=5, toughness=5,
    mana_cost="{4}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Crocodile", "Detective", "Elf"},
    text="Whenever this creature deals combat damage to a player, investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")\nDisguise {3}{G/U}{G/U} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

URGENT_NECROPSY = make_instant(
    name="Urgent Necropsy",
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="As an additional cost to cast this spell, collect evidence X, where X is the total mana value of the permanents this spell targets.\nDestroy up to one target artifact, up to one target creature, up to one target enchantment, and up to one target planeswalker.",
)

VANNIFAR_EVOLVED_ENIGMA = make_creature(
    name="Vannifar, Evolved Enigma",
    power=3, toughness=4,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Elf", "Ooze", "Wizard"},
    supertypes={"Legendary"},
    text="At the beginning of combat on your turn, choose one —\n• Cloak a card from your hand. (Put it onto the battlefield face down as a 2/2 creature with ward {2}. Turn it face up any time for its mana cost if it's a creature card.)\n• Put a +1/+1 counter on each colorless creature you control.",
)

WARLEADERS_CALL = make_enchantment(
    name="Warleader's Call",
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Creatures you control get +1/+1.\nWhenever a creature you control enters, this enchantment deals 1 damage to each opponent.",
    setup_interceptors=warleaders_call_setup
)

WISPDRINKER_VAMPIRE = make_creature(
    name="Wispdrinker Vampire",
    power=2, toughness=4,
    mana_cost="{2}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Rogue", "Vampire"},
    text="Flying\nWhenever another creature you control with power 2 or less enters, each opponent loses 1 life and you gain 1 life.\n{5}{W}{B}: Creatures you control with power 2 or less gain deathtouch and lifelink until end of turn.",
    setup_interceptors=wispdrinker_vampire_setup
)

WORLDSOULS_RAGE = make_sorcery(
    name="Worldsoul's Rage",
    mana_cost="{X}{R}{G}",
    colors={Color.GREEN, Color.RED},
    text="Worldsoul's Rage deals X damage to any target. Put up to X land cards from your hand and/or graveyard onto the battlefield tapped.",
)

YARUS_ROAR_OF_THE_OLD_GODS = make_creature(
    name="Yarus, Roar of the Old Gods",
    power=4, toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Centaur", "Druid"},
    supertypes={"Legendary"},
    text="Other creatures you control have haste.\nWhenever one or more face-down creatures you control deal combat damage to a player, draw a card.\nWhenever a face-down creature you control dies, return it to the battlefield face down under its owner's control if it's a permanent card, then turn it face up.",
    setup_interceptors=yarus_setup
)

CEASE = make_instant(
    name="Cease",
    mana_cost="{1}{B/G} // {4}{G/W}{G/W}",
    colors={Color.BLACK, Color.GREEN, Color.WHITE},
    text="",
)

FLOTSAM = make_instant(
    name="Flotsam",
    mana_cost="{1}{G/U} // {4}{U/B}{U/B}",
    colors={Color.BLACK, Color.GREEN, Color.BLUE},
    text="",
)

FUSS = make_instant(
    name="Fuss",
    mana_cost="{2}{R/W} // {4}{W/U}{W/U}",
    colors={Color.RED, Color.BLUE, Color.WHITE},
    text="",
)

HUSTLE = make_instant(
    name="Hustle",
    mana_cost="{U/R} // {4}{R/G}{R/G}",
    colors={Color.GREEN, Color.RED, Color.BLUE},
    text="",
)

PUSH = make_sorcery(
    name="Push",
    mana_cost="{1}{W/B} // {4}{B/R}{B/R}",
    colors={Color.BLACK, Color.RED, Color.WHITE},
    text="",
)

CRYPTEX = make_artifact(
    name="Cryptex",
    mana_cost="{2}",
    text="{T}, Collect evidence 3: Add one mana of any color. Put an unlock counter on this artifact. (To collect evidence 3, exile cards with total mana value 3 or greater from your graveyard.)\nSacrifice this artifact: Surveil 3, then draw three cards. Activate only if this artifact has five or more unlock counters on it.",
)

GRAVESTONE_STRIDER = make_artifact_creature(
    name="Gravestone Strider",
    power=1, toughness=3,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Golem"},
    text="{1}: Add one mana of any color. Activate only once each turn.\n{2}, Exile this card from your graveyard: Exile target card from a graveyard.",
)

LUMBERING_LAUNDRY = make_artifact_creature(
    name="Lumbering Laundry",
    power=4, toughness=5,
    mana_cost="{5}",
    colors=set(),
    subtypes={"Golem"},
    text="{2}: Until end of turn, you may look at face-down creatures you don't control any time.\nDisguise {5} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)",
)

MAGNETIC_SNUFFLER = make_artifact_creature(
    name="Magnetic Snuffler",
    power=4, toughness=4,
    mana_cost="{5}",
    colors=set(),
    subtypes={"Construct"},
    text="When this creature enters, return target Equipment card from your graveyard to the battlefield attached to this creature.\nWhenever you sacrifice an artifact, put a +1/+1 counter on this creature.",
    setup_interceptors=magnetic_snuffler_setup
)

MAGNIFYING_GLASS = make_artifact(
    name="Magnifying Glass",
    mana_cost="{3}",
    text="{T}: Add {C}.\n{4}, {T}: Investigate. (Create a Clue token. It's an artifact with \"{2}, Sacrifice this token: Draw a card.\")",
)

SANITATION_AUTOMATON = make_artifact_creature(
    name="Sanitation Automaton",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Construct"},
    text="When this creature enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    setup_interceptors=sanitation_automaton_setup
)

THINKING_CAP = make_artifact(
    name="Thinking Cap",
    mana_cost="{1}",
    text="Equipped creature gets +1/+2.\nEquip Detective {1}\nEquip {3} ({3}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

BRANCH_OF_VITUGHAZI = make_land(
    name="Branch of Vitu-Ghazi",
    text="{T}: Add {C}.\nDisguise {3} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this land is turned face up, add two mana of any one color. Until end of turn, you don't lose this mana as steps and phases end.",
)

COMMERCIAL_DISTRICT = make_land(
    name="Commercial District",
    text="({T}: Add {R} or {G}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Forest", "Mountain"},
)

ELEGANT_PARLOR = make_land(
    name="Elegant Parlor",
    text="({T}: Add {R} or {W}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Mountain", "Plains"},
)

ESCAPE_TUNNEL = make_land(
    name="Escape Tunnel",
    text="{T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\n{T}, Sacrifice this land: Target creature with power 2 or less can't be blocked this turn.",
)

HEDGE_MAZE = make_land(
    name="Hedge Maze",
    text="({T}: Add {G} or {U}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Forest", "Island"},
)

LUSH_PORTICO = make_land(
    name="Lush Portico",
    text="({T}: Add {G} or {W}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Forest", "Plains"},
)

METICULOUS_ARCHIVE = make_land(
    name="Meticulous Archive",
    text="({T}: Add {W} or {U}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Island", "Plains"},
)

PUBLIC_THOROUGHFARE = make_land(
    name="Public Thoroughfare",
    text="This land enters tapped.\nWhen this land enters, sacrifice it unless you tap an untapped artifact or land you control.\n{T}: Add one mana of any color.",
)

RAUCOUS_THEATER = make_land(
    name="Raucous Theater",
    text="({T}: Add {B} or {R}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Mountain", "Swamp"},
)

SCENE_OF_THE_CRIME = make_artifact(
    name="Scene of the Crime",
    mana_cost="",
    text="This land enters tapped.\n{T}: Add {C}.\n{T}, Tap an untapped creature you control: Add one mana of any color.\n{2}, Sacrifice this land: Draw a card.",
    subtypes={"Clue"},
)

SHADOWY_BACKSTREET = make_land(
    name="Shadowy Backstreet",
    text="({T}: Add {W} or {B}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Plains", "Swamp"},
)

THUNDERING_FALLS = make_land(
    name="Thundering Falls",
    text="({T}: Add {U} or {R}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Island", "Mountain"},
)

UNDERCITY_SEWERS = make_land(
    name="Undercity Sewers",
    text="({T}: Add {U} or {B}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Island", "Swamp"},
)

UNDERGROUND_MORTUARY = make_land(
    name="Underground Mortuary",
    text="({T}: Add {B} or {G}.)\nThis land enters tapped.\nWhen this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    subtypes={"Forest", "Swamp"},
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

MELEK_REFORGED_RESEARCHER = make_creature(
    name="Melek, Reforged Researcher",
    power=0, toughness=0,
    mana_cost="{3}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Detective", "Weird"},
    supertypes={"Legendary"},
    text="Melek's power and toughness are each equal to twice the number of instant and sorcery cards in your graveyard.\nThe first instant or sorcery spell you cast each turn costs {3} less to cast.",
)

TOMIK_WIELDER_OF_LAW = make_creature(
    name="Tomik, Wielder of Law",
    power=2, toughness=4,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Advisor", "Human"},
    supertypes={"Legendary"},
    text="Affinity for planeswalkers (This spell costs {1} less to cast for each planeswalker you control.)\nFlying, vigilance\nWhenever an opponent attacks with creatures, if two or more of those creatures are attacking you and/or planeswalkers you control, that opponent loses 3 life and you draw a card.",
)

VOJA_JAWS_OF_THE_CONCLAVE = make_creature(
    name="Voja, Jaws of the Conclave",
    power=5, toughness=5,
    mana_cost="{2}{R}{G}{W}",
    colors={Color.GREEN, Color.RED, Color.WHITE},
    subtypes={"Wolf"},
    supertypes={"Legendary"},
    text="Vigilance, trample, ward {3}\nWhenever Voja attacks, put X +1/+1 counters on each creature you control, where X is the number of Elves you control. Draw a card for each Wolf you control.",
)

# =============================================================================
# CARD REGISTRY
# =============================================================================

MURDERS_KARLOV_MANOR_CARDS = {
    "Case of the Shattered Pact": CASE_OF_THE_SHATTERED_PACT,
    "Absolving Lammasu": ABSOLVING_LAMMASU,
    "Assemble the Players": ASSEMBLE_THE_PLAYERS,
    "Aurelia's Vindicator": AURELIAS_VINDICATOR,
    "Auspicious Arrival": AUSPICIOUS_ARRIVAL,
    "Call a Surprise Witness": CALL_A_SURPRISE_WITNESS,
    "Case File Auditor": CASE_FILE_AUDITOR,
    "Case of the Gateway Express": CASE_OF_THE_GATEWAY_EXPRESS,
    "Case of the Pilfered Proof": CASE_OF_THE_PILFERED_PROOF,
    "Case of the Uneaten Feast": CASE_OF_THE_UNEATEN_FEAST,
    "Defenestrated Phantom": DEFENESTRATED_PHANTOM,
    "Delney, Streetwise Lookout": DELNEY_STREETWISE_LOOKOUT,
    "Doorkeeper Thrull": DOORKEEPER_THRULL,
    "Due Diligence": DUE_DILIGENCE,
    "Essence of Antiquity": ESSENCE_OF_ANTIQUITY,
    "Forum Familiar": FORUM_FAMILIAR,
    "Griffnaut Tracker": GRIFFNAUT_TRACKER,
    "Haazda Vigilante": HAAZDA_VIGILANTE,
    "Inside Source": INSIDE_SOURCE,
    "Karlov Watchdog": KARLOV_WATCHDOG,
    "Krovod Haunch": KROVOD_HAUNCH,
    "Make Your Move": MAKE_YOUR_MOVE,
    "Makeshift Binding": MAKESHIFT_BINDING,
    "Marketwatch Phantom": MARKETWATCH_PHANTOM,
    "Museum Nightwatch": MUSEUM_NIGHTWATCH,
    "Neighborhood Guardian": NEIGHBORHOOD_GUARDIAN,
    "No Witnesses": NO_WITNESSES,
    "Not on My Watch": NOT_ON_MY_WATCH,
    "Novice Inspector": NOVICE_INSPECTOR,
    "On the Job": ON_THE_JOB,
    "Perimeter Enforcer": PERIMETER_ENFORCER,
    "Sanctuary Wall": SANCTUARY_WALL,
    "Seasoned Consultant": SEASONED_CONSULTANT,
    "Tenth District Hero": TENTH_DISTRICT_HERO,
    "Unyielding Gatekeeper": UNYIELDING_GATEKEEPER,
    "Wojek Investigator": WOJEK_INVESTIGATOR,
    "Wrench": WRENCH,
    "Agency Outfitter": AGENCY_OUTFITTER,
    "Behind the Mask": BEHIND_THE_MASK,
    "Benthic Criminologists": BENTHIC_CRIMINOLOGISTS,
    "Bubble Smuggler": BUBBLE_SMUGGLER,
    "Burden of Proof": BURDEN_OF_PROOF,
    "Candlestick": CANDLESTICK,
    "Case of the Filched Falcon": CASE_OF_THE_FILCHED_FALCON,
    "Case of the Ransacked Lab": CASE_OF_THE_RANSACKED_LAB,
    "Cold Case Cracker": COLD_CASE_CRACKER,
    "Conspiracy Unraveler": CONSPIRACY_UNRAVELER,
    "Coveted Falcon": COVETED_FALCON,
    "Crimestopper Sprite": CRIMESTOPPER_SPRITE,
    "Cryptic Coat": CRYPTIC_COAT,
    "Curious Inquiry": CURIOUS_INQUIRY,
    "Deduce": DEDUCE,
    "Dramatic Accusation": DRAMATIC_ACCUSATION,
    "Eliminate the Impossible": ELIMINATE_THE_IMPOSSIBLE,
    "Exit Specialist": EXIT_SPECIALIST,
    "Fae Flight": FAE_FLIGHT,
    "Forensic Gadgeteer": FORENSIC_GADGETEER,
    "Forensic Researcher": FORENSIC_RESEARCHER,
    "Furtive Courier": FURTIVE_COURIER,
    "Hotshot Investigators": HOTSHOT_INVESTIGATORS,
    "Intrude on the Mind": INTRUDE_ON_THE_MIND,
    "Jaded Analyst": JADED_ANALYST,
    "Living Conundrum": LIVING_CONUNDRUM,
    "Lost in the Maze": LOST_IN_THE_MAZE,
    "Mistway Spy": MISTWAY_SPY,
    "Out Cold": OUT_COLD,
    "Proft's Eidetic Memory": PROFTS_EIDETIC_MEMORY,
    "Projektor Inspector": PROJEKTOR_INSPECTOR,
    "Reasonable Doubt": REASONABLE_DOUBT,
    "Reenact the Crime": REENACT_THE_CRIME,
    "Steamcore Scholar": STEAMCORE_SCHOLAR,
    "Sudden Setback": SUDDEN_SETBACK,
    "Surveillance Monitor": SURVEILLANCE_MONITOR,
    "Unauthorized Exit": UNAUTHORIZED_EXIT,
    "Agency Coroner": AGENCY_CORONER,
    "Alley Assailant": ALLEY_ASSAILANT,
    "Barbed Servitor": BARBED_SERVITOR,
    "Basilica Stalker": BASILICA_STALKER,
    "Case of the Gorgon's Kiss": CASE_OF_THE_GORGONS_KISS,
    "Case of the Stashed Skeleton": CASE_OF_THE_STASHED_SKELETON,
    "Cerebral Confiscation": CEREBRAL_CONFISCATION,
    "Clandestine Meddler": CLANDESTINE_MEDDLER,
    "Deadly Cover-Up": DEADLY_COVERUP,
    "Extract a Confession": EXTRACT_A_CONFESSION,
    "Festerleech": FESTERLEECH,
    "Homicide Investigator": HOMICIDE_INVESTIGATOR,
    "Hunted Bonebrute": HUNTED_BONEBRUTE,
    "Illicit Masquerade": ILLICIT_MASQUERADE,
    "It Doesn't Add Up": IT_DOESNT_ADD_UP,
    "Lead Pipe": LEAD_PIPE,
    "Leering Onlooker": LEERING_ONLOOKER,
    "Long Goodbye": LONG_GOODBYE,
    "Macabre Reconstruction": MACABRE_RECONSTRUCTION,
    "Massacre Girl, Known Killer": MASSACRE_GIRL_KNOWN_KILLER,
    "Murder": MURDER,
    "Nightdrinker Moroii": NIGHTDRINKER_MOROII,
    "Outrageous Robbery": OUTRAGEOUS_ROBBERY,
    "Persuasive Interrogators": PERSUASIVE_INTERROGATORS,
    "Polygraph Orb": POLYGRAPH_ORB,
    "Presumed Dead": PRESUMED_DEAD,
    "Repeat Offender": REPEAT_OFFENDER,
    "Rot Farm Mortipede": ROT_FARM_MORTIPEDE,
    "Slice from the Shadows": SLICE_FROM_THE_SHADOWS,
    "Slimy Dualleech": SLIMY_DUALLEECH,
    "Snarling Gorehound": SNARLING_GOREHOUND,
    "Soul Enervation": SOUL_ENERVATION,
    "Toxin Analysis": TOXIN_ANALYSIS,
    "Undercity Eliminator": UNDERCITY_ELIMINATOR,
    "Unscrupulous Agent": UNSCRUPULOUS_AGENT,
    "Vein Ripper": VEIN_RIPPER,
    "Anzrag's Rampage": ANZRAGS_RAMPAGE,
    "Bolrac-Clan Basher": BOLRACCLAN_BASHER,
    "Case of the Burning Masks": CASE_OF_THE_BURNING_MASKS,
    "Case of the Crimson Pulse": CASE_OF_THE_CRIMSON_PULSE,
    "Caught Red-Handed": CAUGHT_REDHANDED,
    "The Chase Is On": THE_CHASE_IS_ON,
    "Concealed Weapon": CONCEALED_WEAPON,
    "Connecting the Dots": CONNECTING_THE_DOTS,
    "Convenient Target": CONVENIENT_TARGET,
    "Cornered Crook": CORNERED_CROOK,
    "Crime Novelist": CRIME_NOVELIST,
    "Demand Answers": DEMAND_ANSWERS,
    "Expedited Inheritance": EXPEDITED_INHERITANCE,
    "Expose the Culprit": EXPOSE_THE_CULPRIT,
    "Felonious Rage": FELONIOUS_RAGE,
    "Frantic Scapegoat": FRANTIC_SCAPEGOAT,
    "Fugitive Codebreaker": FUGITIVE_CODEBREAKER,
    "Galvanize": GALVANIZE,
    "Gearbane Orangutan": GEARBANE_ORANGUTAN,
    "Goblin Maskmaker": GOBLIN_MASKMAKER,
    "Harried Dronesmith": HARRIED_DRONESMITH,
    "Incinerator of the Guilty": INCINERATOR_OF_THE_GUILTY,
    "Innocent Bystander": INNOCENT_BYSTANDER,
    "Knife": KNIFE,
    "Krenko, Baron of Tin Street": KRENKO_BARON_OF_TIN_STREET,
    "Krenko's Buzzcrusher": KRENKOS_BUZZCRUSHER,
    "Lamplight Phoenix": LAMPLIGHT_PHOENIX,
    "Offender at Large": OFFENDER_AT_LARGE,
    "Person of Interest": PERSON_OF_INTEREST,
    "Pyrotechnic Performer": PYROTECHNIC_PERFORMER,
    "Reckless Detective": RECKLESS_DETECTIVE,
    "Red Herring": RED_HERRING,
    "Rubblebelt Braggart": RUBBLEBELT_BRAGGART,
    "Shock": SHOCK,
    "Suspicious Detonation": SUSPICIOUS_DETONATION,
    "Torch the Witness": TORCH_THE_WITNESS,
    "Vengeful Tracker": VENGEFUL_TRACKER,
    "Aftermath Analyst": AFTERMATH_ANALYST,
    "Airtight Alibi": AIRTIGHT_ALIBI,
    "Analyze the Pollen": ANALYZE_THE_POLLEN,
    "Archdruid's Charm": ARCHDRUIDS_CHARM,
    "Audience with Trostani": AUDIENCE_WITH_TROSTANI,
    "Axebane Ferox": AXEBANE_FEROX,
    "Bite Down on Crime": BITE_DOWN_ON_CRIME,
    "Case of the Locked Hothouse": CASE_OF_THE_LOCKED_HOTHOUSE,
    "Case of the Trampled Garden": CASE_OF_THE_TRAMPLED_GARDEN,
    "Chalk Outline": CHALK_OUTLINE,
    "Culvert Ambusher": CULVERT_AMBUSHER,
    "Fanatical Strength": FANATICAL_STRENGTH,
    "Flourishing Bloom-Kin": FLOURISHING_BLOOMKIN,
    "Get a Leg Up": GET_A_LEG_UP,
    "Glint Weaver": GLINT_WEAVER,
    "Greenbelt Radical": GREENBELT_RADICAL,
    "Hard-Hitting Question": HARDHITTING_QUESTION,
    "Hedge Whisperer": HEDGE_WHISPERER,
    "Hide in Plain Sight": HIDE_IN_PLAIN_SIGHT,
    "A Killer Among Us": A_KILLER_AMONG_US,
    "Loxodon Eavesdropper": LOXODON_EAVESDROPPER,
    "Nervous Gardener": NERVOUS_GARDENER,
    "Pick Your Poison": PICK_YOUR_POISON,
    "Pompous Gadabout": POMPOUS_GADABOUT,
    "The Pride of Hull Clade": THE_PRIDE_OF_HULL_CLADE,
    "Rope": ROPE,
    "Rubblebelt Maverick": RUBBLEBELT_MAVERICK,
    "Sample Collector": SAMPLE_COLLECTOR,
    "Sharp-Eyed Rookie": SHARPEYED_ROOKIE,
    "Slime Against Humanity": SLIME_AGAINST_HUMANITY,
    "They Went This Way": THEY_WENT_THIS_WAY,
    "Topiary Panther": TOPIARY_PANTHER,
    "Tunnel Tipster": TUNNEL_TIPSTER,
    "Undergrowth Recon": UNDERGROWTH_RECON,
    "Vengeful Creeper": VENGEFUL_CREEPER,
    "Vitu-Ghazi Inspector": VITUGHAZI_INSPECTOR,
    "Agrus Kos, Spirit of Justice": AGRUS_KOS_SPIRIT_OF_JUSTICE,
    "Alquist Proft, Master Sleuth": ALQUIST_PROFT_MASTER_SLEUTH,
    "Anzrag, the Quake-Mole": ANZRAG_THE_QUAKEMOLE,
    "Assassin's Trophy": ASSASSINS_TROPHY,
    "Aurelia, the Law Above": AURELIA_THE_LAW_ABOVE,
    "Blood Spatter Analysis": BLOOD_SPATTER_ANALYSIS,
    "Break Out": BREAK_OUT,
    "Buried in the Garden": BURIED_IN_THE_GARDEN,
    "Coerced to Kill": COERCED_TO_KILL,
    "Crowd-Control Warden": CROWDCONTROL_WARDEN,
    "Curious Cadaver": CURIOUS_CADAVER,
    "Deadly Complication": DEADLY_COMPLICATION,
    "Detective's Satchel": DETECTIVES_SATCHEL,
    "Dog Walker": DOG_WALKER,
    "Doppelgang": DOPPELGANG,
    "Drag the Canal": DRAG_THE_CANAL,
    "Etrata, Deadly Fugitive": ETRATA_DEADLY_FUGITIVE,
    "Evidence Examiner": EVIDENCE_EXAMINER,
    "Ezrim, Agency Chief": EZRIM_AGENCY_CHIEF,
    "Faerie Snoop": FAERIE_SNOOP,
    "Gadget Technician": GADGET_TECHNICIAN,
    "Gleaming Geardrake": GLEAMING_GEARDRAKE,
    "Granite Witness": GRANITE_WITNESS,
    "Ill-Timed Explosion": ILLTIMED_EXPLOSION,
    "Insidious Roots": INSIDIOUS_ROOTS,
    "Izoni, Center of the Web": IZONI_CENTER_OF_THE_WEB,
    "Judith, Carnage Connoisseur": JUDITH_CARNAGE_CONNOISSEUR,
    "Kaya, Spirits' Justice": KAYA_SPIRITS_JUSTICE,
    "Kellan, Inquisitive Prodigy": KELLAN_INQUISITIVE_PRODIGY,
    "Kraul Whipcracker": KRAUL_WHIPCRACKER,
    "Kylox, Visionary Inventor": KYLOX_VISIONARY_INVENTOR,
    "Kylox's Voltstrider": KYLOXS_VOLTSTRIDER,
    "Lazav, Wearer of Faces": LAZAV_WEARER_OF_FACES,
    "Leyline of the Guildpact": LEYLINE_OF_THE_GUILDPACT,
    "Lightning Helix": LIGHTNING_HELIX,
    "Meddling Youths": MEDDLING_YOUTHS,
    "Niv-Mizzet, Guildpact": NIVMIZZET_GUILDPACT,
    "No More Lies": NO_MORE_LIES,
    "Officious Interrogation": OFFICIOUS_INTERROGATION,
    "Private Eye": PRIVATE_EYE,
    "Rakdos, Patron of Chaos": RAKDOS_PATRON_OF_CHAOS,
    "Rakish Scoundrel": RAKISH_SCOUNDREL,
    "Relive the Past": RELIVE_THE_PAST,
    "Repulsive Mutation": REPULSIVE_MUTATION,
    "Riftburst Hellion": RIFTBURST_HELLION,
    "Rune-Brand Juggler": RUNEBRAND_JUGGLER,
    "Sanguine Savior": SANGUINE_SAVIOR,
    "Shady Informant": SHADY_INFORMANT,
    "Soul Search": SOUL_SEARCH,
    "Sumala Sentry": SUMALA_SENTRY,
    "Teysa, Opulent Oligarch": TEYSA_OPULENT_OLIGARCH,
    "Tin Street Gossip": TIN_STREET_GOSSIP,
    "Tolsimir, Midnight's Light": TOLSIMIR_MIDNIGHTS_LIGHT,
    "Treacherous Greed": TREACHEROUS_GREED,
    "Trostani, Three Whispers": TROSTANI_THREE_WHISPERS,
    "Undercover Crocodelf": UNDERCOVER_CROCODELF,
    "Urgent Necropsy": URGENT_NECROPSY,
    "Vannifar, Evolved Enigma": VANNIFAR_EVOLVED_ENIGMA,
    "Warleader's Call": WARLEADERS_CALL,
    "Wispdrinker Vampire": WISPDRINKER_VAMPIRE,
    "Worldsoul's Rage": WORLDSOULS_RAGE,
    "Yarus, Roar of the Old Gods": YARUS_ROAR_OF_THE_OLD_GODS,
    "Cease": CEASE,
    "Flotsam": FLOTSAM,
    "Fuss": FUSS,
    "Hustle": HUSTLE,
    "Push": PUSH,
    "Cryptex": CRYPTEX,
    "Gravestone Strider": GRAVESTONE_STRIDER,
    "Lumbering Laundry": LUMBERING_LAUNDRY,
    "Magnetic Snuffler": MAGNETIC_SNUFFLER,
    "Magnifying Glass": MAGNIFYING_GLASS,
    "Sanitation Automaton": SANITATION_AUTOMATON,
    "Thinking Cap": THINKING_CAP,
    "Branch of Vitu-Ghazi": BRANCH_OF_VITUGHAZI,
    "Commercial District": COMMERCIAL_DISTRICT,
    "Elegant Parlor": ELEGANT_PARLOR,
    "Escape Tunnel": ESCAPE_TUNNEL,
    "Hedge Maze": HEDGE_MAZE,
    "Lush Portico": LUSH_PORTICO,
    "Meticulous Archive": METICULOUS_ARCHIVE,
    "Public Thoroughfare": PUBLIC_THOROUGHFARE,
    "Raucous Theater": RAUCOUS_THEATER,
    "Scene of the Crime": SCENE_OF_THE_CRIME,
    "Shadowy Backstreet": SHADOWY_BACKSTREET,
    "Thundering Falls": THUNDERING_FALLS,
    "Undercity Sewers": UNDERCITY_SEWERS,
    "Underground Mortuary": UNDERGROUND_MORTUARY,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
    "Melek, Reforged Researcher": MELEK_REFORGED_RESEARCHER,
    "Tomik, Wielder of Law": TOMIK_WIELDER_OF_LAW,
    "Voja, Jaws of the Conclave": VOJA_JAWS_OF_THE_CONCLAVE,
}

print(f"Loaded {len(MURDERS_KARLOV_MANOR_CARDS)} Murders_at_Karlov_Manor cards")
