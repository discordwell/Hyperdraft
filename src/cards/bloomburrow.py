"""
Bloomburrow (BLB) Card Implementations

Real card data fetched from Scryfall API.
280 cards in set.
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
    make_static_pt_boost, make_keyword_grant, make_damage_trigger,
    make_life_gain_trigger, make_upkeep_trigger, make_spell_cast_trigger,
    make_end_step_trigger,
    other_creatures_you_control, other_creatures_with_subtype,
    creatures_you_control, creatures_with_subtype, create_target_choice,
    create_modal_choice,
    make_graveyard_to_exile_replacer,
)
from src.engine.blb_mechanics import (
    make_valiant_trigger,
    make_expend_trigger,
    make_forage_trigger,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# =============================================================================
# INTERCEPTOR SETUP FUNCTIONS
# =============================================================================

# Helper filter functions for Bloomburrow creature types
def other_rabbits_bats_birds_mice(source: GameObject):
    """Filter: Other Rabbits, Bats, Birds, and Mice you control."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        if target.id == source.id:
            return False
        if target.controller != source.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        subtypes = target.characteristics.subtypes
        return bool(subtypes & {"Rabbit", "Bat", "Bird", "Mouse"})
    return filter_fn


def other_mice_you_control(source: GameObject):
    """Filter: Other Mice you control."""
    return other_creatures_with_subtype(source, "Mouse")


def other_squirrels_you_control(source: GameObject):
    """Filter: Other Squirrels you control."""
    return other_creatures_with_subtype(source, "Squirrel")


def other_frogs_you_control(source: GameObject):
    """Filter: Other Frogs you control."""
    return other_creatures_with_subtype(source, "Frog")


def lizards_mice_otters_raccoons_you_control(source: GameObject):
    """Filter: Lizards, Mice, Otters, and Raccoons you control."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        if target.controller != source.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        subtypes = target.characteristics.subtypes
        return bool(subtypes & {"Lizard", "Mouse", "Otter", "Raccoon"})
    return filter_fn


def birds_frogs_otters_rats_you_control(source: GameObject):
    """Filter: Birds, Frogs, Otters, and Rats you control."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        if target.controller != source.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        subtypes = target.characteristics.subtypes
        return bool(subtypes & {"Bird", "Frog", "Otter", "Rat"})
    return filter_fn


# -----------------------------------------------------------------------------
# VALLEY QUESTCALLER - Lord effect for Rabbits, Bats, Birds, Mice
# Other Rabbits, Bats, Birds, and Mice you control get +1/+1.
# -----------------------------------------------------------------------------
def valley_questcaller_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = make_static_pt_boost(
        obj, 1, 1, other_rabbits_bats_birds_mice(obj)
    )

    # Triggered ability: Whenever one or more other Rabbits/Bats/Birds/Mice enter, scry 1.
    def tribal_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
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
        if entering.controller != source.controller:
            return False
        if CardType.CREATURE not in entering.characteristics.types:
            return False
        return bool(entering.characteristics.subtypes & {"Rabbit", "Bat", "Bird", "Mouse"})

    def scry_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY,
                      payload={'player': obj.controller, 'amount': 1},
                      source=obj.id)]

    interceptors.append(make_etb_trigger(obj, scry_effect, tribal_etb_filter))
    return interceptors


# -----------------------------------------------------------------------------
# MABEL, HEIR TO CRAGFLAME - Mouse lord (+1/+1) and ETB token creation
# Other Mice you control get +1/+1.
# When Mabel enters, create Cragflame equipment token.
# -----------------------------------------------------------------------------
def mabel_heir_to_cragflame_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = make_static_pt_boost(obj, 1, 1, other_mice_you_control(obj))

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Create equipment token (simplified - just creates an artifact token)
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token_type': 'Equipment',
                'name': 'Cragflame',
                'characteristics': {'types': {CardType.ARTIFACT}}
            },
            source=obj.id
        )]

    interceptors.append(make_etb_trigger(obj, etb_effect))
    return interceptors


# -----------------------------------------------------------------------------
# CAMELLIA, THE SEEDMISER - Squirrel lord (grants menace)
# Other Squirrels you control have menace.
# -----------------------------------------------------------------------------
def camellia_the_seedmiser_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_keyword_grant(obj, ['menace'], other_squirrels_you_control(obj))]


# -----------------------------------------------------------------------------
# LONG RIVER LURKER - Grants ward {1} to other Frogs
# Other Frogs you control have ward {1}.
# -----------------------------------------------------------------------------
def long_river_lurker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_keyword_grant(obj, ['ward_1'], other_frogs_you_control(obj))]


# -----------------------------------------------------------------------------
# LIFECREED DUO - ETB life gain trigger
# Whenever another creature you control enters, you gain 1 life.
# -----------------------------------------------------------------------------
def lifecreed_duo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def other_creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
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
                CardType.CREATURE in entering.characteristics.types)

    def life_gain_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    return [make_etb_trigger(obj, life_gain_effect, other_creature_etb_filter)]


# -----------------------------------------------------------------------------
# BELLOWING CRIER - ETB draw/discard
# When this creature enters, draw a card, then discard a card.
# -----------------------------------------------------------------------------
def bellowing_crier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# POND PROPHET - ETB draw a card
# When this creature enters, draw a card.
# -----------------------------------------------------------------------------
def pond_prophet_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# GLIDEDIVE DUO - ETB drain
# When this creature enters, each opponent loses 2 life and you gain 2 life.
# -----------------------------------------------------------------------------
def glidedive_duo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -2},
                    source=obj.id
                ))
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# HEAD OF THE HOMESTEAD - ETB create two 1/1 Rabbit tokens
# When this creature enters, create two 1/1 white Rabbit creature tokens.
# -----------------------------------------------------------------------------
def head_of_the_homestead_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller, 'token_type': 'Creature',
                'name': 'Rabbit', 'power': 1, 'toughness': 1,
                'colors': {Color.WHITE}, 'subtypes': {'Rabbit'}
            }, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller, 'token_type': 'Creature',
                'name': 'Rabbit', 'power': 1, 'toughness': 1,
                'colors': {Color.WHITE}, 'subtypes': {'Rabbit'}
            }, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# PILEATED PROVISIONER - ETB put +1/+1 counter on target
# When this creature enters, put a +1/+1 counter on target creature you control without flying.
# -----------------------------------------------------------------------------
def _pileated_provisioner_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Pileated Provisioner: Put +1/+1 counter on target creature without flying."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.COUNTER_ADDED,
        payload={'object_id': target_id, 'counter_type': '+1/+1', 'amount': 1},
        source=choice.source_id
    )]


def pileated_provisioner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find valid targets: creatures you control without flying
        valid_targets = [
            perm.id for perm in state.objects.values()
            if (perm.controller == obj.controller and
                perm.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in perm.characteristics.types and
                perm.id != obj.id and
                'flying' not in perm.characteristics.keywords)
        ]

        if not valid_targets:
            return []

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature without flying to put a +1/+1 counter on",
            min_targets=1,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = _pileated_provisioner_execute

        return []

    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# SUNSHOWER DRUID - ETB +1/+1 counter and gain 1 life
# When this creature enters, put a +1/+1 counter on target creature and you gain 1 life.
# -----------------------------------------------------------------------------
def _sunshower_druid_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Sunshower Druid: Put +1/+1 counter on target creature and gain 1 life."""
    target_id = selected[0] if selected else None

    events = [Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': choice.player, 'amount': 1},
        source=choice.source_id
    )]

    if target_id:
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': target_id, 'counter_type': '+1/+1', 'amount': 1},
                source=choice.source_id
            ))

    return events


def sunshower_druid_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find valid targets: any creature
        valid_targets = [
            perm.id for perm in state.objects.values()
            if (perm.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in perm.characteristics.types)
        ]

        if not valid_targets:
            # Still gain life even without targets
            return [Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )]

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature to put a +1/+1 counter on",
            min_targets=1,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = _sunshower_druid_execute

        return []

    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# FINCH FORMATION - ETB grant flying to target
# When this creature enters, target creature you control gains flying until end of turn.
# -----------------------------------------------------------------------------
def _finch_formation_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Finch Formation: Target creature gains flying until end of turn."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.GRANT_KEYWORD,
        payload={'object_id': target_id, 'keyword': 'flying', 'duration': 'end_of_turn'},
        source=choice.source_id
    )]


def finch_formation_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        valid_targets = [
            perm.id for perm in state.objects.values()
            if (perm.controller == obj.controller and
                perm.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in perm.characteristics.types)
        ]

        if not valid_targets:
            return []

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature to gain flying until end of turn",
            min_targets=1,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = _finch_formation_execute

        return []

    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# PLUMECREED ESCORT - ETB grant hexproof to target
# When this creature enters, target creature you control gains hexproof until end of turn.
# -----------------------------------------------------------------------------
def _plumecreed_escort_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Plumecreed Escort: Target creature gains hexproof until end of turn."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.GRANT_KEYWORD,
        payload={'object_id': target_id, 'keyword': 'hexproof', 'duration': 'end_of_turn'},
        source=choice.source_id
    )]


def plumecreed_escort_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        valid_targets = [
            perm.id for perm in state.objects.values()
            if (perm.controller == obj.controller and
                perm.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in perm.characteristics.types)
        ]

        if not valid_targets:
            return []

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature to gain hexproof until end of turn",
            min_targets=1,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = _plumecreed_escort_execute

        return []

    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# DRIFTGLOOM COYOTE - ETB exile target creature opponent controls
# When this creature enters, exile target creature an opponent controls until this leaves.
# -----------------------------------------------------------------------------
def _driftgloom_coyote_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Driftgloom Coyote: Exile target creature opponent controls."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    events = [Event(
        type=EventType.EXILE,
        payload={'object_id': target_id, 'until_leaves': choice.source_id},
        source=choice.source_id
    )]

    # If power 2 or less, put +1/+1 counter on Driftgloom Coyote
    power = get_power(target, state)
    if power <= 2:
        events.append(Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': choice.source_id, 'counter_type': '+1/+1', 'amount': 1},
            source=choice.source_id
        ))

    return events


def driftgloom_coyote_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        valid_targets = [
            perm.id for perm in state.objects.values()
            if (perm.controller != obj.controller and
                perm.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in perm.characteristics.types)
        ]

        if not valid_targets:
            return []

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature an opponent controls to exile",
            min_targets=1,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = _driftgloom_coyote_execute

        return []

    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# SPLASH LASHER - ETB tap and stun counter
# When this creature enters, tap up to one target creature and put a stun counter on it.
# -----------------------------------------------------------------------------
def _splash_lasher_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Splash Lasher: Tap target creature and put a stun counter on it."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(type=EventType.TAP, payload={'object_id': target_id}, source=choice.source_id),
        Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': target_id, 'counter_type': 'stun', 'amount': 1
        }, source=choice.source_id)
    ]


def splash_lasher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find valid targets: up to one creature
        valid_targets = [
            perm.id for perm in state.objects.values()
            if (perm.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in perm.characteristics.types and
                perm.id != obj.id)
        ]

        if not valid_targets:
            return []

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature to tap and put a stun counter on (or 0 for none)",
            min_targets=0,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = _splash_lasher_execute

        return []

    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# EDDYMURK CRAB - ETB tap up to two creatures
# When this creature enters, tap up to two target creatures.
# -----------------------------------------------------------------------------
def _eddymurk_crab_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Eddymurk Crab: Tap up to two target creatures."""
    events = []
    for target_id in selected:
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            events.append(Event(type=EventType.TAP, payload={'object_id': target_id}, source=choice.source_id))
    return events


def eddymurk_crab_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find valid targets: any creature
        valid_targets = [
            perm.id for perm in state.objects.values()
            if (perm.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in perm.characteristics.types and
                perm.id != obj.id)
        ]

        if not valid_targets:
            return []

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose up to two creatures to tap",
            min_targets=0,
            max_targets=2
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = _eddymurk_crab_execute

        return []

    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# VINEREAP MENTOR - ETB and death Food token creation
# When this creature enters or dies, create a Food token.
# -----------------------------------------------------------------------------
def vinereap_mentor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def create_food(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token_type': 'Artifact',
                'name': 'Food',
                'subtypes': {'Food'}
            },
            source=obj.id
        )]

    return [
        make_etb_trigger(obj, create_food),
        make_death_trigger(obj, create_food)
    ]


# -----------------------------------------------------------------------------
# BAKERSBANE DUO - ETB create Food token
# When this creature enters, create a Food token.
# -----------------------------------------------------------------------------
def bakersbane_duo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token_type': 'Artifact',
                'name': 'Food',
                'subtypes': {'Food'}
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# HEARTFIRE HERO - Death trigger deals damage
# When this creature dies, it deals damage equal to its power to each opponent.
# -----------------------------------------------------------------------------
def heartfire_hero_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def death_effect(event: Event, state: GameState) -> list[Event]:
        power = get_power(obj, state)
        events = []
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': power, 'source': obj.id, 'is_combat': False},
                    source=obj.id
                ))
        return events
    return [make_death_trigger(obj, death_effect)]


# -----------------------------------------------------------------------------
# STEAMPATH CHARGER - Death trigger deals damage
# When this creature dies, it deals 1 damage to target player.
# -----------------------------------------------------------------------------
def steampath_charger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def death_effect(event: Event, state: GameState) -> list[Event]:
        # Deal to first opponent found
        for player_id in state.players:
            if player_id != obj.controller:
                return [Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 1, 'source': obj.id, 'is_combat': False},
                    source=obj.id
                )]
        return []
    return [make_death_trigger(obj, death_effect)]


# -----------------------------------------------------------------------------
# AGATE-BLADE ASSASSIN - Attack trigger drain
# Whenever this creature attacks, defending player loses 1 life and you gain 1 life.
# -----------------------------------------------------------------------------
def agateblade_assassin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        defending = event.payload.get('defending_player')
        events = []
        if defending:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': defending, 'amount': -1},
                source=obj.id
            ))
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        ))
        return events
    return [make_attack_trigger(obj, attack_effect)]


# -----------------------------------------------------------------------------
# MOONRISE CLERIC - Attack trigger life gain
# Whenever this creature attacks, you gain 1 life.
# -----------------------------------------------------------------------------
def moonrise_cleric_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


# -----------------------------------------------------------------------------
# THISTLEDOWN PLAYERS - Attack trigger untap
# Whenever this creature attacks, untap target nonland permanent.
# -----------------------------------------------------------------------------
def thistledown_players_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Find a tapped nonland permanent to untap
        for target in state.objects.values():
            if (target.zone == ZoneType.BATTLEFIELD and
                CardType.LAND not in target.characteristics.types and
                target.state.tapped):
                return [Event(type=EventType.UNTAP, payload={'object_id': target.id}, source=obj.id)]
        return []
    return [make_attack_trigger(obj, attack_effect)]


# -----------------------------------------------------------------------------
# BRAZEN COLLECTOR - Attack trigger add mana
# Whenever this creature attacks, add {R}.
# -----------------------------------------------------------------------------
def brazen_collector_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.ADD_MANA,
            payload={'player': obj.controller, 'mana': 'R'},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


# -----------------------------------------------------------------------------
# KNIGHTFISHER - Other Birds ETB creates Fish token
# Whenever another nontoken Bird you control enters, create a 1/1 blue Fish creature token.
# -----------------------------------------------------------------------------
def knightfisher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def bird_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
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
        # Must be nontoken Bird we control
        return (entering.controller == source.controller and
                CardType.CREATURE in entering.characteristics.types and
                'Bird' in entering.characteristics.subtypes and
                not entering.state.is_token)

    def create_fish(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token_type': 'Creature',
                'name': 'Fish',
                'power': 1, 'toughness': 1,
                'colors': {Color.BLUE},
                'subtypes': {'Fish'}
            },
            source=obj.id
        )]

    return [make_etb_trigger(obj, create_fish, bird_etb_filter)]


# -----------------------------------------------------------------------------
# PLUMECREED MENTOR - Flying creature ETB puts +1/+1 counter
# Whenever this creature or another creature you control with flying enters,
# put a +1/+1 counter on target creature you control without flying.
# -----------------------------------------------------------------------------
def plumecreed_mentor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def flying_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        # This creature or another with flying we control
        if entering_id == source.id:
            return True
        return (entering.controller == source.controller and
                CardType.CREATURE in entering.characteristics.types and
                'flying' in entering.characteristics.keywords)

    def counter_effect(event: Event, state: GameState) -> list[Event]:
        # Find creature without flying
        for target in state.objects.values():
            if (target.controller == obj.controller and
                target.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in target.characteristics.types and
                'flying' not in target.characteristics.keywords):
                return [Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': target.id, 'counter_type': '+1/+1', 'amount': 1},
                    source=obj.id
                )]
        return []

    return [make_etb_trigger(obj, counter_effect, flying_etb_filter)]


# -----------------------------------------------------------------------------
# VALLEY MIGHTCALLER - Other creature type ETB puts +1/+1 counter on self
# Whenever another Frog, Rabbit, Raccoon, or Squirrel you control enters,
# put a +1/+1 counter on this creature.
# -----------------------------------------------------------------------------
def valley_mightcaller_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def creature_type_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
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
                CardType.CREATURE in entering.characteristics.types and
                bool(entering.characteristics.subtypes & {"Frog", "Rabbit", "Raccoon", "Squirrel"}))

    def counter_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [make_etb_trigger(obj, counter_effect, creature_type_etb_filter)]


# -----------------------------------------------------------------------------
# HONORED DREYLEADER - ETB and ongoing +1/+1 for Squirrels/Food
# When this creature enters, put a +1/+1 counter on it for each other Squirrel and/or Food you control.
# Whenever another Squirrel or Food you control enters, put a +1/+1 counter on this creature.
# -----------------------------------------------------------------------------
def honored_dreyleader_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        count = 0
        for permanent in state.objects.values():
            if permanent.id == obj.id:
                continue
            if permanent.controller != obj.controller:
                continue
            if permanent.zone != ZoneType.BATTLEFIELD:
                continue
            is_squirrel = (CardType.CREATURE in permanent.characteristics.types and
                          'Squirrel' in permanent.characteristics.subtypes)
            is_food = 'Food' in permanent.characteristics.subtypes
            if is_squirrel or is_food:
                count += 1
        if count > 0:
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': count},
                source=obj.id
            )]
        return []

    def squirrel_food_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
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
        if entering.controller != source.controller:
            return False
        is_squirrel = (CardType.CREATURE in entering.characteristics.types and
                      'Squirrel' in entering.characteristics.subtypes)
        is_food = 'Food' in entering.characteristics.subtypes
        return is_squirrel or is_food

    def counter_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [
        make_etb_trigger(obj, etb_effect),
        make_etb_trigger(obj, counter_effect, squirrel_food_etb_filter)
    ]


# -----------------------------------------------------------------------------
# CORUSCATION MAGE - Spell cast trigger deals damage
# Whenever you cast a noncreature spell, this creature deals 1 damage to each opponent.
# -----------------------------------------------------------------------------
def coruscation_mage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 1, 'source': obj.id, 'is_combat': False},
                    source=obj.id
                ))
        return events

    def noncreature_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.CREATURE not in spell_types

    return [make_spell_cast_trigger(obj, damage_effect, filter_fn=noncreature_filter)]


# -----------------------------------------------------------------------------
# TEMPEST ANGLER - Spell cast trigger +1/+1 counter
# Whenever you cast a noncreature spell, put a +1/+1 counter on this creature.
# -----------------------------------------------------------------------------
def tempest_angler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def counter_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    def noncreature_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.CREATURE not in spell_types

    return [make_spell_cast_trigger(obj, counter_effect, filter_fn=noncreature_filter)]


# -----------------------------------------------------------------------------
# STARSCAPE CLERIC - Life gain trigger opponent loses life
# Whenever you gain life, each opponent loses 1 life.
# -----------------------------------------------------------------------------
def starscape_cleric_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
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
    return [make_life_gain_trigger(obj, opponent_life_loss, controller_only=True)]


# -----------------------------------------------------------------------------
# ESSENCE CHANNELER - Life gain trigger +1/+1 counter
# Whenever you gain life, put a +1/+1 counter on this creature.
# -----------------------------------------------------------------------------
def essence_channeler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def counter_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_life_gain_trigger(obj, counter_effect, controller_only=True)]


# -----------------------------------------------------------------------------
# THIEVING OTTER - Damage trigger draw a card
# Whenever this creature deals damage to an opponent, draw a card.
# -----------------------------------------------------------------------------
def thieving_otter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]

    def opponent_damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != source.id:
            return False
        target = event.payload.get('target')
        # Target is a player and not controller
        return target in state.players and target != source.controller

    return [make_damage_trigger(obj, draw_effect, filter_fn=opponent_damage_filter)]


# -----------------------------------------------------------------------------
# INTREPID RABBIT - ETB +1/+1 until end of turn
# When this creature enters, target creature you control gets +1/+1 until end of turn.
# -----------------------------------------------------------------------------
def _intrepid_rabbit_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Intrepid Rabbit: Target creature gets +1/+1 until end of turn."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.PUMP,
        payload={'object_id': target_id, 'power': 1, 'toughness': 1, 'duration': 'end_of_turn'},
        source=choice.source_id
    )]


def intrepid_rabbit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        valid_targets = [
            perm.id for perm in state.objects.values()
            if (perm.controller == obj.controller and
                perm.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in perm.characteristics.types)
        ]

        if not valid_targets:
            return []

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature to get +1/+1 until end of turn",
            min_targets=1,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = _intrepid_rabbit_execute

        return []

    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# THORNPLATE INTIMIDATOR - ETB opponent loses 3 life unless sacrifice/discard
# When this creature enters, target opponent loses 3 life unless they sacrifice
# a nonland permanent of their choice or discard a card.
# -----------------------------------------------------------------------------
def thornplate_intimidator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified: opponent just loses 3 life
        for player_id in state.players:
            if player_id != obj.controller:
                return [Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -3},
                    source=obj.id
                )]
        return []
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# DARKSTAR AUGUR - Upkeep trigger reveal and draw
# At the beginning of your upkeep, reveal the top card of your library
# and put that card into your hand. You lose life equal to its mana value.
# -----------------------------------------------------------------------------
def darkstar_augur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified: draw a card and lose 3 life (average mana value)
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': -3}, source=obj.id)
        ]
    return [make_upkeep_trigger(obj, upkeep_effect, controller_only=True)]


# -----------------------------------------------------------------------------
# MINDWHISKER - Upkeep trigger surveil
# At the beginning of your upkeep, surveil 1.
# -----------------------------------------------------------------------------
def mindwhisker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SURVEIL, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_upkeep_trigger(obj, upkeep_effect, controller_only=True)]


# -----------------------------------------------------------------------------
# SERRA REDEEMER - Other small creature ETB +1/+1 counters
# Whenever another creature you control with power 2 or less enters,
# put two +1/+1 counters on that creature.
# -----------------------------------------------------------------------------
def serra_redeemer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def small_creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
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
        if entering.controller != source.controller:
            return False
        if CardType.CREATURE not in entering.characteristics.types:
            return False
        power = get_power(entering, state)
        return power <= 2

    def counter_effect(event: Event, state: GameState) -> list[Event]:
        entering_id = event.payload.get('object_id')
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': entering_id, 'counter_type': '+1/+1', 'amount': 2},
            source=obj.id
        )]

    return [make_etb_trigger(obj, counter_effect, small_creature_etb_filter)]


# -----------------------------------------------------------------------------
# BRIA, RIPTIDE ROGUE - Grants prowess to other creatures
# Other creatures you control have prowess.
# -----------------------------------------------------------------------------
def bria_riptide_rogue_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_keyword_grant(obj, ['prowess'], other_creatures_you_control(obj))]


# -----------------------------------------------------------------------------
# DAGGERFANG DUO - ETB mill two cards
# When this creature enters, you may mill two cards.
# -----------------------------------------------------------------------------
def daggerfang_duo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MILL, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# LIGHTSHELL DUO - ETB surveil 2
# When this creature enters, surveil 2.
# -----------------------------------------------------------------------------
def lightshell_duo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SURVEIL, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# ZORALINE, COSMOS CALLER - Bat attacks life gain
# Whenever a Bat you control attacks, you gain 1 life.
# -----------------------------------------------------------------------------
def zoraline_cosmos_caller_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def bat_attack_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        return (attacker.controller == source.controller and
                'Bat' in attacker.characteristics.subtypes)

    def life_gain_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    return [make_attack_trigger(obj, life_gain_effect, bat_attack_filter)]


# -----------------------------------------------------------------------------
# FINNEAS, ACE ARCHER - Attack trigger +1/+1 counters
# Whenever Finneas attacks, put a +1/+1 counter on each other creature you control
# that's a token or a Rabbit.
# -----------------------------------------------------------------------------
def finneas_ace_archer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for target in state.objects.values():
            if target.id == obj.id:
                continue
            if target.controller != obj.controller:
                continue
            if target.zone != ZoneType.BATTLEFIELD:
                continue
            if CardType.CREATURE not in target.characteristics.types:
                continue
            is_token = target.state.is_token
            is_rabbit = 'Rabbit' in target.characteristics.subtypes
            if is_token or is_rabbit:
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': target.id, 'counter_type': '+1/+1', 'amount': 1},
                    source=obj.id
                ))
        return events
    return [make_attack_trigger(obj, attack_effect)]


# -----------------------------------------------------------------------------
# GEV, SCALED SCORCH - Lizard cast trigger deals damage
# Whenever you cast a Lizard spell, Gev deals 1 damage to target opponent.
# -----------------------------------------------------------------------------
def gev_scaled_scorch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        for player_id in state.players:
            if player_id != obj.controller:
                return [Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 1, 'source': obj.id, 'is_combat': False},
                    source=obj.id
                )]
        return []

    def lizard_cast_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source.controller:
            return False
        spell_subtypes = set(event.payload.get('subtypes', []))
        return 'Lizard' in spell_subtypes

    return [make_spell_cast_trigger(obj, damage_effect, filter_fn=lizard_cast_filter)]


# -----------------------------------------------------------------------------
# WICK, THE WHORLED MIND - Rat ETB creates/grows Snail
# Whenever Wick or another Rat you control enters, create a 1/1 black Snail creature token
# if you don't control a Snail. Otherwise, put a +1/+1 counter on a Snail you control.
# -----------------------------------------------------------------------------
def wick_the_whorled_mind_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def rat_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        # Wick itself or another Rat we control
        if entering_id == source.id:
            return True
        return (entering.controller == source.controller and
                CardType.CREATURE in entering.characteristics.types and
                'Rat' in entering.characteristics.subtypes)

    def snail_effect(event: Event, state: GameState) -> list[Event]:
        # Check if we control a Snail
        for permanent in state.objects.values():
            if (permanent.controller == obj.controller and
                permanent.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in permanent.characteristics.types and
                'Snail' in permanent.characteristics.subtypes):
                # Put counter on Snail
                return [Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': permanent.id, 'counter_type': '+1/+1', 'amount': 1},
                    source=obj.id
                )]
        # Create Snail token
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token_type': 'Creature',
                'name': 'Snail',
                'power': 1, 'toughness': 1,
                'colors': {Color.BLACK},
                'subtypes': {'Snail'}
            },
            source=obj.id
        )]

    return [make_etb_trigger(obj, snail_effect, rat_etb_filter)]


# -----------------------------------------------------------------------------
# STORMCATCH MENTOR - Cost reduction for instants/sorceries
# Instant and sorcery spells you cast cost {1} less to cast.
# (Static ability - simplified, not fully implementable without cost system)
# -----------------------------------------------------------------------------
def stormcatch_mentor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Prowess and cost reduction are complex - just return empty for now
    return []


# -----------------------------------------------------------------------------
# VALLEY FLAMECALLER - Damage boost static ability
# If a Lizard, Mouse, Otter, or Raccoon you control would deal damage to a permanent
# or player, it deals that much damage plus 1 instead.
# -----------------------------------------------------------------------------
def valley_flamecaller_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def damage_boost_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        source_id = event.payload.get('source')
        source_obj = state.objects.get(source_id)
        if not source_obj:
            return False
        if source_obj.controller != obj.controller:
            return False
        if CardType.CREATURE not in source_obj.characteristics.types:
            return False
        subtypes = source_obj.characteristics.subtypes
        return bool(subtypes & {"Lizard", "Mouse", "Otter", "Raccoon"})

    def damage_boost_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        current = new_event.payload.get('amount', 0)
        new_event.payload['amount'] = current + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=damage_boost_filter,
        handler=damage_boost_handler,
        duration='while_on_battlefield'
    )]


# -----------------------------------------------------------------------------
# PATCHWORK BANNER - Creature type lord
# Creatures you control of the chosen type get +1/+1.
# -----------------------------------------------------------------------------
def patchwork_banner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # This requires tracking chosen type - simplified to boost all creatures
    return make_static_pt_boost(obj, 1, 1, creatures_you_control(obj))


# -----------------------------------------------------------------------------
# SEASONED WARRENGUARD - Attack trigger +2/+0 if control a token
# Whenever this creature attacks while you control a token, it gets +2/+0.
# -----------------------------------------------------------------------------
def seasoned_warrenguard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Check if we control a token
        for permanent in state.objects.values():
            if (permanent.controller == obj.controller and
                permanent.zone == ZoneType.BATTLEFIELD and
                permanent.state.is_token):
                return [Event(
                    type=EventType.PUMP,
                    payload={'object_id': obj.id, 'power': 2, 'toughness': 0, 'duration': 'end_of_turn'},
                    source=obj.id
                )]
        return []
    return [make_attack_trigger(obj, attack_effect)]


# -----------------------------------------------------------------------------
# HARVESTRITE HOST - Rabbit ETB pump trigger
# Whenever this creature or another Rabbit you control enters, target gets +1/+0.
# -----------------------------------------------------------------------------
def harvestrite_host_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def rabbit_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        # This creature or another Rabbit we control
        if entering_id == source.id:
            return True
        return (entering.controller == source.controller and
                CardType.CREATURE in entering.characteristics.types and
                'Rabbit' in entering.characteristics.subtypes)

    def pump_effect(event: Event, state: GameState) -> list[Event]:
        # Find a creature to pump
        for target in state.objects.values():
            if (target.controller == obj.controller and
                target.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in target.characteristics.types):
                return [Event(
                    type=EventType.PUMP,
                    payload={'object_id': target.id, 'power': 1, 'toughness': 0, 'duration': 'end_of_turn'},
                    source=obj.id
                )]
        return []

    return [make_etb_trigger(obj, pump_effect, rabbit_etb_filter)]


# -----------------------------------------------------------------------------
# JACKDAW SAVIOR - Flying creature death trigger returns creature from graveyard
# -----------------------------------------------------------------------------
def jackdaw_savior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def flying_death_filter(event: Event, state: GameState, source: GameObject) -> bool:
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
        # This creature or another with flying we control
        if dying_id == source.id:
            return True
        return (dying.controller == source.controller and
                CardType.CREATURE in dying.characteristics.types and
                'flying' in dying.characteristics.keywords)

    def return_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified - return a creature from graveyard (needs targeting system)
        return [Event(
            type=EventType.RETURN_FROM_GRAVEYARD,
            payload={'controller': obj.controller},
            source=obj.id
        )]

    return [make_death_trigger(obj, return_effect, flying_death_filter)]


# -----------------------------------------------------------------------------
# SALVATION SWAN - Bird ETB flicker trigger
# Whenever this creature or another Bird you control enters, exile creature and return.
# -----------------------------------------------------------------------------
def _salvation_swan_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Salvation Swan: Exile target creature without flying, return with flying counter."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.FLICKER,
        payload={'object_id': target_id, 'with_flying_counter': True},
        source=choice.source_id
    )]


def salvation_swan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def bird_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        if entering_id == source.id:
            return True
        return (entering.controller == source.controller and
                CardType.CREATURE in entering.characteristics.types and
                'Bird' in entering.characteristics.subtypes)

    def flicker_effect(event: Event, state: GameState) -> list[Event]:
        # Find valid targets: creatures without flying that we control
        valid_targets = [
            perm.id for perm in state.objects.values()
            if (perm.controller == obj.controller and
                perm.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in perm.characteristics.types and
                perm.id != obj.id and
                'flying' not in perm.characteristics.keywords)
        ]

        if not valid_targets:
            return []

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature without flying to exile and return with flying counter (or 0 for none)",
            min_targets=0,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = _salvation_swan_execute

        return []

    return [make_etb_trigger(obj, flicker_effect, bird_etb_filter)]


# -----------------------------------------------------------------------------
# VALLEY ROTCALLER - Attack trigger drain based on creature types
# Whenever this creature attacks, each opponent loses X life and you gain X life.
# -----------------------------------------------------------------------------
def valley_rotcaller_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        count = 0
        for permanent in state.objects.values():
            if permanent.id == obj.id:
                continue
            if permanent.controller != obj.controller:
                continue
            if permanent.zone != ZoneType.BATTLEFIELD:
                continue
            if CardType.CREATURE not in permanent.characteristics.types:
                continue
            subtypes = permanent.characteristics.subtypes
            if subtypes & {"Squirrel", "Bat", "Lizard", "Rat"}:
                count += 1
        if count > 0:
            events = []
            for player_id in state.players:
                if player_id != obj.controller:
                    events.append(Event(
                        type=EventType.LIFE_CHANGE,
                        payload={'player': player_id, 'amount': -count},
                        source=obj.id
                    ))
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': count},
                source=obj.id
            ))
            return events
        return []
    return [make_attack_trigger(obj, attack_effect)]


# -----------------------------------------------------------------------------
# STARSEER MENTOR - End step drain trigger
# At the beginning of your end step, if you gained or lost life this turn,
# target opponent loses 3 life unless they sacrifice or discard.
# -----------------------------------------------------------------------------
def starseer_mentor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified - just drain 3 from opponents
        events = []
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -3},
                    source=obj.id
                ))
        return events
    return [make_end_step_trigger(obj, end_step_effect, controller_only=True)]


# -----------------------------------------------------------------------------
# SEEDPOD SQUIRE - Attack trigger pump creature without flying
# Whenever this creature attacks, target creature you control without flying gets +1/+1.
# -----------------------------------------------------------------------------
def seedpod_squire_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        for target in state.objects.values():
            if (target.controller == obj.controller and
                target.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in target.characteristics.types and
                'flying' not in target.characteristics.keywords):
                return [Event(
                    type=EventType.PUMP,
                    payload={'object_id': target.id, 'power': 1, 'toughness': 1, 'duration': 'end_of_turn'},
                    source=obj.id
                )]
        return []
    return [make_attack_trigger(obj, attack_effect)]


# -----------------------------------------------------------------------------
# STICKYTONGUE SENTINEL - ETB bounce another permanent you control
# When this creature enters, return up to one other target permanent you control to hand.
# -----------------------------------------------------------------------------
def stickytongue_sentinel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find a creature to bounce (simplified targeting)
        for target in state.objects.values():
            if (target.controller == obj.controller and
                target.zone == ZoneType.BATTLEFIELD and
                target.id != obj.id):
                return [Event(
                    type=EventType.BOUNCE,
                    payload={'object_id': target.id},
                    source=obj.id
                )]
        return []
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# SKYSKIPPER DUO - ETB flicker
# When this creature enters, exile up to one other target creature you control.
# Return it at the beginning of the next end step.
# -----------------------------------------------------------------------------
def skyskipper_duo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        for target in state.objects.values():
            if (target.controller == obj.controller and
                target.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in target.characteristics.types and
                target.id != obj.id):
                return [Event(
                    type=EventType.FLICKER,
                    payload={'object_id': target.id},
                    source=obj.id
                )]
        return []
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# DOWNWIND AMBUSHER - ETB choice: -1/-1 or destroy damaged creature
# -----------------------------------------------------------------------------
def downwind_ambusher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified - just do -1/-1 to opponent's creature
        for target in state.objects.values():
            if (target.controller != obj.controller and
                target.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in target.characteristics.types):
                return [Event(
                    type=EventType.PUMP,
                    payload={'object_id': target.id, 'power': -1, 'toughness': -1, 'duration': 'end_of_turn'},
                    source=obj.id
                )]
        return []
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# ALANIAS PATHMAKER - ETB exile top card, may play until end of next turn
# -----------------------------------------------------------------------------
def alanias_pathmaker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.IMPULSE_DRAW,
            payload={'player': obj.controller, 'amount': 1, 'duration': 'next_end_step'},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# CLIFFTOP LOOKOUT - ETB reveal cards until land, put land onto battlefield
# -----------------------------------------------------------------------------
def clifftop_lookout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.REVEAL_UNTIL_LAND,
            payload={'player': obj.controller},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# DREAMDEW ENTRANCER - ETB tap and stun
# When this creature enters, tap up to one target creature and put three stun counters on it.
# -----------------------------------------------------------------------------
def dreamdew_entrancer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        for target in state.objects.values():
            if (target.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in target.characteristics.types and
                target.id != obj.id):
                return [
                    Event(type=EventType.TAP, payload={'object_id': target.id}, source=obj.id),
                    Event(type=EventType.COUNTER_ADDED, payload={
                        'object_id': target.id, 'counter_type': 'stun', 'amount': 3
                    }, source=obj.id)
                ]
        return []
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# TREEGUARD DUO - ETB pump based on creature count
# When this creature enters, target creature you control gains vigilance and gets +X/+X.
# -----------------------------------------------------------------------------
def treeguard_duo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        creature_count = sum(
            1 for p in state.objects.values()
            if (p.controller == obj.controller and
                p.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in p.characteristics.types)
        )
        for target in state.objects.values():
            if (target.controller == obj.controller and
                target.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in target.characteristics.types):
                return [
                    Event(type=EventType.PUMP, payload={
                        'object_id': target.id,
                        'power': creature_count, 'toughness': creature_count,
                        'duration': 'end_of_turn'
                    }, source=obj.id),
                    Event(type=EventType.GRANT_KEYWORD, payload={
                        'object_id': target.id, 'keyword': 'vigilance', 'duration': 'end_of_turn'
                    }, source=obj.id)
                ]
        return []
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# HIVESPINE WOLVERINE - ETB modal: counter, fight, or destroy artifact/enchantment
# -----------------------------------------------------------------------------
def hivespine_wolverine_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified - put counter on a creature we control
        for target in state.objects.values():
            if (target.controller == obj.controller and
                target.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in target.characteristics.types):
                return [Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': target.id, 'counter_type': '+1/+1', 'amount': 1},
                    source=obj.id
                )]
        return []
    return [make_etb_trigger(obj, etb_effect)]


# =============================================================================
# AUTO-GENERATED SETUP FUNCTIONS (Bloomburrow missing cards)
# =============================================================================

# -----------------------------------------------------------------------------
# Filter helpers for BLB animal-tribal mechanics
# -----------------------------------------------------------------------------
def _other_bats_you_control(source: GameObject):
    return other_creatures_with_subtype(source, "Bat")


def _other_rats_you_control(source: GameObject):
    return other_creatures_with_subtype(source, "Rat")


def _attacking_creatures_you_control(source: GameObject):
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.controller == source.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD and
                target.state.attacking)
    return filter_fn


# -----------------------------------------------------------------------------
# WHITE CARDS
# -----------------------------------------------------------------------------

def beza_the_bounding_spring_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Beza enters, conditional Treasure/life/Fish/draw based on opponent comparisons."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        opp_ids = [pid for pid in state.players if pid != obj.controller]
        if not opp_ids:
            return events

        def count_for(controller_id: str, card_type: CardType) -> int:
            return sum(
                1 for o in state.objects.values()
                if o.controller == controller_id and o.zone == ZoneType.BATTLEFIELD
                and card_type in o.characteristics.types
            )

        def hand_size(controller_id: str) -> int:
            for zone in state.zones.values():
                if zone.type == ZoneType.HAND and zone.owner == controller_id:
                    return len(zone.objects)
            return 0

        my_lands = count_for(obj.controller, CardType.LAND)
        my_creatures = count_for(obj.controller, CardType.CREATURE)
        my_hand = hand_size(obj.controller)
        my_life = state.players[obj.controller].life

        for opp in opp_ids:
            if count_for(opp, CardType.LAND) > my_lands:
                events.append(Event(
                    type=EventType.CREATE_TOKEN,
                    payload={'controller': obj.controller, 'token_type': 'Artifact',
                             'name': 'Treasure', 'subtypes': {'Treasure'}},
                    source=obj.id))
                break
        for opp in opp_ids:
            if state.players[opp].life > my_life:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': obj.controller, 'amount': 4}, source=obj.id))
                break
        for opp in opp_ids:
            if count_for(opp, CardType.CREATURE) > my_creatures:
                for _ in range(2):
                    events.append(Event(
                        type=EventType.CREATE_TOKEN,
                        payload={'controller': obj.controller, 'token_type': 'Creature',
                                 'name': 'Fish', 'power': 1, 'toughness': 1,
                                 'colors': {Color.BLUE}, 'subtypes': {'Fish'}},
                        source=obj.id))
                break
        for opp in opp_ids:
            if hand_size(opp) > my_hand:
                events.append(Event(
                    type=EventType.DRAW,
                    payload={'player': obj.controller, 'amount': 1}, source=obj.id))
                break
        return events

    return [make_etb_trigger(obj, etb_effect)]


def bravekin_duo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: activated {1}{T} sorcery-speed ability (target +1/+1 UEOT)
    return []


def builders_talent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Class enters: create 0/4 white Wall token with defender."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={'controller': obj.controller, 'token_type': 'Creature',
                     'name': 'Wall', 'power': 0, 'toughness': 4,
                     'colors': {Color.WHITE}, 'subtypes': {'Wall'},
                     'keywords': ['defender']},
            source=obj.id)]
    # engine gap: Class level-up activation and gated triggers
    return [make_etb_trigger(obj, etb_effect)]


def caretakers_talent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever one or more tokens you control enter, draw a card (once per turn)."""
    def token_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering = state.objects.get(event.payload.get('object_id'))
        if not entering:
            return False
        return (entering.controller == source.controller and
                entering.state.is_token)

    def draw_effect(event: Event, state: GameState) -> list[Event]:
        key = f'caretakers_talent_drew_{obj.id}_{state.turn_number}'
        if state.turn_data.get(key):
            return []
        state.turn_data[key] = True
        return [Event(type=EventType.DRAW,
                      payload={'player': obj.controller, 'amount': 1},
                      source=obj.id)]
    # engine gap: Class level 2 / 3 effects
    return [make_etb_trigger(obj, draw_effect, token_etb_filter)]


def carrot_cake_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this artifact enters, create Rabbit token and scry 1."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN,
                  payload={'controller': obj.controller, 'token_type': 'Creature',
                           'name': 'Rabbit', 'power': 1, 'toughness': 1,
                           'colors': {Color.WHITE}, 'subtypes': {'Rabbit'}},
                  source=obj.id),
            Event(type=EventType.SCRY,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id),
        ]
    # engine gap: sacrifice trigger replicating same effect
    return [make_etb_trigger(obj, etb_effect)]


def feather_of_flight_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura ETB: draw a card. Enchanted creature gets +1/+0 and flying."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW,
                      payload={'player': obj.controller, 'amount': 1},
                      source=obj.id)]
    # engine gap: aura attachment-bound P/T and keyword grant
    return [make_etb_trigger(obj, etb_effect)]


def flowerfoot_swordmaster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Valiant — Mice you control get +1/+0 until end of turn."""
    def pump_mice(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for tgt in state.objects.values():
            if (tgt.controller == obj.controller and
                tgt.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in tgt.characteristics.types and
                'Mouse' in tgt.characteristics.subtypes):
                events.append(Event(
                    type=EventType.PUMP,
                    payload={'object_id': tgt.id, 'power': 1, 'toughness': 0,
                             'duration': 'end_of_turn'},
                    source=obj.id))
        return events
    # engine gap: Offspring {2} (cost-based token copy)
    return [make_valiant_trigger(obj, pump_mice)]


def jolly_gerbils_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: "whenever you give a gift" hook
    return []


def mouse_trapper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Valiant — Tap target creature an opponent controls."""
    def tap_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': obj.id,
                'controller': obj.controller,
                'effect': 'tap',
                'effect_params': {},
                'target_filter': 'opponent_creature',
                'min_targets': 1,
                'max_targets': 1,
                'optional': False,
            },
            source=obj.id)]
    return [make_valiant_trigger(obj, tap_effect)]


def nettle_guard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Valiant — It gets +0/+2 until end of turn."""
    def pump_self(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PUMP,
            payload={'object_id': obj.id, 'power': 0, 'toughness': 2,
                     'duration': 'end_of_turn'},
            source=obj.id)]
    # engine gap: sacrifice activated ability ({1}, Sac: Destroy artifact/enchantment)
    return [make_valiant_trigger(obj, pump_self)]


def star_charter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """End step: if life changed, look at top 4 (simplified to scry 4)."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        key_gain = f'life_gained_turn_{state.turn_number}_{obj.controller}'
        key_loss = f'life_lost_turn_{state.turn_number}_{obj.controller}'
        if not (state.turn_data.get(key_gain) or state.turn_data.get(key_loss)):
            return []
        # engine gap: reveal/conditional draw - simplified to scry 4
        return [Event(type=EventType.SCRY,
                      payload={'player': obj.controller, 'amount': 4},
                      source=obj.id)]
    return [make_end_step_trigger(obj, end_step_effect, controller_only=True)]


def warren_elder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: activated +1/+1 anthem ability
    return []


def warren_warleader_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you attack, choose: create tapped Rabbit OR pump attackers."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: modal choice between tapped Rabbit token and attacker pump.
        # Default to creating a 1/1 white Rabbit token.
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={'controller': obj.controller, 'token_type': 'Creature',
                     'name': 'Rabbit', 'power': 1, 'toughness': 1,
                     'colors': {Color.WHITE}, 'subtypes': {'Rabbit'},
                     'tapped': True, 'attacking': True},
            source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]


def waxwane_witness_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Life gain or loss during your turn -> +1/+0 until end of turn."""
    def life_effect(event: Event, state: GameState) -> list[Event]:
        if state.active_player != obj.controller:
            return []
        return [Event(type=EventType.PUMP,
                      payload={'object_id': obj.id, 'power': 1, 'toughness': 0,
                               'duration': 'end_of_turn'},
                      source=obj.id)]
    return [
        make_life_gain_trigger(obj, life_effect, controller_only=True),
        make_life_loss_trigger(obj, life_effect, opponent_only=False),
    ]


def whiskervale_forerunner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Valiant — Look at top 5 (simplified to scry 5)."""
    def scry_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: full reveal-and-conditional-put-onto-bf — simplified to scry 5
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 5},
            source=obj.id)]
    return [make_valiant_trigger(obj, scry_effect)]


# -----------------------------------------------------------------------------
# BLUE CARDS
# -----------------------------------------------------------------------------

def _azure_beastbinder_execute(choice, selected, state: GameState) -> list[Event]:
    """Apply -X/-Y to push creature toward 2/2 (closest engine approximation)."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    # engine gap: full lose-abilities + base-PT-lock; approximate with -1/-1 pump.
    if CardType.CREATURE in target.characteristics.types:
        return [Event(
            type=EventType.PUMP,
            payload={'object_id': target_id, 'power': -1, 'toughness': -1,
                     'duration': 'end_of_turn'},
            source=choice.source_id)]
    return []


def azure_beastbinder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack trigger: target opp creature gets -1/-1 (approx of base-2/2 lock)."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        valid_targets = [
            t.id for t in state.objects.values()
            if t.controller != obj.controller
            and t.zone == ZoneType.BATTLEFIELD
            and (CardType.CREATURE in t.characteristics.types or
                 CardType.ARTIFACT in t.characteristics.types or
                 CardType.PLANESWALKER in t.characteristics.types)
        ]
        if not valid_targets:
            return []
        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose an artifact, creature, or planeswalker",
            min_targets=0,
            max_targets=1,
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = _azure_beastbinder_execute
        return []
    # engine gap: "can't be blocked by power 2+"; full lose-abilities + base-PT-lock
    return [make_attack_trigger(obj, attack_effect)]


def _daring_waverider_execute(choice, selected, state: GameState) -> list[Event]:
    """Cast chosen instant/sorcery from gy without paying mana cost."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.GRAVEYARD:
        return []
    return [Event(
        type=EventType.CAST,
        payload={'object_id': target_id, 'controller': choice.player,
                 'from_graveyard': True, 'without_paying_cost': True,
                 'replace_graveyard_with_exile': True},
        source=choice.source_id)]


def daring_waverider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: may cast instant/sorcery from gy (MV<=4) without paying."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        gy_zone = state.zones.get(f'graveyard_{obj.controller}')
        if not gy_zone:
            return []
        valid_targets = []
        for oid in gy_zone.objects:
            tgt = state.objects.get(oid)
            if not tgt:
                continue
            types = tgt.characteristics.types
            if CardType.INSTANT not in types and CardType.SORCERY not in types:
                continue
            mv = getattr(tgt.characteristics, 'mana_value', None)
            if mv is None:
                mv = 0
            if mv > 4:
                continue
            valid_targets.append(oid)
        if not valid_targets:
            return []
        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose an instant/sorcery card with MV<=4 to cast for free",
            min_targets=0,
            max_targets=1,
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = _daring_waverider_execute
        return []
    return [make_etb_trigger(obj, etb_effect)]


def dour_portmage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another creature you control leaves the battlefield without dying, draw a card."""
    def leave_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        # Without dying = NOT going to graveyard
        if event.payload.get('to_zone_type') == ZoneType.GRAVEYARD:
            return False
        leaving_id = event.payload.get('object_id')
        if leaving_id == source.id:
            return False
        leaving = state.objects.get(leaving_id)
        if not leaving:
            return False
        return (leaving.controller == source.controller and
                CardType.CREATURE in leaving.characteristics.types)

    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW,
                      payload={'player': obj.controller, 'amount': 1},
                      source=obj.id)]

    leave_trigger = Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: leave_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=draw_effect(e, s)),
        duration='while_on_battlefield',
    )
    # engine gap: activated bounce ability
    return [leave_trigger]


def eluge_the_shoreless_sea_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """P/T equal to Islands you control."""
    def is_owner_island(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id

    def power_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_POWER and
                event.payload.get('object_id') == obj.id)

    def toughness_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_TOUGHNESS and
                event.payload.get('object_id') == obj.id)

    def islands_count() -> int:
        return sum(
            1 for o in state.objects.values()
            if o.controller == obj.controller and o.zone == ZoneType.BATTLEFIELD
            and 'Island' in o.characteristics.subtypes
        )

    def pt_handler(event: Event, state: GameState) -> InterceptorResult:
        ne = event.copy()
        count = sum(
            1 for o in state.objects.values()
            if o.controller == obj.controller and o.zone == ZoneType.BATTLEFIELD
            and 'Island' in o.characteristics.subtypes
        )
        ne.payload['value'] = count
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=ne)

    p_int = Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.QUERY,
                        filter=power_filter, handler=pt_handler,
                        duration='while_on_battlefield')
    t_int = Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.QUERY,
                        filter=toughness_filter, handler=pt_handler,
                        duration='while_on_battlefield')
    # engine gap: flood counter creation, type change to Island, cost reduction
    return [p_int, t_int]


def gossips_talent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Class L1: surveil 1 when a creature you control enters."""
    def creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering = state.objects.get(event.payload.get('object_id'))
        if not entering:
            return False
        return (entering.controller == source.controller and
                CardType.CREATURE in entering.characteristics.types)

    def surveil_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SURVEIL,
                      payload={'player': obj.controller, 'amount': 1},
                      source=obj.id)]
    # engine gap: Class level-up activation and L2/L3 effects
    return [make_etb_trigger(obj, surveil_effect, creature_etb_filter)]


def kitnap_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura ETB: tap enchanted creature; if no gift, 3 stun counters; gain control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        attached_id = getattr(obj.state, 'attached_to', None)
        if not attached_id:
            return []
        # engine gap: gift-promised tracking — assume no gift, always stun.
        return [
            Event(type=EventType.TAP,
                  payload={'object_id': attached_id},
                  source=obj.id),
            Event(type=EventType.COUNTER_ADDED,
                  payload={'object_id': attached_id, 'counter_type': 'stun', 'amount': 3},
                  source=obj.id),
            Event(type=EventType.GAIN_CONTROL,
                  payload={'object_id': attached_id, 'new_controller': obj.controller},
                  source=obj.id),
        ]
    return [make_etb_trigger(obj, etb_effect)]


def kitsa_otterball_elite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Prowess: +1/+1 UEOT whenever you cast a noncreature spell."""
    def noncreature_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = event.payload.get('caster') or event.controller
        if caster != source.controller:
            return False
        types = set(event.payload.get('types', []))
        return CardType.CREATURE not in types

    def prowess_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.PUMP,
                      payload={'object_id': obj.id, 'power': 1, 'toughness': 1,
                               'duration': 'end_of_turn'},
                      source=obj.id)]
    # engine gap: activated {T}: loot ability; {2}{T}: copy-spell-with-power-gate
    return [make_spell_cast_trigger(obj, prowess_effect, filter_fn=noncreature_filter)]


def mockingbird_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: enter-as-copy with X mana value cap
    return []


def nightwhorl_hermit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: Threshold-conditional power boost + unblockable
    return []


def shoreline_looter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Unblockable + threshold combat damage trigger."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        # Engine gap: full threshold-conditional discard branch
        return [Event(type=EventType.DRAW,
                      payload={'player': obj.controller, 'amount': 1},
                      source=obj.id)]

    def opponent_combat_dmg_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != source.id:
            return False
        if not event.payload.get('is_combat'):
            return False
        target = event.payload.get('target')
        return target in state.players and target != source.controller

    # engine gap: unblockable static, threshold conditional discard
    return [make_damage_trigger(obj, damage_effect, filter_fn=opponent_combat_dmg_filter)]


def stormchasers_talent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Class enters: create 1/1 blue/red Otter token with prowess."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={'controller': obj.controller, 'token_type': 'Creature',
                     'name': 'Otter', 'power': 1, 'toughness': 1,
                     'colors': {Color.BLUE, Color.RED}, 'subtypes': {'Otter'},
                     'keywords': ['prowess']},
            source=obj.id)]
    # engine gap: Class level-up and L2/L3 effects
    return [make_etb_trigger(obj, etb_effect)]


def sugar_coat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: Aura that overwrites types and abilities of enchanted permanent
    return []


def thought_shucker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: activated {1}{U} ability gated by Threshold (7+ gy) and once-only
    return []


def thundertrap_trainer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: simplified library look (scry 4)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: targeted reveal + selective put-into-hand for noncreature/nonland
        return [Event(type=EventType.SCRY,
                      payload={'player': obj.controller, 'amount': 4},
                      source=obj.id)]
    # engine gap: Offspring
    return [make_etb_trigger(obj, etb_effect)]


def valley_floodcaller_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a noncreature spell, BFOR creatures you control get +1/+1 and untap."""
    def noncreature_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = event.payload.get('caster') or event.controller
        if caster != source.controller:
            return False
        types = set(event.payload.get('types', []))
        return CardType.CREATURE not in types

    def pump_untap(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for target in state.objects.values():
            if (target.controller == obj.controller and
                target.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in target.characteristics.types and
                bool(target.characteristics.subtypes &
                     {"Bird", "Frog", "Otter", "Rat"})):
                events.append(Event(
                    type=EventType.PUMP,
                    payload={'object_id': target.id, 'power': 1, 'toughness': 1,
                             'duration': 'end_of_turn'},
                    source=obj.id))
                if target.state.tapped:
                    events.append(Event(type=EventType.UNTAP,
                                        payload={'object_id': target.id},
                                        source=obj.id))
        return events
    # engine gap: cast-noncreature-as-flash permission
    return [make_spell_cast_trigger(obj, pump_untap, filter_fn=noncreature_filter)]


def waterspout_warden_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack trigger: gain flying if another creature entered this turn."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        key = f'creature_etb_turn_{state.turn_number}_{obj.controller}'
        # Use turn_data to check if any creature entered this turn other than self
        if not state.turn_data.get(key):
            return []
        return [Event(type=EventType.GRANT_KEYWORD,
                      payload={'object_id': obj.id, 'keyword': 'flying',
                               'duration': 'end_of_turn'},
                      source=obj.id)]

    def creature_etb_recorder(event: Event, state: GameState) -> list[Event]:
        if event.type != EventType.ZONE_CHANGE:
            return []
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return []
        entering = state.objects.get(event.payload.get('object_id'))
        if not entering:
            return []
        if (entering.controller == obj.controller and
            CardType.CREATURE in entering.characteristics.types and
            entering.id != obj.id):
            state.turn_data[f'creature_etb_turn_{state.turn_number}_{obj.controller}'] = True
        return []

    record_filter = lambda e, s: e.type == EventType.ZONE_CHANGE
    record_int = Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=record_filter,
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=creature_etb_recorder(e, s)),
        duration='while_on_battlefield')
    return [record_int, make_attack_trigger(obj, attack_effect)]


def wishing_well_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: activated {T}-add-coin-counter ability + conditional gy-cast trigger
    return []


# -----------------------------------------------------------------------------
# BLACK CARDS
# -----------------------------------------------------------------------------

def bandits_talent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Class enters: each opponent discards two cards (simplified)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for pid in state.players:
            if pid != obj.controller:
                events.append(Event(type=EventType.DISCARD,
                                    payload={'player': pid, 'amount': 2},
                                    source=obj.id))
        return events
    # engine gap: Class L2/L3, "unless they discard nonland" choice
    return [make_etb_trigger(obj, etb_effect)]


def bonebind_orator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: activated ability with cost "{3}{B}, exile self from gy" — no
    # generic activated-from-graveyard interceptor exists yet.
    return []


def bonecache_overseer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: activated draw with conditional cost (cards left graveyard, food sacrificed)
    return []


def huskburster_swarm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: cost reduction based on exiled+graveyard creature cards
    return []


def iridescent_vinelasher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Landfall - whenever a land you control enters, deal 1 damage to target opponent."""
    def land_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering = state.objects.get(event.payload.get('object_id'))
        if not entering:
            return False
        return (entering.controller == source.controller and
                CardType.LAND in entering.characteristics.types)

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        for pid in state.players:
            if pid != obj.controller:
                return [Event(type=EventType.DAMAGE,
                              payload={'target': pid, 'amount': 1,
                                       'source': obj.id, 'is_combat': False},
                              source=obj.id)]
        return []
    # engine gap: Offspring
    return [make_etb_trigger(obj, damage_effect, land_etb_filter)]


def maha_its_feathers_night_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creatures opponents control have base toughness 1."""
    def opp_creature_filter(target: GameObject, state: GameState) -> bool:
        return (target.controller != obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)

    def toughness_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        target = state.objects.get(event.payload.get('object_id'))
        if not target:
            return False
        return opp_creature_filter(target, state)

    def toughness_handler(event: Event, state: GameState) -> InterceptorResult:
        ne = event.copy()
        ne.payload['value'] = 1
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=ne)

    # engine gap: Ward—Discard a card
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.QUERY,
                        filter=toughness_filter, handler=toughness_handler,
                        duration='while_on_battlefield')]


def moonstone_harbinger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you gain or lose life, Bats you control get +1/+0 and gain deathtouch (1/turn)."""
    def life_effect(event: Event, state: GameState) -> list[Event]:
        if state.active_player != obj.controller:
            return []
        key = f'moonstone_harbinger_{obj.id}_t{state.turn_number}'
        if state.turn_data.get(key):
            return []
        state.turn_data[key] = True
        events: list[Event] = []
        for target in state.objects.values():
            if (target.controller == obj.controller and
                target.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in target.characteristics.types and
                'Bat' in target.characteristics.subtypes):
                events.append(Event(
                    type=EventType.PUMP,
                    payload={'object_id': target.id, 'power': 1, 'toughness': 0,
                             'duration': 'end_of_turn'},
                    source=obj.id))
                events.append(Event(
                    type=EventType.GRANT_KEYWORD,
                    payload={'object_id': target.id, 'keyword': 'deathtouch',
                             'duration': 'end_of_turn'},
                    source=obj.id))
        return events
    return [
        make_life_gain_trigger(obj, life_effect, controller_only=True),
        make_life_loss_trigger(obj, life_effect, opponent_only=False),
    ]


def osteomancer_adept_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: activated cast-from-graveyard with forage cost and finality counter rider
    return []


def persistent_marshstalker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Power equals 1 for each other Rat you control (continuous)."""
    def power_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_POWER and
                event.payload.get('object_id') == obj.id)

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        count = sum(
            1 for o in state.objects.values()
            if o.id != obj.id and o.controller == obj.controller
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in o.characteristics.types
            and 'Rat' in o.characteristics.subtypes
        )
        ne = event.copy()
        ne.payload['value'] = ne.payload.get('value', 0) + count
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=ne)

    # engine gap: threshold-gated graveyard reanimation on Rat attack
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.QUERY,
                        filter=power_filter, handler=power_handler,
                        duration='while_on_battlefield')]


def ravine_raider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: activated +1/+1 pump ability
    return []


def rottenmouth_viper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB or attack: +blight counter, then drain X*4."""
    def blight_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'blight', 'amount': 1},
            source=obj.id)]
        blight_count = obj.state.counters.get('blight', 0) + 1
        for pid in state.players:
            if pid != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': pid, 'amount': -4 * blight_count},
                    source=obj.id))
        # engine gap: "unless sacrifices/discards" payment choice
        return events

    return [
        make_etb_trigger(obj, blight_effect),
        make_attack_trigger(obj, blight_effect),
    ]


def scavengers_talent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Class L1: when one or more creatures die, create a Food (1/turn)."""
    def death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying = state.objects.get(event.payload.get('object_id'))
        if not dying:
            return False
        return (dying.controller == source.controller and
                CardType.CREATURE in dying.characteristics.types)

    def food_effect(event: Event, state: GameState) -> list[Event]:
        key = f'scavengers_talent_{obj.id}_t{state.turn_number}'
        if state.turn_data.get(key):
            return []
        state.turn_data[key] = True
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={'controller': obj.controller, 'token_type': 'Artifact',
                     'name': 'Food', 'subtypes': {'Food'}},
            source=obj.id)]
    # engine gap: Class L2/L3 effects
    death_int = Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: death_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=food_effect(e, s)),
        duration='while_on_battlefield')
    return [death_int]


def sinister_monolith_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Beginning of combat: each opponent loses 1, you gain 1."""
    def begin_combat_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.PHASE_START, EventType.COMBAT_DECLARED):
            return False
        if event.type == EventType.PHASE_START:
            if event.payload.get('phase') != 'beginning_of_combat':
                return False
        return state.active_player == obj.controller

    def drain_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for pid in state.players:
            if pid != obj.controller:
                events.append(Event(type=EventType.LIFE_CHANGE,
                                    payload={'player': pid, 'amount': -1},
                                    source=obj.id))
        events.append(Event(type=EventType.LIFE_CHANGE,
                            payload={'player': obj.controller, 'amount': 1},
                            source=obj.id))
        return events

    # engine gap: activated draw-2 ability with self-sacrifice
    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=begin_combat_filter,
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=drain_effect(e, s)),
        duration='while_on_battlefield')]


def starlit_soothsayer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """End step: if life changed this turn, surveil 1."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        key_gain = f'life_gained_turn_{state.turn_number}_{obj.controller}'
        key_loss = f'life_lost_turn_{state.turn_number}_{obj.controller}'
        if not (state.turn_data.get(key_gain) or state.turn_data.get(key_loss)):
            return []
        return [Event(type=EventType.SURVEIL,
                      payload={'player': obj.controller, 'amount': 1},
                      source=obj.id)]
    return [make_end_step_trigger(obj, end_step_effect, controller_only=True)]


def thoughtstalker_warlock_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: opponent discards a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        for pid in state.players:
            if pid != obj.controller:
                return [Event(type=EventType.DISCARD,
                              payload={'player': pid, 'amount': 1},
                              source=obj.id)]
        return []
    # engine gap: reveal-and-choose-nonland-card branch when opponent lost life
    return [make_etb_trigger(obj, etb_effect)]


def wicks_patrol_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: mill three, then -X/-X to opponent's creature where X = greatest MV in graveyard."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id)]
        # Find greatest MV in our graveyard
        gy_zone = None
        for zone in state.zones.values():
            if zone.type == ZoneType.GRAVEYARD and zone.owner == obj.controller:
                gy_zone = zone
                break
        max_mv = 0
        if gy_zone:
            for oid in gy_zone.objects:
                go = state.objects.get(oid)
                if not go or not go.card_def:
                    continue
                cost_str = (go.card_def.mana_cost or "").replace("{", "").replace("}", "")
                count = 0
                num = ""
                for ch in cost_str:
                    if ch.isdigit():
                        num += ch
                    else:
                        if num:
                            count += int(num)
                            num = ""
                        if ch.upper() in {'W', 'U', 'B', 'R', 'G', 'C', 'X'}:
                            count += 1 if ch.upper() != 'X' else 0
                if num:
                    count += int(num)
                if count > max_mv:
                    max_mv = count
        if max_mv > 0:
            for tgt in state.objects.values():
                if (tgt.controller != obj.controller and
                    tgt.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in tgt.characteristics.types):
                    events.append(Event(
                        type=EventType.PUMP,
                        payload={'object_id': tgt.id, 'power': -max_mv,
                                 'toughness': -max_mv, 'duration': 'end_of_turn'},
                        source=obj.id))
                    break
        return events
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# RED CARDS
# -----------------------------------------------------------------------------

def artists_talent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Class L1: cast noncreature spell -> may discard, then draw."""
    def noncreature_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = event.payload.get('caster') or event.controller
        if caster != source.controller:
            return False
        types = set(event.payload.get('types', []))
        return CardType.CREATURE not in types

    def loot_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DISCARD,
                  payload={'player': obj.controller, 'amount': 1, 'optional': True},
                  source=obj.id),
            Event(type=EventType.DRAW,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id),
        ]
    # engine gap: Class L2 (cost reduction) and L3 (damage replacement)
    return [make_spell_cast_trigger(obj, loot_effect, filter_fn=noncreature_filter)]


def blacksmiths_talent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Class enters: create Sword equipment token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={'controller': obj.controller, 'token_type': 'Artifact',
                     'name': 'Sword', 'subtypes': {'Equipment'}},
            source=obj.id)]
    # engine gap: Class L2 (begin-combat attach) and L3 (double strike + haste)
    return [make_etb_trigger(obj, etb_effect)]


def brambleguard_captain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Begin of combat: target creature you control gets +X/+0 (X = this creature's power)."""
    def combat_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.PHASE_START, EventType.COMBAT_DECLARED):
            return False
        if event.type == EventType.PHASE_START:
            if event.payload.get('phase') != 'beginning_of_combat':
                return False
        return state.active_player == obj.controller

    def pump_effect(event: Event, state: GameState) -> list[Event]:
        from src.engine import get_power as _gp
        x = _gp(obj, state)
        for tgt in state.objects.values():
            if (tgt.controller == obj.controller and
                tgt.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in tgt.characteristics.types and
                tgt.id != obj.id):
                return [Event(
                    type=EventType.PUMP,
                    payload={'object_id': tgt.id, 'power': x, 'toughness': 0,
                             'duration': 'end_of_turn'},
                    source=obj.id)]
        return []

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_filter,
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=pump_effect(e, s)),
        duration='while_on_battlefield')]


def byway_barterer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Expend 4 — discard hand, draw 2 (simplified to discard 1, draw 2)."""
    def loot_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: "may discard your hand" choice — simplified to discard 1, draw 2
        return [
            Event(type=EventType.DISCARD,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id),
            Event(type=EventType.DRAW,
                  payload={'player': obj.controller, 'amount': 2},
                  source=obj.id),
        ]
    return [make_expend_trigger(obj, 4, loot_effect)]


def dragonhawk_fates_tempest_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB or attack: simplified impulse draw of X (X = creatures with power 4+)."""
    def big_creature_count() -> int:
        from src.engine import get_power as _gp
        return sum(
            1 for o in state.objects.values()
            if o.controller == obj.controller and o.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in o.characteristics.types
            and _gp(o, state) >= 4
        )

    def impulse_effect(event: Event, state: GameState) -> list[Event]:
        x = big_creature_count()
        if x <= 0:
            return []
        # engine gap: delayed end-step damage based on still-exiled count
        return [Event(type=EventType.IMPULSE_DRAW,
                      payload={'player': obj.controller, 'amount': x,
                               'duration': 'next_end_step'},
                      source=obj.id)]
    return [
        make_etb_trigger(obj, impulse_effect),
        make_attack_trigger(obj, impulse_effect),
    ]


def emberheart_challenger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Valiant — Exile top of library; play it UEOT."""
    def impulse_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.IMPULSE_DRAW,
            payload={'player': obj.controller, 'amount': 1,
                     'duration': 'end_of_turn'},
            source=obj.id)]
    # engine gap: prowess static (covered globally where prowess wires elsewhere)
    return [make_valiant_trigger(obj, impulse_effect)]


def festival_of_embers_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """If a card or token would be put into ANY graveyard, exile it instead."""
    # engine gap: gy-cast-with-life-cost permission ("During your turn, you may
    # cast instants/sorceries from gy by paying 1 life"); activated sac ability.
    return [make_graveyard_to_exile_replacer(
        obj, affects_controller=True, affects_opponents=True)]


def flamecache_gecko_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: if an opponent lost life this turn, add {B}{R}."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        any_loss = False
        for pid in state.players:
            if pid == obj.controller:
                continue
            if state.turn_data.get(f'life_lost_turn_{state.turn_number}_{pid}'):
                any_loss = True
                break
        if not any_loss:
            return []
        return [
            Event(type=EventType.ADD_MANA,
                  payload={'player': obj.controller, 'mana': 'B'}, source=obj.id),
            Event(type=EventType.ADD_MANA,
                  payload={'player': obj.controller, 'mana': 'R'}, source=obj.id),
        ]
    # engine gap: activated discard/draw ability
    return [make_etb_trigger(obj, etb_effect)]


def frilled_sparkshooter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: enters with a +1/+1 counter if an opponent lost life this turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        any_loss = False
        for pid in state.players:
            if pid == obj.controller:
                continue
            if state.turn_data.get(f'life_lost_turn_{state.turn_number}_{pid}'):
                any_loss = True
                break
        if not any_loss:
            return []
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                      source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


def harnesser_of_storms_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a noncreature or Otter spell, exile top of library; play UEOT (1/turn)."""
    def cast_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = event.payload.get('caster') or event.controller
        if caster != source.controller:
            return False
        types = set(event.payload.get('types', []))
        subs = set(event.payload.get('subtypes', []))
        return (CardType.CREATURE not in types) or ('Otter' in subs)

    def impulse_effect(event: Event, state: GameState) -> list[Event]:
        key = f'harnesser_storms_{obj.id}_t{state.turn_number}'
        if state.turn_data.get(key):
            return []
        state.turn_data[key] = True
        return [Event(type=EventType.IMPULSE_DRAW,
                      payload={'player': obj.controller, 'amount': 1,
                               'duration': 'end_of_turn'},
                      source=obj.id)]
    return [make_spell_cast_trigger(obj, impulse_effect, filter_fn=cast_filter)]


def aheartfire_hero_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """A-Heartfire Hero: death damage = power; Valiant gap."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        from src.engine import get_power as _gp
        power = _gp(obj, state)
        events: list[Event] = []
        for pid in state.players:
            if pid != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': pid, 'amount': power, 'source': obj.id,
                             'is_combat': False},
                    source=obj.id))
        return events
    # engine gap: Valiant trigger
    return [make_death_trigger(obj, death_effect)]


def hearthborn_battler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a player casts their second spell each turn, deal 2 damage to target opponent."""
    def cast_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = event.payload.get('caster') or event.controller
        if not caster:
            return False
        key = f'hearthborn_count_{state.turn_number}_{caster}'
        prev = state.turn_data.get(key, 0)
        state.turn_data[key] = prev + 1
        return prev + 1 == 2

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        for pid in state.players:
            if pid != obj.controller:
                return [Event(type=EventType.DAMAGE,
                              payload={'target': pid, 'amount': 2,
                                       'source': obj.id, 'is_combat': False},
                              source=obj.id)]
        return []

    return [make_spell_cast_trigger(obj, damage_effect,
                                    controller_only=False,
                                    filter_fn=cast_filter)]


def hired_claw_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you attack with one or more Lizards, deal 1 damage to target opponent."""
    def lizard_attack_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker = state.objects.get(event.payload.get('attacker_id'))
        if not attacker:
            return False
        return (attacker.controller == source.controller and
                'Lizard' in attacker.characteristics.subtypes)

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        for pid in state.players:
            if pid != obj.controller:
                return [Event(type=EventType.DAMAGE,
                              payload={'target': pid, 'amount': 1,
                                       'source': obj.id, 'is_combat': False},
                              source=obj.id)]
        return []
    # engine gap: activated +1/+1 counter ability (conditional on opponent life loss)
    return [make_attack_trigger(obj, damage_effect, lizard_attack_filter)]


def hoarders_overflow_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: put a stash counter on this enchantment."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id, 'counter_type': 'stash', 'amount': 1},
                      source=obj.id)]
    # engine gap: Expend 4; activated discard-hand-then-draw-X
    return [make_etb_trigger(obj, etb_effect)]


def kindlespark_duo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a noncreature spell, untap this creature."""
    def noncreature_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = event.payload.get('caster') or event.controller
        if caster != source.controller:
            return False
        types = set(event.payload.get('types', []))
        return CardType.CREATURE not in types

    def untap_effect(event: Event, state: GameState) -> list[Event]:
        if obj.state.tapped:
            return [Event(type=EventType.UNTAP,
                          payload={'object_id': obj.id},
                          source=obj.id)]
        return []
    # engine gap: tap-for-1-damage ability
    return [make_spell_cast_trigger(obj, untap_effect, filter_fn=noncreature_filter)]


def manifold_mouse_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Begin combat: target Mouse you control gains double strike or trample (default trample)."""
    def combat_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.PHASE_START, EventType.COMBAT_DECLARED):
            return False
        if event.type == EventType.PHASE_START:
            if event.payload.get('phase') != 'beginning_of_combat':
                return False
        return state.active_player == obj.controller

    def grant_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: choice between double strike and trample
        for tgt in state.objects.values():
            if (tgt.controller == obj.controller and
                tgt.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in tgt.characteristics.types and
                'Mouse' in tgt.characteristics.subtypes):
                return [Event(type=EventType.GRANT_KEYWORD,
                              payload={'object_id': tgt.id, 'keyword': 'trample',
                                       'duration': 'end_of_turn'},
                              source=obj.id)]
        return []

    # engine gap: Offspring
    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_filter,
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=grant_effect(e, s)),
        duration='while_on_battlefield')]


def raccoon_rallier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: activated {T} ability with sorcery-speed gate (target gains haste)
    return []


def reptilian_recruiter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: gain control until eot if power<=2 or you control another Lizard (simplified)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        from src.engine import get_power as _gp
        has_other_lizard = any(
            o.id != obj.id and o.controller == obj.controller and
            o.zone == ZoneType.BATTLEFIELD and
            'Lizard' in o.characteristics.subtypes
            for o in state.objects.values()
        )
        for tgt in state.objects.values():
            if (tgt.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in tgt.characteristics.types and
                tgt.id != obj.id):
                if _gp(tgt, state) <= 2 or has_other_lizard:
                    return [
                        Event(type=EventType.GAIN_CONTROL,
                              payload={'object_id': tgt.id,
                                       'new_controller': obj.controller,
                                       'duration': 'end_of_turn'},
                              source=obj.id),
                        Event(type=EventType.UNTAP,
                              payload={'object_id': tgt.id}, source=obj.id),
                        Event(type=EventType.GRANT_KEYWORD,
                              payload={'object_id': tgt.id, 'keyword': 'haste',
                                       'duration': 'end_of_turn'},
                              source=obj.id),
                    ]
        return []
    return [make_etb_trigger(obj, etb_effect)]


def roughshod_duo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Expend 4 — target creature you control gets +1/+1 and gains trample UEOT."""
    def expend_effect(event: Event, state: GameState) -> list[Event]:
        # Pick the first creature you control as default target (greedy).
        for tgt in state.objects.values():
            if (tgt.controller == obj.controller and
                tgt.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in tgt.characteristics.types):
                return [
                    Event(type=EventType.PUMP,
                          payload={'object_id': tgt.id, 'power': 1, 'toughness': 1,
                                   'duration': 'end_of_turn'},
                          source=obj.id),
                    Event(type=EventType.GRANT_KEYWORD,
                          payload={'object_id': tgt.id, 'keyword': 'trample',
                                   'duration': 'end_of_turn'},
                          source=obj.id),
                ]
        return []
    return [make_expend_trigger(obj, 4, expend_effect)]


def stormsplitter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an instant or sorcery, create a copy token of this creature."""
    def is_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = event.payload.get('caster') or event.controller
        if caster != source.controller:
            return False
        types = set(event.payload.get('types', []))
        return bool(types & {CardType.INSTANT, CardType.SORCERY})

    def token_copy(event: Event, state: GameState) -> list[Event]:
        # engine gap: copy-token of arbitrary creature with end-step exile rider
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={'controller': obj.controller, 'token_type': 'Creature',
                     'name': obj.name, 'power': obj.characteristics.power or 1,
                     'toughness': obj.characteristics.toughness or 1,
                     'colors': set(obj.characteristics.colors),
                     'subtypes': set(obj.characteristics.subtypes),
                     'keywords': ['haste'], 'exile_at_end_of_turn': True},
            source=obj.id)]
    return [make_spell_cast_trigger(obj, token_copy, filter_fn=is_filter)]


def sunspine_lynx_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: deal damage to each player equal to nonbasic lands they control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for pid in state.players:
            count = sum(
                1 for o in state.objects.values()
                if o.controller == pid and o.zone == ZoneType.BATTLEFIELD
                and CardType.LAND in o.characteristics.types
                and 'Basic' not in o.characteristics.supertypes
            )
            if count > 0:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': pid, 'amount': count,
                             'source': obj.id, 'is_combat': False},
                    source=obj.id))
        return events
    # engine gap: "players can't gain life", "damage can't be prevented"
    return [make_etb_trigger(obj, etb_effect)]


def teapot_slinger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Expend 4 — Deals 2 damage to each opponent."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for pid in state.players:
            if pid != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': pid, 'amount': 2,
                             'source': obj.id, 'is_combat': False},
                    source=obj.id))
        return events
    return [make_expend_trigger(obj, 4, damage_effect)]


def war_squeak_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura ETB: target creature an opponent controls can't block this turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        for tgt in state.objects.values():
            if (tgt.controller != obj.controller and
                tgt.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in tgt.characteristics.types):
                return [Event(type=EventType.CANT_BLOCK,
                              payload={'object_id': tgt.id, 'duration': 'end_of_turn'},
                              source=obj.id)]
        return []
    # engine gap: Aura attachment-bound +1/+1 and haste grant
    return [make_etb_trigger(obj, etb_effect)]


def whiskerquill_scribe_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Valiant — You may discard a card. If you do, draw a card. (Simplified to loot.)"""
    def loot_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: "may" choice; simplified to unconditional loot
        return [
            Event(type=EventType.DISCARD,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id),
            Event(type=EventType.DRAW,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id),
        ]
    return [make_valiant_trigger(obj, loot_effect)]


# -----------------------------------------------------------------------------
# GREEN CARDS
# -----------------------------------------------------------------------------

def barkknuckle_boxer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Expend 4 — Gains indestructible until end of turn."""
    def indestructible_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': obj.id, 'keyword': 'indestructible',
                     'duration': 'end_of_turn'},
            source=obj.id)]
    return [make_expend_trigger(obj, 4, indestructible_effect)]


def brambleguard_veteran_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Expend 4 — Raccoons you control get +1/+1 and gain vigilance UEOT."""
    def expend_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for tgt in state.objects.values():
            if (tgt.controller == obj.controller and
                tgt.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in tgt.characteristics.types and
                'Raccoon' in tgt.characteristics.subtypes):
                events.append(Event(
                    type=EventType.PUMP,
                    payload={'object_id': tgt.id, 'power': 1, 'toughness': 1,
                             'duration': 'end_of_turn'},
                    source=obj.id))
                events.append(Event(
                    type=EventType.GRANT_KEYWORD,
                    payload={'object_id': tgt.id, 'keyword': 'vigilance',
                             'duration': 'end_of_turn'},
                    source=obj.id))
        return events
    return [make_expend_trigger(obj, 4, expend_effect)]


def bushy_bodyguard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: may forage; if you do, put two +1/+1 counters on it."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: 'may' choice and full forage cost gating — simplified to
        # always attempt forage; if cost can be paid, gain counters.
        from src.engine.blb_mechanics import pay_forage_cost
        if pay_forage_cost(obj.controller, state, source_id=obj.id):
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 2},
                source=obj.id)]
        return []
    # engine gap: Offspring {2} (cost-based token copy)
    return [make_etb_trigger(obj, etb_effect)]


def _curious_forager_execute(choice, selected, state: GameState) -> list[Event]:
    """Return chosen permanent card from graveyard to hand."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.GRAVEYARD:
        return []
    return [Event(
        type=EventType.RETURN_FROM_GRAVEYARD,
        payload={'object_id': target_id, 'controller': choice.player,
                 'destination': 'hand'},
        source=choice.source_id)]


def curious_forager_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: may forage. When you do, return target permanent card from gy to hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: 'may' choice — simplified to always attempt forage.
        from src.engine.blb_mechanics import pay_forage_cost
        if not pay_forage_cost(obj.controller, state, source_id=obj.id):
            return []
        gy_zone = state.zones.get(f'graveyard_{obj.controller}')
        if not gy_zone:
            return []
        permanent_types = {CardType.CREATURE, CardType.ARTIFACT,
                           CardType.ENCHANTMENT, CardType.LAND,
                           CardType.PLANESWALKER}
        valid_targets = []
        for oid in gy_zone.objects:
            tgt = state.objects.get(oid)
            if tgt and tgt.characteristics.types & permanent_types:
                valid_targets.append(oid)
        if not valid_targets:
            return []
        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a permanent card to return to your hand",
            min_targets=1,
            max_targets=1,
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = _curious_forager_execute
        return []
    return [make_etb_trigger(obj, etb_effect)]


def druid_of_the_spade_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """As long as you control a token, this creature gets +2/+0 and has trample."""
    def has_token() -> bool:
        return any(
            o.controller == obj.controller and o.zone == ZoneType.BATTLEFIELD
            and o.state.is_token
            for o in state.objects.values()
        )

    def power_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        return has_token()

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        ne = event.copy()
        ne.payload['value'] = ne.payload.get('value', 0) + 2
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=ne)

    def ability_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        return has_token()

    def ability_handler(event: Event, state: GameState) -> InterceptorResult:
        ne = event.copy()
        granted = list(ne.payload.get('granted', []))
        if 'trample' not in granted:
            granted.append('trample')
        ne.payload['granted'] = granted
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=ne)

    return [
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY,
                    filter=power_filter, handler=power_handler,
                    duration='while_on_battlefield'),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY,
                    filter=ability_filter, handler=ability_handler,
                    duration='while_on_battlefield'),
    ]


def fecund_greenshell_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB or other-creature ETB with toughness>power: scry-like top-card check (simplified)."""
    def etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering = state.objects.get(event.payload.get('object_id'))
        if not entering:
            return False
        if entering.controller != source.controller:
            return False
        if CardType.CREATURE not in entering.characteristics.types:
            return False
        if entering.id == source.id:
            return True
        p = entering.characteristics.power or 0
        t = entering.characteristics.toughness or 0
        return t > p

    def reveal_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: top-card type check + put-onto-battlefield branch
        return [Event(type=EventType.SCRY,
                      payload={'player': obj.controller, 'amount': 1},
                      source=obj.id)]

    # engine gap: 10-land anthem (+2/+2)
    return [make_etb_trigger(obj, reveal_effect, etb_filter)]


def hazardroot_herbalist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you attack, target creature you control gets +1/+0 (deathtouch if token)."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        for tgt in state.objects.values():
            if (tgt.controller == obj.controller and
                tgt.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in tgt.characteristics.types):
                events: list[Event] = [Event(
                    type=EventType.PUMP,
                    payload={'object_id': tgt.id, 'power': 1, 'toughness': 0,
                             'duration': 'end_of_turn'},
                    source=obj.id)]
                if tgt.state.is_token:
                    events.append(Event(
                        type=EventType.GRANT_KEYWORD,
                        payload={'object_id': tgt.id, 'keyword': 'deathtouch',
                                 'duration': 'end_of_turn'},
                        source=obj.id))
                return events
        return []
    return [make_attack_trigger(obj, attack_effect)]


def heaped_harvest_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Artifact ETB: search for basic land, put onto battlefield tapped."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: search-and-fetch-basic + sacrifice retrigger
        return [Event(type=EventType.SEARCH_LIBRARY,
                      payload={'player': obj.controller, 'card_type': CardType.LAND,
                               'basic_only': True, 'destination': 'battlefield_tapped'},
                      source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


def hunters_talent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Class enters: bite (target creature you control deals damage to opponent's creature)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: targeted fight-style damage
        return []
    # engine gap: Class L2 (attack pump w/ trample) and L3 (end-step draw)
    return [make_etb_trigger(obj, etb_effect)]


def innkeepers_talent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Class L1: begin combat, put +1/+1 counter on target creature you control."""
    def combat_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.PHASE_START, EventType.COMBAT_DECLARED):
            return False
        if event.type == EventType.PHASE_START:
            if event.payload.get('phase') != 'beginning_of_combat':
                return False
        return state.active_player == obj.controller

    def counter_effect(event: Event, state: GameState) -> list[Event]:
        for tgt in state.objects.values():
            if (tgt.controller == obj.controller and
                tgt.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in tgt.characteristics.types):
                return [Event(type=EventType.COUNTER_ADDED,
                              payload={'object_id': tgt.id,
                                       'counter_type': '+1/+1', 'amount': 1},
                              source=obj.id)]
        return []
    # engine gap: Class L2 (ward 1 on counter-having permanents) and L3 (counter doubling)
    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_filter,
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=counter_effect(e, s)),
        duration='while_on_battlefield')]


def keeneyed_curator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: "exiled with this creature" provenance tracking + 4-type
    # threshold static buff; activated {1}: exile-from-graveyard ability.
    return []


def lumra_bellow_of_the_woods_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: mill 4, then return all land cards from graveyard to battlefield tapped."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = [Event(type=EventType.MILL,
                                     payload={'player': obj.controller, 'amount': 4},
                                     source=obj.id)]
        # Find lands in our graveyard
        gy_zone = None
        for zone in state.zones.values():
            if zone.type == ZoneType.GRAVEYARD and zone.owner == obj.controller:
                gy_zone = zone
                break
        if gy_zone:
            for oid in list(gy_zone.objects):
                go = state.objects.get(oid)
                if go and CardType.LAND in go.characteristics.types:
                    events.append(Event(
                        type=EventType.RETURN_FROM_GRAVEYARD,
                        payload={'object_id': oid, 'controller': obj.controller,
                                 'tapped': True},
                        source=obj.id))
        return events

    # P/T equal to lands you control
    def power_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_POWER and
                event.payload.get('object_id') == obj.id)

    def toughness_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_TOUGHNESS and
                event.payload.get('object_id') == obj.id)

    def pt_handler(event: Event, state: GameState) -> InterceptorResult:
        ne = event.copy()
        count = sum(
            1 for o in state.objects.values()
            if o.controller == obj.controller and o.zone == ZoneType.BATTLEFIELD
            and CardType.LAND in o.characteristics.types
        )
        ne.payload['value'] = count
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=ne)

    return [
        make_etb_trigger(obj, etb_effect),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY,
                    filter=power_filter, handler=pt_handler,
                    duration='while_on_battlefield'),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY,
                    filter=toughness_filter, handler=pt_handler,
                    duration='while_on_battlefield'),
    ]


def mistbreath_elder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Upkeep: bounce another creature, put +1/+1 counter on this; otherwise bounce self."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: choose-and-bounce-another with +1/+1 reward, otherwise self-bounce
        for tgt in state.objects.values():
            if (tgt.controller == obj.controller and
                tgt.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in tgt.characteristics.types and
                tgt.id != obj.id):
                return [
                    Event(type=EventType.BOUNCE,
                          payload={'object_id': tgt.id}, source=obj.id),
                    Event(type=EventType.COUNTER_ADDED,
                          payload={'object_id': obj.id,
                                   'counter_type': '+1/+1', 'amount': 1},
                          source=obj.id),
                ]
        return []
    return [make_upkeep_trigger(obj, upkeep_effect, controller_only=True)]


def pawpatch_recruit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When a creature you control is targeted by an opponent, +1/+1 counter on another."""
    def opponent_target_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.TARGET_REQUIRED and event.type != EventType.CAST:
            return False
        # engine gap: opponent-targets-your-creature event detection
        return False

    def counter_effect(event: Event, state: GameState) -> list[Event]:
        return []
    # engine gap: Offspring + opponent-targets-your-creature trigger
    return []


def rustshield_rampager_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: Offspring + power<=2 unblockability
    return []


def scrapshooter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: destroy target artifact/enchantment if gift was promised (simplified to always)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: gift promise tracking - simplified to always destroy
        for tgt in state.objects.values():
            if (tgt.controller != obj.controller and
                tgt.zone == ZoneType.BATTLEFIELD and
                (CardType.ARTIFACT in tgt.characteristics.types or
                 CardType.ENCHANTMENT in tgt.characteristics.types)):
                return [Event(type=EventType.DESTROY,
                              payload={'object_id': tgt.id},
                              source=obj.id)]
        return []
    return [make_etb_trigger(obj, etb_effect)]


def stocking_the_pantry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When +1/+1 counter is added to a creature you control, put a supply counter on this."""
    def counter_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.COUNTER_ADDED:
            return False
        if event.payload.get('counter_type') != '+1/+1':
            return False
        target = state.objects.get(event.payload.get('object_id'))
        if not target:
            return False
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types)

    def supply_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id, 'counter_type': 'supply', 'amount': 1},
                      source=obj.id)]
    # engine gap: activated remove-counter-to-draw ability
    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=counter_filter,
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=supply_effect(e, s)),
        duration='while_on_battlefield')]


def tender_wildguide_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: activated mana ability + activated +1/+1 counter; Offspring {2}
    return []


def thornvault_forager_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: activated mana abilities (incl. forage cost) and tutor ability
    return []


def three_tree_rootweaver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: activated any-color mana ability
    return []


def three_tree_scribe_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When a creature you control leaves bf without dying, put +1/+1 counter on target creature."""
    def leave_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') == ZoneType.GRAVEYARD:
            return False
        leaving = state.objects.get(event.payload.get('object_id'))
        if not leaving:
            return False
        return (leaving.controller == source.controller and
                CardType.CREATURE in leaving.characteristics.types)

    def counter_effect(event: Event, state: GameState) -> list[Event]:
        for tgt in state.objects.values():
            if (tgt.controller == obj.controller and
                tgt.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in tgt.characteristics.types):
                return [Event(type=EventType.COUNTER_ADDED,
                              payload={'object_id': tgt.id,
                                       'counter_type': '+1/+1', 'amount': 1},
                              source=obj.id)]
        return []

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: leave_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=counter_effect(e, s)),
        duration='while_on_battlefield')]


def treetop_sentries_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: forage to draw a card (simplified)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: Forage cost gating
        return [Event(type=EventType.DRAW,
                      payload={'player': obj.controller, 'amount': 1},
                      source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


# -----------------------------------------------------------------------------
# MULTICOLOR / GOLD CARDS
# -----------------------------------------------------------------------------

def alania_divergent_storm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trigger when first instant/sorcery/Otter spell of turn is cast."""
    def cast_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = event.payload.get('caster') or event.controller
        if caster != source.controller:
            return False
        types = set(event.payload.get('types', []))
        subs = set(event.payload.get('subtypes', []))
        is_instant = CardType.INSTANT in types
        is_sorcery = CardType.SORCERY in types
        is_otter = 'Otter' in subs and CardType.CREATURE in types
        if not (is_instant or is_sorcery or is_otter):
            return False
        # Track first-of-each-type per turn
        key = None
        if is_instant:
            key = f'alania_first_instant_{state.turn_number}_{source.controller}'
        elif is_sorcery:
            key = f'alania_first_sorcery_{state.turn_number}_{source.controller}'
        elif is_otter:
            key = f'alania_first_otter_{state.turn_number}_{source.controller}'
        if not key or state.turn_data.get(key):
            return False
        state.turn_data[key] = True
        return True

    def copy_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: opponent-draw + spell copy with new targets
        for pid in state.players:
            if pid != obj.controller:
                return [Event(type=EventType.DRAW,
                              payload={'player': pid, 'amount': 1},
                              source=obj.id)]
        return []

    return [make_spell_cast_trigger(obj, copy_effect, filter_fn=cast_filter)]


def baylen_the_haymaker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: three activated abilities with "tap N untapped tokens you control"
    # as their cost — no token-tap-cost framework exists yet.
    return []


def burrowguard_mentor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """P/T equal to creatures you control."""
    def power_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_POWER and
                event.payload.get('object_id') == obj.id)

    def toughness_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.QUERY_TOUGHNESS and
                event.payload.get('object_id') == obj.id)

    def pt_handler(event: Event, state: GameState) -> InterceptorResult:
        ne = event.copy()
        count = sum(
            1 for o in state.objects.values()
            if o.controller == obj.controller and o.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in o.characteristics.types
        )
        ne.payload['value'] = count
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=ne)

    return [
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY,
                    filter=power_filter, handler=pt_handler,
                    duration='while_on_battlefield'),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.QUERY,
                    filter=toughness_filter, handler=pt_handler,
                    duration='while_on_battlefield'),
    ]


def cindering_cutthroat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: enters with +1/+1 counter if opp lost life this turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        any_loss = False
        for pid in state.players:
            if pid == obj.controller:
                continue
            if state.turn_data.get(f'life_lost_turn_{state.turn_number}_{pid}'):
                any_loss = True
                break
        if not any_loss:
            return []
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id,
                               'counter_type': '+1/+1', 'amount': 1},
                      source=obj.id)]
    # engine gap: activated menace ability
    return [make_etb_trigger(obj, etb_effect)]


def clement_the_worrywort_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this or another creature you control enters, bounce target with lesser MV."""
    def creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering = state.objects.get(event.payload.get('object_id'))
        if not entering:
            return False
        return (entering.controller == source.controller and
                CardType.CREATURE in entering.characteristics.types)

    def bounce_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: targeted-with-lesser-MV bounce
        return []
    # engine gap: Frog mana ability grant
    return [make_etb_trigger(obj, bounce_effect, creature_etb_filter)]


def corpseberry_cultivator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Begin combat: may forage. Whenever you forage, +1/+1 counter on this."""
    def combat_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.PHASE_START, EventType.COMBAT_DECLARED):
            return False
        if event.type == EventType.PHASE_START:
            if event.payload.get('phase') != 'beginning_of_combat':
                return False
        return state.active_player == obj.controller

    def begin_combat_forage(event: Event, state: GameState) -> list[Event]:
        # engine gap: 'may' choice; simplified to always attempt forage.
        from src.engine.blb_mechanics import pay_forage_cost
        pay_forage_cost(obj.controller, state, source_id=obj.id)
        return []

    def counter_on_forage(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id)]

    return [
        Interceptor(
            id=new_id(), source=obj.id, controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=combat_filter,
            handler=lambda e, s: InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=begin_combat_forage(e, s)),
            duration='while_on_battlefield'),
        make_forage_trigger(obj, counter_on_forage),
    ]


def fireglass_mentor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Beginning of second main phase: if opp lost life, exile top 2, choose 1 playable."""
    def main2_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') not in ('main2', 'postcombat_main', 'second_main'):
            return False
        return state.active_player == obj.controller

    def impulse_effect(event: Event, state: GameState) -> list[Event]:
        any_loss = False
        for pid in state.players:
            if pid == obj.controller:
                continue
            if state.turn_data.get(f'life_lost_turn_{state.turn_number}_{pid}'):
                any_loss = True
                break
        if not any_loss:
            return []
        # engine gap: pick-one of two impulse-drawn cards
        return [Event(type=EventType.IMPULSE_DRAW,
                      payload={'player': obj.controller, 'amount': 1,
                               'duration': 'end_of_turn'},
                      source=obj.id)]

    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=main2_filter,
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=impulse_effect(e, s)),
        duration='while_on_battlefield')]


def glarb_calamitys_augur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: top-of-library reveal/play permission and surveil-2 activated ability
    return []


def helga_skittish_seer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast creature spell with MV>=4: draw, gain 1, +1/+1 counter."""
    def cast_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = event.payload.get('caster') or event.controller
        if caster != source.controller:
            return False
        types = set(event.payload.get('types', []))
        if CardType.CREATURE not in types:
            return False
        return event.payload.get('mana_value', 0) >= 4

    def reward_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id),
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id),
            Event(type=EventType.COUNTER_ADDED,
                  payload={'object_id': obj.id,
                           'counter_type': '+1/+1', 'amount': 1},
                  source=obj.id),
        ]
    # engine gap: tap-add-X-mana ability
    return [make_spell_cast_trigger(obj, reward_effect, filter_fn=cast_filter)]


def hugs_grisly_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: exile top X cards (X = mana value 6 simplified), play until next turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.IMPULSE_DRAW,
                      payload={'player': obj.controller, 'amount': 6,
                               'duration': 'next_end_step'},
                      source=obj.id)]
    # engine gap: extra land per turn permission
    return [make_etb_trigger(obj, etb_effect)]


def the_infamous_cruelclaw_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player: exile top until nonland, may cast for discard cost."""
    def combat_dmg_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != source.id:
            return False
        if not event.payload.get('is_combat'):
            return False
        target = event.payload.get('target')
        return target in state.players

    def impulse_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: exile-until-nonland + cast-by-discarding
        return [Event(type=EventType.IMPULSE_DRAW,
                      payload={'player': obj.controller, 'amount': 1,
                               'duration': 'end_of_turn'},
                      source=obj.id)]
    return [make_damage_trigger(obj, impulse_effect, filter_fn=combat_dmg_filter)]


def junkblade_bruiser_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Expend 4 — This creature gets +2/+1 UEOT."""
    def pump_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PUMP,
            payload={'object_id': obj.id, 'power': 2, 'toughness': 1,
                     'duration': 'end_of_turn'},
            source=obj.id)]
    return [make_expend_trigger(obj, 4, pump_effect)]


def kastral_the_windcrested_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever Birds you control deal combat damage to player, choose one (default: draw a card)."""
    def bird_combat_dmg_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('is_combat'):
            return False
        target = event.payload.get('target')
        if target not in state.players:
            return False
        src_obj = state.objects.get(event.payload.get('source'))
        if not src_obj:
            return False
        return (src_obj.controller == source.controller and
                'Bird' in src_obj.characteristics.subtypes)

    def reward_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: modal choice
        return [Event(type=EventType.DRAW,
                      payload={'player': obj.controller, 'amount': 1},
                      source=obj.id)]
    return [make_damage_trigger(obj, reward_effect, filter_fn=bird_combat_dmg_filter)]


def lilysplash_mentor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: activated {1}{G}{U} sorcery-speed flicker-with-+1/+1 ability
    return []


def lunar_convocation_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """End step: if you gained life this turn, each opp loses 1. If gained AND lost, create Bat."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        gained = state.turn_data.get(f'life_gained_turn_{state.turn_number}_{obj.controller}')
        lost = state.turn_data.get(f'life_lost_turn_{state.turn_number}_{obj.controller}')
        if gained:
            for pid in state.players:
                if pid != obj.controller:
                    events.append(Event(type=EventType.LIFE_CHANGE,
                                        payload={'player': pid, 'amount': -1},
                                        source=obj.id))
        if gained and lost:
            events.append(Event(
                type=EventType.CREATE_TOKEN,
                payload={'controller': obj.controller, 'token_type': 'Creature',
                         'name': 'Bat', 'power': 1, 'toughness': 1,
                         'colors': {Color.BLACK}, 'subtypes': {'Bat'},
                         'keywords': ['flying']},
                source=obj.id))
        return events
    # engine gap: activated pay-life-to-draw ability
    return [make_end_step_trigger(obj, end_step_effect, controller_only=True)]


def mind_drill_assailant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Threshold: +3/+0 if 7+ cards in graveyard."""
    def power_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        gy_zone = None
        for zone in state.zones.values():
            if zone.type == ZoneType.GRAVEYARD and zone.owner == obj.controller:
                gy_zone = zone
                break
        if not gy_zone:
            return False
        return len(gy_zone.objects) >= 7

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        ne = event.copy()
        ne.payload['value'] = ne.payload.get('value', 0) + 3
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=ne)

    # engine gap: activated surveil-1 ability
    return [Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                        priority=InterceptorPriority.QUERY,
                        filter=power_filter, handler=power_handler,
                        duration='while_on_battlefield')]


def muerra_trash_tactician_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Beginning of first main phase: add R or G per Raccoon (simplified to 1 R)."""
    def main1_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') not in ('main1', 'precombat_main', 'first_main'):
            return False
        return state.active_player == obj.controller

    def mana_effect(event: Event, state: GameState) -> list[Event]:
        count = sum(
            1 for o in state.objects.values()
            if o.controller == obj.controller and o.zone == ZoneType.BATTLEFIELD
            and 'Raccoon' in o.characteristics.subtypes
        )
        events: list[Event] = []
        for _ in range(count):
            events.append(Event(type=EventType.ADD_MANA,
                                payload={'player': obj.controller, 'mana': 'R'},
                                source=obj.id))
        return events
    # engine gap: Expend 4 / Expend 8 triggers
    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=main1_filter,
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=mana_effect(e, s)),
        duration='while_on_battlefield')]


def ral_crackling_wit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a noncreature spell, put a loyalty counter on Ral."""
    def noncreature_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = event.payload.get('caster') or event.controller
        if caster != source.controller:
            return False
        types = set(event.payload.get('types', []))
        return CardType.CREATURE not in types

    def loyalty_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id,
                               'counter_type': 'loyalty', 'amount': 1},
                      source=obj.id)]
    # engine gap: planeswalker loyalty abilities
    return [make_spell_cast_trigger(obj, loyalty_effect, filter_fn=noncreature_filter)]


def seedglaive_mentor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Valiant — Put a +1/+1 counter on it."""
    def counter_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id)]
    return [make_valiant_trigger(obj, counter_effect)]


def tidecaller_mentor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Threshold ETB: bounce nonland permanent if 7+ cards in graveyard."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        gy_zone = None
        for zone in state.zones.values():
            if zone.type == ZoneType.GRAVEYARD and zone.owner == obj.controller:
                gy_zone = zone
                break
        if not gy_zone or len(gy_zone.objects) < 7:
            return []
        for tgt in state.objects.values():
            if (tgt.zone == ZoneType.BATTLEFIELD and
                CardType.LAND not in tgt.characteristics.types):
                return [Event(type=EventType.BOUNCE,
                              payload={'object_id': tgt.id},
                              source=obj.id)]
        return []
    return [make_etb_trigger(obj, etb_effect)]


def veteran_guardmouse_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Valiant — +1/+0 and gains first strike UEOT. Scry 1."""
    def valiant_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.PUMP,
                  payload={'object_id': obj.id, 'power': 1, 'toughness': 0,
                           'duration': 'end_of_turn'},
                  source=obj.id),
            Event(type=EventType.GRANT_KEYWORD,
                  payload={'object_id': obj.id, 'keyword': 'first_strike',
                           'duration': 'end_of_turn'},
                  source=obj.id),
            Event(type=EventType.SCRY,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id),
        ]
    return [make_valiant_trigger(obj, valiant_effect)]


def vren_the_relentless_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """End step: create X 1/1 Rats based on opponents' creatures exiled this turn."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        x = state.turn_data.get(f'vren_exiled_count_{state.turn_number}', 0)
        if x <= 0:
            return []
        events: list[Event] = []
        for _ in range(x):
            events.append(Event(
                type=EventType.CREATE_TOKEN,
                payload={'controller': obj.controller, 'token_type': 'Creature',
                         'name': 'Rat', 'power': 1, 'toughness': 1,
                         'colors': {Color.BLACK}, 'subtypes': {'Rat'}},
                source=obj.id))
        return events

    def opp_creature_death_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        target = state.objects.get(event.payload.get('object_id'))
        if not target:
            return False
        return (target.controller != obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)

    def replace_with_exile(event: Event, state: GameState) -> InterceptorResult:
        # Track exile and convert destroy to exile
        state.turn_data[f'vren_exiled_count_{state.turn_number}'] = (
            state.turn_data.get(f'vren_exiled_count_{state.turn_number}', 0) + 1
        )
        new_event = Event(
            type=EventType.EXILE,
            payload=dict(event.payload),
            source=event.source,
            controller=event.controller)
        return InterceptorResult(
            action=InterceptorAction.REPLACE,
            new_events=[new_event])

    # engine gap: Ward 2; full die->exile replacement on opponents' creatures
    return [
        make_end_step_trigger(obj, end_step_effect, controller_only=False),
        Interceptor(id=new_id(), source=obj.id, controller=obj.controller,
                    priority=InterceptorPriority.PREVENT,
                    filter=opp_creature_death_filter,
                    handler=replace_with_exile,
                    duration='while_on_battlefield'),
    ]


def wandertale_mentor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Expend 4 — Put a +1/+1 counter on this creature."""
    def counter_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id)]
    # engine gap: activated mana ability ({T}: Add {R} or {G})
    return [make_expend_trigger(obj, 4, counter_effect)]


def ygra_eater_of_all_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a Food is put into a graveyard from the battlefield, +2 +1/+1 counters on Ygra."""
    def food_die_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        target = state.objects.get(event.payload.get('object_id'))
        if not target:
            return False
        return 'Food' in target.characteristics.subtypes

    def counter_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': obj.id,
                               'counter_type': '+1/+1', 'amount': 2},
                      source=obj.id)]

    # engine gap: Ward (sacrifice food); making other creatures Food artifacts
    return [Interceptor(
        id=new_id(), source=obj.id, controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=food_die_filter,
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=counter_effect(e, s)),
        duration='while_on_battlefield')]


# -----------------------------------------------------------------------------
# ARTIFACTS / EQUIPMENT
# -----------------------------------------------------------------------------

def barkform_harvester_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: Changeling (every creature type); activated {2} bottom-of-library
    return []


def bumbleflowers_sharepot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Artifact ETB: create Food token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={'controller': obj.controller, 'token_type': 'Artifact',
                     'name': 'Food', 'subtypes': {'Food'}},
            source=obj.id)]
    # engine gap: activated destroy-permanent ability
    return [make_etb_trigger(obj, etb_effect)]


def fountainport_bell_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Artifact ETB: search library for basic land, reveal, top of library (simplified)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: search-and-reveal-then-top
        return [Event(type=EventType.SEARCH_LIBRARY,
                      payload={'player': obj.controller, 'card_type': CardType.LAND,
                               'basic_only': True, 'destination': 'library_top'},
                      source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]


def heirloom_epic_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: activated ability with creature-tap mana substitution
    return []


def short_bow_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: Equipment attachment-bound +1/+1 / vigilance / reach + Equip {1}
    return []


def starforged_sword_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: if gift was promised, attach to target creature you control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: gift-conditional auto-attach
        return []
    return [make_etb_trigger(obj, etb_effect)]


def tangle_tumbler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: Vehicle (tap-tokens-to-crew); activated {3}{T} counter ability
    return []


def three_tree_mascot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: Changeling and activated any-color mana ability
    return []


# -----------------------------------------------------------------------------
# LANDS
# -----------------------------------------------------------------------------

def fabled_passage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: tap-and-sacrifice search; conditional untap based on land count
    return []


def fountainport_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: multiple activated abilities (mana, draw, token, treasure)
    return []


def hidden_grotto_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: surveil 1."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SURVEIL,
                      payload={'player': obj.controller, 'amount': 1},
                      source=obj.id)]
    # engine gap: any-color mana ability
    return [make_etb_trigger(obj, etb_effect)]


def lilypad_village_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: restricted-mana abilities and conditional surveil activation
    return []


def lupinflower_village_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: restricted mana, sacrifice tutor for tribal creatures
    return []


def mudflat_village_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: restricted mana ability ({B} for creature spells); activated
    # {1}{B}{T}-Sac for tribal-gy-to-hand (Bat/Lizard/Rat/Squirrel)
    return []


def oakhollow_village_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: restricted mana, conditional +1/+1 counter activation
    return []


def rockface_village_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: restricted mana ability; activated {R}{T} sorcery-speed tribal
    # pump (Lizard/Mouse/Otter/Raccoon: +1/+0 + haste UEOT)
    return []


def three_tree_city_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: chosen-creature-type tracking; X-mana production
    return []


def uncharted_haven_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: chosen-color tracking; conditional mana ability
    return []


# -----------------------------------------------------------------------------
# COMMANDER / EXTRA SET CARDS
# -----------------------------------------------------------------------------

def byrke_long_ear_of_the_law_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: put +1/+1 on up to two creatures. Attack: double counters."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        count = 0
        for tgt in state.objects.values():
            if count >= 2:
                break
            if (tgt.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in tgt.characteristics.types):
                events.append(Event(type=EventType.COUNTER_ADDED,
                                    payload={'object_id': tgt.id,
                                             'counter_type': '+1/+1', 'amount': 1},
                                    source=obj.id))
                count += 1
        return events

    def counter_attack_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker = state.objects.get(event.payload.get('attacker_id'))
        if not attacker:
            return False
        if attacker.controller != source.controller:
            return False
        return attacker.state.counters.get('+1/+1', 0) > 0

    def double_effect(event: Event, state: GameState) -> list[Event]:
        attacker = state.objects.get(event.payload.get('attacker_id'))
        if not attacker:
            return []
        current = attacker.state.counters.get('+1/+1', 0)
        if current <= 0:
            return []
        return [Event(type=EventType.COUNTER_ADDED,
                      payload={'object_id': attacker.id,
                               'counter_type': '+1/+1', 'amount': current},
                      source=obj.id)]

    return [
        make_etb_trigger(obj, etb_effect),
        make_attack_trigger(obj, double_effect,
                            filter_fn=counter_attack_filter),
    ]


def charmed_sleep_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura ETB: tap enchanted creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        attached = obj.state.attached_to
        if not attached:
            return []
        return [Event(type=EventType.TAP,
                      payload={'object_id': attached},
                      source=obj.id)]
    # engine gap: doesn't-untap restriction
    return [make_etb_trigger(obj, etb_effect)]


def colossification_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura ETB: tap enchanted creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        attached = obj.state.attached_to
        if not attached:
            return []
        return [Event(type=EventType.TAP,
                      payload={'object_id': attached},
                      source=obj.id)]
    # engine gap: aura attachment-bound +20/+20
    return [make_etb_trigger(obj, etb_effect)]


def sword_of_vengeance_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # engine gap: equipment static (+2/+0, first strike, vigilance, trample, haste); equip cost
    return []


def blossoming_sands_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: gain 1 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': obj.controller, 'amount': 1},
                      source=obj.id)]
    # engine gap: dual-color mana ability
    return [make_etb_trigger(obj, etb_effect)]


def swiftwater_cliffs_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: gain 1 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': obj.controller, 'amount': 1},
                      source=obj.id)]
    # engine gap: dual-color mana ability
    return [make_etb_trigger(obj, etb_effect)]


# =============================================================================
# SPELL RESOLVE FUNCTIONS
# =============================================================================

def _pawpatch_formation_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Pawpatch Formation after target selection - buff +X/+X based on creature count."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    # Target must be a creature on the battlefield
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []  # Target no longer valid

    # Count creatures the caster controls
    creature_count = sum(
        1 for obj in state.objects.values()
        if (obj.controller == choice.player and
            obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types)
    )

    return [
        Event(
            type=EventType.PUMP,
            payload={
                'object_id': target_id,
                'power': creature_count,
                'toughness': creature_count,
                'duration': 'end_of_turn'
            },
            source=choice.source_id
        )
    ]


# -----------------------------------------------------------------------------
# Helper to find spell on stack and get caster info
# -----------------------------------------------------------------------------
def _get_spell_info(state: GameState, spell_name: str) -> tuple[str, str]:
    """Find a spell on the stack by name and return (caster_id, spell_id)."""
    stack_zone = state.zones.get('stack')
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == spell_name:
                return (obj.controller, obj.id)
    return (state.active_player, f"{spell_name.lower().replace(' ', '_')}_spell")


# =============================================================================
# REMOVAL SPELL RESOLVE FUNCTIONS
# =============================================================================

def _fell_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Fell: Destroy target creature."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.DESTROY,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def fell_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Fell: Destroy target creature."""
    caster_id, spell_id = _get_spell_info(state, "Fell")

    # Find valid targets: any creature on battlefield
    valid_targets = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types)
    ]

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to destroy",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _fell_execute

    return []


def _feed_the_cycle_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Feed the Cycle: Destroy target creature or planeswalker."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.DESTROY,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def feed_the_cycle_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Feed the Cycle: Destroy target creature or planeswalker."""
    caster_id, spell_id = _get_spell_info(state, "Feed the Cycle")

    valid_targets = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            (CardType.CREATURE in obj.characteristics.types or
             CardType.PLANESWALKER in obj.characteristics.types))
    ]

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature or planeswalker to destroy",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _feed_the_cycle_execute

    return []


def _repel_calamity_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Repel Calamity: Destroy target creature with power or toughness 4+."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.DESTROY,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def repel_calamity_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Repel Calamity: Destroy target creature with power or toughness 4 or greater."""
    caster_id, spell_id = _get_spell_info(state, "Repel Calamity")

    valid_targets = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types and
            (get_power(obj, state) >= 4 or get_toughness(obj, state) >= 4))
    ]

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature with power or toughness 4+ to destroy",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _repel_calamity_execute

    return []


def _nocturnal_hunger_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Nocturnal Hunger: Destroy target creature, lose 2 life if no gift."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    events = [Event(
        type=EventType.DESTROY,
        payload={'object_id': target_id},
        source=choice.source_id
    )]

    # For now, simplified: always lose 2 life (gift not promised)
    events.append(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': choice.player, 'amount': -2},
        source=choice.source_id
    ))

    return events


def nocturnal_hunger_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Nocturnal Hunger: Destroy target creature. Lose 2 life if gift not promised."""
    caster_id, spell_id = _get_spell_info(state, "Nocturnal Hunger")

    valid_targets = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types)
    ]

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to destroy",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _nocturnal_hunger_execute

    return []


def _banishing_light_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Banishing Light: Exile target nonland permanent opponent controls."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.EXILE,
        payload={'object_id': target_id, 'until_leaves': choice.source_id},
        source=choice.source_id
    )]


def banishing_light_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Banishing Light ETB trigger with targeting."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find valid targets: nonland permanents opponents control
        valid_targets = [
            perm.id for perm in state.objects.values()
            if (perm.zone == ZoneType.BATTLEFIELD and
                perm.controller != obj.controller and
                CardType.LAND not in perm.characteristics.types)
        ]

        if not valid_targets:
            return []

        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a nonland permanent to exile",
            min_targets=1,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = _banishing_light_execute

        return []

    return [make_etb_trigger(obj, etb_effect)]


# =============================================================================
# DAMAGE SPELL RESOLVE FUNCTIONS
# =============================================================================

def _playful_shove_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Playful Shove: 1 damage to any target, draw a card."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    events = []

    # Target can be player or permanent
    if target_id in state.players:
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 1, 'source': choice.source_id, 'is_combat': False},
            source=choice.source_id
        ))
    else:
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': target_id, 'amount': 1, 'source': choice.source_id, 'is_combat': False},
                source=choice.source_id
            ))

    # Draw a card
    events.append(Event(
        type=EventType.DRAW,
        payload={'player': choice.player, 'amount': 1},
        source=choice.source_id
    ))

    return events


def playful_shove_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Playful Shove: 1 damage to any target, draw a card."""
    caster_id, spell_id = _get_spell_info(state, "Playful Shove")

    # Valid targets: any creature/planeswalker or player
    valid_targets = list(state.players.keys())
    for obj in state.objects.values():
        if (obj.zone == ZoneType.BATTLEFIELD and
            (CardType.CREATURE in obj.characteristics.types or
             CardType.PLANESWALKER in obj.characteristics.types)):
            valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a target to deal 1 damage",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _playful_shove_execute

    return []


def _flame_lash_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Flame Lash: 4 damage to any target."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    if target_id in state.players:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 4, 'source': choice.source_id, 'is_combat': False},
            source=choice.source_id
        )]
    else:
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            return [Event(
                type=EventType.DAMAGE,
                payload={'target': target_id, 'amount': 4, 'source': choice.source_id, 'is_combat': False},
                source=choice.source_id
            )]
    return []


def flame_lash_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Flame Lash: 4 damage to any target."""
    caster_id, spell_id = _get_spell_info(state, "Flame Lash")

    valid_targets = list(state.players.keys())
    for obj in state.objects.values():
        if (obj.zone == ZoneType.BATTLEFIELD and
            (CardType.CREATURE in obj.characteristics.types or
             CardType.PLANESWALKER in obj.characteristics.types)):
            valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a target to deal 4 damage",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _flame_lash_execute

    return []


def _blooming_blast_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Blooming Blast: 2 damage to target creature (3 to controller if gift)."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': 2, 'source': choice.source_id, 'is_combat': False},
        source=choice.source_id
    )]


def blooming_blast_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Blooming Blast: 2 damage to target creature."""
    caster_id, spell_id = _get_spell_info(state, "Blooming Blast")

    valid_targets = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types)
    ]

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to deal 2 damage",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _blooming_blast_execute

    return []


def _sonar_strike_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Sonar Strike: 4 damage to attacking/blocking/tapped creature, gain 3 life if Bat."""
    target_id = selected[0] if selected else None
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

    # Check if controller has a Bat
    has_bat = any(
        obj.controller == choice.player and
        obj.zone == ZoneType.BATTLEFIELD and
        CardType.CREATURE in obj.characteristics.types and
        'Bat' in obj.characteristics.subtypes
        for obj in choice.callback_data.get('state_objects', {}).values()
    )

    # Simplified: check in current state
    for obj in state.objects.values():
        if (obj.controller == choice.player and
            obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types and
            'Bat' in obj.characteristics.subtypes):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': choice.player, 'amount': 3},
                source=choice.source_id
            ))
            break

    return events


def sonar_strike_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Sonar Strike: 4 damage to attacking, blocking, or tapped creature."""
    caster_id, spell_id = _get_spell_info(state, "Sonar Strike")

    # Valid targets: attacking, blocking, or tapped creatures
    valid_targets = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types and
            (obj.state.tapped or
             getattr(obj.state, 'attacking', False) or
             getattr(obj.state, 'blocking', False)))
    ]

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose an attacking, blocking, or tapped creature to deal 4 damage",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _sonar_strike_execute

    return []


def _take_out_the_trash_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Take Out the Trash: 3 damage to creature or planeswalker."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': 3, 'source': choice.source_id, 'is_combat': False},
        source=choice.source_id
    )]


def take_out_the_trash_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Take Out the Trash: 3 damage to creature or planeswalker."""
    caster_id, spell_id = _get_spell_info(state, "Take Out the Trash")

    valid_targets = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            (CardType.CREATURE in obj.characteristics.types or
             CardType.PLANESWALKER in obj.characteristics.types))
    ]

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature or planeswalker to deal 3 damage",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _take_out_the_trash_execute

    return []


def _rabid_gnaw_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Rabid Gnaw: Your creature gets +1/+0, then deals damage equal to its power to their creature."""
    if len(selected) < 2:
        return []

    your_creature_id = selected[0]
    their_creature_id = selected[1]

    your_creature = state.objects.get(your_creature_id)
    their_creature = state.objects.get(their_creature_id)

    if not your_creature or your_creature.zone != ZoneType.BATTLEFIELD:
        return []
    if not their_creature or their_creature.zone != ZoneType.BATTLEFIELD:
        return []

    power = get_power(your_creature, state) + 1  # +1/+0 buff

    return [
        Event(
            type=EventType.PUMP,
            payload={'object_id': your_creature_id, 'power': 1, 'toughness': 0, 'duration': 'end_of_turn'},
            source=choice.source_id
        ),
        Event(
            type=EventType.DAMAGE,
            payload={'target': their_creature_id, 'amount': power, 'source': your_creature_id, 'is_combat': False},
            source=choice.source_id
        )
    ]


def rabid_gnaw_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Rabid Gnaw: Your creature gets +1/+0 then deals damage to their creature."""
    caster_id, spell_id = _get_spell_info(state, "Rabid Gnaw")

    # Valid targets: your creatures and opponent's creatures
    your_creatures = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types and
            obj.controller == caster_id)
    ]

    their_creatures = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types and
            obj.controller != caster_id)
    ]

    if not your_creatures or not their_creatures:
        return []

    # For simplicity, create single choice with combined targets
    # In a full implementation, this would be two separate choices
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=your_creatures + their_creatures,
        prompt="Choose your creature, then opponent's creature",
        min_targets=2,
        max_targets=2,
        callback_data={'your_creatures': your_creatures, 'their_creatures': their_creatures}
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _rabid_gnaw_execute

    return []


def _giant_growth_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Giant Growth: Target creature gets +3/+3 until end of turn."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.PUMP,
        payload={'object_id': target_id, 'power': 3, 'toughness': 3, 'duration': 'end_of_turn'},
        source=choice.source_id
    )]


def giant_growth_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Giant Growth: Target creature gets +3/+3 until end of turn."""
    caster_id, spell_id = _get_spell_info(state, "Giant Growth")

    valid_targets = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types)
    ]

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to get +3/+3",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _giant_growth_execute

    return []


def _rabid_bite_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Rabid Bite: Your creature deals damage equal to its power to their creature."""
    if len(selected) < 2:
        return []

    your_creature_id = selected[0]
    their_creature_id = selected[1]

    your_creature = state.objects.get(your_creature_id)
    their_creature = state.objects.get(their_creature_id)

    if not your_creature or your_creature.zone != ZoneType.BATTLEFIELD:
        return []
    if not their_creature or their_creature.zone != ZoneType.BATTLEFIELD:
        return []

    power = get_power(your_creature, state)

    return [Event(
        type=EventType.DAMAGE,
        payload={'target': their_creature_id, 'amount': power, 'source': your_creature_id, 'is_combat': False},
        source=choice.source_id
    )]


def rabid_bite_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Rabid Bite: Your creature deals damage equal to its power to opponent's creature."""
    caster_id, spell_id = _get_spell_info(state, "Rabid Bite")

    your_creatures = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types and
            obj.controller == caster_id)
    ]

    their_creatures = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types and
            obj.controller != caster_id)
    ]

    if not your_creatures or not their_creatures:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=your_creatures + their_creatures,
        prompt="Choose your creature, then opponent's creature",
        min_targets=2,
        max_targets=2,
        callback_data={'your_creatures': your_creatures, 'their_creatures': their_creatures}
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _rabid_bite_execute

    return []


# =============================================================================
# MODAL SPELL RESOLVE FUNCTIONS
# =============================================================================

def _agate_assault_mode_handler(choice, selected, state: GameState) -> list[Event]:
    """Handle Agate Assault mode selection and follow-up targeting."""
    selected_mode = selected[0] if selected else 0
    mode_index = selected_mode["index"] if isinstance(selected_mode, dict) else selected_mode

    caster_id = choice.player
    spell_id = choice.source_id

    if mode_index == 0:
        # Mode 1: 4 damage to target creature (exile if dies)
        valid_targets = [
            obj.id for obj in state.objects.values()
            if (obj.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in obj.characteristics.types)
        ]

        if not valid_targets:
            return []

        target_choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            legal_targets=valid_targets,
            prompt="Choose a creature to deal 4 damage (exile if it dies)",
            min_targets=1,
            max_targets=1
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = _agate_assault_damage_execute
        return []

    else:
        # Mode 2: Exile target artifact
        valid_targets = [
            obj.id for obj in state.objects.values()
            if (obj.zone == ZoneType.BATTLEFIELD and
                CardType.ARTIFACT in obj.characteristics.types)
        ]

        if not valid_targets:
            return []

        target_choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            legal_targets=valid_targets,
            prompt="Choose an artifact to exile",
            min_targets=1,
            max_targets=1
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = _agate_assault_exile_execute
        return []


def _agate_assault_damage_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Agate Assault damage mode: 4 damage, exile if dies."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.DAMAGE,
        payload={
            'target': target_id,
            'amount': 4,
            'source': choice.source_id,
            'is_combat': False,
            'exile_on_death': True
        },
        source=choice.source_id
    )]


def _agate_assault_exile_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Agate Assault exile mode: Exile target artifact."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.EXILE,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def agate_assault_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Agate Assault: Modal - 4 damage to creature or exile artifact."""
    caster_id, spell_id = _get_spell_info(state, "Agate Assault")

    modes = [
        {"index": 0, "text": "Deal 4 damage to target creature (exile if it dies)"},
        {"index": 1, "text": "Exile target artifact"},
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        min_modes=1,
        max_modes=1,
        prompt="Choose one:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _agate_assault_mode_handler

    return []


def _early_winter_mode_handler(choice, selected, state: GameState) -> list[Event]:
    """Handle Early Winter mode selection and follow-up targeting."""
    selected_mode = selected[0] if selected else 0
    mode_index = selected_mode["index"] if isinstance(selected_mode, dict) else selected_mode

    caster_id = choice.player
    spell_id = choice.source_id

    if mode_index == 0:
        # Mode 1: Exile target creature
        valid_targets = [
            obj.id for obj in state.objects.values()
            if (obj.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in obj.characteristics.types)
        ]

        if not valid_targets:
            return []

        target_choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            legal_targets=valid_targets,
            prompt="Choose a creature to exile",
            min_targets=1,
            max_targets=1
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = _early_winter_exile_execute
        return []

    else:
        # Mode 2: Target opponent exiles an enchantment they control
        # For now, simplified - find opponent's enchantments
        opponents = [p for p in state.players.keys() if p != caster_id]
        valid_targets = [
            obj.id for obj in state.objects.values()
            if (obj.zone == ZoneType.BATTLEFIELD and
                CardType.ENCHANTMENT in obj.characteristics.types and
                obj.controller != caster_id)
        ]

        if not valid_targets:
            return []

        # Simplified: caster chooses which opponent's enchantment gets exiled
        target_choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            legal_targets=valid_targets,
            prompt="Choose an opponent's enchantment for them to exile",
            min_targets=1,
            max_targets=1
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = _early_winter_enchantment_execute
        return []


def _early_winter_exile_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Early Winter: Exile target creature."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.EXILE,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def _early_winter_enchantment_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Early Winter: Opponent exiles their enchantment."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.EXILE,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def early_winter_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Early Winter: Modal - exile creature or opponent exiles enchantment."""
    caster_id, spell_id = _get_spell_info(state, "Early Winter")

    modes = [
        {"index": 0, "text": "Exile target creature"},
        {"index": 1, "text": "Target opponent exiles an enchantment they control"},
    ]

    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        min_modes=1,
        max_modes=1,
        prompt="Choose one:"
    )
    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _early_winter_mode_handler

    return []


def _downwind_ambusher_mode_handler(choice, selected, state: GameState) -> list[Event]:
    """Handle Downwind Ambusher mode selection and follow-up targeting."""
    selected_mode = selected[0] if selected else 0
    mode_index = selected_mode["index"] if isinstance(selected_mode, dict) else selected_mode

    caster_id = choice.player
    spell_id = choice.source_id

    if mode_index == 0:
        # Mode 1: -1/-1 to target opponent's creature
        valid_targets = [
            obj.id for obj in state.objects.values()
            if (obj.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in obj.characteristics.types and
                obj.controller != caster_id)
        ]

        if not valid_targets:
            return []

        target_choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            legal_targets=valid_targets,
            prompt="Choose an opponent's creature to get -1/-1",
            min_targets=1,
            max_targets=1
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = _downwind_ambusher_debuff_execute
        return []

    else:
        # Mode 2: Destroy target creature dealt damage this turn
        # Simplified - just target any opponent creature
        valid_targets = [
            obj.id for obj in state.objects.values()
            if (obj.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in obj.characteristics.types and
                obj.controller != caster_id)
        ]

        if not valid_targets:
            return []

        target_choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            legal_targets=valid_targets,
            prompt="Choose an opponent's creature that was dealt damage this turn to destroy",
            min_targets=1,
            max_targets=1
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = _downwind_ambusher_destroy_execute
        return []


def _downwind_ambusher_debuff_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Downwind Ambusher: -1/-1 to opponent's creature."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.PUMP,
        payload={'object_id': target_id, 'power': -1, 'toughness': -1, 'duration': 'end_of_turn'},
        source=choice.source_id
    )]


def _downwind_ambusher_destroy_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Downwind Ambusher: Destroy creature dealt damage this turn."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.DESTROY,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def downwind_ambusher_etb_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Downwind Ambusher ETB: Modal choice - -1/-1 or destroy damaged creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        modes = [
            {"index": 0, "text": "Target opponent's creature gets -1/-1 until end of turn"},
            {"index": 1, "text": "Destroy target opponent's creature dealt damage this turn"},
        ]

        choice = create_modal_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            modes=modes,
            min_modes=1,
            max_modes=1,
            prompt="Choose one:"
        )
        choice.choice_type = "modal_with_callback"
        choice.callback_data['handler'] = _downwind_ambusher_mode_handler

        return []

    return [make_etb_trigger(obj, etb_effect)]


def _hivespine_wolverine_mode_handler(choice, selected, state: GameState) -> list[Event]:
    """Handle Hivespine Wolverine mode selection and follow-up targeting."""
    selected_mode = selected[0] if selected else 0
    mode_index = selected_mode["index"] if isinstance(selected_mode, dict) else selected_mode

    caster_id = choice.player
    source_id = choice.source_id

    if mode_index == 0:
        # Mode 1: Put a +1/+1 counter on target creature you control
        valid_targets = [
            obj.id for obj in state.objects.values()
            if (obj.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in obj.characteristics.types and
                obj.controller == caster_id)
        ]

        if not valid_targets:
            return []

        target_choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=source_id,
            legal_targets=valid_targets,
            prompt="Choose a creature to put a +1/+1 counter on",
            min_targets=1,
            max_targets=1
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = _hivespine_counter_execute
        return []

    elif mode_index == 1:
        # Mode 2: This creature fights target creature token
        valid_targets = [
            obj.id for obj in state.objects.values()
            if (obj.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in obj.characteristics.types and
                getattr(obj.state, 'is_token', False))
        ]

        if not valid_targets:
            return []

        target_choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=source_id,
            legal_targets=valid_targets,
            prompt="Choose a creature token to fight",
            min_targets=1,
            max_targets=1
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = _hivespine_fight_execute
        target_choice.callback_data['fighter_id'] = source_id
        return []

    else:
        # Mode 3: Destroy target artifact or enchantment
        valid_targets = [
            obj.id for obj in state.objects.values()
            if (obj.zone == ZoneType.BATTLEFIELD and
                (CardType.ARTIFACT in obj.characteristics.types or
                 CardType.ENCHANTMENT in obj.characteristics.types))
        ]

        if not valid_targets:
            return []

        target_choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=source_id,
            legal_targets=valid_targets,
            prompt="Choose an artifact or enchantment to destroy",
            min_targets=1,
            max_targets=1
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = _hivespine_destroy_execute
        return []


def _hivespine_counter_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Hivespine Wolverine: Put +1/+1 counter on target creature."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.COUNTER_ADDED,
        payload={'object_id': target_id, 'counter_type': '+1/+1', 'amount': 1},
        source=choice.source_id
    )]


def _hivespine_fight_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Hivespine Wolverine: Fight target creature token."""
    target_id = selected[0] if selected else None
    fighter_id = choice.callback_data.get('fighter_id')

    if not target_id or not fighter_id:
        return []

    target = state.objects.get(target_id)
    fighter = state.objects.get(fighter_id)
    if not target or not fighter:
        return []
    if target.zone != ZoneType.BATTLEFIELD or fighter.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.FIGHT,
        payload={'creature1': fighter_id, 'creature2': target_id},
        source=choice.source_id
    )]


def _hivespine_destroy_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Hivespine Wolverine: Destroy target artifact or enchantment."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.DESTROY,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def hivespine_wolverine_modal_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Hivespine Wolverine ETB: Modal - counter, fight token, or destroy artifact/enchantment."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        modes = [
            {"index": 0, "text": "Put a +1/+1 counter on target creature you control"},
            {"index": 1, "text": "This creature fights target creature token"},
            {"index": 2, "text": "Destroy target artifact or enchantment"},
        ]

        choice = create_modal_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            modes=modes,
            min_modes=1,
            max_modes=1,
            prompt="Choose one:"
        )
        choice.choice_type = "modal_with_callback"
        choice.callback_data['handler'] = _hivespine_wolverine_mode_handler

        return []

    return [make_etb_trigger(obj, etb_effect)]


# =============================================================================
# BOUNCE SPELL RESOLVE FUNCTIONS
# =============================================================================

def _calamitous_tide_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Calamitous Tide: Return up to 2 creatures to hand, draw 2, discard 1."""
    events = []

    # Return selected creatures to hand
    for target_id in selected:
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            events.append(Event(
                type=EventType.BOUNCE,
                payload={'object_id': target_id},
                source=choice.source_id
            ))

    # Draw 2 cards, discard 1
    events.append(Event(
        type=EventType.DRAW,
        payload={'player': choice.player, 'amount': 2},
        source=choice.source_id
    ))
    events.append(Event(
        type=EventType.DISCARD,
        payload={'player': choice.player, 'amount': 1},
        source=choice.source_id
    ))

    return events


def calamitous_tide_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Calamitous Tide: Return up to two creatures to hand, draw 2, discard 1."""
    caster_id, spell_id = _get_spell_info(state, "Calamitous Tide")

    valid_targets = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types)
    ]

    if not valid_targets:
        # Still draw and discard even without targets
        return [
            Event(type=EventType.DRAW, payload={'player': caster_id, 'amount': 2}, source=spell_id),
            Event(type=EventType.DISCARD, payload={'player': caster_id, 'amount': 1}, source=spell_id)
        ]

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose up to two creatures to return to their owners' hands",
        min_targets=0,
        max_targets=2
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _calamitous_tide_execute

    return []


def _run_away_together_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Run Away Together: Return two creatures controlled by different players."""
    events = []

    for target_id in selected:
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            events.append(Event(
                type=EventType.BOUNCE,
                payload={'object_id': target_id},
                source=choice.source_id
            ))

    return events


def run_away_together_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Run Away Together: Return two creatures controlled by different players."""
    caster_id, spell_id = _get_spell_info(state, "Run Away Together")

    valid_targets = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types)
    ]

    if len(valid_targets) < 2:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose two creatures controlled by different players",
        min_targets=2,
        max_targets=2
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _run_away_together_execute

    return []


def _conduct_electricity_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Conduct Electricity: 6 damage to creature, 2 damage to creature token."""
    events = []

    if len(selected) >= 1:
        target1 = state.objects.get(selected[0])
        if target1 and target1.zone == ZoneType.BATTLEFIELD:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': selected[0], 'amount': 6, 'source': choice.source_id, 'is_combat': False},
                source=choice.source_id
            ))

    if len(selected) >= 2:
        target2 = state.objects.get(selected[1])
        if target2 and target2.zone == ZoneType.BATTLEFIELD:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': selected[1], 'amount': 2, 'source': choice.source_id, 'is_combat': False},
                source=choice.source_id
            ))

    return events


def conduct_electricity_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Conduct Electricity: 6 damage to creature, 2 to creature token."""
    caster_id, spell_id = _get_spell_info(state, "Conduct Electricity")

    # Primary target: any creature
    creatures = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types)
    ]

    # Secondary target: creature tokens only
    tokens = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types and
            getattr(obj.state, 'is_token', False))
    ]

    if not creatures:
        return []

    # For simplicity, use combined targeting
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=creatures,
        prompt="Choose a creature (6 damage), then optionally a creature token (2 damage)",
        min_targets=1,
        max_targets=2,
        callback_data={'tokens': tokens}
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _conduct_electricity_execute

    return []


# =============================================================================
# COMBAT TRICK / PUMP SPELL RESOLVE FUNCTIONS
# =============================================================================

def _shore_up_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Shore Up: +1/+1, hexproof, and untap target creature you control."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(
            type=EventType.PUMP,
            payload={'object_id': target_id, 'power': 1, 'toughness': 1, 'duration': 'end_of_turn'},
            source=choice.source_id
        ),
        Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': target_id, 'keyword': 'hexproof', 'duration': 'end_of_turn'},
            source=choice.source_id
        ),
        Event(
            type=EventType.UNTAP,
            payload={'object_id': target_id},
            source=choice.source_id
        )
    ]


def shore_up_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Shore Up: Target creature you control gets +1/+1, hexproof, and untap."""
    caster_id, spell_id = _get_spell_info(state, "Shore Up")

    valid_targets = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types and
            obj.controller == caster_id)
    ]

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to get +1/+1, hexproof, and untap",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _shore_up_execute

    return []


def _mabels_mettle_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Mabel's Mettle: +2/+2 to one creature, +1/+1 to another."""
    events = []

    if len(selected) >= 1:
        target1 = state.objects.get(selected[0])
        if target1 and target1.zone == ZoneType.BATTLEFIELD:
            events.append(Event(
                type=EventType.PUMP,
                payload={'object_id': selected[0], 'power': 2, 'toughness': 2, 'duration': 'end_of_turn'},
                source=choice.source_id
            ))

    if len(selected) >= 2:
        target2 = state.objects.get(selected[1])
        if target2 and target2.zone == ZoneType.BATTLEFIELD:
            events.append(Event(
                type=EventType.PUMP,
                payload={'object_id': selected[1], 'power': 1, 'toughness': 1, 'duration': 'end_of_turn'},
                source=choice.source_id
            ))

    return events


def mabels_mettle_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Mabel's Mettle: +2/+2 to target, +1/+1 to another target."""
    caster_id, spell_id = _get_spell_info(state, "Mabel's Mettle")

    valid_targets = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types)
    ]

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature (+2/+2), then optionally another creature (+1/+1)",
        min_targets=1,
        max_targets=2
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _mabels_mettle_execute

    return []


def _might_of_the_meek_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Might of the Meek: Trample, +1/+0 if Mouse, draw."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    events = [
        Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': target_id, 'keyword': 'trample', 'duration': 'end_of_turn'},
            source=choice.source_id
        )
    ]

    # Check for Mouse
    has_mouse = any(
        obj.controller == choice.player and
        obj.zone == ZoneType.BATTLEFIELD and
        CardType.CREATURE in obj.characteristics.types and
        'Mouse' in obj.characteristics.subtypes
        for obj in state.objects.values()
    )

    if has_mouse:
        events.append(Event(
            type=EventType.PUMP,
            payload={'object_id': target_id, 'power': 1, 'toughness': 0, 'duration': 'end_of_turn'},
            source=choice.source_id
        ))

    # Draw a card
    events.append(Event(
        type=EventType.DRAW,
        payload={'player': choice.player, 'amount': 1},
        source=choice.source_id
    ))

    return events


def might_of_the_meek_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Might of the Meek: Trample, +1/+0 if Mouse, draw."""
    caster_id, spell_id = _get_spell_info(state, "Might of the Meek")

    valid_targets = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types)
    ]

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to gain trample",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _might_of_the_meek_execute

    return []


def _savor_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Savor: -2/-2 to creature, create Food."""
    target_id = selected[0] if selected else None

    events = []

    if target_id:
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            events.append(Event(
                type=EventType.PUMP,
                payload={'object_id': target_id, 'power': -2, 'toughness': -2, 'duration': 'end_of_turn'},
                source=choice.source_id
            ))

    # Create Food token
    events.append(Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': choice.player,
            'token_type': 'Artifact',
            'name': 'Food',
            'subtypes': {'Food'}
        },
        source=choice.source_id
    ))

    return events


def savor_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Savor: Target creature gets -2/-2, create Food."""
    caster_id, spell_id = _get_spell_info(state, "Savor")

    valid_targets = [
        obj.id for obj in state.objects.values()
        if (obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types)
    ]

    if not valid_targets:
        # Still create Food
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': caster_id,
                'token_type': 'Artifact',
                'name': 'Food',
                'subtypes': {'Food'}
            },
            source=spell_id
        )]

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to get -2/-2",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _savor_execute

    return []


def pawpatch_formation_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Pawpatch Formation: Target creature you control gets +X/+X until end of turn,
    where X is the number of creatures you control.

    Creates a target choice for the caster. Returns empty events to pause resolution.
    """
    # Find the spell on the stack to determine who cast it
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Pawpatch Formation":
                caster_id = obj.controller
                spell_id = obj.id
                break

    # Fallback to active player if we can't find the spell
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "pawpatch_formation_spell"

    # Count creatures for display purposes
    creature_count = sum(
        1 for obj in state.objects.values()
        if (obj.controller == caster_id and
            obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types)
    )

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
        prompt=f"Choose a creature to buff with Pawpatch Formation (+{creature_count}/+{creature_count})",
        min_targets=1,
        max_targets=1
    )

    # Set up callback for when target is selected
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _pawpatch_formation_execute

    # Return empty events to pause resolution until choice is submitted
    return []


# =============================================================================
# CARD DEFINITIONS
# =============================================================================

BANISHING_LIGHT = make_enchantment(
    name="Banishing Light",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, exile target nonland permanent an opponent controls until this enchantment leaves the battlefield.",
    setup_interceptors=banishing_light_setup,
)

BEZA_THE_BOUNDING_SPRING = make_creature(
    name="Beza, the Bounding Spring",
    power=4, toughness=5,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Elemental", "Elk"},
    supertypes={"Legendary"},
    text="When Beza enters, create a Treasure token if an opponent controls more lands than you. You gain 4 life if an opponent has more life than you. Create two 1/1 blue Fish creature tokens if an opponent controls more creatures than you. Draw a card if an opponent has more cards in hand than you.",
    setup_interceptors=beza_the_bounding_spring_setup,
)

BRAVEKIN_DUO = make_creature(
    name="Brave-Kin Duo",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Mouse", "Rabbit"},
    text="{1}, {T}: Target creature gets +1/+1 until end of turn. Activate only as a sorcery.",
    setup_interceptors=bravekin_duo_setup,
)

BRIGHTBLADE_STOAT = make_creature(
    name="Brightblade Stoat",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Soldier", "Weasel"},
    text="First strike, lifelink",
)

BUILDERS_TALENT = make_enchantment(
    name="Builder's Talent",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="(Gain the next level as a sorcery to add its ability.)\nWhen this Class enters, create a 0/4 white Wall creature token with defender.\n{W}: Level 2\nWhenever one or more noncreature, nonland permanents you control enter, put a +1/+1 counter on target creature you control.\n{4}{W}: Level 3\nWhen this Class becomes level 3, return target noncreature, nonland permanent card from your graveyard to the battlefield.",
    subtypes={"Class"},
    setup_interceptors=builders_talent_setup,
)

CARETAKERS_TALENT = make_enchantment(
    name="Caretaker's Talent",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="(Gain the next level as a sorcery to add its ability.)\nWhenever one or more tokens you control enter, draw a card. This ability triggers only once each turn.\n{W}: Level 2\nWhen this Class becomes level 2, create a token that's a copy of target token you control.\n{3}{W}: Level 3\nCreature tokens you control get +2/+2.",
    subtypes={"Class"},
    setup_interceptors=caretakers_talent_setup,
)

CARROT_CAKE = make_artifact(
    name="Carrot Cake",
    mana_cost="{1}{W}",
    text="When this artifact enters and when you sacrifice it, create a 1/1 white Rabbit creature token and scry 1. (Look at the top card of your library. You may put that card on the bottom.)\n{2}, {T}, Sacrifice this artifact: You gain 3 life.",
    subtypes={"Food"},
    setup_interceptors=carrot_cake_setup,
)

CRUMB_AND_GET_IT = make_instant(
    name="Crumb and Get It",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Gift a Food (You may promise an opponent a gift as you cast this spell. If you do, they create a Food token before its other effects. It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\nTarget creature you control gets +2/+2 until end of turn. If the gift was promised, that creature also gains indestructible until end of turn.",
)

DAWNS_TRUCE = make_instant(
    name="Dawn's Truce",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Gift a card (You may promise an opponent a gift as you cast this spell. If you do, they draw a card before its other effects.)\nYou and permanents you control gain hexproof until end of turn. If the gift was promised, permanents you control also gain indestructible until end of turn.",
)

DEWDROP_CURE = make_sorcery(
    name="Dewdrop Cure",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Gift a card (You may promise an opponent a gift as you cast this spell. If you do, they draw a card before its other effects.)\nReturn up to two target creature cards each with mana value 2 or less from your graveyard to the battlefield. If the gift was promised, instead return up to three target creature cards each with mana value 2 or less from your graveyard to the battlefield.",
)

DRIFTGLOOM_COYOTE = make_creature(
    name="Driftgloom Coyote",
    power=3, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Coyote", "Elemental"},
    text="When this creature enters, exile target creature an opponent controls until this creature leaves the battlefield. If that creature had power 2 or less, put a +1/+1 counter on this creature.",
    setup_interceptors=driftgloom_coyote_setup,
)

ESSENCE_CHANNELER = make_creature(
    name="Essence Channeler",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Bat", "Cleric"},
    text="As long as you've lost life this turn, this creature has flying and vigilance.\nWhenever you gain life, put a +1/+1 counter on this creature.\nWhen this creature dies, put its counters on target creature you control.",
    setup_interceptors=essence_channeler_setup
)

FEATHER_OF_FLIGHT = make_enchantment(
    name="Feather of Flight",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Flash\nEnchant creature\nWhen this Aura enters, draw a card.\nEnchanted creature gets +1/+0 and has flying.",
    subtypes={"Aura"},
    setup_interceptors=feather_of_flight_setup,
)

FLOWERFOOT_SWORDMASTER = make_creature(
    name="Flowerfoot Swordmaster",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Mouse", "Soldier"},
    text="Offspring {2} (You may pay an additional {2} as you cast this spell. If you do, when this creature enters, create a 1/1 token copy of it.)\nValiant — Whenever this creature becomes the target of a spell or ability you control for the first time each turn, Mice you control get +1/+0 until end of turn.",
    setup_interceptors=flowerfoot_swordmaster_setup,
)

HARVESTRITE_HOST = make_creature(
    name="Harvestrite Host",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Citizen", "Rabbit"},
    text="Whenever this creature or another Rabbit you control enters, target creature you control gets +1/+0 until end of turn. Then draw a card if this is the second time this ability has resolved this turn.",
    setup_interceptors=harvestrite_host_setup
)

HOP_TO_IT = make_sorcery(
    name="Hop to It",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Create three 1/1 white Rabbit creature tokens.",
)

INTREPID_RABBIT = make_creature(
    name="Intrepid Rabbit",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Rabbit", "Soldier"},
    text="Offspring {1} (You may pay an additional {1} as you cast this spell. If you do, when this creature enters, create a 1/1 token copy of it.)\nWhen this creature enters, target creature you control gets +1/+1 until end of turn.",
    setup_interceptors=intrepid_rabbit_setup
)

JACKDAW_SAVIOR = make_creature(
    name="Jackdaw Savior",
    power=3, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Bird", "Cleric"},
    text="Flying\nWhenever this creature or another creature you control with flying dies, return another target creature card with lesser mana value from your graveyard to the battlefield.",
    setup_interceptors=jackdaw_savior_setup
)

JOLLY_GERBILS = make_creature(
    name="Jolly Gerbils",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Citizen", "Hamster"},
    text="Whenever you give a gift, draw a card.",
    setup_interceptors=jolly_gerbils_setup,
)

LIFECREED_DUO = make_creature(
    name="Lifecreed Duo",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Bat", "Bird"},
    text="Flying\nWhenever another creature you control enters, you gain 1 life.",
    setup_interceptors=lifecreed_duo_setup
)

MABELS_METTLE = make_instant(
    name="Mabel's Mettle",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 until end of turn. Up to one other target creature gets +1/+1 until end of turn.",
    resolve=mabels_mettle_resolve,
)

MOUSE_TRAPPER = make_creature(
    name="Mouse Trapper",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Mouse", "Soldier"},
    text="Flash\nValiant — Whenever this creature becomes the target of a spell or ability you control for the first time each turn, tap target creature an opponent controls.",
    setup_interceptors=mouse_trapper_setup,
)

NETTLE_GUARD = make_creature(
    name="Nettle Guard",
    power=3, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Mouse", "Soldier"},
    text="Valiant — Whenever this creature becomes the target of a spell or ability you control for the first time each turn, it gets +0/+2 until end of turn.\n{1}, Sacrifice this creature: Destroy target artifact or enchantment.",
    setup_interceptors=nettle_guard_setup,
)

PARTING_GUST = make_instant(
    name="Parting Gust",
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    text="Gift a tapped Fish (You may promise an opponent a gift as you cast this spell. If you do, they create a tapped 1/1 blue Fish creature token before its other effects.)\nExile target nontoken creature. If the gift wasn't promised, return that card to the battlefield under its owner's control with a +1/+1 counter on it at the beginning of the next end step.",
)

PILEATED_PROVISIONER = make_creature(
    name="Pileated Provisioner",
    power=3, toughness=4,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Bird", "Scout"},
    text="Flying\nWhen this creature enters, put a +1/+1 counter on target creature you control without flying.",
    setup_interceptors=pileated_provisioner_setup
)

RABBIT_RESPONSE = make_instant(
    name="Rabbit Response",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +2/+1 until end of turn. If you control a Rabbit, scry 2. (Look at the top two cards of your library, then put any number of them on the bottom and the rest on top in any order.)",
)

REPEL_CALAMITY = make_instant(
    name="Repel Calamity",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Destroy target creature with power or toughness 4 or greater.",
    resolve=repel_calamity_resolve,
)

SALVATION_SWAN = make_creature(
    name="Salvation Swan",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Bird", "Cleric"},
    text="Flash\nFlying\nWhenever this creature or another Bird you control enters, exile up to one target creature you control without flying. Return it to the battlefield under its owner's control with a flying counter on it at the beginning of the next end step.",
    setup_interceptors=salvation_swan_setup
)

SEASON_OF_THE_BURROW = make_sorcery(
    name="Season of the Burrow",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Choose up to five {P} worth of modes. You may choose the same mode more than once.\n{P} — Create a 1/1 white Rabbit creature token.\n{P}{P} — Exile target nonland permanent. Its controller draws a card.\n{P}{P}{P} — Return target permanent card with mana value 3 or less from your graveyard to the battlefield with an indestructible counter on it.",
)

SEASONED_WARRENGUARD = make_creature(
    name="Seasoned Warrenguard",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Rabbit", "Warrior"},
    text="Whenever this creature attacks while you control a token, this creature gets +2/+0 until end of turn.",
    setup_interceptors=seasoned_warrenguard_setup
)

SHRIKE_FORCE = make_creature(
    name="Shrike Force",
    power=1, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Bird", "Knight"},
    text="Flying, double strike, vigilance",
)

SONAR_STRIKE = make_instant(
    name="Sonar Strike",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Sonar Strike deals 4 damage to target attacking, blocking, or tapped creature. You gain 3 life if you control a Bat.",
    resolve=sonar_strike_resolve,
)

STAR_CHARTER = make_creature(
    name="Star Charter",
    power=3, toughness=1,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Bat", "Cleric"},
    text="Flying\nAt the beginning of your end step, if you gained or lost life this turn, look at the top four cards of your library. You may reveal a creature card with power 3 or less from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
    setup_interceptors=star_charter_setup,
)

STARFALL_INVOCATION = make_sorcery(
    name="Starfall Invocation",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Gift a card (You may promise an opponent a gift as you cast this spell. If you do, they draw a card before its other effects.)\nDestroy all creatures. If the gift was promised, return a creature card put into your graveyard this way to the battlefield under your control.",
)

THISTLEDOWN_PLAYERS = make_creature(
    name="Thistledown Players",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Bard", "Mouse"},
    text="Whenever this creature attacks, untap target nonland permanent.",
    setup_interceptors=thistledown_players_setup
)

VALLEY_QUESTCALLER = make_creature(
    name="Valley Questcaller",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Rabbit", "Warrior"},
    text="Whenever one or more other Rabbits, Bats, Birds, and/or Mice you control enter, scry 1.\nOther Rabbits, Bats, Birds, and Mice you control get +1/+1.",
    setup_interceptors=valley_questcaller_setup
)

WARREN_ELDER = make_creature(
    name="Warren Elder",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Rabbit"},
    text="{3}{W}: Creatures you control get +1/+1 until end of turn.",
    setup_interceptors=warren_elder_setup,
)

WARREN_WARLEADER = make_creature(
    name="Warren Warleader",
    power=4, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Knight", "Rabbit"},
    text="Offspring {2} (You may pay an additional {2} as you cast this spell. If you do, when this creature enters, create a 1/1 token copy of it.)\nWhenever you attack, choose one —\n• Create a 1/1 white Rabbit creature token that's tapped and attacking.\n• Attacking creatures you control get +1/+1 until end of turn.",
    setup_interceptors=warren_warleader_setup,
)

WAXWANE_WITNESS = make_creature(
    name="Wax-Wane Witness",
    power=2, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Bat", "Cleric"},
    text="Flying, vigilance\nWhenever you gain or lose life during your turn, this creature gets +1/+0 until end of turn.",
    setup_interceptors=waxwane_witness_setup,
)

WHISKERVALE_FORERUNNER = make_creature(
    name="Whiskervale Forerunner",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Bard", "Mouse"},
    text="Valiant — Whenever this creature becomes the target of a spell or ability you control for the first time each turn, look at the top five cards of your library. You may reveal a creature card with mana value 3 or less from among them. You may put it onto the battlefield if it's your turn. If you don't put it onto the battlefield, put it into your hand. Put the rest on the bottom of your library in a random order.",
    setup_interceptors=whiskervale_forerunner_setup,
)

AZURE_BEASTBINDER = make_creature(
    name="Azure Beastbinder",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Rat", "Rogue"},
    text="Vigilance\nThis creature can't be blocked by creatures with power 2 or greater.\nWhenever this creature attacks, up to one target artifact, creature, or planeswalker an opponent controls loses all abilities until your next turn. If it's a creature, it also has base power and toughness 2/2 until your next turn.",
    setup_interceptors=azure_beastbinder_setup,
)

BELLOWING_CRIER = make_creature(
    name="Bellowing Crier",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Advisor", "Frog"},
    text="When this creature enters, draw a card, then discard a card.",
    setup_interceptors=bellowing_crier_setup
)

CALAMITOUS_TIDE = make_sorcery(
    name="Calamitous Tide",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Return up to two target creatures to their owners' hands. Draw two cards, then discard a card.",
    resolve=calamitous_tide_resolve,
)

DARING_WAVERIDER = make_creature(
    name="Daring Waverider",
    power=4, toughness=4,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Otter", "Wizard"},
    text="When this creature enters, you may cast target instant or sorcery card with mana value 4 or less from your graveyard without paying its mana cost. If that spell would be put into your graveyard, exile it instead.",
    setup_interceptors=daring_waverider_setup,
)

DAZZLING_DENIAL = make_instant(
    name="Dazzling Denial",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {2}. If you control a Bird, counter that spell unless its controller pays {4} instead.",
)

DIRE_DOWNDRAFT = make_instant(
    name="Dire Downdraft",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="This spell costs {1} less to cast if it targets an attacking or tapped creature.\nTarget creature's owner puts it on their choice of the top or bottom of their library.",
)

DOUR_PORTMAGE = make_creature(
    name="Dour Port-Mage",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Frog", "Wizard"},
    text="Whenever one or more other creatures you control leave the battlefield without dying, draw a card.\n{1}{U}, {T}: Return another target creature you control to its owner's hand.",
    setup_interceptors=dour_portmage_setup,
)

EDDYMURK_CRAB = make_creature(
    name="Eddymurk Crab",
    power=5, toughness=5,
    mana_cost="{5}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Crab", "Elemental"},
    text="Flash\nThis spell costs {1} less to cast for each instant and sorcery card in your graveyard.\nThis creature enters tapped if it's not your turn.\nWhen this creature enters, tap up to two target creatures.",
    setup_interceptors=eddymurk_crab_setup
)

ELUGE_THE_SHORELESS_SEA = make_creature(
    name="Eluge, the Shoreless Sea",
    power=0, toughness=0,
    mana_cost="{1}{U}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Fish"},
    supertypes={"Legendary"},
    text="Eluge's power and toughness are each equal to the number of Islands you control.\nWhenever Eluge enters or attacks, put a flood counter on target land. It's an Island in addition to its other types for as long as it has a flood counter on it.\nThe first instant or sorcery spell you cast each turn costs {U} (or {1}) less to cast for each land you control with a flood counter on it.",
    setup_interceptors=eluge_the_shoreless_sea_setup,
)

FINCH_FORMATION = make_creature(
    name="Finch Formation",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Scout"},
    text="Offspring {3} (You may pay an additional {3} as you cast this spell. If you do, when this creature enters, create a 1/1 token copy of it.)\nFlying\nWhen this creature enters, target creature you control gains flying until end of turn.",
    setup_interceptors=finch_formation_setup
)

GOSSIPS_TALENT = make_enchantment(
    name="Gossip's Talent",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="(Gain the next level as a sorcery to add its ability.)\nWhenever a creature you control enters, surveil 1.\n{1}{U}: Level 2\nWhenever you attack, target attacking creature with power 3 or less can't be blocked this turn.\n{3}{U}: Level 3\nWhenever a creature you control deals combat damage to a player, you may exile it, then return it to the battlefield under its owner's control.",
    subtypes={"Class"},
    setup_interceptors=gossips_talent_setup,
)

INTO_THE_FLOOD_MAW = make_instant(
    name="Into the Flood Maw",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Gift a tapped Fish (You may promise an opponent a gift as you cast this spell. If you do, they create a tapped 1/1 blue Fish creature token before its other effects.)\nReturn target creature an opponent controls to its owner's hand. If the gift was promised, instead return target nonland permanent an opponent controls to its owner's hand.",
)

KITNAP = make_enchantment(
    name="Kitnap",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Gift a card (You may promise an opponent a gift as you cast this spell. If you do, when it enters, they draw a card.)\nEnchant creature\nWhen this Aura enters, tap enchanted creature. If the gift wasn't promised, put three stun counters on it.\nYou control enchanted creature.",
    subtypes={"Aura"},
    setup_interceptors=kitnap_setup,
)

KITSA_OTTERBALL_ELITE = make_creature(
    name="Kitsa, Otterball Elite",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Otter", "Wizard"},
    supertypes={"Legendary"},
    text="Vigilance\nProwess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\n{T}: Draw a card, then discard a card.\n{2}, {T}: Copy target instant or sorcery spell you control. You may choose new targets for the copy. Activate only if Kitsa's power is 3 or greater.",
    setup_interceptors=kitsa_otterball_elite_setup,
)

KNIGHTFISHER = make_creature(
    name="Knightfisher",
    power=4, toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Knight"},
    text="Flying\nWhenever another nontoken Bird you control enters, create a 1/1 blue Fish creature token.",
    setup_interceptors=knightfisher_setup
)

LIGHTSHELL_DUO = make_creature(
    name="Lightshell Duo",
    power=3, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Otter", "Rat"},
    text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nWhen this creature enters, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
    setup_interceptors=lightshell_duo_setup
)

LONG_RIVER_LURKER = make_creature(
    name="Long River Lurker",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Frog", "Scout"},
    text="Ward {1}\nOther Frogs you control have ward {1}.\nWhen this creature enters, target creature you control can't be blocked this turn. Whenever that creature deals combat damage this turn, you may exile it. If you do, return it to the battlefield under its owner's control.",
    setup_interceptors=long_river_lurker_setup
)

LONG_RIVERS_PULL = make_instant(
    name="Long River's Pull",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Gift a card (You may promise an opponent a gift as you cast this spell. If you do, they draw a card before its other effects.)\nCounter target creature spell. If the gift was promised, instead counter target spell.",
)

MIND_SPIRAL = make_sorcery(
    name="Mind Spiral",
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    text="Gift a tapped Fish (You may promise an opponent a gift as you cast this spell. If you do, they create a tapped 1/1 blue Fish creature token before its other effects.)\nTarget player draws three cards. If the gift was promised, tap target creature an opponent controls and put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

MINDWHISKER = make_creature(
    name="Mindwhisker",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Rat", "Wizard"},
    text="At the beginning of your upkeep, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\nThreshold — As long as there are seven or more cards in your graveyard, creatures your opponents control get -1/-0.",
    setup_interceptors=mindwhisker_setup
)

MOCKINGBIRD = make_creature(
    name="Mockingbird",
    power=1, toughness=1,
    mana_cost="{X}{U}",
    colors={Color.BLUE},
    subtypes={"Bard", "Bird"},
    text="Flying\nYou may have this creature enter as a copy of any creature on the battlefield with mana value less than or equal to the amount of mana spent to cast this creature, except it's a Bird in addition to its other types and it has flying.",
    setup_interceptors=mockingbird_setup,
)

NIGHTWHORL_HERMIT = make_creature(
    name="Nightwhorl Hermit",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Rat", "Rogue"},
    text="Vigilance\nThreshold — As long as there are seven or more cards in your graveyard, this creature gets +1/+0 and can't be blocked.",
    setup_interceptors=nightwhorl_hermit_setup,
)

OTTERBALL_ANTICS = make_sorcery(
    name="Otterball Antics",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Create a 1/1 blue and red Otter creature token with prowess. If this spell was cast from anywhere other than your hand, put a +1/+1 counter on that creature. (Whenever you cast a noncreature spell, a creature with prowess gets +1/+1 until end of turn.)\nFlashback {3}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

PEARL_OF_WISDOM = make_sorcery(
    name="Pearl of Wisdom",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="This spell costs {1} less to cast if you control an Otter.\nDraw two cards.",
)

PLUMECREED_ESCORT = make_creature(
    name="Plumecreed Escort",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Scout"},
    text="Flash\nFlying\nWhen this creature enters, target creature you control gains hexproof until end of turn.",
    setup_interceptors=plumecreed_escort_setup
)

PORTENT_OF_CALAMITY = make_sorcery(
    name="Portent of Calamity",
    mana_cost="{X}{U}",
    colors={Color.BLUE},
    text="Reveal the top X cards of your library. For each card type, you may exile a card of that type from among them. Put the rest into your graveyard. You may cast a spell from among the exiled cards without paying its mana cost if you exiled four or more cards this way. Then put the rest of the exiled cards into your hand.",
)

RUN_AWAY_TOGETHER = make_instant(
    name="Run Away Together",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Choose two target creatures controlled by different players. Return those creatures to their owners' hands.",
    resolve=run_away_together_resolve,
)

SEASON_OF_WEAVING = make_sorcery(
    name="Season of Weaving",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Choose up to five {P} worth of modes. You may choose the same mode more than once.\n{P} — Draw a card.\n{P}{P} — Choose an artifact or creature you control. Create a token that's a copy of it.\n{P}{P}{P} — Return each nonland, nontoken permanent to its owner's hand.",
)

SHORE_UP = make_instant(
    name="Shore Up",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature you control gets +1/+1 and gains hexproof until end of turn. Untap it. (It can't be the target of spells or abilities your opponents control.)",
    resolve=shore_up_resolve,
)

SHORELINE_LOOTER = make_creature(
    name="Shoreline Looter",
    power=1, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Rat", "Rogue"},
    text="This creature can't be blocked.\nThreshold — Whenever this creature deals combat damage to a player, draw a card. Then discard a card unless there are seven or more cards in your graveyard.",
    setup_interceptors=shoreline_looter_setup,
)

SKYSKIPPER_DUO = make_creature(
    name="Skyskipper Duo",
    power=3, toughness=3,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Frog"},
    text="Flying\nWhen this creature enters, exile up to one other target creature you control. Return it to the battlefield under its owner's control at the beginning of the next end step.",
    setup_interceptors=skyskipper_duo_setup
)

SPELLGYRE = make_instant(
    name="Spellgyre",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Choose one —\n• Counter target spell.\n• Surveil 2, then draw two cards. (To surveil 2, look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
)

SPLASH_LASHER = make_creature(
    name="Splash Lasher",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Frog", "Wizard"},
    text="Offspring {1}{U} (You may pay an additional {1}{U} as you cast this spell. If you do, when this creature enters, create a 1/1 token copy of it.)\nWhen this creature enters, tap up to one target creature and put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
    setup_interceptors=splash_lasher_setup
)

SPLASH_PORTAL = make_sorcery(
    name="Splash Portal",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Exile target creature you control, then return it to the battlefield under its owner's control. If that creature is a Bird, Frog, Otter, or Rat, draw a card.",
)

STORMCHASERS_TALENT = make_enchantment(
    name="Stormchaser's Talent",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="(Gain the next level as a sorcery to add its ability.)\nWhen this Class enters, create a 1/1 blue and red Otter creature token with prowess.\n{3}{U}: Level 2\nWhen this Class becomes level 2, return target instant or sorcery card from your graveyard to your hand.\n{5}{U}: Level 3\nWhenever you cast an instant or sorcery spell, create a 1/1 blue and red Otter creature token with prowess.",
    subtypes={"Class"},
    setup_interceptors=stormchasers_talent_setup,
)

SUGAR_COAT = make_enchantment(
    name="Sugar Coat",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Flash\nEnchant creature or Food\nEnchanted permanent is a colorless Food artifact with \"{2}, {T}, Sacrifice this artifact: You gain 3 life\" and loses all other card types and abilities.",
    subtypes={"Aura"},
    setup_interceptors=sugar_coat_setup,
)

THOUGHT_SHUCKER = make_creature(
    name="Thought Shucker",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Rat", "Rogue"},
    text="Threshold — {1}{U}: Put a +1/+1 counter on this creature and draw a card. Activate only if there are seven or more cards in your graveyard and only once.",
    setup_interceptors=thought_shucker_setup,
)

THUNDERTRAP_TRAINER = make_creature(
    name="Thundertrap Trainer",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Otter", "Wizard"},
    text="Offspring {4} (You may pay an additional {4} as you cast this spell. If you do, when this creature enters, create a 1/1 token copy of it.)\nWhen this creature enters, look at the top four cards of your library. You may reveal a noncreature, nonland card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
    setup_interceptors=thundertrap_trainer_setup,
)

VALLEY_FLOODCALLER = make_creature(
    name="Valley Floodcaller",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Otter", "Wizard"},
    text="Flash\nYou may cast noncreature spells as though they had flash.\nWhenever you cast a noncreature spell, Birds, Frogs, Otters, and Rats you control get +1/+1 until end of turn. Untap them.",
    setup_interceptors=valley_floodcaller_setup,
)

WATERSPOUT_WARDEN = make_creature(
    name="Waterspout Warden",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Frog", "Soldier"},
    text="Whenever this creature attacks, if another creature entered the battlefield under your control this turn, this creature gains flying until end of turn.",
    setup_interceptors=waterspout_warden_setup,
)

WISHING_WELL = make_artifact(
    name="Wishing Well",
    mana_cost="{3}{U}",
    text="{T}: Put a coin counter on this artifact. When you do, you may cast target instant or sorcery card with mana value equal to the number of coin counters on this artifact from your graveyard without paying its mana cost. If that spell would be put into your graveyard, exile it instead. Activate only as a sorcery.",
    setup_interceptors=wishing_well_setup,
)

AGATEBLADE_ASSASSIN = make_creature(
    name="Agate-Blade Assassin",
    power=1, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Lizard"},
    text="Whenever this creature attacks, defending player loses 1 life and you gain 1 life.",
    setup_interceptors=agateblade_assassin_setup
)

BANDITS_TALENT = make_enchantment(
    name="Bandit's Talent",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="(Gain the next level as a sorcery to add its ability.)\nWhen this Class enters, each opponent discards two cards unless they discard a nonland card.\n{B}: Level 2\nAt the beginning of each opponent's upkeep, if that player has one or fewer cards in hand, they lose 2 life.\n{3}{B}: Level 3\nAt the beginning of your draw step, draw an additional card for each opponent who has one or fewer cards in hand.",
    subtypes={"Class"},
    setup_interceptors=bandits_talent_setup,
)

BONEBIND_ORATOR = make_creature(
    name="Bonebind Orator",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Bard", "Squirrel", "Warlock"},
    text="{3}{B}, Exile this card from your graveyard: Return another target creature card from your graveyard to your hand.",
    setup_interceptors=bonebind_orator_setup,
)

BONECACHE_OVERSEER = make_creature(
    name="Bonecache Overseer",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Squirrel", "Warlock"},
    text="{T}, Pay 1 life: Draw a card. Activate only if three or more cards left your graveyard this turn or if you've sacrificed a Food this turn.",
)

COILING_REBIRTH = make_sorcery(
    name="Coiling Rebirth",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Gift a card (You may promise an opponent a gift as you cast this spell. If you do, they draw a card before its other effects.)\nReturn target creature card from your graveyard to the battlefield. Then if the gift was promised and that creature isn't legendary, create a token that's a copy of that creature, except it's 1/1.",
)

CONSUMED_BY_GREED = make_instant(
    name="Consumed by Greed",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Gift a card (You may promise an opponent a gift as you cast this spell. If you do, they draw a card before its other effects.)\nTarget opponent sacrifices a creature with the greatest power among creatures they control. If the gift was promised, return target creature card from your graveyard to your hand.",
)

CRUELCLAWS_HEIST = make_sorcery(
    name="Cruelclaw's Heist",
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    text="Gift a card (You may promise an opponent a gift as you cast this spell. If you do, they draw a card before its other effects.)\nTarget opponent reveals their hand. You choose a nonland card from it. Exile that card. If the gift was promised, you may cast that card for as long as it remains exiled, and mana of any type can be spent to cast it.",
)

DAGGERFANG_DUO = make_creature(
    name="Daggerfang Duo",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Rat", "Squirrel"},
    text="Deathtouch\nWhen this creature enters, you may mill two cards. (You may put the top two cards of your library into your graveyard.)",
    setup_interceptors=daggerfang_duo_setup
)

DARKSTAR_AUGUR = make_creature(
    name="Darkstar Augur",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "Warlock"},
    text="Offspring {B} (You may pay an additional {B} as you cast this spell. If you do, when this creature enters, create a 1/1 token copy of it.)\nFlying\nAt the beginning of your upkeep, reveal the top card of your library and put that card into your hand. You lose life equal to its mana value.",
    setup_interceptors=darkstar_augur_setup
)

DIRESIGHT = make_sorcery(
    name="Diresight",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Surveil 2, then draw two cards. You lose 2 life. (To surveil 2, look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
)

DOWNWIND_AMBUSHER = make_creature(
    name="Downwind Ambusher",
    power=4, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Skunk"},
    text="Flash\nWhen this creature enters, choose one —\n• Target creature an opponent controls gets -1/-1 until end of turn.\n• Destroy target creature an opponent controls that was dealt damage this turn.",
    setup_interceptors=downwind_ambusher_etb_setup
)

EARLY_WINTER = make_instant(
    name="Early Winter",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="Choose one —\n• Exile target creature.\n• Target opponent exiles an enchantment they control.",
    resolve=early_winter_resolve,
)

FEED_THE_CYCLE = make_instant(
    name="Feed the Cycle",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, forage or pay {B}. (To forage, exile three cards from your graveyard or sacrifice a Food.)\nDestroy target creature or planeswalker.",
    resolve=feed_the_cycle_resolve,
)

FELL = make_sorcery(
    name="Fell",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Destroy target creature.",
    resolve=fell_resolve,
)

GLIDEDIVE_DUO = make_creature(
    name="Glidedive Duo",
    power=3, toughness=3,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "Lizard"},
    text="Flying\nWhen this creature enters, each opponent loses 2 life and you gain 2 life.",
    setup_interceptors=glidedive_duo_setup
)

HAZELS_NOCTURNE = make_instant(
    name="Hazel's Nocturne",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Return up to two target creature cards from your graveyard to your hand. Each opponent loses 2 life and you gain 2 life.",
)

HUSKBURSTER_SWARM = make_creature(
    name="Huskburster Swarm",
    power=6, toughness=6,
    mana_cost="{7}{B}",
    colors={Color.BLACK},
    subtypes={"Elemental", "Insect"},
    text="This spell costs {1} less to cast for each creature card you own in exile and in your graveyard.\nMenace, deathtouch",
    setup_interceptors=huskburster_swarm_setup,
)

IRIDESCENT_VINELASHER = make_creature(
    name="Iridescent Vinelasher",
    power=1, toughness=2,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Lizard"},
    text="Offspring {2} (You may pay an additional {2} as you cast this spell. If you do, when this creature enters, create a 1/1 token copy of it.)\nLandfall — Whenever a land you control enters, this creature deals 1 damage to target opponent.",
    setup_interceptors=iridescent_vinelasher_setup,
)

MAHA_ITS_FEATHERS_NIGHT = make_creature(
    name="Maha, Its Feathers Night",
    power=6, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Bird", "Elemental"},
    supertypes={"Legendary"},
    text="Flying, trample\nWard—Discard a card.\nCreatures your opponents control have base toughness 1.",
    setup_interceptors=maha_its_feathers_night_setup,
)

MOONSTONE_HARBINGER = make_creature(
    name="Moonstone Harbinger",
    power=1, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "Warrior"},
    text="Flying, deathtouch\nWhenever you gain or lose life during your turn, Bats you control get +1/+0 and gain deathtouch until end of turn. This ability triggers only once each turn.",
    setup_interceptors=moonstone_harbinger_setup,
)

NOCTURNAL_HUNGER = make_instant(
    name="Nocturnal Hunger",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Gift a Food (You may promise an opponent a gift as you cast this spell. If you do, they create a Food token before its other effects. It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\nDestroy target creature. If the gift wasn't promised, you lose 2 life.",
    resolve=nocturnal_hunger_resolve,
)

OSTEOMANCER_ADEPT = make_creature(
    name="Osteomancer Adept",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Squirrel", "Warlock"},
    text="Deathtouch\n{T}: Until end of turn, you may cast creature spells from your graveyard by foraging in addition to paying their other costs. If you cast a spell this way, that creature enters with a finality counter on it. (To forage, exile three cards from your graveyard or sacrifice a Food. If a creature with a finality counter on it would die, exile it instead.)",
)

PERSISTENT_MARSHSTALKER = make_creature(
    name="Persistent Marshstalker",
    power=3, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Berserker", "Rat"},
    text="This creature gets +1/+0 for each other Rat you control.\nThreshold — Whenever you attack with one or more Rats, if there are seven or more cards in your graveyard, you may pay {2}{B}. If you do, return this card from your graveyard to the battlefield tapped and attacking.",
    setup_interceptors=persistent_marshstalker_setup,
)

PSYCHIC_WHORL = make_sorcery(
    name="Psychic Whorl",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Target opponent discards two cards. Then if you control a Rat, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
)

RAVINE_RAIDER = make_creature(
    name="Ravine Raider",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Lizard", "Rogue"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\n{1}{B}: This creature gets +1/+1 until end of turn.",
    setup_interceptors=ravine_raider_setup,
)

ROTTENMOUTH_VIPER = make_creature(
    name="Rottenmouth Viper",
    power=6, toughness=6,
    mana_cost="{5}{B}",
    colors={Color.BLACK},
    subtypes={"Elemental", "Snake"},
    text="As an additional cost to cast this spell, you may sacrifice any number of nonland permanents. This spell costs {1} less to cast for each permanent sacrificed this way.\nWhenever this creature enters or attacks, put a blight counter on it. Then for each blight counter on it, each opponent loses 4 life unless that player sacrifices a nonland permanent of their choice or discards a card.",
    setup_interceptors=rottenmouth_viper_setup,
)

RUTHLESS_NEGOTIATION = make_sorcery(
    name="Ruthless Negotiation",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target opponent exiles a card from their hand. If this spell was cast from a graveyard, draw a card.\nFlashback {4}{B} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

SAVOR = make_instant(
    name="Savor",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn. Create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")",
    resolve=savor_resolve,
)

SCALES_OF_SHALE = make_instant(
    name="Scales of Shale",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Affinity for Lizards (This spell costs {1} less to cast for each Lizard you control.)\nTarget creature gets +2/+0 and gains lifelink and indestructible until end of turn.",
)

SCAVENGERS_TALENT = make_enchantment(
    name="Scavenger's Talent",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="(Gain the next level as a sorcery to add its ability.)\nWhenever one or more creatures you control die, create a Food token. This ability triggers only once each turn.\n{1}{B}: Level 2\nWhenever you sacrifice a permanent, target player mills two cards.\n{2}{B}: Level 3\nAt the beginning of your end step, you may sacrifice three other nonland permanents. If you do, return a creature card from your graveyard to the battlefield with a finality counter on it.",
    subtypes={"Class"},
    setup_interceptors=scavengers_talent_setup,
)

SEASON_OF_LOSS = make_sorcery(
    name="Season of Loss",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Choose up to five {P} worth of modes. You may choose the same mode more than once.\n{P} — Each player sacrifices a creature of their choice.\n{P}{P} — Draw a card for each creature that died under your control this turn.\n{P}{P}{P} — Each opponent loses X life, where X is the number of creature cards in your graveyard.",
)

SINISTER_MONOLITH = make_artifact(
    name="Sinister Monolith",
    mana_cost="{3}{B}",
    text="At the beginning of combat on your turn, each opponent loses 1 life and you gain 1 life.\n{T}, Pay 2 life, Sacrifice this artifact: Draw two cards. Activate only as a sorcery.",
    setup_interceptors=sinister_monolith_setup,
)

STARGAZE = make_sorcery(
    name="Stargaze",
    mana_cost="{X}{B}{B}",
    colors={Color.BLACK},
    text="Look at twice X cards from the top of your library. Put X cards from among them into your hand and the rest into your graveyard. You lose X life.",
)

STARLIT_SOOTHSAYER = make_creature(
    name="Starlit Soothsayer",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "Cleric"},
    text="Flying\nAt the beginning of your end step, if you gained or lost life this turn, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    setup_interceptors=starlit_soothsayer_setup,
)

STARSCAPE_CLERIC = make_creature(
    name="Starscape Cleric",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Bat", "Cleric"},
    text="Offspring {2}{B} (You may pay an additional {2}{B} as you cast this spell. If you do, when this creature enters, create a 1/1 token copy of it.)\nFlying\nThis creature can't block.\nWhenever you gain life, each opponent loses 1 life.",
    setup_interceptors=starscape_cleric_setup
)

THORNPLATE_INTIMIDATOR = make_creature(
    name="Thornplate Intimidator",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Rat", "Rogue"},
    text="Offspring {3} (You may pay an additional {3} as you cast this spell. If you do, when this creature enters, create a 1/1 token copy of it.)\nWhen this creature enters, target opponent loses 3 life unless they sacrifice a nonland permanent of their choice or discard a card.",
    setup_interceptors=thornplate_intimidator_setup
)

THOUGHTSTALKER_WARLOCK = make_creature(
    name="Thought-Stalker Warlock",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Lizard", "Warlock"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhen this creature enters, choose target opponent. If they lost life this turn, they reveal their hand, you choose a nonland card from it, and they discard that card. Otherwise, they discard a card.",
    setup_interceptors=thoughtstalker_warlock_setup,
)

VALLEY_ROTCALLER = make_creature(
    name="Valley Rotcaller",
    power=1, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Squirrel", "Warlock"},
    text="Menace\nWhenever this creature attacks, each opponent loses X life and you gain X life, where X is the number of other Squirrels, Bats, Lizards, and Rats you control.",
    setup_interceptors=valley_rotcaller_setup
)

WICK_THE_WHORLED_MIND = make_creature(
    name="Wick, the Whorled Mind",
    power=2, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Rat", "Warlock"},
    supertypes={"Legendary"},
    text="Whenever Wick or another Rat you control enters, create a 1/1 black Snail creature token if you don't control a Snail. Otherwise, put a +1/+1 counter on a Snail you control.\n{U}{B}{R}, Sacrifice a Snail: Wick deals damage equal to the sacrificed creature's power to each opponent. Then draw cards equal to the sacrificed creature's power.",
    setup_interceptors=wick_the_whorled_mind_setup
)

WICKS_PATROL = make_creature(
    name="Wick's Patrol",
    power=5, toughness=3,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Rat", "Warlock"},
    text="When this creature enters, mill three cards. When you do, target creature an opponent controls gets -X/-X until end of turn, where X is the greatest mana value among cards in your graveyard.",
    setup_interceptors=wicks_patrol_setup,
)

AGATE_ASSAULT = make_sorcery(
    name="Agate Assault",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Choose one —\n• Agate Assault deals 4 damage to target creature. If that creature would die this turn, exile it instead.\n• Exile target artifact.",
    resolve=agate_assault_resolve,
)

ALANIAS_PATHMAKER = make_creature(
    name="Alania's Pathmaker",
    power=4, toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Otter", "Wizard"},
    text="When this creature enters, exile the top card of your library. Until the end of your next turn, you may play that card.",
    setup_interceptors=alanias_pathmaker_setup
)

ARTISTS_TALENT = make_enchantment(
    name="Artist's Talent",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="(Gain the next level as a sorcery to add its ability.)\nWhenever you cast a noncreature spell, you may discard a card. If you do, draw a card.\n{2}{R}: Level 2\nNoncreature spells you cast cost {1} less to cast.\n{2}{R}: Level 3\nIf a source you control would deal noncombat damage to an opponent or a permanent an opponent controls, it deals that much damage plus 2 instead.",
    subtypes={"Class"},
    setup_interceptors=artists_talent_setup,
)

BLACKSMITHS_TALENT = make_enchantment(
    name="Blacksmith's Talent",
    mana_cost="{R}",
    colors={Color.RED},
    text="(Gain the next level as a sorcery to add its ability.)\nWhen this Class enters, create a colorless Equipment artifact token named Sword with \"Equipped creature gets +1/+1\" and equip {2}.\n{2}{R}: Level 2\nAt the beginning of combat on your turn, attach target Equipment you control to up to one target creature you control.\n{3}{R}: Level 3\nDuring your turn, equipped creatures you control have double strike and haste.",
    subtypes={"Class"},
    setup_interceptors=blacksmiths_talent_setup,
)

BLOOMING_BLAST = make_instant(
    name="Blooming Blast",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Gift a Treasure (You may promise an opponent a gift as you cast this spell. If you do, they create a Treasure token before its other effects. It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nBlooming Blast deals 2 damage to target creature. If the gift was promised, Blooming Blast also deals 3 damage to that creature's controller.",
    resolve=blooming_blast_resolve,
)

BRAMBLEGUARD_CAPTAIN = make_creature(
    name="Brambleguard Captain",
    power=2, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Mouse", "Soldier"},
    text="At the beginning of combat on your turn, target creature you control gets +X/+0 until end of turn, where X is this creature's power.",
    setup_interceptors=brambleguard_captain_setup,
)

BRAZEN_COLLECTOR = make_creature(
    name="Brazen Collector",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Raccoon", "Rogue"},
    text="First strike\nWhenever this creature attacks, add {R}. Until end of turn, you don't lose this mana as steps and phases end.",
    setup_interceptors=brazen_collector_setup
)

BYWAY_BARTERER = make_creature(
    name="Byway Barterer",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Raccoon", "Rogue"},
    text="Menace\nWhenever you expend 4, you may discard your hand. If you do, draw two cards. (You expend 4 as you spend your fourth total mana to cast spells during a turn.)",
    setup_interceptors=byway_barterer_setup,
)

CONDUCT_ELECTRICITY = make_instant(
    name="Conduct Electricity",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="Conduct Electricity deals 6 damage to target creature and 2 damage to up to one target creature token.",
    resolve=conduct_electricity_resolve,
)

CORUSCATION_MAGE = make_creature(
    name="Coruscation Mage",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Otter", "Wizard"},
    text="Offspring {2} (You may pay an additional {2} as you cast this spell. If you do, when this creature enters, create a 1/1 token copy of it.)\nWhenever you cast a noncreature spell, this creature deals 1 damage to each opponent.",
    setup_interceptors=coruscation_mage_setup
)

DRAGONHAWK_FATES_TEMPEST = make_creature(
    name="Dragonhawk, Fate's Tempest",
    power=5, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Bird", "Dragon"},
    supertypes={"Legendary"},
    text="Flying\nWhenever Dragonhawk enters or attacks, exile the top X cards of your library, where X is the number of creatures you control with power 4 or greater. You may play those cards until your next end step. At the beginning of your next end step, Dragonhawk deals 2 damage to each opponent for each of those cards that are still exiled.",
    setup_interceptors=dragonhawk_fates_tempest_setup,
)

EMBERHEART_CHALLENGER = make_creature(
    name="Emberheart Challenger",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Mouse", "Warrior"},
    text="Haste\nProwess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nValiant — Whenever this creature becomes the target of a spell or ability you control for the first time each turn, exile the top card of your library. Until end of turn, you may play that card.",
    setup_interceptors=emberheart_challenger_setup,
)

FESTIVAL_OF_EMBERS = make_enchantment(
    name="Festival of Embers",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="During your turn, you may cast instant and sorcery spells from your graveyard by paying 1 life in addition to their other costs.\nIf a card or token would be put into your graveyard from anywhere, exile it instead.\n{1}{R}: Sacrifice this enchantment.",
    setup_interceptors=festival_of_embers_setup,
)

FLAMECACHE_GECKO = make_creature(
    name="Flamecache Gecko",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Warlock"},
    text="When this creature enters, if an opponent lost life this turn, add {B}{R}.\n{1}{R}, Discard a card: Draw a card.",
    setup_interceptors=flamecache_gecko_setup,
)

FRILLED_SPARKSHOOTER = make_creature(
    name="Frilled Sparkshooter",
    power=3, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Archer", "Lizard"},
    text="Menace, reach\nThis creature enters with a +1/+1 counter on it if an opponent lost life this turn.",
    setup_interceptors=frilled_sparkshooter_setup,
)

HARNESSER_OF_STORMS = make_creature(
    name="Harnesser of Storms",
    power=1, toughness=4,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Otter", "Wizard"},
    text="Whenever you cast a noncreature or Otter spell, you may exile the top card of your library. Until end of turn, you may play that card. This ability triggers only once each turn.",
    setup_interceptors=harnesser_of_storms_setup,
)

HEARTFIRE_HERO = make_creature(
    name="Heartfire Hero",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Mouse", "Soldier"},
    text="Valiant — Whenever this creature becomes the target of a spell or ability you control for the first time each turn, put a +1/+1 counter on it.\nWhen this creature dies, it deals damage equal to its power to each opponent.",
    setup_interceptors=heartfire_hero_setup
)

AHEARTFIRE_HERO = make_creature(
    name="A-Heartfire Hero",
    power=0, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Mouse", "Soldier"},
    text="Valiant — Whenever Heartfire Hero becomes the target of a spell or ability you control for the first time each turn, put a +1/+1 counter on it.\nWhen Heartfire Hero dies, it deals damage equal to its power to each opponent.",
    setup_interceptors=aheartfire_hero_setup,
)

HEARTHBORN_BATTLER = make_creature(
    name="Hearthborn Battler",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Warlock"},
    text="Haste\nWhenever a player casts their second spell each turn, this creature deals 2 damage to target opponent.",
    setup_interceptors=hearthborn_battler_setup,
)

HIRED_CLAW = make_creature(
    name="Hired Claw",
    power=1, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Mercenary"},
    text="Whenever you attack with one or more Lizards, this creature deals 1 damage to target opponent.\n{1}{R}: Put a +1/+1 counter on this creature. Activate only if an opponent lost life this turn and only once each turn.",
    setup_interceptors=hired_claw_setup,
)

HOARDERS_OVERFLOW = make_enchantment(
    name="Hoarder's Overflow",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="When this enchantment enters and whenever you expend 4, put a stash counter on it. (You expend 4 as you spend your fourth total mana to cast spells during a turn.)\n{1}{R}, Sacrifice this enchantment: Discard your hand, then draw cards equal to the number of stash counters on this enchantment.",
    setup_interceptors=hoarders_overflow_setup,
)

KINDLESPARK_DUO = make_creature(
    name="Kindlespark Duo",
    power=1, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Otter"},
    text="{T}: This creature deals 1 damage to target opponent.\nWhenever you cast a noncreature spell, untap this creature.",
    setup_interceptors=kindlespark_duo_setup,
)

MANIFOLD_MOUSE = make_creature(
    name="Manifold Mouse",
    power=1, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Mouse", "Soldier"},
    text="Offspring {2} (You may pay an additional {2} as you cast this spell. If you do, when this creature enters, create a 1/1 token copy of it.)\nAt the beginning of combat on your turn, target Mouse you control gains your choice of double strike or trample until end of turn.",
    setup_interceptors=manifold_mouse_setup,
)

MIGHT_OF_THE_MEEK = make_instant(
    name="Might of the Meek",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gains trample until end of turn. It also gets +1/+0 until end of turn if you control a Mouse.\nDraw a card.",
    resolve=might_of_the_meek_resolve,
)

PLAYFUL_SHOVE = make_sorcery(
    name="Playful Shove",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Playful Shove deals 1 damage to any target.\nDraw a card.",
    resolve=playful_shove_resolve,
)

QUAKETUSK_BOAR = make_creature(
    name="Quaketusk Boar",
    power=5, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Boar", "Elemental"},
    text="Reach, trample, haste",
)

RABID_GNAW = make_instant(
    name="Rabid Gnaw",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature you control gets +1/+0 until end of turn. Then it deals damage equal to its power to target creature you don't control.",
    resolve=rabid_gnaw_resolve,
)

RACCOON_RALLIER = make_creature(
    name="Raccoon Rallier",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Bard", "Raccoon"},
    text="{T}: Target creature you control gains haste until end of turn. Activate only as a sorcery.",
    setup_interceptors=raccoon_rallier_setup,
)

REPTILIAN_RECRUITER = make_creature(
    name="Reptilian Recruiter",
    power=4, toughness=2,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Warrior"},
    text="Trample\nWhen this creature enters, choose target creature. If that creature's power is 2 or less or if you control another Lizard, gain control of that creature until end of turn, untap it, and it gains haste until end of turn.",
    setup_interceptors=reptilian_recruiter_setup,
)

ROUGHSHOD_DUO = make_creature(
    name="Roughshod Duo",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Mouse", "Raccoon"},
    text="Trample\nWhenever you expend 4, target creature you control gets +1/+1 and gains trample until end of turn. (You expend 4 as you spend your fourth total mana to cast spells during a turn.)",
    setup_interceptors=roughshod_duo_setup,
)

SAZACAPS_BREW = make_instant(
    name="Sazacap's Brew",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Gift a tapped Fish (You may promise an opponent a gift as you cast this spell. If you do, they create a tapped 1/1 blue Fish creature token before its other effects.)\nAs an additional cost to cast this spell, discard a card.\nTarget player draws two cards. If the gift was promised, target creature you control gets +2/+0 until end of turn.",
)

SEASON_OF_THE_BOLD = make_sorcery(
    name="Season of the Bold",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Choose up to five {P} worth of modes. You may choose the same mode more than once.\n{P} — Create a tapped Treasure token.\n{P}{P} — Exile the top two cards of your library. Until the end of your next turn, you may play them.\n{P}{P}{P} — Until the end of your next turn, whenever you cast a spell, Season of the Bold deals 2 damage to up to one target creature.",
)

STEAMPATH_CHARGER = make_creature(
    name="Steampath Charger",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Warlock"},
    text="Offspring {2} (You may pay an additional {2} as you cast this spell. If you do, when this creature enters, create a 1/1 token copy of it.)\nWhen this creature dies, it deals 1 damage to target player.",
    setup_interceptors=steampath_charger_setup
)

STORMSPLITTER = make_creature(
    name="Stormsplitter",
    power=1, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Otter", "Wizard"},
    text="Haste\nWhenever you cast an instant or sorcery spell, create a token that's a copy of this creature. Exile that token at the beginning of the next end step.",
    setup_interceptors=stormsplitter_setup,
)

SUNSPINE_LYNX = make_creature(
    name="Sunspine Lynx",
    power=5, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Cat", "Elemental"},
    text="Players can't gain life.\nDamage can't be prevented.\nWhen this creature enters, it deals damage to each player equal to the number of nonbasic lands that player controls.",
    setup_interceptors=sunspine_lynx_setup,
)

TAKE_OUT_THE_TRASH = make_instant(
    name="Take Out the Trash",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Take Out the Trash deals 3 damage to target creature or planeswalker. If you control a Raccoon, you may discard a card. If you do, draw a card.",
    resolve=take_out_the_trash_resolve,
)

TEAPOT_SLINGER = make_creature(
    name="Teapot Slinger",
    power=3, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Raccoon", "Warrior"},
    text="Menace\nWhenever you expend 4, this creature deals 2 damage to each opponent. (You expend 4 as you spend your fourth total mana to cast spells during a turn.)",
    setup_interceptors=teapot_slinger_setup,
)

VALLEY_FLAMECALLER = make_creature(
    name="Valley Flamecaller",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Warlock"},
    text="If a Lizard, Mouse, Otter, or Raccoon you control would deal damage to a permanent or player, it deals that much damage plus 1 instead.",
    setup_interceptors=valley_flamecaller_setup
)

VALLEY_RALLY = make_instant(
    name="Valley Rally",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Gift a Food (You may promise an opponent a gift as you cast this spell. If you do, they create a Food token before its other effects. It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\nCreatures you control get +2/+0 until end of turn. If the gift was promised, target creature you control gains first strike until end of turn.",
)

WAR_SQUEAK = make_enchantment(
    name="War Squeak",
    mana_cost="{R}",
    colors={Color.RED},
    text="Enchant creature\nWhen this Aura enters, target creature an opponent controls can't block this turn.\nEnchanted creature gets +1/+1 and has haste.",
    subtypes={"Aura"},
    setup_interceptors=war_squeak_setup,
)

WHISKERQUILL_SCRIBE = make_creature(
    name="Whiskerquill Scribe",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Citizen", "Mouse"},
    text="Valiant — Whenever this creature becomes the target of a spell or ability you control for the first time each turn, you may discard a card. If you do, draw a card.",
    setup_interceptors=whiskerquill_scribe_setup,
)

WILDFIRE_HOWL = make_sorcery(
    name="Wildfire Howl",
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    text="Gift a card (You may promise an opponent a gift as you cast this spell. If you do, they draw a card before its other effects.)\nWildfire Howl deals 2 damage to each creature. If the gift was promised, instead Wildfire Howl deals 1 damage to any target and 2 damage to each creature.",
)

BAKERSBANE_DUO = make_creature(
    name="Bakersbane Duo",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Raccoon", "Squirrel"},
    text="When this creature enters, create a Food token.\nWhenever you expend 4, this creature gets +1/+1 until end of turn. (You expend 4 as you spend your fourth total mana to cast spells during a turn.)",
    setup_interceptors=bakersbane_duo_setup
)

BARKKNUCKLE_BOXER = make_creature(
    name="Bark-Knuckle Boxer",
    power=3, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Berserker", "Raccoon"},
    text="Whenever you expend 4, this creature gains indestructible until end of turn. (You expend 4 as you spend your fourth total mana to cast spells during a turn.)",
    setup_interceptors=barkknuckle_boxer_setup,
)

BRAMBLEGUARD_VETERAN = make_creature(
    name="Brambleguard Veteran",
    power=3, toughness=4,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Raccoon", "Warrior"},
    text="Whenever you expend 4, Raccoons you control get +1/+1 and gain vigilance until end of turn. (You expend 4 as you spend your fourth total mana to cast spells during a turn.)",
    setup_interceptors=brambleguard_veteran_setup,
)

BUSHY_BODYGUARD = make_creature(
    name="Bushy Bodyguard",
    power=2, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Squirrel", "Warrior"},
    text="Offspring {2} (You may pay an additional {2} as you cast this spell. If you do, when this creature enters, create a 1/1 token copy of it.)\nWhen this creature enters, you may forage. If you do, put two +1/+1 counters on it. (To forage, exile three cards from your graveyard or sacrifice a Food.)",
    setup_interceptors=bushy_bodyguard_setup,
)

CACHE_GRAB = make_instant(
    name="Cache Grab",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Mill four cards. You may put a permanent card from among the cards milled this way into your hand. If you control a Squirrel or returned a Squirrel card to your hand this way, create a Food token. (To mill four cards, put the top four cards of your library into your graveyard. A Food token is an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")",
)

CLIFFTOP_LOOKOUT = make_creature(
    name="Clifftop Lookout",
    power=1, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Frog", "Scout"},
    text="Reach\nWhen this creature enters, reveal cards from the top of your library until you reveal a land card. Put that card onto the battlefield tapped and the rest on the bottom of your library in a random order.",
    setup_interceptors=clifftop_lookout_setup
)

CURIOUS_FORAGER = make_creature(
    name="Curious Forager",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Squirrel"},
    text="When this creature enters, you may forage. When you do, return target permanent card from your graveyard to your hand. (To forage, exile three cards from your graveyard or sacrifice a Food.)",
    setup_interceptors=curious_forager_setup,
)

DRUID_OF_THE_SPADE = make_creature(
    name="Druid of the Spade",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Rabbit"},
    text="As long as you control a token, this creature gets +2/+0 and has trample.",
    setup_interceptors=druid_of_the_spade_setup,
)

FECUND_GREENSHELL = make_creature(
    name="Fecund Greenshell",
    power=4, toughness=6,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental", "Turtle"},
    text="Reach\nAs long as you control ten or more lands, creatures you control get +2/+2.\nWhenever this creature or another creature you control with toughness greater than its power enters, look at the top card of your library. If it's a land card, you may put it onto the battlefield tapped. Otherwise, put it into your hand.",
    setup_interceptors=fecund_greenshell_setup,
)

FOR_THE_COMMON_GOOD = make_sorcery(
    name="For the Common Good",
    mana_cost="{X}{X}{G}",
    colors={Color.GREEN},
    text="Create X tokens that are copies of target token you control. Then tokens you control gain indestructible until your next turn. You gain 1 life for each token you control.",
)

GALEWIND_MOOSE = make_creature(
    name="Galewind Moose",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental", "Elk"},
    text="Flash\nVigilance, reach, trample",
)

HAZARDROOT_HERBALIST = make_creature(
    name="Hazardroot Herbalist",
    power=1, toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Rabbit"},
    text="Whenever you attack, target creature you control gets +1/+0 until end of turn. If that creature is a token, it also gains deathtouch until end of turn.",
    setup_interceptors=hazardroot_herbalist_setup,
)

HEAPED_HARVEST = make_artifact(
    name="Heaped Harvest",
    mana_cost="{2}{G}",
    text="When this artifact enters and when you sacrifice it, you may search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\n{2}, {T}, Sacrifice this artifact: You gain 3 life.",
    subtypes={"Food"},
    setup_interceptors=heaped_harvest_setup,
)

HIGH_STRIDE = make_instant(
    name="High Stride",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +1/+3 and gains reach until end of turn. Untap it.",
)

HIVESPINE_WOLVERINE = make_creature(
    name="Hivespine Wolverine",
    power=5, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental", "Wolverine"},
    text="When this creature enters, choose one —\n• Put a +1/+1 counter on target creature you control.\n• This creature fights target creature token.\n• Destroy target artifact or enchantment.",
    setup_interceptors=hivespine_wolverine_modal_setup
)

HONORED_DREYLEADER = make_creature(
    name="Honored Dreyleader",
    power=1, toughness=1,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Squirrel", "Warrior"},
    text="Trample\nWhen this creature enters, put a +1/+1 counter on it for each other Squirrel and/or Food you control.\nWhenever another Squirrel or Food you control enters, put a +1/+1 counter on this creature.",
    setup_interceptors=honored_dreyleader_setup
)

HUNTERS_TALENT = make_enchantment(
    name="Hunter's Talent",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="(Gain the next level as a sorcery to add its ability.)\nWhen this Class enters, target creature you control deals damage equal to its power to target creature you don't control.\n{1}{G}: Level 2\nWhenever you attack, target attacking creature gets +1/+0 and gains trample until end of turn.\n{3}{G}: Level 3\nAt the beginning of your end step, if you control a creature with power 4 or greater, draw a card.",
    subtypes={"Class"},
    setup_interceptors=hunters_talent_setup,
)

INNKEEPERS_TALENT = make_enchantment(
    name="Innkeeper's Talent",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="(Gain the next level as a sorcery to add its ability.)\nAt the beginning of combat on your turn, put a +1/+1 counter on target creature you control.\n{G}: Level 2\nPermanents you control with counters on them have ward {1}.\n{3}{G}: Level 3\nIf you would put one or more counters on a permanent or player, put twice that many of each of those kinds of counters on that permanent or player instead.",
    subtypes={"Class"},
    setup_interceptors=innkeepers_talent_setup,
)

KEENEYED_CURATOR = make_creature(
    name="Keen-Eyed Curator",
    power=3, toughness=3,
    mana_cost="{G}{G}",
    colors={Color.GREEN},
    subtypes={"Raccoon", "Scout"},
    text="As long as there are four or more card types among cards exiled with this creature, it gets +4/+4 and has trample.\n{1}: Exile target card from a graveyard.",
    setup_interceptors=keeneyed_curator_setup,
)

LONGSTALK_BRAWL = make_sorcery(
    name="Longstalk Brawl",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Gift a tapped Fish (You may promise an opponent a gift as you cast this spell. If you do, they create a tapped 1/1 blue Fish creature token before its other effects.)\nChoose target creature you control and target creature you don't control. Put a +1/+1 counter on the creature you control if the gift was promised. Then those creatures fight each other.",
)

LUMRA_BELLOW_OF_THE_WOODS = make_creature(
    name="Lumra, Bellow of the Woods",
    power=0, toughness=0,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Bear", "Elemental"},
    supertypes={"Legendary"},
    text="Vigilance, reach\nLumra's power and toughness are each equal to the number of lands you control.\nWhen Lumra enters, mill four cards. Then return all land cards from your graveyard to the battlefield tapped.",
    setup_interceptors=lumra_bellow_of_the_woods_setup,
)

MISTBREATH_ELDER = make_creature(
    name="Mistbreath Elder",
    power=2, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Frog", "Warrior"},
    text="At the beginning of your upkeep, return another creature you control to its owner's hand. If you do, put a +1/+1 counter on this creature. Otherwise, you may return this creature to its owner's hand.",
    setup_interceptors=mistbreath_elder_setup,
)

OVERPROTECT = make_instant(
    name="Overprotect",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +3/+3 and gains trample, hexproof, and indestructible until end of turn.",
)

PAWPATCH_FORMATION = make_instant(
    name="Pawpatch Formation",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +X/+X until end of turn, where X is the number of creatures you control.",
    resolve=pawpatch_formation_resolve,
)

PAWPATCH_RECRUIT = make_creature(
    name="Pawpatch Recruit",
    power=2, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Rabbit", "Warrior"},
    text="Offspring {2} (You may pay an additional {2} as you cast this spell. If you do, when this creature enters, create a 1/1 token copy of it.)\nTrample\nWhenever a creature you control becomes the target of a spell or ability an opponent controls, put a +1/+1 counter on target creature you control other than that creature.",
    setup_interceptors=pawpatch_recruit_setup,
)

PEERLESS_RECYCLING = make_instant(
    name="Peerless Recycling",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Gift a card (You may promise an opponent a gift as you cast this spell. If you do, they draw a card before its other effects.)\nReturn target permanent card from your graveyard to your hand. If the gift was promised, instead return two target permanent cards from your graveyard to your hand.",
)

POLLIWALLOP = make_instant(
    name="Polliwallop",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Affinity for Frogs (This spell costs {1} less to cast for each Frog you control.)\nTarget creature you control deals damage equal to twice its power to target creature you don't control.",
)

RUSTSHIELD_RAMPAGER = make_creature(
    name="Rust-Shield Rampager",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Raccoon", "Warrior"},
    text="Offspring {2} (You may pay an additional {2} as you cast this spell. If you do, when this creature enters, create a 1/1 token copy of it.)\nThis creature can't be blocked by creatures with power 2 or less.",
    setup_interceptors=rustshield_rampager_setup,
)

SCRAPSHOOTER = make_creature(
    name="Scrapshooter",
    power=4, toughness=4,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Archer", "Raccoon"},
    text="Gift a card (You may promise an opponent a gift as you cast this spell. If you do, when it enters, they draw a card.)\nReach\nWhen this creature enters, if the gift was promised, destroy target artifact or enchantment an opponent controls.",
    setup_interceptors=scrapshooter_setup,
)

SEASON_OF_GATHERING = make_sorcery(
    name="Season of Gathering",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Choose up to five {P} worth of modes. You may choose the same mode more than once.\n{P} — Put a +1/+1 counter on a creature you control. It gains vigilance and trample until end of turn.\n{P}{P} — Choose artifact or enchantment. Destroy all permanents of the chosen type.\n{P}{P}{P} — Draw cards equal to the greatest power among creatures you control.",
)

STICKYTONGUE_SENTINEL = make_creature(
    name="Stickytongue Sentinel",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Frog", "Warrior"},
    text="Reach\nWhen this creature enters, return up to one other target permanent you control to its owner's hand.",
    setup_interceptors=stickytongue_sentinel_setup
)

STOCKING_THE_PANTRY = make_enchantment(
    name="Stocking the Pantry",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Whenever you put one or more +1/+1 counters on a creature you control, put a supply counter on this enchantment.\n{2}, Remove a supply counter from this enchantment: Draw a card.",
    setup_interceptors=stocking_the_pantry_setup,
)

SUNSHOWER_DRUID = make_creature(
    name="Sunshower Druid",
    power=0, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Frog"},
    text="When this creature enters, put a +1/+1 counter on target creature and you gain 1 life.",
    setup_interceptors=sunshower_druid_setup
)

TENDER_WILDGUIDE = make_creature(
    name="Tender Wildguide",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Possum"},
    text="Offspring {2} (You may pay an additional {2} as you cast this spell. If you do, when this creature enters, create a 1/1 token copy of it.)\n{T}: Add one mana of any color.\n{T}: Put a +1/+1 counter on this creature.",
    setup_interceptors=tender_wildguide_setup,
)

THORNVAULT_FORAGER = make_creature(
    name="Thornvault Forager",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Ranger", "Squirrel"},
    text="{T}: Add {G}.\n{T}, Forage: Add two mana in any combination of colors. (To forage, exile three cards from your graveyard or sacrifice a Food.)\n{3}{G}, {T}: Search your library for a Squirrel card, reveal it, put it into your hand, then shuffle.",
)

THREE_TREE_ROOTWEAVER = make_creature(
    name="Three Tree Rootweaver",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Mole"},
    text="{T}: Add one mana of any color.",
)

THREE_TREE_SCRIBE = make_creature(
    name="Three Tree Scribe",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Frog"},
    text="Whenever this creature or another creature you control leaves the battlefield without dying, put a +1/+1 counter on target creature you control.",
    setup_interceptors=three_tree_scribe_setup,
)

TREEGUARD_DUO = make_creature(
    name="Treeguard Duo",
    power=3, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Frog", "Rabbit"},
    text="When this creature enters, until end of turn, target creature you control gains vigilance and gets +X/+X, where X is the number of creatures you control.",
    setup_interceptors=treeguard_duo_setup
)

TREETOP_SENTRIES = make_creature(
    name="Treetop Sentries",
    power=2, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Archer", "Squirrel"},
    text="Reach\nWhen this creature enters, you may forage. If you do, draw a card. (To forage, exile three cards from your graveyard or sacrifice a Food.)",
    setup_interceptors=treetop_sentries_setup,
)

VALLEY_MIGHTCALLER = make_creature(
    name="Valley Mightcaller",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Frog", "Warrior"},
    text="Trample\nWhenever another Frog, Rabbit, Raccoon, or Squirrel you control enters, put a +1/+1 counter on this creature.",
    setup_interceptors=valley_mightcaller_setup
)

WEAR_DOWN = make_sorcery(
    name="Wear Down",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Gift a card (You may promise an opponent a gift as you cast this spell. If you do, they draw a card before its other effects.)\nDestroy target artifact or enchantment. If the gift was promised, instead destroy two target artifacts and/or enchantments.",
)

ALANIA_DIVERGENT_STORM = make_creature(
    name="Alania, Divergent Storm",
    power=3, toughness=5,
    mana_cost="{3}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Otter", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast a spell, if it's the first instant spell, the first sorcery spell, or the first Otter spell other than Alania you've cast this turn, you may have target opponent draw a card. If you do, copy that spell. You may choose new targets for the copy.",
    setup_interceptors=alania_divergent_storm_setup,
)

BAYLEN_THE_HAYMAKER = make_creature(
    name="Baylen, the Haymaker",
    power=4, toughness=3,
    mana_cost="{R}{G}{W}",
    colors={Color.GREEN, Color.RED, Color.WHITE},
    subtypes={"Rabbit", "Warrior"},
    supertypes={"Legendary"},
    text="Tap two untapped tokens you control: Add one mana of any color.\nTap three untapped tokens you control: Draw a card.\nTap four untapped tokens you control: Put three +1/+1 counters on Baylen. It gains trample until end of turn.",
    setup_interceptors=baylen_the_haymaker_setup,
)

BURROWGUARD_MENTOR = make_creature(
    name="Burrowguard Mentor",
    power=0, toughness=0,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Rabbit", "Soldier"},
    text="Trample\nBurrowguard Mentor's power and toughness are each equal to the number of creatures you control.",
    setup_interceptors=burrowguard_mentor_setup,
)

CAMELLIA_THE_SEEDMISER = make_creature(
    name="Camellia, the Seedmiser",
    power=3, toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Squirrel", "Warlock"},
    supertypes={"Legendary"},
    text="Menace\nOther Squirrels you control have menace.\nWhenever you sacrifice one or more Foods, create a 1/1 green Squirrel creature token.\n{2}, Forage: Put a +1/+1 counter on each other Squirrel you control. (To forage, exile three cards from your graveyard or sacrifice a Food.)",
    setup_interceptors=camellia_the_seedmiser_setup
)

CINDERING_CUTTHROAT = make_creature(
    name="Cindering Cutthroat",
    power=3, toughness=2,
    mana_cost="{2}{B/R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Assassin", "Lizard"},
    text="This creature enters with a +1/+1 counter on it if an opponent lost life this turn.\n{1}{B/R}: This creature gains menace until end of turn. (It can't be blocked except by two or more creatures.)",
    setup_interceptors=cindering_cutthroat_setup,
)

CLEMENT_THE_WORRYWORT = make_creature(
    name="Clement, the Worrywort",
    power=3, toughness=3,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Druid", "Frog"},
    supertypes={"Legendary"},
    text="Vigilance\nWhenever Clement or another creature you control enters, return up to one target creature you control with lesser mana value to its owner's hand.\nFrogs you control have \"{T}: Add {G} or {U}. Spend this mana only to cast a creature spell.\"",
    setup_interceptors=clement_the_worrywort_setup,
)

CORPSEBERRY_CULTIVATOR = make_creature(
    name="Corpseberry Cultivator",
    power=2, toughness=3,
    mana_cost="{1}{B/G}{B/G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Squirrel", "Warlock"},
    text="At the beginning of combat on your turn, you may forage. (Exile three cards from your graveyard or sacrifice a Food.)\nWhenever you forage, put a +1/+1 counter on this creature.",
    setup_interceptors=corpseberry_cultivator_setup,
)

DREAMDEW_ENTRANCER = make_creature(
    name="Dreamdew Entrancer",
    power=3, toughness=4,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Frog", "Wizard"},
    text="Reach\nWhen this creature enters, tap up to one target creature and put three stun counters on it. If you control that creature, draw two cards.",
    setup_interceptors=dreamdew_entrancer_setup
)

FINNEAS_ACE_ARCHER = make_creature(
    name="Finneas, Ace Archer",
    power=2, toughness=2,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Archer", "Rabbit"},
    supertypes={"Legendary"},
    text="Vigilance, reach\nWhenever Finneas attacks, put a +1/+1 counter on each other creature you control that's a token or a Rabbit. Then if creatures you control have total power 10 or greater, draw a card.",
    setup_interceptors=finneas_ace_archer_setup
)

FIREGLASS_MENTOR = make_creature(
    name="Fireglass Mentor",
    power=2, toughness=1,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Lizard", "Warlock"},
    text="At the beginning of your second main phase, if an opponent lost life this turn, exile the top two cards of your library. Choose one of them. Until end of turn, you may play that card.",
    setup_interceptors=fireglass_mentor_setup,
)

GEV_SCALED_SCORCH = make_creature(
    name="Gev, Scaled Scorch",
    power=3, toughness=2,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Lizard", "Mercenary"},
    supertypes={"Legendary"},
    text="Ward—Pay 2 life.\nOther creatures you control enter with an additional +1/+1 counter on them for each opponent who lost life this turn.\nWhenever you cast a Lizard spell, Gev deals 1 damage to target opponent.",
    setup_interceptors=gev_scaled_scorch_setup
)

GLARB_CALAMITYS_AUGUR = make_creature(
    name="Glarb, Calamity's Augur",
    power=2, toughness=4,
    mana_cost="{B}{G}{U}",
    colors={Color.BLACK, Color.GREEN, Color.BLUE},
    subtypes={"Frog", "Noble", "Wizard"},
    supertypes={"Legendary"},
    text="Deathtouch\nYou may look at the top card of your library any time.\nYou may play lands and cast spells with mana value 4 or greater from the top of your library.\n{T}: Surveil 2.",
)

HEAD_OF_THE_HOMESTEAD = make_creature(
    name="Head of the Homestead",
    power=3, toughness=2,
    mana_cost="{3}{G/W}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Citizen", "Rabbit"},
    text="When this creature enters, create two 1/1 white Rabbit creature tokens.",
    setup_interceptors=head_of_the_homestead_setup
)

HELGA_SKITTISH_SEER = make_creature(
    name="Helga, Skittish Seer",
    power=1, toughness=3,
    mana_cost="{G}{W}{U}",
    colors={Color.GREEN, Color.BLUE, Color.WHITE},
    subtypes={"Druid", "Frog"},
    supertypes={"Legendary"},
    text="Whenever you cast a creature spell with mana value 4 or greater, you draw a card, gain 1 life, and put a +1/+1 counter on Helga.\n{T}: Add X mana of any one color, where X is Helga's power. Spend this mana only to cast creature spells with mana value 4 or greater or creature spells with {X} in their mana costs.",
    setup_interceptors=helga_skittish_seer_setup,
)

HUGS_GRISLY_GUARDIAN = make_creature(
    name="Hugs, Grisly Guardian",
    power=5, toughness=5,
    mana_cost="{X}{R}{R}{G}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Badger", "Warrior"},
    supertypes={"Legendary"},
    text="Trample\nWhen Hugs enters, exile the top X cards of your library. Until the end of your next turn, you may play those cards.\nYou may play an additional land on each of your turns.",
    setup_interceptors=hugs_grisly_guardian_setup,
)

THE_INFAMOUS_CRUELCLAW = make_creature(
    name="The Infamous Cruelclaw",
    power=3, toughness=3,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Mercenary", "Weasel"},
    supertypes={"Legendary"},
    text="Menace\nWhenever The Infamous Cruelclaw deals combat damage to a player, exile cards from the top of your library until you exile a nonland card. You may cast that card by discarding a card rather than paying its mana cost.",
    setup_interceptors=the_infamous_cruelclaw_setup,
)

JUNKBLADE_BRUISER = make_creature(
    name="Junkblade Bruiser",
    power=4, toughness=5,
    mana_cost="{3}{R/G}{R/G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Berserker", "Raccoon"},
    text="Trample\nWhenever you expend 4, this creature gets +2/+1 until end of turn. (You expend 4 as you spend your fourth total mana to cast spells during a turn.)",
    setup_interceptors=junkblade_bruiser_setup,
)

KASTRAL_THE_WINDCRESTED = make_creature(
    name="Kastral, the Windcrested",
    power=4, toughness=5,
    mana_cost="{3}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Bird", "Scout"},
    supertypes={"Legendary"},
    text="Flying\nWhenever one or more Birds you control deal combat damage to a player, choose one —\n• You may put a Bird creature card from your hand or graveyard onto the battlefield with a finality counter on it.\n• Put a +1/+1 counter on each Bird you control.\n• Draw a card.",
    setup_interceptors=kastral_the_windcrested_setup,
)

LILYSPLASH_MENTOR = make_creature(
    name="Lilysplash Mentor",
    power=4, toughness=4,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Druid", "Frog"},
    text="Reach\n{1}{G}{U}: Exile another target creature you control, then return it to the battlefield under its owner's control with a +1/+1 counter on it. Activate only as a sorcery.",
    setup_interceptors=lilysplash_mentor_setup,
)

LUNAR_CONVOCATION = make_enchantment(
    name="Lunar Convocation",
    mana_cost="{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    text="At the beginning of your end step, if you gained life this turn, each opponent loses 1 life.\nAt the beginning of your end step, if you gained and lost life this turn, create a 1/1 black Bat creature token with flying.\n{1}{B}, Pay 2 life: Draw a card.",
    setup_interceptors=lunar_convocation_setup,
)

MABEL_HEIR_TO_CRAGFLAME = make_creature(
    name="Mabel, Heir to Cragflame",
    power=3, toughness=3,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Mouse", "Soldier"},
    supertypes={"Legendary"},
    text="Other Mice you control get +1/+1.\nWhen Mabel enters, create Cragflame, a legendary colorless Equipment artifact token with \"Equipped creature gets +1/+1 and has vigilance, trample, and haste\" and equip {2}.",
    setup_interceptors=mabel_heir_to_cragflame_setup
)

MIND_DRILL_ASSAILANT = make_creature(
    name="Mind Drill Assailant",
    power=2, toughness=5,
    mana_cost="{2}{U/B}{U/B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Rat", "Warlock"},
    text="Threshold — As long as there are seven or more cards in your graveyard, this creature gets +3/+0.\n{2}{U/B}: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    setup_interceptors=mind_drill_assailant_setup,
)

MOONRISE_CLERIC = make_creature(
    name="Moonrise Cleric",
    power=2, toughness=3,
    mana_cost="{1}{W/B}{W/B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Bat", "Cleric"},
    text="Flying\nWhenever this creature attacks, you gain 1 life.",
    setup_interceptors=moonrise_cleric_setup
)

MUERRA_TRASH_TACTICIAN = make_creature(
    name="Muerra, Trash Tactician",
    power=2, toughness=4,
    mana_cost="{1}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Raccoon", "Warrior"},
    supertypes={"Legendary"},
    text="At the beginning of your first main phase, add {R} or {G} for each Raccoon you control.\nWhenever you expend 4, you gain 3 life. (You expend 4 as you spend your fourth total mana to cast spells during a turn.)\nWhenever you expend 8, exile the top two cards of your library. Until the end of your next turn, you may play those cards.",
    setup_interceptors=muerra_trash_tactician_setup,
)

PLUMECREED_MENTOR = make_creature(
    name="Plumecreed Mentor",
    power=2, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Bird", "Scout"},
    text="Flying\nWhenever this creature or another creature you control with flying enters, put a +1/+1 counter on target creature you control without flying.",
    setup_interceptors=plumecreed_mentor_setup
)

POND_PROPHET = make_creature(
    name="Pond Prophet",
    power=1, toughness=1,
    mana_cost="{G/U}{G/U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Advisor", "Frog"},
    text="When this creature enters, draw a card.",
    setup_interceptors=pond_prophet_setup
)

RAL_CRACKLING_WIT = make_planeswalker(
    name="Ral, Crackling Wit",
    mana_cost="{2}{U}{R}",
    colors={Color.RED, Color.BLUE},
    loyalty=4,
    subtypes={"Ral"},
    supertypes={"Legendary"},
    text="Whenever you cast a noncreature spell, put a loyalty counter on Ral.\n+1: Create a 1/1 blue and red Otter creature token with prowess.\n−3: Draw three cards, then discard two cards.\n−10: Draw three cards. You get an emblem with \"Instant and sorcery spells you cast have storm.\" (Whenever you cast an instant or sorcery spell, copy it for each spell cast before it this turn.)",
    setup_interceptors=ral_crackling_wit_setup,
)

SEEDGLAIVE_MENTOR = make_creature(
    name="Seedglaive Mentor",
    power=3, toughness=2,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Mouse", "Soldier"},
    text="Vigilance, haste\nValiant — Whenever this creature becomes the target of a spell or ability you control for the first time each turn, put a +1/+1 counter on it.",
    setup_interceptors=seedglaive_mentor_setup,
)

SEEDPOD_SQUIRE = make_creature(
    name="Seedpod Squire",
    power=3, toughness=3,
    mana_cost="{3}{W/U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Bird", "Scout"},
    text="Flying\nWhenever this creature attacks, target creature you control without flying gets +1/+1 until end of turn.",
    setup_interceptors=seedpod_squire_setup
)

STARSEER_MENTOR = make_creature(
    name="Starseer Mentor",
    power=3, toughness=5,
    mana_cost="{3}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Bat", "Warlock"},
    text="Flying, vigilance\nAt the beginning of your end step, if you gained or lost life this turn, target opponent loses 3 life unless they sacrifice a nonland permanent of their choice or discard a card.",
    setup_interceptors=starseer_mentor_setup
)

STORMCATCH_MENTOR = make_creature(
    name="Stormcatch Mentor",
    power=1, toughness=1,
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Otter", "Wizard"},
    text="Haste\nProwess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nInstant and sorcery spells you cast cost {1} less to cast.",
    setup_interceptors=stormcatch_mentor_setup,
)

TEMPEST_ANGLER = make_creature(
    name="Tempest Angler",
    power=2, toughness=2,
    mana_cost="{1}{U/R}{U/R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Otter", "Wizard"},
    text="Whenever you cast a noncreature spell, put a +1/+1 counter on this creature.",
    setup_interceptors=tempest_angler_setup
)

TIDECALLER_MENTOR = make_creature(
    name="Tidecaller Mentor",
    power=3, toughness=3,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Rat", "Wizard"},
    text="Menace\nThreshold — When this creature enters, if there are seven or more cards in your graveyard, return up to one target nonland permanent to its owner's hand.",
    setup_interceptors=tidecaller_mentor_setup,
)

VETERAN_GUARDMOUSE = make_creature(
    name="Veteran Guardmouse",
    power=3, toughness=4,
    mana_cost="{3}{R/W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Mouse", "Soldier"},
    text="Valiant — Whenever this creature becomes the target of a spell or ability you control for the first time each turn, it gets +1/+0 and gains first strike until end of turn. Scry 1. (Look at the top card of your library. You may put that card on the bottom.)",
    setup_interceptors=veteran_guardmouse_setup,
)

VINEREAP_MENTOR = make_creature(
    name="Vinereap Mentor",
    power=3, toughness=2,
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Druid", "Squirrel"},
    text="When this creature enters or dies, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")",
    setup_interceptors=vinereap_mentor_setup
)

VREN_THE_RELENTLESS = make_creature(
    name="Vren, the Relentless",
    power=3, toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Rat", "Rogue"},
    supertypes={"Legendary"},
    text="Ward {2}\nIf a creature an opponent controls would die, exile it instead.\nAt the beginning of each end step, create X 1/1 black Rat creature tokens with \"This token gets +1/+1 for each other Rat you control,\" where X is the number of creatures that were exiled under your opponents' control this turn.",
    setup_interceptors=vren_the_relentless_setup,
)

WANDERTALE_MENTOR = make_creature(
    name="Wandertale Mentor",
    power=2, toughness=2,
    mana_cost="{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Bard", "Raccoon"},
    text="Whenever you expend 4, put a +1/+1 counter on this creature. (You expend 4 as you spend your fourth total mana to cast spells during a turn.)\n{T}: Add {R} or {G}.",
    setup_interceptors=wandertale_mentor_setup,
)

YGRA_EATER_OF_ALL = make_creature(
    name="Ygra, Eater of All",
    power=6, toughness=6,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Cat", "Elemental"},
    supertypes={"Legendary"},
    text="Ward—Sacrifice a Food.\nOther creatures are Food artifacts in addition to their other types and have \"{2}, {T}, Sacrifice this permanent: You gain 3 life.\"\nWhenever a Food is put into a graveyard from the battlefield, put two +1/+1 counters on Ygra.",
    setup_interceptors=ygra_eater_of_all_setup,
)

ZORALINE_COSMOS_CALLER = make_creature(
    name="Zoraline, Cosmos Caller",
    power=3, toughness=3,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Bat", "Cleric"},
    supertypes={"Legendary"},
    text="Flying, vigilance\nWhenever a Bat you control attacks, you gain 1 life.\nWhenever Zoraline enters or attacks, you may pay {W}{B} and 2 life. When you do, return target nonland permanent card with mana value 3 or less from your graveyard to the battlefield with a finality counter on it.",
    setup_interceptors=zoraline_cosmos_caller_setup
)

BARKFORM_HARVESTER = make_artifact_creature(
    name="Barkform Harvester",
    power=2, toughness=3,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Shapeshifter"},
    text="Changeling (This card is every creature type.)\nReach\n{2}: Put target card from your graveyard on the bottom of your library.",
    setup_interceptors=barkform_harvester_setup,
)

BUMBLEFLOWERS_SHAREPOT = make_artifact(
    name="Bumbleflower's Sharepot",
    mana_cost="{2}",
    text="When this artifact enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\n{5}, {T}, Sacrifice this artifact: Destroy target nonland permanent. Activate only as a sorcery.",
    setup_interceptors=bumbleflowers_sharepot_setup,
)

FOUNTAINPORT_BELL = make_artifact(
    name="Fountainport Bell",
    mana_cost="{1}",
    text="When this artifact enters, you may search your library for a basic land card, reveal it, then shuffle and put that card on top.\n{1}, Sacrifice this artifact: Draw a card.",
    setup_interceptors=fountainport_bell_setup,
)

HEIRLOOM_EPIC = make_artifact(
    name="Heirloom Epic",
    mana_cost="{1}",
    text="{4}, {T}: Draw a card. For each mana in this ability's activation cost, you may tap an untapped creature you control rather than pay that mana. Activate only as a sorcery.",
)

PATCHWORK_BANNER = make_artifact(
    name="Patchwork Banner",
    mana_cost="{3}",
    text="As this artifact enters, choose a creature type.\nCreatures you control of the chosen type get +1/+1.\n{T}: Add one mana of any color.",
    setup_interceptors=patchwork_banner_setup
)

SHORT_BOW = make_artifact(
    name="Short Bow",
    mana_cost="{2}",
    text="Equipped creature gets +1/+1 and has vigilance and reach.\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=short_bow_setup,
)

STARFORGED_SWORD = make_artifact(
    name="Starforged Sword",
    mana_cost="{4}",
    text="Gift a tapped Fish (You may promise an opponent a gift as you cast this spell. If you do, when it enters, they create a tapped 1/1 blue Fish creature token.)\nWhen this Equipment enters, if the gift was promised, attach this Equipment to target creature you control.\nEquipped creature gets +3/+3 and loses flying.\nEquip {3}",
    subtypes={"Equipment"},
    setup_interceptors=starforged_sword_setup,
)

TANGLE_TUMBLER = make_artifact(
    name="Tangle Tumbler",
    mana_cost="{3}",
    text="Vigilance\n{3}, {T}: Put a +1/+1 counter on target creature.\nTap two untapped tokens you control: This Vehicle becomes an artifact creature until end of turn.",
    subtypes={"Vehicle"},
    setup_interceptors=tangle_tumbler_setup,
)

THREE_TREE_MASCOT = make_artifact_creature(
    name="Three Tree Mascot",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Shapeshifter"},
    text="Changeling (This card is every creature type.)\n{1}: Add one mana of any color. Activate only once each turn.",
)

FABLED_PASSAGE = make_land(
    name="Fabled Passage",
    text="{T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. Then if you control four or more lands, untap that land.",
)

FOUNTAINPORT = make_land(
    name="Fountainport",
    text="{T}: Add {C}.\n{2}, {T}, Sacrifice a token: Draw a card.\n{3}, {T}, Pay 1 life: Create a 1/1 blue Fish creature token.\n{4}, {T}: Create a Treasure token.",
)

HIDDEN_GROTTO = make_land(
    name="Hidden Grotto",
    text="When this land enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\n{T}: Add {C}.\n{1}, {T}: Add one mana of any color.",
    setup_interceptors=hidden_grotto_setup,
)

LILYPAD_VILLAGE = make_land(
    name="Lilypad Village",
    text="{T}: Add {C}.\n{T}: Add {U}. Spend this mana only to cast a creature spell.\n{U}, {T}: Surveil 2. Activate only if a Bird, Frog, Otter, or Rat entered the battlefield under your control this turn.",
)

LUPINFLOWER_VILLAGE = make_land(
    name="Lupinflower Village",
    text="{T}: Add {C}.\n{T}: Add {W}. Spend this mana only to cast a creature spell.\n{1}{W}, {T}, Sacrifice this land: Look at the top six cards of your library. You may reveal a Bat, Bird, Mouse, or Rabbit card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
)

MUDFLAT_VILLAGE = make_land(
    name="Mudflat Village",
    text="{T}: Add {C}.\n{T}: Add {B}. Spend this mana only to cast a creature spell.\n{1}{B}, {T}, Sacrifice this land: Return target Bat, Lizard, Rat, or Squirrel card from your graveyard to your hand.",
    setup_interceptors=mudflat_village_setup,
)

OAKHOLLOW_VILLAGE = make_land(
    name="Oakhollow Village",
    text="{T}: Add {C}.\n{T}: Add {G}. Spend this mana only to cast a creature spell.\n{G}, {T}: Put a +1/+1 counter on each Frog, Rabbit, Raccoon, or Squirrel you control that entered the battlefield this turn.",
)

ROCKFACE_VILLAGE = make_land(
    name="Rockface Village",
    text="{T}: Add {C}.\n{T}: Add {R}. Spend this mana only to cast a creature spell.\n{R}, {T}: Target Lizard, Mouse, Otter, or Raccoon you control gets +1/+0 and gains haste until end of turn. Activate only as a sorcery.",
    setup_interceptors=rockface_village_setup,
)

THREE_TREE_CITY = make_land(
    name="Three Tree City",
    text="As Three Tree City enters, choose a creature type.\n{T}: Add {C}.\n{2}, {T}: Choose a color. Add an amount of mana of that color equal to the number of creatures you control of the chosen type.",
    supertypes={"Legendary"},
)

UNCHARTED_HAVEN = make_land(
    name="Uncharted Haven",
    text="This land enters tapped. As it enters, choose a color.\n{T}: Add one mana of the chosen color.",
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

BRIA_RIPTIDE_ROGUE = make_creature(
    name="Bria, Riptide Rogue",
    power=3, toughness=3,
    mana_cost="{2}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Otter", "Rogue"},
    supertypes={"Legendary"},
    text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nOther creatures you control have prowess. (If a creature has multiple instances of prowess, each triggers separately.)\nWhenever you cast a noncreature spell, target creature you control can't be blocked this turn.",
    setup_interceptors=bria_riptide_rogue_setup
)

BYRKE_LONG_EAR_OF_THE_LAW = make_creature(
    name="Byrke, Long Ear of the Law",
    power=4, toughness=4,
    mana_cost="{4}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Rabbit", "Soldier"},
    supertypes={"Legendary"},
    text="Vigilance\nWhen Byrke enters, put a +1/+1 counter on each of up to two target creatures.\nWhenever a creature you control with a +1/+1 counter on it attacks, double the number of +1/+1 counters on it.",
    setup_interceptors=byrke_long_ear_of_the_law_setup,
)

SERRA_REDEEMER = make_creature(
    name="Serra Redeemer",
    power=2, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel", "Soldier"},
    text="Flying\nWhenever another creature you control with power 2 or less enters, put two +1/+1 counters on that creature.",
    setup_interceptors=serra_redeemer_setup
)

CHARMED_SLEEP = make_enchantment(
    name="Charmed Sleep",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Enchant creature\nWhen this Aura enters, tap enchanted creature.\nEnchanted creature doesn't untap during its controller's untap step.",
    subtypes={"Aura"},
    setup_interceptors=charmed_sleep_setup,
)

MIND_SPRING = make_sorcery(
    name="Mind Spring",
    mana_cost="{X}{U}{U}",
    colors={Color.BLUE},
    text="Draw X cards.",
)

THIEVING_OTTER = make_creature(
    name="Thieving Otter",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Otter"},
    text="Whenever this creature deals damage to an opponent, draw a card.",
    setup_interceptors=thieving_otter_setup
)

FLAME_LASH = make_instant(
    name="Flame Lash",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Flame Lash deals 4 damage to any target.",
    resolve=flame_lash_resolve,
)

COLOSSIFICATION = make_enchantment(
    name="Colossification",
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    text="Enchant creature\nWhen this Aura enters, tap enchanted creature.\nEnchanted creature gets +20/+20.",
    subtypes={"Aura"},
    setup_interceptors=colossification_setup,
)

GIANT_GROWTH = make_instant(
    name="Giant Growth",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn.",
    resolve=giant_growth_resolve,
)

RABID_BITE = make_sorcery(
    name="Rabid Bite",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control deals damage equal to its power to target creature you don't control.",
    resolve=rabid_bite_resolve,
)

SWORD_OF_VENGEANCE = make_artifact(
    name="Sword of Vengeance",
    mana_cost="{3}",
    text="Equipped creature gets +2/+0 and has first strike, vigilance, trample, and haste.\nEquip {3}",
    subtypes={"Equipment"},
    setup_interceptors=sword_of_vengeance_setup,
)

BLOSSOMING_SANDS = make_land(
    name="Blossoming Sands",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {G} or {W}.",
    setup_interceptors=blossoming_sands_setup,
)

SWIFTWATER_CLIFFS = make_land(
    name="Swiftwater Cliffs",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {U} or {R}.",
    setup_interceptors=swiftwater_cliffs_setup,
)

# =============================================================================
# CARD REGISTRY
# =============================================================================

BLOOMBURROW_CARDS = {
    "Banishing Light": BANISHING_LIGHT,
    "Beza, the Bounding Spring": BEZA_THE_BOUNDING_SPRING,
    "Brave-Kin Duo": BRAVEKIN_DUO,
    "Brightblade Stoat": BRIGHTBLADE_STOAT,
    "Builder's Talent": BUILDERS_TALENT,
    "Caretaker's Talent": CARETAKERS_TALENT,
    "Carrot Cake": CARROT_CAKE,
    "Crumb and Get It": CRUMB_AND_GET_IT,
    "Dawn's Truce": DAWNS_TRUCE,
    "Dewdrop Cure": DEWDROP_CURE,
    "Driftgloom Coyote": DRIFTGLOOM_COYOTE,
    "Essence Channeler": ESSENCE_CHANNELER,
    "Feather of Flight": FEATHER_OF_FLIGHT,
    "Flowerfoot Swordmaster": FLOWERFOOT_SWORDMASTER,
    "Harvestrite Host": HARVESTRITE_HOST,
    "Hop to It": HOP_TO_IT,
    "Intrepid Rabbit": INTREPID_RABBIT,
    "Jackdaw Savior": JACKDAW_SAVIOR,
    "Jolly Gerbils": JOLLY_GERBILS,
    "Lifecreed Duo": LIFECREED_DUO,
    "Mabel's Mettle": MABELS_METTLE,
    "Mouse Trapper": MOUSE_TRAPPER,
    "Nettle Guard": NETTLE_GUARD,
    "Parting Gust": PARTING_GUST,
    "Pileated Provisioner": PILEATED_PROVISIONER,
    "Rabbit Response": RABBIT_RESPONSE,
    "Repel Calamity": REPEL_CALAMITY,
    "Salvation Swan": SALVATION_SWAN,
    "Season of the Burrow": SEASON_OF_THE_BURROW,
    "Seasoned Warrenguard": SEASONED_WARRENGUARD,
    "Shrike Force": SHRIKE_FORCE,
    "Sonar Strike": SONAR_STRIKE,
    "Star Charter": STAR_CHARTER,
    "Starfall Invocation": STARFALL_INVOCATION,
    "Thistledown Players": THISTLEDOWN_PLAYERS,
    "Valley Questcaller": VALLEY_QUESTCALLER,
    "Warren Elder": WARREN_ELDER,
    "Warren Warleader": WARREN_WARLEADER,
    "Wax-Wane Witness": WAXWANE_WITNESS,
    "Whiskervale Forerunner": WHISKERVALE_FORERUNNER,
    "Azure Beastbinder": AZURE_BEASTBINDER,
    "Bellowing Crier": BELLOWING_CRIER,
    "Calamitous Tide": CALAMITOUS_TIDE,
    "Daring Waverider": DARING_WAVERIDER,
    "Dazzling Denial": DAZZLING_DENIAL,
    "Dire Downdraft": DIRE_DOWNDRAFT,
    "Dour Port-Mage": DOUR_PORTMAGE,
    "Eddymurk Crab": EDDYMURK_CRAB,
    "Eluge, the Shoreless Sea": ELUGE_THE_SHORELESS_SEA,
    "Finch Formation": FINCH_FORMATION,
    "Gossip's Talent": GOSSIPS_TALENT,
    "Into the Flood Maw": INTO_THE_FLOOD_MAW,
    "Kitnap": KITNAP,
    "Kitsa, Otterball Elite": KITSA_OTTERBALL_ELITE,
    "Knightfisher": KNIGHTFISHER,
    "Lightshell Duo": LIGHTSHELL_DUO,
    "Long River Lurker": LONG_RIVER_LURKER,
    "Long River's Pull": LONG_RIVERS_PULL,
    "Mind Spiral": MIND_SPIRAL,
    "Mindwhisker": MINDWHISKER,
    "Mockingbird": MOCKINGBIRD,
    "Nightwhorl Hermit": NIGHTWHORL_HERMIT,
    "Otterball Antics": OTTERBALL_ANTICS,
    "Pearl of Wisdom": PEARL_OF_WISDOM,
    "Plumecreed Escort": PLUMECREED_ESCORT,
    "Portent of Calamity": PORTENT_OF_CALAMITY,
    "Run Away Together": RUN_AWAY_TOGETHER,
    "Season of Weaving": SEASON_OF_WEAVING,
    "Shore Up": SHORE_UP,
    "Shoreline Looter": SHORELINE_LOOTER,
    "Skyskipper Duo": SKYSKIPPER_DUO,
    "Spellgyre": SPELLGYRE,
    "Splash Lasher": SPLASH_LASHER,
    "Splash Portal": SPLASH_PORTAL,
    "Stormchaser's Talent": STORMCHASERS_TALENT,
    "Sugar Coat": SUGAR_COAT,
    "Thought Shucker": THOUGHT_SHUCKER,
    "Thundertrap Trainer": THUNDERTRAP_TRAINER,
    "Valley Floodcaller": VALLEY_FLOODCALLER,
    "Waterspout Warden": WATERSPOUT_WARDEN,
    "Wishing Well": WISHING_WELL,
    "Agate-Blade Assassin": AGATEBLADE_ASSASSIN,
    "Bandit's Talent": BANDITS_TALENT,
    "Bonebind Orator": BONEBIND_ORATOR,
    "Bonecache Overseer": BONECACHE_OVERSEER,
    "Coiling Rebirth": COILING_REBIRTH,
    "Consumed by Greed": CONSUMED_BY_GREED,
    "Cruelclaw's Heist": CRUELCLAWS_HEIST,
    "Daggerfang Duo": DAGGERFANG_DUO,
    "Darkstar Augur": DARKSTAR_AUGUR,
    "Diresight": DIRESIGHT,
    "Downwind Ambusher": DOWNWIND_AMBUSHER,
    "Early Winter": EARLY_WINTER,
    "Feed the Cycle": FEED_THE_CYCLE,
    "Fell": FELL,
    "Glidedive Duo": GLIDEDIVE_DUO,
    "Hazel's Nocturne": HAZELS_NOCTURNE,
    "Huskburster Swarm": HUSKBURSTER_SWARM,
    "Iridescent Vinelasher": IRIDESCENT_VINELASHER,
    "Maha, Its Feathers Night": MAHA_ITS_FEATHERS_NIGHT,
    "Moonstone Harbinger": MOONSTONE_HARBINGER,
    "Nocturnal Hunger": NOCTURNAL_HUNGER,
    "Osteomancer Adept": OSTEOMANCER_ADEPT,
    "Persistent Marshstalker": PERSISTENT_MARSHSTALKER,
    "Psychic Whorl": PSYCHIC_WHORL,
    "Ravine Raider": RAVINE_RAIDER,
    "Rottenmouth Viper": ROTTENMOUTH_VIPER,
    "Ruthless Negotiation": RUTHLESS_NEGOTIATION,
    "Savor": SAVOR,
    "Scales of Shale": SCALES_OF_SHALE,
    "Scavenger's Talent": SCAVENGERS_TALENT,
    "Season of Loss": SEASON_OF_LOSS,
    "Sinister Monolith": SINISTER_MONOLITH,
    "Stargaze": STARGAZE,
    "Starlit Soothsayer": STARLIT_SOOTHSAYER,
    "Starscape Cleric": STARSCAPE_CLERIC,
    "Thornplate Intimidator": THORNPLATE_INTIMIDATOR,
    "Thought-Stalker Warlock": THOUGHTSTALKER_WARLOCK,
    "Valley Rotcaller": VALLEY_ROTCALLER,
    "Wick, the Whorled Mind": WICK_THE_WHORLED_MIND,
    "Wick's Patrol": WICKS_PATROL,
    "Agate Assault": AGATE_ASSAULT,
    "Alania's Pathmaker": ALANIAS_PATHMAKER,
    "Artist's Talent": ARTISTS_TALENT,
    "Blacksmith's Talent": BLACKSMITHS_TALENT,
    "Blooming Blast": BLOOMING_BLAST,
    "Brambleguard Captain": BRAMBLEGUARD_CAPTAIN,
    "Brazen Collector": BRAZEN_COLLECTOR,
    "Byway Barterer": BYWAY_BARTERER,
    "Conduct Electricity": CONDUCT_ELECTRICITY,
    "Coruscation Mage": CORUSCATION_MAGE,
    "Dragonhawk, Fate's Tempest": DRAGONHAWK_FATES_TEMPEST,
    "Emberheart Challenger": EMBERHEART_CHALLENGER,
    "Festival of Embers": FESTIVAL_OF_EMBERS,
    "Flamecache Gecko": FLAMECACHE_GECKO,
    "Frilled Sparkshooter": FRILLED_SPARKSHOOTER,
    "Harnesser of Storms": HARNESSER_OF_STORMS,
    "Heartfire Hero": HEARTFIRE_HERO,
    "A-Heartfire Hero": AHEARTFIRE_HERO,
    "Hearthborn Battler": HEARTHBORN_BATTLER,
    "Hired Claw": HIRED_CLAW,
    "Hoarder's Overflow": HOARDERS_OVERFLOW,
    "Kindlespark Duo": KINDLESPARK_DUO,
    "Manifold Mouse": MANIFOLD_MOUSE,
    "Might of the Meek": MIGHT_OF_THE_MEEK,
    "Playful Shove": PLAYFUL_SHOVE,
    "Quaketusk Boar": QUAKETUSK_BOAR,
    "Rabid Gnaw": RABID_GNAW,
    "Raccoon Rallier": RACCOON_RALLIER,
    "Reptilian Recruiter": REPTILIAN_RECRUITER,
    "Roughshod Duo": ROUGHSHOD_DUO,
    "Sazacap's Brew": SAZACAPS_BREW,
    "Season of the Bold": SEASON_OF_THE_BOLD,
    "Steampath Charger": STEAMPATH_CHARGER,
    "Stormsplitter": STORMSPLITTER,
    "Sunspine Lynx": SUNSPINE_LYNX,
    "Take Out the Trash": TAKE_OUT_THE_TRASH,
    "Teapot Slinger": TEAPOT_SLINGER,
    "Valley Flamecaller": VALLEY_FLAMECALLER,
    "Valley Rally": VALLEY_RALLY,
    "War Squeak": WAR_SQUEAK,
    "Whiskerquill Scribe": WHISKERQUILL_SCRIBE,
    "Wildfire Howl": WILDFIRE_HOWL,
    "Bakersbane Duo": BAKERSBANE_DUO,
    "Bark-Knuckle Boxer": BARKKNUCKLE_BOXER,
    "Brambleguard Veteran": BRAMBLEGUARD_VETERAN,
    "Bushy Bodyguard": BUSHY_BODYGUARD,
    "Cache Grab": CACHE_GRAB,
    "Clifftop Lookout": CLIFFTOP_LOOKOUT,
    "Curious Forager": CURIOUS_FORAGER,
    "Druid of the Spade": DRUID_OF_THE_SPADE,
    "Fecund Greenshell": FECUND_GREENSHELL,
    "For the Common Good": FOR_THE_COMMON_GOOD,
    "Galewind Moose": GALEWIND_MOOSE,
    "Hazardroot Herbalist": HAZARDROOT_HERBALIST,
    "Heaped Harvest": HEAPED_HARVEST,
    "High Stride": HIGH_STRIDE,
    "Hivespine Wolverine": HIVESPINE_WOLVERINE,
    "Honored Dreyleader": HONORED_DREYLEADER,
    "Hunter's Talent": HUNTERS_TALENT,
    "Innkeeper's Talent": INNKEEPERS_TALENT,
    "Keen-Eyed Curator": KEENEYED_CURATOR,
    "Longstalk Brawl": LONGSTALK_BRAWL,
    "Lumra, Bellow of the Woods": LUMRA_BELLOW_OF_THE_WOODS,
    "Mistbreath Elder": MISTBREATH_ELDER,
    "Overprotect": OVERPROTECT,
    "Pawpatch Formation": PAWPATCH_FORMATION,
    "Pawpatch Recruit": PAWPATCH_RECRUIT,
    "Peerless Recycling": PEERLESS_RECYCLING,
    "Polliwallop": POLLIWALLOP,
    "Rust-Shield Rampager": RUSTSHIELD_RAMPAGER,
    "Scrapshooter": SCRAPSHOOTER,
    "Season of Gathering": SEASON_OF_GATHERING,
    "Stickytongue Sentinel": STICKYTONGUE_SENTINEL,
    "Stocking the Pantry": STOCKING_THE_PANTRY,
    "Sunshower Druid": SUNSHOWER_DRUID,
    "Tender Wildguide": TENDER_WILDGUIDE,
    "Thornvault Forager": THORNVAULT_FORAGER,
    "Three Tree Rootweaver": THREE_TREE_ROOTWEAVER,
    "Three Tree Scribe": THREE_TREE_SCRIBE,
    "Treeguard Duo": TREEGUARD_DUO,
    "Treetop Sentries": TREETOP_SENTRIES,
    "Valley Mightcaller": VALLEY_MIGHTCALLER,
    "Wear Down": WEAR_DOWN,
    "Alania, Divergent Storm": ALANIA_DIVERGENT_STORM,
    "Baylen, the Haymaker": BAYLEN_THE_HAYMAKER,
    "Burrowguard Mentor": BURROWGUARD_MENTOR,
    "Camellia, the Seedmiser": CAMELLIA_THE_SEEDMISER,
    "Cindering Cutthroat": CINDERING_CUTTHROAT,
    "Clement, the Worrywort": CLEMENT_THE_WORRYWORT,
    "Corpseberry Cultivator": CORPSEBERRY_CULTIVATOR,
    "Dreamdew Entrancer": DREAMDEW_ENTRANCER,
    "Finneas, Ace Archer": FINNEAS_ACE_ARCHER,
    "Fireglass Mentor": FIREGLASS_MENTOR,
    "Gev, Scaled Scorch": GEV_SCALED_SCORCH,
    "Glarb, Calamity's Augur": GLARB_CALAMITYS_AUGUR,
    "Head of the Homestead": HEAD_OF_THE_HOMESTEAD,
    "Helga, Skittish Seer": HELGA_SKITTISH_SEER,
    "Hugs, Grisly Guardian": HUGS_GRISLY_GUARDIAN,
    "The Infamous Cruelclaw": THE_INFAMOUS_CRUELCLAW,
    "Junkblade Bruiser": JUNKBLADE_BRUISER,
    "Kastral, the Windcrested": KASTRAL_THE_WINDCRESTED,
    "Lilysplash Mentor": LILYSPLASH_MENTOR,
    "Lunar Convocation": LUNAR_CONVOCATION,
    "Mabel, Heir to Cragflame": MABEL_HEIR_TO_CRAGFLAME,
    "Mind Drill Assailant": MIND_DRILL_ASSAILANT,
    "Moonrise Cleric": MOONRISE_CLERIC,
    "Muerra, Trash Tactician": MUERRA_TRASH_TACTICIAN,
    "Plumecreed Mentor": PLUMECREED_MENTOR,
    "Pond Prophet": POND_PROPHET,
    "Ral, Crackling Wit": RAL_CRACKLING_WIT,
    "Seedglaive Mentor": SEEDGLAIVE_MENTOR,
    "Seedpod Squire": SEEDPOD_SQUIRE,
    "Starseer Mentor": STARSEER_MENTOR,
    "Stormcatch Mentor": STORMCATCH_MENTOR,
    "Tempest Angler": TEMPEST_ANGLER,
    "Tidecaller Mentor": TIDECALLER_MENTOR,
    "Veteran Guardmouse": VETERAN_GUARDMOUSE,
    "Vinereap Mentor": VINEREAP_MENTOR,
    "Vren, the Relentless": VREN_THE_RELENTLESS,
    "Wandertale Mentor": WANDERTALE_MENTOR,
    "Ygra, Eater of All": YGRA_EATER_OF_ALL,
    "Zoraline, Cosmos Caller": ZORALINE_COSMOS_CALLER,
    "Barkform Harvester": BARKFORM_HARVESTER,
    "Bumbleflower's Sharepot": BUMBLEFLOWERS_SHAREPOT,
    "Fountainport Bell": FOUNTAINPORT_BELL,
    "Heirloom Epic": HEIRLOOM_EPIC,
    "Patchwork Banner": PATCHWORK_BANNER,
    "Short Bow": SHORT_BOW,
    "Starforged Sword": STARFORGED_SWORD,
    "Tangle Tumbler": TANGLE_TUMBLER,
    "Three Tree Mascot": THREE_TREE_MASCOT,
    "Fabled Passage": FABLED_PASSAGE,
    "Fountainport": FOUNTAINPORT,
    "Hidden Grotto": HIDDEN_GROTTO,
    "Lilypad Village": LILYPAD_VILLAGE,
    "Lupinflower Village": LUPINFLOWER_VILLAGE,
    "Mudflat Village": MUDFLAT_VILLAGE,
    "Oakhollow Village": OAKHOLLOW_VILLAGE,
    "Rockface Village": ROCKFACE_VILLAGE,
    "Three Tree City": THREE_TREE_CITY,
    "Uncharted Haven": UNCHARTED_HAVEN,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
    "Bria, Riptide Rogue": BRIA_RIPTIDE_ROGUE,
    "Byrke, Long Ear of the Law": BYRKE_LONG_EAR_OF_THE_LAW,
    "Serra Redeemer": SERRA_REDEEMER,
    "Charmed Sleep": CHARMED_SLEEP,
    "Mind Spring": MIND_SPRING,
    "Thieving Otter": THIEVING_OTTER,
    "Flame Lash": FLAME_LASH,
    "Colossification": COLOSSIFICATION,
    "Giant Growth": GIANT_GROWTH,
    "Rabid Bite": RABID_BITE,
    "Sword of Vengeance": SWORD_OF_VENGEANCE,
    "Blossoming Sands": BLOSSOMING_SANDS,
    "Swiftwater Cliffs": SWIFTWATER_CLIFFS,
}

print(f"Loaded {len(BLOOMBURROW_CARDS)} Bloomburrow cards")
