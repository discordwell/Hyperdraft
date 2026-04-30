"""
Edge_of_Eternities (EOE) Card Implementations

Real card data fetched from Scryfall API.
266 cards in set.
"""

from src.cards.card_factories import (
    make_artifact,
    make_artifact_creature,
    make_instant,
    make_land,
    make_planeswalker,
    make_sorcery,
)

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
    make_end_step_trigger, make_life_gain_trigger, make_tap_trigger,
    make_spell_cast_trigger, make_damage_trigger,
    make_leaves_battlefield_trigger,
    make_warp_setup,
    other_creatures_you_control, other_creatures_with_subtype,
    creatures_you_control, all_opponents,
    open_library_search,
    make_void_end_step_trigger, make_void_attack_trigger, is_void_active,
    make_lander_etb_trigger, make_lander_death_trigger,
    make_station_creature_setup,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# =============================================================================
# INTERCEPTOR SETUP FUNCTIONS
# =============================================================================

# -----------------------------------------------------------------------------
# WHITE CREATURE INTERCEPTORS
# -----------------------------------------------------------------------------

def honored_knightcaptain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a 1/1 white Human Soldier creature token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Human Soldier Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Human', 'Soldier'],
                'colors': [Color.WHITE]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def knight_luminary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a 1/1 white Human Soldier creature token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Human Soldier Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Human', 'Soldier'],
                'colors': [Color.WHITE]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def dockworker_drone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """This creature enters with a +1/+1 counter on it. When dies, put counters on target."""
    interceptors = []

    # ETB: enters with +1/+1 counter
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Death trigger (counter transfer would require target selection)
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Target selection required
    interceptors.append(make_death_trigger(obj, death_effect))

    return interceptors


def rayblade_trooper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, put +1/+1 counter on target creature you control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need target selection - creates counter event for self as placeholder
        return []  # Target selection required
    return [make_etb_trigger(obj, etb_effect)]


def weftblade_enhancer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, put +1/+1 counter on each of up to two target creatures."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Target selection required
    return [make_etb_trigger(obj, etb_effect)]


def haliya_guided_by_light_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever Haliya or another creature or artifact enters, gain 1 life."""
    def etb_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller != source_obj.controller:
            return False
        # Must be creature or artifact
        types = entering_obj.characteristics.types
        return CardType.CREATURE in types or CardType.ARTIFACT in types

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    return [make_etb_trigger(obj, etb_effect, filter_fn=etb_filter)]


def flightdeck_coordinator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your end step, if you control two or more tapped creatures, gain 2 life."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        # Count tapped creatures you control
        tapped_count = sum(1 for o in state.objects.values()
                         if o.controller == obj.controller
                         and CardType.CREATURE in o.characteristics.types
                         and o.zone == ZoneType.BATTLEFIELD
                         and o.state.tapped)
        if tapped_count >= 2:
            return [Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id
            )]
        return []
    return [make_end_step_trigger(obj, end_step_effect)]


def wedgelight_rammer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, create a 2/2 colorless Robot artifact creature token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Robot Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.ARTIFACT, CardType.CREATURE],
                'subtypes': ['Robot'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def auxiliary_boosters_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, create a 2/2 Robot token and attach this Equipment to it."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Robot Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.ARTIFACT, CardType.CREATURE],
                'subtypes': ['Robot'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# BLUE CREATURE INTERCEPTORS
# -----------------------------------------------------------------------------

def codecracker_hound_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, look at top two cards, put one in hand, one in graveyard."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def quantum_riddler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, draw a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def mouth_of_the_storm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, creatures opponents control get -3/-0 until your next turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need to create temporary P/T modifying interceptors
        return []
    return [make_etb_trigger(obj, etb_effect)]


def mechanozoa_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, tap target artifact or creature and put a stun counter on it."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Target selection required
    return [make_etb_trigger(obj, etb_effect)]


def sinister_cryologist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, target creature opponent controls gets -3/-0 until end of turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Target selection required
    return [make_etb_trigger(obj, etb_effect)]


def starbreach_whale_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, surveil 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def mechan_assembler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another artifact you control enters, create a 2/2 Robot token (once per turn)."""
    triggered_this_turn = [False]

    def artifact_etb_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if triggered_this_turn[0]:
            return False
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj or entering_id == source_obj.id:
            return False
        return (entering_obj.controller == source_obj.controller and
                CardType.ARTIFACT in entering_obj.characteristics.types)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        triggered_this_turn[0] = True
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Robot Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.ARTIFACT, CardType.CREATURE],
                'subtypes': ['Robot'],
                'colors': []
            },
            source=obj.id
        )]

    return [make_etb_trigger(obj, effect_fn, filter_fn=artifact_etb_filter)]


def mechan_navigator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature becomes tapped, draw a card, then discard a card."""
    def tap_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_tap_trigger(obj, tap_effect)]


def illvoi_infiltrator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature deals combat damage to a player, draw a card."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]


def uthros_scanship_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, draw two cards, then discard a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 2}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]


def cryogen_relic_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters or leaves, draw a card."""
    interceptors = []

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Leave trigger would need special handling
    return interceptors


# -----------------------------------------------------------------------------
# BLACK CREATURE INTERCEPTORS
# -----------------------------------------------------------------------------

def virus_beetle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, each opponent discards a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DISCARD,
                    payload={'player': player_id, 'amount': 1},
                    source=obj.id
                ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def beamsaw_prospector_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies, create a Lander token."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Lander Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Lander'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def gravpack_monoist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies, create a tapped 2/2 Robot token."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Robot Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.ARTIFACT, CardType.CREATURE],
                'subtypes': ['Robot'],
                'colors': [],
                'tapped': True
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def susurian_voidborn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this or another creature/artifact you control dies, opponent loses 1 life, you gain 1."""
    def death_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying_obj = state.objects.get(dying_id)
        if not dying_obj:
            return False
        if dying_obj.controller != source_obj.controller:
            return False
        types = dying_obj.characteristics.types
        return CardType.CREATURE in types or CardType.ARTIFACT in types

    def death_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -1},
                    source=obj.id
                ))
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        ))
        return events

    return [make_death_trigger(obj, death_effect, filter_fn=death_filter)]


def lightless_evangel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you sacrifice another creature or artifact, put a +1/+1 counter on this."""
    def sacrifice_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        if event.payload.get('cause') != 'sacrifice':
            return False
        sacrificed_id = event.payload.get('object_id')
        sacrificed_obj = state.objects.get(sacrificed_id)
        if not sacrificed_obj or sacrificed_id == obj.id:
            return False
        if sacrificed_obj.controller != obj.controller:
            return False
        types = sacrificed_obj.characteristics.types
        return CardType.CREATURE in types or CardType.ARTIFACT in types

    def sacrifice_effect(event: Event, state: GameState) -> list[Event]:
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
        filter=sacrifice_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=sacrifice_effect(e, s)),
        duration='while_on_battlefield'
    )]


def fell_gravship_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, mill 3, then return creature/Spacecraft from graveyard to hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def monoist_circuitfeeder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, target creature you control gets +X/+0, target opponent creature gets -0/-X."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Target selection required
    return [make_etb_trigger(obj, etb_effect)]


def elegy_acolyte_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever one or more creatures deal combat damage to player, draw a card, lose 1 life."""
    def damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('is_combat'):
            return False
        source_id = event.payload.get('source')
        source_obj = state.objects.get(source_id)
        if not source_obj:
            return False
        if source_obj.controller != obj.controller:
            return False
        if CardType.CREATURE not in source_obj.characteristics.types:
            return False
        target_id = event.payload.get('target')
        return target_id in state.players  # Damage to a player

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': -1}, source=obj.id)
        ]

    # Void EOT: create a 2/2 colorless Robot artifact creature token.
    def void_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Robot Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT, CardType.CREATURE],
                'subtypes': ['Robot'],
                'colors': [],
                'power': 2,
                'toughness': 2,
                'is_token': True,
            },
            source=obj.id,
        )]

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=damage_filter,
            handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=damage_effect(e, s)),
            duration='while_on_battlefield',
        ),
        make_void_end_step_trigger(obj, void_effect),
    ]


# -----------------------------------------------------------------------------
# RED CREATURE INTERCEPTORS
# -----------------------------------------------------------------------------

def nebula_dragon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, deal 3 damage to any target."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Target selection required
    return [make_etb_trigger(obj, etb_effect)]


def nova_hellkite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, deal 1 damage to target creature opponent controls."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Target selection required
    return [make_etb_trigger(obj, etb_effect)]


def debris_field_crusher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, deal 3 damage to any target."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Target selection required
    return [make_etb_trigger(obj, etb_effect)]


def kav_landseeker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, create a Lander token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Lander Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Lander'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def melded_moxite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, you may discard a card. If you do, draw two cards."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified: just the draw effect (choice system required)
        return []
    return [make_etb_trigger(obj, etb_effect)]


def memorial_team_leader_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """During your turn, other creatures you control get +1/+0."""
    def affects_filter(target: GameObject, state: GameState) -> bool:
        if target.id == obj.id:
            return False
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        # Only during your turn
        return state.active_player == obj.controller

    return make_static_pt_boost(obj, 1, 0, affects_filter)


def tannuk_steadfast_second_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other creatures you control have haste."""
    def affects_filter(target: GameObject, state: GameState) -> bool:
        return (target.id != obj.id and
                target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)

    return [make_keyword_grant(obj, ['haste'], affects_filter)]


def warmaker_gunship_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, deal damage equal to artifacts you control to target creature opponent controls."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Target selection required
    return [make_etb_trigger(obj, etb_effect)]


def weftstalker_ardent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another creature or artifact enters, deal 1 damage to each opponent."""
    def etb_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj or entering_id == source_obj.id:
            return False
        if entering_obj.controller != source_obj.controller:
            return False
        types = entering_obj.characteristics.types
        return CardType.CREATURE in types or CardType.ARTIFACT in types

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 1, 'source': obj.id},
                    source=obj.id
                ))
        return events

    return [make_etb_trigger(obj, effect_fn, filter_fn=etb_filter)]


def molecular_modifier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At beginning of combat, target creature gets +1/+0 and first strike until end of turn."""
    def combat_start_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.PHASE_START and
                event.payload.get('phase') == 'combat' and
                state.active_player == obj.controller)

    def combat_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Target selection required

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_start_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=combat_effect(e, s)),
        duration='while_on_battlefield'
    )]


# -----------------------------------------------------------------------------
# GREEN CREATURE INTERCEPTORS
# -----------------------------------------------------------------------------

def galactic_wayfarer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, create a Lander token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Lander Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Lander'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def biomechan_engineer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, create a Lander token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Lander Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Lander'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def biotech_specialist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, create a Lander token. Whenever sacrifice artifact, deal 2 to opponent."""
    interceptors = []

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Lander Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Lander'],
                'colors': []
            },
            source=obj.id
        )]
    interceptors.append(make_etb_trigger(obj, etb_effect))

    return interceptors


def germinating_wurm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, gain 2 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def blooming_stinger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, another target creature you control gains deathtouch until end of turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Target selection required
    return [make_etb_trigger(obj, etb_effect)]


def drix_fatemaker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, put a +1/+1 counter on target creature. Each creature with counter has trample."""
    interceptors = []

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Target selection required
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Grant trample to creatures with +1/+1 counters
    def trample_filter(target: GameObject, state: GameState) -> bool:
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        counters = getattr(target.state, 'counters', {})
        return counters.get('+1/+1', 0) > 0

    interceptors.append(make_keyword_grant(obj, ['trample'], trample_filter))

    return interceptors


def edge_rover_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When dies, each player creates a Lander token."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Lander Token',
                    'controller': player_id,
                    'types': [CardType.ARTIFACT],
                    'subtypes': ['Lander'],
                    'colors': []
                },
                source=obj.id
            ))
        return events
    return [make_death_trigger(obj, death_effect)]


def atmospheric_greenhouse_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, put a +1/+1 counter on each creature you control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for o in state.objects.values():
            if (o.controller == obj.controller and
                CardType.CREATURE in o.characteristics.types and
                o.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': o.id, 'counter_type': '+1/+1', 'amount': 1},
                    source=obj.id
                ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def glacier_godmaw_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, create a Lander token. Landfall gives +1/+1, vigilance, haste until EOT."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Lander Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Lander'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def meltstrider_eulogist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a creature you control with +1/+1 counter dies, draw a card."""
    def death_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying_obj = state.objects.get(dying_id)
        if not dying_obj:
            return False
        if dying_obj.controller != source_obj.controller:
            return False
        if CardType.CREATURE not in dying_obj.characteristics.types:
            return False
        counters = getattr(dying_obj.state, 'counters', {})
        return counters.get('+1/+1', 0) > 0

    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    return [make_death_trigger(obj, death_effect, filter_fn=death_filter)]


def thawbringer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters or dies, surveil 1."""
    interceptors = []

    def surveil_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    interceptors.append(make_etb_trigger(obj, surveil_effect))
    interceptors.append(make_death_trigger(obj, surveil_effect))
    return interceptors


def seedship_broodtender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, mill 3."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# MULTICOLOR/GOLD CREATURE INTERCEPTORS
# -----------------------------------------------------------------------------

def interceptor_mechan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: return target artifact/creature from GY (target gap).
    Void EOT: +1/+1 counter on this creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # engine gap: graveyard target selection

    def void_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id,
        )]

    return [
        make_etb_trigger(obj, etb_effect),
        make_void_end_step_trigger(obj, void_effect),
    ]


def mmmenon_uthros_exile_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever an artifact enters, put a +1/+1 counter on target creature."""
    def artifact_etb_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller != source_obj.controller:
            return False
        return CardType.ARTIFACT in entering_obj.characteristics.types

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # Target selection required

    return [make_etb_trigger(obj, effect_fn, filter_fn=artifact_etb_filter)]


def syr_vondam_sunstar_exemplar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another creature dies or is exiled, put +1/+1 counter on Syr Vondam, gain 1 life."""
    def death_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        to_zone = event.payload.get('to_zone_type')
        if to_zone not in (ZoneType.GRAVEYARD, ZoneType.EXILE):
            return False
        dying_id = event.payload.get('object_id')
        dying_obj = state.objects.get(dying_id)
        if not dying_obj or dying_id == source_obj.id:
            return False
        if dying_obj.controller != source_obj.controller:
            return False
        return CardType.CREATURE in dying_obj.characteristics.types

    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.COUNTER_ADDED, payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1}, source=obj.id),
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]

    return [make_death_trigger(obj, death_effect, filter_fn=death_filter)]


def syr_vondam_the_lucent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever enters or attacks, other creatures you control get +1/+0 and deathtouch until EOT."""
    interceptors = []

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Would need temporary P/T modifying interceptors
        return []

    interceptors.append(make_etb_trigger(obj, effect_fn))
    interceptors.append(make_attack_trigger(obj, effect_fn))
    return interceptors


def haliya_ascendant_cadet_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever enters or attacks, put +1/+1 counter on target creature. Draw on combat damage."""
    interceptors = []

    def etb_attack_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Target selection required

    interceptors.append(make_etb_trigger(obj, etb_attack_effect))
    interceptors.append(make_attack_trigger(obj, etb_attack_effect))
    return interceptors


def alpharael_dreaming_acolyte_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, draw two cards. Then discard two unless you discard an artifact."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 2}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 2}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]


def sami_ships_engineer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At end step, if you control two or more tapped creatures, create a 2/2 Robot token."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        tapped_count = sum(1 for o in state.objects.values()
                         if o.controller == obj.controller
                         and CardType.CREATURE in o.characteristics.types
                         and o.zone == ZoneType.BATTLEFIELD
                         and o.state.tapped)
        if tapped_count >= 2:
            return [Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Robot Token',
                    'controller': obj.controller,
                    'power': 2,
                    'toughness': 2,
                    'types': [CardType.ARTIFACT, CardType.CREATURE],
                    'subtypes': ['Robot'],
                    'colors': [],
                    'tapped': True
                },
                source=obj.id
            )]
        return []
    return [make_end_step_trigger(obj, end_step_effect)]


def station_monitor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast your second spell each turn, create a 1/1 Drone token."""
    spells_this_turn = [0]

    def spell_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source_obj.controller:
            return False
        spells_this_turn[0] += 1
        return spells_this_turn[0] == 2

    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Drone Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.ARTIFACT, CardType.CREATURE],
                'subtypes': ['Drone'],
                'colors': [],
                'abilities': ['flying']
            },
            source=obj.id
        )]

    return [make_spell_cast_trigger(obj, spell_effect)]


def pinnacle_emissary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an artifact spell, create a 1/1 Drone token."""
    def artifact_cast_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source_obj.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.ARTIFACT in spell_types

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Drone Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.ARTIFACT, CardType.CREATURE],
                'subtypes': ['Drone'],
                'colors': [],
                'abilities': ['flying']
            },
            source=obj.id
        )]

    return [make_spell_cast_trigger(obj, effect_fn)]


# -----------------------------------------------------------------------------
# COLORLESS ARTIFACT CREATURE INTERCEPTORS
# -----------------------------------------------------------------------------

def chrome_companion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever becomes tapped, gain 1 life."""
    def tap_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_tap_trigger(obj, tap_effect)]


def dauntless_scrapbot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, exile each opponent's graveyard. Create a Lander token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Lander Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Lander'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def extinguisher_battleship_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, destroy target noncreature permanent, deal 4 damage to each creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        # Deal 4 damage to each creature
        for o in state.objects.values():
            if (CardType.CREATURE in o.characteristics.types and
                o.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': o.id, 'amount': 4, 'source': obj.id},
                    source=obj.id
                ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def pinnacle_killship_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, deal 10 damage to up to one target creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Target selection required
    return [make_etb_trigger(obj, etb_effect)]


def wurmwall_sweeper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, surveil 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def virulent_silencer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a nontoken artifact creature deals combat damage to player, give 2 poison counters."""
    def damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('is_combat'):
            return False
        source_id = event.payload.get('source')
        source_obj = state.objects.get(source_id)
        if not source_obj:
            return False
        if source_obj.controller != obj.controller:
            return False
        types = source_obj.characteristics.types
        if CardType.ARTIFACT not in types or CardType.CREATURE not in types:
            return False
        if getattr(source_obj.state, 'is_token', False):
            return False
        target_id = event.payload.get('target')
        return target_id in state.players

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target_id = event.payload.get('target')
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'player': target_id, 'counter_type': 'poison', 'amount': 2},
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


def thrumming_hivepool_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Slivers you control have double strike and haste. At upkeep, create two 1/1 Sliver tokens."""
    interceptors = []

    # Grant double strike and haste to Slivers
    def sliver_filter(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                'Sliver' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)

    interceptors.append(make_keyword_grant(obj, ['double_strike', 'haste'], sliver_filter))

    # Upkeep trigger
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.OBJECT_CREATED, payload={
                'name': 'Sliver Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Sliver'],
                'colors': []
            }, source=obj.id),
            Event(type=EventType.OBJECT_CREATED, payload={
                'name': 'Sliver Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Sliver'],
                'colors': []
            }, source=obj.id)
        ]
    interceptors.append(make_upkeep_trigger(obj, upkeep_effect))

    return interceptors


# -----------------------------------------------------------------------------
# ADDITIONAL INTERCEPTORS
# -----------------------------------------------------------------------------

def brightspear_zealot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """This creature gets +2/+0 as long as you've cast two or more spells this turn."""
    def affects_filter(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        # Check if two or more spells cast this turn (simplified check)
        return getattr(state, 'spells_cast_this_turn', {}).get(obj.controller, 0) >= 2

    return make_static_pt_boost(obj, 2, 0, affects_filter)


def cosmogrand_zenith_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast your second spell each turn, create tokens or put counters."""
    spells_this_turn = [0]

    def spell_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source_obj.controller:
            return False
        spells_this_turn[0] += 1
        return spells_this_turn[0] == 2

    def spell_effect(event: Event, state: GameState) -> list[Event]:
        # Create two 1/1 white Human Soldier tokens
        return [
            Event(type=EventType.OBJECT_CREATED, payload={
                'name': 'Human Soldier Token', 'controller': obj.controller,
                'power': 1, 'toughness': 1, 'types': [CardType.CREATURE],
                'subtypes': ['Human', 'Soldier'], 'colors': [Color.WHITE]
            }, source=obj.id),
            Event(type=EventType.OBJECT_CREATED, payload={
                'name': 'Human Soldier Token', 'controller': obj.controller,
                'power': 1, 'toughness': 1, 'types': [CardType.CREATURE],
                'subtypes': ['Human', 'Soldier'], 'colors': [Color.WHITE]
            }, source=obj.id)
        ]

    return [make_spell_cast_trigger(obj, spell_effect)]


def dawnstrike_vanguard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At end step, if you control 2+ tapped creatures, put +1/+1 counter on each other creature."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        tapped_count = sum(1 for o in state.objects.values()
                         if o.controller == obj.controller
                         and CardType.CREATURE in o.characteristics.types
                         and o.zone == ZoneType.BATTLEFIELD
                         and o.state.tapped)
        if tapped_count >= 2:
            events = []
            for o in state.objects.values():
                if (o.id != obj.id and o.controller == obj.controller and
                    CardType.CREATURE in o.characteristics.types and
                    o.zone == ZoneType.BATTLEFIELD):
                    events.append(Event(
                        type=EventType.COUNTER_ADDED,
                        payload={'object_id': o.id, 'counter_type': '+1/+1', 'amount': 1},
                        source=obj.id
                    ))
            return events
        return []
    return [make_end_step_trigger(obj, end_step_effect)]


def exosuit_savior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, return up to one other target permanent you control to hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Target selection required
    return [make_etb_trigger(obj, etb_effect)]


def lightstall_inquisitor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, each opponent exiles a card from their hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified - just trigger discard/exile for opponents
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DISCARD,  # Using discard as placeholder for exile from hand
                    payload={'player': player_id, 'amount': 1},
                    source=obj.id
                ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def lumenclass_frigate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other creatures you control get +1/+1 when charged."""
    def affects_filter(target: GameObject, state: GameState) -> bool:
        if target.id == obj.id:
            return False
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        # Check if this spacecraft has 2+ charge counters
        counters = getattr(obj.state, 'counters', {})
        return counters.get('charge', 0) >= 2

    return make_static_pt_boost(obj, 1, 1, affects_filter)


def pulsar_squadron_ace_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, look at top 5 cards for Spacecraft or put +1/+1 counter."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified - put a +1/+1 counter on self
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def starfighter_pilot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature becomes tapped, surveil 1."""
    def tap_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_tap_trigger(obj, tap_effect)]


def sunstar_chaplain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At end step, if you control 2+ tapped creatures, put +1/+1 counter on target creature."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        tapped_count = sum(1 for o in state.objects.values()
                         if o.controller == obj.controller
                         and CardType.CREATURE in o.characteristics.types
                         and o.zone == ZoneType.BATTLEFIELD
                         and o.state.tapped)
        if tapped_count >= 2:
            return []  # Target selection required
        return []
    return [make_end_step_trigger(obj, end_step_effect)]


def sunstar_lightsmith_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast your second spell each turn, put +1/+1 counter and draw a card."""
    spells_this_turn = [0]

    def spell_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source_obj.controller:
            return False
        spells_this_turn[0] += 1
        return spells_this_turn[0] == 2

    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.COUNTER_ADDED, payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1}, source=obj.id),
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]

    return [make_spell_cast_trigger(obj, spell_effect)]


def cloudsculpt_technician_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """As long as you control an artifact, this creature gets +1/+0."""
    def affects_filter(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        # Check if controller controls an artifact
        for o in state.objects.values():
            if (o.controller == obj.controller and
                CardType.ARTIFACT in o.characteristics.types and
                o.zone == ZoneType.BATTLEFIELD):
                return True
        return False

    return make_static_pt_boost(obj, 1, 0, affects_filter)


def emissary_escort_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """This creature gets +X/+0 where X is greatest MV among other artifacts you control."""
    def power_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        return event.payload.get('object_id') == obj.id

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        # Find greatest mana value among other artifacts
        max_mv = 0
        for o in state.objects.values():
            if (o.id != obj.id and
                o.controller == obj.controller and
                CardType.ARTIFACT in o.characteristics.types and
                o.zone == ZoneType.BATTLEFIELD):
                mv = getattr(o.characteristics, 'mana_value', 0) or 0
                if mv > max_mv:
                    max_mv = mv
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + max_mv
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=power_filter,
        handler=power_handler,
        duration='while_on_battlefield'
    )]


def illvoi_operative_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast your second spell each turn, put a +1/+1 counter on this."""
    spells_this_turn = [0]

    def spell_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source_obj.controller:
            return False
        spells_this_turn[0] += 1
        return spells_this_turn[0] == 2

    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [make_spell_cast_trigger(obj, spell_effect)]


def nanoform_sentinel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature becomes tapped, untap another target permanent (once per turn)."""
    triggered_this_turn = [False]

    def tap_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if triggered_this_turn[0]:
            return False
        return (event.type == EventType.TAP and
                event.payload.get('object_id') == source_obj.id)

    def tap_effect(event: Event, state: GameState) -> list[Event]:
        triggered_this_turn[0] = True
        return []  # Target selection required
    return [make_tap_trigger(obj, tap_effect)]


def gravblade_heavy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """As long as you control an artifact, this creature gets +1/+0 and has deathtouch."""
    interceptors = []

    def has_artifact(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        for o in state.objects.values():
            if (o.controller == obj.controller and
                CardType.ARTIFACT in o.characteristics.types and
                o.zone == ZoneType.BATTLEFIELD):
                return True
        return False

    interceptors.extend(make_static_pt_boost(obj, 1, 0, has_artifact))
    interceptors.append(make_keyword_grant(obj, ['deathtouch'], has_artifact))

    return interceptors


def swarm_culler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature becomes tapped, you may sacrifice another creature/artifact to draw."""
    def tap_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified - just draw a card (sacrifice choice needed)
        return []  # Requires sacrifice choice
    return [make_tap_trigger(obj, tap_effect)]


def frontline_warrager_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At end step, if you control 2+ tapped creatures, put +1/+1 counter on this."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        tapped_count = sum(1 for o in state.objects.values()
                         if o.controller == obj.controller
                         and CardType.CREATURE in o.characteristics.types
                         and o.zone == ZoneType.BATTLEFIELD
                         and o.state.tapped)
        if tapped_count >= 2:
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id
            )]
        return []
    return [make_end_step_trigger(obj, end_step_effect)]


def kavaron_harrier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature attacks, you may pay 2 to create a tapped attacking Robot token."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Robot Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.ARTIFACT, CardType.CREATURE],
                'subtypes': ['Robot'],
                'colors': [],
                'tapped': True
            },
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def oreplate_pangolin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another artifact enters, you may pay 1 to put +1/+1 counter on this."""
    def artifact_etb_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj or entering_id == source_obj.id:
            return False
        if entering_obj.controller != source_obj.controller:
            return False
        return CardType.ARTIFACT in entering_obj.characteristics.types

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [make_etb_trigger(obj, effect_fn, filter_fn=artifact_etb_filter)]


def vaultguard_trooper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At end step, if you control 2+ tapped creatures, you may discard hand to draw 2."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        tapped_count = sum(1 for o in state.objects.values()
                         if o.controller == obj.controller
                         and CardType.CREATURE in o.characteristics.types
                         and o.zone == ZoneType.BATTLEFIELD
                         and o.state.tapped)
        if tapped_count >= 2:
            return [Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id
            )]
        return []
    return [make_end_step_trigger(obj, end_step_effect)]


def eumidian_terrabotanist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Landfall - Whenever a land you control enters, you gain 1 life."""
    def landfall_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller != source_obj.controller:
            return False
        return CardType.LAND in entering_obj.characteristics.types

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    return [make_etb_trigger(obj, landfall_effect, filter_fn=landfall_filter)]


def harmonious_grovestrider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Power/toughness equal to number of lands you control."""
    def pt_filter(event: Event, state: GameState) -> bool:
        return (event.type in (EventType.QUERY_POWER, EventType.QUERY_TOUGHNESS) and
                event.payload.get('object_id') == obj.id)

    def pt_handler(event: Event, state: GameState) -> InterceptorResult:
        # Count lands controller controls
        land_count = sum(1 for o in state.objects.values()
                        if o.controller == obj.controller
                        and CardType.LAND in o.characteristics.types
                        and o.zone == ZoneType.BATTLEFIELD)
        new_event = event.copy()
        new_event.payload['value'] = land_count
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=pt_filter,
        handler=pt_handler,
        duration='while_on_battlefield'
    )]


def hemosymbic_mite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature becomes tapped, another target creature gets +X/+X."""
    def tap_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Target selection required
    return [make_tap_trigger(obj, tap_effect)]


def icecave_crasher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Landfall - Whenever a land you control enters, this gets +1/+0 until end of turn."""
    def landfall_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller != source_obj.controller:
            return False
        return CardType.LAND in entering_obj.characteristics.types

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        # Self-targeted +1/+0 EOT (no choice needed)
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': obj.id,
                'power_mod': 1,
                'toughness_mod': 0,
                'duration': 'end_of_turn'
            },
            source=obj.id
        )]

    return [make_etb_trigger(obj, landfall_effect, filter_fn=landfall_filter)]


def remnant_elemental_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Landfall - Whenever a land you control enters, this gets +2/+0 until end of turn."""
    def landfall_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller != source_obj.controller:
            return False
        return CardType.LAND in entering_obj.characteristics.types

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        # Self-targeted +2/+0 EOT (no choice needed)
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': obj.id,
                'power_mod': 2,
                'toughness_mod': 0,
                'duration': 'end_of_turn'
            },
            source=obj.id
        )]

    return [make_etb_trigger(obj, landfall_effect, filter_fn=landfall_filter)]


def ouroboroid_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At beginning of combat on your turn, put X +1/+1 counters on each creature you control."""
    def combat_start_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.PHASE_START and
                event.payload.get('phase') == 'combat' and
                state.active_player == obj.controller)

    def combat_effect(event: Event, state: GameState) -> list[Event]:
        # Get this creature's power
        power = get_power(obj, state)
        events = []
        for o in state.objects.values():
            if (o.controller == obj.controller and
                CardType.CREATURE in o.characteristics.types and
                o.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': o.id, 'counter_type': '+1/+1', 'amount': power},
                    source=obj.id
                ))
        return events

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_start_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=combat_effect(e, s)),
        duration='while_on_battlefield'
    )]


def seedship_agrarian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature becomes tapped, create a Lander token. Landfall - +1/+1 counter."""
    interceptors = []

    def tap_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Lander Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Lander'],
                'colors': []
            },
            source=obj.id
        )]
    interceptors.append(make_tap_trigger(obj, tap_effect))

    def landfall_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller != source_obj.controller:
            return False
        return CardType.LAND in entering_obj.characteristics.types

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    interceptors.append(make_etb_trigger(obj, landfall_effect, filter_fn=landfall_filter))

    return interceptors


def skystinger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature blocks a creature with flying, this gets +5/+0 until end of turn."""
    def block_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.BLOCK_DECLARED:
            return False
        if event.payload.get('blocker_id') != source_obj.id:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        # Check if attacker has flying
        abilities = getattr(attacker.characteristics, 'abilities', [])
        return 'flying' in abilities

    def block_effect(event: Event, state: GameState) -> list[Event]:
        # Self-targeted +5/+0 EOT (no choice needed)
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': obj.id,
                'power_mod': 5,
                'toughness_mod': 0,
                'duration': 'end_of_turn'
            },
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: block_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=block_effect(e, s)),
        duration='while_on_battlefield'
    )]


def tapestry_warden_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Each creature you control with toughness greater than power assigns combat damage equal to toughness."""
    # This is a complex static ability that modifies combat damage calculation
    return []


def cosmogoyf_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Power is equal to cards you own in exile, toughness is that plus 1."""
    def pt_filter(event: Event, state: GameState) -> bool:
        return (event.type in (EventType.QUERY_POWER, EventType.QUERY_TOUGHNESS) and
                event.payload.get('object_id') == obj.id)

    def pt_handler(event: Event, state: GameState) -> InterceptorResult:
        # Count cards in exile owned by controller
        exile_count = sum(1 for o in state.objects.values()
                        if o.owner == obj.controller
                        and o.zone == ZoneType.EXILE)
        new_event = event.copy()
        if event.type == EventType.QUERY_POWER:
            new_event.payload['value'] = exile_count
        else:  # toughness
            new_event.payload['value'] = exile_count + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=pt_filter,
        handler=pt_handler,
        duration='while_on_battlefield'
    )]


def tannuk_memorial_ensign_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Landfall - Whenever a land you control enters, deal 1 damage to each opponent."""
    landfall_count_this_turn = [0]

    def landfall_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller != source_obj.controller:
            return False
        return CardType.LAND in entering_obj.characteristics.types

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        landfall_count_this_turn[0] += 1
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 1, 'source': obj.id},
                    source=obj.id
                ))
        # Draw card on second trigger
        if landfall_count_this_turn[0] == 2:
            events.append(Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id))
        return events

    return [make_etb_trigger(obj, landfall_effect, filter_fn=landfall_filter)]


def starfield_shepherd_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, search for basic Plains or creature with MV 1 or less."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,  # Simplified search effect
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def starwinder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a creature you control deals combat damage to a player, you may draw that many cards."""
    def damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('is_combat'):
            return False
        source_id = event.payload.get('source')
        source_obj = state.objects.get(source_id)
        if not source_obj:
            return False
        if source_obj.controller != obj.controller:
            return False
        if CardType.CREATURE not in source_obj.characteristics.types:
            return False
        target_id = event.payload.get('target')
        return target_id in state.players

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        amount = event.payload.get('amount', 0)
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': amount},
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


def selfcraft_mechan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, you may sacrifice an artifact. When you do, put +1/+1 counter and draw."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Requires sacrifice choice
    return [make_etb_trigger(obj, etb_effect)]


def comet_crawler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature attacks, you may sacrifice another creature/artifact for +2/+0."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Requires sacrifice choice
    return [make_attack_trigger(obj, attack_effect)]


def rescue_skiff_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, return target creature or enchantment from graveyard to battlefield."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Target selection required
    return [make_etb_trigger(obj, etb_effect)]


def susurian_dirgecraft_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, each opponent sacrifices a nontoken creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.SACRIFICE,
                    payload={'player': player_id, 'type': 'creature'},
                    source=obj.id
                ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def weapons_manufacturing_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a nontoken artifact you control enters, create a Munitions token."""
    def artifact_etb_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller != source_obj.controller:
            return False
        if getattr(entering_obj.state, 'is_token', False):
            return False
        return CardType.ARTIFACT in entering_obj.characteristics.types

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Munitions Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'colors': []
            },
            source=obj.id
        )]

    return [make_etb_trigger(obj, effect_fn, filter_fn=artifact_etb_filter)]


def sothera_the_supervoid_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a creature you control dies, each opponent chooses and exiles a creature they control."""
    def death_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying_obj = state.objects.get(dying_id)
        if not dying_obj:
            return False
        if dying_obj.controller != source_obj.controller:
            return False
        return CardType.CREATURE in dying_obj.characteristics.types

    def death_effect(event: Event, state: GameState) -> list[Event]:
        # Each opponent exiles a creature (simplified)
        return []

    return [make_death_trigger(obj, death_effect, filter_fn=death_filter)]


def nutrient_block_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this artifact is put into a graveyard from the battlefield, draw a card."""
    def death_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        return (event.type == EventType.ZONE_CHANGE and
                event.payload.get('object_id') == source_obj.id and
                event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD and
                event.payload.get('to_zone_type') == ZoneType.GRAVEYARD)

    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    return [make_death_trigger(obj, death_effect, filter_fn=death_filter)]


# =============================================================================
# MISSING CARD SETUPS (auto-generated, mostly stubs)
# =============================================================================

def anticausal_vestige_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When leaves the battlefield, draw a card; warp."""
    interceptors = []

    def leaves_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: warp/cheat-into-play permanent from hand
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    interceptors.append(make_leaves_battlefield_trigger(obj, leaves_effect))
    return interceptors


def tezzeret_cruel_captain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever an artifact you control enters, put a loyalty counter on Tezzeret."""
    def artifact_etb_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller != source_obj.controller:
            return False
        return CardType.ARTIFACT in entering_obj.characteristics.types

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'loyalty', 'amount': 1},
            source=obj.id
        )]

    # engine gap: planeswalker activated abilities and emblems
    return [make_etb_trigger(obj, effect_fn, filter_fn=artifact_etb_filter)]


def allfates_stalker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, exile up to one target non-Assassin creature; warp."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: target selection + temporary exile until LTB
        return []
    return [make_etb_trigger(obj, etb_effect)]


def astelli_reclaimer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, return target noncreature/nonland permanent card from graveyard with MV X or less."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: target selection + X-based MV filter on graveyard
        return []
    return [make_etb_trigger(obj, etb_effect)]


def banishing_light_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, exile target nonland permanent an opponent controls until this leaves."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: target selection + temporary exile-until-LTB
        return []
    return [make_etb_trigger(obj, etb_effect)]


def dualsun_adepts_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{5}: Creatures you control get +1/+1 until end of turn."""
    # engine gap: activated ability that pumps all creatures via temporary P/T
    return []


def exalted_sunborn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """If one or more tokens would be created under your control, twice that many are created instead."""
    # engine gap: replacement effect on token creation (doubling)
    return []


def hardlight_containment_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura: enchant artifact; ETB exile creature; ward 1 on enchanted permanent."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: aura attachment + temporary exile + ward grant
        return []
    return [make_etb_trigger(obj, etb_effect)]


def luxknight_breacher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enters with a +1/+1 counter for each other creature/artifact you control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        count = 0
        for o in state.objects.values():
            if (o.id != obj.id and o.controller == obj.controller and
                o.zone == ZoneType.BATTLEFIELD and
                (CardType.CREATURE in o.characteristics.types or
                 CardType.ARTIFACT in o.characteristics.types)):
                count += 1
        if count <= 0:
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': count},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def pinnacle_starcage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, exile all artifacts/creatures with MV<=2 until this leaves."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: mass temporary exile-until-LTB
        return []
    return [make_etb_trigger(obj, etb_effect)]


def seam_rip_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, exile target nonland permanent (MV<=2) an opponent controls until this leaves."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: target selection + temporary exile-until-LTB
        return []
    return [make_etb_trigger(obj, etb_effect)]


def the_seriema_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, search for a legendary creature card. Station 7+ flying. Other tapped legendaries indestructible."""
    interceptors = []

    def legendary_creature(card_obj, st):
        return (
            CardType.CREATURE in card_obj.characteristics.types
            and "Legendary" in (card_obj.characteristics.supertypes or set())
        )

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return open_library_search(
            state, obj.controller, obj.id,
            filter_fn=legendary_creature,
            destination="hand",
            reveal=True,
            shuffle_after=True,
            optional=False,
            min_count=1,
            prompt="Search your library for a legendary creature card and put it into your hand.",
        )
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Other tapped legendary creatures you control have indestructible.
    def legendary_tapped_filter(target: GameObject, state: GameState) -> bool:
        if target.id == obj.id:
            return False
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        if 'Legendary' not in target.characteristics.supertypes:
            return False
        return target.state.tapped

    interceptors.append(make_keyword_grant(obj, ['indestructible'], legendary_tapped_filter))
    return interceptors


def squires_lightblade_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment: ETB attach to your creature, gives first strike EOT. +1/+0. Equip {3}."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: equipment auto-attach + first-strike-until-EOT
        return []
    return [make_etb_trigger(obj, etb_effect)]


def starport_security_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Activated ability tap-target with cost reduction; engine gap on dynamic activated cost."""
    # engine gap: dynamic activated ability cost (-2 if you control creature with +1/+1 counter)
    return []


def sunstar_expansionist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB conditional Lander; landfall +1/+0 EOT."""
    interceptors = []

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Count lands per player
        my_lands = sum(1 for o in state.objects.values()
                       if o.controller == obj.controller and CardType.LAND in o.characteristics.types
                       and o.zone == ZoneType.BATTLEFIELD)
        opp_more = False
        for pid in state.players.keys():
            if pid == obj.controller:
                continue
            their_lands = sum(1 for o in state.objects.values()
                              if o.controller == pid and CardType.LAND in o.characteristics.types
                              and o.zone == ZoneType.BATTLEFIELD)
            if their_lands > my_lands:
                opp_more = True
                break
        if not opp_more:
            return []
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Lander Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Lander'],
                'colors': []
            },
            source=obj.id
        )]
    interceptors.append(make_etb_trigger(obj, etb_effect))

    def landfall_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller != source_obj.controller:
            return False
        return CardType.LAND in entering_obj.characteristics.types

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: temporary +1/+0 EOT pump
        return []
    interceptors.append(make_etb_trigger(obj, landfall_effect, filter_fn=landfall_filter))
    return interceptors


def atomic_microsizer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment: equipped +1/+0; whenever equipped attacks, target gets unblockable + base 1/1 EOT."""
    # engine gap: equipped-creature attack trigger; can't-be-blocked + base P/T set
    return []


def cryoshatter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura: enchanted creature gets -5/-0; when tapped or damaged, destroy it."""
    # engine gap: aura attachment + -5/-0 + conditional destroy on tap/damage
    return []


def gigastorm_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """This spell costs {3} less to cast if you've cast another spell this turn."""
    # engine gap: dynamic cast cost reduction (cost reduction at cast time)
    return []


def illvoi_galeblade_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}, sac: draw a card."""
    # engine gap: activated ability with sacrifice cost
    return []


def illvoi_light_jammer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment: ETB attach + hexproof EOT. +1/+2. Equip {3}."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: equipment auto-attach + hexproof-until-EOT
        return []
    return [make_etb_trigger(obj, etb_effect)]


def mechan_shieldmate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Defender; can attack as though it didn't have defender if an artifact entered this turn."""
    # engine gap: conditional defender removal based on per-turn ETB tracking
    return []


def mmmenon_the_right_hand_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying; look at top; cast artifacts from top; artifacts you control tap for {U} (specific use)."""
    # engine gap: cast-from-library + restricted mana production
    return []


def moonlit_meditation_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura: first time you would create tokens each turn, create copies of enchanted permanent instead."""
    # engine gap: replacement of token creation by copying enchanted permanent
    return []


def specimen_freighter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, return up to two non-Spacecraft creatures to hand. Station 9+ flying. Attack: defender mills 4."""
    interceptors = []

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: targeted bounce (up to 2)
        return []
    interceptors.append(make_etb_trigger(obj, etb_effect))

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Mill 4 to each opponent (defending player approximation)
        return [Event(
            type=EventType.MILL,
            payload={'player': pid, 'amount': 4},
            source=obj.id
        ) for pid in state.players.keys() if pid != obj.controller]
    interceptors.append(make_attack_trigger(obj, attack_effect))
    return interceptors


def starfield_vocalist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """If a permanent entering causes a triggered ability of yours to trigger, that ability triggers an additional time."""
    # engine gap: replicate triggered abilities (doubling effect)
    return []


def steelswarm_operator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tap-for-restricted-mana abilities."""
    # engine gap: restricted mana production (only for artifacts)
    return []


def synthesizer_labship_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Station 9+: becomes a creature with flying + vigilance.

    The 2+ tier (combat-trigger to animate target artifact) is an engine gap —
    it requires interactive targeting and a temporary become-creature effect.
    """
    return make_station_creature_setup(obj, [
        (9, {'power': 5, 'toughness': 5, 'keywords': ['flying', 'vigilance']}),
    ])


def tractor_beam_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura: tap, gain control, no untap."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: aura attachment + control change + untap restriction
        return []
    return [make_etb_trigger(obj, etb_effect)]


def uthros_psionicist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """The second spell you cast each turn costs {2} less."""
    # engine gap: cost reduction with per-turn second-spell tracking
    return []


def weftwalking_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB if cast, shuffle hand+graveyard into library, draw 7. First spell each player casts may be free."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: hand/graveyard shuffle into library + once-per-turn first-spell-free
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 7},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def alpharael_stonechosen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ward-discard random; void attack: defender loses half life."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: void mechanic check + ward + half-life-loss
        return []
    return [make_attack_trigger(obj, attack_effect)]


def blade_of_the_swarm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: choose one - two +1/+1 counters on self OR put exiled warp card on bottom."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Default to mode 1: counters (engine gap: modal choice + warp interaction)
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def chorale_of_the_void_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura: attack puts target creature card from defender's GY onto BF tapped+attacking. Void EOT sac."""
    interceptors = []

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: aura-attached attack trigger, reanimate from opponent GY
        return []
    interceptors.append(make_attack_trigger(obj, attack_effect))

    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: void-mechanic conditional sacrifice
        return []
    interceptors.append(make_end_step_trigger(obj, end_step_effect))
    return interceptors


def dubious_delicacy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flash; ETB: target creature -3/-3 EOT. Activated abilities for life/loss."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: target selection + temporary -3/-3 P/T modification
        return []
    return [make_etb_trigger(obj, etb_effect)]


def entropic_battlecruiser_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Station 1+/8+ effects; opponent discard => 3 life loss; attack: opponents discard."""
    interceptors = []

    def discard_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DISCARD:
            return False
        return event.payload.get('player') != obj.controller

    def discard_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: requires station >=1 charge counter check
        target = event.payload.get('player')
        if not target:
            return []
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': target, 'amount': -3},
            source=obj.id
        )]

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=discard_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=discard_effect(e, s)),
        duration='while_on_battlefield'
    ))

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: requires station >=8; opponent discard, lose 3 if can't
        return [Event(
            type=EventType.DISCARD,
            payload={'player': pid, 'amount': 1},
            source=obj.id
        ) for pid in state.players.keys() if pid != obj.controller]
    interceptors.append(make_attack_trigger(obj, attack_effect))
    return interceptors


def fallers_faithful_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: destroy up to one target creature. If undamaged, controller draws 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: target selection + conditional draw based on damage history
        return []
    return [make_etb_trigger(obj, etb_effect)]


def hylderblade_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment +3/+1; void EOT attach to target."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: void mechanic check + equipment auto-attach
        return []
    return [make_end_step_trigger(obj, end_step_effect)]


def insatiable_skittermaw_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace; void EOT +1/+1 counter on self."""
    def void_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_void_end_step_trigger(obj, void_effect)]


def perigee_beckoner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: target creature gets +2/+0 and 'when dies, return tapped'. Warp."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: target selection + temporary granted death trigger
        return []
    return [make_etb_trigger(obj, etb_effect)]


def requiem_monolith_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: temporary 'when damaged, draw cards and lose life' on target."""
    # engine gap: activated ability granting temporary damage trigger to a target
    return []


def sunset_saboteur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace; ward discard; attack puts +1/+1 on opponent's creature (downside)."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: target selection on opponent's creature
        return []
    return [make_attack_trigger(obj, attack_effect)]


def timeline_culler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste; warp from graveyard."""
    # engine gap: warp casting from graveyard
    return []


def umbral_collar_zealot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sacrifice another creature/artifact: surveil 1."""
    # engine gap: activated ability with sacrifice cost
    return []


def voidforged_titan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Void EOT: draw a card and lose 1 life."""
    def void_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': -1}, source=obj.id),
        ]
    return [make_void_end_step_trigger(obj, void_effect)]


def xuifit_osteoharmonist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Return target creature card from your GY to BF as a Skeleton, no abilities."""
    # engine gap: tap-activated reanimation with type/ability rewriting
    return []


def galvanizing_sawship_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Station 3+: becomes a creature with flying + haste.

    The station charge mechanic is in src/engine/station.py; this setup wires
    the threshold-gated stats/keywords via the QUERY_* interceptor pattern.
    """
    return make_station_creature_setup(obj, [
        (3, {'power': 4, 'toughness': 4, 'keywords': ['flying', 'haste']}),
    ])


def kavaron_skywarden_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach; void EOT: +1/+1 counter."""
    def void_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_void_end_step_trigger(obj, void_effect)]


def kavaron_turbodrone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: target creature gets +1/+1 and haste EOT (sorcery speed)."""
    # engine gap: tap activated targeted +1/+1 + haste EOT
    return []


def memorial_vault_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}, sac artifact: exile top X cards, may play this turn."""
    # engine gap: activated ability with sacrifice cost + impulse draw
    return []


def pain_for_all_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura: ETB enchanted deals power-damage to any other target. Whenever damaged, deals to each opponent."""
    interceptors = []

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: aura-relative damage redirection + targeting
        return []
    interceptors.append(make_etb_trigger(obj, etb_effect))
    return interceptors


def possibility_technician_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this or another Kavu enters, exile top card; may play if you control a Kavu."""
    def kavu_etb_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller != source_obj.controller:
            return False
        if CardType.CREATURE not in entering_obj.characteristics.types:
            return False
        return 'Kavu' in entering_obj.characteristics.subtypes or entering_id == source_obj.id

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: exile-top + may-play conditional cast
        return [Event(
            type=EventType.EXILE_FROM_TOP,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, effect_fn, filter_fn=kavu_etb_filter)]


def red_tiger_mechan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste; warp."""
    # engine gap: warp mechanic; haste comes from card text/keyword grant
    return []


def roving_actuator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Void ETB: exile target instant/sorcery (MV<=2) from GY, copy, may cast free."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: void mechanic + GY targeting + copy-and-cast-free
        return []
    return [make_etb_trigger(obj, etb_effect)]


def rust_harvester_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace; {2}{T}, exile artifact from GY: +1/+1 counter, deal power damage to any target."""
    # engine gap: activated ability with exile cost from GY
    return []


def slagdrill_scrapper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}{T}, sac artifact/land: draw."""
    # engine gap: activated ability with sacrifice cost
    return []


def terrapact_intimidator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: target opponent may have you create 2 Lander tokens; if not, two +1/+1 on self."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: opponent choice; default to self-counters branch
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def territorial_bruntar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach; landfall: exile until nonland; may cast."""
    def landfall_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller != source_obj.controller:
            return False
        return CardType.LAND in entering_obj.characteristics.types

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: reveal-until-nonland + impulse-cast
        return []
    return [make_etb_trigger(obj, landfall_effect, filter_fn=landfall_filter)]


def zookeeper_mechan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Add {R}; {6}{R}: target creature +4/+0 EOT (sorcery)."""
    # engine gap: activated abilities (mana production + targeted pump)
    return []


def bioengineered_future_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: create Lander; creatures enter with extra +1/+1 per land entered this turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Lander Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Lander'],
                'colors': []
            },
            source=obj.id
        )]
    # engine gap: replacement effect adding counters per lands-entered-this-turn
    return [make_etb_trigger(obj, etb_effect)]


def broodguard_elite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enters with X +1/+1 counters; LTB transfer counters; warp."""
    interceptors = []

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: X-cost counter parsing
        return []
    interceptors.append(make_etb_trigger(obj, etb_effect))

    def leaves_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: counter transfer to target on LTB
        return []
    interceptors.append(make_leaves_battlefield_trigger(obj, leaves_effect))
    return interceptors


def eusocial_engineering_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Landfall: create 2/2 Robot."""
    def landfall_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller != source_obj.controller:
            return False
        return CardType.LAND in entering_obj.characteristics.types

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Robot Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.ARTIFACT, CardType.CREATURE],
                'subtypes': ['Robot'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, landfall_effect, filter_fn=landfall_filter)]


def famished_worldsire_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ward 3; Devour land 3; ETB: search for X land cards onto BF tapped."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: devour mechanic + library search putting lands tapped
        return []
    return [make_etb_trigger(obj, etb_effect)]


def frenzied_baloth_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trample, haste; uncounterable; creatures uncounterable; combat damage uncovered."""
    # engine gap: uncounterable spells + combat damage cannot be prevented
    return []


def fungal_colossus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """This spell costs {X} less to cast where X is differently named lands."""
    # engine gap: dynamic cast cost reduction (lands-named-count)
    return []


def gene_pollinator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}, tap a permanent: any color mana."""
    # engine gap: activated mana ability with tap of another permanent as cost
    return []


def icetill_explorer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Extra land per turn; may play lands from GY; landfall: mill 1."""
    interceptors = []

    # engine gap: play lands from graveyard
    # Additional land play is supported
    from src.cards.interceptor_helpers import make_additional_land_play
    interceptors.append(make_additional_land_play(obj, count=1))

    def landfall_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller != source_obj.controller:
            return False
        return CardType.LAND in entering_obj.characteristics.types

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    interceptors.append(make_etb_trigger(obj, landfall_effect, filter_fn=landfall_filter))
    return interceptors


def intrepid_tenderfoot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{3}: +1/+1 counter on self (sorcery)."""
    # engine gap: activated ability with mana cost
    return []


def larval_scoutlander_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB may sac land/Lander -> search 2 basics tapped. Station 7+ flying."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: sacrifice-cost-replaced + library search
        return []
    return [make_etb_trigger(obj, etb_effect)]


def lashwhip_predator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Cost {2} less if opponents control 3+ creatures."""
    # engine gap: dynamic cast cost reduction (opponent board count)
    return []


def loading_zone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Doubles counters put on creature/Spacecraft/Planet you control. Warp."""
    from src.engine.replacements import make_counter_doubler
    src_controller = obj.controller

    def your_eligible_permanent(target: GameObject, state: GameState) -> bool:
        if target.controller != src_controller:
            return False
        types = target.characteristics.types
        if CardType.CREATURE in types:
            return True
        # Spacecraft / Planet are subtypes in the Edge of Eternities space.
        subtypes = target.characteristics.subtypes
        return 'Spacecraft' in subtypes or 'Planet' in subtypes

    return [make_counter_doubler(obj, target_filter=your_eligible_permanent)]


def meltstriders_gear_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment ETB attach. Equipped +2/+1 reach. Equip {5}."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: equipment auto-attach
        return []
    return [make_etb_trigger(obj, etb_effect)]


def meltstriders_resolve_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura ETB: enchanted creature fights up to one target opponent's creature. +0/+2; can't be blocked by 2+."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: aura attachment + fight effect targeting
        return []
    return [make_etb_trigger(obj, etb_effect)]


def mightform_harmonizer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Landfall: double power of target creature EOT. Warp."""
    def landfall_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller != source_obj.controller:
            return False
        return CardType.LAND in entering_obj.characteristics.types

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: target selection + dynamic power doubling EOT
        return []
    return [make_etb_trigger(obj, landfall_effect, filter_fn=landfall_filter)]


def sledgeclass_seedship_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Station 7+ flying. Attack: may put creature card from hand onto BF."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: cheat-into-play creature from hand
        return []
    return [make_attack_trigger(obj, attack_effect)]


def terrasymbiosis_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever +1/+1 counters added to creature, may draw cards. Once per turn."""
    triggered_this_turn = [False]

    def counter_filter(event: Event, state: GameState) -> bool:
        if triggered_this_turn[0]:
            return False
        if event.type != EventType.COUNTER_ADDED:
            return False
        if event.payload.get('counter_type') != '+1/+1':
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        if target.controller != obj.controller:
            return False
        return CardType.CREATURE in target.characteristics.types

    def counter_effect(event: Event, state: GameState) -> list[Event]:
        triggered_this_turn[0] = True
        amount = event.payload.get('amount', 1)
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': amount},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=counter_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=counter_effect(e, s)),
        duration='while_on_battlefield'
    )]


def dyadrine_synthesis_amalgam_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trample; enters with X +1/+1; attack: remove counters from 2 creatures => draw + 2/2 token."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: optional counter-removal cost + token creation
        return []
    return [make_attack_trigger(obj, attack_effect)]


def genemorph_imago_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying; landfall: target has base 3/3 EOT (or 6/6 if 6+ lands)."""
    def landfall_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller != source_obj.controller:
            return False
        return CardType.LAND in entering_obj.characteristics.types

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: target selection + base P/T set EOT
        return []
    return [make_etb_trigger(obj, landfall_effect, filter_fn=landfall_filter)]


def infinite_guideline_station_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: create tapped Robot per multicolored permanent. Station 12+ flying. Attack: draw per multicolored."""
    interceptors = []

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for o in state.objects.values():
            if (o.controller == obj.controller and
                o.zone == ZoneType.BATTLEFIELD and
                len(o.characteristics.colors) >= 2):
                events.append(Event(
                    type=EventType.OBJECT_CREATED,
                    payload={
                        'name': 'Robot Token',
                        'controller': obj.controller,
                        'power': 2,
                        'toughness': 2,
                        'types': [CardType.ARTIFACT, CardType.CREATURE],
                        'subtypes': ['Robot'],
                        'colors': [],
                        'tapped': True
                    },
                    source=obj.id
                ))
        return events
    interceptors.append(make_etb_trigger(obj, etb_effect))

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: requires station >=12; counts multicolored permanents
        count = sum(1 for o in state.objects.values()
                    if o.controller == obj.controller
                    and o.zone == ZoneType.BATTLEFIELD
                    and len(o.characteristics.colors) >= 2)
        if count <= 0:
            return []
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': count},
            source=obj.id
        )]
    interceptors.append(make_attack_trigger(obj, attack_effect))
    return interceptors


def ragost_deft_gastronaut_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Artifacts you control are Foods with sac->3 life. Sac Food -> 3 dmg each opponent. EOT untap if life gained."""
    interceptors = []

    # Grant Food subtype to artifacts you control
    from src.cards.interceptor_helpers import type_grant_interceptor

    def your_artifacts(target: GameObject, state: GameState) -> bool:
        if target.controller != obj.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        return CardType.ARTIFACT in target.characteristics.types

    interceptors.append(type_grant_interceptor(obj, ['Food'], affects_filter=your_artifacts))

    # engine gap: activated abilities (sac->3 life, sac food->3 damage), self-untap-if-lifegain
    return interceptors


def sami_wildcat_captain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Double strike vigilance; spells have affinity for artifacts."""
    # engine gap: affinity-for-artifacts cost reduction
    return []


def allfates_scroll_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: any color mana; {7}{T} sac: draw X cards (differently named lands)."""
    # engine gap: tap-for-any-color + sac-and-draw with dynamic X
    return []


def bygone_colossus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Warp."""
    # engine gap: warp casting
    return []


def dawnsire_sunstar_dreadnought_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Station 10+/20+ effects."""
    interceptors = []

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: requires station >=10 charge counters; targeted 100 damage
        return []
    interceptors.append(make_attack_trigger(obj, attack_effect))
    return interceptors


def the_dominion_bracelet_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipped +1/+1 with control-opponent ability. Equip {1}."""
    # engine gap: control-opponent activated ability with dynamic cost
    return []


def the_endstone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you play land or cast spell, draw. EOT: life becomes half starting life."""
    interceptors = []

    def play_or_cast_filter(event: Event, state: GameState) -> bool:
        if event.type == EventType.CAST or event.type == EventType.SPELL_CAST:
            caster = event.payload.get('caster') or event.payload.get('controller') or event.controller
            return caster == obj.controller
        if event.type == EventType.ZONE_CHANGE:
            if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
                return False
            entering_id = event.payload.get('object_id')
            entering = state.objects.get(entering_id)
            if not entering:
                return False
            if entering.controller != obj.controller:
                return False
            return CardType.LAND in entering.characteristics.types
        return False

    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=play_or_cast_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=draw_effect(e, s)),
        duration='while_on_battlefield'
    ))

    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: setting life total to specific value (half starting life rounded up)
        return []
    interceptors.append(make_end_step_trigger(obj, end_step_effect))
    return interceptors


def the_eternity_elevator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: Add CCC. Station 20+: tap for X mana (charge counters)."""
    # engine gap: activated mana abilities with charge-counter scaling
    return []


def survey_mechan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying; hexproof; {10}, sac: 3 damage + draw 3 + 3 life. Cost reduction by named lands."""
    # engine gap: activated ability with sac cost + dynamic cost reduction
    return []


def thaumaton_torpedo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{6}{T} sac: destroy nonland. -3 cost if attacked with Spacecraft this turn."""
    # engine gap: activated ability + dynamic cost reduction (per-turn attack tracking)
    return []


def adagia_windswept_bastion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Land enters tapped; {T}: W; Station 12+ activated ability."""
    # engine gap: enters-tapped land + station-charge-counter gated activated ability
    return []


def breeding_pool_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Shockland: pay 2 life or enters tapped."""
    # engine gap: enters-tapped-unless-pay choice
    return []


def command_bridge_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enters tapped; sacrifice unless tap; tap for any color."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: sacrifice-unless-tap-untapped-permanent cost
        return []
    return [make_etb_trigger(obj, etb_effect)]


def evendo_waking_haven_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enters tapped; {T}: G; Station 12+ activated ability."""
    # engine gap: station-charge-counter gated activated ability
    return []


def godless_shrine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Shockland: pay 2 life or enters tapped."""
    # engine gap: enters-tapped-unless-pay choice
    return []


def kavaron_memorial_world_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enters tapped; {T}: R; Station 12+ activated ability."""
    # engine gap: station-charge-counter gated activated ability
    return []


def sacred_foundry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Shockland: pay 2 life or enters tapped."""
    # engine gap: enters-tapped-unless-pay choice
    return []


def secluded_starforge_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Activated abilities (Robot tokens, Spacecraft pump)."""
    # engine gap: tap-X-artifacts activated ability + token-creation activated ability
    return []


def stomping_ground_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Shockland: pay 2 life or enters tapped."""
    # engine gap: enters-tapped-unless-pay choice
    return []


def susur_secundi_void_altar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enters tapped; {T}: B; Station 12+ activated ability (sac creature draw cards)."""
    # engine gap: station-charge-counter gated activated ability
    return []


def uthros_titanic_godcore_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enters tapped; {T}: U; Station 12+ activated ability (U per artifact)."""
    # engine gap: station-charge-counter gated activated ability
    return []


def watery_grave_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Shockland: pay 2 life or enters tapped."""
    # engine gap: enters-tapped-unless-pay choice
    return []


# =============================================================================
# CARD DEFINITIONS
# =============================================================================

ANTICAUSAL_VESTIGE = make_creature(
    name="Anticausal Vestige",
    power=7, toughness=5,
    mana_cost="{6}",
    colors=set(),
    subtypes={"Eldrazi"},
    text="When this creature leaves the battlefield, draw a card, then you may put a permanent card with mana value less than or equal to the number of lands you control from your hand onto the battlefield tapped.\nWarp {4} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{4}", inner_setup=anticausal_vestige_setup),
)

TEZZERET_CRUEL_CAPTAIN = make_planeswalker(
    name="Tezzeret, Cruel Captain",
    mana_cost="{3}",
    colors=set(),
    loyalty=4,
    subtypes={"Tezzeret"},
    supertypes={"Legendary"},
    text="Whenever an artifact you control enters, put a loyalty counter on Tezzeret.\n0: Untap target artifact or creature. If it's an artifact creature, put a +1/+1 counter on it.\n−3: Search your library for an artifact card with mana value 1 or less, reveal it, put it into your hand, then shuffle.\n−7: You get an emblem with \"At the beginning of combat on your turn, put three +1/+1 counters on target artifact you control. If it's not a creature, it becomes a 0/0 Robot artifact creature.\"",
    setup_interceptors=tezzeret_cruel_captain_setup,
)

ALLFATES_STALKER = make_creature(
    name="All-Fates Stalker",
    power=2, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Assassin", "Drix"},
    text="When this creature enters, exile up to one target non-Assassin creature until this creature leaves the battlefield.\nWarp {1}{W} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{1}{W}", inner_setup=allfates_stalker_setup),
)

ASTELLI_RECLAIMER = make_creature(
    name="Astelli Reclaimer",
    power=5, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel", "Warrior"},
    text="Flying\nWhen this creature enters, return target noncreature, nonland permanent card with mana value X or less from your graveyard to the battlefield, where X is the amount of mana spent to cast this creature.\nWarp {2}{W}",
    setup_interceptors=make_warp_setup("{2}{W}", inner_setup=astelli_reclaimer_setup),
)

AUXILIARY_BOOSTERS = make_artifact(
    name="Auxiliary Boosters",
    mana_cost="{4}{W}",
    text="When this Equipment enters, create a 2/2 colorless Robot artifact creature token and attach this Equipment to it.\nEquipped creature gets +1/+2 and has flying.\nEquip {3} ({3}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=auxiliary_boosters_setup,
)

BANISHING_LIGHT = make_enchantment(
    name="Banishing Light",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, exile target nonland permanent an opponent controls until this enchantment leaves the battlefield.",
    setup_interceptors=banishing_light_setup,
)

BEYOND_THE_QUIET = make_sorcery(
    name="Beyond the Quiet",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Exile all creatures and Spacecraft.",
)

BRIGHTSPEAR_ZEALOT = make_creature(
    name="Brightspear Zealot",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Vigilance\nThis creature gets +2/+0 as long as you've cast two or more spells this turn.",
    setup_interceptors=brightspear_zealot_setup
)

COSMOGRAND_ZENITH = make_creature(
    name="Cosmogrand Zenith",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Whenever you cast your second spell each turn, choose one —\n• Create two 1/1 white Human Soldier creature tokens.\n• Put a +1/+1 counter on each creature you control.",
    setup_interceptors=cosmogrand_zenith_setup
)

DAWNSTRIKE_VANGUARD = make_creature(
    name="Dawnstrike Vanguard",
    power=4, toughness=5,
    mana_cost="{5}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Lifelink\nAt the beginning of your end step, if you control two or more tapped creatures, put a +1/+1 counter on each creature you control other than this creature.",
    setup_interceptors=dawnstrike_vanguard_setup
)

DOCKWORKER_DRONE = make_artifact_creature(
    name="Dockworker Drone",
    power=1, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Robot"},
    text="This creature enters with a +1/+1 counter on it.\nWhen this creature dies, put its counters on target creature you control.",
    setup_interceptors=dockworker_drone_setup
)

DUALSUN_ADEPTS = make_creature(
    name="Dual-Sun Adepts",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Double strike\n{5}: Creatures you control get +1/+1 until end of turn.",
)

DUALSUN_TECHNIQUE = make_instant(
    name="Dual-Sun Technique",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature you control gains double strike until end of turn. If it has a +1/+1 counter on it, draw a card.",
)

EMERGENCY_EJECT = make_instant(
    name="Emergency Eject",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Destroy target nonland permanent. Its controller creates a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

EXALTED_SUNBORN = make_creature(
    name="Exalted Sunborn",
    power=4, toughness=5,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel", "Wizard"},
    text="Flying, lifelink\nIf one or more tokens would be created under your control, twice that many of those tokens are created instead.\nWarp {1}{W} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{1}{W}", inner_setup=exalted_sunborn_setup),
)

EXOSUIT_SAVIOR = make_creature(
    name="Exosuit Savior",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Flying\nWhen this creature enters, return up to one other target permanent you control to its owner's hand.",
    setup_interceptors=exosuit_savior_setup
)

FLIGHTDECK_COORDINATOR = make_creature(
    name="Flight-Deck Coordinator",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="At the beginning of your end step, if you control two or more tapped creatures, you gain 2 life.",
    setup_interceptors=flightdeck_coordinator_setup
)

FOCUS_FIRE = make_instant(
    name="Focus Fire",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Focus Fire deals X damage to target attacking or blocking creature, where X is 2 plus the number of creatures and/or Spacecraft you control.",
)

HALIYA_GUIDED_BY_LIGHT = make_creature(
    name="Haliya, Guided by Light",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Whenever Haliya or another creature or artifact you control enters, you gain 1 life.\nAt the beginning of your end step, draw a card if you've gained 3 or more life this turn.\nWarp {W} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{W}", inner_setup=haliya_guided_by_light_setup),
)

HARDLIGHT_CONTAINMENT = make_enchantment(
    name="Hardlight Containment",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Enchant artifact you control\nWhen this Aura enters, exile target creature an opponent controls until this Aura leaves the battlefield.\nEnchanted permanent has ward {1}.",
    subtypes={"Aura"},
    setup_interceptors=hardlight_containment_setup,
)

HONOR = make_sorcery(
    name="Honor",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Put a +1/+1 counter on target creature.\nDraw a card.",
)

HONORED_KNIGHTCAPTAIN = make_creature(
    name="Honored Knight-Captain",
    power=1, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Advisor", "Human", "Knight"},
    text="When this creature enters, create a 1/1 white Human Soldier creature token.\n{4}{W}{W}, Sacrifice this creature: Search your library for an Equipment card, put it onto the battlefield, then shuffle.",
    setup_interceptors=honored_knightcaptain_setup,
)

KNIGHT_LUMINARY = make_creature(
    name="Knight Luminary",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="When this creature enters, create a 1/1 white Human Soldier creature token.\nWarp {1}{W} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{1}{W}", inner_setup=knight_luminary_setup),
)

LIGHTSTALL_INQUISITOR = make_creature(
    name="Lightstall Inquisitor",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Angel", "Wizard"},
    text="Vigilance\nWhen this creature enters, each opponent exiles a card from their hand and may play that card for as long as it remains exiled. Each spell cast this way costs {1} more to cast. Each land played this way enters tapped.",
    setup_interceptors=lightstall_inquisitor_setup,
)

LUMENCLASS_FRIGATE = make_artifact(
    name="Lumen-Class Frigate",
    mana_cost="{1}{W}",
    text="Station (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 12+.)\n2+ | Other creatures you control get +1/+1.\n12+ | Flying, lifelink",
    subtypes={"Spacecraft"},
    setup_interceptors=lumenclass_frigate_setup,
)

LUXKNIGHT_BREACHER = make_creature(
    name="Luxknight Breacher",
    power=2, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="This creature enters with a +1/+1 counter on it for each other creature and/or artifact you control.",
    setup_interceptors=luxknight_breacher_setup,
)

PINNACLE_STARCAGE = make_artifact(
    name="Pinnacle Starcage",
    mana_cost="{1}{W}{W}",
    text="When this artifact enters, exile all artifacts and creatures with mana value 2 or less until this artifact leaves the battlefield.\n{6}{W}{W}: Put each card exiled with this artifact into its owner's graveyard, then create a 2/2 colorless Robot artifact creature token for each card put into a graveyard this way. Sacrifice this artifact.",
    setup_interceptors=pinnacle_starcage_setup,
)

PULSAR_SQUADRON_ACE = make_creature(
    name="Pulsar Squadron Ace",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Pilot"},
    text="When this creature enters, look at the top five cards of your library. You may reveal a Spacecraft card from among them and put it into your hand. Put the rest on the bottom of your library in a random order. If you didn't put a card into your hand this way, put a +1/+1 counter on this creature.",
    setup_interceptors=pulsar_squadron_ace_setup,
)

RADIANT_STRIKE = make_instant(
    name="Radiant Strike",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Destroy target artifact or tapped creature. You gain 3 life.",
)

RAYBLADE_TROOPER = make_creature(
    name="Rayblade Trooper",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="When this creature enters, put a +1/+1 counter on target creature you control.\nWhenever a nontoken creature you control with a +1/+1 counter on it dies, create a 1/1 white Human Soldier creature token.\nWarp {1}{W} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{1}{W}", inner_setup=rayblade_trooper_setup),
)

REROUTE_SYSTEMS = make_instant(
    name="Reroute Systems",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Target artifact or creature gains indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)\n• Reroute Systems deals 2 damage to target tapped creature.",
)

RESCUE_SKIFF = make_artifact(
    name="Rescue Skiff",
    mana_cost="{5}{W}",
    text="When this Spacecraft enters, return target creature or enchantment card from your graveyard to the battlefield.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 10+.)\n10+ | Flying",
    subtypes={"Spacecraft"},
    setup_interceptors=rescue_skiff_setup,
)

SCOUT_FOR_SURVIVORS = make_sorcery(
    name="Scout for Survivors",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Return up to three target creature cards with total mana value 3 or less from your graveyard to the battlefield. Put a +1/+1 counter on each of them.",
)

SEAM_RIP = make_enchantment(
    name="Seam Rip",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, exile target nonland permanent an opponent controls with mana value 2 or less until this enchantment leaves the battlefield.",
    setup_interceptors=seam_rip_setup,
)

THE_SERIEMA = make_artifact(
    name="The Seriema",
    mana_cost="{1}{W}{W}",
    text="When The Seriema enters, search your library for a legendary creature card, reveal it, put it into your hand, then shuffle.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 7+.)\n7+ | Flying\nOther tapped legendary creatures you control have indestructible.",
    subtypes={"Spacecraft"},
    supertypes={"Legendary"},
    setup_interceptors=the_seriema_setup,
)

SQUIRES_LIGHTBLADE = make_artifact(
    name="Squire's Lightblade",
    mana_cost="{W}",
    text="Flash\nWhen this Equipment enters, attach it to target creature you control. That creature gains first strike until end of turn.\nEquipped creature gets +1/+0.\nEquip {3}",
    subtypes={"Equipment"},
    setup_interceptors=squires_lightblade_setup,
)

STARFIELD_SHEPHERD = make_creature(
    name="Starfield Shepherd",
    power=3, toughness=2,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nWhen this creature enters, search your library for a basic Plains card or a creature card with mana value 1 or less, reveal it, put it into your hand, then shuffle.\nWarp {1}{W} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{1}{W}", inner_setup=starfield_shepherd_setup),
)

STARFIGHTER_PILOT = make_creature(
    name="Starfighter Pilot",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Pilot"},
    text="Whenever this creature becomes tapped, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    setup_interceptors=starfighter_pilot_setup,
)

STARPORT_SECURITY = make_artifact_creature(
    name="Starport Security",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Robot", "Soldier"},
    text="{3}{W}, {T}: Tap another target creature. This ability costs {2} less to activate if you control a creature with a +1/+1 counter on it.",
    setup_interceptors=starport_security_setup,
)

SUNSTAR_CHAPLAIN = make_creature(
    name="Sunstar Chaplain",
    power=3, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Human"},
    text="At the beginning of your end step, if you control two or more tapped creatures, put a +1/+1 counter on target creature you control.\n{2}, Remove a +1/+1 counter from a creature you control: Tap target artifact or creature.",
    setup_interceptors=sunstar_chaplain_setup,
)

SUNSTAR_EXPANSIONIST = make_creature(
    name="Sunstar Expansionist",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="When this creature enters, if an opponent controls more lands than you, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")\nLandfall — Whenever a land you control enters, this creature gets +1/+0 until end of turn.",
    setup_interceptors=sunstar_expansionist_setup,
)

SUNSTAR_LIGHTSMITH = make_creature(
    name="Sunstar Lightsmith",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Artificer", "Human"},
    text="Whenever you cast your second spell each turn, put a +1/+1 counter on this creature and draw a card.",
    setup_interceptors=sunstar_lightsmith_setup,
)

WEDGELIGHT_RAMMER = make_artifact(
    name="Wedgelight Rammer",
    mana_cost="{3}{W}",
    text="When this Spacecraft enters, create a 2/2 colorless Robot artifact creature token.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 9+.)\n9+ | Flying, first strike",
    subtypes={"Spacecraft"},
    setup_interceptors=wedgelight_rammer_setup,
)

WEFTBLADE_ENHANCER = make_creature(
    name="Weftblade Enhancer",
    power=3, toughness=4,
    mana_cost="{5}{W}",
    colors={Color.WHITE},
    subtypes={"Artificer", "Drix"},
    text="When this creature enters, put a +1/+1 counter on each of up to two target creatures.\nWarp {2}{W} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{2}{W}", inner_setup=weftblade_enhancer_setup),
)

ZEALOUS_DISPLAY = make_instant(
    name="Zealous Display",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +2/+0 until end of turn. If it's not your turn, untap those creatures.",
)

ANNUL = make_instant(
    name="Annul",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Counter target artifact or enchantment spell.",
)

ATOMIC_MICROSIZER = make_artifact(
    name="Atomic Microsizer",
    mana_cost="{U}",
    text="Equipped creature gets +1/+0.\nWhenever equipped creature attacks, choose up to one target creature. That creature can't be blocked this turn and has base power and toughness 1/1 until end of turn.\nEquip {2}",
    subtypes={"Equipment"},
    setup_interceptors=atomic_microsizer_setup,
)

CEREBRAL_DOWNLOAD = make_instant(
    name="Cerebral Download",
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    text="Surveil X, where X is the number of artifacts you control. Then draw three cards. (To surveil X, look at the top X cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
)

CLOUDSCULPT_TECHNICIAN = make_creature(
    name="Cloudsculpt Technician",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Artificer", "Jellyfish"},
    text="Flying\nAs long as you control an artifact, this creature gets +1/+0.",
    setup_interceptors=cloudsculpt_technician_setup,
)

CODECRACKER_HOUND = make_creature(
    name="Codecracker Hound",
    power=2, toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Dog"},
    text="When this creature enters, look at the top two cards of your library. Put one into your hand and the other into your graveyard.\nWarp {2}{U} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{2}{U}", inner_setup=codecracker_hound_setup),
)

CONSULT_THE_STAR_CHARTS = make_instant(
    name="Consult the Star Charts",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Kicker {1}{U} (You may pay an additional {1}{U} as you cast this spell.)\nLook at the top X cards of your library, where X is the number of lands you control. Put one of those cards into your hand. If this spell was kicked, put two of those cards into your hand instead. Put the rest on the bottom of your library in a random order.",
)

CRYOGEN_RELIC = make_artifact(
    name="Cryogen Relic",
    mana_cost="{1}{U}",
    text="When this artifact enters or leaves the battlefield, draw a card.\n{1}{U}, Sacrifice this artifact: Put a stun counter on up to one target tapped creature. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
    setup_interceptors=cryogen_relic_setup,
)

CRYOSHATTER = make_enchantment(
    name="Cryoshatter",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Enchant creature\nEnchanted creature gets -5/-0.\nWhen enchanted creature becomes tapped or is dealt damage, destroy it.",
    subtypes={"Aura"},
    setup_interceptors=cryoshatter_setup,
)

DESCULPTING_BLAST = make_instant(
    name="Desculpting Blast",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target nonland permanent to its owner's hand. If it was attacking, create a 1/1 colorless Drone artifact creature token with flying and \"This token can block only creatures with flying.\"",
)

DIVERT_DISASTER = make_instant(
    name="Divert Disaster",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {2}. If they do, you create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

EMISSARY_ESCORT = make_artifact_creature(
    name="Emissary Escort",
    power=0, toughness=4,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Robot", "Soldier"},
    text="This creature gets +X/+0, where X is the greatest mana value among other artifacts you control.",
    setup_interceptors=emissary_escort_setup,
)

GIGASTORM_TITAN = make_creature(
    name="Gigastorm Titan",
    power=4, toughness=4,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="This spell costs {3} less to cast if you've cast another spell this turn.",
    setup_interceptors=gigastorm_titan_setup,
)

ILLVOI_GALEBLADE = make_creature(
    name="Illvoi Galeblade",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Jellyfish", "Warrior"},
    text="Flash\nFlying\n{2}, Sacrifice this creature: Draw a card.",
)

ILLVOI_INFILTRATOR = make_creature(
    name="Illvoi Infiltrator",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Jellyfish", "Rogue"},
    text="This creature can't be blocked if you've cast two or more spells this turn.\nWhenever this creature deals combat damage to a player, draw a card.",
    setup_interceptors=illvoi_infiltrator_setup,
)

ILLVOI_LIGHT_JAMMER = make_artifact(
    name="Illvoi Light Jammer",
    mana_cost="{1}{U}",
    text="Flash\nWhen this Equipment enters, attach it to target creature you control. That creature gains hexproof until end of turn. (It can't be the target of spells or abilities your opponents control.)\nEquipped creature gets +1/+2.\nEquip {3}",
    subtypes={"Equipment"},
    setup_interceptors=illvoi_light_jammer_setup,
)

ILLVOI_OPERATIVE = make_creature(
    name="Illvoi Operative",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Jellyfish", "Rogue"},
    text="Whenever you cast your second spell each turn, put a +1/+1 counter on this creature.",
    setup_interceptors=illvoi_operative_setup,
)

LOST_IN_SPACE = make_instant(
    name="Lost in Space",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Target artifact or creature's owner puts it on their choice of the top or bottom of their library. Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

MECHAN_ASSEMBLER = make_artifact_creature(
    name="Mechan Assembler",
    power=4, toughness=4,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Artificer", "Robot"},
    text="Whenever another artifact you control enters, create a 2/2 colorless Robot artifact creature token. This ability triggers only once each turn.",
    setup_interceptors=mechan_assembler_setup,
)

MECHAN_NAVIGATOR = make_artifact_creature(
    name="Mechan Navigator",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Pilot", "Robot"},
    text="Whenever this creature becomes tapped, draw a card, then discard a card.",
    setup_interceptors=mechan_navigator_setup,
)

MECHAN_SHIELDMATE = make_artifact_creature(
    name="Mechan Shieldmate",
    power=3, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Robot", "Soldier"},
    text="Defender\nAs long as an artifact entered the battlefield under your control this turn, this creature can attack as though it didn't have defender.",
    setup_interceptors=mechan_shieldmate_setup,
)

MECHANOZOA = make_artifact_creature(
    name="Mechanozoa",
    power=5, toughness=5,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Jellyfish", "Robot"},
    text="When this creature enters, tap target artifact or creature an opponent controls and put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nWarp {2}{U} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{2}{U}", inner_setup=mechanozoa_setup),
)

MENTAL_MODULATION = make_instant(
    name="Mental Modulation",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="This spell costs {1} less to cast during your turn.\nTap target artifact or creature.\nDraw a card.",
)

MMMENON_THE_RIGHT_HAND = make_creature(
    name="Mm'menon, the Right Hand",
    power=3, toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Advisor", "Jellyfish"},
    supertypes={"Legendary"},
    text="Flying\nYou may look at the top card of your library any time.\nYou may cast artifact spells from the top of your library.\nArtifacts you control have \"{T}: Add {U}. Spend this mana only to cast a spell from anywhere other than your hand.\"",
    setup_interceptors=mmmenon_the_right_hand_setup,
)

MOONLIT_MEDITATION = make_enchantment(
    name="Moonlit Meditation",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Enchant artifact or creature you control\nThe first time you would create one or more tokens each turn, you may instead create that many tokens that are copies of enchanted permanent.",
    subtypes={"Aura"},
    setup_interceptors=moonlit_meditation_setup,
)

MOUTH_OF_THE_STORM = make_creature(
    name="Mouth of the Storm",
    power=6, toughness=6,
    mana_cost="{6}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="Flying\nWard {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nWhen this creature enters, creatures your opponents control get -3/-0 until your next turn.",
    setup_interceptors=mouth_of_the_storm_setup,
)

NANOFORM_SENTINEL = make_artifact_creature(
    name="Nanoform Sentinel",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Robot"},
    text="Whenever this creature becomes tapped, untap another target permanent. This ability triggers only once each turn.",
    setup_interceptors=nanoform_sentinel_setup,
)

QUANTUM_RIDDLER = make_creature(
    name="Quantum Riddler",
    power=4, toughness=6,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Sphinx"},
    text="Flying\nWhen this creature enters, draw a card.\nAs long as you have one or fewer cards in hand, if you would draw one or more cards, you draw that many cards plus one instead.\nWarp {1}{U}",
    setup_interceptors=make_warp_setup("{1}{U}", inner_setup=quantum_riddler_setup),
)

SCOUR_FOR_SCRAP = make_instant(
    name="Scour for Scrap",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Choose one or both —\n• Search your library for an artifact card, reveal it, put it into your hand, then shuffle.\n• Return target artifact card from your graveyard to your hand.",
)

SELFCRAFT_MECHAN = make_artifact_creature(
    name="Selfcraft Mechan",
    power=3, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Artificer", "Robot"},
    text="When this creature enters, you may sacrifice an artifact. When you do, put a +1/+1 counter on target creature and draw a card.",
    setup_interceptors=selfcraft_mechan_setup,
)

SINISTER_CRYOLOGIST = make_creature(
    name="Sinister Cryologist",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Jellyfish", "Wizard"},
    text="When this creature enters, target creature an opponent controls gets -3/-0 until end of turn.\nWarp {U} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{U}", inner_setup=sinister_cryologist_setup),
)

SPECIMEN_FREIGHTER = make_artifact(
    name="Specimen Freighter",
    mana_cost="{5}{U}",
    text="When this Spacecraft enters, return up to two target non-Spacecraft creatures to their owners' hands.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 9+.)\n9+ | Flying\nWhenever this Spacecraft attacks, defending player mills four cards.",
    subtypes={"Spacecraft"},
    setup_interceptors=specimen_freighter_setup,
)

STARBREACH_WHALE = make_creature(
    name="Starbreach Whale",
    power=3, toughness=5,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Whale"},
    text="Flying\nWhen this creature enters, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\nWarp {1}{U} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{1}{U}", inner_setup=starbreach_whale_setup),
)

STARFIELD_VOCALIST = make_creature(
    name="Starfield Vocalist",
    power=3, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Bard", "Human"},
    text="If a permanent entering the battlefield causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.\nWarp {1}{U} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{1}{U}", inner_setup=starfield_vocalist_setup),
)

STARWINDER = make_creature(
    name="Starwinder",
    power=7, toughness=7,
    mana_cost="{5}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Leviathan"},
    text="Whenever a creature you control deals combat damage to a player, you may draw that many cards.\nWarp {2}{U}{U} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{2}{U}{U}", inner_setup=starwinder_setup),
)

STEELSWARM_OPERATOR = make_artifact_creature(
    name="Steelswarm Operator",
    power=1, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Robot", "Soldier"},
    text="Flying\n{T}: Add {U}. Spend this mana only to cast an artifact spell.\n{T}: Add {U}{U}. Spend this mana only to activate abilities of artifact sources.",
)

SYNTHESIZER_LABSHIP = make_artifact(
    name="Synthesizer Labship",
    mana_cost="{U}",
    text="Station (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 9+.)\n2+ | At the beginning of combat on your turn, up to one other target artifact you control becomes an artifact creature with base power and toughness 2/2 and gains flying until end of turn.\n9+ | Flying, vigilance",
    subtypes={"Spacecraft"},
    setup_interceptors=synthesizer_labship_setup,
)

TRACTOR_BEAM = make_enchantment(
    name="Tractor Beam",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Enchant creature or Spacecraft\nWhen this Aura enters, tap enchanted permanent.\nYou control enchanted permanent.\nEnchanted permanent doesn't untap during its controller's untap step.",
    subtypes={"Aura"},
    setup_interceptors=tractor_beam_setup,
)

UNRAVEL = make_instant(
    name="Unravel",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell. If the amount of mana spent to cast that spell was less than its mana value, you draw a card.",
)

UTHROS_PSIONICIST = make_creature(
    name="Uthros Psionicist",
    power=2, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Jellyfish", "Scientist"},
    text="The second spell you cast each turn costs {2} less to cast.",
    setup_interceptors=uthros_psionicist_setup,
)

UTHROS_SCANSHIP = make_artifact(
    name="Uthros Scanship",
    mana_cost="{3}{U}",
    text="When this Spacecraft enters, draw two cards, then discard a card.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 8+.)\n8+ | Flying",
    subtypes={"Spacecraft"},
    setup_interceptors=uthros_scanship_setup,
)

WEFTWALKING = make_enchantment(
    name="Weftwalking",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="When this enchantment enters, if you cast it, shuffle your hand and graveyard into your library, then draw seven cards.\nThe first spell each player casts during each of their turns may be cast without paying its mana cost.",
    setup_interceptors=weftwalking_setup,
)

ALPHARAEL_STONECHOSEN = make_creature(
    name="Alpharael, Stonechosen",
    power=3, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Human"},
    supertypes={"Legendary"},
    text="Ward—Discard a card at random.\nVoid — Whenever Alpharael attacks, if a nonland permanent left the battlefield this turn or a spell was warped this turn, defending player loses half their life, rounded up.",
    setup_interceptors=alpharael_stonechosen_setup,
)

ARCHENEMYS_CHARM = make_instant(
    name="Archenemy's Charm",
    mana_cost="{B}{B}{B}",
    colors={Color.BLACK},
    text="Choose one —\n• Exile target creature or planeswalker.\n• Return one or two target creature and/or planeswalker cards from your graveyard to your hand.\n• Put two +1/+1 counters on target creature you control. It gains lifelink until end of turn.",
)

BEAMSAW_PROSPECTOR = make_creature(
    name="Beamsaw Prospector",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Artificer", "Human"},
    text="When this creature dies, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
    setup_interceptors=beamsaw_prospector_setup,
)

BLADE_OF_THE_SWARM = make_creature(
    name="Blade of the Swarm",
    power=3, toughness=1,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Insect"},
    text="When this creature enters, choose one —\n• Put two +1/+1 counters on this creature.\n• Put target exiled card with warp on the bottom of its owner's library.",
    setup_interceptors=blade_of_the_swarm_setup,
)

CHORALE_OF_THE_VOID = make_enchantment(
    name="Chorale of the Void",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Enchant creature you control\nWhenever enchanted creature attacks, put target creature card from defending player's graveyard onto the battlefield under your control tapped and attacking.\nVoid — At the beginning of your end step, sacrifice this Aura unless a nonland permanent left the battlefield this turn or a spell was warped this turn.",
    subtypes={"Aura"},
    setup_interceptors=chorale_of_the_void_setup,
)

COMET_CRAWLER = make_creature(
    name="Comet Crawler",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Insect"},
    text="Lifelink\nWhenever this creature attacks, you may sacrifice another creature or artifact. If you do, this creature gets +2/+0 until end of turn.",
    setup_interceptors=comet_crawler_setup,
)

DARK_ENDURANCE = make_instant(
    name="Dark Endurance",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="This spell costs {1} less to cast if it targets a blocking creature.\nTarget creature gets +2/+0 and gains indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)",
)

DECODE_TRANSMISSIONS = make_sorcery(
    name="Decode Transmissions",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="You draw two cards and lose 2 life.\nVoid — If a nonland permanent left the battlefield this turn or a spell was warped this turn, instead you draw two cards and each opponent loses 2 life.",
)

DEPRESSURIZE = make_instant(
    name="Depressurize",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -3/-0 until end of turn. Then if that creature's power is 0 or less, destroy it.",
)

DUBIOUS_DELICACY = make_artifact(
    name="Dubious Delicacy",
    mana_cost="{2}{B}",
    text="Flash\nWhen this artifact enters, up to one target creature gets -3/-3 until end of turn.\n{2}, {T}, Sacrifice this artifact: You gain 3 life.\n{2}, {T}, Sacrifice this artifact: Target opponent loses 3 life.",
    subtypes={"Food"},
    setup_interceptors=dubious_delicacy_setup,
)

ELEGY_ACOLYTE = make_creature(
    name="Elegy Acolyte",
    power=4, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Human"},
    text="Lifelink\nWhenever one or more creatures you control deal combat damage to a player, you draw a card and lose 1 life.\nVoid — At the beginning of your end step, if a nonland permanent left the battlefield this turn or a spell was warped this turn, create a 2/2 colorless Robot artifact creature token.",
    setup_interceptors=elegy_acolyte_setup,
)

EMBRACE_OBLIVION = make_sorcery(
    name="Embrace Oblivion",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, sacrifice an artifact or creature.\nDestroy target creature or Spacecraft.",
)

ENTROPIC_BATTLECRUISER = make_artifact(
    name="Entropic Battlecruiser",
    mana_cost="{3}{B}",
    text="Station (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 8+.)\n1+ | Whenever an opponent discards a card, they lose 3 life.\n8+ | Flying, deathtouch\nWhenever this Spacecraft attacks, each opponent discards a card. Each opponent who can't loses 3 life.",
    subtypes={"Spacecraft"},
    setup_interceptors=entropic_battlecruiser_setup,
)

FALLERS_FAITHFUL = make_creature(
    name="Faller's Faithful",
    power=3, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard"},
    text="When this creature enters, destroy up to one other target creature. If that creature wasn't dealt damage this turn, its controller draws two cards.",
    setup_interceptors=fallers_faithful_setup,
)

FELL_GRAVSHIP = make_artifact(
    name="Fell Gravship",
    mana_cost="{2}{B}",
    text="When this Spacecraft enters, mill three cards, then return a creature or Spacecraft card from your graveyard to your hand.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 8+.)\n8+ | Flying, lifelink",
    subtypes={"Spacecraft"},
    setup_interceptors=fell_gravship_setup,
)

GRAVBLADE_HEAVY = make_creature(
    name="Gravblade Heavy",
    power=3, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    text="As long as you control an artifact, this creature gets +1/+0 and has deathtouch.",
    setup_interceptors=gravblade_heavy_setup,
)

GRAVKILL = make_instant(
    name="Gravkill",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Exile target creature or Spacecraft.",
)

GRAVPACK_MONOIST = make_creature(
    name="Gravpack Monoist",
    power=2, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Scout"},
    text="Flying\nWhen this creature dies, create a tapped 2/2 colorless Robot artifact creature token.",
    setup_interceptors=gravpack_monoist_setup,
)

HULLCARVER = make_artifact_creature(
    name="Hullcarver",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Robot"},
    text="Deathtouch",
)

HYLDERBLADE = make_artifact(
    name="Hylderblade",
    mana_cost="{B}",
    text="Equipped creature gets +3/+1.\nVoid — At the beginning of your end step, if a nonland permanent left the battlefield this turn or a spell was warped this turn, attach this Equipment to target creature you control.\nEquip {4} ({4}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=hylderblade_setup,
)

HYMN_OF_THE_FALLER = make_sorcery(
    name="Hymn of the Faller",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Surveil 1, then you draw a card and lose 1 life. (To surveil 1, look at the top card of your library. You may put it into your graveyard.)\nVoid — If a nonland permanent left the battlefield this turn or a spell was warped this turn, draw another card.",
)

INSATIABLE_SKITTERMAW = make_creature(
    name="Insatiable Skittermaw",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Insect"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nVoid — At the beginning of your end step, if a nonland permanent left the battlefield this turn or a spell was warped this turn, put a +1/+1 counter on this creature.",
    setup_interceptors=insatiable_skittermaw_setup,
)

LIGHTLESS_EVANGEL = make_creature(
    name="Lightless Evangel",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Vampire"},
    text="Whenever you sacrifice another creature or artifact, put a +1/+1 counter on this creature.",
    setup_interceptors=lightless_evangel_setup,
)

MONOIST_CIRCUITFEEDER = make_artifact_creature(
    name="Monoist Circuit-Feeder",
    power=4, toughness=4,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Nautilus"},
    text="Flying\nWhen this creature enters, until end of turn, target creature you control gets +X/+0 and target creature an opponent controls gets -0/-X, where X is the number of artifacts you control.",
    setup_interceptors=monoist_circuitfeeder_setup,
)

MONOIST_SENTRY = make_artifact_creature(
    name="Monoist Sentry",
    power=4, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Robot"},
    text="Defender",
)

PERIGEE_BECKONER = make_creature(
    name="Perigee Beckoner",
    power=4, toughness=5,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="When this creature enters, until end of turn, another target creature you control gets +2/+0 and gains \"When this creature dies, return it to the battlefield tapped under its owner's control.\"\nWarp {1}{B} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{1}{B}", inner_setup=perigee_beckoner_setup),
)

REQUIEM_MONOLITH = make_artifact(
    name="Requiem Monolith",
    mana_cost="{2}{B}",
    text="{T}: Until end of turn, target creature gains \"Whenever this creature is dealt damage, you draw that many cards and lose that much life.\" That creature's controller may have this artifact deal 1 damage to it. Activate only as a sorcery.",
    setup_interceptors=requiem_monolith_setup,
)

SCROUNGE_FOR_ETERNITY = make_sorcery(
    name="Scrounge for Eternity",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, sacrifice an artifact or creature.\nReturn target creature or Spacecraft card with mana value 5 or less from your graveyard to the battlefield. Then create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

SOTHERA_THE_SUPERVOID = make_enchantment(
    name="Sothera, the Supervoid",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Whenever a creature you control dies, each opponent chooses a creature they control and exiles it.\nAt the beginning of your end step, if a player controls no creatures, sacrifice Sothera, then put a creature card exiled with it onto the battlefield under your control with two additional +1/+1 counters on it.",
    supertypes={"Legendary"},
    setup_interceptors=sothera_the_supervoid_setup,
)

SUNSET_SABOTEUR = make_creature(
    name="Sunset Saboteur",
    power=4, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="Menace\nWard—Discard a card.\nWhenever this creature attacks, put a +1/+1 counter on target creature an opponent controls.",
    setup_interceptors=sunset_saboteur_setup,
)

SUSURIAN_DIRGECRAFT = make_artifact(
    name="Susurian Dirgecraft",
    mana_cost="{4}{B}",
    text="When this Spacecraft enters, each opponent sacrifices a nontoken creature of their choice.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 7+.)\n7+ | Flying",
    subtypes={"Spacecraft"},
    setup_interceptors=susurian_dirgecraft_setup,
)

SUSURIAN_VOIDBORN = make_creature(
    name="Susurian Voidborn",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Soldier", "Vampire"},
    text="Whenever this creature or another creature or artifact you control dies, target opponent loses 1 life and you gain 1 life.\nWarp {B} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{B}", inner_setup=susurian_voidborn_setup),
)

SWARM_CULLER = make_creature(
    name="Swarm Culler",
    power=2, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Insect", "Warrior"},
    text="Flying\nWhenever this creature becomes tapped, you may sacrifice another creature or artifact. If you do, draw a card.",
    setup_interceptors=swarm_culler_setup,
)

TEMPORAL_INTERVENTION = make_sorcery(
    name="Temporal Intervention",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Void — This spell costs {2} less to cast if a nonland permanent left the battlefield this turn or a spell was warped this turn.\nTarget opponent reveals their hand. You choose a nonland card from it. That player discards that card.",
)

TIMELINE_CULLER = make_creature(
    name="Timeline Culler",
    power=2, toughness=2,
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    subtypes={"Drix", "Warlock"},
    text="Haste\nYou may cast this card from your graveyard using its warp ability.\nWarp—{B}, Pay 2 life. (You may cast this card from your hand or graveyard for its warp cost. If you do, exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=timeline_culler_setup,
)

TRAGIC_TRAJECTORY = make_sorcery(
    name="Tragic Trajectory",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn.\nVoid — That creature gets -10/-10 until end of turn instead if a nonland permanent left the battlefield this turn or a spell was warped this turn.",
)

UMBRAL_COLLAR_ZEALOT = make_creature(
    name="Umbral Collar Zealot",
    power=3, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Human"},
    text="Sacrifice another creature or artifact: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    setup_interceptors=umbral_collar_zealot_setup,
)

VIRUS_BEETLE = make_artifact_creature(
    name="Virus Beetle",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Insect"},
    text="When this creature enters, each opponent discards a card.",
    setup_interceptors=virus_beetle_setup,
)

VOIDFORGED_TITAN = make_artifact_creature(
    name="Voidforged Titan",
    power=5, toughness=4,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Robot", "Warrior"},
    text="Void — At the beginning of your end step, if a nonland permanent left the battlefield this turn or a spell was warped this turn, you draw a card and lose 1 life.",
    setup_interceptors=voidforged_titan_setup,
)

VOTE_OUT = make_sorcery(
    name="Vote Out",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nDestroy target creature.",
)

XUIFIT_OSTEOHARMONIST = make_creature(
    name="Xu-Ifit, Osteoharmonist",
    power=2, toughness=3,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="{T}: Return target creature card from your graveyard to the battlefield. It's a Skeleton in addition to its other types and has no abilities. Activate only as a sorcery.",
    setup_interceptors=xuifit_osteoharmonist_setup,
)

ZERO_POINT_BALLAD = make_sorcery(
    name="Zero Point Ballad",
    mana_cost="{X}{B}",
    colors={Color.BLACK},
    text="Destroy all creatures with toughness X or less. You lose X life. If X is 6 or more, return a creature card put into a graveyard this way to the battlefield under your control.",
)

BOMBARD = make_instant(
    name="Bombard",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Bombard deals 4 damage to target creature.",
)

CUT_PROPULSION = make_instant(
    name="Cut Propulsion",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Target creature deals damage to itself equal to its power. If that creature has flying, it deals twice that much damage to itself instead.",
)

DEBRIS_FIELD_CRUSHER = make_artifact(
    name="Debris Field Crusher",
    mana_cost="{4}{R}",
    text="When this Spacecraft enters, it deals 3 damage to any target.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 8+.)\n8+ | Flying\n{1}{R}: This Spacecraft gets +2/+0 until end of turn.",
    subtypes={"Spacecraft"},
    setup_interceptors=debris_field_crusher_setup,
)

DEVASTATING_ONSLAUGHT = make_sorcery(
    name="Devastating Onslaught",
    mana_cost="{X}{X}{R}",
    colors={Color.RED},
    text="Create X tokens that are copies of target artifact or creature you control. Those tokens gain haste until end of turn. Sacrifice them at the beginning of the next end step.",
)

DRILL_TOO_DEEP = make_instant(
    name="Drill Too Deep",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Choose one —\n• Put five charge counters on target Spacecraft or Planet you control.\n• Destroy target artifact.",
)

FRONTLINE_WARRAGER = make_creature(
    name="Frontline War-Rager",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Kavu", "Soldier"},
    text="At the beginning of your end step, if you control two or more tapped creatures, put a +1/+1 counter on this creature.",
    setup_interceptors=frontline_warrager_setup,
)

FULL_BORE = make_instant(
    name="Full Bore",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature you control gets +3/+2 until end of turn. If that creature was cast for its warp cost, it also gains trample and haste until end of turn.",
)

GALVANIZING_SAWSHIP = make_artifact(
    name="Galvanizing Sawship",
    mana_cost="{5}{R}",
    text="Station (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 3+.)\n3+ | Flying, haste",
    subtypes={"Spacecraft"},
    setup_interceptors=galvanizing_sawship_setup,
)

INVASIVE_MANEUVERS = make_instant(
    name="Invasive Maneuvers",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Invasive Maneuvers deals 3 damage to target creature. It deals 5 damage instead if you control a Spacecraft.",
)

KAV_LANDSEEKER = make_creature(
    name="Kav Landseeker",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Kavu", "Soldier"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhen this creature enters, create a Lander token. At the beginning of the end step on your next turn, sacrifice that token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
    setup_interceptors=kav_landseeker_setup,
)

KAVARON_HARRIER = make_artifact_creature(
    name="Kavaron Harrier",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Robot", "Soldier"},
    text="Whenever this creature attacks, you may pay {2}. If you do, create a 2/2 colorless Robot artifact creature token that's tapped and attacking. Sacrifice that token at end of combat.",
    setup_interceptors=kavaron_harrier_setup,
)

KAVARON_SKYWARDEN = make_creature(
    name="Kavaron Skywarden",
    power=4, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Kavu", "Soldier"},
    text="Reach\nVoid — At the beginning of your end step, if a nonland permanent left the battlefield this turn or a spell was warped this turn, put a +1/+1 counter on this creature.",
    setup_interceptors=kavaron_skywarden_setup,
)

KAVARON_TURBODRONE = make_artifact_creature(
    name="Kavaron Turbodrone",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Robot", "Scout"},
    text="{T}: Target creature you control gets +1/+1 and gains haste until end of turn. Activate only as a sorcery.",
    setup_interceptors=kavaron_turbodrone_setup,
)

LITHOBRAKING = make_instant(
    name="Lithobraking",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Create a Lander token. Then you may sacrifice an artifact. When you do, Lithobraking deals 2 damage to each creature. (A Lander token is an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

MELDED_MOXITE = make_artifact(
    name="Melded Moxite",
    mana_cost="{1}{R}",
    text="When this artifact enters, you may discard a card. If you do, draw two cards.\n{3}, Sacrifice this artifact: Create a tapped 2/2 colorless Robot artifact creature token.",
    setup_interceptors=melded_moxite_setup,
)

MEMORIAL_TEAM_LEADER = make_creature(
    name="Memorial Team Leader",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Kavu", "Soldier"},
    text="During your turn, other creatures you control get +1/+0.\nWarp {1}{R} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{1}{R}", inner_setup=memorial_team_leader_setup),
)

MEMORIAL_VAULT = make_artifact(
    name="Memorial Vault",
    mana_cost="{3}{R}",
    text="{T}, Sacrifice another artifact: Exile the top X cards of your library, where X is one plus the mana value of the sacrificed artifact. You may play those cards this turn.",
)

MOLECULAR_MODIFIER = make_creature(
    name="Molecular Modifier",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Artificer", "Kavu"},
    text="At the beginning of combat on your turn, target creature you control gets +1/+0 and gains first strike until end of turn.",
    setup_interceptors=molecular_modifier_setup,
)

NEBULA_DRAGON = make_creature(
    name="Nebula Dragon",
    power=4, toughness=4,
    mana_cost="{6}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\nWhen this creature enters, it deals 3 damage to any target.",
    setup_interceptors=nebula_dragon_setup,
)

NOVA_HELLKITE = make_creature(
    name="Nova Hellkite",
    power=4, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying, haste\nWhen this creature enters, it deals 1 damage to target creature an opponent controls.\nWarp {2}{R} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{2}{R}", inner_setup=nova_hellkite_setup),
)

ORBITAL_PLUNGE = make_sorcery(
    name="Orbital Plunge",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Orbital Plunge deals 6 damage to target creature. If excess damage was dealt this way, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

OREPLATE_PANGOLIN = make_artifact_creature(
    name="Oreplate Pangolin",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Pangolin", "Robot"},
    text="Whenever another artifact you control enters, you may pay {1}. If you do, put a +1/+1 counter on this creature.",
    setup_interceptors=oreplate_pangolin_setup,
)

PAIN_FOR_ALL = make_enchantment(
    name="Pain for All",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Enchant creature you control\nWhen this Aura enters, enchanted creature deals damage equal to its power to any other target.\nWhenever enchanted creature is dealt damage, it deals that much damage to each opponent.",
    subtypes={"Aura"},
    setup_interceptors=pain_for_all_setup,
)

PLASMA_BOLT = make_sorcery(
    name="Plasma Bolt",
    mana_cost="{R}",
    colors={Color.RED},
    text="Plasma Bolt deals 2 damage to any target.\nVoid — Plasma Bolt deals 3 damage instead if a nonland permanent left the battlefield this turn or a spell was warped this turn.",
)

POSSIBILITY_TECHNICIAN = make_creature(
    name="Possibility Technician",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Artificer", "Kavu"},
    text="Whenever this creature or another Kavu you control enters, exile the top card of your library. For as long as that card remains exiled, you may play it if you control a Kavu.\nWarp {1}{R} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{1}{R}", inner_setup=possibility_technician_setup),
)

RED_TIGER_MECHAN = make_artifact_creature(
    name="Red Tiger Mechan",
    power=3, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Cat", "Robot"},
    text="Haste\nWarp {1}{R} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{1}{R}", inner_setup=red_tiger_mechan_setup),
)

REMNANT_ELEMENTAL = make_creature(
    name="Remnant Elemental",
    power=0, toughness=4,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Reach\nLandfall — Whenever a land you control enters, this creature gets +2/+0 until end of turn.",
    setup_interceptors=remnant_elemental_setup,
)

RIG_FOR_WAR = make_instant(
    name="Rig for War",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains first strike and reach until end of turn.",
)

ROVING_ACTUATOR = make_artifact_creature(
    name="Roving Actuator",
    power=3, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Robot"},
    text="Void — When this creature enters, if a nonland permanent left the battlefield this turn or a spell was warped this turn, exile up to one target instant or sorcery card with mana value 2 or less from your graveyard. Copy it. You may cast the copy without paying its mana cost.",
    setup_interceptors=roving_actuator_setup,
)

RUINOUS_RAMPAGE = make_sorcery(
    name="Ruinous Rampage",
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    text="Choose one —\n• Ruinous Rampage deals 3 damage to each opponent.\n• Exile all artifacts with mana value 3 or less.",
)

RUST_HARVESTER = make_artifact_creature(
    name="Rust Harvester",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Robot"},
    text="Menace\n{2}, {T}, Exile an artifact card from your graveyard: Put a +1/+1 counter on this creature, then it deals damage equal to its power to any target.",
)

SLAGDRILL_SCRAPPER = make_artifact_creature(
    name="Slagdrill Scrapper",
    power=1, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Robot", "Scout"},
    text="{2}, {T}, Sacrifice another artifact or land: Draw a card.",
)

SYSTEMS_OVERRIDE = make_sorcery(
    name="Systems Override",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Gain control of target artifact or creature until end of turn. Untap that permanent. It gains haste until end of turn. If it's a Spacecraft, put ten charge counters on it. If you do, remove ten charge counters from it at the beginning of the next end step.",
)

TANNUK_STEADFAST_SECOND = make_creature(
    name="Tannuk, Steadfast Second",
    power=3, toughness=5,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Kavu", "Pilot"},
    supertypes={"Legendary"},
    text="Other creatures you control have haste.\nArtifact cards and red creature cards in your hand have warp {2}{R}. (You may cast a card from your hand for its warp cost. Exile that permanent at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=tannuk_steadfast_second_setup,
)

TERMINAL_VELOCITY = make_sorcery(
    name="Terminal Velocity",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="You may put an artifact or creature card from your hand onto the battlefield. That permanent gains haste, \"When this permanent leaves the battlefield, it deals damage equal to its mana value to each creature,\" and \"At the beginning of your end step, sacrifice this permanent.\"",
)

TERRAPACT_INTIMIDATOR = make_creature(
    name="Terrapact Intimidator",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Kavu", "Scout"},
    text="When this creature enters, target opponent may have you create two Lander tokens. If they don't, put two +1/+1 counters on this creature. (A Lander token is an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
    setup_interceptors=terrapact_intimidator_setup,
)

TERRITORIAL_BRUNTAR = make_creature(
    name="Territorial Bruntar",
    power=6, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Beast"},
    text="Reach\nLandfall — Whenever a land you control enters, exile cards from the top of your library until you exile a nonland card. You may cast that card this turn.",
    setup_interceptors=territorial_bruntar_setup,
)

VAULTGUARD_TROOPER = make_creature(
    name="Vaultguard Trooper",
    power=5, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Kavu", "Soldier"},
    text="At the beginning of your end step, if you control two or more tapped creatures, you may discard your hand. If you do, draw two cards.",
    setup_interceptors=vaultguard_trooper_setup,
)

WARMAKER_GUNSHIP = make_artifact(
    name="Warmaker Gunship",
    mana_cost="{2}{R}",
    text="When this Spacecraft enters, it deals damage equal to the number of artifacts you control to target creature an opponent controls.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 6+.)\n6+ | Flying",
    subtypes={"Spacecraft"},
    setup_interceptors=warmaker_gunship_setup,
)

WEAPONS_MANUFACTURING = make_enchantment(
    name="Weapons Manufacturing",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Whenever a nontoken artifact you control enters, create a colorless artifact token named Munitions with \"When this token leaves the battlefield, it deals 2 damage to any target.\"",
    setup_interceptors=weapons_manufacturing_setup,
)

WEFTSTALKER_ARDENT = make_creature(
    name="Weftstalker Ardent",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Artificer", "Drix"},
    text="Whenever another creature or artifact you control enters, this creature deals 1 damage to each opponent.\nWarp {R} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{R}", inner_setup=weftstalker_ardent_setup),
)

ZOOKEEPER_MECHAN = make_artifact_creature(
    name="Zookeeper Mechan",
    power=1, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Robot"},
    text="{T}: Add {R}.\n{6}{R}: Target creature you control gets +4/+0 until end of turn. Activate only as a sorcery.",
    setup_interceptors=zookeeper_mechan_setup,
)

ATMOSPHERIC_GREENHOUSE = make_artifact(
    name="Atmospheric Greenhouse",
    mana_cost="{4}{G}",
    text="When this Spacecraft enters, put a +1/+1 counter on each creature you control.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 8+.)\n8+ | Flying, trample",
    subtypes={"Spacecraft"},
    setup_interceptors=atmospheric_greenhouse_setup,
)

BIOENGINEERED_FUTURE = make_enchantment(
    name="Bioengineered Future",
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")\nEach creature you control enters with an additional +1/+1 counter on it for each land that entered the battlefield under your control this turn.",
    setup_interceptors=bioengineered_future_setup,
)

BIOSYNTHIC_BURST = make_instant(
    name="Biosynthic Burst",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Put a +1/+1 counter on target creature you control. It gains reach, trample, and indestructible until end of turn. Untap it. (Damage and effects that say \"destroy\" don't destroy it.)",
)

BLOOMING_STINGER = make_creature(
    name="Blooming Stinger",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Scorpion"},
    text="Deathtouch\nWhen this creature enters, another target creature you control gains deathtouch until end of turn.",
    setup_interceptors=blooming_stinger_setup,
)

BROODGUARD_ELITE = make_creature(
    name="Broodguard Elite",
    power=0, toughness=0,
    mana_cost="{X}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Insect", "Knight"},
    text="This creature enters with X +1/+1 counters on it.\nWhen this creature leaves the battlefield, put its counters on target creature you control.\nWarp {X}{G} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{X}{G}", inner_setup=broodguard_elite_setup),
)

CLOSE_ENCOUNTER = make_instant(
    name="Close Encounter",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="As an additional cost to cast this spell, choose a creature you control or a warped creature card you own in exile.\nClose Encounter deals damage equal to the power of the chosen creature or card to target creature.",
)

DIPLOMATIC_RELATIONS = make_instant(
    name="Diplomatic Relations",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +1/+0 and gains vigilance until end of turn. It deals damage equal to its power to target creature an opponent controls.",
)

DRIX_FATEMAKER = make_creature(
    name="Drix Fatemaker",
    power=3, toughness=2,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Drix", "Wizard"},
    text="When this creature enters, put a +1/+1 counter on target creature.\nEach creature you control with a +1/+1 counter on it has trample.\nWarp {1}{G} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{1}{G}", inner_setup=drix_fatemaker_setup),
)

EDGE_ROVER = make_artifact_creature(
    name="Edge Rover",
    power=2, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Robot", "Scout"},
    text="Reach\nWhen this creature dies, each player creates a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
    setup_interceptors=edge_rover_setup,
)

EUMIDIAN_TERRABOTANIST = make_creature(
    name="Eumidian Terrabotanist",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Insect"},
    text="Landfall — Whenever a land you control enters, you gain 1 life.",
    setup_interceptors=eumidian_terrabotanist_setup,
)

EUSOCIAL_ENGINEERING = make_enchantment(
    name="Eusocial Engineering",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Landfall — Whenever a land you control enters, create a 2/2 colorless Robot artifact creature token.\nWarp {1}{G} (You may cast this card from your hand for its warp cost. Exile this enchantment at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{1}{G}", inner_setup=eusocial_engineering_setup),
)

FAMISHED_WORLDSIRE = make_creature(
    name="Famished Worldsire",
    power=0, toughness=0,
    mana_cost="{5}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Leviathan"},
    text="Ward {3}\nDevour land 3 (As this creature enters, you may sacrifice any number of lands. It enters with three times that many +1/+1 counters on it.)\nWhen this creature enters, look at the top X cards of your library, where X is this creature's power. Put any number of land cards from among them onto the battlefield tapped, then shuffle.",
    setup_interceptors=famished_worldsire_setup,
)

FRENZIED_BALOTH = make_creature(
    name="Frenzied Baloth",
    power=3, toughness=2,
    mana_cost="{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="This spell can't be countered.\nTrample, haste\nCreature spells you control can't be countered.\nCombat damage can't be prevented.",
    setup_interceptors=frenzied_baloth_setup,
)

FUNGAL_COLOSSUS = make_creature(
    name="Fungal Colossus",
    power=5, toughness=5,
    mana_cost="{6}{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Fungus"},
    text="This spell costs {X} less to cast, where X is the number of differently named lands you control.",
    setup_interceptors=fungal_colossus_setup,
)

GALACTIC_WAYFARER = make_creature(
    name="Galactic Wayfarer",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout"},
    text="When this creature enters, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
    setup_interceptors=galactic_wayfarer_setup,
)

GENE_POLLINATOR = make_artifact_creature(
    name="Gene Pollinator",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Insect", "Robot"},
    text="{T}, Tap an untapped permanent you control: Add one mana of any color.",
)

GERMINATING_WURM = make_creature(
    name="Germinating Wurm",
    power=5, toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Wurm"},
    text="When this creature enters, you gain 2 life.\nWarp {1}{G} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{1}{G}", inner_setup=germinating_wurm_setup),
)

GLACIER_GODMAW = make_creature(
    name="Glacier Godmaw",
    power=6, toughness=6,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Leviathan"},
    text="Trample\nWhen this creature enters, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")\nLandfall — Whenever a land you control enters, creatures you control get +1/+1 and gain vigilance and haste until end of turn.",
    setup_interceptors=glacier_godmaw_setup,
)

HARMONIOUS_GROVESTRIDER = make_creature(
    name="Harmonious Grovestrider",
    power=0, toughness=0,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Ward {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nHarmonious Grovestrider's power and toughness are each equal to the number of lands you control.",
    setup_interceptors=harmonious_grovestrider_setup,
)

HEMOSYMBIC_MITE = make_creature(
    name="Hemosymbic Mite",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Mite"},
    text="Whenever this creature becomes tapped, another target creature you control gets +X/+X until end of turn, where X is this creature's power.",
    setup_interceptors=hemosymbic_mite_setup,
)

ICECAVE_CRASHER = make_creature(
    name="Icecave Crasher",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample\nLandfall — Whenever a land you control enters, this creature gets +1/+0 until end of turn.",
    setup_interceptors=icecave_crasher_setup,
)

ICETILL_EXPLORER = make_creature(
    name="Icetill Explorer",
    power=2, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Insect", "Scout"},
    text="You may play an additional land on each of your turns.\nYou may play lands from your graveyard.\nLandfall — Whenever a land you control enters, mill a card.",
    setup_interceptors=icetill_explorer_setup,
)

INTREPID_TENDERFOOT = make_creature(
    name="Intrepid Tenderfoot",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Citizen", "Insect"},
    text="{3}: Put a +1/+1 counter on this creature. Activate only as a sorcery.",
)

LARVAL_SCOUTLANDER = make_artifact(
    name="Larval Scoutlander",
    mana_cost="{2}{G}",
    text="When this Spacecraft enters, you may sacrifice a land or Lander. If you do, search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 7+.)\n7+ | Flying",
    subtypes={"Spacecraft"},
    setup_interceptors=larval_scoutlander_setup,
)

LASHWHIP_PREDATOR = make_creature(
    name="Lashwhip Predator",
    power=5, toughness=7,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Plant"},
    text="This spell costs {2} less to cast if your opponents control three or more creatures.\nReach",
    setup_interceptors=lashwhip_predator_setup,
)

LOADING_ZONE = make_enchantment(
    name="Loading Zone",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="If one or more counters would be put on a creature, Spacecraft, or Planet you control, twice that many of each of those kinds of counters are put on it instead.\nWarp {G} (You may cast this card from your hand for its warp cost. Exile this enchantment at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{G}", inner_setup=loading_zone_setup),
)

MELTSTRIDER_EULOGIST = make_creature(
    name="Meltstrider Eulogist",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Insect", "Soldier"},
    text="Whenever a creature you control with a +1/+1 counter on it dies, draw a card.",
    setup_interceptors=meltstrider_eulogist_setup,
)

MELTSTRIDERS_GEAR = make_artifact(
    name="Meltstrider's Gear",
    mana_cost="{G}",
    text="When this Equipment enters, attach it to target creature you control.\nEquipped creature gets +2/+1 and has reach.\nEquip {5} ({5}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=meltstriders_gear_setup,
)

MELTSTRIDERS_RESOLVE = make_enchantment(
    name="Meltstrider's Resolve",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Enchant creature you control\nWhen this Aura enters, enchanted creature fights up to one target creature an opponent controls. (Each deals damage equal to its power to the other.)\nEnchanted creature gets +0/+2 and can't be blocked by more than one creature.",
    subtypes={"Aura"},
    setup_interceptors=meltstriders_resolve_setup,
)

MIGHTFORM_HARMONIZER = make_creature(
    name="Mightform Harmonizer",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Insect"},
    text="Landfall — Whenever a land you control enters, double the power of target creature you control until end of turn.\nWarp {2}{G} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{2}{G}", inner_setup=mightform_harmonizer_setup),
)

OUROBOROID = make_creature(
    name="Ouroboroid",
    power=1, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Wurm"},
    text="At the beginning of combat on your turn, put X +1/+1 counters on each creature you control, where X is this creature's power.",
    setup_interceptors=ouroboroid_setup,
)

PULL_THROUGH_THE_WEFT = make_sorcery(
    name="Pull Through the Weft",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Return up to two target nonland permanent cards from your graveyard to your hand, then return up to two target land cards from your graveyard to the battlefield tapped.",
)

SAMIS_CURIOSITY = make_sorcery(
    name="Sami's Curiosity",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="You gain 2 life. Create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

SEEDSHIP_AGRARIAN = make_creature(
    name="Seedship Agrarian",
    power=3, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Insect", "Scientist"},
    text="Whenever this creature becomes tapped, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")\nLandfall — Whenever a land you control enters, put a +1/+1 counter on this creature.",
    setup_interceptors=seedship_agrarian_setup,
)

SEEDSHIP_IMPACT = make_instant(
    name="Seedship Impact",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Destroy target artifact or enchantment. If its mana value was 2 or less, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
)

SHATTERED_WINGS = make_sorcery(
    name="Shattered Wings",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Destroy target artifact, enchantment, or creature with flying. Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

SKYSTINGER = make_creature(
    name="Skystinger",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Insect", "Warrior"},
    text="Reach\nWhenever this creature blocks a creature with flying, this creature gets +5/+0 until end of turn.",
    setup_interceptors=skystinger_setup,
)

SLEDGECLASS_SEEDSHIP = make_artifact(
    name="Sledge-Class Seedship",
    mana_cost="{2}{G}",
    text="Station (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 7+.)\n7+ | Flying\nWhenever this Spacecraft attacks, you may put a creature card from your hand onto the battlefield.",
    subtypes={"Spacecraft"},
    setup_interceptors=sledgeclass_seedship_setup,
)

TAPESTRY_WARDEN = make_artifact_creature(
    name="Tapestry Warden",
    power=3, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Robot", "Soldier"},
    text="Vigilance\nEach creature you control with toughness greater than its power assigns combat damage equal to its toughness rather than its power.\nEach creature you control with toughness greater than its power stations permanents using its toughness rather than its power.",
    setup_interceptors=tapestry_warden_setup,
)

TERRASYMBIOSIS = make_enchantment(
    name="Terrasymbiosis",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Whenever you put one or more +1/+1 counters on a creature you control, you may draw that many cards. Do this only once each turn.",
    setup_interceptors=terrasymbiosis_setup,
)

THAWBRINGER = make_creature(
    name="Thawbringer",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Insect", "Scout"},
    text="When this creature enters or dies, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    setup_interceptors=thawbringer_setup,
)

ALPHARAEL_DREAMING_ACOLYTE = make_creature(
    name="Alpharael, Dreaming Acolyte",
    power=2, toughness=3,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Cleric", "Human"},
    supertypes={"Legendary"},
    text="When Alpharael enters, draw two cards. Then discard two cards unless you discard an artifact card.\nDuring your turn, Alpharael has deathtouch.",
    setup_interceptors=alpharael_dreaming_acolyte_setup,
)

BIOMECHAN_ENGINEER = make_creature(
    name="Biomechan Engineer",
    power=2, toughness=2,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Artificer", "Insect"},
    text="When this creature enters, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")\n{8}: Draw two cards and create a 2/2 colorless Robot artifact creature token.",
    setup_interceptors=biomechan_engineer_setup,
)

BIOTECH_SPECIALIST = make_creature(
    name="Biotech Specialist",
    power=1, toughness=3,
    mana_cost="{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Insect", "Scientist"},
    text="When this creature enters, create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")\nWhenever you sacrifice an artifact, this creature deals 2 damage to target opponent.",
    setup_interceptors=biotech_specialist_setup,
)

COSMOGOYF = make_creature(
    name="Cosmogoyf",
    power=0, toughness=0,
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Elemental", "Lhurgoyf"},
    text="Cosmogoyf's power is equal to the number of cards you own in exile and its toughness is equal to that number plus 1.",
    setup_interceptors=cosmogoyf_setup,
)

DYADRINE_SYNTHESIS_AMALGAM = make_artifact_creature(
    name="Dyadrine, Synthesis Amalgam",
    power=0, toughness=1,
    mana_cost="{X}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Construct"},
    supertypes={"Legendary"},
    text="Trample\nDyadrine enters with a number of +1/+1 counters on it equal to the amount of mana spent to cast it.\nWhenever you attack, you may remove a +1/+1 counter from each of two creatures you control. If you do, draw a card and create a 2/2 colorless Robot artifact creature token.",
    setup_interceptors=dyadrine_synthesis_amalgam_setup,
)

GENEMORPH_IMAGO = make_creature(
    name="Genemorph Imago",
    power=1, toughness=3,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Druid", "Insect"},
    text="Flying\nLandfall — Whenever a land you control enters, target creature has base power and toughness 3/3 until end of turn. If you control six or more lands, that creature has base power and toughness 6/6 until end of turn instead.",
    setup_interceptors=genemorph_imago_setup,
)

HALIYA_ASCENDANT_CADET = make_creature(
    name="Haliya, Ascendant Cadet",
    power=3, toughness=3,
    mana_cost="{2}{G}{W}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Whenever Haliya enters or attacks, put a +1/+1 counter on target creature you control.\nWhenever one or more creatures you control with +1/+1 counters on them deal combat damage to a player, draw a card.",
    setup_interceptors=haliya_ascendant_cadet_setup,
)

INFINITE_GUIDELINE_STATION = make_artifact(
    name="Infinite Guideline Station",
    mana_cost="{W}{U}{B}{R}{G}",
    text="When Infinite Guideline Station enters, create a tapped 2/2 colorless Robot artifact creature token for each multicolored permanent you control.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 12+.)\n12+ | Flying\nWhenever Infinite Guideline Station attacks, draw a card for each multicolored permanent you control.",
    subtypes={"Spacecraft"},
    supertypes={"Legendary"},
    setup_interceptors=infinite_guideline_station_setup,
)

INTERCEPTOR_MECHAN = make_artifact_creature(
    name="Interceptor Mechan",
    power=2, toughness=2,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Robot"},
    text="Flying\nWhen this creature enters, return target artifact or creature card from your graveyard to your hand.\nVoid — At the beginning of your end step, if a nonland permanent left the battlefield this turn or a spell was warped this turn, put a +1/+1 counter on this creature.",
    setup_interceptors=interceptor_mechan_setup,
)

MMMENON_UTHROS_EXILE = make_creature(
    name="Mm'menon, Uthros Exile",
    power=1, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Advisor", "Jellyfish"},
    supertypes={"Legendary"},
    text="Flying\nWhenever an artifact you control enters, put a +1/+1 counter on target creature.",
    setup_interceptors=mmmenon_uthros_exile_setup,
)

MUTINOUS_MASSACRE = make_sorcery(
    name="Mutinous Massacre",
    mana_cost="{3}{B}{B}{R}{R}",
    colors={Color.BLACK, Color.RED},
    text="Choose odd or even. Destroy each creature with mana value of the chosen quality. Then gain control of all creatures until end of turn. Untap them. They gain haste until end of turn. (Zero is even.)",
)

PINNACLE_EMISSARY = make_artifact_creature(
    name="Pinnacle Emissary",
    power=3, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Robot"},
    text="Whenever you cast an artifact spell, create a 1/1 colorless Drone artifact creature token with flying and \"This token can block only creatures with flying.\"\nWarp {U/R} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{U/R}", inner_setup=pinnacle_emissary_setup),
)

RAGOST_DEFT_GASTRONAUT = make_creature(
    name="Ragost, Deft Gastronaut",
    power=2, toughness=2,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Citizen", "Lobster"},
    supertypes={"Legendary"},
    text="Artifacts you control are Foods in addition to their other types and have \"{2}, {T}, Sacrifice this artifact: You gain 3 life.\"\n{1}, {T}, Sacrifice a Food: Ragost deals 3 damage to each opponent.\nAt the beginning of each end step, if you gained life this turn, untap Ragost.",
    setup_interceptors=ragost_deft_gastronaut_setup,
)

SAMI_SHIPS_ENGINEER = make_creature(
    name="Sami, Ship's Engineer",
    power=2, toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Artificer", "Human"},
    supertypes={"Legendary"},
    text="At the beginning of your end step, if you control two or more tapped creatures, create a tapped 2/2 colorless Robot artifact creature token.",
    setup_interceptors=sami_ships_engineer_setup,
)

SAMI_WILDCAT_CAPTAIN = make_creature(
    name="Sami, Wildcat Captain",
    power=4, toughness=4,
    mana_cost="{4}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Artificer", "Human", "Rogue"},
    supertypes={"Legendary"},
    text="Double strike, vigilance\nSpells you cast have affinity for artifacts. (They cost {1} less to cast for each artifact you control.)",
    setup_interceptors=sami_wildcat_captain_setup,
)

SEEDSHIP_BROODTENDER = make_creature(
    name="Seedship Broodtender",
    power=2, toughness=3,
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Citizen", "Insect"},
    text="When this creature enters, mill three cards. (Put the top three cards of your library into your graveyard.)\n{3}{B}{G}, Sacrifice this creature: Return target creature or Spacecraft card from your graveyard to the battlefield. Activate only as a sorcery.",
    setup_interceptors=seedship_broodtender_setup,
)

SINGULARITY_RUPTURE = make_sorcery(
    name="Singularity Rupture",
    mana_cost="{3}{U}{B}{B}",
    colors={Color.BLACK, Color.BLUE},
    text="Destroy all creatures, then any number of target players each mill half their library, rounded down.",
)

SPACETIME_ANOMALY = make_sorcery(
    name="Space-Time Anomaly",
    mana_cost="{2}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    text="Target player mills cards equal to your life total.",
)

STATION_MONITOR = make_creature(
    name="Station Monitor",
    power=2, toughness=2,
    mana_cost="{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Artificer", "Lizard"},
    text="Whenever you cast your second spell each turn, create a 1/1 colorless Drone artifact creature token with flying and \"This token can block only creatures with flying.\"",
    setup_interceptors=station_monitor_setup,
)

SYR_VONDAM_SUNSTAR_EXEMPLAR = make_creature(
    name="Syr Vondam, Sunstar Exemplar",
    power=2, toughness=2,
    mana_cost="{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="Vigilance, menace\nWhenever another creature you control dies or is put into exile, put a +1/+1 counter on Syr Vondam and you gain 1 life.\nWhen Syr Vondam dies or is put into exile while its power is 4 or greater, destroy up to one target nonland permanent.",
    setup_interceptors=syr_vondam_sunstar_exemplar_setup,
)

SYR_VONDAM_THE_LUCENT = make_creature(
    name="Syr Vondam, the Lucent",
    power=4, toughness=4,
    mana_cost="{2}{W}{B}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="Deathtouch, lifelink\nWhenever Syr Vondam enters or attacks, other creatures you control get +1/+0 and gain deathtouch until end of turn.",
    setup_interceptors=syr_vondam_the_lucent_setup,
)

TANNUK_MEMORIAL_ENSIGN = make_creature(
    name="Tannuk, Memorial Ensign",
    power=2, toughness=4,
    mana_cost="{1}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Kavu", "Pilot"},
    supertypes={"Legendary"},
    text="Landfall — Whenever a land you control enters, Tannuk deals 1 damage to each opponent. If this is the second time this ability has resolved this turn, draw a card.",
    setup_interceptors=tannuk_memorial_ensign_setup,
)

ALLFATES_SCROLL = make_artifact(
    name="All-Fates Scroll",
    mana_cost="{3}",
    text="{T}: Add one mana of any color.\n{7}, {T}, Sacrifice this artifact: Draw X cards, where X is the number of differently named lands you control.",
)

BYGONE_COLOSSUS = make_artifact_creature(
    name="Bygone Colossus",
    power=9, toughness=9,
    mana_cost="{9}",
    colors=set(),
    subtypes={"Giant", "Robot"},
    text="Warp {3} (You may cast this card from your hand for its warp cost. Exile this creature at the beginning of the next end step, then you may cast it from exile on a later turn.)",
    setup_interceptors=make_warp_setup("{3}", inner_setup=bygone_colossus_setup),
)

CHROME_COMPANION = make_artifact_creature(
    name="Chrome Companion",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Dog"},
    text="Whenever this creature becomes tapped, you gain 1 life.\n{2}, {T}: Put target card from a graveyard on the bottom of its owner's library.",
    setup_interceptors=chrome_companion_setup,
)

DAUNTLESS_SCRAPBOT = make_artifact_creature(
    name="Dauntless Scrapbot",
    power=3, toughness=1,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Robot"},
    text="When this creature enters, exile each opponent's graveyard. Create a Lander token. (It's an artifact with \"{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\")",
    setup_interceptors=dauntless_scrapbot_setup,
)

DAWNSIRE_SUNSTAR_DREADNOUGHT = make_artifact(
    name="Dawnsire, Sunstar Dreadnought",
    mana_cost="{5}",
    text="Station (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 20+.)\n10+ | Whenever you attack, Dawnsire deals 100 damage to up to one target creature or planeswalker.\n20+ | Flying",
    subtypes={"Spacecraft"},
    supertypes={"Legendary"},
    setup_interceptors=dawnsire_sunstar_dreadnought_setup,
)

THE_DOMINION_BRACELET = make_artifact(
    name="The Dominion Bracelet",
    mana_cost="{2}",
    text="Equipped creature gets +1/+1 and has \"{15}, Exile The Dominion Bracelet: You control target opponent during their next turn. This ability costs {X} less to activate, where X is this creature's power. Activate only as a sorcery.\" (You see all cards that player could see and make all decisions for them.)\nEquip {1}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    setup_interceptors=the_dominion_bracelet_setup,
)

THE_ENDSTONE = make_artifact(
    name="The Endstone",
    mana_cost="{7}",
    text="Whenever you play a land or cast a spell, draw a card.\nAt the beginning of your end step, your life total becomes half your starting life total, rounded up.",
    supertypes={"Legendary"},
    setup_interceptors=the_endstone_setup,
)

THE_ETERNITY_ELEVATOR = make_artifact(
    name="The Eternity Elevator",
    mana_cost="{5}",
    text="{T}: Add {C}{C}{C}.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery.)\n20+ | {T}: Add X mana of any one color, where X is the number of charge counters on The Eternity Elevator.",
    subtypes={"Spacecraft"},
    supertypes={"Legendary"},
    setup_interceptors=the_eternity_elevator_setup,
)

EXTINGUISHER_BATTLESHIP = make_artifact(
    name="Extinguisher Battleship",
    mana_cost="{8}",
    text="When this Spacecraft enters, destroy target noncreature permanent. Then this Spacecraft deals 4 damage to each creature.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 5+.)\n5+ | Flying, trample",
    subtypes={"Spacecraft"},
    setup_interceptors=extinguisher_battleship_setup,
)

NUTRIENT_BLOCK = make_artifact(
    name="Nutrient Block",
    mana_cost="{1}",
    text="Indestructible (Effects that say \"destroy\" don't destroy this artifact.)\n{2}, {T}, Sacrifice this artifact: You gain 3 life.\nWhen this artifact is put into a graveyard from the battlefield, draw a card.",
    subtypes={"Food"},
    setup_interceptors=nutrient_block_setup,
)

PINNACLE_KILLSHIP = make_artifact(
    name="Pinnacle Kill-Ship",
    mana_cost="{7}",
    text="When this Spacecraft enters, it deals 10 damage to up to one target creature.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 7+.)\n7+ | Flying",
    subtypes={"Spacecraft"},
    setup_interceptors=pinnacle_killship_setup,
)

SURVEY_MECHAN = make_artifact_creature(
    name="Survey Mechan",
    power=1, toughness=3,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Robot"},
    text="Flying\nHexproof (This creature can't be the target of spells or abilities your opponents control.)\n{10}, Sacrifice this creature: It deals 3 damage to any target. Target player draws three cards and gains 3 life. This ability costs {X} less to activate, where X is the number of differently named lands you control.",
    setup_interceptors=survey_mechan_setup,
)

THAUMATON_TORPEDO = make_artifact(
    name="Thaumaton Torpedo",
    mana_cost="{1}",
    text="{6}, {T}, Sacrifice this artifact: Destroy target nonland permanent. This ability costs {3} less to activate if you attacked with a Spacecraft this turn.",
    setup_interceptors=thaumaton_torpedo_setup,
)

THRUMMING_HIVEPOOL = make_artifact(
    name="Thrumming Hivepool",
    mana_cost="{6}",
    text="Affinity for Slivers (This spell costs {1} less to cast for each Sliver you control.)\nSlivers you control have double strike and haste.\nAt the beginning of your upkeep, create two 1/1 colorless Sliver creature tokens.",
    setup_interceptors=thrumming_hivepool_setup,
)

VIRULENT_SILENCER = make_artifact_creature(
    name="Virulent Silencer",
    power=2, toughness=3,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Assassin", "Robot"},
    text="Whenever a nontoken artifact creature you control deals combat damage to a player, that player gets two poison counters. (A player with ten or more poison counters loses the game.)",
    setup_interceptors=virulent_silencer_setup,
)

WURMWALL_SWEEPER = make_artifact(
    name="Wurmwall Sweeper",
    mana_cost="{2}",
    text="When this Spacecraft enters, surveil 2.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 4+.)\n4+ | Flying",
    subtypes={"Spacecraft"},
    setup_interceptors=wurmwall_sweeper_setup,
)

ADAGIA_WINDSWEPT_BASTION = make_land(
    name="Adagia, Windswept Bastion",
    text="This land enters tapped.\n{T}: Add {W}.\nStation (Tap another creature you control: Put charge counters equal to its power on this Planet. Station only as a sorcery.)\n12+ | {3}{W}, {T}: Create a token that's a copy of target artifact or enchantment you control, except it's legendary. Activate only as a sorcery.",
    subtypes={"Planet"},
    setup_interceptors=adagia_windswept_bastion_setup,
)

BREEDING_POOL = make_land(
    name="Breeding Pool",
    text="({T}: Add {G} or {U}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
    subtypes={"Forest", "Island"},
    setup_interceptors=breeding_pool_setup,
)

COMMAND_BRIDGE = make_land(
    name="Command Bridge",
    text="This land enters tapped.\nWhen this land enters, sacrifice it unless you tap an untapped permanent you control.\n{T}: Add one mana of any color.",
    setup_interceptors=command_bridge_setup,
)

EVENDO_WAKING_HAVEN = make_land(
    name="Evendo, Waking Haven",
    text="This land enters tapped.\n{T}: Add {G}.\nStation (Tap another creature you control: Put charge counters equal to its power on this Planet. Station only as a sorcery.)\n12+ | {G}, {T}: Add {G} for each creature you control.",
    subtypes={"Planet"},
    setup_interceptors=evendo_waking_haven_setup,
)

GODLESS_SHRINE = make_land(
    name="Godless Shrine",
    text="({T}: Add {W} or {B}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
    subtypes={"Plains", "Swamp"},
    setup_interceptors=godless_shrine_setup,
)

KAVARON_MEMORIAL_WORLD = make_land(
    name="Kavaron, Memorial World",
    text="This land enters tapped.\n{T}: Add {R}.\nStation (Tap another creature you control: Put charge counters equal to its power on this Planet. Station only as a sorcery.)\n12+ | {1}{R}, {T}, Sacrifice a land: Create a 2/2 colorless Robot artifact creature token, then creatures you control get +1/+0 and gain haste until end of turn.",
    subtypes={"Planet"},
    setup_interceptors=kavaron_memorial_world_setup,
)

SACRED_FOUNDRY = make_land(
    name="Sacred Foundry",
    text="({T}: Add {R} or {W}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
    subtypes={"Mountain", "Plains"},
    setup_interceptors=sacred_foundry_setup,
)

SECLUDED_STARFORGE = make_land(
    name="Secluded Starforge",
    text="{T}: Add {C}.\n{2}, {T}, Tap X untapped artifacts you control: Target creature gets +X/+0 until end of turn. Activate only as a sorcery.\n{5}, {T}: Create a 2/2 colorless Robot artifact creature token.",
    setup_interceptors=secluded_starforge_setup,
)

STOMPING_GROUND = make_land(
    name="Stomping Ground",
    text="({T}: Add {R} or {G}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
    subtypes={"Forest", "Mountain"},
    setup_interceptors=stomping_ground_setup,
)

SUSUR_SECUNDI_VOID_ALTAR = make_land(
    name="Susur Secundi, Void Altar",
    text="This land enters tapped.\n{T}: Add {B}.\nStation (Tap another creature you control: Put charge counters equal to its power on this Planet. Station only as a sorcery.)\n12+ | {1}{B}, {T}, Pay 2 life, Sacrifice a creature: Draw cards equal to the sacrificed creature's power. Activate only as a sorcery.",
    subtypes={"Planet"},
    setup_interceptors=susur_secundi_void_altar_setup,
)

UTHROS_TITANIC_GODCORE = make_land(
    name="Uthros, Titanic Godcore",
    text="This land enters tapped.\n{T}: Add {U}.\nStation (Tap another creature you control: Put charge counters equal to its power on this Planet. Station only as a sorcery.)\n12+ | {U}, {T}: Add {U} for each artifact you control.",
    subtypes={"Planet"},
    setup_interceptors=uthros_titanic_godcore_setup,
)

WATERY_GRAVE = make_land(
    name="Watery Grave",
    text="({T}: Add {U} or {B}.)\nAs this land enters, you may pay 2 life. If you don't, it enters tapped.",
    subtypes={"Island", "Swamp"},
    setup_interceptors=watery_grave_setup,
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

# =============================================================================
# CARD REGISTRY
# =============================================================================

EDGE_OF_ETERNITIES_CARDS = {
    "Anticausal Vestige": ANTICAUSAL_VESTIGE,
    "Tezzeret, Cruel Captain": TEZZERET_CRUEL_CAPTAIN,
    "All-Fates Stalker": ALLFATES_STALKER,
    "Astelli Reclaimer": ASTELLI_RECLAIMER,
    "Auxiliary Boosters": AUXILIARY_BOOSTERS,
    "Banishing Light": BANISHING_LIGHT,
    "Beyond the Quiet": BEYOND_THE_QUIET,
    "Brightspear Zealot": BRIGHTSPEAR_ZEALOT,
    "Cosmogrand Zenith": COSMOGRAND_ZENITH,
    "Dawnstrike Vanguard": DAWNSTRIKE_VANGUARD,
    "Dockworker Drone": DOCKWORKER_DRONE,
    "Dual-Sun Adepts": DUALSUN_ADEPTS,
    "Dual-Sun Technique": DUALSUN_TECHNIQUE,
    "Emergency Eject": EMERGENCY_EJECT,
    "Exalted Sunborn": EXALTED_SUNBORN,
    "Exosuit Savior": EXOSUIT_SAVIOR,
    "Flight-Deck Coordinator": FLIGHTDECK_COORDINATOR,
    "Focus Fire": FOCUS_FIRE,
    "Haliya, Guided by Light": HALIYA_GUIDED_BY_LIGHT,
    "Hardlight Containment": HARDLIGHT_CONTAINMENT,
    "Honor": HONOR,
    "Honored Knight-Captain": HONORED_KNIGHTCAPTAIN,
    "Knight Luminary": KNIGHT_LUMINARY,
    "Lightstall Inquisitor": LIGHTSTALL_INQUISITOR,
    "Lumen-Class Frigate": LUMENCLASS_FRIGATE,
    "Luxknight Breacher": LUXKNIGHT_BREACHER,
    "Pinnacle Starcage": PINNACLE_STARCAGE,
    "Pulsar Squadron Ace": PULSAR_SQUADRON_ACE,
    "Radiant Strike": RADIANT_STRIKE,
    "Rayblade Trooper": RAYBLADE_TROOPER,
    "Reroute Systems": REROUTE_SYSTEMS,
    "Rescue Skiff": RESCUE_SKIFF,
    "Scout for Survivors": SCOUT_FOR_SURVIVORS,
    "Seam Rip": SEAM_RIP,
    "The Seriema": THE_SERIEMA,
    "Squire's Lightblade": SQUIRES_LIGHTBLADE,
    "Starfield Shepherd": STARFIELD_SHEPHERD,
    "Starfighter Pilot": STARFIGHTER_PILOT,
    "Starport Security": STARPORT_SECURITY,
    "Sunstar Chaplain": SUNSTAR_CHAPLAIN,
    "Sunstar Expansionist": SUNSTAR_EXPANSIONIST,
    "Sunstar Lightsmith": SUNSTAR_LIGHTSMITH,
    "Wedgelight Rammer": WEDGELIGHT_RAMMER,
    "Weftblade Enhancer": WEFTBLADE_ENHANCER,
    "Zealous Display": ZEALOUS_DISPLAY,
    "Annul": ANNUL,
    "Atomic Microsizer": ATOMIC_MICROSIZER,
    "Cerebral Download": CEREBRAL_DOWNLOAD,
    "Cloudsculpt Technician": CLOUDSCULPT_TECHNICIAN,
    "Codecracker Hound": CODECRACKER_HOUND,
    "Consult the Star Charts": CONSULT_THE_STAR_CHARTS,
    "Cryogen Relic": CRYOGEN_RELIC,
    "Cryoshatter": CRYOSHATTER,
    "Desculpting Blast": DESCULPTING_BLAST,
    "Divert Disaster": DIVERT_DISASTER,
    "Emissary Escort": EMISSARY_ESCORT,
    "Gigastorm Titan": GIGASTORM_TITAN,
    "Illvoi Galeblade": ILLVOI_GALEBLADE,
    "Illvoi Infiltrator": ILLVOI_INFILTRATOR,
    "Illvoi Light Jammer": ILLVOI_LIGHT_JAMMER,
    "Illvoi Operative": ILLVOI_OPERATIVE,
    "Lost in Space": LOST_IN_SPACE,
    "Mechan Assembler": MECHAN_ASSEMBLER,
    "Mechan Navigator": MECHAN_NAVIGATOR,
    "Mechan Shieldmate": MECHAN_SHIELDMATE,
    "Mechanozoa": MECHANOZOA,
    "Mental Modulation": MENTAL_MODULATION,
    "Mm'menon, the Right Hand": MMMENON_THE_RIGHT_HAND,
    "Moonlit Meditation": MOONLIT_MEDITATION,
    "Mouth of the Storm": MOUTH_OF_THE_STORM,
    "Nanoform Sentinel": NANOFORM_SENTINEL,
    "Quantum Riddler": QUANTUM_RIDDLER,
    "Scour for Scrap": SCOUR_FOR_SCRAP,
    "Selfcraft Mechan": SELFCRAFT_MECHAN,
    "Sinister Cryologist": SINISTER_CRYOLOGIST,
    "Specimen Freighter": SPECIMEN_FREIGHTER,
    "Starbreach Whale": STARBREACH_WHALE,
    "Starfield Vocalist": STARFIELD_VOCALIST,
    "Starwinder": STARWINDER,
    "Steelswarm Operator": STEELSWARM_OPERATOR,
    "Synthesizer Labship": SYNTHESIZER_LABSHIP,
    "Tractor Beam": TRACTOR_BEAM,
    "Unravel": UNRAVEL,
    "Uthros Psionicist": UTHROS_PSIONICIST,
    "Uthros Scanship": UTHROS_SCANSHIP,
    "Weftwalking": WEFTWALKING,
    "Alpharael, Stonechosen": ALPHARAEL_STONECHOSEN,
    "Archenemy's Charm": ARCHENEMYS_CHARM,
    "Beamsaw Prospector": BEAMSAW_PROSPECTOR,
    "Blade of the Swarm": BLADE_OF_THE_SWARM,
    "Chorale of the Void": CHORALE_OF_THE_VOID,
    "Comet Crawler": COMET_CRAWLER,
    "Dark Endurance": DARK_ENDURANCE,
    "Decode Transmissions": DECODE_TRANSMISSIONS,
    "Depressurize": DEPRESSURIZE,
    "Dubious Delicacy": DUBIOUS_DELICACY,
    "Elegy Acolyte": ELEGY_ACOLYTE,
    "Embrace Oblivion": EMBRACE_OBLIVION,
    "Entropic Battlecruiser": ENTROPIC_BATTLECRUISER,
    "Faller's Faithful": FALLERS_FAITHFUL,
    "Fell Gravship": FELL_GRAVSHIP,
    "Gravblade Heavy": GRAVBLADE_HEAVY,
    "Gravkill": GRAVKILL,
    "Gravpack Monoist": GRAVPACK_MONOIST,
    "Hullcarver": HULLCARVER,
    "Hylderblade": HYLDERBLADE,
    "Hymn of the Faller": HYMN_OF_THE_FALLER,
    "Insatiable Skittermaw": INSATIABLE_SKITTERMAW,
    "Lightless Evangel": LIGHTLESS_EVANGEL,
    "Monoist Circuit-Feeder": MONOIST_CIRCUITFEEDER,
    "Monoist Sentry": MONOIST_SENTRY,
    "Perigee Beckoner": PERIGEE_BECKONER,
    "Requiem Monolith": REQUIEM_MONOLITH,
    "Scrounge for Eternity": SCROUNGE_FOR_ETERNITY,
    "Sothera, the Supervoid": SOTHERA_THE_SUPERVOID,
    "Sunset Saboteur": SUNSET_SABOTEUR,
    "Susurian Dirgecraft": SUSURIAN_DIRGECRAFT,
    "Susurian Voidborn": SUSURIAN_VOIDBORN,
    "Swarm Culler": SWARM_CULLER,
    "Temporal Intervention": TEMPORAL_INTERVENTION,
    "Timeline Culler": TIMELINE_CULLER,
    "Tragic Trajectory": TRAGIC_TRAJECTORY,
    "Umbral Collar Zealot": UMBRAL_COLLAR_ZEALOT,
    "Virus Beetle": VIRUS_BEETLE,
    "Voidforged Titan": VOIDFORGED_TITAN,
    "Vote Out": VOTE_OUT,
    "Xu-Ifit, Osteoharmonist": XUIFIT_OSTEOHARMONIST,
    "Zero Point Ballad": ZERO_POINT_BALLAD,
    "Bombard": BOMBARD,
    "Cut Propulsion": CUT_PROPULSION,
    "Debris Field Crusher": DEBRIS_FIELD_CRUSHER,
    "Devastating Onslaught": DEVASTATING_ONSLAUGHT,
    "Drill Too Deep": DRILL_TOO_DEEP,
    "Frontline War-Rager": FRONTLINE_WARRAGER,
    "Full Bore": FULL_BORE,
    "Galvanizing Sawship": GALVANIZING_SAWSHIP,
    "Invasive Maneuvers": INVASIVE_MANEUVERS,
    "Kav Landseeker": KAV_LANDSEEKER,
    "Kavaron Harrier": KAVARON_HARRIER,
    "Kavaron Skywarden": KAVARON_SKYWARDEN,
    "Kavaron Turbodrone": KAVARON_TURBODRONE,
    "Lithobraking": LITHOBRAKING,
    "Melded Moxite": MELDED_MOXITE,
    "Memorial Team Leader": MEMORIAL_TEAM_LEADER,
    "Memorial Vault": MEMORIAL_VAULT,
    "Molecular Modifier": MOLECULAR_MODIFIER,
    "Nebula Dragon": NEBULA_DRAGON,
    "Nova Hellkite": NOVA_HELLKITE,
    "Orbital Plunge": ORBITAL_PLUNGE,
    "Oreplate Pangolin": OREPLATE_PANGOLIN,
    "Pain for All": PAIN_FOR_ALL,
    "Plasma Bolt": PLASMA_BOLT,
    "Possibility Technician": POSSIBILITY_TECHNICIAN,
    "Red Tiger Mechan": RED_TIGER_MECHAN,
    "Remnant Elemental": REMNANT_ELEMENTAL,
    "Rig for War": RIG_FOR_WAR,
    "Roving Actuator": ROVING_ACTUATOR,
    "Ruinous Rampage": RUINOUS_RAMPAGE,
    "Rust Harvester": RUST_HARVESTER,
    "Slagdrill Scrapper": SLAGDRILL_SCRAPPER,
    "Systems Override": SYSTEMS_OVERRIDE,
    "Tannuk, Steadfast Second": TANNUK_STEADFAST_SECOND,
    "Terminal Velocity": TERMINAL_VELOCITY,
    "Terrapact Intimidator": TERRAPACT_INTIMIDATOR,
    "Territorial Bruntar": TERRITORIAL_BRUNTAR,
    "Vaultguard Trooper": VAULTGUARD_TROOPER,
    "Warmaker Gunship": WARMAKER_GUNSHIP,
    "Weapons Manufacturing": WEAPONS_MANUFACTURING,
    "Weftstalker Ardent": WEFTSTALKER_ARDENT,
    "Zookeeper Mechan": ZOOKEEPER_MECHAN,
    "Atmospheric Greenhouse": ATMOSPHERIC_GREENHOUSE,
    "Bioengineered Future": BIOENGINEERED_FUTURE,
    "Biosynthic Burst": BIOSYNTHIC_BURST,
    "Blooming Stinger": BLOOMING_STINGER,
    "Broodguard Elite": BROODGUARD_ELITE,
    "Close Encounter": CLOSE_ENCOUNTER,
    "Diplomatic Relations": DIPLOMATIC_RELATIONS,
    "Drix Fatemaker": DRIX_FATEMAKER,
    "Edge Rover": EDGE_ROVER,
    "Eumidian Terrabotanist": EUMIDIAN_TERRABOTANIST,
    "Eusocial Engineering": EUSOCIAL_ENGINEERING,
    "Famished Worldsire": FAMISHED_WORLDSIRE,
    "Frenzied Baloth": FRENZIED_BALOTH,
    "Fungal Colossus": FUNGAL_COLOSSUS,
    "Galactic Wayfarer": GALACTIC_WAYFARER,
    "Gene Pollinator": GENE_POLLINATOR,
    "Germinating Wurm": GERMINATING_WURM,
    "Glacier Godmaw": GLACIER_GODMAW,
    "Harmonious Grovestrider": HARMONIOUS_GROVESTRIDER,
    "Hemosymbic Mite": HEMOSYMBIC_MITE,
    "Icecave Crasher": ICECAVE_CRASHER,
    "Icetill Explorer": ICETILL_EXPLORER,
    "Intrepid Tenderfoot": INTREPID_TENDERFOOT,
    "Larval Scoutlander": LARVAL_SCOUTLANDER,
    "Lashwhip Predator": LASHWHIP_PREDATOR,
    "Loading Zone": LOADING_ZONE,
    "Meltstrider Eulogist": MELTSTRIDER_EULOGIST,
    "Meltstrider's Gear": MELTSTRIDERS_GEAR,
    "Meltstrider's Resolve": MELTSTRIDERS_RESOLVE,
    "Mightform Harmonizer": MIGHTFORM_HARMONIZER,
    "Ouroboroid": OUROBOROID,
    "Pull Through the Weft": PULL_THROUGH_THE_WEFT,
    "Sami's Curiosity": SAMIS_CURIOSITY,
    "Seedship Agrarian": SEEDSHIP_AGRARIAN,
    "Seedship Impact": SEEDSHIP_IMPACT,
    "Shattered Wings": SHATTERED_WINGS,
    "Skystinger": SKYSTINGER,
    "Sledge-Class Seedship": SLEDGECLASS_SEEDSHIP,
    "Tapestry Warden": TAPESTRY_WARDEN,
    "Terrasymbiosis": TERRASYMBIOSIS,
    "Thawbringer": THAWBRINGER,
    "Alpharael, Dreaming Acolyte": ALPHARAEL_DREAMING_ACOLYTE,
    "Biomechan Engineer": BIOMECHAN_ENGINEER,
    "Biotech Specialist": BIOTECH_SPECIALIST,
    "Cosmogoyf": COSMOGOYF,
    "Dyadrine, Synthesis Amalgam": DYADRINE_SYNTHESIS_AMALGAM,
    "Genemorph Imago": GENEMORPH_IMAGO,
    "Haliya, Ascendant Cadet": HALIYA_ASCENDANT_CADET,
    "Infinite Guideline Station": INFINITE_GUIDELINE_STATION,
    "Interceptor Mechan": INTERCEPTOR_MECHAN,
    "Mm'menon, Uthros Exile": MMMENON_UTHROS_EXILE,
    "Mutinous Massacre": MUTINOUS_MASSACRE,
    "Pinnacle Emissary": PINNACLE_EMISSARY,
    "Ragost, Deft Gastronaut": RAGOST_DEFT_GASTRONAUT,
    "Sami, Ship's Engineer": SAMI_SHIPS_ENGINEER,
    "Sami, Wildcat Captain": SAMI_WILDCAT_CAPTAIN,
    "Seedship Broodtender": SEEDSHIP_BROODTENDER,
    "Singularity Rupture": SINGULARITY_RUPTURE,
    "Space-Time Anomaly": SPACETIME_ANOMALY,
    "Station Monitor": STATION_MONITOR,
    "Syr Vondam, Sunstar Exemplar": SYR_VONDAM_SUNSTAR_EXEMPLAR,
    "Syr Vondam, the Lucent": SYR_VONDAM_THE_LUCENT,
    "Tannuk, Memorial Ensign": TANNUK_MEMORIAL_ENSIGN,
    "All-Fates Scroll": ALLFATES_SCROLL,
    "Bygone Colossus": BYGONE_COLOSSUS,
    "Chrome Companion": CHROME_COMPANION,
    "Dauntless Scrapbot": DAUNTLESS_SCRAPBOT,
    "Dawnsire, Sunstar Dreadnought": DAWNSIRE_SUNSTAR_DREADNOUGHT,
    "The Dominion Bracelet": THE_DOMINION_BRACELET,
    "The Endstone": THE_ENDSTONE,
    "The Eternity Elevator": THE_ETERNITY_ELEVATOR,
    "Extinguisher Battleship": EXTINGUISHER_BATTLESHIP,
    "Nutrient Block": NUTRIENT_BLOCK,
    "Pinnacle Kill-Ship": PINNACLE_KILLSHIP,
    "Survey Mechan": SURVEY_MECHAN,
    "Thaumaton Torpedo": THAUMATON_TORPEDO,
    "Thrumming Hivepool": THRUMMING_HIVEPOOL,
    "Virulent Silencer": VIRULENT_SILENCER,
    "Wurmwall Sweeper": WURMWALL_SWEEPER,
    "Adagia, Windswept Bastion": ADAGIA_WINDSWEPT_BASTION,
    "Breeding Pool": BREEDING_POOL,
    "Command Bridge": COMMAND_BRIDGE,
    "Evendo, Waking Haven": EVENDO_WAKING_HAVEN,
    "Godless Shrine": GODLESS_SHRINE,
    "Kavaron, Memorial World": KAVARON_MEMORIAL_WORLD,
    "Sacred Foundry": SACRED_FOUNDRY,
    "Secluded Starforge": SECLUDED_STARFORGE,
    "Stomping Ground": STOMPING_GROUND,
    "Susur Secundi, Void Altar": SUSUR_SECUNDI_VOID_ALTAR,
    "Uthros, Titanic Godcore": UTHROS_TITANIC_GODCORE,
    "Watery Grave": WATERY_GRAVE,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
}

print(f"Loaded {len(EDGE_OF_ETERNITIES_CARDS)} Edge_of_Eternities cards")
