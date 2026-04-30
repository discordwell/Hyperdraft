"""
Lost_Caverns_of_Ixalan (LCI) Card Implementations

Real card data fetched from Scryfall API.
292 cards in set.
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
    make_damage_trigger, make_spell_cast_trigger,
    other_creatures_you_control, other_creatures_with_subtype,
    creatures_you_control, creatures_with_subtype, create_target_choice
)


# =============================================================================
# INTERCEPTOR SETUP FUNCTIONS
# =============================================================================

# --- WHITE CARDS ---

def ironpaw_aspirant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, put a +1/+1 counter on target creature."""
    def handle_target_choice(choice, selected: list, game_state: GameState) -> list[Event]:
        if not selected:
            return []
        target_id = selected[0]
        target = game_state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []
        if CardType.CREATURE not in target.characteristics.types:
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': target_id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find all creatures on the battlefield (valid targets)
        valid_targets = []
        for game_obj in state.objects.values():
            if (game_obj.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in game_obj.characteristics.types):
                valid_targets.append(game_obj.id)

        if not valid_targets:
            return []

        create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature to put a +1/+1 counter on",
            min_targets=1,
            max_targets=1,
            callback_data={'handler': handle_target_choice}
        )
        return []

    return [make_etb_trigger(obj, etb_effect)]


def malamet_war_scribe_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, creatures you control get +2/+1 until end of turn."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # This would need temporary P/T boost - simplified as a placeholder
        return []
    return [make_etb_trigger(obj, etb_effect)]


def market_gnome_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, you gain 1 life and draw a card."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )
        ]
    return [make_death_trigger(obj, death_effect)]


def miners_guidewing_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, target creature you control explores."""
    def handle_target_choice(choice, selected: list, game_state: GameState) -> list[Event]:
        if not selected:
            return []
        target_id = selected[0]
        target = game_state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []
        if CardType.CREATURE not in target.characteristics.types:
            return []
        return [Event(
            type=EventType.EXPLORE,
            payload={'object_id': target_id, 'controller': target.controller},
            source=obj.id
        )]

    def death_effect(event: Event, state: GameState) -> list[Event]:
        # Find creatures controller controls (use last known controller)
        controller = obj.controller
        valid_targets = []
        for game_obj in state.objects.values():
            if (game_obj.zone == ZoneType.BATTLEFIELD and
                game_obj.controller == controller and
                CardType.CREATURE in game_obj.characteristics.types):
                valid_targets.append(game_obj.id)

        if not valid_targets:
            return []

        create_target_choice(
            state=state,
            player_id=controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature you control to explore",
            min_targets=1,
            max_targets=1,
            callback_data={'handler': handle_target_choice}
        )
        return []

    return [make_death_trigger(obj, death_effect)]


def oltec_cloud_guard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a 1/1 colorless Gnome artifact creature token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Gnome Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.ARTIFACT, CardType.CREATURE],
                'subtypes': ['Gnome'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def sanguine_evangelist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters or dies, create a 1/1 black Bat creature token with flying."""
    def create_bat(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Bat Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Bat'],
                'colors': [Color.BLACK],
                'keywords': ['flying']
            },
            source=obj.id
        )]
    return [
        make_etb_trigger(obj, create_bat),
        make_death_trigger(obj, create_bat)
    ]


def soaring_sandwing_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you gain 3 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def tinkers_tote_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this artifact enters, create two 1/1 colorless Gnome artifact creature tokens."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Gnome Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.ARTIFACT, CardType.CREATURE],
                    'subtypes': ['Gnome'],
                    'colors': []
                },
                source=obj.id
            ),
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Gnome Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.ARTIFACT, CardType.CREATURE],
                    'subtypes': ['Gnome'],
                    'colors': []
                },
                source=obj.id
            )
        ]
    return [make_etb_trigger(obj, etb_effect)]


# --- BLUE CARDS ---

def cogwork_wrestler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, target creature an opponent controls gets -2/-0 until end of turn."""
    def handle_target_choice(choice, selected: list, game_state: GameState) -> list[Event]:
        if not selected:
            return []
        target_id = selected[0]
        target = game_state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []
        if CardType.CREATURE not in target.characteristics.types:
            return []
        return [Event(
            type=EventType.TEMPORARY_PT_CHANGE,
            payload={'object_id': target_id, 'power': -2, 'toughness': 0, 'duration': 'end_of_turn'},
            source=obj.id
        )]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find creatures opponents control
        valid_targets = []
        for game_obj in state.objects.values():
            if (game_obj.zone == ZoneType.BATTLEFIELD and
                game_obj.controller != obj.controller and
                CardType.CREATURE in game_obj.characteristics.types):
                valid_targets.append(game_obj.id)

        if not valid_targets:
            return []

        create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature an opponent controls to get -2/-0",
            min_targets=1,
            max_targets=1,
            callback_data={'handler': handle_target_choice}
        )
        return []

    return [make_etb_trigger(obj, etb_effect)]


def council_of_echoes_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, if descend 4, return up to one target nonland permanent to its owner's hand."""
    def handle_target_choice(choice, selected: list, game_state: GameState) -> list[Event]:
        if not selected:
            return []
        target_id = selected[0]
        target = game_state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []
        if CardType.LAND in target.characteristics.types:
            return []
        return [Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': target_id,
                'from_zone_type': ZoneType.BATTLEFIELD,
                'to_zone_type': ZoneType.HAND,
                'to_zone': f'hand_{target.owner}'
            },
            source=obj.id
        )]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Check descend 4 - need 4+ permanent cards in graveyard
        graveyard_key = f"graveyard_{obj.controller}"
        perm_count = 0
        graveyard = state.zones.get(graveyard_key)
        if graveyard:
            for card_id in graveyard.objects:
                card = state.objects.get(card_id)
                if card:
                    card_types = card.characteristics.types
                    if (CardType.CREATURE in card_types or
                        CardType.ARTIFACT in card_types or
                        CardType.ENCHANTMENT in card_types or
                        CardType.LAND in card_types or
                        CardType.PLANESWALKER in card_types):
                        perm_count += 1

        if perm_count < 4:
            return []

        # Find nonland permanents (other than this creature)
        valid_targets = []
        for game_obj in state.objects.values():
            if (game_obj.id != obj.id and
                game_obj.zone == ZoneType.BATTLEFIELD and
                CardType.LAND not in game_obj.characteristics.types):
                valid_targets.append(game_obj.id)

        if not valid_targets:
            return []

        create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a nonland permanent to return to hand (or none)",
            min_targets=0,  # "up to one"
            max_targets=1,
            callback_data={'handler': handle_target_choice}
        )
        return []

    return [make_etb_trigger(obj, etb_effect)]


def didact_echo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, draw a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def river_herald_scout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, it explores."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.EXPLORE,
            payload={'object_id': obj.id, 'controller': obj.controller},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def sage_of_days_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, look at the top three cards of your library."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def spyglass_siren_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Map token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Map Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Map'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def staunch_crewmate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, look at the top four cards of your library."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LOOK_AT_TOP,
            payload={'player': obj.controller, 'amount': 4},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def waylaying_pirates_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, if you control an artifact, tap target artifact or creature and put a stun counter on it."""
    def handle_target_choice(choice, selected: list, game_state: GameState) -> list[Event]:
        if not selected:
            return []
        target_id = selected[0]
        target = game_state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []
        target_types = target.characteristics.types
        if CardType.ARTIFACT not in target_types and CardType.CREATURE not in target_types:
            return []
        return [
            Event(
                type=EventType.TAP,
                payload={'object_id': target_id},
                source=obj.id
            ),
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': target_id, 'counter_type': 'stun', 'amount': 1},
                source=obj.id
            )
        ]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Check if we control an artifact
        controls_artifact = False
        for game_obj in state.objects.values():
            if (game_obj.controller == obj.controller and
                game_obj.zone == ZoneType.BATTLEFIELD and
                CardType.ARTIFACT in game_obj.characteristics.types):
                controls_artifact = True
                break

        if not controls_artifact:
            return []

        # Find artifacts or creatures opponents control
        valid_targets = []
        for game_obj in state.objects.values():
            if (game_obj.zone == ZoneType.BATTLEFIELD and
                game_obj.controller != obj.controller):
                target_types = game_obj.characteristics.types
                if CardType.ARTIFACT in target_types or CardType.CREATURE in target_types:
                    valid_targets.append(game_obj.id)

        if not valid_targets:
            return []

        create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose an artifact or creature to tap and put a stun counter on",
            min_targets=1,
            max_targets=1,
            callback_data={'handler': handle_target_choice}
        )
        return []

    return [make_etb_trigger(obj, etb_effect)]


def waterwind_scout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Map token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Map Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Map'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- BLACK CARDS ---

def abyssal_gorestalker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, each player sacrifices two creatures of their choice."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            events.append(Event(
                type=EventType.SACRIFICE,
                payload={'player': player_id, 'count': 2, 'type': 'creature'},
                source=obj.id
            ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def chupacabra_echo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, target creature an opponent controls gets -X/-X until end of turn."""
    def handle_target_choice(choice, selected: list, game_state: GameState) -> list[Event]:
        if not selected:
            return []
        target_id = selected[0]
        target = game_state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []
        if CardType.CREATURE not in target.characteristics.types:
            return []

        # Count permanent cards in controller's graveyard (fathomless descent)
        controller = choice.callback_data.get('controller', obj.controller)
        graveyard_key = f"graveyard_{controller}"
        x_value = 0
        graveyard = game_state.zones.get(graveyard_key)
        if graveyard:
            for card_id in graveyard.objects:
                card = game_state.objects.get(card_id)
                if card:
                    card_types = card.characteristics.types
                    # Permanent types: creature, artifact, enchantment, land, planeswalker
                    if (CardType.CREATURE in card_types or
                        CardType.ARTIFACT in card_types or
                        CardType.ENCHANTMENT in card_types or
                        CardType.LAND in card_types or
                        CardType.PLANESWALKER in card_types):
                        x_value += 1

        if x_value == 0:
            return []

        return [Event(
            type=EventType.TEMPORARY_PT_CHANGE,
            payload={'object_id': target_id, 'power': -x_value, 'toughness': -x_value, 'duration': 'end_of_turn'},
            source=obj.id
        )]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find creatures opponents control
        valid_targets = []
        for game_obj in state.objects.values():
            if (game_obj.zone == ZoneType.BATTLEFIELD and
                game_obj.controller != obj.controller and
                CardType.CREATURE in game_obj.characteristics.types):
                valid_targets.append(game_obj.id)

        if not valid_targets:
            return []

        create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature an opponent controls to get -X/-X",
            min_targets=1,
            max_targets=1,
            callback_data={'handler': handle_target_choice, 'controller': obj.controller}
        )
        return []

    return [make_etb_trigger(obj, etb_effect)]


def corpses_of_the_lost_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this enchantment enters, create a 2/2 black Skeleton Pirate creature token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Skeleton Pirate Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Skeleton', 'Pirate'],
                'colors': [Color.BLACK]
            },
            source=obj.id
        )]
    # Also gives Skeletons +1/+0 and haste
    def skeleton_filter(target: GameObject, gs: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                'Skeleton' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    interceptors = [make_etb_trigger(obj, etb_effect)]
    interceptors.extend(make_static_pt_boost(obj, 1, 0, skeleton_filter))
    interceptors.append(make_keyword_grant(obj, ['haste'], skeleton_filter))
    return interceptors


def greedy_freebooter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, scry 1 and create a Treasure token."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Treasure Token',
                    'controller': obj.controller,
                    'types': [CardType.ARTIFACT],
                    'subtypes': ['Treasure'],
                    'colors': []
                },
                source=obj.id
            )
        ]
    return [make_death_trigger(obj, death_effect)]


def mephitic_draught_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this artifact enters or is put into a graveyard from the battlefield, you draw a card and lose 1 life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': -1},
                source=obj.id
            )
        ]
    return [
        make_etb_trigger(obj, effect_fn),
        make_death_trigger(obj, effect_fn)
    ]


def primordial_gnawer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, discover 3."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DISCOVER,
            payload={'player': obj.controller, 'value': 3},
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def skullcap_snail_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, target opponent exiles a card from their hand."""
    def handle_card_choice(choice, selected: list, game_state: GameState) -> list[Event]:
        """Handle the card selection from opponent's hand."""
        if not selected:
            return []
        card_id = selected[0]
        card = game_state.objects.get(card_id)
        if not card:
            return []
        return [Event(
            type=EventType.EXILE,
            payload={'object_id': card_id, 'exiled_by': obj.id},
            source=obj.id
        )]

    def handle_opponent_choice(choice, selected: list, game_state: GameState) -> list[Event]:
        """Handle the opponent selection, then prompt for card choice."""
        if not selected:
            return []
        target_opponent = selected[0]

        # Get cards from opponent's hand
        hand_key = f"hand_{target_opponent}"
        hand = game_state.zones.get(hand_key)
        if not hand or not hand.objects:
            return []

        card_ids = list(hand.objects)

        create_target_choice(
            state=game_state,
            player_id=target_opponent,  # Opponent chooses which card to exile
            source_id=obj.id,
            legal_targets=card_ids,
            prompt="Choose a card from your hand to exile",
            min_targets=1,
            max_targets=1,
            callback_data={'handler': handle_card_choice}
        )
        return []

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find opponents
        opponents = [pid for pid in state.players if pid != obj.controller]
        if not opponents:
            return []

        # If only one opponent, target them automatically
        if len(opponents) == 1:
            target_opponent = opponents[0]
            hand_key = f"hand_{target_opponent}"
            hand = state.zones.get(hand_key)
            if not hand or not hand.objects:
                return []

            card_ids = list(hand.objects)

            create_target_choice(
                state=state,
                player_id=target_opponent,
                source_id=obj.id,
                legal_targets=card_ids,
                prompt="Choose a card from your hand to exile",
                min_targets=1,
                max_targets=1,
                callback_data={'handler': handle_card_choice}
            )
            return []

        # Multiple opponents - need to choose one first
        create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=opponents,
            prompt="Choose a target opponent",
            min_targets=1,
            max_targets=1,
            callback_data={'handler': handle_opponent_choice}
        )
        return []

    return [make_etb_trigger(obj, etb_effect)]


def synapse_necromage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, create two 1/1 black Fungus creature tokens with 'This token can't block.'"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Fungus Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Fungus'],
                    'colors': [Color.BLACK]
                },
                source=obj.id
            ),
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Fungus Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Fungus'],
                    'colors': [Color.BLACK]
                },
                source=obj.id
            )
        ]
    return [make_death_trigger(obj, death_effect)]


# --- RED CARDS ---

def dinotomaton_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, target creature you control gains menace until end of turn."""
    def handle_target_choice(choice, selected: list, game_state: GameState) -> list[Event]:
        if not selected:
            return []
        target_id = selected[0]
        target = game_state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []
        if CardType.CREATURE not in target.characteristics.types:
            return []
        return [Event(
            type=EventType.KEYWORD_GRANT,
            payload={'object_id': target_id, 'keyword': 'menace', 'duration': 'end_of_turn'},
            source=obj.id
        )]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        valid_targets = []
        for game_obj in state.objects.values():
            if (game_obj.zone == ZoneType.BATTLEFIELD and
                game_obj.controller == obj.controller and
                CardType.CREATURE in game_obj.characteristics.types):
                valid_targets.append(game_obj.id)

        if not valid_targets:
            return []

        create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature you control to gain menace",
            min_targets=1,
            max_targets=1,
            callback_data={'handler': handle_target_choice}
        )
        return []

    return [make_etb_trigger(obj, etb_effect)]


def geological_appraiser_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, if you cast it, discover 3."""
    def etb_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        return (event.type == EventType.ZONE_CHANGE and
                event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD and
                event.payload.get('object_id') == source_obj.id and
                event.payload.get('was_cast', False))

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DISCOVER,
            payload={'player': obj.controller, 'value': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect, etb_filter)]


def magmatic_galleon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this Vehicle enters, it deals 5 damage to target creature an opponent controls."""
    def handle_target_choice(choice, selected: list, game_state: GameState) -> list[Event]:
        if not selected:
            return []
        target_id = selected[0]
        target = game_state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []
        if CardType.CREATURE not in target.characteristics.types:
            return []
        return [Event(
            type=EventType.DAMAGE,
            payload={'target_id': target_id, 'amount': 5, 'is_combat': False},
            source=obj.id
        )]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find creatures opponents control
        valid_targets = []
        for game_obj in state.objects.values():
            if (game_obj.zone == ZoneType.BATTLEFIELD and
                game_obj.controller != obj.controller and
                CardType.CREATURE in game_obj.characteristics.types):
                valid_targets.append(game_obj.id)

        if not valid_targets:
            return []

        create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature an opponent controls to deal 5 damage to",
            min_targets=1,
            max_targets=1,
            callback_data={'handler': handle_target_choice}
        )
        return []

    return [make_etb_trigger(obj, etb_effect)]


def plundering_pirate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Treasure token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Treasure Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def rampaging_spiketail_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, target creature you control gets +2/+0 and gains indestructible until end of turn."""
    def handle_target_choice(choice, selected: list, game_state: GameState) -> list[Event]:
        if not selected:
            return []
        target_id = selected[0]
        target = game_state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []
        if CardType.CREATURE not in target.characteristics.types:
            return []
        return [
            Event(
                type=EventType.TEMPORARY_PT_CHANGE,
                payload={'object_id': target_id, 'power': 2, 'toughness': 0, 'duration': 'end_of_turn'},
                source=obj.id
            ),
            Event(
                type=EventType.KEYWORD_GRANT,
                payload={'object_id': target_id, 'keyword': 'indestructible', 'duration': 'end_of_turn'},
                source=obj.id
            )
        ]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        valid_targets = []
        for game_obj in state.objects.values():
            if (game_obj.zone == ZoneType.BATTLEFIELD and
                game_obj.controller == obj.controller and
                CardType.CREATURE in game_obj.characteristics.types):
                valid_targets.append(game_obj.id)

        if not valid_targets:
            return []

        create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature you control to get +2/+0 and indestructible",
            min_targets=1,
            max_targets=1,
            callback_data={'handler': handle_target_choice}
        )
        return []

    return [make_etb_trigger(obj, etb_effect)]


def trumpeting_carnosaur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, discover 5."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DISCOVER,
            payload={'player': obj.controller, 'value': 5},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- GREEN CARDS ---

def armored_kincaller_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you may reveal a Dinosaur card from your hand. If you do or if you control another Dinosaur, you gain 3 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Check if we control another Dinosaur
        for obj_id, game_obj in state.objects.items():
            if (obj_id != obj.id and
                game_obj.controller == obj.controller and
                game_obj.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in game_obj.characteristics.types and
                'Dinosaur' in game_obj.characteristics.subtypes):
                return [Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': obj.controller, 'amount': 3},
                    source=obj.id
                )]
        return []
    return [make_etb_trigger(obj, etb_effect)]


def cavern_stomper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, scry 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def cenote_scout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, it explores."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.EXPLORE,
            payload={'object_id': obj.id, 'controller': obj.controller},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def coati_scavenger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, if descend 4, return target permanent card from your graveyard to your hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Descend 4 check - would need graveyard tracking
        return []
    return [make_etb_trigger(obj, etb_effect)]


def earthshaker_dreadmaw_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, draw a card for each other Dinosaur you control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        dino_count = 0
        for obj_id, game_obj in state.objects.items():
            if (obj_id != obj.id and
                game_obj.controller == obj.controller and
                game_obj.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in game_obj.characteristics.types and
                'Dinosaur' in game_obj.characteristics.subtypes):
                dino_count += 1
        if dino_count > 0:
            return [Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': dino_count},
                source=obj.id
            )]
        return []
    return [make_etb_trigger(obj, etb_effect)]


def mineshaft_spider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you may mill two cards."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def nurturing_bristleback_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a 3/3 green Dinosaur creature token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Dinosaur Token',
                'controller': obj.controller,
                'power': 3,
                'toughness': 3,
                'types': [CardType.CREATURE],
                'subtypes': ['Dinosaur'],
                'colors': [Color.GREEN]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def pathfinding_axejaw_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, it explores."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.EXPLORE,
            payload={'object_id': obj.id, 'controller': obj.controller},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def river_herald_guide_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, it explores."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.EXPLORE,
            payload={'object_id': obj.id, 'controller': obj.controller},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def sentinel_of_the_nameless_city_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature enters or attacks, create a Map token."""
    def create_map(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Map Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Map'],
                'colors': []
            },
            source=obj.id
        )]
    return [
        make_etb_trigger(obj, create_map),
        make_attack_trigger(obj, create_map)
    ]


# --- MULTICOLOR CARDS ---

def palanis_hatcher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Dinosaurs you control have haste. When this creature enters, create two 0/1 green Dinosaur Egg creature tokens."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Dinosaur Egg Token',
                    'controller': obj.controller,
                    'power': 0,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Dinosaur', 'Egg'],
                    'colors': [Color.GREEN]
                },
                source=obj.id
            ),
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Dinosaur Egg Token',
                    'controller': obj.controller,
                    'power': 0,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Dinosaur', 'Egg'],
                    'colors': [Color.GREEN]
                },
                source=obj.id
            )
        ]
    # Grant haste to other Dinosaurs
    def dino_filter(target: GameObject, gs: GameState) -> bool:
        return (target.id != obj.id and
                target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                'Dinosaur' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    return [
        make_etb_trigger(obj, etb_effect),
        make_keyword_grant(obj, ['haste'], dino_filter)
    ]


def captain_storm_cosmium_raider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever an artifact you control enters, put a +1/+1 counter on target Pirate you control."""
    def artifact_etb_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == source_obj.controller and
                CardType.ARTIFACT in entering_obj.characteristics.types)

    def artifact_etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find a Pirate to put counter on (simplified - puts on self if Pirate)
        if 'Pirate' in obj.characteristics.subtypes:
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id
            )]
        return []
    return [make_etb_trigger(obj, artifact_etb_effect, artifact_etb_filter)]


def itzquinth_firstborn_of_gishath_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Itzquinth enters, you may pay {2}. When you do, target Dinosaur you control deals damage equal to its power to another target creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would require mana payment and targeting
        return []
    return [make_etb_trigger(obj, etb_effect)]


# --- COLORLESS CARDS ---

def cartographers_companion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a Map token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Map Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Map'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def compass_gnome_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you may search your library for a basic land card or Cave card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={'player': obj.controller, 'card_type': 'land'},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def digsite_conservator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature dies, you may pay {4}. If you do, discover 4."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        # Would require mana payment
        return []
    return [make_death_trigger(obj, death_effect)]


def disruptor_wanderglyph_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature attacks, exile target card from an opponent's graveyard."""
    def handle_target_choice(choice, selected: list, game_state: GameState) -> list[Event]:
        if not selected:
            return []
        target_id = selected[0]
        target = game_state.objects.get(target_id)
        if not target or target.zone != ZoneType.GRAVEYARD:
            return []
        return [Event(
            type=EventType.EXILE,
            payload={'object_id': target_id, 'exiled_by': obj.id},
            source=obj.id
        )]

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Find cards in opponents' graveyards
        valid_targets = []
        for pid in state.players:
            if pid != obj.controller:
                graveyard_key = f"graveyard_{pid}"
                graveyard = state.zones.get(graveyard_key)
                if graveyard:
                    for card_id in graveyard.objects:
                        valid_targets.append(card_id)

        if not valid_targets:
            return []

        create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a card from an opponent's graveyard to exile",
            min_targets=1,
            max_targets=1,
            callback_data={'handler': handle_target_choice}
        )
        return []

    return [make_attack_trigger(obj, attack_effect)]


def runaway_boulder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this artifact enters, it deals 6 damage to target creature an opponent controls."""
    def handle_target_choice(choice, selected: list, game_state: GameState) -> list[Event]:
        if not selected:
            return []
        target_id = selected[0]
        target = game_state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []
        if CardType.CREATURE not in target.characteristics.types:
            return []
        return [Event(
            type=EventType.DAMAGE,
            payload={'target_id': target_id, 'amount': 6, 'is_combat': False},
            source=obj.id
        )]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find creatures opponents control
        valid_targets = []
        for game_obj in state.objects.values():
            if (game_obj.zone == ZoneType.BATTLEFIELD and
                game_obj.controller != obj.controller and
                CardType.CREATURE in game_obj.characteristics.types):
                valid_targets.append(game_obj.id)

        if not valid_targets:
            return []

        create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature an opponent controls to deal 6 damage to",
            min_targets=1,
            max_targets=1,
            callback_data={'handler': handle_target_choice}
        )
        return []

    return [make_etb_trigger(obj, etb_effect)]


def scampering_surveyor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, search your library for a basic land card or Cave card, put it onto the battlefield tapped, then shuffle."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={'player': obj.controller, 'card_type': 'land', 'put_on_battlefield': True, 'tapped': True},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def threefold_thunderhulk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """This creature enters with three +1/+1 counters on it. Whenever this creature enters or attacks, create Gnome tokens equal to its power."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 3},
            source=obj.id
        )]
    # Also creates tokens on ETB/attack but would need power query
    return [make_etb_trigger(obj, etb_effect)]


# --- ADDITIONAL WHITE CARDS ---

def kinjallis_dawnrunner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, it explores."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.EXPLORE,
            payload={'object_id': obj.id, 'controller': obj.controller},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def kutzils_flanker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you gain 2 life and scry 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id
            ),
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id
            )
        ]
    return [make_etb_trigger(obj, etb_effect)]


def mischievous_pup_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, return up to one other target permanent you control to its owner's hand."""
    def handle_target_choice(choice, selected: list, game_state: GameState) -> list[Event]:
        if not selected:
            return []
        target_id = selected[0]
        target = game_state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []
        return [Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': target_id,
                'from_zone_type': ZoneType.BATTLEFIELD,
                'to_zone_type': ZoneType.HAND,
                'to_zone': f'hand_{target.owner}'
            },
            source=obj.id
        )]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find other permanents controller controls
        valid_targets = []
        for game_obj in state.objects.values():
            if (game_obj.id != obj.id and
                game_obj.zone == ZoneType.BATTLEFIELD and
                game_obj.controller == obj.controller):
                valid_targets.append(game_obj.id)

        if not valid_targets:
            return []

        create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a permanent you control to return to hand (or none)",
            min_targets=0,  # "up to one"
            max_targets=1,
            callback_data={'handler': handle_target_choice}
        )
        return []

    return [make_etb_trigger(obj, etb_effect)]


def oltec_archaeologists_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, scry 3."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def glorifier_of_suffering_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you may sacrifice another creature or artifact."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would require sacrifice choice - placeholder
        return []
    return [make_etb_trigger(obj, etb_effect)]


# --- ADDITIONAL BLUE CARDS ---

def kitesail_larcenist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, choose up to one target artifact or creature each player controls."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Complex targeting - placeholder
        return []
    return [make_etb_trigger(obj, etb_effect)]


def tishanas_tidebinder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, counter up to one target activated or triggered ability."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would require ability targeting - placeholder
        return []
    return [make_etb_trigger(obj, etb_effect)]


def sinuous_benthisaur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, look at top X cards based on Caves."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Cave counting - simplified
        return [Event(
            type=EventType.LOOK_AT_TOP,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- ADDITIONAL BLACK CARDS ---

def deepcavern_bat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    Flying, lifelink.
    When this creature enters, look at target opponent's hand.
    You may exile a nonland card from it until this creature leaves the battlefield.
    """
    # Track which card we exiled (mutable container for closure)
    exiled_card_ref = {'id': None, 'owner': None}

    def handle_exile_choice(choice, selected: list, game_state: GameState) -> list[Event]:
        """Handle the choice callback for Deep-Cavern Bat's exile effect."""
        if not selected:
            return []

        card_id = selected[0]

        if card_id not in game_state.objects:
            return []

        card = game_state.objects[card_id]

        # Store reference to exiled card for return trigger
        exiled_card_ref['id'] = card_id
        exiled_card_ref['owner'] = card.owner

        # Exile the card
        return [Event(
            type=EventType.EXILE,
            payload={
                'object_id': card_id,
                'exiled_by': obj.id
            },
            source=obj.id
        )]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Find opponents
        opponents = [pid for pid in state.players if pid != obj.controller]
        if not opponents:
            return []

        # For now, target first opponent (could add opponent choice later)
        target_opponent = opponents[0]

        # Get nonland cards from opponent's hand
        hand_key = f"hand_{target_opponent}"
        if hand_key not in state.zones:
            return []

        hand = state.zones[hand_key]
        valid_choices = []

        for card_id in hand.objects:
            card = state.objects.get(card_id)
            if card and CardType.LAND not in card.characteristics.types:
                valid_choices.append(card_id)

        if not valid_choices:
            return []

        # Create choice for the controller to pick a nonland card to exile (may = min 0)
        create_target_choice(
            state,
            obj.controller,
            obj.id,
            valid_choices,
            prompt="Look at opponent's hand. Choose a nonland card to exile (or none):",
            min_targets=0,
            max_targets=1,
            callback_data={
                'handler': handle_exile_choice,
                'bat_id': obj.id,
                'target_opponent': target_opponent
            }
        )
        return []

    def leaves_battlefield_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        """Trigger when Deep-Cavern Bat leaves the battlefield."""
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('object_id') != source_obj.id:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        return True

    def leaves_battlefield_effect(event: Event, state: GameState) -> list[Event]:
        """Return the exiled card to its owner's hand."""
        exiled_id = exiled_card_ref.get('id')
        exiled_owner = exiled_card_ref.get('owner')

        if not exiled_id or exiled_id not in state.objects:
            return []

        exiled_card = state.objects[exiled_id]

        # Only return if still in exile
        if exiled_card.zone != ZoneType.EXILE:
            return []

        # Return to owner's hand
        return [Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': exiled_id,
                'from_zone': 'exile',
                'to_zone': f'hand_{exiled_owner}',
                'from_zone_type': ZoneType.EXILE,
                'to_zone_type': ZoneType.HAND
            },
            source=obj.id
        )]

    # Create leaves-the-battlefield interceptor
    def ltb_trigger_filter(event: Event, state: GameState) -> bool:
        return leaves_battlefield_filter(event, state, obj)

    def ltb_trigger_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = leaves_battlefield_effect(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    ltb_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=ltb_trigger_filter,
        handler=ltb_trigger_handler,
        duration='until_leaves'  # Fire once when leaving, then clean up
    )

    return [make_etb_trigger(obj, etb_effect), ltb_interceptor]


def deathcap_marionette_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, you may mill two cards."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def starving_revenant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, surveil 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def bringer_of_the_last_gift_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, each player sacrifices all other creatures."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            events.append(Event(
                type=EventType.SACRIFICE_ALL,
                payload={'player': player_id, 'type': 'creature', 'except': obj.id},
                source=obj.id
            ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def queens_bay_paladin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature enters or attacks, return up to one target Vampire from graveyard."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Graveyard return - placeholder
        return []
    return [
        make_etb_trigger(obj, effect_fn),
        make_attack_trigger(obj, effect_fn)
    ]


# --- ADDITIONAL RED CARDS ---

def bonehoard_dracosaur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your upkeep, exile the top two cards."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.EXILE_TOP,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_upkeep_trigger(obj, upkeep_effect)]


def belligerent_yearling_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another Dinosaur you control enters, you may have this creature's base power become equal to that creature's power."""
    def dino_etb_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == source_obj.id:
            return False
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == source_obj.controller and
                CardType.CREATURE in entering_obj.characteristics.types and
                'Dinosaur' in entering_obj.characteristics.subtypes)

    def dino_effect(event: Event, state: GameState) -> list[Event]:
        # Power change - placeholder
        return []
    return [make_etb_trigger(obj, dino_effect, dino_etb_filter)]


def burning_sun_cavalry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature attacks or blocks while you control a Dinosaur, gets +1/+1."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Check for dinosaur control - simplified
        for obj_id, game_obj in state.objects.items():
            if (game_obj.controller == obj.controller and
                game_obj.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in game_obj.characteristics.types and
                'Dinosaur' in game_obj.characteristics.subtypes):
                return []  # Would apply +1/+1 boost
        return []
    return [make_attack_trigger(obj, attack_effect)]


def etalis_favor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this Aura enters, discover 3."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DISCOVER,
            payload={'player': obj.controller, 'value': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- ADDITIONAL GREEN CARDS ---

def jadelight_spelunker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, it explores X times."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # X is from mana spent - simplified to 1 explore
        return [Event(
            type=EventType.EXPLORE,
            payload={'object_id': obj.id, 'controller': obj.controller},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def spelunking_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this enchantment enters, draw a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def malamet_brawler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature attacks, target attacking creature gains trample until end of turn."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Trample grant - placeholder
        return []
    return [make_attack_trigger(obj, attack_effect)]


def malamet_scythe_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this Equipment enters, attach it to target creature you control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Auto-attach - placeholder
        return []
    return [make_etb_trigger(obj, etb_effect)]


# --- ADDITIONAL MULTICOLOR CARDS ---

def anim_pakal_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you attack with non-Gnome creatures, put a +1/+1 counter and create Gnome tokens."""
    def attack_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        # Check if we're attacking with non-Gnomes
        return True

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def deepfathom_echo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of combat on your turn, this creature explores."""
    def combat_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.EXPLORE,
            payload={'object_id': obj.id, 'controller': obj.controller},
            source=obj.id
        )]
    # Combat start trigger - simplified as upkeep
    return []


def akawalli_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Descend 4 - gets +2/+2 and trample when 4+ permanent cards in graveyard."""
    def descend_filter(target: GameObject, gs: GameState) -> bool:
        # Count permanent cards in graveyard
        return target.id == obj.id
    # This is a static ability - would need graveyard checking
    return []


def zoyowa_lavatongue_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your end step, if you descended, opponents may discard or sacrifice."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        # Descended check - simplified
        return []
    return [make_end_step_trigger(obj, end_step_effect)]


def vito_fanatic_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you sacrifice another permanent, you gain 2 life (first time)."""
    # Sacrifice trigger - placeholder
    return []


# --- ADDITIONAL COLORLESS CARDS ---

def roaming_throne_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Triggered abilities of creatures of the chosen type trigger an additional time."""
    # Complex ability doubling - placeholder
    return []


def chimil_inner_sun_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At the beginning of your end step, discover 5."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DISCOVER,
            payload={'player': obj.controller, 'value': 5},
            source=obj.id
        )]
    return [make_end_step_trigger(obj, end_step_effect)]


def careening_mine_cart_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this Vehicle attacks, create a Treasure token."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Treasure Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def hoverstone_pilgrim_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ward 2 - placeholder static ability."""
    return []


# --- LAND CARDS WITH ATTACK TRIGGERS ---

def restless_anchorage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this land attacks, create a Map token."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Map Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Map'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def restless_prairie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this land attacks, other creatures you control get +1/+1 until end of turn."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Temporary P/T boost - placeholder
        return []
    return [make_attack_trigger(obj, attack_effect)]


def restless_reef_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this land attacks, target player mills four cards."""
    def handle_target_choice(choice, selected: list, game_state: GameState) -> list[Event]:
        if not selected:
            return []
        target_player = selected[0]
        return [Event(
            type=EventType.MILL,
            payload={'player': target_player, 'amount': 4},
            source=obj.id
        )]

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # All players are valid targets
        valid_targets = list(state.players.keys())
        if not valid_targets:
            return []

        create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a player to mill four cards",
            min_targets=1,
            max_targets=1,
            callback_data={'handler': handle_target_choice}
        )
        return []

    return [make_attack_trigger(obj, attack_effect)]


def restless_ridgeline_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this land attacks, another target attacking creature gets +2/+0."""
    def handle_target_choice(choice, selected: list, game_state: GameState) -> list[Event]:
        if not selected:
            return []
        target_id = selected[0]
        target = game_state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []
        if CardType.CREATURE not in target.characteristics.types:
            return []
        return [Event(
            type=EventType.TEMPORARY_PT_CHANGE,
            payload={'object_id': target_id, 'power': 2, 'toughness': 0, 'duration': 'end_of_turn'},
            source=obj.id
        )]

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Find other attacking creatures
        valid_targets = []
        for game_obj in state.objects.values():
            if (game_obj.id != obj.id and
                game_obj.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in game_obj.characteristics.types):
                obj_state = getattr(game_obj, 'state', None)
                if obj_state and getattr(obj_state, 'attacking', False):
                    valid_targets.append(game_obj.id)

        if not valid_targets:
            return []

        create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose an attacking creature to get +2/+0",
            min_targets=1,
            max_targets=1,
            callback_data={'handler': handle_target_choice}
        )
        return []

    return [make_attack_trigger(obj, attack_effect)]


def restless_vents_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this land attacks, you may discard a card. If you do, draw a card."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Discard/draw - simplified to just draw for placeholder
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def pit_of_offerings_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this land enters, exile up to three target cards from graveyards."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Targeting graveyard cards - placeholder
        return []
    return [make_etb_trigger(obj, etb_effect)]


# =============================================================================
# SPELL RESOLVE FUNCTIONS
# =============================================================================

def _get_lost_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Get Lost after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    target_types = target.characteristics.types
    if (CardType.CREATURE not in target_types and
        CardType.ENCHANTMENT not in target_types and
        CardType.PLANESWALKER not in target_types):
        return []

    target_controller = target.controller
    events = [
        Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': target_id},
            source=choice.source_id
        )
    ]
    # Create two Map tokens for the controller
    for _ in range(2):
        events.append(Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Map Token',
                'controller': target_controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Map'],
                'colors': []
            },
            source=choice.source_id
        ))
    return events


def get_lost_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Get Lost: Destroy target creature, enchantment, or planeswalker."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Get Lost":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "get_lost_spell"

    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            target_types = obj.characteristics.types
            if (CardType.CREATURE in target_types or
                CardType.ENCHANTMENT in target_types or
                CardType.PLANESWALKER in target_types):
                valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature, enchantment, or planeswalker to destroy",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _get_lost_execute
    return []


def _cosmium_blast_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Cosmium Blast after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    return [Event(
        type=EventType.DAMAGE,
        payload={'target_id': target_id, 'amount': 4, 'is_combat': False},
        source=choice.source_id
    )]


def cosmium_blast_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Cosmium Blast: Deal 4 damage to target attacking or blocking creature."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Cosmium Blast":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "cosmium_blast_spell"

    # Find attacking or blocking creatures
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
            obj_state = getattr(obj, 'state', None)
            if obj_state and (getattr(obj_state, 'attacking', False) or getattr(obj_state, 'blocking', False)):
                valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose an attacking or blocking creature to deal 4 damage to",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _cosmium_blast_execute
    return []


def _quicksand_whirlpool_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Quicksand Whirlpool after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    return [Event(
        type=EventType.EXILE,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def quicksand_whirlpool_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Quicksand Whirlpool: Exile target creature."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Quicksand Whirlpool":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "quicksand_whirlpool_spell"

    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
            valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to exile",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _quicksand_whirlpool_execute
    return []


def _out_of_air_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Out of Air after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.STACK:
        return []

    return [Event(
        type=EventType.COUNTER_SPELL,
        payload={'spell_id': target_id},
        source=choice.source_id
    )]


def out_of_air_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Out of Air: Counter target spell."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Out of Air":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "out_of_air_spell"

    # Find spells on the stack that aren't this spell
    valid_targets = []
    if stack_zone:
        for obj_id in stack_zone.objects:
            if obj_id != spell_id:
                obj = state.objects.get(obj_id)
                if obj:
                    valid_targets.append(obj_id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a spell to counter",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _out_of_air_execute
    return []


def _ray_of_ruin_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Ray of Ruin after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    target_types = target.characteristics.types
    target_supertypes = target.characteristics.supertypes or set()
    if not (CardType.CREATURE in target_types or
            'Vehicle' in (target.characteristics.subtypes or set()) or
            (CardType.LAND in target_types and 'Basic' not in target_supertypes)):
        return []

    return [
        Event(
            type=EventType.EXILE,
            payload={'object_id': target_id},
            source=choice.source_id
        ),
        Event(
            type=EventType.SCRY,
            payload={'player': choice.player, 'amount': 1},
            source=choice.source_id
        )
    ]


def ray_of_ruin_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Ray of Ruin: Exile target creature, Vehicle, or nonbasic land."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Ray of Ruin":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "ray_of_ruin_spell"

    valid_targets = []
    for obj in state.objects.values():
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        target_types = obj.characteristics.types
        subtypes = obj.characteristics.subtypes or set()
        supertypes = obj.characteristics.supertypes or set()

        # Creature
        if CardType.CREATURE in target_types:
            valid_targets.append(obj.id)
        # Vehicle
        elif 'Vehicle' in subtypes:
            valid_targets.append(obj.id)
        # Nonbasic land
        elif CardType.LAND in target_types and 'Basic' not in supertypes:
            valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature, Vehicle, or nonbasic land to exile",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _ray_of_ruin_execute
    return []


def _abrade_creature_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Abrade creature mode."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    return [Event(
        type=EventType.DAMAGE,
        payload={'target_id': target_id, 'amount': 3, 'is_combat': False},
        source=choice.source_id
    )]


def _abrade_artifact_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Abrade artifact mode."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.ARTIFACT not in target.characteristics.types:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def abrade_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Abrade: Choose one - 3 damage to creature OR destroy artifact."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Abrade":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "abrade_spell"

    # Find valid creature and artifact targets
    creature_targets = []
    artifact_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                creature_targets.append(obj.id)
            if CardType.ARTIFACT in obj.characteristics.types:
                artifact_targets.append(obj.id)

    # Create modal choice
    modes = []
    if creature_targets:
        modes.append({'id': 'damage', 'text': 'Deal 3 damage to target creature', 'targets': creature_targets})
    if artifact_targets:
        modes.append({'id': 'destroy', 'text': 'Destroy target artifact', 'targets': artifact_targets})

    if not modes:
        return []

    # For simplicity, if both modes available, present creature damage first
    # A proper implementation would use a modal choice system
    if creature_targets:
        choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            legal_targets=creature_targets,
            prompt="Choose a creature to deal 3 damage to",
            min_targets=1,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = _abrade_creature_execute
    else:
        choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            legal_targets=artifact_targets,
            prompt="Choose an artifact to destroy",
            min_targets=1,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = _abrade_artifact_execute

    return []


def _rumbling_rockslide_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Rumbling Rockslide after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    # Count lands controller controls
    land_count = 0
    caster_id = choice.player
    for obj in choice.callback_data.get('state_snapshot', state).objects.values():
        if (obj.controller == caster_id and
            obj.zone == ZoneType.BATTLEFIELD and
            CardType.LAND in obj.characteristics.types):
            land_count += 1

    return [Event(
        type=EventType.DAMAGE,
        payload={'target_id': target_id, 'amount': land_count, 'is_combat': False},
        source=choice.source_id
    )]


def rumbling_rockslide_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Rumbling Rockslide: Deal damage to target creature equal to lands you control."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Rumbling Rockslide":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "rumbling_rockslide_spell"

    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
            valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to deal damage to (equal to lands you control)",
        min_targets=1,
        max_targets=1,
        callback_data={'state_snapshot': state}
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _rumbling_rockslide_execute
    return []


def _triumphant_chomp_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Triumphant Chomp after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    # Find greatest power among Dinosaurs controller controls
    caster_id = choice.player
    max_dino_power = 0
    for obj in choice.callback_data.get('state_snapshot', state).objects.values():
        if (obj.controller == caster_id and
            obj.zone == ZoneType.BATTLEFIELD and
            CardType.CREATURE in obj.characteristics.types and
            'Dinosaur' in (obj.characteristics.subtypes or set())):
            power = obj.characteristics.power or 0
            if power > max_dino_power:
                max_dino_power = power

    damage = max(2, max_dino_power)

    return [Event(
        type=EventType.DAMAGE,
        payload={'target_id': target_id, 'amount': damage, 'is_combat': False},
        source=choice.source_id
    )]


def triumphant_chomp_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Triumphant Chomp: Deal damage equal to 2 or greatest Dinosaur power."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Triumphant Chomp":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "triumphant_chomp_spell"

    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
            valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to deal damage to",
        min_targets=1,
        max_targets=1,
        callback_data={'state_snapshot': state}
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _triumphant_chomp_execute
    return []


def _huatlis_final_strike_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Huatli's Final Strike after both targets selected."""
    if len(selected) < 2:
        return []

    your_creature_id = selected[0]
    opponent_creature_id = selected[1]

    your_creature = state.objects.get(your_creature_id)
    opponent_creature = state.objects.get(opponent_creature_id)

    if not your_creature or your_creature.zone != ZoneType.BATTLEFIELD:
        return []
    if not opponent_creature or opponent_creature.zone != ZoneType.BATTLEFIELD:
        return []

    # Your creature gets +1/+0, then deals damage equal to its power
    power = (your_creature.characteristics.power or 0) + 1

    return [Event(
        type=EventType.DAMAGE,
        payload={'target_id': opponent_creature_id, 'amount': power, 'is_combat': False},
        source=choice.source_id
    )]


def huatlis_final_strike_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Huatli's Final Strike."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Huatli's Final Strike":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "huatlis_final_strike_spell"

    # Find creatures you control
    your_creatures = []
    for obj in state.objects.values():
        if (obj.zone == ZoneType.BATTLEFIELD and
            obj.controller == caster_id and
            CardType.CREATURE in obj.characteristics.types):
            your_creatures.append(obj.id)

    # Find creatures opponents control
    opponent_creatures = []
    for obj in state.objects.values():
        if (obj.zone == ZoneType.BATTLEFIELD and
            obj.controller != caster_id and
            CardType.CREATURE in obj.characteristics.types):
            opponent_creatures.append(obj.id)

    if not your_creatures or not opponent_creatures:
        return []

    # For simplicity, combine both target lists with first being your creature
    # A proper implementation would have two-step targeting
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=your_creatures + opponent_creatures,
        prompt="Choose your creature, then an opponent's creature",
        min_targets=2,
        max_targets=2
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _huatlis_final_strike_execute
    return []


def _join_the_dead_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Join the Dead after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    # Count permanent cards in controller's graveyard for descend 4 check
    caster_id = choice.player
    graveyard_key = f"graveyard_{caster_id}"
    perm_count = 0
    graveyard = state.zones.get(graveyard_key)
    if graveyard:
        for card_id in graveyard.objects:
            card = state.objects.get(card_id)
            if card:
                card_types = card.characteristics.types
                if (CardType.CREATURE in card_types or
                    CardType.ARTIFACT in card_types or
                    CardType.ENCHANTMENT in card_types or
                    CardType.LAND in card_types or
                    CardType.PLANESWALKER in card_types):
                    perm_count += 1

    # -10/-10 if descend 4, else -5/-5
    debuff = -10 if perm_count >= 4 else -5

    return [Event(
        type=EventType.TEMPORARY_PT_CHANGE,
        payload={'object_id': target_id, 'power': debuff, 'toughness': debuff, 'duration': 'end_of_turn'},
        source=choice.source_id
    )]


def join_the_dead_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Join the Dead: Target creature gets -5/-5 (or -10/-10 with descend 4)."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Join the Dead":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "join_the_dead_spell"

    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
            valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to get -5/-5 (or -10/-10 with descend 4)",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _join_the_dead_execute
    return []


def _staggering_size_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Staggering Size after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    return [
        Event(
            type=EventType.TEMPORARY_PT_CHANGE,
            payload={'object_id': target_id, 'power': 3, 'toughness': 3, 'duration': 'end_of_turn'},
            source=choice.source_id
        ),
        Event(
            type=EventType.KEYWORD_GRANT,
            payload={'object_id': target_id, 'keyword': 'trample', 'duration': 'end_of_turn'},
            source=choice.source_id
        )
    ]


def staggering_size_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Staggering Size: +3/+3 and trample until end of turn."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Staggering Size":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "staggering_size_spell"

    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
            valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to get +3/+3 and trample",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _staggering_size_execute
    return []


def _brackish_blunder_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Brackish Blunder after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    # Check if tapped for Map token creation
    is_tapped = getattr(target.state, 'tapped', False) if hasattr(target, 'state') else False
    caster_id = choice.player

    events = [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.HAND,
            'to_zone': f'hand_{target.owner}'
        },
        source=choice.source_id
    )]

    if is_tapped:
        events.append(Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Map Token',
                'controller': caster_id,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Map'],
                'colors': []
            },
            source=choice.source_id
        ))

    return events


def brackish_blunder_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Brackish Blunder: Return target creature to hand, if tapped create Map."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Brackish Blunder":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "brackish_blunder_spell"

    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
            valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to return to hand",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _brackish_blunder_execute
    return []


def _acrobatic_leap_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Acrobatic Leap after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    if CardType.CREATURE not in target.characteristics.types:
        return []

    return [
        Event(
            type=EventType.TEMPORARY_PT_CHANGE,
            payload={'object_id': target_id, 'power': 1, 'toughness': 3, 'duration': 'end_of_turn'},
            source=choice.source_id
        ),
        Event(
            type=EventType.KEYWORD_GRANT,
            payload={'object_id': target_id, 'keyword': 'flying', 'duration': 'end_of_turn'},
            source=choice.source_id
        ),
        Event(
            type=EventType.UNTAP,
            payload={'object_id': target_id},
            source=choice.source_id
        )
    ]


def acrobatic_leap_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Acrobatic Leap: +1/+3, flying until end of turn, untap."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Acrobatic Leap":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "acrobatic_leap_spell"

    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
            valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to get +1/+3, flying, and untap",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _acrobatic_leap_execute
    return []


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


# --- WHITE (additional) ---

def adaptive_gemguard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tap two artifacts/creatures: +1/+1 counter on this. Sorcery-speed activated ability."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated ability with multi-permanent tap cost and sorcery speed
        return []
    return [make_etb_trigger(obj, effect_fn)]


def attentive_sunscribe_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this creature becomes tapped, scry 1."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_tap_trigger(obj, effect_fn)]


def bat_colony_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: create Bat tokens equal to mana from a Cave spent. Cave ETB: +1/+1 counter on target."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: tracking mana sources spent on cast not modeled
        return []

    def cave_etb_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == source_obj.controller and
                'Cave' in entering_obj.characteristics.subtypes)

    def cave_etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: requires target choice for the +1/+1 counter
        return []

    return [
        make_etb_trigger(obj, etb_effect),
        make_etb_trigger(obj, cave_etb_effect, filter_fn=cave_etb_filter),
    ]


def clayfired_bricks_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, search library for basic Plains, gain 2 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.SEARCH_LIBRARY,
                payload={'player': obj.controller, 'card_type': 'basic_land', 'subtype': 'Plains', 'destination': 'hand'},
                source=obj.id
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id
            ),
        ]
    return [make_etb_trigger(obj, etb_effect)]


def dauntless_dismantler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Opponents' artifacts enter tapped. Activated: destroy each artifact with mana value X."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: enter-tapped replacement for opponents' artifacts and X-cost activated destroy
        return []
    return [make_etb_trigger(obj, effect_fn)]


def deconstruction_hammer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment grants +1/+1 and a sac-to-destroy ability."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: equipment with granted activated abilities
        return []
    return [make_etb_trigger(obj, effect_fn)]


def dusk_rose_reliquary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Additional sac cost. Ward {2}. ETB: exile target until this leaves."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: exile-until-leaves with target choice
        return []
    return [make_etb_trigger(obj, etb_effect)]


def envoy_of_okinec_ahau_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{4}{W}: Create a 1/1 colorless Gnome artifact creature token."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated mana-cost abilities not modeled here
        return []
    return [make_etb_trigger(obj, effect_fn)]


def fabrication_foundry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Mana ability + activated graveyard recursion."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated abilities and exile-cost-X recursion
        return []
    return [make_etb_trigger(obj, effect_fn)]


def guardian_of_the_great_door_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Additional cost: tap four. Flying."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: additional-cost on cast not modeled (flying granted via card abilities)
        return []
    return [make_etb_trigger(obj, effect_fn)]


def might_of_the_ancestors_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Beginning of combat on your turn: target creature gets +2/+0 and gains vigilance until EOT."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: beginning-of-combat trigger with targeted EOT P/T+keyword
        return []

    def combat_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.COMBAT_DECLARED, EventType.PHASE_START):
            return False
        if event.type == EventType.PHASE_START and event.payload.get('phase') != 'beginning_of_combat':
            return False
        return state.active_player == obj.controller

    def combat_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(event, state))

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_filter,
        handler=combat_handler,
        duration='while_on_battlefield'
    )]


def petrify_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura: enchanted permanent can't attack/block/activate."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: aura attached restriction (can't attack/block/activate)
        return []
    return [make_etb_trigger(obj, effect_fn)]


def resplendent_angel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """End step: if you gained 5+ life this turn, create 4/4 Angel token."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        gained = state.turn_data.get(f'life_gained_{obj.controller}', 0)
        if gained < 5:
            return []
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Angel Token',
                'controller': obj.controller,
                'power': 4,
                'toughness': 4,
                'types': [CardType.CREATURE],
                'subtypes': ['Angel'],
                'colors': [Color.WHITE],
                'keywords': ['flying', 'vigilance']
            },
            source=obj.id
        )]
    # Triggers each end step (for any player)
    return [make_end_step_trigger(obj, end_step_effect, controller_only=False)]


def ruinlurker_bat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, lifelink. End step: if descended this turn, scry 1."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        if not state.turn_data.get(f'descended_{obj.controller}', False):
            return []
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_end_step_trigger(obj, end_step_effect)]


def thousand_moons_crackshot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks, may pay {2}{W}. When you do, tap target creature."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: optional cost prompt then tap target on payment
        return []
    return [make_attack_trigger(obj, attack_effect)]


def thousand_moons_infantry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Untap during each other player's untap step."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: extra untap during opponents' untap step
        return []
    return [make_etb_trigger(obj, effect_fn)]


def vanguard_of_the_rose_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{1}, sac another: gain indestructible until EOT and tap."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated ability with sacrifice cost and EOT keyword grant
        return []
    return [make_etb_trigger(obj, effect_fn)]


def warden_of_the_inner_sky_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Has flying/vigilance with 3+ counters; tap-3 to add counter and scry."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: counter-conditional keywords and multi-permanent-tap activated ability
        return []

    # Conditional keyword grant via QUERY_ABILITIES
    def ability_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        live = state.objects.get(obj.id)
        if not live:
            return False
        return sum(live.state.counters.values()) >= 3

    def ability_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []))
        for kw in ('flying', 'vigilance'):
            if kw not in granted:
                granted.append(kw)
        new_event.payload['granted'] = granted
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [
        make_etb_trigger(obj, effect_fn),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=ability_filter,
            handler=ability_handler,
            duration='while_on_battlefield'
        ),
    ]


def akal_pakal_first_among_equals_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Each player's end step: if an artifact entered under your control this turn, look at top 2, keep 1, mill 1."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        if not state.turn_data.get(f'artifact_etb_{obj.controller}', False):
            return []
        return [
            Event(
                type=EventType.LOOK_AT_TOP,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id
            ),
            Event(
                type=EventType.MILL,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            ),
        ]
    return [make_end_step_trigger(obj, end_step_effect, controller_only=False)]


# --- BLUE (additional) ---

def deeproot_pilgrimage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever one or more nontoken Merfolk you control become tapped, create a 1/1 Merfolk token."""
    def tap_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.TAP:
            return False
        target = state.objects.get(event.payload.get('object_id'))
        if not target:
            return False
        if target.controller != obj.controller:
            return False
        if target.state.is_token:
            return False
        return ('Merfolk' in target.characteristics.subtypes and
                CardType.CREATURE in target.characteristics.types)

    def tap_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Merfolk Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Merfolk'],
                    'colors': [Color.BLUE],
                    'keywords': ['hexproof'],
                },
                source=obj.id
            )]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=tap_filter,
        handler=tap_handler,
        duration='while_on_battlefield'
    )]


def eaten_by_piranhas_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura: enchanted creature loses abilities and is a 1/1 black Skeleton."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: type-change + base-stat override aura
        return []
    return [make_etb_trigger(obj, effect_fn)]


def frilled_cavewurm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Descend 4: gets +2/+0 with 4+ permanent cards in graveyard."""
    def affects_self(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        graveyard = state.zones.get(f"graveyard_{obj.controller}")
        if not graveyard:
            return False
        perm_count = 0
        for cid in graveyard.objects:
            card = state.objects.get(cid)
            if not card:
                continue
            ts = card.characteristics.types
            if (CardType.CREATURE in ts or CardType.ARTIFACT in ts or
                CardType.ENCHANTMENT in ts or CardType.LAND in ts or
                CardType.PLANESWALKER in ts):
                perm_count += 1
        return perm_count >= 4

    return make_static_pt_boost(obj, 2, 0, affects_self)


def hermitic_nautilus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{1}{U}: +3/-3 until EOT."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated EOT P/T modifier
        return []
    return [make_etb_trigger(obj, effect_fn)]


def malcolm_alluring_scoundrel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to player: chorus counter + draw/discard. 4+ chorus: may cast discarded."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        # Combat damage to a player adds chorus counter and triggers loot
        if not event.payload.get('is_combat'):
            return []
        target = event.payload.get('target')
        if target not in state.players:
            return []
        return [
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': 'chorus', 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.DISCARD,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            ),
            # engine gap: cast-without-paying-cost branch when 4+ chorus counters
        ]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]


def marauding_brinefang_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ward {3} and islandcycling. No persistent abilities to wire."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: ward and cycling are static cost-replacement abilities
        return []
    return [make_etb_trigger(obj, effect_fn)]


def merfolk_cavediver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a creature you control explores, this gets +1/+0 and is unblockable until EOT."""
    def explore_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.EXPLORE:
            return False
        explorer = state.objects.get(event.payload.get('object_id'))
        if not explorer:
            return False
        return explorer.controller == obj.controller

    def explore_handler(event: Event, state: GameState) -> InterceptorResult:
        # engine gap: EOT P/T boost + EOT unblockable
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=explore_filter,
        handler=explore_handler,
        duration='while_on_battlefield'
    )]


def oaken_siren_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, vigilance, and an artifact-only mana ability."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: restricted mana ability
        return []
    return [make_etb_trigger(obj, effect_fn)]


def orazca_puzzledoor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{1}, {T}, sacrifice: top-2, keep one, mill one."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated ability with tap+sac cost
        return []
    return [make_etb_trigger(obj, effect_fn)]


def pirate_hat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment with granted attack-trigger loot."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: equipment with granted triggered ability
        return []
    return [make_etb_trigger(obj, effect_fn)]


def shipwreck_sentry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Defender; can attack as if no defender if an artifact entered under your control this turn."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: conditional defender removal based on per-turn state
        return []
    return [make_etb_trigger(obj, effect_fn)]


def song_of_stupefaction_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura: ETB may mill 2; -X/-0 where X = permanent cards in graveyard."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: optional mill prompt and dynamic -X/-0 aura
        return []
    return [make_etb_trigger(obj, etb_effect)]


def subterranean_schooner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever attacks: target creature that crewed it explores."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: crew-tracking + targeted explore
        return []
    return [make_attack_trigger(obj, attack_effect)]


def zoetic_glyph_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura: enchanted artifact becomes 5/4 Golem creature. When this is put into GY from BF, discover 3."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DISCOVER,
            payload={'player': obj.controller, 'value': 3},
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


# --- BLACK (additional) ---

def acolyte_of_aclazotz_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}, sac another creature/artifact: each opponent loses 1, you gain 1."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated ability with tap+sac cost
        return []
    return [make_etb_trigger(obj, effect_fn)]


def bloodletter_of_aclazotz_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying. Replacement: opponent loses life on your turn, lose double instead."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: replacement effect doubling life loss to opponents on your turn
        return []
    return [make_etb_trigger(obj, effect_fn)]


def bloodthorn_flail_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment +2/+1; equip cost {3} or discard a card."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: equipment with alternative equip cost
        return []
    return [make_etb_trigger(obj, effect_fn)]


def broodrage_mycoid_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """End step: if descended, create 1/1 black Fungus token (can't block)."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        if not state.turn_data.get(f'descended_{obj.controller}', False):
            return []
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Fungus Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Fungus'],
                'colors': [Color.BLACK],
                'keywords': ['cant_block'],
            },
            source=obj.id
        )]
    return [make_end_step_trigger(obj, end_step_effect)]


def canonized_in_blood_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """End step: if descended, +1/+1 counter on target creature you control. Activated: sac for 4/3 token."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        if not state.turn_data.get(f'descended_{obj.controller}', False):
            return []
        # engine gap: targeted +1/+1 counter requires choice
        return []
    return [make_end_step_trigger(obj, end_step_effect)]


def dead_weight_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aura: enchanted creature gets -2/-2."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: aura with continuous P/T adjustment to target permanent
        return []
    return [make_etb_trigger(obj, effect_fn)]


def deep_goblin_skulltaker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace. End step: if descended, +1/+1 counter on this."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        if not state.turn_data.get(f'descended_{obj.controller}', False):
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_end_step_trigger(obj, end_step_effect)]


def echo_of_dusk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Descend 4: this gets +1/+1 and lifelink with 4+ permanent cards in graveyard."""
    def descend_check(state: GameState) -> bool:
        graveyard = state.zones.get(f"graveyard_{obj.controller}")
        if not graveyard:
            return False
        perm_count = 0
        for cid in graveyard.objects:
            card = state.objects.get(cid)
            if not card:
                continue
            ts = card.characteristics.types
            if (CardType.CREATURE in ts or CardType.ARTIFACT in ts or
                CardType.ENCHANTMENT in ts or CardType.LAND in ts or
                CardType.PLANESWALKER in ts):
                perm_count += 1
        return perm_count >= 4

    def affects_self(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id and descend_check(state)

    interceptors = list(make_static_pt_boost(obj, 1, 1, affects_self))

    def ability_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        return descend_check(state)

    def ability_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []))
        if 'lifelink' not in granted:
            granted.append('lifelink')
        new_event.payload['granted'] = granted
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=ability_filter,
        handler=ability_handler,
        duration='while_on_battlefield'
    ))
    return interceptors


def fungal_fortitude_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flash. Aura: +2/+0; when enchanted creature dies, return tapped."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: aura with delayed return-from-graveyard trigger
        return []
    return [make_etb_trigger(obj, effect_fn)]


def gargantuan_leech_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Costs {1} less per Cave you control or in graveyard. Lifelink."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: cost reduction based on Caves (lifelink granted via card text)
        return []
    return [make_etb_trigger(obj, effect_fn)]


def preacher_of_the_schism_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch. Attacks player with most life: create 1/1 Vampire token. Attacks while you have most life: draw and lose 1."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Identify attacked player
        defender_id = event.payload.get('defender_id') or event.payload.get('defender')
        events: list[Event] = []
        if defender_id and defender_id in state.players:
            life_values = {p.id: p.life for p in state.players.values()}
            max_life = max(life_values.values())
            target_life = life_values.get(defender_id, 0)
            if target_life == max_life:
                events.append(Event(
                    type=EventType.OBJECT_CREATED,
                    payload={
                        'name': 'Vampire Token',
                        'controller': obj.controller,
                        'power': 1,
                        'toughness': 1,
                        'types': [CardType.CREATURE],
                        'subtypes': ['Vampire'],
                        'colors': [Color.WHITE],
                        'keywords': ['lifelink'],
                    },
                    source=obj.id
                ))
            ctrl = state.players.get(obj.controller)
            if ctrl is not None and ctrl.life == max_life:
                events.append(Event(
                    type=EventType.DRAW,
                    payload={'player': obj.controller, 'amount': 1},
                    source=obj.id
                ))
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': obj.controller, 'amount': -1},
                    source=obj.id
                ))
        return events
    return [make_attack_trigger(obj, attack_effect)]


def screaming_phantom_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying. Whenever attacks, mill a card."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def soulcoil_viper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Activated reanimate with finality counter."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated reanimation with finality counter rider
        return []
    return [make_etb_trigger(obj, effect_fn)]


def souls_of_the_lost_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Additional cost: discard or sac. P/T equal to perm cards in graveyard / +1."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: additional cost on cast and dynamic P/T from graveyard count
        return []
    return [make_etb_trigger(obj, effect_fn)]


def stalactite_stalker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace. End step: if descended, +1/+1 counter. Sac activated -X/-X target."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        if not state.turn_data.get(f'descended_{obj.controller}', False):
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_end_step_trigger(obj, end_step_effect)]


def stinging_cave_crawler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch. Descend 4: when attacks with 4+ perm cards in GY, draw + lose 1."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        graveyard = state.zones.get(f"graveyard_{obj.controller}")
        if not graveyard:
            return []
        perm_count = 0
        for cid in graveyard.objects:
            card = state.objects.get(cid)
            if not card:
                continue
            ts = card.characteristics.types
            if (CardType.CREATURE in ts or CardType.ARTIFACT in ts or
                CardType.ENCHANTMENT in ts or CardType.LAND in ts or
                CardType.PLANESWALKER in ts):
                perm_count += 1
        if perm_count < 4:
            return []
        return [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': -1},
                source=obj.id
            ),
        ]
    return [make_attack_trigger(obj, attack_effect)]


def vitos_inquisitor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{B}, sac another: +1/+1 counter on this, gains menace EOT."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated ability with sac cost and EOT keyword grant
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- RED (additional) ---

def brazen_blademaster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever attacks while you control 2+ artifacts, +2/+1 EOT."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        artifacts = sum(1 for o in state.objects.values()
                        if o.controller == obj.controller
                        and o.zone == ZoneType.BATTLEFIELD
                        and CardType.ARTIFACT in o.characteristics.types)
        if artifacts < 2:
            return []
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': 2, 'toughness_mod': 1, 'duration': 'end_of_turn'},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def breeches_eager_pillager_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """First strike. Whenever a Pirate you control attacks, choose one (modal)."""
    def pirate_attack_filter(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker = state.objects.get(event.payload.get('attacker_id'))
        if not attacker:
            return False
        if attacker.controller != source_obj.controller:
            return False
        return 'Pirate' in attacker.characteristics.subtypes

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: modal once-per-turn-per-mode choice
        return []

    return [make_attack_trigger(obj, attack_effect, filter_fn=pirate_attack_filter)]


def child_of_the_volcano_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trample. End step: if descended, +1/+1 counter."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        if not state.turn_data.get(f'descended_{obj.controller}', False):
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_end_step_trigger(obj, end_step_effect)]


def curator_of_suns_creation_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you discover, discover again for same value (once per turn)."""
    def discover_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DISCOVER:
            return False
        if event.payload.get('player') != obj.controller:
            return False
        if state.turn_data.get(f'curator_triggered_{obj.id}', False):
            return False
        # Don't re-trigger off our own copy
        return event.source != obj.id

    def discover_handler(event: Event, state: GameState) -> InterceptorResult:
        state.turn_data[f'curator_triggered_{obj.id}'] = True
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DISCOVER,
                payload={'player': obj.controller, 'value': event.payload.get('value', 0)},
                source=obj.id
            )]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=discover_filter,
        handler=discover_handler,
        duration='while_on_battlefield'
    )]


def diamond_pickaxe_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Indestructible equipment that grants +1/+1 and Treasure-on-attack."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: equipment with granted attack-trigger Treasure
        return []
    return [make_etb_trigger(obj, effect_fn)]


def enterprising_scallywag_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """End step: if descended, create a Treasure token."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        if not state.turn_data.get(f'descended_{obj.controller}', False):
            return []
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Treasure Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_end_step_trigger(obj, end_step_effect)]


def ageological_appraiser_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, if cast, discover 3."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DISCOVER,
            payload={'player': obj.controller, 'value': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def goblin_tomb_raider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """As long as you control an artifact, +1/+0 and haste."""
    def affects_self(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        return any(o.controller == obj.controller and
                   o.zone == ZoneType.BATTLEFIELD and
                   CardType.ARTIFACT in o.characteristics.types
                   for o in state.objects.values())

    interceptors = list(make_static_pt_boost(obj, 1, 0, affects_self))

    def ability_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        return any(o.controller == obj.controller and
                   o.zone == ZoneType.BATTLEFIELD and
                   CardType.ARTIFACT in o.characteristics.types
                   for o in state.objects.values())

    def ability_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []))
        if 'haste' not in granted:
            granted.append('haste')
        new_event.payload['granted'] = granted
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=ability_filter,
        handler=ability_handler,
        duration='while_on_battlefield'
    ))
    return interceptors


def goldfury_strider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trample. Tap two: target creature gets +2/+0 EOT (sorcery only)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: multi-permanent-tap activated ability with target choice
        return []
    return [make_etb_trigger(obj, effect_fn)]


def hotfoot_gnome_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste. {T}: another target creature gains haste EOT."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: targeted activated EOT keyword grant
        return []
    return [make_etb_trigger(obj, effect_fn)]


def inti_seneschal_of_the_sun_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you attack, may discard. When you do, +1/+1 on target attacker, trample EOT."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: optional discard prompt and targeted EOT keyword grant
        return []

    def discard_effect(event: Event, state: GameState) -> list[Event]:
        if event.payload.get('player') != obj.controller:
            return []
        # engine gap: impulse-from-top until next end step
        return []

    return [
        make_attack_trigger(obj, attack_effect),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=lambda e, s: e.type == EventType.DISCARD and e.payload.get('player') == obj.controller,
            handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=discard_effect(e, s)),
            duration='while_on_battlefield'
        ),
    ]


def panicked_altisaur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach. {T}: deal 2 damage to each opponent."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated tap ability with broadcast damage
        return []
    return [make_etb_trigger(obj, effect_fn)]


def poetic_ingenuity_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever Dinos attack, create that many Treasure. Once per turn: cast artifact -> 3/1 Dinosaur."""
    def attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker = state.objects.get(event.payload.get('attacker_id'))
        if not attacker:
            return False
        if attacker.controller != obj.controller:
            return False
        return 'Dinosaur' in attacker.characteristics.subtypes

    def attack_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Treasure Token',
                    'controller': obj.controller,
                    'types': [CardType.ARTIFACT],
                    'subtypes': ['Treasure'],
                    'colors': [],
                },
                source=obj.id
            )]
        )

    def artifact_cast_effect(event: Event, state: GameState) -> list[Event]:
        if state.turn_data.get(f'poetic_ingenuity_{obj.id}', False):
            return []
        state.turn_data[f'poetic_ingenuity_{obj.id}'] = True
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Dinosaur Token',
                'controller': obj.controller,
                'power': 3,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Dinosaur'],
                'colors': [Color.RED],
            },
            source=obj.id
        )]

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=attack_filter,
            handler=attack_handler,
            duration='while_on_battlefield'
        ),
        make_spell_cast_trigger(obj, artifact_cast_effect, spell_type_filter={CardType.ARTIFACT}),
    ]


def rampaging_ceratops_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Can't be blocked except by 3+ creatures."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: block restriction (must-be-blocked-by-3+)
        return []
    return [make_etb_trigger(obj, effect_fn)]


def scytheclaw_raptor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a player casts during another player's turn, deal 4 damage to them."""
    def cast_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = event.payload.get('caster') or event.controller
        if not caster:
            return False
        return caster != state.active_player

    def cast_handler(event: Event, state: GameState) -> InterceptorResult:
        caster = event.payload.get('caster') or event.controller
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.DAMAGE,
                payload={'source': obj.id, 'target': caster, 'amount': 4, 'is_combat': False},
                source=obj.id
            )]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=cast_filter,
        handler=cast_handler,
        duration='while_on_battlefield'
    )]


def seismic_monstrosaur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trample. {2}{R}, sac a land: draw a card. Mountaincycling."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated ability with sacrifice cost and cycling
        return []
    return [make_etb_trigger(obj, effect_fn)]


def sunfire_torch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment +1/+0 and grants attack-may-sac for 2 damage to any target."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: equipment with optional sacrifice trigger
        return []
    return [make_etb_trigger(obj, effect_fn)]


def sunshot_militia_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tap two: deal 1 damage to each opponent (sorcery only)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: multi-permanent-tap activated ability
        return []
    return [make_etb_trigger(obj, effect_fn)]


def volatile_wanderglyph_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever this becomes tapped, may discard a card. If you do, draw."""
    def tap_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: optional discard then draw on tap
        return []
    return [make_tap_trigger(obj, tap_effect)]


# --- GREEN (additional) ---

def basking_capybara_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Descend 4: +3/+0 with 4+ perm cards in graveyard."""
    def affects_self(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        graveyard = state.zones.get(f"graveyard_{obj.controller}")
        if not graveyard:
            return False
        perm_count = 0
        for cid in graveyard.objects:
            card = state.objects.get(cid)
            if not card:
                continue
            ts = card.characteristics.types
            if (CardType.CREATURE in ts or CardType.ARTIFACT in ts or
                CardType.ENCHANTMENT in ts or CardType.LAND in ts or
                CardType.PLANESWALKER in ts):
                perm_count += 1
        return perm_count >= 4

    return make_static_pt_boost(obj, 3, 0, affects_self)


def bedrock_tortoise_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Your turn: your creatures have hexproof. Toughness > power assigns by toughness."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: conditional hexproof and assigning-by-toughness damage
        return []
    return [make_etb_trigger(obj, effect_fn)]


def explorers_cache_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enters with two +1/+1 counters. Creature dies with +1/+1 counter -> +1/+1 here. {T}: move counter to target."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 2},
            source=obj.id
        )]

    def death_with_counter_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        target = state.objects.get(event.payload.get('object_id'))
        if not target:
            return False
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        return target.state.counters.get('+1/+1', 0) > 0

    def death_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id
            )]
        )

    return [
        make_etb_trigger(obj, etb_effect),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=death_with_counter_filter,
            handler=death_handler,
            duration='while_on_battlefield'
        ),
    ]


def ghalta_stampede_tyrant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trample. ETB: put any number of creature cards from hand onto battlefield."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: hand-to-battlefield optional batch put-into-play
        return []
    return [make_etb_trigger(obj, etb_effect)]


def glowcap_lantern_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment grants top-look and explore-on-attack."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: equipment with multiple granted abilities
        return []
    return [make_etb_trigger(obj, effect_fn)]


def hulking_raptor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ward {2}. Beginning of first main: add {G}{G}."""
    def main_phase_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'main_1':
            return False
        return state.active_player == obj.controller

    def main_phase_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.MANA_PRODUCED,
                payload={'player': obj.controller, 'mana': {Color.GREEN: 2}},
                source=obj.id
            )]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=main_phase_filter,
        handler=main_phase_handler,
        duration='while_on_battlefield'
    )]


def intrepid_paleontologist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Mana. Activated exile. Cast Dinos from exiled cards."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: multiple activated abilities and cast-from-exile permission
        return []
    return [make_etb_trigger(obj, effect_fn)]


def ixallis_lorekeeper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: add one mana of any color, restricted to Dinosaur sources."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: restricted mana ability
        return []
    return [make_etb_trigger(obj, effect_fn)]


def malamet_veteran_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trample. Descend 4: when attacks with 4+ perm cards in GY, +1/+1 counter on target."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: targeted +1/+1 counter on attack with descend gate
        return []
    return [make_attack_trigger(obj, attack_effect)]


def poison_dart_frog_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach. Mana. {2}: deathtouch EOT."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated ability for EOT keyword grant
        return []
    return [make_etb_trigger(obj, effect_fn)]


def pugnacious_hammerskull_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks while you don't control another Dinosaur, put stun counter on this."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        other_dino = any(o.id != obj.id and
                         o.controller == obj.controller and
                         o.zone == ZoneType.BATTLEFIELD and
                         'Dinosaur' in o.characteristics.subtypes
                         for o in state.objects.values())
        if other_dino:
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'stun', 'amount': 1},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def seeker_of_sunlight_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{2}{G}: this creature explores (sorcery only)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated sorcery-speed explore
        return []
    return [make_etb_trigger(obj, effect_fn)]


def the_skullspore_nexus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Cost-X less by max power. Nontoken creatures die: create big Fungus token. {2},{T}: double power EOT."""
    def death_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        target = state.objects.get(event.payload.get('object_id'))
        if not target:
            return False
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        return not target.state.is_token

    def death_handler(event: Event, state: GameState) -> InterceptorResult:
        target = state.objects.get(event.payload.get('object_id'))
        if not target:
            return InterceptorResult(action=InterceptorAction.PASS)
        power = target.characteristics.power or 0
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Fungus Dinosaur Token',
                    'controller': obj.controller,
                    'power': power,
                    'toughness': power,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Fungus', 'Dinosaur'],
                    'colors': [Color.GREEN],
                },
                source=obj.id
            )]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=death_filter,
        handler=death_handler,
        duration='while_on_battlefield'
    )]


def tendril_of_the_mycotyrant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{5}{G}{G}: 7 +1/+1 counters on target noncreature land you control; becomes 0/0 Fungus haste."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: animate-land activated ability
        return []
    return [make_etb_trigger(obj, effect_fn)]


def thrashing_brontodon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{1}, sac this: destroy target artifact or enchantment."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated ability with sac cost and target destroy
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- MULTICOLOR (additional) ---

def abuelo_ancestral_echo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, ward {2}. Activated: exile a permanent of yours, return at next end step."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated flicker with delayed return
        return []
    return [make_etb_trigger(obj, effect_fn)]


def amalia_benavides_aguirre_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ward-pay-3-life. When you gain life, this explores. If P==20, destroy all other creatures."""
    def life_gain_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = [Event(
            type=EventType.EXPLORE,
            payload={'object_id': obj.id, 'controller': obj.controller},
            source=obj.id
        )]
        live = state.objects.get(obj.id)
        power = live.characteristics.power if live else 0
        if power == 20:
            for other in list(state.objects.values()):
                if other.id == obj.id:
                    continue
                if (CardType.CREATURE in other.characteristics.types and
                        other.zone == ZoneType.BATTLEFIELD):
                    events.append(Event(
                        type=EventType.OBJECT_DESTROYED,
                        payload={'object_id': other.id},
                        source=obj.id
                    ))
        return events
    return [make_life_gain_trigger(obj, life_gain_effect)]


def the_ancient_one_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Descend 8: can't attack/block unless 8+ perm cards in GY. {2}{U}{B}: loot + mill on discard."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: conditional attack/block restriction and activated loot
        return []
    return [make_etb_trigger(obj, effect_fn)]


def bartolome_del_presidio_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sacrifice another creature/artifact: +1/+1 counter on this."""
    def sac_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.SACRIFICE:
            return False
        # Triggered by player sacrificing — must be controller's sacrifice and not this card itself
        if event.payload.get('player') != obj.controller and event.controller != obj.controller:
            return False
        target = state.objects.get(event.payload.get('object_id'))
        if not target or target.id == obj.id:
            return False
        ts = target.characteristics.types
        return CardType.CREATURE in ts or CardType.ARTIFACT in ts

    def sac_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id
            )]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=sac_filter,
        handler=sac_handler,
        duration='while_on_battlefield'
    )]


def the_belligerent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks: create Treasure, may play from top until EOT. Crew 3."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Treasure Token',
                    'controller': obj.controller,
                    'types': [CardType.ARTIFACT],
                    'subtypes': ['Treasure'],
                    'colors': []
                },
                source=obj.id
            ),
            # engine gap: play-from-top permission until EOT
        ]
    return [make_attack_trigger(obj, attack_effect)]


def caparocti_sunborn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever attacks, may tap two artifacts/creatures. If you do, discover 3."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: optional multi-permanent tap then conditional discover
        return []
    return [make_attack_trigger(obj, attack_effect)]


def gishath_suns_avatar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vigilance, trample, haste. Combat damage to player: reveal that many, put Dinos in play."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: reveal-X-and-batch-put-into-play
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]


def kutzil_malamet_exemplar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Opponents can't cast during your turn. Combat damage by buffed creature -> draw."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: opponent-can't-cast restriction and pumped-damage card draw
        return []
    return [make_etb_trigger(obj, effect_fn)]


def the_mycotyrant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """P/T equal to Fungi/Saprolings count. End step: X 1/1 black Fungus tokens by descend count."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        x = state.turn_data.get(f'descend_count_{obj.controller}', 0)
        if x <= 0:
            return []
        events = []
        for _ in range(x):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Fungus Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Fungus'],
                    'colors': [Color.BLACK],
                    'keywords': ['cant_block'],
                },
                source=obj.id
            ))
        return events
    return [make_end_step_trigger(obj, end_step_effect)]


def nicanzil_current_conductor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Explore land: may put land from hand. Explore nonland: +1/+1 on Nicanzil."""
    def explore_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.EXPLORE:
            return False
        explorer = state.objects.get(event.payload.get('object_id'))
        if not explorer:
            return False
        return explorer.controller == obj.controller

    def explore_handler(event: Event, state: GameState) -> InterceptorResult:
        # Nonland branch: payload may indicate the revealed card type
        revealed_is_land = event.payload.get('revealed_is_land')
        if revealed_is_land is False:
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                    source=obj.id
                )]
            )
        # Land branch: optional play from hand — engine gap
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


def quintorius_kand_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Planeswalker: spell-from-exile static + 3 loyalty abilities."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: planeswalker loyalty abilities and cast-from-exile triggers
        return []
    return [make_etb_trigger(obj, effect_fn)]


def saheeli_the_suns_brilliance_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{U}{R},{T}: copy a creature/artifact you control as artifact, haste, sac at next end step."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: clone-as-artifact with delayed sacrifice
        return []
    return [make_etb_trigger(obj, effect_fn)]


def sovereign_okinec_ahau_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ward {2}. When attacks, for each creature you control with power > base, add diff in +1/+1."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        events: list[Event] = []
        for o in list(state.objects.values()):
            if (o.controller != obj.controller or
                    o.zone != ZoneType.BATTLEFIELD or
                    CardType.CREATURE not in o.characteristics.types):
                continue
            base_power = o.characteristics.power or 0
            current_power = get_power(o, state)
            diff = current_power - base_power
            if diff > 0:
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': o.id, 'counter_type': '+1/+1', 'amount': diff},
                    source=obj.id
                ))
        return events
    return [make_attack_trigger(obj, attack_effect)]


def uchbenbak_the_great_mistake_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vigilance, menace. Activated reanimate from graveyard with finality counter."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: graveyard-only activated ability with finality counter return
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- ARTIFACTS (additional) ---

def buried_treasure_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}, sac: any color. {5}, exile from GY: discover 5 (sorcery)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated abilities with sacrifice / graveyard-exile costs
        return []
    return [make_etb_trigger(obj, effect_fn)]


def contested_game_ball_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Combat damage to you: attacker gains control + untap. {2},{T}: draw + point counter; sac at 5+."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: control-change-on-damage replacement-style trigger
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]


def hunters_blowgun_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment +1/+1; deathtouch on your turn, reach otherwise."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: equipment with conditional keyword grants
        return []
    return [make_etb_trigger(obj, effect_fn)]


def the_millennium_calendar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Untap-step counter accumulator, doubler activated, 1000-counter loss trigger."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: untap-tracking, doubler activated, threshold mass life loss
        return []
    return [make_etb_trigger(obj, effect_fn)]


def sorcerous_spyglass_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """As enters, look at opp's hand and choose a name. Ability lock for chosen name."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: replacement-style as-enters choice with ability lockdown
        return []
    return [make_etb_trigger(obj, etb_effect)]


def swashbucklers_whip_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment grants reach + tap-target + discover-10."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: equipment with multiple granted activated abilities
        return []
    return [make_etb_trigger(obj, effect_fn)]


def tarrians_soulcleaver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipment vigilance. Whenever another artifact/creature dies, +1/+1 on equipped creature."""
    def death_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.OBJECT_DESTROYED:
            return False
        target = state.objects.get(event.payload.get('object_id'))
        if not target or target.id == obj.id:
            return False
        ts = target.characteristics.types
        return CardType.CREATURE in ts or CardType.ARTIFACT in ts

    def death_handler(event: Event, state: GameState) -> InterceptorResult:
        equipped_id = obj.state.attached_to
        if not equipped_id:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': equipped_id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id
            )]
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=death_filter,
        handler=death_handler,
        duration='while_on_battlefield'
    )]


# --- LANDS ---

def captivating_cave_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Mana abilities and an activated +1/+1 counter sorcery."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: land activated abilities (mana, costed counter activation)
        return []
    return [make_etb_trigger(obj, effect_fn)]


def cavern_of_souls_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """As enters, choose a creature type. Mana abilities including uncounterable mana."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: as-enters type choice and creature-type-restricted uncounterable mana
        return []
    return [make_etb_trigger(obj, effect_fn)]


def cavernous_maw_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: {C}. {2}: become 3/3 Elemental, gated by 3+ Caves."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated land animation
        return []
    return [make_etb_trigger(obj, effect_fn)]


def echoing_deeps_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """May enter as a copy of any land in any graveyard, becomes Cave too."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: enter-as-copy-of-graveyard-land choice
        return []
    return [make_etb_trigger(obj, effect_fn)]


def forgotten_monument_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: {C}. Other Caves you control gain pay-1-life mana."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: granting activated abilities to other lands
        return []
    return [make_etb_trigger(obj, effect_fn)]


def hidden_cataract_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB tapped. {T}: {U}. {4}{U},{T},sac: discover 4."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated land with sacrifice cost
        return []
    return [make_etb_trigger(obj, effect_fn)]


def hidden_courtyard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB tapped. {T}: {W}. {4}{W},{T},sac: discover 4."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated land with sacrifice cost
        return []
    return [make_etb_trigger(obj, effect_fn)]


def hidden_necropolis_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB tapped. {T}: {B}. {4}{B},{T},sac: discover 4."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated land with sacrifice cost
        return []
    return [make_etb_trigger(obj, effect_fn)]


def hidden_nursery_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB tapped. {T}: {G}. {4}{G},{T},sac: discover 4."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated land with sacrifice cost
        return []
    return [make_etb_trigger(obj, effect_fn)]


def hidden_volcano_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB tapped. {T}: {R}. {4}{R},{T},sac: discover 4."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated land with sacrifice cost
        return []
    return [make_etb_trigger(obj, effect_fn)]


def promising_vein_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: {C}. {1},{T},sac: search basic land tapped."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated land with sacrifice/search cost
        return []
    return [make_etb_trigger(obj, effect_fn)]


def sunken_citadel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB tapped, choose color. Mana abilities of chosen color."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: as-enters color choice and restricted mana
        return []
    return [make_etb_trigger(obj, effect_fn)]


def volatile_fault_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: {C}. {1},{T},sac: destroy nonbasic land; opp searches; create Treasure."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: activated land with destroy + search + token chain
        return []
    return [make_etb_trigger(obj, effect_fn)]


# =============================================================================
# CARD DEFINITIONS
# =============================================================================

ABUELOS_AWAKENING = make_sorcery(
    name="Abuelo's Awakening",
    mana_cost="{X}{3}{W}",
    colors={Color.WHITE},
    text="Return target artifact or non-Aura enchantment card from your graveyard to the battlefield with X additional +1/+1 counters on it. It's a 1/1 Spirit creature with flying in addition to its other types.",
)

ACROBATIC_LEAP = make_instant(
    name="Acrobatic Leap",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gets +1/+3 and gains flying until end of turn. Untap it.",
    resolve=acrobatic_leap_resolve,
)

ADAPTIVE_GEMGUARD = make_artifact_creature(
    name="Adaptive Gemguard",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Gnome"},
    text="Tap two untapped artifacts and/or creatures you control: Put a +1/+1 counter on this creature. Activate only as a sorcery.",
    setup_interceptors=adaptive_gemguard_setup,
)

ATTENTIVE_SUNSCRIBE = make_artifact_creature(
    name="Attentive Sunscribe",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Gnome"},
    text="Whenever this creature becomes tapped, scry 1. (Look at the top card of your library. You may put that card on the bottom.)",
    setup_interceptors=attentive_sunscribe_setup,
)

BAT_COLONY = make_enchantment(
    name="Bat Colony",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, create a 1/1 black Bat creature token with flying for each mana from a Cave spent to cast it.\nWhenever a Cave you control enters, put a +1/+1 counter on target creature you control.",
    setup_interceptors=bat_colony_setup,
)

CLAYFIRED_BRICKS = make_artifact(
    name="Clay-Fired Bricks",
    mana_cost="{1}{W}",
    text="When this artifact enters, search your library for a basic Plains card, reveal it, put it into your hand, then shuffle. You gain 2 life.\nCraft with artifact {5}{W}{W}",
    setup_interceptors=clayfired_bricks_setup,
)

COSMIUM_BLAST = make_instant(
    name="Cosmium Blast",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Cosmium Blast deals 4 damage to target attacking or blocking creature.",
    resolve=cosmium_blast_resolve,
)

DAUNTLESS_DISMANTLER = make_creature(
    name="Dauntless Dismantler",
    power=1, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Artificer", "Human"},
    text="Artifacts your opponents control enter tapped.\n{X}{X}{W}, Sacrifice this creature: Destroy each artifact with mana value X.",
    setup_interceptors=dauntless_dismantler_setup,
)

DECONSTRUCTION_HAMMER = make_artifact(
    name="Deconstruction Hammer",
    mana_cost="{W}",
    text="Equipped creature gets +1/+1 and has \"{3}, {T}, Sacrifice Deconstruction Hammer: Destroy target artifact or enchantment.\"\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=deconstruction_hammer_setup,
)

DUSK_ROSE_RELIQUARY = make_artifact(
    name="Dusk Rose Reliquary",
    mana_cost="{W}",
    text="As an additional cost to cast this spell, sacrifice an artifact or creature.\nWard {2}\nWhen this artifact enters, exile target artifact or creature an opponent controls until this artifact leaves the battlefield.",
    setup_interceptors=dusk_rose_reliquary_setup,
)

ENVOY_OF_OKINEC_AHAU = make_creature(
    name="Envoy of Okinec Ahau",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Advisor", "Cat"},
    text="{4}{W}: Create a 1/1 colorless Gnome artifact creature token.",
    setup_interceptors=envoy_of_okinec_ahau_setup,
)

FABRICATION_FOUNDRY = make_artifact(
    name="Fabrication Foundry",
    mana_cost="{1}{W}",
    text="{T}: Add {W}. Spend this mana only to cast an artifact spell or activate an ability of an artifact source.\n{2}{W}, {T}, Exile one or more other artifacts you control with total mana value X: Return target artifact card with mana value X or less from your graveyard to the battlefield. Activate only as a sorcery.",
    setup_interceptors=fabrication_foundry_setup,
)

FAMILY_REUNION = make_instant(
    name="Family Reunion",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Creatures you control get +1/+1 until end of turn.\n• Creatures you control gain hexproof until end of turn. (They can't be the targets of spells or abilities your opponents control.)",
)

GET_LOST = make_instant(
    name="Get Lost",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Destroy target creature, enchantment, or planeswalker. Its controller creates two Map tokens. (They're artifacts with \"{1}, {T}, Sacrifice this token: Target creature you control explores. Activate only as a sorcery.\")",
    resolve=get_lost_resolve,
)

GLORIFIER_OF_SUFFERING = make_creature(
    name="Glorifier of Suffering",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Soldier", "Vampire"},
    text="When this creature enters, you may sacrifice another creature or artifact. When you do, put a +1/+1 counter on each of up to two target creatures.",
    setup_interceptors=glorifier_of_suffering_setup
)

GUARDIAN_OF_THE_GREAT_DOOR = make_creature(
    name="Guardian of the Great Door",
    power=4, toughness=4,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="As an additional cost to cast this spell, tap four untapped artifacts, creatures, and/or lands you control.\nFlying",
    setup_interceptors=guardian_of_the_great_door_setup,
)

HELPING_HAND = make_sorcery(
    name="Helping Hand",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Return target creature card with mana value 3 or less from your graveyard to the battlefield tapped.",
)

IRONPAW_ASPIRANT = make_creature(
    name="Ironpaw Aspirant",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Warrior"},
    text="When this creature enters, put a +1/+1 counter on target creature.",
    setup_interceptors=ironpaw_aspirant_setup
)

KINJALLIS_DAWNRUNNER = make_creature(
    name="Kinjalli's Dawnrunner",
    power=1, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="Double strike\nWhen this creature enters, it explores. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put the card back or put it into your graveyard.)",
    setup_interceptors=kinjallis_dawnrunner_setup
)

KUTZILS_FLANKER = make_creature(
    name="Kutzil's Flanker",
    power=3, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Warrior"},
    text="Flash\nWhen this creature enters, choose one —\n• Put a +1/+1 counter on this creature for each creature that left the battlefield under your control this turn.\n• You gain 2 life and scry 2.\n• Exile target player's graveyard.",
    setup_interceptors=kutzils_flanker_setup
)

MALAMET_WAR_SCRIBE = make_creature(
    name="Malamet War Scribe",
    power=4, toughness=3,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Warrior"},
    text="When this creature enters, creatures you control get +2/+1 until end of turn.",
    setup_interceptors=malamet_war_scribe_setup
)

MARKET_GNOME = make_artifact_creature(
    name="Market Gnome",
    power=0, toughness=3,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Gnome"},
    text="When this creature dies, you gain 1 life and draw a card.\nWhen this creature is exiled from the battlefield while you're activating a craft ability, you gain 1 life and draw a card.",
    setup_interceptors=market_gnome_setup
)

MIGHT_OF_THE_ANCESTORS = make_enchantment(
    name="Might of the Ancestors",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="At the beginning of combat on your turn, target creature you control gets +2/+0 and gains vigilance until end of turn.",
    setup_interceptors=might_of_the_ancestors_setup,
)

MINERS_GUIDEWING = make_creature(
    name="Miner's Guidewing",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Bird"},
    text="Flying, vigilance\nWhen this creature dies, target creature you control explores. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on that creature, then put the card back or put it into your graveyard.)",
    setup_interceptors=miners_guidewing_setup
)

MISCHIEVOUS_PUP = make_creature(
    name="Mischievous Pup",
    power=3, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Dog"},
    text="Flash (You may cast this spell any time you could cast an instant.)\nWhen this creature enters, return up to one other target permanent you control to its owner's hand.",
    setup_interceptors=mischievous_pup_setup
)

OJER_TAQ_DEEPEST_FOUNDATION = make_creature(
    name="Ojer Taq, Deepest Foundation",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "God", "Land"},
    supertypes={"Legendary"},
    text="",
)

OLTEC_ARCHAEOLOGISTS = make_creature(
    name="Oltec Archaeologists",
    power=4, toughness=4,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Artificer", "Human", "Scout"},
    text="When this creature enters, choose one —\n• Return target artifact card from your graveyard to your hand.\n• Scry 3. (Look at the top three cards of your library, then put any number of them on the bottom and the rest on top in any order.)",
    setup_interceptors=oltec_archaeologists_setup
)

OLTEC_CLOUD_GUARD = make_creature(
    name="Oltec Cloud Guard",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Flying\nWhen this creature enters, create a 1/1 colorless Gnome artifact creature token.",
    setup_interceptors=oltec_cloud_guard_setup
)

OTECLAN_LANDMARK = make_artifact_creature(
    name="Oteclan Landmark",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Golem"},
    text="",
)

PETRIFY = make_enchantment(
    name="Petrify",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Enchant artifact or creature\nEnchanted permanent can't attack or block, and its activated abilities can't be activated.",
    subtypes={"Aura"},
    setup_interceptors=petrify_setup,
)

QUICKSAND_WHIRLPOOL = make_instant(
    name="Quicksand Whirlpool",
    mana_cost="{5}{W}",
    colors={Color.WHITE},
    text="This spell costs {3} less to cast if it targets a tapped creature.\nExile target creature.",
    resolve=quicksand_whirlpool_resolve,
)

RESPLENDENT_ANGEL = make_creature(
    name="Resplendent Angel",
    power=3, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying\nAt the beginning of each end step, if you gained 5 or more life this turn, create a 4/4 white Angel creature token with flying and vigilance.\n{3}{W}{W}{W}: Until end of turn, this creature gets +2/+2 and gains lifelink.",
    setup_interceptors=resplendent_angel_setup,
)

RUINLURKER_BAT = make_creature(
    name="Ruin-Lurker Bat",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Bat"},
    text="Flying, lifelink\nAt the beginning of your end step, if you descended this turn, scry 1. (You descended if a permanent card was put into your graveyard from anywhere.)",
    setup_interceptors=ruinlurker_bat_setup,
)

SANGUINE_EVANGELIST = make_creature(
    name="Sanguine Evangelist",
    power=2, toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Vampire"},
    text="Battle cry (Whenever this creature attacks, each other attacking creature gets +1/+0 until end of turn.)\nWhen this creature enters or dies, create a 1/1 black Bat creature token with flying.",
    setup_interceptors=sanguine_evangelist_setup
)

SOARING_SANDWING = make_creature(
    name="Soaring Sandwing",
    power=3, toughness=5,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Dinosaur"},
    text="Flying\nWhen this creature enters, you gain 3 life.\nPlainscycling {2} ({2}, Discard this card: Search your library for a Plains card, reveal it, put it into your hand, then shuffle.)",
    setup_interceptors=soaring_sandwing_setup
)

SPRINGLOADED_SAWBLADES = make_artifact(
    name="Spring-Loaded Sawblades",
    mana_cost="",
    text="",
    subtypes={"Vehicle"},
)

THOUSAND_MOONS_CRACKSHOT = make_creature(
    name="Thousand Moons Crackshot",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Whenever this creature attacks, you may pay {2}{W}. When you do, tap target creature.",
    setup_interceptors=thousand_moons_crackshot_setup,
)

THOUSAND_MOONS_INFANTRY = make_creature(
    name="Thousand Moons Infantry",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Untap this creature during each other player's untap step.",
    setup_interceptors=thousand_moons_infantry_setup,
)

THOUSAND_MOONS_SMITHY = make_artifact(
    name="Thousand Moons Smithy",
    mana_cost="",
    text="",
    supertypes={"Legendary"},
)

TINKERS_TOTE = make_artifact(
    name="Tinker's Tote",
    mana_cost="{2}{W}",
    text="When this artifact enters, create two 1/1 colorless Gnome artifact creature tokens.\n{W}, Sacrifice this artifact: You gain 3 life.",
    setup_interceptors=tinkers_tote_setup
)

UNSTABLE_GLYPHBRIDGE = make_artifact_creature(
    name="Unstable Glyphbridge",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Golem"},
    text="",
)

VANGUARD_OF_THE_ROSE = make_creature(
    name="Vanguard of the Rose",
    power=3, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Knight", "Vampire"},
    text="{1}, Sacrifice another creature or artifact: This creature gains indestructible until end of turn. Tap it.",
    setup_interceptors=vanguard_of_the_rose_setup,
)

WARDEN_OF_THE_INNER_SKY = make_creature(
    name="Warden of the Inner Sky",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="As long as this creature has three or more counters on it, it has flying and vigilance.\nTap three untapped artifacts and/or creatures you control: Put a +1/+1 counter on this creature. Scry 1. Activate only as a sorcery.",
    setup_interceptors=warden_of_the_inner_sky_setup,
)

AKAL_PAKAL_FIRST_AMONG_EQUALS = make_creature(
    name="Akal Pakal, First Among Equals",
    power=1, toughness=5,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Advisor", "Human"},
    supertypes={"Legendary"},
    text="At the beginning of each player's end step, if an artifact entered the battlefield under your control this turn, look at the top two cards of your library. Put one of them into your hand and the other into your graveyard.",
    setup_interceptors=akal_pakal_first_among_equals_setup,
)

ANCESTRAL_REMINISCENCE = make_sorcery(
    name="Ancestral Reminiscence",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Draw three cards, then discard a card.",
)

BRACKISH_BLUNDER = make_instant(
    name="Brackish Blunder",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target creature to its owner's hand. If it was tapped, create a Map token. (It's an artifact with \"{1}, {T}, Sacrifice this token: Target creature you control explores. Activate only as a sorcery.\")",
    resolve=brackish_blunder_resolve,
)

BRAIDED_NET = make_artifact(
    name="Braided Net",
    mana_cost="",
    text="",
)

CHART_A_COURSE = make_sorcery(
    name="Chart a Course",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Draw two cards. Then discard a card unless you attacked this turn.",
)

COGWORK_WRESTLER = make_artifact_creature(
    name="Cogwork Wrestler",
    power=1, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Gnome"},
    text="Flash\nWhen this creature enters, target creature an opponent controls gets -2/-0 until end of turn.",
    setup_interceptors=cogwork_wrestler_setup
)

CONFOUNDING_RIDDLE = make_instant(
    name="Confounding Riddle",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Choose one —\n• Look at the top four cards of your library. Put one of them into your hand and the rest into your graveyard.\n• Counter target spell unless its controller pays {4}.",
)

COUNCIL_OF_ECHOES = make_creature(
    name="Council of Echoes",
    power=4, toughness=4,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Advisor", "Spirit"},
    text="Flying\nDescend 4 — When this creature enters, if there are four or more permanent cards in your graveyard, return up to one target nonland permanent other than this creature to its owner's hand.",
    setup_interceptors=council_of_echoes_setup
)

DEEPROOT_PILGRIMAGE = make_enchantment(
    name="Deeproot Pilgrimage",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Whenever one or more nontoken Merfolk you control become tapped, create a 1/1 blue Merfolk creature token with hexproof.",
    setup_interceptors=deeproot_pilgrimage_setup,
)

DIDACT_ECHO = make_creature(
    name="Didact Echo",
    power=3, toughness=2,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Cleric", "Spirit"},
    text="When this creature enters, draw a card.\nDescend 4 — This creature has flying as long as there are four or more permanent cards in your graveyard.",
    setup_interceptors=didact_echo_setup
)

EATEN_BY_PIRANHAS = make_enchantment(
    name="Eaten by Piranhas",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Flash (You may cast this spell any time you could cast an instant.)\nEnchant creature\nEnchanted creature loses all abilities and is a black Skeleton creature with base power and toughness 1/1. (It loses all other colors, card types, and creature types.)",
    subtypes={"Aura"},
    setup_interceptors=eaten_by_piranhas_setup,
)

THE_ENIGMA_JEWEL = make_artifact(
    name="The Enigma Jewel",
    mana_cost="",
    text="",
    supertypes={"Legendary"},
)

THE_EVERFLOWING_WELL = make_artifact(
    name="The Everflowing Well",
    mana_cost="",
    text="",
    supertypes={"Legendary"},
)

FRILLED_CAVEWURM = make_creature(
    name="Frilled Cave-Wurm",
    power=2, toughness=5,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Salamander", "Wurm"},
    text="Descend 4 — This creature gets +2/+0 as long as there are four or more permanent cards in your graveyard.",
    setup_interceptors=frilled_cavewurm_setup,
)

HERMITIC_NAUTILUS = make_artifact_creature(
    name="Hermitic Nautilus",
    power=1, toughness=4,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Nautilus"},
    text="Vigilance\n{1}{U}: This creature gets +3/-3 until end of turn.",
    setup_interceptors=hermitic_nautilus_setup,
)

HURL_INTO_HISTORY = make_instant(
    name="Hurl into History",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Counter target artifact or creature spell. Discover X, where X is that spell's mana value. (Exile cards from the top of your library until you exile a nonland card with that mana value or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
)

INVERTED_ICEBERG = make_artifact_creature(
    name="Inverted Iceberg",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Golem"},
    text="",
)

KITESAIL_LARCENIST = make_creature(
    name="Kitesail Larcenist",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="Flying, ward {1}\nWhen this creature enters, for each player, choose up to one other target artifact or creature that player controls. For as long as this creature remains on the battlefield, the chosen permanents become Treasure artifacts with \"{T}, Sacrifice this artifact: Add one mana of any color\" and lose all other abilities.",
    setup_interceptors=kitesail_larcenist_setup
)

LODESTONE_NEEDLE = make_artifact(
    name="Lodestone Needle",
    mana_cost="",
    text="",
)

MALCOLM_ALLURING_SCOUNDREL = make_creature(
    name="Malcolm, Alluring Scoundrel",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Pirate", "Siren"},
    supertypes={"Legendary"},
    text="Flash\nFlying\nWhenever Malcolm deals combat damage to a player, put a chorus counter on it. Draw a card, then discard a card. If there are four or more chorus counters on Malcolm, you may cast the discarded card without paying its mana cost.",
    setup_interceptors=malcolm_alluring_scoundrel_setup,
)

MARAUDING_BRINEFANG = make_creature(
    name="Marauding Brinefang",
    power=6, toughness=7,
    mana_cost="{5}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Dinosaur"},
    text="Ward {3} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {3}.)\nIslandcycling {2} ({2}, Discard this card: Search your library for an Island card, reveal it, put it into your hand, then shuffle.)",
    setup_interceptors=marauding_brinefang_setup,
)

MERFOLK_CAVEDIVER = make_creature(
    name="Merfolk Cave-Diver",
    power=2, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Scout"},
    text="Whenever a creature you control explores, this creature gets +1/+0 until end of turn and can't be blocked this turn.",
    setup_interceptors=merfolk_cavediver_setup,
)

OAKEN_SIREN = make_artifact_creature(
    name="Oaken Siren",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Pirate", "Siren"},
    text="Flying, vigilance\n{T}: Add {U}. Spend this mana only to cast an artifact spell or activate an ability of an artifact source.",
    setup_interceptors=oaken_siren_setup,
)

OJER_PAKPATIQ_DEEPEST_EPOCH = make_creature(
    name="Ojer Pakpatiq, Deepest Epoch",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "God", "Land"},
    supertypes={"Legendary"},
    text="",
)

ORAZCA_PUZZLEDOOR = make_artifact(
    name="Orazca Puzzle-Door",
    mana_cost="{U}",
    text="{1}, {T}, Sacrifice this artifact: Look at the top two cards of your library. Put one of those cards into your hand and the other into your graveyard.",
    setup_interceptors=orazca_puzzledoor_setup,
)

OUT_OF_AIR = make_instant(
    name="Out of Air",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="This spell costs {2} less to cast if it targets a creature spell.\nCounter target spell.",
    resolve=out_of_air_resolve,
)

PIRATE_HAT = make_artifact(
    name="Pirate Hat",
    mana_cost="{1}{U}",
    text="Equipped creature gets +1/+1 and has \"Whenever this creature attacks, draw a card, then discard a card.\"\nEquip Pirate {1}\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=pirate_hat_setup,
)

RELICS_ROAR = make_instant(
    name="Relic's Roar",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Until end of turn, target artifact or creature becomes a Dinosaur artifact creature with base power and toughness 4/3 in addition to its other types.",
)

RIVER_HERALD_SCOUT = make_creature(
    name="River Herald Scout",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Scout"},
    text="When this creature enters, it explores. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put the card back or put it into your graveyard.)",
    setup_interceptors=river_herald_scout_setup
)

SAGE_OF_DAYS = make_creature(
    name="Sage of Days",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When this creature enters, look at the top three cards of your library. You may put one of those cards back on top of your library. Put the rest into your graveyard.",
    setup_interceptors=sage_of_days_setup
)

SELFREFLECTION = make_sorcery(
    name="Self-Reflection",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Create a token that's a copy of target creature you control.\nFlashback {3}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

SHIPWRECK_SENTRY = make_creature(
    name="Shipwreck Sentry",
    power=3, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="Defender\nAs long as an artifact entered the battlefield under your control this turn, this creature can attack as though it didn't have defender.",
    setup_interceptors=shipwreck_sentry_setup,
)

SINUOUS_BENTHISAUR = make_creature(
    name="Sinuous Benthisaur",
    power=4, toughness=4,
    mana_cost="{5}{U}",
    colors={Color.BLUE},
    subtypes={"Dinosaur"},
    text="When this creature enters, look at the top X cards of your library, where X is the number of Caves you control plus the number of Cave cards in your graveyard. Put two of those cards into your hand and the rest on the bottom of your library in a random order.",
    setup_interceptors=sinuous_benthisaur_setup
)

SONG_OF_STUPEFACTION = make_enchantment(
    name="Song of Stupefaction",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Enchant creature or Vehicle\nWhen this Aura enters, you may mill two cards. (You may put the top two cards of your library into your graveyard.)\nFathomless descent — Enchanted permanent gets -X/-0, where X is the number of permanent cards in your graveyard.",
    subtypes={"Aura"},
    setup_interceptors=song_of_stupefaction_setup,
)

SPYGLASS_SIREN = make_creature(
    name="Spyglass Siren",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Pirate", "Siren"},
    text="Flying\nWhen this creature enters, create a Map token. (It's an artifact with \"{1}, {T}, Sacrifice this token: Target creature you control explores. Activate only as a sorcery.\")",
    setup_interceptors=spyglass_siren_setup
)

STAUNCH_CREWMATE = make_creature(
    name="Staunch Crewmate",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="When this creature enters, look at the top four cards of your library. You may reveal an artifact or Pirate card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
    setup_interceptors=staunch_crewmate_setup
)

SUBTERRANEAN_SCHOONER = make_artifact(
    name="Subterranean Schooner",
    mana_cost="{1}{U}",
    text="Whenever this Vehicle attacks, target creature that crewed it this turn explores. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on that creature, then put the card back or put it into your graveyard.)\nCrew 1",
    subtypes={"Vehicle"},
    setup_interceptors=subterranean_schooner_setup,
)

TISHANAS_TIDEBINDER = make_creature(
    name="Tishana's Tidebinder",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="Flash\nWhen this creature enters, counter up to one target activated or triggered ability. If an ability of an artifact, creature, or planeswalker is countered this way, that permanent loses all abilities for as long as this creature remains on the battlefield. (Mana abilities can't be targeted.)",
    setup_interceptors=tishanas_tidebinder_setup
)

UNLUCKY_DROP = make_instant(
    name="Unlucky Drop",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Target artifact or creature's owner puts it on their choice of the top or bottom of their library.",
)

WATERLOGGED_HULK = make_artifact(
    name="Waterlogged Hulk",
    mana_cost="",
    text="",
    subtypes={"Vehicle"},
)

WATERWIND_SCOUT = make_creature(
    name="Waterwind Scout",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Scout"},
    text="Flying\nWhen this creature enters, create a Map token. (It's an artifact with \"{1}, {T}, Sacrifice this token: Target creature you control explores. Activate only as a sorcery.\")",
    setup_interceptors=waterwind_scout_setup
)

WAYLAYING_PIRATES = make_creature(
    name="Waylaying Pirates",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="When this creature enters, if you control an artifact, tap target artifact or creature an opponent controls and put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
    setup_interceptors=waylaying_pirates_setup
)

ZOETIC_GLYPH = make_enchantment(
    name="Zoetic Glyph",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Enchant artifact\nEnchanted artifact is a Golem creature with base power and toughness 5/4 in addition to its other types.\nWhen this Aura is put into a graveyard from the battlefield, discover 3.",
    subtypes={"Aura"},
    setup_interceptors=zoetic_glyph_setup,
)

ABYSSAL_GORESTALKER = make_creature(
    name="Abyssal Gorestalker",
    power=6, toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="When this creature enters, each player sacrifices two creatures of their choice.",
    setup_interceptors=abyssal_gorestalker_setup
)

ACLAZOTZ_DEEPEST_BETRAYAL = make_creature(
    name="Aclazotz, Deepest Betrayal",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Bat", "God", "Land"},
    supertypes={"Legendary"},
    text="",
)

ACOLYTE_OF_ACLAZOTZ = make_creature(
    name="Acolyte of Aclazotz",
    power=1, toughness=4,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Vampire"},
    text="{T}, Sacrifice another creature or artifact: Each opponent loses 1 life and you gain 1 life.",
    setup_interceptors=acolyte_of_aclazotz_setup,
)

ANOTHER_CHANCE = make_instant(
    name="Another Chance",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="You may mill two cards. Then return up to two creature cards from your graveyard to your hand. (To mill two cards, put the top two cards of your library into your graveyard.)",
)

def _bitter_triumph_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Bitter Triumph after target selection."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    # Verify target is still valid (on battlefield and is creature or planeswalker)
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []  # Target no longer valid

    target_types = target.characteristics.types
    if CardType.CREATURE not in target_types and CardType.PLANESWALKER not in target_types:
        return []  # Not a valid target type

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def bitter_triumph_resolve(targets: list, state: GameState) -> list[Event]:
    """
    Resolve Bitter Triumph: Destroy target creature or planeswalker.

    Note: The additional cost (discard a card or pay 3 life) is handled during casting,
    not during resolution. This function handles the targeting and destruction.
    """
    # Find the spell on the stack to determine who cast it
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Bitter Triumph":
                caster_id = obj.controller
                spell_id = obj.id
                break

    # Fallback to active player if we can't find the spell
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "bitter_triumph_spell"

    # Find creatures and planeswalkers (valid targets)
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            target_types = obj.characteristics.types
            if CardType.CREATURE in target_types or CardType.PLANESWALKER in target_types:
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
        prompt="Choose a creature or planeswalker to destroy",
        min_targets=1,
        max_targets=1
    )

    # Set up callback for when target is selected
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _bitter_triumph_execute

    # Return empty events to pause resolution until choice is submitted
    return []


BITTER_TRIUMPH = make_instant(
    name="Bitter Triumph",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, discard a card or pay 3 life.\nDestroy target creature or planeswalker.",
    resolve=bitter_triumph_resolve,
)

BLOODLETTER_OF_ACLAZOTZ = make_creature(
    name="Bloodletter of Aclazotz",
    power=2, toughness=4,
    mana_cost="{1}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Vampire"},
    text="Flying\nIf an opponent would lose life during your turn, they lose twice that much life instead. (Damage causes loss of life.)",
    setup_interceptors=bloodletter_of_aclazotz_setup,
)

BLOODTHORN_FLAIL = make_artifact(
    name="Bloodthorn Flail",
    mana_cost="{B}",
    text="Equipped creature gets +2/+1.\nEquip—Pay {3} or discard a card.",
    subtypes={"Equipment"},
    setup_interceptors=bloodthorn_flail_setup,
)

BRINGER_OF_THE_LAST_GIFT = make_creature(
    name="Bringer of the Last Gift",
    power=6, toughness=6,
    mana_cost="{6}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Vampire"},
    text="Flying\nWhen this creature enters, if you cast it, each player sacrifices all other creatures they control. Then each player returns all creature cards from their graveyard that weren't put there this way to the battlefield.",
    setup_interceptors=bringer_of_the_last_gift_setup
)

BROODRAGE_MYCOID = make_creature(
    name="Broodrage Mycoid",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Fungus"},
    text="At the beginning of your end step, if you descended this turn, create a 1/1 black Fungus creature token with \"This token can't block.\" (You descended if a permanent card was put into your graveyard from anywhere.)",
    setup_interceptors=broodrage_mycoid_setup,
)

CANONIZED_IN_BLOOD = make_enchantment(
    name="Canonized in Blood",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="At the beginning of your end step, if you descended this turn, put a +1/+1 counter on target creature you control. (You descended if a permanent card was put into your graveyard from anywhere.)\n{5}{B}{B}, Sacrifice this enchantment: Create a 4/3 white and black Vampire Demon creature token with flying.",
    setup_interceptors=canonized_in_blood_setup,
)

CHUPACABRA_ECHO = make_creature(
    name="Chupacabra Echo",
    power=3, toughness=2,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Beast", "Horror", "Spirit"},
    text="Fathomless descent — When this creature enters, target creature an opponent controls gets -X/-X until end of turn, where X is the number of permanent cards in your graveyard.",
    setup_interceptors=chupacabra_echo_setup
)

CORPSES_OF_THE_LOST = make_enchantment(
    name="Corpses of the Lost",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Skeletons you control get +1/+0 and have haste.\nWhen this enchantment enters, create a 2/2 black Skeleton Pirate creature token.\nAt the beginning of your end step, if you descended this turn, you may pay 1 life. If you do, return this enchantment to its owner's hand. (You descended if a permanent card was put into your graveyard from anywhere.)",
    setup_interceptors=corpses_of_the_lost_setup
)

DEAD_WEIGHT = make_enchantment(
    name="Dead Weight",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Enchant creature\nEnchanted creature gets -2/-2.",
    subtypes={"Aura"},
    setup_interceptors=dead_weight_setup,
)

DEATHCAP_MARIONETTE = make_creature(
    name="Deathcap Marionette",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Fungus"},
    text="Deathtouch\nWhen this creature enters, you may mill two cards. (You may put the top two cards of your library into your graveyard.)",
    setup_interceptors=deathcap_marionette_setup
)

DEEP_GOBLIN_SKULLTAKER = make_creature(
    name="Deep Goblin Skulltaker",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Warrior"},
    text="Menace\nAt the beginning of your end step, if you descended this turn, put a +1/+1 counter on this creature. (You descended if a permanent card was put into your graveyard from anywhere.)",
    setup_interceptors=deep_goblin_skulltaker_setup,
)

DEEPCAVERN_BAT = make_creature(
    name="Deep-Cavern Bat",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Bat"},
    text="Flying, lifelink\nWhen this creature enters, look at target opponent's hand. You may exile a nonland card from it until this creature leaves the battlefield.",
    setup_interceptors=deepcavern_bat_setup
)

DEFOSSILIZE = make_sorcery(
    name="Defossilize",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield. That creature explores, then it explores again. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on that creature, then put the card back or put it into your graveyard. Then repeat this process.)",
)

ECHO_OF_DUSK = make_creature(
    name="Echo of Dusk",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Vampire"},
    text="Descend 4 — As long as there are four or more permanent cards in your graveyard, this creature gets +1/+1 and has lifelink.",
    setup_interceptors=echo_of_dusk_setup,
)

FANATICAL_OFFERING = make_instant(
    name="Fanatical Offering",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, sacrifice an artifact or creature.\nDraw two cards and create a Map token. (It's an artifact with \"{1}, {T}, Sacrifice this token: Target creature you control explores. Activate only as a sorcery.\")",
)

FUNGAL_FORTITUDE = make_enchantment(
    name="Fungal Fortitude",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Flash\nEnchant creature\nEnchanted creature gets +2/+0.\nWhen enchanted creature dies, return it to the battlefield tapped under its owner's control.",
    subtypes={"Aura"},
    setup_interceptors=fungal_fortitude_setup,
)

GARGANTUAN_LEECH = make_creature(
    name="Gargantuan Leech",
    power=5, toughness=5,
    mana_cost="{7}{B}",
    colors={Color.BLACK},
    subtypes={"Leech"},
    text="This spell costs {1} less to cast for each Cave you control and each Cave card in your graveyard.\nLifelink",
    setup_interceptors=gargantuan_leech_setup,
)

GRASPING_SHADOWS = make_enchantment(
    name="Grasping Shadows",
    mana_cost="",
    colors=set(),
    text="",
    subtypes={"Cave"},
)

GREEDY_FREEBOOTER = make_creature(
    name="Greedy Freebooter",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate"},
    text="When this creature dies, scry 1 and create a Treasure token. (To scry 1, look at the top card of your library. You may put that card on the bottom. A Treasure token is an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
    setup_interceptors=greedy_freebooter_setup
)

JOIN_THE_DEAD = make_instant(
    name="Join the Dead",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Target creature gets -5/-5 until end of turn.\nDescend 4 — That creature gets -10/-10 until end of turn instead if there are four or more permanent cards in your graveyard.",
    resolve=join_the_dead_resolve,
)

MALICIOUS_ECLIPSE = make_sorcery(
    name="Malicious Eclipse",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="All creatures get -2/-2 until end of turn. If a creature an opponent controls would die this turn, exile it instead.",
)

MEPHITIC_DRAUGHT = make_artifact(
    name="Mephitic Draught",
    mana_cost="{1}{B}",
    text="When this artifact enters or is put into a graveyard from the battlefield, you draw a card and you lose 1 life.",
    setup_interceptors=mephitic_draught_setup
)

PREACHER_OF_THE_SCHISM = make_creature(
    name="Preacher of the Schism",
    power=2, toughness=4,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Vampire"},
    text="Deathtouch\nWhenever this creature attacks the player with the most life or tied for most life, create a 1/1 white Vampire creature token with lifelink.\nWhenever this creature attacks while you have the most life or are tied for most life, you draw a card and you lose 1 life.",
    setup_interceptors=preacher_of_the_schism_setup,
)

PRIMORDIAL_GNAWER = make_creature(
    name="Primordial Gnawer",
    power=5, toughness=2,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Insect"},
    text="When this creature dies, discover 3. (Exile cards from the top of your library until you exile a nonland card with mana value 3 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
    setup_interceptors=primordial_gnawer_setup
)

QUEENS_BAY_PALADIN = make_creature(
    name="Queen's Bay Paladin",
    power=5, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Knight", "Vampire"},
    text="Whenever this creature enters or attacks, return up to one target Vampire card from your graveyard to the battlefield with a finality counter on it. You lose life equal to its mana value. (If a creature with a finality counter on it would die, exile it instead.)",
    setup_interceptors=queens_bay_paladin_setup
)

RAMPAGING_SPIKETAIL = make_creature(
    name="Rampaging Spiketail",
    power=5, toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Dinosaur"},
    text="When this creature enters, target creature you control gets +2/+0 and gains indestructible until end of turn.\nSwampcycling {2} ({2}, Discard this card: Search your library for a Swamp card, reveal it, put it into your hand, then shuffle.)",
    setup_interceptors=rampaging_spiketail_setup
)

RAY_OF_RUIN = make_sorcery(
    name="Ray of Ruin",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="Exile target creature, Vehicle, or nonbasic land. Scry 1. (Look at the top card of your library. You may put that card on the bottom.)",
    resolve=ray_of_ruin_resolve,
)

SCREAMING_PHANTOM = make_creature(
    name="Screaming Phantom",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Flying\nWhenever this creature attacks, mill a card. (Put the top card of your library into your graveyard.)",
    setup_interceptors=screaming_phantom_setup,
)

SKULLCAP_SNAIL = make_creature(
    name="Skullcap Snail",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Fungus", "Snail"},
    text="When this creature enters, target opponent exiles a card from their hand.",
    setup_interceptors=skullcap_snail_setup
)

SOULCOIL_VIPER = make_creature(
    name="Soulcoil Viper",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Snake"},
    text="{B}, {T}, Sacrifice this creature: Return target creature card from your graveyard to the battlefield with a finality counter on it. Activate only as a sorcery. (If a creature with a finality counter on it would die, exile it instead.)",
    setup_interceptors=soulcoil_viper_setup,
)

SOULS_OF_THE_LOST = make_creature(
    name="Souls of the Lost",
    power=0, toughness=0,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="As an additional cost to cast this spell, discard a card or sacrifice a permanent.\nFathomless descent — Souls of the Lost's power is equal to the number of permanent cards in your graveyard and its toughness is equal to that number plus 1.",
    setup_interceptors=souls_of_the_lost_setup,
)

STALACTITE_STALKER = make_creature(
    name="Stalactite Stalker",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Rogue"},
    text="Menace\nAt the beginning of your end step, if you descended this turn, put a +1/+1 counter on this creature. (You descended if a permanent card was put into your graveyard from anywhere.)\n{2}{B}, Sacrifice this creature: Target creature gets -X/-X until end of turn, where X is this creature's power.",
    setup_interceptors=stalactite_stalker_setup,
)

STARVING_REVENANT = make_creature(
    name="Starving Revenant",
    power=4, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Spirit"},
    text="When this creature enters, surveil 2. Then for each card you put on top of your library, you draw a card and you lose 3 life.\nDescend 8 — Whenever you draw a card, if there are eight or more permanent cards in your graveyard, target opponent loses 1 life and you gain 1 life.",
    setup_interceptors=starving_revenant_setup
)

STINGING_CAVE_CRAWLER = make_creature(
    name="Stinging Cave Crawler",
    power=1, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Insect"},
    text="Deathtouch\nDescend 4 — Whenever this creature attacks, if there are four or more permanent cards in your graveyard, you draw a card and you lose 1 life.",
    setup_interceptors=stinging_cave_crawler_setup,
)

SYNAPSE_NECROMAGE = make_creature(
    name="Synapse Necromage",
    power=3, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Fungus", "Wizard"},
    text="When this creature dies, create two 1/1 black Fungus creature tokens with \"This token can't block.\"",
    setup_interceptors=synapse_necromage_setup
)

TARRIANS_JOURNAL = make_artifact(
    name="Tarrian's Journal",
    mana_cost="",
    text="",
    subtypes={"Cave"},
    supertypes={"Legendary"},
)

TERROR_TIDE = make_sorcery(
    name="Terror Tide",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Fathomless descent — All creatures get -X/-X until end of turn, where X is the number of permanent cards in your graveyard.",
)

TITHING_BLADE = make_artifact(
    name="Tithing Blade",
    mana_cost="",
    text="",
)

VISAGE_OF_DREAD = make_artifact_creature(
    name="Visage of Dread",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Dinosaur", "Horror", "Skeleton"},
    text="",
)

VITOS_INQUISITOR = make_creature(
    name="Vito's Inquisitor",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Knight", "Vampire"},
    text="{B}, Sacrifice another creature or artifact: Put a +1/+1 counter on this creature. It gains menace until end of turn.",
    setup_interceptors=vitos_inquisitor_setup,
)

ABRADE = make_instant(
    name="Abrade",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Choose one —\n• Abrade deals 3 damage to target creature.\n• Destroy target artifact.",
    resolve=abrade_resolve,
)

ANCESTORS_AID = make_instant(
    name="Ancestors' Aid",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +2/+0 and gains first strike until end of turn.\nCreate a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
)

BELLIGERENT_YEARLING = make_creature(
    name="Belligerent Yearling",
    power=3, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur"},
    text="Trample\nWhenever another Dinosaur you control enters, you may have this creature's base power become equal to that creature's power until end of turn.",
    setup_interceptors=belligerent_yearling_setup
)

BONEHOARD_DRACOSAUR = make_creature(
    name="Bonehoard Dracosaur",
    power=5, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur", "Dragon"},
    text="Flying, first strike\nAt the beginning of your upkeep, exile the top two cards of your library. You may play them this turn. If you exiled a land card this way, create a 3/1 red Dinosaur creature token. If you exiled a nonland card this way, create a Treasure token.",
    setup_interceptors=bonehoard_dracosaur_setup
)

BRASSS_TUNNELGRINDER = make_artifact(
    name="Brass's Tunnel-Grinder",
    mana_cost="",
    text="",
    subtypes={"Cave"},
    supertypes={"Legendary"},
)

BRAZEN_BLADEMASTER = make_creature(
    name="Brazen Blademaster",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Orc", "Pirate"},
    text="Whenever this creature attacks while you control two or more artifacts, it gets +2/+1 until end of turn.",
    setup_interceptors=brazen_blademaster_setup,
)

BREECHES_EAGER_PILLAGER = make_creature(
    name="Breeches, Eager Pillager",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Pirate"},
    supertypes={"Legendary"},
    text="First strike\nWhenever a Pirate you control attacks, choose one that hasn't been chosen this turn —\n• Create a Treasure token.\n• Target creature can't block this turn.\n• Exile the top card of your library. You may play it this turn.",
    setup_interceptors=breeches_eager_pillager_setup,
)

BURNING_SUN_CAVALRY = make_creature(
    name="Burning Sun Cavalry",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Knight"},
    text="Whenever this creature attacks or blocks while you control a Dinosaur, this creature gets +1/+1 until end of turn.",
    setup_interceptors=burning_sun_cavalry_setup
)

CALAMITOUS_CAVEIN = make_sorcery(
    name="Calamitous Cave-In",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Calamitous Cave-In deals X damage to each creature and each planeswalker, where X is the number of Caves you control plus the number of Cave cards in your graveyard.",
)

CHILD_OF_THE_VOLCANO = make_creature(
    name="Child of the Volcano",
    power=3, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Trample\nAt the beginning of your end step, if you descended this turn, put a +1/+1 counter on this creature. (You descended if a permanent card was put into your graveyard from anywhere.)",
    setup_interceptors=child_of_the_volcano_setup,
)

CURATOR_OF_SUNS_CREATION = make_creature(
    name="Curator of Sun's Creation",
    power=3, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Artificer", "Human"},
    text="Whenever you discover, discover again for the same value. This ability triggers only once each turn.",
    setup_interceptors=curator_of_suns_creation_setup,
)

DARING_DISCOVERY = make_sorcery(
    name="Daring Discovery",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="Up to three target creatures can't block this turn.\nDiscover 4. (Exile cards from the top of your library until you exile a nonland card with mana value 4 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
)

DIAMOND_PICKAXE = make_artifact(
    name="Diamond Pick-Axe",
    mana_cost="{R}",
    text="Indestructible (Effects that say \"destroy\" don't destroy this Equipment.)\nEquipped creature gets +1/+1 and has \"Whenever this creature attacks, create a Treasure token.\" (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nEquip {2}",
    subtypes={"Equipment"},
    setup_interceptors=diamond_pickaxe_setup,
)

DINOTOMATON = make_artifact_creature(
    name="Dinotomaton",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur", "Gnome"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhen this creature enters, target creature you control gains menace until end of turn.",
    setup_interceptors=dinotomaton_setup
)

DIRE_FLAIL = make_artifact(
    name="Dire Flail",
    mana_cost="",
    text="",
    subtypes={"//", "Artifact", "Equipment"},
)

DOWSING_DEVICE = make_artifact(
    name="Dowsing Device",
    mana_cost="",
    text="",
    subtypes={"Cave"},
)

DREADMAWS_IRE = make_instant(
    name="Dreadmaw's Ire",
    mana_cost="{R}",
    colors={Color.RED},
    text="Until end of turn, target attacking creature gets +2/+2 and gains trample and \"Whenever this creature deals combat damage to a player, destroy target artifact that player controls.\"",
)

ENTERPRISING_SCALLYWAG = make_creature(
    name="Enterprising Scallywag",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Pirate"},
    text="At the beginning of your end step, if you descended this turn, create a Treasure token. (You descended if a permanent card was put into your graveyard from anywhere.)",
    setup_interceptors=enterprising_scallywag_setup,
)

ETALIS_FAVOR = make_enchantment(
    name="Etali's Favor",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Enchant creature you control\nWhen this Aura enters, discover 3. (Exile cards from the top of your library until you exile a nonland card with mana value 3 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)\nEnchanted creature gets +1/+1 and has trample.",
    subtypes={"Aura"},
    setup_interceptors=etalis_favor_setup
)

GEOLOGICAL_APPRAISER = make_creature(
    name="Geological Appraiser",
    power=3, toughness=2,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Artificer", "Human"},
    text="When this creature enters, if you cast it, discover 3. (Exile cards from the top of your library until you exile a nonland card with mana value 3 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
    setup_interceptors=geological_appraiser_setup
)

AGEOLOGICAL_APPRAISER = make_creature(
    name="A-Geological Appraiser",
    power=3, toughness=2,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Artificer", "Human"},
    text="When Geological Appraiser enters, if you cast it, discover 3. (Exile cards from the top of your library until you exile a nonland card with mana value 3 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
    setup_interceptors=ageological_appraiser_setup,
)

GOBLIN_TOMB_RAIDER = make_creature(
    name="Goblin Tomb Raider",
    power=1, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Pirate"},
    text="As long as you control an artifact, this creature gets +1/+0 and has haste.",
    setup_interceptors=goblin_tomb_raider_setup,
)

GOLDFURY_STRIDER = make_artifact_creature(
    name="Goldfury Strider",
    power=3, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Golem"},
    text="Trample\nTap two untapped artifacts and/or creatures you control: Target creature gets +2/+0 until end of turn. Activate only as a sorcery.",
    setup_interceptors=goldfury_strider_setup,
)

HIT_THE_MOTHER_LODE = make_sorcery(
    name="Hit the Mother Lode",
    mana_cost="{4}{R}{R}{R}",
    colors={Color.RED},
    text="Discover 10. If the discovered card's mana value is less than 10, create a number of tapped Treasure tokens equal to the difference. (To discover 10, exile cards from the top of your library until you exile a nonland card with mana value 10 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
)

HOTFOOT_GNOME = make_artifact_creature(
    name="Hotfoot Gnome",
    power=3, toughness=1,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Gnome"},
    text="Haste\n{T}: Another target creature gains haste until end of turn.",
    setup_interceptors=hotfoot_gnome_setup,
)

IDOL_OF_THE_DEEP_KING = make_artifact(
    name="Idol of the Deep King",
    mana_cost="",
    text="",
    subtypes={"Equipment"},
)

INTI_SENESCHAL_OF_THE_SUN = make_creature(
    name="Inti, Seneschal of the Sun",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="Whenever you attack, you may discard a card. When you do, put a +1/+1 counter on target attacking creature. It gains trample until end of turn.\nWhenever you discard one or more cards, exile the top card of your library. You may play that card until your next end step.",
    setup_interceptors=inti_seneschal_of_the_sun_setup,
)

MAGMATIC_GALLEON = make_artifact(
    name="Magmatic Galleon",
    mana_cost="{3}{R}{R}",
    text="When this Vehicle enters, it deals 5 damage to target creature an opponent controls.\nWhenever one or more creatures your opponents control are dealt excess noncombat damage, create a Treasure token.\nCrew 2",
    subtypes={"Vehicle"},
    setup_interceptors=magmatic_galleon_setup
)

OJER_AXONIL_DEEPEST_MIGHT = make_creature(
    name="Ojer Axonil, Deepest Might",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "God", "Land"},
    supertypes={"Legendary"},
    text="",
)

PANICKED_ALTISAUR = make_creature(
    name="Panicked Altisaur",
    power=4, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur"},
    text="Reach\n{T}: This creature deals 2 damage to each opponent.",
    setup_interceptors=panicked_altisaur_setup,
)

PLUNDERING_PIRATE = make_creature(
    name="Plundering Pirate",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Orc", "Pirate"},
    text="When this creature enters, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
    setup_interceptors=plundering_pirate_setup
)

POETIC_INGENUITY = make_enchantment(
    name="Poetic Ingenuity",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Whenever one or more Dinosaurs you control attack, create that many Treasure tokens.\nWhenever you cast an artifact spell, create a 3/1 red Dinosaur creature token. This ability triggers only once each turn.",
    setup_interceptors=poetic_ingenuity_setup,
)

RAMPAGING_CERATOPS = make_creature(
    name="Rampaging Ceratops",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur"},
    text="This creature can't be blocked except by three or more creatures.",
    setup_interceptors=rampaging_ceratops_setup,
)

RUMBLING_ROCKSLIDE = make_sorcery(
    name="Rumbling Rockslide",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Rumbling Rockslide deals damage to target creature equal to the number of lands you control.",
    resolve=rumbling_rockslide_resolve,
)

SAHEELIS_LATTICE = make_artifact_creature(
    name="Saheeli's Lattice",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Dinosaur"},
    text="",
)

SCYTHECLAW_RAPTOR = make_creature(
    name="Scytheclaw Raptor",
    power=4, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur"},
    text="Whenever a player casts a spell, if it's not their turn, this creature deals 4 damage to them.",
    setup_interceptors=scytheclaw_raptor_setup,
)

SEISMIC_MONSTROSAUR = make_creature(
    name="Seismic Monstrosaur",
    power=6, toughness=5,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur"},
    text="Trample\n{2}{R}, Sacrifice a land: Draw a card.\nMountaincycling {2} ({2}, Discard this card: Search your library for a Mountain card, reveal it, put it into your hand, then shuffle.)",
    setup_interceptors=seismic_monstrosaur_setup,
)

SUNFIRE_TORCH = make_artifact(
    name="Sunfire Torch",
    mana_cost="{R}",
    text="Equipped creature gets +1/+0 and has \"Whenever this creature attacks, you may sacrifice Sunfire Torch. When you do, this creature deals 2 damage to any target.\"\nEquip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=sunfire_torch_setup,
)

SUNSHOT_MILITIA = make_creature(
    name="Sunshot Militia",
    power=1, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="Tap two untapped artifacts and/or creatures you control: This creature deals 1 damage to each opponent. Activate only as a sorcery.",
    setup_interceptors=sunshot_militia_setup,
)

TECTONIC_HAZARD = make_sorcery(
    name="Tectonic Hazard",
    mana_cost="{R}",
    colors={Color.RED},
    text="Tectonic Hazard deals 1 damage to each opponent and each creature they control.",
)

TRIUMPHANT_CHOMP = make_sorcery(
    name="Triumphant Chomp",
    mana_cost="{R}",
    colors={Color.RED},
    text="Triumphant Chomp deals damage to target creature equal to 2 or the greatest power among Dinosaurs you control, whichever is greater.",
    resolve=triumphant_chomp_resolve,
)

TRUMPETING_CARNOSAUR = make_creature(
    name="Trumpeting Carnosaur",
    power=7, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur"},
    text="Trample\nWhen this creature enters, discover 5.\n{2}{R}, Discard this card: It deals 3 damage to target creature or planeswalker.",
    setup_interceptors=trumpeting_carnosaur_setup
)

VOLATILE_WANDERGLYPH = make_artifact_creature(
    name="Volatile Wanderglyph",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Golem"},
    text="Whenever this creature becomes tapped, you may discard a card. If you do, draw a card.",
    setup_interceptors=volatile_wanderglyph_setup,
)

ZOYOWAS_JUSTICE = make_instant(
    name="Zoyowa's Justice",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="The owner of target artifact or creature with mana value 1 or greater shuffles it into their library. Then that player discovers X, where X is its mana value. (They exile cards from the top of their library until they exile a nonland card with that mana value or less. They cast it without paying its mana cost or put it into their hand. They put the rest on the bottom in a random order.)",
)

ARMORED_KINCALLER = make_creature(
    name="Armored Kincaller",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="When this creature enters, you may reveal a Dinosaur card from your hand. If you do or if you control another Dinosaur, you gain 3 life.",
    setup_interceptors=armored_kincaller_setup
)

BASKING_CAPYBARA = make_creature(
    name="Basking Capybara",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Capybara"},
    text="Descend 4 — This creature gets +3/+0 as long as there are four or more permanent cards in your graveyard.",
    setup_interceptors=basking_capybara_setup,
)

BEDROCK_TORTOISE = make_creature(
    name="Bedrock Tortoise",
    power=0, toughness=6,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Turtle"},
    text="During your turn, creatures you control have hexproof.\nEach creature you control with toughness greater than its power assigns combat damage equal to its toughness rather than its power.",
    setup_interceptors=bedrock_tortoise_setup,
)

CAVERN_STOMPER = make_creature(
    name="Cavern Stomper",
    power=7, toughness=7,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="When this creature enters, scry 2. (Look at the top two cards of your library, then put any number of them on the bottom and the rest on top in any order.)\n{3}{G}: This creature can't be blocked by creatures with power 2 or less this turn.",
    setup_interceptors=cavern_stomper_setup
)

CENOTE_SCOUT = make_creature(
    name="Cenote Scout",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Merfolk", "Scout"},
    text="When this creature enters, it explores. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put the card back or put it into your graveyard.)",
    setup_interceptors=cenote_scout_setup
)

COATI_SCAVENGER = make_creature(
    name="Coati Scavenger",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Raccoon"},
    text="Descend 4 — When this creature enters, if there are four or more permanent cards in your graveyard, return target permanent card from your graveyard to your hand.",
    setup_interceptors=coati_scavenger_setup
)

COLOSSADACTYL = make_creature(
    name="Colossadactyl",
    power=4, toughness=5,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Reach, trample",
)

COSMIUM_CONFLUENCE = make_sorcery(
    name="Cosmium Confluence",
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    text="Choose three. You may choose the same mode more than once.\n• Search your library for a Cave card, put it onto the battlefield tapped, then shuffle.\n• Put three +1/+1 counters on a Cave you control. It becomes a 0/0 Elemental creature with haste. It's still a land.\n• Destroy target enchantment.",
)

DISTURBED_SLUMBER = make_instant(
    name="Disturbed Slumber",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Until end of turn, target land you control becomes a 4/4 Dinosaur creature with reach and haste. It's still a land. It must be blocked this turn if able.",
)

EARTHSHAKER_DREADMAW = make_creature(
    name="Earthshaker Dreadmaw",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Trample\nWhen this creature enters, draw a card for each other Dinosaur you control.",
    setup_interceptors=earthshaker_dreadmaw_setup
)

EXPLORERS_CACHE = make_artifact(
    name="Explorer's Cache",
    mana_cost="{1}{G}",
    text="This artifact enters with two +1/+1 counters on it.\nWhenever a creature you control with a +1/+1 counter on it dies, put a +1/+1 counter on this artifact.\n{T}: Move a +1/+1 counter from this artifact onto target creature. Activate only as a sorcery.",
    setup_interceptors=explorers_cache_setup,
)

GHALTA_STAMPEDE_TYRANT = make_creature(
    name="Ghalta, Stampede Tyrant",
    power=12, toughness=12,
    mana_cost="{5}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur", "Elder"},
    supertypes={"Legendary"},
    text="Trample\nWhen Ghalta enters, put any number of creature cards from your hand onto the battlefield.",
    setup_interceptors=ghalta_stampede_tyrant_setup,
)

GLIMPSE_THE_CORE = make_sorcery(
    name="Glimpse the Core",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Search your library for a basic Forest card, put that card onto the battlefield tapped, then shuffle.\n• Return target Cave card from your graveyard to the battlefield tapped.",
)

GLOWCAP_LANTERN = make_artifact(
    name="Glowcap Lantern",
    mana_cost="{G}",
    text="Equipped creature has \"You may look at the top card of your library any time\" and \"Whenever this creature attacks, it explores.\" (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on that creature, then put the card back or put it into your graveyard.)\nEquip {2}",
    subtypes={"Equipment"},
    setup_interceptors=glowcap_lantern_setup,
)

GROWING_RITES_OF_ITLIMOC = make_enchantment(
    name="Growing Rites of Itlimoc",
    mana_cost="",
    colors=set(),
    text="",
    supertypes={"Legendary"},
)

HUATLI_POET_OF_UNITY = make_creature(
    name="Huatli, Poet of Unity",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Bard", "Enchantment", "Human", "Warrior"},
    supertypes={"Legendary"},
    text="",
)

HUATLIS_FINAL_STRIKE = make_instant(
    name="Huatli's Final Strike",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +1/+0 until end of turn. It deals damage equal to its power to target creature an opponent controls.",
    resolve=huatlis_final_strike_resolve,
)

HULKING_RAPTOR = make_creature(
    name="Hulking Raptor",
    power=5, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Ward {2}\nAt the beginning of your first main phase, add {G}{G}.",
    setup_interceptors=hulking_raptor_setup,
)

IN_THE_PRESENCE_OF_AGES = make_instant(
    name="In the Presence of Ages",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Reveal the top four cards of your library. You may put a creature card and/or a land card from among them into your hand. Put the rest into your graveyard.",
)

INTREPID_PALEONTOLOGIST = make_creature(
    name="Intrepid Paleontologist",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Human"},
    text="{T}: Add one mana of any color.\n{2}: Exile target card from a graveyard.\nYou may cast Dinosaur creature spells from among cards you own exiled with this creature. If you cast a spell this way, that creature enters with a finality counter on it. (If a creature with a finality counter on it would die, exile it instead.)",
    setup_interceptors=intrepid_paleontologist_setup,
)

IXALLIS_LOREKEEPER = make_creature(
    name="Ixalli's Lorekeeper",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Human"},
    text="{T}: Add one mana of any color. Spend this mana only to cast a Dinosaur spell or activate an ability of a Dinosaur source.",
    setup_interceptors=ixallis_lorekeeper_setup,
)

JADE_SEEDSTONES = make_artifact_creature(
    name="Jade Seedstones",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Golem"},
    text="",
)

JADELIGHT_SPELUNKER = make_creature(
    name="Jadelight Spelunker",
    power=1, toughness=1,
    mana_cost="{X}{G}",
    colors={Color.GREEN},
    subtypes={"Merfolk", "Scout"},
    text="When this creature enters, it explores X times. (To have it explore, reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on that creature, then put the card back or put it into your graveyard.)",
    setup_interceptors=jadelight_spelunker_setup
)

KASLEMS_STONETREE = make_artifact_creature(
    name="Kaslem's Stonetree",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Golem"},
    text="",
)

MALAMET_BATTLE_GLYPH = make_sorcery(
    name="Malamet Battle Glyph",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Choose target creature you control and target creature you don't control. If the creature you control entered this turn, put a +1/+1 counter on it. Then those creatures fight each other.",
)

MALAMET_BRAWLER = make_creature(
    name="Malamet Brawler",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Cat", "Warrior"},
    text="Whenever this creature attacks, target attacking creature gains trample until end of turn.",
    setup_interceptors=malamet_brawler_setup
)

MALAMET_SCYTHE = make_artifact(
    name="Malamet Scythe",
    mana_cost="{2}{G}",
    text="Flash\nWhen this Equipment enters, attach it to target creature you control.\nEquipped creature gets +2/+2.\nEquip {4} ({4}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=malamet_scythe_setup
)

MALAMET_VETERAN = make_creature(
    name="Malamet Veteran",
    power=5, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Cat", "Warrior"},
    text="Trample\nDescend 4 — Whenever this creature attacks, if there are four or more permanent cards in your graveyard, put a +1/+1 counter on target creature.",
    setup_interceptors=malamet_veteran_setup,
)

MINESHAFT_SPIDER = make_creature(
    name="Mineshaft Spider",
    power=3, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Spider"},
    text="Reach\nWhen this creature enters, you may mill two cards. (You may put the top two cards of your library into your graveyard.)",
    setup_interceptors=mineshaft_spider_setup
)

NURTURING_BRISTLEBACK = make_creature(
    name="Nurturing Bristleback",
    power=5, toughness=5,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="When this creature enters, create a 3/3 green Dinosaur creature token.\nForestcycling {2} ({2}, Discard this card: Search your library for a Forest card, reveal it, put it into your hand, then shuffle.)",
    setup_interceptors=nurturing_bristleback_setup
)

OJER_KASLEM_DEEPEST_GROWTH = make_creature(
    name="Ojer Kaslem, Deepest Growth",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "God", "Land"},
    supertypes={"Legendary"},
    text="",
)

OVER_THE_EDGE = make_sorcery(
    name="Over the Edge",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Destroy target artifact or enchantment.\n• Target creature you control explores, then it explores again. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on that creature, then put the card back or put it into your graveyard. Then repeat this process.)",
)

PATHFINDING_AXEJAW = make_creature(
    name="Pathfinding Axejaw",
    power=4, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="When this creature enters, it explores. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put the card back or put it into your graveyard.)",
    setup_interceptors=pathfinding_axejaw_setup
)

POISON_DART_FROG = make_creature(
    name="Poison Dart Frog",
    power=1, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Frog"},
    text="Reach\n{T}: Add one mana of any color.\n{2}: This creature gains deathtouch until end of turn.",
    setup_interceptors=poison_dart_frog_setup,
)

PUGNACIOUS_HAMMERSKULL = make_creature(
    name="Pugnacious Hammerskull",
    power=6, toughness=6,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Whenever this creature attacks while you don't control another Dinosaur, put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
    setup_interceptors=pugnacious_hammerskull_setup,
)

RIVER_HERALD_GUIDE = make_creature(
    name="River Herald Guide",
    power=3, toughness=1,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Merfolk", "Scout"},
    text="Vigilance\nWhen this creature enters, it explores. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put the card back or put it into your graveyard.)",
    setup_interceptors=river_herald_guide_setup
)

SEEKER_OF_SUNLIGHT = make_creature(
    name="Seeker of Sunlight",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Merfolk", "Scout"},
    text="{2}{G}: This creature explores. Activate only as a sorcery. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put the card back or put it into your graveyard.)",
    setup_interceptors=seeker_of_sunlight_setup,
)

SENTINEL_OF_THE_NAMELESS_CITY = make_creature(
    name="Sentinel of the Nameless City",
    power=3, toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Merfolk", "Scout", "Warrior"},
    text="Vigilance\nWhenever this creature enters or attacks, create a Map token. (It's an artifact with \"{1}, {T}, Sacrifice this token: Target creature you control explores. Activate only as a sorcery.\")",
    setup_interceptors=sentinel_of_the_nameless_city_setup
)

THE_SKULLSPORE_NEXUS = make_artifact(
    name="The Skullspore Nexus",
    mana_cost="{6}{G}{G}",
    text="This spell costs {X} less to cast, where X is the greatest power among creatures you control.\nWhenever one or more nontoken creatures you control die, create a green Fungus Dinosaur creature token with base power and toughness each equal to the total power of those creatures.\n{2}, {T}: Double target creature's power until end of turn.",
    supertypes={"Legendary"},
    setup_interceptors=the_skullspore_nexus_setup,
)

SPELUNKING = make_enchantment(
    name="Spelunking",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, draw a card, then you may put a land card from your hand onto the battlefield. If you put a Cave onto the battlefield this way, you gain 4 life.\nLands you control enter untapped.",
    setup_interceptors=spelunking_setup
)

STAGGERING_SIZE = make_instant(
    name="Staggering Size",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 and gains trample until end of turn.",
    resolve=staggering_size_resolve,
)

TENDRIL_OF_THE_MYCOTYRANT = make_creature(
    name="Tendril of the Mycotyrant",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Fungus", "Wizard"},
    text="{5}{G}{G}: Put seven +1/+1 counters on target noncreature land you control. It becomes a 0/0 Fungus creature with haste. It's still a land.",
    setup_interceptors=tendril_of_the_mycotyrant_setup,
)

THRASHING_BRONTODON = make_creature(
    name="Thrashing Brontodon",
    power=3, toughness=4,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="{1}, Sacrifice this creature: Destroy target artifact or enchantment.",
    setup_interceptors=thrashing_brontodon_setup,
)

TWISTS_AND_TURNS = make_enchantment(
    name="Twists and Turns",
    mana_cost="",
    colors=set(),
    text="",
    subtypes={"Cave"},
)

WALK_WITH_THE_ANCESTORS = make_sorcery(
    name="Walk with the Ancestors",
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    text="Return up to one target permanent card from your graveyard to your hand. Discover 4. (Exile cards from the top of your library until you exile a nonland card with mana value 4 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
)

ABUELO_ANCESTRAL_ECHO = make_creature(
    name="Abuelo, Ancestral Echo",
    power=2, toughness=2,
    mana_cost="{1}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    text="Flying, ward {2}\n{1}{W}{U}: Exile another target creature or artifact you control. Return it to the battlefield under its owner's control at the beginning of the next end step.",
    setup_interceptors=abuelo_ancestral_echo_setup,
)

AKAWALLI_THE_SEETHING_TOWER = make_creature(
    name="Akawalli, the Seething Tower",
    power=3, toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Fungus"},
    supertypes={"Legendary"},
    text="Descend 4 — As long as there are four or more permanent cards in your graveyard, Akawalli gets +2/+2 and has trample.\nDescend 8 — As long as there are eight or more permanent cards in your graveyard, Akawalli gets an additional +2/+2 and can't be blocked by more than one creature.",
    setup_interceptors=akawalli_setup,
)

AMALIA_BENAVIDES_AGUIRRE = make_creature(
    name="Amalia Benavides Aguirre",
    power=2, toughness=2,
    mana_cost="{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Scout", "Vampire"},
    supertypes={"Legendary"},
    text="Ward—Pay 3 life.\nWhenever you gain life, Amalia Benavides Aguirre explores. Then destroy all other creatures if its power is exactly 20. (To have this creature explore, reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put the card back or put it into your graveyard.)",
    setup_interceptors=amalia_benavides_aguirre_setup,
)

THE_ANCIENT_ONE = make_creature(
    name="The Ancient One",
    power=8, toughness=8,
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"God", "Spirit"},
    supertypes={"Legendary"},
    text="Descend 8 — The Ancient One can't attack or block unless there are eight or more permanent cards in your graveyard.\n{2}{U}{B}: Draw a card, then discard a card. When you discard a card this way, target player mills cards equal to its mana value.",
    setup_interceptors=the_ancient_one_setup,
)

ANIM_PAKAL_THOUSANDTH_MOON = make_creature(
    name="Anim Pakal, Thousandth Moon",
    power=1, toughness=2,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Whenever you attack with one or more non-Gnome creatures, put a +1/+1 counter on Anim Pakal, then create X 1/1 colorless Gnome artifact creature tokens that are tapped and attacking, where X is the number of +1/+1 counters on Anim Pakal.",
    setup_interceptors=anim_pakal_setup
)

BARTOLOM_DEL_PRESIDIO = make_creature(
    name="Bartolomé del Presidio",
    power=2, toughness=1,
    mana_cost="{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Knight", "Vampire"},
    supertypes={"Legendary"},
    text="Sacrifice another creature or artifact: Put a +1/+1 counter on Bartolomé del Presidio.",
    setup_interceptors=bartolome_del_presidio_setup,
)

THE_BELLIGERENT = make_artifact(
    name="The Belligerent",
    mana_cost="{2}{U}{R}",
    text="Whenever The Belligerent attacks, create a Treasure token. Until end of turn, you may look at the top card of your library any time, and you may play lands and cast spells from the top of your library.\nCrew 3",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
    setup_interceptors=the_belligerent_setup,
)

CAPAROCTI_SUNBORN = make_creature(
    name="Caparocti Sunborn",
    power=4, toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Whenever Caparocti Sunborn attacks, you may tap two untapped artifacts and/or creatures you control. If you do, discover 3. (Exile cards from the top of your library until you exile a nonland card with mana value 3 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
    setup_interceptors=caparocti_sunborn_setup,
)

CAPTAIN_STORM_COSMIUM_RAIDER = make_creature(
    name="Captain Storm, Cosmium Raider",
    power=2, toughness=2,
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Whenever an artifact you control enters, put a +1/+1 counter on target Pirate you control.",
    setup_interceptors=captain_storm_cosmium_raider_setup
)

DEEPFATHOM_ECHO = make_creature(
    name="Deepfathom Echo",
    power=4, toughness=4,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Merfolk", "Spirit"},
    text="At the beginning of combat on your turn, this creature explores. Then you may have it become a copy of another creature you control until end of turn. (To have this creature explore, reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put the card back or put it into your graveyard.)",
    setup_interceptors=deepfathom_echo_setup,
)

GISHATH_SUNS_AVATAR = make_creature(
    name="Gishath, Sun's Avatar",
    power=7, toughness=6,
    mana_cost="{5}{R}{G}{W}",
    colors={Color.GREEN, Color.RED, Color.WHITE},
    subtypes={"Avatar", "Dinosaur"},
    supertypes={"Legendary"},
    text="Vigilance, trample, haste\nWhenever Gishath deals combat damage to a player, reveal that many cards from the top of your library. Put any number of Dinosaur creature cards from among them onto the battlefield and the rest on the bottom of your library in a random order.",
    setup_interceptors=gishath_suns_avatar_setup,
)

ITZQUINTH_FIRSTBORN_OF_GISHATH = make_creature(
    name="Itzquinth, Firstborn of Gishath",
    power=2, toughness=3,
    mana_cost="{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Dinosaur"},
    supertypes={"Legendary"},
    text="Haste\nWhen Itzquinth enters, you may pay {2}. When you do, target Dinosaur you control deals damage equal to its power to another target creature.",
    setup_interceptors=itzquinth_firstborn_of_gishath_setup
)

KELLAN_DARING_TRAVELER = make_creature(
    name="Kellan, Daring Traveler",
    power=2, toughness=3,
    mana_cost="{1}{W} // {G}",
    colors={Color.WHITE},
    subtypes={"//", "Faerie", "Human", "Scout", "Sorcery"},
    supertypes={"Legendary"},
    text="",
)

KUTZIL_MALAMET_EXEMPLAR = make_creature(
    name="Kutzil, Malamet Exemplar",
    power=3, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Cat", "Warrior"},
    supertypes={"Legendary"},
    text="Your opponents can't cast spells during your turn.\nWhenever one or more creatures you control each with power greater than its base power deals combat damage to a player, draw a card.",
    setup_interceptors=kutzil_malamet_exemplar_setup,
)

MASTERS_GUIDEMURAL = make_artifact(
    name="Master's Guide-Mural",
    mana_cost="",
    text="",
)

MOLTEN_COLLAPSE = make_sorcery(
    name="Molten Collapse",
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Choose one. If you descended this turn, you may choose both instead. (You descended if a permanent card was put into your graveyard from anywhere.)\n• Destroy target creature or planeswalker.\n• Destroy target noncreature, nonland permanent with mana value 1 or less.",
)

THE_MYCOTYRANT = make_creature(
    name="The Mycotyrant",
    power=0, toughness=0,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Elder", "Fungus"},
    supertypes={"Legendary"},
    text="Trample\nThe Mycotyrant's power and toughness are each equal to the number of creatures you control that are Fungi and/or Saprolings.\nAt the beginning of your end step, create X 1/1 black Fungus creature tokens with \"This token can't block,\" where X is the number of times you descended this turn. (You descend each time a permanent card is put into your graveyard from anywhere.)",
    setup_interceptors=the_mycotyrant_setup,
)

NICANZIL_CURRENT_CONDUCTOR = make_creature(
    name="Nicanzil, Current Conductor",
    power=2, toughness=3,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Merfolk", "Scout"},
    supertypes={"Legendary"},
    text="Whenever a creature you control explores a land card, you may put a land card from your hand onto the battlefield tapped.\nWhenever a creature you control explores a nonland card, put a +1/+1 counter on Nicanzil.",
    setup_interceptors=nicanzil_current_conductor_setup,
)

PALANIS_HATCHER = make_creature(
    name="Palani's Hatcher",
    power=5, toughness=3,
    mana_cost="{3}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Dinosaur"},
    text="Other Dinosaurs you control have haste.\nWhen this creature enters, create two 0/1 green Dinosaur Egg creature tokens.\nAt the beginning of combat on your turn, if you control one or more Eggs, sacrifice an Egg, then create a 3/3 green Dinosaur creature token.",
    setup_interceptors=palanis_hatcher_setup
)

QUINTORIUS_KAND = make_planeswalker(
    name="Quintorius Kand",
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    loyalty=4,
    subtypes={"Quintorius"},
    supertypes={"Legendary"},
    text="Whenever you cast a spell from exile, Quintorius Kand deals 2 damage to each opponent and you gain 2 life.\n+1: Create a 3/2 red and white Spirit creature token.\n−3: Discover 4.\n−6: Exile any number of target cards from your graveyard. Add {R} for each card exiled this way. You may play those cards this turn.",
    setup_interceptors=quintorius_kand_setup,
)

SAHEELI_THE_SUNS_BRILLIANCE = make_creature(
    name="Saheeli, the Sun's Brilliance",
    power=2, toughness=2,
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Artificer", "Human"},
    supertypes={"Legendary"},
    text="{U}{R}, {T}: Create a token that's a copy of another target creature or artifact you control, except it's an artifact in addition to its other types. It gains haste. Sacrifice it at the beginning of the next end step.",
    setup_interceptors=saheeli_the_suns_brilliance_setup,
)

SOVEREIGN_OKINEC_AHAU = make_creature(
    name="Sovereign Okinec Ahau",
    power=3, toughness=4,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Cat", "Noble"},
    supertypes={"Legendary"},
    text="Ward {2}\nWhenever Sovereign Okinec Ahau attacks, for each creature you control with power greater than that creature's base power, put a number of +1/+1 counters on that creature equal to the difference.",
    setup_interceptors=sovereign_okinec_ahau_setup,
)

SQUIRMING_EMERGENCE = make_sorcery(
    name="Squirming Emergence",
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Fathomless descent — Return to the battlefield target nonland permanent card in your graveyard with mana value less than or equal to the number of permanent cards in your graveyard.",
)

UCHBENBAK_THE_GREAT_MISTAKE = make_creature(
    name="Uchbenbak, the Great Mistake",
    power=6, toughness=4,
    mana_cost="{3}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Horror", "Skeleton"},
    supertypes={"Legendary"},
    text="Vigilance, menace\nDescend 8 — {4}{U}{B}: Return this card from your graveyard to the battlefield with a finality counter on it. Activate only if there are eight or more permanent cards in your graveyard and only as a sorcery. (If a creature with a finality counter on it would die, exile it instead.)",
    setup_interceptors=uchbenbak_the_great_mistake_setup,
)

VITO_FANATIC_OF_ACLAZOTZ = make_creature(
    name="Vito, Fanatic of Aclazotz",
    power=4, toughness=4,
    mana_cost="{2}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Demon", "Vampire"},
    supertypes={"Legendary"},
    text="Flying\nWhenever you sacrifice another permanent, you gain 2 life if this is the first time this ability has resolved this turn. If it's the second time, each opponent loses 2 life. If it's the third time, create a 4/3 white and black Vampire Demon creature token with flying.",
    setup_interceptors=vito_fanatic_setup,
)

WAIL_OF_THE_FORGOTTEN = make_sorcery(
    name="Wail of the Forgotten",
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    text="Descend 8 — Choose one. If there are eight or more permanent cards in your graveyard as you cast this spell, choose one or more instead.\n• Return target nonland permanent to its owner's hand.\n• Target opponent discards a card.\n• Look at the top three cards of your library. Put one of them into your hand and the rest into your graveyard.",
)

ZOYOWA_LAVATONGUE = make_creature(
    name="Zoyowa Lava-Tongue",
    power=2, toughness=2,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Goblin", "Warlock"},
    supertypes={"Legendary"},
    text="Deathtouch\nAt the beginning of your end step, if you descended this turn, each opponent may discard a card or sacrifice a permanent of their choice. Zoyowa deals 3 damage to each opponent who didn't. (You descended if a permanent card was put into your graveyard from anywhere.)",
    setup_interceptors=zoyowa_lavatongue_setup,
)

BURIED_TREASURE = make_artifact(
    name="Buried Treasure",
    mana_cost="{2}",
    text="{T}, Sacrifice this artifact: Add one mana of any color.\n{5}, Exile this card from your graveyard: Discover 5. Activate only as a sorcery. (Exile cards from the top of your library until you exile a nonland card with mana value 5 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
    subtypes={"Treasure"},
    setup_interceptors=buried_treasure_setup,
)

CAREENING_MINE_CART = make_artifact(
    name="Careening Mine Cart",
    mana_cost="{3}",
    text="Whenever this Vehicle attacks, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
    setup_interceptors=careening_mine_cart_setup
)

CARTOGRAPHERS_COMPANION = make_artifact_creature(
    name="Cartographer's Companion",
    power=2, toughness=1,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Gnome"},
    text="When this creature enters, create a Map token. (It's an artifact with \"{1}, {T}, Sacrifice this token: Target creature you control explores. Activate only as a sorcery.\")",
    setup_interceptors=cartographers_companion_setup
)

CHIMIL_THE_INNER_SUN = make_artifact(
    name="Chimil, the Inner Sun",
    mana_cost="{6}",
    text="Spells you control can't be countered.\nAt the beginning of your end step, discover 5. (Exile cards from the top of your library until you exile a nonland card with mana value 5 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
    supertypes={"Legendary"},
    setup_interceptors=chimil_inner_sun_setup
)

COMPASS_GNOME = make_artifact_creature(
    name="Compass Gnome",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Gnome"},
    text="When this creature enters, you may search your library for a basic land card or Cave card, reveal it, then shuffle and put that card on top.",
    setup_interceptors=compass_gnome_setup
)

CONTESTED_GAME_BALL = make_artifact(
    name="Contested Game Ball",
    mana_cost="{2}",
    text="Whenever you're dealt combat damage, the attacking player gains control of this artifact and untaps it.\n{2}, {T}: Draw a card and put a point counter on this artifact. Then if it has five or more point counters on it, sacrifice it and create a Treasure token.",
    setup_interceptors=contested_game_ball_setup,
)

DIGSITE_CONSERVATOR = make_artifact_creature(
    name="Digsite Conservator",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Gnome"},
    text="Sacrifice this creature: Exile up to four target cards from a single graveyard. Activate only as a sorcery.\nWhen this creature dies, you may pay {4}. If you do, discover 4. (Exile cards from the top of your library until you exile a nonland card with mana value 4 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
    setup_interceptors=digsite_conservator_setup
)

DISRUPTOR_WANDERGLYPH = make_artifact_creature(
    name="Disruptor Wanderglyph",
    power=3, toughness=4,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Golem"},
    text="Whenever this creature attacks, exile target card from an opponent's graveyard.",
    setup_interceptors=disruptor_wanderglyph_setup
)

HOVERSTONE_PILGRIM = make_artifact_creature(
    name="Hoverstone Pilgrim",
    power=2, toughness=5,
    mana_cost="{5}",
    colors=set(),
    subtypes={"Golem"},
    text="Flying\nWard {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\n{2}: Put target card from a graveyard on the bottom of its owner's library.",
    setup_interceptors=hoverstone_pilgrim_setup,
)

HUNTERS_BLOWGUN = make_artifact(
    name="Hunter's Blowgun",
    mana_cost="{1}",
    text="Equipped creature gets +1/+1.\nEquipped creature has deathtouch during your turn. Otherwise, it has reach.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=hunters_blowgun_setup,
)

MATZALANTLI_THE_GREAT_DOOR = make_artifact(
    name="Matzalantli, the Great Door",
    mana_cost="",
    text="",
    supertypes={"Legendary"},
)

THE_MILLENNIUM_CALENDAR = make_artifact(
    name="The Millennium Calendar",
    mana_cost="{1}",
    text="Whenever you untap one or more permanents during your untap step, put that many time counters on The Millennium Calendar.\n{2}, {T}: Double the number of time counters on The Millennium Calendar.\nWhen there are 1,000 or more time counters on The Millennium Calendar, sacrifice it and each opponent loses 1,000 life.",
    supertypes={"Legendary"},
    setup_interceptors=the_millennium_calendar_setup,
)

ROAMING_THRONE = make_artifact_creature(
    name="Roaming Throne",
    power=4, toughness=4,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Golem"},
    text="Ward {2}\nAs this creature enters, choose a creature type.\nThis creature is the chosen type in addition to its other types.\nIf a triggered ability of another creature you control of the chosen type triggers, it triggers an additional time.",
    setup_interceptors=roaming_throne_setup,
)

RUNAWAY_BOULDER = make_artifact(
    name="Runaway Boulder",
    mana_cost="{6}",
    text="Flash\nWhen this artifact enters, it deals 6 damage to target creature an opponent controls.\nCycling {2} ({2}, Discard this card: Draw a card.)",
    setup_interceptors=runaway_boulder_setup
)

SCAMPERING_SURVEYOR = make_artifact_creature(
    name="Scampering Surveyor",
    power=3, toughness=2,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Gnome"},
    text="When this creature enters, search your library for a basic land card or Cave card, put it onto the battlefield tapped, then shuffle.",
    setup_interceptors=scampering_surveyor_setup
)

SORCEROUS_SPYGLASS = make_artifact(
    name="Sorcerous Spyglass",
    mana_cost="{2}",
    text="As this artifact enters, look at an opponent's hand, then choose any card name.\nActivated abilities of sources with the chosen name can't be activated unless they're mana abilities.",
    setup_interceptors=sorcerous_spyglass_setup,
)

SUNBIRD_STANDARD = make_artifact_creature(
    name="Sunbird Standard",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Bird", "Construct"},
    text="",
)

SWASHBUCKLERS_WHIP = make_artifact(
    name="Swashbuckler's Whip",
    mana_cost="{1}",
    text="Equipped creature has reach, \"{2}, {T}: Tap target artifact or creature,\" and \"{8}, {T}: Discover 10.\" (Exile cards from the top of your library until you exile a nonland card with mana value 10 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)\nEquip {1}",
    subtypes={"Equipment"},
    setup_interceptors=swashbucklers_whip_setup,
)

TARRIANS_SOULCLEAVER = make_artifact(
    name="Tarrian's Soulcleaver",
    mana_cost="{1}",
    text="Equipped creature has vigilance.\nWhenever another artifact or creature is put into a graveyard from the battlefield, put a +1/+1 counter on equipped creature.\nEquip {2}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    setup_interceptors=tarrians_soulcleaver_setup,
)

THREEFOLD_THUNDERHULK = make_artifact_creature(
    name="Threefold Thunderhulk",
    power=0, toughness=0,
    mana_cost="{7}",
    colors=set(),
    subtypes={"Gnome"},
    text="This creature enters with three +1/+1 counters on it.\nWhenever this creature enters or attacks, create a number of 1/1 colorless Gnome artifact creature tokens equal to its power.\n{2}, Sacrifice another artifact: Put a +1/+1 counter on this creature.",
    setup_interceptors=threefold_thunderhulk_setup
)

THRONE_OF_THE_GRIM_CAPTAIN = make_artifact_creature(
    name="Throne of the Grim Captain",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Pirate", "Skeleton", "Spirit"},
    supertypes={"Legendary"},
    text="",
)

TREASURE_MAP = make_artifact(
    name="Treasure Map",
    mana_cost="",
    text="",
)

CAPTIVATING_CAVE = make_land(
    name="Captivating Cave",
    text="{T}: Add {C}.\n{1}, {T}: Add one mana of any color.\n{4}, {T}, Sacrifice this land: Put two +1/+1 counters on target creature. Activate only as a sorcery.",
    subtypes={"Cave"},
    setup_interceptors=captivating_cave_setup,
)

CAVERN_OF_SOULS = make_land(
    name="Cavern of Souls",
    text="As this land enters, choose a creature type.\n{T}: Add {C}.\n{T}: Add one mana of any color. Spend this mana only to cast a creature spell of the chosen type, and that spell can't be countered.",
    setup_interceptors=cavern_of_souls_setup,
)

CAVERNOUS_MAW = make_land(
    name="Cavernous Maw",
    text="{T}: Add {C}.\n{2}: This land becomes a 3/3 Elemental creature until end of turn. It's still a Cave land. Activate only if the number of other Caves you control plus the number of Cave cards in your graveyard is three or greater.",
    subtypes={"Cave"},
    setup_interceptors=cavernous_maw_setup,
)

ECHOING_DEEPS = make_land(
    name="Echoing Deeps",
    text="You may have this land enter tapped as a copy of any land card in a graveyard, except it's a Cave in addition to its other types.\n{T}: Add {C}.",
    subtypes={"Cave"},
    setup_interceptors=echoing_deeps_setup,
)

FORGOTTEN_MONUMENT = make_land(
    name="Forgotten Monument",
    text="{T}: Add {C}.\nOther Caves you control have \"{T}, Pay 1 life: Add one mana of any color.\"",
    subtypes={"Cave"},
    setup_interceptors=forgotten_monument_setup,
)

HIDDEN_CATARACT = make_land(
    name="Hidden Cataract",
    text="This land enters tapped.\n{T}: Add {U}.\n{4}{U}, {T}, Sacrifice this land: Discover 4. Activate only as a sorcery. (Exile cards from the top of your library until you exile a nonland card with mana value 4 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
    subtypes={"Cave"},
    setup_interceptors=hidden_cataract_setup,
)

HIDDEN_COURTYARD = make_land(
    name="Hidden Courtyard",
    text="This land enters tapped.\n{T}: Add {W}.\n{4}{W}, {T}, Sacrifice this land: Discover 4. Activate only as a sorcery. (Exile cards from the top of your library until you exile a nonland card with mana value 4 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
    subtypes={"Cave"},
    setup_interceptors=hidden_courtyard_setup,
)

HIDDEN_NECROPOLIS = make_land(
    name="Hidden Necropolis",
    text="This land enters tapped.\n{T}: Add {B}.\n{4}{B}, {T}, Sacrifice this land: Discover 4. Activate only as a sorcery. (Exile cards from the top of your library until you exile a nonland card with mana value 4 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
    subtypes={"Cave"},
    setup_interceptors=hidden_necropolis_setup,
)

HIDDEN_NURSERY = make_land(
    name="Hidden Nursery",
    text="This land enters tapped.\n{T}: Add {G}.\n{4}{G}, {T}, Sacrifice this land: Discover 4. Activate only as a sorcery. (Exile cards from the top of your library until you exile a nonland card with mana value 4 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
    subtypes={"Cave"},
    setup_interceptors=hidden_nursery_setup,
)

HIDDEN_VOLCANO = make_land(
    name="Hidden Volcano",
    text="This land enters tapped.\n{T}: Add {R}.\n{4}{R}, {T}, Sacrifice this land: Discover 4. Activate only as a sorcery. (Exile cards from the top of your library until you exile a nonland card with mana value 4 or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)",
    subtypes={"Cave"},
    setup_interceptors=hidden_volcano_setup,
)

PIT_OF_OFFERINGS = make_land(
    name="Pit of Offerings",
    text="This land enters tapped.\nWhen this land enters, exile up to three target cards from graveyards.\n{T}: Add {C}.\n{T}: Add one mana of any of the exiled cards' colors.",
    subtypes={"Cave"},
    setup_interceptors=pit_of_offerings_setup
)

PROMISING_VEIN = make_land(
    name="Promising Vein",
    text="{T}: Add {C}.\n{1}, {T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
    subtypes={"Cave"},
    setup_interceptors=promising_vein_setup,
)

RESTLESS_ANCHORAGE = make_land(
    name="Restless Anchorage",
    text="This land enters tapped.\n{T}: Add {W} or {U}.\n{1}{W}{U}: Until end of turn, this land becomes a 2/3 white and blue Bird creature with flying. It's still a land.\nWhenever this land attacks, create a Map token.",
    setup_interceptors=restless_anchorage_setup
)

RESTLESS_PRAIRIE = make_land(
    name="Restless Prairie",
    text="This land enters tapped.\n{T}: Add {G} or {W}.\n{2}{G}{W}: This land becomes a 3/3 green and white Llama creature until end of turn. It's still a land.\nWhenever this land attacks, other creatures you control get +1/+1 until end of turn.",
    setup_interceptors=restless_prairie_setup
)

RESTLESS_REEF = make_land(
    name="Restless Reef",
    text="This land enters tapped.\n{T}: Add {U} or {B}.\n{2}{U}{B}: Until end of turn, this land becomes a 4/4 blue and black Shark creature with deathtouch. It's still a land.\nWhenever this land attacks, target player mills four cards.",
    setup_interceptors=restless_reef_setup
)

RESTLESS_RIDGELINE = make_land(
    name="Restless Ridgeline",
    text="This land enters tapped.\n{T}: Add {R} or {G}.\n{2}{R}{G}: This land becomes a 3/4 red and green Dinosaur creature until end of turn. It's still a land.\nWhenever this land attacks, another target attacking creature gets +2/+0 until end of turn. Untap that creature.",
    setup_interceptors=restless_ridgeline_setup
)

RESTLESS_VENTS = make_land(
    name="Restless Vents",
    text="This land enters tapped.\n{T}: Add {B} or {R}.\n{1}{B}{R}: Until end of turn, this land becomes a 2/3 black and red Insect creature with menace. It's still a land.\nWhenever this land attacks, you may discard a card. If you do, draw a card.",
    setup_interceptors=restless_vents_setup
)

SUNKEN_CITADEL = make_land(
    name="Sunken Citadel",
    text="This land enters tapped. As it enters, choose a color.\n{T}: Add one mana of the chosen color.\n{T}: Add two mana of the chosen color. Spend this mana only to activate abilities of land sources.",
    subtypes={"Cave"},
    setup_interceptors=sunken_citadel_setup,
)

VOLATILE_FAULT = make_land(
    name="Volatile Fault",
    text="{T}: Add {C}.\n{1}, {T}, Sacrifice this land: Destroy target nonbasic land an opponent controls. That player may search their library for a basic land card, put it onto the battlefield, then shuffle. You create a Treasure token.",
    subtypes={"Cave"},
    setup_interceptors=volatile_fault_setup,
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

LOST_CAVERNS_IXALAN_CARDS = {
    "Abuelo's Awakening": ABUELOS_AWAKENING,
    "Acrobatic Leap": ACROBATIC_LEAP,
    "Adaptive Gemguard": ADAPTIVE_GEMGUARD,
    "Attentive Sunscribe": ATTENTIVE_SUNSCRIBE,
    "Bat Colony": BAT_COLONY,
    "Clay-Fired Bricks": CLAYFIRED_BRICKS,
    "Cosmium Blast": COSMIUM_BLAST,
    "Dauntless Dismantler": DAUNTLESS_DISMANTLER,
    "Deconstruction Hammer": DECONSTRUCTION_HAMMER,
    "Dusk Rose Reliquary": DUSK_ROSE_RELIQUARY,
    "Envoy of Okinec Ahau": ENVOY_OF_OKINEC_AHAU,
    "Fabrication Foundry": FABRICATION_FOUNDRY,
    "Family Reunion": FAMILY_REUNION,
    "Get Lost": GET_LOST,
    "Glorifier of Suffering": GLORIFIER_OF_SUFFERING,
    "Guardian of the Great Door": GUARDIAN_OF_THE_GREAT_DOOR,
    "Helping Hand": HELPING_HAND,
    "Ironpaw Aspirant": IRONPAW_ASPIRANT,
    "Kinjalli's Dawnrunner": KINJALLIS_DAWNRUNNER,
    "Kutzil's Flanker": KUTZILS_FLANKER,
    "Malamet War Scribe": MALAMET_WAR_SCRIBE,
    "Market Gnome": MARKET_GNOME,
    "Might of the Ancestors": MIGHT_OF_THE_ANCESTORS,
    "Miner's Guidewing": MINERS_GUIDEWING,
    "Mischievous Pup": MISCHIEVOUS_PUP,
    "Ojer Taq, Deepest Foundation": OJER_TAQ_DEEPEST_FOUNDATION,
    "Oltec Archaeologists": OLTEC_ARCHAEOLOGISTS,
    "Oltec Cloud Guard": OLTEC_CLOUD_GUARD,
    "Oteclan Landmark": OTECLAN_LANDMARK,
    "Petrify": PETRIFY,
    "Quicksand Whirlpool": QUICKSAND_WHIRLPOOL,
    "Resplendent Angel": RESPLENDENT_ANGEL,
    "Ruin-Lurker Bat": RUINLURKER_BAT,
    "Sanguine Evangelist": SANGUINE_EVANGELIST,
    "Soaring Sandwing": SOARING_SANDWING,
    "Spring-Loaded Sawblades": SPRINGLOADED_SAWBLADES,
    "Thousand Moons Crackshot": THOUSAND_MOONS_CRACKSHOT,
    "Thousand Moons Infantry": THOUSAND_MOONS_INFANTRY,
    "Thousand Moons Smithy": THOUSAND_MOONS_SMITHY,
    "Tinker's Tote": TINKERS_TOTE,
    "Unstable Glyphbridge": UNSTABLE_GLYPHBRIDGE,
    "Vanguard of the Rose": VANGUARD_OF_THE_ROSE,
    "Warden of the Inner Sky": WARDEN_OF_THE_INNER_SKY,
    "Akal Pakal, First Among Equals": AKAL_PAKAL_FIRST_AMONG_EQUALS,
    "Ancestral Reminiscence": ANCESTRAL_REMINISCENCE,
    "Brackish Blunder": BRACKISH_BLUNDER,
    "Braided Net": BRAIDED_NET,
    "Chart a Course": CHART_A_COURSE,
    "Cogwork Wrestler": COGWORK_WRESTLER,
    "Confounding Riddle": CONFOUNDING_RIDDLE,
    "Council of Echoes": COUNCIL_OF_ECHOES,
    "Deeproot Pilgrimage": DEEPROOT_PILGRIMAGE,
    "Didact Echo": DIDACT_ECHO,
    "Eaten by Piranhas": EATEN_BY_PIRANHAS,
    "The Enigma Jewel": THE_ENIGMA_JEWEL,
    "The Everflowing Well": THE_EVERFLOWING_WELL,
    "Frilled Cave-Wurm": FRILLED_CAVEWURM,
    "Hermitic Nautilus": HERMITIC_NAUTILUS,
    "Hurl into History": HURL_INTO_HISTORY,
    "Inverted Iceberg": INVERTED_ICEBERG,
    "Kitesail Larcenist": KITESAIL_LARCENIST,
    "Lodestone Needle": LODESTONE_NEEDLE,
    "Malcolm, Alluring Scoundrel": MALCOLM_ALLURING_SCOUNDREL,
    "Marauding Brinefang": MARAUDING_BRINEFANG,
    "Merfolk Cave-Diver": MERFOLK_CAVEDIVER,
    "Oaken Siren": OAKEN_SIREN,
    "Ojer Pakpatiq, Deepest Epoch": OJER_PAKPATIQ_DEEPEST_EPOCH,
    "Orazca Puzzle-Door": ORAZCA_PUZZLEDOOR,
    "Out of Air": OUT_OF_AIR,
    "Pirate Hat": PIRATE_HAT,
    "Relic's Roar": RELICS_ROAR,
    "River Herald Scout": RIVER_HERALD_SCOUT,
    "Sage of Days": SAGE_OF_DAYS,
    "Self-Reflection": SELFREFLECTION,
    "Shipwreck Sentry": SHIPWRECK_SENTRY,
    "Sinuous Benthisaur": SINUOUS_BENTHISAUR,
    "Song of Stupefaction": SONG_OF_STUPEFACTION,
    "Spyglass Siren": SPYGLASS_SIREN,
    "Staunch Crewmate": STAUNCH_CREWMATE,
    "Subterranean Schooner": SUBTERRANEAN_SCHOONER,
    "Tishana's Tidebinder": TISHANAS_TIDEBINDER,
    "Unlucky Drop": UNLUCKY_DROP,
    "Waterlogged Hulk": WATERLOGGED_HULK,
    "Waterwind Scout": WATERWIND_SCOUT,
    "Waylaying Pirates": WAYLAYING_PIRATES,
    "Zoetic Glyph": ZOETIC_GLYPH,
    "Abyssal Gorestalker": ABYSSAL_GORESTALKER,
    "Aclazotz, Deepest Betrayal": ACLAZOTZ_DEEPEST_BETRAYAL,
    "Acolyte of Aclazotz": ACOLYTE_OF_ACLAZOTZ,
    "Another Chance": ANOTHER_CHANCE,
    "Bitter Triumph": BITTER_TRIUMPH,
    "Bloodletter of Aclazotz": BLOODLETTER_OF_ACLAZOTZ,
    "Bloodthorn Flail": BLOODTHORN_FLAIL,
    "Bringer of the Last Gift": BRINGER_OF_THE_LAST_GIFT,
    "Broodrage Mycoid": BROODRAGE_MYCOID,
    "Canonized in Blood": CANONIZED_IN_BLOOD,
    "Chupacabra Echo": CHUPACABRA_ECHO,
    "Corpses of the Lost": CORPSES_OF_THE_LOST,
    "Dead Weight": DEAD_WEIGHT,
    "Deathcap Marionette": DEATHCAP_MARIONETTE,
    "Deep Goblin Skulltaker": DEEP_GOBLIN_SKULLTAKER,
    "Deep-Cavern Bat": DEEPCAVERN_BAT,
    "Defossilize": DEFOSSILIZE,
    "Echo of Dusk": ECHO_OF_DUSK,
    "Fanatical Offering": FANATICAL_OFFERING,
    "Fungal Fortitude": FUNGAL_FORTITUDE,
    "Gargantuan Leech": GARGANTUAN_LEECH,
    "Grasping Shadows": GRASPING_SHADOWS,
    "Greedy Freebooter": GREEDY_FREEBOOTER,
    "Join the Dead": JOIN_THE_DEAD,
    "Malicious Eclipse": MALICIOUS_ECLIPSE,
    "Mephitic Draught": MEPHITIC_DRAUGHT,
    "Preacher of the Schism": PREACHER_OF_THE_SCHISM,
    "Primordial Gnawer": PRIMORDIAL_GNAWER,
    "Queen's Bay Paladin": QUEENS_BAY_PALADIN,
    "Rampaging Spiketail": RAMPAGING_SPIKETAIL,
    "Ray of Ruin": RAY_OF_RUIN,
    "Screaming Phantom": SCREAMING_PHANTOM,
    "Skullcap Snail": SKULLCAP_SNAIL,
    "Soulcoil Viper": SOULCOIL_VIPER,
    "Souls of the Lost": SOULS_OF_THE_LOST,
    "Stalactite Stalker": STALACTITE_STALKER,
    "Starving Revenant": STARVING_REVENANT,
    "Stinging Cave Crawler": STINGING_CAVE_CRAWLER,
    "Synapse Necromage": SYNAPSE_NECROMAGE,
    "Tarrian's Journal": TARRIANS_JOURNAL,
    "Terror Tide": TERROR_TIDE,
    "Tithing Blade": TITHING_BLADE,
    "Visage of Dread": VISAGE_OF_DREAD,
    "Vito's Inquisitor": VITOS_INQUISITOR,
    "Abrade": ABRADE,
    "Ancestors' Aid": ANCESTORS_AID,
    "Belligerent Yearling": BELLIGERENT_YEARLING,
    "Bonehoard Dracosaur": BONEHOARD_DRACOSAUR,
    "Brass's Tunnel-Grinder": BRASSS_TUNNELGRINDER,
    "Brazen Blademaster": BRAZEN_BLADEMASTER,
    "Breeches, Eager Pillager": BREECHES_EAGER_PILLAGER,
    "Burning Sun Cavalry": BURNING_SUN_CAVALRY,
    "Calamitous Cave-In": CALAMITOUS_CAVEIN,
    "Child of the Volcano": CHILD_OF_THE_VOLCANO,
    "Curator of Sun's Creation": CURATOR_OF_SUNS_CREATION,
    "Daring Discovery": DARING_DISCOVERY,
    "Diamond Pick-Axe": DIAMOND_PICKAXE,
    "Dinotomaton": DINOTOMATON,
    "Dire Flail": DIRE_FLAIL,
    "Dowsing Device": DOWSING_DEVICE,
    "Dreadmaw's Ire": DREADMAWS_IRE,
    "Enterprising Scallywag": ENTERPRISING_SCALLYWAG,
    "Etali's Favor": ETALIS_FAVOR,
    "Geological Appraiser": GEOLOGICAL_APPRAISER,
    "A-Geological Appraiser": AGEOLOGICAL_APPRAISER,
    "Goblin Tomb Raider": GOBLIN_TOMB_RAIDER,
    "Goldfury Strider": GOLDFURY_STRIDER,
    "Hit the Mother Lode": HIT_THE_MOTHER_LODE,
    "Hotfoot Gnome": HOTFOOT_GNOME,
    "Idol of the Deep King": IDOL_OF_THE_DEEP_KING,
    "Inti, Seneschal of the Sun": INTI_SENESCHAL_OF_THE_SUN,
    "Magmatic Galleon": MAGMATIC_GALLEON,
    "Ojer Axonil, Deepest Might": OJER_AXONIL_DEEPEST_MIGHT,
    "Panicked Altisaur": PANICKED_ALTISAUR,
    "Plundering Pirate": PLUNDERING_PIRATE,
    "Poetic Ingenuity": POETIC_INGENUITY,
    "Rampaging Ceratops": RAMPAGING_CERATOPS,
    "Rumbling Rockslide": RUMBLING_ROCKSLIDE,
    "Saheeli's Lattice": SAHEELIS_LATTICE,
    "Scytheclaw Raptor": SCYTHECLAW_RAPTOR,
    "Seismic Monstrosaur": SEISMIC_MONSTROSAUR,
    "Sunfire Torch": SUNFIRE_TORCH,
    "Sunshot Militia": SUNSHOT_MILITIA,
    "Tectonic Hazard": TECTONIC_HAZARD,
    "Triumphant Chomp": TRIUMPHANT_CHOMP,
    "Trumpeting Carnosaur": TRUMPETING_CARNOSAUR,
    "Volatile Wanderglyph": VOLATILE_WANDERGLYPH,
    "Zoyowa's Justice": ZOYOWAS_JUSTICE,
    "Armored Kincaller": ARMORED_KINCALLER,
    "Basking Capybara": BASKING_CAPYBARA,
    "Bedrock Tortoise": BEDROCK_TORTOISE,
    "Cavern Stomper": CAVERN_STOMPER,
    "Cenote Scout": CENOTE_SCOUT,
    "Coati Scavenger": COATI_SCAVENGER,
    "Colossadactyl": COLOSSADACTYL,
    "Cosmium Confluence": COSMIUM_CONFLUENCE,
    "Disturbed Slumber": DISTURBED_SLUMBER,
    "Earthshaker Dreadmaw": EARTHSHAKER_DREADMAW,
    "Explorer's Cache": EXPLORERS_CACHE,
    "Ghalta, Stampede Tyrant": GHALTA_STAMPEDE_TYRANT,
    "Glimpse the Core": GLIMPSE_THE_CORE,
    "Glowcap Lantern": GLOWCAP_LANTERN,
    "Growing Rites of Itlimoc": GROWING_RITES_OF_ITLIMOC,
    "Huatli, Poet of Unity": HUATLI_POET_OF_UNITY,
    "Huatli's Final Strike": HUATLIS_FINAL_STRIKE,
    "Hulking Raptor": HULKING_RAPTOR,
    "In the Presence of Ages": IN_THE_PRESENCE_OF_AGES,
    "Intrepid Paleontologist": INTREPID_PALEONTOLOGIST,
    "Ixalli's Lorekeeper": IXALLIS_LOREKEEPER,
    "Jade Seedstones": JADE_SEEDSTONES,
    "Jadelight Spelunker": JADELIGHT_SPELUNKER,
    "Kaslem's Stonetree": KASLEMS_STONETREE,
    "Malamet Battle Glyph": MALAMET_BATTLE_GLYPH,
    "Malamet Brawler": MALAMET_BRAWLER,
    "Malamet Scythe": MALAMET_SCYTHE,
    "Malamet Veteran": MALAMET_VETERAN,
    "Mineshaft Spider": MINESHAFT_SPIDER,
    "Nurturing Bristleback": NURTURING_BRISTLEBACK,
    "Ojer Kaslem, Deepest Growth": OJER_KASLEM_DEEPEST_GROWTH,
    "Over the Edge": OVER_THE_EDGE,
    "Pathfinding Axejaw": PATHFINDING_AXEJAW,
    "Poison Dart Frog": POISON_DART_FROG,
    "Pugnacious Hammerskull": PUGNACIOUS_HAMMERSKULL,
    "River Herald Guide": RIVER_HERALD_GUIDE,
    "Seeker of Sunlight": SEEKER_OF_SUNLIGHT,
    "Sentinel of the Nameless City": SENTINEL_OF_THE_NAMELESS_CITY,
    "The Skullspore Nexus": THE_SKULLSPORE_NEXUS,
    "Spelunking": SPELUNKING,
    "Staggering Size": STAGGERING_SIZE,
    "Tendril of the Mycotyrant": TENDRIL_OF_THE_MYCOTYRANT,
    "Thrashing Brontodon": THRASHING_BRONTODON,
    "Twists and Turns": TWISTS_AND_TURNS,
    "Walk with the Ancestors": WALK_WITH_THE_ANCESTORS,
    "Abuelo, Ancestral Echo": ABUELO_ANCESTRAL_ECHO,
    "Akawalli, the Seething Tower": AKAWALLI_THE_SEETHING_TOWER,
    "Amalia Benavides Aguirre": AMALIA_BENAVIDES_AGUIRRE,
    "The Ancient One": THE_ANCIENT_ONE,
    "Anim Pakal, Thousandth Moon": ANIM_PAKAL_THOUSANDTH_MOON,
    "Bartolomé del Presidio": BARTOLOM_DEL_PRESIDIO,
    "The Belligerent": THE_BELLIGERENT,
    "Caparocti Sunborn": CAPAROCTI_SUNBORN,
    "Captain Storm, Cosmium Raider": CAPTAIN_STORM_COSMIUM_RAIDER,
    "Deepfathom Echo": DEEPFATHOM_ECHO,
    "Gishath, Sun's Avatar": GISHATH_SUNS_AVATAR,
    "Itzquinth, Firstborn of Gishath": ITZQUINTH_FIRSTBORN_OF_GISHATH,
    "Kellan, Daring Traveler": KELLAN_DARING_TRAVELER,
    "Kutzil, Malamet Exemplar": KUTZIL_MALAMET_EXEMPLAR,
    "Master's Guide-Mural": MASTERS_GUIDEMURAL,
    "Molten Collapse": MOLTEN_COLLAPSE,
    "The Mycotyrant": THE_MYCOTYRANT,
    "Nicanzil, Current Conductor": NICANZIL_CURRENT_CONDUCTOR,
    "Palani's Hatcher": PALANIS_HATCHER,
    "Quintorius Kand": QUINTORIUS_KAND,
    "Saheeli, the Sun's Brilliance": SAHEELI_THE_SUNS_BRILLIANCE,
    "Sovereign Okinec Ahau": SOVEREIGN_OKINEC_AHAU,
    "Squirming Emergence": SQUIRMING_EMERGENCE,
    "Uchbenbak, the Great Mistake": UCHBENBAK_THE_GREAT_MISTAKE,
    "Vito, Fanatic of Aclazotz": VITO_FANATIC_OF_ACLAZOTZ,
    "Wail of the Forgotten": WAIL_OF_THE_FORGOTTEN,
    "Zoyowa Lava-Tongue": ZOYOWA_LAVATONGUE,
    "Buried Treasure": BURIED_TREASURE,
    "Careening Mine Cart": CAREENING_MINE_CART,
    "Cartographer's Companion": CARTOGRAPHERS_COMPANION,
    "Chimil, the Inner Sun": CHIMIL_THE_INNER_SUN,
    "Compass Gnome": COMPASS_GNOME,
    "Contested Game Ball": CONTESTED_GAME_BALL,
    "Digsite Conservator": DIGSITE_CONSERVATOR,
    "Disruptor Wanderglyph": DISRUPTOR_WANDERGLYPH,
    "Hoverstone Pilgrim": HOVERSTONE_PILGRIM,
    "Hunter's Blowgun": HUNTERS_BLOWGUN,
    "Matzalantli, the Great Door": MATZALANTLI_THE_GREAT_DOOR,
    "The Millennium Calendar": THE_MILLENNIUM_CALENDAR,
    "Roaming Throne": ROAMING_THRONE,
    "Runaway Boulder": RUNAWAY_BOULDER,
    "Scampering Surveyor": SCAMPERING_SURVEYOR,
    "Sorcerous Spyglass": SORCEROUS_SPYGLASS,
    "Sunbird Standard": SUNBIRD_STANDARD,
    "Swashbuckler's Whip": SWASHBUCKLERS_WHIP,
    "Tarrian's Soulcleaver": TARRIANS_SOULCLEAVER,
    "Threefold Thunderhulk": THREEFOLD_THUNDERHULK,
    "Throne of the Grim Captain": THRONE_OF_THE_GRIM_CAPTAIN,
    "Treasure Map": TREASURE_MAP,
    "Captivating Cave": CAPTIVATING_CAVE,
    "Cavern of Souls": CAVERN_OF_SOULS,
    "Cavernous Maw": CAVERNOUS_MAW,
    "Echoing Deeps": ECHOING_DEEPS,
    "Forgotten Monument": FORGOTTEN_MONUMENT,
    "Hidden Cataract": HIDDEN_CATARACT,
    "Hidden Courtyard": HIDDEN_COURTYARD,
    "Hidden Necropolis": HIDDEN_NECROPOLIS,
    "Hidden Nursery": HIDDEN_NURSERY,
    "Hidden Volcano": HIDDEN_VOLCANO,
    "Pit of Offerings": PIT_OF_OFFERINGS,
    "Promising Vein": PROMISING_VEIN,
    "Restless Anchorage": RESTLESS_ANCHORAGE,
    "Restless Prairie": RESTLESS_PRAIRIE,
    "Restless Reef": RESTLESS_REEF,
    "Restless Ridgeline": RESTLESS_RIDGELINE,
    "Restless Vents": RESTLESS_VENTS,
    "Sunken Citadel": SUNKEN_CITADEL,
    "Volatile Fault": VOLATILE_FAULT,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
}

print(f"Loaded {len(LOST_CAVERNS_IXALAN_CARDS)} Lost_Caverns_of_Ixalan cards")
