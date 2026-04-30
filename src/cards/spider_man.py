"""
Marvels_Spider-Man (SPM) Card Implementations

Real card data fetched from Scryfall API.
193 cards in set.
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
    make_spell_cast_trigger, make_damage_trigger,
    make_targeted_etb_trigger,
    other_creatures_you_control, other_creatures_with_subtype,
    creatures_you_control, creatures_with_subtype,
    open_library_search,
    basic_land_filter, basic_subtype_filter, subtype_filter_lib,
    make_saga_setup,
    # SPM mechanics — Web-slinging and Mayhem.
    make_web_slinging_setup, make_mayhem_setup, combine_setups,
)
from src.engine.spm_mechanics import (
    is_web_slinging_cast, web_slinging_returned_mv, is_mayhem_cast,
    was_discarded_this_turn,
)
from src.engine.library_search import _shuffle_library


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# =============================================================================
# SETUP INTERCEPTOR FUNCTIONS
# =============================================================================

# --- Aunt May ---
# "Whenever another creature you control enters, you gain 1 life. If it's a Spider, put a +1/+1 counter on it."
def aunt_may_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def other_creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == source.id:
            return False
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == source.controller and
                CardType.CREATURE in entering_obj.characteristics.types)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        events = [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
        # If it's a Spider, also put a +1/+1 counter on it
        if entering_obj and "Spider" in entering_obj.characteristics.subtypes:
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': entering_id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id
            ))
        return events

    return [make_etb_trigger(obj, effect_fn, aunt_may_setup_filter)]

# Need a separate filter since we're using custom filter
def aunt_may_setup_filter(event: Event, state: GameState, source: GameObject) -> bool:
    if event.type != EventType.ZONE_CHANGE:
        return False
    if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
        return False
    entering_id = event.payload.get('object_id')
    if entering_id == source.id:
        return False
    entering_obj = state.objects.get(entering_id)
    if not entering_obj:
        return False
    return (entering_obj.controller == source.controller and
            CardType.CREATURE in entering_obj.characteristics.types)


# --- City Pigeon ---
# "When this creature leaves the battlefield, create a Food token."
def city_pigeon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def leaves_battlefield_filter(event: Event, state: GameState, source: GameObject) -> bool:
        return (event.type == EventType.ZONE_CHANGE and
                event.payload.get('object_id') == source.id and
                event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Food Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Food'],
            },
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: leaves_battlefield_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(e, s)),
        duration='until_leaves'
    )]


# --- Selfless Police Captain ---
# "This creature enters with a +1/+1 counter on it."
def selfless_police_captain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- Silver Sable, Mercenary Leader ---
# "When Silver Sable enters, put a +1/+1 counter on another target creature."
def silver_sable_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_targeted_etb_trigger(
        obj,
        effect='counter_add',
        effect_params={'counter_type': '+1/+1', 'amount': 1},
        target_filter='other_creature_you_control',
        prompt="Choose another target creature to put a +1/+1 counter on"
    )]
    # Note: rules text says "another target creature" (any controller); approximated as
    # other_creature_you_control because no "other_creature" cross-controller filter exists.


# --- Starling, Aerial Ally ---
# "When Starling enters, another target creature you control gains flying until end of turn."
def starling_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_targeted_etb_trigger(
        obj,
        effect='grant_keyword',
        effect_params={'keyword': 'flying', 'duration': 'end_of_turn'},
        target_filter='other_creature_you_control',
        prompt="Choose another creature you control to gain flying until end of turn"
    )]


# --- Flying Octobot ---
# "Whenever another Villain you control enters, put a +1/+1 counter on this creature."
def flying_octobot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    triggered_this_turn = {'value': False}

    def other_villain_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if triggered_this_turn['value']:
            return False
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == source.id:
            return False
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == source.controller and
                "Villain" in entering_obj.characteristics.subtypes)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        triggered_this_turn['value'] = True
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [make_etb_trigger(obj, effect_fn, other_villain_etb_filter)]


# --- Mysterio, Master of Illusion ---
# "When Mysterio enters, create a 3/3 blue Illusion Villain creature token for each nontoken Villain you control."
def mysterio_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Count nontoken Villains
        villain_count = 0
        for other in state.objects.values():
            if (other.controller == obj.controller and
                other.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in other.characteristics.types and
                "Villain" in other.characteristics.subtypes and
                not other.state.is_token):
                villain_count += 1

        events = []
        for _ in range(villain_count):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Illusion Villain Token',
                    'controller': obj.controller,
                    'power': 3,
                    'toughness': 3,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Illusion', 'Villain'],
                    'colors': [Color.BLUE],
                    'linked_to': obj.id  # Track for exile when Mysterio leaves
                },
                source=obj.id
            ))
        return events

    return [make_etb_trigger(obj, etb_effect)]


# --- Spider-Byte, Web Warden ---
# "When Spider-Byte enters, return up to one target nonland permanent to its owner's hand."
def spiderbyte_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_targeted_etb_trigger(
        obj,
        effect='bounce',
        target_filter='nonland_permanent',
        max_targets=1,
        optional=True,
        prompt="Choose up to one nonland permanent to return to its owner's hand"
    )]


# --- Agent Venom ---
# "Whenever another nontoken creature you control dies, you draw a card and lose 1 life."
def agent_venom_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def other_creature_dies_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        if dying_id == source.id:
            return False
        dying_obj = state.objects.get(dying_id)
        if not dying_obj:
            return False
        return (dying_obj.controller == source.controller and
                CardType.CREATURE in dying_obj.characteristics.types and
                not dying_obj.state.is_token)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': -1}, source=obj.id)
        ]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: other_creature_dies_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(e, s)),
        duration='while_on_battlefield'
    )]


# --- Common Crook ---
# "When this creature dies, create a Treasure token."
def common_crook_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Treasure Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


# --- Morlun, Devourer of Spiders ---
# "Morlun enters with X +1/+1 counters on him. When Morlun enters, he deals X damage to target opponent."
def morlun_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # X value would be tracked from casting - simplified
        x_value = event.payload.get('x_value', 0)
        events = []
        if x_value > 0:
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': x_value},
                source=obj.id
            ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


# --- Tombstone, Career Criminal ---
# "When Tombstone enters, return target Villain card from your graveyard to your hand."
# "Villain spells you cast cost {1} less to cast."
def tombstone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Compute legal targets: Villain cards in our graveyard
        graveyard = state.zones.get(f'graveyard_{obj.controller}')
        legal = []
        if graveyard:
            for card_id in graveyard.objects:
                card = state.objects.get(card_id)
                if card and 'Villain' in card.characteristics.subtypes:
                    legal.append(card_id)
        if not legal:
            return []
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': obj.id,
                'controller': obj.controller,
                'effect': 'graveyard_to_hand',
                'effect_params': {},
                'target_filter': 'creature_in_your_graveyard',
                'min_targets': 1,
                'max_targets': 1,
                'optional': False,
                'prompt': "Choose a Villain card in your graveyard to return to your hand",
                'legal_targets_override': legal,
            },
            source=obj.id
        )]
    # Cost reduction would need QUERY_COST interceptor — engine gap; left untouched.
    return [make_etb_trigger(obj, etb_effect)]


# --- Venomized Cat ---
# "When this creature enters, mill two cards."
def venomized_cat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- J. Jonah Jameson ---
# "When J. Jonah Jameson enters, suspect up to one target creature."
# "Whenever a creature you control with menace attacks, create a Treasure token."
def j_jonah_jameson_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting for suspect - placeholder
        return []

    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Attack trigger for menace creatures
    def menace_attack_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        if not attacker or attacker.controller != source.controller:
            return False
        if CardType.CREATURE not in attacker.characteristics.types:
            return False
        # Check if attacker has menace
        return 'menace' in attacker.characteristics.keywords

    def menace_attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Treasure Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
            },
            source=obj.id
        )]

    interceptors.append(make_attack_trigger(obj, menace_attack_effect, filter_fn=menace_attack_filter))

    return interceptors


# --- Shocker, Unshakable ---
# "When Shocker enters, he deals 2 damage to target creature and 2 damage to that creature's controller."
def shocker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Two-step: target a creature for 2 damage, then resolve a follow-up event
    # that also deals 2 damage to that creature's controller.
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Use TARGET_REQUIRED with damage to creature; then react in callback to ping controller.
        # Compute creature targets manually to allow custom callback for the "controller" hit.
        creature_ids = [
            o.id for o in state.objects.values()
            if o.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in o.characteristics.types
        ]
        if not creature_ids:
            return []

        def shocker_resolve(choice, selected, state: GameState) -> list[Event]:
            tid = selected[0] if selected else None
            if not tid:
                return []
            target = state.objects.get(tid)
            if not target:
                return []
            events = [Event(
                type=EventType.DAMAGE,
                payload={'target': tid, 'amount': 2, 'source': obj.id, 'is_combat': False},
                source=obj.id
            )]
            if target.controller in state.players:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': target.controller, 'amount': 2,
                             'source': obj.id, 'is_combat': False},
                    source=obj.id
                ))
            return events

        from src.cards.interceptor_helpers import create_target_choice
        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=creature_ids,
            prompt="Choose target creature (Shocker deals 2 to it and 2 to its controller)",
            min_targets=1,
            max_targets=1,
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = shocker_resolve
        return []

    return [make_etb_trigger(obj, etb_effect)]


# --- Professional Wrestler ---
# "When this creature enters, create a Treasure token."
def professional_wrestler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Treasure Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- Spider-Ham, Peter Porker ---
# "When Spider-Ham enters, create a Food token."
# "Other Spiders, Boars, Bats, Bears, Birds, Cats, Dogs, Frogs, Jackals, Lizards, Mice, Otters, Rabbits, Raccoons, Rats, Squirrels, Turtles, and Wolves you control get +1/+1."
def spider_ham_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []

    # ETB: Create Food token
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Food Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Food'],
            },
            source=obj.id
        )]

    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Lord effect for animal types
    animal_types = {"Spider", "Boar", "Bat", "Bear", "Bird", "Cat", "Dog", "Frog",
                    "Jackal", "Lizard", "Mouse", "Otter", "Rabbit", "Raccoon",
                    "Rat", "Squirrel", "Turtle", "Wolf"}

    def affects_animals(target: GameObject, state: GameState) -> bool:
        if target.id == obj.id:
            return False
        if target.controller != obj.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        return bool(target.characteristics.subtypes & animal_types)

    interceptors.extend(make_static_pt_boost(obj, 1, 1, affects_animals))
    return interceptors


# --- Wall Crawl ---
# "When this enchantment enters, create a 2/1 green Spider creature token with reach, then you gain 1 life for each Spider you control."
# "Spiders you control get +1/+1 and can't be blocked by creatures with defender."
def wall_crawl_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []

    # ETB: Create Spider token and gain life
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Spider Token',
                'controller': obj.controller,
                'power': 2,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Spider'],
                'colors': [Color.GREEN],
            },
            source=obj.id
        )]
        # Count spiders for life gain
        spider_count = 1  # Include the token we just created
        for other in state.objects.values():
            if (other.controller == obj.controller and
                other.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in other.characteristics.types and
                "Spider" in other.characteristics.subtypes):
                spider_count += 1
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': spider_count},
            source=obj.id
        ))
        return events

    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Lord effect: Spiders you control get +1/+1
    interceptors.extend(make_static_pt_boost(
        obj, 1, 1,
        creatures_with_subtype(obj, "Spider")
    ))

    return interceptors


# --- Doctor Octopus, Master Planner ---
# "Other Villains you control get +2/+2."
def doctor_octopus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_static_pt_boost(
        obj, 2, 2,
        other_creatures_with_subtype(obj, "Villain")
    )


# --- Gallant Citizen ---
# "When this creature enters, draw a card."
def gallant_citizen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- Mary Jane Watson ---
# "Whenever a Spider you control enters, draw a card. This ability triggers only once each turn."
def mary_jane_watson_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    triggered_this_turn = {'value': False}

    def spider_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if triggered_this_turn['value']:
            return False
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == source.controller and
                CardType.CREATURE in entering_obj.characteristics.types and
                "Spider" in entering_obj.characteristics.subtypes)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        triggered_this_turn['value'] = True
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    return [make_etb_trigger(obj, effect_fn, spider_etb_filter)]


# --- Mob Lookout ---
# "When this creature enters, target creature you control connives."
def mob_lookout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Connive = draw then discard - would need targeting
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- Web-Warriors ---
# "When this creature enters, put a +1/+1 counter on each other creature you control."
def web_warriors_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for other in state.objects.values():
            if (other.id != obj.id and
                other.controller == obj.controller and
                other.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in other.characteristics.types):
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': other.id, 'counter_type': '+1/+1', 'amount': 1},
                    source=obj.id
                ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


# --- SP//dr, Piloted by Peni ---
# "When SP//dr enters, put a +1/+1 counter on target creature."
def spdr_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_targeted_etb_trigger(
        obj,
        effect='counter_add',
        effect_params={'counter_type': '+1/+1', 'amount': 1},
        target_filter='creature',
        prompt="Choose target creature to put a +1/+1 counter on"
    )]
    # Modified-creature combat-damage draw rider: engine gap (modified-tracker is fragile).


# --- Spider-Girl, Legacy Hero ---
# "When Spider-Girl leaves the battlefield, create a 1/1 green and white Human Citizen creature token."
def spider_girl_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def leaves_battlefield_filter(event: Event, state: GameState, source: GameObject) -> bool:
        return (event.type == EventType.ZONE_CHANGE and
                event.payload.get('object_id') == source.id and
                event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Human Citizen Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Human', 'Citizen'],
                'colors': [Color.GREEN, Color.WHITE],
            },
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: leaves_battlefield_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(e, s)),
        duration='until_leaves'
    )]


# --- Vulture, Scheming Scavenger ---
# "Whenever Vulture attacks, other Villains you control gain flying until end of turn."
def vulture_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for other in state.objects.values():
            if (other.id != obj.id and
                    other.controller == obj.controller and
                    other.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in other.characteristics.types and
                    'Villain' in other.characteristics.subtypes):
                events.append(Event(
                    type=EventType.GRANT_KEYWORD,
                    payload={'object_id': other.id, 'keyword': 'flying',
                             'duration': 'end_of_turn'},
                    source=obj.id
                ))
        return events
    return [make_attack_trigger(obj, attack_effect)]


# --- Cosmic Spider-Man ---
# "At the beginning of combat on your turn, other Spiders you control gain flying, first strike, trample, lifelink, and haste until end of turn."
def cosmic_spiderman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def combat_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.PHASE_START and
                event.payload.get('phase') == 'combat' and
                state.active_player == obj.controller)

    keywords = ('flying', 'first strike', 'trample', 'lifelink', 'haste')

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        events = []
        for other in state.objects.values():
            if (other.id != obj.id and
                    other.controller == obj.controller and
                    other.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in other.characteristics.types and
                    'Spider' in other.characteristics.subtypes):
                for kw in keywords:
                    events.append(Event(
                        type=EventType.GRANT_KEYWORD,
                        payload={'object_id': other.id, 'keyword': kw,
                                 'duration': 'end_of_turn'},
                        source=obj.id
                    ))
        return events

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(e, s)),
        duration='while_on_battlefield'
    )]


# --- News Helicopter ---
# "When this creature enters, create a 1/1 green and white Human Citizen creature token."
def news_helicopter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Human Citizen Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Human', 'Citizen'],
                'colors': [Color.GREEN, Color.WHITE],
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- Eerie Gravestone ---
# "When this artifact enters, draw a card."
def eerie_gravestone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- Hot Dog Cart ---
# "When this artifact enters, create a Food token."
def hot_dog_cart_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Food Token',
                'controller': obj.controller,
                'types': [CardType.ARTIFACT],
                'subtypes': ['Food'],
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- Spider-Bot ---
# "When this creature enters, you may search your library for a basic land card, reveal it, then shuffle and put that card on top."
def spider_bot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # MTG ordering: shuffle, then put the chosen land on top.
        def on_chosen(choice, moved, state):
            library = state.zones.get(f"library_{obj.controller}")
            if not library or not moved:
                _shuffle_library(state, obj.controller)
                return []
            top_id = moved[0]
            if top_id in library.objects:
                library.objects.remove(top_id)
            _shuffle_library(state, obj.controller)
            library.objects.insert(0, top_id)
            return []

        return open_library_search(
            state, obj.controller, obj.id,
            filter_fn=basic_land_filter(),
            destination="library_top",
            reveal=True,
            shuffle_after=False,
            optional=True,
            on_chosen=on_chosen,
            prompt="You may search your library for a basic land card, reveal it, then shuffle and put it on top.",
        )
    return [make_etb_trigger(obj, etb_effect)]


# --- Ultimate Green Goblin ---
# "At the beginning of your upkeep, discard a card, then create a Treasure token."
def ultimate_green_goblin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Treasure Token',
                    'controller': obj.controller,
                    'types': [CardType.ARTIFACT],
                    'subtypes': ['Treasure'],
                },
                source=obj.id
            )
        ]
    return [make_upkeep_trigger(obj, upkeep_effect)]


# --- Ezekiel Sims, Spider-Totem ---
# "At the beginning of combat on your turn, target Spider you control gets +2/+2 until end of turn."
def ezekiel_sims_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def combat_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.PHASE_START and
                event.payload.get('phase') == 'combat' and
                state.active_player == obj.controller)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Compute legal Spider-you-control targets explicitly.
        legal = []
        for other in state.objects.values():
            if (other.controller == obj.controller and
                    other.zone == ZoneType.BATTLEFIELD and
                    CardType.CREATURE in other.characteristics.types and
                    'Spider' in other.characteristics.subtypes):
                legal.append(other.id)
        if not legal:
            return []
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': obj.id,
                'controller': obj.controller,
                'effect': 'pump',
                'effect_params': {'power_mod': 2, 'toughness_mod': 2},
                'target_filter': 'your_creature',
                'min_targets': 1,
                'max_targets': 1,
                'optional': False,
                'prompt': "Choose target Spider you control to get +2/+2 until end of turn",
                'legal_targets_override': legal,
            },
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(e, s)),
        duration='while_on_battlefield'
    )]


# --- Lurking Lizards ---
# "Whenever you cast a spell with mana value 4 or greater, put a +1/+1 counter on this creature."
def lurking_lizards_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def spell_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        return event.payload.get('mana_value', 0) >= 4

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [make_spell_cast_trigger(obj, effect_fn, mana_value_min=4)]


# --- Angry Rabble ---
# "Whenever you cast a spell with mana value 4 or greater, this creature deals 1 damage to each opponent."
def angry_rabble_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 1, 'source': obj.id, 'is_combat': False},
                    source=obj.id
                ))
        return events

    return [make_spell_cast_trigger(obj, effect_fn, mana_value_min=4)]


# --- Hobgoblin, Mantled Marauder ---
# "Whenever you discard a card, Hobgoblin gets +2/+0 until end of turn."
def hobgoblin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def discard_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.DISCARD and
                event.payload.get('player') == obj.controller)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_CHANGE,
            payload={'object_id': obj.id, 'power': 2, 'toughness': 0, 'duration': 'end_of_turn'},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=discard_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(e, s)),
        duration='while_on_battlefield'
    )]


# --- Damage Control Crew ---
# "When this creature enters, choose one - Repair / Impound"
def damage_control_crew_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified: just placeholder for modal ability
        return []
    return [make_etb_trigger(obj, etb_effect)]


# --- Prowler, Clawed Thief ---
# "Whenever another Villain you control enters, Prowler connives."
def prowler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def other_villain_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == source.id:
            return False
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        return (entering_obj.controller == source.controller and
                "Villain" in entering_obj.characteristics.subtypes)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Connive = draw then discard
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]

    return [make_etb_trigger(obj, effect_fn, other_villain_etb_filter)]


# --- Doc Ock's Henchmen ---
# "Whenever this creature attacks, it connives."
def doc_ocks_henchmen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Connive = draw then discard
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_attack_trigger(obj, attack_effect)]


# --- Mysterio's Phantasm ---
# "Whenever this creature attacks, mill a card."
def mysterios_phantasm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


# --- Green Goblin, Revenant ---
# "Whenever Green Goblin attacks, discard a card. Then draw a card for each card you've discarded this turn."
def green_goblin_revenant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified: discard 1, draw 1 (would need to track discards this turn for full impl)
        return [
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_attack_trigger(obj, attack_effect)]


# --- Spinneret and Spiderling ---
# "Whenever you attack with two or more Spiders, put a +1/+1 counter on Spinneret and Spiderling."
def spinneret_and_spiderling_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.COMBAT_DECLARED:
            return False
        # Count attacking Spiders
        spider_attackers = 0
        for attacker_id in event.payload.get('attackers', []):
            attacker = state.objects.get(attacker_id)
            if attacker and "Spider" in attacker.characteristics.subtypes:
                spider_attackers += 1
        return spider_attackers >= 2

    def effect_fn(event: Event, state: GameState) -> list[Event]:
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
        filter=attack_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(e, s)),
        duration='while_on_battlefield'
    )]


# --- Spider-Punk ---
# "Other Spiders you control have riot."
def spider_punk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # Grant riot to other Spiders - simplified as +1/+1 counter on ETB
    return [make_keyword_grant(
        obj,
        ['riot'],
        other_creatures_with_subtype(obj, "Spider")
    )]


# --- Silk, Web Weaver ---
# "Whenever you cast a creature spell, create a 1/1 green and white Human Citizen creature token."
def silk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Human Citizen Token',
                'controller': obj.controller,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Human', 'Citizen'],
                'colors': [Color.GREEN, Color.WHITE],
            },
            source=obj.id
        )]

    return [make_spell_cast_trigger(obj, effect_fn, spell_type_filter={CardType.CREATURE})]


# --- Spider-Man India ---
# "Whenever you cast a creature spell, put a +1/+1 counter on target creature you control. It gains flying until end of turn."
def spiderman_india_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Would need targeting - simplified to self
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [make_spell_cast_trigger(obj, effect_fn, spell_type_filter={CardType.CREATURE})]


# --- Carnage, Crimson Chaos ---
# "Trample" + "When Carnage enters, return target creature card with mana value
# 3 or less from your graveyard to the battlefield." + Mayhem {B}{R}.
def _carnage_etb(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Reanimate handler will create a chooser among creatures with MV<=3 in our graveyard.
        return [Event(
            type=EventType.RETURN_FROM_GRAVEYARD,
            payload={
                'player': obj.controller,
                'card_type': 'creature',
                'max_mv': 3,
                'amount': 1,
            },
            source=obj.id
        )]
    # Note: "attacks each combat / sacrifice on combat damage" rider is left unwired
    # (engine gap: per-card grant of self-sacrifice trigger on reanimated target).
    return [make_etb_trigger(obj, etb_effect)]


carnage_setup = combine_setups(
    make_mayhem_setup("{B}{R}"),
    _carnage_etb,
)


# --- Mister Negative ---
# "When Mister Negative enters, you may exchange life totals with target opponent."
def mister_negative_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting for life exchange - placeholder
        return []
    return [make_etb_trigger(obj, etb_effect)]


# --- The Spot, Living Portal ---
# "When The Spot enters, exile up to one target nonland permanent and up to one target nonland permanent card from a graveyard."
def the_spot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting - placeholder
        return []
    return [make_etb_trigger(obj, etb_effect)]


# --- Sun-Spider, Nimble Webber ---
# "When Sun-Spider enters, search your library for an Aura or Equipment card, reveal it, put it into your hand, then shuffle."
def sun_spider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def aura_or_equipment(card_obj, st):
        subs = card_obj.characteristics.subtypes or set()
        return "Aura" in subs or "Equipment" in subs

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return open_library_search(
            state, obj.controller, obj.id,
            filter_fn=aura_or_equipment,
            destination="hand",
            reveal=True,
            shuffle_after=True,
            optional=False,
            min_count=1,
            prompt="Search your library for an Aura or Equipment card and put it into your hand.",
        )
    return [make_etb_trigger(obj, etb_effect)]


# --- Rhino, Barreling Brute ---
# "Whenever Rhino attacks, if you've cast a spell with mana value 4 or greater this turn, draw a card."
def rhino_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Would need to track spells cast this turn - simplified to always draw
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


# --- Kraven the Hunter ---
# "Whenever a creature an opponent controls with the greatest power among creatures that player controls dies, draw a card and put a +1/+1 counter on Kraven the Hunter."
def kraven_the_hunter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def creature_dies_filter(event: Event, state: GameState) -> bool:
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
        return (dying_obj.controller != obj.controller and
                CardType.CREATURE in dying_obj.characteristics.types)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.COUNTER_ADDED, payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1}, source=obj.id)
        ]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=creature_dies_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(e, s)),
        duration='while_on_battlefield'
    )]


# --- Lizard, Connors's Curse ---
# "When Lizard, Connors's Curse enters, up to one other target creature loses all abilities and becomes a green Lizard creature with base power and toughness 4/4."
def lizard_connors_curse_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting - placeholder
        return []
    return [make_etb_trigger(obj, etb_effect)]


# --- Molten Man, Inferno Incarnate ---
# "When Molten Man enters, search your library for a basic Mountain card, put it onto the battlefield tapped, then shuffle."
def molten_man_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return open_library_search(
            state, obj.controller, obj.id,
            filter_fn=basic_subtype_filter("Mountain"),
            destination="battlefield_tapped",
            shuffle_after=True,
            optional=False,
            min_count=1,
            prompt="Search your library for a basic Mountain card and put it onto the battlefield tapped.",
        )
    return [make_etb_trigger(obj, etb_effect)]


# --- Spider-Man, Brooklyn Visionary ---
# Web-slinging {2}{G} + "When Spider-Man enters, search your library for a basic
# land card, put it onto the battlefield tapped, then shuffle."
def _spiderman_brooklyn_visionary_etb(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return open_library_search(
            state, obj.controller, obj.id,
            filter_fn=basic_land_filter(),
            destination="battlefield_tapped",
            shuffle_after=True,
            optional=False,
            min_count=1,
            prompt="Search your library for a basic land card and put it onto the battlefield tapped.",
        )
    return [make_etb_trigger(obj, etb_effect)]


spiderman_brooklyn_visionary_setup = combine_setups(
    make_web_slinging_setup("{2}{G}"),
    _spiderman_brooklyn_visionary_etb,
)


# --- Mechanical Mobster ---
# "When this creature enters, exile up to one target card from a graveyard. Target creature you control connives."
def mechanical_mobster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Connive effect
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]


# --- Scorpion, Seething Striker ---
# "At the beginning of your end step, if a creature died this turn, target creature you control connives."
def scorpion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_end_step_trigger

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Would need to track if creature died this turn - simplified
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_end_step_trigger(obj, effect_fn)]


# --- Spider-Woman, Stunning Savior ---
# "Artifacts and creatures your opponents control enter tapped."
def spiderwoman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering_obj = state.objects.get(entering_id)
        if not entering_obj:
            return False
        if entering_obj.controller == obj.controller:
            return False
        types = entering_obj.characteristics.types
        return CardType.ARTIFACT in types or CardType.CREATURE in types

    def tap_handler(event: Event, state: GameState) -> InterceptorResult:
        entering_id = event.payload.get('object_id')
        new_events = [Event(
            type=EventType.TAP,
            payload={'object_id': entering_id},
            source=obj.id
        )]
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=etb_filter,
        handler=tap_handler,
        duration='while_on_battlefield'
    )]


# --- Araña, Heart of the Spider ---
# "Whenever you attack, put a +1/+1 counter on target attacking creature."
def arana_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.COMBAT_DECLARED and
                state.active_player == obj.controller)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Would need targeting - simplified to put on self if attacking
        attackers = event.payload.get('attackers', [])
        if obj.id in attackers:
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id
            )]
        return []

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(e, s)),
        duration='while_on_battlefield'
    )]


# --- Black Cat, Cunning Thief ---
# "When Black Cat enters, look at the top nine cards of target opponent's library..."
def black_cat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting and library manipulation - placeholder
        return []
    return [make_etb_trigger(obj, etb_effect)]


# --- Gwenom, Remorseless ---
# "Whenever Gwenom attacks, until end of turn, you may look at the top card of your library..."
def gwenom_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Complex ability - placeholder
        return []
    return [make_attack_trigger(obj, attack_effect)]


# --- Spider-Man Noir ---
# "Whenever a creature you control attacks alone, put a +1/+1 counter on it. Then surveil X."
def spiderman_noir_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.COMBAT_DECLARED:
            return False
        attackers = event.payload.get('attackers', [])
        return len(attackers) == 1 and state.active_player == obj.controller

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        attackers = event.payload.get('attackers', [])
        if attackers:
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': attackers[0], 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id
            )]
        return []

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(e, s)),
        duration='while_on_battlefield'
    )]


# --- Shriek, Treblemaker ---
# "Whenever a creature an opponent controls dies, Shriek deals 1 damage to that player."
def shriek_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def creature_dies_filter(event: Event, state: GameState) -> bool:
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
        return (dying_obj.controller != obj.controller and
                CardType.CREATURE in dying_obj.characteristics.types)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        dying_id = event.payload.get('object_id')
        dying_obj = state.objects.get(dying_id)
        if dying_obj:
            return [Event(
                type=EventType.DAMAGE,
                payload={'target': dying_obj.controller, 'amount': 1, 'source': obj.id, 'is_combat': False},
                source=obj.id
            )]
        return []

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=creature_dies_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(e, s)),
        duration='while_on_battlefield'
    )]


# =============================================================================
# ADDITIONAL SETUP INTERCEPTORS (auto-generated stubs and wiring)
# =============================================================================

# --- Anti-Venom, Horrifying Healer ---
# "When Anti-Venom enters, return target creature card from your graveyard to the battlefield.
#  Damage to him is prevented and replaced with +1/+1 counters."
def antivenom_horrifying_healer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    # ETB: reanimate (engine gap: targeted graveyard reanimate not wired)
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # engine gap: targeted reanimate from graveyard

    interceptors = [make_etb_trigger(obj, etb_effect)]

    # Damage prevention -> counter replacement
    def dmg_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        return event.payload.get('target') == obj.id

    def dmg_handler(event: Event, state: GameState) -> InterceptorResult:
        amount = event.payload.get('amount', 0)
        # Replace damage with counters
        new_events = []
        if amount > 0:
            new_events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': amount},
                source=obj.id
            ))
        return InterceptorResult(action=InterceptorAction.PREVENT, new_events=new_events)

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=dmg_filter,
        handler=dmg_handler,
        duration='while_on_battlefield'
    ))
    return interceptors


# --- Arachne, Psionic Weaver ---
# Web-slinging {W} + "As Arachne enters, look at an opponent's hand, choose a
# type; spells of that type cost {1} more." Hand-reveal + cost-modifier are
# engine gaps; we still wire the web-slinging alt cost.
def _arachne_etb(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # engine gap: hand-reveal + cost-modifier-by-chosen-type
    return [make_etb_trigger(obj, etb_effect)]


arachne_psionic_weaver_setup = combine_setups(
    make_web_slinging_setup("{W}"),
    _arachne_etb,
)


# --- Costume Closet ---
# "Enters with two +1/+1 counters; tap to move counter; trigger on modified creature leaving."
def costume_closet_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []

    # ETB: place 2 +1/+1 counters on this artifact
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 2},
            source=obj.id
        )]
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Trigger when a modified creature you control leaves the battlefield
    def modified_leaves_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        leaving_id = event.payload.get('object_id')
        if leaving_id == obj.id:
            return False
        leaving = state.objects.get(leaving_id)
        if not leaving or leaving.controller != obj.controller:
            return False
        if CardType.CREATURE not in leaving.characteristics.types:
            return False
        # "Modified" = has counters or attached aura/equipment
        has_counters = bool(getattr(leaving.state, 'counters', {}))
        has_attachments = bool(getattr(leaving.state, 'attachments', []))
        return has_counters or has_attachments

    def modified_leaves_effect(event: Event, state: GameState) -> list[Event]:
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
        filter=modified_leaves_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=modified_leaves_effect(e, s)),
        duration='while_on_battlefield'
    ))
    return interceptors


# --- Daily Bugle Reporters ---
# "When this creature enters, choose one - +1/+1 counters or graveyard return."
def daily_bugle_reporters_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # engine gap: modal targeting (counters vs graveyard return)
    return [make_etb_trigger(obj, etb_effect)]


# --- Flash Thompson, Spider-Fan ---
# "When Flash Thompson enters, choose one or both - tap or untap target creature."
def flash_thompson_spiderfan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # engine gap: modal targeting (tap/untap)
    return [make_etb_trigger(obj, etb_effect)]


# --- Friendly Neighborhood ---
# "Enchant land. ETB: create three 1/1 G/W Human Citizen tokens. Enchanted land has activated ability."
def friendly_neighborhood_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for _ in range(3):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Human Citizen Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Human', 'Citizen'],
                    'colors': [Color.GREEN, Color.WHITE],
                },
                source=obj.id
            ))
        return events
    # engine gap: enchanted-land-grants-activated-ability not wired
    return [make_etb_trigger(obj, etb_effect)]


# --- Origin of Spider-Man ---
# Saga: I-Spider token, II-counter+type change, III-double strike grant
def origin_of_spiderman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Saga I/II/III.

    I — Create a 2/1 green Spider creature token with reach.
    II — Put a +1/+1 counter on target creature you control; it becomes a legendary Spider Hero (engine gap: target+type-add).
    III — Target creature you control gains double strike EOT (engine gap: target)."""
    def i(o, s):
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': o.controller,
                'token': {
                    'name': 'Spider',
                    'power': 2, 'toughness': 1,
                    'types': {CardType.CREATURE},
                    'subtypes': {'Spider'},
                    'colors': {Color.GREEN},
                    'abilities': [{'keyword': 'reach'}],
                },
            },
            source=o.id,
        )]

    def ii(_o, _s): return []  # engine gap: target + type-add

    def iii(_o, _s): return []  # engine gap: target + double strike grant

    return make_saga_setup(obj, {1: i, 2: ii, 3: iii})


# --- Rent Is Due ---
# "At the beginning of your end step, you may tap two untapped creatures and/or Treasures. If so draw a card; else sacrifice."
def rent_is_due_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_end_step_trigger

    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified: draw a card if controller has 2+ untapped creatures/treasures, else sacrifice
        eligible = 0
        for other in state.objects.values():
            if (other.controller == obj.controller and
                    other.zone == ZoneType.BATTLEFIELD and
                    not getattr(other.state, 'tapped', False)):
                if (CardType.CREATURE in other.characteristics.types or
                        'Treasure' in other.characteristics.subtypes):
                    eligible += 1
        if eligible >= 2:
            return [Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            )]
        return [Event(
            type=EventType.SACRIFICE,
            payload={'object_id': obj.id, 'controller': obj.controller},
            source=obj.id
        )]

    return [make_end_step_trigger(obj, end_step_effect)]


# --- Spectacular Spider-Man ---
# Activated abilities only — no triggers to register at ETB.
def spectacular_spiderman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: activated abilities (gain flying / sac + grant hexproof) handled elsewhere


# --- Spider-Man, Web-Slinger ---
# "Web-slinging {W}" — alt cost mechanic. The helper stamps the alt cost on
# the card_def so the engine's cast-cost lookup can see it.
spiderman_webslinger_setup = make_web_slinging_setup("{W}")


# --- Spider-UK ---
# Web-slinging + "At end step, if 2+ creatures entered this turn, draw a card and gain 2 life."
def _spideruk_end_step_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_end_step_trigger

    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        # engine gap: tracking creatures-entered-this-turn count is heuristic
        entered = getattr(state, 'creatures_entered_this_turn', {}).get(obj.controller, 0)
        if entered >= 2:
            return [
                Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
                Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=obj.id),
            ]
        return []
    return [make_end_step_trigger(obj, end_step_effect)]


spideruk_setup = combine_setups(
    make_web_slinging_setup("{2}{W}"),
    _spideruk_end_step_setup,
)


# --- Web Up ---
# "When this enchantment enters, exile target nonland permanent an opponent controls until ~ leaves."
def web_up_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # engine gap: targeted exile-until-leaves
    return [make_etb_trigger(obj, etb_effect)]


# --- Web-Shooters ---
# Equipment - static enchant ability; +1/+1, reach, attack trigger to tap.
def webshooters_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipped creature gets +1/+1, reach, and on attack taps an opponent's creature.

    Wired statics: +1/+1 boost and reach grant on the attached creature.
    Wired trigger: when the equipped creature attacks, request a target tap on
    a creature an opponent controls.
    """
    def is_equipped_target(target: GameObject, state: GameState) -> bool:
        if CardType.CREATURE not in target.characteristics.types:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        return target.state.attached_to == obj.id

    interceptors: list[Interceptor] = []
    interceptors.extend(make_static_pt_boost(obj, 1, 1, is_equipped_target))
    interceptors.append(make_keyword_grant(obj, ['reach'], is_equipped_target))

    def attacker_is_equipped(event: Event, state: GameState, source_obj: GameObject) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        return attacker.state.attached_to == source_obj.id

    def attack_effect(event: Event, state: GameState) -> list[Event]:
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
                'prompt': "Choose a creature an opponent controls to tap",
            },
            source=obj.id,
        )]

    interceptors.append(make_attack_trigger(obj, attack_effect, filter_fn=attacker_is_equipped))
    return interceptors


# --- Wild Pack Squad ---
# "At the beginning of combat on your turn, up to one target creature gains first strike and vigilance until end of turn."
def wild_pack_squad_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def combat_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.PHASE_START and
                event.payload.get('phase') == 'combat' and
                state.active_player == obj.controller)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.TARGET_REQUIRED,
            payload={
                'source': obj.id,
                'controller': obj.controller,
                'effects': [
                    {'effect': 'grant_keyword',
                     'params': {'keyword': 'first strike', 'duration': 'end_of_turn'}},
                    {'effect': 'grant_keyword',
                     'params': {'keyword': 'vigilance', 'duration': 'end_of_turn'}},
                ],
                'target_filter': 'creature',
                'min_targets': 1,
                'max_targets': 1,
                'optional': True,
                'prompt': "Choose up to one creature to gain first strike and vigilance until end of turn",
            },
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(e, s)),
        duration='while_on_battlefield'
    )]


# --- With Great Power... ---
# Aura: +2/+2 per attached aura/equipment; redirect damage from you to enchanted creature.
def with_great_power_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: aura attaching + dynamic +2/+2 per attachments + damage redirect


# --- Beetle, Legacy Criminal ---
# Activated graveyard ability (Aftermath-style).
def beetle_legacy_criminal_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: activated-from-graveyard not auto-wired


# --- Chameleon, Master of Disguise ---
# "Enter as a copy" + Mayhem {2}{U} alt cost. Wire the Mayhem alt cost via the
# helper; enter-as-copy still requires engine support and is left as a gap.
chameleon_master_of_disguise_setup = make_mayhem_setup("{2}{U}")


# --- The Clone Saga ---
def the_clone_saga_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Saga I/II/III.

    I — Surveil 3.
    II — When you next cast a creature spell this turn, copy it (engine gap: delayed copy trigger).
    III — Choose a card name; draw a card whenever a creature with that name deals combat damage (engine gap: name choice + damage trigger)."""
    def i(o, s):
        return [Event(
            type=EventType.SURVEIL,
            payload={'player': o.controller, 'count': 3},
            source=o.id,
        )]

    def ii(_o, _s): return []  # engine gap: delayed copy trigger
    def iii(_o, _s): return []  # engine gap: name choice + damage trigger

    return make_saga_setup(obj, {1: i, 2: ii, 3: iii})


# --- Doc Ock, Sinister Scientist ---
# Conditional base P/T 8/8 if 8+ cards in graveyard; hexproof while controlling another Villain.
def doc_ock_sinister_scientist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []

    # P/T = 8/8 if 8+ cards in your graveyard. Use QUERY_POWER / QUERY_TOUGHNESS.
    source_id = obj.id

    def gy_count(state: GameState) -> int:
        graveyard = state.zones.get(f'graveyard_{obj.controller}')
        return len(graveyard.objects) if graveyard else 0

    def make_pt_query(query_event_type: EventType, base_value: int):
        def pt_filter(event: Event, state: GameState) -> bool:
            if event.type != query_event_type:
                return False
            src = state.objects.get(source_id)
            if not src or src.zone != ZoneType.BATTLEFIELD:
                return False
            if event.payload.get('object_id') != source_id:
                return False
            return gy_count(state) >= 8

        def pt_handler(event: Event, state: GameState) -> InterceptorResult:
            new_event = event.copy()
            new_event.payload['value'] = base_value
            return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

        return Interceptor(
            id=new_id(),
            source=source_id,
            controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=pt_filter,
            handler=pt_handler,
            duration='while_on_battlefield'
        )

    interceptors.append(make_pt_query(EventType.QUERY_POWER, 8))
    interceptors.append(make_pt_query(EventType.QUERY_TOUGHNESS, 8))

    # Hexproof while you control another Villain — engine gap: dynamic hexproof toggle
    return interceptors


# --- Hydro-Man, Fluid Felon ---
# Whenever you cast a blue spell, +1/+1 EOT; at end step transforms to a land until next turn.
def hydroman_fluid_felon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []

    def blue_spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': 1, 'toughness_mod': 1, 'duration': 'end_of_turn'},
            source=obj.id
        )]

    interceptors.append(make_spell_cast_trigger(
        obj, blue_spell_effect,
        color_filter={Color.BLUE},
        controller_only=True
    ))
    # End step land-transform: engine gap (type-changing self-replacement)
    return interceptors


# --- Impostor Syndrome ---
# "Whenever a nontoken creature you control deals combat damage to a player, create a copy token."
def impostor_syndrome_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('is_combat', False):
            return False
        src_id = event.payload.get('source')
        src = state.objects.get(src_id)
        if not src or src.controller != obj.controller:
            return False
        if getattr(src.state, 'is_token', False):
            return False
        if CardType.CREATURE not in src.characteristics.types:
            return False
        # Damage to a player
        target_id = event.payload.get('target')
        return target_id in state.players

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        src_id = event.payload.get('source')
        src = state.objects.get(src_id)
        if not src:
            return []
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': f"{src.characteristics.name} Token",
                'controller': obj.controller,
                'power': src.characteristics.power,
                'toughness': src.characteristics.toughness,
                'types': list(src.characteristics.types),
                'subtypes': list(src.characteristics.subtypes),
                'colors': list(src.characteristics.colors),
                'is_copy_of': src_id,
            },
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=damage_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(e, s)),
        duration='while_on_battlefield'
    )]


# --- Lady Octopus, Inspired Inventor ---
# Adds ingenuity counters on first/second draw; activated cast-without-paying.
def lady_octopus_inspired_inventor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_draw_trigger

    draws_this_turn = {'value': 0, 'turn': -1}

    def draw_effect(event: Event, state: GameState) -> list[Event]:
        cur_turn = getattr(state, 'turn_number', 0)
        if draws_this_turn['turn'] != cur_turn:
            draws_this_turn['turn'] = cur_turn
            draws_this_turn['value'] = 0
        draws_this_turn['value'] += 1
        if draws_this_turn['value'] in (1, 2):
            return [Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': 'ingenuity', 'amount': 1},
                source=obj.id
            )]
        return []

    return [make_draw_trigger(obj, draw_effect)]


# --- Madame Web, Clairvoyant ---
# Static "look at top card" + cast Spider/noncreature spells from top + attack-mill option.
def madame_web_clairvoyant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # "may mill a card" — best-effort optional mill
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    # engine gap: cast-from-top-of-library not wired
    return [make_attack_trigger(obj, attack_effect)]


# --- Oscorp Research Team ---
# Activated ability {6}{U}: draw 2.
def oscorp_research_team_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: activated ability cost evaluation is handled elsewhere


# --- Robotics Mastery ---
# Aura: ETB - create two 1/1 colorless flying Robot tokens. +2/+2 to enchanted.
def robotics_mastery_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for _ in range(2):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Robot Token',
                    'controller': obj.controller,
                    'power': 1,
                    'toughness': 1,
                    'types': [CardType.ARTIFACT, CardType.CREATURE],
                    'subtypes': ['Robot'],
                    'colors': [],
                    'keywords': ['flying'],
                },
                source=obj.id
            ))
        return events
    return [make_etb_trigger(obj, etb_effect)]
    # engine gap: aura +2/+2 to enchanted creature is handled by the aura layer system


# --- Spider-Man No More ---
# Aura: enchanted creature becomes 1/1 Citizen with defender, loses other abilities/types.
def spiderman_no_more_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: type-rewriting aura with ability removal


# --- Alien Symbiosis ---
# Aura giving +1/+1, menace, Symbiote type. Discard-from-graveyard alt cost.
def alien_symbiosis_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: aura attribute layering + alternative cast cost from graveyard


# --- The Death of Gwen Stacy ---
def the_death_of_gwen_stacy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Saga I/II/III.

    I — Destroy target creature (engine gap: target).
    II — Each player may discard a card; each who doesn't loses 3 life (engine gap: optional discard prompt).
    III — Exile any number of target players' graveyards (engine gap: target)."""
    def i(_o, _s): return []  # engine gap: target creature
    def ii(_o, _s): return []  # engine gap: optional discard prompt
    def iii(_o, _s): return []  # engine gap: target graveyards

    return make_saga_setup(obj, {1: i, 2: ii, 3: iii})


# --- Inner Demons Gangsters ---
# Activated discard-pump + menace. No persistent triggers.
def inner_demons_gangsters_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: activated ability with discard cost handled at activation site


# --- Merciless Enforcers ---
# Activated 1-damage-each-opponent ping; lifelink keyword.
def merciless_enforcers_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: activated ability cost/effect handled at activation site


# --- Parker Luck ---
# At end step, two players each reveal top, swap MV-life-loss, then put cards in hand.
def parker_luck_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_end_step_trigger

    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        return []  # engine gap: simultaneous reveal + cross-mv life loss

    return [make_end_step_trigger(obj, end_step_effect)]


# --- The Soul Stone ---
# Tap for {B}, harness ability, then upkeep reanimate (Infinity Stone mechanic).
def the_soul_stone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: Infinity Stone harness flag + upkeep reanimate


# --- Swarm, Being of Bees ---
# Flash + flying + Mayhem {B} alt cost. Flash/flying are static keywords already
# carried on the card_def; only the Mayhem alt cost needs explicit wiring.
swarm_being_of_bees_setup = make_mayhem_setup("{B}")


# --- Venom, Evil Unleashed ---
# Deathtouch + activated graveyard ability.
def venom_evil_unleashed_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: activated-from-graveyard ability


# --- Electro, Assaulting Battery ---
# Don't lose unspent red mana, +R from instants/sorceries cast, LTB X-damage trigger.
def electro_assaulting_battery_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []

    # Whenever you cast an instant or sorcery, add {R}.
    def add_red_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MANA_PRODUCED,
            payload={'player': obj.controller, 'mana': {'R': 1}},
            source=obj.id
        )]

    interceptors.append(make_spell_cast_trigger(
        obj, add_red_effect,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY},
        controller_only=True
    ))

    # LTB X-damage: engine gap (X cost prompt + damage)
    return interceptors


# --- Masked Meower ---
# Haste + activated discard-sac to draw.
def masked_meower_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: activated ability with discard-and-sac cost


# --- Maximum Carnage ---
def maximum_carnage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Saga I/II/III.

    I — Until your next turn, each creature attacks each combat if able and attacks a player other than you if able (engine gap: global goad).
    II — Add {R}{R}{R}.
    III — This Saga deals 5 damage to each opponent."""
    def i(_o, _s): return []  # engine gap: global goad-like restriction

    def ii(o, s):
        return [Event(
            type=EventType.MANA_PRODUCED,
            payload={'player': o.controller, 'mana': {Color.RED: 3}},
            source=o.id,
        )]

    def iii(o, s):
        events: list[Event] = []
        for pid in s.players:
            if pid == o.controller:
                continue
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'source_id': o.id, 'target': pid,
                         'target_id': pid, 'amount': 5},
                source=o.id,
            ))
        return events

    return make_saga_setup(obj, {1: i, 2: ii, 3: iii})


# --- Raging Goblinoids ---
# Haste (static) + Mayhem {2}{R} alt cost.
raging_goblinoids_setup = make_mayhem_setup("{2}{R}")


# --- Shadow of the Goblin ---
# Main-phase loot + ping per land/spell-from-non-hand.
def shadow_of_the_goblin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []

    # First main phase: discard a card, then draw a card
    def first_main_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') not in ('main_1', 'main1', 'first_main'):
            return False
        return state.active_player == obj.controller

    def first_main_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
        ]

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=first_main_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=first_main_effect(e, s)),
        duration='while_on_battlefield'
    ))

    # engine gap: "play a land or cast a spell from anywhere other than your hand" trigger
    return interceptors


# --- Spider-Gwen, Free Spirit ---
# "Whenever Spider-Gwen becomes tapped, you may discard a card. If you do, draw a card."
def spidergwen_free_spirit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_tap_trigger

    def tap_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
        ]

    return [make_tap_trigger(obj, tap_effect)]


# --- Spider-Islanders ---
# Mayhem {1}{R} alt cost only.
spiderislanders_setup = make_mayhem_setup("{1}{R}")


# --- Spider-Verse ---
# Spiders ignore legend rule; copy spells cast from non-hand. Once per turn.
def spiderverse_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: legend rule waiver + cast-from-non-hand copy mechanic


# --- Stegron the Dinosaur Man ---
# Menace + activated discard-self pump-to-Dinosaur. No persistent triggers.
def stegron_the_dinosaur_man_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: activated discard-self ability


# --- Superior Foes of Spider-Man ---
# Trample + 4MV+ spell impulse.
def superior_foes_of_spiderman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.IMPULSE_DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_spell_cast_trigger(obj, effect_fn, mana_value_min=4)]


# --- Taxi Driver ---
# Activated ability {1},{T}: target gains haste EOT.
def taxi_driver_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: activated targeted keyword grant


# --- Guy in the Chair ---
# {T} for any color, {2}{G},{T}: +1/+1 counter on target Spider.
def guy_in_the_chair_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: activated mana ability + activated counter ability


# --- Kraven's Cats ---
# Activated pump.
def kravens_cats_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: activated pump ability


# --- Kraven's Last Hunt ---
def kravens_last_hunt_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Saga I/II/III.

    I — Mill 5; conditional damage to target creature (engine gap: conditional damage from greatest power in graveyard).
    II — Target creature you control gets +2/+2 EOT (engine gap: target).
    III — Return target creature card from your graveyard to your hand (engine gap: target card in graveyard)."""
    def i(o, s):
        return [Event(
            type=EventType.MILL,
            payload={'player': o.controller, 'count': 5},
            source=o.id,
        )]

    def ii(_o, _s): return []  # engine gap: target + buff
    def iii(_o, _s): return []  # engine gap: target card in graveyard

    return make_saga_setup(obj, {1: i, 2: ii, 3: iii})


# --- Miles Morales ---
# ETB +1/+1 to up to two targets; transform; double counters on attack.
def miles_morales_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_targeted_etb_trigger(
        obj,
        effect='counter_add',
        effect_params={'counter_type': '+1/+1', 'amount': 1},
        target_filter='creature',
        min_targets=0,
        max_targets=2,
        optional=True,
        prompt="Choose up to two creatures to put a +1/+1 counter on each"
    )]
    # engine gap: transform mechanic + attack-counter doubling not wired


# --- Pictures of Spider-Man ---
# ETB look-at-top-5, activated sac for treasure.
def pictures_of_spiderman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # engine gap: look-at-top-N + select-up-to-2-creatures
    return [make_etb_trigger(obj, etb_effect)]


# --- Radioactive Spider ---
# Reach + deathtouch + activated tutor.
def radioactive_spider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: activated tutor for Spider Hero


# --- Sandman, Shifting Scoundrel ---
# Power/toughness = number of lands you control.
def sandman_shifting_scoundrel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors = []
    source_id = obj.id

    def land_count(state: GameState) -> int:
        count = 0
        for other in state.objects.values():
            if (other.controller == obj.controller and
                    other.zone == ZoneType.BATTLEFIELD and
                    CardType.LAND in other.characteristics.types):
                count += 1
        return count

    def make_pt_query(query_event_type: EventType):
        def pt_filter(event: Event, state: GameState) -> bool:
            if event.type != query_event_type:
                return False
            src = state.objects.get(source_id)
            if not src or src.zone != ZoneType.BATTLEFIELD:
                return False
            return event.payload.get('object_id') == source_id

        def pt_handler(event: Event, state: GameState) -> InterceptorResult:
            new_event = event.copy()
            new_event.payload['value'] = land_count(state)
            return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

        return Interceptor(
            id=new_id(),
            source=source_id,
            controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=pt_filter,
            handler=pt_handler,
            duration='while_on_battlefield'
        )

    interceptors.append(make_pt_query(EventType.QUERY_POWER))
    interceptors.append(make_pt_query(EventType.QUERY_TOUGHNESS))
    # engine gap: "can't be blocked by power<=2" + activated graveyard reanimate of self+land
    return interceptors


# --- Spiders-Man, Heroic Horde ---
# Web-slinging {4}{G}{G} + ETB *if cast via web-slinging*: gain 3 + create two 2/1 Spiders.
# We use combine_setups: the web-slinging helper handles the alt cost and tracks
# "this was cast via web-slinging" in state.turn_data; the ETB trigger below
# checks that flag before producing the bonus events.
def _spidersman_heroic_horde_etb(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        if not was_discarded_this_turn:
            pass  # noqa - keep imports referenced
        # Only fire if this card was cast via web-slinging this turn.
        if not _was_websling(state, obj.id):
            return []
        events = [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
        for _ in range(2):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'name': 'Spider Token',
                    'controller': obj.controller,
                    'power': 2,
                    'toughness': 1,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Spider'],
                    'colors': [Color.GREEN],
                    'keywords': ['reach'],
                },
                source=obj.id
            ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def _was_websling(state: GameState, object_id: str) -> bool:
    from src.engine.spm_mechanics import was_web_slung_this_turn
    return was_web_slung_this_turn(state, object_id)


spidersman_heroic_horde_setup = combine_setups(
    make_web_slinging_setup("{4}{G}{G}"),
    _spidersman_heroic_horde_etb,
)


# --- Supportive Parents ---
# Mana ability: tap two creatures for any color.
def supportive_parents_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: activated mana ability with tap-two-creatures cost


# --- Web of Life and Destiny ---
# Convoke + at-combat tutor-onto-battlefield.
def web_of_life_and_destiny_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def combat_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.PHASE_START and
                event.payload.get('phase') == 'combat' and
                state.active_player == obj.controller)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # engine gap: look-at-top-5 + creature-onto-battlefield

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(e, s)),
        duration='while_on_battlefield'
    )]


# --- Biorganic Carapace ---
# Equipment - ETB self-attach, +2/+2, combat-damage draw per modified creature.
def biorganic_carapace_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: equipment ETB-attach + dynamic per-modified-creature draw


# --- Cheering Crowd ---
# Each player's first main: may put +1/+1 counter and add {C} per counter.
def cheering_crowd_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def first_main_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        return event.payload.get('phase') in ('main_1', 'main1', 'first_main')

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # engine gap: each-player-may-counter + mana-add per counter

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=first_main_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(e, s)),
        duration='while_on_battlefield'
    )]


# --- Jackal, Genius Geneticist ---
# Trample + copy creature spell when MV equals Jackal's power.
def jackal_genius_geneticist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def spell_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        spell_id = event.payload.get('spell_id')
        spell = state.objects.get(spell_id) if spell_id else None
        if not spell or CardType.CREATURE not in spell.characteristics.types:
            return False
        cur = state.objects.get(obj.id)
        if not cur:
            return False
        return event.payload.get('mana_value', 0) == cur.characteristics.power

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.COPY_SPELL,
                payload={'spell_id': event.payload.get('spell_id'), 'controller': obj.controller, 'not_legendary': True},
                source=obj.id
            ),
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id
            ),
        ]

    return [make_spell_cast_trigger(obj, effect_fn, controller_only=True, filter_fn=lambda e, s, o: spell_filter(e, s))]


# --- Kraven, Proud Predator ---
# Power = greatest mana value among permanents you control.
def kraven_proud_predator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    source_id = obj.id

    def greatest_mv(state: GameState) -> int:
        best = 0
        for other in state.objects.values():
            if (other.controller == obj.controller and
                    other.zone == ZoneType.BATTLEFIELD):
                mv = getattr(other.characteristics, 'mana_value', 0) or 0
                if mv > best:
                    best = mv
        return best

    def power_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        src = state.objects.get(source_id)
        if not src or src.zone != ZoneType.BATTLEFIELD:
            return False
        return event.payload.get('object_id') == source_id

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['value'] = greatest_mv(state)
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(),
        source=source_id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=power_filter,
        handler=power_handler,
        duration='while_on_battlefield'
    )]


# --- Morbius the Living Vampire ---
# Flying/vigilance/lifelink + activated graveyard "look at top 3, hand 1."
def morbius_the_living_vampire_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: activated-from-graveyard impulse-style top-3


# --- Scarlet Spider, Ben Reilly ---
# Web-slinging {R}{G} + Sensational Save: if cast via web-slinging, enters with
# X +1/+1 counters where X is the MV of the creature returned to pay the cost.
def _scarlet_spider_ben_reilly_etb(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        from src.engine.spm_mechanics import was_web_slung_this_turn, web_slinging_returned_mv_for
        if not was_web_slung_this_turn(state, obj.id):
            return []
        x = web_slinging_returned_mv_for(state, obj.id)
        if x <= 0:
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': x},
            source=obj.id,
        )]
    return [make_etb_trigger(obj, etb_effect)]


scarlet_spider_ben_reilly_setup = combine_setups(
    make_web_slinging_setup("{R}{G}"),
    _scarlet_spider_ben_reilly_etb,
)


# --- Scarlet Spider, Kaine ---
# Menace (static) + ETB optional discard-for-counter + Mayhem {B/R}.
def _scarlet_spider_kaine_etb(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id
            ),
        ]
    return [make_etb_trigger(obj, etb_effect)]


scarlet_spider_kaine_setup = combine_setups(
    make_mayhem_setup("{B/R}"),
    _scarlet_spider_kaine_etb,
)


# --- Skyward Spider ---
# Ward 2 + flying-while-modified.
def skyward_spider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    source_id = obj.id

    def ability_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_ABILITIES:
            return False
        target_id = event.payload.get('object_id')
        if target_id != source_id:
            return False
        target = state.objects.get(target_id)
        if not target:
            return False
        # "Modified" = has counters or attached aura/equipment
        has_counters = bool(getattr(target.state, 'counters', {}))
        has_attachments = bool(getattr(target.state, 'attachments', []))
        return has_counters or has_attachments

    def ability_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []))
        if 'flying' not in granted:
            granted.append('flying')
        new_event.payload['granted'] = granted
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [Interceptor(
        id=new_id(),
        source=source_id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=ability_filter,
        handler=ability_handler,
        duration='while_on_battlefield'
    )]


# --- Spider Manifestation ---
# Reach + tap for {R}/{G} + untap on 4MV+ spell.
def spider_manifestation_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.UNTAP,
            payload={'object_id': obj.id},
            source=obj.id
        )]
    return [make_spell_cast_trigger(obj, effect_fn, mana_value_min=4)]


# --- Spider-Man 2099 ---
# Double strike, vigilance, conditional end-step damage.
def spiderman_2099_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_end_step_trigger

    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        return []  # engine gap: tracking spell-from-non-hand or land-this-turn + targeted damage

    return [make_end_step_trigger(obj, end_step_effect)]


# --- Superior Spider-Man ---
# Enter as a copy of a graveyard creature (replacement).
def superior_spiderman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: enter-as-copy-from-graveyard replacement


# --- Symbiote Spider-Man ---
# Combat damage to player: look at top X, hand 1, rest to GY. Activated graveyard counter+ability transfer.
def symbiote_spiderman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('is_combat', False):
            return False
        if event.payload.get('source') != source.id:
            return False
        return event.payload.get('target') in state.players

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # engine gap: full "look at X cards, choose 1 to hand, rest to GY" choice not wired;
        # approximate by milling the damage amount (player can recover via other effects)
        amount = event.payload.get('amount', 0)
        if amount <= 0:
            return []
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': amount},
            source=obj.id
        )]

    return [make_damage_trigger(obj, effect_fn, combat_only=True, filter_fn=damage_filter)]


# --- Bagel and Schmear ---
# Activated abilities only.
def bagel_and_schmear_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: activated tap-sac abilities


# --- Doc Ock's Tentacles ---
# Equipment with auto-attach trigger on 5MV+ creature ETB.
def doc_ocks_tentacles_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def big_creature_etb_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        if entering.controller != obj.controller:
            return False
        if CardType.CREATURE not in entering.characteristics.types:
            return False
        return getattr(entering.characteristics, 'mana_value', 0) >= 5

    def attach_effect(event: Event, state: GameState) -> list[Event]:
        entering_id = event.payload.get('object_id')
        return [Event(
            type=EventType.AUTO_EQUIP,
            payload={'equipment_id': obj.id, 'creature_id': entering_id},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=big_creature_etb_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=attach_effect(e, s)),
        duration='while_on_battlefield'
    )]


# --- Interdimensional Web Watch ---
# ETB exile top 2 + play-from-exile until next end step.
def interdimensional_web_watch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.IMPULSE_DRAW,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- Iron Spider, Stark Upgrade ---
# Vigilance + activated counter-distribution + activated draw.
def iron_spider_stark_upgrade_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: activated abilities only


# --- Living Brain, Mechanical Marvel ---
# At-combat artifact-becomes-creature effect.
def living_brain_mechanical_marvel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def combat_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.PHASE_START and
                event.payload.get('phase') == 'combat' and
                state.active_player == obj.controller)

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return []  # engine gap: targeted artifact-becomes-3/3-creature + untap

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(e, s)),
        duration='while_on_battlefield'
    )]


# --- Passenger Ferry ---
# Vehicle attack-trigger pay {U} for unblockable.
def passenger_ferry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []  # engine gap: optional cost + targeted unblockable
    return [make_attack_trigger(obj, attack_effect)]


# --- Peter Parker's Camera ---
# Enters with 3 film counters; activated ability to copy your activated/triggered ability.
def peter_parkers_camera_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'film', 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- Rocket-Powered Goblin Glider ---
# Equipment - ETB if cast from graveyard, attach. +2/+0 flying haste. Mayhem {2}.
# We wire the Mayhem alt cost; auto-attach-on-mayhem-cast is left as an engine gap.
rocketpowered_goblin_glider_setup = make_mayhem_setup("{2}")


# --- Spider-Mobile ---
# Trample, attack/block self-pump per Spider, crew 2.
def spidermobile_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def attack_or_block_filter(event: Event, state: GameState) -> bool:
        if event.type == EventType.ATTACK_DECLARED:
            return event.payload.get('attacker_id') == obj.id
        if event.type == EventType.BLOCK_DECLARED:
            return event.payload.get('blocker_id') == obj.id
        return False

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        spider_count = 0
        for other in state.objects.values():
            if (other.controller == obj.controller and
                    other.zone == ZoneType.BATTLEFIELD and
                    'Spider' in other.characteristics.subtypes):
                spider_count += 1
        if spider_count <= 0:
            return []
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': spider_count, 'toughness_mod': spider_count, 'duration': 'end_of_turn'},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_or_block_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=effect_fn(e, s)),
        duration='while_on_battlefield'
    )]


# --- Spider-Slayer, Hatred Honed ---
# Damage-to-Spider destroys; activated graveyard ability.
def spiderslayer_hatred_honed_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def damage_to_spider_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != source.id:
            return False
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        if not target:
            return False
        return 'Spider' in target.characteristics.subtypes

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        target_id = event.payload.get('target')
        return [Event(
            type=EventType.DESTROY,
            payload={'object_id': target_id},
            source=obj.id
        )]

    return [make_damage_trigger(obj, effect_fn, filter_fn=damage_to_spider_filter)]


# --- Spider-Suit ---
# Equipment static; no triggers.
def spidersuit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipped creature gets +2/+2 and is a Spider Hero in addition to its other types.

    Wired: +2/+2 boost on the attached creature.
    engine gap: 'is a Spider Hero in addition to its other types' subtype grant
    is not yet exposed via QUERY_ABILITIES/keyword_grant.
    """
    def is_equipped_target(target: GameObject, state: GameState) -> bool:
        if CardType.CREATURE not in target.characteristics.types:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        return target.state.attached_to == obj.id
    return make_static_pt_boost(obj, 2, 2, is_equipped_target)


# --- Steel Wrecking Ball ---
# ETB: 5 damage to target creature; activated discard-self destroy artifact.
def steel_wrecking_ball_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_targeted_etb_trigger(
        obj,
        effect='damage',
        effect_params={'amount': 5},
        target_filter='creature',
        prompt="Choose target creature to deal 5 damage to"
    )]
    # Activated discard-self destroy-artifact ability is handled at activation site.


# --- Subway Train ---
# ETB: optional pay {G} to fetch basic land.
def subway_train_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # engine gap: optional cost + tutor
    return [make_etb_trigger(obj, etb_effect)]


# --- Daily Bugle Building ---
def daily_bugle_building_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: land activated abilities (including targeted menace grant)


# --- Multiversal Passage ---
def multiversal_passage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: choose-basic-land-type + pay-2-life-or-tapped


# --- Ominous Asylum ---
def ominous_asylum_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: ETB tapped + activated surveil


# --- Oscorp Industries ---
def oscorp_industries_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: ETB tapped + ETB-from-graveyard penalty + mayhem


# --- Savage Mansion ---
def savage_mansion_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: ETB tapped + activated surveil


# --- Sinister Hideout ---
def sinister_hideout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: ETB tapped + activated surveil


# --- Suburban Sanctuary ---
def suburban_sanctuary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: ETB tapped + activated surveil


# --- University Campus ---
def university_campus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: ETB tapped + activated surveil


# --- Urban Retreat ---
def urban_retreat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: ETB tapped + bounce-creature-to-flicker activation


# --- Vibrant Cityscape ---
def vibrant_cityscape_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return []  # engine gap: tap-sacrifice fetch ability


# =============================================================================
# PHASE 2B VANILLA-SPELL RESOLVES
# =============================================================================

def villainous_wrath_resolve(targets: list, state: GameState) -> list[Event]:
    """Villainous Wrath: Target opponent loses life equal to creatures
    they control. Then destroy all creatures.
    """
    # Find the resolving spell so we can attribute events.
    spell_id = None
    stack_zone = state.zones.get('stack')
    if stack_zone:
        for obj_id in reversed(list(stack_zone.objects or [])):
            so = state.objects.get(obj_id)
            if so and so.name == "Villainous Wrath":
                spell_id = so.id
                break

    events: list[Event] = []

    # First: target opponent loses life equal to creatures they control.
    target_player = None
    if targets:
        for grp in targets:
            for t in grp or []:
                if t is not None and getattr(t, 'is_player', False):
                    target_player = t.id
                    break
            if target_player is not None:
                break

    if target_player is not None:
        creature_count = sum(
            1 for o in state.objects.values()
            if (o.controller == target_player and
                o.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in o.characteristics.types)
        )
        if creature_count > 0:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': target_player, 'amount': -creature_count},
                source=spell_id,
            ))

    # Then: destroy all creatures.
    for obj_id, o in state.objects.items():
        if (o.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in o.characteristics.types):
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': obj_id},
                source=spell_id,
            ))

    return events


# =============================================================================
# CARD DEFINITIONS
# =============================================================================

ANTIVENOM_HORRIFYING_HEALER = make_creature(
    name="Anti-Venom, Horrifying Healer",
    power=5, toughness=5,
    mana_cost="{W}{W}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Hero", "Symbiote"},
    supertypes={"Legendary"},
    text="When Anti-Venom enters, if he was cast, return target creature card from your graveyard to the battlefield.\nIf damage would be dealt to Anti-Venom, prevent that damage and put that many +1/+1 counters on him.",
    setup_interceptors=antivenom_horrifying_healer_setup,
)

ARACHNE_PSIONIC_WEAVER = make_creature(
    name="Arachne, Psionic Weaver",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Web-slinging {W} (You may cast this spell for {W} if you also return a tapped creature you control to its owner's hand.)\nAs Arachne enters, look at an opponent's hand, then choose a card type other than creature.\nSpells of the chosen type cost {1} more to cast.",
    setup_interceptors=arachne_psionic_weaver_setup,
)

AUNT_MAY = make_creature(
    name="Aunt May",
    power=0, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Citizen", "Human"},
    supertypes={"Legendary"},
    text="Whenever another creature you control enters, you gain 1 life. If it's a Spider, put a +1/+1 counter on it.",
    setup_interceptors=aunt_may_setup,
)

CITY_PIGEON = make_creature(
    name="City Pigeon",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Bird"},
    text="Flying\nWhen this creature leaves the battlefield, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")",
    setup_interceptors=city_pigeon_setup,
)

COSTUME_CLOSET = make_artifact(
    name="Costume Closet",
    mana_cost="{1}{W}",
    text="This artifact enters with two +1/+1 counters on it.\n{T}: Move a +1/+1 counter from this artifact onto target creature you control. Activate only as a sorcery.\nWhenever a modified creature you control leaves the battlefield, put a +1/+1 counter on this artifact. (Equipment, Auras you control, and counters are modifications.)",
    setup_interceptors=costume_closet_setup,
)

DAILY_BUGLE_REPORTERS = make_creature(
    name="Daily Bugle Reporters",
    power=2, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Citizen", "Human"},
    text="When this creature enters, choose one —\n• Puff Piece — Put a +1/+1 counter on each of up to two target creatures.\n• Investigative Journalism — Return target creature card with mana value 2 or less from your graveyard to your hand.",
    setup_interceptors=daily_bugle_reporters_setup,
)

FLASH_THOMPSON_SPIDERFAN = make_creature(
    name="Flash Thompson, Spider-Fan",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Citizen", "Human"},
    supertypes={"Legendary"},
    text="Flash\nWhen Flash Thompson enters, choose one or both —\n• Heckle — Tap target creature.\n• Hero Worship — Untap target creature.",
    setup_interceptors=flash_thompson_spiderfan_setup,
)

FRIENDLY_NEIGHBORHOOD = make_enchantment(
    name="Friendly Neighborhood",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Enchant land\nWhen this Aura enters, create three 1/1 green and white Human Citizen creature tokens.\nEnchanted land has \"{1}, {T}: Target creature gets +1/+1 until end of turn for each creature you control. Activate only as a sorcery.\"",
    subtypes={"Aura"},
    setup_interceptors=friendly_neighborhood_setup,
)

ORIGIN_OF_SPIDERMAN = make_enchantment(
    name="Origin of Spider-Man",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Create a 2/1 green Spider creature token with reach.\nII — Put a +1/+1 counter on target creature you control. It becomes a legendary Spider Hero in addition to its other types.\nIII — Target creature you control gains double strike until end of turn.",
    subtypes={"Saga"},
    setup_interceptors=origin_of_spiderman_setup,
)

PETER_PARKER = make_creature(
    name="Peter Parker",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Hero", "Human", "Legendary", "Scientist"},
    supertypes={"Legendary"},
    text="",
)

RENT_IS_DUE = make_enchantment(
    name="Rent Is Due",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="At the beginning of your end step, you may tap two untapped creatures and/or Treasures you control. If you do, draw a card. Otherwise, sacrifice this enchantment.",
    setup_interceptors=rent_is_due_setup,
)

SELFLESS_POLICE_CAPTAIN = make_creature(
    name="Selfless Police Captain",
    power=1, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Detective", "Human"},
    text="This creature enters with a +1/+1 counter on it.\nWhen this creature leaves the battlefield, put its +1/+1 counters on target creature you control.",
    setup_interceptors=selfless_police_captain_setup,
)

SILVER_SABLE_MERCENARY_LEADER = make_creature(
    name="Silver Sable, Mercenary Leader",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Hero", "Human", "Mercenary"},
    supertypes={"Legendary"},
    text="When Silver Sable enters, put a +1/+1 counter on another target creature.\nWhenever Silver Sable attacks, target modified creature you control gains lifelink until end of turn. (Equipment, Auras you control, and counters are modifications.)",
    setup_interceptors=silver_sable_setup,
)

SPECTACULAR_SPIDERMAN = make_creature(
    name="Spectacular Spider-Man",
    power=3, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Flash\n{1}: Spectacular Spider-Man gains flying until end of turn.\n{1}, Sacrifice Spectacular Spider-Man: Creatures you control gain hexproof and indestructible until end of turn.",
)

SPECTACULAR_TACTICS = make_instant(
    name="Spectacular Tactics",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Put a +1/+1 counter on target creature you control. It gains hexproof until end of turn.\n• Destroy target creature with power 4 or greater.",
)

SPIDERMAN_WEBSLINGER = make_creature(
    name="Spider-Man, Web-Slinger",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Web-slinging {W} (You may cast this spell for {W} if you also return a tapped creature you control to its owner's hand.)",
    setup_interceptors=spiderman_webslinger_setup,
)

SPIDERUK = make_creature(
    name="Spider-UK",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Web-slinging {2}{W} (You may cast this spell for {2}{W} if you also return a tapped creature you control to its owner's hand.)\nAt the beginning of your end step, if two or more creatures entered the battlefield under your control this turn, you draw a card and gain 2 life.",
    setup_interceptors=spideruk_setup,
)

STARLING_AERIAL_ALLY = make_creature(
    name="Starling, Aerial Ally",
    power=3, toughness=4,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Hero", "Human"},
    supertypes={"Legendary"},
    text="Flying\nWhen Starling enters, another target creature you control gains flying until end of turn.",
    setup_interceptors=starling_setup,
)

SUDDEN_STRIKE = make_instant(
    name="Sudden Strike",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Destroy target attacking or blocking creature.",
)

THWIP = make_instant(
    name="Thwip!",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 and gains flying until end of turn. If it's a Spider, you gain 2 life.",
)

WEB_UP = make_enchantment(
    name="Web Up",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, exile target nonland permanent an opponent controls until this enchantment leaves the battlefield.",
    setup_interceptors=web_up_setup,
)

WEBSHOOTERS = make_artifact(
    name="Web-Shooters",
    mana_cost="{1}{W}",
    text="Equipped creature gets +1/+1 and has reach and \"Whenever this creature attacks, tap target creature an opponent controls.\"\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=webshooters_setup,
)

WILD_PACK_SQUAD = make_creature(
    name="Wild Pack Squad",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Mercenary"},
    text="At the beginning of combat on your turn, up to one target creature gains first strike and vigilance until end of turn.",
    setup_interceptors=wild_pack_squad_setup,
)

WITH_GREAT_POWER = make_enchantment(
    name="With Great Power...",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Enchant creature you control\nEnchanted creature gets +2/+2 for each Aura and Equipment attached to it.\nAll damage that would be dealt to you is dealt to enchanted creature instead.",
    subtypes={"Aura"},
    setup_interceptors=with_great_power_setup,
)

AMAZING_ACROBATICS = make_instant(
    name="Amazing Acrobatics",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Choose one or both —\n• Counter target spell.\n• Tap one or two target creatures.",
)

BEETLE_LEGACY_CRIMINAL = make_creature(
    name="Beetle, Legacy Criminal",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue", "Villain"},
    supertypes={"Legendary"},
    text="Flying\n{1}{U}, Exile this card from your graveyard: Put a +1/+1 counter on target creature. It gains flying until end of turn. Activate only as a sorcery.",
    setup_interceptors=beetle_legacy_criminal_setup,
)

CHAMELEON_MASTER_OF_DISGUISE = make_creature(
    name="Chameleon, Master of Disguise",
    power=2, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Shapeshifter", "Villain"},
    supertypes={"Legendary"},
    text="You may have Chameleon enter as a copy of a creature you control, except his name is Chameleon, Master of Disguise.\nMayhem {2}{U} (You may cast this card from your graveyard for {2}{U} if you discarded it this turn. Timing rules still apply.)",
    setup_interceptors=chameleon_master_of_disguise_setup,
)

THE_CLONE_SAGA = make_enchantment(
    name="The Clone Saga",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Surveil 3.\nII — When you next cast a creature spell this turn, copy it, except the copy isn't legendary.\nIII — Choose a card name. Whenever a creature with the chosen name deals combat damage to a player this turn, draw a card.",
    subtypes={"Saga"},
    setup_interceptors=the_clone_saga_setup,
)

DOC_OCK_SINISTER_SCIENTIST = make_creature(
    name="Doc Ock, Sinister Scientist",
    power=4, toughness=5,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scientist", "Villain"},
    supertypes={"Legendary"},
    text="As long as there are eight or more cards in your graveyard, Doc Ock has base power and toughness 8/8.\nAs long as you control another Villain, Doc Ock has hexproof. (He can't be the target of spells or abilities your opponents control.)",
    setup_interceptors=doc_ock_sinister_scientist_setup,
)

DOC_OCKS_HENCHMEN = make_creature(
    name="Doc Ock's Henchmen",
    power=2, toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Villain"},
    text="Flash\nWhenever this creature attacks, it connives. (Draw a card, then discard a card. If you discarded a nonland card, put a +1/+1 counter on this creature.)",
    setup_interceptors=doc_ocks_henchmen_setup,
)

FLYING_OCTOBOT = make_artifact_creature(
    name="Flying Octobot",
    power=1, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Robot", "Villain"},
    text="Flying\nWhenever another Villain you control enters, put a +1/+1 counter on this creature. This ability triggers only once each turn.",
    setup_interceptors=flying_octobot_setup,
)

HIDE_ON_THE_CEILING = make_instant(
    name="Hide on the Ceiling",
    mana_cost="{X}{U}",
    colors={Color.BLUE},
    text="Exile X target artifacts and/or creatures. Return the exiled cards to the battlefield under their owners' control at the beginning of the next end step.",
)

HYDROMAN_FLUID_FELON = make_creature(
    name="Hydro-Man, Fluid Felon",
    power=2, toughness=2,
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Villain"},
    supertypes={"Legendary"},
    text="Whenever you cast a blue spell, if Hydro-Man is a creature, he gets +1/+1 until end of turn.\nAt the beginning of your end step, untap Hydro-Man. Until your next turn, he becomes a land and gains \"{T}: Add {U}.\" (He's not a creature during that time.)",
    setup_interceptors=hydroman_fluid_felon_setup,
)

IMPOSTOR_SYNDROME = make_enchantment(
    name="Impostor Syndrome",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Whenever a nontoken creature you control deals combat damage to a player, create a token that's a copy of it, except it isn't legendary.",
    setup_interceptors=impostor_syndrome_setup,
)

LADY_OCTOPUS_INSPIRED_INVENTOR = make_creature(
    name="Lady Octopus, Inspired Inventor",
    power=0, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scientist", "Villain"},
    supertypes={"Legendary"},
    text="Whenever you draw your first or second card each turn, put an ingenuity counter on Lady Octopus.\n{T}: You may cast an artifact spell from your hand with mana value less than or equal to the number of ingenuity counters on Lady Octopus without paying its mana cost.",
    setup_interceptors=lady_octopus_inspired_inventor_setup,
)

MADAME_WEB_CLAIRVOYANT = make_creature(
    name="Madame Web, Clairvoyant",
    power=4, toughness=4,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Advisor", "Mutant"},
    supertypes={"Legendary"},
    text="You may look at the top card of your library any time.\nYou may cast Spider spells and noncreature spells from the top of your library.\nWhenever you attack, you may mill a card. (You may put the top card of your library into your graveyard.)",
    setup_interceptors=madame_web_clairvoyant_setup,
)

MYSTERIO_MASTER_OF_ILLUSION = make_creature(
    name="Mysterio, Master of Illusion",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="When Mysterio enters, create a 3/3 blue Illusion Villain creature token for each nontoken Villain you control. Exile those tokens when Mysterio leaves the battlefield.",
    setup_interceptors=mysterio_setup,
)

MYSTERIOS_PHANTASM = make_creature(
    name="Mysterio's Phantasm",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Illusion", "Villain"},
    text="Flying, vigilance\nWhenever this creature attacks, mill a card. (Put the top card of your library into your graveyard.)",
    setup_interceptors=mysterios_phantasm_setup,
)

NORMAN_OSBORN = make_creature(
    name="Norman Osborn",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Human", "Legendary", "Scientist", "Villain"},
    supertypes={"Legendary"},
    text="",
)

OSCORP_RESEARCH_TEAM = make_creature(
    name="Oscorp Research Team",
    power=1, toughness=5,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scientist"},
    text="{6}{U}: Draw two cards.",
    setup_interceptors=oscorp_research_team_setup,
)

ROBOTICS_MASTERY = make_enchantment(
    name="Robotics Mastery",
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    text="Flash\nEnchant creature\nWhen this Aura enters, create two 1/1 colorless Robot artifact creature tokens with flying.\nEnchanted creature gets +2/+2.",
    subtypes={"Aura"},
    setup_interceptors=robotics_mastery_setup,
)

SCHOOL_DAZE = make_instant(
    name="School Daze",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Choose one —\n• Do Homework — Draw three cards.\n• Fight Crime — Counter target spell. Draw a card.",
)

SECRET_IDENTITY = make_instant(
    name="Secret Identity",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Choose one —\n• Conceal — Until end of turn, target creature you control becomes a Citizen with base power and toughness 1/1 and gains hexproof.\n• Reveal — Until end of turn, target creature you control becomes a Hero with base power and toughness 3/4 and gains flying and vigilance.",
)

SPIDERBYTE_WEB_WARDEN = make_creature(
    name="Spider-Byte, Web Warden",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Avatar", "Hero", "Spider"},
    supertypes={"Legendary"},
    text="When Spider-Byte enters, return up to one target nonland permanent to its owner's hand.",
    setup_interceptors=spiderbyte_setup,
)

SPIDERMAN_NO_MORE = make_enchantment(
    name="Spider-Man No More",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Enchant creature\nEnchanted creature is a Citizen with base power and toughness 1/1. It has defender and loses all other abilities. (It also loses all other creature types.)",
    subtypes={"Aura"},
    setup_interceptors=spiderman_no_more_setup,
)

SPIDERSENSE = make_instant(
    name="Spider-Sense",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Web-slinging {U} (You may cast this spell for {U} if you also return a tapped creature you control to its owner's hand.)\nCounter target instant spell, sorcery spell, or triggered ability.",
    setup_interceptors=make_web_slinging_setup("{U}"),
)

UNSTABLE_EXPERIMENT = make_instant(
    name="Unstable Experiment",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Target player draws a card, then up to one target creature you control connives. (Draw a card, then discard a card. If you discarded a nonland card, put a +1/+1 counter on that creature.)",
)

WHOOSH = make_instant(
    name="Whoosh!",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Kicker {1}{U} (You may pay an additional {1}{U} as you cast this spell.)\nReturn target nonland permanent to its owner's hand. If this spell was kicked, draw a card.",
)

AGENT_VENOM = make_creature(
    name="Agent Venom",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Hero", "Soldier", "Symbiote"},
    supertypes={"Legendary"},
    text="Flash\nMenace\nWhenever another nontoken creature you control dies, you draw a card and lose 1 life.",
    setup_interceptors=agent_venom_setup,
)

ALIEN_SYMBIOSIS = make_enchantment(
    name="Alien Symbiosis",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Enchant creature\nEnchanted creature gets +1/+1, has menace, and is a Symbiote in addition to its other types.\nYou may cast this card from your graveyard by discarding a card in addition to paying its other costs.",
    subtypes={"Aura"},
    setup_interceptors=alien_symbiosis_setup,
)

BEHOLD_THE_SINISTER_SIX = make_sorcery(
    name="Behold the Sinister Six!",
    mana_cost="{6}{B}",
    colors={Color.BLACK},
    text="Return up to six target creature cards with different names from your graveyard to the battlefield.",
)

BLACK_CAT_CUNNING_THIEF = make_creature(
    name="Black Cat, Cunning Thief",
    power=2, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue", "Villain"},
    supertypes={"Legendary"},
    text="When Black Cat enters, look at the top nine cards of target opponent's library, exile two of them face down, then put the rest on the bottom of their library in a random order. You may play the exiled cards for as long as they remain exiled. Mana of any type can be spent to cast spells this way.",
    setup_interceptors=black_cat_setup,
)

COMMON_CROOK = make_creature(
    name="Common Crook",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue", "Villain"},
    text="When this creature dies, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
    setup_interceptors=common_crook_setup,
)

THE_DEATH_OF_GWEN_STACY = make_enchantment(
    name="The Death of Gwen Stacy",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Destroy target creature.\nII — Each player may discard a card. Each player who doesn't loses 3 life.\nIII — Exile any number of target players' graveyards.",
    subtypes={"Saga"},
    setup_interceptors=the_death_of_gwen_stacy_setup,
)

EDDIE_BROCK = make_creature(
    name="Eddie Brock",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Hero", "Human", "Legendary", "Villain"},
    supertypes={"Legendary"},
    text="",
)

GWENOM_REMORSELESS = make_creature(
    name="Gwenom, Remorseless",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Hero", "Spider", "Symbiote"},
    supertypes={"Legendary"},
    text="Deathtouch, lifelink\nWhenever Gwenom attacks, until end of turn, you may look at the top card of your library any time and you may play cards from the top of your library. If you cast a spell this way, pay life equal to its mana value rather than pay its mana cost.",
    setup_interceptors=gwenom_setup,
)

INNER_DEMONS_GANGSTERS = make_creature(
    name="Inner Demons Gangsters",
    power=3, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue", "Villain"},
    text="Discard a card: This creature gets +1/+0 and gains menace until end of turn. Activate only as a sorcery. (It can't be blocked except by two or more creatures.)",
    setup_interceptors=inner_demons_gangsters_setup,
)

MERCILESS_ENFORCERS = make_creature(
    name="Merciless Enforcers",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Mercenary", "Villain"},
    text="Lifelink\n{3}{B}: This creature deals 1 damage to each opponent.",
    setup_interceptors=merciless_enforcers_setup,
)

MORLUN_DEVOURER_OF_SPIDERS = make_creature(
    name="Morlun, Devourer of Spiders",
    power=2, toughness=1,
    mana_cost="{X}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Villain"},
    supertypes={"Legendary"},
    text="Lifelink\nMorlun enters with X +1/+1 counters on him.\nWhen Morlun enters, he deals X damage to target opponent.",
    setup_interceptors=morlun_setup,
)

PARKER_LUCK = make_enchantment(
    name="Parker Luck",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="At the beginning of your end step, two target players each reveal the top card of their library. They each lose life equal to the mana value of the card revealed by the other player. Then they each put the card they revealed into their hand.",
    setup_interceptors=parker_luck_setup,
)

PRISON_BREAK = make_sorcery(
    name="Prison Break",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield with an additional +1/+1 counter on it.\nMayhem {3}{B} (You may cast this card from your graveyard for {3}{B} if you discarded it this turn. Timing rules still apply.)",
    setup_interceptors=make_mayhem_setup("{3}{B}"),
)

RISKY_RESEARCH = make_sorcery(
    name="Risky Research",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Surveil 2, then draw two cards. You lose 2 life. (To surveil 2, look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
)

SANDMANS_QUICKSAND = make_sorcery(
    name="Sandman's Quicksand",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Mayhem {3}{B} (You may cast this card from your graveyard for {3}{B} if you discarded it this turn. Timing rules still apply.)\nAll creatures get -2/-2 until end of turn. If this spell's mayhem cost was paid, creatures your opponents control get -2/-2 until end of turn instead.",
    setup_interceptors=make_mayhem_setup("{3}{B}"),
)

SCORPION_SEETHING_STRIKER = make_creature(
    name="Scorpion, Seething Striker",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Scorpion", "Villain"},
    supertypes={"Legendary"},
    text="Deathtouch\nAt the beginning of your end step, if a creature died this turn, target creature you control connives. (Draw a card, then discard a card. If you discarded a nonland card, put a +1/+1 counter on that creature.)",
    setup_interceptors=scorpion_setup,
)

SCORPIONS_STING = make_instant(
    name="Scorpion's Sting",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -3/-3 until end of turn.",
)

THE_SOUL_STONE = make_artifact(
    name="The Soul Stone",
    mana_cost="{1}{B}",
    text="Indestructible\n{T}: Add {B}.\n{6}{B}, {T}, Exile a creature you control: Harness The Soul Stone. (Once harnessed, its ∞ ability is active.)\n∞ — At the beginning of your upkeep, return target creature card from your graveyard to the battlefield.",
    subtypes={"Infinity", "Stone"},
    supertypes={"Legendary"},
    setup_interceptors=the_soul_stone_setup,
)

SPIDERMAN_NOIR = make_creature(
    name="Spider-Man Noir",
    power=4, toughness=4,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Menace\nWhenever a creature you control attacks alone, put a +1/+1 counter on it. Then surveil X, where X is the number of counters on it. (Look at the top X cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
    setup_interceptors=spiderman_noir_setup,
)

THE_SPOTS_PORTAL = make_instant(
    name="The Spot's Portal",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Put target creature on the bottom of its owner's library. You lose 2 life unless you control a Villain.",
)

SWARM_BEING_OF_BEES = make_creature(
    name="Swarm, Being of Bees",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Insect", "Villain"},
    supertypes={"Legendary"},
    text="Flash\nFlying\nMayhem {B} (You may cast this card from your graveyard for {B} if you discarded it this turn. Timing rules still apply.)",
    setup_interceptors=swarm_being_of_bees_setup,
)

TOMBSTONE_CAREER_CRIMINAL = make_creature(
    name="Tombstone, Career Criminal",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="When Tombstone enters, return target Villain card from your graveyard to your hand.\nVillain spells you cast cost {1} less to cast.",
    setup_interceptors=tombstone_setup,
)

VENOM_EVIL_UNLEASHED = make_creature(
    name="Venom, Evil Unleashed",
    power=4, toughness=5,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Symbiote", "Villain"},
    supertypes={"Legendary"},
    text="Deathtouch\n{2}{B}, Exile this card from your graveyard: Put two +1/+1 counters on target creature. It gains deathtouch until end of turn. Activate only as a sorcery.",
    setup_interceptors=venom_evil_unleashed_setup,
)

VENOMIZED_CAT = make_creature(
    name="Venomized Cat",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Cat", "Symbiote", "Villain"},
    text="Deathtouch\nWhen this creature enters, mill two cards. (Put the top two cards of your library into your graveyard.)",
    setup_interceptors=venomized_cat_setup,
)

VENOMS_HUNGER = make_sorcery(
    name="Venom's Hunger",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="This spell costs {2} less to cast if you control a Villain.\nDestroy target creature. You gain 2 life.",
)

VILLAINOUS_WRATH = make_sorcery(
    name="Villainous Wrath",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Target opponent loses life equal to the number of creatures they control. Then destroy all creatures.",
    resolve=villainous_wrath_resolve,
)

ANGRY_RABBLE = make_creature(
    name="Angry Rabble",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Citizen", "Human"},
    text="Trample\nWhenever you cast a spell with mana value 4 or greater, this creature deals 1 damage to each opponent.\n{5}{R}: Put two +1/+1 counters on this creature. Activate only as a sorcery.",
    setup_interceptors=angry_rabble_setup,
)

ELECTRO_ASSAULTING_BATTERY = make_creature(
    name="Electro, Assaulting Battery",
    power=2, toughness=3,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Flying\nYou don't lose unspent red mana as steps and phases end.\nWhenever you cast an instant or sorcery spell, add {R}.\nWhen Electro leaves the battlefield, you may pay {X}. When you do, he deals X damage to target player.",
    setup_interceptors=electro_assaulting_battery_setup,
)

ELECTROS_BOLT = make_sorcery(
    name="Electro's Bolt",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Electro's Bolt deals 4 damage to target creature.\nMayhem {1}{R} (You may cast this card from your graveyard for {1}{R} if you discarded it this turn. Timing rules still apply.)",
    setup_interceptors=make_mayhem_setup("{1}{R}"),
)

GWEN_STACY = make_creature(
    name="Gwen Stacy",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Hero", "Human", "Legendary", "Performer"},
    supertypes={"Legendary"},
    text="",
)

HEROES_HANGOUT = make_sorcery(
    name="Heroes' Hangout",
    mana_cost="{R}",
    colors={Color.RED},
    text="Choose one —\n• Date Night — Exile the top two cards of your library. Choose one of them. Until the end of your next turn, you may play that card.\n• Patrol Night — One or two target creatures each get +1/+0 and gain first strike until end of turn.",
)

HOBGOBLIN_MANTLED_MARAUDER = make_creature(
    name="Hobgoblin, Mantled Marauder",
    power=1, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Human", "Villain"},
    supertypes={"Legendary"},
    text="Flying, haste\nWhenever you discard a card, Hobgoblin gets +2/+0 until end of turn.",
    setup_interceptors=hobgoblin_setup,
)

J_JONAH_JAMESON = make_creature(
    name="J. Jonah Jameson",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Citizen", "Human"},
    supertypes={"Legendary"},
    text="When J. Jonah Jameson enters, suspect up to one target creature. (A suspected creature has menace and can't block.)\nWhenever a creature you control with menace attacks, create a Treasure token.",
    setup_interceptors=j_jonah_jameson_setup,
)

MASKED_MEOWER = make_creature(
    name="Masked Meower",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Cat", "Hero", "Spider"},
    text="Haste\nDiscard a card, Sacrifice this creature: Draw a card.",
    setup_interceptors=masked_meower_setup,
)

MAXIMUM_CARNAGE = make_enchantment(
    name="Maximum Carnage",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Until your next turn, each creature attacks each combat if able and attacks a player other than you if able.\nII — Add {R}{R}{R}.\nIII — This Saga deals 5 damage to each opponent.",
    subtypes={"Saga"},
    setup_interceptors=maximum_carnage_setup,
)

MOLTEN_MAN_INFERNO_INCARNATE = make_creature(
    name="Molten Man, Inferno Incarnate",
    power=0, toughness=0,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Villain"},
    supertypes={"Legendary"},
    text="When Molten Man enters, search your library for a basic Mountain card, put it onto the battlefield tapped, then shuffle.\nMolten Man gets +1/+1 for each Mountain you control.\nWhen Molten Man leaves the battlefield, sacrifice a land.",
    setup_interceptors=molten_man_setup,
)

RAGING_GOBLINOIDS = make_creature(
    name="Raging Goblinoids",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Berserker", "Goblin", "Villain"},
    text="Haste\nMayhem {2}{R} (You may cast this card from your graveyard for {2}{R} if you discarded it this turn. Timing rules still apply.)",
    setup_interceptors=raging_goblinoids_setup,
)

ROMANTIC_RENDEZVOUS = make_sorcery(
    name="Romantic Rendezvous",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Discard a card, then draw two cards.",
)

SHADOW_OF_THE_GOBLIN = make_enchantment(
    name="Shadow of the Goblin",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Unreliable Visions — At the beginning of your first main phase, discard a card. If you do, draw a card.\nUndying Vengeance — Whenever you play a land or cast a spell from anywhere other than your hand, this enchantment deals 1 damage to each opponent.",
    setup_interceptors=shadow_of_the_goblin_setup,
)

SHOCK = make_instant(
    name="Shock",
    mana_cost="{R}",
    colors={Color.RED},
    text="Shock deals 2 damage to any target.",
)

SHOCKER_UNSHAKABLE = make_creature(
    name="Shocker, Unshakable",
    power=5, toughness=5,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rogue", "Villain"},
    supertypes={"Legendary"},
    text="During your turn, Shocker has first strike.\nVibro-Shock Gauntlets — When Shocker enters, he deals 2 damage to target creature and 2 damage to that creature's controller.",
    setup_interceptors=shocker_setup,
)

SPIDERGWEN_FREE_SPIRIT = make_creature(
    name="Spider-Gwen, Free Spirit",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Reach\nWhenever Spider-Gwen becomes tapped, you may discard a card. If you do, draw a card.",
    setup_interceptors=spidergwen_free_spirit_setup,
)

SPIDERISLANDERS = make_creature(
    name="Spider-Islanders",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Citizen", "Horror", "Spider"},
    text="Mayhem {1}{R} (You may cast this card from your graveyard for {1}{R} if you discarded it this turn. Timing rules still apply.)",
    setup_interceptors=spiderislanders_setup,
)

SPIDERPUNK = make_creature(
    name="Spider-Punk",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Riot (This creature enters with your choice of a +1/+1 counter or haste.)\nOther Spiders you control have riot.\nSpells and abilities can't be countered.\nDamage can't be prevented.",
    setup_interceptors=spider_punk_setup,
)

SPIDERVERSE = make_enchantment(
    name="Spider-Verse",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="The \"legend rule\" doesn't apply to Spiders you control.\nWhenever you cast a spell from anywhere other than your hand, you may copy it. If you do, you may choose new targets for the copy. If the copy is a permanent spell, it gains haste. Do this only once each turn.",
    setup_interceptors=spiderverse_setup,
)

SPINNERET_AND_SPIDERLING = make_creature(
    name="Spinneret and Spiderling",
    power=1, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Whenever you attack with two or more Spiders, put a +1/+1 counter on Spinneret and Spiderling.\nWhenever Spinneret and Spiderling deals 4 or more damage, exile the top card of your library. Until the end of your next turn, you may play that card.",
    setup_interceptors=spinneret_and_spiderling_setup,
)

STEGRON_THE_DINOSAUR_MAN = make_creature(
    name="Stegron the Dinosaur Man",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur", "Villain"},
    supertypes={"Legendary"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nDinosaur Formula — {1}{R}, Discard this card: Until end of turn, target creature you control gets +3/+1 and becomes a Dinosaur in addition to its other types.",
    setup_interceptors=stegron_the_dinosaur_man_setup,
)

SUPERIOR_FOES_OF_SPIDERMAN = make_creature(
    name="Superior Foes of Spider-Man",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rogue", "Villain"},
    text="Trample\nWhenever you cast a spell with mana value 4 or greater, you may exile the top card of your library. If you do, you may play that card until you exile another card with this creature.",
    setup_interceptors=superior_foes_of_spiderman_setup,
)

TAXI_DRIVER = make_creature(
    name="Taxi Driver",
    power=3, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Pilot"},
    text="{1}, {T}: Target creature gains haste until end of turn.",
    setup_interceptors=taxi_driver_setup,
)

WISECRACK = make_instant(
    name="Wisecrack",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Target creature deals damage equal to its power to itself. If that creature is attacking, Wisecrack deals 2 damage to that creature's controller.",
)

DAMAGE_CONTROL_CREW = make_creature(
    name="Damage Control Crew",
    power=3, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Citizen", "Human"},
    text="When this creature enters, choose one —\n• Repair — Return target card with mana value 4 or greater from your graveyard to your hand.\n• Impound — Exile target artifact or enchantment.",
    setup_interceptors=damage_control_crew_setup,
)

EZEKIEL_SIMS_SPIDERTOTEM = make_creature(
    name="Ezekiel Sims, Spider-Totem",
    power=3, toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Advisor", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Reach\nAt the beginning of combat on your turn, target Spider you control gets +2/+2 until end of turn.",
    setup_interceptors=ezekiel_sims_setup,
)

GROW_EXTRA_ARMS = make_instant(
    name="Grow Extra Arms",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="This spell costs {1} less to cast if it targets a Spider.\nTarget creature gets +4/+4 until end of turn.",
)

GUY_IN_THE_CHAIR = make_creature(
    name="Guy in the Chair",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Advisor", "Human"},
    text="{T}: Add one mana of any color.\nWeb Support — {2}{G}, {T}: Put a +1/+1 counter on target Spider. Activate only as a sorcery.",
    setup_interceptors=guy_in_the_chair_setup,
)

KAPOW = make_sorcery(
    name="Kapow!",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Put a +1/+1 counter on target creature you control. It fights target creature an opponent controls. (Each deals damage equal to its power to the other.)",
)

KRAVENS_CATS = make_creature(
    name="Kraven's Cats",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Cat", "Villain"},
    text="{2}{G}: This creature gets +2/+2 until end of turn. Activate only once each turn.",
    setup_interceptors=kravens_cats_setup,
)

KRAVENS_LAST_HUNT = make_enchantment(
    name="Kraven's Last Hunt",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Mill five cards. When you do, this Saga deals damage equal to the greatest power among creature cards in your graveyard to target creature.\nII — Target creature you control gets +2/+2 until end of turn.\nIII — Return target creature card from your graveyard to your hand.",
    subtypes={"Saga"},
    setup_interceptors=kravens_last_hunt_setup,
)

LIZARD_CONNORSS_CURSE = make_creature(
    name="Lizard, Connors's Curse",
    power=5, toughness=5,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Lizard", "Villain"},
    supertypes={"Legendary"},
    text="Trample\nLizard Formula — When Lizard, Connors's Curse enters, up to one other target creature loses all abilities and becomes a green Lizard creature with base power and toughness 4/4.",
    setup_interceptors=lizard_connors_curse_setup,
)

LURKING_LIZARDS = make_creature(
    name="Lurking Lizards",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Lizard", "Villain"},
    text="Trample\nWhenever you cast a spell with mana value 4 or greater, put a +1/+1 counter on this creature.",
    setup_interceptors=lurking_lizards_setup,
)

MILES_MORALES = make_creature(
    name="Miles Morales",
    power=1, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Citizen", "Hero", "Human"},
    supertypes={"Legendary"},
    text="When Miles Morales enters, put a +1/+1 counter on each of up to two target creatures.\n{3}{R}{G}{W}: Transform Miles Morales. Activate only as a sorcery.\n// Transforms into: Ultimate Spider-Man (4/3)\nFirst strike, haste\nCamouflage — {2}: Put a +1/+1 counter on Ultimate Spider-Man. He gains hexproof and becomes colorless until end of turn.\nWhenever you attack, double the number of each kind of counter on each Spider and legendary creature you control.",
    setup_interceptors=miles_morales_setup,
)

PICTURES_OF_SPIDERMAN = make_artifact(
    name="Pictures of Spider-Man",
    mana_cost="{2}{G}",
    text="When this artifact enters, look at the top five cards of your library. You may reveal up to two creature cards from among them and put them into your hand. Put the rest on the bottom of your library in a random order.\n{1}, {T}, Sacrifice this artifact: Create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
    setup_interceptors=pictures_of_spiderman_setup,
)

PROFESSIONAL_WRESTLER = make_creature(
    name="Professional Wrestler",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Performer", "Warrior"},
    text="When this creature enters, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nThis creature can't be blocked by more than one creature.",
    setup_interceptors=professional_wrestler_setup,
)

RADIOACTIVE_SPIDER = make_creature(
    name="Radioactive Spider",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Spider"},
    text="Reach, deathtouch\nFateful Bite — {2}, Sacrifice this creature: Search your library for a Spider Hero card, reveal it, put it into your hand, then shuffle. Activate only as a sorcery.",
    setup_interceptors=radioactive_spider_setup,
)

SANDMAN_SHIFTING_SCOUNDREL = make_creature(
    name="Sandman, Shifting Scoundrel",
    power=0, toughness=0,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental", "Sand", "Villain"},
    supertypes={"Legendary"},
    text="Sandman's power and toughness are each equal to the number of lands you control.\nSandman can't be blocked by creatures with power 2 or less.\n{3}{G}{G}: Return this card and target land card from your graveyard to the battlefield tapped.",
    setup_interceptors=sandman_shifting_scoundrel_setup,
)

SCOUT_THE_CITY = make_sorcery(
    name="Scout the City",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Look Around — Mill three cards. You may put a permanent card from among them into your hand. You gain 3 life. (To mill three cards, put the top three cards of your library into your graveyard.)\n• Bring Down — Destroy target creature with flying.",
)

SPIDERHAM_PETER_PORKER = make_creature(
    name="Spider-Ham, Peter Porker",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Boar", "Hero", "Spider"},
    supertypes={"Legendary"},
    text="When Spider-Ham enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\nAnimal May-Ham — Other Spiders, Boars, Bats, Bears, Birds, Cats, Dogs, Frogs, Jackals, Lizards, Mice, Otters, Rabbits, Raccoons, Rats, Squirrels, Turtles, and Wolves you control get +1/+1.",
    setup_interceptors=spider_ham_setup,
)

SPIDERMAN_BROOKLYN_VISIONARY = make_creature(
    name="Spider-Man, Brooklyn Visionary",
    power=4, toughness=3,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Web-slinging {2}{G} (You may cast this spell for {2}{G} if you also return a tapped creature you control to its owner's hand.)\nWhen Spider-Man enters, search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
    setup_interceptors=spiderman_brooklyn_visionary_setup,
)

SPIDERREX_DARING_DINO = make_creature(
    name="Spider-Rex, Daring Dino",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur", "Hero", "Spider"},
    supertypes={"Legendary"},
    text="Reach, trample\nWard {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)",
)

SPIDERSMAN_HEROIC_HORDE = make_creature(
    name="Spiders-Man, Heroic Horde",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Hero", "Spider"},
    supertypes={"Legendary"},
    text="Web-slinging {4}{G}{G} (You may cast this spell for {4}{G}{G} if you also return a tapped creature you control to its owner's hand.)\nWhen Spiders-Man enters, if they were cast using web-slinging, you gain 3 life and create two 2/1 green Spider creature tokens with reach.",
    setup_interceptors=spidersman_heroic_horde_setup,
)

STRENGTH_OF_WILL = make_instant(
    name="Strength of Will",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Until end of turn, target creature you control gains indestructible and \"Whenever this creature is dealt damage, put that many +1/+1 counters on it.\"",
)

SUPPORTIVE_PARENTS = make_creature(
    name="Supportive Parents",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Citizen", "Human"},
    text="Tap two untapped creatures you control: Add one mana of any color.",
    setup_interceptors=supportive_parents_setup,
)

TERRIFIC_TEAMUP = make_instant(
    name="Terrific Team-Up",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="This spell costs {2} less to cast if you control a permanent with mana value 4 or greater.\nOne or two target creatures you control each get +1/+0 until end of turn. They each deal damage equal to their power to target creature an opponent controls.",
)

WALL_CRAWL = make_enchantment(
    name="Wall Crawl",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, create a 2/1 green Spider creature token with reach, then you gain 1 life for each Spider you control.\nSpiders you control get +1/+1 and can't be blocked by creatures with defender.",
    setup_interceptors=wall_crawl_setup,
)

WEB_OF_LIFE_AND_DESTINY = make_enchantment(
    name="Web of Life and Destiny",
    mana_cost="{6}{G}{G}",
    colors={Color.GREEN},
    text="Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.)\nAt the beginning of combat on your turn, look at the top five cards of your library. You may put a creature card from among them onto the battlefield. Put the rest on the bottom of your library in a random order.",
    setup_interceptors=web_of_life_and_destiny_setup,
)

ARAA_HEART_OF_THE_SPIDER = make_creature(
    name="Araña, Heart of the Spider",
    power=3, toughness=3,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Whenever you attack, put a +1/+1 counter on target attacking creature.\nWhenever a modified creature you control deals combat damage to a player, exile the top card of your library. You may play that card this turn. (Equipment, Auras you control, and counters are modifications.)",
    setup_interceptors=arana_setup,
)

BIORGANIC_CARAPACE = make_artifact(
    name="Biorganic Carapace",
    mana_cost="{2}{W}{U}",
    text="When this Equipment enters, attach it to target creature you control.\nEquipped creature gets +2/+2 and has \"Whenever this creature deals combat damage to a player, draw a card for each modified creature you control.\" (Equipment, Auras you control, and counters are modifications.)\nEquip {2}",
    subtypes={"Equipment"},
    setup_interceptors=biorganic_carapace_setup,
)

CARNAGE_CRIMSON_CHAOS = make_creature(
    name="Carnage, Crimson Chaos",
    power=4, toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Symbiote", "Villain"},
    supertypes={"Legendary"},
    text="Trample\nWhen Carnage enters, return target creature card with mana value 3 or less from your graveyard to the battlefield. It gains \"This creature attacks each combat if able\" and \"When this creature deals combat damage to a player, sacrifice it.\"\nMayhem {B}{R}",
    setup_interceptors=carnage_setup,
)

CHEERING_CROWD = make_creature(
    name="Cheering Crowd",
    power=2, toughness=2,
    mana_cost="{1}{R/G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Citizen", "Human"},
    text="At the beginning of each player's first main phase, that player may put a +1/+1 counter on this creature. If they do, they add {C} for each counter on it.",
    setup_interceptors=cheering_crowd_setup,
)

COSMIC_SPIDERMAN = make_creature(
    name="Cosmic Spider-Man",
    power=5, toughness=5,
    mana_cost="{W}{U}{B}{R}{G}",
    colors={Color.BLACK, Color.GREEN, Color.RED, Color.BLUE, Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Flying, first strike, trample, lifelink, haste\nAt the beginning of combat on your turn, other Spiders you control gain flying, first strike, trample, lifelink, and haste until end of turn.",
    setup_interceptors=cosmic_spiderman_setup,
)

DOCTOR_OCTOPUS_MASTER_PLANNER = make_creature(
    name="Doctor Octopus, Master Planner",
    power=4, toughness=8,
    mana_cost="{5}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Scientist", "Villain"},
    supertypes={"Legendary"},
    text="Other Villains you control get +2/+2.\nYour maximum hand size is eight.\nAt the beginning of your end step, if you have fewer than eight cards in hand, draw cards equal to the difference.",
    setup_interceptors=doctor_octopus_setup,
)

GALLANT_CITIZEN = make_creature(
    name="Gallant Citizen",
    power=1, toughness=1,
    mana_cost="{G/W}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Citizen", "Human"},
    text="When this creature enters, draw a card.",
    setup_interceptors=gallant_citizen_setup,
)

GREEN_GOBLIN_REVENANT = make_creature(
    name="Green Goblin, Revenant",
    power=3, toughness=3,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Goblin", "Human", "Villain"},
    supertypes={"Legendary"},
    text="Flying, deathtouch\nWhenever Green Goblin attacks, discard a card. Then draw a card for each card you've discarded this turn.",
    setup_interceptors=green_goblin_revenant_setup,
)

JACKAL_GENIUS_GENETICIST = make_creature(
    name="Jackal, Genius Geneticist",
    power=1, toughness=1,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Scientist", "Villain"},
    supertypes={"Legendary"},
    text="Trample\nWhenever you cast a creature spell with mana value equal to Jackal's power, copy that spell, except the copy isn't legendary. Then put a +1/+1 counter on Jackal. (The copy becomes a token.)",
    setup_interceptors=jackal_genius_geneticist_setup,
)

KRAVEN_PROUD_PREDATOR = make_creature(
    name="Kraven, Proud Predator",
    power=0, toughness=4,
    mana_cost="{1}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Villain", "Warrior"},
    supertypes={"Legendary"},
    text="Vigilance\nTop of the Food Chain — Kraven's power is equal to the greatest mana value among permanents you control.",
    setup_interceptors=kraven_proud_predator_setup,
)

KRAVEN_THE_HUNTER = make_creature(
    name="Kraven the Hunter",
    power=4, toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Villain", "Warrior"},
    supertypes={"Legendary"},
    text="Trample\nWhenever a creature an opponent controls with the greatest power among creatures that player controls dies, draw a card and put a +1/+1 counter on Kraven the Hunter.",
    setup_interceptors=kraven_the_hunter_setup,
)

MARY_JANE_WATSON = make_creature(
    name="Mary Jane Watson",
    power=2, toughness=2,
    mana_cost="{1}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Performer"},
    supertypes={"Legendary"},
    text="Whenever a Spider you control enters, draw a card. This ability triggers only once each turn.",
    setup_interceptors=mary_jane_watson_setup,
)

MISTER_NEGATIVE = make_creature(
    name="Mister Negative",
    power=5, toughness=5,
    mana_cost="{5}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Vigilance, lifelink\nDarkforce Inversion — When Mister Negative enters, you may exchange life totals with target opponent. If you lost life this way, draw that many cards.",
    setup_interceptors=mister_negative_setup,
)

MOB_LOOKOUT = make_creature(
    name="Mob Lookout",
    power=0, toughness=3,
    mana_cost="{1}{U/B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Rogue", "Villain"},
    text="When this creature enters, target creature you control connives. (Draw a card, then discard a card. If you discarded a nonland card, put a +1/+1 counter on that creature.)",
    setup_interceptors=mob_lookout_setup,
)

MORBIUS_THE_LIVING_VAMPIRE = make_creature(
    name="Morbius the Living Vampire",
    power=3, toughness=1,
    mana_cost="{2}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Scientist", "Vampire", "Villain"},
    supertypes={"Legendary"},
    text="Flying, vigilance, lifelink\n{U}{B}, Exile this card from your graveyard: Look at the top three cards of your library. Put one of them into your hand and the rest on the bottom of your library in any order.",
    setup_interceptors=morbius_the_living_vampire_setup,
)

PROWLER_CLAWED_THIEF = make_creature(
    name="Prowler, Clawed Thief",
    power=2, toughness=3,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Rogue", "Villain"},
    supertypes={"Legendary"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhenever another Villain you control enters, Prowler connives. (Draw a card, then discard a card. If you discarded a nonland card, put a +1/+1 counter on this creature.)",
    setup_interceptors=prowler_setup,
)

PUMPKIN_BOMBARDMENT = make_sorcery(
    name="Pumpkin Bombardment",
    mana_cost="{B/R}",
    colors={Color.BLACK, Color.RED},
    text="As an additional cost to cast this spell, discard a card or pay {2}.\nPumpkin Bombardment deals 3 damage to target creature.",
)

RHINO_BARRELING_BRUTE = make_creature(
    name="Rhino, Barreling Brute",
    power=6, toughness=7,
    mana_cost="{3}{R}{R}{G}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Vigilance, trample, haste\nWhenever Rhino attacks, if you've cast a spell with mana value 4 or greater this turn, draw a card.",
    setup_interceptors=rhino_setup,
)

RHINOS_RAMPAGE = make_sorcery(
    name="Rhino's Rampage",
    mana_cost="{R/G}",
    colors={Color.GREEN, Color.RED},
    text="Target creature you control gets +1/+0 until end of turn. It fights target creature an opponent controls. When excess damage is dealt to the creature an opponent controls this way, destroy up to one target noncreature artifact with mana value 3 or less.",
)

SCARLET_SPIDER_BEN_REILLY = make_creature(
    name="Scarlet Spider, Ben Reilly",
    power=4, toughness=3,
    mana_cost="{1}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Web-slinging {R}{G} (You may cast this spell for {R}{G} if you also return a tapped creature you control to its owner's hand.)\nTrample\nSensational Save — If Scarlet Spider was cast using web-slinging, he enters with X +1/+1 counters on him, where X is the mana value of the returned creature.",
    setup_interceptors=scarlet_spider_ben_reilly_setup,
)

SCARLET_SPIDER_KAINE = make_creature(
    name="Scarlet Spider, Kaine",
    power=2, toughness=1,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhen Scarlet Spider enters, you may discard a card. If you do, put a +1/+1 counter on him.\nMayhem {B/R} (You may cast this card from your graveyard for {B/R} if you discarded it this turn. Timing rules still apply.)",
    setup_interceptors=scarlet_spider_kaine_setup,
)

SHRIEK_TREBLEMAKER = make_creature(
    name="Shriek, Treblemaker",
    power=2, toughness=3,
    mana_cost="{2}{B/R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Mutant", "Villain"},
    supertypes={"Legendary"},
    text="At the beginning of your first main phase, you may discard a card. When you do, target creature can't block this turn.\nSonic Blast — Whenever a creature an opponent controls dies, Shriek deals 1 damage to that player.",
    setup_interceptors=shriek_setup,
)

SILK_WEB_WEAVER = make_creature(
    name="Silk, Web Weaver",
    power=3, toughness=5,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Web-slinging {1}{G}{W} (You may cast this spell for {1}{G}{W} if you also return a tapped creature you control to its owner's hand.)\nWhenever you cast a creature spell, create a 1/1 green and white Human Citizen creature token.\n{3}{G}{W}: Creatures you control get +2/+2 and gain vigilance until end of turn.",
    setup_interceptors=silk_setup,
)

SKYWARD_SPIDER = make_creature(
    name="Skyward Spider",
    power=2, toughness=2,
    mana_cost="{W/U}{W/U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    text="Ward {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nThis creature has flying as long as it's modified. (Equipment, Auras you control, and counters are modifications.)",
    setup_interceptors=skyward_spider_setup,
)

SPDR_PILOTED_BY_PENI = make_artifact_creature(
    name="SP//dr, Piloted by Peni",
    power=4, toughness=4,
    mana_cost="{3}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Hero", "Spider"},
    supertypes={"Legendary"},
    text="Vigilance\nWhen SP//dr enters, put a +1/+1 counter on target creature.\nWhenever a modified creature you control deals combat damage to a player, draw a card. (Equipment, Auras you control, and counters are modifications.)",
    setup_interceptors=spdr_setup,
)

SPIDER_MANIFESTATION = make_creature(
    name="Spider Manifestation",
    power=2, toughness=2,
    mana_cost="{1}{R/G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Avatar", "Spider"},
    text="Reach\n{T}: Add {R} or {G}.\nWhenever you cast a spell with mana value 4 or greater, untap this creature.",
    setup_interceptors=spider_manifestation_setup,
)

SPIDERGIRL_LEGACY_HERO = make_creature(
    name="Spider-Girl, Legacy Hero",
    power=2, toughness=2,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="During your turn, Spider-Girl has flying.\nWhen Spider-Girl leaves the battlefield, create a 1/1 green and white Human Citizen creature token.",
    setup_interceptors=spider_girl_setup,
)

SPIDERMAN_2099 = make_creature(
    name="Spider-Man 2099",
    power=2, toughness=3,
    mana_cost="{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="From the Future — You can't cast Spider-Man 2099 during your first, second, or third turns of the game.\nDouble strike, vigilance\nAt the beginning of your end step, if you've played a land or cast a spell this turn from anywhere other than your hand, Spider-Man 2099 deals damage equal to his power to any target.",
    setup_interceptors=spiderman_2099_setup,
)

SPIDERMAN_INDIA = make_creature(
    name="Spider-Man India",
    power=4, toughness=4,
    mana_cost="{3}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Web-slinging {1}{G}{W} (You may cast this spell for {1}{G}{W} if you also return a tapped creature you control to its owner's hand.)\nPavitr's Sevā — Whenever you cast a creature spell, put a +1/+1 counter on target creature you control. It gains flying until end of turn.",
    setup_interceptors=spiderman_india_setup,
)

SPIDERWOMAN_STUNNING_SAVIOR = make_creature(
    name="Spider-Woman, Stunning Savior",
    power=2, toughness=2,
    mana_cost="{1}{W/U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Flying\nVenom Blast — Artifacts and creatures your opponents control enter tapped.",
    setup_interceptors=spiderwoman_setup,
)

THE_SPOT_LIVING_PORTAL = make_creature(
    name="The Spot, Living Portal",
    power=4, toughness=4,
    mana_cost="{3}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Scientist", "Villain"},
    supertypes={"Legendary"},
    text="When The Spot enters, exile up to one target nonland permanent and up to one target nonland permanent card from a graveyard.\nWhen The Spot dies, put him on the bottom of his owner's library. If you do, return the exiled cards to their owners' hands.",
    setup_interceptors=the_spot_setup,
)

SUNSPIDER_NIMBLE_WEBBER = make_creature(
    name="Sun-Spider, Nimble Webber",
    power=3, toughness=2,
    mana_cost="{3}{W/U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="During your turn, Sun-Spider has flying.\nWhen Sun-Spider enters, search your library for an Aura or Equipment card, reveal it, put it into your hand, then shuffle.",
    setup_interceptors=sun_spider_setup,
)

SUPERIOR_SPIDERMAN = make_creature(
    name="Superior Spider-Man",
    power=4, toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Hero", "Human", "Spider"},
    supertypes={"Legendary"},
    text="Mind Swap — You may have Superior Spider-Man enter as a copy of any creature card in a graveyard, except his name is Superior Spider-Man and he's a 4/4 Spider Human Hero in addition to his other types. When you do, exile that card.",
    setup_interceptors=superior_spiderman_setup,
)

SYMBIOTE_SPIDERMAN = make_creature(
    name="Symbiote Spider-Man",
    power=2, toughness=4,
    mana_cost="{2}{U/B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Hero", "Spider", "Symbiote"},
    supertypes={"Legendary"},
    text="Whenever this creature deals combat damage to a player, look at that many cards from the top of your library. Put one of them into your hand and the rest into your graveyard.\nFind New Host — {2}{U/B}, Exile this card from your graveyard: Put a +1/+1 counter on target creature you control. It gains this card's other abilities. Activate only as a sorcery.",
    setup_interceptors=symbiote_spiderman_setup,
)

ULTIMATE_GREEN_GOBLIN = make_creature(
    name="Ultimate Green Goblin",
    power=5, toughness=4,
    mana_cost="{1}{B/R}{B/R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Goblin", "Villain"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, discard a card, then create a Treasure token.\nMayhem {2}{B/R} (You may cast this card from your graveyard for {2}{B/R} if you discarded it this turn. Timing rules still apply.)",
    setup_interceptors=ultimate_green_goblin_setup,
)

VULTURE_SCHEMING_SCAVENGER = make_creature(
    name="Vulture, Scheming Scavenger",
    power=4, toughness=6,
    mana_cost="{5}{U/B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Artificer", "Human", "Villain"},
    supertypes={"Legendary"},
    text="Flying\nWhenever Vulture attacks, other Villains you control gain flying until end of turn.",
    setup_interceptors=vulture_setup,
)

WEBWARRIORS = make_creature(
    name="Web-Warriors",
    power=4, toughness=3,
    mana_cost="{4}{G/W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hero", "Spider"},
    text="When this creature enters, put a +1/+1 counter on each other creature you control.",
    setup_interceptors=web_warriors_setup,
)

WRAITH_VICIOUS_VIGILANTE = make_creature(
    name="Wraith, Vicious Vigilante",
    power=1, toughness=1,
    mana_cost="{1}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Detective", "Hero", "Human"},
    supertypes={"Legendary"},
    text="Double strike\nFear Gas — Wraith can't be blocked.",
)

BAGEL_AND_SCHMEAR = make_artifact(
    name="Bagel and Schmear",
    mana_cost="{1}",
    text="Share — {W}, {T}, Sacrifice this artifact: Put a +1/+1 counter on up to one target creature. Draw a card. Activate only as a sorcery.\nNosh — {2}, {T}, Sacrifice this artifact: You gain 3 life and draw a card.",
    subtypes={"Food"},
    setup_interceptors=bagel_and_schmear_setup,
)

DOC_OCKS_TENTACLES = make_artifact(
    name="Doc Ock's Tentacles",
    mana_cost="{1}",
    text="Whenever a creature you control with mana value 5 or greater enters, you may attach this Equipment to it.\nEquipped creature gets +4/+4.\nEquip {5}",
    subtypes={"Equipment"},
    setup_interceptors=doc_ocks_tentacles_setup,
)

EERIE_GRAVESTONE = make_artifact(
    name="Eerie Gravestone",
    mana_cost="{2}",
    text="When this artifact enters, draw a card.\n{1}{B}, Sacrifice this artifact: Mill four cards. You may put a creature card from among them into your hand. (To mill four cards, put the top four cards of your library into your graveyard.)",
    setup_interceptors=eerie_gravestone_setup,
)

HOT_DOG_CART = make_artifact(
    name="Hot Dog Cart",
    mana_cost="{3}",
    text="When this artifact enters, create a Food token. (It's an artifact with \"{2}, {T}, Sacrifice this token: You gain 3 life.\")\n{T}: Add one mana of any color.",
    setup_interceptors=hot_dog_cart_setup,
)

INTERDIMENSIONAL_WEB_WATCH = make_artifact(
    name="Interdimensional Web Watch",
    mana_cost="{4}",
    text="When this artifact enters, exile the top two cards of your library. Until the end of your next turn, you may play those cards.\n{T}: Add two mana in any combination of colors. Spend this mana only to cast spells from exile.",
    setup_interceptors=interdimensional_web_watch_setup,
)

IRON_SPIDER_STARK_UPGRADE = make_artifact_creature(
    name="Iron Spider, Stark Upgrade",
    power=2, toughness=3,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Hero", "Spider"},
    supertypes={"Legendary"},
    text="Vigilance\n{T}: Put a +1/+1 counter on each artifact creature and/or Vehicle you control.\n{2}, Remove two +1/+1 counters from among artifacts you control: Draw a card.",
)

LIVING_BRAIN_MECHANICAL_MARVEL = make_artifact_creature(
    name="Living Brain, Mechanical Marvel",
    power=3, toughness=3,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Robot", "Villain"},
    supertypes={"Legendary"},
    text="At the beginning of combat on your turn, target non-Equipment artifact you control becomes an artifact creature with base power and toughness 3/3 until end of turn. Untap it.",
    setup_interceptors=living_brain_mechanical_marvel_setup,
)

MECHANICAL_MOBSTER = make_artifact_creature(
    name="Mechanical Mobster",
    power=2, toughness=1,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Human", "Robot", "Villain"},
    text="When this creature enters, exile up to one target card from a graveyard. Target creature you control connives. (Draw a card, then discard a card. If you discarded a nonland card, put a +1/+1 counter on that creature.)",
    setup_interceptors=mechanical_mobster_setup,
)

NEWS_HELICOPTER = make_artifact_creature(
    name="News Helicopter",
    power=1, toughness=1,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Construct"},
    text="Flying\nWhen this creature enters, create a 1/1 green and white Human Citizen creature token.",
    setup_interceptors=news_helicopter_setup,
)

PASSENGER_FERRY = make_artifact(
    name="Passenger Ferry",
    mana_cost="{3}",
    text="Whenever this Vehicle attacks, you may pay {U}. When you do, another target attacking creature can't be blocked this turn.\nCrew 2 (Tap any number of creatures you control with total power 2 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
    setup_interceptors=passenger_ferry_setup,
)

PETER_PARKERS_CAMERA = make_artifact(
    name="Peter Parker's Camera",
    mana_cost="{1}",
    text="This artifact enters with three film counters on it.\n{2}, {T}, Remove a film counter from this artifact: Copy target activated or triggered ability you control. You may choose new targets for the copy.",
    setup_interceptors=peter_parkers_camera_setup,
)

ROCKETPOWERED_GOBLIN_GLIDER = make_artifact(
    name="Rocket-Powered Goblin Glider",
    mana_cost="{3}",
    text="When this Equipment enters, if it was cast from your graveyard, attach it to target creature you control.\nEquipped creature gets +2/+0 and has flying and haste.\nEquip {2}\nMayhem {2}",
    subtypes={"Equipment"},
    setup_interceptors=rocketpowered_goblin_glider_setup,
)

SPIDERBOT = make_artifact_creature(
    name="Spider-Bot",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Robot", "Scout", "Spider"},
    text="Reach\nWhen this creature enters, you may search your library for a basic land card, reveal it, then shuffle and put that card on top.",
    setup_interceptors=spider_bot_setup,
)

SPIDERMOBILE = make_artifact(
    name="Spider-Mobile",
    mana_cost="{3}",
    text="Trample\nWhenever this Vehicle attacks or blocks, it gets +1/+1 until end of turn for each Spider you control.\nCrew 2",
    subtypes={"Vehicle"},
    setup_interceptors=spidermobile_setup,
)

SPIDERSLAYER_HATRED_HONED = make_artifact_creature(
    name="Spider-Slayer, Hatred Honed",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Human", "Villain"},
    supertypes={"Legendary"},
    text="Whenever Spider-Slayer deals damage to a Spider, destroy that creature.\n{6}, Exile this card from your graveyard: Create two tapped 1/1 colorless Robot artifact creature tokens with flying.",
    setup_interceptors=spiderslayer_hatred_honed_setup,
)

SPIDERSUIT = make_artifact(
    name="Spider-Suit",
    mana_cost="{1}",
    text="Equipped creature gets +2/+2 and is a Spider Hero in addition to its other types.\nEquip {3} ({3}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
    setup_interceptors=spidersuit_setup,
)

STEEL_WRECKING_BALL = make_artifact(
    name="Steel Wrecking Ball",
    mana_cost="{5}",
    text="When this artifact enters, it deals 5 damage to target creature.\n{1}{R}, Discard this card: Destroy target artifact.",
    setup_interceptors=steel_wrecking_ball_setup,
)

SUBWAY_TRAIN = make_artifact(
    name="Subway Train",
    mana_cost="{2}",
    text="When this Vehicle enters, you may pay {G}. If you do, search your library for a basic land card, reveal it, put it into your hand, then shuffle.\nCrew 2 (Tap any number of creatures you control with total power 2 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
    setup_interceptors=subway_train_setup,
)

DAILY_BUGLE_BUILDING = make_land(
    name="Daily Bugle Building",
    text="{T}: Add {C}.\n{1}, {T}: Add one mana of any color.\nSmear Campaign — {1}, {T}: Target legendary creature gains menace until end of turn. Activate only as a sorcery.",
    setup_interceptors=daily_bugle_building_setup,
)

MULTIVERSAL_PASSAGE = make_land(
    name="Multiversal Passage",
    text="As this land enters, choose a basic land type. Then you may pay 2 life. If you don't, it enters tapped.\nThis land is the chosen type.",
    setup_interceptors=multiversal_passage_setup,
)

OMINOUS_ASYLUM = make_land(
    name="Ominous Asylum",
    text="This land enters tapped.\n{T}: Add {B} or {R}.\n{4}, {T}: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

OSCORP_INDUSTRIES = make_land(
    name="Oscorp Industries",
    text="This land enters tapped.\nWhen this land enters from a graveyard, you lose 2 life.\n{T}: Add {U}, {B}, or {R}.\nMayhem (You may play this card from your graveyard if you discarded it this turn. Timing rules still apply.)",
    setup_interceptors=oscorp_industries_setup,
)

SAVAGE_MANSION = make_land(
    name="Savage Mansion",
    text="This land enters tapped.\n{T}: Add {R} or {G}.\n{4}, {T}: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

SINISTER_HIDEOUT = make_land(
    name="Sinister Hideout",
    text="This land enters tapped.\n{T}: Add {U} or {B}.\n{4}, {T}: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

SUBURBAN_SANCTUARY = make_land(
    name="Suburban Sanctuary",
    text="This land enters tapped.\n{T}: Add {G} or {W}.\n{4}, {T}: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

UNIVERSITY_CAMPUS = make_land(
    name="University Campus",
    text="This land enters tapped.\n{T}: Add {W} or {U}.\n{4}, {T}: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
)

URBAN_RETREAT = make_land(
    name="Urban Retreat",
    text="This land enters tapped.\n{T}: Add {G}, {W}, or {U}.\n{2}, Return a tapped creature you control to its owner's hand: Put this card from your hand onto the battlefield. Activate only as a sorcery.",
)

VIBRANT_CITYSCAPE = make_land(
    name="Vibrant Cityscape",
    text="{T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
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

SPIDER_MAN_CARDS = {
    "Anti-Venom, Horrifying Healer": ANTIVENOM_HORRIFYING_HEALER,
    "Arachne, Psionic Weaver": ARACHNE_PSIONIC_WEAVER,
    "Aunt May": AUNT_MAY,
    "City Pigeon": CITY_PIGEON,
    "Costume Closet": COSTUME_CLOSET,
    "Daily Bugle Reporters": DAILY_BUGLE_REPORTERS,
    "Flash Thompson, Spider-Fan": FLASH_THOMPSON_SPIDERFAN,
    "Friendly Neighborhood": FRIENDLY_NEIGHBORHOOD,
    "Origin of Spider-Man": ORIGIN_OF_SPIDERMAN,
    "Peter Parker": PETER_PARKER,
    "Rent Is Due": RENT_IS_DUE,
    "Selfless Police Captain": SELFLESS_POLICE_CAPTAIN,
    "Silver Sable, Mercenary Leader": SILVER_SABLE_MERCENARY_LEADER,
    "Spectacular Spider-Man": SPECTACULAR_SPIDERMAN,
    "Spectacular Tactics": SPECTACULAR_TACTICS,
    "Spider-Man, Web-Slinger": SPIDERMAN_WEBSLINGER,
    "Spider-UK": SPIDERUK,
    "Starling, Aerial Ally": STARLING_AERIAL_ALLY,
    "Sudden Strike": SUDDEN_STRIKE,
    "Thwip!": THWIP,
    "Web Up": WEB_UP,
    "Web-Shooters": WEBSHOOTERS,
    "Wild Pack Squad": WILD_PACK_SQUAD,
    "With Great Power...": WITH_GREAT_POWER,
    "Amazing Acrobatics": AMAZING_ACROBATICS,
    "Beetle, Legacy Criminal": BEETLE_LEGACY_CRIMINAL,
    "Chameleon, Master of Disguise": CHAMELEON_MASTER_OF_DISGUISE,
    "The Clone Saga": THE_CLONE_SAGA,
    "Doc Ock, Sinister Scientist": DOC_OCK_SINISTER_SCIENTIST,
    "Doc Ock's Henchmen": DOC_OCKS_HENCHMEN,
    "Flying Octobot": FLYING_OCTOBOT,
    "Hide on the Ceiling": HIDE_ON_THE_CEILING,
    "Hydro-Man, Fluid Felon": HYDROMAN_FLUID_FELON,
    "Impostor Syndrome": IMPOSTOR_SYNDROME,
    "Lady Octopus, Inspired Inventor": LADY_OCTOPUS_INSPIRED_INVENTOR,
    "Madame Web, Clairvoyant": MADAME_WEB_CLAIRVOYANT,
    "Mysterio, Master of Illusion": MYSTERIO_MASTER_OF_ILLUSION,
    "Mysterio's Phantasm": MYSTERIOS_PHANTASM,
    "Norman Osborn": NORMAN_OSBORN,
    "Oscorp Research Team": OSCORP_RESEARCH_TEAM,
    "Robotics Mastery": ROBOTICS_MASTERY,
    "School Daze": SCHOOL_DAZE,
    "Secret Identity": SECRET_IDENTITY,
    "Spider-Byte, Web Warden": SPIDERBYTE_WEB_WARDEN,
    "Spider-Man No More": SPIDERMAN_NO_MORE,
    "Spider-Sense": SPIDERSENSE,
    "Unstable Experiment": UNSTABLE_EXPERIMENT,
    "Whoosh!": WHOOSH,
    "Agent Venom": AGENT_VENOM,
    "Alien Symbiosis": ALIEN_SYMBIOSIS,
    "Behold the Sinister Six!": BEHOLD_THE_SINISTER_SIX,
    "Black Cat, Cunning Thief": BLACK_CAT_CUNNING_THIEF,
    "Common Crook": COMMON_CROOK,
    "The Death of Gwen Stacy": THE_DEATH_OF_GWEN_STACY,
    "Eddie Brock": EDDIE_BROCK,
    "Gwenom, Remorseless": GWENOM_REMORSELESS,
    "Inner Demons Gangsters": INNER_DEMONS_GANGSTERS,
    "Merciless Enforcers": MERCILESS_ENFORCERS,
    "Morlun, Devourer of Spiders": MORLUN_DEVOURER_OF_SPIDERS,
    "Parker Luck": PARKER_LUCK,
    "Prison Break": PRISON_BREAK,
    "Risky Research": RISKY_RESEARCH,
    "Sandman's Quicksand": SANDMANS_QUICKSAND,
    "Scorpion, Seething Striker": SCORPION_SEETHING_STRIKER,
    "Scorpion's Sting": SCORPIONS_STING,
    "The Soul Stone": THE_SOUL_STONE,
    "Spider-Man Noir": SPIDERMAN_NOIR,
    "The Spot's Portal": THE_SPOTS_PORTAL,
    "Swarm, Being of Bees": SWARM_BEING_OF_BEES,
    "Tombstone, Career Criminal": TOMBSTONE_CAREER_CRIMINAL,
    "Venom, Evil Unleashed": VENOM_EVIL_UNLEASHED,
    "Venomized Cat": VENOMIZED_CAT,
    "Venom's Hunger": VENOMS_HUNGER,
    "Villainous Wrath": VILLAINOUS_WRATH,
    "Angry Rabble": ANGRY_RABBLE,
    "Electro, Assaulting Battery": ELECTRO_ASSAULTING_BATTERY,
    "Electro's Bolt": ELECTROS_BOLT,
    "Gwen Stacy": GWEN_STACY,
    "Heroes' Hangout": HEROES_HANGOUT,
    "Hobgoblin, Mantled Marauder": HOBGOBLIN_MANTLED_MARAUDER,
    "J. Jonah Jameson": J_JONAH_JAMESON,
    "Masked Meower": MASKED_MEOWER,
    "Maximum Carnage": MAXIMUM_CARNAGE,
    "Molten Man, Inferno Incarnate": MOLTEN_MAN_INFERNO_INCARNATE,
    "Raging Goblinoids": RAGING_GOBLINOIDS,
    "Romantic Rendezvous": ROMANTIC_RENDEZVOUS,
    "Shadow of the Goblin": SHADOW_OF_THE_GOBLIN,
    "Shock": SHOCK,
    "Shocker, Unshakable": SHOCKER_UNSHAKABLE,
    "Spider-Gwen, Free Spirit": SPIDERGWEN_FREE_SPIRIT,
    "Spider-Islanders": SPIDERISLANDERS,
    "Spider-Punk": SPIDERPUNK,
    "Spider-Verse": SPIDERVERSE,
    "Spinneret and Spiderling": SPINNERET_AND_SPIDERLING,
    "Stegron the Dinosaur Man": STEGRON_THE_DINOSAUR_MAN,
    "Superior Foes of Spider-Man": SUPERIOR_FOES_OF_SPIDERMAN,
    "Taxi Driver": TAXI_DRIVER,
    "Wisecrack": WISECRACK,
    "Damage Control Crew": DAMAGE_CONTROL_CREW,
    "Ezekiel Sims, Spider-Totem": EZEKIEL_SIMS_SPIDERTOTEM,
    "Grow Extra Arms": GROW_EXTRA_ARMS,
    "Guy in the Chair": GUY_IN_THE_CHAIR,
    "Kapow!": KAPOW,
    "Kraven's Cats": KRAVENS_CATS,
    "Kraven's Last Hunt": KRAVENS_LAST_HUNT,
    "Lizard, Connors's Curse": LIZARD_CONNORSS_CURSE,
    "Lurking Lizards": LURKING_LIZARDS,
    "Miles Morales": MILES_MORALES,
    "Pictures of Spider-Man": PICTURES_OF_SPIDERMAN,
    "Professional Wrestler": PROFESSIONAL_WRESTLER,
    "Radioactive Spider": RADIOACTIVE_SPIDER,
    "Sandman, Shifting Scoundrel": SANDMAN_SHIFTING_SCOUNDREL,
    "Scout the City": SCOUT_THE_CITY,
    "Spider-Ham, Peter Porker": SPIDERHAM_PETER_PORKER,
    "Spider-Man, Brooklyn Visionary": SPIDERMAN_BROOKLYN_VISIONARY,
    "Spider-Rex, Daring Dino": SPIDERREX_DARING_DINO,
    "Spiders-Man, Heroic Horde": SPIDERSMAN_HEROIC_HORDE,
    "Strength of Will": STRENGTH_OF_WILL,
    "Supportive Parents": SUPPORTIVE_PARENTS,
    "Terrific Team-Up": TERRIFIC_TEAMUP,
    "Wall Crawl": WALL_CRAWL,
    "Web of Life and Destiny": WEB_OF_LIFE_AND_DESTINY,
    "Araña, Heart of the Spider": ARAA_HEART_OF_THE_SPIDER,
    "Biorganic Carapace": BIORGANIC_CARAPACE,
    "Carnage, Crimson Chaos": CARNAGE_CRIMSON_CHAOS,
    "Cheering Crowd": CHEERING_CROWD,
    "Cosmic Spider-Man": COSMIC_SPIDERMAN,
    "Doctor Octopus, Master Planner": DOCTOR_OCTOPUS_MASTER_PLANNER,
    "Gallant Citizen": GALLANT_CITIZEN,
    "Green Goblin, Revenant": GREEN_GOBLIN_REVENANT,
    "Jackal, Genius Geneticist": JACKAL_GENIUS_GENETICIST,
    "Kraven, Proud Predator": KRAVEN_PROUD_PREDATOR,
    "Kraven the Hunter": KRAVEN_THE_HUNTER,
    "Mary Jane Watson": MARY_JANE_WATSON,
    "Mister Negative": MISTER_NEGATIVE,
    "Mob Lookout": MOB_LOOKOUT,
    "Morbius the Living Vampire": MORBIUS_THE_LIVING_VAMPIRE,
    "Prowler, Clawed Thief": PROWLER_CLAWED_THIEF,
    "Pumpkin Bombardment": PUMPKIN_BOMBARDMENT,
    "Rhino, Barreling Brute": RHINO_BARRELING_BRUTE,
    "Rhino's Rampage": RHINOS_RAMPAGE,
    "Scarlet Spider, Ben Reilly": SCARLET_SPIDER_BEN_REILLY,
    "Scarlet Spider, Kaine": SCARLET_SPIDER_KAINE,
    "Shriek, Treblemaker": SHRIEK_TREBLEMAKER,
    "Silk, Web Weaver": SILK_WEB_WEAVER,
    "Skyward Spider": SKYWARD_SPIDER,
    "SP//dr, Piloted by Peni": SPDR_PILOTED_BY_PENI,
    "Spider Manifestation": SPIDER_MANIFESTATION,
    "Spider-Girl, Legacy Hero": SPIDERGIRL_LEGACY_HERO,
    "Spider-Man 2099": SPIDERMAN_2099,
    "Spider-Man India": SPIDERMAN_INDIA,
    "Spider-Woman, Stunning Savior": SPIDERWOMAN_STUNNING_SAVIOR,
    "The Spot, Living Portal": THE_SPOT_LIVING_PORTAL,
    "Sun-Spider, Nimble Webber": SUNSPIDER_NIMBLE_WEBBER,
    "Superior Spider-Man": SUPERIOR_SPIDERMAN,
    "Symbiote Spider-Man": SYMBIOTE_SPIDERMAN,
    "Ultimate Green Goblin": ULTIMATE_GREEN_GOBLIN,
    "Vulture, Scheming Scavenger": VULTURE_SCHEMING_SCAVENGER,
    "Web-Warriors": WEBWARRIORS,
    "Wraith, Vicious Vigilante": WRAITH_VICIOUS_VIGILANTE,
    "Bagel and Schmear": BAGEL_AND_SCHMEAR,
    "Doc Ock's Tentacles": DOC_OCKS_TENTACLES,
    "Eerie Gravestone": EERIE_GRAVESTONE,
    "Hot Dog Cart": HOT_DOG_CART,
    "Interdimensional Web Watch": INTERDIMENSIONAL_WEB_WATCH,
    "Iron Spider, Stark Upgrade": IRON_SPIDER_STARK_UPGRADE,
    "Living Brain, Mechanical Marvel": LIVING_BRAIN_MECHANICAL_MARVEL,
    "Mechanical Mobster": MECHANICAL_MOBSTER,
    "News Helicopter": NEWS_HELICOPTER,
    "Passenger Ferry": PASSENGER_FERRY,
    "Peter Parker's Camera": PETER_PARKERS_CAMERA,
    "Rocket-Powered Goblin Glider": ROCKETPOWERED_GOBLIN_GLIDER,
    "Spider-Bot": SPIDERBOT,
    "Spider-Mobile": SPIDERMOBILE,
    "Spider-Slayer, Hatred Honed": SPIDERSLAYER_HATRED_HONED,
    "Spider-Suit": SPIDERSUIT,
    "Steel Wrecking Ball": STEEL_WRECKING_BALL,
    "Subway Train": SUBWAY_TRAIN,
    "Daily Bugle Building": DAILY_BUGLE_BUILDING,
    "Multiversal Passage": MULTIVERSAL_PASSAGE,
    "Ominous Asylum": OMINOUS_ASYLUM,
    "Oscorp Industries": OSCORP_INDUSTRIES,
    "Savage Mansion": SAVAGE_MANSION,
    "Sinister Hideout": SINISTER_HIDEOUT,
    "Suburban Sanctuary": SUBURBAN_SANCTUARY,
    "University Campus": UNIVERSITY_CAMPUS,
    "Urban Retreat": URBAN_RETREAT,
    "Vibrant Cityscape": VIBRANT_CITYSCAPE,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
}

print(f"Loaded {len(SPIDER_MAN_CARDS)} Marvels_Spider-Man cards")
